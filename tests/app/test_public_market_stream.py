from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable

import pytest
from nautilus_trader.adapters.binance.common.enums import BinanceEnvironment

from halpha.public_market_stream import (
    BinancePublicMarketStream,
    MarketStreamBar,
    MarketStreamEvent,
    MarketStreamQuote,
    MarketStreamStatus,
)


class FakeWebSocketClient:
    def __init__(
        self,
        handler: Callable[[bytes], None],
        reconnect: Callable[[], Awaitable[None]],
    ) -> None:
        self.handler = handler
        self.reconnect = reconnect
        self.book_tickers: list[str | None] = []
        self.bars: list[tuple[str, str]] = []
        self.disconnected = False

    async def subscribe_book_ticker(self, symbol: str | None = None) -> None:
        self.book_tickers.append(symbol)

    async def subscribe_bars(self, symbol: str, interval: str) -> None:
        self.bars.append((symbol, interval))

    async def disconnect(self) -> None:
        self.disconnected = True

    def emit(self, payload: dict[str, object]) -> None:
        self.handler(json.dumps(payload, separators=(",", ":")).encode())


async def _next_kind(
    stream,
    kind: type[MarketStreamEvent],
) -> MarketStreamEvent:
    for _ in range(12):
        event = await asyncio.wait_for(anext(stream), timeout=1)
        if isinstance(event, kind):
            return event
    raise AssertionError(f"stream did not emit {kind.__name__}")


async def _next_live_status(stream) -> MarketStreamStatus:
    for _ in range(6):
        event = await asyncio.wait_for(anext(stream), timeout=1)
        if isinstance(event, MarketStreamStatus) and event.state == "LIVE":
            return event
    raise AssertionError("stream did not become live")


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
def test_public_market_stream_routes_every_feed_to_the_profile_environment(
    profile: str,
    expected_environment: BinanceEnvironment,
    expected_source: str,
) -> None:
    async def scenario() -> None:
        clients: dict[str, FakeWebSocketClient] = {}
        environments: dict[str, BinanceEnvironment] = {}

        def factory(route, environment, handler, reconnect):
            client = FakeWebSocketClient(handler, reconnect)
            clients[route] = client
            environments[route] = environment
            return client

        provider = BinancePublicMarketStream(
            profile,
            client_factory=factory,
        )
        stream = provider.stream("BTCUSDT-PERP")
        status = await _next_live_status(stream)
        assert status.source == expected_source
        assert environments == {
            "public": expected_environment,
            "market": expected_environment,
        }
        assert clients["public"].book_tickers == ["BTCUSDT"]
        assert clients["market"].bars == [
            ("BTCUSDT", "1m"),
            ("BTCUSDT", "5m"),
            ("BTCUSDT", "15m"),
            ("BTCUSDT", "1h"),
            ("BTCUSDT", "4h"),
            ("BTCUSDT", "1d"),
        ]

        clients["public"].emit(
            {
                "stream": "btcusdt@bookTicker",
                "data": {
                    "s": "BTCUSDT",
                    "u": 42,
                    "b": "101.1",
                    "B": "2",
                    "a": "101.3",
                    "A": "3",
                    "T": 1_800_000_100_000,
                },
            }
        )
        quote = await _next_kind(stream, MarketStreamQuote)
        assert isinstance(quote, MarketStreamQuote)
        assert quote.bid_price == "101.1"
        assert quote.ask_price == "101.3"
        assert quote.reference_price == "101.2"
        assert quote.source == expected_source
        assert quote.source_cutoff.isoformat() == "2027-01-15T08:01:40+00:00"

        clients["market"].emit(
            {
                "stream": "btcusdt@kline_5m",
                "data": {
                    "e": "kline",
                    "E": 1_800_000_100_250,
                    "s": "BTCUSDT",
                    "k": {
                        "t": 1_800_000_000_000,
                        "T": 1_800_000_299_999,
                        "s": "BTCUSDT",
                        "i": "5m",
                        "f": 1,
                        "L": 2,
                        "o": "101",
                        "c": "102",
                        "h": "103",
                        "l": "100",
                        "v": "12.5",
                        "n": 2,
                        "x": False,
                        "q": "1000",
                        "V": "6",
                        "Q": "500",
                        "B": "0",
                    },
                },
            }
        )
        bar = await _next_kind(stream, MarketStreamBar)
        assert isinstance(bar, MarketStreamBar)
        assert bar.interval == "5m"
        assert bar.closed is False
        assert bar.bar.open == "101"
        assert bar.bar.close == "102"
        assert bar.bar.volume == "12.5"
        assert bar.source == expected_source

        await clients["market"].reconnect()
        reconnecting = await _next_kind(stream, MarketStreamStatus)
        assert isinstance(reconnecting, MarketStreamStatus)
        assert reconnecting.state == "RECONNECTING"
        assert reconnecting.reason == "MARKET_STREAM_RECONNECTED"

        await stream.aclose()
        await provider.close()
        assert all(client.disconnected for client in clients.values())

    asyncio.run(scenario())


def test_public_market_stream_ignores_malformed_or_wrong_symbol_payloads() -> None:
    async def scenario() -> None:
        clients: dict[str, FakeWebSocketClient] = {}

        def factory(route, _environment, handler, reconnect):
            client = FakeWebSocketClient(handler, reconnect)
            clients[route] = client
            return client

        provider = BinancePublicMarketStream(
            "BINANCE_LIVE_READ_ONLY",
            client_factory=factory,
        )
        stream = provider.stream("BTCUSDT-PERP")
        await _next_live_status(stream)
        clients["public"].emit(
            {
                "stream": "ethusdt@bookTicker",
                "data": {
                    "s": "ETHUSDT",
                    "u": 1,
                    "b": "10",
                    "B": "1",
                    "a": "11",
                    "A": "1",
                    "T": 1_800_000_100_000,
                },
            }
        )
        clients["public"].handler(b"not-json")
        await asyncio.sleep(0)

        pending = asyncio.create_task(anext(stream))
        await asyncio.sleep(0.02)
        assert not pending.done()
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        await stream.aclose()
        await provider.close()

    asyncio.run(scenario())
