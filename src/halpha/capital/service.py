"""CAP public application boundary over the one exact-Decimal checker."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg import Connection

from halpha.capital.checks import check_action
from halpha.capital.models import (
    ActionCheckInput,
    AllocationStatus,
    AuthorityClass,
    CapDecision,
    EnvironmentKind,
    StopCategory,
    StopStateVersion,
)
from halpha.domain_values import content_digest
from halpha.capital.repository import PostgreSQLCapitalRepository


class CapitalApplicationService:
    def __init__(self, connection: Connection[Any], environment_id: str) -> None:
        self._capital = PostgreSQLCapitalRepository(connection, environment_id)
        self._environment_id = environment_id

    def check_current_action(self, action: ActionCheckInput) -> CapDecision:
        allocation = self._capital.get_allocation(action.activation_id, for_update=True)
        authorization = self._capital.get_authorization_for_activation(action.activation_id)
        account = self._capital.get_account_limit(allocation.capital_limit_version_ref)
        stop_states = self._capital.lock_current_stop_states(
            account_ref=action.account_ref,
            activation_id=action.activation_id,
        )
        return check_action(
            action,
            account=account,
            authorization=authorization,
            allocation=allocation,
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
                | {StopCategory.NEW_FUNDING}
            ),
            "reason": "EXTERNAL_ACTIVITY_DETECTED",
            "source": "SYSTEM_EXTERNAL_ACTIVITY",
            "started_at": observed_at,
            "authorization_version_ref": None,
            "loss_latch_digest": None,
            "release_rules": {
                "NEW_FUNDING": {
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

    def release_allocation_with_closure(
        self,
        *,
        activation_id: str,
        closure_digest: str,
        observed_at: datetime,
    ):
        if not closure_digest:
            raise ValueError("CLOSURE_UNPROVEN")
        allocation = self._capital.get_allocation(activation_id, for_update=True)
        if allocation.status is AllocationStatus.RELEASED:
            if allocation.closure_digest != closure_digest:
                raise ValueError("CLOSURE_CONFLICT")
            return allocation
        released = allocation.model_copy(
            update={
                "status": AllocationStatus.RELEASED,
                "closure_digest": closure_digest,
                "released_at": observed_at,
                "state_version": allocation.state_version + 1,
            }
        )
        self._capital.update_allocation(
            released,
            expected_version=allocation.state_version,
        )
        return released
