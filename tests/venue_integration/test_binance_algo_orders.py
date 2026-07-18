from __future__ import annotations

from types import SimpleNamespace

import pytest

from halpha.planning.models import ProposedActionKind
from halpha.venue_integration.binance_algo_orders import (
    BinanceAlgoOrderEvidenceError,
    working_fact_from_open_algo_orders,
)
from halpha.venue_integration.models import (
    VenueFactKind,
    VenueFactSourceClass,
)
from tests.venue_integration.test_execution_action import NOW, _action, _proposed


def _protection_action():
    return _action(
        _proposed(
            kind=ProposedActionKind.PROTECTION,
            profile="PROTECTIVE_STOP_REDUCE_ONLY",
            order_type="STOP_MARKET",
            reduce_only=True,
            quantity="0.004",
            trigger_price="50000.1",
        )
    )


def _take_profit_action():
    return _action(
        _proposed(
            kind=ProposedActionKind.TAKE_PROFIT,
            profile="TAKE_PROFIT_1",
            order_type="MARKET_IF_TOUCHED",
            reduce_only=True,
            quantity="0.002",
            trigger_price="60000.1",
        )
    )


def _open_algo(**updates):
    action = _protection_action()
    values = {
        "algoId": 10000001,
        "clientAlgoId": action.client_order_id,
        "algoStatus": "NEW",
        "orderType": "STOP_MARKET",
        "symbol": "BTCUSDT",
        "quantity": "0.0040",
        "triggerPrice": "50000.10",
        "reduceOnly": True,
        "closePosition": False,
        "workingType": "CONTRACT_PRICE",
        "createTime": 1_773_910_800_000,
        "updateTime": 1_773_910_800_100,
    }
    values.update(updates)
    return SimpleNamespace(**values)


def test_exact_open_algo_uuid_projects_authoritative_working_fact() -> None:
    action = _protection_action()
    fact = working_fact_from_open_algo_orders(
        action=action,
        open_algo_orders=(_open_algo(),),
        expected_symbol="BTCUSDT",
        observed_at=NOW,
    )

    assert fact is not None
    assert fact.kind is VenueFactKind.ORDER_STATE
    assert fact.source_class is VenueFactSourceClass.VENUE_QUERY
    assert fact.payload["status"] == "WORKING"
    assert fact.payload["venue_status"] == "NEW"
    assert fact.payload["venue_order_ref"] == "10000001"
    assert fact.payload["query_path"] == "/fapi/v1/openAlgoOrders"
    assert fact.payload["read_only"] is True


def test_unrelated_open_algo_is_ignored() -> None:
    action = _protection_action()
    assert working_fact_from_open_algo_orders(
        action=action,
        open_algo_orders=(_open_algo(clientAlgoId="f" * 32),),
        expected_symbol="BTCUSDT",
        observed_at=NOW,
    ) is None


def test_generic_market_if_touched_maps_to_binance_take_profit_market() -> None:
    action = _take_profit_action()
    fact = working_fact_from_open_algo_orders(
        action=action,
        open_algo_orders=(
            _open_algo(
                clientAlgoId=action.client_order_id,
                orderType="TAKE_PROFIT_MARKET",
                quantity="0.002",
                triggerPrice="60000.1",
            ),
        ),
        expected_symbol="BTCUSDT",
        observed_at=NOW,
    )

    assert fact is not None
    assert fact.payload["order_type"] == "TAKE_PROFIT_MARKET"
    assert fact.payload["action_order_type"] == "MARKET_IF_TOUCHED"
    assert fact.payload["action_profile"] == "TAKE_PROFIT_1"


@pytest.mark.parametrize(
    ("updates", "reason"),
    (
        ({"symbol": "ETHUSDT"}, "ALGO_QUERY_SYMBOL_MISMATCH"),
        ({"algoStatus": "CANCELED"}, "ALGO_QUERY_STATUS_INVALID"),
        ({"orderType": "TAKE_PROFIT_MARKET"}, "ALGO_QUERY_ORDER_TYPE_MISMATCH"),
        ({"reduceOnly": False}, "ALGO_QUERY_REDUCE_ONLY_MISMATCH"),
        ({"closePosition": True}, "ALGO_QUERY_CLOSE_POSITION_MISMATCH"),
        ({"quantity": "0.005"}, "ALGO_QUERY_QUANTITY_MISMATCH"),
        ({"triggerPrice": "50001"}, "ALGO_QUERY_TRIGGER_PRICE_MISMATCH"),
    ),
)
def test_claimed_open_algo_must_match_persisted_terms(updates, reason) -> None:
    with pytest.raises(BinanceAlgoOrderEvidenceError, match=reason):
        working_fact_from_open_algo_orders(
            action=_protection_action(),
            open_algo_orders=(_open_algo(**updates),),
            expected_symbol="BTCUSDT",
            observed_at=NOW,
        )
