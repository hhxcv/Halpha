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
LIVE_TRIGGER_STATE_MIGRATION_VERSION = 18
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
LIVE_TRIGGER_STATE_MIGRATIONS = (
    StateStoreMigration(
        version=LIVE_TRIGGER_STATE_MIGRATION_VERSION,
        name="live_trigger_state",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS live_trigger_decisions (
              decision_id TEXT PRIMARY KEY,
              trigger_id TEXT NOT NULL,
              status TEXT NOT NULL,
              evaluated_at TEXT NOT NULL,
              source_data_types_json TEXT NOT NULL,
              source_refs_json TEXT NOT NULL,
              reason_codes_json TEXT NOT NULL,
              threshold_params_json TEXT NOT NULL,
              matched_evidence_json TEXT NOT NULL,
              cooldown_until TEXT,
              linked_collection_job_ids_json TEXT NOT NULL,
              linked_report_job_id TEXT,
              linked_report_job_status TEXT,
              linked_run_id TEXT,
              linked_report_ref TEXT,
              warnings_json TEXT NOT NULL,
              errors_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_live_trigger_decisions_trigger ON live_trigger_decisions(trigger_id, evaluated_at)",
            "CREATE INDEX IF NOT EXISTS idx_live_trigger_decisions_status ON live_trigger_decisions(status, evaluated_at)",
            "CREATE INDEX IF NOT EXISTS idx_live_trigger_decisions_report_job ON live_trigger_decisions(linked_report_job_id)",
            """
            CREATE TABLE IF NOT EXISTS live_trigger_cooldowns (
              trigger_id TEXT PRIMARY KEY,
              cooldown_until TEXT NOT NULL,
              decision_id TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """,
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
        persisted = self.get_state(target_key) or dict(state)
        for volatile_key in ("transport", "stream"):
            if volatile_key in state:
                persisted[volatile_key] = state[volatile_key]
        return persisted

    def _ensure_tables(self) -> None:
        with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
            apply_runtime_state_migrations(
                connection,
                migrations=(*RUNTIME_STATE_MIGRATIONS, *LIVE_COLLECTION_STATE_MIGRATIONS),
            )


@dataclass(frozen=True)
class LiveTriggerStateRepository:
    config_path: Path

    @property
    def database_path(self) -> Path:
        return runtime_state_path(config_path=self.config_path)

    def upsert_decision(self, decision: dict[str, Any]) -> dict[str, Any]:
        self._ensure_tables()
        decision_id = _required_decision_text(decision, "decision_id")
        try:
            with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
                with runtime_state_transaction(connection):
                    connection.execute(
                        """
                        INSERT OR REPLACE INTO live_trigger_decisions (
                          decision_id,
                          trigger_id,
                          status,
                          evaluated_at,
                          source_data_types_json,
                          source_refs_json,
                          reason_codes_json,
                          threshold_params_json,
                          matched_evidence_json,
                          cooldown_until,
                          linked_collection_job_ids_json,
                          linked_report_job_id,
                          linked_report_job_status,
                          linked_run_id,
                          linked_report_ref,
                          warnings_json,
                          errors_json,
                          updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            decision_id,
                            _required_decision_text(decision, "trigger_id"),
                            _required_decision_text(decision, "status"),
                            _required_decision_text(decision, "evaluated_at"),
                            _dumps_list(decision.get("source_data_types")),
                            _dumps_list(decision.get("source_refs")),
                            _dumps_list(decision.get("reason_codes")),
                            _dumps_mapping(decision.get("threshold_params")),
                            _dumps_mapping(decision.get("matched_evidence")),
                            _optional_str(decision.get("cooldown_until")),
                            _dumps_list(decision.get("linked_collection_job_ids")),
                            _optional_str(decision.get("linked_report_job_id")),
                            _optional_str(decision.get("linked_report_job_status")),
                            _optional_str(decision.get("linked_run_id")),
                            _optional_str(decision.get("linked_report_ref")),
                            _dumps_list(decision.get("warnings")),
                            _dumps_list(decision.get("errors")),
                            _required_decision_text(decision, "updated_at"),
                        ),
                    )
        except sqlite3.Error as exc:
            return _trigger_state_error(exc, operation="write Live trigger decision")
        return self.get_decision(decision_id) or dict(decision)

    def get_decision(self, decision_id: str) -> dict[str, Any] | None:
        self._ensure_tables()
        try:
            with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
                row = connection.execute(
                    """
                    SELECT *
                    FROM live_trigger_decisions
                    WHERE decision_id = ?
                    """,
                    (decision_id,),
                ).fetchone()
        except sqlite3.Error as exc:
            return _trigger_state_error(exc, operation="read Live trigger decision")
        return _row_to_trigger_decision(row) if row else None

    def list_decisions(self, *, limit: int = 100) -> list[dict[str, Any]]:
        self._ensure_tables()
        try:
            with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM live_trigger_decisions
                    ORDER BY evaluated_at DESC, decision_id DESC
                    LIMIT ?
                    """,
                    (max(1, int(limit)),),
                ).fetchall()
        except (sqlite3.Error, ValueError) as exc:
            if isinstance(exc, sqlite3.Error):
                return [_trigger_state_error(exc, operation="list Live trigger decisions")]
            return []
        return [_row_to_trigger_decision(row) for row in rows]

    def latest_decisions(self) -> dict[str, dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for decision in self.list_decisions(limit=500):
            trigger_id = str(decision.get("trigger_id") or "")
            if not trigger_id or trigger_id in latest:
                continue
            latest[trigger_id] = decision
        return latest

    def get_cooldown(self, trigger_id: str) -> dict[str, Any] | None:
        self._ensure_tables()
        try:
            with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
                row = connection.execute(
                    """
                    SELECT trigger_id, cooldown_until, decision_id, updated_at
                    FROM live_trigger_cooldowns
                    WHERE trigger_id = ?
                    """,
                    (trigger_id,),
                ).fetchone()
        except sqlite3.Error as exc:
            return _trigger_state_error(exc, operation="read Live trigger cooldown")
        return _row_to_cooldown(row) if row else None

    def list_cooldowns(self) -> list[dict[str, Any]]:
        self._ensure_tables()
        try:
            with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
                rows = connection.execute(
                    """
                    SELECT trigger_id, cooldown_until, decision_id, updated_at
                    FROM live_trigger_cooldowns
                    ORDER BY trigger_id
                    """
                ).fetchall()
        except sqlite3.Error as exc:
            return [_trigger_state_error(exc, operation="list Live trigger cooldowns")]
        return [_row_to_cooldown(row) for row in rows]

    def upsert_cooldown(
        self,
        *,
        trigger_id: str,
        cooldown_until: str,
        decision_id: str,
        updated_at: str,
    ) -> dict[str, Any]:
        self._ensure_tables()
        try:
            with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
                with runtime_state_transaction(connection):
                    connection.execute(
                        """
                        INSERT OR REPLACE INTO live_trigger_cooldowns (
                          trigger_id,
                          cooldown_until,
                          decision_id,
                          updated_at
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (trigger_id, cooldown_until, decision_id, updated_at),
                    )
        except sqlite3.Error as exc:
            return _trigger_state_error(exc, operation="write Live trigger cooldown")
        return self.get_cooldown(trigger_id) or {
            "trigger_id": trigger_id,
            "cooldown_until": cooldown_until,
            "decision_id": decision_id,
            "updated_at": updated_at,
        }

    def _ensure_tables(self) -> None:
        with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
            apply_runtime_state_migrations(
                connection,
                migrations=(
                    *RUNTIME_STATE_MIGRATIONS,
                    *LIVE_COLLECTION_STATE_MIGRATIONS,
                    *LIVE_TRIGGER_STATE_MIGRATIONS,
                ),
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


def _row_to_trigger_decision(row: Any) -> dict[str, Any]:
    return {
        "decision_id": row[0],
        "trigger_id": row[1],
        "status": row[2],
        "evaluated_at": row[3],
        "source_data_types": _loads_list(row[4]),
        "source_refs": _loads_list(row[5]),
        "reason_codes": _loads_list(row[6]),
        "threshold_params": _loads_mapping(row[7]),
        "matched_evidence": _loads_mapping(row[8]),
        "cooldown_until": row[9],
        "linked_collection_job_ids": _loads_list(row[10]),
        "linked_report_job_id": row[11],
        "linked_report_job_status": row[12],
        "linked_run_id": row[13],
        "linked_report_ref": row[14],
        "warnings": _loads_list(row[15]),
        "errors": _loads_list(row[16]),
        "updated_at": row[17],
    }


def _row_to_cooldown(row: Any) -> dict[str, Any]:
    return {
        "trigger_id": row[0],
        "cooldown_until": row[1],
        "decision_id": row[2],
        "updated_at": row[3],
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


def _trigger_state_error(exc: sqlite3.Error, *, operation: str) -> dict[str, Any]:
    diagnostic = runtime_state_error_diagnostic(exc, operation=operation)
    return {
        "decision_id": "__live_trigger_state_error__",
        "trigger_id": "live",
        "status": "failed",
        "evaluated_at": "",
        "source_data_types": [],
        "source_refs": [],
        "reason_codes": ["runtime_state_error"],
        "threshold_params": {},
        "matched_evidence": {},
        "cooldown_until": None,
        "linked_collection_job_ids": [],
        "linked_report_job_id": None,
        "linked_report_job_status": None,
        "linked_run_id": None,
        "linked_report_ref": None,
        "warnings": [],
        "errors": [diagnostic.get("message") or "Live trigger runtime state could not be read."],
        "updated_at": "",
        "diagnostic": diagnostic,
    }


def _required_text(state: dict[str, Any], key: str) -> str:
    value = state.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Live collection state requires {key}.")
    return value.strip()


def _required_decision_text(state: dict[str, Any], key: str) -> str:
    value = state.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Live trigger decision requires {key}.")
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
