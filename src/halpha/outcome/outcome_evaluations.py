from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from halpha.market.ohlcv_store import OHLCVParquetStore, OHLCVStoreError
from halpha.runtime.pipeline_contracts import PipelineError, RunContext
from halpha.storage import display_path, resolve_runtime_path, runtime_root, write_json


STAGE_NAME = "evaluate_outcomes"
OUTCOME_TARGETS_ARTIFACT = "analysis/outcome_targets.json"
OUTCOME_EVALUATIONS_ARTIFACT = "analysis/outcome_evaluations.json"
SCHEMA_VERSION = 1
OHLCV_TARGET_KINDS = {"market_signal", "strategy_gate"}
FOLLOW_THROUGH_TARGET_KINDS = {
    "event_assessment",
    "alert_decision",
    "decision_recommendation",
    "watch_trigger",
}
EVENT_INTELLIGENCE_ASSESSMENT_ARTIFACT = "analysis/event_intelligence_assessment.json"
ALERT_DECISIONS_ARTIFACT = "analysis/alert_decisions.json"
DECISION_RECOMMENDATIONS_ARTIFACT = "analysis/decision_recommendations.json"
WATCH_TRIGGERS_ARTIFACT = "analysis/watch_triggers.json"
TEXT_EVENT_HISTORY_STATE_ARTIFACT = "data/research/metadata/text_event_history_state.json"


def evaluate_outcomes(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    targets_artifact = _read_targets(run)
    created_at = _created_at(run, now)
    targets = _target_records(targets_artifact)
    storage_dir, storage_artifact, storage_warning = _ohlcv_storage(config, run)
    follow_context = _follow_through_context(run)
    uses_ohlcv = any(str(target.get("target_kind") or "") in OHLCV_TARGET_KINDS for target in targets)
    evaluations = [
        _evaluation_record(
            target,
            created_at=created_at,
            run=run,
            storage_dir=storage_dir,
            storage_artifact=storage_artifact,
            storage_warning=storage_warning,
            follow_context=follow_context,
        )
        for target in targets
    ]
    warnings = _artifact_warnings(targets_artifact, evaluations, storage_warning=storage_warning)
    errors = [
        error
        for evaluation in evaluations
        for error in _dict_list(evaluation.get("errors"))
    ]
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "outcome_evaluations",
        "run_id": run.run_id,
        "created_at": created_at,
        "status": _artifact_status(evaluations, warnings=warnings, errors=errors),
        "evaluation_policy": _evaluation_policy(),
        "evaluations": sorted(evaluations, key=lambda item: item["outcome_id"]),
        "counts": _counts(evaluations, errors),
        "source_artifacts": _unique(
            [
                OUTCOME_TARGETS_ARTIFACT,
                *(_string_list(targets_artifact.get("source_artifacts"))),
                *([storage_artifact] if storage_artifact and uses_ohlcv else []),
                *follow_context["source_artifacts"],
            ]
        ),
        "warnings": warnings,
        "errors": errors,
    }
    write_json(run.analysis_dir / "outcome_evaluations.json", artifact)
    _record_manifest(run, artifact)
    return [OUTCOME_EVALUATIONS_ARTIFACT]


