from __future__ import annotations

import json
from pathlib import Path

import pytest

from halpha.codex.input_budget import DEFAULT_MATERIAL_MAX_CHARS
from halpha.config import load_config
from halpha.pipeline import run_pipeline
from halpha.storage import write_json


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_pipeline_generates_research_context_with_embedded_materials(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _write_market_raw,
            "collect_text_events": _write_text_raw,
            "run_codex_report": _skip_codex_report,
        },
    )

    assert result.succeeded is True
    assert result.failed_stage is None

    context = (result.run.analysis_dir / "research_context.md").read_text(encoding="utf-8")
    assert "artifact_type: research_context" in context
    assert "audience: codex_cli" in context
    assert "language_target: zh-CN" in context
    assert "raw_market: raw/market.json" in context
    assert "raw_text_events: raw/text_events.json" in context
    assert "data_quality_summary: analysis/data_quality_summary.json" in context
    assert "data_quality_material: analysis/data_quality_material.md" in context
    assert "feature_snapshots: analysis/feature_snapshots.json" in context
    assert "factor_states: analysis/factor_states.json" in context
    assert "multi_source_signals: analysis/multi_source_signals.json" in context
    assert "intelligence_fusion: analysis/intelligence_fusion.json" in context
    assert "intelligence_fusion_material: analysis/intelligence_fusion_material.md" in context
    assert "factor_signal_material: analysis/factor_signal_material.md" in context
    assert "market_material: analysis/market_material.md" in context
    assert "text_material: analysis/text_material.md" in context
    assert "event_intelligence_material: analysis/event_intelligence_material.md" in context
    assert "alert_decision_material: analysis/alert_decision_material.md" in context
    assert "text_event_records: analysis/text_event_records.json" in context
    assert "text_event_topics: analysis/text_event_topics.json" in context
    assert "text_event_signals: analysis/text_event_signals.json" in context
    assert "## source_policy" in context
    assert "allowed_sources_only: true" in context
    assert "fabricate_missing_sources: false" in context
    assert "financial_advice: false" in context
    assert "## codex_input_policy" in context
    assert "bounded_report_facing_material_only: true" in context
    assert "full_intermediate_json_embedded: false" in context
    assert "default_material_max_chars:" in context
    assert "## generation_constraints" in context
    assert "do_not_invent_prices_events_links_sources: true" in context
    assert "include_context_specific_risk_notes: true" in context
    assert "avoid_generic_disclaimers: true" in context
    assert "prefer_tables_for_comparable_data: true" in context
    assert "group_multi_symbol_sections_by_symbol: true" in context
    assert "title_is_h1_not_section: true" in context
    assert "synthesis_should_not_repeat_prior_sections: true" in context
    assert "quant_signal_requirements:" in context
    assert "include_signal_conclusions: true" in context
    assert "include_evidence_near_conclusions: true" in context
    assert "include_uncertainty_near_conclusions: true" in context
    assert "include_watch_points: true" in context
    assert "include_risk_notes: true" in context
    assert "do_not_calculate_signals_from_raw_ohlcv_history: true" in context
    assert "do_not_inspect_shared_ohlcv_storage: true" in context
    assert "factor_signal_requirements:" in context
    assert "include_when_factor_signal_material_exists: true" in context
    assert "use_halpha_factor_states_only: true" in context
    assert "use_halpha_multi_source_signal_states_only: true" in context
    assert "do_not_generate_factor_scores: true" in context
    assert "do_not_generate_signal_states: true" in context
    assert "event_intelligence_requirements:" in context
    assert "data_quality_requirements:" in context
    assert "use_halpha_quality_statuses_only: true" in context
    assert "do_not_generate_quality_checks: true" in context
    assert "do_not_inspect_omitted_tables: true" in context
    assert "alert_decision_requirements:" in context
    assert "use_halpha_alert_priorities_only: true" in context
    assert "do_not_generate_alert_priority: true" in context
    assert "use_halpha_event_categories_only: true" in context
    assert "do_not_generate_event_classification: true" in context
    assert "do_not_generate_event_impacts: true" in context
    assert "do_not_generate_price_forecasts: true" in context
    assert "do_not_generate_event_action_guidance: true" in context
    assert "may_explain_halpha_supported_research_guidance: true" in context
    assert "required_sections:" in context
    assert "- 核心结论" in context
    assert "- 决策框架" in context
    assert "- 标题" not in context
    assert "- market_overview" not in context
    assert '<embed path="analysis/market_material.md">' in context
    assert "artifact_type: analysis_market_material" in context
    assert '<embed path="analysis/text_material.md">' in context
    assert "artifact_type: analysis_text_material" in context
    assert '<embed path="analysis/event_intelligence_material.md">' in context
    assert '<embed path="analysis/alert_decision_material.md">' in context
    assert '<embed path="analysis/data_quality_material.md">' in context
    assert '<embed path="analysis/factor_signal_material.md">' in context
    assert '<embed path="analysis/intelligence_fusion_material.md">' in context
    assert "artifact_type: analysis_event_intelligence_material" in context
    assert "artifact_type: analysis_alert_decision_material" in context
    assert "artifact_type: analysis_data_quality_material" in context
    assert "artifact_type: analysis_factor_signal_material" in context
    assert "artifact_type: analysis_intelligence_fusion_material" in context
    assert "codex_may_generate_quality_checks: false" in context
    assert "codex_may_generate_factor_scores: false" in context
    assert "codex_may_generate_signal_states: false" in context
    assert "codex_may_generate_fusion_states: false" in context
    assert "full_reusable_history_embedded: false" in context
    assert "full_feature_snapshots_json_embedded: false" in context
    assert "full_factor_states_json_embedded: false" in context
    assert "full_multi_source_signals_json_embedded: false" in context
    assert "full_intelligence_fusion_json_embedded: false" in context
    assert "full_catalog_embedded: false" in context
    assert "full_run_index_embedded: false" in context
    assert "codex_may_generate_alert_priority: false" in context
    assert "codex_may_generate_event_categories: false" in context
    assert "codex_may_generate_price_forecasts: false" in context
    assert "content_text: Source-provided event text." in context

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifacts"]["event_intelligence_material"] == "analysis/event_intelligence_material.md"
    assert manifest["artifacts"]["data_quality_material"] == "analysis/data_quality_material.md"
    assert manifest["artifacts"]["factor_signal_material"] == "analysis/factor_signal_material.md"
    assert manifest["artifacts"]["intelligence_fusion_material"] == "analysis/intelligence_fusion_material.md"
    assert manifest["artifacts"]["research_context"] == "analysis/research_context.md"
    assert manifest["codex_input"]["policy"]["bounded_report_facing_material_only"] is True
    assert manifest["codex_input"]["policy"]["full_intermediate_json_embedded"] is False
    assert manifest["codex_input"]["research_context"]["artifact"] == "analysis/research_context.md"
    assert manifest["codex_input"]["research_context"]["status"] == "included"
    assert manifest["codex_input"]["research_context"]["chars"] == len(context)
    assert manifest["codex_input"]["research_context"]["over_budget"] is False
    material_records = {
        record["artifact"]: record for record in manifest["codex_input"]["materials"]
    }
    assert material_records["analysis/alert_decision_material.md"]["status"] == "included"
    assert material_records["analysis/event_intelligence_material.md"]["status"] == "included"
    assert material_records["analysis/data_quality_material.md"]["status"] == "included"
    assert material_records["analysis/factor_signal_material.md"]["status"] == "included"
    assert material_records["analysis/intelligence_fusion_material.md"]["status"] == "included"
    assert material_records["analysis/text_material.md"]["status"] == "included"
    research_stage = _stage(manifest, "build_research_context")
    codex_context_stage = _stage(manifest, "build_codex_context")
    report_stage = _stage(manifest, "run_codex_report")
    assert research_stage["status"] == "succeeded"
    assert research_stage["artifacts"] == ["analysis/research_context.md"]
    assert codex_context_stage["status"] == "succeeded"
    assert report_stage["status"] == "succeeded"


