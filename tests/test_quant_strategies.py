from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from halpha.config import load_config
from halpha.ohlcv_store import OHLCVParquetStore
from halpha.pipeline import run_pipeline
from halpha.quant.registry import get_strategy_definition


def test_quant_strategy_registry_resolves_strategy_modules() -> None:
    definition = get_strategy_definition("tsmom_vol_scaled")
    breakout = get_strategy_definition("breakout_atr_trend")
    reversion = get_strategy_definition("bollinger_rsi_reversion")

    assert definition is not None
    assert definition.name == "tsmom_vol_scaled"
    assert definition.run.__module__ == "halpha.quant.strategies.tsmom_vol_scaled"
    assert breakout is not None
    assert breakout.name == "breakout_atr_trend"
    assert breakout.run.__module__ == "halpha.quant.strategies.breakout_atr_trend"
    assert reversion is not None
    assert reversion.name == "bollinger_rsi_reversion"
    assert reversion.run.__module__ == "halpha.quant.strategies.bollinger_rsi_reversion"
    assert get_strategy_definition("missing") is None


def test_quant_strategy_runner_writes_tsmom_strategy_artifacts(tmp_path: Path) -> None:
    config_path = _write_strategy_config(tmp_path, lookback=5)
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
            _record(open_time="2026-06-02T00:00:00Z", close=102, volume=11),
            _record(open_time="2026-06-03T00:00:00Z", close=104, volume=12),
            _record(open_time="2026-06-04T00:00:00Z", close=106, volume=13),
            _record(open_time="2026-06-05T00:00:00Z", close=109, volume=14),
        ]
    )

    result = _run_pipeline_with_strategies(config, config_path)

    strategy_runs = _strategy_runs(result)
    strategy_signals = _strategy_signals(result)
    market_signals = _market_signals(result)
    material = (result.run.analysis_dir / "market_signal_material.md").read_text(encoding="utf-8")
    manifest = _manifest(result)
    strategy_run = strategy_runs["runs"][0]
    strategy_signal = strategy_signals["signals"][0]

    assert result.succeeded is True
    assert strategy_runs["artifact_type"] == "quant_strategy_runs"
    assert strategy_runs["engine"]["name"] == "vectorbt"
    assert strategy_runs["engine"]["objects_exposed"] is False
    assert strategy_runs["source_artifacts"] == ["raw/market_data_views.json"]
    assert len(strategy_runs["runs"]) == 1
    assert strategy_run["strategy_run_id"] == (
        "quant_strategy_run:tsmom_vol_scaled:binance:BTCUSDT:1d:2026-06-05T00:00:00Z"
    )
    assert strategy_run["status"] == "succeeded"
    assert strategy_run["strategy_name"] == "tsmom_vol_scaled"
    assert strategy_run["strategy_version"] == 1
    assert strategy_run["params"] == {
        "return_window": 2,
        "volatility_window": 2,
        "target_volatility": 0.2,
    }
    assert strategy_run["input_view_id"] == "ohlcv_view:binance:BTCUSDT:1d:2026-06-05T00:00:00Z"
    assert strategy_run["input_window_start"] == "2026-06-01T00:00:00Z"
    assert strategy_run["input_window_end"] == "2026-06-05T00:00:00Z"
    assert strategy_run["latest_candle_time"] == "2026-06-05T00:00:00Z"
    assert strategy_run["data_quality"]["row_count"] == 5
    assert strategy_run["data_quality"]["minimum_required_rows"] == 3
    assert strategy_run["data_quality"]["sufficient_data"] is True
    assert strategy_run["indicators"]["calculation_backend"] == "vectorbt.IndicatorFactory"
    assert strategy_run["indicators"]["latest_close"] == 109.0
    assert strategy_run["indicators"]["baseline_close"] == 104.0
    assert strategy_run["indicators"]["return_window_pct"] == 4.807692
    assert strategy_run["indicators"]["row_count"] == 5
    assert strategy_run["signals"]["calculation_backend"] == "vectorbt.IndicatorFactory"
    assert strategy_run["signals"]["latest_regime"] in {
        "risk_limited_momentum",
        "risk_on_momentum",
    }
    assert strategy_run["signals"]["entry_count"] == 1
    assert strategy_run["signals"]["exit_count"] == 0
    assert strategy_run["assessment"]["direction"] == "bullish"
    assert strategy_run["assessment"]["strength"] == "medium"
    assert strategy_run["assessment"]["evidence"]
    assert strategy_run["assessment"]["uncertainty"]
    backtest = strategy_run["backtest_diagnostic"]
    assert backtest["enabled"] is True
    assert backtest["status"] == "succeeded"
    assert backtest["assumptions"] == {
        "initial_cash": 10000.0,
        "fees_bps": 10.0,
        "slippage_bps": 5.0,
        "mode": "long_flat",
        "direction": "long_only",
        "price_source": "close",
        "execution_timing": "research_close_to_close",
    }
    assert backtest["window"] == {
        "start": "2026-06-01T00:00:00Z",
        "end": "2026-06-05T00:00:00Z",
        "rows": 5,
    }
    assert backtest["metrics"]["calculation_backend"] == "vectorbt.Portfolio.from_signals"
    assert backtest["metrics"]["trade_count"] >= 1
    assert backtest["metrics"]["exposure_pct"] > 0
    assert backtest["metrics"]["final_equity"] > 0
    assert set(backtest["metrics"]) == {
        "calculation_backend",
        "total_return_pct",
        "max_drawdown_pct",
        "trade_count",
        "exposure_pct",
        "final_equity",
    }
    assert "Historical backtest diagnostic is research material" in backtest["warnings"][0]
    assert strategy_run["parameter_diagnostic"] == {"enabled": False, "status": "disabled"}
    assert strategy_run["error"] is None

    assert strategy_signals["source_artifacts"] == [
        "analysis/quant_strategy_runs.json",
        "raw/market_data_views.json",
    ]
    assert strategy_signal["strategy_name"] == "tsmom_vol_scaled"
    assert strategy_signal["direction"] == "bullish"
    assert strategy_signal["key_values"]["return_window_pct"] == 4.807692
    assert strategy_signal["key_values"]["entry_count"] == 1
    assert strategy_signal["key_values"]["backtest_diagnostic_status"] == "succeeded"
    assert strategy_signal["key_values"]["backtest_trade_count"] >= 1
    assert strategy_signal["key_values"]["backtest_final_equity"] > 0
    assert strategy_signal["source_artifacts"] == [
        "analysis/quant_strategy_runs.json",
        "raw/market_data_views.json",
    ]
    assert market_signals["source_artifacts"] == [
        "analysis/market_strategy_signals.json",
        "analysis/quant_strategy_runs.json",
    ]
    assert market_signals["signals"][0]["strategy_name"] == "tsmom_vol_scaled"
    assert "analysis/quant_strategy_runs.json" in material
    assert "backtest_diagnostics_are_historical_research_material: true" in material
    assert "backtest_diagnostic_policy: historical_research_material_only_not_forecast" in material

    assert manifest["artifacts"]["quant_strategy_runs"] == "analysis/quant_strategy_runs.json"
    assert manifest["artifacts"]["market_strategy_signals"] == "analysis/market_strategy_signals.json"
    assert manifest["counts"]["quant_strategy_runs"] == 1
    assert manifest["counts"]["quant_strategy_runs_succeeded"] == 1
    assert manifest["counts"]["quant_strategy_runs_failed"] == 0
    assert manifest["counts"]["quant_strategy_runs_insufficient_data"] == 0
    assert manifest["counts"]["market_strategy_signals"] == 1
    assert manifest["quant_strategies"]["enabled"] == ["tsmom_vol_scaled"]
    assert manifest["quant_strategies"]["backtest_diagnostics_enabled"] is True
    assert manifest["quant_strategies"]["parameter_diagnostics_enabled"] is False
    assert manifest["quant_strategies"]["failures"] == []
    assert manifest["quant_strategies"]["insufficient_data"] == []
    assert _stage(manifest, "evaluate_quant_strategies")["artifacts"] == [
        "analysis/quant_strategy_runs.json"
    ]
    assert _stage(manifest, "evaluate_market_strategy_signals")["artifacts"] == [
        "analysis/market_strategy_signals.json"
    ]


