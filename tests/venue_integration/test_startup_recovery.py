from __future__ import annotations

from datetime import UTC, datetime, timedelta

from halpha.capital.models import CapDecision, RiskClass
from halpha.domain_values import content_digest
from halpha.planning.models import PlanEvent, ProposedAction, ProposedActionKind
from halpha.planning.registry import Direction
from halpha.venue_integration.facts import build_venue_fact
from halpha.venue_integration.models import (
    ExecutionActionState,
    VenueFactKind,
    VenueFactSourceClass,
)
from halpha.venue_integration.service import ExecutionApplicationService
from halpha.venue_integration.transitions import (
    apply_venue_outcome,
    begin_submission,
    build_execution_action,
    mark_submission_unknown,
)


NOW = datetime(2026, 7, 17, 12, tzinfo=UTC)


def _submitting_action():
    proposed = ProposedAction(
        environment_id="demo-main",
        action_kind=ProposedActionKind.ENTRY,
        action_profile="ENTRY_MARKET",
        instrument_ref="BTCUSDT-PERP",
        direction=Direction.LONG,
        quantity="0.002",
        close_position=False,
        order_type="MARKET",
        reduce_only=False,
        source_responsibility="HALPHA_MONITORED",
        causation_ref="a" * 64,
    )
    capital = {
        "accepted": True,
        "reason_code": "ACCEPTED_RISK_INCREASING",
        "risk_class": "RISK_INCREASING",
    }
    event_fields = {
        "plan_event_id": "10000000-0000-0000-0000-000000000001",
        "environment_id": "demo-main",
        "activation_id": "10000000-0000-0000-0000-000000000002",
        "rule_id": "ENTRY",
        "source_identity": "activation:BAR:ENTRY:BTCUSDT:1",
        "source_cutoff": NOW,
        "input_digest": "b" * 64,
        "reason_code": "PROPOSED_ACTION_CAP_ACCEPTED",
        "condition_judgement": None,
        "proposed_action": proposed,
        "no_action_reason": None,
        "capital_decision": capital,
        "capital_decision_digest": content_digest(capital),
        "created_at": NOW,
    }
    action = build_execution_action(
        execution_action_id="10000000-0000-0000-0000-000000000003",
        plan_event=PlanEvent(
            **event_fields,
            content_digest=content_digest(event_fields),
        ),
        environment_kind="DEMO",
        authority_class="DEMO_VALIDATION",
        execution_profile_ref="BINANCE_DEMO",
        account_ref="demo-owner",
        observed_at=NOW,
        client_order_id="0123456789abcdef0123456789abcdef",
    )
    decision_fields = {
        "accepted": True,
        "reason_code": "ACCEPTED_RISK_INCREASING",
        "risk_class": RiskClass.RISK_INCREASING,
        "effective_leverage": "5",
        "action_notional": "100",
        "economic_action_notional": "100",
        "activation_notional_after": "100",
        "account_notional_after": "100",
        "activation_margin_after": "20",
        "stopped_categories": (),
        "input_digest": "c" * 64,
    }
    decision = CapDecision(
        **decision_fields,
        decision_digest=content_digest(decision_fields),
    )
    return begin_submission(
        action,
        capital_decision=decision,
        request_payload={"order_type": "MARKET", "quantity": "0.002"},
        observed_at=NOW + timedelta(seconds=1),
    )


class FakeActionRepository:
    def __init__(self, actions):
        self.actions = {action.execution_action_id: action for action in actions}

    def list_by_states(self, states, *, for_update=False):
        assert for_update is True
        return tuple(
            action for action in self.actions.values() if action.state.value in states
        )

    def update(self, action, *, expected_version):
        current = self.actions[action.execution_action_id]
        assert current.state_version == expected_version
        self.actions[action.execution_action_id] = action

    def list_for_activation(self, activation_id):
        return tuple(
            action
            for action in self.actions.values()
            if action.activation_id == activation_id
        )

    def get(self, execution_action_id, *, for_update=False):
        assert for_update is True
        return self.actions[execution_action_id]


class FakeFactRepository:
    def __init__(self):
        self.facts = {}

    def find_by_source(self, fact):
        return self.facts.get(fact.venue_fact_id)

    def insert(self, fact):
        self.facts[fact.venue_fact_id] = fact


