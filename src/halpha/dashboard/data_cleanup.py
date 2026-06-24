from __future__ import annotations

from contextlib import closing
from pathlib import Path
import shutil
import sqlite3
from typing import Any

from halpha.outcome.outcome_history import OUTCOME_HISTORY_ARTIFACT, OUTCOME_HISTORY_STATE_ARTIFACT
from halpha.data.run_index import RUN_INDEX_ARTIFACT, run_index_path
from halpha.storage import artifact_base, safe_local_ref
from halpha.utils.value_helpers import (
    as_dict as _dict,
    as_list as _list,
    strict_int as _int,
    stringified_list as _string_list,
)


EXTERNAL_ARTIFACT_REF = "<external-artifact>"
MAX_DELETION_RUN_ITEMS = 500
REJECTED_EXTERNAL_REF_NAME = ".halpha_external_ref_rejected"
RUN_ARTIFACT_DELETE_CONFIRMATION = "DELETE RUN DATA"
SHARED_DATA_DELETE_CONFIRMATION = "DELETE SHARED DATA"
SHARED_DATA_ALLOWED_ROOTS = {"data"}
SHARED_DATA_STORE_DELETE_REFS = {
    "research_data_catalog": ("data/research/metadata/research_data_catalog.json",),
    "run_index": (RUN_INDEX_ARTIFACT,),
    "text_event_history": (
        "data/research/metadata/text_event_history_state.json",
        "data/research/text_events",
    ),
    "ohlcv_history": (
        "data/market/metadata/ohlcv_schema.json",
        "data/market/metadata/ohlcv_sync_state.json",
        "data/market/ohlcv",
    ),
    "derivatives_market_history": (
        "data/market/metadata/derivatives_market_schema.json",
        "data/market/metadata/derivatives_market_state.json",
        "data/market/derivatives",
    ),
    "macro_calendar_history": (
        "data/macro/metadata/macro_calendar_schema.json",
        "data/macro/metadata/macro_calendar_state.json",
        "data/macro/calendar",
    ),
    "onchain_flow_history": (
        "data/onchain/metadata/onchain_flow_schema.json",
        "data/onchain/metadata/onchain_flow_state.json",
        "data/onchain/flow",
    ),
    "outcome_history": (
        OUTCOME_HISTORY_STATE_ARTIFACT,
        OUTCOME_HISTORY_ARTIFACT,
        "data/research/outcomes",
    ),
}


def dashboard_data_deletion_plan(
    config: dict[str, Any],
    *,
    config_path: Path,
    runs_payload: dict[str, Any],
    stores_payload: dict[str, Any],
) -> dict[str, Any]:
    base = artifact_base(config_path)
    run_section = _run_artifact_deletion_section(config, runs_payload=runs_payload, base=base)
    shared_section = _shared_data_deletion_section(config, stores_payload=stores_payload, base=base)
    cleanup_candidates = _cleanup_candidate_section(_list(run_section.get("cleanup_candidates")))
    statuses = [run_section["status"], shared_section["status"]]
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_data_deletion_plan",
        "status": _overall_status(statuses),
        "confirmations": {
            "run_artifacts": RUN_ARTIFACT_DELETE_CONFIRMATION,
            "shared_data": SHARED_DATA_DELETE_CONFIRMATION,
        },
        "run_artifacts": run_section,
        "shared_data": shared_section,
        "cleanup_candidates": cleanup_candidates,
        "warnings": [
            *run_section.get("warnings", []),
            *shared_section.get("warnings", []),
        ],
        "errors": [
            *run_section.get("errors", []),
            *shared_section.get("errors", []),
        ],
        "omitted": {
            "absolute_local_paths_embedded": False,
            "raw_shared_data_embedded": False,
            "run_artifact_contents_embedded": False,
        },
    }


