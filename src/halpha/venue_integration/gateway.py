"""Private persisted-action gate in front of the qualified venue client."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import uuid4

from halpha.venue_integration.models import (
    ExecutionAction,
    ExecutionActionKind,
    ExecutionActionState,
)
from halpha.venue_integration.repository import PostgreSQLExecutionActionRepository


@dataclass(frozen=True, slots=True)
class VenueCallReceipt:
    source_object_id: str
    source_sequence: str
    source_time: datetime | None
    status: str
    payload: dict[str, Any]


class VenueExecutionClient(Protocol):
    """One qualified client implementation/factory path for both profiles."""

    def submit_order(self, action: ExecutionAction) -> VenueCallReceipt: ...

    def cancel_order(self, action: ExecutionAction) -> VenueCallReceipt: ...

    def query_order(self, action: ExecutionAction) -> VenueCallReceipt: ...


class VenueDefinitelyNotSubmitted(RuntimeError):
    """The qualified client proves no venue write was entered."""


class VenueSubmissionUncertain(RuntimeError):
    """The client cannot prove whether the stable identity reached the venue."""


@dataclass(frozen=True, slots=True)
class PersistedActionPermit:
    action_id: str
    state_digest: str
    nonce: str


class PersistedActionGate:
    """Fail-closed single-use gate; permits do not survive process restart."""

    def __init__(
        self,
        repository: PostgreSQLExecutionActionRepository,
        client: VenueExecutionClient,
        *,
        environment_id: str,
        execution_profile_ref: str,
        account_ref: str,
    ) -> None:
        self._repository = repository
        self._client = client
        self._environment_id = environment_id
        self._execution_profile_ref = execution_profile_ref
        self._account_ref = account_ref
        self._permits: dict[str, PersistedActionPermit] = {}

    def authorize_committed_submission(
        self,
        execution_action_id: str,
        *,
        expected_state_digest: str,
    ) -> PersistedActionPermit:
        action = self._repository.get(execution_action_id)
        self._require_identity(action)
        if (
            action.state is not ExecutionActionState.SUBMITTING
            or action.state_digest != expected_state_digest
            or action.request_digest is None
        ):
            raise RuntimeError("SUBMISSION_RESULT_UNKNOWN")
        if execution_action_id in self._permits:
            raise RuntimeError("DUPLICATE_IDENTITY_CONFLICT")
        permit = PersistedActionPermit(
            action_id=execution_action_id,
            state_digest=expected_state_digest,
            nonce=uuid4().hex,
        )
        self._permits[execution_action_id] = permit
        return permit

    def execute_once(self, permit: PersistedActionPermit) -> VenueCallReceipt:
        registered = self._permits.pop(permit.action_id, None)
        if registered != permit:
            raise RuntimeError("SUBMISSION_RESULT_UNKNOWN")
        action = self._repository.get(permit.action_id)
        self._require_identity(action)
        if (
            action.state is not ExecutionActionState.SUBMITTING
            or action.state_digest != permit.state_digest
        ):
            raise RuntimeError("SUBMISSION_RESULT_UNKNOWN")
        if action.action_kind is ExecutionActionKind.CANCEL:
            return self._client.cancel_order(action)
        return self._client.submit_order(action)

    def query_original_identity(self, execution_action_id: str) -> VenueCallReceipt:
        action = self._repository.get(execution_action_id)
        self._require_identity(action)
        if action.state not in {
            ExecutionActionState.SUBMITTING,
            ExecutionActionState.UNKNOWN,
            ExecutionActionState.OPEN,
        }:
            raise RuntimeError("NOT_SUBMITTED")
        return self._client.query_order(action)

    def _require_identity(self, action: ExecutionAction) -> None:
        if (
            action.environment_id != self._environment_id
            or action.execution_profile_ref.value != self._execution_profile_ref
            or action.account_ref != self._account_ref
        ):
            raise RuntimeError("AUTHORIZATION_MISMATCH")
