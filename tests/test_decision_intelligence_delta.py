from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from halpha.config import load_config
from halpha.decision.decision_delta import build_decision_intelligence_delta_artifact
from halpha.pipeline import run_pipeline
from halpha.storage import write_json


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_decision_delta_artifact_builder_reports_quant_disabled_result() -> None:
    run = SimpleNamespace(manifest={"artifacts": {}, "counts": {}})

    result = build_decision_intelligence_delta_artifact({"quant": {"enabled": False}}, run)

    assert result.artifacts == []
    assert result.enabled is False
    assert result.status == "skipped"
    assert result.reason == "quant_disabled"
    assert result.previous_run == {
        "status": "not_checked",
        "run_id": None,
        "path": None,
    }
    assert result.warnings == []
    assert result.errors == []
    assert run.manifest["counts"]["decision_delta_changed_records"] == 0


def test_decision_intelligence_delta_records_no_previous_run(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_decision_intelligence_delta",
        now=datetime(2026, 6, 5, tzinfo=timezone.utc),
        stage_handlers=_stage_handlers_for_current(
            regime="trend_up",
            risk_level="low",
            action_level="TRY_SMALL",
            decision_bias="tentative_constructive",
            invalidation_conditions=["BTCUSDT risk_level rises to high or extreme."],
            watch_conditions=["BTCUSDT evidence remains aligned."],
        ),
    )

    assert result.succeeded is True
    artifact = _decision_delta(result)
    manifest = _manifest(result)

    assert artifact["artifact_type"] == "decision_intelligence_delta"
    assert artifact["schema_version"] == 1
    assert artifact["run_id"] == result.run.run_id
    assert artifact["status"] == "no_previous_run"
    assert artifact["previous_run_id"] is None
    assert artifact["previous_run_path"] is None
    assert artifact["changes"] == []
    assert artifact["warnings"] == ["No previous successful decision-intelligence run found."]
    assert artifact["errors"] == []
    assert manifest["artifacts"]["decision_intelligence_delta"] == "analysis/decision_intelligence_delta.json"
    assert manifest["counts"]["decision_delta_changed_records"] == 0
    assert manifest["decision_intelligence"]["previous_run"] == {
        "status": "no_previous_run",
        "run_id": None,
        "path": None,
    }
    assert _stage(manifest, "build_decision_intelligence_delta")["artifacts"] == [
        "analysis/decision_intelligence_delta.json"
    ]
    assert _stage(manifest, "build_analysis_materials")["status"] == "not_run"


def test_decision_intelligence_delta_records_changed_fields(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_previous_run(
        tmp_path / "runs" / "20260604T000000Z",
        run_id="20260604T000000Z",
        regime="trend_up",
        risk_level="low",
        action_level="TRY_SMALL",
        decision_bias="tentative_constructive",
        invalidation_conditions=["BTCUSDT risk_level rises to high or extreme."],
        watch_conditions=["BTCUSDT evidence remains aligned."],
    )
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_decision_intelligence_delta",
        now=datetime(2026, 6, 5, tzinfo=timezone.utc),
        stage_handlers=_stage_handlers_for_current(
            regime="mixed",
            risk_level="high",
            action_level="WATCH",
            decision_bias="wait_for_conflict_resolution",
            invalidation_conditions=[],
            watch_conditions=[
                "BTCUSDT signal conflict resolves.",
                "BTCUSDT risk_level falls below high.",
            ],
        ),
    )

    assert result.succeeded is True
    artifact = _decision_delta(result)
    manifest = _manifest(result)
    changes = {change["field"]: change for change in artifact["changes"]}

    assert artifact["status"] == "compared"
    assert artifact["previous_run_id"] == "20260604T000000Z"
    assert artifact["previous_run_path"] == "runs/20260604T000000Z"
    assert set(changes) >= {
        "regime",
        "risk_level",
        "action_level",
        "decision_bias",
        "invalidation_status",
        "major_watch_triggers",
    }
    assert changes["regime"]["from"] == "trend_up"
    assert changes["regime"]["to"] == "mixed"
    assert changes["risk_level"]["from"] == "low"
    assert changes["risk_level"]["to"] == "high"
    assert changes["action_level"]["from"] == "TRY_SMALL"
    assert changes["action_level"]["to"] == "WATCH"
    assert changes["decision_bias"]["from"] == "tentative_constructive"
    assert changes["decision_bias"]["to"] == "wait_for_conflict_resolution"
    assert changes["invalidation_status"]["from"] == "has_invalidation_conditions"
    assert changes["invalidation_status"]["to"] == "no_invalidation_conditions"
    assert "BTCUSDT evidence remains aligned." in changes["major_watch_triggers"]["from"]
    assert "BTCUSDT signal conflict resolves." in changes["major_watch_triggers"]["to"]
    assert all(change["scope"] == {"source": "binance", "symbol": "BTCUSDT", "timeframe": "1d"} for change in artifact["changes"])
    assert all(change["source_artifacts"] for change in artifact["changes"])
    assert manifest["counts"]["decision_delta_changed_records"] == len(artifact["changes"])
    assert manifest["decision_intelligence"]["previous_run"] == {
        "status": "compared",
        "run_id": "20260604T000000Z",
        "path": "runs/20260604T000000Z",
    }