def dashboard_delete_data(
    config: dict[str, Any],
    *,
    config_path: Path,
    request: dict[str, Any],
    runs_payload: dict[str, Any],
    stores_payload: dict[str, Any],
) -> dict[str, Any]:
    kind = request.get("kind")
    if kind == "run_artifacts":
        return _delete_run_artifacts(
            config,
            config_path=config_path,
            request=request,
            runs_payload=runs_payload,
            stores_payload=stores_payload,
        )
    if kind == "shared_data":
        return _delete_shared_data(
            config,
            config_path=config_path,
            request=request,
            runs_payload=runs_payload,
            stores_payload=stores_payload,
        )
    return _deletion_result(
        kind=str(kind or "unknown"),
        status="failed",
        errors=["kind must be run_artifacts or shared_data."],
    )


def _run_artifact_deletion_section(
    config: dict[str, Any],
    *,
    runs_payload: dict[str, Any],
    base: Path,
) -> dict[str, Any]:
    run_root = _dashboard_run_output_dir(config, base=base)
    root_safe = _safe_ref(run_root, base=base)
    root_blocked = _deletion_root_block_reason(run_root, base=base)
    runs = _list(runs_payload.get("runs"))
    cleanup_candidates = [
        *_cleanup_candidates_from_runs_payload(runs_payload),
        *_nested_run_root_cleanup_candidates(run_root, base=base),
    ][:40]
    items = [
        _run_artifact_delete_item(run, run_root=run_root, root_blocked=root_blocked, base=base)
        for run in runs
        if isinstance(run, dict)
    ]
    blocked_count = sum(1 for item in items if not item["deletable"])
    warnings = _string_list(runs_payload.get("warnings"))
    if root_blocked:
        warnings.append(root_blocked)
    return {
        "status": "partial" if blocked_count else str(runs_payload.get("status") or "unknown"),
        "run_output_dir": root_safe,
        "confirmation_text": RUN_ARTIFACT_DELETE_CONFIRMATION,
        "items": items,
        "counts": {
            "runs": len(items),
            "deletable": sum(1 for item in items if item["deletable"]),
            "blocked": blocked_count,
            "cleanup_candidates": len(cleanup_candidates),
        },
        "cleanup_candidates": cleanup_candidates,
        "warnings": warnings,
        "errors": _string_list(runs_payload.get("errors")),
    }


def _shared_data_deletion_section(
    config: dict[str, Any],
    *,
    stores_payload: dict[str, Any],
    base: Path,
) -> dict[str, Any]:
    stores = _list(stores_payload.get("stores"))
    items = [
        _shared_data_delete_item(store, config=config, base=base)
        for store in stores
        if isinstance(store, dict)
    ]
    blocked_count = sum(1 for item in items if not item["deletable"])
    warnings = [
        "shared data may be reused by multiple reports and future runs; deletion requires explicit confirmation.",
        *_string_list(stores_payload.get("warnings")),
    ]
    return {
        "status": "partial" if blocked_count else str(stores_payload.get("status") or "unknown"),
        "allowed_roots": sorted(SHARED_DATA_ALLOWED_ROOTS),
        "confirmation_text": SHARED_DATA_DELETE_CONFIRMATION,
        "items": items,
        "counts": {
            "stores": len(items),
            "deletable": sum(1 for item in items if item["deletable"]),
            "blocked": blocked_count,
        },
        "warnings": warnings,
        "errors": _string_list(stores_payload.get("errors")),
    }


def _cleanup_candidate_section(items: list[Any]) -> dict[str, Any]:
    candidates = [item for item in items if isinstance(item, dict)]
    return {
        "status": "available" if candidates else "empty",
        "items": candidates[:20],
        "counts": {
            "items": len(candidates),
            "run_index_refs": sum(1 for item in candidates if item.get("kind") == "run_index_ref"),
            "missing_report_refs": sum(1 for item in candidates if item.get("kind") == "missing_report_ref"),
            "nested_run_roots": sum(1 for item in candidates if item.get("kind") == "nested_run_root"),
        },
        "warnings": [],
        "errors": [],
    }


