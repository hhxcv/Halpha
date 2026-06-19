from __future__ import annotations

from pathlib import Path
from typing import Any

from halpha.codex.input_budget import (
    CODEX_INPUT_POLICY,
    DEFAULT_MATERIAL_MAX_CHARS,
    RESEARCH_CONTEXT_MAX_CHARS,
    text_budget_record,
    update_codex_input_manifest,
)
from halpha.pipeline import PipelineError, RunContext


STAGE_NAME = "build_research_context"
RESEARCH_CONTEXT_ARTIFACT = "analysis/research_context.md"
MARKET_MATERIAL_ARTIFACT = "analysis/market_material.md"
MARKET_SIGNAL_MATERIAL_ARTIFACT = "analysis/market_signal_material.md"
DERIVATIVES_MARKET_MATERIAL_ARTIFACT = "analysis/derivatives_market_material.md"
MACRO_CALENDAR_MATERIAL_ARTIFACT = "analysis/macro_calendar_material.md"
ONCHAIN_FLOW_MATERIAL_ARTIFACT = "analysis/onchain_flow_material.md"
STRATEGY_EVALUATION_MATERIAL_ARTIFACT = "analysis/strategy_evaluation_material.md"
STRATEGY_EXPERIMENT_MATERIAL_ARTIFACT = "analysis/strategy_experiment_material.md"
FACTOR_SIGNAL_MATERIAL_ARTIFACT = "analysis/factor_signal_material.md"
INTELLIGENCE_FUSION_MATERIAL_ARTIFACT = "analysis/intelligence_fusion_material.md"
DECISION_INTELLIGENCE_MATERIAL_ARTIFACT = "analysis/decision_intelligence_material.md"
ALERT_DECISION_MATERIAL_ARTIFACT = "analysis/alert_decision_material.md"
EVENT_INTELLIGENCE_MATERIAL_ARTIFACT = "analysis/event_intelligence_material.md"
TEXT_MATERIAL_ARTIFACT = "analysis/text_material.md"
DATA_QUALITY_MATERIAL_ARTIFACT = "analysis/data_quality_material.md"
OUTCOME_TRACKING_MATERIAL_ARTIFACT = "analysis/outcome_tracking_material.md"


