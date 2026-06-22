from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from halpha.pipeline import RunContext


FEATURE_SNAPSHOTS_ARTIFACT = "analysis/feature_snapshots.json"
FACTOR_STATES_ARTIFACT = "analysis/factor_states.json"
MULTI_SOURCE_SIGNALS_ARTIFACT = "analysis/multi_source_signals.json"
FACTOR_SIGNAL_MATERIAL_ARTIFACT = "analysis/factor_signal_material.md"
INTELLIGENCE_FUSION_ARTIFACT = "analysis/intelligence_fusion.json"
INTELLIGENCE_FUSION_MATERIAL_ARTIFACT = "analysis/intelligence_fusion_material.md"
USER_STATE_CONTEXT_ARTIFACT = "analysis/user_state_context.json"
PERSONALIZED_RISK_CONSTRAINTS_ARTIFACT = "analysis/personalized_risk_constraints.json"
PERSONALIZED_RISK_MATERIAL_ARTIFACT = "analysis/personalized_risk_material.md"
FEATURE_FACTOR_CHECK_NAMES = {
    "feature_snapshots",
    "factor_states",
    "multi_source_signals",
    "factor_signal_material",
}
PERSONALIZED_RISK_CHECK_NAMES = {
    "user_state_context",
    "personalized_risk_constraints",
    "personalized_risk_material",
}
POST_DATA_QUALITY_CHECK_NAMES = {
    *FEATURE_FACTOR_CHECK_NAMES,
    "intelligence_fusion",
    "intelligence_fusion_material",
    *PERSONALIZED_RISK_CHECK_NAMES,
}


def post_data_quality_artifact_checks(run: RunContext, *, expected: bool) -> list[dict[str, Any]]:
    return [
        _feature_snapshots_check(run, expected=expected),
        _factor_states_check(run, expected=expected),
        _multi_source_signals_check(run, expected=expected),
        _factor_signal_material_check(run, expected=expected),
        _intelligence_fusion_check(run, expected=expected),
        _intelligence_fusion_material_check(run, expected=expected),
        _user_state_context_check(run, expected=expected),
        _personalized_risk_constraints_check(run, expected=expected),
        _personalized_risk_material_check(run, expected=expected),
    ]


def _feature_snapshots_check(run: RunContext, *, expected: bool) -> dict[str, Any]:
    artifact = FEATURE_SNAPSHOTS_ARTIFACT
    if not expected:
        return _post_data_quality_stage_check(
            "feature_snapshots",
            artifact,
            producer_stage="build_feature_snapshots",
        )
    data, error = _read_json(run.analysis_dir / "feature_snapshots.json")
    if error:
        return _missing_post_data_quality_check("feature_snapshots", artifact, error)
    records = _list(data.get("records"))
    coverage = _list(data.get("coverage"))
    warnings = _string_list(data.get("warnings"))
    errors = _error_messages(data.get("errors"))
    shape_errors = _json_artifact_shape_errors(
        data,
        artifact_type="feature_snapshots",
        records_field="records",
    )
    errors.extend(shape_errors)
    status = _analysis_artifact_status(str(data.get("status") or "unknown"), warnings, errors)
    counts = _dict(data.get("counts"))
    return _check(
        "feature_snapshots",
        "analysis",
        status,
        f"{len(records)} feature snapshot record(s), {len(coverage)} source coverage record(s).",
        [artifact],
        warnings=warnings,
        errors=errors,
        details={
            "records": len(records),
            "coverage_records": len(coverage),
            "manifest_records": _int(_dict(run.manifest.get("feature_snapshots")).get("records")),
            "manifest_coverage_records": _int(
                _dict(run.manifest.get("feature_snapshots")).get("coverage_records")
            ),
            "warnings": _int(counts.get("warnings")),
            "errors": _int(counts.get("errors")),
            "stale_records": _status_count(records, "stale"),
            "degraded_records": _status_count(records, "degraded"),
            "failed_records": _status_count(records, "failed"),
        },
    )


