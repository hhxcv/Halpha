from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from halpha.config import load_config
from halpha.decision.intelligence_fusion import build_intelligence_fusion
from halpha.pipeline import RunContext, run_pipeline
from halpha.pipeline_stages import OPERATION_ORDER
from halpha.storage import write_json


def test_intelligence_fusion_pipeline_writes_records_and_manifest(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    handlers = {name: _noop_stage for name in OPERATION_ORDER if name != "build_intelligence_fusion"}
    handlers.update(
        {
            "build_market_signals": _write_supportive_inputs,
            "build_market_regime_assessment": _write_regime,
            "build_risk_assessment": _write_low_risk,
            "build_factor_states": _write_supportive_factor,
            "build_multi_source_signals": _write_supportive_multi_source,
        }
    )

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="synthesize_intelligence",
        stage_handlers=handlers,
    )

    assert result.succeeded is True
    artifact = _fusion(result.run)
    manifest = _manifest(result.run)
    record = _record(artifact, symbol="BTCUSDT", timeframe="1d")

    assert artifact["artifact_type"] == "intelligence_fusion"
    assert artifact["status"] == "ok"
    assert record["state"] == "supportive"
    assert record["confluence"]["state"] == "aligned"
    assert record["confluence"]["independent_sources"] >= 2
    assert "analysis/market_signals.json" in record["source_artifacts"]
    assert manifest["artifacts"]["intelligence_fusion"] == "analysis/intelligence_fusion.json"
    assert manifest["counts"]["intelligence_fusion_records"] == len(artifact["records"])
    assert manifest["intelligence_fusion"]["state_counts"]["supportive"] == 1
    assert _task(manifest, "build_intelligence_fusion")["artifacts"] == [
        "analysis/intelligence_fusion.json"
    ]
    assert _task(manifest, "build_analysis_materials")["status"] == "not_run"


