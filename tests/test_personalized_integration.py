from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from halpha.decision.personalized_integration import integrate_personalized_risk_constraints
from halpha.pipeline import RunContext
from halpha.storage import write_json


def test_personalized_integration_blocks_disabled_asset_across_report_facing_artifacts(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_decision_artifact(run, [_decision(action_level="DO", decision_bias="constructive")])
    _write_watch_artifact(run, [_watch_trigger(priority="medium")])
    _write_alert_artifact(run, [_alert(priority="P1")])
    _write_constraints(run, [_constraint(state="disabled_asset_blocked", action="block", reason_codes=["disabled_asset"])])

    artifacts = integrate_personalized_risk_constraints({"quant": {"enabled": True}}, run)

    decision = _decision_records(run)[0]
    watch = _watch_records(run)[0]
    alert = _alert_records(run)[0]
    assert artifacts == [
        "analysis/decision_recommendations.json",
        "analysis/watch_triggers.json",
        "analysis/alert_decisions.json",
    ]
    assert decision["action_level"] == "NO_ACTION"
    assert decision["decision_bias"] == "personalized_blocked"
    assert decision["pre_personalized_action_level"] == "DO"
    assert decision["personalized_state"] == "disabled_asset_blocked"
    assert "personalized_disabled_asset" in decision["downgrade_reasons"]
    assert watch["priority"] == "low"
    assert watch["pre_personalized_expected_decision_impact"] == "could_downgrade_or_block_stronger_action"
    assert watch["expected_decision_impact"] == "personalized_constraint_blocks_stronger_action"
    assert alert["priority"] == "no_alert"
    assert alert["pre_personalized_priority"] == "P1"
    assert alert["requires_user_attention"] is False
    assert "personalized_disabled_asset" in alert["suppression_reasons"]
    assert run.manifest["counts"]["personalized_risk_decision_adjusted_records"] == 1
    assert run.manifest["counts"]["personalized_risk_watch_adjusted_records"] == 1
    assert run.manifest["counts"]["personalized_risk_alert_adjusted_records"] == 1


def test_personalized_integration_downgrades_risk_limit_without_blocking(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_decision_artifact(run, [_decision(action_level="DO", decision_bias="constructive")])
    _write_alert_artifact(run, [_alert(priority="P1")])
    _write_constraints(
        run,
        [_constraint(state="risk_limit_downgraded", action="downgrade", reason_codes=["risk_action_cap"])],
    )

    integrate_personalized_risk_constraints({}, run)

    decision = _decision_records(run)[0]
    alert = _alert_records(run)[0]
    assert decision["action_level"] == "WATCH"
    assert decision["decision_bias"] == "wait_for_personalized_constraint"
    assert decision["pre_personalized_action_level"] == "DO"
    assert "personalized_risk_action_cap" in decision["downgrade_reasons"]
    assert alert["priority"] == "P3"
    assert alert["pre_personalized_priority"] == "P1"
    assert "personalized_risk_action_cap" in alert["downgrade_reasons"]
    assert alert.get("suppression_reasons") == []


def test_personalized_integration_annotates_watchlist_without_changing_action(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_decision_artifact(run, [_decision(action_level="TRY_SMALL")])
    _write_constraints(
        run,
        [_constraint(state="watchlist_relevant", action="annotate", reason_codes=["watchlist_match"])],
    )

    integrate_personalized_risk_constraints({}, run)

    decision = _decision_records(run)[0]
    assert decision["action_level"] == "TRY_SMALL"
    assert decision["personalized_state"] == "watchlist_relevant"
    assert decision["personalized_action"] == "annotate"
    assert "pre_personalized_action_level" not in decision
    assert run.manifest["counts"]["personalized_risk_decision_linked_records"] == 1
    assert run.manifest["counts"]["personalized_risk_decision_adjusted_records"] == 0


def test_personalized_integration_general_constraint_is_traceable_noop(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_decision_artifact(run, [_decision(action_level="WATCH")])
    _write_alert_artifact(run, [_alert(priority="no_alert")])
    _write_constraints(run, [_constraint(state="general", action="none", reason_codes=["user_state_not_configured"])])

    integrate_personalized_risk_constraints({}, run)

    decision = _decision_records(run)[0]
    alert = _alert_records(run)[0]
    assert decision["action_level"] == "WATCH"
    assert decision["personalized_state"] == "general"
    assert "pre_personalized_action_level" not in decision
    assert alert["priority"] == "no_alert"
    assert alert["personalized_state"] == "general"
    assert run.manifest["counts"]["personalized_risk_decision_adjusted_records"] == 0
    assert run.manifest["counts"]["personalized_risk_alert_adjusted_records"] == 0


def test_personalized_integration_refreshes_decision_and_alert_material(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_decision_artifact(run, [_decision(action_level="DO", decision_bias="constructive")])
    _write_watch_artifact(run, [_watch_trigger(priority="medium")])
    _write_alert_artifact(run, [_alert(priority="P1")])
    _write_constraints(
        run,
        [_constraint(state="risk_limit_downgraded", action="downgrade", reason_codes=["risk_action_cap"])],
    )
    _write_material_inputs(run)
    (run.analysis_dir / "decision_intelligence_material.md").write_text("old decision material", encoding="utf-8")
    (run.analysis_dir / "alert_decision_material.md").write_text("old alert material", encoding="utf-8")

    artifacts = integrate_personalized_risk_constraints({"quant": {"enabled": True}}, run)

    decision_material = (run.analysis_dir / "decision_intelligence_material.md").read_text(encoding="utf-8")
    alert_material = (run.analysis_dir / "alert_decision_material.md").read_text(encoding="utf-8")
    assert "analysis/decision_intelligence_material.md" in artifacts
    assert "analysis/alert_decision_material.md" in artifacts
    assert "personalized_state: risk_limit_downgraded" in decision_material
    assert "pre_personalized_action_level: DO" in decision_material
    assert "personalized_context:" in alert_material
    assert "personalized_action: downgrade" in alert_material


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


def _write_watch_artifact(run: RunContext, records: list[dict[str, Any]]) -> None:
    _write_records_artifact(run, "watch_triggers.json", "watch_triggers", records)


def _write_alert_artifact(run: RunContext, records: list[dict[str, Any]]) -> None:
    _write_records_artifact(run, "alert_decisions.json", "alert_decisions", records)


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


def _write_constraints(run: RunContext, records: list[dict[str, Any]]) -> None:
    write_json(
        run.analysis_dir / "personalized_risk_constraints.json",
        {
            "schema_version": 1,
            "artifact_type": "personalized_risk_constraints",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "status": "ok",
            "records": records,
            "coverage": [],
            "counts": {"records": len(records), "warnings": 0, "errors": 0},
            "warnings": [],
            "errors": [],
            "source_artifacts": ["analysis/personalized_risk_constraints.json"],
        },
    )


def _constraint(*, state: str, action: str, reason_codes: list[str]) -> dict[str, Any]:
    return {
        "constraint_id": f"personalized:btcusdt:1d:{state}",
        "scope": {"symbol": "BTCUSDT", "timeframe": "1d"},
        "state": state,
        "action": action,
        "severity": "high" if action == "block" else "medium",
        "confidence": "high",
        "reason_codes": reason_codes,
        "matched_user_state": {"watchlist": True},
        "upstream_records": [],
        "evidence": [f"{state} evidence"],
        "uncertainty": [f"{state} uncertainty"],
        "warnings": [],
        "errors": [],
        "source_artifacts": ["analysis/personalized_risk_constraints.json"],
    }


def _decision(*, action_level: str, decision_bias: str = "tentative_constructive") -> dict[str, Any]:
    return {
        "record_id": "decision_recommendation:binance:BTCUSDT:1d:2026-06-05T00:00:00Z",
        "source": "binance",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "latest_candle_time": "2026-06-05T00:00:00Z",
        "action_level": action_level,
        "decision_bias": decision_bias,
        "confidence": "medium",
        "status": "actionable" if action_level in {"DO", "TRY_SMALL"} else "watch",
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


def _watch_trigger(*, priority: str) -> dict[str, Any]:
    return {
        "trigger_id": "watch_trigger:binance:BTCUSDT:1d:risk_escalation:2026-06-05T00:00:00Z",
        "source": "binance",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "type": "risk_escalation",
        "condition": "risk rises",
        "priority": priority,
        "expected_decision_impact": "could_downgrade_or_block_stronger_action",
        "linked_decision_record_id": "decision_recommendation:binance:BTCUSDT:1d:2026-06-05T00:00:00Z",
        "evidence": ["watch evidence"],
        "source_artifacts": ["analysis/watch_triggers.json"],
    }


def _alert(*, priority: str) -> dict[str, Any]:
    return {
        "alert_decision_id": "alert_decision:BTCUSDT:1d:event-assessment-1",
        "status": "succeeded",
        "priority": priority,
        "scope": {"symbol": "BTCUSDT", "timeframe": "1d", "assessment_id": "event-assessment-1"},
        "attention_decision": "no_alert" if priority == "no_alert" else "review_soon",
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
        "linked_watch_trigger_ids": ["watch_trigger:binance:BTCUSDT:1d:risk_escalation:2026-06-05T00:00:00Z"],
        "source_artifacts": ["analysis/alert_decisions.json"],
    }


def _write_material_inputs(run: RunContext) -> None:
    _write_records_artifact(run, "market_regime_assessment.json", "market_regime_assessment", [_regime()])
    _write_records_artifact(run, "risk_assessment.json", "risk_assessment", [_risk()])
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


def _assessment() -> dict[str, Any]:
    return {
        "assessment_id": "event-assessment-1",
        "scope": {"symbol": "BTCUSDT", "timeframe": "1d", "topic_ids": [], "event_signal_ids": []},
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


def _watch_records(run: RunContext) -> list[dict[str, Any]]:
    return _json(run.analysis_dir / "watch_triggers.json")["records"]


def _alert_records(run: RunContext) -> list[dict[str, Any]]:
    return _json(run.analysis_dir / "alert_decisions.json")["records"]


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
