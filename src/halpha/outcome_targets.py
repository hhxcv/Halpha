from __future__ import annotations

from contextlib import closing
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from .pipeline import RunContext
from .run_index import RUN_INDEX_ARTIFACT, run_index_path
from .storage import display_path, write_json


STAGE_NAME = "build_outcome_targets"
OUTCOME_TARGETS_ARTIFACT = "analysis/outcome_targets.json"
SCHEMA_VERSION = 1
SOURCE_ARTIFACTS: dict[str, dict[str, str]] = {
    "market_signals": {
        "path": "analysis/market_signals.json",
        "records_key": "signals",
        "target_kind": "market_signal",
        "record_type": "market_signal",
    },
    "strategy_effectiveness_gates": {
        "path": "analysis/strategy_effectiveness_gates.json",
        "records_key": "records",
        "target_kind": "strategy_gate",
        "record_type": "strategy_effectiveness_gate",
    },
    "event_intelligence_assessment": {
        "path": "analysis/event_intelligence_assessment.json",
        "records_key": "records",
        "target_kind": "event_assessment",
        "record_type": "event_intelligence_assessment",
    },
    "alert_decisions": {
        "path": "analysis/alert_decisions.json",
        "records_key": "records",
        "target_kind": "alert_decision",
        "record_type": "alert_decision",
    },
    "decision_recommendations": {
        "path": "analysis/decision_recommendations.json",
        "records_key": "records",
        "target_kind": "decision_recommendation",
        "record_type": "decision_recommendation",
    },
    "watch_triggers": {
        "path": "analysis/watch_triggers.json",
        "records_key": "records",
        "target_kind": "watch_trigger",
        "record_type": "watch_trigger",
    },
}


@dataclass(frozen=True)
class PreviousRun:
    run_id: str
    run_dir: Path
    finished_at: str | None
    artifacts: dict[str, str]


def build_outcome_targets(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    del config
    created_at = _created_at(run, now)
    previous, previous_warning = _latest_previous_successful_run(run.config_path, current_run_id=run.run_id)
    if previous is None:
        warning = previous_warning or "No previous successful run found in run index."
        artifact = _empty_artifact(
            run,
            created_at=created_at,
            status="skipped",
            previous_run={"status": "no_previous_run", "reason": warning},
            warnings=[warning],
        )
        return _write_artifact(run, artifact)

    targets: list[dict[str, Any]] = []
    skipped_records: list[dict[str, Any]] = []
    warnings: list[str] = []
    errors: list[dict[str, Any]] = []
    seen_target_ids: set[str] = set()
    source_artifacts = [RUN_INDEX_ARTIFACT]

    for artifact_key in SOURCE_ARTIFACTS:
        indexed_path = previous.artifacts.get(artifact_key)
        if not indexed_path:
            continue
        source_artifacts.append(indexed_path)
        artifact, read_error = _read_previous_artifact(previous, indexed_path)
        if read_error:
            errors.append({"source_artifact": indexed_path, "message": read_error})
            continue
        spec = SOURCE_ARTIFACTS[artifact_key]
        records = _records(artifact, spec["records_key"])
        if not records:
            continue
        for record in records:
            record_variants = _record_variants_for_target(
                record,
                artifact=artifact,
                source_run=previous,
                target_kind=spec["target_kind"],
            )
            if not record_variants:
                record_variants = [record]
            for record_variant in record_variants:
                target, skipped = _target_from_record(
                    record_variant,
                    artifact=artifact,
                    source_run=previous,
                    source_artifact=indexed_path,
                    target_kind=spec["target_kind"],
                    record_type=spec["record_type"],
                    created_at=created_at,
                )
                if skipped is not None:
                    skipped_records.append(skipped)
                    continue
                if target is None:
                    continue
                if target["target_id"] in seen_target_ids:
                    skipped_records.append(
                        _skip_record(
                            source_artifact=indexed_path,
                            record_type=spec["record_type"],
                            record_id=target["source_record_id"],
                            reason="duplicate_target_id",
                        )
                    )
                    continue
                seen_target_ids.add(target["target_id"])
                targets.append(target)

    warnings.extend(_warning_summary(skipped_records, errors, targets))
    status = _status(targets=targets, warnings=warnings, errors=errors)
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "outcome_targets",
        "run_id": run.run_id,
        "created_at": created_at,
        "status": status,
        "previous_run": {
            "status": "found",
            "run_id": previous.run_id,
            "run_dir": display_path(previous.run_dir, base=run.config_path.parent),
            "finished_at": previous.finished_at,
        },
        "target_policy": _target_policy(),
        "targets": sorted(targets, key=lambda item: item["target_id"]),
        "skipped_records": sorted(
            skipped_records,
            key=lambda item: (
                str(item.get("source_artifact") or ""),
                str(item.get("source_record_type") or ""),
                str(item.get("source_record_id") or ""),
                str(item.get("reason") or ""),
            ),
        ),
        "counts": _counts(targets, skipped_records, errors),
        "source_artifacts": _unique(source_artifacts),
        "warnings": warnings,
        "errors": errors,
    }
    return _write_artifact(run, artifact)