def _factor_states_check(run: RunContext, *, expected: bool) -> dict[str, Any]:
    artifact = FACTOR_STATES_ARTIFACT
    if not expected:
        return _post_data_quality_stage_check(
            "factor_states",
            artifact,
            producer_stage="build_factor_states",
        )
    data, error = _read_json(run.analysis_dir / "factor_states.json")
    if error:
        return _missing_post_data_quality_check("factor_states", artifact, error)
    records = _list(data.get("records"))
    warnings = _string_list(data.get("warnings"))
    errors = _error_messages(data.get("errors"))
    shape_errors = _json_artifact_shape_errors(
        data,
        artifact_type="factor_states",
        records_field="records",
    )
    errors.extend(shape_errors)
    status = _analysis_artifact_status(str(data.get("status") or "unknown"), warnings, errors)
    counts = _dict(data.get("counts"))
    return _check(
        "factor_states",
        "analysis",
        status,
        f"{len(records)} factor state record(s).",
        [artifact],
        warnings=warnings,
        errors=errors,
        details={
            "records": len(records),
            "manifest_records": _int(_dict(run.manifest.get("factor_states")).get("records")),
            "warnings": _int(counts.get("warnings")),
            "errors": _int(counts.get("errors")),
            "conflicting_records": _state_count(records, "conflicting"),
            "degraded_records": _state_count(records, "degraded"),
            "insufficient_evidence_records": _state_count(records, "insufficient_evidence"),
            "failed_records": _state_count(records, "failed"),
        },
    )


def _multi_source_signals_check(run: RunContext, *, expected: bool) -> dict[str, Any]:
    artifact = MULTI_SOURCE_SIGNALS_ARTIFACT
    if not expected:
        return _post_data_quality_stage_check(
            "multi_source_signals",
            artifact,
            producer_stage="build_multi_source_signals",
        )
    data, error = _read_json(run.analysis_dir / "multi_source_signals.json")
    if error:
        return _missing_post_data_quality_check("multi_source_signals", artifact, error)
    records = _list(data.get("records"))
    warnings = _string_list(data.get("warnings"))
    errors = _error_messages(data.get("errors"))
    shape_errors = _json_artifact_shape_errors(
        data,
        artifact_type="multi_source_signals",
        records_field="records",
    )
    errors.extend(shape_errors)
    status = _analysis_artifact_status(str(data.get("status") or "unknown"), warnings, errors)
    counts = _dict(data.get("counts"))
    return _check(
        "multi_source_signals",
        "analysis",
        status,
        f"{len(records)} multi-source signal record(s).",
        [artifact],
        warnings=warnings,
        errors=errors,
        details={
            "records": len(records),
            "manifest_records": _int(_dict(run.manifest.get("multi_source_signals")).get("records")),
            "warnings": _int(counts.get("warnings")),
            "errors": _int(counts.get("errors")),
            "conflicting_records": _state_count(records, "conflicting"),
            "degraded_records": _state_count(records, "degraded"),
            "insufficient_evidence_records": _state_count(records, "insufficient_evidence"),
            "failed_records": _state_count(records, "failed"),
        },
    )


def _factor_signal_material_check(run: RunContext, *, expected: bool) -> dict[str, Any]:
    artifact = FACTOR_SIGNAL_MATERIAL_ARTIFACT
    if not expected:
        return _post_data_quality_stage_check(
            "factor_signal_material",
            artifact,
            producer_stage="build_analysis_materials",
        )
    path = run.analysis_dir / "factor_signal_material.md"
    if not path.exists():
        return _missing_post_data_quality_check("factor_signal_material", artifact, f"{path.name} was not found.")
    material = path.read_text(encoding="utf-8")
    errors = []
    required_boundaries = [
        "artifact_type: analysis_factor_signal_material",
        "codex_may_generate_feature_records: false",
        "codex_may_generate_factor_scores: false",
        "codex_may_generate_signal_states: false",
        "full_feature_snapshots_json_embedded: false",
        "full_factor_states_json_embedded: false",
        "full_multi_source_signals_json_embedded: false",
        "selected_records_only: true",
    ]
    for boundary in required_boundaries:
        if boundary not in material:
            errors.append(f"factor signal material missing boundary: {boundary}")
    material_summary = _dict(run.manifest.get("factor_signal_material"))
    budget = _factor_signal_material_budget(run)
    status = "failed" if errors else _analysis_artifact_status(str(material_summary.get("status") or "ok"), [], [])
    return _check(
        "factor_signal_material",
        "analysis",
        status,
        "factor signal material is present with Codex boundary metadata.",
        [artifact, FEATURE_SNAPSHOTS_ARTIFACT, FACTOR_STATES_ARTIFACT, MULTI_SOURCE_SIGNALS_ARTIFACT],
        errors=errors,
        details={
            "chars": len(material),
            "selected_records": _int(run.manifest.get("counts", {}).get("factor_signal_material_records")),
            "omitted_records": _int(run.manifest.get("counts", {}).get("factor_signal_material_omitted_records")),
            "codex_boundaries_present": not errors,
            "codex_budget_checked": bool(budget),
            "codex_budget_status": budget.get("status") if budget else "not_available_before_codex_context",
            "codex_budget_chars": _int(budget.get("chars")) if budget else 0,
            "codex_budget_over_budget": bool(budget.get("over_budget")) if budget else False,
            "codex_budget_warnings": len(_list(budget.get("warnings"))) if budget else 0,
        },
    )


