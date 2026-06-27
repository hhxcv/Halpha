from __future__ import annotations

from pathlib import Path

import pytest

from halpha.data.collection_coverage import write_collection_coverage_state
from halpha.market.ohlcv_query import query_ohlcv_records
from halpha.market.ohlcv_store import OHLCVParquetStore


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_ohlcv_query_filters_range_deterministically_and_excludes_end_by_default(tmp_path: Path) -> None:
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-03T00:00:00Z", close=103),
            _record(open_time="2026-06-01T00:00:00Z", close=101),
            _record(open_time="2026-06-04T00:00:00Z", close=104),
            _record(open_time="2026-06-02T00:00:00Z", close=102),
        ]
    )

    result = query_ohlcv_records(
        tmp_path / "data" / "market" / "ohlcv",
        source="binance",
        symbol="BTCUSDT",
        timeframe="1d",
        start="2026-06-02T00:00:00Z",
        end="2026-06-04T00:00:00Z",
    )

    assert result["status"] == "ok"
    assert result["time_fields"]["end_inclusive"] is False
    assert result["record_count"] == 2
    assert result["history_row_count"] == 4
    assert [record["open_time"] for record in result["records"]] == [
        "2026-06-02T00:00:00Z",
        "2026-06-03T00:00:00Z",
    ]
    assert result["missing_diagnostics"]["expected_interval_count"] == 2
    assert result["missing_diagnostics"]["missing_interval_count"] == 0


def test_ohlcv_query_supports_inclusive_open_time_end_for_existing_windows(tmp_path: Path) -> None:
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=101),
            _record(open_time="2026-06-02T00:00:00Z", close=102),
            _record(open_time="2026-06-03T00:00:00Z", close=103),
        ]
    )

    result = query_ohlcv_records(
        tmp_path / "data" / "market" / "ohlcv",
        source="binance",
        symbol="BTCUSDT",
        timeframe="1d",
        start="2026-06-02T00:00:00Z",
        end="2026-06-03T00:00:00Z",
        end_inclusive=True,
    )

    assert result["time_fields"]["end_inclusive"] is True
    assert [record["open_time"] for record in result["records"]] == [
        "2026-06-02T00:00:00Z",
        "2026-06-03T00:00:00Z",
    ]
    assert result["missing_diagnostics"]["expected_interval_count"] == 2


def test_ohlcv_query_as_of_excludes_unclosed_future_candles(tmp_path: Path) -> None:
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=101),
            _record(open_time="2026-06-02T00:00:00Z", close=102),
            _record(open_time="2026-06-03T00:00:00Z", close=103),
            _record(open_time="2026-06-04T00:00:00Z", close=104),
        ]
    )

    result = query_ohlcv_records(
        tmp_path / "data" / "market" / "ohlcv",
        source="binance",
        symbol="BTCUSDT",
        timeframe="1d",
        start="2026-06-01T00:00:00Z",
        end="2026-06-05T00:00:00Z",
        as_of="2026-06-03T12:00:00Z",
    )

    assert result["as_of"] == "2026-06-03T12:00:00Z"
    assert [record["open_time"] for record in result["records"]] == [
        "2026-06-01T00:00:00Z",
        "2026-06-02T00:00:00Z",
    ]
    assert result["missing_diagnostics"]["expected_interval_count"] == 2
    assert result["missing_diagnostics"]["missing_interval_count"] == 0


def test_ohlcv_query_surfaces_missing_candle_diagnostics(tmp_path: Path) -> None:
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=101),
            _record(open_time="2026-06-03T00:00:00Z", close=103),
        ]
    )

    result = query_ohlcv_records(
        tmp_path / "data" / "market" / "ohlcv",
        source="binance",
        symbol="BTCUSDT",
        timeframe="1d",
        start="2026-06-01T00:00:00Z",
        end="2026-06-04T00:00:00Z",
    )

    assert result["status"] == "warning"
    assert result["missing_diagnostics"]["missing_interval_count"] == 1
    assert result["missing_diagnostics"]["missing_open_time_samples"] == ["2026-06-02T00:00:00Z"]
    assert result["quality"]["missing_interval_count"] == 1
    assert "missing_ohlcv_intervals" in {warning["code"] for warning in result["warnings"]}


