from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from threading import Event, Thread
from typing import Any
from urllib.parse import quote, urlparse

from halpha.data.collection_coverage import read_collection_coverage_state, write_collection_coverage_state
from halpha.live.config import LiveSettings, load_live_settings
from halpha.live.scheduler import LiveCollectionTarget, build_live_collection_targets
from halpha.live.stream_state import LiveStreamStateRepository
from halpha.market.ohlcv_quality import OHLCV_TIMEFRAME_DURATIONS, ohlcv_next_open_time
from halpha.market.ohlcv_store import OHLCVParquetStore, OHLCVStoreError
from halpha.runtime.public_http import market_proxy_url_from_market, normalize_public_proxy_url
from halpha.runtime.public_rate_limits import sanitize_public_api_error_message
from halpha.storage import resolve_runtime_path


BINANCE_SPOT_STREAM_ENDPOINT = "wss://data-stream.binance.vision/stream?streams={streams}"
BINANCE_USDM_STREAM_ENDPOINT = "wss://fstream.binance.com/market/stream?streams={streams}"
SUPPORTED_STREAM_SOURCES = frozenset({"binance", "binance_spot", "binance_usdm"})
OHLCV_SYNC_STATE_ARTIFACT = "data/market/metadata/ohlcv_sync_state.json"
COVERAGE_STATE_ARTIFACT = "data/research/metadata/collection_coverage_state.json"


class LiveOHLCVStreamError(Exception):
    pass


class LiveOHLCVStreamReconnect(LiveOHLCVStreamError):
    pass


@dataclass(frozen=True)
class LiveOHLCVStreamTarget:
    target_key: str
    source: str
    symbol: str
    timeframe: str
    stream_name: str
    target: dict[str, Any]


