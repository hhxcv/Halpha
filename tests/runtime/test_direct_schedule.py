from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from halpha.capital.models import AuthorityClass, EnvironmentKind
from halpha.executor.direct_schedule import (
    DIRECT_PRICE_MOVE_MAX_SAMPLES,
    POST_ONLY_RETRY_MAX_ATTEMPTS,
    DirectPriceMoveTracker,
    DirectScheduleBoundary,
)
from halpha.executor.coordinator import OrderScheduleCapRejected
from halpha.executor.product_entry import (
    ProductAccountFacts,
    ProductPreSubmitRejected,
)
from halpha.executor.responsibilities import ProductRiskReductionFacts
from halpha.planning.models import PlanActivation, PlanLifecycle
from halpha.planning.order_policies import (
    CancelOnShockRule,
    ClosedBarPrice15mCondition,
    ConditionFactProvenance,
    ConditionFacts,
    ConditionGroup,
    ExpireRemainingRule,
    InitialStopSpec,
    MarkPriceCondition,
    NumericComparator,
    ProtectionPolicy,
    RepriceEntryRule,
)
from halpha.planning.order_schedule import (
    AmountDistribution,
    BinancePriceMatch,
    EntryProgram,
    EntryProgramKind,
    InstrumentOrderRules,
    OrderScheduleSpec,
    PriceDistribution,
    SinglePrice,
    VenueOrderPolicy,
    VenueOrderType,
    VenueTimeInForce,
    compile_order_schedule,
)
from halpha.planning.order_schedule_actions import (
    materialize_direct_schedule,
    materialize_direct_schedule_reprice,
    materialize_direct_schedule_retry,
)
from halpha.planning.registry import DIRECT_EXECUTION_REF, Direction
from halpha.planning.transitions import proposed_cancel_for_action, record_direct_fill
from halpha.venue_integration.models import (
    ExecutionActionKind,
    ExecutionActionState,
    VenueFactKind,
)


NOW = datetime(2026, 7, 23, 8, tzinfo=UTC)


def test_price_move_tracker_has_a_hard_sample_bound_under_bursty_input() -> None:
    tracker = DirectPriceMoveTracker()
    for index in range(DIRECT_PRICE_MOVE_MAX_SAMPLES + 100):
        tracker.record_mark(
            SimpleNamespace(ts_event=index + 1, value="100")
        )

    assert len(tracker._marks) == DIRECT_PRICE_MOVE_MAX_SAMPLES


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


def _spec(
    *,
    shock: bool = False,
    condition_price: str = "50",
    expire_at: datetime | None = None,
    expire_remaining_seconds: int | None = None,
) -> OrderScheduleSpec:
    return OrderScheduleSpec(
        price_distribution=PriceDistribution(
            lower_price="90",
            upper_price="110",
            level_count=3,
        ),
        amount_distribution=AmountDistribution(base_notional="20"),
        venue_policy=(
            VenueOrderPolicy(
                time_in_force=VenueTimeInForce.GTD,
                expire_at=expire_at,
            )
            if expire_at is not None
            else VenueOrderPolicy()
        ),
        entry_conditions=ConditionGroup(
            items=(
                MarkPriceCondition(
                    comparator=NumericComparator.GTE,
                    price=condition_price,
                ),
            )
        ),
        protection_policy=ProtectionPolicy(
            initial_stop=InitialStopSpec(distance_bps="100")
        ),
        dynamic_rules=tuple(
            rule
            for rule in (
                CancelOnShockRule(window_seconds=5, adverse_move_bps="100")
                if shock
                else None,
                ExpireRemainingRule(after_seconds=expire_remaining_seconds)
                if expire_remaining_seconds is not None
                else None,
            )
            if rule is not None
        ),
    )


def _post_only_spec(*, limit_price: str) -> OrderScheduleSpec:
    return OrderScheduleSpec(
        price_distribution=SinglePrice(limit_price=limit_price),
        amount_distribution=AmountDistribution(base_notional="100"),
        venue_policy=VenueOrderPolicy(post_only=True),
        entry_conditions=ConditionGroup(
            items=(
                MarkPriceCondition(
                    comparator=NumericComparator.GTE,
                    price="50",
                ),
            )
        ),
        protection_policy=ProtectionPolicy(
            initial_stop=InitialStopSpec(distance_bps="100")
        ),
    )


def _price_match_spec(
    *,
    price_match: BinancePriceMatch = BinancePriceMatch.OPPONENT_10,
) -> OrderScheduleSpec:
    return OrderScheduleSpec(
        price_distribution=SinglePrice(),
        amount_distribution=AmountDistribution(base_notional="100"),
        venue_policy=VenueOrderPolicy(price_match=price_match),
        entry_conditions=ConditionGroup(
            items=(
                MarkPriceCondition(
                    comparator=NumericComparator.GTE,
                    price="50",
                ),
            )
        ),
        protection_policy=ProtectionPolicy(
            initial_stop=InitialStopSpec(distance_bps="100")
        ),
    )


def _time_sliced_resting_spec() -> OrderScheduleSpec:
    return OrderScheduleSpec(
        entry_program=EntryProgram(
            kind=EntryProgramKind.TIME_SLICED,
            slice_count=2,
            first_slice_delay_seconds=0,
            slice_interval_seconds=10,
        ),
        price_distribution=SinglePrice(limit_price="90"),
        amount_distribution=AmountDistribution(base_notional="20"),
        venue_policy=VenueOrderPolicy(post_only=True),
        entry_conditions=ConditionGroup(
            items=(
                MarkPriceCondition(
                    comparator=NumericComparator.GTE,
                    price="50",
                ),
            )
        ),
        protection_policy=ProtectionPolicy(
            initial_stop=InitialStopSpec(distance_bps="100")
        ),
        dynamic_rules=(ExpireRemainingRule(after_seconds=15),),
    )


def _reprice_spec(
    *,
    limit_price: str = "100",
    post_only: bool = False,
    trigger_distance_bps: str = "5",
    maximum_total_move_bps: str = "30",
    max_adjustments: int = 3,
) -> OrderScheduleSpec:
    return OrderScheduleSpec(
        entry_program=EntryProgram(kind=EntryProgramKind.ONE_TIME),
        price_distribution=SinglePrice(limit_price=limit_price),
        amount_distribution=AmountDistribution(base_notional="100"),
        venue_policy=VenueOrderPolicy(post_only=post_only),
        entry_conditions=ConditionGroup(
            items=(
                MarkPriceCondition(
                    comparator=NumericComparator.GTE,
                    price="50",
                ),
            )
        ),
        protection_policy=ProtectionPolicy(
            initial_stop=InitialStopSpec(distance_bps="100")
        ),
        dynamic_rules=(
            RepriceEntryRule(
                trigger_distance_bps=trigger_distance_bps,
                maximum_total_move_bps=maximum_total_move_bps,
                max_adjustments=max_adjustments,
            ),
        ),
    )


def _activation(
    spec: OrderScheduleSpec,
    *,
    direction: Direction = Direction.LONG,
) -> PlanActivation:
    preview = compile_order_schedule(
        spec,
        _rules(),
        venue_ref="BINANCE_USDM",
        instrument_ref="BTCUSDT-PERP",
        direction=direction,
        max_notional="100",
        schedule_ref="plan-version-direct",
        reference_price=(
            "100"
            if (
                spec.venue_policy.order_type is VenueOrderType.MARKET
                or spec.venue_policy.price_match is not None
            )
            else None
        ),
    )
    assert preview.valid
    return PlanActivation(
        activation_id="activation-direct",
        environment_id="demo",
        environment_kind=EnvironmentKind.DEMO,
        authority_class=AuthorityClass.DEMO_VALIDATION,
        plan_version_ref="plan-version-direct",
        account_ref="demo-account",
        instrument_ref="BTCUSDT-PERP",
        direction=direction,
        decision_basis_ref=DIRECT_EXECUTION_REF,
        framework_strategy_id="HALPHA-DIRECT",
        order_schedule_snapshot=preview,
        target_exposure="100",
        rule_state={
            "deadlines": {"entry_valid_until": (NOW + timedelta(hours=1)).isoformat()}
        },
        created_at=NOW,
        updated_at=NOW,
    )


def _facts() -> ProductAccountFacts:
    return ProductAccountFacts(
        checked_at=NOW + timedelta(minutes=1),
        conservative_price="100",
        available_margin="1000",
        actual_margin_mode="ISOLATED",
        actual_leverage="5",
        activation_current_notional="0",
        account_current_notional="0",
        activation_current_margin="0",
        current_abs_position="0",
        post_action_abs_position="0.2",
    )


def _condition_facts(
    mark: str | None = "100",
    *,
    closed_bar_15m_close: str | None = None,
    observed_at: datetime = NOW + timedelta(minutes=1),
) -> ConditionFacts:
    return ConditionFacts(
        basis_ready=True,
        mark_price=mark,
        closed_bar_15m_close=closed_bar_15m_close,
        closed_bar_15m_at=(
            observed_at - timedelta(minutes=1)
            if closed_bar_15m_close is not None
            else None
        ),
        bid_price="99.9",
        ask_price="100.1",
        elapsed_seconds=60,
        provenance=ConditionFactProvenance(
            source="BINANCE_DEMO_PUBLIC",
            source_cutoff=observed_at,
            evaluated_at=observed_at,
            quote_source_time=observed_at - timedelta(seconds=2),
            quote_received_at=observed_at - timedelta(seconds=1),
            mark_source_time=observed_at - timedelta(seconds=2),
            mark_received_at=observed_at - timedelta(seconds=1),
        ),
    )


def _risk_facts(
    *,
    current_abs_position: str = "0",
    position_fact: object | None = None,
) -> ProductRiskReductionFacts:
    return ProductRiskReductionFacts(
        checked_at=NOW + timedelta(minutes=1),
        conservative_price="100",
        available_margin="1000",
        actual_margin_mode="ISOLATED",
        actual_leverage="5",
        activation_current_notional="0",
        account_current_notional="0",
        activation_current_margin="0",
        current_abs_position=current_abs_position,
        position_fact=position_fact,
    )


def _persisted_leg(
    item,
    *,
    state: ExecutionActionState,
    call_started_at: datetime | None = None,
    created_at: datetime = NOW,
) -> SimpleNamespace:
    return SimpleNamespace(
        execution_action_id=item.execution_action_id,
        activation_id="activation-direct",
        source_identity=item.source_identity,
        client_order_id=item.client_order_id,
        action_kind=ExecutionActionKind.ENTRY,
        action_terms=item.proposed_action.model_dump(mode="python"),
        state=state,
        state_version=1,
        call_started_at=call_started_at,
        call_completed_at=None,
        created_at=created_at,
        updated_at=created_at,
    )


