from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from halpha.market.ohlcv_store import OHLCVParquetStore, OHLCVStoreError
from halpha.runtime.pipeline_contracts import PipelineError, RunContext
from halpha.storage import display_path, write_json


STAGE_NAME = "build_strategy_benchmark_suite"
STRATEGY_BENCHMARK_SUITE_ARTIFACT = "analysis/strategy_benchmark_suite.json"
SCHEMA_VERSION = 1
BENCHMARK_SOURCE = "strategy_benchmark_suite"
VIEW_INCLUDED_COLUMNS = ["open_time", "open", "high", "low", "close", "volume"]
SUPPORTED_WINDOW_SELECTIONS = {"configured_lookback", "latest_lookback", "date_window"}


def build_strategy_benchmark_suite(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    if not _benchmark_suite_enabled(config):
        _record_disabled(run)
        return []

    artifact = create_strategy_benchmark_suite_artifact(
        config,
        config_path=run.config_path,
        run_output_dir=run.run_dir.parent,
        manifest_artifacts=run.manifest.get("artifacts"),
        now=now,
    )
    records = artifact["benchmarks"]
    coverage = artifact["coverage"]
    warnings = artifact["warnings"]
    errors = artifact["errors"]
    write_json(run.analysis_dir / "strategy_benchmark_suite.json", artifact)
    run.manifest["artifacts"]["strategy_benchmark_suite"] = STRATEGY_BENCHMARK_SUITE_ARTIFACT
    _record_manifest_summary(run, records, coverage=coverage, warnings=warnings, errors=errors)
    return [STRATEGY_BENCHMARK_SUITE_ARTIFACT]


def create_strategy_benchmark_suite_artifact(
    config: dict[str, Any],
    *,
    config_path: Path,
    run_output_dir: Path,
    manifest_artifacts: dict[str, Any] | None = None,
    now: datetime | str | None = None,
) -> dict[str, Any]:
    quant = config.get("quant") if isinstance(config.get("quant"), dict) else {}
    market = config.get("market") if isinstance(config.get("market"), dict) else {}
    ohlcv = market.get("ohlcv") if isinstance(market.get("ohlcv"), dict) else {}
    suite_config = quant.get("benchmark_suite") if isinstance(quant.get("benchmark_suite"), dict) else {}

    source = str(market["source"])
    storage_dir = _storage_dir(ohlcv, config_path)
    source_artifact = _sync_state_artifact(
        storage_dir,
        config_path=config_path,
        manifest_artifacts=manifest_artifacts,
    )
    windows = _window_specs(suite_config)
    store = OHLCVParquetStore(storage_dir, run_output_dir=run_output_dir)

    records = []
    try:
        for symbol in _configured_symbols(market):
            for timeframe in _configured_timeframes(ohlcv):
                for window in windows:
                    records.append(
                        _benchmark_record(
                            store=store,
                            storage_dir=storage_dir,
                            config_base=config_path.parent,
                            source=source,
                            symbol=symbol,
                            timeframe=timeframe,
                            lookback=_configured_lookback(ohlcv, timeframe),
                            window=window,
                            source_artifact=source_artifact,
                        )
                    )
    except OHLCVStoreError as exc:
        raise PipelineError(str(exc), stage=STAGE_NAME, exit_code=3) from exc

    coverage = _coverage(
        records,
        symbols=_configured_symbols(market),
        timeframes=_configured_timeframes(ohlcv),
        windows=windows,
    )
    warnings = _unique_items(
        item
        for record in records
        for item in record.get("warnings", [])
        if isinstance(item, dict)
    )
    errors = [
        error
        for record in records
        for error in record.get("errors", [])
        if isinstance(error, dict)
    ]
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "strategy_benchmark_suite",
        "created_at": _format_utc(now),
        "selection_policy": {
            "source": "configured_symbols_timeframes_and_windows",
            "raw_ohlcv_history_embedded": False,
            "supported_window_selections": sorted(SUPPORTED_WINDOW_SELECTIONS),
        },
        "source_artifacts": [source_artifact],
        "coverage": coverage,
        "benchmarks": records,
        "warnings": warnings,
        "errors": errors,
    }
    return artifact