def _evaluation_record(
    target: dict[str, Any],
    *,
    created_at: str,
    run: RunContext,
    storage_dir: Path | None,
    storage_artifact: str | None,
    storage_warning: str | None,
    follow_context: dict[str, Any],
) -> dict[str, Any]:
    target_kind = str(target.get("target_kind") or "unknown")
    base = _base_evaluation(
        target,
        created_at=created_at,
        run=run,
        storage_artifact=storage_artifact if target_kind in OHLCV_TARGET_KINDS else None,
    )
    pending_reason = _pending_reason(target, created_at=created_at)
    if pending_reason:
        return {
            **base,
            "evaluation_status": "pending",
            "outcome_state": "unresolved",
            "observation_window": _empty_window(target, no_lookahead=True),
            "metrics": {},
            "evidence": [pending_reason],
            "warnings": [pending_reason],
            "errors": [],
        }

    if target_kind in FOLLOW_THROUGH_TARGET_KINDS:
        return _follow_through_record(base, target, follow_context=follow_context)

    if target_kind not in OHLCV_TARGET_KINDS:
        return {
            **base,
            "evaluation_status": "skipped",
            "outcome_state": "skipped",
            "observation_window": _empty_window(target, no_lookahead=True),
            "metrics": {},
            "evidence": ["Target kind is not supported by outcome evaluation."],
            "warnings": ["unsupported_target_kind"],
            "errors": [],
        }

    if storage_dir is None:
        return _insufficient_record(
            base,
            target,
            reason=storage_warning or "market.ohlcv storage is not configured.",
        )

    source = _source(target)
    symbol = _required_text(target.get("symbol"))
    timeframe = _required_text(target.get("timeframe"))
    if not source or not symbol or not timeframe:
        return _insufficient_record(
            base,
            target,
            reason="Target is missing source, symbol, or timeframe for OHLCV evaluation.",
        )

    try:
        records = OHLCVParquetStore(storage_dir).read_records(source=source, symbol=symbol, timeframe=timeframe)
    except OHLCVStoreError as exc:
        return {
            **base,
            "evaluation_status": "failed",
            "outcome_state": "failed",
            "observation_window": _empty_window(target, no_lookahead=True),
            "metrics": {},
            "evidence": [],
            "warnings": [],
            "errors": [{"type": "OHLCVStoreError", "message": str(exc)}],
        }

    source_as_of = _parse_target_timestamp(target.get("source_as_of"))
    horizon_end = _parse_target_timestamp(_horizon(target).get("observation_window_end"))
    anchor = _anchor_record(records, source_as_of)
    observed = _observation_rows(records, source_as_of=source_as_of, horizon_end=horizon_end)
    if anchor is None:
        return _insufficient_record(base, target, reason="No source-state OHLCV anchor row was available.")
    if not observed:
        return _insufficient_record(
            base,
            target,
            reason="No OHLCV rows were available strictly after target source_as_of and within the horizon.",
        )

    metrics = _metrics(target, anchor=anchor, observed=observed)
    outcome_state = _outcome_state(target, metrics)
    return {
        **base,
        "evaluation_status": "evaluated",
        "outcome_state": outcome_state,
        "observation_window": {
            "source_as_of": _format_utc(source_as_of),
            "start": observed[0]["open_time"],
            "end": observed[-1]["open_time"],
            "horizon_end": _format_utc(horizon_end),
            "sample_rows": len(observed),
            "no_lookahead": True,
            "excluded_at_or_before_source_as_of": True,
        },
        "metrics": metrics,
        "evidence": _evaluation_evidence(target, metrics, outcome_state=outcome_state),
        "warnings": [],
        "errors": [],
    }


def _base_evaluation(
    target: dict[str, Any],
    *,
    created_at: str,
    run: RunContext,
    storage_artifact: str | None,
) -> dict[str, Any]:
    target_id = str(target.get("target_id") or "missing_target_id")
    source_artifacts = _unique(
        [
            OUTCOME_TARGETS_ARTIFACT,
            *_string_list(target.get("source_artifacts")),
            *([storage_artifact] if storage_artifact else []),
        ]
    )
    return {
        "outcome_id": _outcome_id(target_id=target_id, evaluation_run_id=run.run_id),
        "target_id": target_id,
        "target_kind": target.get("target_kind"),
        "source_run_id": target.get("source_run_id"),
        "evaluation_run_id": run.run_id,
        "evaluated_at": created_at,
        "source_artifacts": source_artifacts,
    }


def _insufficient_record(base: dict[str, Any], target: dict[str, Any], *, reason: str) -> dict[str, Any]:
    return {
        **base,
        "evaluation_status": "insufficient_data",
        "outcome_state": "insufficient_data",
        "observation_window": _empty_window(target, no_lookahead=True),
        "metrics": {},
        "evidence": [reason],
        "warnings": [reason],
        "errors": [],
    }


