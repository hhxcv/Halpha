from __future__ import annotations

from pathlib import Path
from typing import Any

from halpha.data.data_inspection import DataInspectionError, inspect_local_store_state
from halpha.outcome.outcome_history import OUTCOME_HISTORY_ARTIFACT, OUTCOME_HISTORY_STATE_ARTIFACT
from halpha.storage import artifact_base as _artifact_base, read_json_object
from halpha.utils.value_helpers import (
    as_dict as _dict,
    as_list as _list,
    strict_int as _int,
    stringified_list as _string_list,
)


REJECTED_EXTERNAL_REF_NAME = ".halpha_external_ref_rejected"
MAX_STORE_DRILLDOWN_ITEMS = 12
DATA_STORE_SECTION_NAMES = {
    "research_data_catalog",
    "run_index",
    "text_event_history",
    "ohlcv_history",
    "derivatives_market_history",
    "market_anomaly_history",
    "macro_calendar_history",
    "onchain_flow_history",
}
DATA_STORE_TITLES = {
    "research_data_catalog": "Research data catalog",
    "run_index": "Run index",
    "text_event_history": "Text event history",
    "ohlcv_history": "OHLCV history",
    "derivatives_market_history": "Derivatives market history",
    "market_anomaly_history": "Market anomaly history",
    "macro_calendar_history": "Macro/calendar history",
    "onchain_flow_history": "On-chain flow history",
    "outcome_history": "Outcome history",
}
SAFE_METADATA_PREVIEW_SUFFIXES = {".json", ".md", ".markdown", ".txt", ".yaml", ".yml"}


def _include_dashboard_store_section(section: dict[str, Any]) -> bool:
    if section.get("name") == "market_anomaly_history" and section.get("status") == "skipped":
        return section.get("reason") != "market.anomalies is not enabled."
    return True


def dashboard_data_stores(config: dict[str, Any], *, config_path: Path) -> dict[str, Any]:
    try:
        state = inspect_local_store_state(config, config_path=config_path)
    except DataInspectionError as exc:
        return {
            "schema_version": 1,
            "artifact_type": "dashboard_data_stores",
            "status": "failed",
            "source_artifacts": [],
            "stores": [],
            "warnings": [],
            "errors": [str(exc)],
            "omitted": _data_store_omissions(),
        }

    sections = [
        _dashboard_store_section(section, config_path=config_path)
        for section in _list(state.get("sections"))
        if isinstance(section, dict)
        and section.get("name") in DATA_STORE_SECTION_NAMES
        and _include_dashboard_store_section(section)
    ]
    sections.append(_outcome_history_store_section(config_path))
    statuses = [str(section.get("status") or "unknown") for section in sections]
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_data_stores",
        "status": _dashboard_store_overall_status(statuses),
        "state_scope": "shared_reusable_stores",
        "run_snapshot_scope": "not_included",
        "source_artifacts": sorted(
            {
                artifact
                for section in sections
                for artifact in _string_list(section.get("source_artifacts"))
            }
        ),
        "stores": sections,
        "warnings": [],
        "errors": [],
        "omitted": _data_store_omissions(),
    }


def _dashboard_store_section(section: dict[str, Any], *, config_path: Path) -> dict[str, Any]:
    artifact = section.get("artifact")
    reason = section.get("reason")
    name = str(section.get("name") or "unknown")
    fields = _bounded_mapping(section.get("fields"))
    extra = _bounded_mapping(section.get("extra"))
    source_artifacts = [artifact] if isinstance(artifact, str) and artifact else []
    warnings = [reason] if isinstance(reason, str) and reason else []
    scope = _data_store_scope(name)
    return {
        "name": name,
        "title": DATA_STORE_TITLES.get(name, str(section.get("name") or "Unknown")),
        **scope,
        "status": str(section.get("status") or "unknown"),
        "artifact": artifact if isinstance(artifact, str) else None,
        "preview_path": _metadata_preview_path(artifact),
        "fields": fields,
        "extra": extra,
        "drilldown": _data_store_drilldown(
            name,
            artifact if isinstance(artifact, str) else None,
            fields=fields,
            extra=extra,
            config_path=config_path,
            warnings=warnings,
        ),
        "source_artifacts": source_artifacts,
        "warnings": warnings,
        "errors": [],
    }


