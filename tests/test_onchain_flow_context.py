from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from halpha.config import load_config
from halpha.onchain.onchain_flow_context import build_onchain_flow_context
from halpha.onchain.onchain_flow_history import sync_onchain_flow_history
from halpha.onchain.onchain_flow_views import build_onchain_flow_views
from halpha.pipeline import RunContext, run_pipeline
from halpha.storage import write_json


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_onchain_flow_context_builds_abnormal_activity_congestion_and_unavailable_source(
    tmp_path: Path,
) -> None:
    config_path = _write_config(
        tmp_path,
        data_classes=["stablecoin_supply", "chain_activity", "network_congestion", "exchange_flow_availability"],
    )
    config = load_config(config_path)

    result = _run_until_context(config, config_path, _write_abnormal_raw_stage)

    assert result.succeeded is True
    context = _context(result)
    manifest = _manifest(result)
    stablecoin = _context_record(context, "stablecoin_liquidity")
    activity = _context_record(context, "chain_activity")
    congestion = _context_record(context, "network_congestion")
    exchange = _context_record(context, "exchange_flow_source_availability")

    assert context["status"] == "warning"
    assert context["counts"]["records"] == 4
    assert stablecoin["status"] == "succeeded"
    assert stablecoin["state"] == "sharp_stablecoin_supply_contraction"
    assert stablecoin["severity"] == "high"
    assert stablecoin["metrics"]["stablecoin_supply_change_pct"] == -0.1
    assert stablecoin["thresholds"]["sharp_supply_contraction_change_pct"] == -0.05
    assert stablecoin["evidence"][0]["source_artifact"] == "raw/onchain_flow_views.json"
    assert activity["state"] == "surging_chain_activity"
    assert activity["severity"] == "high"
    assert activity["metrics"]["transaction_count_change_pct"] == 0.6
    assert congestion["state"] == "severe_network_congestion"
    assert congestion["severity"] == "high"
    assert congestion["metrics"]["latest_mempool_size_bytes"] == 120_000_000.0
    assert exchange["status"] == "unavailable"
    assert exchange["state"] == "source_unavailable"
    assert exchange["severity"] == "medium"
    assert any("must not be treated as neutral" in item for item in exchange["uncertainty"])
    assert manifest["artifacts"]["onchain_flow_context"] == "analysis/onchain_flow_context.json"
    assert manifest["counts"]["onchain_flow_context_records"] == 4
    assert manifest["onchain_flow_context"]["exchange_flow_source_availability"] == 1


def test_onchain_flow_context_preserves_partial_status_and_low_confidence(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, data_classes=["stablecoin_supply"])
    config = load_config(config_path)

    result = _run_until_context(config, config_path, _write_partial_raw_stage)

    assert result.succeeded is True
    context = _context(result)
    stablecoin = _context_record(context, "stablecoin_liquidity")

    assert context["status"] == "warning"
    assert stablecoin["status"] == "partial"
    assert stablecoin["state"] == "sharp_stablecoin_supply_expansion"
    assert stablecoin["confidence"] == "low"
    assert stablecoin["errors"] == [
        {
            "source": "defillama_stablecoins",
            "data_class": "stablecoin_supply",
            "message": "one stablecoin row could not be parsed",
            "error_type": "parse_error",
        }
    ]
    assert context["counts"]["partial"] == 1


def test_onchain_flow_context_preserves_stale_input_without_neutralizing(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, data_classes=["stablecoin_supply"])
    config = load_config(config_path)
    old_run = _run_context(tmp_path, config_path, "run-old")
    _write_raw(
        old_run,
        [_stablecoin_item("2026-05-01T00:00:00Z", 1000.0)],
        window_start="2026-05-01T00:00:00Z",
        window_end="2026-05-01T00:00:00Z",
    )
    sync_onchain_flow_history(config, old_run, now="2026-05-01T01:00:00Z")

    result = _run_until_context(config, config_path, _write_stale_raw_stage)

    assert result.succeeded is True
    context = _context(result)
    stablecoin = _context_record(context, "stablecoin_liquidity")

    assert context["status"] == "warning"
    assert stablecoin["status"] == "stale"
    assert stablecoin["state"] == "stale"
    assert stablecoin["severity"] == "medium"
    assert stablecoin["confidence"] == "low"
    assert "view status is stale." in stablecoin["uncertainty"]
    assert context["counts"]["stale"] == 1


