from datetime import UTC, datetime

import pytest

from halpha.outcomes.account_reconciliation import (
    AccountReconciliationError,
    EXTERNAL_ACCOUNT_CLOSURE,
    account_result_role,
    build_external_account_closure_facts,
)
from halpha.outcomes.trade_result import summarize_trade_result


def _facts(*, reduce_only: bool = True, realized_pnl: str = "-0.190350"):
    return build_external_account_closure_facts(
        environment_id="demo-main",
        account_ref="demo-account",
        instrument_ref="BTCUSDT-PERP",
        activation_id="activation-1",
        direction="LONG",
        open_quantity="0.0015",
        average_entry_price="65549.9",
        attributed_trade_ids=frozenset({"519484642"}),
        order={
            "order_id": "22983261835",
            "client_order_id": "2e5b705f947c5a71bcc66f4471ddc1f4",
            "symbol": "BTCUSDT",
            "status": "FILLED",
            "side": "SELL",
            "order_type": "MARKET",
            "executed_quantity": "0.0015",
            "average_price": "65423.0",
            "reduce_only": reduce_only,
            "update_time_ms": 1784563676828,
        },
        trades=(
            {
                "trade_id": "519485905",
                "order_id": "22983261835",
                "symbol": "BTCUSDT",
                "side": "SELL",
                "price": "65423.8",
                "quantity": "0.0011",
                "commission": "0.02878647",
                "commission_asset": "USDT",
                "realized_pnl": "-0.13871",
                "time_ms": 1784563676828,
                "maker": False,
            },
            {
                "trade_id": "519485906",
                "order_id": "22983261835",
                "symbol": "BTCUSDT",
                "side": "SELL",
                "price": "65420.8",
                "quantity": "0.0004",
                "commission": "0.01046732",
                "commission_asset": "USDT",
                "realized_pnl": realized_pnl,
                "time_ms": 1784563676828,
                "maker": False,
            },
        ),
        observed_at=datetime(2026, 7, 22, tzinfo=UTC),
    )


def test_external_closure_remains_unclaimed_but_closes_exact_account_result() -> None:
    facts = _facts(realized_pnl="-0.05164")

    assert len(facts) == 5
    assert all(fact.activation_ref is None for fact in facts)
    assert all(fact.action_ref is None for fact in facts)
    assert all(fact.attribution_class is None for fact in facts)
    assert all(
        account_result_role(fact.impact_scope) == EXTERNAL_ACCOUNT_CLOSURE
        for fact in facts
    )

    entry_facts = (
        {
            "kind": "FILL",
            "action_ref": "entry-action",
            "source_time": "2026-07-20T16:04:01.139+00:00",
            "payload": {
                "trade_id": "519484642",
                "last_price": "65549.9",
                "last_quantity": "0.0015",
            },
        },
        {
            "kind": "COMMISSION",
            "action_ref": "entry-action",
            "payload": {
                "trade_id": "519484642",
                "amount": "0.03932994 USDT",
                "currency": "USDT",
            },
        },
    )
    external_facts = tuple(
        {
            "kind": fact.kind.value,
            "action_ref": None,
            "source_time": fact.source_time,
            "result_role": account_result_role(fact.impact_scope),
            "payload": fact.payload,
        }
        for fact in facts
    )
    result = summarize_trade_result(
        direction="LONG",
        action_kinds={"entry-action": "ENTRY"},
        facts=(*entry_facts, *external_facts),
    )

    assert result["closed"] is True
    assert result["average_exit_price"] == "65423"
    assert result["gross_pnl"] == "-0.19035"
    assert result["commission"] == "0.07858373"
    assert result["net_pnl"] == "-0.26893373"
    assert result["holding_duration_seconds"] == "235.689"
    assert result["result_scope"] == "ACCOUNT_FACTS_WITH_EXTERNAL_CLOSURE"
    assert result["strategy_attribution_complete"] is False
    assert result["external_closure_fill_count"] == 2


def test_external_closure_requires_reduce_only_order() -> None:
    with pytest.raises(
        AccountReconciliationError,
        match="EXTERNAL_ORDER_NOT_REDUCE_ONLY",
    ):
        _facts(reduce_only=False, realized_pnl="-0.05164")


def test_external_closure_rejects_exchange_pnl_mismatch() -> None:
    with pytest.raises(
        AccountReconciliationError,
        match="EXTERNAL_REALIZED_PNL_MISMATCH",
    ):
        _facts(realized_pnl="0")
