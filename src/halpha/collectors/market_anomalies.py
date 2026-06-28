from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from json import JSONDecodeError
from typing import Any

from halpha.market.ohlcv_store import OHLCVParquetStore, OHLCVStoreError
from halpha.runtime.pipeline_contracts import RunContext
from halpha.storage import display_path, resolve_runtime_path, runtime_root, write_json


STAGE_NAME = "collect_market_anomalies_data"
MARKET_ANOMALIES_ARTIFACT = "raw/market_anomalies.json"
DEFAULT_PRICE_MOVE_THRESHOLD_PCT = 5.0
DEFAULT_VOLUME_SPIKE_MULTIPLIER = 3.0
DEFAULT_LOOKBACK_DAYS = 30
DEFAULT_VOLUME_LOOKBACK = 20
SUPPORTED_SOURCE_KINDS = {"external_intel", "halpha_rule"}


def collect_market_anomalies_data(config: dict[str, Any], run: RunContext) -> list[str]:
    anomalies = _anomalies_config(config)
    if not anomalies.get("enabled"):
        _record_manifest_counts(run, items=[], availability=[], errors=[])
        return []

    collected_at = _format_utc(None)
    requested_start, requested_end = _collection_window(anomalies, collected_at=collected_at)
    raw = _raw_artifact(collected_at, requested_start=requested_start, requested_end=requested_end)
    source_kinds = _source_kinds(anomalies)
    if "external_intel" in source_kinds:
        _collect_external_json(anomalies, raw)
    if "halpha_rule" in source_kinds:
        _collect_halpha_rule_anomalies(config, anomalies, raw, collected_at=collected_at)

    artifact_path = run.raw_dir / "market_anomalies.json"
    write_json(artifact_path, raw)
    run.manifest["artifacts"]["raw_market_anomalies"] = MARKET_ANOMALIES_ARTIFACT
    _record_manifest_counts(run, items=raw["items"], availability=raw["availability"], errors=raw["errors"])
    return [MARKET_ANOMALIES_ARTIFACT]


def _collect_external_json(anomalies: dict[str, Any], raw: dict[str, Any]) -> None:
    path_value = anomalies.get("external_json_path")
    if not isinstance(path_value, str) or not path_value.strip():
        raw["availability"].append(
            _availability_record(
                source_kind="external_intel",
                source="external_json",
                status="unavailable",
                reason="market.anomalies.external_json_path is not configured.",
            )
        )
        return
    path = resolve_runtime_path(path_value, config_path=None)
    source_ref = display_path(path, base=runtime_root(None))
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raw["availability"].append(
            _availability_record(
                source_kind="external_intel",
                source="external_json",
                status="unavailable",
                reason=f"{source_ref} was not found.",
            )
        )
        return
    except (OSError, JSONDecodeError) as exc:
        raw["errors"].append(_collector_error(source="external_json", message=f"{source_ref} could not be read: {exc}"))
        raw["availability"].append(
            _availability_record(
                source_kind="external_intel",
                source="external_json",
                status="failed",
                reason=f"{source_ref} could not be read.",
            )
        )
        return

    items = loaded.get("items") if isinstance(loaded, dict) else loaded
    if not isinstance(items, list):
        raw["errors"].append(_collector_error(source="external_json", message="external market anomaly JSON must be a list or an object with items."))
        raw["availability"].append(
            _availability_record(source_kind="external_intel", source="external_json", status="failed")
        )
        return

    before_count = len(raw["items"])
    for item in items:
        if not isinstance(item, dict):
            raw["warnings"].append("external market anomaly item is not a JSON object.")
            continue
        normalized, warning = _external_item(item, source_ref=source_ref, collected_at=raw["collected_at"])
        if warning:
            raw["warnings"].append(warning)
            continue
        raw["items"].append(normalized)
    record_count = len(raw["items"]) - before_count
    raw["availability"].append(
        _availability_record(
            source_kind="external_intel",
            source="external_json",
            status="succeeded" if record_count else "no_data",
            record_count=record_count,
        )
    )


