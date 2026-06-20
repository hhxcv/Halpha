from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any

from halpha.pipeline import PipelineError, RunContext


STAGE_NAME = "build_analysis_materials"
INTELLIGENCE_FUSION_ARTIFACT = "analysis/intelligence_fusion.json"
INTELLIGENCE_FUSION_MATERIAL_ARTIFACT = "analysis/intelligence_fusion_material.md"

MAX_RECORDS = 8
MAX_MESSAGES = 5
MAX_ARTIFACTS = 12
STATE_PRIORITY = {
    "risk_blocked": 0,
    "event_overridden": 1,
    "conflicting": 2,
    "degraded": 3,
    "insufficient_evidence": 4,
    "cautionary": 5,
    "supportive": 6,
    "neutral": 7,
    "failed": 8,
}


def build_intelligence_fusion_material(config: dict[str, Any], run: RunContext) -> list[str]:
    artifact = _read_fusion_artifact(run)
    material_record = _material_record(artifact)
    material = render_intelligence_fusion_material(material_record)
    (run.analysis_dir / "intelligence_fusion_material.md").write_text(material, encoding="utf-8")

    run.manifest["artifacts"]["intelligence_fusion_material"] = INTELLIGENCE_FUSION_MATERIAL_ARTIFACT
    run.manifest["counts"]["intelligence_fusion_material_records"] = material_record["selected_records"]["selected_record_count"]
    run.manifest["counts"]["intelligence_fusion_material_omitted_records"] = material_record["omissions"]["omitted_record_count"]
    run.manifest["intelligence_fusion_material"] = {
        "status": material_record["fusion_overview"]["status"],
        "artifact": INTELLIGENCE_FUSION_MATERIAL_ARTIFACT,
        "source_artifacts": material_record["source_policy"]["source_artifacts"],
        "selected_records": material_record["selected_records"]["selected_record_count"],
        "omitted_records": material_record["omissions"]["omitted_record_count"],
        "warnings": len(material_record["fusion_overview"]["warnings"]),
        "errors": len(material_record["fusion_overview"]["errors"]),
    }
    return [INTELLIGENCE_FUSION_MATERIAL_ARTIFACT]


