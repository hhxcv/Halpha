"""Provision dedicated non-admin Windows identities and Halpha tasks.

Task-account passwords are generated in process memory, stored only in the
maintenance identity's Windows Credential Manager, and passed to the Task
Scheduler COM API without command-line or file transport.
"""

from __future__ import annotations

import argparse
from contextlib import nullcontext
from hashlib import sha256
import json
from pathlib import Path
import secrets
import socket
import string
import time
from typing import Any, Sequence

import keyring
import pywintypes
import win32api
import win32com.client
import win32con
import win32net
import win32netcon
import win32security

from halpha.configuration import HalphaSettings, load_settings
from halpha.runtime_identity import require_repository_runtime
from halpha.runtime_control import RuntimeController, RuntimeControlError
from halpha.winvault import require_win_vault_backend
from halpha.windows_deployment import (
    SHARED_BACKUP_TASK,
    SHARED_BACKUP_USER,
    WindowsDeployment,
    windows_deployment,
)
from halpha.windows_runtime import (
    WindowsRuntimeError,
    acquire_executor_maintenance_mutex,
)


TASK_ACCOUNT_VAULT_SERVICE = "Halpha/Windows/TaskAccounts"
BACKUP_USER = SHARED_BACKUP_USER
TASK_FOLDER = r"\Halpha"
TASK_CREATE_OR_UPDATE = 6
TASK_LOGON_PASSWORD = 1
TASK_RUNLEVEL_LUA = 0
TASK_TRIGGER_BOOT = 8
TASK_TRIGGER_DAILY = 2
TASK_ACTION_EXEC = 0
TASK_INSTANCES_IGNORE_NEW = 2
TASK_STATE_QUEUED = 2
TASK_STATE_RUNNING = 4
WATCHDOG_START_BOUNDARY = "2000-01-01T00:00:00"
WATCHDOG_INTERVAL = "PT1M"
WATCHDOG_DURATION = "P1D"
USER_FLAGS = (
    win32netcon.UF_SCRIPT
    | win32netcon.UF_NORMAL_ACCOUNT
    | win32netcon.UF_DONT_EXPIRE_PASSWD
    | win32netcon.UF_PASSWD_CANT_CHANGE
)
REQUIRED_ACCOUNT_RIGHTS = (
    "SeBatchLogonRight",
    "SeDenyInteractiveLogonRight",
    "SeDenyRemoteInteractiveLogonRight",
)


class ProvisioningError(RuntimeError):
    """Sanitized host-provisioning failure."""


def _require_elevated_administrator() -> None:
    administrators = win32security.ConvertStringSidToSid("S-1-5-32-544")
    if not win32security.CheckTokenMembership(None, administrators):
        raise ProvisioningError("ADMINISTRATOR_TOKEN_REQUIRED")


def _generate_password() -> str:
    alphabet = string.ascii_letters + string.digits + "-_!@#%"
    return "H!" + "".join(secrets.choice(alphabet) for _ in range(46)) + "9z"


def _task_account_password(username: str) -> str:
    backend = keyring.get_keyring()
    require_win_vault_backend(backend)
    try:
        password = backend.get_password(TASK_ACCOUNT_VAULT_SERVICE, username)
        if not password:
            password = _generate_password()
            backend.set_password(TASK_ACCOUNT_VAULT_SERVICE, username, password)
        if backend.get_password(TASK_ACCOUNT_VAULT_SERVICE, username) != password:
            raise ProvisioningError("TASK_ACCOUNT_VAULT_WRITEBACK_MISMATCH")
        return password
    except ProvisioningError:
        raise
    except Exception as exc:
        raise ProvisioningError(
            f"TASK_ACCOUNT_VAULT_FAILED type={type(exc).__name__}"
        ) from None


