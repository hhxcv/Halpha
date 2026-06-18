from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any

from halpha.pipeline import PipelineError, RunContext


STAGE_NAME = "build_analysis_materials"
DERIVATIVES_MARKET_CONTEXT_ARTIFACT = "analysis/derivatives_market_context.json"
DATA_QUALITY_SUMMARY_ARTIFACT = "analysis/data_quality_summary.json"
DERIVATIVES_MARKET_MATERIAL_ARTIFACT = "analysis/derivatives_market_material.md"
MAX_RECORDS_PER_SECTION = 4
MAX_MESSAGES = 6
MAX_ARTIFACTS = 16
MAX_METRICS = 10

SECTION_TYPES = {
    "funding_and_leverage": {"funding_pressure", "open_interest_pressure"},
    "premium_and_basis": {"premium_basis_state"},
    "liquidity_and_depth": {"liquidity_depth_state"},
    "liquidation_source_availability": {"liquidation_availability"},
}


def build_derivatives_market_material(config: dict[str, Any], run: RunContext) -> list[str]:
    if not _derivatives_enabled(config):
        _record_zero_counts(run)
        return []

    context = _read_context(run)
    data_quality = _read_optional_data_quality_summary(run)
    material_record = _material_record(context, data_quality_summary=data_quality)
    material = render_derivatives_market_material(material_record)
    output_path = run.analysis_dir / "derivatives_market_material.md"
    output_path.write_text(material, encoding="utf-8")

    run.manifest["artifacts"]["derivatives_market_material"] = DERIVATIVES_MARKET_MATERIAL_ARTIFACT
    run.manifest["counts"]["derivatives_market_material_records"] = material_record["selected_record_count"]
    run.manifest["counts"]["derivatives_market_material_omitted_records"] = material_record["omitted_record_count"]
    run.manifest["derivatives_market_material"] = {
        "status": material_record["status"],
        "artifact": DERIVATIVES_MARKET_MATERIAL_ARTIFACT,
        "source_artifacts": [DERIVATIVES_MARKET_CONTEXT_ARTIFACT],
        "selected_records": material_record["selected_record_count"],
        "omitted_records": material_record["omitted_record_count"],
        "context_records": material_record["context_record_count"],
    }
    return [DERIVATIVES_MARKET_MATERIAL_ARTIFACT]


