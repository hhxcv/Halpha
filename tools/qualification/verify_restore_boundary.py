"""Qualify three context-isolated PostgreSQL backup/restore round trips."""

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
from uuid import uuid4

import keyring
import psycopg
from psycopg import sql
import pywintypes
import win32com.client


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from halpha.backup import backup_environment, restore_archive
from halpha.configuration import backup_settings, load_settings
from halpha.database.record_families import (
    CURRENT_PRODUCT_SCHEMA_REVISION,
    PRODUCT_RECORD_FAMILIES,
)
from halpha.database.security_contract import ENVIRONMENT_ROLE_KINDS
from halpha.runtime_identity import repository_root, require_repository_runtime
from halpha.windows_runtime import current_process_sid
from halpha.winvault import (
    backup_secret_resolver,
    require_win_vault_backend,
)
from tools.provisioning.provision_halpha_databases import SUPERUSER_REFERENCE
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
from tools.qualification.verify_database_boundary import (
    _connect,
    _environment_qualified,
    _inspect_environment,
)


TASK_STATE_READY = 3
TASK_STATE_RUNNING = 4
ENVIRONMENTS = ("demo", "live_copy", "live_personal")
DEFAULT_OUTPUT = Path("build/qualification/database-restore.json")
SOURCE_PATTERNS = (
    "migrations/versions/*.py",
    "requirements/runtime.txt",
    "src/halpha/backup.py",
    "src/halpha/configuration.py",
    "src/halpha/database/**/*.py",
    "src/halpha/process_contract.py",
    "src/halpha/runtime_identity.py",
    "src/halpha/source_identity.py",
    "src/halpha/windows_filesystem.py",
    "src/halpha/windows_runtime.py",
    "src/halpha/winvault.py",
    "tools/provisioning/provision_halpha_databases.py",
    "tools/provisioning/provision_windows_tasks.py",
    "tools/qualification/source_binding.py",
    "tools/qualification/verify_database_boundary.py",
    "tools/qualification/verify_restore_boundary.py",
)


class RestoreQualificationError(RuntimeError):
    """Sanitized restore-qualification failure."""


def _restore_target_database_name() -> str:
    return f"halpha_restore_{uuid4().hex}"


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


def _source_patterns(root: Path, config_path: Path) -> tuple[str, ...]:
    config = config_path.resolve()
    if not config.is_file() or not config.is_relative_to(root):
        raise RestoreQualificationError(
            "RESTORE_QUALIFICATION_CONFIG_OUTSIDE_REPOSITORY"
        )
    return (*SOURCE_PATTERNS, config.relative_to(root).as_posix())


def _validate_output(
    root: Path,
    settings: Any,
    output: Path,
    *,
    child: bool,
) -> None:
    base = (
        (root / settings.maintenance.temporary_root).resolve()
        if child
        else (root / "build" / "qualification").resolve()
    )
    if (
        output.suffix.lower() != ".json"
        or not output.is_relative_to(base)
        or (
            child
            and not output.name.startswith("restore-qualification-")
        )
    ):
        raise RestoreQualificationError(
            "RESTORE_QUALIFICATION_OUTPUT_OUTSIDE_ALLOWED_ROOT"
        )