def build_research_context(config: dict[str, Any], run: RunContext) -> list[str]:
    artifact_index = _artifact_index(run)
    market_material = _read_material(
        run.analysis_dir / "market_material.md",
        MARKET_MATERIAL_ARTIFACT,
        enabled=bool(config.get("market", {}).get("enabled")),
        producer_stage="build_analysis_materials",
    )
    text_material = _read_material(
        run.analysis_dir / "text_material.md",
        TEXT_MATERIAL_ARTIFACT,
        enabled=bool(config.get("text", {}).get("enabled")),
        producer_stage="build_analysis_materials",
    )
    data_quality_material = _read_material(
        run.analysis_dir / "data_quality_material.md",
        DATA_QUALITY_MATERIAL_ARTIFACT,
        enabled=bool(run.manifest.get("artifacts", {}).get("data_quality_material")),
        producer_stage="build_analysis_materials",
    )
    outcome_tracking_material = _read_material(
        run.analysis_dir / "outcome_tracking_material.md",
        OUTCOME_TRACKING_MATERIAL_ARTIFACT,
        enabled=bool(run.manifest.get("artifacts", {}).get("outcome_tracking_material")),
        producer_stage="build_analysis_materials",
    )
    market_signal_material = _read_material(
        run.analysis_dir / "market_signal_material.md",
        MARKET_SIGNAL_MATERIAL_ARTIFACT,
        enabled=_quant_enabled(config),
        producer_stage="build_market_signal_material",
    )
    derivatives_market_material = _read_material(
        run.analysis_dir / "derivatives_market_material.md",
        DERIVATIVES_MARKET_MATERIAL_ARTIFACT,
        enabled=bool(run.manifest.get("artifacts", {}).get("derivatives_market_material")),
        producer_stage="build_analysis_materials",
    )
    macro_calendar_material = _read_material(
        run.analysis_dir / "macro_calendar_material.md",
        MACRO_CALENDAR_MATERIAL_ARTIFACT,
        enabled=bool(run.manifest.get("artifacts", {}).get("macro_calendar_material")),
        producer_stage="build_macro_calendar_material",
    )
    onchain_flow_material = _read_material(
        run.analysis_dir / "onchain_flow_material.md",
        ONCHAIN_FLOW_MATERIAL_ARTIFACT,
        enabled=bool(run.manifest.get("artifacts", {}).get("onchain_flow_material")),
        producer_stage="build_onchain_flow_material",
    )
    strategy_evaluation_material = _read_material(
        run.analysis_dir / "strategy_evaluation_material.md",
        STRATEGY_EVALUATION_MATERIAL_ARTIFACT,
        enabled=bool(run.manifest.get("artifacts", {}).get("strategy_evaluation_material")),
        producer_stage="evaluate_strategy_evaluation",
    )
    strategy_experiment_material = _read_material(
        run.analysis_dir / "strategy_experiment_material.md",
        STRATEGY_EXPERIMENT_MATERIAL_ARTIFACT,
        enabled=bool(run.manifest.get("artifacts", {}).get("strategy_experiment_material")),
        producer_stage="build_strategy_experiment_material",
    )
    factor_signal_material = _read_material(
        run.analysis_dir / "factor_signal_material.md",
        FACTOR_SIGNAL_MATERIAL_ARTIFACT,
        enabled=bool(run.manifest.get("artifacts", {}).get("factor_signal_material")),
        producer_stage="build_analysis_materials",
    )
    intelligence_fusion_material = _read_material(
        run.analysis_dir / "intelligence_fusion_material.md",
        INTELLIGENCE_FUSION_MATERIAL_ARTIFACT,
        enabled=bool(run.manifest.get("artifacts", {}).get("intelligence_fusion_material")),
        producer_stage="build_analysis_materials",
    )
    decision_intelligence_material = _read_material(
        run.analysis_dir / "decision_intelligence_material.md",
        DECISION_INTELLIGENCE_MATERIAL_ARTIFACT,
        enabled=_quant_enabled(config),
        producer_stage="build_decision_intelligence_material",
    )
    alert_decision_material = _read_material(
        run.analysis_dir / "alert_decision_material.md",
        ALERT_DECISION_MATERIAL_ARTIFACT,
        enabled=bool(run.manifest.get("artifacts", {}).get("alert_decision_material")),
        producer_stage="build_alert_decision_material",
    )
    event_intelligence_material = _read_material(
        run.analysis_dir / "event_intelligence_material.md",
        EVENT_INTELLIGENCE_MATERIAL_ARTIFACT,
        enabled=bool(run.manifest.get("artifacts", {}).get("event_intelligence_material")),
        producer_stage="build_event_intelligence_material",
    )
    material_inputs = _prepare_material_inputs(
        market_material=market_material,
        market_signal_material=market_signal_material,
        derivatives_market_material=derivatives_market_material,
        macro_calendar_material=macro_calendar_material,
        onchain_flow_material=onchain_flow_material,
        strategy_evaluation_material=strategy_evaluation_material,
        strategy_experiment_material=strategy_experiment_material,
        factor_signal_material=factor_signal_material,
        intelligence_fusion_material=intelligence_fusion_material,
        decision_intelligence_material=decision_intelligence_material,
        alert_decision_material=alert_decision_material,
        event_intelligence_material=event_intelligence_material,
        data_quality_material=data_quality_material,
        outcome_tracking_material=outcome_tracking_material,
        text_material=text_material,
    )

    context = render_research_context(
        config,
        run=run,
        artifact_index=artifact_index,
        market_material=material_inputs[MARKET_MATERIAL_ARTIFACT]["content"],
        market_signal_material=material_inputs[MARKET_SIGNAL_MATERIAL_ARTIFACT]["content"],
        derivatives_market_material=material_inputs[DERIVATIVES_MARKET_MATERIAL_ARTIFACT]["content"],
        macro_calendar_material=material_inputs[MACRO_CALENDAR_MATERIAL_ARTIFACT]["content"],
        onchain_flow_material=material_inputs[ONCHAIN_FLOW_MATERIAL_ARTIFACT]["content"],
        strategy_evaluation_material=material_inputs[STRATEGY_EVALUATION_MATERIAL_ARTIFACT]["content"],
        strategy_experiment_material=material_inputs[STRATEGY_EXPERIMENT_MATERIAL_ARTIFACT]["content"],
        factor_signal_material=material_inputs[FACTOR_SIGNAL_MATERIAL_ARTIFACT]["content"],
        intelligence_fusion_material=material_inputs[INTELLIGENCE_FUSION_MATERIAL_ARTIFACT]["content"],
        decision_intelligence_material=material_inputs[DECISION_INTELLIGENCE_MATERIAL_ARTIFACT]["content"],
        alert_decision_material=material_inputs[ALERT_DECISION_MATERIAL_ARTIFACT]["content"],
        event_intelligence_material=material_inputs[EVENT_INTELLIGENCE_MATERIAL_ARTIFACT]["content"],
        data_quality_material=material_inputs[DATA_QUALITY_MATERIAL_ARTIFACT]["content"],
        outcome_tracking_material=material_inputs[OUTCOME_TRACKING_MATERIAL_ARTIFACT]["content"],
        text_material=material_inputs[TEXT_MATERIAL_ARTIFACT]["content"],
    )
    output_path = run.analysis_dir / "research_context.md"
    output_path.write_text(context, encoding="utf-8")
    run.manifest["artifacts"]["research_context"] = RESEARCH_CONTEXT_ARTIFACT
    update_codex_input_manifest(
        run.manifest,
        materials=[value["budget"] for value in material_inputs.values()],
        research_context=text_budget_record(
            RESEARCH_CONTEXT_ARTIFACT,
            context,
            status="included",
            max_chars=RESEARCH_CONTEXT_MAX_CHARS,
            role="research_context",
        ),
    )
    return [RESEARCH_CONTEXT_ARTIFACT]


