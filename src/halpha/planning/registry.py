"""Build-time code strategy registry and authoritative parameter validation."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from halpha.domain_values import canonical_decimal, content_digest, decimal_from_string
from halpha.source_identity import source_file_sha256


ONE_SHOT_STRATEGY_ID = "ONE_SHOT_DONCHIAN_ATR_BREAKOUT"
ONE_SHOT_STRATEGY_VERSION = "1.0.1"
PARAMETER_SCHEMA_VERSION = "1.3.0"


class Direction(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


class PlanParameterDisplayFormat(StrEnum):
    VALUE = "VALUE"
    PERCENT = "PERCENT"
    BOOLEAN_LABEL = "BOOLEAN_LABEL"


class PlanKeyParameterDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    parameter_key: str
    label: str
    display_format: PlanParameterDisplayFormat = PlanParameterDisplayFormat.VALUE
    unit: str | None = None
    true_label: str | None = None
    false_label: str | None = None

    @model_validator(mode="after")
    def boolean_labels_match_format(self) -> PlanKeyParameterDefinition:
        labels = (self.true_label, self.false_label)
        if self.display_format is PlanParameterDisplayFormat.BOOLEAN_LABEL:
            if any(label is None for label in labels):
                raise ValueError("PLAN_PARAMETER_BOOLEAN_LABEL_MISSING")
        elif any(label is not None for label in labels):
            raise ValueError("PLAN_PARAMETER_BOOLEAN_LABEL_UNEXPECTED")
        return self


class OneShotParameters(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=False,
        validate_default=True,
    )

    direction: Direction
    demo_immediate_entry: bool = False
    channel_lookback_15m: int = Field(default=20, ge=4, le=96)
    confirmation_bars_1m: int = Field(default=2, ge=1, le=3)
    initial_stop_atr_multiple: str = "1.5"
    max_entry_extension_atr: str = "0.5"
    take_profit_1_r: str = "1.5"
    take_profit_1_fraction: str = "0.50"
    take_profit_2_r: str = "3.0"
    max_hold_bars_15m: int = Field(default=4, ge=4, le=672)
    entry_valid_minutes: int = Field(default=60, ge=15, le=10080)

    @field_validator(
        "initial_stop_atr_multiple",
        "max_entry_extension_atr",
        "take_profit_1_r",
        "take_profit_1_fraction",
        "take_profit_2_r",
    )
    @classmethod
    def validate_decimal_strings(cls, value: str, info: Any) -> str:
        ranges = {
            "initial_stop_atr_multiple": (Decimal("1.0"), Decimal("3.0")),
            "max_entry_extension_atr": (Decimal("0.1"), Decimal("1.0")),
            "take_profit_1_r": (Decimal("1.0"), Decimal("3.0")),
            "take_profit_1_fraction": (Decimal("0.25"), Decimal("0.75")),
            "take_profit_2_r": (Decimal("2.0"), Decimal("6.0")),
        }
        parsed = decimal_from_string(value, code="PARAMETER_INVALID", positive=True)
        minimum, maximum = ranges[info.field_name]
        if parsed < minimum or parsed > maximum:
            raise ValueError("PARAMETER_OUT_OF_RANGE")
        return canonical_decimal(parsed)

    @model_validator(mode="after")
    def validate_cross_constraints(self) -> OneShotParameters:
        if Decimal(self.take_profit_2_r) <= Decimal(self.take_profit_1_r):
            raise ValueError("TAKE_PROFIT_ORDER_INVALID")
        return self

    @property
    def effective_confirmation_bars_1m(self) -> int:
        return 1 if self.demo_immediate_entry else self.confirmation_bars_1m


class CodeStrategyDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy_id: str
    strategy_version: str
    display_name: str
    value_logic: str
    applicable_scenarios: str
    execution_behavior: str
    implementation_path: str
    implementation_digest: str
    parameter_schema_version: str
    parameter_schema: dict[str, Any]
    native_indicators: tuple[str, ...]
    allowed_action_profiles: tuple[str, ...]
    supported_directions: tuple[Direction, ...]
    economic_scope: dict[str, Any]
    plan_key_parameters: tuple[PlanKeyParameterDefinition, ...]

    @model_validator(mode="after")
    def plan_key_parameters_belong_to_schema(self) -> CodeStrategyDefinition:
        schema_keys = set(self.parameter_schema.get("properties", {}))
        parameter_keys = [item.parameter_key for item in self.plan_key_parameters]
        if len(parameter_keys) != len(set(parameter_keys)):
            raise ValueError("PLAN_KEY_PARAMETER_DUPLICATED")
        if not set(parameter_keys).issubset(schema_keys):
            raise ValueError("PLAN_KEY_PARAMETER_UNKNOWN")
        return self


class FixedStrategyPlanBasis(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy_id: str
    strategy_version: str
    implementation_digest: str
    parameter_schema_version: str
    normalized_parameters: dict[str, Any]
    parameter_digest: str
    fact_input_contract: dict[str, Any]
    allowed_action_profiles: tuple[str, ...]
    economic_scope: dict[str, Any]
    product_build_id: str = Field(pattern=r"^[0-9a-f]{64}$")


def _implementation_path() -> Path:
    return Path(__file__).resolve().parent / "strategies" / "one_shot.py"


def _implementation_digest() -> str:
    return source_file_sha256(_implementation_path())


def _parameter_schema() -> dict[str, Any]:
    decimal_pattern = r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$"
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"urn:halpha:strategy:{ONE_SHOT_STRATEGY_ID}:parameters:{PARAMETER_SCHEMA_VERSION}",
        "title": "单次 Donchian 突破与 ATR 风险退出",
        "type": "object",
        "additionalProperties": False,
        "required": ["direction"],
        "properties": {
            "direction": {"type": "string", "enum": ["LONG", "SHORT"]},
            "demo_immediate_entry": {"type": "boolean", "default": False},
            "channel_lookback_15m": {
                "type": "integer",
                "minimum": 4,
                "maximum": 96,
                "default": 20,
            },
            "confirmation_bars_1m": {
                "type": "integer",
                "minimum": 1,
                "maximum": 3,
                "default": 2,
            },
            "initial_stop_atr_multiple": {
                "type": "string",
                "pattern": decimal_pattern,
                "default": "1.5",
                "x-halpha-minimum": "1.0",
                "x-halpha-maximum": "3.0",
            },
            "max_entry_extension_atr": {
                "type": "string",
                "pattern": decimal_pattern,
                "default": "0.5",
                "x-halpha-minimum": "0.1",
                "x-halpha-maximum": "1.0",
            },
            "take_profit_1_r": {
                "type": "string",
                "pattern": decimal_pattern,
                "default": "1.5",
                "x-halpha-minimum": "1.0",
                "x-halpha-maximum": "3.0",
            },
            "take_profit_1_fraction": {
                "type": "string",
                "pattern": decimal_pattern,
                "default": "0.50",
                "x-halpha-minimum": "0.25",
                "x-halpha-maximum": "0.75",
            },
            "take_profit_2_r": {
                "type": "string",
                "pattern": decimal_pattern,
                "default": "3.0",
                "x-halpha-minimum": "2.0",
                "x-halpha-maximum": "6.0",
            },
            "max_hold_bars_15m": {
                "type": "integer",
                "minimum": 4,
                "maximum": 672,
                "default": 4,
            },
            "entry_valid_minutes": {
                "type": "integer",
                "minimum": 15,
                "maximum": 10080,
                "default": 60,
            },
        },
        "allOf": [
            {
                "x-halpha-cross-constraint": {
                    "code": "TAKE_PROFIT_ORDER_INVALID",
                    "expression": "take_profit_2_r > take_profit_1_r",
                }
            }
        ],
    }


def _definition() -> CodeStrategyDefinition:
    return CodeStrategyDefinition(
        strategy_id=ONE_SHOT_STRATEGY_ID,
        strategy_version=ONE_SHOT_STRATEGY_VERSION,
        display_name="单次 Donchian 突破与 ATR 风险退出",
        value_logic=(
            "用 Donchian 通道识别价格脱离近期区间的方向性突破，并用 ATR 统一入场距离、"
            "仓位风险和退出尺度，争取捕捉短周期动量，同时限制单次交易损失。"
        ),
        applicable_scenarios=(
            "适用于 Binance USDⓈ-M 的 BTCUSDT 永续合约出现明确 15 分钟通道突破、"
            "希望以单次多头或空头交易参与短周期趋势的场景；震荡行情可能产生假突破。"
        ),
        execution_behavior=(
            "激活后检查已闭合 15 分钟 K 线和配置数量的 1 分钟确认收盘；满足突破且未过度"
            "延伸时发起一次市价入场，成交后设置 ATR 止损和两档止盈，并记录最长持仓期限；"
            "每个激活最多入场一次。仅 Demo 流程检查开关会跳过自然突破等待。"
        ),
        implementation_path="halpha.planning.strategies.one_shot:OneShotDonchianAtrLogic",
        implementation_digest=_implementation_digest(),
        parameter_schema_version=PARAMETER_SCHEMA_VERSION,
        parameter_schema=_parameter_schema(),
        native_indicators=(
            "nautilus_trader.indicators.DonchianChannel",
            "nautilus_trader.indicators.AverageTrueRange",
        ),
        allowed_action_profiles=(
            "ENTRY_MARKET",
            "PROTECTIVE_STOP_REDUCE_ONLY",
            "TAKE_PROFIT_1",
            "TAKE_PROFIT_2",
            "CANCEL_ORDER",
            "REDUCE_OR_CLOSE_MARKET",
        ),
        supported_directions=(Direction.LONG, Direction.SHORT),
        economic_scope={
            "venue": "BINANCE_USDM",
            "qualified_live_instrument": "BTCUSDT-PERP",
            "one_entry_cycle": True,
            "funding_model": "NOT_MODELED_IN_BACKTEST",
        },
        plan_key_parameters=(
            PlanKeyParameterDefinition(
                parameter_key="demo_immediate_entry",
                label="入场模式",
                display_format=PlanParameterDisplayFormat.BOOLEAN_LABEL,
                true_label="Demo 流程检查",
                false_label="自然突破信号",
            ),
            PlanKeyParameterDefinition(
                parameter_key="channel_lookback_15m",
                label="15m 通道回看",
                unit="根",
            ),
            PlanKeyParameterDefinition(
                parameter_key="confirmation_bars_1m",
                label="1m 确认根数",
                unit="根",
            ),
            PlanKeyParameterDefinition(
                parameter_key="entry_valid_minutes",
                label="入场等待窗口",
                unit="分钟",
            ),
            PlanKeyParameterDefinition(
                parameter_key="initial_stop_atr_multiple",
                label="初始止损",
                unit="ATR",
            ),
            PlanKeyParameterDefinition(
                parameter_key="max_entry_extension_atr",
                label="最大追价",
                unit="ATR",
            ),
            PlanKeyParameterDefinition(
                parameter_key="take_profit_1_fraction",
                label="止盈一仓位比例",
                display_format=PlanParameterDisplayFormat.PERCENT,
            ),
            PlanKeyParameterDefinition(
                parameter_key="take_profit_1_r",
                label="止盈一目标",
                unit="R",
            ),
            PlanKeyParameterDefinition(
                parameter_key="take_profit_2_r",
                label="止盈二目标",
                unit="R",
            ),
            PlanKeyParameterDefinition(
                parameter_key="max_hold_bars_15m",
                label="最大持仓（15m）",
                unit="根",
            ),
        ),
    )


def list_strategies() -> tuple[CodeStrategyDefinition, ...]:
    return (_definition(),)


def strategy_registry_payload() -> dict[str, Any]:
    strategies = [item.model_dump(mode="json") for item in list_strategies()]
    payload: dict[str, Any] = {
        "schema_version": 2,
        "registry_kind": "STATIC_BUILD_ARTIFACT",
        "strategies": strategies,
    }
    payload["registry_digest"] = content_digest(payload)
    return payload


def render_strategy_registry() -> str:
    return (
        json.dumps(
            strategy_registry_payload(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def describe_strategy(strategy_id: str) -> CodeStrategyDefinition:
    if strategy_id != ONE_SHOT_STRATEGY_ID:
        raise KeyError("STRATEGY_UNAVAILABLE")
    return _definition()


def strategy_parameter_schema(strategy_id: str) -> dict[str, Any]:
    return describe_strategy(strategy_id).parameter_schema


def validate_parameters(strategy_id: str, parameters: dict[str, Any]) -> dict[str, Any]:
    describe_strategy(strategy_id)
    normalized = OneShotParameters.model_validate(parameters)
    return normalized.model_dump(mode="json")


def build_fixed_plan_basis(
    strategy_id: str,
    parameters: dict[str, Any],
    *,
    product_build_id: str,
) -> FixedStrategyPlanBasis:
    definition = describe_strategy(strategy_id)
    normalized = validate_parameters(strategy_id, parameters)
    return FixedStrategyPlanBasis(
        strategy_id=definition.strategy_id,
        strategy_version=definition.strategy_version,
        implementation_digest=definition.implementation_digest,
        parameter_schema_version=definition.parameter_schema_version,
        normalized_parameters=normalized,
        parameter_digest=content_digest(normalized),
        fact_input_contract={
            "source_1m": "1-MINUTE-LAST-EXTERNAL",
            "target_15m": "15-MINUTE-LAST-EXTERNAL",
            "closed_and_continuous": True,
            "risk_increase_freshness_seconds": 65,
        },
        allowed_action_profiles=definition.allowed_action_profiles,
        economic_scope=definition.economic_scope,
        product_build_id=product_build_id,
    )
