from __future__ import annotations

import json
from pathlib import Path

import pytest

from halpha.cli import main
from halpha.market.ohlcv_store import OHLCVParquetStore


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_cli_experiment_runs_candidates_against_benchmark_suite(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = _write_config(tmp_path, symbols=["BTCUSDT", "ETHUSDT"], lookback=3)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(symbol="BTCUSDT", open_time="2026-06-01T00:00:00Z", close=100),
            _record(symbol="BTCUSDT", open_time="2026-06-02T00:00:00Z", close=102),
            _record(symbol="BTCUSDT", open_time="2026-06-03T00:00:00Z", close=104),
        ]
    )
    output_dir = tmp_path / "experiments"

    exit_code = main(["experiment", "--config", str(config_path), "--output-dir", str(output_dir)])

    output = capsys.readouterr().out
    run_dirs = list(output_dir.iterdir())
    experiment_path = run_dirs[0] / "strategy_experiment.json"
    benchmark_path = run_dirs[0] / "strategy_benchmark_suite.json"
    gates_path = run_dirs[0] / "strategy_effectiveness_gates.json"
    manifest_path = run_dirs[0] / "manifest.json"
    experiment = json.loads(experiment_path.read_text(encoding="utf-8"))
    benchmark_suite = json.loads(benchmark_path.read_text(encoding="utf-8"))
    gates = json.loads(gates_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    candidate = experiment["candidates"][0]
    succeeded = candidate["evaluations"][0]
    insufficient = candidate["evaluations"][1]

    assert exit_code == 0
    assert "Halpha experiment succeeded." in output
    assert "strategy_experiment:" in output
    assert "strategy_benchmark_suite:" in output
    assert "strategy_effectiveness_gates:" in output
    assert "manifest:" in output
    assert len(run_dirs) == 1
    assert experiment_path.is_file()
    assert benchmark_path.is_file()
    assert gates_path.is_file()
    assert manifest_path.is_file()
    assert benchmark_suite["coverage"] == {
        "benchmark_records": 2,
        "configured_symbols": ["BTCUSDT", "ETHUSDT"],
        "configured_timeframes": ["1d"],
        "configured_windows": ["configured_lookback"],
        "failed": 0,
        "insufficient_data": 1,
        "missing_history": 1,
        "succeeded": 1,
        "total_window_rows": 3,
    }
    assert experiment["artifact_type"] == "strategy_experiment"
    assert experiment["source_artifacts"] == ["strategy_benchmark_suite.json"]
    assert experiment["coverage"] == {
        "strategy_candidates": 1,
        "benchmark_records": 2,
        "benchmark_succeeded": 1,
        "benchmark_insufficient_data": 1,
        "evaluations": 2,
        "evaluations_succeeded": 1,
        "evaluations_insufficient_data": 1,
        "evaluations_failed": 0,
        "evaluations_skipped": 0,
    }
    assert candidate["strategy_name"] == "tsmom_vol_scaled"
    assert candidate["status"] == "succeeded"
    assert candidate["summary"]["benchmark_records"] == 2
    assert candidate["summary"]["succeeded"] == 1
    assert candidate["summary"]["insufficient_data"] == 1
    assert candidate["summary"]["mean_net_return_pct"] is not None
    assert succeeded["status"] == "succeeded"
    assert succeeded["benchmark_status"] == "succeeded"
    assert succeeded["single_window"]["execution_model"]["lookahead_policy"] == "no_same_bar_execution"
    assert succeeded["walk_forward"]["status"] == "insufficient_data"
    assert succeeded["walk_forward"]["window_count"] == 0
    assert succeeded["metrics"]["strategy"]["final_equity"] > 0
    assert insufficient["status"] == "insufficient_data"
    assert insufficient["benchmark_status"] == "insufficient_data"
    assert insufficient["metrics"] == {}
    assert insufficient["single_window"] == {}
    assert insufficient["walk_forward"] == {}
    assert insufficient["warnings"][0]["code"] == "benchmark_not_succeeded"
    assert gates["artifact_type"] == "strategy_effectiveness_gates"
    assert gates["source_artifacts"] == ["strategy_experiment.json"]
    assert gates["coverage"] == {
        "strategy_candidates": 1,
        "effective": 0,
        "watchlisted": 0,
        "rejected": 0,
        "insufficient_evidence": 1,
    }
    assert gates["records"][0]["strategy_name"] == "tsmom_vol_scaled"
    assert gates["records"][0]["status"] == "insufficient_evidence"
    assert manifest["artifact_type"] == "strategy_experiment_manifest"
    assert manifest["status"] == "succeeded"
    assert manifest["artifacts"] == {
        "manifest": "manifest.json",
        "strategy_benchmark_suite": "strategy_benchmark_suite.json",
        "strategy_effectiveness_gates": "strategy_effectiveness_gates.json",
        "strategy_experiment": "strategy_experiment.json",
    }
    assert manifest["counts"] == {
        **experiment["coverage"],
        "strategy_gate_candidates": 1,
        "strategy_gate_effective": 0,
        "strategy_gate_watchlisted": 0,
        "strategy_gate_rejected": 0,
        "strategy_gate_insufficient_evidence": 1,
    }
    assert manifest["failures"] == []


def test_cli_experiment_uses_only_targeted_strategy_candidates(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = _write_config(
        tmp_path,
        symbols=["BTCUSDT", "ETHUSDT"],
        lookback=3,
        strategy_extra_yaml="""
      targeted_params:
        - source: binance
          symbol: BTCUSDT
          timeframe: 1d
          params:
            return_window: 1
            volatility_window: 1
            target_volatility: 0.2
""",
        extra_strategy_yaml="""
    - name: sma_cross_trend
      enabled: true
      params:
        short_window: 1
        long_window: 2
      backtest:
        enabled: true
        initial_cash: 10000
        fees_bps: 10
        slippage_bps: 5
        mode: long_flat
""",
    )
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(symbol="BTCUSDT", open_time="2026-06-01T00:00:00Z", close=100),
            _record(symbol="BTCUSDT", open_time="2026-06-02T00:00:00Z", close=102),
            _record(symbol="BTCUSDT", open_time="2026-06-03T00:00:00Z", close=104),
        ]
    )
    output_dir = tmp_path / "experiments"

    exit_code = main(["experiment", "--config", str(config_path), "--output-dir", str(output_dir)])

    capsys.readouterr()
    run_dir = next(output_dir.iterdir())
    experiment = json.loads((run_dir / "strategy_experiment.json").read_text(encoding="utf-8"))
    benchmark_suite = json.loads((run_dir / "strategy_benchmark_suite.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert benchmark_suite["selection_policy"]["source"] == "configured_targeted_strategy_params"
    assert benchmark_suite["selection_policy"]["target_filter"] == [
        {"source": "binance", "symbol": "BTCUSDT", "timeframe": "1d"}
    ]
    assert experiment["inputs"]["selection_policy"] == {
        "source": "targeted_params",
        "unmatched_target_combinations_embedded": False,
    }
    assert [candidate["strategy_name"] for candidate in experiment["candidates"]] == [
        "tsmom_vol_scaled"
    ]
    assert experiment["candidates"][0]["evaluations"][0]["parameter_profile"]["source"] == (
        "targeted_params"
    )


def test_cli_experiment_records_failed_evaluation_without_stopping(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path, symbols=["BTCUSDT"], lookback=2)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(symbol="BTCUSDT", open_time="2026-06-01T00:00:00Z", close=100),
            _record(symbol="BTCUSDT", open_time="2026-06-02T00:00:00Z", close=102),
        ]
    )
    output_dir = tmp_path / "experiments"

    def fail_single_window(*args, **kwargs):
        raise ValueError("forced strategy evaluation failure.")

    monkeypatch.setattr(
        "halpha.strategy.strategy_experiment.evaluate_single_window_backtest",
        fail_single_window,
    )

    exit_code = main(["experiment", "--config", str(config_path), "--output-dir", str(output_dir)])

    capsys.readouterr()
    run_dir = next(output_dir.iterdir())
    experiment = json.loads((run_dir / "strategy_experiment.json").read_text(encoding="utf-8"))
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    evaluation = experiment["candidates"][0]["evaluations"][0]

    assert exit_code == 0
    assert experiment["coverage"]["evaluations_failed"] == 1
    assert experiment["candidates"][0]["status"] == "failed"
    assert evaluation["status"] == "failed"
    assert evaluation["single_window"] == {}
    assert evaluation["errors"][0] == {
        "error_type": "ValueError",
        "message": "forced strategy evaluation failure.",
        "stage": "strategy_experiment",
    }
    assert manifest["failures"] == [
        {
            "strategy_name": "tsmom_vol_scaled",
            "benchmark_id": evaluation["benchmark_id"],
            "error_type": "ValueError",
            "message": "forced strategy evaluation failure.",
        }
    ]


