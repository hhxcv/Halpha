from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import ccxt
import pytest

from halpha.market.ohlcv_source import CCXTOHLCVSource, OHLCVSourceError, _fetch_configured_ohlcv


def test_internal_fetch_configured_ohlcv_returns_normalized_finalized_records() -> None:
    exchange = _FakeExchange(
        {
            ("BTCUSDT", "1d"): [
                _row("2026-06-01T00:00:00Z", 100),
                _row("2026-06-02T00:00:00Z", 101),
                _row("2026-06-03T00:00:00Z", 102),
            ],
            ("BTCUSDT", "1h"): [
                _row("2026-06-03T09:00:00Z", 110),
                _row("2026-06-03T10:00:00Z", 111),
            ],
        }
    )
    captured_options: dict[str, Any] = {}

    def factory(options: dict[str, Any]) -> _FakeExchange:
        captured_options.update(options)
        return exchange

    records = _fetch_configured_ohlcv(
        {
            "source": "binance",
            "symbols": ["BTCUSDT"],
            "ohlcv": {
                "timeframes": ["1d", "1h"],
                "lookback": {"1d": 3, "1h": 2},
            },
        },
        now="2026-06-03T10:30:00Z",
        exchange_factory=factory,
    )

    assert captured_options == {
        "enableRateLimit": True,
        "options": {"fetchMarkets": {"types": ["spot"]}},
        "urls": {"api": {"public": "https://data-api.binance.vision/api/v3"}},
    }
    assert not {"apiKey", "secret", "password", "uid"} & set(captured_options)
    assert exchange.calls == [
        {"symbol": "BTCUSDT", "timeframe": "1d", "since": None, "limit": 3},
        {"symbol": "BTCUSDT", "timeframe": "1h", "since": None, "limit": 2},
    ]
    assert records == [
        {
            "source": "binance",
            "symbol": "BTCUSDT",
            "timeframe": "1d",
            "open_time": "2026-06-01T00:00:00Z",
            "open": 99.0,
            "high": 101.0,
            "low": 98.0,
            "close": 100.0,
            "volume": 10.0,
            "fetched_at": "2026-06-03T10:30:00Z",
        },
        {
            "source": "binance",
            "symbol": "BTCUSDT",
            "timeframe": "1d",
            "open_time": "2026-06-02T00:00:00Z",
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 101.0,
            "volume": 10.0,
            "fetched_at": "2026-06-03T10:30:00Z",
        },
        {
            "source": "binance",
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "open_time": "2026-06-03T09:00:00Z",
            "open": 109.0,
            "high": 111.0,
            "low": 108.0,
            "close": 110.0,
            "volume": 10.0,
            "fetched_at": "2026-06-03T10:30:00Z",
        },
    ]


def test_internal_fetch_configured_ohlcv_uses_configured_proxy_without_credentials() -> None:
    captured_options: dict[str, Any] = {}

    def factory(options: dict[str, Any]) -> _FakeExchange:
        captured_options.update(options)
        return _FakeExchange({("BTCUSDT", "1d"): [_row("2026-06-01T00:00:00Z", 100)]})

    _fetch_configured_ohlcv(
        {
            "source": "binance",
            "symbols": ["BTCUSDT"],
            "proxy": {
                "enabled": True,
                "url": "http://proxy.example:8080",
            },
            "ohlcv": {
                "timeframes": ["1d"],
                "lookback": {"1d": 1},
            },
        },
        now="2026-06-03T00:00:00Z",
        exchange_factory=factory,
    )

    assert captured_options == {
        "enableRateLimit": True,
        "options": {"fetchMarkets": {"types": ["spot"]}},
        "urls": {"api": {"public": "https://data-api.binance.vision/api/v3"}},
        "httpsProxy": "http://proxy.example:8080",
    }
    assert not {"apiKey", "secret", "password", "uid"} & set(captured_options)


def test_ccxt_ohlcv_source_rejects_proxy_credentials() -> None:
    with pytest.raises(OHLCVSourceError, match="market.proxy.url must not include credentials"):
        CCXTOHLCVSource(
            "binance",
            proxy_url="http://user:password@proxy.example:8080",
            exchange_factory=lambda options: _FakeExchange({}),
        )


