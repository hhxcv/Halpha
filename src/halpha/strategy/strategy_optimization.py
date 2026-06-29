from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from statistics import mean
from typing import Any

from halpha.market.ohlcv_query import OHLCVQueryError, query_ohlcv_records
from halpha.quant.registry import get_strategy_definition, get_supported_strategy_spec
from halpha.quant.strategy_evaluation import evaluate_single_window_backtest
from halpha.strategy.strategy_benchmark_suite import create_strategy_benchmark_suite_artifact
from halpha.storage import display_path, ensure_directory, resolve_runtime_path, write_json


STRATEGY_OPTIMIZATION_ARTIFACT = "strategy_optimization.json"
STRATEGY_OPTIMIZATION_MANIFEST_ARTIFACT = "manifest.json"
STRATEGY_OPTIMIZATION_BENCHMARK_ARTIFACT = "strategy_benchmark_suite.json"
OPTIMIZATION_SOURCE = "strategy_optimization"
DEFAULT_MAX_COMBINATIONS = 50


class StrategyOptimizationError(Exception):
    def __init__(self, message: str, *, exit_code: int = 3) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass(frozen=True)
class StrategyOptimizationResult:
    succeeded: bool
    exit_code: int
    status: str
    reason: str | None
    output_dir: Path
    artifact_path: Path
    benchmark_suite_path: Path
    manifest_path: Path


def run_strategy_optimization(
    config: dict[str, Any],
    *,
    config_path: Path,
    strategy_name: str,
    grid: dict[str, list[Any]] | None = None,
    max_combinations: int = DEFAULT_MAX_COMBINATIONS,
    output_dir: Path | None = None,
    now: datetime | None = None,
) -> StrategyOptimizationResult:
    clock_value = _utc_now(now)
    if not isinstance(max_combinations, int) or isinstance(max_combinations, bool) or max_combinations <= 0:
        raise StrategyOptimizationError("max_combinations must be a positive integer.", exit_code=2)

    strategy = _configured_strategy(config, strategy_name)
    definition = get_strategy_definition(strategy_name)
    if definition is None:
        raise StrategyOptimizationError(f"strategy is not supported: {strategy_name}", exit_code=2)
    market = _market_config(config)
    ohlcv = _ohlcv_config(market)
    _require_benchmark_suite_enabled(config)
    storage_dir = _storage_dir(ohlcv, config_path)
    base_output_dir = _base_output_dir(config, config_path=config_path, output_dir=output_dir)
    search_space = _search_space(strategy_name, explicit_grid=grid)
    combinations = _parameter_combinations(search_space["grid"])
    if len(combinations) > max_combinations:
        raise StrategyOptimizationError(
            (
                f"{strategy_name} optimization grid has {len(combinations)} combinations; "
                f"max_combinations is {max_combinations}."
            ),
            exit_code=2,
        )

    try:
        benchmark_suite = create_strategy_benchmark_suite_artifact(
            config,
            config_path=config_path,
            run_output_dir=base_output_dir,
            now=clock_value,
        )
    except Exception as exc:
        raise StrategyOptimizationError(str(exc), exit_code=getattr(exc, "exit_code", 3)) from exc

    target_dir = _unique_output_dir(base_output_dir, _optimization_id(clock_value, strategy_name))
    benchmark_suite_path = target_dir / STRATEGY_OPTIMIZATION_BENCHMARK_ARTIFACT
    write_json(benchmark_suite_path, benchmark_suite)

    base_params = _effective_base_params(strategy_name, strategy)
    candidates = [
        _candidate_record(
            index=index,
            base_strategy=strategy,
            base_params=base_params,
            candidate_params=params,
            benchmarks=_dict_list(benchmark_suite.get("benchmarks")),
            storage_dir=storage_dir,
            definition=definition,
        )
        for index, params in enumerate(combinations, start=1)
    ]
    selected_candidate = _selected_candidate(candidates)
    warnings = _artifact_warnings(candidates, selected_candidate=selected_candidate)
    errors = _artifact_errors(candidates)
    artifact = {
        "schema_version": 1,
        "artifact_type": "strategy_optimization",
        "created_at": _format_utc(clock_value),
        "optimization_id": _optimization_id(clock_value, strategy_name),
        "strategy_name": strategy_name,
        "instrument_identity": _instrument_identity(config, benchmark_suite),
        "inputs": {
            "candidate_source": "bounded_grid_search",
            "strategy_source": "configured_quant_strategy",
            "benchmark_suite_artifact": STRATEGY_OPTIMIZATION_BENCHMARK_ARTIFACT,
        },
        "base_params": base_params,
        "search_space": {
            **search_space,
            "combination_count": len(combinations),
            "max_combinations": max_combinations,
        },
        "constraints": {
            "max_combinations": max_combinations,
            "raw_ohlcv_history_embedded": False,
            "automatic_config_mutation": False,
        },
        "selection_policy": {
            "name": "max_mean_net_return_with_drawdown_tiebreak_research_only_v1",
            "metric": "mean_net_return_pct",
            "tie_breakers": ["worst_max_drawdown_pct", "mean_cost_drag_pct", "candidate_id"],
            "automatic_config_mutation": False,
            "research_only": True,
        },
        "coverage": _coverage(candidates, benchmark_suite),
        "candidates": candidates,
        "failed_candidates": _failed_candidates(candidates),
        "selected_candidate": selected_candidate,
        "walk_forward": {
            "enabled": False,
            "status": "skipped",
            "reason": "walk-forward optimization is not implemented in this artifact.",
            "windows": [],
        },
        "robustness": {
            "status": "not_evaluated",
            "warnings": [],
        },
        "source_artifacts": [STRATEGY_OPTIMIZATION_BENCHMARK_ARTIFACT],
        "warnings": warnings,
        "errors": errors,
    }
    artifact_path = target_dir / STRATEGY_OPTIMIZATION_ARTIFACT
    write_json(artifact_path, artifact)

    manifest_path = target_dir / STRATEGY_OPTIMIZATION_MANIFEST_ARTIFACT
    manifest = _manifest(
        config_path=config_path,
        created_at=_format_utc(clock_value),
        artifact=artifact,
        output_dir=target_dir,
        artifact_path=artifact_path,
        benchmark_suite_path=benchmark_suite_path,
        manifest_path=manifest_path,
    )
    write_json(manifest_path, manifest)
    return StrategyOptimizationResult(
        succeeded=True,
        exit_code=0,
        status="succeeded",
        reason=None,
        output_dir=target_dir,
        artifact_path=artifact_path,
        benchmark_suite_path=benchmark_suite_path,
        manifest_path=manifest_path,
    )


