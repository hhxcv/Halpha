from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
import json
from json import JSONDecodeError
from pathlib import Path
import shutil
import sqlite3
from typing import Any

from halpha.data.run_index import (
    RUN_INDEX_BASE_RUN_COLUMNS,
    RUN_INDEX_RUN_COLUMNS,
    RunIndexRecord,
    run_index_artifacts,
    run_index_latest_refs,
    run_index_path,
)
from halpha.runtime.legacy_state_migration import rebuild_run_index_from_manifests
from halpha.runtime.run_classification import (
    DISPOSAL_DERIVED_ARCHIVE,
    DISPOSAL_LEGACY_ARCHIVE,
    DISPOSAL_MONITOR_REASSESSMENT_ARCHIVE,
    DISPOSAL_VALIDATION_ARCHIVE,
    classification_from_manifest,
)
from halpha.storage import artifact_base, safe_local_ref


RUN_ARCHIVE_CLEANUP_SCHEMA_VERSION = 1
REPORT_ARCHIVE_DELETE_CONFIRMATION = "DELETE REPORT RUNS"
DISPOSABLE_DISPOSAL_CLASSES = {
    DISPOSAL_DERIVED_ARCHIVE,
    DISPOSAL_MONITOR_REASSESSMENT_ARCHIVE,
    DISPOSAL_VALIDATION_ARCHIVE,
}
REVIEW_DISPOSAL_CLASSES = {DISPOSAL_LEGACY_ARCHIVE}
EXTERNAL_REF = "<external-ref>"


@dataclass(frozen=True)
class RunArchiveCleanupError(Exception):
    message: str
    exit_code: int = 1

    def __str__(self) -> str:
        return self.message


def plan_run_archive_cleanup(
    config: dict[str, Any],
    *,
    config_path: Path,
    include_report_archives: bool = False,
    confirm_report_deletion: str | None = None,
) -> dict[str, Any]:
    base = artifact_base(config_path)
    run_root = _run_root(config, base=base)
    root_error = _run_root_error(run_root, base=base)
    index_snapshot = _read_run_index_snapshot(config_path, base=base)
    latest_refs = index_snapshot["latest_refs"]
    rows_by_id = {
        record.run_id: record
        for record in index_snapshot["records"]
    }
    artifacts_by_id = index_snapshot["artifacts"]
    candidates: list[dict[str, Any]] = []
    diagnostics = [*index_snapshot["diagnostics"]]

    if root_error:
        diagnostics.append(
            {
                "category": "review_required",
                "reason": root_error,
                "ref": _safe_ref(run_root, base=base),
            }
        )
    elif run_root.exists() and not run_root.is_dir():
        diagnostics.append(
            {
                "category": "review_required",
                "reason": "configured run root exists but is not a directory.",
                "ref": _safe_ref(run_root, base=base),
            }
        )
    elif run_root.is_dir():
        for run_dir in _iter_run_dirs(run_root):
            item = _run_dir_cleanup_item(
                run_dir,
                base=base,
                run_root=run_root,
                indexed_record=rows_by_id.get(run_dir.name),
                indexed_artifacts=artifacts_by_id.get(run_dir.name, {}),
                latest_refs=latest_refs,
                include_report_archives=include_report_archives,
                confirm_report_deletion=confirm_report_deletion,
            )
            if item["category"] == "safe_to_delete" or item["category"] == "report_bearing":
                candidates.append(item)
            else:
                diagnostics.append(item)

    missing_index_records = _missing_index_record_diagnostics(
        rows_by_id.values(),
        base=base,
        latest_refs=latest_refs,
    )
    diagnostics.extend(missing_index_records)
    categories = _category_counts(candidates, diagnostics)
    size_bytes = sum(_int(item.get("size_bytes")) for item in candidates if item.get("deletable"))
    return {
        "schema_version": RUN_ARCHIVE_CLEANUP_SCHEMA_VERSION,
        "artifact_type": "run_archive_cleanup_plan",
        "status": "available" if candidates or diagnostics else "empty",
        "mode": "dry_run",
        "run_root": _safe_ref(run_root, base=base),
        "report_confirmation_text": REPORT_ARCHIVE_DELETE_CONFIRMATION,
        "counts": {
            "candidates": len(candidates),
            "safe_to_delete": categories["safe_to_delete"],
            "report_bearing": categories["report_bearing"],
            "review_required": categories["review_required"],
            "diagnostics": len(diagnostics),
            "deletable": sum(1 for item in candidates if item.get("deletable")),
            "approximate_deletable_size_bytes": size_bytes,
        },
        "latest_index_refs": latest_refs,
        "candidates": candidates,
        "diagnostics": diagnostics[:100],
        "warnings": _cleanup_warnings(candidates, diagnostics),
        "errors": [],
        "omitted": {
            "absolute_local_paths_embedded": False,
            "run_archive_contents_embedded": False,
            "shared_data_embedded": False,
        },
    }


