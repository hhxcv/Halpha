from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from halpha.data.event_like_query import EventLikeQueryError, query_event_like_records


EVENT_FEATURE_SCHEMA_VERSION = 1
EVENT_FEATURE_SOURCE = "strategy_event_features"
MARKET_ANOMALY_DATA_TYPE = "market_anomaly"
MARKET_ANOMALY_FILTER_ID = "event_market_anomaly_count_filter_v1"
VISIBLE_EVENT_INPUT_STATUSES = {"available", "partial", "degraded", "empty"}
EVENT_TIME_FIELDS = {
    "text_event": ("published_at", "collected_at", "first_seen_at"),
    "macro_calendar": ("scheduled_at",),
    "market_anomaly": ("observed_at",),
    "derivatives_market": ("as_of",),
    "onchain_flow": ("as_of",),
}


def build_event_feature_input(
    config_path: Path,
    *,
    data_type: str,
    start: str | datetime,
    end: str | datetime,
    source: str | None = None,
    identity: dict[str, Any] | None = None,
    as_of: str | datetime | None = None,
    categories: list[str] | tuple[str, ...] | None = None,
    keywords: list[str] | tuple[str, ...] | None = None,
    limit: int = 1000,
) -> dict[str, Any]:
    requested_start = _format_utc(start, "start")
    requested_end = _format_utc(end, "end")
    as_of_boundary = _format_optional_utc(as_of) or requested_end
    normalized_categories = _normalized_filter_values(categories)
    normalized_keywords = _normalized_filter_values(keywords)
    try:
        query = query_event_like_records(
            config_path,
            data_type=data_type,
            source=source,
            identity=identity,
            start=requested_start,
            end=requested_end,
            as_of=as_of_boundary,
            limit=limit,
            sort_order="asc",
        )
    except EventLikeQueryError as exc:
        return _base_event_input(
            data_type=data_type,
            requested_start=requested_start,
            requested_end=requested_end,
            as_of_boundary=as_of_boundary,
            source=source,
            identity=identity,
            category_filters=normalized_categories,
            keyword_filters=normalized_keywords,
            status="failed",
            records=[],
            matched_record_count=0,
            filtered_out_record_count=0,
            warnings=[],
            errors=[
                {
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "source": EVENT_FEATURE_SOURCE,
                }
            ],
            source_artifacts=[],
        )

    normalized_records = [
        _event_feature_record(data_type, record)
        for record in query.get("records", [])
        if isinstance(record, dict)
    ]
    filtered_records, filtered_count = _apply_feature_filters(
        normalized_records,
        category_filters=normalized_categories,
        keyword_filters=normalized_keywords,
    )
    query_warnings = _warning_list(query.get("warnings"))
    warnings = [
        *query_warnings,
        *_filter_warnings(
            filtered_records=filtered_records,
            filtered_out_record_count=filtered_count,
            category_filters=normalized_categories,
            keyword_filters=normalized_keywords,
            has_upstream_warnings=bool(query_warnings),
        ),
    ]
    status = _feature_status(records=filtered_records, warnings=warnings)
    return _base_event_input(
        data_type=str(query.get("data_type") or data_type),
        requested_start=requested_start,
        requested_end=requested_end,
        as_of_boundary=as_of_boundary,
        source=source,
        identity=identity,
        category_filters=normalized_categories,
        keyword_filters=normalized_keywords,
        status=status,
        records=filtered_records,
        matched_record_count=int(query.get("matched_record_count") or 0),
        filtered_out_record_count=filtered_count,
        warnings=warnings,
        errors=[],
        source_artifacts=_source_artifacts(query.get("source_artifacts"), filtered_records),
    )


def build_market_anomaly_feature_input(
    config_path: Path,
    *,
    start: str | datetime,
    end: str | datetime,
    source: str | None = None,
    identity: dict[str, Any] | None = None,
    as_of: str | datetime | None = None,
    categories: list[str] | tuple[str, ...] | None = None,
    keywords: list[str] | tuple[str, ...] | None = None,
    limit: int = 1000,
) -> dict[str, Any]:
    return build_event_feature_input(
        config_path,
        data_type=MARKET_ANOMALY_DATA_TYPE,
        source=source,
        identity=identity,
        start=start,
        end=end,
        as_of=as_of,
        categories=categories,
        keywords=keywords,
        limit=limit,
    )


