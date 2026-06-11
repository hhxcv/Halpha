from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .pipeline import RunContext
from .storage import display_path, write_json


CATALOG_SCHEMA_VERSION = 1
CATALOG_ARTIFACT = "data/research/metadata/research_data_catalog.json"


def write_research_data_catalog(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    catalog_path = research_data_catalog_path(run.config_path)
    catalog = build_research_data_catalog(config, run, now=now)
    write_json(catalog_path, catalog)

    run.manifest["artifacts"]["research_data_catalog"] = CATALOG_ARTIFACT
    run.manifest["research_data_catalog"] = {
        "status": catalog["status"],
        "artifact": CATALOG_ARTIFACT,
        "store_count": catalog["counts"]["stores"],
        "record_count": catalog["counts"]["records"],
        "warning_count": catalog["counts"]["warnings"],
        "error_count": catalog["counts"]["errors"],
    }
    run.manifest["counts"]["research_data_catalog_stores"] = catalog["counts"]["stores"]
    run.manifest["counts"]["research_data_catalog_records"] = catalog["counts"]["records"]
    run.manifest["counts"]["research_data_catalog_warnings"] = catalog["counts"]["warnings"]
    run.manifest["counts"]["research_data_catalog_errors"] = catalog["counts"]["errors"]
    return [CATALOG_ARTIFACT]


def build_research_data_catalog(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> dict[str, Any]:
    stores = []
    warnings = []
    errors = []

    for store in (
        _ohlcv_store_record(config, run),
        _run_index_store_record(run),
        _text_event_history_store_record(run),
        _outcome_history_store_record(run),
    ):
        if store is None:
            continue
        stores.append(store)
        warnings.extend(store["warnings"])
        errors.extend(store["errors"])

    status = _overall_status(stores=stores, warnings=warnings, errors=errors)
    return {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "artifact_type": "research_data_catalog",
        "generated_at": _format_utc(now),
        "status": status,
        "stores": sorted(stores, key=lambda store: str(store["name"])),
        "counts": {
            "stores": len(stores),
            "records": sum(_int(store.get("record_count")) for store in stores),
            "warnings": len(warnings),
            "errors": len(errors),
        },
        "warnings": _unique_sorted(warnings),
        "errors": errors,
    }


def research_data_catalog_path(config_path: Path) -> Path:
    return config_path.parent / CATALOG_ARTIFACT


def _ohlcv_store_record(config: dict[str, Any], run: RunContext) -> dict[str, Any] | None:
    market = config.get("market", {})
    ohlcv = market.get("ohlcv")
    if not market.get("enabled") or not isinstance(ohlcv, dict):
        return None

    storage_dir = _storage_dir(ohlcv, run.config_path)
    metadata_dir = storage_dir.parent / "metadata"
    schema_path = metadata_dir / "ohlcv_schema.json"
    state_path = metadata_dir / "ohlcv_sync_state.json"
    schema = _read_json_object(schema_path)
    state = _read_json_object(state_path)
    sync_summary = run.manifest.get("ohlcv_sync")
    warnings: list[str] = []
    errors: list[dict[str, Any]] = []

    if schema is None:
        warnings.append("shared OHLCV schema metadata is missing.")
    if state is None:
        warnings.append("shared OHLCV sync state metadata is missing.")
    if isinstance(sync_summary, dict):
        warnings.extend(_string_list(sync_summary.get("warnings")))
        errors.extend(_error_list(sync_summary.get("errors")))

    items = state.get("items") if isinstance(state, dict) else []
    if not isinstance(items, list):
        items = []
        warnings.append("shared OHLCV sync state items must be a list.")

    source_fields = ["source"]
    source_names = sorted(
        {
            str(item.get("source"))
            for item in items
            if isinstance(item, dict) and isinstance(item.get("source"), str) and item.get("source")
        }
    )
    warning_count = len(warnings)
    error_count = len(errors)
    return {
        "name": "ohlcv_history",
        "kind": "market_ohlcv_history",
        "status": _store_status(sync_summary, warning_count=warning_count, error_count=error_count),
        "format": "parquet",
        "storage_path": display_path(storage_dir, base=run.config_path.parent),
        "schema_path": display_path(schema_path, base=run.config_path.parent),
        "state_path": display_path(state_path, base=run.config_path.parent),
        "schema_version": schema.get("schema_version") if isinstance(schema, dict) else None,
        "partition_fields": ["source", "symbol", "timeframe", "year", "month"],
        "unique_key_fields": _string_list(schema.get("unique_key")) if isinstance(schema, dict) else [],
        "source_fields": source_fields,
        "sources": source_names,
        "latest_update_at": state.get("updated_at") if isinstance(state, dict) else None,
        "record_count": sum(_int(item.get("row_count")) for item in items if isinstance(item, dict)),
        "warning_count": warning_count,
        "error_count": error_count,
        "consumers": [
            "raw/market_data_views.json",
            "analysis/strategy_benchmark_suite.json",
            "analysis/quant_strategy_runs.json",
            "standalone_backtest",
            "standalone_strategy_experiment",
        ],
        "source_artifacts": [
            display_path(schema_path, base=run.config_path.parent),
            display_path(state_path, base=run.config_path.parent),
        ],
        "warnings": _unique_sorted(warnings),
        "errors": errors,
    }


def _run_index_store_record(run: RunContext) -> dict[str, Any] | None:
    index_summary = run.manifest.get("run_index")
    if not isinstance(index_summary, dict):
        return None
    index_path = run.config_path.parent / "data" / "research" / "index.sqlite"
    if not index_path.exists() and index_summary.get("status") != "failed":
        return None

    status = str(index_summary.get("status") or "degraded")
    warnings = _string_list(index_summary.get("warnings"))
    errors = []
    if status == "failed":
        message = index_summary.get("error")
        errors.append({"message": str(message or "run index write failed")})

    tables = index_summary.get("tables")
    runs = _int(tables.get("runs")) if isinstance(tables, dict) else 0
    return {
        "name": "run_index",
        "kind": "run_audit_index",
        "status": status,
        "format": "sqlite",
        "storage_path": display_path(index_path, base=run.config_path.parent),
        "schema_path": None,
        "state_path": display_path(index_path, base=run.config_path.parent),
        "schema_version": index_summary.get("schema_version"),
        "partition_fields": [],
        "unique_key_fields": ["run_id"],
        "source_fields": [],
        "sources": [],
        "latest_update_at": index_summary.get("updated_at"),
        "record_count": runs,
        "warning_count": len(warnings),
        "error_count": len(errors),
        "consumers": [
            "previous_run_lookup",
            "data_inspection",
            "audit",
        ],
        "source_artifacts": [display_path(index_path, base=run.config_path.parent)],
        "warnings": warnings,
        "errors": errors,
    }


def _text_event_history_store_record(run: RunContext) -> dict[str, Any] | None:
    state_path = run.config_path.parent / "data" / "research" / "metadata" / "text_event_history_state.json"
    storage_path = run.config_path.parent / "data" / "research" / "text_events"
    state = _read_json_object(state_path)
    summary = run.manifest.get("text_event_history")
    if state is None and not isinstance(summary, dict):
        return None

    warnings = _string_list(state.get("warnings")) if isinstance(state, dict) else []
    errors = _error_list(state.get("errors")) if isinstance(state, dict) else []
    totals = state.get("totals") if isinstance(state, dict) else {}
    return {
        "name": "text_event_history",
        "kind": "text_event_history",
        "status": state.get("status") if isinstance(state, dict) else summary.get("status"),
        "format": "parquet",
        "storage_path": display_path(storage_path, base=run.config_path.parent),
        "schema_path": None,
        "state_path": display_path(state_path, base=run.config_path.parent),
        "schema_version": state.get("schema_version") if isinstance(state, dict) else None,
        "partition_fields": ["source", "year", "month"],
        "unique_key_fields": ["stable_event_key"],
        "source_fields": ["source"],
        "sources": _history_sources(state),
        "latest_update_at": state.get("updated_at") if isinstance(state, dict) else None,
        "record_count": _int(totals.get("records")) if isinstance(totals, dict) else 0,
        "warning_count": len(warnings),
        "error_count": len(errors),
        "consumers": [
            "data_quality_summary",
            "future_event_workflows",
            "future_outcome_workflows",
        ],
        "source_artifacts": [display_path(state_path, base=run.config_path.parent)],
        "warnings": warnings,
        "errors": errors,
    }


def _outcome_history_store_record(run: RunContext) -> dict[str, Any] | None:
    state_path = run.config_path.parent / "data" / "research" / "metadata" / "outcome_history_state.json"
    storage_path = run.config_path.parent / "data" / "research" / "outcomes"
    history_path = storage_path / "outcome_history.json"
    state = _read_json_object(state_path)
    summary = run.manifest.get("outcome_history")
    if state is None and not isinstance(summary, dict):
        return None
    if state is None and isinstance(summary, dict) and summary.get("status") != "failed":
        return None

    totals = state.get("totals") if isinstance(state, dict) else {}
    if isinstance(state, dict) and state.get("status") == "skipped" and _int(totals.get("records")) == 0:
        return None

    warnings = _string_list(state.get("warnings")) if isinstance(state, dict) else []
    errors = _error_list(state.get("errors")) if isinstance(state, dict) else []
    if isinstance(summary, dict) and summary.get("status") == "failed":
        errors.append({"message": str(summary.get("error") or "outcome history write failed")})
    return {
        "name": "outcome_history",
        "kind": "outcome_history",
        "status": state.get("status") if isinstance(state, dict) else summary.get("status"),
        "format": "json",
        "storage_path": display_path(storage_path, base=run.config_path.parent),
        "schema_path": None,
        "state_path": display_path(state_path, base=run.config_path.parent),
        "schema_version": state.get("schema_version") if isinstance(state, dict) else None,
        "partition_fields": [],
        "unique_key_fields": ["stable_outcome_key"],
        "source_fields": ["source_run_id", "evaluation_run_id", "target_kind"],
        "sources": _outcome_sources(state),
        "latest_update_at": state.get("updated_at") if isinstance(state, dict) else None,
        "record_count": _int(totals.get("records")) if isinstance(totals, dict) else 0,
        "warning_count": len(warnings),
        "error_count": len(errors),
        "consumers": [
            "data_inspection",
            "analysis/outcome_tracking_material.md",
            "future_research_calibration",
        ],
        "source_artifacts": [
            display_path(history_path, base=run.config_path.parent),
            display_path(state_path, base=run.config_path.parent),
        ],
        "warnings": warnings,
        "errors": errors,
    }


def _history_sources(state: dict[str, Any] | None) -> list[str]:
    sources = state.get("sources") if isinstance(state, dict) else None
    if not isinstance(sources, list):
        return []
    return sorted(
        {
            str(source.get("source"))
            for source in sources
            if isinstance(source, dict) and isinstance(source.get("source"), str) and source.get("source")
        }
    )


def _outcome_sources(state: dict[str, Any] | None) -> list[str]:
    sources = state.get("sources") if isinstance(state, dict) else None
    if not isinstance(sources, list):
        return []
    return sorted(
        {
            str(source.get("source_run_id"))
            for source in sources
            if isinstance(source, dict) and isinstance(source.get("source_run_id"), str) and source.get("source_run_id")
        }
    )


def _storage_dir(ohlcv: dict[str, Any], config_path: Path) -> Path:
    storage_dir = Path(str(ohlcv["storage_dir"]))
    if storage_dir.is_absolute():
        return storage_dir
    return config_path.parent / storage_dir


def _read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if not isinstance(loaded, dict):
        return None
    return loaded


def _store_status(
    sync_summary: Any,
    *,
    warning_count: int,
    error_count: int,
) -> str:
    if error_count:
        return "failed"
    if not isinstance(sync_summary, dict):
        return "degraded" if warning_count else "warning"
    sync_status = sync_summary.get("status")
    if sync_status == "failed":
        return "failed"
    if sync_status == "skipped":
        return "skipped"
    if warning_count:
        return "warning"
    return "ok"


def _overall_status(
    *,
    stores: list[dict[str, Any]],
    warnings: list[str],
    errors: list[dict[str, Any]],
) -> str:
    if not stores and not errors:
        return "skipped"
    if errors:
        return "failed"
    statuses = {str(store.get("status")) for store in stores}
    if "failed" in statuses:
        return "failed"
    if "degraded" in statuses:
        return "degraded"
    if warnings or "warning" in statuses:
        return "warning"
    if statuses == {"skipped"}:
        return "skipped"
    return "ok"


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("generated_at must include a UTC offset.")
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str):
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("generated_at must be an ISO 8601 UTC string.") from exc
        if timestamp.tzinfo is None:
            raise ValueError("generated_at must include a UTC offset.")
        timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)
    else:
        raise ValueError("generated_at must be a datetime or ISO 8601 UTC string.")
    return timestamp.isoformat().replace("+00:00", "Z")


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item]


def _error_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    return 0


def _unique_sorted(values: list[str]) -> list[str]:
    return sorted(set(values))
