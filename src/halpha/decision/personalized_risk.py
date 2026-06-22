from __future__ import annotations

import json
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from halpha.pipeline import PipelineError, RunContext
from halpha.storage import write_json


STAGE_NAME = "build_personalized_risk_constraints"
PERSONALIZED_RISK_CONSTRAINTS_ARTIFACT = "analysis/personalized_risk_constraints.json"
USER_STATE_CONTEXT_ARTIFACT = "analysis/user_state_context.json"
INTELLIGENCE_FUSION_ARTIFACT = "analysis/intelligence_fusion.json"
DECISION_RECOMMENDATIONS_ARTIFACT = "analysis/decision_recommendations.json"
WATCH_TRIGGERS_ARTIFACT = "analysis/watch_triggers.json"
ALERT_DECISIONS_ARTIFACT = "analysis/alert_decisions.json"
SCHEMA_VERSION = 1

UPSTREAM_INPUTS = (
    ("intelligence_fusion", INTELLIGENCE_FUSION_ARTIFACT, "records"),
    ("decision_recommendations", DECISION_RECOMMENDATIONS_ARTIFACT, "records"),
    ("watch_triggers", WATCH_TRIGGERS_ARTIFACT, "records"),
    ("alert_decisions", ALERT_DECISIONS_ARTIFACT, "records"),
)
STATE_ORDER = (
    "disabled_asset_blocked",
    "risk_limit_downgraded",
    "timeframe_mismatch",
    "strategy_preference_note",
    "watchlist_relevant",
    "general",
    "insufficient_user_state",
    "skipped",
    "degraded",
    "failed",
)
ACTION_ORDER = ("block", "downgrade", "annotate", "none", "skip")
ACTION_RANK = {
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


def build_personalized_risk_constraints(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    created_at = _format_utc(now)
    try:
        user_state = _read_required_json(
            run.analysis_dir / "user_state_context.json",
            USER_STATE_CONTEXT_ARTIFACT,
        )
    except _ArtifactReadError as exc:
        artifact = _failed_artifact(run, created_at=created_at, errors=exc.errors)
        _write_artifact(run, artifact)
        raise PipelineError(
            "user-state context is required before personalized risk constraints.",
            stage=STAGE_NAME,
            artifacts=[PERSONALIZED_RISK_CONSTRAINTS_ARTIFACT],
            error_details={"errors": exc.errors},
        ) from exc

    inputs = _UpstreamInputs(run)
    records = _constraint_records(user_state, inputs)
    status = _artifact_status(user_state, inputs, records)
    warnings = _unique_sorted([*inputs.warnings, *[warning for record in records for warning in record["warnings"]]])
    errors = _unique_errors([*inputs.errors, *[error for record in records for error in record["errors"]]])
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "personalized_risk_constraints",
        "run_id": run.run_id,
        "created_at": created_at,
        "status": status,
        "records": records,
        "coverage": inputs.coverage,
        "counts": _counts(records, warnings=warnings, errors=errors),
        "warnings": warnings,
        "errors": errors,
        "source_artifacts": _unique_sorted([USER_STATE_CONTEXT_ARTIFACT, *inputs.source_artifacts]),
    }
    _write_artifact(run, artifact)
    return [PERSONALIZED_RISK_CONSTRAINTS_ARTIFACT]


class _ArtifactReadError(Exception):
    def __init__(self, errors: list[dict[str, str]]) -> None:
        super().__init__("artifact read failed")
        self.errors = errors


class _UpstreamInputs:
    def __init__(self, run: RunContext) -> None:
        self.run = run
        self.coverage: list[dict[str, Any]] = []
        self.source_artifacts: list[str] = []
        self.warnings: list[str] = []
        self.errors: list[dict[str, str]] = []
        self.refs_by_scope: dict[tuple[str | None, str | None], list[dict[str, Any]]] = {}
        self.scopes: set[tuple[str | None, str | None]] = set()
        self._load()

    def _load(self) -> None:
        for layer, artifact_path, records_key in UPSTREAM_INPUTS:
            self._load_artifact(layer, artifact_path, records_key)

    def _load_artifact(self, layer: str, artifact_path: str, records_key: str) -> None:
        path = self.run.run_dir / artifact_path
        if not path.exists():
            warning = f"{artifact_path} is missing; personalized constraints use available upstream evidence only."
            self.coverage.append(
                {
                    "source_layer": layer,
                    "source_artifact": artifact_path,
                    "status": "missing",
                    "records": 0,
                    "warnings": [warning],
                    "errors": [],
                }
            )
            self.warnings.append(warning)
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, JSONDecodeError) as exc:
            error = {
                "source_artifact": artifact_path,
                "message": f"{artifact_path} could not be read as JSON.",
            }
            self.coverage.append(
                {
                    "source_layer": layer,
                    "source_artifact": artifact_path,
                    "status": "failed",
                    "records": 0,
                    "warnings": [],
                    "errors": [error],
                }
            )
            self.errors.append(error)
            return
        records = _dict_list(data.get(records_key))
        status = _coverage_status(data)
        coverage_warnings = _string_list(data.get("warnings"))
        coverage_errors = _error_list(data.get("errors"), source_artifact=artifact_path)
        self.coverage.append(
            {
                "source_layer": layer,
                "source_artifact": artifact_path,
                "status": status,
                "records": len(records),
                "warnings": coverage_warnings,
                "errors": coverage_errors,
            }
        )
        self.source_artifacts.append(artifact_path)
        self.warnings.extend(coverage_warnings)
        self.errors.extend(coverage_errors)
        for record in records:
            scope = _scope_for_layer(layer, record)
            self.scopes.add(scope)
            self.refs_by_scope.setdefault(scope, []).append(_upstream_ref(layer, artifact_path, record))


