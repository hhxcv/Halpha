from __future__ import annotations

import json
from datetime import UTC, datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from halpha.pipeline import PipelineError, RunContext
from halpha.storage import write_json


STAGE_NAME = "integrate_intelligence_fusion"
INTELLIGENCE_FUSION_ARTIFACT = "analysis/intelligence_fusion.json"
DECISION_RECOMMENDATIONS_ARTIFACT = "analysis/decision_recommendations.json"
ALERT_DECISIONS_ARTIFACT = "analysis/alert_decisions.json"
DECISION_INTELLIGENCE_MATERIAL_ARTIFACT = "analysis/decision_intelligence_material.md"
ALERT_DECISION_MATERIAL_ARTIFACT = "analysis/alert_decision_material.md"

ACTIONABLE_ACTION_LEVELS = {
    "STRONG_DO",
    "DO",
    "TRY_SMALL",
    "AVOID",
    "EXIT_OR_REDUCE",
    "HEDGE_OR_PROTECT",
}
ATTENTION_DECISIONS = {
    "P0": "interrupt_now",
    "P1": "review_soon",
    "P2": "record_without_interrupting",
    "P3": "archive_as_noise",
    "no_alert": "no_alert",
    "unknown": "unknown",
}


def integrate_intelligence_fusion(config: dict[str, Any], run: RunContext) -> list[str]:
    fusion_artifact = _read_optional_artifact(
        run.analysis_dir / "intelligence_fusion.json",
        INTELLIGENCE_FUSION_ARTIFACT,
        records_key="records",
    )
    if fusion_artifact is None:
        _record_manifest(run, status="skipped", decision_records=[], alert_records=[], warnings=[], errors=[])
        return []

    fusion_records = _dict_list(fusion_artifact.get("records"))
    fusion_index = _FusionIndex(fusion_records)
    decision_artifact = _read_optional_artifact(
        run.analysis_dir / "decision_recommendations.json",
        DECISION_RECOMMENDATIONS_ARTIFACT,
        records_key="records",
    )
    alert_artifact = _read_optional_artifact(
        run.analysis_dir / "alert_decisions.json",
        ALERT_DECISIONS_ARTIFACT,
        records_key="records",
    )

    artifacts: list[str] = []
    warnings: list[str] = []
    errors: list[dict[str, Any]] = []
    decision_records: list[dict[str, Any]] = []
    alert_records: list[dict[str, Any]] = []

    if decision_artifact is not None:
        decision_result = _integrate_decision_records(decision_artifact, fusion_index)
        decision_records = decision_result["records"]
        warnings.extend(decision_result["warnings"])
        decision_artifact["records"] = decision_records
        decision_artifact["source_artifacts"] = _unique_strings(
            [
                DECISION_RECOMMENDATIONS_ARTIFACT,
                INTELLIGENCE_FUSION_ARTIFACT,
                *_string_list(decision_artifact.get("source_artifacts")),
                *_string_list(fusion_artifact.get("source_artifacts")),
            ]
        )
        decision_artifact["warnings"] = _unique_strings(
            [*_string_list(decision_artifact.get("warnings")), *decision_result["warnings"]]
        )
        decision_artifact["created_at"] = _created_at(fusion_artifact)
        write_json(run.analysis_dir / "decision_recommendations.json", decision_artifact)
        artifacts.append(DECISION_RECOMMENDATIONS_ARTIFACT)
        _refresh_decision_recommendation_counts(run, decision_records)

    if alert_artifact is not None:
        alert_result = _integrate_alert_records(alert_artifact, fusion_index)
        alert_records = alert_result["records"]
        warnings.extend(alert_result["warnings"])
        alert_artifact["records"] = alert_records
        alert_artifact["source_artifacts"] = _unique_strings(
            [
                ALERT_DECISIONS_ARTIFACT,
                INTELLIGENCE_FUSION_ARTIFACT,
                *_string_list(alert_artifact.get("source_artifacts")),
                *_string_list(fusion_artifact.get("source_artifacts")),
            ]
        )
        alert_artifact["warnings"] = _unique_strings(
            [*_string_list(alert_artifact.get("warnings")), *alert_result["warnings"]]
        )
        alert_artifact["coverage"] = _alert_coverage(alert_records)
        alert_artifact["created_at"] = _created_at(fusion_artifact)
        write_json(run.analysis_dir / "alert_decisions.json", alert_artifact)
        artifacts.append(ALERT_DECISIONS_ARTIFACT)
        _refresh_alert_decision_counts(run, alert_records)

    artifacts.extend(_refresh_materials(config, run, decision_changed=bool(decision_records), alert_changed=bool(alert_records)))
    _record_manifest(
        run,
        status="succeeded",
        decision_records=decision_records,
        alert_records=alert_records,
        warnings=warnings,
        errors=errors,
    )
    return _unique_strings(artifacts)


