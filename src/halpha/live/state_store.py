from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import json
import sqlite3
from pathlib import Path
from typing import Any

from halpha.runtime.state_store import (
    RUNTIME_STATE_MIGRATIONS,
    StateStoreMigration,
    apply_runtime_state_migrations,
    open_runtime_state_connection,
    runtime_state_error_diagnostic,
    runtime_state_path,
    runtime_state_transaction,
)


LIVE_COLLECTION_STATE_MIGRATION_VERSION = 17
LIVE_COLLECTION_STATE_MIGRATIONS = (
    StateStoreMigration(
        version=LIVE_COLLECTION_STATE_MIGRATION_VERSION,
        name="live_collection_state",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS live_collection_state (
              target_key TEXT PRIMARY KEY,
              data_type TEXT NOT NULL,
              target_json TEXT NOT NULL,
              enabled INTEGER NOT NULL,
              cadence_seconds INTEGER,
              lookback_seconds INTEGER,
              lookahead_seconds INTEGER,
              last_attempt_at TEXT,
              last_success_at TEXT,
              next_attempt_at TEXT,
              latest_job_id TEXT,
              latest_job_status TEXT,
              latest_terminal_job_id TEXT,
              latest_terminal_status TEXT,
              consecutive_failures INTEGER NOT NULL,
              source_refs_json TEXT NOT NULL,
              warnings_json TEXT NOT NULL,
              errors_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_live_collection_state_type ON live_collection_state(data_type, target_key)",
            "CREATE INDEX IF NOT EXISTS idx_live_collection_state_next_attempt ON live_collection_state(next_attempt_at)",
        ),
    ),
)


@dataclass(frozen=True)
class LiveCollectionStateRepository:
    config_path: Path

    @property
    def database_path(self) -> Path:
        return runtime_state_path(config_path=self.config_path)

    def get_state(self, target_key: str) -> dict[str, Any] | None:
        self._ensure_tables()
        try:
            with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
                row = connection.execute(
                    """
                    SELECT *
                    FROM live_collection_state
                    WHERE target_key = ?
                    """,
                    (target_key,),
                ).fetchone()
        except sqlite3.Error as exc:
            return _state_error(exc, operation="read Live collection state")
        return _row_to_state(row) if row else None

    def list_states(self) -> list[dict[str, Any]]:
        self._ensure_tables()
        try:
            with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM live_collection_state
                    ORDER BY data_type, target_key
                    """
                ).fetchall()
        except sqlite3.Error as exc:
            diagnostic = _state_error(exc, operation="list Live collection states")
            return [diagnostic]
        return [_row_to_state(row) for row in rows]

    def upsert_state(self, state: dict[str, Any]) -> dict[str, Any]:
        self._ensure_tables()
        target_key = _required_text(state, "target_key")
        try:
            with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
                with runtime_state_transaction(connection):
                    connection.execute(
                        """
                        INSERT OR REPLACE INTO live_collection_state (
                          target_key,
                          data_type,
                          target_json,
                          enabled,
                          cadence_seconds,
                          lookback_seconds,
                          lookahead_seconds,
                          last_attempt_at,
                          last_success_at,
                          next_attempt_at,
                          latest_job_id,
                          latest_job_status,
                          latest_terminal_job_id,
                          latest_terminal_status,
                          consecutive_failures,
                          source_refs_json,
                          warnings_json,
                          errors_json,
                          updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            target_key,
                            _required_text(state, "data_type"),
                            _dumps_mapping(state.get("target")),
                            1 if state.get("enabled") is True else 0,
                            _optional_int(state.get("cadence_seconds")),
                            _optional_int(state.get("lookback_seconds")),
                            _optional_int(state.get("lookahead_seconds")),
                            _optional_str(state.get("last_attempt_at")),
                            _optional_str(state.get("last_success_at")),
                            _optional_str(state.get("next_attempt_at")),
                            _optional_str(state.get("latest_job_id")),
                            _optional_str(state.get("latest_job_status")),
                            _optional_str(state.get("latest_terminal_job_id")),
                            _optional_str(state.get("latest_terminal_status")),
                            _int(state.get("consecutive_failures")),
                            _dumps_list(state.get("source_refs")),
                            _dumps_list(state.get("warnings")),
                            _dumps_list(state.get("errors")),
                            _required_text(state, "updated_at"),
                        ),
                    )
        except sqlite3.Error as exc:
            return _state_error(exc, operation="write Live collection state")
        return self.get_state(target_key) or dict(state)

    def _ensure_tables(self) -> None:
        with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
            apply_runtime_state_migrations(
                connection,
                migrations=(*RUNTIME_STATE_MIGRATIONS, *LIVE_COLLECTION_STATE_MIGRATIONS),
            )


def _row_to_state(row: Any) -> dict[str, Any]:
    return {
        "target_key": row[0],
        "data_type": row[1],
        "target": _loads_mapping(row[2]),
        "enabled": bool(row[3]),
        "cadence_seconds": row[4],
        "lookback_seconds": row[5],
        "lookahead_seconds": row[6],
        "last_attempt_at": row[7],
        "last_success_at": row[8],
        "next_attempt_at": row[9],
        "latest_job_id": row[10],
        "latest_job_status": row[11],
        "latest_terminal_job_id": row[12],
        "latest_terminal_status": row[13],
        "consecutive_failures": int(row[14] or 0),
        "source_refs": _loads_list(row[15]),
        "warnings": _loads_list(row[16]),
        "errors": _loads_list(row[17]),
        "updated_at": row[18],
    }


def _state_error(exc: sqlite3.Error, *, operation: str) -> dict[str, Any]:
    diagnostic = runtime_state_error_diagnostic(exc, operation=operation)
    return {
        "target_key": "__live_state_error__",
        "data_type": "live",
        "target": {},
        "enabled": False,
        "cadence_seconds": None,
        "lookback_seconds": None,
        "lookahead_seconds": None,
        "last_attempt_at": None,
        "last_success_at": None,
        "next_attempt_at": None,
        "latest_job_id": None,
        "latest_job_status": "failed",
        "latest_terminal_job_id": None,
        "latest_terminal_status": "failed",
        "consecutive_failures": 1,
        "source_refs": [],
        "warnings": [],
        "errors": [diagnostic.get("message") or "Live runtime state could not be read."],
        "updated_at": "",
        "diagnostic": diagnostic,
    }


def _required_text(state: dict[str, Any], key: str) -> str:
    value = state.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Live collection state requires {key}.")
    return value.strip()


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _dumps_mapping(value: Any) -> str:
    return json.dumps(value if isinstance(value, dict) else {}, ensure_ascii=True, sort_keys=True)


def _dumps_list(value: Any) -> str:
    return json.dumps(value if isinstance(value, list) else [], ensure_ascii=True)


def _loads_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, str) or not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _loads_list(value: Any) -> list[Any]:
    if not isinstance(value, str) or not value:
        return []
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return []
    return loaded if isinstance(loaded, list) else []
