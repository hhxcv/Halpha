from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from halpha.capital.models import CapDecision, RiskClass
from halpha.domain_values import content_digest
from halpha.planning.models import (
    PlanEvent,
    ProposedAction,
    ProposedActionKind,
)
from halpha.planning.registry import Direction
from halpha.venue_integration.facts import build_venue_fact
from halpha.venue_integration.models import (
    ExecutionActionState,
    VenueFactKind,
    VenueFactSourceClass,
)
from halpha.venue_integration.transitions import (
    ExecutionActionConflict,
    apply_venue_outcome,
    begin_submission,
    build_execution_action,
    mark_not_submitted,
    mark_submission_unknown,
    reconcile_action,
    resolve_existing_action,
)


NOW = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)


def _proposed(
    *,
    kind: ProposedActionKind = ProposedActionKind.ENTRY,
    profile: str = "ENTRY_MARKET",
    order_type: str = "MARKET",
    reduce_only: bool = False,
    quantity: str | None = "0.001",
    cancel_target: dict[str, str] | None = None,
    price: str | None = None,
    trigger_price: str | None = None,
) -> ProposedAction:
    return ProposedAction(
        environment_id="demo-main",
        action_kind=kind,
        action_profile=profile,
        instrument_ref="BTCUSDT-PERP",
        direction=Direction.LONG,
        quantity=quantity,
        close_position=False,
        order_type=order_type,
        price=price,
        trigger_price=trigger_price,
        reduce_only=reduce_only,
        source_responsibility=(
            "HALPHA_MONITORED" if kind is ProposedActionKind.ENTRY else "NONE"
        ),
        causation_ref="a" * 64,
        cancel_target=cancel_target,
    )