class _FusionIndex:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.by_scope: dict[tuple[str | None, str | None], dict[str, Any]] = {}
        for record in sorted(records, key=lambda item: str(item.get("fusion_record_id") or "")):
            scope = _dict(record.get("scope"))
            key = (_scope_value(scope.get("symbol")), _scope_value(scope.get("timeframe")))
            self.by_scope.setdefault(key, record)

    def match(self, *, symbol: Any, timeframe: Any, allow_symbol_only: bool = False) -> dict[str, Any] | None:
        symbol_value = _scope_value(symbol)
        timeframe_value = _scope_value(timeframe)
        for key in ((symbol_value, timeframe_value),):
            record = self.by_scope.get(key)
            if record is not None:
                return record
        if allow_symbol_only and symbol_value is not None:
            return self.by_scope.get((symbol_value, None))
        return None


def _integrate_decision_records(artifact: dict[str, Any], fusion_index: _FusionIndex) -> dict[str, Any]:
    records = []
    warnings: list[str] = []
    for original in _dict_list(artifact.get("records")):
        record = dict(original)
        fusion = fusion_index.match(symbol=record.get("symbol"), timeframe=record.get("timeframe"))
        if fusion is None:
            records.append(record)
            continue
        context = _fusion_context(fusion)
        _apply_fusion_fields(record, context)
        decision_warnings = _apply_decision_adjustments(record, context)
        warnings.extend(decision_warnings)
        records.append(record)
    return {"records": records, "warnings": _unique_strings(warnings)}


def _integrate_alert_records(artifact: dict[str, Any], fusion_index: _FusionIndex) -> dict[str, Any]:
    records = []
    warnings: list[str] = []
    for original in _dict_list(artifact.get("records")):
        record = dict(original)
        scope = _dict(record.get("scope"))
        fusion = fusion_index.match(
            symbol=scope.get("symbol"),
            timeframe=scope.get("timeframe"),
            allow_symbol_only=True,
        )
        if fusion is None:
            records.append(record)
            continue
        context = _fusion_context(fusion)
        _apply_fusion_fields(record, context)
        alert_warnings = _apply_alert_adjustments(record, context)
        warnings.extend(alert_warnings)
        records.append(record)
    return {"records": records, "warnings": _unique_strings(warnings)}


def _apply_fusion_fields(record: dict[str, Any], context: dict[str, Any]) -> None:
    record["fusion_record_id"] = context["fusion_record_id"]
    record["fusion_state"] = context["fusion_state"]
    record["fusion_conflict_state"] = context["fusion_conflict_state"]
    record["fusion_risk_override_state"] = context["fusion_risk_override_state"]
    record["fusion_event_override_state"] = context["fusion_event_override_state"]
    record["fusion_outcome_feedback_state"] = context["fusion_outcome_feedback_state"]
    record["fusion_confidence"] = context["fusion_confidence"]
    record["fusion_evidence"] = context["fusion_evidence"]
    record["fusion_uncertainty"] = context["fusion_uncertainty"]
    record["fusion_source_artifacts"] = context["fusion_source_artifacts"]
    record["source_artifacts"] = _unique_strings(
        [
            *_string_list(record.get("source_artifacts")),
            INTELLIGENCE_FUSION_ARTIFACT,
            *context["fusion_source_artifacts"],
        ]
    )


