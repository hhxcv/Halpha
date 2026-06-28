from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from halpha.data.collection_coverage import (
    COVERAGE_STATE_ARTIFACT,
    read_collection_coverage_state,
    summarize_collection_coverage,
)
from halpha.market.ohlcv_quality import (
    OHLCV_TIMEFRAME_DURATIONS,
    ohlcv_next_open_time,
    ohlcv_series_quality,
    quality_warning_messages,
)
from halpha.market.ohlcv_store import OHLCVParquetStore, OHLCVStoreError
from halpha.storage import display_path, runtime_root


OHLCV_QUERY_SCHEMA_VERSION = 1
MISSING_SAMPLE_LIMIT = 5


class OHLCVQueryError(Exception):
    def __init__(self, message: str, *, exit_code: int = 3) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def query_ohlcv_records(
    storage_dir: Path | str,
    *,
    source: str,
    symbol: str,
    timeframe: str,
    start: str | datetime,
    end: str | datetime,
    as_of: str | datetime | None = None,
    config_path: Path | None = None,
    run_output_dir: Path | str | None = None,
    limit: int | None = None,
    end_inclusive: bool = False,
    now: datetime | str | None = None,
) -> dict[str, Any]:
    duration = _timeframe_duration(timeframe)
    requested_start = _format_utc(start, "start")
    requested_end = _format_utc(end, "end")
    start_dt = _parse_utc(requested_start, "start")
    end_dt = _parse_utc(requested_end, "end")
    if end_dt < start_dt or (end_dt == start_dt and not end_inclusive):
        raise OHLCVQueryError("end must be greater than start for OHLCV queries.", exit_code=2)

    as_of_dt = _parse_optional_utc(as_of, "as_of")
    all_records = _read_group_records(
        storage_dir,
        source=source,
        symbol=symbol,
        timeframe=timeframe,
        run_output_dir=run_output_dir,
    )
    selected = _filter_records(
        all_records,
        start_dt=start_dt,
        end_dt=end_dt,
        duration=duration,
        timeframe=timeframe,
        as_of_dt=as_of_dt,
        end_inclusive=end_inclusive,
    )
    return _query_result(
        storage_dir,
        source=source,
        symbol=symbol,
        timeframe=timeframe,
        records=selected,
        history_row_count=len(all_records),
        requested_start=requested_start,
        requested_end=requested_end,
        as_of=_format_utc(as_of, "as_of") if as_of is not None else None,
        duration=duration,
        config_path=config_path,
        limit=limit,
        end_inclusive=end_inclusive,
        now=now,
    )


def query_latest_ohlcv_records(
    storage_dir: Path | str,
    *,
    source: str,
    symbol: str,
    timeframe: str,
    lookback: int,
    as_of: str | datetime | None = None,
    config_path: Path | None = None,
    run_output_dir: Path | str | None = None,
    limit: int | None = None,
    now: datetime | str | None = None,
) -> dict[str, Any]:
    if isinstance(lookback, bool) or not isinstance(lookback, int) or lookback <= 0:
        raise OHLCVQueryError("lookback must be a positive integer.", exit_code=2)
    duration = _timeframe_duration(timeframe)
    as_of_dt = _parse_optional_utc(as_of, "as_of")
    all_records = _read_group_records(
        storage_dir,
        source=source,
        symbol=symbol,
        timeframe=timeframe,
        run_output_dir=run_output_dir,
    )
    eligible = [
        record
        for record in all_records
        if _is_closed_candle(record, timeframe=timeframe, as_of_dt=as_of_dt)
    ]
    selected = eligible[-lookback:] if eligible else []
    requested_start = selected[0]["open_time"] if selected else None
    requested_end = selected[-1]["open_time"] if selected else None
    return _query_result(
        storage_dir,
        source=source,
        symbol=symbol,
        timeframe=timeframe,
        records=selected,
        history_row_count=len(all_records),
        requested_start=requested_start,
        requested_end=requested_end,
        as_of=_format_utc(as_of, "as_of") if as_of is not None else None,
        duration=duration,
        config_path=config_path,
        limit=limit,
        end_inclusive=True,
        now=now,
        query_mode="latest_lookback",
        requested_lookback=lookback,
    )


