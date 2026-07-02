from __future__ import annotations

from halpha.market.ohlcv_quality import ohlcv_series_quality


def test_ohlcv_quality_uses_minimum_freshness_tolerance_for_short_timeframes() -> None:
    quality = ohlcv_series_quality(
        [{"open_time": "2026-06-05T00:00:00Z"}],
        timeframe="1m",
        now="2026-06-05T00:02:06Z",
    )

    assert quality["stale_latest_candle"] is False
    assert quality["stale_after_open_time"] == "2026-06-05T00:15:00Z"
    assert quality["stale_tolerance_seconds"] == 900


def test_ohlcv_quality_uses_minimum_freshness_tolerance_for_five_minute_views() -> None:
    quality = ohlcv_series_quality(
        [{"open_time": "2026-06-05T00:30:00Z"}],
        timeframe="5m",
        now="2026-06-05T00:40:11Z",
    )

    assert quality["stale_latest_candle"] is False
    assert quality["stale_after_open_time"] == "2026-06-05T00:45:00Z"
    assert quality["stale_tolerance_seconds"] == 900
