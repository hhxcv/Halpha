"""One-shot PostgreSQL backup and maintenance-only restore launcher."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
import json
import locale
import os
from pathlib import Path
import re
import secrets
import subprocess
from typing import Any, Iterator, Sequence

import keyring
import psycopg
from psycopg import sql
import pywintypes
import win32con
import win32file
import win32security

from halpha.configuration import (
    DatabaseMaintenanceTarget,
    HalphaSettings,
    backup_log_directory,
    backup_settings,
    load_settings,
    maintenance_settings,
)
from halpha.database.security_contract import database_access_roles
from halpha.operational_logging import configure_halpha_logging
from halpha.runtime_identity import repository_root, require_repository_runtime
from halpha.windows_runtime import (
    BUILTIN_ADMINISTRATORS_SID,
    SYSTEM_SID,
    require_process_identity,
)
from halpha.windows_filesystem import (
    WindowsFilesystemError,
    assert_directory_security,
    backup_acl_specs,
    role_write_grants,
)
from halpha.winvault import backup_secret_resolver, maintenance_secret_resolver


POSTGRESQL_VERSION = "17.10"
RESTORE_DATABASE_PATTERN = re.compile(r"^halpha_restore_[a-z0-9_]{1,48}$")
BACKUP_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "observed_at",
        "database",
        "environment_kind",
        "venue_account_type",
        "archive",
        "archive_size",
        "archive_sha256",
        "format",
        "tool_version",
        "credential_transport",
    }
)


class BackupError(RuntimeError):
    """Sanitized backup or restore failure."""


def _repository_path(repository_root: Path, relative: str) -> Path:
    root = repository_root.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise BackupError("BACKUP_PATH_OUTSIDE_REPOSITORY")
    return path


def _protected_security_attributes(
    task_sid: str,
    maintenance_sid: str,
) -> pywintypes.SECURITY_ATTRIBUTES:
    sid = win32security.ConvertStringSidToSid(task_sid)
    dacl = win32security.ACL()
    grants = (
        (
            (SYSTEM_SID, win32file.FILE_ALL_ACCESS),
            (BUILTIN_ADMINISTRATORS_SID, win32file.FILE_ALL_ACCESS),
            (maintenance_sid, win32file.FILE_ALL_ACCESS),
        )
        if task_sid == maintenance_sid
        else role_write_grants(
            maintenance_sid=maintenance_sid,
            role_sid=task_sid,
        )
    )
    for sid_text, mask in grants:
        dacl.AddAccessAllowedAceEx(
            win32security.ACL_REVISION,
            0,
            mask,
            win32security.ConvertStringSidToSid(sid_text),
        )
    descriptor = win32security.SECURITY_DESCRIPTOR()
    descriptor.SetSecurityDescriptorOwner(sid, False)
    descriptor.SetSecurityDescriptorDacl(True, dacl, False)
    descriptor.SetSecurityDescriptorControl(
        win32security.SE_DACL_PROTECTED,
        win32security.SE_DACL_PROTECTED,
    )
    attributes = pywintypes.SECURITY_ATTRIBUTES()
    attributes.bInheritHandle = False
    attributes.SECURITY_DESCRIPTOR = descriptor
    return attributes


def _escape_pgpass(value: str) -> str:
    return value.replace("\\", "\\\\").replace(":", "\\:")


@contextmanager
def _temporary_pgpass(
    temporary_root: Path,
    *,
    task_sid: str,
    maintenance_sid: str,
    database: str,
    username: str,
    password: str,
) -> Iterator[Path]:
    if not temporary_root.is_dir():
        raise BackupError("BACKUP_TEMPORARY_DIRECTORY_MISSING")
    path = temporary_root / f"pgpass-{secrets.token_hex(16)}.conf"
    content = (
        ":".join(
            _escape_pgpass(value)
            for value in ("127.0.0.1", "5432", database, username, password)
        )
        + "\n"
    ).encode("utf-8")
    try:
        handle = win32file.CreateFile(
            str(path),
            win32con.GENERIC_READ | win32con.GENERIC_WRITE,
            win32con.FILE_SHARE_READ | win32con.FILE_SHARE_DELETE,
            _protected_security_attributes(task_sid, maintenance_sid),
            win32con.CREATE_NEW,
            win32con.FILE_ATTRIBUTE_TEMPORARY | win32con.FILE_FLAG_DELETE_ON_CLOSE,
            None,
        )
    except pywintypes.error as exc:
        raise BackupError(f"PGPASS_CREATE_FAILED code={exc.winerror}") from None
    try:
        win32file.WriteFile(handle, content)
        win32file.FlushFileBuffers(handle)
        yield path
    finally:
        handle.Close()


def _tool_path(settings: HalphaSettings, name: str) -> Path:
    path = Path(settings.maintenance.postgresql_bin_directory) / f"{name}.exe"
    if not path.is_file():
        raise BackupError(f"POSTGRESQL_TOOL_MISSING tool={name}")
    version = subprocess.run(
        [str(path), "--version"],
        check=False,
        capture_output=True,
        text=True,
        encoding=locale.getpreferredencoding(False),
        errors="replace",
    )
    if version.returncode != 0 or f"PostgreSQL) {POSTGRESQL_VERSION}" not in version.stdout:
        raise BackupError(f"POSTGRESQL_TOOL_VERSION_MISMATCH tool={name}")
    return path


def _subprocess_environment(pgpass_path: Path) -> dict[str, str]:
    system_root = os.environ.get("SystemRoot")
    if not system_root:
        raise BackupError("SYSTEM_ROOT_MISSING")
    return {
        "SystemRoot": system_root,
        "PGPASSFILE": str(pgpass_path),
        "PGCLIENTENCODING": "UTF8",
    }


def _run_tool(command: Sequence[str], pgpass_path: Path) -> None:
    result = subprocess.run(
        list(command),
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding=locale.getpreferredencoding(False),
        errors="replace",
        env=_subprocess_environment(pgpass_path),
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode != 0:
        message = result.stderr.casefold()
        if "no password supplied" in message:
            failure = "PGPASS_NOT_USED"
        elif "password authentication failed" in message:
            failure = "AUTHENTICATION_REJECTED"
        elif "could not open output file" in message:
            failure = "OUTPUT_OPEN_FAILED"
        elif "permission denied" in message:
            failure = "DATABASE_PERMISSION_DENIED"
        elif "connection to server" in message:
            failure = "DATABASE_CONNECTION_FAILED"
        else:
            failure = "UNCLASSIFIED"
        raise BackupError(
            f"POSTGRESQL_TOOL_FAILED tool={Path(command[0]).stem} "
            f"code={result.returncode} class={failure}"
        )


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _target(settings: HalphaSettings, environment: str) -> DatabaseMaintenanceTarget:
    targets = dict(settings.maintenance.named_targets())
    try:
        return targets[environment]
    except KeyError:
        raise BackupError("BACKUP_ENVIRONMENT_INVALID") from None


def _write_backup_manifest(
    archive: Path,
    *,
    target: DatabaseMaintenanceTarget,
    observed_at: datetime,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": 2,
        "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
        "database": target.database_name,
        "environment_kind": target.environment_kind,
        "venue_account_type": target.venue_account_type.value,
        "archive": archive.name,
        "archive_size": archive.stat().st_size,
        "archive_sha256": _sha256_file(archive),
        "format": "POSTGRESQL_CUSTOM",
        "tool_version": POSTGRESQL_VERSION,
        "credential_transport": "DELETE_ON_CLOSE_PGPASSFILE",
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    archive.with_suffix(".json").write_text(rendered, encoding="utf-8")
    return report


def _assert_restore_manifest(
    source: Path,
    manifest: dict[str, Any],
    *,
    target: DatabaseMaintenanceTarget,
) -> None:
    observed_at_value = manifest.get("observed_at")
    try:
        observed_at = datetime.fromisoformat(
            str(observed_at_value).replace("Z", "+00:00")
        )
    except ValueError:
        observed_at = None
    expected_name = re.fullmatch(
        rf"{re.escape(target.database_name)}-\d{{8}}T\d{{6}}Z\.dump",
        source.name,
    )
    if (
        set(manifest) != BACKUP_MANIFEST_KEYS
        or manifest.get("schema_version") != 2
        or observed_at is None
        or observed_at.tzinfo is None
        or manifest.get("database") != target.database_name
        or manifest.get("environment_kind") != target.environment_kind
        or manifest.get("venue_account_type") != target.venue_account_type.value
        or manifest.get("archive") != source.name
        or manifest.get("archive_size") != source.stat().st_size
        or source.stat().st_size <= 0
        or manifest.get("archive_sha256") != _sha256_file(source)
        or manifest.get("format") != "POSTGRESQL_CUSTOM"
        or manifest.get("tool_version") != POSTGRESQL_VERSION
        or manifest.get("credential_transport") != "DELETE_ON_CLOSE_PGPASSFILE"
        or expected_name is None
    ):
        raise BackupError("RESTORE_MANIFEST_INVALID")


def _assert_empty_restore_target(
    connection: psycopg.Connection[Any],
    *,
    target_database: str,
    migration_role: str,
) -> None:
    database_row = connection.execute(
        """
        SELECT owner.rolname, database_row.datcollate, database_row.datctype
        FROM pg_catalog.pg_database AS database_row
        JOIN pg_catalog.pg_roles AS owner ON owner.oid = database_row.datdba
        WHERE database_row.datname = current_database()
        """
    ).fetchone()
    relation_count = int(
        connection.execute(
            """
            SELECT count(*)
            FROM pg_catalog.pg_class AS relation
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname NOT LIKE 'pg_%'
              AND namespace.nspname <> 'information_schema'
            """
        ).fetchone()[0]
    )
    extra_schemas = [
        str(row[0])
        for row in connection.execute(
            """
            SELECT nspname
            FROM pg_catalog.pg_namespace
            WHERE nspname NOT LIKE 'pg_%'
              AND nspname NOT IN ('information_schema', 'public')
            ORDER BY nspname
            """
        ).fetchall()
    ]
    if (
        connection.info.dbname != target_database
        or connection.info.user != migration_role
        or database_row != (migration_role, "C", "C")
        or relation_count != 0
        or extra_schemas
    ):
        raise BackupError("RESTORE_TARGET_NOT_EMPTY_OR_NONSTANDARD")


def _converge_restore_database_acl(
    connection: psycopg.Connection[Any],
    *,
    environment: str,
    target_database: str,
    migration_role: str,
) -> None:
    rows = connection.execute(
        """
        SELECT DISTINCT COALESCE(role.rolname, 'PUBLIC')
        FROM pg_catalog.pg_database AS database_row
        CROSS JOIN LATERAL aclexplode(
            COALESCE(
                database_row.datacl,
                acldefault('d', database_row.datdba)
            )
        ) AS acl
        LEFT JOIN pg_catalog.pg_roles AS role ON role.oid = acl.grantee
        WHERE database_row.datname = current_database()
        """
    ).fetchall()
    granted_roles, peer_roles = database_access_roles(environment)
    revoke_targets = (
        {str(row[0]) for row in rows}
        | set(granted_roles)
        | set(peer_roles)
        | {"PUBLIC"}
    ) - {migration_role}
    for grantee in sorted(revoke_targets):
        target = sql.SQL("PUBLIC") if grantee == "PUBLIC" else sql.Identifier(grantee)
        connection.execute(
            sql.SQL("REVOKE ALL PRIVILEGES ON DATABASE {} FROM {}").format(
                sql.Identifier(target_database),
                target,
            )
        )
    for role in granted_roles:
        connection.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(target_database),
                sql.Identifier(role),
            )
        )
    connection.commit()


def _apply_retention(directory: Path, retention_count: int) -> list[str]:
    archives = sorted(directory.glob("*.dump"), key=lambda path: path.name, reverse=True)
    removed: list[str] = []
    for archive in archives[retention_count:]:
        manifest = archive.with_suffix(".json")
        archive.unlink(missing_ok=True)
        manifest.unlink(missing_ok=True)
        removed.append(archive.name)
    return removed


def backup_environment(
    repository_root: Path,
    settings: HalphaSettings,
    *,
    environment: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    target = _target(settings, environment)
    task_sid = settings.windows.backup_task_sid
    require_process_identity(task_sid)
    acl_specs = {
        spec.label: spec
        for spec in backup_acl_specs(repository_root, settings)
    }
    assert_directory_security(acl_specs[f"{environment}_backups"])
    assert_directory_security(acl_specs["backup_temporary"])
    resolver = backup_secret_resolver(keyring.get_keyring(), backup_settings(settings))
    password = resolver.resolve(target.backup_credential_reference).get_secret_value()
    backup_root = _repository_path(repository_root, settings.maintenance.backup_root)
    output = backup_root / environment
    temporary_root = _repository_path(repository_root, settings.maintenance.temporary_root)
    observed_at = now or datetime.now(UTC)
    stamp = observed_at.strftime("%Y%m%dT%H%M%SZ")
    partial = output / f"{target.database_name}-{stamp}.dump.partial"
    archive = output / f"{target.database_name}-{stamp}.dump"
    if partial.exists() or archive.exists():
        raise BackupError("BACKUP_ARCHIVE_IDENTITY_COLLISION")
    pg_dump = _tool_path(settings, "pg_dump")
    try:
        with _temporary_pgpass(
            temporary_root,
            task_sid=task_sid,
            maintenance_sid=settings.windows.maintenance_sid,
            database=target.database_name,
            username=target.backup_role_name,
            password=password,
        ) as pgpass:
            _run_tool(
                (
                    str(pg_dump),
                    "--host=127.0.0.1",
                    "--port=5432",
                    f"--username={target.backup_role_name}",
                    f"--dbname={target.database_name}",
                    "--format=custom",
                    "--no-owner",
                    f"--file={partial}",
                ),
                pgpass,
            )
        if not partial.is_file() or partial.stat().st_size == 0:
            raise BackupError("BACKUP_ARCHIVE_EMPTY")
        partial.replace(archive)
        report = _write_backup_manifest(archive, target=target, observed_at=observed_at)
        report["retention_removed"] = _apply_retention(
            output,
            settings.maintenance.backup_retention_count,
        )
        report["status"] = "BACKUP_CREATED"
        return report
    finally:
        password = ""
        partial.unlink(missing_ok=True)


def backup_all(repository_root: Path, settings: HalphaSettings) -> dict[str, Any]:
    results = {
        environment: backup_environment(repository_root, settings, environment=environment)
        for environment, _target_value in settings.maintenance.named_targets()
    }
    return {"status": "BACKUPS_CREATED", "results": results}


def restore_archive(
    repository_root: Path,
    settings: HalphaSettings,
    *,
    environment: str,
    archive: Path,
    target_database: str,
) -> dict[str, Any]:
    if RESTORE_DATABASE_PATTERN.fullmatch(target_database) is None:
        raise BackupError("RESTORE_TARGET_DATABASE_INVALID")
    target = _target(settings, environment)
    task_sid = settings.windows.maintenance_sid
    require_process_identity(task_sid)
    acl_specs = {
        spec.label: spec
        for spec in backup_acl_specs(repository_root, settings)
    }
    assert_directory_security(acl_specs[f"{environment}_backups"])
    assert_directory_security(acl_specs["backup_temporary"])
    backup_root = _repository_path(repository_root, settings.maintenance.backup_root)
    environment_root = (backup_root / environment).resolve()
    source = archive.resolve()
    if not source.is_file() or source.parent != environment_root:
        raise BackupError("RESTORE_ARCHIVE_OUTSIDE_BACKUP_ROOT")
    manifest_path = source.with_suffix(".json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        raise BackupError("RESTORE_MANIFEST_INVALID") from None
    _assert_restore_manifest(source, manifest, target=target)
    resolver = maintenance_secret_resolver(keyring.get_keyring(), maintenance_settings(settings))
    password = resolver.resolve(target.migration_credential_reference).get_secret_value()
    temporary_root = _repository_path(repository_root, settings.maintenance.temporary_root)
    pg_restore = _tool_path(settings, "pg_restore")
    try:
        with psycopg.connect(
            host="127.0.0.1",
            port=5432,
            dbname=target_database,
            user=target.migration_role_name,
            password=password,
        ) as connection:
            _assert_empty_restore_target(
                connection,
                target_database=target_database,
                migration_role=target.migration_role_name,
            )
        with _temporary_pgpass(
            temporary_root,
            task_sid=task_sid,
            maintenance_sid=settings.windows.maintenance_sid,
            database=target_database,
            username=target.migration_role_name,
            password=password,
        ) as pgpass:
            _run_tool(
                (
                    str(pg_restore),
                    "--host=127.0.0.1",
                    "--port=5432",
                    f"--username={target.migration_role_name}",
                    f"--dbname={target_database}",
                    "--no-owner",
                    "--exit-on-error",
                    str(source),
                ),
                pgpass,
            )
        with psycopg.connect(
            host="127.0.0.1",
            port=5432,
            dbname=target_database,
            user=target.migration_role_name,
            password=password,
        ) as connection:
            _converge_restore_database_acl(
                connection,
                environment=environment,
                target_database=target_database,
                migration_role=target.migration_role_name,
            )
    finally:
        password = ""
    return {
        "status": "RESTORE_COMPLETED",
        "source_database": target.database_name,
        "target_database": target_database,
        "archive_sha256": manifest["archive_sha256"],
        "target_verified_empty": True,
        "database_acl_converged": True,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="halpha-backup")
    parser.add_argument("--config", type=Path, required=True)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("backup")
    restore = subparsers.add_parser("restore")
    restore.add_argument("--environment", choices=("demo", "live"), required=True)
    restore.add_argument("--archive", type=Path, required=True)
    restore.add_argument("--target-database", required=True)
    args = parser.parse_args(argv)
    logger = None
    try:
        root = repository_root()
        require_repository_runtime(root)
        settings = load_settings(args.config)
        for spec in backup_acl_specs(root, settings):
            assert_directory_security(spec)
        logger = configure_halpha_logging(
            backup_log_directory(root, settings),
            role="backup",
        )
        logger.info("backup_operation_starting", operation=args.command)
        if args.command == "backup":
            report = backup_all(root, settings)
        else:
            report = restore_archive(
                root,
                settings,
                environment=args.environment,
                archive=args.archive,
                target_database=args.target_database,
            )
    except Exception as exc:
        if isinstance(exc, (BackupError, WindowsFilesystemError)):
            reason = str(exc)
        elif isinstance(exc, pywintypes.error):
            reason = f"BACKUP_WINDOWS_OPERATION_FAILED code={exc.winerror}"
        else:
            reason = f"BACKUP_OPERATION_FAILED type={type(exc).__name__}"
        if logger is not None:
            logger.error("backup_operation_rejected", reason_code=reason)
        print(json.dumps({"status": "REJECTED", "reason": reason}, sort_keys=True))
        return 2
    if logger is not None:
        logger.info("backup_operation_completed", operation=args.command)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
