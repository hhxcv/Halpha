from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from halpha.decision.fusion_integration import integrate_intelligence_fusion
from halpha.pipeline import RunContext
from halpha.storage import write_json


def test_fusion_integration_attaches_supportive_context_without_upgrading(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_decision_artifact(run, [_decision(action_level="TRY_SMALL")])
    _write_alert_artifact(run, [_alert(priority="P2")])
    _write_fusion_artifact(run, [_fusion(state="supportive", confluence="aligned")])

    artifacts = integrate_intelligence_fusion({"quant": {"enabled": True}}, run)

    decision = _decision_records(run)[0]
    alert = _alert_records(run)[0]
    assert artifacts == ["analysis/decision_recommendations.json", "analysis/alert_decisions.json"]
    assert decision["action_level"] == "TRY_SMALL"
    assert decision["fusion_state"] == "supportive"
    assert decision["fusion_record_id"] == "fusion:btcusdt:1d"
    assert "pre_fusion_action_level" not in decision
    assert alert["priority"] == "P2"
    assert alert["fusion_attention_annotation"] == "fusion_aligned"
    assert alert["fusion_state"] == "supportive"
    assert _manifest_count(run, "intelligence_fusion_decision_linked_records") == 1
    assert _manifest_count(run, "intelligence_fusion_alert_linked_records") == 1


def test_fusion_integration_downgrades_decision_on_severe_conflict(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_decision_artifact(run, [_decision(action_level="DO", decision_bias="constructive")])
    _write_fusion_artifact(run, [_fusion(state="conflicting", conflict="severe")])

    integrate_intelligence_fusion({"quant": {"enabled": True}}, run)

    decision = _decision_records(run)[0]
    assert decision["action_level"] == "WATCH"
    assert decision["decision_bias"] == "wait_for_conflict_resolution"
    assert decision["pre_fusion_action_level"] == "DO"
    assert "fusion_severe_conflict" in decision["downgrade_reasons"]
    assert "fusion_conflict_state=severe." in decision["conflicts"]
    assert _manifest_count(run, "intelligence_fusion_decision_adjusted_records") == 1


def test_fusion_integration_downgrades_decision_on_lifecycle_retirement_context(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_decision_artifact(run, [_decision(action_level="DO", decision_bias="constructive")])
    _write_fusion_artifact(
        run,
        [
            _fusion(
                state="conflicting",
                conflict="material",
                evidence=[
                    "caution: strategy_lifecycle state=retired direction=cautionary lifecycle_status=retired retirement_state=explicitly_retired"
                ],
                source_artifacts=[
                    "analysis/intelligence_fusion.json",
                    "analysis/strategy_lifecycle_state.json",
                ],
            )
        ],
    )

    integrate_intelligence_fusion({"quant": {"enabled": True}}, run)

    decision = _decision_records(run)[0]
    assert decision["action_level"] == "WATCH"
    assert decision["pre_fusion_action_level"] == "DO"
    assert "fusion_severe_conflict" in decision["downgrade_reasons"]
    assert "analysis/strategy_lifecycle_state.json" in decision["source_artifacts"]
    assert "analysis/strategy_lifecycle_state.json" in decision["fusion_source_artifacts"]
    assert any("strategy_lifecycle state=retired" in item for item in decision["fusion_evidence"])


def test_fusion_integration_blocks_decision_on_risk_override(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_decision_artifact(run, [_decision(action_level="TRY_SMALL")])
    _write_fusion_artifact(run, [_fusion(state="risk_blocked", risk_override="block")])

    integrate_intelligence_fusion({"quant": {"enabled": True}}, run)

    decision = _decision_records(run)[0]
    assert decision["action_level"] == "NO_ACTION"
    assert decision["decision_bias"] == "risk_blocked"
    assert decision["status"] == "risk_blocked"
    assert "fusion_risk_override_block" in decision["downgrade_reasons"]
    assert any("fusion_risk_override_state=block" in item for item in decision["risk_conditions"])


def test_fusion_integration_blocks_decision_on_event_override(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_decision_artifact(run, [_decision(action_level="TRY_SMALL")])
    _write_fusion_artifact(run, [_fusion(state="event_overridden", event_override="block")])

    integrate_intelligence_fusion({"quant": {"enabled": True}}, run)

    decision = _decision_records(run)[0]
    assert decision["action_level"] == "NO_ACTION"
    assert decision["status"] == "no_action"
    assert "fusion_event_override_block" in decision["downgrade_reasons"]
    assert any("fusion_event_override_state=block" in item for item in decision["risk_conditions"])


def test_fusion_integration_downgrades_insufficient_alert_attention(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_alert_artifact(run, [_alert(priority="P1")])
    _write_fusion_artifact(run, [_fusion(state="insufficient_evidence", confluence="none")])

    integrate_intelligence_fusion({"quant": {"enabled": True}}, run)

    alert = _alert_records(run)[0]
    assert alert["priority"] == "P3"
    assert alert["pre_fusion_priority"] == "P1"
    assert alert["requires_user_attention"] is False
    assert alert["requires_reassessment"] is True
    assert alert["fusion_attention_annotation"] == "insufficient_evidence_watch_only"
    assert "fusion_insufficient_evidence_watch_only" in alert["downgrade_reasons"]
    assert _manifest_count(run, "intelligence_fusion_alert_adjusted_records") == 1


def test_fusion_integration_refreshes_decision_and_alert_material(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_decision_artifact(run, [_decision(action_level="DO", decision_bias="constructive")])
    _write_alert_artifact(run, [_alert(priority="P1")])
    _write_fusion_artifact(run, [_fusion(state="conflicting", conflict="severe")])
    _write_material_inputs(run)
    (run.analysis_dir / "decision_intelligence_material.md").write_text("old decision material", encoding="utf-8")
    (run.analysis_dir / "alert_decision_material.md").write_text("old alert material", encoding="utf-8")

    artifacts = integrate_intelligence_fusion({"quant": {"enabled": True}}, run)

    decision_material = (run.analysis_dir / "decision_intelligence_material.md").read_text(encoding="utf-8")
    alert_material = (run.analysis_dir / "alert_decision_material.md").read_text(encoding="utf-8")
    assert "analysis/decision_intelligence_material.md" in artifacts
    assert "analysis/alert_decision_material.md" in artifacts
    assert "fusion_state: conflicting" in decision_material
    assert "fusion_adjustment_reasons:" in decision_material
    assert "fusion_attention_annotation: conflict_watch_only" in alert_material
    assert "codex_may_generate_fusion_states: false" in alert_material


def _run_context(tmp_path: Path) -> RunContext:
    run_dir = tmp_path / "run"
    raw_dir = run_dir / "raw"
    analysis_dir = run_dir / "analysis"
    codex_context_dir = run_dir / "codex_context"
    report_dir = run_dir / "report"
    for directory in (raw_dir, analysis_dir, codex_context_dir, report_dir):
        directory.mkdir(parents=True, exist_ok=True)
    return RunContext(
        run_id="test-run",
        run_dir=run_dir,
        raw_dir=raw_dir,
        analysis_dir=analysis_dir,
        codex_context_dir=codex_context_dir,
        report_dir=report_dir,
        manifest_path=run_dir / "run_manifest.json",
        config_path=tmp_path / "config.yaml",
        manifest={"artifacts": {}, "counts": {}, "stages": [], "codex": {}, "errors": []},
    )


def _write_decision_artifact(run: RunContext, records: list[dict[str, Any]]) -> None:
    _write_records_artifact(run, "decision_recommendations.json", "decision_recommendations", records)


def _write_alert_artifact(run: RunContext, records: list[dict[str, Any]]) -> None:
    _write_records_artifact(run, "alert_decisions.json", "alert_decisions", records)


def _write_fusion_artifact(run: RunContext, records: list[dict[str, Any]]) -> None:
    write_json(
        run.analysis_dir / "intelligence_fusion.json",
        {
            "schema_version": 1,
            "artifact_type": "intelligence_fusion",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "status": "ok",
            "records": records,
            "coverage": [],
            "counts": {"records": len(records), "warnings": 0, "errors": 0},
            "warnings": [],
            "errors": [],
            "source_artifacts": ["analysis/intelligence_fusion.json"],
        },
    )


def _write_material_inputs(run: RunContext) -> None:
    _write_records_artifact(run, "market_regime_assessment.json", "market_regime_assessment", [_regime()])
    _write_records_artifact(run, "risk_assessment.json", "risk_assessment", [_risk()])
    _write_records_artifact(run, "watch_triggers.json", "watch_triggers", [_watch_trigger()])
    _write_records_artifact(run, "event_intelligence_assessment.json", "event_intelligence_assessment", [_assessment()])
    write_json(
        run.analysis_dir / "decision_intelligence_delta.json",
        {
            "schema_version": 1,
            "artifact_type": "decision_intelligence_delta",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "status": "no_previous_run",
            "changes": [],
            "warnings": [],
            "errors": [],
            "source_artifacts": ["analysis/decision_recommendations.json"],
        },
    )


def _write_records_artifact(
    run: RunContext,
    filename: str,
    artifact_type: str,
    records: list[dict[str, Any]],
) -> None:
    write_json(
        run.analysis_dir / filename,
        {
            "schema_version": 1,
            "artifact_type": artifact_type,
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "records": records,
            "warnings": [],
            "errors": [],
            "source_artifacts": [f"analysis/{filename}"],
        },
    )


def _decision(
    *,
    action_level: str,
    decision_bias: str = "tentative_constructive",
) -> dict[str, Any]:
    return {
        "record_id": "decision_recommendation:binance:BTCUSDT:1d:2026-06-05T00:00:00Z",
        "source": "binance",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "latest_candle_time": "2026-06-05T00:00:00Z",
        "action_level": action_level,
        "decision_bias": decision_bias,
        "confidence": "medium",
        "status": "actionable",
        "recommended_actions": ["Use only as research decision support."],
        "do_not_do": ["Do not trade automatically."],
        "risk_conditions": ["risk_level=low; status=succeeded."],
        "downgrade_reasons": [],
        "invalidation_conditions": ["Recheck if price breaks invalidation."],
        "evidence": ["market signal supports action"],
        "conflicts": [],
        "warnings": [],
        "source_artifacts": ["analysis/decision_recommendations.json"],
    }


def _alert(*, priority: str) -> dict[str, Any]:
    return {
        "alert_decision_id": "alert_decision:BTCUSDT:1d:event-assessment-1",
        "status": "succeeded",
        "priority": priority,
        "scope": {
            "symbol": "BTCUSDT",
            "timeframe": "1d",
            "assessment_id": "event-assessment-1",
            "topic_ids": [],
            "event_signal_ids": [],
        },
        "attention_decision": "review_soon" if priority == "P1" else "record_without_interrupting",
        "decision_impact": "could_downgrade",
        "risk_effect": "risk_up",
        "watch_trigger_relevance": ["risk_escalation"],
        "requires_reassessment": priority in {"P0", "P1"},
        "requires_user_attention": priority in {"P0", "P1"},
        "reason": f"priority={priority}.",
        "evidence_strength": "medium",
        "downgrade_reasons": [],
        "suppression_reasons": [],
        "uncertainty": [],
        "warnings": [],
        "linked_event_assessment_ids": ["event-assessment-1"],
        "linked_decision_record_ids": ["decision_recommendation:binance:BTCUSDT:1d:2026-06-05T00:00:00Z"],
        "linked_watch_trigger_ids": [],
        "source_artifacts": ["analysis/alert_decisions.json"],
    }


def _fusion(
    *,
    state: str,
    confluence: str = "partial",
    conflict: str = "none",
    risk_override: str = "none",
    event_override: str = "none",
    evidence: list[str] | None = None,
    source_artifacts: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "fusion_record_id": "fusion:btcusdt:1d",
        "scope": {
            "symbol": "BTCUSDT",
            "timeframe": "1d",
            "asset": None,
            "chain": None,
            "region": None,
        },
        "state": state,
        "direction": "mixed" if state == "conflicting" else "bullish",
        "confidence": "medium",
        "confluence": {
            "state": confluence,
            "supporting_sources": 2,
            "independent_sources": 2,
            "source_layers": ["strategy", "factor"],
        },
        "conflict": {"state": conflict, "conflicting_sources": 1, "source_layers": ["factor"]},
        "risk_override": {"state": risk_override, "risk_level": "extreme", "reasons": ["risk block"]},
        "event_override": {"state": event_override, "severity": "critical", "reasons": ["event block"]},
        "outcome_feedback": {"state": "unknown", "source_records": 0},
        "evidence": evidence or ["fusion evidence"],
        "uncertainty": ["fusion uncertainty"],
        "warnings": ["fusion warning"] if state in {"conflicting", "insufficient_evidence"} else [],
        "errors": [],
        "source_artifacts": source_artifacts or ["analysis/intelligence_fusion.json"],
        "source_record_refs": [],
        "created_at": "2026-06-05T00:00:00Z",
    }


def _regime() -> dict[str, Any]:
    return {
        "record_id": "regime:BTCUSDT:1d",
        "source": "binance",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "regime": "trend_up",
        "confidence": "medium",
        "status": "succeeded",
        "evidence": ["regime evidence"],
        "uncertainty": [],
        "source_artifacts": ["analysis/market_regime_assessment.json"],
    }


def _risk() -> dict[str, Any]:
    return {
        "record_id": "risk:BTCUSDT:1d",
        "source": "binance",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "risk_level": "low",
        "status": "succeeded",
        "rising_risks": [],
        "blocking_risks": [],
        "signal_conflict_risks": [],
        "warnings": [],
        "source_artifacts": ["analysis/risk_assessment.json"],
    }


def _watch_trigger() -> dict[str, Any]:
    return {
        "trigger_id": "watch:BTCUSDT:1d",
        "source": "binance",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "type": "risk_escalation",
        "condition": "risk rises",
        "priority": "medium",
        "expected_decision_impact": "could_downgrade_or_block_stronger_action",
        "linked_decision_record_id": "decision_recommendation:binance:BTCUSDT:1d:2026-06-05T00:00:00Z",
        "evidence": ["watch evidence"],
        "source_artifacts": ["analysis/watch_triggers.json"],
    }


def _assessment() -> dict[str, Any]:
    return {
        "assessment_id": "event-assessment-1",
        "scope": {
            "symbol": "BTCUSDT",
            "timeframe": "1d",
            "topic_ids": [],
            "event_signal_ids": [],
        },
        "event_severity": "medium",
        "source_reliability": "medium",
        "market_response_relationship": "risk_up",
        "decision_impact": "could_downgrade",
        "confidence": "medium",
        "downgrade_reasons": [],
        "source_artifacts": ["analysis/event_intelligence_assessment.json"],
    }


def _decision_records(run: RunContext) -> list[dict[str, Any]]:
    return _json(run.analysis_dir / "decision_recommendations.json")["records"]


def _alert_records(run: RunContext) -> list[dict[str, Any]]:
    return _json(run.analysis_dir / "alert_decisions.json")["records"]


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest_count(run: RunContext, key: str) -> int:
    return int(run.manifest["counts"][key])