def _collect_halpha_rule_anomalies(
    config: dict[str, Any],
    anomalies: dict[str, Any],
    raw: dict[str, Any],
    *,
    collected_at: str,
) -> None:
    market = _market_config(config)
    ohlcv = market.get("ohlcv") if isinstance(market.get("ohlcv"), dict) else {}
    storage_dir = ohlcv.get("storage_dir")
    if not isinstance(storage_dir, str) or not storage_dir.strip():
        raw["availability"].append(
            _availability_record(
                source_kind="halpha_rule",
                source="halpha_monitor_rules",
                status="unavailable",
                reason="market.ohlcv.storage_dir is not configured.",
            )
        )
        return
    source = _ohlcv_source(market, ohlcv, anomalies)
    symbols = _symbols(market, anomalies)
    timeframes = _timeframes(ohlcv, anomalies)
    requested_start = _parse_utc(raw["requested_start"])
    requested_end = _parse_utc(raw["requested_end"])
    threshold_pct = _positive_float(anomalies.get("price_move_threshold_pct"), DEFAULT_PRICE_MOVE_THRESHOLD_PCT)
    volume_multiplier = _positive_float(anomalies.get("volume_spike_multiplier"), DEFAULT_VOLUME_SPIKE_MULTIPLIER)
    store = OHLCVParquetStore(resolve_runtime_path(storage_dir))

    request_count = 0
    error_count = 0
    before_count = len(raw["items"])
    for symbol in symbols:
        for timeframe in timeframes:
            request_count += 1
            try:
                records = store.read_records(source=source, symbol=symbol, timeframe=timeframe)
            except OHLCVStoreError as exc:
                error_count += 1
                raw["errors"].append(
                    _collector_error(
                        source="halpha_monitor_rules",
                        symbol=symbol,
                        timeframe=timeframe,
                        message=str(exc),
                    )
                )
                continue
            selected = _records_in_window(records, requested_start=requested_start, requested_end=requested_end)
            raw["items"].extend(
                _price_move_items(
                    selected,
                    threshold_pct=threshold_pct,
                    collected_at=collected_at,
                )
            )
            raw["items"].extend(
                _volume_spike_items(
                    selected,
                    multiplier=volume_multiplier,
                    collected_at=collected_at,
                )
            )

    record_count = len(raw["items"]) - before_count
    raw["availability"].append(
        _availability_record(
            source_kind="halpha_rule",
            source="halpha_monitor_rules",
            status="partial" if record_count and error_count else "failed" if error_count else "succeeded" if record_count else "no_data",
            record_count=record_count,
            request_count=request_count,
            error_count=error_count,
        )
    )


def _external_item(item: dict[str, Any], *, source_ref: str, collected_at: str) -> tuple[dict[str, Any], str | None]:
    observed_at = _first_text(item, "observed_at", "as_of", "time", "timestamp", "published_at")
    if not observed_at:
        return {}, "external market anomaly item is missing observed_at/as_of/time/timestamp."
    try:
        observed_at = _format_utc(observed_at)
    except ValueError:
        return {}, "external market anomaly item has an invalid observed_at timestamp."
    source = _first_text(item, "source", "source_name", default="external_json")
    data_class = _first_text(item, "data_class", "anomaly_type", "event_type", default="external_alert")
    symbol = _first_text(item, "symbol", "asset", default="MARKET")
    metric = _first_text(item, "metric", default=str(data_class))
    value = item.get("value")
    threshold = item.get("threshold")
    unit = _first_text(item, "unit", default="")
    direction = _first_text(item, "direction", default="unknown")
    title = _first_text(item, "title", "event_name", "name", default=f"{symbol} {data_class}")
    summary = _first_text(item, "summary", "description", "text", default="")
    metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
    units = item.get("units") if isinstance(item.get("units"), dict) else {}
    if value is not None:
        metrics = {**metrics, metric: value}
    if unit:
        units = {**units, metric: unit}
    record = {
        "anomaly_id": str(item.get("anomaly_id") or item.get("id") or _dedupe_key(symbol=symbol, data_class=data_class, observed_at=observed_at, metric=metric, direction=direction)),
        "source_kind": "external_intel",
        "source": source,
        "data_class": data_class,
        "symbol": symbol,
        "market_type": _first_text(item, "market_type", default="unknown"),
        "timeframe": _first_text(item, "timeframe", "period", default="event"),
        "observed_at": observed_at,
        "published_at": _optional_utc(_first_text(item, "published_at")),
        "collected_at": collected_at,
        "first_seen_at": collected_at,
        "last_seen_at": collected_at,
        "severity": _first_text(item, "severity", default="medium"),
        "direction": direction,
        "metric": metric,
        "value": value,
        "threshold": threshold,
        "unit": unit,
        "window_start": _optional_utc(_first_text(item, "window_start")),
        "window_end": _optional_utc(_first_text(item, "window_end")),
        "title": title,
        "summary": summary,
        "dedupe_key": str(item.get("dedupe_key") or _dedupe_key(symbol=symbol, data_class=data_class, observed_at=observed_at, metric=metric, direction=direction)),
        "metrics": metrics,
        "units": units,
        "raw_fields": dict(item),
        "warnings": _string_list(item.get("warnings")),
        "errors": _string_list(item.get("errors")),
        "source_artifacts": [source_ref],
    }
    return record, None