def _intelligence_fusion_check(run: RunContext, *, expected: bool) -> dict[str, Any]:
    artifact = INTELLIGENCE_FUSION_ARTIFACT
    if not expected:
        return _post_data_quality_stage_check(
            "intelligence_fusion",
            artifact,
            producer_stage="build_intelligence_fusion",
        )
    data, error = _read_json(run.analysis_dir / "intelligence_fusion.json")
    if error:
        return _missing_post_data_quality_check("intelligence_fusion", artifact, error)
    records = _list(data.get("records"))
    coverage = _list(data.get("coverage"))
    warnings = _string_list(data.get("warnings"))
    errors = _error_messages(data.get("errors"))
    errors.extend(
        _json_artifact_shape_errors(
            data,
            artifact_type="intelligence_fusion",
            records_field="records",
        )
    )
    if not isinstance(data.get("coverage"), list):
        errors.append("coverage must be a list.")
    counts = _dict(data.get("counts"))
    state_counts = _count_mapping(counts.get("state_counts"), records, field="state")
    confluence_counts = _nested_count_mapping(counts.get("confluence_counts"), records, "confluence")
    conflict_counts = _nested_count_mapping(counts.get("conflict_counts"), records, "conflict")
    risk_override_counts = _nested_count_mapping(counts.get("risk_override_counts"), records, "risk_override")
    event_override_counts = _nested_count_mapping(counts.get("event_override_counts"), records, "event_override")
    outcome_feedback_counts = _nested_count_mapping(
        counts.get("outcome_feedback_counts"),
        records,
        "outcome_feedback",
    )
    status = _intelligence_fusion_quality_status(str(data.get("status") or "unknown"), state_counts, warnings, errors)
    manifest_summary = _dict(run.manifest.get("intelligence_fusion"))
    manifest_counts = _dict(run.manifest.get("counts"))
    return _check(
        "intelligence_fusion",
        "analysis",
        status,
        f"{len(records)} intelligence fusion record(s), {len(coverage)} source coverage record(s).",
        [artifact],
        warnings=warnings,
        errors=errors,
        details={
            "records": len(records),
            "coverage_records": len(coverage),
            "manifest_records": _int(manifest_summary.get("records")),
            "state_counts": state_counts,
            "confluence_counts": confluence_counts,
            "conflict_counts": conflict_counts,
            "risk_override_counts": risk_override_counts,
            "event_override_counts": event_override_counts,
            "outcome_feedback_counts": outcome_feedback_counts,
            "warnings": _int(counts.get("warnings")),
            "errors": _int(counts.get("errors")),
            "degraded_records": _int(state_counts.get("degraded")),
            "failed_records": _int(state_counts.get("failed")),
            "insufficient_evidence_records": _int(state_counts.get("insufficient_evidence")),
            "risk_blocked_records": _int(state_counts.get("risk_blocked")),
            "event_overridden_records": _int(state_counts.get("event_overridden")),
            "conflicting_records": _int(state_counts.get("conflicting")),
            "decision_linked_records": _int(manifest_counts.get("intelligence_fusion_decision_linked_records")),
            "decision_adjusted_records": _int(manifest_counts.get("intelligence_fusion_decision_adjusted_records")),
            "alert_linked_records": _int(manifest_counts.get("intelligence_fusion_alert_linked_records")),
            "alert_adjusted_records": _int(manifest_counts.get("intelligence_fusion_alert_adjusted_records")),
        },
    )