def _record_variants_for_target(
    record: dict[str, Any],
    *,
    artifact: dict[str, Any],
    source_run: PreviousRun,
    target_kind: str,
) -> list[dict[str, Any]]:
    if target_kind != "strategy_gate" or _has_direct_scope(record):
        return [record]
    experiment = _strategy_experiment_artifact(record, artifact, source_run)
    if experiment is None:
        return [record]
    candidate = _matching_strategy_candidate(record, experiment)
    if candidate is None:
        return [record]
    variants = []
    for evaluation in _dict_list(candidate.get("evaluations")):
        variant = _strategy_gate_variant(record, evaluation)
        if variant is not None:
            variants.append(variant)
    return variants


def _has_direct_scope(record: dict[str, Any]) -> bool:
    return bool(_source(record) and _symbol(record) and _timeframe(record))


def _strategy_experiment_artifact(
    record: dict[str, Any],
    artifact: dict[str, Any],
    source_run: PreviousRun,
) -> dict[str, Any] | None:
    source_artifacts = [
        *_string_list(record.get("source_artifacts")),
        *_string_list(artifact.get("source_artifacts")),
    ]
    for source_artifact in source_artifacts:
        if source_artifact.endswith("strategy_experiment.json"):
            experiment, error = _read_previous_artifact(source_run, source_artifact)
            if error is None:
                return experiment
    return None


def _matching_strategy_candidate(record: dict[str, Any], experiment: dict[str, Any]) -> dict[str, Any] | None:
    strategy_name = record.get("strategy_name")
    for candidate in _dict_list(experiment.get("candidates")):
        if candidate.get("strategy_name") == strategy_name:
            return candidate
    return None


def _strategy_gate_variant(record: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any] | None:
    source = evaluation.get("source")
    symbol = evaluation.get("symbol")
    timeframe = evaluation.get("timeframe")
    source_as_of = evaluation.get("input_window_end") or evaluation.get("latest_candle_time")
    if not all(isinstance(value, str) and value for value in (source, symbol, timeframe, source_as_of)):
        return None
    gate_id = _optional_str(record.get("gate_id")) or _optional_str(record.get("strategy_name")) or "strategy_gate"
    evaluation_id = (
        _optional_str(evaluation.get("evaluation_id"))
        or _optional_str(evaluation.get("benchmark_id"))
        or f"{source}:{symbol}:{timeframe}:{source_as_of}"
    )
    variant = {**record}
    variant.update(
        {
            "gate_id": f"{gate_id}:{_short_digest(evaluation_id)}",
            "gate_record_id": gate_id,
            "gate_scope_id": evaluation_id,
            "source": source,
            "symbol": symbol,
            "asset": symbol,
            "timeframe": timeframe,
            "source_as_of": source_as_of,
            "latest_candle_time": source_as_of,
            "benchmark_id": evaluation.get("benchmark_id"),
            "evaluation_id": evaluation.get("evaluation_id"),
            "benchmark_status": evaluation.get("benchmark_status"),
            "evaluation_status": evaluation.get("status"),
            "source_artifacts": _unique(
                [
                    *_string_list(record.get("source_artifacts")),
                    "analysis/strategy_experiment.json",
                ]
            ),
            "warnings": _unique([*_string_list(record.get("warnings")), *_string_list(evaluation.get("warnings"))]),
            "errors": [*_dict_list(record.get("errors")), *_dict_list(evaluation.get("errors"))],
        }
    )
    return variant


