from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any

from halpha.pipeline import PipelineError, RunContext


STAGE_NAME = "build_macro_calendar_material"
MACRO_CALENDAR_CONTEXT_ARTIFACT = "analysis/macro_calendar_context.json"
MACRO_CALENDAR_MATERIAL_ARTIFACT = "analysis/macro_calendar_material.md"
MAX_RECORDS_PER_SECTION = 4
MAX_MESSAGES = 8
MAX_ARTIFACTS = 16
MAX_EVIDENCE_ITEMS = 5

LIMITED_STATUSES = {"failed", "unavailable", "stale", "degraded", "partial"}


def build_macro_calendar_material(config: dict[str, Any], run: RunContext) -> list[str]:
    if not _macro_calendar_enabled(config):
        _record_zero_counts(run)
        return []

    context = _read_context(run)
    material_record = _material_record(context)
    material = render_macro_calendar_material(material_record)
    output_path = run.analysis_dir / "macro_calendar_material.md"
    output_path.write_text(material, encoding="utf-8")

    run.manifest["artifacts"]["macro_calendar_material"] = MACRO_CALENDAR_MATERIAL_ARTIFACT
    run.manifest["counts"]["macro_calendar_material_records"] = material_record["selected_record_count"]
    run.manifest["counts"]["macro_calendar_material_omitted_records"] = material_record["omitted_record_count"]
    run.manifest["macro_calendar_material"] = {
        "status": material_record["status"],
        "artifact": MACRO_CALENDAR_MATERIAL_ARTIFACT,
        "source_artifacts": [MACRO_CALENDAR_CONTEXT_ARTIFACT],
        "context_records": material_record["context_record_count"],
        "selected_records": material_record["selected_record_count"],
        "omitted_records": material_record["omitted_record_count"],
        "context_type_counts": material_record["macro_calendar_overview"]["context_type_counts"],
        "status_counts": material_record["macro_calendar_overview"]["status_counts"],
    }
    return [MACRO_CALENDAR_MATERIAL_ARTIFACT]


