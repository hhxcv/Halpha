from __future__ import annotations

import json
from json import JSONDecodeError
from typing import Any

from halpha.codex.input_budget import DEFAULT_MATERIAL_MAX_CHARS, text_budget_record
from halpha.runtime.pipeline_contracts import PipelineError, RunContext


STAGE_NAME = "build_personalized_risk_material"
USER_STATE_CONTEXT_ARTIFACT = "analysis/user_state_context.json"
PERSONALIZED_RISK_CONSTRAINTS_ARTIFACT = "analysis/personalized_risk_constraints.json"
PERSONALIZED_RISK_MATERIAL_ARTIFACT = "analysis/personalized_risk_material.md"

MAX_SELECTED_RECORDS = 7
MAX_LOW_PRIORITY_RECORDS = 2
MAX_MESSAGES = 3
MAX_SOURCE_ARTIFACTS = 6
MAX_TEXT_CHARS = 160

STATE_PRIORITY = {
    "failed": 0,
    "disabled_asset_blocked": 1,
    "risk_limit_downgraded": 2,
    "timeframe_mismatch": 3,
    "watchlist_relevant": 4,
    "strategy_preference_note": 5,
    "degraded": 6,
    "insufficient_user_state": 7,
    "general": 8,
    "skipped": 9,
}
ACTION_PRIORITY = {
    "block": 0,
    "downgrade": 1,
    "annotate": 2,
    "none": 3,
    "skip": 4,
}
SEVERITY_PRIORITY = {
    "high": 0,
    "medium": 1,
    "low": 2,
    "info": 3,
}


def build_personalized_risk_material(config: dict[str, Any], run: RunContext) -> list[str]:
    user_state = _read_artifact(
        run.analysis_dir / "user_state_context.json",
        USER_STATE_CONTEXT_ARTIFACT,
        expected_type="user_state_context",
        producer_stage="build_user_state_context",
    )
    constraints = _read_artifact(
        run.analysis_dir / "personalized_risk_constraints.json",
        PERSONALIZED_RISK_CONSTRAINTS_ARTIFACT,
        expected_type="personalized_risk_constraints",
        producer_stage="build_personalized_risk_constraints",
    )
    material_record = _material_record(user_state=user_state, constraints=constraints)
    material = render_personalized_risk_material(material_record)
    (run.analysis_dir / "personalized_risk_material.md").write_text(material, encoding="utf-8")

    budget = text_budget_record(
        PERSONALIZED_RISK_MATERIAL_ARTIFACT,
        material,
        status="pending_research_context_inclusion",
        max_chars=DEFAULT_MATERIAL_MAX_CHARS,
        role="report_facing_material",
    )
    run.manifest["artifacts"]["personalized_risk_material"] = PERSONALIZED_RISK_MATERIAL_ARTIFACT
    run.manifest["counts"]["personalized_risk_material_records"] = material_record["selected_records"][
        "selected_record_count"
    ]
    run.manifest["counts"]["personalized_risk_material_omitted_records"] = material_record["omissions"][
        "omitted_record_count"
    ]
    run.manifest["counts"]["personalized_risk_material_warnings"] = len(
        material_record["constraint_overview"]["warnings"]
    )
    run.manifest["counts"]["personalized_risk_material_errors"] = len(
        material_record["constraint_overview"]["errors"]
    )
    run.manifest["personalized_risk_material"] = {
        "status": material_record["constraint_overview"]["status"],
        "artifact": PERSONALIZED_RISK_MATERIAL_ARTIFACT,
        "source_artifacts": material_record["source_policy"]["source_artifacts"],
        "total_constraint_records": material_record["constraint_overview"]["record_count"],
        "selected_records": material_record["selected_records"]["selected_record_count"],
        "omitted_records": material_record["omissions"]["omitted_record_count"],
        "warnings": len(material_record["constraint_overview"]["warnings"]),
        "errors": len(material_record["constraint_overview"]["errors"]),
        "codex_input_budget": budget,
    }
    return [PERSONALIZED_RISK_MATERIAL_ARTIFACT]


