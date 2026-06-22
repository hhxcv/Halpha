from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from halpha.config import load_config
from halpha.decision.decision_material import (
    decision_material_record_count,
    render_decision_intelligence_material,
    validate_decision_material_inputs,
)
from halpha.pipeline import run_pipeline
from halpha.storage import write_json


def test_decision_intelligence_material_summarizes_m3_artifacts(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_decision_intelligence_material",
        now=datetime(2026, 6, 5, tzinfo=timezone.utc),
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "sync_ohlcv": _noop_stage,
            "build_market_data_views": _noop_stage,
            "evaluate_quant_strategies": _noop_stage,
            "evaluate_strategy_evaluation": _noop_stage,
            "evaluate_market_strategy_signals": _noop_stage,
            "build_market_signals": _noop_stage,
            "build_market_signal_material": _noop_stage,
            "build_market_regime_assessment": _write_market_regime_assessment,
            "build_risk_assessment": _write_risk_assessment,
            "build_decision_recommendations": _write_decision_recommendations,
            "build_watch_triggers": _write_watch_triggers,
            "build_decision_intelligence_delta": _write_decision_delta,
        },
    )

    assert result.succeeded is True
    material = (result.run.analysis_dir / "decision_intelligence_material.md").read_text(encoding="utf-8")
    artifacts = _decision_material_inputs(result)
    manifest = _manifest(result)

    validate_decision_material_inputs(artifacts)
    assert decision_material_record_count(artifacts) == 1
    assert render_decision_intelligence_material(artifacts, run_id=result.run.run_id) == material

    assert "artifact_type: analysis_decision_intelligence_material" in material
    assert "schema_version: 1" in material
    assert f"run_id: {result.run.run_id}" in material
    for artifact in [
        "analysis/market_regime_assessment.json",
        "analysis/risk_assessment.json",
        "analysis/decision_recommendations.json",
        "analysis/watch_triggers.json",
        "analysis/decision_intelligence_delta.json",
    ]:
        assert artifact in material
    for section in [
        "## source_policy",
        "## decision_overview",
        "## regime",
        "## risk",
        "## recommendations",
        "## do_not_do",
        "## invalidation_conditions",
        "## watch_triggers",
        "## delta_vs_previous_run",
        "## evidence_conflicts_uncertainty",
        "## report_usage_rules",
        "## record: decision_recommendation:binance:BTCUSDT:1d:2026-06-03T00:00:00Z",
    ]:
        assert section in material
    assert "research_decision_support_only: true" in material
    assert "trading_execution: false" in material
    assert "return_promise: false" in material
    assert "codex_may_explain_not_infer_action_levels: true" in material
    assert "source: binance" in material
    assert "symbol: BTCUSDT" in material
    assert "timeframe: 1d" in material
    assert "regime: mixed" in material
    assert "risk_level: high" in material
    assert "action_level: WATCH" in material
    assert "decision_bias: wait_for_conflict_resolution" in material
    assert "Do not upgrade this watch state into a stronger action while risk_level=high." in material
    assert "BTCUSDT risk_level falls below high." in material
    assert "field: risk_level" in material
    assert "from: low" in material
    assert "to: high" in material

    assert manifest["artifacts"]["decision_intelligence_material"] == "analysis/decision_intelligence_material.md"
    assert manifest["counts"]["decision_intelligence_material_records"] == 1
    assert manifest["decision_intelligence"]["artifacts"]["decision_intelligence_material"] == (
        "analysis/decision_intelligence_material.md"
    )
    assert manifest["decision_intelligence"]["counts"]["decision_material_records"] == 1
    assert _stage(manifest, "build_decision_intelligence_material")["artifacts"] == [
        "analysis/decision_intelligence_material.md"
    ]
    assert _stage(manifest, "build_analysis_materials")["status"] == "not_run"


def test_decision_intelligence_material_skips_when_quant_is_not_enabled(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, quant_enabled=False)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "sync_ohlcv": _noop_stage,
            "build_market_data_views": _noop_stage,
            "evaluate_quant_strategies": _noop_stage,
            "evaluate_strategy_evaluation": _noop_stage,
            "evaluate_market_strategy_signals": _noop_stage,
            "build_market_signals": _noop_stage,
            "build_market_signal_material": _noop_stage,
            "build_analysis_materials": _noop_stage,
            "build_research_context": _noop_stage,
            "build_codex_context": _noop_stage,
            "run_codex_report": _noop_stage,
        },
    )

    manifest = _manifest(result)
    assert result.succeeded is True
    assert not (result.run.analysis_dir / "decision_intelligence_material.md").exists()
    assert "decision_intelligence_material" not in manifest["artifacts"]
    assert manifest["counts"]["decision_intelligence_material_records"] == 0
    assert _stage(manifest, "build_decision_intelligence_material")["artifacts"] == []


