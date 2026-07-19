"""Qualify the App-owned one-shot PostgreSQL backup boundary on Windows."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import socket
import time
from typing import Any, Sequence

import keyring
import pywintypes
import win32com.client
import win32con
import win32file
import win32security

from halpha.backup import POSTGRESQL_VERSION, backup_all
from halpha.configuration import load_settings, maintenance_settings
from halpha.runtime_identity import repository_root, require_repository_runtime
from halpha.windows_runtime import current_process_sid
from halpha.winvault import maintenance_secret_resolver, require_win_vault_backend
from tools.provisioning.provision_windows_tasks import (
    APP_USER,
    TASK_ACCOUNT_VAULT_SERVICE,
    TASK_ACTION_EXEC,
    TASK_CREATE_OR_UPDATE,
    TASK_FOLDER,
    TASK_INSTANCES_IGNORE_NEW,
    TASK_LOGON_PASSWORD,
    TASK_RUNLEVEL_LUA,
)


TASK_STATE_READY = 3
TASK_STATE_RUNNING = 4


class BackupQualificationError(RuntimeError):
    """Sanitized host-backup qualification failure."""


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _directory_boundary(path: Path, expected_sid: str) -> dict[str, Any]:
    descriptor = win32security.GetNamedSecurityInfo(
        str(path),
        win32security.SE_FILE_OBJECT,
        win32security.OWNER_SECURITY_INFORMATION
        | win32security.DACL_SECURITY_INFORMATION,
    )
    owner = win32security.ConvertSidToStringSid(
        descriptor.GetSecurityDescriptorOwner()
    )
    control, _ = descriptor.GetSecurityDescriptorControl()
    dacl = descriptor.GetSecurityDescriptorDacl()
    aces: list[dict[str, Any]] = []
    if dacl is not None:
        for index in range(dacl.GetAceCount()):
            header, mask, sid = dacl.GetAce(index)
            aces.append(
                {
                    "type": int(header[0]),
                    "flags": int(header[1]),
                    "mask": int(mask),
                    "sid": win32security.ConvertSidToStringSid(sid),
                }
            )
    return {
        "owner_sid": owner,
        "owner_matches": owner == expected_sid,
        "dacl_protected": bool(control & win32security.SE_DACL_PROTECTED),
        "ace_count": len(aces),
        "only_app_identity_granted": (
            bool(aces)
            and all(
                ace["type"] == win32security.ACCESS_ALLOWED_ACE_TYPE
                and ace["sid"] == expected_sid
                for ace in aces
            )
            and any(
                ace["mask"] in (win32file.FILE_ALL_ACCESS, win32con.GENERIC_ALL)
                and not (ace["flags"] & win32con.INHERIT_ONLY_ACE)
                for ace in aces
            )
        ),
    }


def _secret_scan(root: Path, values: Sequence[str]) -> bool:
    needles = [value.encode("utf-8") for value in values if value]
    if not needles:
        raise BackupQualificationError("BACKUP_SECRET_SCAN_INPUT_EMPTY")
    candidates = [
        list((root / "logs").glob("backup.jsonl*")),
        list((root / "backups" / "postgresql").rglob("*.json")),
    ]
    for paths in candidates:
        for path in paths:
            if not path.is_file() or path.suffix == ".dump":
                continue
            content = path.read_bytes()
            if any(needle in content for needle in needles):
                return False
    return True


def _qualify_child(root: Path, config_path: Path) -> dict[str, Any]:
    runtime = require_repository_runtime(root)
    settings = load_settings(config_path)
    if current_process_sid() != settings.windows.app_task_sid:
        raise BackupQualificationError("BACKUP_QUALIFICATION_APP_IDENTITY_REQUIRED")
    backend = keyring.get_keyring()
    require_win_vault_backend(backend)
    resolver = maintenance_secret_resolver(backend, maintenance_settings(settings))
    secret_values = [
        resolver.resolve(target.backup_credential_reference).get_secret_value()
        for target in (settings.maintenance.demo, settings.maintenance.live)
    ]
    try:
        operation = backup_all(root, settings)
        temporary_root = (root / settings.maintenance.temporary_root).resolve()
        temporary_entries = (
            sorted(path.relative_to(temporary_root).as_posix() for path in temporary_root.rglob("*"))
            if temporary_root.exists()
            else []
        )
        environments: dict[str, Any] = {}
        backup_root = (root / settings.maintenance.backup_root).resolve()
        for environment, result in operation["results"].items():
            directory = backup_root / environment
            archive = directory / str(result["archive"])
            manifest_path = archive.with_suffix(".json")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            environments[environment] = {
                "database": result["database"],
                "archive_name": archive.name,
                "archive_size": archive.stat().st_size,
                "archive_sha256": _sha256_file(archive),
                "manifest_digest_matches": (
                    manifest.get("archive_sha256") == _sha256_file(archive)
                    and result.get("archive_sha256") == manifest.get("archive_sha256")
                ),
                "format": manifest.get("format"),
                "tool_version": manifest.get("tool_version"),
                "credential_transport": manifest.get("credential_transport"),
                "directory_boundary": _directory_boundary(
                    directory,
                    settings.windows.app_task_sid,
                ),
            }
        evidence: dict[str, Any] = {
            "schema_version": 1,
            "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "runtime": {
                "python_version": runtime.python_version,
                "executable": runtime.executable,
                "process_sid": current_process_sid(),
            },
            "task_identity": "APP",
            "operation_status": operation["status"],
            "environments": environments,
            "temporary_entries_after_exit": temporary_entries,
            "secret_value_scan": (
                "CLEAN" if _secret_scan(root, secret_values) else "REJECTED"
            ),
            "retention_count": settings.maintenance.backup_retention_count,
        }
    finally:
        secret_values = []
    environment_ok = all(
        item["archive_size"] > 0
        and item["manifest_digest_matches"]
        and item["format"] == "POSTGRESQL_CUSTOM"
        and item["tool_version"] == POSTGRESQL_VERSION
        and item["credential_transport"] == "DELETE_ON_CLOSE_PGPASSFILE"
        and item["directory_boundary"]["owner_matches"]
        and item["directory_boundary"]["dacl_protected"]
        and item["directory_boundary"]["only_app_identity_granted"]
        for item in evidence["environments"].values()
    )
    evidence["status"] = (
        "QUALIFIED"
        if operation["status"] == "BACKUPS_CREATED"
        and not temporary_entries
        and evidence["secret_value_scan"] == "CLEAN"
        and environment_ok
        else "REJECTED"
    )
    canonical = json.dumps(
        evidence,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    evidence["evidence_digest"] = sha256(canonical.encode("utf-8")).hexdigest()
    return evidence


def _write_report(path: Path, evidence: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _task_account_password() -> str:
    backend = keyring.get_keyring()
    require_win_vault_backend(backend)
    password = backend.get_password(TASK_ACCOUNT_VAULT_SERVICE, APP_USER)
    if not password:
        raise BackupQualificationError("APP_TASK_ACCOUNT_PASSWORD_REFERENCE_MISSING")
    return password


def _run_child_task(root: Path, config_path: Path, output: Path) -> dict[str, Any]:
    service = win32com.client.Dispatch("Schedule.Service")
    service.Connect()
    folder = service.GetFolder(TASK_FOLDER)
    task_name = f"DIRECTBackupQualification-{os.getpid()}"
    definition = service.NewTask(0)
    definition.RegistrationInfo.Author = "Halpha Project Owner"
    definition.RegistrationInfo.Description = "Ephemeral DIRECT backup-boundary qualification"
    settings = definition.Settings
    settings.AllowDemandStart = True
    settings.DisallowStartIfOnBatteries = False
    settings.Enabled = True
    settings.ExecutionTimeLimit = "PT10M"
    settings.Hidden = True
    settings.MultipleInstances = TASK_INSTANCES_IGNORE_NEW
    settings.RestartCount = 0
    settings.StartWhenAvailable = False
    settings.StopIfGoingOnBatteries = False
    account = f"{socket.gethostname()}\\{APP_USER}"
    definition.Principal.DisplayName = "Halpha ephemeral backup qualification"
    definition.Principal.UserId = account
    definition.Principal.LogonType = TASK_LOGON_PASSWORD
    definition.Principal.RunLevel = TASK_RUNLEVEL_LUA
    action = definition.Actions.Create(TASK_ACTION_EXEC)
    action.Path = str((root / ".venv" / "Scripts" / "python.exe").resolve())
    action.Arguments = (
        "-m tools.qualification.verify_backup_boundary "
        f'--config "{config_path.resolve()}" '
        f'--output "{output.resolve()}" --child'
    )
    action.WorkingDirectory = str(root)
    password = _task_account_password()
    try:
        task = folder.RegisterTaskDefinition(
            task_name,
            definition,
            TASK_CREATE_OR_UPDATE,
            account,
            password,
            TASK_LOGON_PASSWORD,
            "",
        )
        password = ""
        before = output.stat().st_mtime_ns if output.exists() else -1
        task.Run("")
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            state = int(task.State)
            updated = output.exists() and output.stat().st_mtime_ns != before
            if state != TASK_STATE_RUNNING and updated:
                break
            if state == TASK_STATE_READY and int(task.LastTaskResult) not in (0, 267009):
                raise BackupQualificationError(
                    f"BACKUP_QUALIFICATION_TASK_FAILED code={int(task.LastTaskResult)}"
                )
            time.sleep(0.25)
        else:
            raise BackupQualificationError("BACKUP_QUALIFICATION_TASK_TIMEOUT")
        if int(task.LastTaskResult) != 0:
            raise BackupQualificationError(
                f"BACKUP_QUALIFICATION_TASK_FAILED code={int(task.LastTaskResult)}"
            )
        evidence = json.loads(output.read_text(encoding="utf-8"))
        if not isinstance(evidence, dict):
            raise BackupQualificationError("BACKUP_QUALIFICATION_REPORT_INVALID")
        return evidence
    finally:
        password = ""
        try:
            folder.DeleteTask(task_name, 0)
        except pywintypes.com_error as exc:
            raise BackupQualificationError(
                f"BACKUP_QUALIFICATION_TASK_CLEANUP_FAILED code={exc.hresult}"
            ) from None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--child", action="store_true")
    args = parser.parse_args(argv)
    root = repository_root()
    require_repository_runtime(root)
    output = args.output.resolve()
    if not output.is_relative_to(root):
        raise BackupQualificationError("BACKUP_QUALIFICATION_OUTPUT_OUTSIDE_REPOSITORY")
    if args.child:
        try:
            evidence = _qualify_child(root, args.config)
        except Exception as exc:
            reason = (
                str(exc)
                if isinstance(exc, BackupQualificationError)
                else f"BACKUP_QUALIFICATION_FAILED type={type(exc).__name__}"
            )
            evidence = {
                "schema_version": 1,
                "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "status": "REJECTED",
                "reason": reason,
            }
        _write_report(output, evidence)
    else:
        evidence = _run_child_task(root, args.config, output)
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if evidence.get("status") == "QUALIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
