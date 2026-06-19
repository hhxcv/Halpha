from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from halpha.analysis.factor_signal_material import build_factor_signal_material
from halpha.pipeline import PipelineError, RunContext
from halpha.storage import write_json


def test_factor_signal_material_writes_bounded_records_and_boundaries(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_upstream_artifacts(run)

    artifacts = build_factor_signal_material({}, run)

    assert artifacts == ["analysis/factor_signal_material.md"]
    material = (run.analysis_dir / "factor_signal_material.md").read_text(encoding="utf-8")
    assert "artifact_type: analysis_factor_signal_material" in material
    assert "## source_policy" in material
    assert "## factor_signal_overview" in material
    assert "## taxonomy" in material
    assert "## selected_multi_source_signals" in material
    assert "## selected_factor_states" in material
    assert "## selected_feature_snapshots" in material
    assert "## data_quality" in material
    assert "## omissions" in material
    assert "## report_usage_rules" in material
    assert "codex_may_explain_factor_signal_material: true" in material
    assert "codex_may_generate_feature_records: false" in material
    assert "codex_may_generate_factor_scores: false" in material
    assert "codex_may_generate_factor_states: false" in material
    assert "codex_may_generate_signal_states: false" in material
    assert "codex_may_generate_action_levels: false" in material
    assert "codex_may_generate_price_forecasts: false" in material
    assert "codex_may_create_trading_instructions: false" in material
    assert "selected_records_only: true" in material
    assert "full_feature_snapshots_json_embedded: false" in material
    assert "full_factor_states_json_embedded: false" in material
    assert "full_multi_source_signals_json_embedded: false" in material
    assert "full_raw_streams_embedded: false" in material
    assert "full_reusable_histories_embedded: false" in material
    assert "- analysis/feature_snapshots.json" in material
    assert "- analysis/factor_states.json" in material
    assert "- analysis/multi_source_signals.json" in material
    assert "feature_records_omitted: 12" in material
    assert "factor_records_omitted: 13" in material
    assert "multi_source_signal_records_omitted: 10" in material
    assert "feature:failed" in material
    assert "factor:failed:global" in material
    assert "multi_source_signal:conflicting" in material
    assert "RAW_STREAM_SENTINEL_SHOULD_NOT_APPEAR" not in material

    assert run.manifest["artifacts"]["factor_signal_material"] == "analysis/factor_signal_material.md"
    assert run.manifest["counts"]["factor_signal_material_records"] == 9
    assert run.manifest["counts"]["factor_signal_material_omitted_records"] == 35
    assert run.manifest["factor_signal_material"]["selected_feature_records"] == 2
    assert run.manifest["factor_signal_material"]["selected_factor_records"] == 4
    assert run.manifest["factor_signal_material"]["selected_multi_source_signal_records"] == 3


def test_factor_signal_material_requires_upstream_artifacts(tmp_path: Path) -> None:
    run = _run_context(tmp_path)

    with pytest.raises(PipelineError) as error:
        build_factor_signal_material({}, run)

    assert str(error.value) == (
        "analysis/feature_snapshots.json was not found; build_feature_snapshots must run first."
    )


def _write_upstream_artifacts(run: RunContext) -> None:
    feature_records = [
        _feature("feature:failed", status="failed", direction_hint="unknown"),
        _feature("feature:cautionary", status="available", direction_hint="cautionary"),
        *[
            _feature(f"feature:low:{index:02d}", status="available", direction_hint="neutral")
            for index in range(12)
        ],
    ]
    factor_records = [
        _factor("factor:failed:global", state="failed", direction="unknown", score=0.0),
        *[
            _factor(f"factor:trend:BTCUSDT:1d:{index:02d}", state="supportive", direction="supportive", score=0.6)
            for index in range(16)
        ],
    ]
    signal_records = [
        _signal("multi_source_signal:conflicting", state="conflicting", direction="conflicting", score=0.0),
        *[
            _signal(f"multi_source_signal:BTCUSDT:1d:{index:02d}", state="supportive", direction="supportive", score=0.5)
            for index in range(12)
        ],
    ]
    write_json(
        run.analysis_dir / "feature_snapshots.json",
        {
            "schema_version": 1,
            "artifact_type": "feature_snapshots",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "status": "warning",
            "records": feature_records,
            "coverage": [
                {
                    "source_layer": "market",
                    "source_artifact": "raw/market.json",
                    "status": "available",
                    "record_count": 1,
                },
                {
                    "source_layer": "derivatives_market",
                    "source_artifact": "analysis/derivatives_market_context.json",
                    "status": "missing",
                    "reason": "optional source was not configured.",
                },
            ],
            "counts": {"records": len(feature_records)},
            "warnings": ["feature coverage has a missing optional source."],
            "errors": [],
            "source_artifacts": ["raw/market.json"],
        },
    )
    write_json(
        run.analysis_dir / "factor_states.json",
        {
            "schema_version": 1,
            "artifact_type": "factor_states",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "status": "warning",
            "records": factor_records,
            "counts": {"records": len(factor_records)},
            "warnings": ["one factor failed."],
            "errors": [],
            "source_artifacts": ["analysis/feature_snapshots.json"],
        },
    )
    write_json(
        run.analysis_dir / "multi_source_signals.json",
        {
            "schema_version": 1,
            "artifact_type": "multi_source_signals",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "status": "warning",
            "records": signal_records,
            "counts": {"records": len(signal_records)},
            "warnings": ["one signal is conflicting."],
            "errors": [],
            "source_artifacts": ["analysis/factor_states.json"],
        },
    )


def _feature(feature_id: str, *, status: str, direction_hint: str) -> dict[str, Any]:
    return {
        "feature_id": feature_id,
        "feature_type": "strategy_direction",
        "factor_family": "trend",
        "source_layer": "market_signals",
        "source_artifact": "analysis/market_signals.json",
        "source_record_id": feature_id,
        "scope": {"symbol": "BTCUSDT", "timeframe": "1d", "asset": None, "chain": None, "region": None},
        "observed_at": "2026-06-05T00:00:00Z",
        "calculation_window": {"start": "2026-06-01T00:00:00Z", "end": "2026-06-05T00:00:00Z", "row_count": 4},
        "value": 1,
        "value_unit": "ordinal_strength",
        "direction_hint": direction_hint,
        "status": status,
        "confidence": "medium",
        "evidence": [f"{feature_id} evidence"],
        "uncertainty": ["feature values are bounded summaries only."],
        "warnings": ["feature warning"] if status != "available" else [],
        "errors": [{"message": "feature failed"}] if status == "failed" else [],
        "source_artifacts": ["analysis/market_signals.json"],
        "raw_records": ["RAW_STREAM_SENTINEL_SHOULD_NOT_APPEAR"],
    }


def _factor(factor_id: str, *, state: str, direction: str, score: float) -> dict[str, Any]:
    return {
        "factor_id": factor_id,
        "factor_type": "trend",
        "scope": {"symbol": "BTCUSDT", "timeframe": "1d", "asset": None, "chain": None, "region": None},
        "state": state,
        "direction": direction,
        "score": score,
        "score_unit": "bounded_-1_to_1",
        "confidence": "medium",
        "calculation_window": {"start": "2026-06-01T00:00:00Z", "end": "2026-06-05T00:00:00Z", "feature_count": 2},
        "input_feature_ids": ["feature:cautionary"],
        "evidence": [f"{factor_id} evidence"],
        "uncertainty": ["factor evidence is bounded."],
        "warnings": ["factor warning"] if state == "failed" else [],
        "errors": [{"message": "factor failed"}] if state == "failed" else [],
        "source_artifacts": ["analysis/feature_snapshots.json"],
    }


def _signal(signal_id: str, *, state: str, direction: str, score: float) -> dict[str, Any]:
    return {
        "signal_id": signal_id,
        "signal_type": "multi_source_market_context",
        "scope": {"symbol": "BTCUSDT", "timeframe": "1d", "asset": None, "chain": None, "region": None},
        "state": state,
        "direction": direction,
        "score": score,
        "score_unit": "bounded_-1_to_1",
        "confidence": "medium",
        "factor_score_summary": {"factor_count": 2, "average_score": score},
        "supportive_factor_ids": ["factor:trend:BTCUSDT:1d:00"] if direction == "supportive" else [],
        "cautionary_factor_ids": [],
        "neutral_factor_ids": [],
        "conflicting_factor_ids": ["factor:failed:global"] if state == "conflicting" else [],
        "insufficient_factor_ids": [],
        "degraded_factor_ids": [],
        "failed_factor_ids": [],
        "evidence": [f"{signal_id} evidence"],
        "uncertainty": ["signal evidence is bounded."],
        "warnings": ["signal warning"] if state == "conflicting" else [],
        "errors": [],
        "source_artifacts": ["analysis/factor_states.json"],
        "created_at": "2026-06-05T00:00:00Z",
    }


def _run_context(tmp_path: Path) -> RunContext:
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
        config_path=tmp_path / "config.yaml",
        manifest={"artifacts": {}, "counts": {}, "errors": []},
    )
