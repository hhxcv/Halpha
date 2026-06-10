from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from .ohlcv_store import OHLCVParquetStore, OHLCVStoreError
from .pipeline import PipelineError, RunContext
from .quant.registry import get_strategy_definition
from .quant.strategy_evaluation import evaluate_single_window_backtest, evaluate_walk_forward_backtest
from .strategy_effectiveness_gates import (
    STRATEGY_EFFECTIVENESS_GATES_ARTIFACT,
    build_strategy_effectiveness_gates,
)
from .strategy_experiment_material import (
    STRATEGY_EFFECTIVENESS_GATES_ARTIFACT as PIPELINE_STRATEGY_EFFECTIVENESS_GATES_ARTIFACT,
    STRATEGY_EXPERIMENT_ARTIFACT as PIPELINE_STRATEGY_EXPERIMENT_ARTIFACT,
    STRATEGY_EXPERIMENT_MATERIAL_ARTIFACT,
    render_strategy_experiment_material,
)
from .strategy_benchmark_suite import create_strategy_benchmark_suite_artifact
from .storage import display_path, ensure_directory, write_json


PIPELINE_STAGE_NAME = "build_strategy_experiment_material"
STRATEGY_EXPERIMENT_ARTIFACT = "strategy_experiment.json"
STRATEGY_EXPERIMENT_MANIFEST_ARTIFACT = "manifest.json"
STRATEGY_EXPERIMENT_BENCHMARK_ARTIFACT = "strategy_benchmark_suite.json"
EXPERIMENT_SOURCE = "strategy_experiment"


class StrategyExperimentError(Exception):
    def __init__(self, message: str, *, exit_code: int = 3) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass(frozen=True)
class StrategyExperimentResult:
    succeeded: bool
    exit_code: int
    status: str
    reason: str | None
    output_dir: Path
    artifact_path: Path
    benchmark_suite_path: Path
    gates_path: Path
    manifest_path: Path


def build_strategy_experiment_material(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | None = None,
) -> list[str]:
    if not _pipeline_experiment_enabled(config):
        _record_pipeline_skipped(run, reason="quant or benchmark suite disabled")
        return []

    benchmark_suite = _read_pipeline_benchmark_suite(run)
    if benchmark_suite is None:
        _record_pipeline_skipped(run, reason="analysis/strategy_benchmark_suite.json not generated")
        return []

    try:
        clock_value = _utc_now(now)
        strategies = _configured_strategies(config, strategy_names=None)
        market = _market_config(config)
        ohlcv = _ohlcv_config(market)
        _require_benchmark_suite_enabled(config)
        storage_dir = _storage_dir(ohlcv, run.config_path)
    except StrategyExperimentError as exc:
        raise PipelineError(str(exc), stage=PIPELINE_STAGE_NAME, exit_code=exc.exit_code) from exc

    candidates = [
        _candidate_record(
            strategy=strategy,
            benchmarks=benchmark_suite["benchmarks"],
            storage_dir=storage_dir,
        )
        for strategy in strategies
    ]
    coverage = _coverage(candidates, benchmark_suite)
    warnings = _unique_items(
        item
        for candidate in candidates
        for item in candidate.get("warnings", [])
        if isinstance(item, dict)
    )
    errors = [
        error
        for candidate in candidates
        for error in candidate.get("errors", [])
        if isinstance(error, dict)
    ]
    artifact = {
        "schema_version": 1,
        "artifact_type": "strategy_experiment",
        "created_at": _format_utc(clock_value),
        "experiment_id": f"{run.run_id}_strategy_experiment",
        "inputs": {
            "candidate_source": "configured_quant_strategies",
            "strategy_names": [str(strategy.get("name")) for strategy in strategies],
            "benchmark_suite_artifact": "analysis/strategy_benchmark_suite.json",
        },
        "source_artifacts": ["analysis/strategy_benchmark_suite.json"],
        "coverage": coverage,
        "candidates": candidates,
        "warnings": warnings,
        "errors": errors,
    }
    gates = build_strategy_effectiveness_gates(
        artifact,
        config,
        created_at=_format_utc(clock_value),
        source_artifacts=[PIPELINE_STRATEGY_EXPERIMENT_ARTIFACT],
    )
    material = render_strategy_experiment_material(artifact, gates)

    write_json(run.analysis_dir / "strategy_experiment.json", artifact)
    write_json(run.analysis_dir / "strategy_effectiveness_gates.json", gates)
    (run.analysis_dir / "strategy_experiment_material.md").write_text(material, encoding="utf-8")
    run.manifest["artifacts"]["strategy_experiment"] = PIPELINE_STRATEGY_EXPERIMENT_ARTIFACT
    run.manifest["artifacts"]["strategy_effectiveness_gates"] = (
        PIPELINE_STRATEGY_EFFECTIVENESS_GATES_ARTIFACT
    )
    run.manifest["artifacts"]["strategy_experiment_material"] = STRATEGY_EXPERIMENT_MATERIAL_ARTIFACT
    _record_pipeline_summary(run, artifact=artifact, gates=gates)
    return [
        PIPELINE_STRATEGY_EXPERIMENT_ARTIFACT,
        PIPELINE_STRATEGY_EFFECTIVENESS_GATES_ARTIFACT,
        STRATEGY_EXPERIMENT_MATERIAL_ARTIFACT,
    ]