def _constraint_records(user_state: dict[str, Any], inputs: _UpstreamInputs) -> list[dict[str, Any]]:
    status = _text(user_state.get("status"))
    mode = _text(user_state.get("mode"))
    user_scopes = _user_state_scopes(user_state)
    scopes = sorted(inputs.scopes | user_scopes, key=_scope_sort_key)
    if not scopes:
        return [_empty_constraint(user_state, inputs)]
    return [_constraint_record(scope, user_state, inputs, status=status, mode=mode) for scope in scopes]


def _constraint_record(
    scope_key: tuple[str | None, str | None],
    user_state: dict[str, Any],
    inputs: _UpstreamInputs,
    *,
    status: str,
    mode: str,
) -> dict[str, Any]:
    symbol, timeframe = scope_key
    upstream_refs = inputs.refs_by_scope.get(scope_key, [])
    matches = _matched_user_state(symbol, timeframe, user_state)
    source_artifacts = _unique_sorted([USER_STATE_CONTEXT_ARTIFACT, *[ref["source_artifact"] for ref in upstream_refs]])
    evidence = [f"user_state_context status={status or 'unknown'} mode={mode or 'unknown'}"]
    uncertainty: list[str] = []
    warnings: list[str] = []
    errors: list[dict[str, str]] = []

    if status == "failed":
        state = "failed"
        action = "skip"
        severity = "high"
        confidence = "low"
        reason_codes = ["user_state_context_failed"]
        errors.append({"source_artifact": USER_STATE_CONTEXT_ARTIFACT, "message": "user-state context failed."})
    elif status == "skipped" or mode == "general":
        state = "general" if upstream_refs else "skipped"
        action = "none" if upstream_refs else "skip"
        severity = "info"
        confidence = "low"
        reason_codes = ["user_state_not_configured"]
        evidence.append("No configured user state is available; no personalized constraint is applied.")
    elif not upstream_refs:
        state = "insufficient_user_state"
        action = "skip"
        severity = "low"
        confidence = "low"
        reason_codes = ["no_upstream_scope_evidence"]
        uncertainty.append("User-state scope has no matching current-run intelligence, decision, watch, or alert evidence.")
    else:
        state, action, severity, confidence, reason_codes = _state_action_for_scope(
            scope_key,
            user_state,
            upstream_refs,
            matches,
        )
        evidence.extend(_state_evidence(scope_key, user_state, upstream_refs, matches, reason_codes))
        uncertainty.extend(_state_uncertainty(reason_codes))

    if _has_degraded_coverage(inputs):
        warnings.append("At least one optional upstream artifact is missing, degraded, or failed.")

    return {
        "constraint_id": _constraint_id(scope_key, state),
        "scope": {"symbol": symbol, "timeframe": timeframe},
        "state": state,
        "action": action,
        "severity": severity,
        "confidence": confidence,
        "reason_codes": reason_codes,
        "matched_user_state": matches,
        "upstream_records": upstream_refs,
        "evidence": _unique_sorted(evidence),
        "uncertainty": _unique_sorted(uncertainty),
        "warnings": _unique_sorted(warnings),
        "errors": errors,
        "source_artifacts": source_artifacts,
    }


