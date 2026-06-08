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


SUPPORTED_STRATEGY_NAMES = {"tsmom_vol_scaled"}


def get_strategy_definition(name: str) -> StrategyDefinition | None:
    if name == "tsmom_vol_scaled":
        from .strategies import tsmom_vol_scaled

        return StrategyDefinition(
            name=tsmom_vol_scaled.NAME,
            run=tsmom_vol_scaled.run,
            failed_params=tsmom_vol_scaled.failed_params,
        )
    return None