def _intelligence_fusion_material_check(run: RunContext, *, expected: bool) -> dict[str, Any]:
    artifact = INTELLIGENCE_FUSION_MATERIAL_ARTIFACT
    if not expected:
        return _post_data_quality_stage_check(
            "intelligence_fusion_material",
            artifact,
            producer_stage="build_analysis_materials",
        )
    path = run.analysis_dir / "intelligence_fusion_material.md"
    if not path.exists():
        return _missing_post_data_quality_check("intelligence_fusion_material", artifact, f"{path.name} was not found.")
    material = path.read_text(encoding="utf-8")
    errors = []
    required_boundaries = [
        "artifact_type: analysis_intelligence_fusion_material",
        "full_intelligence_fusion_json_embedded: false",
        "full_upstream_json_embedded: false",
        "codex_may_generate_fusion_states: false",
        "codex_may_generate_risk_overrides: false",
        "codex_may_generate_event_overrides: false",
        "codex_may_generate_alert_priorities: false",
        "codex_may_generate_action_levels: false",
    ]
    for boundary in required_boundaries:
        if boundary not in material:
            errors.append(f"intelligence fusion material missing boundary: {boundary}")
    material_summary = _dict(run.manifest.get("intelligence_fusion_material"))
    manifest_counts = _dict(run.manifest.get("counts"))
    budget = _material_budget(run, INTELLIGENCE_FUSION_MATERIAL_ARTIFACT)
    status = "failed" if errors else _analysis_artifact_status(str(material_summary.get("status") or "ok"), [], [])
    return _check(
        "intelligence_fusion_material",
        "analysis",
        status,
        "intelligence fusion material is present with Codex boundary metadata.",
        [artifact, INTELLIGENCE_FUSION_ARTIFACT],
        errors=errors,
        details={
            "chars": len(material),
            "selected_records": _int(manifest_counts.get("intelligence_fusion_material_records")),
            "omitted_records": _int(manifest_counts.get("intelligence_fusion_material_omitted_records")),
            "codex_boundaries_present": not errors,
            "codex_budget_checked": bool(budget),
            "codex_budget_status": budget.get("status") if budget else "not_available_before_codex_context",
            "codex_budget_chars": _int(budget.get("chars")) if budget else 0,
            "codex_budget_over_budget": bool(budget.get("over_budget")) if budget else False,
            "codex_budget_warnings": len(_list(budget.get("warnings"))) if budget else 0,
        },
    )


def _user_state_context_check(run: RunContext, *, expected: bool) -> dict[str, Any]:
    artifact = USER_STATE_CONTEXT_ARTIFACT
    if not expected:
        return _post_data_quality_stage_check(
            "user_state_context",
            artifact,
            producer_stage="build_user_state_context",
        )
    data, error = _read_json(run.analysis_dir / "user_state_context.json")
    if error:
        return _missing_post_data_quality_check("user_state_context", artifact, error)
    warnings = _string_list(data.get("warnings"))
    errors = _error_messages(data.get("errors"))
    errors.extend(
        _json_artifact_shape_errors(
            data,
            artifact_type="user_state_context",
            records_field="watchlist",
        )
    )
    counts = _dict(data.get("counts"))
    source = _dict(data.get("source"))
    privacy = _dict(data.get("privacy"))
    privacy_errors = _user_state_privacy_boundary_errors(data)
    errors.extend(privacy_errors)
    status = _analysis_artifact_status(str(data.get("status") or "unknown"), warnings, errors)
    return _check(
        "user_state_context",
        "analysis",
        status,
        f"user-state context mode {data.get('mode') or 'unknown'}, {status} status.",
        [artifact],
        warnings=warnings,
        errors=errors,
        details={
            "mode": str(data.get("mode") or "unknown"),
            "configured": bool(source.get("configured")),
            "watchlist_records": _int(counts.get("watchlist_records")),
            "disabled_assets": _int(counts.get("disabled_assets")),
            "preferred_timeframes": _int(counts.get("preferred_timeframes")),
            "strategy_preference_records": _int(counts.get("strategy_preference_records")),
            "manual_exposure_summary_records": _int(counts.get("manual_exposure_summary_records")),
            "omitted_private_values": _int(
                counts.get("omitted_private_values") or privacy.get("omitted_private_values")
            ),
            "raw_path_embedded": bool(source.get("raw_path_embedded")),
            "raw_file_embedded": bool(source.get("raw_file_embedded")),
            "private_notes_embedded": bool(privacy.get("private_notes_embedded")),
            "machine_paths_embedded": bool(privacy.get("machine_paths_embedded")),
            "account_identifiers_embedded": bool(privacy.get("account_identifiers_embedded")),
            "holdings_values_embedded": bool(privacy.get("holdings_values_embedded")),
            "privacy_boundaries_present": not privacy_errors,
            "warnings": _int(counts.get("warnings")),
            "errors": _int(counts.get("errors")),
        },
    )