def event_window_contexts(
    signal_times: list[str],
    feature_input: dict[str, Any] | None,
    *,
    window_seconds: int | float,
    direction: str = "lookback",
    limit_per_window: int = 5,
) -> list[dict[str, Any]]:
    seconds = _positive_number(window_seconds, "window_seconds")
    if direction not in {"lookback", "lookahead"}:
        raise ValueError("direction must be lookback or lookahead.")
    if not isinstance(limit_per_window, int) or isinstance(limit_per_window, bool) or limit_per_window <= 0:
        raise ValueError("limit_per_window must be a positive integer.")
    if not isinstance(feature_input, dict):
        return [
            _window_context(
                signal_time=signal_time,
                status="unavailable",
                direction=direction,
                window_seconds=seconds,
                records=[],
                limit_per_window=limit_per_window,
                reason="missing_event_feature_input",
            )
            for signal_time in signal_times
        ]

    input_status = str(feature_input.get("status") or "unknown")
    records = _visible_event_records(feature_input.get("records"))
    if input_status not in VISIBLE_EVENT_INPUT_STATUSES:
        return [
            _window_context(
                signal_time=signal_time,
                status=input_status,
                direction=direction,
                window_seconds=seconds,
                records=[],
                limit_per_window=limit_per_window,
                reason="missing_event_feature",
                feature_input_status=input_status,
            )
            for signal_time in signal_times
        ]

    contexts = []
    for signal_time in signal_times:
        signal_dt = _parse_optional_utc(signal_time, "signal_time")
        if signal_dt is None:
            contexts.append(
                _window_context(
                    signal_time=signal_time,
                    status="failed",
                    direction=direction,
                    window_seconds=seconds,
                    records=[],
                    limit_per_window=limit_per_window,
                    reason="invalid_signal_time",
                    feature_input_status=input_status,
                )
            )
            continue
        matched = _matched_window_records(records, signal_dt=signal_dt, window_seconds=seconds, direction=direction)
        contexts.append(
            _window_context(
                signal_time=signal_time,
                status="available" if matched else "empty",
                direction=direction,
                window_seconds=seconds,
                records=matched,
                limit_per_window=limit_per_window,
                reason=None,
                feature_input_status=input_status,
            )
        )
    return contexts


def event_count_filter_contexts(
    signal_times: list[str],
    feature_input: dict[str, Any] | None,
    *,
    window_seconds: int | float,
    min_event_count: int = 1,
    direction: str = "lookback",
    filter_id: str = MARKET_ANOMALY_FILTER_ID,
) -> list[dict[str, Any]]:
    if not isinstance(min_event_count, int) or isinstance(min_event_count, bool) or min_event_count <= 0:
        raise ValueError("min_event_count must be a positive integer.")
    contexts = event_window_contexts(
        signal_times,
        feature_input,
        window_seconds=window_seconds,
        direction=direction,
    )
    filtered = []
    for context in contexts:
        event_count = int(context.get("event_count") or 0)
        unavailable = context.get("status") not in {"available", "empty"}
        suppressed = unavailable or event_count >= min_event_count
        reason = None
        if unavailable:
            reason = "missing_event_feature"
        elif suppressed:
            reason = "event_count_at_or_above_min"
        filtered.append(
            {
                **context,
                "filter_id": filter_id,
                "suppressed": suppressed,
                "suppression_reason": reason,
                "min_event_count": min_event_count,
                "lookahead_policy": "event_time_and_first_seen_at_not_after_signal_time_for_lookback",
            }
        )
    return filtered


