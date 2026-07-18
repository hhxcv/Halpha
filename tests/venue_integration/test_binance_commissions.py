from __future__ import annotations

from types import SimpleNamespace

import pytest

from halpha.capital.models import RiskClass
from halpha.venue_integration.binance_commissions import (
    BinanceCommissionEvidenceError,
    commission_facts_from_user_trades,
    missing_commission_trade_ids,
)
from halpha.venue_integration.facts import build_venue_fact
from halpha.venue_integration.models import (
    ExecutionActionState,
    VenueFactKind,
    VenueFactSourceClass,
)
from halpha.venue_integration.transitions import apply_venue_outcome, begin_submission
from tests.venue_integration.test_execution_action import NOW, _action, _cap_decision


def _accepted_action():
    submitting = begin_submission(
        _action(),
        capital_decision=_cap_decision(RiskClass.RISK_INCREASING),
        request_payload={"profile": "ENTRY_MARKET"},
        observed_at=NOW,
    )
    return apply_venue_outcome(
        submitting,
        target=ExecutionActionState.ACKNOWLEDGED,
        venue_order_refs=("314159",),
        venue_fact_refs=(),
        observed_at=NOW,
    )


def _fill(action):
    return build_venue_fact(
        venue_fact_id="10000000-0000-0000-0000-000000000020",
        environment_id=action.environment_id,
        venue_ref="BINANCE",
        account_ref=action.account_ref,
        instrument_ref="BTCUSDT-PERP",
        kind=VenueFactKind.FILL,
        source_class=VenueFactSourceClass.VENUE_STREAM,
        source_object_id="2718",
        source_sequence="fill-event-1",
        source_time=NOW,
        received_at=NOW,
        cutoff=NOW,
        payload={
            "trade_id": "2718",
            "venue_order_ref": "314159",
            "last_price": "50000.10",
            "last_quantity": "0.002",
        },
        action=action,
    )


def _trade(**updates):
    values = {
        "id": 2718,
        "orderId": 314159,
        "symbol": "BTCUSDT",
        "price": "50000.100",
        "qty": "0.0020",
        "commission": "0.04000000",
        "commissionAsset": "USDT",
        "time": 1_773_910_800_000,
    }
    values.update(updates)
    return SimpleNamespace(**values)


def test_read_only_user_trade_completes_missing_actual_commission() -> None:
    action = _accepted_action()
    fill = _fill(action)

    facts = commission_facts_from_user_trades(
        action=action,
        facts=(fill,),
        user_trades=(_trade(),),
        expected_symbol="BTCUSDT",
        observed_at=NOW,
    )

    assert missing_commission_trade_ids((fill,)) == ("2718",)
    assert len(facts) == 1
    commission = facts[0]
    assert commission.kind is VenueFactKind.COMMISSION
    assert commission.source_class is VenueFactSourceClass.VENUE_QUERY
    assert commission.source_object_id == fill.source_object_id
    assert commission.payload["amount"] == "0.04"
    assert commission.payload["currency"] == "USDT"
    assert commission.payload["query_path"] == "/fapi/v1/userTrades"
    assert commission.payload["read_only"] is True


def test_existing_actual_commission_is_not_duplicated() -> None:
    action = _accepted_action()
    fill = _fill(action)
    existing = commission_facts_from_user_trades(
        action=action,
        facts=(fill,),
        user_trades=(_trade(),),
        expected_symbol="BTCUSDT",
        observed_at=NOW,
    )[0]

    assert missing_commission_trade_ids((fill, existing)) == ()
    assert commission_facts_from_user_trades(
        action=action,
        facts=(fill, existing),
        user_trades=(_trade(),),
        expected_symbol="BTCUSDT",
        observed_at=NOW,
    ) == ()


@pytest.mark.parametrize(
    ("updates", "reason"),
    (
        ({"orderId": 314160}, "COMMISSION_QUERY_ORDER_MISMATCH"),
        ({"symbol": "ETHUSDT"}, "COMMISSION_QUERY_SYMBOL_MISMATCH"),
        ({"price": "50000.11"}, "COMMISSION_QUERY_PRICE_MISMATCH"),
        ({"qty": "0.003"}, "COMMISSION_QUERY_QUANTITY_MISMATCH"),
        ({"commission": "-0.01"}, "COMMISSION_QUERY_COMMISSION_INVALID"),
        ({"commissionAsset": ""}, "COMMISSION_QUERY_ASSET_MISSING"),
    ),
)
def test_claimed_trade_must_match_fill_and_actual_fee_contract(updates, reason) -> None:
    action = _accepted_action()
    with pytest.raises(BinanceCommissionEvidenceError, match=reason):
        commission_facts_from_user_trades(
            action=action,
            facts=(_fill(action),),
            user_trades=(_trade(**updates),),
            expected_symbol="BTCUSDT",
            observed_at=NOW,
        )


def test_unrelated_account_trade_is_ignored() -> None:
    action = _accepted_action()
    assert commission_facts_from_user_trades(
        action=action,
        facts=(_fill(action),),
        user_trades=(_trade(id=9999),),
        expected_symbol="BTCUSDT",
        observed_at=NOW,
    ) == ()
