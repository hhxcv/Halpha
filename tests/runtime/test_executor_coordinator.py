from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from halpha.capital.models import AuthorityClass, EnvironmentKind, RiskClass
from halpha.domain_values import content_digest
from halpha.executor.coordinator import (
    HalphaCoordinator,
    _aggregate_protection_projection,
    _protection_projection_state,
    _submission_block_reason,
)
from halpha.outcomes.models import (
    EvidencePurpose,
    PrimaryResult,
    Review,
    ReviewStatus,
)
from halpha.outcomes.service import OutcomeApplicationService
from halpha.planning.models import (
    PlanActivation,
    PlanLifecycle,
    ProtectionState,
    RunState,
)
from halpha.planning.order_policies import InitialStopSpec, ProtectionPolicy
from halpha.planning.order_schedule import (
    AmountDistribution,
    InstrumentOrderRules,
    OrderScheduleSpec,
    PriceDistribution,
    VenueOrderPolicy,
    compile_order_schedule,
)
from halpha.planning.order_schedule_actions import materialize_direct_schedule
from halpha.planning.registry import DIRECT_EXECUTION_REF, Direction
from halpha.planning.transitions import record_direct_fill
from halpha.venue_integration.models import (
    ExecutionActionKind,
    ExecutionActionState,
    VenueFactKind,
    VenueFactSourceClass,
)
from halpha.venue_integration.nautilus_events import NormalizedNautilusEvent


def _action(kind: ExecutionActionKind, state: ExecutionActionState):
    return SimpleNamespace(action_kind=kind, state=state)


def _order_fact(status: str):
    observed_at = datetime(2026, 7, 23, tzinfo=UTC)
    return SimpleNamespace(
        kind=VenueFactKind.ORDER_STATE,
        payload={"status": status},
        source_time=observed_at,
        cutoff=observed_at,
        received_at=observed_at,
        venue_fact_id=f"order-{status.lower()}",
    )


def _direct_schedule_fixture(
    *,
    level_count: int = 3,
) -> tuple[PlanActivation, tuple, datetime]:
    created_at = datetime(2026, 7, 23, tzinfo=UTC)
    entry_valid_until = created_at + timedelta(hours=1)
    rules = InstrumentOrderRules(
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
        source_cutoff=created_at.isoformat(),
    )
    spec = OrderScheduleSpec(
        price_distribution=PriceDistribution(
            lower_price="90",
            upper_price="110",
            level_count=level_count,
        ),
        amount_distribution=AmountDistribution(base_notional="20"),
        venue_policy=VenueOrderPolicy(post_only=True),
        protection_policy=ProtectionPolicy(
            initial_stop=InitialStopSpec(distance_bps="100")
        ),
    )
    snapshot = compile_order_schedule(
        spec,
        rules,
        venue_ref="BINANCE_USDM",
        instrument_ref="BTCUSDT-PERP",
        direction=Direction.LONG,
        max_notional="100",
        schedule_ref="plan-version-001",
        reference_price="100",
    )
    assert snapshot.valid
    activation = PlanActivation(
        activation_id="activation",
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
        rule_state={
            "deadlines": {"entry_valid_until": entry_valid_until.isoformat()}
        },
        created_at=created_at,
        updated_at=created_at,
    )
    legs = materialize_direct_schedule(
        activation,
        entry_valid_until=entry_valid_until,
    )
    return activation, legs, entry_valid_until


def _with_conflicting_schedule_digest(legs: tuple) -> tuple:
    first = legs[0]
    execution_context = dict(first.proposed_action.execution_context)
    execution_context["order_schedule"] = {
        **execution_context["order_schedule"],
        "schedule_digest": "f" * 64,
    }
    return (
        first.model_copy(
            update={
                "proposed_action": first.proposed_action.model_copy(
                    update={"execution_context": execution_context}
                )
            }
        ),
        *legs[1:],
    )


def test_working_protection_projects_working() -> None:
    assert (
        _protection_projection_state(
            _action(
                ExecutionActionKind.PROTECTION,
                ExecutionActionState.OPEN,
            ),
            _order_fact("WORKING"),
        )
        is ProtectionState.WORKING
    )


def test_terminal_unfilled_protection_projects_gap() -> None:
    for status in ("CANCELLED", "REJECTED", "EXPIRED"):
        assert (
            _protection_projection_state(
                _action(ExecutionActionKind.PROTECTION, ExecutionActionState.OPEN),
                _order_fact(status),
            )
            is ProtectionState.GAP
        )


def test_non_protection_or_non_projectable_state_has_no_projection() -> None:
    assert (
        _protection_projection_state(
            _action(ExecutionActionKind.ENTRY, ExecutionActionState.OPEN),
            _order_fact("WORKING"),
        )
        is None
    )


def test_late_working_fact_does_not_erase_existing_protection_gap() -> None:
    activation = _direct_schedule_fixture()[0].model_copy(
        update={"protection_state": ProtectionState.GAP}
    )
    updates: list[dict[str, object]] = []
    coordinator = object.__new__(HalphaCoordinator)
    coordinator._planning = SimpleNamespace(
        get_activation=lambda *_args, **_kwargs: activation,
        update_protection_projection=lambda **kwargs: updates.append(kwargs),
    )
    coordinator._action_repository = SimpleNamespace(
        list_for_activation=lambda _activation_id: ()
    )
    coordinator._fact_repository = SimpleNamespace(
        list_for_action=lambda _action_id: ()
    )
    action = SimpleNamespace(
        action_kind=ExecutionActionKind.PROTECTION,
        activation_id=activation.activation_id,
    )

    coordinator._apply_protection_projection_from_fact(
        action=action,
        fact=_order_fact("WORKING"),
        observed_at=activation.updated_at,
    )

    assert updates == []


def test_protection_projection_reduces_all_fill_responsibilities() -> None:
    activation = _direct_schedule_fixture()[0]
    entry = SimpleNamespace(
        execution_action_id="entry",
        action_kind=ExecutionActionKind.ENTRY,
        action_terms={},
    )
    first = SimpleNamespace(
        execution_action_id="protection-1",
        action_kind=ExecutionActionKind.PROTECTION,
        state=ExecutionActionState.OPEN,
        action_terms={"execution_context": {"fill_fact_ref": "fill-1"}},
    )
    second = SimpleNamespace(
        execution_action_id="protection-2",
        action_kind=ExecutionActionKind.PROTECTION,
        state=ExecutionActionState.SUBMITTING,
        action_terms={"execution_context": {"fill_fact_ref": "fill-2"}},
    )
    facts = {
        "entry": (
            SimpleNamespace(kind=VenueFactKind.FILL, venue_fact_id="fill-1"),
            SimpleNamespace(kind=VenueFactKind.FILL, venue_fact_id="fill-2"),
        ),
        "protection-1": (_order_fact("WORKING"),),
        "protection-2": (),
    }

    mixed = _aggregate_protection_projection(
        activation,
        (entry, first, second),
        lambda action_id: facts[action_id],
    )
    facts["protection-2"] = (_order_fact("WORKING"),)
    covered = _aggregate_protection_projection(
        activation,
        (entry, first, second),
        lambda action_id: facts[action_id],
    )
    first.state = ExecutionActionState.NOT_SUBMITTED
    gap = _aggregate_protection_projection(
        activation,
        (entry, first, second),
        lambda action_id: facts[action_id],
    )

    assert mixed is ProtectionState.UNKNOWN
    assert covered is ProtectionState.WORKING
    assert gap is ProtectionState.GAP


