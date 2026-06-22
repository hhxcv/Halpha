from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from halpha.pipeline import RunContext
from halpha.storage import write_json
from halpha.strategy.strategy_lifecycle import build_strategy_lifecycle_state


def test_strategy_lifecycle_state_records_degradation_and_versions(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    write_json(
        run.analysis_dir / "quant_strategy_runs.json",
        {
            "artifact_type": "quant_strategy_runs",
            "status": "ok",
            "source_artifacts": ["raw/market_data_views.json"],
            "runs": [
                _quant_run("tsmom_vol_scaled", "BTCUSDT", "1d", version=2, params={"return_window": 20}),
                _quant_run("tsmom_vol_scaled", "ETHUSDT", "1d", version=3, params={"return_window": 40}),
            ],
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        run.analysis_dir / "strategy_evaluation_summary.json",
        {
            "artifact_type": "strategy_evaluation_summary",
            "status": "ok",
            "source_artifacts": ["analysis/quant_strategy_runs.json"],
            "records": [
                _evaluation("tsmom_vol_scaled", "BTCUSDT", "1d", version=2, params={"return_window": 20}),
                _evaluation("tsmom_vol_scaled", "ETHUSDT", "1d", version=3, params={"return_window": 40}),
            ],
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        run.analysis_dir / "strategy_experiment.json",
        {
            "artifact_type": "strategy_experiment",
            "status": "ok",
            "source_artifacts": ["analysis/strategy_benchmark_suite.json"],
            "candidates": [],
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        run.analysis_dir / "strategy_effectiveness_gates.json",
        {
            "artifact_type": "strategy_effectiveness_gates",
            "status": "ok",
            "source_artifacts": ["analysis/strategy_experiment.json"],
            "records": [
                _gate("tsmom_vol_scaled", "BTCUSDT", "1d", "effective", params={"return_window": 20}),
                _gate("tsmom_vol_scaled", "ETHUSDT", "1d", "effective", params={"return_window": 40}),
            ],
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        run.analysis_dir / "outcome_targets.json",
        {
            "artifact_type": "outcome_targets",
            "status": "ok",
            "targets": [
                _strategy_gate_target("target:btc", "tsmom_vol_scaled", "BTCUSDT", "1d"),
            ],
            "warnings": [],
            "errors": [],
            "source_artifacts": ["data/research/index.sqlite"],
        },
    )
    write_json(
        run.analysis_dir / "outcome_evaluations.json",
        {
            "artifact_type": "outcome_evaluations",
            "status": "ok",
            "evaluations": [
                {
                    "outcome_id": "outcome:btc",
                    "target_id": "target:btc",
                    "target_kind": "strategy_gate",
                    "evaluation_status": "evaluated",
                    "outcome_state": "not_aligned",
                    "warnings": [],
                    "errors": [],
                    "source_artifacts": ["analysis/outcome_targets.json"],
                }
            ],
            "warnings": [],
            "errors": [],
            "source_artifacts": ["analysis/outcome_targets.json"],
        },
    )

    artifacts = build_strategy_lifecycle_state(
        {"quant": {"enabled": True, "strategies": [{"name": "tsmom_vol_scaled"}]}},
        run,
        now=datetime(2026, 6, 6, tzinfo=UTC),
    )

    artifact = _read_lifecycle(run)
    by_symbol = {record["scope"]["symbol"]: record for record in artifact["records"]}

    assert artifacts == ["analysis/strategy_lifecycle_state.json"]
    assert artifact["artifact_type"] == "strategy_lifecycle_state"
    assert artifact["status"] == "warning"
    assert artifact["counts"]["records"] == 2
    assert by_symbol["BTCUSDT"]["lifecycle_status"] == "degraded"
    assert by_symbol["BTCUSDT"]["strategy_contract_version"] == "2"
    assert by_symbol["BTCUSDT"]["degradation"]["state"] == "degraded"
    assert by_symbol["BTCUSDT"]["health_state"]["state"] == "degraded"
    assert by_symbol["ETHUSDT"]["lifecycle_status"] == "effective"
    assert by_symbol["ETHUSDT"]["strategy_contract_version"] == "3"
    assert by_symbol["BTCUSDT"]["parameter_digest"] != by_symbol["ETHUSDT"]["parameter_digest"]
    assert "analysis/strategy_lifecycle_state.json" not in by_symbol["BTCUSDT"]["source_artifacts"]
    assert run.manifest["artifacts"]["strategy_lifecycle_state"] == "analysis/strategy_lifecycle_state.json"
    assert run.manifest["counts"]["strategy_lifecycle_degraded"] == 1
    assert run.manifest["counts"]["strategy_lifecycle_effective"] == 1


def test_strategy_lifecycle_policy_explicit_retirement_without_reason_leak(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_minimal_upstream(run, gate_status="effective")
    config = {
        "quant": {
            "enabled": True,
            "strategies": [{"name": "tsmom_vol_scaled"}],
            "lifecycle_policy": {
                "records": [
                    {
                        "action": "retire",
                        "strategy_name": "tsmom_vol_scaled",
                        "reason": "private local review note",
                        "created_at": "2026-06-06T00:00:00Z",
                    }
                ]
            },
        }
    }

    build_strategy_lifecycle_state(config, run, now="2026-06-06T00:00:00Z")

    record = _read_lifecycle(run)["records"][0]

    assert record["lifecycle_status"] == "retired"
    assert record["retirement"]["state"] == "explicitly_retired"
    assert record["retirement"]["policy_refs"]
    assert record["promotion"] == {"state": "not_requested", "policy_refs": []}
    assert "config:quant.lifecycle_policy.records" in record["source_artifacts"]
    serialized = json.dumps(record, ensure_ascii=False, sort_keys=True)
    assert "private local review note" not in serialized
    assert run.manifest["counts"]["strategy_lifecycle_retired"] == 1
    assert run.manifest["counts"]["strategy_lifecycle_policy_records"] == 1


def test_strategy_lifecycle_records_missing_upstream_as_degraded_artifact(tmp_path: Path) -> None:
    run = _run_context(tmp_path)

    build_strategy_lifecycle_state(
        {"quant": {"enabled": True, "strategies": [{"name": "tsmom_vol_scaled"}]}},
        run,
        now="2026-06-06T00:00:00Z",
    )

    artifact = _read_lifecycle(run)
    coverage = {(item["source_layer"], item["source_artifact"]): item for item in artifact["coverage"]}

    assert artifact["status"] == "degraded"
    assert artifact["records"] == []
    assert coverage[("gate", "analysis/strategy_effectiveness_gates.json")]["status"] == "missing"
    assert coverage[("strategy_run", "analysis/quant_strategy_runs.json")]["status"] == "missing"
    assert run.manifest["strategy_lifecycle_state"]["status"] == "degraded"
    assert run.manifest["counts"]["strategy_lifecycle_records"] == 0


def test_strategy_lifecycle_skips_when_quant_disabled(tmp_path: Path) -> None:
    run = _run_context(tmp_path)

    artifacts = build_strategy_lifecycle_state({"quant": {"enabled": False}}, run)

    assert artifacts == []
    assert not (run.analysis_dir / "strategy_lifecycle_state.json").exists()
    assert run.manifest["strategy_lifecycle_state"]["status"] == "skipped"
    assert "strategy_lifecycle_state" not in run.manifest["artifacts"]


def _write_minimal_upstream(run: RunContext, *, gate_status: str) -> None:
    write_json(
        run.analysis_dir / "quant_strategy_runs.json",
        {
            "artifact_type": "quant_strategy_runs",
            "status": "ok",
            "runs": [
                _quant_run("tsmom_vol_scaled", None, None, version=1, params={"return_window": 20}),
            ],
            "warnings": [],
            "errors": [],
            "source_artifacts": ["raw/market_data_views.json"],
        },
    )
    write_json(
        run.analysis_dir / "strategy_evaluation_summary.json",
        {
            "artifact_type": "strategy_evaluation_summary",
            "status": "ok",
            "records": [
                _evaluation("tsmom_vol_scaled", None, None, version=1, params={"return_window": 20}),
            ],
            "warnings": [],
            "errors": [],
            "source_artifacts": ["analysis/quant_strategy_runs.json"],
        },
    )
    write_json(
        run.analysis_dir / "strategy_experiment.json",
        {
            "artifact_type": "strategy_experiment",
            "status": "ok",
            "candidates": [],
            "warnings": [],
            "errors": [],
            "source_artifacts": ["analysis/strategy_benchmark_suite.json"],
        },
    )
    write_json(
        run.analysis_dir / "strategy_effectiveness_gates.json",
        {
            "artifact_type": "strategy_effectiveness_gates",
            "status": "ok",
            "records": [_gate("tsmom_vol_scaled", None, None, gate_status, params={"return_window": 20})],
            "warnings": [],
            "errors": [],
            "source_artifacts": ["analysis/strategy_experiment.json"],
        },
    )
    write_json(
        run.analysis_dir / "outcome_targets.json",
        {
            "artifact_type": "outcome_targets",
            "status": "skipped",
            "targets": [],
            "warnings": [],
            "errors": [],
            "source_artifacts": [],
        },
    )
    write_json(
        run.analysis_dir / "outcome_evaluations.json",
        {
            "artifact_type": "outcome_evaluations",
            "status": "skipped",
            "evaluations": [],
            "warnings": [],
            "errors": [],
            "source_artifacts": [],
        },
    )


def _quant_run(
    strategy_name: str,
    symbol: str | None,
    timeframe: str | None,
    *,
    version: int,
    params: dict[str, Any],
) -> dict[str, Any]:
    return {
        "strategy_run_id": f"run:{strategy_name}:{symbol or 'all'}:{timeframe or 'all'}",
        "strategy_name": strategy_name,
        "strategy_version": version,
        "source": "binance",
        "symbol": symbol,
        "timeframe": timeframe,
        "status": "succeeded",
        "params": params,
        "warnings": [],
        "errors": [],
        "source_artifacts": ["raw/market_data_views.json"],
    }


def _evaluation(
    strategy_name: str,
    symbol: str | None,
    timeframe: str | None,
    *,
    version: int,
    params: dict[str, Any],
) -> dict[str, Any]:
    return {
        "evaluation_id": f"evaluation:{strategy_name}:{symbol or 'all'}:{timeframe or 'all'}",
        "strategy_name": strategy_name,
        "strategy_version": version,
        "symbol": symbol,
        "timeframe": timeframe,
        "status": "succeeded",
        "params": params,
        "walk_forward": {"status": "succeeded", "summary": {"result_stability": "stable"}},
        "overfitting_risk": {"status": "low"},
        "warnings": [],
        "errors": [],
        "source_artifacts": ["analysis/quant_strategy_runs.json"],
    }


def _gate(
    strategy_name: str,
    symbol: str | None,
    timeframe: str | None,
    status: str,
    *,
    params: dict[str, Any],
) -> dict[str, Any]:
    return {
        "gate_id": f"gate:{strategy_name}:{symbol or 'all'}:{timeframe or 'all'}",
        "strategy_name": strategy_name,
        "symbol": symbol,
        "timeframe": timeframe,
        "status": status,
        "params": params,
        "reasons": [{"code": "benchmark_coverage_met", "severity": "pass"}],
        "warnings": [],
        "errors": [],
        "source_artifacts": ["analysis/strategy_experiment.json"],
    }


def _strategy_gate_target(
    target_id: str,
    strategy_name: str,
    symbol: str,
    timeframe: str,
) -> dict[str, Any]:
    return {
        "target_id": target_id,
        "target_kind": "strategy_gate",
        "source_record_id": f"gate:{strategy_name}:{symbol}:{timeframe}",
        "source": "binance",
        "symbol": symbol,
        "timeframe": timeframe,
        "expected_observation": {
            "observation_type": "strategy_gate_follow_through",
            "strategy_name": strategy_name,
            "gate_status": "effective",
        },
        "warnings": [],
        "errors": [],
        "source_artifacts": ["analysis/strategy_effectiveness_gates.json"],
    }


def _run_context(tmp_path: Path) -> RunContext:
    run_dir = tmp_path / "runs" / "run-1"
    raw_dir = run_dir / "raw"
    analysis_dir = run_dir / "analysis"
    codex_context_dir = run_dir / "codex_context"
    report_dir = run_dir / "report"
    for directory in (raw_dir, analysis_dir, codex_context_dir, report_dir):
        directory.mkdir(parents=True)
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


def _read_lifecycle(run: RunContext) -> dict[str, Any]:
    return json.loads((run.analysis_dir / "strategy_lifecycle_state.json").read_text(encoding="utf-8"))
