from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from halpha.planning.order_schedule import (
    AmountDistribution,
    AmountDistributionMode,
    DistributionDirection,
    InstrumentOrderRules,
    OrderScheduleSpec,
    PriceDistribution,
    PriceSpacingMode,
    ScheduleSubmissionMode,
    ScheduleSubmissionOrder,
    SinglePrice,
    VenueOrderPolicy,
    VenueOrderType,
    VenueTimeInForce,
    compile_order_schedule,
    direct_allowed_action_profiles,
    validate_current_order_schedule_support,
    validate_direct_execution_schedule,
    validate_order_schedule_snapshot,
)
from halpha.planning.order_policies import (
    CancelOnShockRule,
    ConditionGroup,
    ConditionOperator,
    DecisionBasisReadyCondition,
    InitialStopSpec,
    MarkPriceCondition,
    NumericComparator,
    ProfitRCondition,
    ProtectionStep,
    ProtectionPolicy,
    SteppedProtectionRule,
    TakeProfitLadderSpec,
    TakeProfitLevel,
)
from halpha.planning.registry import DecisionBasisKind, Direction


def _rules(**updates: str) -> InstrumentOrderRules:
    values = {
        "source": "BINANCE_DEMO_EXCHANGE_INFO",
        "min_price": "0.1",
        "max_price": "1000000",
        "price_tick_size": "0.1",
        "limit_quantity_step": "0.01",
        "min_limit_quantity": "0.01",
        "max_limit_quantity": "1000",
        "market_quantity_step": "0.1",
        "min_market_quantity": "0.1",
        "max_market_quantity": "100",
        "min_notional": "5",
        "source_cutoff": "2026-07-23T00:00:00+00:00",
        **updates,
    }
    return InstrumentOrderRules(**values)


def _compile(spec: OrderScheduleSpec, **updates: str):
    return compile_order_schedule(
        spec,
        _rules(),
        venue_ref=updates.pop("venue_ref", "BINANCE_USDM"),
        instrument_ref=updates.pop("instrument_ref", "BTCUSDT-PERP"),
        direction=Direction(updates.pop("direction", "LONG")),
        max_notional=updates.pop("max_notional", "1000"),
        schedule_ref=updates.pop("schedule_ref", "schedule-1"),
        reference_price=updates.pop("reference_price", None),
    )


def _legacy_v2_snapshot():
    preview = _compile(
        OrderScheduleSpec(
            price_distribution=SinglePrice(limit_price="10"),
            amount_distribution=AmountDistribution(base_notional="20"),
        )
    )
    return preview.model_copy(
        update={
            "compiler_version": "2",
            "instrument_rules_digest": (
                "665c5638adafe632d2f124c425920f89"
                "b34981d63473eab92afd3c409683cefa"
            ),
            "schedule_digest": (
                "cbd28fe2cc4fee9be5fec618ff6702b8"
                "fa98bf5481936c1392813517e797a816"
            ),
        }
    )


def _protected_single_schedule(**updates: object) -> OrderScheduleSpec:
    values: dict[str, object] = {
        "price_distribution": SinglePrice(limit_price="100"),
        "amount_distribution": AmountDistribution(base_notional="20"),
        "protection_policy": ProtectionPolicy(
            initial_stop=InitialStopSpec(distance_bps="100")
        ),
        **updates,
    }
    return OrderScheduleSpec(**values)


def test_current_runtime_rejects_strategy_schedule_instead_of_silently_ignoring_it() -> None:
    with pytest.raises(ValueError, match="STRATEGY_ORDER_SCHEDULE_NOT_SUPPORTED"):
        validate_current_order_schedule_support(
            DecisionBasisKind.STRATEGY_SIGNAL,
            _protected_single_schedule(),
        )


def test_current_direct_catalog_rejects_unverified_preprotected_parallel() -> None:
    with pytest.raises(ValueError, match="PREPROTECTED_PARALLEL_NOT_VERIFIED"):
        validate_current_order_schedule_support(
            DecisionBasisKind.DIRECT_EXECUTION,
            _protected_single_schedule(
                submission_mode=ScheduleSubmissionMode.PREPROTECTED_PARALLEL,
            ),
        )


