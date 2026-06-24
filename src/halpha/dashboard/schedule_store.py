from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import json
import sqlite3
from pathlib import Path
from typing import Any

from halpha.runtime.state_store import (
    RUNTIME_STATE_MIGRATIONS,
    STATE_STORE_REF,
    StateStoreMigration,
    apply_runtime_state_migrations,
    open_runtime_state_connection,
    runtime_state_path,
    runtime_state_transaction,
)


DASHBOARD_SCHEDULE_STORE_ARTIFACT = STATE_STORE_REF
DASHBOARD_SCHEDULE_SCHEMA_VERSION = 1
DASHBOARD_SCHEDULE_MIGRATION_VERSION = 4
DASHBOARD_SCHEDULE_AUTH_MIGRATION_VERSION = 10
DASHBOARD_SCHEDULE_HISTORY_LIMIT = 20
DAILY_REPORT_SCHEDULE_ID = "daily_report"
DAILY_REPORT_SCHEDULE_KIND = "daily_report"


class DashboardScheduleStoreError(Exception):
    pass


@dataclass(frozen=True)
class ScheduleDispatchClaim:
    status: str
    schedule: dict[str, Any] | None
    scheduled_for: str | None
    warnings: list[str]
    errors: list[str]


DASHBOARD_SCHEDULE_MIGRATIONS = (
    StateStoreMigration(
        version=DASHBOARD_SCHEDULE_MIGRATION_VERSION,
        name="dashboard_daily_report_schedule",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS dashboard_schedules (
              schedule_id TEXT PRIMARY KEY,
              schedule_kind TEXT NOT NULL,
              enabled INTEGER NOT NULL,
              status TEXT NOT NULL,
              time_of_day TEXT NOT NULL,
              timezone TEXT NOT NULL,
              job_intent TEXT NOT NULL,
              next_run_at TEXT,
              last_run_at TEXT,
              last_job_id TEXT,
              revision INTEGER NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              warnings_json TEXT NOT NULL,
              errors_json TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS dashboard_schedule_dispatches (
              schedule_id TEXT NOT NULL,
              scheduled_for TEXT NOT NULL,
              dispatch_kind TEXT NOT NULL,
              status TEXT NOT NULL,
              claimed_at TEXT,
              completed_at TEXT,
              job_id TEXT,
              run_ref TEXT,
              report_ref TEXT,
              terminal_status TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              warnings_json TEXT NOT NULL,
              errors_json TEXT NOT NULL,
              PRIMARY KEY (schedule_id, scheduled_for),
              FOREIGN KEY (schedule_id) REFERENCES dashboard_schedules(schedule_id) ON DELETE CASCADE
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_dashboard_schedule_dispatches_updated ON dashboard_schedule_dispatches(schedule_id, updated_at, scheduled_for)",
            "CREATE INDEX IF NOT EXISTS idx_dashboard_schedule_dispatches_job ON dashboard_schedule_dispatches(job_id)",
        ),
    ),
    StateStoreMigration(
        version=DASHBOARD_SCHEDULE_AUTH_MIGRATION_VERSION,
        name="schedule_codex_authorization",
        statements=(
            "ALTER TABLE dashboard_schedules ADD COLUMN codex_authorization_json TEXT NOT NULL DEFAULT '{}'",
        ),
    ),
)


class DashboardScheduleRepository:
    def __init__(self, *, config_path: Path) -> None:
        self.config_path = Path(config_path)
        self.database_path = runtime_state_path(config_path=self.config_path)

    def get_schedule(self, schedule_id: str = DAILY_REPORT_SCHEDULE_ID) -> dict[str, Any] | None:
        if not self.database_path.exists():
            return None
        try:
            with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
                apply_dashboard_schedule_migrations(connection)
                row = connection.execute(
                    """
                    SELECT *
                    FROM dashboard_schedules
                    WHERE schedule_id = ?
                    """,
                    (schedule_id,),
                ).fetchone()
        except sqlite3.Error:
            return None
        return _row_to_schedule(row) if row else None

    def list_dispatches(
        self,
        schedule_id: str = DAILY_REPORT_SCHEDULE_ID,
        *,
        limit: int = DASHBOARD_SCHEDULE_HISTORY_LIMIT,
    ) -> list[dict[str, Any]]:
        if not self.database_path.exists():
            return []
        try:
            with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
                apply_dashboard_schedule_migrations(connection)
                rows = connection.execute(
                    """
                    SELECT *
                    FROM dashboard_schedule_dispatches
                    WHERE schedule_id = ?
                    ORDER BY COALESCE(updated_at, created_at, scheduled_for) DESC, scheduled_for DESC
                    LIMIT ?
                    """,
                    (schedule_id, max(0, limit)),
                ).fetchall()
        except sqlite3.Error:
            return []
        return [_row_to_dispatch(row) for row in rows]

    def save_schedule(self, schedule: dict[str, Any]) -> dict[str, Any]:
        schedule_id = _schedule_id(schedule)
        now = _required_str(schedule.get("updated_at"), "dashboard schedule updated_at is required.")
        try:
            with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
                apply_dashboard_schedule_migrations(connection, now=now)
                with runtime_state_transaction(connection):
                    previous = self._schedule_for_update(connection, schedule_id)
                    revision = int(previous["revision"] or 0) + 1 if previous else 1
                    self._replace_schedule(connection, {**schedule, "revision": revision})
        except sqlite3.Error as exc:
            raise DashboardScheduleStoreError("dashboard schedule state store could not be written.") from exc
        return self.get_schedule(schedule_id) or dict(schedule)

    def claim_dispatch(
        self,
        *,
        schedule_id: str,
        scheduled_for: str,
        claimed_at: str,
        next_run_at: str,
        dispatch_kind: str,
        blocked_error: str | None = None,
    ) -> ScheduleDispatchClaim:
        try:
            with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
                apply_dashboard_schedule_migrations(connection, now=claimed_at)
                with runtime_state_transaction(connection):
                    schedule = self._schedule_for_update(connection, schedule_id)
                    if schedule is None:
                        return ScheduleDispatchClaim(
                            status="missing",
                            schedule=None,
                            scheduled_for=None,
                            warnings=["daily report schedule is missing."],
                            errors=[],
                        )
                    existing = self._dispatch_for_update(connection, schedule_id, scheduled_for)
                    if existing is not None:
                        return ScheduleDispatchClaim(
                            status="duplicate",
                            schedule=schedule,
                            scheduled_for=scheduled_for,
                            warnings=["daily report schedule occurrence was already claimed."],
                            errors=[],
                        )
                    status = "blocked" if blocked_error else "claimed"
                    errors = [blocked_error] if blocked_error else []
                    self._insert_dispatch(
                        connection,
                        {
                            "schedule_id": schedule_id,
                            "scheduled_for": scheduled_for,
                            "dispatch_kind": dispatch_kind,
                            "status": status,
                            "claimed_at": claimed_at,
                            "completed_at": None,
                            "job_id": None,
                            "run_ref": None,
                            "report_ref": None,
                            "terminal_status": None,
                            "created_at": claimed_at,
                            "updated_at": claimed_at,
                            "warnings": [],
                            "errors": errors,
                        },
                    )
                    updated_schedule = {
                        **schedule,
                        "status": "blocked" if blocked_error else "available",
                        "next_run_at": next_run_at,
                        "last_run_at": schedule.get("last_run_at") if blocked_error else claimed_at,
                        "updated_at": claimed_at,
                        "errors": _unique([*errors, *_bounded_strings(schedule.get("errors"), limit=20)])[:20],
                    }
                    self._replace_schedule(connection, updated_schedule)
        except sqlite3.Error as exc:
            raise DashboardScheduleStoreError("dashboard schedule dispatch could not be claimed.") from exc
        return ScheduleDispatchClaim(
            status="blocked" if blocked_error else "claimed",
            schedule=self.get_schedule(schedule_id),
            scheduled_for=scheduled_for,
            warnings=[],
            errors=[blocked_error] if blocked_error else [],
        )

    def record_dispatch_job(
        self,
        *,
        schedule_id: str,
        scheduled_for: str,
        job: dict[str, Any],
        updated_at: str,
    ) -> None:
        job_id = str(job.get("job_id") or "")
        result_refs = job.get("result_refs") if isinstance(job.get("result_refs"), dict) else {}
        terminal_status = _terminal_status(job)
        status = _dispatch_status_from_job(job)
        try:
            with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
                apply_dashboard_schedule_migrations(connection, now=updated_at)
                with runtime_state_transaction(connection):
                    dispatch = self._dispatch_for_update(connection, schedule_id, scheduled_for)
                    if dispatch is None:
                        return
                    self._replace_dispatch(
                        connection,
                        {
                            **dispatch,
                            "status": status,
                            "completed_at": updated_at if terminal_status else dispatch.get("completed_at"),
                            "job_id": job_id or dispatch.get("job_id"),
                            "run_ref": _optional_str(result_refs.get("run_id")) or dispatch.get("run_ref"),
                            "report_ref": _optional_str(result_refs.get("report")) or dispatch.get("report_ref"),
                            "terminal_status": terminal_status or dispatch.get("terminal_status"),
                            "updated_at": updated_at,
                            "warnings": _bounded_strings(job.get("warnings"), limit=20)
                            or _bounded_strings(dispatch.get("warnings"), limit=20),
                            "errors": _bounded_strings(job.get("errors"), limit=20)
                            or _bounded_strings(dispatch.get("errors"), limit=20),
                        },
                    )
                    schedule = self._schedule_for_update(connection, schedule_id)
                    if schedule is not None and job_id:
                        self._replace_schedule(
                            connection,
                            {
                                **schedule,
                                "last_job_id": job_id,
                                "updated_at": updated_at,
                            },
                        )
        except sqlite3.Error as exc:
            raise DashboardScheduleStoreError("dashboard schedule dispatch job could not be recorded.") from exc

    def record_dispatch_error(
        self,
        *,
        schedule_id: str,
        scheduled_for: str,
        error: str,
        updated_at: str,
    ) -> None:
        try:
            with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
                apply_dashboard_schedule_migrations(connection, now=updated_at)
                with runtime_state_transaction(connection):
                    dispatch = self._dispatch_for_update(connection, schedule_id, scheduled_for)
                    if dispatch is None:
                        return
                    self._replace_dispatch(
                        connection,
                        {
                            **dispatch,
                            "status": "job_failed",
                            "completed_at": updated_at,
                            "updated_at": updated_at,
                            "errors": _unique([error, *_bounded_strings(dispatch.get("errors"), limit=20)])[:20],
                        },
                    )
        except sqlite3.Error as exc:
            raise DashboardScheduleStoreError("dashboard schedule dispatch error could not be recorded.") from exc

    def record_missed_dispatch(
        self,
        *,
        schedule_id: str,
        scheduled_for: str,
        missed_at: str,
        next_run_at: str,
        warning: str,
    ) -> bool:
        try:
            with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
                apply_dashboard_schedule_migrations(connection, now=missed_at)
                with runtime_state_transaction(connection):
                    schedule = self._schedule_for_update(connection, schedule_id)
                    if schedule is None:
                        return False
                    existing = self._dispatch_for_update(connection, schedule_id, scheduled_for)
                    if existing is not None:
                        return False
                    self._insert_dispatch(
                        connection,
                        {
                            "schedule_id": schedule_id,
                            "scheduled_for": scheduled_for,
                            "dispatch_kind": "automatic",
                            "status": "missed",
                            "claimed_at": None,
                            "completed_at": missed_at,
                            "job_id": None,
                            "run_ref": None,
                            "report_ref": None,
                            "terminal_status": "missed",
                            "created_at": missed_at,
                            "updated_at": missed_at,
                            "warnings": [warning],
                            "errors": [],
                        },
                    )
                    self._replace_schedule(
                        connection,
                        {
                            **schedule,
                            "next_run_at": next_run_at,
                            "updated_at": missed_at,
                            "warnings": _unique([warning, *_bounded_strings(schedule.get("warnings"), limit=20)])[:20],
                        },
                    )
        except sqlite3.Error as exc:
            raise DashboardScheduleStoreError("dashboard schedule missed dispatch could not be recorded.") from exc
        return True

    def _schedule_for_update(self, connection: sqlite3.Connection, schedule_id: str) -> dict[str, Any] | None:
        row = connection.execute(
            """
            SELECT *
            FROM dashboard_schedules
            WHERE schedule_id = ?
            """,
            (schedule_id,),
        ).fetchone()
        return _row_to_schedule(row) if row else None

    def _dispatch_for_update(
        self,
        connection: sqlite3.Connection,
        schedule_id: str,
        scheduled_for: str,
    ) -> dict[str, Any] | None:
        row = connection.execute(
            """
            SELECT *
            FROM dashboard_schedule_dispatches
            WHERE schedule_id = ? AND scheduled_for = ?
            """,
            (schedule_id, scheduled_for),
        ).fetchone()
        return _row_to_dispatch(row) if row else None

    def _replace_schedule(self, connection: sqlite3.Connection, schedule: dict[str, Any]) -> None:
        settings = schedule.get("settings") if isinstance(schedule.get("settings"), dict) else {}
        connection.execute(
            """
            INSERT INTO dashboard_schedules (
              schedule_id,
              schedule_kind,
              enabled,
              status,
              time_of_day,
              timezone,
              job_intent,
              next_run_at,
              last_run_at,
              last_job_id,
              revision,
              created_at,
              updated_at,
              codex_authorization_json,
              warnings_json,
              errors_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(schedule_id) DO UPDATE SET
              schedule_kind = excluded.schedule_kind,
              enabled = excluded.enabled,
              status = excluded.status,
              time_of_day = excluded.time_of_day,
              timezone = excluded.timezone,
              job_intent = excluded.job_intent,
              next_run_at = excluded.next_run_at,
              last_run_at = excluded.last_run_at,
              last_job_id = excluded.last_job_id,
              revision = excluded.revision,
              updated_at = excluded.updated_at,
              codex_authorization_json = excluded.codex_authorization_json,
              warnings_json = excluded.warnings_json,
              errors_json = excluded.errors_json
            """,
            (
                _schedule_id(schedule),
                str(schedule.get("schedule_kind") or DAILY_REPORT_SCHEDULE_KIND),
                1 if schedule.get("enabled") is True else 0,
                str(schedule.get("status") or "available"),
                str(settings.get("time_of_day") or schedule.get("time_of_day") or ""),
                str(settings.get("timezone") or schedule.get("timezone") or ""),
                str(settings.get("job_intent") or schedule.get("job_intent") or ""),
                _optional_str(schedule.get("next_run_at")),
                _optional_str(schedule.get("last_run_at")),
                _optional_str(schedule.get("last_job_id")),
                _int(schedule.get("revision")),
                str(schedule.get("created_at") or schedule.get("updated_at") or ""),
                str(schedule.get("updated_at") or ""),
                _dumps_object(schedule.get("codex_authorization")),
                _dumps_list(schedule.get("warnings")),
                _dumps_list(schedule.get("errors")),
            ),
        )

    def _insert_dispatch(self, connection: sqlite3.Connection, dispatch: dict[str, Any]) -> None:
        self._replace_dispatch(connection, dispatch)

    def _replace_dispatch(self, connection: sqlite3.Connection, dispatch: dict[str, Any]) -> None:
        connection.execute(
            """
            INSERT OR REPLACE INTO dashboard_schedule_dispatches (
              schedule_id,
              scheduled_for,
              dispatch_kind,
              status,
              claimed_at,
              completed_at,
              job_id,
              run_ref,
              report_ref,
              terminal_status,
              created_at,
              updated_at,
              warnings_json,
              errors_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(dispatch.get("schedule_id") or DAILY_REPORT_SCHEDULE_ID),
                str(dispatch.get("scheduled_for") or ""),
                str(dispatch.get("dispatch_kind") or "automatic"),
                str(dispatch.get("status") or "claimed"),
                _optional_str(dispatch.get("claimed_at")),
                _optional_str(dispatch.get("completed_at")),
                _optional_str(dispatch.get("job_id")),
                _optional_str(dispatch.get("run_ref")),
                _optional_str(dispatch.get("report_ref")),
                _optional_str(dispatch.get("terminal_status")),
                str(dispatch.get("created_at") or dispatch.get("updated_at") or ""),
                str(dispatch.get("updated_at") or ""),
                _dumps_list(dispatch.get("warnings")),
                _dumps_list(dispatch.get("errors")),
            ),
        )


def apply_dashboard_schedule_migrations(connection: sqlite3.Connection, *, now: str | None = None) -> None:
    apply_runtime_state_migrations(
        connection,
        migrations=RUNTIME_STATE_MIGRATIONS + DASHBOARD_SCHEDULE_MIGRATIONS,
        now=now,
    )


def _row_to_schedule(row: Any) -> dict[str, Any]:
    return {
        "schema_version": DASHBOARD_SCHEDULE_SCHEMA_VERSION,
        "artifact_type": "dashboard_daily_report_schedule",
        "schedule_id": row[0],
        "schedule_kind": row[1],
        "enabled": bool(row[2]),
        "status": row[3],
        "settings": {
            "time_of_day": row[4],
            "timezone": row[5],
            "job_intent": row[6],
        },
        "next_run_at": row[7],
        "last_run_at": row[8],
        "last_job_id": row[9],
        "revision": int(row[10] or 0),
        "created_at": row[11],
        "updated_at": row[12],
        "warnings": _loads_list(row[13]),
        "errors": _loads_list(row[14]),
        "codex_authorization": _loads_object(row[15]) if len(row) > 15 else {},
    }


def _row_to_dispatch(row: Any) -> dict[str, Any]:
    return {
        "schedule_id": row[0],
        "scheduled_for": row[1],
        "dispatch_kind": row[2],
        "status": row[3],
        "claimed_at": row[4],
        "completed_at": row[5],
        "job_id": row[6],
        "run_ref": row[7],
        "report_ref": row[8],
        "terminal_status": row[9],
        "created_at": row[10],
        "updated_at": row[11],
        "warnings": _loads_list(row[12]),
        "errors": _loads_list(row[13]),
    }


def _schedule_id(schedule: dict[str, Any]) -> str:
    schedule_id = schedule.get("schedule_id")
    if not isinstance(schedule_id, str) or not schedule_id:
        raise DashboardScheduleStoreError("dashboard schedule_id is required.")
    return schedule_id


def _required_str(value: Any, message: str) -> str:
    if not isinstance(value, str) or not value:
        raise DashboardScheduleStoreError(message)
    return value


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _dumps_list(value: Any) -> str:
    return json.dumps(_bounded_strings(value, limit=20), sort_keys=True, separators=(",", ":"))


def _loads_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return _bounded_strings(value, limit=20)
    if not isinstance(value, str) or not value:
        return []
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return []
    return _bounded_strings(loaded, limit=20)


def _dumps_object(value: Any) -> str:
    if not isinstance(value, dict):
        return "{}"
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _loads_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, str) or not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


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


def _terminal_status(job: dict[str, Any]) -> str | None:
    status = job.get("status")
    if status in {"succeeded", "failed", "cancelled", "unsupported", "blocked", "not_started"}:
        return str(status)
    return None


def _dispatch_status_from_job(job: dict[str, Any]) -> str:
    status = _terminal_status(job)
    if status is None:
        return "job_created"
    if status == "succeeded":
        return "job_succeeded"
    if status == "cancelled":
        return "job_cancelled"
    return "job_failed"


def _unique(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        if value and value not in output:
            output.append(value)
    return output