def _outcome_history_store_section(config_path: Path) -> dict[str, Any]:
    base = _artifact_base(config_path)
    path = base / OUTCOME_HISTORY_STATE_ARTIFACT
    data, error = _read_json(path)
    if error:
        return {
            "name": "outcome_history",
            "title": DATA_STORE_TITLES["outcome_history"],
            **_data_store_scope("outcome_history"),
            "status": "skipped",
            "artifact": OUTCOME_HISTORY_STATE_ARTIFACT,
            "preview_path": None,
            "fields": {
                "history": OUTCOME_HISTORY_ARTIFACT,
            },
            "extra": {},
            "drilldown": _empty_data_store_drilldown(
                "outcome_history",
                metadata_refs=[OUTCOME_HISTORY_STATE_ARTIFACT],
                warnings=[error],
            ),
            "source_artifacts": [OUTCOME_HISTORY_STATE_ARTIFACT],
            "warnings": [error],
            "errors": [],
        }
    totals = _dict(data.get("totals"))
    fields = {
        "updated_at": data.get("updated_at"),
        "records": _int(totals.get("records")),
        "incoming_records": _int(totals.get("incoming_records")),
        "inserted_records": _int(totals.get("inserted_records")),
        "updated_records": _int(totals.get("updated_records")),
        "duplicate_records": _int(totals.get("duplicate_records")),
        "conflicting_duplicates": _int(totals.get("conflicting_duplicates")),
        "warnings": _int(totals.get("warning_count")),
        "errors": _int(totals.get("error_count")),
        "history": data.get("history_path") or OUTCOME_HISTORY_ARTIFACT,
        "storage_path": data.get("storage_path"),
    }
    return {
        "name": "outcome_history",
        "title": DATA_STORE_TITLES["outcome_history"],
        **_data_store_scope("outcome_history"),
        "status": str(data.get("status") or "unknown"),
        "artifact": OUTCOME_HISTORY_STATE_ARTIFACT,
        "preview_path": OUTCOME_HISTORY_STATE_ARTIFACT,
        "fields": _bounded_mapping(fields),
        "extra": {},
        "drilldown": _data_store_drilldown_from_metadata(
            "outcome_history",
            data,
            fields=_bounded_mapping(fields),
            metadata_refs=[OUTCOME_HISTORY_STATE_ARTIFACT],
            warnings=_string_list(data.get("warnings")),
        ),
        "source_artifacts": [OUTCOME_HISTORY_STATE_ARTIFACT, *_string_list(data.get("source_artifacts"))],
        "warnings": _string_list(data.get("warnings")),
        "errors": _string_list(data.get("errors")),
    }


def _data_store_scope(name: str) -> dict[str, Any]:
    if name == "run_index":
        return {
            "state_scope": "local_run_index",
            "source_label": "Local run index",
            "run_snapshot": False,
        }
    return {
        "state_scope": "shared_reusable_store",
        "source_label": "Shared reusable store",
        "run_snapshot": False,
    }


def _data_store_drilldown(
    name: str,
    artifact: str | None,
    *,
    fields: dict[str, Any],
    extra: dict[str, Any],
    config_path: Path,
    warnings: list[str],
) -> dict[str, Any]:
    del extra
    if not artifact:
        return _empty_data_store_drilldown(name, warnings=warnings)
    preview_path = _metadata_preview_path(artifact)
    if not preview_path:
        return _data_store_drilldown_from_metadata(
            name,
            {},
            fields=fields,
            metadata_refs=[artifact],
            warnings=warnings,
        )
    data, error = _read_json(_artifact_base(config_path) / preview_path)
    read_warnings = [*warnings]
    if error:
        read_warnings.append(error)
        data = {}
    else:
        read_warnings.extend(_string_list(data.get("warnings")))
        read_warnings.extend(_string_list(data.get("errors")))
    return _data_store_drilldown_from_metadata(
        name,
        data,
        fields=fields,
        metadata_refs=[preview_path],
        warnings=read_warnings,
    )


