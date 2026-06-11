from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from .pipeline import RunContext
from .storage import display_path, write_json


OUTCOME_HISTORY_SCHEMA_VERSION = 1
OUTCOME_EVALUATIONS_ARTIFACT = "analysis/outcome_evaluations.json"
OUTCOME_HISTORY_STORAGE_ARTIFACT = "data/research/outcomes"
OUTCOME_HISTORY_ARTIFACT = "data/research/outcomes/outcome_history.json"
OUTCOME_HISTORY_STATE_ARTIFACT = "data/research/metadata/outcome_history_state.json"


def write_outcome_history(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    del config
    evaluations_artifact = _read_outcome_evaluations(run)
    if evaluations_artifact is None:
        _record_manifest_summary(run, _skipped_state(run, reason="analysis/outcome_evaluations.json was not found.", now=now))
        return []

    incoming_records = _history_records(evaluations_artifact, run)
    existing_records = _read_history_records(outcome_history_path(run.config_path))
    merged_records, merge_summary = _merge_history(existing_records, incoming_records)
    warnings = _unique_sorted(merge_summary["warnings"])
    errors: list[dict[str, Any]] = []
    status = _status(record_count=len(merged_records), warnings=warnings, errors=errors)

    history = {
        "schema_version": OUTCOME_HISTORY_SCHEMA_VERSION,
        "artifact_type": "outcome_history",
        "updated_at": _format_utc(now),
        "storage_path": display_path(outcome_history_storage_path(run.config_path), base=run.config_path.parent),
        "record_count": len(merged_records),
        "records": sorted(merged_records, key=lambda item: item["stable_outcome_key"]),
    }
    write_json(outcome_history_path(run.config_path), history)

    state = {
        "schema_version": OUTCOME_HISTORY_SCHEMA_VERSION,
        "artifact_type": "outcome_history_state",
        "updated_at": _format_utc(now),
        "status": status,
        "storage_path": display_path(outcome_history_storage_path(run.config_path), base=run.config_path.parent),
        "history_path": display_path(outcome_history_path(run.config_path), base=run.config_path.parent),
        "state_path": display_path(outcome_history_state_path(run.config_path), base=run.config_path.parent),
        "totals": {
            "records": len(merged_records),
            "incoming_records": len(incoming_records),
            "inserted_records": merge_summary["inserted_records"],
            "updated_records": merge_summary["updated_records"],
            "duplicate_records": merge_summary["duplicate_records"],
            "conflicting_duplicates": merge_summary["conflicting_duplicates"],
            "warning_count": len(warnings),
            "error_count": len(errors),
        },
        "sources": _source_summaries(merged_records),
        "target_kinds": _value_summaries(merged_records, "target_kind"),
        "outcome_states": _value_summaries(merged_records, "outcome_state"),
        "evaluation_statuses": _value_summaries(merged_records, "evaluation_status"),
        "warnings": warnings,
        "errors": errors,
        "source_artifacts": [
            display_path(run.analysis_dir / "outcome_evaluations.json", base=run.config_path.parent)
        ],
    }
    write_json(outcome_history_state_path(run.config_path), state)
    _record_manifest_summary(run, state)
    return [OUTCOME_HISTORY_STATE_ARTIFACT]


def outcome_history_storage_path(config_path: Path) -> Path:
    return config_path.parent / OUTCOME_HISTORY_STORAGE_ARTIFACT


def outcome_history_path(config_path: Path) -> Path:
    return config_path.parent / OUTCOME_HISTORY_ARTIFACT


def outcome_history_state_path(config_path: Path) -> Path:
    return config_path.parent / OUTCOME_HISTORY_STATE_ARTIFACT


def _read_outcome_evaluations(run: RunContext) -> dict[str, Any] | None:
    path = run.analysis_dir / "outcome_evaluations.json"
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except JSONDecodeError as exc:
        raise ValueError(f"{OUTCOME_EVALUATIONS_ARTIFACT} is not valid JSON: {exc.msg}.") from exc
    if not isinstance(artifact, dict):
        raise ValueError(f"{OUTCOME_EVALUATIONS_ARTIFACT} must be a JSON object.")
    records = artifact.get("evaluations")
    if not isinstance(records, list):
        raise ValueError(f"{OUTCOME_EVALUATIONS_ARTIFACT} must contain an evaluations list.")
    return artifact


def _history_records(artifact: dict[str, Any], run: RunContext) -> list[dict[str, Any]]:
    records = []
    for evaluation in artifact.get("evaluations") or []:
        if not isinstance(evaluation, dict):
            continue
        records.append(_history_record(evaluation, run))
    return sorted(records, key=lambda item: item["stable_outcome_key"])


def _history_record(evaluation: dict[str, Any], run: RunContext) -> dict[str, Any]:
    observation_window = evaluation.get("observation_window")
    if not isinstance(observation_window, dict):
        observation_window = {}
    stable_key = _stable_outcome_key(evaluation, observation_window=observation_window)
    content_hash = _content_hash(evaluation)
    evaluated_at = _optional_text(evaluation.get("evaluated_at"))
    evaluation_run_id = _clean_text(evaluation.get("evaluation_run_id"), fallback=run.run_id)
    return {
        "stable_outcome_key": stable_key,
        "target_id": _clean_text(evaluation.get("target_id"), fallback="missing_target_id"),
        "target_kind": _clean_text(evaluation.get("target_kind"), fallback="unknown"),
        "source_run_id": _clean_text(evaluation.get("source_run_id"), fallback="unknown_source_run"),
        "outcome_id": _clean_text(evaluation.get("outcome_id"), fallback="missing_outcome_id"),
        "evaluation_run_ids": [evaluation_run_id],
        "first_evaluation_run_id": evaluation_run_id,
        "latest_evaluation_run_id": evaluation_run_id,
        "first_evaluated_at": evaluated_at,
        "latest_evaluated_at": evaluated_at,
        "evaluation_status": _clean_text(evaluation.get("evaluation_status"), fallback="unknown"),
        "outcome_state": _clean_text(evaluation.get("outcome_state"), fallback="unknown"),
        "source_as_of": _optional_text(observation_window.get("source_as_of")),
        "horizon_end": _optional_text(observation_window.get("horizon_end")),
        "observation_start": _optional_text(observation_window.get("start")),
        "observation_end": _optional_text(observation_window.get("end")),
        "sample_rows": _optional_int(observation_window.get("sample_rows")),
        "metrics": _object_or_empty(evaluation.get("metrics")),
        "evidence": _list_or_empty(evaluation.get("evidence")),
        "uncertainty": _string_list(evaluation.get("uncertainty")),
        "warnings": _string_list(evaluation.get("warnings")),
        "errors": _dict_list(evaluation.get("errors")),
        "source_artifacts": _source_artifacts(evaluation, run),
        "content_hash": content_hash,
        "status": "warning" if _string_list(evaluation.get("warnings")) else "active",
    }


def _read_history_records(path: Path) -> list[dict[str, Any]]:
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except JSONDecodeError as exc:
        raise ValueError(f"{OUTCOME_HISTORY_ARTIFACT} is not valid JSON: {exc.msg}.") from exc
    if not isinstance(artifact, dict):
        raise ValueError(f"{OUTCOME_HISTORY_ARTIFACT} must be a JSON object.")
    records = artifact.get("records")
    if not isinstance(records, list):
        raise ValueError(f"{OUTCOME_HISTORY_ARTIFACT} must contain a records list.")
    return [_normalize_existing(record) for record in records if isinstance(record, dict)]


def _merge_history(
    existing_records: list[dict[str, Any]],
    incoming_records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_key = {record["stable_outcome_key"]: record for record in existing_records}
    inserted = 0
    updated = 0
    duplicate = 0
    conflicts = 0
    warnings = []

    for incoming in incoming_records:
        existing = by_key.get(incoming["stable_outcome_key"])
        if existing is None:
            by_key[incoming["stable_outcome_key"]] = incoming
            inserted += 1
            continue

        duplicate += 1
        same_content = existing.get("content_hash") == incoming.get("content_hash")
        same_evaluation_run = incoming["latest_evaluation_run_id"] in _string_list(existing.get("evaluation_run_ids"))
        if not same_content:
            updated += 1
            if same_evaluation_run:
                conflicts += 1
                warning = f"conflicting duplicate outcome history record: {incoming['stable_outcome_key']}"
                warnings.append(warning)
                incoming["warnings"] = _unique_sorted([*incoming.get("warnings", []), warning])
                incoming["status"] = "warning"
        _merge_trace_fields(existing, incoming)
        if not same_content:
            _replace_latest_fields(existing, incoming)

    return (
        sorted(by_key.values(), key=lambda record: record["stable_outcome_key"]),
        {
            "inserted_records": inserted,
            "updated_records": updated,
            "duplicate_records": duplicate,
            "conflicting_duplicates": conflicts,
            "warnings": _unique_sorted(warnings),
        },
    )


def _merge_trace_fields(existing: dict[str, Any], incoming: dict[str, Any]) -> None:
    existing["evaluation_run_ids"] = _unique_sorted(
        [*_string_list(existing.get("evaluation_run_ids")), *_string_list(incoming.get("evaluation_run_ids"))]
    )
    existing["first_evaluation_run_id"] = (
        existing.get("first_evaluation_run_id") or incoming.get("first_evaluation_run_id")
    )
    existing["latest_evaluation_run_id"] = incoming["latest_evaluation_run_id"]
    existing["first_evaluated_at"] = _earliest_timestamp(
        existing.get("first_evaluated_at"),
        incoming.get("first_evaluated_at"),
    )
    existing["latest_evaluated_at"] = _latest_timestamp(
        existing.get("latest_evaluated_at"),
        incoming.get("latest_evaluated_at"),
    )
    existing["source_artifacts"] = _unique_sorted(
        [*_string_list(existing.get("source_artifacts")), *_string_list(incoming.get("source_artifacts"))]
    )


def _replace_latest_fields(existing: dict[str, Any], incoming: dict[str, Any]) -> None:
    for field in (
        "outcome_id",
        "evaluation_status",
        "outcome_state",
        "source_as_of",
        "horizon_end",
        "observation_start",
        "observation_end",
        "sample_rows",
        "metrics",
        "evidence",
        "uncertainty",
        "warnings",
        "errors",
        "content_hash",
        "status",
    ):
        existing[field] = incoming[field]


def _normalize_existing(record: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        "stable_outcome_key": _clean_text(record.get("stable_outcome_key"), fallback="missing_stable_outcome_key"),
        "target_id": _clean_text(record.get("target_id"), fallback="missing_target_id"),
        "target_kind": _clean_text(record.get("target_kind"), fallback="unknown"),
        "source_run_id": _clean_text(record.get("source_run_id"), fallback="unknown_source_run"),
        "outcome_id": _clean_text(record.get("outcome_id"), fallback="missing_outcome_id"),
        "evaluation_run_ids": _string_list(record.get("evaluation_run_ids")),
        "first_evaluation_run_id": _optional_text(record.get("first_evaluation_run_id")),
        "latest_evaluation_run_id": _optional_text(record.get("latest_evaluation_run_id")),
        "first_evaluated_at": _optional_text(record.get("first_evaluated_at")),
        "latest_evaluated_at": _optional_text(record.get("latest_evaluated_at")),
        "evaluation_status": _clean_text(record.get("evaluation_status"), fallback="unknown"),
        "outcome_state": _clean_text(record.get("outcome_state"), fallback="unknown"),
        "source_as_of": _optional_text(record.get("source_as_of")),
        "horizon_end": _optional_text(record.get("horizon_end")),
        "observation_start": _optional_text(record.get("observation_start")),
        "observation_end": _optional_text(record.get("observation_end")),
        "sample_rows": _optional_int(record.get("sample_rows")),
        "metrics": _object_or_empty(record.get("metrics")),
        "evidence": _list_or_empty(record.get("evidence")),
        "uncertainty": _string_list(record.get("uncertainty")),
        "warnings": _string_list(record.get("warnings")),
        "errors": _dict_list(record.get("errors")),
        "source_artifacts": _string_list(record.get("source_artifacts")),
        "content_hash": _clean_text(record.get("content_hash"), fallback=""),
        "status": _clean_text(record.get("status"), fallback="active"),
    }
    if not normalized["evaluation_run_ids"] and normalized["latest_evaluation_run_id"]:
        normalized["evaluation_run_ids"] = [normalized["latest_evaluation_run_id"]]
    return normalized


def _skipped_state(run: RunContext, *, reason: str, now: datetime | str | None) -> dict[str, Any]:
    return {
        "schema_version": OUTCOME_HISTORY_SCHEMA_VERSION,
        "artifact_type": "outcome_history_state",
        "updated_at": _format_utc(now),
        "status": "skipped",
        "storage_path": display_path(outcome_history_storage_path(run.config_path), base=run.config_path.parent),
        "history_path": display_path(outcome_history_path(run.config_path), base=run.config_path.parent),
        "state_path": display_path(outcome_history_state_path(run.config_path), base=run.config_path.parent),
        "totals": {
            "records": 0,
            "incoming_records": 0,
            "inserted_records": 0,
            "updated_records": 0,
            "duplicate_records": 0,
            "conflicting_duplicates": 0,
            "warning_count": 1,
            "error_count": 0,
        },
        "sources": [],
        "target_kinds": [],
        "outcome_states": [],
        "evaluation_statuses": [],
        "warnings": [reason],
        "errors": [],
        "source_artifacts": [],
    }


def _record_manifest_summary(run: RunContext, state: dict[str, Any]) -> None:
    totals = state["totals"]
    if state["status"] != "skipped":
        run.manifest["artifacts"]["outcome_history_state"] = OUTCOME_HISTORY_STATE_ARTIFACT
    run.manifest["outcome_history"] = {
        "status": state["status"],
        "storage_path": state["storage_path"],
        "history_path": state["history_path"],
        "state_path": state["state_path"],
        "records": totals["records"],
        "incoming_records": totals["incoming_records"],
        "duplicate_records": totals["duplicate_records"],
        "conflicting_duplicates": totals["conflicting_duplicates"],
        "warnings": totals["warning_count"],
        "errors": totals["error_count"],
    }
    run.manifest["counts"]["outcome_history_records"] = totals["records"]
    run.manifest["counts"]["outcome_history_incoming_records"] = totals["incoming_records"]
    run.manifest["counts"]["outcome_history_duplicate_records"] = totals["duplicate_records"]
    run.manifest["counts"]["outcome_history_conflicting_duplicates"] = totals["conflicting_duplicates"]
    run.manifest["counts"]["outcome_history_warnings"] = totals["warning_count"]
    run.manifest["counts"]["outcome_history_errors"] = totals["error_count"]


def _source_summaries(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_source: dict[str, int] = {}
    for record in records:
        source_run_id = str(record.get("source_run_id") or "unknown_source_run")
        by_source[source_run_id] = by_source.get(source_run_id, 0) + 1
    return [
        {"source_run_id": source_run_id, "record_count": count}
        for source_run_id, count in sorted(by_source.items())
    ]


def _value_summaries(records: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(record.get(field) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return [{"value": value, "record_count": count} for value, count in sorted(counts.items())]


def _source_artifacts(evaluation: dict[str, Any], run: RunContext) -> list[str]:
    artifacts = [display_path(run.analysis_dir / "outcome_evaluations.json", base=run.config_path.parent)]
    for artifact in _string_list(evaluation.get("source_artifacts")):
        if artifact.startswith("data/") or artifact.startswith("runs/"):
            artifacts.append(artifact)
        elif Path(artifact).is_absolute():
            artifacts.append(display_path(Path(artifact), base=run.config_path.parent))
        else:
            artifacts.append(display_path(run.run_dir / artifact, base=run.config_path.parent))
    return _unique_sorted(artifacts)


def _stable_outcome_key(evaluation: dict[str, Any], *, observation_window: dict[str, Any]) -> str:
    identity = "|".join(
        [
            _clean_text(evaluation.get("source_run_id"), fallback="unknown_source_run"),
            _clean_text(evaluation.get("target_id"), fallback="missing_target_id"),
            _clean_text(observation_window.get("horizon_end"), fallback="missing_horizon_end"),
        ]
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return f"outcome_history:{digest}"


def _content_hash(evaluation: dict[str, Any]) -> str:
    payload = {
        "evaluation_status": evaluation.get("evaluation_status"),
        "outcome_state": evaluation.get("outcome_state"),
        "observation_window": evaluation.get("observation_window"),
        "metrics": evaluation.get("metrics"),
        "evidence": evaluation.get("evidence"),
        "uncertainty": evaluation.get("uncertainty"),
        "warnings": evaluation.get("warnings"),
        "errors": evaluation.get("errors"),
        "source_artifacts": evaluation.get("source_artifacts"),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _status(*, record_count: int, warnings: list[str], errors: list[dict[str, Any]]) -> str:
    if errors:
        return "failed"
    if warnings:
        return "warning"
    if record_count == 0:
        return "skipped"
    return "ok"


def _earliest_timestamp(left: Any, right: Any) -> str | None:
    left_text = _optional_text(left)
    right_text = _optional_text(right)
    if left_text is None:
        return right_text
    if right_text is None:
        return left_text
    return min(left_text, right_text)


def _latest_timestamp(left: Any, right: Any) -> str | None:
    left_text = _optional_text(left)
    right_text = _optional_text(right)
    if left_text is None:
        return right_text
    if right_text is None:
        return left_text
    return max(left_text, right_text)


def _clean_text(value: Any, *, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _optional_text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _object_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item]


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("updated_at must include a UTC offset.")
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str):
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("updated_at must be an ISO 8601 UTC string.") from exc
        if timestamp.tzinfo is None:
            raise ValueError("updated_at must include a UTC offset.")
        timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)
    else:
        raise ValueError("updated_at must be a datetime or ISO 8601 UTC string.")
    return timestamp.isoformat().replace("+00:00", "Z")


def _unique_sorted(values: list[str]) -> list[str]:
    return sorted(set(values))