def _table_snapshots(
    connection: psycopg.Connection[Any],
) -> dict[str, dict[str, Any]]:
    snapshots: dict[str, dict[str, Any]] = {}
    for table in PRODUCT_RECORD_FAMILIES:
        primary_key = tuple(
            str(row[0])
            for row in connection.execute(
                """
                SELECT attribute.attname
                FROM pg_catalog.pg_index AS index_row
                CROSS JOIN LATERAL unnest(index_row.indkey)
                     WITH ORDINALITY AS key_column(attnum, ordinal)
                JOIN pg_catalog.pg_attribute AS attribute
                  ON attribute.attrelid = index_row.indrelid
                 AND attribute.attnum = key_column.attnum
                WHERE index_row.indrelid = to_regclass(%s)
                  AND index_row.indisprimary
                ORDER BY key_column.ordinal
                """,
                (f"halpha.{table}",),
            ).fetchall()
        )
        if not primary_key:
            raise RestoreQualificationError(
                f"RESTORE_QUALIFICATION_PRIMARY_KEY_MISSING table={table}"
            )
        digest = sha256()
        byte_count = 0
        copy_query = sql.SQL(
            "COPY (SELECT * FROM halpha.{} ORDER BY {}) "
            "TO STDOUT WITH (FORMAT BINARY)"
        ).format(
            sql.Identifier(table),
            sql.SQL(", ").join(
                sql.Identifier(column) for column in primary_key
            ),
        )
        with connection.cursor().copy(copy_query) as copy:
            for block in copy:
                payload = bytes(block)
                digest.update(payload)
                byte_count += len(payload)
        record_count = int(
            connection.execute(
                sql.SQL("SELECT count(*) FROM halpha.{}").format(
                    sql.Identifier(table)
                )
            ).fetchone()[0]
        )
        snapshots[table] = {
            "record_count": record_count,
            "content_sha256": digest.hexdigest(),
            "copy_bytes": byte_count,
            "primary_key": list(primary_key),
        }
    return snapshots


def _record_snapshots(
    settings: Any,
    environment: str,
    password: str,
) -> dict[str, dict[str, Any]]:
    target = getattr(settings.maintenance, environment)
    with psycopg.connect(
        host="127.0.0.1",
        port=5432,
        dbname=target.database_name,
        user=target.backup_role_name,
        password=password,
        options="-c default_transaction_read_only=on",
    ) as connection:
        return _table_snapshots(connection)


def _counts_from_snapshots(
    snapshots: dict[str, dict[str, Any]],
) -> dict[str, int]:
    return {
        table: int(snapshot["record_count"])
        for table, snapshot in snapshots.items()
    }


def _child(
    root: Path,
    config_path: Path,
) -> dict[str, Any]:
    require_repository_runtime(root)
    settings = load_settings(config_path)
    if current_process_sid() != settings.windows.backup_task_sid:
        raise RestoreQualificationError(
            "RESTORE_QUALIFICATION_BACKUP_IDENTITY_REQUIRED"
        )
    backend = keyring.get_keyring()
    require_win_vault_backend(backend)
    resolver = backup_secret_resolver(backend, backup_settings(settings))
    environments: dict[str, Any] = {}
    for environment in ENVIRONMENTS:
        target = getattr(settings.maintenance, environment)
        password = resolver.resolve(
            target.backup_credential_reference
        ).get_secret_value()
        try:
            snapshots_before = _record_snapshots(
                settings,
                environment,
                password,
            )
            backup = backup_environment(
                root,
                settings,
                environment=environment,
            )
            snapshots_after = _record_snapshots(
                settings,
                environment,
                password,
            )
        finally:
            password = ""
        archive = (
            root
            / settings.maintenance.backup_root
            / environment
            / str(backup["archive"])
        ).resolve()
        environments[environment] = {
            "source_archive": archive.name,
            "backup": backup,
            "source_record_counts_before": _counts_from_snapshots(
                snapshots_before
            ),
            "source_record_counts_after": _counts_from_snapshots(
                snapshots_after
            ),
            "source_table_snapshots_before": snapshots_before,
            "source_table_snapshots_after": snapshots_after,
            "source_stable_during_backup": (
                snapshots_before == snapshots_after
            ),
        }
    report: dict[str, Any] = {
        "schema_version": 3,
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "task_identity": "BACKUP",
        "environments": environments,
    }
    report["status"] = (
        "QUALIFIED"
        if set(environments) == set(ENVIRONMENTS)
        and all(
            item["backup"].get("status") == "BACKUP_CREATED"
            and item["source_stable_during_backup"]
            and set(item["source_record_counts_after"])
            == set(PRODUCT_RECORD_FAMILIES)
            and set(item["source_table_snapshots_after"])
            == set(PRODUCT_RECORD_FAMILIES)
            for item in environments.values()
        )
        else "REJECTED"
    )
    return report


def _vault_value(service: str, account: str, *, missing_code: str) -> str:
    backend = keyring.get_keyring()
    require_win_vault_backend(backend)
    value = backend.get_password(service, account)
    if not value:
        raise RestoreQualificationError(missing_code)
    return value


