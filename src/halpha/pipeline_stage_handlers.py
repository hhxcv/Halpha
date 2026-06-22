from __future__ import annotations

from typing import Any

from halpha.pipeline_stages import STAGE_ORDER
from halpha.runtime.pipeline_contracts import RunContext, StageHandler, StageNotImplementedError
from halpha.stage_handlers import domain_stage_handlers


def default_stage_handlers(overrides: dict[str, StageHandler] | None = None) -> dict[str, StageHandler]:
    handlers = {stage: _unimplemented_handler(stage) for stage in STAGE_ORDER}
    for stage_group in domain_stage_handlers():
        handlers.update(stage_group)
    if overrides:
        handlers.update(overrides)
    return handlers


def _unimplemented_handler(stage: str) -> StageHandler:
    def handler(config: dict[str, Any], run: RunContext) -> list[str] | None:
        raise StageNotImplementedError(stage)

    return handler


__all__ = ["default_stage_handlers"]
