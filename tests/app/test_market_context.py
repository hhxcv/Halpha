from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from nautilus_trader.adapters.binance.common.enums import BinanceEnvironment

import halpha.public_market as public_market_module
from halpha.public_market import (
    BINANCE_KLINE_INTERVALS,
    BinancePublicMarketContext,
    MARKET_INTERVAL_MILLISECONDS,
    MarketContextUnavailable,
)


class FakeMarketApi:
    def __init__(self, *, complete: bool = True) -> None:
        self.complete = complete
        self.server_time_ms = 1_800_000_100_000

    async def query_ticker_book(self, symbol=None, symbols=None):
        assert symbol == "BTCUSDT"
        assert symbols is None
        return [
            SimpleNamespace(
                symbol=symbol,
                bidPrice="119",
                askPrice="121",
                time=self.server_time_ms,
            )
        ]

    async def query_klines(
        self,
        symbol,
        interval,
        limit=None,
        start_time=None,
        end_time=None,
    ):
        assert symbol == "BTCUSDT"
        assert end_time is not None
        count = int(limit)
        start = int(start_time)
        interval_ms = next(
            MARKET_INTERVAL_MILLISECONDS[key]
            for key, native in BINANCE_KLINE_INTERVALS.items()
            if interval is native
        )
        if not self.complete:
            count -= 1
        return [
            SimpleNamespace(
                open_time=start + index * interval_ms,
                open=str(100 + index),
                high=str(102 + index),
                low=str(98 + index),
                close=str(101 + index),
                volume="10",
                close_time=start + (index + 1) * interval_ms - 1,
                trades_count=7,
            )
            for index in range(count)
        ]


def test_public_market_context_uses_closed_contiguous_bars_and_exact_prices() -> None:
    provider = BinancePublicMarketContext(
        "BINANCE_DEMO",
        market_api=FakeMarketApi(),
    )

    context = asyncio.run(provider.fetch("BTCUSDT-PERP", 20))

    assert context.source == "BINANCE_DEMO_PUBLIC"
    assert context.reference_price == "120"
    assert context.bid_price == "119"
    assert context.ask_price == "121"
    assert context.latest_close_1m == "101"
    assert context.latest_volume_1m == "10"
    assert context.latest_trade_count_1m == 7
    assert context.latest_close_15m == "120"
    assert context.channel_upper == "121"
    assert context.channel_lower == "98"
    assert Decimal(context.long_breakout_gap_pct) == Decimal(1) / Decimal(120) * 100
    assert Decimal(context.short_breakout_gap_pct) == Decimal(22) / Decimal(120) * 100


def test_public_market_context_keeps_atr_warmup_for_short_channel() -> None:
    provider = BinancePublicMarketContext(
        "BINANCE_DEMO",
        market_api=FakeMarketApi(),
    )

    context = asyncio.run(provider.fetch("BTCUSDT-PERP", 4))

    assert context.channel_lookback_15m == 4
    assert context.latest_close_15m == "115"
    assert context.channel_upper == "116"
    assert context.channel_lower == "109"
    assert Decimal(context.long_breakout_gap_pct) == Decimal(-4) / Decimal(120) * 100
    assert Decimal(context.short_breakout_gap_pct) == Decimal(11) / Decimal(120) * 100


def test_public_market_context_rejects_incomplete_window() -> None:
    provider = BinancePublicMarketContext(
        "BINANCE_DEMO",
        market_api=FakeMarketApi(complete=False),
    )

    with pytest.raises(
        MarketContextUnavailable,
        match="MARKET_CONTEXT_READ_FAILED_VALUEERROR",
    ):
        asyncio.run(provider.fetch("BTCUSDT-PERP", 20))


def test_public_market_window_returns_exact_contiguous_review_bars() -> None:
    provider = BinancePublicMarketContext(
        "BINANCE_DEMO",
        market_api=FakeMarketApi(),
        observed_at_provider=lambda: datetime(2027, 2, 1, tzinfo=UTC),
    )
    start = datetime(2027, 1, 15, 8, 0, 30, tzinfo=UTC)

    window = asyncio.run(
        provider.fetch_window(
            "BTCUSDT-PERP",
            "1m",
            start,
            start + timedelta(minutes=4),
        )
    )

    assert window.interval == "1m"
    assert window.source == "BINANCE_DEMO_PUBLIC"
    assert len(window.bars) == 5
    assert window.bars[0].open_at == datetime(2027, 1, 15, 8, 0, tzinfo=UTC)
    assert window.bars[-1].close == "105"
    assert window.source_cutoff == datetime(2027, 1, 15, 8, 5, tzinfo=UTC)