def render_macro_calendar_material(material_record: dict[str, Any]) -> str:
    lines = [
        "---",
        "artifact_type: analysis_macro_calendar_material",
        "schema_version: 1",
        "audience: ai",
        "source_artifacts:",
        f"  - {MACRO_CALENDAR_CONTEXT_ARTIFACT}",
        "---",
        "",
        "# macro_calendar_material",
        "",
    ]
    for section in (
        "source_policy",
        "macro_calendar_overview",
        "material_budget",
        "scheduled_catalysts",
        "recent_catalysts",
        "no_event_and_unavailable_sources",
        "data_quality",
        "downstream_implications",
        "report_usage_rules",
        "selected_records",
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


def _material_record(context: dict[str, Any]) -> dict[str, Any]:
    records = _records(context)
    scheduled_records = _filter_by_context_type(records, {"scheduled_catalyst"})
    recent_records = _filter_by_context_type(records, {"recent_catalyst"})
    no_event_and_unavailable_records = [
        record
        for record in records
        if record.get("context_type") in {"no_event_window", "source_availability"}
        or _clean_text(record.get("status"), fallback="unknown") in LIMITED_STATUSES
    ]
    scheduled_selected = _select_records(scheduled_records, limit=MAX_RECORDS_PER_SECTION)
    recent_selected = _select_records(recent_records, limit=MAX_RECORDS_PER_SECTION)
    no_event_and_unavailable_selected = _select_records(
        no_event_and_unavailable_records,
        limit=MAX_RECORDS_PER_SECTION,
    )
    scheduled = _section_record(
        records,
        section_name="scheduled_catalysts",
        records=scheduled_records,
        selected=scheduled_selected,
    )
    recent = _section_record(
        records,
        section_name="recent_catalysts",
        records=recent_records,
        selected=recent_selected,
    )
    no_event_and_unavailable = _section_record(
        records,
        section_name="no_event_and_unavailable_sources",
        records=no_event_and_unavailable_records,
        selected=no_event_and_unavailable_selected,
    )
    selected_records = _unique_records(
        [
            *[_record_summary(record) for record in scheduled_selected],
            *[_record_summary(record) for record in recent_selected],
            *[_record_summary(record) for record in no_event_and_unavailable_selected],
        ]
    )
    selected_count = len(selected_records)
    context_count = len(records)
    omitted_count = max(0, context_count - selected_count)
    overview = {
        "record_type": "macro_calendar_overview",
        "run_id": context.get("run_id"),
        "created_at": context.get("created_at"),
        "status": context.get("status") or "unknown",
        "context_record_count": context_count,
        "selected_record_count": selected_count,
        "omitted_record_count": omitted_count,
        "selected_record_limit_per_section": MAX_RECORDS_PER_SECTION,
        "counts": _mapping(context.get("counts")),
        "context_type_counts": _counts_by(records, "context_type"),
        "status_counts": _counts_by(records, "status"),
        "state_counts": _counts_by(records, "state"),
        "severity_counts": _counts_by(records, "severity"),
        "source_availability_counts": _counts_by(records, "source_availability"),
        "source_artifacts": _bounded_artifacts(_string_list(context.get("source_artifacts"))),
        "warnings": _bounded_messages(_string_list(context.get("warnings"))),
        "errors": _bounded_errors(_list(context.get("errors"))),
    }
    budget = {
        "record_type": "macro_calendar_material_budget",
        "context_record_count": context_count,
        "selected_record_count": selected_count,
        "omitted_record_count": omitted_count,
        "omitted_by_context_type": _omitted_counts(records, selected_records, field="context_type"),
        "omitted_by_status": _omitted_counts(records, selected_records, field="status"),
        "selection_policy": [
            "high-severity or high-importance scheduled catalysts first",
            "recent scheduled catalysts next",
            "no-event, unavailable, stale, degraded, partial, and failed source states as representative evidence",
            "low-signal remainder omitted with counts",
        ],
    }
    return {
        "source_policy": _source_policy(),
        "macro_calendar_overview": overview,
        "material_budget": budget,
        "scheduled_catalysts": scheduled,
        "recent_catalysts": recent,
        "no_event_and_unavailable_sources": no_event_and_unavailable,
        "data_quality": _data_quality_record(context, records),
        "downstream_implications": _downstream_implications(selected_records),
        "report_usage_rules": _report_usage_rules(),
        "selected_records": {
            "record_type": "macro_calendar_selected_records",
            "records": selected_records,
        },
        "status": overview["status"],
        "context_record_count": context_count,
        "selected_record_count": selected_count,
        "omitted_record_count": omitted_count,
    }


def _section_record(
    all_records: list[dict[str, Any]],
    *,
    section_name: str,
    records: list[dict[str, Any]],
    selected: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "record_type": f"macro_calendar_{section_name}",
        "total_records": len(records),
        "selected_context_ids": [_clean_text(record.get("context_id"), fallback="") for record in selected],
        "selected_record_summaries": [_section_record_summary(record) for record in selected],
        "omitted_record_count": max(0, len(records) - len(selected)),
        "total_context_records": len(all_records),
        "status_counts": _counts_by(records, "status"),
        "state_counts": _counts_by(records, "state"),
        "severity_counts": _counts_by(records, "severity"),
    }


def _section_record_summary(record: dict[str, Any]) -> dict[str, Any]:
    realized_impact = _mapping(record.get("realized_impact"))
    return {
        "context_id": record.get("context_id"),
        "context_type": record.get("context_type"),
        "event_name": record.get("event_name"),
        "region": record.get("region"),
        "scheduled_at": record.get("scheduled_at"),
        "status": record.get("status"),
        "state": record.get("state"),
        "severity": record.get("severity"),
        "source_availability": record.get("source_availability"),
        "realized_impact_status": realized_impact.get("status") or "unknown",
    }


def _record_summary(record: dict[str, Any]) -> dict[str, Any]:
    realized_impact = _mapping(record.get("realized_impact"))
    return {
        "context_id": record.get("context_id"),
        "context_type": record.get("context_type"),
        "data_class": record.get("data_class"),
        "source": record.get("source"),
        "event_name": record.get("event_name"),
        "event_type": record.get("event_type"),
        "region": record.get("region"),
        "scheduled_at": record.get("scheduled_at"),
        "as_of": record.get("as_of"),
        "status": record.get("status"),
        "state": record.get("state"),
        "severity": record.get("severity"),
        "confidence": record.get("confidence"),
        "time_to_event_hours": record.get("time_to_event_hours"),
        "affected_assets": _string_list(record.get("affected_assets")),
        "importance": record.get("importance"),
        "source_availability": record.get("source_availability"),
        "realized_impact": {
            "status": realized_impact.get("status") or "unknown",
            "reason": realized_impact.get("reason"),
        },
        "evidence": _bounded_evidence(_list(record.get("evidence"))),
        "uncertainty": _bounded_messages(_string_list(record.get("uncertainty"))),
        "warnings": _bounded_messages(_string_list(record.get("warnings"))),
        "errors": _bounded_errors(_list(record.get("errors"))),
        "source_artifacts": _bounded_artifacts(_string_list(record.get("source_artifacts"))),
    }


def _source_policy() -> dict[str, Any]:
    return {
        "record_type": "macro_calendar_source_policy",
        "codex_may_explain_macro_calendar_context": True,
        "codex_may_generate_macro_events": False,
        "codex_may_generate_macro_states": False,
        "codex_may_generate_risk_levels": False,
        "codex_may_generate_watch_triggers": False,
        "codex_may_generate_alert_priorities": False,
        "codex_may_infer_missing_source_data": False,
        "codex_may_infer_missing_event_times_or_time_zones": False,
        "codex_may_infer_realized_market_impact": False,
        "codex_may_forecast_macro_outcomes": False,
        "codex_may_generate_price_forecasts": False,
        "codex_may_create_trading_instructions": False,
        "full_raw_macro_calendar_artifacts_embedded": False,
        "full_reusable_macro_calendar_history_embedded": False,
        "full_macro_calendar_views_embedded": False,
        "full_macro_calendar_context_json_embedded": False,
        "selected_context_records_only": True,
    }


def _data_quality_record(context: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    limited = [
        record
        for record in records
        if _clean_text(record.get("status"), fallback="unknown") in LIMITED_STATUSES
        or _clean_text(record.get("source_availability"), fallback="unknown") in LIMITED_STATUSES
    ]
    no_event = [record for record in records if record.get("context_type") == "no_event_window"]
    return {
        "record_type": "macro_calendar_data_quality",
        "status": context.get("status") or "unknown",
        "source_limited_record_count": len(limited),
        "no_event_window_count": len(no_event),
        "warning_count": len(_string_list(context.get("warnings"))),
        "error_count": len(_list(context.get("errors"))),
        "status_counts": _counts_by(records, "status"),
        "source_availability_counts": _counts_by(records, "source_availability"),
        "warnings": _bounded_messages(_string_list(context.get("warnings"))),
        "errors": _bounded_errors(_list(context.get("errors"))),
        "source_artifacts": _bounded_artifacts(
            [
                MACRO_CALENDAR_CONTEXT_ARTIFACT,
                *_string_list(context.get("source_artifacts")),
            ]
        ),
    }


def _downstream_implications(selected_records: list[dict[str, Any]]) -> dict[str, Any]:
    scheduled = [record for record in selected_records if record.get("context_type") == "scheduled_catalyst"]
    recent = [record for record in selected_records if record.get("context_type") == "recent_catalyst"]
    source_limited = [
        record
        for record in selected_records
        if record.get("context_type") == "source_availability"
        or _clean_text(record.get("status"), fallback="unknown") in LIMITED_STATUSES
    ]
    no_event = [record for record in selected_records if record.get("context_type") == "no_event_window"]
    return {
        "record_type": "macro_calendar_downstream_implications",
        "macro_calendar_context_is_supporting_evidence_only": True,
        "scheduled_catalyst_is_not_realized_market_impact": True,
        "use_downstream_halpha_artifacts_for_action_language": True,
        "scheduled_catalysts_selected": len(scheduled),
        "recent_catalysts_selected": len(recent),
        "source_limited_records_selected": len(source_limited),
        "no_event_records_selected": len(no_event),
        "implications": _unique(
            [
                *(
                    [
                        "Scheduled catalysts may explain timing risk and uncertainty when linked by downstream Halpha artifacts."
                    ]
                    if scheduled
                    else []
                ),
                *(
                    [
                        "Recent catalysts are event-timing evidence only; realized market response is not evaluated by this material."
                    ]
                    if recent
                    else []
                ),
                *(
                    [
                        "Unavailable, stale, degraded, partial, or failed macro/calendar evidence is source uncertainty, not neutral evidence."
                    ]
                    if source_limited
                    else []
                ),
                *(
                    [
                        "No-event windows do not prove that macro risk is absent."
                    ]
                    if no_event
                    else []
                ),
                "Codex should explain macro/calendar implications only from Halpha-generated material and downstream Halpha artifacts.",
            ]
        ),
    }


def _report_usage_rules() -> dict[str, Any]:
    return {
        "record_type": "macro_calendar_report_usage_rules",
        "may_explain": [
            "scheduled catalyst timing risk",
            "recent scheduled catalyst context",
            "no-event windows",
            "source availability, freshness, time-zone, and data-quality limits",
            "whether downstream Halpha artifacts linked macro/calendar context to risk, watch, event, alert, or decision evidence",
        ],
        "must_distinguish": [
            "upcoming scheduled catalyst versus confirmed realized market impact",
            "recent catalyst timing versus confirmed market response",
            "no-event window versus absence of macro risk",
            "source uncertainty versus low risk",
        ],
        "must_not_generate": [
            "macro/calendar records",
            "macro/calendar states",
            "risk levels",
            "watch triggers",
            "alert priorities",
            "trading signals",
            "economic-release forecasts",
            "policy-outcome forecasts",
            "asset price forecasts",
            "trading instructions",
            "position sizing",
            "account actions",
        ],
    }


def _select_records(records: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    return sorted(records, key=_record_sort_key)[:limit]


def _record_sort_key(record: dict[str, Any]) -> tuple[int, int, int, float, str, str]:
    severity_order = {"high": 0, "medium": 1, "unknown": 2, "low": 3}
    status_order = {
        "failed": 0,
        "unavailable": 1,
        "stale": 2,
        "degraded": 3,
        "partial": 4,
        "succeeded": 5,
        "no_event": 6,
    }
    type_order = {
        "scheduled_catalyst": 0,
        "recent_catalyst": 1,
        "source_availability": 2,
        "no_event_window": 3,
    }
    hours = record.get("time_to_event_hours")
    hours_value = abs(float(hours)) if isinstance(hours, int | float) else 999999.0
    return (
        severity_order.get(_clean_text(record.get("severity"), fallback="unknown"), 2),
        status_order.get(_clean_text(record.get("status"), fallback="unknown"), 7),
        type_order.get(_clean_text(record.get("context_type"), fallback="unknown"), 4),
        hours_value,
        _clean_text(record.get("scheduled_at"), fallback=""),
        _clean_text(record.get("context_id"), fallback=""),
    )


def _read_context(run: RunContext) -> dict[str, Any]:
    try:
        loaded = json.loads((run.analysis_dir / "macro_calendar_context.json").read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{MACRO_CALENDAR_CONTEXT_ARTIFACT} was not found; build_macro_calendar_context must run first.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    except JSONDecodeError as exc:
        raise PipelineError(
            f"{MACRO_CALENDAR_CONTEXT_ARTIFACT} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    if not isinstance(loaded, dict):
        raise PipelineError(
            f"{MACRO_CALENDAR_CONTEXT_ARTIFACT} must be a JSON object.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    if loaded.get("artifact_type") != "macro_calendar_context":
        raise PipelineError(
            f"{MACRO_CALENDAR_CONTEXT_ARTIFACT} must have artifact_type macro_calendar_context.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    if not isinstance(loaded.get("records"), list):
        raise PipelineError(
            f"{MACRO_CALENDAR_CONTEXT_ARTIFACT} must contain records as a list.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    return loaded


def _records(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [record for record in _list(context.get("records")) if isinstance(record, dict)]


def _filter_by_context_type(records: list[dict[str, Any]], context_types: set[str]) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if _clean_text(record.get("context_type"), fallback="unknown") in context_types
    ]


def _unique_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        key = _clean_text(record.get("context_id"), fallback="")
        if not key:
            key = "|".join(
                [
                    _clean_text(record.get("context_type"), fallback="unknown"),
                    _clean_text(record.get("source"), fallback="unknown"),
                    _clean_text(record.get("event_name"), fallback="unknown"),
                    _clean_text(record.get("scheduled_at"), fallback="unknown"),
                ]
            )
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)
    return unique


def _omitted_counts(
    records: list[dict[str, Any]],
    selected_records: list[dict[str, Any]],
    *,
    field: str,
) -> dict[str, int]:
    selected_ids = {
        _clean_text(record.get("context_id"), fallback="")
        for record in selected_records
        if _clean_text(record.get("context_id"), fallback="")
    }
    omitted = [
        record
        for record in records
        if _clean_text(record.get("context_id"), fallback="") not in selected_ids
    ]
    return _counts_by(omitted, field)


def _macro_calendar_enabled(config: dict[str, Any]) -> bool:
    macro_calendar = config.get("macro_calendar")
    return isinstance(macro_calendar, dict) and macro_calendar.get("enabled") is True


def _record_zero_counts(run: RunContext) -> None:
    run.manifest["counts"]["macro_calendar_material_records"] = 0
    run.manifest["counts"]["macro_calendar_material_omitted_records"] = 0


def _bounded_evidence(values: list[Any]) -> list[Any]:
    evidence = []
    for value in values[:MAX_EVIDENCE_ITEMS]:
        if isinstance(value, dict):
            evidence.append(_bounded_mapping(value, limit=10))
        elif isinstance(value, str) and value:
            evidence.append(value)
    return evidence


def _bounded_mapping(value: dict[str, Any], *, limit: int) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in sorted(value)[:limit]:
        item = value[key]
        if isinstance(item, bool | int | float | str) or item is None:
            result[key] = item
    return result


def _counts_by(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = _clean_text(record.get(field), fallback="unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _bounded_artifacts(values: list[Any]) -> list[str]:
    return sorted({str(value) for value in values if isinstance(value, str) and value})[:MAX_ARTIFACTS]


def _bounded_messages(values: list[Any]) -> list[str]:
    return [str(value) for value in values if isinstance(value, str) and value][:MAX_MESSAGES]


def _bounded_errors(values: list[Any]) -> list[Any]:
    errors: list[Any] = []
    for value in values[:MAX_MESSAGES]:
        if isinstance(value, dict):
            errors.append(_bounded_mapping(value, limit=8))
        elif isinstance(value, str) and value:
            errors.append(value)
    return errors


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _clean_text(value: Any, *, fallback: str) -> str:
    text = str(value).strip() if value is not None else ""
    return text or fallback


def _unique(values: list[str]) -> list[str]:
    unique: list[str] = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return unique


def _yaml_block(data: dict[str, Any]) -> str:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise PipelineError(
            "PyYAML is required to write YAML macro calendar material.",
            stage=STAGE_NAME,
            exit_code=1,
        ) from exc

    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
