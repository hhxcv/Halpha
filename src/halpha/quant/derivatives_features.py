from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from halpha.data.event_like_query import EventLikeQueryError, query_derivatives_market_records


DERIVATIVES_FEATURE_SCHEMA_VERSION = 1
DERIVATIVES_FEATURE_SOURCE = "strategy_derivatives_features"
DEFAULT_FUNDING_PERIOD = "8h"
FUNDING_RATE_CLASS = "funding_rate"
FUNDING_RATE_METRIC = "funding_rate"
FUNDING_RATE_FILTER_ID = "derivatives_funding_rate_abs_max_v1"
VISIBLE_FEATURE_INPUT_STATUSES = {"available", "partial", "degraded"}


def build_derivatives_feature_input(
    config_path: Path,
    *,
    market_identity: dict[str, Any],
    data_class: str,
    metric: str,
    start: str | datetime,
    end: str | datetime,
    as_of: str | datetime | None = None,
    period: str = DEFAULT_FUNDING_PERIOD,
    max_staleness_seconds: int | None = None,
    limit: int = 1000,
) -> dict[str, Any]:
    source = str(market_identity.get("source") or "")
    symbol = str(market_identity.get("symbol") or "")
    market_type = str(market_identity.get("market_type") or "")
    requested_start = _format_utc(start, "start")
    requested_end = _format_utc(end, "end")
    as_of_boundary = _format_optional_utc(as_of) or requested_end
    if not source or not symbol:
        return _base_feature_input(
            data_class=data_class,
            metric=metric,
            source=source or None,
            symbol=symbol or None,
            market_type=market_type or None,
            period=period,
            requested_start=requested_start,
            requested_end=requested_end,
            as_of_boundary=as_of_boundary,
            max_staleness_seconds=max_staleness_seconds,
            status="skipped",
            records=[],
            matched_record_count=0,
            skipped_record_count=0,
            warnings=[
                _warning(
                    "missing_derivatives_feature_identity",
                    "Derivatives feature loading requires source and symbol market identity.",
                )
            ],
            errors=[],
            source_artifacts=[],
        )

    identity = {
        "data_class": data_class,
        "symbol": symbol,
        "period": period,
    }
    if market_type:
        identity["market_type"] = market_type

    try:
        query = query_derivatives_market_records(
            config_path,
            source=source,
            identity=identity,
            start=requested_start,
            end=requested_end,
            as_of=as_of_boundary,
            limit=limit,
            sort_order="asc",
        )
    except EventLikeQueryError as exc:
        return _base_feature_input(
            data_class=data_class,
            metric=metric,
            source=source,
            symbol=symbol,
            market_type=market_type or None,
            period=period,
            requested_start=requested_start,
            requested_end=requested_end,
            as_of_boundary=as_of_boundary,
            max_staleness_seconds=max_staleness_seconds,
            status="failed",
            records=[],
            matched_record_count=0,
            skipped_record_count=0,
            warnings=[],
            errors=[
                {
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "source": DERIVATIVES_FEATURE_SOURCE,
                }
            ],
            source_artifacts=[],
        )

    records, record_warnings, skipped_count = _feature_records(
        query.get("records") if isinstance(query.get("records"), list) else [],
        data_class=data_class,
        metric=metric,
        as_of_boundary=as_of_boundary,
    )
    warnings = [
        *_warning_list(query.get("warnings")),
        *record_warnings,
        *_feature_status_warnings(
            records=records,
            skipped_record_count=skipped_count,
            requested_end=requested_end,
            max_staleness_seconds=max_staleness_seconds,
        ),
    ]
    status = _feature_status(
        records=records,
        skipped_record_count=skipped_count,
        warnings=warnings,
        requested_end=requested_end,
        max_staleness_seconds=max_staleness_seconds,
    )
    return _base_feature_input(
        data_class=data_class,
        metric=metric,
        source=source,
        symbol=symbol,
        market_type=market_type or None,
        period=period,
        requested_start=requested_start,
        requested_end=requested_end,
        as_of_boundary=as_of_boundary,
        max_staleness_seconds=max_staleness_seconds,
        status=status,
        records=records,
        matched_record_count=int(query.get("matched_record_count") or 0),
        skipped_record_count=skipped_count,
        warnings=warnings,
        errors=[],
        source_artifacts=_source_artifacts(query.get("source_artifacts"), records),
    )