def _apply_decision_adjustments(record: dict[str, Any], context: dict[str, Any]) -> list[str]:
    reasons = _fusion_decision_reasons(context)
    warnings: list[str] = []
    original_action = _text(record.get("action_level"), fallback="NO_ACTION")
    new_action = _decision_action_after_fusion(original_action, context)
    record["fusion_adjustment_reasons"] = _unique_strings(
        [*_string_list(record.get("fusion_adjustment_reasons")), *reasons]
    )
    record["risk_conditions"] = _unique_strings(
        [
            *_string_list(record.get("risk_conditions")),
            *_fusion_risk_conditions(context),
        ]
    )
    record["conflicts"] = _unique_strings(
        [
            *_string_list(record.get("conflicts")),
            *_fusion_conflicts(context),
        ]
    )
    record["warnings"] = _unique_strings(
        [
            *_string_list(record.get("warnings")),
            *_fusion_decision_warnings(context),
        ]
    )
    record["do_not_do"] = _unique_strings(
        [
            *_string_list(record.get("do_not_do")),
            *_fusion_do_not_do(context),
        ]
    )
    if new_action != original_action:
        record["pre_fusion_action_level"] = original_action
        record["pre_fusion_decision_bias"] = record.get("decision_bias")
        record["pre_fusion_recommended_actions"] = _string_list(record.get("recommended_actions"))
        record["pre_fusion_invalidation_conditions"] = _string_list(record.get("invalidation_conditions"))
        record["action_level"] = new_action
        record["decision_bias"] = _decision_bias_after_fusion(new_action, context)
        record["confidence"] = "low" if new_action in {"NO_ACTION", "WATCH"} else record.get("confidence", "unknown")
        record["status"] = _decision_status_after_fusion(new_action, context)
        record["recommended_actions"] = _recommended_actions_after_fusion(new_action, record, context)
        record["invalidation_conditions"] = [] if new_action in {"NO_ACTION", "WATCH"} else _string_list(record.get("invalidation_conditions"))
        record["downgrade_reasons"] = _unique_strings(
            [*_string_list(record.get("downgrade_reasons")), *reasons]
        )
        warnings.append("fusion_adjusted_decision_recommendation")
    return warnings


def _apply_alert_adjustments(record: dict[str, Any], context: dict[str, Any]) -> list[str]:
    annotation = _alert_annotation(context)
    warnings: list[str] = []
    record["fusion_attention_annotation"] = annotation
    record["uncertainty"] = _unique_strings(
        [
            *_string_list(record.get("uncertainty")),
            *_fusion_alert_uncertainty(context),
        ]
    )
    record["warnings"] = _unique_strings(
        [
            *_string_list(record.get("warnings")),
            *_fusion_alert_warnings(context),
        ]
    )
    if annotation in {"conflict_watch_only", "insufficient_evidence_watch_only", "degraded_watch_only"}:
        original_priority = _text(record.get("priority"), fallback="unknown")
        if original_priority in {"P0", "P1", "P2"}:
            record["pre_fusion_priority"] = original_priority
            record["priority"] = "P3"
            record["attention_decision"] = ATTENTION_DECISIONS["P3"]
            record["requires_user_attention"] = False
            record["requires_reassessment"] = True
            record["status"] = "degraded"
            record["reason"] = (
                _text(record.get("reason"), fallback="")
                + " fusion downgraded user attention to watch-only because evidence is not decision-grade."
            ).strip()
            warnings.append("fusion_downgraded_alert_attention")
        record["downgrade_reasons"] = _unique_strings(
            [*_string_list(record.get("downgrade_reasons")), f"fusion_{annotation}"]
        )
    elif annotation in {"risk_blocked_reassessment", "event_override_reassessment"}:
        record["requires_reassessment"] = True
        record["downgrade_reasons"] = _unique_strings(
            [*_string_list(record.get("downgrade_reasons")), f"fusion_{annotation}"]
        )
    return warnings


def _fusion_context(record: dict[str, Any]) -> dict[str, Any]:
    confluence = _dict(record.get("confluence"))
    conflict = _dict(record.get("conflict"))
    risk_override = _dict(record.get("risk_override"))
    event_override = _dict(record.get("event_override"))
    outcome_feedback = _dict(record.get("outcome_feedback"))
    return {
        "fusion_record_id": _text(record.get("fusion_record_id"), fallback="fusion:unknown"),
        "fusion_state": _text(record.get("state"), fallback="unknown"),
        "fusion_direction": _text(record.get("direction"), fallback="unknown"),
        "fusion_confidence": _text(record.get("confidence"), fallback="unknown"),
        "fusion_confluence_state": _text(confluence.get("state"), fallback="unknown"),
        "fusion_conflict_state": _text(conflict.get("state"), fallback="unknown"),
        "fusion_risk_override_state": _text(risk_override.get("state"), fallback="unknown"),
        "fusion_event_override_state": _text(event_override.get("state"), fallback="unknown"),
        "fusion_outcome_feedback_state": _text(outcome_feedback.get("state"), fallback="unknown"),
        "fusion_evidence": _string_list(record.get("evidence"))[:8],
        "fusion_uncertainty": _string_list(record.get("uncertainty"))[:8],
        "fusion_warnings": _string_list(record.get("warnings"))[:8],
        "fusion_source_artifacts": _unique_strings(
            [INTELLIGENCE_FUSION_ARTIFACT, *_string_list(record.get("source_artifacts"))]
        ),
    }


