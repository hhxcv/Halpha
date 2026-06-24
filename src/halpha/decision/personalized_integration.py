from __future__ import annotations

from typing import Any


PERSONALIZED_RISK_CONSTRAINTS_ARTIFACT = "analysis/personalized_risk_constraints.json"

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


def apply_personalized_constraints_to_decision_records(
    records: list[dict[str, Any]],
    constraints_artifact: dict[str, Any] | None,
) -> dict[str, Any]:
    if constraints_artifact is None:
        return _application_result("skipped", records, warnings=[], errors=[])
    constraint_index = _ConstraintIndex(_dict_list(constraints_artifact.get("records")))
    result = _integrate_decision_records({"records": records}, constraint_index)
    return _application_result(
        "succeeded",
        result["records"],
        warnings=result["warnings"],
        errors=[],
        source_artifacts=_unique_strings(
            [PERSONALIZED_RISK_CONSTRAINTS_ARTIFACT, *_string_list(constraints_artifact.get("source_artifacts"))]
        ),
    )


def apply_personalized_constraints_to_watch_records(
    records: list[dict[str, Any]],
    constraints_artifact: dict[str, Any] | None,
) -> dict[str, Any]:
    if constraints_artifact is None:
        return _application_result("skipped", records, warnings=[], errors=[])
    constraint_index = _ConstraintIndex(_dict_list(constraints_artifact.get("records")))
    result = _integrate_watch_records({"records": records}, constraint_index)
    return _application_result(
        "succeeded",
        result["records"],
        warnings=result["warnings"],
        errors=[],
        source_artifacts=_unique_strings(
            [PERSONALIZED_RISK_CONSTRAINTS_ARTIFACT, *_string_list(constraints_artifact.get("source_artifacts"))]
        ),
    )


