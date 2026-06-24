from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
import sqlite3
from typing import Any

import pytest

from halpha.config import load_config
from halpha.data.run_index import run_index_path
from halpha.pipeline import run_pipeline
from halpha.pipeline_stages import OPERATION_ORDER
from halpha.storage import write_json


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_outcome_targets_record_no_previous_run_state(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="synthesize_intelligence",
        stage_handlers=_handlers_for_until("build_outcome_targets"),
        now=datetime(2026, 6, 5, 0, 0, tzinfo=UTC),
    )

    artifact = _outcome_targets(result)
    manifest = _manifest(result)

    assert result.succeeded is True
    assert artifact["artifact_type"] == "outcome_targets"
    assert artifact["status"] == "skipped"
    assert artifact["previous_run"]["status"] == "no_previous_run"
    assert artifact["targets"] == []
    assert artifact["counts"]["targets"] == 0
    assert "Run index was not found" in artifact["warnings"][0]
    assert manifest["artifacts"]["outcome_targets"] == "analysis/outcome_targets.json"
    assert manifest["counts"]["outcome_targets"] == 0
    assert manifest["counts"]["outcome_target_skipped_records"] == 0
    assert _stage(manifest, "build_outcome_targets")["artifacts"] == ["analysis/outcome_targets.json"]


def test_outcome_targets_reject_previous_run_outside_project_root(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    previous = _run_previous_source_pipeline(config, config_path)
    outside_dir = tmp_path.parent / "outside-outcome-targets-run"
    write_json(
        outside_dir / "analysis" / "market_signals.json",
        {
            "schema_version": 1,
            "artifact_type": "market_signals",
            "status": "ok",
            "signals": [{"private_note": "outside outcome target artifact was read"}],
        },
    )
    with sqlite3.connect(run_index_path(config_path)) as connection:
        connection.execute("UPDATE runs SET run_dir = ? WHERE run_id = ?", (str(outside_dir), previous.run.run_id))
        connection.commit()

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="synthesize_intelligence",
        stage_handlers=_handlers_for_until("build_outcome_targets"),
        now=datetime(2026, 6, 7, 0, 0, tzinfo=UTC),
    )

    artifact = _outcome_targets(result)
    assert result.succeeded is True
    assert artifact["status"] == "skipped"
    assert artifact["targets"] == []
    assert "points outside the configured project root" in artifact["warnings"][0]
    assert "outside outcome target artifact was read" not in json.dumps(artifact)