def test_quant_strategy_runner_records_insufficient_data_without_fabrication(tmp_path: Path) -> None:
    config_path = _write_strategy_config(tmp_path, lookback=2)
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records([_record(open_time="2026-06-05T00:00:00Z", close=109, volume=14)])

    result = _run_pipeline_with_strategies(config, config_path)

    strategy_run = _strategy_runs(result)["runs"][0]
    strategy_signal = _strategy_signals(result)["signals"][0]
    manifest = _manifest(result)

    assert result.succeeded is True
    assert strategy_run["status"] == "insufficient_data"
    assert strategy_run["data_quality"]["row_count"] == 1
    assert strategy_run["data_quality"]["minimum_required_rows"] == 3
    assert strategy_run["data_quality"]["sufficient_data"] is False
    assert strategy_run["indicators"] == {}
    assert strategy_run["signals"] == {}
    assert strategy_run["assessment"]["direction"] == "unknown"
    assert strategy_run["assessment"]["confidence"] == "low"
    assert strategy_run["warnings"][0]["code"] == "insufficient_ohlcv_rows"
    assert strategy_signal["direction"] == "unknown"
    assert strategy_signal["insufficient_data"] is True
    assert strategy_signal["key_values"]["backtest_diagnostic_status"] == "skipped"
    assert manifest["counts"]["quant_strategy_runs_insufficient_data"] == 1
    assert manifest["counts"]["market_strategy_signals_insufficient_data"] == 1
    assert manifest["quant_strategies"]["insufficient_data"][0]["row_count"] == 1


