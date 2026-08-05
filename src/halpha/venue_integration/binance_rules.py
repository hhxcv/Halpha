"""Canonical Binance symbol-filter parsing shared by planning and execution."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

from halpha.domain_values import canonical_decimal


class BinanceInstrumentRulesError(ValueError):
    """The venue response cannot prove the required instrument rules."""


def _value(source: object, name: str) -> Any:
    if isinstance(source, Mapping):
        return source.get(name)
    return getattr(source, name, None)


def _filter_name(item: object) -> str:
    value = _value(item, "filterType")
    return str(getattr(value, "value", value))


def _positive_decimal(source: object, *names: str) -> str:
    raw = None
    for name in names:
        candidate = _value(source, name)
        if candidate is not None:
            raw = candidate
            break
    try:
        parsed = Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        raise BinanceInstrumentRulesError("INSTRUMENT_RULES_UNKNOWN") from None
    if not parsed.is_finite() or parsed <= 0:
        raise BinanceInstrumentRulesError("INSTRUMENT_RULES_UNKNOWN")
    return canonical_decimal(parsed)


@dataclass(frozen=True, slots=True)
class BinanceInstrumentRuleSet:
    min_price: str
    max_price: str
    price_tick_size: str
    limit_quantity_step: str
    min_limit_quantity: str
    max_limit_quantity: str
    market_quantity_step: str
    min_market_quantity: str
    max_market_quantity: str
    min_notional: str

    def order_schedule_payload(self) -> dict[str, str]:
        return {
            "min_price": self.min_price,
            "max_price": self.max_price,
            "price_tick_size": self.price_tick_size,
            "limit_quantity_step": self.limit_quantity_step,
            "min_limit_quantity": self.min_limit_quantity,
            "max_limit_quantity": self.max_limit_quantity,
            "market_quantity_step": self.market_quantity_step,
            "min_market_quantity": self.min_market_quantity,
            "max_market_quantity": self.max_market_quantity,
            "min_notional": self.min_notional,
        }

    def market_sizing_payload(self) -> dict[str, str]:
        return {
            "step_size": self.market_quantity_step,
            "price_tick_size": self.price_tick_size,
            "min_quantity": self.min_market_quantity,
            "max_market_quantity": self.max_market_quantity,
            "min_notional": self.min_notional,
        }


def parse_binance_symbol_filters(
    raw_filters: Iterable[object],
) -> BinanceInstrumentRuleSet:
    filters = {_filter_name(item): item for item in raw_filters}
    try:
        price = filters["PRICE_FILTER"]
        limit_lot = filters["LOT_SIZE"]
        market_lot = filters["MARKET_LOT_SIZE"]
        notional = filters["MIN_NOTIONAL"]
    except KeyError:
        raise BinanceInstrumentRulesError("INSTRUMENT_RULES_UNKNOWN") from None
    return BinanceInstrumentRuleSet(
        min_price=_positive_decimal(price, "minPrice"),
        max_price=_positive_decimal(price, "maxPrice"),
        price_tick_size=_positive_decimal(price, "tickSize"),
        limit_quantity_step=_positive_decimal(limit_lot, "stepSize"),
        min_limit_quantity=_positive_decimal(limit_lot, "minQty"),
        max_limit_quantity=_positive_decimal(limit_lot, "maxQty"),
        market_quantity_step=_positive_decimal(market_lot, "stepSize"),
        min_market_quantity=_positive_decimal(market_lot, "minQty"),
        max_market_quantity=_positive_decimal(market_lot, "maxQty"),
        min_notional=_positive_decimal(notional, "notional", "minNotional"),
    )


def binance_exchange_symbol_rules(
    exchange_info: object,
    symbol: str,
) -> BinanceInstrumentRuleSet:
    symbols = _value(exchange_info, "symbols")
    if not isinstance(symbols, list):
        raise BinanceInstrumentRulesError("INSTRUMENT_RULES_UNKNOWN")
    symbol_info = next(
        (item for item in symbols if str(_value(item, "symbol")) == symbol),
        None,
    )
    raw_filters = _value(symbol_info, "filters") if symbol_info is not None else None
    if not isinstance(raw_filters, list):
        raise BinanceInstrumentRulesError("INSTRUMENT_RULES_UNKNOWN")
    return parse_binance_symbol_filters(raw_filters)
