from __future__ import annotations

from halpha.runtime.pipeline_contracts import StageHandler
from halpha.stage_handlers._lazy import lazy_stage_handler


def stage_handlers() -> dict[str, StageHandler]:
    return {
        "collect_derivatives_market_data": lazy_stage_handler(
            "halpha.collectors.derivatives_market",
            "collect_derivatives_market_data",
        ),
        "sync_derivatives_market_history": lazy_stage_handler(
            "halpha.market.derivatives_history",
            "sync_derivatives_market_history",
        ),
        "build_derivatives_market_views": lazy_stage_handler(
            "halpha.market.derivatives_market_views",
            "build_derivatives_market_views",
        ),
        "build_derivatives_market_context": lazy_stage_handler(
            "halpha.market.derivatives_market_context",
            "build_derivatives_market_context",
        ),
    }
