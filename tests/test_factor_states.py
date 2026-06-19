from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from halpha.config import load_config
from halpha.factor_states import build_factor_states
from halpha.pipeline import RunContext, run_pipeline
from halpha.storage import write_json


def test_factor_states_pipeline_writes_agreement_records_and_manifest(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_factor_states",
        stage_handlers={
            "collect_market_data": _noop_stage,
            "build_feature_snapshots": _write_agreement_feature_snapshots,
        },
    )

    assert result.succeeded is True
    artifact = _factor_states(result.run)
    manifest = _manifest(result.run)
    trend = _record(artifact, "trend", symbol="BTCUSDT", timeframe="1d")

    assert artifact["artifact_type"] == "factor_states"
    assert trend["state"] == "supportive"
    assert trend["direction"] == "supportive"
    assert 0.0 < trend["score"] <= 1.0
    assert trend["score_unit"] == "bounded_-1_to_1"
    assert trend["input_feature_ids"] == ["feature:market:btc", "feature:signal:btc"]
    assert trend["calculation_window"]["feature_count"] == 2
    assert "analysis/feature_snapshots.json" in trend["source_artifacts"]
    assert manifest["artifacts"]["factor_states"] == "analysis/factor_states.json"
    assert manifest["counts"]["factor_states"] == len(artifact["records"])
    assert manifest["factor_states"]["factors_by_type"]["trend"] == 1
    assert _stage(manifest, "build_factor_states")["artifacts"] == ["analysis/factor_states.json"]