def _benchmark_suite_enabled(config: dict[str, Any]) -> bool:
    quant = config.get("quant") if isinstance(config.get("quant"), dict) else {}
    market = config.get("market") if isinstance(config.get("market"), dict) else {}
    ohlcv = market.get("ohlcv") if isinstance(market.get("ohlcv"), dict) else {}
    suite_config = quant.get("benchmark_suite") if isinstance(quant.get("benchmark_suite"), dict) else {}
    return (
        quant.get("enabled") is True
        and market.get("enabled") is True
        and isinstance(ohlcv, dict)
        and suite_config.get("enabled") is not False
    )


def _benchmark_record(
    *,
    store: OHLCVParquetStore,
    storage_dir: Path,
    config_base: Path,
    source: str,
    symbol: str,
    timeframe: str,
    lookback: int,
    window: dict[str, Any],
    source_artifact: str,
) -> dict[str, Any]:
    records = store.read_records(source=source, symbol=symbol, timeframe=timeframe)
    selected_rows = _select_rows(records, timeframe=timeframe, configured_lookback=lookback, window=window)
    selection = str(window["selection"])
    requested_lookback = _requested_lookback(selection, configured_lookback=lookback, window=window)
    minimum_rows = _minimum_rows(selection, requested_lookback=requested_lookback, window=window)
    row_count = len(selected_rows)
    history_row_count = len(records)
    start = selected_rows[0]["open_time"] if selected_rows else None
    end = selected_rows[-1]["open_time"] if selected_rows else None
    latest = end
    insufficient = row_count < minimum_rows
    warnings = _record_warnings(
        source=source,
        symbol=symbol,
        timeframe=timeframe,
        window_name=str(window["name"]),
        history_row_count=history_row_count,
        row_count=row_count,
        minimum_rows=minimum_rows,
    )
    status = "insufficient_data" if insufficient else "succeeded"
    return {
        "benchmark_id": _benchmark_id(source, symbol, timeframe, str(window["name"]), start, end),
        "status": status,
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "window_identity": str(window["name"]),
        "window_selection": selection,
        "requested_lookback": requested_lookback,
        "minimum_rows": minimum_rows,
        "input_window_start": start,
        "input_window_end": end,
        "latest_candle_time": latest,
        "row_count": row_count,
        "history_row_count": history_row_count,
        "storage_ref": _storage_ref(storage_dir, source, symbol, timeframe, config_base),
        "included_columns": VIEW_INCLUDED_COLUMNS,
        "source_artifacts": [source_artifact],
        "warnings": warnings,
        "errors": [],
    }


def _select_rows(
    records: list[dict[str, Any]],
    *,
    timeframe: str,
    configured_lookback: int,
    window: dict[str, Any],
) -> list[dict[str, Any]]:
    selection = str(window["selection"])
    if selection == "configured_lookback":
        return records[-configured_lookback:] if records else []
    if selection == "latest_lookback":
        lookback = int(window["lookback"])
        return records[-lookback:] if records else []
    if selection == "date_window":
        start = str(window["start"])
        end = str(window["end"])
        return [record for record in records if start <= str(record["open_time"]) <= end]
    raise PipelineError(
        f"unsupported benchmark window selection for {timeframe}: {selection}",
        stage=STAGE_NAME,
        exit_code=3,
    )


def _record_warnings(
    *,
    source: str,
    symbol: str,
    timeframe: str,
    window_name: str,
    history_row_count: int,
    row_count: int,
    minimum_rows: int,
) -> list[dict[str, Any]]:
    warnings = []
    if history_row_count == 0:
        warnings.append(
            _warning(
                "missing_local_history",
                f"{source} {symbol} {timeframe} has no local OHLCV history for benchmark window {window_name}.",
            )
        )
    if row_count < minimum_rows:
        warnings.append(
            _warning(
                "insufficient_benchmark_history",
                (
                    f"{source} {symbol} {timeframe} benchmark window {window_name} has "
                    f"{row_count} rows, below required minimum {minimum_rows}."
                ),
            )
        )
    return warnings


