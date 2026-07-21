"""Pure EXE identity and state transitions shared by Demo and Live."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from halpha.capital.models import CapDecision, RiskClass
from halpha.domain_values import content_digest
from halpha.planning.models import PlanEvent, ProposedAction, ProposedActionKind
from halpha.venue_integration.models import (
    ExecutionAction,
    ExecutionActionKind,
    ExecutionActionState,
    ExecutionProfileRef,
    execution_action_state_digest,
)


class ExecutionActionConflict(ValueError):
    pass


_PROFILE_SHAPES: dict[str, tuple[frozenset[ExecutionActionKind], str, bool]] = {
    "ENTRY_MARKET": (frozenset({ExecutionActionKind.ENTRY}), "MARKET", False),
    "ENTRY_LIMIT": (frozenset({ExecutionActionKind.ENTRY}), "LIMIT", False),
    "ENTRY_STOP_MARKET": (
        frozenset({ExecutionActionKind.ENTRY}),
        "STOP_MARKET",
        False,
    ),
    "CANCEL_ORDER": (frozenset({ExecutionActionKind.CANCEL}), "CANCEL", False),
    "PROTECTIVE_STOP_REDUCE_ONLY": (
        frozenset({ExecutionActionKind.PROTECTION}),
        "STOP_MARKET",
        True,
    ),
    "TAKE_PROFIT_1": (
        frozenset({ExecutionActionKind.TAKE_PROFIT}),
        "MARKET_IF_TOUCHED",
        True,
    ),
    "TAKE_PROFIT_2": (
        frozenset({ExecutionActionKind.TAKE_PROFIT}),
        "MARKET_IF_TOUCHED",
        True,
    ),
    "REDUCE_OR_CLOSE_MARKET": (
        frozenset({ExecutionActionKind.RISK_REDUCTION, ExecutionActionKind.EXIT}),
        "MARKET",
        True,
    ),
}


_ALLOWED_TRANSITIONS: dict[ExecutionActionState, frozenset[ExecutionActionState]] = {
    ExecutionActionState.READY: frozenset(
        {
            ExecutionActionState.NOT_SUBMITTED,
            ExecutionActionState.SUBMITTING,
            ExecutionActionState.HANDED_OVER,
        }
    ),
    ExecutionActionState.SUBMITTING: frozenset(
        {
            ExecutionActionState.NOT_SUBMITTED,
            ExecutionActionState.UNKNOWN,
            ExecutionActionState.OPEN,
        }
    ),
    ExecutionActionState.UNKNOWN: frozenset(
        {
            ExecutionActionState.NOT_SUBMITTED,
            ExecutionActionState.OPEN,
        }
    ),
    ExecutionActionState.OPEN: frozenset({ExecutionActionState.CLOSED}),
    ExecutionActionState.NOT_SUBMITTED: frozenset(),
    ExecutionActionState.CLOSED: frozenset(),
    ExecutionActionState.HANDED_OVER: frozenset(),
}


def expected_profile(environment_kind: str) -> ExecutionProfileRef:
    if environment_kind == "DEMO":
        return ExecutionProfileRef.BINANCE_DEMO
    if environment_kind == "LIVE":
        return ExecutionProfileRef.BINANCE_LIVE_WRITE
    raise ValueError("EXECUTION_PROFILE_MISMATCH")


def _normalize_action_shape(proposed: ProposedAction) -> tuple[ExecutionActionKind, RiskClass]:
    selected = _PROFILE_SHAPES.get(proposed.action_profile)
    if selected is None:
        raise ValueError("ACTION_PROFILE_UNQUALIFIED")
    expected_kinds, expected_order_type, expected_reduce_only = selected
    action_kind = ExecutionActionKind(proposed.action_kind.value)
    if (
        action_kind not in expected_kinds
        or expected_order_type != proposed.order_type
        or expected_reduce_only is not proposed.reduce_only
    ):
        raise ValueError("ACTION_PROFILE_MISMATCH")
    if proposed.source_responsibility not in {"HALPHA_MONITORED", "VENUE_MONITORED", "NONE"}:
        raise ValueError("ACTION_PROFILE_MISMATCH")
    if proposed.action_profile == "ENTRY_LIMIT" and proposed.price is None:
        raise ValueError("ACTION_PROFILE_MISMATCH")
    if proposed.action_profile in {
        "ENTRY_STOP_MARKET",
        "PROTECTIVE_STOP_REDUCE_ONLY",
        "TAKE_PROFIT_1",
        "TAKE_PROFIT_2",
    } and proposed.trigger_price is None:
        raise ValueError("ACTION_PROFILE_MISMATCH")
    if proposed.action_profile in {
        "ENTRY_MARKET",
        "REDUCE_OR_CLOSE_MARKET",
        "CANCEL_ORDER",
    } and (proposed.price is not None or proposed.trigger_price is not None):
        raise ValueError("ACTION_PROFILE_MISMATCH")
    if proposed.close_position:
        raise ValueError("CLOSE_POSITION_UNQUALIFIED")
    if proposed.action_kind is ProposedActionKind.ENTRY:
        risk_class = RiskClass.RISK_INCREASING
    elif proposed.action_kind is ProposedActionKind.CANCEL:
        risk_class = RiskClass.RISK_NEUTRAL
    else:
        risk_class = RiskClass.RISK_REDUCING
    return action_kind, risk_class


def build_execution_action(
    *,
    execution_action_id: str,
    plan_event: PlanEvent,
    environment_kind: str,
    authority_class: str,
    execution_profile_ref: str,
    account_ref: str,
    observed_at: datetime,
    client_order_id: str | None = None,
) -> ExecutionAction:
    """Create one READY action only for a CAP-accepted immutable PlanEvent."""

    proposed = plan_event.proposed_action
    if proposed is None or plan_event.no_action_reason is not None:
        raise ValueError("CAP_REJECTED")
    if not bool(plan_event.capital_decision.get("accepted")):
        raise ValueError("CAP_REJECTED")
    if plan_event.capital_decision_digest != content_digest(plan_event.capital_decision):
        raise ExecutionActionConflict("DUPLICATE_IDENTITY_CONFLICT")
    if proposed.environment_id != plan_event.environment_id:
        raise ValueError("AUTHORIZATION_MISMATCH")
    action_kind, action_class = _normalize_action_shape(proposed)
    profile = expected_profile(environment_kind)
    if profile.value != execution_profile_ref:
        raise ValueError("EXECUTION_PROFILE_MISMATCH")
    if action_kind is ExecutionActionKind.CANCEL:
        stable_client_order_id = None
    else:
        stable_client_order_id = client_order_id or uuid4().hex
    action_terms = {
        "account_ref": account_ref,
        "instrument_ref": proposed.instrument_ref,
        "direction": proposed.direction.value,
        "action_profile": proposed.action_profile,
        "order_type": proposed.order_type,
        "quantity": proposed.quantity,
        "close_position": proposed.close_position,
        "price": proposed.price,
        "trigger_price": proposed.trigger_price,
        "valid_until": (
            proposed.valid_until.isoformat() if proposed.valid_until is not None else None
        ),
        "reduce_only": proposed.reduce_only,
        "source_responsibility": proposed.source_responsibility,
        "causation_ref": proposed.causation_ref,
        "execution_context": proposed.execution_context,
        "creation_capital_decision_digest": plan_event.capital_decision_digest,
    }
    fields: dict[str, Any] = {
        "execution_action_id": execution_action_id,
        "environment_id": plan_event.environment_id,
        "environment_kind": environment_kind,
        "authority_class": authority_class,
        "execution_profile_ref": execution_profile_ref,
        "account_ref": account_ref,
        "activation_id": plan_event.activation_id,
        "plan_event_ref": plan_event.plan_event_id,
        "source_identity": plan_event.source_identity,
        "action_kind": action_kind,
        "action_class": action_class,
        "action_terms": action_terms,
        "action_terms_digest": content_digest(action_terms),
        "capital_decision_digest": plan_event.capital_decision_digest,
        "client_order_id": stable_client_order_id,
        "cancel_target": proposed.cancel_target,
        "state": ExecutionActionState.READY,
        "state_version": 1,
        "request_digest": None,
        "call_started_at": None,
        "call_completed_at": None,
        "venue_order_refs": (),
        "venue_fact_refs": (),
        "unknown_reason": None,
        "next_query_at": None,
        "not_submitted_reason": None,
        "protection_digest": (
            content_digest(action_terms)
            if action_kind is ExecutionActionKind.PROTECTION
            else None
        ),
        "closure_evidence_digest": None,
        "created_at": observed_at,
        "updated_at": observed_at,
    }
    fields["state_digest"] = execution_action_state_digest(fields)
    return ExecutionAction(**fields)


def resolve_existing_action(
    existing: ExecutionAction | None,
    *,
    plan_event: PlanEvent,
) -> ExecutionAction | None:
    if existing is None:
        return None
    proposed = plan_event.proposed_action
    if proposed is None:
        raise ExecutionActionConflict("DUPLICATE_IDENTITY_CONFLICT")
    if (
        existing.plan_event_ref != plan_event.plan_event_id
        or existing.source_identity != plan_event.source_identity
        or existing.action_kind.value != proposed.action_kind.value
        or existing.action_terms.get("causation_ref") != proposed.causation_ref
        or existing.action_terms.get("creation_capital_decision_digest")
        != plan_event.capital_decision_digest
    ):
        raise ExecutionActionConflict("DUPLICATE_IDENTITY_CONFLICT")
    return existing


def _transition(
    action: ExecutionAction,
    *,
    target: ExecutionActionState,
    observed_at: datetime,
    updates: dict[str, Any] | None = None,
) -> ExecutionAction:
    if target not in _ALLOWED_TRANSITIONS[action.state]:
        raise ExecutionActionConflict("EXECUTION_ACTION_TRANSITION_INVALID")
    values = action.model_dump(mode="python", exclude={"state_digest"})
    values.update(updates or {})
    values.update(
        {
            "state": target,
            "state_version": action.state_version + 1,
            "updated_at": observed_at,
        }
    )
    values["state_digest"] = execution_action_state_digest(values)
    return ExecutionAction(**values)


def begin_submission(
    action: ExecutionAction,
    *,
    capital_decision: CapDecision,
    request_payload: dict[str, Any],
    observed_at: datetime,
) -> ExecutionAction:
    if action.state is not ExecutionActionState.READY:
        raise ExecutionActionConflict("PREDECESSOR_OPEN")
    if not capital_decision.accepted or capital_decision.risk_class is not action.action_class:
        raise ValueError("CAP_REJECTED")
    request_digest = content_digest(
        {
            "execution_action_id": action.execution_action_id,
            "environment_id": action.environment_id,
            "activation_id": action.activation_id,
            "client_order_id": action.client_order_id,
            "cancel_target": action.cancel_target,
            "action_terms_digest": action.action_terms_digest,
            "capital_decision_digest": capital_decision.decision_digest,
            "request": request_payload,
        }
    )
    return _transition(
        action,
        target=ExecutionActionState.SUBMITTING,
        observed_at=observed_at,
        updates={
            "capital_decision_digest": capital_decision.decision_digest,
            "request_digest": request_digest,
            "call_started_at": observed_at,
        },
    )


def mark_not_submitted(
    action: ExecutionAction,
    *,
    reason_code: str,
    observed_at: datetime,
) -> ExecutionAction:
    if not reason_code or len(reason_code) > 160:
        raise ValueError("NOT_SUBMITTED_REASON_INVALID")
    return _transition(
        action,
        target=ExecutionActionState.NOT_SUBMITTED,
        observed_at=observed_at,
        updates={
            "unknown_reason": None,
            "next_query_at": None,
            "not_submitted_reason": reason_code,
            "call_completed_at": (
                observed_at if action.call_started_at is not None else None
            ),
        },
    )


def mark_submission_unknown(
    action: ExecutionAction,
    *,
    reason: str,
    next_query_at: datetime,
    observed_at: datetime,
) -> ExecutionAction:
    if action.state is ExecutionActionState.UNKNOWN:
        return action
    return _transition(
        action,
        target=ExecutionActionState.UNKNOWN,
        observed_at=observed_at,
        updates={"unknown_reason": reason, "next_query_at": next_query_at},
    )


def defer_unknown_query(
    action: ExecutionAction,
    *,
    next_query_at: datetime,
    observed_at: datetime,
) -> ExecutionAction:
    """Rate-limit another query without changing the unresolved responsibility."""

    if action.state is not ExecutionActionState.UNKNOWN:
        raise ExecutionActionConflict("EXECUTION_ACTION_TRANSITION_INVALID")
    values = action.model_dump(mode="python", exclude={"state_digest"})
    values.update(
        {
            "next_query_at": next_query_at,
            "state_version": action.state_version + 1,
            "updated_at": observed_at,
        }
    )
    values["state_digest"] = execution_action_state_digest(values)
    return ExecutionAction(**values)


def mark_action_open(
    action: ExecutionAction,
    *,
    venue_order_refs: tuple[str, ...],
    venue_fact_refs: tuple[str, ...],
    observed_at: datetime,
) -> ExecutionAction:
    return _transition(
        action,
        target=ExecutionActionState.OPEN,
        observed_at=observed_at,
        updates={
            "call_completed_at": observed_at,
            "venue_order_refs": tuple(dict.fromkeys((*action.venue_order_refs, *venue_order_refs))),
            "venue_fact_refs": tuple(dict.fromkeys((*action.venue_fact_refs, *venue_fact_refs))),
            "unknown_reason": None,
            "next_query_at": None,
        },
    )


def absorb_venue_observation(
    action: ExecutionAction,
    *,
    venue_order_refs: tuple[str, ...],
    venue_fact_refs: tuple[str, ...],
    observed_at: datetime,
) -> ExecutionAction:
    """Retain an attributed fact without changing the current monotonic state."""

    merged_order_refs = tuple(
        dict.fromkeys((*action.venue_order_refs, *venue_order_refs))
    )
    merged_fact_refs = tuple(
        dict.fromkeys((*action.venue_fact_refs, *venue_fact_refs))
    )
    if (
        merged_order_refs == action.venue_order_refs
        and merged_fact_refs == action.venue_fact_refs
    ):
        return action
    values = action.model_dump(mode="python", exclude={"state_digest"})
    values.update(
        {
            "state_version": action.state_version + 1,
            "updated_at": observed_at,
            "call_completed_at": observed_at,
            "venue_order_refs": merged_order_refs,
            "venue_fact_refs": merged_fact_refs,
        }
    )
    values["state_digest"] = execution_action_state_digest(values)
    return ExecutionAction(**values)


def reconcile_action(
    action: ExecutionAction,
    *,
    closure_evidence: dict[str, Any],
    venue_fact_refs: tuple[str, ...],
    observed_at: datetime,
) -> ExecutionAction:
    if action.state is not ExecutionActionState.OPEN:
        raise ValueError("CLOSURE_UNPROVEN")
    closure_digest = content_digest(
        {
            "execution_action_id": action.execution_action_id,
            "state": action.state,
            "request_digest": action.request_digest,
            "venue_order_refs": action.venue_order_refs,
            "venue_fact_refs": tuple(
                dict.fromkeys((*action.venue_fact_refs, *venue_fact_refs))
            ),
            "evidence": closure_evidence,
        }
    )
    return _transition(
        action,
        target=ExecutionActionState.CLOSED,
        observed_at=observed_at,
        updates={
            "closure_evidence_digest": closure_digest,
            "venue_fact_refs": tuple(
                dict.fromkeys((*action.venue_fact_refs, *venue_fact_refs))
            ),
        },
    )


def hand_over_ready_action(
    action: ExecutionAction,
    *,
    observed_at: datetime,
) -> ExecutionAction:
    return _transition(
        action,
        target=ExecutionActionState.HANDED_OVER,
        observed_at=observed_at,
    )
