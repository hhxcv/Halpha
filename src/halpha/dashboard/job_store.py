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
    runtime_state_transaction,
    runtime_state_path,
)


DASHBOARD_JOB_STORE_ARTIFACT = STATE_STORE_REF
DASHBOARD_JOB_LOG_ROOT_REF = ".halpha/dashboard/job_logs"
DASHBOARD_JOB_SCHEMA_VERSION = 1
DASHBOARD_JOB_MIGRATION_VERSION = 3
DASHBOARD_JOB_EVENT_LIMIT = 200
JOB_TRANSIENT_STATUSES = {"queued", "running", "cancel_requested"}
JOB_TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "unsupported", "blocked", "not_started"}
ALLOWED_JOB_TRANSITIONS = {
    "queued": {"running", "failed", "unsupported", "blocked", "not_started"},
    "running": {"cancel_requested", "succeeded", "failed", "cancelled"},
    "cancel_requested": {"cancelled", "failed"},
}


class DashboardJobStoreError(Exception):
    pass


@dataclass(frozen=True)
class DashboardJobEvent:
    job_id: str
    event_type: str
    from_status: str | None
    to_status: str
    created_at: str
    message: str | None = None
    details: dict[str, Any] | None = None


DASHBOARD_JOB_MIGRATIONS = (
    StateStoreMigration(
        version=DASHBOARD_JOB_MIGRATION_VERSION,
        name="dashboard_command_jobs",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS dashboard_command_jobs (
              job_id TEXT PRIMARY KEY,
              intent TEXT NOT NULL,
              kind TEXT NOT NULL,
              requested_by TEXT NOT NULL,
              config_ref TEXT NOT NULL,
              status TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              started_at TEXT,
              finished_at TEXT,
              pid INTEGER,
              exit_code INTEGER,
              cancellable INTEGER NOT NULL,
              cancellation_requested_at TEXT,
              cancel_reason TEXT,
              params_json TEXT NOT NULL,
              command_json TEXT NOT NULL,
              job_dir TEXT NOT NULL,
              stdout_ref TEXT,
              stderr_ref TEXT,
              stdout_chars INTEGER NOT NULL,
              stderr_chars INTEGER NOT NULL,
              stdout_truncated INTEGER NOT NULL,
              stderr_truncated INTEGER NOT NULL,
              max_log_chars INTEGER NOT NULL,
              result_refs_json TEXT NOT NULL,
              source_artifacts_json TEXT NOT NULL,
              warnings_json TEXT NOT NULL,
              errors_json TEXT NOT NULL,
              diagnostic_json TEXT
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS dashboard_command_job_events (
              event_id INTEGER PRIMARY KEY AUTOINCREMENT,
              job_id TEXT NOT NULL,
              event_type TEXT NOT NULL,
              from_status TEXT,
              to_status TEXT NOT NULL,
              created_at TEXT NOT NULL,
              message TEXT,
              details_json TEXT NOT NULL,
              FOREIGN KEY (job_id) REFERENCES dashboard_command_jobs(job_id) ON DELETE CASCADE
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_dashboard_command_jobs_created ON dashboard_command_jobs(created_at, job_id)",
            "CREATE INDEX IF NOT EXISTS idx_dashboard_command_jobs_status ON dashboard_command_jobs(status, updated_at)",
            "CREATE INDEX IF NOT EXISTS idx_dashboard_command_job_events_job ON dashboard_command_job_events(job_id, event_id)",
        ),
    ),
)


class DashboardJobRepository:
    def __init__(self, *, config_path: Path) -> None:
        self.config_path = Path(config_path)
        self.database_path = runtime_state_path(config_path=self.config_path)

    def save_job(self, job: dict[str, Any], *, event_type: str, message: str | None = None) -> dict[str, Any]:
        job_id = _job_id(job)
        status = _status(job)
        now = str(job.get("updated_at") or job.get("created_at") or "")
        if not now:
            raise DashboardJobStoreError("dashboard job updated_at is required.")
        try:
            with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
                apply_dashboard_job_migrations(connection, now=now)
                with runtime_state_transaction(connection):
                    previous = self._status_for_update(connection, job_id)
                    _validate_transition(previous, status)
                    self._replace_job(connection, job)
                    self._record_event(
                        connection,
                        DashboardJobEvent(
                            job_id=job_id,
                            event_type=event_type,
                            from_status=previous,
                            to_status=status,
                            created_at=now,
                            message=message,
                        ),
                    )
        except sqlite3.Error as exc:
            raise DashboardJobStoreError("dashboard job state store could not be written.") from exc
        return self.get_job(job_id) or dict(job)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        if not self.database_path.exists():
            return None
        try:
            with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
                apply_dashboard_job_migrations(connection)
                row = connection.execute(
                    """
                    SELECT *
                    FROM dashboard_command_jobs
                    WHERE job_id = ?
                    """,
                    (job_id,),
                ).fetchone()
                return _row_to_job(row) if row else None
        except sqlite3.Error:
            return None

    def list_jobs(self, *, limit: int) -> list[dict[str, Any]]:
        if not self.database_path.exists():
            return []
        try:
            with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
                apply_dashboard_job_migrations(connection)
                rows = connection.execute(
                    """
                    SELECT *
                    FROM dashboard_command_jobs
                    ORDER BY created_at DESC, job_id DESC
                    LIMIT ?
                    """,
                    (max(0, limit),),
                ).fetchall()
        except sqlite3.Error:
            return []
        return [_row_to_job(row) for row in rows]

    def list_transient_jobs(self) -> list[dict[str, Any]]:
        if not self.database_path.exists():
            return []
        try:
            with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
                apply_dashboard_job_migrations(connection)
                rows = connection.execute(
                    """
                    SELECT *
                    FROM dashboard_command_jobs
                    WHERE status IN (?, ?, ?)
                    ORDER BY created_at DESC, job_id DESC
                    """,
                    tuple(sorted(JOB_TRANSIENT_STATUSES)),
                ).fetchall()
        except sqlite3.Error:
            return []
        return [_row_to_job(row) for row in rows]

    def job_events(self, job_id: str, *, limit: int = DASHBOARD_JOB_EVENT_LIMIT) -> list[dict[str, Any]]:
        if not self.database_path.exists():
            return []
        try:
            with closing(open_runtime_state_connection(config_path=self.config_path)) as connection:
                apply_dashboard_job_migrations(connection)
                rows = connection.execute(
                    """
                    SELECT event_type, from_status, to_status, created_at, message, details_json
                    FROM dashboard_command_job_events
                    WHERE job_id = ?
                    ORDER BY event_id DESC
                    LIMIT ?
                    """,
                    (job_id, max(0, limit)),
                ).fetchall()
        except sqlite3.Error:
            return []
        events = []
        for event_type, from_status, to_status, created_at, message, details_json in rows:
            events.append(
                {
                    "event_type": event_type,
                    "from_status": from_status,
                    "to_status": to_status,
                    "created_at": created_at,
                    "message": message,
                    "details": _loads_mapping(details_json),
                }
            )
        return list(reversed(events))

    def _status_for_update(self, connection: sqlite3.Connection, job_id: str) -> str | None:
        row = connection.execute(
            "SELECT status FROM dashboard_command_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        return str(row[0]) if row and isinstance(row[0], str) else None

    def _replace_job(self, connection: sqlite3.Connection, job: dict[str, Any]) -> None:
        logs = job.get("logs") if isinstance(job.get("logs"), dict) else {}
        connection.execute(
            """
            INSERT OR REPLACE INTO dashboard_command_jobs (
              job_id,
              intent,
              kind,
              requested_by,
              config_ref,
              status,
              created_at,
              updated_at,
              started_at,
              finished_at,
              pid,
              exit_code,
              cancellable,
              cancellation_requested_at,
              cancel_reason,
              params_json,
              command_json,
              job_dir,
              stdout_ref,
              stderr_ref,
              stdout_chars,
              stderr_chars,
              stdout_truncated,
              stderr_truncated,
              max_log_chars,
              result_refs_json,
              source_artifacts_json,
              warnings_json,
              errors_json,
              diagnostic_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _job_id(job),
                str(job.get("intent") or ""),
                str(job.get("kind") or "command"),
                str(job.get("requested_by") or "Dashboard"),
                str(job.get("config_ref") or ""),
                _status(job),
                str(job.get("created_at") or ""),
                str(job.get("updated_at") or ""),
                _optional_str(job.get("started_at")),
                _optional_str(job.get("finished_at")),
                _optional_int(job.get("pid")),
                _optional_int(job.get("exit_code")),
                1 if job.get("cancellable") is True else 0,
                _optional_str(job.get("cancellation_requested_at")),
                _optional_str(job.get("cancel_reason")),
                _dumps_mapping(job.get("params")),
                _dumps_list(job.get("command")),
                str(job.get("job_dir") or ""),
                _optional_str(logs.get("stdout_ref")),
                _optional_str(logs.get("stderr_ref")),
                _int(logs.get("stdout_chars")),
                _int(logs.get("stderr_chars")),
                1 if logs.get("stdout_truncated") is True else 0,
                1 if logs.get("stderr_truncated") is True else 0,
                _int(logs.get("max_chars")),
                _dumps_mapping(job.get("result_refs")),
                _dumps_list(job.get("source_artifacts")),
                _dumps_list(job.get("warnings")),
                _dumps_list(job.get("errors")),
                _dumps_optional_mapping(job.get("diagnostic")),
            ),
        )

    def _record_event(self, connection: sqlite3.Connection, event: DashboardJobEvent) -> None:
        connection.execute(
            """
            INSERT INTO dashboard_command_job_events (
              job_id,
              event_type,
              from_status,
              to_status,
              created_at,
              message,
              details_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.job_id,
                event.event_type,
                event.from_status,
                event.to_status,
                event.created_at,
                event.message,
                _dumps_mapping(event.details),
            ),
        )


def apply_dashboard_job_migrations(connection: sqlite3.Connection, *, now: str | None = None) -> None:
    apply_runtime_state_migrations(connection, migrations=RUNTIME_STATE_MIGRATIONS + DASHBOARD_JOB_MIGRATIONS, now=now)


def _validate_transition(previous: str | None, status: str) -> None:
    if previous is None:
        return
    if previous == status:
        return
    if previous in JOB_TERMINAL_STATUSES:
        raise DashboardJobStoreError(f"dashboard job cannot transition from terminal status {previous} to {status}.")
    allowed = ALLOWED_JOB_TRANSITIONS.get(previous, set())
    if status not in allowed:
        raise DashboardJobStoreError(f"dashboard job cannot transition from {previous} to {status}.")


def _row_to_job(row: Any) -> dict[str, Any]:
    logs = {
        "stdout_ref": row[18],
        "stderr_ref": row[19],
        "stdout_chars": int(row[20] or 0),
        "stderr_chars": int(row[21] or 0),
        "stdout_truncated": bool(row[22]),
        "stderr_truncated": bool(row[23]),
        "max_chars": int(row[24] or 0),
    }
    job = {
        "schema_version": DASHBOARD_JOB_SCHEMA_VERSION,
        "artifact_type": "dashboard_job",
        "job_id": row[0],
        "kind": row[2],
        "intent": row[1],
        "requested_by": row[3],
        "params": _loads_mapping(row[15]),
        "config_ref": row[4],
        "status": row[5],
        "created_at": row[6],
        "updated_at": row[7],
        "started_at": row[8],
        "finished_at": row[9],
        "pid": row[10],
        "exit_code": row[11],
        "cancellable": bool(row[12]),
        "cancellation_requested_at": row[13],
        "cancel_reason": row[14],
        "command": _loads_list(row[16]),
        "job_dir": row[17],
        "logs": logs,
        "result_refs": _loads_mapping(row[25]),
        "source_artifacts": _loads_list(row[26]),
        "warnings": _loads_list(row[27]),
        "errors": _loads_list(row[28]),
    }
    diagnostic = _loads_optional_mapping(row[29])
    if diagnostic:
        job["diagnostic"] = diagnostic
    return job


def _job_id(job: dict[str, Any]) -> str:
    job_id = job.get("job_id")
    if not isinstance(job_id, str) or not job_id:
        raise DashboardJobStoreError("dashboard job_id is required.")
    return job_id


def _status(job: dict[str, Any]) -> str:
    status = job.get("status")
    if not isinstance(status, str) or not status:
        raise DashboardJobStoreError("dashboard job status is required.")
    return status


def _dumps_mapping(value: Any) -> str:
    return json.dumps(value if isinstance(value, dict) else {}, sort_keys=True, separators=(",", ":"))


def _dumps_optional_mapping(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    return _dumps_mapping(value)


def _dumps_list(value: Any) -> str:
    return json.dumps(value if isinstance(value, list) else [], sort_keys=True, separators=(",", ":"))


def _loads_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, str) or not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _loads_optional_mapping(value: Any) -> dict[str, Any] | None:
    loaded = _loads_mapping(value)
    return loaded or None


def _loads_list(value: Any) -> list[Any]:
    if not isinstance(value, str) or not value:
        return []
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return []
    return loaded if isinstance(loaded, list) else []


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
