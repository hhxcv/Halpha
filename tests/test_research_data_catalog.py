from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from halpha.data.collection_coverage import write_collection_coverage_state
from halpha.market.ohlcv_store import OHLCVParquetStore
from halpha.pipeline import RunContext
from halpha.data.research_data_catalog import (
    build_research_data_catalog,
    validate_research_data_catalog,
    write_research_data_catalog,
)


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


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
    assert store_record["domain"] == "market"
    assert store_record["status"] == "ok"
    assert store_record["format"] == "parquet"
    assert store_record["storage_path"] == "data/market/ohlcv"
    assert store_record["schema_path"] == "data/market/metadata/ohlcv_schema.json"
    assert store_record["state_path"] == "data/market/metadata/ohlcv_sync_state.json"
    assert store_record["time_field"] == "open_time"
    assert store_record["latest_update_at"]
    assert store_record["latest_completed_revision"] == store_record["latest_update_at"]
    assert store_record["unique_key_fields"] == ["source", "symbol", "timeframe", "open_time"]
    assert store_record["sources"] == ["binance"]
    assert store_record["coverage_state"] == {
        "status": "not_available",
        "state_path": "data/research/metadata/collection_coverage_state.json",
        "data_type": "ohlcv",
        "record_count": 0,
        "status_counts": {},
        "range_start": None,
        "range_end": None,
        "partial_ranges": [],
        "failed_ranges": [],
        "not_collected_ranges": [],
    }
    assert store_record["query_capability"] == {
        "status": "implemented",
        "time_field": "open_time",
        "coverage_diagnostics": True,
    }
    assert store_record["migration_status"] == "current"
    assert store_record["migration"] == {
        "status": "current",
        "applied_schema_version": 1,
        "available_migrators": [],
        "compatibility_readers": ["current_reader"],
        "last_migration_at": store_record["latest_update_at"],
        "warnings": [],
        "errors": [],
    }
    assert store_record["record_count"] == 2
    assert run.manifest["artifacts"]["research_data_catalog"] == (
        "data/research/metadata/research_data_catalog.json"
    )
    assert run.manifest["research_data_catalog"]["status"] == "ok"
    assert run.manifest["counts"]["research_data_catalog_records"] == 2