def run_strategy_experiment(
    config: dict[str, Any],
    *,
    config_path: Path,
    strategy_names: list[str] | None = None,
    output_dir: Path | None = None,
    now: datetime | None = None,
) -> StrategyExperimentResult:
    clock_value = _utc_now(now)
    strategies = _configured_strategies(config, strategy_names=strategy_names)
    market = _market_config(config)
    ohlcv = _ohlcv_config(market)
    _require_benchmark_suite_enabled(config)
    storage_dir = _storage_dir(ohlcv, config_path)
    base_output_dir = _base_output_dir(config, config_path=config_path, output_dir=output_dir)

    try:
        benchmark_suite = create_strategy_benchmark_suite_artifact(
            config,
            config_path=config_path,
            run_output_dir=base_output_dir,
            now=clock_value,
        )
    except PipelineError as exc:
        raise StrategyExperimentError(str(exc), exit_code=exc.exit_code) from exc
    target_dir = _unique_output_dir(base_output_dir, _experiment_id(clock_value))
    benchmark_suite_path = target_dir / STRATEGY_EXPERIMENT_BENCHMARK_ARTIFACT
    write_json(benchmark_suite_path, benchmark_suite)

    candidates = [
        _candidate_record(
            strategy=strategy,
            benchmarks=benchmark_suite["benchmarks"],
            storage_dir=storage_dir,
        )
        for strategy in strategies
    ]
    coverage = _coverage(candidates, benchmark_suite)
    warnings = _unique_items(
        item
        for candidate in candidates
        for item in candidate.get("warnings", [])
        if isinstance(item, dict)
    )
    errors = [
        error
        for candidate in candidates
        for error in candidate.get("errors", [])
        if isinstance(error, dict)
    ]
    artifact = {
        "schema_version": 1,
        "artifact_type": "strategy_experiment",
        "created_at": _format_utc(clock_value),
        "experiment_id": _experiment_id(clock_value),
        "inputs": {
            "candidate_source": "configured_quant_strategies",
            "strategy_names": [str(strategy.get("name")) for strategy in strategies],
            "benchmark_suite_artifact": STRATEGY_EXPERIMENT_BENCHMARK_ARTIFACT,
        },
        "source_artifacts": [STRATEGY_EXPERIMENT_BENCHMARK_ARTIFACT],
        "coverage": coverage,
        "candidates": candidates,
        "warnings": warnings,
        "errors": errors,
    }
    artifact_path = target_dir / STRATEGY_EXPERIMENT_ARTIFACT
    write_json(artifact_path, artifact)

    gates = build_strategy_effectiveness_gates(
        artifact,
        config,
        created_at=_format_utc(clock_value),
    )
    gates_path = target_dir / STRATEGY_EFFECTIVENESS_GATES_ARTIFACT
    write_json(gates_path, gates)

    manifest_path = target_dir / STRATEGY_EXPERIMENT_MANIFEST_ARTIFACT
    manifest = _manifest(
        config_path=config_path,
        created_at=_format_utc(clock_value),
        strategy_names=[str(strategy.get("name")) for strategy in strategies],
        benchmark_suite=benchmark_suite,
        artifact=artifact,
        gates=gates,
        output_dir=target_dir,
        artifact_path=artifact_path,
        benchmark_suite_path=benchmark_suite_path,
        gates_path=gates_path,
        manifest_path=manifest_path,
    )
    write_json(manifest_path, manifest)

    return StrategyExperimentResult(
        succeeded=True,
        exit_code=0,
        status="succeeded",
        reason=None,
        output_dir=target_dir,
        artifact_path=artifact_path,
        benchmark_suite_path=benchmark_suite_path,
        gates_path=gates_path,
        manifest_path=manifest_path,
    )