def _base_event_input(
    *,
    data_type: str,
    requested_start: str,
    requested_end: str,
    as_of_boundary: str,
    source: str | None,
    identity: dict[str, Any] | None,
    category_filters: list[str],
    keyword_filters: list[str],
    status: str,
    records: list[dict[str, Any]],
    matched_record_count: int,
    filtered_out_record_count: int,
    warnings: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    source_artifacts: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": EVENT_FEATURE_SCHEMA_VERSION,
        "artifact_type": "strategy_event_feature_input",
        "feature_source": EVENT_FEATURE_SOURCE,
        "status": status,
        "feature_id": _feature_id(
            data_type=data_type,
            source=source,
            identity=identity,
            start=requested_start,
            end=requested_end,
            as_of_boundary=as_of_boundary,
            categories=category_filters,
            keywords=keyword_filters,
        ),
        "data_type": data_type,
        "source": source,
        "identity": _normalized_identity(identity),
        "requested_start": requested_start,
        "requested_end": requested_end,
        "as_of_boundary": as_of_boundary,
        "category_filters": category_filters,
        "keyword_filters": keyword_filters,
        "record_count": len(records),
        "matched_record_count": matched_record_count,
        "filtered_out_record_count": filtered_out_record_count,
        "records": records,
        "warnings": warnings,
        "errors": errors,
        "source_artifacts": source_artifacts,
    }


def _event_feature_record(data_type: str, record: dict[str, Any]) -> dict[str, Any]:
    event_time = _event_time(data_type, record)
    categories = _record_categories(data_type, record)
    source_artifacts = _string_list(record.get("source_artifacts"))
    warnings = _string_list(record.get("warnings"))
    errors = _string_list(record.get("errors"))
    quality_status = "degraded" if warnings or errors or record.get("status") == "warning" else "available"
    return {
        "schema_version": EVENT_FEATURE_SCHEMA_VERSION,
        "record_type": "strategy_event_feature_record",
        "event_id": _event_id(record),
        "data_type": data_type,
        "event_time": event_time,
        "published_at": _first_timestamp(record, ("published_at", "source_published_at")),
        "collected_at": _first_timestamp(record, ("collected_at",)),
        "first_seen_at": _first_timestamp(record, ("first_seen_at",)),
        "source": str(record.get("source") or ""),
        "category": categories[0] if categories else "",
        "categories": categories,
        "class": str(record.get("data_class") or record.get("event_type") or record.get("metric") or ""),
        "severity": str(record.get("severity") or record.get("importance") or ""),
        "symbol": str(record.get("symbol") or ""),
        "region": str(record.get("region") or ""),
        "title": str(record.get("title") or record.get("event_name") or ""),
        "summary": str(record.get("summary") or ""),
        "keywords_text": _keywords_text(record),
        "quality": {
            "status": quality_status,
            "source_status": str(record.get("status") or ""),
            "warnings": warnings,
            "errors": errors,
        },
        "source_artifacts": source_artifacts,
        "raw_ref": {
            "history_key": record.get("history_key"),
            "stable_event_key": record.get("stable_event_key"),
            "item_id": record.get("item_id"),
            "anomaly_id": record.get("anomaly_id"),
        },
    }


def _apply_feature_filters(
    records: list[dict[str, Any]],
    *,
    category_filters: list[str],
    keyword_filters: list[str],
) -> tuple[list[dict[str, Any]], int]:
    selected = []
    filtered = 0
    for record in records:
        if category_filters and not _category_matches(record, category_filters):
            filtered += 1
            continue
        if keyword_filters and not _keyword_matches(record, keyword_filters):
            filtered += 1
            continue
        selected.append(record)
    return selected, filtered


