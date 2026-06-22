from __future__ import annotations

from halpha.runtime.pipeline_contracts import StageHandler
from halpha.stage_handlers._lazy import lazy_stage_handler


def stage_handlers() -> dict[str, StageHandler]:
    return {
        "build_strategy_benchmark_suite": lazy_stage_handler(
            "halpha.strategy.strategy_benchmark_suite",
            "build_strategy_benchmark_suite",
        ),
        "evaluate_quant_strategies": lazy_stage_handler(
            "halpha.strategy.quant_strategies",
            "evaluate_quant_strategies",
        ),
        "evaluate_strategy_evaluation": lazy_stage_handler(
            "halpha.strategy.strategy_evaluation_summary",
            "build_strategy_evaluation_summary",
        ),
        "build_strategy_experiment_material": lazy_stage_handler(
            "halpha.strategy.strategy_experiment",
            "build_strategy_experiment_material",
        ),
        "evaluate_market_strategy_signals": lazy_stage_handler(
            "halpha.strategy.quant_signals",
            "evaluate_market_strategy_signals",
        ),
        "build_strategy_lifecycle_state": lazy_stage_handler(
            "halpha.strategy.strategy_lifecycle",
            "build_strategy_lifecycle_state",
        ),
        "build_strategy_lifecycle_material": lazy_stage_handler(
            "halpha.strategy.strategy_lifecycle_material",
            "build_strategy_lifecycle_material",
        ),
    }