def _pipeline_experiment_enabled(config: dict[str, Any]) -> bool:
    quant = config.get("quant") if isinstance(config.get("quant"), dict) else {}
    market = config.get("market") if isinstance(config.get("market"), dict) else {}
    ohlcv = market.get("ohlcv") if isinstance(market.get("ohlcv"), dict) else {}
    suite_config = quant.get("benchmark_suite") if isinstance(quant.get("benchmark_suite"), dict) else {}
    return (
        quant.get("enabled") is True
        and market.get("enabled") is True
        and isinstance(ohlcv, dict)
        and suite_config.get("enabled") is not False
    )


def _read_pipeline_benchmark_suite(run: RunContext) -> dict[str, Any] | None:
    path = run.analysis_dir / "strategy_benchmark_suite.json"
    if not path.exists():
        return None
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PipelineError(
            "analysis/strategy_benchmark_suite.json is not valid JSON: "
            f"{exc.msg}.",
            stage=PIPELINE_STAGE_NAME,
            exit_code=3,
        ) from exc
    if not isinstance(artifact, dict):
        raise PipelineError(
            "analysis/strategy_benchmark_suite.json must be a mapping.",
            stage=PIPELINE_STAGE_NAME,
            exit_code=3,
        )
    benchmarks = artifact.get("benchmarks")
    if not isinstance(benchmarks, list):
        raise PipelineError(
            "analysis/strategy_benchmark_suite.json must contain a benchmarks list.",
            stage=PIPELINE_STAGE_NAME,
            exit_code=3,
        )
    return artifact


def _record_pipeline_skipped(run: RunContext, *, reason: str) -> None:
    run.manifest["counts"]["strategy_experiment_candidates"] = 0
    run.manifest["counts"]["strategy_experiment_evaluations"] = 0
    run.manifest["counts"]["strategy_experiment_evaluations_succeeded"] = 0
    run.manifest["counts"]["strategy_experiment_evaluations_failed"] = 0
    run.manifest["counts"]["strategy_experiment_evaluations_insufficient_data"] = 0
    run.manifest["counts"]["strategy_gate_candidates"] = 0
    run.manifest["counts"]["strategy_gate_effective"] = 0
    run.manifest["counts"]["strategy_gate_watchlisted"] = 0
    run.manifest["counts"]["strategy_gate_rejected"] = 0
    run.manifest["counts"]["strategy_gate_insufficient_evidence"] = 0
    run.manifest["counts"]["strategy_experiment_material_records"] = 0
    run.manifest["strategy_experiment"] = {
        "enabled": False,
        "status": "skipped",
        "reason": reason,
        "artifacts": {},
        "counts": {},
        "warnings": [],
        "errors": [],
    }


