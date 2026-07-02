from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from halpha.market.ohlcv_quality import ohlcv_next_open_time
from halpha.market.ohlcv_source import CCXTOHLCVSource, OHLCVSourceError
from halpha.market.ohlcv_store import OHLCVParquetStore, OHLCVStoreError
from halpha.runtime.pipeline_contracts import PipelineError, RunContext
from halpha.data.research_data_catalog import write_research_data_catalog
from halpha.storage import display_path, resolve_runtime_path, runtime_root


STAGE_NAME = "sync_ohlcv"
SYNC_SCHEMA_VERSION = 1
REQUEST_LIMIT_PADDING = 1


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


def sync_ohlcv_history(
    config: dict[str, Any],
    run: RunContext,
    *,
    source_factory: SourceFactory | None = None,
    now: datetime | str | None = None,
) -> list[str]:
    market = config.get("market", {})
    ohlcv = market.get("ohlcv")
    if not market.get("enabled") or not isinstance(ohlcv, dict):
        _record_skipped_sync(run, "market.ohlcv is not configured.")
        return write_research_data_catalog(config, run, now=now)

    storage_dir = _storage_dir(ohlcv, run.config_path)
    metadata_paths = _metadata_paths(storage_dir)
    base = runtime_root(run.config_path)
    artifacts = _artifact_paths(metadata_paths, base)
    store = OHLCVParquetStore(storage_dir, run_output_dir=run.run_dir.parent)
    factory = source_factory or (lambda source, proxy_url: _default_source_factory(source, proxy_url, run.config_path))
    source_name = str(market["source"])

    try:
        source = factory(source_name, _proxy_url(market))
    except Exception as exc:
        item_error = _error_item(
            source=source_name,
            symbol=None,
            timeframe=None,
            message=f"could not initialize OHLCV source {source_name}: {exc}",
        )
        summary = _sync_summary(
            source=source_name,
            storage_dir=storage_dir,
            artifacts=artifacts,
            items=[],
            warnings=[],
            errors=[item_error],
            config_base=base,
        )
        metadata_errors = _write_store_metadata(store, source=source_name)
        if metadata_errors:
            _add_summary_errors(summary, metadata_errors)
        _record_sync_summary(run, summary, artifacts)
        artifacts.update(_catalog_artifacts(config, run, now=now))
        raise _sync_failure(summary["errors"], artifacts) from exc

    items = []
    warnings: list[str] = []
    errors: list[dict[str, Any]] = []
    for symbol in _configured_symbols(market):
        for timeframe in _configured_timeframes(ohlcv):
            item = _sync_item(
                store=store,
                source=source,
                source_name=source_name,
                symbol=symbol,
                timeframe=timeframe,
                lookback=_configured_lookback(ohlcv, timeframe),
                now=now,
            )
            items.append(item)
            warnings.extend(item["warnings"])
            errors.extend(item["errors"])

    summary = _sync_summary(
        source=source_name,
        storage_dir=storage_dir,
        artifacts=artifacts,
        items=items,
        warnings=warnings,
        errors=errors,
        config_base=base,
    )
    metadata_errors = _write_store_metadata(store, source=source_name)
    if metadata_errors:
        _add_summary_errors(summary, metadata_errors)
    _record_sync_summary(run, summary, artifacts)
    artifacts.update(_catalog_artifacts(config, run, now=now))

    if summary["errors"]:
        raise _sync_failure(summary["errors"], artifacts)

    return list(artifacts.values())


