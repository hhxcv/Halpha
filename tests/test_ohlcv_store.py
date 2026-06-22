from __future__ import annotations

import json
from pathlib import Path

import pytest

from halpha.market.ohlcv_store import OHLCVParquetStore, OHLCV_REQUIRED_FIELDS, OHLCVStoreError


def test_ohlcv_store_writes_reads_deduplicates_and_orders_records(tmp_path: Path) -> None:
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")

    summary = store.write_records(
        [
            _record(open_time="2026-06-02T00:00:00Z", close=102),
            _record(open_time="2026-06-01T00:00:00Z", close=101),
            _record(open_time="2026-06-01T00:00:00Z", close=101),
        ]
    )

    records = store.read_records(source="binance", symbol="BTCUSDT", timeframe="1d")

    assert [record["open_time"] for record in records] == [
        "2026-06-01T00:00:00Z",
        "2026-06-02T00:00:00Z",
    ]
    assert records[0]["close"] == 101.0
    assert all(tuple(record) == OHLCV_REQUIRED_FIELDS for record in records)
    assert summary["items"] == [
        {
            "source": "binance",
            "symbol": "BTCUSDT",
            "timeframe": "1d",
            "earliest_open_time": "2026-06-01T00:00:00Z",
            "latest_open_time": "2026-06-02T00:00:00Z",
            "row_count": 2,
            "storage_ref": (
                tmp_path
                / "data"
                / "market"
                / "ohlcv"
                / "source=binance"
                / "symbol=BTCUSDT"
                / "timeframe=1d"
            ).as_posix(),
            "warnings": [],
        }
    ]
    assert (
        tmp_path
        / "data"
        / "market"
        / "ohlcv"
        / "source=binance"
        / "symbol=BTCUSDT"
        / "timeframe=1d"
        / "year=2026"
        / "month=06"
        / "part-000.parquet"
    ).exists()


def test_ohlcv_store_persists_schema_and_range_metadata(tmp_path: Path) -> None:
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")

    store.write_records(
        [
            _record(open_time="2026-06-02T00:00:00Z"),
            _record(open_time="2026-06-01T00:00:00Z"),
        ]
    )

    schema = json.loads(
        (tmp_path / "data" / "market" / "metadata" / "ohlcv_schema.json").read_text(encoding="utf-8")
    )
    sync_state = json.loads(
        (tmp_path / "data" / "market" / "metadata" / "ohlcv_sync_state.json").read_text(
            encoding="utf-8"
        )
    )

    assert schema == {
        "schema_version": 1,
        "artifact_type": "ohlcv_schema",
        "required_fields": list(OHLCV_REQUIRED_FIELDS),
        "unique_key": ["source", "symbol", "timeframe", "open_time"],
        "time_format": "iso8601_utc",
    }
    assert sync_state["artifact_type"] == "ohlcv_sync_state"
    assert sync_state["items"][0]["earliest_open_time"] == "2026-06-01T00:00:00Z"
    assert sync_state["items"][0]["latest_open_time"] == "2026-06-02T00:00:00Z"
    assert sync_state["items"][0]["row_count"] == 2


def test_ohlcv_store_keeps_groups_separate_and_sorted(tmp_path: Path) -> None:
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")

    store.write_records(
        [
            _record(symbol="ETHUSDT", open_time="2026-06-02T00:00:00Z", close=202),
            _record(symbol="BTCUSDT", open_time="2026-06-02T00:00:00Z", close=102),
            _record(symbol="BTCUSDT", open_time="2026-06-01T00:00:00Z", close=101),
            _record(symbol="BTCUSDT", timeframe="1h", open_time="2026-06-01T01:00:00Z", close=101.5),
        ]
    )

    daily_btc = store.read_records(source="binance", symbol="BTCUSDT", timeframe="1d")
    hourly_btc = store.read_records(source="binance", symbol="BTCUSDT", timeframe="1h")
    daily_eth = store.read_records(source="binance", symbol="ETHUSDT", timeframe="1d")

    assert [record["open_time"] for record in daily_btc] == [
        "2026-06-01T00:00:00Z",
        "2026-06-02T00:00:00Z",
    ]
    assert [record["close"] for record in hourly_btc] == [101.5]
    assert [record["close"] for record in daily_eth] == [202.0]


def test_ohlcv_store_rejects_run_output_dir_storage_root(tmp_path: Path) -> None:
    with pytest.raises(OHLCVStoreError, match="outside run output directory"):
        OHLCVParquetStore(tmp_path / "runs" / "run-1" / "ohlcv", run_output_dir=tmp_path / "runs")

    store = OHLCVParquetStore(
        tmp_path / "data" / "market" / "ohlcv",
        run_output_dir=tmp_path / "runs",
    )
    store.write_records([_record()])

    assert store.read_records(source="binance", symbol="BTCUSDT", timeframe="1d")


def test_ohlcv_store_rejects_invalid_schema_records(tmp_path: Path) -> None:
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    record = _record()
    del record["fetched_at"]

    with pytest.raises(OHLCVStoreError, match="fetched_at"):
        store.write_records([record])


def test_ohlcv_store_rejects_conflicting_duplicate_candles(tmp_path: Path) -> None:
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")

    with pytest.raises(OHLCVStoreError, match="conflicting values"):
        store.write_records([_record(close=100), _record(close=101)])


def _record(
    *,
    source: str = "binance",
    symbol: str = "BTCUSDT",
    timeframe: str = "1d",
    open_time: str = "2026-06-01T00:00:00Z",
    close: float = 100.0,
) -> dict[str, object]:
    return {
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "open_time": open_time,
        "open": close - 1,
        "high": close + 1,
        "low": close - 2,
        "close": close,
        "volume": 10,
        "fetched_at": "2026-06-03T00:00:00Z",
    }
