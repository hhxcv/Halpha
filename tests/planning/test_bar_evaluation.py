from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

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


def _evaluator(*, requires_live_warmup: bool = False) -> NautilusBarEntryEvaluator:
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
        requires_live_warmup=requires_live_warmup,
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


def test_live_warmup_primes_indicators_without_historical_proposals() -> None:
    evaluator = _evaluator(requires_live_warmup=True)
    with pytest.raises(BarEvaluationError, match="LIVE_WARMUP_NOT_COMPLETE"):
        evaluator.accept(_bar(SOURCE, minute=1, close="100", high="101", low="99"))

    for index in range(20):
        evaluator.accept_historical(
            _bar(
                TARGET,
                minute=(index + 1) * 15,
                close=str(100 + index),
                high=str(101 + index),
                low=str(99 + index),
            )
        )
    for minute in range(286, 301):
        evaluator.accept_historical(
            _bar(SOURCE, minute=minute, close="120", high="121", low="119")
        )

    evaluator.complete_live_warmup()
    assert evaluator.warmup_complete is True
    assert evaluator.accept(
        _bar(SOURCE, minute=300, close="120", high="121", low="119")
    ) is None
    assert evaluator.accept(
        _bar(SOURCE, minute=301, close="120.5", high="121", low="120")
    ) is None
    proposal_input = evaluator.accept(
        _bar(SOURCE, minute=302, close="120.8", high="121", low="120")
    )
    assert proposal_input is not None


def test_live_warmup_rejects_a_gapped_source_tail() -> None:
    evaluator = _evaluator(requires_live_warmup=True)
    for index in range(20):
        evaluator.accept_historical(
            _bar(
                TARGET,
                minute=(index + 1) * 15,
                close=str(100 + index),
                high=str(101 + index),
                low=str(99 + index),
            )
        )
    for minute in (*range(285, 292), *range(293, 301)):
        evaluator.accept_historical(
            _bar(SOURCE, minute=minute, close="120", high="121", low="119")
        )

    with pytest.raises(BarEvaluationError, match="SOURCE_WARMUP_INCOMPLETE"):
        evaluator.complete_live_warmup()


def test_live_adapter_warms_history_before_subscribing_to_bars() -> None:
    evaluator = _evaluator(requires_live_warmup=True)
    adapter = HalphaStrategyAdapter(
        activation_id=evaluator.activation_id,
        logic=OneShotDonchianAtrLogic(evaluator.parameters),
        state_provider=lambda: ActivationStrategyState(),
        proposal_sink=lambda _proposal: None,
        instrument_ref="BTCUSDT-PERP",
        bar_evaluator=evaluator,
        live_history_warmup=True,
        current_time_provider=lambda: datetime(2026, 1, 2, 6, 7, 30, tzinfo=UTC),
    )
    request_id = uuid4()
    events: list[tuple[str, object]] = []

    adapter.subscribe_mark_prices = lambda instrument_id: events.append(
        ("mark", instrument_id)
    )
    adapter.subscribe_quote_ticks = lambda instrument_id: events.append(
        ("quote", instrument_id)
    )
    adapter.subscribe_bars = lambda bar_type: events.append(("bar", bar_type))

    def request_aggregated_bars(bar_types, **kwargs):
        events.append(("request", (bar_types, kwargs)))
        return request_id

    adapter.request_aggregated_bars = request_aggregated_bars
    adapter.on_start()

    assert [event[0] for event in events] == ["mark", "quote", "request"]
    bar_types, request = events[-1][1]
    # Nautilus expects requested bar types to be internally aggregated. The
    # first composite names the external 1m source queried from Binance, and
    # include_external_data forwards that source to on_historical_data.
    assert bar_types == [evaluator.target_bar_type]
    assert bar_types[0].is_internally_aggregated()
    assert bar_types[0].is_composite()
    assert bar_types[0].composite() == evaluator.source_bar_type
    assert request["include_external_data"] is True
    assert request["update_subscriptions"] is True
    assert request["update_catalog"] is False
    assert request["end"] - request["start"] < timedelta(hours=72, minutes=15)

    for index in range(20):
        adapter.on_historical_data(
            _bar(
                TARGET.standard(),
                minute=(index + 1) * 15,
                close=str(100 + index),
                high=str(101 + index),
                low=str(99 + index),
            )
        )
    for minute in range(286, 301):
        adapter.on_historical_data(
            _bar(SOURCE, minute=minute, close="120", high="121", low="119")
        )

    request["callback"](request_id)

    assert evaluator.warmup_complete is True
    assert adapter.live_history_ready is True
    assert events[-2:] == [
        ("bar", SOURCE),
        ("bar", evaluator.target_bar_type),
    ]
