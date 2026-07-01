from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from halpha.data.event_like_query import EventLikeQueryError, query_derivatives_market_records


FUNDING_COST_SCHEMA_VERSION = 1
FUNDING_COST_SOURCE = "strategy_funding_costs"
FUNDING_RATE_CLASS = "funding_rate"
DEFAULT_FUNDING_PERIOD = "8h"


def build_funding_cost_input(
    config_path: Path,
    *,
    market_identity: dict[str, Any],
    ohlcv_rows: list[dict[str, Any]],
    as_of: str | datetime | None = None,
    period: str = DEFAULT_FUNDING_PERIOD,
) -> dict[str, Any]:
    source = str(market_identity.get("source") or "")
    symbol = str(market_identity.get("symbol") or "")
    if not source or not symbol:
        return _base_input(
            source=source or None,
            symbol=symbol or None,
            period=period,
            as_of_boundary=_format_optional_utc(as_of),
            status="skipped",
            periods=[],
            warnings=[
                _warning(
                    "missing_funding_identity",
                    "Funding cost lookup requires source and symbol market identity.",
                )
            ],
            source_artifacts=[],
        )
    if len(ohlcv_rows) < 2:
        return _base_input(
            source=source,
            symbol=symbol,
            period=period,
            as_of_boundary=_format_optional_utc(as_of),
            status="skipped",
            periods=[],
            warnings=[
                _warning(
                    "insufficient_ohlcv_rows_for_funding",
                    "Funding cost alignment requires at least two OHLCV rows.",
                )
            ],
            source_artifacts=[],
        )

    query_start = _open_time(ohlcv_rows[0])
    query_end = _iso(_parse_utc(_open_time(ohlcv_rows[-1]), "ohlcv_rows[-1].open_time") + timedelta(seconds=1))
    as_of_boundary = _format_optional_utc(as_of) or _open_time(ohlcv_rows[-1])
    identity = {
        "data_class": FUNDING_RATE_CLASS,
        "symbol": symbol,
        "period": period,
    }

    try:
        query = query_derivatives_market_records(
            config_path,
            source=source,
            identity=identity,
            start=query_start,
            end=query_end,
            as_of=as_of_boundary,
            sort_order="asc",
        )
    except EventLikeQueryError as exc:
        return _base_input(
            source=source,
            symbol=symbol,
            period=period,
            as_of_boundary=as_of_boundary,
            status="failed",
            periods=[],
            warnings=[],
            errors=[
                {
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                    "source": FUNDING_COST_SOURCE,
                }
            ],
            source_artifacts=[],
        )

    return funding_cost_input_from_records(
        ohlcv_rows,
        query.get("records") if isinstance(query.get("records"), list) else [],
        source=source,
        symbol=symbol,
        period=period,
        as_of_boundary=as_of_boundary,
        upstream_warnings=query.get("warnings") if isinstance(query.get("warnings"), list) else [],
        source_artifacts=query.get("source_artifacts") if isinstance(query.get("source_artifacts"), list) else [],
    )


def funding_cost_input_from_records(
    ohlcv_rows: list[dict[str, Any]],
    funding_records: list[dict[str, Any]],
    *,
    source: str,
    symbol: str,
    period: str = DEFAULT_FUNDING_PERIOD,
    as_of_boundary: str | None = None,
    upstream_warnings: list[Any] | None = None,
    source_artifacts: list[Any] | None = None,
) -> dict[str, Any]:
    if len(ohlcv_rows) < 2:
        return _base_input(
            source=source,
            symbol=symbol,
            period=period,
            as_of_boundary=as_of_boundary,
            status="skipped",
            periods=[],
            warnings=[
                _warning(
                    "insufficient_ohlcv_rows_for_funding",
                    "Funding cost alignment requires at least two OHLCV rows.",
                )
            ],
            source_artifacts=_string_list(source_artifacts),
        )

    valid_records, invalid_warnings = _valid_funding_records(funding_records)
    periods = []
    matched_record_count = 0
    missing_period_count = 0
    expected_record_count = 0
    for index in range(1, len(ohlcv_rows)):
        period_start = _open_time(ohlcv_rows[index - 1])
        period_end = _open_time(ohlcv_rows[index])
        start_dt = _parse_utc(period_start, "period_start")
        end_dt = _parse_utc(period_end, "period_end")
        expected_count = _expected_funding_record_count(start_dt, end_dt, period=period)
        matched = [
            record
            for record in valid_records
            if start_dt < record["as_of_dt"] <= end_dt
        ]
        matched_record_count += len(matched)
        expected_record_count += expected_count
        if len(matched) < expected_count:
            missing_period_count += expected_count - len(matched)
        funding_rate = sum(record["funding_rate"] for record in matched)
        periods.append(
            {
                "period_start": period_start,
                "period_end": period_end,
                "expected_record_count": expected_count,
                "funding_rate": round(float(funding_rate), 12),
                "matched_record_count": len(matched),
                "funding_as_of": [record["as_of"] for record in matched],
            }
        )

    status = _funding_status(matched_record_count=matched_record_count, missing_period_count=missing_period_count)
    warnings = [
        *_warning_list(upstream_warnings),
        *invalid_warnings,
        *_coverage_warnings(status=status, missing_period_count=missing_period_count),
    ]
    artifacts = sorted(
        {
            *_string_list(source_artifacts),
            *[
                artifact
                for record in funding_records
                for artifact in _string_list(record.get("source_artifacts"))
            ],
        }
    )
    return _base_input(
        source=source,
        symbol=symbol,
        period=period,
        as_of_boundary=as_of_boundary,
        status=status,
        periods=periods,
        warnings=warnings,
        source_artifacts=artifacts,
    )


