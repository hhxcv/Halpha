from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from halpha.capital.models import CapDecision, RiskClass
from halpha.domain_values import content_digest
from halpha.planning.models import PlanEvent, ProposedAction, ProposedActionKind
from halpha.planning.registry import Direction
from halpha.venue_integration.facts import (
    build_venue_fact,
    latest_execution_status,
    venue_trade_fact_id,
    venue_trade_fact_is_canonicalizable,
)
from halpha.venue_integration.models import (
    BINANCE_USDM_VENUE_REF,
    ExecutionActionState,
    VenueFactKind,
    VenueFactSourceClass,
)
from halpha.venue_integration.service import ExecutionApplicationService
from halpha.venue_integration.transitions import (
    begin_submission,
    build_execution_action,
    mark_action_open,
    mark_not_submitted,
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

    def list_trade_versions(self, fact):
        return tuple(
            existing
            for existing in self.facts.values()
            if (
                existing.environment_id,
                existing.kind,
                existing.source_object_id,
                existing.account_ref,
                existing.instrument_ref,
            )
            == (
                fact.environment_id,
                fact.kind,
                fact.source_object_id,
                fact.account_ref,
                fact.instrument_ref,
            )
        )

    def insert(self, fact):
        if fact.venue_fact_id in self.facts:
            return False
        self.facts[fact.venue_fact_id] = fact
        return True

    def get(self, venue_fact_id):
        return self.facts[venue_fact_id]

    def list_for_action(self, execution_action_id):
        return tuple(
            fact
            for fact in self.facts.values()
            if fact.action_ref == execution_action_id
        )


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
    facts = FakeFactRepository()
    service = ExecutionApplicationService(
        repository,  # type: ignore[arg-type]
        facts,  # type: ignore[arg-type]
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


def test_startup_does_not_requery_open_action_with_complete_terminal_fact() -> None:
    submitting = _submitting_action()
    already_open = mark_action_open(
        submitting,
        venue_order_refs=("venue-order-rejected",),
        venue_fact_refs=(),
        observed_at=NOW + timedelta(seconds=2),
    )
    terminal = build_venue_fact(
        venue_fact_id="10000000-0000-0000-0000-000000000014",
        environment_id=already_open.environment_id,
        venue_ref=BINANCE_USDM_VENUE_REF,
        account_ref=already_open.account_ref,
        instrument_ref="BTCUSDT-PERP",
        kind=VenueFactKind.ORDER_STATE,
        source_class=VenueFactSourceClass.VENUE_QUERY,
        source_object_id=already_open.client_order_id or "",
        source_sequence="terminal-rejected-query",
        source_time=NOW + timedelta(seconds=3),
        received_at=NOW + timedelta(seconds=3),
        cutoff=NOW + timedelta(seconds=3),
        payload={
            "status": "REJECTED",
            "venue_order_ref": "venue-order-rejected",
            "venue_order_quantity": "0.002",
            "cumulative_filled_quantity": "0",
            "reconciliation": True,
            "event_type": "BinanceAlgoOrderQuery",
        },
        action=already_open,
    )
    actions = FakeActionRepository((already_open,))
    facts = FakeFactRepository()
    assert facts.insert(terminal) is True
    service = ExecutionApplicationService(
        actions,  # type: ignore[arg-type]
        facts,  # type: ignore[arg-type]
        environment_id="demo-main",
        environment_kind="DEMO",
        authority_class="DEMO_VALIDATION",
        execution_profile_ref="BINANCE_DEMO",
        account_ref="demo-owner",
    )

    recovered = service.prepare_startup_reconciliation(
        observed_at=NOW + timedelta(seconds=10)
    )

    assert recovered == ()
    assert actions.actions[already_open.execution_action_id] is already_open


def test_startup_accepts_filled_child_after_conditional_wrapper_cancel() -> None:
    already_open = mark_action_open(
        _submitting_action(),
        venue_order_refs=("ordinary-child-order", "conditional-wrapper"),
        venue_fact_refs=(),
        observed_at=NOW + timedelta(seconds=2),
    )

    def fact(
        *,
        fact_id: str,
        kind: VenueFactKind,
        source_object_id: str,
        source_time: datetime,
        payload: dict[str, object],
    ):
        return build_venue_fact(
            venue_fact_id=fact_id,
            environment_id=already_open.environment_id,
            venue_ref=BINANCE_USDM_VENUE_REF,
            account_ref=already_open.account_ref,
            instrument_ref="BTCUSDT-PERP",
            kind=kind,
            source_class=VenueFactSourceClass.VENUE_QUERY,
            source_object_id=source_object_id,
            source_sequence=fact_id,
            source_time=source_time,
            received_at=source_time,
            cutoff=source_time,
            payload=payload,
            action=already_open,
        )

    filled = fact(
        fact_id="10000000-0000-0000-0000-000000000015",
        kind=VenueFactKind.ORDER_STATE,
        source_object_id=already_open.client_order_id or "",
        source_time=NOW + timedelta(seconds=3),
        payload={
            "status": "FILLED",
            "venue_order_ref": "ordinary-child-order",
            "venue_order_quantity": "0.002",
            "cumulative_filled_quantity": "0.002",
            "reconciliation": True,
            "event_type": "BinanceOrderQuery",
        },
    )
    trade = fact(
        fact_id="10000000-0000-0000-0000-000000000016",
        kind=VenueFactKind.FILL,
        source_object_id="987654321",
        source_time=NOW + timedelta(seconds=3),
        payload={
            "trade_id": "987654321",
            "client_order_id": already_open.client_order_id,
            "venue_order_ref": "ordinary-child-order",
            "last_price": "50000",
            "last_quantity": "0.002",
            "order_side": "BUY",
            "liquidity_side": "TAKER",
            "reconciliation": True,
            "event_type": "BinanceUserTradeQuery",
        },
    )
    wrapper_cancel = fact(
        fact_id="10000000-0000-0000-0000-000000000017",
        kind=VenueFactKind.ORDER_STATE,
        source_object_id=already_open.client_order_id or "",
        source_time=NOW + timedelta(seconds=4),
        payload={
            "status": "CANCELLED",
            "venue_order_ref": "conditional-wrapper",
            "venue_order_quantity": "0.002",
            "cumulative_filled_quantity": "0",
            "reconciliation": True,
            "event_type": "OrderCanceled",
        },
    )
    actions = FakeActionRepository((already_open,))
    facts = FakeFactRepository()
    for item in (filled, trade, wrapper_cancel):
        assert facts.insert(item) is True
    service = ExecutionApplicationService(
        actions,  # type: ignore[arg-type]
        facts,  # type: ignore[arg-type]
        environment_id="demo-main",
        environment_kind="DEMO",
        authority_class="DEMO_VALIDATION",
        execution_profile_ref="BINANCE_DEMO",
        account_ref="demo-owner",
    )

    assert service.prepare_startup_reconciliation(
        observed_at=NOW + timedelta(seconds=10)
    ) == ()


def test_user_takeover_hands_over_uncalled_and_unresolved_actions() -> None:
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
    repository = FakeActionRepository((ready, submitting, unknown))
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
    assert states[submitting.execution_action_id] is ExecutionActionState.HANDED_OVER
    assert states[unknown.execution_action_id] is ExecutionActionState.HANDED_OVER
    handed_unknown = repository.actions[unknown.execution_action_id]
    assert handed_unknown.request_digest == unknown.request_digest
    assert handed_unknown.call_started_at == unknown.call_started_at
    assert handed_unknown.unknown_reason is None
    assert handed_unknown.next_query_at is None


def test_late_fill_is_retained_for_handed_over_called_action() -> None:
    unknown = mark_submission_unknown(
        _submitting_action(),
        reason="VENUE_TIMEOUT",
        next_query_at=NOW + timedelta(seconds=5),
        observed_at=NOW + timedelta(seconds=2),
    )
    actions = FakeActionRepository((unknown,))
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
    handed = service.apply_user_takeover(
        unknown.activation_id,
        observed_at=NOW + timedelta(seconds=10),
    )[0]
    late_fill = build_venue_fact(
        venue_fact_id="10000000-0000-0000-0000-000000000013",
        environment_id=handed.environment_id,
        venue_ref=BINANCE_USDM_VENUE_REF,
        account_ref=handed.account_ref,
        instrument_ref="BTCUSDT-PERP",
        kind=VenueFactKind.FILL,
        source_class=VenueFactSourceClass.VENUE_STREAM,
        source_object_id="trade-after-handover",
        source_sequence="late-fill-event",
        source_time=NOW + timedelta(seconds=11),
        received_at=NOW + timedelta(seconds=11),
        cutoff=NOW + timedelta(seconds=11),
        payload={
            "trade_id": "trade-after-handover",
            "client_order_id": handed.client_order_id,
            "venue_order_ref": "venue-order-after-handover",
            "last_price": "50000",
            "last_quantity": "0.001",
            "order_side": "BUY",
            "liquidity_side": "TAKER",
        },
        action=handed,
    )

    application = service.apply_venue_fact_with_result(
        fact=late_fill,
        observed_at=late_fill.received_at,
    )

    assert application.inserted is True
    assert application.action is not None
    assert application.action.state is ExecutionActionState.HANDED_OVER
    assert application.action.request_digest == unknown.request_digest
    assert application.action.venue_order_refs == ("venue-order-after-handover",)
    assert application.action.venue_fact_refs == (late_fill.venue_fact_id,)


def test_late_acknowledgement_is_retained_without_regressing_working_state() -> None:
    submitting = _submitting_action()
    working_fact = build_venue_fact(
        venue_fact_id="10000000-0000-0000-0000-000000000011",
        environment_id=submitting.environment_id,
        venue_ref=BINANCE_USDM_VENUE_REF,
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
        venue_ref=BINANCE_USDM_VENUE_REF,
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


def test_late_fill_is_retained_without_reopening_not_submitted_action() -> None:
    submitting = _submitting_action()
    action = mark_not_submitted(
        submitting,
        reason_code="VENUE_QUERY_PROVED_ABSENT",
        observed_at=NOW + timedelta(seconds=1),
    )
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
    late_fill = build_venue_fact(
        venue_fact_id="10000000-0000-0000-0000-000000000040",
        environment_id=action.environment_id,
        venue_ref=BINANCE_USDM_VENUE_REF,
        account_ref=action.account_ref,
        instrument_ref="BTCUSDT-PERP",
        kind=VenueFactKind.FILL,
        source_class=VenueFactSourceClass.VENUE_STREAM,
        source_object_id="trade-late-after-absent",
        source_sequence="late-fill-event",
        source_time=NOW,
        received_at=NOW + timedelta(seconds=2),
        cutoff=NOW + timedelta(seconds=2),
        payload={
            "trade_id": "trade-late-after-absent",
            "client_order_id": action.client_order_id,
            "venue_order_ref": "venue-order-late",
            "last_price": "50000",
            "last_quantity": "0.001",
            "order_side": "BUY",
            "liquidity_side": "TAKER",
        },
        action=action,
    )

    application = service.apply_venue_fact_with_result(
        fact=late_fill,
        observed_at=late_fill.received_at,
    )

    assert application.inserted is True
    assert application.action is not None
    assert application.action.state is ExecutionActionState.NOT_SUBMITTED
    assert application.action.venue_order_refs == ("venue-order-late",)
    assert application.action.venue_fact_refs == (late_fill.venue_fact_id,)
    assert facts.facts[late_fill.venue_fact_id] is late_fill


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
        venue_ref=BINANCE_USDM_VENUE_REF,
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
        venue_ref=BINANCE_USDM_VENUE_REF,
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

    first_application = service.apply_venue_fact_with_result(
        fact=first,
        observed_at=first.received_at,
    )
    repeated_application = service.apply_venue_fact_with_result(
        fact=repeated,
        observed_at=repeated.received_at,
    )

    assert first_application.inserted is True
    assert first_application.canonical_fact is first
    assert first_application.action is not None
    assert repeated_application.inserted is False
    assert repeated_application.canonical_fact is first
    assert repeated_application.action is first_application.action
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
        venue_ref=BINANCE_USDM_VENUE_REF,
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
        venue_ref=BINANCE_USDM_VENUE_REF,
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


def test_same_trade_from_stream_and_reconciliation_is_one_economic_fill() -> None:
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
    common = {
        "environment_id": action.environment_id,
        "venue_ref": BINANCE_USDM_VENUE_REF,
        "account_ref": action.account_ref,
        "instrument_ref": "BTCUSDT-PERP",
        "kind": VenueFactKind.FILL,
        "source_object_id": "trade-duplicate-1",
        "source_time": NOW,
        "action": action,
    }
    stream = build_venue_fact(
        venue_fact_id="10000000-0000-0000-0000-000000000026",
        source_class=VenueFactSourceClass.VENUE_STREAM,
        source_sequence="stream-event-uuid",
        received_at=NOW + timedelta(seconds=1),
        cutoff=NOW + timedelta(seconds=1),
        payload={
            "event_type": "OrderFilled",
            "trade_id": "trade-duplicate-1",
            "client_order_id": action.client_order_id,
            "venue_order_ref": "venue-order-1",
            "last_price": "50000.1",
            "last_quantity": "0.001",
            "leaves_quantity": "0.001",
            "order_side": "BUY",
            "liquidity_side": "TAKER",
            "reconciliation": False,
        },
        **common,
    )
    reconciliation = build_venue_fact(
        venue_fact_id="10000000-0000-0000-0000-000000000027",
        source_class=VenueFactSourceClass.VENUE_QUERY,
        source_sequence="reconciliation-event-uuid",
        received_at=NOW + timedelta(seconds=2),
        cutoff=NOW + timedelta(seconds=2),
        payload={
            **stream.payload,
            "leaves_quantity": "0",
            "reconciliation": True,
        },
        **common,
    )

    first = service.apply_venue_fact_with_result(
        fact=stream,
        observed_at=stream.received_at,
    )
    repeated = service.apply_venue_fact_with_result(
        fact=reconciliation,
        observed_at=reconciliation.received_at,
    )

    assert first.inserted is True
    assert repeated.inserted is False
    assert repeated.canonical_fact is stream
    assert tuple(facts.facts) == (stream.venue_fact_id,)
    assert repeated.action is first.action


def test_cumulative_entry_fill_above_action_quantity_is_retained_and_flagged() -> None:
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

    def fill(trade_id: str, quantity: str, offset: int):
        fact = build_venue_fact(
            venue_fact_id=f"10000000-0000-0000-0000-{offset:012d}",
            environment_id=action.environment_id,
            venue_ref=BINANCE_USDM_VENUE_REF,
            account_ref=action.account_ref,
            instrument_ref="BTCUSDT-PERP",
            kind=VenueFactKind.FILL,
            source_class=VenueFactSourceClass.VENUE_STREAM,
            source_object_id=trade_id,
            source_sequence=f"event-{offset}",
            source_time=NOW + timedelta(seconds=offset),
            received_at=NOW + timedelta(seconds=offset),
            cutoff=NOW + timedelta(seconds=offset),
            payload={
                "trade_id": trade_id,
                "client_order_id": action.client_order_id,
                "venue_order_ref": "venue-order-overfill",
                "last_price": "50000",
                "last_quantity": quantity,
                "order_side": "BUY",
                "liquidity_side": "TAKER",
            },
            action=action,
        )
        return fact.model_copy(
            update={"venue_fact_id": venue_trade_fact_id(fact)}
        )

    first = fill("trade-overfill-1", "0.0015", 50)
    second = fill("trade-overfill-2", "0.001", 51)

    first_result = service.apply_venue_fact_with_result(
        fact=first,
        observed_at=first.received_at,
    )
    second_result = service.apply_venue_fact_with_result(
        fact=second,
        observed_at=second.received_at,
    )

    assert first_result.action_quantity_conflict is False
    assert second_result.action_quantity_conflict is True
    assert second_result.inserted is True
    assert set(facts.facts) == {first.venue_fact_id, second.venue_fact_id}


def test_venue_order_quantity_drift_is_retained_and_flagged() -> None:
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
    observation = build_venue_fact(
        venue_fact_id="10000000-0000-0000-0000-000000000052",
        environment_id=action.environment_id,
        venue_ref=BINANCE_USDM_VENUE_REF,
        account_ref=action.account_ref,
        instrument_ref="BTCUSDT-PERP",
        kind=VenueFactKind.ORDER_STATE,
        source_class=VenueFactSourceClass.VENUE_STREAM,
        source_object_id="venue-order-quantity-drift",
        source_sequence="event-quantity-drift",
        source_time=NOW,
        received_at=NOW + timedelta(seconds=1),
        cutoff=NOW + timedelta(seconds=1),
        payload={
            "status": "WORKING",
            "client_order_id": action.client_order_id,
            "venue_order_ref": "venue-order-quantity-drift",
            "venue_order_quantity": "0.003",
        },
        action=action,
    )

    result = service.apply_venue_fact_with_result(
        fact=observation,
        observed_at=observation.received_at,
    )

    assert result.inserted is True
    assert result.action_quantity_conflict is True
    assert facts.get(observation.venue_fact_id) is observation


def test_same_trade_id_with_changed_economic_fill_is_a_conflict() -> None:
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
    common = {
        "environment_id": action.environment_id,
        "venue_ref": BINANCE_USDM_VENUE_REF,
        "account_ref": action.account_ref,
        "instrument_ref": "BTCUSDT-PERP",
        "kind": VenueFactKind.FILL,
        "source_object_id": "trade-conflict-1",
        "source_time": NOW,
        "action": action,
    }
    first = build_venue_fact(
        venue_fact_id="10000000-0000-0000-0000-000000000028",
        source_class=VenueFactSourceClass.VENUE_STREAM,
        source_sequence="stream-event-uuid",
        received_at=NOW + timedelta(seconds=1),
        cutoff=NOW + timedelta(seconds=1),
        payload={
            "trade_id": "trade-conflict-1",
            "client_order_id": action.client_order_id,
            "venue_order_ref": "venue-order-1",
            "last_price": "50000.1",
            "last_quantity": "0.001",
            "order_side": "BUY",
            "liquidity_side": "TAKER",
        },
        **common,
    )
    conflict = build_venue_fact(
        venue_fact_id="10000000-0000-0000-0000-000000000029",
        source_class=VenueFactSourceClass.VENUE_QUERY,
        source_sequence="reconciliation-event-uuid",
        received_at=NOW + timedelta(seconds=2),
        cutoff=NOW + timedelta(seconds=2),
        payload={**first.payload, "last_quantity": "0.002"},
        **common,
    )
    service.apply_venue_fact(fact=first, observed_at=first.received_at)

    with pytest.raises(ValueError, match="FACT_CONFLICT"):
        service.apply_venue_fact(
            fact=conflict,
            observed_at=conflict.received_at,
        )


def test_same_commission_from_stream_and_reconciliation_is_one_fact() -> None:
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
    common = {
        "environment_id": action.environment_id,
        "venue_ref": BINANCE_USDM_VENUE_REF,
        "account_ref": action.account_ref,
        "instrument_ref": "BTCUSDT-PERP",
        "kind": VenueFactKind.COMMISSION,
        "source_object_id": "trade-commission-1",
        "source_time": NOW,
        "action": action,
    }
    stream = build_venue_fact(
        venue_fact_id="10000000-0000-0000-0000-000000000032",
        source_class=VenueFactSourceClass.VENUE_STREAM,
        source_sequence="stream-event:COMMISSION",
        received_at=NOW + timedelta(seconds=1),
        cutoff=NOW + timedelta(seconds=1),
        payload={
            "trade_id": "trade-commission-1",
            "client_order_id": action.client_order_id,
            "amount": "0.030 USDT",
            "currency": "usdt",
        },
        **common,
    )
    reconciliation = build_venue_fact(
        venue_fact_id="10000000-0000-0000-0000-000000000033",
        source_class=VenueFactSourceClass.VENUE_QUERY,
        source_sequence="query-event:COMMISSION",
        received_at=NOW + timedelta(seconds=2),
        cutoff=NOW + timedelta(seconds=2),
        payload={
            **stream.payload,
            "amount": "0.03 USDT",
            "currency": "USDT",
        },
        **common,
    )

    first = service.apply_venue_fact_with_result(
        fact=stream,
        observed_at=stream.received_at,
    )
    repeated = service.apply_venue_fact_with_result(
        fact=reconciliation,
        observed_at=reconciliation.received_at,
    )

    assert first.inserted is True
    assert repeated.inserted is False
    assert repeated.canonical_fact is stream
    assert tuple(facts.facts) == (stream.venue_fact_id,)


def test_trade_replay_selects_the_matching_legacy_version_not_the_first_row() -> None:
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
    common = {
        "environment_id": action.environment_id,
        "venue_ref": BINANCE_USDM_VENUE_REF,
        "account_ref": action.account_ref,
        "instrument_ref": "BTCUSDT-PERP",
        "kind": VenueFactKind.FILL,
        "source_object_id": "trade-legacy-versions",
        "source_time": NOW,
        "action": action,
    }

    def version(fact_id: str, sequence: str, quantity: str, seconds: int):
        return build_venue_fact(
            venue_fact_id=fact_id,
            source_class=VenueFactSourceClass.VENUE_STREAM,
            source_sequence=sequence,
            received_at=NOW + timedelta(seconds=seconds),
            cutoff=NOW + timedelta(seconds=seconds),
            payload={
                "trade_id": "trade-legacy-versions",
                "client_order_id": action.client_order_id,
                "venue_order_ref": "venue-order-versions",
                "last_price": "50000",
                "last_quantity": quantity,
                "order_side": "BUY",
                "liquidity_side": "TAKER",
            },
            **common,
        )

    first_version = version(
        "10000000-0000-0000-0000-000000000034",
        "legacy-a",
        "0.001",
        1,
    )
    matching_version = version(
        "10000000-0000-0000-0000-000000000035",
        "legacy-b",
        "0.002",
        2,
    )
    replay = build_venue_fact(
        venue_fact_id="10000000-0000-0000-0000-000000000036",
        source_class=VenueFactSourceClass.VENUE_QUERY,
        source_sequence="query-random",
        received_at=NOW + timedelta(seconds=3),
        cutoff=NOW + timedelta(seconds=3),
        payload={**matching_version.payload, "reconciliation": True},
        **common,
    )
    assert facts.insert(first_version) is True
    assert facts.insert(matching_version) is True

    applied = service.apply_venue_fact_with_result(
        fact=replay,
        observed_at=replay.received_at,
    )

    assert applied.inserted is False
    assert applied.canonical_fact is matching_version
    assert applied.action is not None
    assert applied.action.venue_fact_refs == (matching_version.venue_fact_id,)


def test_same_economic_trade_cannot_be_reassigned_to_another_action() -> None:
    first_action = _submitting_action()
    second_action = first_action.model_copy(
        update={
            "execution_action_id": "10000000-0000-0000-0000-000000000037",
            "client_order_id": "b" * 32,
        }
    )
    actions = FakeActionRepository((first_action, second_action))
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
    common = {
        "environment_id": first_action.environment_id,
        "venue_ref": BINANCE_USDM_VENUE_REF,
        "account_ref": first_action.account_ref,
        "instrument_ref": "BTCUSDT-PERP",
        "kind": VenueFactKind.FILL,
        "source_object_id": "trade-attribution-conflict",
        "source_time": NOW,
        "payload": {
            "trade_id": "trade-attribution-conflict",
            "client_order_id": first_action.client_order_id,
            "venue_order_ref": "venue-order-attribution",
            "last_price": "50000",
            "last_quantity": "0.001",
            "order_side": "BUY",
            "liquidity_side": "TAKER",
        },
    }
    first = build_venue_fact(
        venue_fact_id="10000000-0000-0000-0000-000000000038",
        source_class=VenueFactSourceClass.VENUE_STREAM,
        source_sequence="stream-event",
        received_at=NOW + timedelta(seconds=1),
        cutoff=NOW + timedelta(seconds=1),
        action=first_action,
        **common,
    )
    reassigned = build_venue_fact(
        venue_fact_id="10000000-0000-0000-0000-000000000039",
        source_class=VenueFactSourceClass.VENUE_QUERY,
        source_sequence="query-event",
        received_at=NOW + timedelta(seconds=2),
        cutoff=NOW + timedelta(seconds=2),
        action=first_action,
        **common,
    ).model_copy(
        update={
            "action_ref": second_action.execution_action_id,
            "attribution_digest": "d" * 64,
        }
    )
    assert venue_trade_fact_id(first) == venue_trade_fact_id(reassigned)
    assert facts.insert(first) is True

    with pytest.raises(ValueError, match="FACT_ATTRIBUTION_CONFLICT"):
        service.apply_venue_fact(
            fact=reassigned,
            observed_at=reassigned.received_at,
        )


def test_affected_reference_metadata_is_not_economic_trade_identity() -> None:
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
    common = {
        "environment_id": action.environment_id,
        "venue_ref": BINANCE_USDM_VENUE_REF,
        "account_ref": action.account_ref,
        "instrument_ref": "BTCUSDT-PERP",
        "kind": VenueFactKind.FILL,
        "source_class": VenueFactSourceClass.VENUE_STREAM,
        "source_object_id": "trade-affected-reference",
        "source_sequence": "stream-event",
        "source_time": NOW,
        "payload": {
            "trade_id": "trade-affected-reference",
            "client_order_id": action.client_order_id,
            "venue_order_ref": "venue-order-affected-reference",
            "last_price": "50000",
            "last_quantity": "0.001",
            "order_side": "BUY",
            "liquidity_side": "TAKER",
        },
        "action": action,
    }
    original = build_venue_fact(
        venue_fact_id="10000000-0000-0000-0000-000000000041",
        received_at=NOW + timedelta(seconds=1),
        cutoff=NOW + timedelta(seconds=1),
        **common,
    )
    annotated_replay = build_venue_fact(
        venue_fact_id="10000000-0000-0000-0000-000000000042",
        received_at=NOW + timedelta(seconds=1),
        cutoff=NOW + timedelta(seconds=1),
        affected_reference_refs=(action.activation_id,),
        **common,
    )

    assert venue_trade_fact_is_canonicalizable(original) is True
    assert venue_trade_fact_is_canonicalizable(annotated_replay) is False
    assert original.content_digest == annotated_replay.content_digest
    service.apply_venue_fact(fact=original, observed_at=original.received_at)

    with pytest.raises(ValueError, match="FACT_CONFLICT"):
        service.apply_venue_fact(
            fact=annotated_replay,
            observed_at=annotated_replay.received_at,
        )


@pytest.mark.parametrize("payload_client_order_id", (None, "b" * 32))
def test_trade_attribution_requires_matching_payload_client_order_identity(
    payload_client_order_id: str | None,
) -> None:
    action = _submitting_action()

    with pytest.raises(ValueError, match="VENUE_FACT_ATTRIBUTION_INVALID"):
        build_venue_fact(
            venue_fact_id="10000000-0000-0000-0000-000000000043",
            environment_id=action.environment_id,
            venue_ref=BINANCE_USDM_VENUE_REF,
            account_ref=action.account_ref,
            instrument_ref="BTCUSDT-PERP",
            kind=VenueFactKind.FILL,
            source_class=VenueFactSourceClass.VENUE_STREAM,
            source_object_id="trade-wrong-client-order",
            source_sequence="stream-event",
            source_time=NOW,
            received_at=NOW + timedelta(seconds=1),
            cutoff=NOW + timedelta(seconds=1),
            payload={
                "trade_id": "trade-wrong-client-order",
                "client_order_id": payload_client_order_id,
                "venue_order_ref": "venue-order-wrong-client-order",
                "last_price": "50000",
                "last_quantity": "0.001",
                "order_side": "BUY",
                "liquidity_side": "TAKER",
            },
            action=action,
        )


def test_application_rechecks_trade_identity_against_the_locked_action() -> None:
    first_action = _submitting_action()
    second_action = first_action.model_copy(
        update={
            "execution_action_id": "10000000-0000-0000-0000-000000000044",
            "client_order_id": "b" * 32,
        }
    )
    fact = build_venue_fact(
        venue_fact_id="10000000-0000-0000-0000-000000000045",
        environment_id=first_action.environment_id,
        venue_ref=BINANCE_USDM_VENUE_REF,
        account_ref=first_action.account_ref,
        instrument_ref="BTCUSDT-PERP",
        kind=VenueFactKind.FILL,
        source_class=VenueFactSourceClass.VENUE_STREAM,
        source_object_id="trade-locked-action-identity",
        source_sequence="stream-event",
        source_time=NOW,
        received_at=NOW + timedelta(seconds=1),
        cutoff=NOW + timedelta(seconds=1),
        payload={
            "trade_id": "trade-locked-action-identity",
            "client_order_id": first_action.client_order_id,
            "venue_order_ref": "venue-order-locked-action-identity",
            "last_price": "50000",
            "last_quantity": "0.001",
            "order_side": "BUY",
            "liquidity_side": "TAKER",
        },
        action=first_action,
    ).model_copy(
        update={
            "action_ref": second_action.execution_action_id,
            "attribution_digest": "d" * 64,
        }
    )
    actions = FakeActionRepository((first_action, second_action))
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

    with pytest.raises(ValueError, match="VENUE_FACT_ATTRIBUTION_INVALID"):
        service.apply_venue_fact(fact=fact, observed_at=fact.received_at)

    assert actions.actions[first_action.execution_action_id] is first_action
    assert actions.actions[second_action.execution_action_id] is second_action


def test_concurrent_trade_attribution_loser_reads_winner_and_fails_closed() -> None:
    first_action = _submitting_action()
    second_action = first_action.model_copy(
        update={
            "execution_action_id": "10000000-0000-0000-0000-000000000043",
            "client_order_id": "b" * 32,
        }
    )
    actions = FakeActionRepository((first_action, second_action))
    common = {
        "environment_id": first_action.environment_id,
        "venue_ref": BINANCE_USDM_VENUE_REF,
        "account_ref": first_action.account_ref,
        "instrument_ref": "BTCUSDT-PERP",
        "kind": VenueFactKind.FILL,
        "source_object_id": "trade-concurrent-attribution",
        "source_time": NOW,
        "payload": {
            "trade_id": "trade-concurrent-attribution",
            "client_order_id": first_action.client_order_id,
            "venue_order_ref": "venue-order-concurrent-attribution",
            "last_price": "50000",
            "last_quantity": "0.001",
            "order_side": "BUY",
            "liquidity_side": "TAKER",
        },
    }
    winner = build_venue_fact(
        venue_fact_id="placeholder-winner",
        source_class=VenueFactSourceClass.VENUE_STREAM,
        source_sequence="stream-event",
        received_at=NOW + timedelta(seconds=1),
        cutoff=NOW + timedelta(seconds=1),
        action=first_action,
        **common,
    )
    loser = build_venue_fact(
        venue_fact_id="placeholder-loser",
        source_class=VenueFactSourceClass.VENUE_QUERY,
        source_sequence="query-event",
        received_at=NOW + timedelta(seconds=2),
        cutoff=NOW + timedelta(seconds=2),
        action=first_action,
        **common,
    ).model_copy(
        update={
            "action_ref": second_action.execution_action_id,
            "attribution_digest": "d" * 64,
        }
    )
    economic_id = venue_trade_fact_id(winner)
    winner = winner.model_copy(update={"venue_fact_id": economic_id})
    loser = loser.model_copy(update={"venue_fact_id": economic_id})

    class ConcurrentWinnerRepository(FakeFactRepository):
        def insert(self, fact):
            assert fact is loser
            assert not self.facts
            self.facts[winner.venue_fact_id] = winner
            return False

    facts = ConcurrentWinnerRepository()
    service = ExecutionApplicationService(
        actions,  # type: ignore[arg-type]
        facts,  # type: ignore[arg-type]
        environment_id="demo-main",
        environment_kind="DEMO",
        authority_class="DEMO_VALIDATION",
        execution_profile_ref="BINANCE_DEMO",
        account_ref="demo-owner",
    )

    with pytest.raises(ValueError, match="FACT_ATTRIBUTION_CONFLICT"):
        service.apply_venue_fact(
            fact=loser,
            observed_at=loser.received_at,
        )

    assert facts.facts == {winner.venue_fact_id: winner}
    assert actions.actions[first_action.execution_action_id] is first_action
    assert actions.actions[second_action.execution_action_id] is second_action
