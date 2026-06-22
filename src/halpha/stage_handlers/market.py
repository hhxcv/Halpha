from __future__ import annotations

from halpha.runtime.pipeline_contracts import StageHandler
from halpha.stage_handlers._lazy import lazy_stage_handler


def stage_handlers() -> dict[str, StageHandler]:
    return {
        "collect_market_data": lazy_stage_handler("halpha.collectors.market", "collect_market_data"),
        "sync_ohlcv": lazy_stage_handler("halpha.market.ohlcv_sync", "sync_ohlcv_history"),
        "build_market_data_views": lazy_stage_handler("halpha.market.market_data_views", "build_market_data_views"),
        "build_market_signals": lazy_stage_handler("halpha.market.market_signals", "build_market_signals"),
        "build_market_signal_material": lazy_stage_handler(
            "halpha.market.market_signals",
            "build_market_signal_material",
        ),
    }