def _cleanup_candidates_from_runs_payload(runs_payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in _list(runs_payload.get("index_diagnostics")):
        if not isinstance(item, dict):
            continue
        candidates.append(
            {
                "kind": "run_index_ref",
                "run_id": item.get("run_id"),
                "reason": "run index row references missing run artifacts.",
                "missing": _string_list(item.get("missing")),
                "refs": _unique_refs([item.get("run_dir"), item.get("manifest")]),
            }
        )
    for item in _list(runs_payload.get("report_diagnostics")):
        if not isinstance(item, dict):
            continue
        candidates.append(
            {
                "kind": "missing_report_ref",
                "run_id": item.get("run_id"),
                "reason": "recorded report artifact is missing and omitted from report lists.",
                "missing": ["report"],
                "refs": _unique_refs([item.get("artifact")]),
            }
        )
    return candidates[:40]


def _nested_run_root_cleanup_candidates(run_root: Path, *, base: Path) -> list[dict[str, Any]]:
    nested_root = run_root / run_root.name
    if not nested_root.is_dir():
        return []
    manifests = sorted(nested_root.glob("*/run_manifest.json"))
    if not manifests:
        return []
    return [
        {
            "kind": "nested_run_root",
            "run_id": None,
            "reason": "nested run root is outside indexed run history and requires explicit review before cleanup.",
            "missing": [],
            "refs": [_safe_ref(nested_root, base=base), *[_safe_ref(path, base=base) for path in manifests[:5]]],
            "counts": {
                "run_manifests": len(manifests),
                "sample_refs": min(len(manifests), 5),
            },
            "indexed": False,
        }
    ]


def _run_artifact_delete_item(
    run: dict[str, Any],
    *,
    run_root: Path,
    root_blocked: str | None,
    base: Path,
) -> dict[str, Any]:
    run_id = str(run.get("run_id") or "")
    target, safe_ref, reason = _resolve_deletion_ref(str(run.get("run_dir") or ""), base=base)
    blocked_reason = root_blocked or reason
    if not blocked_reason and target is not None:
        if not _is_path_within(target, run_root):
            blocked_reason = "run directory is outside the configured run output directory."
        elif _same_path(target, run_root):
            blocked_reason = "run output root cannot be deleted from a run selection."
    return {
        "run_id": run_id,
        "title": run_id,
        "status": str(run.get("status") or "unknown"),
        "started_at": run.get("started_at"),
        "finished_at": run.get("finished_at"),
        "warning_count": _int(run.get("warning_count")),
        "error_count": _int(run.get("error_count")),
        "run_dir": safe_ref,
        "manifest": run.get("manifest"),
        "exists": bool(target and target.exists()),
        "deletable": blocked_reason is None,
        "blocked_reason": blocked_reason,
    }


def _shared_data_delete_item(
    store: dict[str, Any],
    *,
    config: dict[str, Any],
    base: Path,
) -> dict[str, Any]:
    name = str(store.get("name") or "")
    refs = _shared_store_delete_refs(name, store, config=config)
    records = [_shared_delete_ref_record(ref, base=base) for ref in refs]
    existing_records = [record for record in records if record["exists"]]
    blocked_records = [record for record in records if not record["deletable"]]
    blocked_reason = None
    if blocked_records:
        blocked_reason = "one or more refs are outside the shared-data deletion boundary."
    elif not existing_records:
        blocked_reason = "no existing shared data refs were found for this store."
    return {
        "name": name,
        "title": str(store.get("title") or name),
        "status": str(store.get("status") or "unknown"),
        "group": _data_store_category(name),
        "records": _int(_dict(store.get("fields")).get("records")),
        "delete_refs": records,
        "deletable": blocked_reason is None,
        "blocked_reason": blocked_reason,
        "warnings": _string_list(store.get("warnings")),
        "errors": _string_list(store.get("errors")),
    }


def _shared_store_delete_refs(name: str, store: dict[str, Any], *, config: dict[str, Any]) -> list[str]:
    refs: list[str] = list(SHARED_DATA_STORE_DELETE_REFS.get(name, ()))
    if name == "ohlcv_history":
        refs.extend(_configured_ohlcv_storage_refs(config))
    if name == "outcome_history":
        fields = _dict(store.get("fields"))
        refs.extend(
            str(value)
            for value in (fields.get("history"), fields.get("storage_path"))
            if isinstance(value, str) and value
        )
    return _unique_refs(refs)


def _configured_ohlcv_storage_refs(config: dict[str, Any]) -> list[str]:
    market = config.get("market") if isinstance(config.get("market"), dict) else {}
    ohlcv = market.get("ohlcv") if isinstance(market.get("ohlcv"), dict) else {}
    storage_dir = ohlcv.get("storage_dir")
    return [storage_dir] if isinstance(storage_dir, str) and storage_dir.strip() else []


def _shared_delete_ref_record(ref: str, *, base: Path) -> dict[str, Any]:
    target, safe_ref, reason = _resolve_deletion_ref(ref, base=base)
    blocked_reason = reason
    if not blocked_reason and target is not None:
        parts = Path(safe_ref).parts
        if not parts or parts[0] not in SHARED_DATA_ALLOWED_ROOTS:
            blocked_reason = "shared data deletion is limited to configured project data refs."
        elif len(parts) == 1:
            blocked_reason = "shared data root cannot be deleted as one operation."
    return {
        "ref": safe_ref,
        "exists": bool(target and target.exists()),
        "kind": "directory" if target and target.exists() and target.is_dir() and not target.is_symlink() else "file",
        "deletable": blocked_reason is None,
        "blocked_reason": blocked_reason,
    }


def _delete_run_artifacts(
    config: dict[str, Any],
    *,
    config_path: Path,
    request: dict[str, Any],
    runs_payload: dict[str, Any],
    stores_payload: dict[str, Any],
) -> dict[str, Any]:
    if request.get("confirm") != RUN_ARTIFACT_DELETE_CONFIRMATION:
        return _deletion_result(
            kind="run_artifacts",
            status="blocked",
            errors=["confirmation text does not match run artifact deletion requirement."],
        )
    requested_ids = _unique_refs(str(item) for item in _list(request.get("run_ids")) if isinstance(item, str))
    if not requested_ids:
        return _deletion_result(
            kind="run_artifacts",
            status="failed",
            errors=["run_ids must contain at least one run id."],
        )

    base = artifact_base(config_path)
    plan = dashboard_data_deletion_plan(
        config,
        config_path=config_path,
        runs_payload=runs_payload,
        stores_payload=stores_payload,
    )
    candidates = {
        str(item.get("run_id")): item
        for item in _list(_dict(plan.get("run_artifacts")).get("items"))
        if isinstance(item, dict)
    }
    deleted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    index_deleted_ids: list[str] = []

    for run_id in requested_ids:
        item = candidates.get(run_id)
        if item is None:
            blocked.append({"id": run_id, "reason": "run id is not present in the deletion plan."})
            continue
        if not item.get("deletable"):
            blocked.append({"id": run_id, "reason": item.get("blocked_reason") or "run is not deletable."})
            continue
        target, safe_ref, reason = _resolve_deletion_ref(str(item.get("run_dir") or ""), base=base)
        if reason or target is None:
            blocked.append({"id": run_id, "reason": reason or "run directory could not be resolved."})
            continue
        error = _delete_local_path(target)
        if error:
            blocked.append({"id": run_id, "ref": safe_ref, "reason": error})
            continue
        if item.get("exists"):
            deleted.append({"id": run_id, "ref": safe_ref})
        else:
            skipped.append({"id": run_id, "ref": safe_ref, "reason": "run directory was already missing."})
        index_deleted_ids.append(run_id)

    index_result = _delete_run_index_records(config_path, index_deleted_ids)
    warnings = _string_list(index_result.get("warnings"))
    errors = _string_list(index_result.get("errors"))
    status = _deletion_status(deleted=deleted, skipped=skipped, blocked=blocked, errors=errors)
    return _deletion_result(
        kind="run_artifacts",
        status=status,
        deleted=deleted,
        skipped=skipped,
        blocked=blocked,
        warnings=warnings,
        errors=errors,
        index=index_result,
    )


def _delete_shared_data(
    config: dict[str, Any],
    *,
    config_path: Path,
    request: dict[str, Any],
    runs_payload: dict[str, Any],
    stores_payload: dict[str, Any],
) -> dict[str, Any]:
    if request.get("confirm") != SHARED_DATA_DELETE_CONFIRMATION:
        return _deletion_result(
            kind="shared_data",
            status="blocked",
            errors=["confirmation text does not match shared data deletion requirement."],
        )
    requested_names = _unique_refs(str(item) for item in _list(request.get("store_names")) if isinstance(item, str))
    if not requested_names:
        return _deletion_result(
            kind="shared_data",
            status="failed",
            errors=["store_names must contain at least one shared data store name."],
        )

    base = artifact_base(config_path)
    plan = dashboard_data_deletion_plan(
        config,
        config_path=config_path,
        runs_payload=runs_payload,
        stores_payload=stores_payload,
    )
    candidates = {
        str(item.get("name")): item
        for item in _list(_dict(plan.get("shared_data")).get("items"))
        if isinstance(item, dict)
    }
    deleted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []

    for name in requested_names:
        item = candidates.get(name)
        if item is None:
            blocked.append({"id": name, "reason": "store name is not present in the deletion plan."})
            continue
        if not item.get("deletable"):
            blocked.append({"id": name, "reason": item.get("blocked_reason") or "store is not deletable."})
            continue
        for record in _list(item.get("delete_refs")):
            if not isinstance(record, dict):
                continue
            ref = str(record.get("ref") or "")
            if not record.get("deletable"):
                blocked.append(
                    {"id": name, "ref": ref, "reason": record.get("blocked_reason") or "ref is not deletable."}
                )
                continue
            target, safe_ref, reason = _resolve_deletion_ref(ref, base=base)
            if reason or target is None:
                blocked.append({"id": name, "ref": ref, "reason": reason or "ref could not be resolved."})
                continue
            if not target.exists() and not target.is_symlink():
                skipped.append({"id": name, "ref": safe_ref, "reason": "ref was already missing."})
                continue
            error = _delete_local_path(target)
            if error:
                blocked.append({"id": name, "ref": safe_ref, "reason": error})
            else:
                deleted.append({"id": name, "ref": safe_ref})

    status = _deletion_status(deleted=deleted, skipped=skipped, blocked=blocked, errors=[])
    return _deletion_result(
        kind="shared_data",
        status=status,
        deleted=deleted,
        skipped=skipped,
        blocked=blocked,
        warnings=["shared data deletion completed only for explicitly selected, project-local refs."],
    )


def _deletion_result(
    *,
    kind: str,
    status: str,
    deleted: list[dict[str, Any]] | None = None,
    skipped: list[dict[str, Any]] | None = None,
    blocked: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "schema_version": 1,
        "artifact_type": "dashboard_data_deletion_result",
        "kind": kind,
        "status": status,
        "deleted": deleted or [],
        "skipped": skipped or [],
        "blocked": blocked or [],
        "warnings": warnings or [],
        "errors": errors or [],
        "omitted": {
            "absolute_local_paths_embedded": False,
            "deleted_contents_embedded": False,
        },
    }
    if index is not None:
        result["index"] = index
    return result


def _deletion_status(
    *,
    deleted: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    blocked: list[dict[str, Any]],
    errors: list[str],
) -> str:
    if errors:
        return "failed"
    if blocked and not (deleted or skipped):
        return "blocked"
    if blocked:
        return "partial"
    if deleted or skipped:
        return "succeeded"
    return "missing"


def _delete_run_index_records(config_path: Path, run_ids: list[str]) -> dict[str, Any]:
    if not run_ids:
        return {"status": "skipped", "deleted_run_ids": [], "warnings": [], "errors": []}
    index_path = run_index_path(config_path)
    if not index_path.exists():
        return {
            "status": "missing",
            "deleted_run_ids": [],
            "warnings": ["local run index was not found."],
            "errors": [],
        }
    deleted: list[str] = []
    try:
        with closing(sqlite3.connect(index_path)) as connection:
            with connection:
                connection.execute("PRAGMA foreign_keys = ON")
                for run_id in run_ids:
                    row = connection.execute("SELECT run_id FROM runs WHERE run_id = ?", (run_id,)).fetchone()
                    if row is None:
                        continue
                    connection.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))
                    deleted.append(run_id)
    except sqlite3.Error as exc:
        return {
            "status": "failed",
            "deleted_run_ids": deleted,
            "warnings": [],
            "errors": [f"{RUN_INDEX_ARTIFACT} could not be updated: {exc}"],
        }
    return {"status": "succeeded", "deleted_run_ids": deleted, "warnings": [], "errors": []}


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


