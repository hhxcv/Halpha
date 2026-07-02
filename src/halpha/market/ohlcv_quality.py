from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any


OHLCV_TIMEFRAME_DURATIONS = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
    "1w": timedelta(weeks=1),
    "1M": timedelta(days=31),
}
OHLCV_TIMEFRAME_ORDER = ("1m", "5m", "15m", "1h", "4h", "1d", "1w", "1M")
STALE_CANDLE_TOLERANCE_MULTIPLIER = 2
STALE_CANDLE_MIN_TOLERANCE = timedelta(minutes=15)
QUALITY_SAMPLE_LIMIT = 3


def ohlcv_record_invariant_errors(record: dict[str, Any]) -> list[str]:
    identity = _record_identity(record)
    errors = []
    for field in ("open", "high", "low", "close"):
        value = record.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not isfinite(float(value)):
            errors.append(f"{identity}: {field} must be a finite number.")
        elif float(value) <= 0:
            errors.append(f"{identity}: {field} must be positive.")

    volume = record.get("volume")
    if not isinstance(volume, (int, float)) or isinstance(volume, bool) or not isfinite(float(volume)):
        errors.append(f"{identity}: volume must be a finite number.")
    elif float(volume) < 0:
        errors.append(f"{identity}: volume must be zero or positive.")

    if not errors:
        open_value = float(record["open"])
        high_value = float(record["high"])
        low_value = float(record["low"])
        close_value = float(record["close"])
        if high_value < max(open_value, close_value, low_value):
            errors.append(f"{identity}: high must be greater than or equal to open, close, and low.")
        if low_value > min(open_value, close_value, high_value):
            errors.append(f"{identity}: low must be less than or equal to open, close, and high.")

    timeframe = str(record.get("timeframe") or "")
    if timeframe in OHLCV_TIMEFRAME_DURATIONS:
        opened_at = _parse_utc_or_none(record.get("open_time"))
        if opened_at is not None and not ohlcv_timeframe_is_aligned(opened_at, timeframe):
            errors.append(
                f"{identity}: open_time must align to the {timeframe} UTC timeframe boundary."
            )

    return errors


def ohlcv_series_quality(
    records: list[dict[str, Any]],
    *,
    timeframe: str,
    now: datetime | str | None = None,
) -> dict[str, Any]:
    duration = OHLCV_TIMEFRAME_DURATIONS.get(timeframe)
    ordered = sorted(records, key=lambda item: str(item.get("open_time") or ""))
    open_times = [str(record.get("open_time")) for record in ordered if record.get("open_time")]
    unique_open_times = sorted(set(open_times))
    duplicate_samples, duplicate_count = _duplicate_open_time_samples(open_times)
    missing_samples, missing_count = _missing_interval_samples(unique_open_times, timeframe, duration)
    freshness = _freshness_state(unique_open_times[-1] if unique_open_times else None, duration, now=now)
    status = "degraded" if duplicate_count or missing_count or freshness["stale_latest_candle"] else "ok"
    return {
        "status": status,
        "timeframe_duration_seconds": int(duration.total_seconds()) if duration is not None else None,
        "range_start": unique_open_times[0] if unique_open_times else None,
        "range_end": unique_open_times[-1] if unique_open_times else None,
        "duplicate_open_time_count": duplicate_count,
        "duplicate_open_time_samples": duplicate_samples,
        "missing_interval_count": missing_count,
        "missing_interval_samples": missing_samples,
        **freshness,
    }


def quality_warning_messages(
    *,
    source: str,
    symbol: str,
    timeframe: str,
    quality: dict[str, Any],
) -> list[str]:
    warnings = []
    duplicate_count = int(quality.get("duplicate_open_time_count") or 0)
    if duplicate_count:
        warnings.append(
            f"{source} {symbol} {timeframe} has {duplicate_count} duplicate OHLCV open_time value(s)."
        )
    missing_count = int(quality.get("missing_interval_count") or 0)
    if missing_count:
        warnings.append(
            f"{source} {symbol} {timeframe} is missing {missing_count} expected OHLCV interval(s)."
        )
    if quality.get("stale_latest_candle") is True:
        latest = quality.get("range_end") or "missing"
        reference = quality.get("freshness_reference_time") or "unknown"
        warnings.append(f"{source} {symbol} {timeframe} latest OHLCV candle is stale: {latest} at {reference}.")
    return warnings


