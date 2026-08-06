from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from halpha.capital.models import AuthorityClass, EnvironmentKind
from halpha.planning.models import PlanActivation
from halpha.planning.order_policies import (
    FullFillLossBudgetSpec,
    InitialStopSpec,
    ProtectionPolicy,
    TakeProfitLadderSpec,
    TakeProfitLevel,
)
from halpha.planning.order_schedule import (
    AmountDistribution,
    EntryProgram,
    EntryProgramKind,
    InstrumentOrderRules,
    OrderScheduleSpec,
    PriceDistribution,
    SinglePrice,
    VenueOrderPolicy,
    VenueOrderType,
    compile_order_schedule,
)
from halpha.planning.registry import Direction
from halpha.planning.transitions import (
    proposed_direct_protection_from_fill,
    proposed_direct_protection_replacement,
    proposed_direct_take_profit_replacement,
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


def _budgeted_ladder_activation(direction: Direction) -> tuple[
    PlanActivation,
    ProtectionPolicy,
]:
    policy = ProtectionPolicy(
        initial_stop=InitialStopSpec(distance_bps="5000"),
        full_fill_loss_budget=FullFillLossBudgetSpec(
            entry_fee_bps="10",
            exit_fee_bps="20",
        ),
        take_profit_ladder=TakeProfitLadderSpec(
            levels=(TakeProfitLevel(trigger_r="0.5", quantity_fraction="1"),)
        ),
        time_exit_seconds=3_600,
    )
    spec = OrderScheduleSpec(
        entry_program=EntryProgram(kind=EntryProgramKind.PRICE_LADDER),
        price_distribution=PriceDistribution(
            lower_price="100",
            upper_price="150",
            level_count=2,
        ),
        amount_distribution=AmountDistribution(base_notional="150"),
        protection_policy=policy,
    )
    snapshot = compile_order_schedule(
        spec,
        InstrumentOrderRules(
            source="TEST",
            min_price="0.1",
            max_price="1000000",
            price_tick_size="0.1",
            limit_quantity_step="0.01",
            min_limit_quantity="0.01",
            max_limit_quantity="1000",
            market_quantity_step="0.01",
            min_market_quantity="0.01",
            max_market_quantity="1000",
            min_notional="5",
            source_cutoff="2026-07-17T00:00:00+00:00",
        ),
        venue_ref="BINANCE_USDM",
        instrument_ref="BTCUSDT-PERP",
        direction=direction,
        max_notional="300",
        schedule_ref="budgeted-ladder-version",
    )
    assert snapshot.valid
    activation = _activation(direction).model_copy(
        update={
            "decision_basis_ref": "DIRECT_EXECUTION@1",
            "plan_version_ref": snapshot.schedule_ref,
            "order_schedule_snapshot": snapshot,
        }
    )
    return activation, policy


def _projected_fill_loss(
    activation: PlanActivation,
    *,
    entry_fee_bps: str,
    exit_fee_bps: str,
) -> Decimal:
    state = activation.rule_state["direct_protection"]
    fills = tuple(state["fills"].values())
    quantity = sum(Decimal(item["fill_quantity"]) for item in fills)
    cost_basis = sum(
        Decimal(item["fill_price"]) * Decimal(item["fill_quantity"])
        for item in fills
    )
    stop = Decimal(state["aggregate_target"]["initial_stop_price"])
    exit_notional = quantity * stop
    gross_loss = (
        cost_basis - exit_notional
        if activation.direction is Direction.LONG
        else exit_notional - cost_basis
    )
    return (
        gross_loss
        + cost_basis * Decimal(entry_fee_bps) / Decimal(10_000)
        + exit_notional * Decimal(exit_fee_bps) / Decimal(10_000)
    )


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


@pytest.mark.parametrize(
    ("direction", "fills", "outside_boundary"),
    (
        (Direction.LONG, (("150", "1"), ("100", "1.5")), Decimal("100")),
        (Direction.SHORT, (("100", "1.5"), ("150", "1")), Decimal("150")),
    ),
)
def test_budgeted_ladder_rebalances_all_fills_without_exceeding_frozen_loss(
    direction: Direction,
    fills: tuple[tuple[str, str], ...],
    outside_boundary: Decimal,
) -> None:
    activation, policy = _budgeted_ladder_activation(direction)
    maximum_loss = Decimal(
        activation.order_schedule_snapshot.full_fill_protection_estimate.maximum_projected_loss
    )
    stops: list[Decimal] = []

    for index, (fill_price, fill_quantity) in enumerate(fills, start=1):
        activation = record_direct_fill(
            activation,
            entry_action_ref=f"entry-action-{index}",
            fill_fact_ref=f"fill-{index}",
            fill_price=fill_price,
            fill_quantity=fill_quantity,
            fill_time=NOW + timedelta(seconds=index),
            protection_policy=policy.model_dump(mode="json"),
            price_tick_size="0.1",
            quantity_step="0.01",
            observed_at=NOW + timedelta(seconds=index),
        )
        state = activation.rule_state["direct_protection"]
        stop = Decimal(state["aggregate_target"]["initial_stop_price"])
        stops.append(stop)
        assert all(
            item["targets"] == state["aggregate_target"]
            for item in state["fills"].values()
        )
        assert _projected_fill_loss(
            activation,
            entry_fee_bps="10",
            exit_fee_bps="20",
        ) <= maximum_loss
        if direction is Direction.LONG:
            assert stop < outside_boundary
        else:
            assert stop > outside_boundary

    # Adding the second tranche changes the aggregate average and may move the
    # stop away from the first-fill target; the absolute frozen loss cap is the
    # invariant, not monotonic stop movement during entry construction.
    assert stops[1] != stops[0]

    replacement = proposed_direct_protection_replacement(
        activation,
        predecessor_action_ref="protection-action-1",
        predecessor_trigger_price=str(stops[0]),
        entry_action_ref="entry-action-1",
        fill_fact_ref="fill-1",
        fill_source_identity="trade-1:1",
        fill_quantity=fills[0][1],
        target_trigger_price=str(stops[1]),
        step_index=2,
        replacement_kind="ENTRY_AGGREGATE_REBALANCE",
    )
    assert replacement.trigger_price == str(stops[1])
    assert replacement.execution_context["protection_replacement"] == {
        "step_index": 2,
        "kind": "ENTRY_AGGREGATE_REBALANCE",
        "predecessor_action_ref": "protection-action-1",
        "trigger_price": str(stops[1]),
    }
    with pytest.raises(ValueError, match="PROTECTION_AGGREGATE_TARGET_STALE"):
        proposed_direct_protection_replacement(
            activation,
            predecessor_action_ref="protection-action-1",
            predecessor_trigger_price=str(stops[0]),
            entry_action_ref="entry-action-1",
            fill_fact_ref="fill-1",
            fill_source_identity="trade-1:1",
            fill_quantity=fills[0][1],
            target_trigger_price=str(stops[0]),
            step_index=2,
            replacement_kind="ENTRY_AGGREGATE_REBALANCE",
        )

    aggregate_take_profit = activation.rule_state["direct_protection"][
        "aggregate_target"
    ]["take_profit_prices"][0]
    take_profit_replacement = proposed_direct_take_profit_replacement(
        activation,
        predecessor_action_ref="take-profit-action-1",
        protection_action_ref="protection-action-1",
        entry_action_ref="entry-action-1",
        fill_fact_ref="fill-1",
        fill_source_identity="trade-1:1",
        level_index=0,
        remaining_quantity=fills[0][1],
        target_trigger_price=aggregate_take_profit,
        aggregate_revision=2,
        valid_until=NOW + timedelta(hours=1),
    )
    assert take_profit_replacement.trigger_price == aggregate_take_profit
    assert take_profit_replacement.execution_context["take_profit_replacement"] == {
        "aggregate_revision": 2,
        "predecessor_action_ref": "take-profit-action-1",
        "trigger_price": aggregate_take_profit,
        "remaining_quantity": fills[0][1],
    }
    with pytest.raises(ValueError, match="TAKE_PROFIT_AGGREGATE_TARGET_STALE"):
        proposed_direct_take_profit_replacement(
            activation,
            predecessor_action_ref="take-profit-action-1",
            protection_action_ref="protection-action-1",
            entry_action_ref="entry-action-1",
            fill_fact_ref="fill-1",
            fill_source_identity="trade-1:1",
            level_index=0,
            remaining_quantity=fills[0][1],
            target_trigger_price=aggregate_take_profit,
            aggregate_revision=1,
            valid_until=None,
        )

    replay = record_direct_fill(
        activation,
        entry_action_ref="entry-action-2",
        fill_fact_ref="fill-2",
        fill_price=fills[1][0],
        fill_quantity=fills[1][1],
        fill_time=NOW + timedelta(seconds=2),
        protection_policy=policy.model_dump(mode="json"),
        price_tick_size="0.1",
        quantity_step="0.01",
        observed_at=NOW + timedelta(minutes=1),
    )
    assert replay is activation


def test_one_time_entry_uses_actual_fill_and_budget_without_ladder_boundary_clamp() -> None:
    policy = ProtectionPolicy(
        initial_stop=InitialStopSpec(distance_bps="100"),
        full_fill_loss_budget=FullFillLossBudgetSpec(
            entry_fee_bps="10",
            exit_fee_bps="20",
        ),
        time_exit_seconds=3_600,
    )
    spec = OrderScheduleSpec(
        entry_program=EntryProgram(kind=EntryProgramKind.ONE_TIME),
        price_distribution=SinglePrice(),
        amount_distribution=AmountDistribution(base_notional="200"),
        venue_policy=VenueOrderPolicy(
            order_type=VenueOrderType.MARKET,
            time_in_force=None,
        ),
        protection_policy=policy,
    )
    snapshot = compile_order_schedule(
        spec,
        InstrumentOrderRules(
            source="TEST",
            min_price="0.1",
            max_price="1000000",
            price_tick_size="0.1",
            limit_quantity_step="0.01",
            min_limit_quantity="0.01",
            max_limit_quantity="1000",
            market_quantity_step="0.01",
            min_market_quantity="0.01",
            max_market_quantity="1000",
            min_notional="5",
            source_cutoff="2026-07-17T00:00:00+00:00",
        ),
        venue_ref="BINANCE_USDM",
        instrument_ref="BTCUSDT-PERP",
        direction=Direction.LONG,
        max_notional="200",
        schedule_ref="budgeted-one-time-version",
        reference_price="100",
    )
    assert snapshot.valid
    activation = _activation(Direction.LONG).model_copy(
        update={
            "decision_basis_ref": "DIRECT_EXECUTION@1",
            "plan_version_ref": snapshot.schedule_ref,
            "order_schedule_snapshot": snapshot,
        }
    )

    activation = record_direct_fill(
        activation,
        entry_action_ref="entry-action",
        fill_fact_ref="fill-fact",
        fill_price="110",
        fill_quantity="2",
        fill_time=NOW,
        protection_policy=policy.model_dump(mode="json"),
        price_tick_size="0.1",
        quantity_step="0.01",
        observed_at=NOW,
    )

    stop = Decimal(
        activation.rule_state["direct_protection"]["aggregate_target"][
            "initial_stop_price"
        ]
    )
    assert Decimal("100") < stop < Decimal("110")
    assert _projected_fill_loss(
        activation,
        entry_fee_bps="10",
        exit_fee_bps="20",
    ) <= Decimal(snapshot.full_fill_protection_estimate.maximum_projected_loss)


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
    assert tuple(action.quantity for action in actions) == ("0.003", "0.002", "0.004")
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


def test_direct_take_profit_ladder_assigns_a_minimum_step_to_one_target() -> None:
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

    actions = proposed_direct_take_profits_from_fill(
        activation,
        entry_action_ref="entry-action-1",
        protection_action_ref="protection-action-1",
        fill_fact_ref="fill-1",
        fill_source_identity="trade-1:1",
    )

    assert len(actions) == 1
    assert actions[0].quantity == "0.001"
    assert actions[0].trigger_price == "102"
    assert actions[0].execution_context["direct_take_profit"]["level_index"] == 1
