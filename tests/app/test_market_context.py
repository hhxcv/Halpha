from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from nautilus_trader.adapters.binance.common.enums import BinanceKlineInterval

from halpha.public_market import (
    BinancePublicMarketContext,
    FIFTEEN_MINUTES_MS,
    ONE_MINUTE_MS,
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
        interval_ms = (
            ONE_MINUTE_MS
            if interval is BinanceKlineInterval.MINUTE_1
            else FIFTEEN_MINUTES_MS
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
