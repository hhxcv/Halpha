"""TRADEPLAN's private PostgreSQL writer and read boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from halpha.planning.models import (
    PlanActivation,
    PlanEvent,
    TradePlanContent,
    TradePlanDraft,
    TradePlanVersion,
)
from halpha.planning.registry import FixedStrategyPlanBasis


class PlanningConflict(RuntimeError):
    pass


class PostgreSQLPlanningRepository:
    """Only this repository writes the four TRADEPLAN record families."""

    def __init__(self, connection: Connection[Any], environment_id: str) -> None:
        self._connection = connection
        self._environment_id = environment_id

    def save_draft(self, draft: TradePlanDraft, *, expected_version: int | None) -> None:
        if draft.environment_id != self._environment_id:
            raise PlanningConflict("PLAN_ENVIRONMENT_MISMATCH")
        if expected_version is None:
            cursor = self._connection.execute(
                """
                INSERT INTO halpha.trade_plan_draft (
                    plan_id, environment_id, draft_version, content_digest, content, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (
                    draft.plan_id,
                    draft.environment_id,
                    draft.draft_version,
                    draft.content_digest,
                    Jsonb(draft.content.model_dump(mode="json")),
                    draft.updated_at,
                ),
            )
        else:
            if draft.draft_version != expected_version + 1:
                raise PlanningConflict("PLAN_VERSION_CONFLICT")
            cursor = self._connection.execute(
                """
                UPDATE halpha.trade_plan_draft
                SET draft_version = %s, content_digest = %s, content = %s, updated_at = %s
                WHERE environment_id = %s AND plan_id = %s AND draft_version = %s
                """,
                (
                    draft.draft_version,
                    draft.content_digest,
                    Jsonb(draft.content.model_dump(mode="json")),
                    draft.updated_at,
                    draft.environment_id,
                    draft.plan_id,
                    expected_version,
                ),
            )
        if cursor.rowcount != 1:
            raise PlanningConflict("PLAN_VERSION_CONFLICT")

    def get_draft(self, plan_id: str, *, for_update: bool = False) -> TradePlanDraft:
        suffix = " FOR UPDATE" if for_update else ""
        row = self._connection.execute(
            """
            SELECT plan_id, environment_id, draft_version, content_digest, content, updated_at
            FROM halpha.trade_plan_draft
            WHERE environment_id = %s AND plan_id = %s
            """ + suffix,
            (self._environment_id, plan_id),
        ).fetchone()
        if row is None:
            raise PlanningConflict("PLAN_NOT_FOUND")
        return TradePlanDraft(
            plan_id=str(row[0]),
            environment_id=str(row[1]),
            draft_version=int(row[2]),
            content_digest=str(row[3]),
            content=TradePlanContent.model_validate(row[4]),
            updated_at=row[5],
        )

    def insert_version(self, version: TradePlanVersion) -> None:
        basis = version.strategy_basis
        self._connection.execute(
            """
            INSERT INTO halpha.trade_plan_version (
                plan_version_id, environment_id, plan_id, fixed_at,
                strategy_definition_ref, build_digest, parameter_schema_version,
                parameters, parameter_digest, account_ref, venue_ref, instrument_ref,
                direction, max_margin, max_notional, max_allowed_loss, terms,
                content_digest, fixed_strategy_basis
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                version.plan_version_id,
                version.environment_id,
                version.plan_id,
                version.fixed_at,
                f"{basis.strategy_id}@{basis.strategy_version}",
                basis.build_digest,
                basis.parameter_schema_version,
                Jsonb(basis.normalized_parameters),
                basis.parameter_digest,
                version.account_ref,
                version.venue_ref,
                version.instrument_ref,
                version.direction.value,
                version.requested_limits.max_margin,
                version.requested_limits.max_notional,
                version.requested_limits.max_allowed_loss,
                Jsonb(
                    {
                        **version.terms,
                        "target_exposure": version.target_exposure,
                        "valid_from": version.valid_from.isoformat(),
                        "valid_until": version.valid_until.isoformat(),
                        "allowed_actions": sorted(version.allowed_actions),
                    }
                ),
                version.content_digest,
                Jsonb(basis.model_dump(mode="json")),
            ),
        )

    def get_version(self, plan_version_id: str, *, for_update: bool = False) -> TradePlanVersion:
        suffix = " FOR UPDATE" if for_update else ""
        row = self._connection.execute(
            """
            SELECT plan_version_id, plan_id, environment_id, fixed_at,
                   fixed_strategy_basis, account_ref, venue_ref, instrument_ref,
                   direction, max_margin, max_notional, max_allowed_loss, terms,
                   content_digest
            FROM halpha.trade_plan_version
            WHERE environment_id = %s AND plan_version_id = %s
            """ + suffix,
            (self._environment_id, plan_version_id),
        ).fetchone()
        if row is None:
            raise PlanningConflict("PLAN_VERSION_NOT_FOUND")
        terms = dict(row[12])
        return TradePlanVersion(
            plan_version_id=str(row[0]),
            plan_id=str(row[1]),
            environment_id=str(row[2]),
            fixed_at=row[3],
            strategy_basis=FixedStrategyPlanBasis.model_validate(row[4]),
            account_ref=str(row[5]),
            venue_ref=str(row[6]),
            instrument_ref=str(row[7]),
            direction=str(row[8]),
            target_exposure=str(terms.pop("target_exposure")),
            requested_limits={
                "max_margin": str(row[9]),
                "max_notional": str(row[10]),
                "max_allowed_loss": str(row[11]),
            },
            valid_from=datetime.fromisoformat(str(terms.pop("valid_from"))),
            valid_until=datetime.fromisoformat(str(terms.pop("valid_until"))),
            allowed_actions=frozenset(terms.pop("allowed_actions")),
            terms=terms,
            content_digest=str(row[13]),
        )

    def insert_activation(self, activation: PlanActivation) -> None:
        self._connection.execute(
            """
            INSERT INTO halpha.plan_activation (
                activation_id, environment_id, environment_kind, authority_class,
                plan_version_ref, account_ref, instrument_ref, direction,
                strategy_id, framework_strategy_id,
                target_exposure,
                lifecycle, run_state, pause_reason, paused_at, reconciliation_digest,
                current_resume_command_ref, has_entry_fill, entry_opportunity_consumed,
                responsibility_owner, state_version, rule_state, pending_action_digest,
                protection_state, takeover_scope, latest_venue_cutoff, closure_digest,
                result_ref, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s
            )
            """,
            (
                activation.activation_id,
                activation.environment_id,
                activation.environment_kind.value,
                activation.authority_class.value,
                activation.plan_version_ref,
                activation.account_ref,
                activation.instrument_ref,
                activation.direction.value,
                activation.strategy_id,
                activation.framework_strategy_id,
                activation.target_exposure,
                activation.lifecycle.value,
                activation.run_state.value,
                activation.pause_reason,
                activation.paused_at,
                activation.reconciliation_digest,
                activation.current_resume_command_ref,
                activation.has_entry_fill,
                activation.entry_opportunity_consumed,
                activation.responsibility_owner,
                activation.state_version,
                Jsonb(activation.rule_state),
                activation.pending_action_digest,
                activation.protection_state.value,
                Jsonb(activation.takeover_scope) if activation.takeover_scope is not None else None,
                activation.latest_venue_cutoff,
                activation.closure_digest,
                activation.result_ref,
                activation.created_at,
                activation.updated_at,
            ),
        )

    def get_activation(
        self, activation_id: str, *, for_update: bool = False
    ) -> PlanActivation:
        suffix = " FOR UPDATE" if for_update else ""
        row = self._connection.execute(
            """
            SELECT activation_id, environment_id, environment_kind, authority_class,
                   plan_version_ref, account_ref, instrument_ref, direction, strategy_id,
                   framework_strategy_id, target_exposure, lifecycle, run_state,
                   pause_reason, paused_at, reconciliation_digest,
                   current_resume_command_ref, has_entry_fill,
                   entry_opportunity_consumed, responsibility_owner, state_version,
                   rule_state, pending_action_digest, protection_state,
                   takeover_scope, latest_venue_cutoff, closure_digest, result_ref,
                   created_at, updated_at
            FROM halpha.plan_activation
            WHERE environment_id = %s AND activation_id = %s
            """ + suffix,
            (self._environment_id, activation_id),
        ).fetchone()
        if row is None:
            raise PlanningConflict("ACTIVATION_NOT_FOUND")
        return PlanActivation(
            activation_id=str(row[0]),
            environment_id=str(row[1]),
            environment_kind=str(row[2]),
            authority_class=str(row[3]),
            plan_version_ref=str(row[4]),
            account_ref=str(row[5]),
            instrument_ref=str(row[6]),
            direction=str(row[7]),
            strategy_id=str(row[8]),
            framework_strategy_id=str(row[9]),
            target_exposure=str(row[10]),
            lifecycle=str(row[11]),
            run_state=str(row[12]),
            pause_reason=str(row[13]) if row[13] is not None else None,
            paused_at=row[14],
            reconciliation_digest=str(row[15]) if row[15] is not None else None,
            current_resume_command_ref=str(row[16]) if row[16] is not None else None,
            has_entry_fill=bool(row[17]),
            entry_opportunity_consumed=bool(row[18]),
            responsibility_owner=str(row[19]),
            state_version=int(row[20]),
            rule_state=dict(row[21]),
            pending_action_digest=str(row[22]) if row[22] is not None else None,
            protection_state=str(row[23]),
            takeover_scope=dict(row[24]) if row[24] is not None else None,
            latest_venue_cutoff=row[25],
            closure_digest=str(row[26]) if row[26] is not None else None,
            result_ref=str(row[27]) if row[27] is not None else None,
            created_at=row[28],
            updated_at=row[29],
        )

    def list_open_activations(self) -> tuple[PlanActivation, ...]:
        rows = self._connection.execute(
            """
            SELECT activation_id
            FROM halpha.plan_activation
            WHERE environment_id = %s
              AND lifecycle NOT IN ('COMPLETED', 'USER_TAKEOVER')
            ORDER BY created_at, activation_id
            """,
            (self._environment_id,),
        ).fetchall()
        return tuple(self.get_activation(str(row[0])) for row in rows)

    def update_activation(self, activation: PlanActivation, *, expected_version: int) -> None:
        cursor = self._connection.execute(
            """
            UPDATE halpha.plan_activation
            SET lifecycle = %s, run_state = %s, pause_reason = %s, paused_at = %s,
                reconciliation_digest = %s, current_resume_command_ref = %s,
                has_entry_fill = %s, entry_opportunity_consumed = %s,
                responsibility_owner = %s, state_version = %s, rule_state = %s,
                pending_action_digest = %s, protection_state = %s, takeover_scope = %s,
                latest_venue_cutoff = %s, closure_digest = %s, result_ref = %s,
                updated_at = %s
            WHERE environment_id = %s AND activation_id = %s AND state_version = %s
            """,
            (
                activation.lifecycle.value,
                activation.run_state.value,
                activation.pause_reason,
                activation.paused_at,
                activation.reconciliation_digest,
                activation.current_resume_command_ref,
                activation.has_entry_fill,
                activation.entry_opportunity_consumed,
                activation.responsibility_owner,
                activation.state_version,
                Jsonb(activation.rule_state),
                activation.pending_action_digest,
                activation.protection_state.value,
                Jsonb(activation.takeover_scope) if activation.takeover_scope is not None else None,
                activation.latest_venue_cutoff,
                activation.closure_digest,
                activation.result_ref,
                activation.updated_at,
                activation.environment_id,
                activation.activation_id,
                expected_version,
            ),
        )
        if cursor.rowcount != 1:
            raise PlanningConflict("PLAN_VERSION_CONFLICT")

    def pause_all_open_for_writer_continuity_loss(self, observed_at: datetime) -> int:
        cursor = self._connection.execute(
            """
            UPDATE halpha.plan_activation
            SET run_state = 'PAUSED', pause_reason = 'WRITER_CONTINUITY_LOST',
                paused_at = %s, reconciliation_digest = NULL,
                current_resume_command_ref = NULL, state_version = state_version + 1,
                updated_at = %s
            WHERE environment_id = %s
              AND lifecycle NOT IN ('COMPLETED', 'USER_TAKEOVER')
              AND run_state <> 'PAUSED'
            """,
            (observed_at, observed_at, self._environment_id),
        )
        return int(cursor.rowcount)

    def find_event_by_source(
        self, activation_id: str, source_identity: str
    ) -> PlanEvent | None:
        row = self._connection.execute(
            """
            SELECT plan_event_id, environment_id, activation_id, rule_id,
                   source_identity, source_cutoff, input_digest, reason_code,
                   condition_judgement, proposed_action, no_action_reason,
                   capital_decision, capital_decision_digest, created_at, content_digest
            FROM halpha.plan_event
            WHERE environment_id = %s AND activation_id = %s AND source_identity = %s
            """,
            (self._environment_id, activation_id, source_identity),
        ).fetchone()
        if row is None:
            return None
        return PlanEvent(
            plan_event_id=str(row[0]),
            environment_id=str(row[1]),
            activation_id=str(row[2]),
            rule_id=str(row[3]),
            source_identity=str(row[4]),
            source_cutoff=row[5],
            input_digest=str(row[6]),
            reason_code=str(row[7]),
            condition_judgement=row[8],
            proposed_action=row[9],
            no_action_reason=row[10],
            capital_decision=dict(row[11]),
            capital_decision_digest=str(row[12]),
            created_at=row[13],
            content_digest=str(row[14]),
        )

    def insert_event(self, event: PlanEvent) -> None:
        self._connection.execute(
            """
            INSERT INTO halpha.plan_event (
                plan_event_id, environment_id, activation_id, rule_id,
                source_identity, source_cutoff, input_digest, reason_code,
                condition_judgement, proposed_action, no_action_reason,
                capital_decision, capital_decision_digest, created_at, content_digest
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                event.plan_event_id,
                event.environment_id,
                event.activation_id,
                event.rule_id,
                event.source_identity,
                event.source_cutoff,
                event.input_digest,
                event.reason_code,
                Jsonb(event.condition_judgement.model_dump(mode="json")) if event.condition_judgement else None,
                Jsonb(event.proposed_action.model_dump(mode="json")) if event.proposed_action else None,
                event.no_action_reason,
                Jsonb(event.capital_decision),
                event.capital_decision_digest,
                event.created_at,
                event.content_digest,
            ),
        )