def _ensure_local_user(username: str, password: str, comment: str) -> None:
    info = {
        "name": username,
        "password": password,
        "priv": win32netcon.USER_PRIV_USER,
        "home_dir": None,
        "comment": comment,
        "flags": USER_FLAGS,
        "script_path": None,
    }
    try:
        win32net.NetUserGetInfo(None, username, 1)
    except pywintypes.error as exc:
        if exc.winerror != 2221:  # NERR_UserNotFound
            raise ProvisioningError(
                f"TASK_ACCOUNT_LOOKUP_FAILED user={username} code={exc.winerror}"
            ) from None
        try:
            win32net.NetUserAdd(None, 1, info)
        except pywintypes.error as create_exc:
            raise ProvisioningError(
                f"TASK_ACCOUNT_CREATE_FAILED user={username} code={create_exc.winerror}"
            ) from None
    else:
        try:
            win32net.NetUserSetInfo(None, username, 1003, {"password": password})
            win32net.NetUserSetInfo(None, username, 1008, {"flags": USER_FLAGS})
            win32net.NetUserSetInfo(None, username, 1007, {"comment": comment})
        except pywintypes.error as update_exc:
            raise ProvisioningError(
                f"TASK_ACCOUNT_UPDATE_FAILED user={username} code={update_exc.winerror}"
            ) from None

    administrator_name = win32security.LookupAccountSid(
        None,
        win32security.ConvertStringSidToSid("S-1-5-32-544"),
    )[0]
    local_groups = set(
        win32net.NetUserGetLocalGroups(
            None,
            username,
            win32netcon.LG_INCLUDE_INDIRECT,
        )
    )
    if administrator_name in local_groups:
        raise ProvisioningError(f"TASK_ACCOUNT_MUST_NOT_BE_ADMIN user={username}")


def _account_sid(username: str) -> str:
    account = f"{socket.gethostname()}\\{username}"
    try:
        sid = win32security.LookupAccountName(None, account)[0]
    except pywintypes.error as exc:
        raise ProvisioningError(
            f"TASK_ACCOUNT_SID_LOOKUP_FAILED user={username} code={exc.winerror}"
        ) from None
    return str(win32security.ConvertSidToStringSid(sid))


def _current_user_sid() -> str:
    token = win32security.OpenProcessToken(
        win32api.GetCurrentProcess(),
        win32con.TOKEN_QUERY,
    )
    try:
        sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
        return str(win32security.ConvertSidToStringSid(sid))
    finally:
        token.Close()


def _require_configured_identity_sids(
    *,
    configured: dict[str, str],
    actual: dict[str, str],
) -> None:
    mismatches = tuple(
        role
        for role in sorted(configured)
        if configured[role] != actual.get(role)
    )
    if not mismatches:
        return
    details = ",".join(
        f"{role}:{configured[role]}!={actual.get(role, 'MISSING')}"
        for role in mismatches
    )
    raise ProvisioningError(
        f"WINDOWS_IDENTITY_CONFIG_MISMATCH roles={','.join(mismatches)} "
        f"details={details}"
    )


def _grant_batch_only_rights(username: str) -> tuple[str, ...]:
    sid = win32security.ConvertStringSidToSid(_account_sid(username))
    policy = win32security.LsaOpenPolicy(
        None,
        win32security.POLICY_LOOKUP_NAMES | win32security.POLICY_CREATE_ACCOUNT,
    )
    try:
        win32security.LsaAddAccountRights(policy, sid, REQUIRED_ACCOUNT_RIGHTS)
        rights = tuple(sorted(win32security.LsaEnumerateAccountRights(policy, sid)))
    finally:
        policy.Close()
    missing = sorted(set(REQUIRED_ACCOUNT_RIGHTS) - set(rights))
    if missing:
        raise ProvisioningError(
            f"TASK_ACCOUNT_RIGHTS_MISSING user={username} rights={','.join(missing)}"
        )
    return rights


def _task_folder(service: Any) -> Any:
    try:
        return service.GetFolder(TASK_FOLDER)
    except pywintypes.com_error:
        root = service.GetFolder("\\")
        try:
            return root.CreateFolder("Halpha")
        except pywintypes.com_error as exc:
            raise ProvisioningError(
                f"TASK_FOLDER_CREATE_FAILED code={exc.hresult}"
            ) from None


def _require_live_task_reprojection_stopped(
    *,
    repository_root: Path,
    config_path: Path,
    settings: HalphaSettings,
    task_service: Any,
) -> None:
    if settings.release.profile not in {
        "BINANCE_LIVE_READ_ONLY",
        "BINANCE_LIVE_WRITE",
    }:
        return
    try:
        inventory = RuntimeController(
            repository_root,
            settings,
            config_path,
            task_service_factory=lambda: task_service,
        ).inventory()
    except RuntimeControlError as exc:
        raise ProvisioningError(
            "LIVE_TASK_REPROJECTION_STOP_CHECK_FAILED "
            f"type={type(exc).__name__}"
        ) from None

    violations = []
    for instance in inventory.services:
        if (
            instance.manager == "DISCOVERED_ONLY"
            and instance.recognized_as in {"app", "executor"}
        ):
            count = len(instance.process_ids) or 1
            violations.append(
                f"{instance.service}:unmanaged+instances={count}"
            )
            continue
        if (
            instance.manager != "WINDOWS_TASK"
            or instance.service not in {"app", "executor"}
        ):
            continue
        facts: list[str] = []
        if instance.enabled:
            facts.append("enabled")
        if instance.state not in {"DISABLED", "READY", "MISSING"}:
            facts.append(f"state={instance.state}")
        count = len(instance.process_ids)
        if count == 0 and (
            instance.root_pid is not None or instance.state == "RUNNING"
        ):
            count = 1
        if count:
            facts.append(f"instances={count}")
        if facts:
            violations.append(f"{instance.service}:{'+'.join(facts)}")
    if violations:
        raise ProvisioningError(
            "LIVE_TASK_REPROJECTION_REQUIRES_FULL_STOP "
            f"roles={','.join(violations)}"
        )


