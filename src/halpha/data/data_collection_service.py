from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from math import ceil
from pathlib import Path
from typing import Any

from halpha.market.ohlcv_collection import collect_ohlcv_data
from halpha.pipeline import run_pipeline
from halpha.runtime.pipeline_contracts import PipelineError
from halpha.runtime.run_classification import run_trigger_from_env
from halpha.text.text_event_collection import collect_text_event_data


CONFIGURED_EVENT_DATA_TYPES = {"macro_calendar", "onchain_flow", "derivatives_market"}
CONFIGURED_EVENT_REFRESH_TASKS = {
    "macro_calendar": ("collect_macro_calendar_data", "sync_macro_calendar_history"),
    "onchain_flow": ("collect_onchain_flow_data", "sync_onchain_flow_history"),
    "derivatives_market": ("collect_derivatives_market_data", "sync_derivatives_market_history"),
}
REFRESH_DATA_TASKS = (
    "collect_market_data",
    "collect_derivatives_market_data",
    "sync_derivatives_market_history",
    "collect_macro_calendar_data",
    "sync_macro_calendar_history",
    "collect_onchain_flow_data",
    "sync_onchain_flow_history",
    "collect_text_events",
    "sync_ohlcv",
)


def collect_research_data(
    config: dict[str, Any],
    *,
    config_path: Path,
    data_type: str,
    source: str | None,
    symbol: str | None,
    timeframe: str | None,
    requested_start: str,
    requested_end: str,
    apply: bool,
    max_exact_windows: int,
    merge_gap_threshold_seconds: int,
    min_fetch_window_seconds: int,
    run_trigger: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if data_type == "ohlcv":
        if not source or not symbol or not timeframe:
            raise ValueError("data collect --data-type ohlcv requires --source, --symbol and --timeframe.")
        return collect_ohlcv_data(
            config,
            config_path=config_path,
            source=source,
            symbol=symbol,
            timeframe=timeframe,
            requested_start=requested_start,
            requested_end=requested_end,
            dry_run=not apply,
            max_exact_windows=max_exact_windows,
            merge_gap_threshold_seconds=merge_gap_threshold_seconds,
            min_fetch_window_seconds=min_fetch_window_seconds,
        )
    if data_type == "text_event":
        return collect_text_event_data(
            config,
            config_path=config_path,
            source=source or "all",
            requested_start=requested_start,
            requested_end=requested_end,
            dry_run=not apply,
            max_exact_windows=max_exact_windows,
            merge_gap_threshold_seconds=merge_gap_threshold_seconds,
            min_fetch_window_seconds=min_fetch_window_seconds,
        )
    return _collect_configured_event_data(
        config,
        config_path=config_path,
        data_type=data_type,
        source=source,
        requested_start=requested_start,
        requested_end=requested_end,
        apply=apply,
        run_trigger=run_trigger,
    )


def _collect_configured_event_data(
    config: dict[str, Any],
    *,
    config_path: Path,
    data_type: str,
    source: str | None,
    requested_start: str,
    requested_end: str,
    apply: bool,
    run_trigger: dict[str, Any] | None,
) -> dict[str, Any]:
    if data_type not in CONFIGURED_EVENT_DATA_TYPES:
        raise ValueError(f"unsupported configured collection data type: {data_type}")
    if source and source != "configured":
        raise ValueError(f"{data_type} collection uses configured data sources; omit --source.")
    start = _parse_collection_timestamp(requested_start, field_name="start")
    end = _parse_collection_timestamp(requested_end, field_name="end")
    if end < start:
        raise ValueError("requested_end must be greater than or equal to requested_start.")

    adjusted_config, warnings = _configured_event_collection_config(
        config,
        data_type=data_type,
        requested_start=start,
        requested_end=end,
    )
    plan = {
        "strategy": "configured_scope",
        "planned_fetch_windows": [
            {
                "range_start": requested_start,
                "range_end": requested_end,
                "reason": "configured_scope",
            }
        ],
    }
    if not apply:
        return _configured_event_result(
            data_type=data_type,
            requested_start=requested_start,
            requested_end=requested_end,
            mode="dry_run",
            status="ok",
            plan=plan,
            warnings=warnings,
            artifacts={},
            counts={"planned_fetch_windows": 1},
        )

    result = run_pipeline(
        adjusted_config,
        config_path=config_path,
        until_stage="refresh_data",
        skip_codex=True,
        stage_handlers=_configured_event_stage_handlers(data_type),
        run_trigger=run_trigger
        or run_trigger_from_env(
            default_source="CLI",
            default_intent="data_collect",
        ),
    )
    status = "ok" if result.succeeded else "failed"
    errors = [] if result.succeeded else [{"message": result.reason or "configured collection failed."}]
    return _configured_event_result(
        data_type=data_type,
        requested_start=requested_start,
        requested_end=requested_end,
        mode="apply",
        status=status,
        plan=plan,
        warnings=warnings,
        errors=errors,
        artifacts={"manifest": result.run.manifest_path.as_posix()},
        counts={
            "planned_fetch_windows": 1,
            "pipeline_exit_code": result.exit_code,
        },
    )


def _configured_event_stage_handlers(data_type: str) -> dict[str, Any]:
    selected_tasks = set(CONFIGURED_EVENT_REFRESH_TASKS[data_type])
    return {
        task_name: _noop_data_collect_stage
        for task_name in REFRESH_DATA_TASKS
        if task_name not in selected_tasks
    }


def _noop_data_collect_stage(config: dict[str, Any], run: Any) -> list[str]:
    del config, run
    return []


def _configured_event_result(
    *,
    data_type: str,
    requested_start: str,
    requested_end: str,
    mode: str,
    status: str,
    plan: dict[str, Any],
    warnings: list[str],
    errors: list[dict[str, Any]] | None = None,
    artifacts: dict[str, str],
    counts: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "configured_event_collection_result",
        "mode": mode,
        "status": status,
        "data_type": data_type,
        "source": "configured",
        "symbol": None,
        "timeframe": None,
        "requested_start": requested_start,
        "requested_end": requested_end,
        "plan": plan,
        "fetches": [],
        "coverage_updates": [],
        "counts": counts,
        "artifacts": artifacts,
        "warnings": warnings,
        "errors": errors or [],
    }


def _configured_event_collection_config(
    config: dict[str, Any],
    *,
    data_type: str,
    requested_start: datetime,
    requested_end: datetime,
) -> tuple[dict[str, Any], list[str]]:
    adjusted = deepcopy(config)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    warnings = [
        "Configured-source collection uses the channels and data classes from the active config.",
    ]
    if data_type == "macro_calendar":
        macro = adjusted.setdefault("macro_calendar", {})
        macro["lookback_days"] = max(
            _positive_config_int(macro.get("lookback_days"), default=7),
            _days_between(now, requested_start),
        )
        macro["lookahead_days"] = max(
            _positive_config_int(macro.get("lookahead_days"), default=45),
            _days_between(requested_end, now),
        )
        return adjusted, warnings
    if data_type == "onchain_flow":
        onchain = adjusted.setdefault("onchain_flow", {})
        onchain["lookback_days"] = max(
            _positive_config_int(onchain.get("lookback_days"), default=7),
            _days_between(now, requested_start),
        )
        return adjusted, warnings
    warnings.append(
        "Derivatives collection uses configured symbols, periods, and source endpoint limits; "
        "the requested range is recorded for the job but exact historical gap fetches are source-limited."
    )
    return adjusted, warnings


def _parse_collection_timestamp(value: str, *, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO 8601 timestamp.") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a UTC offset.")
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def _days_between(later: datetime, earlier: datetime) -> int:
    seconds = (later - earlier).total_seconds()
    return max(0, int(ceil(seconds / 86400)))


def _positive_config_int(value: Any, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
