from types import SimpleNamespace

import pytest

from halpha.venue_integration.binance_rules import (
    BinanceInstrumentRulesError,
    binance_exchange_symbol_rules,
    parse_binance_symbol_filters,
)


def _filters() -> list[dict[str, str]]:
    return [
        {
            "filterType": "PRICE_FILTER",
            "minPrice": "0.10",
            "maxPrice": "1000000.00",
            "tickSize": "0.10",
        },
        {
            "filterType": "LOT_SIZE",
            "minQty": "0.0001",
            "maxQty": "1000",
            "stepSize": "0.0001",
        },
        {
            "filterType": "MARKET_LOT_SIZE",
            "minQty": "0.001",
            "maxQty": "100",
            "stepSize": "0.001",
        },
        {"filterType": "MIN_NOTIONAL", "notional": "5.0"},
    ]


def test_shared_parser_keeps_limit_and_market_quantity_filters_separate() -> None:
    rules = parse_binance_symbol_filters(_filters())

    assert rules.order_schedule_payload() == {
        "min_price": "0.1",
        "max_price": "1000000",
        "price_tick_size": "0.1",
        "limit_quantity_step": "0.0001",
        "min_limit_quantity": "0.0001",
        "max_limit_quantity": "1000",
        "market_quantity_step": "0.001",
        "min_market_quantity": "0.001",
        "max_market_quantity": "100",
        "min_notional": "5",
    }
    assert rules.market_sizing_payload()["step_size"] == "0.001"
    assert rules.market_sizing_payload()["max_market_quantity"] == "100"


def test_exchange_parser_accepts_nautilus_shaped_objects() -> None:
    object_filters = [SimpleNamespace(**item) for item in _filters()]
    exchange_info = SimpleNamespace(
        symbols=[SimpleNamespace(symbol="BTCUSDT", filters=object_filters)]
    )

    rules = binance_exchange_symbol_rules(exchange_info, "BTCUSDT")

    assert rules.price_tick_size == "0.1"
    assert rules.limit_quantity_step == "0.0001"


def test_missing_required_filter_is_unknown() -> None:
    with pytest.raises(BinanceInstrumentRulesError, match="INSTRUMENT_RULES_UNKNOWN"):
        parse_binance_symbol_filters(_filters()[:-1])