def _query_result(
    storage_dir: Path | str,
    *,
    source: str,
    symbol: str,
    timeframe: str,
    records: list[dict[str, Any]],
    history_row_count: int,
    requested_start: str | None,
    requested_end: str | None,
    as_of: str | None,
    duration: timedelta,
    config_path: Path | None,
    limit: int | None,
    end_inclusive: bool,
    now: datetime | str | None,
    query_mode: str = "range",
    requested_lookback: int | None = None,
) -> dict[str, Any]:
    bounded_records, truncated = _apply_limit(records, limit)
    actual_start = bounded_records[0]["open_time"] if bounded_records else None
    actual_end = bounded_records[-1]["open_time"] if bounded_records else None
    quality = ohlcv_series_quality(records, timeframe=timeframe, now=as_of or now)
    missing = _missing_diagnostics(
        records,
        timeframe=timeframe,
        requested_start=requested_start,
        requested_end=requested_end,
        as_of=as_of,
        duration=duration,
        end_inclusive=end_inclusive,
    )
    coverage = _coverage_diagnostics(
        config_path=config_path,
        source=source,
        symbol=symbol,
        timeframe=timeframe,
        requested_start=requested_start,
        requested_end=requested_end,
    )
    warnings = _query_warnings(
        source=source,
        symbol=symbol,
        timeframe=timeframe,
        quality=quality,
        missing=missing,
        coverage=coverage,
        truncated=truncated,
    )
    return {
        "schema_version": OHLCV_QUERY_SCHEMA_VERSION,
        "artifact_type": "ohlcv_query_result",
        "status": "warning" if warnings else "ok",
        "query_mode": query_mode,
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "requested_start": requested_start,
        "requested_end": requested_end,
        "requested_lookback": requested_lookback,
        "as_of": as_of,
        "time_fields": {
            "range_field": "open_time",
            "start_inclusive": True,
            "end_inclusive": end_inclusive,
            "closed_candle_rule": "open_time + timeframe_duration <= as_of when as_of is provided",
        },
        "range": {
            "start": actual_start,
            "end": actual_end,
            "latest_candle_time": actual_end,
        },
        "matched_record_count": len(records),
        "record_count": len(bounded_records),
        "history_row_count": history_row_count,
        "truncated": truncated,
        "limit": limit,
        "records": bounded_records,
        "missing_diagnostics": missing,
        "quality": quality,
        "coverage_diagnostics": coverage,
        "warnings": warnings,
        "errors": [],
        "source_artifacts": _source_artifacts(storage_dir, config_path=config_path),
    }


def _read_group_records(
    storage_dir: Path | str,
    *,
    source: str,
    symbol: str,
    timeframe: str,
    run_output_dir: Path | str | None,
) -> list[dict[str, Any]]:
    try:
        return OHLCVParquetStore(storage_dir, run_output_dir=run_output_dir).read_records(
            source=source,
            symbol=symbol,
            timeframe=timeframe,
        )
    except OHLCVStoreError as exc:
        raise OHLCVQueryError(str(exc), exit_code=3) from exc


def _filter_records(
    records: list[dict[str, Any]],
    *,
    start_dt: datetime,
    end_dt: datetime,
    duration: timedelta,
    timeframe: str,
    as_of_dt: datetime | None,
    end_inclusive: bool,
) -> list[dict[str, Any]]:
    selected = []
    for record in records:
        open_time = _parse_utc(str(record.get("open_time") or ""), "open_time")
        if open_time < start_dt:
            continue
        if end_inclusive:
            if open_time > end_dt:
                continue
        elif open_time >= end_dt:
            continue
        if not _is_closed_candle(record, timeframe=timeframe, as_of_dt=as_of_dt):
            continue
        selected.append(record)
    return sorted(selected, key=lambda item: str(item.get("open_time") or ""))


def _is_closed_candle(
    record: dict[str, Any],
    *,
    timeframe: str,
    as_of_dt: datetime | None,
) -> bool:
    if as_of_dt is None:
        return True
    open_time = _parse_utc(str(record.get("open_time") or ""), "open_time")
    return ohlcv_next_open_time(open_time, timeframe) <= as_of_dt


def _apply_limit(records: list[dict[str, Any]], limit: int | None) -> tuple[list[dict[str, Any]], bool]:
    if limit is None:
        return records, False
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise OHLCVQueryError("limit must be a positive integer.", exit_code=2)
    if len(records) <= limit:
        return records, False
    return records[:limit], True


def _missing_diagnostics(
    records: list[dict[str, Any]],
    *,
    timeframe: str,
    requested_start: str | None,
    requested_end: str | None,
    as_of: str | None,
    duration: timedelta,
    end_inclusive: bool,
) -> dict[str, Any]:
    if requested_start is None or requested_end is None:
        return {
            "status": "not_available",
            "timeframe_duration_seconds": int(duration.total_seconds()),
            "expected_interval_count": None,
            "returned_interval_count": len(records),
            "missing_interval_count": 0,
            "missing_open_time_samples": [],
        }
    expected = _expected_open_times(
        requested_start,
        requested_end,
        duration=duration,
        timeframe=timeframe,
        as_of=as_of,
        end_inclusive=end_inclusive,
    )
    returned = {str(record.get("open_time")) for record in records if record.get("open_time")}
    missing = [value for value in expected if value not in returned]
    status = "degraded" if missing else "ok"
    return {
        "status": status,
        "timeframe": timeframe,
        "timeframe_duration_seconds": int(duration.total_seconds()),
        "expected_interval_count": len(expected),
        "returned_interval_count": len(records),
        "missing_interval_count": len(missing),
        "missing_open_time_samples": _bounded_missing_samples(missing),
    }