def _stop_task_before_delete(task: Any) -> None:
    if int(task.State) != TASK_STATE_RUNNING:
        return
    task.Stop(0)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if int(task.State) != TASK_STATE_RUNNING:
            return
        time.sleep(0.1)
    raise RestoreQualificationError(
        "RESTORE_QUALIFICATION_TASK_STOP_TIMEOUT"
    )


def _run_child_task(
    root: Path,
    config_path: Path,
) -> dict[str, Any]:
    settings = load_settings(config_path)
    child_output = (
        root
        / settings.maintenance.temporary_root
        / f"restore-qualification-{os.getpid()}.json"
    ).resolve()
    child_output.unlink(missing_ok=True)
    service = win32com.client.Dispatch("Schedule.Service")
    service.Connect()
    folder = service.GetFolder(TASK_FOLDER)
    task_name = f"HalphaRestoreCheck-{os.getpid()}"
    definition = service.NewTask(0)
    definition.RegistrationInfo.Author = "Halpha Project Owner"
    definition.RegistrationInfo.Description = (
        "Ephemeral Halpha Demo/Live restore qualification"
    )
    definition.Settings.AllowDemandStart = True
    definition.Settings.DisallowStartIfOnBatteries = False
    definition.Settings.Enabled = True
    definition.Settings.ExecutionTimeLimit = "PT10M"
    definition.Settings.Hidden = True
    definition.Settings.MultipleInstances = TASK_INSTANCES_IGNORE_NEW
    definition.Settings.RestartCount = 0
    definition.Settings.StartWhenAvailable = False
    definition.Settings.StopIfGoingOnBatteries = False
    account = f"{socket.gethostname()}\\{BACKUP_USER}"
    definition.Principal.DisplayName = "Halpha ephemeral backup qualification"
    definition.Principal.UserId = account
    definition.Principal.LogonType = TASK_LOGON_PASSWORD
    definition.Principal.RunLevel = TASK_RUNLEVEL_LUA
    action = definition.Actions.Create(TASK_ACTION_EXEC)
    action.Path = str((root / ".venv" / "Scripts" / "python.exe").resolve())
    action.Arguments = (
        "-m tools.qualification.verify_restore_boundary "
        f'--config "{config_path.resolve()}" '
        f'--output "{child_output}" --child'
    )
    action.WorkingDirectory = str(root)
    password = _vault_value(
        TASK_ACCOUNT_VAULT_SERVICE,
        BACKUP_USER,
        missing_code="BACKUP_TASK_ACCOUNT_PASSWORD_REFERENCE_MISSING",
    )
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
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            state = int(task.State)
            if state != TASK_STATE_RUNNING and child_output.exists():
                break
            if (
                state == TASK_STATE_READY
                and int(task.LastTaskResult) not in (0, 267009)
            ):
                raise RestoreQualificationError(
                    "RESTORE_QUALIFICATION_TASK_FAILED "
                    f"code={int(task.LastTaskResult)}"
                )
            time.sleep(0.25)
        else:
            raise RestoreQualificationError(
                "RESTORE_QUALIFICATION_TASK_TIMEOUT"
            )
        if int(task.LastTaskResult) != 0:
            raise RestoreQualificationError(
                "RESTORE_QUALIFICATION_TASK_FAILED "
                f"code={int(task.LastTaskResult)}"
            )
        report = json.loads(child_output.read_text(encoding="utf-8"))
        if not isinstance(report, dict):
            raise RestoreQualificationError(
                "RESTORE_QUALIFICATION_REPORT_INVALID"
            )
        return report
    finally:
        password = ""
        cleanup_error: RestoreQualificationError | None = None
        if task is not None:
            try:
                _stop_task_before_delete(task)
            except Exception as exc:
                cleanup_error = RestoreQualificationError(
                    "RESTORE_QUALIFICATION_TASK_CLEANUP_FAILED "
                    f"type={type(exc).__name__}"
                )
            try:
                folder.DeleteTask(task_name, 0)
            except pywintypes.com_error as exc:
                cleanup_error = RestoreQualificationError(
                    "RESTORE_QUALIFICATION_TASK_CLEANUP_FAILED "
                    f"code={exc.hresult}"
                )
        child_output.unlink(missing_ok=True)
        if cleanup_error is not None:
            raise cleanup_error