def _sync_item(
    *,
    store: OHLCVParquetStore,
    source: OHLCVSourceClient,
    source_name: str,
    symbol: str,
    timeframe: str,
    lookback: int,
    now: datetime | str | None,
) -> dict[str, Any]:
    item_warnings: list[str] = []
    item_errors: list[dict[str, Any]] = []
    limit = lookback + REQUEST_LIMIT_PADDING
    existing_records: list[dict[str, Any]] = []
    before_count = 0
    latest_existing = None
    mode = "initial_backfill"
    since = None

    try:
        existing_records = store.read_records(source=source_name, symbol=symbol, timeframe=timeframe)
        before_count = len(existing_records)
        latest_existing = existing_records[-1]["open_time"] if existing_records else None
        mode = "incremental" if existing_records else "initial_backfill"
        since = _next_open_time(latest_existing, timeframe) if latest_existing is not None else None
        fetched_records = source.fetch_records(
            symbol=symbol,
            timeframe=timeframe,
            since=since,
            limit=limit,
            now=now,
        )
        records_to_store = _records_to_store(
            fetched_records,
            latest_existing=latest_existing,
            lookback=lookback,
        )
        store.write_records(records_to_store, update_metadata=False)
        after_records = store.read_records(source=source_name, symbol=symbol, timeframe=timeframe)
        stored_count = max(len(after_records) - before_count, 0)
        fetched_count = len(fetched_records)
        skipped_count = max(fetched_count - stored_count, 0)
        if mode == "initial_backfill" and len(after_records) < lookback:
            item_warnings.append(
                f"{source_name} {symbol} {timeframe} stored {len(after_records)} finalized candles, "
                f"below configured lookback {lookback}."
            )
        if mode == "incremental" and fetched_count >= limit:
            item_warnings.append(
                f"{source_name} {symbol} {timeframe} reached the configured sync request limit; "
                "additional finalized candles may remain missing."
            )
        status = "succeeded"
    except (OHLCVSourceError, OHLCVStoreError) as exc:
        after_records = existing_records
        fetched_count = 0
        stored_count = 0
        skipped_count = 0
        item_errors.append(
            _error_item(
                source=source_name,
                symbol=symbol,
                timeframe=timeframe,
                message=str(exc),
            )
        )
        status = "failed"

    return {
        "status": status,
        "mode": mode,
        "source": source_name,
        "symbol": symbol,
        "timeframe": timeframe,
        "configured_lookback": lookback,
        "existing_count": before_count,
        "requested_since_open_time": _format_optional_utc(since),
        "requested_limit": limit,
        "fetched_count": fetched_count,
        "stored_count": stored_count,
        "skipped_count": skipped_count,
        "stored_range": _stored_range(after_records),
        "latest_closed_candle": _latest_open_time(after_records),
        "warnings": item_warnings,
        "errors": item_errors,
    }


def _default_source_factory(
    source_name: str,
    proxy_url: str | None,
    config_path: Path | None = None,
) -> OHLCVSourceClient:
    return CCXTOHLCVSource(source_name, proxy_url=proxy_url, rate_limit_config_path=config_path)


def _record_skipped_sync(run: RunContext, reason: str) -> None:
    summary = {
        "schema_version": SYNC_SCHEMA_VERSION,
        "artifact_type": "ohlcv_sync",
        "status": "skipped",
        "source": None,
        "storage_dir": None,
        "metadata": {},
        "items": [],
        "totals": {
            "items": 0,
            "fetched_count": 0,
            "stored_count": 0,
            "skipped_count": 0,
            "error_count": 0,
        },
        "warnings": [reason],
        "errors": [],
    }
    run.manifest["ohlcv_sync"] = summary
    run.manifest["counts"]["ohlcv_sync_items"] = 0
    run.manifest["counts"]["ohlcv_records_fetched"] = 0
    run.manifest["counts"]["ohlcv_records_stored"] = 0
    run.manifest["counts"]["ohlcv_records_skipped"] = 0
    run.manifest["counts"]["ohlcv_sync_errors"] = 0


def _sync_summary(
    *,
    source: str,
    storage_dir: Path,
    artifacts: dict[str, str],
    items: list[dict[str, Any]],
    warnings: list[str],
    errors: list[dict[str, Any]],
    config_base: Path,
) -> dict[str, Any]:
    return {
        "schema_version": SYNC_SCHEMA_VERSION,
        "artifact_type": "ohlcv_sync",
        "status": "failed" if errors else "succeeded",
        "source": source,
        "storage_dir": display_path(storage_dir, base=config_base),
        "metadata": {
            "ohlcv_schema": artifacts["ohlcv_schema"],
            "ohlcv_sync_state": artifacts["ohlcv_sync_state"],
        },
        "items": items,
        "totals": {
            "items": len(items),
            "fetched_count": sum(item["fetched_count"] for item in items),
            "stored_count": sum(item["stored_count"] for item in items),
            "skipped_count": sum(item["skipped_count"] for item in items),
            "error_count": len(errors),
        },
        "warnings": _unique_sorted(warnings),
        "errors": errors,
    }


def _record_sync_summary(run: RunContext, summary: dict[str, Any], artifacts: dict[str, str]) -> None:
    run.manifest["ohlcv_sync"] = summary
    run.manifest["artifacts"]["ohlcv_schema"] = artifacts["ohlcv_schema"]
    run.manifest["artifacts"]["ohlcv_sync_state"] = artifacts["ohlcv_sync_state"]
    run.manifest["counts"]["ohlcv_sync_items"] = summary["totals"]["items"]
    run.manifest["counts"]["ohlcv_records_fetched"] = summary["totals"]["fetched_count"]
    run.manifest["counts"]["ohlcv_records_stored"] = summary["totals"]["stored_count"]
    run.manifest["counts"]["ohlcv_records_skipped"] = summary["totals"]["skipped_count"]
    run.manifest["counts"]["ohlcv_sync_errors"] = summary["totals"]["error_count"]