def render_personalized_risk_material(material_record: dict[str, Any]) -> str:
    lines = [
        "---",
        "artifact_type: analysis_personalized_risk_material",
        "schema_version: 1",
        "audience: ai",
        "source_artifacts:",
        f"  - {USER_STATE_CONTEXT_ARTIFACT}",
        f"  - {PERSONALIZED_RISK_CONSTRAINTS_ARTIFACT}",
        "bounded_material: true",
        "full_user_state_file_embedded: false",
        "private_notes_embedded: false",
        "machine_paths_embedded: false",
        "account_identifiers_embedded: false",
        "holdings_values_embedded: false",
        "full_user_state_context_json_embedded: false",
        "full_personalized_risk_constraints_json_embedded: false",
        "full_intermediate_json_embedded: false",
        "codex_may_explain_personalized_constraints: true",
        "codex_may_generate_user_state: false",
        "codex_may_generate_holdings: false",
        "codex_may_generate_allocations: false",
        "codex_may_size_positions: false",
        "codex_may_generate_action_levels: false",
        "codex_may_generate_price_forecasts: false",
        "codex_may_create_trading_instructions: false",
        "financial_advice: false",
        "---",
        "",
        "# personalized_risk_material",
        "",
    ]
    for section in (
        "source_policy",
        "user_state_summary",
        "constraint_overview",
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


def _read_artifact(path: Any, artifact: str, *, expected_type: str, producer_stage: str) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{artifact} was not found; {producer_stage} must run first.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    except JSONDecodeError as exc:
        raise PipelineError(
            f"{artifact} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    if not isinstance(loaded, dict):
        raise PipelineError(
            f"{artifact} must contain a JSON object.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    if loaded.get("artifact_type") != expected_type:
        raise PipelineError(
            f"{artifact} must have artifact_type {expected_type}.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    return loaded


def _material_record(*, user_state: dict[str, Any], constraints: dict[str, Any]) -> dict[str, Any]:
    records = _dict_list(constraints.get("records"))
    selected = _select_records(records)
    return {
        "source_policy": _source_policy(user_state, constraints),
        "user_state_summary": _user_state_summary(user_state),
        "constraint_overview": _constraint_overview(constraints, records),
        "selected_records": {
            "record_type": "selected_personalized_risk_constraints",
            "selection_policy": (
                "failed_disabled_blocked_risk_downgraded_timeframe_mismatch_"
                "watchlist_strategy_then_degraded_insufficient_general"
            ),
            "max_records": MAX_SELECTED_RECORDS,
            "total_records": len(records),
            "selected_record_count": len(selected),
            "records": [_material_constraint_record(record) for record in selected],
        },
        "omissions": _omissions(records, selected),
        "report_usage_rules": _report_usage_rules(),
    }


def _source_policy(user_state: dict[str, Any], constraints: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_aware": True,
        "bounded_material": True,
        "source_artifacts": _unique_strings(
            [
                USER_STATE_CONTEXT_ARTIFACT,
                PERSONALIZED_RISK_CONSTRAINTS_ARTIFACT,
                *_string_list(user_state.get("source_artifacts")),
                *_string_list(constraints.get("source_artifacts")),
            ]
        )[:MAX_SOURCE_ARTIFACTS],
        "raw_user_state_source_ref": _safe_source_ref(user_state),
        "full_user_state_file_embedded": False,
        "private_notes_embedded": False,
        "machine_paths_embedded": False,
        "account_identifiers_embedded": False,
        "holdings_values_embedded": False,
        "full_user_state_context_json_embedded": False,
        "full_personalized_risk_constraints_json_embedded": False,
        "full_intermediate_json_embedded": False,
        "codex_may_explain_personalized_constraints": True,
        "codex_may_distinguish_general_and_personalized_constraints": True,
        "codex_may_generate_user_state": False,
        "codex_may_generate_holdings": False,
        "codex_may_generate_allocations": False,
        "codex_may_size_positions": False,
        "codex_may_generate_action_levels": False,
        "codex_may_generate_alert_priorities": False,
        "codex_may_generate_price_forecasts": False,
        "codex_may_create_trading_instructions": False,
        "financial_advice": False,
    }


def _user_state_summary(user_state: dict[str, Any]) -> dict[str, Any]:
    counts = _dict(user_state.get("counts"))
    privacy = _dict(user_state.get("privacy"))
    risk = _dict(user_state.get("risk"))
    return {
        "record_type": "sanitized_user_state_summary",
        "status": user_state.get("status"),
        "mode": user_state.get("mode"),
        "source_ref": _safe_source_ref(user_state),
        "raw_path_embedded": False,
        "raw_file_embedded": False,
        "watchlist_records": _int(counts.get("watchlist_records")),
        "disabled_assets": _int(counts.get("disabled_assets")),
        "preferred_timeframes": _int(counts.get("preferred_timeframes")),
        "strategy_preference_records": _int(counts.get("strategy_preference_records")),
        "manual_exposure_summary_records": _int(counts.get("manual_exposure_summary_records")),
        "omitted_private_values": _int(counts.get("omitted_private_values") or privacy.get("omitted_private_values")),
        "risk_preference": risk.get("preference"),
        "risk_max_state": risk.get("max_risk_state"),
        "risk_max_action_level": risk.get("max_action_level"),
        "allow_new_exposure": risk.get("allow_new_exposure"),
        "private_notes_embedded": False,
        "machine_paths_embedded": False,
        "account_identifiers_embedded": False,
        "holdings_values_embedded": False,
        "warnings": _bounded_strings(user_state.get("warnings")),
        "errors": _bounded_errors(user_state.get("errors")),
    }


def _constraint_overview(constraints: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    counts = _dict(constraints.get("counts"))
    return {
        "record_type": "personalized_risk_constraint_overview",
        "run_id": constraints.get("run_id"),
        "created_at": constraints.get("created_at"),
        "status": constraints.get("status"),
        "record_count": len(records),
        "state_counts": _dict(counts.get("state_counts")) or _count_by(records, "state"),
        "action_counts": _dict(counts.get("action_counts")) or _count_by(records, "action"),
        "coverage": _coverage_summary(constraints),
        "warnings": _bounded_strings(constraints.get("warnings")),
        "errors": _bounded_errors(constraints.get("errors")),
    }


def _coverage_summary(constraints: dict[str, Any]) -> list[dict[str, Any]]:
    coverage = []
    for item in _dict_list(constraints.get("coverage"))[:MAX_MESSAGES]:
        coverage.append(
            {
                "source_layer": item.get("source_layer"),
                "source_artifact": item.get("source_artifact"),
                "status": item.get("status"),
                "records": item.get("records"),
                "warnings": _bounded_strings(item.get("warnings"), limit=2),
                "errors": _bounded_errors(item.get("errors"), limit=2),
            }
        )
    return coverage


def _material_constraint_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_type": "personalized_risk_constraint",
        "constraint_id": record.get("constraint_id"),
        "scope": _dict(record.get("scope")),
        "state": record.get("state"),
        "action": record.get("action"),
        "severity": record.get("severity"),
        "confidence": record.get("confidence"),
        "reason_codes": _string_list(record.get("reason_codes"))[:MAX_MESSAGES],
        "matched_user_state": _matched_user_state(record.get("matched_user_state")),
        "upstream_record_count": len(_dict_list(record.get("upstream_records"))),
        "upstream_layer_counts": _upstream_layer_counts(record),
        "evidence": _bounded_strings(record.get("evidence"), limit=2),
        "uncertainty": _bounded_strings(record.get("uncertainty"), limit=2),
        "warnings": _bounded_strings(record.get("warnings"), limit=2),
        "errors": _bounded_errors(record.get("errors"), limit=2),
        "source_artifacts": _string_list(record.get("source_artifacts"))[:4],
    }


def _upstream_layer_counts(record: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ref in _dict_list(record.get("upstream_records")):
        layer = str(ref.get("source_layer") or "unknown")
        counts[layer] = counts.get(layer, 0) + 1
    return dict(sorted(counts.items()))


def _matched_user_state(value: Any) -> dict[str, bool]:
    matches = _dict(value)
    return {
        "watchlist": bool(matches.get("watchlist")),
        "disabled_asset": bool(matches.get("disabled_asset")),
        "preferred_timeframe": bool(matches.get("preferred_timeframe")),
        "strategy_preference": bool(matches.get("strategy_preference")),
        "manual_exposure_summary": bool(matches.get("manual_exposure_summary")),
    }


def _omissions(records: list[dict[str, Any]], selected: list[dict[str, Any]]) -> dict[str, Any]:
    selected_ids = {id(record) for record in selected}
    omitted = [record for record in records if id(record) not in selected_ids]
    return {
        "record_type": "personalized_risk_material_omissions",
        "total_records": len(records),
        "selected_record_count": len(selected),
        "omitted_record_count": len(omitted),
        "omitted_state_counts": _count_by(omitted, "state"),
        "omitted_action_counts": _count_by(omitted, "action"),
        "omission_reason": "bounded_material_record_limit" if omitted else None,
    }


def _report_usage_rules() -> dict[str, Any]:
    return {
        "codex_may_explain_personalized_constraints": True,
        "codex_may_distinguish_general_and_personalized_constraints": True,
        "codex_may_explain_disabled_asset_blocks": True,
        "codex_may_explain_risk_limit_downgrades": True,
        "codex_may_explain_timeframe_mismatches": True,
        "codex_may_explain_watchlist_relevance": True,
        "use_halpha_generated_personalized_states_only": True,
        "do_not_infer_hidden_user_state": True,
        "do_not_create_or_revise_holdings": True,
        "do_not_create_allocations": True,
        "do_not_size_positions": True,
        "do_not_generate_action_levels": True,
        "do_not_generate_alert_priorities": True,
        "do_not_generate_price_forecasts": True,
        "do_not_create_trading_instructions": True,
        "financial_advice": False,
    }


def _select_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    low_priority_records = 0
    for record in sorted(records, key=_record_sort_key):
        if len(selected) >= MAX_SELECTED_RECORDS:
            break
        if record.get("state") in {"general", "skipped"}:
            if low_priority_records >= MAX_LOW_PRIORITY_RECORDS:
                continue
            low_priority_records += 1
        selected.append(record)
    return selected


def _record_sort_key(record: dict[str, Any]) -> tuple[int, int, int, str, str, str]:
    scope = _dict(record.get("scope"))
    return (
        STATE_PRIORITY.get(str(record.get("state") or ""), 99),
        ACTION_PRIORITY.get(str(record.get("action") or ""), 99),
        SEVERITY_PRIORITY.get(str(record.get("severity") or ""), 99),
        str(scope.get("symbol") or ""),
        str(scope.get("timeframe") or ""),
        str(record.get("constraint_id") or ""),
    )


def _safe_source_ref(user_state: dict[str, Any]) -> str:
    source = _dict(user_state.get("source"))
    ref = source.get("source_ref")
    safe_refs = {"configured_user_state", "not_configured", "unknown"}
    if isinstance(ref, str) and ref.strip() in safe_refs:
        return ref.strip()
    if source.get("configured") is True:
        return "configured_user_state"
    if source.get("configured") is False:
        return "not_configured"
    return "unknown"


def _count_by(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(record.get(field) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def _bounded_strings(value: Any, *, limit: int = MAX_MESSAGES) -> list[str]:
    return [_bounded_text(item) for item in _string_list(value)[:limit]]


def _bounded_errors(value: Any, *, limit: int = MAX_MESSAGES) -> list[dict[str, str]]:
    errors = []
    for item in _dict_list(value)[:limit]:
        errors.append(
            {
                "source_artifact": _bounded_text(item.get("source_artifact")),
                "message": _bounded_text(item.get("message")),
            }
        )
    return errors


def _bounded_text(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) <= MAX_TEXT_CHARS:
        return text
    return text[: MAX_TEXT_CHARS - 3].rstrip() + "..."


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
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
            "PyYAML is required to write YAML personalized risk material.",
            stage=STAGE_NAME,
            exit_code=1,
        ) from exc

    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