def _delete_local_path(path: Path) -> str | None:
    try:
        if path.is_symlink() or path.is_file():
            path.unlink()
            return None
        if path.is_dir():
            shutil.rmtree(path)
            return None
        return None
    except OSError as exc:
        detail = exc.strerror or exc.__class__.__name__
        return f"{path.name} could not be deleted: {detail}"


def _dashboard_run_output_dir(config: dict[str, Any], *, base: Path) -> Path:
    run = config.get("run") if isinstance(config.get("run"), dict) else {}
    output_dir = Path(str(run.get("output_dir") or "runs"))
    return output_dir if output_dir.is_absolute() else base / output_dir


def _deletion_root_block_reason(path: Path, *, base: Path) -> str | None:
    if not _is_path_within(path, base):
        return "configured deletion root is outside the project boundary."
    return None


def _resolve_deletion_ref(ref: str, *, base: Path) -> tuple[Path | None, str, str | None]:
    raw = str(ref or "").replace("\\", "/").strip()
    if not raw:
        return None, "", "ref is required."
    if raw == EXTERNAL_ARTIFACT_REF:
        return None, EXTERNAL_ARTIFACT_REF, "external artifact refs cannot be deleted from the dashboard."
    path = Path(raw)
    if not path.is_absolute() and any(part in {"", ".", ".."} for part in path.parts):
        return None, raw, "ref must not contain traversal segments."
    target = path if path.is_absolute() else base / path
    try:
        resolved = target.resolve()
        resolved.relative_to(base.resolve())
    except (OSError, ValueError):
        return None, EXTERNAL_ARTIFACT_REF, "ref must stay under the configured project root."
    return target, _safe_ref(resolved, base=base), None


