from __future__ import annotations

import json
from collections import Counter
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from halpha.pipeline import PipelineError, RunContext


STAGE_NAME = "build_alert_decision_material"
EVENT_INTELLIGENCE_ASSESSMENT_ARTIFACT = "analysis/event_intelligence_assessment.json"
ALERT_DECISIONS_ARTIFACT = "analysis/alert_decisions.json"
ALERT_DECISION_MATERIAL_ARTIFACT = "analysis/alert_decision_material.md"
MAX_RECORDS = 30
MAX_LOW_PRIORITY_RECORDS = 8
MAX_LIST_ITEMS = 8
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "no_alert": 4, "unknown": 5}
HIGH_PRIORITY_ALERTS = {"P0", "P1", "P2"}


def build_alert_decision_material(config: dict[str, Any], run: RunContext) -> list[str]:
    alert_artifact = _read_optional_artifact(
        run.analysis_dir / "alert_decisions.json",
        ALERT_DECISIONS_ARTIFACT,
        records_key="records",
    )
    if alert_artifact is None:
        _record_manifest_summary(run, records=[], warnings=[], errors=[], status="skipped")
        return []

    assessment_artifact = _read_required_artifact(
        run.analysis_dir / "event_intelligence_assessment.json",
        EVENT_INTELLIGENCE_ASSESSMENT_ARTIFACT,
        records_key="records",
        previous_stage="build_event_intelligence_assessment",
    )
    records = _records(alert_artifact, "records")
    assessments = _records(assessment_artifact, "records")
    warnings = _material_warnings(records, alert_artifact, assessment_artifact)
    errors: list[dict[str, Any]] = []
    material = render_alert_decision_material(
        run,
        alert_artifact=alert_artifact,
        assessment_artifact=assessment_artifact,
        warnings=warnings,
    )
    output_path = run.analysis_dir / "alert_decision_material.md"
    output_path.write_text(material, encoding="utf-8")

    run.manifest["artifacts"]["alert_decision_material"] = ALERT_DECISION_MATERIAL_ARTIFACT
    _record_manifest_summary(run, records=records, warnings=warnings, errors=errors, status="succeeded")
    return [ALERT_DECISION_MATERIAL_ARTIFACT]


