from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
from typing import Any

from halpha.dashboard.common import dashboard_read_json as _read_json
from halpha.dashboard.common import dashboard_resolve_ref as _resolve_ref
from halpha.dashboard.common import dashboard_safe_ref as _safe_ref
from halpha.dashboard.run_aggregation import manifest_report_state, run_list_record as _run_list_record
from halpha.data.run_index import (
    RUN_INDEX_BASE_RUN_COLUMNS,
    RUN_INDEX_ARTIFACT,
    RUN_INDEX_RUN_COLUMNS,
    run_index_latest_refs,
    run_index_path,
    run_index_selection_label,
    select_latest_run_record,
    select_report_run_records,
)
from halpha.storage import artifact_base as _artifact_base
from halpha.utils.value_helpers import (
    as_dict as _dict,
    as_list as _list,
    stringified_list as _string_list,
)


MAX_STAGE_ARTIFACT_REFS = 20
DEFAULT_REPORT_RUN_LIMIT = 100
REPORT_FILE_CATEGORY_ORDER = {
    "report": 0,
    "analysis": 1,
    "codex_context": 2,
    "raw_input": 3,
    "run_metadata": 4,
    "other": 5,
}
REPORT_FILE_CATEGORY_LABELS = {
    "report": "Report",
    "analysis": "Analysis",
    "codex_context": "Codex context",
    "raw_input": "Raw inputs",
    "run_metadata": "Run metadata",
    "other": "Other",
}


def dashboard_runs(config_path: Path, *, limit: int = 100, report_limit: int = DEFAULT_REPORT_RUN_LIMIT) -> dict[str, Any]:
    base = _artifact_base(config_path)
    index_path = run_index_path(config_path)
    empty_latest = {"latest_run_id": None, "latest_successful_run_id": None}
    if not index_path.exists():
        return {
            "schema_version": 1,
            "artifact_type": "dashboard_run_list",
            "status": "missing",
            "source_artifacts": [RUN_INDEX_ARTIFACT],
            "latest": empty_latest,
            "runs": [],
            "warnings": ["local run index was not found."],
            "errors": [],
        }
    try:
        with closing(sqlite3.connect(index_path)) as connection:
            rows = _dashboard_run_rows(connection, limit=limit, report_limit=report_limit)
            artifacts = _run_artifact_index(connection)
            latest = _run_latest_refs(connection)
    except sqlite3.Error as exc:
        return {
            "schema_version": 1,
            "artifact_type": "dashboard_run_list",
            "status": "failed",
            "source_artifacts": [RUN_INDEX_ARTIFACT],
            "latest": empty_latest,
            "runs": [],
            "warnings": [],
            "errors": [f"{RUN_INDEX_ARTIFACT} is not readable: {exc}"],
        }
    runs = [_run_list_record(row, artifacts.get(str(row[0]), {}), base=base, latest=latest) for row in rows]
    missing_report_diagnostics = [
        {
            "run_id": run["run_id"],
            "status": run["report_state"]["status"],
            "artifact": run["report_state"].get("artifact"),
        }
        for run in runs
        if _dict(run.get("report_state")).get("status") == "missing"
        and _dict(run.get("report_state")).get("artifact")
    ]
    report_diagnostics = missing_report_diagnostics[:20]
    missing_index_diagnostics = [
        {
            "run_id": run["run_id"],
            "status": run["integrity_state"]["status"],
            "missing": run["integrity_state"].get("missing", []),
            "run_dir": run["integrity_state"].get("run_dir"),
            "manifest": run["integrity_state"].get("manifest"),
        }
        for run in runs
        if _dict(run.get("integrity_state")).get("status") != "available"
    ]
    index_diagnostics = missing_index_diagnostics[:20]
    warnings: list[str] = []
    if missing_index_diagnostics:
        warnings.append(f"{len(missing_index_diagnostics)} run index row(s) reference missing run artifacts.")
    if missing_report_diagnostics:
        warnings.append(
            f"{len(missing_report_diagnostics)} recorded report artifact(s) were missing and omitted from report lists."
        )
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_run_list",
        "status": "partial" if missing_index_diagnostics else "available",
        "source_artifacts": [RUN_INDEX_ARTIFACT],
        "latest": latest,
        "runs": runs,
        "counts": {
            "runs": len(runs),
            "latest_run_limit": limit,
            "report_run_limit": report_limit,
        },
        "index_diagnostics": index_diagnostics,
        "report_diagnostics": report_diagnostics,
        "warnings": warnings,
        "errors": [],
    }


