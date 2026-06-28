from __future__ import annotations

from dataclasses import dataclass
from typing import Any


OHLCV_REQUIRED_FIELDS = ("open_time", "open", "high", "low", "close", "volume")
LONG_FLAT_POLICY = "research_long_flat_target_exposure"
SUPPORTED_MARKET_TYPES = ("spot", "swap")
OHLCV_INPUT = {
    "input_type": "ohlcv",
    "required": True,
    "time_alignment": "closed_bar_no_lookahead",
    "fields": list(OHLCV_REQUIRED_FIELDS),
}
RESEARCH_RISK_NOTE = "Historical strategy output is research material, not a forecast."


@dataclass(frozen=True)
class StrategySpec:
    name: str
    family: str
    version: str
    description: str
    supported_market_types: tuple[str, ...]
    required_inputs: tuple[dict[str, Any], ...]
    output_position_policy: str
    default_params: dict[str, Any]
    parameter_schema: dict[str, dict[str, Any]]
    optimization_space: dict[str, dict[str, Any]]
    minimum_rows_policy: dict[str, Any]
    risk_notes: tuple[str, ...]

    def to_record(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "name": self.name,
            "family": self.family,
            "version": self.version,
            "description": self.description,
            "supported_market_types": list(self.supported_market_types),
            "required_inputs": [_copy_mapping(item) for item in self.required_inputs],
            "output_position_policy": self.output_position_policy,
            "default_params": dict(self.default_params),
            "parameter_schema": {
                name: dict(schema)
                for name, schema in self.parameter_schema.items()
            },
            "optimization_space": {
                name: dict(space)
                for name, space in self.optimization_space.items()
            },
            "minimum_rows_policy": dict(self.minimum_rows_policy),
            "risk_notes": list(self.risk_notes),
        }


def _positive_integer_param(
    default: int,
    description: str,
    *,
    constraints: list[str] | None = None,
) -> dict[str, Any]:
    return _param(
        "positive_integer",
        default,
        description,
        minimum=1,
        constraints=constraints,
    )


def _positive_number_param(
    default: float,
    description: str,
    *,
    constraints: list[str] | None = None,
) -> dict[str, Any]:
    return _param(
        "positive_number",
        default,
        description,
        exclusive_minimum=0,
        constraints=constraints,
    )


def _bounded_number_param(
    default: float,
    description: str,
    *,
    minimum: float,
    maximum: float,
    constraints: list[str] | None = None,
) -> dict[str, Any]:
    return _param(
        "number",
        default,
        description,
        minimum=minimum,
        maximum=maximum,
        constraints=constraints,
    )


def _param(
    value_type: str,
    default: int | float,
    description: str,
    **extra: Any,
) -> dict[str, Any]:
    record = {
        "type": value_type,
        "default": default,
        "description": description,
        "optimization_enabled": True,
    }
    for key, value in extra.items():
        if value is not None:
            record[key] = value
    return record


def _grid(values: list[int | float]) -> dict[str, Any]:
    return {
        "type": "grid",
        "values": list(values),
    }


def _copy_mapping(value: dict[str, Any]) -> dict[str, Any]:
    copied = {}
    for key, item in value.items():
        if isinstance(item, (list, tuple)):
            copied[key] = list(item)
        else:
            copied[key] = item
    return copied


STRATEGY_SPEC_ORDER = (
    "tsmom_vol_scaled",
    "breakout_atr_trend",
    "sma_cross_trend",
    "bollinger_rsi_reversion",
)