class LiveOHLCVStreamService:
    def __init__(
        self,
        config: dict[str, Any],
        *,
        config_path: Path,
        stop_event: Event,
        state_repository: LiveStreamStateRepository | None = None,
    ) -> None:
        self.config = config
        self.config_path = Path(config_path)
        self.stop_event = stop_event
        self.state_repository = state_repository or LiveStreamStateRepository(self.config_path)
        self._threads: list[Thread] = []

    def start(self) -> None:
        settings = load_live_settings(self.config)
        targets = build_ohlcv_stream_targets(self.config, settings)
        if not settings.enabled or not settings.ohlcv_stream.enabled or not targets:
            self._record_disabled_targets(targets, settings=settings)
            return
        unsupported = [target for target in targets if target.source not in SUPPORTED_STREAM_SOURCES]
        for target in unsupported:
            self._upsert_target_state(
                target,
                status="unsupported",
                warnings=[f"{target.source} does not expose an implemented Live OHLCV WebSocket stream."],
            )
        supported = [target for target in targets if target.source in SUPPORTED_STREAM_SOURCES]
        if not supported:
            return
        try:
            _import_websocket()
        except LiveOHLCVStreamError as exc:
            for target in supported:
                self._upsert_target_state(target, status="dependency_missing", errors=[str(exc)])
            return
        for source, group_targets in _targets_by_source(supported).items():
            thread = Thread(
                target=self._run_source_loop,
                args=(source, group_targets, settings),
                name=f"halpha-live-ohlcv-{source}",
                daemon=True,
            )
            thread.start()
            self._threads.append(thread)

    def stop(self, *, timeout: float = 3.0) -> None:
        self.stop_event.set()
        for thread in self._threads:
            thread.join(timeout=timeout)

    def _run_source_loop(
        self,
        source: str,
        targets: list[LiveOHLCVStreamTarget],
        settings: LiveSettings,
    ) -> None:
        reconnect_count = 0
        while not self.stop_event.is_set():
            delay = min(
                settings.ohlcv_stream.reconnect_max_seconds,
                settings.ohlcv_stream.reconnect_initial_seconds * (2 ** min(reconnect_count, 6)),
            )
            try:
                self._consume_source_stream(source, targets, reconnect_count=reconnect_count)
                reconnect_count = 0
            except LiveOHLCVStreamReconnect as exc:
                reconnect_count += 1
                self._record_group_reconnect(targets, reconnect_count=reconnect_count, delay_seconds=delay, error=str(exc))
            except Exception as exc:
                reconnect_count += 1
                self._record_group_reconnect(targets, reconnect_count=reconnect_count, delay_seconds=delay, error=str(exc))
            if self.stop_event.wait(delay):
                break

    def _consume_source_stream(
        self,
        source: str,
        targets: list[LiveOHLCVStreamTarget],
        *,
        reconnect_count: int,
    ) -> None:
        websocket_module = _import_websocket()
        url = ohlcv_stream_url(source, [target.stream_name for target in targets])
        now_text = _utc_now()
        for target in targets:
            self._upsert_target_state(
                target,
                status="connecting",
                endpoint=_safe_endpoint_label(source),
                connected_at=None,
                reconnect_count=reconnect_count,
            )
        ws = None
        try:
            ws = websocket_module.create_connection(url, timeout=30, **_proxy_kwargs(self.config))
            connected_at = _utc_now()
            for target in targets:
                self._upsert_target_state(
                    target,
                    status="connected",
                    endpoint=_safe_endpoint_label(source),
                    connected_at=connected_at,
                    reconnect_count=reconnect_count,
                    backfill_required=True,
                    backfill_since=_initial_backfill_since(target, self.config, self.config_path),
                )
            targets_by_stream = {target.stream_name: target for target in targets}
            while not self.stop_event.is_set():
                raw_message = ws.recv()
                if raw_message is None:
                    continue
                event = parse_ohlcv_stream_message(raw_message)
                if event.get("event_type") == "serverShutdown":
                    raise LiveOHLCVStreamReconnect("Binance WebSocket server shutdown event received.")
                stream_name = str(event.get("stream") or "").lower()
                target = targets_by_stream.get(stream_name)
                if target is None:
                    continue
                record = binance_kline_event_to_ohlcv_record(
                    event,
                    source=target.source,
                    symbol=target.symbol,
                    timeframe=target.timeframe,
                )
                self._upsert_target_state(
                    target,
                    status="streaming",
                    endpoint=_safe_endpoint_label(source),
                    connected_at=connected_at,
                    last_event_at=_format_event_time(event.get("event_time")),
                    reconnect_count=reconnect_count,
                )
                if record is None:
                    continue
                self._write_closed_candle(record)
                self._upsert_target_state(
                    target,
                    status="available",
                    endpoint=_safe_endpoint_label(source),
                    connected_at=connected_at,
                    last_event_at=record["fetched_at"],
                    last_closed_candle_at=record["open_time"],
                    reconnect_count=reconnect_count,
                    backfill_required=False,
                    backfill_since=None,
                )
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass
            for target in targets:
                previous = self.state_repository.get_state(target.target_key) or {}
                if previous.get("status") in {"available", "streaming", "connected"}:
                    self._upsert_target_state(
                        target,
                        status="reconnecting",
                        endpoint=_safe_endpoint_label(source),
                        connected_at=previous.get("connected_at") if isinstance(previous.get("connected_at"), str) else now_text,
                        last_event_at=previous.get("last_event_at") if isinstance(previous.get("last_event_at"), str) else None,
                        last_closed_candle_at=previous.get("last_closed_candle_at")
                        if isinstance(previous.get("last_closed_candle_at"), str)
                        else None,
                        backfill_required=True,
                        backfill_since=_next_backfill_since(previous.get("last_closed_candle_at"), target.timeframe),
                    )

    def _write_closed_candle(self, record: dict[str, Any]) -> None:
        market = self.config.get("market") if isinstance(self.config.get("market"), dict) else {}
        ohlcv = market.get("ohlcv") if isinstance(market.get("ohlcv"), dict) else {}
        storage_dir = resolve_runtime_path(Path(str(ohlcv["storage_dir"])), config_path=self.config_path)
        store = OHLCVParquetStore(storage_dir)
        store.write_records([record])
        _write_stream_coverage_record(record, config_path=self.config_path)

    def _record_disabled_targets(self, targets: list[LiveOHLCVStreamTarget], *, settings: LiveSettings) -> None:
        for target in targets:
            self._upsert_target_state(
                target,
                status="disabled",
                warnings=[] if settings.enabled else ["Live is disabled."],
            )

    def _record_group_reconnect(
        self,
        targets: list[LiveOHLCVStreamTarget],
        *,
        reconnect_count: int,
        delay_seconds: int,
        error: str,
    ) -> None:
        next_reconnect_at = _format_utc(datetime.now(timezone.utc) + timedelta(seconds=delay_seconds))
        safe_error = _safe_error(error)
        for target in targets:
            previous = self.state_repository.get_state(target.target_key) or {}
            self._upsert_target_state(
                target,
                status="reconnecting",
                endpoint=_safe_endpoint_label(target.source),
                connected_at=previous.get("connected_at") if isinstance(previous.get("connected_at"), str) else None,
                last_event_at=previous.get("last_event_at") if isinstance(previous.get("last_event_at"), str) else None,
                last_closed_candle_at=previous.get("last_closed_candle_at")
                if isinstance(previous.get("last_closed_candle_at"), str)
                else None,
                backfill_required=True,
                backfill_since=_next_backfill_since(previous.get("last_closed_candle_at"), target.timeframe),
                next_reconnect_at=next_reconnect_at,
                reconnect_count=reconnect_count,
                warnings=["Live OHLCV WebSocket disconnected; REST backfill is required."],
                errors=[safe_error] if safe_error else [],
            )

    def _upsert_target_state(
        self,
        target: LiveOHLCVStreamTarget,
        *,
        status: str,
        endpoint: str | None = None,
        connected_at: str | None = None,
        last_event_at: str | None = None,
        last_closed_candle_at: str | None = None,
        backfill_required: bool | None = None,
        backfill_since: str | None = None,
        next_reconnect_at: str | None = None,
        reconnect_count: int | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
    ) -> dict[str, Any]:
        previous = self.state_repository.get_state(target.target_key) or {}
        state = {
            **previous,
            "target_key": target.target_key,
            "data_type": "ohlcv",
            "target": target.target,
            "enabled": True,
            "transport": "websocket",
            "status": status,
            "stream_name": target.stream_name,
            "endpoint": endpoint or previous.get("endpoint"),
            "connected_at": connected_at if connected_at is not None else previous.get("connected_at"),
            "last_event_at": last_event_at if last_event_at is not None else previous.get("last_event_at"),
            "last_closed_candle_at": last_closed_candle_at
            if last_closed_candle_at is not None
            else previous.get("last_closed_candle_at"),
            "backfill_required": backfill_required
            if backfill_required is not None
            else previous.get("backfill_required") is True,
            "backfill_since": backfill_since if backfill_since is not None else previous.get("backfill_since"),
            "next_reconnect_at": next_reconnect_at if next_reconnect_at is not None else previous.get("next_reconnect_at"),
            "reconnect_count": reconnect_count if reconnect_count is not None else previous.get("reconnect_count", 0),
            "warnings": warnings if warnings is not None else previous.get("warnings", []),
            "errors": errors if errors is not None else previous.get("errors", []),
            "updated_at": _utc_now(),
        }
        return self.state_repository.upsert_state(state)


