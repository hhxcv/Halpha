from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


DEFAULT_DISPLAY_TIMEZONE = "Asia/Shanghai"


def configured_display_timezone(config: dict[str, Any]) -> str:
    dashboard = config.get("dashboard") if isinstance(config.get("dashboard"), dict) else {}
    run = config.get("run") if isinstance(config.get("run"), dict) else {}
    for candidate in (dashboard.get("display_timezone"), run.get("timezone"), DEFAULT_DISPLAY_TIMEZONE):
        if not isinstance(candidate, str) or not candidate.strip():
            continue
        timezone_name = candidate.strip()
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            continue
        return timezone_name
    return DEFAULT_DISPLAY_TIMEZONE


def display_timezone(config: dict[str, Any]) -> ZoneInfo:
    return ZoneInfo(configured_display_timezone(config))


def display_run_id(now: datetime | None, config: dict[str, Any]) -> str:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(display_timezone(config)).strftime("%Y%m%dT%H%M%S%z")


def format_display_timestamp(value: datetime | str, config: dict[str, Any]) -> str:
    timestamp = _coerce_timestamp(value)
    timezone_name = configured_display_timezone(config)
    local = timestamp.astimezone(ZoneInfo(timezone_name)).replace(microsecond=0)
    return f"{local:%Y-%m-%d %H:%M:%S} {timezone_name} ({_utc_offset(local)})"


def _coerce_timestamp(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        timestamp = value
    elif isinstance(value, str):
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise TypeError("timestamp must be a datetime or ISO 8601 string.")
    if timestamp.tzinfo is None:
        raise ValueError("timestamp must include a UTC offset.")
    return timestamp.astimezone(timezone.utc)


def _utc_offset(value: datetime) -> str:
    offset = value.utcoffset()
    if offset is None:
        return "UTC+00:00"
    total_seconds = int(offset.total_seconds())
    sign = "+" if total_seconds >= 0 else "-"
    total_seconds = abs(total_seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes = remainder // 60
    return f"UTC{sign}{hours:02d}:{minutes:02d}"