def _personalized_risk_constraints_check(run: RunContext, *, expected: bool) -> dict[str, Any]:
    artifact = PERSONALIZED_RISK_CONSTRAINTS_ARTIFACT
    if not expected:
        return _post_data_quality_stage_check(
            "personalized_risk_constraints",
            artifact,
            producer_stage="build_personalized_risk_constraints",
        )
    data, error = _read_json(run.analysis_dir / "personalized_risk_constraints.json")
    if error:
        return _missing_post_data_quality_check("personalized_risk_constraints", artifact, error)
    records = _list(data.get("records"))
    coverage = _list(data.get("coverage"))
    warnings = _string_list(data.get("warnings"))
    errors = _error_messages(data.get("errors"))
    errors.extend(
        _json_artifact_shape_errors(
            data,
            artifact_type="personalized_risk_constraints",
            records_field="records",
        )
    )
    if not isinstance(data.get("coverage"), list):
        errors.append("coverage must be a list.")
    counts = _dict(data.get("counts"))
    state_counts = _count_mapping(counts.get("state_counts"), records, field="state")
    action_counts = _count_mapping(counts.get("action_counts"), records, field="action")
    status = _personalized_risk_quality_status(
        str(data.get("status") or "unknown"),
        state_counts,
        warnings,
        errors,
    )
    manifest_summary = _dict(run.manifest.get("personalized_risk_constraints"))
    manifest_counts = _dict(run.manifest.get("counts"))
    integration_summary = _dict(run.manifest.get("personalized_risk_integration"))
    return _check(
        "personalized_risk_constraints",
        "analysis",
        status,
        f"{len(records)} personalized risk constraint record(s), {len(coverage)} source coverage record(s).",
        [artifact, USER_STATE_CONTEXT_ARTIFACT],
        warnings=warnings,
        errors=errors,
        details={
            "records": len(records),
            "coverage_records": len(coverage),
            "manifest_records": _int(manifest_summary.get("records")),
            "state_counts": state_counts,
            "action_counts": action_counts,
            "warnings": _int(counts.get("warnings")),
            "errors": _int(counts.get("errors")),
            "failed_records": _int(state_counts.get("failed")),
            "degraded_records": _int(state_counts.get("degraded")),
            "insufficient_user_state_records": _int(state_counts.get("insufficient_user_state")),
            "disabled_asset_blocked_records": _int(state_counts.get("disabled_asset_blocked")),
            "risk_limit_downgraded_records": _int(state_counts.get("risk_limit_downgraded")),
            "timeframe_mismatch_records": _int(state_counts.get("timeframe_mismatch")),
            "watchlist_relevant_records": _int(state_counts.get("watchlist_relevant")),
            "strategy_preference_note_records": _int(state_counts.get("strategy_preference_note")),
            "integration_status": str(integration_summary.get("status") or "unknown"),
            "decision_linked_records": _int(manifest_counts.get("personalized_risk_decision_linked_records")),
            "decision_adjusted_records": _int(manifest_counts.get("personalized_risk_decision_adjusted_records")),
            "watch_linked_records": _int(manifest_counts.get("personalized_risk_watch_linked_records")),
            "watch_adjusted_records": _int(manifest_counts.get("personalized_risk_watch_adjusted_records")),
            "alert_linked_records": _int(manifest_counts.get("personalized_risk_alert_linked_records")),
            "alert_adjusted_records": _int(manifest_counts.get("personalized_risk_alert_adjusted_records")),
        },
    )


