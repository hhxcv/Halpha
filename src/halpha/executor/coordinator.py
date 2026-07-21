"""Executor application coordinator; it owns ordering, not domain records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from psycopg import Connection

from halpha.capital.models import (
    ActivationCapitalBoundary,
    ActionCheckInput,
    AuthorityClass,
    EnvironmentKind,
    RiskClass,
)
from halpha.capital.service import CapitalApplicationService
from halpha.domain_values import content_digest
from halpha.outcomes.service import OutcomeApplicationService, review_id_for_activation
from halpha.planning.models import (
    ConditionJudgement,
    ConditionResult,
    PlanActivation,
    PlanEvent,
    PlanLifecycle,
    ProposedAction,
    ProtectionState,
    RunState,
)
from halpha.planning.service import PlanningApplicationService
from halpha.planning.strategies.one_shot import StrategyProposal
from halpha.planning.transitions import (
    proposed_cancel_for_action,
    proposed_protection_from_fill,
    proposed_reduce_or_close_position,
    proposed_take_profits_from_fill,
    venue_source_identity,
)
from halpha.venue_integration.facts import build_venue_fact
from halpha.venue_integration.gateway import (
    PersistedActionGate,
    VenueDefinitelyNotSubmitted,
)
from halpha.venue_integration.models import (
    ExecutionAction,
    ExecutionActionKind,
    ExecutionActionState,
    VenueFactKind,
    VenueFact,
    VenueFactSourceClass,
)
from halpha.venue_integration.nautilus_events import (
    NautilusExecutionEventNormalizer,
    NormalizedNautilusEvent,
)
from halpha.venue_integration.repository import (
    PostgreSQLExecutionActionRepository,
    PostgreSQLVenueFactRepository,
)
from halpha.venue_integration.service import ExecutionApplicationService


@dataclass(frozen=True, slots=True)
class CoordinatedProposalResult:
    plan_event: PlanEvent
    execution_action: ExecutionAction | None


@dataclass(frozen=True, slots=True)
class ProcessExecutionResult:
    execution_action: ExecutionAction
    venue_called: bool
    reason_code: str


def _protection_projection_state(
    action: ExecutionAction,
) -> ProtectionState | None:
    if action.action_kind is not ExecutionActionKind.PROTECTION:
        return None
    if action.state is ExecutionActionState.WORKING:
        return ProtectionState.WORKING
    if action.state in {
        ExecutionActionState.CANCELLED,
        ExecutionActionState.REJECTED,
        ExecutionActionState.EXPIRED,
    }:
        return ProtectionState.GAP
    return None


def _submission_block_reason(
    action: ExecutionAction,
    activation: PlanActivation,
) -> str | None:
    """Pause new risk without disabling protection, cancellation, or exit duties."""

    if activation.lifecycle in {
        PlanLifecycle.USER_TAKEOVER,
        PlanLifecycle.COMPLETED,
    }:
        return "USER_TAKEOVER_ACTIVE"
    if (
        activation.run_state is not RunState.ACTIVE
        and action.action_class is RiskClass.RISK_INCREASING
    ):
        return "NEW_RISK_STOPPED"
    return None


class HalphaCoordinator:
    """Compose TRADEPLAN -> CAP -> EXE with no direct cross-owner table writes."""

    def __init__(
        self,
        connection: Connection[Any],
        gate: PersistedActionGate,
        *,
        environment_id: str,
        environment_kind: str,
        authority_class: str,
        execution_profile_ref: str,
        account_ref: str,
        venue_ref: str = "BINANCE",
        runtime_real_write_gate: str = "CLOSED",
        live_write_activation_id: str | None = None,
        live_write_submission_guard: Callable[[str], None] | None = None,
    ) -> None:
        if environment_kind == "DEMO":
            if (
                authority_class != "DEMO_VALIDATION"
                or execution_profile_ref != "BINANCE_DEMO"
            ):
                raise ValueError("EXECUTION_PROFILE_MISMATCH")
        elif environment_kind == "LIVE":
            if (
                authority_class != "LIVE_REAL_CAPITAL"
                or execution_profile_ref != "BINANCE_LIVE_WRITE"
                or runtime_real_write_gate != "OPEN"
                or live_write_activation_id is None
                or live_write_submission_guard is None
            ):
                raise ValueError("EXECUTION_PROFILE_MISMATCH")
        else:
            raise ValueError("EXECUTION_PROFILE_MISMATCH")
        self._connection = connection
        self._gate = gate
        self._environment_id = environment_id
        self._environment_kind = environment_kind
        self._authority_class = authority_class
        self._execution_profile_ref = execution_profile_ref
        self._account_ref = account_ref
        self._venue_ref = venue_ref
        self._runtime_real_write_gate = runtime_real_write_gate
        self._live_write_activation_id = live_write_activation_id
        self._live_write_submission_guard = live_write_submission_guard
        self._planning = PlanningApplicationService(connection, environment_id)
        self._capital = CapitalApplicationService(connection, environment_id)
        self._action_repository = PostgreSQLExecutionActionRepository(
            connection, environment_id
        )
        self._fact_repository = PostgreSQLVenueFactRepository(connection, environment_id)
        self._execution = ExecutionApplicationService(
            self._action_repository,
            self._fact_repository,
            environment_id=environment_id,
            environment_kind=environment_kind,
            authority_class=authority_class,
            execution_profile_ref=execution_profile_ref,
            account_ref=account_ref,
        )

    def get_activation_snapshot(self, activation_id: str) -> PlanActivation:
        return self._planning.get_activation(activation_id)

    def get_execution_action(self, execution_action_id: str) -> ExecutionAction:
        return self._action_repository.get(execution_action_id)

    def list_execution_actions(
        self,
        activation_id: str,
    ) -> tuple[ExecutionAction, ...]:
        return self._action_repository.list_for_activation(activation_id)

    def has_open_entry_responsibility(self, activation_id: str) -> bool:
        return self._action_repository.has_open_entry_responsibility(activation_id)

    def new_risk_allowed(self, activation_id: str) -> bool:
        with self._connection.transaction():
            return self._capital.new_risk_allowed(activation_id)

    def list_venue_facts_for_action(
        self,
        execution_action_id: str,
    ) -> tuple[VenueFact, ...]:
        return self._fact_repository.list_for_action(execution_action_id)

    def expire_empty_entry_window(
        self,
        *,
        activation_id: str,
        observed_at: datetime,
    ) -> tuple[PlanActivation, PlanEvent]:
        """Close one expired activation when it never created venue responsibility."""

        with self._connection.transaction():
            expired, event = self._planning.expire_entry_deadline(
                activation_id=activation_id,
                plan_event_id=str(uuid4()),
                observed_at=observed_at,
            )
            if (
                expired.has_entry_fill
                or expired.pending_action_digest is not None
                or self._action_repository.list_for_activation(activation_id)
            ):
                return expired, event
            result_ref = review_id_for_activation(
                self._environment_id,
                activation_id,
            )
            closure_digest = content_digest(
                {
                    "environment_id": self._environment_id,
                    "activation_id": activation_id,
                    "reason": "ENTRY_WINDOW_EXPIRED",
                    "plan_event_id": event.plan_event_id,
                    "entry_deadline": event.source_cutoff,
                    "has_entry_fill": False,
                    "execution_action_count": 0,
                }
            )
            completed = self._planning.complete_with_execution_closure(
                activation_id=activation_id,
                closure_digest=closure_digest,
                result_ref=result_ref,
                observed_at=observed_at,
            )
            OutcomeApplicationService(
                self._connection,
                self._environment_id,
            ).update_activation_review(
                activation_id,
                fact_cutoff=event.source_cutoff,
                observed_at=observed_at,
            )
            return completed, event

    def get_entry_sizing_boundary(self, activation_id: str) -> ActivationCapitalBoundary:
        with self._connection.transaction():
            return self._capital.get_plan_boundary(activation_id)

    def record_strategy_proposal_rejection(
        self,
        *,
        plan_event_id: str,
        proposal: StrategyProposal,
        reason_code: str,
        observed_at: datetime,
    ) -> PlanEvent:
        """Persist a fail-closed proposal outcome without creating an EXE action."""

        with self._connection.transaction():
            return self._planning.record_plan_event(
                plan_event_id=plan_event_id,
                activation_id=proposal.activation_id,
                rule_id=proposal.rule_id,
                source_identity=proposal.source_identity,
                source_cutoff=proposal.source_cutoff,
                input_digest=proposal.input_digest,
                reason_code=reason_code,
                proposed_action=None,
                no_action_reason=reason_code,
                condition_judgement=ConditionJudgement(
                    rule_id=proposal.rule_id,
                    source_identity=proposal.source_identity,
                    source_cutoff=proposal.source_cutoff,
                    input_digest=proposal.input_digest,
                    result=ConditionResult.UNKNOWN,
                    reason_code=reason_code,
                    next_responsibility="NONE",
                ),
                capital_decision={
                    "accepted": False,
                    "reason_code": f"NOT_EVALUATED_{reason_code}",
                },
                created_at=observed_at,
            )

    def reject_execution_action_before_submission(
        self,
        execution_action_id: str,
        *,
        reason_code: str,
        observed_at: datetime,
    ) -> ExecutionAction:
        """Close a READY action when the second fresh-fact check fails."""

        with self._connection.transaction():
            action = self._action_repository.get(
                execution_action_id,
                for_update=True,
            )
            if action.state is not ExecutionActionState.READY:
                return action
            return self._execution.record_definitely_not_submitted(
                execution_action_id,
                reason_code=reason_code,
                observed_at=observed_at,
            )

    def record_unknown_action_not_submitted(
        self,
        execution_action_id: str,
        *,
        reason_code: str,
        observed_at: datetime,
    ) -> ExecutionAction:
        """Close only an unresolved action proven absent by its original identity."""

        with self._connection.transaction():
            action = self._action_repository.get(
                execution_action_id,
                for_update=True,
            )
            if action.state is not ExecutionActionState.SUBMITTED_UNKNOWN:
                return action
            return self._execution.record_definitely_not_submitted(
                execution_action_id,
                reason_code=reason_code,
                observed_at=observed_at,
            )

    def reconcile_execution_action(
        self,
        execution_action_id: str,
        *,
        closure_evidence: dict[str, Any],
        venue_fact_refs: tuple[str, ...],
        observed_at: datetime,
    ) -> ExecutionAction:
        with self._connection.transaction():
            return self._execution.reconcile_execution_action(
                execution_action_id,
                closure_evidence=closure_evidence,
                venue_fact_refs=venue_fact_refs,
                observed_at=observed_at,
            )

    def recover_unresolved_actions(self, *, observed_at: datetime) -> tuple[ExecutionAction, ...]:
        """Make crash-window actions query-only, then query their original UUIDs.

        The caller must run this only after the TradingNode startup reconciliation
        is ready and while all affected activations remain continuity-paused.
        Query calls are asynchronous; callbacks persist the authoritative result.
        """

        with self._connection.transaction():
            unresolved = self._execution.prepare_startup_reconciliation(
                observed_at=observed_at,
            )
        for action in unresolved:
            try:
                self._gate.query_original_identity(action.execution_action_id)
            except Exception:
                # A query transport failure is not evidence about venue state.
                # The action remains SUBMITTED_UNKNOWN for a later same-UUID query.
                continue
        return unresolved

    def query_unknown_action_if_due(
        self,
        execution_action_id: str,
        *,
        observed_at: datetime,
    ) -> bool:
        """Query one unresolved action by its original UUID at a limited rate."""

        with self._connection.transaction():
            action = self._execution.prepare_due_unknown_query(
                execution_action_id,
                next_query_at=observed_at + timedelta(seconds=10),
                observed_at=observed_at,
            )
        if action is None:
            return False
        try:
            self._gate.query_original_identity(action.execution_action_id)
        except Exception:
            # Query transport failure does not change the unresolved responsibility.
            pass
        return True

    def build_nautilus_event_normalizer(
        self,
        *,
        leaves_quantity_for_client_order_id: Callable[[str], str | None] | None = None,
    ) -> NautilusExecutionEventNormalizer:
        return NautilusExecutionEventNormalizer(
            self._action_repository.find_order_action_by_client_id,
            environment_id=self._environment_id,
            venue_ref=self._venue_ref,
            leaves_quantity_for_client_order_id=leaves_quantity_for_client_order_id,
            cancel_action_for_target=self._action_repository.find_open_cancel_for_target,
        )

    def handle_nautilus_order_event(
        self,
        normalizer: NautilusExecutionEventNormalizer,
        event: object,
        *,
        observed_at: datetime,
    ) -> NormalizedNautilusEvent:
        """Persist callback facts; unknown identities stop account new risk."""

        with self._connection.transaction():
            normalized = normalizer.normalize(event, received_at=observed_at)
            action = normalized.action
            if normalized.definitely_not_submitted and action is not None:
                self._execution.record_definitely_not_submitted(
                    action.execution_action_id,
                    reason_code="NAUTILUS_ORDER_DENIED",
                    observed_at=observed_at,
                )
                return normalized
            if normalized.result_unknown and action is not None:
                self._execution.record_submission_unknown(
                    action.execution_action_id,
                    reason=normalized.unknown_reason or "VENUE_RESULT_UNKNOWN",
                    next_query_at=observed_at + timedelta(seconds=10),
                    observed_at=observed_at,
                )
                return normalized
            for fact in normalized.facts:
                updated = self._execution.apply_venue_fact(
                    fact=fact,
                    observed_at=observed_at,
                )
                projection = (
                    _protection_projection_state(updated)
                    if updated is not None
                    else None
                )
                if projection is not None:
                    self._planning.update_protection_projection(
                        activation_id=updated.activation_id,
                        protection_state=projection,
                        pending_action_digest=None,
                        observed_at=observed_at,
                    )
                if (
                    fact.kind is VenueFactKind.ORDER_STATE
                    and fact.payload.get("status") == "CANCELLED"
                    and normalized.client_order_id is not None
                ):
                    cancel_action = self._action_repository.find_open_cancel_for_target(
                        normalized.client_order_id
                    )
                    if cancel_action is not None:
                        self._execution.reconcile_cancel_from_target_fact(
                            cancel_action.execution_action_id,
                            target_fact=fact,
                            observed_at=observed_at,
                        )
            if action is None and normalized.facts:
                evidence_digest = content_digest(
                    tuple(fact.content_digest for fact in normalized.facts)
                )
                self._capital.stop_new_risk_for_external_activity(
                    stop_state_version_id=str(uuid4()),
                    environment_kind=EnvironmentKind(self._environment_kind),
                    authority_class=AuthorityClass(self._authority_class),
                    account_ref=self._account_ref,
                    evidence_digest=evidence_digest,
                    observed_at=observed_at,
                )
            return normalized

    def consume_strategy_proposal(
        self,
        *,
        plan_event_id: str,
        execution_action_id: str,
        proposal: StrategyProposal,
        action_check: ActionCheckInput,
        created_at: datetime,
        client_order_id: str | None = None,
    ) -> CoordinatedProposalResult:
        """Commit PlanEvent and accepted ExecutionAction in one DB transaction."""

        if (
            self._environment_kind == "LIVE"
            and proposal.activation_id != self._live_write_activation_id
        ):
            raise RuntimeError("LIVE_WRITE_ACTIVATION_SCOPE_MISMATCH")
        self._require_current_live_write_gate(proposal.activation_id)
        with self._connection.transaction():
            # The activation lock serializes entry creation. An unknown order is
            # already an open responsibility even before a fill reaches TRADEPLAN.
            self._planning.get_activation(proposal.activation_id, for_update=True)
            event = self._planning.consume_strategy_proposal(
                plan_event_id=plan_event_id,
                proposal=proposal,
                action_check=action_check,
                entry_responsibility_open=(
                    self._action_repository.has_open_entry_responsibility(
                        proposal.activation_id
                    )
                ),
                created_at=created_at,
            )
            if not bool(event.capital_decision.get("accepted")):
                return CoordinatedProposalResult(event, None)
            action = self._execution.create_execution_action(
                execution_action_id=execution_action_id,
                plan_event=event,
                observed_at=created_at,
                client_order_id=client_order_id,
            )
            return CoordinatedProposalResult(event, action)

    def process_execution_action(
        self,
        execution_action_id: str,
        *,
        action_check: ActionCheckInput,
        request_payload: dict[str, Any],
        observed_at: datetime,
    ) -> ProcessExecutionResult:
        """Persist SUBMITTING, call once, then normalize the original identity."""

        if self._environment_kind == "LIVE" and self._runtime_real_write_gate != "OPEN":
            raise RuntimeError("RUNTIME_REAL_WRITE_GATE_CLOSED")
        self._require_current_live_write_gate(action_check.activation_id)
        with self._connection.transaction():
            action = self._action_repository.get(execution_action_id, for_update=True)
            if (
                self._environment_kind == "LIVE"
                and action.activation_id != self._live_write_activation_id
            ):
                raise RuntimeError("LIVE_WRITE_ACTIVATION_SCOPE_MISMATCH")
            activation = self._planning.get_activation(action.activation_id, for_update=True)
            block_reason = _submission_block_reason(action, activation)
            if block_reason is not None:
                raise RuntimeError(block_reason)
            self._validate_action_check(action, action_check)
            decision = self._capital.check_current_action(action_check)
            if not decision.accepted:
                if decision.reason_code in {"VALUATION_UNKNOWN", "ATTRIBUTION_UNKNOWN"}:
                    return ProcessExecutionResult(
                        action,
                        venue_called=False,
                        reason_code=decision.reason_code,
                    )
                rejected = self._execution.record_definitely_not_submitted(
                    execution_action_id,
                    reason_code=decision.reason_code,
                    observed_at=observed_at,
                )
                return ProcessExecutionResult(
                    rejected,
                    venue_called=False,
                    reason_code=decision.reason_code,
                )
            prepared = self._execution.prepare_submission(
                execution_action_id,
                capital_decision=decision,
                request_payload=request_payload,
                observed_at=observed_at,
            )

        try:
            self._require_current_live_write_gate(prepared.activation_id)
        except RuntimeError:
            with self._connection.transaction():
                not_submitted = self._execution.record_definitely_not_submitted(
                    prepared.execution_action_id,
                    reason_code="RUNTIME_REAL_WRITE_GATE_CLOSED",
                    observed_at=observed_at,
                )
            return ProcessExecutionResult(
                not_submitted,
                venue_called=False,
                reason_code="RUNTIME_REAL_WRITE_GATE_CLOSED",
            )

        permit = self._gate.authorize_committed_submission(
            prepared.execution_action_id,
            expected_state_digest=prepared.state_digest,
        )
        try:
            receipt = self._gate.execute_once(permit)
        except VenueDefinitelyNotSubmitted:
            with self._connection.transaction():
                not_submitted = self._execution.record_definitely_not_submitted(
                    prepared.execution_action_id,
                    reason_code="VENUE_CLIENT_DEFINITELY_NOT_SUBMITTED",
                    observed_at=observed_at,
                )
            return ProcessExecutionResult(
                not_submitted,
                venue_called=True,
                reason_code="NOT_SUBMITTED",
            )
        except Exception as exc:
            # All unclassified client failures are uncertain: error type is not
            # treated as proof that the stable identity never reached the venue.
            with self._connection.transaction():
                unknown = self._execution.record_submission_unknown(
                    prepared.execution_action_id,
                    reason=f"VENUE_CALL_UNCERTAIN:{type(exc).__name__}",
                    next_query_at=observed_at + timedelta(seconds=10),
                    observed_at=observed_at,
                )
            return ProcessExecutionResult(
                unknown,
                venue_called=True,
                reason_code="SUBMISSION_RESULT_UNKNOWN",
            )

        fact = build_venue_fact(
            venue_fact_id=str(uuid4()),
            environment_id=self._environment_id,
            venue_ref=self._venue_ref,
            account_ref=self._account_ref,
            instrument_ref=str(prepared.action_terms["instrument_ref"]),
            kind=VenueFactKind.ORDER_STATE,
            source_class=VenueFactSourceClass.VENUE_QUERY,
            source_object_id=receipt.source_object_id,
            source_sequence=receipt.source_sequence,
            source_time=receipt.source_time,
            received_at=observed_at,
            cutoff=observed_at,
            payload={**receipt.payload, "status": receipt.status},
            action=prepared,
        )
        with self._connection.transaction():
            updated = self._execution.apply_venue_fact(
                fact=fact,
                observed_at=observed_at,
            )
        if updated is None:
            raise RuntimeError("VENUE_FACT_ATTRIBUTION_INVALID")
        return ProcessExecutionResult(
            updated,
            venue_called=True,
            reason_code=f"VENUE_{updated.state.value}",
        )

    def _require_current_live_write_gate(self, activation_id: str) -> None:
        if self._environment_kind != "LIVE":
            return
        guard = self._live_write_submission_guard
        if guard is None:
            raise RuntimeError("RUNTIME_REAL_WRITE_GATE_CLOSED")
        try:
            guard(activation_id)
        except Exception:
            raise RuntimeError("RUNTIME_REAL_WRITE_GATE_CLOSED") from None

    def apply_venue_fact(
        self,
        fact: VenueFact,
        *,
        observed_at: datetime,
    ) -> ExecutionAction | None:
        """Apply one DAT fact and update only TRADEPLAN's protection projection."""

        with self._connection.transaction():
            updated = self._execution.apply_venue_fact(
                fact=fact,
                observed_at=observed_at,
            )
            projection = (
                _protection_projection_state(updated)
                if updated is not None
                else None
            )
            if projection is not None:
                self._planning.update_protection_projection(
                    activation_id=updated.activation_id,
                    protection_state=projection,
                    pending_action_digest=None,
                    observed_at=observed_at,
                )
            if (
                fact.kind is VenueFactKind.ORDER_STATE
                and fact.payload.get("status") == "CANCELLED"
            ):
                target_client_order_id = fact.payload.get("client_order_id")
                if isinstance(target_client_order_id, str):
                    cancel_action = (
                        self._action_repository.find_open_cancel_for_target(
                            target_client_order_id
                        )
                    )
                    if cancel_action is not None:
                        self._execution.reconcile_cancel_from_target_fact(
                            cancel_action.execution_action_id,
                            target_fact=fact,
                            observed_at=observed_at,
                        )
            return updated

    def create_protection_for_fill(
        self,
        *,
        fill_fact: VenueFact,
        plan_event_id: str,
        execution_action_id: str,
        action_check: ActionCheckInput,
        observed_at: datetime,
        client_order_id: str | None = None,
    ) -> CoordinatedProposalResult:
        """Persist a confirmed fill and its explicit protection in one transaction."""

        if fill_fact.kind is not VenueFactKind.FILL or fill_fact.action_ref is None:
            raise ValueError("PROTECTION_UNKNOWN")
        with self._connection.transaction():
            entry_action = self._execution.apply_venue_fact(
                fact=fill_fact,
                observed_at=observed_at,
            )
            if (
                entry_action is None
                or entry_action.action_kind is not ExecutionActionKind.ENTRY
            ):
                raise ValueError("VENUE_FACT_ATTRIBUTION_INVALID")
            context = entry_action.action_terms.get("execution_context", {}).get(
                "entry_risk_context"
            )
            if not isinstance(context, dict):
                raise ValueError("PROTECTION_UNKNOWN")
            fill_price = fill_fact.payload.get("last_price")
            fill_quantity = fill_fact.payload.get("last_quantity")
            if not isinstance(fill_price, str) or not isinstance(fill_quantity, str):
                raise ValueError("PROTECTION_UNKNOWN")
            fill_time = fill_fact.source_time or fill_fact.cutoff
            activation = self._planning.record_first_fill(
                activation_id=entry_action.activation_id,
                entry_action_ref=entry_action.execution_action_id,
                fill_fact_ref=fill_fact.venue_fact_id,
                fill_price=fill_price,
                fill_time=fill_time,
                entry_risk_context=context,
                observed_at=observed_at,
            )
            source_identity = venue_source_identity(
                activation_id=activation.activation_id,
                rule_id="PROTECTION_AFTER_FILL",
                source_class=fill_fact.source_class.value,
                source_object_id=fill_fact.source_object_id,
                source_sequence_or_version=fill_fact.source_sequence,
            )
            proposed = proposed_protection_from_fill(
                activation,
                entry_action_ref=entry_action.execution_action_id,
                fill_fact_ref=fill_fact.venue_fact_id,
                fill_source_identity=source_identity,
                fill_quantity=fill_quantity,
            )
            event, action = self._record_proposed_action(
                plan_event_id=plan_event_id,
                execution_action_id=execution_action_id,
                activation_id=activation.activation_id,
                rule_id="PROTECTION_AFTER_FILL",
                source_identity=source_identity,
                source_cutoff=fill_fact.cutoff,
                input_digest=fill_fact.content_digest,
                proposed_action=proposed,
                action_check=action_check,
                observed_at=observed_at,
                client_order_id=client_order_id,
            )
            if action is None:
                self._planning.update_protection_projection(
                    activation_id=activation.activation_id,
                    protection_state=ProtectionState.GAP,
                    pending_action_digest=None,
                    observed_at=observed_at,
                )
            else:
                self._planning.update_protection_projection(
                    activation_id=activation.activation_id,
                    protection_state=ProtectionState.UNKNOWN,
                    pending_action_digest=action.state_digest,
                    observed_at=observed_at,
                )
            return CoordinatedProposalResult(event, action)

    def create_take_profits_for_protected_fill(
        self,
        *,
        protection_action_id: str,
        fill_fact_ref: str,
        fill_source_identity: str,
        fill_quantity: str,
        plan_event_ids: tuple[str, str],
        execution_action_ids: tuple[str, str],
        action_checks: tuple[ActionCheckInput, ActionCheckInput],
        observed_at: datetime,
        client_order_ids: tuple[str | None, str | None] = (None, None),
    ) -> tuple[CoordinatedProposalResult, CoordinatedProposalResult]:
        with self._connection.transaction():
            protection = self._action_repository.get(
                protection_action_id,
                for_update=True,
            )
            if (
                protection.action_kind is not ExecutionActionKind.PROTECTION
                or protection.state is not ExecutionActionState.WORKING
            ):
                raise ValueError("PROTECTION_UNKNOWN")
            activation = self._planning.get_activation(
                protection.activation_id,
                for_update=True,
            )
            if activation.protection_state is not ProtectionState.WORKING:
                raise ValueError("PROTECTION_UNKNOWN")
            entry_action_ref = protection.action_terms.get("execution_context", {}).get(
                "entry_action_ref"
            )
            if not isinstance(entry_action_ref, str):
                raise ValueError("PROTECTION_UNKNOWN")
            proposed_actions = proposed_take_profits_from_fill(
                activation,
                entry_action_ref=entry_action_ref,
                protection_action_ref=protection.execution_action_id,
                fill_fact_ref=fill_fact_ref,
                fill_source_identity=fill_source_identity,
                fill_quantity=fill_quantity,
            )
            results = []
            for index, (proposed, event_id, action_id, check, client_id) in enumerate(
                zip(
                    proposed_actions,
                    plan_event_ids,
                    execution_action_ids,
                    action_checks,
                    client_order_ids,
                    strict=True,
                ),
                start=1,
            ):
                source_identity = f"{fill_source_identity}:TAKE_PROFIT_{index}"
                event, action = self._record_proposed_action(
                    plan_event_id=event_id,
                    execution_action_id=action_id,
                    activation_id=activation.activation_id,
                    rule_id=f"TAKE_PROFIT_{index}_AFTER_PROTECTION",
                    source_identity=source_identity,
                    source_cutoff=observed_at,
                    input_digest=proposed.causation_ref,
                    proposed_action=proposed,
                    action_check=check,
                    observed_at=observed_at,
                    client_order_id=client_id,
                )
                results.append(CoordinatedProposalResult(event, action))
            return results[0], results[1]

    def create_cancel_for_action(
        self,
        *,
        target_action_id: str,
        target_endpoint: str,
        plan_event_id: str,
        execution_action_id: str,
        action_check: ActionCheckInput,
        reason_ref: str,
        observed_at: datetime,
        client_order_id: str | None = None,
    ) -> CoordinatedProposalResult:
        with self._connection.transaction():
            target = self._action_repository.get(target_action_id, for_update=True)
            if target.client_order_id is None:
                raise ValueError("CANCEL_TARGET_INVALID")
            activation = self._planning.get_activation(target.activation_id, for_update=True)
            proposed = proposed_cancel_for_action(
                activation,
                target_client_order_id=target.client_order_id,
                target_endpoint=target_endpoint,
                causation_ref=reason_ref,
            )
            event, action = self._record_proposed_action(
                plan_event_id=plan_event_id,
                execution_action_id=execution_action_id,
                activation_id=activation.activation_id,
                rule_id="CANCEL_OPEN_RESPONSIBILITY",
                source_identity=(
                    f"{activation.activation_id}:CANCEL:{target.execution_action_id}:{reason_ref}"
                ),
                source_cutoff=observed_at,
                input_digest=content_digest(
                    {
                        "target_action_id": target.execution_action_id,
                        "target_state_digest": target.state_digest,
                        "reason_ref": reason_ref,
                    }
                ),
                proposed_action=proposed,
                action_check=action_check,
                observed_at=observed_at,
                client_order_id=client_order_id,
            )
            return CoordinatedProposalResult(event, action)

    def create_position_exit(
        self,
        *,
        activation_id: str,
        position_quantity: str,
        position_fact_ref: str,
        reason_ref: str,
        plan_event_id: str,
        execution_action_id: str,
        action_check: ActionCheckInput,
        observed_at: datetime,
        client_order_id: str | None = None,
    ) -> CoordinatedProposalResult:
        with self._connection.transaction():
            activation = self._planning.get_activation(activation_id, for_update=True)
            if activation.lifecycle not in {PlanLifecycle.RUNNING, PlanLifecycle.EXITING}:
                raise RuntimeError("USER_TAKEOVER_ACTIVE")
            proposed = proposed_reduce_or_close_position(
                activation,
                position_quantity=position_quantity,
                causation_ref=reason_ref,
                position_fact_ref=position_fact_ref,
            )
            event, action = self._record_proposed_action(
                plan_event_id=plan_event_id,
                execution_action_id=execution_action_id,
                activation_id=activation.activation_id,
                rule_id="REDUCE_OR_CLOSE_POSITION",
                source_identity=(
                    f"{activation.activation_id}:EXIT:{position_fact_ref}:{reason_ref}"
                ),
                source_cutoff=observed_at,
                input_digest=content_digest(
                    {
                        "position_fact_ref": position_fact_ref,
                        "position_quantity": position_quantity,
                        "reason_ref": reason_ref,
                    }
                ),
                proposed_action=proposed,
                action_check=action_check,
                observed_at=observed_at,
                client_order_id=client_order_id,
            )
            return CoordinatedProposalResult(event, action)

    def apply_persisted_user_takeover(
        self,
        *,
        activation_id: str,
        observed_at: datetime,
    ) -> tuple[ExecutionAction, ...]:
        with self._connection.transaction():
            activation = self._planning.get_activation(activation_id, for_update=True)
            if activation.lifecycle is not PlanLifecycle.USER_TAKEOVER:
                raise ValueError("USER_TAKEOVER_NOT_PERSISTED")
            return self._execution.apply_user_takeover(
                activation_id,
                observed_at=observed_at,
            )

    def close_activation(
        self,
        *,
        activation_id: str,
        cutoff: datetime,
        position_zero: bool,
        open_order_refs: tuple[str, ...],
        external_activity_conflict: bool,
        user_takeover: bool,
        handover_command_ref: str | None,
        fact_refs: tuple[str, ...],
        observed_at: datetime,
    ) -> str:
        """Bind closure/release atomically, then derive OUT without rollback coupling."""

        with self._connection.transaction():
            closure_digest = self._execution.evaluate_activation_closure(
                activation_id,
                cutoff=cutoff,
                position_zero=position_zero,
                open_order_refs=open_order_refs,
                external_activity_conflict=external_activity_conflict,
                user_takeover=user_takeover,
                handover_command_ref=handover_command_ref,
                fact_refs=fact_refs,
            )
            activation = self._planning.get_activation(
                activation_id,
                for_update=True,
            )
            if activation.protection_state in {
                ProtectionState.UNKNOWN,
                ProtectionState.GAP,
                ProtectionState.WORKING,
            }:
                self._planning.update_protection_projection(
                    activation_id=activation_id,
                    protection_state=ProtectionState.CLOSED,
                    pending_action_digest=None,
                    observed_at=observed_at,
                )
            self._planning.complete_with_execution_closure(
                activation_id=activation_id,
                closure_digest=closure_digest,
                result_ref=review_id_for_activation(self._environment_id, activation_id),
                observed_at=observed_at,
            )
        # OUT failure is deliberately outside the closure/release transaction.
        # Restart recovery discovers the same completed activation and retries
        # this idempotent review identity without replaying a venue action.
        with self._connection.transaction():
            OutcomeApplicationService(
                self._connection, self._environment_id
            ).update_activation_review(
                activation_id,
                fact_cutoff=cutoff,
                observed_at=observed_at,
            )
        return closure_digest

    def _record_proposed_action(
        self,
        *,
        plan_event_id: str,
        execution_action_id: str,
        activation_id: str,
        rule_id: str,
        source_identity: str,
        source_cutoff: datetime,
        input_digest: str,
        proposed_action: ProposedAction,
        action_check: ActionCheckInput,
        observed_at: datetime,
        client_order_id: str | None,
    ) -> tuple[PlanEvent, ExecutionAction | None]:
        self._validate_proposed_action_check(
            proposed_action,
            action_check,
            activation_id=activation_id,
        )
        decision = self._capital.check_current_action(action_check)
        event = self._planning.record_plan_event(
            plan_event_id=plan_event_id,
            activation_id=activation_id,
            rule_id=rule_id,
            source_identity=source_identity,
            source_cutoff=source_cutoff,
            input_digest=input_digest,
            reason_code=(
                "PROPOSED_ACTION_CAP_ACCEPTED"
                if decision.accepted
                else "PROPOSED_ACTION_CAP_REJECTED"
            ),
            proposed_action=proposed_action,
            no_action_reason=None,
            condition_judgement=None,
            capital_decision=decision.model_dump(mode="json"),
            created_at=observed_at,
        )
        if not decision.accepted:
            return event, None
        action = self._execution.create_execution_action(
            execution_action_id=execution_action_id,
            plan_event=event,
            observed_at=observed_at,
            client_order_id=client_order_id,
        )
        return event, action

    def consume_proposed_action(
        self,
        *,
        plan_event_id: str,
        execution_action_id: str,
        activation_id: str,
        rule_id: str,
        source_identity: str,
        source_cutoff: datetime,
        input_digest: str,
        proposed_action: ProposedAction,
        action_check: ActionCheckInput,
        observed_at: datetime,
        client_order_id: str | None = None,
    ) -> CoordinatedProposalResult:
        """Public coordination boundary for non-strategy rule actions."""

        with self._connection.transaction():
            event, action = self._record_proposed_action(
                plan_event_id=plan_event_id,
                execution_action_id=execution_action_id,
                activation_id=activation_id,
                rule_id=rule_id,
                source_identity=source_identity,
                source_cutoff=source_cutoff,
                input_digest=input_digest,
                proposed_action=proposed_action,
                action_check=action_check,
                observed_at=observed_at,
                client_order_id=client_order_id,
            )
            return CoordinatedProposalResult(event, action)

    @staticmethod
    def _validate_action_check(
        action: ExecutionAction,
        check: ActionCheckInput,
    ) -> None:
        terms = action.action_terms
        if (
            check.environment_id != action.environment_id
            or check.environment_kind is not action.environment_kind
            or check.authority_class is not action.authority_class
            or check.activation_id != action.activation_id
            or check.account_ref != action.account_ref
            or check.instrument_ref != terms.get("instrument_ref")
            or check.action_profile != terms.get("action_profile")
            or check.risk_class is not action.action_class
            or check.quantized_quantity != (terms.get("quantity") or "0")
        ):
            raise ValueError("ACTION_SCOPE_MISMATCH")

    def _validate_proposed_action_check(
        self,
        proposed: ProposedAction,
        check: ActionCheckInput,
        *,
        activation_id: str,
    ) -> None:
        expected_risk = (
            "RISK_INCREASING"
            if proposed.action_kind.value == "ENTRY"
            else (
                "RISK_NEUTRAL"
                if proposed.action_kind.value == "CANCEL"
                else "RISK_REDUCING"
            )
        )
        expected_category = (
            "NEW_RISK"
            if proposed.action_kind.value == "ENTRY"
            else (
                "PROTECTION"
                if proposed.action_kind.value == "PROTECTION"
                else "RISK_REDUCTION_OR_ORDER_MANAGEMENT"
            )
        )
        if (
            check.environment_id != proposed.environment_id
            or check.environment_kind.value != self._environment_kind
            or check.authority_class.value != self._authority_class
            or check.activation_id != activation_id
            or check.account_ref != self._account_ref
            or check.instrument_ref != proposed.instrument_ref
            or check.action_profile != proposed.action_profile
            or check.risk_class.value != expected_risk
            or check.control_category.value != expected_category
            or check.quantized_quantity != (proposed.quantity or "0")
        ):
            raise ValueError("PLAN_BOUNDARY_MISMATCH")
