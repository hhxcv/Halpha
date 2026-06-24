from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from halpha.config import load_config
from halpha.pipeline import run_pipeline, run_pipeline_stage
from halpha.storage import write_json


GOLDEN_PATH = Path(__file__).parent / "fixtures" / "alert_decision_golden_cases.json"


def test_alert_decision_golden_cases_cover_priority_downgrade_and_material_boundaries(
    tmp_path: Path,
) -> None:
    fixture = _load_fixture()
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_alert_decision_material",
        stage_handlers=_base_handlers(
            {
                "build_event_intelligence_assessment": lambda config, run: _write_assessment(
                    run, fixture["cases"]
                ),
                "build_risk_assessment": _write_risk_assessment,
                "build_decision_recommendations": _write_decision_recommendations,
                "build_watch_triggers": _write_watch_triggers,
            }
        ),
    )

    assert result.succeeded is True
    manifest = _manifest(result)
    decisions = _read_json(result.run.analysis_dir / "alert_decisions.json")
    material = (result.run.analysis_dir / "alert_decision_material.md").read_text(encoding="utf-8")
    records_by_assessment = {
        record["scope"]["assessment_id"]: record for record in decisions["records"]
    }

    assert decisions["artifact_type"] == "alert_decisions"
    assert decisions["priority_taxonomy"] == ["P0", "P1", "P2", "P3", "no_alert", "unknown"]
    assert len(records_by_assessment) == len(fixture["cases"])

    for case in fixture["cases"]:
        assessment = case["assessment"]
        expected = case["expected"]
        record = records_by_assessment[assessment["assessment_id"]]
        assert record["priority"] == expected["priority"], case["case_id"]
        assert record["status"] == expected["status"], case["case_id"]
        assert record["attention_decision"] == expected["attention_decision"], case["case_id"]
        assert record["requires_user_attention"] is expected["requires_user_attention"], case["case_id"]
        assert record["requires_reassessment"] is expected["requires_reassessment"], case["case_id"]
        assert record["evidence_strength"] == expected["evidence_strength"], case["case_id"]
        assert set(expected["suppression_reasons"]) <= set(record["suppression_reasons"]), case["case_id"]
        assert set(assessment["downgrade_reasons"]) <= set(record["downgrade_reasons"]), case["case_id"]
        assert record["linked_event_assessment_ids"] == [assessment["assessment_id"]]
        assert "analysis/event_intelligence_assessment.json" in record["source_artifacts"]

    assert manifest["counts"]["alert_decision_records"] == 6
    assert manifest["counts"]["alert_decision_p0_records"] == 1
    assert manifest["counts"]["alert_decision_p1_records"] == 1
    assert manifest["counts"]["alert_decision_p2_records"] == 1
    assert manifest["counts"]["alert_decision_p3_records"] == 1
    assert manifest["counts"]["alert_decision_no_alert_records"] == 2
    assert manifest["counts"]["alert_decision_downgraded_records"] == 3
    assert manifest["counts"]["alert_decision_suppressed_records"] == 3
    assert manifest["counts"]["alert_decision_material_records"] == 6
    assert manifest["alert_decisions"]["priority"] == {
        "P0": 1,
        "P1": 1,
        "P2": 1,
        "P3": 1,
        "no_alert": 2,
    }
    assert manifest["alert_decision_material"]["priority"] == {
        "P0": 1,
        "P1": 1,
        "P2": 1,
        "P3": 1,
        "no_alert": 2,
    }
    assert _stage(manifest, "build_alert_decision_material")["artifacts"] == [
        "analysis/alert_decision_material.md"
    ]
    assert _stage(manifest, "build_event_intelligence_material")["status"] == "not_run"

    assert "artifact_type: analysis_alert_decision_material" in material
    assert "analysis/event_intelligence_assessment.json" in material
    assert "analysis/alert_decisions.json" in material
    assert "priority: P0" in material
    assert "priority: P1" in material
    assert "priority: P2" in material
    assert "priority: P3" in material
    assert "priority: no_alert" in material
    assert "codex_may_generate_alert_priority: false" in material
    assert "codex_may_generate_event_severity: false" in material
    assert "codex_may_generate_decision_impact: false" in material
    assert "codex_may_send_or_schedule_alerts: false" in material
    assert "full_alert_decision_json_embedded: false" in material
    assert "full_event_assessment_json_embedded: false" in material
    assert "Raw text body that should never appear in alert decision material." not in material

    rerun = run_pipeline_stage(
        config,
        config_path=config_path,
        run_dir=result.run.run_dir,
        stage="build_alert_decision_material",
    )
    rerun_manifest = _manifest(rerun)
    assert rerun.succeeded is True
    rerun_stage = _stage(rerun_manifest, "build_alert_decision_material")
    assert rerun_stage["mode"] == "recomputed"
    assert rerun_stage["artifacts"] == ["analysis/alert_decision_material.md"]
    assert rerun_manifest["counts"]["alert_decision_material_records"] == 6