def test_ohlcv_query_surfaces_collection_coverage_gaps(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("run:\n  output_dir: runs\n", encoding="utf-8")
    write_collection_coverage_state(
        config_path,
        [
            {
                "data_type": "ohlcv",
                "source": "binance",
                "identity": {"symbol": "BTCUSDT", "timeframe": "1d"},
                "range_start": "2026-06-01T00:00:00Z",
                "range_end": "2026-06-02T00:00:00Z",
                "status": "no_data",
            },
            {
                "data_type": "ohlcv",
                "source": "binance",
                "identity": {"symbol": "BTCUSDT", "timeframe": "1d"},
                "range_start": "2026-06-02T00:00:00Z",
                "range_end": "2026-06-03T00:00:00Z",
                "status": "failed",
                "errors": [{"message": "source timeout"}],
            },
            {
                "data_type": "ohlcv",
                "source": "binance",
                "identity": {"symbol": "BTCUSDT", "timeframe": "1d"},
                "range_start": "2026-06-03T00:00:00Z",
                "range_end": "2026-06-04T00:00:00Z",
                "status": "partial",
                "record_count": 1,
            },
        ],
        now="2026-06-05T00:00:00Z",
    )

    result = query_ohlcv_records(
        tmp_path / "data" / "market" / "ohlcv",
        source="binance",
        symbol="BTCUSDT",
        timeframe="1d",
        start="2026-06-01T00:00:00Z",
        end="2026-06-05T00:00:00Z",
        config_path=config_path,
    )

    coverage = result["coverage_diagnostics"]
    assert result["status"] == "warning"
    assert coverage["status"] == "available"
    assert coverage["status_counts"] == {"failed": 1, "no_data": 1, "partial": 1}
    assert coverage["failed_ranges"] == [
        {"range_start": "2026-06-02T00:00:00Z", "range_end": "2026-06-03T00:00:00Z"}
    ]
    assert coverage["partial_ranges"] == [
        {"range_start": "2026-06-03T00:00:00Z", "range_end": "2026-06-04T00:00:00Z"}
    ]
    assert coverage["unknown_ranges"] == [
        {"range_start": "2026-06-04T00:00:00Z", "range_end": "2026-06-05T00:00:00Z"}
    ]
    assert "incomplete_collection_coverage" in {warning["code"] for warning in result["warnings"]}


def test_ohlcv_query_limit_truncates_records_with_diagnostics(tmp_path: Path) -> None:
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=101),
            _record(open_time="2026-06-02T00:00:00Z", close=102),
            _record(open_time="2026-06-03T00:00:00Z", close=103),
        ]
    )

    result = query_ohlcv_records(
        tmp_path / "data" / "market" / "ohlcv",
        source="binance",
        symbol="BTCUSDT",
        timeframe="1d",
        start="2026-06-01T00:00:00Z",
        end="2026-06-04T00:00:00Z",
        limit=2,
    )

    assert result["truncated"] is True
    assert result["matched_record_count"] == 3
    assert result["record_count"] == 2
    assert result["missing_diagnostics"]["missing_interval_count"] == 0
    assert [record["open_time"] for record in result["records"]] == [
        "2026-06-01T00:00:00Z",
        "2026-06-02T00:00:00Z",
    ]
    assert "query_result_truncated" in {warning["code"] for warning in result["warnings"]}


def _record(
    *,
    source: str = "binance",
    symbol: str = "BTCUSDT",
    timeframe: str = "1d",
    open_time: str,
    close: float,
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
        "fetched_at": "2026-06-05T00:00:00Z",
    }
