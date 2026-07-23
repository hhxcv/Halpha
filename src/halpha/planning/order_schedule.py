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
    ProfitRCondition,
    ProtectionPolicy,
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
    model_config = ConfigDict(extra="forbid", frozen=True)


ORDER_SCHEDULE_COMPILER_VERSION = "3"
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
    display_quantity: str | None = None
    expire_at: datetime | None = None

    @field_validator("display_quantity")
    @classmethod
    def optional_positive_quantity(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return canonical_decimal(
            _bounded_decimal(
                value,
                code="VENUE_ORDER_POLICY_INVALID",
                positive=True,
            )
        )

    @model_validator(mode="after")
    def policy_is_supported(self) -> VenueOrderPolicy:
        if self.order_type is VenueOrderType.MARKET:
            if (
                self.time_in_force is not None
                or self.post_only
                or self.price_match is not None
                or self.display_quantity is not None
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
        if self.display_quantity is not None:
            raise ValueError("DISPLAY_QUANTITY_NOT_DEMO_VERIFIED")
        if self.time_in_force is VenueTimeInForce.GTD:
            if self.expire_at is None or self.expire_at.utcoffset() is None:
                raise ValueError("GTD_EXPIRY_REQUIRED")
        elif self.expire_at is not None:
            raise ValueError("GTD_EXPIRY_TIME_IN_FORCE_CONFLICT")
        return self


class OrderScheduleSpec(ScheduleModel):
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
        level_count = (
            1
            if isinstance(self.price_distribution, SinglePrice)
            else self.price_distribution.level_count
        )
        if (
            amounts.mode is AmountDistributionMode.CUSTOM
            and len(amounts.custom_notionals)
            != level_count
        ):
            raise ValueError("ORDER_SCHEDULE_CUSTOM_AMOUNT_COUNT_INVALID")
        policy = self.venue_policy
        if isinstance(self.price_distribution, SinglePrice):
            if amounts.mode is not AmountDistributionMode.FIXED:
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
        validate_dynamic_rules(
            self.dynamic_rules,
            protection_policy=self.protection_policy,
        )
        if any(isinstance(rule, CancelOnShockRule) for rule in self.dynamic_rules):
            if (
                self.submission_mode is not ScheduleSubmissionMode.SERIAL_PROTECTED
                or policy.order_type is not VenueOrderType.LIMIT
            ):
                raise ValueError("CANCEL_ON_SHOCK_POLICY_CONFLICT")
        if any(isinstance(rule, ExpireRemainingRule) for rule in self.dynamic_rules):
            if policy.order_type is not VenueOrderType.LIMIT:
                raise ValueError("EXPIRE_REMAINING_POLICY_CONFLICT")
        if (
            self.submission_mode is ScheduleSubmissionMode.PREPROTECTED_PARALLEL
            and self.protection_policy is None
        ):
            raise ValueError("PREPROTECTED_PARALLEL_PROTECTION_REQUIRED")
        return self


def validate_direct_execution_schedule(spec: OrderScheduleSpec | None) -> None:
    """Reject shared schedule features not yet consumed by direct execution."""

    if spec is None:
        raise ValueError("DIRECT_EXECUTION_SCHEDULE_REQUIRED")
    if spec.protection_policy is None:
        raise ValueError("DIRECT_EXECUTION_PROTECTION_REQUIRED")
    take_profit_ladder = spec.protection_policy.take_profit_ladder
    if take_profit_ladder is not None and (
        len(take_profit_ladder.levels) != 1
        or Decimal(take_profit_ladder.levels[0].quantity_fraction) != Decimal(1)
    ):
        # Direct protection is currently created for every individual fill.
        # Only a single 100% target remains executable when the venue reports a
        # minimum-step partial fill; all other splits can quantize a configured
        # level to zero after exposure already exists.
        raise ValueError("DIRECT_EXECUTION_TAKE_PROFIT_SPLIT_NOT_VERIFIED")
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
    if any(isinstance(rule, SteppedProtectionRule) for rule in spec.dynamic_rules):
        raise ValueError("DIRECT_EXECUTION_STEPPED_PROTECTION_UNSUPPORTED")
    if any(
        isinstance(rule, CancelOnShockRule) and rule.max_triggers != 1
        for rule in spec.dynamic_rules
    ):
        raise ValueError(
            "DIRECT_EXECUTION_CANCEL_ON_SHOCK_MAX_TRIGGERS_UNSUPPORTED"
        )


def direct_allowed_action_profiles(
    spec: OrderScheduleSpec | None,
) -> frozenset[str]:
    """Derive the exact action authority consumed by one direct schedule."""

    validate_direct_execution_schedule(spec)
    assert spec is not None
    assert spec.protection_policy is not None

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
    raw_price: str | None
    price: str | None
    sizing_price: str
    requested_notional: str
    quantity: str
    effective_notional: str


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
    normalized_legs: tuple[CompiledOrderLeg, ...]
    legs: tuple[CompiledOrderLeg, ...]
    issues: tuple[ScheduleIssue, ...]


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


def _legacy_v2_instrument_rules_digest(rules: InstrumentOrderRules) -> str:
    """Reproduce the cutoff-independent rules digest persisted by compiler v2."""

    return rules.digest


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
    """Reproduce compiler v2 without weakening current digest semantics."""

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
    # Compiler v2 already excluded the observation cutoff from the standalone
    # rules digest, but still treated it as executable schedule content. Keep
    # that hybrid historical algorithm explicit so persisted v2 snapshots
    # remain verifiable while v3 confirmations stay stable across observations.
    payload["instrument_rules"] = instrument_rules.model_dump(mode="json")
    return payload


def validate_order_schedule_snapshot(snapshot: OrderSchedulePreview) -> None:
    """Reject a persisted snapshot whose full executable content is not self-consistent."""

    if not snapshot.valid or snapshot.issues or snapshot.legs != snapshot.normalized_legs:
        raise ValueError("ORDER_SCHEDULE_SNAPSHOT_INVALID")
    if snapshot.compiler_version not in {
        LEGACY_ORDER_SCHEDULE_COMPILER_VERSION,
        ORDER_SCHEDULE_COMPILER_VERSION,
    }:
        raise ValueError("ORDER_SCHEDULE_COMPILER_UNSUPPORTED")
    if snapshot.source_cutoff != snapshot.instrument_rules.source_cutoff:
        raise ValueError("ORDER_SCHEDULE_SNAPSHOT_CORRUPT")
    expected_rules_digest = (
        _legacy_v2_instrument_rules_digest(snapshot.instrument_rules)
        if snapshot.compiler_version == LEGACY_ORDER_SCHEDULE_COMPILER_VERSION
        else snapshot.instrument_rules.digest
    )
    if snapshot.instrument_rules_digest != expected_rules_digest:
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
    return {
        "price_distribution": price_payload,
        "amount_distribution": amount_payload,
        "venue_policy": spec.venue_policy.model_dump(mode="json", exclude_none=True),
        "submission_mode": spec.submission_mode.value,
        "submission_order": spec.submission_order.value,
        "entry_conditions": spec.entry_conditions.model_dump(mode="json"),
        "protection_policy": (
            spec.protection_policy.model_dump(mode="json")
            if spec.protection_policy is not None
            else None
        ),
        "dynamic_rules": [
            rule.model_dump(mode="json") for rule in spec.dynamic_rules
        ],
    }


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
) -> OrderSchedulePreview:
    """Compile one immutable decision without venue access or runtime state."""

    for value, code in (
        (venue_ref, "ORDER_SCHEDULE_VENUE_REF_INVALID"),
        (instrument_ref, "ORDER_SCHEDULE_INSTRUMENT_REF_INVALID"),
        (schedule_ref, "ORDER_SCHEDULE_REF_INVALID"),
    ):
        if not value or value.strip() != value or len(value) > 160:
            raise ValueError(code)
    maximum = _bounded_decimal(
        max_notional,
        code="ORDER_SCHEDULE_MAX_NOTIONAL_INVALID",
        positive=True,
    )
    raw_prices = _raw_prices(spec.price_distribution)
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
        cutoff = datetime.fromisoformat(rules.source_cutoff)
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
    if len(set(explicit_prices)) != len(explicit_prices):
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
    for index, (raw_price, price, requested_notional) in enumerate(
        zip(raw_prices, normalized_prices, raw_notionals, strict=True)
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
                raw_price=(canonical_decimal(raw_price) if raw_price is not None else None),
                price=canonical_decimal(price) if price is not None else None,
                sizing_price=canonical_decimal(sizing_price),
                requested_notional=canonical_decimal(requested_notional),
                quantity=canonical_decimal(quantity),
                effective_notional=canonical_decimal(effective_notional),
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
    normalized_legs = tuple(legs)
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
        normalized_legs=normalized_legs,
        legs=tuple(legs),
        issues=tuple(issues),
    )
