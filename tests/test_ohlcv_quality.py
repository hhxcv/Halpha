from __future__ import annotations

from datetime import datetime, timezone

from halpha.market.ohlcv_quality import (
    ohlcv_next_open_time,
    ohlcv_record_invariant_errors,
)


def test_weekly_and_monthly_timeframes_use_calendar_boundaries() -> None:
    weekly_record = _record(timeframe="1w", open_time="2026-06-01T00:00:00Z")
    monthly_record = _record(timeframe="1month", open_time="2026-06-01T00:00:00Z")

    assert ohlcv_record_invariant_errors(weekly_record) == []
    assert ohlcv_record_invariant_errors(monthly_record) == []
    assert ohlcv_next_open_time(
        datetime(2026, 6, 1, tzinfo=timezone.utc),
        "1month",
    ) == datetime(2026, 7, 1, tzinfo=timezone.utc)


def test_weekly_and_monthly_timeframes_reject_non_boundary_open_times() -> None:
    weekly_errors = ohlcv_record_invariant_errors(_record(timeframe="1w", open_time="2026-06-02T00:00:00Z"))
    monthly_errors = ohlcv_record_invariant_errors(
        _record(timeframe="1month", open_time="2026-06-02T00:00:00Z")
    )

    assert "open_time must align to the 1w UTC timeframe boundary" in weekly_errors[0]
    assert "open_time must align to the 1month UTC timeframe boundary" in monthly_errors[0]


def _record(*, timeframe: str, open_time: str) -> dict[str, object]:
    return {
        "source": "binance",
        "symbol": "BTCUSDT",
        "timeframe": timeframe,
        "open_time": open_time,
        "open": 100,
        "high": 101,
        "low": 99,
        "close": 100,
        "volume": 10,
        "fetched_at": "2026-06-05T00:00:00Z",
    }