def test_quant_strategy_runner_records_disabled_backtest_diagnostic(tmp_path: Path) -> None:
    config_path = _write_strategy_config(tmp_path, lookback=5, backtest_enabled=False)
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
            _record(open_time="2026-06-02T00:00:00Z", close=102, volume=11),
            _record(open_time="2026-06-03T00:00:00Z", close=104, volume=12),
            _record(open_time="2026-06-04T00:00:00Z", close=106, volume=13),
            _record(open_time="2026-06-05T00:00:00Z", close=109, volume=14),
        ]
    )

    result = _run_pipeline_with_strategies(config, config_path)

    strategy_run = _strategy_runs(result)["runs"][0]
    strategy_signal = _strategy_signals(result)["signals"][0]
    manifest = _manifest(result)

    assert result.succeeded is True
    assert strategy_run["status"] == "succeeded"
    assert strategy_run["backtest_diagnostic"] == {"enabled": False, "status": "disabled"}
    assert strategy_signal["key_values"]["backtest_diagnostic_status"] == "disabled"
    assert "backtest_total_return_pct" not in strategy_signal["key_values"]
    assert manifest["quant_strategies"]["backtest_diagnostics_enabled"] is False


def test_quant_strategy_runner_records_enabled_parameter_diagnostic(tmp_path: Path) -> None:
    config_path = _write_strategy_config(
        tmp_path,
        lookback=5,
        parameter_diagnostics_enabled=True,
        parameter_grid_return_windows=[1, 2, 10],
    )
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
            _record(open_time="2026-06-02T00:00:00Z", close=102, volume=11),
            _record(open_time="2026-06-03T00:00:00Z", close=104, volume=12),
            _record(open_time="2026-06-04T00:00:00Z", close=110, volume=13),
            _record(open_time="2026-06-05T00:00:00Z", close=105, volume=14),
        ]
    )

    result = _run_pipeline_with_strategies(config, config_path)

    strategy_run = _strategy_runs(result)["runs"][0]
    strategy_signal = _strategy_signals(result)["signals"][0]
    market_signal = _market_signals(result)["signals"][0]
    material = (result.run.analysis_dir / "market_signal_material.md").read_text(encoding="utf-8")
    manifest = _manifest(result)
    diagnostic = strategy_run["parameter_diagnostic"]

    assert result.succeeded is True
    assert diagnostic["enabled"] is True
    assert diagnostic["status"] == "succeeded"
    assert diagnostic["assumptions"] == {
        "max_combinations": 3,
        "grid_source": "quant.parameter_diagnostics.grids.tsmom_vol_scaled",
        "metric_scope": "latest_state_and_bounded_backtest_summary",
        "selection_policy": "diagnostic_only_no_best_parameter_selection",
        "strategy_backtest_enabled": True,
    }
    assert diagnostic["grid"] == {
        "return_window": [1, 2, 10],
        "volatility_window": [2],
        "target_volatility": [0.2],
    }
    assert diagnostic["tested_combinations"] == 3
    assert diagnostic["valid_combinations"] == 2
    assert diagnostic["invalid_combinations"] == 1
    assert diagnostic["stability"] == "sensitive"
    assert diagnostic["summary_metrics"]["direction_counts"] == {"bearish": 1, "bullish": 1}
    assert diagnostic["combinations"][0]["params"]["return_window"] == 1
    assert diagnostic["combinations"][0]["status"] == "succeeded"
    assert diagnostic["combinations"][0]["metrics"]["direction"] == "bearish"
    assert diagnostic["combinations"][1]["params"]["return_window"] == 2
    assert diagnostic["combinations"][1]["status"] == "succeeded"
    assert diagnostic["combinations"][1]["metrics"]["direction"] == "bullish"
    assert diagnostic["combinations"][2]["params"]["return_window"] == 10
    assert diagnostic["combinations"][2]["status"] == "insufficient_data"
    assert diagnostic["combinations"][2]["error"]["error_type"] == "InsufficientData"
    assert diagnostic["warnings"][0]["code"] == "parameter_direction_sensitivity"
    assert any(item["code"] == "parameter_invalid_combinations" for item in diagnostic["warnings"])
    assert "do not choose trading parameters" in diagnostic["notes"][0]

    assert strategy_signal["key_values"]["parameter_diagnostic_status"] == "succeeded"
    assert strategy_signal["key_values"]["parameter_tested_combinations"] == 3
    assert strategy_signal["key_values"]["parameter_valid_combinations"] == 2
    assert strategy_signal["key_values"]["parameter_invalid_combinations"] == 1
    assert strategy_signal["key_values"]["parameter_stability"] == "sensitive"
    assert any("multiple assessment directions" in item for item in strategy_signal["uncertainty"])
    assert market_signal["key_values"]["parameter_stability"] == "sensitive"
    assert "parameter_diagnostic_policy: bounded_sensitivity_context_only_not_optimization" in material
    assert "bounded_parameter_diagnostic_summaries" in material
    assert manifest["quant_strategies"]["parameter_diagnostics_enabled"] is True


