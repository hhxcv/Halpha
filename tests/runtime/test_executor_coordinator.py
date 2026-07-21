from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from halpha.capital.models import AuthorityClass, EnvironmentKind, RiskClass
from halpha.executor.coordinator import (
    HalphaCoordinator,
    _protection_projection_state,
    _submission_block_reason,
)
from halpha.planning.models import (
    PlanLifecycle,
    ProtectionState,
    RunState,
)
from halpha.venue_integration.models import (
    ExecutionActionKind,
    ExecutionActionState,
    VenueFactKind,
)
from halpha.venue_integration.nautilus_events import NormalizedNautilusEvent


def _action(kind: ExecutionActionKind, state: ExecutionActionState):
    return SimpleNamespace(action_kind=kind, state=state)


def _order_fact(status: str):
    return SimpleNamespace(kind=VenueFactKind.ORDER_STATE, payload={"status": status})


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


def test_cancelled_target_fact_reconciles_its_open_cancel_action() -> None:
    observed_at = datetime(2026, 7, 20, 1, 35, tzinfo=UTC)
    target_client_order_id = "a" * 32
    target = SimpleNamespace(
        activation_id="activation-demo-001",
        action_kind=ExecutionActionKind.PROTECTION,
        state=ExecutionActionState.OPEN,
    )
    cancel = SimpleNamespace(execution_action_id="cancel-action-001")
    fact = SimpleNamespace(
        kind=VenueFactKind.ORDER_STATE,
        payload={
            "status": "CANCELLED",
            "client_order_id": target_client_order_id,
        },
    )
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
        update_protection_projection=lambda **_values: None
    )
    coordinator._action_repository = SimpleNamespace(
        find_open_cancel_for_target=lambda client_id: (
            cancel if client_id == target_client_order_id else None
        )
    )

    updated = coordinator.apply_venue_fact(fact, observed_at=observed_at)

    assert updated is target
    assert reconciled == [("cancel-action-001", fact, observed_at)]


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


def test_live_gate_closing_after_submitting_records_not_submitted_without_venue_call() -> None:
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
    assert recorded == [(action_id, "RUNTIME_REAL_WRITE_GATE_CLOSED")]
    assert result.venue_called is False
    assert result.reason_code == "RUNTIME_REAL_WRITE_GATE_CLOSED"
    assert result.execution_action.state is ExecutionActionState.NOT_SUBMITTED