def build_funding_rate_feature_input(
    config_path: Path,
    *,
    market_identity: dict[str, Any],
    start: str | datetime,
    end: str | datetime,
    as_of: str | datetime | None = None,
    period: str = DEFAULT_FUNDING_PERIOD,
    max_staleness_seconds: int | None = None,
    limit: int = 1000,
) -> dict[str, Any]:
    return build_derivatives_feature_input(
        config_path,
        market_identity=market_identity,
        data_class=FUNDING_RATE_CLASS,
        metric=FUNDING_RATE_METRIC,
        start=start,
        end=end,
        as_of=as_of,
        period=period,
        max_staleness_seconds=max_staleness_seconds,
        limit=limit,
    )


def funding_rate_filter_contexts(
    signal_times: list[str],
    feature_input: dict[str, Any] | None,
    *,
    max_abs_funding_rate: float,
) -> list[dict[str, Any]]:
    threshold = _positive_number(max_abs_funding_rate, "max_abs_funding_rate")
    if not isinstance(feature_input, dict):
        return [
            _filter_context(
                signal_time=signal_time,
                status="unavailable",
                suppressed=True,
                suppression_reason="missing_derivatives_feature_input",
                max_abs_funding_rate=threshold,
            )
            for signal_time in signal_times
        ]

    input_status = str(feature_input.get("status") or "unknown")
    records = _visible_feature_records(feature_input.get("records"))
    if input_status not in VISIBLE_FEATURE_INPUT_STATUSES:
        reason = "stale_derivatives_feature" if input_status == "stale" else "missing_derivatives_feature"
        return [
            _filter_context(
                signal_time=signal_time,
                status=input_status,
                suppressed=True,
                suppression_reason=reason,
                max_abs_funding_rate=threshold,
                feature_input_status=input_status,
            )
            for signal_time in signal_times
        ]

    contexts = []
    for signal_time in signal_times:
        signal_dt = _parse_optional_utc(signal_time, "signal_time")
        if signal_dt is None:
            contexts.append(
                _filter_context(
                    signal_time=signal_time,
                    status="failed",
                    suppressed=True,
                    suppression_reason="invalid_signal_time",
                    max_abs_funding_rate=threshold,
                    feature_input_status=input_status,
                )
            )
            continue
        matched = _latest_visible_record(records, signal_dt=signal_dt)
        if matched is None:
            contexts.append(
                _filter_context(
                    signal_time=signal_time,
                    status="unavailable",
                    suppressed=True,
                    suppression_reason="missing_derivatives_feature",
                    max_abs_funding_rate=threshold,
                    feature_input_status=input_status,
                )
            )
            continue
        value = float(matched["value"])
        suppressed = abs(value) > threshold
        contexts.append(
            _filter_context(
                signal_time=signal_time,
                status="suppressed" if suppressed else "passed",
                suppressed=suppressed,
                suppression_reason="funding_rate_abs_above_max" if suppressed else None,
                max_abs_funding_rate=threshold,
                feature_input_status=input_status,
                feature_record=matched,
            )
        )
    return contexts