def _personalized_risk_material_check(run: RunContext, *, expected: bool) -> dict[str, Any]:
    artifact = PERSONALIZED_RISK_MATERIAL_ARTIFACT
    if not expected:
        return _post_data_quality_stage_check(
            "personalized_risk_material",
            artifact,
            producer_stage="build_personalized_risk_material",
        )
    path = run.analysis_dir / "personalized_risk_material.md"
    if not path.exists():
        return _missing_post_data_quality_check("personalized_risk_material", artifact, f"{path.name} was not found.")
    material = path.read_text(encoding="utf-8")
    errors = []
    required_boundaries = [
        "artifact_type: analysis_personalized_risk_material",
        "full_user_state_file_embedded: false",
        "private_notes_embedded: false",
        "machine_paths_embedded: false",
        "account_identifiers_embedded: false",
        "holdings_values_embedded: false",
        "full_user_state_context_json_embedded: false",
        "full_personalized_risk_constraints_json_embedded: false",
        "codex_may_generate_user_state: false",
        "codex_may_generate_allocations: false",
        "codex_may_size_positions: false",
        "codex_may_generate_action_levels: false",
        "codex_may_create_trading_instructions: false",
    ]
    for boundary in required_boundaries:
        if boundary not in material:
            errors.append(f"personalized risk material missing boundary: {boundary}")
    material_summary = _dict(run.manifest.get("personalized_risk_material"))
    manifest_counts = _dict(run.manifest.get("counts"))
    budget = _material_budget(run, PERSONALIZED_RISK_MATERIAL_ARTIFACT)
    if not budget:
        budget = _dict(material_summary.get("codex_input_budget"))
    status = "failed" if errors else _analysis_artifact_status(str(material_summary.get("status") or "ok"), [], [])
    return _check(
        "personalized_risk_material",
        "analysis",
        status,
        "personalized risk material is present with privacy and Codex boundary metadata.",
        [artifact, USER_STATE_CONTEXT_ARTIFACT, PERSONALIZED_RISK_CONSTRAINTS_ARTIFACT],
        errors=errors,
        details={
            "chars": len(material),
            "selected_records": _int(manifest_counts.get("personalized_risk_material_records")),
            "omitted_records": _int(manifest_counts.get("personalized_risk_material_omitted_records")),
            "codex_boundaries_present": not errors,
            "codex_budget_checked": bool(budget),
            "codex_budget_status": budget.get("status") if budget else "not_available_before_codex_context",
            "codex_budget_chars": _int(budget.get("chars")) if budget else 0,
            "codex_budget_over_budget": bool(budget.get("over_budget")) if budget else False,
            "codex_budget_warnings": len(_list(budget.get("warnings"))) if budget else 0,
        },
    )


def _post_data_quality_stage_check(name: str, artifact: str, *, producer_stage: str) -> dict[str, Any]:
    return _check(
        name,
        "analysis",
        "skipped",
        f"{artifact} is produced by {producer_stage} after the data-quality stage; this stage-time skip is expected.",
        [artifact],
        details={
            "producer_stage": producer_stage,
            "written_after_data_quality_stage": True,
            "stage_time_skip_is_expected": True,
            "report_as_final_missing": False,
        },
    )


def _missing_post_data_quality_check(name: str, artifact: str, error: str) -> dict[str, Any]:
    message = f"{artifact} was expected for final artifact audit but could not be inspected: {error}"
    return _check(
        name,
        "analysis",
        "failed",
        message,
        [artifact],
        errors=[message],
        details={
            "stage_time_skip_is_expected": False,
            "report_as_final_missing": True,
        },
    )


def _json_artifact_shape_errors(data: dict[str, Any], *, artifact_type: str, records_field: str) -> list[str]:
    errors = []
    if data.get("artifact_type") != artifact_type:
        errors.append(f"artifact_type must be {artifact_type}.")
    if not isinstance(data.get(records_field), list):
        errors.append(f"{records_field} must be a list.")
    return errors


def _analysis_artifact_status(status: str, warnings: list[str], errors: list[str]) -> str:
    normalized = status.strip().lower()
    if errors or normalized == "failed":
        return "failed"
    if normalized in {"degraded", "warning", "skipped"}:
        return normalized
    if warnings:
        return "warning"
    return "ok"


def _intelligence_fusion_quality_status(
    status: str,
    state_counts: dict[str, int],
    warnings: list[str],
    errors: list[str],
) -> str:
    normalized = status.strip().lower()
    if errors or normalized == "failed" or _int(state_counts.get("failed")):
        return "failed"
    if _int(state_counts.get("degraded")):
        return "degraded"
    if normalized in {"degraded", "warning", "skipped"}:
        return normalized
    if warnings:
        return "warning"
    return "ok"


