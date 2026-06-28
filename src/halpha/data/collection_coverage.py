from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from halpha.storage import resolve_runtime_path, write_json


COVERAGE_SCHEMA_VERSION = 1
COVERAGE_STATE_ARTIFACT = "data/research/metadata/collection_coverage_state.json"
COVERAGE_STATUSES = {
    "collected",
    "partial",
    "failed",
    "not_collected",
    "no_data",
    "stale",
    "warning",
    "error",
}
MERGEABLE_STATUSES = {"collected", "not_collected", "no_data", "stale", "warning"}
STATUS_PRIORITY = {
    "collected": 80,
    "no_data": 70,
    "warning": 60,
    "stale": 50,
    "partial": 40,
    "failed": 30,
    "not_collected": 20,
    "error": 10,
}


def collection_coverage_path(config_path: Path) -> Path:
    return resolve_runtime_path(COVERAGE_STATE_ARTIFACT, config_path=config_path)


def read_collection_coverage_state(config_path: Path) -> dict[str, Any]:
    path = collection_coverage_path(config_path)
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return empty_collection_coverage_state(status="skipped", warnings=["collection coverage state was not found."])
    except json.JSONDecodeError as exc:
        return empty_collection_coverage_state(
            status="error",
            errors=[{"message": f"collection coverage state is not valid JSON: {exc}"}],
        )
    if not isinstance(loaded, dict):
        return empty_collection_coverage_state(
            status="error",
            errors=[{"message": "collection coverage state must be a JSON object."}],
        )
    return normalize_collection_coverage_state(loaded)


def write_collection_coverage_state(
    config_path: Path,
    records: list[dict[str, Any]],
    *,
    now: datetime | str | None = None,
    source_artifacts: list[str] | None = None,
) -> dict[str, Any]:
    state = build_collection_coverage_state(
        records,
        now=now,
        source_artifacts=source_artifacts,
    )
    write_json(collection_coverage_path(config_path), state)
    return state


def build_collection_coverage_state(
    records: list[dict[str, Any]],
    *,
    now: datetime | str | None = None,
    source_artifacts: list[str] | None = None,
) -> dict[str, Any]:
    normalized = merge_collection_coverage_records(records)
    warnings: list[str] = []
    errors: list[dict[str, Any]] = []
    for record in normalized:
        warnings.extend(_string_list(record.get("warnings")))
        errors.extend(_error_list(record.get("errors")))
    status = "failed" if errors else ("warning" if warnings else "ok")
    return {
        "schema_version": COVERAGE_SCHEMA_VERSION,
        "artifact_type": "collection_coverage_state",
        "updated_at": _format_utc(now),
        "status": status,
        "records": normalized,
        "counts": {
            "records": len(normalized),
            "statuses": _status_counts(normalized),
            "warnings": len(warnings),
            "errors": len(errors),
        },
        "source_artifacts": _unique_sorted(source_artifacts or []),
        "warnings": _unique_sorted(warnings),
        "errors": errors,
    }


def empty_collection_coverage_state(
    *,
    status: str = "skipped",
    warnings: list[str] | None = None,
    errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": COVERAGE_SCHEMA_VERSION,
        "artifact_type": "collection_coverage_state",
        "updated_at": None,
        "status": status,
        "records": [],
        "counts": {
            "records": 0,
            "statuses": {},
            "warnings": len(warnings or []),
            "errors": len(errors or []),
        },
        "source_artifacts": [],
        "warnings": warnings or [],
        "errors": errors or [],
    }


def normalize_collection_coverage_state(state: dict[str, Any]) -> dict[str, Any]:
    records = state.get("records")
    if not isinstance(records, list):
        records = []
    normalized_records = []
    errors = _error_list(state.get("errors"))
    warnings = _string_list(state.get("warnings"))
    for record in records:
        if not isinstance(record, dict):
            errors.append({"message": "coverage record must be a JSON object."})
            continue
        try:
            normalized_records.append(normalize_collection_coverage_record(record))
        except ValueError as exc:
            errors.append({"message": str(exc)})
    status = str(state.get("status") or "")
    if status not in {"ok", "warning", "degraded", "skipped", "failed", "error"}:
        status = "failed" if errors else ("warning" if warnings else "ok")
    return {
        "schema_version": state.get("schema_version") or COVERAGE_SCHEMA_VERSION,
        "artifact_type": state.get("artifact_type") or "collection_coverage_state",
        "updated_at": state.get("updated_at"),
        "status": status,
        "records": normalized_records,
        "counts": {
            "records": len(normalized_records),
            "statuses": _status_counts(normalized_records),
            "warnings": len(warnings),
            "errors": len(errors),
        },
        "source_artifacts": _unique_sorted(_string_list(state.get("source_artifacts"))),
        "warnings": _unique_sorted(warnings),
        "errors": errors,
    }