def test_quant_strategy_runner_records_failed_run_for_invalid_runtime_params(tmp_path: Path) -> None:
    config_path = _write_strategy_config(tmp_path, lookback=5)
    config = load_config(config_path)
    config["quant"]["strategies"][0]["params"]["return_window"] = 0
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
            _record(open_time="2026-06-02T00:00:00Z", close=102, volume=11),
            _record(open_time="2026-06-03T00:00:00Z", close=104, volume=12),
            _record(open_time="2026-06-04T00:00:00Z", close=106, volume=13),
            _record(open_time="2026-06-05T00:00:00Z", close=109, volume=14),
        ]
    )

    result = _run_pipeline_with_strategies(config, config_path)

    strategy_run = _strategy_runs(result)["runs"][0]
    strategy_signal = _strategy_signals(result)["signals"][0]
    manifest = _manifest(result)

    assert result.succeeded is True
    assert strategy_run["status"] == "failed"
    assert strategy_run["params"]["return_window"] == 0
    assert strategy_run["indicators"] == {}
    assert strategy_run["signals"] == {}
    assert strategy_run["error"] == {
        "error_type": "ValueError",
        "message": "return_window must be a positive integer.",
        "stage": "evaluate_quant_strategies",
    }
    assert strategy_signal["direction"] == "unknown"
    assert "return_window must be a positive integer." in strategy_signal["uncertainty"]
    assert manifest["counts"]["quant_strategy_runs"] == 1
    assert manifest["counts"]["quant_strategy_runs_failed"] == 1
    assert manifest["quant_strategies"]["failures"][0]["message"] == (
        "return_window must be a positive integer."
    )
    assert _stage(manifest, "evaluate_quant_strategies")["status"] == "succeeded"


def test_quant_strategy_runner_records_manifest_diagnostics_for_mixed_strategy_states(
    tmp_path: Path,
) -> None:
    config_path = _write_manifest_diagnostics_strategy_config(tmp_path)
    config = load_config(config_path)
    config["quant"]["strategies"][2]["params"]["rsi_window"] = 0
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
            _record(open_time="2026-06-02T00:00:00Z", close=102, volume=11),
            _record(open_time="2026-06-03T00:00:00Z", close=104, volume=12),
            _record(open_time="2026-06-04T00:00:00Z", close=106, volume=13),
            _record(open_time="2026-06-05T00:00:00Z", close=109, volume=14),
        ]
    )

    result = _run_pipeline_with_strategies(config, config_path)

    strategy_runs = _strategy_runs(result)
    manifest = _manifest(result)
    failure = manifest["quant_strategies"]["failures"][0]
    insufficient = manifest["quant_strategies"]["insufficient_data"][0]

    assert result.succeeded is True
    assert manifest["artifacts"]["quant_strategy_runs"] == "analysis/quant_strategy_runs.json"
    assert manifest["artifacts"]["market_strategy_signals"] == "analysis/market_strategy_signals.json"
    assert manifest["counts"]["quant_strategy_runs"] == 3
    assert manifest["counts"]["quant_strategy_runs_succeeded"] == 1
    assert manifest["counts"]["quant_strategy_runs_failed"] == 1
    assert manifest["counts"]["quant_strategy_runs_insufficient_data"] == 1
    assert manifest["counts"]["quant_strategy_runs_disabled"] == 0
    assert manifest["counts"]["quant_strategies_enabled"] == 3
    assert manifest["counts"]["quant_strategies_disabled"] == 1
    assert manifest["counts"]["market_strategy_signals"] == 3
    assert manifest["counts"]["market_strategy_signals_insufficient_data"] == 1
    assert manifest["quant_strategies"]["engine"]["name"] == "vectorbt"
    assert "version" in manifest["quant_strategies"]["engine"]
    assert manifest["quant_strategies"]["enabled"] == [
        "tsmom_vol_scaled",
        "breakout_atr_trend",
        "bollinger_rsi_reversion",
    ]
    assert manifest["quant_strategies"]["disabled"] == ["tsmom_vol_scaled"]
    assert failure == {
        "strategy_name": "bollinger_rsi_reversion",
        "source": "binance",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "input_view_id": "ohlcv_view:binance:BTCUSDT:1d:2026-06-05T00:00:00Z",
        "error_type": "ValueError",
        "message": "rsi_window must be a positive integer.",
    }
    assert insufficient == {
        "strategy_name": "breakout_atr_trend",
        "source": "binance",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "input_view_id": "ohlcv_view:binance:BTCUSDT:1d:2026-06-05T00:00:00Z",
        "row_count": 5,
        "minimum_required_rows": 11,
    }
    assert sorted(item["status"] for item in strategy_runs["runs"]) == [
        "failed",
        "insufficient_data",
        "succeeded",
    ]