def _metrics(target: dict[str, Any], *, anchor: dict[str, Any], observed: list[dict[str, Any]]) -> dict[str, Any]:
    anchor_close = float(anchor["close"])
    end_close = float(observed[-1]["close"])
    highs = [float(row["high"]) for row in observed]
    lows = [float(row["low"]) for row in observed]
    direction = _expected_direction(target)
    metrics: dict[str, Any] = {
        "anchor_open_time": anchor["open_time"],
        "anchor_close": anchor_close,
        "end_open_time": observed[-1]["open_time"],
        "end_close": end_close,
        "return_pct": _pct(end_close - anchor_close, anchor_close),
        "sample_rows": len(observed),
        "threshold_pct": _threshold_pct(target),
        "threshold_hit": None,
        "cost_context": _cost_context(target),
    }
    if direction == "bearish":
        favorable = _pct(anchor_close - min(lows), anchor_close)
        adverse = _pct(anchor_close - max(highs), anchor_close)
    elif direction == "bullish":
        favorable = _pct(max(highs) - anchor_close, anchor_close)
        adverse = _pct(min(lows) - anchor_close, anchor_close)
    else:
        favorable = None
        adverse = None
    metrics["max_favorable_excursion_pct"] = favorable
    metrics["max_adverse_excursion_pct"] = adverse
    if metrics["threshold_pct"] is not None and favorable is not None:
        metrics["threshold_hit"] = favorable >= metrics["threshold_pct"]
    return metrics


def _outcome_state(target: dict[str, Any], metrics: dict[str, Any]) -> str:
    direction = _expected_direction(target)
    return_pct = metrics.get("return_pct")
    if not isinstance(return_pct, (int, float)):
        return "unresolved"
    if direction == "bullish":
        if return_pct > 0:
            return "aligned"
        if return_pct < 0:
            return "not_aligned"
        return "no_change"
    if direction == "bearish":
        if return_pct < 0:
            return "aligned"
        if return_pct > 0:
            return "not_aligned"
        return "no_change"
    return "unresolved"


def _evaluation_evidence(target: dict[str, Any], metrics: dict[str, Any], *, outcome_state: str) -> list[str]:
    direction = _expected_direction(target) or "unknown"
    return [
        "Observation rows are strictly after target source_as_of.",
        f"expected_direction={direction}; return_pct={metrics['return_pct']}; outcome_state={outcome_state}.",
    ]


def _follow_through_record(
    base: dict[str, Any],
    target: dict[str, Any],
    *,
    follow_context: dict[str, Any],
) -> dict[str, Any]:
    current_records = _matching_follow_records(target, follow_context)
    text_history_records = int(follow_context.get("text_event_history_records") or 0)
    if not current_records and text_history_records <= 0:
        return {
            **base,
            "evaluation_status": "insufficient_data",
            "outcome_state": "insufficient_data",
            "observation_window": _follow_window(target),
            "metrics": _follow_metrics([], text_history_records=text_history_records),
            "evidence": ["No later Halpha follow-through artifacts or reusable text-event history were available."],
            "uncertainty": _follow_uncertainty(target, []),
            "warnings": ["missing_follow_through_evidence"],
            "errors": [],
            "source_artifacts": _follow_source_artifacts(base, [], follow_context),
        }

    state, basis = _follow_state(target, current_records)
    status = "stale" if state == "stale" else "evaluated"
    return {
        **base,
        "evaluation_status": status,
        "outcome_state": state,
        "observation_window": _follow_window(target),
        "metrics": _follow_metrics(current_records, state=state, text_history_records=text_history_records),
        "evidence": basis,
        "uncertainty": _follow_uncertainty(target, current_records),
        "warnings": _follow_warnings(current_records, state=state),
        "errors": [],
        "source_artifacts": _follow_source_artifacts(base, current_records, follow_context),
    }


def _follow_through_context(run: RunContext) -> dict[str, Any]:
    artifacts = {
        "event_assessment": _read_optional_current_artifact(
            run.analysis_dir / "event_intelligence_assessment.json",
            EVENT_INTELLIGENCE_ASSESSMENT_ARTIFACT,
            "records",
        ),
        "alert_decision": _read_optional_current_artifact(
            run.analysis_dir / "alert_decisions.json",
            ALERT_DECISIONS_ARTIFACT,
            "records",
        ),
        "decision_recommendation": _read_optional_current_artifact(
            run.analysis_dir / "decision_recommendations.json",
            DECISION_RECOMMENDATIONS_ARTIFACT,
            "records",
        ),
        "watch_trigger": _read_optional_current_artifact(
            run.analysis_dir / "watch_triggers.json",
            WATCH_TRIGGERS_ARTIFACT,
            "records",
        ),
    }
    text_history_state = _read_optional_json(
        resolve_runtime_path(TEXT_EVENT_HISTORY_STATE_ARTIFACT, config_path=run.config_path)
    )
    source_artifacts = [
        artifact_path
        for artifact_path, artifact in (
            (EVENT_INTELLIGENCE_ASSESSMENT_ARTIFACT, artifacts["event_assessment"]),
            (ALERT_DECISIONS_ARTIFACT, artifacts["alert_decision"]),
            (DECISION_RECOMMENDATIONS_ARTIFACT, artifacts["decision_recommendation"]),
            (WATCH_TRIGGERS_ARTIFACT, artifacts["watch_trigger"]),
            (TEXT_EVENT_HISTORY_STATE_ARTIFACT, text_history_state),
        )
        if artifact is not None
    ]
    return {
        "artifacts": artifacts,
        "text_event_history_state": text_history_state,
        "text_event_history_records": _text_history_record_count(text_history_state),
        "source_artifacts": source_artifacts,
    }


