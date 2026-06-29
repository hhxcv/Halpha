from __future__ import annotations

from pathlib import Path

from halpha.strategy.workbench_service import run_strategy_backtest_action


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
