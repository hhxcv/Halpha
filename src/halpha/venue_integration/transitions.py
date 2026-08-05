"""Pure EXE identity and state transitions shared by Demo and Live."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from halpha.capital.models import CapDecision, RiskClass
from halpha.domain_values import content_digest
from halpha.planning.models import PlanEvent, ProposedAction
from halpha.venue_integration.models import (
    ExecutionAction,
    ExecutionActionKind,
    ExecutionActionState,
    ExecutionProfileRef,
    ExitResponsibilityRole,
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
            ExecutionActionState.HANDED_OVER,
        }
    ),
    ExecutionActionState.UNKNOWN: frozenset(
        {
            ExecutionActionState.NOT_SUBMITTED,
            ExecutionActionState.OPEN,
            ExecutionActionState.HANDED_OVER,
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


def _validate_profile_shape(
    *,
    action_profile: object,
    action_kind: ExecutionActionKind,
    order_type: object,
    reduce_only: object,
    source_responsibility: object,
    price: object,
    trigger_price: object,
    close_position: object,
) -> RiskClass:
    selected = (
        _PROFILE_SHAPES.get(action_profile)
        if isinstance(action_profile, str)
        else None
    )
    if selected is None:
        raise ValueError("ACTION_PROFILE_UNQUALIFIED")
    expected_kinds, expected_order_type, expected_reduce_only = selected
    if (
        action_kind not in expected_kinds
        or expected_order_type != order_type
        or type(reduce_only) is not bool
        or expected_reduce_only is not reduce_only
    ):
        raise ValueError("ACTION_PROFILE_MISMATCH")
    if source_responsibility not in {
        "HALPHA_MONITORED",
        "VENUE_MONITORED",
        "NONE",
    }:
        raise ValueError("ACTION_PROFILE_MISMATCH")
    if action_profile == "ENTRY_LIMIT" and (
        price is None or trigger_price is not None
    ):
        raise ValueError("ACTION_PROFILE_MISMATCH")
    if action_profile in {
        "ENTRY_STOP_MARKET",
        "PROTECTIVE_STOP_REDUCE_ONLY",
        "TAKE_PROFIT_1",
        "TAKE_PROFIT_2",
    } and (trigger_price is None or price is not None):
        raise ValueError("ACTION_PROFILE_MISMATCH")
    if action_profile in {
        "ENTRY_MARKET",
        "REDUCE_OR_CLOSE_MARKET",
        "CANCEL_ORDER",
    } and (price is not None or trigger_price is not None):
        raise ValueError("ACTION_PROFILE_MISMATCH")
    if close_position is not False:
        raise ValueError("CLOSE_POSITION_UNQUALIFIED")
    if action_kind is ExecutionActionKind.ENTRY:
        return RiskClass.RISK_INCREASING
    if action_kind is ExecutionActionKind.CANCEL:
        return RiskClass.RISK_NEUTRAL
    return RiskClass.RISK_REDUCING


def _normalize_action_shape(
    proposed: ProposedAction,
) -> tuple[ExecutionActionKind, RiskClass]:
    action_kind = ExecutionActionKind(proposed.action_kind.value)
    risk_class = _validate_profile_shape(
        action_profile=proposed.action_profile,
        action_kind=action_kind,
        order_type=proposed.order_type,
        reduce_only=proposed.reduce_only,
        source_responsibility=proposed.source_responsibility,
        price=proposed.price,
        trigger_price=proposed.trigger_price,
        close_position=proposed.close_position,
    )
    return action_kind, risk_class


def validate_execution_action_shape(action: ExecutionAction) -> None:
    """Recheck persisted economic shape immediately before any venue mutation."""

    terms = action.action_terms
    risk_class = _validate_profile_shape(
        action_profile=terms.get("action_profile"),
        action_kind=action.action_kind,
        order_type=terms.get("order_type"),
        reduce_only=terms.get("reduce_only"),
        source_responsibility=terms.get("source_responsibility"),
        price=terms.get("price"),
        trigger_price=terms.get("trigger_price"),
        close_position=terms.get("close_position"),
    )
    if action.action_class is not risk_class:
        raise ValueError("ACTION_PROFILE_MISMATCH")
    position_side = terms.get("position_side")
    if terms.get("action_profile") == "REDUCE_OR_CLOSE_MARKET":
        if position_side not in {"BOTH", "LONG", "SHORT"}:
            raise ValueError("ACTION_POSITION_SIDE_INVALID")
    elif position_side is not None:
        raise ValueError("ACTION_POSITION_SIDE_INVALID")
    if (
        terms.get("account_ref") != action.account_ref
        or not isinstance(terms.get("instrument_ref"), str)
        or terms.get("direction") not in {"LONG", "SHORT"}
    ):
        raise ValueError("ACTION_PROFILE_MISMATCH")
    exit_role = terms.get("exit_responsibility_role")
    if action.action_kind is ExecutionActionKind.EXIT:
        try:
            ExitResponsibilityRole(exit_role)
        except (TypeError, ValueError):
            raise ValueError("EXIT_RESPONSIBILITY_ROLE_INVALID") from None
    elif exit_role is not None:
        raise ValueError("EXIT_RESPONSIBILITY_ROLE_INVALID")
    quantity = terms.get("quantity")
    if action.action_kind is ExecutionActionKind.CANCEL:
        target = action.cancel_target
        target_client_order_id = (
            target.get("client_order_id")
            if isinstance(target, dict)
            else None
        )
        if (
            quantity is not None
            or not isinstance(target, dict)
            or not isinstance(target_client_order_id, str)
            or len(target_client_order_id) != 32
            or any(
                character not in "0123456789abcdef"
                for character in target_client_order_id
            )
            or target.get("endpoint") not in {"ORDINARY", "ALGO"}
        ):
            raise ValueError("ACTION_PROFILE_MISMATCH")
    else:
        try:
            parsed_quantity = Decimal(quantity) if isinstance(quantity, str) else Decimal(0)
        except InvalidOperation:
            raise ValueError("ACTION_PROFILE_MISMATCH") from None
        if not parsed_quantity.is_finite() or parsed_quantity <= 0:
            raise ValueError("ACTION_PROFILE_MISMATCH")
    for value in (terms.get("price"), terms.get("trigger_price")):
        if value is None:
            continue
        try:
            parsed = Decimal(value) if isinstance(value, str) else Decimal(0)
        except InvalidOperation:
            raise ValueError("ACTION_PROFILE_MISMATCH") from None
        if not parsed.is_finite() or parsed <= 0:
            raise ValueError("ACTION_PROFILE_MISMATCH")


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
    execution_context = dict(proposed.execution_context)
    exit_role = execution_context.pop("exit_responsibility_role", None)
    position_side = execution_context.pop("position_side", None)
    if action_kind is ExecutionActionKind.EXIT:
        try:
            exit_role = ExitResponsibilityRole(exit_role).value
        except (TypeError, ValueError):
            raise ValueError("EXIT_RESPONSIBILITY_ROLE_INVALID") from None
    elif exit_role is not None:
        raise ValueError("EXIT_RESPONSIBILITY_ROLE_INVALID")
    has_position_side = proposed.action_profile == "REDUCE_OR_CLOSE_MARKET"
    if has_position_side:
        if position_side not in {"BOTH", "LONG", "SHORT"}:
            raise ValueError("ACTION_POSITION_SIDE_INVALID")
    elif position_side is not None:
        raise ValueError("ACTION_POSITION_SIDE_INVALID")
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
        "execution_context": execution_context,
        "creation_capital_decision_digest": plan_event.capital_decision_digest,
    }
    if action_kind is ExecutionActionKind.EXIT:
        action_terms["exit_responsibility_role"] = exit_role
    if has_position_side:
        action_terms["position_side"] = position_side
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
    action = ExecutionAction(**fields)
    validate_execution_action_shape(action)
    return action


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
    if existing.action_kind is ExecutionActionKind.EXIT:
        proposed_role = proposed.execution_context.get(
            "exit_responsibility_role"
        )
        try:
            proposed_role = ExitResponsibilityRole(proposed_role).value
        except (TypeError, ValueError):
            raise ExecutionActionConflict(
                "DUPLICATE_IDENTITY_CONFLICT"
            ) from None
        if (
            existing.action_terms.get("exit_responsibility_role")
            != proposed_role
        ):
            raise ExecutionActionConflict("DUPLICATE_IDENTITY_CONFLICT")
    if proposed.action_profile == "REDUCE_OR_CLOSE_MARKET" and (
        existing.action_terms.get("position_side")
        != proposed.execution_context.get("position_side")
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
        current_reason = action.unknown_reason or ""
        initial_async_reason = (
            current_reason.startswith("VENUE_CALL_UNCERTAIN:")
            or current_reason == "EXECUTOR_RESTART_AFTER_SUBMITTING"
        )
        later_venue_diagnosis = reason in {
            "VENUE_SUBMISSION_RESULT_UNKNOWN",
            "VENUE_CANCEL_RESULT_UNKNOWN",
            "VENUE_RESULT_UNKNOWN",
        }
        if initial_async_reason and later_venue_diagnosis:
            values = action.model_dump(mode="python", exclude={"state_digest"})
            values.update(
                {
                    "unknown_reason": reason,
                    "next_query_at": next_query_at,
                    "state_version": action.state_version + 1,
                    "updated_at": observed_at,
                }
            )
            values["state_digest"] = execution_action_state_digest(values)
            return ExecutionAction(**values)
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


def hand_over_action_responsibility(
    action: ExecutionAction,
    *,
    observed_at: datetime,
) -> ExecutionAction:
    if action.state not in {
        ExecutionActionState.READY,
        ExecutionActionState.SUBMITTING,
        ExecutionActionState.UNKNOWN,
    }:
        raise ExecutionActionConflict("EXECUTION_ACTION_TRANSITION_INVALID")
    return _transition(
        action,
        target=ExecutionActionState.HANDED_OVER,
        observed_at=observed_at,
        updates={
            "unknown_reason": None,
            "next_query_at": None,
        },
    )