def _record_pipeline_summary(
    run: RunContext,
    *,
    artifact: dict[str, Any],
    gates: dict[str, Any],
) -> None:
    coverage = artifact["coverage"]
    gate_coverage = gates["coverage"] if isinstance(gates.get("coverage"), dict) else {}
    run.manifest["counts"]["strategy_experiment_candidates"] = int(
        coverage.get("strategy_candidates") or 0
    )
    run.manifest["counts"]["strategy_experiment_evaluations"] = int(coverage.get("evaluations") or 0)
    run.manifest["counts"]["strategy_experiment_evaluations_succeeded"] = int(
        coverage.get("evaluations_succeeded") or 0
    )
    run.manifest["counts"]["strategy_experiment_evaluations_failed"] = int(
        coverage.get("evaluations_failed") or 0
    )
    run.manifest["counts"]["strategy_experiment_evaluations_insufficient_data"] = int(
        coverage.get("evaluations_insufficient_data") or 0
    )
    run.manifest["counts"]["strategy_gate_candidates"] = int(
        gate_coverage.get("strategy_candidates") or 0
    )
    run.manifest["counts"]["strategy_gate_effective"] = int(gate_coverage.get("effective") or 0)
    run.manifest["counts"]["strategy_gate_watchlisted"] = int(
        gate_coverage.get("watchlisted") or 0
    )
    run.manifest["counts"]["strategy_gate_rejected"] = int(gate_coverage.get("rejected") or 0)
    run.manifest["counts"]["strategy_gate_insufficient_evidence"] = int(
        gate_coverage.get("insufficient_evidence") or 0
    )
    run.manifest["counts"]["strategy_experiment_material_records"] = len(
        _dict_list(gates.get("records"))
    )
    run.manifest["strategy_experiment"] = {
        "enabled": True,
        "status": "succeeded",
        "artifacts": {
            "strategy_experiment": PIPELINE_STRATEGY_EXPERIMENT_ARTIFACT,
            "strategy_effectiveness_gates": PIPELINE_STRATEGY_EFFECTIVENESS_GATES_ARTIFACT,
            "strategy_experiment_material": STRATEGY_EXPERIMENT_MATERIAL_ARTIFACT,
        },
        "counts": {
            "strategy_candidates": run.manifest["counts"]["strategy_experiment_candidates"],
            "evaluations": run.manifest["counts"]["strategy_experiment_evaluations"],
            "gate_effective": run.manifest["counts"]["strategy_gate_effective"],
            "gate_watchlisted": run.manifest["counts"]["strategy_gate_watchlisted"],
            "gate_rejected": run.manifest["counts"]["strategy_gate_rejected"],
            "gate_insufficient_evidence": run.manifest["counts"][
                "strategy_gate_insufficient_evidence"
            ],
        },
        "warnings": _unique_items(
            [
                *_warning_items(artifact.get("warnings")),
                *_warning_items(gates.get("warnings")),
            ]
        ),
        "errors": [
            *_error_items(artifact.get("errors")),
            *_error_items(gates.get("errors")),
        ],
    }


def _candidate_record(
    *,
    strategy: dict[str, Any],
    benchmarks: list[dict[str, Any]],
    storage_dir: Path,
) -> dict[str, Any]:
    name = str(strategy.get("name"))
    definition = get_strategy_definition(name)
    if definition is None:
        error = {
            "error_type": "UnsupportedStrategy",
            "message": f"{name} is not implemented.",
            "stage": EXPERIMENT_SOURCE,
        }
        return {
            "strategy_name": name,
            "params": strategy.get("params") if isinstance(strategy.get("params"), dict) else {},
            "status": "failed",
            "summary": _summary([]),
            "evaluations": [],
            "warnings": [],
            "errors": [error],
        }

    evaluations = [
        _evaluation_record(
            strategy=strategy,
            benchmark=benchmark,
            storage_dir=storage_dir,
            definition=definition,
        )
        for benchmark in benchmarks
    ]
    warnings = _unique_items(
        item
        for evaluation in evaluations
        for item in evaluation.get("warnings", [])
        if isinstance(item, dict)
    )
    errors = [
        error
        for evaluation in evaluations
        for error in evaluation.get("errors", [])
        if isinstance(error, dict)
    ]
    return {
        "strategy_name": name,
        "params": strategy.get("params") if isinstance(strategy.get("params"), dict) else {},
        "status": _candidate_status(evaluations),
        "summary": _summary(evaluations),
        "evaluations": evaluations,
        "warnings": warnings,
        "errors": errors,
    }


