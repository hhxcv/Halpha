"""Immutable CAP values; PostgreSQL records remain the cross-restart authority."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from halpha.domain_values import canonical_decimal, decimal_from_string


class EnvironmentKind(StrEnum):
    DEMO = "DEMO"
    LIVE = "LIVE"


class AuthorityClass(StrEnum):
    DEMO_VALIDATION = "DEMO_VALIDATION"
    LIVE_REAL_CAPITAL = "LIVE_REAL_CAPITAL"
    NO_TRADING_AUTHORITY = "NO_TRADING_AUTHORITY"


class AllocationStatus(StrEnum):
    HELD = "HELD"
    EXIT_ONLY = "EXIT_ONLY"
    TAKEOVER_HELD = "TAKEOVER_HELD"
    RELEASED = "RELEASED"


class RiskClass(StrEnum):
    RISK_INCREASING = "RISK_INCREASING"
    RISK_NEUTRAL = "RISK_NEUTRAL"
    RISK_REDUCING = "RISK_REDUCING"
    AMBIGUOUS = "AMBIGUOUS"


class StopCategory(StrEnum):
    NEW_FUNDING = "NEW_FUNDING"
    PROTECTION = "PROTECTION"
    RISK_REDUCTION_OR_ORDER_MANAGEMENT = "RISK_REDUCTION_OR_ORDER_MANAGEMENT"
    ALL_WRITES = "ALL_WRITES"


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


class AccountCapitalLimitVersion(EnvironmentAuthority):
    capital_limit_version_id: str
    account_ref: str
    quote_asset: str
    version: int
    effective_at: datetime
    max_margin: str
    max_notional: str
    max_allowed_loss: str
    max_action_notional: str
    scope: dict[str, Any]
    content_digest: str

    @field_validator("max_margin", "max_notional", "max_allowed_loss", "max_action_notional")
    @classmethod
    def amounts_are_non_negative(cls, value: str) -> str:
        return canonical_decimal(
            decimal_from_string(value, code="ACCOUNT_LIMIT_INVALID", non_negative=True)
        )


class MachineAuthorizationVersion(EnvironmentAuthority):
    authorization_version_id: str
    activation_id: str
    plan_version_ref: str
    account_ref: str
    instrument_ref: str
    direction: str
    version: int
    valid_from: datetime
    valid_until: datetime
    allowed_actions: frozenset[str]
    terms: dict[str, Any]
    content_digest: str

    @model_validator(mode="after")
    def window_is_valid(self) -> MachineAuthorizationVersion:
        if self.valid_until <= self.valid_from:
            raise ValueError("AUTHORIZATION_WINDOW_INVALID")
        if not self.allowed_actions:
            raise ValueError("AUTHORIZATION_ACTIONS_EMPTY")
        return self


class PlanAllocation(EnvironmentAuthority):
    allocation_id: str
    activation_id: str
    capital_limit_version_ref: str
    quote_asset: str
    max_margin: str
    max_notional: str
    max_allowed_loss: str
    status: AllocationStatus = AllocationStatus.HELD
    state_version: int = 1
    current_margin: str = "0"
    current_notional: str = "0"
    activation_loss: str = "0"
    loss_fact_cutoff: datetime | None = None
    funding_query_cutoff: datetime | None = None
    max_loss_reached: bool = False
    loss_latch_digest: str | None = None
    closure_digest: str | None = None
    released_at: datetime | None = None

    @field_validator(
        "max_margin",
        "max_notional",
        "max_allowed_loss",
        "current_margin",
        "current_notional",
        "activation_loss",
    )
    @classmethod
    def amounts_are_non_negative(cls, value: str) -> str:
        return canonical_decimal(
            decimal_from_string(value, code="ALLOCATION_VALUE_INVALID", non_negative=True)
        )

    @model_validator(mode="after")
    def latch_is_consistent(self) -> PlanAllocation:
        if self.max_loss_reached and not self.loss_latch_digest:
            raise ValueError("LOSS_LATCH_DIGEST_REQUIRED")
        if self.loss_fact_cutoff is None and self.funding_query_cutoff is not None:
            raise ValueError("LOSS_FACT_CUTOFF_REQUIRED")
        if (
            self.loss_fact_cutoff is not None
            and self.funding_query_cutoff is not None
            and self.funding_query_cutoff > self.loss_fact_cutoff
        ):
            raise ValueError("FUNDING_CUTOFF_AFTER_LOSS_FACT")
        if self.status is AllocationStatus.RELEASED:
            if not self.closure_digest or self.released_at is None:
                raise ValueError("RELEASE_CLOSURE_REQUIRED")
        elif self.released_at is not None:
            raise ValueError("RELEASE_STATE_INVALID")
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
    authorization_version_ref: str | None = None
    loss_latch_digest: str | None = None
    release_rules: dict[str, Any]
    content_digest: str

class AllocationRequest(EnvironmentAuthority):
    allocation_id: str
    activation_id: str
    capital_limit_version_ref: str
    quote_asset: str
    max_margin: str
    max_notional: str
    max_allowed_loss: str

    @field_validator("max_margin", "max_notional", "max_allowed_loss")
    @classmethod
    def amounts_are_non_negative(cls, value: str) -> str:
        return canonical_decimal(
            decimal_from_string(value, code="ALLOCATION_VALUE_INVALID", non_negative=True)
        )


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
