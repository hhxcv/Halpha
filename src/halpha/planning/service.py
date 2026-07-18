"""B02 application coordination across TRADEPLAN and CAP public boundaries.

The service accepts an existing PostgreSQL connection so the caller owns one
local transaction. It never imports EXE or any venue client; B02 commits only
plans, authorization, allocation, activation, and UX command state.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from psycopg import Connection

from halpha.capital.checks import allocate_plan, check_action, latch_max_loss
from halpha.capital.models import (
    ActionCheckInput,
    AllocationRequest,
    MachineAuthorizationVersion,
    PlanAllocation,
    RiskClass,
    StopCategory,
    StopStateVersion,
)
from halpha.capital.repository import PostgreSQLCapitalRepository
from halpha.domain_values import content_digest
from halpha.planning.adapter import strategy_id_for_activation
from halpha.planning.models import (
    ConditionJudgement,
    ConditionResult,
    PlanActivation,
    PlanEvent,
    PlanLifecycle,
    ProtectionState,
    ProposedAction,
    RunState,
    TradePlanContent,
    TradePlanDraft,
    TradePlanVersion,
)
from halpha.planning.registry import build_fixed_plan_basis
from halpha.planning.repository import PostgreSQLPlanningRepository
from halpha.planning.strategies.one_shot import StrategyProposal
from halpha.planning.transitions import (
    build_plan_event,
    consume_entry_opportunity,
    complete_activation,
    deadline_source_identity,
    enter_exit,
    proposed_action_from_strategy_proposal,
    record_first_fill,
    resolve_existing_event,
    update_protection_projection,
)


class PlanningApplicationService:
    """Coordinate owner-specific repositories without taking semantic ownership."""

    def __init__(self, connection: Connection[Any], environment_id: str) -> None:
        self._planning = PostgreSQLPlanningRepository(connection, environment_id)
        self._capital = PostgreSQLCapitalRepository(connection, environment_id)
        self._environment_id = environment_id

    def create_draft(
        self,
        *,
        plan_id: str,
        content: TradePlanContent,
        observed_at: datetime,
    ) -> TradePlanDraft:
        fields = {
            "plan_id": plan_id,
            "environment_id": self._environment_id,
            "draft_version": 1,
            "content": content,
            "updated_at": observed_at,
        }
        draft = TradePlanDraft(**fields, content_digest=content_digest(content))
        self._planning.save_draft(draft, expected_version=None)
        return draft

    def update_draft(
        self,
        *,
        plan_id: str,
        expected_version: int,
        content: TradePlanContent,
        observed_at: datetime,
    ) -> TradePlanDraft:
        draft = TradePlanDraft(
            plan_id=plan_id,
            environment_id=self._environment_id,
            draft_version=expected_version + 1,
            content=content,
            content_digest=content_digest(content),
            updated_at=observed_at,
        )
        self._planning.save_draft(draft, expected_version=expected_version)
        return draft

    def fix_draft(
        self,
        *,
        plan_id: str,
        expected_draft_version: int,
        plan_version_id: str,
        build_digest: str,
        evidence_digest: str,
        evidence_scope: dict[str, object],
        fixed_at: datetime,
    ) -> TradePlanVersion:
        draft = self._planning.get_draft(plan_id, for_update=True)
        if draft.draft_version != expected_draft_version:
            raise ValueError("PLAN_VERSION_CONFLICT")
        content = draft.content
        basis = build_fixed_plan_basis(
            content.strategy_id,
            content.parameters,
            build_digest=build_digest,
            evidence_digest=evidence_digest,
            evidence_scope=evidence_scope,
        )
        fields = {
            "plan_version_id": plan_version_id,
            "plan_id": plan_id,
            "environment_id": self._environment_id,
            "fixed_at": fixed_at,
            "strategy_basis": basis,
            "account_ref": content.account_ref,
            "venue_ref": content.venue_ref,
            "instrument_ref": content.instrument_ref,
            "direction": content.direction,
            "target_exposure": content.target_exposure,
            "requested_limits": content.requested_limits,
            "valid_from": content.valid_from,
            "valid_until": content.valid_until,
            "allowed_actions": content.allowed_actions,
            "terms": content.terms,
        }
        version = TradePlanVersion(**fields, content_digest=content_digest(fields))
        self._planning.insert_version(version)
        return version

    def activate_version(
        self,
        *,
        plan_version_id: str,
        activation_id: str,
        authorization_version_id: str,
        allocation_id: str,
        capital_limit_version_id: str,
        quote_asset: str,
        observed_at: datetime,
    ) -> tuple[PlanActivation, MachineAuthorizationVersion, PlanAllocation]:
        version = self._planning.get_version(plan_version_id, for_update=True)
        if not (version.valid_from <= observed_at < version.valid_until):
            raise ValueError("AUTHORIZATION_EXPIRED")
        account = self._capital.get_account_limit(capital_limit_version_id)
        if account.account_ref != version.account_ref:
            raise ValueError("AUTHORIZATION_MISMATCH")
        if account.quote_asset != quote_asset:
            raise ValueError("ALLOCATION_CONFLICT")
        allowed_instruments = account.scope.get("instruments")
        if isinstance(allowed_instruments, list) and version.instrument_ref not in allowed_instruments:
            raise ValueError("AUTHORIZATION_MISMATCH")
        self._capital.lock_account_scope(
            account_ref=account.account_ref,
            quote_asset=quote_asset,
        )
        account = self._capital.get_account_limit(
            capital_limit_version_id,
            for_update=True,
        )
        existing = self._capital.lock_open_allocations(
            authority_class=account.authority_class.value,
            quote_asset=quote_asset,
        )
        allocation = allocate_plan(
            account,
            existing,
            AllocationRequest(
                allocation_id=allocation_id,
                activation_id=activation_id,
                capital_limit_version_ref=capital_limit_version_id,
                environment_id=account.environment_id,
                environment_kind=account.environment_kind,
                authority_class=account.authority_class,
                quote_asset=quote_asset,
                max_margin=version.requested_limits.max_margin,
                max_notional=version.requested_limits.max_notional,
                max_allowed_loss=version.requested_limits.max_allowed_loss,
            ),
        )
        authorization_fields = {
            "authorization_version_id": authorization_version_id,
            "environment_id": account.environment_id,
            "environment_kind": account.environment_kind,
            "authority_class": account.authority_class,
            "activation_id": activation_id,
            "plan_version_ref": plan_version_id,
            "account_ref": version.account_ref,
            "instrument_ref": version.instrument_ref,
            "direction": version.direction.value,
            "version": 1,
            "valid_from": max(version.valid_from, observed_at),
            "valid_until": version.valid_until,
            "allowed_actions": version.allowed_actions,
            "terms": {
                **version.terms,
                "strategy_definition_ref": (
                    f"{version.strategy_basis.strategy_id}@"
                    f"{version.strategy_basis.strategy_version}"
                ),
                "parameter_digest": version.strategy_basis.parameter_digest,
                "allocation_terms_digest": content_digest(version.requested_limits),
            },
        }
        authorization = MachineAuthorizationVersion(
            **authorization_fields,
            content_digest=content_digest(authorization_fields),
        )
        activation = PlanActivation(
            activation_id=activation_id,
            environment_id=account.environment_id,
            environment_kind=account.environment_kind,
            authority_class=account.authority_class,
            plan_version_ref=plan_version_id,
            authorization_version_ref=authorization_version_id,
            allocation_ref=allocation_id,
            account_ref=version.account_ref,
            instrument_ref=version.instrument_ref,
            direction=version.direction,
            strategy_id=version.strategy_basis.strategy_id,
            framework_strategy_id=strategy_id_for_activation(activation_id),
            target_exposure=version.target_exposure,
            rule_state={
                "deadlines": {"entry_valid_until": version.valid_until.isoformat()},
                "condition_judgements": {},
                "last_bar_cursors": {},
            },
            protection_state=ProtectionState.NONE,
            created_at=observed_at,
            updated_at=observed_at,
        )
        self._capital.insert_authorization(authorization)
        self._planning.insert_activation(activation)
        self._capital.insert_allocation(allocation)
        return activation, authorization, allocation

    def record_plan_event(
        self,
        *,
        plan_event_id: str,
        activation_id: str,
        rule_id: str,
        source_identity: str,
        source_cutoff: datetime,
        input_digest: str,
        reason_code: str,
        proposed_action: ProposedAction | None,
        no_action_reason: str | None,
        condition_judgement: ConditionJudgement | None,
        capital_decision: dict[str, object],
        created_at: datetime,
    ) -> PlanEvent:
        """Append or replay one source-identity event under the activation lock."""

        activation = self._planning.get_activation(activation_id, for_update=True)
        existing = self._planning.find_event_by_source(activation_id, source_identity)
        replay = resolve_existing_event(
            existing,
            source_identity=source_identity,
            input_digest=input_digest,
        )
        if replay is not None:
            return replay
        event = build_plan_event(
            plan_event_id=plan_event_id,
            activation=activation,
            rule_id=rule_id,
            source_identity=source_identity,
            source_cutoff=source_cutoff,
            input_digest=input_digest,
            reason_code=reason_code,
            proposed_action=proposed_action,
            no_action_reason=no_action_reason,
            condition_judgement=condition_judgement,
            capital_decision=capital_decision,
            created_at=created_at,
        )
        self._planning.insert_event(event)
        return event

    def consume_strategy_proposal(
        self,
        *,
        plan_event_id: str,
        proposal: StrategyProposal,
        action_check: ActionCheckInput,
        created_at: datetime,
    ) -> PlanEvent:
        """Normalize one proposal, perform CAP's first check, and append one event."""

        activation = self._planning.get_activation(
            proposal.activation_id,
            for_update=True,
        )
        existing = self._planning.find_event_by_source(
            activation.activation_id,
            proposal.source_identity,
        )
        replay = resolve_existing_event(
            existing,
            source_identity=proposal.source_identity,
            input_digest=proposal.input_digest,
        )
        if replay is not None:
            return replay

        proposed_action = proposed_action_from_strategy_proposal(activation, proposal)
        if (
            activation.lifecycle is not PlanLifecycle.RUNNING
            or activation.run_state is not RunState.ACTIVE
            or activation.entry_opportunity_consumed
        ):
            event = build_plan_event(
                plan_event_id=plan_event_id,
                activation=activation,
                rule_id=proposal.rule_id,
                source_identity=proposal.source_identity,
                source_cutoff=proposal.source_cutoff,
                input_digest=proposal.input_digest,
                reason_code="NEW_RISK_STOPPED",
                proposed_action=None,
                no_action_reason="NEW_RISK_STOPPED",
                condition_judgement=ConditionJudgement(
                    rule_id=proposal.rule_id,
                    source_identity=proposal.source_identity,
                    source_cutoff=proposal.source_cutoff,
                    input_digest=proposal.input_digest,
                    result=ConditionResult.TRUE,
                    reason_code=proposal.reason_code,
                    next_responsibility="NONE",
                ),
                capital_decision={
                    "accepted": False,
                    "reason_code": "NOT_EVALUATED_NEW_RISK_STOPPED",
                },
                created_at=created_at,
            )
            self._planning.insert_event(event)
            return event
        if created_at >= proposal.valid_until:
            event = build_plan_event(
                plan_event_id=plan_event_id,
                activation=activation,
                rule_id=proposal.rule_id,
                source_identity=proposal.source_identity,
                source_cutoff=proposal.source_cutoff,
                input_digest=proposal.input_digest,
                reason_code="PROPOSAL_EXPIRED",
                proposed_action=None,
                no_action_reason="PROPOSAL_EXPIRED",
                condition_judgement=ConditionJudgement(
                    rule_id=proposal.rule_id,
                    source_identity=proposal.source_identity,
                    source_cutoff=proposal.source_cutoff,
                    input_digest=proposal.input_digest,
                    result=ConditionResult.MISSED,
                    reason_code="PROPOSAL_EXPIRED",
                    next_responsibility="NONE",
                ),
                capital_decision={
                    "accepted": False,
                    "reason_code": "NOT_EVALUATED_PROPOSAL_EXPIRED",
                },
                created_at=created_at,
            )
            self._planning.insert_event(event)
            return event

        self._validate_entry_action_check(
            activation=activation,
            proposal=proposal,
            action=action_check,
            created_at=created_at,
        )
        allocation = self._capital.get_allocation(
            activation.activation_id,
            for_update=True,
        )
        authorization = self._capital.get_authorization(
            activation.authorization_version_ref,
        )
        account = self._capital.get_account_limit(
            allocation.capital_limit_version_ref,
        )
        stop_states = self._capital.lock_current_stop_states(
            account_ref=activation.account_ref,
            activation_id=activation.activation_id,
        )
        decision = check_action(
            action_check,
            account=account,
            authorization=authorization,
            allocation=allocation,
            stop_states=stop_states,
        )
        condition = ConditionJudgement(
            rule_id=proposal.rule_id,
            source_identity=proposal.source_identity,
            source_cutoff=proposal.source_cutoff,
            input_digest=proposal.input_digest,
            result=ConditionResult.TRUE,
            reason_code=proposal.reason_code,
            next_responsibility="EXE" if decision.accepted else "NONE",
        )
        event = build_plan_event(
            plan_event_id=plan_event_id,
            activation=activation,
            rule_id=proposal.rule_id,
            source_identity=proposal.source_identity,
            source_cutoff=proposal.source_cutoff,
            input_digest=proposal.input_digest,
            reason_code=(
                "PROPOSED_ACTION_CAP_ACCEPTED"
                if decision.accepted
                else "PROPOSED_ACTION_CAP_REJECTED"
            ),
            proposed_action=proposed_action,
            no_action_reason=None,
            condition_judgement=condition,
            capital_decision=decision.model_dump(mode="json"),
            created_at=created_at,
        )
        self._planning.insert_event(event)
        return event

    @staticmethod
    def _validate_entry_action_check(
        *,
        activation: PlanActivation,
        proposal: StrategyProposal,
        action: ActionCheckInput,
        created_at: datetime,
    ) -> None:
        if (
            action.environment_id != activation.environment_id
            or action.environment_kind is not activation.environment_kind
            or action.authority_class is not activation.authority_class
            or action.activation_id != activation.activation_id
            or action.account_ref != activation.account_ref
            or action.instrument_ref != activation.instrument_ref
            or action.action_profile != proposal.action_profile
            or action.control_category is not StopCategory.NEW_FUNDING
            or action.risk_class is not RiskClass.RISK_INCREASING
            or action.quantized_quantity != proposal.quantity
            or action.checked_at != created_at
        ):
            raise ValueError("AUTHORIZATION_MISMATCH")

    def pause_for_writer_continuity_loss(self, observed_at: datetime) -> int:
        """Fail closed before a replacement Executor can form any new write."""

        return self._planning.pause_all_open_for_writer_continuity_loss(observed_at)

    def get_activation(self, activation_id: str, *, for_update: bool = False) -> PlanActivation:
        """Return the TRADEPLAN-owned activation through its public boundary."""

        return self._planning.get_activation(activation_id, for_update=for_update)

    def record_first_fill(
        self,
        *,
        activation_id: str,
        entry_action_ref: str,
        fill_fact_ref: str,
        fill_price: str,
        fill_time: datetime,
        entry_risk_context: dict[str, object],
        observed_at: datetime,
    ) -> PlanActivation:
        activation = self._planning.get_activation(activation_id, for_update=True)
        updated = record_first_fill(
            activation,
            entry_action_ref=entry_action_ref,
            fill_fact_ref=fill_fact_ref,
            fill_price=fill_price,
            fill_time=fill_time,
            entry_risk_context=entry_risk_context,
            observed_at=observed_at,
        )
        if updated is not activation:
            self._planning.update_activation(
                updated,
                expected_version=activation.state_version,
            )
        return updated

    def update_protection_projection(
        self,
        *,
        activation_id: str,
        protection_state: ProtectionState,
        pending_action_digest: str | None,
        observed_at: datetime,
    ) -> PlanActivation:
        activation = self._planning.get_activation(activation_id, for_update=True)
        updated = update_protection_projection(
            activation,
            protection_state=protection_state,
            pending_action_digest=pending_action_digest,
            observed_at=observed_at,
        )
        if updated is not activation:
            self._planning.update_activation(
                updated,
                expected_version=activation.state_version,
            )
        return updated

    def complete_with_execution_closure(
        self,
        *,
        activation_id: str,
        closure_digest: str,
        result_ref: str,
        observed_at: datetime,
    ) -> PlanActivation:
        activation = self._planning.get_activation(activation_id, for_update=True)
        completed = complete_activation(
            activation,
            closure_digest=closure_digest,
            result_ref=result_ref,
            observed_at=observed_at,
        )
        self._planning.update_activation(
            completed,
            expected_version=activation.state_version,
        )
        return completed

    def expire_entry_deadline(
        self,
        *,
        activation_id: str,
        plan_event_id: str,
        observed_at: datetime,
    ) -> tuple[PlanActivation, PlanEvent]:
        """Persist one deadline event and irreversibly consume the entry window."""

        activation = self._planning.get_activation(activation_id, for_update=True)
        deadline_value = (
            activation.rule_state.get("deadlines", {}).get("entry_valid_until")
            if isinstance(activation.rule_state.get("deadlines"), dict)
            else None
        )
        if not isinstance(deadline_value, str):
            raise ValueError("ENTRY_DEADLINE_MISSING")
        try:
            deadline = datetime.fromisoformat(deadline_value.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("ENTRY_DEADLINE_INVALID") from None
        if observed_at < deadline:
            raise ValueError("ENTRY_DEADLINE_NOT_REACHED")
        source_identity = deadline_source_identity(
            activation_id=activation.activation_id,
            rule_id="ENTRY_DEADLINE",
            deadline=deadline,
        )
        input_digest = content_digest(
            {
                "activation_id": activation.activation_id,
                "rule_id": "ENTRY_DEADLINE",
                "deadline": deadline,
            }
        )
        existing = self._planning.find_event_by_source(
            activation.activation_id,
            source_identity,
        )
        replay = resolve_existing_event(
            existing,
            source_identity=source_identity,
            input_digest=input_digest,
        )
        if replay is not None:
            return activation, replay
        event = build_plan_event(
            plan_event_id=plan_event_id,
            activation=activation,
            rule_id="ENTRY_DEADLINE",
            source_identity=source_identity,
            source_cutoff=deadline,
            input_digest=input_digest,
            reason_code="ENTRY_DEADLINE_EXPIRED",
            proposed_action=None,
            no_action_reason="ENTRY_WINDOW_EXPIRED",
            condition_judgement=None,
            capital_decision={
                "accepted": False,
                "reason_code": "ENTRY_WINDOW_EXPIRED",
            },
            created_at=observed_at,
        )
        self._planning.insert_event(event)
        consumed = consume_entry_opportunity(activation, observed_at=observed_at)
        if consumed.state_version != activation.state_version:
            self._planning.update_activation(
                consumed,
                expected_version=activation.state_version,
            )
        return consumed, event

    def update_activation_loss(
        self,
        *,
        activation_id: str,
        activation_loss: Decimal,
        loss_fact_cutoff: datetime,
        funding_query_cutoff: datetime,
        fact_digest: str,
        stop_state_version_id: str,
        observed_at: datetime,
    ) -> tuple[PlanActivation, PlanAllocation, StopStateVersion | None]:
        """Persist one loss revision and atomically enter exit on first threshold hit."""

        activation = self._planning.get_activation(activation_id, for_update=True)
        allocation = self._capital.get_allocation(activation_id, for_update=True)
        states = self._capital.lock_current_stop_states(
            account_ref=activation.account_ref,
            activation_id=activation.activation_id,
        )
        updated_allocation = latch_max_loss(
            allocation,
            activation_loss=activation_loss,
            fact_cutoff=loss_fact_cutoff,
            funding_query_cutoff=funding_query_cutoff,
            fact_digest=fact_digest,
        )
        if updated_allocation.state_version != allocation.state_version:
            self._capital.update_allocation(
                updated_allocation,
                expected_version=allocation.state_version,
            )
        if not updated_allocation.max_loss_reached:
            return activation, updated_allocation, None

        current_activation_stop = next(
            (state for state in states if state.activation_id == activation.activation_id),
            None,
        )
        stop_is_current = (
            current_activation_stop is not None
            and StopCategory.NEW_FUNDING in current_activation_stop.stopped_categories
            and current_activation_stop.loss_latch_digest
            == updated_allocation.loss_latch_digest
        )
        if stop_is_current:
            max_loss_stop = current_activation_stop
        else:
            stop_fields = {
                "stop_state_version_id": stop_state_version_id,
                "environment_id": activation.environment_id,
                "environment_kind": activation.environment_kind,
                "authority_class": activation.authority_class,
                "account_ref": activation.account_ref,
                "activation_id": activation.activation_id,
                "version": (
                    1 if current_activation_stop is None else current_activation_stop.version + 1
                ),
                "stopped_categories": frozenset(
                    set(
                        current_activation_stop.stopped_categories
                        if current_activation_stop is not None
                        else ()
                    )
                    | {StopCategory.NEW_FUNDING}
                ),
                "reason": "MAX_LOSS_REACHED",
                "source": "SYSTEM_MAX_LOSS",
                "started_at": observed_at,
                "authorization_version_ref": activation.authorization_version_ref,
                "loss_latch_digest": updated_allocation.loss_latch_digest,
                "release_rules": {
                    "NEW_FUNDING": {
                        "user_releasable": False,
                        "requires": "ACTIVATION_CLOSURE",
                    },
                    "prior_release_rules": (
                        current_activation_stop.release_rules
                        if current_activation_stop is not None
                        else {}
                    ),
                },
            }
            max_loss_stop = StopStateVersion(
                **stop_fields,
                content_digest=content_digest(stop_fields),
            )
            self._capital.insert_stop_state(max_loss_stop)

        exiting = enter_exit(activation, observed_at=observed_at)
        if exiting.state_version != activation.state_version:
            self._planning.update_activation(
                exiting,
                expected_version=activation.state_version,
            )
        return exiting, updated_allocation, max_loss_stop

    def fix_and_activate(
        self,
        *,
        plan_id: str,
        expected_draft_version: int,
        plan_version_id: str,
        activation_id: str,
        authorization_version_id: str,
        allocation_id: str,
        capital_limit_version_id: str,
        quote_asset: str,
        build_digest: str,
        evidence_digest: str,
        evidence_scope: dict[str, object],
        observed_at: datetime,
    ) -> tuple[
        TradePlanVersion,
        PlanActivation,
        MachineAuthorizationVersion,
        PlanAllocation,
    ]:
        """Perform draft -> fixed -> activation inside the caller's transaction."""

        version = self.fix_draft(
            plan_id=plan_id,
            expected_draft_version=expected_draft_version,
            plan_version_id=plan_version_id,
            build_digest=build_digest,
            evidence_digest=evidence_digest,
            evidence_scope=evidence_scope,
            fixed_at=observed_at,
        )
        activation, authorization, allocation = self.activate_version(
            plan_version_id=plan_version_id,
            activation_id=activation_id,
            authorization_version_id=authorization_version_id,
            allocation_id=allocation_id,
            capital_limit_version_id=capital_limit_version_id,
            quote_asset=quote_asset,
            observed_at=observed_at,
        )
        return version, activation, authorization, allocation