def apply_run_archive_cleanup(
    config: dict[str, Any],
    *,
    config_path: Path,
    run_ids: list[str],
    include_report_archives: bool = False,
    confirm_report_deletion: str | None = None,
) -> dict[str, Any]:
    requested_ids = _unique_strings(run_ids)
    if not requested_ids:
        raise RunArchiveCleanupError("at least one --run-id is required when applying cleanup.", exit_code=2)
    plan = plan_run_archive_cleanup(
        config,
        config_path=config_path,
        include_report_archives=include_report_archives,
        confirm_report_deletion=confirm_report_deletion,
    )
    candidates = {
        str(item.get("run_id")): item
        for item in plan["candidates"]
        if isinstance(item.get("run_id"), str)
    }
    base = artifact_base(config_path)
    run_root = _run_root(config, base=base)
    deleted: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for run_id in requested_ids:
        item = candidates.get(run_id)
        if item is None:
            blocked.append({"run_id": run_id, "reason": "run id is not in the approved cleanup candidate set."})
            continue
        if not item.get("deletable"):
            blocked.append({"run_id": run_id, "reason": str(item.get("deletion_reason") or "run is not deletable.")})
            continue
        target = _resolve_ref(str(item.get("run_dir") or ""), base=base)
        guard = _delete_guard(target, run_root=run_root, base=base)
        if guard:
            blocked.append({"run_id": run_id, "reason": guard})
            continue
        if target is None or not target.exists():
            skipped.append({"run_id": run_id, "run_dir": str(item.get("run_dir") or ""), "reason": "run directory is already missing."})
            continue
        error = _delete_run_dir(target)
        if error:
            blocked.append({"run_id": run_id, "run_dir": str(item.get("run_dir") or ""), "reason": error})
            continue
        deleted.append({"run_id": run_id, "run_dir": str(item.get("run_dir") or ""), "size_bytes": item.get("size_bytes")})

    index_result: dict[str, Any] = {"status": "skipped", "reason": "no run directories were deleted."}
    if deleted:
        index_result = rebuild_run_index_from_manifests(config, config_path=config_path)

    status = _apply_status(deleted=deleted, skipped=skipped, blocked=blocked, index_result=index_result)
    return {
        "schema_version": RUN_ARCHIVE_CLEANUP_SCHEMA_VERSION,
        "artifact_type": "run_archive_cleanup_result",
        "status": status,
        "mode": "apply",
        "run_root": plan["run_root"],
        "requested_run_ids": requested_ids,
        "deleted": deleted,
        "skipped": skipped,
        "blocked": blocked,
        "index_rebuild": index_result,
        "warnings": _result_warnings(blocked=blocked, index_result=index_result),
        "errors": _result_errors(index_result),
        "omitted": {
            "absolute_local_paths_embedded": False,
            "deleted_contents_embedded": False,
            "shared_data_embedded": False,
        },
    }


