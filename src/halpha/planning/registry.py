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
ONE_SHOT_STRATEGY_VERSION = "1.0.0"
PARAMETER_SCHEMA_VERSION = "1.0.0"


class Direction(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"


class DecimalString(str):
    """Marker type used only to keep JSON Schema values string-exact."""


class OneShotParameters(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=False,
        validate_default=True,
    )

    direction: Direction
    channel_lookback_15m: int = Field(default=20, ge=20, le=96)
    confirmation_bars_1m: int = Field(default=2, ge=1, le=3)
    initial_stop_atr_multiple: str = "1.5"
    max_entry_extension_atr: str = "0.5"
    take_profit_1_r: str = "1.5"
    take_profit_1_fraction: str = "0.50"
    take_profit_2_r: str = "3.0"
    max_hold_bars_15m: int = Field(default=96, ge=4, le=672)
    entry_valid_minutes: int = Field(default=1440, ge=15, le=10080)

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


class CodeStrategyDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy_id: str
    strategy_version: str
    display_name: str
    implementation_path: str
    implementation_digest: str
    parameter_schema_version: str
    parameter_schema: dict[str, Any]
    native_indicators: tuple[str, ...]
    allowed_action_profiles: tuple[str, ...]
    supported_directions: tuple[Direction, ...]
    economic_scope: dict[str, Any]


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
            "channel_lookback_15m": {"type": "integer", "minimum": 20, "maximum": 96, "default": 20},
            "confirmation_bars_1m": {"type": "integer", "minimum": 1, "maximum": 3, "default": 2},
            "initial_stop_atr_multiple": {"type": "string", "pattern": decimal_pattern, "default": "1.5", "x-halpha-minimum": "1.0", "x-halpha-maximum": "3.0"},
            "max_entry_extension_atr": {"type": "string", "pattern": decimal_pattern, "default": "0.5", "x-halpha-minimum": "0.1", "x-halpha-maximum": "1.0"},
            "take_profit_1_r": {"type": "string", "pattern": decimal_pattern, "default": "1.5", "x-halpha-minimum": "1.0", "x-halpha-maximum": "3.0"},
            "take_profit_1_fraction": {"type": "string", "pattern": decimal_pattern, "default": "0.50", "x-halpha-minimum": "0.25", "x-halpha-maximum": "0.75"},
            "take_profit_2_r": {"type": "string", "pattern": decimal_pattern, "default": "3.0", "x-halpha-minimum": "2.0", "x-halpha-maximum": "6.0"},
            "max_hold_bars_15m": {"type": "integer", "minimum": 4, "maximum": 672, "default": 96},
            "entry_valid_minutes": {"type": "integer", "minimum": 15, "maximum": 10080, "default": 1440},
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
            "REDUCE_OR_CLOSE_MARKET",
        ),
        supported_directions=(Direction.LONG, Direction.SHORT),
        economic_scope={
            "venue": "BINANCE_USDM",
            "qualified_live_instrument": "BTCUSDT-PERP",
            "one_entry_cycle": True,
            "funding_model": "NOT_MODELED_IN_BACKTEST",
        },
    )


def list_strategies() -> tuple[CodeStrategyDefinition, ...]:
    return (_definition(),)


def strategy_registry_payload() -> dict[str, Any]:
    strategies = [item.model_dump(mode="json") for item in list_strategies()]
    payload: dict[str, Any] = {
        "schema_version": 1,
        "registry_kind": "STATIC_BUILD_ARTIFACT",
        "strategies": strategies,
    }
    payload["registry_digest"] = content_digest(payload)
    return payload


def render_strategy_registry() -> str:
    return json.dumps(
        strategy_registry_payload(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


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
            "target_15m": "15-MINUTE-LAST-INTERNAL@1-MINUTE-EXTERNAL",
            "closed_and_continuous": True,
            "risk_increase_freshness_seconds": 65,
        },
        allowed_action_profiles=definition.allowed_action_profiles,
        economic_scope=definition.economic_scope,
        product_build_id=product_build_id,
    )
