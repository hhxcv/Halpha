from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from json import JSONDecodeError
from typing import Any

from halpha.data.public_capabilities import ONCHAIN_FLOW_VIEW_DATA_CLASSES, unsupported_onchain_flow_view_reason
from halpha.onchain.onchain_flow_history import (
    ONCHAIN_FLOW_HISTORY_STATE_ARTIFACT,
    onchain_flow_group_path,
    read_onchain_flow_history_records,
)
from halpha.runtime.pipeline_contracts import PipelineError, RunContext
from halpha.storage import display_path, write_json


STAGE_NAME = "build_onchain_flow_views"
ONCHAIN_FLOW_VIEWS_ARTIFACT = "raw/onchain_flow_views.json"
VIEW_SCHEMA_VERSION = 1
MAX_VIEW_RECORDS = 50
VIEW_INCLUDED_COLUMNS = ("as_of", "endpoint", "metrics", "units", "warnings", "errors")
SUPPORTED_VIEW_DATA_CLASSES = ONCHAIN_FLOW_VIEW_DATA_CLASSES


def build_onchain_flow_views(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    onchain_flow = _onchain_flow_config(config)
    if not onchain_flow.get("enabled"):
        _record_zero_counts(run)
        return []

    lookback_days = _positive_int(onchain_flow.get("lookback_days"), default=7)
    raw = _read_optional_raw_artifact(run.raw_dir / "onchain_flow.json")
    window_start, window_end = _view_window(raw, lookback_days=lookback_days, now=now)
    availability = _availability_by_key(raw)
    history_records = read_onchain_flow_history_records(run.config_path)

    views = []
    for scope in _requested_scopes(onchain_flow):
        data_class = scope["data_class"]
        if data_class not in SUPPORTED_VIEW_DATA_CLASSES:
            views.append(_skipped_view(scope=scope, reason=unsupported_onchain_flow_view_reason(data_class)))
            continue
        if data_class == "exchange_flow_availability":
            views.append(
                _availability_view(
                    scope=scope,
                    window_start=window_start,
                    window_end=window_end,
                    availability_status=availability.get((scope["source"], data_class)),
                    config_base=run.config_path.parent,
                )
            )
            continue
        views.append(
            _view_record(
                records=history_records,
                scope=scope,
                window_start=window_start,
                window_end=window_end,
                availability_status=availability.get((scope["source"], data_class)),
                config_base=run.config_path.parent,
            )
        )

    artifact = {
        "schema_version": VIEW_SCHEMA_VERSION,
        "artifact_type": "onchain_flow_views",
        "created_at": _format_utc(now),
        "input_window_start": window_start,
        "input_window_end": window_end,
        "source_artifacts": [_state_artifact(run)],
        "views": views,
        "warnings": _artifact_warnings(views),
        "errors": _artifact_errors(views),
    }
    write_json(run.raw_dir / "onchain_flow_views.json", artifact)
    run.manifest["artifacts"]["onchain_flow_views"] = ONCHAIN_FLOW_VIEWS_ARTIFACT
    _record_manifest_summary(run, views, artifact)
    return [ONCHAIN_FLOW_VIEWS_ARTIFACT]


def _load_onchain_flow_view_records(
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
        for record in read_onchain_flow_history_records(config_path)
        if record.get("source") == view.get("source")
        and record.get("data_class") == view.get("data_class")
        and record.get("asset") == view.get("asset")
        and record.get("chain") == view.get("chain")
        and start <= str(record.get("as_of") or "") <= end
    ]
    columns = tuple(view.get("included_columns") or VIEW_INCLUDED_COLUMNS)
    return [
        {column: record.get(column) for column in columns}
        for record in sorted(records, key=lambda item: item["as_of"])[-MAX_VIEW_RECORDS:]
    ]


def _view_record(
    *,
    records: list[dict[str, Any]],
    scope: dict[str, str],
    window_start: str,
    window_end: str,
    availability_status: dict[str, Any] | None,
    config_base: Any,
) -> dict[str, Any]:
    group_records = [
        record
        for record in records
        if record.get("source") == scope["source"]
        and record.get("data_class") == scope["data_class"]
        and record.get("asset") == scope["asset"]
        and record.get("chain") == scope["chain"]
    ]
    group_records = sorted(group_records, key=lambda record: record["as_of"])
    window = [record for record in group_records if window_start <= str(record.get("as_of") or "") <= window_end]
    selected = window[-MAX_VIEW_RECORDS:]
    latest_group = group_records[-1]["as_of"] if group_records else None
    latest_window = window[-1]["as_of"] if window else None
    status, warnings, errors = _view_status(
        scope=scope,
        window=window,
        group_records=group_records,
        window_start=window_start,
        availability_status=availability_status,
    )
    omitted = max(len(window) - len(selected), 0)
    if omitted:
        warnings.append(
            f"{scope['source']} {scope['data_class']} {scope['asset']} {scope['chain']} "
            f"on-chain flow view omitted {omitted} records over budget {MAX_VIEW_RECORDS}."
        )
        if status == "succeeded":
            status = "bounded"

    return {
        "view_id": _view_id(scope, latest_window or latest_group),
        "data_class": scope["data_class"],
        "source": scope["source"],
        "asset": scope["asset"],
        "chain": scope["chain"],
        "lookback_days": scope["lookback_days"],
        "input_window_start": window_start,
        "input_window_end": window_end,
        "latest_observation_time": latest_window or latest_group,
        "row_count": len(window),
        "included_record_count": len(selected),
        "omitted_record_count": omitted,
        "status": status,
        "storage_ref": _storage_ref(scope, config_base),
        "included_columns": list(VIEW_INCLUDED_COLUMNS),
        "records": [_selected_record(record) for record in selected],
        "warnings": _unique_sorted(warnings),
        "errors": errors,
        "source_artifacts": [_state_artifact_from_base(config_base)],
    }


def _availability_view(
    *,
    scope: dict[str, str],
    window_start: str,
    window_end: str,
    availability_status: dict[str, Any] | None,
    config_base: Any,
) -> dict[str, Any]:
    raw_status = str(availability_status.get("status") or "") if isinstance(availability_status, dict) else ""
    reason = str(availability_status.get("reason") or "") if isinstance(availability_status, dict) else ""
    status = raw_status or "missing_availability"
    warnings = []
    errors = []
    if status in {"failed"}:
        errors.append({"source": scope["source"], "data_class": scope["data_class"], "message": reason or status})
    elif status != "succeeded":
        warnings.append(reason or f"{scope['data_class']} source availability status is {status}.")

    return {
        "view_id": _view_id(scope, "availability"),
        "data_class": scope["data_class"],
        "source": scope["source"],
        "asset": scope["asset"],
        "chain": scope["chain"],
        "lookback_days": scope["lookback_days"],
        "input_window_start": window_start,
        "input_window_end": window_end,
        "latest_observation_time": None,
        "row_count": 0,
        "included_record_count": 0,
        "omitted_record_count": 0,
        "status": status,
        "storage_ref": None,
        "included_columns": [],
        "records": [],
        "warnings": _unique_sorted(warnings),
        "errors": errors,
        "source_artifacts": [_state_artifact_from_base(config_base)],
    }


def _view_status(
    *,
    scope: dict[str, str],
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
        if raw_status == "partial":
            warnings.append(reason or f"{scope['data_class']} on-chain flow source returned partial data.")
            return "partial", warnings, errors
        return "succeeded", warnings, errors
    if raw_status == "failed":
        errors.append(
            {
                "source": scope["source"],
                "data_class": scope["data_class"],
                "asset": scope["asset"],
                "chain": scope["chain"],
                "message": reason or "on-chain flow source failed.",
            }
        )
        return "failed", warnings, errors
    if raw_status in {"insufficient_data", "partial", "skipped", "stale", "unavailable"}:
        warnings.append(reason or f"{scope['data_class']} on-chain flow source status is {raw_status}.")
        return raw_status, warnings, errors
    if group_records and str(group_records[-1].get("as_of") or "") < window_start:
        warnings.append(
            f"{scope['source']} {scope['data_class']} {scope['asset']} {scope['chain']} "
            "on-chain flow history is stale for current window."
        )
        return "stale", warnings, errors
    warnings.append(
        f"{scope['source']} {scope['data_class']} {scope['asset']} {scope['chain']} has no on-chain flow history."
    )
    return "missing_history", warnings, errors


def _selected_record(record: dict[str, Any]) -> dict[str, Any]:
    return {column: record.get(column) for column in VIEW_INCLUDED_COLUMNS}


def _skipped_view(*, scope: dict[str, str], reason: str) -> dict[str, Any]:
    return {
        "view_id": _view_id(scope, "skipped"),
        "data_class": scope["data_class"],
        "source": scope["source"],
        "asset": scope["asset"],
        "chain": scope["chain"],
        "lookback_days": 0,
        "input_window_start": None,
        "input_window_end": None,
        "latest_observation_time": None,
        "row_count": 0,
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


def _requested_scopes(onchain_flow: dict[str, Any]) -> list[dict[str, Any]]:
    lookback_days = _positive_int(onchain_flow.get("lookback_days"), default=7)
    data_classes = _string_list(onchain_flow.get("data_classes"))
    assets = set(_string_list(onchain_flow.get("assets")))
    chains = set(_string_list(onchain_flow.get("chains")))
    scopes = []
    for data_class in data_classes:
        if data_class == "stablecoin_supply" and "ALL_STABLECOINS" in assets and "all" in chains:
            scopes.append(
                {
                    "data_class": data_class,
                    "source": "defillama_stablecoins",
                    "asset": "ALL_STABLECOINS",
                    "chain": "all",
                    "lookback_days": lookback_days,
                }
            )
        elif data_class in {"chain_activity", "network_congestion"} and "BTC" in assets and "bitcoin" in chains:
            scopes.append(
                {
                    "data_class": data_class,
                    "source": "blockchain_com_charts",
                    "asset": "BTC",
                    "chain": "bitcoin",
                    "lookback_days": lookback_days,
                }
            )
        elif data_class == "exchange_flow_availability":
            scopes.append(
                {
                    "data_class": data_class,
                    "source": "public_aggregate",
                    "asset": "ALL_CONFIGURED_ASSETS",
                    "chain": "all",
                    "lookback_days": lookback_days,
                }
            )
        else:
            scopes.append(
                {
                    "data_class": data_class,
                    "source": str(onchain_flow.get("source") or "unknown_source"),
                    "asset": ",".join(sorted(assets)) or "unknown_asset",
                    "chain": ",".join(sorted(chains)) or "unknown_chain",
                    "lookback_days": lookback_days,
                }
            )
    return scopes


def _view_window(raw: dict[str, Any] | None, *, lookback_days: int, now: datetime | str | None) -> tuple[str, str]:
    window = raw.get("window") if isinstance(raw, dict) else None
    if isinstance(window, dict) and isinstance(window.get("lookback_start"), str) and isinstance(window.get("lookback_end"), str):
        return window["lookback_start"], window["lookback_end"]
    timestamp = _parse_utc(_format_utc(now))
    return _format_utc(timestamp - timedelta(days=lookback_days)), _format_utc(timestamp)


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
            "raw/onchain_flow.json is not valid JSON: " f"{exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    if not isinstance(loaded, dict):
        raise PipelineError("raw/onchain_flow.json must be a JSON object.", stage=STAGE_NAME, exit_code=3)
    return loaded


def _view_id(scope: dict[str, str], latest: str | None) -> str:
    suffix = latest or "missing"
    return (
        f"onchain_flow_view:{scope['data_class']}:{scope['source']}:"
        f"{scope['asset']}:{scope['chain']}:{suffix}"
    )


def _storage_ref(scope: dict[str, str], config_base: Any) -> str:
    return display_path(
        onchain_flow_group_path(
            config_base / "config.yaml",
            source=scope["source"],
            data_class=scope["data_class"],
            asset=scope["asset"],
            chain=scope["chain"],
        ),
        base=config_base,
    )


def _record_manifest_summary(run: RunContext, views: list[dict[str, Any]], artifact: dict[str, Any]) -> None:
    counts = run.manifest.setdefault("counts", {})
    counts["onchain_flow_views"] = len(views)
    counts["onchain_flow_view_records"] = sum(_int(view.get("included_record_count")) for view in views)
    counts["onchain_flow_views_bounded"] = sum(1 for view in views if view.get("status") == "bounded")
    counts["onchain_flow_views_partial"] = sum(1 for view in views if view.get("status") == "partial")
    counts["onchain_flow_views_stale"] = sum(1 for view in views if view.get("status") == "stale")
    counts["onchain_flow_views_unavailable"] = sum(1 for view in views if view.get("status") == "unavailable")
    counts["onchain_flow_views_errors"] = sum(len(_list(view.get("errors"))) for view in views)
    run.manifest["onchain_flow_views"] = {
        "status": _artifact_status(views),
        "artifact": ONCHAIN_FLOW_VIEWS_ARTIFACT,
        "views": len(views),
        "records": counts["onchain_flow_view_records"],
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
    counts["onchain_flow_views"] = 0
    counts["onchain_flow_view_records"] = 0
    counts["onchain_flow_views_bounded"] = 0
    counts["onchain_flow_views_partial"] = 0
    counts["onchain_flow_views_stale"] = 0
    counts["onchain_flow_views_unavailable"] = 0
    counts["onchain_flow_views_errors"] = 0


def _artifact_status(views: list[dict[str, Any]]) -> str:
    if any(view.get("errors") for view in views):
        return "warning"
    warning_statuses = {
        "bounded",
        "failed",
        "insufficient_data",
        "missing_availability",
        "missing_history",
        "partial",
        "skipped",
        "stale",
        "unavailable",
    }
    if any(view.get("status") in warning_statuses for view in views):
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
    artifact = run.manifest.get("artifacts", {}).get("onchain_flow_state")
    return str(artifact or ONCHAIN_FLOW_HISTORY_STATE_ARTIFACT)


def _state_artifact_from_base(config_base: Any) -> str:
    return display_path(config_base / ONCHAIN_FLOW_HISTORY_STATE_ARTIFACT, base=config_base)


def _onchain_flow_config(config: dict[str, Any]) -> dict[str, Any]:
    onchain_flow = config.get("onchain_flow")
    return onchain_flow if isinstance(onchain_flow, dict) else {}


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