def test_cli_experiment_reports_missing_strategy_candidate(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = _write_config(tmp_path, symbols=["BTCUSDT"], lookback=2)

    exit_code = main(
        [
            "experiment",
            "--config",
            str(config_path),
            "--strategy",
            "breakout_atr_trend",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "Halpha experiment failed." in output
    assert "stage: experiment" in output
    assert "strategy is not configured and enabled: breakout_atr_trend" in output


def test_cli_experiment_requires_enabled_benchmark_suite(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = _write_config(
        tmp_path,
        symbols=["BTCUSDT"],
        lookback=2,
        benchmark_suite_yaml="""
  benchmark_suite:
    enabled: false
""",
    )

    exit_code = main(["experiment", "--config", str(config_path)])

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "Halpha experiment failed." in output
    assert "stage: experiment" in output
    assert "quant.benchmark_suite.enabled must not be false for strategy experiments." in output


def _write_config(
    tmp_path: Path,
    *,
    symbols: list[str],
    lookback: int,
    strategy_extra_yaml: str = "",
    extra_strategy_yaml: str = "",
    benchmark_suite_yaml: str = "",
) -> Path:
    config_path = tmp_path / "config.yaml"
    symbol_yaml = "\n".join(f"    - {symbol}" for symbol in symbols)
    config_path.write_text(
        f"""
run:
  output_dir: runs
  timezone: Asia/Shanghai
market:
  enabled: true
  source: binance
  symbols:
{symbol_yaml}
  ohlcv:
    storage_dir: data/market/ohlcv
    timeframes:
      - 1d
    lookback:
      1d: {lookback}
quant:
  enabled: true
  engine: vectorbt
  strategies:
    - name: tsmom_vol_scaled
      enabled: true
      params:
        return_window: 1
        volatility_window: 1
        target_volatility: 0.2
      backtest:
        enabled: true
        initial_cash: 10000
        fees_bps: 10
        slippage_bps: 5
        mode: long_flat
{strategy_extra_yaml.rstrip()}
{extra_strategy_yaml.rstrip()}
  parameter_diagnostics:
    enabled: false
    max_combinations: 50
{benchmark_suite_yaml.rstrip()}
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


def _record(
    *,
    source: str = "binance",
    symbol: str,
    timeframe: str = "1d",
    open_time: str,
    close: float,
) -> dict[str, object]:
    return {
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "open_time": open_time,
        "open": close - 1,
        "high": close + 2,
        "low": close - 2,
        "close": close,
        "volume": 10,
        "fetched_at": "2026-06-05T00:00:00Z",
    }
