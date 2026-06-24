from __future__ import annotations

from contextlib import closing
import sqlite3
from pathlib import Path

import pytest

from halpha.runtime.state_store import (
    StateStoreMigration,
    apply_runtime_state_migrations,
    initialize_runtime_state_store,
    open_runtime_state_connection,
    open_runtime_state_readonly_connection,
    runtime_state_error_diagnostic,
    runtime_state_transaction,
    runtime_state_path,
)


def test_runtime_state_store_initializes_under_runtime_root_not_config_dir(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_path = config_dir / "config.yaml"
    config_path.write_text("run:\n  output_dir: runs\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = initialize_runtime_state_store(config_path=config_path, now="2026-06-24T00:00:00Z")

    state_path = tmp_path / ".halpha" / "state.sqlite"
    assert runtime_state_path(config_path=config_path) == state_path
    assert state_path.is_file()
    assert not (config_dir / ".halpha" / "state.sqlite").exists()
    assert result == {
        "status": "ok",
        "database_ref": ".halpha/state.sqlite",
        "applied_migrations": [1],
    }
    with closing(sqlite3.connect(state_path)) as connection:
        rows = connection.execute(
            "SELECT version, name, applied_at FROM schema_migrations ORDER BY version",
        ).fetchall()
    assert rows == [(1, "foundation", "2026-06-24T00:00:00Z")]


def test_runtime_state_store_initialization_is_idempotent(tmp_path: Path) -> None:
    first = initialize_runtime_state_store(runtime_root=tmp_path, now="2026-06-24T00:00:00Z")
    second = initialize_runtime_state_store(runtime_root=tmp_path, now="2026-06-25T00:00:00Z")

    assert first["applied_migrations"] == [1]
    assert second["applied_migrations"] == []
    with closing(sqlite3.connect(tmp_path / ".halpha" / "state.sqlite")) as connection:
        rows = connection.execute(
            "SELECT version, name, applied_at FROM schema_migrations ORDER BY version",
        ).fetchall()
    assert rows == [(1, "foundation", "2026-06-24T00:00:00Z")]


def test_runtime_state_connections_enable_wal_foreign_keys_and_busy_timeout(tmp_path: Path) -> None:
    initialize_runtime_state_store(runtime_root=tmp_path)

    with closing(open_runtime_state_connection(runtime_root=tmp_path, busy_timeout_ms=1234)) as connection:
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]

    assert journal_mode == "wal"
    assert foreign_keys == 1
    assert busy_timeout == 1234


def test_runtime_state_migrations_apply_in_order_and_once(tmp_path: Path) -> None:
    migrations = (
        StateStoreMigration(
            version=1,
            name="create_probe",
            statements=(
                """
                CREATE TABLE migration_probe (
                  position INTEGER PRIMARY KEY,
                  label TEXT NOT NULL
                )
                """,
                "INSERT INTO migration_probe (position, label) VALUES (1, 'first')",
            ),
        ),
        StateStoreMigration(
            version=2,
            name="append_probe",
            statements=("INSERT INTO migration_probe (position, label) VALUES (2, 'second')",),
        ),
    )

    with closing(open_runtime_state_connection(runtime_root=tmp_path)) as connection:
        applied = apply_runtime_state_migrations(
            connection,
            migrations=migrations,
            now="2026-06-24T00:00:00Z",
        )
        reapplied = apply_runtime_state_migrations(
            connection,
            migrations=migrations,
            now="2026-06-25T00:00:00Z",
        )
        probe_rows = connection.execute("SELECT label FROM migration_probe ORDER BY position").fetchall()
        migration_rows = connection.execute(
            "SELECT version, name, applied_at FROM schema_migrations ORDER BY version",
        ).fetchall()

    assert [migration.version for migration in applied] == [1, 2]
    assert reapplied == []
    assert probe_rows == [("first",), ("second",)]
    assert migration_rows == [
        (1, "create_probe", "2026-06-24T00:00:00Z"),
        (2, "append_probe", "2026-06-24T00:00:00Z"),
    ]


def test_runtime_state_transaction_rolls_back_on_failure(tmp_path: Path) -> None:
    initialize_runtime_state_store(runtime_root=tmp_path)

    with closing(open_runtime_state_connection(runtime_root=tmp_path)) as connection:
        connection.execute("CREATE TABLE rollback_probe (value TEXT NOT NULL)")
        with pytest.raises(RuntimeError, match="stop"):
            with runtime_state_transaction(connection):
                connection.execute("INSERT INTO rollback_probe (value) VALUES ('partial')")
                raise RuntimeError("stop")
        count = connection.execute("SELECT COUNT(*) FROM rollback_probe").fetchone()[0]

    assert count == 0


def test_runtime_state_readonly_connection_does_not_apply_migrations_or_mutate(tmp_path: Path) -> None:
    state_path = tmp_path / ".halpha" / "state.sqlite"
    state_path.parent.mkdir(parents=True)
    sqlite3.connect(state_path).close()

    with closing(open_runtime_state_readonly_connection(runtime_root=tmp_path)) as connection:
        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            connection.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("CREATE TABLE should_not_write (value TEXT)")

    with closing(sqlite3.connect(state_path)) as connection:
        tables = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    assert tables == []


def test_runtime_state_allows_concurrent_readers(tmp_path: Path) -> None:
    initialize_runtime_state_store(runtime_root=tmp_path)

    with (
        closing(open_runtime_state_readonly_connection(runtime_root=tmp_path)) as first,
        closing(open_runtime_state_readonly_connection(runtime_root=tmp_path)) as second,
    ):
        first_count = first.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        second_count = second.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]

    assert first_count == 1
    assert second_count == 1


