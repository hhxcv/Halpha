from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


StrategyRun = Callable[..., dict[str, Any]]
StrategyParams = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class StrategyDefinition:
    name: str
    run: StrategyRun
    failed_params: StrategyParams


SUPPORTED_STRATEGY_NAMES = {"bollinger_rsi_reversion", "breakout_atr_trend", "tsmom_vol_scaled"}


def get_strategy_definition(name: str) -> StrategyDefinition | None:
    if name == "tsmom_vol_scaled":
        from .strategies import tsmom_vol_scaled

        return StrategyDefinition(
            name=tsmom_vol_scaled.NAME,
            run=tsmom_vol_scaled.run,
            failed_params=tsmom_vol_scaled.failed_params,
        )
    if name == "breakout_atr_trend":
        from .strategies import breakout_atr_trend

        return StrategyDefinition(
            name=breakout_atr_trend.NAME,
            run=breakout_atr_trend.run,
            failed_params=breakout_atr_trend.failed_params,
        )
    if name == "bollinger_rsi_reversion":
        from .strategies import bollinger_rsi_reversion

        return StrategyDefinition(
            name=bollinger_rsi_reversion.NAME,
            run=bollinger_rsi_reversion.run,
            failed_params=bollinger_rsi_reversion.failed_params,
        )
    return None
