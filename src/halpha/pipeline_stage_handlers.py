from __future__ import annotations

from typing import Any

from halpha.pipeline_stages import STAGE_ORDER
from halpha.runtime.pipeline_contracts import PipelineError, RunContext, StageHandler, StageNotImplementedError


def default_stage_handlers(overrides: dict[str, StageHandler] | None = None) -> dict[str, StageHandler]:
    handlers = {stage: _unimplemented_handler(stage) for stage in STAGE_ORDER}
    for stage_group in (
        _market_stage_handlers(),
        _derivatives_stage_handlers(),
        _macro_stage_handlers(),
        _onchain_stage_handlers(),
        _text_stage_handlers(),
        _strategy_stage_handlers(),
        _decision_stage_handlers(),
        _delivery_stage_handlers(),
    ):
        handlers.update(stage_group)
    if overrides:
        handlers.update(overrides)
    return handlers


def _market_stage_handlers() -> dict[str, StageHandler]:
    return {
        "collect_market_data": _collect_market_data,
        "sync_ohlcv": _sync_ohlcv,
        "build_market_data_views": _build_market_data_views,
        "build_market_signals": _build_market_signals,
        "build_market_signal_material": _build_market_signal_material,
    }


def _derivatives_stage_handlers() -> dict[str, StageHandler]:
    return {
        "collect_derivatives_market_data": _collect_derivatives_market_data,
        "sync_derivatives_market_history": _sync_derivatives_market_history,
        "build_derivatives_market_views": _build_derivatives_market_views,
        "build_derivatives_market_context": _build_derivatives_market_context,
    }


def _macro_stage_handlers() -> dict[str, StageHandler]:
    return {
        "collect_macro_calendar_data": _collect_macro_calendar_data,
        "sync_macro_calendar_history": _sync_macro_calendar_history,
        "build_macro_calendar_views": _build_macro_calendar_views,
        "build_macro_calendar_context": _build_macro_calendar_context,
        "build_macro_calendar_material": _build_macro_calendar_material,
    }


def _onchain_stage_handlers() -> dict[str, StageHandler]:
    return {
        "collect_onchain_flow_data": _collect_onchain_flow_data,
        "sync_onchain_flow_history": _sync_onchain_flow_history,
        "build_onchain_flow_views": _build_onchain_flow_views,
        "build_onchain_flow_context": _build_onchain_flow_context,
        "build_onchain_flow_material": _build_onchain_flow_material,
    }


def _text_stage_handlers() -> dict[str, StageHandler]:
    return {
        "collect_text_events": _collect_text_events,
        "build_text_event_records": _build_text_event_records,
        "build_text_entity_evidence": _build_text_entity_evidence,
        "build_text_event_classification_evidence": _build_text_event_classification_evidence,
        "build_text_event_topics": _build_text_event_topics,
        "build_text_event_signals": _build_text_event_signals,
    }


def _strategy_stage_handlers() -> dict[str, StageHandler]:
    return {
        "build_strategy_benchmark_suite": _build_strategy_benchmark_suite,
        "evaluate_quant_strategies": _evaluate_quant_strategies,
        "evaluate_strategy_evaluation": _evaluate_strategy_evaluation,
        "build_strategy_experiment_material": _build_strategy_experiment_material,
        "evaluate_market_strategy_signals": _evaluate_market_strategy_signals,
        "build_strategy_lifecycle_state": _build_strategy_lifecycle_state,
        "build_strategy_lifecycle_material": _build_strategy_lifecycle_material,
    }


def _decision_stage_handlers() -> dict[str, StageHandler]:
    return {
        "build_market_regime_assessment": _build_market_regime_assessment,
        "build_risk_assessment": _build_risk_assessment,
        "build_decision_recommendations": _build_decision_recommendations,
        "build_watch_triggers": _build_watch_triggers,
        "build_event_market_confluence": _build_event_market_confluence,
        "build_event_intelligence_assessment": _build_event_intelligence_assessment,
        "build_alert_decisions": _build_alert_decisions,
        "build_alert_decision_material": _build_alert_decision_material,
        "build_event_intelligence_material": _build_event_intelligence_material,
        "build_decision_intelligence_delta": _build_decision_intelligence_delta,
        "build_decision_intelligence_material": _build_decision_intelligence_material,
        "build_feature_snapshots": _build_feature_snapshots,
        "build_factor_states": _build_factor_states,
        "build_multi_source_signals": _build_multi_source_signals,
        "build_intelligence_fusion": _build_intelligence_fusion,
        "integrate_intelligence_fusion": _integrate_intelligence_fusion,
        "build_user_state_context": _build_user_state_context,
        "build_personalized_risk_constraints": _build_personalized_risk_constraints,
        "integrate_personalized_risk_constraints": _integrate_personalized_risk_constraints,
        "build_personalized_risk_material": _build_personalized_risk_material,
    }


