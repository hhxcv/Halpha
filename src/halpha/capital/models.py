"""Immutable inputs and results for stateless capital checks."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from halpha.domain_values import canonical_decimal, decimal_from_string


_DIGEST = re.compile(r"^[0-9a-f]{64}$")
ACCOUNT_SYSTEM_STOP_RELEASE_EVIDENCE_MAX_AGE = timedelta(seconds=65)


class EnvironmentKind(StrEnum):
    DEMO = "DEMO"
    LIVE = "LIVE"


class AuthorityClass(StrEnum):
    DEMO_VALIDATION = "DEMO_VALIDATION"
    LIVE_REAL_CAPITAL = "LIVE_REAL_CAPITAL"
    NO_TRADING_AUTHORITY = "NO_TRADING_AUTHORITY"


class RiskClass(StrEnum):
    RISK_INCREASING = "RISK_INCREASING"
    RISK_NEUTRAL = "RISK_NEUTRAL"
    RISK_REDUCING = "RISK_REDUCING"
    AMBIGUOUS = "AMBIGUOUS"


class StopCategory(StrEnum):
    NEW_RISK = "NEW_RISK"
    PROTECTION = "PROTECTION"
    RISK_REDUCTION_OR_ORDER_MANAGEMENT = "RISK_REDUCTION_OR_ORDER_MANAGEMENT"
    ALL_EXCHANGE_CHANGES = "ALL_EXCHANGE_CHANGES"


class AccountSystemStopSource(StrEnum):
    EXTERNAL_ACTIVITY = "SYSTEM_EXTERNAL_ACTIVITY"
    ATTRIBUTED_ACTION_ANOMALY = "SYSTEM_ATTRIBUTED_ACTION_ANOMALY"


class CapModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EnvironmentAuthority(CapModel):
    environment_id: str
    environment_kind: EnvironmentKind
    authority_class: AuthorityClass

    @model_validator(mode="after")
    def authority_matches_environment(self) -> EnvironmentAuthority:
        expected = (
            AuthorityClass.DEMO_VALIDATION
            if self.environment_kind is EnvironmentKind.DEMO
            else AuthorityClass.LIVE_REAL_CAPITAL
        )
        if self.authority_class is not expected:
            raise ValueError("AUTHORITY_ENVIRONMENT_MISMATCH")
        return self


class ActivationCapitalBoundary(EnvironmentAuthority):
    """Current plan and activation fields used by one action check."""

    activation_id: str
    account_ref: str
    instrument_ref: str
    valid_from: datetime
    valid_until: datetime
    allowed_actions: frozenset[str]
    max_margin: str
    max_notional: str
    max_allowed_loss: str
    lifecycle: str
    responsibility_owner: str

    @field_validator("max_margin", "max_notional", "max_allowed_loss")
    @classmethod
    def amounts_are_non_negative(cls, value: str) -> str:
        return canonical_decimal(
            decimal_from_string(value, code="PLAN_CAPITAL_BOUNDARY_INVALID", non_negative=True)
        )

    @model_validator(mode="after")
    def window_is_valid(self) -> "ActivationCapitalBoundary":
        if self.valid_until <= self.valid_from:
            raise ValueError("PLAN_WINDOW_INVALID")
        if not self.allowed_actions:
            raise ValueError("PLAN_ACTIONS_EMPTY")
        return self


class StopStateVersion(EnvironmentAuthority):
    stop_state_version_id: str
    account_ref: str
    activation_id: str | None
    version: int
    stopped_categories: frozenset[StopCategory]
    reason: str
    source: str
    started_at: datetime
    loss_latch_digest: str | None = None
    release_rules: dict[str, Any]
    content_digest: str


class AccountSystemStopReleaseRequest(EnvironmentAuthority):
    new_stop_state_version_id: str
    account_ref: str
    resolution_activation_id: str
    expected_version: int
    expected_stop_content_digest: str
    expected_source: AccountSystemStopSource
    reconciliation_digest: str
    resolution_evidence_digest: str
    reconciliation_observed_at: datetime
    submitted_at: datetime
    resolution_status: Literal["NO_UNRESOLVED_ACCOUNT_STOP_CAUSE"]
    confirmation: Literal["USER_CONFIRMED_SYSTEM_STOP_RELEASE"]

    @field_validator(
        "expected_stop_content_digest",
        "reconciliation_digest",
        "resolution_evidence_digest",
    )
    @classmethod
    def digests_are_sha256(cls, value: str) -> str:
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("SYSTEM_STOP_RELEASE_DIGEST_INVALID")
        return value

    @field_validator("reconciliation_observed_at", "submitted_at")
    @classmethod
    def timestamps_are_aware(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("SYSTEM_STOP_RELEASE_TIMEZONE_REQUIRED")
        return value

    @model_validator(mode="after")
    def release_evidence_is_current(self) -> "AccountSystemStopReleaseRequest":
        if self.expected_version <= 0:
            raise ValueError("SYSTEM_STOP_RELEASE_VERSION_INVALID")
        if (
            not self.new_stop_state_version_id
            or not self.account_ref
            or not self.resolution_activation_id
        ):
            raise ValueError("SYSTEM_STOP_RELEASE_IDENTITY_INVALID")
        if (
            self.reconciliation_observed_at > self.submitted_at
            or self.submitted_at - self.reconciliation_observed_at
            > ACCOUNT_SYSTEM_STOP_RELEASE_EVIDENCE_MAX_AGE
        ):
            raise ValueError("SYSTEM_STOP_RELEASE_EVIDENCE_STALE")
        return self


class ActionCheckInput(EnvironmentAuthority):
    activation_id: str
    account_ref: str
    instrument_ref: str
    action_profile: str
    control_category: StopCategory
    risk_class: RiskClass
    checked_at: datetime
    quantized_quantity: str
    conservative_price: str
    economic_action_prior_notional: str = "0"
    activation_current_notional: str = "0"
    account_current_notional: str = "0"
    activation_current_margin: str = "0"
    account_dynamic_available_margin: str
    actual_margin_mode: str
    actual_leverage: str
    post_action_abs_position: str
    current_abs_position: str
    would_reverse_position: bool = False
    facts_fresh: bool = True
    attribution_unambiguous: bool = True

    @field_validator(
        "quantized_quantity",
        "conservative_price",
        "economic_action_prior_notional",
        "activation_current_notional",
        "account_current_notional",
        "activation_current_margin",
        "account_dynamic_available_margin",
        "actual_leverage",
        "post_action_abs_position",
        "current_abs_position",
    )
    @classmethod
    def decimal_inputs_are_non_negative(cls, value: str) -> str:
        return canonical_decimal(
            decimal_from_string(value, code="ACTION_VALUE_INVALID", non_negative=True)
        )


class CapDecision(CapModel):
    accepted: bool
    reason_code: str
    risk_class: RiskClass
    effective_leverage: str | None
    action_notional: str
    economic_action_notional: str
    activation_notional_after: str
    account_notional_after: str
    activation_margin_after: str
    stopped_categories: tuple[StopCategory, ...]
    input_digest: str
    decision_digest: str
