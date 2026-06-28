from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from halpha.dashboard.data_stores import dashboard_data_stores
from halpha.data.collection_coverage import read_collection_coverage_state, summarize_collection_coverage
from halpha.data.collection_planner import plan_collection_from_coverage
from halpha.data.data_export import DataExportError, export_data
from halpha.data.event_like_query import EventLikeQueryError, query_event_like_records
from halpha.market.ohlcv_query import OHLCVQueryError, query_ohlcv_records
from halpha.macro.macro_calendar_history import read_macro_calendar_history_records
from halpha.market.derivatives_history import read_derivatives_history_records
from halpha.onchain.onchain_flow_history import read_onchain_flow_history_records
from halpha.runtime.command_jobs import CommandJobManager
from halpha.storage import resolve_runtime_path
from halpha.text.text_event_history import read_text_event_history_records


DATA_VIEWER_SCHEMA_VERSION = 1
SUPPORTED_DATA_TYPES = ("ohlcv", "text_event", "macro_calendar", "onchain_flow", "derivatives_market")
COLLECTABLE_DATA_TYPES = set(SUPPORTED_DATA_TYPES)
EVENT_LIKE_DATA_TYPES = {"text_event", "macro_calendar", "onchain_flow", "derivatives_market"}
STORE_BY_DATA_TYPE = {
    "ohlcv": "ohlcv_history",
    "text_event": "text_event_history",
    "derivatives_market": "derivatives_market_history",
    "macro_calendar": "macro_calendar_history",
    "onchain_flow": "onchain_flow_history",
}
EXPORT_FORMATS = {
    "ohlcv": ("csv", "parquet"),
    "text_event": ("csv", "json"),
    "macro_calendar": ("csv", "json"),
    "onchain_flow": ("csv", "json"),
    "derivatives_market": ("csv", "json"),
}
MAX_PREVIEW_RECORDS = 500
MAX_OHLCV_PREVIEW_RECORDS = 1000
MAX_TIMELINE_INTERVALS = 200
EXPORT_ROOT_REF = "data/exports"


def dashboard_data_viewer_summary(config: dict[str, Any], *, config_path: Path) -> dict[str, Any]:
    stores_payload = dashboard_data_stores(config, config_path=config_path)
    coverage_state = read_collection_coverage_state(config_path)
    stores_by_name = {
        str(store.get("name")): store
        for store in stores_payload.get("stores", [])
        if isinstance(store, dict) and store.get("name")
    }
    summaries = []
    for data_type in SUPPORTED_DATA_TYPES:
        store = stores_by_name.get(STORE_BY_DATA_TYPE[data_type], {})
        coverage = summarize_collection_coverage(coverage_state, data_type=data_type)
        coverage_payload = _coverage_summary(coverage, coverage_state=coverage_state)
        _fill_history_range_fallback(coverage_payload, data_type=data_type, config_path=config_path)
        warnings = _string_list(store.get("warnings"))
        warnings.extend(str(item) for item in coverage_state.get("warnings", []) if isinstance(item, str))
        summaries.append(
            {
                "data_type": data_type,
                "store_name": STORE_BY_DATA_TYPE[data_type],
                "title": store.get("title") or _title_for_data_type(data_type),
                "status": str(store.get("status") or "skipped"),
                "summary": _dict(store.get("drilldown")).get("summary") or _dict(store.get("fields")),
                "ranges": _dict(store.get("drilldown")).get("ranges") or {},
                "coverage": coverage_payload,
                "query_capability": _query_capability(data_type),
                "export_capability": _export_capability(data_type),
                "collection_capability": _collection_capability(data_type),
                "warnings": _bounded_strings(warnings),
                "errors": _bounded_strings(_string_list(store.get("errors"))),
                "source_artifacts": _bounded_strings(_string_list(store.get("source_artifacts"))),
            }
        )
    return {
        "schema_version": DATA_VIEWER_SCHEMA_VERSION,
        "artifact_type": "dashboard_data_viewer_summary",
        "status": stores_payload.get("status") or "partial",
        "stores": summaries,
        "source_artifacts": _bounded_strings(_string_list(stores_payload.get("source_artifacts"))),
        "warnings": _bounded_strings(_string_list(stores_payload.get("warnings"))),
        "errors": _bounded_strings(_string_list(stores_payload.get("errors"))),
        "omitted": {
            "full_reusable_histories_embedded": False,
            "full_raw_histories_embedded": False,
            "preview_records_embedded": False,
        },
    }


