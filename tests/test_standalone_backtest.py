from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from halpha.cli import main
from halpha.market.ohlcv_store import OHLCVParquetStore
from halpha.strategy.standalone_backtest import _visualization_record


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_cli_backtest_runs_one_strategy_from_local_ohlcv_history(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = _write_config(tmp_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=100),
            _record(open_time="2026-06-02T00:00:00Z", close=101),
            _record(open_time="2026-06-03T00:00:00Z", close=99),
            _record(open_time="2026-06-04T00:00:00Z", close=102),
        ]
    )
    output_dir = tmp_path / "backtests"

    exit_code = main(
        [
            "backtest",
            "--config",
            str(config_path),
            "--strategy",
            "tsmom_vol_scaled",
            "--symbol",
            "BTCUSDT",
            "--timeframe",
            "1d",
            "--output-dir",
            str(output_dir),
        ]
    )

    output = capsys.readouterr().out
    run_dirs = list(output_dir.iterdir())
    artifact = run_dirs[0] / "strategy_backtest.json"
    manifest_path = run_dirs[0] / "manifest.json"
    backtest = json.loads(artifact.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    history = json.loads(
        (tmp_path / "data" / "research" / "strategy_evaluations" / "strategy_evaluation_history.json").read_text(
            encoding="utf-8"
        )
    )
    history_record = history["records"][0]

    assert exit_code == 0
    assert "Halpha backtest succeeded." in output
    assert "strategy_backtest:" in output
    assert "manifest:" in output
    assert len(run_dirs) == 1
    assert backtest["status"] == "succeeded"
    assert backtest["strategy_name"] == "tsmom_vol_scaled"
    assert backtest["source"] == "binance"
    assert backtest["symbol"] == "BTCUSDT"
    assert backtest["timeframe"] == "1d"
    assert backtest["execution_model"]["lookahead_policy"] == "no_same_bar_execution"
    assert backtest["cost_assumptions"]["fees_bps"] == 10.0
    assert backtest["cost_assumptions"]["slippage_bps"] == 5.0
    assert backtest["equity_curve"]
    assert backtest["visualization"]["chart_type"] == "candlestick_backtest"
    assert backtest["visualization"]["status"] == "available"
    assert [bar["time"] for bar in backtest["visualization"]["bars"]] == [
        "2026-06-01T00:00:00Z",
        "2026-06-02T00:00:00Z",
        "2026-06-03T00:00:00Z",
        "2026-06-04T00:00:00Z",
    ]
    assert backtest["visualization"]["equity_curve"]
    assert all("time" in point and "net_equity" in point for point in backtest["visualization"]["equity_curve"])
    assert backtest["visualization"]["limits"]["max_bars"] == 120
    assert manifest["artifact_type"] == "standalone_strategy_backtest_manifest"
    assert manifest["status"] == "succeeded"
    assert manifest["evaluation_status"] == "succeeded"
    assert manifest["artifacts"] == {
        "manifest": "manifest.json",
        "strategy_backtest": "strategy_backtest.json",
    }
    assert manifest["shared_artifacts"] == {
        "strategy_evaluation_history": "data/research/strategy_evaluations/strategy_evaluation_history.json"
    }
    assert history["artifact_type"] == "strategy_evaluation_history"
    assert history_record["execution_source"]["type"] == "standalone_backtest"
    assert history_record["strategy_name"] == "tsmom_vol_scaled"
    assert history_record["symbol"] == "BTCUSDT"
    assert history_record["timeframe"] == "1d"
    assert history_record["metrics"]["strategy_metrics"]["net_return_pct"] == backtest["strategy_metrics"]["net_return_pct"]
    assert history_record["visualization"]["chart_type"] == "candlestick_backtest"


def test_cli_backtest_reports_missing_history(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = _write_config(tmp_path)

    exit_code = main(
        [
            "backtest",
            "--config",
            str(config_path),
            "--strategy",
            "tsmom_vol_scaled",
            "--symbol",
            "BTCUSDT",
            "--timeframe",
            "1d",
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 3
    assert "Halpha backtest failed." in output
    assert "stage: backtest" in output
    assert "no OHLCV history found" in output


def test_cli_backtest_uses_runtime_root_for_external_config_defaults(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    config_dir = tmp_path / "external-config"
    runtime_root.mkdir()
    config_dir.mkdir()
    monkeypatch.chdir(runtime_root)
    config_path = _write_config(config_dir)
    store = OHLCVParquetStore(runtime_root / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=100),
            _record(open_time="2026-06-02T00:00:00Z", close=101),
            _record(open_time="2026-06-03T00:00:00Z", close=99),
            _record(open_time="2026-06-04T00:00:00Z", close=102),
        ]
    )

    exit_code = main(
        [
            "backtest",
            "--config",
            str(config_path),
            "--strategy",
            "tsmom_vol_scaled",
            "--symbol",
            "BTCUSDT",
            "--timeframe",
            "1d",
        ]
    )

    output = capsys.readouterr().out
    output_dir = runtime_root / "runs" / "strategy_backtests"
    run_dirs = list(output_dir.iterdir())

    assert exit_code == 0
    assert "Halpha backtest succeeded." in output
    assert len(run_dirs) == 1
    assert (run_dirs[0] / "strategy_backtest.json").is_file()
    assert not (config_dir / "runs").exists()
    assert not (config_dir / "data").exists()


@pytest.mark.parametrize(
    ("extra_args", "expected_reason"),
    [
        (["--strategy", "breakout_atr_trend", "--symbol", "BTCUSDT", "--timeframe", "1d"], "strategy is not configured and enabled"),
        (["--strategy", "tsmom_vol_scaled", "--symbol", "ETHUSDT", "--timeframe", "1d"], "symbol is not configured"),
        (["--strategy", "tsmom_vol_scaled", "--symbol", "BTCUSDT", "--timeframe", "1h"], "timeframe is not configured"),
    ],
)
def test_cli_backtest_reports_unavailable_inputs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    extra_args: list[str],
    expected_reason: str,
) -> None:
    config_path = _write_config(tmp_path)

    exit_code = main(["backtest", "--config", str(config_path), *extra_args])

    output = capsys.readouterr().out

    assert exit_code == 2
    assert "Halpha backtest failed." in output
    assert "stage: backtest" in output
    assert expected_reason in output


def test_backtest_visualization_does_not_create_entry_marker_after_chart_truncation() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [
        _record(
            open_time=(start + timedelta(days=index)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            close=100 + index,
        )
        for index in range(130)
    ]
    evaluation = {
        "equity_curve": [
            {
                "open_time": row["open_time"],
                "net_equity": 1 + index * 0.001,
                "position": 1.0,
                "turnover": 0.0,
            }
            for index, row in enumerate(rows)
        ]
    }

    visualization = _visualization_record(
        rows=rows,
        evaluation=evaluation,
        strategy_name="tsmom_vol_scaled",
        source="binance",
        symbol="BTCUSDT",
        timeframe="1d",
    )

    assert len(visualization["bars"]) == 120
    assert visualization["omitted"]["bars"] == 10
    assert visualization["omitted"]["markers"] == 1
    assert visualization["markers"] == []


def test_backtest_visualization_prefers_window_with_completed_trade_markers() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [
        _record(
            open_time=(start + timedelta(days=index)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            close=100 + index,
        )
        for index in range(180)
    ]
    equity_curve = []
    for index, row in enumerate(rows):
        position = 1.0 if 24 <= index < 48 else 0.0
        equity_curve.append(
            {
                "open_time": row["open_time"],
                "net_equity": 1 + index * 0.001,
                "position": position,
                "turnover": 1.0 if index in {24, 48} else 0.0,
            }
        )

    visualization = _visualization_record(
        rows=rows,
        evaluation={"equity_curve": equity_curve},
        strategy_name="tsmom_vol_scaled",
        source="binance",
        symbol="BTCUSDT",
        timeframe="1d",
    )

    assert len(visualization["bars"]) == 120
    assert visualization["bars"][0]["time"] == rows[0]["open_time"]
    assert [marker["kind"] for marker in visualization["markers"]] == ["entry", "exit"]
    assert [marker["time"] for marker in visualization["markers"]] == [
        rows[24]["open_time"],
        rows[48]["open_time"],
    ]
    assert visualization["omitted"]["markers"] == 0


def test_backtest_visualization_counts_operation_markers_omitted_by_chart_window() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [
        _record(
            open_time=(start + timedelta(days=index)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            close=100 + index,
        )
        for index in range(180)
    ]
    equity_curve = []
    for index, row in enumerate(rows):
        position = 1.0 if 20 <= index < 32 or 168 <= index < 176 else 0.0
        equity_curve.append(
            {
                "open_time": row["open_time"],
                "net_equity": 1 + index * 0.001,
                "position": position,
                "turnover": 1.0 if index in {20, 32, 168, 176} else 0.0,
            }
        )

    visualization = _visualization_record(
        rows=rows,
        evaluation={"equity_curve": equity_curve},
        strategy_name="tsmom_vol_scaled",
        source="binance",
        symbol="BTCUSDT",
        timeframe="1d",
    )

    assert len(visualization["bars"]) == 120
    assert [marker["time"] for marker in visualization["markers"]] == [
        rows[168]["open_time"],
        rows[176]["open_time"],
    ]
    assert visualization["omitted"]["markers"] == 2


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
  ohlcv:
    storage_dir: data/market/ohlcv
    timeframes:
      - 1d
    lookback:
      1d: 4
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


def _record(*, open_time: str, close: float) -> dict[str, object]:
    return {
        "source": "binance",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "open_time": open_time,
        "open": close - 1,
        "high": close + 2,
        "low": close - 2,
        "close": close,
        "volume": 10,
        "fetched_at": "2026-06-05T00:00:00Z",
    }
