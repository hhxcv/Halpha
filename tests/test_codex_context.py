from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from halpha.config import load_config
from halpha.pipeline import run_pipeline
from halpha.storage import write_json


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_pipeline_generates_codex_context_and_prompt_artifacts(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    _write_outcome_history_state(tmp_path)
    _write_full_outcome_history_with_sentinel(tmp_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        now=datetime(2026, 6, 5, 0, 30, tzinfo=timezone.utc),
        stage_handlers={
            "collect_market_data": _write_market_raw,
            "collect_text_events": _write_text_raw,
            "run_codex_report": _skip_codex_report,
        },
    )

    assert result.succeeded is True
    assert result.failed_stage is None

    context = (result.run.codex_context_dir / "context.md").read_text(encoding="utf-8")
    research_context = (result.run.analysis_dir / "research_context.md").read_text(encoding="utf-8")
    assert "# codex_context" in context
    assert "raw_market: raw/market.json" in context
    assert "raw_text_events: raw/text_events.json" in context
    assert "data_quality_summary: analysis/data_quality_summary.json" in context
    assert "data_quality_material: analysis/data_quality_material.md" in context
    assert "outcome_tracking_material: analysis/outcome_tracking_material.md" in context
    assert "feature_snapshots: analysis/feature_snapshots.json" in context
    assert "factor_states: analysis/factor_states.json" in context
    assert "multi_source_signals: analysis/multi_source_signals.json" in context
    assert "intelligence_fusion: analysis/intelligence_fusion.json" in context
    assert "intelligence_fusion_material: analysis/intelligence_fusion_material.md" in context
    assert "user_state_context: analysis/user_state_context.json" in context
    assert "personalized_risk_constraints: analysis/personalized_risk_constraints.json" in context
    assert "personalized_risk_material: analysis/personalized_risk_material.md" in context
    assert "factor_signal_material: analysis/factor_signal_material.md" in context
    assert "market_material: analysis/market_material.md" in context
    assert "text_material: analysis/text_material.md" in context
    assert "event_intelligence_material: analysis/event_intelligence_material.md" in context
    assert "alert_decision_material: analysis/alert_decision_material.md" in context
    assert "text_event_records: analysis/text_event_records.json" in context
    assert "text_event_topics: analysis/text_event_topics.json" in context
    assert "text_event_signals: analysis/text_event_signals.json" in context
    assert "research_context: analysis/research_context.md" in context
    assert "codex_context: codex_context/context.md" in context
    assert "codex_prompt: codex_context/prompt.md" in context
    assert '<embed path="analysis/research_context.md">' in context
    assert "artifact_type: research_context" in context
    assert "artifact_type: analysis_data_quality_material" in context
    assert "artifact_type: analysis_outcome_tracking_material" in context
    assert "artifact_type: analysis_factor_signal_material" in context
    assert "artifact_type: analysis_intelligence_fusion_material" in context
    assert "artifact_type: analysis_personalized_risk_material" in context
    assert "outcome_tracking_material: analysis/outcome_tracking_material.md" in research_context
    assert "artifact_type: analysis_outcome_tracking_material" in research_context
    assert "factor_signal_material: analysis/factor_signal_material.md" in research_context
    assert "intelligence_fusion_material: analysis/intelligence_fusion_material.md" in research_context
    assert "personalized_risk_material: analysis/personalized_risk_material.md" in research_context
    assert "artifact_type: analysis_factor_signal_material" in research_context
    assert "artifact_type: analysis_intelligence_fusion_material" in research_context
    assert "artifact_type: analysis_personalized_risk_material" in research_context
    assert "codex_may_generate_quality_checks: false" in context
    assert "codex_may_generate_factor_scores: false" in context
    assert "codex_may_generate_signal_states: false" in context
    assert "codex_may_generate_fusion_states: false" in context
    assert "codex_may_generate_user_state: false" in context
    assert "codex_may_generate_allocations: false" in context
    assert "full_reusable_history_embedded: false" in context
    assert "full_user_state_context_json_embedded: false" in context
    assert "full_personalized_risk_constraints_json_embedded: false" in context
    assert "full_catalog_embedded: false" in context
    assert "full_run_index_embedded: false" in context
    assert "full_outcome_history_embedded: false" in context
    assert "CREATE TABLE" not in context
    assert "stable_event_key:" not in context
    assert "FULL_OUTCOME_HISTORY_SHOULD_NOT_APPEAR" not in context
    assert "content_text: Source-provided event text." in context

    prompt = (result.run.codex_context_dir / "prompt.md").read_text(encoding="utf-8")
    assert "Generate a Simplified Chinese Markdown market intelligence report" in prompt
    assert "Use Chinese section headings only." in prompt
    assert "Do not invent prices, events, links, sources, or certainty." in prompt
    assert "Preserve source awareness." in prompt
    assert "Distinguish facts, assumptions, uncertainties, and judgment." in prompt
    assert "Use cautious language for market interpretation." in prompt
    assert "The first line must be a single H1 title" in prompt
    assert "# Daily Market Brief（生成时间：2026-06-05 08:30:00 Asia/Shanghai (UTC+08:00)）" in prompt
    assert "Do not create a separate title section." in prompt
    assert "Do not calculate or rewrite the generation time" in prompt
    assert "Avoid filler, generic disclaimers" in prompt
    assert "Use Markdown tables for market data" in prompt
    assert "other comparable non-strategy data" in prompt
    assert "Halpha inserts the complete quant strategy run table after Codex output" in prompt
    assert "do not recreate the full strategy run table" in prompt
    assert "When event intelligence material is present" in prompt
    assert "When alert decision material is present" in prompt
    assert "Use only Halpha-generated event categories" in prompt
    assert "Use only Halpha-generated alert priority" in prompt
    assert "Do not generate or revise event classifications" in prompt
    assert "Event intelligence material rules:" in prompt
    assert "Alert decision material rules:" in prompt
    assert "Data quality material rules:" in prompt
    assert "Outcome tracking material rules:" in prompt
    assert "Factor signal material rules:" in prompt
    assert "Intelligence fusion material rules:" in prompt
    assert "Personalized risk material rules:" in prompt
    assert "When factor/signal material is present" in prompt
    assert "When intelligence fusion material is present" in prompt
    assert "When personalized risk material is present" in prompt
    assert "Do not generate or revise feature records" in prompt
    assert "Do not infer hidden user state" in prompt
    assert "Do not generate or revise personalized constraints" in prompt
    assert "When data quality material is present" in prompt
    assert "Do not generate or revise data-quality checks" in prompt
    assert "Do not create outcome labels" in prompt
    assert "infer omitted outcome stores" in prompt
    assert "Treat store references as references only" in prompt
    assert "P0, P1, P2, P3, and no-alert" in prompt
    assert "Do not generate or revise alert priorities" in prompt
    assert "event-quant confluence or conflict" in prompt
    assert "do not recreate it from raw text" in prompt
    assert "organize each main section with symbol-level subheadings" in prompt
    assert "Do not include fixed boilerplate" in prompt
    assert "Write as an analyst memo, not a material digest" in prompt
    assert "Start with a decision-useful thesis" in prompt
    assert "Do not default to neutral to avoid judgment" in prompt
    assert "research guidance, watch conditions, review steps, and invalidation conditions" in prompt
    assert "Halpha may append deterministic evidence appendices" in prompt
    assert "core report prerequisites" in prompt
    assert "report_readiness passed" in prompt
    assert "not financial advice" not in prompt
    assert "Do not modify repository files" in prompt
    assert "<context>" in prompt
    assert "# codex_context" in prompt
    assert "artifact_type: research_context" in prompt
    assert "artifact_type: analysis_event_intelligence_material" in prompt
    assert "artifact_type: analysis_alert_decision_material" in prompt
    assert "artifact_type: analysis_data_quality_material" in prompt
    assert "artifact_type: analysis_outcome_tracking_material" in prompt
    assert "artifact_type: analysis_factor_signal_material" in prompt
    assert "artifact_type: analysis_intelligence_fusion_material" in prompt
    assert "artifact_type: analysis_personalized_risk_material" in prompt
    assert "codex_may_generate_event_categories: false" in prompt
    assert "codex_may_generate_alert_priority: false" in prompt
    assert "codex_may_generate_quality_checks: false" in prompt
    assert "codex_may_generate_outcome_labels: false" in prompt
    assert "codex_may_generate_factor_scores: false" in prompt
    assert "codex_may_generate_signal_states: false" in prompt
    assert "codex_may_generate_fusion_states: false" in prompt
    assert "codex_may_generate_user_state: false" in prompt
    assert "codex_may_generate_allocations: false" in prompt
    assert "codex_may_generate_price_forecasts: false" in prompt
    assert "- 核心结论" in prompt
    assert "- 决策框架" in prompt
    assert "- 风险提示" in prompt
    assert "- 标题" not in prompt
    assert "- Market Overview" not in prompt

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifacts"]["codex_context"] == "codex_context/context.md"
    assert manifest["artifacts"]["codex_prompt"] == "codex_context/prompt.md"
    assert manifest["artifacts"]["data_quality_material"] == "analysis/data_quality_material.md"
    assert manifest["artifacts"]["outcome_tracking_material"] == "analysis/outcome_tracking_material.md"
    assert manifest["artifacts"]["factor_signal_material"] == "analysis/factor_signal_material.md"
    assert manifest["artifacts"]["intelligence_fusion_material"] == "analysis/intelligence_fusion_material.md"
    assert manifest["artifacts"]["personalized_risk_material"] == "analysis/personalized_risk_material.md"
    assert manifest["codex_input"]["codex_context"]["artifact"] == "codex_context/context.md"
    assert manifest["codex_input"]["codex_context"]["status"] == "included"
    assert manifest["codex_input"]["codex_context"]["chars"] == len(context)
    assert manifest["codex_input"]["codex_context"]["over_budget"] is False
    assert manifest["codex_input"]["codex_prompt"]["artifact"] == "codex_context/prompt.md"
    assert manifest["codex_input"]["codex_prompt"]["status"] == "sent_to_codex_cli"
    assert manifest["codex_input"]["codex_prompt"]["chars"] == len(prompt)
    assert manifest["codex_input"]["codex_prompt"]["over_budget"] is False
    assert manifest["codex_input"]["warnings"] == []
    material_records = {
        record["artifact"]: record for record in manifest["codex_input"]["materials"]
    }
    assert material_records["analysis/data_quality_material.md"]["status"] == "included"
    assert material_records["analysis/outcome_tracking_material.md"]["status"] == "included"
    assert material_records["analysis/factor_signal_material.md"]["status"] == "included"
    assert material_records["analysis/intelligence_fusion_material.md"]["status"] == "included"
    assert material_records["analysis/personalized_risk_material.md"]["status"] == "included"
    codex_context_stage = _stage(manifest, "build_codex_context")
    report_stage = _stage(manifest, "run_codex_report")
    assert codex_context_stage["status"] == "succeeded"
    assert codex_context_stage["artifacts"] == [
        "codex_context/context.md",
        "codex_context/prompt.md",
    ]
    assert report_stage["status"] == "succeeded"


def test_codex_context_and_prompt_include_market_signal_material_when_quant_enabled(
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
            "evaluate_strategy_evaluation": _write_strategy_evaluation_summary,
            "build_strategy_experiment_material": _write_strategy_experiment_material,
            "run_codex_report": _skip_codex_report,
        },
    )

    assert result.succeeded is True
    context = (result.run.codex_context_dir / "context.md").read_text(encoding="utf-8")
    prompt = (result.run.codex_context_dir / "prompt.md").read_text(encoding="utf-8")
    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert "market_signals: analysis/market_signals.json" in context
    assert "report_readiness:" in context
    assert "status: passed" in context
    assert "name: latest_ohlcv_views" in context
    assert "name: strategy_evaluation" in context
    assert "strategy_evaluation_summary: analysis/strategy_evaluation_summary.json" in context
    assert "strategy_evaluation_material: analysis/strategy_evaluation_material.md" in context
    assert "strategy_experiment: analysis/strategy_experiment.json" in context
    assert "strategy_effectiveness_gates: analysis/strategy_effectiveness_gates.json" in context
    assert "strategy_experiment_material: analysis/strategy_experiment_material.md" in context
    assert "strategy_lifecycle_state: analysis/strategy_lifecycle_state.json" in context
    assert "strategy_lifecycle_material: analysis/strategy_lifecycle_material.md" in context
    assert "market_signal_material: analysis/market_signal_material.md" in context
    assert "data_quality_material: analysis/data_quality_material.md" in context
    assert "market_regime_assessment: analysis/market_regime_assessment.json" in context
    assert "risk_assessment: analysis/risk_assessment.json" in context
    assert "decision_recommendations: analysis/decision_recommendations.json" in context
    assert "watch_triggers: analysis/watch_triggers.json" in context
    assert "decision_intelligence_delta: analysis/decision_intelligence_delta.json" in context
    assert "decision_intelligence_material: analysis/decision_intelligence_material.md" in context
    assert "artifact_type: analysis_market_signal_material" in context
    assert "artifact_type: analysis_strategy_evaluation_material" in context
    assert "artifact_type: analysis_strategy_experiment_material" in context
    assert "artifact_type: analysis_strategy_lifecycle_material" in context
    assert "artifact_type: analysis_decision_intelligence_material" in context
    assert "research_decision_support_only: true" in context
    assert "action_level:" in context
    assert "decision_bias:" in context
    assert "invalidation_conditions:" in context
    assert "record_type: market_signal" in context
    assert "signal_id: market_signal:tsmom_vol_scaled:binance:BTCUSDT:1d:2026-06-03T00:00:00Z" in context
    assert "latest_close: 106.0" in context
    assert "return_window_pct is 6.0% over the configured return window." in context
    assert "Strategy uses OHLCV close prices only and excludes text events." in context
    assert "raw_ohlcv_history_embedded: false" in context
    assert "full_data_quality_json_embedded: false" in context
    assert "codex_may_generate_validation_results: false" in context
    assert "open_time:" not in context
    assert "Quantitative conclusions" in prompt
    assert "Keep quantitative signal evidence and uncertainty near" in prompt
    assert "explain upstream strategy conclusions from the provided material only as needed" in prompt
    assert "Do not list every strategy/source/symbol/timeframe row" in prompt
    assert "do not restate every strategy run row or numeric field" in prompt
    assert "Watch points:" in prompt
    assert "Risk notes:" in prompt
    assert "When market signal material is present" in prompt
    assert "Quantitative strategy material rules:" in prompt
    assert "Keep strategy assumptions, evidence, and uncertainty adjacent" in prompt
    assert "When strategy signals disagree, describe the conflict" in prompt
    assert "Treat backtest diagnostics as historical research material only" in prompt
    assert "Strategy evaluation material rules:" in prompt
    assert "cost assumptions, baseline comparison, sample limits" in prompt
    assert "Use Halpha-generated evaluation metrics only" in prompt
    assert "Do not upgrade weak, fragile, unstable, costly" in prompt
    assert "Strategy experiment gate material rules:" in prompt
    assert "Use Halpha-generated effectiveness gate statuses only" in prompt
    assert "identify effective, watchlisted, rejected, and insufficient-evidence" in prompt
    assert "Do not generate or revise strategy gate statuses" in prompt
    assert "Strategy lifecycle material rules:" in prompt
    assert "When strategy lifecycle material is present" in prompt
    assert "Use Halpha-generated lifecycle statuses" in prompt
    assert "Do not generate or revise lifecycle states" in prompt
    assert "Decision intelligence material rules:" in prompt
    assert "Data quality material rules:" in prompt
    assert "data quality material as Halpha-generated reliability evidence" in prompt
    assert "use it for action-facing decision language" in prompt
    assert "current decision view" in prompt
    assert "what to do" in prompt
    assert "what not to do" in prompt
    assert "tentative opportunities" in prompt
    assert "wait/watch conditions" in prompt
    assert "risk state" in prompt
    assert "invalidation conditions" in prompt
    assert "changes versus previous run" in prompt
    assert "uncertainty, and method limits" in prompt
    assert "Keep evidence, risk conditions, confidence, conflicts, and uncertainty near" in prompt
    assert "Do not invent action levels" in prompt
    assert "Do not upgrade WATCH, NO_ACTION" in prompt
    assert "no_previous_run" in prompt
    assert "Do not fabricate strategy signals, strategy conclusions" in prompt
    assert "return promises" in prompt
    assert "Do not calculate new quantitative signals from raw OHLCV history" in prompt
    assert "position sizing" in prompt
    assert "account actions" in prompt
    assert "Do not invent prices, events, links, sources, or certainty." in prompt
    assert "Preserve source awareness." in prompt
    assert "Do not include fixed boilerplate" in prompt
    assert "Start with a decision-useful thesis" in prompt
    assert "Do not default to neutral to avoid judgment" in prompt
    assert "Do not create standalone material-led sections" in prompt
    assert "Simplified Chinese Markdown" in prompt
    assert manifest["artifacts"]["codex_context"] == "codex_context/context.md"
    assert manifest["artifacts"]["codex_prompt"] == "codex_context/prompt.md"
    assert manifest["artifacts"]["data_quality_material"] == "analysis/data_quality_material.md"
    assert manifest["artifacts"]["strategy_evaluation_material"] == "analysis/strategy_evaluation_material.md"
    assert manifest["artifacts"]["strategy_experiment_material"] == "analysis/strategy_experiment_material.md"
    assert manifest["artifacts"]["strategy_lifecycle_material"] == "analysis/strategy_lifecycle_material.md"
    assert manifest["artifacts"]["decision_intelligence_material"] == "analysis/decision_intelligence_material.md"