def test_alert_decision_path_skips_without_upstream_event_assessment(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_alert_decision_material",
        stage_handlers=_base_handlers({"build_event_intelligence_assessment": _noop_stage}),
    )

    assert result.succeeded is True
    manifest = _manifest(result)
    assert not (result.run.analysis_dir / "alert_decisions.json").exists()
    assert not (result.run.analysis_dir / "alert_decision_material.md").exists()
    assert "alert_decisions" not in manifest["artifacts"]
    assert "alert_decision_material" not in manifest["artifacts"]
    assert manifest["alert_decisions"]["status"] == "skipped"
    assert manifest["alert_decision_material"]["status"] == "skipped"
    assert manifest["counts"]["alert_decision_records"] == 0
    assert manifest["counts"]["alert_decision_material_records"] == 0
    assert _stage(manifest, "build_alert_decisions")["artifacts"] == []
    assert _stage(manifest, "build_alert_decision_material")["artifacts"] == []
    assert _stage(manifest, "build_event_intelligence_material")["status"] == "not_run"


def _load_fixture() -> dict[str, Any]:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


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


def _base_handlers(overrides: dict[str, Any]) -> dict[str, Any]:
    handlers: dict[str, Any] = {
        "collect_market_data": _noop_stage,
        "collect_text_events": _noop_stage,
        "build_text_event_records": _noop_stage,
        "build_text_entity_evidence": _noop_stage,
        "build_text_event_classification_evidence": _noop_stage,
        "build_text_event_topics": _noop_stage,
        "build_text_event_signals": _noop_stage,
        "sync_ohlcv": _noop_stage,
        "build_market_data_views": _noop_stage,
        "build_strategy_benchmark_suite": _noop_stage,
        "evaluate_quant_strategies": _noop_stage,
        "evaluate_strategy_evaluation": _noop_stage,
        "build_strategy_experiment_material": _noop_stage,
        "evaluate_market_strategy_signals": _noop_stage,
        "build_market_signals": _noop_stage,
        "build_market_signal_material": _noop_stage,
        "build_market_regime_assessment": _noop_stage,
        "build_risk_assessment": _noop_stage,
        "build_decision_recommendations": _noop_stage,
        "build_watch_triggers": _noop_stage,
        "build_event_market_confluence": _noop_stage,
    }
    handlers.update(overrides)
    return handlers


def _write_assessment(run, cases: list[dict[str, Any]]) -> list[str]:
    records = [case["assessment"] for case in cases]
    warnings: list[str] = []
    for record in records:
        warnings.extend(record.get("warnings", []))
    write_json(
        run.analysis_dir / "event_intelligence_assessment.json",
        {
            "schema_version": 1,
            "artifact_type": "event_intelligence_assessment",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": [
                "analysis/text_event_topics.json",
                "analysis/text_event_signals.json",
                "analysis/event_market_confluence.json",
                "analysis/decision_recommendations.json",
                "analysis/watch_triggers.json",
            ],
            "coverage": {
                "records": len(records),
                "downgraded_records": sum(1 for record in records if record["downgrade_reasons"]),
            },
            "records": records,
            "warnings": sorted(set(warnings)),
            "errors": [],
        },
    )
    run.manifest["artifacts"]["event_intelligence_assessment"] = "analysis/event_intelligence_assessment.json"
    run.manifest["counts"]["event_intelligence_assessment_records"] = len(records)
    run.manifest["counts"]["event_intelligence_assessment_downgraded_records"] = sum(
        1 for record in records if record["downgrade_reasons"]
    )
    run.manifest["event_intelligence_assessment"] = {
        "status": "succeeded",
        "artifacts": ["analysis/event_intelligence_assessment.json"],
        "records": len(records),
        "warnings": len(set(warnings)),
        "errors": 0,
    }
    return ["analysis/event_intelligence_assessment.json"]


def _write_risk_assessment(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "risk_assessment.json",
        {
            "schema_version": 1,
            "artifact_type": "risk_assessment",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["analysis/market_signals.json"],
            "records": [
                {
                    "record_id": "risk_assessment:binance:BTCUSDT:1d:2026-06-05T00:00:00Z",
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "risk_level": "high",
                    "status": "succeeded",
                    "source_artifacts": ["analysis/market_signals.json"],
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
            "source_artifacts": ["analysis/risk_assessment.json"],
            "records": [
                {
                    "record_id": "decision_recommendation:binance:BTCUSDT:1d:2026-06-05T00:00:00Z",
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "action_level": "TRY_SMALL",
                    "decision_bias": "tentative_constructive",
                    "status": "actionable",
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
    records = []
    for trigger_type in ["confirmation", "invalidation", "risk_escalation", "wait_condition"]:
        records.append(
            {
                "trigger_id": f"watch_trigger:binance:BTCUSDT:1d:{trigger_type}:2026-06-05T00:00:00Z",
                "symbol": "BTCUSDT",
                "timeframe": "1d",
                "type": trigger_type,
                "condition": f"Golden {trigger_type} condition.",
                "linked_decision_record_id": (
                    "decision_recommendation:binance:BTCUSDT:1d:2026-06-05T00:00:00Z"
                ),
                "source_artifacts": ["analysis/decision_recommendations.json"],
            }
        )
    write_json(
        run.analysis_dir / "watch_triggers.json",
        {
            "schema_version": 1,
            "artifact_type": "watch_triggers",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["analysis/decision_recommendations.json"],
            "records": records,
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["watch_triggers"] = "analysis/watch_triggers.json"
    return ["analysis/watch_triggers.json"]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest(result) -> dict[str, Any]:
    return _read_json(result.run.manifest_path)


def _stage(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    return next(stage for stage in manifest["stages"] if stage["name"] == name)


def _noop_stage(config, run) -> list[str]:
    return []
