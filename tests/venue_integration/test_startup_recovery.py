from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from halpha.capital.models import CapDecision, RiskClass
from halpha.domain_values import content_digest
from halpha.planning.models import PlanEvent, ProposedAction, ProposedActionKind
from halpha.planning.registry import Direction
from halpha.venue_integration.facts import build_venue_fact, latest_execution_status
from halpha.venue_integration.models import (
    ExecutionActionState,
    VenueFactKind,
    VenueFactSourceClass,
)
from halpha.venue_integration.service import ExecutionApplicationService
from halpha.venue_integration.transitions import (
    begin_submission,
    build_execution_action,
    mark_action_open,
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
        return next(
            (
                existing
                for existing in self.facts.values()
                if (
                    existing.environment_id,
                    existing.source_class,
                    existing.source_object_id,
                    existing.source_sequence,
                )
                == (
                    fact.environment_id,
                    fact.source_class,
                    fact.source_object_id,
                    fact.source_sequence,
                )
            ),
            None,
        )

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
    already_open = mark_action_open(
        submitting.model_copy(
            update={
                "execution_action_id": "10000000-0000-0000-0000-000000000006",
                "client_order_id": "00112233445566778899aabbccddeeff",
            }
        ),
        venue_order_refs=("venue-order-open",),
        venue_fact_refs=("open-fact",),
        observed_at=NOW + timedelta(seconds=3),
    )
    repository = FakeActionRepository((submitting, already_unknown, already_open))
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
        ExecutionActionState.UNKNOWN,
        ExecutionActionState.UNKNOWN,
        ExecutionActionState.OPEN,
    )
    assert recovered[0].unknown_reason == "EXECUTOR_RESTART_AFTER_SUBMITTING"
    assert recovered[0].request_digest == submitting.request_digest
    assert recovered[1] is already_unknown
    assert recovered[2] is already_open
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
    assert states[unknown.execution_action_id] is ExecutionActionState.UNKNOWN


def test_late_acknowledgement_is_retained_without_regressing_working_state() -> None:
    submitting = _submitting_action()
    working_fact = build_venue_fact(
        venue_fact_id="10000000-0000-0000-0000-000000000011",
        environment_id=submitting.environment_id,
        venue_ref="BINANCE",
        account_ref=submitting.account_ref,
        instrument_ref="BTCUSDT-PERP",
        kind=VenueFactKind.ORDER_STATE,
        source_class=VenueFactSourceClass.VENUE_STREAM,
        source_object_id=submitting.client_order_id or "",
        source_sequence="working",
        source_time=NOW + timedelta(seconds=3),
        received_at=NOW + timedelta(seconds=3),
        cutoff=NOW + timedelta(seconds=3),
        payload={"status": "WORKING", "venue_order_ref": "12345"},
        action=submitting,
    )
    late_ack = build_venue_fact(
        venue_fact_id="10000000-0000-0000-0000-000000000012",
        environment_id=submitting.environment_id,
        venue_ref="BINANCE",
        account_ref=submitting.account_ref,
        instrument_ref="BTCUSDT-PERP",
        kind=VenueFactKind.ORDER_STATE,
        source_class=VenueFactSourceClass.VENUE_STREAM,
        source_object_id=submitting.client_order_id or "",
        source_sequence="late-ack",
        source_time=NOW + timedelta(seconds=2),
        received_at=NOW + timedelta(seconds=4),
        cutoff=NOW + timedelta(seconds=4),
        payload={
            "status": "ACKNOWLEDGED",
            "venue_order_ref": "12345",
        },
        action=submitting,
    )
    actions = FakeActionRepository((submitting,))
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

    opened = service.apply_venue_fact(
        fact=working_fact,
        observed_at=working_fact.received_at,
    )
    updated = service.apply_venue_fact(
        fact=late_ack,
        observed_at=NOW + timedelta(seconds=4),
    )

    assert opened is not None
    assert updated is not None
    assert updated.state is ExecutionActionState.OPEN
    assert updated.state_version == opened.state_version + 1
    assert late_ack.venue_fact_id in updated.venue_fact_refs
    assert facts.facts[late_ack.venue_fact_id] is late_ack
    assert latest_execution_status(tuple(facts.facts.values())) == "WORKING"


