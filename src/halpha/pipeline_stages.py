from __future__ import annotations

from dataclasses import dataclass


STAGE_ORDER = (
    "refresh_data",
    "build_source_evidence",
    "run_strategy_research",
    "synthesize_intelligence",
    "build_materials",
    "generate_report",
    "finalize_run",
)
STAGE_TASKS = {
    "refresh_data": (
        "collect_market_data",
        "collect_derivatives_market_data",
        "sync_derivatives_market_history",
        "collect_macro_calendar_data",
        "sync_macro_calendar_history",
        "collect_onchain_flow_data",
        "sync_onchain_flow_history",
        "collect_text_events",
        "sync_ohlcv",
    ),
    "build_source_evidence": (
        "build_derivatives_market_views",
        "build_derivatives_market_context",
        "build_macro_calendar_views",
        "build_macro_calendar_context",
        "build_macro_calendar_material",
        "build_onchain_flow_views",
        "build_onchain_flow_context",
        "build_onchain_flow_material",
        "build_text_event_records",
        "build_text_entity_evidence",
        "build_text_event_classification_evidence",
        "build_text_event_topics",
        "build_text_event_signals",
        "build_market_data_views",
    ),
    "run_strategy_research": (
        "build_strategy_benchmark_suite",
        "evaluate_quant_strategies",
        "evaluate_strategy_evaluation",
        "build_strategy_experiment_material",
        "build_market_signals",
        "build_market_signal_material",
    ),
    "synthesize_intelligence": (
        "build_market_regime_assessment",
        "build_risk_assessment",
        "build_decision_recommendations",
        "build_watch_triggers",
        "build_event_market_confluence",
        "build_event_intelligence_assessment",
        "build_alert_decisions",
        "build_decision_intelligence_delta",
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
    ),
    "build_materials": (
        "build_alert_decision_material",
        "build_event_intelligence_material",
        "build_decision_intelligence_material",
        "build_data_quality_summary",
        "build_personalized_risk_material",
        "build_analysis_materials",
    ),
    "generate_report": (
        "build_research_context",
        "build_codex_context",
        "run_codex_report",
    ),
    "finalize_run": ("validate_product_contracts",),
}
TASK_STAGE_MAP = {
    task: stage
    for stage, tasks in STAGE_TASKS.items()
    for task in tasks
}
OPERATION_ORDER = tuple(
    task
    for stage in STAGE_ORDER
    for task in STAGE_TASKS[stage]
)
LEGACY_OPERATION_ORDER = (
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
STAGE_OUTPUTS = {
    "collect_market_data": ("raw/market.json",),
    "collect_derivatives_market_data": ("raw/derivatives_market.json",),
    "sync_derivatives_market_history": (
        "data/market/metadata/derivatives_market_schema.json",
        "data/market/metadata/derivatives_market_state.json",
    ),
    "build_derivatives_market_views": ("raw/derivatives_market_views.json",),
    "build_derivatives_market_context": ("analysis/derivatives_market_context.json",),
    "collect_macro_calendar_data": ("raw/macro_calendar.json",),
    "sync_macro_calendar_history": (
        "data/macro/metadata/macro_calendar_schema.json",
        "data/macro/metadata/macro_calendar_state.json",
    ),
    "build_macro_calendar_views": ("raw/macro_calendar_views.json",),
    "build_macro_calendar_context": ("analysis/macro_calendar_context.json",),
    "build_macro_calendar_material": ("analysis/macro_calendar_material.md",),
    "collect_onchain_flow_data": ("raw/onchain_flow.json",),
    "sync_onchain_flow_history": (
        "data/onchain/metadata/onchain_flow_schema.json",
        "data/onchain/metadata/onchain_flow_state.json",
    ),
    "build_onchain_flow_views": ("raw/onchain_flow_views.json",),
    "build_onchain_flow_context": ("analysis/onchain_flow_context.json",),
    "build_onchain_flow_material": ("analysis/onchain_flow_material.md",),
    "collect_text_events": ("raw/text_events.json",),
    "build_text_event_records": (
        "analysis/text_event_records.json",
        "data/research/metadata/text_event_history_state.json",
    ),
    "build_text_entity_evidence": ("analysis/text_entity_evidence.json",),
    "build_text_event_classification_evidence": ("analysis/text_event_classification_evidence.json",),
    "build_text_event_topics": ("analysis/text_event_topics.json",),
    "build_text_event_signals": ("analysis/text_event_signals.json",),
    "sync_ohlcv": (
        "data/market/metadata/ohlcv_schema.json",
        "data/market/metadata/ohlcv_sync_state.json",
    ),
    "build_market_data_views": ("raw/market_data_views.json",),
    "build_strategy_benchmark_suite": ("analysis/strategy_benchmark_suite.json",),
    "evaluate_quant_strategies": ("analysis/quant_strategy_runs.json",),
    "evaluate_strategy_evaluation": ("analysis/strategy_evaluation_summary.json",),
    "build_strategy_experiment_material": (
        "analysis/strategy_experiment.json",
        "analysis/strategy_effectiveness_gates.json",
        "analysis/strategy_experiment_material.md",
    ),
    "build_market_signals": ("analysis/market_signals.json",),
    "build_market_signal_material": ("analysis/market_signal_material.md",),
    "build_market_regime_assessment": ("analysis/market_regime_assessment.json",),
    "build_risk_assessment": ("analysis/risk_assessment.json",),
    "build_decision_recommendations": ("analysis/decision_recommendations.json",),
    "build_watch_triggers": ("analysis/watch_triggers.json",),
    "build_event_market_confluence": ("analysis/event_market_confluence.json",),
    "build_event_intelligence_assessment": ("analysis/event_intelligence_assessment.json",),
    "build_alert_decisions": ("analysis/alert_decisions.json",),
    "build_alert_decision_material": ("analysis/alert_decision_material.md",),
    "build_event_intelligence_material": ("analysis/event_intelligence_material.md",),
    "build_decision_intelligence_delta": ("analysis/decision_intelligence_delta.json",),
    "build_decision_intelligence_material": ("analysis/decision_intelligence_material.md",),
    "build_data_quality_summary": ("analysis/data_quality_summary.json",),
    "build_outcome_targets": ("analysis/outcome_targets.json",),
    "evaluate_outcomes": ("analysis/outcome_evaluations.json",),
    "build_strategy_lifecycle_state": ("analysis/strategy_lifecycle_state.json",),
    "build_strategy_lifecycle_material": ("analysis/strategy_lifecycle_material.md",),
    "build_feature_snapshots": ("analysis/feature_snapshots.json",),
    "build_factor_states": ("analysis/factor_states.json",),
    "build_multi_source_signals": ("analysis/multi_source_signals.json",),
    "build_intelligence_fusion": ("analysis/intelligence_fusion.json",),
    "integrate_intelligence_fusion": (
        "analysis/decision_recommendations.json",
        "analysis/alert_decisions.json",
    ),
    "build_user_state_context": ("analysis/user_state_context.json",),
    "build_personalized_risk_constraints": ("analysis/personalized_risk_constraints.json",),
    "integrate_personalized_risk_constraints": (
        "analysis/decision_recommendations.json",
        "analysis/alert_decisions.json",
    ),
    "build_personalized_risk_material": ("analysis/personalized_risk_material.md",),
    "build_analysis_materials": (
        "analysis/market_material.md",
        "analysis/text_material.md",
        "analysis/data_quality_material.md",
        "analysis/derivatives_market_material.md",
        "analysis/outcome_tracking_material.md",
        "analysis/factor_signal_material.md",
        "analysis/intelligence_fusion_material.md",
    ),
    "build_research_context": ("analysis/research_context.md",),
    "build_codex_context": ("codex_context/context.md", "codex_context/prompt.md"),
    "run_codex_report": ("report/report.md",),
    "validate_product_contracts": ("analysis/product_contract_validation.json",),
}
STAGE_ENABLED_CONDITIONS = {
    "collect_derivatives_market_data": "market.derivatives.enabled",
    "collect_macro_calendar_data": "macro_calendar.enabled",
    "collect_onchain_flow_data": "onchain_flow.enabled",
    "collect_text_events": "text.enabled",
    "evaluate_quant_strategies": "quant.enabled",
    "run_codex_report": "codex.enabled and not --no-codex",
}


@dataclass(frozen=True)
class StageOperation:
    operation_id: str
    dependencies: tuple[str, ...]
    outputs: tuple[str, ...] = ()
    enabled_condition: str | None = None


STAGE_OPERATIONS = tuple(
    StageOperation(
        operation_id=operation,
        dependencies=() if index == 0 else (OPERATION_ORDER[index - 1],),
        outputs=STAGE_OUTPUTS.get(operation, ()),
        enabled_condition=STAGE_ENABLED_CONDITIONS.get(operation),
    )
    for index, operation in enumerate(OPERATION_ORDER)
)
STAGE_OPERATION_MAP = {operation.operation_id: operation for operation in STAGE_OPERATIONS}


class StageSelectionError(Exception):
    """Raised when a requested validation stage is not known."""


def operation_metadata() -> list[dict[str, object]]:
    return [
        {
            "operation_id": operation.operation_id,
            "dependencies": list(operation.dependencies),
            "outputs": list(operation.outputs),
            "enabled_condition": operation.enabled_condition,
        }
        for operation in STAGE_OPERATIONS
    ]


def downstream_closure(stage: str, *, through_stage: str | None = None) -> list[str]:
    validate_stage_graph()
    validate_stage(stage, option_name="stage")
    if through_stage is not None:
        validate_stage(through_stage, option_name="through_stage")
        if STAGE_ORDER.index(through_stage) < STAGE_ORDER.index(stage):
            return []
        terminal_index = STAGE_ORDER.index(through_stage)
        return list(STAGE_ORDER[STAGE_ORDER.index(stage) : terminal_index + 1])
    return list(STAGE_ORDER[STAGE_ORDER.index(stage) :])


def operation_downstream_closure(operation_id: str, *, through_operation: str | None = None) -> list[str]:
    validate_stage_graph()
    validate_operation(operation_id, option_name="operation")
    if through_operation is not None:
        validate_operation(through_operation, option_name="through_operation")
        if OPERATION_ORDER.index(through_operation) < OPERATION_ORDER.index(operation_id):
            return []

    closure = {operation_id}
    changed = True
    while changed:
        changed = False
        for operation in STAGE_OPERATIONS:
            if operation.operation_id in closure:
                continue
            if any(dependency in closure for dependency in operation.dependencies):
                closure.add(operation.operation_id)
                changed = True

    ordered = [item for item in OPERATION_ORDER if item in closure]
    if through_operation is None:
        return ordered
    terminal_index = OPERATION_ORDER.index(through_operation)
    return [item for item in ordered if OPERATION_ORDER.index(item) <= terminal_index]


def tasks_for_stage(stage: str) -> list[str]:
    validate_stage(stage, option_name="stage")
    return list(STAGE_TASKS[stage])


def stage_for_task(operation_id: str) -> str:
    validate_operation(operation_id, option_name="operation")
    return TASK_STAGE_MAP[operation_id]


def stages_after(stage: str) -> list[str]:
    index = STAGE_ORDER.index(stage)
    return list(STAGE_ORDER[index + 1 :])


def stages_before(stage: str) -> list[str]:
    index = STAGE_ORDER.index(stage)
    return list(STAGE_ORDER[:index])


def validate_optional_stage(stage: str | None, *, option_name: str) -> None:
    if stage is None:
        return
    validate_stage(stage, option_name=option_name)


def validate_stage(stage: str, *, option_name: str) -> None:
    if stage not in STAGE_ORDER:
        supported = ", ".join(STAGE_ORDER)
        raise StageSelectionError(f"{option_name} must be one of: {supported}.")


def validate_operation(operation_id: str, *, option_name: str) -> None:
    if operation_id not in OPERATION_ORDER:
        supported = ", ".join(OPERATION_ORDER)
        raise StageSelectionError(f"{option_name} must be one of: {supported}.")


def validate_stage_graph() -> None:
    if tuple(STAGE_TASKS) != STAGE_ORDER:
        raise ValueError("pipeline product stages must be registered exactly once in canonical order.")
    task_ids = [task for tasks in STAGE_TASKS.values() for task in tasks]
    if len(task_ids) != len(set(task_ids)):
        raise ValueError("pipeline task ownership must be unique.")
    if set(task_ids) != set(LEGACY_OPERATION_ORDER):
        missing = sorted(set(LEGACY_OPERATION_ORDER) - set(task_ids))
        extra = sorted(set(task_ids) - set(LEGACY_OPERATION_ORDER))
        raise ValueError(f"pipeline task ownership mismatch; missing={missing}, extra={extra}.")
    operation_ids = [operation.operation_id for operation in STAGE_OPERATIONS]
    if operation_ids != list(OPERATION_ORDER):
        raise ValueError("pipeline operation metadata must register every stage exactly once in canonical order.")
    unknown_output_stages = set(STAGE_OUTPUTS) - set(OPERATION_ORDER)
    if unknown_output_stages:
        raise ValueError(f"pipeline operation outputs reference unknown stages: {sorted(unknown_output_stages)}.")
    unknown_enabled_stages = set(STAGE_ENABLED_CONDITIONS) - set(OPERATION_ORDER)
    if unknown_enabled_stages:
        raise ValueError(
            f"pipeline operation enabled conditions reference unknown stages: {sorted(unknown_enabled_stages)}."
        )

    seen: set[str] = set()
    for operation in STAGE_OPERATIONS:
        for dependency in operation.dependencies:
            if dependency not in STAGE_OPERATION_MAP:
                raise ValueError(
                    f"pipeline operation {operation.operation_id} depends on unknown operation {dependency}."
                )
            if dependency not in seen:
                raise ValueError(
                    f"pipeline operation graph must be acyclic; {operation.operation_id} depends on {dependency}."
                )
            if STAGE_ORDER.index(TASK_STAGE_MAP[dependency]) > STAGE_ORDER.index(TASK_STAGE_MAP[operation.operation_id]):
                raise ValueError(
                    f"pipeline operation {operation.operation_id} depends on later-stage task {dependency}."
                )
        seen.add(operation.operation_id)