def test_onchain_flow_context_records_missing_views_input(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, data_classes=["stablecoin_supply"])
    config = load_config(config_path)
    run = _run_context(tmp_path, config_path, "run-missing")

    artifacts = build_onchain_flow_context(config, run, now="2026-06-18T01:01:00Z")

    context = json.loads((run.analysis_dir / "onchain_flow_context.json").read_text(encoding="utf-8"))

    assert artifacts == ["analysis/onchain_flow_context.json"]
    assert context["status"] == "warning"
    assert context["records"] == []
    assert context["warnings"] == ["onchain_flow_views.json was not found."]
    assert run.manifest["counts"]["onchain_flow_context_records"] == 0
    assert run.manifest["onchain_flow_context"]["status"] == "warning"


def _run_until_context(config: dict[str, Any], config_path: Path, collect_stage):
    return run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_source_evidence",
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_onchain_flow_data": collect_stage,
            "sync_onchain_flow_history": lambda config, run: sync_onchain_flow_history(
                config,
                run,
                now="2026-06-18T01:00:00Z",
            ),
            "build_onchain_flow_views": lambda config, run: build_onchain_flow_views(
                config,
                run,
                now="2026-06-18T01:01:00Z",
            ),
            "build_onchain_flow_context": lambda config, run: build_onchain_flow_context(
                config,
                run,
                now="2026-06-18T01:02:00Z",
            ),
        },
    )


