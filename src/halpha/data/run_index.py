from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from halpha.runtime.state_store import (
    RUNTIME_STATE_MIGRATIONS,
    STATE_STORE_REF,
    StateStoreMigration,
    apply_runtime_state_migrations,
    open_runtime_state_connection,
    runtime_state_error_diagnostic,
    runtime_state_path,
    runtime_state_transaction,
)
from halpha.storage import artifact_base, display_path

if TYPE_CHECKING:
    from halpha.runtime.pipeline_contracts import RunContext


RUN_INDEX_SCHEMA_VERSION = 2
RUN_INDEX_ARTIFACT = STATE_STORE_REF
LEGACY_RUN_INDEX_ARTIFACT = "data/research/index.sqlite"
LATEST_RUN_KEY = "latest_run"
LATEST_SUCCESSFUL_RUN_KEY = "latest_successful_run"
LATEST_REPORT_RUN_KEY = "latest_report_run"
RUN_INDEX_RUN_COLUMNS = """
run_id,
run_dir,
started_at,
finished_at,
status,
failed_stage,
codex_status,
warning_count,
error_count,
manifest_path
"""
RUN_INDEX_RUN_COLUMNS_R = """
r.run_id,
r.run_dir,
r.started_at,
r.finished_at,
r.status,
r.failed_stage,
r.codex_status,
r.warning_count,
r.error_count,
r.manifest_path
"""

