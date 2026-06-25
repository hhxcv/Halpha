from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from halpha.config import load_config
from halpha.decision.feature_snapshots import build_feature_snapshots
from halpha.pipeline import RunContext, run_pipeline
from halpha.storage import write_json


pytestmark = pytest.mark.usefixtures("isolate_artifact_cwd")


def test_feature_snapshots_pipeline_writes_market_and_onchain_records(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, onchain_enabled=True)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="synthesize_intelligence",
        stage_handlers={
            "collect_market_data": _write_raw_market,
            "collect_onchain_flow_data": _noop_stage,
            "sync_onchain_flow_history": _noop_stage,
            "build_onchain_flow_views": _noop_stage,
            "build_onchain_flow_context": _write_onchain_context,
            "build_onchain_flow_material": _noop_stage,
            "build_data_quality_summary": _write_data_quality_ok,
            "build_outcome_targets": _write_outcome_targets,
            "evaluate_outcomes": _write_outcome_evaluations,
        },
    )

    assert result.succeeded is True
    artifact = _feature_snapshots(result.run)
    manifest = _manifest(result.run)
    feature_types = {record["feature_type"] for record in artifact["records"]}
    coverage = {(item["source_layer"], item["status"]) for item in artifact["coverage"]}

    assert artifact["artifact_type"] == "feature_snapshots"
    assert "price_trend" in feature_types
    assert "onchain_liquidity_context" in feature_types
    assert ("market", "available") in coverage
    assert ("onchain_flow", "available") in coverage
    assert ("market_signals", "skipped") in coverage
    assert manifest["artifacts"]["feature_snapshots"] == "analysis/feature_snapshots.json"
    assert manifest["counts"]["feature_snapshots"] == len(artifact["records"])
    assert manifest["feature_snapshots"]["features_by_type"]["price_trend"] == 1
    assert manifest["feature_snapshots"]["source_status_counts"]["available"] >= 2
    assert _stage(manifest, "build_feature_snapshots")["artifacts"] == [
        "analysis/feature_snapshots.json"
    ]