def dashboard_data_viewer_timeline(config: dict[str, Any], *, config_path: Path, request: dict[str, Any]) -> dict[str, Any]:
    del config
    parsed, error = _parse_viewer_request(request, require_source=False, default_limit=MAX_TIMELINE_INTERVALS)
    if error:
        return _error_payload("dashboard_data_coverage_timeline", error)
    state = read_collection_coverage_state(config_path)
    summary = summarize_collection_coverage(
        state,
        data_type=parsed["data_type"],
        source=parsed.get("source"),
        identity=parsed["identity"] if parsed["identity"] else None,
        requested_start=parsed["start"],
        requested_end=parsed["end"],
    )
    intervals = _coverage_intervals(
        state,
        data_type=parsed["data_type"],
        source=parsed.get("source"),
        identity=parsed["identity"] if parsed["identity"] else None,
        requested_start=parsed["start"],
        requested_end=parsed["end"],
    )
    intervals.extend(_unknown_intervals(summary.get("unknown_ranges") or []))
    intervals = sorted(intervals, key=lambda item: (str(item.get("range_start") or ""), str(item.get("status") or "")))
    bounded = intervals[: parsed["limit"]]
    omitted = max(0, len(intervals) - len(bounded))
    warnings = _string_list(state.get("warnings"))
    if omitted:
        warnings.append(f"{omitted} coverage timeline interval(s) omitted by limit.")
    return {
        "schema_version": DATA_VIEWER_SCHEMA_VERSION,
        "artifact_type": "dashboard_data_coverage_timeline",
        "status": "warning" if warnings or state.get("errors") else "ok",
        "data_type": parsed["data_type"],
        "source": parsed.get("source"),
        "identity": parsed["identity"],
        "requested_start": parsed["start"],
        "requested_end": parsed["end"],
        "coverage": _coverage_summary(summary, coverage_state=state),
        "intervals": bounded,
        "omitted": {"intervals": omitted, "full_coverage_state_embedded": False},
        "source_artifacts": ["data/research/metadata/collection_coverage_state.json"],
        "warnings": _bounded_strings(warnings),
        "errors": _bounded_error_messages(state.get("errors")),
    }


