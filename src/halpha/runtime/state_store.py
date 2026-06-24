from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

from halpha.storage import artifact_base


STATE_STORE_REF = ".halpha/state.sqlite"
DEFAULT_BUSY_TIMEOUT_MS = 5000


@dataclass(frozen=True)
class StateStoreMigration:
    version: int
    name: str
    statements: tuple[str, ...] = ()


RUNTIME_STATE_MIGRATIONS = (
    StateStoreMigration(
        version=1,
        name="foundation",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS runtime_state_metadata (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """,
        ),
    ),
)


def runtime_state_path(
    *,
    runtime_root: Path | None = None,
    config_path: Path | None = None,
) -> Path:
    root = runtime_root if runtime_root is not None else artifact_base(config_path)
    return root.resolve() / STATE_STORE_REF


def initialize_runtime_state_store(
    *,
    runtime_root: Path | None = None,
    config_path: Path | None = None,
    now: datetime | str | None = None,
) -> dict[str, Any]:
    database_path = runtime_state_path(runtime_root=runtime_root, config_path=config_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(open_runtime_state_connection(runtime_root=runtime_root, config_path=config_path)) as connection:
        applied = apply_runtime_state_migrations(connection, now=now)
    return {
        "status": "ok",
        "database_ref": STATE_STORE_REF,
        "applied_migrations": [migration.version for migration in applied],
    }


def open_runtime_state_connection(
    *,
    runtime_root: Path | None = None,
    config_path: Path | None = None,
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
) -> sqlite3.Connection:
    database_path = runtime_state_path(runtime_root=runtime_root, config_path=config_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    _configure_connection(connection, busy_timeout_ms=busy_timeout_ms, read_only=False)
    return connection


def open_runtime_state_readonly_connection(
    *,
    runtime_root: Path | None = None,
    config_path: Path | None = None,
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
) -> sqlite3.Connection:
    database_path = runtime_state_path(runtime_root=runtime_root, config_path=config_path)
    connection = sqlite3.connect(_sqlite_file_uri(database_path, mode="ro"), uri=True)
    _configure_connection(connection, busy_timeout_ms=busy_timeout_ms, read_only=True)
    return connection


def apply_runtime_state_migrations(
    connection: sqlite3.Connection,
    *,
    migrations: Iterable[StateStoreMigration] = RUNTIME_STATE_MIGRATIONS,
    now: datetime | str | None = None,
) -> list[StateStoreMigration]:
    ordered = _validated_migrations(tuple(migrations))
    applied_at = _format_utc(now)
    _create_schema_migrations_table(connection)
    applied_versions = {
        int(row[0])
        for row in connection.execute("SELECT version FROM schema_migrations").fetchall()
    }
    applied: list[StateStoreMigration] = []
    with runtime_state_transaction(connection):
        for migration in ordered:
            if migration.version in applied_versions:
                continue
            for statement in migration.statements:
                connection.execute(statement)
            connection.execute(
                """
                INSERT INTO schema_migrations (version, name, applied_at)
                VALUES (?, ?, ?)
                """,
                (migration.version, migration.name, applied_at),
            )
            applied.append(migration)
    return applied


def runtime_state_transaction(connection: sqlite3.Connection):
    return _RuntimeStateTransaction(connection)


def runtime_state_error_diagnostic(exc: sqlite3.Error, *, operation: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "operation": _safe_operation_label(operation),
        "error_type": type(exc).__name__,
        "message": _runtime_state_error_message(exc),
        "database_ref": STATE_STORE_REF,
        "private_values_embedded": False,
    }


class _RuntimeStateTransaction:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def __enter__(self) -> sqlite3.Connection:
        self._connection.execute("BEGIN IMMEDIATE")
        return self._connection

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc_type is None:
            self._connection.commit()
        else:
            self._connection.rollback()
        return False


def _configure_connection(connection: sqlite3.Connection, *, busy_timeout_ms: int, read_only: bool) -> None:
    connection.isolation_level = None
    if not read_only:
        connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
    if read_only:
        connection.execute("PRAGMA query_only = ON")


def _sqlite_file_uri(path: Path, *, mode: str) -> str:
    resolved = path.resolve().as_posix()
    return f"file:{quote(resolved, safe='/:')}?mode={mode}"


def _runtime_state_error_message(exc: sqlite3.Error) -> str:
    text = str(exc).lower()
    if "locked" in text:
        return "runtime state database is locked; retry after the current writer finishes."
    if "unable to open" in text or "cannot open" in text:
        return "runtime state database could not be opened; verify runtime root permissions and retry."
    if "readonly" in text or "read-only" in text:
        return "runtime state database is read-only; use a write connection for mutations."
    return "runtime state SQLite operation failed; inspect the local state store and retry."


def _safe_operation_label(operation: str) -> str:
    text = str(operation).strip()
    lowered = text.lower()
    private_markers = ("\\", "/", "://", "token", "secret", "proxy")
    if not text or any(marker in lowered for marker in private_markers):
        return "runtime state operation"
    return text[:80]


def _create_schema_migrations_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
          version INTEGER PRIMARY KEY,
          name TEXT NOT NULL,
          applied_at TEXT NOT NULL
        )
        """
    )


def _validated_migrations(migrations: tuple[StateStoreMigration, ...]) -> tuple[StateStoreMigration, ...]:
    versions = [migration.version for migration in migrations]
    if versions != sorted(versions):
        raise ValueError("runtime state migrations must be ordered by version.")
    if len(set(versions)) != len(versions):
        raise ValueError("runtime state migration versions must be unique.")
    if any(version < 1 for version in versions):
        raise ValueError("runtime state migration versions must be positive.")
    return migrations


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("migration timestamp must include a UTC offset.")
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str):
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("migration timestamp must be an ISO 8601 UTC string.") from exc
        if timestamp.tzinfo is None:
            raise ValueError("migration timestamp must include a UTC offset.")
        timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)
    else:
        raise ValueError("migration timestamp must be a datetime or ISO 8601 UTC string.")
    return timestamp.isoformat().replace("+00:00", "Z")