def _short_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _latest_previous_successful_run(config_path: Path, *, current_run_id: str) -> tuple[PreviousRun | None, str | None]:
    index_path = run_index_path(config_path)
    if not index_path.exists():
        return None, "Run index was not found; no previous successful run can be selected."
    try:
        with closing(sqlite3.connect(index_path)) as connection:
            row = connection.execute(
                """
                SELECT run_id, run_dir, finished_at
                FROM runs
                WHERE status = 'succeeded' AND run_id <> ?
                ORDER BY COALESCE(finished_at, started_at, run_id) DESC, run_id DESC
                LIMIT 1
                """,
                (current_run_id,),
            ).fetchone()
            if row is None:
                return None, "No previous successful run found in run index."
            artifacts = {
                str(artifact_key): str(path)
                for artifact_key, path in connection.execute(
                    """
                    SELECT artifact_key, path
                    FROM run_artifacts
                    WHERE run_id = ?
                    ORDER BY artifact_key, path
                    """,
                    (row[0],),
                ).fetchall()
                if artifact_key in SOURCE_ARTIFACTS and isinstance(path, str) and path
            }
    except sqlite3.Error as exc:
        return None, f"{RUN_INDEX_ARTIFACT} is not readable: {exc}"

    run_dir = Path(str(row[1]))
    if not run_dir.is_absolute():
        run_dir = config_path.parent / run_dir
    return PreviousRun(run_id=str(row[0]), run_dir=run_dir, finished_at=_optional_str(row[2]), artifacts=artifacts), None


def _read_previous_artifact(previous: PreviousRun, artifact_path: str) -> tuple[dict[str, Any] | None, str | None]:
    path = Path(artifact_path)
    if not path.is_absolute():
        path = previous.run_dir / path
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, f"{artifact_path} was listed in run index but was not found."
    except JSONDecodeError as exc:
        return None, f"{artifact_path} is not valid JSON: {exc.msg}."
    if not isinstance(artifact, dict):
        return None, f"{artifact_path} must be a JSON object."
    return artifact, None