def test_decision_intelligence_delta_skips_when_quant_is_not_enabled(tmp_path: Path) -> None:
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
    assert not (result.run.analysis_dir / "decision_intelligence_delta.json").exists()
    assert "decision_intelligence_delta" not in manifest["artifacts"]
    assert manifest["counts"]["decision_delta_changed_records"] == 0
    assert manifest["decision_intelligence"]["previous_run"] == {
        "status": "not_checked",
        "run_id": None,
        "path": None,
    }
    assert _stage(manifest, "build_decision_intelligence_delta")["artifacts"] == []


def test_decision_intelligence_manifest_records_partial_failure_when_delta_input_is_missing(
    tmp_path: Path,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    handlers = _stage_handlers_for_current(
        regime="mixed",
        risk_level="high",
        action_level="WATCH",
        decision_bias="wait_for_conflict_resolution",
        invalidation_conditions=[],
        watch_conditions=[],
    )
    handlers["build_watch_triggers"] = _noop_stage

    result = run_pipeline(
        config,
        config_path=config_path,
        now=datetime(2026, 6, 5, tzinfo=timezone.utc),
        stage_handlers=handlers,
    )

    assert result.succeeded is False
    assert result.failed_stage == "build_decision_intelligence_delta"
    assert result.reason == "analysis/watch_triggers.json was not found; build_watch_triggers must run first."

    manifest = _manifest(result)
    section = manifest["decision_intelligence"]
    assert section["enabled"] is True
    assert section["status"] == "failed"
    assert section["artifacts"] == {
        "market_regime_assessment": "analysis/market_regime_assessment.json",
        "risk_assessment": "analysis/risk_assessment.json",
        "decision_recommendations": "analysis/decision_recommendations.json",
    }
    assert section["counts"] == {
        "regime_records": 1,
        "risk_records": 1,
        "decision_recommendations": 1,
        "watch_triggers": 0,
        "changed_delta_records": 0,
        "decision_material_records": 0,
    }
    assert section["previous_run"] == {
        "status": "not_checked",
        "run_id": None,
        "path": None,
    }
    assert section["warnings"] == ["Major upstream signal conflict caps action strength at WATCH."]
    assert section["errors"] == [
        "build_decision_intelligence_delta: analysis/watch_triggers.json was not found; "
        "build_watch_triggers must run first."
    ]
    assert _stage(manifest, "build_decision_intelligence_delta")["status"] == "failed"
    assert "decision_intelligence_delta" not in manifest["artifacts"]
    assert "decision_intelligence_material" not in manifest["artifacts"]


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


def _stage_handlers_for_current(
    *,
    regime: str,
    risk_level: str,
    action_level: str,
    decision_bias: str,
    invalidation_conditions: list[str],
    watch_conditions: list[str],
) -> dict[str, Any]:
    return {
        "collect_market_data": _noop_stage,
        "collect_text_events": _noop_stage,
        "sync_ohlcv": _noop_stage,
        "build_market_data_views": _noop_stage,
        "evaluate_quant_strategies": _noop_stage,
        "evaluate_strategy_evaluation": _noop_stage,
        "evaluate_market_strategy_signals": _noop_stage,
        "build_market_signals": _noop_stage,
        "build_market_signal_material": _noop_stage,
        "build_market_regime_assessment": lambda config, run: _write_market_regime_assessment(run, regime=regime),
        "build_risk_assessment": lambda config, run: _write_risk_assessment(run, risk_level=risk_level),
        "build_decision_recommendations": lambda config, run: _write_decision_recommendations(
            run,
            action_level=action_level,
            decision_bias=decision_bias,
            invalidation_conditions=invalidation_conditions,
            risk_level=risk_level,
        ),
        "build_watch_triggers": lambda config, run: _write_watch_triggers(run, conditions=watch_conditions),
    }


def _write_previous_run(
    run_dir: Path,
    *,
    run_id: str,
    regime: str,
    risk_level: str,
    action_level: str,
    decision_bias: str,
    invalidation_conditions: list[str],
    watch_conditions: list[str],
) -> None:
    analysis_dir = run_dir / "analysis"
    analysis_dir.mkdir(parents=True)
    run = _PreviousRun(run_id=run_id, analysis_dir=analysis_dir)
    _write_market_regime_assessment(run, regime=regime)
    _write_risk_assessment(run, risk_level=risk_level)
    _write_decision_recommendations(
        run,
        action_level=action_level,
        decision_bias=decision_bias,
        invalidation_conditions=invalidation_conditions,
        risk_level=risk_level,
    )
    _write_watch_triggers(run, conditions=watch_conditions)
    write_json(
        run_dir / "run_manifest.json",
        {
            "schema_version": 1,
            "run_id": run_id,
            "status": "succeeded",
            "started_at": "2026-06-04T00:00:00Z",
            "finished_at": "2026-06-04T00:01:00Z",
            "artifacts": {
                "market_regime_assessment": "analysis/market_regime_assessment.json",
                "risk_assessment": "analysis/risk_assessment.json",
                "decision_recommendations": "analysis/decision_recommendations.json",
                "watch_triggers": "analysis/watch_triggers.json",
            },
        },
    )


class _PreviousRun:
    def __init__(self, *, run_id: str, analysis_dir: Path) -> None:
        self.run_id = run_id
        self.analysis_dir = analysis_dir
        self.manifest = {"artifacts": {}, "counts": {}}


def _write_market_regime_assessment(run, *, regime: str) -> list[str]:
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
                    "record_id": f"market_regime:binance:BTCUSDT:1d:{run.run_id}",
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "latest_candle_time": "2026-06-03T00:00:00Z",
                    "regime": regime,
                    "confidence": "medium",
                    "status": "succeeded",
                    "evidence": [f"market_regime={regime}."],
                    "conflicts": [],
                    "source_artifacts": ["analysis/market_signals.json"],
                }
            ],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["market_regime_assessment"] = "analysis/market_regime_assessment.json"
    run.manifest["counts"]["market_regime_records"] = 1
    return ["analysis/market_regime_assessment.json"]


