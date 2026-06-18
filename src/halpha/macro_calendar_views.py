from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from json import JSONDecodeError
from typing import Any

from .macro_calendar_history import (
    MACRO_CALENDAR_HISTORY_STATE_ARTIFACT,
    macro_calendar_group_path,
    read_macro_calendar_history_records,
)
from .pipeline import PipelineError, RunContext
from .storage import display_path, write_json


STAGE_NAME = "build_macro_calendar_views"
MACRO_CALENDAR_VIEWS_ARTIFACT = "raw/macro_calendar_views.json"
VIEW_SCHEMA_VERSION = 1
MAX_VIEW_RECORDS = 50
VIEW_INCLUDED_COLUMNS = (
    "scheduled_at",
    "event_name",
    "event_type",
    "importance",
    "affected_assets",
    "endpoint",
    "warnings",
    "errors",
)
SUPPORTED_VIEW_DATA_CLASSES = {"central_bank_event"}


def build_macro_calendar_views(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    macro_calendar = _macro_calendar_config(config)
    if not macro_calendar.get("enabled"):
        _record_zero_counts(run)
        return []

    source = str(macro_calendar.get("source") or "unknown_source")
    data_classes = _string_list(macro_calendar.get("data_classes"))
    regions = _string_list(macro_calendar.get("regions"))
    lookback_days = _positive_int(macro_calendar.get("lookback_days"), default=7)
    lookahead_days = _positive_int(macro_calendar.get("lookahead_days"), default=45)
    raw = _read_optional_raw_artifact(run.raw_dir / "macro_calendar.json")
    window_start, window_end = _view_window(raw, lookback_days=lookback_days, lookahead_days=lookahead_days, now=now)
    availability = _availability_by_key(raw)
    history_records = read_macro_calendar_history_records(run.config_path)

    views = []
    for data_class in data_classes:
        if data_class not in SUPPORTED_VIEW_DATA_CLASSES:
            for region in regions or [None]:
                views.append(
                    _skipped_view(
                        source=source,
                        data_class=data_class,
                        region=region,
                        reason=f"{data_class} macro calendar views are not implemented.",
                    )
                )
            continue
        for region in regions:
            views.append(
                _view_record(
                    records=history_records,
                    source=source,
                    data_class=data_class,
                    region=region,
                    lookback_days=lookback_days,
                    lookahead_days=lookahead_days,
                    window_start=window_start,
                    window_end=window_end,
                    availability_status=availability.get((source, data_class)),
                    config_base=run.config_path.parent,
                )
            )

    artifact = {
        "schema_version": VIEW_SCHEMA_VERSION,
        "artifact_type": "macro_calendar_views",
        "created_at": _format_utc(now),
        "input_window_start": window_start,
        "input_window_end": window_end,
        "source_artifacts": [_state_artifact(run)],
        "views": views,
        "warnings": _artifact_warnings(views),
        "errors": _artifact_errors(views),
    }
    write_json(run.raw_dir / "macro_calendar_views.json", artifact)
    run.manifest["artifacts"]["macro_calendar_views"] = MACRO_CALENDAR_VIEWS_ARTIFACT
    _record_manifest_summary(run, views, artifact)
    return [MACRO_CALENDAR_VIEWS_ARTIFACT]


def load_macro_calendar_view_records(
    view: dict[str, Any],
    *,
    config_path: Any,
) -> list[dict[str, Any]]:
    start = view.get("input_window_start")
    end = view.get("input_window_end")
    if not start or not end:
        return []
    records = [
        record
        for record in read_macro_calendar_history_records(config_path)
        if record.get("source") == view.get("source")
        and record.get("data_class") == view.get("data_class")
        and record.get("region") == view.get("region")
        and start <= str(record.get("scheduled_at") or "") <= end
    ]
    columns = tuple(view.get("included_columns") or VIEW_INCLUDED_COLUMNS)
    return [
        {column: record.get(column) for column in columns}
        for record in sorted(records, key=lambda item: item["scheduled_at"])[:MAX_VIEW_RECORDS]
    ]


def _view_record(
    *,
    records: list[dict[str, Any]],
    source: str,
    data_class: str,
    region: str,
    lookback_days: int,
    lookahead_days: int,
    window_start: str,
    window_end: str,
    availability_status: dict[str, Any] | None,
    config_base: Any,
) -> dict[str, Any]:
    group_records = [
        record
        for record in records
        if record.get("source") == source
        and record.get("data_class") == data_class
        and record.get("region") == region
    ]
    group_records = sorted(group_records, key=lambda record: record["scheduled_at"])
    window = [record for record in group_records if window_start <= str(record.get("scheduled_at") or "") <= window_end]
    selected = window[:MAX_VIEW_RECORDS]
    latest_group = group_records[-1]["scheduled_at"] if group_records else None
    latest_window = window[-1]["scheduled_at"] if window else None
    status, warnings, errors = _view_status(
        source=source,
        data_class=data_class,
        region=region,
        window=window,
        group_records=group_records,
        window_start=window_start,
        availability_status=availability_status,
    )
    omitted = max(len(window) - len(selected), 0)
    if omitted:
        warnings.append(
            f"{source} {data_class} {region} macro calendar view omitted {omitted} records over budget {MAX_VIEW_RECORDS}."
        )
        if status == "succeeded":
            status = "bounded"

    return {
        "view_id": _view_id(source, data_class, region, latest_window or latest_group),
        "data_class": data_class,
        "source": source,
        "region": region,
        "lookback_days": lookback_days,
        "lookahead_days": lookahead_days,
        "input_window_start": window_start,
        "input_window_end": window_end,
        "latest_observation_time": latest_window or latest_group,
        "event_count": len(window),
        "included_record_count": len(selected),
        "omitted_record_count": omitted,
        "status": status,
        "storage_ref": _storage_ref(source, data_class, region, config_base),
        "included_columns": list(VIEW_INCLUDED_COLUMNS),
        "records": [_selected_record(record) for record in selected],
        "warnings": _unique_sorted(warnings),
        "errors": errors,
        "source_artifacts": [_state_artifact_from_base(config_base)],
    }


def _view_status(
    *,
    source: str,
    data_class: str,
    region: str,
    window: list[dict[str, Any]],
    group_records: list[dict[str, Any]],
    window_start: str,
    availability_status: dict[str, Any] | None,
) -> tuple[str, list[str], list[dict[str, Any]]]:
    warnings: list[str] = []
    errors: list[dict[str, Any]] = []
    raw_status = str(availability_status.get("status") or "") if isinstance(availability_status, dict) else ""
    reason = str(availability_status.get("reason") or "") if isinstance(availability_status, dict) else ""
    if window:
        return "succeeded", warnings, errors
    if raw_status in {"failed", "unavailable"}:
        errors.append(
            {
                "source": source,
                "data_class": data_class,
                "region": region,
                "message": reason or f"macro calendar availability status is {raw_status}.",
            }
        )
        return raw_status, warnings, errors
    if raw_status == "stale" or (group_records and str(group_records[-1].get("scheduled_at") or "") < window_start):
        warnings.append(f"{source} {data_class} {region} macro calendar history is stale for current window.")
        return "stale", warnings, errors
    if raw_status == "no_event":
        return "no_event", warnings, errors
    warnings.append(f"{source} {data_class} {region} has no macro calendar history.")
    return "missing_history", warnings, errors


def _selected_record(record: dict[str, Any]) -> dict[str, Any]:
    return {column: record.get(column) for column in VIEW_INCLUDED_COLUMNS}


def _skipped_view(*, source: str, data_class: str, region: str | None, reason: str) -> dict[str, Any]:
    return {
        "view_id": f"macro_calendar_view:{data_class}:{source}:{region or 'unknown_region'}:skipped",
        "data_class": data_class,
        "source": source,
        "region": region,
        "lookback_days": 0,
        "lookahead_days": 0,
        "input_window_start": None,
        "input_window_end": None,
        "latest_observation_time": None,
        "event_count": 0,
        "included_record_count": 0,
        "omitted_record_count": 0,
        "status": "skipped",
        "storage_ref": None,
        "included_columns": [],
        "records": [],
        "warnings": [reason],
        "errors": [],
        "source_artifacts": [],
    }


def _view_window(
    raw: dict[str, Any] | None,
    *,
    lookback_days: int,
    lookahead_days: int,
    now: datetime | str | None,
) -> tuple[str, str]:
    window = raw.get("window") if isinstance(raw, dict) else None
    if isinstance(window, dict) and isinstance(window.get("lookback_start"), str) and isinstance(window.get("lookahead_end"), str):
        return window["lookback_start"], window["lookahead_end"]
    timestamp = _parse_utc(_format_utc(now))
    return (
        _format_utc(timestamp - timedelta(days=lookback_days)),
        _format_utc(timestamp + timedelta(days=lookahead_days)),
    )


def _availability_by_key(raw: dict[str, Any] | None) -> dict[tuple[str, str], dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    availability = {}
    for item in _list(raw.get("availability")):
        if not isinstance(item, dict):
            continue
        source = item.get("source")
        data_class = item.get("data_class")
        if isinstance(source, str) and isinstance(data_class, str):
            availability[(source, data_class)] = item
    return availability


def _read_optional_raw_artifact(path) -> dict[str, Any] | None:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except JSONDecodeError as exc:
        raise PipelineError(
            "raw/macro_calendar.json is not valid JSON: " f"{exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    if not isinstance(loaded, dict):
        raise PipelineError("raw/macro_calendar.json must be a JSON object.", stage=STAGE_NAME, exit_code=3)
    return loaded


def _view_id(source: str, data_class: str, region: str, latest: str | None) -> str:
    suffix = latest or "missing"
    return f"macro_calendar_view:{data_class}:{source}:{region}:{suffix}"


def _storage_ref(source: str, data_class: str, region: str, config_base: Any) -> str:
    return display_path(
        macro_calendar_group_path(
            config_base / "config.yaml",
            source=source,
            data_class=data_class,
            region=region,
        ),
        base=config_base,
    )


def _record_manifest_summary(run: RunContext, views: list[dict[str, Any]], artifact: dict[str, Any]) -> None:
    counts = run.manifest.setdefault("counts", {})
    counts["macro_calendar_views"] = len(views)
    counts["macro_calendar_view_events"] = sum(_int(view.get("event_count")) for view in views)
    counts["macro_calendar_view_records"] = sum(_int(view.get("included_record_count")) for view in views)
    counts["macro_calendar_views_stale"] = sum(1 for view in views if view.get("status") == "stale")
    counts["macro_calendar_views_no_event"] = sum(1 for view in views if view.get("status") == "no_event")
    counts["macro_calendar_views_errors"] = sum(len(_list(view.get("errors"))) for view in views)
    run.manifest["macro_calendar_views"] = {
        "status": _artifact_status(views),
        "artifact": MACRO_CALENDAR_VIEWS_ARTIFACT,
        "views": len(views),
        "events": counts["macro_calendar_view_events"],
        "records": counts["macro_calendar_view_records"],
        "storage_refs": sorted(
            str(view["storage_ref"])
            for view in views
            if isinstance(view.get("storage_ref"), str) and view.get("storage_ref")
        ),
        "warnings": len(artifact["warnings"]),
        "errors": len(artifact["errors"]),
    }


def _record_zero_counts(run: RunContext) -> None:
    counts = run.manifest.setdefault("counts", {})
    counts["macro_calendar_views"] = 0
    counts["macro_calendar_view_events"] = 0
    counts["macro_calendar_view_records"] = 0
    counts["macro_calendar_views_stale"] = 0
    counts["macro_calendar_views_no_event"] = 0
    counts["macro_calendar_views_errors"] = 0


def _artifact_status(views: list[dict[str, Any]]) -> str:
    if any(view.get("errors") for view in views):
        return "warning"
    if any(view.get("status") in {"bounded", "missing_history", "stale", "skipped"} for view in views):
        return "warning"
    return "ok" if views else "skipped"


def _artifact_warnings(views: list[dict[str, Any]]) -> list[str]:
    warnings = []
    for view in views:
        warnings.extend(_string_list(view.get("warnings")))
    return _unique_sorted(warnings)


def _artifact_errors(views: list[dict[str, Any]]) -> list[dict[str, Any]]:
    errors = []
    for view in views:
        errors.extend(_list(view.get("errors")))
    return [error for error in errors if isinstance(error, dict)]


def _state_artifact(run: RunContext) -> str:
    artifact = run.manifest.get("artifacts", {}).get("macro_calendar_state")
    return str(artifact or MACRO_CALENDAR_HISTORY_STATE_ARTIFACT)


def _state_artifact_from_base(config_base: Any) -> str:
    return display_path(config_base / MACRO_CALENDAR_HISTORY_STATE_ARTIFACT, base=config_base)


def _macro_calendar_config(config: dict[str, Any]) -> dict[str, Any]:
    macro_calendar = config.get("macro_calendar")
    return macro_calendar if isinstance(macro_calendar, dict) else {}


def _positive_int(value: Any, *, default: int) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return default


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value or [] if isinstance(item, str) and item.strip()]


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    return 0


def _unique_sorted(values: list[str]) -> list[str]:
    return sorted(set(values))


def _parse_utc(value: str) -> datetime:
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PipelineError("timestamp must be an ISO 8601 UTC string.", stage=STAGE_NAME, exit_code=3) from exc
    if timestamp.tzinfo is None:
        raise PipelineError("timestamp must include a UTC offset.", stage=STAGE_NAME, exit_code=3)
    return timestamp.astimezone(timezone.utc).replace(microsecond=0)


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise PipelineError("created_at must include a UTC offset.", stage=STAGE_NAME, exit_code=3)
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str):
        timestamp = _parse_utc(value)
    else:
        raise PipelineError("created_at must be a datetime or ISO 8601 UTC string.", stage=STAGE_NAME, exit_code=3)
    return timestamp.isoformat().replace("+00:00", "Z")