def test_runtime_state_writer_lock_failure_is_bounded(tmp_path: Path) -> None:
    initialize_runtime_state_store(runtime_root=tmp_path)

    with (
        closing(open_runtime_state_connection(runtime_root=tmp_path)) as first,
        closing(open_runtime_state_connection(runtime_root=tmp_path, busy_timeout_ms=1)) as second,
    ):
        with runtime_state_transaction(first):
            first.execute(
                """
                INSERT OR REPLACE INTO runtime_state_metadata (key, value, updated_at)
                VALUES ('writer', 'first', '2026-06-24T00:00:00Z')
                """,
            )
            with pytest.raises(sqlite3.OperationalError) as exc_info:
                with runtime_state_transaction(second):
                    second.execute(
                        """
                        INSERT OR REPLACE INTO runtime_state_metadata (key, value, updated_at)
                        VALUES ('writer', 'second', '2026-06-24T00:00:00Z')
                        """,
                    )

    diagnostic = runtime_state_error_diagnostic(exc_info.value, operation="write runtime state")
    assert diagnostic == {
        "status": "failed",
        "operation": "write runtime state",
        "error_type": "OperationalError",
        "message": "runtime state database is locked; retry after the current writer finishes.",
        "database_ref": ".halpha/state.sqlite",
        "private_values_embedded": False,
    }


def test_runtime_state_error_diagnostic_redacts_private_paths_and_values(tmp_path: Path) -> None:
    private_path = tmp_path / "private" / "state.sqlite"
    exc = sqlite3.OperationalError(
        f"unable to open database file at {private_path} with proxy http://127.0.0.1:7890 and token secret",
    )

    diagnostic = runtime_state_error_diagnostic(exc, operation=f"open {private_path}")
    diagnostic_text = repr(diagnostic)

    assert diagnostic == {
        "status": "failed",
        "operation": "runtime state operation",
        "error_type": "OperationalError",
        "message": "runtime state database could not be opened; verify runtime root permissions and retry.",
        "database_ref": ".halpha/state.sqlite",
        "private_values_embedded": False,
    }
    assert str(private_path) not in diagnostic_text
    assert "127.0.0.1" not in diagnostic_text
    assert "secret" not in diagnostic_text