def test_unprotectable_direct_fill_is_persisted_as_gap_without_action() -> None:
    activation = _direct_schedule_fixture(level_count=2)[0]
    observed_at = activation.updated_at + timedelta(seconds=1)
    fill = SimpleNamespace(
        kind=VenueFactKind.FILL,
        action_ref="entry-action",
        activation_ref=activation.activation_id,
        payload={"last_price": "100", "last_quantity": "0.1"},
        source_time=observed_at,
        cutoff=observed_at,
        venue_fact_id="fill-invalid-target",
        source_class=VenueFactSourceClass.VENUE_STREAM,
        source_object_id="trade-invalid-target",
        source_sequence="1",
        content_digest="c" * 64,
    )
    entry_action = SimpleNamespace(
        execution_action_id="entry-action",
        activation_id=activation.activation_id,
        action_kind=ExecutionActionKind.ENTRY,
        action_terms={
            "execution_context": {
                "protection_policy": ProtectionPolicy(
                    initial_stop=InitialStopSpec(distance_bps="1")
                ).model_dump(mode="json"),
                "order_schedule": {
                    "price_tick_size": "1",
                    "quantity_step": "0.1",
                },
            }
        },
    )
    recorded_events: list[dict[str, object]] = []
    projections: list[dict[str, object]] = []
    persisted_activations: list[PlanActivation] = []

    def persist_direct_fill(**values: object) -> PlanActivation:
        values = dict(values)
        values.pop("activation_id")
        persisted = record_direct_fill(activation, **values)
        persisted_activations.append(persisted)
        return persisted

    def record_event(**values: object) -> SimpleNamespace:
        recorded_events.append(values)
        return SimpleNamespace(**values)

    coordinator = object.__new__(HalphaCoordinator)
    coordinator._connection = SimpleNamespace(transaction=lambda: nullcontext())
    coordinator._execution = SimpleNamespace(apply_venue_fact=lambda **_kwargs: entry_action)
    coordinator._planning = SimpleNamespace(
        record_direct_fill=persist_direct_fill,
        record_plan_event=record_event,
        update_protection_projection=lambda **values: projections.append(values),
    )

    result = coordinator.create_protection_for_fill(
        fill_fact=fill,
        plan_event_id="plan-event-protection-gap",
        execution_action_id="must-not-be-created",
        action_check=object(),
        observed_at=observed_at,
    )

    assert result.execution_action is None
    assert persisted_activations[0].has_entry_fill
    direct_fill = persisted_activations[0].rule_state["direct_protection"]["fills"][
        fill.venue_fact_id
    ]
    assert direct_fill["protection_error"] == "PROTECTION_PRICE_INVALID"
    assert recorded_events[0]["no_action_reason"] == "PROTECTION_PRICE_INVALID"
    assert projections[0]["protection_state"] is ProtectionState.GAP
    assert (
        _protection_projection_state(
            _action(
                ExecutionActionKind.PROTECTION,
                ExecutionActionState.UNKNOWN,
            ),
            SimpleNamespace(kind=VenueFactKind.COMMISSION, payload={}),
        )
        is None
    )


def test_paused_activation_blocks_only_risk_increasing_submission() -> None:
    paused = SimpleNamespace(
        lifecycle=PlanLifecycle.RUNNING,
        run_state=RunState.PAUSED,
    )
    increasing = SimpleNamespace(action_class=RiskClass.RISK_INCREASING)
    neutral = SimpleNamespace(action_class=RiskClass.RISK_NEUTRAL)
    reducing = SimpleNamespace(action_class=RiskClass.RISK_REDUCING)

    assert _submission_block_reason(increasing, paused) == "NEW_RISK_STOPPED"
    assert _submission_block_reason(neutral, paused) is None
    assert _submission_block_reason(reducing, paused) is None


def test_user_takeover_or_completion_blocks_every_submission_class() -> None:
    action = SimpleNamespace(action_class=RiskClass.RISK_REDUCING)
    for lifecycle in (PlanLifecycle.USER_TAKEOVER, PlanLifecycle.COMPLETED):
        activation = SimpleNamespace(
            lifecycle=lifecycle,
            run_state=RunState.PAUSED,
        )
        assert _submission_block_reason(action, activation) == "USER_TAKEOVER_ACTIVE"


def test_live_submission_guard_rechecks_the_exact_activation() -> None:
    observed: list[str] = []
    coordinator = object.__new__(HalphaCoordinator)
    coordinator._environment_kind = "LIVE"
    coordinator._live_write_submission_guard = observed.append

    coordinator._require_current_live_write_gate("activation-live-001")

    assert observed == ["activation-live-001"]


def test_live_submission_guard_fails_closed_without_leaking_internal_error() -> None:
    coordinator = object.__new__(HalphaCoordinator)
    coordinator._environment_kind = "LIVE"

    def fail(_activation_id: str) -> None:
        raise ValueError("sensitive-detail")

    coordinator._live_write_submission_guard = fail

    with pytest.raises(RuntimeError, match="^RUNTIME_REAL_WRITE_GATE_CLOSED$"):
        coordinator._require_current_live_write_gate("activation-live-001")


def test_unknown_nautilus_result_records_specific_reason_without_terminal_fact() -> None:
    observed_at = datetime(2026, 7, 20, 4, 59, tzinfo=UTC)
    action = SimpleNamespace(execution_action_id="execution-action-unknown")
    recorded: list[dict[str, object]] = []
    normalized = NormalizedNautilusEvent(
        action=action,
        facts=(),
        result_unknown=True,
        unknown_reason="VENUE_SUBMISSION_RESULT_UNKNOWN",
    )

    coordinator = object.__new__(HalphaCoordinator)
    coordinator._connection = SimpleNamespace(transaction=lambda: nullcontext())
    coordinator._execution = SimpleNamespace(
        record_submission_unknown=lambda execution_action_id, **values: recorded.append(
            {"execution_action_id": execution_action_id, **values}
        )
    )
    normalizer = SimpleNamespace(normalize=lambda _event, **_values: normalized)

    result = coordinator.handle_nautilus_order_event(
        normalizer,
        object(),
        observed_at=observed_at,
    )

    assert result is normalized
    assert recorded == [
        {
            "execution_action_id": "execution-action-unknown",
            "reason": "VENUE_SUBMISSION_RESULT_UNKNOWN",
            "next_query_at": observed_at + timedelta(seconds=10),
            "observed_at": observed_at,
        }
    ]