def test_quant_strategy_runner_writes_breakout_atr_trend_artifacts(tmp_path: Path) -> None:
    config_path = _write_breakout_strategy_config(tmp_path, lookback=6)
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
            _record(open_time="2026-06-02T00:00:00Z", close=101, volume=11),
            _record(open_time="2026-06-03T00:00:00Z", close=102, volume=12),
            _record(open_time="2026-06-04T00:00:00Z", close=103, volume=13),
            _record(open_time="2026-06-05T00:00:00Z", close=104, volume=14),
            _record(open_time="2026-06-06T00:00:00Z", close=110, volume=20),
        ]
    )

    result = _run_pipeline_with_strategies(config, config_path)

    strategy_run = _strategy_runs(result)["runs"][0]
    strategy_signal = _strategy_signals(result)["signals"][0]
    market_signal = _market_signals(result)["signals"][0]
    manifest = _manifest(result)

    assert result.succeeded is True
    assert strategy_run["status"] == "succeeded"
    assert strategy_run["strategy_name"] == "breakout_atr_trend"
    assert strategy_run["params"] == {
        "breakout_window": 3,
        "exit_window": 2,
        "atr_window": 3,
    }
    assert strategy_run["indicators"]["calculation_backend"] == "vectorbt.IndicatorFactory"
    assert strategy_run["indicators"]["latest_close"] == 110.0
    assert strategy_run["indicators"]["breakout_window_high"] == 106.0
    assert strategy_run["indicators"]["breakout_window_low"] == 100.0
    assert strategy_run["indicators"]["exit_window_low"] == 101.0
    assert strategy_run["indicators"]["atr"] == 5.333333
    assert strategy_run["indicators"]["atr_pct"] == 4.848485
    assert strategy_run["indicators"]["range_width_pct"] == 5.454545
    assert strategy_run["indicators"]["breakout_distance_atr"] == 0.75
    assert strategy_run["signals"]["latest_regime"] == "confirmed_breakout"
    assert strategy_run["signals"]["entry_count"] == 1
    assert strategy_run["signals"]["exit_count"] == 0
    assert strategy_run["signals"]["latest_entry"] is True
    assert strategy_run["signals"]["latest_signal_active"] is True
    assert strategy_run["assessment"]["direction"] == "bullish"
    assert strategy_run["assessment"]["strength"] == "medium"
    assert strategy_run["assessment"]["evidence"]
    assert strategy_run["assessment"]["uncertainty"]
    assert strategy_run["backtest_diagnostic"]["status"] == "succeeded"
    assert strategy_run["error"] is None

    assert strategy_signal["strategy_name"] == "breakout_atr_trend"
    assert strategy_signal["direction"] == "bullish"
    assert strategy_signal["key_values"]["breakout_window_high"] == 106.0
    assert strategy_signal["key_values"]["atr_pct"] == 4.848485
    assert strategy_signal["key_values"]["breakout_distance_atr"] == 0.75
    assert strategy_signal["key_values"]["latest_regime"] == "confirmed_breakout"
    assert strategy_signal["key_values"]["entry_count"] == 1
    assert strategy_signal["key_values"]["backtest_diagnostic_status"] == "succeeded"
    assert market_signal["strategy_name"] == "breakout_atr_trend"
    assert manifest["counts"]["quant_strategy_runs_succeeded"] == 1
    assert manifest["quant_strategies"]["enabled"] == ["breakout_atr_trend"]


def test_quant_strategy_runner_records_breakout_non_breakout_state(tmp_path: Path) -> None:
    config_path = _write_breakout_strategy_config(tmp_path, lookback=6, backtest_enabled=False)
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
            _record(open_time="2026-06-02T00:00:00Z", close=101, volume=11),
            _record(open_time="2026-06-03T00:00:00Z", close=102, volume=12),
            _record(open_time="2026-06-04T00:00:00Z", close=103, volume=13),
            _record(open_time="2026-06-05T00:00:00Z", close=104, volume=14),
            _record(open_time="2026-06-06T00:00:00Z", close=105, volume=15),
        ]
    )

    result = _run_pipeline_with_strategies(config, config_path)

    strategy_run = _strategy_runs(result)["runs"][0]
    strategy_signal = _strategy_signals(result)["signals"][0]

    assert result.succeeded is True
    assert strategy_run["status"] == "succeeded"
    assert strategy_run["signals"]["latest_regime"] == "range_bound"
    assert strategy_run["signals"]["entry_count"] == 0
    assert strategy_run["signals"]["latest_signal_active"] is False
    assert strategy_run["assessment"]["direction"] == "neutral"
    assert strategy_run["assessment"]["strength"] == "low"
    assert strategy_run["backtest_diagnostic"] == {"enabled": False, "status": "disabled"}
    assert strategy_signal["direction"] == "neutral"
    assert strategy_signal["key_values"]["breakout_window_high"] == 106.0
    assert strategy_signal["key_values"]["latest_signal_active"] is False
    assert strategy_signal["key_values"]["backtest_diagnostic_status"] == "disabled"


def test_quant_strategy_runner_records_breakout_insufficient_data(tmp_path: Path) -> None:
    config_path = _write_breakout_strategy_config(tmp_path, lookback=2)
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-05T00:00:00Z", close=104, volume=14),
            _record(open_time="2026-06-06T00:00:00Z", close=110, volume=20),
        ]
    )

    result = _run_pipeline_with_strategies(config, config_path)

    strategy_run = _strategy_runs(result)["runs"][0]
    strategy_signal = _strategy_signals(result)["signals"][0]
    manifest = _manifest(result)

    assert result.succeeded is True
    assert strategy_run["status"] == "insufficient_data"
    assert strategy_run["data_quality"]["row_count"] == 2
    assert strategy_run["data_quality"]["minimum_required_rows"] == 4
    assert strategy_run["indicators"] == {}
    assert strategy_run["signals"] == {}
    assert strategy_run["warnings"][0]["code"] == "insufficient_ohlcv_rows"
    assert strategy_signal["direction"] == "unknown"
    assert strategy_signal["insufficient_data"] is True
    assert strategy_signal["key_values"]["backtest_diagnostic_status"] == "skipped"
    assert manifest["counts"]["quant_strategy_runs_insufficient_data"] == 1
    assert manifest["quant_strategies"]["insufficient_data"][0]["row_count"] == 2