def test_ccxt_ohlcv_source_passes_since_as_milliseconds() -> None:
    exchange = _FakeExchange({("BTCUSDT", "1d"): [_row("2026-06-01T00:00:00Z", 100)]})
    source = CCXTOHLCVSource("binance", exchange_factory=lambda options: exchange)

    source.fetch_records(
        symbol="BTCUSDT",
        timeframe="1d",
        since=datetime(2026, 5, 1, tzinfo=timezone.utc),
        limit=50,
        now="2026-06-03T00:00:00Z",
    )

    assert exchange.calls == [
        {
            "symbol": "BTCUSDT",
            "timeframe": "1d",
            "since": 1777593600000,
            "limit": 50,
        }
    ]


def test_ccxt_ohlcv_source_rejects_unsupported_source() -> None:
    with pytest.raises(OHLCVSourceError, match="unsupported OHLCV source: kraken"):
        CCXTOHLCVSource("kraken", exchange_factory=lambda options: _FakeExchange({}))


def test_ccxt_ohlcv_source_rejects_unsupported_timeframe() -> None:
    source = CCXTOHLCVSource(
        "binance",
        exchange_factory=lambda options: _FakeExchange({}, timeframes={"1d": "1d"}),
    )

    with pytest.raises(OHLCVSourceError, match="unsupported timeframe 1h for binance"):
        source.fetch_records(symbol="BTCUSDT", timeframe="1h", now="2026-06-03T00:00:00Z")


def test_ccxt_ohlcv_source_reports_unsupported_symbol() -> None:
    source = CCXTOHLCVSource(
        "binance",
        exchange_factory=lambda options: _FailingExchange(ccxt.BadSymbol("bad symbol")),
    )

    with pytest.raises(OHLCVSourceError, match="unsupported symbol BADUSDT for binance"):
        source.fetch_records(symbol="BADUSDT", timeframe="1d", now="2026-06-03T00:00:00Z")


def test_ccxt_ohlcv_source_reports_network_failure() -> None:
    source = CCXTOHLCVSource(
        "binance",
        exchange_factory=lambda options: _FailingExchange(ccxt.NetworkError("timeout")),
    )

    with pytest.raises(OHLCVSourceError, match="ohlcv network failure for binance BTCUSDT 1d"):
        source.fetch_records(symbol="BTCUSDT", timeframe="1d", now="2026-06-03T00:00:00Z")


def test_ccxt_ohlcv_source_reports_exchange_source_error() -> None:
    source = CCXTOHLCVSource(
        "binance",
        exchange_factory=lambda options: _FailingExchange(ccxt.ExchangeError("source rejected request")),
    )

    with pytest.raises(OHLCVSourceError, match="ohlcv source error for binance BTCUSDT 1d"):
        source.fetch_records(symbol="BTCUSDT", timeframe="1d", now="2026-06-03T00:00:00Z")


def test_ccxt_ohlcv_source_rejects_malformed_rows() -> None:
    source = CCXTOHLCVSource(
        "binance",
        exchange_factory=lambda options: _FakeExchange({("BTCUSDT", "1d"): [[1, 2]]}),
    )

    with pytest.raises(OHLCVSourceError, match="timestamp, open, high, low, close, volume"):
        source.fetch_records(symbol="BTCUSDT", timeframe="1d", now="2026-06-03T00:00:00Z")


def _row(open_time: str, close: float) -> list[float | int]:
    timestamp = int(datetime.fromisoformat(open_time.replace("Z", "+00:00")).timestamp() * 1000)
    return [timestamp, close - 1, close + 1, close - 2, close, 10]


class _FakeExchange:
    def __init__(
        self,
        rows: dict[tuple[str, str], list[list[float | int]]],
        *,
        timeframes: dict[str, str] | None = None,
    ) -> None:
        self.rows = rows
        self.calls: list[dict[str, Any]] = []
        self.has = {"fetchOHLCV": True}
        self.timeframes = timeframes or {"1d": "1d", "1h": "1h"}

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: int | None = None,
        limit: int | None = None,
    ) -> list[list[float | int]]:
        self.calls.append(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "since": since,
                "limit": limit,
            }
        )
        return self.rows[(symbol, timeframe)]


class _FailingExchange(_FakeExchange):
    def __init__(self, error: Exception) -> None:
        super().__init__({})
        self.error = error

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: int | None = None,
        limit: int | None = None,
    ) -> list[list[float | int]]:
        raise self.error