def test_denied_protection_atomically_projects_aggregate_gap() -> None:
    observed_at = datetime(2026, 7, 23, 6, 45, tzinfo=UTC)
    activation = _direct_schedule_fixture()[0].model_copy(
        update={"protection_state": ProtectionState.UNKNOWN}
    )
    entry = SimpleNamespace(
        execution_action_id="entry-action",
        activation_id=activation.activation_id,
        action_kind=ExecutionActionKind.ENTRY,
        action_terms={},
    )
    protection = SimpleNamespace(
        execution_action_id="protection-denied",
        activation_id=activation.activation_id,
        action_kind=ExecutionActionKind.PROTECTION,
        state=ExecutionActionState.SUBMITTING,
        action_terms={"execution_context": {"fill_fact_ref": "entry-fill"}},
    )
    entry_fill = SimpleNamespace(
        kind=VenueFactKind.FILL,
        venue_fact_id="entry-fill",
    )
    projected: list[ProtectionState] = []

    class Planning:
        current = activation

        @classmethod
        def get_activation(cls, *_args, **_kwargs):
            return cls.current

        @classmethod
        def update_protection_projection(cls, **values):
            projected.append(values["protection_state"])
            cls.current = cls.current.model_copy(
                update={"protection_state": values["protection_state"]}
            )
            return cls.current

    def deny(_action_id: str, **_kwargs: object) -> SimpleNamespace:
        protection.state = ExecutionActionState.NOT_SUBMITTED
        return protection

    coordinator = object.__new__(HalphaCoordinator)
    coordinator._connection = SimpleNamespace(transaction=lambda: nullcontext())
    coordinator._planning = Planning()
    coordinator._execution = SimpleNamespace(record_definitely_not_submitted=deny)
    coordinator._action_repository = SimpleNamespace(
        list_for_activation=lambda _activation_id: (entry, protection),
    )
    coordinator._fact_repository = SimpleNamespace(
        list_for_action=lambda action_id: (
            (entry_fill,) if action_id == entry.execution_action_id else ()
        )
    )
    normalizer = SimpleNamespace(
        normalize=lambda _event, **_kwargs: NormalizedNautilusEvent(
            action=protection,
            facts=(),
            definitely_not_submitted=True,
        )
    )

    coordinator.handle_nautilus_order_event(
        normalizer,
        object(),
        observed_at=observed_at,
    )

    assert projected == [ProtectionState.GAP]


def test_due_unknown_action_query_uses_only_its_persisted_identity() -> None:
    observed_at = datetime(2026, 7, 20, 5, 0, tzinfo=UTC)
    action = SimpleNamespace(execution_action_id="execution-action-unknown")
    prepared: list[dict[str, object]] = []
    queried: list[str] = []

    def prepare(execution_action_id: str, **values: object) -> object:
        prepared.append({"execution_action_id": execution_action_id, **values})
        return action

    coordinator = object.__new__(HalphaCoordinator)
    coordinator._connection = SimpleNamespace(transaction=lambda: nullcontext())
    coordinator._execution = SimpleNamespace(prepare_due_unknown_query=prepare)
    coordinator._gate = SimpleNamespace(query_original_identity=queried.append)

    attempted = coordinator.query_unknown_action_if_due(
        action.execution_action_id,
        observed_at=observed_at,
    )

    assert attempted is True
    assert queried == ["execution-action-unknown"]
    assert prepared == [
        {
            "execution_action_id": "execution-action-unknown",
            "next_query_at": observed_at + timedelta(seconds=10),
            "observed_at": observed_at,
        }
    ]


def test_startup_recovery_queries_submitting_unknown_and_open_without_releasing_on_dispatch() -> None:
    observed_at = datetime(2026, 7, 23, 6, 0, tzinfo=UTC)
    actions = (
        SimpleNamespace(
            execution_action_id="startup-submitting",
            activation_id="activation-a",
            state=ExecutionActionState.UNKNOWN,
        ),
        SimpleNamespace(
            execution_action_id="startup-unknown",
            activation_id="activation-a",
            state=ExecutionActionState.UNKNOWN,
        ),
        SimpleNamespace(
            execution_action_id="startup-open",
            activation_id="activation-b",
            state=ExecutionActionState.OPEN,
        ),
    )
    queried: list[str] = []

    def query(action_id: str) -> None:
        queried.append(action_id)
        if action_id == "startup-open":
            raise ConnectionError("query transport unavailable")

    coordinator = object.__new__(HalphaCoordinator)
    coordinator._connection = SimpleNamespace(transaction=lambda: nullcontext())
    coordinator._execution = SimpleNamespace(
        prepare_startup_reconciliation=lambda **_kwargs: actions
    )
    coordinator._action_repository = SimpleNamespace(
        get=lambda action_id: next(
            action for action in actions if action.execution_action_id == action_id
        )
    )
    coordinator._gate = SimpleNamespace(query_original_identity=query)
    coordinator.arm_startup_recovery_barrier()

    recovered = coordinator.recover_unresolved_actions(observed_at=observed_at)

    assert recovered == actions
    assert queried == [action.execution_action_id for action in actions]
    assert coordinator.startup_recovery_complete() is False
    assert coordinator.startup_recovery_allows_submission("activation-a") is False
    assert coordinator.startup_recovery_allows_submission("activation-b") is False
    assert coordinator.startup_recovery_allows_submission("activation-unaffected") is True

    # Dispatch success and one transport failure are both non-authoritative.
    assert coordinator.retry_startup_recovery_queries(
        observed_at=observed_at + timedelta(seconds=9)
    ) == ()
    retried = coordinator.retry_startup_recovery_queries(
        observed_at=observed_at + timedelta(seconds=10)
    )
    assert retried == tuple(action.execution_action_id for action in actions)
    assert coordinator.startup_recovery_complete() is False
    assert queried == [
        *(action.execution_action_id for action in actions),
        *retried,
    ]


def test_authoritative_startup_query_fact_releases_barrier_only_after_commit() -> None:
    observed_at = datetime(2026, 7, 23, 6, 30, tzinfo=UTC)
    action = SimpleNamespace(
        execution_action_id="startup-open",
        activation_id="activation-a",
        action_kind=ExecutionActionKind.ENTRY,
        state=ExecutionActionState.OPEN,
    )
    trace: list[str] = []

    class Transaction:
        def __enter__(self):
            trace.append("BEGIN")

        def __exit__(self, *_args):
            trace.append("COMMIT")

    coordinator = object.__new__(HalphaCoordinator)
    coordinator._connection = SimpleNamespace(transaction=Transaction)
    coordinator._execution = SimpleNamespace(
        prepare_startup_reconciliation=lambda **_kwargs: (action,),
        apply_venue_fact=lambda **_kwargs: action,
    )
    coordinator._action_repository = SimpleNamespace(
        get=lambda _action_id: action,
        find_open_cancel_for_target=lambda _client_order_id: None,
    )
    coordinator._gate = SimpleNamespace(query_original_identity=lambda _action_id: None)
    coordinator.arm_startup_recovery_barrier()
    coordinator.recover_unresolved_actions(
        observed_at=observed_at,
        resolution_sink=lambda activation_id, action_id: trace.append(
            f"RESOLVED:{activation_id}:{action_id}"
        ),
    )
    trace.clear()
    fact = SimpleNamespace(
        kind=VenueFactKind.ORDER_STATE,
        payload={"status": "WORKING"},
        source_time=observed_at + timedelta(seconds=1),
        cutoff=observed_at + timedelta(seconds=1),
        received_at=observed_at + timedelta(seconds=1),
        venue_fact_id="startup-query-fact",
    )
    normalized = NormalizedNautilusEvent(
        action=action,
        facts=(fact,),
        client_order_id="persisted-client-id",
    )
    normalizer = SimpleNamespace(normalize=lambda _event, **_kwargs: normalized)

    result = coordinator.handle_nautilus_order_event(
        normalizer,
        object(),
        observed_at=observed_at + timedelta(seconds=1),
    )

    assert result is normalized
    assert trace == [
        "BEGIN",
        "COMMIT",
        "RESOLVED:activation-a:startup-open",
    ]
    assert coordinator.startup_recovery_complete() is True
    assert coordinator.startup_recovery_allows_submission("activation-a") is True