def _duplicate_open_time_samples(open_times: list[str]) -> tuple[list[dict[str, Any]], int]:
    counts: dict[str, int] = {}
    for open_time in open_times:
        counts[open_time] = counts.get(open_time, 0) + 1
    duplicates = [
        {"open_time": open_time, "duplicate_count": count - 1}
        for open_time, count in sorted(counts.items())
        if count > 1
    ]
    total = sum(int(item["duplicate_count"]) for item in duplicates)
    return _bounded_samples(duplicates), total


def _missing_interval_samples(
    open_times: list[str],
    timeframe: str,
    duration: timedelta | None,
) -> tuple[list[dict[str, Any]], int]:
    if duration is None or len(open_times) < 2:
        return [], 0

    gaps = []
    total = 0
    parsed = [(value, _parse_utc_or_none(value)) for value in open_times]
    for (previous_value, previous_time), (next_value, next_time) in zip(parsed, parsed[1:]):
        if previous_time is None or next_time is None:
            continue
        expected_next = ohlcv_next_open_time(previous_time, timeframe)
        if next_time <= expected_next:
            continue
        missing = 0
        cursor = expected_next
        while cursor < next_time:
            missing += 1
            cursor = ohlcv_next_open_time(cursor, timeframe)
        total += missing
        gaps.append(
            {
                "after_open_time": previous_value,
                "before_open_time": next_value,
                "expected_next_open_time": _format_utc(expected_next),
                "missing_intervals": missing,
            }
        )
    return _bounded_samples(gaps), total


def _freshness_state(
    latest_open_time: str | None,
    duration: timedelta | None,
    *,
    now: datetime | str | None,
) -> dict[str, Any]:
    reference = _coerce_utc_or_none(now)
    if latest_open_time is None or duration is None or reference is None:
        return {
            "stale_latest_candle": False,
            "freshness_reference_time": _format_utc(reference) if reference is not None else None,
            "stale_after_open_time": None,
            "stale_tolerance_seconds": None,
        }
    latest = _parse_utc_or_none(latest_open_time)
    if latest is None:
        stale_tolerance = _stale_tolerance(duration)
        return {
            "stale_latest_candle": False,
            "freshness_reference_time": _format_utc(reference),
            "stale_after_open_time": None,
            "stale_tolerance_seconds": int(stale_tolerance.total_seconds()),
        }
    stale_tolerance = _stale_tolerance(duration)
    stale_after = latest + stale_tolerance
    return {
        "stale_latest_candle": reference > stale_after,
        "freshness_reference_time": _format_utc(reference),
        "stale_after_open_time": _format_utc(stale_after),
        "stale_tolerance_seconds": int(stale_tolerance.total_seconds()),
    }


def _stale_tolerance(duration: timedelta) -> timedelta:
    return max(duration * STALE_CANDLE_TOLERANCE_MULTIPLIER, STALE_CANDLE_MIN_TOLERANCE)


def _record_identity(record: dict[str, Any]) -> str:
    return (
        "ohlcv record "
        f"source={record.get('source')}, symbol={record.get('symbol')}, "
        f"timeframe={record.get('timeframe')}, open_time={record.get('open_time')}"
    )


def ohlcv_timeframe_is_aligned(value: datetime, timeframe: str) -> bool:
    value = value.astimezone(timezone.utc).replace(microsecond=0)
    if timeframe == "1M":
        return (
            value.day == 1
            and value.hour == 0
            and value.minute == 0
            and value.second == 0
        )
    if timeframe == "1w":
        return (
            value.weekday() == 0
            and value.hour == 0
            and value.minute == 0
            and value.second == 0
        )
    duration = OHLCV_TIMEFRAME_DURATIONS.get(timeframe)
    if duration is None:
        return False
    seconds = int(value.timestamp())
    return seconds % int(duration.total_seconds()) == 0


def ohlcv_next_open_time(value: datetime, timeframe: str) -> datetime:
    value = value.astimezone(timezone.utc).replace(microsecond=0)
    if timeframe == "1M":
        year = value.year + (1 if value.month == 12 else 0)
        month = 1 if value.month == 12 else value.month + 1
        return value.replace(year=year, month=month, day=1, hour=0, minute=0, second=0)
    duration = OHLCV_TIMEFRAME_DURATIONS.get(timeframe)
    if duration is None:
        raise KeyError(timeframe)
    return value + duration


def _parse_utc_or_none(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def _coerce_utc_or_none(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return None
        return value.astimezone(timezone.utc).replace(microsecond=0)
    return _parse_utc_or_none(value)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _bounded_samples(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(items) <= QUALITY_SAMPLE_LIMIT:
        return items
    return [*items[: QUALITY_SAMPLE_LIMIT - 1], items[-1]]