def render_research_context(
    config: dict[str, Any],
    *,
    run: RunContext,
    artifact_index: dict[str, Any],
    market_material: str | None,
    market_signal_material: str | None,
    derivatives_market_material: str | None,
    macro_calendar_material: str | None,
    onchain_flow_material: str | None,
    strategy_evaluation_material: str | None,
    strategy_experiment_material: str | None,
    factor_signal_material: str | None,
    intelligence_fusion_material: str | None,
    decision_intelligence_material: str | None,
    alert_decision_material: str | None,
    event_intelligence_material: str | None,
    data_quality_material: str | None,
    outcome_tracking_material: str | None,
    text_material: str | None,
) -> str:
    source_artifacts = [value for value in artifact_index.values() if value is not None]
    lines = [
        "---",
        "artifact_type: research_context",
        "schema_version: 1",
        "audience: codex_cli",
        "language_target: zh-CN",
        "source_artifacts:",
        *_yaml_list(source_artifacts),
        "---",
        "",
        "# research_context",
        "",
        "## run",
        "",
        "```yaml",
        _yaml_block(_run_summary(config, run)).rstrip(),
        "```",
        "",
        "## material_index",
        "",
        "```yaml",
        _yaml_block(artifact_index).rstrip(),
        "```",
        "",
        "## source_policy",
        "",
        "```yaml",
        _yaml_block(_source_policy()).rstrip(),
        "```",
        "",
        "## codex_input_policy",
        "",
        "```yaml",
        _yaml_block(_codex_input_policy()).rstrip(),
        "```",
        "",
        "## generation_constraints",
        "",
        "```yaml",
        _yaml_block(_generation_constraints()).rstrip(),
        "```",
        "",
        "## market_material",
        "",
    ]
    lines.extend(_embedded_material(MARKET_MATERIAL_ARTIFACT, market_material))
    lines.extend(["", "## market_signal_material", ""])
    lines.extend(_embedded_material(MARKET_SIGNAL_MATERIAL_ARTIFACT, market_signal_material))
    lines.extend(["", "## derivatives_market_material", ""])
    lines.extend(_embedded_material(DERIVATIVES_MARKET_MATERIAL_ARTIFACT, derivatives_market_material))
    lines.extend(["", "## macro_calendar_material", ""])
    lines.extend(_embedded_material(MACRO_CALENDAR_MATERIAL_ARTIFACT, macro_calendar_material))
    lines.extend(["", "## onchain_flow_material", ""])
    lines.extend(_embedded_material(ONCHAIN_FLOW_MATERIAL_ARTIFACT, onchain_flow_material))
    lines.extend(["", "## strategy_evaluation_material", ""])
    lines.extend(_embedded_material(STRATEGY_EVALUATION_MATERIAL_ARTIFACT, strategy_evaluation_material))
    lines.extend(["", "## strategy_experiment_material", ""])
    lines.extend(_embedded_material(STRATEGY_EXPERIMENT_MATERIAL_ARTIFACT, strategy_experiment_material))
    lines.extend(["", "## factor_signal_material", ""])
    lines.extend(_embedded_material(FACTOR_SIGNAL_MATERIAL_ARTIFACT, factor_signal_material))
    lines.extend(["", "## intelligence_fusion_material", ""])
    lines.extend(_embedded_material(INTELLIGENCE_FUSION_MATERIAL_ARTIFACT, intelligence_fusion_material))
    lines.extend(["", "## decision_intelligence_material", ""])
    lines.extend(_embedded_material(DECISION_INTELLIGENCE_MATERIAL_ARTIFACT, decision_intelligence_material))
    lines.extend(["", "## alert_decision_material", ""])
    lines.extend(_embedded_material(ALERT_DECISION_MATERIAL_ARTIFACT, alert_decision_material))
    lines.extend(["", "## event_intelligence_material", ""])
    lines.extend(_embedded_material(EVENT_INTELLIGENCE_MATERIAL_ARTIFACT, event_intelligence_material))
    lines.extend(["", "## data_quality_material", ""])
    lines.extend(_embedded_material(DATA_QUALITY_MATERIAL_ARTIFACT, data_quality_material))
    lines.extend(["", "## outcome_tracking_material", ""])
    lines.extend(_embedded_material(OUTCOME_TRACKING_MATERIAL_ARTIFACT, outcome_tracking_material))
    lines.extend(["", "## text_material", ""])
    lines.extend(_embedded_material(TEXT_MATERIAL_ARTIFACT, text_material))
    return "\n".join(lines)


