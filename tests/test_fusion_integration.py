from __future__ import annotations

from typing import Any

from halpha.decision.fusion_integration import (
    apply_fusion_to_alert_records,
    apply_fusion_to_decision_records,
)


def test_fusion_apply_attaches_supportive_context_without_upgrading() -> None:
    fusion = _fusion_artifact([_fusion(state="supportive", confluence="aligned")])

    decision_result = apply_fusion_to_decision_records([_decision(action_level="TRY_SMALL")], fusion)
    alert_result = apply_fusion_to_alert_records([_alert(priority="P2")], fusion)

    decision = decision_result["records"][0]
    alert = alert_result["records"][0]
    assert decision_result["status"] == "succeeded"
    assert alert_result["status"] == "succeeded"
    assert decision["action_level"] == "TRY_SMALL"
    assert decision["fusion_state"] == "supportive"
    assert decision["fusion_record_id"] == "fusion:btcusdt:1d"
    assert "pre_fusion_action_level" not in decision
    assert alert["priority"] == "P2"
    assert alert["fusion_attention_annotation"] == "fusion_aligned"
    assert alert["fusion_state"] == "supportive"
    assert decision_result["decision_linked_records"] == 1
    assert alert_result["alert_linked_records"] == 1


def test_fusion_apply_downgrades_decision_on_severe_conflict() -> None:
    result = apply_fusion_to_decision_records(
        [_decision(action_level="DO", decision_bias="constructive")],
        _fusion_artifact([_fusion(state="conflicting", conflict="severe")]),
    )

    decision = result["records"][0]
    assert decision["action_level"] == "WATCH"
    assert decision["decision_bias"] == "wait_for_conflict_resolution"
    assert decision["pre_fusion_action_level"] == "DO"
    assert "fusion_severe_conflict" in decision["downgrade_reasons"]
    assert "fusion_conflict_state=severe." in decision["conflicts"]
    assert result["decision_adjusted_records"] == 1


def test_fusion_apply_downgrades_decision_on_lifecycle_retirement_context() -> None:
    result = apply_fusion_to_decision_records(
        [_decision(action_level="DO", decision_bias="constructive")],
        _fusion_artifact(
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
        ),
    )

    decision = result["records"][0]
    assert decision["action_level"] == "WATCH"
    assert decision["pre_fusion_action_level"] == "DO"
    assert "fusion_severe_conflict" in decision["downgrade_reasons"]
    assert "analysis/strategy_lifecycle_state.json" in decision["source_artifacts"]
    assert "analysis/strategy_lifecycle_state.json" in decision["fusion_source_artifacts"]
    assert any("strategy_lifecycle state=retired" in item for item in decision["fusion_evidence"])


def test_fusion_apply_blocks_decision_on_risk_override() -> None:
    result = apply_fusion_to_decision_records(
        [_decision(action_level="TRY_SMALL")],
        _fusion_artifact([_fusion(state="risk_blocked", risk_override="block")]),
    )

    decision = result["records"][0]
    assert decision["action_level"] == "NO_ACTION"
    assert decision["decision_bias"] == "risk_blocked"
    assert decision["status"] == "risk_blocked"
    assert "fusion_risk_override_block" in decision["downgrade_reasons"]
    assert any("fusion_risk_override_state=block" in item for item in decision["risk_conditions"])


def test_fusion_apply_blocks_decision_on_event_override() -> None:
    result = apply_fusion_to_decision_records(
        [_decision(action_level="TRY_SMALL")],
        _fusion_artifact([_fusion(state="event_overridden", event_override="block")]),
    )

    decision = result["records"][0]
    assert decision["action_level"] == "NO_ACTION"
    assert decision["status"] == "no_action"
    assert "fusion_event_override_block" in decision["downgrade_reasons"]
    assert any("fusion_event_override_state=block" in item for item in decision["risk_conditions"])


def test_fusion_apply_downgrades_insufficient_alert_attention() -> None:
    result = apply_fusion_to_alert_records(
        [_alert(priority="P1")],
        _fusion_artifact([_fusion(state="insufficient_evidence", confluence="none")]),
    )

    alert = result["records"][0]
    assert alert["priority"] == "P3"
    assert alert["pre_fusion_priority"] == "P1"
    assert alert["requires_user_attention"] is False
    assert alert["requires_reassessment"] is True
    assert alert["fusion_attention_annotation"] == "insufficient_evidence_watch_only"
    assert "fusion_insufficient_evidence_watch_only" in alert["downgrade_reasons"]
    assert result["alert_adjusted_records"] == 1


def test_fusion_apply_skips_when_artifact_is_absent() -> None:
    records = [_decision(action_level="TRY_SMALL")]

    result = apply_fusion_to_decision_records(records, None)

    assert result["status"] == "skipped"
    assert result["records"] == records
    assert result["decision_linked_records"] == 0


def _fusion_artifact(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "intelligence_fusion",
        "run_id": "test-run",
        "created_at": "2026-06-05T00:00:00Z",
        "status": "ok",
        "records": records,
        "coverage": [],
        "counts": {"records": len(records), "warnings": 0, "errors": 0},
        "warnings": [],
        "errors": [],
        "source_artifacts": ["analysis/intelligence_fusion.json"],
    }


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
