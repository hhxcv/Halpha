"""Qualify the real Windows task identities and protected stop boundary.

The report contains only non-secret host evidence. Task-account passwords stay
inside this maintenance process and are used only for Windows batch logon.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import socket
import time
from typing import Any, Sequence
from urllib.request import urlopen

import keyring
from keyring.backends.Windows import WinVaultKeyring
import pywintypes
import win32com.client
import win32con
import win32event
import win32profile
import win32security
import winerror

from halpha.configuration import (
    app_settings,
    executor_settings,
    known_live_credential_references,
    load_settings,
    settings_digest,
)
from halpha.runtime_identity import require_repository_runtime
from halpha.windows_runtime import (
    assert_kernel_object_security,
    current_process_sid,
    event_grants,
    signal_stop_event,
)
from halpha.winvault import (
    app_peer_secret_references,
    app_secret_references,
    executor_forbidden_secret_references,
    executor_secret_references,
    require_win_vault_backend,
)
from halpha.windows_deployment import (
    SHARED_BACKUP_TASK,
    SHARED_BACKUP_USER,
    windows_deployment,
)
from tools.provisioning.provision_windows_tasks import (
    TASK_ACCOUNT_VAULT_SERVICE,
)


TASK_FOLDER = r"\Halpha"
TASK_STATE_DISABLED = 1
TASK_STATE_READY = 3
TASK_STATE_RUNNING = 4
ACCESS_DENIED = winerror.ERROR_ACCESS_DENIED


class WindowsQualificationError(RuntimeError):
    """Sanitized Windows runtime qualification failure."""


def _executor_runtime_policy(
    *,
    read_only: bool,
    continuous_account_observation: bool,
) -> tuple[bool, str]:
    if not read_only:
        return True, "PERSISTENT_TRADING_TASK"
    if continuous_account_observation:
        return True, "PERSISTENT_ACCOUNT_OBSERVER"
    return False, "EXPLICIT_OBSERVATION_SESSION_ONLY"


def _canonical_digest(value: dict[str, Any]) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _task_password(backend: object, username: str) -> str:
    value = backend.get_password(TASK_ACCOUNT_VAULT_SERVICE, username)
    if not value:
        raise WindowsQualificationError(
            f"TASK_ACCOUNT_PASSWORD_REFERENCE_MISSING user={username}"
        )
    return value


def _unload_task_identity_profile(
    token: Any,
    profile: Any,
    *,
    username: str,
) -> None:
    try:
        win32profile.UnloadUserProfile(token, profile)
    except pywintypes.error as exc:
        if exc.winerror == winerror.ERROR_INVALID_HANDLE:
            return
        raise WindowsQualificationError(
            f"TASK_IDENTITY_PROFILE_UNLOAD_FAILED user={username} "
            f"code={exc.winerror}"
        ) from None


def _task_identity_access(
    *,
    username: str,
    account_password: str,
    own_event: str,
    cross_event: str | None,
) -> dict[str, object]:
    try:
        token = win32security.LogonUser(
            username,
            ".",
            account_password,
            win32con.LOGON32_LOGON_BATCH,
            win32con.LOGON32_PROVIDER_DEFAULT,
        )
    except pywintypes.error as exc:
        raise WindowsQualificationError(
            f"TASK_IDENTITY_LOGON_FAILED user={username} code={exc.winerror}"
        ) from None
    profile = None
    try:
        try:
            profile = win32profile.LoadUserProfile(token, {"UserName": username})
        except pywintypes.error as exc:
            raise WindowsQualificationError(
                f"TASK_IDENTITY_PROFILE_LOAD_FAILED user={username} code={exc.winerror}"
            ) from None
        win32security.ImpersonateLoggedOnUser(token)
        try:
            own = win32event.OpenEvent(win32con.SYNCHRONIZE, False, own_event)
            own.Close()
            if cross_event is None:
                cross_access = "NOT_APPLICABLE"
                cross_error: int | None = None
            else:
                try:
                    cross = win32event.OpenEvent(
                        win32con.SYNCHRONIZE,
                        False,
                        cross_event,
                    )
                except pywintypes.error as exc:
                    cross_access = (
                        "DENIED" if exc.winerror == ACCESS_DENIED else "ERROR"
                    )
                    cross_error = int(exc.winerror)
                else:
                    cross.Close()
                    cross_access = "ALLOWED"
                    cross_error = 0
        finally:
            win32security.RevertToSelf()
    finally:
        try:
            if profile is not None:
                _unload_task_identity_profile(
                    token,
                    profile,
                    username=username,
                )
        finally:
            token.Close()
    return {
        "own_event_wait_access": "ALLOWED",
        "cross_event_wait_access": cross_access,
        "cross_event_winerror": cross_error,
    }


def _task_vault_visibility(
    *,
    username: str,
    account_password: str,
    required: Sequence[Any],
    forbidden: Sequence[Any],
) -> dict[str, object]:
    try:
        token = win32security.LogonUser(
            username,
            ".",
            account_password,
            win32con.LOGON32_LOGON_BATCH,
            win32con.LOGON32_PROVIDER_DEFAULT,
        )
    except pywintypes.error as exc:
        raise WindowsQualificationError(
            f"TASK_IDENTITY_LOGON_FAILED user={username} code={exc.winerror}"
        ) from None
    profile = None
    try:
        try:
            profile = win32profile.LoadUserProfile(token, {"UserName": username})
        except pywintypes.error as exc:
            raise WindowsQualificationError(
                f"TASK_IDENTITY_PROFILE_LOAD_FAILED user={username} code={exc.winerror}"
            ) from None
        win32security.ImpersonateLoggedOnUser(token)
        try:
            backend = WinVaultKeyring()
            require_win_vault_backend(backend)
            required_visible = sum(
                bool(backend.get_password(reference.service, reference.account))
                for reference in required
            )
            forbidden_visible = sum(
                backend.get_password(reference.service, reference.account) is not None
                for reference in forbidden
            )
        finally:
            win32security.RevertToSelf()
    finally:
        try:
            if profile is not None:
                _unload_task_identity_profile(
                    token,
                    profile,
                    username=username,
                )
        finally:
            token.Close()
    return {
        "required_reference_count": len(required),
        "required_reference_visible_count": required_visible,
        "forbidden_reference_count": len(forbidden),
        "forbidden_reference_visible_count": forbidden_visible,
        "boundary": (
            "QUALIFIED"
            if required_visible == len(required) and forbidden_visible == 0
            else "REJECTED"
        ),
    }


def _task(service: Any, name: str) -> Any:
    return service.GetFolder(TASK_FOLDER).GetTask(name)


def _wait_for_state(task: Any, expected: int, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if int(task.State) == expected:
            return
        time.sleep(0.2)
    raise WindowsQualificationError(
        f"TASK_STATE_TIMEOUT task={task.Name} expected={expected} actual={int(task.State)}"
    )


def _processes_by_module(config_path: Path) -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = {"app": [], "executor": []}
    config_key = str(config_path.resolve()).replace("/", "\\").casefold()
    wmi = win32com.client.GetObject("winmgmts:")
    query = (
        "SELECT ProcessId,ParentProcessId,CommandLine,ExecutablePath "
        "FROM Win32_Process WHERE Name='python.exe'"
    )
    for process in wmi.ExecQuery(query):
        command = str(process.CommandLine or "")
        if config_key not in command.replace("/", "\\").casefold():
            continue
        if "-m halpha.app" in command:
            role = "app"
        elif "-m halpha.executor" in command:
            role = "executor"
        else:
            continue
        owner = process.ExecMethod_("GetOwner")
        if int(owner.Properties_("ReturnValue").Value) != 0:
            raise WindowsQualificationError(f"PROCESS_OWNER_LOOKUP_FAILED role={role}")
        result[role].append(
            {
                "pid": int(process.ProcessId),
                "parent_pid": int(process.ParentProcessId),
                "owner": (
                    f"{owner.Properties_('Domain').Value}\\"
                    f"{owner.Properties_('User').Value}"
                ),
                "executable": str(process.ExecutablePath or ""),
            }
        )
    for processes in result.values():
        processes.sort(key=lambda item: int(item["pid"]))
    return result


def _assert_event_security(name: str, task_sid: str, maintenance_sid: str) -> None:
    handle = win32event.OpenEvent(
        win32con.READ_CONTROL | win32con.SYNCHRONIZE,
        False,
        name,
    )
    try:
        assert_kernel_object_security(
            handle,
            owner_sid=task_sid,
            grants=event_grants(task_sid, maintenance_sid),
        )
    finally:
        handle.Close()


def _http_status(port: int) -> int:
    with urlopen(f"http://127.0.0.1:{port}/operations", timeout=5) as response:
        return int(response.status)


def _task_xml_digest(
    repository_root: Path,
    role: str,
    environment_namespace: str,
) -> str:
    artifact_name = (
        "backup.xml"
        if role == "backup"
        else f"{role}.{environment_namespace}.xml"
    )
    path = repository_root / "build" / "runtime" / "tasks" / artifact_name
    if not path.is_file():
        raise WindowsQualificationError(f"TASK_XML_MISSING role={role}")
    content = path.read_bytes()
    if b"<Password>" in content or TASK_ACCOUNT_VAULT_SERVICE.encode() in content:
        raise WindowsQualificationError(f"TASK_XML_SECRET_MATERIAL_DETECTED role={role}")
    return sha256(content).hexdigest()


def qualify(repository_root: Path, config_path: Path) -> dict[str, Any]:
    runtime = require_repository_runtime(repository_root)
    settings = load_settings(config_path)
    windows = settings.windows
    deployment = windows_deployment(settings.release.venue_account_type.value)
    read_only = settings.release.profile == "BINANCE_LIVE_READ_ONLY"
    executor_persistent, executor_runtime_mode = _executor_runtime_policy(
        read_only=read_only,
        continuous_account_observation=(
            settings.executor.continuous_account_observation
        ),
    )
    if current_process_sid() != windows.maintenance_sid:
        raise WindowsQualificationError("MAINTENANCE_SID_MISMATCH")

    backend = keyring.get_keyring()
    require_win_vault_backend(backend)
    passwords = {
        "app": _task_password(backend, deployment.app_user),
        "executor": _task_password(backend, deployment.executor_user),
    }
    if deployment.owns_shared_backup:
        passwords["backup"] = _task_password(backend, SHARED_BACKUP_USER)
    service = win32com.client.Dispatch("Schedule.Service")
    service.Connect()
    tasks = {
        "app": _task(service, deployment.app_task),
        "executor": _task(service, deployment.executor_task),
    }
    persistent_tasks = {
        role: task
        for role, task in tasks.items()
        if role != "executor" or executor_persistent
    }
    if read_only and not executor_persistent and (
        bool(tasks["executor"].Enabled)
        or int(tasks["executor"].State) != TASK_STATE_DISABLED
        or int(tasks["executor"].GetInstances(0).Count) != 0
    ):
        raise WindowsQualificationError(
            "READ_ONLY_EXECUTOR_TASK_MUST_BE_DISABLED"
        )
    for task in persistent_tasks.values():
        task.Run("")
    for task in persistent_tasks.values():
        _wait_for_state(task, TASK_STATE_RUNNING, 30)

    try:
        deadline = time.monotonic() + 30
        status = 0
        while time.monotonic() < deadline:
            try:
                status = _http_status(settings.app.port)
            except OSError:
                time.sleep(0.2)
                continue
            break
        if status != 200:
            raise WindowsQualificationError(f"APP_HTTP_STATUS_INVALID status={status}")

        _assert_event_security(
            windows.app_stop_event,
            windows.app_task_sid,
            windows.maintenance_sid,
        )
        access = {
            "app": _task_identity_access(
                username=deployment.app_user,
                account_password=passwords["app"],
                own_event=windows.app_stop_event,
                cross_event=(
                    windows.executor_stop_event
                    if executor_persistent
                    else None
                ),
            ),
        }
        if executor_persistent:
            _assert_event_security(
                windows.executor_stop_event,
                windows.executor_task_sid,
                windows.maintenance_sid,
            )
            access["executor"] = _task_identity_access(
                username=deployment.executor_user,
                account_password=passwords["executor"],
                own_event=windows.executor_stop_event,
                cross_event=windows.app_stop_event,
            )
        app_required = [
            settings.app.database_credential_reference,
            settings.app.csrf_signing_reference,
        ]
        if settings.email.delivery_enabled:
            app_required.append(settings.app.smtp_credential_reference)
        role_settings = executor_settings(settings)
        app_role_settings = app_settings(settings)
        peer_app_references = app_peer_secret_references(app_role_settings)
        executor_required = executor_secret_references(role_settings)
        known_executor_references = {
            *executor_required,
            *executor_forbidden_secret_references(role_settings),
        }
        known_app_references = {
            *app_secret_references(app_role_settings),
            *peer_app_references,
        }
        known_live_references = set(known_live_credential_references())
        maintenance_references = tuple(
            reference
            for _name, target in settings.maintenance.named_targets()
            for reference in (
                target.migration_credential_reference,
                target.backup_credential_reference,
            )
        )
        app_forbidden = tuple(dict.fromkeys((
            *peer_app_references,
            *known_executor_references,
            *maintenance_references,
            *(
                reference
                for reference in known_live_references
                if reference not in app_required
            ),
        )))
        executor_forbidden = tuple(dict.fromkeys((
            *known_app_references,
            *maintenance_references,
            *executor_forbidden_secret_references(role_settings),
            *(
                reference
                for reference in known_live_references
                if reference not in executor_required
            ),
        )))
        backup_required = tuple(
            target.backup_credential_reference
            for _name, target in settings.maintenance.named_targets()
        )
        backup_forbidden = tuple(dict.fromkeys((
            *known_app_references,
            *known_executor_references,
            *(
                target.migration_credential_reference
                for _name, target in settings.maintenance.named_targets()
            ),
            *(
                reference
                for reference in known_live_references
                if reference not in backup_required
            ),
        )))
        vault_access: dict[str, dict[str, object]] = {
            "app": _task_vault_visibility(
                username=deployment.app_user,
                account_password=passwords["app"],
                required=tuple(app_required),
                forbidden=app_forbidden,
            ),
            "executor": _task_vault_visibility(
                username=deployment.executor_user,
                account_password=passwords["executor"],
                required=executor_required,
                forbidden=executor_forbidden,
            ),
        }
        if deployment.owns_shared_backup:
            vault_access["backup"] = _task_vault_visibility(
                username=SHARED_BACKUP_USER,
                account_password=passwords["backup"],
                required=backup_required,
                forbidden=backup_forbidden,
            )
        before = _processes_by_module(config_path)
        for task in persistent_tasks.values():
            task.Run("")
        time.sleep(0.5)
        after_duplicate_start = _processes_by_module(config_path)
        if before != after_duplicate_start:
            raise WindowsQualificationError("IGNORE_NEW_PROCESS_SET_CHANGED")

        signal_stop_event(
            name=windows.app_stop_event,
            task_sid=windows.app_task_sid,
            maintenance_sid=windows.maintenance_sid,
        )
        if executor_persistent:
            signal_stop_event(
                name=windows.executor_stop_event,
                task_sid=windows.executor_task_sid,
                maintenance_sid=windows.maintenance_sid,
            )
    finally:
        passwords.clear()

    for task in persistent_tasks.values():
        _wait_for_state(task, TASK_STATE_READY, 30)
    task_results = {
        role: int(task.GetInstances(0).Count) for role, task in tasks.items()
    }
    last_results = {
        role: int(task.LastTaskResult) for role, task in tasks.items()
    }

    expected_owners = {
        "app": f"{socket.gethostname()}\\{deployment.app_user}",
        "executor": f"{socket.gethostname()}\\{deployment.executor_user}",
    }
    owners_match = bool(before["app"]) and all(
        item["owner"].casefold() == expected_owners["app"].casefold()
        for item in before["app"]
    )
    if not executor_persistent:
        owners_match = owners_match and not before["executor"]
        cross_denied = (
            access["app"]["cross_event_wait_access"] == "NOT_APPLICABLE"
        )
    else:
        owners_match = owners_match and bool(before["executor"]) and all(
            item["owner"].casefold() == expected_owners["executor"].casefold()
            for item in before["executor"]
        )
        cross_denied = all(
            item["cross_event_wait_access"] == "DENIED"
            and item["cross_event_winerror"] == ACCESS_DENIED
            for item in access.values()
        )
    persistent_last_results = {
        role: last_results[role] for role in persistent_tasks
    }
    qualified = (
        owners_match
        and cross_denied
        and all(item["boundary"] == "QUALIFIED" for item in vault_access.values())
        and all(value == 0 for value in persistent_last_results.values())
        and all(value == 0 for value in task_results.values())
        and (
            executor_persistent
            or (
                not bool(tasks["executor"].Enabled)
                and int(tasks["executor"].State) == TASK_STATE_DISABLED
            )
        )
    )
    report: dict[str, Any] = {
        "schema_version": 2,
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": "QUALIFIED" if qualified else "REJECTED",
        "runtime": {
            "python_version": runtime.python_version,
            "executable": runtime.executable,
        },
        "configuration_sha256": settings_digest(settings),
        "tasks": {
            "app": {
                "path": f"{TASK_FOLDER}\\{deployment.app_task}",
                "xml_sha256": _task_xml_digest(
                    repository_root,
                    "app",
                    deployment.namespace,
                ),
                "processes": before["app"],
                "expected_owner": expected_owners["app"],
                "last_result": last_results["app"],
            },
            "executor": {
                "path": f"{TASK_FOLDER}\\{deployment.executor_task}",
                "xml_sha256": _task_xml_digest(
                    repository_root,
                    "executor",
                    deployment.namespace,
                ),
                "processes": before["executor"],
                "expected_owner": expected_owners["executor"],
                "last_result": last_results["executor"],
                "enabled": bool(tasks["executor"].Enabled),
                "runtime_mode": executor_runtime_mode,
            },
        },
        "http": {"operations_status": status, "bind": "127.0.0.1"},
        "named_events": {
            "dacl": "EXACT_PROTECTED",
            "access": access,
            "maintenance_stop": (
                "APP_AND_EXECUTOR_SIGNALED"
                if executor_persistent
                else "APP_SIGNALED_EXECUTOR_NOT_CREATED"
            ),
        },
        "winvault": vault_access,
        "multiple_instances": (
            "APP_AND_EXECUTOR_IGNORE_NEW_VERIFIED"
            if executor_persistent
            else "APP_IGNORE_NEW_VERIFIED_EXECUTOR_DISABLED"
        ),
        "post_stop_instances": task_results,
        "secret_transport": "IN_PROCESS_BATCH_LOGON_ONLY",
    }
    if deployment.owns_shared_backup:
        report["tasks"]["backup"] = {
            "path": f"{TASK_FOLDER}\\{SHARED_BACKUP_TASK}",
            "xml_sha256": _task_xml_digest(
                repository_root,
                "backup",
                deployment.namespace,
            ),
            "expected_owner": (
                f"{socket.gethostname()}\\{SHARED_BACKUP_USER}"
            ),
        }
    report["evidence_digest"] = _canonical_digest(report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="verify-windows-runtime")
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = qualify(args.repository_root.resolve(), args.config.resolve())
    except Exception as exc:
        reason = str(exc) if isinstance(exc, WindowsQualificationError) else (
            f"WINDOWS_RUNTIME_QUALIFICATION_FAILED type={type(exc).__name__}"
        )
        print(json.dumps({"status": "REJECTED", "reason": reason}, sort_keys=True))
        return 2
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(f"{args.output.suffix}.tmp")
        temporary.write_text(rendered, encoding="utf-8")
        temporary.replace(args.output)
    print(rendered, end="")
    return 0 if report["status"] == "QUALIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