def _artifact_index(run: RunContext) -> dict[str, Any]:
    artifacts = run.manifest.get("artifacts", {})
    index = {
        "raw_market": artifacts.get("raw_market"),
        "raw_text_events": artifacts.get("raw_text_events"),
        "market_signal_material": artifacts.get("market_signal_material"),
        "derivatives_market_material": artifacts.get("derivatives_market_material"),
        "macro_calendar_material": artifacts.get("macro_calendar_material"),
        "onchain_flow_material": artifacts.get("onchain_flow_material"),
        "feature_snapshots": artifacts.get("feature_snapshots"),
        "factor_states": artifacts.get("factor_states"),
        "multi_source_signals": artifacts.get("multi_source_signals"),
        "intelligence_fusion": artifacts.get("intelligence_fusion"),
        "intelligence_fusion_material": artifacts.get("intelligence_fusion_material"),
        "factor_signal_material": artifacts.get("factor_signal_material"),
        "data_quality_summary": artifacts.get("data_quality_summary"),
        "data_quality_material": artifacts.get("data_quality_material"),
        "outcome_tracking_material": artifacts.get("outcome_tracking_material"),
        "market_material": artifacts.get("market_material"),
        "text_material": artifacts.get("text_material"),
    }
    if artifacts.get("outcome_tracking_material"):
        index.update(
            {
                "outcome_targets": artifacts.get("outcome_targets"),
                "outcome_evaluations": artifacts.get("outcome_evaluations"),
                "outcome_history_state": artifacts.get("outcome_history_state"),
                "outcome_tracking_material": artifacts.get("outcome_tracking_material"),
            }
        )
    if artifacts.get("market_signal_material"):
        index.update(
            {
                "market_data_views": artifacts.get("market_data_views"),
                "quant_strategy_runs": artifacts.get("quant_strategy_runs"),
                "strategy_evaluation_summary": artifacts.get("strategy_evaluation_summary"),
                "strategy_evaluation_material": artifacts.get("strategy_evaluation_material"),
                "strategy_experiment": artifacts.get("strategy_experiment"),
                "strategy_effectiveness_gates": artifacts.get("strategy_effectiveness_gates"),
                "strategy_experiment_material": artifacts.get("strategy_experiment_material"),
                "market_strategy_signals": artifacts.get("market_strategy_signals"),
                "market_signals": artifacts.get("market_signals"),
            }
        )
    if artifacts.get("derivatives_market_material"):
        index.update(
            {
                "raw_derivatives_market": artifacts.get("raw_derivatives_market"),
                "derivatives_market_state": artifacts.get("derivatives_market_state"),
                "derivatives_market_views": artifacts.get("derivatives_market_views"),
                "derivatives_market_context": artifacts.get("derivatives_market_context"),
                "derivatives_market_material": artifacts.get("derivatives_market_material"),
            }
        )
    if artifacts.get("macro_calendar_material"):
        index.update(
            {
                "macro_calendar_context": artifacts.get("macro_calendar_context"),
                "macro_calendar_material": artifacts.get("macro_calendar_material"),
            }
        )
    if artifacts.get("onchain_flow_material"):
        index.update(
            {
                "raw_onchain_flow": artifacts.get("raw_onchain_flow"),
                "onchain_flow_state": artifacts.get("onchain_flow_state"),
                "onchain_flow_views": artifacts.get("onchain_flow_views"),
                "onchain_flow_context": artifacts.get("onchain_flow_context"),
                "onchain_flow_material": artifacts.get("onchain_flow_material"),
            }
        )
    if artifacts.get("factor_signal_material"):
        index.update(
            {
                "feature_snapshots": artifacts.get("feature_snapshots"),
                "factor_states": artifacts.get("factor_states"),
                "multi_source_signals": artifacts.get("multi_source_signals"),
                "factor_signal_material": artifacts.get("factor_signal_material"),
            }
        )
    if artifacts.get("intelligence_fusion_material"):
        index.update(
            {
                "intelligence_fusion": artifacts.get("intelligence_fusion"),
                "intelligence_fusion_material": artifacts.get("intelligence_fusion_material"),
            }
        )
    if artifacts.get("decision_intelligence_material"):
        index.update(
            {
                "market_regime_assessment": artifacts.get("market_regime_assessment"),
                "risk_assessment": artifacts.get("risk_assessment"),
                "decision_recommendations": artifacts.get("decision_recommendations"),
                "watch_triggers": artifacts.get("watch_triggers"),
                "decision_intelligence_delta": artifacts.get("decision_intelligence_delta"),
                "decision_intelligence_material": artifacts.get("decision_intelligence_material"),
            }
        )
    if artifacts.get("event_intelligence_material"):
        index.update(
            {
                "text_event_records": artifacts.get("text_event_records"),
                "text_entity_evidence": artifacts.get("text_entity_evidence"),
                "text_event_classification_evidence": artifacts.get("text_event_classification_evidence"),
                "text_event_topics": artifacts.get("text_event_topics"),
                "text_event_signals": artifacts.get("text_event_signals"),
                "event_market_confluence": artifacts.get("event_market_confluence"),
                "event_intelligence_material": artifacts.get("event_intelligence_material"),
            }
        )
    if artifacts.get("alert_decision_material"):
        index.update(
            {
                "event_intelligence_assessment": artifacts.get("event_intelligence_assessment"),
                "alert_decisions": artifacts.get("alert_decisions"),
                "alert_decision_material": artifacts.get("alert_decision_material"),
            }
        )
    return index