def _feature_status(*, records: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> str:
    if not records:
        return "unavailable" if warnings else "empty"
    if any(_warning_is_partial(item) for item in warnings):
        return "partial"
    if any(record.get("quality", {}).get("status") == "degraded" for record in records):
        return "degraded"
    return "available"


def _filter_warnings(
    *,
    filtered_records: list[dict[str, Any]],
    filtered_out_record_count: int,
    category_filters: list[str],
    keyword_filters: list[str],
    has_upstream_warnings: bool,
) -> list[dict[str, Any]]:
    warnings = []
    if not filtered_records and has_upstream_warnings:
        warnings.append(
            _warning(
                "event_feature_unavailable",
                "No matching event feature records are available for the requested window and filters.",
            )
        )
    if filtered_out_record_count and (category_filters or keyword_filters):
        warnings.append(
            _warning(
                "event_feature_filtered_records",
                "Some event records were excluded by category or keyword filters.",
            )
        )
    return warnings


def _window_context(
    *,
    signal_time: str,
    status: str,
    direction: str,
    window_seconds: float,
    records: list[dict[str, Any]],
    limit_per_window: int,
    reason: str | None,
    feature_input_status: str | None = None,
) -> dict[str, Any]:
    signal_dt = _parse_optional_utc(signal_time, "signal_time")
    if signal_dt is None:
        window_start = None
        window_end = None
    elif direction == "lookback":
        window_start = _iso(signal_dt - timedelta(seconds=window_seconds))
        window_end = _iso(signal_dt)
    else:
        window_start = _iso(signal_dt)
        window_end = _iso(signal_dt + timedelta(seconds=window_seconds))
    bounded = records[:limit_per_window]
    return {
        "status": status,
        "reason": reason,
        "signal_time": signal_time,
        "direction": direction,
        "window_start": window_start,
        "window_end": window_end,
        "window_seconds": window_seconds,
        "feature_input_status": feature_input_status,
        "event_count": len(records),
        "record_count": len(bounded),
        "truncated": len(records) > len(bounded),
        "records": [_window_record(record) for record in bounded],
    }


def _matched_window_records(
    records: list[dict[str, Any]],
    *,
    signal_dt: datetime,
    window_seconds: float,
    direction: str,
) -> list[dict[str, Any]]:
    if direction == "lookback":
        window_start = signal_dt - timedelta(seconds=window_seconds)
        return [
            record
            for record in records
            if window_start <= record["event_time_dt"] <= signal_dt
            and _record_visible_at_signal(record, signal_dt=signal_dt)
        ]
    window_end = signal_dt + timedelta(seconds=window_seconds)
    return [
        record
        for record in records
        if signal_dt <= record["event_time_dt"] <= window_end
        and _record_visible_at_signal(record, signal_dt=signal_dt)
    ]


def _visible_event_records(raw_records: Any) -> list[dict[str, Any]]:
    records = []
    if not isinstance(raw_records, list):
        return records
    for record in raw_records:
        if not isinstance(record, dict):
            continue
        event_time = _parse_optional_utc(record.get("event_time"), "event_time")
        if event_time is None:
            continue
        records.append(
            {
                **record,
                "event_time_dt": event_time,
                "published_dt": _parse_optional_utc(record.get("published_at"), "published_at"),
                "collected_dt": _parse_optional_utc(record.get("collected_at"), "collected_at"),
                "first_seen_dt": _parse_optional_utc(record.get("first_seen_at"), "first_seen_at"),
            }
        )
    return sorted(records, key=lambda item: item["event_time"])


def _record_visible_at_signal(record: dict[str, Any], *, signal_dt: datetime) -> bool:
    for field in ("published_dt", "collected_dt", "first_seen_dt"):
        timestamp = record.get(field)
        if timestamp is not None and timestamp > signal_dt:
            return False
    return True


def _window_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": record.get("event_id"),
        "data_type": record.get("data_type"),
        "event_time": record.get("event_time"),
        "first_seen_at": record.get("first_seen_at"),
        "source": record.get("source"),
        "category": record.get("category"),
        "severity": record.get("severity"),
        "symbol": record.get("symbol"),
        "title": record.get("title"),
        "quality": record.get("quality"),
        "source_artifacts": record.get("source_artifacts"),
    }


def _event_time(data_type: str, record: dict[str, Any]) -> str | None:
    for field in EVENT_TIME_FIELDS.get(data_type, ("event_time", "as_of", "published_at", "first_seen_at")):
        value = record.get(field)
        timestamp = _parse_optional_utc(value, field)
        if timestamp is not None:
            return _iso(timestamp)
    return None


def _first_timestamp(record: dict[str, Any], fields: tuple[str, ...]) -> str | None:
    for field in fields:
        timestamp = _parse_optional_utc(record.get(field), field)
        if timestamp is not None:
            return _iso(timestamp)
    return None