def test_same_venue_version_reobserved_later_is_idempotent() -> None:
    action = _submitting_action()
    actions = FakeActionRepository((action,))
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
    first = build_venue_fact(
        venue_fact_id="10000000-0000-0000-0000-000000000020",
        environment_id=action.environment_id,
        venue_ref="BINANCE",
        account_ref=action.account_ref,
        instrument_ref="BTCUSDT-PERP",
        kind=VenueFactKind.ORDER_STATE,
        source_class=VenueFactSourceClass.VENUE_QUERY,
        source_object_id="venue-order-1",
        source_sequence="123:WORKING",
        source_time=NOW,
        received_at=NOW + timedelta(seconds=1),
        cutoff=NOW + timedelta(seconds=1),
        payload={"status": "WORKING", "venue_order_ref": "venue-order-1"},
        action=action,
    )
    repeated = build_venue_fact(
        venue_fact_id="10000000-0000-0000-0000-000000000021",
        environment_id=action.environment_id,
        venue_ref="BINANCE",
        account_ref=action.account_ref,
        instrument_ref="BTCUSDT-PERP",
        kind=VenueFactKind.ORDER_STATE,
        source_class=VenueFactSourceClass.VENUE_QUERY,
        source_object_id="venue-order-1",
        source_sequence="123:WORKING",
        source_time=NOW,
        received_at=NOW + timedelta(seconds=2),
        cutoff=NOW + timedelta(seconds=2),
        payload={"status": "WORKING", "venue_order_ref": "venue-order-1"},
        action=action,
    )

    first_result = service.apply_venue_fact(
        fact=first,
        observed_at=first.received_at,
    )
    repeated_result = service.apply_venue_fact(
        fact=repeated,
        observed_at=repeated.received_at,
    )

    assert first_result is not None
    assert repeated_result is first_result
    assert tuple(facts.facts) == (first.venue_fact_id,)


def test_same_venue_version_with_changed_payload_is_a_conflict() -> None:
    action = _submitting_action()
    actions = FakeActionRepository((action,))
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
    first = build_venue_fact(
        venue_fact_id="10000000-0000-0000-0000-000000000022",
        environment_id=action.environment_id,
        venue_ref="BINANCE",
        account_ref=action.account_ref,
        instrument_ref="BTCUSDT-PERP",
        kind=VenueFactKind.ORDER_STATE,
        source_class=VenueFactSourceClass.VENUE_QUERY,
        source_object_id="venue-order-2",
        source_sequence="456:WORKING",
        source_time=NOW,
        received_at=NOW + timedelta(seconds=1),
        cutoff=NOW + timedelta(seconds=1),
        payload={"status": "WORKING", "venue_order_ref": "venue-order-2"},
        action=action,
    )
    conflict = build_venue_fact(
        venue_fact_id="10000000-0000-0000-0000-000000000023",
        environment_id=action.environment_id,
        venue_ref="BINANCE",
        account_ref=action.account_ref,
        instrument_ref="BTCUSDT-PERP",
        kind=VenueFactKind.ORDER_STATE,
        source_class=VenueFactSourceClass.VENUE_QUERY,
        source_object_id="venue-order-2",
        source_sequence="456:WORKING",
        source_time=NOW,
        received_at=NOW + timedelta(seconds=2),
        cutoff=NOW + timedelta(seconds=2),
        payload={"status": "CANCELLED", "venue_order_ref": "venue-order-2"},
        action=action,
    )
    service.apply_venue_fact(fact=first, observed_at=first.received_at)

    with pytest.raises(ValueError, match="FACT_CONFLICT"):
        service.apply_venue_fact(fact=conflict, observed_at=conflict.received_at)