def test_research_context_marks_disabled_text_material_as_not_generated(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, text_enabled=False)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _write_market_raw,
            "run_codex_report": _skip_codex_report,
        },
    )

    assert result.succeeded is True
    assert result.failed_stage is None
    assert not (result.run.analysis_dir / "text_material.md").exists()

    context = (result.run.analysis_dir / "research_context.md").read_text(encoding="utf-8")
    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert "market_material: analysis/market_material.md" in context
    assert "data_quality_material: analysis/data_quality_material.md" in context
    assert "text_material: null" in context
    assert "artifact: analysis/text_material.md" in context
    assert "status: not_generated" in context
    material_records = {
        record["artifact"]: record for record in manifest["codex_input"]["materials"]
    }
    assert material_records["analysis/text_material.md"]["status"] == "not_generated"
    assert material_records["analysis/text_material.md"]["warnings"] == []


def test_research_context_compresses_over_budget_material_for_codex_input(
    tmp_path: Path,
) -> None:
    config_path = _write_config(tmp_path, text_enabled=False)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="generate_report",
        stage_handlers={
            "collect_market_data": _write_market_raw,
            "collect_text_events": _noop_stage,
            "build_analysis_materials": _write_large_market_material,
            "run_codex_report": _skip_codex_report,
        },
    )

    assert result.succeeded is True
    context = (result.run.analysis_dir / "research_context.md").read_text(encoding="utf-8")
    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    material_records = {
        record["artifact"]: record for record in manifest["codex_input"]["materials"]
    }
    market_record = material_records["analysis/market_material.md"]
    quality_record = material_records["analysis/data_quality_material.md"]

    assert "status: compressed_for_codex_input" in context
    assert "HIGH_SIGNAL_BEGIN" in context
    assert "HIGH_SIGNAL_END" in context
    assert "QUALITY_SIGNAL_BEGIN" in context
    assert "QUALITY_SIGNAL_END" in context
    assert "material_char_budget_exceeded" in context
    assert market_record["status"] == "compressed"
    assert market_record["chars"] <= DEFAULT_MATERIAL_MAX_CHARS
    assert market_record["original_chars"] > market_record["chars"]
    assert market_record["omitted_chars"] > 0
    assert "material_compressed_for_codex_input" in market_record["warnings"]
    assert quality_record["status"] == "compressed"
    assert quality_record["chars"] <= DEFAULT_MATERIAL_MAX_CHARS
    assert quality_record["original_chars"] > quality_record["chars"]
    assert quality_record["omitted_chars"] > 0
    assert "material_compressed_for_codex_input" in quality_record["warnings"]
    assert manifest["codex_input"]["research_context"]["over_budget"] is False


