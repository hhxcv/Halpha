from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.objects import Price, Quantity

from halpha.planning.adapter import HalphaStrategyAdapter
from halpha.planning.bar_evaluation import (
    BarEvaluationError,
    EntrySizingSnapshot,
    NautilusBarEntryEvaluator,
)
from halpha.planning.registry import Direction, OneShotParameters
from halpha.planning.strategies.one_shot import (
    ActivationStrategyState,
    InstrumentQuantityRules,
    OneShotDonchianAtrLogic,
)


SOURCE = BarType.from_str("BTCUSDT-PERP.BINANCE-1-MINUTE-LAST-EXTERNAL")
TARGET = BarType.from_str("BTCUSDT-PERP.BINANCE-15-MINUTE-LAST-INTERNAL")


def _bar(bar_type: BarType, *, minute: int, close: str, high: str, low: str) -> Bar:
    timestamp = int(
        (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=minute)).timestamp()
        * 1_000_000_000
    )
    return Bar(
        bar_type=bar_type,
        open=Price.from_str(close),
        high=Price.from_str(high),
        low=Price.from_str(low),
        close=Price.from_str(close),
        volume=Quantity.from_str("100"),
        ts_event=timestamp,
        ts_init=timestamp,
    )


def _evaluator() -> NautilusBarEntryEvaluator:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return NautilusBarEntryEvaluator(
        activation_id="activation-bar-evaluation",
        instrument_ref="BTCUSDT-PERP",
        parameters=OneShotParameters(direction=Direction.LONG),
        decision_not_before=start,
        valid_until=start + timedelta(days=1),
        sizing_provider=lambda bar: EntrySizingSnapshot(
            reference_price=str(bar.close),
            reference_source="BACKTEST_LAST_BAR_PROXY",
            max_allowed_loss="50",
            max_notional="500",
            max_margin="100",
            effective_leverage="5",
            taker_fee_rate="0.0006",
            rules=InstrumentQuantityRules(
                step_size="0.0001",
                price_tick_size="0.1",
                min_quantity="0.0001",
                max_market_quantity="100",
                min_notional="5",
            ),
        ),
    )


def test_shared_adapter_builds_one_normalized_proposal_from_native_bars() -> None:
    evaluator = _evaluator()
    proposals = []
    adapter = HalphaStrategyAdapter(
        activation_id=evaluator.activation_id,
        logic=OneShotDonchianAtrLogic(evaluator.parameters),
        state_provider=lambda: ActivationStrategyState(),
        proposal_sink=proposals.append,
        bar_evaluator=evaluator,
    )
    for index in range(20):
        adapter.on_bar(
            _bar(
                TARGET,
                minute=(index + 1) * 15,
                close=str(100 + index),
                high=str(101 + index),
                low=str(99 + index),
            )
        )
    adapter.on_bar(_bar(SOURCE, minute=301, close="120.5", high="121", low="120"))
    adapter.on_bar(_bar(SOURCE, minute=302, close="120.8", high="121", low="120"))

    assert len(proposals) == 1
    assert proposals[0].activation_id == evaluator.activation_id
    assert proposals[0].reference_source == "BACKTEST_LAST_BAR_PROXY"
    assert proposals[0].action_profile == "ENTRY_MARKET"


def test_duplicate_bar_is_idempotent_and_conflicting_identity_fails_closed() -> None:
    evaluator = _evaluator()
    first = _bar(TARGET, minute=15, close="100", high="101", low="99")
    evaluator.accept(first)
    evaluator.accept(first)

    with pytest.raises(BarEvaluationError, match="TARGET_BAR_IDENTITY_CONFLICT"):
        evaluator.accept(_bar(TARGET, minute=15, close="101", high="102", low="100"))