def test_demo_submission_path_does_not_add_a_second_gate() -> None:
    coordinator = object.__new__(HalphaCoordinator)
    coordinator._environment_kind = "DEMO"
    coordinator._live_write_submission_guard = lambda _activation_id: pytest.fail(
        "Demo must not invoke the LIVE deployment gate"
    )

    coordinator._require_current_live_write_gate("activation-demo-001")


def test_open_entry_responsibility_blocks_a_second_distinct_bar_action() -> None:
    event = SimpleNamespace(capital_decision={"accepted": False})
    observed: dict[str, object] = {}

    class Planning:
        @staticmethod
        def get_activation(activation_id: str, *, for_update: bool = False):
            observed["locked_activation"] = (activation_id, for_update)
            return object()

        @staticmethod
        def consume_strategy_proposal(**values):
            observed["planning_values"] = values
            return event

    class Execution:
        @staticmethod
        def create_execution_action(**_values):
            pytest.fail("an open entry responsibility must not create another action")

    coordinator = object.__new__(HalphaCoordinator)
    coordinator._environment_kind = "DEMO"
    coordinator._live_write_submission_guard = None
    coordinator._connection = SimpleNamespace(transaction=lambda: nullcontext())
    coordinator._planning = Planning()
    coordinator._action_repository = SimpleNamespace(
        has_open_entry_responsibility=lambda _activation_id: True
    )
    coordinator._execution = Execution()
    proposal = SimpleNamespace(activation_id="activation-demo-001")

    result = coordinator.consume_strategy_proposal(
        plan_event_id="plan-event-second-bar",
        execution_action_id="execution-action-second-bar",
        proposal=proposal,
        action_check=object(),
        created_at=datetime(2026, 7, 20, 5, 26, tzinfo=UTC),
    )

    assert result.execution_action is None
    assert observed["locked_activation"] == ("activation-demo-001", True)
    assert observed["planning_values"]["entry_responsibility_open"] is True


def test_order_schedule_establishes_all_local_actions_in_one_transaction() -> None:
    observed_at = datetime(2026, 7, 23, 1, 0, tzinfo=UTC)
    entered: list[str] = []

    class Transaction:
        def __enter__(self):
            entered.append("BEGIN")

        def __exit__(self, *_args):
            entered.append("END")

    activation, legs, _entry_valid_until = _direct_schedule_fixture()
    checks = tuple(
        SimpleNamespace(checked_at=observed_at) for _index in range(3)
    )
    recorded: list[str] = []
    coordinator = object.__new__(HalphaCoordinator)
    coordinator._connection = SimpleNamespace(transaction=Transaction)
    coordinator._planning = SimpleNamespace(
        get_activation=lambda *_args, **_kwargs: activation
    )
    coordinator._action_repository = SimpleNamespace(
        list_for_activation=lambda _activation_id: ()
    )
    coordinator._capital = SimpleNamespace(
        check_current_action=lambda _check: SimpleNamespace(accepted=True)
    )

    def record(**values):
        recorded.append(values["execution_action_id"])
        return (
            SimpleNamespace(plan_event_id=values["plan_event_id"]),
            SimpleNamespace(execution_action_id=values["execution_action_id"]),
        )

    coordinator._record_proposed_action = record

    results = coordinator.consume_order_schedule_atomic(
        activation_id="activation",
        legs=legs,
        action_checks=checks,
        observed_at=observed_at,
    )

    assert entered == ["BEGIN", "END"]
    assert recorded == [item.execution_action_id for item in legs]
    assert [item.execution_action.execution_action_id for item in results] == recorded


def test_order_schedule_cap_rejection_happens_before_any_local_action() -> None:
    observed_at = datetime(2026, 7, 23, 1, 0, tzinfo=UTC)
    activation, legs, _entry_valid_until = _direct_schedule_fixture(level_count=2)
    coordinator = object.__new__(HalphaCoordinator)
    coordinator._connection = SimpleNamespace(transaction=lambda: nullcontext())
    coordinator._planning = SimpleNamespace(
        get_activation=lambda *_args, **_kwargs: activation
    )
    coordinator._action_repository = SimpleNamespace(
        list_for_activation=lambda _activation_id: ()
    )
    coordinator._capital = SimpleNamespace(
        check_current_action=lambda _check: SimpleNamespace(accepted=False)
    )
    coordinator._record_proposed_action = lambda **_kwargs: pytest.fail(
        "a rejected schedule must not append a partial event or action"
    )

    with pytest.raises(ValueError, match="ORDER_SCHEDULE_CAP_REJECTED"):
        coordinator.consume_order_schedule_atomic(
            activation_id="activation",
            legs=legs,
            action_checks=tuple(
                SimpleNamespace(checked_at=observed_at) for _leg in legs
            ),
            observed_at=observed_at,
        )


def test_partial_schedule_action_set_is_not_auto_repaired() -> None:
    observed_at = datetime(2026, 7, 23, 1, 0, tzinfo=UTC)
    activation, legs, _entry_valid_until = _direct_schedule_fixture(level_count=2)
    existing = SimpleNamespace(
        execution_action_id=legs[0].execution_action_id,
        action_terms={
            "execution_context": legs[0].proposed_action.execution_context
        },
    )
    coordinator = object.__new__(HalphaCoordinator)
    coordinator._connection = SimpleNamespace(transaction=lambda: nullcontext())
    coordinator._planning = SimpleNamespace(
        get_activation=lambda *_args, **_kwargs: activation
    )
    coordinator._action_repository = SimpleNamespace(
        list_for_activation=lambda _activation_id: (existing,)
    )
    coordinator._capital = SimpleNamespace(
        check_current_action=lambda _check: pytest.fail(
            "partial local responsibility must fail before CAP"
        )
    )

    with pytest.raises(
        ValueError,
        match="ORDER_SCHEDULE_LOCAL_RESPONSIBILITY_CONFLICT",
    ):
        coordinator.consume_order_schedule_atomic(
            activation_id="activation",
            legs=legs,
            action_checks=(
                SimpleNamespace(checked_at=observed_at),
                SimpleNamespace(checked_at=observed_at),
            ),
            observed_at=observed_at,
        )


