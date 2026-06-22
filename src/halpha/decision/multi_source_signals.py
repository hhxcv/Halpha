from __future__ import annotations

import json
from datetime import datetime, timezone
from json import JSONDecodeError
from typing import Any

from halpha.runtime.pipeline_contracts import PipelineError, RunContext
from halpha.storage import write_json


STAGE_NAME = "build_multi_source_signals"
MULTI_SOURCE_SIGNALS_ARTIFACT = "analysis/multi_source_signals.json"
FACTOR_STATES_ARTIFACT = "analysis/factor_states.json"
MULTI_SOURCE_SIGNALS_SCHEMA_VERSION = 1


def build_multi_source_signals(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    factor_states = _read_factor_states(run)
    created_at = _created_at(factor_states, now)
    factor_records = _factor_records(factor_states)
    records = [
        _signal_record(scope=scope, factors=factors, created_at=created_at)
        for scope, factors in sorted(
            _factors_by_scope(factor_records).items(),
            key=lambda item: _scope_sort_key(item[0]),
        )
    ]
    if not records:
        records.append(_empty_signal(created_at=created_at))
    records = sorted(records, key=lambda record: record["signal_id"])
    warnings = _artifact_warnings(records)
    errors = _artifact_errors(records)
    artifact = {
        "schema_version": MULTI_SOURCE_SIGNALS_SCHEMA_VERSION,
        "artifact_type": "multi_source_signals",
        "run_id": run.run_id,
        "created_at": created_at,
        "status": _artifact_status(records, warnings=warnings, errors=errors),
        "records": records,
        "counts": _counts(records, warnings=warnings, errors=errors),
        "warnings": warnings,
        "errors": errors,
        "source_artifacts": _unique_sorted(
            [
                FACTOR_STATES_ARTIFACT,
                *_string_list(factor_states.get("source_artifacts")),
            ]
        ),
    }
    write_json(run.analysis_dir / "multi_source_signals.json", artifact)
    _record_manifest(run, artifact)
    return [MULTI_SOURCE_SIGNALS_ARTIFACT]


def _read_factor_states(run: RunContext) -> dict[str, Any]:
    path = run.analysis_dir / "factor_states.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{FACTOR_STATES_ARTIFACT} was not found; build_factor_states must run first.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    except JSONDecodeError as exc:
        raise PipelineError(
            f"{FACTOR_STATES_ARTIFACT} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    if not isinstance(data, dict):
        raise PipelineError(
            f"{FACTOR_STATES_ARTIFACT} must contain a JSON object.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    return data


def _factor_records(factor_states: dict[str, Any]) -> list[dict[str, Any]]:
    records = factor_states.get("records")
    if not isinstance(records, list):
        raise PipelineError(
            f"{FACTOR_STATES_ARTIFACT} must contain a records list.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    clean_records = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise PipelineError(
                f"{FACTOR_STATES_ARTIFACT} records[{index}] must be a mapping.",
                stage=STAGE_NAME,
                exit_code=3,
            )
        clean_records.append(record)
    return clean_records


def _factors_by_scope(
    factor_records: list[dict[str, Any]]
) -> dict[tuple[tuple[str, str | None], ...], list[dict[str, Any]]]:
    grouped: dict[tuple[tuple[str, str | None], ...], list[dict[str, Any]]] = {}
    for factor in factor_records:
        scope = _scope_tuple(factor.get("scope"))
        grouped.setdefault(scope, []).append(factor)
    return grouped


def _signal_record(
    *,
    scope: tuple[tuple[str, str | None], ...],
    factors: list[dict[str, Any]],
    created_at: str,
) -> dict[str, Any]:
    scope_dict = _scope_dict(scope)
    state = _signal_state(factors)
    direction = _signal_direction(factors, state=state)
    score = _signal_score(factors)
    confidence = _signal_confidence(factors, state=state)
    factor_ids = sorted(_string_list([factor.get("factor_id") for factor in factors]))
    supportive_factor_ids = _factor_ids_by_direction(factors, "supportive")
    cautionary_factor_ids = _factor_ids_by_direction(factors, "cautionary")
    neutral_factor_ids = _factor_ids_by_direction(factors, "neutral")
    conflicting_factor_ids = _factor_ids_by_direction(factors, "conflicting")
    insufficient_factor_ids = _factor_ids_by_state(factors, "insufficient_evidence")
    degraded_factor_ids = _factor_ids_by_state(factors, "degraded", "stale")
    failed_factor_ids = _factor_ids_by_state(factors, "failed")
    return {
        "signal_id": f"multi_source_signal:{_scope_key(scope_dict)}",
        "signal_type": "multi_source_market_context",
        "scope": scope_dict,
        "state": state,
        "direction": direction,
        "score": score,
        "score_unit": "bounded_-1_to_1",
        "confidence": confidence,
        "factor_score_summary": _factor_score_summary(factors),
        "contributing_factor_ids": factor_ids,
        "supportive_factor_ids": supportive_factor_ids,
        "cautionary_factor_ids": cautionary_factor_ids,
        "neutral_factor_ids": neutral_factor_ids,
        "conflicting_factor_ids": conflicting_factor_ids,
        "insufficient_factor_ids": insufficient_factor_ids,
        "degraded_factor_ids": degraded_factor_ids,
        "failed_factor_ids": failed_factor_ids,
        "evidence": _record_evidence(factors, state=state, score=score),
        "uncertainty": _record_uncertainty(
            factors,
            state=state,
            insufficient_factor_ids=insufficient_factor_ids,
            degraded_factor_ids=degraded_factor_ids,
            failed_factor_ids=failed_factor_ids,
        ),
        "warnings": _record_warnings(factors, state=state),
        "errors": _record_errors(factors),
        "source_artifacts": _unique_sorted(
            [
                FACTOR_STATES_ARTIFACT,
                *[
                    artifact
                    for factor in factors
                    for artifact in _string_list(factor.get("source_artifacts"))
                ],
            ]
        ),
        "created_at": created_at,
    }


def _empty_signal(*, created_at: str) -> dict[str, Any]:
    scope = _scope_dict(_scope_tuple({}))
    return {
        "signal_id": "multi_source_signal:global",
        "signal_type": "multi_source_market_context",
        "scope": scope,
        "state": "insufficient_evidence",
        "direction": "unknown",
        "score": 0.0,
        "score_unit": "bounded_-1_to_1",
        "confidence": "low",
        "factor_score_summary": {
            "factor_count": 0,
            "average_score": 0.0,
            "supportive": 0,
            "cautionary": 0,
            "neutral": 0,
            "conflicting": 0,
            "insufficient_evidence": 1,
            "degraded": 0,
            "failed": 0,
        },
        "contributing_factor_ids": [],
        "supportive_factor_ids": [],
        "cautionary_factor_ids": [],
        "neutral_factor_ids": [],
        "conflicting_factor_ids": [],
        "insufficient_factor_ids": [],
        "degraded_factor_ids": [],
        "failed_factor_ids": [],
        "evidence": ["No factor records were available for multi-source signal generation."],
        "uncertainty": ["Missing factor states prevent a directional multi-source signal."],
        "warnings": ["No factor records were available."],
        "errors": [],
        "source_artifacts": [FACTOR_STATES_ARTIFACT],
        "created_at": created_at,
    }


def _signal_state(factors: list[dict[str, Any]]) -> str:
    if not factors:
        return "insufficient_evidence"
    states = {_state(factor.get("state")) for factor in factors}
    directions = {_direction(factor.get("direction")) for factor in factors}
    if "failed" in states and states <= {"failed", "insufficient_evidence"}:
        return "failed"
    if "conflicting" in states or "conflicting" in directions:
        return "conflicting"
    if "supportive" in directions and "cautionary" in directions:
        return "conflicting"
    if states <= {"insufficient_evidence"}:
        return "insufficient_evidence"
    if states & {"degraded", "stale", "failed", "insufficient_evidence"}:
        return "degraded"
    if "supportive" in directions:
        return "supportive"
    if "cautionary" in directions:
        return "cautionary"
    return "neutral"


def _signal_direction(factors: list[dict[str, Any]], *, state: str) -> str:
    if state == "conflicting":
        return "conflicting"
    if state in {"insufficient_evidence", "failed"}:
        return "unknown"
    score = _signal_score(factors)
    if score > 0.2:
        return "supportive"
    if score < -0.2:
        return "cautionary"
    return "neutral"


def _signal_score(factors: list[dict[str, Any]]) -> float:
    scores = []
    for factor in factors:
        try:
            score = float(factor.get("score"))
        except (TypeError, ValueError):
            continue
        if -1.0 <= score <= 1.0:
            scores.append(score)
    if not scores:
        return 0.0
    return round(max(-1.0, min(1.0, sum(scores) / len(scores))), 4)


def _signal_confidence(factors: list[dict[str, Any]], *, state: str) -> str:
    if not factors or state in {"failed", "insufficient_evidence", "conflicting"}:
        return "low"
    values = [_confidence_value(factor.get("confidence")) for factor in factors]
    average = sum(values) / len(values) if values else 0.0
    if state == "degraded":
        average *= 0.5
    if average >= 0.75:
        return "high"
    if average >= 0.45:
        return "medium"
    return "low"


def _factor_score_summary(factors: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "factor_count": len(factors),
        "average_score": _signal_score(factors),
        "supportive": sum(1 for factor in factors if _direction(factor.get("direction")) == "supportive"),
        "cautionary": sum(1 for factor in factors if _direction(factor.get("direction")) == "cautionary"),
        "neutral": sum(1 for factor in factors if _direction(factor.get("direction")) == "neutral"),
        "conflicting": sum(
            1
            for factor in factors
            if _direction(factor.get("direction")) == "conflicting" or _state(factor.get("state")) == "conflicting"
        ),
        "insufficient_evidence": sum(1 for factor in factors if _state(factor.get("state")) == "insufficient_evidence"),
        "degraded": sum(1 for factor in factors if _state(factor.get("state")) in {"degraded", "stale"}),
        "failed": sum(1 for factor in factors if _state(factor.get("state")) == "failed"),
    }


def _record_evidence(factors: list[dict[str, Any]], *, state: str, score: float) -> list[str]:
    evidence = [
        f"Multi-source signal state {state} with score {score}.",
        f"{len(factors)} factor state(s) contributed.",
    ]
    for factor in sorted(factors, key=lambda item: str(item.get("factor_id") or ""))[:8]:
        factor_id = str(factor.get("factor_id") or "missing_factor_id")
        evidence.append(
            f"{factor_id}: state={factor.get('state') or 'unknown'}, direction={factor.get('direction') or 'unknown'}, score={factor.get('score')}."
        )
        evidence.extend(_string_list(factor.get("evidence"))[:2])
    return _unique_ordered(evidence)


def _record_uncertainty(
    factors: list[dict[str, Any]],
    *,
    state: str,
    insufficient_factor_ids: list[str],
    degraded_factor_ids: list[str],
    failed_factor_ids: list[str],
) -> list[str]:
    uncertainty = [
        item
        for factor in factors
        for item in _string_list(factor.get("uncertainty"))
    ]
    if state == "conflicting":
        uncertainty.append("Supportive and cautionary factor directions are both present.")
    if insufficient_factor_ids:
        uncertainty.append("One or more factor states have insufficient evidence.")
    if degraded_factor_ids:
        uncertainty.append("One or more factor states are stale or degraded.")
    if failed_factor_ids:
        uncertainty.append("One or more factor states failed.")
    return _unique_ordered(uncertainty)


def _record_warnings(factors: list[dict[str, Any]], *, state: str) -> list[str]:
    warnings = [
        item
        for factor in factors
        for item in _string_list(factor.get("warnings"))
    ]
    if state == "conflicting":
        warnings.append("Multi-source signal has conflicting factor directions.")
    if state in {"degraded", "insufficient_evidence", "failed"}:
        warnings.append(f"Multi-source signal state is {state}.")
    return _unique_ordered(warnings)


def _record_errors(factors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        error
        for factor in factors
        for error in _error_list(factor.get("errors"))
    ]


def _factor_ids_by_direction(factors: list[dict[str, Any]], direction: str) -> list[str]:
    return sorted(
        str(factor.get("factor_id"))
        for factor in factors
        if factor.get("factor_id") and _direction(factor.get("direction")) == direction
    )


def _factor_ids_by_state(factors: list[dict[str, Any]], *states: str) -> list[str]:
    return sorted(
        str(factor.get("factor_id"))
        for factor in factors
        if factor.get("factor_id") and _state(factor.get("state")) in states
    )


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
        "state_counts": _count_by(records, "state"),
        "direction_counts": _count_by(records, "direction"),
        "confidence_counts": _count_by(records, "confidence"),
        "conflicting": sum(1 for record in records if record.get("state") == "conflicting"),
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
    if any(record.get("state") in {"conflicting", "degraded", "insufficient_evidence"} for record in records):
        return "warning"
    if warnings:
        return "warning"
    if records:
        return "ok"
    return "skipped"


def _record_manifest(run: RunContext, artifact: dict[str, Any]) -> None:
    counts = artifact["counts"]
    run.manifest["artifacts"]["multi_source_signals"] = MULTI_SOURCE_SIGNALS_ARTIFACT
    run.manifest["multi_source_signals"] = {
        "status": artifact["status"],
        "artifact": MULTI_SOURCE_SIGNALS_ARTIFACT,
        "records": counts["records"],
        "state_counts": counts["state_counts"],
        "direction_counts": counts["direction_counts"],
        "confidence_counts": counts["confidence_counts"],
        "conflicting": counts["conflicting"],
        "warnings": counts["warnings"],
        "errors": counts["errors"],
    }
    run.manifest["counts"]["multi_source_signals"] = counts["records"]
    run.manifest["counts"]["multi_source_signal_conflicting"] = counts["conflicting"]
    run.manifest["counts"]["multi_source_signal_warnings"] = counts["warnings"]
    run.manifest["counts"]["multi_source_signal_errors"] = counts["errors"]


def _scope_tuple(value: Any) -> tuple[tuple[str, str | None], ...]:
    scope = value if isinstance(value, dict) else {}
    return tuple(
        (key, _text_or_none(scope.get(key)))
        for key in ("symbol", "timeframe", "asset", "chain", "region")
    )


def _scope_dict(scope: tuple[tuple[str, str | None], ...]) -> dict[str, str | None]:
    return {key: value for key, value in scope}


def _scope_key(scope: dict[str, Any]) -> str:
    values = [scope.get(key) for key in ("symbol", "timeframe", "asset", "chain", "region") if scope.get(key)]
    return ":".join(_slug(value) for value in values) or "global"


def _scope_sort_key(scope: tuple[tuple[str, str | None], ...]) -> tuple[str, ...]:
    return tuple(value or "" for _, value in scope)


def _state(value: Any) -> str:
    state = str(value or "unknown").strip().lower()
    if state in {
        "supportive",
        "cautionary",
        "neutral",
        "conflicting",
        "insufficient_evidence",
        "degraded",
        "failed",
        "stale",
    }:
        return state
    return "unknown"


def _direction(value: Any) -> str:
    direction = str(value or "unknown").strip().lower()
    if direction in {"supportive", "cautionary", "neutral", "conflicting", "unknown"}:
        return direction
    return "unknown"


def _confidence_value(value: Any) -> float:
    return {
        "high": 1.0,
        "medium": 0.75,
        "low": 0.5,
        "unknown": 0.25,
    }.get(_confidence(value), 0.25)


def _confidence(value: Any) -> str:
    confidence = str(value or "unknown").strip().lower()
    if confidence in {"high", "medium", "low", "unknown"}:
        return confidence
    return "unknown"


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


def _created_at(factor_states: dict[str, Any], value: datetime | str | None = None) -> str:
    if isinstance(value, str):
        return value
    if value is not None:
        return _format_utc(value)
    created_at = factor_states.get("created_at")
    if isinstance(created_at, str) and created_at:
        return created_at
    return _format_utc()


def _format_utc(value: datetime | None = None) -> str:
    timestamp = value or datetime.now(timezone.utc)
    timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)
    return timestamp.isoformat().replace("+00:00", "Z")
