"""Qualify the dedicated one-shot PostgreSQL backup boundary on Windows."""

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

from halpha.backup import BACKUP_MANIFEST_KEYS, POSTGRESQL_VERSION, backup_all
from halpha.configuration import backup_settings, load_settings
from halpha.runtime_identity import repository_root, require_repository_runtime
from halpha.windows_filesystem import (
    DirectoryAclSpec,
    WindowsFilesystemError,
    assert_directory_security,
    backup_acl_specs,
)
from halpha.windows_runtime import current_process_sid
from halpha.winvault import backup_secret_resolver, require_win_vault_backend
from tools.provisioning.provision_windows_tasks import (
    BACKUP_USER,
    TASK_ACCOUNT_VAULT_SERVICE,
    TASK_ACTION_EXEC,
    TASK_CREATE_OR_UPDATE,
    TASK_FOLDER,
    TASK_INSTANCES_IGNORE_NEW,
    TASK_LOGON_PASSWORD,
    TASK_RUNLEVEL_LUA,
)
from tools.qualification.source_binding import (
    SourceBindingError,
    capture_source_sha256,
)


TASK_STATE_READY = 3
TASK_STATE_RUNNING = 4
SOURCE_PATTERNS = (
    "requirements/runtime.txt",
    "src/halpha/backup.py",
    "src/halpha/configuration.py",
    "src/halpha/database/**/*.py",
    "src/halpha/operational_logging.py",
    "src/halpha/runtime_identity.py",
    "src/halpha/windows_filesystem.py",
    "src/halpha/windows_runtime.py",
    "src/halpha/winvault.py",
    "tools/provisioning/provision_windows_tasks.py",
    "tools/qualification/source_binding.py",
    "tools/qualification/verify_backup_boundary.py",
)


class BackupQualificationError(RuntimeError):
    """Sanitized host-backup qualification failure."""


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_patterns(root: Path, config_path: Path) -> tuple[str, ...]:
    config = config_path.resolve()
    if not config.is_file() or not config.is_relative_to(root):
        raise BackupQualificationError(
            "BACKUP_QUALIFICATION_CONFIG_OUTSIDE_REPOSITORY"
        )
    return (*SOURCE_PATTERNS, config.relative_to(root).as_posix())


def _directory_boundary(spec: DirectoryAclSpec) -> dict[str, Any]:
    try:
        assert_directory_security(spec)
    except WindowsFilesystemError as exc:
        raise BackupQualificationError(str(exc)) from None
    return {
        "owner_sid": spec.owner_sid,
        "dacl": "EXACT_PROTECTED",
        "grant_count": len(spec.grants),
        "grants": [
            {"sid": sid, "mask": mask}
            for sid, mask in spec.grants
        ],
        "boundary": "QUALIFIED",
    }