def _fusion_decision_reasons(context: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if context["fusion_risk_override_state"] == "block" or context["fusion_state"] == "risk_blocked":
        reasons.append("fusion_risk_override_block")
    if context["fusion_event_override_state"] == "block" or context["fusion_state"] == "event_overridden":
        reasons.append("fusion_event_override_block")
    if context["fusion_conflict_state"] == "severe" or context["fusion_state"] == "conflicting":
        reasons.append("fusion_severe_conflict")
    if context["fusion_state"] == "insufficient_evidence":
        reasons.append("fusion_insufficient_evidence")
    if context["fusion_state"] == "degraded":
        reasons.append("fusion_degraded_evidence")
    return reasons


def _decision_action_after_fusion(action_level: str, context: dict[str, Any]) -> str:
    if context["fusion_risk_override_state"] == "block" or context["fusion_state"] == "risk_blocked":
        return "NO_ACTION"
    if context["fusion_event_override_state"] == "block" or context["fusion_state"] == "event_overridden":
        return "NO_ACTION"
    if action_level in ACTIONABLE_ACTION_LEVELS and (
        context["fusion_conflict_state"] == "severe"
        or context["fusion_state"] in {"conflicting", "insufficient_evidence", "degraded"}
    ):
        return "WATCH"
    return action_level


def _decision_bias_after_fusion(action_level: str, context: dict[str, Any]) -> str:
    if context["fusion_risk_override_state"] == "block" or context["fusion_state"] == "risk_blocked":
        return "risk_blocked"
    if action_level == "WATCH" and context["fusion_conflict_state"] == "severe":
        return "wait_for_conflict_resolution"
    if action_level == "WATCH":
        return "wait_for_confirmation"
    if action_level == "NO_ACTION":
        return "no_action"
    return "tentative_constructive" if action_level == "TRY_SMALL" else _text(action_level, fallback="unknown").lower()


def _decision_status_after_fusion(action_level: str, context: dict[str, Any]) -> str:
    if action_level == "NO_ACTION" and (
        context["fusion_risk_override_state"] == "block" or context["fusion_state"] == "risk_blocked"
    ):
        return "risk_blocked"
    if action_level == "WATCH":
        return "watch"
    if action_level == "NO_ACTION":
        return "no_action"
    return "actionable"


def _recommended_actions_after_fusion(action_level: str, record: dict[str, Any], context: dict[str, Any]) -> list[str]:
    symbol = _text(record.get("symbol"), fallback="this market")
    if action_level == "NO_ACTION":
        return [
            f"Do not upgrade {symbol} until fusion block conditions clear.",
            f"Review {context['fusion_record_id']} before reusing pre-fusion action language.",
        ]
    if action_level == "WATCH":
        return [
            f"Watch {symbol} until fusion conflict, degraded evidence, or insufficient evidence clears.",
            f"Recheck {context['fusion_record_id']} before considering stronger action language.",
        ]
    return _string_list(record.get("recommended_actions"))


def _fusion_risk_conditions(context: dict[str, Any]) -> list[str]:
    conditions = []
    if context["fusion_risk_override_state"] not in {"none", "unknown"}:
        conditions.append(f"fusion_risk_override_state={context['fusion_risk_override_state']}.")
    if context["fusion_event_override_state"] not in {"none", "unknown"}:
        conditions.append(f"fusion_event_override_state={context['fusion_event_override_state']}.")
    if context["fusion_outcome_feedback_state"] not in {"unknown", "supportive"}:
        conditions.append(f"fusion_outcome_feedback_state={context['fusion_outcome_feedback_state']}.")
    return conditions


def _fusion_conflicts(context: dict[str, Any]) -> list[str]:
    if context["fusion_conflict_state"] in {"severe", "material"}:
        return [f"fusion_conflict_state={context['fusion_conflict_state']}."]
    return []


def _fusion_decision_warnings(context: dict[str, Any]) -> list[str]:
    warnings = list(context["fusion_warnings"])
    if _fusion_decision_reasons(context):
        warnings.append("Decision recommendation carries conservative fusion adjustment context.")
    return _unique_strings(warnings)


def _fusion_do_not_do(context: dict[str, Any]) -> list[str]:
    guidance = []
    if _fusion_decision_reasons(context):
        guidance.append("Do not override fusion downgrade or block context with stronger action language.")
    if context["fusion_state"] in {"insufficient_evidence", "degraded"}:
        guidance.append("Do not treat insufficient or degraded fusion evidence as confirmation.")
    return guidance


def _alert_annotation(context: dict[str, Any]) -> str:
    if context["fusion_risk_override_state"] == "block" or context["fusion_state"] == "risk_blocked":
        return "risk_blocked_reassessment"
    if context["fusion_event_override_state"] == "block" or context["fusion_state"] == "event_overridden":
        return "event_override_reassessment"
    if context["fusion_conflict_state"] == "severe" or context["fusion_state"] == "conflicting":
        return "conflict_watch_only"
    if context["fusion_state"] == "insufficient_evidence":
        return "insufficient_evidence_watch_only"
    if context["fusion_state"] == "degraded":
        return "degraded_watch_only"
    if context["fusion_confluence_state"] == "aligned":
        return "fusion_aligned"
    return "fusion_context_attached"


def _fusion_alert_uncertainty(context: dict[str, Any]) -> list[str]:
    values = list(context["fusion_uncertainty"])
    if _alert_annotation(context).endswith("watch_only"):
        values.append("Fusion evidence is not strong enough for user-attention escalation.")
    if _alert_annotation(context).endswith("reassessment"):
        values.append("Fusion evidence requires reassessment but does not send or schedule alerts.")
    return _unique_strings(values)


def _fusion_alert_warnings(context: dict[str, Any]) -> list[str]:
    warnings = list(context["fusion_warnings"])
    if _alert_annotation(context) != "fusion_aligned":
        warnings.append("Alert decision carries fusion context; priority remains deterministic.")
    return _unique_strings(warnings)


def _refresh_materials(
    config: dict[str, Any],
    run: RunContext,
    *,
    decision_changed: bool,
    alert_changed: bool,
) -> list[str]:
    artifacts: list[str] = []
    if decision_changed and (run.analysis_dir / "decision_intelligence_material.md").is_file():
        from halpha.decision.decision_intelligence import build_decision_intelligence_material

        artifacts.extend(build_decision_intelligence_material(config, run))
    if alert_changed and (run.analysis_dir / "alert_decision_material.md").is_file():
        from halpha.analysis.alert_decision_material import build_alert_decision_material

        artifacts.extend(build_alert_decision_material(config, run))
    return artifacts


def _refresh_decision_recommendation_counts(run: RunContext, records: list[dict[str, Any]]) -> None:
    run.manifest["counts"]["decision_recommendation_records"] = len(records)
    run.manifest["counts"]["decision_recommendation_actionable_records"] = sum(
        1 for record in records if record.get("action_level") in ACTIONABLE_ACTION_LEVELS
    )
    run.manifest["counts"]["decision_recommendation_non_actionable_records"] = sum(
        1 for record in records if record.get("action_level") not in ACTIONABLE_ACTION_LEVELS
    )
    run.manifest["counts"]["decision_recommendation_fusion_linked_records"] = sum(
        1 for record in records if record.get("fusion_record_id")
    )
    run.manifest["counts"]["decision_recommendation_fusion_adjusted_records"] = sum(
        1 for record in records if record.get("pre_fusion_action_level")
    )


def _refresh_alert_decision_counts(run: RunContext, records: list[dict[str, Any]]) -> None:
    priority = _count_by(records, "priority")
    run.manifest["counts"]["alert_decision_records"] = len(records)
    run.manifest["counts"]["alert_decision_p0_records"] = priority.get("P0", 0)
    run.manifest["counts"]["alert_decision_p1_records"] = priority.get("P1", 0)
    run.manifest["counts"]["alert_decision_p2_records"] = priority.get("P2", 0)
    run.manifest["counts"]["alert_decision_p3_records"] = priority.get("P3", 0)
    run.manifest["counts"]["alert_decision_no_alert_records"] = priority.get("no_alert", 0)
    run.manifest["counts"]["alert_decision_fusion_linked_records"] = sum(
        1 for record in records if record.get("fusion_record_id")
    )
    run.manifest["counts"]["alert_decision_fusion_adjusted_records"] = sum(
        1 for record in records if record.get("pre_fusion_priority")
    )


def _record_manifest(
    run: RunContext,
    *,
    status: str,
    decision_records: list[dict[str, Any]],
    alert_records: list[dict[str, Any]],
    warnings: list[str],
    errors: list[dict[str, Any]],
) -> None:
    decision_linked = sum(1 for record in decision_records if record.get("fusion_record_id"))
    alert_linked = sum(1 for record in alert_records if record.get("fusion_record_id"))
    decision_adjusted = sum(1 for record in decision_records if record.get("pre_fusion_action_level"))
    alert_adjusted = sum(1 for record in alert_records if record.get("pre_fusion_priority"))
    run.manifest["counts"]["intelligence_fusion_decision_linked_records"] = decision_linked
    run.manifest["counts"]["intelligence_fusion_alert_linked_records"] = alert_linked
    run.manifest["counts"]["intelligence_fusion_decision_adjusted_records"] = decision_adjusted
    run.manifest["counts"]["intelligence_fusion_alert_adjusted_records"] = alert_adjusted
    run.manifest["counts"]["intelligence_fusion_integration_warnings"] = len(warnings)
    run.manifest["counts"]["intelligence_fusion_integration_errors"] = len(errors)
    run.manifest["intelligence_fusion_integration"] = {
        "status": status,
        "source_artifact": INTELLIGENCE_FUSION_ARTIFACT if status == "succeeded" else None,
        "decision_records": len(decision_records),
        "decision_linked_records": decision_linked,
        "decision_adjusted_records": decision_adjusted,
        "alert_records": len(alert_records),
        "alert_linked_records": alert_linked,
        "alert_adjusted_records": alert_adjusted,
        "warnings": len(warnings),
        "errors": len(errors),
    }


def _alert_coverage(records: list[dict[str, Any]]) -> dict[str, Any]:
    priority = _count_by(records, "priority")
    return {
        "records": len(records),
        "priority": priority,
        "no_alert_records": priority.get("no_alert", 0),
        "user_attention_records": sum(1 for record in records if record.get("requires_user_attention") is True),
        "downgraded_records": sum(1 for record in records if _string_list(record.get("downgrade_reasons"))),
        "suppressed_records": sum(1 for record in records if _string_list(record.get("suppression_reasons"))),
        "warning_records": sum(1 for record in records if _string_list(record.get("warnings"))),
        "derivatives_linked_records": sum(1 for record in records if record.get("linked_derivatives_context_ids")),
        "macro_calendar_linked_records": sum(1 for record in records if record.get("linked_macro_calendar_context_ids")),
        "onchain_flow_linked_records": sum(1 for record in records if record.get("linked_onchain_flow_context_ids")),
        "p0_p1_records": priority.get("P0", 0) + priority.get("P1", 0),
    }


def _read_optional_artifact(path: Path, artifact_name: str, *, records_key: str) -> dict[str, Any] | None:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except JSONDecodeError as exc:
        raise PipelineError(f"{artifact_name} is not valid JSON: {exc.msg}.", stage=STAGE_NAME, exit_code=3) from exc
    if not isinstance(loaded, dict):
        raise PipelineError(f"{artifact_name} must be a JSON object.", stage=STAGE_NAME, exit_code=3)
    if not isinstance(loaded.get(records_key), list):
        raise PipelineError(f"{artifact_name} is invalid: {records_key} must be a list.", stage=STAGE_NAME, exit_code=3)
    return loaded


def _created_at(fusion_artifact: dict[str, Any]) -> str:
    created_at = fusion_artifact.get("created_at")
    if isinstance(created_at, str) and created_at:
        return created_at
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _scope_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"unknown", "missing", "market_wide", "event"}:
        return None
    return text


def _count_by(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = _text(record.get(key), fallback="unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def _text(value: Any, *, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _unique_strings(values: list[str]) -> list[str]:
    unique = []
    for value in values:
        if value and value not in unique:
            unique.append(value)
    return unique