def _base_feature_input(
    *,
    data_class: str,
    metric: str,
    source: str | None,
    symbol: str | None,
    market_type: str | None,
    period: str,
    requested_start: str,
    requested_end: str,
    as_of_boundary: str,
    max_staleness_seconds: int | None,
    status: str,
    records: list[dict[str, Any]],
    matched_record_count: int,
    skipped_record_count: int,
    warnings: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    source_artifacts: list[str],
) -> dict[str, Any]:
    latest = records[-1] if records else None
    return {
        "schema_version": DERIVATIVES_FEATURE_SCHEMA_VERSION,
        "artifact_type": "strategy_derivatives_feature_input",
        "status": status,
        "feature_id": _feature_id(
            data_class=data_class,
            metric=metric,
            source=source,
            symbol=symbol,
            period=period,
            as_of_boundary=as_of_boundary,
        ),
        "data_type": "derivatives_market",
        "data_class": data_class,
        "metric": metric,
        "source": source,
        "symbol": symbol,
        "market_type": market_type,
        "period": period,
        "requested_start": requested_start,
        "requested_end": requested_end,
        "as_of_boundary": as_of_boundary,
        "max_staleness_seconds": max_staleness_seconds,
        "record_count": len(records),
        "matched_record_count": matched_record_count,
        "skipped_record_count": skipped_record_count,
        "latest_record": latest,
        "records": records,
        "warnings": warnings,
        "errors": errors,
        "source_artifacts": source_artifacts,
    }