def test_quant_strategy_runner_writes_bollinger_rsi_oversold_artifacts(tmp_path: Path) -> None:
    config_path = _write_reversion_strategy_config(tmp_path, lookback=6)
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
            _record(open_time="2026-06-02T00:00:00Z", close=102, volume=11),
            _record(open_time="2026-06-03T00:00:00Z", close=101, volume=12),
            _record(open_time="2026-06-04T00:00:00Z", close=100, volume=13),
            _record(open_time="2026-06-05T00:00:00Z", close=99, volume=14),
            _record(open_time="2026-06-06T00:00:00Z", close=90, volume=20),
        ]
    )

    result = _run_pipeline_with_strategies(config, config_path)

    strategy_run = _strategy_runs(result)["runs"][0]
    strategy_signal = _strategy_signals(result)["signals"][0]
    market_signal = _market_signals(result)["signals"][0]
    manifest = _manifest(result)

    assert result.succeeded is True
    assert strategy_run["status"] == "succeeded"
    assert strategy_run["strategy_name"] == "bollinger_rsi_reversion"
    assert strategy_run["params"] == {
        "bollinger_window": 3,
        "band_std": 1.0,
        "rsi_window": 3,
        "rsi_oversold": 35.0,
        "rsi_overbought": 65.0,
        "trend_window": 3,
        "trend_filter_pct": 50.0,
    }
    assert strategy_run["indicators"]["calculation_backend"] == "vectorbt.IndicatorFactory"
    assert strategy_run["indicators"]["latest_close"] == 90.0
    assert strategy_run["indicators"]["bollinger_lower"] > strategy_run["indicators"]["latest_close"]
    assert strategy_run["indicators"]["rsi"] == 0.0
    assert strategy_run["indicators"]["trend_window_pct"] == pytest.approx(-10.891089, abs=0.000001)
    assert strategy_run["signals"]["latest_regime"] == "oversold_reversion_watch"
    assert strategy_run["signals"]["entry_count"] == 1
    assert strategy_run["signals"]["latest_signal_active"] is True
    assert strategy_run["signals"]["latest_oversold"] is True
    assert strategy_run["signals"]["latest_overbought"] is False
    assert strategy_run["signals"]["trend_filter_active"] is False
    assert strategy_run["assessment"]["direction"] == "bullish"
    assert strategy_run["assessment"]["strength"] == "high"
    assert strategy_run["assessment"]["evidence"]
    assert strategy_run["assessment"]["uncertainty"]
    assert strategy_run["backtest_diagnostic"]["status"] == "succeeded"
    assert strategy_run["error"] is None

    assert strategy_signal["strategy_name"] == "bollinger_rsi_reversion"
    assert strategy_signal["direction"] == "bullish"
    assert strategy_signal["key_values"]["latest_regime"] == "oversold_reversion_watch"
    assert strategy_signal["key_values"]["bollinger_lower"] > strategy_signal["key_values"]["latest_close"]
    assert strategy_signal["key_values"]["rsi"] == 0.0
    assert strategy_signal["key_values"]["latest_oversold"] is True
    assert strategy_signal["key_values"]["trend_filter_active"] is False
    assert strategy_signal["key_values"]["backtest_diagnostic_status"] == "succeeded"
    assert market_signal["strategy_name"] == "bollinger_rsi_reversion"
    assert market_signal["key_values"]["latest_regime"] == "oversold_reversion_watch"
    assert manifest["counts"]["quant_strategy_runs_succeeded"] == 1
    assert manifest["quant_strategies"]["enabled"] == ["bollinger_rsi_reversion"]


def test_quant_strategy_runner_records_bollinger_rsi_overbought_state(tmp_path: Path) -> None:
    config_path = _write_reversion_strategy_config(tmp_path, lookback=6, backtest_enabled=False)
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
            _record(open_time="2026-06-02T00:00:00Z", close=98, volume=11),
            _record(open_time="2026-06-03T00:00:00Z", close=99, volume=12),
            _record(open_time="2026-06-04T00:00:00Z", close=100, volume=13),
            _record(open_time="2026-06-05T00:00:00Z", close=101, volume=14),
            _record(open_time="2026-06-06T00:00:00Z", close=110, volume=20),
        ]
    )

    result = _run_pipeline_with_strategies(config, config_path)

    strategy_run = _strategy_runs(result)["runs"][0]
    strategy_signal = _strategy_signals(result)["signals"][0]

    assert result.succeeded is True
    assert strategy_run["status"] == "succeeded"
    assert strategy_run["signals"]["latest_regime"] == "overbought_reversion_watch"
    assert strategy_run["signals"]["latest_signal_active"] is False
    assert strategy_run["signals"]["latest_oversold"] is False
    assert strategy_run["signals"]["latest_overbought"] is True
    assert strategy_run["assessment"]["direction"] == "bearish"
    assert strategy_run["assessment"]["strength"] == "high"
    assert strategy_run["backtest_diagnostic"] == {"enabled": False, "status": "disabled"}
    assert strategy_signal["direction"] == "bearish"
    assert strategy_signal["key_values"]["latest_regime"] == "overbought_reversion_watch"
    assert strategy_signal["key_values"]["bollinger_upper"] < strategy_signal["key_values"]["latest_close"]
    assert strategy_signal["key_values"]["rsi"] == 100.0
    assert strategy_signal["key_values"]["latest_overbought"] is True
    assert strategy_signal["key_values"]["backtest_diagnostic_status"] == "disabled"