def _record_categories(data_type: str, record: dict[str, Any]) -> list[str]:
    values = [
        data_type,
        record.get("data_class"),
        record.get("event_type"),
        record.get("metric"),
        record.get("direction"),
        record.get("severity"),
        record.get("importance"),
        record.get("source_kind"),
    ]
    return sorted({str(value).strip() for value in values if isinstance(value, str) and value.strip()})


def _keywords_text(record: dict[str, Any]) -> str:
    fields = [
        record.get("title"),
        record.get("summary"),
        record.get("event_name"),
        record.get("normalized_text"),
        record.get("source"),
        record.get("symbol"),
        record.get("region"),
    ]
    return " ".join(str(value) for value in fields if isinstance(value, str) and value.strip())


def _category_matches(record: dict[str, Any], filters: list[str]) -> bool:
    categories = {str(value).lower() for value in record.get("categories", []) if isinstance(value, str)}
    return any(item in categories for item in filters)


def _keyword_matches(record: dict[str, Any], filters: list[str]) -> bool:
    text = str(record.get("keywords_text") or "").lower()
    return all(item in text for item in filters)


def _event_id(record: dict[str, Any]) -> str:
    for field in ("anomaly_id", "stable_event_key", "history_key", "item_id"):
        value = record.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "unknown_event"


def _feature_id(
    *,
    data_type: str,
    source: str | None,
    identity: dict[str, Any] | None,
    start: str,
    end: str,
    as_of_boundary: str,
    categories: list[str],
    keywords: list[str],
) -> str:
    identity_text = ",".join(f"{key}={value}" for key, value in _normalized_identity(identity).items()) or "all"
    category_text = ",".join(categories) or "all"
    keyword_text = ",".join(keywords) or "all"
    return ":".join(
        [
            "event_feature",
            data_type,
            source or "all",
            identity_text,
            start,
            end,
            as_of_boundary,
            f"categories={category_text}",
            f"keywords={keyword_text}",
        ]
    )


def _source_artifacts(query_artifacts: Any, records: list[dict[str, Any]]) -> list[str]:
    values = set(_string_list(query_artifacts))
    for record in records:
        values.update(_string_list(record.get("source_artifacts")))
    return sorted(values)


def _warning_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    warnings = []
    for item in value:
        if isinstance(item, dict):
            warnings.append(
                {
                    "code": str(item.get("code") or "event_feature_upstream_warning"),
                    "message": str(item.get("message") or item),
                    "source": str(item.get("source") or "event_like_query"),
                }
            )
    return warnings


def _warning_is_partial(warning_record: dict[str, Any]) -> bool:
    return str(warning_record.get("code") or "") in {
        "query_result_truncated",
        "invalid_event_time_records",
        "incomplete_collection_coverage",
    }


def _warning(code: str, message: str) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "source": EVENT_FEATURE_SOURCE,
    }


def _normalized_filter_values(values: list[str] | tuple[str, ...] | None) -> list[str]:
    if not values:
        return []
    return sorted({str(value).strip().lower() for value in values if str(value).strip()})


def _normalized_identity(identity: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(identity, dict):
        return {}
    return {
        str(key): str(identity[key])
        for key in sorted(identity)
        if identity[key] is not None and str(identity[key]) != ""
    }


def _format_utc(value: str | datetime, field: str) -> str:
    timestamp = _parse_utc(value, field)
    return _iso(timestamp)


def _format_optional_utc(value: Any) -> str | None:
    if value is None:
        return None
    timestamp = _parse_optional_utc(value, "timestamp")
    return _iso(timestamp) if timestamp is not None else None


def _parse_utc(value: str | datetime, field: str) -> datetime:
    timestamp = _parse_optional_utc(value, field)
    if timestamp is None:
        raise EventLikeQueryError(f"{field} must be an ISO-8601 UTC timestamp.", exit_code=2)
    return timestamp


def _parse_optional_utc(value: Any, field: str) -> datetime | None:
    if isinstance(value, datetime):
        timestamp = value
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            timestamp = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _positive_number(value: Any, name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or float(value) <= 0
    ):
        raise ValueError(f"{name} must be a positive number.")
    return float(value)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({str(item) for item in value if isinstance(item, str) and item.strip()})