def _personalized_risk_quality_status(
    status: str,
    state_counts: dict[str, int],
    warnings: list[str],
    errors: list[str],
) -> str:
    normalized = status.strip().lower()
    if errors or normalized == "failed" or _int(state_counts.get("failed")):
        return "failed"
    if normalized == "skipped":
        return "skipped"
    if _int(state_counts.get("degraded")) or _int(state_counts.get("insufficient_user_state")):
        return "degraded"
    if normalized in {"degraded", "warning"}:
        return normalized
    if warnings:
        return "warning"
    return "ok"


def _user_state_privacy_boundary_errors(data: dict[str, Any]) -> list[str]:
    errors = []
    source = _dict(data.get("source"))
    privacy = _dict(data.get("privacy"))
    if source.get("raw_path_embedded") is not False:
        errors.append("user-state source raw_path_embedded must be false.")
    if source.get("raw_file_embedded") is not False:
        errors.append("user-state source raw_file_embedded must be false.")
    source_ref = source.get("source_ref")
    if isinstance(source_ref, str) and any(marker in source_ref for marker in (":", "\\", "/")):
        errors.append("user-state source_ref must be sanitized and must not contain a local path.")
    for key in (
        "private_notes_embedded",
        "machine_paths_embedded",
        "account_identifiers_embedded",
        "holdings_values_embedded",
    ):
        if privacy.get(key) is not False:
            errors.append(f"user-state privacy {key} must be false.")
    for record in _list(data.get("manual_exposure_summary")):
        if isinstance(record, dict) and "private_note" in record:
            errors.append("manual_exposure_summary must not include private_note values.")
            break
    return errors


def _state_count(records: list[Any], state: str) -> int:
    return sum(1 for item in records if isinstance(item, dict) and item.get("state") == state)


def _count_mapping(value: Any, records: list[Any], *, field: str) -> dict[str, int]:
    counts = {str(key): _int(count) for key, count in _dict(value).items() if isinstance(key, str)}
    if counts:
        return dict(sorted(counts.items()))
    fallback: dict[str, int] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        key = record.get(field)
        if isinstance(key, str) and key:
            fallback[key] = fallback.get(key, 0) + 1
    return dict(sorted(fallback.items()))


def _nested_count_mapping(value: Any, records: list[Any], field: str) -> dict[str, int]:
    counts = {str(key): _int(count) for key, count in _dict(value).items() if isinstance(key, str)}
    if counts:
        return dict(sorted(counts.items()))
    fallback: dict[str, int] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        nested = record.get(field)
        nested_state = nested.get("state") if isinstance(nested, dict) else None
        if isinstance(nested_state, str) and nested_state:
            fallback[nested_state] = fallback.get(nested_state, 0) + 1
    return dict(sorted(fallback.items()))


def _factor_signal_material_budget(run: RunContext) -> dict[str, Any]:
    return _material_budget(run, FACTOR_SIGNAL_MATERIAL_ARTIFACT)


def _material_budget(run: RunContext, artifact: str) -> dict[str, Any]:
    codex_input = _dict(run.manifest.get("codex_input"))
    materials = codex_input.get("materials")
    if isinstance(materials, dict):
        budget = materials.get(artifact)
        return budget if isinstance(budget, dict) else {}
    if isinstance(materials, list):
        for item in materials:
            record = _dict(item)
            if record.get("artifact") == artifact:
                return record
    return {}


def _check(
    name: str,
    scope: str,
    status: str,
    summary: str,
    source_artifacts: list[str],
    *,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    warnings = _unique_sorted(warnings or [])
    errors = errors or []
    return {
        "name": name,
        "status": status,
        "scope": scope,
        "summary": summary,
        "warning_count": len(warnings),
        "error_count": len(errors),
        "source_artifacts": source_artifacts,
        "details": {
            **(details or {}),
            "warnings": warnings,
            "errors": errors,
        },
    }


def _read_json(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, f"{path.name} was not found."
    except JSONDecodeError as exc:
        return {}, f"{path.name} is not valid JSON: {exc.msg}."
    if not isinstance(loaded, dict):
        return {}, f"{path.name} must be a JSON object."
    return loaded, None


def _status_count(records: list[Any], status: str) -> int:
    return sum(1 for item in records if isinstance(item, dict) and item.get("status") == status)


def _error_messages(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    messages = []
    for value in values:
        if isinstance(value, str):
            messages.append(value)
        elif isinstance(value, dict) and isinstance(value.get("message"), str):
            messages.append(value["message"])
    return messages


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return 0


def _unique_sorted(values: list[str]) -> list[str]:
    return sorted({value for value in values if value})