def normalize_collection_coverage_record(record: dict[str, Any]) -> dict[str, Any]:
    data_type = _required_text(record, "data_type")
    source = _required_text(record, "source")
    range_start = _format_utc(_required_text(record, "range_start"))
    range_end = _format_utc(_required_text(record, "range_end"))
    if _parse_utc(range_end) < _parse_utc(range_start):
        raise ValueError("coverage range_end must be greater than or equal to range_start.")
    status = _required_text(record, "status")
    if status not in COVERAGE_STATUSES:
        raise ValueError(f"unsupported collection coverage status: {status}")
    identity = record.get("identity")
    if identity is None:
        identity = {}
    if not isinstance(identity, dict):
        raise ValueError("collection coverage identity must be an object.")
    latest_attempt_at = _optional_time(record.get("latest_attempt_at"))
    latest_success_at = _optional_time(record.get("latest_success_at"))
    updated_at = _optional_time(record.get("updated_at")) or latest_attempt_at or latest_success_at
    return {
        "data_type": data_type,
        "source": source,
        "identity": _normalized_identity(identity),
        "range_start": range_start,
        "range_end": range_end,
        "status": status,
        "record_count": _non_negative_int(record.get("record_count")),
        "attempt_count": _non_negative_int(record.get("attempt_count"), default=1),
        "latest_attempt_at": latest_attempt_at,
        "latest_success_at": latest_success_at,
        "updated_at": updated_at,
        "coverage_method": str(record.get("coverage_method") or "explicit"),
        "source_artifacts": _unique_sorted(_string_list(record.get("source_artifacts"))),
        "warnings": _unique_sorted(_string_list(record.get("warnings"))),
        "errors": _error_list(record.get("errors")),
    }


def merge_collection_coverage_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = [normalize_collection_coverage_record(record) for record in records]
    normalized.sort(key=_record_sort_key)
    merged: list[dict[str, Any]] = []
    for record in normalized:
        if merged and _same_coverage_range(merged[-1], record):
            merged[-1] = _merge_exact_range(merged[-1], record)
        elif merged and _can_merge(merged[-1], record):
            merged[-1] = _merge_pair(merged[-1], record)
        else:
            merged.append(record)
    return merged


def summarize_collection_coverage(
    state: dict[str, Any],
    *,
    data_type: str | None = None,
    source: str | None = None,
    identity: dict[str, Any] | None = None,
    requested_start: str | None = None,
    requested_end: str | None = None,
) -> dict[str, Any]:
    wanted_identity = _normalized_identity(identity or {}) if identity is not None else None
    records = [
        normalize_collection_coverage_record(record)
        for record in state.get("records", [])
        if isinstance(record, dict)
    ]
    filtered = [
        record
        for record in records
        if (data_type is None or record["data_type"] == data_type)
        and (source is None or record["source"] == source)
        and (wanted_identity is None or record["identity"] == wanted_identity)
    ]
    starts = [record["range_start"] for record in filtered]
    ends = [record["range_end"] for record in filtered]
    summary = {
        "record_count": len(filtered),
        "status_counts": _status_counts(filtered),
        "range_start": min(starts) if starts else None,
        "range_end": max(ends) if ends else None,
        "partial_ranges": _ranges_for_status(filtered, "partial"),
        "failed_ranges": _ranges_for_status(filtered, "failed"),
        "not_collected_ranges": _ranges_for_status(filtered, "not_collected"),
        "unknown_ranges": [],
    }
    if requested_start and requested_end:
        summary["unknown_ranges"] = _unknown_ranges(filtered, requested_start, requested_end)
    return summary