def test_factor_states_detect_conflicting_feature_directions(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_feature_snapshots(
        run,
        records=[
            _feature("feature:trend:supportive", "trend", direction_hint="supportive"),
            _feature("feature:trend:cautionary", "trend", direction_hint="cautionary"),
        ],
    )

    build_factor_states({}, run, now="2026-06-05T00:00:00Z")

    trend = _record(_factor_states(run), "trend", symbol="BTCUSDT", timeframe="1d")
    assert trend["state"] == "conflicting"
    assert trend["direction"] == "conflicting"
    assert trend["confidence"] == "low"
    assert "Factor has conflicting feature directions." in trend["warnings"]


def test_factor_states_emit_missing_input_states_from_feature_coverage(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_feature_snapshots(
        run,
        records=[],
        coverage=[
            {
                "source_layer": "market_signals",
                "source_artifact": "analysis/market_signals.json",
                "status": "missing",
                "records": 0,
                "warnings": 0,
                "errors": 0,
                "reason": None,
                "error": "market_signals.json was not found.",
                "artifact_status": None,
            }
        ],
    )

    build_factor_states({}, run, now="2026-06-05T00:00:00Z")

    artifact = _factor_states(run)
    trend = _record(artifact, "trend")
    assert trend["state"] == "insufficient_evidence"
    assert trend["direction"] == "unknown"
    assert trend["score"] == 0.0
    assert trend["input_feature_ids"] == []
    assert "market_signals coverage is missing." in trend["warnings"]
    assert artifact["counts"]["state_counts"]["insufficient_evidence"] == 1


def test_factor_states_preserve_stale_and_degraded_input_states(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_feature_snapshots(
        run,
        records=[
            _feature(
                "feature:liquidity:stale",
                "liquidity",
                direction_hint="cautionary",
                status="stale",
                warning="latest liquidity evidence is stale.",
            ),
            _feature(
                "feature:quality:degraded",
                "evidence_quality",
                direction_hint="cautionary",
                status="degraded",
                warning="data quality is degraded.",
            ),
        ],
    )

    build_factor_states({}, run, now="2026-06-05T00:00:00Z")

    artifact = _factor_states(run)
    liquidity = _record(artifact, "liquidity", symbol="BTCUSDT", timeframe="1d")
    quality = _record(artifact, "evidence_quality", symbol="BTCUSDT", timeframe="1d")

    assert liquidity["state"] == "stale"
    assert liquidity["direction"] == "cautionary"
    assert liquidity["confidence"] == "low"
    assert "latest liquidity evidence is stale." in liquidity["warnings"]
    assert quality["state"] == "degraded"
    assert quality["direction"] == "cautionary"
    assert "data quality is degraded." in quality["warnings"]


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  output_dir: runs
  timezone: Asia/Shanghai
market:
  enabled: true
  source: binance
  symbols:
    - BTCUSDT
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


def _write_agreement_feature_snapshots(config: dict[str, Any], run: RunContext) -> list[str]:
    _write_feature_snapshots(
        run,
        records=[
            _feature("feature:market:btc", "trend", source_layer="market", direction_hint="supportive"),
            _feature("feature:signal:btc", "trend", source_layer="market_signals", direction_hint="supportive"),
            _feature("feature:quality:global", "evidence_quality", source_layer="data_quality", direction_hint="supportive"),
        ],
        coverage=[
            {
                "source_layer": "market",
                "source_artifact": "raw/market.json",
                "status": "available",
                "records": 1,
                "warnings": 0,
                "errors": 0,
                "reason": None,
                "error": None,
                "artifact_status": "ok",
            }
        ],
    )
    return ["analysis/feature_snapshots.json"]


def _write_feature_snapshots(
    run: RunContext,
    *,
    records: list[dict[str, Any]],
    coverage: list[dict[str, Any]] | None = None,
) -> None:
    write_json(
        run.analysis_dir / "feature_snapshots.json",
        {
            "schema_version": 1,
            "artifact_type": "feature_snapshots",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "status": "ok",
            "records": records,
            "coverage": coverage or [],
            "counts": {
                "records": len(records),
                "coverage_records": len(coverage or []),
                "features_by_type": {},
                "features_by_source_layer": {},
                "status_counts": {},
                "source_status_counts": {},
                "warnings": 0,
                "errors": 0,
            },
            "warnings": [],
            "errors": [],
            "source_artifacts": ["raw/market.json"],
        },
    )
    run.manifest["artifacts"]["feature_snapshots"] = "analysis/feature_snapshots.json"


def _feature(
    feature_id: str,
    factor_family: str,
    *,
    source_layer: str = "market_signals",
    direction_hint: str,
    status: str = "available",
    warning: str | None = None,
) -> dict[str, Any]:
    return {
        "feature_id": feature_id,
        "feature_type": "strategy_direction" if factor_family == "trend" else "source_quality",
        "factor_family": factor_family,
        "source_layer": source_layer,
        "source_artifact": "analysis/feature_snapshots.json",
        "source_record_id": feature_id,
        "scope": {
            "symbol": "BTCUSDT",
            "timeframe": "1d",
            "asset": None,
            "chain": None,
            "region": None,
        },
        "observed_at": "2026-06-05T00:00:00Z",
        "calculation_window": {
            "start": "2026-06-01T00:00:00Z",
            "end": "2026-06-05T00:00:00Z",
            "row_count": 4,
        },
        "value": 1,
        "value_unit": "ordinal_strength",
        "direction_hint": direction_hint,
        "status": status,
        "confidence": "medium",
        "evidence": [f"{feature_id} evidence"],
        "uncertainty": [],
        "warnings": [warning] if warning else [],
        "errors": [],
        "source_artifacts": ["analysis/feature_snapshots.json"],
    }


def _noop_stage(config: dict[str, Any], run: RunContext) -> list[str]:
    return []


def _factor_states(run: RunContext) -> dict[str, Any]:
    return json.loads((run.analysis_dir / "factor_states.json").read_text(encoding="utf-8"))


def _manifest(run: RunContext) -> dict[str, Any]:
    return json.loads(run.manifest_path.read_text(encoding="utf-8"))


def _record(
    artifact: dict[str, Any],
    factor_type: str,
    *,
    symbol: str | None = None,
    timeframe: str | None = None,
) -> dict[str, Any]:
    for record in artifact["records"]:
        scope = record["scope"]
        if (
            record["factor_type"] == factor_type
            and scope.get("symbol") == symbol
            and scope.get("timeframe") == timeframe
        ):
            return record
    raise AssertionError(f"factor record not found: {factor_type} {symbol} {timeframe}")


def _stage(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    return next(stage for stage in manifest["stages"] if stage["name"] == name)