def _empty_constraint(user_state: dict[str, Any], inputs: _UpstreamInputs) -> dict[str, Any]:
    status = _text(user_state.get("status"))
    state = "skipped" if status == "skipped" else "insufficient_user_state"
    reason = "user_state_not_configured" if status == "skipped" else "no_personalization_scope"
    if inputs.errors:
        state = "failed"
        reason = "upstream_read_failed"
    return {
        "constraint_id": f"personalized:global:{state}",
        "scope": {"symbol": None, "timeframe": None},
        "state": state,
        "action": "skip",
        "severity": "info" if state == "skipped" else "low",
        "confidence": "low",
        "reason_codes": [reason],
        "matched_user_state": _empty_matches(),
        "upstream_records": [],
        "evidence": [f"user_state_context status={status or 'unknown'}"],
        "uncertainty": ["No current-run personalization scope is available."],
        "warnings": _unique_sorted(inputs.warnings),
        "errors": inputs.errors,
        "source_artifacts": _unique_sorted([USER_STATE_CONTEXT_ARTIFACT, *inputs.source_artifacts]),
    }


def _state_action_for_scope(
    scope_key: tuple[str | None, str | None],
    user_state: dict[str, Any],
    upstream_refs: list[dict[str, Any]],
    matches: dict[str, bool],
) -> tuple[str, str, str, str, list[str]]:
    symbol, timeframe = scope_key
    reason_codes: list[str] = []
    if matches["disabled_asset"]:
        return "disabled_asset_blocked", "block", "high", "high", ["disabled_asset"]

    risk_reasons = _risk_limit_reasons(user_state, upstream_refs)
    if risk_reasons:
        return "risk_limit_downgraded", "downgrade", "high", "high", risk_reasons

    preferred_timeframes = _preferred_timeframes(user_state)
    if timeframe and preferred_timeframes and timeframe not in preferred_timeframes:
        return "timeframe_mismatch", "downgrade", "medium", "medium", ["timeframe_not_preferred"]

    strategy_reason = _strategy_preference_reason(user_state, upstream_refs)
    if strategy_reason:
        reason_codes.append(strategy_reason)
        return "strategy_preference_note", "annotate", "low", "medium", reason_codes

    if matches["watchlist"] or matches["manual_exposure_summary"] or matches["preferred_timeframe"]:
        reason_codes.extend(
            reason
            for reason, matched in (
                ("watchlist_match", matches["watchlist"]),
                ("manual_exposure_summary_match", matches["manual_exposure_summary"]),
                ("preferred_timeframe_match", matches["preferred_timeframe"]),
            )
            if matched
        )
        return "watchlist_relevant", "annotate", "low", "medium", reason_codes

    if symbol:
        return "general", "none", "info", "low", ["no_user_state_match"]
    return "general", "none", "info", "low", ["global_scope"]


