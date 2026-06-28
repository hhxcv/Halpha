from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from halpha.market.ohlcv_source import (
    OHLCV_SOURCE_SPECS,
    OHLCVSourceError,
    QUOTE_SUFFIXES,
    SUPPORTED_OHLCV_SOURCES,
    ohlcv_exchange_symbol,
)


UNKNOWN = "unknown"
NO_CONTRACT = "none"
PRICE_UNIT_QUOTE_PER_BASE = "quote_asset_per_base_asset"
LINEAR_SWAP_QUOTES = {"USDT", "USDC", "USD"}


class InstrumentIdentityError(ValueError):
    """Raised when a source/symbol/timeframe identity cannot be derived."""


@dataclass(frozen=True)
class InstrumentIdentity:
    source: str
    symbol: str
    exchange_symbol: str
    market_type: str
    contract_type: str
    base_asset: str
    quote_asset: str
    settlement_asset: str
    price_unit: str
    timeframe: str
    identity_status: str
    warnings: tuple[dict[str, str], ...] = ()

    def to_record(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "source": self.source,
            "symbol": self.symbol,
            "exchange_symbol": self.exchange_symbol,
            "market_type": self.market_type,
            "contract_type": self.contract_type,
            "base_asset": self.base_asset,
            "quote_asset": self.quote_asset,
            "settlement_asset": self.settlement_asset,
            "price_unit": self.price_unit,
            "timeframe": self.timeframe,
            "identity_status": self.identity_status,
            "warnings": list(self.warnings),
        }


def derive_instrument_identity(
    *,
    source: str,
    symbol: str,
    timeframe: str,
) -> dict[str, Any]:
    """Return a JSON-compatible research identity for an OHLCV source tuple."""

    return instrument_identity(source=source, symbol=symbol, timeframe=timeframe).to_record()


def instrument_identity(
    *,
    source: str,
    symbol: str,
    timeframe: str,
) -> InstrumentIdentity:
    source = _require_supported_source(source)
    symbol = _require_non_empty_text(symbol, "symbol")
    timeframe = _require_non_empty_text(timeframe, "timeframe")
    spec = OHLCV_SOURCE_SPECS[source]
    base_asset, quote_asset, settlement_from_symbol = _symbol_assets(symbol)
    warnings: list[dict[str, str]] = []
    if base_asset == UNKNOWN or quote_asset == UNKNOWN:
        warnings.append(
            _warning(
                "symbol_assets_unknown",
                f"Could not infer base and quote assets from symbol {symbol}.",
            )
        )

    try:
        exchange_symbol = ohlcv_exchange_symbol(source, symbol)
    except OHLCVSourceError as exc:
        raise InstrumentIdentityError(str(exc)) from exc

    if spec.market_type == "spot":
        contract_type = "spot" if base_asset != UNKNOWN and quote_asset != UNKNOWN else UNKNOWN
        settlement_asset = NO_CONTRACT if contract_type == "spot" else UNKNOWN
        identity_status = "normalized" if contract_type == "spot" else "degraded"
    elif spec.market_type == "swap":
        contract_type, settlement_asset = _swap_contract_identity(quote_asset, settlement_from_symbol)
        warnings.append(
            _warning(
                "contract_terms_inferred_without_market_metadata",
                (
                    f"{source} {symbol} swap identity is inferred from source config "
                    "and symbol parsing; no exchange market metadata was fetched."
                ),
            )
        )
        identity_status = "inferred" if contract_type != UNKNOWN else "degraded"
    else:
        contract_type = UNKNOWN
        settlement_asset = UNKNOWN
        identity_status = "degraded"
        warnings.append(
            _warning(
                "market_type_unknown",
                f"{source} market type {spec.market_type} is not recognized by instrument identity.",
            )
        )

    price_unit = (
        PRICE_UNIT_QUOTE_PER_BASE
        if base_asset != UNKNOWN and quote_asset != UNKNOWN
        else UNKNOWN
    )
    return InstrumentIdentity(
        source=source,
        symbol=symbol,
        exchange_symbol=exchange_symbol,
        market_type=spec.market_type,
        contract_type=contract_type,
        base_asset=base_asset,
        quote_asset=quote_asset,
        settlement_asset=settlement_asset,
        price_unit=price_unit,
        timeframe=timeframe,
        identity_status=identity_status,
        warnings=tuple(warnings),
    )


def identity_from_ohlcv_record(record: dict[str, Any]) -> dict[str, Any]:
    return derive_instrument_identity(
        source=_require_non_empty_text(record.get("source"), "record.source"),
        symbol=_require_non_empty_text(record.get("symbol"), "record.symbol"),
        timeframe=_require_non_empty_text(record.get("timeframe"), "record.timeframe"),
    )


def _swap_contract_identity(
    quote_asset: str,
    settlement_from_symbol: str | None,
) -> tuple[str, str]:
    if quote_asset in LINEAR_SWAP_QUOTES:
        return "linear_perpetual", settlement_from_symbol or quote_asset
    return UNKNOWN, UNKNOWN


def _symbol_assets(symbol: str) -> tuple[str, str, str | None]:
    requested = symbol.strip()
    if "/" in requested:
        pair, _, settlement = requested.partition(":")
        base, separator, quote = pair.partition("/")
        if separator:
            return (
                _asset_or_unknown(base),
                _asset_or_unknown(quote),
                _asset_or_none(settlement),
            )
    compact = requested.upper()
    for quote in QUOTE_SUFFIXES:
        if compact.endswith(quote) and len(compact) > len(quote):
            return compact[: -len(quote)], quote, None
    return UNKNOWN, UNKNOWN, None


def _require_supported_source(source: str) -> str:
    source = _require_non_empty_text(source, "source")
    if source not in SUPPORTED_OHLCV_SOURCES:
        supported = ", ".join(sorted(SUPPORTED_OHLCV_SOURCES))
        raise InstrumentIdentityError(
            f"unsupported OHLCV source: {source}. Supported sources: {supported}."
        )
    return source


def _require_non_empty_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InstrumentIdentityError(f"{path} must be a non-empty string.")
    return value.strip()


def _asset_or_unknown(value: str) -> str:
    value = value.strip().upper()
    return value or UNKNOWN


def _asset_or_none(value: str) -> str | None:
    value = value.strip().upper()
    return value or None


def _warning(code: str, message: str) -> dict[str, str]:
    return {
        "severity": "warning",
        "code": code,
        "message": message,
        "source": "instrument_identity",
    }
