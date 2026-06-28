from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from halpha.data.collection_coverage import (
    COVERAGE_STATE_ARTIFACT,
    read_collection_coverage_state,
    write_collection_coverage_state,
)
from halpha.data.collection_planner import plan_collection_from_coverage
from halpha.data.research_data_catalog import CATALOG_ARTIFACT, write_research_data_catalog_snapshot
from halpha.market.ohlcv_quality import ohlcv_next_open_time, ohlcv_timeframe_is_aligned
from halpha.market.ohlcv_source import (
    CCXTOHLCVSource,
    OHLCVSourceError,
    SUPPORTED_OHLCV_SOURCES,
    TIMEFRAME_DURATIONS,
)
from halpha.market.ohlcv_store import OHLCVParquetStore, OHLCVStoreError
from halpha.storage import display_path, resolve_runtime_path, runtime_root


COLLECTION_SCHEMA_VERSION = 1
OHLCV_SCHEMA_ARTIFACT = "data/market/metadata/ohlcv_schema.json"
OHLCV_SYNC_STATE_ARTIFACT = "data/market/metadata/ohlcv_sync_state.json"
REQUEST_LIMIT_PADDING = 1


class OHLCVCollectionError(Exception):
    def __init__(self, message: str, *, exit_code: int = 3) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class OHLCVSourceClient(Protocol):
    def fetch_records(
        self,
        *,
        symbol: str,
        timeframe: str,
        since: datetime | str | None = None,
        limit: int | None = None,
        now: datetime | str | None = None,
    ) -> list[dict[str, Any]]:
        ...


SourceFactory = Callable[[str, str | None], OHLCVSourceClient]