def dashboard_data_viewer_preview(config: dict[str, Any], *, config_path: Path, request: dict[str, Any]) -> dict[str, Any]:
    data_type = str(request.get("data_type") or "").strip()
    default_limit = MAX_OHLCV_PREVIEW_RECORDS if data_type == "ohlcv" else MAX_PREVIEW_RECORDS
    parsed, error = _parse_viewer_request(request, require_source=False, default_limit=default_limit)
    if error:
        return _error_payload("dashboard_data_preview", error)
    try:
        if parsed["data_type"] == "ohlcv":
            missing = [
                name
                for name in ("source", "symbol", "timeframe")
                if not parsed.get(name)
            ]
            if missing:
                return _error_payload("dashboard_data_preview", f"ohlcv preview requires {', '.join(missing)}.")
            result = query_ohlcv_records(
                _ohlcv_storage_dir(config, config_path=config_path),
                source=str(parsed["source"]),
                symbol=str(parsed["symbol"]),
                timeframe=str(parsed["timeframe"]),
                start=parsed["start"],
                end=parsed["end"],
                as_of=parsed.get("as_of"),
                config_path=config_path,
                limit=parsed["limit"],
            )
        else:
            result = query_event_like_records(
                config_path,
                data_type=parsed["data_type"],
                source=parsed.get("source"),
                identity=parsed["identity"],
                start=parsed["start"],
                end=parsed["end"],
                as_of=parsed.get("as_of"),
                limit=parsed["limit"],
                sort_order=parsed["sort_order"],
            )
    except (OHLCVQueryError, EventLikeQueryError, DataExportError) as exc:
        return _error_payload("dashboard_data_preview", str(exc), status="failed")
    return {
        "schema_version": DATA_VIEWER_SCHEMA_VERSION,
        "artifact_type": "dashboard_data_preview",
        "status": result.get("status") or "ok",
        "data_type": parsed["data_type"],
        "source": parsed.get("source"),
        "identity": parsed["identity"],
        "query": _query_summary(result),
        "records": result.get("records") or [],
        "coverage_diagnostics": result.get("coverage_diagnostics") or {},
        "warnings": result.get("warnings") or [],
        "errors": result.get("errors") or [],
        "source_artifacts": result.get("source_artifacts") or [],
        "omitted": {
            "full_reusable_history_embedded": False,
            "record_limit": parsed["limit"],
        },
    }


def dashboard_data_viewer_export(config: dict[str, Any], *, config_path: Path, request: dict[str, Any]) -> dict[str, Any]:
    parsed, error = _parse_viewer_request(request, require_source=False, default_limit=None)
    if error:
        return _error_payload("dashboard_data_export", error)
    output_format = str(request.get("format") or request.get("output_format") or "").strip().lower()
    if not output_format:
        return _error_payload("dashboard_data_export", "format is required.")
    output_path, output_error = _dashboard_export_path(
        request.get("output_path"),
        data_type=parsed["data_type"],
        output_format=output_format,
        config_path=config_path,
    )
    if output_error:
        return _error_payload("dashboard_data_export", output_error)
    try:
        result = export_data(
            config,
            config_path=config_path,
            data_type=parsed["data_type"],
            source=parsed.get("source"),
            symbol=parsed.get("symbol"),
            timeframe=parsed.get("timeframe"),
            identity=parsed["identity"],
            start=parsed["start"],
            end=parsed["end"],
            as_of=parsed.get("as_of"),
            output_format=output_format,
            output_path=output_path,
            limit=parsed.get("limit"),
            sort_order=parsed["sort_order"],
        )
    except DataExportError as exc:
        return _error_payload("dashboard_data_export", str(exc), status="failed")
    return {
        "schema_version": DATA_VIEWER_SCHEMA_VERSION,
        "artifact_type": "dashboard_data_export",
        "status": result.get("status") or "ok",
        "export": result,
        "source_artifacts": result.get("source_artifacts") or [],
        "warnings": result.get("warnings") or [],
        "errors": result.get("errors") or [],
    }


def dashboard_data_viewer_collection_plan(
    config: dict[str, Any],
    *,
    config_path: Path,
    request: dict[str, Any],
) -> dict[str, Any]:
    del config
    params, error = _collect_params(request)
    if error:
        return _error_payload("dashboard_data_collection_plan", error)
    state = read_collection_coverage_state(config_path)
    try:
        if params.get("source"):
            plan = plan_collection_from_coverage(
                state,
                data_type=params["data_type"],
                source=params["source"],
                identity=params["identity"],
                requested_start=params["start"],
                requested_end=params["end"],
                supports_historical=bool(request.get("supports_historical", True)),
                max_exact_windows=_positive_int(request.get("max_exact_windows"), default=3),
                merge_gap_threshold_seconds=_non_negative_int(request.get("merge_gap_threshold_seconds"), default=0),
                min_fetch_window_seconds=_non_negative_int(request.get("min_fetch_window_seconds"), default=0),
            )
        else:
            plan = _configured_source_collection_plan(params)
    except (ValueError, TypeError) as exc:
        return _error_payload("dashboard_data_collection_plan", str(exc))
    return {
        "schema_version": DATA_VIEWER_SCHEMA_VERSION,
        "artifact_type": "dashboard_data_collection_plan",
        "status": plan.get("status") or "ok",
        "plan": plan,
        "source_artifacts": ["data/research/metadata/collection_coverage_state.json"],
        "warnings": plan.get("warnings") or [],
        "errors": plan.get("errors") or [],
    }