def dashboard_run_detail(config_path: Path, *, run_id: str) -> dict[str, Any]:
    base = _artifact_base(config_path)
    index_path = run_index_path(config_path)
    if not index_path.exists():
        active_detail = _run_detail_from_manifest(base, run_id=run_id)
        if active_detail is not None:
            return active_detail
        return _run_detail_missing(run_id, warning="local run index was not found.")
    try:
        with closing(sqlite3.connect(index_path)) as connection:
            row = _dashboard_run_row(connection, run_id=run_id)
            latest = _run_latest_refs(connection)
    except sqlite3.Error as exc:
        return {
            "schema_version": 1,
            "artifact_type": "dashboard_run_detail",
            "status": "failed",
            "run_id": run_id,
            "source_artifacts": [RUN_INDEX_ARTIFACT],
            "fields": {},
            "stages": [],
            "artifacts": [],
            "warnings": [],
            "errors": [f"{RUN_INDEX_ARTIFACT} is not readable: {exc}"],
        }
    if row is None:
        active_detail = _run_detail_from_manifest(base, run_id=run_id)
        if active_detail is not None:
            return active_detail
        return _run_detail_missing(run_id, warning="run id was not found in the local run index.")

    run = _run_list_record(row, {}, base=base, latest=latest)
    run_dir = _resolve_ref(str(row[1]), base=base)
    manifest_path = _resolve_ref(str(row[9]), base=base)
    manifest, error = _read_json(manifest_path)
    if error:
        return {
            "schema_version": 1,
            "artifact_type": "dashboard_run_detail",
            "status": "failed",
            "run_id": run_id,
            "source_artifacts": [RUN_INDEX_ARTIFACT, _safe_ref(manifest_path, base=base)],
            "fields": run,
            "stages": [],
            "artifacts": [],
            "warnings": [],
            "errors": [error],
        }

    report_state = _report_state(run_dir, manifest)
    report_files, report_file_warnings = _report_file_catalog(run_dir, report_state=report_state, base=base)
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_run_detail",
        "status": "available",
        "run_id": run_id,
        "source_artifacts": [RUN_INDEX_ARTIFACT, _safe_ref(manifest_path, base=base)],
        "fields": {
            **run,
            "report": report_state.get("artifact") if report_state.get("status") == "available" else None,
            "report_state": report_state,
            "manifest_status": str(manifest.get("status") or "unknown"),
            "codex": _bounded_mapping(manifest.get("codex")),
            "counts": _bounded_mapping(manifest.get("counts")),
        },
        "stages": _stage_timeline(manifest),
        "artifacts": _manifest_artifacts(manifest),
        "report_files": report_files,
        "warnings": [*_string_list(manifest.get("warnings")), *report_file_warnings],
        "errors": _manifest_error_messages(manifest),
    }


