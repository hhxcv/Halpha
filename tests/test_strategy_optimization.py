from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from halpha.cli import main
from halpha.market.ohlcv_store import OHLCVParquetStore


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_cli_optimize_writes_bounded_strategy_optimization_artifact(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = _write_config(tmp_path, lookback=5)
    original_config = config_path.read_text(encoding="utf-8")
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=100),
            _record(open_time="2026-06-02T00:00:00Z", close=102),
            _record(open_time="2026-06-03T00:00:00Z", close=101),
            _record(open_time="2026-06-04T00:00:00Z", close=104),
            _record(open_time="2026-06-05T00:00:00Z", close=106),
        ]
    )
    output_dir = tmp_path / "optimizations"

    exit_code = main(
        [
            "optimize",
            "--config",
            str(config_path),
            "--strategy",
            "tsmom_vol_scaled",
            "--grid",
            "return_window=1,2",
            "--grid",
            "volatility_window=1",
            "--grid",
            "target_volatility=0.2",
            "--max-combinations",
            "4",
            "--output-dir",
            str(output_dir),
        ]
    )

    output = capsys.readouterr().out
    run_dir = next(output_dir.iterdir())
    artifact = json.loads((run_dir / "strategy_optimization.json").read_text(encoding="utf-8"))
    benchmark_suite = json.loads((run_dir / "strategy_benchmark_suite.json").read_text(encoding="utf-8"))
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert "Halpha optimization succeeded." in output
    assert "strategy_optimization:" in output
    assert "strategy_benchmark_suite:" in output
    assert "manifest:" in output
    assert config_path.read_text(encoding="utf-8") == original_config
    assert artifact["artifact_type"] == "strategy_optimization"
    assert artifact["strategy_name"] == "tsmom_vol_scaled"
    assert artifact["base_params"] == {
        "return_window": 1,
        "target_volatility": 0.2,
        "volatility_window": 1,
    }
    assert artifact["search_space"]["source"] == "cli_grid_override"
    assert artifact["search_space"]["combination_count"] == 2
    assert artifact["search_space"]["max_combinations"] == 4
    assert artifact["search_space"]["grid"] == {
        "return_window": [1, 2],
        "target_volatility": [0.2],
        "volatility_window": [1],
    }
    assert artifact["constraints"]["automatic_config_mutation"] is False
    assert artifact["selection_policy"]["automatic_config_mutation"] is False
    assert artifact["coverage"]["candidate_count"] == 2
    assert artifact["coverage"]["evaluations"] == 2
    assert artifact["coverage"]["succeeded"] == 2
    assert [candidate["candidate_id"] for candidate in artifact["candidates"]] == [
        "candidate:0001",
        "candidate:0002",
    ]
    assert artifact["candidates"][0]["changed_params"] == {
        "return_window": 1,
        "target_volatility": 0.2,
        "volatility_window": 1,
    }
    assert artifact["selected_candidate"]["candidate_id"] in {"candidate:0001", "candidate:0002"}
    assert artifact["selected_candidate"]["automatic_config_mutation"] is False
    assert artifact["walk_forward"]["enabled"] is True
    assert artifact["walk_forward"]["status"] == "insufficient_data"
    assert artifact["walk_forward"]["windows"] == []
    assert artifact["robustness"]["status"] == "insufficient_data"
    assert artifact["source_artifacts"] == ["strategy_benchmark_suite.json"]
    assert benchmark_suite["artifact_type"] == "strategy_benchmark_suite"
    assert manifest["artifact_type"] == "strategy_optimization_manifest"
    assert manifest["counts"] == artifact["coverage"]
    assert manifest["artifacts"] == {
        "manifest": "manifest.json",
        "strategy_benchmark_suite": "strategy_benchmark_suite.json",
        "strategy_optimization": "strategy_optimization.json",
    }


