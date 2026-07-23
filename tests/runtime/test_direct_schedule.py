from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from halpha.capital.models import AuthorityClass, EnvironmentKind
from halpha.executor.direct_schedule import DirectScheduleBoundary
from halpha.executor.product_entry import DirectScheduleFacts, ProductAccountFacts
from halpha.executor.responsibilities import ProductRiskReductionFacts
from halpha.planning.models import PlanActivation, PlanLifecycle
from halpha.planning.order_policies import (
    CancelOnShockRule,
    ConditionFacts,
    ConditionGroup,
    ExpireRemainingRule,
    InitialStopSpec,
    MarkPriceCondition,
    NumericComparator,
    ProtectionPolicy,
)
from halpha.planning.order_schedule import (
    AmountDistribution,
    InstrumentOrderRules,
    OrderScheduleSpec,
    PriceDistribution,
    VenueOrderPolicy,
    VenueTimeInForce,
    compile_order_schedule,
)
from halpha.planning.order_schedule_actions import materialize_direct_schedule
from halpha.planning.registry import DIRECT_EXECUTION_REF, Direction
from halpha.planning.transitions import proposed_cancel_for_action, record_direct_fill
from halpha.venue_integration.models import (
    ExecutionActionKind,
    ExecutionActionState,
    VenueFactKind,
)


NOW = datetime(2026, 7, 23, 8, tzinfo=UTC)


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


def _activation(spec: OrderScheduleSpec) -> PlanActivation:
    preview = compile_order_schedule(
        spec,
        _rules(),
        venue_ref="BINANCE_USDM",
        instrument_ref="BTCUSDT-PERP",
        direction=Direction.LONG,
        max_notional="100",
        schedule_ref="plan-version-direct",
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
        direction=Direction.LONG,
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


def _facts(mark: str | None = "100") -> DirectScheduleFacts:
    return DirectScheduleFacts(
        account=ProductAccountFacts(
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
        ),
        conditions=ConditionFacts(
            basis_ready=True,
            mark_price=mark,
            bid_price="99.9",
            ask_price="100.1",
            elapsed_seconds=60,
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
    )


class _Coordinator:
    def __init__(self, activation: PlanActivation) -> None:
        self.activation = activation
        self.actions: list[SimpleNamespace] = []
        self.atomic_calls: list[dict[str, object]] = []
        self.submissions: list[str] = []
        self.rejections: list[tuple[str, str]] = []
        self.cancel_targets: list[str] = []
        self.cancel_endpoints: list[str] = []
        self.submission_checks: list[object] = []
        self.venue_facts: dict[str, tuple[object, ...]] = {}
        self.closures: list[dict[str, object]] = []
        self.expirations: list[dict[str, object]] = []

    def get_activation_snapshot(self, _activation_id: str) -> PlanActivation:
        return self.activation

    def expire_empty_entry_window(self, **kwargs):
        self.expirations.append(kwargs)
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
        self.actions.extend(
            _persisted_leg(item, state=ExecutionActionState.READY)
            for item in kwargs["legs"]
        )
        return ()

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
        )
        self.actions.append(action)
        return SimpleNamespace(execution_action=action)

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
    fact_provider=None,
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

    return DirectScheduleBoundary(
        loop=asyncio.get_running_loop(),
        coordinator=coordinator,
        fact_provider=fact_provider or default_provider,
        risk_reduction_fact_provider=(
            risk_fact_provider or default_risk_provider
        ),
        environment_id=environment_id,
        environment_kind=environment_kind,
        authority_class=authority_class,
        account_ref=account_ref,
        submission_enabled=enabled,
        current_time_provider=now if callable(now) else lambda: now,
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
            fact_provider=failed_facts,
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
    assert loop_contexts[0]["message"] == "HALPHA_DIRECT_SCHEDULE_FAILED"


def test_true_conditions_atomically_materialize_all_legs_and_submit_only_first() -> None:
    async def scenario():
        coordinator = _Coordinator(_activation(_spec()))
        boundary = _boundary(coordinator)
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())
    assert len(coordinator.actions) == 3
    assert len(coordinator.atomic_calls) == 1
    evidence = coordinator.atomic_calls[0]["condition_evidence"]
    assert evidence["evaluation"]["result"] == "TRUE"
    assert evidence["facts"]["mark_price"] == "100"
    assert coordinator.submissions == [coordinator.actions[0].execution_action_id]


def test_unknown_or_false_condition_creates_no_local_responsibility() -> None:
    async def scenario():
        coordinator = _Coordinator(_activation(_spec(condition_price="150")))
        boundary = _boundary(coordinator)
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())
    assert coordinator.actions == []
    assert coordinator.atomic_calls == []
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
            fact_provider=delayed_facts,
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
    assert coordinator.rejections == []


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
            fact_provider=delayed_facts,
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
        (legs[1].execution_action_id, "DIRECT_ENTRY_SHOCK_TRIGGERED"),
        (legs[2].execution_action_id, "DIRECT_ENTRY_SHOCK_TRIGGERED"),
    ]
    assert len(coordinator.submissions) == 1


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
            fact_provider=forbidden_entry_facts,
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
        activation = _activation(_spec(expire_at=NOW + timedelta(minutes=20)))
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
        return coordinator

    coordinator = asyncio.run(scenario())
    assert len(coordinator.rejections) == 3
    assert coordinator.submissions == []


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
            (item.execution_action_id, "DIRECT_GTD_EXPIRY_TOO_SOON")
            for item in legs
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

        async def later_facts(*_args):
            return _facts(mark="1")

        boundary = _boundary(coordinator, fact_provider=later_facts)
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

        async def first_facts(*_args):
            return _facts(mark=first_mark)

        before_restart = _boundary(coordinator, fact_provider=first_facts)
        before_restart.resume("activation-direct")
        await before_restart.wait_idle()
        assert coordinator.submissions == []
        before_restart.close()

        async def recovered_facts(*_args):
            return _facts(mark="100")

        after_restart = _boundary(coordinator, fact_provider=recovered_facts)
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
        boundary = _boundary(coordinator, fact_provider=lambda *_args: asyncio.sleep(0, result=_facts(mark="100")))
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


