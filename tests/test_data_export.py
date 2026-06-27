from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import pytest

from halpha.data.data_export import DataExportError, export_data
from halpha.market.ohlcv_store import OHLCVParquetStore
from halpha.pipeline import RunContext
from halpha.text.text_event_history import write_text_event_history


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_export_ohlcv_csv_respects_as_of_and_writes_metadata(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _ohlcv_record(open_time="2026-06-01T00:00:00Z", close=101),
            _ohlcv_record(open_time="2026-06-02T00:00:00Z", close=102),
            _ohlcv_record(open_time="2026-06-03T00:00:00Z", close=103),
        ]
    )

    result = export_data(
        _config(),
        config_path=config_path,
        data_type="ohlcv",
        source="binance",
        symbol="BTCUSDT",
        timeframe="1d",
        start="2026-06-01T00:00:00Z",
        end="2026-06-04T00:00:00Z",
        as_of="2026-06-03T12:00:00Z",
        output_format="csv",
        output_path=tmp_path / "exports" / "ohlcv.csv",
        now="2026-06-05T00:00:00Z",
    )

    rows = _read_csv(tmp_path / "exports" / "ohlcv.csv")
    metadata = _read_json(tmp_path / "exports" / "ohlcv.csv.metadata.json")
    assert result["record_count"] == 2
    assert result["metadata_path"] == "exports/ohlcv.csv.metadata.json"
    assert [row["open_time"] for row in rows] == [
        "2026-06-01T00:00:00Z",
        "2026-06-02T00:00:00Z",
    ]
    assert metadata["query_parameters"]["as_of"] == "2026-06-03T12:00:00Z"
    assert metadata["record_count"] == 2
    assert metadata["truncated"] is False
    assert metadata["coverage_diagnostics"]["status"] == "not_available"
    assert "data/research/metadata/collection_coverage_state.json" in metadata["source_artifacts"]