def _coverage_diagnostics(
    *,
    config_path: Path | None,
    source: str,
    symbol: str,
    timeframe: str,
    requested_start: str | None,
    requested_end: str | None,
) -> dict[str, Any]:
    identity = {"symbol": symbol, "timeframe": timeframe}
    if config_path is None:
        return {
            "status": "not_requested",
            "state_path": None,
            "data_type": "ohlcv",
            "source": source,
            "identity": identity,
            "record_count": 0,
            "status_counts": {},
            "range_start": None,
            "range_end": None,
            "partial_ranges": [],
            "failed_ranges": [],
            "not_collected_ranges": [],
            "unknown_ranges": [],
            "warnings": [],
            "errors": [],
        }
    state = read_collection_coverage_state(config_path)
    summary = summarize_collection_coverage(
        state,
        data_type="ohlcv",
        source=source,
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
        "data_type": "ohlcv",
        "source": source,
        "identity": identity,
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


def _query_warnings(
    *,
    source: str,
    symbol: str,
    timeframe: str,
    quality: dict[str, Any],
    missing: dict[str, Any],
    coverage: dict[str, Any],
    truncated: bool,
) -> list[dict[str, Any]]:
    warnings = [
        {"code": "degraded_ohlcv_quality", "message": message, "source": "ohlcv_query"}
        for message in quality_warning_messages(source=source, symbol=symbol, timeframe=timeframe, quality=quality)
    ]
    if int(missing.get("missing_interval_count") or 0):
        warnings.append(
            {
                "code": "missing_ohlcv_intervals",
                "message": (
                    f"{source} {symbol} {timeframe} query is missing "
                    f"{missing['missing_interval_count']} expected interval(s)."
                ),
                "source": "ohlcv_query",
            }
        )
    if truncated:
        warnings.append(
            {
                "code": "query_result_truncated",
                "message": f"{source} {symbol} {timeframe} OHLCV query result was truncated by limit.",
                "source": "ohlcv_query",
            }
        )
    if _coverage_incomplete(coverage):
        warnings.append(
            {
                "code": "incomplete_collection_coverage",
                "message": f"{source} {symbol} {timeframe} query overlaps incomplete or unknown collection coverage.",
                "source": "ohlcv_query",
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


def _expected_open_times(
    start: str,
    end: str,
    *,
    duration: timedelta,
    timeframe: str,
    as_of: str | None,
    end_inclusive: bool,
) -> list[str]:
    cursor = _parse_utc(start, "start")
    end_dt = _parse_utc(end, "end")
    as_of_dt = _parse_optional_utc(as_of, "as_of")
    expected = []
    while cursor < end_dt or (end_inclusive and cursor == end_dt):
        if as_of_dt is None or ohlcv_next_open_time(cursor, timeframe) <= as_of_dt:
            expected.append(_iso(cursor))
        cursor = ohlcv_next_open_time(cursor, timeframe)
    return expected


def _bounded_missing_samples(values: list[str]) -> list[str]:
    if len(values) <= MISSING_SAMPLE_LIMIT:
        return values
    return [*values[: MISSING_SAMPLE_LIMIT - 1], values[-1]]


def _source_artifacts(storage_dir: Path | str, *, config_path: Path | None) -> list[str]:
    base = runtime_root(config_path)
    artifacts = [display_path(Path(storage_dir).parent / "metadata" / "ohlcv_sync_state.json", base=base)]
    if config_path is not None:
        artifacts.append(COVERAGE_STATE_ARTIFACT)
    return sorted(set(artifacts))


def _timeframe_duration(timeframe: str) -> timedelta:
    duration = OHLCV_TIMEFRAME_DURATIONS.get(timeframe)
    if duration is None:
        supported = ", ".join(sorted(OHLCV_TIMEFRAME_DURATIONS))
        raise OHLCVQueryError(f"unsupported OHLCV timeframe {timeframe}. Supported: {supported}.", exit_code=2)
    return duration


def _format_utc(value: str | datetime | None, field: str) -> str:
    if value is None:
        raise OHLCVQueryError(f"{field} must be an ISO 8601 UTC string.", exit_code=2)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise OHLCVQueryError(f"{field} must include a UTC offset.", exit_code=2)
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str) and value.strip():
        timestamp = _parse_utc(value.strip(), field)
    else:
        raise OHLCVQueryError(f"{field} must be an ISO 8601 UTC string.", exit_code=2)
    return _iso(timestamp)


def _parse_optional_utc(value: str | datetime | None, field: str) -> datetime | None:
    if value is None:
        return None
    return _parse_utc(_format_utc(value, field), field)


def _parse_utc(value: str, field: str) -> datetime:
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OHLCVQueryError(f"{field} must be an ISO 8601 UTC string.", exit_code=2) from exc
    if timestamp.tzinfo is None:
        raise OHLCVQueryError(f"{field} must include a UTC offset.", exit_code=2)
    return timestamp.astimezone(timezone.utc).replace(microsecond=0)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