def dashboard_data_viewer_collection_job(
    config: dict[str, Any],
    *,
    config_path: Path,
    job_manager: CommandJobManager | None,
    request: dict[str, Any],
) -> dict[str, Any]:
    del config, config_path
    if job_manager is None:
        return _error_payload("dashboard_data_collection_job", "dashboard command jobs are not configured.", status="blocked")
    params, error = _collect_params(request)
    if error:
        return _error_payload("dashboard_data_collection_job", error)
    job_params = {
        "data_type": params["data_type"],
        "start": params["start"],
        "end": params["end"],
    }
    if params.get("source"):
        job_params["source"] = params["source"]
    try:
        if request.get("max_exact_windows") is not None:
            job_params["max_exact_windows"] = _positive_int(request.get("max_exact_windows"), default=3)
        if request.get("merge_gap_threshold_seconds") is not None:
            job_params["merge_gap_threshold_seconds"] = _non_negative_int(
                request.get("merge_gap_threshold_seconds"),
                default=0,
            )
        if request.get("min_fetch_window_seconds") is not None:
            job_params["min_fetch_window_seconds"] = _non_negative_int(
                request.get("min_fetch_window_seconds"),
                default=0,
            )
    except ValueError as exc:
        return _error_payload("dashboard_data_collection_job", str(exc))
    if params["data_type"] == "ohlcv":
        job_params["symbol"] = params["symbol"]
        job_params["timeframe"] = params["timeframe"]
    job = job_manager.create_job({"intent": "data_collect", "params": job_params})
    return {
        "schema_version": DATA_VIEWER_SCHEMA_VERSION,
        "artifact_type": "dashboard_data_collection_job",
        "status": job.get("status") or "unknown",
        "job": job,
        "warnings": job.get("warnings") or [],
        "errors": job.get("errors") or [],
    }


def _parse_viewer_request(
    request: dict[str, Any],
    *,
    require_source: bool,
    default_limit: int | None,
) -> tuple[dict[str, Any], str | None]:
    data_type = str(request.get("data_type") or "").strip()
    if data_type not in SUPPORTED_DATA_TYPES:
        supported = ", ".join(SUPPORTED_DATA_TYPES)
        return {}, f"data_type must be one of: {supported}."
    start = str(request.get("start") or "").strip()
    end = str(request.get("end") or "").strip()
    if not start or not end:
        return {}, "start and end are required."
    source = _optional_text(request.get("source"))
    if require_source and not source:
        return {}, "source is required."
    limit_value = request.get("limit", default_limit)
    if limit_value is None:
        limit = None
    else:
        try:
            parsed_limit = _positive_int(limit_value, default=default_limit or MAX_PREVIEW_RECORDS)
        except (TypeError, ValueError) as exc:
            return {}, str(exc)
        limit = min(parsed_limit, default_limit) if default_limit is not None else parsed_limit
    sort_order = str(request.get("sort_order") or "asc").strip().lower()
    if sort_order not in {"asc", "desc"}:
        return {}, "sort_order must be asc or desc."
    identity = _request_identity(data_type, request, source=source)
    return {
        "data_type": data_type,
        "source": source,
        "symbol": _optional_text(request.get("symbol")),
        "timeframe": _optional_text(request.get("timeframe")),
        "identity": identity,
        "start": start,
        "end": end,
        "as_of": _optional_text(request.get("as_of")),
        "limit": limit,
        "sort_order": sort_order,
    }, None