def _write_risk_assessment(run, *, risk_level: str) -> list[str]:
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
                    "record_id": f"risk_assessment:binance:BTCUSDT:1d:{run.run_id}",
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "latest_candle_time": "2026-06-03T00:00:00Z",
                    "risk_level": risk_level,
                    "status": "succeeded",
                    "evidence": [f"risk_level={risk_level}."],
                    "source_artifacts": ["analysis/market_regime_assessment.json"],
                }
            ],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["risk_assessment"] = "analysis/risk_assessment.json"
    run.manifest["counts"]["risk_assessment_records"] = 1
    return ["analysis/risk_assessment.json"]


def _write_decision_recommendations(
    run,
    *,
    action_level: str,
    decision_bias: str,
    invalidation_conditions: list[str],
    risk_level: str,
) -> list[str]:
    write_json(
        run.analysis_dir / "decision_recommendations.json",
        {
            "schema_version": 1,
            "artifact_type": "decision_recommendations",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["analysis/risk_assessment.json"],
            "records": [
                {
                    "record_id": "decision_recommendation:binance:BTCUSDT:1d:2026-06-03T00:00:00Z",
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "latest_candle_time": "2026-06-03T00:00:00Z",
                    "action_level": action_level,
                    "decision_bias": decision_bias,
                    "status": "actionable" if invalidation_conditions else "watch",
                    "risk_conditions": [f"risk_level={risk_level}; status=succeeded."],
                    "invalidation_conditions": invalidation_conditions,
                    "evidence": [f"action_level={action_level}."],
                    "source_artifacts": ["analysis/risk_assessment.json"],
                }
            ],
            "warnings": ["Major upstream signal conflict caps action strength at WATCH."]
            if action_level == "WATCH"
            else [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["decision_recommendations"] = "analysis/decision_recommendations.json"
    run.manifest["counts"]["decision_recommendation_records"] = 1
    return ["analysis/decision_recommendations.json"]


def _write_watch_triggers(run, *, conditions: list[str]) -> list[str]:
    write_json(
        run.analysis_dir / "watch_triggers.json",
        {
            "schema_version": 1,
            "artifact_type": "watch_triggers",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["analysis/decision_recommendations.json"],
            "records": [
                {
                    "trigger_id": f"watch_trigger:binance:BTCUSDT:1d:recheck_next_run:2026-06-03T00:00:00Z:{index}",
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "type": "recheck_next_run",
                    "condition": condition,
                    "priority": "low",
                    "expected_decision_impact": "refreshes_current_decision_view",
                    "linked_decision_record_id": "decision_recommendation:binance:BTCUSDT:1d:2026-06-03T00:00:00Z",
                    "evidence": [condition],
                    "source_artifacts": ["analysis/decision_recommendations.json"],
                }
                for index, condition in enumerate(conditions, start=1)
            ],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["watch_triggers"] = "analysis/watch_triggers.json"
    run.manifest["counts"]["watch_trigger_records"] = len(conditions)
    return ["analysis/watch_triggers.json"]


def _decision_delta(result) -> dict[str, Any]:
    return json.loads((result.run.analysis_dir / "decision_intelligence_delta.json").read_text(encoding="utf-8"))


def _manifest(result) -> dict[str, Any]:
    return json.loads(result.run.manifest_path.read_text(encoding="utf-8"))


def _stage(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    return next(stage for stage in manifest["stages"] if stage["name"] == name)


def _noop_stage(config, run) -> list[str]:
    return []
