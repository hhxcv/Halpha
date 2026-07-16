from __future__ import annotations

from nautilus_trader.live.config import ControllerConfig
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.trading.controller import Controller
from nautilus_trader.trading.strategy import Strategy


class QualificationController(Controller):
    """Minimal public Controller used only by the B00 lifecycle fixture."""

    def __init__(self, trader, config: ControllerConfig | None = None) -> None:
        super().__init__(trader=trader, config=config)


class QualificationStrategy(Strategy):
    """No-I/O strategy used to exercise public Controller lifecycle calls."""

    def __init__(self, config: StrategyConfig | None = None) -> None:
        super().__init__(config=config)
