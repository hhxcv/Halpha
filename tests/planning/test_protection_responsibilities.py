from __future__ import annotations

from datetime import UTC, datetime, timedelta

from halpha.capital.models import AuthorityClass, EnvironmentKind
from halpha.planning.models import PlanActivation
from halpha.planning.registry import Direction
from halpha.planning.transitions import (
    proposed_protection_from_fill,
    proposed_take_profits_from_fill,
    record_first_fill,
)


NOW = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)


def _activation(direction: Direction = Direction.LONG) -> PlanActivation:
    return PlanActivation(
        activation_id="10000000-0000-0000-0000-000000000001",
        environment_id="demo-main",
        environment_kind=EnvironmentKind.DEMO,
        authority_class=AuthorityClass.DEMO_VALIDATION,
        plan_version_ref="10000000-0000-0000-0000-000000000002",
        authorization_version_ref="10000000-0000-0000-0000-000000000003",
        allocation_ref="10000000-0000-0000-0000-000000000004",
        account_ref="demo-owner",
        instrument_ref="BTCUSDT-PERP",
        direction=direction,
        strategy_id="ONE_SHOT_DONCHIAN_ATR_BREAKOUT",
        framework_strategy_id="HALPHA-TEST-001",
        target_exposure="0.01",
        rule_state={"deadlines": {}, "condition_judgements": {}, "last_bar_cursors": {}},
        created_at=NOW,
        updated_at=NOW,
    )


def _context() -> dict[str, object]:
    return {
        "trigger_atr": "2",
        "initial_stop_atr_multiple": "1.5",
        "take_profit_1_r": "1.5",
        "take_profit_1_fraction": "0.5",
        "take_profit_2_r": "3",
        "max_hold_bars_15m": 96,
        "indicator_source_digest": "a" * 64,
        "indicator_source_cutoff_ns": 1_773_910_800_000_000_000,
        "quantity_step": "0.001",
        "price_tick_size": "0.1",
    }


def test_first_fill_freezes_r_and_later_partial_fill_cannot_overwrite_it() -> None:
    activation = record_first_fill(
        _activation(),
        entry_action_ref="entry-action",
        fill_fact_ref="fill-1",
        fill_price="100",
        fill_time=NOW,
        entry_risk_context=_context(),
        observed_at=NOW,
    )
    frozen = activation.rule_state["first_fill"]
    assert frozen["first_fill_price"] == "100"
    assert frozen["trigger_atr"] == "2"
    assert frozen["R"] == "3"
    assert frozen["time_exit_due_at"] == (NOW + timedelta(days=1)).isoformat()
    assert activation.has_entry_fill is True
    assert activation.entry_opportunity_consumed is True

    replay = record_first_fill(
        activation,
        entry_action_ref="entry-action",
        fill_fact_ref="fill-2",
        fill_price="101",
        fill_time=NOW + timedelta(seconds=5),
        entry_risk_context=_context(),
        observed_at=NOW + timedelta(seconds=5),
    )
    assert replay is activation
    assert replay.rule_state["first_fill"] == frozen


def test_long_fill_derives_explicit_stop_and_two_fixed_reduce_only_take_profits() -> None:
    activation = record_first_fill(
        _activation(Direction.LONG),
        entry_action_ref="entry-action",
        fill_fact_ref="fill-1",
        fill_price="100",
        fill_time=NOW,
        entry_risk_context=_context(),
        observed_at=NOW,
    )
    protection = proposed_protection_from_fill(
        activation,
        entry_action_ref="entry-action",
        fill_fact_ref="fill-1",
        fill_source_identity="trade-1:1",
        fill_quantity="0.01",
    )
    assert protection.action_profile == "PROTECTIVE_STOP_REDUCE_ONLY"
    assert protection.quantity == "0.01"
    assert protection.trigger_price == "97"
    assert protection.reduce_only is True
    tp1, tp2 = proposed_take_profits_from_fill(
        activation,
        entry_action_ref="entry-action",
        protection_action_ref="protection-action",
        fill_fact_ref="fill-1",
        fill_source_identity="trade-1:1",
        fill_quantity="0.01",
    )
    assert (tp1.quantity, tp2.quantity) == ("0.005", "0.005")
    assert (tp1.trigger_price, tp2.trigger_price) == ("104.5", "109")
    assert tp1.reduce_only is tp2.reduce_only is True


def test_short_fill_reverses_price_direction_without_changing_execution_flow() -> None:
    activation = record_first_fill(
        _activation(Direction.SHORT),
        entry_action_ref="entry-action",
        fill_fact_ref="fill-1",
        fill_price="100",
        fill_time=NOW,
        entry_risk_context=_context(),
        observed_at=NOW,
    )
    protection = proposed_protection_from_fill(
        activation,
        entry_action_ref="entry-action",
        fill_fact_ref="fill-1",
        fill_source_identity="trade-1:1",
        fill_quantity="0.01",
    )
    tp1, tp2 = proposed_take_profits_from_fill(
        activation,
        entry_action_ref="entry-action",
        protection_action_ref="protection-action",
        fill_fact_ref="fill-1",
        fill_source_identity="trade-1:1",
        fill_quantity="0.01",
    )
    assert protection.trigger_price == "103"
    assert (tp1.trigger_price, tp2.trigger_price) == ("95.5", "91")
