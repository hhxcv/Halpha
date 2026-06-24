from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import sqlite3
from pathlib import Path
from typing import Any, Callable

from halpha.runtime.state_store import (
    RUNTIME_STATE_MIGRATIONS,
    STATE_STORE_REF,
    StateStoreMigration,
    apply_runtime_state_migrations,
    open_runtime_state_connection,
    runtime_state_path,
    runtime_state_transaction,
)


MONITOR_STATE_STORE_ARTIFACT = STATE_STORE_REF
MONITOR_STATE_SCHEMA_VERSION = 1
MONITOR_STATE_MIGRATION_VERSION = 5
MONITOR_ALERT_SAMPLE_LIMIT = 20
MONITOR_CYCLE_HISTORY_LIMIT = 20
ALERT_COUNT_KEYS = (
    "records",
    "emitted",
    "suppressed_duplicate",
    "suppressed_cooldown",
    "suppressed_no_alert",
    "skipped",
)
FAILED_MONITOR_STATUSES = {"failed", "error"}


class MonitorStateStoreError(Exception):
    pass


@dataclass(frozen=True)
class MonitorArchivePersistence:
    summary: dict[str, Any]
    records: list[dict[str, Any]]
    cooldown_records: dict[str, dict[str, Any]]


ArchiveBuilder = Callable[[dict[str, dict[str, Any]]], MonitorArchivePersistence]


