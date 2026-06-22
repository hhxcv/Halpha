from __future__ import annotations

from halpha.runtime.pipeline_contracts import StageHandler
from halpha.stage_handlers._lazy import lazy_stage_handler


def stage_handlers() -> dict[str, StageHandler]:
    return {
        "collect_macro_calendar_data": lazy_stage_handler(
            "halpha.collectors.macro_calendar",
            "collect_macro_calendar_data",
        ),
        "sync_macro_calendar_history": lazy_stage_handler(
            "halpha.macro.macro_calendar_history",
            "sync_macro_calendar_history",
        ),
        "build_macro_calendar_views": lazy_stage_handler(
            "halpha.macro.macro_calendar_views",
            "build_macro_calendar_views",
        ),
        "build_macro_calendar_context": lazy_stage_handler(
            "halpha.macro.macro_calendar_context",
            "build_macro_calendar_context",
        ),
        "build_macro_calendar_material": lazy_stage_handler(
            "halpha.analysis.macro_calendar_material",
            "build_macro_calendar_material",
        ),
    }
