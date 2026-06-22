from __future__ import annotations

import json
from datetime import datetime, timezone
from json import JSONDecodeError
from typing import Any

from halpha.pipeline import RunContext
from halpha.storage import write_json


STAGE_NAME = "build_macro_calendar_context"
MACRO_CALENDAR_CONTEXT_ARTIFACT = "analysis/macro_calendar_context.json"
MACRO_CALENDAR_VIEWS_ARTIFACT = "raw/macro_calendar_views.json"
RAW_MACRO_CALENDAR_ARTIFACT = "raw/macro_calendar.json"
CONTEXT_SCHEMA_VERSION = 1
SUPPORTED_DATA_CLASSES = {"central_bank_event"}


def build_macro_calendar_context(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    macro_calendar = _macro_calendar_config(config)
    if not macro_calendar.get("enabled"):
        _record_zero_counts(run)
        return []

    created_at = _format_utc(now)
    views, views_error = _read_json(run.raw_dir / "macro_calendar_views.json")
    raw, raw_error = _read_json(run.raw_dir / "macro_calendar.json")
    records: list[dict[str, Any]] = []
    warnings = []
    errors: list[dict[str, Any]] = []
    source_artifacts = [MACRO_CALENDAR_VIEWS_ARTIFACT]

    if raw_error is None:
        source_artifacts.append(RAW_MACRO_CALENDAR_ARTIFACT)
    if views_error:
        warnings.append(views_error)
    else:
        for view in _list(views.get("views")):
            if not isinstance(view, dict) or view.get("data_class") not in SUPPORTED_DATA_CLASSES:
                continue
            view_records, duplicate_warnings = _dedupe_view_records(view)
            warnings.extend(duplicate_warnings)
            source_state = _source_state(raw if raw_error is None else {}, view)
            context_records = _context_records(
                view,
                view_records=view_records,
                source_state=source_state,
                now=created_at,
            )
            records.extend(context_records)
            for record in context_records:
                warnings.extend(_string_list(record.get("warnings")))
                errors.extend(_error_list(record.get("errors")))

    artifact = {
        "schema_version": CONTEXT_SCHEMA_VERSION,
        "artifact_type": "macro_calendar_context",
        "run_id": run.run_id,
        "created_at": created_at,
        "status": _artifact_status(records, warnings=warnings, errors=errors),
        "records": sorted(records, key=lambda record: _record_sort_key(record)),
        "counts": _counts(records, warnings=warnings, errors=errors),
        "warnings": _unique_sorted(warnings),
        "errors": errors,
        "source_artifacts": _unique_sorted(source_artifacts),
    }
    write_json(run.analysis_dir / "macro_calendar_context.json", artifact)
    _record_manifest_summary(run, artifact)
    return [MACRO_CALENDAR_CONTEXT_ARTIFACT]


def _context_records(
    view: dict[str, Any],
    *,
    view_records: list[dict[str, Any]],
    source_state: dict[str, Any],
    now: str,
) -> list[dict[str, Any]]:
    if view_records:
        return [_event_context_record(view, record, source_state=source_state, now=now) for record in view_records]
    return [_empty_window_context_record(view, source_state=source_state, now=now)]


def _event_context_record(
    view: dict[str, Any],
    record: dict[str, Any],
    *,
    source_state: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    scheduled_at = str(record.get("scheduled_at") or "")
    scheduled_time = _parse_optional_utc(scheduled_at)
    now_time = _parse_optional_utc(now)
    upcoming = scheduled_time is not None and now_time is not None and scheduled_time >= now_time
    context_type = "scheduled_catalyst" if upcoming else "recent_catalyst"
    state = "upcoming" if upcoming else "recent"
    status = _event_status(source_state)
    warnings = _unique_sorted([*_string_list(view.get("warnings")), *_string_list(record.get("warnings"))])
    errors = [*source_state["errors"], *_error_list(record.get("errors"))]
    uncertainty = _unique_sorted(
        [
            *_status_uncertainty(source_state),
            "scheduled catalyst does not imply market direction or realized impact.",
            (
                "recent scheduled catalyst does not confirm market response."
                if context_type == "recent_catalyst"
                else "upcoming scheduled catalyst is timing evidence, not a forecast."
            ),
        ]
    )
    return {
        "context_id": _context_id(
            context_type=context_type,
            source=str(view.get("source") or "unknown_source"),
            region=str(view.get("region") or "unknown_region"),
            event_name=str(record.get("event_name") or "unknown_event"),
            scheduled_at=scheduled_at or "missing",
        ),
        "context_type": context_type,
        "data_class": view.get("data_class"),
        "source": view.get("source"),
        "event_name": record.get("event_name"),
        "event_type": record.get("event_type"),
        "region": view.get("region"),
        "scheduled_at": scheduled_at or None,
        "as_of": now,
        "status": status,
        "state": state,
        "severity": _importance_severity(record.get("importance")),
        "confidence": _confidence(status),
        "time_to_event_hours": _time_to_event_hours(scheduled_at, now),
        "affected_assets": _string_list(record.get("affected_assets")),
        "importance": record.get("importance"),
        "source_availability": source_state["status"],
        "realized_impact": {
            "status": "not_evaluated",
            "reason": "macro calendar context records scheduled timing only; realized market response requires downstream evidence.",
        },
        "evidence": [
            {
                "source_artifact": MACRO_CALENDAR_VIEWS_ARTIFACT,
                "evidence_type": "scheduled_event",
                "event_name": record.get("event_name"),
                "event_type": record.get("event_type"),
                "scheduled_at": scheduled_at or None,
                "storage_ref": view.get("storage_ref"),
            }
        ],
        "uncertainty": uncertainty,
        "warnings": warnings,
        "errors": errors,
        "source_artifacts": _record_source_artifacts(view, source_state),
    }


def _empty_window_context_record(
    view: dict[str, Any],
    *,
    source_state: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    view_status = str(view.get("status") or "unknown")
    if view_status == "no_event":
        context_type = "no_event_window"
        state = "no_event"
        status = "no_event"
        severity = "low"
        uncertainty = ["no-event window does not prove macro risk is absent."]
    else:
        context_type = "source_availability"
        state = _availability_state(view_status=view_status, source_status=source_state["status"])
        status = state
        severity = "low"
        uncertainty = _status_uncertainty(source_state)
        if not uncertainty:
            uncertainty = [f"view status is {view_status}."]
    warnings = _unique_sorted([*_string_list(view.get("warnings")), *source_state["warnings"]])
    errors = source_state["errors"]
    return {
        "context_id": _context_id(
            context_type=context_type,
            source=str(view.get("source") or "unknown_source"),
            region=str(view.get("region") or "unknown_region"),
            event_name=str(view.get("data_class") or "unknown_data_class"),
            scheduled_at=str(view.get("input_window_end") or "missing"),
        ),
        "context_type": context_type,
        "data_class": view.get("data_class"),
        "source": view.get("source"),
        "event_name": None,
        "event_type": None,
        "region": view.get("region"),
        "scheduled_at": None,
        "as_of": now,
        "status": status,
        "state": state,
        "severity": severity,
        "confidence": _confidence(status),
        "time_to_event_hours": None,
        "affected_assets": [],
        "importance": None,
        "source_availability": source_state["status"],
        "realized_impact": {
            "status": "not_evaluated",
            "reason": "no scheduled macro event was available for realized-impact evaluation.",
        },
        "evidence": [
            {
                "source_artifact": MACRO_CALENDAR_VIEWS_ARTIFACT,
                "evidence_type": context_type,
                "input_window_start": view.get("input_window_start"),
                "input_window_end": view.get("input_window_end"),
                "storage_ref": view.get("storage_ref"),
            }
        ],
        "uncertainty": _unique_sorted(uncertainty),
        "warnings": warnings,
        "errors": errors,
        "source_artifacts": _record_source_artifacts(view, source_state),
    }


def _dedupe_view_records(view: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    records = []
    warnings = []
    seen = set()
    for record in _list(view.get("records")):
        if not isinstance(record, dict):
            warnings.append("macro calendar view record is not a JSON object.")
            continue
        key = _event_key(view, record)
        if key in seen:
            warnings.append(f"duplicate macro calendar context input omitted: {key}")
            continue
        seen.add(key)
        records.append(record)
    return records, _unique_sorted(warnings)


def _source_state(raw: dict[str, Any], view: dict[str, Any]) -> dict[str, Any]:
    availability = _list(raw.get("availability"))
    matched = [
        item
        for item in availability
        if isinstance(item, dict)
        and item.get("source") == view.get("source")
        and item.get("data_class") == view.get("data_class")
    ]
    statuses = {str(item.get("status")) for item in matched if isinstance(item.get("status"), str)}
    raw_errors = _error_list(raw.get("errors"))
    errors = []
    warnings = []
    uncertainty = []
    for item in matched:
        status = item.get("status")
        if status in {"partial", "failed", "unavailable", "stale", "degraded"}:
            reason = item.get("reason") or status
            uncertainty.append(f"source availability is {status}.")
            if status in {"failed", "unavailable"}:
                errors.append(
                    {
                        "source": view.get("source"),
                        "data_class": view.get("data_class"),
                        "message": str(reason),
                    }
                )
            else:
                warnings.append(f"macro calendar source availability is {status}: {reason}")
    if "failed" in statuses:
        status = "failed"
    elif "unavailable" in statuses:
        status = "unavailable"
    elif "stale" in statuses:
        status = "stale"
    elif "degraded" in statuses:
        status = "degraded"
    elif "partial" in statuses or raw_errors:
        status = "partial"
    elif "no_event" in statuses:
        status = "no_event"
    else:
        status = "succeeded"
    return {
        "status": status,
        "has_raw_source": bool(raw),
        "warnings": _unique_sorted(warnings),
        "errors": [*raw_errors, *errors],
        "uncertainty": _unique_sorted(uncertainty),
    }


def _event_status(source_state: dict[str, Any]) -> str:
    if source_state["status"] in {"partial", "failed", "unavailable", "stale", "degraded"}:
        return source_state["status"]
    return "succeeded"


def _availability_state(*, view_status: str, source_status: str) -> str:
    if source_status in {"failed", "unavailable", "stale", "degraded", "partial"}:
        return source_status
    if view_status in {"failed", "unavailable", "stale", "missing_history", "skipped"}:
        return "unavailable" if view_status in {"missing_history", "skipped"} else view_status
    return "unavailable"


def _status_uncertainty(source_state: dict[str, Any]) -> list[str]:
    status = str(source_state.get("status") or "")
    if status == "succeeded":
        return []
    if status == "no_event":
        return ["source returned no configured macro calendar events in the current window."]
    return _unique_sorted(_string_list(source_state.get("uncertainty")) or [f"source availability is {status}."])


def _record_source_artifacts(view: dict[str, Any], source_state: dict[str, Any]) -> list[str]:
    source_artifacts = [MACRO_CALENDAR_VIEWS_ARTIFACT, *_string_list(view.get("source_artifacts"))]
    if source_state["has_raw_source"]:
        source_artifacts.append(RAW_MACRO_CALENDAR_ARTIFACT)
    return _unique_sorted(source_artifacts)


def _read_json(path) -> tuple[dict[str, Any], str | None]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, f"{path.name} was not found."
    except JSONDecodeError as exc:
        return {}, f"{path.name} is not valid JSON: {exc.msg}."
    if not isinstance(loaded, dict):
        return {}, f"{path.name} must be a JSON object."
    return loaded, None


def _record_manifest_summary(run: RunContext, artifact: dict[str, Any]) -> None:
    counts = artifact["counts"]
    run.manifest["artifacts"]["macro_calendar_context"] = MACRO_CALENDAR_CONTEXT_ARTIFACT
    run.manifest["macro_calendar_context"] = {
        "status": artifact["status"],
        "artifact": MACRO_CALENDAR_CONTEXT_ARTIFACT,
        "records": counts["records"],
        "scheduled_catalyst": counts["scheduled_catalyst"],
        "recent_catalyst": counts["recent_catalyst"],
        "no_event_window": counts["no_event_window"],
        "source_availability": counts["source_availability"],
        "warnings": counts["warnings"],
        "errors": counts["errors"],
        "statuses": counts["statuses"],
    }
    manifest_counts = run.manifest.setdefault("counts", {})
    manifest_counts["macro_calendar_context_records"] = counts["records"]
    manifest_counts["macro_calendar_context_scheduled_catalyst"] = counts["scheduled_catalyst"]
    manifest_counts["macro_calendar_context_recent_catalyst"] = counts["recent_catalyst"]
    manifest_counts["macro_calendar_context_no_event_window"] = counts["no_event_window"]
    manifest_counts["macro_calendar_context_source_availability"] = counts["source_availability"]
    manifest_counts["macro_calendar_context_warnings"] = counts["warnings"]
    manifest_counts["macro_calendar_context_errors"] = counts["errors"]


def _record_zero_counts(run: RunContext) -> None:
    counts = run.manifest.setdefault("counts", {})
    counts["macro_calendar_context_records"] = 0
    counts["macro_calendar_context_scheduled_catalyst"] = 0
    counts["macro_calendar_context_recent_catalyst"] = 0
    counts["macro_calendar_context_no_event_window"] = 0
    counts["macro_calendar_context_source_availability"] = 0
    counts["macro_calendar_context_warnings"] = 0
    counts["macro_calendar_context_errors"] = 0


def _counts(
    records: list[dict[str, Any]],
    *,
    warnings: list[str],
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "records": len(records),
        "scheduled_catalyst": sum(1 for record in records if record.get("context_type") == "scheduled_catalyst"),
        "recent_catalyst": sum(1 for record in records if record.get("context_type") == "recent_catalyst"),
        "no_event_window": sum(1 for record in records if record.get("context_type") == "no_event_window"),
        "source_availability": sum(1 for record in records if record.get("context_type") == "source_availability"),
        "succeeded": sum(1 for record in records if record.get("status") == "succeeded"),
        "partial": sum(1 for record in records if record.get("status") == "partial"),
        "stale": sum(1 for record in records if record.get("status") == "stale"),
        "no_event": sum(1 for record in records if record.get("status") == "no_event"),
        "unavailable": sum(1 for record in records if record.get("status") == "unavailable"),
        "failed": sum(1 for record in records if record.get("status") == "failed"),
        "degraded": sum(1 for record in records if record.get("status") == "degraded"),
        "warnings": len(_unique_sorted(warnings)),
        "errors": len(errors),
        "statuses": _value_counts(records, "status"),
    }


def _artifact_status(
    records: list[dict[str, Any]],
    *,
    warnings: list[str],
    errors: list[dict[str, Any]],
) -> str:
    if errors:
        return "warning"
    statuses = {str(record.get("status")) for record in records}
    if statuses == {"succeeded"} and not warnings:
        return "ok"
    if not records:
        return "skipped"
    return "warning" if warnings or statuses - {"succeeded", "no_event"} else "ok"


def _value_counts(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = record.get(field)
        if isinstance(value, str) and value:
            counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _context_id(*, context_type: str, source: str, region: str, event_name: str, scheduled_at: str) -> str:
    return f"macro_calendar_context:{context_type}:{source}:{region}:{_id_part(event_name)}:{scheduled_at}"


def _event_key(view: dict[str, Any], record: dict[str, Any]) -> str:
    return "|".join(
        [
            str(view.get("source") or ""),
            str(view.get("data_class") or ""),
            str(view.get("region") or ""),
            str(record.get("event_name") or ""),
            str(record.get("scheduled_at") or ""),
        ]
    )


def _record_sort_key(record: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(record.get("scheduled_at") or ""),
        str(record.get("context_type") or ""),
        str(record.get("source") or ""),
        str(record.get("context_id") or ""),
    )


def _importance_severity(value: Any) -> str:
    importance = str(value or "").lower()
    if importance == "high":
        return "medium"
    if importance == "medium":
        return "low"
    return "low"


def _confidence(status: str) -> str:
    if status == "succeeded":
        return "medium"
    if status == "no_event":
        return "medium"
    return "low"


def _time_to_event_hours(scheduled_at: str, now: str) -> float | None:
    scheduled_time = _parse_optional_utc(scheduled_at)
    now_time = _parse_optional_utc(now)
    if scheduled_time is None or now_time is None:
        return None
    return round((scheduled_time - now_time).total_seconds() / 3600, 4)


def _id_part(value: str) -> str:
    return "_".join(part for part in value.lower().split() if part) or "unknown"


def _macro_calendar_config(config: dict[str, Any]) -> dict[str, Any]:
    macro_calendar = config.get("macro_calendar")
    return macro_calendar if isinstance(macro_calendar, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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


def _parse_optional_utc(value: str) -> datetime | None:
    if not value:
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        return None
    return timestamp.astimezone(timezone.utc).replace(microsecond=0)


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("created_at must include a UTC offset.")
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str):
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("created_at must be an ISO 8601 UTC string.") from exc
        if timestamp.tzinfo is None:
            raise ValueError("created_at must include a UTC offset.")
        timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)
    else:
        raise ValueError("created_at must be a datetime or ISO 8601 UTC string.")
    return timestamp.isoformat().replace("+00:00", "Z")
