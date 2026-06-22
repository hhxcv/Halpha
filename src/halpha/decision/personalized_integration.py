from __future__ import annotations

import json
from datetime import UTC, datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from halpha.runtime.pipeline_contracts import PipelineError, RunContext
from halpha.storage import write_json


STAGE_NAME = "integrate_personalized_risk_constraints"
PERSONALIZED_RISK_CONSTRAINTS_ARTIFACT = "analysis/personalized_risk_constraints.json"
DECISION_RECOMMENDATIONS_ARTIFACT = "analysis/decision_recommendations.json"
WATCH_TRIGGERS_ARTIFACT = "analysis/watch_triggers.json"
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


def integrate_personalized_risk_constraints(config: dict[str, Any], run: RunContext) -> list[str]:
    constraints_artifact = _read_optional_artifact(
        run.analysis_dir / "personalized_risk_constraints.json",
        PERSONALIZED_RISK_CONSTRAINTS_ARTIFACT,
        records_key="records",
    )
    if constraints_artifact is None:
        _record_manifest(
            run,
            status="skipped",
            decision_records=[],
            watch_records=[],
            alert_records=[],
            warnings=[],
            errors=[],
        )
        return []

    constraint_index = _ConstraintIndex(_dict_list(constraints_artifact.get("records")))
    decision_artifact = _read_optional_artifact(
        run.analysis_dir / "decision_recommendations.json",
        DECISION_RECOMMENDATIONS_ARTIFACT,
        records_key="records",
    )
    watch_artifact = _read_optional_artifact(
        run.analysis_dir / "watch_triggers.json",
        WATCH_TRIGGERS_ARTIFACT,
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
    watch_records: list[dict[str, Any]] = []
    alert_records: list[dict[str, Any]] = []

    if decision_artifact is not None:
        decision_result = _integrate_decision_records(decision_artifact, constraint_index)
        decision_records = decision_result["records"]
        warnings.extend(decision_result["warnings"])
        decision_artifact["records"] = decision_records
        decision_artifact["source_artifacts"] = _unique_strings(
            [
                DECISION_RECOMMENDATIONS_ARTIFACT,
                PERSONALIZED_RISK_CONSTRAINTS_ARTIFACT,
                *_string_list(decision_artifact.get("source_artifacts")),
                *_string_list(constraints_artifact.get("source_artifacts")),
            ]
        )
        decision_artifact["warnings"] = _unique_strings(
            [*_string_list(decision_artifact.get("warnings")), *decision_result["warnings"]]
        )
        decision_artifact["created_at"] = _created_at(constraints_artifact)
        write_json(run.analysis_dir / "decision_recommendations.json", decision_artifact)
        artifacts.append(DECISION_RECOMMENDATIONS_ARTIFACT)
        _refresh_decision_counts(run, decision_records)

    if watch_artifact is not None:
        watch_result = _integrate_watch_records(watch_artifact, constraint_index)
        watch_records = watch_result["records"]
        warnings.extend(watch_result["warnings"])
        watch_artifact["records"] = watch_records
        watch_artifact["source_artifacts"] = _unique_strings(
            [
                WATCH_TRIGGERS_ARTIFACT,
                PERSONALIZED_RISK_CONSTRAINTS_ARTIFACT,
                *_string_list(watch_artifact.get("source_artifacts")),
                *_string_list(constraints_artifact.get("source_artifacts")),
            ]
        )
        watch_artifact["warnings"] = _unique_strings(
            [*_string_list(watch_artifact.get("warnings")), *watch_result["warnings"]]
        )
        watch_artifact["created_at"] = _created_at(constraints_artifact)
        write_json(run.analysis_dir / "watch_triggers.json", watch_artifact)
        artifacts.append(WATCH_TRIGGERS_ARTIFACT)
        _refresh_watch_counts(run, watch_records)

    if alert_artifact is not None:
        alert_result = _integrate_alert_records(alert_artifact, constraint_index)
        alert_records = alert_result["records"]
        warnings.extend(alert_result["warnings"])
        alert_artifact["records"] = alert_records
        alert_artifact["source_artifacts"] = _unique_strings(
            [
                ALERT_DECISIONS_ARTIFACT,
                PERSONALIZED_RISK_CONSTRAINTS_ARTIFACT,
                *_string_list(alert_artifact.get("source_artifacts")),
                *_string_list(constraints_artifact.get("source_artifacts")),
            ]
        )
        alert_artifact["warnings"] = _unique_strings(
            [*_string_list(alert_artifact.get("warnings")), *alert_result["warnings"]]
        )
        alert_artifact["coverage"] = _alert_coverage(alert_records)
        alert_artifact["created_at"] = _created_at(constraints_artifact)
        write_json(run.analysis_dir / "alert_decisions.json", alert_artifact)
        artifacts.append(ALERT_DECISIONS_ARTIFACT)
        _refresh_alert_counts(run, alert_records)

    artifacts.extend(
        _refresh_materials(
            config,
            run,
            decision_changed=bool(decision_records or watch_records),
            alert_changed=bool(alert_records),
        )
    )
    _record_manifest(
        run,
        status="succeeded",
        decision_records=decision_records,
        watch_records=watch_records,
        alert_records=alert_records,
        warnings=warnings,
        errors=errors,
    )
    return _unique_strings(artifacts)


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
    reasons = _personalized_reasons(context)
    warnings: list[str] = []
    record["personalized_adjustment_reasons"] = _unique_strings(
        [*_string_list(record.get("personalized_adjustment_reasons")), *reasons]
    )
    record["risk_conditions"] = _unique_strings(
        [
            *_string_list(record.get("risk_conditions")),
            f"personalized_state={context['state']}; personalized_action={context['action']}.",
        ]
    )
    record["warnings"] = _unique_strings(
        [
            *_string_list(record.get("warnings")),
            *_personalized_warnings(context),
        ]
    )
    record["do_not_do"] = _unique_strings(
        [
            *_string_list(record.get("do_not_do")),
            *_personalized_do_not_do(context),
        ]
    )

    original_action = _text(record.get("action_level"), fallback="NO_ACTION")
    new_action = _decision_action_after_personalization(original_action, context)
    if new_action != original_action:
        record["pre_personalized_action_level"] = original_action
        record["pre_personalized_decision_bias"] = record.get("decision_bias")
        record["pre_personalized_recommended_actions"] = _string_list(record.get("recommended_actions"))
        record["pre_personalized_invalidation_conditions"] = _string_list(record.get("invalidation_conditions"))
        record["action_level"] = new_action
        record["decision_bias"] = _decision_bias_after_personalization(new_action, context)
        record["confidence"] = "low" if new_action in {"NO_ACTION", "WATCH"} else record.get("confidence", "unknown")
        record["status"] = _decision_status_after_personalization(new_action, context)
        record["recommended_actions"] = _recommended_actions_after_personalization(new_action, record, context)
        record["invalidation_conditions"] = (
            [] if new_action == "NO_ACTION" else _string_list(record.get("invalidation_conditions"))
        )
        record["downgrade_reasons"] = _unique_strings([*_string_list(record.get("downgrade_reasons")), *reasons])
        warnings.append("personalized_adjusted_decision_recommendation")
    elif context["action"] in {"block", "downgrade"}:
        record["downgrade_reasons"] = _unique_strings([*_string_list(record.get("downgrade_reasons")), *reasons])
    return warnings


def _apply_watch_adjustments(record: dict[str, Any], context: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    record["personalized_adjustment_reasons"] = _unique_strings(
        [*_string_list(record.get("personalized_adjustment_reasons")), *_personalized_reasons(context)]
    )
    record["evidence"] = _unique_strings([*_string_list(record.get("evidence")), *context["evidence"]])
    record["warnings"] = _unique_strings([*_string_list(record.get("warnings")), *_personalized_warnings(context)])
    if context["action"] not in {"block", "downgrade"}:
        return warnings

    original_priority = _text(record.get("priority"), fallback="unknown")
    new_priority = "low" if context["action"] == "block" else _downgrade_watch_priority(original_priority)
    if new_priority != original_priority:
        record["pre_personalized_priority"] = original_priority
        record["priority"] = new_priority
    record["pre_personalized_expected_decision_impact"] = record.get("expected_decision_impact")
    record["expected_decision_impact"] = (
        "personalized_constraint_blocks_stronger_action"
        if context["action"] == "block"
        else "personalized_constraint_requires_more_conservative_review"
    )
    warnings.append("personalized_adjusted_watch_trigger")
    return warnings


def _apply_alert_adjustments(record: dict[str, Any], context: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    record["personalized_adjustment_reasons"] = _unique_strings(
        [*_string_list(record.get("personalized_adjustment_reasons")), *_personalized_reasons(context)]
    )
    record["uncertainty"] = _unique_strings([*_string_list(record.get("uncertainty")), *context["uncertainty"]])
    record["warnings"] = _unique_strings([*_string_list(record.get("warnings")), *_personalized_warnings(context)])
    if context["action"] not in {"block", "downgrade"}:
        return warnings

    original_priority = _text(record.get("priority"), fallback="unknown")
    new_priority = "no_alert" if context["action"] == "block" else _downgrade_alert_priority(original_priority)
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
            f"personalized constraint {context['constraint_id']} set priority={new_priority}.",
        )
        if context["action"] == "block":
            record["suppression_reasons"] = _unique_strings(
                [*_string_list(record.get("suppression_reasons")), *_personalized_reasons(context)]
            )
        record["downgrade_reasons"] = _unique_strings(
            [*_string_list(record.get("downgrade_reasons")), *_personalized_reasons(context)]
        )
        warnings.append("personalized_adjusted_alert_decision")
    elif context["action"] == "downgrade":
        record["downgrade_reasons"] = _unique_strings(
            [*_string_list(record.get("downgrade_reasons")), *_personalized_reasons(context)]
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
        "evidence": _string_list(record.get("evidence"))[:8],
        "uncertainty": _string_list(record.get("uncertainty"))[:8],
        "warnings": _string_list(record.get("warnings"))[:8],
        "source_artifacts": _unique_strings(
            [PERSONALIZED_RISK_CONSTRAINTS_ARTIFACT, *_string_list(record.get("source_artifacts"))]
        ),
    }


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


def _refresh_decision_counts(run: RunContext, records: list[dict[str, Any]]) -> None:
    run.manifest["counts"]["decision_recommendation_records"] = len(records)
    run.manifest["counts"]["decision_recommendation_actionable_records"] = sum(
        1 for record in records if record.get("action_level") in ACTIONABLE_ACTION_LEVELS
    )
    run.manifest["counts"]["decision_recommendation_non_actionable_records"] = sum(
        1 for record in records if record.get("action_level") not in ACTIONABLE_ACTION_LEVELS
    )
    run.manifest["counts"]["decision_recommendation_personalized_linked_records"] = sum(
        1 for record in records if record.get("personalized_constraint_id")
    )
    run.manifest["counts"]["decision_recommendation_personalized_adjusted_records"] = sum(
        1 for record in records if record.get("pre_personalized_action_level")
    )


def _refresh_watch_counts(run: RunContext, records: list[dict[str, Any]]) -> None:
    run.manifest["counts"]["watch_trigger_records"] = len(records)
    run.manifest["counts"]["watch_trigger_linked_records"] = sum(
        1 for record in records if record.get("linked_decision_record_id")
    )
    run.manifest["counts"]["watch_trigger_personalized_linked_records"] = sum(
        1 for record in records if record.get("personalized_constraint_id")
    )
    run.manifest["counts"]["watch_trigger_personalized_adjusted_records"] = sum(
        1 for record in records if record.get("pre_personalized_expected_decision_impact")
    )


def _refresh_alert_counts(run: RunContext, records: list[dict[str, Any]]) -> None:
    priority = _count_by(records, "priority")
    run.manifest["counts"]["alert_decision_records"] = len(records)
    run.manifest["counts"]["alert_decision_p0_records"] = priority.get("P0", 0)
    run.manifest["counts"]["alert_decision_p1_records"] = priority.get("P1", 0)
    run.manifest["counts"]["alert_decision_p2_records"] = priority.get("P2", 0)
    run.manifest["counts"]["alert_decision_p3_records"] = priority.get("P3", 0)
    run.manifest["counts"]["alert_decision_no_alert_records"] = priority.get("no_alert", 0)
    run.manifest["counts"]["alert_decision_personalized_linked_records"] = sum(
        1 for record in records if record.get("personalized_constraint_id")
    )
    run.manifest["counts"]["alert_decision_personalized_adjusted_records"] = sum(
        1 for record in records if record.get("pre_personalized_priority")
    )


def _record_manifest(
    run: RunContext,
    *,
    status: str,
    decision_records: list[dict[str, Any]],
    watch_records: list[dict[str, Any]],
    alert_records: list[dict[str, Any]],
    warnings: list[str],
    errors: list[dict[str, Any]],
) -> None:
    decision_linked = sum(1 for record in decision_records if record.get("personalized_constraint_id"))
    watch_linked = sum(1 for record in watch_records if record.get("personalized_constraint_id"))
    alert_linked = sum(1 for record in alert_records if record.get("personalized_constraint_id"))
    decision_adjusted = sum(1 for record in decision_records if record.get("pre_personalized_action_level"))
    watch_adjusted = sum(1 for record in watch_records if record.get("pre_personalized_expected_decision_impact"))
    alert_adjusted = sum(1 for record in alert_records if record.get("pre_personalized_priority"))
    run.manifest["counts"]["personalized_risk_decision_linked_records"] = decision_linked
    run.manifest["counts"]["personalized_risk_watch_linked_records"] = watch_linked
    run.manifest["counts"]["personalized_risk_alert_linked_records"] = alert_linked
    run.manifest["counts"]["personalized_risk_decision_adjusted_records"] = decision_adjusted
    run.manifest["counts"]["personalized_risk_watch_adjusted_records"] = watch_adjusted
    run.manifest["counts"]["personalized_risk_alert_adjusted_records"] = alert_adjusted
    run.manifest["counts"]["personalized_risk_integration_warnings"] = len(warnings)
    run.manifest["counts"]["personalized_risk_integration_errors"] = len(errors)
    run.manifest["personalized_risk_integration"] = {
        "status": status,
        "source_artifact": PERSONALIZED_RISK_CONSTRAINTS_ARTIFACT if status == "succeeded" else None,
        "decision_records": len(decision_records),
        "decision_linked_records": decision_linked,
        "decision_adjusted_records": decision_adjusted,
        "watch_records": len(watch_records),
        "watch_linked_records": watch_linked,
        "watch_adjusted_records": watch_adjusted,
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
        "personalized_linked_records": sum(1 for record in records if record.get("personalized_constraint_id")),
        "personalized_adjusted_records": sum(1 for record in records if record.get("pre_personalized_priority")),
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


def _created_at(constraints_artifact: dict[str, Any]) -> str:
    created_at = constraints_artifact.get("created_at")
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


def _append_reason(value: Any, reason: str) -> str:
    current = _text(value, fallback="")
    if current:
        return f"{current} {reason}"
    return reason


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