def _evaluation_record(
    *,
    strategy: dict[str, Any],
    benchmark: dict[str, Any],
    storage_dir: Path,
    definition: Any,
) -> dict[str, Any]:
    identity = _evaluation_identity(strategy, benchmark)
    if benchmark.get("status") != "succeeded":
        return {
            **identity,
            "status": "insufficient_data",
            "benchmark_status": benchmark.get("status"),
            "metrics": {},
            "single_window": {},
            "walk_forward": {},
            "warnings": [
                _warning(
                    "benchmark_not_succeeded",
                    (
                        f"Benchmark {benchmark.get('benchmark_id')} status is "
                        f"{benchmark.get('status')}; strategy evaluation was not run."
                    ),
                )
            ],
            "errors": [],
        }

    try:
        rows = _benchmark_rows(benchmark, storage_dir=storage_dir)
        if len(rows) != int(benchmark.get("row_count") or 0):
            return _insufficient_record(
                identity,
                benchmark,
                f"Loaded {len(rows)} rows, expected benchmark row_count {benchmark.get('row_count')}.",
            )
        signals = definition.signal_records(strategy, _view_from_benchmark(benchmark), rows)
        evaluation = evaluate_single_window_backtest(
            strategy=strategy,
            market_identity={
                "source": benchmark.get("source"),
                "symbol": benchmark.get("symbol"),
                "timeframe": benchmark.get("timeframe"),
            },
            ohlcv_rows=rows,
            signal_records=signals,
            cost_assumptions=_cost_assumptions(strategy),
        )
        walk_forward = evaluate_walk_forward_backtest(
            strategy=strategy,
            market_identity={
                "source": benchmark.get("source"),
                "symbol": benchmark.get("symbol"),
                "timeframe": benchmark.get("timeframe"),
            },
            ohlcv_rows=rows,
            signal_records=signals,
            cost_assumptions=_cost_assumptions(strategy),
        )
    except (OHLCVStoreError, KeyError, TypeError, ValueError) as exc:
        return _failed_record(identity, type(exc).__name__, str(exc))

    return {
        **identity,
        "status": str(evaluation.get("status") or "failed"),
        "benchmark_status": benchmark.get("status"),
        "metrics": _metrics(evaluation),
        "single_window": evaluation,
        "walk_forward": _bounded_walk_forward(walk_forward),
        "warnings": _unique_items(
            [
                *_warning_items(evaluation.get("warnings")),
                *_warning_items(walk_forward.get("warnings")),
            ]
        ),
        "errors": [
            *_error_items(evaluation.get("errors")),
            *_error_items(walk_forward.get("errors")),
        ],
    }


def _benchmark_rows(benchmark: dict[str, Any], *, storage_dir: Path) -> list[dict[str, Any]]:
    store = OHLCVParquetStore(storage_dir)
    records = store.read_records(
        source=str(benchmark["source"]),
        symbol=str(benchmark["symbol"]),
        timeframe=str(benchmark["timeframe"]),
    )
    start = str(benchmark["input_window_start"])
    end = str(benchmark["input_window_end"])
    columns = [str(column) for column in benchmark.get("included_columns", [])] or [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]
    return [
        {column: record[column] for column in columns}
        for record in records
        if start <= str(record["open_time"]) <= end
    ]


def _view_from_benchmark(benchmark: dict[str, Any]) -> dict[str, Any]:
    return {
        "view_id": benchmark.get("benchmark_id"),
        "source": benchmark.get("source"),
        "symbol": benchmark.get("symbol"),
        "timeframe": benchmark.get("timeframe"),
        "requested_lookback": benchmark.get("requested_lookback"),
        "input_window_start": benchmark.get("input_window_start"),
        "input_window_end": benchmark.get("input_window_end"),
        "latest_candle_time": benchmark.get("latest_candle_time"),
        "row_count": benchmark.get("row_count"),
        "storage_ref": benchmark.get("storage_ref"),
        "included_columns": benchmark.get("included_columns"),
        "insufficient_data": False,
        "warnings": [],
    }


def _evaluation_identity(strategy: dict[str, Any], benchmark: dict[str, Any]) -> dict[str, Any]:
    name = str(strategy.get("name"))
    benchmark_id = str(benchmark.get("benchmark_id"))
    return {
        "evaluation_id": f"strategy_experiment:{name}:{benchmark_id}",
        "strategy_name": name,
        "benchmark_id": benchmark_id,
        "source": benchmark.get("source"),
        "symbol": benchmark.get("symbol"),
        "timeframe": benchmark.get("timeframe"),
        "window_identity": benchmark.get("window_identity"),
        "input_window_start": benchmark.get("input_window_start"),
        "input_window_end": benchmark.get("input_window_end"),
    }