def test_quant_strategy_runner_records_bollinger_rsi_neutral_state(tmp_path: Path) -> None:
    config_path = _write_reversion_strategy_config(tmp_path, lookback=6, backtest_enabled=False)
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
            _record(open_time="2026-06-02T00:00:00Z", close=101, volume=11),
            _record(open_time="2026-06-03T00:00:00Z", close=100, volume=12),
            _record(open_time="2026-06-04T00:00:00Z", close=101, volume=13),
            _record(open_time="2026-06-05T00:00:00Z", close=100, volume=14),
            _record(open_time="2026-06-06T00:00:00Z", close=101, volume=15),
        ]
    )

    result = _run_pipeline_with_strategies(config, config_path)

    strategy_run = _strategy_runs(result)["runs"][0]
    strategy_signal = _strategy_signals(result)["signals"][0]

    assert result.succeeded is True
    assert strategy_run["status"] == "succeeded"
    assert strategy_run["signals"]["latest_regime"] == "neutral_range"
    assert strategy_run["signals"]["entry_count"] == 0
    assert strategy_run["signals"]["exit_count"] == 0
    assert strategy_run["signals"]["latest_signal_active"] is False
    assert strategy_run["signals"]["latest_oversold"] is False
    assert strategy_run["signals"]["latest_overbought"] is False
    assert strategy_run["assessment"]["direction"] == "neutral"
    assert strategy_run["assessment"]["strength"] == "low"
    assert strategy_signal["direction"] == "neutral"
    assert strategy_signal["key_values"]["latest_regime"] == "neutral_range"
    assert strategy_signal["key_values"]["latest_signal_active"] is False


def test_quant_strategy_runner_records_bollinger_rsi_strong_trend_warning(tmp_path: Path) -> None:
    config_path = _write_reversion_strategy_config(
        tmp_path,
        lookback=6,
        backtest_enabled=False,
        trend_filter_pct=5.0,
    )
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
            _record(open_time="2026-06-02T00:00:00Z", close=98, volume=11),
            _record(open_time="2026-06-03T00:00:00Z", close=99, volume=12),
            _record(open_time="2026-06-04T00:00:00Z", close=100, volume=13),
            _record(open_time="2026-06-05T00:00:00Z", close=101, volume=14),
            _record(open_time="2026-06-06T00:00:00Z", close=110, volume=20),
        ]
    )

    result = _run_pipeline_with_strategies(config, config_path)

    strategy_run = _strategy_runs(result)["runs"][0]
    strategy_signal = _strategy_signals(result)["signals"][0]

    assert result.succeeded is True
    assert strategy_run["status"] == "succeeded"
    assert strategy_run["signals"]["latest_regime"] == "overbought_reversion_risk_strong_uptrend"
    assert strategy_run["signals"]["trend_filter_active"] is True
    assert strategy_run["signals"]["strong_trend_direction"] == "up"
    assert strategy_run["assessment"]["direction"] == "mixed"
    assert strategy_run["assessment"]["confidence"] == "low"
    assert strategy_run["warnings"][0]["code"] == "strong_uptrend_reversion_filter"
    assert strategy_signal["direction"] == "mixed"
    assert strategy_signal["key_values"]["trend_filter_active"] is True
    assert strategy_signal["key_values"]["strong_trend_direction"] == "up"
    assert any("strong uptrend" in item for item in strategy_signal["uncertainty"])


def test_quant_strategy_runner_records_bollinger_rsi_insufficient_data(tmp_path: Path) -> None:
    config_path = _write_reversion_strategy_config(tmp_path, lookback=2)
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-05T00:00:00Z", close=100, volume=14),
            _record(open_time="2026-06-06T00:00:00Z", close=90, volume=20),
        ]
    )

    result = _run_pipeline_with_strategies(config, config_path)

    strategy_run = _strategy_runs(result)["runs"][0]
    strategy_signal = _strategy_signals(result)["signals"][0]
    manifest = _manifest(result)

    assert result.succeeded is True
    assert strategy_run["status"] == "insufficient_data"
    assert strategy_run["data_quality"]["row_count"] == 2
    assert strategy_run["data_quality"]["minimum_required_rows"] == 4
    assert strategy_run["indicators"] == {}
    assert strategy_run["signals"] == {}
    assert strategy_run["warnings"][0]["code"] == "insufficient_ohlcv_rows"
    assert strategy_signal["direction"] == "unknown"
    assert strategy_signal["insufficient_data"] is True
    assert strategy_signal["key_values"]["backtest_diagnostic_status"] == "skipped"
    assert manifest["counts"]["quant_strategy_runs_insufficient_data"] == 1
    assert manifest["quant_strategies"]["insufficient_data"][0]["row_count"] == 2