def test_research_context_embeds_market_signal_material_when_quant_enabled(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, quant_enabled=True, text_enabled=False)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _write_market_raw,
            "collect_text_events": _noop_stage,
            "sync_ohlcv": _noop_stage,
            "build_market_data_views": _write_market_data_views,
            "evaluate_quant_strategies": _write_quant_strategy_runs,
            "evaluate_strategy_evaluation": _write_strategy_evaluation_summary_and_material,
            "build_strategy_experiment_material": _write_strategy_experiment_material,
            "run_codex_report": _skip_codex_report,
        },
    )

    assert result.succeeded is True
    context = (result.run.analysis_dir / "research_context.md").read_text(encoding="utf-8")
    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert "market_data_views: raw/market_data_views.json" in context
    assert "strategy_evaluation_summary: analysis/strategy_evaluation_summary.json" in context
    assert "strategy_evaluation_material: analysis/strategy_evaluation_material.md" in context
    assert "strategy_experiment: analysis/strategy_experiment.json" in context
    assert "strategy_effectiveness_gates: analysis/strategy_effectiveness_gates.json" in context
    assert "strategy_experiment_material: analysis/strategy_experiment_material.md" in context
    assert "market_signals: analysis/market_signals.json" in context
    assert "market_signal_material: analysis/market_signal_material.md" in context
    assert "market_regime_assessment: analysis/market_regime_assessment.json" in context
    assert "risk_assessment: analysis/risk_assessment.json" in context
    assert "decision_recommendations: analysis/decision_recommendations.json" in context
    assert "watch_triggers: analysis/watch_triggers.json" in context
    assert "decision_intelligence_delta: analysis/decision_intelligence_delta.json" in context
    assert "decision_intelligence_material: analysis/decision_intelligence_material.md" in context
    assert '<embed path="analysis/market_signal_material.md">' in context
    assert "artifact_type: analysis_market_signal_material" in context
    assert '<embed path="analysis/strategy_evaluation_material.md">' in context
    assert "artifact_type: analysis_strategy_evaluation_material" in context
    assert '<embed path="analysis/strategy_experiment_material.md">' in context
    assert "artifact_type: analysis_strategy_experiment_material" in context
    assert '<embed path="analysis/decision_intelligence_material.md">' in context
    assert "artifact_type: analysis_decision_intelligence_material" in context
    assert "research_decision_support_only: true" in context
    assert "decision_intelligence_requirements:" in context
    assert "use_decision_material_for_decision_language: true" in context
    assert "use_quant_material_as_upstream_evidence: true" in context
    assert "do_not_invent_action_levels: true" in context
    assert "do_not_upgrade_low_confidence_or_unsupported_material: true" in context
    assert "strategy_evaluation_requirements:" in context
    assert "include_cost_assumptions: true" in context
    assert "include_baseline_comparison: true" in context
    assert "include_sample_limits: true" in context
    assert "include_reliability_and_uncertainty: true" in context
    assert "do_not_generate_metrics: true" in context
    assert "do_not_upgrade_weak_or_unstable_evidence: true" in context
    assert "strategy_experiment_gate_requirements:" in context
    assert "use_halpha_gate_statuses_only: true" in context
    assert "identify_effective_watchlisted_rejected_and_insufficient_evidence: true" in context
    assert "do_not_generate_gate_outcomes: true" in context
    assert "raw_ohlcv_history_embedded: false" in context
    assert "include_signal_conclusions: true" in context
    assert "include_evidence_near_conclusions: true" in context
    assert "include_uncertainty_near_conclusions: true" in context
    assert "record_type: market_signal" in context
    assert "signal_id: market_signal:tsmom_vol_scaled:binance:BTCUSDT:1d:2026-06-03T00:00:00Z" in context
    assert "open_time:" not in context
    assert manifest["artifacts"]["market_signal_material"] == "analysis/market_signal_material.md"
    assert manifest["artifacts"]["strategy_evaluation_summary"] == "analysis/strategy_evaluation_summary.json"
    assert manifest["artifacts"]["strategy_evaluation_material"] == "analysis/strategy_evaluation_material.md"
    assert manifest["artifacts"]["strategy_experiment_material"] == "analysis/strategy_experiment_material.md"
    assert manifest["artifacts"]["decision_intelligence_material"] == "analysis/decision_intelligence_material.md"
    assert manifest["artifacts"]["research_context"] == "analysis/research_context.md"