def _read_material(path: Path, artifact: str, *, enabled: bool, producer_stage: str) -> str | None:
    if not enabled:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{artifact} was not found; {producer_stage} must run first.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc


def _run_summary(config: dict[str, Any], run: RunContext) -> dict[str, Any]:
    report = config.get("report", {})
    return {
        "run_id": run.run_id,
        "report_title": report.get("title"),
        "report_language": report.get("language"),
    }


def _quant_enabled(config: dict[str, Any]) -> bool:
    quant = config.get("quant")
    return isinstance(quant, dict) and quant.get("enabled") is True


def _source_policy() -> dict[str, Any]:
    return {
        "allowed_sources_only": True,
        "fabricate_missing_sources": False,
        "fabricate_missing_facts": False,
        "fabricate_missing_signals": False,
        "missing_url_label": "source_url_not_provided",
        "distinguish_facts_assumptions_uncertainties_judgment": True,
        "raw_ohlcv_history_embedded": False,
        "full_data_quality_json_embedded": False,
        "full_reusable_history_embedded": False,
        "full_outcome_history_embedded": False,
        "full_raw_derivatives_artifacts_embedded": False,
        "full_raw_macro_calendar_artifacts_embedded": False,
        "full_raw_onchain_flow_artifacts_embedded": False,
        "full_reusable_derivatives_history_embedded": False,
        "full_reusable_macro_calendar_history_embedded": False,
        "full_reusable_onchain_flow_history_embedded": False,
        "full_derivatives_views_embedded": False,
        "full_macro_calendar_views_embedded": False,
        "full_onchain_flow_views_embedded": False,
        "full_derivatives_context_json_embedded": False,
        "full_macro_calendar_context_json_embedded": False,
        "full_onchain_flow_context_json_embedded": False,
        "full_feature_snapshots_json_embedded": False,
        "full_factor_states_json_embedded": False,
        "full_multi_source_signals_json_embedded": False,
        "full_intelligence_fusion_json_embedded": False,
        "full_catalog_embedded": False,
        "full_run_index_embedded": False,
        "full_intermediate_json_embedded": False,
        "full_run_manifest_embedded": False,
        "bounded_report_facing_material_only": True,
        "financial_advice": False,
    }


def _codex_input_policy() -> dict[str, Any]:
    return {
        **CODEX_INPUT_POLICY,
        "default_material_max_chars": DEFAULT_MATERIAL_MAX_CHARS,
        "research_context_max_chars": RESEARCH_CONTEXT_MAX_CHARS,
    }