def dashboard_latest_run_section(
    config_path: Path,
    *,
    base: Path,
) -> tuple[dict[str, Any], Path | None, dict[str, Any]]:
    index_path = run_index_path(config_path)
    if not index_path.exists():
        return (
            _section(
                "latest_run",
                "missing",
                source_artifacts=[RUN_INDEX_ARTIFACT],
                warnings=["local run index was not found."],
            ),
            None,
            {},
        )
    try:
        with closing(sqlite3.connect(index_path)) as connection:
            latest = _run_latest_refs(connection)
            row = _latest_run_row(connection)
    except sqlite3.Error as exc:
        return (
            _section(
                "latest_run",
                "failed",
                source_artifacts=[RUN_INDEX_ARTIFACT],
                errors=[f"{RUN_INDEX_ARTIFACT} is not readable: {exc}"],
            ),
            None,
            {},
        )
    if row is None:
        return (
            _section(
                "latest_run",
                "missing",
                source_artifacts=[RUN_INDEX_ARTIFACT],
                warnings=["local run index does not contain a latest run."],
            ),
            None,
            {},
        )

    selection_key, run_id, run_dir_ref, manifest_ref = row
    run_dir = _resolve_ref(run_dir_ref, base=base)
    manifest_path = _resolve_ref(manifest_ref, base=base)
    manifest, error = _read_json(manifest_path)
    if error:
        return (
            _section(
                "latest_run",
                "failed",
                fields={
                    "run_id": run_id,
                    "run_dir": _safe_ref(run_dir, base=base),
                    "manifest": _safe_ref(manifest_path, base=base),
                },
                source_artifacts=[RUN_INDEX_ARTIFACT, _safe_ref(manifest_path, base=base)],
                errors=[error],
            ),
            run_dir,
            {},
        )

    fields = {
        "run_id": str(manifest.get("run_id") or run_id),
        "run_dir": _safe_ref(run_dir, base=base),
        "manifest": _safe_ref(manifest_path, base=base),
        "run_status": str(manifest.get("status") or "unknown"),
        "started_at": manifest.get("started_at"),
        "finished_at": manifest.get("finished_at"),
        "codex_status": _dict(manifest.get("codex")).get("status"),
        "stage_counts": _stage_counts(manifest),
        "warning_count": _warning_count(manifest),
        "error_count": _error_count(manifest),
        "report": _report_state(run_dir, manifest),
        "selection": {
            "key": selection_key,
            "label": _latest_selection_label(selection_key),
            "latest_run_id": latest.get("latest_run_id"),
            "latest_successful_run_id": latest.get("latest_successful_run_id"),
        },
    }
    return (
        _section(
            "latest_run",
            "available",
            fields=fields,
            source_artifacts=[RUN_INDEX_ARTIFACT, _safe_ref(manifest_path, base=base)],
        ),
        run_dir,
        manifest,
    )


def _latest_run_row(connection: sqlite3.Connection) -> tuple[str, str, str, str] | None:
    selected = select_latest_run_record(connection)
    if selected:
        run = selected.run
        return selected.selection_key, run.run_id, run.run_dir, run.manifest_path
    fallback = _fallback_latest_run(connection, succeeded_only=True)
    if fallback:
        return ("fallback_latest_successful_run", *fallback)
    fallback = _fallback_latest_run(connection, succeeded_only=False)
    if fallback:
        return ("fallback_latest_run", *fallback)
    return None


def _run_latest_refs(connection: sqlite3.Connection) -> dict[str, str | None]:
    return run_index_latest_refs(connection)


def _dashboard_run_rows(connection: sqlite3.Connection, *, limit: int, report_limit: int) -> list[Any]:
    try:
        latest_rows = connection.execute(
            f"""
            SELECT {RUN_INDEX_RUN_COLUMNS}
            FROM runs
            ORDER BY COALESCE(started_at, '') DESC, run_id DESC
            LIMIT ?
            """,
            (max(0, limit),),
        ).fetchall()
    except sqlite3.OperationalError as exc:
        if not _missing_run_classification_columns(exc):
            raise
        latest_rows = connection.execute(
            f"""
            SELECT {RUN_INDEX_BASE_RUN_COLUMNS}
            FROM runs
            ORDER BY COALESCE(started_at, '') DESC, run_id DESC
            LIMIT ?
            """,
            (max(0, limit),),
        ).fetchall()
    report_rows = [record.as_row() for record in select_report_run_records(connection, limit=report_limit)]
    rows_by_id: dict[str, Any] = {}
    for row in [*latest_rows, *report_rows]:
        run_id = str(row[0])
        if run_id not in rows_by_id:
            rows_by_id[run_id] = row
    return sorted(rows_by_id.values(), key=_run_row_sort_key, reverse=True)


