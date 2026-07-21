"""Read-only public market context for the plan decision surface."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal, Protocol

from nautilus_trader.adapters.binance import get_cached_binance_http_client
from nautilus_trader.adapters.binance.common.enums import (
    BinanceAccountType,
    BinanceEnvironment,
    BinanceKlineInterval,
)
from nautilus_trader.adapters.binance.futures.http.market import (
    BinanceFuturesMarketHttpAPI,
)
from nautilus_trader.common.component import LiveClock
from pydantic import BaseModel, ConfigDict

from halpha.domain_values import canonical_decimal
from halpha.planning.indicators import IndicatorBar, native_donchian_atr_snapshot


FIFTEEN_MINUTES_MS = 15 * 60 * 1000
ONE_MINUTE_MS = 60 * 1000
_INSTRUMENT_SYMBOLS = {"BTCUSDT-PERP": "BTCUSDT"}
PUBLIC_MARKET_TIMEOUT_SECONDS = 10
MAX_MARKET_WINDOW_BARS = 300


class MarketContextUnavailable(RuntimeError):
    """Sanitized public-market read failure."""


class MarketContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument_ref: str
    source: str
    source_cutoff: datetime
    latest_closed_1m_at: datetime
    latest_closed_15m_at: datetime
    channel_lookback_15m: int
    bid_price: str
    ask_price: str
    reference_price: str
    latest_close_1m: str
    latest_volume_1m: str
    latest_trade_count_1m: int
    latest_close_15m: str
    channel_upper: str
    channel_lower: str
    atr_14: str
    long_breakout_gap_pct: str
    short_breakout_gap_pct: str


class MarketBar(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    open_at: datetime
    close_at: datetime
    open: str
    high: str
    low: str
    close: str
    volume: str


class MarketWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument_ref: str
    interval: Literal["1m", "15m"]
    source: str
    source_cutoff: datetime
    bars: tuple[MarketBar, ...]


class MarketContextProvider(Protocol):
    async def fetch(self, instrument_ref: str, lookback: int) -> MarketContext: ...

    async def fetch_window(
        self,
        instrument_ref: str,
        interval: Literal["1m", "15m"],
        start_at: datetime,
        end_at: datetime,
    ) -> MarketWindow: ...


class BinanceMarketApi(Protocol):
    async def query_ticker_book(
        self,
        symbol: str | None = None,
        symbols: list[str] | None = None,
    ) -> list[Any]: ...

    async def query_klines(
        self,
        symbol: str,
        interval: BinanceKlineInterval,
        limit: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[Any]: ...


class BinancePublicMarketContext:
    """Read the two public Binance endpoints needed by the planning UI."""

    def __init__(
        self,
        profile: str,
        *,
        proxy_url: str | None = None,
        market_api: BinanceMarketApi | None = None,
    ) -> None:
        demo = profile == "BINANCE_DEMO"
        self._source = "BINANCE_DEMO_PUBLIC" if demo else "BINANCE_LIVE_PUBLIC"
        if market_api is None:
            client = get_cached_binance_http_client(
                clock=LiveClock(),
                account_type=BinanceAccountType.USDT_FUTURES,
                environment=(
                    BinanceEnvironment.DEMO if demo else BinanceEnvironment.LIVE
                ),
                proxy_url=proxy_url,
            )
            market_api = BinanceFuturesMarketHttpAPI(
                client,
                BinanceAccountType.USDT_FUTURES,
            )
        self._market_api = market_api

    async def fetch(self, instrument_ref: str, lookback: int) -> MarketContext:
        symbol = _INSTRUMENT_SYMBOLS.get(instrument_ref)
        if symbol is None:
            raise MarketContextUnavailable("MARKET_CONTEXT_INSTRUMENT_UNSUPPORTED")
        if not 4 <= lookback <= 96:
            raise MarketContextUnavailable("MARKET_CONTEXT_LOOKBACK_INVALID")
        try:
            books = await asyncio.wait_for(
                self._market_api.query_ticker_book(symbol=symbol),
                timeout=PUBLIC_MARKET_TIMEOUT_SECONDS,
            )
            book = next(
                (item for item in books if getattr(item, "symbol", None) == symbol),
                None,
            )
            if book is None or getattr(book, "time", None) is None:
                raise ValueError("public market book invalid")
            server_time_ms = int(book.time)
            indicator_bar_count = max(lookback, 15)
            latest_open_ms = (
                server_time_ms // FIFTEEN_MINUTES_MS - 1
            ) * FIFTEEN_MINUTES_MS
            start_ms = (
                latest_open_ms
                - (indicator_bar_count - 1) * FIFTEEN_MINUTES_MS
            )
            end_ms = latest_open_ms + FIFTEEN_MINUTES_MS - 1
            latest_1m_open_ms = (
                server_time_ms // ONE_MINUTE_MS - 1
            ) * ONE_MINUTE_MS
            bars, latest_1m_bars = await asyncio.gather(
                asyncio.wait_for(
                    self._market_api.query_klines(
                        symbol=symbol,
                        interval=BinanceKlineInterval.MINUTE_15,
                        limit=indicator_bar_count,
                        start_time=start_ms,
                        end_time=end_ms,
                    ),
                    timeout=PUBLIC_MARKET_TIMEOUT_SECONDS,
                ),
                asyncio.wait_for(
                    self._market_api.query_klines(
                        symbol=symbol,
                        interval=BinanceKlineInterval.MINUTE_1,
                        limit=1,
                        start_time=latest_1m_open_ms,
                        end_time=latest_1m_open_ms + ONE_MINUTE_MS - 1,
                    ),
                    timeout=PUBLIC_MARKET_TIMEOUT_SECONDS,
                ),
            )
            if len(bars) != indicator_bar_count:
                raise ValueError("public market sample incomplete")
            if (
                len(latest_1m_bars) != 1
                or int(latest_1m_bars[0].open_time) != latest_1m_open_ms
            ):
                raise ValueError("public market latest 1m bar invalid")
            expected_open_times = [
                start_ms + index * FIFTEEN_MINUTES_MS
                for index in range(indicator_bar_count)
            ]
            if [int(bar.open_time) for bar in bars] != expected_open_times:
                raise ValueError("public market bars not contiguous")
            indicator_bars = tuple(
                IndicatorBar(
                    open=str(bar.open),
                    high=str(bar.high),
                    low=str(bar.low),
                    close=str(bar.close),
                    volume=str(bar.volume),
                    ts_event_ns=(int(bar.close_time) + 1) * 1_000_000,
                )
                for bar in bars
            )
            indicators = native_donchian_atr_snapshot(
                instrument_id=f"{instrument_ref}.BINANCE",
                lookback=lookback,
                bars=indicator_bars,
            )
            if not indicators.initialized:
                raise ValueError("public market indicators not initialized")
            bid = Decimal(str(book.bidPrice))
            ask = Decimal(str(book.askPrice))
            reference = (bid + ask) / Decimal(2)
            upper = Decimal(indicators.upper)
            lower = Decimal(indicators.lower)
            latest_volume_1m = Decimal(str(latest_1m_bars[0].volume))
            latest_trade_count_1m = int(latest_1m_bars[0].trades_count)
            if (
                bid <= 0
                or ask <= 0
                or ask < bid
                or upper <= lower
                or latest_volume_1m < 0
                or latest_trade_count_1m < 0
            ):
                raise ValueError("public market values invalid")
            return MarketContext(
                instrument_ref=instrument_ref,
                source=self._source,
                source_cutoff=datetime.fromtimestamp(int(book.time) / 1000, tz=UTC),
                latest_closed_1m_at=datetime.fromtimestamp(
                    (int(latest_1m_bars[0].close_time) + 1) / 1000,
                    tz=UTC,
                ),
                latest_closed_15m_at=datetime.fromtimestamp(
                    (int(bars[-1].close_time) + 1) / 1000,
                    tz=UTC,
                ),
                channel_lookback_15m=lookback,
                bid_price=canonical_decimal(bid),
                ask_price=canonical_decimal(ask),
                reference_price=canonical_decimal(reference),
                latest_close_1m=canonical_decimal(
                    Decimal(str(latest_1m_bars[0].close))
                ),
                latest_volume_1m=canonical_decimal(latest_volume_1m),
                latest_trade_count_1m=latest_trade_count_1m,
                latest_close_15m=canonical_decimal(Decimal(str(bars[-1].close))),
                channel_upper=canonical_decimal(upper),
                channel_lower=canonical_decimal(lower),
                atr_14=canonical_decimal(Decimal(indicators.atr)),
                long_breakout_gap_pct=canonical_decimal(
                    (upper - reference) / reference * Decimal(100)
                ),
                short_breakout_gap_pct=canonical_decimal(
                    (reference - lower) / reference * Decimal(100)
                ),
            )
        except MarketContextUnavailable:
            raise
        except Exception as exc:
            raise MarketContextUnavailable(
                f"MARKET_CONTEXT_READ_FAILED_{type(exc).__name__.upper()}"
            ) from None

    async def fetch_window(
        self,
        instrument_ref: str,
        interval: Literal["1m", "15m"],
        start_at: datetime,
        end_at: datetime,
    ) -> MarketWindow:
        symbol = _INSTRUMENT_SYMBOLS.get(instrument_ref)
        if symbol is None:
            raise MarketContextUnavailable("MARKET_CONTEXT_INSTRUMENT_UNSUPPORTED")
        if start_at.utcoffset() is None or end_at.utcoffset() is None:
            raise MarketContextUnavailable("MARKET_WINDOW_TIMEZONE_REQUIRED")
        interval_ms = ONE_MINUTE_MS if interval == "1m" else FIFTEEN_MINUTES_MS
        native_interval = (
            BinanceKlineInterval.MINUTE_1
            if interval == "1m"
            else BinanceKlineInterval.MINUTE_15
        )
        start_ms = int(start_at.timestamp() * 1000) // interval_ms * interval_ms
        end_ms = int(end_at.timestamp() * 1000) // interval_ms * interval_ms
        count = (end_ms - start_ms) // interval_ms + 1
        if count <= 0 or count > MAX_MARKET_WINDOW_BARS:
            raise MarketContextUnavailable("MARKET_WINDOW_RANGE_INVALID")
        try:
            bars = await asyncio.wait_for(
                self._market_api.query_klines(
                    symbol=symbol,
                    interval=native_interval,
                    limit=count,
                    start_time=start_ms,
                    end_time=end_ms + interval_ms - 1,
                ),
                timeout=PUBLIC_MARKET_TIMEOUT_SECONDS,
            )
            expected_open_times = [
                start_ms + index * interval_ms for index in range(count)
            ]
            if len(bars) != count or [
                int(bar.open_time) for bar in bars
            ] != expected_open_times:
                raise ValueError("public market window incomplete")
            normalized = tuple(
                MarketBar(
                    open_at=datetime.fromtimestamp(int(bar.open_time) / 1000, tz=UTC),
                    close_at=datetime.fromtimestamp(
                        (int(bar.close_time) + 1) / 1000,
                        tz=UTC,
                    ),
                    open=canonical_decimal(Decimal(str(bar.open))),
                    high=canonical_decimal(Decimal(str(bar.high))),
                    low=canonical_decimal(Decimal(str(bar.low))),
                    close=canonical_decimal(Decimal(str(bar.close))),
                    volume=canonical_decimal(Decimal(str(bar.volume))),
                )
                for bar in bars
            )
            return MarketWindow(
                instrument_ref=instrument_ref,
                interval=interval,
                source=self._source,
                source_cutoff=normalized[-1].close_at,
                bars=normalized,
            )
        except MarketContextUnavailable:
            raise
        except Exception as exc:
            raise MarketContextUnavailable(
                f"MARKET_WINDOW_READ_FAILED_{type(exc).__name__.upper()}"
            ) from None