def test_outcome_targets_extract_supported_previous_run_artifacts(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    previous = _run_previous_source_pipeline(config, config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="synthesize_intelligence",
        stage_handlers=_handlers_for_until("build_outcome_targets"),
        now=datetime(2026, 6, 7, 0, 0, tzinfo=UTC),
    )

    artifact = _outcome_targets(result)
    manifest = _manifest(result)
    by_kind = {target["target_kind"]: target for target in artifact["targets"]}

    assert result.succeeded is True
    assert artifact["status"] == "ok"
    assert artifact["previous_run"]["run_id"] == previous.run.run_id
    assert artifact["counts"]["targets"] == 6
    assert artifact["counts"]["skipped_records"] == 0
    assert artifact["counts"]["by_kind"] == {
        "alert_decision": 1,
        "decision_recommendation": 1,
        "event_assessment": 1,
        "market_signal": 1,
        "strategy_gate": 1,
        "watch_trigger": 1,
    }
    assert artifact["counts"]["by_maturity_status"] == {"matured": 6}
    assert set(by_kind) == set(artifact["counts"]["by_kind"])
    assert all(target["source_run_id"] == previous.run.run_id for target in artifact["targets"])
    assert all(target["source_record_id"] for target in artifact["targets"])
    assert all(target["source_as_of"] for target in artifact["targets"])
    assert all(target["horizon"]["matures_at"] for target in artifact["targets"])
    assert by_kind["market_signal"]["expected_observation"]["direction"] == "bullish"
    assert by_kind["strategy_gate"]["expected_observation"]["gate_status"] == "effective"
    assert by_kind["event_assessment"]["expected_observation"]["decision_impact"] == "supports_existing_view"
    assert by_kind["alert_decision"]["expected_observation"]["priority"] == "P2"
    assert by_kind["decision_recommendation"]["expected_observation"]["action_level"] == "TRY_SMALL"
    assert by_kind["watch_trigger"]["expected_observation"]["trigger_type"] == "confirmation"
    assert manifest["counts"]["outcome_targets"] == 6
    assert manifest["counts"]["outcome_target_skipped_records"] == 0
    assert manifest["outcome_targets"]["source_run_id"] == previous.run.run_id
    assert _stage(manifest, "build_outcome_targets")["artifacts"] == ["analysis/outcome_targets.json"]


def test_outcome_targets_expand_unscoped_strategy_gates_from_benchmark_evaluations(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    previous = run_pipeline(
        config,
        config_path=config_path,
        until_stage="run_strategy_research",
        stage_handlers=_handlers_for_until(
            "build_strategy_experiment_material",
            {"build_strategy_experiment_material": _write_unscoped_strategy_gate_with_experiment},
        ),
        now=datetime(2026, 6, 5, 0, 0, tzinfo=UTC),
    )
    assert previous.succeeded is True

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="synthesize_intelligence",
        stage_handlers=_handlers_for_until("build_outcome_targets"),
        now=datetime(2026, 6, 7, 0, 0, tzinfo=UTC),
    )

    artifact = _outcome_targets(result)
    targets = artifact["targets"]

    assert result.succeeded is True
    assert artifact["status"] == "ok"
    assert artifact["previous_run"]["run_id"] == previous.run.run_id
    assert artifact["counts"]["targets"] == 2
    assert artifact["counts"]["skipped_records"] == 0
    assert artifact["counts"]["missing_source_fields"] == 0
    assert artifact["counts"]["by_kind"] == {"strategy_gate": 2}
    assert {target["symbol"] for target in targets} == {"BTCUSDT", "ETHUSDT"}
    assert {target["timeframe"] for target in targets} == {"1d"}
    assert all(target["source"] == "binance" for target in targets)
    assert all(target["source_record_id"].startswith("strategy_effectiveness_gate:tsmom_vol_scaled:") for target in targets)
    assert all("analysis/strategy_experiment.json" in target["source_artifacts"] for target in targets)
    assert all(target["expected_observation"]["gate_status"] == "effective" for target in targets)
    assert {target["expected_observation"]["evaluation_status"] for target in targets} == {"succeeded"}


def test_outcome_targets_skip_missing_fields_and_duplicate_targets(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    previous = run_pipeline(
        config,
        config_path=config_path,
        until_stage="run_strategy_research",
        stage_handlers=_handlers_for_until(
            "build_market_signals",
            {"build_market_signals": _write_duplicate_and_incomplete_market_signals},
        ),
        now=datetime(2026, 6, 5, 0, 0, tzinfo=UTC),
    )
    assert previous.succeeded is True

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="synthesize_intelligence",
        stage_handlers=_handlers_for_until("build_outcome_targets"),
        now=datetime(2026, 6, 7, 0, 0, tzinfo=UTC),
    )

    artifact = _outcome_targets(result)
    manifest = _manifest(result)

    assert artifact["status"] == "warning"
    assert artifact["counts"]["targets"] == 1
    assert artifact["counts"]["skipped_records"] == 2
    assert artifact["counts"]["duplicate_records"] == 1
    assert artifact["counts"]["missing_source_fields"] == 1
    assert {record["reason"] for record in artifact["skipped_records"]} == {
        "duplicate_target_id",
        "missing_source_fields",
    }
    assert manifest["counts"]["outcome_targets"] == 1
    assert manifest["counts"]["outcome_target_skipped_records"] == 2
    assert manifest["counts"]["outcome_target_duplicate_records"] == 1
    assert manifest["counts"]["outcome_target_missing_source_fields"] == 1
    assert manifest["outcome_targets"]["skipped_reasons"] == {
        "duplicate_target_id": 1,
        "missing_source_fields": 1,
    }


def _run_previous_source_pipeline(config: dict[str, Any], config_path: Path):
    return run_pipeline(
        config,
        config_path=config_path,
        until_stage="synthesize_intelligence",
        stage_handlers=_handlers_for_until(
            "build_alert_decisions",
            {
                "build_strategy_experiment_material": _write_strategy_effectiveness_gates,
                "build_market_signals": _write_market_signals,
                "build_decision_recommendations": _write_decision_recommendations,
                "build_watch_triggers": _write_watch_triggers,
                "build_event_intelligence_assessment": _write_event_intelligence_assessment,
                "build_alert_decisions": _write_alert_decisions,
            },
        ),
        now=datetime(2026, 6, 5, 0, 0, tzinfo=UTC),
    )


def _handlers_for_until(stage: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    handlers = {name: _noop_stage for name in OPERATION_ORDER if name != stage}
    if overrides:
        handlers.update(overrides)
    return handlers


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  output_dir: runs
market:
  enabled: true
  source: binance
  symbols:
    - BTCUSDT
  ohlcv:
    storage_dir: data/market/ohlcv
    timeframes:
      - 1d
    lookback:
      1d: 3
quant:
  enabled: true
  engine: vectorbt
  strategies:
    - name: tsmom_vol_scaled
text:
  enabled: true
  max_items: 1
  sources:
    - name: coindesk
      type: rss
      url: https://example.com/feed.xml
report:
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _write_market_signals(config, run) -> list[str]:
    del config
    write_json(
        run.analysis_dir / "market_signals.json",
        {
            "schema_version": 1,
            "artifact_type": "market_signals",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["analysis/market_strategy_signals.json"],
            "signals": [_market_signal()],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["market_signals"] = "analysis/market_signals.json"
    return ["analysis/market_signals.json"]


def _write_duplicate_and_incomplete_market_signals(config, run) -> list[str]:
    del config
    write_json(
        run.analysis_dir / "market_signals.json",
        {
            "schema_version": 1,
            "artifact_type": "market_signals",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["analysis/market_strategy_signals.json"],
            "signals": [
                _market_signal(),
                _market_signal(),
                {
                    "signal_id": "market_signal:missing_symbol",
                    "source": "binance",
                    "timeframe": "1d",
                    "latest_candle_time": "2026-06-05T00:00:00Z",
                    "direction": "bullish",
                    "strength": "medium",
                    "confidence": "medium",
                    "source_artifacts": ["analysis/market_strategy_signals.json"],
                },
            ],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["market_signals"] = "analysis/market_signals.json"
    return ["analysis/market_signals.json"]


def _write_strategy_effectiveness_gates(config, run) -> list[str]:
    del config
    write_json(
        run.analysis_dir / "strategy_effectiveness_gates.json",
        {
            "schema_version": 1,
            "artifact_type": "strategy_effectiveness_gates",
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["analysis/strategy_experiment.json"],
            "records": [
                {
                    "gate_id": "strategy_effectiveness_gate:tsmom_vol_scaled:binance:BTCUSDT:1d:2026-06-05T00:00:00Z",
                    "strategy_name": "tsmom_vol_scaled",
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "latest_candle_time": "2026-06-05T00:00:00Z",
                    "status": "effective",
                    "reasons": [{"code": "benchmark_coverage_met", "severity": "pass"}],
                    "source_artifacts": ["analysis/strategy_experiment.json"],
                    "warnings": [],
                    "errors": [],
                }
            ],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["strategy_effectiveness_gates"] = "analysis/strategy_effectiveness_gates.json"
    return ["analysis/strategy_effectiveness_gates.json"]


def _write_unscoped_strategy_gate_with_experiment(config, run) -> list[str]:
    del config
    write_json(
        run.analysis_dir / "strategy_experiment.json",
        {
            "schema_version": 1,
            "artifact_type": "strategy_experiment",
            "created_at": "2026-06-05T00:00:00Z",
            "candidates": [
                {
                    "strategy_name": "tsmom_vol_scaled",
                    "status": "succeeded",
                    "params": {},
                    "evaluations": [
                        _strategy_experiment_evaluation("BTCUSDT"),
                        _strategy_experiment_evaluation("ETHUSDT"),
                    ],
                    "warnings": [],
                    "errors": [],
                }
            ],
            "source_artifacts": ["analysis/strategy_benchmark_suite.json"],
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        run.analysis_dir / "strategy_effectiveness_gates.json",
        {
            "schema_version": 1,
            "artifact_type": "strategy_effectiveness_gates",
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["analysis/strategy_experiment.json"],
            "records": [
                {
                    "gate_id": "strategy_effectiveness_gate:tsmom_vol_scaled",
                    "strategy_name": "tsmom_vol_scaled",
                    "status": "effective",
                    "gate_inputs": {},
                    "reasons": [{"code": "benchmark_coverage_met", "severity": "pass"}],
                    "source_artifacts": ["analysis/strategy_experiment.json"],
                    "warnings": [],
                    "errors": [],
                }
            ],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["strategy_experiment"] = "analysis/strategy_experiment.json"
    run.manifest["artifacts"]["strategy_effectiveness_gates"] = "analysis/strategy_effectiveness_gates.json"
    return ["analysis/strategy_experiment.json", "analysis/strategy_effectiveness_gates.json"]


def _strategy_experiment_evaluation(symbol: str) -> dict[str, Any]:
    return {
        "evaluation_id": f"strategy_experiment:tsmom_vol_scaled:binance:{symbol}:1d:2026-06-05T00:00:00Z",
        "benchmark_id": f"strategy_benchmark:binance:{symbol}:1d:configured_lookback",
        "benchmark_status": "succeeded",
        "status": "succeeded",
        "source": "binance",
        "symbol": symbol,
        "timeframe": "1d",
        "input_window_start": "2026-01-01T00:00:00Z",
        "input_window_end": "2026-06-05T00:00:00Z",
        "metrics": {},
        "warnings": [],
        "errors": [],
    }


def _write_decision_recommendations(config, run) -> list[str]:
    del config
    write_json(
        run.analysis_dir / "decision_recommendations.json",
        {
            "schema_version": 1,
            "artifact_type": "decision_recommendations",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["analysis/risk_assessment.json", "analysis/market_signals.json"],
            "records": [
                {
                    "record_id": "decision_recommendation:binance:BTCUSDT:1d:2026-06-05T00:00:00Z",
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "latest_candle_time": "2026-06-05T00:00:00Z",
                    "action_level": "TRY_SMALL",
                    "decision_bias": "tentative_constructive",
                    "status": "actionable",
                    "evidence": ["Decision evidence."],
                    "source_artifacts": ["analysis/risk_assessment.json", "analysis/market_signals.json"],
                }
            ],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["decision_recommendations"] = "analysis/decision_recommendations.json"
    return ["analysis/decision_recommendations.json"]


def _write_watch_triggers(config, run) -> list[str]:
    del config
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
                    "trigger_id": "watch_trigger:binance:BTCUSDT:1d:confirmation:2026-06-05T00:00:00Z",
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "type": "confirmation",
                    "condition": "BTCUSDT confirmation condition remains required.",
                    "linked_decision_record_id": "decision_recommendation:binance:BTCUSDT:1d:2026-06-05T00:00:00Z",
                    "source_artifacts": ["analysis/decision_recommendations.json"],
                }
            ],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["watch_triggers"] = "analysis/watch_triggers.json"
    return ["analysis/watch_triggers.json"]


def _write_event_intelligence_assessment(config, run) -> list[str]:
    del config
    write_json(
        run.analysis_dir / "event_intelligence_assessment.json",
        {
            "schema_version": 1,
            "artifact_type": "event_intelligence_assessment",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["analysis/text_event_signals.json"],
            "records": [
                {
                    "assessment_id": "event_intelligence_assessment:BTCUSDT:1d:text_event_signal:abc123",
                    "status": "succeeded",
                    "scope": {"symbol": "BTCUSDT", "timeframe": "1d"},
                    "event_severity": "medium",
                    "decision_impact": "supports_existing_view",
                    "risk_effect": "neutral",
                    "watch_relevance": "confirmation",
                    "confidence": "medium",
                    "evidence": [{"type": "event_signal", "event_signal_id": "text_event_signal:abc123"}],
                    "source_artifacts": ["analysis/text_event_signals.json"],
                    "warnings": [],
                    "errors": [],
                }
            ],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["event_intelligence_assessment"] = "analysis/event_intelligence_assessment.json"
    return ["analysis/event_intelligence_assessment.json"]


def _write_alert_decisions(config, run) -> list[str]:
    del config
    write_json(
        run.analysis_dir / "alert_decisions.json",
        {
            "schema_version": 1,
            "artifact_type": "alert_decisions",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["analysis/event_intelligence_assessment.json"],
            "records": [
                {
                    "alert_decision_id": "alert_decision:BTCUSDT:1d:event_intelligence_assessment:BTCUSDT:1d:text_event_signal:abc123",
                    "status": "attention",
                    "priority": "P2",
                    "scope": {
                        "symbol": "BTCUSDT",
                        "timeframe": "1d",
                        "assessment_id": "event_intelligence_assessment:BTCUSDT:1d:text_event_signal:abc123",
                    },
                    "attention_decision": "record_without_interrupting",
                    "requires_reassessment": False,
                    "requires_user_attention": False,
                    "source_artifacts": ["analysis/event_intelligence_assessment.json"],
                    "warnings": [],
                    "errors": [],
                }
            ],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["alert_decisions"] = "analysis/alert_decisions.json"
    return ["analysis/alert_decisions.json"]


def _market_signal() -> dict[str, Any]:
    return {
        "signal_id": "market_signal:tsmom_vol_scaled:binance:BTCUSDT:1d:2026-06-05T00:00:00Z",
        "strategy_name": "tsmom_vol_scaled",
        "source": "binance",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "latest_candle_time": "2026-06-05T00:00:00Z",
        "direction": "bullish",
        "strength": "medium",
        "confidence": "medium",
        "evidence": ["Market signal evidence."],
        "uncertainty": ["Market signal uncertainty."],
        "insufficient_data": False,
        "source_artifacts": ["analysis/market_strategy_signals.json"],
        "created_at": "2026-06-05T00:00:00Z",
    }


def _outcome_targets(result) -> dict[str, Any]:
    return json.loads((result.run.analysis_dir / "outcome_targets.json").read_text(encoding="utf-8"))


def _manifest(result) -> dict[str, Any]:
    return json.loads(result.run.manifest_path.read_text(encoding="utf-8"))


def _stage(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    return next(
        task
        for stage in manifest["stages"]
        for task in stage.get("tasks", [])
        if task["name"] == name
    )


def _noop_stage(config, run) -> list[str]:
    return []
