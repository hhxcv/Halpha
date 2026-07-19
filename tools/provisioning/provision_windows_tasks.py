"""Provision dedicated non-admin Windows identities and the two product tasks.

Task-account passwords are generated in process memory, stored only in the
maintenance identity's Windows Credential Manager, and passed to the Task
Scheduler COM API without command-line or file transport.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import secrets
import socket
import string
from typing import Any, Sequence

import keyring
import pywintypes
import win32api
import win32com.client
import win32con
import win32net
import win32netcon
import win32security

from halpha.runtime_identity import require_repository_runtime
from halpha.winvault import require_win_vault_backend


TASK_ACCOUNT_VAULT_SERVICE = "Halpha/Windows/TaskAccounts"
APP_USER = "HalphaApp"
EXECUTOR_USER = "HalphaExecutor"
TASK_FOLDER = r"\Halpha"
TASK_CREATE_OR_UPDATE = 6
TASK_LOGON_PASSWORD = 1
TASK_RUNLEVEL_LUA = 0
TASK_TRIGGER_BOOT = 8
TASK_TRIGGER_DAILY = 2
TASK_ACTION_EXEC = 0
TASK_INSTANCES_IGNORE_NEW = 2
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


def _register_task(
    *,
    service: Any,
    task_name: str,
    username: str,
    password: str,
    module: str,
    module_command: str | None,
    trigger_kind: str,
    repository_root: Path,
    config_path: Path,
) -> Any:
    definition = service.NewTask(0)
    definition.RegistrationInfo.Author = "Halpha Project Owner"
    definition.RegistrationInfo.Description = (
        f"Halpha {task_name} process; managed by repository provisioning"
    )
    settings = definition.Settings
    settings.AllowDemandStart = True
    settings.DisallowStartIfOnBatteries = False
    settings.Enabled = True
    settings.ExecutionTimeLimit = "PT0S"
    settings.Hidden = True
    settings.MultipleInstances = TASK_INSTANCES_IGNORE_NEW
    settings.StartWhenAvailable = True
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


def provision(repository_root: Path, config_path: Path) -> dict[str, Any]:
    _require_elevated_administrator()
    root = repository_root.resolve()
    config = config_path.resolve()
    if not config.is_file():
        raise ProvisioningError("RUNTIME_CONFIG_MISSING")
    python = root / ".venv" / "Scripts" / "python.exe"
    if not python.is_file():
        raise ProvisioningError("REPOSITORY_VENV_PYTHON_MISSING")

    accounts = (
        ("app", APP_USER, "Halpha App scheduled-task identity"),
        ("executor", EXECUTOR_USER, "Halpha Executor scheduled-task identity"),
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
            "rights": list(_grant_batch_only_rights(username)),
            "administrator": False,
        }

    service = win32com.client.Dispatch("Schedule.Service")
    service.Connect()
    task_output = root / "build" / "runtime" / "tasks"
    task_state: dict[str, Any] = {}
    for role, task_name, username, module, module_command, trigger_kind in (
        ("app", "App", APP_USER, "halpha.app", None, "boot"),
        ("executor", "Executor", EXECUTOR_USER, "halpha.executor", None, "boot"),
        ("backup", "Backup", APP_USER, "halpha.backup", "backup", "daily"),
    ):
        task = _register_task(
            service=service,
            task_name=task_name,
            username=username,
            password=passwords["app" if role == "backup" else role],
            module=module,
            module_command=module_command,
            trigger_kind=trigger_kind,
            repository_root=root,
            config_path=config,
        )
        xml_digest = _export_task_xml(task, task_output / f"{role}.xml")
        task_state[role] = {
            "path": f"{TASK_FOLDER}\\{task_name}",
            "state": int(task.State),
            "enabled": bool(task.Enabled),
            "xml_sha256": xml_digest,
        }

    passwords.clear()
    return {
        "status": "WINDOWS_TASKS_PROVISIONED",
        "maintenance_sid": _current_user_sid(),
        "accounts": account_state,
        "tasks": task_state,
        "task_account_password_transport": "IN_PROCESS_COM_ONLY",
        "task_account_password_storage": "MAINTENANCE_WINVAULT_ONLY",
    }


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
