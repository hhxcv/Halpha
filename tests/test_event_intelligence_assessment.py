from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from halpha.config import load_config
from halpha.pipeline import run_pipeline, run_pipeline_stage
from halpha.storage import write_json


def test_event_intelligence_assessment_records_supported_event(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = _run_assessment_pipeline(config, config_path)

    assert result.succeeded is True
    artifact = _assessment(result)
    manifest = _manifest(result)
    record = artifact["records"][0]

    assert artifact["artifact_type"] == "event_intelligence_assessment"
    assert artifact["schema_version"] == 1
    assert {
        "analysis/text_event_topics.json",
        "analysis/text_event_signals.json",
        "analysis/event_market_confluence.json",
    } <= set(artifact["source_artifacts"])
    assert record["status"] == "succeeded"
    assert record["source_reliability"] == "high"
    assert record["event_severity"] == "medium"
    assert record["market_response_relationship"] == "confirmed"
    assert record["decision_impact"] == "supports_existing_view"
    assert record["risk_effect"] == "neutral"
    assert record["watch_relevance"] == "confirmation"
    assert record["confidence"] == "high"
    assert record["downgrade_reasons"] == []
    assert record["linked_event_signal_ids"] == ["text_event_signal:btcusdt:etf_flows:abc123"]
    assert record["linked_decision_record_ids"] == [
        "decision_recommendation:binance:BTCUSDT:1d:2026-06-05T00:00:00Z"
    ]
    assert record["linked_watch_trigger_ids"] == [
        "watch_trigger:binance:BTCUSDT:1d:confirmation:2026-06-05T00:00:00Z"
    ]
    assert "analysis/event_market_confluence.json" in record["source_artifacts"]

    assert manifest["artifacts"]["event_intelligence_assessment"] == "analysis/event_intelligence_assessment.json"
    assert manifest["counts"]["event_intelligence_assessment_records"] == 1
    assert manifest["counts"]["event_intelligence_assessment_downgraded_records"] == 0
    assert manifest["counts"]["event_intelligence_assessment_high_or_critical_records"] == 0
    assert manifest["event_intelligence_assessment"]["severity"] == {"medium": 1}
    assert _stage(manifest, "build_event_intelligence_assessment")["artifacts"] == [
        "analysis/event_intelligence_assessment.json"
    ]
    assert _stage(manifest, "build_event_intelligence_material")["status"] == "not_run"


def test_event_intelligence_assessment_single_stage_rerun(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    initial = _run_assessment_pipeline(config, config_path)

    result = run_pipeline_stage(
        config,
        config_path=config_path,
        run_dir=initial.run.run_dir,
        stage="build_event_intelligence_assessment",
    )

    assert result.succeeded is True
    manifest = _manifest(result)
    assert manifest["stages"][-1]["name"] == "build_event_intelligence_assessment"
    assert manifest["stages"][-1]["mode"] == "single_stage"
    assert manifest["stages"][-1]["artifacts"] == ["analysis/event_intelligence_assessment.json"]
    assert _assessment(result)["records"]


def test_event_intelligence_assessment_skips_without_event_inputs(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_event_intelligence_assessment",
        stage_handlers=_base_handlers(
            {
                "build_text_event_topics": _noop_stage,
                "build_text_event_signals": _noop_stage,
                "build_market_signals": _noop_stage,
                "build_market_regime_assessment": _noop_stage,
                "build_risk_assessment": _noop_stage,
                "build_decision_recommendations": _noop_stage,
                "build_watch_triggers": _noop_stage,
            }
        ),
    )

    manifest = _manifest(result)
    assert result.succeeded is True
    assert not (result.run.analysis_dir / "event_intelligence_assessment.json").exists()
    assert "event_intelligence_assessment" not in manifest["artifacts"]
    assert manifest["event_intelligence_assessment"]["status"] == "skipped"
    assert manifest["counts"]["event_intelligence_assessment_records"] == 0
    assert _stage(manifest, "build_event_intelligence_assessment")["artifacts"] == []


def test_event_intelligence_assessment_downgrades_low_confidence_event(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = _run_assessment_pipeline(config, config_path, signal_status="low_confidence")

    record = _assessment(result)["records"][0]
    assert record["status"] == "degraded"
    assert record["event_severity"] == "low"
    assert record["source_reliability"] == "low"
    assert record["market_response_relationship"] == "insufficient_market_evidence"
    assert record["decision_impact"] == "insufficient_evidence"
    assert {"event_signal_not_accepted", "low_confidence_event", "insufficient_event_evidence"} <= set(
        record["downgrade_reasons"]
    )
    assert "event_assessment_downgraded" in record["warnings"]


def test_event_intelligence_assessment_downgrades_duplicate_and_stale_event(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = _run_assessment_pipeline(config, config_path, recency="stale", duplicate_topic=True)

    record = _assessment(result)["records"][0]
    assert record["status"] == "degraded"
    assert record["event_severity"] == "low"
    assert {"duplicate_event_group", "stale_event"} <= set(record["downgrade_reasons"])
    assert record["market_response_relationship"] == "confirmed"
    assert record["decision_impact"] == "supports_existing_view"


def test_event_intelligence_assessment_suppresses_unrelated_signal_without_market_context(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = _run_assessment_pipeline(
        config,
        config_path,
        include_market_decision=False,
        symbol=None,
    )

    record = _assessment(result)["records"][0]
    manifest = _manifest(result)
    assert record["status"] == "degraded"
    assert record["affected_assets"] == []
    assert record["event_severity"] == "noise"
    assert record["market_response_relationship"] == "insufficient_market_evidence"
    assert {"unrelated_event", "event_market_confluence_missing", "decision_recommendation_missing"} <= set(
        record["downgrade_reasons"]
    )
    assert manifest["counts"]["event_intelligence_assessment_downgraded_records"] == 1
    assert manifest["counts"]["event_intelligence_assessment_insufficient_market_evidence_records"] == 1


def _run_assessment_pipeline(
    config: dict[str, Any],
    config_path: Path,
    *,
    signal_status: str = "accepted",
    recency: str = "fresh",
    duplicate_topic: bool = False,
    include_market_decision: bool = True,
    symbol: str | None = "BTCUSDT",
):
    return run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_event_intelligence_assessment",
        stage_handlers=_base_handlers(
            {
                "build_text_event_topics": lambda config, run: _write_topics(
                    run,
                    duplicate_topic=duplicate_topic,
                    symbol=symbol,
                ),
                "build_text_event_signals": lambda config, run: _write_event_signals(
                    run,
                    status=signal_status,
                    recency=recency,
                    symbol=symbol,
                ),
                "build_market_signals": _write_market_signals if include_market_decision else _noop_stage,
                "build_market_regime_assessment": _write_market_regime if include_market_decision else _noop_stage,
                "build_risk_assessment": _write_risk_assessment if include_market_decision else _noop_stage,
                "build_decision_recommendations": _write_decision_recommendations
                if include_market_decision
                else _noop_stage,
                "build_watch_triggers": _write_watch_triggers if include_market_decision else _noop_stage,
            }
        ),
    )


def _base_handlers(overrides: dict[str, Any]) -> dict[str, Any]:
    handlers: dict[str, Any] = {
        "collect_market_data": _noop_stage,
        "collect_text_events": _noop_stage,
        "build_text_event_records": _noop_stage,
        "build_text_entity_evidence": _noop_stage,
        "build_text_event_classification_evidence": _noop_stage,
        "sync_ohlcv": _noop_stage,
        "build_market_data_views": _noop_stage,
        "build_strategy_benchmark_suite": _noop_stage,
        "evaluate_quant_strategies": _noop_stage,
        "evaluate_strategy_evaluation": _noop_stage,
        "build_strategy_experiment_material": _noop_stage,
        "evaluate_market_strategy_signals": _noop_stage,
        "build_market_signal_material": _noop_stage,
    }
    handlers.update(overrides)
    return handlers


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


def _write_topics(run, *, duplicate_topic: bool, symbol: str | None) -> list[str]:
    write_json(
        run.analysis_dir / "text_event_topics.json",
        {
            "schema_version": 1,
            "artifact_type": "text_event_topics",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["analysis/text_event_records.json", "analysis/text_entity_evidence.json"],
            "topics": [
                {
                    "topic_id": "text_event_topic:btcusdt:abc123",
                    "status": "succeeded",
                    "topic_label": "Bitcoin ETF flow",
                    "symbols": [symbol] if symbol else [],
                    "event_ids": ["text_event:coindesk:abc123"],
                    "primary_event_id": "text_event:coindesk:abc123",
                    "source_count": 2,
                    "event_count": 2 if duplicate_topic else 1,
                    "first_seen_at": "2026-06-05T00:00:00Z",
                    "latest_seen_at": "2026-06-05T00:30:00Z",
                    "merge_decisions": [
                        {
                            "left_event_id": "text_event:coindesk:abc123",
                            "right_event_id": "text_event:blockworks:def456",
                            "relationship": "duplicate",
                            "similarity": 1.0,
                            "reasons": ["canonical_url_match"],
                            "methods": ["canonical_url_rule"],
                        }
                    ]
                    if duplicate_topic
                    else [],
                    "warnings": [],
                    "source_artifacts": ["analysis/text_event_records.json", "analysis/text_entity_evidence.json"],
                }
            ],
            "pair_decisions": [],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["text_event_topics"] = "analysis/text_event_topics.json"
    return ["analysis/text_event_topics.json"]


def _write_event_signals(run, *, status: str, recency: str, symbol: str | None) -> list[str]:
    accepted = status == "accepted"
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
                    "event_signal_id": "text_event_signal:btcusdt:etf_flows:abc123",
                    "status": status,
                    "symbol": symbol,
                    "relevance_scope": "symbol" if symbol else "market_wide",
                    "topic_id": "text_event_topic:btcusdt:abc123",
                    "primary_category": "etf_flows" if accepted else "unknown",
                    "event_bias": "supportive" if accepted else "unknown",
                    "risk_impact": "neutral" if accepted else "unknown",
                    "opportunity_impact": "opportunity_up" if accepted else "unknown",
                    "strength": "medium" if accepted else "unknown",
                    "confidence": "high" if accepted else "low",
                    "recency": recency,
                    "evidence": [{"type": "category_gate", "accepted_by_gate": accepted}],
                    "uncertainty": ["Event signal is bounded research evidence."],
                    "warnings": [] if accepted else ["signal_status_low_confidence"],
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


def _write_market_signals(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "market_signals.json",
        {
            "schema_version": 1,
            "artifact_type": "market_signals",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["analysis/market_strategy_signals.json"],
            "signals": [
                {
                    "signal_id": "market_signal:tsmom_vol_scaled:binance:BTCUSDT:1d:2026-06-05T00:00:00Z",
                    "strategy_name": "tsmom_vol_scaled",
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "direction": "bullish",
                    "strength": "medium",
                    "confidence": "medium",
                    "evidence": ["market direction is bullish."],
                    "uncertainty": [],
                    "insufficient_data": False,
                    "source_artifacts": ["analysis/market_strategy_signals.json"],
                }
            ],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["market_signals"] = "analysis/market_signals.json"
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
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "regime": "trend_up",
                    "confidence": "medium",
                    "source_artifacts": ["analysis/market_signals.json"],
                }
            ],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["market_regime_assessment"] = "analysis/market_regime_assessment.json"
    return ["analysis/market_regime_assessment.json"]


def _write_risk_assessment(config, run) -> list[str]:
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
                    "risk_level": "low",
                    "status": "succeeded",
                    "source_artifacts": ["analysis/market_signals.json"],
                }
            ],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["risk_assessment"] = "analysis/risk_assessment.json"
    return ["analysis/risk_assessment.json"]


def _write_decision_recommendations(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "decision_recommendations.json",
        {
            "schema_version": 1,
            "artifact_type": "decision_recommendations",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["analysis/risk_assessment.json", "analysis/market_signals.json"],
            "records": [
                {
                    "record_id": "decision_recommendation:binance:BTCUSDT:1d:2026-06-05T00:00:00Z",
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "action_level": "TRY_SMALL",
                    "decision_bias": "tentative_constructive",
                    "status": "actionable",
                    "source_artifacts": ["analysis/risk_assessment.json", "analysis/market_signals.json"],
                }
            ],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["decision_recommendations"] = "analysis/decision_recommendations.json"
    return ["analysis/decision_recommendations.json"]


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


def _assessment(result) -> dict[str, Any]:
    return json.loads((result.run.analysis_dir / "event_intelligence_assessment.json").read_text(encoding="utf-8"))


def _manifest(result) -> dict[str, Any]:
    return json.loads(result.run.manifest_path.read_text(encoding="utf-8"))


def _stage(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    return next(stage for stage in manifest["stages"] if stage["name"] == name)


def _noop_stage(config, run) -> list[str]:
    return []
