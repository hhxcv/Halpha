from __future__ import annotations


STAGE_ORDER = (
    "collect_market_data",
    "collect_derivatives_market_data",
    "sync_derivatives_market_history",
    "build_derivatives_market_views",
    "build_derivatives_market_context",
    "collect_macro_calendar_data",
    "sync_macro_calendar_history",
    "build_macro_calendar_views",
    "build_macro_calendar_context",
    "build_macro_calendar_material",
    "collect_onchain_flow_data",
    "sync_onchain_flow_history",
    "build_onchain_flow_views",
    "build_onchain_flow_context",
    "build_onchain_flow_material",
    "collect_text_events",
    "build_text_event_records",
    "build_text_entity_evidence",
    "build_text_event_classification_evidence",
    "build_text_event_topics",
    "build_text_event_signals",
    "sync_ohlcv",
    "build_market_data_views",
    "build_strategy_benchmark_suite",
    "evaluate_quant_strategies",
    "evaluate_strategy_evaluation",
    "build_strategy_experiment_material",
    "evaluate_market_strategy_signals",
    "build_market_signals",
    "build_market_signal_material",
    "build_market_regime_assessment",
    "build_risk_assessment",
    "build_decision_recommendations",
    "build_watch_triggers",
    "build_event_market_confluence",
    "build_event_intelligence_assessment",
    "build_alert_decisions",
    "build_alert_decision_material",
    "build_event_intelligence_material",
    "build_decision_intelligence_delta",
    "build_decision_intelligence_material",
    "build_data_quality_summary",
    "build_outcome_targets",
    "evaluate_outcomes",
    "build_strategy_lifecycle_state",
    "build_strategy_lifecycle_material",
    "build_feature_snapshots",
    "build_factor_states",
    "build_multi_source_signals",
    "build_intelligence_fusion",
    "integrate_intelligence_fusion",
    "build_user_state_context",
    "build_personalized_risk_constraints",
    "integrate_personalized_risk_constraints",
    "build_personalized_risk_material",
    "build_analysis_materials",
    "build_research_context",
    "build_codex_context",
    "run_codex_report",
    "validate_product_contracts",
)
DECISION_INTELLIGENCE_STAGES = {
    "build_market_regime_assessment",
    "build_risk_assessment",
    "build_decision_recommendations",
    "build_watch_triggers",
    "build_decision_intelligence_delta",
    "build_decision_intelligence_material",
}


class StageSelectionError(Exception):
    """Raised when a requested validation stage is not known."""


def stages_after(stage: str) -> list[str]:
    index = STAGE_ORDER.index(stage)
    return list(STAGE_ORDER[index + 1 :])


def validate_optional_stage(stage: str | None, *, option_name: str) -> None:
    if stage is None:
        return
    validate_stage(stage, option_name=option_name)


def validate_stage(stage: str, *, option_name: str) -> None:
    if stage not in STAGE_ORDER:
        supported = ", ".join(STAGE_ORDER)
        raise StageSelectionError(f"{option_name} must be one of: {supported}.")
