"""EXE application boundary; one implementation serves Demo and Live instances."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from halpha.capital.models import CapDecision
from halpha.domain_values import content_digest
from halpha.planning.models import PlanEvent
from halpha.venue_integration.facts import (
    action_quantity_conflict,
    terminal_fills_complete,
    terminal_order_status,
    venue_trade_economic_version_digest,
    venue_trade_fact_is_canonicalizable,
)
from halpha.venue_integration.models import (
    BINANCE_USDM_VENUE_REF,
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
    begin_submission,
    build_execution_action,
    defer_unknown_query,
    hand_over_action_responsibility,
    mark_not_submitted,
    mark_action_open,
    mark_submission_unknown,
    reconcile_action,
    resolve_existing_action,
)


_SUPPORTED_ORDER_STATUSES = frozenset(
    {
        "ACKNOWLEDGED",
        "ACCEPTED",
        "WORKING",
        "NEW",
        "PARTIALLY_FILLED",
        "FILLED",
        "CANCELLED",
        "CANCELED",
        "REJECTED",
        "EXPIRED",
    }
)


def _same_source_content(left: VenueFact, right: VenueFact) -> bool:
    """Ignore only the local observation time for an identical venue fact."""

    venue_matches = left.venue_ref == right.venue_ref
    if (
        left.kind is right.kind
        and venue_trade_fact_is_canonicalizable(left)
        and venue_trade_fact_is_canonicalizable(right)
    ):
        return (
            venue_matches
            and venue_trade_economic_version_digest(left)
            == venue_trade_economic_version_digest(right)
            and _same_trade_attribution(left, right)
        )

    fields = (
        "environment_id",
        "account_ref",
        "instrument_ref",
        "kind",
        "source_class",
        "source_object_id",
        "source_sequence",
        "source_time",
        "schema_version",
        "payload",
        "activation_ref",
        "action_ref",
        "attribution_digest",
        "attribution_class",
        "handover_command_ref",
        "supersedes_ref",
        "correction_reason",
        "correction_evidence_refs",
        "correction_effective_time",
        "impact_scope",
        "affected_reference_refs",
    )
    return venue_matches and all(
        getattr(left, field) == getattr(right, field) for field in fields
    )


def _same_trade_attribution(left: VenueFact, right: VenueFact) -> bool:
    return all(
        getattr(left, field) == getattr(right, field)
        for field in (
            "activation_ref",
            "action_ref",
            "attribution_class",
            "handover_command_ref",
            "impact_scope",
            "affected_reference_refs",
        )
    )


def _canonical_trade_candidate(
    fact: VenueFact,
    candidates: tuple[VenueFact, ...],
) -> VenueFact | None:
    candidates = tuple(
        candidate
        for candidate in candidates
        if venue_trade_fact_is_canonicalizable(candidate)
    )
    if not candidates:
        return None
    digest = venue_trade_economic_version_digest(fact)
    matching = tuple(
        candidate
        for candidate in candidates
        if venue_trade_economic_version_digest(candidate) == digest
    )
    for candidate in matching:
        if _same_trade_attribution(candidate, fact):
            return candidate
    base_digest = venue_trade_economic_version_digest(
        fact,
        include_role=False,
    )
    if matching or any(
        venue_trade_economic_version_digest(
            candidate,
            include_role=False,
        )
        == base_digest
        for candidate in candidates
    ):
        raise ValueError("FACT_ATTRIBUTION_CONFLICT")
    raise ValueError("FACT_CONFLICT")


@dataclass(frozen=True, slots=True)
class VenueFactApplicationResult:
    """Canonical persisted fact and whether this application inserted it."""

    canonical_fact: VenueFact
    action: ExecutionAction | None
    inserted: bool
    action_quantity_conflict: bool = False


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
            ExecutionActionState.UNKNOWN,
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
        """Return every called order identity that startup must query."""

        unresolved = self._actions.list_by_states(
            (
                ExecutionActionState.SUBMITTING.value,
                ExecutionActionState.UNKNOWN.value,
                ExecutionActionState.OPEN.value,
            ),
            for_update=True,
        )
        results: list[ExecutionAction] = []
        for action in unresolved:
            action_facts = self._facts.list_for_action(
                action.execution_action_id
            )
            if (
                action.state is ExecutionActionState.OPEN
                and terminal_order_status(action_facts) is not None
                and terminal_fills_complete(action, action_facts)
            ):
                # The original venue identity and its complete position effect
                # are already durable.  The product responsibility loop still
                # closes the monotonic action, but startup does not need to
                # re-query a terminal identity or hold the global barrier.
                continue
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

    def prepare_due_unknown_query(
        self,
        execution_action_id: str,
        *,
        next_query_at: datetime,
        observed_at: datetime,
    ) -> ExecutionAction | None:
        action = self._actions.get(execution_action_id, for_update=True)
        if (
            action.state is not ExecutionActionState.UNKNOWN
            or action.next_query_at is None
            or action.next_query_at > observed_at
        ):
            return None
        updated = defer_unknown_query(
            action,
            next_query_at=next_query_at,
            observed_at=observed_at,
        )
        self._actions.update(updated, expected_version=action.state_version)
        return updated

    def record_definitely_not_submitted(
        self,
        execution_action_id: str,
        *,
        reason_code: str,
        observed_at: datetime,
    ) -> ExecutionAction:
        action = self._actions.get(execution_action_id, for_update=True)
        updated = mark_not_submitted(
            action,
            reason_code=reason_code,
            observed_at=observed_at,
        )
        self._actions.update(updated, expected_version=action.state_version)
        return updated

    def apply_venue_fact(
        self,
        *,
        fact: VenueFact,
        observed_at: datetime,
    ) -> ExecutionAction | None:
        return self.apply_venue_fact_with_result(
            fact=fact,
            observed_at=observed_at,
        ).action

    def apply_venue_fact_with_result(
        self,
        *,
        fact: VenueFact,
        observed_at: datetime,
    ) -> VenueFactApplicationResult:
        if fact.venue_ref != BINANCE_USDM_VENUE_REF:
            raise ValueError("VENUE_FACT_VENUE_REF_MISMATCH")
        trade_fact = venue_trade_fact_is_canonicalizable(fact)
        existing = (
            _canonical_trade_candidate(
                fact,
                self._facts.list_trade_versions(fact),
            )
            if trade_fact
            else self._facts.find_by_source(fact)
        )
        inserted = False
        if existing is not None:
            if not _same_source_content(existing, fact):
                raise ValueError("FACT_CONFLICT")
            fact = existing
        else:
            inserted = self._facts.insert(fact)
            if not inserted:
                existing = (
                    _canonical_trade_candidate(
                        fact,
                        self._facts.list_trade_versions(fact),
                    )
                    if trade_fact
                    else self._facts.find_by_source(fact)
                )
                if existing is None or not _same_source_content(existing, fact):
                    raise ValueError("FACT_CONFLICT")
                fact = existing
        if fact.action_ref is None:
            return VenueFactApplicationResult(
                canonical_fact=fact,
                action=None,
                inserted=inserted,
            )
        action = self._actions.get(fact.action_ref, for_update=True)
        payload_client_order_id = fact.payload.get("client_order_id")
        requires_trade_identity = fact.kind in {
            VenueFactKind.FILL,
            VenueFactKind.COMMISSION,
        }
        if (
            fact.environment_id != action.environment_id
            or fact.activation_ref != action.activation_id
            or fact.account_ref != action.account_ref
            or fact.instrument_ref != action.action_terms.get("instrument_ref")
            or (
                requires_trade_identity
                and (
                    action.client_order_id is None
                    or payload_client_order_id != action.client_order_id
                )
            )
            or (
                not requires_trade_identity
                and payload_client_order_id is not None
                and payload_client_order_id != action.client_order_id
            )
        ):
            raise ValueError("VENUE_FACT_ATTRIBUTION_INVALID")
        quantity_conflict = action_quantity_conflict(
            action,
            self._facts.list_for_action(action.execution_action_id),
        )
        if fact.venue_fact_id in action.venue_fact_refs:
            return VenueFactApplicationResult(
                canonical_fact=fact,
                action=action,
                inserted=inserted,
                action_quantity_conflict=quantity_conflict,
            )
        venue_order_ref = fact.payload.get("venue_order_ref")
        venue_order_refs = (str(venue_order_ref),) if venue_order_ref else ()
        venue_fact_refs = (fact.venue_fact_id,)
        opens_action = _execution_fact_opens_action(fact)
        if (
            not opens_action
            or action.state
            not in {
                ExecutionActionState.SUBMITTING,
                ExecutionActionState.UNKNOWN,
            }
        ):
            updated = absorb_venue_observation(
                action,
                venue_order_refs=venue_order_refs,
                venue_fact_refs=venue_fact_refs,
                observed_at=observed_at,
            )
            if updated is not action:
                self._actions.update(updated, expected_version=action.state_version)
            return VenueFactApplicationResult(
                canonical_fact=fact,
                action=updated,
                inserted=inserted,
                action_quantity_conflict=quantity_conflict,
            )
        updated = mark_action_open(
            action,
            venue_order_refs=venue_order_refs,
            venue_fact_refs=venue_fact_refs,
            observed_at=observed_at,
        )
        self._actions.update(updated, expected_version=action.state_version)
        return VenueFactApplicationResult(
            canonical_fact=fact,
            action=updated,
            inserted=inserted,
            action_quantity_conflict=quantity_conflict,
        )

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
            ExecutionActionState.UNKNOWN,
        }:
            opened = mark_action_open(
                action,
                venue_order_refs=(
                    str(target_fact.payload["venue_order_ref"]),
                )
                if target_fact.payload.get("venue_order_ref")
                else (),
                venue_fact_refs=(target_fact.venue_fact_id,),
                observed_at=observed_at,
            )
            self._actions.update(opened, expected_version=action.state_version)
            action = opened
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
            if action.state in {
                ExecutionActionState.READY,
                ExecutionActionState.SUBMITTING,
                ExecutionActionState.UNKNOWN,
            }:
                locked = self._actions.get(action.execution_action_id, for_update=True)
                if locked.state not in {
                    ExecutionActionState.READY,
                    ExecutionActionState.SUBMITTING,
                    ExecutionActionState.UNKNOWN,
                }:
                    results.append(locked)
                    continue
                handed_over = hand_over_action_responsibility(
                    locked,
                    observed_at=observed_at,
                )
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
        user_takeover: bool,
        handover_command_ref: str | None,
        fact_refs: tuple[str, ...],
    ) -> str:
        actions = self._actions.list_for_activation(activation_id)
        closed_states = {
            ExecutionActionState.CLOSED,
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
        return content_digest(
            {
                "environment_id": self._environment_id,
                "activation_id": activation_id,
                "cutoff": cutoff,
                "position_zero": position_zero,
                "open_order_refs": open_order_refs,
                "external_activity_conflict": external_activity_conflict,
                "user_takeover": user_takeover,
                "handover_command_ref": handover_command_ref,
                "fact_refs": fact_refs,
                "action_closure_digests": tuple(
                    (action.execution_action_id, action.closure_evidence_digest)
                    for action in actions
                ),
            }
        )


def _execution_fact_opens_action(fact: VenueFact) -> bool:
    if fact.kind is VenueFactKind.ORDER_STATE:
        status = str(fact.payload.get("status", "")).upper()
        if status not in _SUPPORTED_ORDER_STATUSES:
            raise ValueError("VENUE_ORDER_STATE_UNSUPPORTED")
        return True
    if fact.kind is VenueFactKind.FILL:
        return True
    return False
