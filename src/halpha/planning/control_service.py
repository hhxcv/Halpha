"""Transactional handling of the five accepted B02 activation controls."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg import Connection

from halpha.capital.models import AllocationStatus, StopCategory, StopStateVersion
from halpha.capital.repository import PostgreSQLCapitalRepository
from halpha.domain_values import content_digest
from halpha.planning.models import PlanActivation
from halpha.planning.repository import PostgreSQLPlanningRepository
from halpha.planning.transitions import (
    ControlIntent,
    enter_exit,
    enter_user_takeover,
    resume_activation,
)
from halpha.user_workbench.commands import (
    Command,
    Receipt,
    ReceiptState,
    advance_receipt,
    initial_receipt,
)
from halpha.user_workbench.repository import CommandConflict, PostgreSQLCommandRepository


class ActivationControlService:
    def __init__(self, connection: Connection[Any], environment_id: str) -> None:
        self._planning = PostgreSQLPlanningRepository(connection, environment_id)
        self._capital = PostgreSQLCapitalRepository(connection, environment_id)
        self._commands = PostgreSQLCommandRepository(connection, environment_id)

    @staticmethod
    def _active_categories(states: tuple[StopStateVersion, ...]) -> frozenset[StopCategory]:
        return frozenset(category for state in states for category in state.stopped_categories)

    def _write_activation_stop_version(
        self,
        *,
        stop_state_version_id: str,
        states: tuple[StopStateVersion, ...],
        activation: PlanActivation,
        categories: frozenset[StopCategory],
        reason: str,
        observed_at: datetime,
    ) -> StopStateVersion:
        current = next((item for item in states if item.activation_id is not None), None)
        fields = {
            "stop_state_version_id": stop_state_version_id,
            "environment_id": activation.environment_id,
            "environment_kind": activation.environment_kind,
            "authority_class": activation.authority_class,
            "account_ref": activation.account_ref,
            "activation_id": activation.activation_id,
            "version": 1 if current is None else current.version + 1,
            "stopped_categories": categories,
            "reason": reason,
            "source": "USER",
            "started_at": observed_at,
            "authorization_version_ref": activation.authorization_version_ref,
            "release_rules": {"user_releasable": True},
        }
        state = StopStateVersion(**fields, content_digest=content_digest(fields))
        self._capital.insert_stop_state(state)
        return state

    def submit(
        self,
        command: Command,
        *,
        receipt_id: str,
        stop_state_version_id: str,
        reconciliation_digest: str | None = None,
        authorization_current: bool = True,
        facts_known: bool = True,
    ) -> Receipt:
        existing = self._commands.find_by_idempotency(
            command.owner_scope,
            command.idempotency_key,
            for_update=True,
        )
        if existing is not None:
            existing_command, existing_receipt = existing
            if existing_command.content_digest != command.content_digest:
                raise CommandConflict("COMMAND_CONTENT_CONFLICT")
            return existing_receipt
        receipt = initial_receipt(command, receipt_id=receipt_id, processing_owner="TRADEPLAN")
        self._commands.insert(command, receipt)

        activation = self._planning.get_activation(command.target_ref, for_update=True)
        if activation.state_version != command.expected_version:
            updated = advance_receipt(
                receipt,
                state=ReceiptState.REJECTED,
                reason_code="PLAN_VERSION_CONFLICT",
                result=None,
                pending_responsibility_refs=(),
                observed_at=command.submitted_at,
            )
            self._commands.update_receipt(updated, expected_version=receipt.state_version)
            return updated
        allocation = self._capital.get_allocation(activation.activation_id, for_update=True)
        states = self._capital.lock_current_stop_states(
            account_ref=activation.account_ref,
            activation_id=activation.activation_id,
        )
        active = self._active_categories(states)
        intent = command.intent
        pending: tuple[str, ...] = ()
        reason = "CONTROL_EFFECTIVE"
        receipt_state = ReceiptState.EFFECTIVE
        original_activation_version = activation.state_version
        original_allocation_version = allocation.state_version

        if intent is ControlIntent.STOP_NEW_RISK:
            current_activation = next(
                (item for item in states if item.activation_id == activation.activation_id),
                None,
            )
            categories = frozenset(
                set(current_activation.stopped_categories if current_activation else ())
                | {StopCategory.NEW_FUNDING}
            )
            self._write_activation_stop_version(
                stop_state_version_id=stop_state_version_id,
                states=states,
                activation=activation,
                categories=categories,
                reason="USER_STOP_NEW_RISK",
                observed_at=command.submitted_at,
            )
            if activation.pending_action_digest:
                receipt_state = ReceiptState.PROCESSING
                pending = ("OPEN_ENTRY_RESPONSIBILITIES_TERMINAL",)
                reason = "NEW_RISK_STOPPED_LOCALLY"
        elif intent is ControlIntent.RESUME_NEW_RISK:
            if (
                allocation.status is not AllocationStatus.HELD
                or allocation.max_loss_reached
                or activation.entry_opportunity_consumed
                or activation.lifecycle.value != "RUNNING"
            ):
                receipt_state = ReceiptState.REJECTED
                reason = "NEW_RISK_RESUME_NOT_ALLOWED"
            else:
                current_activation = next(
                    (item for item in states if item.activation_id == activation.activation_id),
                    None,
                )
                categories = frozenset(
                    set(current_activation.stopped_categories if current_activation else ())
                    - {StopCategory.NEW_FUNDING}
                )
                account_categories = frozenset(
                    category
                    for state in states
                    if state.activation_id is None
                    for category in state.stopped_categories
                )
                if StopCategory.NEW_FUNDING in account_categories or StopCategory.ALL_WRITES in active:
                    receipt_state = ReceiptState.REJECTED
                    reason = "ACTION_CATEGORY_STOPPED"
                else:
                    self._write_activation_stop_version(
                        stop_state_version_id=stop_state_version_id,
                        states=states,
                        activation=activation,
                        categories=categories,
                        reason="USER_RESUME_NEW_RISK",
                        observed_at=command.submitted_at,
                    )
        elif intent is ControlIntent.RESUME_ACTIVATION:
            if reconciliation_digest is None:
                receipt_state = ReceiptState.REJECTED
                reason = "RECONCILIATION_REQUIRED"
            else:
                try:
                    activation = resume_activation(
                        activation,
                        command_id=command.command_id,
                        reconciliation_digest=reconciliation_digest,
                        observed_at=command.submitted_at,
                        active_stop_categories=active,
                        authorization_current=authorization_current,
                        facts_known=facts_known,
                    )
                except ValueError as exc:
                    receipt_state = ReceiptState.REJECTED
                    reason = str(exc)
        elif intent is ControlIntent.EXIT_STRATEGY:
            activation = enter_exit(activation, observed_at=command.submitted_at)
            current_activation = next(
                (item for item in states if item.activation_id == activation.activation_id),
                None,
            )
            categories = frozenset(
                set(current_activation.stopped_categories if current_activation else ())
                | {StopCategory.NEW_FUNDING}
            )
            self._write_activation_stop_version(
                stop_state_version_id=stop_state_version_id,
                states=states,
                activation=activation,
                categories=categories,
                reason="EXIT_STRATEGY_STOP_NEW_RISK",
                observed_at=command.submitted_at,
            )
            allocation = allocation.model_copy(
                update={
                    "status": AllocationStatus.EXIT_ONLY,
                    "state_version": allocation.state_version + 1,
                }
            )
            receipt_state = ReceiptState.PROCESSING
            pending = ("EXIT_CLOSURE_DIGEST",)
            reason = "EXIT_RESPONSIBILITY_ACCEPTED"
        elif intent is ControlIntent.USER_TAKEOVER:
            activation = enter_user_takeover(
                activation,
                takeover_scope=command.scope,
                observed_at=command.submitted_at,
            )
            allocation = allocation.model_copy(
                update={
                    "status": AllocationStatus.TAKEOVER_HELD,
                    "state_version": allocation.state_version + 1,
                }
            )
            reason = "USER_TAKEOVER_PERSISTED"
        else:  # pragma: no cover - enum is closed
            raise ValueError("CONTROL_INTENT_UNSUPPORTED")

        if activation.state_version != original_activation_version:
            self._planning.update_activation(
                activation,
                expected_version=original_activation_version,
            )
        if allocation.state_version != original_allocation_version:
            self._capital.update_allocation(
                allocation,
                expected_version=original_allocation_version,
            )
        updated = advance_receipt(
            receipt,
            state=receipt_state,
            reason_code=reason,
            result={
                "activation_id": activation.activation_id,
                "activation_state_version": activation.state_version,
                "allocation_state": allocation.status.value,
            },
            pending_responsibility_refs=pending,
            observed_at=command.submitted_at,
        )
        self._commands.update_receipt(updated, expected_version=receipt.state_version)
        return updated
