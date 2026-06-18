from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from halpha.config import load_config
from halpha.pipeline import run_pipeline, run_pipeline_stage
from halpha.storage import write_json


def test_alert_decisions_escalate_p0_and_p1_only_with_explicit_relevance(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = _run_alert_pipeline(
        config,
        config_path,
        records=[
            _assessment_record(
                "p0",
                event_severity="high",
                source_reliability="high",
                confidence="high",
                decision_impact="could_invalidate",
                risk_effect="risk_up",
                watch_relevance="invalidation",
            ),
            _assessment_record(
                "p1",
                event_severity="high",
                source_reliability="medium",
                confidence="medium",
                decision_impact="could_downgrade",
                risk_effect="risk_up",
                watch_relevance="risk_escalation",
            ),
        ],
    )

    artifact = _alert_decisions(result)
    manifest = _manifest(result)
    records = {record["scope"]["assessment_id"].split(":")[-1]: record for record in artifact["records"]}

    assert artifact["artifact_type"] == "alert_decisions"
    assert artifact["priority_taxonomy"] == ["P0", "P1", "P2", "P3", "no_alert", "unknown"]
    assert records["p0"]["priority"] == "P0"
    assert records["p0"]["attention_decision"] == "interrupt_now"
    assert records["p0"]["requires_user_attention"] is True
    assert records["p0"]["requires_reassessment"] is True
    assert records["p0"]["evidence_strength"] == "high"
    assert records["p0"]["source_artifacts"]
    assert records["p1"]["priority"] == "P1"
    assert records["p1"]["attention_decision"] == "review_soon"
    assert records["p1"]["requires_user_attention"] is True
    assert records["p1"]["evidence_strength"] == "medium"
    assert all(record["linked_event_assessment_ids"] for record in artifact["records"])

    assert manifest["artifacts"]["alert_decisions"] == "analysis/alert_decisions.json"
    assert manifest["counts"]["alert_decision_records"] == 2
    assert manifest["counts"]["alert_decision_p0_records"] == 1
    assert manifest["counts"]["alert_decision_p1_records"] == 1
    assert manifest["counts"]["alert_decision_no_alert_records"] == 0
    assert _stage(manifest, "build_alert_decisions")["artifacts"] == ["analysis/alert_decisions.json"]
    assert _stage(manifest, "build_event_intelligence_material")["status"] == "not_run"


def test_alert_decisions_record_p2_and_p3_archival_attention(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = _run_alert_pipeline(
        config,
        config_path,
        records=[
            _assessment_record(
                "p2",
                event_severity="medium",
                source_reliability="medium",
                confidence="medium",
                decision_impact="supports_existing_view",
                risk_effect="neutral",
                watch_relevance="confirmation",
            ),
            _assessment_record(
                "p3",
                event_severity="medium",
                source_reliability="high",
                confidence="high",
                decision_impact="supports_existing_view",
                risk_effect="neutral",
                watch_relevance="confirmation",
                downgrade_reasons=["duplicate_event_group", "stale_event"],
            ),
        ],
    )

    records = {record["scope"]["assessment_id"].split(":")[-1]: record for record in _alert_decisions(result)["records"]}

    assert records["p2"]["priority"] == "P2"
    assert records["p2"]["attention_decision"] == "record_without_interrupting"
    assert records["p2"]["requires_user_attention"] is False
    assert records["p2"]["suppression_reasons"] == []
    assert records["p3"]["priority"] == "P3"
    assert records["p3"]["attention_decision"] == "archive_as_noise"
    assert records["p3"]["requires_user_attention"] is False
    assert {"duplicate_event_group", "stale_event"} <= set(records["p3"]["suppression_reasons"])
    assert "alert_decision_suppressed_or_downgraded" in records["p3"]["warnings"]


def test_alert_decisions_reference_derivatives_relevance_when_event_is_relevant(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = _run_alert_pipeline(
        config,
        config_path,
        records=[
            _assessment_record(
                "derivatives",
                event_severity="high",
                source_reliability="high",
                confidence="high",
                decision_impact="could_downgrade",
                risk_effect="risk_up",
                watch_relevance="risk_escalation",
            )
        ],
        extra_handlers={"build_derivatives_market_context": _write_derivatives_context},
    )

    artifact = _alert_decisions(result)
    manifest = _manifest(result)
    record = artifact["records"][0]

    assert record["priority"] == "P1"
    assert record["linked_derivatives_context_ids"] == [
        "derivatives_context:funding_pressure:binance_usdm:BTCUSDT:8h:2026-06-05T00:00:00Z"
    ]
    assert any("derivatives_context funding_pressure" in item for item in record["derivatives_relevance"])
    assert "analysis/derivatives_market_context.json" in record["source_artifacts"]
    assert "analysis/derivatives_market_context.json" in artifact["source_artifacts"]
    assert manifest["counts"]["alert_decision_derivatives_linked_records"] == 1


def test_alert_decisions_suppress_no_alert_for_unrelated_or_insufficient_events(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = _run_alert_pipeline(
        config,
        config_path,
        records=[
            _assessment_record(
                "noise",
                event_severity="noise",
                source_reliability="low",
                confidence="low",
                decision_impact="insufficient_evidence",
                risk_effect="unknown",
                watch_relevance="none",
                downgrade_reasons=["unrelated_event"],
                affected_assets=[],
            ),
            _assessment_record(
                "insufficient",
                event_severity="low",
                source_reliability="low",
                confidence="low",
                decision_impact="insufficient_evidence",
                risk_effect="unknown",
                watch_relevance="wait_condition",
                downgrade_reasons=["event_signal_not_accepted", "insufficient_event_evidence"],
            ),
        ],
    )

    artifact = _alert_decisions(result)
    manifest = _manifest(result)

    assert {record["priority"] for record in artifact["records"]} == {"no_alert"}
    assert all(record["attention_decision"] == "no_alert" for record in artifact["records"])
    assert all(record["requires_user_attention"] is False for record in artifact["records"])
    assert all("suppress_as_no_alert" in record["suppression_reasons"] for record in artifact["records"])
    assert manifest["counts"]["alert_decision_no_alert_records"] == 2
    assert manifest["counts"]["alert_decision_suppressed_records"] == 2


def test_alert_decisions_skip_when_event_assessment_is_missing(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_alert_decisions",
        stage_handlers=_base_handlers({"build_event_intelligence_assessment": _noop_stage}),
    )

    manifest = _manifest(result)
    assert result.succeeded is True
    assert not (result.run.analysis_dir / "alert_decisions.json").exists()
    assert "alert_decisions" not in manifest["artifacts"]
    assert manifest["alert_decisions"]["status"] == "skipped"
    assert manifest["counts"]["alert_decision_records"] == 0
    assert _stage(manifest, "build_alert_decisions")["artifacts"] == []


def test_alert_decisions_single_stage_rerun(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    initial = _run_alert_pipeline(config, config_path, records=[_assessment_record("p2")])

    result = run_pipeline_stage(
        config,
        config_path=config_path,
        run_dir=initial.run.run_dir,
        stage="build_alert_decisions",
    )

    manifest = _manifest(result)
    assert result.succeeded is True
    assert manifest["stages"][-1]["name"] == "build_alert_decisions"
    assert manifest["stages"][-1]["mode"] == "single_stage"
    assert manifest["stages"][-1]["artifacts"] == ["analysis/alert_decisions.json"]
    assert _alert_decisions(result)["records"][0]["priority"] == "P2"


def _run_alert_pipeline(
    config: dict[str, Any],
    config_path: Path,
    *,
    records: list[dict[str, Any]],
    extra_handlers: dict[str, Any] | None = None,
):
    overrides = {"build_event_intelligence_assessment": lambda config, run: _write_assessment(run, records)}
    if extra_handlers:
        overrides.update(extra_handlers)
    return run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_alert_decisions",
        stage_handlers=_base_handlers(overrides),
    )


def _base_handlers(overrides: dict[str, Any]) -> dict[str, Any]:
    handlers: dict[str, Any] = {
        "collect_market_data": _noop_stage,
        "collect_text_events": _noop_stage,
        "build_text_event_records": _noop_stage,
        "build_text_entity_evidence": _noop_stage,
        "build_text_event_classification_evidence": _noop_stage,
        "build_text_event_topics": _noop_stage,
        "build_text_event_signals": _noop_stage,
        "sync_ohlcv": _noop_stage,
        "build_market_data_views": _noop_stage,
        "build_strategy_benchmark_suite": _noop_stage,
        "evaluate_quant_strategies": _noop_stage,
        "evaluate_strategy_evaluation": _noop_stage,
        "build_strategy_experiment_material": _noop_stage,
        "evaluate_market_strategy_signals": _noop_stage,
        "build_market_signals": _noop_stage,
        "build_market_signal_material": _noop_stage,
        "build_market_regime_assessment": _noop_stage,
        "build_risk_assessment": _write_risk_assessment,
        "build_decision_recommendations": _write_decision_recommendations,
        "build_watch_triggers": _write_watch_triggers,
        "build_event_market_confluence": _noop_stage,
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


def _assessment_record(
    suffix: str,
    *,
    event_severity: str = "medium",
    source_reliability: str = "medium",
    confidence: str = "medium",
    decision_impact: str = "supports_existing_view",
    risk_effect: str = "neutral",
    watch_relevance: str = "confirmation",
    downgrade_reasons: list[str] | None = None,
    affected_assets: list[str] | None = None,
) -> dict[str, Any]:
    downgrade_reasons = downgrade_reasons or []
    affected_assets = ["BTCUSDT"] if affected_assets is None else affected_assets
    return {
        "assessment_id": f"event_intelligence_assessment:BTCUSDT:1d:{suffix}",
        "status": "degraded" if downgrade_reasons else "succeeded",
        "scope": {
            "symbol": "BTCUSDT" if affected_assets else "market_wide",
            "timeframe": "1d",
            "topic_ids": [f"text_event_topic:{suffix}"],
            "event_signal_ids": [f"text_event_signal:{suffix}"],
        },
        "event_summary": f"Assessment fixture {suffix}.",
        "affected_assets": affected_assets,
        "relevant_timeframes": ["1d"],
        "source_reliability": source_reliability,
        "event_severity": event_severity,
        "market_response_relationship": "confirmed" if not downgrade_reasons else "independent",
        "decision_impact": decision_impact,
        "risk_effect": risk_effect,
        "watch_relevance": watch_relevance,
        "confidence": confidence,
        "evidence": [{"type": "event_signal", "event_signal_id": f"text_event_signal:{suffix}"}],
        "downgrade_reasons": downgrade_reasons,
        "uncertainty": ["Assessment fixture uncertainty."],
        "warnings": ["event_assessment_downgraded"] if downgrade_reasons else [],
        "linked_event_signal_ids": [f"text_event_signal:{suffix}"],
        "linked_decision_record_ids": ["decision_recommendation:binance:BTCUSDT:1d:2026-06-05T00:00:00Z"],
        "linked_watch_trigger_ids": ["watch_trigger:binance:BTCUSDT:1d:confirmation:2026-06-05T00:00:00Z"],
        "source_artifacts": [
            "analysis/event_intelligence_assessment.json",
            "analysis/text_event_signals.json",
            "analysis/decision_recommendations.json",
            "analysis/watch_triggers.json",
        ],
    }


def _write_assessment(run, records: list[dict[str, Any]]) -> list[str]:
    write_json(
        run.analysis_dir / "event_intelligence_assessment.json",
        {
            "schema_version": 1,
            "artifact_type": "event_intelligence_assessment",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["analysis/text_event_signals.json"],
            "coverage": {"records": len(records)},
            "records": records,
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["event_intelligence_assessment"] = "analysis/event_intelligence_assessment.json"
    run.manifest["counts"]["event_intelligence_assessment_records"] = len(records)
    return ["analysis/event_intelligence_assessment.json"]


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
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "risk_level": "high",
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
            "source_artifacts": ["analysis/risk_assessment.json"],
            "records": [
                {
                    "record_id": "decision_recommendation:binance:BTCUSDT:1d:2026-06-05T00:00:00Z",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "action_level": "TRY_SMALL",
                    "decision_bias": "tentative_constructive",
                    "source_artifacts": ["analysis/risk_assessment.json"],
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
                    "condition": "Confirmation remains required.",
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


def _write_derivatives_context(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "derivatives_market_context.json",
        {
            "schema_version": 1,
            "artifact_type": "derivatives_market_context",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "status": "warning",
            "records": [
                {
                    "context_id": "derivatives_context:funding_pressure:binance_usdm:BTCUSDT:8h:2026-06-05T00:00:00Z",
                    "context_type": "funding_pressure",
                    "data_class": "funding_rate",
                    "source": "binance_usdm",
                    "market_type": "usd_m_futures",
                    "symbol": "BTCUSDT",
                    "period": "8h",
                    "as_of": "2026-06-05T00:00:00Z",
                    "status": "succeeded",
                    "state": "extreme_positive_funding",
                    "severity": "high",
                    "confidence": "medium",
                    "metrics": {},
                    "thresholds": {},
                    "evidence": [],
                    "uncertainty": [],
                    "warnings": [],
                    "errors": [],
                    "source_artifacts": [
                        "analysis/derivatives_market_context.json",
                        "raw/derivatives_market_views.json",
                    ],
                }
            ],
            "counts": {"records": 1},
            "warnings": [],
            "errors": [],
            "source_artifacts": ["raw/derivatives_market_views.json"],
        },
    )
    run.manifest["artifacts"]["derivatives_market_context"] = "analysis/derivatives_market_context.json"
    return ["analysis/derivatives_market_context.json"]


def _alert_decisions(result) -> dict[str, Any]:
    return json.loads((result.run.analysis_dir / "alert_decisions.json").read_text(encoding="utf-8"))


def _manifest(result) -> dict[str, Any]:
    return json.loads(result.run.manifest_path.read_text(encoding="utf-8"))


def _stage(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    return next(stage for stage in manifest["stages"] if stage["name"] == name)


def _noop_stage(config, run) -> list[str]:
    return []
