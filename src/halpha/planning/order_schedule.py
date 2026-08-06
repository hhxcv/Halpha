"""Deterministic Decimal compilation for one plan-owned entry schedule.

The compiler owns no runtime state and performs no venue call.  It converts one
immutable user decision plus current instrument rules into independently
persistable order legs.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, ROUND_DOWN, ROUND_UP, localcontext
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from halpha.domain_values import canonical_decimal, content_digest, decimal_from_string
from halpha.planning.order_policies import (
    CancelOnShockRule,
    ConditionOperator,
    ConditionGroup,
    DecisionBasisReadyCondition,
    DynamicRule,
    ExpireRemainingRule,
    ProfitLockRule,
    ProfitRCondition,
    ProtectionPolicy,
    RepriceEntryRule,
    SteppedProtectionRule,
    compile_protection_targets,
    validate_dynamic_rules,
)
from halpha.planning.registry import (
    DIRECT_EXECUTION_ALLOWED_ACTION_PROFILES,
    DecisionBasisKind,
    Direction,
)


class ScheduleModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_serialization_defaults_required=True,
    )


ORDER_SCHEDULE_COMPILER_VERSION = "7"
PREVIOUS_ORDER_SCHEDULE_COMPILER_VERSION = "6"
LEGACY_V5_ORDER_SCHEDULE_COMPILER_VERSION = "5"
LEGACY_V4_ORDER_SCHEDULE_COMPILER_VERSION = "4"
LEGACY_V3_ORDER_SCHEDULE_COMPILER_VERSION = "3"
LEGACY_ORDER_SCHEDULE_COMPILER_VERSION = "2"
MAX_ORDER_SCHEDULE_LEGS = 50
BINANCE_GTD_MIN_LEAD_SECONDS = 600
MAX_DECIMAL_SIGNIFICANT_DIGITS = 38
MAX_DECIMAL_ABS_ADJUSTED_EXPONENT = 18
MAX_DISTRIBUTION_RATIO = Decimal("100")


def _bounded_decimal(
    value: str,
    *,
    code: str,
    positive: bool = False,
    non_negative: bool = False,
) -> Decimal:
    parsed = decimal_from_string(
        value,
        code=code,
        positive=positive,
        non_negative=non_negative,
    )
    if (
        len(parsed.as_tuple().digits) > MAX_DECIMAL_SIGNIFICANT_DIGITS
        or abs(parsed.adjusted()) > MAX_DECIMAL_ABS_ADJUSTED_EXPONENT
    ):
        raise ValueError(code)
    return parsed


class PriceSpacingMode(StrEnum):
    EQUAL = "EQUAL"
    LINEAR = "LINEAR"
    GEOMETRIC = "GEOMETRIC"
    CUSTOM_WEIGHTS = "CUSTOM_WEIGHTS"


class PricePlanKind(StrEnum):
    SINGLE = "SINGLE"
    LADDER = "LADDER"


class EntryProgramKind(StrEnum):
    ONE_TIME = "ONE_TIME"
    PRICE_LADDER = "PRICE_LADDER"
    TIME_SLICED = "TIME_SLICED"
    EVENT_TRIGGERED = "EVENT_TRIGGERED"


class EntryProgram(ScheduleModel):
    kind: EntryProgramKind
    slice_count: int = Field(default=1, ge=1, le=MAX_ORDER_SCHEDULE_LEGS)
    first_slice_delay_seconds: int = Field(default=0, ge=0, le=604_800)
    slice_interval_seconds: int = Field(default=0, ge=0, le=604_800)

    @model_validator(mode="after")
    def timing_is_consistent(self) -> EntryProgram:
        if self.kind is EntryProgramKind.TIME_SLICED:
            if self.slice_count < 2 or self.slice_interval_seconds < 1:
                raise ValueError("TIME_SLICED_ENTRY_INVALID")
            if (
                self.first_slice_delay_seconds
                + (self.slice_count - 1) * self.slice_interval_seconds
                > 604_800
            ):
                raise ValueError("TIME_SLICED_ENTRY_INVALID")
        elif (
            self.slice_count != 1
            or self.first_slice_delay_seconds != 0
            or self.slice_interval_seconds != 0
        ):
            raise ValueError("ENTRY_PROGRAM_TIMING_CONFLICT")
        return self


class DistributionDirection(StrEnum):
    LOW_TO_HIGH = "LOW_TO_HIGH"
    HIGH_TO_LOW = "HIGH_TO_LOW"


class AmountDistributionMode(StrEnum):
    FIXED = "FIXED"
    LINEAR = "LINEAR"
    EXPONENTIAL = "EXPONENTIAL"
    CUSTOM = "CUSTOM"


class VenueTimeInForce(StrEnum):
    GTC = "GTC"
    GTD = "GTD"
    IOC = "IOC"
    FOK = "FOK"


class VenueOrderType(StrEnum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"


class ScheduleSubmissionMode(StrEnum):
    SERIAL_PROTECTED = "SERIAL_PROTECTED"
    PREPROTECTED_PARALLEL = "PREPROTECTED_PARALLEL"


class ScheduleSubmissionOrder(StrEnum):
    LOW_TO_HIGH = "LOW_TO_HIGH"
    HIGH_TO_LOW = "HIGH_TO_LOW"


class BinancePriceMatch(StrEnum):
    OPPONENT = "OPPONENT"
    OPPONENT_5 = "OPPONENT_5"
    OPPONENT_10 = "OPPONENT_10"
    OPPONENT_20 = "OPPONENT_20"
    QUEUE = "QUEUE"
    QUEUE_5 = "QUEUE_5"
    QUEUE_10 = "QUEUE_10"
    QUEUE_20 = "QUEUE_20"


class SinglePrice(ScheduleModel):
    kind: Literal[PricePlanKind.SINGLE] = PricePlanKind.SINGLE
    limit_price: str | None = None

    @field_validator("limit_price")
    @classmethod
    def optional_positive_price(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return canonical_decimal(
            _bounded_decimal(
                value,
                code="ORDER_SCHEDULE_PRICE_INVALID",
                positive=True,
            )
        )


class PriceDistribution(ScheduleModel):
    kind: Literal[PricePlanKind.LADDER] = PricePlanKind.LADDER
    lower_price: str
    upper_price: str
    level_count: int = Field(ge=2, le=MAX_ORDER_SCHEDULE_LEGS)
    spacing_mode: PriceSpacingMode = PriceSpacingMode.EQUAL
    spacing_direction: DistributionDirection = DistributionDirection.LOW_TO_HIGH
    linear_start_weight: str = "1"
    linear_step: str = "1"
    geometric_ratio: str = "2"
    custom_gap_weights: tuple[str, ...] = ()

    @field_validator(
        "lower_price",
        "upper_price",
        "linear_start_weight",
        "geometric_ratio",
    )
    @classmethod
    def positive_decimal(cls, value: str) -> str:
        return canonical_decimal(
            _bounded_decimal(
                value,
                code="ORDER_SCHEDULE_PRICE_INVALID",
                positive=True,
            )
        )

    @field_validator("linear_step")
    @classmethod
    def finite_linear_step(cls, value: str) -> str:
        return canonical_decimal(
            _bounded_decimal(value, code="ORDER_SCHEDULE_PRICE_WEIGHT_INVALID")
        )

    @field_validator("custom_gap_weights")
    @classmethod
    def positive_weights(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(
            canonical_decimal(
                _bounded_decimal(
                    value,
                    code="ORDER_SCHEDULE_PRICE_WEIGHT_INVALID",
                    positive=True,
                )
            )
            for value in values
        )

    @model_validator(mode="after")
    def distribution_is_consistent(self) -> PriceDistribution:
        if Decimal(self.upper_price) <= Decimal(self.lower_price):
            raise ValueError("ORDER_SCHEDULE_PRICE_RANGE_INVALID")
        gap_count = self.level_count - 1
        if self.spacing_mode is PriceSpacingMode.CUSTOM_WEIGHTS:
            if len(self.custom_gap_weights) != gap_count:
                raise ValueError("ORDER_SCHEDULE_PRICE_WEIGHT_COUNT_INVALID")
        elif self.custom_gap_weights:
            raise ValueError("ORDER_SCHEDULE_PRICE_WEIGHT_MODE_INVALID")
        if (
            self.spacing_mode is PriceSpacingMode.GEOMETRIC
            and not (
                Decimal(1)
                < Decimal(self.geometric_ratio)
                <= MAX_DISTRIBUTION_RATIO
            )
        ):
            raise ValueError("ORDER_SCHEDULE_GEOMETRIC_RATIO_INVALID")
        if self.spacing_mode is PriceSpacingMode.LINEAR:
            first = Decimal(self.linear_start_weight)
            step = Decimal(self.linear_step)
            if any(first + step * index <= 0 for index in range(gap_count)):
                raise ValueError("ORDER_SCHEDULE_LINEAR_WEIGHT_INVALID")
        return self


PricePlan = Annotated[
    SinglePrice | PriceDistribution,
    Field(discriminator="kind"),
]


class AmountDistribution(ScheduleModel):
    mode: AmountDistributionMode = AmountDistributionMode.FIXED
    direction: DistributionDirection = DistributionDirection.LOW_TO_HIGH
    base_notional: str = "10"
    linear_step: str = "10"
    exponential_ratio: str = "2"
    custom_notionals: tuple[str, ...] = ()

    @field_validator("base_notional", "exponential_ratio")
    @classmethod
    def positive_decimal(cls, value: str) -> str:
        return canonical_decimal(
            _bounded_decimal(
                value,
                code="ORDER_SCHEDULE_AMOUNT_INVALID",
                positive=True,
            )
        )

    @field_validator("linear_step")
    @classmethod
    def non_negative_step(cls, value: str) -> str:
        return canonical_decimal(
            _bounded_decimal(
                value,
                code="ORDER_SCHEDULE_AMOUNT_INVALID",
                non_negative=True,
            )
        )

    @field_validator("custom_notionals")
    @classmethod
    def positive_custom_amounts(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(
            canonical_decimal(
                _bounded_decimal(
                    value,
                    code="ORDER_SCHEDULE_AMOUNT_INVALID",
                    positive=True,
                )
            )
            for value in values
        )

    @model_validator(mode="after")
    def distribution_is_consistent(self) -> AmountDistribution:
        if self.mode is AmountDistributionMode.CUSTOM:
            if not self.custom_notionals:
                raise ValueError("ORDER_SCHEDULE_CUSTOM_AMOUNT_EMPTY")
        elif self.custom_notionals:
            raise ValueError("ORDER_SCHEDULE_CUSTOM_AMOUNT_MODE_INVALID")
        if (
            self.mode is AmountDistributionMode.EXPONENTIAL
            and not (
                Decimal(1)
                < Decimal(self.exponential_ratio)
                <= MAX_DISTRIBUTION_RATIO
            )
        ):
            raise ValueError("ORDER_SCHEDULE_EXPONENTIAL_RATIO_INVALID")
        return self


class VenueOrderPolicy(ScheduleModel):
    order_type: VenueOrderType = VenueOrderType.LIMIT
    time_in_force: VenueTimeInForce | None = VenueTimeInForce.GTC
    post_only: bool = False
    price_match: BinancePriceMatch | None = None
    expire_at: datetime | None = None

    @model_validator(mode="after")
    def policy_is_supported(self) -> VenueOrderPolicy:
        if self.order_type is VenueOrderType.MARKET:
            if (
                self.time_in_force is not None
                or self.post_only
                or self.price_match is not None
                or self.expire_at is not None
            ):
                raise ValueError("MARKET_ORDER_POLICY_CONFLICT")
            return self
        if self.time_in_force is None:
            raise ValueError("LIMIT_TIME_IN_FORCE_REQUIRED")
        if self.post_only and self.time_in_force is not VenueTimeInForce.GTC:
            raise ValueError("POST_ONLY_TIME_IN_FORCE_CONFLICT")
        if self.post_only and self.price_match is not None:
            raise ValueError("POST_ONLY_PRICE_MATCH_CONFLICT")
        if self.time_in_force is VenueTimeInForce.GTD:
            if self.expire_at is None or self.expire_at.utcoffset() is None:
                raise ValueError("GTD_EXPIRY_REQUIRED")
        elif self.expire_at is not None:
            raise ValueError("GTD_EXPIRY_TIME_IN_FORCE_CONFLICT")
        return self


class OrderScheduleSpec(ScheduleModel):
    entry_program: EntryProgram | None = None
    price_distribution: PricePlan
    amount_distribution: AmountDistribution
    venue_policy: VenueOrderPolicy = VenueOrderPolicy()
    submission_mode: ScheduleSubmissionMode = ScheduleSubmissionMode.SERIAL_PROTECTED
    submission_order: ScheduleSubmissionOrder = ScheduleSubmissionOrder.LOW_TO_HIGH
    entry_conditions: ConditionGroup = ConditionGroup()
    protection_policy: ProtectionPolicy | None = None
    dynamic_rules: tuple[DynamicRule, ...] = ()

    @model_validator(mode="after")
    def custom_amount_count_matches_levels(self) -> OrderScheduleSpec:
        amounts = self.amount_distribution
        program = self.resolved_entry_program
        level_count = (
            program.slice_count
            if program.kind is EntryProgramKind.TIME_SLICED
            else (
                1
                if isinstance(self.price_distribution, SinglePrice)
                else self.price_distribution.level_count
            )
        )
        if (
            amounts.mode is AmountDistributionMode.CUSTOM
            and len(amounts.custom_notionals)
            != level_count
        ):
            raise ValueError("ORDER_SCHEDULE_CUSTOM_AMOUNT_COUNT_INVALID")
        policy = self.venue_policy
        if isinstance(self.price_distribution, SinglePrice):
            if (
                program.kind is not EntryProgramKind.TIME_SLICED
                and amounts.mode is not AmountDistributionMode.FIXED
            ):
                raise ValueError("SINGLE_ORDER_AMOUNT_MODE_INVALID")
            if policy.order_type is VenueOrderType.MARKET:
                if self.price_distribution.limit_price is not None:
                    raise ValueError("MARKET_ORDER_PRICE_CONFLICT")
            elif (
                (self.price_distribution.limit_price is None)
                == (policy.price_match is None)
            ):
                raise ValueError("SINGLE_LIMIT_PRICE_AMBIGUOUS")
        elif (
            policy.order_type is not VenueOrderType.LIMIT
            or policy.price_match is not None
        ):
            raise ValueError("PRICE_MATCH_EXPLICIT_PRICE_CONFLICT")
        if program.kind is EntryProgramKind.PRICE_LADDER:
            if not isinstance(self.price_distribution, PriceDistribution):
                raise ValueError("PRICE_LADDER_ENTRY_REQUIRES_RANGE")
        elif not isinstance(self.price_distribution, SinglePrice):
            raise ValueError("ENTRY_PROGRAM_REQUIRES_SINGLE_PRICE")
        if program.kind is EntryProgramKind.TIME_SLICED:
            if self.submission_order is not ScheduleSubmissionOrder.LOW_TO_HIGH:
                raise ValueError("TIME_SLICED_SUBMISSION_ORDER_CONFLICT")
            if (
                policy.order_type is VenueOrderType.LIMIT
                and policy.time_in_force
                not in {
                    VenueTimeInForce.GTC,
                    VenueTimeInForce.IOC,
                    VenueTimeInForce.FOK,
                }
            ):
                raise ValueError("TIME_SLICED_VENUE_POLICY_CONFLICT")
            if (
                policy.order_type is VenueOrderType.LIMIT
                and policy.time_in_force is VenueTimeInForce.GTC
                and not any(
                    isinstance(rule, ExpireRemainingRule)
                    for rule in self.dynamic_rules
                )
            ):
                raise ValueError("TIME_SLICED_RESTING_EXPIRY_REQUIRED")
        if program.kind is EntryProgramKind.EVENT_TRIGGERED and not any(
            not isinstance(condition, DecisionBasisReadyCondition)
            for condition in self.entry_conditions.items
        ):
            raise ValueError("EVENT_TRIGGER_REQUIRED")
        validate_dynamic_rules(
            self.dynamic_rules,
            protection_policy=self.protection_policy,
        )
        if any(isinstance(rule, CancelOnShockRule) for rule in self.dynamic_rules):
            if self.submission_mode is not ScheduleSubmissionMode.SERIAL_PROTECTED:
                raise ValueError("CANCEL_ON_SHOCK_POLICY_CONFLICT")
        if any(isinstance(rule, ExpireRemainingRule) for rule in self.dynamic_rules):
            if policy.order_type is not VenueOrderType.LIMIT:
                raise ValueError("EXPIRE_REMAINING_POLICY_CONFLICT")
        if any(isinstance(rule, RepriceEntryRule) for rule in self.dynamic_rules):
            if (
                program.kind
                not in {EntryProgramKind.ONE_TIME, EntryProgramKind.EVENT_TRIGGERED}
                or not isinstance(self.price_distribution, SinglePrice)
                or self.price_distribution.limit_price is None
                or policy.order_type is not VenueOrderType.LIMIT
                or policy.time_in_force is not VenueTimeInForce.GTC
                or policy.price_match is not None
                or self.submission_mode is not ScheduleSubmissionMode.SERIAL_PROTECTED
            ):
                raise ValueError("REPRICE_ENTRY_POLICY_CONFLICT")
        if (
            self.submission_mode is ScheduleSubmissionMode.PREPROTECTED_PARALLEL
            and self.protection_policy is None
        ):
            raise ValueError("PREPROTECTED_PARALLEL_PROTECTION_REQUIRED")
        return self

    @property
    def resolved_entry_program(self) -> EntryProgram:
        if self.entry_program is not None:
            return self.entry_program
        if isinstance(self.price_distribution, PriceDistribution):
            return EntryProgram(kind=EntryProgramKind.PRICE_LADDER)
        return EntryProgram(kind=EntryProgramKind.ONE_TIME)


def validate_direct_execution_schedule(spec: OrderScheduleSpec | None) -> None:
    """Validate runtime support, including frozen schedules from older compilers."""

    if spec is None:
        raise ValueError("DIRECT_EXECUTION_SCHEDULE_REQUIRED")
    if spec.protection_policy is None:
        raise ValueError("DIRECT_EXECUTION_PROTECTION_REQUIRED")
    if (
        spec.entry_program is not None
        and spec.protection_policy.take_profit_ladder is None
        and spec.protection_policy.time_exit_seconds is None
        and not any(
            isinstance(rule, (SteppedProtectionRule, ProfitLockRule))
            for rule in spec.dynamic_rules
        )
    ):
        raise ValueError("DIRECT_EXECUTION_AUTOMATIC_EXIT_REQUIRED")
    take_profit_ladder = spec.protection_policy.take_profit_ladder
    if take_profit_ladder is not None:
        if len(take_profit_ladder.levels) > 4:
            raise ValueError("DIRECT_EXECUTION_TAKE_PROFIT_LEVEL_COUNT_INVALID")
        if sum(
            (
                Decimal(level.quantity_fraction)
                for level in take_profit_ladder.levels
            ),
            Decimal(0),
        ) != Decimal(1):
            # Direct fills are protected independently. Requiring the ladder to
            # allocate the complete fill keeps every quantity step attributable
            # even when a small partial fill cannot populate every configured
            # target.
            raise ValueError("DIRECT_EXECUTION_TAKE_PROFIT_FRACTION_TOTAL_INVALID")
    if spec.submission_mode is ScheduleSubmissionMode.PREPROTECTED_PARALLEL:
        # The deterministic compiler can represent and qualification tests can
        # exercise this mode, but the current product has no L4 Demo evidence
        # that venue protection is active before every concurrently exposed
        # entry.  Keep it outside the persisted DIRECT_EXECUTION catalog until
        # that evidence exists.
        raise ValueError("PREPROTECTED_PARALLEL_NOT_VERIFIED")
    if (
        spec.entry_conditions.operator is ConditionOperator.ANY
        and len(spec.entry_conditions.items) > 1
        and any(
            isinstance(condition, DecisionBasisReadyCondition)
            for condition in spec.entry_conditions.items
        )
    ):
        # DIRECT_EXECUTION readiness is always true once the activation is
        # runnable.  Keeping it beside optional conditions under ANY would
        # silently turn every optional market condition into decoration.
        raise ValueError("DIRECT_EXECUTION_ANY_IMMEDIATE_CONDITION_CONFLICT")
    if any(
        isinstance(condition, ProfitRCondition)
        for condition in spec.entry_conditions.items
    ):
        raise ValueError("DIRECT_EXECUTION_PROFIT_R_UNSUPPORTED")
    if any(
        isinstance(rule, CancelOnShockRule) and rule.max_triggers != 1
        for rule in spec.dynamic_rules
    ):
        raise ValueError(
            "DIRECT_EXECUTION_CANCEL_ON_SHOCK_MAX_TRIGGERS_UNSUPPORTED"
        )


def validate_new_direct_execution_schedule(
    spec: OrderScheduleSpec | None,
) -> None:
    """Require the current creation contract without rewriting legacy plans."""

    validate_direct_execution_schedule(spec)
    if spec is None or spec.entry_program is None:
        raise ValueError("DIRECT_EXECUTION_ENTRY_PROGRAM_REQUIRED")
    if (
        spec.entry_program.kind is EntryProgramKind.TIME_SLICED
        and spec.venue_policy.order_type is VenueOrderType.LIMIT
        and spec.venue_policy.time_in_force
        not in {VenueTimeInForce.IOC, VenueTimeInForce.FOK}
    ):
        # A time slice is an execution instant, not another indefinitely
        # resting order. Keep reading older bounded-GTC plans, but do not let
        # the current creator produce new plans whose actual entry time is
        # unknowable.
        raise ValueError("DIRECT_EXECUTION_TIME_SLICED_TIF_UNSUPPORTED")
    if (
        spec.entry_program.kind is EntryProgramKind.TIME_SLICED
        and any(
            isinstance(rule, ExpireRemainingRule)
            for rule in spec.dynamic_rules
        )
    ):
        raise ValueError("DIRECT_EXECUTION_TIME_SLICED_EXPIRY_UNSUPPORTED")
    if (
        spec.protection_policy is not None
        and spec.protection_policy.take_profit_ladder is None
        and spec.protection_policy.time_exit_seconds is None
        and not any(
            isinstance(rule, (SteppedProtectionRule, ProfitLockRule))
            for rule in spec.dynamic_rules
        )
    ):
        raise ValueError("DIRECT_EXECUTION_AUTOMATIC_EXIT_REQUIRED")
    if (
        spec.protection_policy is None
        or spec.protection_policy.full_fill_loss_budget is None
    ):
        raise ValueError("DIRECT_EXECUTION_FULL_FILL_LOSS_BUDGET_REQUIRED")


def direct_allowed_action_profiles(
    spec: OrderScheduleSpec | None,
) -> frozenset[str]:
    """Derive the exact action authority consumed by one direct schedule."""

    validate_direct_execution_schedule(spec)
    if spec is None or spec.protection_policy is None:
        # Keep the invariant explicit in production.  ``assert`` would remove
        # this narrowing under ``python -O`` and make later failures indirect.
        raise ValueError("DIRECT_EXECUTION_PROTECTION_REQUIRED")

    is_limit = spec.venue_policy.order_type is VenueOrderType.LIMIT
    profiles = {
        "ENTRY_LIMIT" if is_limit else "ENTRY_MARKET",
        "PROTECTIVE_STOP_REDUCE_ONLY",
        "REDUCE_OR_CLOSE_MARKET",
    }
    if is_limit:
        profiles.add("CANCEL_ORDER")
    take_profit_ladder = spec.protection_policy.take_profit_ladder
    if take_profit_ladder is not None:
        profiles.add("TAKE_PROFIT_1")
        if len(take_profit_ladder.levels) > 1:
            # Runtime profiles describe the qualified venue action shape. All
            # direct levels after the first reuse TAKE_PROFIT_2.
            profiles.add("TAKE_PROFIT_2")

    supported = frozenset(DIRECT_EXECUTION_ALLOWED_ACTION_PROFILES)
    if not profiles.issubset(supported):
        raise ValueError("DIRECT_EXECUTION_ACTION_PROFILE_UNSUPPORTED")
    return frozenset(profiles)


def validate_current_order_schedule_support(
    decision_basis_kind: DecisionBasisKind,
    spec: OrderScheduleSpec | None,
) -> None:
    """Fail closed when a persisted schedule has no current runtime consumer."""

    if decision_basis_kind is DecisionBasisKind.DIRECT_EXECUTION:
        validate_direct_execution_schedule(spec)
    elif spec is not None:
        # The durable design permits a strategy to feed the shared order-plan
        # boundary, but the current strategy runtime still emits its legacy
        # single entry action.  Accepting a schedule here would be a false
        # execution promise until that consumer is implemented and qualified.
        raise ValueError("STRATEGY_ORDER_SCHEDULE_NOT_SUPPORTED")


class InstrumentOrderRules(ScheduleModel):
    source: str
    min_price: str
    max_price: str
    price_tick_size: str
    limit_quantity_step: str
    min_limit_quantity: str
    max_limit_quantity: str
    market_quantity_step: str
    min_market_quantity: str
    max_market_quantity: str
    min_notional: str
    source_cutoff: str

    @field_validator("source")
    @classmethod
    def source_is_stable(cls, value: str) -> str:
        if not value or value.strip() != value or len(value) > 160:
            raise ValueError("INSTRUMENT_RULE_SOURCE_INVALID")
        return value

    @field_validator(
        "price_tick_size",
        "min_price",
        "max_price",
        "limit_quantity_step",
        "min_limit_quantity",
        "max_limit_quantity",
        "market_quantity_step",
        "min_market_quantity",
        "max_market_quantity",
        "min_notional",
    )
    @classmethod
    def positive_decimal(cls, value: str) -> str:
        return canonical_decimal(
            _bounded_decimal(
                value,
                code="INSTRUMENT_RULE_INVALID",
                positive=True,
            )
        )

    @field_validator("source_cutoff")
    @classmethod
    def aware_source_cutoff(cls, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            raise ValueError("INSTRUMENT_RULE_CUTOFF_INVALID") from None
        if parsed.utcoffset() is None:
            raise ValueError("INSTRUMENT_RULE_CUTOFF_INVALID")
        return parsed.isoformat()

    @model_validator(mode="after")
    def limits_are_consistent(self) -> InstrumentOrderRules:
        if Decimal(self.max_price) < Decimal(self.min_price):
            raise ValueError("INSTRUMENT_RULE_INVALID")
        if Decimal(self.max_limit_quantity) < Decimal(self.min_limit_quantity):
            raise ValueError("INSTRUMENT_RULE_INVALID")
        if Decimal(self.max_market_quantity) < Decimal(self.min_market_quantity):
            raise ValueError("INSTRUMENT_RULE_INVALID")
        return self

    @property
    def digest(self) -> str:
        return content_digest(
            self.model_dump(mode="json", exclude={"source_cutoff"})
        )


class ScheduleIssue(ScheduleModel):
    code: str
    field: str
    leg_index: int | None = None


class CompiledOrderLeg(ScheduleModel):
    leg_index: int
    leg_count: int
    release_after_seconds: int = Field(default=0, ge=0, le=604_800)
    raw_price: str | None
    price: str | None
    sizing_price: str
    requested_notional: str
    quantity: str
    effective_notional: str


class FullFillProtectionEstimate(ScheduleModel):
    """Deterministic full-entry stop loss before slippage, gaps, or funding."""

    average_entry_price: str
    entry_boundary_price: str
    stop_price: str
    quantity: str
    gross_price_loss: str
    estimated_entry_fee: str
    estimated_exit_fee: str
    maximum_projected_loss: str


class OrderSchedulePreview(ScheduleModel):
    valid: bool
    compiler_version: str
    schedule_ref: str
    schedule_digest: str
    schedule_spec: OrderScheduleSpec
    preprotected_parallel_supported: bool
    venue_ref: str
    instrument_ref: str
    direction: Direction
    max_notional: str
    reference_price: str | None
    instrument_rules: InstrumentOrderRules
    instrument_rules_digest: str
    source_cutoff: str
    requested_total_notional: str
    effective_total_notional: str
    full_fill_protection_estimate: FullFillProtectionEstimate | None = None
    normalized_legs: tuple[CompiledOrderLeg, ...]
    legs: tuple[CompiledOrderLeg, ...]
    issues: tuple[ScheduleIssue, ...]


def _compile_full_fill_protection_estimate(
    *,
    policy: ProtectionPolicy,
    direction: Direction,
    legs: tuple[CompiledOrderLeg, ...],
    price_tick_size: str,
) -> FullFillProtectionEstimate | None:
    budget = policy.full_fill_loss_budget
    if budget is None or not legs:
        return None
    quantity = sum((Decimal(leg.quantity) for leg in legs), Decimal(0))
    notional = sum((Decimal(leg.effective_notional) for leg in legs), Decimal(0))
    if quantity <= 0 or notional <= 0:
        return None
    with localcontext() as context:
        context.prec = 128
        average_entry = notional / quantity
        tick = Decimal(price_tick_size)
        distance = (
            average_entry
            * Decimal(policy.initial_stop.distance_bps)
            / Decimal(10_000)
        )
        raw_stop = (
            average_entry - distance
            if direction is Direction.LONG
            else average_entry + distance
        )
        stop = (
            raw_stop / tick
        ).to_integral_value(
            rounding=ROUND_UP if direction is Direction.LONG else ROUND_DOWN
        ) * tick
        if stop <= 0:
            raise ValueError("PROTECTION_PRICE_INVALID")
        prices = tuple(Decimal(leg.sizing_price) for leg in legs)
        entry_boundary = (
            min(prices) if direction is Direction.LONG else max(prices)
        )
        # The initial stop must sit beyond every planned entry. Otherwise a
        # falling/rising market can stop the owned position while a later leg
        # is still allowed to add risk in the opposite direction.
        distinct_entry_prices = set(prices)
        if len(distinct_entry_prices) > 1 and (
            (direction is Direction.LONG and stop >= entry_boundary)
            or (direction is Direction.SHORT and stop <= entry_boundary)
        ):
            raise ValueError("PROTECTION_INSIDE_ENTRY_RANGE")
        gross_loss = quantity * abs(average_entry - stop)
        entry_fee = notional * Decimal(budget.entry_fee_bps) / Decimal(10_000)
        exit_fee = (
            quantity
            * stop
            * Decimal(budget.exit_fee_bps)
            / Decimal(10_000)
        )
        maximum_loss = gross_loss + entry_fee + exit_fee
    return FullFillProtectionEstimate(
        average_entry_price=canonical_decimal(average_entry),
        entry_boundary_price=canonical_decimal(entry_boundary),
        stop_price=canonical_decimal(stop),
        quantity=canonical_decimal(quantity),
        gross_price_loss=canonical_decimal(gross_loss),
        estimated_entry_fee=canonical_decimal(entry_fee),
        estimated_exit_fee=canonical_decimal(exit_fee),
        maximum_projected_loss=canonical_decimal(maximum_loss),
    )


def _schedule_digest_payload(
    *,
    compiler_version: str,
    schedule_spec: OrderScheduleSpec,
    preprotected_parallel_supported: bool,
    venue_ref: str,
    instrument_ref: str,
    direction: Direction,
    max_notional: str,
    reference_price: str | None,
    instrument_rules: InstrumentOrderRules,
    requested_total_notional: str,
    effective_total_notional: str,
    legs: tuple[CompiledOrderLeg, ...],
) -> dict[str, object]:
    return {
        "compiler_version": compiler_version,
        "venue_ref": venue_ref,
        "instrument_ref": instrument_ref,
        "direction": direction.value,
        "max_notional": max_notional,
        "reference_price": reference_price,
        "spec": _normalized_spec_payload(schedule_spec),
        # The exchange observation time is provenance, not an executable rule.
        # A fresh activation check must remain confirmable when the rule values
        # are unchanged even though exchangeInfo reports a newer server time.
        "instrument_rules": instrument_rules.model_dump(
            mode="json",
            exclude={"source_cutoff"},
        ),
        "preprotected_parallel_supported": preprotected_parallel_supported,
        "requested_total_notional": requested_total_notional,
        "effective_total_notional": effective_total_notional,
        "legs": [leg.model_dump(mode="json") for leg in legs],
    }


def _legacy_v2_schedule_digest_payload(
    *,
    schedule_spec: OrderScheduleSpec,
    preprotected_parallel_supported: bool,
    venue_ref: str,
    instrument_ref: str,
    direction: Direction,
    max_notional: str,
    reference_price: str | None,
    instrument_rules: InstrumentOrderRules,
    requested_total_notional: str,
    effective_total_notional: str,
    legs: tuple[CompiledOrderLeg, ...],
) -> dict[str, object]:
    """Reproduce the frozen v2 digest without recompiling its order legs."""

    payload = _schedule_digest_payload(
        compiler_version=LEGACY_ORDER_SCHEDULE_COMPILER_VERSION,
        schedule_spec=schedule_spec,
        preprotected_parallel_supported=preprotected_parallel_supported,
        venue_ref=venue_ref,
        instrument_ref=instrument_ref,
        direction=direction,
        max_notional=max_notional,
        reference_price=reference_price,
        instrument_rules=instrument_rules,
        requested_total_notional=requested_total_notional,
        effective_total_notional=effective_total_notional,
        legs=legs,
    )
    _remove_post_v3_dynamic_fields(payload)
    _remove_post_v5_schedule_fields(payload)
    # v2 included the observation cutoff in the schedule digest. Keep that
    # historical algorithm isolated; current previews use v5 only.
    payload["instrument_rules"] = instrument_rules.model_dump(mode="json")
    return payload


def _legacy_v3_schedule_digest_payload(
    *,
    schedule_spec: OrderScheduleSpec,
    preprotected_parallel_supported: bool,
    venue_ref: str,
    instrument_ref: str,
    direction: Direction,
    max_notional: str,
    reference_price: str | None,
    instrument_rules: InstrumentOrderRules,
    requested_total_notional: str,
    effective_total_notional: str,
    legs: tuple[CompiledOrderLeg, ...],
) -> dict[str, object]:
    """Reproduce the frozen v3 digest after the rule model gains v4 fields."""

    payload = _schedule_digest_payload(
        compiler_version=LEGACY_V3_ORDER_SCHEDULE_COMPILER_VERSION,
        schedule_spec=schedule_spec,
        preprotected_parallel_supported=preprotected_parallel_supported,
        venue_ref=venue_ref,
        instrument_ref=instrument_ref,
        direction=direction,
        max_notional=max_notional,
        reference_price=reference_price,
        instrument_rules=instrument_rules,
        requested_total_notional=requested_total_notional,
        effective_total_notional=effective_total_notional,
        legs=legs,
    )
    _remove_post_v3_dynamic_fields(payload)
    _remove_post_v5_schedule_fields(payload)
    return payload


def _remove_post_v3_dynamic_fields(payload: dict[str, object]) -> None:
    """Remove fields that did not exist in the frozen v2/v3 canonical payload."""

    spec = payload.get("spec")
    if not isinstance(spec, dict):
        return
    rules = spec.get("dynamic_rules")
    if not isinstance(rules, list):
        return
    for rule in rules:
        if isinstance(rule, dict) and rule.get("kind") == "CANCEL_ON_SHOCK":
            rule.pop("invalidation_price", None)
            rule.pop("opportunity_missed_price", None)


def _legacy_v4_schedule_digest_payload(
    *,
    schedule_spec: OrderScheduleSpec,
    preprotected_parallel_supported: bool,
    venue_ref: str,
    instrument_ref: str,
    direction: Direction,
    max_notional: str,
    reference_price: str | None,
    instrument_rules: InstrumentOrderRules,
    requested_total_notional: str,
    effective_total_notional: str,
    legs: tuple[CompiledOrderLeg, ...],
) -> dict[str, object]:
    """Reproduce the frozen v4 digest after the rule model gains v5 fields."""

    payload = _schedule_digest_payload(
        compiler_version=LEGACY_V4_ORDER_SCHEDULE_COMPILER_VERSION,
        schedule_spec=schedule_spec,
        preprotected_parallel_supported=preprotected_parallel_supported,
        venue_ref=venue_ref,
        instrument_ref=instrument_ref,
        direction=direction,
        max_notional=max_notional,
        reference_price=reference_price,
        instrument_rules=instrument_rules,
        requested_total_notional=requested_total_notional,
        effective_total_notional=effective_total_notional,
        legs=legs,
    )
    spec = payload.get("spec")
    if not isinstance(spec, dict):
        return payload
    rules = spec.get("dynamic_rules")
    if not isinstance(rules, list):
        return payload
    for rule in rules:
        if isinstance(rule, dict) and rule.get("kind") == "CANCEL_ON_SHOCK":
            rule.pop("opportunity_missed_price", None)
    _remove_post_v5_schedule_fields(payload)
    return payload


def _remove_post_v5_schedule_fields(payload: dict[str, object]) -> None:
    """Remove entry-program timing added after the frozen v5 payload."""

    spec = payload.get("spec")
    if isinstance(spec, dict):
        spec.pop("entry_program", None)
    legs = payload.get("legs")
    if isinstance(legs, list):
        for leg in legs:
            if isinstance(leg, dict):
                leg.pop("release_after_seconds", None)


def _legacy_v5_schedule_digest_payload(
    *,
    schedule_spec: OrderScheduleSpec,
    preprotected_parallel_supported: bool,
    venue_ref: str,
    instrument_ref: str,
    direction: Direction,
    max_notional: str,
    reference_price: str | None,
    instrument_rules: InstrumentOrderRules,
    requested_total_notional: str,
    effective_total_notional: str,
    legs: tuple[CompiledOrderLeg, ...],
) -> dict[str, object]:
    payload = _schedule_digest_payload(
        compiler_version=LEGACY_V5_ORDER_SCHEDULE_COMPILER_VERSION,
        schedule_spec=schedule_spec,
        preprotected_parallel_supported=preprotected_parallel_supported,
        venue_ref=venue_ref,
        instrument_ref=instrument_ref,
        direction=direction,
        max_notional=max_notional,
        reference_price=reference_price,
        instrument_rules=instrument_rules,
        requested_total_notional=requested_total_notional,
        effective_total_notional=effective_total_notional,
        legs=legs,
    )
    _remove_post_v5_schedule_fields(payload)
    return payload


def _legacy_v6_schedule_digest_payload(
    *,
    schedule_spec: OrderScheduleSpec,
    preprotected_parallel_supported: bool,
    venue_ref: str,
    instrument_ref: str,
    direction: Direction,
    max_notional: str,
    reference_price: str | None,
    instrument_rules: InstrumentOrderRules,
    requested_total_notional: str,
    effective_total_notional: str,
    legs: tuple[CompiledOrderLeg, ...],
) -> dict[str, object]:
    """Reproduce the frozen v6 payload before entry repricing was added."""

    return _schedule_digest_payload(
        compiler_version=PREVIOUS_ORDER_SCHEDULE_COMPILER_VERSION,
        schedule_spec=schedule_spec,
        preprotected_parallel_supported=preprotected_parallel_supported,
        venue_ref=venue_ref,
        instrument_ref=instrument_ref,
        direction=direction,
        max_notional=max_notional,
        reference_price=reference_price,
        instrument_rules=instrument_rules,
        requested_total_notional=requested_total_notional,
        effective_total_notional=effective_total_notional,
        legs=legs,
    )


def validate_order_schedule_snapshot(snapshot: OrderSchedulePreview) -> None:
    """Reject a persisted snapshot whose full executable content is not self-consistent."""

    if not snapshot.valid or snapshot.issues or snapshot.legs != snapshot.normalized_legs:
        raise ValueError("ORDER_SCHEDULE_SNAPSHOT_INVALID")
    if snapshot.compiler_version not in {
        LEGACY_ORDER_SCHEDULE_COMPILER_VERSION,
        LEGACY_V3_ORDER_SCHEDULE_COMPILER_VERSION,
        LEGACY_V4_ORDER_SCHEDULE_COMPILER_VERSION,
        LEGACY_V5_ORDER_SCHEDULE_COMPILER_VERSION,
        PREVIOUS_ORDER_SCHEDULE_COMPILER_VERSION,
        ORDER_SCHEDULE_COMPILER_VERSION,
    }:
        raise ValueError("ORDER_SCHEDULE_COMPILER_UNSUPPORTED")
    if snapshot.compiler_version in {
        LEGACY_ORDER_SCHEDULE_COMPILER_VERSION,
        LEGACY_V3_ORDER_SCHEDULE_COMPILER_VERSION,
    } and any(
        isinstance(rule, CancelOnShockRule)
        and (
            rule.invalidation_price is not None
            or rule.opportunity_missed_price is not None
            or rule.window_seconds is None
            or rule.adverse_move_bps is None
        )
        for rule in snapshot.schedule_spec.dynamic_rules
    ):
        raise ValueError("ORDER_SCHEDULE_SNAPSHOT_CORRUPT")
    if (
        snapshot.compiler_version == LEGACY_V4_ORDER_SCHEDULE_COMPILER_VERSION
        and any(
            isinstance(rule, CancelOnShockRule)
            and rule.opportunity_missed_price is not None
            for rule in snapshot.schedule_spec.dynamic_rules
        )
    ):
        raise ValueError("ORDER_SCHEDULE_SNAPSHOT_CORRUPT")
    if snapshot.compiler_version in {
        LEGACY_ORDER_SCHEDULE_COMPILER_VERSION,
        LEGACY_V3_ORDER_SCHEDULE_COMPILER_VERSION,
        LEGACY_V4_ORDER_SCHEDULE_COMPILER_VERSION,
        LEGACY_V5_ORDER_SCHEDULE_COMPILER_VERSION,
    } and (
        snapshot.schedule_spec.entry_program is not None
        or any(
            isinstance(rule, ProfitLockRule)
            for rule in snapshot.schedule_spec.dynamic_rules
        )
        or any(leg.release_after_seconds != 0 for leg in snapshot.legs)
    ):
        raise ValueError("ORDER_SCHEDULE_SNAPSHOT_CORRUPT")
    if (
        snapshot.compiler_version != ORDER_SCHEDULE_COMPILER_VERSION
        and any(
            isinstance(rule, RepriceEntryRule)
            for rule in snapshot.schedule_spec.dynamic_rules
        )
    ):
        raise ValueError("ORDER_SCHEDULE_SNAPSHOT_CORRUPT")
    if snapshot.source_cutoff != snapshot.instrument_rules.source_cutoff:
        raise ValueError("ORDER_SCHEDULE_SNAPSHOT_CORRUPT")
    if snapshot.instrument_rules_digest != snapshot.instrument_rules.digest:
        raise ValueError("ORDER_SCHEDULE_SNAPSHOT_CORRUPT")
    protection_policy = snapshot.schedule_spec.protection_policy
    expected_protection_estimate = (
        _compile_full_fill_protection_estimate(
            policy=protection_policy,
            direction=snapshot.direction,
            legs=snapshot.legs,
            price_tick_size=snapshot.instrument_rules.price_tick_size,
        )
        if protection_policy is not None
        else None
    )
    if snapshot.full_fill_protection_estimate != expected_protection_estimate:
        raise ValueError("ORDER_SCHEDULE_SNAPSHOT_CORRUPT")
    if snapshot.schedule_spec.submission_mode is ScheduleSubmissionMode.PREPROTECTED_PARALLEL:
        if not snapshot.preprotected_parallel_supported:
            raise ValueError("PREPROTECTED_PARALLEL_NOT_VERIFIED")
    elif snapshot.preprotected_parallel_supported:
        raise ValueError("ORDER_SCHEDULE_SNAPSHOT_CORRUPT")
    requested_total = canonical_decimal(
        sum(
            (Decimal(leg.requested_notional) for leg in snapshot.legs),
            Decimal(0),
        )
    )
    effective_total = canonical_decimal(
        sum(
            (Decimal(leg.effective_notional) for leg in snapshot.legs),
            Decimal(0),
        )
    )
    if (
        requested_total != snapshot.requested_total_notional
        or effective_total != snapshot.effective_total_notional
        or any(
            leg.leg_index != index or leg.leg_count != len(snapshot.legs)
            for index, leg in enumerate(snapshot.legs)
        )
    ):
        raise ValueError("ORDER_SCHEDULE_SNAPSHOT_CORRUPT")
    digest_arguments = {
        "schedule_spec": snapshot.schedule_spec,
        "preprotected_parallel_supported": snapshot.preprotected_parallel_supported,
        "venue_ref": snapshot.venue_ref,
        "instrument_ref": snapshot.instrument_ref,
        "direction": snapshot.direction,
        "max_notional": snapshot.max_notional,
        "reference_price": snapshot.reference_price,
        "instrument_rules": snapshot.instrument_rules,
        "requested_total_notional": snapshot.requested_total_notional,
        "effective_total_notional": snapshot.effective_total_notional,
        "legs": snapshot.legs,
    }
    if snapshot.compiler_version == LEGACY_ORDER_SCHEDULE_COMPILER_VERSION:
        digest_payload = _legacy_v2_schedule_digest_payload(**digest_arguments)
    elif snapshot.compiler_version == LEGACY_V3_ORDER_SCHEDULE_COMPILER_VERSION:
        digest_payload = _legacy_v3_schedule_digest_payload(**digest_arguments)
    elif snapshot.compiler_version == LEGACY_V4_ORDER_SCHEDULE_COMPILER_VERSION:
        digest_payload = _legacy_v4_schedule_digest_payload(**digest_arguments)
    elif snapshot.compiler_version == LEGACY_V5_ORDER_SCHEDULE_COMPILER_VERSION:
        digest_payload = _legacy_v5_schedule_digest_payload(**digest_arguments)
    elif snapshot.compiler_version == PREVIOUS_ORDER_SCHEDULE_COMPILER_VERSION:
        digest_payload = _legacy_v6_schedule_digest_payload(**digest_arguments)
    else:
        digest_payload = _schedule_digest_payload(
            compiler_version=snapshot.compiler_version,
            **digest_arguments,
        )
    expected = content_digest(digest_payload)
    if expected != snapshot.schedule_digest:
        raise ValueError("ORDER_SCHEDULE_SNAPSHOT_CORRUPT")


def _gap_weights(distribution: PriceDistribution) -> tuple[Decimal, ...]:
    count = distribution.level_count - 1
    with localcontext() as context:
        context.prec = 128
        if distribution.spacing_mode is PriceSpacingMode.EQUAL:
            weights = tuple(Decimal(1) for _ in range(count))
        elif distribution.spacing_mode is PriceSpacingMode.LINEAR:
            first = Decimal(distribution.linear_start_weight)
            step = Decimal(distribution.linear_step)
            weights = tuple(first + step * index for index in range(count))
        elif distribution.spacing_mode is PriceSpacingMode.GEOMETRIC:
            ratio = Decimal(distribution.geometric_ratio)
            weights = tuple(ratio**index for index in range(count))
        else:
            weights = tuple(Decimal(value) for value in distribution.custom_gap_weights)
    if distribution.spacing_direction is DistributionDirection.HIGH_TO_LOW:
        return tuple(reversed(weights))
    return weights


def _raw_prices(distribution: PricePlan) -> tuple[Decimal | None, ...]:
    if isinstance(distribution, SinglePrice):
        return (
            Decimal(distribution.limit_price)
            if distribution.limit_price is not None
            else None,
        )
    lower = Decimal(distribution.lower_price)
    upper = Decimal(distribution.upper_price)
    weights = _gap_weights(distribution)
    with localcontext() as context:
        context.prec = 128
        total = sum(weights, Decimal(0))
        span = upper - lower
        prices = [lower]
        cumulative = Decimal(0)
        for weight in weights[:-1]:
            cumulative += weight
            prices.append(lower + span * cumulative / total)
        prices.append(upper)
    return tuple(prices)


def _raw_notionals(
    distribution: AmountDistribution,
    level_count: int,
) -> tuple[Decimal, ...]:
    with localcontext() as context:
        context.prec = 128
        if distribution.mode is AmountDistributionMode.FIXED:
            values = tuple(Decimal(distribution.base_notional) for _ in range(level_count))
        elif distribution.mode is AmountDistributionMode.LINEAR:
            base = Decimal(distribution.base_notional)
            step = Decimal(distribution.linear_step)
            values = tuple(base + step * index for index in range(level_count))
        elif distribution.mode is AmountDistributionMode.EXPONENTIAL:
            base = Decimal(distribution.base_notional)
            ratio = Decimal(distribution.exponential_ratio)
            values = tuple(base * ratio**index for index in range(level_count))
        else:
            values = tuple(Decimal(value) for value in distribution.custom_notionals)
    if distribution.direction is DistributionDirection.HIGH_TO_LOW:
        return tuple(reversed(values))
    return values


def _normalized_spec_payload(spec: OrderScheduleSpec) -> dict[str, object]:
    price_plan = spec.price_distribution
    if isinstance(price_plan, SinglePrice):
        price_payload: dict[str, object] = {
            "kind": PricePlanKind.SINGLE.value,
            "limit_price": price_plan.limit_price,
        }
    else:
        price_payload = {
            "kind": PricePlanKind.LADDER.value,
            "lower_price": price_plan.lower_price,
            "upper_price": price_plan.upper_price,
            "level_count": price_plan.level_count,
            "spacing_mode": price_plan.spacing_mode.value,
            "spacing_direction": price_plan.spacing_direction.value,
        }
        if price_plan.spacing_mode is PriceSpacingMode.LINEAR:
            price_payload.update(
                linear_start_weight=price_plan.linear_start_weight,
                linear_step=price_plan.linear_step,
            )
        elif price_plan.spacing_mode is PriceSpacingMode.GEOMETRIC:
            price_payload["geometric_ratio"] = price_plan.geometric_ratio
        elif price_plan.spacing_mode is PriceSpacingMode.CUSTOM_WEIGHTS:
            price_payload["custom_gap_weights"] = price_plan.custom_gap_weights

    amounts = spec.amount_distribution
    amount_payload: dict[str, object] = {
        "mode": amounts.mode.value,
        "direction": amounts.direction.value,
    }
    if amounts.mode is AmountDistributionMode.FIXED:
        amount_payload["base_notional"] = amounts.base_notional
    elif amounts.mode is AmountDistributionMode.LINEAR:
        amount_payload.update(
            base_notional=amounts.base_notional,
            linear_step=amounts.linear_step,
        )
    elif amounts.mode is AmountDistributionMode.EXPONENTIAL:
        amount_payload.update(
            base_notional=amounts.base_notional,
            exponential_ratio=amounts.exponential_ratio,
        )
    else:
        amount_payload["custom_notionals"] = amounts.custom_notionals
    payload: dict[str, object] = {
        "price_distribution": price_payload,
        "amount_distribution": amount_payload,
        "venue_policy": spec.venue_policy.model_dump(mode="json", exclude_none=True),
        "submission_mode": spec.submission_mode.value,
        "submission_order": spec.submission_order.value,
        "entry_conditions": spec.entry_conditions.model_dump(mode="json"),
        "protection_policy": None,
        "dynamic_rules": [
            rule.model_dump(mode="json") for rule in spec.dynamic_rules
        ],
    }
    if spec.entry_program is not None:
        payload["entry_program"] = spec.entry_program.model_dump(mode="json")
    if spec.protection_policy is not None:
        protection_payload = spec.protection_policy.model_dump(mode="json")
        # Older frozen schedules predate the optional aggregate budget field.
        # Omitting only that absent field preserves their exact digest.
        if protection_payload.get("full_fill_loss_budget") is None:
            protection_payload.pop("full_fill_loss_budget", None)
        payload["protection_policy"] = protection_payload
    return payload


def _quantize_price(value: Decimal, tick: Decimal, direction: Direction) -> Decimal:
    rounding = ROUND_DOWN if direction is Direction.LONG else ROUND_UP
    return (value / tick).to_integral_value(rounding=rounding) * tick


def _floor_quantity(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def compile_order_schedule(
    spec: OrderScheduleSpec,
    rules: InstrumentOrderRules,
    *,
    venue_ref: str,
    instrument_ref: str,
    direction: Direction,
    max_notional: str,
    schedule_ref: str,
    reference_price: str | None = None,
    preprotected_parallel_supported: bool = False,
    evaluated_at: datetime | None = None,
) -> OrderSchedulePreview:
    """Compile one immutable decision without venue access or runtime state.

    ``evaluated_at`` is the caller-observed decision time for relative venue
    deadlines. The rules cutoff remains provenance for instrument limits and
    must not stand in for the current preview or activation time.
    """

    for value, code in (
        (venue_ref, "ORDER_SCHEDULE_VENUE_REF_INVALID"),
        (instrument_ref, "ORDER_SCHEDULE_INSTRUMENT_REF_INVALID"),
        (schedule_ref, "ORDER_SCHEDULE_REF_INVALID"),
    ):
        if not value or value.strip() != value or len(value) > 160:
            raise ValueError(code)
    if evaluated_at is not None and evaluated_at.utcoffset() is None:
        raise ValueError("ORDER_SCHEDULE_EVALUATED_AT_TIMEZONE_REQUIRED")
    maximum = _bounded_decimal(
        max_notional,
        code="ORDER_SCHEDULE_MAX_NOTIONAL_INVALID",
        positive=True,
    )
    program = spec.resolved_entry_program
    base_prices = _raw_prices(spec.price_distribution)
    raw_prices = (
        tuple(base_prices[0] for _ in range(program.slice_count))
        if program.kind is EntryProgramKind.TIME_SLICED
        else base_prices
    )
    release_offsets = (
        tuple(
            program.first_slice_delay_seconds
            + index * program.slice_interval_seconds
            for index in range(program.slice_count)
        )
        if program.kind is EntryProgramKind.TIME_SLICED
        else tuple(0 for _ in raw_prices)
    )
    requires_reference = any(price is None for price in raw_prices)
    reference = (
        _bounded_decimal(
            reference_price,
            code="ORDER_SCHEDULE_REFERENCE_PRICE_INVALID",
            positive=True,
        )
        if requires_reference and reference_price is not None
        else None
    )
    raw_notionals = _raw_notionals(spec.amount_distribution, len(raw_prices))
    tick = Decimal(rules.price_tick_size)
    if spec.venue_policy.order_type is VenueOrderType.MARKET:
        step = Decimal(rules.market_quantity_step)
        min_quantity = Decimal(rules.min_market_quantity)
        max_quantity = Decimal(rules.max_market_quantity)
    else:
        step = Decimal(rules.limit_quantity_step)
        min_quantity = Decimal(rules.min_limit_quantity)
        max_quantity = Decimal(rules.max_limit_quantity)
    min_notional = Decimal(rules.min_notional)
    min_price = Decimal(rules.min_price)
    max_price = Decimal(rules.max_price)
    normalized_prices = tuple(
        None if price is None else _quantize_price(price, tick, direction)
        for price in raw_prices
    )
    issues: list[ScheduleIssue] = []
    if (
        spec.submission_mode is ScheduleSubmissionMode.PREPROTECTED_PARALLEL
        and not preprotected_parallel_supported
    ):
        issues.append(
            ScheduleIssue(
                code="PREPROTECTED_PARALLEL_NOT_VERIFIED",
                field="submission_mode",
            )
        )
    if spec.venue_policy.time_in_force is VenueTimeInForce.GTD:
        cutoff = evaluated_at or datetime.fromisoformat(rules.source_cutoff)
        expire_at = spec.venue_policy.expire_at
        if (
            expire_at is None
            or expire_at <= cutoff + timedelta(seconds=BINANCE_GTD_MIN_LEAD_SECONDS)
        ):
            issues.append(
                ScheduleIssue(
                    code="GTD_EXPIRY_TOO_SOON",
                    field="venue_policy.expire_at",
                )
            )
    explicit_prices = tuple(price for price in normalized_prices if price is not None)
    if (
        program.kind is not EntryProgramKind.TIME_SLICED
        and len(set(explicit_prices)) != len(explicit_prices)
    ):
        issues.append(
            ScheduleIssue(
                code="ORDER_SCHEDULE_PRICE_COLLISION",
                field="price_distribution",
            )
        )
    if spec.protection_policy is not None:
        for index, price in enumerate(normalized_prices):
            if price is None:
                # MARKET and priceMatch orders have no known fill price until
                # the venue reports one; the runtime repeats this same check.
                continue
            try:
                compile_protection_targets(
                    spec.protection_policy,
                    direction=direction.value,
                    fill_price=canonical_decimal(price),
                    price_tick_size=rules.price_tick_size,
                )
            except ValueError as exc:
                if str(exc) != "PROTECTION_PRICE_INVALID":
                    raise
                issues.append(
                    ScheduleIssue(
                        code="PROTECTION_PRICE_INVALID",
                        field="protection_policy",
                        leg_index=index,
                    )
                )
    if requires_reference and reference is None:
        issues.append(
            ScheduleIssue(
                code="ORDER_SCHEDULE_REFERENCE_PRICE_REQUIRED",
                field="reference_price",
            )
        )
    requested_total = sum(raw_notionals, Decimal(0))
    if requested_total > maximum:
        issues.append(
            ScheduleIssue(
                code="ORDER_SCHEDULE_TOTAL_EXCEEDS_PLAN_LIMIT",
                field="amount_distribution",
            )
        )

    legs: list[CompiledOrderLeg] = []
    effective_total = Decimal(0)
    for index, (raw_price, price, requested_notional, release_after_seconds) in enumerate(
        zip(
            raw_prices,
            normalized_prices,
            raw_notionals,
            release_offsets,
            strict=True,
        )
    ):
        if price is not None and (price < min_price or price > max_price):
            issues.append(
                ScheduleIssue(
                    code="ORDER_SCHEDULE_PRICE_OUTSIDE_VENUE_LIMIT",
                    field="price_distribution",
                    leg_index=index,
                )
            )
        sizing_price = price if price is not None else reference
        if sizing_price is None or sizing_price <= 0:
            continue
        with localcontext() as context:
            context.prec = 128
            quantity = _floor_quantity(requested_notional / sizing_price, step)
            effective_notional = quantity * sizing_price
        if quantity < min_quantity:
            issues.append(
                ScheduleIssue(
                    code="ORDER_SCHEDULE_QUANTITY_BELOW_MINIMUM",
                    field="amount_distribution",
                    leg_index=index,
                )
            )
        if quantity > max_quantity:
            issues.append(
                ScheduleIssue(
                    code="ORDER_SCHEDULE_QUANTITY_ABOVE_MAXIMUM",
                    field="amount_distribution",
                    leg_index=index,
                )
            )
        if effective_notional < min_notional:
            issues.append(
                ScheduleIssue(
                    code="ORDER_SCHEDULE_NOTIONAL_BELOW_MINIMUM",
                    field="amount_distribution",
                    leg_index=index,
                )
            )
        effective_total += effective_notional
        legs.append(
            CompiledOrderLeg(
                leg_index=index,
                leg_count=len(raw_prices),
                release_after_seconds=release_after_seconds,
                raw_price=(canonical_decimal(raw_price) if raw_price is not None else None),
                price=canonical_decimal(price) if price is not None else None,
                sizing_price=canonical_decimal(sizing_price),
                requested_notional=canonical_decimal(requested_notional),
                quantity=canonical_decimal(quantity),
                effective_notional=canonical_decimal(effective_notional),
            )
        )

    normalized_legs = tuple(legs)
    full_fill_protection_estimate = None
    if spec.protection_policy is not None and normalized_legs:
        try:
            full_fill_protection_estimate = _compile_full_fill_protection_estimate(
                policy=spec.protection_policy,
                direction=direction,
                legs=normalized_legs,
                price_tick_size=rules.price_tick_size,
            )
        except ValueError as exc:
            if str(exc) != "PROTECTION_INSIDE_ENTRY_RANGE":
                raise
            issues.append(
                ScheduleIssue(
                    code="PROTECTION_INSIDE_ENTRY_RANGE",
                    field="protection_policy.initial_stop.distance_bps",
                )
            )

    normalized_maximum = canonical_decimal(maximum)
    normalized_reference = canonical_decimal(reference) if reference is not None else None
    requested_total_text = canonical_decimal(requested_total)
    effective_total_text = canonical_decimal(effective_total)
    digest_payload = _schedule_digest_payload(
        compiler_version=ORDER_SCHEDULE_COMPILER_VERSION,
        schedule_spec=spec,
        preprotected_parallel_supported=preprotected_parallel_supported,
        venue_ref=venue_ref,
        instrument_ref=instrument_ref,
        direction=direction,
        max_notional=normalized_maximum,
        reference_price=normalized_reference,
        instrument_rules=rules,
        requested_total_notional=requested_total_text,
        effective_total_notional=effective_total_text,
        legs=tuple(legs),
    )
    schedule_digest = content_digest(digest_payload)
    if issues:
        legs = []
        effective_total = Decimal(0)
    return OrderSchedulePreview(
        valid=not issues,
        compiler_version=ORDER_SCHEDULE_COMPILER_VERSION,
        schedule_ref=schedule_ref,
        schedule_digest=schedule_digest,
        schedule_spec=spec,
        preprotected_parallel_supported=preprotected_parallel_supported,
        venue_ref=venue_ref,
        instrument_ref=instrument_ref,
        direction=direction,
        max_notional=normalized_maximum,
        reference_price=normalized_reference,
        instrument_rules=rules,
        instrument_rules_digest=rules.digest,
        source_cutoff=rules.source_cutoff,
        requested_total_notional=requested_total_text,
        effective_total_notional=effective_total_text,
        full_fill_protection_estimate=full_fill_protection_estimate,
        normalized_legs=normalized_legs,
        legs=tuple(legs),
        issues=tuple(issues),
    )