def _base_input(
    *,
    source: str | None,
    symbol: str | None,
    period: str,
    as_of_boundary: str | None,
    status: str,
    periods: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    source_artifacts: list[str],
    errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    matched_record_count = sum(int(item.get("matched_record_count") or 0) for item in periods)
    missing_period_count = sum(
        max(0, int(item.get("expected_record_count") or 0) - int(item.get("matched_record_count") or 0))
        for item in periods
    )
    expected_record_count = sum(int(item.get("expected_record_count") or 0) for item in periods)
    return {
        "schema_version": FUNDING_COST_SCHEMA_VERSION,
        "artifact_type": "strategy_funding_cost_input",
        "status": status,
        "source": source,
        "symbol": symbol,
        "data_class": FUNDING_RATE_CLASS,
        "period": period,
        "as_of_boundary": as_of_boundary,
        "unit": "fraction_of_notional",
        "sign_convention": "positive_rate_paid_by_longs_received_by_shorts",
        "period_count": len(periods),
        "expected_record_count": expected_record_count,
        "matched_record_count": matched_record_count,
        "missing_period_count": missing_period_count,
        "periods": periods,
        "warnings": warnings,
        "errors": errors or [],
        "source_artifacts": source_artifacts,
    }


def _valid_funding_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    valid = []
    warnings = []
    for record in records:
        if not isinstance(record, dict):
            continue
        as_of = record.get("as_of")
        metrics = record.get("metrics") if isinstance(record.get("metrics"), dict) else {}
        rate = metrics.get("funding_rate")
        as_of_dt = _parse_optional_utc(as_of)
        funding_rate = _finite_number_or_none(rate)
        if as_of_dt is None or funding_rate is None:
            warnings.append(
                _warning(
                    "invalid_funding_record",
                    "Funding cost alignment skipped a funding record with invalid as_of or funding_rate.",
                )
            )
            continue
        valid.append(
            {
                "as_of": _iso(as_of_dt),
                "as_of_dt": as_of_dt,
                "funding_rate": funding_rate,
            }
        )
    return sorted(valid, key=lambda item: item["as_of"]), warnings


def _funding_status(*, matched_record_count: int, missing_period_count: int) -> str:
    if matched_record_count == 0:
        return "unavailable"
    if missing_period_count:
        return "partial"
    return "available"


def _expected_funding_record_count(start: datetime, end: datetime, *, period: str) -> int:
    seconds = _period_seconds(period)
    if seconds is None or end <= start:
        return 1
    start_ts = int(start.timestamp())
    end_ts = int(end.timestamp())
    next_ts = ((start_ts // seconds) + 1) * seconds
    count = 0
    while next_ts <= end_ts:
        count += 1
        next_ts += seconds
    return count


def _period_seconds(period: str) -> int | None:
    value = str(period or "").strip().lower()
    if not value.endswith("h"):
        return None
    raw = value[:-1]
    if not raw.isdigit():
        return None
    hours = int(raw)
    if hours <= 0:
        return None
    return hours * 3600


def _coverage_warnings(*, status: str, missing_period_count: int) -> list[dict[str, Any]]:
    if status == "unavailable":
        return [
            _warning(
                "funding_history_unavailable",
                "No matching funding records are available for the evaluation window.",
            )
        ]
    if status == "partial":
        return [
            _warning(
                "funding_history_partial",
                f"Funding records are missing for {missing_period_count} evaluation periods.",
            )
        ]
    return []


def _warning_list(values: list[Any] | None) -> list[dict[str, Any]]:
    warnings = []
    for value in values or []:
        if isinstance(value, dict):
            warnings.append({**value, "source": str(value.get("source") or FUNDING_COST_SOURCE)})
        elif isinstance(value, str) and value.strip():
            warnings.append(_warning("funding_upstream_warning", value.strip()))
    return warnings


def _warning(code: str, message: str) -> dict[str, Any]:
    return {
        "severity": "warning",
        "code": code,
        "message": message,
        "source": FUNDING_COST_SOURCE,
    }


def _open_time(row: dict[str, Any]) -> str:
    value = row.get("open_time")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("OHLCV row open_time must be an ISO 8601 UTC string for funding alignment.")
    return _iso(_parse_utc(value, "open_time"))


def _parse_optional_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return _parse_utc(value, "as_of")
    except ValueError:
        return None


def _parse_utc(value: str, field: str) -> datetime:
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO 8601 UTC string.") from exc
    if timestamp.tzinfo is None:
        raise ValueError(f"{field} must include a UTC offset.")
    return timestamp.astimezone(timezone.utc).replace(microsecond=0)


def _format_optional_utc(value: str | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("as_of must include a UTC offset.")
        return _iso(value)
    if isinstance(value, str) and value.strip():
        return _iso(_parse_utc(value, "as_of"))
    raise ValueError("as_of must be an ISO 8601 UTC string.")


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _finite_number_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if hasattr(value, "item"):
        value = value.item()
        if isinstance(value, bool):
            return None
    if not isinstance(value, (int, float)):
        return None
    number = float(value)
    if number != number or number in {float("inf"), float("-inf")}:
        return None
    return number


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value or [] if isinstance(item, str) and item.strip()]