def test_codex_context_and_prompt_include_onchain_flow_material_when_enabled(
    tmp_path: Path,
) -> None:
    config_path = _write_config(tmp_path, text_enabled=False, onchain_enabled=True)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
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
    context = (result.run.codex_context_dir / "context.md").read_text(encoding="utf-8")
    prompt = (result.run.codex_context_dir / "prompt.md").read_text(encoding="utf-8")
    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert "onchain_flow_context: analysis/onchain_flow_context.json" in context
    assert "onchain_flow_material: analysis/onchain_flow_material.md" in context
    assert '<embed path="analysis/onchain_flow_material.md">' in context
    assert "artifact_type: analysis_onchain_flow_material" in context
    assert "codex_may_generate_onchain_records: false" in context
    assert "codex_may_generate_flow_states: false" in context
    assert "codex_may_generate_address_labels: false" in context
    assert "full_raw_onchain_flow_artifacts_embedded: false" in context
    assert "full_onchain_flow_context_json_embedded: false" in context
    assert "PRIVATE_RAW_SENTINEL_SHOULD_NOT_APPEAR" not in context
    assert "When on-chain flow material is present" in prompt
    assert "On-chain flow material rules:" in prompt
    assert "Do not generate or revise on-chain records" in prompt
    assert "address labels" in prompt
    assert "wallet actions" in prompt
    assert "do not recreate it from raw on-chain artifacts" in prompt
    assert manifest["artifacts"]["onchain_flow_material"] == "analysis/onchain_flow_material.md"
    assert manifest["artifacts"]["codex_context"] == "codex_context/context.md"
    assert manifest["artifacts"]["codex_prompt"] == "codex_context/prompt.md"