def _write_config(tmp_path: Path, *, data_classes: list[str]) -> Path:
    data_class_lines = "\n".join(f"    - {item}" for item in data_classes)
    path = tmp_path / "config.yaml"
    path.write_text(
        f"""
run:
  output_dir: runs
market:
  enabled: true
  source: binance
  symbols:
    - BTCUSDT
macro_calendar:
  enabled: false
onchain_flow:
  enabled: true
  source: public_aggregate
  data_classes:
{data_class_lines}
  assets:
    - ALL_STABLECOINS
    - BTC
  chains:
    - all
    - bitcoin
  lookback_days: 7
text:
  enabled: false
report:
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return path


def _write_abnormal_raw_stage(config: dict[str, Any], run: RunContext) -> list[str]:
    items = [
        _stablecoin_item("2026-06-11T00:00:00Z", 1000.0),
        _stablecoin_item("2026-06-18T00:00:00Z", 900.0),
        _chain_item("chain_activity", "2026-06-11T00:00:00Z", "transaction_count", 1000.0),
        _chain_item("chain_activity", "2026-06-18T00:00:00Z", "transaction_count", 1600.0),
        _chain_item("network_congestion", "2026-06-11T00:00:00Z", "mempool_size_bytes", 10_000_000.0),
        _chain_item("network_congestion", "2026-06-18T00:00:00Z", "mempool_size_bytes", 120_000_000.0),
    ]
    _write_raw(
        run,
        items,
        availability=[
            _availability("defillama_stablecoins", "stablecoin_supply", "succeeded", len(items[:2])),
            _availability("blockchain_com_charts", "chain_activity", "succeeded", 2),
            _availability("blockchain_com_charts", "network_congestion", "succeeded", 2),
            _exchange_unavailable_availability(),
        ],
    )
    run.manifest["artifacts"]["raw_onchain_flow"] = "raw/onchain_flow.json"
    return ["raw/onchain_flow.json"]


def _write_partial_raw_stage(config: dict[str, Any], run: RunContext) -> list[str]:
    errors = [
        {
            "source": "defillama_stablecoins",
            "endpoint": "stablecoincharts_all",
            "data_class": "stablecoin_supply",
            "error_type": "parse_error",
            "message": "one stablecoin row could not be parsed",
        }
    ]
    _write_raw(
        run,
        [
            _stablecoin_item("2026-06-11T00:00:00Z", 1000.0),
            _stablecoin_item("2026-06-18T00:00:00Z", 1100.0),
        ],
        availability=[
            _availability(
                "defillama_stablecoins",
                "stablecoin_supply",
                "partial",
                2,
                parsed_record_count=3,
                error_count=1,
                reason="stablecoin source parsed with row-level errors.",
            )
        ],
        errors=errors,
    )
    run.manifest["artifacts"]["raw_onchain_flow"] = "raw/onchain_flow.json"
    return ["raw/onchain_flow.json"]


def _write_stale_raw_stage(config: dict[str, Any], run: RunContext) -> list[str]:
    _write_raw(
        run,
        [],
        availability=[
            _availability(
                "defillama_stablecoins",
                "stablecoin_supply",
                "stale",
                0,
                reason="stablecoin source returned no current rows.",
            )
        ],
    )
    run.manifest["artifacts"]["raw_onchain_flow"] = "raw/onchain_flow.json"
    return ["raw/onchain_flow.json"]


def _write_raw(
    run: RunContext,
    items: list[dict[str, Any]],
    *,
    window_start: str = "2026-06-11T00:00:00Z",
    window_end: str = "2026-06-18T00:00:00Z",
    availability: list[dict[str, Any]] | None = None,
    errors: list[dict[str, Any]] | None = None,
) -> None:
    write_json(
        run.raw_dir / "onchain_flow.json",
        {
            "schema_version": 1,
            "artifact_type": "onchain_flow_raw",
            "collector": "onchain_flow",
            "collection_method": "public_http",
            "source": {
                "name": "public_aggregate",
                "url": "https://stablecoins.llama.fi;https://api.blockchain.info",
            },
            "collected_at": "2026-06-18T01:00:00Z",
            "window": {
                "lookback_start": window_start,
                "lookback_end": window_end,
            },
            "items": items,
            "availability": availability or [],
            "warnings": [],
            "errors": errors or [],
        },
    )


def _stablecoin_item(as_of: str, total_circulating_usd: float) -> dict[str, Any]:
    return {
        "item_id": f"onchain_flow:stablecoin_supply:defillama_stablecoins:all:{as_of}",
        "data_class": "stablecoin_supply",
        "source": "defillama_stablecoins",
        "asset": "ALL_STABLECOINS",
        "chain": "all",
        "as_of": as_of,
        "endpoint": "stablecoincharts_all",
        "metrics": {"total_circulating_usd": total_circulating_usd},
        "units": {"total_circulating_usd": "USD"},
        "raw_fields": {"source_url": "https://stablecoins.llama.fi/stablecoincharts/all", "date": as_of},
        "warnings": [],
        "errors": [],
    }


def _chain_item(data_class: str, as_of: str, metric_name: str, value: float) -> dict[str, Any]:
    return {
        "item_id": f"onchain_flow:{data_class}:blockchain_com_charts:bitcoin:{as_of}",
        "data_class": data_class,
        "source": "blockchain_com_charts",
        "asset": "BTC",
        "chain": "bitcoin",
        "as_of": as_of,
        "endpoint": f"blockchain_chart_{data_class}",
        "metrics": {metric_name: value},
        "units": {metric_name: "bytes" if metric_name == "mempool_size_bytes" else "transactions"},
        "raw_fields": {"source_url": "https://api.blockchain.info/charts/example", "x": as_of, "y": value},
        "warnings": [],
        "errors": [],
    }


def _availability(
    source: str,
    data_class: str,
    status: str,
    record_count: int,
    *,
    parsed_record_count: int | None = None,
    error_count: int = 0,
    reason: str | None = None,
) -> dict[str, Any]:
    record = {
        "source": source,
        "data_class": data_class,
        "status": status,
        "record_count": record_count,
        "parsed_record_count": record_count if parsed_record_count is None else parsed_record_count,
        "error_count": error_count,
        "endpoint": f"{data_class}_endpoint",
    }
    if reason is not None:
        record["reason"] = reason
    return record


def _exchange_unavailable_availability() -> dict[str, Any]:
    return {
        "source": "public_aggregate",
        "data_class": "exchange_flow_availability",
        "status": "unavailable",
        "record_count": 0,
        "parsed_record_count": 0,
        "error_count": 0,
        "endpoint": "exchange_flow_periodic_public_source",
        "reason": "missing exchange-flow evidence must not be treated as neutral risk context.",
    }


def _context(result) -> dict[str, Any]:
    return json.loads((result.run.analysis_dir / "onchain_flow_context.json").read_text(encoding="utf-8"))


def _context_record(context: dict[str, Any], context_type: str) -> dict[str, Any]:
    return next(record for record in context["records"] if record["context_type"] == context_type)


def _manifest(result) -> dict[str, Any]:
    return json.loads(result.run.manifest_path.read_text(encoding="utf-8"))


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


def _noop_stage(config, run) -> list[str]:
    return []
