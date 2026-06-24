from __future__ import annotations

from typing import Any

from halpha.runtime.pipeline_contracts import PipelineError, RunContext, StageHandler
from halpha.stage_handlers._lazy import lazy_stage_handler


def stage_handlers() -> dict[str, StageHandler]:
    return {
        "build_data_quality_summary": lazy_stage_handler("halpha.data.data_quality", "build_data_quality_summary"),
        "build_outcome_targets": lazy_stage_handler("halpha.outcome.outcome_targets", "build_outcome_targets"),
        "evaluate_outcomes": lazy_stage_handler("halpha.outcome.outcome_evaluations", "evaluate_outcomes"),
        "build_analysis_materials": build_analysis_materials,
        "build_research_context": lazy_stage_handler("halpha.analysis.research_context", "build_research_context"),
        "build_codex_context": lazy_stage_handler("halpha.codex.context_builder", "build_codex_context"),
        "run_codex_report": lazy_stage_handler("halpha.codex.runner", "run_codex_report"),
        "write_outcome_history": lazy_stage_handler("halpha.outcome.outcome_history", "write_outcome_history"),
        "write_research_data_catalog": lazy_stage_handler(
            "halpha.data.research_data_catalog",
            "write_research_data_catalog",
        ),
        "validate_product_contracts": lazy_stage_handler(
            "halpha.product.product_validation",
            "build_product_contract_validation",
        ),
    }


def build_analysis_materials(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.analysis.data_quality_material import build_data_quality_material
    from halpha.analysis.derivatives_market_material import build_derivatives_market_material
    from halpha.analysis.factor_signal_material import build_factor_signal_material
    from halpha.analysis.intelligence_fusion_material import build_intelligence_fusion_material
    from halpha.analysis.market_material import build_market_material
    from halpha.analysis.outcome_tracking_material import build_outcome_tracking_material
    from halpha.analysis.text_material import build_text_material

    artifacts = []
    try:
        artifacts.extend(build_factor_signal_material(config, run))
        artifacts.extend(build_intelligence_fusion_material(config, run))
        artifacts.extend(build_data_quality_material(config, run))
        artifacts.extend(build_derivatives_market_material(config, run))
        artifacts.extend(build_outcome_tracking_material(config, run))
        artifacts.extend(build_market_material(config, run))
        artifacts.extend(build_text_material(config, run))
    except PipelineError as exc:
        if artifacts and not exc.artifacts:
            exc.artifacts = artifacts
        raise
    return artifacts
