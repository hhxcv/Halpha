"""Immutable DAT/EXE values; PostgreSQL remains the recovery authority."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from halpha.capital.models import AuthorityClass, EnvironmentKind, RiskClass
from halpha.domain_values import content_digest


_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_UUID32 = re.compile(r"^[0-9a-f]{32}$")


class ExecutionProfileRef(StrEnum):
    BINANCE_DEMO = "BINANCE_DEMO"
    BINANCE_LIVE_WRITE = "BINANCE_LIVE_WRITE"


class ExecutionActionKind(StrEnum):
    ENTRY = "ENTRY"
    CANCEL = "CANCEL"
    PROTECTION = "PROTECTION"
    TAKE_PROFIT = "TAKE_PROFIT"
    RISK_REDUCTION = "RISK_REDUCTION"
    EXIT = "EXIT"


class ExecutionActionState(StrEnum):
    READY = "READY"
    NOT_SUBMITTED = "NOT_SUBMITTED"
    SUBMITTING = "SUBMITTING"
    SUBMITTED_UNKNOWN = "SUBMITTED_UNKNOWN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    WORKING = "WORKING"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    RECONCILED = "RECONCILED"
    HANDED_OVER = "HANDED_OVER"


class VenueFactKind(StrEnum):
    CLOSED_BAR = "CLOSED_BAR"
    MARK_PRICE = "MARK_PRICE"
    TOP_OF_BOOK = "TOP_OF_BOOK"
    INSTRUMENT_RULES = "INSTRUMENT_RULES"
    ACCOUNT_STATE = "ACCOUNT_STATE"
    ORDER_STATE = "ORDER_STATE"
    FILL = "FILL"
    COMMISSION = "COMMISSION"
    FUNDING = "FUNDING"
    POSITION_STATE = "POSITION_STATE"


class VenueFactSourceClass(StrEnum):
    VENUE_QUERY = "VENUE_QUERY"
    VENUE_STREAM = "VENUE_STREAM"
    FRAMEWORK_DERIVED = "FRAMEWORK_DERIVED"
    EXTERNAL_UNCLAIMED = "EXTERNAL_UNCLAIMED"


class VenueFactAttributionClass(StrEnum):
    HALPHA_EXECUTION = "HALPHA_EXECUTION"
    USER_TAKEOVER = "USER_TAKEOVER"


class VenueModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ExecutionAction(VenueModel):
    execution_action_id: str
    environment_id: str
    environment_kind: EnvironmentKind
    authority_class: AuthorityClass
    execution_profile_ref: ExecutionProfileRef
    account_ref: str
    activation_id: str
    plan_event_ref: str
    source_identity: str
    action_kind: ExecutionActionKind
    action_class: RiskClass
    action_terms: dict[str, Any]
    action_terms_digest: str
    capital_decision_digest: str
    client_order_id: str | None
    cancel_target: dict[str, Any] | None
    state: ExecutionActionState
    state_version: int
    state_digest: str
    request_digest: str | None = None
    call_started_at: datetime | None = None
    call_completed_at: datetime | None = None
    venue_order_refs: tuple[str, ...] = ()
    venue_fact_refs: tuple[str, ...] = ()
    unknown_reason: str | None = None
    next_query_at: datetime | None = None
    not_submitted_reason: str | None = None
    protection_digest: str | None = None
    closure_evidence_digest: str | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator(
        "action_terms_digest",
        "capital_decision_digest",
        "state_digest",
        "request_digest",
        "protection_digest",
        "closure_evidence_digest",
    )
    @classmethod
    def digests_are_sha256(cls, value: str | None) -> str | None:
        if value is not None and _DIGEST.fullmatch(value) is None:
            raise ValueError("EXECUTION_ACTION_DIGEST_INVALID")
        return value

    @field_validator("created_at", "updated_at", "call_started_at", "call_completed_at", "next_query_at")
    @classmethod
    def timestamps_are_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("EXECUTION_ACTION_TIMEZONE_REQUIRED")
        return value

    @model_validator(mode="after")
    def invariants_hold(self) -> ExecutionAction:
        expected_authority = (
            AuthorityClass.DEMO_VALIDATION
            if self.environment_kind is EnvironmentKind.DEMO
            else AuthorityClass.LIVE_REAL_CAPITAL
        )
        expected_profile = (
            ExecutionProfileRef.BINANCE_DEMO
            if self.environment_kind is EnvironmentKind.DEMO
            else ExecutionProfileRef.BINANCE_LIVE_WRITE
        )
        if self.authority_class is not expected_authority:
            raise ValueError("AUTHORIZATION_MISMATCH")
        if self.execution_profile_ref is not expected_profile:
            raise ValueError("EXECUTION_PROFILE_MISMATCH")
        if self.state_version <= 0:
            raise ValueError("EXECUTION_ACTION_VERSION_INVALID")
        if self.updated_at < self.created_at:
            raise ValueError("EXECUTION_ACTION_TIME_REGRESSION")
        if self.action_terms_digest != content_digest(self.action_terms):
            raise ValueError("DUPLICATE_IDENTITY_CONFLICT")
        if self.action_kind is ExecutionActionKind.CANCEL:
            if self.client_order_id is not None or self.cancel_target is None:
                raise ValueError("CANCEL_TARGET_INVALID")
        elif self.client_order_id is None or _UUID32.fullmatch(self.client_order_id) is None:
            raise ValueError("CLIENT_ORDER_ID_INVALID")
        if self.action_kind is not ExecutionActionKind.CANCEL and self.cancel_target is not None:
            raise ValueError("CANCEL_TARGET_INVALID")

        called_states = {
            ExecutionActionState.SUBMITTING,
            ExecutionActionState.SUBMITTED_UNKNOWN,
            ExecutionActionState.ACKNOWLEDGED,
            ExecutionActionState.WORKING,
            ExecutionActionState.PARTIALLY_FILLED,
            ExecutionActionState.FILLED,
            ExecutionActionState.CANCELLED,
            ExecutionActionState.REJECTED,
            ExecutionActionState.EXPIRED,
            ExecutionActionState.RECONCILED,
        }
        if self.state in called_states:
            if self.request_digest is None or self.call_started_at is None:
                raise ValueError("CALL_EVIDENCE_REQUIRED")
        elif self.state is ExecutionActionState.NOT_SUBMITTED:
            if (self.request_digest is None) != (self.call_started_at is None):
                raise ValueError("CALL_EVIDENCE_INCOMPLETE")
        elif self.request_digest is not None or self.call_started_at is not None:
            raise ValueError("CALL_EVIDENCE_FORBIDDEN")
        if self.call_completed_at is not None:
            if self.call_started_at is None or self.call_completed_at < self.call_started_at:
                raise ValueError("CALL_COMPLETION_INVALID")
        if self.state is ExecutionActionState.SUBMITTED_UNKNOWN:
            if self.unknown_reason is None or self.next_query_at is None:
                raise ValueError("SUBMISSION_UNKNOWN_EVIDENCE_REQUIRED")
        elif self.unknown_reason is not None or self.next_query_at is not None:
            raise ValueError("SUBMISSION_UNKNOWN_EVIDENCE_FORBIDDEN")
        if self.state is ExecutionActionState.NOT_SUBMITTED:
            if not self.not_submitted_reason:
                raise ValueError("NOT_SUBMITTED_REASON_REQUIRED")
        elif self.not_submitted_reason is not None:
            raise ValueError("NOT_SUBMITTED_REASON_FORBIDDEN")
        if self.state is ExecutionActionState.RECONCILED and self.closure_evidence_digest is None:
            raise ValueError("CLOSURE_UNPROVEN")
        if execution_action_state_digest(self) != self.state_digest:
            raise ValueError("EXECUTION_ACTION_STATE_DIGEST_INVALID")
        return self


def execution_action_state_digest(action: ExecutionAction | dict[str, Any]) -> str:
    values = (
        action.model_dump(mode="python", exclude={"state_digest"})
        if isinstance(action, ExecutionAction)
        else {key: value for key, value in action.items() if key != "state_digest"}
    )
    if values.get("not_submitted_reason") is None:
        values.pop("not_submitted_reason", None)
    return content_digest(values)


class VenueFact(VenueModel):
    venue_fact_id: str
    environment_id: str
    venue_ref: str
    account_ref: str | None = None
    instrument_ref: str | None = None
    kind: VenueFactKind
    source_class: VenueFactSourceClass
    source_object_id: str | None = None
    source_sequence: str | None = None
    source_time: datetime | None = None
    received_at: datetime
    cutoff: datetime
    schema_version: int = 1
    content_digest: str
    payload: dict[str, Any]
    activation_ref: str | None = None
    action_ref: str | None = None
    attribution_digest: str | None = None
    attribution_class: VenueFactAttributionClass | None = None
    handover_command_ref: str | None = None
    supersedes_ref: str | None = None
    correction_reason: str | None = None
    correction_evidence_refs: tuple[str, ...] | None = None
    correction_effective_time: datetime | None = None
    impact_scope: dict[str, Any] | None = None
    affected_reference_refs: tuple[str, ...] | None = None

    @field_validator("content_digest", "attribution_digest")
    @classmethod
    def fact_digests_are_sha256(cls, value: str | None) -> str | None:
        if value is not None and _DIGEST.fullmatch(value) is None:
            raise ValueError("VENUE_FACT_DIGEST_INVALID")
        return value

    @field_validator("source_time", "received_at", "cutoff", "correction_effective_time")
    @classmethod
    def fact_timestamps_are_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("VENUE_FACT_TIMEZONE_REQUIRED")
        return value

    @model_validator(mode="after")
    def fact_invariants_hold(self) -> VenueFact:
        if self.schema_version <= 0:
            raise ValueError("VENUE_FACT_SCHEMA_INVALID")
        if self.source_object_id is None or self.source_sequence is None:
            raise ValueError("VENUE_FACT_SOURCE_IDENTITY_REQUIRED")
        if self.cutoff > self.received_at:
            raise ValueError("VENUE_FACT_CUTOFF_INVALID")
        if self.content_digest != venue_fact_content_digest(self):
            raise ValueError("VENUE_FACT_CONTENT_DIGEST_INVALID")
        if self.attribution_class is None:
            if any(
                value is not None
                for value in (
                    self.activation_ref,
                    self.action_ref,
                    self.attribution_digest,
                    self.handover_command_ref,
                )
            ):
                raise ValueError("VENUE_FACT_ATTRIBUTION_INVALID")
        elif self.attribution_class is VenueFactAttributionClass.HALPHA_EXECUTION:
            if (
                self.activation_ref is None
                or self.action_ref is None
                or self.attribution_digest is None
                or self.handover_command_ref is not None
            ):
                raise ValueError("VENUE_FACT_ATTRIBUTION_INVALID")
        elif (
            self.activation_ref is None
            or self.action_ref is not None
            or self.attribution_digest is None
            or self.handover_command_ref is None
        ):
            raise ValueError("VENUE_FACT_ATTRIBUTION_INVALID")
        correction_values = (
            self.correction_reason,
            self.correction_effective_time,
        )
        if self.supersedes_ref is None and any(value is not None for value in correction_values):
            raise ValueError("VENUE_FACT_CORRECTION_INVALID")
        if self.supersedes_ref is not None and any(value is None for value in correction_values):
            raise ValueError("VENUE_FACT_CORRECTION_INVALID")
        return self


def venue_fact_content_digest(fact: VenueFact | dict[str, Any]) -> str:
    values = fact.model_dump(mode="python") if isinstance(fact, VenueFact) else dict(fact)
    return content_digest(
        {
            key: values.get(key)
            for key in (
                "environment_id",
                "venue_ref",
                "account_ref",
                "instrument_ref",
                "kind",
                "source_class",
                "source_object_id",
                "source_sequence",
                "source_time",
                "received_at",
                "cutoff",
                "schema_version",
                "payload",
            )
        }
    )