def apply_personalized_constraints_to_alert_records(
    records: list[dict[str, Any]],
    constraints_artifact: dict[str, Any] | None,
) -> dict[str, Any]:
    if constraints_artifact is None:
        return _application_result("skipped", records, warnings=[], errors=[])
    constraint_index = _ConstraintIndex(_dict_list(constraints_artifact.get("records")))
    result = _integrate_alert_records({"records": records}, constraint_index)
    return _application_result(
        "succeeded",
        result["records"],
        warnings=result["warnings"],
        errors=[],
        source_artifacts=_unique_strings(
            [PERSONALIZED_RISK_CONSTRAINTS_ARTIFACT, *_string_list(constraints_artifact.get("source_artifacts"))]
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
        "decision_linked_records": sum(1 for record in records if record.get("personalized_constraint_id")),
        "decision_adjusted_records": sum(1 for record in records if record.get("pre_personalized_action_level")),
        "watch_linked_records": sum(1 for record in records if record.get("personalized_constraint_id")),
        "watch_adjusted_records": sum(
            1 for record in records if record.get("pre_personalized_expected_decision_impact")
        ),
        "alert_linked_records": sum(1 for record in records if record.get("personalized_constraint_id")),
        "alert_adjusted_records": sum(1 for record in records if record.get("pre_personalized_priority")),
    }


class _ConstraintIndex:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.by_scope: dict[tuple[str | None, str | None], dict[str, Any]] = {}
        for record in sorted(records, key=lambda item: str(item.get("constraint_id") or "")):
            scope = _dict(record.get("scope"))
            key = (_scope_value(scope.get("symbol")), _scope_value(scope.get("timeframe")))
            self.by_scope.setdefault(key, record)

    def match(self, *, symbol: Any, timeframe: Any, allow_symbol_only: bool = False) -> dict[str, Any] | None:
        symbol_value = _scope_value(symbol)
        timeframe_value = _scope_value(timeframe)
        record = self.by_scope.get((symbol_value, timeframe_value))
        if record is not None:
            return record
        if allow_symbol_only and symbol_value is not None:
            return self.by_scope.get((symbol_value, None))
        return None


def _integrate_decision_records(artifact: dict[str, Any], constraint_index: _ConstraintIndex) -> dict[str, Any]:
    records = []
    warnings: list[str] = []
    for original in _dict_list(artifact.get("records")):
        record = dict(original)
        constraint = constraint_index.match(symbol=record.get("symbol"), timeframe=record.get("timeframe"))
        if constraint is None:
            records.append(record)
            continue
        context = _constraint_context(constraint)
        _apply_personalized_fields(record, context)
        decision_warnings = _apply_decision_adjustments(record, context)
        warnings.extend(decision_warnings)
        records.append(record)
    return {"records": records, "warnings": _unique_strings(warnings)}


def _integrate_watch_records(artifact: dict[str, Any], constraint_index: _ConstraintIndex) -> dict[str, Any]:
    records = []
    warnings: list[str] = []
    for original in _dict_list(artifact.get("records")):
        record = dict(original)
        constraint = constraint_index.match(symbol=record.get("symbol"), timeframe=record.get("timeframe"))
        if constraint is None:
            records.append(record)
            continue
        context = _constraint_context(constraint)
        _apply_personalized_fields(record, context)
        watch_warnings = _apply_watch_adjustments(record, context)
        warnings.extend(watch_warnings)
        records.append(record)
    return {"records": records, "warnings": _unique_strings(warnings)}


def _integrate_alert_records(artifact: dict[str, Any], constraint_index: _ConstraintIndex) -> dict[str, Any]:
    records = []
    warnings: list[str] = []
    for original in _dict_list(artifact.get("records")):
        record = dict(original)
        scope = _dict(record.get("scope"))
        constraint = constraint_index.match(
            symbol=scope.get("symbol") or record.get("symbol"),
            timeframe=scope.get("timeframe") or record.get("timeframe"),
            allow_symbol_only=True,
        )
        if constraint is None:
            records.append(record)
            continue
        context = _constraint_context(constraint)
        _apply_personalized_fields(record, context)
        alert_warnings = _apply_alert_adjustments(record, context)
        warnings.extend(alert_warnings)
        records.append(record)
    return {"records": records, "warnings": _unique_strings(warnings)}


def _apply_personalized_fields(record: dict[str, Any], context: dict[str, Any]) -> None:
    record["personalized_constraint_id"] = context["constraint_id"]
    record["personalized_state"] = context["state"]
    record["personalized_action"] = context["action"]
    record["personalized_severity"] = context["severity"]
    record["personalized_confidence"] = context["confidence"]
    record["personalized_reason_codes"] = context["reason_codes"]
    record["personalized_evidence"] = context["evidence"]
    record["personalized_uncertainty"] = context["uncertainty"]
    record["personalized_source_artifacts"] = context["source_artifacts"]
    record["source_artifacts"] = _unique_strings(
        [
            *_string_list(record.get("source_artifacts")),
            PERSONALIZED_RISK_CONSTRAINTS_ARTIFACT,
            *context["source_artifacts"],
        ]
    )


def _apply_decision_adjustments(record: dict[str, Any], context: dict[str, Any]) -> list[str]:
    effective_context = _effective_context_for_decision(record, context)
    reasons = _personalized_reasons(effective_context)
    warnings: list[str] = []
    record["personalized_effective_action"] = effective_context["action"]
    record["personalized_adjustment_reasons"] = _unique_strings(
        [*_string_list(record.get("personalized_adjustment_reasons")), *reasons]
    )
    record["risk_conditions"] = _unique_strings(
        [
            *_string_list(record.get("risk_conditions")),
            f"personalized_state={context['state']}; personalized_action={effective_context['action']}.",
        ]
    )
    record["warnings"] = _unique_strings(
        [
            *_string_list(record.get("warnings")),
            *_personalized_warnings(effective_context),
        ]
    )
    record["do_not_do"] = _unique_strings(
        [
            *_string_list(record.get("do_not_do")),
            *_personalized_do_not_do(effective_context),
        ]
    )

    original_action = _text(record.get("action_level"), fallback="NO_ACTION")
    new_action = _decision_action_after_personalization(original_action, effective_context)
    if new_action != original_action:
        record["pre_personalized_action_level"] = original_action
        record["pre_personalized_decision_bias"] = record.get("decision_bias")
        record["pre_personalized_recommended_actions"] = _string_list(record.get("recommended_actions"))
        record["pre_personalized_invalidation_conditions"] = _string_list(record.get("invalidation_conditions"))
        record["action_level"] = new_action
        record["decision_bias"] = _decision_bias_after_personalization(new_action, effective_context)
        record["confidence"] = "low" if new_action in {"NO_ACTION", "WATCH"} else record.get("confidence", "unknown")
        record["status"] = _decision_status_after_personalization(new_action, effective_context)
        record["recommended_actions"] = _recommended_actions_after_personalization(new_action, record, effective_context)
        record["invalidation_conditions"] = (
            [] if new_action == "NO_ACTION" else _string_list(record.get("invalidation_conditions"))
        )
        record["downgrade_reasons"] = _unique_strings([*_string_list(record.get("downgrade_reasons")), *reasons])
        warnings.append("personalized_adjusted_decision_recommendation")
    elif effective_context["action"] in {"block", "downgrade"}:
        record["downgrade_reasons"] = _unique_strings([*_string_list(record.get("downgrade_reasons")), *reasons])
    return warnings


def _apply_watch_adjustments(record: dict[str, Any], context: dict[str, Any]) -> list[str]:
    effective_context = _effective_context_for_watch(record, context)
    warnings: list[str] = []
    record["personalized_effective_action"] = effective_context["action"]
    record["personalized_adjustment_reasons"] = _unique_strings(
        [*_string_list(record.get("personalized_adjustment_reasons")), *_personalized_reasons(effective_context)]
    )
    record["evidence"] = _unique_strings([*_string_list(record.get("evidence")), *effective_context["evidence"]])
    record["warnings"] = _unique_strings([*_string_list(record.get("warnings")), *_personalized_warnings(effective_context)])
    if effective_context["action"] not in {"block", "downgrade"}:
        return warnings

    original_priority = _text(record.get("priority"), fallback="unknown")
    new_priority = "low" if effective_context["action"] == "block" else _downgrade_watch_priority(original_priority)
    if new_priority != original_priority:
        record["pre_personalized_priority"] = original_priority
        record["priority"] = new_priority
    record["pre_personalized_expected_decision_impact"] = record.get("expected_decision_impact")
    record["expected_decision_impact"] = (
        "personalized_constraint_blocks_stronger_action"
        if effective_context["action"] == "block"
        else "personalized_constraint_requires_more_conservative_review"
    )
    warnings.append("personalized_adjusted_watch_trigger")
    return warnings


def _apply_alert_adjustments(record: dict[str, Any], context: dict[str, Any]) -> list[str]:
    effective_context = _effective_context_for_alert(record, context)
    warnings: list[str] = []
    record["personalized_effective_action"] = effective_context["action"]
    record["personalized_adjustment_reasons"] = _unique_strings(
        [*_string_list(record.get("personalized_adjustment_reasons")), *_personalized_reasons(effective_context)]
    )
    record["uncertainty"] = _unique_strings([*_string_list(record.get("uncertainty")), *effective_context["uncertainty"]])
    record["warnings"] = _unique_strings([*_string_list(record.get("warnings")), *_personalized_warnings(effective_context)])
    if effective_context["action"] not in {"block", "downgrade"}:
        return warnings

    original_priority = _text(record.get("priority"), fallback="unknown")
    new_priority = "no_alert" if effective_context["action"] == "block" else _downgrade_alert_priority(original_priority)
    if new_priority != original_priority:
        record["pre_personalized_priority"] = original_priority
        record["pre_personalized_attention_decision"] = record.get("attention_decision")
        record["pre_personalized_requires_user_attention"] = record.get("requires_user_attention")
        record["pre_personalized_status"] = record.get("status")
        record["priority"] = new_priority
        record["attention_decision"] = ATTENTION_DECISIONS.get(new_priority, "unknown")
        record["requires_user_attention"] = False
        record["requires_reassessment"] = True
        record["status"] = "suppressed" if new_priority == "no_alert" else "degraded"
        record["reason"] = _append_reason(
            record.get("reason"),
            f"personalized constraint {effective_context['constraint_id']} set priority={new_priority}.",
        )
        if effective_context["action"] == "block":
            record["suppression_reasons"] = _unique_strings(
                [*_string_list(record.get("suppression_reasons")), *_personalized_reasons(effective_context)]
            )
        record["downgrade_reasons"] = _unique_strings(
            [*_string_list(record.get("downgrade_reasons")), *_personalized_reasons(effective_context)]
        )
        warnings.append("personalized_adjusted_alert_decision")
    elif effective_context["action"] == "downgrade":
        record["downgrade_reasons"] = _unique_strings(
            [*_string_list(record.get("downgrade_reasons")), *_personalized_reasons(effective_context)]
        )
    return warnings


def _constraint_context(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "constraint_id": _text(record.get("constraint_id"), fallback="personalized:unknown"),
        "state": _text(record.get("state"), fallback="unknown"),
        "action": _text(record.get("action"), fallback="none"),
        "severity": _text(record.get("severity"), fallback="unknown"),
        "confidence": _text(record.get("confidence"), fallback="unknown"),
        "reason_codes": _string_list(record.get("reason_codes")),
        "policy": _dict(record.get("constraint_policy")),
        "evidence": _string_list(record.get("evidence"))[:8],
        "uncertainty": _string_list(record.get("uncertainty"))[:8],
        "warnings": _string_list(record.get("warnings"))[:8],
        "source_artifacts": _unique_strings(
            [PERSONALIZED_RISK_CONSTRAINTS_ARTIFACT, *_string_list(record.get("source_artifacts"))]
        ),
    }


def _effective_context_for_decision(record: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    reason_codes = _applicable_decision_reason_codes(record, context)
    return _context_with_effective_action(context, reason_codes)


def _effective_context_for_watch(record: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    reason_codes = _applicable_watch_reason_codes(record, context)
    return _context_with_effective_action(context, reason_codes)


def _effective_context_for_alert(record: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    reason_codes = _applicable_alert_reason_codes(record, context)
    return _context_with_effective_action(context, reason_codes)


def _context_with_effective_action(context: dict[str, Any], reason_codes: list[str]) -> dict[str, Any]:
    effective = dict(context)
    action = context["action"]
    if action in {"block", "downgrade"} and not reason_codes:
        action = "annotate"
    effective["action"] = action
    effective["reason_codes"] = reason_codes
    return effective


def _applicable_decision_reason_codes(record: dict[str, Any], context: dict[str, Any]) -> list[str]:
    action_level = _text(record.get("action_level"), fallback="NO_ACTION")
    risk_level = _risk_level_from_decision(record)
    return [
        code
        for code in context["reason_codes"]
        if _reason_code_applies(
            code,
            context,
            action_level=action_level,
            risk_level=risk_level,
            priority=None,
        )
    ]


def _applicable_watch_reason_codes(record: dict[str, Any], context: dict[str, Any]) -> list[str]:
    priority = _text(record.get("priority"), fallback="unknown")
    return [
        code
        for code in context["reason_codes"]
        if _reason_code_applies(
            code,
            context,
            action_level=None,
            risk_level=None,
            priority=priority,
        )
    ]


def _applicable_alert_reason_codes(record: dict[str, Any], context: dict[str, Any]) -> list[str]:
    priority = _text(record.get("priority"), fallback="unknown")
    return [
        code
        for code in context["reason_codes"]
        if _reason_code_applies(
            code,
            context,
            action_level=None,
            risk_level=None,
            priority=priority,
        )
    ]


def _reason_code_applies(
    code: str,
    context: dict[str, Any],
    *,
    action_level: str | None,
    risk_level: str | None,
    priority: str | None,
) -> bool:
    risk_policy = _dict(_dict(context.get("policy")).get("risk"))
    if code == "risk_action_cap":
        max_action = _text(risk_policy.get("max_action_level"), fallback="")
        if action_level is not None:
            max_rank = ACTIONABLE_RANK.get(max_action)
            action_rank = ACTIONABLE_RANK.get(action_level)
            return max_rank is None or (action_rank is not None and action_rank > max_rank)
        return priority in {"P0", "P1", "P2", "high", "medium"}
    if code == "new_exposure_not_allowed":
        if action_level is not None:
            return action_level in {"TRY_SMALL", "DO", "STRONG_DO"}
        return priority in {"P0", "P1", "P2", "high", "medium"}
    if code == "risk_state_cap":
        max_risk = _text(risk_policy.get("max_risk_state"), fallback="")
        max_rank = RISK_RANK.get(max_risk)
        risk_rank = RISK_RANK.get(risk_level or "")
        return max_rank is None or (risk_rank is not None and risk_rank > max_rank)
    return True


ACTIONABLE_RANK = {
    "NO_ACTION": 0,
    "WATCH": 1,
    "TRY_SMALL": 2,
    "DO": 3,
    "STRONG_DO": 4,
    "AVOID": 2,
    "EXIT_OR_REDUCE": 2,
    "HEDGE_OR_PROTECT": 2,
}
RISK_RANK = {"low": 0, "medium": 1, "high": 2, "extreme": 3}


def _risk_level_from_decision(record: dict[str, Any]) -> str:
    for condition in _string_list(record.get("risk_conditions")):
        if condition.startswith("risk_level="):
            return condition.split("=", 1)[1].split(";", 1)[0].strip()
    return ""


def _decision_action_after_personalization(action_level: str, context: dict[str, Any]) -> str:
    if context["action"] == "block":
        return "NO_ACTION"
    if context["action"] == "downgrade" and action_level in ACTIONABLE_ACTION_LEVELS:
        return "WATCH"
    return action_level


def _decision_bias_after_personalization(action_level: str, context: dict[str, Any]) -> str:
    if context["action"] == "block":
        return "personalized_blocked"
    if action_level == "WATCH":
        return "wait_for_personalized_constraint"
    if action_level == "NO_ACTION":
        return "no_action"
    return action_level.lower()


def _decision_status_after_personalization(action_level: str, context: dict[str, Any]) -> str:
    if context["action"] == "block":
        return "risk_blocked"
    if action_level == "WATCH":
        return "watch"
    if action_level == "NO_ACTION":
        return "no_action"
    return "actionable"


def _recommended_actions_after_personalization(
    action_level: str,
    record: dict[str, Any],
    context: dict[str, Any],
) -> list[str]:
    symbol = _text(record.get("symbol"), fallback="this market")
    if action_level == "NO_ACTION":
        return [
            f"Do not use stronger {symbol} action language while personalized constraint {context['constraint_id']} blocks it.",
            "Treat this as research-only constraint evidence, not an account or trading instruction.",
        ]
    if action_level == "WATCH":
        return [
            f"Watch {symbol} until personalized constraint {context['constraint_id']} no longer requires downgrade.",
            "Use upstream evidence and personalized constraint state together before considering stronger language.",
        ]
    return _string_list(record.get("recommended_actions"))


def _downgrade_watch_priority(priority: str) -> str:
    if priority == "high":
        return "medium"
    if priority == "medium":
        return "low"
    return priority


def _downgrade_alert_priority(priority: str) -> str:
    if priority in {"P0", "P1", "P2"}:
        return "P3"
    return priority


def _personalized_reasons(context: dict[str, Any]) -> list[str]:
    return [f"personalized_{reason}" for reason in context["reason_codes"]]


def _personalized_warnings(context: dict[str, Any]) -> list[str]:
    warnings = list(context["warnings"])
    if context["action"] in {"block", "downgrade"}:
        warnings.append("Record carries conservative personalized constraint context.")
    return _unique_strings(warnings)


def _personalized_do_not_do(context: dict[str, Any]) -> list[str]:
    if context["action"] in {"block", "downgrade"}:
        return ["Do not override personalized constraint context with stronger action or alert language."]
    return []


def _scope_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"unknown", "missing", "market_wide", "event"}:
        return None
    return text


def _append_reason(value: Any, reason: str) -> str:
    current = _text(value, fallback="")
    if current:
        return f"{current} {reason}"
    return reason


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


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
