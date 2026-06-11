from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from halpha.ohlcv_store import OHLCVParquetStore
from halpha.pipeline import RunContext
from halpha.research_data_catalog import build_research_data_catalog, write_research_data_catalog


def test_research_data_catalog_registers_shared_ohlcv_store(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = _config()
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _ohlcv_record(symbol="BTCUSDT", open_time="2026-06-01T00:00:00Z", close=100),
            _ohlcv_record(symbol="ETHUSDT", open_time="2026-06-02T00:00:00Z", close=200),
        ]
    )
    run = _run_context(tmp_path, config_path)
    run.manifest["ohlcv_sync"] = {
        "status": "succeeded",
        "warnings": [],
        "errors": [],
    }

    artifacts = write_research_data_catalog(config, run, now="2026-06-05T00:00:00Z")

    catalog_path = tmp_path / "data" / "research" / "metadata" / "research_data_catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    store_record = catalog["stores"][0]

    assert artifacts == ["data/research/metadata/research_data_catalog.json"]
    assert catalog["status"] == "ok"
    assert catalog["counts"] == {"errors": 0, "records": 2, "stores": 1, "warnings": 0}
    assert store_record["name"] == "ohlcv_history"
    assert store_record["status"] == "ok"
    assert store_record["format"] == "parquet"
    assert store_record["storage_path"] == "data/market/ohlcv"
    assert store_record["schema_path"] == "data/market/metadata/ohlcv_schema.json"
    assert store_record["state_path"] == "data/market/metadata/ohlcv_sync_state.json"
    assert store_record["unique_key_fields"] == ["source", "symbol", "timeframe", "open_time"]
    assert store_record["sources"] == ["binance"]
    assert store_record["record_count"] == 2
    assert run.manifest["artifacts"]["research_data_catalog"] == (
        "data/research/metadata/research_data_catalog.json"
    )
    assert run.manifest["research_data_catalog"]["status"] == "ok"
    assert run.manifest["counts"]["research_data_catalog_records"] == 2


def test_research_data_catalog_records_missing_metadata_without_absolute_paths(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    run = _run_context(tmp_path, config_path)

    catalog = build_research_data_catalog(_config(), run, now="2026-06-05T00:00:00Z")

    assert catalog["status"] == "degraded"
    assert catalog["counts"]["warnings"] == 2
    store = catalog["stores"][0]
    assert store["status"] == "degraded"
    assert store["schema_path"] == "data/market/metadata/ohlcv_schema.json"
    assert store["state_path"] == "data/market/metadata/ohlcv_sync_state.json"
    assert str(tmp_path) not in json.dumps(catalog)


def test_research_data_catalog_skips_when_ohlcv_is_not_configured(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    run = _run_context(tmp_path, config_path)
    config = _config()
    del config["market"]["ohlcv"]

    catalog = build_research_data_catalog(config, run, now="2026-06-05T00:00:00Z")

    assert catalog["status"] == "skipped"
    assert catalog["stores"] == []
    assert catalog["warnings"] == [
        "market.ohlcv is not configured; no shared OHLCV store is registered."
    ]


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text("run:\n  output_dir: runs\n", encoding="utf-8")
    return path


def _config() -> dict[str, Any]:
    return {
        "market": {
            "enabled": True,
            "source": "binance",
            "symbols": ["BTCUSDT", "ETHUSDT"],
            "ohlcv": {
                "storage_dir": "data/market/ohlcv",
                "timeframes": ["1d"],
                "lookback": {"1d": 2},
            },
        }
    }


def _run_context(tmp_path: Path, config_path: Path) -> RunContext:
    run_dir = tmp_path / "runs" / "run-1"
    raw_dir = run_dir / "raw"
    analysis_dir = run_dir / "analysis"
    codex_context_dir = run_dir / "codex_context"
    report_dir = run_dir / "report"
    for directory in (raw_dir, analysis_dir, codex_context_dir, report_dir):
        directory.mkdir(parents=True, exist_ok=True)
    return RunContext(
        run_id="run-1",
        run_dir=run_dir,
        raw_dir=raw_dir,
        analysis_dir=analysis_dir,
        codex_context_dir=codex_context_dir,
        report_dir=report_dir,
        manifest_path=run_dir / "run_manifest.json",
        config_path=config_path,
        manifest={"artifacts": {}, "counts": {}, "errors": []},
    )


def _ohlcv_record(
    *,
    source: str = "binance",
    symbol: str,
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