RUN_INDEX_MIGRATIONS = (
    StateStoreMigration(
        version=2,
        name="run_index",
        statements=(
            """
            CREATE TABLE IF NOT EXISTS runs (
              run_id TEXT PRIMARY KEY,
              run_dir TEXT NOT NULL,
              config_path TEXT,
              started_at TEXT,
              finished_at TEXT,
              status TEXT NOT NULL,
              failed_stage TEXT,
              codex_status TEXT,
              warning_count INTEGER NOT NULL,
              error_count INTEGER NOT NULL,
              manifest_path TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS run_stages (
              run_id TEXT NOT NULL,
              stage_index INTEGER NOT NULL,
              stage_name TEXT NOT NULL,
              status TEXT,
              started_at TEXT,
              finished_at TEXT,
              warning_count INTEGER NOT NULL,
              error_count INTEGER NOT NULL,
              PRIMARY KEY (run_id, stage_index),
              FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS run_artifacts (
              run_id TEXT NOT NULL,
              artifact_key TEXT NOT NULL,
              path TEXT NOT NULL,
              kind TEXT NOT NULL,
              PRIMARY KEY (run_id, artifact_key, path),
              FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
            )
            """,
            "DROP VIEW IF EXISTS run_latest",
            """
            CREATE VIEW run_latest AS
            SELECT *
            FROM (
              SELECT
                'latest_run' AS key,
                run_id,
                COALESCE(finished_at, started_at, '') AS updated_at
              FROM runs
              ORDER BY COALESCE(started_at, '') DESC, run_id DESC
              LIMIT 1
            )
            UNION ALL
            SELECT *
            FROM (
              SELECT
                'latest_successful_run' AS key,
                run_id,
                COALESCE(finished_at, started_at, '') AS updated_at
              FROM runs
              WHERE status = 'succeeded'
              ORDER BY COALESCE(started_at, '') DESC, run_id DESC
              LIMIT 1
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at, run_id)",
            "CREATE INDEX IF NOT EXISTS idx_runs_status_started_at ON runs(status, started_at, run_id)",
            "CREATE INDEX IF NOT EXISTS idx_run_artifacts_lookup ON run_artifacts(run_id, artifact_key)",
        ),
    ),
)


@dataclass(frozen=True)
class RunIndexRecord:
    run_id: str
    run_dir: str
    started_at: str | None
    finished_at: str | None
    status: str
    failed_stage: str | None
    codex_status: str | None
    warning_count: int
    error_count: int
    manifest_path: str

    @classmethod
    def from_row(cls, row: Any) -> RunIndexRecord | None:
        if row is None or len(row) < 10:
            return None
        if not all(isinstance(row[index], str) and row[index] for index in (0, 1, 4, 9)):
            return None
        return cls(
            run_id=str(row[0]),
            run_dir=str(row[1]),
            started_at=_optional_string(row[2]),
            finished_at=_optional_string(row[3]),
            status=str(row[4]),
            failed_stage=_optional_string(row[5]),
            codex_status=_optional_string(row[6]),
            warning_count=_int(row[7]),
            error_count=_int(row[8]),
            manifest_path=str(row[9]),
        )

    def as_row(self) -> tuple[Any, ...]:
        return (
            self.run_id,
            self.run_dir,
            self.started_at,
            self.finished_at,
            self.status,
            self.failed_stage,
            self.codex_status,
            self.warning_count,
            self.error_count,
            self.manifest_path,
        )


@dataclass(frozen=True)
class RunIndexSelection:
    selection_key: str
    run: RunIndexRecord
    artifacts: dict[str, str]


@dataclass(frozen=True)
class RunIndexManifestInspection:
    status: str
    run_id: str | None
    warnings: tuple[str, ...]
    errors: tuple[str, ...]


def write_run_index(run: RunContext, *, now: datetime | str | None = None) -> dict[str, Any]:
    updated_at = _format_utc(now)

    with closing(open_runtime_state_connection(config_path=run.config_path)) as connection:
        apply_run_index_migrations(connection, now=updated_at)
        with runtime_state_transaction(connection):
            _replace_run(connection, run)
            _replace_run_stages(connection, run)
            _replace_run_artifacts(connection, run)
        counts = _table_counts(connection)
        latest_successful = _latest_run_id(connection, succeeded_only=True)

    return {
        "schema_version": RUN_INDEX_SCHEMA_VERSION,
        "status": "ok",
        "artifact": RUN_INDEX_ARTIFACT,
        "updated_at": updated_at,
        "run_id": run.run_id,
        "tables": counts,
        "latest_successful_run_id": latest_successful,
    }


def run_index_path(config_path: Path) -> Path:
    return runtime_state_path(config_path=config_path)


def apply_run_index_migrations(connection: sqlite3.Connection, *, now: datetime | str | None = None) -> None:
    apply_runtime_state_migrations(connection, migrations=RUNTIME_STATE_MIGRATIONS + RUN_INDEX_MIGRATIONS, now=now)


def run_index_error_diagnostic(exc: sqlite3.Error, *, operation: str) -> dict[str, Any]:
    return runtime_state_error_diagnostic(exc, operation=operation)


def run_index_table_counts(connection: sqlite3.Connection) -> dict[str, int]:
    return _table_counts(connection)


def run_index_latest_refs(connection: sqlite3.Connection) -> dict[str, str | None]:
    refs: dict[str, str | None] = {"latest_run_id": None, "latest_successful_run_id": None}
    rows = connection.execute(
        "SELECT key, run_id FROM run_latest WHERE key IN (?, ?)",
        (LATEST_RUN_KEY, LATEST_SUCCESSFUL_RUN_KEY),
    ).fetchall()
    for key, run_id in rows:
        if not isinstance(run_id, str) or not run_id:
            continue
        if key == LATEST_RUN_KEY:
            refs["latest_run_id"] = run_id
        elif key == LATEST_SUCCESSFUL_RUN_KEY:
            refs["latest_successful_run_id"] = run_id
    return refs


def run_index_selection_label(selection_key: str) -> str:
    labels = {
        LATEST_SUCCESSFUL_RUN_KEY: "latest successful run",
        LATEST_RUN_KEY: "latest indexed run",
        LATEST_REPORT_RUN_KEY: "latest report-bearing run",
        "fallback_latest_successful_run": "fallback latest successful run",
        "fallback_latest_run": "fallback latest indexed run",
    }
    return labels.get(selection_key, selection_key)


def fetch_run_index_record(connection: sqlite3.Connection, run_id: str) -> RunIndexRecord | None:
    row = connection.execute(
        f"""
        SELECT {RUN_INDEX_RUN_COLUMNS}
        FROM runs
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchone()
    return RunIndexRecord.from_row(row)


def select_latest_run_record(
    connection: sqlite3.Connection,
    *,
    prefer_successful: bool = True,
) -> RunIndexSelection | None:
    keys = (LATEST_SUCCESSFUL_RUN_KEY, LATEST_RUN_KEY) if prefer_successful else (LATEST_RUN_KEY,)
    for key in keys:
        row = connection.execute("SELECT run_id FROM run_latest WHERE key = ?", (key,)).fetchone()
        if not row or not isinstance(row[0], str) or not row[0]:
            continue
        record = fetch_run_index_record(connection, row[0])
        if record:
            return RunIndexSelection(selection_key=key, run=record, artifacts=run_index_artifacts(connection, record.run_id))
    return None


def select_latest_available_report_run(
    connection: sqlite3.Connection,
    *,
    base: Path,
) -> RunIndexSelection | None:
    for selection in select_available_report_run_records(connection, base=base, limit=1):
        return selection
    return None


def select_available_report_run_records(
    connection: sqlite3.Connection,
    *,
    base: Path,
    limit: int,
) -> list[RunIndexSelection]:
    if limit <= 0:
        return []
    rows = connection.execute(
        f"""
        SELECT {RUN_INDEX_RUN_COLUMNS_R}, a.path
        FROM runs r
        JOIN run_artifacts a ON a.run_id = r.run_id
        WHERE a.artifact_key = 'report'
        ORDER BY COALESCE(r.started_at, '') DESC, r.run_id DESC, a.path
        """
    ).fetchall()
    selections: list[RunIndexSelection] = []
    for row in rows:
        record = RunIndexRecord.from_row(row[:10])
        report_ref = row[10] if len(row) > 10 and isinstance(row[10], str) else None
        if record is None or not report_ref:
            continue
        report_path = _available_report_path(record, report_ref, base=base)
        if report_path is None:
            continue
        selections.append(
            RunIndexSelection(
                selection_key=LATEST_REPORT_RUN_KEY,
                run=record,
                artifacts={"report": report_ref},
            )
        )
        if len(selections) >= limit:
            break
    return selections


def select_report_run_records(connection: sqlite3.Connection, *, limit: int) -> list[RunIndexRecord]:
    if limit <= 0:
        return []
    rows = connection.execute(
        f"""
        SELECT {RUN_INDEX_RUN_COLUMNS_R}
        FROM runs r
        WHERE EXISTS (
          SELECT 1
          FROM run_artifacts a
          WHERE a.run_id = r.run_id
            AND a.artifact_key = 'report'
        )
        ORDER BY COALESCE(r.started_at, '') DESC, r.run_id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [record for row in rows if (record := RunIndexRecord.from_row(row)) is not None]


def select_previous_successful_run_record(
    connection: sqlite3.Connection,
    *,
    current_run_id: str,
    artifact_keys: set[str] | frozenset[str] | None = None,
) -> RunIndexSelection | None:
    row = connection.execute(
        f"""
        SELECT {RUN_INDEX_RUN_COLUMNS}
        FROM runs
        WHERE status = 'succeeded' AND run_id <> ?
        ORDER BY COALESCE(finished_at, started_at, run_id) DESC, run_id DESC
        LIMIT 1
        """,
        (current_run_id,),
    ).fetchone()
    record = RunIndexRecord.from_row(row)
    if record is None:
        return None
    return RunIndexSelection(
        selection_key="latest_previous_successful_run",
        run=record,
        artifacts=run_index_artifacts(connection, record.run_id, artifact_keys=artifact_keys),
    )


def run_index_artifacts(
    connection: sqlite3.Connection,
    run_id: str,
    *,
    artifact_keys: set[str] | frozenset[str] | None = None,
) -> dict[str, str]:
    params: list[Any] = [run_id]
    where = "WHERE run_id = ?"
    if artifact_keys:
        ordered_keys = sorted(artifact_keys)
        where += " AND artifact_key IN (%s)" % ",".join("?" for _ in ordered_keys)
        params.extend(ordered_keys)
    rows = connection.execute(
        f"""
        SELECT artifact_key, path
        FROM run_artifacts
        {where}
        ORDER BY artifact_key, path
        """,
        params,
    ).fetchall()
    artifacts: dict[str, str] = {}
    for artifact_key, path in rows:
        if isinstance(artifact_key, str) and artifact_key and isinstance(path, str) and path:
            artifacts.setdefault(artifact_key, path)
    return artifacts


def inspect_indexed_manifest(connection: sqlite3.Connection, *, run_id: str, base: Path) -> RunIndexManifestInspection:
    record = fetch_run_index_record(connection, run_id)
    if record is None:
        return RunIndexManifestInspection(
            status="missing",
            run_id=run_id,
            warnings=("run id was not found in the local run index.",),
            errors=(),
        )
    manifest_path = _resolve_project_ref(record.manifest_path, base=base)
    if manifest_path is None:
        return RunIndexManifestInspection(
            status="failed",
            run_id=record.run_id,
            warnings=(),
            errors=("indexed manifest path points outside the configured project root.",),
        )
    try:
        import json

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return RunIndexManifestInspection(
            status="missing",
            run_id=record.run_id,
            warnings=("indexed manifest was not found.",),
            errors=(),
        )
    except (OSError, json.JSONDecodeError) as exc:
        return RunIndexManifestInspection(
            status="failed",
            run_id=record.run_id,
            warnings=(),
            errors=(f"indexed manifest could not be inspected: {exc}.",),
        )
    if not isinstance(manifest, dict):
        return RunIndexManifestInspection(
            status="failed",
            run_id=record.run_id,
            warnings=(),
            errors=("indexed manifest must be a JSON object.",),
        )
    warnings = _manifest_consistency_warnings(record, manifest)
    return RunIndexManifestInspection(
        status="warning" if warnings else "available",
        run_id=record.run_id,
        warnings=tuple(warnings),
        errors=(),
    )


def _replace_run(connection: sqlite3.Connection, run: RunContext) -> None:
    manifest = run.manifest
    connection.execute(
        """
        INSERT OR REPLACE INTO runs (
          run_id,
          run_dir,
          config_path,
          started_at,
          finished_at,
          status,
          failed_stage,
          codex_status,
          warning_count,
          error_count,
          manifest_path
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run.run_id,
            display_path(run.run_dir, base=artifact_base(run.config_path)),
            display_path(run.config_path, base=artifact_base(run.config_path)),
            _optional_string(manifest.get("started_at")),
            _optional_string(manifest.get("finished_at")),
            str(manifest.get("status") or "unknown"),
            _failed_stage(manifest),
            _optional_string((manifest.get("codex") or {}).get("status"))
            if isinstance(manifest.get("codex"), dict)
            else None,
            _warning_count(manifest),
            _error_count(manifest),
            display_path(run.manifest_path, base=artifact_base(run.config_path)),
        ),
    )


def _replace_run_stages(connection: sqlite3.Connection, run: RunContext) -> None:
    connection.execute("DELETE FROM run_stages WHERE run_id = ?", (run.run_id,))
    stages = run.manifest.get("stages")
    if not isinstance(stages, list):
        return
    for index, stage in enumerate(stages):
        if not isinstance(stage, dict):
            continue
        connection.execute(
            """
            INSERT INTO run_stages (
              run_id,
              stage_index,
              stage_name,
              status,
              started_at,
              finished_at,
              warning_count,
              error_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.run_id,
                index,
                str(stage.get("name") or ""),
                _optional_string(stage.get("status")),
                _optional_string(stage.get("started_at")),
                _optional_string(stage.get("finished_at")),
                _warning_count(stage),
                1 if isinstance(stage.get("error"), dict) else 0,
            ),
        )


def _replace_run_artifacts(connection: sqlite3.Connection, run: RunContext) -> None:
    connection.execute("DELETE FROM run_artifacts WHERE run_id = ?", (run.run_id,))
    artifacts = run.manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        return
    for key, value in sorted(artifacts.items()):
        for path in _artifact_paths(value):
            connection.execute(
                """
                INSERT OR REPLACE INTO run_artifacts (
                  run_id,
                  artifact_key,
                  path,
                  kind
                )
                VALUES (?, ?, ?, ?)
                """,
                (run.run_id, str(key), path, _artifact_kind(path)),
            )


def _table_counts(connection: sqlite3.Connection) -> dict[str, int]:
    return {
        "runs": _count_rows(connection, "runs"),
        "run_stages": _count_rows(connection, "run_stages"),
        "run_artifacts": _count_rows(connection, "run_artifacts"),
        "run_latest": _count_rows(connection, "run_latest"),
    }


def _count_rows(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _latest_run_id(connection: sqlite3.Connection, *, succeeded_only: bool) -> str | None:
    key = LATEST_SUCCESSFUL_RUN_KEY if succeeded_only else LATEST_RUN_KEY
    row = connection.execute("SELECT run_id FROM run_latest WHERE key = ?", (key,)).fetchone()
    return row[0] if row and isinstance(row[0], str) and row[0] else None


def _available_report_path(record: RunIndexRecord, report_ref: str, *, base: Path) -> Path | None:
    run_dir = _resolve_project_ref(record.run_dir, base=base)
    if run_dir is None:
        return None
    report_path = Path(report_ref)
    if report_path.is_absolute() or report_ref.replace("\\", "/").startswith(("runs/", "data/")):
        target = _resolve_project_ref(report_ref, base=base)
    else:
        target = run_dir / report_path
        try:
            target.resolve().relative_to(base.resolve())
        except (OSError, ValueError):
            return None
    if target is None:
        return None
    return target if target.is_file() else None


def _resolve_project_ref(ref: str, *, base: Path) -> Path | None:
    path = Path(ref)
    target = path if path.is_absolute() else base / path
    try:
        target.resolve().relative_to(base.resolve())
    except (OSError, ValueError):
        return None
    return target


def _manifest_consistency_warnings(record: RunIndexRecord, manifest: dict[str, Any]) -> list[str]:
    checks = (
        ("run_id", record.run_id),
        ("status", record.status),
        ("started_at", record.started_at),
        ("finished_at", record.finished_at),
    )
    warnings = []
    for key, indexed_value in checks:
        manifest_value = manifest.get(key)
        if indexed_value is None and manifest_value in (None, ""):
            continue
        if manifest_value != indexed_value:
            warnings.append(f"indexed {key} differs from run_manifest.json.")
    return warnings


def _failed_stage(manifest: dict[str, Any]) -> str | None:
    errors = manifest.get("errors")
    if isinstance(errors, list) and errors:
        first = errors[0]
        if isinstance(first, dict) and isinstance(first.get("stage"), str):
            return first["stage"]
    stages = manifest.get("stages")
    if isinstance(stages, list):
        for stage in stages:
            if isinstance(stage, dict) and stage.get("status") == "failed":
                name = stage.get("name")
                return str(name) if name else None
    return None


def _warning_count(value: Any) -> int:
    if isinstance(value, dict):
        count = 0
        warnings = value.get("warnings")
        if isinstance(warnings, list):
            count += len(warnings)
        return count
    return 0


def _error_count(manifest: dict[str, Any]) -> int:
    errors = manifest.get("errors")
    return len(errors) if isinstance(errors, list) else 0


def _artifact_paths(value: Any) -> list[str]:
    if isinstance(value, str) and value:
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if isinstance(item, str) and item]
    if isinstance(value, dict):
        paths = []
        for item in value.values():
            paths.extend(_artifact_paths(item))
        return sorted(set(paths))
    return []


def _artifact_kind(path: str) -> str:
    if path.startswith("raw/"):
        return "raw"
    if path.startswith("analysis/"):
        return "analysis"
    if path.startswith("codex_context/"):
        return "codex_context"
    if path.startswith("report/"):
        return "report"
    if path.startswith("data/"):
        return "shared_data"
    return "other"


def _optional_string(value: Any) -> str | None:
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


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("updated_at must include a UTC offset.")
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str):
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("updated_at must be an ISO 8601 UTC string.") from exc
        if timestamp.tzinfo is None:
            raise ValueError("updated_at must include a UTC offset.")
        timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)
    else:
        raise ValueError("updated_at must be a datetime or ISO 8601 UTC string.")
    return timestamp.isoformat().replace("+00:00", "Z")
