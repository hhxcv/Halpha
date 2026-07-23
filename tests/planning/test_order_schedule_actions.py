from datetime import UTC, datetime, timedelta
from decimal import Decimal

from halpha.capital.models import AuthorityClass, EnvironmentKind
from halpha.planning.models import PlanActivation
from halpha.planning.order_policies import InitialStopSpec, ProtectionPolicy
from halpha.planning.order_schedule import (
    AmountDistribution,
    InstrumentOrderRules,
    OrderScheduleSpec,
    PriceDistribution,
    ScheduleSubmissionOrder,
    SinglePrice,
    VenueOrderPolicy,
    compile_order_schedule,
)
from halpha.planning.order_schedule_actions import materialize_direct_schedule
from halpha.planning.registry import DIRECT_EXECUTION_REF, Direction


NOW = datetime(2026, 7, 23, tzinfo=UTC)


def _rules() -> InstrumentOrderRules:
    return InstrumentOrderRules(
        source="BINANCE_DEMO_EXCHANGE_INFO",
        min_price="0.1",
        max_price="1000000",
        price_tick_size="0.1",
        limit_quantity_step="0.01",
        min_limit_quantity="0.01",
        max_limit_quantity="1000",
        market_quantity_step="0.1",
        min_market_quantity="0.1",
        max_market_quantity="100",
        min_notional="5",
        source_cutoff=NOW.isoformat(),
    )


def _activation(spec: OrderScheduleSpec) -> PlanActivation:
    snapshot = compile_order_schedule(
        spec,
        _rules(),
        venue_ref="BINANCE_USDM",
        instrument_ref="BTCUSDT-PERP",
        direction=Direction.LONG,
        max_notional="100",
        schedule_ref="plan-version-001",
        reference_price="100",
    )
    assert snapshot.valid
    return PlanActivation(
        activation_id="activation-001",
        environment_id="demo",
        environment_kind=EnvironmentKind.DEMO,
        authority_class=AuthorityClass.DEMO_VALIDATION,
        plan_version_ref="plan-version-001",
        account_ref="demo-account",
        instrument_ref="BTCUSDT-PERP",
        direction=Direction.LONG,
        decision_basis_ref=DIRECT_EXECUTION_REF,
        framework_strategy_id="HALPHA-INTERNAL-001",
        order_schedule_snapshot=snapshot,
        target_exposure="100",
        rule_state={"deadlines": {"entry_valid_until": (NOW + timedelta(hours=1)).isoformat()}},
        created_at=NOW,
        updated_at=NOW,
    )


def _protection() -> ProtectionPolicy:
    return ProtectionPolicy(initial_stop=InitialStopSpec(distance_bps="100"))


def test_materializer_creates_stable_complete_leg_identities_and_context() -> None:
    activation = _activation(
        OrderScheduleSpec(
            price_distribution=PriceDistribution(
                lower_price="10",
                upper_price="30",
                level_count=3,
            ),
            amount_distribution=AmountDistribution(base_notional="20"),
            venue_policy=VenueOrderPolicy(post_only=True),
            protection_policy=_protection(),
        )
    )

    first = materialize_direct_schedule(
        activation,
        entry_valid_until=NOW + timedelta(hours=1),
    )
    second = materialize_direct_schedule(
        activation,
        entry_valid_until=NOW + timedelta(hours=1),
    )

    assert first == second
    assert [item.leg.leg_index for item in first] == [0, 1, 2]
    assert [Decimal(item.economic_action_prior_notional) for item in first] == [
        Decimal(0),
        Decimal(first[0].leg.effective_notional),
        Decimal(first[0].leg.effective_notional)
        + Decimal(first[1].leg.effective_notional),
    ]
    assert len({item.plan_event_id for item in first}) == 3
    assert len({item.execution_action_id for item in first}) == 3
    assert all(len(item.client_order_id) == 32 for item in first)
    context = first[0].proposed_action.execution_context
    assert context["venue_policy"]["post_only"] is True
    assert context["order_schedule"]["submission_index"] == 0
    assert context["protection_policy"]["initial_stop"]["distance_bps"] == "100"


def test_high_to_low_changes_submission_sequence_not_stable_leg_identity() -> None:
    base = OrderScheduleSpec(
        price_distribution=PriceDistribution(
            lower_price="10",
            upper_price="30",
            level_count=3,
        ),
        amount_distribution=AmountDistribution(base_notional="20"),
        protection_policy=_protection(),
    )
    low_to_high = materialize_direct_schedule(
        _activation(base),
        entry_valid_until=NOW + timedelta(hours=1),
    )
    high_to_low = materialize_direct_schedule(
        _activation(
            base.model_copy(
                update={"submission_order": ScheduleSubmissionOrder.HIGH_TO_LOW}
            )
        ),
        entry_valid_until=NOW + timedelta(hours=1),
    )

    assert [item.leg.leg_index for item in low_to_high] == [0, 1, 2]
    assert [item.leg.leg_index for item in high_to_low] == [2, 1, 0]


def test_price_match_keeps_local_sizing_price_and_explicit_wire_policy() -> None:
    activation = _activation(
        OrderScheduleSpec(
            price_distribution=SinglePrice(),
            amount_distribution=AmountDistribution(base_notional="20"),
            venue_policy=VenueOrderPolicy(price_match="QUEUE_5"),
            protection_policy=_protection(),
        )
    )

    materialized = materialize_direct_schedule(
        activation,
        entry_valid_until=NOW + timedelta(hours=1),
    )[0]

    assert materialized.proposed_action.price == "100"
    assert (
        materialized.proposed_action.execution_context["venue_policy"]["price_match"]
        == "QUEUE_5"
    )