def collect_ohlcv_data(
    config: dict[str, Any],
    *,
    config_path: Path,
    source: str,
    symbol: str,
    timeframe: str,
    requested_start: str,
    requested_end: str,
    dry_run: bool = True,
    source_factory: SourceFactory | None = None,
    now: datetime | str | None = None,
    supports_historical: bool = True,
    max_exact_windows: int = 3,
    merge_gap_threshold_seconds: int = 0,
    min_fetch_window_seconds: int = 0,
) -> dict[str, Any]:
    start = _format_utc(requested_start)
    end = _format_utc(requested_end)
    requested_start_dt = _parse_utc(start)
    requested_end_dt = _parse_utc(end)
    if requested_end_dt <= requested_start_dt:
        raise OHLCVCollectionError("requested_end must be greater than requested_start.", exit_code=2)

    market, ohlcv = _configured_market_ohlcv(config)
    source_name = _require_configured_source(market, source)
    _require_configured_symbol(market, symbol)
    _require_configured_timeframe(ohlcv, timeframe)
    _require_timeframe_aligned(requested_start_dt, timeframe, "requested_start")
    _require_timeframe_aligned(requested_end_dt, timeframe, "requested_end")

    coverage_state = read_collection_coverage_state(config_path)
    identity = {"symbol": symbol, "timeframe": timeframe}
    plan = plan_collection_from_coverage(
        coverage_state,
        data_type="ohlcv",
        source=source_name,
        identity=identity,
        requested_start=start,
        requested_end=end,
        supports_historical=supports_historical,
        now=now,
        max_exact_windows=max_exact_windows,
        merge_gap_threshold_seconds=merge_gap_threshold_seconds,
        min_fetch_window_seconds=min_fetch_window_seconds,
    )

    mode = "dry_run" if dry_run else "apply"
    result = _base_result(
        mode=mode,
        source=source_name,
        symbol=symbol,
        timeframe=timeframe,
        requested_start=start,
        requested_end=end,
        plan=plan,
    )
    if dry_run:
        return result

    existing_records = _existing_coverage_records(coverage_state)
    if plan["strategy"] == "no_work":
        result["artifacts"].update(
            _write_catalog_snapshot(
                config,
                config_path=config_path,
                status="succeeded",
                warnings=result["warnings"],
                errors=result["errors"],
                now=now,
            )
        )
        return result

    planned_windows = [window for window in plan.get("planned_fetch_windows", []) if isinstance(window, dict)]
    if plan["strategy"] == "blocked":
        coverage_updates = _blocked_coverage_records(
            source=source_name,
            symbol=symbol,
            timeframe=timeframe,
            requested_start=start,
            requested_end=end,
            plan=plan,
            now=now,
        )
        state = write_collection_coverage_state(
            config_path,
            [*existing_records, *coverage_updates],
            now=now,
            source_artifacts=[COVERAGE_STATE_ARTIFACT],
        )
        result["status"] = "blocked"
        result["coverage_updates"] = coverage_updates
        result["artifacts"]["collection_coverage"] = COVERAGE_STATE_ARTIFACT
        result["counts"]["coverage_records_written"] = len(coverage_updates)
        result["counts"]["coverage_state_records"] = state["counts"]["records"]
        result["errors"].extend(plan.get("errors") or [])
        result["artifacts"].update(
            _write_catalog_snapshot(
                config,
                config_path=config_path,
                status="failed",
                warnings=result["warnings"],
                errors=result["errors"],
                now=now,
            )
        )
        return result

    storage_dir = _storage_dir(ohlcv, config_path)
    store = OHLCVParquetStore(storage_dir)
    try:
        store.write_records([])
        source_client = (source_factory or _default_source_factory)(source_name, _proxy_url(market))
    except (OHLCVSourceError, OHLCVStoreError, OHLCVCollectionError, ValueError) as exc:
        result["errors"].append(
            {
                "source": source_name,
                "symbol": symbol,
                "timeframe": timeframe,
                "message": str(exc),
            }
        )
        coverage_updates = _failed_coverage_records(
            windows=planned_windows or [{"range_start": start, "range_end": end}],
            source=source_name,
            symbol=symbol,
            timeframe=timeframe,
            message=str(exc),
            now=now,
        )
        state = _write_apply_metadata(
            config,
            config_path=config_path,
            existing_coverage_records=existing_records,
            coverage_updates=coverage_updates,
            result=result,
            status="failed",
            now=now,
        )
        result["coverage_updates"] = coverage_updates
        result["counts"]["coverage_state_records"] = state["counts"]["records"]
        _finalize_result_status(result)
        return result

    coverage_updates: list[dict[str, Any]] = []
    for window in planned_windows:
        item, coverage_record = _collect_window(
            store=store,
            source_client=source_client,
            source_name=source_name,
            symbol=symbol,
            timeframe=timeframe,
            window=window,
            now=now,
        )
        result["fetches"].append(item)
        coverage_updates.append(coverage_record)
        result["warnings"].extend(item["warnings"])
        result["errors"].extend(item["errors"])
        result["counts"]["fetched_records"] += item["fetched_count"]
        result["counts"]["window_records"] += item["window_record_count"]
        result["counts"]["stored_records"] += item["stored_count"]

    state = _write_apply_metadata(
        config,
        config_path=config_path,
        existing_coverage_records=existing_records,
        coverage_updates=coverage_updates,
        result=result,
        status="failed" if result["errors"] else "succeeded",
        now=now,
    )
    result["coverage_updates"] = coverage_updates
    result["counts"]["coverage_state_records"] = state["counts"]["records"]
    _finalize_result_status(result)
    return result