def _register_task(
    *,
    service: Any,
    task_name: str,
    username: str,
    password: str,
    module: str,
    module_command: str | None,
    trigger_kind: str,
    enabled: bool,
    allow_demand_start: bool | None = None,
    start_when_available: bool = True,
    repository_root: Path,
    config_path: Path,
) -> Any:
    definition = service.NewTask(0)
    definition.RegistrationInfo.Author = "Halpha Project Owner"
    definition.RegistrationInfo.Description = (
        f"Halpha {task_name} process; managed by repository provisioning"
    )
    settings = definition.Settings
    settings.AllowDemandStart = (
        enabled if allow_demand_start is None else allow_demand_start
    )
    settings.DisallowStartIfOnBatteries = False
    settings.Enabled = enabled
    settings.ExecutionTimeLimit = "PT0S"
    settings.Hidden = True
    settings.MultipleInstances = TASK_INSTANCES_IGNORE_NEW
    settings.StartWhenAvailable = start_when_available
    settings.StopIfGoingOnBatteries = False

    account = f"{socket.gethostname()}\\{username}"
    definition.Principal.DisplayName = f"Halpha {task_name} identity"
    definition.Principal.UserId = account
    definition.Principal.LogonType = TASK_LOGON_PASSWORD
    definition.Principal.RunLevel = TASK_RUNLEVEL_LUA

    if trigger_kind == "boot":
        trigger = definition.Triggers.Create(TASK_TRIGGER_BOOT)
        trigger.Enabled = True
        trigger.Id = "SystemStartup"
        watchdog = definition.Triggers.Create(TASK_TRIGGER_DAILY)
        watchdog.Enabled = True
        watchdog.Id = "MinuteWatchdog"
        watchdog.StartBoundary = WATCHDOG_START_BOUNDARY
        watchdog.DaysInterval = 1
        watchdog.Repetition.Interval = WATCHDOG_INTERVAL
        watchdog.Repetition.Duration = WATCHDOG_DURATION
        watchdog.Repetition.StopAtDurationEnd = False
    elif trigger_kind == "daily":
        trigger = definition.Triggers.Create(TASK_TRIGGER_DAILY)
        trigger.Enabled = True
        trigger.Id = "DailyBackup"
        trigger.StartBoundary = "2000-01-01T02:30:00"
        trigger.DaysInterval = 1
    else:
        raise ProvisioningError(f"TASK_TRIGGER_KIND_INVALID task={task_name}")

    action = definition.Actions.Create(TASK_ACTION_EXEC)
    action.Path = str((repository_root / ".venv" / "Scripts" / "python.exe").resolve())
    action.Arguments = f'-m {module} --config "{config_path.resolve()}"'
    if module_command:
        action.Arguments += f" {module_command}"
    action.WorkingDirectory = str(repository_root.resolve())

    folder = _task_folder(service)
    try:
        return folder.RegisterTaskDefinition(
            task_name,
            definition,
            TASK_CREATE_OR_UPDATE,
            account,
            password,
            TASK_LOGON_PASSWORD,
            "",
        )
    except pywintypes.com_error as exc:
        raise ProvisioningError(
            f"TASK_REGISTRATION_FAILED task={task_name} code={exc.hresult}"
        ) from None


def _export_task_xml(task: Any, destination: Path) -> str:
    xml = str(task.Xml)
    if "<Password>" in xml or TASK_ACCOUNT_VAULT_SERVICE in xml:
        raise ProvisioningError("TASK_XML_SECRET_MATERIAL_DETECTED")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(xml, encoding="utf-8", newline="\n")
    return sha256(xml.encode("utf-8")).hexdigest()