def parse_optimization_grid_args(strategy_name: str, raw_grid: list[str]) -> dict[str, list[Any]] | None:
    if not raw_grid:
        return None
    spec = get_supported_strategy_spec(strategy_name)
    if spec is None:
        raise StrategyOptimizationError(f"strategy is not supported: {strategy_name}", exit_code=2)
    parsed: dict[str, list[Any]] = {}
    for item in raw_grid:
        if "=" not in item:
            raise StrategyOptimizationError("optimization grid items must use KEY=VALUE[,VALUE].", exit_code=2)
        raw_key, raw_values = item.split("=", 1)
        key = raw_key.strip()
        if not key:
            raise StrategyOptimizationError("optimization grid parameter name must not be empty.", exit_code=2)
        if key in parsed:
            raise StrategyOptimizationError(f"optimization grid parameter is repeated: {key}", exit_code=2)
        schema = spec.parameter_schema.get(key)
        if not isinstance(schema, dict):
            supported = ", ".join(sorted(spec.parameter_schema))
            raise StrategyOptimizationError(
                f"{key} is not supported for {strategy_name}. Supported params: {supported}.",
                exit_code=2,
            )
        values = [value.strip() for value in raw_values.split(",") if value.strip()]
        if not values:
            raise StrategyOptimizationError(f"optimization grid {key} must include at least one value.", exit_code=2)
        parsed[key] = [_parse_grid_value(value, schema=schema, path=f"{key}[{index}]") for index, value in enumerate(values)]
    return parsed


def _search_space(strategy_name: str, *, explicit_grid: dict[str, list[Any]] | None) -> dict[str, Any]:
    spec = get_supported_strategy_spec(strategy_name)
    if spec is None:
        raise StrategyOptimizationError(f"strategy is not supported: {strategy_name}", exit_code=2)
    if explicit_grid:
        grid = {str(key): list(values) for key, values in explicit_grid.items()}
        source = "cli_grid_override"
    else:
        grid = {
            name: list(space.get("values", []))
            for name, space in spec.optimization_space.items()
            if isinstance(space, dict) and isinstance(space.get("values"), list)
        }
        source = "strategy_spec_optimization_space"
    if not grid:
        raise StrategyOptimizationError(f"no optimization grid is available for {strategy_name}.", exit_code=2)
    for name, values in grid.items():
        if name not in spec.parameter_schema:
            supported = ", ".join(sorted(spec.parameter_schema))
            raise StrategyOptimizationError(
                f"{name} is not supported for {strategy_name}. Supported params: {supported}.",
                exit_code=2,
            )
        if not values:
            raise StrategyOptimizationError(f"optimization grid {name} must include at least one value.", exit_code=2)
    return {
        "source": source,
        "strategy_spec_version": spec.version,
        "grid": {name: grid[name] for name in sorted(grid)},
    }