def _event(proposed: ProposedAction | None = None) -> PlanEvent:
    proposed = proposed or _proposed()
    capital = {
        "accepted": True,
        "reason_code": "ACCEPTED_RISK_INCREASING",
        "risk_class": (
            "RISK_INCREASING"
            if proposed.action_kind is ProposedActionKind.ENTRY
            else (
                "RISK_NEUTRAL"
                if proposed.action_kind is ProposedActionKind.CANCEL
                else "RISK_REDUCING"
            )
        ),
    }
    fields = {
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
    return PlanEvent(**fields, content_digest=content_digest(fields))


def _action(proposed: ProposedAction | None = None):
    return build_execution_action(
        execution_action_id="10000000-0000-0000-0000-000000000003",
        plan_event=_event(proposed),
        environment_kind="DEMO",
        authority_class="DEMO_VALIDATION",
        execution_profile_ref="BINANCE_DEMO",
        account_ref="demo-owner",
        observed_at=NOW,
        client_order_id="0123456789abcdef0123456789abcdef",
    )


def _cap_decision(risk_class: RiskClass) -> CapDecision:
    fields = {
        "accepted": True,
        "reason_code": f"ACCEPTED_{risk_class.value}",
        "risk_class": risk_class,
        "effective_leverage": "5" if risk_class is RiskClass.RISK_INCREASING else None,
        "action_notional": "100",
        "economic_action_notional": "100",
        "activation_notional_after": "100",
        "account_notional_after": "100",
        "activation_margin_after": "20",
        "stopped_categories": (),
        "input_digest": "c" * 64,
    }
    return CapDecision(**fields, decision_digest=content_digest(fields))


def test_demo_and_live_use_one_action_model_with_fixed_environment_identity() -> None:
    demo = _action()
    live_event = _event().model_copy(
        update={
            "environment_id": "live-main",
            "proposed_action": _proposed().model_copy(
                update={"environment_id": "live-main"}
            ),
        }
    )
    live = build_execution_action(
        execution_action_id="10000000-0000-0000-0000-000000000004",
        plan_event=live_event,
        environment_kind="LIVE",
        authority_class="LIVE_REAL_CAPITAL",
        execution_profile_ref="BINANCE_LIVE_WRITE",
        account_ref="live-owner",
        observed_at=NOW,
        client_order_id="fedcba9876543210fedcba9876543210",
    )
    assert type(demo) is type(live)
    assert demo.state is live.state is ExecutionActionState.READY
    assert demo.execution_profile_ref.value == "BINANCE_DEMO"
    assert live.execution_profile_ref.value == "BINANCE_LIVE_WRITE"

    with pytest.raises(ValueError, match="EXECUTION_PROFILE_MISMATCH"):
        build_execution_action(
            execution_action_id="10000000-0000-0000-0000-000000000005",
            plan_event=_event(),
            environment_kind="DEMO",
            authority_class="DEMO_VALIDATION",
            execution_profile_ref="BINANCE_LIVE_WRITE",
            account_ref="demo-owner",
            observed_at=NOW,
        )


def test_all_selected_profiles_normalize_without_demo_specific_action_types() -> None:
    cases = (
        (_proposed(), "ENTRY"),
        (
            _proposed(
                kind=ProposedActionKind.ENTRY,
                profile="ENTRY_LIMIT",
                order_type="LIMIT",
                price="50000",
            ),
            "ENTRY",
        ),
        (
            _proposed(
                kind=ProposedActionKind.ENTRY,
                profile="ENTRY_STOP_MARKET",
                order_type="STOP_MARKET",
                trigger_price="60000",
            ),
            "ENTRY",
        ),
        (
            _proposed(
                kind=ProposedActionKind.CANCEL,
                profile="CANCEL_ORDER",
                order_type="CANCEL",
                quantity=None,
                cancel_target={"client_order_id": "0" * 32, "endpoint": "ALGO"},
            ),
            "CANCEL",
        ),
        (
            _proposed(
                kind=ProposedActionKind.PROTECTION,
                profile="PROTECTIVE_STOP_REDUCE_ONLY",
                order_type="STOP_MARKET",
                reduce_only=True,
                trigger_price="40000",
            ),
            "PROTECTION",
        ),
        (
            _proposed(
                kind=ProposedActionKind.TAKE_PROFIT,
                profile="TAKE_PROFIT_1",
                order_type="MARKET_IF_TOUCHED",
                reduce_only=True,
                trigger_price="65000",
            ),
            "TAKE_PROFIT",
        ),
        (
            _proposed(
                kind=ProposedActionKind.TAKE_PROFIT,
                profile="TAKE_PROFIT_2",
                order_type="MARKET_IF_TOUCHED",
                reduce_only=True,
                trigger_price="70000",
            ),
            "TAKE_PROFIT",
        ),
        (
            _proposed(
                kind=ProposedActionKind.EXIT,
                profile="REDUCE_OR_CLOSE_MARKET",
                order_type="MARKET",
                reduce_only=True,
            ),
            "EXIT",
        ),
    )
    assert tuple(_action(item).action_kind.value for item, _ in cases) == tuple(
        expected for _, expected in cases
    )


def test_source_replay_returns_original_and_different_terms_conflict() -> None:
    event = _event()
    action = _action()
    assert resolve_existing_action(action, plan_event=event) is action
    conflict = event.model_copy(
        update={
            "proposed_action": event.proposed_action.model_copy(
                update={"causation_ref": "d" * 64}
            )
        }
    )
    with pytest.raises(ExecutionActionConflict, match="DUPLICATE_IDENTITY_CONFLICT"):
        resolve_existing_action(action, plan_event=conflict)


def test_submitting_crash_becomes_query_only_unknown_and_never_returns_ready() -> None:
    action = _action()
    submitting = begin_submission(
        action,
        capital_decision=_cap_decision(RiskClass.RISK_INCREASING),
        request_payload={"order_type": "MARKET", "quantity": "0.001"},
        observed_at=NOW + timedelta(seconds=1),
    )
    assert submitting.state is ExecutionActionState.SUBMITTING
    assert submitting.request_digest is not None
    with pytest.raises(ExecutionActionConflict, match="PREDECESSOR_OPEN"):
        begin_submission(
            submitting,
            capital_decision=_cap_decision(RiskClass.RISK_INCREASING),
            request_payload={},
            observed_at=NOW + timedelta(seconds=2),
        )
    unknown = mark_submission_unknown(
        submitting,
        reason="WRITE_TIMEOUT",
        next_query_at=NOW + timedelta(seconds=10),
        observed_at=NOW + timedelta(seconds=2),
    )
    assert unknown.state is ExecutionActionState.SUBMITTED_UNKNOWN
    assert mark_submission_unknown(
        unknown,
        reason="IGNORED_REPLAY",
        next_query_at=NOW + timedelta(seconds=20),
        observed_at=NOW + timedelta(seconds=3),
    ) is unknown
    definitely_absent = mark_not_submitted(
        unknown,
        observed_at=NOW + timedelta(seconds=4),
    )
    assert definitely_absent.state is ExecutionActionState.NOT_SUBMITTED
    assert definitely_absent.request_digest == unknown.request_digest


def test_authoritative_fact_advances_original_action_and_reconciliation_needs_closure() -> None:
    submitting = begin_submission(
        _action(),
        capital_decision=_cap_decision(RiskClass.RISK_INCREASING),
        request_payload={"order_type": "MARKET"},
        observed_at=NOW + timedelta(seconds=1),
    )
    fact = build_venue_fact(
        venue_fact_id="10000000-0000-0000-0000-000000000006",
        environment_id="demo-main",
        venue_ref="BINANCE",
        account_ref="demo-owner",
        instrument_ref="BTCUSDT-PERP",
        kind=VenueFactKind.ORDER_STATE,
        source_class=VenueFactSourceClass.VENUE_QUERY,
        source_object_id=submitting.client_order_id or "",
        source_sequence="1",
        source_time=NOW + timedelta(seconds=2),
        received_at=NOW + timedelta(seconds=2),
        cutoff=NOW + timedelta(seconds=2),
        payload={"status": "FILLED", "venue_order_ref": "12345"},
        action=submitting,
    )
    filled = apply_venue_outcome(
        submitting,
        target=ExecutionActionState.FILLED,
        venue_order_refs=("12345",),
        venue_fact_refs=(fact.venue_fact_id,),
        observed_at=NOW + timedelta(seconds=2),
    )
    reconciled = reconcile_action(
        filled,
        closure_evidence={
            "order_terminal": True,
            "fills_complete": True,
            "fees_complete": True,
            "position_effect_known": True,
        },
        venue_fact_refs=(fact.venue_fact_id,),
        observed_at=NOW + timedelta(seconds=3),
    )
    assert reconciled.state is ExecutionActionState.RECONCILED
    assert reconciled.closure_evidence_digest is not None

    with pytest.raises(ValueError, match="VENUE_FACT_ATTRIBUTION_INVALID"):
        build_venue_fact(
            venue_fact_id="10000000-0000-0000-0000-000000000007",
            environment_id="live-main",
            venue_ref="BINANCE",
            account_ref="demo-owner",
            instrument_ref="BTCUSDT-PERP",
            kind=VenueFactKind.ORDER_STATE,
            source_class=VenueFactSourceClass.VENUE_QUERY,
            source_object_id="12345",
            source_sequence="2",
            source_time=NOW,
            received_at=NOW,
            cutoff=NOW,
            payload={"status": "FILLED"},
            action=submitting,
        )