def test_research_context_embeds_onchain_flow_material_when_enabled(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, text_enabled=False, onchain_enabled=True)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="generate_report",
        stage_handlers={
            "collect_market_data": _write_market_raw,
            "collect_text_events": _noop_stage,
            "collect_onchain_flow_data": _noop_stage,
            "sync_onchain_flow_history": _noop_stage,
            "build_onchain_flow_views": _noop_stage,
            "build_onchain_flow_context": _write_onchain_flow_context,
            "run_codex_report": _skip_codex_report,
        },
    )

    assert result.succeeded is True
    context = (result.run.analysis_dir / "research_context.md").read_text(encoding="utf-8")
    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert "onchain_flow_context: analysis/onchain_flow_context.json" in context
    assert "onchain_flow_material: analysis/onchain_flow_material.md" in context
    assert '<embed path="analysis/onchain_flow_material.md">' in context
    assert "artifact_type: analysis_onchain_flow_material" in context
    assert "onchain_flow_requirements:" in context
    assert "include_when_onchain_flow_material_exists: true" in context
    assert "do_not_generate_onchain_records: true" in context
    assert "do_not_generate_flow_states: true" in context
    assert "do_not_generate_address_labels: true" in context
    assert "full_raw_onchain_flow_artifacts_embedded: false" in context
    assert "full_reusable_onchain_flow_history_embedded: false" in context
    assert "full_onchain_flow_views_embedded: false" in context
    assert "full_onchain_flow_context_json_embedded: false" in context
    assert "PRIVATE_RAW_SENTINEL_SHOULD_NOT_APPEAR" not in context
    assert manifest["artifacts"]["onchain_flow_material"] == "analysis/onchain_flow_material.md"
    assert manifest["codex_input"]["policy"]["full_raw_onchain_flow_artifacts_embedded"] is False
    assert manifest["codex_input"]["policy"]["full_reusable_onchain_flow_history_embedded"] is False
    assert manifest["codex_input"]["policy"]["full_onchain_flow_views_embedded"] is False
    assert manifest["codex_input"]["policy"]["full_onchain_flow_context_json_embedded"] is False
    material_records = {
        record["artifact"]: record for record in manifest["codex_input"]["materials"]
    }
    assert material_records["analysis/onchain_flow_material.md"]["status"] == "included"


