from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from halpha.data.collection_coverage import normalize_collection_coverage_record


PLAN_SCHEMA_VERSION = 1
PLAN_STRATEGIES = {"no_work", "gap_only", "merged_gaps", "widened_window", "full_range", "blocked"}
SKIPPABLE_STATUSES = {"collected", "no_data", "warning"}
RETRY_STATUSES = {"partial", "failed", "stale", "error"}


def plan_collection_from_coverage(
    coverage_state: dict[str, Any],
    *,
    data_type: str,
    source: str,
    identity: dict[str, Any],
    requested_start: str,
    requested_end: str,
    supports_historical: bool = True,
    now: datetime | str | None = None,
    max_exact_windows: int = 3,
    merge_gap_threshold_seconds: int = 0,
    min_fetch_window_seconds: int = 0,
) -> dict[str, Any]:
    start = _format_utc(requested_start)
    end = _format_utc(requested_end)
    if _parse_utc(end) < _parse_utc(start):
        raise ValueError("requested_end must be greater than or equal to requested_start.")
    normalized_identity = _normalized_identity(identity)
    records = _matching_records(
        coverage_state,
        data_type=data_type,
        source=source,
        identity=normalized_identity,
        requested_start=start,
        requested_end=end,
    )
    skipped_ranges = _ranges_for_status(records, SKIPPABLE_STATUSES)
    retry_ranges = _retry_ranges(records)
    explicit_gap_ranges = _ranges_for_status(records, {"not_collected"})
    unknown_gap_ranges = _unknown_ranges(records, start, end)
    gap_ranges = _dedupe_ranges([*explicit_gap_ranges, *unknown_gap_ranges])
    candidate_ranges = _candidate_ranges(gap_ranges, retry_ranges)
    coverage_diagnostics = _coverage_diagnostics(records, gap_ranges, retry_ranges)
    warnings: list[str] = []
    errors: list[dict[str, Any]] = []

    if not candidate_ranges:
        strategy = "no_work"
        planned_fetch_windows: list[dict[str, Any]] = []
    elif not supports_historical:
        strategy = "blocked"
        planned_fetch_windows = []
        errors.append(
            {
                "message": "source does not support historical collection for the requested range.",
                "requested_start": start,
                "requested_end": end,
            }
        )
    else:
        strategy, planned_fetch_windows, strategy_warnings = _plan_fetch_windows(
            candidate_ranges,
            requested_start=start,
            requested_end=end,
            max_exact_windows=max_exact_windows,
            merge_gap_threshold_seconds=merge_gap_threshold_seconds,
            min_fetch_window_seconds=min_fetch_window_seconds,
        )
        warnings.extend(strategy_warnings)

    status = "blocked" if strategy == "blocked" else ("warning" if warnings else "ok")
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "artifact_type": "collection_plan",
        "created_at": _format_utc(now),
        "status": status,
        "data_type": data_type,
        "source": source,
        "identity": normalized_identity,
        "requested_start": start,
        "requested_end": end,
        "strategy": strategy,
        "skipped_ranges": skipped_ranges,
        "gap_ranges": gap_ranges,
        "retry_ranges": retry_ranges,
        "planned_fetch_windows": planned_fetch_windows,
        "coverage_diagnostics": coverage_diagnostics,
        "warnings": warnings,
        "errors": errors,
    }