@pytest.mark.parametrize(
    "tamper",
    [
        lambda legs: tuple(reversed(legs)),
        lambda legs: (
            legs[0].model_copy(update={"input_digest": "0" * 64}),
            *legs[1:],
        ),
        lambda legs: (
            legs[0].model_copy(
                update={
                    "execution_action_id": "00000000-0000-0000-0000-000000000000"
                }
            ),
            *legs[1:],
        ),
        lambda legs: (
            legs[0].model_copy(
                update={"plan_event_id": "00000000-0000-0000-0000-000000000000"}
            ),
            *legs[1:],
        ),
        lambda legs: (
            legs[0].model_copy(update={"client_order_id": "0" * 32}),
            *legs[1:],
        ),
        _with_conflicting_schedule_digest,
        lambda legs: (
            legs[0].model_copy(
                update={
                    "proposed_action": legs[0].proposed_action.model_copy(
                        update={"quantity": "999"}
                    )
                }
            ),
            *legs[1:],
        ),
    ],
)
def test_order_schedule_rejects_non_authoritative_materialization(tamper) -> None:
    observed_at = datetime(2026, 7, 23, 1, 0, tzinfo=UTC)
    activation, legs, _entry_valid_until = _direct_schedule_fixture(level_count=2)
    coordinator = object.__new__(HalphaCoordinator)
    coordinator._connection = SimpleNamespace(transaction=lambda: nullcontext())
    coordinator._planning = SimpleNamespace(
        get_activation=lambda *_args, **_kwargs: activation
    )
    coordinator._action_repository = SimpleNamespace(
        list_for_activation=lambda _activation_id: pytest.fail(
            "non-authoritative legs must fail before reading existing actions"
        )
    )
    coordinator._capital = SimpleNamespace(
        check_current_action=lambda _check: pytest.fail(
            "non-authoritative legs must fail before CAP"
        )
    )

    with pytest.raises(
        ValueError,
        match="ORDER_SCHEDULE_MATERIALIZATION_MISMATCH",
    ):
        coordinator.consume_order_schedule_atomic(
            activation_id="activation",
            legs=tamper(legs),
            action_checks=tuple(
                SimpleNamespace(checked_at=observed_at) for _leg in legs
            ),
            observed_at=observed_at,
        )


def test_order_schedule_rejects_existing_action_from_another_schedule_digest() -> None:
    observed_at = datetime(2026, 7, 23, 1, 0, tzinfo=UTC)
    activation, legs, _entry_valid_until = _direct_schedule_fixture(level_count=2)
    conflicting = SimpleNamespace(
        execution_action_id="conflicting-action",
        action_terms={
            "execution_context": {
                "order_schedule": {"schedule_digest": "f" * 64}
            }
        },
    )
    coordinator = object.__new__(HalphaCoordinator)
    coordinator._connection = SimpleNamespace(transaction=lambda: nullcontext())
    coordinator._planning = SimpleNamespace(
        get_activation=lambda *_args, **_kwargs: activation
    )
    coordinator._action_repository = SimpleNamespace(
        list_for_activation=lambda _activation_id: (conflicting,)
    )
    coordinator._capital = SimpleNamespace(
        check_current_action=lambda _check: pytest.fail(
            "a conflicting persisted digest must fail before CAP"
        )
    )

    with pytest.raises(ValueError, match="ORDER_SCHEDULE_DIGEST_CONFLICT"):
        coordinator.consume_order_schedule_atomic(
            activation_id="activation",
            legs=legs,
            action_checks=tuple(
                SimpleNamespace(checked_at=observed_at) for _leg in legs
            ),
            observed_at=observed_at,
        )


def test_exact_uuid_absence_closes_only_an_unknown_action() -> None:
    observed_at = datetime(2026, 7, 20, 5, 40, tzinfo=UTC)
    unknown = SimpleNamespace(
        execution_action_id="entry-action-unknown",
        state=ExecutionActionState.UNKNOWN,
    )
    recorded: list[dict[str, object]] = []
    coordinator = object.__new__(HalphaCoordinator)
    coordinator._connection = SimpleNamespace(transaction=lambda: nullcontext())
    coordinator._action_repository = SimpleNamespace(
        get=lambda _action_id, for_update=False: unknown
    )
    coordinator._execution = SimpleNamespace(
        record_definitely_not_submitted=lambda action_id, **values: recorded.append(
            {"action_id": action_id, **values}
        )
    )

    coordinator.record_unknown_action_not_submitted(
        unknown.execution_action_id,
        reason_code="VENUE_QUERY_PROVED_ABSENT",
        observed_at=observed_at,
    )

    assert recorded == [
        {
            "action_id": "entry-action-unknown",
            "reason_code": "VENUE_QUERY_PROVED_ABSENT",
            "observed_at": observed_at,
        }
    ]


