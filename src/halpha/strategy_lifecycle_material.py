from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any

from .pipeline import PipelineError, RunContext


STAGE_NAME = "build_strategy_lifecycle_material"
STRATEGY_LIFECYCLE_STATE_ARTIFACT = "analysis/strategy_lifecycle_state.json"
STRATEGY_LIFECYCLE_MATERIAL_ARTIFACT = "analysis/strategy_lifecycle_material.md"
MAX_RECORDS = 8
MAX_MESSAGES = 5
MAX_ARTIFACTS = 12
STATUS_PRIORITY = {
    "degraded": 0,
    "retired": 1,
    "watchlisted": 2,
    "rejected": 3,
    "failed": 4,
    "insufficient_evidence": 5,
    "effective": 6,
    "active_candidate": 7,
    "skipped": 8,
}


def build_strategy_lifecycle_material(config: dict[str, Any], run: RunContext) -> list[str]:
    del config
    state = _read_lifecycle_state(run)
    if state is None:
        _record_skipped_manifest(run, reason=f"{STRATEGY_LIFECYCLE_STATE_ARTIFACT} was not generated.")
        return []

    material_record = _material_record(state)
    material = render_strategy_lifecycle_material(material_record)
    (run.analysis_dir / "strategy_lifecycle_material.md").write_text(material, encoding="utf-8")

    run.manifest["artifacts"]["strategy_lifecycle_material"] = STRATEGY_LIFECYCLE_MATERIAL_ARTIFACT
    run.manifest["counts"]["strategy_lifecycle_material_records"] = material_record["selected_records"][
        "selected_record_count"
    ]
    run.manifest["counts"]["strategy_lifecycle_material_omitted_records"] = material_record["omissions"][
        "omitted_record_count"
    ]
    run.manifest["strategy_lifecycle_material"] = {
        "status": material_record["lifecycle_overview"]["status"],
        "artifact": STRATEGY_LIFECYCLE_MATERIAL_ARTIFACT,
        "source_artifacts": material_record["source_policy"]["source_artifacts"],
        "selected_records": material_record["selected_records"]["selected_record_count"],
        "omitted_records": material_record["omissions"]["omitted_record_count"],
        "warnings": len(material_record["lifecycle_overview"]["warnings"]),
        "errors": len(material_record["lifecycle_overview"]["errors"]),
    }
    return [STRATEGY_LIFECYCLE_MATERIAL_ARTIFACT]