def _parameter_combinations(grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    names = sorted(grid)
    values = [grid[name] for name in names]
    return [dict(zip(names, item, strict=True)) for item in product(*values)]


def _candidate_record(
    *,
    index: int,
    base_strategy: dict[str, Any],
    base_params: dict[str, Any],
    candidate_params: dict[str, Any],
    benchmarks: list[dict[str, Any]],
    storage_dir: Path,
    definition: Any,
) -> dict[str, Any]:
    params = {**base_params, **candidate_params}
    strategy = {
        **base_strategy,
        "params": params,
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
        for item in _warning_items(evaluation.get("warnings"))
    )
    errors = [
        item
        for evaluation in evaluations
        for item in _error_items(evaluation.get("errors"))
    ]
    return {
        "candidate_id": f"candidate:{index:04d}",
        "params": params,
        "changed_params": candidate_params,
        "status": _candidate_status(evaluations),
        "metrics": _candidate_metrics(evaluations),
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
            "warnings": [
                _warning(
                    "benchmark_not_succeeded",
                    (
                        f"Benchmark {benchmark.get('benchmark_id')} status is "
                        f"{benchmark.get('status')}; optimization candidate was not evaluated."
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
    except (OHLCVQueryError, KeyError, TypeError, ValueError) as exc:
        return _failed_record(identity, type(exc).__name__, str(exc))
    return {
        **identity,
        "status": str(evaluation.get("status") or "failed"),
        "benchmark_status": benchmark.get("status"),
        "metrics": _metrics(evaluation),
        "warnings": _warning_items(evaluation.get("warnings")),
        "errors": _error_items(evaluation.get("errors")),
    }


def _benchmark_rows(benchmark: dict[str, Any], *, storage_dir: Path) -> list[dict[str, Any]]:
    query = query_ohlcv_records(
        storage_dir,
        source=str(benchmark["source"]),
        symbol=str(benchmark["symbol"]),
        timeframe=str(benchmark["timeframe"]),
        start=str(benchmark["input_window_start"]),
        end=str(benchmark["input_window_end"]),
        end_inclusive=True,
    )
    columns = [str(column) for column in benchmark.get("included_columns", [])] or [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]
    return [{column: record[column] for column in columns} for record in query["records"]]


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
        "evaluation_id": f"strategy_optimization:{name}:{benchmark_id}",
        "strategy_name": name,
        "benchmark_id": benchmark_id,
        "source": benchmark.get("source"),
        "symbol": benchmark.get("symbol"),
        "timeframe": benchmark.get("timeframe"),
        "window_identity": benchmark.get("window_identity"),
        "input_window_start": benchmark.get("input_window_start"),
        "input_window_end": benchmark.get("input_window_end"),
    }


def _metrics(evaluation: dict[str, Any]) -> dict[str, Any]:
    strategy_metrics = evaluation.get("strategy_metrics") if isinstance(evaluation.get("strategy_metrics"), dict) else {}
    relative_metrics = evaluation.get("relative_metrics") if isinstance(evaluation.get("relative_metrics"), dict) else {}
    trade_summary = evaluation.get("trade_summary") if isinstance(evaluation.get("trade_summary"), dict) else {}
    return {
        "net_return_pct": strategy_metrics.get("net_return_pct"),
        "gross_return_pct": strategy_metrics.get("gross_return_pct"),
        "max_drawdown_pct": strategy_metrics.get("max_drawdown_pct"),
        "cost_drag_pct": strategy_metrics.get("cost_drag_pct"),
        "volatility_pct": strategy_metrics.get("volatility_pct"),
        "sharpe": strategy_metrics.get("sharpe"),
        "excess_return_vs_buy_and_hold_pct": relative_metrics.get("excess_return_vs_buy_and_hold_pct"),
        "turnover": trade_summary.get("turnover"),
        "trade_count": trade_summary.get("trade_count"),
        "exposure_pct": trade_summary.get("exposure_pct"),
    }


def _candidate_metrics(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    succeeded = [item for item in evaluations if item.get("status") == "succeeded"]
    net_returns = _metric_values(succeeded, "net_return_pct")
    drawdowns = _metric_values(succeeded, "max_drawdown_pct")
    cost_drags = _metric_values(succeeded, "cost_drag_pct")
    excess_returns = _metric_values(succeeded, "excess_return_vs_buy_and_hold_pct")
    trade_counts = _metric_values(succeeded, "trade_count")
    return {
        "evaluation_count": len(evaluations),
        "succeeded": len(succeeded),
        "failed": sum(1 for item in evaluations if item.get("status") == "failed"),
        "insufficient_data": sum(1 for item in evaluations if item.get("status") == "insufficient_data"),
        "mean_net_return_pct": _rounded_mean(net_returns),
        "worst_max_drawdown_pct": min(drawdowns) if drawdowns else None,
        "mean_cost_drag_pct": _rounded_mean(cost_drags),
        "mean_excess_return_vs_buy_and_hold_pct": _rounded_mean(excess_returns),
        "total_trade_count": int(sum(trade_counts)) if trade_counts else 0,
    }


def _selected_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    eligible = [
        item
        for item in candidates
        if item.get("status") == "succeeded"
        and isinstance(item.get("metrics"), dict)
        and isinstance(item["metrics"].get("mean_net_return_pct"), (int, float))
    ]
    if not eligible:
        return None
    ordered = sorted(
        eligible,
        key=lambda item: (
            -float(item["metrics"]["mean_net_return_pct"]),
            -float(item["metrics"].get("worst_max_drawdown_pct") or -1_000_000.0),
            float(item["metrics"].get("mean_cost_drag_pct") or 1_000_000.0),
            str(item.get("candidate_id")),
        ),
    )
    selected = ordered[0]
    return {
        "candidate_id": selected.get("candidate_id"),
        "params": selected.get("params"),
        "changed_params": selected.get("changed_params"),
        "status": selected.get("status"),
        "metrics": selected.get("metrics"),
        "selection_reason": "highest_mean_net_return_with_drawdown_and_cost_tiebreak",
        "automatic_config_mutation": False,
    }


def _coverage(candidates: list[dict[str, Any]], benchmark_suite: dict[str, Any]) -> dict[str, Any]:
    evaluations = [
        evaluation
        for candidate in candidates
        for evaluation in _dict_list(candidate.get("evaluations"))
    ]
    benchmark_coverage = benchmark_suite.get("coverage") if isinstance(benchmark_suite.get("coverage"), dict) else {}
    return {
        "candidate_count": len(candidates),
        "succeeded": sum(1 for item in candidates if item.get("status") == "succeeded"),
        "failed": sum(1 for item in candidates if item.get("status") == "failed"),
        "insufficient_data": sum(1 for item in candidates if item.get("status") == "insufficient_data"),
        "skipped": sum(1 for item in candidates if item.get("status") == "skipped"),
        "evaluations": len(evaluations),
        "evaluations_succeeded": sum(1 for item in evaluations if item.get("status") == "succeeded"),
        "evaluations_failed": sum(1 for item in evaluations if item.get("status") == "failed"),
        "evaluations_insufficient_data": sum(1 for item in evaluations if item.get("status") == "insufficient_data"),
        "benchmark_records": int(benchmark_coverage.get("benchmark_records") or 0),
        "benchmark_succeeded": int(benchmark_coverage.get("succeeded") or 0),
        "benchmark_insufficient_data": int(benchmark_coverage.get("insufficient_data") or 0),
    }


def _manifest(
    *,
    config_path: Path,
    created_at: str,
    artifact: dict[str, Any],
    output_dir: Path,
    artifact_path: Path,
    benchmark_suite_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "strategy_optimization_manifest",
        "created_at": created_at,
        "status": "succeeded",
        "config_path": display_path(config_path, base=config_path.parent),
        "inputs": {
            "strategy_name": artifact.get("strategy_name"),
            "candidate_count": artifact.get("coverage", {}).get("candidate_count"),
            "output_dir": display_path(output_dir, base=manifest_path.parent),
        },
        "artifacts": {
            "strategy_optimization": display_path(artifact_path, base=manifest_path.parent),
            "strategy_benchmark_suite": display_path(benchmark_suite_path, base=manifest_path.parent),
            "manifest": display_path(manifest_path, base=manifest_path.parent),
        },
        "counts": artifact.get("coverage", {}),
        "selected_candidate": artifact.get("selected_candidate"),
        "failures": _failure_summaries(artifact),
        "warnings": artifact.get("warnings", []),
        "errors": artifact.get("errors", []),
    }


def _configured_strategy(config: dict[str, Any], strategy_name: str) -> dict[str, Any]:
    quant = config.get("quant") if isinstance(config.get("quant"), dict) else {}
    if quant.get("enabled") is not True:
        raise StrategyOptimizationError("quant.enabled must be true for strategy optimization.", exit_code=2)
    strategies = quant.get("strategies")
    if not isinstance(strategies, list):
        raise StrategyOptimizationError("quant.strategies must be configured for strategy optimization.", exit_code=2)
    matches = [
        strategy
        for strategy in strategies
        if isinstance(strategy, dict)
        and strategy.get("name") == strategy_name
        and strategy.get("enabled", True) is not False
    ]
    if not matches:
        raise StrategyOptimizationError(
            f"strategy is not configured and enabled: {strategy_name}",
            exit_code=2,
        )
    return matches[0]


def _effective_base_params(strategy_name: str, strategy: dict[str, Any]) -> dict[str, Any]:
    spec = get_supported_strategy_spec(strategy_name)
    defaults = spec.default_params if spec is not None else {}
    params = strategy.get("params") if isinstance(strategy.get("params"), dict) else {}
    return {**defaults, **params}


def _market_config(config: dict[str, Any]) -> dict[str, Any]:
    market = config.get("market")
    if not isinstance(market, dict) or market.get("enabled") is not True:
        raise StrategyOptimizationError("market.enabled must be true for strategy optimization.", exit_code=2)
    return market


def _ohlcv_config(market: dict[str, Any]) -> dict[str, Any]:
    ohlcv = market.get("ohlcv")
    if not isinstance(ohlcv, dict):
        raise StrategyOptimizationError("market.ohlcv must be configured for strategy optimization.", exit_code=2)
    return ohlcv


def _require_benchmark_suite_enabled(config: dict[str, Any]) -> None:
    quant = config.get("quant") if isinstance(config.get("quant"), dict) else {}
    suite_config = quant.get("benchmark_suite") if isinstance(quant.get("benchmark_suite"), dict) else {}
    if suite_config.get("enabled") is False:
        raise StrategyOptimizationError(
            "quant.benchmark_suite.enabled must not be false for strategy optimization.",
            exit_code=2,
        )


def _instrument_identity(config: dict[str, Any], benchmark_suite: dict[str, Any]) -> dict[str, Any]:
    market = config.get("market") if isinstance(config.get("market"), dict) else {}
    coverage = benchmark_suite.get("coverage") if isinstance(benchmark_suite.get("coverage"), dict) else {}
    return {
        "source": market.get("source"),
        "symbols": coverage.get("configured_symbols") or [],
        "timeframes": coverage.get("configured_timeframes") or [],
        "windows": coverage.get("configured_windows") or [],
    }


def _candidate_status(evaluations: list[dict[str, Any]]) -> str:
    if any(item.get("status") == "failed" for item in evaluations):
        return "failed"
    if any(item.get("status") == "succeeded" for item in evaluations):
        return "succeeded"
    if any(item.get("status") == "insufficient_data" for item in evaluations):
        return "insufficient_data"
    return "skipped"


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
        "warnings": [_warning("benchmark_row_mismatch", message)],
        "errors": [],
    }


def _failed_record(identity: dict[str, Any], error_type: str, message: str) -> dict[str, Any]:
    return {
        **identity,
        "status": "failed",
        "benchmark_status": "succeeded",
        "metrics": {},
        "warnings": [],
        "errors": [
            {
                "error_type": error_type,
                "message": message,
                "stage": OPTIMIZATION_SOURCE,
            }
        ],
    }


def _cost_assumptions(strategy: dict[str, Any]) -> dict[str, Any]:
    backtest = strategy.get("backtest") if isinstance(strategy.get("backtest"), dict) else {}
    return {
        "fees_bps": backtest.get("fees_bps", 0.0),
        "slippage_bps": backtest.get("slippage_bps", 0.0),
    }


def _metric_values(evaluations: list[dict[str, Any]], key: str) -> list[float]:
    values = []
    for evaluation in evaluations:
        metrics = evaluation.get("metrics") if isinstance(evaluation.get("metrics"), dict) else {}
        value = metrics.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        values.append(float(value))
    return values


def _rounded_mean(values: list[float]) -> float | None:
    return round(mean(values), 6) if values else None


def _failed_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failed = []
    for candidate in candidates:
        if candidate.get("status") not in {"failed", "insufficient_data", "skipped"}:
            continue
        failed.append(
            {
                "candidate_id": candidate.get("candidate_id"),
                "params": candidate.get("params"),
                "status": candidate.get("status"),
                "errors": _error_items(candidate.get("errors")),
                "warnings": _warning_items(candidate.get("warnings")),
            }
        )
    return failed


def _artifact_warnings(candidates: list[dict[str, Any]], *, selected_candidate: dict[str, Any] | None) -> list[dict[str, Any]]:
    warnings = _unique_items(
        item
        for candidate in candidates
        for item in _warning_items(candidate.get("warnings"))
    )
    if selected_candidate is None:
        warnings.append(
            _warning(
                "no_selected_candidate",
                "No optimization candidate had enough successful evaluation evidence for selection.",
            )
        )
    if any(candidate.get("status") == "failed" for candidate in candidates):
        warnings.append(
            _warning(
                "optimization_failed_candidates",
                "One or more optimization candidates failed and were preserved in the artifact.",
            )
        )
    return _unique_items(warnings)


def _artifact_errors(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item
        for candidate in candidates
        for item in _error_items(candidate.get("errors"))
    ]


def _failure_summaries(artifact: dict[str, Any]) -> list[dict[str, Any]]:
    failures = []
    for candidate in _dict_list(artifact.get("candidates")):
        if candidate.get("status") != "failed":
            continue
        errors = _error_items(candidate.get("errors"))
        first = errors[0] if errors else {}
        failures.append(
            {
                "candidate_id": candidate.get("candidate_id"),
                "error_type": first.get("error_type"),
                "message": first.get("message"),
            }
        )
    return failures


def _parse_grid_value(value: str, *, schema: dict[str, Any], path: str) -> Any:
    value_type = str(schema.get("type") or "")
    if value_type == "positive_integer":
        try:
            parsed = int(value)
        except ValueError as exc:
            raise StrategyOptimizationError(f"{path} must be a positive integer.", exit_code=2) from exc
        if parsed <= 0:
            raise StrategyOptimizationError(f"{path} must be a positive integer.", exit_code=2)
        return parsed
    if value_type in {"positive_number", "number"}:
        try:
            parsed = float(value)
        except ValueError as exc:
            raise StrategyOptimizationError(f"{path} must be a number.", exit_code=2) from exc
        if value_type == "positive_number" and parsed <= 0:
            raise StrategyOptimizationError(f"{path} must be a positive number.", exit_code=2)
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, (int, float)) and parsed < float(minimum):
            raise StrategyOptimizationError(f"{path} must be greater than or equal to {minimum}.", exit_code=2)
        if isinstance(maximum, (int, float)) and parsed > float(maximum):
            raise StrategyOptimizationError(f"{path} must be lower than or equal to {maximum}.", exit_code=2)
        return parsed
    if value_type == "boolean":
        lowered = value.lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
        raise StrategyOptimizationError(f"{path} must be a boolean.", exit_code=2)
    return value


def _warning(code: str, message: str) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "source": OPTIMIZATION_SOURCE,
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


def _storage_dir(ohlcv: dict[str, Any], config_path: Path) -> Path:
    storage_dir = Path(str(ohlcv["storage_dir"]))
    return resolve_runtime_path(storage_dir, config_path=config_path)


def _base_output_dir(config: dict[str, Any], *, config_path: Path, output_dir: Path | None) -> Path:
    if output_dir is not None:
        return resolve_runtime_path(output_dir, config_path=config_path)
    run = config.get("run") if isinstance(config.get("run"), dict) else {}
    root = Path(str(run.get("output_dir") or "runs"))
    return resolve_runtime_path(root, config_path=config_path) / "strategy_optimizations"


def _unique_output_dir(output_dir: Path, optimization_id: str) -> Path:
    ensure_directory(output_dir)
    candidate = output_dir / optimization_id
    if not candidate.exists():
        candidate.mkdir()
        return candidate
    for index in range(1, 100):
        candidate = output_dir / f"{optimization_id}-{index:02d}"
        if not candidate.exists():
            candidate.mkdir()
            return candidate
    raise StrategyOptimizationError(f"could not create a unique output directory for {optimization_id}.")


def _optimization_id(now: datetime, strategy_name: str) -> str:
    timestamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}_{_slug(strategy_name)}_optimization"


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "value"


def _utc_now(now: datetime | None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise StrategyOptimizationError("now must include a UTC offset.", exit_code=2)
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