def test_global_time_exit_stops_and_cancels_remaining_entry_before_position_exit() -> None:
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


def test_limit_cap_keeps_the_more_conservative_live_price_and_full_plan_margin() -> None:
    async def scenario():
        coordinator = _Coordinator(_activation(_spec()))

        async def conservative_facts(*_args):
            facts = _facts()
            return DirectScheduleFacts(
                account=replace(facts.account, conservative_price="150"),
                conditions=facts.conditions,
            )

        boundary = _boundary(coordinator, fact_provider=conservative_facts)
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
            SimpleNamespace(ts_event=cutoff_ns - 10_000_000_000, value="100"),
        )
        boundary.record_mark(
            "activation-direct",
            SimpleNamespace(ts_event=cutoff_ns - 5_000_000_000, value="98"),
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


def test_risk_reduction_with_missing_position_fact_holds_remaining_leg_unknown() -> None:
    async def scenario():
        activation = _activation(_spec()).model_copy(update={"has_entry_fill": True})
        coordinator = _Coordinator(activation)
        legs = materialize_direct_schedule(
            activation,
            entry_valid_until=NOW + timedelta(hours=1),
        )
        coordinator.actions.extend(
            _persisted_leg(item, state=(
                ExecutionActionState.CLOSED
                if index == 0
                else ExecutionActionState.READY
            ))
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
                {"trade_id": "tp-trade", "last_quantity": "0.1", "leaves_quantity": "0"},
            ),
        )
        boundary = _boundary(coordinator, risk_fact_provider=lambda *_args: asyncio.sleep(0, result=_risk_facts()))
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())
    assert coordinator.submissions == []
    assert coordinator.rejections == []
    assert coordinator.actions[1].state is ExecutionActionState.READY


def test_restart_advances_to_next_leg_only_after_terminal_entry_is_still_protected() -> None:
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
            _fact("entry-commission", VenueFactKind.COMMISSION, {"trade_id": "entry-trade"}),
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
            _fact("protection-working-fact", VenueFactKind.ORDER_STATE, {"status": "WORKING"}),
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
            _fact("partial-protection-working", VenueFactKind.ORDER_STATE, {"status": "WORKING"}),
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


def test_two_partial_fills_require_two_exact_working_protections_before_advancing() -> None:
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
                    position_fact=SimpleNamespace(
                        venue_fact_id="position-current"
                    ),
                ),
            ),
        )
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator

    coordinator = asyncio.run(scenario())
    assert coordinator.closures == []
    assert coordinator.submissions == []


def test_terminal_before_fill_waits_then_advances_after_late_fill_is_persisted() -> None:
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
        boundary.resume("activation-direct")
        await boundary.wait_idle()
        return coordinator, legs

    coordinator, legs = asyncio.run(scenario())
    assert coordinator.closures[0]["execution_action_id"] == legs[0].execution_action_id
    assert coordinator.submissions == [legs[1].execution_action_id]
