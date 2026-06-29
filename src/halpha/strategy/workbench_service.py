from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from halpha.storage import artifact_base, display_path
from halpha.strategy.standalone_backtest import StandaloneBacktestError, run_standalone_strategy_backtest
from halpha.strategy.strategy_experiment import StrategyExperimentError, run_strategy_experiment
from halpha.strategy.strategy_optimization import (
    DEFAULT_MAX_COMBINATIONS,
    StrategyOptimizationError,
    parse_optimization_grid_args,
    run_strategy_optimization,
)


@dataclass(frozen=True)
class StrategyWorkbenchActionResult:
    exit_code: int
    status: str
    lines: tuple[str, ...]
    result_refs: dict[str, str]
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0

    @property
    def stdout(self) -> str:
        return "\n".join(self.lines) + "\n"


def run_strategy_backtest_action(
    config: dict[str, Any],
    *,
    config_path: Path,
    strategy_name: str,
    symbol: str,
    timeframe: str,
    output_dir: Path | None = None,
) -> StrategyWorkbenchActionResult:
    try:
        result = run_standalone_strategy_backtest(
            config,
            config_path=config_path,
            strategy_name=strategy_name,
            symbol=symbol,
            timeframe=timeframe,
            output_dir=output_dir,
        )
    except StandaloneBacktestError as exc:
        return _failed_action(exc.exit_code, "Halpha backtest failed.", "backtest", str(exc))

    artifact = _display(result.artifact_path, config_path=config_path)
    manifest = _display(result.manifest_path, config_path=config_path)
    lines = [
        "Halpha backtest succeeded." if result.succeeded else "Halpha backtest failed.",
        f"status: {result.status}",
        *([f"reason: {result.reason}"] if result.reason else []),
        f"strategy_backtest: {artifact}",
        f"manifest: {manifest}",
    ]
    return StrategyWorkbenchActionResult(
        exit_code=result.exit_code,
        status=result.status,
        lines=tuple(lines),
        result_refs={"strategy_backtest": artifact, "manifest": manifest},
        errors=tuple([result.reason] if result.reason and not result.succeeded else []),
    )


def run_strategy_experiment_action(
    config: dict[str, Any],
    *,
    config_path: Path,
    strategy_names: list[str] | None = None,
    output_dir: Path | None = None,
) -> StrategyWorkbenchActionResult:
    try:
        result = run_strategy_experiment(
            config,
            config_path=config_path,
            strategy_names=strategy_names,
            output_dir=output_dir,
        )
    except StrategyExperimentError as exc:
        return _failed_action(exc.exit_code, "Halpha experiment failed.", "experiment", str(exc))

    artifact = _display(result.artifact_path, config_path=config_path)
    benchmark_suite = _display(result.benchmark_suite_path, config_path=config_path)
    gates = _display(result.gates_path, config_path=config_path)
    manifest = _display(result.manifest_path, config_path=config_path)
    return StrategyWorkbenchActionResult(
        exit_code=result.exit_code,
        status=result.status,
        lines=(
            "Halpha experiment succeeded.",
            f"status: {result.status}",
            f"strategy_experiment: {artifact}",
            f"strategy_benchmark_suite: {benchmark_suite}",
            f"strategy_effectiveness_gates: {gates}",
            f"manifest: {manifest}",
        ),
        result_refs={
            "strategy_experiment": artifact,
            "strategy_benchmark_suite": benchmark_suite,
            "strategy_effectiveness_gates": gates,
            "manifest": manifest,
        },
    )


def run_strategy_optimization_action(
    config: dict[str, Any],
    *,
    config_path: Path,
    strategy_name: str,
    grid: dict[str, list[Any]] | None = None,
    grid_args: list[str] | None = None,
    max_combinations: int = DEFAULT_MAX_COMBINATIONS,
    walk_forward_policy: dict[str, Any] | None = None,
    output_dir: Path | None = None,
) -> StrategyWorkbenchActionResult:
    try:
        parsed_grid = grid if grid is not None else parse_optimization_grid_args(strategy_name, grid_args or [])
        result = run_strategy_optimization(
            config,
            config_path=config_path,
            strategy_name=strategy_name,
            grid=parsed_grid,
            max_combinations=max_combinations,
            walk_forward_policy=walk_forward_policy,
            output_dir=output_dir,
        )
    except StrategyOptimizationError as exc:
        return _failed_action(exc.exit_code, "Halpha optimization failed.", "optimization", str(exc))

    artifact = _display(result.artifact_path, config_path=config_path)
    benchmark_suite = _display(result.benchmark_suite_path, config_path=config_path)
    manifest = _display(result.manifest_path, config_path=config_path)
    return StrategyWorkbenchActionResult(
        exit_code=result.exit_code,
        status=result.status,
        lines=(
            "Halpha optimization succeeded.",
            f"status: {result.status}",
            f"strategy_optimization: {artifact}",
            f"strategy_benchmark_suite: {benchmark_suite}",
            f"manifest: {manifest}",
        ),
        result_refs={
            "strategy_optimization": artifact,
            "strategy_benchmark_suite": benchmark_suite,
            "manifest": manifest,
        },
    )


def _failed_action(exit_code: int, title: str, stage: str, reason: str) -> StrategyWorkbenchActionResult:
    return StrategyWorkbenchActionResult(
        exit_code=exit_code,
        status="failed",
        lines=(title, f"stage: {stage}", f"reason: {reason}"),
        result_refs={},
        errors=(reason,),
    )


def _display(path: Path, *, config_path: Path) -> str:
    return display_path(path, base=artifact_base(config_path))