class _Coordinator:
    def __init__(self, activation: PlanActivation) -> None:
        self.activation = activation
        self.actions: list[SimpleNamespace] = []
        self.atomic_calls: list[dict[str, object]] = []
        self.submissions: list[str] = []
        self.rejections: list[tuple[str, str]] = []
        self.pre_submit_rejections: list[dict[str, object]] = []
        self.cancel_targets: list[str] = []
        self.cancel_endpoints: list[str] = []
        self.submission_checks: list[object] = []
        self.venue_facts: dict[str, tuple[object, ...]] = {}
        self.closures: list[dict[str, object]] = []
        self.expirations: list[dict[str, object]] = []
        self.remaining_expirations: list[dict[str, object]] = []
        self.invalidations: list[dict[str, object]] = []
        self.account_facts: list[object] = []
        self.condition_states: list[dict[str, object]] = []

    def get_activation_snapshot(self, _activation_id: str) -> PlanActivation:
        return self.activation

    def record_runtime_condition_state(self, **kwargs):
        self.condition_states.append(kwargs)
        return self.activation

    def expire_empty_entry_window(self, **kwargs):
        self.expirations.append(kwargs)
        self.activation = self.activation.model_copy(
            update={"lifecycle": PlanLifecycle.COMPLETED}
        )
        return self.activation, SimpleNamespace()

    def expire_remaining_entry_opportunity(self, **kwargs):
        self.remaining_expirations.append(kwargs)
        self.activation = self.activation.model_copy(
            update={"entry_opportunity_consumed": True}
        )
        return self.activation, SimpleNamespace()

    def invalidate_empty_entry_opportunity(self, **kwargs):
        self.invalidations.append(kwargs)
        self.activation = self.activation.model_copy(
            update={"lifecycle": PlanLifecycle.COMPLETED}
        )
        return self.activation, SimpleNamespace()

    def list_execution_actions(self, _activation_id: str):
        return tuple(self.actions)

    def list_venue_facts_for_action(self, execution_action_id: str):
        return self.venue_facts.get(execution_action_id, ())

    def consume_order_schedule_atomic(self, **kwargs):
        self.atomic_calls.append(kwargs)
        for item, check in zip(
            kwargs["legs"],
            kwargs["action_checks"],
            strict=True,
        ):
            persisted = _persisted_leg(
                item,
                state=ExecutionActionState.READY,
                created_at=kwargs["observed_at"],
            )
            persisted.action_terms["quantity"] = check.quantized_quantity
            self.actions.append(persisted)
        return ()

    def consume_order_schedule_retry(self, **kwargs):
        item = kwargs["retry_leg"]
        persisted = _persisted_leg(
            item,
            state=ExecutionActionState.READY,
            created_at=kwargs["observed_at"],
        )
        persisted.action_terms["quantity"] = kwargs["action_check"].quantized_quantity
        self.actions.append(persisted)
        return SimpleNamespace(execution_action=persisted)

    def consume_order_schedule_reprice(self, **kwargs):
        item = kwargs["replacement_leg"]
        persisted = _persisted_leg(
            item,
            state=ExecutionActionState.READY,
            created_at=kwargs["observed_at"],
        )
        persisted.action_terms["quantity"] = kwargs["action_check"].quantized_quantity
        self.actions.append(persisted)
        return SimpleNamespace(execution_action=persisted)

    def process_execution_action(self, execution_action_id: str, **kwargs):
        self.submissions.append(execution_action_id)
        self.submission_checks.append(kwargs["action_check"])
        action = next(
            item
            for item in self.actions
            if item.execution_action_id == execution_action_id
        )
        action.state = ExecutionActionState.SUBMITTING
        action.call_started_at = kwargs["observed_at"]

    def reject_execution_action_before_submission(
        self,
        execution_action_id: str,
        *,
        reason_code: str,
        **_kwargs,
    ):
        self.rejections.append((execution_action_id, reason_code))
        action = next(
            item
            for item in self.actions
            if item.execution_action_id == execution_action_id
        )
        action.state = ExecutionActionState.NOT_SUBMITTED
        return action

    def record_direct_pre_submit_rejection(self, **kwargs):
        self.pre_submit_rejections.append(kwargs)
        return SimpleNamespace(**kwargs)

    def create_cancel_for_action(self, **kwargs):
        self.cancel_targets.append(kwargs["target_action_id"])
        self.cancel_endpoints.append(kwargs["target_endpoint"])
        target = next(
            item
            for item in self.actions
            if item.execution_action_id == kwargs["target_action_id"]
        )
        proposed = proposed_cancel_for_action(
            self.activation,
            target_client_order_id=target.client_order_id,
            target_endpoint=kwargs["target_endpoint"],
            causation_ref=kwargs["reason_ref"],
        )
        action = SimpleNamespace(
            execution_action_id=kwargs["execution_action_id"],
            activation_id="activation-direct",
            source_identity=(
                f"activation-direct:CANCEL:{kwargs['target_action_id']}:"
                f"{kwargs['reason_ref']}"
            ),
            client_order_id=None,
            action_kind=ExecutionActionKind.CANCEL,
            action_terms=proposed.model_dump(mode="python"),
            cancel_target=proposed.cancel_target,
            state=ExecutionActionState.READY,
            state_version=1,
            call_started_at=None,
            call_completed_at=None,
            created_at=kwargs["observed_at"],
            updated_at=kwargs["observed_at"],
        )
        self.actions.append(action)
        return SimpleNamespace(execution_action=action)

    def apply_venue_fact(self, fact: object, **_kwargs):
        self.account_facts.append(fact)
        return None

    def reconcile_retryable_entry_rejection(
        self,
        execution_action_id: str,
        *,
        observed_at: datetime,
    ):
        action = next(
            item
            for item in self.actions
            if item.execution_action_id == execution_action_id
        )
        action.state = ExecutionActionState.CLOSED
        action.updated_at = observed_at
        return action

    def reconcile_execution_action(self, execution_action_id: str, **kwargs):
        action = next(
            item
            for item in self.actions
            if item.execution_action_id == execution_action_id
        )
        action.state = ExecutionActionState.CLOSED
        self.closures.append({"execution_action_id": execution_action_id, **kwargs})
        return action


def _boundary(
    coordinator: _Coordinator,
    *,
    enabled=lambda: True,
    now: datetime = NOW + timedelta(minutes=1),
    monotonic_now=None,
    pre_submit_fact_provider=None,
    condition_fact_provider=None,
    risk_fact_provider=None,
    failure_sink=None,
    environment_id: str = "demo",
    environment_kind: EnvironmentKind = EnvironmentKind.DEMO,
    authority_class: AuthorityClass = AuthorityClass.DEMO_VALIDATION,
    account_ref: str = "demo-account",
) -> DirectScheduleBoundary:
    async def default_provider(*_args):
        return _facts()

    async def default_risk_provider(*_args):
        return _risk_facts()

    def default_condition_provider(
        _activation,
        _cutoff_ns,
        observed_at,
        _price_move_bps_by_window,
    ):
        return _condition_facts(observed_at=observed_at)

    return DirectScheduleBoundary(
        loop=asyncio.get_running_loop(),
        coordinator=coordinator,
        pre_submit_fact_provider=pre_submit_fact_provider or default_provider,
        condition_fact_provider=(condition_fact_provider or default_condition_provider),
        risk_reduction_fact_provider=(risk_fact_provider or default_risk_provider),
        environment_id=environment_id,
        environment_kind=environment_kind,
        authority_class=authority_class,
        account_ref=account_ref,
        submission_enabled=enabled,
        current_time_provider=now if callable(now) else lambda: now,
        monotonic_time_provider=monotonic_now,
        failure_sink=failure_sink,
    )


def test_background_failure_is_reported_with_activation_identity() -> None:
    async def scenario():
        failures: list[tuple[str, str]] = []
        loop_contexts: list[dict[str, object]] = []
        asyncio.get_running_loop().set_exception_handler(
            lambda _loop, context: loop_contexts.append(context)
        )
        coordinator = _Coordinator(_activation(_spec()))

        async def failed_facts(*_args):
            raise ValueError("FACTS_UNAVAILABLE")

        boundary = _boundary(
            coordinator,
            pre_submit_fact_provider=failed_facts,
            failure_sink=lambda activation_id, exception: failures.append(
                (activation_id, str(exception))
            ),
        )
        boundary.resume("activation-direct")
        for _ in range(3):
            await asyncio.sleep(0)
        return failures, loop_contexts

    failures, loop_contexts = asyncio.run(scenario())
    assert failures == [
        ("activation-direct", "FACTS_UNAVAILABLE"),
    ]
    assert loop_contexts == []


def test_existing_exit_responsibility_stops_entry_scheduler_account_checks() -> None:
    async def scenario():
        account_reads = 0
        activation = _activation(_spec()).model_copy(
            update={
                "has_entry_fill": True,
                "entry_opportunity_consumed": True,
            }
        )
        coordinator = _Coordinator(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        coordinator.actions.append(
            _persisted_leg(legs[0], state=ExecutionActionState.OPEN)
        )
        coordinator.actions.append(
            SimpleNamespace(
                execution_action_id="exit-action",
                activation_id="activation-direct",
                source_identity="activation-direct:EXIT:DIRECT_TIME_EXIT",
                client_order_id="d" * 32,
                action_kind=ExecutionActionKind.EXIT,
                action_terms={
                    "action_profile": "REDUCE_OR_CLOSE_MARKET",
                    "quantity": "0.2",
                },
                state=ExecutionActionState.OPEN,
                state_version=1,
                call_started_at=NOW,
                call_completed_at=None,
                created_at=NOW,
                updated_at=NOW,
            )
        )

        async def read_account(*_args):
            nonlocal account_reads
            account_reads += 1
            raise ValueError("POSITION_ATTRIBUTION_UNKNOWN")

        boundary = _boundary(
            coordinator,
            pre_submit_fact_provider=read_account,
            risk_fact_provider=read_account,
        )
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator, account_reads

    coordinator, account_reads = asyncio.run(scenario())
    assert account_reads == 0
    assert coordinator.submissions == []


@pytest.mark.parametrize(
    ("direction", "limit_price"),
    (
        (Direction.LONG, "101"),
        (Direction.SHORT, "99"),
    ),
)
def test_marketable_post_only_entry_waits_without_creating_action(
    direction: Direction,
    limit_price: str,
) -> None:
    async def scenario():
        coordinator = _Coordinator(
            _activation(
                _post_only_spec(limit_price=limit_price),
                direction=direction,
            )
        )
        boundary = _boundary(coordinator)
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())
    assert coordinator.atomic_calls == []
    assert coordinator.actions == []
    assert coordinator.submissions == []
    latest = coordinator.condition_states[-1]["state"]
    assert latest.result.value == "TRUE"
    assert latest.submission_ready is False
    assert latest.blocking_reason == "DIRECT_POST_ONLY_WOULD_TAKE"


def test_post_only_race_rejection_retries_with_new_identity_after_restart() -> None:
    async def scenario():
        current_time = NOW + timedelta(minutes=1)
        activation = _activation(
            _post_only_spec(limit_price="100"),
            direction=Direction.SHORT,
        )
        coordinator = _Coordinator(activation)
        base = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )[0]
        first = _persisted_leg(
            base,
            state=ExecutionActionState.OPEN,
            created_at=current_time - timedelta(seconds=1),
        )
        coordinator.actions.append(first)
        coordinator.venue_facts[first.execution_action_id] = (
            _fact(
                "post-only-rejected",
                VenueFactKind.ORDER_STATE,
                {
                    "status": "REJECTED",
                    "cumulative_filled_quantity": "0",
                    "reason": (
                        "{'code': -5022, 'msg': 'Due to the order could not "
                        "be executed as maker, the Post Only order will be rejected.'}"
                    ),
                },
            ),
        )
        boundary = _boundary(coordinator, now=lambda: current_time)
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        assert first.state is ExecutionActionState.CLOSED
        assert coordinator.submissions == []

        current_time += timedelta(seconds=3)
        restarted_coordinator = _Coordinator(coordinator.activation)
        restarted_coordinator.actions.extend(coordinator.actions)
        restarted_coordinator.venue_facts.update(coordinator.venue_facts)
        restarted_boundary = _boundary(
            restarted_coordinator,
            now=lambda: current_time,
        )
        restarted_boundary.resume("activation-direct")
        await restarted_boundary.wait_idle()
        return restarted_coordinator, first

    coordinator, first = asyncio.run(scenario())
    assert len(coordinator.actions) == 2
    retry = coordinator.actions[-1]
    assert retry.execution_action_id != first.execution_action_id
    assert retry.client_order_id != first.client_order_id
    retry_schedule = retry.action_terms["execution_context"]["order_schedule"]
    assert retry_schedule["attempt_index"] == 1
    assert retry_schedule["retry_reason"] == "POST_ONLY_WOULD_TAKE_RACE"
    assert coordinator.submissions == [retry.execution_action_id]
    assert coordinator.activation.lifecycle is PlanLifecycle.RUNNING


def test_price_match_rejection_closes_attempt_and_retries_with_same_policy() -> None:
    async def scenario():
        current_time = NOW + timedelta(minutes=1)
        activation = _activation(_price_match_spec())
        coordinator = _Coordinator(activation)
        base = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )[0]
        first = _persisted_leg(
            base,
            state=ExecutionActionState.OPEN,
            created_at=current_time - timedelta(seconds=1),
        )
        coordinator.actions.append(first)
        coordinator.venue_facts[first.execution_action_id] = (
            _fact(
                "price-match-rejected",
                VenueFactKind.ORDER_STATE,
                {
                    "status": "REJECTED",
                    "cumulative_filled_quantity": "0",
                    "reason": "{'code': -5037, 'msg': 'Invalid price match'}",
                },
            ),
        )
        boundary = _boundary(coordinator, now=lambda: current_time)
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        assert first.state is ExecutionActionState.CLOSED
        assert coordinator.submissions == []

        current_time += timedelta(seconds=3)
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator, first

    coordinator, first = asyncio.run(scenario())
    assert len(coordinator.actions) == 2
    retry = coordinator.actions[-1]
    assert retry.execution_action_id != first.execution_action_id
    assert retry.client_order_id != first.client_order_id
    retry_schedule = retry.action_terms["execution_context"]["order_schedule"]
    assert retry_schedule["attempt_index"] == 1
    assert retry_schedule["retry_reason"] == "PRICE_MATCH_TEMPORARILY_UNAVAILABLE"
    assert retry.action_terms["execution_context"]["venue_policy"]["price_match"] == (
        "OPPONENT_10"
    )
    assert coordinator.submissions == [retry.execution_action_id]
    assert coordinator.activation.lifecycle is PlanLifecycle.RUNNING


def test_post_only_race_rejection_stops_after_bounded_retries() -> None:
    async def scenario():
        current_time = NOW + timedelta(minutes=2)
        activation = _activation(
            _post_only_spec(limit_price="100"),
            direction=Direction.SHORT,
        )
        coordinator = _Coordinator(activation)
        base = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )[0]
        for attempt_index in range(POST_ONLY_RETRY_MAX_ATTEMPTS + 1):
            item = (
                base
                if attempt_index == 0
                else materialize_direct_schedule_retry(
                    activation,
                    base,
                    attempt_index=attempt_index,
                )
            )
            action = _persisted_leg(
                item,
                state=ExecutionActionState.CLOSED,
                created_at=current_time - timedelta(minutes=1),
            )
            coordinator.actions.append(action)
            coordinator.venue_facts[action.execution_action_id] = (
                _fact(
                    f"post-only-rejected-{attempt_index}",
                    VenueFactKind.ORDER_STATE,
                    {
                        "status": "REJECTED",
                        "cumulative_filled_quantity": "0",
                        "reason": (
                            "{'code': -5022, 'msg': 'Due to the order could not "
                            "be executed as maker, the Post Only order will be rejected.'}"
                        ),
                    },
                ),
            )
        boundary = _boundary(coordinator, now=lambda: current_time)
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())
    assert len(coordinator.actions) == POST_ONLY_RETRY_MAX_ATTEMPTS + 1
    assert coordinator.submissions == []
    assert coordinator.activation.lifecycle is PlanLifecycle.RUNNING