def _coverage(
    records: list[dict[str, Any]],
    *,
    symbols: list[str],
    timeframes: list[str],
    windows: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "configured_symbols": symbols,
        "configured_timeframes": timeframes,
        "configured_windows": [str(window["name"]) for window in windows],
        "benchmark_records": len(records),
        "succeeded": sum(1 for record in records if record.get("status") == "succeeded"),
        "insufficient_data": sum(1 for record in records if record.get("status") == "insufficient_data"),
        "failed": sum(1 for record in records if record.get("status") == "failed"),
        "missing_history": sum(1 for record in records if int(record.get("history_row_count") or 0) == 0),
        "total_window_rows": sum(int(record.get("row_count") or 0) for record in records),
    }


def _record_manifest_summary(
    run: RunContext,
    records: list[dict[str, Any]],
    *,
    coverage: dict[str, Any],
    warnings: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    run.manifest["counts"]["strategy_benchmark_records"] = len(records)
    run.manifest["counts"]["strategy_benchmark_succeeded"] = coverage["succeeded"]
    run.manifest["counts"]["strategy_benchmark_insufficient_data"] = coverage["insufficient_data"]
    run.manifest["counts"]["strategy_benchmark_failed"] = coverage["failed"]
    run.manifest["strategy_benchmark_suite"] = {
        "enabled": True,
        "records": len(records),
        "succeeded": coverage["succeeded"],
        "insufficient_data": coverage["insufficient_data"],
        "failed": coverage["failed"],
        "missing_history": coverage["missing_history"],
        "source_artifacts": sorted(
            {
                artifact
                for record in records
                for artifact in record.get("source_artifacts", [])
                if isinstance(artifact, str)
            }
        ),
        "warnings": [_warning_summary(item) for item in warnings],
        "errors": errors,
    }


def _record_disabled(run: RunContext) -> None:
    run.manifest["counts"]["strategy_benchmark_records"] = 0
    run.manifest["counts"]["strategy_benchmark_succeeded"] = 0
    run.manifest["counts"]["strategy_benchmark_insufficient_data"] = 0
    run.manifest["counts"]["strategy_benchmark_failed"] = 0
    run.manifest["strategy_benchmark_suite"] = {
        "enabled": False,
        "records": 0,
        "warnings": [],
        "errors": [],
    }


def _window_specs(suite_config: dict[str, Any]) -> list[dict[str, Any]]:
    raw_windows = suite_config.get("windows")
    if raw_windows is None:
        return [{"name": "configured_lookback", "selection": "configured_lookback"}]
    if not isinstance(raw_windows, list) or not raw_windows:
        raise PipelineError(
            "quant.benchmark_suite.windows must be a non-empty list.",
            stage=STAGE_NAME,
            exit_code=3,
        )

    windows = []
    names = set()
    for index, item in enumerate(raw_windows):
        if not isinstance(item, dict):
            raise PipelineError(
                f"quant.benchmark_suite.windows[{index}] must be a mapping.",
                stage=STAGE_NAME,
                exit_code=3,
            )
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise PipelineError(
                f"quant.benchmark_suite.windows[{index}].name must be a non-empty string.",
                stage=STAGE_NAME,
                exit_code=3,
            )
        name = name.strip()
        if name in names:
            raise PipelineError(f"duplicate benchmark window name: {name}", stage=STAGE_NAME, exit_code=3)
        names.add(name)
        selection = str(item.get("selection") or "configured_lookback")
        if selection not in SUPPORTED_WINDOW_SELECTIONS:
            supported = ", ".join(sorted(SUPPORTED_WINDOW_SELECTIONS))
            raise PipelineError(
                f"quant.benchmark_suite.windows[{index}].selection must be one of: {supported}.",
                stage=STAGE_NAME,
                exit_code=3,
            )
        window: dict[str, Any] = {"name": name, "selection": selection}
        if selection == "latest_lookback":
            window["lookback"] = _positive_int(
                item.get("lookback"),
                f"quant.benchmark_suite.windows[{index}].lookback",
            )
        if selection == "date_window":
            window["start"] = _utc_string(item.get("start"), f"quant.benchmark_suite.windows[{index}].start")
            window["end"] = _utc_string(item.get("end"), f"quant.benchmark_suite.windows[{index}].end")
            if window["start"] > window["end"]:
                raise PipelineError(
                    f"quant.benchmark_suite.windows[{index}].start must be before or equal to end.",
                    stage=STAGE_NAME,
                    exit_code=3,
                )
            if "minimum_rows" in item:
                window["minimum_rows"] = _positive_int(
                    item.get("minimum_rows"),
                    f"quant.benchmark_suite.windows[{index}].minimum_rows",
                )
        windows.append(window)
    return sorted(windows, key=lambda item: str(item["name"]))


def _requested_lookback(selection: str, *, configured_lookback: int, window: dict[str, Any]) -> int | None:
    if selection == "configured_lookback":
        return configured_lookback
    if selection == "latest_lookback":
        return int(window["lookback"])
    return None


def _minimum_rows(selection: str, *, requested_lookback: int | None, window: dict[str, Any]) -> int:
    if selection in {"configured_lookback", "latest_lookback"} and requested_lookback is not None:
        return requested_lookback
    return int(window.get("minimum_rows") or 2)


def _configured_symbols(market: dict[str, Any]) -> list[str]:
    return sorted({str(symbol) for symbol in market.get("symbols", [])})


def _configured_timeframes(ohlcv: dict[str, Any]) -> list[str]:
    return sorted({str(timeframe) for timeframe in ohlcv.get("timeframes", [])})


def _configured_lookback(ohlcv: dict[str, Any], timeframe: str) -> int:
    return int(ohlcv["lookback"][timeframe])


def _storage_dir(ohlcv: dict[str, Any], config_path: Path) -> Path:
    storage_dir = Path(str(ohlcv["storage_dir"]))
    if storage_dir.is_absolute():
        return storage_dir
    return config_path.parent / storage_dir


def _storage_ref(
    storage_dir: Path,
    source: str,
    symbol: str,
    timeframe: str,
    config_base: Path,
) -> str:
    group_dir = storage_dir / f"source={source}" / f"symbol={symbol}" / f"timeframe={timeframe}"
    return display_path(group_dir, base=config_base)


def _sync_state_artifact(
    storage_dir: Path,
    *,
    config_path: Path,
    manifest_artifacts: dict[str, Any] | None,
) -> str:
    artifact = manifest_artifacts.get("ohlcv_sync_state") if isinstance(manifest_artifacts, dict) else None
    if isinstance(artifact, str) and artifact:
        return artifact
    return display_path(storage_dir.parent / "metadata" / "ohlcv_sync_state.json", base=config_path.parent)


def _benchmark_id(
    source: str,
    symbol: str,
    timeframe: str,
    window_name: str,
    start: str | None,
    end: str | None,
) -> str:
    return ":".join(
        [
            "strategy_benchmark",
            source,
            symbol,
            timeframe,
            window_name,
            start or "missing",
            end or "missing",
        ]
    )


def _warning(code: str, message: str) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "source": BENCHMARK_SOURCE,
    }