def _run_dir_cleanup_item(
    run_dir: Path,
    *,
    base: Path,
    run_root: Path,
    indexed_record: RunIndexRecord | None,
    indexed_artifacts: dict[str, str],
    latest_refs: dict[str, str | None],
    include_report_archives: bool,
    confirm_report_deletion: str | None,
) -> dict[str, Any]:
    manifest_path = run_dir / "run_manifest.json"
    guard = _candidate_guard(run_dir, run_root=run_root, base=base)
    common = {
        "run_dir": _safe_ref(run_dir, base=base),
        "manifest": _safe_ref(manifest_path, base=base),
        "size_bytes": 0 if guard else _directory_size(run_dir),
        "latest_index_refs": _latest_refs_for_run(run_dir.name, latest_refs),
    }
    if guard:
        return {**common, "run_id": run_dir.name, "category": "review_required", "deletable": False, "reason": guard}
    manifest, error = _read_manifest(manifest_path)
    if error:
        return {
            **common,
            "run_id": run_dir.name,
            "category": "review_required",
            "deletable": False,
            "reason": error,
        }
    run_id = str(manifest.get("run_id") or run_dir.name)
    if run_id != run_dir.name:
        return {
            **common,
            "run_id": run_id,
            "category": "review_required",
            "deletable": False,
            "reason": "run_id does not match the run directory name.",
        }
    classification = classification_from_manifest(manifest)
    run_status = _run_status(manifest, indexed_record)
    report_state = _report_state(run_dir, manifest=manifest, indexed_artifacts=indexed_artifacts, base=base)
    if run_status != "succeeded":
        category = "review_required"
        deletable = False
        deletion_reason = f"run status {run_status} requires review."
    elif report_state["status"] == "dangling":
        category = "review_required"
        deletable = False
        deletion_reason = "report artifact refs are dangling and require review."
    elif _has_report_ref(report_state):
        category = "report_bearing"
        deletable = include_report_archives and confirm_report_deletion == REPORT_ARCHIVE_DELETE_CONFIRMATION
        deletion_reason = (
            "report-bearing archive deletion explicitly confirmed."
            if deletable
            else f"report-bearing archive requires --include-report-runs and --confirm-report-runs {REPORT_ARCHIVE_DELETE_CONFIRMATION}."
        )
    elif classification["disposal_class"] in DISPOSABLE_DISPOSAL_CLASSES:
        category = "safe_to_delete"
        deletable = True
        deletion_reason = f"disposal_class {classification['disposal_class']} has no report artifact refs."
    elif classification["disposal_class"] in REVIEW_DISPOSAL_CLASSES or classification["run_kind"] == "unknown":
        category = "review_required"
        deletable = False
        deletion_reason = "unknown or legacy classification requires review."
    else:
        category = "review_required"
        deletable = False
        deletion_reason = f"disposal_class {classification['disposal_class']} is not a disposable archive."
    return {
        **common,
        "run_id": run_id,
        "status": run_status,
        "run_kind": classification["run_kind"],
        "disposal_class": classification["disposal_class"],
        "trigger": _trigger_summary(classification["trigger"]),
        "report": report_state,
        "indexed": indexed_record is not None,
        "category": category,
        "deletable": deletable,
        "deletion_reason": deletion_reason,
    }


def _read_run_index_snapshot(config_path: Path, *, base: Path) -> dict[str, Any]:
    path = run_index_path(config_path)
    if not path.exists():
        return {"records": [], "artifacts": {}, "latest_refs": {}, "diagnostics": []}
    try:
        with closing(sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)) as connection:
            rows = _run_index_rows(connection)
            records = [record for row in rows if (record := RunIndexRecord.from_row(row)) is not None]
            artifacts = {
                record.run_id: run_index_artifacts(connection, record.run_id)
                for record in records
            }
            latest_refs = _safe_latest_refs(connection)
    except sqlite3.Error as exc:
        return {
            "records": [],
            "artifacts": {},
            "latest_refs": {},
            "diagnostics": [
                {
                    "category": "review_required",
                    "reason": f"run index could not be inspected: {exc.__class__.__name__}.",
                    "ref": _safe_ref(path, base=base),
                }
            ],
        }
    return {"records": records, "artifacts": artifacts, "latest_refs": latest_refs, "diagnostics": []}


def _run_index_rows(connection: sqlite3.Connection) -> list[Any]:
    try:
        return connection.execute(f"SELECT {RUN_INDEX_RUN_COLUMNS} FROM runs ORDER BY run_id").fetchall()
    except sqlite3.OperationalError as exc:
        if "no such column" not in str(exc).lower():
            raise
        return connection.execute(f"SELECT {RUN_INDEX_BASE_RUN_COLUMNS} FROM runs ORDER BY run_id").fetchall()