def test_open_unfilled_entry_is_cancelled_then_repriced_after_terminal_proof() -> None:
    async def scenario():
        current_time = NOW + timedelta(minutes=1)
        activation = _activation(_reprice_spec())
        coordinator = _Coordinator(activation)
        base = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )[0]
        first = _persisted_leg(
            base,
            state=ExecutionActionState.OPEN,
            call_started_at=current_time - timedelta(seconds=10),
            created_at=current_time - timedelta(seconds=10),
        )
        coordinator.actions.append(first)
        boundary = _boundary(coordinator, now=lambda: current_time)

        boundary.resume("activation-direct")
        await boundary.wait_idle()
        cancel = next(
            action
            for action in coordinator.actions
            if action.action_kind is ExecutionActionKind.CANCEL
        )
        assert "DIRECT_ENTRY_REPRICE" in cancel.source_identity
        assert len(
            [
                action
                for action in coordinator.actions
                if action.action_kind is ExecutionActionKind.ENTRY
            ]
        ) == 1

        first.state = ExecutionActionState.CLOSED
        first.updated_at = current_time
        coordinator.venue_facts[first.execution_action_id] = (
            _fact(
                "entry-cancelled-zero-fill",
                VenueFactKind.ORDER_STATE,
                {
                    "status": "CANCELLED",
                    "cumulative_filled_quantity": "0",
                },
            ),
        )
        cancel.state = ExecutionActionState.CLOSED
        cancel.updated_at = current_time
        current_time += timedelta(seconds=1)

        boundary.resume("activation-direct")
        await boundary.wait_idle()
        replacement = next(
            action
            for action in coordinator.actions
            if (
                action.action_kind is ExecutionActionKind.ENTRY
                and action.execution_action_id != first.execution_action_id
            )
        )
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator, first, replacement

    coordinator, first, replacement = asyncio.run(scenario())
    context = replacement.action_terms["execution_context"]["order_schedule"]
    assert context["attempt_index"] == 1
    assert context["retry_reason"] == "ENTRY_REPRICE"
    assert context["reprice_index"] == 1
    assert context["replacement_price"] == "99.8"
    assert replacement.action_terms["price"] == "99.8"
    assert replacement.execution_action_id != first.execution_action_id
    assert replacement.client_order_id != first.client_order_id
    assert coordinator.submissions.count(replacement.execution_action_id) == 1


def test_reprice_target_is_clamped_to_configured_total_move() -> None:
    async def scenario():
        current_time = NOW + timedelta(minutes=1)
        activation = _activation(_reprice_spec(maximum_total_move_bps="30"))
        coordinator = _Coordinator(activation)
        base = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )[0]
        first = _persisted_leg(
            base,
            state=ExecutionActionState.CLOSED,
            call_started_at=current_time - timedelta(seconds=10),
            created_at=current_time - timedelta(seconds=10),
        )
        coordinator.actions.append(first)
        coordinator.venue_facts[first.execution_action_id] = (
            _fact(
                "entry-cancelled-before-clamped-reprice",
                VenueFactKind.ORDER_STATE,
                {
                    "status": "CANCELLED",
                    "cumulative_filled_quantity": "0",
                },
            ),
        )
        reason_ref = (
            "activation-direct:DIRECT_DYNAMIC:DIRECT_ENTRY_REPRICE:"
            f"{first.execution_action_id}:v1"
        )
        coordinator.create_cancel_for_action(
            activation_id="activation-direct",
            target_action_id=first.execution_action_id,
            target_endpoint="ORDINARY",
            plan_event_id="cancel-plan-event",
            execution_action_id="cancel-action",
            action_check=_risk_facts().cancel_check(activation),
            reason_ref=reason_ref,
            observed_at=current_time,
            client_order_id=None,
        ).execution_action.state = ExecutionActionState.CLOSED

        def condition_provider(_activation, _cutoff, observed_at, _moves):
            return _condition_facts(observed_at=observed_at).model_copy(
                update={"bid_price": "105", "ask_price": "105.1"}
            )

        boundary = _boundary(
            coordinator,
            now=lambda: current_time,
            condition_fact_provider=condition_provider,
        )
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())
    replacement = next(
        action
        for action in coordinator.actions
        if (
            action.action_kind is ExecutionActionKind.ENTRY
            and action.action_terms["execution_context"]["order_schedule"].get(
                "retry_reason"
            )
            == "ENTRY_REPRICE"
        )
    )
    assert replacement.action_terms["price"] == "100.3"


def test_entry_with_any_fill_is_never_repriced() -> None:
    async def scenario():
        current_time = NOW + timedelta(minutes=1)
        activation = _activation(_reprice_spec())
        coordinator = _Coordinator(activation)
        base = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )[0]
        first = _persisted_leg(
            base,
            state=ExecutionActionState.OPEN,
            call_started_at=current_time - timedelta(seconds=10),
            created_at=current_time - timedelta(seconds=10),
        )
        coordinator.actions.append(first)
        coordinator.venue_facts[first.execution_action_id] = (
            _fact(
                "partial-fill-before-reprice",
                VenueFactKind.FILL,
                {"last_quantity": "0.01", "trade_id": "partial"},
            ),
        )
        boundary = _boundary(coordinator, now=lambda: current_time)
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())
    cancel_reasons = [
        str(action.action_terms.get("causation_ref", ""))
        for action in coordinator.actions
        if action.action_kind is ExecutionActionKind.CANCEL
    ]
    assert all("DIRECT_ENTRY_REPRICE" not in reason for reason in cancel_reasons)
    assert not any(
        action.action_terms.get("execution_context", {})
        .get("order_schedule", {})
        .get("retry_reason")
        == "ENTRY_REPRICE"
        for action in coordinator.actions
    )


def test_post_only_retry_after_reprice_preserves_replacement_price() -> None:
    async def scenario():
        current_time = NOW + timedelta(minutes=1)
        activation = _activation(_reprice_spec(post_only=True))
        coordinator = _Coordinator(activation)
        base = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )[0]
        first = _persisted_leg(
            base,
            state=ExecutionActionState.CLOSED,
            created_at=current_time - timedelta(seconds=20),
        )
        coordinator.actions.append(first)
        coordinator.venue_facts[first.execution_action_id] = (
            _fact(
                "first-entry-cancelled",
                VenueFactKind.ORDER_STATE,
                {
                    "status": "CANCELLED",
                    "cumulative_filled_quantity": "0",
                },
            ),
        )
        replacement = materialize_direct_schedule_reprice(
            activation,
            base,
            attempt_index=1,
            replacement_price="99.8",
            reprice_index=1,
        )
        second = _persisted_leg(
            replacement,
            state=ExecutionActionState.OPEN,
            created_at=current_time - timedelta(seconds=10),
        )
        coordinator.actions.append(second)
        coordinator.venue_facts[second.execution_action_id] = (
            _fact(
                "replacement-post-only-rejected",
                VenueFactKind.ORDER_STATE,
                {
                    "status": "REJECTED",
                    "cumulative_filled_quantity": "0",
                    "reason": (
                        "{'code': -5022, 'msg': 'Due to the order could not "
                        "be executed as maker, the Post Only order will be rejected.'}"
                    ),
                },
            ),
        )
        boundary = _boundary(coordinator, now=lambda: current_time)
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        current_time += timedelta(seconds=5)
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())
    retry = max(
        (
            action
            for action in coordinator.actions
            if action.action_kind is ExecutionActionKind.ENTRY
        ),
        key=lambda action: action.action_terms["execution_context"][
            "order_schedule"
        ].get("attempt_index", 0),
    )
    context = retry.action_terms["execution_context"]["order_schedule"]
    assert context["attempt_index"] == 2
    assert context["retry_reason"] == "POST_ONLY_WOULD_TAKE_RACE"
    assert context["replacement_price"] == "99.8"
    assert context["reprice_index"] == 1
    assert retry.action_terms["price"] == "99.8"


def test_post_only_race_rejection_does_not_retry_after_market_invalidation() -> None:
    async def scenario():
        current_time = NOW + timedelta(minutes=1)
        spec = _post_only_spec(limit_price="100").model_copy(
            update={
                "dynamic_rules": (CancelOnShockRule(invalidation_price="101"),),
            }
        )
        activation = _activation(spec, direction=Direction.SHORT)
        coordinator = _Coordinator(activation)
        base = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )[0]
        first = _persisted_leg(
            base,
            state=ExecutionActionState.OPEN,
            created_at=current_time - timedelta(seconds=3),
        )
        coordinator.actions.append(first)
        coordinator.venue_facts[first.execution_action_id] = (
            _fact(
                "post-only-rejected-invalidated",
                VenueFactKind.ORDER_STATE,
                {
                    "status": "REJECTED",
                    "cumulative_filled_quantity": "0",
                    "reason": (
                        "{'code': -5022, 'msg': 'Due to the order could not "
                        "be executed as maker, the Post Only order will be rejected.'}"
                    ),
                },
            ),
        )
        boundary = _boundary(
            coordinator,
            now=lambda: current_time,
            condition_fact_provider=(
                lambda _activation, _cutoff, observed_at, _moves: _condition_facts(
                    mark="102",
                    observed_at=observed_at,
                )
            ),
        )
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())
    assert len(coordinator.actions) == 1
    assert coordinator.actions[0].state is ExecutionActionState.CLOSED
    assert len(coordinator.invalidations) == 1
    assert coordinator.submissions == []


def test_post_only_race_rejection_does_not_retry_after_entry_deadline() -> None:
    async def scenario():
        current_time = NOW + timedelta(hours=1)
        activation = _activation(
            _post_only_spec(limit_price="100"),
            direction=Direction.SHORT,
        )
        coordinator = _Coordinator(activation)
        base = materialize_direct_schedule(
            activation,
            entry_valid_until=current_time,
        )[0]
        first = _persisted_leg(
            base,
            state=ExecutionActionState.OPEN,
            created_at=current_time - timedelta(seconds=3),
        )
        coordinator.actions.append(first)
        coordinator.venue_facts[first.execution_action_id] = (
            _fact(
                "post-only-rejected-expired",
                VenueFactKind.ORDER_STATE,
                {
                    "status": "REJECTED",
                    "cumulative_filled_quantity": "0",
                    "reason": (
                        "{'code': -5022, 'msg': 'Due to the order could not "
                        "be executed as maker, the Post Only order will be rejected.'}"
                    ),
                },
            ),
        )
        boundary = _boundary(coordinator, now=lambda: current_time)
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())
    assert len(coordinator.actions) == 1
    assert coordinator.actions[0].state is ExecutionActionState.CLOSED
    assert len(coordinator.expirations) == 1
    assert coordinator.submissions == []


def test_failure_sink_error_is_sanitized_and_does_not_block_forced_resume() -> None:
    async def scenario():
        loop_contexts: list[dict[str, object]] = []
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(lambda _loop, context: loop_contexts.append(context))
        boundary = _boundary(
            _Coordinator(_activation(_spec())),
            failure_sink=lambda _activation_id, _exception: (_ for _ in ()).throw(
                RuntimeError("private sink diagnostic")
            ),
        )
        advances = 0

        async def resumed_advance(activation_id: str) -> None:
            nonlocal advances
            advances += 1
            boundary._forced_risk_refreshes.discard(activation_id)

        boundary._advance = resumed_advance

        async def failed() -> None:
            raise RuntimeError("private original diagnostic")

        failed_task = loop.create_task(failed())
        await asyncio.gather(failed_task, return_exceptions=True)
        boundary._forced_risk_refreshes.add("activation-direct")
        boundary._report_failure("activation-direct", failed_task)
        await boundary.wait_idle()
        return advances, loop_contexts

    advances, loop_contexts = asyncio.run(scenario())

    assert advances == 1
    assert len(loop_contexts) == 1
    assert loop_contexts[0]["message"] == "HALPHA_DIRECT_SCHEDULE_FAILURE_SINK_FAILED"
    assert loop_contexts[0]["exception_type"] == "RuntimeError"
    assert "exception" not in loop_contexts[0]
    assert "task" not in loop_contexts[0]


def test_true_conditions_use_one_pre_submit_query_and_submit_first_leg() -> None:
    async def scenario():
        coordinator = _Coordinator(_activation(_spec()))
        fact_calls = 0

        async def pre_submit_facts(*_args):
            nonlocal fact_calls
            fact_calls += 1
            return _facts()

        boundary = _boundary(
            coordinator,
            pre_submit_fact_provider=pre_submit_facts,
        )
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator, fact_calls

    coordinator, fact_calls = asyncio.run(scenario())
    assert fact_calls == 1
    assert len(coordinator.actions) == 3
    assert len(coordinator.atomic_calls) == 1
    evidence = coordinator.atomic_calls[0]["condition_evidence"]
    assert evidence["evaluation"]["result"] == "TRUE"
    assert evidence["facts"]["mark_price"] == "100"
    condition_facts = coordinator.atomic_calls[0]["condition_facts"]
    assert tuple(fact.kind for fact in condition_facts) == (VenueFactKind.MARK_PRICE,)
    assert condition_facts[0].payload["mark_price"] == "100"
    assert coordinator.submissions == [coordinator.actions[0].execution_action_id]


