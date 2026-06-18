from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .derivatives_history import (
    DERIVATIVES_HISTORY_STATE_ARTIFACT,
    derivatives_market_group_path,
    read_derivatives_history_records,
)
from .pipeline import PipelineError, RunContext
from .storage import display_path, write_json


STAGE_NAME = "build_derivatives_market_views"
DERIVATIVES_MARKET_VIEWS_ARTIFACT = "raw/derivatives_market_views.json"
VIEW_SCHEMA_VERSION = 1
VIEW_INCLUDED_COLUMNS = ("as_of", "endpoint", "metrics", "units", "warnings", "errors")
SUPPORTED_VIEW_DATA_CLASSES = {
    "basis",
    "funding_rate",
    "liquidation_summary",
    "open_interest",
    "premium_index",
    "spread_depth",
}


def build_derivatives_market_views(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    derivatives = _derivatives_config(config)
    if not derivatives.get("enabled"):
        _record_zero_counts(run)
        return []

    source = str(derivatives.get("source") or "unknown_source")
    symbols = _string_list(derivatives.get("symbols"))
    data_classes = _string_list(derivatives.get("data_classes"))
    periods = _string_list(derivatives.get("periods"))
    lookback = derivatives.get("lookback") if isinstance(derivatives.get("lookback"), dict) else {}
    history_records = read_derivatives_history_records(run.config_path)
    views = []
    for data_class in data_classes:
        if data_class not in SUPPORTED_VIEW_DATA_CLASSES:
            views.append(
                _skipped_view(
                    source=source,
                    data_class=data_class,
                    reason=f"{data_class} derivatives views are not implemented.",
                )
            )
            continue
        for symbol in symbols:
            for period in _view_periods(data_class, periods):
                views.append(
                    _view_record(
                        records=history_records,
                        source=source,
                        data_class=data_class,
                        symbol=symbol,
                        period=period,
                        lookback=_view_lookback(data_class, period, lookback),
                        config_base=run.config_path.parent,
                    )
                )

    artifact = {
        "schema_version": VIEW_SCHEMA_VERSION,
        "artifact_type": "derivatives_market_views",
        "created_at": _format_utc(now),
        "source_artifacts": [_state_artifact(run)],
        "views": views,
        "warnings": _artifact_warnings(views),
        "errors": [],
    }
    write_json(run.raw_dir / "derivatives_market_views.json", artifact)
    run.manifest["artifacts"]["derivatives_market_views"] = DERIVATIVES_MARKET_VIEWS_ARTIFACT
    _record_manifest_summary(run, views, artifact)
    return [DERIVATIVES_MARKET_VIEWS_ARTIFACT]


def load_derivatives_market_view_records(
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
        for record in read_derivatives_history_records(config_path)
        if record.get("source") == view.get("source")
        and record.get("data_class") == view.get("data_class")
        and record.get("symbol") == view.get("symbol")
        and record.get("period") == view.get("period")
        and start <= str(record.get("as_of") or "") <= end
    ]
    columns = tuple(view.get("included_columns") or VIEW_INCLUDED_COLUMNS)
    return [{column: record.get(column) for column in columns} for record in sorted(records, key=lambda item: item["as_of"])]


def _view_record(
    *,
    records: list[dict[str, Any]],
    source: str,
    data_class: str,
    symbol: str,
    period: str,
    lookback: int,
    config_base: Any,
) -> dict[str, Any]:
    group_records = [
        record
        for record in records
        if record.get("source") == source
        and record.get("data_class") == data_class
        and record.get("symbol") == symbol
        and record.get("period") == period
    ]
    group_records = sorted(group_records, key=lambda record: record["as_of"])
    window = group_records[-lookback:] if group_records else []
    row_count = len(window)
    latest = window[-1]["as_of"] if window else None
    insufficient = row_count < lookback
    status = "succeeded"
    warnings = []
    if not window:
        status = "missing_history"
        warnings.append(f"{source} {data_class} {symbol} {period} has no derivatives history.")
    elif insufficient:
        status = "insufficient_data"
        warnings.append(
            f"{source} {data_class} {symbol} {period} has {row_count} derivatives rows, "
            f"below configured lookback {lookback}."
        )

    return {
        "view_id": _view_id(source, data_class, symbol, period, latest),
        "data_class": data_class,
        "source": source,
        "market_type": "usd_m_futures",
        "symbol": symbol,
        "period": period,
        "requested_lookback": lookback,
        "input_window_start": window[0]["as_of"] if window else None,
        "input_window_end": latest,
        "latest_observation_time": latest,
        "row_count": row_count,
        "status": status,
        "storage_ref": _storage_ref(source, data_class, symbol, period, config_base),
        "included_columns": list(VIEW_INCLUDED_COLUMNS),
        "insufficient_data": insufficient,
        "warnings": warnings,
        "errors": [],
        "source_artifacts": [_state_artifact_from_base(config_base)],
    }


def _skipped_view(*, source: str, data_class: str, reason: str) -> dict[str, Any]:
    return {
        "view_id": f"derivatives_view:{data_class}:{source}:skipped",
        "data_class": data_class,
        "source": source,
        "market_type": "usd_m_futures",
        "symbol": None,
        "period": None,
        "requested_lookback": 0,
        "input_window_start": None,
        "input_window_end": None,
        "latest_observation_time": None,
        "row_count": 0,
        "status": "skipped",
        "storage_ref": None,
        "included_columns": [],
        "insufficient_data": True,
        "warnings": [reason],
        "errors": [],
        "source_artifacts": [],
    }


def _view_periods(data_class: str, periods: list[str]) -> list[str]:
    if data_class == "funding_rate":
        return ["8h"]
    if data_class == "open_interest":
        return ["snapshot", *periods]
    if data_class == "premium_index":
        return ["snapshot"]
    if data_class == "spread_depth":
        return ["snapshot"]
    if data_class == "liquidation_summary":
        return ["source_availability"]
    return periods


def _view_lookback(data_class: str, period: str, lookback: dict[str, Any]) -> int:
    if period == "snapshot":
        return 1
    if data_class == "funding_rate":
        values = [value for value in lookback.values() if isinstance(value, int) and not isinstance(value, bool) and value > 0]
        return max(values) if values else 1
    value = lookback.get(period)
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return 1


def _view_id(source: str, data_class: str, symbol: str, period: str, latest: str | None) -> str:
    suffix = latest or "missing"
    return f"derivatives_view:{data_class}:{source}:{symbol}:{period}:{suffix}"


def _storage_ref(source: str, data_class: str, symbol: str, period: str, config_base: Any) -> str:
    return display_path(
        derivatives_market_group_path(
            config_base / "config.yaml",
            source=source,
            data_class=data_class,
            symbol=symbol,
            period=period,
        ),
        base=config_base,
    )


def _record_manifest_summary(run: RunContext, views: list[dict[str, Any]], artifact: dict[str, Any]) -> None:
    counts = run.manifest.setdefault("counts", {})
    counts["derivatives_market_views"] = len(views)
    counts["derivatives_market_views_insufficient_data"] = sum(
        1 for view in views if view.get("insufficient_data")
    )
    counts["derivatives_market_views_skipped"] = sum(1 for view in views if view.get("status") == "skipped")
    counts["derivatives_market_views_errors"] = sum(len(_list(view.get("errors"))) for view in views)
    run.manifest["derivatives_market_views"] = {
        "status": _artifact_status(views),
        "artifact": DERIVATIVES_MARKET_VIEWS_ARTIFACT,
        "views": len(views),
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
    counts["derivatives_market_views"] = 0
    counts["derivatives_market_views_insufficient_data"] = 0
    counts["derivatives_market_views_skipped"] = 0
    counts["derivatives_market_views_errors"] = 0


def _artifact_status(views: list[dict[str, Any]]) -> str:
    if any(view.get("errors") for view in views):
        return "warning"
    if any(view.get("status") in {"missing_history", "insufficient_data", "skipped"} for view in views):
        return "warning"
    return "ok" if views else "skipped"


def _artifact_warnings(views: list[dict[str, Any]]) -> list[str]:
    warnings = []
    for view in views:
        warnings.extend(_string_list(view.get("warnings")))
    return sorted(set(warnings))


def _state_artifact(run: RunContext) -> str:
    artifact = run.manifest.get("artifacts", {}).get("derivatives_market_state")
    return str(artifact or DERIVATIVES_HISTORY_STATE_ARTIFACT)


def _state_artifact_from_base(config_base: Any) -> str:
    return display_path(config_base / DERIVATIVES_HISTORY_STATE_ARTIFACT, base=config_base)


def _derivatives_config(config: dict[str, Any]) -> dict[str, Any]:
    market = config.get("market")
    if not isinstance(market, dict):
        return {}
    derivatives = market.get("derivatives")
    return derivatives if isinstance(derivatives, dict) else {}


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value or [] if isinstance(item, str) and item.strip()]


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise PipelineError("created_at must include a UTC offset.", stage=STAGE_NAME, exit_code=3)
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str):
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise PipelineError("created_at must be an ISO 8601 UTC string.", stage=STAGE_NAME, exit_code=3) from exc
        if timestamp.tzinfo is None:
            raise PipelineError("created_at must include a UTC offset.", stage=STAGE_NAME, exit_code=3)
        timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)
    else:
        raise PipelineError("created_at must be a datetime or ISO 8601 UTC string.", stage=STAGE_NAME, exit_code=3)
    return timestamp.isoformat().replace("+00:00", "Z")
