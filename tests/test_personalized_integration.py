from __future__ import annotations

from typing import Any

from halpha.decision.personalized_integration import (
    apply_personalized_constraints_to_alert_records,
    apply_personalized_constraints_to_decision_records,
    apply_personalized_constraints_to_watch_records,
)


def test_personalized_apply_blocks_disabled_asset_across_report_facing_records() -> None:
    constraints = _constraints_artifact(
        [_constraint(state="disabled_asset_blocked", action="block", reason_codes=["disabled_asset"])]
    )

    decision_result = apply_personalized_constraints_to_decision_records(
        [_decision(action_level="DO", decision_bias="constructive")],
        constraints,
    )
    watch_result = apply_personalized_constraints_to_watch_records([_watch_trigger(priority="medium")], constraints)
    alert_result = apply_personalized_constraints_to_alert_records([_alert(priority="P1")], constraints)

    decision = decision_result["records"][0]
    watch = watch_result["records"][0]
    alert = alert_result["records"][0]
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
    assert decision_result["decision_adjusted_records"] == 1
    assert watch_result["watch_adjusted_records"] == 1
    assert alert_result["alert_adjusted_records"] == 1


def test_personalized_apply_downgrades_risk_limit_without_blocking() -> None:
    constraints = _constraints_artifact(
        [_constraint(state="risk_limit_downgraded", action="downgrade", reason_codes=["risk_action_cap"])]
    )

    decision_result = apply_personalized_constraints_to_decision_records(
        [_decision(action_level="DO", decision_bias="constructive")],
        constraints,
    )
    alert_result = apply_personalized_constraints_to_alert_records([_alert(priority="P1")], constraints)

    decision = decision_result["records"][0]
    alert = alert_result["records"][0]
    assert decision["action_level"] == "WATCH"
    assert decision["decision_bias"] == "wait_for_personalized_constraint"
    assert decision["pre_personalized_action_level"] == "DO"
    assert "personalized_risk_action_cap" in decision["downgrade_reasons"]
    assert alert["priority"] == "P3"
    assert alert["pre_personalized_priority"] == "P1"
    assert "personalized_risk_action_cap" in alert["downgrade_reasons"]
    assert alert.get("suppression_reasons") == []


def test_personalized_apply_annotates_watchlist_without_changing_action() -> None:
    result = apply_personalized_constraints_to_decision_records(
        [_decision(action_level="TRY_SMALL")],
        _constraints_artifact(
            [_constraint(state="watchlist_relevant", action="annotate", reason_codes=["watchlist_match"])]
        ),
    )

    decision = result["records"][0]
    assert decision["action_level"] == "TRY_SMALL"
    assert decision["personalized_state"] == "watchlist_relevant"
    assert decision["personalized_action"] == "annotate"
    assert "pre_personalized_action_level" not in decision
    assert result["decision_linked_records"] == 1
    assert result["decision_adjusted_records"] == 0


def test_personalized_apply_general_constraint_is_traceable_noop() -> None:
    constraints = _constraints_artifact(
        [_constraint(state="general", action="none", reason_codes=["user_state_not_configured"])]
    )

    decision_result = apply_personalized_constraints_to_decision_records([_decision(action_level="WATCH")], constraints)
    alert_result = apply_personalized_constraints_to_alert_records([_alert(priority="no_alert")], constraints)

    decision = decision_result["records"][0]
    alert = alert_result["records"][0]
    assert decision["action_level"] == "WATCH"
    assert decision["personalized_state"] == "general"
    assert "pre_personalized_action_level" not in decision
    assert alert["priority"] == "no_alert"
    assert alert["personalized_state"] == "general"
    assert decision_result["decision_adjusted_records"] == 0
    assert alert_result["alert_adjusted_records"] == 0


def test_personalized_apply_ignores_risk_action_cap_when_final_record_is_already_capped() -> None:
    result = apply_personalized_constraints_to_decision_records(
        [_decision(action_level="WATCH")],
        _constraints_artifact(
            [
                _constraint(
                    state="risk_limit_downgraded",
                    action="downgrade",
                    reason_codes=["risk_action_cap"],
                    constraint_policy={"risk": {"max_action_level": "WATCH"}},
                )
            ]
        ),
    )

    decision = result["records"][0]
    assert decision["action_level"] == "WATCH"
    assert decision["personalized_action"] == "downgrade"
    assert decision["personalized_effective_action"] == "annotate"
    assert decision["personalized_adjustment_reasons"] == []
    assert "pre_personalized_action_level" not in decision
    assert result["decision_adjusted_records"] == 0


def test_personalized_apply_skips_when_artifact_is_absent() -> None:
    records = [_decision(action_level="TRY_SMALL")]

    result = apply_personalized_constraints_to_decision_records(records, None)

    assert result["status"] == "skipped"
    assert result["records"] == records
    assert result["decision_linked_records"] == 0


def _constraints_artifact(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "personalized_risk_constraints",
        "run_id": "test-run",
        "created_at": "2026-06-05T00:00:00Z",
        "status": "ok",
        "records": records,
        "coverage": [],
        "counts": {"records": len(records), "warnings": 0, "errors": 0},
        "warnings": [],
        "errors": [],
        "source_artifacts": ["analysis/personalized_risk_constraints.json"],
    }


def _constraint(
    *,
    state: str,
    action: str,
    reason_codes: list[str],
    constraint_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "constraint_id": f"personalized:btcusdt:1d:{state}",
        "scope": {"symbol": "BTCUSDT", "timeframe": "1d"},
        "state": state,
        "action": action,
        "severity": "high" if action == "block" else "medium",
        "confidence": "high",
        "reason_codes": reason_codes,
        "constraint_policy": constraint_policy or {},
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