@pytest.mark.parametrize(
    "levels",
    (
        (TakeProfitLevel(trigger_r="1", quantity_fraction="0.5"),),
        (
            TakeProfitLevel(trigger_r="1", quantity_fraction="0.5"),
            TakeProfitLevel(trigger_r="2", quantity_fraction="0.5"),
        ),
    ),
)
def test_current_direct_catalog_rejects_unverified_take_profit_splits(
    levels: tuple[TakeProfitLevel, ...],
) -> None:
    spec = _protected_single_schedule(
        protection_policy=ProtectionPolicy(
            initial_stop=InitialStopSpec(distance_bps="100"),
            take_profit_ladder=TakeProfitLadderSpec(levels=levels),
        )
    )

    with pytest.raises(
        ValueError,
        match="DIRECT_EXECUTION_TAKE_PROFIT_SPLIT_NOT_VERIFIED",
    ):
        validate_direct_execution_schedule(spec)


def test_current_direct_catalog_accepts_one_full_take_profit_target() -> None:
    spec = _protected_single_schedule(
        protection_policy=ProtectionPolicy(
            initial_stop=InitialStopSpec(distance_bps="100"),
            take_profit_ladder=TakeProfitLadderSpec(
                levels=(TakeProfitLevel(trigger_r="1", quantity_fraction="1"),)
            ),
        )
    )

    validate_direct_execution_schedule(spec)

    assert direct_allowed_action_profiles(spec) == frozenset(
        {
            "ENTRY_LIMIT",
            "PROTECTIVE_STOP_REDUCE_ONLY",
            "TAKE_PROFIT_1",
            "CANCEL_ORDER",
            "REDUCE_OR_CLOSE_MARKET",
        }
    )


@pytest.mark.parametrize("direction", (Direction.LONG, Direction.SHORT))
def test_explicit_entry_prices_preflight_fill_relative_protection(
    direction: Direction,
) -> None:
    spec = _protected_single_schedule(
        protection_policy=ProtectionPolicy(
            initial_stop=InitialStopSpec(distance_bps="1"),
            take_profit_ladder=TakeProfitLadderSpec(
                levels=(TakeProfitLevel(trigger_r="1", quantity_fraction="1"),)
            ),
        )
    )

    preview = compile_order_schedule(
        spec,
        _rules(price_tick_size="1"),
        venue_ref="BINANCE_USDM",
        instrument_ref="BTCUSDT-PERP",
        direction=direction,
        max_notional="100",
        schedule_ref="protection-price-preflight",
    )

    assert not preview.valid
    assert [(issue.code, issue.field, issue.leg_index) for issue in preview.issues] == [
        ("PROTECTION_PRICE_INVALID", "protection_policy", 0)
    ]


def test_market_entry_defers_fill_relative_protection_to_runtime() -> None:
    spec = _protected_single_schedule(
        price_distribution=SinglePrice(),
        venue_policy=VenueOrderPolicy(
            order_type=VenueOrderType.MARKET,
            time_in_force=None,
        ),
        protection_policy=ProtectionPolicy(
            initial_stop=InitialStopSpec(distance_bps="1"),
            take_profit_ladder=TakeProfitLadderSpec(
                levels=(TakeProfitLevel(trigger_r="1", quantity_fraction="1"),)
            ),
        ),
    )

    preview = compile_order_schedule(
        spec,
        _rules(price_tick_size="1"),
        venue_ref="BINANCE_USDM",
        instrument_ref="BTCUSDT-PERP",
        direction=Direction.LONG,
        max_notional="100",
        schedule_ref="market-protection-runtime-check",
        reference_price="100",
    )

    assert preview.valid


def test_direct_any_cannot_mix_always_true_readiness_with_market_conditions() -> None:
    spec = _protected_single_schedule(
        entry_conditions=ConditionGroup(
            operator=ConditionOperator.ANY,
            items=(
                DecisionBasisReadyCondition(),
                MarkPriceCondition(comparator=NumericComparator.GTE, price="100"),
            ),
        )
    )

    with pytest.raises(
        ValueError,
        match="DIRECT_EXECUTION_ANY_IMMEDIATE_CONDITION_CONFLICT",
    ):
        validate_current_order_schedule_support(
            DecisionBasisKind.DIRECT_EXECUTION,
            spec,
        )


