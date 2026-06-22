from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from halpha.market.ohlcv_store import OHLCVParquetStore, OHLCVStoreError
from halpha.runtime.pipeline_contracts import PipelineError, RunContext
from halpha.storage import display_path, write_json


STAGE_NAME = "build_market_data_views"
MARKET_DATA_VIEWS_ARTIFACT = "raw/market_data_views.json"
VIEW_SCHEMA_VERSION = 1
VIEW_INCLUDED_COLUMNS = ("open_time", "open", "high", "low", "close", "volume")


def build_market_data_views(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    market = config.get("market", {})
    ohlcv = market.get("ohlcv")
    if not market.get("enabled") or not isinstance(ohlcv, dict):
        run.manifest["counts"]["market_data_views"] = 0
        run.manifest["counts"]["market_data_views_insufficient_data"] = 0
        return []

    source = str(market["source"])
    storage_dir = _storage_dir(ohlcv, run.config_path)
    store = OHLCVParquetStore(storage_dir, run_output_dir=run.run_dir.parent)
    views = []
    try:
        for symbol in _configured_symbols(market):
            for timeframe in _configured_timeframes(ohlcv):
                views.append(
                    _view_record(
                        store=store,
                        storage_dir=storage_dir,
                        source=source,
                        symbol=symbol,
                        timeframe=timeframe,
                        lookback=_configured_lookback(ohlcv, timeframe),
                        config_base=run.config_path.parent,
                    )
                )
    except OHLCVStoreError as exc:
        raise PipelineError(str(exc), stage=STAGE_NAME, exit_code=3) from exc

    artifact = {
        "schema_version": VIEW_SCHEMA_VERSION,
        "artifact_type": "market_data_views",
        "created_at": _format_utc(now),
        "source_artifacts": [_sync_state_artifact(storage_dir, run)],
        "views": views,
    }
    write_json(run.raw_dir / "market_data_views.json", artifact)
    run.manifest["artifacts"]["market_data_views"] = MARKET_DATA_VIEWS_ARTIFACT
    run.manifest["counts"]["market_data_views"] = len(views)
    run.manifest["counts"]["market_data_views_insufficient_data"] = sum(
        1 for view in views if view["insufficient_data"]
    )
    return [MARKET_DATA_VIEWS_ARTIFACT]


def load_market_data_view_records(
    view: dict[str, Any],
    *,
    storage_dir: Path | str,
) -> list[dict[str, Any]]:
    store = OHLCVParquetStore(storage_dir)
    try:
        records = store.read_records(
            source=str(view["source"]),
            symbol=str(view["symbol"]),
            timeframe=str(view["timeframe"]),
        )
    except OHLCVStoreError as exc:
        raise PipelineError(str(exc), stage=STAGE_NAME, exit_code=3) from exc

    start = view.get("input_window_start")
    end = view.get("input_window_end")
    if not start or not end:
        return []

    columns = tuple(view.get("included_columns") or VIEW_INCLUDED_COLUMNS)
    return [
        {column: record[column] for column in columns}
        for record in records
        if start <= record["open_time"] <= end
    ]


def _view_record(
    *,
    store: OHLCVParquetStore,
    storage_dir: Path,
    source: str,
    symbol: str,
    timeframe: str,
    lookback: int,
    config_base: Path,
) -> dict[str, Any]:
    records = store.read_records(source=source, symbol=symbol, timeframe=timeframe)
    window = records[-lookback:] if records else []
    row_count = len(window)
    latest = window[-1]["open_time"] if window else None
    insufficient = row_count < lookback
    warnings = []
    if insufficient:
        warnings.append(
            f"{source} {symbol} {timeframe} has {row_count} OHLCV rows, "
            f"below configured lookback {lookback}."
        )

    return {
        "view_id": _view_id(source, symbol, timeframe, latest),
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "requested_lookback": lookback,
        "input_window_start": window[0]["open_time"] if window else None,
        "input_window_end": latest,
        "latest_candle_time": latest,
        "row_count": row_count,
        "storage_ref": _storage_ref(storage_dir, source, symbol, timeframe, config_base),
        "included_columns": list(VIEW_INCLUDED_COLUMNS),
        "insufficient_data": insufficient,
        "warnings": warnings,
    }


def _view_id(source: str, symbol: str, timeframe: str, latest: str | None) -> str:
    suffix = latest or "missing"
    return f"ohlcv_view:{source}:{symbol}:{timeframe}:{suffix}"


def _storage_ref(
    storage_dir: Path,
    source: str,
    symbol: str,
    timeframe: str,
    config_base: Path,
) -> str:
    group_dir = storage_dir / f"source={source}" / f"symbol={symbol}" / f"timeframe={timeframe}"
    return display_path(group_dir, base=config_base)


def _sync_state_artifact(storage_dir: Path, run: RunContext) -> str:
    artifact = run.manifest.get("artifacts", {}).get("ohlcv_sync_state")
    if isinstance(artifact, str) and artifact:
        return artifact
    return display_path(storage_dir.parent / "metadata" / "ohlcv_sync_state.json", base=run.config_path.parent)


def _storage_dir(ohlcv: dict[str, Any], config_path: Path) -> Path:
    storage_dir = Path(str(ohlcv["storage_dir"]))
    if storage_dir.is_absolute():
        return storage_dir
    return config_path.parent / storage_dir


def _configured_symbols(market: dict[str, Any]) -> list[str]:
    return [str(symbol) for symbol in market.get("symbols", [])]


def _configured_timeframes(ohlcv: dict[str, Any]) -> list[str]:
    return [str(timeframe) for timeframe in ohlcv.get("timeframes", [])]


def _configured_lookback(ohlcv: dict[str, Any], timeframe: str) -> int:
    return int(ohlcv["lookback"][timeframe])


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