def _generation_constraints() -> dict[str, Any]:
    return {
        "output_language": "Simplified Chinese",
        "output_format": "Markdown",
        "use_only_embedded_context": True,
        "do_not_invent_prices_events_links_sources": True,
        "include_context_specific_risk_notes": True,
        "avoid_generic_disclaimers": True,
        "prefer_tables_for_comparable_data": True,
        "group_multi_symbol_sections_by_symbol": True,
        "title_is_h1_not_section": True,
        "synthesis_should_not_repeat_prior_sections": True,
        "quant_signal_requirements": {
            "include_when_market_signal_material_exists": True,
            "include_signal_conclusions": True,
            "include_evidence_near_conclusions": True,
            "include_uncertainty_near_conclusions": True,
            "include_watch_points": True,
            "include_risk_notes": True,
            "do_not_calculate_signals_from_raw_ohlcv_history": True,
            "do_not_inspect_shared_ohlcv_storage": True,
        },
        "strategy_evaluation_requirements": {
            "include_when_strategy_evaluation_material_exists": True,
            "include_cost_assumptions": True,
            "include_baseline_comparison": True,
            "include_sample_limits": True,
            "include_reliability_and_uncertainty": True,
            "do_not_generate_metrics": True,
            "do_not_upgrade_weak_or_unstable_evidence": True,
        },
        "strategy_experiment_gate_requirements": {
            "include_when_strategy_experiment_material_exists": True,
            "use_halpha_gate_statuses_only": True,
            "identify_effective_watchlisted_rejected_and_insufficient_evidence": True,
            "include_costs_benchmark_coverage_sample_limits_and_uncertainty": True,
            "do_not_generate_gate_outcomes": True,
            "do_not_upgrade_rejected_watchlisted_or_insufficient_evidence": True,
        },
        "factor_signal_requirements": {
            "include_when_factor_signal_material_exists": True,
            "use_halpha_feature_records_only": True,
            "use_halpha_factor_states_only": True,
            "use_halpha_multi_source_signal_states_only": True,
            "explain_agreement_conflict_missing_stale_degraded_and_uncertainty": True,
            "do_not_generate_feature_records": True,
            "do_not_generate_factor_scores": True,
            "do_not_generate_factor_states": True,
            "do_not_generate_signal_states": True,
            "do_not_generate_action_levels": True,
            "do_not_generate_price_forecasts": True,
            "do_not_create_trading_instructions": True,
            "full_feature_snapshots_json_embedded": False,
            "full_factor_states_json_embedded": False,
            "full_multi_source_signals_json_embedded": False,
        },
        "intelligence_fusion_requirements": {
            "include_when_intelligence_fusion_material_exists": True,
            "use_halpha_fusion_states_only": True,
            "explain_confluence_conflict_risk_override_event_override_outcome_feedback": True,
            "keep_uncertainty_near_fusion_statements": True,
            "do_not_generate_fusion_states": True,
            "do_not_generate_risk_overrides": True,
            "do_not_generate_event_overrides": True,
            "do_not_generate_alert_priorities": True,
            "do_not_generate_action_levels": True,
            "do_not_generate_price_forecasts": True,
            "do_not_create_trading_instructions": True,
            "full_intelligence_fusion_json_embedded": False,
        },
        "derivatives_market_requirements": {
            "include_when_derivatives_market_material_exists": True,
            "use_halpha_derivatives_context_states_only": True,
            "explain_source_availability_and_quality_limits": True,
            "do_not_generate_derivatives_states": True,
            "do_not_generate_derivatives_signals": True,
            "do_not_generate_risk_levels": True,
            "do_not_infer_missing_market_structure_data": True,
            "do_not_calculate_funding_open_interest_premium_basis_spread_depth_or_liquidations": True,
            "do_not_create_trading_instructions": True,
            "full_raw_derivatives_artifacts_embedded": False,
            "full_reusable_derivatives_history_embedded": False,
            "full_derivatives_context_json_embedded": False,
        },
        "macro_calendar_requirements": {
            "include_when_macro_calendar_material_exists": True,
            "use_halpha_macro_calendar_context_states_only": True,
            "explain_scheduled_catalyst_timing_risk": True,
            "distinguish_scheduled_catalyst_from_realized_market_impact": True,
            "explain_source_availability_freshness_time_zone_and_quality_limits": True,
            "do_not_generate_macro_events": True,
            "do_not_generate_macro_states": True,
            "do_not_generate_risk_levels": True,
            "do_not_generate_watch_triggers": True,
            "do_not_generate_alert_priorities": True,
            "do_not_infer_missing_source_data": True,
            "do_not_forecast_macro_outcomes": True,
            "do_not_generate_price_forecasts": True,
            "do_not_create_trading_instructions": True,
            "full_raw_macro_calendar_artifacts_embedded": False,
            "full_reusable_macro_calendar_history_embedded": False,
            "full_macro_calendar_views_embedded": False,
            "full_macro_calendar_context_json_embedded": False,
        },
        "onchain_flow_requirements": {
            "include_when_onchain_flow_material_exists": True,
            "use_halpha_onchain_flow_context_states_only": True,
            "explain_stablecoin_liquidity_chain_activity_network_congestion_and_source_availability": True,
            "explain_source_availability_freshness_and_quality_limits": True,
            "do_not_generate_onchain_records": True,
            "do_not_generate_flow_states": True,
            "do_not_generate_address_labels": True,
            "do_not_generate_risk_levels": True,
            "do_not_generate_watch_triggers": True,
            "do_not_generate_alert_priorities": True,
            "do_not_infer_missing_source_data": True,
            "do_not_infer_wallet_or_exchange_address_identity": True,
            "do_not_generate_price_forecasts": True,
            "do_not_create_trading_instructions": True,
            "full_raw_onchain_flow_artifacts_embedded": False,
            "full_reusable_onchain_flow_history_embedded": False,
            "full_onchain_flow_views_embedded": False,
            "full_onchain_flow_context_json_embedded": False,
        },
        "decision_intelligence_requirements": {
            "include_when_decision_intelligence_material_exists": True,
            "use_decision_material_for_decision_language": True,
            "use_quant_material_as_upstream_evidence": True,
            "include_current_decision_view": True,
            "include_what_to_do": True,
            "include_what_not_to_do": True,
            "include_tentative_opportunities": True,
            "include_wait_watch_conditions": True,
            "include_risk_state": True,
            "include_invalidation_conditions": True,
            "include_changes_versus_previous_run": True,
            "include_uncertainty_and_method_limits": True,
            "do_not_invent_action_levels": True,
            "do_not_upgrade_low_confidence_or_unsupported_material": True,
            "do_not_create_trading_instructions": True,
        },
        "alert_decision_requirements": {
            "include_when_alert_decision_material_exists": True,
            "use_halpha_alert_priorities_only": True,
            "include_p0_p1_p2_p3_and_no_alert_state_when_supported": True,
            "include_downgrade_and_suppression_reasons": True,
            "include_uncertainty_near_alert_state": True,
            "do_not_generate_alert_priority": True,
            "do_not_generate_event_severity": True,
            "do_not_generate_decision_impact": True,
            "do_not_generate_action_levels": True,
            "do_not_create_alert_delivery_or_trading_instructions": True,
        },
        "event_intelligence_requirements": {
            "include_when_event_intelligence_material_exists": True,
            "use_halpha_event_categories_only": True,
            "use_halpha_event_signals_only": True,
            "use_halpha_event_market_relationships_only": True,
            "include_source_coverage_topic_grouping_recency_and_uncertainty": True,
            "include_event_quant_confluence_or_conflict_when_supported": True,
            "financial_tone_is_not_a_trading_signal": True,
            "do_not_generate_event_classification": True,
            "do_not_generate_event_impacts": True,
            "do_not_generate_price_forecasts": True,
            "do_not_generate_action_guidance": True,
            "do_not_upgrade_low_confidence_or_unknown_event_evidence": True,
        },
        "data_quality_requirements": {
            "include_when_data_quality_material_exists": True,
            "use_halpha_quality_statuses_only": True,
            "explain_quality_limits_when_relevant": True,
            "keep_store_references_as_references_only": True,
            "do_not_generate_quality_checks": True,
            "do_not_generate_validation_results": True,
            "do_not_inspect_omitted_tables": True,
            "do_not_infer_missing_store_contents": True,
            "do_not_report_stage_time_run_index_skip_as_final_missing": True,
        },
        "outcome_tracking_requirements": {
            "include_when_outcome_tracking_material_exists": True,
            "use_halpha_outcome_states_only": True,
            "codex_may_explain_outcome_states": True,
            "do_not_generate_outcome_labels": True,
            "do_not_validate_missing_histories": True,
            "do_not_infer_omitted_store_contents": True,
            "do_not_score_prior_recommendations_independently": True,
            "do_not_rank_strategies_from_outcomes": True,
            "full_outcome_history_embedded": False,
        },
        "required_sections": [
            "核心摘要",
            "市场概览",
            "文本事件",
            "综合判断",
            "观察要点",
            "风险提示",
        ],
    }


