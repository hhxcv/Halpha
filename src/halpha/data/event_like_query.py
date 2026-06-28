from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from halpha.data.collection_coverage import (
    COVERAGE_STATE_ARTIFACT,
    read_collection_coverage_state,
    summarize_collection_coverage,
)
from halpha.macro.macro_calendar_history import (
    MACRO_CALENDAR_HISTORY_SCHEMA_ARTIFACT,
    MACRO_CALENDAR_HISTORY_STATE_ARTIFACT,
    read_macro_calendar_history_records,
)
from halpha.market.derivatives_history import (
    DERIVATIVES_HISTORY_SCHEMA_ARTIFACT,
    DERIVATIVES_HISTORY_STATE_ARTIFACT,
    read_derivatives_history_records,
)
from halpha.market.market_anomaly_history import (
    MARKET_ANOMALY_HISTORY_SCHEMA_ARTIFACT,
    MARKET_ANOMALY_HISTORY_STATE_ARTIFACT,
    read_market_anomaly_history_records,
)
from halpha.onchain.onchain_flow_history import (
    ONCHAIN_FLOW_HISTORY_SCHEMA_ARTIFACT,
    ONCHAIN_FLOW_HISTORY_STATE_ARTIFACT,
    read_onchain_flow_history_records,
)
from halpha.text.text_event_history import (
    TEXT_EVENT_HISTORY_STATE_ARTIFACT,
    read_text_event_history_records,
)


EVENT_LIKE_QUERY_SCHEMA_VERSION = 1


class EventLikeQueryError(Exception):
    def __init__(self, message: str, *, exit_code: int = 3) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass(frozen=True)
class _EventLikeAdapter:
    data_type: str
    reader: Callable[[Path], list[dict[str, Any]]]
    primary_time_field: str
    range_time_fields: tuple[str, ...]
    as_of_time_fields: tuple[str, ...]
    source_artifacts: tuple[str, ...]
    requires_as_of_evidence: bool = True


_ADAPTERS: dict[str, _EventLikeAdapter] = {
    "text_event": _EventLikeAdapter(
        data_type="text_event",
        reader=read_text_event_history_records,
        primary_time_field="published_at",
        range_time_fields=("published_at", "collected_at", "first_seen_at"),
        as_of_time_fields=("published_at", "collected_at", "first_seen_at"),
        source_artifacts=(TEXT_EVENT_HISTORY_STATE_ARTIFACT,),
    ),
    "macro_calendar": _EventLikeAdapter(
        data_type="macro_calendar",
        reader=read_macro_calendar_history_records,
        primary_time_field="scheduled_at",
        range_time_fields=("scheduled_at",),
        as_of_time_fields=("source_published_at", "first_seen_at"),
        source_artifacts=(MACRO_CALENDAR_HISTORY_SCHEMA_ARTIFACT, MACRO_CALENDAR_HISTORY_STATE_ARTIFACT),
    ),
    "onchain_flow": _EventLikeAdapter(
        data_type="onchain_flow",
        reader=read_onchain_flow_history_records,
        primary_time_field="as_of",
        range_time_fields=("as_of",),
        as_of_time_fields=("as_of",),
        source_artifacts=(ONCHAIN_FLOW_HISTORY_SCHEMA_ARTIFACT, ONCHAIN_FLOW_HISTORY_STATE_ARTIFACT),
    ),
    "derivatives_market": _EventLikeAdapter(
        data_type="derivatives_market",
        reader=read_derivatives_history_records,
        primary_time_field="as_of",
        range_time_fields=("as_of",),
        as_of_time_fields=("as_of",),
        source_artifacts=(DERIVATIVES_HISTORY_SCHEMA_ARTIFACT, DERIVATIVES_HISTORY_STATE_ARTIFACT),
    ),
    "market_anomaly": _EventLikeAdapter(
        data_type="market_anomaly",
        reader=read_market_anomaly_history_records,
        primary_time_field="observed_at",
        range_time_fields=("observed_at",),
        as_of_time_fields=("published_at", "first_seen_at"),
        source_artifacts=(MARKET_ANOMALY_HISTORY_SCHEMA_ARTIFACT, MARKET_ANOMALY_HISTORY_STATE_ARTIFACT),
    ),
}