def _dashboard_run_row(connection: sqlite3.Connection, *, run_id: str) -> Any:
    try:
        return connection.execute(
            f"""
            SELECT {RUN_INDEX_RUN_COLUMNS}
            FROM runs
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
    except sqlite3.OperationalError as exc:
        if not _missing_run_classification_columns(exc):
            raise
        return connection.execute(
            f"""
            SELECT {RUN_INDEX_BASE_RUN_COLUMNS}
            FROM runs
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()


def _run_row_sort_key(row: Any) -> tuple[str, str]:
    return (str(row[2] or ""), str(row[0] or ""))


def _missing_run_classification_columns(exc: sqlite3.OperationalError) -> bool:
    text = str(exc).lower()
    return "no such column" in text and any(
        column in text
        for column in (
            "run_kind",
            "trigger_source",
            "trigger_intent",
            "disposal_class",
            "trigger_job_id",
            "trigger_schedule_id",
            "trigger_monitor_cycle_id",
            "trigger_source_keys",
            "trigger_parent_run_id",
            "trigger_requested_stage",
        )
    )


def _latest_selection_label(selection_key: str) -> str:
    return run_index_selection_label(selection_key)


def _run_artifact_index(connection: sqlite3.Connection) -> dict[str, dict[str, list[str]]]:
    rows = connection.execute(
        "SELECT run_id, artifact_key, path FROM run_artifacts ORDER BY run_id, artifact_key, path"
    ).fetchall()
    artifacts: dict[str, dict[str, list[str]]] = {}
    for run_id, key, path in rows:
        if not isinstance(run_id, str) or not isinstance(key, str) or not isinstance(path, str):
            continue
        artifacts.setdefault(run_id, {}).setdefault(key, []).append(path)
    return artifacts


def _fallback_latest_run(
    connection: sqlite3.Connection,
    *,
    succeeded_only: bool,
) -> tuple[str, str, str] | None:
    where = "WHERE status = 'succeeded'" if succeeded_only else ""
    row = connection.execute(
        f"""
        SELECT run_id, run_dir, manifest_path
        FROM runs
        {where}
        ORDER BY COALESCE(started_at, '') DESC, run_id DESC
        LIMIT 1
        """
    ).fetchone()
    if row and all(isinstance(value, str) and value for value in row):
        return row[0], row[1], row[2]
    return None


def _run_detail_missing(run_id: str, *, warning: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_run_detail",
        "status": "missing",
        "run_id": run_id,
        "source_artifacts": [RUN_INDEX_ARTIFACT],
        "fields": {},
        "stages": [],
        "artifacts": [],
        "warnings": [warning],
        "errors": [],
    }


def _run_detail_from_manifest(base: Path, *, run_id: str) -> dict[str, Any] | None:
    if not _safe_run_id(run_id):
        return None
    run_dir = base / "runs" / run_id
    manifest_path = run_dir / "run_manifest.json"
    if not manifest_path.is_file():
        return None
    manifest, error = _read_json(manifest_path)
    if error:
        return {
            "schema_version": 1,
            "artifact_type": "dashboard_run_detail",
            "status": "failed",
            "run_id": run_id,
            "source_artifacts": [_safe_ref(manifest_path, base=base)],
            "fields": {},
            "stages": [],
            "artifacts": [],
            "warnings": [],
            "errors": [error],
        }
    report_state = _report_state(run_dir, manifest)
    report_files, report_file_warnings = _report_file_catalog(run_dir, report_state=report_state, base=base)
    errors = _manifest_error_messages(manifest)
    fields = {
        "run_id": str(manifest.get("run_id") or run_id),
        "run_dir": _safe_ref(run_dir, base=base),
        "started_at": manifest.get("started_at"),
        "finished_at": manifest.get("finished_at"),
        "status": str(manifest.get("status") or "unknown"),
        "failed_stage": _manifest_failed_stage(manifest),
        "codex_status": _dict(manifest.get("codex")).get("status"),
        "run_kind": str(manifest.get("run_kind") or "unknown"),
        "trigger": _dict(manifest.get("trigger")),
        "disposal_class": str(manifest.get("disposal_class") or "legacy_archive"),
        "warning_count": len(_string_list(manifest.get("warnings"))),
        "error_count": len(errors),
        "manifest": _safe_ref(manifest_path, base=base),
        "integrity_state": {
            "status": "available",
            "run_dir": _safe_ref(run_dir, base=base),
            "manifest": _safe_ref(manifest_path, base=base),
            "missing": [],
        },
        "report": report_state.get("artifact") if report_state.get("status") == "available" else None,
        "report_state": report_state,
        "manifest_status": str(manifest.get("status") or "unknown"),
        "codex": _bounded_mapping(manifest.get("codex")),
        "counts": _bounded_mapping(manifest.get("counts")),
        "latest_state": {
            "is_latest_run": False,
            "is_latest_successful_run": False,
        },
    }
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_run_detail",
        "status": "available",
        "run_id": run_id,
        "source_artifacts": [_safe_ref(manifest_path, base=base)],
        "fields": fields,
        "stages": _stage_timeline(manifest),
        "artifacts": _manifest_artifacts(manifest),
        "report_files": report_files,
        "warnings": [*_string_list(manifest.get("warnings")), *report_file_warnings],
        "errors": errors,
    }


