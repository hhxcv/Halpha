from __future__ import annotations

from typing import Any


INTELLIGENCE_FUSION_ARTIFACT = "analysis/intelligence_fusion.json"

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


def apply_fusion_to_decision_records(
    records: list[dict[str, Any]],
    fusion_artifact: dict[str, Any] | None,
) -> dict[str, Any]:
    if fusion_artifact is None:
        return _application_result("skipped", records, warnings=[], errors=[])
    fusion_records = _dict_list(fusion_artifact.get("records"))
    result = _integrate_decision_records({"records": records}, _FusionIndex(fusion_records))
    return _application_result(
        "succeeded",
        result["records"],
        warnings=result["warnings"],
        errors=[],
        source_artifacts=_unique_strings(
            [INTELLIGENCE_FUSION_ARTIFACT, *_string_list(fusion_artifact.get("source_artifacts"))]
        ),
    )


def apply_fusion_to_alert_records(
    records: list[dict[str, Any]],
    fusion_artifact: dict[str, Any] | None,
) -> dict[str, Any]:
    if fusion_artifact is None:
        return _application_result("skipped", records, warnings=[], errors=[])
    fusion_records = _dict_list(fusion_artifact.get("records"))
    result = _integrate_alert_records({"records": records}, _FusionIndex(fusion_records))
    return _application_result(
        "succeeded",
        result["records"],
        warnings=result["warnings"],
        errors=[],
        source_artifacts=_unique_strings(
            [INTELLIGENCE_FUSION_ARTIFACT, *_string_list(fusion_artifact.get("source_artifacts"))]
        ),
    )


def _application_result(
    status: str,
    records: list[dict[str, Any]],
    *,
    warnings: list[str],
    errors: list[dict[str, Any]],
    source_artifacts: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "records": records,
        "warnings": _unique_strings(warnings),
        "errors": errors,
        "source_artifacts": _unique_strings(source_artifacts or []),
        "decision_linked_records": sum(1 for record in records if record.get("fusion_record_id")),
        "decision_adjusted_records": sum(1 for record in records if record.get("pre_fusion_action_level")),
        "alert_linked_records": sum(1 for record in records if record.get("fusion_record_id")),
        "alert_adjusted_records": sum(1 for record in records if record.get("pre_fusion_priority")),
    }


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


def _scope_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"unknown", "missing", "market_wide", "event"}:
        return None
    return text


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