def render_alert_decision_material(
    run: RunContext,
    *,
    alert_artifact: dict[str, Any],
    assessment_artifact: dict[str, Any],
    warnings: list[str],
) -> str:
    all_records = _sorted_alert_records(_records(alert_artifact, "records"))
    selection = _alert_record_selection(all_records)
    records = selection["records"]
    assessments = _records(assessment_artifact, "records")
    assessment_index = {
        str(record.get("assessment_id")): record
        for record in assessments
        if isinstance(record.get("assessment_id"), str) and record.get("assessment_id")
    }
    source_artifacts = _source_artifacts(alert_artifact, assessment_artifact)
    lines = [
        "---",
        "artifact_type: analysis_alert_decision_material",
        "schema_version: 1",
        "audience: ai",
        "source_artifacts:",
        *_yaml_list(source_artifacts),
        "---",
        "",
        "# alert_decision_material",
        "",
        "## source_policy",
        "",
        "```yaml",
        _yaml_block(_source_policy()).rstrip(),
        "```",
        "",
        "## alert_overview",
        "",
        "```yaml",
        _yaml_block(_alert_overview(run, all_records, assessments, warnings=warnings)).rstrip(),
        "```",
        "",
        "## material_budget",
        "",
        "```yaml",
        _yaml_block(selection["summary"]).rstrip(),
        "```",
        "",
        "## priority_summary",
        "",
        "```yaml",
        _yaml_block(_priority_summary(all_records)).rstrip(),
        "```",
        "",
        "## decision_impact",
        "",
        "```yaml",
        _yaml_block(_decision_impact_summary(all_records)).rstrip(),
        "```",
        "",
        "## risk_and_watch_relevance",
        "",
        "```yaml",
        _yaml_block(_risk_and_watch_summary(all_records)).rstrip(),
        "```",
        "",
        "## downgrade_and_suppression_summary",
        "",
        "```yaml",
        _yaml_block(_downgrade_and_suppression_summary(all_records)).rstrip(),
        "```",
        "",
        "## uncertainty",
        "",
        "```yaml",
        _yaml_block(_uncertainty_summary(all_records, warnings=warnings)).rstrip(),
        "```",
        "",
        "## report_usage_rules",
        "",
        "```yaml",
        _yaml_block(_report_usage_rules()).rstrip(),
        "```",
        "",
        "## records",
        "",
    ]
    if not records:
        lines.extend(["```yaml", _yaml_block({"records": []}).rstrip(), "```", ""])
    else:
        for record in records:
            assessment = assessment_index.get(_first_string(record.get("linked_event_assessment_ids")))
            material_record = _material_record(record, assessment)
            lines.extend(
                [
                    f"### record: {material_record['alert_decision_id']}",
                    "",
                    "```yaml",
                    _yaml_block(material_record).rstrip(),
                    "```",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def _read_optional_artifact(path: Path, artifact_name: str, *, records_key: str) -> dict[str, Any] | None:
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except JSONDecodeError as exc:
        raise PipelineError(
            f"{artifact_name} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    return _validate_artifact(artifact, artifact_name, records_key=records_key)


def _read_required_artifact(
    path: Path,
    artifact_name: str,
    *,
    records_key: str,
    previous_stage: str,
) -> dict[str, Any]:
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{artifact_name} was not found; {previous_stage} must run first.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    except JSONDecodeError as exc:
        raise PipelineError(
            f"{artifact_name} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    return _validate_artifact(artifact, artifact_name, records_key=records_key)


def _validate_artifact(artifact: Any, artifact_name: str, *, records_key: str) -> dict[str, Any]:
    if not isinstance(artifact, dict):
        raise PipelineError(f"{artifact_name} must be a JSON object.", stage=STAGE_NAME, exit_code=3)
    if not isinstance(artifact.get(records_key), list):
        raise PipelineError(f"{artifact_name} is invalid: {records_key} must be a list.", stage=STAGE_NAME, exit_code=3)
    return artifact


def _records(artifact: dict[str, Any], key: str) -> list[dict[str, Any]]:
    return [record for record in artifact.get(key) or [] if isinstance(record, dict)]


def _source_policy() -> dict[str, Any]:
    return {
        "source_aware": True,
        "bounded_material": True,
        "full_alert_decision_json_embedded": False,
        "full_event_assessment_json_embedded": False,
        "raw_text_streams_embedded": False,
        "fabricate_missing_alert_priorities": False,
        "fabricate_missing_event_severity": False,
        "fabricate_missing_decision_impact": False,
    }


def _alert_overview(
    run: RunContext,
    records: list[dict[str, Any]],
    assessments: list[dict[str, Any]],
    *,
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "alert_decisions": len(records),
        "event_assessments": len(assessments),
        "priority_counts": _counts(records, "priority"),
        "user_attention_records": sum(1 for record in records if record.get("requires_user_attention") is True),
        "reassessment_records": sum(1 for record in records if record.get("requires_reassessment") is True),
        "downgraded_records": sum(1 for record in records if _string_list(record.get("downgrade_reasons"))),
        "suppressed_records": sum(1 for record in records if _string_list(record.get("suppression_reasons"))),
        "warnings": warnings,
    }


def _priority_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "priority_counts": _counts(records, "priority"),
        "attention_decision_counts": _counts(records, "attention_decision"),
        "records": [
            {
                "alert_decision_id": record.get("alert_decision_id"),
                "priority": record.get("priority"),
                "attention_decision": record.get("attention_decision"),
                "requires_user_attention": record.get("requires_user_attention"),
                "evidence_strength": record.get("evidence_strength"),
                "reason": _bounded_text(record.get("reason")),
            }
            for record in records[:MAX_LIST_ITEMS]
        ],
        "omitted_records": max(0, len(records) - MAX_LIST_ITEMS),
    }


def _decision_impact_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "decision_impact_counts": _counts(records, "decision_impact"),
        "records": [
            {
                "alert_decision_id": record.get("alert_decision_id"),
                "priority": record.get("priority"),
                "decision_impact": record.get("decision_impact"),
                "linked_decision_record_ids": _string_list(record.get("linked_decision_record_ids"))[:MAX_LIST_ITEMS],
            }
            for record in records[:MAX_LIST_ITEMS]
        ],
    }


def _risk_and_watch_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "risk_effect_counts": _counts(records, "risk_effect"),
        "watch_relevance_counts": _list_counts(records, "watch_trigger_relevance"),
        "records": [
            {
                "alert_decision_id": record.get("alert_decision_id"),
                "priority": record.get("priority"),
                "risk_effect": record.get("risk_effect"),
                "watch_trigger_relevance": _string_list(record.get("watch_trigger_relevance")),
                "linked_watch_trigger_ids": _string_list(record.get("linked_watch_trigger_ids"))[:MAX_LIST_ITEMS],
            }
            for record in records[:MAX_LIST_ITEMS]
        ],
    }


def _downgrade_and_suppression_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "downgrade_reason_counts": _list_counts(records, "downgrade_reasons"),
        "suppression_reason_counts": _list_counts(records, "suppression_reasons"),
        "records": [
            {
                "alert_decision_id": record.get("alert_decision_id"),
                "priority": record.get("priority"),
                "downgrade_reasons": _string_list(record.get("downgrade_reasons"))[:MAX_LIST_ITEMS],
                "suppression_reasons": _string_list(record.get("suppression_reasons"))[:MAX_LIST_ITEMS],
            }
            for record in records
            if _string_list(record.get("downgrade_reasons")) or _string_list(record.get("suppression_reasons"))
        ][:MAX_LIST_ITEMS],
    }


