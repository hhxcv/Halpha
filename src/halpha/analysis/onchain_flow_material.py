from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any

from halpha.runtime.pipeline_contracts import PipelineError, RunContext


STAGE_NAME = "build_onchain_flow_material"
ONCHAIN_FLOW_CONTEXT_ARTIFACT = "analysis/onchain_flow_context.json"
ONCHAIN_FLOW_MATERIAL_ARTIFACT = "analysis/onchain_flow_material.md"
MAX_RECORDS_PER_SECTION = 4
MAX_MESSAGES = 4
MAX_ARTIFACTS = 8
MAX_EVIDENCE_ITEMS = 1
MAX_MAPPING_ITEMS = 4

LIMITED_STATUSES = {"failed", "unavailable", "stale", "degraded", "partial", "insufficient"}


def build_onchain_flow_material(config: dict[str, Any], run: RunContext) -> list[str]:
    if not _onchain_flow_enabled(config):
        _record_zero_counts(run)
        return []

    context = _read_context(run)
    material_record = _material_record(context)
    material = render_onchain_flow_material(material_record)
    output_path = run.analysis_dir / "onchain_flow_material.md"
    output_path.write_text(material, encoding="utf-8")

    run.manifest["artifacts"]["onchain_flow_material"] = ONCHAIN_FLOW_MATERIAL_ARTIFACT
    run.manifest["counts"]["onchain_flow_material_records"] = material_record["selected_record_count"]
    run.manifest["counts"]["onchain_flow_material_omitted_records"] = material_record["omitted_record_count"]
    run.manifest["onchain_flow_material"] = {
        "status": material_record["status"],
        "artifact": ONCHAIN_FLOW_MATERIAL_ARTIFACT,
        "source_artifacts": [ONCHAIN_FLOW_CONTEXT_ARTIFACT],
        "context_records": material_record["context_record_count"],
        "selected_records": material_record["selected_record_count"],
        "omitted_records": material_record["omitted_record_count"],
        "context_type_counts": material_record["onchain_flow_overview"]["context_type_counts"],
        "status_counts": material_record["onchain_flow_overview"]["status_counts"],
        "state_counts": material_record["onchain_flow_overview"]["state_counts"],
    }
    return [ONCHAIN_FLOW_MATERIAL_ARTIFACT]