def _peer_connect_rejected(
    environment: str,
    target_database: str,
) -> dict[str, bool]:
    results: dict[str, bool] = {}
    for peer in ENVIRONMENTS:
        if peer == environment:
            continue
        for role in ENVIRONMENT_ROLE_KINDS[peer]:
            key = f"{peer}_{role}"
            try:
                with _connect(peer, role, database=target_database):
                    results[key] = False
            except psycopg.OperationalError as exc:
                if "permission denied for database" not in str(exc):
                    raise
                results[key] = True
    return results


def _drop_target_database(
    superuser: str,
    target_database: str,
) -> None:
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
            sql.SQL("DROP DATABASE {}").format(
                sql.Identifier(target_database)
            )
        )


def _qualify_environment_restore(
    root: Path,
    settings: Any,
    child_environment: dict[str, Any],
    *,
    environment: str,
    superuser: str,
) -> dict[str, Any]:
    target = getattr(settings.maintenance, environment)
    target_database = _restore_target_database_name()
    target_database_created = False
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
                sql.SQL(
                    "CREATE DATABASE {} OWNER {} TEMPLATE template0 "
                    "ENCODING 'UTF8' LC_COLLATE 'C' LC_CTYPE 'C'"
                ).format(
                    sql.Identifier(target_database),
                    sql.Identifier(target.migration_role_name),
                )
            )
            target_database_created = True
            admin.execute(
                sql.SQL(
                    "REVOKE ALL PRIVILEGES ON DATABASE {} FROM PUBLIC"
                ).format(sql.Identifier(target_database))
            )
        archive = (
            root
            / settings.maintenance.backup_root
            / environment
            / str(child_environment.get("source_archive"))
        ).resolve()
        restore = restore_archive(
            root,
            settings,
            environment=environment,
            archive=archive,
            target_database=target_database,
        )
        with psycopg.connect(
            host="127.0.0.1",
            port=5432,
            dbname=target_database,
            user="postgres",
            password=superuser,
        ) as restored:
            restored_revision_rows = restored.execute(
                "SELECT version_num FROM halpha_meta.alembic_version"
            ).fetchall()
            restored_revision = (
                str(restored_revision_rows[0][0])
                if len(restored_revision_rows) == 1
                else "INVALID"
            )
            restored_tables = {
                str(row[0])
                for row in restored.execute(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'halpha'"
                ).fetchall()
            }
            restored_snapshots = _table_snapshots(restored)
            restored_counts = _counts_from_snapshots(restored_snapshots)
        boundary = _inspect_environment(
            environment,
            database=target_database,
        )
        peer_connect = _peer_connect_rejected(
            environment,
            target_database,
        )
        source_counts = child_environment.get(
            "source_record_counts_after",
            {},
        )
        source_snapshots = child_environment.get(
            "source_table_snapshots_after",
            {},
        )
        checks = {
            "custom_archive_digest_verified": (
                restore.get("archive_sha256")
                == child_environment.get("backup", {}).get("archive_sha256")
            ),
            "target_verified_empty_before_restore": (
                restore.get("target_verified_empty") is True
            ),
            "database_acl_converged_after_restore": (
                restore.get("database_acl_converged") is True
            ),
            "exact_product_schema_restored": (
                restored_tables == set(PRODUCT_RECORD_FAMILIES)
            ),
            "restored_schema_revision_current": (
                restored_revision == CURRENT_PRODUCT_SCHEMA_REVISION
            ),
            "source_and_restored_record_counts_match": (
                restored_counts == source_counts
                and set(restored_counts) == set(PRODUCT_RECORD_FAMILIES)
            ),
            "source_and_restored_content_match": (
                restored_snapshots == source_snapshots
                and set(restored_snapshots) == set(PRODUCT_RECORD_FAMILIES)
            ),
            "exact_runtime_database_contract_restored": (
                _environment_qualified(environment, boundary)
            ),
            "all_peer_environment_roles_rejected": (
                set(peer_connect)
                == {
                    f"{peer}_{role}"
                    for peer in ENVIRONMENTS
                    if peer != environment
                    for role in ENVIRONMENT_ROLE_KINDS[peer]
                }
                and all(peer_connect.values())
            ),
            "target_database_is_ephemeral": (
                target_database.startswith("halpha_restore_")
                and len(target_database) == len("halpha_restore_") + 32
            ),
        }
        return {
            "source_archive": child_environment.get("source_archive"),
            "target_database": target_database,
            "restored_schema_revision": restored_revision,
            "source_record_counts": source_counts,
            "restored_record_counts": restored_counts,
            "source_table_snapshots": source_snapshots,
            "restored_table_snapshots": restored_snapshots,
            "peer_connect_rejected": peer_connect,
            "database_boundary": boundary,
            "checks": checks,
            "status": "QUALIFIED" if all(checks.values()) else "REJECTED",
        }
    finally:
        if target_database_created:
            _drop_target_database(superuser, target_database)