def test_research_context_fails_when_decision_material_is_missing_for_quant_enabled(
    tmp_path: Path,
) -> None:
    config_path = _write_config(tmp_path, quant_enabled=True, text_enabled=False)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _write_market_raw,
            "collect_text_events": _noop_stage,
            "sync_ohlcv": _noop_stage,
            "build_market_data_views": _write_market_data_views,
            "evaluate_quant_strategies": _write_quant_strategy_runs,
            "evaluate_strategy_evaluation": _write_strategy_evaluation_summary_and_material,
            "build_decision_intelligence_material": _noop_stage,
        },
    )

    assert result.succeeded is False
    assert result.failed_stage == "build_research_context"
    assert result.reason == (
        "analysis/decision_intelligence_material.md was not found; "
        "build_decision_intelligence_material must run first."
    )
    assert not (result.run.analysis_dir / "research_context.md").exists()

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert _stage(manifest, "build_research_context")["status"] == "failed"
    assert manifest["errors"] == [
        {
            "stage": "build_research_context",
            "message": (
                "analysis/decision_intelligence_material.md was not found; "
                "build_decision_intelligence_material must run first."
            ),
        }
    ]


def test_research_context_fails_when_enabled_material_is_missing(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _write_market_raw,
            "collect_text_events": _write_text_raw,
            "build_analysis_materials": _skip_analysis_materials,
        },
    )

    assert result.succeeded is False
    assert result.failed_stage == "build_research_context"
    assert result.reason == "analysis/market_material.md was not found; build_analysis_materials must run first."
    assert not (result.run.analysis_dir / "research_context.md").exists()

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert _stage(manifest, "build_research_context")["status"] == "failed"
    assert manifest["errors"] == [
        {
            "stage": "build_research_context",
            "message": "analysis/market_material.md was not found; build_analysis_materials must run first.",
        }
    ]


