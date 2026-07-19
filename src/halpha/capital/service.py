"""CAP public application boundary over the one exact-Decimal checker."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg import Connection

from halpha.capital.checks import check_action
from halpha.capital.models import (
    ActivationCapitalBoundary,
    ActionCheckInput,
    AuthorityClass,
    CapDecision,
    EnvironmentKind,
    StopCategory,
    StopStateVersion,
)
from halpha.domain_values import content_digest
from halpha.capital.repository import PostgreSQLCapitalRepository
from halpha.planning.repository import PostgreSQLPlanningRepository


class CapitalApplicationService:
    def __init__(self, connection: Connection[Any], environment_id: str) -> None:
        self._capital = PostgreSQLCapitalRepository(connection, environment_id)
        self._planning = PostgreSQLPlanningRepository(connection, environment_id)
        self._environment_id = environment_id

    def get_plan_boundary(
        self,
        activation_id: str,
        *,
        for_update: bool = False,
    ) -> ActivationCapitalBoundary:
        activation = self._planning.get_activation(activation_id, for_update=for_update)
        version = self._planning.get_version(activation.plan_version_ref)
        capital_state = activation.rule_state.get("capital", {})
        if not isinstance(capital_state, dict):
            capital_state = {}
        return ActivationCapitalBoundary(
            activation_id=activation.activation_id,
            environment_id=activation.environment_id,
            environment_kind=activation.environment_kind,
            authority_class=activation.authority_class,
            account_ref=activation.account_ref,
            instrument_ref=activation.instrument_ref,
            valid_from=version.valid_from,
            valid_until=version.valid_until,
            allowed_actions=version.allowed_actions,
            max_margin=version.requested_limits.max_margin,
            max_notional=version.requested_limits.max_notional,
            max_allowed_loss=version.requested_limits.max_allowed_loss,
            activation_loss=str(capital_state.get("activation_loss", "0")),
            lifecycle=activation.lifecycle.value,
            responsibility_owner=activation.responsibility_owner,
        )

    def check_current_action(self, action: ActionCheckInput) -> CapDecision:
        boundary = self.get_plan_boundary(action.activation_id, for_update=True)
        stop_states = self._capital.lock_current_stop_states(
            account_ref=action.account_ref,
            activation_id=action.activation_id,
        )
        return check_action(
            action,
            boundary=boundary,
            stop_states=stop_states,
        )

    def stop_new_risk_for_external_activity(
        self,
        *,
        stop_state_version_id: str,
        environment_kind: EnvironmentKind,
        authority_class: AuthorityClass,
        account_ref: str,
        evidence_digest: str,
        observed_at: datetime,
    ) -> StopStateVersion:
        states = self._capital.lock_current_stop_states(
            account_ref=account_ref,
            activation_id="",
        )
        current = next((state for state in states if state.activation_id is None), None)
        if (
            current is not None
            and current.source == "SYSTEM_EXTERNAL_ACTIVITY"
            and current.release_rules.get("evidence_digest") == evidence_digest
        ):
            return current
        fields = {
            "stop_state_version_id": stop_state_version_id,
            "environment_id": self._environment_id,
            "environment_kind": environment_kind,
            "authority_class": authority_class,
            "account_ref": account_ref,
            "activation_id": None,
            "version": 1 if current is None else current.version + 1,
            "stopped_categories": frozenset(
                set(current.stopped_categories if current is not None else ())
                | {StopCategory.NEW_RISK}
            ),
            "reason": "EXTERNAL_ACTIVITY_DETECTED",
            "source": "SYSTEM_EXTERNAL_ACTIVITY",
            "started_at": observed_at,
            "loss_latch_digest": None,
            "release_rules": {
                "NEW_RISK": {
                    "user_releasable": False,
                    "requires": "EXTERNAL_ACTIVITY_RESOLUTION_OR_USER_TAKEOVER",
                },
                "evidence_digest": evidence_digest,
                "prior_release_rules": (
                    current.release_rules if current is not None else {}
                ),
            },
        }
        state = StopStateVersion(**fields, content_digest=content_digest(fields))
        self._capital.insert_stop_state(state)
        return state
