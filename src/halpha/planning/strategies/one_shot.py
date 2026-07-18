"""Pure one-shot Donchian/ATR decision and exact Decimal sizing logic.

This module deliberately imports no NautilusTrader order, Strategy, node, or
execution API. Native indicator calculation is supplied through the separate
indicator boundary; this class only evaluates its immutable output.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from halpha.domain_values import canonical_decimal, content_digest, decimal_from_string
from halpha.planning.registry import Direction, ONE_SHOT_STRATEGY_ID, OneShotParameters


class RiskDirection(StrEnum):
    INCREASE = "INCREASE"
    REDUCE = "REDUCE"


class ActivationStrategyState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entry_opportunity_consumed: bool = False
    lifecycle: str = "RUNNING"
    run_state: str = "ACTIVE"
    new_risk_allowed: bool = True


class NativeIndicatorSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    upper: str
    lower: str
    atr: str
    initialized: bool
    source_digest: str
    source_cutoff_ns: int

    @field_validator("upper", "lower", "atr")
    @classmethod
    def finite_values(cls, value: str) -> str:
        return canonical_decimal(decimal_from_string(value, code="INDICATOR_VALUE_INVALID"))


class InstrumentQuantityRules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step_size: str
    price_tick_size: str
    min_quantity: str
    max_market_quantity: str
    min_notional: str

    @field_validator(
        "step_size",
        "price_tick_size",
        "min_quantity",
        "max_market_quantity",
        "min_notional",
    )
    @classmethod
    def positive_values(cls, value: str) -> str:
        return canonical_decimal(
            decimal_from_string(value, code="INSTRUMENT_RULE_INVALID", positive=True)
        )


class EntryEvaluationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    activation_id: str
    instrument_id: str
    source_identity: str
    source_cutoff: datetime
    input_digest: str
    decision_at: datetime
    valid_until: datetime
    confirmation_closes: tuple[str, ...]
    indicators: NativeIndicatorSnapshot
    reference_price: str
    reference_source: str
    max_allowed_loss: str
    max_notional: str
    max_margin: str
    effective_leverage: str
    taker_fee_rate: str
    rules: InstrumentQuantityRules

    @field_validator(
        "reference_price",
        "max_allowed_loss",
        "max_notional",
        "max_margin",
        "effective_leverage",
        "rules",
    )
    @classmethod
    def retain_values(cls, value: object) -> object:
        return value

    @field_validator("confirmation_closes")
    @classmethod
    def closes_are_positive(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values:
            raise ValueError("CONFIRMATION_BARS_MISSING")
        return tuple(
            canonical_decimal(decimal_from_string(value, code="BAR_VALUE_INVALID", positive=True))
            for value in values
        )

    @model_validator(mode="after")
    def time_window_is_valid(self) -> EntryEvaluationInput:
        if not self.source_identity.startswith(f"{self.activation_id}:"):
            raise ValueError("SOURCE_IDENTITY_MISMATCH")
        if self.source_cutoff > self.decision_at:
            raise ValueError("SOURCE_CUTOFF_AFTER_DECISION")
        if self.valid_until <= self.decision_at:
            raise ValueError("PROPOSAL_WINDOW_INVALID")
        for field in (
            "reference_price",
            "max_allowed_loss",
            "max_notional",
            "max_margin",
            "effective_leverage",
        ):
            decimal_from_string(getattr(self, field), code="SIZING_INPUT_INVALID", positive=True)
        fee = decimal_from_string(
            self.taker_fee_rate,
            code="SIZING_INPUT_INVALID",
            non_negative=True,
        )
        if fee >= 1:
            raise ValueError("FEE_RATE_INVALID")
        return self


class EntryRiskContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    trigger_atr: str
    initial_stop_atr_multiple: str
    take_profit_1_r: str
    take_profit_1_fraction: str
    take_profit_2_r: str
    max_hold_bars_15m: int
    indicator_source_digest: str
    indicator_source_cutoff_ns: int
    quantity_step: str
    price_tick_size: str

    @field_validator(
        "trigger_atr",
        "initial_stop_atr_multiple",
        "take_profit_1_r",
        "take_profit_1_fraction",
        "take_profit_2_r",
        "quantity_step",
        "price_tick_size",
    )
    @classmethod
    def positive_context_values(cls, value: str) -> str:
        return canonical_decimal(
            decimal_from_string(value, code="ENTRY_RISK_CONTEXT_INVALID", positive=True)
        )


class StrategyProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy_id: str
    activation_id: str
    rule_id: str
    source_identity: str
    source_cutoff: datetime
    input_digest: str
    instrument_id: str
    direction: Direction
    action_profile: str
    risk_direction: RiskDirection
    quantity: str
    reference_price: str
    reference_source: str
    reason_code: str
    valid_until: datetime
    entry_risk_context: EntryRiskContext | None = None
    proposal_digest: str


class StrategyEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reason_code: str
    proposal: StrategyProposal | None = None


def _floor_to_step(quantity: Decimal, step: Decimal) -> Decimal:
    units = (quantity / step).to_integral_value(rounding=ROUND_DOWN)
    return units * step


class OneShotDonchianAtrLogic:
    """Deterministic decision object; activation state is always explicit input."""

    strategy_id = ONE_SHOT_STRATEGY_ID

    def __init__(self, parameters: OneShotParameters) -> None:
        self.parameters = parameters

    def evaluate_entry(
        self,
        evaluation: EntryEvaluationInput,
        state: ActivationStrategyState,
    ) -> StrategyEvaluation:
        if state.entry_opportunity_consumed:
            return StrategyEvaluation(reason_code="ENTRY_OPPORTUNITY_CONSUMED")
        if state.lifecycle != "RUNNING" or state.run_state != "ACTIVE" or not state.new_risk_allowed:
            return StrategyEvaluation(reason_code="NEW_RISK_NOT_ALLOWED")
        if not evaluation.indicators.initialized:
            return StrategyEvaluation(reason_code="INDICATORS_NOT_INITIALIZED")
        if len(evaluation.confirmation_closes) != self.parameters.confirmation_bars_1m:
            return StrategyEvaluation(reason_code="CONFIRMATION_WINDOW_INCOMPLETE")

        upper = Decimal(evaluation.indicators.upper)
        lower = Decimal(evaluation.indicators.lower)
        atr = Decimal(evaluation.indicators.atr)
        if upper <= lower or atr <= 0:
            return StrategyEvaluation(reason_code="INDICATOR_VALUE_INVALID")
        closes = tuple(Decimal(value) for value in evaluation.confirmation_closes)
        extension = Decimal(self.parameters.max_entry_extension_atr) * atr
        if self.parameters.direction is Direction.LONG:
            triggered = all(close > upper for close in closes) and closes[-1] <= upper + extension
        else:
            triggered = all(close < lower for close in closes) and closes[-1] >= lower - extension
        if not triggered:
            return StrategyEvaluation(reason_code="ENTRY_CONDITION_FALSE")

        reference_price = Decimal(evaluation.reference_price)
        stop_distance = Decimal(self.parameters.initial_stop_atr_multiple) * atr
        risk_budget = Decimal(evaluation.max_allowed_loss) * Decimal("0.80")
        fee = Decimal(evaluation.taker_fee_rate)
        two_side_cost = reference_price * (fee * 2 + Decimal("0.0010") * 2)
        candidates = (
            risk_budget / (stop_distance + two_side_cost),
            Decimal(evaluation.max_notional) / (reference_price * Decimal("1.0020")),
            Decimal(evaluation.max_margin)
            * Decimal(evaluation.effective_leverage)
            / (reference_price * Decimal("1.0020")),
            Decimal(evaluation.rules.max_market_quantity),
        )
        quantity = _floor_to_step(min(candidates), Decimal(evaluation.rules.step_size))
        if quantity < Decimal(evaluation.rules.step_size) * 2:
            return StrategyEvaluation(reason_code="QUANTITY_BELOW_TAKE_PROFIT_SPLIT_MINIMUM")
        if quantity < Decimal(evaluation.rules.min_quantity):
            return StrategyEvaluation(reason_code="QUANTITY_BELOW_MINIMUM")
        if quantity * reference_price < Decimal(evaluation.rules.min_notional):
            return StrategyEvaluation(reason_code="NOTIONAL_BELOW_MINIMUM")

        proposal_fields = {
            "strategy_id": self.strategy_id,
            "activation_id": evaluation.activation_id,
            "rule_id": "ENTRY_BREAKOUT",
            "source_identity": evaluation.source_identity,
            "source_cutoff": evaluation.source_cutoff,
            "input_digest": evaluation.input_digest,
            "instrument_id": evaluation.instrument_id,
            "direction": self.parameters.direction,
            "action_profile": "ENTRY_MARKET",
            "risk_direction": RiskDirection.INCREASE,
            "quantity": canonical_decimal(quantity),
            "reference_price": canonical_decimal(reference_price),
            "reference_source": evaluation.reference_source,
            "reason_code": "ENTRY_BREAKOUT_CONFIRMED",
            "valid_until": evaluation.valid_until,
            "entry_risk_context": EntryRiskContext(
                trigger_atr=canonical_decimal(atr),
                initial_stop_atr_multiple=self.parameters.initial_stop_atr_multiple,
                take_profit_1_r=self.parameters.take_profit_1_r,
                take_profit_1_fraction=self.parameters.take_profit_1_fraction,
                take_profit_2_r=self.parameters.take_profit_2_r,
                max_hold_bars_15m=self.parameters.max_hold_bars_15m,
                indicator_source_digest=evaluation.indicators.source_digest,
                indicator_source_cutoff_ns=evaluation.indicators.source_cutoff_ns,
                quantity_step=evaluation.rules.step_size,
                price_tick_size=evaluation.rules.price_tick_size,
            ),
        }
        return StrategyEvaluation(
            reason_code="PROPOSAL_CREATED",
            proposal=StrategyProposal(
                **proposal_fields,
                proposal_digest=content_digest(proposal_fields),
            ),
        )