def test_submission_transition_does_not_reuse_older_account_fact_time() -> None:
    async def scenario():
        coordinator = _Coordinator(_activation(_spec()))
        times = iter(
            (
                NOW + timedelta(minutes=1),
                NOW + timedelta(minutes=2),
                NOW + timedelta(minutes=3),
            )
        )
        boundary = _boundary(
            coordinator,
            now=lambda: next(times),
        )
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())

    action = coordinator.actions[0]
    assert action.created_at == NOW + timedelta(minutes=2)
    assert action.call_started_at == NOW + timedelta(minutes=3)
    assert action.call_started_at >= action.created_at
    assert coordinator.submission_checks[0].checked_at == NOW + timedelta(minutes=1)


def test_non_market_condition_does_not_require_market_fact_refs() -> None:
    async def scenario():
        activation = _activation(
            _spec().model_copy(update={"entry_conditions": ConditionGroup()})
        )
        coordinator = _Coordinator(activation)

        def basis_only_facts(*_args):
            return ConditionFacts(basis_ready=True)

        boundary = _boundary(
            coordinator,
            condition_fact_provider=basis_only_facts,
        )
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())

    assert coordinator.atomic_calls[0]["condition_facts"] == ()
    assert coordinator.submissions == [coordinator.actions[0].execution_action_id]


def test_condition_cutoff_is_not_replaced_by_account_fact_time() -> None:
    async def scenario():
        coordinator = _Coordinator(_activation(_spec()))
        condition_time = NOW + timedelta(minutes=2)

        boundary = _boundary(
            coordinator,
            now=condition_time,
        )
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator.atomic_calls[0], condition_time

    atomic_call, condition_time = asyncio.run(scenario())

    assert atomic_call["observed_at"] == condition_time
    assert atomic_call["condition_source_cutoff"] == condition_time
    assert atomic_call["action_checks"][0].checked_at == NOW + timedelta(minutes=1)
    assert atomic_call["condition_evidence"]["environment"] == {
        "environment_id": "demo",
        "environment_kind": "DEMO",
    }


def test_condition_transition_queries_once_after_3600_waiting_cycles() -> None:
    async def scenario():
        coordinator = _Coordinator(_activation(_spec(condition_price="50")))
        fact_calls = 0
        mark = ["1"]

        async def pre_submit_facts(*_args):
            nonlocal fact_calls
            fact_calls += 1
            return _facts()

        def condition_facts(*_args):
            return _condition_facts(mark=mark[0], observed_at=_args[2])

        boundary = _boundary(
            coordinator,
            pre_submit_fact_provider=pre_submit_facts,
            condition_fact_provider=condition_facts,
        )
        for _ in range(3_600):
            boundary.resume("activation-direct")
            await boundary.wait_idle()
        assert fact_calls == 0
        assert coordinator.actions == []
        assert coordinator.atomic_calls == []
        mark[0] = "100"
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator, fact_calls

    coordinator, fact_calls = asyncio.run(scenario())
    assert fact_calls == 1
    assert len(coordinator.atomic_calls) == 1
    assert coordinator.submissions == [coordinator.actions[0].execution_action_id]


def test_closed_bar_condition_does_not_use_mark_price_as_a_substitute() -> None:
    async def scenario():
        spec = _spec().model_copy(
            update={
                "entry_conditions": ConditionGroup(
                    items=(
                        ClosedBarPrice15mCondition(
                            comparator=NumericComparator.LTE,
                            price="50",
                        ),
                    )
                )
            }
        )
        coordinator = _Coordinator(_activation(spec, direction=Direction.SHORT))
        closed_bar = ["70"]
        fact_calls = 0

        async def pre_submit_facts(*_args):
            nonlocal fact_calls
            fact_calls += 1
            return _facts()

        def condition_facts(*_args):
            return _condition_facts(
                mark="40",
                closed_bar_15m_close=closed_bar[0],
                observed_at=_args[2],
            )

        boundary = _boundary(
            coordinator,
            pre_submit_fact_provider=pre_submit_facts,
            condition_fact_provider=condition_facts,
        )
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        assert fact_calls == 0
        assert coordinator.actions == []

        closed_bar[0] = "40"
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator, fact_calls

    coordinator, fact_calls = asyncio.run(scenario())

    assert fact_calls == 1
    assert len(coordinator.atomic_calls) == 1
    assert coordinator.submissions == [coordinator.actions[0].execution_action_id]


def test_pre_submit_failures_back_off_without_delaying_the_next_leg() -> None:
    async def scenario():
        coordinator = _Coordinator(_activation(_spec()))
        current_time = [NOW + timedelta(minutes=1)]
        monotonic_time = [100.0]
        attempts = 0
        failures: list[str] = []
        loop_contexts: list[dict[str, object]] = []
        asyncio.get_running_loop().set_exception_handler(
            lambda _loop, context: loop_contexts.append(context)
        )

        async def pre_submit_facts(*_args):
            nonlocal attempts
            attempts += 1
            if attempts <= 2:
                raise ProductPreSubmitRejected("ACCOUNT_FACT_QUERY_FAILED_TIMEOUT")
            return _facts()

        boundary = _boundary(
            coordinator,
            now=lambda: current_time[0],
            monotonic_now=lambda: monotonic_time[0],
            pre_submit_fact_provider=pre_submit_facts,
            failure_sink=lambda _activation_id, exception: failures.append(
                str(exception)
            ),
        )

        boundary.resume("activation-direct")
        await boundary.wait_idle()
        assert attempts == 1
        assert (
            coordinator.condition_states[-1]["state"].blocking_reason
            == "ACCOUNT_FACT_QUERY_FAILED_TIMEOUT"
        )

        for _ in range(100):
            boundary.resume("activation-direct")
            await boundary.wait_idle()
        assert attempts == 1
        assert (
            coordinator.condition_states[-1]["state"].blocking_reason
            == "ACCOUNT_FACT_QUERY_FAILED_TIMEOUT"
        )

        current_time[0] += timedelta(seconds=5)
        monotonic_time[0] += 5
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        assert attempts == 2

        current_time[0] += timedelta(seconds=9)
        monotonic_time[0] += 9
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        assert attempts == 2

        current_time[0] += timedelta(seconds=1)
        monotonic_time[0] += 1
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        assert attempts == 3
        first = coordinator.actions[0]
        first.state = ExecutionActionState.CLOSED

        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator, attempts, failures, loop_contexts

    coordinator, attempts, failures, loop_contexts = asyncio.run(scenario())
    assert attempts == 4
    assert len(coordinator.submissions) == 2
    assert failures == []
    assert coordinator.pre_submit_rejections == [
        {
            "activation_id": "activation-direct",
            "execution_action_id": coordinator.actions[0].execution_action_id,
            "reason_code": "ACCOUNT_FACT_QUERY_FAILED_TIMEOUT",
            "observed_at": NOW + timedelta(minutes=1),
        },
        {
            "activation_id": "activation-direct",
            "execution_action_id": coordinator.actions[0].execution_action_id,
            "reason_code": "ACCOUNT_FACT_QUERY_FAILED_TIMEOUT",
            "observed_at": NOW + timedelta(minutes=1, seconds=5),
        },
    ]
    blocked_states = [
        item["state"]
        for item in coordinator.condition_states
        if item["state"].submission_ready is False
    ]
    assert blocked_states
    assert {
        item.blocking_reason for item in blocked_states
    } == {
        "DIRECT_ACCOUNT_FACT_CHECKING",
        "ACCOUNT_FACT_QUERY_FAILED_TIMEOUT",
    }
    assert loop_contexts == []


def test_cap_rejection_is_recorded_and_does_not_crash_boundary() -> None:
    async def scenario():
        coordinator = _Coordinator(_activation(_spec()))
        legs = materialize_direct_schedule(
            coordinator.activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        failures: list[str] = []

        def reject_schedule(**kwargs):
            coordinator.atomic_calls.append(kwargs)
            raise OrderScheduleCapRejected(
                ((legs[0].execution_action_id, "ACTION_LIMIT_EXCEEDED"),)
            )

        coordinator.consume_order_schedule_atomic = reject_schedule
        boundary = _boundary(
            coordinator,
            failure_sink=lambda _activation_id, exception: failures.append(
                str(exception)
            ),
        )

        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator, failures

    coordinator, failures = asyncio.run(scenario())
    assert failures == []
    assert coordinator.actions == []
    assert len(coordinator.atomic_calls) == 1
    assert coordinator.pre_submit_rejections == [
        {
            "activation_id": "activation-direct",
            "execution_action_id": materialize_direct_schedule(
                coordinator.activation,
                entry_valid_until=NOW + timedelta(hours=1),
            )[0].execution_action_id,
            "reason_code": "ACTION_LIMIT_EXCEEDED",
            "observed_at": NOW + timedelta(minutes=1),
        }
    ]


def test_market_quantity_is_trimmed_to_requested_notional_at_latest_price() -> None:
    market_spec = OrderScheduleSpec(
        price_distribution=SinglePrice(),
        amount_distribution=AmountDistribution(base_notional="100"),
        venue_policy=VenueOrderPolicy(
            order_type=VenueOrderType.MARKET,
            time_in_force=None,
        ),
        entry_conditions=ConditionGroup(
            items=(
                MarkPriceCondition(
                    comparator=NumericComparator.GTE,
                    price="50",
                ),
            )
        ),
        protection_policy=ProtectionPolicy(
            initial_stop=InitialStopSpec(distance_bps="100")
        ),
    )

    async def scenario():
        coordinator = _Coordinator(_activation(market_spec))
        boundary = _boundary(
            coordinator,
            pre_submit_fact_provider=lambda *_args: asyncio.sleep(
                0,
                result=replace(
                    _facts(),
                    conservative_price="101",
                ),
            ),
        )

        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())
    assert len(coordinator.atomic_calls) == 1
    assert coordinator.atomic_calls[0]["action_checks"][0].quantized_quantity == "0.9"
    assert coordinator.actions[0].action_terms["quantity"] == "0.9"
    assert coordinator.submission_checks[0].quantized_quantity == "0.9"
    assert Decimal("0.9") * Decimal("101") <= Decimal("100")


def test_waiting_market_plan_closes_when_fixed_invalidation_price_is_crossed() -> None:
    market_spec = OrderScheduleSpec(
        price_distribution=SinglePrice(),
        amount_distribution=AmountDistribution(base_notional="100"),
        venue_policy=VenueOrderPolicy(
            order_type=VenueOrderType.MARKET,
            time_in_force=None,
        ),
        entry_conditions=ConditionGroup(
            items=(
                MarkPriceCondition(
                    comparator=NumericComparator.GTE,
                    price="120",
                ),
            )
        ),
        protection_policy=ProtectionPolicy(
            initial_stop=InitialStopSpec(distance_bps="100")
        ),
        dynamic_rules=(CancelOnShockRule(invalidation_price="95"),),
    )

    async def scenario():
        coordinator = _Coordinator(_activation(market_spec))
        boundary = _boundary(
            coordinator,
            condition_fact_provider=(
                lambda _activation, _cutoff, observed_at, _moves: _condition_facts(
                    mark="94", observed_at=observed_at
                )
            ),
        )
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())
    assert coordinator.actions == []
    assert coordinator.submissions == []
    assert len(coordinator.invalidations) == 1
    evidence = coordinator.invalidations[0]["evidence"]
    assert evidence["checks"][0]["configured_price"] == "95"
    assert evidence["checks"][0]["observed_mark_price"] == "94"


def test_waiting_short_plan_closes_after_favorable_move_misses_entry() -> None:
    market_spec = OrderScheduleSpec(
        price_distribution=SinglePrice(),
        amount_distribution=AmountDistribution(base_notional="100"),
        venue_policy=VenueOrderPolicy(
            order_type=VenueOrderType.MARKET,
            time_in_force=None,
        ),
        entry_conditions=ConditionGroup(
            items=(
                MarkPriceCondition(
                    comparator=NumericComparator.GTE,
                    price="120",
                ),
            )
        ),
        protection_policy=ProtectionPolicy(
            initial_stop=InitialStopSpec(distance_bps="100")
        ),
        dynamic_rules=(CancelOnShockRule(opportunity_missed_price="96"),),
    )

    async def scenario():
        coordinator = _Coordinator(_activation(market_spec, direction=Direction.SHORT))
        boundary = _boundary(
            coordinator,
            condition_fact_provider=(
                lambda _activation, _cutoff, observed_at, _moves: _condition_facts(
                    mark="95", observed_at=observed_at
                )
            ),
        )
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())
    assert coordinator.actions == []
    assert coordinator.submissions == []
    assert len(coordinator.invalidations) == 1
    evidence = coordinator.invalidations[0]["evidence"]
    assert evidence["checks"][0]["kind"] == "OPPORTUNITY_MISSED_PRICE"
    assert evidence["checks"][0]["configured_price"] == "96"
    assert evidence["checks"][0]["observed_mark_price"] == "95"


def test_unknown_invalidation_fact_blocks_entry_without_cancelling_plan() -> None:
    market_spec = OrderScheduleSpec(
        price_distribution=SinglePrice(),
        amount_distribution=AmountDistribution(base_notional="100"),
        venue_policy=VenueOrderPolicy(
            order_type=VenueOrderType.MARKET,
            time_in_force=None,
        ),
        entry_conditions=ConditionGroup(),
        protection_policy=ProtectionPolicy(
            initial_stop=InitialStopSpec(distance_bps="100")
        ),
        dynamic_rules=(CancelOnShockRule(invalidation_price="95"),),
    )

    async def scenario():
        coordinator = _Coordinator(_activation(market_spec))
        boundary = _boundary(
            coordinator,
            condition_fact_provider=(
                lambda _activation, _cutoff, observed_at, _moves: _condition_facts(
                    mark=None, observed_at=observed_at
                )
            ),
        )
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())
    assert coordinator.invalidations == []
    assert coordinator.actions == []
    assert coordinator.submissions == []