def _collect_window(
    *,
    store: OHLCVParquetStore,
    source_client: OHLCVSourceClient,
    source_name: str,
    symbol: str,
    timeframe: str,
    window: dict[str, Any],
    now: datetime | str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    start = _format_utc(str(window["range_start"]))
    end = _format_utc(str(window["range_end"]))
    expected_count = _expected_open_count(start, end, timeframe)
    warnings: list[str] = []
    errors: list[dict[str, Any]] = []
    before_records: list[dict[str, Any]] = []
    fetched_count = 0
    window_records: list[dict[str, Any]] = []
    stored_count = 0

    try:
        before_records = store.read_records(source=source_name, symbol=symbol, timeframe=timeframe)
        fetched_records = source_client.fetch_records(
            symbol=symbol,
            timeframe=timeframe,
            since=start,
            limit=expected_count + REQUEST_LIMIT_PADDING,
            now=now,
        )
        fetched_count = len(fetched_records)
        window_records = _records_in_window(
            fetched_records,
            source=source_name,
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
        )
        store.write_records(window_records)
        after_records = store.read_records(source=source_name, symbol=symbol, timeframe=timeframe)
        stored_count = max(len(after_records) - len(before_records), 0)
        status = _successful_window_status(len(window_records), expected_count)
        if status == "partial":
            warnings.append(
                f"{source_name} {symbol} {timeframe} returned {len(window_records)} of "
                f"{expected_count} expected candle(s) for {start} to {end}."
            )
    except (OHLCVSourceError, OHLCVStoreError, OHLCVCollectionError, ValueError) as exc:
        status = "failed"
        errors.append(
            {
                "source": source_name,
                "symbol": symbol,
                "timeframe": timeframe,
                "range_start": start,
                "range_end": end,
                "message": str(exc),
            }
        )

    item = {
        "status": status,
        "source": source_name,
        "symbol": symbol,
        "timeframe": timeframe,
        "range_start": start,
        "range_end": end,
        "reason": window.get("reason") or "missing_coverage",
        "expected_count": expected_count,
        "fetched_count": fetched_count,
        "window_record_count": len(window_records),
        "stored_count": stored_count,
        "warnings": warnings,
        "errors": errors,
    }
    return item, _coverage_record_from_item(item, now=now)


def _base_result(
    *,
    mode: str,
    source: str,
    symbol: str,
    timeframe: str,
    requested_start: str,
    requested_end: str,
    plan: dict[str, Any],
) -> dict[str, Any]:
    planned_windows = [window for window in plan.get("planned_fetch_windows", []) if isinstance(window, dict)]
    return {
        "schema_version": COLLECTION_SCHEMA_VERSION,
        "artifact_type": "ohlcv_collection_result",
        "mode": mode,
        "status": str(plan.get("status") or "ok"),
        "data_type": "ohlcv",
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "requested_start": requested_start,
        "requested_end": requested_end,
        "plan": plan,
        "fetches": [],
        "coverage_updates": [],
        "counts": {
            "planned_fetch_windows": len(planned_windows),
            "skipped_ranges": len(plan.get("skipped_ranges") or []),
            "gap_ranges": len(plan.get("gap_ranges") or []),
            "retry_ranges": len(plan.get("retry_ranges") or []),
            "fetched_records": 0,
            "window_records": 0,
            "stored_records": 0,
            "coverage_records_written": 0,
            "coverage_state_records": 0,
        },
        "artifacts": {},
        "warnings": list(plan.get("warnings") or []),
        "errors": list(plan.get("errors") or []),
    }


def _write_apply_metadata(
    config: dict[str, Any],
    *,
    config_path: Path,
    existing_coverage_records: list[dict[str, Any]],
    coverage_updates: list[dict[str, Any]],
    result: dict[str, Any],
    status: str,
    now: datetime | str | None,
) -> dict[str, Any]:
    state = write_collection_coverage_state(
        config_path,
        [*existing_coverage_records, *coverage_updates],
        now=now,
        source_artifacts=[OHLCV_SYNC_STATE_ARTIFACT],
    )
    result["counts"]["coverage_records_written"] = len(coverage_updates)
    result["artifacts"].update(
        {
            "collection_coverage": COVERAGE_STATE_ARTIFACT,
            "ohlcv_schema": OHLCV_SCHEMA_ARTIFACT,
            "ohlcv_sync_state": OHLCV_SYNC_STATE_ARTIFACT,
        }
    )
    result["artifacts"].update(
        _write_catalog_snapshot(
            config,
            config_path=config_path,
            status=status,
            warnings=result["warnings"],
            errors=result["errors"],
            now=now,
        )
    )
    return state


def _write_catalog_snapshot(
    config: dict[str, Any],
    *,
    config_path: Path,
    status: str,
    warnings: list[str],
    errors: list[dict[str, Any]],
    now: datetime | str | None,
) -> dict[str, str]:
    write_research_data_catalog_snapshot(
        config,
        config_path=config_path,
        manifest={
            "artifacts": {
                "ohlcv_schema": OHLCV_SCHEMA_ARTIFACT,
                "ohlcv_sync_state": OHLCV_SYNC_STATE_ARTIFACT,
            },
            "counts": {},
            "ohlcv_sync": {
                "status": status,
                "warnings": warnings,
                "errors": errors,
            },
        },
        now=now,
    )
    return {"research_data_catalog": CATALOG_ARTIFACT}


def _coverage_record_from_item(item: dict[str, Any], *, now: datetime | str | None) -> dict[str, Any]:
    status = str(item["status"])
    timestamp = _format_utc(now)
    return {
        "data_type": "ohlcv",
        "source": item["source"],
        "identity": {"symbol": item["symbol"], "timeframe": item["timeframe"]},
        "range_start": item["range_start"],
        "range_end": item["range_end"],
        "status": status,
        "record_count": item["window_record_count"],
        "attempt_count": 1,
        "latest_attempt_at": timestamp,
        "latest_success_at": timestamp if status in {"collected", "no_data"} else None,
        "updated_at": timestamp,
        "coverage_method": "ohlcv_data_collect",
        "source_artifacts": [OHLCV_SYNC_STATE_ARTIFACT],
        "warnings": item["warnings"],
        "errors": item["errors"],
    }


def _blocked_coverage_records(
    *,
    source: str,
    symbol: str,
    timeframe: str,
    requested_start: str,
    requested_end: str,
    plan: dict[str, Any],
    now: datetime | str | None,
) -> list[dict[str, Any]]:
    errors = [error for error in plan.get("errors", []) if isinstance(error, dict)]
    timestamp = _format_utc(now)
    return [
        {
            "data_type": "ohlcv",
            "source": source,
            "identity": {"symbol": symbol, "timeframe": timeframe},
            "range_start": requested_start,
            "range_end": requested_end,
            "status": "failed",
            "record_count": 0,
            "attempt_count": 1,
            "latest_attempt_at": timestamp,
            "latest_success_at": None,
            "updated_at": timestamp,
            "coverage_method": "ohlcv_data_collect",
            "source_artifacts": [COVERAGE_STATE_ARTIFACT],
            "warnings": list(plan.get("warnings") or []),
            "errors": errors or [{"message": "collection plan was blocked."}],
        }
    ]


def _failed_coverage_records(
    *,
    windows: list[dict[str, Any]],
    source: str,
    symbol: str,
    timeframe: str,
    message: str,
    now: datetime | str | None,
) -> list[dict[str, Any]]:
    timestamp = _format_utc(now)
    records = []
    for window in windows:
        records.append(
            {
                "data_type": "ohlcv",
                "source": source,
                "identity": {"symbol": symbol, "timeframe": timeframe},
                "range_start": _format_utc(str(window["range_start"])),
                "range_end": _format_utc(str(window["range_end"])),
                "status": "failed",
                "record_count": 0,
                "attempt_count": 1,
                "latest_attempt_at": timestamp,
                "latest_success_at": None,
                "updated_at": timestamp,
                "coverage_method": "ohlcv_data_collect",
                "source_artifacts": [OHLCV_SYNC_STATE_ARTIFACT],
                "warnings": [],
                "errors": [{"message": message}],
            }
        )
    return records


def _records_in_window(
    records: list[dict[str, Any]],
    *,
    source: str,
    symbol: str,
    timeframe: str,
    start: str,
    end: str,
) -> list[dict[str, Any]]:
    start_dt = _parse_utc(start)
    end_dt = _parse_utc(end)
    selected = []
    for record in records:
        if record.get("source") != source or record.get("symbol") != symbol or record.get("timeframe") != timeframe:
            continue
        open_time = _parse_utc(str(record.get("open_time") or ""))
        if start_dt <= open_time < end_dt:
            selected.append(record)
    return sorted(selected, key=lambda item: str(item.get("open_time") or ""))


def _successful_window_status(record_count: int, expected_count: int) -> str:
    if record_count == 0:
        return "no_data"
    if record_count < expected_count:
        return "partial"
    return "collected"


def _finalize_result_status(result: dict[str, Any]) -> None:
    if result["status"] == "blocked":
        return
    if result["errors"]:
        result["status"] = "failed"
    elif result["warnings"] or any(fetch.get("status") == "partial" for fetch in result["fetches"]):
        result["status"] = "warning"
    else:
        result["status"] = "ok"


def _existing_coverage_records(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [record for record in state.get("records", []) if isinstance(record, dict)]


def _configured_market_ohlcv(config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    market = config.get("market") if isinstance(config.get("market"), dict) else {}
    ohlcv = market.get("ohlcv") if isinstance(market.get("ohlcv"), dict) else None
    if market.get("enabled") is not True or not isinstance(ohlcv, dict):
        raise OHLCVCollectionError("market.ohlcv must be configured for OHLCV collection.", exit_code=2)
    return market, ohlcv


def _require_configured_source(market: dict[str, Any], source: str) -> str:
    requested = str(source or "").strip()
    if not requested:
        raise OHLCVCollectionError("source must be configured for OHLCV collection.", exit_code=2)
    ohlcv = market.get("ohlcv") if isinstance(market.get("ohlcv"), dict) else {}
    configured_sources = [
        str(value)
        for value in ohlcv.get("sources", [])
        if isinstance(value, str) and value.strip()
    ]
    if configured_sources and requested not in configured_sources:
        raise OHLCVCollectionError(
            f"requested source {requested} is not configured for OHLCV collection.",
            exit_code=2,
        )
    if not configured_sources and requested not in SUPPORTED_OHLCV_SOURCES:
        supported = ", ".join(sorted(SUPPORTED_OHLCV_SOURCES))
        raise OHLCVCollectionError(
            f"unsupported OHLCV source {requested}. Supported sources: {supported}.",
            exit_code=2,
        )
    return requested


def _require_configured_symbol(market: dict[str, Any], symbol: str) -> None:
    configured = [str(value) for value in market.get("symbols", []) if isinstance(value, str)]
    if symbol not in configured:
        raise OHLCVCollectionError(f"requested symbol {symbol} is not configured.", exit_code=2)


def _require_configured_timeframe(ohlcv: dict[str, Any], timeframe: str) -> None:
    configured = [str(value) for value in ohlcv.get("timeframes", []) if isinstance(value, str)]
    if timeframe not in configured:
        raise OHLCVCollectionError(f"requested timeframe {timeframe} is not configured.", exit_code=2)
    if timeframe not in TIMEFRAME_DURATIONS:
        supported = ", ".join(sorted(TIMEFRAME_DURATIONS))
        raise OHLCVCollectionError(f"unsupported OHLCV timeframe {timeframe}. Supported: {supported}.", exit_code=2)


def _require_timeframe_aligned(value: datetime, timeframe: str, field: str) -> None:
    if not ohlcv_timeframe_is_aligned(value, timeframe):
        raise OHLCVCollectionError(f"{field} must align to the {timeframe} UTC timeframe boundary.", exit_code=2)


def _expected_open_count(start: str, end: str, timeframe: str) -> int:
    start_dt = _parse_utc(start)
    end_dt = _parse_utc(end)
    if end_dt <= start_dt:
        return 0
    if timeframe != "1month":
        duration = TIMEFRAME_DURATIONS[timeframe]
        return int((end_dt - start_dt).total_seconds() // duration.total_seconds())
    count = 0
    cursor = start_dt
    while cursor < end_dt:
        count += 1
        cursor = ohlcv_next_open_time(cursor, timeframe)
    return count


def _storage_dir(ohlcv: dict[str, Any], config_path: Path) -> Path:
    return resolve_runtime_path(Path(str(ohlcv["storage_dir"])), config_path=config_path)


def _proxy_url(market: dict[str, Any]) -> str | None:
    proxy = market.get("proxy")
    if not isinstance(proxy, dict) or proxy.get("enabled") is not True:
        return None
    value = proxy.get("url")
    return value if isinstance(value, str) and value else None


def _default_source_factory(source_name: str, proxy_url: str | None) -> OHLCVSourceClient:
    return CCXTOHLCVSource(source_name, proxy_url=proxy_url)


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise OHLCVCollectionError("collection timestamps must include a UTC offset.", exit_code=2)
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str):
        timestamp = _parse_utc(value)
    else:
        raise OHLCVCollectionError("collection timestamps must be datetimes or ISO 8601 strings.", exit_code=2)
    return timestamp.isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OHLCVCollectionError(f"collection timestamp is not valid ISO 8601: {value}", exit_code=2) from exc
    if timestamp.tzinfo is None:
        raise OHLCVCollectionError("collection timestamps must include a UTC offset.", exit_code=2)
    return timestamp.astimezone(timezone.utc).replace(microsecond=0)


def display_collection_artifacts(result: dict[str, Any], *, config_path: Path) -> dict[str, str]:
    base = runtime_root(config_path)
    refs = {}
    artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), dict) else {}
    for key, ref in artifacts.items():
        if not isinstance(key, str) or not isinstance(ref, str):
            continue
        refs[key] = display_path(resolve_runtime_path(ref, config_path=config_path), base=base)
    return refs
