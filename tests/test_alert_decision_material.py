from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from halpha.config import load_config
from halpha.pipeline import run_pipeline
from halpha.storage import write_json


def test_alert_decision_material_bounds_report_facing_alert_evidence(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_alert_decision_material",
        stage_handlers=_base_handlers(
            {
                "build_event_intelligence_assessment": _write_assessment,
                "build_alert_decisions": _write_alert_decisions,
            }
        ),
    )

    assert result.succeeded is True
    material = (result.run.analysis_dir / "alert_decision_material.md").read_text(encoding="utf-8")
    manifest = _manifest(result)

    assert "artifact_type: analysis_alert_decision_material" in material
    assert "analysis/event_intelligence_assessment.json" in material
    assert "analysis/alert_decisions.json" in material
    assert "## source_policy" in material
    assert "## alert_overview" in material
    assert "## priority_summary" in material
    assert "## decision_impact" in material
    assert "## risk_and_watch_relevance" in material
    assert "## downgrade_and_suppression_summary" in material
    assert "## uncertainty" in material
    assert "## report_usage_rules" in material
    assert "## records" in material
    assert "priority: P1" in material
    assert "decision_impact: could_downgrade" in material
    assert "downgrade_reasons:" in material
    assert "suppression_reasons:" in material
    assert "codex_may_generate_alert_priority: false" in material
    assert "codex_may_generate_event_severity: false" in material
    assert "codex_may_generate_decision_impact: false" in material
    assert "codex_may_generate_action_levels: false" in material
    assert "codex_may_send_or_schedule_alerts: false" in material
    assert "raw text body that should never be embedded" not in material

    assert manifest["artifacts"]["alert_decision_material"] == "analysis/alert_decision_material.md"
    assert manifest["counts"]["alert_decision_material_records"] == 2
    assert manifest["counts"]["alert_decision_material_warning_records"] == 1
    assert manifest["alert_decision_material"]["status"] == "succeeded"
    assert manifest["alert_decision_material"]["priority"] == {"P1": 1, "no_alert": 1}
    assert _stage(manifest, "build_alert_decision_material")["artifacts"] == [
        "analysis/alert_decision_material.md"
    ]
    assert _stage(manifest, "build_event_intelligence_material")["status"] == "not_run"


def test_alert_decision_material_skips_when_alert_decisions_are_missing(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_alert_decision_material",
        stage_handlers=_base_handlers(
            {
                "build_event_intelligence_assessment": _write_assessment,
                "build_alert_decisions": _noop_stage,
            }
        ),
    )

    manifest = _manifest(result)
    assert result.succeeded is True
    assert not (result.run.analysis_dir / "alert_decision_material.md").exists()
    assert "alert_decision_material" not in manifest["artifacts"]
    assert manifest["counts"]["alert_decision_material_records"] == 0
    assert manifest["alert_decision_material"]["status"] == "skipped"
    assert _stage(manifest, "build_alert_decision_material")["artifacts"] == []


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
        "build_risk_assessment": _noop_stage,
        "build_decision_recommendations": _noop_stage,
        "build_watch_triggers": _noop_stage,
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
  enabled: false
quant:
  enabled: false
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


def _write_assessment(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "event_intelligence_assessment.json",
        {
            "schema_version": 1,
            "artifact_type": "event_intelligence_assessment",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["analysis/text_event_signals.json"],
            "records": [
                {
                    "assessment_id": "event_intelligence_assessment:BTCUSDT:1d:p1",
                    "event_summary": "A bounded summary, not the raw text body that should never be embedded.",
                    "event_severity": "high",
                    "source_reliability": "medium",
                    "market_response_relationship": "conflicting",
                    "decision_impact": "could_downgrade",
                    "risk_effect": "risk_up",
                    "confidence": "medium",
                    "downgrade_reasons": [],
                },
                {
                    "assessment_id": "event_intelligence_assessment:BTCUSDT:1d:no_alert",
                    "event_summary": "Low confidence event.",
                    "event_severity": "low",
                    "source_reliability": "low",
                    "market_response_relationship": "insufficient_market_evidence",
                    "decision_impact": "insufficient_evidence",
                    "risk_effect": "unknown",
                    "confidence": "low",
                    "downgrade_reasons": ["event_signal_not_accepted", "insufficient_event_evidence"],
                },
            ],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["event_intelligence_assessment"] = "analysis/event_intelligence_assessment.json"
    return ["analysis/event_intelligence_assessment.json"]


def _write_alert_decisions(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "alert_decisions.json",
        {
            "schema_version": 1,
            "artifact_type": "alert_decisions",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["analysis/event_intelligence_assessment.json"],
            "records": [
                {
                    "alert_decision_id": "alert_decision:BTCUSDT:1d:p1",
                    "status": "succeeded",
                    "priority": "P1",
                    "scope": {
                        "symbol": "BTCUSDT",
                        "timeframe": "1d",
                        "assessment_id": "event_intelligence_assessment:BTCUSDT:1d:p1",
                    },
                    "attention_decision": "review_soon",
                    "decision_impact": "could_downgrade",
                    "risk_effect": "risk_up",
                    "watch_trigger_relevance": ["risk_escalation"],
                    "requires_reassessment": True,
                    "requires_user_attention": True,
                    "reason": "priority=P1; severity=high; decision_impact=could_downgrade.",
                    "evidence_strength": "medium",
                    "downgrade_reasons": [],
                    "suppression_reasons": [],
                    "uncertainty": ["Alert priority is deterministic."],
                    "warnings": [],
                    "linked_event_assessment_ids": ["event_intelligence_assessment:BTCUSDT:1d:p1"],
                    "linked_decision_record_ids": ["decision_recommendation:BTCUSDT:1d"],
                    "linked_watch_trigger_ids": ["watch_trigger:BTCUSDT:1d:risk_escalation"],
                    "source_artifacts": ["analysis/event_intelligence_assessment.json"],
                },
                {
                    "alert_decision_id": "alert_decision:BTCUSDT:1d:no_alert",
                    "status": "suppressed",
                    "priority": "no_alert",
                    "scope": {
                        "symbol": "BTCUSDT",
                        "timeframe": "1d",
                        "assessment_id": "event_intelligence_assessment:BTCUSDT:1d:no_alert",
                    },
                    "attention_decision": "no_alert",
                    "decision_impact": "insufficient_evidence",
                    "risk_effect": "unknown",
                    "watch_trigger_relevance": [],
                    "requires_reassessment": False,
                    "requires_user_attention": False,
                    "reason": "priority=no_alert; suppressed_or_downgraded=suppress_as_no_alert.",
                    "evidence_strength": "insufficient",
                    "downgrade_reasons": ["event_signal_not_accepted", "insufficient_event_evidence"],
                    "suppression_reasons": ["suppress_as_no_alert", "insufficient_event_evidence"],
                    "uncertainty": ["Evidence is insufficient."],
                    "warnings": ["alert_decision_not_user_attention"],
                    "linked_event_assessment_ids": ["event_intelligence_assessment:BTCUSDT:1d:no_alert"],
                    "linked_decision_record_ids": [],
                    "linked_watch_trigger_ids": [],
                    "source_artifacts": ["analysis/event_intelligence_assessment.json"],
                },
            ],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["alert_decisions"] = "analysis/alert_decisions.json"
    return ["analysis/alert_decisions.json"]


def _manifest(result) -> dict[str, Any]:
    return json.loads(result.run.manifest_path.read_text(encoding="utf-8"))


def _stage(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    return next(stage for stage in manifest["stages"] if stage["name"] == name)


def _noop_stage(config, run) -> list[str]:
    return []