@pytest.mark.parametrize(
    ("entry_point", "initial_result", "initial_state"),
    (
        (
            "unknown_absence",
            PrimaryResult.RESULT_UNKNOWN,
            ExecutionActionState.UNKNOWN,
        ),
        (
            "execution_reconciliation",
            PrimaryResult.PARTIAL,
            ExecutionActionState.OPEN,
        ),
        (
            "cancel_reconciliation",
            PrimaryResult.PARTIAL,
            ExecutionActionState.OPEN,
        ),
    ),
)
def test_late_terminal_action_preserves_v1_and_appends_converged_v2(
    monkeypatch: pytest.MonkeyPatch,
    entry_point: str,
    initial_result: PrimaryResult,
    initial_state: ExecutionActionState,
) -> None:
    activation_id = "activation-completed-late-action"
    action_id = "execution-action-late"
    initial_at = datetime(2026, 7, 20, 5, 30, tzinfo=UTC)
    observed_at = initial_at + timedelta(minutes=10)
    trace: list[str] = []
    initial_input_refs = {
        "activation": {"state_version": 4},
        "execution_actions": [
            {
                "execution_action_id": action_id,
                "state_version": 1,
                "state": initial_state.value,
            }
        ],
    }
    initial_fields = {
        "review_id": "10000000-0000-0000-0000-000000000001",
        "review_version": 1,
        "environment_id": "demo-main",
        "activation_id": activation_id,
        "previous_version": None,
        "status": ReviewStatus.DRAFT,
        "primary_result": initial_result,
        "fact_cutoff": initial_at,
        "input_refs": initial_input_refs,
        "input_digest": content_digest(initial_input_refs),
        "account_result": {
            "classification": (
                "UNKNOWN"
                if initial_result is PrimaryResult.RESULT_UNKNOWN
                else "NO_EXTERNAL_CHANGE"
            ),
            "venue_fact_refs": [],
            "missing_refs": [],
            "trade_result": None,
        },
        "open_responsibilities": {
            "execution_action_refs": [action_id],
            "unknown_action_refs": (
                [action_id]
                if initial_result is PrimaryResult.RESULT_UNKNOWN
                else []
            ),
            "responsibility_owner": "HALPHA",
            "takeover_scope": None,
        },
        "evaluations": {
            "owner_conclusion": {
                "result": "UNKNOWN",
                "reason": "",
                "evidence_refs": [],
            }
        },
        "evidence_purpose": EvidencePurpose.SYSTEM_MECHANISM_EVIDENCE,
        "created_at": initial_at,
    }
    versions = [
        Review(
            **initial_fields,
            content_digest=content_digest(initial_fields),
        )
    ]

    class Reviews:
        @staticmethod
        def get_latest_for_activation(
            current_activation_id: str,
            *,
            for_update: bool = False,
        ) -> Review:
            assert current_activation_id == activation_id
            assert for_update is True
            return versions[-1]

        @staticmethod
        def replace_review(
            review: Review,
            *,
            expected_content_digest: str,
        ) -> None:
            assert expected_content_digest == versions[-1].content_digest
            trace.append("OUT_SUPERSEDE_V1")
            versions[-1] = review

        @staticmethod
        def insert_review(review: Review) -> None:
            trace.append("OUT_INSERT_V2")
            versions.append(review)

    converged_input_refs = {
        "activation": {"state_version": 4},
        "execution_actions": [
            {
                "execution_action_id": action_id,
                "state_version": 2,
                "state": ExecutionActionState.CLOSED.value,
            }
        ],
    }
    converged_basis = {
        "input_refs": converged_input_refs,
        "primary_result": PrimaryResult.NO_ACTION,
        "account_result": {
            "classification": "NO_EXTERNAL_CHANGE",
            "venue_fact_refs": [],
            "missing_refs": [],
            "trade_result": None,
        },
        "open_responsibilities": {
            "execution_action_refs": [],
            "unknown_action_refs": [],
            "responsibility_owner": "HALPHA",
            "takeover_scope": None,
        },
        "evaluations": initial_fields["evaluations"],
        "evidence_purpose": EvidencePurpose.SYSTEM_MECHANISM_EVIDENCE,
    }
    outcome_service = object.__new__(OutcomeApplicationService)
    outcome_service._environment_id = "demo-main"
    outcome_service._repository = Reviews()
    outcome_service._collect_basis = (
        lambda current_activation_id, *, fact_cutoff: converged_basis
    )
    monkeypatch.setattr(
        "halpha.executor.coordinator.OutcomeApplicationService",
        lambda *_args: outcome_service,
    )

    class Transaction:
        def __enter__(self) -> None:
            trace.append("BEGIN")

        def __exit__(self, exc_type, *_args) -> bool:
            trace.append("ROLLBACK" if exc_type is not None else "COMMIT")
            return False

    initial_action = SimpleNamespace(
        execution_action_id=action_id,
        activation_id=activation_id,
        state=initial_state,
    )
    terminal_action = SimpleNamespace(
        execution_action_id=action_id,
        activation_id=activation_id,
        state=ExecutionActionState.CLOSED,
    )

    def close_action(*_args, **_kwargs):
        trace.append("AUTHORITATIVE_ACTION_MUTATION")
        return terminal_action

    coordinator = object.__new__(HalphaCoordinator)
    coordinator._connection = SimpleNamespace(transaction=Transaction)
    coordinator._environment_id = "demo-main"
    coordinator._planning = SimpleNamespace(
        get_activation=lambda _activation_id: SimpleNamespace(
            lifecycle=PlanLifecycle.COMPLETED
        )
    )
    coordinator._action_repository = SimpleNamespace(
        get=lambda _action_id, **_kwargs: initial_action
    )
    coordinator._execution = SimpleNamespace(
        record_definitely_not_submitted=close_action,
        reconcile_execution_action=close_action,
        reconcile_cancel_from_target_fact=close_action,
    )

    if entry_point == "unknown_absence":
        result = coordinator.record_unknown_action_not_submitted(
            action_id,
            reason_code="VENUE_QUERY_PROVED_ABSENT",
            observed_at=observed_at,
        )
    elif entry_point == "execution_reconciliation":
        result = coordinator.reconcile_execution_action(
            action_id,
            closure_evidence={"position_zero": True},
            venue_fact_refs=("fact-terminal",),
            observed_at=observed_at,
        )
    else:
        result = coordinator.reconcile_cancel_from_target_fact(
            action_id,
            target_fact=SimpleNamespace(activation_ref=activation_id),
            observed_at=observed_at,
        )

    assert result is terminal_action
    assert trace == [
        "BEGIN",
        "AUTHORITATIVE_ACTION_MUTATION",
        "COMMIT",
        "BEGIN",
        "OUT_SUPERSEDE_V1",
        "OUT_INSERT_V2",
        "COMMIT",
    ]
    assert len(versions) == 2
    assert versions[0].review_version == 1
    assert versions[0].status is ReviewStatus.SUPERSEDED
    assert versions[0].primary_result is initial_result
    assert versions[1].review_version == 2
    assert versions[1].previous_version == 1
    assert versions[1].status is ReviewStatus.DRAFT
    assert versions[1].primary_result is PrimaryResult.NO_ACTION
    assert versions[1].open_responsibilities["execution_action_refs"] == []
    assert versions[1].open_responsibilities["unknown_action_refs"] == []

    coordinator._refresh_completed_reviews_after_commit(
        terminal_actions=(terminal_action,),
        fact_cutoff=observed_at,
        observed_at=observed_at,
    )
    assert len(versions) == 2


def test_non_completed_activation_does_not_create_review_for_terminal_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_at = datetime(2026, 7, 20, 5, 40, tzinfo=UTC)
    action = SimpleNamespace(
        execution_action_id="execution-action-running",
        activation_id="activation-running",
        state=ExecutionActionState.CLOSED,
    )
    coordinator = object.__new__(HalphaCoordinator)
    coordinator._connection = SimpleNamespace(transaction=lambda: nullcontext())
    coordinator._environment_id = "demo-main"
    coordinator._planning = SimpleNamespace(
        get_activation=lambda _activation_id: SimpleNamespace(
            lifecycle=PlanLifecycle.RUNNING
        )
    )
    coordinator._execution = SimpleNamespace(
        reconcile_execution_action=lambda *_args, **_kwargs: action
    )
    monkeypatch.setattr(
        "halpha.executor.coordinator.OutcomeApplicationService",
        lambda *_args: pytest.fail(
            "a non-completed activation must not create an OUT review"
        ),
    )

    result = coordinator.reconcile_execution_action(
        action.execution_action_id,
        closure_evidence={"position_zero": True},
        venue_fact_refs=("fact-terminal",),
        observed_at=observed_at,
    )

    assert result is action