def _delivery_stage_handlers() -> dict[str, StageHandler]:
    return {
        "build_data_quality_summary": _build_data_quality_summary,
        "build_outcome_targets": _build_outcome_targets,
        "evaluate_outcomes": _evaluate_outcomes,
        "build_analysis_materials": _build_analysis_materials,
        "build_research_context": _build_research_context,
        "build_codex_context": _build_codex_context,
        "run_codex_report": _run_codex_report,
        "validate_product_contracts": _validate_product_contracts,
    }


def _unimplemented_handler(stage: str) -> StageHandler:
    def handler(config: dict[str, Any], run: RunContext) -> list[str] | None:
        raise StageNotImplementedError(stage)

    return handler


def _collect_market_data(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.collectors.market import collect_market_data

    return collect_market_data(config, run)


def _collect_derivatives_market_data(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.collectors.derivatives_market import collect_derivatives_market_data

    return collect_derivatives_market_data(config, run)


def _sync_derivatives_market_history(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.market.derivatives_history import sync_derivatives_market_history

    return sync_derivatives_market_history(config, run)


def _build_derivatives_market_views(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.market.derivatives_market_views import build_derivatives_market_views

    return build_derivatives_market_views(config, run)


def _build_derivatives_market_context(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.market.derivatives_market_context import build_derivatives_market_context

    return build_derivatives_market_context(config, run)


def _collect_macro_calendar_data(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.collectors.macro_calendar import collect_macro_calendar_data

    return collect_macro_calendar_data(config, run)


def _sync_macro_calendar_history(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.macro.macro_calendar_history import sync_macro_calendar_history

    return sync_macro_calendar_history(config, run)


def _build_macro_calendar_views(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.macro.macro_calendar_views import build_macro_calendar_views

    return build_macro_calendar_views(config, run)


def _build_macro_calendar_context(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.macro.macro_calendar_context import build_macro_calendar_context

    return build_macro_calendar_context(config, run)


def _build_macro_calendar_material(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.analysis.macro_calendar_material import build_macro_calendar_material

    return build_macro_calendar_material(config, run)


def _collect_onchain_flow_data(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.collectors.onchain_flow import collect_onchain_flow_data

    return collect_onchain_flow_data(config, run)


def _sync_onchain_flow_history(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.onchain.onchain_flow_history import sync_onchain_flow_history

    return sync_onchain_flow_history(config, run)


def _build_onchain_flow_views(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.onchain.onchain_flow_views import build_onchain_flow_views

    return build_onchain_flow_views(config, run)


def _build_onchain_flow_context(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.onchain.onchain_flow_context import build_onchain_flow_context

    return build_onchain_flow_context(config, run)


def _build_onchain_flow_material(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.analysis.onchain_flow_material import build_onchain_flow_material

    return build_onchain_flow_material(config, run)


def _collect_text_events(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.collectors.text import collect_text_events

    return collect_text_events(config, run)


def _build_text_event_records(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.text.text_event_records import build_text_event_records

    return build_text_event_records(config, run)


def _build_text_entity_evidence(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.text.text_entity_evidence import build_text_entity_evidence

    return build_text_entity_evidence(config, run)


def _build_text_event_classification_evidence(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.text.text_event_classification import build_text_event_classification_evidence

    return build_text_event_classification_evidence(config, run)


def _build_text_event_topics(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.text.text_event_topics import build_text_event_topics

    return build_text_event_topics(config, run)


def _build_text_event_signals(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.text.text_event_signals import build_text_event_signals

    return build_text_event_signals(config, run)


def _sync_ohlcv(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.market.ohlcv_sync import sync_ohlcv_history

    return sync_ohlcv_history(config, run)


def _build_market_data_views(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.market.market_data_views import build_market_data_views

    return build_market_data_views(config, run)


def _build_strategy_benchmark_suite(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.strategy.strategy_benchmark_suite import build_strategy_benchmark_suite

    return build_strategy_benchmark_suite(config, run)


def _evaluate_quant_strategies(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.strategy.quant_strategies import evaluate_quant_strategies

    return evaluate_quant_strategies(config, run)


def _evaluate_strategy_evaluation(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.strategy.strategy_evaluation_summary import build_strategy_evaluation_summary

    return build_strategy_evaluation_summary(config, run)


def _build_strategy_experiment_material(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.strategy.strategy_experiment import build_strategy_experiment_material

    return build_strategy_experiment_material(config, run)


def _evaluate_market_strategy_signals(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.strategy.quant_signals import evaluate_market_strategy_signals

    return evaluate_market_strategy_signals(config, run)


def _build_market_signals(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.market.market_signals import build_market_signals

    return build_market_signals(config, run)


def _build_market_signal_material(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.market.market_signals import build_market_signal_material

    return build_market_signal_material(config, run)


def _build_market_regime_assessment(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.decision.decision_intelligence import build_market_regime_assessment

    return build_market_regime_assessment(config, run)


def _build_risk_assessment(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.decision.decision_intelligence import build_risk_assessment

    return build_risk_assessment(config, run)


def _build_decision_recommendations(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.decision.decision_intelligence import build_decision_recommendations

    return build_decision_recommendations(config, run)


def _build_watch_triggers(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.decision.decision_intelligence import build_watch_triggers

    return build_watch_triggers(config, run)


def _build_event_market_confluence(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.decision.event_market_confluence import build_event_market_confluence

    return build_event_market_confluence(config, run)


def _build_event_intelligence_assessment(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.decision.event_intelligence_assessment import build_event_intelligence_assessment

    return build_event_intelligence_assessment(config, run)


def _build_alert_decisions(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.decision.alert_decisions import build_alert_decisions

    return build_alert_decisions(config, run)


def _build_alert_decision_material(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.analysis.alert_decision_material import build_alert_decision_material

    return build_alert_decision_material(config, run)


def _build_event_intelligence_material(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.analysis.event_intelligence_material import build_event_intelligence_material

    return build_event_intelligence_material(config, run)


def _build_decision_intelligence_delta(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.decision.decision_intelligence import build_decision_intelligence_delta

    return build_decision_intelligence_delta(config, run)


def _build_decision_intelligence_material(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.decision.decision_intelligence import build_decision_intelligence_material

    return build_decision_intelligence_material(config, run)


def _build_data_quality_summary(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.data.data_quality import build_data_quality_summary

    return build_data_quality_summary(config, run)


def _build_outcome_targets(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.outcome.outcome_targets import build_outcome_targets

    return build_outcome_targets(config, run)


def _evaluate_outcomes(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.outcome.outcome_evaluations import evaluate_outcomes

    return evaluate_outcomes(config, run)


def _build_strategy_lifecycle_state(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.strategy.strategy_lifecycle import build_strategy_lifecycle_state

    return build_strategy_lifecycle_state(config, run)


def _build_strategy_lifecycle_material(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.strategy.strategy_lifecycle_material import build_strategy_lifecycle_material

    return build_strategy_lifecycle_material(config, run)


def _build_feature_snapshots(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.decision.feature_snapshots import build_feature_snapshots

    return build_feature_snapshots(config, run)


def _build_factor_states(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.decision.factor_states import build_factor_states

    return build_factor_states(config, run)


def _build_multi_source_signals(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.decision.multi_source_signals import build_multi_source_signals

    return build_multi_source_signals(config, run)


def _build_intelligence_fusion(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.decision.intelligence_fusion import build_intelligence_fusion

    return build_intelligence_fusion(config, run)


def _integrate_intelligence_fusion(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.decision.fusion_integration import integrate_intelligence_fusion

    return integrate_intelligence_fusion(config, run)


def _build_user_state_context(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.decision.user_state import build_user_state_context

    return build_user_state_context(config, run)


def _build_personalized_risk_constraints(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.decision.personalized_risk import build_personalized_risk_constraints

    return build_personalized_risk_constraints(config, run)


def _integrate_personalized_risk_constraints(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.decision.personalized_integration import integrate_personalized_risk_constraints

    return integrate_personalized_risk_constraints(config, run)


def _build_personalized_risk_material(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.analysis.personalized_risk_material import build_personalized_risk_material

    return build_personalized_risk_material(config, run)


def _build_analysis_materials(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.analysis.data_quality_material import build_data_quality_material
    from halpha.analysis.derivatives_market_material import build_derivatives_market_material
    from halpha.analysis.factor_signal_material import build_factor_signal_material
    from halpha.analysis.intelligence_fusion_material import build_intelligence_fusion_material
    from halpha.analysis.market_material import build_market_material
    from halpha.analysis.outcome_tracking_material import build_outcome_tracking_material
    from halpha.analysis.text_material import build_text_material
    from halpha.data.data_quality import refresh_post_data_quality_checks

    artifacts = []
    try:
        artifacts.extend(build_factor_signal_material(config, run))
        artifacts.extend(build_intelligence_fusion_material(config, run))
        refresh_post_data_quality_checks(config, run)
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


def _build_research_context(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.analysis.research_context import build_research_context

    return build_research_context(config, run)


def _build_codex_context(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.codex.context_builder import build_codex_context

    return build_codex_context(config, run)


def _run_codex_report(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.codex.runner import run_codex_report

    return run_codex_report(config, run)


def _validate_product_contracts(config: dict[str, Any], run: RunContext) -> list[str] | None:
    from halpha.product.product_validation import build_product_contract_validation

    return build_product_contract_validation(config, run)


__all__ = ["default_stage_handlers"]