def _risk_limit_reasons(user_state: dict[str, Any], upstream_refs: list[dict[str, Any]]) -> list[str]:
    risk = _dict(user_state.get("risk"))
    reasons: list[str] = []
    max_action = _text(risk.get("max_action_level"))
    max_action_rank = ACTION_RANK.get(max_action)
    if max_action_rank is not None:
        upstream_action = _max_upstream_action(upstream_refs)
        if upstream_action and ACTION_RANK.get(upstream_action, 0) > max_action_rank:
            reasons.append("risk_action_cap")
    if risk.get("allow_new_exposure") is False:
        upstream_action = _max_upstream_action(upstream_refs)
        if upstream_action in {"TRY_SMALL", "DO", "STRONG_DO"}:
            reasons.append("new_exposure_not_allowed")
    max_risk_state = _text(risk.get("max_risk_state"))
    max_risk_rank = RISK_RANK.get(max_risk_state)
    if max_risk_rank is not None:
        upstream_risk = _max_upstream_risk_level(upstream_refs)
        if upstream_risk and RISK_RANK.get(upstream_risk, 0) > max_risk_rank:
            reasons.append("risk_state_cap")
    return _unique_sorted(reasons)


def _max_upstream_action(upstream_refs: list[dict[str, Any]]) -> str | None:
    actions = [
        action
        for ref in upstream_refs
        for action in [_text(ref.get("action_level"))]
        if action in ACTION_RANK
    ]
    if not actions:
        return None
    return max(actions, key=lambda item: ACTION_RANK[item])


def _max_upstream_risk_level(upstream_refs: list[dict[str, Any]]) -> str | None:
    risk_levels = []
    for ref in upstream_refs:
        risk_level = _text(ref.get("risk_level"))
        if risk_level in RISK_RANK:
            risk_levels.append(risk_level)
    if not risk_levels:
        return None
    return max(risk_levels, key=lambda item: RISK_RANK[item])


def _strategy_preference_reason(user_state: dict[str, Any], upstream_refs: list[dict[str, Any]]) -> str | None:
    preferences = _dict(user_state.get("strategy_preferences"))
    text = " ".join(_text(ref.get("evidence_text")).lower() for ref in upstream_refs)
    for strategy in _string_list(preferences.get("disabled")):
        if strategy.lower() in text:
            return "disabled_strategy_preference"
    for strategy in _string_list(preferences.get("preferred")):
        if strategy.lower() in text:
            return "preferred_strategy_match"
    return None


def _state_evidence(
    scope_key: tuple[str | None, str | None],
    user_state: dict[str, Any],
    upstream_refs: list[dict[str, Any]],
    matches: dict[str, bool],
    reason_codes: list[str],
) -> list[str]:
    symbol, timeframe = scope_key
    evidence: list[str] = []
    if symbol and matches["watchlist"]:
        evidence.append(f"watchlist symbol match: {symbol}")
    if symbol and matches["disabled_asset"]:
        evidence.append(f"disabled asset match: {symbol}")
    if timeframe and matches["preferred_timeframe"]:
        evidence.append(f"preferred timeframe match: {timeframe}")
    if "timeframe_not_preferred" in reason_codes and timeframe:
        evidence.append(f"timeframe {timeframe} is outside configured preferred_timeframes.")
    if "risk_action_cap" in reason_codes:
        risk = _dict(user_state.get("risk"))
        evidence.append(f"risk.max_action_level={risk.get('max_action_level')} caps stronger upstream action levels.")
    if "new_exposure_not_allowed" in reason_codes:
        evidence.append("risk.allow_new_exposure=false blocks stronger new-exposure action levels.")
    if "risk_state_cap" in reason_codes:
        risk = _dict(user_state.get("risk"))
        evidence.append(f"risk.max_risk_state={risk.get('max_risk_state')} caps higher upstream risk states.")
    if "preferred_strategy_match" in reason_codes:
        evidence.append("Upstream evidence references a configured preferred strategy.")
    if "disabled_strategy_preference" in reason_codes:
        evidence.append("Upstream evidence references a configured disabled strategy.")
    if upstream_refs:
        evidence.append(f"upstream_records={len(upstream_refs)}")
    return evidence


def _state_uncertainty(reason_codes: list[str]) -> list[str]:
    uncertainty = []
    if "timeframe_not_preferred" in reason_codes:
        uncertainty.append("Preferred timeframes are user-state constraints, not market forecasts.")
    if "preferred_strategy_match" in reason_codes or "disabled_strategy_preference" in reason_codes:
        uncertainty.append("Strategy preference annotations do not validate strategy effectiveness.")
    return uncertainty


