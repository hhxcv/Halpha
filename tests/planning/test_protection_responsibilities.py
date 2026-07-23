from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from halpha.capital.models import AuthorityClass, EnvironmentKind
from halpha.planning.models import PlanActivation
from halpha.planning.order_policies import (
    InitialStopSpec,
    ProtectionPolicy,
    TakeProfitLadderSpec,
    TakeProfitLevel,
)
from halpha.planning.registry import Direction
from halpha.planning.transitions import (
    proposed_direct_protection_from_fill,
    proposed_direct_take_profits_from_fill,
    proposed_protection_from_fill,
    proposed_take_profits_from_fill,
    record_direct_fill,
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
        account_ref="demo-owner",
        instrument_ref="BTCUSDT-PERP",
        direction=direction,
        decision_basis_ref="ONE_SHOT_DONCHIAN_ATR_BREAKOUT@1.0.1",
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
        "entry_extension_boundary": "110",
        "sizing_taker_fee_rate": "0.0006",
        "sizing_effective_leverage": "5",
        "instrument_rules_digest": "b" * 64,
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


def test_direct_schedule_records_multiple_entry_actions_without_first_fill_conflict() -> None:
    policy = ProtectionPolicy(
        initial_stop=InitialStopSpec(distance_bps="100")
    ).model_dump(mode="json")
    first = record_direct_fill(
        _activation(Direction.LONG),
        entry_action_ref="entry-action-1",
        fill_fact_ref="fill-1",
        fill_price="100",
        fill_quantity="0.01",
        fill_time=NOW,
        protection_policy=policy,
        price_tick_size="0.1",
        quantity_step="0.001",
        observed_at=NOW,
    )
    second = record_direct_fill(
        first,
        entry_action_ref="entry-action-2",
        fill_fact_ref="fill-2",
        fill_price="110",
        fill_quantity="0.02",
        fill_time=NOW + timedelta(seconds=5),
        protection_policy=policy,
        price_tick_size="0.1",
        quantity_step="0.001",
        observed_at=NOW + timedelta(seconds=5),
    )

    fills = second.rule_state["direct_protection"]["fills"]
    assert set(fills) == {"fill-1", "fill-2"}
    assert fills["fill-1"]["targets"]["initial_stop_price"] == "99"
    assert fills["fill-2"]["targets"]["initial_stop_price"] == "108.9"
    assert second.rule_state["direct_protection"]["anchor_fill_ref"] == "fill-1"

    protection = proposed_direct_protection_from_fill(
        second,
        entry_action_ref="entry-action-2",
        fill_fact_ref="fill-2",
        fill_source_identity="trade-2:1",
    )
    assert protection.quantity == "0.02"
    assert protection.trigger_price == "108.9"
    assert protection.execution_context["trigger_source"] == "MARK_PRICE"
    assert proposed_direct_take_profits_from_fill(
        second,
        entry_action_ref="entry-action-2",
        protection_action_ref="protection-action-2",
        fill_fact_ref="fill-2",
        fill_source_identity="trade-2:1",
    ) == ()


def test_direct_market_fill_preserves_unprotectable_price_for_gap_recovery() -> None:
    policy = ProtectionPolicy(
        initial_stop=InitialStopSpec(distance_bps="1"),
        take_profit_ladder=TakeProfitLadderSpec(
            levels=(TakeProfitLevel(trigger_r="1", quantity_fraction="1"),)
        ),
    ).model_dump(mode="json")

    activation = record_direct_fill(
        _activation(Direction.LONG),
        entry_action_ref="entry-action-1",
        fill_fact_ref="fill-invalid-target",
        fill_price="100",
        fill_quantity="0.01",
        fill_time=NOW,
        protection_policy=policy,
        price_tick_size="1",
        quantity_step="0.001",
        observed_at=NOW,
    )

    fill = activation.rule_state["direct_protection"]["fills"][
        "fill-invalid-target"
    ]
    assert activation.has_entry_fill
    assert fill["targets"] is None
    assert fill["protection_error"] == "PROTECTION_PRICE_INVALID"
    with pytest.raises(ValueError, match="PROTECTION_PRICE_INVALID"):
        proposed_direct_protection_from_fill(
            activation,
            entry_action_ref="entry-action-1",
            fill_fact_ref="fill-invalid-target",
            fill_source_identity="trade-invalid:1",
        )


def test_direct_take_profit_ladder_uses_persisted_targets_and_step_rounded_quantities() -> None:
    policy = ProtectionPolicy(
        initial_stop=InitialStopSpec(distance_bps="100"),
        take_profit_ladder=TakeProfitLadderSpec(
            levels=(
                TakeProfitLevel(trigger_r="1", quantity_fraction="0.25"),
                TakeProfitLevel(trigger_r="2", quantity_fraction="0.25"),
                TakeProfitLevel(trigger_r="4", quantity_fraction="0.4"),
            )
        ),
        time_exit_seconds=600,
    ).model_dump(mode="json")
    activation = record_direct_fill(
        _activation(Direction.LONG),
        entry_action_ref="entry-action-1",
        fill_fact_ref="fill-1",
        fill_price="100",
        fill_quantity="0.011",
        fill_time=NOW,
        protection_policy=policy,
        price_tick_size="0.1",
        quantity_step="0.001",
        observed_at=NOW,
    )

    actions = proposed_direct_take_profits_from_fill(
        activation,
        entry_action_ref="entry-action-1",
        protection_action_ref="protection-action-1",
        fill_fact_ref="fill-1",
        fill_source_identity="trade-1:1",
    )
    replay = proposed_direct_take_profits_from_fill(
        activation,
        entry_action_ref="entry-action-1",
        protection_action_ref="protection-action-1",
        fill_fact_ref="fill-1",
        fill_source_identity="trade-1:1",
    )

    assert tuple(action.action_profile for action in actions) == (
        "TAKE_PROFIT_1",
        "TAKE_PROFIT_2",
        "TAKE_PROFIT_2",
    )
    assert tuple(action.quantity for action in actions) == ("0.002", "0.002", "0.004")
    assert tuple(action.trigger_price for action in actions) == ("101", "102", "104")
    assert all(action.reduce_only for action in actions)
    assert all(action.valid_until == NOW + timedelta(seconds=600) for action in actions)
    assert tuple(action.causation_ref for action in replay) == tuple(
        action.causation_ref for action in actions
    )
    assert len({action.causation_ref for action in actions}) == len(actions)
    assert actions[2].execution_context["direct_take_profit"] == {
        "level_index": 2,
        "trigger_r": "4",
        "quantity_fraction": "0.4",
        "trigger_price": "104",
        "quantity": "0.004",
    }


def test_direct_take_profit_ladder_reverses_and_rounds_short_targets_conservatively() -> None:
    policy = ProtectionPolicy(
        initial_stop=InitialStopSpec(distance_bps="100"),
        take_profit_ladder=TakeProfitLadderSpec(
            levels=(
                TakeProfitLevel(trigger_r="1.25", quantity_fraction="0.5"),
                TakeProfitLevel(trigger_r="2.25", quantity_fraction="0.5"),
            )
        ),
    ).model_dump(mode="json")
    activation = record_direct_fill(
        _activation(Direction.SHORT),
        entry_action_ref="entry-action-1",
        fill_fact_ref="fill-1",
        fill_price="100",
        fill_quantity="0.01",
        fill_time=NOW,
        protection_policy=policy,
        price_tick_size="0.1",
        quantity_step="0.001",
        observed_at=NOW,
    )

    actions = proposed_direct_take_profits_from_fill(
        activation,
        entry_action_ref="entry-action-1",
        protection_action_ref="protection-action-1",
        fill_fact_ref="fill-1",
        fill_source_identity="trade-1:1",
    )

    assert tuple(action.quantity for action in actions) == ("0.005", "0.005")
    assert tuple(action.trigger_price for action in actions) == ("98.8", "97.8")
    assert all(action.valid_until is None for action in actions)


def test_direct_take_profit_ladder_rejects_a_level_rounded_to_zero() -> None:
    policy = ProtectionPolicy(
        initial_stop=InitialStopSpec(distance_bps="100"),
        take_profit_ladder=TakeProfitLadderSpec(
            levels=(
                TakeProfitLevel(trigger_r="1", quantity_fraction="0.1"),
                TakeProfitLevel(trigger_r="2", quantity_fraction="0.9"),
            )
        ),
    ).model_dump(mode="json")
    activation = record_direct_fill(
        _activation(),
        entry_action_ref="entry-action-1",
        fill_fact_ref="fill-1",
        fill_price="100",
        fill_quantity="0.001",
        fill_time=NOW,
        protection_policy=policy,
        price_tick_size="0.1",
        quantity_step="0.001",
        observed_at=NOW,
    )

    with pytest.raises(ValueError, match="TAKE_PROFIT_SPLIT_INVALID"):
        proposed_direct_take_profits_from_fill(
            activation,
            entry_action_ref="entry-action-1",
            protection_action_ref="protection-action-1",
            fill_fact_ref="fill-1",
            fill_source_identity="trade-1:1",
        )