def _uncertainty_summary(records: list[dict[str, Any]], *, warnings: list[str]) -> dict[str, Any]:
    uncertainty: list[str] = []
    for record in records:
        uncertainty.extend(_string_list(record.get("uncertainty")))
    return {
        "uncertainty": _unique(uncertainty)[:MAX_LIST_ITEMS],
        "warnings": _unique(warnings)[:MAX_LIST_ITEMS],
    }


def _report_usage_rules() -> dict[str, Any]:
    return {
        "codex_may_explain_alert_priority": True,
        "codex_may_explain_no_alert_state": True,
        "codex_may_explain_downgrade_and_suppression_reasons": True,
        "codex_may_generate_alert_priority": False,
        "codex_may_generate_event_severity": False,
        "codex_may_generate_decision_impact": False,
        "codex_may_generate_action_levels": False,
        "codex_may_generate_price_forecasts": False,
        "codex_may_send_or_schedule_alerts": False,
        "codex_may_create_trading_instructions": False,
        "alert_decisions_are_notifications": False,
        "financial_advice": False,
    }


def _material_record(record: dict[str, Any], assessment: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "record_type": "alert_decision_record",
        "alert_decision_id": record.get("alert_decision_id"),
        "priority": record.get("priority"),
        "attention_decision": record.get("attention_decision"),
        "requires_user_attention": record.get("requires_user_attention"),
        "requires_reassessment": record.get("requires_reassessment"),
        "evidence_strength": record.get("evidence_strength"),
        "decision_impact": record.get("decision_impact"),
        "risk_effect": record.get("risk_effect"),
        "watch_trigger_relevance": _string_list(record.get("watch_trigger_relevance")),
        "reason": _bounded_text(record.get("reason")),
        "downgrade_reasons": _string_list(record.get("downgrade_reasons"))[:MAX_LIST_ITEMS],
        "suppression_reasons": _string_list(record.get("suppression_reasons"))[:MAX_LIST_ITEMS],
        "warnings": _string_list(record.get("warnings"))[:MAX_LIST_ITEMS],
        "uncertainty": _string_list(record.get("uncertainty"))[:MAX_LIST_ITEMS],
        "linked_event_assessment_ids": _string_list(record.get("linked_event_assessment_ids"))[:MAX_LIST_ITEMS],
        "linked_decision_record_ids": _string_list(record.get("linked_decision_record_ids"))[:MAX_LIST_ITEMS],
        "linked_watch_trigger_ids": _string_list(record.get("linked_watch_trigger_ids"))[:MAX_LIST_ITEMS],
        "assessment": _assessment_summary(assessment),
        "source_artifacts": _string_list(record.get("source_artifacts"))[:MAX_LIST_ITEMS],
        "report_boundaries": _report_usage_rules(),
    }


def _assessment_summary(assessment: dict[str, Any] | None) -> dict[str, Any] | None:
    if assessment is None:
        return None
    return {
        "assessment_id": assessment.get("assessment_id"),
        "event_severity": assessment.get("event_severity"),
        "source_reliability": assessment.get("source_reliability"),
        "market_response_relationship": assessment.get("market_response_relationship"),
        "decision_impact": assessment.get("decision_impact"),
        "confidence": assessment.get("confidence"),
        "downgrade_reasons": _string_list(assessment.get("downgrade_reasons"))[:MAX_LIST_ITEMS],
    }


def _sorted_alert_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        records,
        key=lambda record: (
            PRIORITY_ORDER.get(str(record.get("priority") or "unknown"), 99),
            str(record.get("alert_decision_id") or ""),
        ),
    )