def test_research_data_catalog_summarizes_collection_coverage_state(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = _config()
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records([_ohlcv_record(symbol="BTCUSDT", open_time="2026-06-01T00:00:00Z", close=100)])
    write_collection_coverage_state(
        config_path,
        [
            {
                "data_type": "ohlcv",
                "source": "binance",
                "identity": {"symbol": "BTCUSDT", "timeframe": "1d"},
                "range_start": "2026-06-01T00:00:00Z",
                "range_end": "2026-06-02T00:00:00Z",
                "status": "collected",
                "record_count": 1,
                "latest_attempt_at": "2026-06-02T00:00:00Z",
                "latest_success_at": "2026-06-02T00:00:00Z",
                "updated_at": "2026-06-02T00:00:00Z",
                "source_artifacts": ["raw/market_data_views.json"],
            },
            {
                "data_type": "ohlcv",
                "source": "binance",
                "identity": {"symbol": "BTCUSDT", "timeframe": "1d"},
                "range_start": "2026-06-03T00:00:00Z",
                "range_end": "2026-06-04T00:00:00Z",
                "status": "failed",
                "errors": [{"message": "source timeout"}],
            },
        ],
        now="2026-06-05T00:00:00Z",
    )
    run = _run_context(tmp_path, config_path)
    run.manifest["ohlcv_sync"] = {"status": "succeeded", "warnings": [], "errors": []}

    catalog = build_research_data_catalog(config, run, now="2026-06-05T00:00:00Z")
    store_record = catalog["stores"][0]

    assert store_record["coverage_state"]["status"] == "available"
    assert store_record["coverage_state"]["data_type"] == "ohlcv"
    assert store_record["coverage_state"]["record_count"] == 2
    assert store_record["coverage_state"]["status_counts"] == {"collected": 1, "failed": 1}
    assert store_record["coverage_state"]["range_start"] == "2026-06-01T00:00:00Z"
    assert store_record["coverage_state"]["range_end"] == "2026-06-04T00:00:00Z"
    assert store_record["coverage_state"]["failed_ranges"] == [
        {"range_start": "2026-06-03T00:00:00Z", "range_end": "2026-06-04T00:00:00Z"}
    ]
    assert store_record["query_capability"]["coverage_diagnostics"] is True


def test_research_data_catalog_records_missing_metadata_without_absolute_paths(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    run = _run_context(tmp_path, config_path)

    catalog = build_research_data_catalog(_config(), run, now="2026-06-05T00:00:00Z")

    assert catalog["status"] == "degraded"
    assert catalog["counts"]["warnings"] == 6
    assert catalog["validation"]["warning_count"] == 4
    store = catalog["stores"][0]
    assert store["status"] == "degraded"
    assert store["schema_path"] == "data/market/metadata/ohlcv_schema.json"
    assert store["state_path"] == "data/market/metadata/ohlcv_sync_state.json"
    assert store["migration_status"] == "degraded"
    assert "ohlcv_history.migration.applied_schema_version" in json.dumps(catalog)
    assert str(tmp_path) not in json.dumps(catalog)


def test_research_data_catalog_uses_safe_external_ref_for_external_shared_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    monkeypatch.chdir(runtime_root)
    config_path = _write_config(runtime_root)
    external_root = tmp_path / "external" / "market" / "ohlcv"
    config = _config()
    config["market"]["ohlcv"]["storage_dir"] = str(external_root)
    store = OHLCVParquetStore(external_root)
    store.write_records([_ohlcv_record(symbol="BTCUSDT", open_time="2026-06-01T00:00:00Z", close=100)])
    run = _run_context(runtime_root, config_path)
    run.manifest["ohlcv_sync"] = {
        "status": "succeeded",
        "warnings": [],
        "errors": [],
    }

    catalog = build_research_data_catalog(config, run, now="2026-06-05T00:00:00Z")

    store_record = catalog["stores"][0]
    serialized = json.dumps(catalog)
    assert catalog["status"] == "ok"
    assert store_record["storage_path"] == "<external-shared-data>"
    assert store_record["schema_path"] == "<external-shared-data>"
    assert store_record["state_path"] == "<external-shared-data>"
    assert str(external_root) not in serialized
    assert external_root.as_posix() not in serialized


def test_research_data_catalog_skips_when_ohlcv_is_not_configured(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    run = _run_context(tmp_path, config_path)
    config = _config()
    del config["market"]["ohlcv"]

    catalog = build_research_data_catalog(config, run, now="2026-06-05T00:00:00Z")

    assert catalog["status"] == "skipped"
    assert catalog["stores"] == []
    assert catalog["warnings"] == []


def test_research_data_catalog_registers_outcome_history_store(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    run = _run_context(tmp_path, config_path)
    _write_outcome_history_state(tmp_path)

    catalog = build_research_data_catalog({}, run, now="2026-06-05T00:00:00Z")
    store = catalog["stores"][0]

    assert catalog["status"] == "ok"
    assert catalog["counts"] == {"errors": 0, "records": 2, "stores": 1, "warnings": 0}
    assert store["name"] == "outcome_history"
    assert store["status"] == "ok"
    assert store["format"] == "json"
    assert store["storage_path"] == "data/research/outcomes"
    assert store["schema_path"] == "data/research/metadata/outcome_history_state.json"
    assert store["state_path"] == "data/research/metadata/outcome_history_state.json"
    assert store["time_field"] == "latest_evaluated_at"
    assert store["unique_key_fields"] == ["stable_outcome_key"]
    assert store["source_fields"] == ["source_run_id", "evaluation_run_id", "target_kind"]
    assert store["sources"] == ["source-run"]
    assert store["record_count"] == 2
    assert store["source_artifacts"] == [
        "data/research/outcomes/outcome_history.json",
        "data/research/metadata/outcome_history_state.json",
    ]


def test_research_data_catalog_registers_derivatives_market_history_store(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    run = _run_context(tmp_path, config_path)
    run.manifest["derivatives_market_history"] = {
        "status": "warning",
        "artifact": "data/market/metadata/derivatives_market_state.json",
    }
    _write_derivatives_market_metadata(tmp_path)

    catalog = build_research_data_catalog({}, run, now="2026-06-05T00:00:00Z")
    store = catalog["stores"][0]

    assert catalog["status"] == "warning"
    assert catalog["counts"] == {"errors": 0, "records": 3, "stores": 1, "warnings": 1}
    assert store["name"] == "derivatives_market_history"
    assert store["status"] == "warning"
    assert store["format"] == "json"
    assert store["storage_path"] == "data/market/derivatives"
    assert store["schema_path"] == "data/market/metadata/derivatives_market_schema.json"
    assert store["state_path"] == "data/market/metadata/derivatives_market_state.json"
    assert store["time_field"] == "as_of"
    assert store["unique_key_fields"] == [
        "source",
        "market_type",
        "data_class",
        "symbol",
        "period",
        "as_of",
    ]
    assert store["sources"] == ["binance_usdm"]
    assert store["record_count"] == 3
    assert store["details"]["groups"] == 1
    assert store["details"]["duplicate_records"] == 1
    assert "data_quality_summary" in store["consumers"]
    assert str(tmp_path) not in json.dumps(catalog)


def test_research_data_catalog_rejects_shared_store_under_runs(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    run = _run_context(tmp_path, config_path)
    config = _config()
    config["market"]["ohlcv"]["storage_dir"] = "runs/shared_ohlcv"

    catalog = build_research_data_catalog(config, run, now="2026-06-05T00:00:00Z")

    assert catalog["status"] == "failed"
    assert catalog["validation"]["error_count"] == 1
    assert catalog["stores"][0]["status"] == "failed"
    assert catalog["errors"][0]["field"] == "storage_path"
    assert "disposable run archive" in catalog["errors"][0]["message"]


def test_research_data_catalog_validation_reports_missing_and_stale_migration_metadata() -> None:
    validation = validate_research_data_catalog(
        {
            "stores": [
                {
                    "name": "legacy_store",
                    "storage_path": "data/research/legacy",
                    "schema_path": "data/research/metadata/legacy_schema.json",
                    "schema_version": 2,
                    "time_field": "updated_at",
                },
                {
                    "name": "stale_store",
                    "storage_path": "data/research/stale",
                    "schema_path": "data/research/metadata/stale_schema.json",
                    "schema_version": 2,
                    "time_field": "updated_at",
                    "migration": {
                        "status": "current",
                        "applied_schema_version": 1,
                        "last_migration_at": "2026-06-01T00:00:00Z",
                    },
                },
            ],
        }
    )

    fields = {f"{item['store']}.{item['field']}" for item in validation["warnings"]}
    assert validation["status"] == "warning"
    assert "legacy_store.migration" in fields
    assert "stale_store.migration.applied_schema_version" in fields


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


def _write_outcome_history_state(tmp_path: Path) -> None:
    state_path = tmp_path / "data" / "research" / "metadata" / "outcome_history_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "schema_version": 1,
        "artifact_type": "outcome_history_state",
        "updated_at": "2026-06-05T00:00:00Z",
        "status": "ok",
        "storage_path": "data/research/outcomes",
        "history_path": "data/research/outcomes/outcome_history.json",
        "state_path": "data/research/metadata/outcome_history_state.json",
        "totals": {
            "records": 2,
            "incoming_records": 2,
            "inserted_records": 2,
            "updated_records": 0,
            "duplicate_records": 0,
            "conflicting_duplicates": 0,
            "warning_count": 0,
            "error_count": 0,
        },
        "sources": [{"source_run_id": "source-run", "record_count": 2}],
        "target_kinds": [{"value": "market_signal", "record_count": 2}],
        "outcome_states": [{"value": "aligned", "record_count": 2}],
        "evaluation_statuses": [{"value": "evaluated", "record_count": 2}],
        "warnings": [],
        "errors": [],
        "source_artifacts": ["runs/run-1/analysis/outcome_evaluations.json"],
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def _write_derivatives_market_metadata(tmp_path: Path) -> None:
    metadata_dir = tmp_path / "data" / "market" / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    schema = {
        "schema_version": 1,
        "artifact_type": "derivatives_market_schema",
        "identity": ["source", "market_type", "data_class", "symbol", "period", "as_of"],
    }
    state = {
        "schema_version": 1,
        "artifact_type": "derivatives_market_state",
        "updated_at": "2026-06-05T00:00:00Z",
        "status": "warning",
        "storage_path": "data/market/derivatives",
        "totals": {
            "records": 3,
            "incoming_records": 4,
            "inserted_records": 3,
            "duplicate_records": 1,
            "conflicting_duplicates": 0,
        },
        "groups": [
            {
                "source": "binance_usdm",
                "data_class": "funding_rate",
                "symbol": "BTCUSDT",
                "period": "8h",
                "row_count": 3,
            }
        ],
        "warnings": ["one duplicate derivatives record ignored."],
        "errors": [],
    }
    (metadata_dir / "derivatives_market_schema.json").write_text(
        json.dumps(schema, ensure_ascii=False),
        encoding="utf-8",
    )
    (metadata_dir / "derivatives_market_state.json").write_text(
        json.dumps(state, ensure_ascii=False),
        encoding="utf-8",
    )


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