def test_intelligence_fusion_detects_conflicting_evidence(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_market_signals(run)
    _write_factor_states(run, state="cautionary", direction="cautionary")
    _write_multi_source_signals(run, state="conflicting", direction="conflicting")

    build_intelligence_fusion({}, run, now="2026-06-05T00:00:00Z")

    record = _record(_fusion(run), symbol="BTCUSDT", timeframe="1d")
    assert record["state"] == "conflicting"
    assert record["direction"] == "mixed"
    assert record["conflict"]["state"] == "severe"
    assert record["conflict"]["conflicting_sources"] >= 1


def test_intelligence_fusion_blocks_on_extreme_risk(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_market_signals(run)
    _write_risk_assessment(
        run,
        risk_level="extreme",
        cap_action_level="NO_ACTION",
        blocking_risks=["liquidity stress"],
    )

    build_intelligence_fusion({}, run, now="2026-06-05T00:00:00Z")

    record = _record(_fusion(run), symbol="BTCUSDT", timeframe="1d")
    assert record["state"] == "risk_blocked"
    assert record["risk_override"]["state"] == "block"
    assert record["risk_override"]["risk_level"] == "extreme"
    assert "liquidity stress" in record["risk_override"]["reasons"]


def test_intelligence_fusion_blocks_on_event_override(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_market_signals(run)
    _write_event_assessment(
        run,
        decision_impact="could_invalidate",
        event_severity="critical",
        risk_effect="risk_up",
        downgrade_reasons=["source event invalidates current view"],
    )

    build_intelligence_fusion({}, run, now="2026-06-05T00:00:00Z")

    record = _record(_fusion(run), symbol="BTCUSDT", timeframe="1d")
    assert record["state"] == "event_overridden"
    assert record["event_override"]["state"] == "block"
    assert record["event_override"]["severity"] == "critical"
    assert "source event invalidates current view" in record["event_override"]["reasons"]


def test_intelligence_fusion_emits_insufficient_record_when_inputs_are_missing(tmp_path: Path) -> None:
    run = _run_context(tmp_path)

    build_intelligence_fusion({}, run, now="2026-06-05T00:00:00Z")

    artifact = _fusion(run)
    record = artifact["records"][0]
    assert record["state"] == "insufficient_evidence"
    assert record["scope"] == {
        "symbol": None,
        "timeframe": None,
        "asset": None,
        "chain": None,
        "region": None,
    }
    assert any(item["status"] == "missing" for item in artifact["coverage"])
    assert any(
        item["source_layer"] == "strategy_lifecycle"
        and item["source_artifact"] == "analysis/strategy_lifecycle_state.json"
        and item["status"] == "missing"
        for item in artifact["coverage"]
    )
    assert "No source records were available for intelligence fusion." in record["warnings"]


def test_intelligence_fusion_uses_degraded_lifecycle_as_cautionary_context(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_market_signals(run)
    _write_strategy_lifecycle(run, lifecycle_status="degraded", degradation_state="degraded")

    build_intelligence_fusion({}, run, now="2026-06-05T00:00:00Z")

    record = _record(_fusion(run), symbol="BTCUSDT", timeframe="1d")
    assert record["state"] == "conflicting"
    assert record["conflict"]["state"] == "material"
    assert "analysis/strategy_lifecycle_state.json" in record["source_artifacts"]
    assert any(
        ref["source_layer"] == "strategy_lifecycle"
        and ref["source_record_id"] == "strategy_lifecycle:tsmom_vol_scaled:BTCUSDT:1d"
        for ref in record["source_record_refs"]
    )
    assert any("strategy_lifecycle state=degraded" in item for item in record["evidence"])
    assert any("degradation_state=degraded" in item for item in record["evidence"])


def test_intelligence_fusion_preserves_explicit_lifecycle_retirement_refs(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_market_signals(run)
    _write_strategy_lifecycle(
        run,
        lifecycle_status="retired",
        retirement_state="explicitly_retired",
    )

    build_intelligence_fusion({}, run, now="2026-06-05T00:00:00Z")

    record = _record(_fusion(run), symbol="BTCUSDT", timeframe="1d")
    assert record["state"] == "conflicting"
    assert "analysis/strategy_lifecycle_state.json" in record["source_artifacts"]
    assert any("strategy_lifecycle state=retired" in item for item in record["evidence"])
    assert any("retirement_state=explicitly_retired" in item for item in record["evidence"])
    assert any(
        ref["source_layer"] == "strategy_lifecycle"
        and ref["source_artifact"] == "analysis/strategy_lifecycle_state.json"
        for ref in record["source_record_refs"]
    )


def test_intelligence_fusion_keeps_insufficient_lifecycle_visible_without_downgrade(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_market_signals(run)
    _write_strategy_lifecycle(run, lifecycle_status="insufficient_evidence")

    build_intelligence_fusion({}, run, now="2026-06-05T00:00:00Z")

    record = _record(_fusion(run), symbol="BTCUSDT", timeframe="1d")
    assert record["state"] == "supportive"
    assert "analysis/strategy_lifecycle_state.json" in record["source_artifacts"]
    assert any("strategy_lifecycle insufficient: insufficient_evidence" in item for item in record["uncertainty"])
    assert any(ref["source_layer"] == "strategy_lifecycle" for ref in record["source_record_refs"])


def test_intelligence_fusion_preserves_degraded_input_state(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_factor_states(
        run,
        state="degraded",
        direction="cautionary",
        warning="factor evidence is stale.",
    )
    _write_multi_source_signals(
        run,
        state="degraded",
        direction="neutral",
        warning="multi-source signal degraded.",
    )

    build_intelligence_fusion({}, run, now="2026-06-05T00:00:00Z")

    record = _record(_fusion(run), symbol="BTCUSDT", timeframe="1d")
    assert record["state"] == "degraded"
    assert record["confidence"] == "low"
    assert "factor evidence is stale." in record["warnings"]
    assert "multi-source signal degraded." in record["warnings"]


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


def _write_supportive_inputs(config: dict[str, Any], run: RunContext) -> list[str]:
    _write_market_signals(run)
    _write_empty_upstream_artifacts(run)
    return ["analysis/market_signals.json"]


def _write_regime(config: dict[str, Any], run: RunContext) -> list[str]:
    _write_market_regime(run)
    return ["analysis/market_regime_assessment.json"]


def _write_low_risk(config: dict[str, Any], run: RunContext) -> list[str]:
    _write_risk_assessment(run)
    return ["analysis/risk_assessment.json"]


def _write_supportive_factor(config: dict[str, Any], run: RunContext) -> list[str]:
    _write_factor_states(run)
    return ["analysis/factor_states.json"]


def _write_supportive_multi_source(config: dict[str, Any], run: RunContext) -> list[str]:
    _write_multi_source_signals(run)
    return ["analysis/multi_source_signals.json"]


def _noop_stage(config: dict[str, Any], run: RunContext) -> list[str]:
    return []


def _write_empty_upstream_artifacts(run: RunContext) -> None:
    _write_records_artifact(run, "strategy_evaluation_summary.json", "strategy_evaluation_summary", "records", [])
    _write_records_artifact(run, "strategy_effectiveness_gates.json", "strategy_effectiveness_gates", "records", [])
    _write_records_artifact(run, "event_intelligence_assessment.json", "event_intelligence_assessment", "records", [])
    _write_records_artifact(run, "alert_decisions.json", "alert_decisions", "records", [])
    _write_records_artifact(run, "outcome_evaluations.json", "outcome_evaluations", "evaluations", [])
    _write_records_artifact(run, "data_quality_summary.json", "data_quality_summary", "checks", [])


def _write_market_signals(run: RunContext) -> None:
    _write_records_artifact(
        run,
        "market_signals.json",
        "market_signals",
        "signals",
        [
            {
                "signal_id": "market_signal:btcusdt:1d",
                "symbol": "BTCUSDT",
                "timeframe": "1d",
                "direction": "bullish",
                "confidence": "medium",
                "insufficient_data": False,
                "evidence": ["trend up"],
                "uncertainty": [],
                "source_artifacts": ["analysis/market_signals.json"],
            }
        ],
    )


def _write_market_regime(run: RunContext) -> None:
    _write_records_artifact(
        run,
        "market_regime_assessment.json",
        "market_regime_assessment",
        "records",
        [
            {
                "record_id": "regime:btcusdt:1d",
                "symbol": "BTCUSDT",
                "timeframe": "1d",
                "status": "ok",
                "regime": "trend_up",
                "confidence": "medium",
                "conflicts": [],
                "warnings": [],
                "errors": [],
                "source_artifacts": ["analysis/market_regime_assessment.json"],
            }
        ],
    )


def _write_risk_assessment(
    run: RunContext,
    *,
    risk_level: str = "low",
    cap_action_level: str = "TRY_SMALL",
    blocking_risks: list[str] | None = None,
) -> None:
    _write_records_artifact(
        run,
        "risk_assessment.json",
        "risk_assessment",
        "records",
        [
            {
                "record_id": "risk:btcusdt:1d",
                "symbol": "BTCUSDT",
                "timeframe": "1d",
                "status": "ok",
                "risk_level": risk_level,
                "confidence": "medium",
                "blocking_risks": blocking_risks or [],
                "rising_risks": [],
                "signal_conflict_risks": [],
                "cap_action_level": cap_action_level,
                "warnings": [],
                "errors": [],
                "source_artifacts": ["analysis/risk_assessment.json"],
            }
        ],
    )


def _write_factor_states(
    run: RunContext,
    *,
    state: str = "supportive",
    direction: str = "supportive",
    warning: str | None = None,
) -> None:
    _write_records_artifact(
        run,
        "factor_states.json",
        "factor_states",
        "records",
        [
            {
                "factor_id": "factor:trend:btcusdt:1d",
                "scope": _scope(),
                "state": state,
                "direction": direction,
                "confidence": "medium",
                "evidence": ["factor evidence"],
                "uncertainty": [],
                "warnings": [warning] if warning else [],
                "errors": [],
                "source_artifacts": ["analysis/factor_states.json"],
            }
        ],
    )


def _write_multi_source_signals(
    run: RunContext,
    *,
    state: str = "supportive",
    direction: str = "supportive",
    warning: str | None = None,
) -> None:
    _write_records_artifact(
        run,
        "multi_source_signals.json",
        "multi_source_signals",
        "records",
        [
            {
                "signal_id": "multi_source:btcusdt:1d",
                "scope": _scope(),
                "state": state,
                "direction": direction,
                "confidence": "medium",
                "uncertainty": [],
                "warnings": [warning] if warning else [],
                "errors": [],
                "source_artifacts": ["analysis/multi_source_signals.json"],
            }
        ],
    )


def _write_event_assessment(
    run: RunContext,
    *,
    decision_impact: str,
    event_severity: str,
    risk_effect: str,
    downgrade_reasons: list[str],
) -> None:
    _write_records_artifact(
        run,
        "event_intelligence_assessment.json",
        "event_intelligence_assessment",
        "records",
        [
            {
                "assessment_id": "event:btcusdt:1d",
                "scope": _scope(),
                "status": "accepted",
                "event_severity": event_severity,
                "decision_impact": decision_impact,
                "risk_effect": risk_effect,
                "confidence": "medium",
                "downgrade_reasons": downgrade_reasons,
                "uncertainty": [],
                "warnings": [],
                "errors": [],
                "source_artifacts": ["analysis/event_intelligence_assessment.json"],
            }
        ],
    )


def _write_strategy_lifecycle(
    run: RunContext,
    *,
    lifecycle_status: str,
    degradation_state: str = "none",
    retirement_state: str = "not_retired",
) -> None:
    _write_records_artifact(
        run,
        "strategy_lifecycle_state.json",
        "strategy_lifecycle_state",
        "records",
        [
            {
                "lifecycle_record_id": "strategy_lifecycle:tsmom_vol_scaled:BTCUSDT:1d",
                "strategy_name": "tsmom_vol_scaled",
                "scope": _scope(),
                "strategy_contract_version": "1",
                "parameter_version": "sha256:abc",
                "parameter_digest": "sha256:abc",
                "lifecycle_status": lifecycle_status,
                "health_state": {
                    "state": lifecycle_status,
                    "confidence": "medium",
                    "reasons": [f"strategy_lifecycle_status={lifecycle_status}."],
                },
                "degradation": {
                    "state": degradation_state,
                    "reasons": ["Prior outcome feedback weakened lifecycle confidence."]
                    if degradation_state == "degraded"
                    else [],
                    "source_record_refs": ["outcome:strategy-gate"],
                },
                "regime_weakness": {"state": "unknown", "regimes": [], "reasons": []},
                "promotion": {"state": "not_requested", "policy_refs": []},
                "retirement": {
                    "state": retirement_state,
                    "policy_refs": ["lifecycle_policy:retire:abc"]
                    if retirement_state == "explicitly_retired"
                    else [],
                },
                "evidence": [f"strategy_lifecycle_status={lifecycle_status}."],
                "uncertainty": ["Lifecycle evidence is deterministic research material."],
                "warnings": [],
                "errors": [],
                "source_artifacts": ["analysis/strategy_effectiveness_gates.json"],
                "source_record_refs": ["gate:tsmom_vol_scaled:BTCUSDT:1d"],
            }
        ],
    )


def _write_records_artifact(
    run: RunContext,
    filename: str,
    artifact_type: str,
    records_key: str,
    records: list[dict[str, Any]],
) -> None:
    write_json(
        run.analysis_dir / filename,
        {
            "schema_version": 1,
            "artifact_type": artifact_type,
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "status": "ok",
            records_key: records,
            "counts": {"records": len(records), "warnings": 0, "errors": 0},
            "warnings": [],
            "errors": [],
            "source_artifacts": [f"analysis/{filename}"],
        },
    )


def _scope() -> dict[str, str | None]:
    return {
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "asset": None,
        "chain": None,
        "region": None,
    }


def _fusion(run: RunContext) -> dict[str, Any]:
    return json.loads((run.analysis_dir / "intelligence_fusion.json").read_text(encoding="utf-8"))


def _manifest(run: RunContext) -> dict[str, Any]:
    return json.loads(run.manifest_path.read_text(encoding="utf-8"))


def _record(
    artifact: dict[str, Any],
    *,
    symbol: str | None = None,
    timeframe: str | None = None,
) -> dict[str, Any]:
    for record in artifact["records"]:
        scope = record["scope"]
        if scope.get("symbol") == symbol and scope.get("timeframe") == timeframe:
            return record
    raise AssertionError("fusion record not found")


def _task(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    for stage in manifest["stages"]:
        for task in stage.get("tasks", []):
            if task["name"] == name:
                return task
    raise AssertionError(f"task {name} not found")