def render_intelligence_fusion_material(material_record: dict[str, Any]) -> str:
    lines = [
        "---",
        "artifact_type: analysis_intelligence_fusion_material",
        "schema_version: 1",
        "audience: ai",
        "source_artifacts:",
        f"  - {INTELLIGENCE_FUSION_ARTIFACT}",
        "---",
        "",
        "# intelligence_fusion_material",
        "",
    ]
    for section in (
        "source_policy",
        "fusion_overview",
        "state_summary",
        "selected_records",
        "omissions",
        "report_usage_rules",
    ):
        lines.extend(
            [
                f"## {section}",
                "",
                "```yaml",
                _yaml_block(material_record[section]).rstrip(),
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _material_record(artifact: dict[str, Any]) -> dict[str, Any]:
    records = _dict_list(artifact.get("records"))
    selected = _select_records(records)
    return {
        "source_policy": _source_policy(artifact),
        "fusion_overview": _fusion_overview(artifact, records),
        "state_summary": _state_summary(artifact, records),
        "selected_records": {
            "record_type": "selected_intelligence_fusion_records",
            "selection_policy": "risk_blocked_event_overridden_conflicting_degraded_insufficient_then_cautionary_supportive",
            "max_records": MAX_RECORDS,
            "total_records": len(records),
            "selected_record_count": len(selected),
            "records": [_material_fusion_record(record) for record in selected],
        },
        "omissions": _omissions(records, selected),
        "report_usage_rules": _report_usage_rules(),
    }


def _source_policy(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_aware": True,
        "bounded_material": True,
        "source_artifacts": _unique_strings(
            [INTELLIGENCE_FUSION_ARTIFACT, *_string_list(artifact.get("source_artifacts"))]
        )[:MAX_ARTIFACTS],
        "full_intelligence_fusion_json_embedded": False,
        "full_upstream_json_embedded": False,
        "full_raw_streams_embedded": False,
        "full_reusable_histories_embedded": False,
        "codex_may_explain_fusion_context": True,
        "codex_may_generate_fusion_states": False,
        "codex_may_generate_risk_overrides": False,
        "codex_may_generate_event_overrides": False,
        "codex_may_generate_alert_priorities": False,
        "codex_may_generate_action_levels": False,
        "codex_may_generate_price_forecasts": False,
        "financial_advice": False,
    }


def _fusion_overview(artifact: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    counts = _dict(artifact.get("counts"))
    return {
        "record_type": "intelligence_fusion_overview",
        "run_id": artifact.get("run_id"),
        "created_at": artifact.get("created_at"),
        "status": artifact.get("status"),
        "record_count": len(records),
        "state_counts": _dict(counts.get("state_counts")) or _count_by(records, "state"),
        "confluence_counts": _dict(counts.get("confluence_counts")),
        "conflict_counts": _dict(counts.get("conflict_counts")),
        "risk_override_counts": _dict(counts.get("risk_override_counts")),
        "event_override_counts": _dict(counts.get("event_override_counts")),
        "outcome_feedback_counts": _dict(counts.get("outcome_feedback_counts")),
        "warnings": _string_list(artifact.get("warnings"))[:MAX_MESSAGES],
        "errors": _error_messages(artifact.get("errors"))[:MAX_MESSAGES],
    }


def _state_summary(artifact: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "record_type": "intelligence_fusion_state_summary",
        "highest_priority_states": [
            {
                "state": state,
                "records": count,
            }
            for state, count in _count_by(records, "state").items()
            if count > 0
        ],
        "records_with_blocking_risk": sum(
            1 for record in records if _dict(record.get("risk_override")).get("state") == "block"
        ),
        "records_with_event_override": sum(
            1 for record in records if _dict(record.get("event_override")).get("state") == "block"
        ),
        "records_with_severe_conflict": sum(
            1 for record in records if _dict(record.get("conflict")).get("state") == "severe"
        ),
        "source_artifacts": _unique_strings(
            [INTELLIGENCE_FUSION_ARTIFACT, *_string_list(artifact.get("source_artifacts"))]
        )[:MAX_ARTIFACTS],
    }


def _material_fusion_record(record: dict[str, Any]) -> dict[str, Any]:
    confluence = _dict(record.get("confluence"))
    conflict = _dict(record.get("conflict"))
    risk_override = _dict(record.get("risk_override"))
    event_override = _dict(record.get("event_override"))
    outcome_feedback = _dict(record.get("outcome_feedback"))
    return {
        "record_type": "intelligence_fusion_record",
        "fusion_record_id": record.get("fusion_record_id"),
        "scope": _dict(record.get("scope")),
        "state": record.get("state"),
        "direction": record.get("direction"),
        "confidence": record.get("confidence"),
        "confluence": {
            "state": confluence.get("state"),
            "supporting_sources": confluence.get("supporting_sources"),
            "independent_sources": confluence.get("independent_sources"),
            "source_layers": _string_list(confluence.get("source_layers"))[:MAX_MESSAGES],
        },
        "conflict": {
            "state": conflict.get("state"),
            "conflicting_sources": conflict.get("conflicting_sources"),
            "source_layers": _string_list(conflict.get("source_layers"))[:MAX_MESSAGES],
        },
        "risk_override": {
            "state": risk_override.get("state"),
            "risk_level": risk_override.get("risk_level"),
            "reasons": _string_list(risk_override.get("reasons"))[:MAX_MESSAGES],
        },
        "event_override": {
            "state": event_override.get("state"),
            "severity": event_override.get("severity"),
            "reasons": _string_list(event_override.get("reasons"))[:MAX_MESSAGES],
        },
        "outcome_feedback": {
            "state": outcome_feedback.get("state"),
            "source_records": outcome_feedback.get("source_records"),
        },
        "evidence": _string_list(record.get("evidence"))[:MAX_MESSAGES],
        "uncertainty": _string_list(record.get("uncertainty"))[:MAX_MESSAGES],
        "warnings": _string_list(record.get("warnings"))[:MAX_MESSAGES],
        "source_artifacts": _string_list(record.get("source_artifacts"))[:MAX_ARTIFACTS],
        "source_record_refs": _source_record_refs(record.get("source_record_refs")),
    }


def _omissions(records: list[dict[str, Any]], selected: list[dict[str, Any]]) -> dict[str, Any]:
    selected_ids = {id(record) for record in selected}
    omitted = [record for record in records if id(record) not in selected_ids]
    return {
        "record_type": "intelligence_fusion_material_omissions",
        "total_records": len(records),
        "selected_record_count": len(selected),
        "omitted_record_count": len(omitted),
        "omitted_state_counts": _count_by(omitted, "state"),
        "omission_reason": "bounded_material_record_limit" if omitted else None,
    }


def _report_usage_rules() -> dict[str, Any]:
    return {
        "codex_may_explain_intelligence_fusion": True,
        "codex_may_explain_confluence_and_conflict": True,
        "codex_may_explain_risk_and_event_overrides": True,
        "codex_may_explain_outcome_feedback": True,
        "codex_may_generate_fusion_states": False,
        "codex_may_generate_risk_overrides": False,
        "codex_may_generate_event_overrides": False,
        "codex_may_generate_alert_priority": False,
        "codex_may_generate_action_levels": False,
        "codex_may_generate_price_forecasts": False,
        "codex_may_create_trading_instructions": False,
        "financial_advice": False,
    }


def _select_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(records, key=_record_sort_key)[:MAX_RECORDS]


def _record_sort_key(record: dict[str, Any]) -> tuple[int, str, str]:
    state = str(record.get("state") or "unknown")
    scope = _dict(record.get("scope"))
    return (
        STATE_PRIORITY.get(state, 99),
        str(scope.get("symbol") or ""),
        str(scope.get("timeframe") or ""),
    )


def _read_fusion_artifact(run: RunContext) -> dict[str, Any]:
    path = run.analysis_dir / "intelligence_fusion.json"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{INTELLIGENCE_FUSION_ARTIFACT} was not found; build_intelligence_fusion must run first.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    except JSONDecodeError as exc:
        raise PipelineError(
            f"{INTELLIGENCE_FUSION_ARTIFACT} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    if not isinstance(loaded, dict):
        raise PipelineError(f"{INTELLIGENCE_FUSION_ARTIFACT} must contain a JSON object.", stage=STAGE_NAME, exit_code=3)
    if loaded.get("artifact_type") != "intelligence_fusion":
        raise PipelineError(
            f"{INTELLIGENCE_FUSION_ARTIFACT} must have artifact_type intelligence_fusion.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    if not isinstance(loaded.get("records"), list):
        raise PipelineError(f"{INTELLIGENCE_FUSION_ARTIFACT} must contain a records list.", stage=STAGE_NAME, exit_code=3)
    return loaded


def _yaml_block(data: dict[str, Any]) -> str:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise PipelineError("PyYAML is required to write intelligence fusion material.", stage=STAGE_NAME, exit_code=1) from exc
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def _count_by(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(record.get(field) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (STATE_PRIORITY.get(item[0], 99), item[0])))


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


def _error_messages(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    messages = []
    for item in value:
        if isinstance(item, dict):
            message = item.get("message")
            messages.append(str(message) if message else str(item))
        elif isinstance(item, str) and item:
            messages.append(item)
    return messages


def _source_record_refs(value: Any) -> list[dict[str, Any]]:
    refs = []
    for item in _dict_list(value):
        refs.append(
            {
                "source_layer": item.get("source_layer"),
                "source_artifact": item.get("source_artifact"),
                "source_record_id": item.get("source_record_id"),
            }
        )
    return refs[:MAX_ARTIFACTS]


def _unique_strings(values: list[str]) -> list[str]:
    unique = []
    for value in values:
        if value and value not in unique:
            unique.append(value)
    return unique