MONITOR_STATE_MIGRATIONS = (
    StateStoreMigration(
        version=MONITOR_STATE_MIGRATION_VERSION,
        name="monitor_state",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS monitor_cycles (
              cycle_id TEXT PRIMARY KEY,
              monitor_output_dir TEXT NOT NULL,
              cycle_manifest TEXT NOT NULL,
              cycle_mode TEXT NOT NULL,
              loop_id TEXT,
              cycle_sequence INTEGER,
              trigger_source TEXT NOT NULL,
              status TEXT NOT NULL,
              started_at TEXT NOT NULL,
              finished_at TEXT,
              config_ref TEXT NOT NULL,
              target_stage TEXT NOT NULL,
              no_codex INTEGER NOT NULL,
              exit_code INTEGER,
              run_id TEXT,
              run_dir TEXT,
              run_manifest TEXT,
              product_run_json TEXT NOT NULL,
              source_artifacts_json TEXT NOT NULL,
              alert_archive_status TEXT NOT NULL,
              alert_counts_json TEXT NOT NULL,
              warning_count INTEGER NOT NULL,
              error_count INTEGER NOT NULL,
              warnings_json TEXT NOT NULL,
              errors_json TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS monitor_alert_records (
              record_id TEXT PRIMARY KEY,
              cycle_id TEXT NOT NULL,
              monitor_output_dir TEXT NOT NULL,
              created_at TEXT NOT NULL,
              status TEXT NOT NULL,
              alert_key TEXT NOT NULL,
              decision_id TEXT NOT NULL,
              symbol TEXT NOT NULL,
              timeframe TEXT NOT NULL,
              priority TEXT NOT NULL,
              attention_decision TEXT NOT NULL,
              requires_user_attention INTEGER NOT NULL,
              suppression_reasons_json TEXT NOT NULL,
              cooldown_until TEXT,
              source_artifacts_json TEXT NOT NULL,
              personalized_context_json TEXT NOT NULL,
              source_run_json TEXT NOT NULL,
              FOREIGN KEY (cycle_id) REFERENCES monitor_cycles(cycle_id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS monitor_alert_cooldowns (
              monitor_output_dir TEXT NOT NULL,
              alert_key TEXT NOT NULL,
              cooldown_until TEXT NOT NULL,
              last_emitted_at TEXT,
              last_record_id TEXT,
              decision_id TEXT,
              priority TEXT,
              attention_decision TEXT,
              source_artifacts_json TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              PRIMARY KEY (monitor_output_dir, alert_key)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS monitor_loops (
              loop_id TEXT PRIMARY KEY,
              monitor_output_dir TEXT NOT NULL,
              status TEXT NOT NULL,
              max_cycles INTEGER NOT NULL,
              completed_cycles INTEGER NOT NULL,
              stop_reason TEXT NOT NULL,
              started_at TEXT NOT NULL,
              finished_at TEXT NOT NULL,
              latest_cycle_id TEXT,
              reason TEXT,
              updated_at TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_monitor_cycles_output_time ON monitor_cycles(monitor_output_dir, finished_at, started_at, cycle_id)",
            "CREATE INDEX IF NOT EXISTS idx_monitor_alert_records_output_time ON monitor_alert_records(monitor_output_dir, created_at, record_id)",
            "CREATE INDEX IF NOT EXISTS idx_monitor_alert_records_cycle ON monitor_alert_records(cycle_id, record_id)",
            "CREATE INDEX IF NOT EXISTS idx_monitor_cooldowns_output_until ON monitor_alert_cooldowns(monitor_output_dir, cooldown_until, alert_key)",
            "CREATE INDEX IF NOT EXISTS idx_monitor_loops_output_time ON monitor_loops(monitor_output_dir, finished_at, started_at, loop_id)",
        ),
    ),
)


class MonitorStateRepository:
    def __init__(self, *, config_path: Path) -> None:
        self.config_path = Path(config_path)
        self.database_path = runtime_state_path(config_path=self.config_path)

    def persist_cycle_with_archive_builder(
        self,
        cycle: dict[str, Any],
        *,
        build_archive: ArchiveBuilder,
        updated_at: str,
    ) -> dict[str, Any]:
        cycle_id = _required_str(cycle.get("cycle_id"), "monitor cycle_id is required.")
        monitor_output_dir = _required_str(cycle.get("monitor_output_dir"), "monitor output dir is required.")
        try:
            with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
                apply_monitor_state_migrations(connection, now=updated_at)
                with runtime_state_transaction(connection):
                    existing = self._cycle_for_update(connection, cycle_id)
                    if existing and existing.get("status") != "running":
                        return _archive_summary_from_cycle(existing)
                    cooldown_records = self._cooldown_records_for_update(connection, monitor_output_dir)
                    archive = build_archive(cooldown_records)
                    self._replace_cycle(
                        connection,
                        {**cycle, "alert_archive": archive.summary, "updated_at": updated_at},
                    )
                    self._insert_alert_records(connection, archive.records, monitor_output_dir=monitor_output_dir)
                    self._replace_cooldowns(
                        connection,
                        archive.cooldown_records,
                        monitor_output_dir=monitor_output_dir,
                        updated_at=updated_at,
                    )
                    return archive.summary
        except sqlite3.Error as exc:
            raise MonitorStateStoreError("monitor state store could not persist cycle state.") from exc

    def save_cycle(self, cycle: dict[str, Any], *, updated_at: str) -> dict[str, Any]:
        cycle_id = _required_str(cycle.get("cycle_id"), "monitor cycle_id is required.")
        try:
            with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
                apply_monitor_state_migrations(connection, now=updated_at)
                with runtime_state_transaction(connection):
                    self._replace_cycle(connection, {**cycle, "updated_at": updated_at})
        except sqlite3.Error as exc:
            raise MonitorStateStoreError("monitor state store could not persist cycle state.") from exc
        return self.get_cycle(cycle_id) or dict(cycle)

    def save_loop(self, loop: dict[str, Any], *, monitor_output_dir: str, updated_at: str) -> None:
        loop_id = _required_str(loop.get("loop_id"), "monitor loop_id is required.")
        try:
            with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
                apply_monitor_state_migrations(connection, now=updated_at)
                with runtime_state_transaction(connection):
                    connection.execute(
                        """
                        INSERT OR REPLACE INTO monitor_loops (
                          loop_id,
                          monitor_output_dir,
                          status,
                          max_cycles,
                          completed_cycles,
                          stop_reason,
                          started_at,
                          finished_at,
                          latest_cycle_id,
                          reason,
                          updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            loop_id,
                            monitor_output_dir,
                            str(loop.get("status") or "unknown"),
                            _int(loop.get("max_cycles")),
                            _int(loop.get("completed_cycles")),
                            str(loop.get("stop_reason") or "unknown"),
                            str(loop.get("started_at") or updated_at),
                            str(loop.get("finished_at") or updated_at),
                            _optional_str(loop.get("latest_cycle_id")),
                            _optional_str(loop.get("reason")),
                            updated_at,
                        ),
                    )
        except sqlite3.Error as exc:
            raise MonitorStateStoreError("monitor state store could not persist loop state.") from exc

    def get_cycle(self, cycle_id: str, *, base: Path | None = None) -> dict[str, Any] | None:
        if not self.database_path.exists():
            return None
        try:
            with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
                apply_monitor_state_migrations(connection)
                row = connection.execute(
                    """
                    SELECT *
                    FROM monitor_cycles
                    WHERE cycle_id = ?
                    """,
                    (cycle_id,),
                ).fetchone()
        except sqlite3.Error:
            return None
        return _row_to_cycle(row, base=base) if row else None

    def health_state(self, *, monitor_output_dir: str, base: Path) -> dict[str, Any]:
        empty_counts = _empty_alert_counts()
        if not self.database_path.exists():
            return {
                "schema_version": MONITOR_STATE_SCHEMA_VERSION,
                "artifact_type": "monitor_health_state",
                "status": "missing",
                "health_state_path": MONITOR_STATE_STORE_ARTIFACT,
                "monitor_output_dir": monitor_output_dir,
                "cycle_count": 0,
                "failed_cycle_count": 0,
                "latest_cycle_id": "none",
                "latest_cycle_status": "missing",
                "latest_run_id": "none",
                "latest_run_manifest": "none",
                "latest_cycle_manifest": "none",
                "alert_archive_status": "missing",
                "alert_counts": empty_counts,
                "cooldown_records": 0,
                "warning_count": 0,
                "error_count": 0,
                "latest_loop": {},
                "source_artifacts": [MONITOR_STATE_STORE_ARTIFACT],
                "warnings": ["monitor state store was not found."],
                "errors": [],
            }
        try:
            with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
                apply_monitor_state_migrations(connection)
                cycle_count = _count_cycles(connection, monitor_output_dir)
                failed_cycle_count = _count_failed_cycles(connection, monitor_output_dir)
                latest_row = _latest_cycle_row(connection, monitor_output_dir)
                latest_cycle = _row_to_cycle(latest_row, base=base) if latest_row else None
                alert_counts = _alert_counts(connection, monitor_output_dir)
                cooldown_count = _cooldown_count(connection, monitor_output_dir)
                warning_count, error_count = _health_issue_counts(connection, monitor_output_dir, base=base)
                latest_loop = _latest_loop(connection, monitor_output_dir)
        except sqlite3.Error:
            return {
                "schema_version": MONITOR_STATE_SCHEMA_VERSION,
                "artifact_type": "monitor_health_state",
                "status": "failed",
                "health_state_path": MONITOR_STATE_STORE_ARTIFACT,
                "monitor_output_dir": monitor_output_dir,
                "cycle_count": 0,
                "failed_cycle_count": 0,
                "latest_cycle_id": "none",
                "latest_cycle_status": "failed",
                "latest_run_id": "none",
                "latest_run_manifest": "none",
                "latest_cycle_manifest": "none",
                "alert_archive_status": "failed",
                "alert_counts": empty_counts,
                "cooldown_records": 0,
                "warning_count": 0,
                "error_count": 1,
                "latest_loop": {},
                "source_artifacts": [MONITOR_STATE_STORE_ARTIFACT],
                "warnings": [],
                "errors": ["monitor state store could not be read."],
            }

        if latest_cycle is None:
            return {
                "schema_version": MONITOR_STATE_SCHEMA_VERSION,
                "artifact_type": "monitor_health_state",
                "status": "missing",
                "health_state_path": MONITOR_STATE_STORE_ARTIFACT,
                "monitor_output_dir": monitor_output_dir,
                "cycle_count": 0,
                "failed_cycle_count": 0,
                "latest_cycle_id": "none",
                "latest_cycle_status": "missing",
                "latest_run_id": "none",
                "latest_run_manifest": "none",
                "latest_cycle_manifest": "none",
                "alert_archive_status": "missing",
                "alert_counts": empty_counts,
                "cooldown_records": cooldown_count,
                "warning_count": 0,
                "error_count": 0,
                "latest_loop": latest_loop,
                "source_artifacts": [MONITOR_STATE_STORE_ARTIFACT],
                "warnings": ["monitor cycle records were not found."],
                "errors": [],
            }

        status = _health_status(
            latest_cycle_status=str(latest_cycle.get("status") or "missing"),
            latest_loop_status=str(latest_loop.get("status") or ""),
            warning_count=warning_count,
            error_count=error_count,
            failed_cycle_count=failed_cycle_count,
        )
        return {
            "schema_version": MONITOR_STATE_SCHEMA_VERSION,
            "artifact_type": "monitor_health_state",
            "status": status,
            "health_state_path": MONITOR_STATE_STORE_ARTIFACT,
            "monitor_output_dir": monitor_output_dir,
            "cycle_count": cycle_count,
            "failed_cycle_count": failed_cycle_count,
            "latest_cycle_id": latest_cycle.get("cycle_id") or "none",
            "latest_cycle_status": latest_cycle.get("status") or "missing",
            "latest_run_id": latest_cycle.get("run_id") or "none",
            "latest_run_manifest": latest_cycle.get("run_manifest") or "none",
            "latest_cycle_manifest": latest_cycle.get("cycle_manifest") or "none",
            "alert_archive_status": latest_cycle.get("alert_archive", {}).get("status") or "missing",
            "alert_counts": alert_counts,
            "cooldown_records": cooldown_count,
            "warning_count": warning_count,
            "error_count": error_count,
            "latest_loop": latest_loop,
            "source_artifacts": _unique_strings(
                [
                    MONITOR_STATE_STORE_ARTIFACT,
                    _optional_str(latest_cycle.get("cycle_manifest")),
                    _optional_str(latest_cycle.get("run_manifest")),
                ]
            ),
            "warnings": _list(latest_cycle.get("warnings")),
            "errors": _list(latest_cycle.get("errors")),
        }

    def list_cycles(self, *, monitor_output_dir: str, base: Path, limit: int = MONITOR_CYCLE_HISTORY_LIMIT) -> dict[str, Any]:
        if not self.database_path.exists():
            return {
                "schema_version": MONITOR_STATE_SCHEMA_VERSION,
                "artifact_type": "dashboard_monitor_cycles",
                "status": "missing",
                "cycles": [],
                "cycle_count": 0,
                "omitted_count": 0,
                "source_artifacts": [MONITOR_STATE_STORE_ARTIFACT],
                "warnings": ["monitor state store was not found."],
                "errors": [],
            }
        try:
            with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
                apply_monitor_state_migrations(connection)
                total = _count_cycles(connection, monitor_output_dir)
                rows = connection.execute(
                    """
                    SELECT *
                    FROM monitor_cycles
                    WHERE monitor_output_dir = ?
                    ORDER BY COALESCE(finished_at, started_at, '') DESC, cycle_id DESC
                    LIMIT ?
                    """,
                    (monitor_output_dir, max(0, limit)),
                ).fetchall()
        except sqlite3.Error:
            return {
                "schema_version": MONITOR_STATE_SCHEMA_VERSION,
                "artifact_type": "dashboard_monitor_cycles",
                "status": "failed",
                "cycles": [],
                "cycle_count": 0,
                "omitted_count": 0,
                "source_artifacts": [MONITOR_STATE_STORE_ARTIFACT],
                "warnings": [],
                "errors": ["monitor cycle records could not be read."],
            }
        cycles = [_row_to_cycle(row, base=base) for row in rows]
        return {
            "schema_version": MONITOR_STATE_SCHEMA_VERSION,
            "artifact_type": "dashboard_monitor_cycles",
            "status": _overall_status([_cycle_component_status(cycle) for cycle in cycles]),
            "cycles": cycles,
            "cycle_count": total,
            "omitted_count": max(0, total - len(cycles)),
            "source_artifacts": _unique_strings(
                [MONITOR_STATE_STORE_ARTIFACT, *(str(cycle.get("cycle_manifest") or "") for cycle in cycles)]
            ),
            "warnings": _bounded_messages(cycles, key="warnings"),
            "errors": _bounded_messages(cycles, key="errors"),
        }

    def alert_summary(
        self,
        *,
        monitor_output_dir: str,
        limit: int = MONITOR_ALERT_SAMPLE_LIMIT,
    ) -> dict[str, Any]:
        if not self.database_path.exists():
            return _alert_component(
                "missing",
                counts=_empty_alert_counts(),
                records=[],
                truncated=False,
                warnings=["monitor state store was not found."],
            )
        try:
            with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
                apply_monitor_state_migrations(connection)
                counts = _alert_counts(connection, monitor_output_dir)
                rows = connection.execute(
                    """
                    SELECT *
                    FROM monitor_alert_records
                    WHERE monitor_output_dir = ?
                    ORDER BY created_at ASC, record_id ASC
                    LIMIT ?
                    """,
                    (monitor_output_dir, max(0, limit)),
                ).fetchall()
                total = counts["records"]
        except sqlite3.Error:
            return _alert_component(
                "failed",
                counts=_empty_alert_counts(),
                records=[],
                truncated=False,
                errors=["monitor alert records could not be read."],
            )
        records = [_row_to_alert_record(row) for row in rows]
        return _alert_component(
            "available" if total else "missing",
            counts=counts,
            records=records,
            truncated=total > len(records),
            warnings=[] if total else ["monitor alert records were not found."],
        )

    def cooldown_summary(self, *, monitor_output_dir: str, now: datetime | str | None = None) -> dict[str, Any]:
        if not self.database_path.exists():
            return _cooldown_component("missing", warnings=["monitor state store was not found."])
        timestamp = _format_utc(now)
        try:
            with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
                apply_monitor_state_migrations(connection)
                row = connection.execute(
                    """
                    SELECT
                      COUNT(*) AS total,
                      SUM(CASE WHEN cooldown_until > ? THEN 1 ELSE 0 END) AS active,
                      SUM(CASE WHEN cooldown_until <= ? THEN 1 ELSE 0 END) AS expired,
                      MAX(updated_at) AS updated_at
                    FROM monitor_alert_cooldowns
                    WHERE monitor_output_dir = ?
                    """,
                    (timestamp, timestamp, monitor_output_dir),
                ).fetchone()
        except sqlite3.Error:
            return _cooldown_component("failed", errors=["monitor cooldown records could not be read."])
        total = _int(row[0]) if row else 0
        return _cooldown_component(
            "available" if total else "missing",
            fields={
                "artifact": MONITOR_STATE_STORE_ARTIFACT,
                "artifact_type": "monitor_alert_cooldown_state",
                "updated_at": row[3] if row else None,
                "record_count": total,
                "active_record_count": _int(row[1]) if row else 0,
                "expired_record_count": _int(row[2]) if row else 0,
                "state_path": MONITOR_STATE_STORE_ARTIFACT,
            },
            warnings=[] if total else ["monitor cooldown records were not found."],
        )

    def _cycle_for_update(self, connection: sqlite3.Connection, cycle_id: str) -> dict[str, Any] | None:
        row = connection.execute(
            """
            SELECT *
            FROM monitor_cycles
            WHERE cycle_id = ?
            """,
            (cycle_id,),
        ).fetchone()
        return _row_to_cycle(row) if row else None

    def _cooldown_records_for_update(
        self,
        connection: sqlite3.Connection,
        monitor_output_dir: str,
    ) -> dict[str, dict[str, Any]]:
        rows = connection.execute(
            """
            SELECT
              alert_key,
              cooldown_until,
              last_emitted_at,
              last_record_id,
              decision_id,
              priority,
              attention_decision,
              source_artifacts_json
            FROM monitor_alert_cooldowns
            WHERE monitor_output_dir = ?
            """,
            (monitor_output_dir,),
        ).fetchall()
        records: dict[str, dict[str, Any]] = {}
        for row in rows:
            alert_key = str(row[0] or "")
            if not alert_key:
                continue
            records[alert_key] = {
                "alert_key": alert_key,
                "cooldown_until": row[1],
                "last_emitted_at": row[2],
                "last_record_id": row[3],
                "decision_id": row[4],
                "priority": row[5],
                "attention_decision": row[6],
                "source_artifacts": _loads_list(row[7]),
            }
        return records

    def _replace_cycle(self, connection: sqlite3.Connection, cycle: dict[str, Any]) -> None:
        archive = cycle.get("alert_archive") if isinstance(cycle.get("alert_archive"), dict) else {}
        alert_counts = _alert_counts_mapping(archive.get("counts"))
        warnings = _bounded_strings(cycle.get("warnings"), limit=40)
        errors = _bounded_strings(cycle.get("errors"), limit=40)
        archive_warnings = _bounded_strings(archive.get("warnings"), limit=40)
        archive_errors = _bounded_strings(archive.get("errors"), limit=40)
        connection.execute(
            """
            INSERT OR REPLACE INTO monitor_cycles (
              cycle_id,
              monitor_output_dir,
              cycle_manifest,
              cycle_mode,
              loop_id,
              cycle_sequence,
              trigger_source,
              status,
              started_at,
              finished_at,
              config_ref,
              target_stage,
              no_codex,
              exit_code,
              run_id,
              run_dir,
              run_manifest,
              product_run_json,
              source_artifacts_json,
              alert_archive_status,
              alert_counts_json,
              warning_count,
              error_count,
              warnings_json,
              errors_json,
              created_at,
              updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _required_str(cycle.get("cycle_id"), "monitor cycle_id is required."),
                _required_str(cycle.get("monitor_output_dir"), "monitor output dir is required."),
                _required_str(cycle.get("cycle_manifest"), "monitor cycle manifest ref is required."),
                str(cycle.get("cycle_mode") or "once"),
                _optional_str(cycle.get("loop_id")),
                _optional_int(cycle.get("cycle_sequence")),
                str(cycle.get("trigger_source") or "cli"),
                str(cycle.get("status") or "unknown"),
                str(cycle.get("started_at") or cycle.get("updated_at") or ""),
                _optional_str(cycle.get("finished_at")),
                str(cycle.get("config_ref") or ""),
                str(cycle.get("target_stage") or ""),
                1 if cycle.get("no_codex") is True else 0,
                _optional_int(cycle.get("exit_code")),
                _optional_str(cycle.get("run_id")),
                _optional_str(cycle.get("run_dir")),
                _optional_str(cycle.get("run_manifest")),
                _dumps_mapping(cycle.get("product_run")),
                _dumps_mapping(cycle.get("source_artifacts")),
                str(archive.get("status") or "skipped"),
                _dumps_mapping(alert_counts),
                len(warnings) + len(archive_warnings),
                len(errors) + len(archive_errors),
                _dumps_list(_unique_strings([*warnings, *archive_warnings])),
                _dumps_list(_unique_strings([*errors, *archive_errors])),
                str(cycle.get("started_at") or cycle.get("updated_at") or ""),
                str(cycle.get("updated_at") or cycle.get("finished_at") or cycle.get("started_at") or ""),
            ),
        )

    def _insert_alert_records(
        self,
        connection: sqlite3.Connection,
        records: list[dict[str, Any]],
        *,
        monitor_output_dir: str,
    ) -> None:
        for record in records:
            connection.execute(
                """
                INSERT OR IGNORE INTO monitor_alert_records (
                  record_id,
                  cycle_id,
                  monitor_output_dir,
                  created_at,
                  status,
                  alert_key,
                  decision_id,
                  symbol,
                  timeframe,
                  priority,
                  attention_decision,
                  requires_user_attention,
                  suppression_reasons_json,
                  cooldown_until,
                  source_artifacts_json,
                  personalized_context_json,
                  source_run_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _required_str(record.get("record_id"), "monitor alert record_id is required."),
                    _required_str(record.get("cycle_id"), "monitor alert cycle_id is required."),
                    monitor_output_dir,
                    str(record.get("created_at") or ""),
                    str(record.get("status") or "unknown"),
                    str(record.get("alert_key") or ""),
                    str(record.get("decision_id") or "unknown"),
                    str(record.get("symbol") or "unknown"),
                    str(record.get("timeframe") or "unknown"),
                    str(record.get("priority") or "unknown"),
                    str(record.get("attention_decision") or "unknown"),
                    1 if record.get("requires_user_attention") is True else 0,
                    _dumps_list(record.get("suppression_reasons")),
                    _optional_str(record.get("cooldown_until")),
                    _dumps_list(record.get("source_artifacts")),
                    _dumps_mapping(record.get("personalized_context")),
                    _dumps_mapping(record.get("source_run")),
                ),
            )

    def _replace_cooldowns(
        self,
        connection: sqlite3.Connection,
        records: dict[str, dict[str, Any]],
        *,
        monitor_output_dir: str,
        updated_at: str,
    ) -> None:
        for alert_key, record in sorted(records.items()):
            cooldown_until = _optional_str(record.get("cooldown_until"))
            if not alert_key or cooldown_until is None:
                continue
            connection.execute(
                """
                INSERT OR REPLACE INTO monitor_alert_cooldowns (
                  monitor_output_dir,
                  alert_key,
                  cooldown_until,
                  last_emitted_at,
                  last_record_id,
                  decision_id,
                  priority,
                  attention_decision,
                  source_artifacts_json,
                  updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    monitor_output_dir,
                    alert_key,
                    cooldown_until,
                    _optional_str(record.get("last_emitted_at")),
                    _optional_str(record.get("last_record_id")),
                    _optional_str(record.get("decision_id")),
                    _optional_str(record.get("priority")),
                    _optional_str(record.get("attention_decision")),
                    _dumps_list(record.get("source_artifacts")),
                    updated_at,
                ),
            )


def apply_monitor_state_migrations(connection: sqlite3.Connection, *, now: datetime | str | None = None) -> None:
    apply_runtime_state_migrations(
        connection,
        migrations=RUNTIME_STATE_MIGRATIONS + MONITOR_STATE_MIGRATIONS,
        now=now,
    )


def _row_to_cycle(row: Any, *, base: Path | None = None) -> dict[str, Any]:
    if row is None:
        return {}
    warnings = _loads_list(row[23])
    errors = _loads_list(row[24])
    evidence_warnings, evidence_errors = _evidence_diagnostics(row, base=base)
    warnings = _unique_strings([*warnings, *evidence_warnings])
    errors = _unique_strings([*errors, *evidence_errors])
    alert_counts = _alert_counts_mapping(_loads_mapping(row[20]))
    return {
        "schema_version": MONITOR_STATE_SCHEMA_VERSION,
        "artifact_type": "monitor_cycle_index_record",
        "cycle_id": row[0],
        "monitor_output_dir": row[1],
        "cycle_manifest": row[2],
        "cycle_mode": row[3],
        "loop_id": row[4],
        "cycle_sequence": row[5],
        "trigger_source": row[6],
        "status": row[7],
        "started_at": row[8],
        "finished_at": row[9],
        "config_ref": row[10],
        "target_stage": row[11],
        "no_codex": bool(row[12]),
        "exit_code": row[13],
        "run_id": row[14],
        "run_dir": row[15],
        "run_manifest": row[16],
        "product_run": _loads_mapping(row[17]),
        "source_artifacts": _loads_mapping(row[18]),
        "alert_archive": {
            "status": row[19],
            "state_store": MONITOR_STATE_STORE_ARTIFACT,
            "archive": MONITOR_STATE_STORE_ARTIFACT,
            "cooldown_state": MONITOR_STATE_STORE_ARTIFACT,
            "archive_state": MONITOR_STATE_STORE_ARTIFACT,
            "counts": alert_counts,
        },
        "alert_counts": alert_counts,
        "warning_count": _int(row[21]) + len(evidence_warnings),
        "error_count": _int(row[22]) + len(evidence_errors),
        "warnings": warnings,
        "errors": errors,
        "created_at": row[25],
        "updated_at": row[26],
    }


def _row_to_alert_record(row: Any) -> dict[str, Any]:
    personalized = _loads_mapping(row[15])
    source_run = _loads_mapping(row[16])
    return {
        "record_id": row[0],
        "cycle_id": row[1],
        "created_at": row[3],
        "status": row[4],
        "alert_key": row[5],
        "decision_id": row[6],
        "symbol": row[7],
        "timeframe": row[8],
        "priority": row[9],
        "attention_decision": row[10],
        "requires_user_attention": bool(row[11]),
        "suppression_reasons": _loads_list(row[12]),
        "cooldown_until": row[13],
        "source_artifacts": _loads_list(row[14]),
        "source_artifact_count": len(_loads_list(row[14])),
        "personalized_context_present": personalized.get("present") is True,
        "source_run": {
            "run_id": source_run.get("run_id"),
            "run_manifest": source_run.get("run_manifest"),
        },
    }


def _archive_summary_from_cycle(cycle: dict[str, Any]) -> dict[str, Any]:
    archive = cycle.get("alert_archive") if isinstance(cycle.get("alert_archive"), dict) else {}
    return {
        "status": str(archive.get("status") or "skipped"),
        "state_store": MONITOR_STATE_STORE_ARTIFACT,
        "archive": MONITOR_STATE_STORE_ARTIFACT,
        "cooldown_state": MONITOR_STATE_STORE_ARTIFACT,
        "archive_state": MONITOR_STATE_STORE_ARTIFACT,
        "counts": _alert_counts_mapping(archive.get("counts")),
        "warnings": _loads_or_list(cycle.get("warnings")),
        "errors": _loads_or_list(cycle.get("errors")),
    }


def _alert_component(
    status: str,
    *,
    counts: dict[str, int],
    records: list[dict[str, Any]],
    truncated: bool,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "name": "alert_archive",
        "status": status,
        "fields": {
            "archive": MONITOR_STATE_STORE_ARTIFACT,
            "archive_state": MONITOR_STATE_STORE_ARTIFACT,
            "artifact_type": "monitor_alert_archive_state",
            "updated_at": records[0]["created_at"] if records else None,
            "last_cycle_id": records[0]["cycle_id"] if records else None,
            "archive_status": status,
            "counts": counts,
            "sample_records": records,
            "sample_truncated": truncated,
            "sample_record_limit": MONITOR_ALERT_SAMPLE_LIMIT,
        },
        "source_artifacts": [MONITOR_STATE_STORE_ARTIFACT],
        "warnings": warnings or [],
        "errors": errors or [],
    }


def _cooldown_component(
    status: str,
    *,
    fields: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "name": "cooldown",
        "status": status,
        "fields": fields
        or {
            "artifact": MONITOR_STATE_STORE_ARTIFACT,
            "artifact_type": "monitor_alert_cooldown_state",
            "updated_at": None,
            "record_count": 0,
            "active_record_count": 0,
            "expired_record_count": 0,
            "state_path": MONITOR_STATE_STORE_ARTIFACT,
        },
        "source_artifacts": [MONITOR_STATE_STORE_ARTIFACT],
        "warnings": warnings or [],
        "errors": errors or [],
    }


def _count_cycles(connection: sqlite3.Connection, monitor_output_dir: str) -> int:
    return int(
        connection.execute(
            "SELECT COUNT(*) FROM monitor_cycles WHERE monitor_output_dir = ?",
            (monitor_output_dir,),
        ).fetchone()[0]
    )


def _count_failed_cycles(connection: sqlite3.Connection, monitor_output_dir: str) -> int:
    return int(
        connection.execute(
            """
            SELECT COUNT(*)
            FROM monitor_cycles
            WHERE monitor_output_dir = ? AND status IN (?, ?)
            """,
            (monitor_output_dir, *tuple(sorted(FAILED_MONITOR_STATUSES))),
        ).fetchone()[0]
    )


def _latest_cycle_row(connection: sqlite3.Connection, monitor_output_dir: str) -> Any:
    return connection.execute(
        """
        SELECT *
        FROM monitor_cycles
        WHERE monitor_output_dir = ?
        ORDER BY COALESCE(finished_at, started_at, '') DESC, cycle_id DESC
        LIMIT 1
        """,
        (monitor_output_dir,),
    ).fetchone()


def _alert_counts(connection: sqlite3.Connection, monitor_output_dir: str) -> dict[str, int]:
    rows = connection.execute(
        """
        SELECT status, COUNT(*)
        FROM monitor_alert_records
        WHERE monitor_output_dir = ?
        GROUP BY status
        """,
        (monitor_output_dir,),
    ).fetchall()
    counts = _empty_alert_counts()
    for status, count in rows:
        key = str(status or "")
        if key in counts:
            counts[key] = int(count or 0)
    counts["records"] = sum(counts[key] for key in ALERT_COUNT_KEYS if key != "records")
    return counts


def _cooldown_count(connection: sqlite3.Connection, monitor_output_dir: str) -> int:
    return int(
        connection.execute(
            "SELECT COUNT(*) FROM monitor_alert_cooldowns WHERE monitor_output_dir = ?",
            (monitor_output_dir,),
        ).fetchone()[0]
    )


def _health_issue_counts(connection: sqlite3.Connection, monitor_output_dir: str, *, base: Path) -> tuple[int, int]:
    rows = connection.execute(
        """
        SELECT *
        FROM monitor_cycles
        WHERE monitor_output_dir = ?
        """,
        (monitor_output_dir,),
    ).fetchall()
    warning_count = 0
    error_count = 0
    for row in rows:
        cycle = _row_to_cycle(row, base=base)
        warning_count += _int(cycle.get("warning_count"))
        error_count += _int(cycle.get("error_count"))
    return warning_count, error_count


def _latest_loop(connection: sqlite3.Connection, monitor_output_dir: str) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT
          loop_id,
          status,
          max_cycles,
          completed_cycles,
          stop_reason,
          started_at,
          finished_at,
          latest_cycle_id,
          reason
        FROM monitor_loops
        WHERE monitor_output_dir = ?
        ORDER BY COALESCE(finished_at, started_at, '') DESC, loop_id DESC
        LIMIT 1
        """,
        (monitor_output_dir,),
    ).fetchone()
    if not row:
        return {}
    return {
        "loop_id": row[0],
        "status": row[1],
        "max_cycles": _int(row[2]),
        "completed_cycles": _int(row[3]),
        "stop_reason": row[4],
        "started_at": row[5],
        "finished_at": row[6],
        "latest_cycle_id": row[7],
        "reason": row[8],
    }


def _evidence_diagnostics(row: Any, *, base: Path | None) -> tuple[list[str], list[str]]:
    if base is None:
        return [], []
    warnings: list[str] = []
    errors: list[str] = []
    cycle_ref = _optional_str(row[2])
    if cycle_ref:
        status, message = _evidence_status(cycle_ref, base=base, label="monitor cycle manifest")
        if status == "missing":
            warnings.append(message)
        elif status == "failed":
            errors.append(message)
    run_ref = _optional_str(row[16])
    if run_ref:
        status, message = _evidence_status(run_ref, base=base, label="linked run manifest")
        if status == "missing":
            warnings.append(message)
        elif status == "failed":
            errors.append(message)
    return warnings, errors


def _evidence_status(ref: str, *, base: Path, label: str) -> tuple[str, str]:
    path = Path(ref)
    target = path if path.is_absolute() else base / path
    try:
        target.resolve().relative_to(base.resolve())
    except (OSError, ValueError):
        return "failed", f"{label} ref points outside the runtime root."
    if not target.exists():
        return "missing", f"{label} was not found: {ref}."
    return "available", ""


def _health_status(
    *,
    latest_cycle_status: str,
    latest_loop_status: str,
    warning_count: int,
    error_count: int,
    failed_cycle_count: int,
) -> str:
    if latest_cycle_status.lower() in FAILED_MONITOR_STATUSES:
        return "failed"
    if latest_loop_status.lower() in FAILED_MONITOR_STATUSES:
        return "failed"
    if error_count:
        return "failed"
    if warning_count or failed_cycle_count:
        return "partial"
    return "available"


def _cycle_component_status(cycle: dict[str, Any]) -> str:
    if cycle.get("errors"):
        return "failed"
    if cycle.get("warnings"):
        return "partial"
    return str(cycle.get("status") or "unknown")


def _overall_status(statuses: list[str]) -> str:
    cleaned = [status for status in statuses if status]
    if not cleaned:
        return "missing"
    if "failed" in cleaned:
        return "failed"
    if "degraded" in cleaned:
        return "degraded"
    if "partial" in cleaned:
        return "partial"
    if "missing" in cleaned:
        return "missing" if set(cleaned) == {"missing"} else "partial"
    if "stale" in cleaned:
        return "stale"
    if "skipped" in cleaned:
        return "skipped" if set(cleaned) == {"skipped"} else "partial"
    if "not_applicable" in cleaned:
        return "not_applicable" if set(cleaned) == {"not_applicable"} else "partial"
    return "available"


def _empty_alert_counts() -> dict[str, int]:
    return {key: 0 for key in ALERT_COUNT_KEYS}


def _alert_counts_mapping(value: Any) -> dict[str, int]:
    data = value if isinstance(value, dict) else {}
    return {key: _int(data.get(key)) for key in ALERT_COUNT_KEYS}


def _bounded_messages(items: list[dict[str, Any]], *, key: str, limit: int = 40) -> list[str]:
    messages: list[str] = []
    for item in items:
        messages.extend(_bounded_strings(item.get(key), limit=limit))
        if len(messages) >= limit:
            break
    return messages[:limit]


def _required_str(value: Any, message: str) -> str:
    if not isinstance(value, str) or not value:
        raise MonitorStateStoreError(message)
    return value


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    return _optional_int(value) or 0


def _dumps_mapping(value: Any) -> str:
    return json.dumps(value if isinstance(value, dict) else {}, sort_keys=True, separators=(",", ":"))


def _dumps_list(value: Any) -> str:
    return json.dumps(_bounded_strings(value, limit=80), sort_keys=True, separators=(",", ":"))


def _loads_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, str) or not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _loads_list(value: Any) -> list[str]:
    if not isinstance(value, str) or not value:
        return []
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return []
    return _bounded_strings(loaded, limit=80)


def _loads_or_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return _bounded_strings(value, limit=80)
    if isinstance(value, str):
        return _loads_list(value)
    return []


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _bounded_strings(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            continue
        output.append(item)
        if len(output) >= limit:
            break
    return output


def _unique_strings(values: list[str | None]) -> list[str]:
    output: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value or value in output:
            continue
        output.append(value)
    return output


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("timestamp must include a UTC offset.")
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str):
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("timestamp must be an ISO 8601 UTC string.") from exc
        if timestamp.tzinfo is None:
            raise ValueError("timestamp must include a UTC offset.")
        timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)
    else:
        raise ValueError("timestamp must be a datetime or ISO 8601 UTC string.")
    return timestamp.isoformat().replace("+00:00", "Z")