def test_direct_any_with_only_market_conditions_remains_meaningful() -> None:
    spec = _protected_single_schedule(
        entry_conditions=ConditionGroup(
            operator=ConditionOperator.ANY,
            items=(
                MarkPriceCondition(comparator=NumericComparator.GTE, price="100"),
            ),
        )
    )

    validate_current_order_schedule_support(
        DecisionBasisKind.DIRECT_EXECUTION,
        spec,
    )


def test_equal_prices_and_fixed_amounts_match_user_example() -> None:
    preview = _compile(
        OrderScheduleSpec(
            price_distribution=PriceDistribution(
                lower_price="10",
                upper_price="30",
                level_count=5,
            ),
            amount_distribution=AmountDistribution(
                mode=AmountDistributionMode.FIXED,
                base_notional="10",
            ),
        )
    )

    assert preview.valid
    assert [leg.price for leg in preview.legs] == ["10", "15", "20", "25", "30"]
    assert [leg.requested_notional for leg in preview.legs] == ["10"] * 5
    assert Decimal(preview.requested_total_notional) == Decimal("50")
    assert Decimal(preview.effective_total_notional) <= Decimal("50")


@pytest.mark.parametrize(
    ("distribution", "expected"),
    [
        (
            AmountDistribution(
                mode=AmountDistributionMode.LINEAR,
                base_notional="10",
                linear_step="10",
            ),
            ["10", "20", "30", "40"],
        ),
        (
            AmountDistribution(
                mode=AmountDistributionMode.EXPONENTIAL,
                base_notional="10",
                exponential_ratio="2",
            ),
            ["10", "20", "40", "80"],
        ),
    ],
)
def test_linear_and_exponential_amounts(
    distribution: AmountDistribution,
    expected: list[str],
) -> None:
    preview = _compile(
        OrderScheduleSpec(
            price_distribution=PriceDistribution(
                lower_price="10",
                upper_price="40",
                level_count=4,
            ),
            amount_distribution=distribution,
        )
    )

    assert preview.valid
    assert [leg.requested_notional for leg in preview.legs] == expected


def test_custom_gap_weights_and_reverse_amount_direction() -> None:
    preview = _compile(
        OrderScheduleSpec(
            price_distribution=PriceDistribution(
                lower_price="10",
                upper_price="25",
                level_count=6,
                spacing_mode=PriceSpacingMode.CUSTOM_WEIGHTS,
                custom_gap_weights=("5", "4", "3", "2", "1"),
            ),
            amount_distribution=AmountDistribution(
                mode=AmountDistributionMode.LINEAR,
                direction=DistributionDirection.HIGH_TO_LOW,
                base_notional="10",
                linear_step="10",
            ),
        )
    )

    assert preview.valid
    assert [leg.price for leg in preview.legs] == ["10", "15", "19", "22", "24", "25"]
    assert [leg.requested_notional for leg in preview.legs] == [
        "60",
        "50",
        "40",
        "30",
        "20",
        "10",
    ]


def test_linear_gap_weights_accept_a_decreasing_positive_sequence() -> None:
    preview = _compile(
        OrderScheduleSpec(
            price_distribution=PriceDistribution(
                lower_price="10",
                upper_price="25",
                level_count=6,
                spacing_mode=PriceSpacingMode.LINEAR,
                linear_start_weight="5",
                linear_step="-1",
            ),
            amount_distribution=AmountDistribution(base_notional="20"),
        )
    )

    assert preview.valid
    assert [leg.price for leg in preview.legs] == ["10", "15", "19", "22", "24", "25"]


