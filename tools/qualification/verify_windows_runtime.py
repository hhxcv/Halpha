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

from halpha.configuration import load_settings, settings_digest
from halpha.runtime_identity import require_repository_runtime
from halpha.windows_runtime import (
    assert_kernel_object_security,
    current_process_sid,
    event_grants,
    signal_stop_event,
)
from halpha.winvault import require_win_vault_backend
from tools.provisioning.provision_windows_tasks import (
    APP_USER,
    EXECUTOR_USER,
    TASK_ACCOUNT_VAULT_SERVICE,
)


TASK_FOLDER = r"\Halpha"
TASK_STATE_READY = 3
TASK_STATE_RUNNING = 4
ACCESS_DENIED = winerror.ERROR_ACCESS_DENIED


class WindowsQualificationError(RuntimeError):
    """Sanitized Windows runtime qualification failure."""


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


def _task_identity_access(
    *,
    username: str,
    account_password: str,
    own_event: str,
    cross_event: str,
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
            try:
                cross = win32event.OpenEvent(
                    win32con.SYNCHRONIZE,
                    False,
                    cross_event,
                )
            except pywintypes.error as exc:
                cross_denied = exc.winerror == ACCESS_DENIED
                cross_error = int(exc.winerror)
            else:
                cross.Close()
                cross_denied = False
                cross_error = 0
        finally:
            win32security.RevertToSelf()
    finally:
        if profile is not None:
            win32profile.UnloadUserProfile(token, profile)
        token.Close()
    return {
        "own_event_wait_access": "ALLOWED",
        "cross_event_wait_access": "DENIED" if cross_denied else "ALLOWED",
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
        if profile is not None:
            win32profile.UnloadUserProfile(token, profile)
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


def _processes_by_module() -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = {"app": [], "executor": []}
    wmi = win32com.client.GetObject("winmgmts:")
    query = (
        "SELECT ProcessId,ParentProcessId,CommandLine,ExecutablePath "
        "FROM Win32_Process WHERE Name='python.exe'"
    )
    for process in wmi.ExecQuery(query):
        command = str(process.CommandLine or "")
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


def _task_xml_digest(repository_root: Path, role: str) -> str:
    path = repository_root / "build" / "runtime" / "tasks" / f"{role}.xml"
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
    if current_process_sid() != windows.maintenance_sid:
        raise WindowsQualificationError("MAINTENANCE_SID_MISMATCH")

    backend = keyring.get_keyring()
    require_win_vault_backend(backend)
    passwords = {
        "app": _task_password(backend, APP_USER),
        "executor": _task_password(backend, EXECUTOR_USER),
    }
    service = win32com.client.Dispatch("Schedule.Service")
    service.Connect()
    tasks = {"app": _task(service, "App"), "executor": _task(service, "Executor")}
    for task in tasks.values():
        task.Run("")
    for task in tasks.values():
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
        _assert_event_security(
            windows.executor_stop_event,
            windows.executor_task_sid,
            windows.maintenance_sid,
        )
        access = {
            "app": _task_identity_access(
                username=APP_USER,
                account_password=passwords["app"],
                own_event=windows.app_stop_event,
                cross_event=windows.executor_stop_event,
            ),
            "executor": _task_identity_access(
                username=EXECUTOR_USER,
                account_password=passwords["executor"],
                own_event=windows.executor_stop_event,
                cross_event=windows.app_stop_event,
            ),
        }
        app_required = (
            settings.app.database_credential_reference,
            settings.app.owner_password_hash_reference,
            settings.app.session_signing_reference,
            settings.app.csrf_signing_reference,
            settings.maintenance.demo.migration_credential_reference,
            settings.maintenance.demo.backup_credential_reference,
            settings.maintenance.live.migration_credential_reference,
            settings.maintenance.live.backup_credential_reference,
        )
        app_forbidden = [
            settings.executor.database_credential_reference,
            settings.executor.binance_api_key_reference,
            settings.executor.binance_api_secret_reference,
        ]
        if settings.executor.runtime_proxy_reference is not None:
            app_forbidden.append(settings.executor.runtime_proxy_reference)
        executor_required = tuple(app_forbidden)
        executor_forbidden = (
            settings.app.database_credential_reference,
            settings.app.owner_password_hash_reference,
            settings.app.session_signing_reference,
            settings.app.csrf_signing_reference,
            settings.app.smtp_credential_reference,
            settings.maintenance.demo.migration_credential_reference,
            settings.maintenance.demo.backup_credential_reference,
            settings.maintenance.live.migration_credential_reference,
            settings.maintenance.live.backup_credential_reference,
        )
        vault_access = {
            "app": _task_vault_visibility(
                username=APP_USER,
                account_password=passwords["app"],
                required=app_required,
                forbidden=tuple(app_forbidden),
            ),
            "executor": _task_vault_visibility(
                username=EXECUTOR_USER,
                account_password=passwords["executor"],
                required=executor_required,
                forbidden=executor_forbidden,
            ),
        }
        before = _processes_by_module()
        for task in tasks.values():
            task.Run("")
        time.sleep(0.5)
        after_duplicate_start = _processes_by_module()
        if before != after_duplicate_start:
            raise WindowsQualificationError("IGNORE_NEW_PROCESS_SET_CHANGED")

        signal_stop_event(
            name=windows.app_stop_event,
            task_sid=windows.app_task_sid,
            maintenance_sid=windows.maintenance_sid,
        )
        signal_stop_event(
            name=windows.executor_stop_event,
            task_sid=windows.executor_task_sid,
            maintenance_sid=windows.maintenance_sid,
        )
    finally:
        passwords.clear()

    for task in tasks.values():
        _wait_for_state(task, TASK_STATE_READY, 30)
    task_results = {
        role: int(task.GetInstances(0).Count) for role, task in tasks.items()
    }
    last_results = {
        role: int(task.LastTaskResult) for role, task in tasks.items()
    }

    expected_owners = {
        "app": f"{socket.gethostname()}\\{APP_USER}",
        "executor": f"{socket.gethostname()}\\{EXECUTOR_USER}",
    }
    owners_match = all(
        processes
        and all(item["owner"].casefold() == expected_owners[role].casefold() for item in processes)
        for role, processes in before.items()
    )
    cross_denied = all(
        item["cross_event_wait_access"] == "DENIED"
        and item["cross_event_winerror"] == ACCESS_DENIED
        for item in access.values()
    )
    qualified = (
        owners_match
        and cross_denied
        and all(item["boundary"] == "QUALIFIED" for item in vault_access.values())
        and all(value == 0 for value in last_results.values())
        and all(value == 0 for value in task_results.values())
    )
    report: dict[str, Any] = {
        "schema_version": 1,
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": "QUALIFIED" if qualified else "REJECTED",
        "runtime": {
            "python_version": runtime.python_version,
            "executable": runtime.executable,
        },
        "configuration_sha256": settings_digest(settings),
        "tasks": {
            "app": {
                "path": r"\Halpha\App",
                "xml_sha256": _task_xml_digest(repository_root, "app"),
                "processes": before["app"],
                "expected_owner": expected_owners["app"],
                "last_result": last_results["app"],
            },
            "executor": {
                "path": r"\Halpha\Executor",
                "xml_sha256": _task_xml_digest(repository_root, "executor"),
                "processes": before["executor"],
                "expected_owner": expected_owners["executor"],
                "last_result": last_results["executor"],
            },
        },
        "http": {"operations_status": status, "bind": "127.0.0.1"},
        "named_events": {
            "dacl": "EXACT_PROTECTED",
            "access": access,
            "maintenance_stop": "SIGNALED",
        },
        "winvault": vault_access,
        "multiple_instances": "IGNORE_NEW_VERIFIED",
        "post_stop_instances": task_results,
        "secret_transport": "IN_PROCESS_BATCH_LOGON_ONLY",
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
