from __future__ import annotations

from pathlib import Path
from typing import Any

from halpha.pipeline import PipelineError, RunContext


STAGE_NAME = "build_research_context"
RESEARCH_CONTEXT_ARTIFACT = "analysis/research_context.md"
MARKET_MATERIAL_ARTIFACT = "analysis/market_material.md"
MARKET_SIGNAL_MATERIAL_ARTIFACT = "analysis/market_signal_material.md"
STRATEGY_EVALUATION_MATERIAL_ARTIFACT = "analysis/strategy_evaluation_material.md"
STRATEGY_EXPERIMENT_MATERIAL_ARTIFACT = "analysis/strategy_experiment_material.md"
DECISION_INTELLIGENCE_MATERIAL_ARTIFACT = "analysis/decision_intelligence_material.md"
EVENT_INTELLIGENCE_MATERIAL_ARTIFACT = "analysis/event_intelligence_material.md"
TEXT_MATERIAL_ARTIFACT = "analysis/text_material.md"


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
    market_signal_material = _read_material(
        run.analysis_dir / "market_signal_material.md",
        MARKET_SIGNAL_MATERIAL_ARTIFACT,
        enabled=_quant_enabled(config),
        producer_stage="build_market_signal_material",
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
    decision_intelligence_material = _read_material(
        run.analysis_dir / "decision_intelligence_material.md",
        DECISION_INTELLIGENCE_MATERIAL_ARTIFACT,
        enabled=_quant_enabled(config),
        producer_stage="build_decision_intelligence_material",
    )
    event_intelligence_material = _read_material(
        run.analysis_dir / "event_intelligence_material.md",
        EVENT_INTELLIGENCE_MATERIAL_ARTIFACT,
        enabled=bool(run.manifest.get("artifacts", {}).get("event_intelligence_material")),
        producer_stage="build_event_intelligence_material",
    )

    output_path = run.analysis_dir / "research_context.md"
    output_path.write_text(
        render_research_context(
            config,
            run=run,
            artifact_index=artifact_index,
            market_material=market_material,
            market_signal_material=market_signal_material,
            strategy_evaluation_material=strategy_evaluation_material,
            strategy_experiment_material=strategy_experiment_material,
            decision_intelligence_material=decision_intelligence_material,
            event_intelligence_material=event_intelligence_material,
            text_material=text_material,
        ),
        encoding="utf-8",
    )
    run.manifest["artifacts"]["research_context"] = RESEARCH_CONTEXT_ARTIFACT
    return [RESEARCH_CONTEXT_ARTIFACT]


def render_research_context(
    config: dict[str, Any],
    *,
    run: RunContext,
    artifact_index: dict[str, Any],
    market_material: str | None,
    market_signal_material: str | None,
    strategy_evaluation_material: str | None,
    strategy_experiment_material: str | None,
    decision_intelligence_material: str | None,
    event_intelligence_material: str | None,
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
    lines.extend(["", "## strategy_evaluation_material", ""])
    lines.extend(_embedded_material(STRATEGY_EVALUATION_MATERIAL_ARTIFACT, strategy_evaluation_material))
    lines.extend(["", "## strategy_experiment_material", ""])
    lines.extend(_embedded_material(STRATEGY_EXPERIMENT_MATERIAL_ARTIFACT, strategy_experiment_material))
    lines.extend(["", "## decision_intelligence_material", ""])
    lines.extend(_embedded_material(DECISION_INTELLIGENCE_MATERIAL_ARTIFACT, decision_intelligence_material))
    lines.extend(["", "## event_intelligence_material", ""])
    lines.extend(_embedded_material(EVENT_INTELLIGENCE_MATERIAL_ARTIFACT, event_intelligence_material))
    lines.extend(["", "## text_material", ""])
    lines.extend(_embedded_material(TEXT_MATERIAL_ARTIFACT, text_material))
    return "\n".join(lines)


def _artifact_index(run: RunContext) -> dict[str, Any]:
    artifacts = run.manifest.get("artifacts", {})
    index = {
        "raw_market": artifacts.get("raw_market"),
        "raw_text_events": artifacts.get("raw_text_events"),
        "market_signal_material": artifacts.get("market_signal_material"),
        "market_material": artifacts.get("market_material"),
        "text_material": artifacts.get("text_material"),
    }
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
        "financial_advice": False,
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
