from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any
from urllib.parse import urlparse

import ccxt


SUPPORTED_OHLCV_SOURCES = {"binance"}
BINANCE_SPOT_PUBLIC_API_URL = "https://data-api.binance.vision/api/v3"
TIMEFRAME_DURATIONS = {
    "1d": timedelta(days=1),
    "1h": timedelta(hours=1),
}


class OHLCVSourceError(Exception):
    """Raised when public OHLCV collection cannot produce valid finalized candles."""


class CCXTOHLCVSource:
    def __init__(
        self,
        source: str,
        *,
        proxy_url: str | None = None,
        exchange_factory: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        self.source = _require_supported_source(source)
        proxy_url = _normalize_proxy_url(proxy_url)
        factory = exchange_factory or _ccxt_exchange_factory(self.source)
        self.exchange = factory(_exchange_options(self.source, proxy_url=proxy_url))
        self._require_ohlcv_support()

    def fetch_records(
        self,
        *,
        symbol: str,
        timeframe: str,
        since: datetime | str | None = None,
        limit: int | None = None,
        now: datetime | str | None = None,
    ) -> list[dict[str, Any]]:
        _require_non_empty_text(symbol, "symbol")
        self._require_timeframe(timeframe)
        fetched_at = _coerce_utc(now)
        since_ms = _millis_from_utc(since) if since is not None else None

        try:
            rows = self.exchange.fetch_ohlcv(symbol, timeframe, since=since_ms, limit=limit)
        except ccxt.BadSymbol as exc:
            raise OHLCVSourceError(f"unsupported symbol {symbol} for {self.source}: {exc}") from exc
        except ccxt.NetworkError as exc:
            raise OHLCVSourceError(
                f"ohlcv network failure for {self.source} {symbol} {timeframe}: {exc}"
            ) from exc
        except ccxt.ExchangeError as exc:
            raise OHLCVSourceError(
                f"ohlcv source error for {self.source} {symbol} {timeframe}: {exc}"
            ) from exc

        if not isinstance(rows, list):
            raise OHLCVSourceError(
                f"{self.source} {symbol} {timeframe} returned non-list OHLCV data."
            )

        records = []
        for index, row in enumerate(rows):
            record = _normalize_row(
                row,
                source=self.source,
                symbol=symbol,
                timeframe=timeframe,
                fetched_at=fetched_at,
                row_path=f"{self.source} {symbol} {timeframe} row[{index}]",
            )
            if _is_finalized(record["open_time"], timeframe, fetched_at):
                records.append(record)

        return _sort_records(records)

    def _require_ohlcv_support(self) -> None:
        if not getattr(self.exchange, "has", {}).get("fetchOHLCV"):
            raise OHLCVSourceError(f"{self.source} does not support public OHLCV fetching.")
        if not callable(getattr(self.exchange, "fetch_ohlcv", None)):
            raise OHLCVSourceError(f"{self.source} does not expose fetch_ohlcv.")

    def _require_timeframe(self, timeframe: str) -> None:
        _require_non_empty_text(timeframe, "timeframe")
        if timeframe not in TIMEFRAME_DURATIONS:
            supported = ", ".join(sorted(TIMEFRAME_DURATIONS))
            raise OHLCVSourceError(
                f"unsupported timeframe {timeframe}. Supported timeframes: {supported}."
            )
        exchange_timeframes = getattr(self.exchange, "timeframes", {}) or {}
        if timeframe not in exchange_timeframes:
            supported = ", ".join(sorted(exchange_timeframes)) or "none"
            raise OHLCVSourceError(
                f"unsupported timeframe {timeframe} for {self.source}. Exchange timeframes: {supported}."
            )


def fetch_configured_ohlcv(
    market: dict[str, Any],
    *,
    now: datetime | str | None = None,
    exchange_factory: Callable[[dict[str, Any]], Any] | None = None,
) -> list[dict[str, Any]]:
    source = CCXTOHLCVSource(
        _required_mapping_text(market, "source", "market.source"),
        proxy_url=_proxy_url_from_market_config(market),
        exchange_factory=exchange_factory,
    )
    symbols = _required_string_list(market, "symbols", "market.symbols")
    ohlcv = _required_mapping(market, "ohlcv", "market.ohlcv")
    timeframes = _required_string_list(ohlcv, "timeframes", "market.ohlcv.timeframes")
    lookback = _required_mapping(ohlcv, "lookback", "market.ohlcv.lookback")

    records = []
    for symbol in symbols:
        for timeframe in timeframes:
            limit = _required_positive_int(
                lookback,
                timeframe,
                f"market.ohlcv.lookback.{timeframe}",
            )
            records.extend(
                source.fetch_records(symbol=symbol, timeframe=timeframe, limit=limit, now=now)
            )

    return _sort_records(records)


def _require_supported_source(source: str) -> str:
    _require_non_empty_text(source, "source")
    if source not in SUPPORTED_OHLCV_SOURCES:
        supported = ", ".join(sorted(SUPPORTED_OHLCV_SOURCES))
        raise OHLCVSourceError(f"unsupported OHLCV source: {source}. Supported sources: {supported}.")
    return source


def _ccxt_exchange_factory(source: str) -> Callable[[dict[str, Any]], Any]:
    exchange_class = getattr(ccxt, source, None)
    if exchange_class is None:
        raise OHLCVSourceError(f"ccxt exchange is not available for source: {source}.")
    return exchange_class


def _exchange_options(source: str, *, proxy_url: str | None) -> dict[str, Any]:
    options: dict[str, Any] = {"enableRateLimit": True}
    if source == "binance":
        options["options"] = {"fetchMarkets": {"types": ["spot"]}}
        options["urls"] = {"api": {"public": BINANCE_SPOT_PUBLIC_API_URL}}
        if proxy_url is not None:
            options["httpsProxy"] = proxy_url
    return options


def _proxy_url_from_market_config(market: dict[str, Any]) -> str | None:
    proxy = market.get("proxy")
    if proxy is None:
        return None
    if not isinstance(proxy, dict):
        raise OHLCVSourceError("market.proxy must be a mapping.")
    enabled = proxy.get("enabled")
    if not isinstance(enabled, bool):
        raise OHLCVSourceError("market.proxy.enabled must be a boolean.")
    if not enabled:
        return None
    url = proxy.get("url")
    if not isinstance(url, str) or not url.strip():
        raise OHLCVSourceError(
            "market.proxy.url must be a non-empty string when market.proxy.enabled is true."
        )
    return _normalize_proxy_url(url)


def _normalize_proxy_url(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise OHLCVSourceError("market.proxy.url must be a non-empty string.")
    proxy_url = value.strip()
    parsed = urlparse(proxy_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise OHLCVSourceError("market.proxy.url must be an http or https URL.")
    if parsed.username or parsed.password:
        raise OHLCVSourceError("market.proxy.url must not include credentials.")
    return proxy_url


def _normalize_row(
    row: Any,
    *,
    source: str,
    symbol: str,
    timeframe: str,
    fetched_at: datetime,
    row_path: str,
) -> dict[str, Any]:
    if not isinstance(row, list) or len(row) < 6:
        raise OHLCVSourceError(
            f"{row_path} must contain timestamp, open, high, low, close, volume."
        )

    return {
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "open_time": _timestamp_from_millis(_require_int(row[0], f"{row_path}.timestamp")),
        "open": _require_number(row[1], f"{row_path}.open"),
        "high": _require_number(row[2], f"{row_path}.high"),
        "low": _require_number(row[3], f"{row_path}.low"),
        "close": _require_number(row[4], f"{row_path}.close"),
        "volume": _require_number(row[5], f"{row_path}.volume"),
        "fetched_at": _format_utc(fetched_at),
    }


def _sort_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        records,
        key=lambda record: (
            record["source"],
            record["symbol"],
            record["timeframe"],
            record["open_time"],
        ),
    )


def _is_finalized(open_time: str, timeframe: str, now: datetime) -> bool:
    opened_at = _coerce_utc(open_time)
    return opened_at + TIMEFRAME_DURATIONS[timeframe] <= now


def _coerce_utc(value: datetime | str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc).replace(microsecond=0)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise OHLCVSourceError("timestamp must include a UTC offset.")
        return value.astimezone(timezone.utc).replace(microsecond=0)
    if not isinstance(value, str) or not value.strip():
        raise OHLCVSourceError("timestamp must be an ISO 8601 UTC string.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OHLCVSourceError("timestamp must be an ISO 8601 UTC string.") from exc
    if parsed.tzinfo is None:
        raise OHLCVSourceError("timestamp must include a UTC offset.")
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _timestamp_from_millis(value: int) -> str:
    return _format_utc(datetime.fromtimestamp(value / 1000, timezone.utc))


def _millis_from_utc(value: datetime | str) -> int:
    return int(_coerce_utc(value).timestamp() * 1000)


def _require_int(value: Any, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise OHLCVSourceError(f"{path} must be an integer millisecond timestamp.")
    return value


def _require_number(value: Any, path: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise OHLCVSourceError(f"{path} must be a number.")
    number = float(value)
    if not isfinite(number):
        raise OHLCVSourceError(f"{path} must be a finite number.")
    return number


def _required_mapping(data: dict[str, Any], key: str, path: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise OHLCVSourceError(f"{path} must be a mapping.")
    return value


def _required_mapping_text(data: dict[str, Any], key: str, path: str) -> str:
    value = data.get(key)
    _require_non_empty_text(value, path)
    return value


def _required_string_list(data: dict[str, Any], key: str, path: str) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list) or not value:
        raise OHLCVSourceError(f"{path} must be a non-empty list.")
    for index, item in enumerate(value):
        _require_non_empty_text(item, f"{path}[{index}]")
    return value


def _required_positive_int(data: dict[str, Any], key: str, path: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise OHLCVSourceError(f"{path} must be a positive integer.")
    return value


def _require_non_empty_text(value: Any, path: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise OHLCVSourceError(f"{path} must be a non-empty string.")
