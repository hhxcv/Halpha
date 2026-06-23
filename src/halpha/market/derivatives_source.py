from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener, urlopen

from halpha.data.public_capabilities import SUPPORTED_DERIVATIVES_MARKET_SOURCES
from halpha.runtime.public_http import urlopen_from_public_proxy

BINANCE_USDM_BASE_URL = "https://fapi.binance.com"
MARKET_TYPE = "usd_m_futures"
REQUEST_TIMEOUT_SECONDS = 20


class DerivativesSourceError(Exception):
    """Raised when a derivatives source request is unsupported or malformed."""


class _EndpointFetchError(Exception):
    def __init__(
        self,
        message: str,
        *,
        error_type: str,
        status_code: int | None = None,
        raw_error_code: int | str | None = None,
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.status_code = status_code
        self.raw_error_code = raw_error_code


@dataclass(frozen=True)
class _RequestSpec:
    request_class: str
    data_class: str
    endpoint: str
    path: str
    symbol_param: str
    response_shape: str
    period_required: bool = False
    limit_allowed: bool = False
    fixed_params: tuple[tuple[str, str], ...] = ()
    default_period: str = "snapshot"


_REQUEST_SPECS: dict[str, _RequestSpec] = {
    "funding_rate_history": _RequestSpec(
        request_class="funding_rate_history",
        data_class="funding_rate",
        endpoint="funding_rate_history",
        path="/fapi/v1/fundingRate",
        symbol_param="symbol",
        response_shape="list",
        limit_allowed=True,
        default_period="8h",
    ),
    "open_interest_current": _RequestSpec(
        request_class="open_interest_current",
        data_class="open_interest",
        endpoint="open_interest_current",
        path="/fapi/v1/openInterest",
        symbol_param="symbol",
        response_shape="dict",
    ),
    "open_interest_history": _RequestSpec(
        request_class="open_interest_history",
        data_class="open_interest",
        endpoint="open_interest_history",
        path="/futures/data/openInterestHist",
        symbol_param="symbol",
        response_shape="list",
        period_required=True,
        limit_allowed=True,
    ),
    "premium_index": _RequestSpec(
        request_class="premium_index",
        data_class="premium_index",
        endpoint="premium_index",
        path="/fapi/v1/premiumIndex",
        symbol_param="symbol",
        response_shape="dict",
    ),
    "basis": _RequestSpec(
        request_class="basis",
        data_class="basis",
        endpoint="basis",
        path="/futures/data/basis",
        symbol_param="pair",
        response_shape="list",
        period_required=True,
        limit_allowed=True,
        fixed_params=(("contractType", "PERPETUAL"),),
    ),
    "order_book_depth": _RequestSpec(
        request_class="order_book_depth",
        data_class="spread_depth",
        endpoint="order_book_depth",
        path="/fapi/v1/depth",
        symbol_param="symbol",
        response_shape="dict",
        limit_allowed=True,
    ),
}


class PublicDerivativesSource:
    def __init__(
        self,
        source: str,
        *,
        proxy_url: str | None = None,
        urlopen_func: Callable[..., Any] | None = None,
    ) -> None:
        self.source = _require_supported_source(source)
        self._urlopen = urlopen_func or urlopen_from_public_proxy(
            proxy_url,
            error_factory=DerivativesSourceError,
            default_urlopen=urlopen,
            proxy_handler_factory=ProxyHandler,
            opener_factory=build_opener,
        )

    def fetch_records(
        self,
        request_class: str,
        *,
        symbol: str,
        period: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        spec = _require_request_spec(request_class)
        symbol = _require_non_empty_text(symbol, "symbol")
        period = _normalize_period(spec, period)
        limit = _normalize_limit(spec, limit)
        url = _request_url(spec, symbol=symbol, period=period, limit=limit)

        try:
            payload = self._request_json(url)
        except _EndpointFetchError as exc:
            return _request_result(
                source=self.source,
                spec=spec,
                symbol=symbol,
                period=period,
                records=[],
                errors=[
                    _error_record(
                        source=self.source,
                        spec=spec,
                        symbol=symbol,
                        period=period,
                        error_type=exc.error_type,
                        message=str(exc),
                        status_code=exc.status_code,
                        raw_error_code=exc.raw_error_code,
                    )
                ],
            )

        records, errors = _normalize_payload(
            payload,
            source=self.source,
            spec=spec,
            symbol=symbol,
            period=period,
        )
        return _request_result(
            source=self.source,
            spec=spec,
            symbol=symbol,
            period=period,
            records=records,
            errors=errors,
        )

    def _request_json(self, url: str) -> Any:
        request = Request(url, headers={"User-Agent": "Halpha/0.0.0"})
        try:
            with self._urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            message, raw_error_code = _http_error_message(exc)
            error_type = "unsupported_symbol" if _is_unsupported_symbol_error(exc, message) else "http_error"
            raise _EndpointFetchError(
                message,
                error_type=error_type,
                status_code=exc.code,
                raw_error_code=raw_error_code,
            ) from exc
        except URLError as exc:
            raise _EndpointFetchError(
                f"binance_usdm derivatives request failed: {exc.reason}",
                error_type="network_error",
            ) from exc
        except TimeoutError as exc:
            raise _EndpointFetchError(
                "binance_usdm derivatives request timed out",
                error_type="timeout",
            ) from exc

        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise _EndpointFetchError(
                "binance_usdm derivatives endpoint returned invalid JSON",
                error_type="malformed_payload",
            ) from exc


def _normalize_payload(
    payload: Any,
    *,
    source: str,
    spec: _RequestSpec,
    symbol: str,
    period: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if spec.response_shape == "dict":
        if not isinstance(payload, dict):
            return [], [
                _malformed_error(
                    source=source,
                    spec=spec,
                    symbol=symbol,
                    period=period,
                    message=f"{spec.endpoint} expected a JSON object payload.",
                )
            ]
        return _normalize_rows([payload], source=source, spec=spec, symbol=symbol, period=period)

    if not isinstance(payload, list):
        return [], [
            _malformed_error(
                source=source,
                spec=spec,
                symbol=symbol,
                period=period,
                message=f"{spec.endpoint} expected a JSON list payload.",
            )
        ]
    return _normalize_rows(payload, source=source, spec=spec, symbol=symbol, period=period)


def _normalize_rows(
    rows: list[Any],
    *,
    source: str,
    spec: _RequestSpec,
    symbol: str,
    period: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = []
    errors = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(
                _malformed_error(
                    source=source,
                    spec=spec,
                    symbol=symbol,
                    period=period,
                    message=f"{spec.endpoint} row[{index}] must be a JSON object.",
                    item_path=f"row[{index}]",
                )
            )
            continue
        try:
            records.append(_normalize_row(row, source=source, spec=spec, symbol=symbol, period=period))
        except DerivativesSourceError as exc:
            errors.append(
                _malformed_error(
                    source=source,
                    spec=spec,
                    symbol=symbol,
                    period=period,
                    message=str(exc),
                    item_path=f"row[{index}]",
                )
            )
    return _sort_records(records), errors


def _normalize_row(
    row: dict[str, Any],
    *,
    source: str,
    spec: _RequestSpec,
    symbol: str,
    period: str,
) -> dict[str, Any]:
    if spec.request_class == "funding_rate_history":
        row_symbol = _required_text(row, "symbol", spec.endpoint)
        _require_symbol_match(row_symbol, symbol, spec.endpoint)
        as_of = _timestamp_from_millis(_required_millis(row, "fundingTime", spec.endpoint))
        metrics = {
            "funding_rate": _required_number(row, "fundingRate", spec.endpoint),
        }
        _add_optional_number(metrics, row, "markPrice", "mark_price")
        units = {"funding_rate": "ratio", "mark_price": "quote_asset"}
        raw_keys = ("symbol", "fundingRate", "fundingTime", "markPrice")
    elif spec.request_class == "open_interest_current":
        row_symbol = _required_text(row, "symbol", spec.endpoint)
        _require_symbol_match(row_symbol, symbol, spec.endpoint)
        as_of = _timestamp_from_millis(_required_millis(row, "time", spec.endpoint))
        metrics = {
            "open_interest_contracts": _required_number(row, "openInterest", spec.endpoint),
        }
        units = {"open_interest_contracts": "contracts"}
        raw_keys = ("symbol", "openInterest", "time")
    elif spec.request_class == "open_interest_history":
        row_symbol = _required_text(row, "symbol", spec.endpoint)
        _require_symbol_match(row_symbol, symbol, spec.endpoint)
        as_of = _timestamp_from_millis(_required_millis(row, "timestamp", spec.endpoint))
        metrics = {
            "open_interest_contracts": _required_number(row, "sumOpenInterest", spec.endpoint),
            "open_interest_value": _required_number(row, "sumOpenInterestValue", spec.endpoint),
        }
        _add_optional_number(metrics, row, "CMCCirculatingSupply", "cmc_circulating_supply")
        units = {
            "open_interest_contracts": "contracts",
            "open_interest_value": "quote_asset",
            "cmc_circulating_supply": "base_asset",
        }
        raw_keys = ("symbol", "sumOpenInterest", "sumOpenInterestValue", "CMCCirculatingSupply", "timestamp")
    elif spec.request_class == "premium_index":
        row_symbol = _required_text(row, "symbol", spec.endpoint)
        _require_symbol_match(row_symbol, symbol, spec.endpoint)
        as_of = _timestamp_from_millis(_required_millis(row, "time", spec.endpoint))
        mark_price = _required_number(row, "markPrice", spec.endpoint)
        index_price = _required_number(row, "indexPrice", spec.endpoint)
        metrics = {
            "mark_price": mark_price,
            "index_price": index_price,
            "premium_rate": _premium_rate(mark_price, index_price),
        }
        _add_optional_number(metrics, row, "lastFundingRate", "last_funding_rate")
        _add_optional_number(metrics, row, "interestRate", "interest_rate")
        units = {
            "mark_price": "quote_asset",
            "index_price": "quote_asset",
            "premium_rate": "ratio",
            "last_funding_rate": "ratio",
            "interest_rate": "ratio",
        }
        raw_keys = (
            "symbol",
            "markPrice",
            "indexPrice",
            "estimatedSettlePrice",
            "lastFundingRate",
            "interestRate",
            "nextFundingTime",
            "time",
        )
    elif spec.request_class == "basis":
        row_symbol = _required_text(row, "pair", spec.endpoint)
        _require_symbol_match(row_symbol, symbol, spec.endpoint)
        as_of = _timestamp_from_millis(_required_millis(row, "timestamp", spec.endpoint))
        metrics = {
            "basis": _required_number(row, "basis", spec.endpoint),
            "basis_rate": _required_number(row, "basisRate", spec.endpoint),
            "futures_price": _required_number(row, "futuresPrice", spec.endpoint),
            "index_price": _required_number(row, "indexPrice", spec.endpoint),
        }
        _add_optional_number(metrics, row, "annualizedBasisRate", "annualized_basis_rate")
        units = {
            "basis": "quote_asset",
            "basis_rate": "ratio",
            "annualized_basis_rate": "ratio",
            "futures_price": "quote_asset",
            "index_price": "quote_asset",
        }
        raw_keys = (
            "pair",
            "contractType",
            "basisRate",
            "futuresPrice",
            "indexPrice",
            "annualizedBasisRate",
            "basis",
            "timestamp",
        )
    elif spec.request_class == "order_book_depth":
        as_of = _timestamp_from_millis(_depth_timestamp(row, spec.endpoint))
        bids = _depth_levels(row, "bids", spec.endpoint)
        asks = _depth_levels(row, "asks", spec.endpoint)
        top_bid_price, top_bid_quantity = bids[0]
        top_ask_price, top_ask_quantity = asks[0]
        spread = top_ask_price - top_bid_price
        mid_price = (top_ask_price + top_bid_price) / 2
        bid_depth_quantity = sum(quantity for _price, quantity in bids)
        ask_depth_quantity = sum(quantity for _price, quantity in asks)
        depth_quantity = bid_depth_quantity + ask_depth_quantity
        metrics = {
            "top_bid_price": top_bid_price,
            "top_bid_quantity": top_bid_quantity,
            "top_ask_price": top_ask_price,
            "top_ask_quantity": top_ask_quantity,
            "mid_price": mid_price,
            "spread": spread,
            "spread_bps": spread / mid_price * 10000,
            "bid_depth_quantity": bid_depth_quantity,
            "ask_depth_quantity": ask_depth_quantity,
            "bid_depth_notional": sum(price * quantity for price, quantity in bids),
            "ask_depth_notional": sum(price * quantity for price, quantity in asks),
            "depth_imbalance": (
                (bid_depth_quantity - ask_depth_quantity) / depth_quantity if depth_quantity else 0.0
            ),
            "snapshot_depth_limit": max(len(bids), len(asks)),
        }
        units = {
            "top_bid_price": "quote_asset",
            "top_bid_quantity": "base_asset",
            "top_ask_price": "quote_asset",
            "top_ask_quantity": "base_asset",
            "mid_price": "quote_asset",
            "spread": "quote_asset",
            "spread_bps": "basis_points",
            "bid_depth_quantity": "base_asset",
            "ask_depth_quantity": "base_asset",
            "bid_depth_notional": "quote_asset",
            "ask_depth_notional": "quote_asset",
            "depth_imbalance": "ratio",
            "snapshot_depth_limit": "levels",
        }
        row = {
            **row,
            "bidLevelCount": len(bids),
            "askLevelCount": len(asks),
            "snapshotDepthLimit": max(len(bids), len(asks)),
        }
        raw_keys = ("lastUpdateId", "E", "T", "bidLevelCount", "askLevelCount", "snapshotDepthLimit")
    else:
        raise DerivativesSourceError(f"unsupported derivatives request_class: {spec.request_class}")

    return {
        "item_id": f"derivatives_market:{spec.data_class}:{source}:{symbol}:{period}:{as_of}",
        "data_class": spec.data_class,
        "source": source,
        "market_type": MARKET_TYPE,
        "symbol": symbol,
        "period": period,
        "as_of": as_of,
        "endpoint": spec.endpoint,
        "request_class": spec.request_class,
        "metrics": metrics,
        "units": _metric_units(metrics, units),
        "raw_fields": _raw_fields(row, raw_keys),
        "warnings": [],
        "errors": [],
    }


def _request_result(
    *,
    source: str,
    spec: _RequestSpec,
    symbol: str,
    period: str,
    records: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "source": source,
        "market_type": MARKET_TYPE,
        "request_class": spec.request_class,
        "data_class": spec.data_class,
        "endpoint": spec.endpoint,
        "symbol": symbol,
        "period": period,
        "records": records,
        "errors": errors,
    }


def _request_url(spec: _RequestSpec, *, symbol: str, period: str, limit: int | None) -> str:
    params: list[tuple[str, str | int]] = [(spec.symbol_param, symbol)]
    params.extend(spec.fixed_params)
    if spec.period_required:
        params.append(("period", period))
    if limit is not None:
        params.append(("limit", limit))
    return f"{BINANCE_USDM_BASE_URL}{spec.path}?{urlencode(params)}"


def _require_supported_source(source: str) -> str:
    _require_non_empty_text(source, "source")
    if source not in SUPPORTED_DERIVATIVES_MARKET_SOURCES:
        supported = ", ".join(sorted(SUPPORTED_DERIVATIVES_MARKET_SOURCES))
        raise DerivativesSourceError(f"unsupported derivatives source: {source}. Supported sources: {supported}.")
    return source


def _require_request_spec(request_class: str) -> _RequestSpec:
    _require_non_empty_text(request_class, "request_class")
    spec = _REQUEST_SPECS.get(request_class)
    if spec is None:
        supported = ", ".join(sorted(_REQUEST_SPECS))
        raise DerivativesSourceError(
            f"unsupported derivatives request_class: {request_class}. Supported request classes: {supported}."
        )
    return spec


def _normalize_period(spec: _RequestSpec, period: str | None) -> str:
    if spec.period_required:
        return _require_non_empty_text(period, "period")
    if period is not None:
        raise DerivativesSourceError(f"{spec.request_class} does not accept a period parameter.")
    return spec.default_period


def _normalize_limit(spec: _RequestSpec, limit: int | None) -> int | None:
    if limit is None:
        return None
    if not spec.limit_allowed:
        raise DerivativesSourceError(f"{spec.request_class} does not accept a limit parameter.")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        raise DerivativesSourceError("limit must be a positive integer.")
    if spec.request_class == "order_book_depth" and limit not in {5, 10, 20, 50, 100, 500, 1000}:
        raise DerivativesSourceError("order_book_depth limit must be one of: 5, 10, 20, 50, 100, 500, 1000.")
    return limit


def _required_text(data: dict[str, Any], key: str, endpoint: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DerivativesSourceError(f"{endpoint} payload missing non-empty {key}.")
    return value


def _require_non_empty_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DerivativesSourceError(f"{path} must be a non-empty string.")
    return value.strip()


def _required_millis(data: dict[str, Any], key: str, endpoint: str) -> int:
    value = data.get(key)
    if isinstance(value, bool):
        raise DerivativesSourceError(f"{endpoint} payload {key} must be a millisecond timestamp.")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    raise DerivativesSourceError(f"{endpoint} payload {key} must be a millisecond timestamp.")


def _required_number(data: dict[str, Any], key: str, endpoint: str) -> float:
    value = data.get(key)
    if value == "":
        raise DerivativesSourceError(f"{endpoint} payload {key} must be numeric.")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise DerivativesSourceError(f"{endpoint} payload {key} must be numeric.") from exc
    if not number.is_finite():
        raise DerivativesSourceError(f"{endpoint} payload {key} must be finite.")
    return float(number)


def _add_optional_number(
    metrics: dict[str, float],
    data: dict[str, Any],
    source_key: str,
    metric_key: str,
) -> None:
    if source_key not in data or data[source_key] in {None, ""}:
        return
    metrics[metric_key] = _required_number(data, source_key, "derivatives")


def _premium_rate(mark_price: float, index_price: float) -> float:
    if index_price == 0:
        raise DerivativesSourceError("premium_index payload indexPrice must be non-zero.")
    return (mark_price - index_price) / index_price


def _depth_timestamp(data: dict[str, Any], endpoint: str) -> int:
    for key in ("T", "E"):
        value = data.get(key)
        if value is not None:
            return _required_millis(data, key, endpoint)
    raise DerivativesSourceError(f"{endpoint} payload missing millisecond timestamp T or E.")


def _depth_levels(data: dict[str, Any], key: str, endpoint: str) -> list[tuple[float, float]]:
    values = data.get(key)
    if not isinstance(values, list) or not values:
        raise DerivativesSourceError(f"{endpoint} payload {key} must be a non-empty list.")
    levels = []
    for index, level in enumerate(values):
        if not isinstance(level, (list, tuple)) or len(level) < 2:
            raise DerivativesSourceError(f"{endpoint} payload {key}[{index}] must contain price and quantity.")
        price = _level_number(level[0], endpoint, f"{key}[{index}].price")
        quantity = _level_number(level[1], endpoint, f"{key}[{index}].quantity")
        if price <= 0:
            raise DerivativesSourceError(f"{endpoint} payload {key}[{index}].price must be positive.")
        if quantity < 0:
            raise DerivativesSourceError(f"{endpoint} payload {key}[{index}].quantity must be non-negative.")
        levels.append((price, quantity))
    return levels


def _level_number(value: Any, endpoint: str, path: str) -> float:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise DerivativesSourceError(f"{endpoint} payload {path} must be numeric.") from exc
    if not number.is_finite():
        raise DerivativesSourceError(f"{endpoint} payload {path} must be finite.")
    return float(number)


def _timestamp_from_millis(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _require_symbol_match(row_symbol: str, requested_symbol: str, endpoint: str) -> None:
    if row_symbol != requested_symbol:
        raise DerivativesSourceError(
            f"{endpoint} payload symbol {row_symbol} does not match requested symbol {requested_symbol}."
        )


def _sort_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        records,
        key=lambda record: (
            record["source"],
            record["data_class"],
            record["symbol"],
            record["period"],
            record["as_of"],
            record["endpoint"],
        ),
    )


def _raw_fields(row: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: row[key] for key in keys if key in row}


def _metric_units(metrics: dict[str, float], units: dict[str, str]) -> dict[str, str]:
    return {key: units[key] for key in metrics if key in units}


def _malformed_error(
    *,
    source: str,
    spec: _RequestSpec,
    symbol: str,
    period: str,
    message: str,
    item_path: str | None = None,
) -> dict[str, Any]:
    error = _error_record(
        source=source,
        spec=spec,
        symbol=symbol,
        period=period,
        error_type="malformed_payload",
        message=message,
    )
    if item_path is not None:
        error["item_path"] = item_path
    return error


def _error_record(
    *,
    source: str,
    spec: _RequestSpec,
    symbol: str,
    period: str,
    error_type: str,
    message: str,
    status_code: int | None = None,
    raw_error_code: int | str | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {
        "source": source,
        "market_type": MARKET_TYPE,
        "request_class": spec.request_class,
        "data_class": spec.data_class,
        "endpoint": spec.endpoint,
        "symbol": symbol,
        "period": period,
        "error_type": error_type,
        "message": message,
    }
    if status_code is not None:
        error["status_code"] = status_code
    if raw_error_code is not None:
        error["raw_error_code"] = raw_error_code
    return error


def _http_error_message(error: HTTPError) -> tuple[str, int | str | None]:
    body = _read_error_detail(error)
    raw_error_code: int | str | None = None
    message = f"binance_usdm derivatives endpoint returned HTTP {error.code}"
    if body:
        parsed = _parse_error_body(body)
        if parsed:
            raw_error_code = parsed.get("code")
            source_message = parsed.get("msg")
            if source_message:
                message = f"{message}: {source_message}"
        else:
            message = f"{message}: {body[:200].replace(chr(10), ' ')}"
    return message, raw_error_code


def _read_error_detail(error: HTTPError) -> str:
    try:
        return error.read().decode("utf-8").strip()
    except Exception:
        return ""


def _parse_error_body(body: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _is_unsupported_symbol_error(error: HTTPError, message: str) -> bool:
    return error.code == 400 and "invalid symbol" in message.lower()