STRATEGY_SPECS = {
    "tsmom_vol_scaled": StrategySpec(
        name="tsmom_vol_scaled",
        family="trend",
        version="1",
        description="Time-series momentum strategy with volatility-scaled long-flat exposure.",
        supported_market_types=SUPPORTED_MARKET_TYPES,
        required_inputs=(OHLCV_INPUT,),
        output_position_policy=LONG_FLAT_POLICY,
        default_params={
            "return_window": 20,
            "volatility_window": 20,
            "target_volatility": 0.2,
        },
        parameter_schema={
            "return_window": _positive_integer_param(
                20,
                "Lookback bars used to measure momentum return.",
            ),
            "volatility_window": _positive_integer_param(
                20,
                "Lookback bars used to estimate realized volatility.",
            ),
            "target_volatility": _positive_number_param(
                0.2,
                "Target annualized volatility used for exposure scaling.",
            ),
        },
        optimization_space={
            "return_window": _grid([10, 20, 40]),
            "volatility_window": _grid([10, 20, 40]),
            "target_volatility": _grid([0.1, 0.2, 0.3]),
        },
        minimum_rows_policy={
            "formula": "max(return_window, volatility_window) + 1",
            "minimum_rows_with_default_params": 21,
            "reason": "Requires momentum and realized-volatility warmup plus one prior bar.",
        },
        risk_notes=(
            RESEARCH_RISK_NOTE,
            "Momentum strategies can fail during fast reversals and sideways markets.",
        ),
    ),
    "breakout_atr_trend": StrategySpec(
        name="breakout_atr_trend",
        family="trend",
        version="1",
        description="Breakout trend strategy using rolling highs, exits, and ATR context.",
        supported_market_types=SUPPORTED_MARKET_TYPES,
        required_inputs=(OHLCV_INPUT,),
        output_position_policy=LONG_FLAT_POLICY,
        default_params={
            "breakout_window": 20,
            "exit_window": 10,
            "atr_window": 14,
        },
        parameter_schema={
            "breakout_window": _positive_integer_param(
                20,
                "Rolling high/low window used to identify breakouts.",
            ),
            "exit_window": _positive_integer_param(
                10,
                "Rolling low window used to exit active breakout exposure.",
            ),
            "atr_window": _positive_integer_param(
                14,
                "ATR lookback bars used for range and distance context.",
            ),
        },
        optimization_space={
            "breakout_window": _grid([10, 20, 40]),
            "exit_window": _grid([5, 10, 20]),
            "atr_window": _grid([7, 14, 21]),
        },
        minimum_rows_policy={
            "formula": "max(breakout_window, exit_window, atr_window) + 1",
            "minimum_rows_with_default_params": 21,
            "reason": "Requires breakout, exit, and ATR warmup plus one prior bar.",
        },
        risk_notes=(
            RESEARCH_RISK_NOTE,
            "Breakout strategies can be sensitive to false breakouts and high volatility.",
        ),
    ),
    "sma_cross_trend": StrategySpec(
        name="sma_cross_trend",
        family="moving_average",
        version="1",
        description="Simple moving-average crossover trend strategy.",
        supported_market_types=SUPPORTED_MARKET_TYPES,
        required_inputs=(OHLCV_INPUT,),
        output_position_policy=LONG_FLAT_POLICY,
        default_params={
            "short_window": 20,
            "long_window": 50,
        },
        parameter_schema={
            "short_window": _positive_integer_param(
                20,
                "Short moving-average lookback bars.",
                constraints=["short_window must be lower than long_window"],
            ),
            "long_window": _positive_integer_param(
                50,
                "Long moving-average lookback bars.",
                constraints=["long_window must be greater than short_window"],
            ),
        },
        optimization_space={
            "short_window": _grid([10, 20, 30]),
            "long_window": _grid([30, 50, 80]),
        },
        minimum_rows_policy={
            "formula": "long_window + 1",
            "minimum_rows_with_default_params": 51,
            "reason": "Requires long moving-average warmup plus one prior bar.",
        },
        risk_notes=(
            RESEARCH_RISK_NOTE,
            "Moving-average crossovers can lag during fast regime changes.",
        ),
    ),
    "bollinger_rsi_reversion": StrategySpec(
        name="bollinger_rsi_reversion",
        family="mean_reversion",
        version="1",
        description="Bollinger and RSI reversion strategy with trend-filter context.",
        supported_market_types=SUPPORTED_MARKET_TYPES,
        required_inputs=(OHLCV_INPUT,),
        output_position_policy=LONG_FLAT_POLICY,
        default_params={
            "bollinger_window": 20,
            "band_std": 2.0,
            "rsi_window": 14,
            "rsi_oversold": 30.0,
            "rsi_overbought": 70.0,
            "trend_window": 50,
            "trend_filter_pct": 8.0,
        },
        parameter_schema={
            "bollinger_window": _positive_integer_param(
                20,
                "Bollinger middle-band lookback bars.",
            ),
            "band_std": _positive_number_param(
                2.0,
                "Standard-deviation multiplier for Bollinger bands.",
            ),
            "rsi_window": _positive_integer_param(
                14,
                "RSI lookback bars.",
            ),
            "rsi_oversold": _bounded_number_param(
                30.0,
                "RSI threshold for oversold reversion context.",
                minimum=0.0,
                maximum=100.0,
                constraints=["rsi_oversold must be lower than rsi_overbought"],
            ),
            "rsi_overbought": _bounded_number_param(
                70.0,
                "RSI threshold for overbought reversion context.",
                minimum=0.0,
                maximum=100.0,
                constraints=["rsi_overbought must be greater than rsi_oversold"],
            ),
            "trend_window": _positive_integer_param(
                50,
                "Trend-filter lookback bars.",
            ),
            "trend_filter_pct": _positive_number_param(
                8.0,
                "Trend move threshold that can suppress weak reversion evidence.",
            ),
        },
        optimization_space={
            "bollinger_window": _grid([20, 40]),
            "band_std": _grid([2.0, 2.5]),
            "rsi_window": _grid([14]),
            "rsi_oversold": _grid([25.0, 30.0]),
            "rsi_overbought": _grid([70.0, 75.0]),
            "trend_window": _grid([50, 100]),
            "trend_filter_pct": _grid([8.0, 10.0]),
        },
        minimum_rows_policy={
            "formula": "max(bollinger_window, rsi_window + 1, trend_window + 1)",
            "minimum_rows_with_default_params": 51,
            "reason": "Requires Bollinger, RSI, and trend-filter warmup.",
        },
        risk_notes=(
            RESEARCH_RISK_NOTE,
            "Mean-reversion strategies can fail during persistent directional trends.",
        ),
    ),
}


def get_strategy_spec(name: str) -> StrategySpec | None:
    return STRATEGY_SPECS.get(name)


def require_strategy_spec(name: str) -> StrategySpec:
    spec = get_strategy_spec(name)
    if spec is None:
        raise KeyError(f"unsupported strategy spec: {name}")
    return spec


def list_strategy_specs() -> list[StrategySpec]:
    return [STRATEGY_SPECS[name] for name in STRATEGY_SPEC_ORDER]


def strategy_spec_records() -> list[dict[str, Any]]:
    return [spec.to_record() for spec in list_strategy_specs()]