def render_derivatives_market_material(material_record: dict[str, Any]) -> str:
    lines = [
        "---",
        "artifact_type: analysis_derivatives_market_material",
        "schema_version: 1",
        "audience: ai",
        "source_artifacts:",
        f"  - {DERIVATIVES_MARKET_CONTEXT_ARTIFACT}",
    ]
    if material_record["data_quality"]["status"] != "not_available":
        lines.append(f"  - {DATA_QUALITY_SUMMARY_ARTIFACT}")
    lines.extend(
        [
            "---",
            "",
            "# derivatives_market_material",
            "",
        ]
    )
    for section in (
        "source_policy",
        "derivatives_overview",
        "funding_and_leverage",
        "premium_and_basis",
        "liquidity_and_depth",
        "liquidation_source_availability",
        "data_quality",
        "downstream_implications",
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
    return "\n".join(lines)


def _material_record(
    context: dict[str, Any],
    *,
    data_quality_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    records = _records(context)
    sections = {
        section: _section_record(records, context_types=context_types)
        for section, context_types in SECTION_TYPES.items()
    }
    selected_count = sum(len(section["selected_records"]) for section in sections.values())
    context_count = len(records)
    omitted_count = max(0, context_count - selected_count)
    overview = {
        "record_type": "derivatives_market_overview",
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
        "severity_counts": _counts_by(records, "severity"),
        "state_counts": _counts_by(records, "state"),
        "source_artifacts": _bounded_artifacts(_string_list(context.get("source_artifacts"))),
        "warnings": _bounded_messages(_string_list(context.get("warnings"))),
        "errors": _bounded_messages(_string_list(context.get("errors"))),
    }
    return {
        "source_policy": _source_policy(),
        "derivatives_overview": overview,
        "funding_and_leverage": sections["funding_and_leverage"],
        "premium_and_basis": sections["premium_and_basis"],
        "liquidity_and_depth": sections["liquidity_and_depth"],
        "liquidation_source_availability": sections["liquidation_source_availability"],
        "data_quality": _data_quality_record(data_quality_summary),
        "downstream_implications": _downstream_implications(sections),
        "report_usage_rules": _report_usage_rules(),
        "status": overview["status"],
        "context_record_count": context_count,
        "selected_record_count": selected_count,
        "omitted_record_count": omitted_count,
    }


def _section_record(records: list[dict[str, Any]], *, context_types: set[str]) -> dict[str, Any]:
    section_records = [
        record
        for record in records
        if _clean_text(record.get("context_type"), fallback="unknown") in context_types
    ]
    selected = _select_records(section_records, limit=MAX_RECORDS_PER_SECTION)
    return {
        "total_records": len(section_records),
        "selected_records": [_record_summary(record) for record in selected],
        "omitted_record_count": max(0, len(section_records) - len(selected)),
        "status_counts": _counts_by(section_records, "status"),
        "state_counts": _counts_by(section_records, "state"),
        "severity_counts": _counts_by(section_records, "severity"),
    }


def _record_summary(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "context_id": record.get("context_id"),
        "context_type": record.get("context_type"),
        "data_class": record.get("data_class"),
        "source": record.get("source"),
        "market_type": record.get("market_type"),
        "symbol": record.get("symbol"),
        "period": record.get("period"),
        "as_of": record.get("as_of"),
        "status": record.get("status"),
        "state": record.get("state"),
        "severity": record.get("severity"),
        "confidence": record.get("confidence"),
        "metrics": _bounded_mapping(_mapping(record.get("metrics")), limit=MAX_METRICS),
        "thresholds": _bounded_mapping(_mapping(record.get("thresholds")), limit=MAX_METRICS),
        "evidence": _bounded_evidence(_list(record.get("evidence"))),
        "uncertainty": _bounded_messages(_string_list(record.get("uncertainty"))),
        "warnings": _bounded_messages(_string_list(record.get("warnings"))),
        "errors": _bounded_messages(_string_list(record.get("errors"))),
        "source_artifacts": _bounded_artifacts(_string_list(record.get("source_artifacts"))),
    }


def _select_records(records: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    return sorted(records, key=_record_sort_key)[:limit]


def _record_sort_key(record: dict[str, Any]) -> tuple[int, int, str, str, str, str]:
    severity_order = {"high": 0, "medium": 1, "unknown": 2, "low": 3}
    status_order = {
        "failed": 0,
        "unavailable": 1,
        "stale": 2,
        "degraded": 3,
        "partial": 4,
        "insufficient": 5,
        "succeeded": 6,
    }
    severity = _clean_text(record.get("severity"), fallback="unknown")
    status = _clean_text(record.get("status"), fallback="unknown")
    return (
        severity_order.get(severity, 2),
        status_order.get(status, 6),
        _clean_text(record.get("context_type"), fallback="unknown"),
        _clean_text(record.get("symbol"), fallback="unknown"),
        _clean_text(record.get("period"), fallback="unknown"),
        _clean_text(record.get("context_id"), fallback="unknown"),
    )


def _source_policy() -> dict[str, Any]:
    return {
        "record_type": "derivatives_market_source_policy",
        "codex_may_explain_derivatives_context": True,
        "codex_may_generate_derivatives_states": False,
        "codex_may_generate_derivatives_signals": False,
        "codex_may_generate_risk_levels": False,
        "codex_may_infer_missing_market_structure_data": False,
        "codex_may_calculate_funding_open_interest_premium_basis_spread_depth_or_liquidations": False,
        "codex_may_generate_price_forecasts": False,
        "codex_may_create_trading_instructions": False,
        "full_raw_derivatives_artifacts_embedded": False,
        "full_reusable_derivatives_history_embedded": False,
        "full_derivatives_views_embedded": False,
        "full_derivatives_context_json_embedded": False,
        "selected_context_records_only": True,
    }


def _data_quality_record(summary: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(summary, dict):
        return {
            "record_type": "derivatives_market_data_quality",
            "status": "not_available",
            "checks": [],
            "warnings": [],
            "errors": [],
        }
    checks = [_quality_check(check) for check in _list(summary.get("checks")) if _is_derivatives_quality_check(check)]
    return {
        "record_type": "derivatives_market_data_quality",
        "status": summary.get("status") or "unknown",
        "checks": checks,
        "omitted_check_count": max(0, len(_list(summary.get("checks"))) - len(checks)),
        "warnings": _bounded_messages(_derivatives_quality_messages(_string_list(summary.get("warnings")))),
        "errors": _bounded_messages(_derivatives_quality_messages(_error_messages(summary.get("errors")))),
        "source_artifacts": _bounded_artifacts(
            [
                DATA_QUALITY_SUMMARY_ARTIFACT,
                *_string_list(summary.get("source_artifacts")),
            ]
        ),
    }


def _quality_check(check: Any) -> dict[str, Any]:
    if not isinstance(check, dict):
        return {
            "name": "invalid_derivatives_quality_check",
            "status": "failed",
            "summary": "data quality check is not a JSON object.",
            "source_artifacts": [],
            "warnings": [],
            "errors": ["data quality check is not a JSON object."],
        }
    details = _mapping(check.get("details"))
    return {
        "name": check.get("name") or "unknown",
        "scope": check.get("scope") or "unknown",
        "status": check.get("status") or "unknown",
        "summary": check.get("summary"),
        "warning_count": check.get("warning_count") or 0,
        "error_count": check.get("error_count") or 0,
        "source_artifacts": _bounded_artifacts(_string_list(check.get("source_artifacts"))),
        "warnings": _bounded_messages(_string_list(details.get("warnings"))),
        "errors": _bounded_messages(_string_list(details.get("errors"))),
    }


def _is_derivatives_quality_check(check: Any) -> bool:
    if not isinstance(check, dict):
        return False
    name = str(check.get("name") or "")
    if name.startswith("derivatives_") or name == "raw_derivatives_market":
        return True
    return any("derivatives" in artifact for artifact in _string_list(check.get("source_artifacts")))


def _derivatives_quality_messages(messages: list[str]) -> list[str]:
    return [message for message in messages if "derivatives" in message.lower()]


def _downstream_implications(sections: dict[str, dict[str, Any]]) -> dict[str, Any]:
    selected_records = [
        record
        for section in sections.values()
        for record in section["selected_records"]
    ]
    stress_records = [
        record
        for record in selected_records
        if record.get("severity") in {"high", "medium"}
        and record.get("status") not in {"unavailable", "stale", "failed"}
    ]
    unavailable_records = [
        record
        for record in selected_records
        if record.get("status") in {"unavailable", "stale", "degraded", "partial", "failed"}
        or record.get("state") in {"unavailable", "stale", "insufficient_evidence"}
    ]
    return {
        "record_type": "derivatives_market_downstream_implications",
        "derivatives_context_is_supporting_evidence_only": True,
        "use_downstream_halpha_artifacts_for_action_language": True,
        "stress_records_selected": len(stress_records),
        "availability_or_quality_limited_records_selected": len(unavailable_records),
        "implications": _unique(
            [
                *(
                    [
                        "Supported medium or high severity derivatives context may qualify regime, risk, decision, watch, or alert interpretation."
                    ]
                    if stress_records
                    else []
                ),
                *(
                    [
                        "Unavailable, stale, degraded, partial, or failed derivatives context is uncertainty evidence, not neutral market evidence."
                    ]
                    if unavailable_records
                    else []
                ),
                "Codex should explain derivatives implications only from Halpha-generated material and downstream Halpha artifacts.",
            ]
        ),
    }


def _report_usage_rules() -> dict[str, Any]:
    return {
        "record_type": "derivatives_market_report_usage_rules",
        "may_explain": [
            "funding pressure",
            "open-interest pressure",
            "premium or basis stress",
            "bounded spread or depth degradation",
            "liquidation-source availability limits",
            "source and data-quality uncertainty",
        ],
        "must_not_generate": [
            "derivatives states",
            "risk levels",
            "market-structure signals",
            "liquidation summaries from missing sources",
            "price forecasts",
            "trading instructions",
            "position sizing",
            "account actions",
        ],
    }


def _read_context(run: RunContext) -> dict[str, Any]:
    try:
        loaded = json.loads((run.analysis_dir / "derivatives_market_context.json").read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{DERIVATIVES_MARKET_CONTEXT_ARTIFACT} was not found; build_derivatives_market_context must run first.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    except JSONDecodeError as exc:
        raise PipelineError(
            f"{DERIVATIVES_MARKET_CONTEXT_ARTIFACT} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    if not isinstance(loaded, dict):
        raise PipelineError(
            f"{DERIVATIVES_MARKET_CONTEXT_ARTIFACT} must be a JSON object.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    if loaded.get("artifact_type") != "derivatives_market_context":
        raise PipelineError(
            f"{DERIVATIVES_MARKET_CONTEXT_ARTIFACT} must have artifact_type derivatives_market_context.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    if not isinstance(loaded.get("records"), list):
        raise PipelineError(
            f"{DERIVATIVES_MARKET_CONTEXT_ARTIFACT} must contain records as a list.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    return loaded


def _read_optional_data_quality_summary(run: RunContext) -> dict[str, Any] | None:
    try:
        loaded = json.loads((run.analysis_dir / "data_quality_summary.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, JSONDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _records(context: dict[str, Any]) -> list[dict[str, Any]]:
    return [record for record in _list(context.get("records")) if isinstance(record, dict)]


def _derivatives_enabled(config: dict[str, Any]) -> bool:
    market = config.get("market")
    derivatives = market.get("derivatives") if isinstance(market, dict) else None
    return isinstance(derivatives, dict) and derivatives.get("enabled") is True


def _record_zero_counts(run: RunContext) -> None:
    run.manifest["counts"]["derivatives_market_material_records"] = 0
    run.manifest["counts"]["derivatives_market_material_omitted_records"] = 0


def _bounded_evidence(values: list[Any]) -> list[Any]:
    evidence = []
    for value in values[:MAX_MESSAGES]:
        if isinstance(value, dict):
            evidence.append(_bounded_mapping(value, limit=MAX_METRICS))
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


def _error_messages(values: Any) -> list[str]:
    messages = []
    for value in _list(values):
        if isinstance(value, str):
            messages.append(value)
        elif isinstance(value, dict):
            message = value.get("message")
            if isinstance(message, str):
                messages.append(message)
    return messages


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _clean_text(value: Any, *, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


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
            "PyYAML is required to write YAML derivatives market material.",
            stage=STAGE_NAME,
            exit_code=1,
        ) from exc

    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