def test_startup_recovery_makes_submitting_query_only_and_preserves_existing_unknown() -> None:
    submitting = _submitting_action()
    already_unknown = mark_submission_unknown(
        submitting.model_copy(
            update={
                "execution_action_id": "10000000-0000-0000-0000-000000000004",
                "client_order_id": "fedcba9876543210fedcba9876543210",
            }
        ),
        reason="EARLIER_TIMEOUT",
        next_query_at=NOW + timedelta(seconds=5),
        observed_at=NOW + timedelta(seconds=2),
    )
    repository = FakeActionRepository((submitting, already_unknown))
    service = ExecutionApplicationService(
        repository,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        environment_id="demo-main",
        environment_kind="DEMO",
        authority_class="DEMO_VALIDATION",
        execution_profile_ref="BINANCE_DEMO",
        account_ref="demo-owner",
    )

    recovered = service.prepare_startup_reconciliation(
        observed_at=NOW + timedelta(seconds=10)
    )

    assert tuple(action.state for action in recovered) == (
        ExecutionActionState.SUBMITTED_UNKNOWN,
        ExecutionActionState.SUBMITTED_UNKNOWN,
    )
    assert recovered[0].unknown_reason == "EXECUTOR_RESTART_AFTER_SUBMITTING"
    assert recovered[0].request_digest == submitting.request_digest
    assert recovered[1] is already_unknown
    assert all(action.state is not ExecutionActionState.READY for action in recovered)


def test_user_takeover_hands_over_only_ready_actions_and_never_retries_unknown() -> None:
    submitting = _submitting_action()
    ready = submitting.model_copy(
        update={
            "execution_action_id": "10000000-0000-0000-0000-000000000005",
            "client_order_id": "abcdef0123456789abcdef0123456789",
            "state": ExecutionActionState.READY,
            "state_version": 1,
            "request_digest": None,
            "call_started_at": None,
            "unknown_reason": None,
            "next_query_at": None,
        }
    )
    unknown = mark_submission_unknown(
        submitting,
        reason="VENUE_TIMEOUT",
        next_query_at=NOW + timedelta(seconds=5),
        observed_at=NOW + timedelta(seconds=2),
    )
    repository = FakeActionRepository((ready, unknown))
    service = ExecutionApplicationService(
        repository,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        environment_id="demo-main",
        environment_kind="DEMO",
        authority_class="DEMO_VALIDATION",
        execution_profile_ref="BINANCE_DEMO",
        account_ref="demo-owner",
    )

    results = service.apply_user_takeover(
        ready.activation_id,
        observed_at=NOW + timedelta(seconds=10),
    )

    states = {action.execution_action_id: action.state for action in results}
    assert states[ready.execution_action_id] is ExecutionActionState.HANDED_OVER
    assert states[unknown.execution_action_id] is ExecutionActionState.SUBMITTED_UNKNOWN


def test_late_acknowledgement_is_retained_without_regressing_working_state() -> None:
    submitting = _submitting_action()
    acknowledged = apply_venue_outcome(
        submitting,
        target=ExecutionActionState.ACKNOWLEDGED,
        venue_order_refs=("12345",),
        venue_fact_refs=("10000000-0000-0000-0000-000000000010",),
        observed_at=NOW + timedelta(seconds=2),
    )
    working = apply_venue_outcome(
        acknowledged,
        target=ExecutionActionState.WORKING,
        venue_order_refs=("12345",),
        venue_fact_refs=("10000000-0000-0000-0000-000000000011",),
        observed_at=NOW + timedelta(seconds=3),
    )
    late_ack = build_venue_fact(
        venue_fact_id="10000000-0000-0000-0000-000000000012",
        environment_id=working.environment_id,
        venue_ref="BINANCE",
        account_ref=working.account_ref,
        instrument_ref="BTCUSDT-PERP",
        kind=VenueFactKind.ORDER_STATE,
        source_class=VenueFactSourceClass.VENUE_STREAM,
        source_object_id=working.client_order_id or "",
        source_sequence="late-ack",
        source_time=NOW + timedelta(seconds=2),
        received_at=NOW + timedelta(seconds=4),
        cutoff=NOW + timedelta(seconds=4),
        payload={
            "status": "ACKNOWLEDGED",
            "venue_order_ref": "12345",
        },
        action=working,
    )
    actions = FakeActionRepository((working,))
    facts = FakeFactRepository()
    service = ExecutionApplicationService(
        actions,  # type: ignore[arg-type]
        facts,  # type: ignore[arg-type]
        environment_id="demo-main",
        environment_kind="DEMO",
        authority_class="DEMO_VALIDATION",
        execution_profile_ref="BINANCE_DEMO",
        account_ref="demo-owner",
    )

    updated = service.apply_venue_fact(
        fact=late_ack,
        observed_at=NOW + timedelta(seconds=4),
    )

    assert updated is not None
    assert updated.state is ExecutionActionState.WORKING
    assert updated.state_version == working.state_version + 1
    assert late_ack.venue_fact_id in updated.venue_fact_refs
    assert facts.facts[late_ack.venue_fact_id] is late_ack