def test_cli_optimize_targets_symbol_timeframe_and_recommends_targeted_params(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = _write_config(tmp_path, lookback=5)
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        .replace("  symbols:\n    - BTCUSDT", "  symbols:\n    - BTCUSDT\n    - ETHUSDT")
        .replace("    timeframes:\n      - 1d", "    timeframes:\n      - 1d\n      - 1h")
        .replace("      1d: 5", "      1d: 5\n      1h: 5")
        .replace(
            "      params:\n        return_window: 1\n        volatility_window: 1\n        target_volatility: 0.2",
            (
                "      params:\n        return_window: 1\n        volatility_window: 1\n        target_volatility: 0.2\n"
                "      targeted_params:\n"
                "        - source: binance\n"
                "          symbol: BTCUSDT\n"
                "          timeframe: 1d\n"
                "          params:\n"
                "            return_window: 2"
            ),
        ),
        encoding="utf-8",
    )
    _write_records(tmp_path, [100, 102, 101, 104, 106])
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(symbol="ETHUSDT", timeframe="1h", open_time=f"2026-06-01T0{hour}:00:00Z", close=50 + hour)
            for hour in range(5)
        ]
    )
    output_dir = tmp_path / "optimizations"

    exit_code = main(
        [
            "optimize",
            "--config",
            str(config_path),
            "--strategy",
            "tsmom_vol_scaled",
            "--source",
            "binance",
            "--symbol",
            "BTCUSDT",
            "--timeframe",
            "1d",
            "--grid",
            "return_window=1,2",
            "--grid",
            "volatility_window=1",
            "--grid",
            "target_volatility=0.2",
            "--max-combinations",
            "4",
            "--output-dir",
            str(output_dir),
        ]
    )

    capsys.readouterr()
    run_dir = next(output_dir.iterdir())
    artifact = json.loads((run_dir / "strategy_optimization.json").read_text(encoding="utf-8"))
    benchmark_suite = json.loads((run_dir / "strategy_benchmark_suite.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert artifact["target"] == {"source": "binance", "symbol": "BTCUSDT", "timeframe": "1d"}
    assert artifact["base_params"] == {
        "return_window": 2,
        "target_volatility": 0.2,
        "volatility_window": 1,
    }
    assert artifact["parameter_profile"]["matched"] is True
    assert artifact["coverage"]["evaluations"] == 2
    assert benchmark_suite["coverage"]["benchmark_records"] == 1
    assert benchmark_suite["selection_policy"]["source"] == "targeted_symbols_timeframes_and_windows"
    assert benchmark_suite["selection_policy"]["target_filter"] == [
        {"source": "binance", "symbol": "BTCUSDT", "timeframe": "1d"}
    ]
    assert artifact["recommended_targeted_params"]["source"] == "binance"
    assert artifact["recommended_targeted_params"]["symbol"] == "BTCUSDT"
    assert artifact["recommended_targeted_params"]["timeframe"] == "1d"
    assert artifact["recommended_targeted_params"]["params"] == artifact["selected_candidate"]["params"]
    assert artifact["recommended_targeted_params"]["automatic_config_mutation"] is False


def test_cli_optimize_records_stable_walk_forward_evidence(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path, lookback=9)
    _write_records(
        tmp_path,
        [
            100,
            101,
            102,
            103,
            104,
            105,
            106,
            107,
            108,
        ],
    )
    output_dir = tmp_path / "optimizations"

    def evaluate_stable(*, strategy: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        net_return = 2.0 if strategy["params"]["return_window"] == 1 else 0.5
        return _evaluation_result(net_return_pct=net_return)

    monkeypatch.setattr(
        "halpha.strategy.strategy_optimization.evaluate_single_window_backtest",
        evaluate_stable,
    )

    exit_code = main(
        [
            "optimize",
            "--config",
            str(config_path),
            "--strategy",
            "tsmom_vol_scaled",
            "--grid",
            "return_window=1,2",
            "--grid",
            "volatility_window=1",
            "--grid",
            "target_volatility=0.2",
            "--walk-forward-train-rows",
            "3",
            "--walk-forward-validation-rows",
            "3",
            "--walk-forward-step-rows",
            "3",
            "--walk-forward-min-windows",
            "2",
            "--output-dir",
            str(output_dir),
        ]
    )

    capsys.readouterr()
    artifact = json.loads((next(output_dir.iterdir()) / "strategy_optimization.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert artifact["walk_forward"]["status"] == "succeeded"
    assert artifact["walk_forward"]["summary"]["window_count"] == 2
    assert artifact["walk_forward"]["summary"]["succeeded_windows"] == 2
    assert artifact["walk_forward"]["summary"]["selected_candidate_counts"] == {"candidate:0001": 2}
    assert artifact["walk_forward"]["summary"]["mean_validation_cost_drag_pct"] == 0.1
    assert artifact["robustness"]["status"] == "robust"
    assert artifact["walk_forward"]["windows"][0]["train_window"] == {
        "start": "2026-06-01T00:00:00Z",
        "end": "2026-06-03T00:00:00Z",
        "rows": 3,
    }
    assert artifact["walk_forward"]["windows"][0]["validation_window"] == {
        "start": "2026-06-04T00:00:00Z",
        "end": "2026-06-06T00:00:00Z",
        "rows": 3,
    }
    assert artifact["walk_forward"]["windows"][0]["selected_candidate"]["candidate_id"] == "candidate:0001"
    assert artifact["walk_forward"]["windows"][0]["validation"]["metrics"]["net_return_pct"] == 2.0


def test_cli_optimize_flags_unstable_walk_forward_parameters(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path, lookback=9)
    _write_records(tmp_path, [100, 101, 102, 103, 104, 105, 106, 107, 108])
    output_dir = tmp_path / "optimizations"

    def evaluate_unstable(
        *,
        strategy: dict[str, Any],
        ohlcv_rows: list[dict[str, Any]],
        **_kwargs: Any,
    ) -> dict[str, Any]:
        first_open = ohlcv_rows[0]["open_time"]
        return_window = strategy["params"]["return_window"]
        if first_open == "2026-06-01T00:00:00Z":
            net_return = 3.0 if return_window == 1 else 1.0
        elif first_open == "2026-06-04T00:00:00Z":
            net_return = 1.0 if return_window == 1 else 3.0
        else:
            net_return = 1.0
        return _evaluation_result(net_return_pct=net_return)

    monkeypatch.setattr(
        "halpha.strategy.strategy_optimization.evaluate_single_window_backtest",
        evaluate_unstable,
    )

    exit_code = main(
        [
            "optimize",
            "--config",
            str(config_path),
            "--strategy",
            "tsmom_vol_scaled",
            "--grid",
            "return_window=1,2",
            "--grid",
            "volatility_window=1",
            "--grid",
            "target_volatility=0.2",
            "--walk-forward-train-rows",
            "3",
            "--walk-forward-validation-rows",
            "3",
            "--walk-forward-step-rows",
            "3",
            "--walk-forward-min-windows",
            "2",
            "--output-dir",
            str(output_dir),
        ]
    )

    capsys.readouterr()
    artifact = json.loads((next(output_dir.iterdir()) / "strategy_optimization.json").read_text(encoding="utf-8"))
    warning_codes = {item["code"] for item in artifact["warnings"]}

    assert exit_code == 0
    assert artifact["walk_forward"]["status"] == "succeeded"
    assert artifact["walk_forward"]["summary"]["selected_candidate_counts"] == {
        "candidate:0001": 1,
        "candidate:0002": 1,
    }
    assert artifact["walk_forward"]["summary"]["selected_candidate_variants"] == 2
    assert artifact["robustness"]["status"] == "overfit_risk"
    assert "optimization_parameter_instability" in warning_codes
    assert "optimization_overfit_risk" in warning_codes


def test_cli_optimize_records_failed_walk_forward_windows(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path, lookback=9)
    _write_records(tmp_path, [100, 101, 102, 103, 104, 105, 106, 107, 108])
    output_dir = tmp_path / "optimizations"

    def evaluate_failed(**_kwargs: Any) -> dict[str, Any]:
        raise ValueError("forced walk-forward failure.")

    monkeypatch.setattr(
        "halpha.strategy.strategy_optimization.evaluate_single_window_backtest",
        evaluate_failed,
    )

    exit_code = main(
        [
            "optimize",
            "--config",
            str(config_path),
            "--strategy",
            "tsmom_vol_scaled",
            "--grid",
            "return_window=1,2",
            "--grid",
            "volatility_window=1",
            "--grid",
            "target_volatility=0.2",
            "--walk-forward-train-rows",
            "3",
            "--walk-forward-validation-rows",
            "3",
            "--walk-forward-step-rows",
            "3",
            "--walk-forward-min-windows",
            "2",
            "--output-dir",
            str(output_dir),
        ]
    )

    capsys.readouterr()
    artifact = json.loads((next(output_dir.iterdir()) / "strategy_optimization.json").read_text(encoding="utf-8"))
    warning_codes = {item["code"] for item in artifact["warnings"]}

    assert exit_code == 0
    assert artifact["walk_forward"]["status"] == "failed"
    assert artifact["walk_forward"]["summary"]["failed_windows"] == 2
    assert artifact["robustness"]["status"] == "failed"
    assert "optimization_walk_forward_failed" in warning_codes


def test_cli_optimize_rejects_grid_over_max_combinations(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = _write_config(tmp_path, lookback=3)
    output_dir = tmp_path / "optimizations"

    exit_code = main(
        [
            "optimize",
            "--config",
            str(config_path),
            "--strategy",
            "tsmom_vol_scaled",
            "--grid",
            "return_window=1,2",
            "--grid",
            "volatility_window=1",
            "--grid",
            "target_volatility=0.2",
            "--max-combinations",
            "1",
            "--output-dir",
            str(output_dir),
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 2
    assert "Halpha optimization failed." in output
    assert "stage: optimization" in output
    assert "optimization grid has 2 combinations; max_combinations is 1" in output
    assert not output_dir.exists()


def test_cli_optimize_uses_strategy_spec_space_when_grid_is_omitted(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = _write_config(tmp_path, lookback=3)

    exit_code = main(
        [
            "optimize",
            "--config",
            str(config_path),
            "--strategy",
            "tsmom_vol_scaled",
            "--max-combinations",
            "1",
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 2
    assert "Halpha optimization failed." in output
    assert "optimization grid has 27 combinations; max_combinations is 1" in output
    assert not (tmp_path / "runs" / "strategy_optimizations").exists()


def test_cli_optimize_records_failed_candidates_without_stopping(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path, lookback=4)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=100),
            _record(open_time="2026-06-02T00:00:00Z", close=102),
            _record(open_time="2026-06-03T00:00:00Z", close=101),
            _record(open_time="2026-06-04T00:00:00Z", close=104),
        ]
    )
    output_dir = tmp_path / "optimizations"

    def evaluate_or_fail(*, strategy: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        if strategy["params"]["return_window"] == 2:
            raise ValueError("forced optimization failure.")
        return {
            "status": "succeeded",
            "strategy_metrics": {
                "cost_drag_pct": 0.0,
                "gross_return_pct": 1.0,
                "max_drawdown_pct": -1.0,
                "net_return_pct": 1.0,
                "sharpe": 1.0,
                "volatility_pct": 1.0,
            },
            "relative_metrics": {"excess_return_vs_buy_and_hold_pct": 0.5},
            "trade_summary": {
                "exposure_pct": 50.0,
                "trade_count": 1,
                "turnover": 1.0,
            },
            "warnings": [],
            "errors": [],
        }

    monkeypatch.setattr(
        "halpha.strategy.strategy_optimization.evaluate_single_window_backtest",
        evaluate_or_fail,
    )

    exit_code = main(
        [
            "optimize",
            "--config",
            str(config_path),
            "--strategy",
            "tsmom_vol_scaled",
            "--grid",
            "return_window=1,2",
            "--grid",
            "volatility_window=1",
            "--grid",
            "target_volatility=0.2",
            "--output-dir",
            str(output_dir),
        ]
    )

    capsys.readouterr()
    artifact = json.loads((next(output_dir.iterdir()) / "strategy_optimization.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert artifact["coverage"]["candidate_count"] == 2
    assert artifact["coverage"]["succeeded"] == 1
    assert artifact["coverage"]["failed"] == 1
    assert artifact["selected_candidate"]["candidate_id"] == "candidate:0001"
    assert artifact["failed_candidates"] == [
        {
            "candidate_id": "candidate:0002",
            "errors": [
                {
                    "error_type": "ValueError",
                    "message": "forced optimization failure.",
                    "stage": "strategy_optimization",
                }
            ],
            "params": {
                "return_window": 2,
                "target_volatility": 0.2,
                "volatility_window": 1,
            },
            "status": "failed",
            "warnings": [],
        }
    ]
    assert "optimization_failed_candidates" in {item["code"] for item in artifact["warnings"]}


def _write_config(tmp_path: Path, *, lookback: int) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
run:
  output_dir: runs
  timezone: Asia/Shanghai
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
  parameter_diagnostics:
    enabled: false
    max_combinations: 50
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


def _write_records(tmp_path: Path, closes: list[float]) -> None:
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(
                open_time=f"2026-06-{index:02d}T00:00:00Z",
                close=close,
            )
            for index, close in enumerate(closes, start=1)
        ]
    )


def _evaluation_result(*, net_return_pct: float) -> dict[str, Any]:
    return {
        "status": "succeeded",
        "strategy_metrics": {
            "cost_drag_pct": 0.1,
            "gross_return_pct": net_return_pct + 0.1,
            "max_drawdown_pct": -1.0,
            "net_return_pct": net_return_pct,
            "sharpe": 1.0,
            "volatility_pct": 1.0,
        },
        "relative_metrics": {"excess_return_vs_buy_and_hold_pct": net_return_pct - 0.5},
        "trade_summary": {
            "exposure_pct": 50.0,
            "trade_count": 1,
            "turnover": 1.0,
        },
        "warnings": [],
        "errors": [],
    }


def _record(
    *,
    source: str = "binance",
    symbol: str = "BTCUSDT",
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