def _embedded_material(artifact: str, content: str | None) -> list[str]:
    if content is None:
        return [
            "```yaml",
            _yaml_block({"artifact": artifact, "status": "not_generated"}).rstrip(),
            "```",
        ]
    return [
        f'<embed path="{artifact}">',
        content.rstrip(),
        "</embed>",
    ]


def _prepare_material_inputs(
    *,
    market_material: str | None,
    market_signal_material: str | None,
    derivatives_market_material: str | None,
    macro_calendar_material: str | None,
    onchain_flow_material: str | None,
    strategy_evaluation_material: str | None,
    strategy_experiment_material: str | None,
    factor_signal_material: str | None,
    intelligence_fusion_material: str | None,
    decision_intelligence_material: str | None,
    alert_decision_material: str | None,
    event_intelligence_material: str | None,
    data_quality_material: str | None,
    outcome_tracking_material: str | None,
    text_material: str | None,
) -> dict[str, dict[str, Any]]:
    materials = [
        (MARKET_MATERIAL_ARTIFACT, market_material),
        (MARKET_SIGNAL_MATERIAL_ARTIFACT, market_signal_material),
        (DERIVATIVES_MARKET_MATERIAL_ARTIFACT, derivatives_market_material),
        (MACRO_CALENDAR_MATERIAL_ARTIFACT, macro_calendar_material),
        (ONCHAIN_FLOW_MATERIAL_ARTIFACT, onchain_flow_material),
        (STRATEGY_EVALUATION_MATERIAL_ARTIFACT, strategy_evaluation_material),
        (STRATEGY_EXPERIMENT_MATERIAL_ARTIFACT, strategy_experiment_material),
        (FACTOR_SIGNAL_MATERIAL_ARTIFACT, factor_signal_material),
        (INTELLIGENCE_FUSION_MATERIAL_ARTIFACT, intelligence_fusion_material),
        (DECISION_INTELLIGENCE_MATERIAL_ARTIFACT, decision_intelligence_material),
        (ALERT_DECISION_MATERIAL_ARTIFACT, alert_decision_material),
        (EVENT_INTELLIGENCE_MATERIAL_ARTIFACT, event_intelligence_material),
        (DATA_QUALITY_MATERIAL_ARTIFACT, data_quality_material),
        (OUTCOME_TRACKING_MATERIAL_ARTIFACT, outcome_tracking_material),
        (TEXT_MATERIAL_ARTIFACT, text_material),
    ]
    return {artifact: _prepare_material_input(artifact, content) for artifact, content in materials}


