"""Read-only public market stream projected through the local workbench."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal, Protocol, TypeAlias

import msgspec
from nautilus_trader.adapters.binance.common.enums import (
    BinanceAccountType,
    BinanceEnvironment,
)
from nautilus_trader.adapters.binance.common.schemas.market import (
    BinanceCandlestickMsg,
    BinanceDataMsgWrapper,
    BinanceQuoteMsg,
)
from nautilus_trader.adapters.binance.common.urls import (
    get_ws_base_url,
    get_ws_public_base_url,
)
from nautilus_trader.adapters.binance.websocket.client import BinanceWebSocketClient
from nautilus_trader.common.component import LiveClock
from pydantic import BaseModel, ConfigDict

from halpha.domain_values import canonical_decimal
from halpha.public_market import (
    MARKET_INTERVALS,
    MarketBar,
    MarketContextUnavailable,
    MarketInterval,
    binance_public_market_identity,
)


_INSTRUMENT_SYMBOLS = {"BTCUSDT-PERP": "BTCUSDT"}
_QUEUE_CAPACITY = 256


class MarketStreamStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["status"] = "status"
    state: Literal["CONNECTING", "LIVE", "RECONNECTING", "FAILED"]
    source: str
    observed_at: datetime
    reason: str | None = None


class MarketStreamQuote(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["quote"] = "quote"
    instrument_ref: str
    source: str
    source_cutoff: datetime
    received_at: datetime
    bid_price: str
    ask_price: str
    reference_price: str


class MarketStreamBar(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["bar"] = "bar"
    instrument_ref: str
    interval: MarketInterval
    source: str
    source_cutoff: datetime
    received_at: datetime
    closed: bool
    bar: MarketBar


MarketStreamEvent: TypeAlias = MarketStreamStatus | MarketStreamQuote | MarketStreamBar


class PublicMarketStreamProvider(Protocol):
    def stream(self, instrument_ref: str) -> AsyncIterator[MarketStreamEvent]: ...

    async def close(self) -> None: ...


class BinanceWebSocketPort(Protocol):
    async def subscribe_book_ticker(self, symbol: str | None = None) -> None: ...

    async def subscribe_bars(self, symbol: str, interval: str) -> None: ...

    async def disconnect(self) -> None: ...


StreamRoute: TypeAlias = Literal["market", "public"]
WebSocketClientFactory: TypeAlias = Callable[
    [
        StreamRoute,
        BinanceEnvironment,
        Callable[[bytes], None],
        Callable[[], Awaitable[None]],
    ],
    BinanceWebSocketPort,
]


class BinancePublicMarketStream:
    """Relay isolated Nautilus-managed public streams through one local UI feed."""

    def __init__(
        self,
        profile: str,
        *,
        proxy_url: str | None = None,
        client_factory: WebSocketClientFactory | None = None,
    ) -> None:
        environment, source = binance_public_market_identity(profile)
        self._route_environments: dict[StreamRoute, BinanceEnvironment] = {
            "public": environment,
            "market": environment,
        }
        self._route_sources: dict[StreamRoute, str] = {
            "public": source,
            "market": source,
        }
        self._status_source = "+".join(dict.fromkeys(self._route_sources.values()))
        self._proxy_url = proxy_url
        self._client_factory = client_factory
        self._clients: dict[StreamRoute, BinanceWebSocketPort] = {}
        self._route_live: dict[StreamRoute, bool] = {
            "market": False,
            "public": False,
        }
        self._subscribers: set[asyncio.Queue[MarketStreamEvent]] = set()
        self._start_lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._closed = False
        self._status = MarketStreamStatus(
            state="CONNECTING",
            source=self._status_source,
            observed_at=datetime.now(UTC),
            reason=None,
        )
        self._wrapper_decoder = msgspec.json.Decoder(BinanceDataMsgWrapper)
        self._quote_decoder = msgspec.json.Decoder(BinanceQuoteMsg)
        self._candlestick_decoder = msgspec.json.Decoder(BinanceCandlestickMsg)

    async def stream(
        self,
        instrument_ref: str,
    ) -> AsyncIterator[MarketStreamEvent]:
        if instrument_ref not in _INSTRUMENT_SYMBOLS:
            raise MarketContextUnavailable("MARKET_CONTEXT_INSTRUMENT_UNSUPPORTED")
        queue: asyncio.Queue[MarketStreamEvent] = asyncio.Queue(
            maxsize=_QUEUE_CAPACITY,
        )
        self._subscribers.add(queue)
        try:
            await self._ensure_started()
            if queue.empty():
                self._put(queue, self._status)
            while True:
                yield await queue.get()
        finally:
            self._subscribers.discard(queue)

    async def close(self) -> None:
        self._closed = True
        clients = tuple(self._clients.values())
        self._clients.clear()
        self._route_live = {"market": False, "public": False}
        if clients:
            await asyncio.gather(
                *(client.disconnect() for client in clients),
                return_exceptions=True,
            )

    async def _ensure_started(self) -> None:
        if self._closed:
            raise MarketContextUnavailable("MARKET_STREAM_CLOSED")
        if self._clients:
            return
        async with self._start_lock:
            if self._clients:
                return
            self._loop = asyncio.get_running_loop()
            self._set_status("CONNECTING")
            clients: dict[StreamRoute, BinanceWebSocketPort] = {}
            try:
                clients["public"] = self._make_client("public")
                clients["market"] = self._make_client("market")
                self._clients = clients
                await clients["public"].subscribe_book_ticker("BTCUSDT")
                self._route_live["public"] = True
                for interval in MARKET_INTERVALS:
                    await clients["market"].subscribe_bars("BTCUSDT", interval)
                self._route_live["market"] = True
                self._set_status("LIVE")
            except Exception as exc:
                self._set_status(
                    "FAILED",
                    f"MARKET_STREAM_CONNECT_FAILED_{type(exc).__name__.upper()}",
                )
                self._clients.clear()
                await asyncio.gather(
                    *(client.disconnect() for client in clients.values()),
                    return_exceptions=True,
                )
                raise MarketContextUnavailable(
                    f"MARKET_STREAM_CONNECT_FAILED_{type(exc).__name__.upper()}"
                ) from None

    def _make_client(self, route: StreamRoute) -> BinanceWebSocketPort:
        async def reconnected() -> None:
            self._route_live[route] = False
            self._set_status("RECONNECTING", f"{route.upper()}_STREAM_RECONNECTED")

        def handler(raw: bytes) -> None:
            self._handle_message(route, raw)

        if self._client_factory is not None:
            return self._client_factory(
                route,
                self._route_environments[route],
                handler,
                reconnected,
            )
        environment = self._route_environments[route]
        base_url = (
            get_ws_public_base_url(
                BinanceAccountType.USDT_FUTURES,
                environment,
                False,
            )
            if route == "public"
            else get_ws_base_url(
                BinanceAccountType.USDT_FUTURES,
                environment,
                False,
            )
        )
        return BinanceWebSocketClient(
            clock=LiveClock(),
            base_url=base_url,
            handler=handler,
            handler_reconnect=reconnected,
            loop=asyncio.get_running_loop(),
            proxy_url=self._proxy_url,
        )

    def _handle_message(self, route: StreamRoute, raw: bytes) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop is loop:
            self._decode_and_publish(route, raw)
        else:
            loop.call_soon_threadsafe(self._decode_and_publish, route, raw)

    def _decode_and_publish(self, route: StreamRoute, raw: bytes) -> None:
        try:
            wrapper = self._wrapper_decoder.decode(raw)
            stream = wrapper.stream
            if stream is None:
                return
            if route == "public" and "@bookTicker" in stream:
                event = self._quote_event(self._quote_decoder.decode(raw))
            elif route == "market" and "@kline_" in stream:
                event = self._bar_event(self._candlestick_decoder.decode(raw))
            else:
                return
        except (InvalidOperation, TypeError, ValueError, msgspec.DecodeError):
            return
        self._route_live[route] = True
        if all(self._route_live.values()) and self._status.state != "LIVE":
            self._set_status("LIVE")
        self._publish(event)

    def _quote_event(self, message: BinanceQuoteMsg) -> MarketStreamQuote:
        data = message.data
        if data.s != "BTCUSDT" or data.T is None or data.T <= 0:
            raise ValueError("MARKET_STREAM_QUOTE_INVALID")
        bid = Decimal(data.b)
        ask = Decimal(data.a)
        if bid <= 0 or ask <= 0 or ask < bid:
            raise ValueError("MARKET_STREAM_QUOTE_INVALID")
        return MarketStreamQuote(
            instrument_ref="BTCUSDT-PERP",
            source=self._route_sources["public"],
            source_cutoff=datetime.fromtimestamp(data.T / 1000, tz=UTC),
            received_at=datetime.now(UTC),
            bid_price=canonical_decimal(bid),
            ask_price=canonical_decimal(ask),
            reference_price=canonical_decimal((bid + ask) / Decimal(2)),
        )

    def _bar_event(self, message: BinanceCandlestickMsg) -> MarketStreamBar:
        data = message.data
        candle = data.k
        interval = candle.i.value
        if (
            data.s != "BTCUSDT"
            or candle.s != "BTCUSDT"
            or interval not in MARKET_INTERVALS
            or data.E <= 0
            or candle.t <= 0
            or candle.T < candle.t
        ):
            raise ValueError("MARKET_STREAM_BAR_INVALID")
        open_price = Decimal(candle.o)
        high = Decimal(candle.h)
        low = Decimal(candle.l)
        close = Decimal(candle.c)
        volume = Decimal(candle.v)
        if (
            min(open_price, high, low, close) <= 0
            or volume < 0
            or high < max(open_price, close)
            or low > min(open_price, close)
            or high < low
        ):
            raise ValueError("MARKET_STREAM_BAR_INVALID")
        return MarketStreamBar(
            instrument_ref="BTCUSDT-PERP",
            interval=interval,
            source=self._route_sources["market"],
            source_cutoff=datetime.fromtimestamp(data.E / 1000, tz=UTC),
            received_at=datetime.now(UTC),
            closed=candle.x,
            bar=MarketBar(
                open_at=datetime.fromtimestamp(candle.t / 1000, tz=UTC),
                close_at=datetime.fromtimestamp((candle.T + 1) / 1000, tz=UTC),
                open=canonical_decimal(open_price),
                high=canonical_decimal(high),
                low=canonical_decimal(low),
                close=canonical_decimal(close),
                volume=canonical_decimal(volume),
            ),
        )

    def _set_status(
        self,
        state: Literal["CONNECTING", "LIVE", "RECONNECTING", "FAILED"],
        reason: str | None = None,
    ) -> None:
        self._status = MarketStreamStatus(
            state=state,
            source=self._status_source,
            observed_at=datetime.now(UTC),
            reason=reason,
        )
        self._publish(self._status)

    def _publish(self, event: MarketStreamEvent) -> None:
        for queue in tuple(self._subscribers):
            self._put(queue, event)

    @staticmethod
    def _put(
        queue: asyncio.Queue[MarketStreamEvent],
        event: MarketStreamEvent,
    ) -> None:
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        queue.put_nowait(event)