def build_ohlcv_stream_targets(config: dict[str, Any], settings: LiveSettings | None = None) -> list[LiveOHLCVStreamTarget]:
    settings = settings or load_live_settings(config)
    if not settings.enabled or not settings.collections["ohlcv"].enabled:
        return []
    targets: list[LiveOHLCVStreamTarget] = []
    for target in build_live_collection_targets(config, settings):
        if target.data_type != "ohlcv" or target.errors:
            continue
        stream_target = _stream_target_from_collection_target(target)
        if stream_target is not None:
            targets.append(stream_target)
    return targets


def ohlcv_stream_url(source: str, stream_names: list[str]) -> str:
    names = sorted({name.lower() for name in stream_names if name})
    if not names:
        raise LiveOHLCVStreamError("OHLCV WebSocket stream URL requires at least one stream name.")
    streams = "/".join(quote(name, safe="@_") for name in names)
    if source in {"binance", "binance_spot"}:
        return BINANCE_SPOT_STREAM_ENDPOINT.format(streams=streams)
    if source == "binance_usdm":
        return BINANCE_USDM_STREAM_ENDPOINT.format(streams=streams)
    raise LiveOHLCVStreamError(f"{source} does not expose an implemented Live OHLCV WebSocket stream.")


def parse_ohlcv_stream_message(raw_message: str | bytes | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw_message, bytes):
        raw_message = raw_message.decode("utf-8")
    if isinstance(raw_message, str):
        try:
            payload = json.loads(raw_message)
        except json.JSONDecodeError as exc:
            raise LiveOHLCVStreamError("WebSocket message is not valid JSON.") from exc
    elif isinstance(raw_message, dict):
        payload = raw_message
    else:
        raise LiveOHLCVStreamError("WebSocket message must be JSON text or a mapping.")
    if not isinstance(payload, dict):
        raise LiveOHLCVStreamError("WebSocket message payload must be a mapping.")
    stream = payload.get("stream")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        raise LiveOHLCVStreamError("WebSocket message data must be a mapping.")
    event_type = data.get("e")
    result = dict(data)
    result["stream"] = str(stream or _stream_name_from_event(data)).lower()
    result["event_type"] = event_type
    result["event_time"] = data.get("E")
    return result