def test_short_prices_round_away_from_a_more_aggressive_price() -> None:
    spec = OrderScheduleSpec(
        price_distribution=PriceDistribution(
            lower_price="10.01",
            upper_price="10.99",
            level_count=2,
        ),
        amount_distribution=AmountDistribution(base_notional="20"),
    )

    long_preview = _compile(spec, direction="LONG")
    short_preview = _compile(spec, direction="SHORT")

    assert [leg.price for leg in long_preview.legs] == ["10", "10.9"]
    assert [leg.price for leg in short_preview.legs] == ["10.1", "11"]


def test_tick_collision_rejects_the_entire_schedule() -> None:
    preview = compile_order_schedule(
        OrderScheduleSpec(
            price_distribution=PriceDistribution(
                lower_price="10.01",
                upper_price="10.19",
                level_count=3,
            ),
            amount_distribution=AmountDistribution(base_notional="20"),
        ),
        _rules(price_tick_size="0.1"),
        venue_ref="BINANCE_USDM",
        instrument_ref="BTCUSDT-PERP",
        direction=Direction.LONG,
        max_notional="100",
        schedule_ref="collision",
    )

    assert not preview.valid
    assert preview.legs == ()
    assert len(preview.normalized_legs) == 3
    assert {issue.code for issue in preview.issues} == {
        "ORDER_SCHEDULE_PRICE_COLLISION"
    }


def test_minimum_notional_and_total_plan_limit_are_reported_together() -> None:
    preview = compile_order_schedule(
        OrderScheduleSpec(
            price_distribution=PriceDistribution(
                lower_price="10",
                upper_price="20",
                level_count=2,
            ),
            amount_distribution=AmountDistribution(base_notional="6"),
        ),
        _rules(min_notional="8"),
        venue_ref="BINANCE_USDM",
        instrument_ref="BTCUSDT-PERP",
        direction=Direction.LONG,
        max_notional="10",
        schedule_ref="invalid",
    )

    codes = [issue.code for issue in preview.issues]
    assert "ORDER_SCHEDULE_TOTAL_EXCEEDS_PLAN_LIMIT" in codes
    assert codes.count("ORDER_SCHEDULE_NOTIONAL_BELOW_MINIMUM") == 2
    assert preview.legs == ()


def test_price_outside_venue_filter_rejects_the_entire_schedule() -> None:
    preview = compile_order_schedule(
        OrderScheduleSpec(
            price_distribution=PriceDistribution(
                lower_price="10",
                upper_price="20",
                level_count=2,
            ),
            amount_distribution=AmountDistribution(base_notional="20"),
        ),
        _rules(min_price="15"),
        venue_ref="BINANCE_USDM",
        instrument_ref="BTCUSDT-PERP",
        direction=Direction.LONG,
        max_notional="100",
        schedule_ref="invalid-price",
    )

    assert not preview.valid
    assert {issue.code for issue in preview.issues} == {
        "ORDER_SCHEDULE_PRICE_OUTSIDE_VENUE_LIMIT"
    }


def test_cutoff_does_not_change_executable_schedule_or_rules_digest() -> None:
    spec = OrderScheduleSpec(
        price_distribution=PriceDistribution(
            lower_price="10",
            upper_price="20",
            level_count=3,
            spacing_mode=PriceSpacingMode.LINEAR,
        ),
        amount_distribution=AmountDistribution(
            mode=AmountDistributionMode.EXPONENTIAL,
            base_notional="10",
            exponential_ratio="1.5",
        ),
    )
    first = compile_order_schedule(
        spec,
        _rules(source_cutoff="2026-07-23T00:00:00+00:00"),
        venue_ref="BINANCE_USDM",
        instrument_ref="BTCUSDT-PERP",
        direction=Direction.LONG,
        max_notional="100",
        schedule_ref="stable",
    )
    second = compile_order_schedule(
        spec,
        _rules(source_cutoff="2026-07-23T00:01:00+00:00"),
        venue_ref="BINANCE_USDM",
        instrument_ref="BTCUSDT-PERP",
        direction=Direction.LONG,
        max_notional="100",
        schedule_ref="stable",
    )

    assert first.valid and second.valid
    assert first.instrument_rules_digest == second.instrument_rules_digest
    assert first.schedule_digest == second.schedule_digest
    assert first.instrument_rules == _rules(source_cutoff="2026-07-23T00:00:00+00:00")
    assert second.instrument_rules == _rules(source_cutoff="2026-07-23T00:01:00+00:00")
    assert first.compiler_version == "3"