def _secret_scan(root: Path, values: Sequence[str]) -> bool:
    needles = [value.encode("utf-8") for value in values if value]
    if not needles:
        raise BackupQualificationError("BACKUP_SECRET_SCAN_INPUT_EMPTY")
    candidates = [
        list(
            (root / "logs" / "maintenance" / "backup").glob(
                "backup.jsonl*"
            )
        ),
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
    if current_process_sid() != settings.windows.backup_task_sid:
        raise BackupQualificationError("BACKUP_QUALIFICATION_TASK_IDENTITY_REQUIRED")
    backend = keyring.get_keyring()
    require_win_vault_backend(backend)
    resolver = backup_secret_resolver(backend, backup_settings(settings))
    secret_values = [
        resolver.resolve(target.backup_credential_reference).get_secret_value()
        for _name, target in settings.maintenance.named_targets()
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
        backup_boundaries = {
            spec.label: spec
            for spec in backup_acl_specs(root, settings)
        }
        for environment, result in operation["results"].items():
            directory = backup_root / environment
            archive = directory / str(result["archive"])
            manifest_path = archive.with_suffix(".json")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            boundary = backup_boundaries[f"{environment}_backups"]
            environments[environment] = {
                "database": result["database"],
                "archive_name": archive.name,
                "archive_size": archive.stat().st_size,
                "archive_sha256": _sha256_file(archive),
                "manifest_digest_matches": (
                    manifest.get("archive_sha256") == _sha256_file(archive)
                    and result.get("archive_sha256") == manifest.get("archive_sha256")
                ),
                "manifest_contract_exact": (
                    set(manifest) == BACKUP_MANIFEST_KEYS
                    and manifest.get("schema_version") == 2
                    and manifest.get("database") == result["database"]
                    and manifest.get("environment_kind")
                    == ("DEMO" if environment == "demo" else "LIVE")
                    and manifest.get("venue_account_type")
                    == dict(settings.maintenance.named_targets())[environment]
                    .venue_account_type.value
                    and manifest.get("archive") == archive.name
                    and manifest.get("archive_size") == archive.stat().st_size
                ),
                "format": manifest.get("format"),
                "tool_version": manifest.get("tool_version"),
                "credential_transport": manifest.get("credential_transport"),
                "directory_boundary": _directory_boundary(boundary),
            }
        evidence: dict[str, Any] = {
            "schema_version": 1,
            "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "runtime": {
                "python_version": runtime.python_version,
                "executable": runtime.executable,
                "process_sid": current_process_sid(),
            },
            "task_identity": "BACKUP",
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
        and item["manifest_contract_exact"]
        and item["format"] == "POSTGRESQL_CUSTOM"
        and item["tool_version"] == POSTGRESQL_VERSION
        and item["credential_transport"] == "DELETE_ON_CLOSE_PGPASSFILE"
        and item["directory_boundary"]["boundary"] == "QUALIFIED"
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
    password = backend.get_password(TASK_ACCOUNT_VAULT_SERVICE, BACKUP_USER)
    if not password:
        raise BackupQualificationError("BACKUP_TASK_ACCOUNT_PASSWORD_REFERENCE_MISSING")
    return password


def _stop_task_before_delete(task: Any) -> None:
    if int(task.State) != TASK_STATE_RUNNING:
        return
    task.Stop(0)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if int(task.State) != TASK_STATE_RUNNING:
            return
        time.sleep(0.1)
    raise BackupQualificationError(
        "BACKUP_QUALIFICATION_TASK_STOP_TIMEOUT"
    )


def _run_child_task(root: Path, config_path: Path) -> dict[str, Any]:
    settings = load_settings(config_path)
    child_output = (
        root
        / settings.maintenance.temporary_root
        / f"backup-qualification-{os.getpid()}.json"
    ).resolve()
    if child_output.exists():
        child_output.unlink()
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
    account = f"{socket.gethostname()}\\{BACKUP_USER}"
    definition.Principal.DisplayName = "Halpha ephemeral backup qualification"
    definition.Principal.UserId = account
    definition.Principal.LogonType = TASK_LOGON_PASSWORD
    definition.Principal.RunLevel = TASK_RUNLEVEL_LUA
    action = definition.Actions.Create(TASK_ACTION_EXEC)
    action.Path = str((root / ".venv" / "Scripts" / "python.exe").resolve())
    action.Arguments = (
        "-m tools.qualification.verify_backup_boundary "
        f'--config "{config_path.resolve()}" '
        f'--output "{child_output}" --child'
    )
    action.WorkingDirectory = str(root)
    password = _task_account_password()
    task = None
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
        task.Run("")
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            state = int(task.State)
            if state != TASK_STATE_RUNNING and child_output.exists():
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
        evidence = json.loads(child_output.read_text(encoding="utf-8"))
        if not isinstance(evidence, dict):
            raise BackupQualificationError("BACKUP_QUALIFICATION_REPORT_INVALID")
        return evidence
    finally:
        password = ""
        cleanup_error: BackupQualificationError | None = None
        if task is not None:
            try:
                _stop_task_before_delete(task)
            except Exception as exc:
                cleanup_error = BackupQualificationError(
                    "BACKUP_QUALIFICATION_TASK_CLEANUP_FAILED "
                    f"type={type(exc).__name__}"
                )
            try:
                folder.DeleteTask(task_name, 0)
            except pywintypes.com_error as exc:
                cleanup_error = BackupQualificationError(
                    "BACKUP_QUALIFICATION_TASK_CLEANUP_FAILED "
                    f"code={exc.hresult}"
                )
        child_output.unlink(missing_ok=True)
        if cleanup_error is not None:
            raise cleanup_error


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--child", action="store_true")
    args = parser.parse_args(argv)
    root = repository_root()
    require_repository_runtime(root)
    config_path = args.config.resolve()
    settings = load_settings(config_path)
    output = args.output.resolve()
    allowed_root = (
        (root / settings.maintenance.temporary_root).resolve()
        if args.child
        else (root / "build" / "qualification").resolve()
    )
    if (
        output.suffix.lower() != ".json"
        or not output.is_relative_to(allowed_root)
        or (
            args.child
            and not output.name.startswith("backup-qualification-")
        )
    ):
        raise BackupQualificationError(
            "BACKUP_QUALIFICATION_OUTPUT_OUTSIDE_ALLOWED_ROOT"
        )
    patterns = _source_patterns(root, config_path)
    source_sha256_at_start = capture_source_sha256(root, patterns)
    try:
        if args.child:
            evidence = _qualify_child(root, args.config)
        else:
            evidence = _run_child_task(root, args.config)
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
    evidence["source_sha256"] = source_sha256_at_start
    try:
        source_stable = (
            capture_source_sha256(root, patterns)
            == source_sha256_at_start
        )
    except SourceBindingError as exc:
        source_stable = False
        evidence.setdefault("errors", []).append(
            f"BACKUP_SOURCE_BINDING_FAILED:{exc}"
        )
    checks = evidence.setdefault("checks", {})
    checks["source_stable_during_qualification"] = source_stable
    if not source_stable:
        evidence["status"] = "REJECTED"
    evidence.pop("evidence_digest", None)
    canonical = json.dumps(
        evidence,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    evidence["evidence_digest"] = sha256(
        canonical.encode("utf-8")
    ).hexdigest()
    _write_report(output, evidence)
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if evidence.get("status") == "QUALIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