def _matched_user_state(symbol: str | None, timeframe: str | None, user_state: dict[str, Any]) -> dict[str, bool]:
    watchlist = _watchlist_by_symbol(user_state)
    disabled_assets = _symbol_set(user_state.get("disabled_assets"))
    preferred_timeframes = _preferred_timeframes(user_state)
    strategy_preferences = _dict(user_state.get("strategy_preferences"))
    manual_exposure = _symbol_set(user_state.get("manual_exposure_summary"))
    watch = bool(symbol and symbol in watchlist)
    return {
        "watchlist": watch,
        "disabled_asset": bool(symbol and symbol in disabled_assets),
        "preferred_timeframe": bool(timeframe and (timeframe in preferred_timeframes or _watch_timeframe_match(watchlist, symbol, timeframe))),
        "strategy_preference": bool(
            _string_list(strategy_preferences.get("preferred")) or _string_list(strategy_preferences.get("disabled"))
        ),
        "manual_exposure_summary": bool(symbol and symbol in manual_exposure),
    }


def _user_state_scopes(user_state: dict[str, Any]) -> set[tuple[str | None, str | None]]:
    scopes: set[tuple[str | None, str | None]] = set()
    preferred_timeframes = _preferred_timeframes(user_state)
    for record in _dict_list(user_state.get("watchlist")):
        symbol = _symbol(record.get("symbol"))
        timeframes = _string_list(record.get("timeframes")) or preferred_timeframes
        for timeframe in timeframes:
            scopes.add((symbol, timeframe))
    for record in _dict_list(user_state.get("disabled_assets")):
        symbol = _symbol(record.get("symbol"))
        for timeframe in preferred_timeframes:
            scopes.add((symbol, timeframe))
    for record in _dict_list(user_state.get("manual_exposure_summary")):
        symbol = _symbol(record.get("symbol"))
        for timeframe in preferred_timeframes:
            scopes.add((symbol, timeframe))
    return {scope for scope in scopes if scope[0] or scope[1]}


def _watchlist_by_symbol(user_state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        _symbol(record.get("symbol")): record
        for record in _dict_list(user_state.get("watchlist"))
        if _symbol(record.get("symbol"))
    }


def _watch_timeframe_match(
    watchlist: dict[str, dict[str, Any]],
    symbol: str | None,
    timeframe: str | None,
) -> bool:
    if not symbol or not timeframe or symbol not in watchlist:
        return False
    timeframes = _string_list(watchlist[symbol].get("timeframes"))
    return bool(timeframes and timeframe in timeframes)


def _preferred_timeframes(user_state: dict[str, Any]) -> list[str]:
    return _string_list(user_state.get("preferred_timeframes"))


def _symbol_set(value: Any) -> set[str]:
    return {
        symbol
        for symbol in (_symbol(record.get("symbol")) for record in _dict_list(value))
        if symbol
    }


def _scope_for_layer(layer: str, record: dict[str, Any]) -> tuple[str | None, str | None]:
    if layer == "alert_decisions":
        scope = _dict(record.get("scope"))
        return (_symbol(scope.get("symbol") or record.get("symbol")), _optional_text(scope.get("timeframe") or record.get("timeframe")))
    if layer == "intelligence_fusion":
        scope = _dict(record.get("scope"))
        return (_symbol(scope.get("symbol")), _optional_text(scope.get("timeframe")))
    return (_symbol(record.get("symbol")), _optional_text(record.get("timeframe")))