def query_event_like_records(
    config_path: Path,
    *,
    data_type: str,
    start: str | datetime,
    end: str | datetime,
    source: str | None = None,
    identity: dict[str, Any] | None = None,
    as_of: str | datetime | None = None,
    limit: int | None = None,
    sort_order: str = "asc",
) -> dict[str, Any]:
    adapter = _adapter(data_type)
    requested_start = _format_utc(start, "start")
    requested_end = _format_utc(end, "end")
    start_dt = _parse_utc(requested_start, "start")
    end_dt = _parse_utc(requested_end, "end")
    if end_dt <= start_dt:
        raise EventLikeQueryError("end must be greater than start for event-like queries.", exit_code=2)
    as_of_text = _format_utc(as_of, "as_of") if as_of is not None else None
    as_of_dt = _parse_utc(as_of_text, "as_of") if as_of_text is not None else None
    normalized_identity = _normalized_identity(identity)
    all_records = adapter.reader(config_path)
    selected, filter_diagnostics = _filter_records(
        all_records,
        adapter=adapter,
        source=source,
        identity=normalized_identity,
        start_dt=start_dt,
        end_dt=end_dt,
        as_of_dt=as_of_dt,
        sort_order=sort_order,
    )
    bounded_records, truncated = _apply_limit(selected, limit)
    coverage = _coverage_diagnostics(
        config_path=config_path,
        data_type=adapter.data_type,
        source=source,
        identity=_coverage_identity(adapter.data_type, source=source, identity=normalized_identity),
        requested_start=requested_start,
        requested_end=requested_end,
    )
    empty = _empty_result_diagnostics(records=selected, coverage=coverage)
    warnings = _query_warnings(
        data_type=adapter.data_type,
        coverage=coverage,
        empty_result=empty,
        filter_diagnostics=filter_diagnostics,
        truncated=truncated,
    )
    return {
        "schema_version": EVENT_LIKE_QUERY_SCHEMA_VERSION,
        "artifact_type": "event_like_query_result",
        "status": "warning" if warnings else "ok",
        "data_type": adapter.data_type,
        "source": source,
        "identity": normalized_identity,
        "requested_start": requested_start,
        "requested_end": requested_end,
        "as_of": as_of_text,
        "sort_order": sort_order,
        "time_fields": {
            "range_field": adapter.primary_time_field,
            "range_fallback_fields": list(adapter.range_time_fields),
            "as_of_boundary_fields": list(adapter.as_of_time_fields),
            "start_inclusive": True,
            "end_inclusive": False,
        },
        "range": _actual_range(bounded_records, adapter),
        "matched_record_count": len(selected),
        "record_count": len(bounded_records),
        "history_row_count": len(all_records),
        "truncated": truncated,
        "limit": limit,
        "records": bounded_records,
        "filter_diagnostics": filter_diagnostics,
        "empty_result_diagnostics": empty,
        "coverage_diagnostics": coverage,
        "warnings": warnings,
        "errors": [],
        "source_artifacts": _source_artifacts(adapter),
    }


def query_text_event_records(
    config_path: Path,
    *,
    start: str | datetime,
    end: str | datetime,
    source: str | None = None,
    identity: dict[str, Any] | None = None,
    as_of: str | datetime | None = None,
    limit: int | None = None,
    sort_order: str = "asc",
) -> dict[str, Any]:
    return query_event_like_records(
        config_path,
        data_type="text_event",
        source=source,
        identity=identity,
        start=start,
        end=end,
        as_of=as_of,
        limit=limit,
        sort_order=sort_order,
    )


def query_macro_calendar_records(
    config_path: Path,
    *,
    start: str | datetime,
    end: str | datetime,
    source: str | None = None,
    identity: dict[str, Any] | None = None,
    as_of: str | datetime | None = None,
    limit: int | None = None,
    sort_order: str = "asc",
) -> dict[str, Any]:
    return query_event_like_records(
        config_path,
        data_type="macro_calendar",
        source=source,
        identity=identity,
        start=start,
        end=end,
        as_of=as_of,
        limit=limit,
        sort_order=sort_order,
    )


def query_onchain_flow_records(
    config_path: Path,
    *,
    start: str | datetime,
    end: str | datetime,
    source: str | None = None,
    identity: dict[str, Any] | None = None,
    as_of: str | datetime | None = None,
    limit: int | None = None,
    sort_order: str = "asc",
) -> dict[str, Any]:
    return query_event_like_records(
        config_path,
        data_type="onchain_flow",
        source=source,
        identity=identity,
        start=start,
        end=end,
        as_of=as_of,
        limit=limit,
        sort_order=sort_order,
    )


def query_derivatives_market_records(
    config_path: Path,
    *,
    start: str | datetime,
    end: str | datetime,
    source: str | None = None,
    identity: dict[str, Any] | None = None,
    as_of: str | datetime | None = None,
    limit: int | None = None,
    sort_order: str = "asc",
) -> dict[str, Any]:
    return query_event_like_records(
        config_path,
        data_type="derivatives_market",
        source=source,
        identity=identity,
        start=start,
        end=end,
        as_of=as_of,
        limit=limit,
        sort_order=sort_order,
    )


