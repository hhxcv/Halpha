from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener, urlopen

from halpha.pipeline import PipelineError, RunContext
from halpha.runtime.public_http import market_proxy_url_from_market, urlopen_from_public_proxy
from halpha.data.raw_artifacts import RawArtifactError, validate_market_raw_artifact
from halpha.storage import write_json


STAGE_NAME = "collect_market_data"
MARKET_ARTIFACT = "raw/market.json"
BINANCE_SOURCE_NAME = "binance"
BINANCE_BASE_URL = "https://data-api.binance.vision"
BINANCE_TICKER_PATH = "/api/v3/ticker/24hr"
REQUEST_TIMEOUT_SECONDS = 20


def collect_market_data(config: dict[str, Any], run: RunContext) -> list[str]:
    market = config.get("market", {})
    if not market.get("enabled"):
        run.manifest["counts"]["market_items"] = 0
        return []

    raw = _collect_raw_market(market)
    try:
        validate_market_raw_artifact(raw, MARKET_ARTIFACT)
    except RawArtifactError as exc:
        raise PipelineError(str(exc), stage=STAGE_NAME, exit_code=3) from exc

    artifact_path = run.raw_dir / "market.json"
    write_json(artifact_path, raw)
    run.manifest["artifacts"]["raw_market"] = MARKET_ARTIFACT
    run.manifest["counts"]["market_items"] = len(raw["items"])

    if raw["errors"]:
        raise PipelineError(
            _collector_failure_message(raw["errors"]),
            stage=STAGE_NAME,
            exit_code=3,
            artifacts=[MARKET_ARTIFACT],
        )

    return [MARKET_ARTIFACT]


def _collect_raw_market(market: dict[str, Any]) -> dict[str, Any]:
    source_name = market.get("source")
    collected_at = _utc_timestamp()
    raw = _raw_artifact(source_name, collected_at)

    if source_name != BINANCE_SOURCE_NAME:
        raw["errors"].append(
            {
                "source": source_name,
                "message": f"unsupported market.source: {source_name}",
            }
        )
        return raw

    try:
        urlopen_func = _urlopen_from_market_config(market)
    except MarketCollectionError as exc:
        raw["errors"].append(
            {
                "source": source_name,
                "message": str(exc),
            }
        )
        return raw

    for symbol in market.get("symbols", []):
        try:
            ticker = _request_binance_ticker(symbol, urlopen_func=urlopen_func)
            raw["items"].append(_market_item(ticker, collected_at))
        except MarketCollectionError as exc:
            raw["errors"].append(
                {
                    "symbol": symbol,
                    "source": BINANCE_SOURCE_NAME,
                    "message": str(exc),
                }
            )

    return raw


def _raw_artifact(source_name: Any, collected_at: str) -> dict[str, Any]:
    source_url = BINANCE_BASE_URL if source_name == BINANCE_SOURCE_NAME else None
    return {
        "schema_version": 1,
        "artifact_type": "market_raw",
        "collector": "market",
        "collection_method": "public_http",
        "source": {
            "name": source_name,
            "url": source_url,
        },
        "collected_at": collected_at,
        "items": [],
        "errors": [],
    }


def _request_binance_ticker(symbol: str, *, urlopen_func) -> dict[str, Any]:
    url = _ticker_url(symbol)
    request = Request(url, headers={"User-Agent": "Halpha/0.0.0"})
    try:
        with urlopen_func(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = _read_error_detail(exc)
        raise MarketCollectionError(f"binance request failed for {symbol}: HTTP {exc.code}{detail}") from exc
    except URLError as exc:
        raise MarketCollectionError(f"binance request failed for {symbol}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise MarketCollectionError(f"binance request timed out for {symbol}") from exc

    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise MarketCollectionError(f"binance returned invalid JSON for {symbol}") from exc
    if not isinstance(data, dict):
        raise MarketCollectionError(f"binance returned unexpected payload for {symbol}")
    return data


def _ticker_url(symbol: str) -> str:
    query = urlencode({"symbol": symbol})
    return f"{BINANCE_BASE_URL}{BINANCE_TICKER_PATH}?{query}"


def _urlopen_from_market_config(market: dict[str, Any]):
    return urlopen_from_public_proxy(
        _proxy_url_from_market_config(market),
        error_factory=MarketCollectionError,
        default_urlopen=urlopen,
        proxy_handler_factory=ProxyHandler,
        opener_factory=build_opener,
        missing_url_message="market.proxy.url must be a non-empty string when market.proxy.enabled is true",
        invalid_url_message="market.proxy.url must be an http or https URL",
        credentials_message="market.proxy.url must not include credentials",
    )


def _proxy_url_from_market_config(market: dict[str, Any]) -> str | None:
    return market_proxy_url_from_market(
        market,
        error_factory=MarketCollectionError,
        require_url_when_enabled=True,
        missing_url_message="market.proxy.url must be a non-empty string when market.proxy.enabled is true",
        invalid_url_message="market.proxy.url must be an http or https URL",
        credentials_message="market.proxy.url must not include credentials",
    )


def _market_item(ticker: dict[str, Any], collected_at: str) -> dict[str, Any]:
    symbol = _required_text(ticker, "symbol")
    close_time = ticker.get("closeTime")
    as_of = _timestamp_from_millis(close_time) if isinstance(close_time, int) else collected_at
    source = {"name": BINANCE_SOURCE_NAME, "url": BINANCE_BASE_URL}
    return {
        "id": f"market:{BINANCE_SOURCE_NAME}:{symbol}:{as_of}",
        "symbol": symbol,
        "as_of": as_of,
        "metrics": {
            "price": _required_text(ticker, "lastPrice"),
            "change_24h_pct": _required_text(ticker, "priceChangePercent"),
            "volume_24h": _required_text(ticker, "volume"),
            "quote_volume_24h": _required_text(ticker, "quoteVolume"),
        },
        "source": source,
    }


def _required_text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise MarketCollectionError(f"binance response missing {key}")
    return value


def _timestamp_from_millis(value: int) -> str:
    return _utc_timestamp(datetime.fromtimestamp(value / 1000, timezone.utc))


def _utc_timestamp(value: datetime | None = None) -> str:
    timestamp = value or datetime.now(timezone.utc)
    timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)
    return timestamp.isoformat().replace("+00:00", "Z")


def _collector_failure_message(errors: list[dict[str, Any]]) -> str:
    summaries = [
        f"{error.get('symbol') or error.get('source')}: {error.get('message')}"
        for error in errors
    ]
    return f"market collection failed for {len(errors)} source item(s): {'; '.join(summaries)}"


def _read_error_detail(error: HTTPError) -> str:
    try:
        body = error.read().decode("utf-8").strip()
    except Exception:
        body = ""
    if not body:
        return ""
    excerpt = body[:200].replace("\n", " ")
    return f": {excerpt}"


class MarketCollectionError(Exception):
    pass
