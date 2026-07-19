"""Qualify an App-identity pg_restore into a newly created empty database."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import socket
import sys
import time
from typing import Any, Sequence

import keyring
import psycopg
from psycopg import sql
import pywintypes
import win32com.client


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from halpha.backup import backup_environment, restore_archive
from halpha.configuration import load_settings
from halpha.database.record_families import PRODUCT_RECORD_FAMILIES
from halpha.runtime_identity import repository_root, require_repository_runtime
from halpha.windows_runtime import current_process_sid
from halpha.winvault import require_win_vault_backend
from tools.provisioning.provision_halpha_databases import SUPERUSER_REFERENCE
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
from tools.qualification.source_binding import (
    SourceBindingError,
    capture_source_sha256,
)


TASK_STATE_READY = 3
TASK_STATE_RUNNING = 4
DEFAULT_OUTPUT = Path("build/qualification/empty-database-restore.json")
SOURCE_PATTERNS = (
    "config/halpha.toml",
    "migrations/versions/*.py",
    "requirements/runtime.txt",
    "src/halpha/backup.py",
    "src/halpha/configuration.py",
    "src/halpha/database/**/*.py",
    "src/halpha/process_contract.py",
    "src/halpha/runtime_identity.py",
    "src/halpha/windows_runtime.py",
    "src/halpha/winvault.py",
    "tools/provisioning/provision_halpha_databases.py",
    "tools/provisioning/provision_windows_tasks.py",
    "tools/qualification/source_binding.py",
    "src/halpha/source_identity.py",
    "tools/qualification/verify_restore_boundary.py",
)


class RestoreQualificationError(RuntimeError):
    """Sanitized empty-restore qualification failure."""


def _canonical_digest(value: dict[str, Any]) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def _child(
    root: Path,
    config_path: Path,
    target_database: str,
) -> dict[str, Any]:
    require_repository_runtime(root)
    settings = load_settings(config_path)
    if current_process_sid() != settings.windows.app_task_sid:
        raise RestoreQualificationError("RESTORE_QUALIFICATION_APP_IDENTITY_REQUIRED")
    backup = backup_environment(root, settings, environment="demo")
    archive = (
        root
        / settings.maintenance.backup_root
        / "demo"
        / str(backup["archive"])
    ).resolve()
    result = restore_archive(
        root,
        settings,
        environment="demo",
        archive=archive,
        target_database=target_database,
    )
    report = {
        "schema_version": 1,
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "task_identity": "APP",
        "source_archive": archive.name,
        "backup": backup,
        "restore": result,
        "status": (
            "QUALIFIED"
            if backup.get("status") == "BACKUP_CREATED"
            and result.get("status") == "RESTORE_COMPLETED"
            else "REJECTED"
        ),
    }
    report["evidence_digest"] = _canonical_digest(report)
    return report


def _vault_value(service: str, account: str, *, missing_code: str) -> str:
    backend = keyring.get_keyring()
    require_win_vault_backend(backend)
    value = backend.get_password(service, account)
    if not value:
        raise RestoreQualificationError(missing_code)
    return value


def _run_child_task(
    root: Path,
    config_path: Path,
    target_database: str,
    output: Path,
) -> dict[str, Any]:
    service = win32com.client.Dispatch("Schedule.Service")
    service.Connect()
    folder = service.GetFolder(TASK_FOLDER)
    task_name = f"HalphaEmptyRestoreCheck-{os.getpid()}"
    definition = service.NewTask(0)
    definition.RegistrationInfo.Author = "Halpha Project Owner"
    definition.RegistrationInfo.Description = "Ephemeral Halpha empty-restore check"
    definition.Settings.AllowDemandStart = True
    definition.Settings.DisallowStartIfOnBatteries = False
    definition.Settings.Enabled = True
    definition.Settings.ExecutionTimeLimit = "PT10M"
    definition.Settings.Hidden = True
    definition.Settings.MultipleInstances = TASK_INSTANCES_IGNORE_NEW
    definition.Settings.RestartCount = 0
    definition.Settings.StartWhenAvailable = False
    definition.Settings.StopIfGoingOnBatteries = False
    account = f"{socket.gethostname()}\\{APP_USER}"
    definition.Principal.DisplayName = "Halpha ephemeral restore qualification"
    definition.Principal.UserId = account
    definition.Principal.LogonType = TASK_LOGON_PASSWORD
    definition.Principal.RunLevel = TASK_RUNLEVEL_LUA
    action = definition.Actions.Create(TASK_ACTION_EXEC)
    action.Path = str((root / ".venv" / "Scripts" / "python.exe").resolve())
    action.Arguments = (
        "-m tools.qualification.verify_restore_boundary "
        f'--config "{config_path.resolve()}" '
        f'--target-database "{target_database}" '
        f'--output "{output.resolve()}" --child'
    )
    action.WorkingDirectory = str(root)
    password = _vault_value(
        TASK_ACCOUNT_VAULT_SERVICE,
        APP_USER,
        missing_code="APP_TASK_ACCOUNT_PASSWORD_REFERENCE_MISSING",
    )
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
                raise RestoreQualificationError(
                    f"RESTORE_QUALIFICATION_TASK_FAILED code={int(task.LastTaskResult)}"
                )
            time.sleep(0.25)
        else:
            raise RestoreQualificationError("RESTORE_QUALIFICATION_TASK_TIMEOUT")
        if int(task.LastTaskResult) != 0:
            raise RestoreQualificationError(
                f"RESTORE_QUALIFICATION_TASK_FAILED code={int(task.LastTaskResult)}"
            )
        report = json.loads(output.read_text(encoding="utf-8"))
        if not isinstance(report, dict):
            raise RestoreQualificationError("RESTORE_QUALIFICATION_REPORT_INVALID")
        return report
    finally:
        password = ""
        try:
            folder.DeleteTask(task_name, 0)
        except pywintypes.com_error as exc:
            raise RestoreQualificationError(
                f"RESTORE_QUALIFICATION_TASK_CLEANUP_FAILED code={exc.hresult}"
            ) from None


def _parent(root: Path, config_path: Path, output: Path) -> dict[str, Any]:
    require_repository_runtime(root)
    settings = load_settings(config_path)
    if current_process_sid() != settings.windows.maintenance_sid:
        raise RestoreQualificationError("RESTORE_QUALIFICATION_MAINTENANCE_IDENTITY_REQUIRED")
    target_database = f"halpha_restore_check_{os.getpid()}"
    superuser = _vault_value(
        *SUPERUSER_REFERENCE,
        missing_code="POSTGRESQL_SUPERUSER_REFERENCE_MISSING",
    )
    child: dict[str, Any] | None = None
    try:
        with psycopg.connect(
            host="127.0.0.1",
            port=5432,
            dbname="postgres",
            user="postgres",
            password=superuser,
            autocommit=True,
        ) as admin:
            admin.execute(
                sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0 ENCODING 'UTF8'").format(
                    sql.Identifier(target_database),
                    sql.Identifier(settings.maintenance.demo.migration_role_name),
                )
            )
            admin.execute(
                sql.SQL("REVOKE CONNECT ON DATABASE {} FROM PUBLIC").format(
                    sql.Identifier(target_database)
                )
            )
        child = _run_child_task(
            root,
            config_path,
            target_database,
            output,
        )
        with psycopg.connect(
            host="127.0.0.1",
            port=5432,
            dbname=target_database,
            user="postgres",
            password=superuser,
        ) as restored:
            restored_tables = {
                str(row[0])
                for row in restored.execute(
                    "SELECT tablename FROM pg_tables WHERE schemaname = 'halpha'"
                ).fetchall()
            }
            restored_counts = {
                table: int(
                    restored.execute(
                        sql.SQL("SELECT count(*) FROM halpha.{}").format(
                            sql.Identifier(table)
                        )
                    ).fetchone()[0]
                )
                for table in PRODUCT_RECORD_FAMILIES
            }
        checks = {
            "restore_ran_as_app_identity": child.get("task_identity") == "APP",
            "custom_archive_digest_verified": (
                child.get("restore", {}).get("archive_sha256")
                == child.get("backup", {}).get("archive_sha256")
            ),
            "empty_target_received_exact_product_schema": restored_tables
            == set(PRODUCT_RECORD_FAMILIES),
            "all_product_records_queryable": set(restored_counts)
            == set(PRODUCT_RECORD_FAMILIES),
            "product_evidence_records_retained": all(
                restored_counts[table] > 0
                for table in (
                    "plan_activation",
                    "execution_action",
                    "venue_fact",
                    "review",
                )
            ),
            "target_database_is_ephemeral": target_database.startswith("halpha_restore_check_"),
        }
        report: dict[str, Any] = {
            "schema_version": 1,
            "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "operation": "EMPTY_DATABASE_RESTORE",
            "source_archive": child.get("source_archive"),
            "target_database": target_database,
            "checks": checks,
            "restored_table_count": len(restored_tables),
            "restored_record_counts": restored_counts,
            "status": "QUALIFIED" if all(checks.values()) else "REJECTED",
        }
        report["evidence_digest"] = _canonical_digest(report)
        _write_report(output, report)
        return report
    finally:
        try:
            with psycopg.connect(
                host="127.0.0.1",
                port=5432,
                dbname="postgres",
                user="postgres",
                password=superuser,
                autocommit=True,
            ) as admin:
                admin.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (target_database,),
                )
                admin.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {}").format(
                        sql.Identifier(target_database)
                    )
                )
        finally:
            superuser = ""


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--target-database")
    parser.add_argument("--child", action="store_true")
    args = parser.parse_args(argv)
    root = repository_root()
    output = args.output.resolve()
    if not output.is_relative_to(root):
        raise RestoreQualificationError("RESTORE_QUALIFICATION_OUTPUT_OUTSIDE_REPOSITORY")
    source_sha256_at_start = capture_source_sha256(root, SOURCE_PATTERNS)
    try:
        if args.child:
            if args.target_database is None:
                raise RestoreQualificationError("RESTORE_CHILD_ARGUMENT_MISSING")
            report = _child(
                root,
                args.config.resolve(),
                args.target_database,
            )
            _write_report(output, report)
        else:
            report = _parent(root, args.config.resolve(), output)
    except Exception as exc:
        reason = (
            str(exc)
            if isinstance(exc, RestoreQualificationError)
            else f"RESTORE_QUALIFICATION_FAILED type={type(exc).__name__}"
        )
        report = {
            "schema_version": 1,
            "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "operation": "EMPTY_DATABASE_RESTORE",
            "status": "REJECTED",
            "reason": reason,
        }
    report["source_sha256"] = source_sha256_at_start
    try:
        source_stable = (
            capture_source_sha256(root, SOURCE_PATTERNS) == source_sha256_at_start
        )
    except SourceBindingError as exc:
        source_stable = False
        report.setdefault("errors", []).append(
            f"RESTORE_SOURCE_BINDING_FAILED:{exc}"
        )
    checks = report.setdefault("checks", {})
    checks["source_stable_during_qualification"] = source_stable
    if not source_stable or (
        report.get("status") == "QUALIFIED" and not all(checks.values())
    ):
        report["status"] = "REJECTED"
    report.pop("evidence_digest", None)
    report["evidence_digest"] = _canonical_digest(report)
    _write_report(output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("status") == "QUALIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