def _safe_run_id(run_id: str) -> bool:
    return bool(run_id) and "/" not in run_id and "\\" not in run_id and Path(run_id).name == run_id


def _manifest_failed_stage(manifest: dict[str, Any]) -> str | None:
    for error in _list(manifest.get("errors")):
        if isinstance(error, dict) and isinstance(error.get("stage"), str):
            return error["stage"]
    return None


def _section(
    name: str,
    status: str,
    *,
    fields: dict[str, Any] | None = None,
    source_artifacts: list[str] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "fields": fields or {},
        "source_artifacts": source_artifacts or [],
        "warnings": warnings or [],
        "errors": errors or [],
    }


def _report_state(run_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    return manifest_report_state(run_dir, manifest)


def _stage_counts(manifest: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for stage in _list(manifest.get("stages")):
        if not isinstance(stage, dict):
            continue
        status = str(stage.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _stage_timeline(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    timeline: list[dict[str, Any]] = []
    for index, stage in enumerate(_list(manifest.get("stages"))):
        if not isinstance(stage, dict):
            continue
        error = _dict(stage.get("error"))
        artifact_paths = _artifact_paths(stage.get("artifacts"))
        record = {
            "index": index,
            "name": stage.get("name"),
            "status": stage.get("status"),
            "started_at": stage.get("started_at"),
            "finished_at": stage.get("finished_at"),
            "artifact_count": len(artifact_paths),
            "artifacts": _stage_artifact_records(artifact_paths),
            "artifact_omitted_count": max(0, len(artifact_paths) - MAX_STAGE_ARTIFACT_REFS),
            "task_count": len(_list(stage.get("tasks"))),
            "tasks": _task_timeline(stage),
            "warning_count": _warning_count(stage),
            "error_count": 1 if error else 0,
        }
        reason = stage.get("reason")
        if isinstance(reason, str) and reason:
            record["reason"] = reason
        if error:
            record["error"] = _bounded_mapping(error)
        timeline.append(record)
    return timeline


def _task_timeline(stage: dict[str, Any]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for index, task in enumerate(_list(stage.get("tasks"))):
        if not isinstance(task, dict):
            continue
        error = _dict(task.get("error"))
        artifact_paths = _artifact_paths(task.get("artifacts"))
        record = {
            "index": index,
            "name": task.get("name"),
            "status": task.get("status"),
            "started_at": task.get("started_at"),
            "finished_at": task.get("finished_at"),
            "artifact_count": len(artifact_paths),
            "artifacts": _stage_artifact_records(artifact_paths),
            "artifact_omitted_count": max(0, len(artifact_paths) - MAX_STAGE_ARTIFACT_REFS),
            "dependencies": _string_list(task.get("dependencies")),
            "warning_count": _warning_count(task),
            "error_count": 1 if error else 0,
        }
        reason = task.get("reason")
        if isinstance(reason, str) and reason:
            record["reason"] = reason
        if error:
            record["error"] = _bounded_mapping(error)
        tasks.append(record)
    return tasks


def _stage_artifact_records(paths: list[str]) -> list[dict[str, str]]:
    return [
        {"path": path, "kind": _artifact_kind(path)}
        for path in paths[:MAX_STAGE_ARTIFACT_REFS]
    ]


def _manifest_artifacts(manifest: dict[str, Any]) -> list[dict[str, str]]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        return []
    records: list[dict[str, str]] = []
    for key, value in sorted(artifacts.items()):
        for path in _artifact_paths(value):
            records.append({"key": str(key), "path": path, "kind": _artifact_kind(path)})
    return records


def _report_file_catalog(
    run_dir: Path,
    *,
    report_state: dict[str, Any],
    base: Path,
) -> tuple[list[dict[str, Any]], list[str]]:
    if not run_dir.is_dir():
        return [], ["run directory was not found; report reference files could not be listed."]
    try:
        run_root = run_dir.resolve()
    except OSError as exc:
        return [], [f"run directory could not be resolved: {exc}"]

    report_ref = report_state.get("artifact")
    report_path = _resolve_run_file_ref(str(report_ref), run_dir=run_dir, base=base) if isinstance(report_ref, str) and report_ref else None
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    try:
        candidate_files = sorted(
            (path for path in run_dir.rglob("*") if path.is_file()),
            key=lambda path: _run_relative_file_ref(path, run_dir=run_dir),
        )
    except OSError as exc:
        return [], [f"run directory files could not be listed: {exc}"]

    for path in candidate_files:
        try:
            resolved = path.resolve()
            resolved.relative_to(run_root)
        except (OSError, ValueError):
            warnings.append("one report reference file outside the run directory was omitted.")
            continue
        relative_ref = _run_relative_file_ref(path, run_dir=run_dir)
        category = _report_file_category(relative_ref)
        safe_ref = _safe_ref(path, base=base)
        pinned = report_path is not None and _same_path(path, report_path)
        records.append(
            {
                "ref": safe_ref,
                "path": relative_ref,
                "name": path.name,
                "title": _report_file_title(relative_ref, pinned=pinned),
                "category": category,
                "category_label": REPORT_FILE_CATEGORY_LABELS.get(category, "Other"),
                "preview_kind": _report_file_preview_kind(path),
                "size_bytes": _file_size(path),
                "pinned": pinned,
            }
        )
    records.sort(key=_report_file_sort_key)
    return records, warnings


def _run_relative_file_ref(path: Path, *, run_dir: Path) -> str:
    try:
        return path.relative_to(run_dir).as_posix()
    except ValueError:
        return path.name


def _resolve_run_file_ref(ref: str, *, run_dir: Path, base: Path) -> Path:
    path = Path(ref)
    if path.is_absolute():
        return path
    if ref.startswith(("runs/", "data/")):
        return base / path
    return run_dir / path


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return left == right


def _report_file_category(relative_ref: str) -> str:
    if relative_ref == "run_manifest.json":
        return "run_metadata"
    first = Path(relative_ref).parts[0] if Path(relative_ref).parts else ""
    if first == "report":
        return "report"
    if first == "analysis":
        return "analysis"
    if first == "codex_context":
        return "codex_context"
    if first == "raw":
        return "raw_input"
    return "other"


def _report_file_title(relative_ref: str, *, pinned: bool) -> str:
    if pinned:
        return "Report"
    if relative_ref == "run_manifest.json":
        return "Run manifest"
    stem = Path(relative_ref).stem.replace("_", " ").replace("-", " ").strip()
    return stem.title() if stem else Path(relative_ref).name


def _report_file_preview_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix == ".json":
        return "json"
    if suffix == ".jsonl":
        return "jsonl"
    if suffix == ".csv":
        return "csv"
    if suffix in {".txt", ".log", ".yaml", ".yml"}:
        return "text"
    return "unsupported"


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _report_file_sort_key(record: dict[str, Any]) -> tuple[int, int, str]:
    category = str(record.get("category") or "other")
    return (
        0 if record.get("pinned") else 1,
        REPORT_FILE_CATEGORY_ORDER.get(category, REPORT_FILE_CATEGORY_ORDER["other"]),
        str(record.get("path") or ""),
    )


def _artifact_paths(value: Any) -> list[str]:
    if isinstance(value, str) and value:
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if isinstance(item, str) and item]
    if isinstance(value, dict):
        paths: list[str] = []
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
        return "data"
    if path.startswith("runs/monitor/"):
        return "monitor"
    if path.startswith("runs/workbench/"):
        return "workbench"
    return "other"


def _manifest_error_messages(manifest: dict[str, Any]) -> list[str]:
    messages: list[str] = []
    for error in _list(manifest.get("errors")):
        if isinstance(error, dict):
            message = error.get("message")
            stage = error.get("stage")
            if stage and message:
                messages.append(f"{stage}: {message}")
            elif message:
                messages.append(str(message))
        elif isinstance(error, str):
            messages.append(error)
    return messages


def _bounded_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, str | int | float | bool) or item is None:
            result[str(key)] = item
        elif isinstance(item, list):
            result[str(key)] = item[:10]
        elif isinstance(item, dict):
            result[str(key)] = {
                str(child_key): child_value
                for child_key, child_value in list(item.items())[:10]
                if isinstance(child_value, str | int | float | bool) or child_value is None
            }
    return result


def _warning_count(value: dict[str, Any]) -> int:
    return _int(value.get("warning_count"), default=len(_list(value.get("warnings"))))


def _error_count(value: dict[str, Any]) -> int:
    return _int(value.get("error_count"), default=len(_list(value.get("errors"))))


def _int(value: Any, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


__all__ = ["dashboard_latest_run_section", "dashboard_run_detail", "dashboard_runs"]