@pytest.mark.parametrize(
    "entry_point",
    (
        "apply_venue_fact",
        "nautilus_callback",
        "unattributed_account_fact",
    ),
)
def test_late_fact_refreshes_completed_review_only_after_fact_commit(
    monkeypatch: pytest.MonkeyPatch,
    entry_point: str,
) -> None:
    observed_at = datetime(2026, 7, 20, 5, 45, tzinfo=UTC)
    activation_id = "activation-completed-late-fact"
    action = SimpleNamespace(
        execution_action_id="execution-action-closed",
        activation_id=activation_id,
        action_kind=ExecutionActionKind.ENTRY,
        state=ExecutionActionState.CLOSED,
    )
    fact = SimpleNamespace(
        venue_fact_id="late-commission-fact",
        activation_ref=(
            None if entry_point == "unattributed_account_fact" else activation_id
        ),
        impact_scope=(
            {"account_episode_activation_id": activation_id}
            if entry_point == "unattributed_account_fact"
            else None
        ),
        kind=VenueFactKind.COMMISSION,
        payload={},
        cutoff=observed_at,
    )
    trace: list[str] = []
    reviews: list[tuple[str, datetime, datetime]] = []

    class Transaction:
        def __enter__(self) -> None:
            trace.append("BEGIN")

        def __exit__(self, exc_type, *_args) -> bool:
            trace.append("ROLLBACK" if exc_type is not None else "COMMIT")
            return False

    def apply_fact(**_kwargs):
        trace.append("AUTHORITATIVE_FACT_MUTATION")
        return (
            None
            if entry_point == "unattributed_account_fact"
            else action
        )

    class Outcomes:
        def __init__(self, _connection, _environment_id):
            pass

        @staticmethod
        def update_activation_review(
            current_activation_id: str,
            *,
            fact_cutoff: datetime,
            observed_at: datetime,
        ) -> None:
            trace.append("OUT_REFRESH")
            reviews.append((current_activation_id, fact_cutoff, observed_at))

    monkeypatch.setattr(
        "halpha.executor.coordinator.OutcomeApplicationService",
        Outcomes,
    )
    coordinator = object.__new__(HalphaCoordinator)
    coordinator._connection = SimpleNamespace(transaction=Transaction)
    coordinator._environment_id = "demo-main"
    coordinator._planning = SimpleNamespace(
        get_activation=lambda _activation_id: SimpleNamespace(
            lifecycle=PlanLifecycle.COMPLETED
        )
    )
    coordinator._execution = SimpleNamespace(apply_venue_fact=apply_fact)
    coordinator._action_repository = SimpleNamespace(
        find_open_cancel_for_target=lambda _client_order_id: None
    )

    if entry_point in {"apply_venue_fact", "unattributed_account_fact"}:
        result = coordinator.apply_venue_fact(fact, observed_at=observed_at)
        if entry_point == "unattributed_account_fact":
            assert result is None
        else:
            assert result is action
    else:
        normalized = NormalizedNautilusEvent(action=action, facts=(fact,))
        normalizer = SimpleNamespace(
            normalize=lambda _event, **_kwargs: normalized
        )
        result = coordinator.handle_nautilus_order_event(
            normalizer,
            object(),
            observed_at=observed_at,
        )
        assert result is normalized

    assert trace == [
        "BEGIN",
        "AUTHORITATIVE_FACT_MUTATION",
        "COMMIT",
        "BEGIN",
        "OUT_REFRESH",
        "COMMIT",
    ]
    assert reviews == [(activation_id, observed_at, observed_at)]