def _read_optional_current_artifact(path: Path, artifact_name: str, records_key: str) -> dict[str, Any] | None:
    artifact = _read_optional_json(path)
    if artifact is None:
        return None
    records = artifact.get(records_key)
    if not isinstance(records, list):
        raise PipelineError(f"{artifact_name} must contain a {records_key} list.", stage=STAGE_NAME, exit_code=3)
    return artifact


def _read_optional_json(path: Path) -> dict[str, Any] | None:
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except JSONDecodeError as exc:
        raise PipelineError(f"{display_path(path)} is not valid JSON: {exc.msg}.", stage=STAGE_NAME, exit_code=3) from exc
    if not isinstance(artifact, dict):
        raise PipelineError(f"{display_path(path)} must be a JSON object.", stage=STAGE_NAME, exit_code=3)
    return artifact


def _matching_follow_records(target: dict[str, Any], follow_context: dict[str, Any]) -> list[dict[str, Any]]:
    target_kind = str(target.get("target_kind") or "unknown")
    records = _records_for_target_kind(target_kind, follow_context)
    exact = [record for record in records if _follow_record_id(record, target_kind) == target.get("source_record_id")]
    if exact:
        return exact
    linked = [
        record
        for record in records
        if str(target.get("source_record_id") or "") in _record_link_ids(record)
    ]
    if linked:
        return linked
    symbol = target.get("symbol")
    timeframe = target.get("timeframe")
    if not symbol or not timeframe:
        return []
    return [
        record
        for record in records
        if _record_symbol(record) == symbol and _record_timeframe(record) == timeframe
    ]


def _records_for_target_kind(target_kind: str, follow_context: dict[str, Any]) -> list[dict[str, Any]]:
    artifact_key = {
        "event_assessment": "event_assessment",
        "alert_decision": "alert_decision",
        "decision_recommendation": "decision_recommendation",
        "watch_trigger": "watch_trigger",
    }.get(target_kind)
    if artifact_key is None:
        return []
    artifact = follow_context["artifacts"].get(artifact_key)
    if not isinstance(artifact, dict):
        return []
    return _dict_list(artifact.get("records"))


def _follow_record_id(record: dict[str, Any], target_kind: str) -> str | None:
    field = {
        "event_assessment": "assessment_id",
        "alert_decision": "alert_decision_id",
        "decision_recommendation": "record_id",
        "watch_trigger": "trigger_id",
    }.get(target_kind)
    if field is None:
        return None
    value = record.get(field)
    return value if isinstance(value, str) and value else None