def _feature_records(
    records: list[Any],
    *,
    data_class: str,
    metric: str,
    as_of_boundary: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    as_of_dt = _parse_utc(as_of_boundary, "as_of_boundary")
    feature_records = []
    warnings = []
    skipped = 0
    for record in records:
        if not isinstance(record, dict):
            skipped += 1
            continue
        feature_time = _parse_optional_utc(record.get("as_of"), "as_of")
        if feature_time is None:
            skipped += 1
            warnings.append(
                _warning(
                    "invalid_derivatives_feature_time",
                    "Derivatives feature loading skipped a record with invalid as_of.",
                )
            )
            continue
        first_seen = _parse_optional_utc(record.get("first_seen_at"), "first_seen_at")
        if first_seen is not None and first_seen > as_of_dt:
            skipped += 1
            warnings.append(
                _warning(
                    "derivatives_feature_not_observable_as_of",
                    "Derivatives feature loading skipped a record first seen after the as_of boundary.",
                )
            )
            continue
        metrics = record.get("metrics") if isinstance(record.get("metrics"), dict) else {}
        value = _finite_number_or_none(metrics.get(metric))
        if value is None:
            skipped += 1
            warnings.append(
                _warning(
                    "invalid_derivatives_feature_metric",
                    f"Derivatives feature loading skipped a {data_class} record with invalid {metric}.",
                )
            )
            continue
        record_warnings = _string_list(record.get("warnings"))
        record_errors = _string_list(record.get("errors"))
        quality_status = "degraded" if record_warnings or record_errors or record.get("status") == "warning" else "available"
        units = record.get("units") if isinstance(record.get("units"), dict) else {}
        feature_records.append(
            {
                "feature_time": _iso(feature_time),
                "as_of": _iso(feature_time),
                "first_seen_at": _format_optional_utc(record.get("first_seen_at")),
                "last_seen_at": _format_optional_utc(record.get("last_seen_at")),
                "source": str(record.get("source") or ""),
                "market_type": str(record.get("market_type") or ""),
                "symbol": str(record.get("symbol") or ""),
                "period": str(record.get("period") or ""),
                "data_class": data_class,
                "metric": metric,
                "value": value,
                "unit": str(units.get(metric) or ""),
                "quality": {
                    "status": quality_status,
                    "source_status": str(record.get("status") or ""),
                    "warnings": record_warnings,
                    "errors": record_errors,
                },
                "source_artifacts": _string_list(record.get("source_artifacts")),
            }
        )
    return sorted(feature_records, key=lambda item: item["feature_time"]), warnings, skipped


def _feature_status(
    *,
    records: list[dict[str, Any]],
    skipped_record_count: int,
    warnings: list[dict[str, Any]],
    requested_end: str,
    max_staleness_seconds: int | None,
) -> str:
    if not records:
        return "unavailable"
    if _is_stale(records[-1], requested_end=requested_end, max_staleness_seconds=max_staleness_seconds):
        return "stale"
    if skipped_record_count or any(_warning_is_partial(item) for item in warnings):
        return "partial"
    if any(record.get("quality", {}).get("status") == "degraded" for record in records):
        return "degraded"
    return "available"


def _feature_status_warnings(
    *,
    records: list[dict[str, Any]],
    skipped_record_count: int,
    requested_end: str,
    max_staleness_seconds: int | None,
) -> list[dict[str, Any]]:
    warnings = []
    if not records:
        warnings.append(
            _warning(
                "derivatives_feature_unavailable",
                "No matching derivatives feature records are available for the requested window.",
            )
        )
    elif _is_stale(records[-1], requested_end=requested_end, max_staleness_seconds=max_staleness_seconds):
        warnings.append(
            _warning(
                "derivatives_feature_stale",
                "The latest derivatives feature record is older than the configured staleness limit.",
            )
        )
    if skipped_record_count:
        warnings.append(
            _warning(
                "derivatives_feature_partial",
                "Some derivatives records were skipped while building the feature input.",
            )
        )
    return warnings


def _is_stale(
    latest_record: dict[str, Any],
    *,
    requested_end: str,
    max_staleness_seconds: int | None,
) -> bool:
    if max_staleness_seconds is None:
        return False
    latest_dt = _parse_optional_utc(latest_record.get("feature_time"), "feature_time")
    end_dt = _parse_utc(requested_end, "requested_end")
    if latest_dt is None:
        return True
    return (end_dt - latest_dt).total_seconds() > max_staleness_seconds


def _filter_context(
    *,
    signal_time: str,
    status: str,
    suppressed: bool,
    suppression_reason: str | None,
    max_abs_funding_rate: float,
    feature_input_status: str | None = None,
    feature_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = feature_record or {}
    return {
        "filter_id": FUNDING_RATE_FILTER_ID,
        "status": status,
        "suppressed": suppressed,
        "suppression_reason": suppression_reason,
        "signal_time": signal_time,
        "feature_input_status": feature_input_status,
        "feature_time": record.get("feature_time"),
        "feature_value": record.get("value"),
        "feature_unit": record.get("unit"),
        "max_abs_funding_rate": max_abs_funding_rate,
        "lookahead_policy": "feature_time_and_first_seen_at_not_after_signal_time",
    }


def _visible_feature_records(raw_records: Any) -> list[dict[str, Any]]:
    records = []
    if not isinstance(raw_records, list):
        return records
    for record in raw_records:
        if not isinstance(record, dict):
            continue
        feature_time = _parse_optional_utc(record.get("feature_time"), "feature_time")
        value = _finite_number_or_none(record.get("value"))
        if feature_time is None or value is None:
            continue
        records.append(
            {
                **record,
                "feature_time_dt": feature_time,
                "first_seen_dt": _parse_optional_utc(record.get("first_seen_at"), "first_seen_at"),
                "value": value,
            }
        )
    return sorted(records, key=lambda item: item["feature_time"])


def _latest_visible_record(records: list[dict[str, Any]], *, signal_dt: datetime) -> dict[str, Any] | None:
    matched = None
    for record in records:
        feature_time = record["feature_time_dt"]
        first_seen = record.get("first_seen_dt")
        if feature_time > signal_dt:
            continue
        if first_seen is not None and first_seen > signal_dt:
            continue
        matched = record
    return matched


def _feature_id(
    *,
    data_class: str,
    metric: str,
    source: str | None,
    symbol: str | None,
    period: str,
    as_of_boundary: str,
) -> str:
    return ":".join(
        [
            "derivatives_feature",
            data_class,
            metric,
            source or "missing_source",
            symbol or "missing_symbol",
            period,
            as_of_boundary,
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
                    "code": str(item.get("code") or "derivatives_feature_upstream_warning"),
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
        "invalid_derivatives_feature_time",
        "invalid_derivatives_feature_metric",
        "derivatives_feature_not_observable_as_of",
        "derivatives_feature_partial",
    }


def _warning(code: str, message: str) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "source": DERIVATIVES_FEATURE_SOURCE,
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


def _finite_number_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(float(value)):
        return None
    return float(value)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({str(item) for item in value if isinstance(item, str) and item.strip()})