def render_onchain_flow_material(material_record: dict[str, Any]) -> str:
    lines = [
        "---",
        "artifact_type: analysis_onchain_flow_material",
        "schema_version: 1",
        "audience: ai",
        "source_artifacts:",
        f"  - {ONCHAIN_FLOW_CONTEXT_ARTIFACT}",
        "---",
        "",
        "# onchain_flow_material",
        "",
    ]
    for section in (
        "source_policy",
        "onchain_flow_overview",
        "material_budget",
        "stablecoin_liquidity",
        "chain_activity",
        "network_congestion",
        "exchange_flow_source_availability",
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
    stablecoin_records = _filter_by_context_type(records, {"stablecoin_liquidity"})
    chain_activity_records = _filter_by_context_type(records, {"chain_activity"})
    congestion_records = _filter_by_context_type(records, {"network_congestion"})
    exchange_flow_records = _filter_by_context_type(records, {"exchange_flow_source_availability"})

    stablecoin_selected = _select_records(stablecoin_records, limit=MAX_RECORDS_PER_SECTION)
    chain_activity_selected = _select_records(chain_activity_records, limit=MAX_RECORDS_PER_SECTION)
    congestion_selected = _select_records(congestion_records, limit=MAX_RECORDS_PER_SECTION)
    exchange_flow_selected = _select_records(exchange_flow_records, limit=MAX_RECORDS_PER_SECTION)

    selected_records = _unique_records(
        [
            *[_record_summary(record) for record in stablecoin_selected],
            *[_record_summary(record) for record in chain_activity_selected],
            *[_record_summary(record) for record in congestion_selected],
            *[_record_summary(record) for record in exchange_flow_selected],
        ]
    )
    selected_count = len(selected_records)
    context_count = len(records)
    omitted_count = max(0, context_count - selected_count)
    overview = {
        "record_type": "onchain_flow_overview",
        "run_id": context.get("run_id"),
        "created_at": context.get("created_at"),
        "status": context.get("status") or "unknown",
        "context_record_count": context_count,
        "selected_record_count": selected_count,
        "omitted_record_count": omitted_count,
        "selected_record_limit_per_section": MAX_RECORDS_PER_SECTION,
        "context_type_counts": _counts_by(records, "context_type"),
        "status_counts": _counts_by(records, "status"),
        "state_counts": _counts_by(records, "state"),
        "severity_counts": _counts_by(records, "severity"),
        "source_artifacts": _bounded_artifacts(_string_list(context.get("source_artifacts"))),
    }
    budget = {
        "record_type": "onchain_flow_material_budget",
        "context_record_count": context_count,
        "selected_record_count": selected_count,
        "omitted_record_count": omitted_count,
        "omitted_by_context_type": _omitted_counts(records, selected_records, field="context_type"),
        "omitted_by_status": _omitted_counts(records, selected_records, field="status"),
        "selection_policy": [
            "high-severity and medium-severity on-chain context first",
            "source-limited, stale, unavailable, partial, failed, and insufficient records preserved as uncertainty evidence",
            "stablecoin liquidity, chain activity, network congestion, and exchange-flow availability represented separately",
            "low-signal remainder omitted with counts",
        ],
    }
    return {
        "source_policy": _source_policy(),
        "onchain_flow_overview": overview,
        "material_budget": budget,
        "stablecoin_liquidity": _section_record(
            records,
            section_name="stablecoin_liquidity",
            records=stablecoin_records,
            selected=stablecoin_selected,
        ),
        "chain_activity": _section_record(
            records,
            section_name="chain_activity",
            records=chain_activity_records,
            selected=chain_activity_selected,
        ),
        "network_congestion": _section_record(
            records,
            section_name="network_congestion",
            records=congestion_records,
            selected=congestion_selected,
        ),
        "exchange_flow_source_availability": _section_record(
            records,
            section_name="exchange_flow_source_availability",
            records=exchange_flow_records,
            selected=exchange_flow_selected,
        ),
        "data_quality": _data_quality_record(context, records),
        "downstream_implications": _downstream_implications(selected_records),
        "report_usage_rules": _report_usage_rules(),
        "selected_records": {
            "record_type": "onchain_flow_selected_records",
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
        "record_type": f"onchain_flow_{section_name}",
        "total_records": len(records),
        "selected_context_ids": [_clean_text(record.get("context_id"), fallback="") for record in selected],
        "omitted_record_count": max(0, len(records) - len(selected)),
        "total_context_records": len(all_records),
        "status_counts": _counts_by(records, "status"),
        "state_counts": _counts_by(records, "state"),
        "severity_counts": _counts_by(records, "severity"),
        "source_availability_counts": _counts_by(records, "source_availability"),
    }


def _record_summary(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "context_id": record.get("context_id"),
        "context_type": record.get("context_type"),
        "data_class": record.get("data_class"),
        "source": record.get("source"),
        "asset": record.get("asset"),
        "chain": record.get("chain"),
        "as_of": record.get("as_of"),
        "status": record.get("status"),
        "state": record.get("state"),
        "severity": record.get("severity"),
        "confidence": record.get("confidence"),
        "source_availability": record.get("source_availability"),
        "metrics": _bounded_mapping(_mapping(record.get("metrics")), limit=MAX_MAPPING_ITEMS),
        "evidence": _bounded_evidence(_list(record.get("evidence"))),
        "uncertainty": _bounded_messages(_string_list(record.get("uncertainty"))),
        "warnings": _bounded_messages(_string_list(record.get("warnings"))),
        "errors": _bounded_errors(_list(record.get("errors"))),
        "source_artifacts": _bounded_artifacts(_string_list(record.get("source_artifacts"))),
    }


def _source_policy() -> dict[str, Any]:
    return {
        "record_type": "onchain_flow_source_policy",
        "codex_may_explain_onchain_flow_context": True,
        "codex_may_generate_onchain_records": False,
        "codex_may_generate_flow_states": False,
        "codex_may_generate_address_labels": False,
        "codex_may_generate_risk_levels": False,
        "codex_may_generate_watch_triggers": False,
        "codex_may_generate_alert_priorities": False,
        "codex_may_generate_price_forecasts": False,
        "codex_may_create_trading_instructions": False,
        "codex_may_infer_missing_source_data": False,
        "codex_may_infer_wallet_or_exchange_address_identity": False,
        "full_raw_onchain_flow_artifacts_embedded": False,
        "full_reusable_onchain_flow_history_embedded": False,
        "full_onchain_flow_views_embedded": False,
        "full_onchain_flow_context_json_embedded": False,
        "selected_context_records_only": True,
    }


def _data_quality_record(context: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    limited = [
        record
        for record in records
        if _clean_text(record.get("status"), fallback="unknown") in LIMITED_STATUSES
        or _clean_text(record.get("source_availability"), fallback="unknown") in LIMITED_STATUSES
    ]
    return {
        "record_type": "onchain_flow_data_quality",
        "status": context.get("status") or "unknown",
        "source_limited_record_count": len(limited),
        "warning_count": len(_string_list(context.get("warnings"))),
        "error_count": len(_list(context.get("errors"))),
        "status_counts": _counts_by(records, "status"),
        "source_availability_counts": _counts_by(records, "source_availability"),
        "warnings": _bounded_messages(_string_list(context.get("warnings"))),
        "errors": _bounded_errors(_list(context.get("errors"))),
        "source_artifacts": _bounded_artifacts(
            [
                ONCHAIN_FLOW_CONTEXT_ARTIFACT,
                *_string_list(context.get("source_artifacts")),
            ]
        ),
    }


def _downstream_implications(selected_records: list[dict[str, Any]]) -> dict[str, Any]:
    abnormal = [
        record
        for record in selected_records
        if record.get("severity") in {"high", "medium"}
        and record.get("status") not in LIMITED_STATUSES
    ]
    source_limited = [
        record
        for record in selected_records
        if _clean_text(record.get("status"), fallback="unknown") in LIMITED_STATUSES
        or _clean_text(record.get("source_availability"), fallback="unknown") in LIMITED_STATUSES
    ]
    stablecoin = [record for record in selected_records if record.get("context_type") == "stablecoin_liquidity"]
    activity = [record for record in selected_records if record.get("context_type") == "chain_activity"]
    congestion = [record for record in selected_records if record.get("context_type") == "network_congestion"]
    exchange_flow = [
        record for record in selected_records if record.get("context_type") == "exchange_flow_source_availability"
    ]
    return {
        "record_type": "onchain_flow_downstream_implications",
        "onchain_flow_context_is_supporting_evidence_only": True,
        "onchain_flow_context_is_not_a_trading_signal": True,
        "use_downstream_halpha_artifacts_for_action_language": True,
        "abnormal_records_selected": len(abnormal),
        "source_limited_records_selected": len(source_limited),
        "stablecoin_liquidity_records_selected": len(stablecoin),
        "chain_activity_records_selected": len(activity),
        "network_congestion_records_selected": len(congestion),
        "exchange_flow_availability_records_selected": len(exchange_flow),
        "implications": _unique(
            [
                *(
                    [
                        "Abnormal on-chain flow context may explain liquidity, usage, or settlement-friction evidence when linked by downstream Halpha artifacts."
                    ]
                    if abnormal
                    else []
                ),
                *(
                    [
                        "Unavailable, stale, partial, failed, or insufficient on-chain evidence is source uncertainty, not neutral or low-risk evidence."
                    ]
                    if source_limited
                    else []
                ),
                *(
                    [
                        "Stablecoin supply context is liquidity evidence, not a price forecast."
                    ]
                    if stablecoin
                    else []
                ),
                *(
                    [
                        "Chain activity context is usage evidence, not action guidance."
                    ]
                    if activity
                    else []
                ),
                *(
                    [
                        "Network congestion context is settlement-friction evidence, not a standalone trade signal."
                    ]
                    if congestion
                    else []
                ),
                *(
                    [
                        "Exchange-flow source availability records describe source coverage only; they do not infer exchange deposit or withdrawal pressure."
                    ]
                    if exchange_flow
                    else []
                ),
                "Codex should explain on-chain implications only from Halpha-generated material and downstream Halpha artifacts.",
            ]
        ),
    }


def _report_usage_rules() -> dict[str, Any]:
    return {
        "record_type": "onchain_flow_report_usage_rules",
        "may_explain": [
            "stablecoin liquidity context",
            "chain activity context",
            "network congestion context",
            "exchange-flow source availability",
            "source availability, freshness, and data-quality limits",
            "whether downstream Halpha artifacts linked on-chain context to risk, watch, event, alert, or decision evidence",
        ],
        "must_distinguish": [
            "on-chain context versus trading signal",
            "stablecoin liquidity evidence versus price forecast",
            "chain activity evidence versus action guidance",
            "network congestion evidence versus market direction",
            "source uncertainty versus low risk",
        ],
        "must_not_generate": [
            "on-chain records",
            "flow states",
            "address labels",
            "risk levels",
            "watch triggers",
            "alert priorities",
            "trading signals",
            "asset price forecasts",
            "trading instructions",
            "position sizing",
            "account actions",
            "wallet actions",
        ],
    }


def _select_records(records: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    return sorted(records, key=_record_sort_key)[:limit]


def _record_sort_key(record: dict[str, Any]) -> tuple[int, int, int, str, str, str, str]:
    severity_order = {"high": 0, "medium": 1, "unknown": 2, "low": 3}
    status_order = {
        "failed": 0,
        "unavailable": 1,
        "stale": 2,
        "degraded": 3,
        "partial": 4,
        "insufficient": 5,
        "bounded": 6,
        "succeeded": 7,
    }
    type_order = {
        "stablecoin_liquidity": 0,
        "network_congestion": 1,
        "chain_activity": 2,
        "exchange_flow_source_availability": 3,
    }
    return (
        severity_order.get(_clean_text(record.get("severity"), fallback="unknown"), 2),
        status_order.get(_clean_text(record.get("status"), fallback="unknown"), 8),
        type_order.get(_clean_text(record.get("context_type"), fallback="unknown"), 4),
        _clean_text(record.get("source"), fallback=""),
        _clean_text(record.get("asset"), fallback=""),
        _clean_text(record.get("chain"), fallback=""),
        _clean_text(record.get("context_id"), fallback=""),
    )


def _read_context(run: RunContext) -> dict[str, Any]:
    try:
        loaded = json.loads((run.analysis_dir / "onchain_flow_context.json").read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{ONCHAIN_FLOW_CONTEXT_ARTIFACT} was not found; build_onchain_flow_context must run first.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    except JSONDecodeError as exc:
        raise PipelineError(
            f"{ONCHAIN_FLOW_CONTEXT_ARTIFACT} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    if not isinstance(loaded, dict):
        raise PipelineError(
            f"{ONCHAIN_FLOW_CONTEXT_ARTIFACT} must be a JSON object.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    if loaded.get("artifact_type") != "onchain_flow_context":
        raise PipelineError(
            f"{ONCHAIN_FLOW_CONTEXT_ARTIFACT} must have artifact_type onchain_flow_context.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    if not isinstance(loaded.get("records"), list):
        raise PipelineError(
            f"{ONCHAIN_FLOW_CONTEXT_ARTIFACT} must contain records as a list.",
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
                    _clean_text(record.get("asset"), fallback="unknown"),
                    _clean_text(record.get("chain"), fallback="unknown"),
                    _clean_text(record.get("as_of"), fallback="unknown"),
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


def _onchain_flow_enabled(config: dict[str, Any]) -> bool:
    onchain_flow = config.get("onchain_flow")
    return isinstance(onchain_flow, dict) and onchain_flow.get("enabled") is True


def _record_zero_counts(run: RunContext) -> None:
    run.manifest["counts"]["onchain_flow_material_records"] = 0
    run.manifest["counts"]["onchain_flow_material_omitted_records"] = 0


def _bounded_evidence(values: list[Any]) -> list[Any]:
    evidence = []
    for value in values[:MAX_EVIDENCE_ITEMS]:
        if isinstance(value, dict):
            evidence.append(_bounded_mapping(value, limit=MAX_MAPPING_ITEMS))
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
    return [str(value) for value in values[:MAX_ARTIFACTS] if isinstance(value, str) and value]


def _bounded_messages(values: list[Any]) -> list[str]:
    return [str(value) for value in values[:MAX_MESSAGES] if isinstance(value, str) and value]


def _bounded_errors(values: list[Any]) -> list[Any]:
    errors = []
    for value in values[:MAX_MESSAGES]:
        if isinstance(value, dict):
            errors.append(_bounded_mapping(value, limit=MAX_MAPPING_ITEMS))
        elif isinstance(value, str) and value:
            errors.append(value)
    return errors


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value or [] if isinstance(item, str) and item.strip()]


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
            "PyYAML is required to write YAML on-chain flow material records.",
            stage=STAGE_NAME,
            exit_code=1,
        ) from exc

    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