def _catalog_artifacts(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None,
) -> dict[str, str]:
    artifacts = write_research_data_catalog(config, run, now=now)
    return {"research_data_catalog": artifacts[0]} if artifacts else {}


def _write_store_metadata(store: OHLCVParquetStore, *, source: str | None) -> list[dict[str, Any]]:
    try:
        store.write_records([])
    except OHLCVStoreError as exc:
        return [_error_item(source=source, symbol=None, timeframe=None, message=str(exc))]
    return []


def _add_summary_errors(summary: dict[str, Any], errors: list[dict[str, Any]]) -> None:
    summary["status"] = "failed"
    summary["errors"].extend(errors)
    summary["totals"]["error_count"] = len(summary["errors"])


def _sync_failure(errors: list[dict[str, Any]], artifacts: dict[str, str]) -> PipelineError:
    messages = [
        error["message"]
        for error in errors
        if isinstance(error.get("message"), str) and error["message"]
    ]
    detail = "; ".join(messages[:3])
    if len(messages) > 3:
        detail = f"{detail}; ..."
    return PipelineError(
        f"ohlcv sync failed for {len(errors)} item(s): {detail}",
        stage=STAGE_NAME,
        exit_code=3,
        artifacts=list(artifacts.values()),
        error_details={"ohlcv_sync_errors": errors},
    )


def _records_to_store(
    records: list[dict[str, Any]],
    *,
    latest_existing: str | None,
    lookback: int,
) -> list[dict[str, Any]]:
    filtered = [
        record
        for record in _sort_records(records)
        if latest_existing is None or record["open_time"] > latest_existing
    ]
    if latest_existing is None:
        return filtered[-lookback:]
    return filtered


def _storage_dir(ohlcv: dict[str, Any], config_path: Path) -> Path:
    storage_dir = Path(str(ohlcv["storage_dir"]))
    return resolve_runtime_path(storage_dir, config_path=config_path)


def _metadata_paths(storage_dir: Path) -> dict[str, Path]:
    metadata_dir = storage_dir.parent / "metadata"
    return {
        "ohlcv_schema": metadata_dir / "ohlcv_schema.json",
        "ohlcv_sync_state": metadata_dir / "ohlcv_sync_state.json",
    }


def _artifact_paths(paths: dict[str, Path], config_base: Path) -> dict[str, str]:
    return {name: display_path(path, base=config_base) for name, path in paths.items()}


def _configured_symbols(market: dict[str, Any]) -> list[str]:
    return [str(symbol) for symbol in market.get("symbols", [])]


def _configured_timeframes(ohlcv: dict[str, Any]) -> list[str]:
    return [str(timeframe) for timeframe in ohlcv.get("timeframes", [])]


def _configured_lookback(ohlcv: dict[str, Any], timeframe: str) -> int:
    return int(ohlcv["lookback"][timeframe])


def _proxy_url(market: dict[str, Any]) -> str | None:
    proxy = market.get("proxy")
    if not isinstance(proxy, dict) or proxy.get("enabled") is not True:
        return None
    value = proxy.get("url")
    if not isinstance(value, str):
        return None
    return value


def _stored_range(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not records:
        return None
    return {
        "earliest_open_time": records[0]["open_time"],
        "latest_open_time": records[-1]["open_time"],
        "row_count": len(records),
    }


def _latest_open_time(records: list[dict[str, Any]]) -> str | None:
    if not records:
        return None
    return str(records[-1]["open_time"])


def _next_open_time(open_time: str, timeframe: str) -> datetime:
    opened_at = _parse_utc(open_time)
    return ohlcv_next_open_time(opened_at, timeframe)


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def _format_optional_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sort_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        records,
        key=lambda record: (
            record["source"],
            record["symbol"],
            record["timeframe"],
            record["open_time"],
        ),
    )


def _error_item(
    *,
    source: str | None,
    symbol: str | None,
    timeframe: str | None,
    message: str,
) -> dict[str, Any]:
    return {
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "message": message,
    }


def _unique_sorted(values: list[str]) -> list[str]:
    return sorted(set(values))
