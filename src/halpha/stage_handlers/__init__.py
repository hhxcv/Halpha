from __future__ import annotations

from collections.abc import Callable

from halpha.runtime.pipeline_contracts import StageHandler
from halpha.stage_handlers.decision import stage_handlers as decision_stage_handlers
from halpha.stage_handlers.delivery import stage_handlers as delivery_stage_handlers
from halpha.stage_handlers.derivatives import stage_handlers as derivatives_stage_handlers
from halpha.stage_handlers.macro import stage_handlers as macro_stage_handlers
from halpha.stage_handlers.market import stage_handlers as market_stage_handlers
from halpha.stage_handlers.onchain import stage_handlers as onchain_stage_handlers
from halpha.stage_handlers.strategy import stage_handlers as strategy_stage_handlers
from halpha.stage_handlers.text import stage_handlers as text_stage_handlers


DomainStageHandlerFactory = Callable[[], dict[str, StageHandler]]
DOMAIN_STAGE_HANDLER_FACTORIES: tuple[DomainStageHandlerFactory, ...] = (
    market_stage_handlers,
    derivatives_stage_handlers,
    macro_stage_handlers,
    onchain_stage_handlers,
    text_stage_handlers,
    strategy_stage_handlers,
    decision_stage_handlers,
    delivery_stage_handlers,
)


def domain_stage_handlers() -> tuple[dict[str, StageHandler], ...]:
    return tuple(factory() for factory in DOMAIN_STAGE_HANDLER_FACTORIES)


__all__ = ["DOMAIN_STAGE_HANDLER_FACTORIES", "domain_stage_handlers"]
