from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .strategy_specs import (
    STRATEGY_SPEC_ORDER,
    StrategySpec,
    get_strategy_spec,
    list_strategy_specs,
    strategy_spec_records,
)


StrategyRun = Callable[..., dict[str, Any]]
StrategyParams = Callable[[dict[str, Any]], dict[str, Any]]
StrategySignalRecords = Callable[[dict[str, Any], dict[str, Any], list[dict[str, Any]]], dict[str, Any]]
MultiLegSignalRecords = Callable[[dict[str, Any], list[dict[str, Any]]], dict[str, Any]]
MultiLegBacktest = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class StrategyDefinition:
    name: str
    spec: StrategySpec
    run: StrategyRun
    failed_params: StrategyParams
    signal_records: StrategySignalRecords
    multi_leg_signal_records: MultiLegSignalRecords | None = None
    multi_leg_backtest: MultiLegBacktest | None = None


SUPPORTED_STRATEGY_NAMES = frozenset(STRATEGY_SPEC_ORDER)


def get_supported_strategy_spec(name: str) -> StrategySpec | None:
    return get_strategy_spec(name)


def supported_strategy_specs() -> list[StrategySpec]:
    return list_strategy_specs()


def supported_strategy_spec_records() -> list[dict[str, Any]]:
    return strategy_spec_records()


def get_strategy_definition(name: str) -> StrategyDefinition | None:
    spec = get_strategy_spec(name)
    if spec is None:
        return None
    if name == "tsmom_vol_scaled":
        from .strategies import tsmom_vol_scaled

        return StrategyDefinition(
            name=tsmom_vol_scaled.NAME,
            spec=spec,
            run=tsmom_vol_scaled.run,
            failed_params=tsmom_vol_scaled.failed_params,
            signal_records=tsmom_vol_scaled.signal_records,
        )
    if name == "signed_tsmom_trend":
        from .strategies import signed_tsmom_trend

        return StrategyDefinition(
            name=signed_tsmom_trend.NAME,
            spec=spec,
            run=signed_tsmom_trend.run,
            failed_params=signed_tsmom_trend.failed_params,
            signal_records=signed_tsmom_trend.signal_records,
        )
    if name == "breakout_atr_trend":
        from .strategies import breakout_atr_trend

        return StrategyDefinition(
            name=breakout_atr_trend.NAME,
            spec=spec,
            run=breakout_atr_trend.run,
            failed_params=breakout_atr_trend.failed_params,
            signal_records=breakout_atr_trend.signal_records,
        )
    if name == "bollinger_rsi_reversion":
        from .strategies import bollinger_rsi_reversion

        return StrategyDefinition(
            name=bollinger_rsi_reversion.NAME,
            spec=spec,
            run=bollinger_rsi_reversion.run,
            failed_params=bollinger_rsi_reversion.failed_params,
            signal_records=bollinger_rsi_reversion.signal_records,
        )
    if name == "bollinger_rsi_long_short":
        from .strategies import bollinger_rsi_long_short

        return StrategyDefinition(
            name=bollinger_rsi_long_short.NAME,
            spec=spec,
            run=bollinger_rsi_long_short.run,
            failed_params=bollinger_rsi_long_short.failed_params,
            signal_records=bollinger_rsi_long_short.signal_records,
        )
    if name == "pair_zscore_reversion":
        from .strategies import pair_zscore_reversion

        return StrategyDefinition(
            name=pair_zscore_reversion.NAME,
            spec=spec,
            run=pair_zscore_reversion.run,
            failed_params=pair_zscore_reversion.failed_params,
            signal_records=pair_zscore_reversion.signal_records,
            multi_leg_signal_records=pair_zscore_reversion.pair_signal_records,
            multi_leg_backtest=pair_zscore_reversion.evaluate_pair_backtest,
        )
    if name == "cross_sectional_momentum":
        from .strategies import cross_sectional_momentum

        return StrategyDefinition(
            name=cross_sectional_momentum.NAME,
            spec=spec,
            run=cross_sectional_momentum.run,
            failed_params=cross_sectional_momentum.failed_params,
            signal_records=cross_sectional_momentum.signal_records,
            multi_leg_signal_records=cross_sectional_momentum.universe_signal_records,
            multi_leg_backtest=cross_sectional_momentum.evaluate_universe_backtest,
        )
    if name == "sma_cross_long_short":
        from .strategies import sma_cross_long_short

        return StrategyDefinition(
            name=sma_cross_long_short.NAME,
            spec=spec,
            run=sma_cross_long_short.run,
            failed_params=sma_cross_long_short.failed_params,
            signal_records=sma_cross_long_short.signal_records,
        )
    if name == "sma_cross_trend":
        from .strategies import sma_cross_trend

        return StrategyDefinition(
            name=sma_cross_trend.NAME,
            spec=spec,
            run=sma_cross_trend.run,
            failed_params=sma_cross_trend.failed_params,
            signal_records=sma_cross_trend.signal_records,
        )
    return None
