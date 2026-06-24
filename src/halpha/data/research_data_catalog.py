from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from halpha.data.run_index import run_index_path
from halpha.runtime.pipeline_contracts import RunContext
from halpha.shared_publication import (
    OUTCOME_HISTORY_STATE_ARTIFACT,
    RESEARCH_DATA_CATALOG_ARTIFACT,
    read_staged_payload,
    stage_shared_payloads,
)
from halpha.storage import display_path, write_json


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
    record_research_data_catalog_manifest_summary(run, catalog)
    return [CATALOG_ARTIFACT]


def prepare_research_data_catalog_publication(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    outcome_state = read_staged_payload(run, OUTCOME_HISTORY_STATE_ARTIFACT)
    catalog = build_research_data_catalog(config, run, now=now, outcome_history_state=outcome_state)
    stage_shared_payloads(
        run,
        group="research_data_catalog",
        payloads={RESEARCH_DATA_CATALOG_ARTIFACT: catalog},
    )
    return []


def record_research_data_catalog_manifest_summary(run: RunContext, catalog: dict[str, Any]) -> None:
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


def build_research_data_catalog(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
    outcome_history_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stores = []
    warnings = []
    errors = []

    for store in (
        _ohlcv_store_record(config, run),
        _derivatives_market_history_store_record(run),
        _macro_calendar_history_store_record(run),
        _onchain_flow_history_store_record(run),
        _run_index_store_record(run),
        _text_event_history_store_record(run),
        _outcome_history_store_record(run, candidate_state=outcome_history_state),
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
    index_path = run_index_path(run.config_path)
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


def _derivatives_market_history_store_record(run: RunContext) -> dict[str, Any] | None:
    state_path = run.config_path.parent / "data" / "market" / "metadata" / "derivatives_market_state.json"
    schema_path = run.config_path.parent / "data" / "market" / "metadata" / "derivatives_market_schema.json"
    storage_path = run.config_path.parent / "data" / "market" / "derivatives"
    state = _read_json_object(state_path)
    summary = run.manifest.get("derivatives_market_history")
    if state is None and (
        not isinstance(summary, dict) or summary.get("status") != "failed"
    ):
        return None

    warnings = _string_list(state.get("warnings")) if isinstance(state, dict) else []
    errors = _error_list(state.get("errors")) if isinstance(state, dict) else []
    if state is None:
        errors.append({"message": "derivatives market history state metadata is missing."})
    totals = state.get("totals") if isinstance(state, dict) else {}
    groups = state.get("groups") if isinstance(state, dict) else []
    schema = _read_json_object(schema_path)
    if schema is None and isinstance(state, dict) and state.get("status") != "skipped":
        warnings.append("derivatives market schema metadata is missing.")

    return {
        "name": "derivatives_market_history",
        "kind": "derivatives_market_history",
        "status": state.get("status") if isinstance(state, dict) else summary.get("status"),
        "format": "json",
        "storage_path": display_path(storage_path, base=run.config_path.parent),
        "schema_path": display_path(schema_path, base=run.config_path.parent),
        "state_path": display_path(state_path, base=run.config_path.parent),
        "schema_version": state.get("schema_version") if isinstance(state, dict) else None,
        "partition_fields": ["source", "data_class", "symbol", "period"],
        "unique_key_fields": _string_list(schema.get("identity")) if isinstance(schema, dict) else [
            "source",
            "market_type",
            "data_class",
            "symbol",
            "period",
            "as_of",
        ],
        "source_fields": ["source", "market_type", "data_class", "symbol", "period"],
        "sources": _derivatives_sources(state),
        "latest_update_at": state.get("updated_at") if isinstance(state, dict) else None,
        "record_count": _int(totals.get("records")) if isinstance(totals, dict) else 0,
        "warning_count": len(warnings),
        "error_count": len(errors),
        "consumers": [
            "raw/derivatives_market_views.json",
            "data_quality_summary",
            "data_inspection",
            "future_derivatives_context",
        ],
        "source_artifacts": [
            display_path(schema_path, base=run.config_path.parent),
            display_path(state_path, base=run.config_path.parent),
        ],
        "details": {
            "groups": len(groups) if isinstance(groups, list) else 0,
            "incoming_records": _int(totals.get("incoming_records")) if isinstance(totals, dict) else 0,
            "duplicate_records": _int(totals.get("duplicate_records")) if isinstance(totals, dict) else 0,
            "conflicting_duplicates": _int(totals.get("conflicting_duplicates")) if isinstance(totals, dict) else 0,
        },
        "warnings": _unique_sorted(warnings),
        "errors": errors,
    }


def _macro_calendar_history_store_record(run: RunContext) -> dict[str, Any] | None:
    state_path = run.config_path.parent / "data" / "macro" / "metadata" / "macro_calendar_state.json"
    schema_path = run.config_path.parent / "data" / "macro" / "metadata" / "macro_calendar_schema.json"
    storage_path = run.config_path.parent / "data" / "macro" / "calendar"
    state = _read_json_object(state_path)
    summary = run.manifest.get("macro_calendar_history")
    if state is None and (
        not isinstance(summary, dict) or summary.get("status") != "failed"
    ):
        return None

    warnings = _string_list(state.get("warnings")) if isinstance(state, dict) else []
    errors = _error_list(state.get("errors")) if isinstance(state, dict) else []
    if state is None:
        errors.append({"message": "macro calendar state metadata is missing."})
    totals = state.get("totals") if isinstance(state, dict) else {}
    groups = state.get("groups") if isinstance(state, dict) else []
    schema = _read_json_object(schema_path)
    if schema is None and isinstance(state, dict) and state.get("status") != "skipped":
        warnings.append("macro calendar schema metadata is missing.")

    return {
        "name": "macro_calendar_history",
        "kind": "macro_calendar_history",
        "status": state.get("status") if isinstance(state, dict) else summary.get("status"),
        "format": "json",
        "storage_path": display_path(storage_path, base=run.config_path.parent),
        "schema_path": display_path(schema_path, base=run.config_path.parent),
        "state_path": display_path(state_path, base=run.config_path.parent),
        "schema_version": state.get("schema_version") if isinstance(state, dict) else None,
        "partition_fields": ["source", "data_class", "region"],
        "unique_key_fields": _string_list(schema.get("identity")) if isinstance(schema, dict) else [
            "source",
            "data_class",
            "region",
            "event_name",
            "scheduled_at",
        ],
        "source_fields": ["source", "data_class", "region"],
        "sources": _macro_calendar_sources(state),
        "latest_update_at": state.get("updated_at") if isinstance(state, dict) else None,
        "record_count": _int(totals.get("records")) if isinstance(totals, dict) else 0,
        "warning_count": len(warnings),
        "error_count": len(errors),
        "consumers": [
            "raw/macro_calendar_views.json",
            "future_macro_calendar_context",
            "data_quality_summary",
            "data_inspection",
        ],
        "source_artifacts": [
            display_path(schema_path, base=run.config_path.parent),
            display_path(state_path, base=run.config_path.parent),
        ],
        "details": {
            "groups": len(groups) if isinstance(groups, list) else 0,
            "incoming_records": _int(totals.get("incoming_records")) if isinstance(totals, dict) else 0,
            "duplicate_records": _int(totals.get("duplicate_records")) if isinstance(totals, dict) else 0,
            "conflicting_duplicates": _int(totals.get("conflicting_duplicates")) if isinstance(totals, dict) else 0,
        },
        "warnings": _unique_sorted(warnings),
        "errors": errors,
    }


def _onchain_flow_history_store_record(run: RunContext) -> dict[str, Any] | None:
    state_path = run.config_path.parent / "data" / "onchain" / "metadata" / "onchain_flow_state.json"
    schema_path = run.config_path.parent / "data" / "onchain" / "metadata" / "onchain_flow_schema.json"
    storage_path = run.config_path.parent / "data" / "onchain" / "flow"
    state = _read_json_object(state_path)
    summary = run.manifest.get("onchain_flow_history")
    if state is None and (
        not isinstance(summary, dict) or summary.get("status") != "failed"
    ):
        return None

    warnings = _string_list(state.get("warnings")) if isinstance(state, dict) else []
    errors = _error_list(state.get("errors")) if isinstance(state, dict) else []
    if state is None:
        errors.append({"message": "on-chain flow state metadata is missing."})
    totals = state.get("totals") if isinstance(state, dict) else {}
    groups = state.get("groups") if isinstance(state, dict) else []
    schema = _read_json_object(schema_path)
    if schema is None and isinstance(state, dict) and state.get("status") != "skipped":
        warnings.append("on-chain flow schema metadata is missing.")

    return {
        "name": "onchain_flow_history",
        "kind": "onchain_flow_history",
        "status": state.get("status") if isinstance(state, dict) else summary.get("status"),
        "format": "json",
        "storage_path": display_path(storage_path, base=run.config_path.parent),
        "schema_path": display_path(schema_path, base=run.config_path.parent),
        "state_path": display_path(state_path, base=run.config_path.parent),
        "schema_version": state.get("schema_version") if isinstance(state, dict) else None,
        "partition_fields": ["source", "data_class", "asset", "chain"],
        "unique_key_fields": _string_list(schema.get("identity")) if isinstance(schema, dict) else [
            "source",
            "data_class",
            "asset",
            "chain",
            "as_of",
        ],
        "source_fields": ["source", "data_class", "asset", "chain"],
        "sources": _onchain_flow_sources(state),
        "latest_update_at": state.get("updated_at") if isinstance(state, dict) else None,
        "record_count": _int(totals.get("records")) if isinstance(totals, dict) else 0,
        "warning_count": len(warnings),
        "error_count": len(errors),
        "consumers": [
            "raw/onchain_flow_views.json",
            "future_onchain_flow_context",
            "data_quality_summary",
            "data_inspection",
        ],
        "source_artifacts": [
            display_path(schema_path, base=run.config_path.parent),
            display_path(state_path, base=run.config_path.parent),
        ],
        "details": {
            "groups": len(groups) if isinstance(groups, list) else 0,
            "incoming_records": _int(totals.get("incoming_records")) if isinstance(totals, dict) else 0,
            "duplicate_records": _int(totals.get("duplicate_records")) if isinstance(totals, dict) else 0,
            "conflicting_duplicates": _int(totals.get("conflicting_duplicates")) if isinstance(totals, dict) else 0,
        },
        "warnings": _unique_sorted(warnings),
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


def _outcome_history_store_record(
    run: RunContext,
    *,
    candidate_state: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    state_path = run.config_path.parent / "data" / "research" / "metadata" / "outcome_history_state.json"
    storage_path = run.config_path.parent / "data" / "research" / "outcomes"
    history_path = storage_path / "outcome_history.json"
    state = candidate_state if isinstance(candidate_state, dict) else _read_json_object(state_path)
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


def _derivatives_sources(state: dict[str, Any] | None) -> list[str]:
    groups = state.get("groups") if isinstance(state, dict) else None
    if not isinstance(groups, list):
        return []
    return sorted(
        {
            str(group.get("source"))
            for group in groups
            if isinstance(group, dict) and isinstance(group.get("source"), str) and group.get("source")
        }
    )


def _macro_calendar_sources(state: dict[str, Any] | None) -> list[str]:
    groups = state.get("groups") if isinstance(state, dict) else None
    if not isinstance(groups, list):
        return []
    return sorted(
        {
            str(group.get("source"))
            for group in groups
            if isinstance(group, dict) and isinstance(group.get("source"), str) and group.get("source")
        }
    )


def _onchain_flow_sources(state: dict[str, Any] | None) -> list[str]:
    groups = state.get("groups") if isinstance(state, dict) else None
    if not isinstance(groups, list):
        return []
    return sorted(
        {
            str(group.get("source"))
            for group in groups
            if isinstance(group, dict) and isinstance(group.get("source"), str) and group.get("source")
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