def _safe_latest_refs(connection: sqlite3.Connection) -> dict[str, str | None]:
    try:
        return run_index_latest_refs(connection)
    except sqlite3.Error:
        return {}


def _missing_index_record_diagnostics(
    records: Any,
    *,
    base: Path,
    latest_refs: dict[str, str | None],
) -> list[dict[str, Any]]:
    diagnostics = []
    for record in records:
        run_dir = _resolve_ref(record.run_dir, base=base)
        manifest = _resolve_ref(record.manifest_path, base=base)
        missing = []
        if run_dir is None or not run_dir.exists():
            missing.append("run_dir")
        if manifest is None or not manifest.exists():
            missing.append("manifest")
        if missing:
            diagnostics.append(
                {
                    "run_id": record.run_id,
                    "run_dir": record.run_dir,
                    "manifest": record.manifest_path,
                    "category": "review_required",
                    "deletable": False,
                    "missing": missing,
                    "latest_index_refs": _latest_refs_for_run(record.run_id, latest_refs),
                    "reason": "run index row references missing run archive artifacts.",
                }
            )
    return diagnostics


def _report_state(
    run_dir: Path,
    *,
    manifest: dict[str, Any],
    indexed_artifacts: dict[str, str],
    base: Path,
) -> dict[str, Any]:
    refs = _report_refs(manifest, indexed_artifacts)
    missing = []
    existing = []
    for ref in refs:
        target = _resolve_report_ref(ref, run_dir=run_dir, base=base)
        safe_ref = _safe_ref(target, base=base) if target else ref
        if target is not None and target.exists():
            existing.append(safe_ref)
        else:
            missing.append(ref)
    if missing:
        status = "dangling"
    elif existing:
        status = "present"
    else:
        status = "absent"
    return {
        "status": status,
        "has_report_ref": bool(refs),
        "refs": refs[:20],
        "existing_refs": existing[:20],
        "missing_refs": missing[:20],
    }


def _report_refs(manifest: dict[str, Any], indexed_artifacts: dict[str, str]) -> list[str]:
    refs: list[str] = []
    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), dict) else {}
    refs.extend(_string_refs(artifacts.get("report")))
    if isinstance(indexed_artifacts.get("report"), str):
        refs.append(indexed_artifacts["report"])
    return _unique_strings(refs)


def _string_refs(value: Any) -> list[str]:
    if isinstance(value, str) and value:
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item]
    return []


def _resolve_report_ref(ref: str, *, run_dir: Path, base: Path) -> Path | None:
    path = Path(ref)
    target = path if path.is_absolute() else (base / path if ref.replace("\\", "/").startswith("runs/") else run_dir / path)
    try:
        target.resolve().relative_to(base.resolve())
    except (OSError, ValueError):
        return None
    return target