def test_feature_snapshots_records_missing_enabled_optional_sources_without_fake_records(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_raw_market({}, run)
    _write_data_quality_ok({}, run)

    build_feature_snapshots(
        {
            "market": {"enabled": True},
            "quant": {"enabled": True},
            "onchain_flow": {"enabled": True},
        },
        run,
        now="2026-06-05T00:00:00Z",
    )

    artifact = _feature_snapshots(run)
    missing = {
        item["source_layer"]: item
        for item in artifact["coverage"]
        if item["status"] == "missing"
    }

    assert artifact["status"] == "degraded"
    assert "market_signals" in missing
    assert "onchain_flow" in missing
    assert all(record["source_layer"] != "onchain_flow" for record in artifact["records"])
    assert any(record["feature_type"] == "price_trend" for record in artifact["records"])
    assert artifact["counts"]["source_status_counts"]["missing"] >= 2


def test_feature_snapshots_preserve_stale_and_degraded_states(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_stale_onchain_context({}, run)
    _write_data_quality_degraded({}, run)

    build_feature_snapshots(
        {
            "market": {"enabled": False},
            "onchain_flow": {"enabled": True},
        },
        run,
        now="2026-06-05T00:00:00Z",
    )

    artifact = _feature_snapshots(run)
    onchain = next(record for record in artifact["records"] if record["source_layer"] == "onchain_flow")
    quality = next(record for record in artifact["records"] if record["source_layer"] == "data_quality")

    assert onchain["status"] == "stale"
    assert onchain["direction_hint"] == "cautionary"
    assert "latest on-chain observation is stale." in onchain["warnings"]
    assert quality["status"] == "degraded"
    assert quality["direction_hint"] == "cautionary"
    assert artifact["counts"]["status_counts"]["stale"] == 1
    assert artifact["counts"]["status_counts"]["degraded"] == 1


def _write_config(tmp_path: Path, *, onchain_enabled: bool = False) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
run:
  output_dir: runs
  timezone: Asia/Shanghai
market:
  enabled: true
  source: binance
  symbols:
    - BTCUSDT
onchain_flow:
  enabled: {"true" if onchain_enabled else "false"}
  source: public_aggregate
  data_classes:
    - stablecoin_supply
  assets:
    - ALL_STABLECOINS
  chains:
    - all
  lookback_days: 7
text:
  enabled: false
report:
  title: Daily Market Brief
  language: zh-CN
codex:
  enabled: true
  command: codex
  args:
    - exec
    - --sandbox
    - read-only
    - "-"
  timeout_seconds: 300
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _run_context(tmp_path: Path) -> RunContext:
    run_dir = tmp_path / "run"
    raw_dir = run_dir / "raw"
    analysis_dir = run_dir / "analysis"
    codex_context_dir = run_dir / "codex_context"
    report_dir = run_dir / "report"
    for directory in (raw_dir, analysis_dir, codex_context_dir, report_dir):
        directory.mkdir(parents=True, exist_ok=True)
    return RunContext(
        run_id="test-run",
        run_dir=run_dir,
        raw_dir=raw_dir,
        analysis_dir=analysis_dir,
        codex_context_dir=codex_context_dir,
        report_dir=report_dir,
        manifest_path=run_dir / "run_manifest.json",
        config_path=tmp_path / "config.yaml",
        manifest={"artifacts": {}, "counts": {}, "stages": [], "codex": {}, "errors": []},
    )


def _write_raw_market(config: dict[str, Any], run: RunContext) -> list[str]:
    write_json(
        run.raw_dir / "market.json",
        {
            "schema_version": 1,
            "artifact_type": "market_raw",
            "collector": "market",
            "collection_method": "public_http",
            "source": {"name": "binance", "url": "https://data-api.binance.vision"},
            "collected_at": "2026-06-05T00:30:00Z",
            "items": [
                {
                    "id": "market:binance:BTCUSDT:2026-06-05T00:30:00Z",
                    "symbol": "BTCUSDT",
                    "as_of": "2026-06-05T00:30:00Z",
                    "metrics": {
                        "price": "68000.00",
                        "change_24h_pct": "1.25",
                        "volume_24h": "123.45",
                        "quote_volume_24h": "8394600.00",
                    },
                    "source": {"name": "binance", "url": "https://data-api.binance.vision"},
                }
            ],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["raw_market"] = "raw/market.json"
    run.manifest["counts"]["market_items"] = 1
    return ["raw/market.json"]


def _write_onchain_context(config: dict[str, Any], run: RunContext) -> list[str]:
    write_json(
        run.analysis_dir / "onchain_flow_context.json",
        {
            "schema_version": 1,
            "artifact_type": "onchain_flow_context",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:30:00Z",
            "status": "ok",
            "records": [
                {
                    "context_id": "onchain_context:stablecoin_supply:BTC:ethereum:2026-06-05",
                    "context_type": "stablecoin_liquidity",
                    "data_class": "stablecoin_supply",
                    "asset": "BTC",
                    "chain": "ethereum",
                    "as_of": "2026-06-05T00:00:00Z",
                    "status": "succeeded",
                    "state": "supply_expansion",
                    "severity": "medium",
                    "confidence": "medium",
                    "metrics": {"change_pct": 0.03},
                    "evidence": ["Stablecoin supply expanded in the current window."],
                    "uncertainty": [],
                    "warnings": [],
                    "errors": [],
                    "source_artifacts": ["analysis/onchain_flow_context.json", "raw/onchain_flow_views.json"],
                }
            ],
            "counts": {"records": 1, "warnings": 0, "errors": 0},
            "warnings": [],
            "errors": [],
            "source_artifacts": ["raw/onchain_flow_views.json"],
        },
    )
    run.manifest["artifacts"]["onchain_flow_context"] = "analysis/onchain_flow_context.json"
    return ["analysis/onchain_flow_context.json"]


def _write_stale_onchain_context(config: dict[str, Any], run: RunContext) -> list[str]:
    _write_onchain_context(config, run)
    artifact = json.loads((run.analysis_dir / "onchain_flow_context.json").read_text(encoding="utf-8"))
    artifact["status"] = "warning"
    artifact["records"][0]["status"] = "stale"
    artifact["records"][0]["state"] = "stale"
    artifact["records"][0]["warnings"] = ["latest on-chain observation is stale."]
    write_json(run.analysis_dir / "onchain_flow_context.json", artifact)
    return ["analysis/onchain_flow_context.json"]


def _write_data_quality_ok(config: dict[str, Any], run: RunContext) -> list[str]:
    write_json(
        run.analysis_dir / "data_quality_summary.json",
        {
            "schema_version": 1,
            "artifact_type": "data_quality_summary",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:30:00Z",
            "status": "ok",
            "checks": [
                {
                    "name": "raw_market",
                    "layer": "raw",
                    "status": "ok",
                    "summary": "1 market item(s).",
                    "artifacts": ["raw/market.json"],
                    "details": {"warnings": [], "errors": []},
                }
            ],
            "counts": {"checks": 1, "ok": 1, "warning": 0, "degraded": 0, "skipped": 0, "failed": 0, "warnings": 0, "errors": 0},
            "warnings": [],
            "errors": [],
            "source_artifacts": ["raw/market.json"],
        },
    )
    run.manifest["artifacts"]["data_quality_summary"] = "analysis/data_quality_summary.json"
    return ["analysis/data_quality_summary.json"]


def _write_data_quality_degraded(config: dict[str, Any], run: RunContext) -> list[str]:
    _write_data_quality_ok(config, run)
    artifact = json.loads((run.analysis_dir / "data_quality_summary.json").read_text(encoding="utf-8"))
    artifact["status"] = "degraded"
    artifact["counts"]["degraded"] = 1
    artifact["counts"]["warnings"] = 1
    artifact["warnings"] = ["raw_market timestamp is stale."]
    write_json(run.analysis_dir / "data_quality_summary.json", artifact)
    return ["analysis/data_quality_summary.json"]


def _write_outcome_targets(config: dict[str, Any], run: RunContext) -> list[str]:
    write_json(
        run.analysis_dir / "outcome_targets.json",
        {
            "schema_version": 1,
            "artifact_type": "outcome_targets",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:30:00Z",
            "status": "ok",
            "targets": [],
            "counts": {"targets": 0},
            "warnings": [],
            "errors": [],
            "source_artifacts": [],
        },
    )
    return ["analysis/outcome_targets.json"]


def _write_outcome_evaluations(config: dict[str, Any], run: RunContext) -> list[str]:
    write_json(
        run.analysis_dir / "outcome_evaluations.json",
        {
            "schema_version": 1,
            "artifact_type": "outcome_evaluations",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:30:00Z",
            "status": "ok",
            "evaluations": [],
            "counts": {"evaluations": 0},
            "warnings": [],
            "errors": [],
            "source_artifacts": ["analysis/outcome_targets.json"],
        },
    )
    return ["analysis/outcome_evaluations.json"]


def _noop_stage(config: dict[str, Any], run: RunContext) -> list[str]:
    return []


def _feature_snapshots(run: RunContext) -> dict[str, Any]:
    return json.loads((run.analysis_dir / "feature_snapshots.json").read_text(encoding="utf-8"))


def _manifest(run: RunContext) -> dict[str, Any]:
    return json.loads(run.manifest_path.read_text(encoding="utf-8"))


def _stage(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    return next(
        task
        for stage in manifest["stages"]
        for task in stage.get("tasks", [])
        if task["name"] == name
    )