def test_current_open_daily_candle_does_not_project_a_future_source_cutoff() -> None:
    observed_at = datetime(2027, 1, 15, 8, 2, 30, tzinfo=UTC)
    provider = BinancePublicMarketContext(
        "BINANCE_DEMO",
        market_api=FakeMarketApi(),
        observed_at_provider=lambda: observed_at,
    )

    window = asyncio.run(
        provider.fetch_window(
            "BTCUSDT-PERP",
            "1d",
            observed_at,
            observed_at,
        )
    )

    assert len(window.bars) == 1
    assert window.bars[0].open_at == datetime(2027, 1, 15, tzinfo=UTC)
    assert window.bars[0].close_at == datetime(2027, 1, 16, tzinfo=UTC)
    assert window.source_cutoff == observed_at
    assert window.source_cutoff < window.bars[0].close_at


@pytest.mark.parametrize(
    ("profile", "expected_environment", "expected_source"),
    (
        (
            "BINANCE_DEMO",
            BinanceEnvironment.DEMO,
            "BINANCE_DEMO_PUBLIC",
        ),
        (
            "BINANCE_LIVE_READ_ONLY",
            BinanceEnvironment.LIVE,
            "BINANCE_LIVE_PUBLIC",
        ),
        (
            "BINANCE_LIVE_WRITE",
            BinanceEnvironment.LIVE,
            "BINANCE_LIVE_PUBLIC",
        ),
    ),
)
def test_market_profile_routes_context_and_history_to_only_its_own_environment(
    monkeypatch: pytest.MonkeyPatch,
    profile: str,
    expected_environment: BinanceEnvironment,
    expected_source: str,
) -> None:
    environments: list[BinanceEnvironment] = []

    def fake_http_client(**kwargs):
        environments.append(kwargs["environment"])
        return object()

    monkeypatch.setattr(
        public_market_module,
        "get_cached_binance_http_client",
        fake_http_client,
    )
    monkeypatch.setattr(
        public_market_module,
        "BinanceFuturesMarketHttpAPI",
        lambda *_args, **_kwargs: FakeMarketApi(),
    )

    provider = BinancePublicMarketContext(profile)
    start = datetime(2027, 1, 15, 8, 0, tzinfo=UTC)
    context = asyncio.run(provider.fetch("BTCUSDT-PERP", 20))
    window = asyncio.run(
        provider.fetch_window(
            "BTCUSDT-PERP",
            "1m",
            start,
            start,
        )
    )

    assert environments == [expected_environment]
    assert context.source == expected_source
    assert window.source == expected_source


def test_unknown_profile_cannot_fall_back_to_live_market_data() -> None:
    with pytest.raises(ValueError, match="PUBLIC_MARKET_PROFILE_UNSUPPORTED"):
        BinancePublicMarketContext(
            "UNRECOGNIZED_PROFILE",
            market_api=FakeMarketApi(),
        )


@pytest.mark.parametrize(
    ("interval", "duration"),
    [
        ("5m", timedelta(minutes=5)),
        ("15m", timedelta(minutes=15)),
        ("1h", timedelta(hours=1)),
        ("4h", timedelta(hours=4)),
        ("1d", timedelta(days=1)),
    ],
)
def test_public_market_window_supports_chart_intervals(
    interval: str,
    duration: timedelta,
) -> None:
    provider = BinancePublicMarketContext(
        "BINANCE_DEMO",
        market_api=FakeMarketApi(),
    )
    start = datetime(2027, 1, 15, 0, 0, tzinfo=UTC)

    window = asyncio.run(
        provider.fetch_window(
            "BTCUSDT-PERP",
            interval,
            start,
            start + duration * 2,
        )
    )

    assert window.interval == interval
    assert len(window.bars) == 3
    assert window.bars[1].open_at == start + duration


def test_public_market_window_rejects_unbounded_review_range() -> None:
    provider = BinancePublicMarketContext(
        "BINANCE_DEMO",
        market_api=FakeMarketApi(),
    )
    start = datetime(2027, 1, 15, 8, 0, tzinfo=UTC)

    with pytest.raises(MarketContextUnavailable, match="MARKET_WINDOW_RANGE_INVALID"):
        asyncio.run(
            provider.fetch_window(
                "BTCUSDT-PERP",
                "1m",
                start,
                start + timedelta(minutes=300),
            )
        )
