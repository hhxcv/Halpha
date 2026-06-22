from __future__ import annotations

from importlib import import_module
from typing import Any

from halpha.runtime.pipeline_contracts import RunContext, StageHandler


def lazy_stage_handler(module_name: str, function_name: str) -> StageHandler:
    def handler(config: dict[str, Any], run: RunContext) -> list[str] | None:
        module = import_module(module_name)
        return getattr(module, function_name)(config, run)

    handler.__name__ = function_name
    handler.__qualname__ = function_name
    return handler