def _disable_stop_registered_tasks(
    tasks: dict[str, Any],
    *,
    timeout_seconds: float = 5.0,
) -> None:
    failures: set[str] = set()
    for role, task in tasks.items():
        try:
            task.Enabled = False
            if bool(task.Enabled):
                failures.add(role)
        except Exception:
            failures.add(role)
    for role, task in tasks.items():
        try:
            instance_count = int(task.GetInstances(0).Count)
            state = int(task.State)
            if instance_count or state in {TASK_STATE_QUEUED, TASK_STATE_RUNNING}:
                task.Stop(0)
        except Exception:
            failures.add(role)
    deadline = time.monotonic() + timeout_seconds
    pending = set(tasks)
    while pending and time.monotonic() < deadline:
        for role in tuple(pending):
            task = tasks[role]
            try:
                instance_count = int(task.GetInstances(0).Count)
                state = int(task.State)
            except Exception:
                failures.add(role)
                pending.remove(role)
                continue
            if instance_count == 0 and state not in {
                TASK_STATE_QUEUED,
                TASK_STATE_RUNNING,
            }:
                pending.remove(role)
        if pending:
            time.sleep(0.05)
    failures.update(pending)
    if failures:
        raise ProvisioningError(
            "TASK_STAGING_ROLLBACK_FAILED "
            f"roles={','.join(sorted(failures))}"
        )


def _provision_tasks_under_guard(
    *,
    root: Path,
    config: Path,
    settings: HalphaSettings,
    deployment: WindowsDeployment,
    service: Any,
    maintenance_sid: str,
) -> dict[str, Any]:
    _require_live_task_reprojection_stopped(
        repository_root=root,
        config_path=config,
        settings=settings,
        task_service=service,
    )

    accounts = [
        (
            "app",
            deployment.app_user,
            f"Halpha {deployment.namespace} App scheduled-task identity",
        ),
        (
            "executor",
            deployment.executor_user,
            f"Halpha {deployment.namespace} Executor scheduled-task identity",
        ),
    ]
    if deployment.owns_shared_backup:
        accounts.append(
            ("backup", BACKUP_USER, "Halpha shared Backup scheduled-task identity")
        )
    account_state: dict[str, Any] = {}
    passwords: dict[str, str] = {}
    for role, username, comment in accounts:
        password = _task_account_password(username)
        passwords[role] = password
        _ensure_local_user(username, password, comment)
        account_state[role] = {
            "username": username,
            "sid": _account_sid(username),
            "administrator": False,
        }

    backup_sid = (
        str(account_state["backup"]["sid"])
        if deployment.owns_shared_backup
        else _account_sid(BACKUP_USER)
    )
    _require_configured_identity_sids(
        configured={
            "app": settings.windows.app_task_sid,
            "executor": settings.windows.executor_task_sid,
            "backup": settings.windows.backup_task_sid,
        },
        actual={
            "app": str(account_state["app"]["sid"]),
            "executor": str(account_state["executor"]["sid"]),
            "backup": backup_sid,
        },
    )
    for role, username, _comment in accounts:
        account_state[role]["rights"] = list(_grant_batch_only_rights(username))

    task_output = root / "build" / "runtime" / "tasks"
    task_state: dict[str, Any] = {}
    task_definitions = [
        (
            "app",
            deployment.app_task,
            deployment.app_user,
            "halpha.app",
            None,
            "boot",
            True,
        ),
        (
            "executor",
            deployment.executor_task,
            deployment.executor_user,
            "halpha.executor",
            None,
            "boot",
            (
                settings.release.profile != "BINANCE_LIVE_READ_ONLY"
                or settings.executor.continuous_account_observation
            ),
        ),
    ]
    if deployment.owns_shared_backup:
        task_definitions.append(
            (
                "backup",
                SHARED_BACKUP_TASK,
                BACKUP_USER,
                "halpha.backup",
                "backup",
                "daily",
                True,
            )
        )
    live_projection = settings.release.profile in {
        "BINANCE_LIVE_READ_ONLY",
        "BINANCE_LIVE_WRITE",
    }
    registered_tasks: dict[str, Any] = {}
    artifact_paths: dict[str, Path] = {}
    desired_enabled: dict[str, bool] = {}
    try:
        for (
            role,
            task_name,
            username,
            module,
            module_command,
            trigger_kind,
            enabled,
        ) in task_definitions:
            desired_enabled[role] = enabled
            task = _register_task(
                service=service,
                task_name=task_name,
                username=username,
                password=passwords[role],
                module=module,
                module_command=module_command,
                trigger_kind=trigger_kind,
                enabled=False if live_projection else enabled,
                allow_demand_start=(
                    enabled
                    or (
                        role == "executor"
                        and settings.release.profile == "BINANCE_LIVE_READ_ONLY"
                    )
                ),
                start_when_available=not live_projection,
                repository_root=root,
                config_path=config,
            )
            registered_tasks[role] = task
            artifact_name = (
                f"{role}.{deployment.namespace}.xml"
                if role != "backup"
                else "backup.xml"
            )
            artifact_path = task_output / artifact_name
            artifact_paths[role] = artifact_path
            if live_projection:
                _export_task_xml(task, artifact_path)

        if live_projection:
            _require_live_task_reprojection_stopped(
                repository_root=root,
                config_path=config,
                settings=settings,
                task_service=service,
            )

        for (
            role,
            task_name,
            _username,
            _module,
            _module_command,
            _trigger_kind,
            _enabled,
        ) in task_definitions:
            task = registered_tasks[role]
            if live_projection:
                task.Enabled = desired_enabled[role]
                if bool(task.Enabled) != desired_enabled[role]:
                    raise ProvisioningError(
                        f"TASK_FINAL_ENABLE_MISMATCH roles={role}"
                    )
            xml_digest = _export_task_xml(task, artifact_paths[role])
            task_state[role] = {
                "path": f"{TASK_FOLDER}\\{task_name}",
                "state": int(task.State),
                "enabled": bool(task.Enabled),
                "runtime_mode": (
                    "CONTINUOUS_PRIVATE_ACCOUNT_OBSERVATION"
                    if role == "executor"
                    and settings.release.profile == "BINANCE_LIVE_READ_ONLY"
                    and settings.executor.continuous_account_observation
                    else "EXPLICIT_OBSERVATION_SESSION_ONLY"
                    if role == "executor"
                    and settings.release.profile == "BINANCE_LIVE_READ_ONLY"
                    else "PERSISTENT_TASK"
                ),
                "xml_sha256": xml_digest,
            }
        if live_projection:
            for role, enabled in desired_enabled.items():
                if enabled:
                    registered_tasks[role].Run("")
                    task_state[role]["state"] = int(registered_tasks[role].State)
    except Exception:
        if live_projection:
            _disable_stop_registered_tasks(registered_tasks)
        raise
    finally:
        passwords.clear()

    return {
        "status": "WINDOWS_TASKS_PROVISIONED",
        "environment_namespace": deployment.namespace,
        "shared_backup_owner": "BINANCE_DEMO",
        "maintenance_sid": maintenance_sid,
        "accounts": account_state,
        "tasks": task_state,
        "task_account_password_transport": "IN_PROCESS_COM_ONLY",
        "task_account_password_storage": "MAINTENANCE_WINVAULT_ONLY",
    }


