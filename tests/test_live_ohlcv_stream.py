from __future__ import annotations

import json
from pathlib import Path

from halpha.live.config import load_live_settings
from halpha.live.ohlcv_stream import (
    binance_kline_event_to_ohlcv_record,
    build_ohlcv_stream_targets,
    ohlcv_stream_url,
    parse_ohlcv_stream_message,
)
from halpha.live.stream_state import LiveStreamStateRepository


def test_binance_kline_stream_url_uses_routed_usdm_market_endpoint() -> None:
    url = ohlcv_stream_url("binance_usdm", ["btcusdt@kline_4h", "btcusdt@kline_1h"])

    assert url == (
        "wss://fstream.binance.com/market/stream?"
        "streams=btcusdt@kline_1h/btcusdt@kline_4h"
    )


def test_binance_spot_kline_stream_url_uses_public_market_endpoint() -> None:
    url = ohlcv_stream_url("binance_spot", ["btcusdt@kline_1m"])

    assert url == "wss://data-stream.binance.vision/stream?streams=btcusdt@kline_1m"


def test_parse_closed_kline_event_as_store_record() -> None:
    raw = json.dumps(
        {
            "stream": "btcusdt@kline_1m",
            "data": {
                "e": "kline",
                "E": 1638747720000,
                "s": "BTCUSDT",
                "k": {
                    "t": 1638747660000,
                    "T": 1638747719999,
                    "s": "BTCUSDT",
                    "i": "1m",
                    "o": "100.0",
                    "c": "102.0",
                    "h": "103.0",
                    "l": "99.0",
                    "v": "12.5",
                    "x": True,
                },
            },
        }
    )

    event = parse_ohlcv_stream_message(raw)
    record = binance_kline_event_to_ohlcv_record(
        event,
        source="binance_usdm",
        symbol="BTCUSDT",
        timeframe="1m",
    )

    assert record == {
        "source": "binance_usdm",
        "symbol": "BTCUSDT",
        "timeframe": "1m",
        "open_time": "2021-12-05T23:41:00Z",
        "open": 100.0,
        "high": 103.0,
        "low": 99.0,
        "close": 102.0,
        "volume": 12.5,
        "fetched_at": "2021-12-05T23:42:00Z",
    }


def test_open_kline_event_does_not_write_record() -> None:
    event = parse_ohlcv_stream_message(
        {
            "e": "kline",
            "E": 1638747700000,
            "s": "BTCUSDT",
            "k": {
                "t": 1638747660000,
                "s": "BTCUSDT",
                "i": "1m",
                "o": "100.0",
                "c": "102.0",
                "h": "103.0",
                "l": "99.0",
                "v": "12.5",
                "x": False,
            },
        }
    )

    assert binance_kline_event_to_ohlcv_record(
        event,
        source="binance_usdm",
        symbol="BTCUSDT",
        timeframe="1m",
    ) is None


def test_build_ohlcv_stream_targets_reuses_configured_live_ohlcv_targets(tmp_path: Path) -> None:
    config = {
        "live": {
            "enabled": True,
            "collections": {
                "ohlcv": {
                    "enabled": True,
                    "cadence_seconds": 300,
                    "lookback_seconds": 3600,
                }
            },
        },
        "market": {
            "enabled": True,
            "source": "binance_usdm",
            "symbols": ["BTCUSDT"],
            "ohlcv": {
                "storage_dir": str(tmp_path / "ohlcv"),
                "sources": ["binance_usdm"],
                "timeframes": ["1m", "4h"],
                "lookback": {"1m": 30, "4h": 60},
            },
        },
    }

    targets = build_ohlcv_stream_targets(config, load_live_settings(config))

    assert [(target.target_key, target.stream_name) for target in targets] == [
        ("ohlcv:binance_usdm:BTCUSDT:1m", "btcusdt@kline_1m"),
        ("ohlcv:binance_usdm:BTCUSDT:4h", "btcusdt@kline_4h"),
    ]


def test_load_live_settings_enables_ohlcv_stream_by_default_when_ohlcv_collection_is_enabled() -> None:
    config = {
        "live": {
            "enabled": True,
            "collections": {
                "ohlcv": {
                    "enabled": True,
                    "cadence_seconds": 300,
                    "lookback_seconds": 3600,
                }
            },
        }
    }

    settings = load_live_settings(config)

    assert settings.ohlcv_stream.enabled is True
    assert settings.ohlcv_stream.stale_after_seconds == 180


def test_stream_state_exposes_market_identity_fields(tmp_path: Path) -> None:
    repository = LiveStreamStateRepository(tmp_path / "config.local.yaml")

    saved = repository.upsert_state(
        {
            "target_key": "ohlcv:binance_usdm:BTCUSDT:1m",
            "data_type": "ohlcv",
            "target": {
                "source": "binance_usdm",
                "symbol": "BTCUSDT",
                "timeframe": "1m",
            },
            "enabled": True,
            "status": "streaming",
        }
    )

    assert saved["source"] == "binance_usdm"
    assert saved["symbol"] == "BTCUSDT"
    assert saved["timeframe"] == "1m"
    assert repository.get_state("ohlcv:binance_usdm:BTCUSDT:1m")["source"] == "binance_usdm"