def binance_kline_event_to_ohlcv_record(
    event: dict[str, Any],
    *,
    source: str,
    symbol: str,
    timeframe: str,
) -> dict[str, Any] | None:
    if event.get("event_type") != "kline":
        return None
    kline = event.get("k")
    if not isinstance(kline, dict):
        raise LiveOHLCVStreamError("kline event missing kline payload.")
    if kline.get("x") is not True:
        return None
    event_symbol = str(kline.get("s") or event.get("s") or "").upper()
    if event_symbol != symbol.upper():
        raise LiveOHLCVStreamError(f"kline symbol mismatch: expected {symbol}, received {event_symbol}.")
    event_interval = str(kline.get("i") or "")
    if event_interval != timeframe:
        raise LiveOHLCVStreamError(f"kline interval mismatch: expected {timeframe}, received {event_interval}.")
    fetched_at = _format_event_time(event.get("event_time")) or _utc_now()
    return {
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "open_time": _timestamp_from_millis(_int(kline.get("t"), "k.t")),
        "open": _number(kline.get("o"), "k.o"),
        "high": _number(kline.get("h"), "k.h"),
        "low": _number(kline.get("l"), "k.l"),
        "close": _number(kline.get("c"), "k.c"),
        "volume": _number(kline.get("v"), "k.v"),
        "fetched_at": fetched_at,
    }


def stream_state_is_fresh(state: dict[str, Any] | None, *, now: datetime, stale_after_seconds: int) -> bool:
    if not isinstance(state, dict):
        return False
    if state.get("status") not in {"connected", "streaming", "available"}:
        return False
    if state.get("backfill_required") is True:
        return False
    last_event_at = _parse_utc(state.get("last_event_at"))
    if last_event_at is None:
        last_event_at = _parse_utc(state.get("updated_at"))
    if last_event_at is None:
        return False
    return now.astimezone(timezone.utc) - last_event_at <= timedelta(seconds=stale_after_seconds)


def stream_state_requires_backfill(state: dict[str, Any] | None, *, now: datetime, stale_after_seconds: int) -> bool:
    if not isinstance(state, dict):
        return False
    if state.get("backfill_required") is True:
        return True
    if state.get("status") in {"dependency_missing", "unsupported", "disabled"}:
        return False
    return not stream_state_is_fresh(state, now=now, stale_after_seconds=stale_after_seconds)


def _stream_target_from_collection_target(target: LiveCollectionTarget) -> LiveOHLCVStreamTarget | None:
    source = str(target.target.get("source") or "")
    symbol = str(target.target.get("symbol") or "")
    timeframe = str(target.target.get("timeframe") or "")
    if not source or not symbol or not timeframe:
        return None
    return LiveOHLCVStreamTarget(
        target_key=target.target_key,
        source=source,
        symbol=symbol,
        timeframe=timeframe,
        stream_name=f"{symbol.lower()}@kline_{timeframe}",
        target=dict(target.target),
    )


def _targets_by_source(targets: list[LiveOHLCVStreamTarget]) -> dict[str, list[LiveOHLCVStreamTarget]]:
    groups: dict[str, list[LiveOHLCVStreamTarget]] = {}
    for target in targets:
        groups.setdefault(target.source, []).append(target)
    return groups


def _import_websocket() -> Any:
    try:
        import websocket  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise LiveOHLCVStreamError(
            "websocket-client is required for Live OHLCV WebSocket streams; install project dependencies."
        ) from exc
    return websocket