def _record_link_ids(record: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for field in (
        "linked_event_assessment_ids",
        "linked_decision_record_ids",
        "linked_watch_trigger_ids",
    ):
        ids.update(_string_list(record.get(field)))
    scope = record.get("scope") if isinstance(record.get("scope"), dict) else {}
    for field in ("assessment_id", "linked_decision_record_id"):
        value = record.get(field) or scope.get(field)
        if isinstance(value, str) and value:
            ids.add(value)
    return ids


def _follow_state(target: dict[str, Any], records: list[dict[str, Any]]) -> tuple[str, list[str]]:
    if not records:
        return "unresolved", ["Later reusable text-event history exists, but no matching follow-through artifact record was found."]
    if any(_record_is_stale(record) for record in records):
        return "stale", ["Later follow-through record is stale or explicitly downgraded as stale."]
    if any(_record_contradicts_target(target, record) for record in records):
        return "contradicted", ["Later follow-through record contradicts the prior target state."]
    if any(_record_confirms_target(target, record) for record in records):
        return "confirmed", ["Later follow-through record confirms or preserves the prior target state."]
    return "unresolved", ["Later follow-through evidence exists but is not decisive."]


def _record_confirms_target(target: dict[str, Any], record: dict[str, Any]) -> bool:
    target_kind = str(target.get("target_kind") or "")
    expected = target.get("expected_observation") if isinstance(target.get("expected_observation"), dict) else {}
    if target_kind == "event_assessment":
        return all(
            _same_or_missing(expected.get(field), record.get(field))
            for field in ("event_severity", "decision_impact", "risk_effect", "watch_relevance")
        ) and str(record.get("status") or "") not in {"failed", "skipped"}
    if target_kind == "alert_decision":
        return _same_or_missing(expected.get("priority"), record.get("priority")) and _same_or_missing(
            expected.get("attention_decision"), record.get("attention_decision")
        )
    if target_kind == "decision_recommendation":
        return _same_or_missing(expected.get("action_level"), record.get("action_level")) and _same_or_missing(
            expected.get("decision_bias"), record.get("decision_bias")
        )
    if target_kind == "watch_trigger":
        return _same_or_missing(expected.get("trigger_type"), record.get("type")) and bool(record.get("condition"))
    return False


def _record_contradicts_target(target: dict[str, Any], record: dict[str, Any]) -> bool:
    target_kind = str(target.get("target_kind") or "")
    expected = target.get("expected_observation") if isinstance(target.get("expected_observation"), dict) else {}
    if target_kind == "event_assessment":
        expected_impact = str(expected.get("decision_impact") or "unknown")
        current_impact = str(record.get("decision_impact") or "unknown")
        expected_risk = str(expected.get("risk_effect") or "unknown")
        current_risk = str(record.get("risk_effect") or "unknown")
        return (
            expected_impact == "supports_existing_view" and current_impact in {"could_invalidate", "could_downgrade"}
        ) or (expected_risk in {"neutral", "risk_down"} and current_risk == "risk_up")
    if target_kind == "alert_decision":
        expected_priority = str(expected.get("priority") or "unknown")
        current_priority = str(record.get("priority") or "unknown")
        return _priority_side(expected_priority) != "unknown" and _priority_side(expected_priority) != _priority_side(
            current_priority
        )
    if target_kind == "decision_recommendation":
        expected_side = _action_side(str(expected.get("action_level") or "unknown"))
        current_side = _action_side(str(record.get("action_level") or "unknown"))
        return expected_side != "unknown" and current_side != "unknown" and expected_side != current_side
    if target_kind == "watch_trigger":
        expected_type = str(expected.get("trigger_type") or "")
        current_type = str(record.get("type") or "")
        return bool(expected_type and current_type and expected_type != current_type)
    return False


def _record_is_stale(record: dict[str, Any]) -> bool:
    values = [
        *_string_list(record.get("downgrade_reasons")),
        *_string_list(record.get("suppression_reasons")),
        *_string_list(record.get("warnings")),
    ]
    return "stale_event" in values or "stale_source_record" in values


def _same_or_missing(expected: Any, current: Any) -> bool:
    if expected in {None, "", "unknown"}:
        return True
    return expected == current


def _priority_side(priority: str) -> str:
    if priority in {"P0", "P1", "P2"}:
        return "attention"
    if priority in {"P3", "no_alert"}:
        return "suppress"
    return "unknown"


def _action_side(action_level: str) -> str:
    if action_level in {"STRONG_DO", "DO", "TRY_SMALL"}:
        return "constructive"
    if action_level in {"AVOID", "EXIT_OR_REDUCE", "HEDGE_OR_PROTECT"}:
        return "defensive"
    if action_level in {"WATCH", "NO_ACTION"}:
        return "neutral"
    return "unknown"


def _follow_metrics(
    records: list[dict[str, Any]],
    *,
    state: str = "unresolved",
    text_history_records: int,
) -> dict[str, Any]:
    states = [_follow_record_id(record, _kind_from_record(record)) for record in records]
    return {
        "current_record_count": len(records),
        "matched_record_ids": [value for value in states if value],
        "confirming_evidence_count": len(records) if state == "confirmed" else 0,
        "contradicting_evidence_count": len(records) if state == "contradicted" else 0,
        "text_event_history_records": text_history_records,
    }


def _follow_source_artifacts(
    base: dict[str, Any],
    records: list[dict[str, Any]],
    follow_context: dict[str, Any],
) -> list[str]:
    record_artifacts = [
        artifact
        for record in records
        for artifact in _string_list(record.get("source_artifacts"))
    ]
    return _unique([*base["source_artifacts"], *follow_context["source_artifacts"], *record_artifacts])


def _kind_from_record(record: dict[str, Any]) -> str:
    if "assessment_id" in record:
        return "event_assessment"
    if "alert_decision_id" in record:
        return "alert_decision"
    if "trigger_id" in record:
        return "watch_trigger"
    return "decision_recommendation"


def _follow_uncertainty(target: dict[str, Any], records: list[dict[str, Any]]) -> list[str]:
    uncertainty = _string_list(target.get("uncertainty"))
    for record in records:
        uncertainty.extend(_string_list(record.get("uncertainty")))
    if not records:
        uncertainty.append("No matched follow-through record was available.")
    return _unique(uncertainty)


def _follow_warnings(records: list[dict[str, Any]], *, state: str) -> list[str]:
    warnings = []
    for record in records:
        warnings.extend(_string_list(record.get("warnings")))
        warnings.extend(_string_list(record.get("downgrade_reasons")))
        warnings.extend(_string_list(record.get("suppression_reasons")))
    if state == "unresolved":
        warnings.append("follow_through_unresolved")
    return _unique(warnings)


def _follow_window(target: dict[str, Any]) -> dict[str, Any]:
    horizon = _horizon(target)
    return {
        "source_as_of": target.get("source_as_of"),
        "start": target.get("source_as_of"),
        "end": horizon.get("observation_window_end"),
        "horizon_end": horizon.get("observation_window_end"),
        "sample_rows": None,
        "no_lookahead": True,
        "excluded_at_or_before_source_as_of": True,
    }


def _record_symbol(record: dict[str, Any]) -> Any:
    scope = record.get("scope") if isinstance(record.get("scope"), dict) else {}
    return record.get("symbol") or scope.get("symbol")


def _record_timeframe(record: dict[str, Any]) -> Any:
    scope = record.get("scope") if isinstance(record.get("scope"), dict) else {}
    return record.get("timeframe") or scope.get("timeframe")


def _text_history_record_count(state: dict[str, Any] | None) -> int:
    if not isinstance(state, dict):
        return 0
    totals = state.get("totals")
    if isinstance(totals, dict):
        value = totals.get("records")
        if isinstance(value, int):
            return value
    return 0


def _read_targets(run: RunContext) -> dict[str, Any]:
    path = run.analysis_dir / "outcome_targets.json"
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{OUTCOME_TARGETS_ARTIFACT} was not found; build_outcome_targets must run first.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    except JSONDecodeError as exc:
        raise PipelineError(
            f"{OUTCOME_TARGETS_ARTIFACT} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    if not isinstance(artifact, dict):
        raise PipelineError(f"{OUTCOME_TARGETS_ARTIFACT} must be a JSON object.", stage=STAGE_NAME, exit_code=3)
    if not isinstance(artifact.get("targets"), list):
        raise PipelineError(f"{OUTCOME_TARGETS_ARTIFACT} must contain a targets list.", stage=STAGE_NAME, exit_code=3)
    return artifact


def _target_records(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    return [target for target in artifact.get("targets") or [] if isinstance(target, dict)]


def _ohlcv_storage(config: dict[str, Any], run: RunContext) -> tuple[Path | None, str | None, str | None]:
    market = config.get("market") if isinstance(config.get("market"), dict) else {}
    ohlcv = market.get("ohlcv") if isinstance(market, dict) else None
    if not isinstance(ohlcv, dict) or not ohlcv.get("storage_dir"):
        return None, None, "market.ohlcv storage is not configured."
    storage_dir = Path(str(ohlcv["storage_dir"]))
    if not storage_dir.is_absolute():
        storage_dir = resolve_runtime_path(storage_dir, config_path=run.config_path)
    artifact = display_path(storage_dir.parent / "metadata" / "ohlcv_sync_state.json", base=runtime_root(run.config_path))
    return storage_dir, artifact, None


def _observation_rows(
    records: list[dict[str, Any]],
    *,
    source_as_of: datetime,
    horizon_end: datetime,
) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if _parse_utc(str(record["open_time"])) > source_as_of
        and _parse_utc(str(record["open_time"])) <= horizon_end
    ]


def _anchor_record(records: list[dict[str, Any]], source_as_of: datetime) -> dict[str, Any] | None:
    candidates = [record for record in records if _parse_utc(str(record["open_time"])) <= source_as_of]
    if not candidates:
        return None
    return sorted(candidates, key=lambda record: str(record["open_time"]))[-1]


def _pending_reason(target: dict[str, Any], *, created_at: str) -> str | None:
    horizon = _horizon(target)
    matures_at = _parse_target_timestamp(horizon.get("matures_at"))
    if _parse_utc(created_at) < matures_at:
        return f"Target horizon has not matured; matures_at={_format_utc(matures_at)}."
    if str(target.get("maturity_status") or "") == "pending":
        return "Target maturity_status is pending."
    return None


def _empty_window(target: dict[str, Any], *, no_lookahead: bool) -> dict[str, Any]:
    horizon = _horizon(target)
    return {
        "source_as_of": target.get("source_as_of"),
        "start": None,
        "end": None,
        "horizon_end": horizon.get("observation_window_end"),
        "sample_rows": 0,
        "no_lookahead": no_lookahead,
        "excluded_at_or_before_source_as_of": no_lookahead,
    }


def _horizon(target: dict[str, Any]) -> dict[str, Any]:
    horizon = target.get("horizon")
    return horizon if isinstance(horizon, dict) else {}


def _source(target: dict[str, Any]) -> str | None:
    source = _required_text(target.get("source"))
    if source:
        return source
    source_artifacts = _string_list(target.get("source_artifacts"))
    for artifact in source_artifacts:
        if "binance" in artifact.lower():
            return "binance"
    return None


def _expected_direction(target: dict[str, Any]) -> str | None:
    expected = target.get("expected_observation")
    if not isinstance(expected, dict):
        return None
    direction = expected.get("direction") or expected.get("expected_direction") or expected.get("strategy_direction")
    if isinstance(direction, str) and direction in {"bullish", "bearish", "neutral"}:
        return direction
    return None


def _threshold_pct(target: dict[str, Any]) -> float | None:
    expected = target.get("expected_observation")
    if not isinstance(expected, dict):
        return None
    value = expected.get("threshold_pct")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _cost_context(target: dict[str, Any]) -> dict[str, Any]:
    expected = target.get("expected_observation")
    if not isinstance(expected, dict):
        return {}
    value = expected.get("cost_context") or expected.get("cost_assumptions")
    return value if isinstance(value, dict) else {}


def _evaluation_policy() -> dict[str, Any]:
    return {
        "evaluated_target_kinds": sorted(OHLCV_TARGET_KINDS | FOLLOW_THROUGH_TARGET_KINDS),
        "ohlcv_target_kinds": sorted(OHLCV_TARGET_KINDS),
        "follow_through_target_kinds": sorted(FOLLOW_THROUGH_TARGET_KINDS),
        "unsupported_target_kinds_are_visible_as_skipped": True,
        "observation_rows_must_be_after_source_as_of": True,
        "anchor_row_at_or_before_source_as_of_is_source_state_only": True,
        "follow_through_labels_are_deterministic": True,
        "llm_generated_outcome_labels": False,
        "portfolio_pnl_or_trading_execution": False,
    }


def _artifact_warnings(
    targets_artifact: dict[str, Any],
    evaluations: list[dict[str, Any]],
    *,
    storage_warning: str | None,
) -> list[str]:
    warnings = []
    if not _target_records(targets_artifact):
        warnings.append("No outcome target records were available for evaluation.")
    if storage_warning and any(evaluation.get("target_kind") in OHLCV_TARGET_KINDS for evaluation in evaluations):
        warnings.append(storage_warning)
    skipped = sum(1 for evaluation in evaluations if evaluation.get("evaluation_status") == "skipped")
    insufficient = sum(1 for evaluation in evaluations if evaluation.get("evaluation_status") == "insufficient_data")
    pending = sum(1 for evaluation in evaluations if evaluation.get("evaluation_status") == "pending")
    stale = sum(1 for evaluation in evaluations if evaluation.get("evaluation_status") == "stale")
    if skipped:
        warnings.append(f"Skipped {skipped} unsupported outcome targets.")
    if insufficient:
        warnings.append(f"Recorded {insufficient} outcome targets with insufficient evaluation data.")
    if pending:
        warnings.append(f"Recorded {pending} pending outcome targets.")
    if stale:
        warnings.append(f"Recorded {stale} stale outcome targets.")
    return warnings


def _artifact_status(
    evaluations: list[dict[str, Any]],
    *,
    warnings: list[str],
    errors: list[dict[str, Any]],
) -> str:
    if errors:
        return "degraded" if evaluations else "failed"
    if not evaluations:
        return "skipped"
    if warnings:
        return "warning"
    return "ok"


def _counts(evaluations: list[dict[str, Any]], errors: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "evaluations": len(evaluations),
        "evaluated": sum(1 for record in evaluations if record.get("evaluation_status") == "evaluated"),
        "pending": sum(1 for record in evaluations if record.get("evaluation_status") == "pending"),
        "skipped": sum(1 for record in evaluations if record.get("evaluation_status") == "skipped"),
        "stale": sum(1 for record in evaluations if record.get("evaluation_status") == "stale"),
        "insufficient_data": sum(
            1 for record in evaluations if record.get("evaluation_status") == "insufficient_data"
        ),
        "failed": sum(1 for record in evaluations if record.get("evaluation_status") == "failed"),
        "errors": len(errors),
        "by_target_kind": _count_by(evaluations, "target_kind"),
        "by_evaluation_status": _count_by(evaluations, "evaluation_status"),
        "by_outcome_state": _count_by(evaluations, "outcome_state"),
    }


def _record_manifest(run: RunContext, artifact: dict[str, Any]) -> None:
    counts = artifact["counts"]
    run.manifest["artifacts"]["outcome_evaluations"] = OUTCOME_EVALUATIONS_ARTIFACT
    run.manifest["outcome_evaluations"] = {
        "status": artifact["status"],
        "artifact": OUTCOME_EVALUATIONS_ARTIFACT,
        "evaluation_count": counts["evaluations"],
        "evaluated_count": counts["evaluated"],
        "pending_count": counts["pending"],
        "insufficient_data_count": counts["insufficient_data"],
        "skipped_count": counts["skipped"],
        "stale_count": counts["stale"],
        "warning_count": len(artifact["warnings"]),
        "error_count": len(artifact["errors"]),
    }
    run.manifest["counts"]["outcome_evaluations"] = counts["evaluations"]
    run.manifest["counts"]["outcome_evaluations_evaluated"] = counts["evaluated"]
    run.manifest["counts"]["outcome_evaluations_pending"] = counts["pending"]
    run.manifest["counts"]["outcome_evaluations_insufficient_data"] = counts["insufficient_data"]
    run.manifest["counts"]["outcome_evaluations_skipped"] = counts["skipped"]
    run.manifest["counts"]["outcome_evaluations_stale"] = counts["stale"]
    run.manifest["counts"]["outcome_evaluation_warnings"] = len(artifact["warnings"])
    run.manifest["counts"]["outcome_evaluation_errors"] = len(artifact["errors"])


def _outcome_id(*, target_id: str, evaluation_run_id: str) -> str:
    digest = hashlib.sha256(f"{target_id}|{evaluation_run_id}".encode("utf-8")).hexdigest()[:16]
    return f"outcome_evaluation:{evaluation_run_id}:{digest}"


def _created_at(run: RunContext, now: datetime | str | None) -> str:
    if now is not None:
        return _format_utc_value(now)
    started_at = run.manifest.get("started_at")
    if isinstance(started_at, str) and started_at:
        return _format_utc(_parse_utc(started_at))
    return _format_utc(datetime.now(UTC))


def _parse_target_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise PipelineError("outcome target timestamp is missing or invalid.", stage=STAGE_NAME, exit_code=3)
    return _parse_utc(value)


def _format_utc_value(value: datetime | str) -> str:
    if isinstance(value, str):
        return _format_utc(_parse_utc(value))
    return _format_utc(value)


def _parse_utc(value: str) -> datetime:
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("timestamp must include a UTC offset.")
    return timestamp.astimezone(UTC).replace(microsecond=0)


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamp must include a UTC offset.")
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _pct(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return round((numerator / denominator) * 100, 6)


def _count_by(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(record.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _required_text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _unique(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result