def test_live_boundary_expires_authorized_empty_schedule_at_entry_deadline() -> None:
    async def scenario():
        activation = _activation(_spec()).model_copy(
            update={
                "activation_id": "activation-live-authorized",
                "environment_id": "live-main",
                "environment_kind": EnvironmentKind.LIVE,
                "authority_class": AuthorityClass.LIVE_REAL_CAPITAL,
                "account_ref": "live-account",
            }
        )
        coordinator = _Coordinator(activation)
        boundary = _boundary(
            coordinator,
            now=NOW + timedelta(hours=1),
            environment_id="live-main",
            environment_kind=EnvironmentKind.LIVE,
            authority_class=AuthorityClass.LIVE_REAL_CAPITAL,
            account_ref="live-account",
        )
        boundary.resume(activation.activation_id)
        await boundary.wait_idle()
        boundary.resume(activation.activation_id)
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())
    assert coordinator.expirations == [
        {
            "activation_id": "activation-live-authorized",
            "observed_at": NOW + timedelta(hours=1),
        }
    ]
    assert coordinator.atomic_calls == []
    assert coordinator.submissions == []


def test_submission_is_disabled_until_startup_recovery_finishes() -> None:
    async def scenario():
        enabled = False
        coordinator = _Coordinator(_activation(_spec()))
        boundary = _boundary(coordinator, enabled=lambda: enabled)
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        enabled = True
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())
    assert len(coordinator.atomic_calls) == 1
    assert len(coordinator.submissions) == 1


def test_time_sliced_entry_waits_for_first_release_before_materializing() -> None:
    spec = OrderScheduleSpec(
        entry_program=EntryProgram(
            kind=EntryProgramKind.TIME_SLICED,
            slice_count=3,
            first_slice_delay_seconds=30,
            slice_interval_seconds=60,
        ),
        price_distribution=SinglePrice(),
        amount_distribution=AmountDistribution(base_notional="20"),
        venue_policy=VenueOrderPolicy(
            order_type=VenueOrderType.MARKET,
            time_in_force=None,
        ),
        protection_policy=ProtectionPolicy(
            initial_stop=InitialStopSpec(distance_bps="100"),
            time_exit_seconds=3_600,
        ),
    )

    async def scenario():
        current_time = [NOW + timedelta(seconds=29)]
        coordinator = _Coordinator(_activation(spec))
        boundary = _boundary(coordinator, now=lambda: current_time[0])
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        assert coordinator.atomic_calls == []
        assert coordinator.submissions == []

        current_time[0] = NOW + timedelta(seconds=30)
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())
    assert len(coordinator.atomic_calls) == 1
    assert len(coordinator.actions) == 3
    assert len(coordinator.submissions) == 1