def _read_manifest(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, "run_manifest.json is missing."
    except OSError:
        return {}, "run_manifest.json could not be read."
    except JSONDecodeError:
        return {}, "run_manifest.json is not valid JSON."
    if not isinstance(loaded, dict):
        return {}, "run_manifest.json must be a JSON object."
    if not isinstance(loaded.get("run_id"), str) or not loaded.get("run_id"):
        return {}, "run_manifest.json is missing run_id."
    return loaded, None


def _run_status(manifest: dict[str, Any], indexed_record: RunIndexRecord | None) -> str:
    status = manifest.get("status")
    if isinstance(status, str) and status:
        return status
    if indexed_record is not None and indexed_record.status:
        return indexed_record.status
    return "unknown"


def _iter_run_dirs(root: Path) -> list[Path]:
    try:
        return sorted(path for path in root.iterdir() if path.is_dir() or path.is_symlink())
    except OSError:
        return []


def _directory_size(path: Path) -> int:
    total = 0
    try:
        for child in path.rglob("*"):
            try:
                stat = child.lstat()
            except OSError:
                continue
            if child.is_file() or child.is_symlink():
                total += stat.st_size
    except OSError:
        return total
    return total


def _candidate_guard(run_dir: Path, *, run_root: Path, base: Path) -> str | None:
    if run_dir.is_symlink():
        return "run directory is a symlink and requires review."
    if not _within(run_dir, base):
        return "run directory is outside the project root."
    if not _within(run_dir, run_root):
        return "run directory is outside the configured run root."
    if _same_path(run_dir, run_root):
        return "configured run root cannot be selected as a run archive."
    return None


def _delete_guard(target: Path | None, *, run_root: Path, base: Path) -> str | None:
    if target is None:
        return "run directory could not be resolved."
    guard = _candidate_guard(target, run_root=run_root, base=base)
    if guard:
        return guard
    if not target.exists():
        return None
    if not target.is_dir():
        return "run archive target is not a directory."
    return None


def _delete_run_dir(path: Path) -> str | None:
    try:
        shutil.rmtree(path)
    except OSError as exc:
        return f"run archive could not be deleted: {exc.__class__.__name__}."
    return None


def _run_root(config: dict[str, Any], *, base: Path) -> Path:
    run = config.get("run") if isinstance(config.get("run"), dict) else {}
    output_dir = Path(str(run.get("output_dir") or "runs"))
    return output_dir if output_dir.is_absolute() else base / output_dir


def _run_root_error(path: Path, *, base: Path) -> str | None:
    if not _within(path, base):
        return "configured run root is outside the project root."
    if _same_path(path, base):
        return "project root cannot be used as the run cleanup root."
    return None


def _resolve_ref(ref: str, *, base: Path) -> Path | None:
    if not ref:
        return None
    path = Path(ref)
    target = path if path.is_absolute() else base / path
    try:
        target.resolve().relative_to(base.resolve())
    except (OSError, ValueError):
        return None
    return target


def _safe_ref(path: Path, *, base: Path) -> str:
    return safe_local_ref(path, base=base, external_ref=EXTERNAL_REF)


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return False


def _has_report_ref(report_state: dict[str, Any]) -> bool:
    return report_state.get("has_report_ref") is True


def _trigger_summary(trigger: dict[str, Any]) -> dict[str, Any]:
    keys = ("source", "intent", "job_id", "schedule_id", "monitor_cycle_id", "source_keys", "parent_run_id", "requested_stage")
    return {key: trigger[key] for key in keys if key in trigger}


def _latest_refs_for_run(run_id: str, latest_refs: dict[str, str | None]) -> list[str]:
    return [key for key, value in sorted(latest_refs.items()) if value == run_id]


def _category_counts(candidates: list[dict[str, Any]], diagnostics: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "safe_to_delete": sum(1 for item in candidates if item.get("category") == "safe_to_delete"),
        "report_bearing": sum(1 for item in candidates if item.get("category") == "report_bearing"),
        "review_required": sum(1 for item in diagnostics if item.get("category") == "review_required"),
    }


def _cleanup_warnings(candidates: list[dict[str, Any]], diagnostics: list[dict[str, Any]]) -> list[str]:
    warnings = []
    if any(item.get("category") == "report_bearing" and not item.get("deletable") for item in candidates):
        warnings.append("report-bearing archives require explicit stronger confirmation before deletion.")
    if diagnostics:
        warnings.append("malformed, dangling, unknown, or legacy run archives require review and are not approved candidates.")
    return warnings


def _result_warnings(*, blocked: list[dict[str, Any]], index_result: dict[str, Any]) -> list[str]:
    warnings = []
    if blocked:
        warnings.append("some requested run archives were not deleted.")
    warnings.extend(str(item) for item in index_result.get("warnings", []) if isinstance(item, str))
    return warnings


def _result_errors(index_result: dict[str, Any]) -> list[str]:
    return [str(item) for item in index_result.get("errors", []) if isinstance(item, str)]


def _apply_status(
    *,
    deleted: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    blocked: list[dict[str, Any]],
    index_result: dict[str, Any],
) -> str:
    if _result_errors(index_result):
        return "failed"
    if blocked and not (deleted or skipped):
        return "blocked"
    if blocked:
        return "partial"
    if deleted or skipped:
        return "succeeded"
    return "empty"


def _unique_strings(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        if value and value not in output:
            output.append(value)
    return output


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    return 0