def test_venue_policy_conflicts_are_rejected() -> None:
    with pytest.raises(ValidationError, match="POST_ONLY_TIME_IN_FORCE_CONFLICT"):
        VenueOrderPolicy(time_in_force=VenueTimeInForce.IOC, post_only=True)
    with pytest.raises(ValidationError, match="POST_ONLY_PRICE_MATCH_CONFLICT"):
        VenueOrderPolicy(post_only=True, price_match="QUEUE")
    with pytest.raises(ValidationError, match="POST_ONLY_TIME_IN_FORCE_CONFLICT"):
        VenueOrderPolicy(
            time_in_force=VenueTimeInForce.GTD,
            post_only=True,
            expire_at=datetime.now(UTC) + timedelta(hours=1),
        )
    with pytest.raises(ValidationError, match="DISPLAY_QUANTITY_NOT_DEMO_VERIFIED"):
        VenueOrderPolicy(display_quantity="0.1")


def test_single_limit_and_price_match_use_the_same_compiler() -> None:
    explicit = _compile(
        OrderScheduleSpec(
            price_distribution=SinglePrice(limit_price="10.09"),
            amount_distribution=AmountDistribution(base_notional="20"),
        )
    )
    price_match = compile_order_schedule(
        OrderScheduleSpec(
            price_distribution=SinglePrice(),
            amount_distribution=AmountDistribution(base_notional="20"),
            venue_policy=VenueOrderPolicy(price_match="QUEUE"),
        ),
        _rules(),
        venue_ref="BINANCE_USDM",
        instrument_ref="BTCUSDT-PERP",
        direction=Direction.LONG,
        max_notional="100",
        schedule_ref="single-price-match",
        reference_price="10.5",
    )

    assert explicit.valid
    assert explicit.legs[0].price == "10"
    assert explicit.legs[0].sizing_price == "10"
    assert price_match.valid
    assert price_match.legs[0].price is None
    assert price_match.legs[0].sizing_price == "10.5"


def test_single_market_uses_market_quantity_rules_and_requires_reference() -> None:
    spec = OrderScheduleSpec(
        price_distribution=SinglePrice(),
        amount_distribution=AmountDistribution(base_notional="20"),
        venue_policy=VenueOrderPolicy(
            order_type=VenueOrderType.MARKET,
            time_in_force=None,
        ),
    )

    missing = _compile(spec)
    preview = compile_order_schedule(
        spec,
        _rules(),
        venue_ref="BINANCE_USDM",
        instrument_ref="BTCUSDT-PERP",
        direction=Direction.LONG,
        max_notional="100",
        schedule_ref="single-market",
        reference_price="30",
    )

    assert not missing.valid
    assert {issue.code for issue in missing.issues} == {
        "ORDER_SCHEDULE_REFERENCE_PRICE_REQUIRED"
    }
    assert preview.valid
    assert preview.legs[0].price is None
    assert preview.legs[0].quantity == "0.6"


def test_schedule_content_digest_is_independent_of_schedule_identity() -> None:
    spec = OrderScheduleSpec(
        price_distribution=SinglePrice(limit_price="10"),
        amount_distribution=AmountDistribution(base_notional="20"),
    )

    first = _compile(spec, schedule_ref="first")
    second = _compile(spec, schedule_ref="second")

    assert first.schedule_ref != second.schedule_ref
    assert first.schedule_digest == second.schedule_digest


def test_valid_schedule_snapshot_is_self_contained_and_verifiable() -> None:
    spec = OrderScheduleSpec(
        price_distribution=SinglePrice(limit_price="10"),
        amount_distribution=AmountDistribution(base_notional="20"),
        venue_policy=VenueOrderPolicy(post_only=True),
    )
    preview = _compile(spec)

    validate_order_schedule_snapshot(preview)

    assert preview.schedule_spec == spec
    assert preview.schedule_spec.venue_policy.post_only is True
    assert preview.preprotected_parallel_supported is False


