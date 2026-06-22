from __future__ import annotations

from halpha.runtime.pipeline_contracts import StageHandler
from halpha.stage_handlers._lazy import lazy_stage_handler


def stage_handlers() -> dict[str, StageHandler]:
    return {
        "collect_onchain_flow_data": lazy_stage_handler(
            "halpha.collectors.onchain_flow",
            "collect_onchain_flow_data",
        ),
        "sync_onchain_flow_history": lazy_stage_handler(
            "halpha.onchain.onchain_flow_history",
            "sync_onchain_flow_history",
        ),
        "build_onchain_flow_views": lazy_stage_handler(
            "halpha.onchain.onchain_flow_views",
            "build_onchain_flow_views",
        ),
        "build_onchain_flow_context": lazy_stage_handler(
            "halpha.onchain.onchain_flow_context",
            "build_onchain_flow_context",
        ),
        "build_onchain_flow_material": lazy_stage_handler(
            "halpha.analysis.onchain_flow_material",
            "build_onchain_flow_material",
        ),
    }