def _empty_data_store_drilldown(
    name: str,
    *,
    metadata_refs: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "category": _data_store_category(name),
        "summary": {},
        "dimensions": {},
        "ranges": {},
        "groups": [],
        "metadata_refs": metadata_refs or [],
        "warnings": warnings or [],
        "omitted": {
            "full_history_records_embedded": False,
            "sqlite_table_contents_embedded": False,
            "group_records_omitted": 0,
        },
    }


def _data_store_drilldown_from_metadata(
    name: str,
    data: dict[str, Any],
    *,
    fields: dict[str, Any],
    metadata_refs: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    groups = _data_store_groups(name, data)
    full_group_count = len(groups)
    return {
        "category": _data_store_category(name),
        "summary": _data_store_summary(fields, data),
        "dimensions": _data_store_dimensions(name, data),
        "ranges": _data_store_ranges(data),
        "groups": groups[:MAX_STORE_DRILLDOWN_ITEMS],
        "metadata_refs": metadata_refs,
        "warnings": warnings,
        "omitted": {
            "full_history_records_embedded": False,
            "sqlite_table_contents_embedded": False,
            "group_records_omitted": max(0, full_group_count - MAX_STORE_DRILLDOWN_ITEMS),
        },
    }


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


def _data_store_summary(fields: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    totals = _dict(data.get("totals"))
    summary = {
        key: value
        for key, value in fields.items()
        if isinstance(value, (str, int, float, bool)) or value is None
    }
    for key in (
        "records",
        "incoming_records",
        "inserted_records",
        "updated_records",
        "duplicate_records",
        "conflicting_duplicates",
        "same_event_groups",
        "same_event_grouped_records",
        "same_event_candidate_pairs",
        "warning_count",
        "error_count",
    ):
        if key in totals and key not in summary:
            summary[key] = totals[key]
    if isinstance(data.get("updated_at"), str):
        summary.setdefault("updated_at", data["updated_at"])
    return _bounded_mapping(summary)


def _data_store_dimensions(name: str, data: dict[str, Any]) -> dict[str, Any]:
    records = _data_store_dimension_records(name, data)
    return _bounded_mapping(
        {
            "sources": _joined_unique(records, ("source", "source_name")),
            "symbols": _joined_unique(records, ("symbol",)),
            "timeframes": _joined_unique(records, ("timeframe",)),
            "metrics": _joined_unique(records, ("metric", "data_class")),
            "regions": _joined_unique(records, ("region",)),
            "assets": _joined_unique(records, ("asset",)),
            "chains": _joined_unique(records, ("chain", "network")),
            "statuses": _joined_unique(records, ("status",)),
            "stores": _joined_unique(records, ("name",)),
            "outcome_states": _joined_unique(records, ("value", "outcome_state")),
        }
    )


def _data_store_dimension_records(name: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    if name == "research_data_catalog":
        return [record for record in _list(data.get("stores")) if isinstance(record, dict)]
    if name == "ohlcv_history":
        return [record for record in _list(data.get("items")) if isinstance(record, dict)]
    if name == "text_event_history":
        return [record for record in _list(data.get("sources")) if isinstance(record, dict)]
    if name == "outcome_history":
        return [record for record in _list(data.get("outcome_states")) if isinstance(record, dict)]
    records = [record for record in _list(data.get("groups")) if isinstance(record, dict)]
    if records:
        return records
    return [record for record in _list(data.get("availability")) if isinstance(record, dict)]


def _data_store_groups(name: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    records = _data_store_dimension_records(name, data)
    return [_bounded_store_group(record) for record in records]


def _bounded_store_group(record: dict[str, Any]) -> dict[str, Any]:
    bounded: dict[str, Any] = {}
    preferred = (
        "name",
        "domain",
        "kind",
        "source",
        "source_name",
        "symbol",
        "timeframe",
        "metric",
        "data_class",
        "region",
        "asset",
        "chain",
        "network",
        "status",
        "format",
        "storage_path",
        "schema_path",
        "state_path",
        "schema_version",
        "schema_metadata_kind",
        "partition_fields",
        "unique_key_fields",
        "time_field",
        "latest_update_at",
        "latest_completed_revision",
        "migration_status",
        "value",
        "outcome_state",
        "row_count",
        "record_count",
        "records",
        "start",
        "end",
        "first_open_time",
        "last_open_time",
        "min_timestamp",
        "max_timestamp",
    )
    for key in preferred:
        value = record.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            bounded[key] = value
        elif isinstance(value, list):
            bounded[key] = _bounded_list_text(value)
    return _bounded_mapping(bounded)


def _data_store_ranges(data: dict[str, Any]) -> dict[str, Any]:
    ranges: dict[str, Any] = {}
    for key in (
        "updated_at",
        "first_open_time",
        "last_open_time",
        "min_timestamp",
        "max_timestamp",
        "start",
        "end",
        "range_start",
        "range_end",
    ):
        value = data.get(key)
        if isinstance(value, (str, int, float, bool)):
            ranges[key] = value
    return _bounded_mapping(ranges)


def _joined_unique(records: list[dict[str, Any]], keys: tuple[str, ...], *, limit: int = 8) -> str | None:
    values: list[str] = []
    for record in records:
        for key in keys:
            value = record.get(key)
            if isinstance(value, str) and value and value not in values:
                values.append(value)
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                text_value = str(value)
                if text_value not in values:
                    values.append(text_value)
    if not values:
        return None
    suffix = "" if len(values) <= limit else f", +{len(values) - limit} more"
    return ", ".join(sorted(values)[:limit]) + suffix


def _metadata_preview_path(artifact: Any) -> str | None:
    if not isinstance(artifact, str) or not artifact:
        return None
    if not (artifact.startswith("data/") or artifact.startswith("runs/")):
        return None
    suffix = Path(artifact).suffix.lower()
    if suffix not in SAFE_METADATA_PREVIEW_SUFFIXES:
        return None
    return artifact


def _data_store_omissions() -> dict[str, bool]:
    return {
        "full_research_catalog_embedded": False,
        "full_raw_histories_embedded": False,
        "full_reusable_histories_embedded": False,
        "sqlite_table_contents_embedded": False,
        "parquet_table_contents_embedded": False,
        "raw_local_user_state_embedded": False,
    }


def _dashboard_store_overall_status(statuses: list[str]) -> str:
    normalized = [status.lower() for status in statuses]
    if any(status == "failed" for status in normalized):
        return "failed"
    if any(status == "degraded" for status in normalized):
        return "degraded"
    if any(status == "warning" for status in normalized):
        return "warning"
    if any(status in {"ok", "available", "succeeded", "success"} for status in normalized):
        if any(status in {"skipped", "missing", "unknown"} for status in normalized):
            return "partial"
        return "available"
    return "partial"


def _read_json(path: Path) -> tuple[dict[str, Any], str | None]:
    return read_json_object(path, external_ref_name=REJECTED_EXTERNAL_REF_NAME)


def _bounded_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    bounded = {
        str(key): item
        for key, item in sorted(value.items())
        if isinstance(item, (str, int, float, bool)) or item is None
    }
    return bounded


def _bounded_list_text(value: list[Any], *, limit: int = 8) -> str | None:
    strings = [str(item) for item in value if isinstance(item, (str, int, float)) and not isinstance(item, bool)]
    if not strings:
        return None
    shown = strings[:limit]
    suffix = "" if len(strings) <= limit else f", +{len(strings) - limit} more"
    return ", ".join(shown) + suffix
