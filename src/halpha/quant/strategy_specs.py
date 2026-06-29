from __future__ import annotations

from dataclasses import dataclass
from typing import Any


OHLCV_REQUIRED_FIELDS = ("open_time", "open", "high", "low", "close", "volume")
LONG_FLAT_POLICY = "research_long_flat_target_exposure"
SIGNED_POLICY = "research_signed_target_exposure"
MULTI_LEG_POLICY = "research_multi_leg_target_exposure"
SUPPORTED_MARKET_TYPES = ("spot", "swap")
FUTURES_MARKET_TYPES = ("swap",)
OHLCV_INPUT = {
    "input_type": "ohlcv",
    "required": True,
    "time_alignment": "closed_bar_no_lookahead",
    "fields": list(OHLCV_REQUIRED_FIELDS),
}
PAIR_OHLCV_INPUT_A = {
    **OHLCV_INPUT,
    "leg_id": "spread_leg_a",
    "leg_role": "spread_primary",
}
PAIR_OHLCV_INPUT_B = {
    **OHLCV_INPUT,
    "leg_id": "spread_leg_b",
    "leg_role": "spread_hedge",
}
CROSS_SECTIONAL_OHLCV_INPUT = {
    **OHLCV_INPUT,
    "instrument_role": "ranked_universe_member",
    "minimum_instrument_count": 3,
}
RESEARCH_RISK_NOTE = "Historical strategy output is research material, not a forecast."
REALIZED_VOLATILITY_FILTER = {
    "filter_id": "realized_volatility_max_pct_v1",
    "input_type": "ohlcv_close_return",
    "required": False,
    "time_alignment": "closed_bar_no_lookahead",
    "parameters": {
        "volatility_filter_enabled": {"type": "boolean", "default": False},
        "volatility_filter_window": {"type": "positive_integer", "default": 20},
        "max_realized_volatility_pct": {"type": "positive_number", "default": 100.0},
    },
}
DERIVATIVES_FUNDING_RATE_FEATURE = {
    "feature_id": "derivatives_feature:funding_rate:funding_rate_v1",
    "input_type": "derivatives_market",
    "data_class": "funding_rate",
    "metric": "funding_rate",
    "required": False,
    "time_alignment": "as_of_and_first_seen_no_lookahead",
    "parameters": {
        "funding_rate_filter_enabled": {"type": "boolean", "default": False},
        "max_abs_funding_rate": {"type": "positive_number", "default": 0.001},
    },
}


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
    supported_filters: tuple[dict[str, Any], ...] = ()
    supported_features: tuple[dict[str, Any], ...] = ()

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
            "supported_filters": [_copy_mapping(item) for item in self.supported_filters],
            "supported_features": [_copy_mapping(item) for item in self.supported_features],
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
    "signed_tsmom_trend",
    "breakout_atr_trend",
    "sma_cross_trend",
    "sma_cross_long_short",
    "pair_zscore_reversion",
    "cross_sectional_momentum",
    "bollinger_rsi_reversion",
    "bollinger_rsi_long_short",
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
    "signed_tsmom_trend": StrategySpec(
        name="signed_tsmom_trend",
        family="trend",
        version="1",
        description="Signed time-series momentum strategy with long, short, and flat exposure states.",
        supported_market_types=SUPPORTED_MARKET_TYPES,
        required_inputs=(OHLCV_INPUT,),
        output_position_policy=SIGNED_POLICY,
        default_params={
            "return_window": 20,
            "deadband_pct": 0.0,
        },
        parameter_schema={
            "return_window": _positive_integer_param(
                20,
                "Lookback bars used to measure signed momentum return.",
            ),
            "deadband_pct": _bounded_number_param(
                0.0,
                "Absolute momentum threshold below which target exposure stays flat.",
                minimum=0.0,
                maximum=100.0,
            ),
        },
        optimization_space={
            "return_window": _grid([10, 20, 40]),
            "deadband_pct": _grid([0.0, 1.0, 2.5]),
        },
        minimum_rows_policy={
            "formula": "return_window + 1",
            "minimum_rows_with_default_params": 21,
            "reason": "Requires signed momentum warmup plus one prior bar.",
        },
        risk_notes=(
            RESEARCH_RISK_NOTE,
            "Signed momentum strategies can lose on both long and short reversals.",
            "Short exposure is research exposure only, not borrowing or account state.",
        ),
        supported_filters=(REALIZED_VOLATILITY_FILTER,),
        supported_features=(DERIVATIVES_FUNDING_RATE_FEATURE,),
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
    "sma_cross_long_short": StrategySpec(
        name="sma_cross_long_short",
        family="moving_average",
        version="1",
        description="Signed simple moving-average crossover strategy with long, short, and flat exposure states.",
        supported_market_types=SUPPORTED_MARKET_TYPES,
        required_inputs=(OHLCV_INPUT,),
        output_position_policy=SIGNED_POLICY,
        default_params={
            "short_window": 20,
            "long_window": 50,
            "neutral_band_pct": 0.0,
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
            "neutral_band_pct": _bounded_number_param(
                0.0,
                "Absolute SMA spread threshold below which target exposure stays flat.",
                minimum=0.0,
                maximum=100.0,
            ),
        },
        optimization_space={
            "short_window": _grid([10, 20, 30]),
            "long_window": _grid([30, 50, 80]),
            "neutral_band_pct": _grid([0.0, 0.5, 1.0]),
        },
        minimum_rows_policy={
            "formula": "long_window + 1",
            "minimum_rows_with_default_params": 51,
            "reason": "Requires long moving-average warmup plus one prior bar.",
        },
        risk_notes=(
            RESEARCH_RISK_NOTE,
            "Moving-average crossovers can lag during fast regime changes.",
            "Short exposure is research exposure only, not borrowing or account state.",
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
    "pair_zscore_reversion": StrategySpec(
        name="pair_zscore_reversion",
        family="statistical_arbitrage",
        version="1",
        description="Pair spread z-score reversion strategy with explicit two-leg research exposure.",
        supported_market_types=SUPPORTED_MARKET_TYPES,
        required_inputs=(PAIR_OHLCV_INPUT_A, PAIR_OHLCV_INPUT_B),
        output_position_policy=MULTI_LEG_POLICY,
        default_params={
            "lookback_window": 20,
            "entry_zscore": 2.0,
            "exit_zscore": 0.5,
            "hedge_ratio": 1.0,
        },
        parameter_schema={
            "lookback_window": _positive_integer_param(
                20,
                "Rolling aligned-pair bars used to estimate spread mean and dispersion.",
            ),
            "entry_zscore": _positive_number_param(
                2.0,
                "Absolute spread z-score threshold used to enter long-spread or short-spread exposure.",
                constraints=["entry_zscore must be greater than exit_zscore"],
            ),
            "exit_zscore": _bounded_number_param(
                0.5,
                "Absolute spread z-score threshold below which active pair exposure exits to flat.",
                minimum=0.0,
                maximum=100.0,
                constraints=["exit_zscore must be lower than entry_zscore"],
            ),
            "hedge_ratio": _positive_number_param(
                1.0,
                "Fixed configured hedge ratio applied to the second leg in the log-price spread.",
            ),
        },
        optimization_space={
            "lookback_window": _grid([20, 40, 60]),
            "entry_zscore": _grid([1.5, 2.0, 2.5]),
            "exit_zscore": _grid([0.25, 0.5, 0.75]),
            "hedge_ratio": _grid([0.5, 1.0, 1.5]),
        },
        minimum_rows_policy={
            "formula": "lookback_window + 1 aligned pair rows",
            "minimum_rows_with_default_params": 21,
            "reason": "Requires rolling spread z-score warmup plus one next-bar evaluation row.",
        },
        risk_notes=(
            RESEARCH_RISK_NOTE,
            "Pair strategy output is research exposure only, not market-neutral account construction.",
            "No pair discovery, cointegration testing, or hedge-ratio optimization is performed.",
        ),
    ),
    "cross_sectional_momentum": StrategySpec(
        name="cross_sectional_momentum",
        family="cross_sectional",
        version="1",
        description="Futures-aware cross-sectional momentum strategy with ranked long-short research exposure.",
        supported_market_types=FUTURES_MARKET_TYPES,
        required_inputs=(CROSS_SECTIONAL_OHLCV_INPUT,),
        output_position_policy=MULTI_LEG_POLICY,
        default_params={
            "lookback_window": 20,
            "long_count": 1,
            "short_count": 1,
            "min_instrument_count": 3,
        },
        parameter_schema={
            "lookback_window": _positive_integer_param(
                20,
                "Lookback bars used to rank instruments by close-to-close momentum return.",
            ),
            "long_count": _positive_integer_param(
                1,
                "Number of top-ranked instruments assigned positive research exposure.",
            ),
            "short_count": _positive_integer_param(
                1,
                "Number of bottom-ranked instruments assigned negative research exposure.",
            ),
            "min_instrument_count": _positive_integer_param(
                3,
                "Minimum aligned instrument count required before ranking evidence is sufficient.",
                constraints=["min_instrument_count must be at least long_count + short_count"],
            ),
        },
        optimization_space={
            "lookback_window": _grid([10, 20, 40]),
            "long_count": _grid([1]),
            "short_count": _grid([1]),
            "min_instrument_count": _grid([3, 5]),
        },
        minimum_rows_policy={
            "formula": "lookback_window + 1 aligned universe rows",
            "minimum_rows_with_default_params": 21,
            "reason": "Requires momentum ranking warmup plus one next-bar evaluation row.",
        },
        risk_notes=(
            RESEARCH_RISK_NOTE,
            "Cross-sectional output is research exposure only, not portfolio allocation or account leverage.",
            "Universe discovery, portfolio optimization, and execution modeling are not performed.",
        ),
    ),
    "bollinger_rsi_long_short": StrategySpec(
        name="bollinger_rsi_long_short",
        family="mean_reversion",
        version="1",
        description="Signed Bollinger and RSI reversion strategy with long, short, flat, and trend-suppressed states.",
        supported_market_types=SUPPORTED_MARKET_TYPES,
        required_inputs=(OHLCV_INPUT,),
        output_position_policy=SIGNED_POLICY,
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
                "RSI threshold for oversold long reversion context.",
                minimum=0.0,
                maximum=100.0,
                constraints=["rsi_oversold must be lower than rsi_overbought"],
            ),
            "rsi_overbought": _bounded_number_param(
                70.0,
                "RSI threshold for overbought short reversion context.",
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
                "Trend move threshold that suppresses same-direction reversion entries.",
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
            "Short exposure is research exposure only, not borrowing or account state.",
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