def provision(repository_root: Path, config_path: Path) -> dict[str, Any]:
    _require_elevated_administrator()
    root = repository_root.resolve()
    config = config_path.resolve()
    if not config.is_file():
        raise ProvisioningError("RUNTIME_CONFIG_MISSING")
    settings = load_settings(config)
    deployment = windows_deployment(settings.release.venue_account_type.value)
    python = root / ".venv" / "Scripts" / "python.exe"
    if not python.is_file():
        raise ProvisioningError("REPOSITORY_VENV_PYTHON_MISSING")

    service = win32com.client.Dispatch("Schedule.Service")
    service.Connect()
    maintenance_sid = _current_user_sid()
    _require_configured_identity_sids(
        configured={"maintenance": settings.windows.maintenance_sid},
        actual={"maintenance": maintenance_sid},
    )
    live_projection = settings.release.profile in {
        "BINANCE_LIVE_READ_ONLY",
        "BINANCE_LIVE_WRITE",
    }
    try:
        guard = (
            acquire_executor_maintenance_mutex(
                name=settings.executor.mutex_name,
                executor_task_sid=settings.windows.executor_task_sid,
                maintenance_sid=settings.windows.maintenance_sid,
                conflict_code="LIVE_TASK_REPROJECTION_EXECUTOR_MUST_BE_STOPPED",
            )
            if live_projection
            else nullcontext()
        )
        with guard:
            return _provision_tasks_under_guard(
                root=root,
                config=config,
                settings=settings,
                deployment=deployment,
                service=service,
                maintenance_sid=maintenance_sid,
            )
    except WindowsRuntimeError as exc:
        raise ProvisioningError(
            f"LIVE_TASK_REPROJECTION_MUTEX_FAILED reason={exc}"
        ) from None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="provision-windows-tasks")
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        require_repository_runtime(args.repository_root.resolve())
        report = provision(args.repository_root, args.config)
    except Exception as exc:
        if isinstance(exc, ProvisioningError):
            reason = str(exc)
        else:
            reason = f"WINDOWS_TASK_PROVISIONING_FAILED type={type(exc).__name__}"
        print(json.dumps({"status": "REJECTED", "reason": reason}, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