def _proxy_kwargs(config: dict[str, Any]) -> dict[str, Any]:
    market = config.get("market") if isinstance(config.get("market"), dict) else {}
    try:
        proxy_url = market_proxy_url_from_market(market, error_factory=LiveOHLCVStreamError)
        proxy_url = normalize_public_proxy_url(proxy_url, error_factory=LiveOHLCVStreamError)
    except LiveOHLCVStreamError:
        return {}
    if proxy_url is None:
        return {}
    parsed = urlparse(proxy_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return {}
    kwargs: dict[str, Any] = {
        "http_proxy_host": parsed.hostname,
        "http_proxy_port": parsed.port,
        "proxy_type": "http",
    }
    if parsed.username:
        kwargs["http_proxy_auth"] = (parsed.username, parsed.password or "")
    return kwargs


def _write_stream_coverage_record(record: dict[str, Any], *, config_path: Path) -> None:
    state = read_collection_coverage_state(config_path)
    existing = [item for item in state.get("records", []) if isinstance(item, dict)]
    opened_at = _parse_utc(record["open_time"])
    if opened_at is None:
        return
    range_end = ohlcv_next_open_time(opened_at, str(record["timeframe"]))
    timestamp = record["fetched_at"]
    coverage = {
        "data_type": "ohlcv",
        "source": record["source"],
        "identity": {"symbol": record["symbol"], "timeframe": record["timeframe"]},
        "range_start": record["open_time"],
        "range_end": _format_utc(range_end),
        "status": "collected",
        "record_count": 1,
        "attempt_count": 1,
        "latest_attempt_at": timestamp,
        "latest_success_at": timestamp,
        "updated_at": timestamp,
        "coverage_method": "ohlcv_websocket_stream",
        "source_artifacts": [OHLCV_SYNC_STATE_ARTIFACT],
        "warnings": [],
        "errors": [],
    }
    write_collection_coverage_state(
        config_path,
        [*existing, coverage],
        now=timestamp,
        source_artifacts=[COVERAGE_STATE_ARTIFACT, OHLCV_SYNC_STATE_ARTIFACT],
    )


def _initial_backfill_since(target: LiveOHLCVStreamTarget, config: dict[str, Any], config_path: Path) -> str:
    existing_latest = _latest_stored_open_time(target, config, config_path)
    if existing_latest is not None:
        next_time = _next_backfill_since(existing_latest, target.timeframe)
        if next_time is not None:
            return next_time
    duration = OHLCV_TIMEFRAME_DURATIONS.get(target.timeframe, timedelta(minutes=1))
    return _format_utc(datetime.now(timezone.utc) - max(duration, timedelta(minutes=1)))


def _latest_stored_open_time(target: LiveOHLCVStreamTarget, config: dict[str, Any], config_path: Path) -> str | None:
    market = config.get("market") if isinstance(config.get("market"), dict) else {}
    ohlcv = market.get("ohlcv") if isinstance(market.get("ohlcv"), dict) else {}
    try:
        storage_dir = resolve_runtime_path(Path(str(ohlcv["storage_dir"])), config_path=config_path)
        records = OHLCVParquetStore(storage_dir).read_records(
            source=target.source,
            symbol=target.symbol,
            timeframe=target.timeframe,
        )
    except (KeyError, OHLCVStoreError):
        return None
    return str(records[-1]["open_time"]) if records else None


def _next_backfill_since(value: Any, timeframe: str) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    parsed = _parse_utc(value)
    if parsed is None:
        return None
    try:
        return _format_utc(ohlcv_next_open_time(parsed, timeframe))
    except KeyError:
        return None


def _stream_name_from_event(data: dict[str, Any]) -> str:
    if data.get("e") == "kline" and isinstance(data.get("k"), dict):
        kline = data["k"]
        return f"{str(kline.get('s') or '').lower()}@kline_{str(kline.get('i') or '')}"
    if data.get("e") == "serverShutdown":
        return "!serverShutdown"
    return ""


def _format_event_time(value: Any) -> str | None:
    if not isinstance(value, int) or isinstance(value, bool):
        return None
    return _timestamp_from_millis(value)


def _timestamp_from_millis(value: int) -> str:
    return _format_utc(datetime.fromtimestamp(value / 1000, timezone.utc))


def _int(value: Any, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise LiveOHLCVStreamError(f"{path} must be an integer millisecond timestamp.")
    return value


def _number(value: Any, path: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise LiveOHLCVStreamError(f"{path} must be numeric.") from exc
    if parsed != parsed:
        raise LiveOHLCVStreamError(f"{path} must be finite.")
    return parsed


def _safe_endpoint_label(source: str) -> str:
    if source in {"binance", "binance_spot"}:
        return "binance_spot_public_market_stream"
    if source == "binance_usdm":
        return "binance_usdm_market_stream"
    return f"{source}_websocket_stream"


def _safe_error(value: str) -> str:
    text = sanitize_public_api_error_message(str(value or "")) or ""
    text = re.sub(r"\bwss?://[^\s]+", "<redacted-url>", text)
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme and parsed.netloc:
        return "Live OHLCV WebSocket connection failed."
    return text[:240]


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _utc_now() -> str:
    return _format_utc(datetime.now(timezone.utc))
