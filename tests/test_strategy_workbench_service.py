from __future__ import annotations

from pathlib import Path

from halpha.strategy.workbench_service import run_strategy_backtest_action, run_strategy_optimization_action


def test_strategy_workbench_backtest_action_formats_shared_result(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "config.yaml"
    captured: dict[str, object] = {}

    class FakeBacktestResult:
        succeeded = True
        exit_code = 0
        status = "succeeded"
        reason = None
        artifact_path = tmp_path / "runs" / "strategy_backtests" / "run-1" / "strategy_backtest.json"
        manifest_path = tmp_path / "runs" / "strategy_backtests" / "run-1" / "manifest.json"

    def fake_backtest(*args, **kwargs):  # noqa: ANN002, ANN003
        captured.update(kwargs)
        return FakeBacktestResult()

    monkeypatch.setattr("halpha.strategy.workbench_service.run_standalone_strategy_backtest", fake_backtest)

    result = run_strategy_backtest_action(
        {},
        config_path=config_path,
        strategy_name="tsmom_vol_scaled",
        symbol="BTCUSDT",
        timeframe="1d",
        output_dir=tmp_path / "runs" / "strategy_backtests",
    )

    assert result.exit_code == 0
    assert result.status == "succeeded"
    assert result.result_refs == {
        "strategy_backtest": "runs/strategy_backtests/run-1/strategy_backtest.json",
        "manifest": "runs/strategy_backtests/run-1/manifest.json",
    }
    assert "Halpha backtest succeeded." in result.stdout
    assert "strategy_backtest: runs/strategy_backtests/run-1/strategy_backtest.json" in result.stdout
    assert captured["strategy_name"] == "tsmom_vol_scaled"
    assert captured["symbol"] == "BTCUSDT"
    assert captured["timeframe"] == "1d"


def test_strategy_workbench_optimization_action_formats_shared_result(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "config.yaml"
    captured: dict[str, object] = {}

    class FakeOptimizationResult:
        succeeded = True
        exit_code = 0
        status = "succeeded"
        reason = None
        output_dir = tmp_path / "runs" / "strategy_optimizations" / "run-1"
        artifact_path = output_dir / "strategy_optimization.json"
        benchmark_suite_path = output_dir / "strategy_benchmark_suite.json"
        manifest_path = output_dir / "manifest.json"

    def fake_optimization(*args, **kwargs):  # noqa: ANN002, ANN003
        captured.update(kwargs)
        return FakeOptimizationResult()

    monkeypatch.setattr("halpha.strategy.workbench_service.run_strategy_optimization", fake_optimization)

    result = run_strategy_optimization_action(
        {},
        config_path=config_path,
        strategy_name="tsmom_vol_scaled",
        grid={"return_window": [1, 2]},
        max_combinations=2,
        walk_forward_policy={"train_rows": 3, "validation_rows": 3, "step_rows": 3, "min_windows": 1},
        output_dir=tmp_path / "runs" / "strategy_optimizations",
    )

    assert result.exit_code == 0
    assert result.status == "succeeded"
    assert result.result_refs == {
        "strategy_optimization": "runs/strategy_optimizations/run-1/strategy_optimization.json",
        "strategy_benchmark_suite": "runs/strategy_optimizations/run-1/strategy_benchmark_suite.json",
        "manifest": "runs/strategy_optimizations/run-1/manifest.json",
    }
    assert "Halpha optimization succeeded." in result.stdout
    assert "strategy_optimization: runs/strategy_optimizations/run-1/strategy_optimization.json" in result.stdout
    assert captured["strategy_name"] == "tsmom_vol_scaled"
    assert captured["grid"] == {"return_window": [1, 2]}
    assert captured["max_combinations"] == 2
    assert captured["walk_forward_policy"] == {
        "train_rows": 3,
        "validation_rows": 3,
        "step_rows": 3,
        "min_windows": 1,
    }