def test_legacy_v2_hybrid_snapshot_remains_verifiable() -> None:
    validate_order_schedule_snapshot(_legacy_v2_snapshot())


def test_legacy_v2_snapshot_rejects_cutoff_tampering_with_retained_digests() -> None:
    legacy = _legacy_v2_snapshot()
    changed_cutoff = "2026-07-23T00:01:00+00:00"
    tampered = legacy.model_copy(
        update={
            "instrument_rules": legacy.instrument_rules.model_copy(
                update={"source_cutoff": changed_cutoff}
            ),
            "source_cutoff": changed_cutoff,
        }
    )

    with pytest.raises(ValueError, match="ORDER_SCHEDULE_SNAPSHOT_CORRUPT"):
        validate_order_schedule_snapshot(tampered)


def test_legacy_v2_snapshot_rejects_leg_tampering_with_retained_digests() -> None:
    legacy = _legacy_v2_snapshot()
    changed_leg = legacy.legs[0].model_copy(update={"quantity": "999"})
    tampered = legacy.model_copy(
        update={"legs": (changed_leg,), "normalized_legs": (changed_leg,)}
    )

    with pytest.raises(ValueError, match="ORDER_SCHEDULE_SNAPSHOT_CORRUPT"):
        validate_order_schedule_snapshot(tampered)


def test_snapshot_rejects_an_unknown_compiler_version() -> None:
    preview = _compile(
        OrderScheduleSpec(
            price_distribution=SinglePrice(limit_price="10"),
            amount_distribution=AmountDistribution(base_notional="20"),
        )
    )

    with pytest.raises(ValueError, match="ORDER_SCHEDULE_COMPILER_UNSUPPORTED"):
        validate_order_schedule_snapshot(
            preview.model_copy(update={"compiler_version": "1"})
        )


def test_schedule_snapshot_rejects_leg_tampering_even_when_digest_fields_are_retained() -> None:
    preview = _compile(
        OrderScheduleSpec(
            price_distribution=SinglePrice(limit_price="10"),
            amount_distribution=AmountDistribution(base_notional="20"),
        )
    )
    changed_leg = preview.legs[0].model_copy(update={"quantity": "999"})
    tampered = preview.model_copy(
        update={"legs": (changed_leg,), "normalized_legs": (changed_leg,)}
    )

    with pytest.raises(ValueError, match="ORDER_SCHEDULE_SNAPSHOT_CORRUPT"):
        validate_order_schedule_snapshot(tampered)


def test_irrelevant_default_fields_and_reference_do_not_change_ladder_digest() -> None:
    first = OrderScheduleSpec(
        price_distribution=PriceDistribution(
            lower_price="10",
            upper_price="20",
            level_count=2,
            geometric_ratio="2",
        ),
        amount_distribution=AmountDistribution(
            mode=AmountDistributionMode.FIXED,
            base_notional="20",
            exponential_ratio="2",
        ),
    )
    second = OrderScheduleSpec(
        price_distribution=PriceDistribution(
            lower_price="10",
            upper_price="20",
            level_count=2,
            geometric_ratio="3",
        ),
        amount_distribution=AmountDistribution(
            mode=AmountDistributionMode.FIXED,
            base_notional="20",
            exponential_ratio="3",
        ),
    )

    plain = _compile(first)
    with_irrelevant_values = _compile(second, reference_price="123")

    assert plain.schedule_digest == with_irrelevant_values.schedule_digest


def test_decimal_and_ratio_inputs_are_bounded_before_distribution_math() -> None:
    with pytest.raises(ValidationError, match="ORDER_SCHEDULE_PRICE_INVALID"):
        SinglePrice(limit_price="1e1000")
    with pytest.raises(ValidationError, match="ORDER_SCHEDULE_EXPONENTIAL_RATIO_INVALID"):
        AmountDistribution(
            mode=AmountDistributionMode.EXPONENTIAL,
            exponential_ratio="101",
        )