def test_export_ohlcv_parquet_writes_query_records(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records([_ohlcv_record(open_time="2026-06-01T00:00:00Z", close=101)])

    export_data(
        _config(),
        config_path=config_path,
        data_type="ohlcv",
        source="binance",
        symbol="BTCUSDT",
        timeframe="1d",
        start="2026-06-01T00:00:00Z",
        end="2026-06-02T00:00:00Z",
        output_format="parquet",
        output_path=tmp_path / "exports" / "ohlcv.parquet",
    )

    records = pq.ParquetFile(tmp_path / "exports" / "ohlcv.parquet").read().to_pylist()
    metadata = _read_json(tmp_path / "exports" / "ohlcv.parquet.metadata.json")
    assert [record["open_time"] for record in records] == ["2026-06-01T00:00:00Z"]
    assert metadata["format"] == "parquet"
    assert metadata["record_count"] == 1


def test_export_text_event_json_preserves_source_refs_and_excludes_future_seen_records(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    run = _run_context(tmp_path, config_path, "run-1")
    write_text_event_history(
        {"text": {"enabled": True}},
        run,
        [
            _text_event(
                "btc-1",
                published_at="2026-06-01T00:30:00Z",
                collected_at="2026-06-01T00:31:00Z",
            ),
            _text_event(
                "late-1",
                published_at="2026-06-01T01:30:00Z",
                collected_at="2026-06-03T00:00:00Z",
            ),
        ],
        now="2026-06-03T00:00:00Z",
    )

    result = export_data(
        {"text": {"enabled": True}},
        config_path=config_path,
        data_type="text_event",
        source="coindesk",
        start="2026-06-01T00:00:00Z",
        end="2026-06-02T00:00:00Z",
        as_of="2026-06-01T02:00:00Z",
        output_format="json",
        output_path=tmp_path / "exports" / "events.json",
        now="2026-06-05T00:00:00Z",
    )

    payload = _read_json(tmp_path / "exports" / "events.json")
    assert result["metadata_path"] is None
    assert payload["artifact_type"] == "data_export"
    assert payload["metadata"]["record_count"] == 1
    assert payload["metadata"]["coverage_diagnostics"]["status"] == "not_available"
    assert payload["records"][0]["raw_item_id"] == "text:coindesk:btc-1"
    assert payload["records"][0]["source_artifacts"]
    assert all(ref.startswith("runs/run-1/") for ref in payload["records"][0]["source_artifacts"])
    assert payload["metadata"]["query"]["filter_diagnostics"]["as_of_excluded_record_count"] == 1


def test_export_event_like_unknown_coverage_stays_visible_in_metadata(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)

    export_data(
        {},
        config_path=config_path,
        data_type="derivatives_market",
        source="binance_usdm",
        identity={"data_class": "funding_rate", "symbol": "BTCUSDT", "period": "8h"},
        start="2026-06-01T00:00:00Z",
        end="2026-06-02T00:00:00Z",
        output_format="json",
        output_path=tmp_path / "exports" / "empty.json",
    )

    payload = _read_json(tmp_path / "exports" / "empty.json")
    metadata = payload["metadata"]
    assert metadata["record_count"] == 0
    assert metadata["coverage_diagnostics"]["status"] == "not_available"
    assert metadata["query"]["empty_result_diagnostics"]["status"] == "unknown_coverage"
    assert "unknown_collection_coverage" in {warning["code"] for warning in metadata["warnings"]}


def test_export_rejects_unsupported_format_without_querying_full_history(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)

    with pytest.raises(DataExportError, match="text_event export format must be one of"):
        export_data(
            {},
            config_path=config_path,
            data_type="text_event",
            start="2026-06-01T00:00:00Z",
            end="2026-06-02T00:00:00Z",
            output_format="parquet",
            output_path=tmp_path / "exports" / "events.parquet",
        )

    assert not (tmp_path / "exports" / "events.parquet").exists()


def test_export_uses_the_ohlcv_query_boundary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = _write_config(tmp_path)
    calls: list[dict[str, Any]] = []

    def fake_query(storage_dir: Path, **kwargs: Any) -> dict[str, Any]:
        calls.append({"storage_dir": storage_dir, **kwargs})
        return _fake_query_result(
            data_type="ohlcv",
            records=[_ohlcv_record(open_time="2026-06-01T00:00:00Z", close=101)],
        )

    monkeypatch.setattr("halpha.data.data_export.query_ohlcv_records", fake_query)

    export_data(
        _config(),
        config_path=config_path,
        data_type="ohlcv",
        source="binance",
        symbol="BTCUSDT",
        timeframe="1d",
        start="2026-06-01T00:00:00Z",
        end="2026-06-02T00:00:00Z",
        as_of="2026-06-02T00:00:00Z",
        output_format="csv",
        output_path=tmp_path / "exports" / "ohlcv.csv",
        limit=1,
    )

    assert calls == [
        {
            "storage_dir": tmp_path / "data" / "market" / "ohlcv",
            "source": "binance",
            "symbol": "BTCUSDT",
            "timeframe": "1d",
            "start": "2026-06-01T00:00:00Z",
            "end": "2026-06-02T00:00:00Z",
            "as_of": "2026-06-02T00:00:00Z",
            "config_path": config_path,
            "limit": 1,
        }
    ]


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text("run:\n  output_dir: runs\n", encoding="utf-8")
    return path


def _config() -> dict[str, Any]:
    return {"market": {"ohlcv": {"storage_dir": "data/market/ohlcv"}}}


def _run_context(tmp_path: Path, config_path: Path, run_id: str) -> RunContext:
    run_dir = tmp_path / "runs" / run_id
    raw_dir = run_dir / "raw"
    analysis_dir = run_dir / "analysis"
    codex_context_dir = run_dir / "codex_context"
    report_dir = run_dir / "report"
    for directory in (raw_dir, analysis_dir, codex_context_dir, report_dir):
        directory.mkdir(parents=True, exist_ok=True)
    return RunContext(
        run_id=run_id,
        run_dir=run_dir,
        raw_dir=raw_dir,
        analysis_dir=analysis_dir,
        codex_context_dir=codex_context_dir,
        report_dir=report_dir,
        manifest_path=run_dir / "run_manifest.json",
        config_path=config_path,
        manifest={"artifacts": {}, "counts": {}, "errors": []},
    )


def _ohlcv_record(*, open_time: str, close: float) -> dict[str, Any]:
    return {
        "source": "binance",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "open_time": open_time,
        "open": close - 1,
        "high": close + 1,
        "low": close - 2,
        "close": close,
        "volume": 10,
        "fetched_at": "2026-06-05T00:00:00Z",
    }


def _text_event(raw_id: str, *, published_at: str, collected_at: str) -> dict[str, Any]:
    return {
        "event_id": f"text_event:coindesk:{raw_id}",
        "raw_item_id": f"text:coindesk:{raw_id}",
        "input_type": "rss_item",
        "source": {"name": "coindesk", "url": "https://example.com/coindesk/rss"},
        "title": f"Bitcoin market update {raw_id}",
        "content_text": f"Bitcoin market update content {raw_id}.",
        "link": f"https://example.com/coindesk/{raw_id}",
        "canonical_url": f"https://example.com/coindesk/{raw_id}",
        "published_at": published_at,
        "collected_at": collected_at,
        "language": "en",
        "normalized_title": f"bitcoin market update {raw_id}",
        "normalized_text": f"bitcoin market update content {raw_id}.",
        "warnings": [],
        "source_artifacts": ["raw/text_events.json"],
    }


def _fake_query_result(*, data_type: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "artifact_type": f"{data_type}_query_result",
        "status": "ok",
        "source": "binance",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "requested_start": "2026-06-01T00:00:00Z",
        "requested_end": "2026-06-02T00:00:00Z",
        "as_of": "2026-06-02T00:00:00Z",
        "time_fields": {"range_field": "open_time"},
        "range": {"start": "2026-06-01T00:00:00Z", "end": "2026-06-01T00:00:00Z"},
        "matched_record_count": len(records),
        "record_count": len(records),
        "history_row_count": len(records),
        "truncated": False,
        "limit": 1,
        "records": records,
        "coverage_diagnostics": {"status": "not_available", "record_count": 0},
        "warnings": [],
        "errors": [],
        "source_artifacts": ["data/research/metadata/collection_coverage_state.json"],
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
