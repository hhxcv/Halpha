from __future__ import annotations

from datetime import datetime, timezone

from halpha.time_display import configured_display_timezone, display_run_id, format_display_timestamp


def test_display_timestamp_uses_configured_run_timezone() -> None:
    config = {"run": {"timezone": "America/New_York"}}
    value = datetime(2026, 6, 5, 0, 30, tzinfo=timezone.utc)

    assert configured_display_timezone(config) == "America/New_York"
    assert display_run_id(value, config) == "20260604T203000-0400"
    assert format_display_timestamp(value, config) == "2026-06-04 20:30:00 America/New_York (UTC-04:00)"


def test_dashboard_display_timezone_overrides_run_timezone() -> None:
    config = {"run": {"timezone": "America/New_York"}, "dashboard": {"display_timezone": "UTC"}}
    value = "2026-06-05T00:30:00Z"

    assert configured_display_timezone(config) == "UTC"
    assert display_run_id(datetime(2026, 6, 5, 0, 30, tzinfo=timezone.utc), config) == "20260605T003000+0000"
    assert format_display_timestamp(value, config) == "2026-06-05 00:30:00 UTC (UTC+00:00)"