def test_time_sliced_entry_releases_second_leg_after_first_fill() -> None:
    spec = OrderScheduleSpec(
        entry_program=EntryProgram(
            kind=EntryProgramKind.TIME_SLICED,
            slice_count=3,
            first_slice_delay_seconds=0,
            slice_interval_seconds=30,
        ),
        price_distribution=SinglePrice(),
        amount_distribution=AmountDistribution(base_notional="20"),
        venue_policy=VenueOrderPolicy(
            order_type=VenueOrderType.MARKET,
            time_in_force=None,
        ),
        protection_policy=ProtectionPolicy(
            initial_stop=InitialStopSpec(distance_bps="100"),
            time_exit_seconds=3_600,
        ),
    )

    async def scenario():
        base = _activation(spec)
        legs = materialize_direct_schedule(
            base,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        activation = record_direct_fill(
            base,
            entry_action_ref=legs[0].execution_action_id,
            fill_fact_ref="fill-first",
            fill_price="100",
            fill_quantity="0.2",
            fill_time=NOW + timedelta(seconds=1),
            protection_policy=spec.protection_policy.model_dump(mode="json"),
            price_tick_size="0.1",
            quantity_step="0.01",
            observed_at=NOW + timedelta(seconds=1),
        )
        assert activation.entry_opportunity_consumed is False
        coordinator = _Coordinator(activation)
        coordinator.actions.extend(
            [
                _persisted_leg(legs[0], state=ExecutionActionState.CLOSED),
                _persisted_leg(legs[1], state=ExecutionActionState.READY),
                _persisted_leg(legs[2], state=ExecutionActionState.READY),
            ]
        )
        boundary = _boundary(
            coordinator,
            now=NOW + timedelta(seconds=31),
        )
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator, legs

    coordinator, legs = asyncio.run(scenario())
    assert coordinator.submissions == [legs[1].execution_action_id]
    assert coordinator.actions[2].state is ExecutionActionState.READY


def test_multi_leg_entry_is_consumed_only_after_every_leg_has_filled() -> None:
    base = _activation(_spec())
    legs = materialize_direct_schedule(
        base,
        entry_valid_until=NOW + timedelta(hours=1),
    )
    activation = base
    consumed_states: list[bool] = []
    for index, leg in enumerate(legs):
        activation = record_direct_fill(
            activation,
            entry_action_ref=leg.execution_action_id,
            fill_fact_ref=f"fill-{index}",
            fill_price="100",
            fill_quantity="0.2",
            fill_time=NOW + timedelta(seconds=index),
            protection_policy=(
                base.order_schedule_snapshot.schedule_spec.protection_policy.model_dump(
                    mode="json"
                )
            ),
            price_tick_size="0.1",
            quantity_step="0.01",
            observed_at=NOW + timedelta(seconds=index),
        )
        consumed_states.append(activation.entry_opportunity_consumed)

    assert consumed_states == [False, False, True]


def test_expired_schedule_rejects_ready_legs_without_submitting() -> None:
    async def scenario():
        activation = _activation(_spec())
        coordinator = _Coordinator(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        coordinator.actions.extend(
            _persisted_leg(item, state=ExecutionActionState.READY) for item in legs
        )
        boundary = _boundary(coordinator, now=NOW + timedelta(hours=2))
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())
    assert len(coordinator.rejections) == 3
    assert coordinator.submissions == []


def test_adverse_mark_shock_cancels_open_leg_and_holds_remaining_legs() -> None:
    async def scenario():
        enabled = False
        activation = _activation(_spec(shock=True))
        coordinator = _Coordinator(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        coordinator.actions.extend(
            [
                _persisted_leg(legs[0], state=ExecutionActionState.OPEN),
                *(
                    _persisted_leg(item, state=ExecutionActionState.READY)
                    for item in legs[1:]
                ),
            ]
        )
        boundary = _boundary(coordinator, enabled=lambda: enabled)
        cutoff_ns = int((NOW + timedelta(minutes=1)).timestamp() * 1_000_000_000)
        boundary.record_mark(
            "activation-direct",
            SimpleNamespace(ts_event=cutoff_ns - 5_000_000_000, value="100"),
        )
        boundary.record_mark(
            "activation-direct",
            SimpleNamespace(ts_event=cutoff_ns, value="98"),
        )
        enabled = True
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator, legs

    coordinator, legs = asyncio.run(scenario())
    assert coordinator.cancel_targets == [legs[0].execution_action_id]
    assert coordinator.cancel_endpoints == ["ORDINARY"]
    assert coordinator.submissions != [legs[1].execution_action_id]
    assert len(coordinator.submissions) == 1  # only the persisted cancel action


def test_shock_is_rechecked_after_delayed_fact_provider_before_submission() -> None:
    async def scenario():
        enabled = False
        activation = _activation(_spec(shock=True))
        coordinator = _Coordinator(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        coordinator.actions.extend(
            [
                _persisted_leg(legs[0], state=ExecutionActionState.CLOSED),
                *(
                    _persisted_leg(item, state=ExecutionActionState.READY)
                    for item in legs[1:]
                ),
            ]
        )
        cutoff_ns = int((NOW + timedelta(minutes=1)).timestamp() * 1_000_000_000)
        boundary: DirectScheduleBoundary

        async def delayed_facts(*_args):
            boundary.record_mark(
                "activation-direct",
                SimpleNamespace(ts_event=cutoff_ns, value="98"),
            )
            await asyncio.sleep(0)
            return _facts()

        boundary = _boundary(
            coordinator,
            enabled=lambda: enabled,
            pre_submit_fact_provider=delayed_facts,
        )
        boundary.record_mark(
            "activation-direct",
            SimpleNamespace(ts_event=cutoff_ns - 6_000_000_000, value="100"),
        )
        boundary.record_mark(
            "activation-direct",
            SimpleNamespace(ts_event=cutoff_ns - 1_000_000_000, value="100"),
        )
        enabled = True
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())
    assert coordinator.submissions == []
    assert len(coordinator.rejections) == 2
    assert {reason for _action_id, reason in coordinator.rejections} == {
        "DIRECT_ENTRY_SHOCK"
    }


def test_expiry_is_rechecked_after_delayed_fact_provider_before_submission() -> None:
    async def scenario():
        activation = _activation(_spec())
        coordinator = _Coordinator(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        coordinator.actions.extend(
            [
                _persisted_leg(legs[0], state=ExecutionActionState.CLOSED),
                *(
                    _persisted_leg(item, state=ExecutionActionState.READY)
                    for item in legs[1:]
                ),
            ]
        )
        current_time = [NOW + timedelta(minutes=1)]

        async def delayed_facts(*_args):
            current_time[0] = NOW + timedelta(hours=2)
            await asyncio.sleep(0)
            return _facts()

        boundary = _boundary(
            coordinator,
            now=lambda: current_time[0],
            pre_submit_fact_provider=delayed_facts,
        )
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator, legs

    coordinator, legs = asyncio.run(scenario())
    assert coordinator.submissions == []
    assert coordinator.rejections == [
        (legs[1].execution_action_id, "DIRECT_ENTRY_REMAINING_EXPIRED"),
        (legs[2].execution_action_id, "DIRECT_ENTRY_REMAINING_EXPIRED"),
    ]


def test_first_shock_cancel_permanently_rejects_remaining_legs() -> None:
    async def scenario():
        enabled = False
        activation = _activation(_spec(shock=True))
        coordinator = _Coordinator(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        coordinator.actions.extend(
            [
                _persisted_leg(legs[0], state=ExecutionActionState.OPEN),
                *(
                    _persisted_leg(item, state=ExecutionActionState.READY)
                    for item in legs[1:]
                ),
            ]
        )
        boundary = _boundary(coordinator, enabled=lambda: enabled)
        cutoff_ns = int((NOW + timedelta(minutes=1)).timestamp() * 1_000_000_000)
        boundary.record_mark(
            "activation-direct",
            SimpleNamespace(ts_event=cutoff_ns - 5_000_000_000, value="100"),
        )
        boundary.record_mark(
            "activation-direct",
            SimpleNamespace(ts_event=cutoff_ns, value="98"),
        )
        enabled = True
        boundary.resume("activation-direct")
        await boundary.wait_idle()

        first = coordinator.actions[0]
        cancel = next(
            action
            for action in coordinator.actions
            if action.action_kind is ExecutionActionKind.CANCEL
        )
        first.state = ExecutionActionState.CLOSED
        cancel.state = ExecutionActionState.CLOSED
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator, legs

    coordinator, legs = asyncio.run(scenario())
    assert coordinator.cancel_targets == [legs[0].execution_action_id]
    assert coordinator.rejections == [
        (legs[1].execution_action_id, "DIRECT_ENTRY_SHOCK"),
        (legs[2].execution_action_id, "DIRECT_ENTRY_SHOCK"),
    ]
    assert len(coordinator.submissions) == 1


def test_time_sliced_resting_entry_expires_each_slice_before_releasing_next() -> (
    None
):
    async def scenario():
        current_time = [NOW + timedelta(seconds=16)]
        activation = _activation(_time_sliced_resting_spec())
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        coordinator = _Coordinator(activation)
        coordinator.actions.extend(
            [
                _persisted_leg(
                    legs[0],
                    state=ExecutionActionState.OPEN,
                    call_started_at=NOW,
                ),
                _persisted_leg(legs[1], state=ExecutionActionState.READY),
            ]
        )

        async def account_facts(*_args):
            return replace(_facts(), checked_at=current_time[0])

        async def risk_facts(*_args):
            return replace(_risk_facts(), checked_at=current_time[0])

        boundary = _boundary(
            coordinator,
            now=lambda: current_time[0],
            pre_submit_fact_provider=account_facts,
            risk_fact_provider=risk_facts,
        )
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        first_cancel = next(
            action
            for action in coordinator.actions
            if action.action_kind is ExecutionActionKind.CANCEL
        )
        assert coordinator.cancel_targets == [legs[0].execution_action_id]
        assert coordinator.rejections == []
        assert ":DIRECT_TIME_SLICE_EXPIRED:" in str(
            first_cancel.action_terms["causation_ref"]
        )

        coordinator.actions[0].state = ExecutionActionState.CLOSED
        first_cancel.state = ExecutionActionState.CLOSED
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        assert coordinator.submissions[-1] == legs[1].execution_action_id
        second = coordinator.actions[1]
        assert second.state is ExecutionActionState.SUBMITTING
        assert second.call_started_at == current_time[0]

        second.state = ExecutionActionState.OPEN
        current_time[0] = NOW + timedelta(seconds=32)
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        second_cancel = [
            action
            for action in coordinator.actions
            if action.action_kind is ExecutionActionKind.CANCEL
        ][-1]
        assert coordinator.cancel_targets == [
            legs[0].execution_action_id,
            legs[1].execution_action_id,
        ]
        assert coordinator.rejections == []

        second.state = ExecutionActionState.CLOSED
        second_cancel.state = ExecutionActionState.CLOSED
        current_time[0] = NOW + timedelta(seconds=33)
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())
    assert coordinator.remaining_expirations == [
        {
            "activation_id": "activation-direct",
            "source_cutoff": NOW + timedelta(seconds=31),
            "observed_at": NOW + timedelta(seconds=33),
        }
    ]


def test_partial_fill_without_working_protection_cancels_its_open_remainder() -> None:
    async def scenario():
        activation = _activation(_spec()).model_copy(update={"has_entry_fill": True})
        coordinator = _Coordinator(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        first = _persisted_leg(legs[0], state=ExecutionActionState.OPEN)
        coordinator.actions.extend(
            [
                first,
                *(
                    _persisted_leg(item, state=ExecutionActionState.READY)
                    for item in legs[1:]
                ),
            ]
        )
        coordinator.venue_facts[first.execution_action_id] = (
            _fact(
                "partial-fill",
                VenueFactKind.FILL,
                {
                    "trade_id": "partial-trade",
                    "last_quantity": "0.1",
                    "leaves_quantity": "0.1",
                },
            ),
        )
        boundary = _boundary(coordinator)
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator, legs

    coordinator, legs = asyncio.run(scenario())
    assert coordinator.cancel_targets == [legs[0].execution_action_id]
    assert coordinator.cancel_endpoints == ["ORDINARY"]
    assert coordinator.rejections == []
    assert coordinator.actions[1].state is ExecutionActionState.READY


def test_failed_protection_keeps_all_later_direct_legs_blocked() -> None:
    async def scenario():
        activation = _activation(_spec()).model_copy(update={"has_entry_fill": True})
        coordinator = _Coordinator(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        first = _persisted_leg(legs[0], state=ExecutionActionState.CLOSED)
        coordinator.actions.extend(
            [
                first,
                *(
                    _persisted_leg(item, state=ExecutionActionState.READY)
                    for item in legs[1:]
                ),
            ]
        )
        fill = _fact(
            "entry-fill",
            VenueFactKind.FILL,
            {
                "trade_id": "entry-trade",
                "last_quantity": "0.1",
                "leaves_quantity": "0",
            },
        )
        coordinator.venue_facts[first.execution_action_id] = (fill,)
        coordinator.actions.append(
            SimpleNamespace(
                execution_action_id="protection-not-submitted",
                activation_id="activation-direct",
                source_identity="activation-direct:PROTECTION:entry-fill",
                client_order_id="protection-client-id",
                action_kind=ExecutionActionKind.PROTECTION,
                action_terms={
                    "quantity": "0.1",
                    "execution_context": {"fill_fact_ref": fill.venue_fact_id},
                },
                state=ExecutionActionState.NOT_SUBMITTED,
                state_version=1,
            )
        )
        boundary = _boundary(coordinator)
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())
    assert coordinator.submissions == []
    assert coordinator.rejections == []


def test_expired_open_leg_uses_risk_reduction_facts_for_cancel() -> None:
    async def scenario():
        activation = _activation(_spec())
        coordinator = _Coordinator(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        coordinator.actions.extend(
            [
                _persisted_leg(legs[0], state=ExecutionActionState.OPEN),
                *(
                    _persisted_leg(item, state=ExecutionActionState.READY)
                    for item in legs[1:]
                ),
            ]
        )

        async def forbidden_entry_facts(*_args):
            raise AssertionError("expired cancellation must not query new-risk facts")

        boundary = _boundary(
            coordinator,
            now=NOW + timedelta(hours=2),
            pre_submit_fact_provider=forbidden_entry_facts,
        )
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator, legs

    coordinator, legs = asyncio.run(scenario())
    assert coordinator.cancel_targets == [legs[0].execution_action_id]
    assert coordinator.cancel_endpoints == ["ORDINARY"]
    assert coordinator.submission_checks[0].risk_class.value == "RISK_NEUTRAL"


def test_existing_cancel_responsibility_blocks_stale_duplicate_cancel() -> None:
    async def scenario():
        activation = _activation(_spec())
        coordinator = _Coordinator(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        coordinator.actions.extend(
            [
                _persisted_leg(legs[0], state=ExecutionActionState.OPEN),
                *(
                    _persisted_leg(item, state=ExecutionActionState.READY)
                    for item in legs[1:]
                ),
                SimpleNamespace(
                    execution_action_id="cancel-existing",
                    activation_id="activation-direct",
                    source_identity="activation-direct:CANCEL:existing",
                    client_order_id=None,
                    action_kind=ExecutionActionKind.CANCEL,
                    action_terms={"action_profile": "CANCEL_ORDER"},
                    cancel_target={
                        "client_order_id": legs[0].client_order_id,
                        "endpoint": "ORDINARY",
                    },
                    state=ExecutionActionState.SUBMITTING,
                    state_version=1,
                ),
            ]
        )
        boundary = _boundary(coordinator, now=NOW + timedelta(hours=2))
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())
    assert len(coordinator.rejections) == 2
    assert coordinator.cancel_targets == []
    assert coordinator.submissions == []


def test_gtd_deadline_expires_remaining_legs_before_plan_deadline() -> None:
    async def scenario():
        expire_at = NOW + timedelta(minutes=20)
        activation = _activation(_spec(expire_at=expire_at))
        coordinator = _Coordinator(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        coordinator.actions.extend(
            _persisted_leg(item, state=ExecutionActionState.READY) for item in legs
        )
        boundary = _boundary(coordinator, now=NOW + timedelta(minutes=30))
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator, expire_at

    coordinator, expire_at = asyncio.run(scenario())
    assert len(coordinator.rejections) == 3
    assert coordinator.submissions == []
    assert coordinator.expirations == []
    assert coordinator.remaining_expirations == [
        {
            "activation_id": "activation-direct",
            "source_cutoff": expire_at,
            "observed_at": NOW + timedelta(minutes=30),
        }
    ]


def test_gtd_deadline_consumes_entry_and_cancels_working_order() -> None:
    async def scenario():
        expire_at = NOW + timedelta(minutes=20)
        activation = _activation(_spec(expire_at=expire_at))
        coordinator = _Coordinator(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        coordinator.actions.extend(
            [
                _persisted_leg(legs[0], state=ExecutionActionState.OPEN),
                *(
                    _persisted_leg(item, state=ExecutionActionState.READY)
                    for item in legs[1:]
                ),
            ]
        )
        boundary = _boundary(coordinator, now=NOW + timedelta(minutes=30))
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator, legs, expire_at

    coordinator, legs, expire_at = asyncio.run(scenario())
    assert coordinator.expirations == []
    assert coordinator.remaining_expirations == [
        {
            "activation_id": "activation-direct",
            "source_cutoff": expire_at,
            "observed_at": NOW + timedelta(minutes=30),
        }
    ]
    assert coordinator.cancel_targets == [legs[0].execution_action_id]
    assert coordinator.cancel_endpoints == ["ORDINARY"]


@pytest.mark.parametrize(
    ("lead_seconds", "should_submit"),
    ((599, False), (600, False), (601, True)),
)
def test_gtd_lead_time_is_revalidated_before_late_serial_submission(
    lead_seconds: int,
    should_submit: bool,
) -> None:
    async def scenario():
        checked_at = NOW + timedelta(minutes=1)
        activation = _activation(
            _spec(expire_at=checked_at + timedelta(seconds=lead_seconds))
        )
        coordinator = _Coordinator(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        coordinator.actions.extend(
            _persisted_leg(item, state=ExecutionActionState.READY) for item in legs
        )
        boundary = _boundary(coordinator, now=checked_at)
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator, legs

    coordinator, legs = asyncio.run(scenario())
    if should_submit:
        assert coordinator.submissions == [legs[0].execution_action_id]
        assert coordinator.rejections == []
    else:
        assert coordinator.submissions == []
        assert coordinator.rejections == [
            (item.execution_action_id, "DIRECT_GTD_EXPIRY_TOO_SOON") for item in legs
        ]


def test_later_leg_waits_when_current_entry_condition_is_false() -> None:
    async def scenario():
        activation = _activation(_spec(condition_price="50"))
        coordinator = _Coordinator(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        coordinator.actions.extend(
            [
                _persisted_leg(legs[0], state=ExecutionActionState.CLOSED),
                *(
                    _persisted_leg(item, state=ExecutionActionState.READY)
                    for item in legs[1:]
                ),
            ]
        )

        def later_conditions(*_args):
            return _condition_facts(mark="1", observed_at=_args[2])

        boundary = _boundary(
            coordinator,
            condition_fact_provider=later_conditions,
        )
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator, legs

    coordinator, legs = asyncio.run(scenario())
    assert coordinator.submissions == []
    assert coordinator.actions[1].state is ExecutionActionState.READY


@pytest.mark.parametrize("first_mark", ("1", None))
def test_later_leg_recovers_from_false_or_unknown_after_runtime_restart(
    first_mark: str | None,
) -> None:
    async def scenario():
        activation = _activation(_spec(condition_price="50"))
        coordinator = _Coordinator(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        coordinator.actions.extend(
            [
                _persisted_leg(legs[0], state=ExecutionActionState.CLOSED),
                *(
                    _persisted_leg(item, state=ExecutionActionState.READY)
                    for item in legs[1:]
                ),
            ]
        )

        def first_conditions(*_args):
            return _condition_facts(mark=first_mark, observed_at=_args[2])

        before_restart = _boundary(
            coordinator,
            condition_fact_provider=first_conditions,
        )
        before_restart.resume("activation-direct")
        await before_restart.wait_idle()
        assert coordinator.submissions == []
        before_restart.close()

        def recovered_conditions(*_args):
            return _condition_facts(mark="100", observed_at=_args[2])

        after_restart = _boundary(
            coordinator,
            condition_fact_provider=recovered_conditions,
        )
        after_restart.resume("activation-direct")
        await after_restart.wait_idle()
        return coordinator, legs

    coordinator, legs = asyncio.run(scenario())
    assert coordinator.submissions == [legs[1].execution_action_id]


def test_later_leg_submits_when_current_entry_condition_is_still_true() -> None:
    async def scenario():
        activation = _activation(_spec(condition_price="50"))
        coordinator = _Coordinator(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        coordinator.actions.extend(
            [
                _persisted_leg(legs[0], state=ExecutionActionState.CLOSED),
                *(
                    _persisted_leg(item, state=ExecutionActionState.READY)
                    for item in legs[1:]
                ),
            ]
        )
        boundary = _boundary(coordinator)
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator, legs

    coordinator, legs = asyncio.run(scenario())
    assert coordinator.submissions == [legs[1].execution_action_id]


def test_expire_remaining_does_not_start_before_the_first_external_submission() -> None:
    async def scenario():
        activation = _activation(_spec(expire_remaining_seconds=300))
        coordinator = _Coordinator(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        coordinator.actions.extend(
            _persisted_leg(item, state=ExecutionActionState.READY) for item in legs
        )
        boundary = _boundary(coordinator, now=NOW + timedelta(minutes=10))
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator, legs

    coordinator, legs = asyncio.run(scenario())
    assert coordinator.rejections == []
    assert coordinator.submissions == [legs[0].execution_action_id]


def test_expire_remaining_uses_persisted_first_submission_time_after_restart() -> None:
    async def scenario():
        activation = _activation(_spec(expire_remaining_seconds=300))
        coordinator = _Coordinator(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        coordinator.actions.extend(
            [
                _persisted_leg(
                    legs[0],
                    state=ExecutionActionState.OPEN,
                    call_started_at=NOW + timedelta(minutes=1),
                ),
                *(
                    _persisted_leg(item, state=ExecutionActionState.READY)
                    for item in legs[1:]
                ),
            ]
        )
        boundary = _boundary(coordinator, now=NOW + timedelta(minutes=7))
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator, legs

    coordinator, legs = asyncio.run(scenario())
    assert coordinator.rejections == [
        (legs[1].execution_action_id, "DIRECT_ENTRY_REMAINING_EXPIRED"),
        (legs[2].execution_action_id, "DIRECT_ENTRY_REMAINING_EXPIRED"),
    ]
    assert coordinator.cancel_targets == [legs[0].execution_action_id]
    assert coordinator.expirations == []
    assert coordinator.remaining_expirations == [
        {
            "activation_id": "activation-direct",
            "source_cutoff": NOW + timedelta(minutes=6),
            "observed_at": NOW + timedelta(minutes=7),
        }
    ]


def test_global_time_exit_stops_and_cancels_remaining_entry_before_position_exit() -> (
    None
):
    async def scenario():
        activation = record_direct_fill(
            _activation(_spec()),
            entry_action_ref="entry-first",
            fill_fact_ref="fill-first",
            fill_price="100",
            fill_quantity="0.2",
            fill_time=NOW,
            protection_policy={
                "initial_stop": {
                    "distance_bps": "100",
                    "trigger_source": "MARK_PRICE",
                    "coverage": "EACH_CONFIRMED_FILL",
                },
                "take_profit_ladder": None,
                "time_exit_seconds": 60,
            },
            price_tick_size="0.1",
            quantity_step="0.01",
            observed_at=NOW,
        )
        coordinator = _Coordinator(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        coordinator.actions.extend(
            [
                _persisted_leg(legs[0], state=ExecutionActionState.CLOSED),
                _persisted_leg(
                    legs[1],
                    state=ExecutionActionState.OPEN,
                    call_started_at=NOW + timedelta(seconds=10),
                ),
                _persisted_leg(legs[2], state=ExecutionActionState.READY),
            ]
        )
        boundary = _boundary(coordinator, now=NOW + timedelta(seconds=61))
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator, legs

    coordinator, legs = asyncio.run(scenario())
    assert coordinator.rejections == [
        (legs[2].execution_action_id, "DIRECT_ENTRY_REMAINING_EXPIRED"),
    ]
    assert coordinator.cancel_targets == [legs[1].execution_action_id]
    assert coordinator.cancel_endpoints == ["ORDINARY"]


def test_limit_cap_keeps_the_more_conservative_live_price_and_full_plan_margin() -> (
    None
):
    async def scenario():
        coordinator = _Coordinator(_activation(_spec()))

        async def conservative_facts(*_args):
            facts = _facts()
            return replace(facts, conservative_price="150")

        boundary = _boundary(
            coordinator,
            pre_submit_fact_provider=conservative_facts,
        )
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())
    checks = coordinator.atomic_calls[0]["action_checks"]
    assert all(check.conservative_price == "150" for check in checks)
    for check in checks:
        assert Decimal(check.activation_current_margin) == (
            Decimal(check.economic_action_prior_notional) / Decimal("5")
        )


def test_brief_price_move_gap_does_not_cancel_open_leg_during_management() -> None:
    async def scenario():
        enabled = False
        activation = _activation(_spec(shock=True))
        coordinator = _Coordinator(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        coordinator.actions.extend(
            [
                _persisted_leg(legs[0], state=ExecutionActionState.OPEN),
                *(
                    _persisted_leg(item, state=ExecutionActionState.READY)
                    for item in legs[1:]
                ),
            ]
        )
        cutoff_ns = int((NOW + timedelta(minutes=1)).timestamp() * 1_000_000_000)
        boundary = _boundary(coordinator, enabled=lambda: enabled)
        boundary.record_mark(
            "activation-direct",
            SimpleNamespace(ts_event=cutoff_ns - 10_000_000_000, value="100"),
        )
        boundary.record_mark(
            "activation-direct",
            SimpleNamespace(ts_event=cutoff_ns - 5_000_000_000, value="99.5"),
        )
        enabled = True
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())
    assert coordinator.cancel_targets == []
    assert coordinator.submissions == []


def test_stale_price_move_makes_shock_guard_fail_closed_and_cancels_open_leg() -> None:
    async def scenario():
        enabled = False
        activation = _activation(_spec(shock=True))
        coordinator = _Coordinator(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        coordinator.actions.extend(
            [
                _persisted_leg(legs[0], state=ExecutionActionState.OPEN),
                *(
                    _persisted_leg(item, state=ExecutionActionState.READY)
                    for item in legs[1:]
                ),
            ]
        )
        cutoff_ns = int((NOW + timedelta(minutes=1)).timestamp() * 1_000_000_000)
        boundary = _boundary(coordinator, enabled=lambda: enabled)
        boundary.record_mark(
            "activation-direct",
            SimpleNamespace(ts_event=cutoff_ns - 20_000_000_000, value="100"),
        )
        boundary.record_mark(
            "activation-direct",
            SimpleNamespace(ts_event=cutoff_ns - 15_000_000_000, value="98"),
        )
        enabled = True
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())
    assert len(coordinator.cancel_targets) == 1
    assert len(coordinator.submissions) == 1  # only the persisted cancel action
    cancel = next(
        action
        for action in coordinator.actions
        if action.action_kind is ExecutionActionKind.CANCEL
    )
    assert "DIRECT_ENTRY_SHOCK_STATUS_UNKNOWN" in cancel.source_identity


def _fact(
    fact_id: str,
    kind: VenueFactKind,
    payload: dict[str, object],
) -> SimpleNamespace:
    return SimpleNamespace(
        venue_fact_id=fact_id,
        kind=kind,
        payload=payload,
        source_time=NOW,
        cutoff=NOW,
        received_at=NOW,
    )


def test_nonzero_reduction_position_refreshes_every_ten_seconds_or_on_fill() -> None:
    async def scenario():
        activation = _activation(_spec()).model_copy(update={"has_entry_fill": True})
        coordinator = _Coordinator(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        coordinator.actions.extend(
            [
                _persisted_leg(legs[0], state=ExecutionActionState.OPEN),
                *(
                    _persisted_leg(item, state=ExecutionActionState.READY)
                    for item in legs[1:]
                ),
            ]
        )
        reduction = SimpleNamespace(
            execution_action_id="risk-reduction-filled",
            activation_id=activation.activation_id,
            source_identity="activation-direct:EXIT:filled",
            client_order_id="risk-reduction-client",
            action_kind=ExecutionActionKind.EXIT,
            action_terms={"quantity": "0.1"},
            state=ExecutionActionState.CLOSED,
            state_version=1,
        )
        coordinator.actions.append(reduction)
        coordinator.venue_facts[reduction.execution_action_id] = (
            _fact(
                "risk-reduction-fill",
                VenueFactKind.FILL,
                {
                    "trade_id": "risk-reduction-trade",
                    "last_quantity": "0.1",
                    "leaves_quantity": "0",
                },
            ),
        )
        current_time = [NOW + timedelta(minutes=1)]
        monotonic_time = [100.0]
        risk_calls = 0
        failures: list[str] = []
        asyncio.get_running_loop().set_exception_handler(lambda _loop, _context: None)

        async def risk_provider(*_args):
            nonlocal risk_calls
            risk_calls += 1
            if risk_calls == 1:
                raise ProductPreSubmitRejected("ACCOUNT_FACT_QUERY_FAILED_TIMEOUT")
            return _risk_facts(
                current_abs_position="0.1",
                position_fact=object(),
            )

        boundary = _boundary(
            coordinator,
            now=lambda: current_time[0],
            monotonic_now=lambda: monotonic_time[0],
            risk_fact_provider=risk_provider,
            failure_sink=lambda _activation_id, exception: failures.append(
                str(exception)
            ),
        )
        boundary.resume(activation.activation_id)
        for _ in range(4):
            await asyncio.sleep(0)
        assert risk_calls == 1

        current_time[0] += timedelta(seconds=1)
        monotonic_time[0] += 1
        for _ in range(100):
            boundary.resume(activation.activation_id)
            await boundary.wait_idle()
        assert risk_calls == 1

        current_time[0] += timedelta(seconds=1)
        monotonic_time[0] += 1
        boundary.resume(
            activation.activation_id,
            force_risk_refresh=True,
        )
        await boundary.wait_idle()
        assert risk_calls == 2

        current_time[0] += timedelta(seconds=9)
        monotonic_time[0] += 9
        boundary.resume(activation.activation_id)
        await boundary.wait_idle()
        assert risk_calls == 2

        current_time[0] += timedelta(seconds=1)
        monotonic_time[0] += 1
        boundary.resume(activation.activation_id)
        await boundary.wait_idle()
        return coordinator, risk_calls, failures

    coordinator, risk_calls, failures = asyncio.run(scenario())
    assert risk_calls == 3
    assert failures == ["ACCOUNT_FACT_QUERY_FAILED_TIMEOUT"]
    assert coordinator.submissions == []


def test_superseded_risk_facts_defer_without_reporting_background_failure() -> None:
    async def scenario():
        activation = _activation(_spec()).model_copy(update={"has_entry_fill": True})
        coordinator = _Coordinator(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        coordinator.actions.extend(
            _persisted_leg(item, state=ExecutionActionState.OPEN) for item in legs
        )
        reduction = SimpleNamespace(
            execution_action_id="risk-reduction-filled",
            activation_id=activation.activation_id,
            source_identity="activation-direct:EXIT:filled",
            client_order_id="risk-reduction-client",
            action_kind=ExecutionActionKind.EXIT,
            action_terms={"quantity": "0.1"},
            state=ExecutionActionState.CLOSED,
            state_version=1,
        )
        coordinator.actions.append(reduction)
        coordinator.venue_facts[reduction.execution_action_id] = (
            _fact(
                "risk-reduction-fill",
                VenueFactKind.FILL,
                {
                    "trade_id": "risk-reduction-trade",
                    "last_quantity": "0.1",
                    "leaves_quantity": "0",
                },
            ),
        )
        current_time = [NOW + timedelta(minutes=1)]
        monotonic_time = [100.0]
        risk_calls = 0
        failures: list[str] = []

        async def risk_provider(*_args):
            nonlocal risk_calls
            risk_calls += 1
            if risk_calls == 1:
                raise ProductPreSubmitRejected("ACCOUNT_FACT_SUPERSEDED")
            return _risk_facts(current_abs_position="0.1", position_fact=object())

        boundary = _boundary(
            coordinator,
            now=lambda: current_time[0],
            monotonic_now=lambda: monotonic_time[0],
            risk_fact_provider=risk_provider,
            failure_sink=lambda _activation_id, exception: failures.append(
                str(exception)
            ),
        )
        boundary.resume(activation.activation_id)
        await boundary.wait_idle()
        assert risk_calls == 1
        assert failures == []
        assert coordinator.submissions == []

        monotonic_time[0] += 4
        boundary.resume(activation.activation_id)
        await boundary.wait_idle()
        assert risk_calls == 1

        monotonic_time[0] += 1
        boundary.resume(activation.activation_id)
        await boundary.wait_idle()
        return coordinator, risk_calls, failures

    coordinator, risk_calls, failures = asyncio.run(scenario())
    assert risk_calls == 2
    assert failures == []
    assert coordinator.submissions == []


def test_filled_protection_that_flattens_position_ends_the_entry_cycle() -> None:
    async def scenario():
        activation = _activation(_spec()).model_copy(update={"has_entry_fill": True})
        coordinator = _Coordinator(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        first = _persisted_leg(legs[0], state=ExecutionActionState.OPEN)
        coordinator.actions.extend(
            [
                first,
                *(
                    _persisted_leg(item, state=ExecutionActionState.READY)
                    for item in legs[1:]
                ),
            ]
        )
        fill = _fact(
            "entry-fill",
            VenueFactKind.FILL,
            {
                "trade_id": "entry-trade",
                # Binance stream quantities retain venue scale while persisted
                # action terms are canonicalized (for example 0.1000 vs 0.1).
                "last_quantity": f"{Decimal(legs[0].leg.quantity):.4f}",
                "leaves_quantity": "0",
            },
        )
        coordinator.venue_facts[first.execution_action_id] = (
            fill,
            _fact(
                "entry-commission",
                VenueFactKind.COMMISSION,
                {"trade_id": "entry-trade"},
            ),
        )
        protection = SimpleNamespace(
            execution_action_id="protection-filled",
            activation_id="activation-direct",
            source_identity="activation-direct:PROTECTION:entry-fill",
            client_order_id="protection-client-id",
            action_kind=ExecutionActionKind.PROTECTION,
            action_terms={
                "quantity": legs[0].leg.quantity,
                "execution_context": {"fill_fact_ref": fill.venue_fact_id},
            },
            state=ExecutionActionState.OPEN,
            state_version=1,
        )
        coordinator.actions.append(protection)
        coordinator.venue_facts[protection.execution_action_id] = (
            _fact(
                "protection-fill",
                VenueFactKind.FILL,
                {
                    "trade_id": "protection-trade",
                    "last_quantity": legs[0].leg.quantity,
                    "leaves_quantity": "0",
                },
            ),
            _fact(
                "protection-commission",
                VenueFactKind.COMMISSION,
                {"trade_id": "protection-trade"},
            ),
        )
        position_fact = SimpleNamespace(venue_fact_id="position-zero")

        async def risk_provider(*_args):
            return replace(_risk_facts(), position_fact=position_fact)

        boundary = _boundary(coordinator, risk_fact_provider=risk_provider)
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator, legs

    coordinator, legs = asyncio.run(scenario())
    assert coordinator.closures[0]["execution_action_id"] == legs[0].execution_action_id
    assert coordinator.submissions == []
    assert coordinator.rejections == [
        (legs[1].execution_action_id, "DIRECT_ENTRY_CYCLE_CLOSED"),
        (legs[2].execution_action_id, "DIRECT_ENTRY_CYCLE_CLOSED"),
    ]


def test_risk_reduction_with_missing_position_fact_holds_remaining_leg_unknown() -> (
    None
):
    async def scenario():
        activation = _activation(_spec()).model_copy(update={"has_entry_fill": True})
        coordinator = _Coordinator(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        coordinator.actions.extend(
            _persisted_leg(
                item,
                state=(
                    ExecutionActionState.CLOSED
                    if index == 0
                    else ExecutionActionState.READY
                ),
            )
            for index, item in enumerate(legs)
        )
        reduction = SimpleNamespace(
            execution_action_id="take-profit-filled",
            activation_id="activation-direct",
            source_identity="activation-direct:TAKE_PROFIT:fill-first",
            client_order_id="take-profit-client-id",
            action_kind=ExecutionActionKind.TAKE_PROFIT,
            action_terms={"quantity": "0.1"},
            state=ExecutionActionState.OPEN,
            state_version=1,
        )
        coordinator.actions.append(reduction)
        coordinator.venue_facts[reduction.execution_action_id] = (
            _fact(
                "take-profit-fill",
                VenueFactKind.FILL,
                {
                    "trade_id": "tp-trade",
                    "last_quantity": "0.1",
                    "leaves_quantity": "0",
                },
            ),
        )
        boundary = _boundary(
            coordinator,
            risk_fact_provider=lambda *_args: asyncio.sleep(0, result=_risk_facts()),
        )
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())
    assert coordinator.submissions == []
    assert coordinator.rejections == []
    assert coordinator.actions[1].state is ExecutionActionState.READY


def test_restart_advances_to_next_leg_only_after_terminal_entry_is_still_protected() -> (
    None
):
    async def scenario():
        activation = _activation(_spec()).model_copy(update={"has_entry_fill": True})
        coordinator = _Coordinator(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        first = _persisted_leg(legs[0], state=ExecutionActionState.OPEN)
        coordinator.actions.extend(
            [
                first,
                *(
                    _persisted_leg(item, state=ExecutionActionState.READY)
                    for item in legs[1:]
                ),
            ]
        )
        fill = _fact(
            "entry-fill",
            VenueFactKind.FILL,
            {
                "trade_id": "entry-trade",
                "last_quantity": legs[0].leg.quantity,
                "leaves_quantity": "0",
            },
        )
        coordinator.venue_facts[first.execution_action_id] = (
            fill,
            _fact(
                "entry-commission",
                VenueFactKind.COMMISSION,
                {"trade_id": "entry-trade"},
            ),
            _fact(
                "entry-terminal",
                VenueFactKind.ORDER_STATE,
                {
                    "status": "FILLED",
                    "cumulative_filled_quantity": legs[0].leg.quantity,
                },
            ),
        )
        protection = SimpleNamespace(
            execution_action_id="protection-working",
            activation_id="activation-direct",
            source_identity="activation-direct:PROTECTION:entry-fill",
            client_order_id="protection-client-id",
            action_kind=ExecutionActionKind.PROTECTION,
            action_terms={
                "quantity": legs[0].leg.quantity,
                "execution_context": {"fill_fact_ref": fill.venue_fact_id},
            },
            state=ExecutionActionState.OPEN,
            state_version=1,
        )
        coordinator.actions.append(protection)
        coordinator.venue_facts[protection.execution_action_id] = (
            _fact(
                "protection-working-fact",
                VenueFactKind.ORDER_STATE,
                {"status": "WORKING"},
            ),
        )
        position_fact = SimpleNamespace(venue_fact_id="position-current")

        async def risk_provider(*_args):
            return _risk_facts(
                current_abs_position=legs[0].leg.quantity,
                position_fact=position_fact,
            )

        # A new boundary has no in-memory progress. It must derive exactly one
        # continuation from the persisted activation, actions, and venue facts.
        boundary = _boundary(coordinator, risk_fact_provider=risk_provider)
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator, legs

    coordinator, legs = asyncio.run(scenario())
    assert coordinator.atomic_calls == []
    assert coordinator.closures[0]["execution_action_id"] == legs[0].execution_action_id
    assert coordinator.submissions == [legs[1].execution_action_id]


def test_terminal_partial_fill_with_exact_working_protection_can_advance_once() -> None:
    async def scenario():
        activation = _activation(_spec()).model_copy(update={"has_entry_fill": True})
        coordinator = _Coordinator(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        first = _persisted_leg(legs[0], state=ExecutionActionState.OPEN)
        coordinator.actions.extend(
            [
                first,
                *(
                    _persisted_leg(item, state=ExecutionActionState.READY)
                    for item in legs[1:]
                ),
            ]
        )
        partial_quantity = "0.1"
        fill = _fact(
            "partial-fill-terminal",
            VenueFactKind.FILL,
            {
                "trade_id": "partial-terminal-trade",
                "last_quantity": partial_quantity,
                "leaves_quantity": "0.1",
            },
        )
        coordinator.venue_facts[first.execution_action_id] = (
            fill,
            _fact(
                "partial-commission",
                VenueFactKind.COMMISSION,
                {"trade_id": "partial-terminal-trade"},
            ),
            _fact(
                "entry-cancelled",
                VenueFactKind.ORDER_STATE,
                {
                    "status": "CANCELLED",
                    "cumulative_filled_quantity": partial_quantity,
                },
            ),
        )
        protection = SimpleNamespace(
            execution_action_id="partial-protection",
            activation_id="activation-direct",
            source_identity="activation-direct:PROTECTION:partial-fill-terminal",
            client_order_id="partial-protection-client-id",
            action_kind=ExecutionActionKind.PROTECTION,
            action_terms={
                "quantity": partial_quantity,
                "execution_context": {"fill_fact_ref": fill.venue_fact_id},
            },
            state=ExecutionActionState.OPEN,
            state_version=1,
        )
        coordinator.actions.append(protection)
        coordinator.venue_facts[protection.execution_action_id] = (
            _fact(
                "partial-protection-working",
                VenueFactKind.ORDER_STATE,
                {"status": "WORKING"},
            ),
        )
        position_fact = SimpleNamespace(venue_fact_id="partial-position")
        boundary = _boundary(
            coordinator,
            risk_fact_provider=lambda *_args: asyncio.sleep(
                0,
                result=_risk_facts(
                    current_abs_position=partial_quantity,
                    position_fact=position_fact,
                ),
            ),
        )
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator, legs

    coordinator, legs = asyncio.run(scenario())
    assert coordinator.closures[0]["execution_action_id"] == legs[0].execution_action_id
    assert coordinator.submissions == [legs[1].execution_action_id]


def test_two_partial_fills_require_two_exact_working_protections_before_advancing() -> (
    None
):
    async def scenario():
        activation = _activation(_spec()).model_copy(update={"has_entry_fill": True})
        coordinator = _Coordinator(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        first = _persisted_leg(legs[0], state=ExecutionActionState.OPEN)
        coordinator.actions.extend(
            [
                first,
                *(
                    _persisted_leg(item, state=ExecutionActionState.READY)
                    for item in legs[1:]
                ),
            ]
        )
        fills = tuple(
            _fact(
                f"partial-fill-{index}",
                VenueFactKind.FILL,
                {
                    "trade_id": f"partial-trade-{index}",
                    "last_quantity": "0.1",
                    "leaves_quantity": "0.1" if index == 1 else "0.02",
                },
            )
            for index in (1, 2)
        )
        coordinator.venue_facts[first.execution_action_id] = (
            fills[0],
            _fact(
                "partial-commission-1",
                VenueFactKind.COMMISSION,
                {"trade_id": "partial-trade-1"},
            ),
            fills[1],
            _fact(
                "partial-commission-2",
                VenueFactKind.COMMISSION,
                {"trade_id": "partial-trade-2"},
            ),
            _fact(
                "entry-cancelled",
                VenueFactKind.ORDER_STATE,
                {
                    "status": "CANCELLED",
                    "cumulative_filled_quantity": "0.2",
                },
            ),
        )
        for index, fill in enumerate(fills, start=1):
            protection = SimpleNamespace(
                execution_action_id=f"partial-protection-{index}",
                activation_id="activation-direct",
                source_identity=f"activation-direct:PROTECTION:{fill.venue_fact_id}",
                client_order_id=f"partial-protection-client-{index}",
                action_kind=ExecutionActionKind.PROTECTION,
                action_terms={
                    "quantity": "0.1",
                    "execution_context": {"fill_fact_ref": fill.venue_fact_id},
                },
                state=ExecutionActionState.OPEN,
                state_version=1,
            )
            coordinator.actions.append(protection)
            coordinator.venue_facts[protection.execution_action_id] = (
                _fact(
                    f"partial-protection-working-{index}",
                    VenueFactKind.ORDER_STATE,
                    {"status": "WORKING"},
                ),
            )
        position_fact = SimpleNamespace(venue_fact_id="two-partial-position")
        boundary = _boundary(
            coordinator,
            risk_fact_provider=lambda *_args: asyncio.sleep(
                0,
                result=_risk_facts(
                    current_abs_position="0.2",
                    position_fact=position_fact,
                ),
            ),
        )
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator, legs

    coordinator, legs = asyncio.run(scenario())
    assert coordinator.closures[0]["execution_action_id"] == legs[0].execution_action_id
    assert coordinator.submissions == [legs[1].execution_action_id]


@pytest.mark.parametrize(
    "terminal_status",
    ("CANCELLED", "EXPIRED", "REJECTED", "FILLED"),
)
def test_terminal_entry_without_cumulative_fill_proof_cannot_open_next_leg(
    terminal_status: str,
) -> None:
    async def scenario():
        activation = _activation(_spec()).model_copy(update={"has_entry_fill": True})
        coordinator = _Coordinator(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        first = _persisted_leg(legs[0], state=ExecutionActionState.OPEN)
        coordinator.actions.extend(
            [
                first,
                *(
                    _persisted_leg(item, state=ExecutionActionState.READY)
                    for item in legs[1:]
                ),
            ]
        )
        fill = _fact(
            "entry-fill",
            VenueFactKind.FILL,
            {
                "trade_id": "entry-trade",
                "last_quantity": "0.1",
                "leaves_quantity": "0.1",
            },
        )
        coordinator.venue_facts[first.execution_action_id] = (
            fill,
            _fact(
                "entry-commission",
                VenueFactKind.COMMISSION,
                {"trade_id": "entry-trade"},
            ),
            _fact(
                "entry-terminal-without-cumulative",
                VenueFactKind.ORDER_STATE,
                {"status": terminal_status},
            ),
        )
        protection = SimpleNamespace(
            execution_action_id="protection-working",
            activation_id="activation-direct",
            source_identity="activation-direct:PROTECTION:entry-fill",
            client_order_id="protection-client-id",
            action_kind=ExecutionActionKind.PROTECTION,
            action_terms={
                "quantity": "0.1",
                "execution_context": {"fill_fact_ref": fill.venue_fact_id},
            },
            state=ExecutionActionState.OPEN,
            state_version=1,
        )
        coordinator.actions.append(protection)
        coordinator.venue_facts[protection.execution_action_id] = (
            _fact(
                "protection-working-fact",
                VenueFactKind.ORDER_STATE,
                {"status": "WORKING"},
            ),
        )
        boundary = _boundary(
            coordinator,
            risk_fact_provider=lambda *_args: asyncio.sleep(
                0,
                result=_risk_facts(
                    current_abs_position="0.1",
                    position_fact=SimpleNamespace(venue_fact_id="position-current"),
                ),
            ),
        )
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())
    assert coordinator.closures == []
    assert coordinator.submissions == []


def test_terminal_before_fill_waits_then_advances_after_late_fill_is_persisted() -> (
    None
):
    async def scenario():
        activation = _activation(_spec()).model_copy(update={"has_entry_fill": True})
        coordinator = _Coordinator(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        first = _persisted_leg(legs[0], state=ExecutionActionState.OPEN)
        coordinator.actions.extend(
            [
                first,
                *(
                    _persisted_leg(item, state=ExecutionActionState.READY)
                    for item in legs[1:]
                ),
            ]
        )
        terminal = _fact(
            "entry-cancelled-before-fill-callback",
            VenueFactKind.ORDER_STATE,
            {
                "status": "CANCELLED",
                "cumulative_filled_quantity": "0.1",
            },
        )
        coordinator.venue_facts[first.execution_action_id] = (terminal,)

        async def risk_provider(*_args):
            has_fill = any(
                fact.kind is VenueFactKind.FILL
                for fact in coordinator.venue_facts[first.execution_action_id]
            )
            return _risk_facts(
                current_abs_position="0.1" if has_fill else "0",
                position_fact=SimpleNamespace(venue_fact_id="position-current"),
            )

        boundary = _boundary(coordinator, risk_fact_provider=risk_provider)
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        assert coordinator.closures == []
        assert coordinator.submissions == []

        fill = _fact(
            "late-entry-fill",
            VenueFactKind.FILL,
            {
                "trade_id": "late-entry-trade",
                "last_quantity": "0.1",
                "leaves_quantity": "0.1",
            },
        )
        coordinator.venue_facts[first.execution_action_id] = (
            terminal,
            fill,
            _fact(
                "late-entry-commission",
                VenueFactKind.COMMISSION,
                {"trade_id": "late-entry-trade"},
            ),
        )
        protection = SimpleNamespace(
            execution_action_id="late-fill-protection",
            activation_id="activation-direct",
            source_identity="activation-direct:PROTECTION:late-entry-fill",
            client_order_id="protection-client-id",
            action_kind=ExecutionActionKind.PROTECTION,
            action_terms={
                "quantity": "0.1",
                "execution_context": {"fill_fact_ref": fill.venue_fact_id},
            },
            state=ExecutionActionState.OPEN,
            state_version=1,
        )
        coordinator.actions.append(protection)
        coordinator.venue_facts[protection.execution_action_id] = (
            _fact(
                "late-fill-protection-working",
                VenueFactKind.ORDER_STATE,
                {"status": "WORKING"},
            ),
        )
        boundary.resume("activation-direct", force_risk_refresh=True)
        await boundary.wait_idle()
        return coordinator, legs

    coordinator, legs = asyncio.run(scenario())
    assert coordinator.closures[0]["execution_action_id"] == legs[0].execution_action_id
    assert coordinator.submissions == [legs[1].execution_action_id]
