from __future__ import annotations

import json
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from halpha.runtime.pipeline_contracts import PipelineError, RunContext
from halpha.storage import write_json


STAGE_NAME = "build_factor_states"
FACTOR_STATES_ARTIFACT = "analysis/factor_states.json"
FEATURE_SNAPSHOTS_ARTIFACT = "analysis/feature_snapshots.json"
FACTOR_STATES_SCHEMA_VERSION = 1
SCORE_UNIT = "bounded_-1_to_1"

FACTOR_TAXONOMY = {
    "trend",
    "volatility",
    "liquidity",
    "leverage",
    "macro_risk",
    "event_pressure",
    "onchain_flow",
    "evidence_quality",
}

COVERAGE_FACTOR_FAMILIES = {
    "market": ("trend",),
    "market_data_views": ("trend", "volatility"),
    "market_signals": ("trend",),
    "derivatives_market": ("leverage", "liquidity"),
    "macro_calendar": ("macro_risk",),
    "onchain_flow": ("liquidity", "onchain_flow"),
    "event_intelligence": ("event_pressure",),
    "outcome_tracking": ("evidence_quality",),
    "data_quality": ("evidence_quality",),
}


def build_factor_states(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    feature_snapshots = _read_feature_snapshots(run)
    created_at = _created_at(feature_snapshots, now)
    feature_records = _feature_records(feature_snapshots)
    coverage_records = _coverage_records(feature_snapshots)
    records = [
        _factor_record(factor_type=factor_type, scope=scope, features=features, created_at=created_at)
        for (factor_type, scope), features in sorted(
            _features_by_factor_scope(feature_records).items(),
            key=lambda item: (item[0][0], _scope_sort_key(item[0][1])),
        )
    ]
    records.extend(
        _missing_coverage_records(
            coverage_records,
            existing_keys={(record["factor_type"], _scope_key(record["scope"])) for record in records},
            created_at=created_at,
        )
    )
    records = sorted(records, key=lambda record: record["factor_id"])
    warnings = _artifact_warnings(records)
    errors = _artifact_errors(records)
    artifact = {
        "schema_version": FACTOR_STATES_SCHEMA_VERSION,
        "artifact_type": "factor_states",
        "run_id": run.run_id,
        "created_at": created_at,
        "status": _artifact_status(records, warnings=warnings, errors=errors),
        "records": records,
        "counts": _counts(records, warnings=warnings, errors=errors),
        "warnings": warnings,
        "errors": errors,
        "source_artifacts": _unique_sorted(
            [
                FEATURE_SNAPSHOTS_ARTIFACT,
                *_string_list(feature_snapshots.get("source_artifacts")),
            ]
        ),
    }
    write_json(run.analysis_dir / "factor_states.json", artifact)
    _record_manifest(run, artifact)
    return [FACTOR_STATES_ARTIFACT]


def _read_feature_snapshots(run: RunContext) -> dict[str, Any]:
    path = run.analysis_dir / "feature_snapshots.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{FEATURE_SNAPSHOTS_ARTIFACT} was not found; build_feature_snapshots must run first.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    except JSONDecodeError as exc:
        raise PipelineError(
            f"{FEATURE_SNAPSHOTS_ARTIFACT} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    if not isinstance(data, dict):
        raise PipelineError(
            f"{FEATURE_SNAPSHOTS_ARTIFACT} must contain a JSON object.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    return data


def _feature_records(feature_snapshots: dict[str, Any]) -> list[dict[str, Any]]:
    records = feature_snapshots.get("records")
    if not isinstance(records, list):
        raise PipelineError(
            f"{FEATURE_SNAPSHOTS_ARTIFACT} must contain a records list.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    clean_records = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise PipelineError(
                f"{FEATURE_SNAPSHOTS_ARTIFACT} records[{index}] must be a mapping.",
                stage=STAGE_NAME,
                exit_code=3,
            )
        clean_records.append(record)
    return clean_records


def _coverage_records(feature_snapshots: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in _list(feature_snapshots.get("coverage")) if isinstance(item, dict)]


def _features_by_factor_scope(
    feature_records: list[dict[str, Any]]
) -> dict[tuple[str, tuple[tuple[str, str | None], ...]], list[dict[str, Any]]]:
    grouped: dict[tuple[str, tuple[tuple[str, str | None], ...]], list[dict[str, Any]]] = {}
    for feature in feature_records:
        factor_type = _factor_type(feature)
        if factor_type not in FACTOR_TAXONOMY:
            continue
        scope = _scope_tuple(feature.get("scope"))
        grouped.setdefault((factor_type, scope), []).append(feature)
    return grouped


def _factor_record(
    *,
    factor_type: str,
    scope: tuple[tuple[str, str | None], ...],
    features: list[dict[str, Any]],
    created_at: str,
) -> dict[str, Any]:
    scope_dict = _scope_dict(scope)
    score = _score(features)
    direction = _direction(features, score=score)
    state = _state(features, direction=direction)
    confidence = _factor_confidence(features, state=state)
    input_feature_ids = sorted(_string_list([feature.get("feature_id") for feature in features]))
    warnings = _record_warnings(features, state=state)
    errors = _record_errors(features)
    uncertainty = _record_uncertainty(features, state=state)
    return {
        "factor_id": _factor_id(factor_type, scope_dict),
        "factor_type": factor_type,
        "scope": scope_dict,
        "state": state,
        "direction": direction,
        "score": score,
        "score_unit": SCORE_UNIT,
        "confidence": confidence,
        "calculation_window": _calculation_window(features),
        "input_feature_ids": input_feature_ids,
        "evidence": _record_evidence(features, state=state, score=score),
        "uncertainty": uncertainty,
        "warnings": warnings,
        "errors": errors,
        "source_artifacts": _unique_sorted(
            [
                FEATURE_SNAPSHOTS_ARTIFACT,
                *[
                    artifact
                    for feature in features
                    for artifact in _string_list(feature.get("source_artifacts"))
                ],
            ]
        ),
    }


def _missing_coverage_records(
    coverage_records: list[dict[str, Any]],
    *,
    existing_keys: set[tuple[str, str]],
    created_at: str,
) -> list[dict[str, Any]]:
    records = []
    for coverage in coverage_records:
        coverage_status = str(coverage.get("status") or "").lower()
        if coverage_status not in {"missing", "failed", "unavailable"}:
            continue
        source_layer = str(coverage.get("source_layer") or "unknown")
        for factor_type in COVERAGE_FACTOR_FAMILIES.get(source_layer, ()):
            scope = _scope_dict(_scope_tuple({}))
            key = (factor_type, _scope_key(scope))
            if key in existing_keys:
                continue
            existing_keys.add(key)
            state = "failed" if coverage_status == "failed" else "insufficient_evidence"
            records.append(
                {
                    "factor_id": _factor_id(factor_type, scope),
                    "factor_type": factor_type,
                    "scope": scope,
                    "state": state,
                    "direction": "unknown",
                    "score": 0.0,
                    "score_unit": SCORE_UNIT,
                    "confidence": "low",
                    "calculation_window": {
                        "start": None,
                        "end": created_at,
                        "feature_count": 0,
                    },
                    "input_feature_ids": [],
                    "evidence": [
                        f"{source_layer} coverage is {coverage_status}; no feature records were available for factor calculation."
                    ],
                    "uncertainty": ["Missing source coverage prevents a directional factor state."],
                    "warnings": _coverage_warnings(coverage),
                    "errors": _coverage_errors(coverage),
                    "source_artifacts": _unique_sorted(
                        [
                            FEATURE_SNAPSHOTS_ARTIFACT,
                            *_string_list(coverage.get("source_artifact")),
                        ]
                    ),
                }
            )
    return records


def _score(features: list[dict[str, Any]]) -> float:
    usable = []
    for feature in features:
        direction_value = _direction_value(feature.get("direction_hint"))
        status_weight = _status_weight(feature.get("status"))
        confidence_weight = _confidence_weight(feature.get("confidence"))
        if status_weight <= 0 or direction_value is None:
            continue
        usable.append(direction_value * status_weight * confidence_weight)
    if not usable:
        return 0.0
    score = sum(usable) / len(usable)
    return round(max(-1.0, min(1.0, score)), 4)


def _direction(features: list[dict[str, Any]], *, score: float) -> str:
    if _has_direction_conflict(features):
        return "conflicting"
    if not _has_usable_direction(features):
        return "unknown"
    if score > 0.2:
        return "supportive"
    if score < -0.2:
        return "cautionary"
    return "neutral"


def _state(features: list[dict[str, Any]], *, direction: str) -> str:
    statuses = {_normalize_status(feature.get("status")) for feature in features}
    if any(_error_list(feature.get("errors")) for feature in features):
        return "failed"
    if direction == "conflicting":
        return "conflicting"
    if statuses and statuses <= {"missing", "insufficient_evidence"}:
        return "insufficient_evidence"
    if "stale" in statuses:
        return "stale"
    if statuses & {"partial", "degraded", "failed"}:
        return "degraded" if "failed" not in statuses else "failed"
    if direction in {"supportive", "cautionary", "neutral"}:
        return direction
    return "insufficient_evidence"


def _factor_confidence(features: list[dict[str, Any]], *, state: str) -> str:
    if not features or state in {"failed", "insufficient_evidence", "conflicting"}:
        return "low"
    values = [_confidence_value(feature.get("confidence")) for feature in features]
    average = sum(values) / len(values) if values else 0.0
    if state in {"stale", "degraded"}:
        average *= 0.5
    if average >= 0.75:
        return "high"
    if average >= 0.45:
        return "medium"
    return "low"


def _calculation_window(features: list[dict[str, Any]]) -> dict[str, Any]:
    starts = []
    ends = []
    for feature in features:
        window = feature.get("calculation_window") if isinstance(feature.get("calculation_window"), dict) else {}
        starts.extend(_string_list(window.get("start")))
        ends.extend(_string_list(window.get("end")))
        observed = _string_list(feature.get("observed_at"))
        ends.extend(observed)
    return {
        "start": min(starts) if starts else None,
        "end": max(ends) if ends else None,
        "feature_count": len(features),
    }


def _record_evidence(features: list[dict[str, Any]], *, state: str, score: float) -> list[str]:
    evidence = [
        f"Factor state {state} with score {score}.",
        f"{len(features)} feature record(s) contributed.",
    ]
    for feature in sorted(features, key=lambda item: str(item.get("feature_id") or ""))[:6]:
        feature_id = str(feature.get("feature_id") or "missing_feature_id")
        direction = str(feature.get("direction_hint") or "unknown")
        status = str(feature.get("status") or "unknown")
        evidence.append(f"{feature_id}: direction={direction}, status={status}.")
        evidence.extend(_string_list(feature.get("evidence"))[:2])
    return _unique_ordered(evidence)


def _record_uncertainty(features: list[dict[str, Any]], *, state: str) -> list[str]:
    uncertainty = [
        item
        for feature in features
        for item in _string_list(feature.get("uncertainty"))
    ]
    if state == "conflicting":
        uncertainty.append("Supportive and cautionary feature directions are both present.")
    if state in {"stale", "degraded", "insufficient_evidence", "failed"}:
        uncertainty.append(f"Factor state is {state}; downstream consumers should treat it as limited evidence.")
    return _unique_ordered(uncertainty)


def _record_warnings(features: list[dict[str, Any]], *, state: str) -> list[str]:
    warnings = [
        item
        for feature in features
        for item in _string_list(feature.get("warnings"))
    ]
    if state == "conflicting":
        warnings.append("Factor has conflicting feature directions.")
    if state in {"stale", "degraded", "insufficient_evidence"}:
        warnings.append(f"Factor state is {state}.")
    return _unique_ordered(warnings)


def _record_errors(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        error
        for feature in features
        for error in _error_list(feature.get("errors"))
    ]


def _artifact_warnings(records: list[dict[str, Any]]) -> list[str]:
    return _unique_ordered(
        [
            warning
            for record in records
            for warning in _string_list(record.get("warnings"))
        ]
    )


def _artifact_errors(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        error
        for record in records
        for error in _error_list(record.get("errors"))
    ]


def _counts(
    records: list[dict[str, Any]],
    *,
    warnings: list[str],
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "records": len(records),
        "factors_by_type": _count_by(records, "factor_type"),
        "direction_counts": _count_by(records, "direction"),
        "state_counts": _count_by(records, "state"),
        "confidence_counts": _count_by(records, "confidence"),
        "warnings": len(warnings),
        "errors": len(errors),
    }


def _artifact_status(
    records: list[dict[str, Any]],
    *,
    warnings: list[str],
    errors: list[dict[str, Any]],
) -> str:
    if errors or any(record.get("state") == "failed" for record in records):
        return "failed"
    if any(record.get("state") in {"stale", "degraded", "insufficient_evidence", "conflicting"} for record in records):
        return "warning"
    if warnings:
        return "warning"
    if records:
        return "ok"
    return "skipped"


def _record_manifest(run: RunContext, artifact: dict[str, Any]) -> None:
    counts = artifact["counts"]
    run.manifest["artifacts"]["factor_states"] = FACTOR_STATES_ARTIFACT
    run.manifest["factor_states"] = {
        "status": artifact["status"],
        "artifact": FACTOR_STATES_ARTIFACT,
        "records": counts["records"],
        "factors_by_type": counts["factors_by_type"],
        "direction_counts": counts["direction_counts"],
        "state_counts": counts["state_counts"],
        "confidence_counts": counts["confidence_counts"],
        "warnings": counts["warnings"],
        "errors": counts["errors"],
    }
    run.manifest["counts"]["factor_states"] = counts["records"]
    run.manifest["counts"]["factor_state_warnings"] = counts["warnings"]
    run.manifest["counts"]["factor_state_errors"] = counts["errors"]


def _factor_type(feature: dict[str, Any]) -> str:
    factor_family = str(feature.get("factor_family") or "").strip().lower()
    if factor_family in FACTOR_TAXONOMY:
        return factor_family
    feature_type = str(feature.get("feature_type") or "").strip().lower()
    feature_map = {
        "price_trend": "trend",
        "price_volatility": "volatility",
        "strategy_direction": "trend",
        "strategy_reliability": "evidence_quality",
        "derivatives_leverage_pressure": "leverage",
        "derivatives_liquidity_pressure": "liquidity",
        "macro_calendar_pressure": "macro_risk",
        "onchain_liquidity_context": "liquidity",
        "onchain_activity_context": "onchain_flow",
        "event_pressure": "event_pressure",
        "outcome_feedback": "evidence_quality",
        "source_quality": "evidence_quality",
    }
    return feature_map.get(feature_type, factor_family)


def _scope_tuple(value: Any) -> tuple[tuple[str, str | None], ...]:
    scope = value if isinstance(value, dict) else {}
    return tuple(
        (key, _text_or_none(scope.get(key)))
        for key in ("symbol", "timeframe", "asset", "chain", "region")
    )


def _scope_dict(scope: tuple[tuple[str, str | None], ...]) -> dict[str, str | None]:
    return {key: value for key, value in scope}


def _scope_key(scope: dict[str, Any] | tuple[tuple[str, str | None], ...]) -> str:
    if isinstance(scope, tuple):
        values = [value for _, value in scope if value]
    else:
        values = [scope.get(key) for key in ("symbol", "timeframe", "asset", "chain", "region") if scope.get(key)]
    return ":".join(_slug(value) for value in values) or "global"


def _scope_sort_key(scope: tuple[tuple[str, str | None], ...]) -> tuple[str, ...]:
    return tuple(value or "" for _, value in scope)


def _factor_id(factor_type: str, scope: dict[str, Any]) -> str:
    return f"factor:{factor_type}:{_scope_key(scope)}"


def _has_direction_conflict(features: list[dict[str, Any]]) -> bool:
    directions = {
        _normalize_direction(feature.get("direction_hint"))
        for feature in features
        if _status_weight(feature.get("status")) > 0
    }
    return "supportive" in directions and "cautionary" in directions


def _has_usable_direction(features: list[dict[str, Any]]) -> bool:
    return any(
        _normalize_direction(feature.get("direction_hint")) in {"supportive", "cautionary", "neutral"}
        and _status_weight(feature.get("status")) > 0
        for feature in features
    )


def _direction_value(value: Any) -> float | None:
    direction = _normalize_direction(value)
    if direction == "supportive":
        return 1.0
    if direction == "cautionary":
        return -1.0
    if direction == "neutral":
        return 0.0
    if direction == "conflicting":
        return 0.0
    return None


def _status_weight(value: Any) -> float:
    status = _normalize_status(value)
    if status in {"available", "neutral"}:
        return 1.0
    if status == "partial":
        return 0.6
    if status == "degraded":
        return 0.45
    if status == "stale":
        return 0.35
    return 0.0


def _confidence_weight(value: Any) -> float:
    return {
        "high": 1.0,
        "medium": 0.75,
        "low": 0.5,
        "unknown": 0.25,
    }.get(_confidence(value), 0.25)


def _confidence_value(value: Any) -> float:
    return _confidence_weight(value)


def _normalize_status(value: Any) -> str:
    status = str(value or "available").strip().lower()
    mapping = {
        "ok": "available",
        "succeeded": "available",
        "success": "available",
        "warning": "degraded",
        "bounded": "partial",
        "insufficient": "insufficient_evidence",
        "insufficient_data": "insufficient_evidence",
        "no_event": "neutral",
        "pending": "insufficient_evidence",
        "skipped": "missing",
        "unavailable": "missing",
    }
    status = mapping.get(status, status)
    allowed = {
        "available",
        "neutral",
        "missing",
        "stale",
        "partial",
        "degraded",
        "insufficient_evidence",
        "conflicting",
        "failed",
    }
    return status if status in allowed else "available"


def _normalize_direction(value: Any) -> str:
    direction = str(value or "unknown").strip().lower()
    if direction in {"supportive", "cautionary", "neutral", "conflicting", "unknown"}:
        return direction
    return "unknown"


def _confidence(value: Any) -> str:
    confidence = str(value or "unknown").strip().lower()
    if confidence in {"high", "medium", "low", "unknown"}:
        return confidence
    return "unknown"


def _coverage_warnings(coverage: dict[str, Any]) -> list[str]:
    warnings = []
    source_layer = str(coverage.get("source_layer") or "unknown")
    status = str(coverage.get("status") or "unknown")
    warnings.append(f"{source_layer} coverage is {status}.")
    warnings.extend(_string_list(coverage.get("reason")))
    warnings.extend(_string_list(coverage.get("error")))
    return _unique_ordered(warnings)


def _coverage_errors(coverage: dict[str, Any]) -> list[dict[str, Any]]:
    if str(coverage.get("status") or "").lower() != "failed":
        return []
    message = str(coverage.get("error") or coverage.get("reason") or "coverage failed")
    return [{"message": message}]


def _count_by(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(record.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        strings = []
        for item in value:
            if isinstance(item, dict):
                strings.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
            elif isinstance(item, (str, int, float)) and str(item):
                strings.append(str(item))
        return strings
    if isinstance(value, dict):
        return [json.dumps(value, ensure_ascii=False, sort_keys=True)]
    return [str(value)] if str(value) else []


def _error_list(value: Any) -> list[dict[str, Any]]:
    errors = []
    for item in _list(value):
        if isinstance(item, dict):
            errors.append(item)
        elif isinstance(item, str):
            errors.append({"message": item})
    return errors


def _unique_sorted(values: list[Any]) -> list[str]:
    return sorted({str(value) for value in values if isinstance(value, (str, int, float)) and str(value)})


def _unique_ordered(values: list[Any]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if not isinstance(value, (str, int, float)):
            continue
        text = str(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _slug(value: Any) -> str:
    text = str(value or "missing").strip().lower()
    chars = []
    for char in text:
        if char.isalnum() or char in {"_", "-", "."}:
            chars.append(char)
        else:
            chars.append("_")
    return "".join(chars).strip("_") or "missing"


def _created_at(feature_snapshots: dict[str, Any], value: datetime | str | None = None) -> str:
    if isinstance(value, str):
        return value
    if value is not None:
        return _format_utc(value)
    created_at = feature_snapshots.get("created_at")
    if isinstance(created_at, str) and created_at:
        return created_at
    return _format_utc()


def _format_utc(value: datetime | None = None) -> str:
    timestamp = value or datetime.now(timezone.utc)
    timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)
    return timestamp.isoformat().replace("+00:00", "Z")