def _write_config(tmp_path: Path, *, quant_enabled: bool = True) -> Path:
    ohlcv_block = (
        """
  ohlcv:
    storage_dir: data/market/ohlcv
    timeframes:
      - 1d
    lookback:
      1d: 3
"""
        if quant_enabled
        else ""
    )
    quant_block = (
        """
quant:
  enabled: true
  engine: vectorbt
  strategies:
    - name: tsmom_vol_scaled
"""
        if quant_enabled
        else """
quant:
  enabled: false
"""
    )
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
{ohlcv_block.rstrip()}
{quant_block.rstrip()}
text:
  enabled: false
report:
  title: Daily Market Brief
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _write_market_regime_assessment(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "market_regime_assessment.json",
        {
            "schema_version": 1,
            "artifact_type": "market_regime_assessment",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["analysis/market_signals.json"],
            "records": [
                {
                    "record_id": "market_regime:binance:BTCUSDT:1d:2026-06-03T00:00:00Z",
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "latest_candle_time": "2026-06-03T00:00:00Z",
                    "regime": "mixed",
                    "confidence": "medium",
                    "status": "partial",
                    "evidence": ["direction_counts: bullish=1, bearish=1."],
                    "conflicts": ["Bullish and bearish market signals conflict."],
                    "uncertainty": ["Strategy directions conflict."],
                    "warnings": ["One upstream signal has weak evidence."],
                    "source_artifacts": ["analysis/market_signals.json"],
                }
            ],
            "warnings": ["One upstream signal has weak evidence."],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["market_regime_assessment"] = "analysis/market_regime_assessment.json"
    return ["analysis/market_regime_assessment.json"]


def _write_risk_assessment(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "risk_assessment.json",
        {
            "schema_version": 1,
            "artifact_type": "risk_assessment",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["analysis/market_regime_assessment.json"],
            "records": [
                {
                    "record_id": "risk_assessment:binance:BTCUSDT:1d:2026-06-03T00:00:00Z",
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "latest_candle_time": "2026-06-03T00:00:00Z",
                    "risk_level": "high",
                    "status": "succeeded",
                    "rising_risks": ["Market regime is mixed."],
                    "blocking_risks": ["Mixed market regime blocks stronger action levels."],
                    "data_quality_risks": [],
                    "signal_conflict_risks": ["Market regime assessment reports material signal conflict."],
                    "gates": {"block_strong_action": True, "cap_action_level": "WATCH"},
                    "evidence": ["market_regime=mixed; confidence=medium; status=partial."],
                    "warnings": [],
                    "errors": [],
                    "source_artifacts": ["analysis/market_regime_assessment.json"],
                }
            ],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["risk_assessment"] = "analysis/risk_assessment.json"
    return ["analysis/risk_assessment.json"]


def _write_decision_recommendations(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "decision_recommendations.json",
        {
            "schema_version": 1,
            "artifact_type": "decision_recommendations",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "action_taxonomy": ["WATCH", "TRY_SMALL"],
            "source_artifacts": ["analysis/risk_assessment.json"],
            "records": [
                {
                    "record_id": "decision_recommendation:binance:BTCUSDT:1d:2026-06-03T00:00:00Z",
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "latest_candle_time": "2026-06-03T00:00:00Z",
                    "action_level": "WATCH",
                    "decision_bias": "wait_for_conflict_resolution",
                    "confidence": "medium",
                    "status": "watch",
                    "recommended_actions": ["Watch BTCUSDT until signal conflict resolves."],
                    "do_not_do": ["Do not upgrade this watch state into a stronger action while risk_level=high."],
                    "risk_conditions": ["risk_level=high; cap_action_level=WATCH."],
                    "invalidation_conditions": ["BTCUSDT risk_level falls below high."],
                    "evidence": ["action_level=WATCH due to mixed regime and high risk."],
                    "conflicts": ["Bullish and bearish market signals conflict."],
                    "warnings": ["Major upstream signal conflict caps action strength at WATCH."],
                    "source_artifacts": ["analysis/risk_assessment.json"],
                }
            ],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["decision_recommendations"] = "analysis/decision_recommendations.json"
    return ["analysis/decision_recommendations.json"]


def _write_watch_triggers(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "watch_triggers.json",
        {
            "schema_version": 1,
            "artifact_type": "watch_triggers",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "trigger_types": ["risk_relief", "wait_condition"],
            "source_artifacts": ["analysis/decision_recommendations.json"],
            "records": [
                {
                    "trigger_id": "watch_trigger:binance:BTCUSDT:1d:risk_relief:2026-06-03T00:00:00Z",
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "type": "risk_relief",
                    "condition": "BTCUSDT risk_level falls below high.",
                    "priority": "medium",
                    "expected_decision_impact": "could_upgrade_watch_to_try_small",
                    "linked_decision_record_id": (
                        "decision_recommendation:binance:BTCUSDT:1d:2026-06-03T00:00:00Z"
                    ),
                    "evidence": ["risk_level=high; cap_action_level=WATCH."],
                    "source_artifacts": ["analysis/decision_recommendations.json"],
                }
            ],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["watch_triggers"] = "analysis/watch_triggers.json"
    return ["analysis/watch_triggers.json"]


def _write_decision_delta(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "decision_intelligence_delta.json",
        {
            "schema_version": 1,
            "artifact_type": "decision_intelligence_delta",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "status": "compared",
            "previous_run_id": "20260604T000000Z",
            "previous_run_path": "runs/20260604T000000Z",
            "compared_artifacts": {
                "current": {
                    "risk_assessment": "analysis/risk_assessment.json",
                },
                "previous": {
                    "risk_assessment": "analysis/risk_assessment.json",
                },
            },
            "changes": [
                {
                    "change_id": "decision_delta:binance:BTCUSDT:1d:risk_level",
                    "scope": {"source": "binance", "symbol": "BTCUSDT", "timeframe": "1d"},
                    "field": "risk_level",
                    "from": "low",
                    "to": "high",
                    "source_artifacts": ["analysis/risk_assessment.json"],
                }
            ],
            "warnings": [],
            "errors": [],
            "source_artifacts": [
                "analysis/market_regime_assessment.json",
                "analysis/risk_assessment.json",
                "analysis/decision_recommendations.json",
                "analysis/watch_triggers.json",
            ],
        },
    )
    run.manifest["artifacts"]["decision_intelligence_delta"] = "analysis/decision_intelligence_delta.json"
    run.manifest["counts"]["decision_delta_changed_records"] = 1
    run.manifest["decision_intelligence"] = {
        "enabled": True,
        "status": "succeeded",
        "artifacts": {
            "decision_intelligence_delta": "analysis/decision_intelligence_delta.json",
        },
        "counts": {"changed_delta_records": 1},
        "previous_run": {
            "status": "compared",
            "run_id": "20260604T000000Z",
            "path": "runs/20260604T000000Z",
        },
        "warnings": [],
        "errors": [],
    }
    return ["analysis/decision_intelligence_delta.json"]


def _manifest(result) -> dict[str, Any]:
    return json.loads(result.run.manifest_path.read_text(encoding="utf-8"))


def _stage(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    return next(stage for stage in manifest["stages"] if stage["name"] == name)


def _decision_material_inputs(result) -> dict[str, dict[str, Any]]:
    return {
        "market_regime_assessment": json.loads(
            (result.run.analysis_dir / "market_regime_assessment.json").read_text(encoding="utf-8")
        ),
        "risk_assessment": json.loads(
            (result.run.analysis_dir / "risk_assessment.json").read_text(encoding="utf-8")
        ),
        "decision_recommendations": json.loads(
            (result.run.analysis_dir / "decision_recommendations.json").read_text(encoding="utf-8")
        ),
        "watch_triggers": json.loads(
            (result.run.analysis_dir / "watch_triggers.json").read_text(encoding="utf-8")
        ),
        "decision_intelligence_delta": json.loads(
            (result.run.analysis_dir / "decision_intelligence_delta.json").read_text(encoding="utf-8")
        ),
    }


def _noop_stage(config, run) -> list[str]:
    return []
