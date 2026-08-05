"""Stable identities and immutable values for the control commands."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from halpha.domain_values import content_digest
from halpha.planning.transitions import ControlIntent


class ReceiptState(StrEnum):
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    EFFECTIVE = "EFFECTIVE"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command_id: str
    environment_id: str
    owner_scope: str
    idempotency_key: str
    target_kind: str = "PLAN_ACTIVATION"
    target_ref: str
    expected_version: int
    intent: ControlIntent
    scope: dict[str, Any]
    parameters: dict[str, Any]
    submitted_at: datetime
    content_digest: str

    @model_validator(mode="after")
    def digest_is_valid(self) -> Command:
        payload = self.model_dump(mode="python", exclude={"content_digest"})
        if content_digest(payload) != self.content_digest:
            raise ValueError("COMMAND_CONTENT_CONFLICT")
        if self.expected_version <= 0:
            raise ValueError("VERSION_CONFLICT")
        return self


class Receipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    receipt_id: str
    environment_id: str
    command_id: str
    processing_owner: str
    state: ReceiptState
    state_version: int
    reason_code: str | None
    result: dict[str, Any] | None
    pending_responsibility_refs: tuple[str, ...]
    content_digest: str
    created_at: datetime
    updated_at: datetime


def build_command(
    *,
    command_id: str,
    environment_id: str,
    owner_scope: str,
    idempotency_key: str,
    activation_id: str,
    expected_version: int,
    intent: ControlIntent,
    scope: dict[str, Any],
    parameters: dict[str, Any],
    submitted_at: datetime,
) -> Command:
    fields = {
        "command_id": command_id,
        "environment_id": environment_id,
        "owner_scope": owner_scope,
        "idempotency_key": idempotency_key,
        "target_kind": "PLAN_ACTIVATION",
        "target_ref": activation_id,
        "expected_version": expected_version,
        "intent": intent,
        "scope": scope,
        "parameters": parameters,
        "submitted_at": submitted_at,
    }
    return Command(**fields, content_digest=content_digest(fields))


def initial_receipt(
    command: Command,
    *,
    receipt_id: str,
    processing_owner: str,
) -> Receipt:
    fields = {
        "receipt_id": receipt_id,
        "environment_id": command.environment_id,
        "command_id": command.command_id,
        "processing_owner": processing_owner,
        "state": ReceiptState.RECEIVED,
        "state_version": 1,
        "reason_code": None,
        "result": None,
        "pending_responsibility_refs": (),
        "created_at": command.submitted_at,
        "updated_at": command.submitted_at,
    }
    return Receipt(**fields, content_digest=content_digest(fields))


def advance_receipt(
    receipt: Receipt,
    *,
    state: ReceiptState,
    reason_code: str | None,
    result: dict[str, Any] | None,
    pending_responsibility_refs: tuple[str, ...],
    observed_at: datetime,
) -> Receipt:
    fields = {
        **receipt.model_dump(mode="python"),
        "state": state,
        "state_version": receipt.state_version + 1,
        "reason_code": reason_code,
        "result": result,
        "pending_responsibility_refs": pending_responsibility_refs,
        "updated_at": observed_at,
    }
    fields.pop("content_digest")
    return Receipt(**fields, content_digest=content_digest(fields))