def test_codex_context_fails_when_research_context_is_missing(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _write_market_raw,
            "collect_text_events": _write_text_raw,
            "build_research_context": _skip_research_context,
        },
    )

    assert result.succeeded is False
    assert result.failed_stage == "build_codex_context"
    assert result.reason == "analysis/research_context.md was not found; build_research_context must run first."
    assert not (result.run.codex_context_dir / "context.md").exists()
    assert not (result.run.codex_context_dir / "prompt.md").exists()

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert _stage(manifest, "build_codex_context")["status"] == "failed"
    assert manifest["errors"] == [
        {
            "stage": "build_codex_context",
            "message": "analysis/research_context.md was not found; build_research_context must run first.",
        }
    ]


def _write_config(
    tmp_path: Path,
    *,
    text_enabled: bool = True,
    quant_enabled: bool = False,
    onchain_enabled: bool = False,
) -> Path:
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
    config_path = tmp_path / "config.yaml"
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


def _write_outcome_history_state(tmp_path: Path) -> None:
    write_json(
        tmp_path / "data" / "research" / "metadata" / "outcome_history_state.json",
        {
            "schema_version": 1,
            "artifact_type": "outcome_history_state",
            "updated_at": "2026-06-05T00:00:00Z",
            "status": "ok",
            "storage_path": "data/research/outcomes",
            "history_path": "data/research/outcomes/outcome_history.json",
            "state_path": "data/research/metadata/outcome_history_state.json",
            "totals": {"records": 2, "warning_count": 0, "error_count": 0},
            "sources": [{"source_run_id": "source-run", "record_count": 2}],
            "target_kinds": [{"value": "event_assessment", "record_count": 1}],
            "outcome_states": [{"value": "confirmed", "record_count": 1}],
            "evaluation_statuses": [{"value": "evaluated", "record_count": 2}],
            "source_artifacts": ["runs/source-run/analysis/outcome_evaluations.json"],
            "warnings": [],
            "errors": [],
        },
    )