def render_strategy_lifecycle_material(material_record: dict[str, Any]) -> str:
    lines = [
        "---",
        "artifact_type: analysis_strategy_lifecycle_material",
        "schema_version: 1",
        "audience: ai",
        "source_artifacts:",
        f"  - {STRATEGY_LIFECYCLE_STATE_ARTIFACT}",
        "---",
        "",
        "# strategy_lifecycle_material",
        "",
    ]
    for section in (
        "source_policy",
        "lifecycle_overview",
        "status_summary",
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


def _read_lifecycle_state(run: RunContext) -> dict[str, Any] | None:
    path = run.analysis_dir / "strategy_lifecycle_state.json"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except JSONDecodeError as exc:
        raise PipelineError(
            f"{STRATEGY_LIFECYCLE_STATE_ARTIFACT} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    if not isinstance(loaded, dict):
        raise PipelineError(
            f"{STRATEGY_LIFECYCLE_STATE_ARTIFACT} must contain a JSON object.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    if loaded.get("artifact_type") != "strategy_lifecycle_state":
        raise PipelineError(
            f"{STRATEGY_LIFECYCLE_STATE_ARTIFACT} must have artifact_type strategy_lifecycle_state.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    if not isinstance(loaded.get("records"), list):
        raise PipelineError(
            f"{STRATEGY_LIFECYCLE_STATE_ARTIFACT} must contain a records list.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    return loaded


def _material_record(state: dict[str, Any]) -> dict[str, Any]:
    records = _dict_list(state.get("records"))
    selected = _select_records(records)
    return {
        "source_policy": _source_policy(state),
        "lifecycle_overview": _lifecycle_overview(state, records),
        "status_summary": _status_summary(state, records),
        "selected_records": {
            "record_type": "selected_strategy_lifecycle_records",
            "selection_policy": "degraded_retired_watchlisted_rejected_failed_insufficient_then_effective",
            "max_records": MAX_RECORDS,
            "total_records": len(records),
            "selected_record_count": len(selected),
            "records": [_material_lifecycle_record(record) for record in selected],
        },
        "omissions": _omissions(records, selected),
        "report_usage_rules": _report_usage_rules(),
    }


def _source_policy(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_aware": True,
        "bounded_material": True,
        "source_artifacts": _unique_strings(
            [STRATEGY_LIFECYCLE_STATE_ARTIFACT, *_string_list(state.get("source_artifacts"))]
        )[:MAX_ARTIFACTS],
        "lifecycle_states_generated_by_halpha": True,
        "strategy_lifecycle_material_is_financial_advice": False,
        "trading_instructions_allowed": False,
        "full_strategy_lifecycle_json_embedded": False,
        "full_strategy_runs_json_embedded": False,
        "full_strategy_evaluation_json_embedded": False,
        "full_strategy_experiment_json_embedded": False,
        "full_outcome_history_embedded": False,
        "full_local_lifecycle_policy_input_embedded": False,
        "private_policy_notes_embedded": False,
        "account_data_embedded": False,
        "codex_may_explain_lifecycle_status": True,
        "codex_may_generate_lifecycle_states": False,
        "codex_may_generate_strategy_versions": False,
        "codex_may_generate_parameter_digests": False,
        "codex_may_create_policy_records": False,
        "codex_may_promote_or_retire_strategies": False,
        "codex_may_optimize_parameters": False,
        "codex_may_select_strategies": False,
        "codex_may_generate_price_forecasts": False,
    }


def _lifecycle_overview(state: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    counts = _dict(state.get("counts"))
    return {
        "record_type": "strategy_lifecycle_overview",
        "run_id": state.get("run_id"),
        "created_at": state.get("created_at"),
        "status": state.get("status") or "unknown",
        "record_count": len(records),
        "lifecycle_status_counts": _dict(counts.get("by_lifecycle_status")) or _count_by(records, "lifecycle_status"),
        "health_state_counts": _count_nested(records, "health_state", "state"),
        "degradation_state_counts": _count_nested(records, "degradation", "state"),
        "retirement_state_counts": _count_nested(records, "retirement", "state"),
        "policy_records": _int(counts.get("policy_records")),
        "warnings": _string_list(state.get("warnings"))[:MAX_MESSAGES],
        "errors": _error_messages(state.get("errors"))[:MAX_MESSAGES],
    }


def _status_summary(state: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    coverage = _dict_list(state.get("coverage"))
    return {
        "record_type": "strategy_lifecycle_status_summary",
        "status_counts": _count_by(records, "lifecycle_status"),
        "records_with_degradation": sum(
            1 for record in records if _dict(record.get("degradation")).get("state") in {"warning", "degraded"}
        ),
        "records_explicitly_retired": sum(
            1 for record in records if _dict(record.get("retirement")).get("state") == "explicitly_retired"
        ),
        "records_watchlisted": sum(1 for record in records if record.get("lifecycle_status") == "watchlisted"),
        "records_rejected": sum(1 for record in records if record.get("lifecycle_status") == "rejected"),
        "records_insufficient_evidence": sum(
            1 for record in records if record.get("lifecycle_status") == "insufficient_evidence"
        ),
        "coverage_status_counts": _count_by(coverage, "status"),
        "coverage_layer_counts": _count_by(coverage, "source_layer"),
        "source_artifacts": _unique_strings(
            [STRATEGY_LIFECYCLE_STATE_ARTIFACT, *_string_list(state.get("source_artifacts"))]
        )[:MAX_ARTIFACTS],
    }


def _material_lifecycle_record(record: dict[str, Any]) -> dict[str, Any]:
    health_state = _dict(record.get("health_state"))
    degradation = _dict(record.get("degradation"))
    regime_weakness = _dict(record.get("regime_weakness"))
    promotion = _dict(record.get("promotion"))
    retirement = _dict(record.get("retirement"))
    return {
        "record_type": "strategy_lifecycle_record",
        "lifecycle_record_id": record.get("lifecycle_record_id"),
        "strategy_name": record.get("strategy_name"),
        "scope": _dict(record.get("scope")),
        "lifecycle_status": record.get("lifecycle_status"),
        "health_state": {
            "state": health_state.get("state"),
            "confidence": health_state.get("confidence"),
            "reasons": _bounded_messages(_list(health_state.get("reasons"))),
        },
        "degradation": {
            "state": degradation.get("state"),
            "reasons": _bounded_messages(_list(degradation.get("reasons"))),
            "source_record_refs": _string_list(degradation.get("source_record_refs"))[:MAX_MESSAGES],
        },
        "regime_weakness": {
            "state": regime_weakness.get("state"),
            "regimes": _string_list(regime_weakness.get("regimes"))[:MAX_MESSAGES],
            "reasons": _bounded_messages(_list(regime_weakness.get("reasons"))),
        },
        "promotion": {
            "state": promotion.get("state"),
            "policy_refs": _string_list(promotion.get("policy_refs"))[:MAX_MESSAGES],
        },
        "retirement": {
            "state": retirement.get("state"),
            "policy_refs": _string_list(retirement.get("policy_refs"))[:MAX_MESSAGES],
        },
        "strategy_contract_version": record.get("strategy_contract_version"),
        "parameter_version": record.get("parameter_version"),
        "parameter_digest": record.get("parameter_digest"),
        "evidence": _bounded_messages(_list(record.get("evidence"))),
        "uncertainty": _bounded_messages(_list(record.get("uncertainty"))),
        "warnings": _bounded_messages(_list(record.get("warnings"))),
        "errors": _error_messages(record.get("errors"))[:MAX_MESSAGES],
        "source_artifacts": _string_list(record.get("source_artifacts"))[:MAX_ARTIFACTS],
        "source_record_refs": _string_list(record.get("source_record_refs"))[:MAX_ARTIFACTS],
    }


def _omissions(records: list[dict[str, Any]], selected: list[dict[str, Any]]) -> dict[str, Any]:
    selected_ids = {id(record) for record in selected}
    omitted = [record for record in records if id(record) not in selected_ids]
    return {
        "record_type": "strategy_lifecycle_material_omissions",
        "total_records": len(records),
        "selected_record_count": len(selected),
        "omitted_record_count": len(omitted),
        "omitted_status_counts": _count_by(omitted, "lifecycle_status"),
        "omitted_health_state_counts": _count_nested(omitted, "health_state", "state"),
        "omitted_degradation_state_counts": _count_nested(omitted, "degradation", "state"),
        "omission_reason": "bounded_material_record_limit" if omitted else None,
        "full_strategy_lifecycle_json_embedded": False,
        "full_local_lifecycle_policy_input_embedded": False,
        "full_outcome_history_embedded": False,
    }


def _report_usage_rules() -> dict[str, Any]:
    return {
        "codex_may_explain_lifecycle_status": True,
        "codex_may_explain_strategy_health": True,
        "codex_may_explain_degradation_watchlist_rejection_retirement": True,
        "codex_may_explain_source_availability_and_omission_counts": True,
        "codex_may_generate_lifecycle_states": False,
        "codex_may_generate_strategy_versions": False,
        "codex_may_generate_parameter_digests": False,
        "codex_may_create_policy_records": False,
        "codex_may_promote_or_retire_strategies": False,
        "codex_may_optimize_parameters": False,
        "codex_may_select_strategies": False,
        "codex_may_generate_price_forecasts": False,
        "codex_may_create_trading_instructions": False,
        "codex_should_not_recreate_full_lifecycle_table": True,
        "financial_advice": False,
    }


def _select_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(records, key=_record_sort_key)[:MAX_RECORDS]


def _record_sort_key(record: dict[str, Any]) -> tuple[int, int, str, str, str]:
    status = str(record.get("lifecycle_status") or "unknown")
    health = _dict(record.get("health_state"))
    confidence = str(health.get("confidence") or "unknown")
    confidence_priority = {"high": 0, "medium": 1, "low": 2, "unknown": 3}
    scope = _dict(record.get("scope"))
    return (
        STATUS_PRIORITY.get(status, 99),
        confidence_priority.get(confidence, 9),
        str(record.get("strategy_name") or ""),
        str(scope.get("symbol") or ""),
        str(scope.get("timeframe") or ""),
    )


def _record_skipped_manifest(run: RunContext, *, reason: str) -> None:
    run.manifest["strategy_lifecycle_material"] = {
        "status": "not_generated",
        "artifact": None,
        "reason": reason,
        "selected_records": 0,
        "omitted_records": 0,
    }
    run.manifest["counts"]["strategy_lifecycle_material_records"] = 0
    run.manifest["counts"]["strategy_lifecycle_material_omitted_records"] = 0


def _count_by(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(record.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _count_nested(records: list[dict[str, Any]], section: str, key: str) -> dict[str, int]:
    return _count_by([_dict(record.get(section)) for record in records], key)


def _bounded_messages(values: list[Any]) -> list[str]:
    return [_bounded_text(value) for value in values if _bounded_text(value)][:MAX_MESSAGES]


def _bounded_text(value: Any) -> str:
    text = str(value).strip() if value is not None else ""
    if len(text) <= 240:
        return text
    return text[:237].rstrip() + "..."


def _error_messages(value: Any) -> list[str]:
    messages: list[str] = []
    for item in _list(value):
        if isinstance(item, dict):
            message = item.get("message") or item.get("error") or item.get("error_type")
            if message is not None:
                messages.append(_bounded_text(message))
        elif item is not None:
            messages.append(_bounded_text(item))
    return [message for message in messages if message]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value if isinstance(item, str) and item.strip()] if isinstance(value, list) else []


def _unique_strings(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    return value if isinstance(value, int) else 0


def _yaml_block(data: dict[str, Any]) -> str:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise PipelineError(
            "PyYAML is required to write YAML strategy lifecycle material.",
            stage=STAGE_NAME,
            exit_code=1,
        ) from exc
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