def _alert_record_selection(records: list[dict[str, Any]]) -> dict[str, Any]:
    high_priority = [record for record in records if str(record.get("priority") or "unknown") in HIGH_PRIORITY_ALERTS]
    low_priority = [record for record in records if str(record.get("priority") or "unknown") not in HIGH_PRIORITY_ALERTS]
    selected = high_priority[:MAX_RECORDS]
    remaining_slots = max(0, MAX_RECORDS - len(selected))
    low_priority_limit = min(MAX_LOW_PRIORITY_RECORDS, remaining_slots)
    selected.extend(low_priority[:low_priority_limit])
    selected_ids = {id(record) for record in selected}
    omitted = [record for record in records if id(record) not in selected_ids]
    omission_reasons: list[str] = []
    if any(str(record.get("priority") or "unknown") in HIGH_PRIORITY_ALERTS for record in omitted):
        omission_reasons.append("high_priority_record_budget_exceeded")
    if any(str(record.get("priority") or "unknown") not in HIGH_PRIORITY_ALERTS for record in omitted):
        omission_reasons.append("low_priority_record_budget_exceeded")
    return {
        "records": selected,
        "summary": {
            "policy": "retain_P0_P1_P2_first_then_sample_low_priority_records",
            "max_records": MAX_RECORDS,
            "max_low_priority_records": MAX_LOW_PRIORITY_RECORDS,
            "total_records": len(records),
            "selected_records": len(selected),
            "omitted_records": len(omitted),
            "selected_by_priority": _counts(selected, "priority"),
            "omitted_by_priority": _counts(omitted, "priority"),
            "omission_reasons": omission_reasons,
        },
    }


def _source_artifacts(alert_artifact: dict[str, Any], assessment_artifact: dict[str, Any]) -> list[str]:
    artifacts = [
        EVENT_INTELLIGENCE_ASSESSMENT_ARTIFACT,
        ALERT_DECISIONS_ARTIFACT,
        *_string_list(alert_artifact.get("source_artifacts")),
        *_string_list(assessment_artifact.get("source_artifacts")),
    ]
    return _unique(artifacts)


def _material_warnings(
    records: list[dict[str, Any]],
    alert_artifact: dict[str, Any],
    assessment_artifact: dict[str, Any],
) -> list[str]:
    warnings = [*_string_list(alert_artifact.get("warnings")), *_string_list(assessment_artifact.get("warnings"))]
    for record in records:
        warnings.extend(_string_list(record.get("warnings")))
    return _unique(warnings)


def _record_manifest_summary(
    run: RunContext,
    *,
    records: list[dict[str, Any]],
    warnings: list[str],
    errors: list[dict[str, Any]],
    status: str,
) -> None:
    selection_summary = _alert_record_selection(_sorted_alert_records(records))["summary"]
    run.manifest["counts"]["alert_decision_material_records"] = len(records)
    run.manifest["counts"]["alert_decision_material_warning_records"] = sum(
        1 for record in records if _string_list(record.get("warnings"))
    )
    run.manifest["alert_decision_material"] = {
        "status": status,
        "artifacts": [ALERT_DECISION_MATERIAL_ARTIFACT] if status == "succeeded" else [],
        "records": len(records),
        "priority": _counts(records, "priority"),
        "material_selection": selection_summary,
        "warnings": len(warnings),
        "errors": len(errors),
        "degraded": any(
            record.get("priority") in {"P3", "no_alert", "unknown"} or _string_list(record.get("suppression_reasons"))
            for record in records
        ),
    }


def _counts(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts = Counter(str(record.get(key) or "unknown") for record in records)
    return dict(sorted(counts.items()))


def _list_counts(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    values: list[str] = []
    for record in records:
        values.extend(_string_list(record.get(key)))
    counts = Counter(values)
    return dict(sorted(counts.items()))


def _bounded_text(value: Any, *, max_length: int = 240) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    if len(text) <= max_length:
        return text
    return text[: max_length - 3].rstrip() + "..."


def _first_string(value: Any) -> str:
    values = _string_list(value)
    return values[0] if values else ""


def _yaml_list(values: list[str]) -> list[str]:
    if not values:
        return ["  []"]
    return [f"  - {value}" for value in values]


def _yaml_block(data: dict[str, Any]) -> str:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise PipelineError(
            "PyYAML is required to write YAML alert decision material.",
            stage=STAGE_NAME,
            exit_code=1,
        ) from exc
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def _unique(values: list[str]) -> list[str]:
    unique: list[str] = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return unique