def _collect_params(request: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    data_type = str(request.get("data_type") or "").strip()
    if data_type not in COLLECTABLE_DATA_TYPES:
        return {}, "data collection jobs currently do not support this data type."
    source = _optional_text(request.get("source"))
    if data_type == "ohlcv" and not source:
        return {}, "source is required."
    if data_type == "text_event" and not source:
        source = "all"
    if data_type not in {"ohlcv", "text_event"}:
        source = None
    start = str(request.get("start") or "").strip()
    end = str(request.get("end") or "").strip()
    if not start or not end:
        return {}, "start and end are required."
    params: dict[str, Any] = {
        "data_type": data_type,
        "source": source,
        "start": start,
        "end": end,
        "identity": _request_identity(data_type, request, source=source),
    }
    if data_type == "ohlcv":
        symbol = _optional_text(request.get("symbol"))
        timeframe = _optional_text(request.get("timeframe"))
        if not symbol or not timeframe:
            return {}, "ohlcv collection requires symbol and timeframe."
        params["symbol"] = symbol
        params["timeframe"] = timeframe
        params["identity"] = {"symbol": symbol, "timeframe": timeframe}
    elif data_type == "text_event" and not params["identity"]:
        params["identity"] = {"source_group": "all"} if source == "all" else {"source_name": source}
    return params, None


def _configured_source_collection_plan(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "collection_plan",
        "created_at": None,
        "status": "warning",
        "data_type": params["data_type"],
        "source": None,
        "identity": params["identity"],
        "requested_start": params["start"],
        "requested_end": params["end"],
        "strategy": "configured_scope",
        "skipped_ranges": [],
        "gap_ranges": [
            {
                "range_start": params["start"],
                "range_end": params["end"],
                "status": "unknown",
            }
        ],
        "retry_ranges": [],
        "planned_fetch_windows": [
            {
                "range_start": params["start"],
                "range_end": params["end"],
                "reason": "configured_scope",
            }
        ],
        "coverage_diagnostics": {
            "status": "not_available",
            "reason": "configured-source collection is planned from configured channels, not a single source identity.",
        },
        "warnings": [
            "Configured-source collection uses configured channels for this data type; source-specific gap planning is not available.",
        ],
        "errors": [],
    }


def _coverage_intervals(
    state: dict[str, Any],
    *,
    data_type: str,
    source: str | None,
    identity: dict[str, str] | None,
    requested_start: str,
    requested_end: str,
) -> list[dict[str, Any]]:
    intervals = []
    wanted_identity = identity if identity else None
    for record in state.get("records", []):
        if not isinstance(record, dict):
            continue
        if record.get("data_type") != data_type:
            continue
        if source is not None and record.get("source") != source:
            continue
        record_identity = _normalized_identity(record.get("identity"))
        if wanted_identity is not None and record_identity != wanted_identity:
            continue
        clipped = _clip_range(record, requested_start=requested_start, requested_end=requested_end)
        if clipped is None:
            continue
        intervals.append(
            {
                **clipped,
                "status": str(record.get("status") or "unknown"),
                "record_count": _non_negative_int_value(record.get("record_count")),
                "attempt_count": _non_negative_int_value(record.get("attempt_count")),
                "latest_attempt_at": record.get("latest_attempt_at"),
                "latest_success_at": record.get("latest_success_at"),
                "source_artifacts": _bounded_strings(_string_list(record.get("source_artifacts"))),
                "warnings": _bounded_strings(_string_list(record.get("warnings"))),
                "errors": _bounded_error_messages(record.get("errors")),
            }
        )
    return intervals


def _unknown_intervals(ranges: list[Any]) -> list[dict[str, Any]]:
    intervals = []
    for item in ranges:
        if not isinstance(item, dict):
            continue
        intervals.append(
            {
                "range_start": item.get("range_start"),
                "range_end": item.get("range_end"),
                "status": "unknown",
                "record_count": 0,
                "attempt_count": 0,
                "source_artifacts": [],
                "warnings": ["coverage is unknown for this interval."],
                "errors": [],
            }
        )
    return intervals


def _clip_range(record: dict[str, Any], *, requested_start: str, requested_end: str) -> dict[str, str] | None:
    range_start = str(record.get("range_start") or "")
    range_end = str(record.get("range_end") or "")
    if not range_start or not range_end:
        return None
    start = max(range_start, requested_start)
    end = min(range_end, requested_end)
    if end <= start:
        return None
    return {"range_start": start, "range_end": end}


def _coverage_summary(summary: dict[str, Any], *, coverage_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "state_status": coverage_state.get("status") or "skipped",
        "record_count": int(summary.get("record_count") or 0),
        "status_counts": summary.get("status_counts") or {},
        "range_start": summary.get("range_start"),
        "range_end": summary.get("range_end"),
        "partial_ranges": summary.get("partial_ranges") or [],
        "failed_ranges": summary.get("failed_ranges") or [],
        "not_collected_ranges": summary.get("not_collected_ranges") or [],
        "unknown_ranges": summary.get("unknown_ranges") or [],
        "warnings": _bounded_strings(_string_list(coverage_state.get("warnings"))),
        "errors": _bounded_error_messages(coverage_state.get("errors")),
    }


def _fill_history_range_fallback(coverage: dict[str, Any], *, data_type: str, config_path: Path) -> None:
    if coverage.get("range_start") and coverage.get("range_end"):
        coverage["range_source"] = "coverage"
        return
    records = _event_like_history_records(data_type, config_path)
    if not records:
        return
    fields = {
        "text_event": ("published_at", "collected_at", "first_seen_at"),
        "macro_calendar": ("scheduled_at",),
        "onchain_flow": ("as_of",),
        "derivatives_market": ("as_of",),
    }.get(data_type, ())
    times = [
        parsed
        for record in records
        if isinstance(record, dict)
        for field in fields
        for parsed in [_parse_record_time(record.get(field))]
        if parsed is not None
    ]
    if not times:
        return
    coverage["range_start"] = _isoformat_utc(min(times))
    coverage["range_end"] = _isoformat_utc(max(times) + timedelta(seconds=1))
    coverage["range_source"] = "history"


def _event_like_history_records(data_type: str, config_path: Path) -> list[dict[str, Any]]:
    readers = {
        "text_event": read_text_event_history_records,
        "macro_calendar": read_macro_calendar_history_records,
        "onchain_flow": read_onchain_flow_history_records,
        "derivatives_market": read_derivatives_history_records,
    }
    reader = readers.get(data_type)
    if reader is None:
        return []
    try:
        records = reader(config_path)
    except Exception:
        return []
    return [record for record in records if isinstance(record, dict)]


def _parse_record_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _isoformat_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _query_summary(result: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "status",
        "requested_start",
        "requested_end",
        "as_of",
        "time_fields",
        "range",
        "matched_record_count",
        "record_count",
        "history_row_count",
        "truncated",
        "limit",
        "missing_diagnostics",
        "filter_diagnostics",
        "empty_result_diagnostics",
    )
    return {key: result.get(key) for key in keys if key in result}


def _request_identity(data_type: str, request: dict[str, Any], *, source: str | None) -> dict[str, str]:
    raw_identity = request.get("identity") if isinstance(request.get("identity"), dict) else {}
    identity = _normalized_identity(raw_identity)
    if identity:
        return identity
    if data_type == "ohlcv":
        symbol = _optional_text(request.get("symbol"))
        timeframe = _optional_text(request.get("timeframe"))
        return {key: value for key, value in {"symbol": symbol, "timeframe": timeframe}.items() if value}
    return {}


def _dashboard_export_path(
    value: Any,
    *,
    data_type: str,
    output_format: str,
    config_path: Path,
) -> tuple[Path | None, str | None]:
    suffix = "parquet" if output_format == "parquet" else output_format
    if output_format not in EXPORT_FORMATS.get(data_type, ()):
        return None, f"{data_type} export format must be one of: {', '.join(EXPORT_FORMATS[data_type])}."
    if value is None or str(value).strip() == "":
        safe_data_type = data_type.replace("_", "-")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        relative = Path(EXPORT_ROOT_REF) / f"{safe_data_type}_{timestamp}.{suffix}"
    else:
        raw = str(value).replace("\\", "/").strip()
        relative = Path(raw)
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            return None, "output_path must be a relative path under data/exports."
        if not raw.startswith(f"{EXPORT_ROOT_REF}/"):
            return None, "output_path must stay under data/exports."
    path = resolve_runtime_path(relative, config_path=config_path)
    export_root = resolve_runtime_path(EXPORT_ROOT_REF, config_path=config_path)
    try:
        path.resolve().relative_to(export_root.resolve())
    except (OSError, ValueError):
        return None, "output_path must stay under data/exports."
    return path, None


def _ohlcv_storage_dir(config: dict[str, Any], *, config_path: Path) -> Path:
    market = config.get("market") if isinstance(config.get("market"), dict) else {}
    ohlcv = market.get("ohlcv") if isinstance(market.get("ohlcv"), dict) else {}
    storage_dir = ohlcv.get("storage_dir")
    if not isinstance(storage_dir, str) or not storage_dir.strip():
        raise DataExportError("market.ohlcv.storage_dir must be configured.")
    return resolve_runtime_path(storage_dir, config_path=config_path)


def _query_capability(data_type: str) -> dict[str, Any]:
    if data_type == "ohlcv":
        return {"implemented": True, "range_field": "open_time", "as_of": True, "requires": ["source", "symbol", "timeframe"]}
    fields = {
        "text_event": "published_at",
        "macro_calendar": "scheduled_at",
        "onchain_flow": "as_of",
        "derivatives_market": "as_of",
    }
    return {"implemented": True, "range_field": fields.get(data_type), "as_of": True, "requires": ["data_type"]}


def _export_capability(data_type: str) -> dict[str, Any]:
    return {"implemented": True, "formats": list(EXPORT_FORMATS[data_type]), "requires_explicit_range": True}


def _collection_capability(data_type: str) -> dict[str, Any]:
    return {
        "implemented": data_type in COLLECTABLE_DATA_TYPES,
        "dry_run": data_type in COLLECTABLE_DATA_TYPES,
        "apply_job": data_type in COLLECTABLE_DATA_TYPES,
    }


def _title_for_data_type(data_type: str) -> str:
    return data_type.replace("_", " ").title()


def _error_payload(artifact_type: str, message: str, *, status: str = "unsupported") -> dict[str, Any]:
    return {
        "schema_version": DATA_VIEWER_SCHEMA_VERSION,
        "artifact_type": artifact_type,
        "status": status,
        "warnings": [],
        "errors": [message],
    }


def _optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _normalized_identity(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): str(value[key])
        for key in sorted(value)
        if value[key] is not None and str(value[key]) != ""
    }


def _positive_int(value: Any, *, default: int) -> int:
    if value is None:
        return default
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError("limit and planner counts must be positive integers.")
    return value


def _non_negative_int(value: Any, *, default: int) -> int:
    if value is None:
        return default
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("planner gap settings must be non-negative integers.")
    return value


def _non_negative_int_value(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, (str, int, float)) and not isinstance(item, bool)]


def _bounded_strings(values: list[str], *, limit: int = 50) -> list[str]:
    return [str(value) for value in values[:limit]]


def _bounded_error_messages(value: Any, *, limit: int = 50) -> list[str]:
    if not isinstance(value, list):
        return []
    messages = []
    for item in value[:limit]:
        if isinstance(item, dict):
            message = item.get("message")
            if isinstance(message, str) and message:
                messages.append(message)
        elif isinstance(item, str):
            messages.append(item)
    return messages