def _prepare_material_input(artifact: str, content: str | None) -> dict[str, Any]:
    if content is None:
        return {
            "content": None,
            "budget": text_budget_record(
                artifact,
                None,
                status="not_generated",
                max_chars=DEFAULT_MATERIAL_MAX_CHARS,
                role="report_facing_material",
            ),
        }
    if len(content) <= DEFAULT_MATERIAL_MAX_CHARS:
        return {
            "content": content,
            "budget": text_budget_record(
                artifact,
                content,
                status="included",
                max_chars=DEFAULT_MATERIAL_MAX_CHARS,
                role="report_facing_material",
            ),
        }
    compressed = _compressed_material(artifact, content, max_chars=DEFAULT_MATERIAL_MAX_CHARS)
    record = text_budget_record(
        artifact,
        compressed,
        status="compressed",
        max_chars=DEFAULT_MATERIAL_MAX_CHARS,
        role="report_facing_material",
    )
    record["original_chars"] = len(content)
    record["omitted_chars"] = max(0, len(content) - len(compressed))
    record["compression_reason"] = "material_char_budget_exceeded"
    record["warnings"].append("material_compressed_for_codex_input")
    return {"content": compressed, "budget": record}


def _compressed_material(artifact: str, content: str, *, max_chars: int) -> str:
    header = "\n".join(
        [
            "```yaml",
            _yaml_block(
                {
                    "artifact": artifact,
                    "status": "compressed_for_codex_input",
                    "complete_artifact_path": artifact,
                    "original_chars": len(content),
                    "max_embedded_chars": max_chars,
                    "omission_reason": "material_char_budget_exceeded",
                    "selection_policy": "head_and_tail_excerpt",
                }
            ).rstrip(),
            "```",
            "",
            "## compressed_excerpt",
            "",
        ]
    )
    separator = "\n\n... omitted middle material; inspect the complete artifact path above ...\n\n"
    footer = "\n\n## omitted_material\n\n```yaml\nstatus: omitted_middle\nreason: material_char_budget_exceeded\n```\n"
    excerpt_budget = max(0, max_chars - len(header) - len(separator) - len(footer))
    head_chars = int(excerpt_budget * 0.7)
    tail_chars = max(0, excerpt_budget - head_chars)
    tail = content[-tail_chars:].lstrip() if tail_chars else ""
    compressed = header + content[:head_chars].rstrip() + separator + tail + footer
    if len(compressed) > max_chars:
        compressed = compressed[: max_chars - len(footer)].rstrip() + footer
    return compressed


def _yaml_list(values: list[str]) -> list[str]:
    if not values:
        return ["  []"]
    return [f"  - {value}" for value in values]


def _yaml_block(data: dict[str, Any]) -> str:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise PipelineError(
            "PyYAML is required to write YAML research context records.",
            stage=STAGE_NAME,
            exit_code=1,
        ) from exc

    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