def query_market_anomaly_records(
    config_path: Path,
    *,
    start: str | datetime,
    end: str | datetime,
    source: str | None = None,
    identity: dict[str, Any] | None = None,
    as_of: str | datetime | None = None,
    limit: int | None = None,
    sort_order: str = "asc",
) -> dict[str, Any]:
    return query_event_like_records(
        config_path,
        data_type="market_anomaly",
        source=source,
        identity=identity,
        start=start,
        end=end,
        as_of=as_of,
        limit=limit,
        sort_order=sort_order,
    )


def _filter_records(
    records: list[dict[str, Any]],
    *,
    adapter: _EventLikeAdapter,
    source: str | None,
    identity: dict[str, str],
    start_dt: datetime,
    end_dt: datetime,
    as_of_dt: datetime | None,
    sort_order: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if sort_order not in {"asc", "desc"}:
        raise EventLikeQueryError("sort_order must be asc or desc.", exit_code=2)
    selected = []
    invalid_time_records = 0
    as_of_excluded_records = 0
    for record in records:
        if not _source_matches(record, source):
            continue
        if not _identity_matches(record, identity):
            continue
        record_time = _record_time(record, adapter.range_time_fields)
        if record_time is None:
            invalid_time_records += 1
            continue
        if record_time < start_dt or record_time >= end_dt:
            continue
        if as_of_dt is not None and not _visible_as_of(record, adapter, as_of_dt=as_of_dt):
            as_of_excluded_records += 1
            continue
        selected.append(record)
    reverse = sort_order == "desc"
    selected = sorted(selected, key=lambda record: _sort_key(record, adapter), reverse=reverse)
    return selected, {
        "invalid_time_record_count": invalid_time_records,
        "as_of_excluded_record_count": as_of_excluded_records,
    }


def _coverage_diagnostics(
    *,
    config_path: Path,
    data_type: str,
    source: str | None,
    identity: dict[str, str] | None,
    requested_start: str,
    requested_end: str,
) -> dict[str, Any]:
    state = read_collection_coverage_state(config_path)
    summary = summarize_collection_coverage(
        state,
        data_type=data_type,
        source=None if source == "all" else source,
        identity=identity,
        requested_start=requested_start,
        requested_end=requested_end,
    )
    coverage_status = str(state.get("status") or "skipped")
    if summary["record_count"] > 0:
        status = "available"
    elif coverage_status in {"error", "failed"}:
        status = "error"
    elif coverage_status == "skipped":
        status = "not_available"
    else:
        status = "empty"
    return {
        "status": status,
        "state_path": COVERAGE_STATE_ARTIFACT,
        "data_type": data_type,
        "source": source,
        "identity": identity or {},
        "record_count": summary["record_count"],
        "status_counts": summary["status_counts"],
        "range_start": summary["range_start"],
        "range_end": summary["range_end"],
        "partial_ranges": summary["partial_ranges"],
        "failed_ranges": summary["failed_ranges"],
        "not_collected_ranges": summary["not_collected_ranges"],
        "unknown_ranges": summary["unknown_ranges"],
        "warnings": [str(item) for item in state.get("warnings", []) if isinstance(item, str)],
        "errors": [item for item in state.get("errors", []) if isinstance(item, dict)],
    }


def _empty_result_diagnostics(*, records: list[dict[str, Any]], coverage: dict[str, Any]) -> dict[str, Any]:
    if records:
        return {"status": "not_empty", "reason": None}
    status_counts = dict(coverage.get("status_counts") or {})
    incomplete = any(
        coverage.get(field)
        for field in ("partial_ranges", "failed_ranges", "not_collected_ranges", "unknown_ranges")
    )
    if status_counts and set(status_counts) <= {"no_data"} and not incomplete:
        return {"status": "no_data", "reason": "coverage_state_records_no_data"}
    if coverage.get("status") == "not_available":
        return {"status": "unknown_coverage", "reason": "coverage_state_missing"}
    if incomplete:
        return {"status": "incomplete_coverage", "reason": "coverage_state_has_incomplete_ranges"}
    return {"status": "unknown_coverage", "reason": "no_matching_coverage_records"}


def _query_warnings(
    *,
    data_type: str,
    coverage: dict[str, Any],
    empty_result: dict[str, Any],
    filter_diagnostics: dict[str, Any],
    truncated: bool,
) -> list[dict[str, Any]]:
    warnings = []
    if truncated:
        warnings.append(
            {
                "code": "query_result_truncated",
                "message": f"{data_type} query result was truncated by limit.",
                "source": "event_like_query",
            }
        )
    if int(filter_diagnostics.get("invalid_time_record_count") or 0):
        warnings.append(
            {
                "code": "invalid_event_time_records",
                "message": f"{data_type} query skipped records with missing or invalid event time.",
                "source": "event_like_query",
            }
        )
    if _coverage_incomplete(coverage):
        warnings.append(
            {
                "code": "incomplete_collection_coverage",
                "message": f"{data_type} query overlaps incomplete or unknown collection coverage.",
                "source": "event_like_query",
            }
        )
    if empty_result.get("status") == "unknown_coverage":
        warnings.append(
            {
                "code": "unknown_collection_coverage",
                "message": f"{data_type} query returned no records and coverage is unknown.",
                "source": "event_like_query",
            }
        )
    return warnings


def _coverage_incomplete(coverage: dict[str, Any]) -> bool:
    if coverage.get("status") not in {"available", "empty"}:
        return False
    return any(
        coverage.get(field)
        for field in ("partial_ranges", "failed_ranges", "not_collected_ranges", "unknown_ranges")
    )


def _source_matches(record: dict[str, Any], source: str | None) -> bool:
    if source is None or source == "all":
        return True
    return str(record.get("source") or "") == source


def _identity_matches(record: dict[str, Any], identity: dict[str, str]) -> bool:
    for key, expected in identity.items():
        value = record.get(key)
        if isinstance(value, list):
            if expected not in {str(item) for item in value}:
                return False
        elif str(value or "") != expected:
            return False
    return True


def _visible_as_of(record: dict[str, Any], adapter: _EventLikeAdapter, *, as_of_dt: datetime) -> bool:
    saw_evidence = False
    for field in adapter.as_of_time_fields:
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            continue
        timestamp = _parse_optional_utc(value, field)
        if timestamp is None:
            return False
        saw_evidence = True
        if timestamp > as_of_dt:
            return False
    return saw_evidence or not adapter.requires_as_of_evidence


def _record_time(record: dict[str, Any], fields: tuple[str, ...]) -> datetime | None:
    for field in fields:
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            continue
        timestamp = _parse_optional_utc(value, field)
        if timestamp is not None:
            return timestamp
    return None


def _sort_key(record: dict[str, Any], adapter: _EventLikeAdapter) -> tuple[str, ...]:
    record_time = _record_time(record, adapter.range_time_fields)
    timestamp = _iso(record_time) if record_time is not None else ""
    return (
        timestamp,
        str(record.get("source") or ""),
        str(record.get("history_key") or record.get("stable_event_key") or record.get("item_id") or ""),
    )


def _actual_range(records: list[dict[str, Any]], adapter: _EventLikeAdapter) -> dict[str, Any]:
    times = [
        _iso(timestamp)
        for record in records
        if (timestamp := _record_time(record, adapter.range_time_fields)) is not None
    ]
    return {
        "time_field": adapter.primary_time_field,
        "start": min(times) if times else None,
        "end": max(times) if times else None,
    }


def _apply_limit(records: list[dict[str, Any]], limit: int | None) -> tuple[list[dict[str, Any]], bool]:
    if limit is None:
        return records, False
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise EventLikeQueryError("limit must be a positive integer.", exit_code=2)
    if len(records) <= limit:
        return records, False
    return records[:limit], True


def _coverage_identity(data_type: str, *, source: str | None, identity: dict[str, str]) -> dict[str, str] | None:
    if identity:
        return identity
    if data_type == "text_event" and source:
        if source == "all":
            return {"source_group": "all"}
        return {"source_name": source}
    return None


def _normalized_identity(identity: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(identity, dict):
        return {}
    return {
        str(key): str(identity[key])
        for key in sorted(identity)
        if identity[key] is not None and str(identity[key]) != ""
    }


def _source_artifacts(adapter: _EventLikeAdapter) -> list[str]:
    return sorted({*adapter.source_artifacts, COVERAGE_STATE_ARTIFACT})


def _adapter(data_type: str) -> _EventLikeAdapter:
    adapter = _ADAPTERS.get(str(data_type or ""))
    if adapter is None:
        supported = ", ".join(sorted(_ADAPTERS))
        raise EventLikeQueryError(f"unsupported event-like data_type {data_type}. Supported: {supported}.", exit_code=2)
    return adapter


def _format_utc(value: str | datetime | None, field: str) -> str:
    if value is None:
        raise EventLikeQueryError(f"{field} must be an ISO 8601 UTC string.", exit_code=2)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise EventLikeQueryError(f"{field} must include a UTC offset.", exit_code=2)
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str) and value.strip():
        timestamp = _parse_utc(value.strip(), field)
    else:
        raise EventLikeQueryError(f"{field} must be an ISO 8601 UTC string.", exit_code=2)
    return _iso(timestamp)


def _parse_utc(value: str, field: str) -> datetime:
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EventLikeQueryError(f"{field} must be an ISO 8601 UTC string.", exit_code=2) from exc
    if timestamp.tzinfo is None:
        raise EventLikeQueryError(f"{field} must include a UTC offset.", exit_code=2)
    return timestamp.astimezone(timezone.utc).replace(microsecond=0)


def _parse_optional_utc(value: str, field: str) -> datetime | None:
    try:
        return _parse_utc(value, field)
    except EventLikeQueryError:
        return None


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