def _upstream_ref(layer: str, artifact_path: str, record: dict[str, Any]) -> dict[str, Any]:
    ref = {
        "source_layer": layer,
        "source_artifact": artifact_path,
        "source_record_id": _record_id(layer, record),
        "scope": {"symbol": _scope_for_layer(layer, record)[0], "timeframe": _scope_for_layer(layer, record)[1]},
        "status": _text(record.get("status") or record.get("attention_decision") or record.get("state")),
        "warnings": _string_list(record.get("warnings")),
        "errors": _error_list(record.get("errors"), source_artifact=artifact_path),
        "source_artifacts": _unique_sorted(_string_list(record.get("source_artifacts"))),
        "evidence_text": _evidence_text(record),
    }
    if layer == "decision_recommendations":
        ref["action_level"] = _text(record.get("action_level"))
        ref["risk_level"] = _risk_level_from_decision(record)
    if layer == "alert_decisions":
        ref["priority"] = _text(record.get("priority"))
        ref["attention_decision"] = _text(record.get("attention_decision"))
    if layer == "watch_triggers":
        ref["trigger_type"] = _text(record.get("type"))
    return ref


def _record_id(layer: str, record: dict[str, Any]) -> str:
    keys = {
        "intelligence_fusion": "fusion_record_id",
        "decision_recommendations": "record_id",
        "watch_triggers": "trigger_id",
        "alert_decisions": "alert_decision_id",
    }
    return _text(record.get(keys[layer]) or record.get("record_id") or record.get("id"))


def _risk_level_from_decision(record: dict[str, Any]) -> str:
    for condition in _string_list(record.get("risk_conditions")):
        if condition.startswith("risk_level="):
            return condition.split("=", 1)[1].split(";", 1)[0].strip()
    return ""


def _evidence_text(record: dict[str, Any]) -> str:
    fields: list[str] = []
    for key in ("evidence", "risk_conditions", "recommended_actions", "condition", "reason", "downgrade_reasons"):
        value = record.get(key)
        if isinstance(value, list):
            fields.extend(_text(item) for item in value)
        elif isinstance(value, str):
            fields.append(value)
    return " ".join(fields)


def _read_required_json(path: Path, artifact_path: str) -> dict[str, Any]:
    if not path.exists():
        raise _ArtifactReadError([{"source_artifact": artifact_path, "message": f"{artifact_path} is missing."}])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, JSONDecodeError) as exc:
        raise _ArtifactReadError(
            [{"source_artifact": artifact_path, "message": f"{artifact_path} could not be read as JSON."}]
        ) from exc
    if not isinstance(data, dict):
        raise _ArtifactReadError([{"source_artifact": artifact_path, "message": f"{artifact_path} root must be a mapping."}])
    return data


def _failed_artifact(run: RunContext, *, created_at: str, errors: list[dict[str, str]]) -> dict[str, Any]:
    record = {
        "constraint_id": "personalized:global:failed",
        "scope": {"symbol": None, "timeframe": None},
        "state": "failed",
        "action": "skip",
        "severity": "high",
        "confidence": "low",
        "reason_codes": ["user_state_context_missing_or_unreadable"],
        "matched_user_state": _empty_matches(),
        "upstream_records": [],
        "evidence": [],
        "uncertainty": [],
        "warnings": [],
        "errors": errors,
        "source_artifacts": [USER_STATE_CONTEXT_ARTIFACT],
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "personalized_risk_constraints",
        "run_id": run.run_id,
        "created_at": created_at,
        "status": "failed",
        "records": [record],
        "coverage": [],
        "counts": _counts([record], warnings=[], errors=errors),
        "warnings": [],
        "errors": errors,
        "source_artifacts": [USER_STATE_CONTEXT_ARTIFACT],
    }


def _artifact_status(
    user_state: dict[str, Any],
    inputs: _UpstreamInputs,
    records: list[dict[str, Any]],
) -> str:
    if inputs.errors or any(record["state"] == "failed" for record in records):
        return "failed"
    if _text(user_state.get("status")) == "skipped":
        return "skipped"
    if _has_degraded_coverage(inputs) or any(record["state"] in {"insufficient_user_state", "degraded"} for record in records):
        return "degraded"
    return "ok"


def _coverage_status(data: dict[str, Any]) -> str:
    status = _text(data.get("status"))
    if status in {"failed", "degraded", "warning", "skipped"}:
        return status
    if _error_list(data.get("errors"), source_artifact=""):
        return "failed"
    if _string_list(data.get("warnings")):
        return "warning"
    return "ok"