def _target_from_record(
    record: dict[str, Any],
    *,
    artifact: dict[str, Any],
    source_run: PreviousRun,
    source_artifact: str,
    target_kind: str,
    record_type: str,
    created_at: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    record_id = _record_id(record, record_type)
    source_as_of = _source_as_of(record, artifact, source_run)
    symbol = _symbol(record)
    timeframe = _timeframe(record)
    source = _source(record)
    skip_reason = _not_evaluable_reason(record, target_kind)
    if skip_reason:
        return None, _skip_record(
            source_artifact=source_artifact,
            record_type=record_type,
            record_id=record_id,
            reason=skip_reason,
        )

    missing = [
        name
        for name, value in (
            ("source_record_id", record_id),
            ("source_as_of", source_as_of),
            ("symbol", symbol),
            ("timeframe", timeframe),
        )
        if not value
    ]
    if missing:
        return None, _skip_record(
            source_artifact=source_artifact,
            record_type=record_type,
            record_id=record_id,
            reason="missing_source_fields",
            missing_fields=missing,
        )

    horizon = _horizon(target_kind, timeframe=timeframe, source_as_of=source_as_of, created_at=created_at)
    target_id = _target_id(
        target_kind=target_kind,
        source_run_id=source_run.run_id,
        source_artifact=source_artifact,
        source_record_id=record_id,
        horizon_id=horizon["horizon_id"],
    )
    target = {
        "target_id": target_id,
        "target_kind": target_kind,
        "source_run_id": source_run.run_id,
        "source_artifact": source_artifact,
        "source_record_id": record_id,
        "source_record_type": record_type,
        "source_created_at": _optional_str(artifact.get("created_at")),
        "source_as_of": source_as_of,
        "source": source,
        "asset": symbol,
        "symbol": symbol,
        "timeframe": timeframe,
        "horizon": horizon,
        "maturity_status": _maturity_status(horizon, created_at=created_at),
        "expected_observation": _expected_observation(record, target_kind),
        "evidence": _evidence(record),
        "uncertainty": _string_list(record.get("uncertainty")),
        "warnings": _string_list(record.get("warnings")),
        "errors": _dict_list(record.get("errors")),
        "source_artifacts": _unique([source_artifact, *_string_list(record.get("source_artifacts"))]),
    }
    return target, None


def _empty_artifact(
    run: RunContext,
    *,
    created_at: str,
    status: str,
    previous_run: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "outcome_targets",
        "run_id": run.run_id,
        "created_at": created_at,
        "status": status,
        "previous_run": previous_run,
        "target_policy": _target_policy(),
        "targets": [],
        "skipped_records": [],
        "counts": {
            "targets": 0,
            "skipped_records": 0,
            "duplicate_records": 0,
            "missing_source_fields": 0,
            "errors": 0,
            "skipped_reasons": {},
            "by_kind": {},
            "by_maturity_status": {},
        },
        "source_artifacts": [RUN_INDEX_ARTIFACT],
        "warnings": warnings,
        "errors": [],
    }


def _write_artifact(run: RunContext, artifact: dict[str, Any]) -> list[str]:
    write_json(run.analysis_dir / "outcome_targets.json", artifact)
    counts = artifact["counts"]
    run.manifest["artifacts"]["outcome_targets"] = OUTCOME_TARGETS_ARTIFACT
    run.manifest["outcome_targets"] = {
        "status": artifact["status"],
        "artifact": OUTCOME_TARGETS_ARTIFACT,
        "source_run_id": artifact.get("previous_run", {}).get("run_id"),
        "target_count": counts["targets"],
        "skipped_record_count": counts["skipped_records"],
        "skipped_reasons": counts["skipped_reasons"],
        "warning_count": len(artifact["warnings"]),
        "error_count": len(artifact["errors"]),
    }
    run.manifest["counts"]["outcome_targets"] = counts["targets"]
    run.manifest["counts"]["outcome_target_skipped_records"] = counts["skipped_records"]
    run.manifest["counts"]["outcome_target_duplicate_records"] = counts["duplicate_records"]
    run.manifest["counts"]["outcome_target_missing_source_fields"] = counts["missing_source_fields"]
    run.manifest["counts"]["outcome_target_errors"] = counts["errors"]
    return [OUTCOME_TARGETS_ARTIFACT]


def _target_policy() -> dict[str, Any]:
    return {
        "source_run_selection": "latest_previous_successful_run",
        "source_artifact_keys": sorted(SOURCE_ARTIFACTS),
        "llm_generated_targets": False,
        "codex_generated_targets": False,
        "no_lookahead_enforced_by_source_as_of": True,
        "default_horizons": {
            "market_signal": "next_candle",
            "strategy_gate": "next_candle_when_timeframe_is_available",
            "event_assessment": "next_run",
            "alert_decision": "next_run",
            "decision_recommendation": "next_candle",
            "watch_trigger": "next_run",
        },
    }


def _records(artifact: dict[str, Any] | None, key: str) -> list[dict[str, Any]]:
    if artifact is None:
        return []
    records = artifact.get(key)
    if not isinstance(records, list):
        return []
    return [record for record in records if isinstance(record, dict)]


def _record_id(record: dict[str, Any], record_type: str) -> str | None:
    fields = {
        "market_signal": ("signal_id",),
        "strategy_effectiveness_gate": ("gate_id",),
        "event_intelligence_assessment": ("assessment_id",),
        "alert_decision": ("alert_decision_id",),
        "decision_recommendation": ("record_id",),
        "watch_trigger": ("trigger_id",),
    }.get(record_type, ())
    for field in fields:
        value = record.get(field)
        if isinstance(value, str) and value:
            return value
    return None


def _source_as_of(record: dict[str, Any], artifact: dict[str, Any], source_run: PreviousRun) -> str | None:
    for value in (
        record.get("source_as_of"),
        record.get("latest_candle_time"),
        record.get("created_at"),
        artifact.get("created_at"),
        source_run.finished_at,
    ):
        timestamp = _format_utc_or_none(value)
        if timestamp:
            return timestamp
    return None


def _symbol(record: dict[str, Any]) -> str | None:
    scope = record.get("scope") if isinstance(record.get("scope"), dict) else {}
    for value in (
        record.get("symbol"),
        scope.get("symbol"),
        _first_string(record.get("affected_assets")),
    ):
        if isinstance(value, str) and value:
            return value
    return None


def _timeframe(record: dict[str, Any]) -> str | None:
    scope = record.get("scope") if isinstance(record.get("scope"), dict) else {}
    for value in (
        record.get("timeframe"),
        scope.get("timeframe"),
        _first_string(record.get("relevant_timeframes")),
    ):
        if isinstance(value, str) and value:
            return value
    return None


def _source(record: dict[str, Any]) -> str | None:
    value = record.get("source")
    if isinstance(value, str) and value:
        return value
    return None


def _not_evaluable_reason(record: dict[str, Any], target_kind: str) -> str | None:
    if target_kind == "market_signal":
        if record.get("insufficient_data") is True:
            return "insufficient_source_evidence"
        direction = str(record.get("direction") or "unknown")
        if direction == "unknown":
            return "unknown_market_direction"
    if target_kind == "decision_recommendation":
        if str(record.get("status") or "") == "insufficient_data":
            return "insufficient_source_evidence"
    if target_kind == "alert_decision":
        if str(record.get("priority") or "") == "unknown":
            return "unknown_alert_priority"
    if target_kind == "watch_trigger" and not record.get("condition"):
        return "missing_watch_condition"
    return None


def _horizon(target_kind: str, *, timeframe: str, source_as_of: str, created_at: str) -> dict[str, Any]:
    start = _parse_utc(source_as_of)
    current = _parse_utc(created_at)
    duration = _timeframe_duration(timeframe)
    if target_kind in {"market_signal", "decision_recommendation", "strategy_gate"} and duration is not None:
        matures = start + duration
        return {
            "horizon_id": f"{target_kind}:{timeframe}:next_candle",
            "horizon_kind": "next_candle",
            "duration": _duration_label(duration),
            "start_at": _format_utc(start),
            "matures_at": _format_utc(matures),
            "expires_at": None,
            "observation_window_start": _format_utc(start),
            "observation_window_end": _format_utc(matures),
        }
    return {
        "horizon_id": f"{target_kind}:next_run",
        "horizon_kind": "next_run",
        "duration": None,
        "start_at": _format_utc(start),
        "matures_at": _format_utc(current),
        "expires_at": None,
        "observation_window_start": _format_utc(start),
        "observation_window_end": _format_utc(current),
    }


def _maturity_status(horizon: dict[str, Any], *, created_at: str) -> str:
    matures_at = _parse_utc(str(horizon["matures_at"]))
    current = _parse_utc(created_at)
    return "matured" if current >= matures_at else "pending"


def _expected_observation(record: dict[str, Any], target_kind: str) -> dict[str, Any]:
    if target_kind == "market_signal":
        return {
            "observation_type": "directional_market_move",
            "direction": record.get("direction"),
            "strength": record.get("strength"),
            "confidence": record.get("confidence"),
        }
    if target_kind == "strategy_gate":
        return {
            "observation_type": "strategy_gate_follow_through",
            "strategy_name": record.get("strategy_name"),
            "gate_status": record.get("status"),
            "gate_record_id": record.get("gate_record_id") or record.get("gate_id"),
            "gate_scope_id": record.get("gate_scope_id"),
            "benchmark_id": record.get("benchmark_id"),
            "evaluation_id": record.get("evaluation_id"),
            "benchmark_status": record.get("benchmark_status"),
            "evaluation_status": record.get("evaluation_status"),
            "reason_codes": [
                item.get("code")
                for item in _dict_list(record.get("reasons"))
                if isinstance(item.get("code"), str)
            ],
        }
    if target_kind == "event_assessment":
        return {
            "observation_type": "event_follow_through",
            "event_severity": record.get("event_severity"),
            "decision_impact": record.get("decision_impact"),
            "risk_effect": record.get("risk_effect"),
            "watch_relevance": record.get("watch_relevance"),
        }
    if target_kind == "alert_decision":
        return {
            "observation_type": "alert_follow_through",
            "priority": record.get("priority"),
            "attention_decision": record.get("attention_decision"),
            "requires_reassessment": record.get("requires_reassessment"),
            "requires_user_attention": record.get("requires_user_attention"),
        }
    if target_kind == "decision_recommendation":
        return {
            "observation_type": "decision_follow_through",
            "action_level": record.get("action_level"),
            "decision_bias": record.get("decision_bias"),
            "status": record.get("status"),
        }
    if target_kind == "watch_trigger":
        return {
            "observation_type": "watch_condition_follow_through",
            "trigger_type": record.get("type"),
            "condition": record.get("condition"),
            "linked_decision_record_id": record.get("linked_decision_record_id"),
        }
    return {"observation_type": "unknown"}


def _evidence(record: dict[str, Any]) -> list[Any]:
    evidence = record.get("evidence")
    if isinstance(evidence, list):
        return evidence
    reasons = record.get("reasons")
    if isinstance(reasons, list):
        return reasons
    condition = record.get("condition")
    if isinstance(condition, str) and condition:
        return [condition]
    return []


def _target_id(
    *,
    target_kind: str,
    source_run_id: str,
    source_artifact: str,
    source_record_id: str,
    horizon_id: str,
) -> str:
    digest_input = "|".join([source_run_id, source_artifact, source_record_id, horizon_id])
    digest = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()[:16]
    return f"outcome_target:{target_kind}:{source_run_id}:{digest}"


def _skip_record(
    *,
    source_artifact: str,
    record_type: str,
    record_id: str | None,
    reason: str,
    missing_fields: list[str] | None = None,
) -> dict[str, Any]:
    record = {
        "source_artifact": source_artifact,
        "source_record_type": record_type,
        "source_record_id": record_id,
        "reason": reason,
    }
    if missing_fields:
        record["missing_fields"] = missing_fields
    return record


def _warning_summary(
    skipped_records: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    targets: list[dict[str, Any]],
) -> list[str]:
    warnings = []
    if skipped_records:
        warnings.append(f"Skipped {len(skipped_records)} outcome target source records.")
    if errors:
        warnings.append(f"Encountered {len(errors)} outcome target source artifact errors.")
    if not targets:
        warnings.append("No evaluable outcome targets were extracted from the selected previous run.")
    return warnings


def _status(*, targets: list[dict[str, Any]], warnings: list[str], errors: list[dict[str, Any]]) -> str:
    if errors:
        return "degraded" if targets else "failed"
    if warnings:
        return "warning" if targets else "skipped"
    return "ok"


def _counts(
    targets: list[dict[str, Any]],
    skipped_records: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "targets": len(targets),
        "skipped_records": len(skipped_records),
        "duplicate_records": sum(1 for record in skipped_records if record.get("reason") == "duplicate_target_id"),
        "missing_source_fields": sum(
            1 for record in skipped_records if record.get("reason") == "missing_source_fields"
        ),
        "errors": len(errors),
        "skipped_reasons": _count_by(skipped_records, "reason"),
        "by_kind": _count_by(targets, "target_kind"),
        "by_maturity_status": _count_by(targets, "maturity_status"),
    }


def _count_by(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(record.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _created_at(run: RunContext, now: datetime | str | None) -> str:
    if now is not None:
        return _format_utc_value(now)
    started_at = run.manifest.get("started_at")
    timestamp = _format_utc_or_none(started_at)
    if timestamp:
        return timestamp
    return _format_utc(datetime.now(UTC))


def _format_utc_value(value: datetime | str) -> str:
    if isinstance(value, str):
        parsed = _format_utc_or_none(value)
        if parsed is None:
            raise ValueError("timestamp must be an ISO 8601 UTC string.")
        return parsed
    return _format_utc(value)


def _format_utc_or_none(value: Any) -> str | None:
    if isinstance(value, datetime):
        return _format_utc(value)
    if not isinstance(value, str) or not value:
        return None
    try:
        return _format_utc(_parse_utc(value))
    except ValueError:
        return None


def _parse_utc(value: str) -> datetime:
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("timestamp must include a UTC offset.")
    return timestamp.astimezone(UTC).replace(microsecond=0)


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamp must include a UTC offset.")
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _timeframe_duration(timeframe: str) -> timedelta | None:
    if len(timeframe) < 2:
        return None
    try:
        amount = int(timeframe[:-1])
    except ValueError:
        return None
    unit = timeframe[-1]
    if amount <= 0:
        return None
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "h":
        return timedelta(hours=amount)
    if unit == "d":
        return timedelta(days=amount)
    if unit == "w":
        return timedelta(weeks=amount)
    return None


def _duration_label(value: timedelta) -> str:
    seconds = int(value.total_seconds())
    if seconds % 604800 == 0:
        return f"{seconds // 604800}w"
    if seconds % 86400 == 0:
        return f"{seconds // 86400}d"
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    if seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _first_string(value: Any) -> str | None:
    values = _string_list(value)
    return values[0] if values else None


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _unique(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result
