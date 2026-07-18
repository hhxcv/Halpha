"""EXE application boundary; one implementation serves Demo and Live instances."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from halpha.capital.models import CapDecision
from halpha.domain_values import DomainValidationError, content_digest, decimal_from_string
from halpha.planning.models import PlanEvent
from halpha.venue_integration.models import (
    ExecutionAction,
    ExecutionActionState,
    VenueFact,
    VenueFactKind,
)
from halpha.venue_integration.repository import (
    PostgreSQLExecutionActionRepository,
    PostgreSQLVenueFactRepository,
)
from halpha.venue_integration.transitions import (
    absorb_venue_observation,
    apply_venue_outcome,
    begin_submission,
    build_execution_action,
    hand_over_ready_action,
    mark_not_submitted,
    mark_submission_unknown,
    reconcile_action,
    resolve_existing_action,
    venue_target_is_stale,
)


_ORDER_STATE_MAP = {
    "ACKNOWLEDGED": ExecutionActionState.ACKNOWLEDGED,
    "ACCEPTED": ExecutionActionState.ACKNOWLEDGED,
    "WORKING": ExecutionActionState.WORKING,
    "NEW": ExecutionActionState.WORKING,
    "PARTIALLY_FILLED": ExecutionActionState.PARTIALLY_FILLED,
    "FILLED": ExecutionActionState.FILLED,
    "CANCELLED": ExecutionActionState.CANCELLED,
    "CANCELED": ExecutionActionState.CANCELLED,
    "REJECTED": ExecutionActionState.REJECTED,
    "EXPIRED": ExecutionActionState.EXPIRED,
}


class ExecutionApplicationService:
    """The sole mutable EXE boundary used by both runtime profiles."""

    def __init__(
        self,
        action_repository: PostgreSQLExecutionActionRepository,
        fact_repository: PostgreSQLVenueFactRepository,
        *,
        environment_id: str,
        environment_kind: str,
        authority_class: str,
        execution_profile_ref: str,
        account_ref: str,
    ) -> None:
        self._actions = action_repository
        self._facts = fact_repository
        self._environment_id = environment_id
        self._environment_kind = environment_kind
        self._authority_class = authority_class
        self._execution_profile_ref = execution_profile_ref
        self._account_ref = account_ref

    def create_execution_action(
        self,
        *,
        execution_action_id: str,
        plan_event: PlanEvent,
        observed_at: datetime,
        client_order_id: str | None = None,
    ) -> ExecutionAction:
        proposed = plan_event.proposed_action
        if proposed is None:
            raise ValueError("CAP_REJECTED")
        existing = self._actions.find_by_source(
            activation_id=plan_event.activation_id,
            plan_event_ref=plan_event.plan_event_id,
            source_identity=plan_event.source_identity,
            action_kind=proposed.action_kind.value,
        )
        replay = resolve_existing_action(existing, plan_event=plan_event)
        if replay is not None:
            return replay
        action = build_execution_action(
            execution_action_id=execution_action_id,
            plan_event=plan_event,
            environment_kind=self._environment_kind,
            authority_class=self._authority_class,
            execution_profile_ref=self._execution_profile_ref,
            account_ref=self._account_ref,
            observed_at=observed_at,
            client_order_id=client_order_id,
        )
        if action.environment_id != self._environment_id:
            raise ValueError("AUTHORIZATION_MISMATCH")
        self._actions.insert(action)
        return action

    def prepare_submission(
        self,
        execution_action_id: str,
        *,
        capital_decision: CapDecision,
        request_payload: dict[str, Any],
        observed_at: datetime,
    ) -> ExecutionAction:
        action = self._actions.get(execution_action_id, for_update=True)
        if action.state in {
            ExecutionActionState.SUBMITTING,
            ExecutionActionState.SUBMITTED_UNKNOWN,
        }:
            raise RuntimeError("SUBMISSION_RESULT_UNKNOWN")
        prepared = begin_submission(
            action,
            capital_decision=capital_decision,
            request_payload=request_payload,
            observed_at=observed_at,
        )
        self._actions.update(prepared, expected_version=action.state_version)
        return prepared

    def prepare_startup_reconciliation(
        self,
        *,
        observed_at: datetime,
    ) -> tuple[ExecutionAction, ...]:
        """Convert the submit crash window to query-only before recovery I/O."""

        unresolved = self._actions.list_by_states(
            (
                ExecutionActionState.SUBMITTING.value,
                ExecutionActionState.SUBMITTED_UNKNOWN.value,
            ),
            for_update=True,
        )
        results: list[ExecutionAction] = []
        for action in unresolved:
            if action.state is ExecutionActionState.SUBMITTING:
                updated = mark_submission_unknown(
                    action,
                    reason="EXECUTOR_RESTART_AFTER_SUBMITTING",
                    next_query_at=observed_at,
                    observed_at=observed_at,
                )
                self._actions.update(updated, expected_version=action.state_version)
                results.append(updated)
            else:
                results.append(action)
        return tuple(results)

    def record_submission_unknown(
        self,
        execution_action_id: str,
        *,
        reason: str,
        next_query_at: datetime,
        observed_at: datetime,
    ) -> ExecutionAction:
        action = self._actions.get(execution_action_id, for_update=True)
        updated = mark_submission_unknown(
            action,
            reason=reason,
            next_query_at=next_query_at,
            observed_at=observed_at,
        )
        if updated is not action:
            self._actions.update(updated, expected_version=action.state_version)
        return updated

    def record_definitely_not_submitted(
        self,
        execution_action_id: str,
        *,
        observed_at: datetime,
    ) -> ExecutionAction:
        action = self._actions.get(execution_action_id, for_update=True)
        updated = mark_not_submitted(action, observed_at=observed_at)
        self._actions.update(updated, expected_version=action.state_version)
        return updated

    def apply_venue_fact(
        self,
        *,
        fact: VenueFact,
        observed_at: datetime,
    ) -> ExecutionAction | None:
        existing = self._facts.find_by_source(fact)
        if existing is not None:
            if existing.content_digest != fact.content_digest:
                raise ValueError("FACT_CONFLICT")
            fact = existing
        else:
            self._facts.insert(fact)
        if fact.action_ref is None:
            return None
        action = self._actions.get(fact.action_ref, for_update=True)
        if (
            fact.environment_id != action.environment_id
            or fact.activation_ref != action.activation_id
        ):
            raise ValueError("VENUE_FACT_ATTRIBUTION_INVALID")
        if fact.venue_fact_id in action.venue_fact_refs:
            return action
        venue_order_ref = fact.payload.get("venue_order_ref")
        venue_order_refs = (str(venue_order_ref),) if venue_order_ref else ()
        venue_fact_refs = (fact.venue_fact_id,)
        target = _state_from_fact(fact)
        if (
            target is None
            or target is action.state
            or venue_target_is_stale(action.state, target)
        ):
            updated = absorb_venue_observation(
                action,
                venue_order_refs=venue_order_refs,
                venue_fact_refs=venue_fact_refs,
                observed_at=observed_at,
            )
            if updated is not action:
                self._actions.update(updated, expected_version=action.state_version)
            return updated
        updated = apply_venue_outcome(
            action,
            target=target,
            venue_order_refs=venue_order_refs,
            venue_fact_refs=venue_fact_refs,
            observed_at=observed_at,
        )
        self._actions.update(updated, expected_version=action.state_version)
        return updated

    def reconcile_execution_action(
        self,
        execution_action_id: str,
        *,
        closure_evidence: dict[str, Any],
        venue_fact_refs: tuple[str, ...],
        observed_at: datetime,
    ) -> ExecutionAction:
        action = self._actions.get(execution_action_id, for_update=True)
        updated = reconcile_action(
            action,
            closure_evidence=closure_evidence,
            venue_fact_refs=venue_fact_refs,
            observed_at=observed_at,
        )
        self._actions.update(updated, expected_version=action.state_version)
        return updated

    def reconcile_cancel_from_target_fact(
        self,
        execution_action_id: str,
        *,
        target_fact: VenueFact,
        observed_at: datetime,
    ) -> ExecutionAction:
        action = self._actions.get(execution_action_id, for_update=True)
        if action.action_kind.value != "CANCEL":
            raise ValueError("CANCEL_TARGET_INVALID")
        if action.state in {
            ExecutionActionState.SUBMITTING,
            ExecutionActionState.SUBMITTED_UNKNOWN,
        }:
            acknowledged = apply_venue_outcome(
                action,
                target=ExecutionActionState.ACKNOWLEDGED,
                venue_order_refs=(
                    str(target_fact.payload["venue_order_ref"]),
                )
                if target_fact.payload.get("venue_order_ref")
                else (),
                venue_fact_refs=(target_fact.venue_fact_id,),
                observed_at=observed_at,
            )
            self._actions.update(acknowledged, expected_version=action.state_version)
            action = acknowledged
        reconciled = reconcile_action(
            action,
            closure_evidence={
                "target_order_terminal": True,
                "target_fact_ref": target_fact.venue_fact_id,
                "target_client_order_id": action.cancel_target.get("client_order_id")
                if action.cancel_target
                else None,
            },
            venue_fact_refs=(target_fact.venue_fact_id,),
            observed_at=observed_at,
        )
        self._actions.update(reconciled, expected_version=action.state_version)
        return reconciled

    def apply_user_takeover(
        self,
        activation_id: str,
        *,
        observed_at: datetime,
    ) -> tuple[ExecutionAction, ...]:
        results: list[ExecutionAction] = []
        for action in self._actions.list_for_activation(activation_id):
            if action.state is ExecutionActionState.READY:
                locked = self._actions.get(action.execution_action_id, for_update=True)
                handed_over = hand_over_ready_action(locked, observed_at=observed_at)
                self._actions.update(handed_over, expected_version=locked.state_version)
                results.append(handed_over)
            else:
                results.append(action)
        return tuple(results)

    def evaluate_activation_closure(
        self,
        activation_id: str,
        *,
        cutoff: datetime,
        position_zero: bool,
        open_order_refs: tuple[str, ...],
        external_activity_conflict: bool,
        fees_complete: bool,
        funding_complete: bool,
        user_takeover: bool,
        handover_command_ref: str | None,
        fact_refs: tuple[str, ...],
    ) -> str:
        actions = self._actions.list_for_activation(activation_id)
        closed_states = {
            ExecutionActionState.RECONCILED,
            ExecutionActionState.NOT_SUBMITTED,
            ExecutionActionState.HANDED_OVER,
        }
        if (
            not position_zero
            or open_order_refs
            or external_activity_conflict
            or any(action.state not in closed_states for action in actions)
        ):
            raise ValueError("CLOSURE_UNPROVEN")
        if user_takeover:
            if handover_command_ref is None:
                raise ValueError("CLOSURE_UNPROVEN")
        elif not fees_complete or not funding_complete:
            raise ValueError("CLOSURE_UNPROVEN")
        return content_digest(
            {
                "environment_id": self._environment_id,
                "activation_id": activation_id,
                "cutoff": cutoff,
                "position_zero": position_zero,
                "open_order_refs": open_order_refs,
                "external_activity_conflict": external_activity_conflict,
                "fees_complete": fees_complete,
                "funding_complete": funding_complete,
                "user_takeover": user_takeover,
                "handover_command_ref": handover_command_ref,
                "fact_refs": fact_refs,
                "action_closure_digests": tuple(
                    (action.execution_action_id, action.closure_evidence_digest)
                    for action in actions
                ),
            }
        )


def _state_from_fact(fact: VenueFact) -> ExecutionActionState | None:
    if fact.kind is VenueFactKind.ORDER_STATE:
        status = str(fact.payload.get("status", "")).upper()
        target = _ORDER_STATE_MAP.get(status)
        if target is None:
            raise ValueError("VENUE_ORDER_STATE_UNSUPPORTED")
        return target
    if fact.kind is VenueFactKind.FILL:
        leaves_quantity = fact.payload.get("leaves_quantity")
        if isinstance(leaves_quantity, str):
            try:
                parsed = decimal_from_string(
                    leaves_quantity,
                    code="VENUE_LEAVES_QUANTITY_INVALID",
                    non_negative=True,
                )
            except DomainValidationError:
                pass
            else:
                if parsed == 0:
                    return ExecutionActionState.FILLED
        return ExecutionActionState.PARTIALLY_FILLED
    return None