def test_outcome_failure_cannot_undo_terminal_action_commit(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    observed_at = datetime(2026, 7, 20, 5, 50, tzinfo=UTC)
    activation_id = "activation-completed-out-failure"
    trace: list[str] = []
    unknown = SimpleNamespace(
        execution_action_id="execution-action-out-failure",
        activation_id=activation_id,
        state=ExecutionActionState.UNKNOWN,
    )
    terminal = SimpleNamespace(
        execution_action_id=unknown.execution_action_id,
        activation_id=activation_id,
        state=ExecutionActionState.NOT_SUBMITTED,
    )

    class Transaction:
        def __enter__(self) -> None:
            trace.append("BEGIN")

        def __exit__(self, exc_type, *_args) -> bool:
            trace.append("ROLLBACK" if exc_type is not None else "COMMIT")
            return False

    def close_action(*_args, **_kwargs):
        trace.append("AUTHORITATIVE_ACTION_MUTATION")
        return terminal

    class FailingOutcomes:
        def __init__(self, _connection, _environment_id):
            pass

        @staticmethod
        def update_activation_review(*_args, **_kwargs) -> None:
            trace.append("OUT_FAILURE")
            raise RuntimeError("OUT_UNAVAILABLE")

    monkeypatch.setattr(
        "halpha.executor.coordinator.OutcomeApplicationService",
        FailingOutcomes,
    )
    coordinator = object.__new__(HalphaCoordinator)
    coordinator._connection = SimpleNamespace(transaction=Transaction)
    coordinator._environment_id = "demo-main"
    coordinator._planning = SimpleNamespace(
        get_activation=lambda _activation_id: SimpleNamespace(
            lifecycle=PlanLifecycle.COMPLETED
        )
    )
    coordinator._action_repository = SimpleNamespace(
        get=lambda _action_id, **_kwargs: unknown
    )
    coordinator._execution = SimpleNamespace(
        record_definitely_not_submitted=close_action
    )

    result = coordinator.record_unknown_action_not_submitted(
        unknown.execution_action_id,
        reason_code="VENUE_QUERY_PROVED_ABSENT",
        observed_at=observed_at,
    )

    assert result is terminal
    assert trace == [
        "BEGIN",
        "AUTHORITATIVE_ACTION_MUTATION",
        "COMMIT",
        "BEGIN",
        "OUT_FAILURE",
        "ROLLBACK",
    ]
    assert "Failed to refresh completed activation review" in caplog.text


def test_terminal_target_fact_reconciles_its_open_cancel_action() -> None:
    observed_at = datetime(2026, 7, 20, 1, 35, tzinfo=UTC)
    target_client_order_id = "a" * 32
    target = SimpleNamespace(
        activation_id="activation-demo-001",
        action_kind=ExecutionActionKind.PROTECTION,
        state=ExecutionActionState.OPEN,
    )
    cancel = SimpleNamespace(execution_action_id="cancel-action-001")
    reconciled: list[tuple[str, object, datetime]] = []

    class Execution:
        @staticmethod
        def apply_venue_fact(**_values):
            return target

        @staticmethod
        def reconcile_cancel_from_target_fact(
            action_id: str,
            *,
            target_fact: object,
            observed_at: datetime,
        ) -> None:
            reconciled.append((action_id, target_fact, observed_at))

    coordinator = object.__new__(HalphaCoordinator)
    coordinator._connection = SimpleNamespace(transaction=lambda: nullcontext())
    coordinator._execution = Execution()
    coordinator._planning = SimpleNamespace(
        get_activation=lambda *_args, **_kwargs: SimpleNamespace(
            protection_state=ProtectionState.UNKNOWN
        ),
        update_protection_projection=lambda **_values: None
    )
    coordinator._action_repository = SimpleNamespace(
        list_for_activation=lambda _activation_id: (),
        find_open_cancel_for_target=lambda client_id: (
            cancel if client_id == target_client_order_id else None
        )
    )
    coordinator._fact_repository = SimpleNamespace(
        list_for_action=lambda _action_id: ()
    )

    facts = (
        SimpleNamespace(
            venue_fact_id="cancelled-fact",
            kind=VenueFactKind.ORDER_STATE,
            payload={
                "status": "CANCELLED",
                "client_order_id": target_client_order_id,
            },
            source_time=observed_at,
            cutoff=observed_at,
            received_at=observed_at,
        ),
        SimpleNamespace(
            venue_fact_id="filled-fact",
            kind=VenueFactKind.FILL,
            payload={
                "leaves_quantity": "0",
                "client_order_id": target_client_order_id,
            },
            source_time=observed_at,
            cutoff=observed_at,
            received_at=observed_at,
        ),
    )

    for fact in facts:
        updated = coordinator.apply_venue_fact(fact, observed_at=observed_at)
        assert updated is target

    assert reconciled == [
        ("cancel-action-001", fact, observed_at) for fact in facts
    ]


def test_expired_empty_entry_window_closes_and_creates_review(monkeypatch) -> None:
    observed_at = datetime(2026, 7, 20, 1, tzinfo=UTC)
    deadline = datetime(2026, 7, 20, 0, 59, tzinfo=UTC)
    expired = SimpleNamespace(
        has_entry_fill=False,
        pending_action_digest=None,
    )
    event = SimpleNamespace(
        plan_event_id="plan-event-expired-001",
        source_cutoff=deadline,
    )
    completed = SimpleNamespace(lifecycle=PlanLifecycle.COMPLETED)
    completion: dict[str, object] = {}
    reviews: list[tuple[str, datetime, datetime]] = []

    class Planning:
        @staticmethod
        def expire_entry_deadline(**values):
            assert values["activation_id"] == "activation-demo-expired"
            assert values["observed_at"] == observed_at
            return expired, event

        @staticmethod
        def complete_with_execution_closure(**values):
            completion.update(values)
            return completed

    class Outcomes:
        def __init__(self, _connection, _environment_id):
            pass

        @staticmethod
        def update_activation_review(
            activation_id: str,
            *,
            fact_cutoff: datetime,
            observed_at: datetime,
        ) -> None:
            reviews.append((activation_id, fact_cutoff, observed_at))

    monkeypatch.setattr(
        "halpha.executor.coordinator.OutcomeApplicationService",
        Outcomes,
    )
    coordinator = object.__new__(HalphaCoordinator)
    coordinator._connection = SimpleNamespace(transaction=lambda: nullcontext())
    coordinator._environment_id = "demo-main"
    coordinator._planning = Planning()
    coordinator._action_repository = SimpleNamespace(
        list_for_activation=lambda _activation_id: ()
    )

    result, result_event = coordinator.expire_empty_entry_window(
        activation_id="activation-demo-expired",
        observed_at=observed_at,
    )

    assert result is completed
    assert result_event is event
    assert completion["result_ref"]
    assert len(str(completion["closure_digest"])) == 64
    assert reviews == [("activation-demo-expired", deadline, observed_at)]


def test_live_gate_closing_after_submitting_records_not_submitted_without_venue_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    activation_id = "activation-live-001"
    action_id = "execution-action-live-001"
    observed_at = datetime(2026, 7, 18, 13, 0, tzinfo=UTC)
    action_terms = {
        "instrument_ref": "BTCUSDT-PERP",
        "action_profile": "ENTRY_MARKET",
        "quantity": "0.001",
    }
    action = SimpleNamespace(
        execution_action_id=action_id,
        environment_id="live-main",
        environment_kind=EnvironmentKind.LIVE,
        authority_class=AuthorityClass.LIVE_REAL_CAPITAL,
        activation_id=activation_id,
        account_ref="live-owner",
        action_class=RiskClass.RISK_INCREASING,
        action_terms=action_terms,
    )
    prepared = SimpleNamespace(
        **vars(action),
        state=ExecutionActionState.SUBMITTING,
        state_digest="d" * 64,
    )
    action_check = SimpleNamespace(
        environment_id="live-main",
        environment_kind=EnvironmentKind.LIVE,
        authority_class=AuthorityClass.LIVE_REAL_CAPITAL,
        activation_id=activation_id,
        account_ref="live-owner",
        instrument_ref="BTCUSDT-PERP",
        action_profile="ENTRY_MARKET",
        risk_class=RiskClass.RISK_INCREASING,
        quantized_quantity="0.001",
    )
    gate_checks: list[str] = []

    def current_gate_guard(current_activation_id: str) -> None:
        gate_checks.append(current_activation_id)
        if len(gate_checks) == 2:
            raise RuntimeError("binding-revoked-after-submitting")

    recorded: list[tuple[str, str]] = []
    dispatch_locks: list[tuple[object, str, str]] = []

    def dispatch_lock(
        connection: object,
        *,
        environment_id: str,
        activation_id: str,
    ):
        dispatch_locks.append((connection, environment_id, activation_id))
        return nullcontext()

    monkeypatch.setattr(
        "halpha.executor.coordinator.serialize_activation_dispatch",
        dispatch_lock,
    )

    class ExecutionService:
        @staticmethod
        def prepare_submission(*args, **kwargs):
            assert args == (action_id,)
            assert kwargs["observed_at"] == observed_at
            return prepared

        @staticmethod
        def record_definitely_not_submitted(
            execution_action_id: str,
            *,
            reason_code: str,
            observed_at: datetime,
        ):
            assert observed_at == datetime(2026, 7, 18, 13, 0, tzinfo=UTC)
            recorded.append((execution_action_id, reason_code))
            values = {
                **vars(prepared),
                "state": ExecutionActionState.NOT_SUBMITTED,
                "not_submitted_reason": reason_code,
            }
            return SimpleNamespace(**values)

    coordinator = object.__new__(HalphaCoordinator)
    coordinator._environment_kind = "LIVE"
    coordinator._runtime_real_write_gate = "OPEN"
    coordinator._live_write_activation_id = activation_id
    coordinator._live_write_submission_guard = current_gate_guard
    coordinator._connection = SimpleNamespace(transaction=lambda: nullcontext())
    coordinator._action_repository = SimpleNamespace(
        get=lambda execution_action_id, **_kwargs: action
    )
    coordinator._planning = SimpleNamespace(
        get_activation=lambda current_activation_id, **_kwargs: SimpleNamespace(
            lifecycle=PlanLifecycle.RUNNING,
            run_state=RunState.ACTIVE,
        )
    )
    coordinator._capital = SimpleNamespace(
        check_current_action=lambda _check: SimpleNamespace(accepted=True)
    )
    coordinator._execution = ExecutionService()
    coordinator._gate = SimpleNamespace(
        authorize_committed_submission=lambda *_args, **_kwargs: pytest.fail(
            "a closed runtime gate must not authorize a venue call"
        ),
        execute_once=lambda *_args, **_kwargs: pytest.fail(
            "a closed runtime gate must not execute a venue call"
        ),
    )

    result = coordinator.process_execution_action(
        action_id,
        action_check=action_check,
        request_payload={"order_type": "MARKET", "quantity": "0.001"},
        observed_at=observed_at,
    )

    assert gate_checks == [activation_id, activation_id]
    assert dispatch_locks == [
        (coordinator._connection, "live-main", activation_id)
    ]
    assert recorded == [(action_id, "RUNTIME_REAL_WRITE_GATE_CLOSED")]
    assert result.venue_called is False
    assert result.reason_code == "RUNTIME_REAL_WRITE_GATE_CLOSED"
    assert result.execution_action.state is ExecutionActionState.NOT_SUBMITTED