def _is_path_within(path: Path, root: Path) -> bool:
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


def _unique_refs(values: Any) -> list[str]:
    unique: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        clean = value.strip()
        if clean and clean not in unique:
            unique.append(clean)
    return unique


def _safe_ref(path: Path, *, base: Path) -> str:
    return safe_local_ref(
        path,
        base=base,
        external_ref=EXTERNAL_ARTIFACT_REF,
        rejected_name=REJECTED_EXTERNAL_REF_NAME,
    )


def _data_store_category(name: str) -> str:
    if "ohlcv" in name:
        return "market"
    if "derivatives" in name:
        return "derivatives"
    if "macro" in name:
        return "macro_calendar"
    if "onchain" in name:
        return "onchain"
    if "text" in name:
        return "text"
    if "outcome" in name:
        return "outcome"
    return "system"


def _overall_status(statuses: list[str]) -> str:
    normalized = [str(status or "unknown").lower() for status in statuses]
    if any(status == "failed" for status in normalized):
        return "failed"
    if any(status in {"error", "critical"} for status in normalized):
        return "failed"
    if any(status in {"degraded", "warning"} for status in normalized):
        return "warning"
    if any(status in {"partial", "missing", "unknown"} for status in normalized):
        return "partial"
    if any(status in {"available", "ok", "succeeded", "success"} for status in normalized):
        return "available"
    return "unknown"