def _price_move_items(
    records: list[dict[str, Any]],
    *,
    threshold_pct: float,
    collected_at: str,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for record in records:
        if previous is None:
            previous = record
            continue
        previous_close = _float_value(previous.get("close"))
        close = _float_value(record.get("close"))
        if previous_close is None or previous_close == 0 or close is None:
            previous = record
            continue
        move_pct = (close - previous_close) / previous_close * 100.0
        if abs(move_pct) >= threshold_pct:
            direction = "up" if move_pct > 0 else "down"
            observed_at = str(record["open_time"])
            symbol = str(record["symbol"])
            timeframe = str(record["timeframe"])
            items.append(
                {
                    "anomaly_id": f"halpha_rule:{symbol}:{timeframe}:price_move:{observed_at}",
                    "source_kind": "halpha_rule",
                    "source": "halpha_monitor_rules",
                    "data_class": "price_move",
                    "symbol": symbol,
                    "market_type": "spot_or_derivatives",
                    "timeframe": timeframe,
                    "observed_at": observed_at,
                    "published_at": observed_at,
                    "collected_at": collected_at,
                    "first_seen_at": collected_at,
                    "last_seen_at": collected_at,
                    "severity": _severity(abs(move_pct), threshold_pct),
                    "direction": direction,
                    "metric": "close_return_pct",
                    "value": round(move_pct, 8),
                    "threshold": threshold_pct,
                    "unit": "percent",
                    "window_start": str(previous["open_time"]),
                    "window_end": observed_at,
                    "title": f"{symbol} {timeframe} close return {move_pct:.2f}%",
                    "summary": f"{symbol} {timeframe} close changed {move_pct:.2f}% from the previous candle.",
                    "dedupe_key": _dedupe_key(
                        symbol=symbol,
                        data_class="price_move",
                        observed_at=observed_at,
                        metric="close_return_pct",
                        direction=direction,
                    ),
                    "metrics": {
                        "close_return_pct": round(move_pct, 8),
                        "previous_close": previous_close,
                        "close": close,
                    },
                    "units": {
                        "close_return_pct": "percent",
                        "previous_close": "quote_asset",
                        "close": "quote_asset",
                    },
                    "raw_fields": {
                        "rule_name": "close_return_threshold",
                        "threshold_pct": threshold_pct,
                    },
                    "warnings": [],
                    "errors": [],
                    "source_artifacts": ["data/market/ohlcv"],
                }
            )
        previous = record
    return items


def _volume_spike_items(
    records: list[dict[str, Any]],
    *,
    multiplier: float,
    collected_at: str,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    previous_volumes: list[float] = []
    for index, record in enumerate(records):
        volume = _float_value(record.get("volume"))
        if volume is None:
            continue
        if len(previous_volumes) >= 3:
            baseline = sum(previous_volumes[-DEFAULT_VOLUME_LOOKBACK:]) / len(previous_volumes[-DEFAULT_VOLUME_LOOKBACK:])
            if baseline > 0:
                ratio = volume / baseline
                if ratio >= multiplier:
                    observed_at = str(record["open_time"])
                    symbol = str(record["symbol"])
                    timeframe = str(record["timeframe"])
                    items.append(
                        {
                            "anomaly_id": f"halpha_rule:{symbol}:{timeframe}:volume_spike:{observed_at}",
                            "source_kind": "halpha_rule",
                            "source": "halpha_monitor_rules",
                            "data_class": "volume_spike",
                            "symbol": symbol,
                            "market_type": "spot_or_derivatives",
                            "timeframe": timeframe,
                            "observed_at": observed_at,
                            "published_at": observed_at,
                            "collected_at": collected_at,
                            "first_seen_at": collected_at,
                            "last_seen_at": collected_at,
                            "severity": _severity(ratio, multiplier),
                            "direction": "up",
                            "metric": "volume_spike_multiplier",
                            "value": round(ratio, 8),
                            "threshold": multiplier,
                            "unit": "ratio",
                            "window_start": str(
                                records[max(0, index - len(previous_volumes[-DEFAULT_VOLUME_LOOKBACK:]))]["open_time"]
                            ),
                            "window_end": observed_at,
                            "title": f"{symbol} {timeframe} volume spike {ratio:.2f}x",
                            "summary": f"{symbol} {timeframe} volume was {ratio:.2f}x the recent candle average.",
                            "dedupe_key": _dedupe_key(
                                symbol=symbol,
                                data_class="volume_spike",
                                observed_at=observed_at,
                                metric="volume_spike_multiplier",
                                direction="up",
                            ),
                            "metrics": {
                                "volume_spike_multiplier": round(ratio, 8),
                                "volume": volume,
                                "average_volume": baseline,
                            },
                            "units": {
                                "volume_spike_multiplier": "ratio",
                                "volume": "base_asset",
                                "average_volume": "base_asset",
                            },
                            "raw_fields": {
                                "rule_name": "volume_spike_threshold",
                                "volume_spike_multiplier": multiplier,
                            },
                            "warnings": [],
                            "errors": [],
                            "source_artifacts": ["data/market/ohlcv"],
                        }
                    )
        previous_volumes.append(volume)
    return items


def _records_in_window(
    records: list[dict[str, Any]],
    *,
    requested_start: datetime,
    requested_end: datetime,
) -> list[dict[str, Any]]:
    selected = []
    for record in records:
        try:
            opened_at = _parse_utc(str(record.get("open_time") or ""))
        except ValueError:
            continue
        if requested_start <= opened_at < requested_end:
            selected.append(record)
    return sorted(selected, key=lambda item: str(item.get("open_time") or ""))


def _raw_artifact(collected_at: str, *, requested_start: str, requested_end: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "market_anomalies_raw",
        "collector": "market_anomalies",
        "collection_method": "configured_sources",
        "collected_at": collected_at,
        "requested_start": requested_start,
        "requested_end": requested_end,
        "items": [],
        "availability": [],
        "warnings": [],
        "errors": [],
    }


def _availability_record(
    *,
    source_kind: str,
    source: str,
    status: str,
    record_count: int = 0,
    request_count: int = 0,
    error_count: int = 0,
    reason: str | None = None,
) -> dict[str, Any]:
    record = {
        "source_kind": source_kind,
        "source": source,
        "status": status,
        "record_count": record_count,
        "request_count": request_count,
        "error_count": error_count,
    }
    if reason:
        record["reason"] = reason
    return record


def _record_manifest_counts(
    run: RunContext,
    *,
    items: list[dict[str, Any]],
    availability: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    counts = run.manifest.setdefault("counts", {})
    counts["market_anomaly_items"] = len(items)
    counts["market_anomaly_errors"] = len(errors)
    counts["market_anomaly_availability"] = len(availability)
    counts["market_anomaly_unavailable"] = sum(1 for item in availability if item.get("status") == "unavailable")
    counts["market_anomaly_no_data"] = sum(1 for item in availability if item.get("status") == "no_data")
    run.manifest["market_anomalies"] = {
        "status": "failed" if errors else "ok",
        "items": len(items),
        "availability_records": len(availability),
        "errors": len(errors),
    }


def _collection_window(anomalies: dict[str, Any], *, collected_at: str) -> tuple[str, str]:
    end = _optional_utc(anomalies.get("window_end")) or collected_at
    start = _optional_utc(anomalies.get("window_start"))
    if not start:
        end_dt = _parse_utc(end)
        lookback_days = _positive_int(anomalies.get("lookback_days"), DEFAULT_LOOKBACK_DAYS)
        start = (end_dt - timedelta(days=lookback_days)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return start, end


def _anomalies_config(config: dict[str, Any]) -> dict[str, Any]:
    market = _market_config(config)
    anomalies = market.get("anomalies")
    return anomalies if isinstance(anomalies, dict) else {}


def _market_config(config: dict[str, Any]) -> dict[str, Any]:
    market = config.get("market")
    return market if isinstance(market, dict) else {}


def _source_kinds(anomalies: dict[str, Any]) -> set[str]:
    configured = [str(item) for item in anomalies.get("source_kinds") or ["halpha_rule"] if isinstance(item, str)]
    selected = {item for item in configured if item in SUPPORTED_SOURCE_KINDS}
    return selected or {"halpha_rule"}


def _symbols(market: dict[str, Any], anomalies: dict[str, Any]) -> list[str]:
    values = anomalies.get("symbols") if isinstance(anomalies.get("symbols"), list) else market.get("symbols")
    return [str(item).strip() for item in values or [] if isinstance(item, str) and item.strip()]


def _timeframes(ohlcv: dict[str, Any], anomalies: dict[str, Any]) -> list[str]:
    values = anomalies.get("timeframes") if isinstance(anomalies.get("timeframes"), list) else ohlcv.get("timeframes")
    return [str(item).strip() for item in values or [] if isinstance(item, str) and item.strip()]


def _ohlcv_source(market: dict[str, Any], ohlcv: dict[str, Any], anomalies: dict[str, Any]) -> str:
    if isinstance(anomalies.get("ohlcv_source"), str) and str(anomalies["ohlcv_source"]).strip():
        return str(anomalies["ohlcv_source"]).strip()
    sources = ohlcv.get("sources") if isinstance(ohlcv.get("sources"), list) else []
    if sources and isinstance(sources[0], str) and sources[0].strip():
        return sources[0].strip()
    return str(market.get("source") or "").strip()


def _collector_error(
    *,
    source: str,
    message: str,
    symbol: str | None = None,
    timeframe: str | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {
        "source": source,
        "error_type": "market_anomaly_collection_error",
        "message": message,
    }
    if symbol:
        error["symbol"] = symbol
    if timeframe:
        error["timeframe"] = timeframe
    return error


def _dedupe_key(*, symbol: str, data_class: str, observed_at: str, metric: str, direction: str) -> str:
    return "|".join(
        [
            _key_part(symbol),
            _key_part(data_class),
            _key_part(observed_at),
            _key_part(metric),
            _key_part(direction),
        ]
    )


def _severity(value: float, threshold: float) -> str:
    if value >= threshold * 2:
        return "high"
    if value >= threshold * 1.25:
        return "medium"
    return "low"


def _first_text(data: dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return default


def _float_value(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _positive_float(value: Any, default: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or float(value) <= 0:
        return default
    return float(value)


def _positive_int(value: Any, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return default
    return value


def _optional_utc(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return _format_utc(value)


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        timestamp = value
    elif isinstance(value, str):
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("timestamp must be an ISO 8601 UTC string.") from exc
    else:
        raise ValueError("timestamp must be a datetime or ISO 8601 UTC string.")
    if timestamp.tzinfo is None:
        raise ValueError("timestamp must include a UTC offset.")
    return timestamp.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp must be an ISO 8601 UTC string.") from exc
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a UTC offset.")
    return parsed.astimezone(timezone.utc)


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value or [] if isinstance(item, str) and item.strip()]


def _key_part(value: str) -> str:
    return value.strip().lower().replace(" ", "_")