def _write_full_outcome_history_with_sentinel(tmp_path: Path) -> None:
    write_json(
        tmp_path / "data" / "research" / "outcomes" / "outcome_history.json",
        {
            "records": [
                {
                    "stable_outcome_key": "FULL_OUTCOME_HISTORY_SHOULD_NOT_APPEAR",
                    "target_id": "FULL_OUTCOME_HISTORY_SHOULD_NOT_APPEAR",
                }
            ]
        },
    )


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


def _write_strategy_evaluation_summary(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "strategy_evaluation_summary.json",
        {
            "schema_version": 1,
            "artifact_type": "strategy_evaluation_summary",
            "created_at": "2026-06-05T00:00:00Z",
            "records": [
                {
                    "evaluation_id": (
                        "strategy_evaluation:tsmom_vol_scaled:binance:BTCUSDT:1d:2026-06-03T00:00:00Z"
                    ),
                    "status": "succeeded",
                    "strategy_name": "tsmom_vol_scaled",
                    "input_view_id": "ohlcv_view:binance:BTCUSDT:1d:2026-06-03T00:00:00Z",
                    "single_window": {
                        "status": "succeeded",
                        "strategy_metrics": {"net_return_pct": 6.0, "max_drawdown_pct": -1.0},
                    },
                }
            ],
        },
    )
    (run.analysis_dir / "strategy_evaluation_material.md").write_text(
        "\n".join(
            [
                "# strategy_evaluation_material",
                "",
                "```yaml",
                "artifact_type: analysis_strategy_evaluation_material",
                "record_count: 1",
                "```",
                "",
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


def _skip_research_context(config, run) -> list[str]:
    return []


def _noop_stage(config, run) -> list[str]:
    return []


def _skip_codex_report(config, run) -> list[str]:
    return []


def _stage(manifest: dict, name: str) -> dict:
    return next(
        task
        for stage in manifest["stages"]
        for task in stage.get("tasks", [])
        if task["name"] == name
    )
