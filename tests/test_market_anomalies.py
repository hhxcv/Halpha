from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from halpha.collectors.market_anomalies import collect_market_anomalies_data
from halpha.data.collection_coverage import read_collection_coverage_state
from halpha.market.market_anomaly_history import (
    read_market_anomaly_history_records,
    sync_market_anomaly_history,
)
from halpha.market.ohlcv_store import OHLCVParquetStore
from halpha.pipeline import RunContext


pytestmark = pytest.mark.usefixtures("isolate_artifact_cwd")


def test_halpha_rule_collector_detects_price_move_from_ohlcv_history(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("run:\n  output_dir: runs\n", encoding="utf-8")
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _ohlcv_record("2026-06-01T00:00:00Z", close=100.0, volume=10.0),
            _ohlcv_record("2026-06-02T00:00:00Z", close=110.0, volume=12.0),
        ]
    )
    run = _run_context(tmp_path, config_path, "run-1")
    config = {
        "market": {
            "enabled": True,
            "source": "binance",
            "symbols": ["BTCUSDT"],
            "ohlcv": {
                "storage_dir": "data/market/ohlcv",
                "sources": ["binance"],
                "timeframes": ["1d"],
            },
            "anomalies": {
                "enabled": True,
                "source_kinds": ["halpha_rule"],
                "window_start": "2026-06-01T00:00:00Z",
                "window_end": "2026-06-03T00:00:00Z",
                "price_move_threshold_pct": 5.0,
            },
        }
    }

    artifacts = collect_market_anomalies_data(config, run)

    raw = json.loads((run.raw_dir / "market_anomalies.json").read_text(encoding="utf-8"))
    assert artifacts == ["raw/market_anomalies.json"]
    assert raw["artifact_type"] == "market_anomalies_raw"
    assert raw["requested_start"] == "2026-06-01T00:00:00Z"
    assert raw["requested_end"] == "2026-06-03T00:00:00Z"
    assert len(raw["items"]) == 1
    assert raw["items"][0]["source_kind"] == "halpha_rule"
    assert raw["items"][0]["data_class"] == "price_move"
    assert raw["items"][0]["symbol"] == "BTCUSDT"
    assert raw["items"][0]["metric"] == "close_return_pct"
    assert raw["items"][0]["value"] == 10.0
    assert run.manifest["counts"]["market_anomaly_items"] == 1


def test_market_anomaly_history_merges_sources_and_writes_coverage(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("run:\n  output_dir: runs\n", encoding="utf-8")
    run = _run_context(tmp_path, config_path, "run-1")
    raw = {
        "schema_version": 1,
        "artifact_type": "market_anomalies_raw",
        "collector": "market_anomalies",
        "collected_at": "2026-06-03T00:00:00Z",
        "requested_start": "2026-06-01T00:00:00Z",
        "requested_end": "2026-06-04T00:00:00Z",
        "items": [
            _anomaly_item("external:1", source_kind="external_intel", source="external_json"),
            _anomaly_item("halpha:1", source_kind="halpha_rule", source="halpha_monitor_rules"),
        ],
        "availability": [],
        "warnings": [],
        "errors": [],
    }
    (run.raw_dir / "market_anomalies.json").write_text(json.dumps(raw), encoding="utf-8")

    artifacts = sync_market_anomaly_history(
        {"market": {"anomalies": {"enabled": True}}},
        run,
        now="2026-06-03T00:00:00Z",
    )

    records = read_market_anomaly_history_records(config_path)
    coverage = read_collection_coverage_state(config_path)
    state = json.loads((tmp_path / "data" / "market" / "metadata" / "market_anomaly_state.json").read_text(encoding="utf-8"))
    assert artifacts == [
        "data/market/metadata/market_anomaly_schema.json",
        "data/market/metadata/market_anomaly_state.json",
    ]
    assert len(records) == 1
    assert records[0]["source_kinds"] == ["external_intel", "halpha_rule"]
    assert records[0]["sources"] == ["external_json", "halpha_monitor_rules"]
    assert len(records[0]["source_records"]) == 2
    assert state["totals"]["duplicate_records"] == 1
    assert state["totals"]["dedupe_groups"] == 1
    assert coverage["counts"]["statuses"] == {"collected": 1}
    assert coverage["records"][0]["data_type"] == "market_anomaly"
    assert coverage["records"][0]["record_count"] == 2


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


def _ohlcv_record(open_time: str, *, close: float, volume: float) -> dict[str, Any]:
    return {
        "source": "binance",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "open_time": open_time,
        "open": close - 1,
        "high": close + 1,
        "low": close - 2,
        "close": close,
        "volume": volume,
        "fetched_at": "2026-06-03T00:00:00Z",
    }


def _anomaly_item(anomaly_id: str, *, source_kind: str, source: str) -> dict[str, Any]:
    return {
        "anomaly_id": anomaly_id,
        "source_kind": source_kind,
        "source": source,
        "data_class": "price_move",
        "symbol": "BTCUSDT",
        "market_type": "spot",
        "timeframe": "1d",
        "observed_at": "2026-06-02T00:00:00Z",
        "published_at": "2026-06-02T00:00:00Z",
        "collected_at": "2026-06-03T00:00:00Z",
        "first_seen_at": "2026-06-03T00:00:00Z",
        "last_seen_at": "2026-06-03T00:00:00Z",
        "severity": "medium",
        "direction": "up",
        "metric": "close_return_pct",
        "value": 10.0,
        "threshold": 5.0,
        "unit": "percent",
        "window_start": "2026-06-01T00:00:00Z",
        "window_end": "2026-06-02T00:00:00Z",
        "title": "BTCUSDT 1d close return 10.00%",
        "summary": "BTCUSDT 1d close changed 10.00% from the previous candle.",
        "dedupe_key": "price_move|BTCUSDT|1d|2026-06-02T00:00:00Z|close_return_pct|up",
        "metrics": {"close_return_pct": 10.0},
        "units": {"close_return_pct": "percent"},
        "raw_fields": {"rule_name": "test"},
        "warnings": [],
        "errors": [],
        "source_artifacts": ["raw/market_anomalies.json"],
    }
