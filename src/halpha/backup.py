"""One-shot PostgreSQL backup and restore launcher for the App task identity."""

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
import pywintypes
import win32con
import win32file
import win32security

from halpha.configuration import (
    DatabaseMaintenanceTarget,
    HalphaSettings,
    load_settings,
    maintenance_settings,
)
from halpha.operational_logging import configure_halpha_logging
from halpha.runtime_identity import repository_root, require_repository_runtime
from halpha.windows_runtime import current_process_sid, require_process_identity
from halpha.winvault import maintenance_secret_resolver


POSTGRESQL_VERSION = "17.10"
RESTORE_DATABASE_PATTERN = re.compile(r"^halpha_restore_[a-z0-9_]{1,48}$")


class BackupError(RuntimeError):
    """Sanitized backup or restore failure."""


def _repository_path(repository_root: Path, relative: str) -> Path:
    root = repository_root.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise BackupError("BACKUP_PATH_OUTSIDE_REPOSITORY")
    return path


def _protected_security_attributes(task_sid: str) -> pywintypes.SECURITY_ATTRIBUTES:
    sid = win32security.ConvertStringSidToSid(task_sid)
    dacl = win32security.ACL()
    dacl.AddAccessAllowedAceEx(
        win32security.ACL_REVISION,
        win32security.OBJECT_INHERIT_ACE | win32security.CONTAINER_INHERIT_ACE,
        win32con.GENERIC_ALL,
        sid,
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


def _protect_directory(path: Path, task_sid: str) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
        attributes = _protected_security_attributes(task_sid)
        descriptor = attributes.SECURITY_DESCRIPTOR
        current = win32security.GetNamedSecurityInfo(
            str(path),
            win32security.SE_FILE_OBJECT,
            win32security.OWNER_SECURITY_INFORMATION,
        )
        actual_owner = win32security.ConvertSidToStringSid(
            current.GetSecurityDescriptorOwner()
        )
        if actual_owner != task_sid:
            raise BackupError("BACKUP_DIRECTORY_OWNER_MISMATCH")
        win32security.SetNamedSecurityInfo(
            str(path),
            win32security.SE_FILE_OBJECT,
            win32security.DACL_SECURITY_INFORMATION
            | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
            None,
            None,
            descriptor.GetSecurityDescriptorDacl(),
            None,
        )
    except pywintypes.error as exc:
        raise BackupError(
            f"BACKUP_DIRECTORY_SECURITY_FAILED code={exc.winerror}"
        ) from None


def _escape_pgpass(value: str) -> str:
    return value.replace("\\", "\\\\").replace(":", "\\:")


@contextmanager
def _temporary_pgpass(
    temporary_root: Path,
    *,
    task_sid: str,
    database: str,
    username: str,
    password: str,
) -> Iterator[Path]:
    _protect_directory(temporary_root, task_sid)
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
            _protected_security_attributes(task_sid),
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
    if environment == "demo":
        return settings.maintenance.demo
    if environment == "live":
        return settings.maintenance.live
    raise BackupError("BACKUP_ENVIRONMENT_INVALID")


def _write_backup_manifest(
    archive: Path,
    *,
    target: DatabaseMaintenanceTarget,
    observed_at: datetime,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": 1,
        "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
        "database": target.database_name,
        "environment_kind": target.environment_kind,
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
    task_sid = settings.windows.app_task_sid
    require_process_identity(task_sid)
    resolver = maintenance_secret_resolver(keyring.get_keyring(), maintenance_settings(settings))
    password = resolver.resolve(target.backup_credential_reference).get_secret_value()
    backup_root = _repository_path(repository_root, settings.maintenance.backup_root)
    output = backup_root / environment
    _protect_directory(output, task_sid)
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
                    "--no-privileges",
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
        for environment in ("demo", "live")
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
    task_sid = settings.windows.app_task_sid
    require_process_identity(task_sid)
    backup_root = _repository_path(repository_root, settings.maintenance.backup_root)
    source = archive.resolve()
    if not source.is_file() or not source.is_relative_to(backup_root):
        raise BackupError("RESTORE_ARCHIVE_OUTSIDE_BACKUP_ROOT")
    manifest_path = source.with_suffix(".json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        raise BackupError("RESTORE_MANIFEST_INVALID") from None
    if (
        manifest.get("database") != target.database_name
        or manifest.get("archive_sha256") != _sha256_file(source)
    ):
        raise BackupError("RESTORE_ARCHIVE_DIGEST_MISMATCH")
    resolver = maintenance_secret_resolver(keyring.get_keyring(), maintenance_settings(settings))
    password = resolver.resolve(target.migration_credential_reference).get_secret_value()
    temporary_root = _repository_path(repository_root, settings.maintenance.temporary_root)
    pg_restore = _tool_path(settings, "pg_restore")
    try:
        with _temporary_pgpass(
            temporary_root,
            task_sid=task_sid,
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
                    "--no-privileges",
                    "--exit-on-error",
                    str(source),
                ),
                pgpass,
            )
    finally:
        password = ""
    return {
        "status": "RESTORE_COMPLETED",
        "source_database": target.database_name,
        "target_database": target_database,
        "archive_sha256": manifest["archive_sha256"],
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
        logger = configure_halpha_logging(
            root / settings.maintenance.log_root,
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
        if isinstance(exc, BackupError):
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
