from __future__ import annotations

import json
from pathlib import Path

from halpha.config import load_config
from halpha.pipeline import run_pipeline
from halpha.storage import write_json


def test_event_market_confluence_records_aligned_event_and_market_evidence(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = _run_confluence_pipeline(config, config_path, market_direction="bullish", action_level="TRY_SMALL")

    assert result.succeeded is True
    artifact = _confluence(result)
    record = artifact["records"][0]

    assert artifact["artifact_type"] == "event_market_confluence"
    assert {
        "analysis/text_event_signals.json",
        "analysis/market_signals.json",
        "analysis/decision_recommendations.json",
        "analysis/risk_assessment.json",
        "analysis/watch_triggers.json",
    } <= set(artifact["source_artifacts"])
    assert record["relationship"] == "confluence"
    assert record["event_bias_summary"] == "supportive"
    assert record["quant_direction_summary"] == "bullish"
    assert record["decision_action_level"] == "TRY_SMALL"
    assert record["risk_effect"] == "do_not_upgrade"
    assert record["linked_event_signal_ids"] == ["text_event_signal:btcusdt:etf_flows:abc123"]
    assert record["linked_decision_record_ids"] == ["decision_recommendation:binance:BTCUSDT:1d:2026-06-05T00:00:00Z"]
    assert {item["type"] for item in record["evidence"]} >= {
        "decision_recommendation",
        "event_signal",
        "market_signal",
        "risk_assessment",
    }
    assert "Use event evidence only as context; do not upgrade action levels from events alone." in record[
        "watch_implications"
    ]
    assert "Event confluence is explanatory and must not upgrade action levels by itself." in record["uncertainty"]

    manifest = _manifest(result)
    assert manifest["artifacts"]["event_market_confluence"] == "analysis/event_market_confluence.json"
    assert manifest["counts"]["event_market_confluence_records"] == 1
    assert manifest["counts"]["event_market_confluence_confluence"] == 1


def test_event_market_confluence_records_conflict_without_upgrading_actions(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = _run_confluence_pipeline(config, config_path, market_direction="bearish", action_level="WATCH")

    assert result.succeeded is True
    record = _confluence(result)["records"][0]

    assert record["relationship"] == "conflict"
    assert record["decision_action_level"] == "WATCH"
    assert record["risk_effect"] == "do_not_upgrade_due_to_risk"
    assert "Review event-quant conflict before using stronger decision bias." in record["watch_implications"]
    assert any("conflict" in item.lower() for item in record["uncertainty"])


def test_event_market_confluence_keeps_unknown_events_insufficient(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = _run_confluence_pipeline(
        config,
        config_path,
        market_direction="bullish",
        action_level="TRY_SMALL",
        event_status="unknown",
    )

    assert result.succeeded is True
    record = _confluence(result)["records"][0]

    assert record["relationship"] == "insufficient_event_evidence"
    assert record["event_bias_summary"] == "unknown"
    assert record["linked_event_signal_ids"] == ["text_event_signal:btcusdt:unknown:abc123"]
    assert "insufficient_event_evidence" in record["warnings"]
    assert "Wait for accepted event evidence before discussing event confluence." in record["watch_implications"]


def _run_confluence_pipeline(
    config: dict,
    config_path: Path,
    *,
    market_direction: str,
    action_level: str,
    event_status: str = "accepted",
):
    return run_pipeline(
        config,
        config_path=config_path,
        until_stage="synthesize_intelligence",
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "build_text_event_records": _noop_stage,
            "build_text_entity_evidence": _noop_stage,
            "build_text_event_classification_evidence": _noop_stage,
            "build_text_event_topics": _noop_stage,
            "build_text_event_signals": lambda config, run: _write_event_signals(
                config,
                run,
                status=event_status,
            ),
            "sync_ohlcv": _noop_stage,
            "build_market_data_views": _noop_stage,
            "build_strategy_benchmark_suite": _noop_stage,
            "evaluate_quant_strategies": _noop_stage,
            "evaluate_strategy_evaluation": _noop_stage,
            "build_strategy_experiment": _noop_stage,
            "build_strategy_experiment_material": _noop_stage,
            "build_market_signals": lambda config, run: _write_market_signals(
                config,
                run,
                direction=market_direction,
            ),
            "build_market_signal_material": _noop_stage,
            "build_market_regime_assessment": _write_market_regime,
            "build_risk_assessment": lambda config, run: _write_risk_assessment(
                config,
                run,
                risk_level="high" if action_level == "WATCH" else "low",
            ),
            "build_watch_triggers": _write_watch_triggers,
            "build_event_intelligence_assessment": _noop_stage,
            "build_alert_decisions": _noop_stage,
            "build_decision_intelligence_delta": _noop_stage,
            "build_outcome_targets": _noop_stage,
            "evaluate_outcomes": _noop_stage,
            "build_strategy_lifecycle_state": _noop_stage,
            "build_strategy_lifecycle_material": _noop_stage,
            "build_feature_snapshots": _noop_stage,
            "build_factor_states": _noop_stage,
            "build_multi_source_signals": _noop_stage,
            "build_intelligence_fusion": _noop_stage,
            "build_user_state_context": _noop_stage,
            "build_personalized_risk_constraints": _noop_stage,
        },
    )


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  output_dir: runs
market:
  enabled: true
  source: binance
  symbols:
    - BTCUSDT
  ohlcv:
    storage_dir: data/market/ohlcv
    timeframes:
      - 1d
    lookback:
      1d: 3
quant:
  enabled: true
  engine: vectorbt
  strategies:
    - name: tsmom_vol_scaled
text:
  enabled: true
  max_items: 1
  sources:
    - name: coindesk
      type: rss
      url: https://example.com/feed.xml
report:
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _write_event_signals(config, run, *, status: str) -> list[str]:
    event_bias = "supportive" if status == "accepted" else "unknown"
    category = "etf_flows" if status == "accepted" else "unknown"
    signal_id = f"text_event_signal:btcusdt:{category}:abc123"
    write_json(
        run.analysis_dir / "text_event_signals.json",
        {
            "schema_version": 1,
            "artifact_type": "text_event_signals",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": [
                "analysis/text_event_records.json",
                "analysis/text_event_topics.json",
                "analysis/text_event_classification_evidence.json",
            ],
            "model_states": [],
            "coverage": {"signals": 1},
            "signals": [
                {
                    "event_signal_id": signal_id,
                    "status": status,
                    "symbol": "BTCUSDT",
                    "relevance_scope": "symbol",
                    "topic_id": "text_event_topic:btcusdt:abc123",
                    "primary_category": category,
                    "event_bias": event_bias,
                    "risk_impact": "neutral",
                    "opportunity_impact": "opportunity_up" if status == "accepted" else "unknown",
                    "strength": "medium" if status == "accepted" else "unknown",
                    "confidence": "high" if status == "accepted" else "unknown",
                    "recency": "fresh",
                    "evidence": [{"type": "category_gate", "accepted_by_gate": status == "accepted"}],
                    "uncertainty": ["Event signal is research context."],
                    "warnings": [] if status == "accepted" else ["signal_status_unknown"],
                    "source_event_ids": ["text_event:coindesk:abc123"],
                    "source_artifacts": [
                        "analysis/text_event_records.json",
                        "analysis/text_event_topics.json",
                        "analysis/text_event_classification_evidence.json",
                    ],
                }
            ],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["text_event_signals"] = "analysis/text_event_signals.json"
    run.manifest["counts"]["text_event_signals"] = 1
    return ["analysis/text_event_signals.json"]


def _write_market_signals(config, run, *, direction: str) -> list[str]:
    write_json(
        run.analysis_dir / "market_signals.json",
        {
            "schema_version": 1,
            "artifact_type": "market_signals",
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["analysis/quant_strategy_runs.json"],
            "signals": [
                {
                    "signal_id": "market_signal:tsmom_vol_scaled:binance:BTCUSDT:1d:2026-06-05T00:00:00Z",
                    "strategy_name": "tsmom_vol_scaled",
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "direction": direction,
                    "strength": "medium",
                    "confidence": "medium",
                    "latest_candle_time": "2026-06-05T00:00:00Z",
                    "evidence": [f"market direction is {direction}."],
                    "uncertainty": [],
                    "insufficient_data": False,
                    "source_artifacts": ["analysis/quant_strategy_runs.json"],
                }
            ],
        },
    )
    run.manifest["artifacts"]["market_signals"] = "analysis/market_signals.json"
    run.manifest["counts"]["market_signals"] = 1
    return ["analysis/market_signals.json"]


def _write_market_regime(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "market_regime_assessment.json",
        {
            "schema_version": 1,
            "artifact_type": "market_regime_assessment",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["analysis/market_signals.json"],
            "records": [
                {
                    "record_id": "market_regime_assessment:binance:BTCUSDT:1d:2026-06-05T00:00:00Z",
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "regime": "trend_up",
                    "confidence": "medium",
                    "status": "succeeded",
                    "evidence": ["regime=trend_up"],
                    "source_artifacts": ["analysis/market_signals.json"],
                }
            ],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["market_regime_assessment"] = "analysis/market_regime_assessment.json"
    return ["analysis/market_regime_assessment.json"]


def _write_risk_assessment(config, run, *, risk_level: str) -> list[str]:
    write_json(
        run.analysis_dir / "risk_assessment.json",
        {
            "schema_version": 1,
            "artifact_type": "risk_assessment",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["analysis/market_signals.json"],
            "records": [
                {
                    "record_id": "risk_assessment:binance:BTCUSDT:1d:2026-06-05T00:00:00Z",
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "risk_level": risk_level,
                    "status": "succeeded",
                    "evidence": [f"risk_level={risk_level}"],
                    "source_artifacts": ["analysis/market_signals.json"],
                }
            ],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["risk_assessment"] = "analysis/risk_assessment.json"
    return ["analysis/risk_assessment.json"]


def _write_watch_triggers(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "watch_triggers.json",
        {
            "schema_version": 1,
            "artifact_type": "watch_triggers",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["analysis/decision_recommendations.json"],
            "records": [
                {
                    "trigger_id": "watch_trigger:binance:BTCUSDT:1d:confirmation:2026-06-05T00:00:00Z",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "type": "confirmation",
                    "condition": "BTCUSDT confirmation condition remains required.",
                    "linked_decision_record_id": "decision_recommendation:binance:BTCUSDT:1d:2026-06-05T00:00:00Z",
                    "source_artifacts": ["analysis/decision_recommendations.json"],
                }
            ],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["watch_triggers"] = "analysis/watch_triggers.json"
    return ["analysis/watch_triggers.json"]


def _confluence(result) -> dict:
    return json.loads((result.run.analysis_dir / "event_market_confluence.json").read_text(encoding="utf-8"))


def _manifest(result) -> dict:
    return json.loads(result.run.manifest_path.read_text(encoding="utf-8"))


def _noop_stage(config, run) -> list[str]:
    return []