def _insufficient_record(
    identity: dict[str, Any],
    benchmark: dict[str, Any],
    message: str,
) -> dict[str, Any]:
    return {
        **identity,
        "status": "insufficient_data",
        "benchmark_status": benchmark.get("status"),
        "metrics": {},
        "single_window": {},
        "walk_forward": {},
        "warnings": [_warning("benchmark_row_mismatch", message)],
        "errors": [],
    }


def _failed_record(identity: dict[str, Any], error_type: str, message: str) -> dict[str, Any]:
    return {
        **identity,
        "status": "failed",
        "benchmark_status": "succeeded",
        "metrics": {},
        "single_window": {},
        "walk_forward": {},
        "warnings": [],
        "errors": [
            {
                "error_type": error_type,
                "message": message,
                "stage": EXPERIMENT_SOURCE,
            }
        ],
    }


def _metrics(evaluation: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy": evaluation.get("strategy_metrics") if isinstance(evaluation.get("strategy_metrics"), dict) else {},
        "baseline": evaluation.get("baseline_metrics") if isinstance(evaluation.get("baseline_metrics"), dict) else {},
        "relative": evaluation.get("relative_metrics") if isinstance(evaluation.get("relative_metrics"), dict) else {},
        "trade": evaluation.get("trade_summary") if isinstance(evaluation.get("trade_summary"), dict) else {},
    }


def _bounded_walk_forward(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "enabled": value.get("enabled") is True,
        "status": value.get("status"),
        "method": value.get("method") if isinstance(value.get("method"), dict) else {},
        "sample": value.get("sample") if isinstance(value.get("sample"), dict) else {},
        "window_policy": value.get("window_policy") if isinstance(value.get("window_policy"), dict) else {},
        "summary": value.get("summary") if isinstance(value.get("summary"), dict) else {},
        "window_count": len(value.get("windows")) if isinstance(value.get("windows"), list) else 0,
        "warnings": _warning_items(value.get("warnings")),
        "errors": _error_items(value.get("errors")),
    }