def _write_config(
    tmp_path: Path,
    *,
    text_enabled: bool = True,
    quant_enabled: bool = False,
    onchain_enabled: bool = False,
) -> Path:
    config_path = tmp_path / "config.yaml"
    text_block = (
        """
text:
  enabled: true
  max_items: 1
  sources:
    - name: coindesk
      type: rss
      url: https://www.coindesk.com/arc/outboundfeeds/rss/
"""
        if text_enabled
        else """
text:
  enabled: false
"""
    )
    ohlcv_block = (
        """
  ohlcv:
    storage_dir: data/market/ohlcv
    timeframes:
      - 1d
    lookback:
      1d: 3
"""
        if quant_enabled
        else ""
    )
    quant_block = (
        """
quant:
  enabled: true
  engine: vectorbt
  strategies:
    - name: tsmom_vol_scaled
"""
        if quant_enabled
        else ""
    )
    onchain_block = (
        """
onchain_flow:
  enabled: true
  source: public_aggregate
  data_classes:
    - stablecoin_supply
    - chain_activity
    - network_congestion
    - exchange_flow_availability
  assets:
    - ALL_STABLECOINS
    - BTC
  chains:
    - all
    - bitcoin
  lookback_days: 7
"""
        if onchain_enabled
        else ""
    )
    config_path.write_text(
        f"""
run:
  output_dir: runs
  timezone: Asia/Shanghai
market:
  enabled: true
  source: binance
  symbols:
    - BTCUSDT
{ohlcv_block.rstrip()}
{text_block.rstrip()}
{onchain_block.rstrip()}
{quant_block.rstrip()}
report:
  title: Daily Market Brief
  language: zh-CN
codex:
  enabled: true
  command: codex
  args:
    - exec
    - --sandbox
    - read-only
    - "-"
  timeout_seconds: 300
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _write_market_raw(config, run) -> list[str]:
    write_json(
        run.raw_dir / "market.json",
        {
            "schema_version": 1,
            "artifact_type": "market_raw",
            "collector": "market",
            "collection_method": "public_http",
            "source": {
                "name": "binance",
                "url": "https://data-api.binance.vision",
            },
            "collected_at": "2026-06-05T00:30:00Z",
            "items": [
                {
                    "id": "market:binance:BTCUSDT:2026-06-05T00:30:00Z",
                    "symbol": "BTCUSDT",
                    "as_of": "2026-06-05T00:30:00Z",
                    "metrics": {
                        "price": "68000.00",
                        "change_24h_pct": "1.25",
                        "volume_24h": "123.45",
                        "quote_volume_24h": "8394600.00",
                    },
                    "source": {
                        "name": "binance",
                        "url": "https://data-api.binance.vision",
                    },
                }
            ],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["raw_market"] = "raw/market.json"
    run.manifest["counts"]["market_items"] = 1
    return ["raw/market.json"]


def _write_text_raw(config, run) -> list[str]:
    write_json(
        run.raw_dir / "text_events.json",
        {
            "schema_version": 1,
            "artifact_type": "text_events_raw",
            "collector": "text",
            "collection_method": "rss",
            "collected_at": "2026-06-05T00:31:00Z",
            "sources": [
                {
                    "name": "coindesk",
                    "type": "rss",
                    "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
                }
            ],
            "items": [
                {
                    "id": "text:coindesk:event-1",
                    "type": "rss_item",
                    "title": "Bitcoin market event",
                    "published_at": "2026-06-05T00:30:00Z",
                    "source": {
                        "name": "coindesk",
                        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
                    },
                    "link": "https://example.com/bitcoin-event",
                    "content_text": "Source-provided event text.",
                    "language": None,
                }
            ],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["raw_text_events"] = "raw/text_events.json"
    run.manifest["counts"]["text_event_items"] = 1
    return ["raw/text_events.json"]


def _write_market_data_views(config, run) -> list[str]:
    write_json(
        run.raw_dir / "market_data_views.json",
        {
            "schema_version": 1,
            "artifact_type": "market_data_views",
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["data/market/metadata/ohlcv_sync_state.json"],
            "views": [
                {
                    "view_id": "ohlcv_view:binance:BTCUSDT:1d:2026-06-03T00:00:00Z",
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "requested_lookback": 3,
                    "input_window_start": "2026-06-01T00:00:00Z",
                    "input_window_end": "2026-06-03T00:00:00Z",
                    "latest_candle_time": "2026-06-03T00:00:00Z",
                    "row_count": 3,
                    "storage_ref": "data/market/ohlcv/source=binance/symbol=BTCUSDT/timeframe=1d",
                    "included_columns": ["open_time", "open", "high", "low", "close", "volume"],
                    "insufficient_data": False,
                    "warnings": [],
                }
            ],
        },
    )
    run.manifest["artifacts"]["market_data_views"] = "raw/market_data_views.json"
    run.manifest["counts"]["market_data_views"] = 1
    run.manifest["counts"]["market_data_views_insufficient_data"] = 0
    return ["raw/market_data_views.json"]


def _write_quant_strategy_runs(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "quant_strategy_runs.json",
        {
            "schema_version": 1,
            "artifact_type": "quant_strategy_runs",
            "created_at": "2026-06-05T00:00:00Z",
            "engine": {"name": "vectorbt", "version": "0.28.0", "objects_exposed": False},
            "source_artifacts": ["raw/market_data_views.json"],
            "runs": [
                {
                    "strategy_run_id": (
                        "quant_strategy_run:tsmom_vol_scaled:binance:BTCUSDT:1d:2026-06-03T00:00:00Z"
                    ),
                    "status": "succeeded",
                    "strategy_name": "tsmom_vol_scaled",
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "input_view_id": "ohlcv_view:binance:BTCUSDT:1d:2026-06-03T00:00:00Z",
                    "input_window_start": "2026-06-01T00:00:00Z",
                    "input_window_end": "2026-06-03T00:00:00Z",
                    "latest_candle_time": "2026-06-03T00:00:00Z",
                    "data_quality": {
                        "row_count": 3,
                        "requested_lookback": 3,
                        "minimum_required_rows": 3,
                        "sufficient_data": True,
                        "warnings": [],
                    },
                    "indicators": {"latest_close": 106.0, "row_count": 3},
                    "signals": {},
                    "backtest_diagnostic": {"enabled": False, "status": "disabled"},
                    "parameter_diagnostic": {"enabled": False, "status": "disabled"},
                    "assessment": {
                        "direction": "bullish",
                        "strength": "medium",
                        "confidence": "medium",
                        "evidence": ["return_window_pct is 6.0% over the configured return window."],
                        "uncertainty": [
                            "Strategy uses OHLCV close prices only and excludes text events."
                        ],
                    },
                    "warnings": [],
                    "error": None,
                    "source_artifacts": ["raw/market_data_views.json"],
                    "created_at": "2026-06-05T00:00:00Z",
                }
            ],
        },
    )
    run.manifest["artifacts"]["quant_strategy_runs"] = "analysis/quant_strategy_runs.json"
    run.manifest["counts"]["quant_strategy_runs"] = 1
    return ["analysis/quant_strategy_runs.json"]


def _write_strategy_evaluation_summary_and_material(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "strategy_evaluation_summary.json",
        {
            "schema_version": 1,
            "artifact_type": "strategy_evaluation_summary",
            "records": [
                {
                    "evaluation_id": "strategy_evaluation:tsmom_vol_scaled:binance:BTCUSDT:1d:2026-06-03T00:00:00Z",
                    "status": "succeeded",
                    "strategy_name": "tsmom_vol_scaled",
                    "input_view_id": "ohlcv_view:binance:BTCUSDT:1d:2026-06-03T00:00:00Z",
                    "single_window": {"status": "succeeded"},
                }
            ],
        },
    )
    (run.analysis_dir / "strategy_evaluation_material.md").write_text(
        "\n".join(
            [
                "---",
                "artifact_type: analysis_strategy_evaluation_material",
                "schema_version: 1",
                "---",
                "",
                "# strategy_evaluation_material",
                "",
                "record_type: strategy_evaluation",
                "strategy_name: tsmom_vol_scaled",
                "status: succeeded",
            ]
        ),
        encoding="utf-8",
    )
    run.manifest["artifacts"]["strategy_evaluation_summary"] = "analysis/strategy_evaluation_summary.json"
    run.manifest["artifacts"]["strategy_evaluation_material"] = "analysis/strategy_evaluation_material.md"
    run.manifest["counts"]["strategy_evaluation_records"] = 1
    run.manifest["counts"]["strategy_evaluation_material_records"] = 1
    return ["analysis/strategy_evaluation_summary.json", "analysis/strategy_evaluation_material.md"]


def _write_strategy_experiment_material(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "strategy_experiment.json",
        {
            "schema_version": 1,
            "artifact_type": "strategy_experiment",
            "created_at": "2026-06-05T00:00:00Z",
            "experiment_id": "test_strategy_experiment",
            "source_artifacts": ["analysis/strategy_benchmark_suite.json"],
            "coverage": {"strategy_candidates": 1, "evaluations": 1},
            "candidates": [],
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        run.analysis_dir / "strategy_effectiveness_gates.json",
        {
            "schema_version": 1,
            "artifact_type": "strategy_effectiveness_gates",
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["analysis/strategy_experiment.json"],
            "coverage": {
                "strategy_candidates": 1,
                "effective": 1,
                "watchlisted": 0,
                "rejected": 0,
                "insufficient_evidence": 0,
            },
            "records": [],
            "warnings": [],
            "errors": [],
        },
    )
    (run.analysis_dir / "strategy_experiment_material.md").write_text(
        "\n".join(
            [
                "---",
                "artifact_type: analysis_strategy_experiment_material",
                "schema_version: 1",
                "---",
                "",
                "# strategy_experiment_material",
                "",
                "record_type: strategy_effectiveness_gate",
                "strategy_name: tsmom_vol_scaled",
                "status: effective",
            ]
        ),
        encoding="utf-8",
    )
    run.manifest["artifacts"]["strategy_experiment"] = "analysis/strategy_experiment.json"
    run.manifest["artifacts"]["strategy_effectiveness_gates"] = "analysis/strategy_effectiveness_gates.json"
    run.manifest["artifacts"]["strategy_experiment_material"] = "analysis/strategy_experiment_material.md"
    run.manifest["counts"]["strategy_experiment_material_records"] = 1
    return [
        "analysis/strategy_experiment.json",
        "analysis/strategy_effectiveness_gates.json",
        "analysis/strategy_experiment_material.md",
    ]


def _write_onchain_flow_context(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "onchain_flow_context.json",
        {
            "schema_version": 1,
            "artifact_type": "onchain_flow_context",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "status": "warning",
            "records": [
                {
                    "context_id": (
                        "onchain_flow_context:stablecoin_liquidity:defillama_stablecoins:"
                        "ALL_STABLECOINS:all:2026-06-05T00:00:00Z"
                    ),
                    "context_type": "stablecoin_liquidity",
                    "data_class": "stablecoin_supply",
                    "source": "defillama_stablecoins",
                    "asset": "ALL_STABLECOINS",
                    "chain": "all",
                    "as_of": "2026-06-05T00:00:00Z",
                    "status": "succeeded",
                    "state": "sharp_stablecoin_supply_contraction",
                    "severity": "high",
                    "confidence": "medium",
                    "source_availability": "succeeded",
                    "metrics": {"stablecoin_supply_change_pct": -0.1},
                    "thresholds": {"sharp_supply_contraction_change_pct": -0.05},
                    "evidence": [{"source_artifact": "raw/onchain_flow_views.json", "value": -0.1}],
                    "uncertainty": ["stablecoin supply is liquidity context, not a price forecast."],
                    "warnings": [],
                    "errors": [],
                    "source_artifacts": ["analysis/onchain_flow_context.json", "raw/onchain_flow_views.json"],
                    "raw_payload": "PRIVATE_RAW_SENTINEL_SHOULD_NOT_APPEAR",
                }
            ],
            "counts": {"records": 1},
            "warnings": [],
            "errors": [],
            "source_artifacts": ["raw/onchain_flow_views.json", "raw/onchain_flow.json"],
        },
    )
    run.manifest["artifacts"]["onchain_flow_context"] = "analysis/onchain_flow_context.json"
    return ["analysis/onchain_flow_context.json"]


def _skip_analysis_materials(config, run) -> list[str]:
    return []


def _write_large_market_material(config, run) -> list[str]:
    market_content = "\n".join(
        [
            "---",
            "artifact_type: analysis_market_material",
            "schema_version: 1",
            "---",
            "",
            "# market_material",
            "",
            "HIGH_SIGNAL_BEGIN",
            *["low priority filler material" for _ in range(1400)],
            "HIGH_SIGNAL_END",
        ]
    )
    quality_content = "\n".join(
        [
            "---",
            "artifact_type: analysis_data_quality_material",
            "schema_version: 1",
            "---",
            "",
            "# data_quality_material",
            "",
            "QUALITY_SIGNAL_BEGIN",
            *["low priority quality filler material" for _ in range(1400)],
            "QUALITY_SIGNAL_END",
        ]
    )
    (run.analysis_dir / "market_material.md").write_text(market_content, encoding="utf-8")
    (run.analysis_dir / "data_quality_material.md").write_text(quality_content, encoding="utf-8")
    run.manifest["artifacts"]["market_material"] = "analysis/market_material.md"
    run.manifest["artifacts"]["data_quality_material"] = "analysis/data_quality_material.md"
    return ["analysis/data_quality_material.md", "analysis/market_material.md"]


def _noop_stage(config, run) -> list[str]:
    return []


def _skip_codex_report(config, run) -> list[str]:
    return []


def _stage(manifest: dict, name: str) -> dict:
    for stage in manifest["stages"]:
        if stage["name"] == name:
            return stage
        for task in stage.get("tasks", []):
            if task["name"] == name:
                return task
    raise AssertionError(f"stage or task {name} not found")