def _has_degraded_coverage(inputs: _UpstreamInputs) -> bool:
    return any(item["status"] in {"missing", "failed", "degraded"} for item in inputs.coverage)


def _counts(records: list[dict[str, Any]], *, warnings: list[str], errors: list[dict[str, str]]) -> dict[str, Any]:
    state_counts = {state: 0 for state in STATE_ORDER}
    action_counts = {action: 0 for action in ACTION_ORDER}
    for record in records:
        state = record["state"]
        action = record["action"]
        state_counts[state] = state_counts.get(state, 0) + 1
        action_counts[action] = action_counts.get(action, 0) + 1
    return {
        "records": len(records),
        "state_counts": state_counts,
        "action_counts": action_counts,
        "warnings": len(warnings),
        "errors": len(errors),
    }


def _write_artifact(run: RunContext, artifact: dict[str, Any]) -> None:
    write_json(run.analysis_dir / "personalized_risk_constraints.json", artifact)
    counts = _dict(artifact.get("counts"))
    state_counts = _dict(counts.get("state_counts"))
    action_counts = _dict(counts.get("action_counts"))
    run.manifest["artifacts"]["personalized_risk_constraints"] = PERSONALIZED_RISK_CONSTRAINTS_ARTIFACT
    run.manifest["personalized_risk_constraints"] = {
        "status": artifact["status"],
        "artifact": PERSONALIZED_RISK_CONSTRAINTS_ARTIFACT,
        "records": _int(counts.get("records")),
        "state_counts": state_counts,
        "action_counts": action_counts,
        "warnings": _int(counts.get("warnings")),
        "errors": _int(counts.get("errors")),
    }
    run.manifest["counts"]["personalized_risk_constraint_records"] = _int(counts.get("records"))
    run.manifest["counts"]["personalized_risk_constraint_warnings"] = _int(counts.get("warnings"))
    run.manifest["counts"]["personalized_risk_constraint_errors"] = _int(counts.get("errors"))
    for state in STATE_ORDER:
        run.manifest["counts"][f"personalized_risk_constraint_state_{state}"] = _int(state_counts.get(state))
    for action in ACTION_ORDER:
        run.manifest["counts"][f"personalized_risk_constraint_action_{action}"] = _int(action_counts.get(action))


def _constraint_id(scope: tuple[str | None, str | None], state: str) -> str:
    symbol = (scope[0] or "global").lower()
    timeframe = (scope[1] or "all").lower()
    return f"personalized:{symbol}:{timeframe}:{state}"


def _scope_sort_key(scope: tuple[str | None, str | None]) -> tuple[str, str]:
    return (scope[0] or "", scope[1] or "")


def _empty_matches() -> dict[str, bool]:
    return {
        "watchlist": False,
        "disabled_asset": False,
        "preferred_timeframe": False,
        "strategy_preference": False,
        "manual_exposure_summary": False,
    }


def _format_utc(value: datetime | str | None) -> str:
    if isinstance(value, str):
        return value
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _symbol(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip().upper()


def _optional_text(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    return [item.strip() for item in value if isinstance(item, str) and item.strip()] if isinstance(value, list) else []


def _error_list(value: Any, *, source_artifact: str) -> list[dict[str, str]]:
    errors = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                message = _text(item.get("message"))
                artifact = _text(item.get("source_artifact") or source_artifact)
            else:
                message = _text(item)
                artifact = source_artifact
            if message:
                error = {"message": message}
                if artifact:
                    error["source_artifact"] = artifact
                errors.append(error)
    return errors


def _unique_sorted(values: list[str]) -> list[str]:
    return sorted({value for value in values if isinstance(value, str) and value})


def _unique_errors(values: list[dict[str, str]]) -> list[dict[str, str]]:
    seen = set()
    errors = []
    for value in values:
        key = (value.get("source_artifact"), value.get("message"))
        if key in seen:
            continue
        seen.add(key)
        errors.append(value)
    return errors


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    return value if isinstance(value, int) else 0