def _summary(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    succeeded = [item for item in evaluations if item.get("status") == "succeeded"]
    net_returns = _metric_values(succeeded, "strategy", "net_return_pct")
    excess_returns = _metric_values(succeeded, "relative", "excess_return_vs_buy_and_hold_pct")
    drawdowns = _metric_values(succeeded, "strategy", "max_drawdown_pct")
    trade_counts = _metric_values(succeeded, "trade", "trade_count")
    return {
        "benchmark_records": len(evaluations),
        "succeeded": len(succeeded),
        "insufficient_data": sum(1 for item in evaluations if item.get("status") == "insufficient_data"),
        "failed": sum(1 for item in evaluations if item.get("status") == "failed"),
        "skipped": sum(1 for item in evaluations if item.get("status") == "skipped"),
        "mean_net_return_pct": _rounded_mean(net_returns),
        "mean_excess_return_vs_buy_and_hold_pct": _rounded_mean(excess_returns),
        "positive_net_return_benchmark_pct": _positive_pct(net_returns),
        "worst_max_drawdown_pct": min(drawdowns) if drawdowns else None,
        "total_trade_count": int(sum(trade_counts)) if trade_counts else 0,
    }


def _coverage(candidates: list[dict[str, Any]], benchmark_suite: dict[str, Any]) -> dict[str, Any]:
    evaluations = [
        evaluation
        for candidate in candidates
        for evaluation in candidate.get("evaluations", [])
        if isinstance(evaluation, dict)
    ]
    benchmark_coverage = benchmark_suite.get("coverage") if isinstance(benchmark_suite.get("coverage"), dict) else {}
    return {
        "strategy_candidates": len(candidates),
        "benchmark_records": int(benchmark_coverage.get("benchmark_records") or 0),
        "benchmark_succeeded": int(benchmark_coverage.get("succeeded") or 0),
        "benchmark_insufficient_data": int(benchmark_coverage.get("insufficient_data") or 0),
        "evaluations": len(evaluations),
        "evaluations_succeeded": sum(1 for item in evaluations if item.get("status") == "succeeded"),
        "evaluations_insufficient_data": sum(1 for item in evaluations if item.get("status") == "insufficient_data"),
        "evaluations_failed": sum(1 for item in evaluations if item.get("status") == "failed"),
        "evaluations_skipped": sum(1 for item in evaluations if item.get("status") == "skipped"),
    }


def _manifest(
    *,
    config_path: Path,
    created_at: str,
    strategy_names: list[str],
    benchmark_suite: dict[str, Any],
    artifact: dict[str, Any],
    gates: dict[str, Any],
    output_dir: Path,
    artifact_path: Path,
    benchmark_suite_path: Path,
    gates_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    coverage = artifact["coverage"]
    gate_coverage = gates["coverage"] if isinstance(gates.get("coverage"), dict) else {}
    return {
        "schema_version": 1,
        "artifact_type": "strategy_experiment_manifest",
        "created_at": created_at,
        "status": "succeeded",
        "config_path": display_path(config_path, base=config_path.parent),
        "inputs": {
            "strategy_names": strategy_names,
            "benchmark_records": int(benchmark_suite.get("coverage", {}).get("benchmark_records") or 0),
            "output_dir": display_path(output_dir, base=manifest_path.parent),
        },
        "artifacts": {
            "strategy_experiment": display_path(artifact_path, base=manifest_path.parent),
            "strategy_benchmark_suite": display_path(benchmark_suite_path, base=manifest_path.parent),
            "strategy_effectiveness_gates": display_path(gates_path, base=manifest_path.parent),
            "manifest": display_path(manifest_path, base=manifest_path.parent),
        },
        "counts": {
            **coverage,
            "strategy_gate_candidates": int(gate_coverage.get("strategy_candidates") or 0),
            "strategy_gate_effective": int(gate_coverage.get("effective") or 0),
            "strategy_gate_watchlisted": int(gate_coverage.get("watchlisted") or 0),
            "strategy_gate_rejected": int(gate_coverage.get("rejected") or 0),
            "strategy_gate_insufficient_evidence": int(gate_coverage.get("insufficient_evidence") or 0),
        },
        "failures": _failure_summaries(artifact),
        "warnings": _unique_items(
            [
                *_warning_items(artifact.get("warnings")),
                *_warning_items(gates.get("warnings")),
            ]
        ),
        "errors": [
            *_error_items(artifact.get("errors")),
            *_error_items(gates.get("errors")),
        ],
    }


def _failure_summaries(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    failures = []
    for candidate in artifact.get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        for evaluation in candidate.get("evaluations", []):
            if not isinstance(evaluation, dict) or evaluation.get("status") != "failed":
                continue
            errors = _error_items(evaluation.get("errors"))
            if not errors:
                continue
            first = errors[0]
            failures.append(
                {
                    "strategy_name": candidate.get("strategy_name"),
                    "benchmark_id": evaluation.get("benchmark_id"),
                    "error_type": first.get("error_type"),
                    "message": first.get("message"),
                }
            )
    return failures


def _configured_strategies(
    config: dict[str, Any],
    *,
    strategy_names: list[str] | None,
) -> list[dict[str, Any]]:
    quant = config.get("quant") if isinstance(config.get("quant"), dict) else {}
    if quant.get("enabled") is not True:
        raise StrategyExperimentError("quant.enabled must be true for strategy experiments.", exit_code=2)
    strategies = [
        strategy
        for strategy in quant.get("strategies", [])
        if isinstance(strategy, dict) and strategy.get("enabled", True) is not False
    ] if isinstance(quant.get("strategies"), list) else []
    if strategy_names:
        requested = set(strategy_names)
        strategies = [strategy for strategy in strategies if str(strategy.get("name")) in requested]
        found = {str(strategy.get("name")) for strategy in strategies}
        missing = sorted(requested - found)
        if missing:
            raise StrategyExperimentError(f"strategy is not configured and enabled: {', '.join(missing)}", exit_code=2)
    if not strategies:
        raise StrategyExperimentError("no enabled strategy candidates are configured.", exit_code=2)
    return sorted(strategies, key=lambda item: str(item.get("name")))


def _market_config(config: dict[str, Any]) -> dict[str, Any]:
    market = config.get("market")
    if not isinstance(market, dict) or market.get("enabled") is not True:
        raise StrategyExperimentError("market.enabled must be true for strategy experiments.", exit_code=2)
    return market


def _ohlcv_config(market: dict[str, Any]) -> dict[str, Any]:
    ohlcv = market.get("ohlcv")
    if not isinstance(ohlcv, dict):
        raise StrategyExperimentError("market.ohlcv must be configured for strategy experiments.", exit_code=2)
    return ohlcv


def _require_benchmark_suite_enabled(config: dict[str, Any]) -> None:
    quant = config.get("quant") if isinstance(config.get("quant"), dict) else {}
    suite_config = quant.get("benchmark_suite") if isinstance(quant.get("benchmark_suite"), dict) else {}
    if suite_config.get("enabled") is False:
        raise StrategyExperimentError(
            "quant.benchmark_suite.enabled must not be false for strategy experiments.",
            exit_code=2,
        )


def _cost_assumptions(strategy: dict[str, Any]) -> dict[str, Any]:
    backtest = strategy.get("backtest") if isinstance(strategy.get("backtest"), dict) else {}
    return {
        "fees_bps": backtest.get("fees_bps", 0.0),
        "slippage_bps": backtest.get("slippage_bps", 0.0),
    }


def _storage_dir(ohlcv: dict[str, Any], config_path: Path) -> Path:
    storage_dir = Path(str(ohlcv["storage_dir"]))
    if storage_dir.is_absolute():
        return storage_dir
    return config_path.parent / storage_dir


def _base_output_dir(config: dict[str, Any], *, config_path: Path, output_dir: Path | None) -> Path:
    if output_dir is not None:
        return output_dir
    run = config.get("run") if isinstance(config.get("run"), dict) else {}
    root = Path(str(run.get("output_dir") or "runs"))
    if not root.is_absolute():
        root = config_path.parent / root
    return root / "strategy_experiments"


def _unique_output_dir(output_dir: Path, experiment_id: str) -> Path:
    ensure_directory(output_dir)
    candidate = output_dir / experiment_id
    if not candidate.exists():
        candidate.mkdir()
        return candidate
    for index in range(1, 100):
        candidate = output_dir / f"{experiment_id}-{index:02d}"
        if not candidate.exists():
            candidate.mkdir()
            return candidate
    raise StrategyExperimentError(f"could not create a unique output directory for {experiment_id}.")


def _experiment_id(now: datetime) -> str:
    timestamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}_strategy_experiment"


def _candidate_status(evaluations: list[dict[str, Any]]) -> str:
    if any(item.get("status") == "failed" for item in evaluations):
        return "failed"
    if any(item.get("status") == "succeeded" for item in evaluations):
        return "succeeded"
    if any(item.get("status") == "insufficient_data" for item in evaluations):
        return "insufficient_data"
    return "skipped"


def _metric_values(evaluations: list[dict[str, Any]], section: str, key: str) -> list[float]:
    values = []
    for evaluation in evaluations:
        metrics = evaluation.get("metrics") if isinstance(evaluation.get("metrics"), dict) else {}
        section_values = metrics.get(section) if isinstance(metrics.get(section), dict) else {}
        value = section_values.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        values.append(float(value))
    return values


def _rounded_mean(values: list[float]) -> float | None:
    return round(mean(values), 6) if values else None


def _positive_pct(values: list[float]) -> float | None:
    if not values:
        return None
    return round((sum(1 for value in values if value > 0) / len(values)) * 100, 6)


def _warning(code: str, message: str) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "source": EXPERIMENT_SOURCE,
    }


def _warning_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _error_items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _dict_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _unique_items(items: Any) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for item in items:
        key = (item.get("code"), item.get("message"), item.get("source"))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _utc_now(now: datetime | None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise StrategyExperimentError("now must include a UTC offset.", exit_code=2)
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