def _run_pipeline_with_strategies(config: dict[str, Any], config_path: Path):
    return run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "sync_ohlcv": _noop_stage,
            "build_analysis_materials": _noop_stage,
            "build_research_context": _noop_stage,
            "build_codex_context": _noop_stage,
            "run_codex_report": _noop_stage,
        },
    )


def _write_strategy_config(
    tmp_path: Path,
    *,
    lookback: int,
    backtest_enabled: bool = True,
    parameter_diagnostics_enabled: bool = False,
    parameter_grid_return_windows: list[int] | None = None,
) -> Path:
    config_path = tmp_path / "config.yaml"
    return_windows = parameter_grid_return_windows or [2]
    grid_return_window_yaml = "\n".join(f"          - {item}" for item in return_windows)
    parameter_diagnostics_yaml = (
        f"""
  parameter_diagnostics:
    enabled: {"true" if parameter_diagnostics_enabled else "false"}
    max_combinations: {len(return_windows)}
    grids:
      tsmom_vol_scaled:
        return_window:
{grid_return_window_yaml}
        volatility_window:
          - 2
        target_volatility:
          - 0.2
"""
        if parameter_diagnostics_enabled
        else """
  parameter_diagnostics:
    enabled: false
    max_combinations: 50
"""
    ).rstrip()
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
        return_window: 2
        volatility_window: 2
        target_volatility: 0.2
      backtest:
        enabled: {"true" if backtest_enabled else "false"}
        initial_cash: 10000
        fees_bps: 10
        slippage_bps: 5
        mode: long_flat
{parameter_diagnostics_yaml}
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


def _write_manifest_diagnostics_strategy_config(tmp_path: Path) -> Path:
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
      1d: 5
quant:
  enabled: true
  engine: vectorbt
  strategies:
    - name: tsmom_vol_scaled
      enabled: true
      params:
        return_window: 2
        volatility_window: 2
        target_volatility: 0.2
    - name: breakout_atr_trend
      enabled: true
      params:
        breakout_window: 10
        exit_window: 2
        atr_window: 3
    - name: bollinger_rsi_reversion
      enabled: true
      params:
        bollinger_window: 3
        band_std: 1.0
        rsi_window: 3
        rsi_oversold: 35
        rsi_overbought: 65
        trend_window: 3
        trend_filter_pct: 50
    - name: tsmom_vol_scaled
      enabled: false
      params:
        return_window: 2
        volatility_window: 2
        target_volatility: 0.2
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


def _write_breakout_strategy_config(
    tmp_path: Path,
    *,
    lookback: int,
    backtest_enabled: bool = True,
) -> Path:
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
    - name: breakout_atr_trend
      enabled: true
      params:
        breakout_window: 3
        exit_window: 2
        atr_window: 3
      backtest:
        enabled: {"true" if backtest_enabled else "false"}
        initial_cash: 10000
        fees_bps: 10
        slippage_bps: 5
        mode: long_flat
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


def _write_reversion_strategy_config(
    tmp_path: Path,
    *,
    lookback: int,
    backtest_enabled: bool = True,
    trend_filter_pct: float = 50.0,
) -> Path:
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
    - name: bollinger_rsi_reversion
      enabled: true
      params:
        bollinger_window: 3
        band_std: 1.0
        rsi_window: 3
        rsi_oversold: 35
        rsi_overbought: 65
        trend_window: 3
        trend_filter_pct: {trend_filter_pct}
      backtest:
        enabled: {"true" if backtest_enabled else "false"}
        initial_cash: 10000
        fees_bps: 10
        slippage_bps: 5
        mode: long_flat
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


def _strategy_runs(result) -> dict[str, Any]:
    return json.loads((result.run.analysis_dir / "quant_strategy_runs.json").read_text(encoding="utf-8"))


def _strategy_signals(result) -> dict[str, Any]:
    return json.loads((result.run.analysis_dir / "market_strategy_signals.json").read_text(encoding="utf-8"))


def _market_signals(result) -> dict[str, Any]:
    return json.loads((result.run.analysis_dir / "market_signals.json").read_text(encoding="utf-8"))


def _manifest(result) -> dict[str, Any]:
    return json.loads(result.run.manifest_path.read_text(encoding="utf-8"))


def _stage(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    return next(stage for stage in manifest["stages"] if stage["name"] == name)


def _noop_stage(config, run) -> list[str]:
    return []


def _record(
    *,
    source: str = "binance",
    symbol: str = "BTCUSDT",
    timeframe: str = "1d",
    open_time: str,
    close: float,
    volume: float,
    open_: float | None = None,
    high: float | None = None,
    low: float | None = None,
) -> dict[str, object]:
    return {
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "open_time": open_time,
        "open": close - 1 if open_ is None else open_,
        "high": close + 2 if high is None else high,
        "low": close - 2 if low is None else low,
        "close": close,
        "volume": volume,
        "fetched_at": "2026-06-05T00:00:00Z",
    }