def _warning_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": item.get("code"),
        "message": item.get("message"),
        "source": item.get("source"),
    }


def _unique_items(items: Any) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for item in items:
        key = (item.get("code"), item.get("message"), item.get("source"))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _positive_int(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise PipelineError(f"{path} must be a positive integer.", stage=STAGE_NAME, exit_code=3)
    return value


def _utc_string(value: Any, path: str) -> str:
    if isinstance(value, datetime):
        timestamp = value
    elif isinstance(value, str) and value.strip():
        try:
            timestamp = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise PipelineError(f"{path} must be an ISO 8601 UTC string.", stage=STAGE_NAME, exit_code=3) from exc
    else:
        raise PipelineError(f"{path} must be an ISO 8601 UTC string.", stage=STAGE_NAME, exit_code=3)
    if timestamp.tzinfo is None:
        raise PipelineError(f"{path} must include a UTC offset.", stage=STAGE_NAME, exit_code=3)
    return timestamp.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise PipelineError("created_at must include a UTC offset.", stage=STAGE_NAME, exit_code=3)
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str):
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise PipelineError("created_at must include a UTC offset.", stage=STAGE_NAME, exit_code=3)
        timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)
    else:
        raise PipelineError("created_at must be a datetime or ISO 8601 UTC string.", stage=STAGE_NAME, exit_code=3)
    return timestamp.isoformat().replace("+00:00", "Z")