def test_gtd_requires_more_than_ten_minutes_from_rules_cutoff() -> None:
    cutoff = datetime(2026, 7, 23, tzinfo=UTC)
    spec = OrderScheduleSpec(
        price_distribution=PriceDistribution(
            lower_price="10",
            upper_price="20",
            level_count=2,
        ),
        amount_distribution=AmountDistribution(base_notional="20"),
        venue_policy=VenueOrderPolicy(
            time_in_force=VenueTimeInForce.GTD,
            expire_at=cutoff + timedelta(seconds=600),
        ),
    )

    preview = compile_order_schedule(
        spec,
        _rules(source_cutoff=cutoff.isoformat()),
        venue_ref="BINANCE_USDM",
        instrument_ref="BTCUSDT-PERP",
        direction=Direction.LONG,
        max_notional="100",
        schedule_ref="gtd-too-soon",
    )

    assert not preview.valid
    assert {issue.code for issue in preview.issues} == {"GTD_EXPIRY_TOO_SOON"}


def test_preprotected_parallel_requires_an_explicit_verified_capability() -> None:
    spec = OrderScheduleSpec(
        price_distribution=PriceDistribution(
            lower_price="10",
            upper_price="20",
            level_count=2,
        ),
        amount_distribution=AmountDistribution(base_notional="20"),
        submission_mode=ScheduleSubmissionMode.PREPROTECTED_PARALLEL,
        protection_policy=ProtectionPolicy(
            initial_stop=InitialStopSpec(distance_bps="100"),
        ),
    )

    blocked = _compile(spec)
    verified = compile_order_schedule(
        spec,
        _rules(),
        venue_ref="BINANCE_USDM",
        instrument_ref="BTCUSDT-PERP",
        direction=Direction.LONG,
        max_notional="100",
        schedule_ref="parallel",
        preprotected_parallel_supported=True,
    )

    assert not blocked.valid
    assert {issue.code for issue in blocked.issues} == {
        "PREPROTECTED_PARALLEL_NOT_VERIFIED"
    }
    assert verified.valid


def test_submission_order_and_policies_are_part_of_the_schedule_digest() -> None:
    base = OrderScheduleSpec(
        price_distribution=PriceDistribution(
            lower_price="10",
            upper_price="20",
            level_count=2,
        ),
        amount_distribution=AmountDistribution(base_notional="20"),
        protection_policy=ProtectionPolicy(
            initial_stop=InitialStopSpec(distance_bps="100"),
        ),
    )
    reversed_order = base.model_copy(
        update={"submission_order": ScheduleSubmissionOrder.HIGH_TO_LOW}
    )
    dynamic = base.model_copy(
        update={
            "dynamic_rules": (
                CancelOnShockRule(window_seconds=5, adverse_move_bps="25"),
            )
        }
    )

    plain_preview = _compile(base)
    reversed_preview = _compile(reversed_order)
    dynamic_preview = _compile(dynamic)

    assert plain_preview.valid and reversed_preview.valid and dynamic_preview.valid
    assert len(
        {
            plain_preview.schedule_digest,
            reversed_preview.schedule_digest,
            dynamic_preview.schedule_digest,
        }
    ) == 3


def test_shared_schedule_model_keeps_non_direct_policy_types_available() -> None:
    spec = OrderScheduleSpec(
        price_distribution=SinglePrice(limit_price="100"),
        amount_distribution=AmountDistribution(base_notional="20"),
        entry_conditions=ConditionGroup(
            items=(
                ProfitRCondition(
                    comparator=NumericComparator.GTE,
                    threshold_r="1",
                ),
            )
        ),
        protection_policy=ProtectionPolicy(
            initial_stop=InitialStopSpec(distance_bps="100"),
        ),
        dynamic_rules=(
            CancelOnShockRule(
                window_seconds=5,
                adverse_move_bps="25",
                max_triggers=2,
            ),
            SteppedProtectionRule(
                steps=(ProtectionStep(trigger_r="1", stop_r="0"),),
            ),
        ),
    )

    assert spec.entry_conditions.items[0].kind == "PROFIT_R"
    assert spec.dynamic_rules[0].max_triggers == 2
    assert spec.dynamic_rules[1].kind == "STEPPED_PROTECTION"