def _matching_records(
    coverage_state: dict[str, Any],
    *,
    data_type: str,
    source: str,
    identity: dict[str, str],
    requested_start: str,
    requested_end: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in coverage_state.get("records", []):
        if not isinstance(item, dict):
            continue
        record = normalize_collection_coverage_record(item)
        if record["data_type"] != data_type or record["source"] != source or record["identity"] != identity:
            continue
        clipped = _clip_range(record, requested_start, requested_end)
        if clipped is not None:
            records.append({**record, **clipped})
    records.sort(key=lambda record: (record["range_start"], record["range_end"], record["status"]))
    return records


def _clip_range(record: dict[str, Any], requested_start: str, requested_end: str) -> dict[str, str] | None:
    range_start = max(record["range_start"], requested_start)
    range_end = min(record["range_end"], requested_end)
    if _parse_utc(range_end) <= _parse_utc(range_start):
        return None
    return {"range_start": range_start, "range_end": range_end}


def _ranges_for_status(records: list[dict[str, Any]], statuses: set[str]) -> list[dict[str, Any]]:
    return [
        {
            "range_start": record["range_start"],
            "range_end": record["range_end"],
            "status": record["status"],
            "source_artifacts": record.get("source_artifacts", []),
            "warnings": record.get("warnings", []),
            "errors": record.get("errors", []),
        }
        for record in records
        if record["status"] in statuses
    ]


def _retry_ranges(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    retry = []
    for record in records:
        if record["status"] not in RETRY_STATUSES:
            continue
        retry.append(
            {
                "range_start": record["range_start"],
                "range_end": record["range_end"],
                "status": record["status"],
                "reason": f"{record['status']}_coverage",
                "source_artifacts": record.get("source_artifacts", []),
                "warnings": record.get("warnings", []),
                "errors": record.get("errors", []),
            }
        )
    return retry


def _candidate_ranges(gap_ranges: list[dict[str, Any]], retry_ranges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = []
    for range_record in gap_ranges:
        candidates.append(
            {
                "range_start": range_record["range_start"],
                "range_end": range_record["range_end"],
                "reason": "missing_coverage",
                "source_status": range_record.get("status", "unknown"),
            }
        )
    for range_record in retry_ranges:
        candidates.append(
            {
                "range_start": range_record["range_start"],
                "range_end": range_record["range_end"],
                "reason": range_record["reason"],
                "source_status": range_record["status"],
                "warnings": range_record.get("warnings", []),
                "errors": range_record.get("errors", []),
            }
        )
    return _dedupe_ranges(candidates)


def _plan_fetch_windows(
    candidates: list[dict[str, Any]],
    *,
    requested_start: str,
    requested_end: str,
    max_exact_windows: int,
    merge_gap_threshold_seconds: int,
    min_fetch_window_seconds: int,
) -> tuple[str, list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    exact_windows = [_fetch_window(candidate) for candidate in candidates]
    widened = False
    if min_fetch_window_seconds > 0:
        widened_windows = [
            _widen_window(window, requested_start, requested_end, min_fetch_window_seconds)
            for window in exact_windows
        ]
        widened = widened_windows != exact_windows
        exact_windows = widened_windows

    merged_windows = _merge_close_windows(exact_windows, merge_gap_threshold_seconds)
    if len(candidates) > max_exact_windows and len(merged_windows) > max_exact_windows:
        warnings.append("fragmented collection gaps exceed max exact windows; planning full requested range.")
        return (
            "full_range",
            [_planned_window(requested_start, requested_end, reason="full_range_more_efficient")],
            warnings,
        )
    if len(merged_windows) < len(exact_windows):
        return "merged_gaps", merged_windows, warnings
    if widened:
        return "widened_window", exact_windows, warnings
    return "gap_only", exact_windows, warnings


def _fetch_window(candidate: dict[str, Any]) -> dict[str, Any]:
    return _planned_window(candidate["range_start"], candidate["range_end"], reason=candidate.get("reason"))


def _planned_window(start: str, end: str, *, reason: str | None) -> dict[str, Any]:
    return {
        "range_start": start,
        "range_end": end,
        "reason": reason or "missing_coverage",
    }


def _widen_window(
    window: dict[str, Any],
    requested_start: str,
    requested_end: str,
    min_fetch_window_seconds: int,
) -> dict[str, Any]:
    start = _parse_utc(window["range_start"])
    end = _parse_utc(window["range_end"])
    duration = (end - start).total_seconds()
    if duration >= min_fetch_window_seconds:
        return window
    missing = min_fetch_window_seconds - duration
    widened_start = max(_parse_utc(requested_start), start - timedelta(seconds=missing / 2))
    widened_end = min(_parse_utc(requested_end), widened_start + timedelta(seconds=min_fetch_window_seconds))
    if widened_end - widened_start < timedelta(seconds=min_fetch_window_seconds):
        widened_start = max(_parse_utc(requested_start), widened_end - timedelta(seconds=min_fetch_window_seconds))
    return {
        **window,
        "range_start": _iso(widened_start),
        "range_end": _iso(widened_end),
        "reason": "widened_window_more_efficient",
    }


def _merge_close_windows(windows: list[dict[str, Any]], threshold_seconds: int) -> list[dict[str, Any]]:
    if not windows:
        return []
    threshold = max(0, threshold_seconds)
    ordered = sorted(windows, key=lambda window: (window["range_start"], window["range_end"], window.get("reason", "")))
    merged = [ordered[0]]
    for window in ordered[1:]:
        previous = merged[-1]
        gap = (_parse_utc(window["range_start"]) - _parse_utc(previous["range_end"])).total_seconds()
        if gap <= threshold:
            previous["range_end"] = max(previous["range_end"], window["range_end"])
            previous["reason"] = "merged_gaps_more_efficient"
        else:
            merged.append(window)
    return merged


def _unknown_ranges(records: list[dict[str, Any]], requested_start: str, requested_end: str) -> list[dict[str, Any]]:
    cursor = _parse_utc(requested_start)
    requested_end_dt = _parse_utc(requested_end)
    known = sorted(records, key=lambda record: (record["range_start"], record["range_end"]))
    unknown = []
    for record in known:
        range_start = _parse_utc(record["range_start"])
        range_end = _parse_utc(record["range_end"])
        if range_end <= cursor:
            continue
        if range_start > cursor:
            unknown.append(
                {
                    "range_start": _iso(cursor),
                    "range_end": _iso(range_start),
                    "status": "unknown",
                }
            )
        cursor = max(cursor, range_end)
        if cursor >= requested_end_dt:
            break
    if cursor < requested_end_dt:
        unknown.append({"range_start": _iso(cursor), "range_end": _iso(requested_end_dt), "status": "unknown"})
    return unknown


def _dedupe_ranges(ranges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in ranges:
        key = (str(item.get("range_start")), str(item.get("range_end")), str(item.get("reason") or item.get("status") or ""))
        deduped[key] = item
    return [deduped[key] for key in sorted(deduped)]


def _coverage_diagnostics(
    records: list[dict[str, Any]],
    gap_ranges: list[dict[str, Any]],
    retry_ranges: list[dict[str, Any]],
) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    for record in records:
        status = record["status"]
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "coverage_records": len(records),
        "status_counts": {key: status_counts[key] for key in sorted(status_counts)},
        "gap_ranges": len(gap_ranges),
        "retry_ranges": len(retry_ranges),
    }


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("plan timestamps must include a UTC offset.")
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str):
        timestamp = _parse_utc(value)
    else:
        raise ValueError("plan timestamps must be datetimes or ISO 8601 strings.")
    return _iso(timestamp)


def _parse_utc(value: str) -> datetime:
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"plan timestamp is not valid ISO 8601: {value}") from exc
    if timestamp.tzinfo is None:
        raise ValueError("plan timestamps must include a UTC offset.")
    return timestamp.astimezone(timezone.utc).replace(microsecond=0)


def _iso(timestamp: datetime) -> str:
    return timestamp.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalized_identity(identity: dict[str, Any]) -> dict[str, str]:
    return {
        str(key): str(identity[key])
        for key in sorted(identity)
        if identity[key] is not None and str(identity[key]) != ""
    }