def _can_merge(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left["status"] not in MERGEABLE_STATUSES:
        return False
    if left["status"] != right["status"]:
        return False
    if left["data_type"] != right["data_type"] or left["source"] != right["source"]:
        return False
    if left["identity"] != right["identity"] or left["coverage_method"] != right["coverage_method"]:
        return False
    return _parse_utc(right["range_start"]) <= _parse_utc(left["range_end"])


def _same_coverage_range(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        left["data_type"] == right["data_type"]
        and left["source"] == right["source"]
        and left["identity"] == right["identity"]
        and left["coverage_method"] == right["coverage_method"]
        and left["range_start"] == right["range_start"]
        and left["range_end"] == right["range_end"]
    )


def _merge_exact_range(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    selected, other = _preferred_exact_range_record(left, right)
    same_status = selected["status"] == other["status"]
    return {
        **selected,
        "attempt_count": _non_negative_int(left.get("attempt_count")) + _non_negative_int(right.get("attempt_count")),
        "latest_attempt_at": _latest_time(left.get("latest_attempt_at"), right.get("latest_attempt_at")),
        "latest_success_at": _latest_time(left.get("latest_success_at"), right.get("latest_success_at")),
        "updated_at": _latest_time(left.get("updated_at"), right.get("updated_at")),
        "source_artifacts": _unique_sorted(
            [*_string_list(left.get("source_artifacts")), *_string_list(right.get("source_artifacts"))]
        ),
        "warnings": _unique_sorted([*_string_list(left.get("warnings")), *_string_list(right.get("warnings"))])
        if same_status
        else _string_list(selected.get("warnings")),
        "errors": [*_error_list(left.get("errors")), *_error_list(right.get("errors"))]
        if same_status
        else _error_list(selected.get("errors")),
    }


def _preferred_exact_range_record(left: dict[str, Any], right: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    left_key = (_status_priority(left), _record_updated_at(left))
    right_key = (_status_priority(right), _record_updated_at(right))
    if right_key > left_key:
        return right, left
    return left, right


def _status_priority(record: dict[str, Any]) -> int:
    return STATUS_PRIORITY.get(str(record.get("status") or ""), 0)


def _record_updated_at(record: dict[str, Any]) -> str:
    return str(record.get("updated_at") or record.get("latest_attempt_at") or record.get("latest_success_at") or "")


def _merge_pair(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    return {
        **left,
        "range_end": max(left["range_end"], right["range_end"]),
        "record_count": _merged_record_count(left, right),
        "attempt_count": _non_negative_int(left.get("attempt_count")) + _non_negative_int(right.get("attempt_count")),
        "latest_attempt_at": _latest_time(left.get("latest_attempt_at"), right.get("latest_attempt_at")),
        "latest_success_at": _latest_time(left.get("latest_success_at"), right.get("latest_success_at")),
        "updated_at": _latest_time(left.get("updated_at"), right.get("updated_at")),
        "source_artifacts": _unique_sorted(
            [*_string_list(left.get("source_artifacts")), *_string_list(right.get("source_artifacts"))]
        ),
        "warnings": _unique_sorted([*_string_list(left.get("warnings")), *_string_list(right.get("warnings"))]),
        "errors": [*_error_list(left.get("errors")), *_error_list(right.get("errors"))],
    }


def _merged_record_count(left: dict[str, Any], right: dict[str, Any]) -> int:
    left_count = _non_negative_int(left.get("record_count"))
    right_count = _non_negative_int(right.get("record_count"))
    if _parse_utc(right["range_start"]) >= _parse_utc(left["range_end"]):
        return left_count + right_count
    return max(left_count, right_count)


def _unknown_ranges(records: list[dict[str, Any]], requested_start: str, requested_end: str) -> list[dict[str, str]]:
    start = _format_utc(requested_start)
    end = _format_utc(requested_end)
    cursor = _parse_utc(start)
    requested_end_dt = _parse_utc(end)
    covered = sorted(records, key=lambda record: record["range_start"])
    unknown = []
    for record in covered:
        record_start = _parse_utc(record["range_start"])
        record_end = _parse_utc(record["range_end"])
        if record_end <= cursor:
            continue
        if record_start > cursor:
            unknown.append({"range_start": _iso(cursor), "range_end": _iso(record_start)})
        if record_end > cursor:
            cursor = record_end
        if cursor >= requested_end_dt:
            break
    if cursor < requested_end_dt:
        unknown.append({"range_start": _iso(cursor), "range_end": _iso(requested_end_dt)})
    return unknown


def _ranges_for_status(records: list[dict[str, Any]], status: str) -> list[dict[str, str]]:
    return [
        {"range_start": record["range_start"], "range_end": record["range_end"]}
        for record in records
        if record["status"] == status
    ]


def _record_sort_key(record: dict[str, Any]) -> tuple[Any, ...]:
    return (
        record["data_type"],
        record["source"],
        json.dumps(record["identity"], sort_keys=True, separators=(",", ":")),
        record["coverage_method"],
        record["range_start"],
        record["range_end"],
        record["status"],
    )


def _status_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        status = str(record.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return {key: counts[key] for key in sorted(counts)}


def _required_text(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"coverage record {key} must be a non-empty string.")
    return value.strip()


def _optional_time(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    return _format_utc(value)


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("coverage timestamps must include a UTC offset.")
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str):
        timestamp = _parse_utc(value)
    else:
        raise ValueError("coverage timestamps must be datetimes or ISO 8601 strings.")
    return _iso(timestamp)


def _parse_utc(value: str) -> datetime:
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"coverage timestamp is not valid ISO 8601: {value}") from exc
    if timestamp.tzinfo is None:
        raise ValueError("coverage timestamps must include a UTC offset.")
    return timestamp.astimezone(timezone.utc).replace(microsecond=0)


def _iso(timestamp: datetime) -> str:
    return timestamp.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _latest_time(left: Any, right: Any) -> str | None:
    values = [value for value in (_optional_time(left), _optional_time(right)) if value]
    return max(values) if values else None


def _normalized_identity(identity: dict[str, Any]) -> dict[str, str]:
    return {
        str(key): str(identity[key])
        for key in sorted(identity)
        if identity[key] is not None and str(identity[key]) != ""
    }


def _non_negative_int(value: Any, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int) and value >= 0:
        return value
    return default


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item]


def _error_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _unique_sorted(values: list[str]) -> list[str]:
    return sorted(set(values))
