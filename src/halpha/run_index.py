from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .storage import display_path

if TYPE_CHECKING:
    from .pipeline import RunContext


RUN_INDEX_SCHEMA_VERSION = 1
RUN_INDEX_ARTIFACT = "data/research/index.sqlite"


def write_run_index(run: RunContext, *, now: datetime | str | None = None) -> dict[str, Any]:
    index_path = run_index_path(run.config_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    updated_at = _format_utc(now)

    with sqlite3.connect(index_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        _create_schema(connection)
        _replace_run(connection, run)
        _replace_run_stages(connection, run)
        _replace_run_artifacts(connection, run)
        _replace_latest(connection, run, updated_at=updated_at)
        counts = _table_counts(connection)

    return {
        "schema_version": RUN_INDEX_SCHEMA_VERSION,
        "status": "ok",
        "artifact": RUN_INDEX_ARTIFACT,
        "updated_at": updated_at,
        "run_id": run.run_id,
        "tables": counts,
        "latest_successful_run_id": run.run_id if run.manifest.get("status") == "succeeded" else None,
    }


def run_index_path(config_path: Path) -> Path:
    return config_path.parent / RUN_INDEX_ARTIFACT


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
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
        );

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
        );

        CREATE TABLE IF NOT EXISTS run_artifacts (
          run_id TEXT NOT NULL,
          artifact_key TEXT NOT NULL,
          path TEXT NOT NULL,
          kind TEXT NOT NULL,
          PRIMARY KEY (run_id, artifact_key, path),
          FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS run_latest (
          key TEXT PRIMARY KEY,
          run_id TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        """
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
            display_path(run.run_dir, base=run.config_path.parent),
            display_path(run.config_path, base=run.config_path.parent),
            _optional_string(manifest.get("started_at")),
            _optional_string(manifest.get("finished_at")),
            str(manifest.get("status") or "unknown"),
            _failed_stage(manifest),
            _optional_string((manifest.get("codex") or {}).get("status"))
            if isinstance(manifest.get("codex"), dict)
            else None,
            _warning_count(manifest),
            _error_count(manifest),
            display_path(run.manifest_path, base=run.config_path.parent),
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


def _replace_latest(connection: sqlite3.Connection, run: RunContext, *, updated_at: str) -> None:
    connection.execute(
        "INSERT OR REPLACE INTO run_latest (key, run_id, updated_at) VALUES (?, ?, ?)",
        ("latest_run", run.run_id, updated_at),
    )
    if run.manifest.get("status") == "succeeded":
        connection.execute(
            "INSERT OR REPLACE INTO run_latest (key, run_id, updated_at) VALUES (?, ?, ?)",
            ("latest_successful_run", run.run_id, updated_at),
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