def _parent(
    root: Path,
    config_path: Path,
) -> dict[str, Any]:
    require_repository_runtime(root)
    settings = load_settings(config_path)
    if current_process_sid() != settings.windows.maintenance_sid:
        raise RestoreQualificationError(
            "RESTORE_QUALIFICATION_MAINTENANCE_IDENTITY_REQUIRED"
        )
    superuser = _vault_value(
        *SUPERUSER_REFERENCE,
        missing_code="POSTGRESQL_SUPERUSER_REFERENCE_MISSING",
    )
    try:
        child = _run_child_task(root, config_path)
        child_environments = child.get("environments", {})
        if (
            child.get("status") != "QUALIFIED"
            or child.get("task_identity") != "BACKUP"
            or set(child_environments) != set(ENVIRONMENTS)
        ):
            raise RestoreQualificationError(
                "RESTORE_QUALIFICATION_BACKUP_EVIDENCE_REJECTED"
            )
        environments = {
            environment: _qualify_environment_restore(
                root,
                settings,
                child_environments[environment],
                environment=environment,
                superuser=superuser,
            )
            for environment in ENVIRONMENTS
        }
    finally:
        superuser = ""
    checks = {
        "backup_ran_as_dedicated_identity": (
            child.get("task_identity") == "BACKUP"
        ),
        "restore_ran_as_maintenance_identity": (
            current_process_sid() == settings.windows.maintenance_sid
        ),
        "both_environments_qualified": (
            set(environments) == set(ENVIRONMENTS)
            and all(
                item.get("status") == "QUALIFIED"
                for item in environments.values()
            )
        ),
    }
    return {
        "schema_version": 3,
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "operation": "DEMO_LIVE_DATABASE_RESTORE",
        "environments": environments,
        "checks": checks,
        "status": "QUALIFIED" if all(checks.values()) else "REJECTED",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--child", action="store_true")
    args = parser.parse_args(argv)
    root = repository_root()
    config_path = args.config.resolve()
    settings = load_settings(config_path)
    output = args.output.resolve()
    _validate_output(root, settings, output, child=args.child)
    patterns = _source_patterns(root, config_path)
    source_sha256_at_start = capture_source_sha256(root, patterns)
    try:
        report = (
            _child(root, config_path)
            if args.child
            else _parent(root, config_path)
        )
    except Exception as exc:
        reason = (
            str(exc)
            if isinstance(exc, RestoreQualificationError)
            else f"RESTORE_QUALIFICATION_FAILED type={type(exc).__name__}"
        )
        report = {
            "schema_version": 3,
            "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "operation": "DEMO_LIVE_DATABASE_RESTORE",
            "status": "REJECTED",
            "reason": reason,
        }
    report["source_sha256"] = source_sha256_at_start
    try:
        source_stable = (
            capture_source_sha256(root, patterns)
            == source_sha256_at_start
        )
    except SourceBindingError as exc:
        source_stable = False
        report.setdefault("errors", []).append(
            f"RESTORE_SOURCE_BINDING_FAILED:{exc}"
        )
    checks = report.setdefault("checks", {})
    checks["source_stable_during_qualification"] = source_stable
    if not source_stable or (
        report.get("status") == "QUALIFIED"
        and not all(checks.values())
    ):
        report["status"] = "REJECTED"
    report["evidence_digest"] = _canonical_digest(report)
    _write_report(output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("status") == "QUALIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
