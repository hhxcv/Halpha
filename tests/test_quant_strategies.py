from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from halpha.config import load_config
from halpha.market.ohlcv_store import OHLCVParquetStore
from halpha.pipeline import run_pipeline
from halpha.quant.parameter_diagnostics import _performance_stability, _signal_state_stability
from halpha.quant.registry import get_strategy_definition


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_quant_strategy_registry_resolves_strategy_modules() -> None:
    definition = get_strategy_definition("tsmom_vol_scaled")
    signed_tsmom = get_strategy_definition("signed_tsmom_trend")
    breakout = get_strategy_definition("breakout_atr_trend")
    sma_cross = get_strategy_definition("sma_cross_trend")
    sma_cross_long_short = get_strategy_definition("sma_cross_long_short")
    reversion = get_strategy_definition("bollinger_rsi_reversion")
    reversion_long_short = get_strategy_definition("bollinger_rsi_long_short")

    assert definition is not None
    assert definition.name == "tsmom_vol_scaled"
    assert definition.run.__module__ == "halpha.quant.strategies.tsmom_vol_scaled"
    assert definition.signal_records.__module__ == "halpha.quant.strategies.tsmom_vol_scaled"
    assert signed_tsmom is not None
    assert signed_tsmom.name == "signed_tsmom_trend"
    assert signed_tsmom.run.__module__ == "halpha.quant.strategies.signed_tsmom_trend"
    assert signed_tsmom.signal_records.__module__ == "halpha.quant.strategies.signed_tsmom_trend"
    assert breakout is not None
    assert breakout.name == "breakout_atr_trend"
    assert breakout.run.__module__ == "halpha.quant.strategies.breakout_atr_trend"
    assert breakout.signal_records.__module__ == "halpha.quant.strategies.breakout_atr_trend"
    assert sma_cross is not None
    assert sma_cross.name == "sma_cross_trend"
    assert sma_cross.run.__module__ == "halpha.quant.strategies.sma_cross_trend"
    assert sma_cross.signal_records.__module__ == "halpha.quant.strategies.sma_cross_trend"
    assert sma_cross_long_short is not None
    assert sma_cross_long_short.name == "sma_cross_long_short"
    assert sma_cross_long_short.run.__module__ == "halpha.quant.strategies.sma_cross_long_short"
    assert sma_cross_long_short.signal_records.__module__ == "halpha.quant.strategies.sma_cross_long_short"
    assert reversion is not None
    assert reversion.name == "bollinger_rsi_reversion"
    assert reversion.run.__module__ == "halpha.quant.strategies.bollinger_rsi_reversion"
    assert reversion.signal_records.__module__ == "halpha.quant.strategies.bollinger_rsi_reversion"
    assert reversion_long_short is not None
    assert reversion_long_short.name == "bollinger_rsi_long_short"
    assert reversion_long_short.run.__module__ == "halpha.quant.strategies.bollinger_rsi_long_short"
    assert reversion_long_short.signal_records.__module__ == "halpha.quant.strategies.bollinger_rsi_long_short"
    assert get_strategy_definition("missing") is None


def test_parameter_stability_separates_state_and_divergent_performance() -> None:
    valid_results = [
        {
            "status": "succeeded",
            "metrics": {
                "direction": "bullish",
                "latest_regime": "trend",
                "backtest_total_return_pct": 12.0,
                "backtest_max_drawdown_pct": -2.0,
                "backtest_trade_count": 4,
                "backtest_exposure_pct": 45.0,
            },
        },
        {
            "status": "succeeded",
            "metrics": {
                "direction": "bullish",
                "latest_regime": "trend",
                "backtest_total_return_pct": -4.0,
                "backtest_max_drawdown_pct": -18.0,
                "backtest_trade_count": 4,
                "backtest_exposure_pct": 46.0,
            },
        },
    ]

    signal_state = _signal_state_stability(valid_results, [])
    performance = _performance_stability(valid_results, [])

    assert signal_state["status"] == "stable"
    assert performance["status"] == "sensitive"
    assert performance["metric_ranges"]["backtest_total_return_pct"]["range"] == 16.0
    assert performance["metric_ranges"]["backtest_max_drawdown_pct"]["range"] == 16.0
    assert performance["reason_codes"] == [
        "metric_range_exceeds_threshold",
        "metric_range_exceeds_threshold",
    ]


def test_parameter_stability_separates_performance_and_divergent_state() -> None:
    valid_results = [
        {
            "status": "succeeded",
            "metrics": {
                "direction": "bullish",
                "latest_regime": "trend",
                "backtest_total_return_pct": 4.0,
                "backtest_max_drawdown_pct": -4.0,
                "backtest_trade_count": 4,
                "backtest_exposure_pct": 50.0,
            },
        },
        {
            "status": "succeeded",
            "metrics": {
                "direction": "bearish",
                "latest_regime": "range",
                "backtest_total_return_pct": 5.0,
                "backtest_max_drawdown_pct": -5.0,
                "backtest_trade_count": 5,
                "backtest_exposure_pct": 51.0,
            },
        },
    ]

    signal_state = _signal_state_stability(valid_results, [])
    performance = _performance_stability(valid_results, [])

    assert signal_state["status"] == "sensitive"
    assert signal_state["reason_codes"] == ["direction_sensitivity", "latest_regime_sensitivity"]
    assert performance["status"] == "stable"
    assert performance["reason_codes"] == ["metric_ranges_within_thresholds"]


def test_parameter_performance_stability_requires_complete_metrics() -> None:
    valid_results = [
        {
            "status": "succeeded",
            "metrics": {
                "direction": "bullish",
                "latest_regime": "trend",
                "backtest_total_return_pct": 4.0,
                "backtest_max_drawdown_pct": -4.0,
                "backtest_trade_count": 4,
                "backtest_exposure_pct": 50.0,
            },
        },
        {
            "status": "succeeded",
            "metrics": {
                "direction": "bullish",
                "latest_regime": "trend",
                "backtest_total_return_pct": 5.0,
                "backtest_max_drawdown_pct": -5.0,
                "backtest_trade_count": 5,
            },
        },
    ]

    performance = _performance_stability(valid_results, [])

    assert performance["status"] == "insufficient_evidence"
    assert performance["reason_codes"] == ["missing_backtest_metric"]
    assert performance["reasons"][0]["metric"] == "backtest_exposure_pct"
    assert performance["metric_ranges"]["backtest_exposure_pct"]["missing_count"] == 1


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
    market_signals = _market_signals(result)
    manifest = _manifest(result)
    strategy_run = strategy_runs["runs"][0]
    market_signal = market_signals["signals"][0]

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
        "execution_model_id": "close_to_close_next_bar_v1",
        "price_source": "close",
        "signal_timing": "signal_at_bar_close",
        "position_timing": "next_bar",
        "lookahead_policy": "no_same_bar_execution",
        "execution_timing": "research_close_to_close",
    }
    assert backtest["window"] == {
        "start": "2026-06-01T00:00:00Z",
        "end": "2026-06-05T00:00:00Z",
        "rows": 5,
    }
    assert backtest["metrics"]["calculation_backend"] == "halpha.strategy_evaluation.evaluate_single_window_backtest"
    assert backtest["metrics"]["execution_model_id"] == "close_to_close_next_bar_v1"
    assert backtest["metrics"]["position_timing"] == "next_bar"
    assert backtest["metrics"]["lookahead_policy"] == "no_same_bar_execution"
    assert backtest["metrics"]["trade_count"] >= 1
    assert backtest["metrics"]["exposure_pct"] > 0
    assert backtest["metrics"]["final_equity"] > 0
    assert set(backtest["metrics"]) == {
        "calculation_backend",
        "execution_model_id",
        "signal_timing",
        "position_timing",
        "lookahead_policy",
        "return_metric_basis",
        "total_return_pct",
        "gross_return_pct",
        "net_return_pct",
        "total_cost_pct",
        "cost_drag_pct",
        "max_drawdown_pct",
        "trade_count",
        "turnover",
        "exposure_pct",
        "final_equity",
        "final_equity_multiplier",
    }
    assert "Historical backtest diagnostic is research material" in backtest["warnings"][0]
    assert strategy_run["parameter_diagnostic"] == {"enabled": False, "status": "disabled"}
    assert strategy_run["error"] is None

    assert market_signal["strategy_name"] == "tsmom_vol_scaled"
    assert market_signal["direction"] == "bullish"
    assert market_signal["key_values"]["return_window_pct"] == 4.807692
    assert market_signal["key_values"]["entry_count"] == 1
    assert market_signal["key_values"]["backtest_diagnostic_status"] == "succeeded"
    assert market_signal["key_values"]["backtest_trade_count"] >= 1
    assert market_signal["key_values"]["backtest_final_equity"] > 0
    assert market_signal["source_artifacts"] == [
        "analysis/quant_strategy_runs.json",
        "raw/market_data_views.json",
    ]
    assert market_signals["source_artifacts"] == [
        "analysis/quant_strategy_runs.json",
        "raw/market_data_views.json",
    ]
    assert market_signals["signals"][0]["strategy_name"] == "tsmom_vol_scaled"
    assert manifest["artifacts"]["quant_strategy_runs"] == "analysis/quant_strategy_runs.json"
    assert manifest["counts"]["quant_strategy_runs"] == 1
    assert manifest["counts"]["quant_strategy_runs_succeeded"] == 1
    assert manifest["counts"]["quant_strategy_runs_failed"] == 0
    assert manifest["counts"]["quant_strategy_runs_insufficient_data"] == 0
    assert manifest["quant_strategies"]["enabled"] == ["tsmom_vol_scaled"]
    assert manifest["quant_strategies"]["backtest_diagnostics_enabled"] is True
    assert manifest["quant_strategies"]["parameter_diagnostics_enabled"] is False
    assert manifest["quant_strategies"]["failures"] == []
    assert manifest["quant_strategies"]["insufficient_data"] == []
    assert _stage(manifest, "evaluate_quant_strategies")["artifacts"] == [
        "analysis/quant_strategy_runs.json"
    ]


def test_quant_strategy_runner_writes_signed_tsmom_strategy_artifacts(tmp_path: Path) -> None:
    config_path = _write_signed_tsmom_strategy_config(tmp_path, lookback=5)
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
            _record(open_time="2026-06-02T00:00:00Z", close=102, volume=11),
            _record(open_time="2026-06-03T00:00:00Z", close=101, volume=12),
            _record(open_time="2026-06-04T00:00:00Z", close=101.2, volume=13),
            _record(open_time="2026-06-05T00:00:00Z", close=103.224, volume=14),
        ]
    )

    result = _run_pipeline_with_strategies(config, config_path)

    strategy_runs = _strategy_runs(result)
    manifest = _manifest(result)
    strategy_run = strategy_runs["runs"][0]

    assert result.succeeded is True
    assert strategy_run["strategy_name"] == "signed_tsmom_trend"
    assert strategy_run["strategy_family"] == "trend"
    assert strategy_run["output_position_policy"] == "research_signed_target_exposure"
    assert strategy_run["params"] == {
        "return_window": 1,
        "deadband_pct": 0.5,
    }
    assert strategy_run["signals"]["latest_position_state"] == "long"
    assert strategy_run["signals"]["short_entry_count"] == 1
    assert strategy_run["backtest_diagnostic"]["status"] == "succeeded"
    assert strategy_run["backtest_diagnostic"]["assumptions"]["direction"] == "long_short"
    assert manifest["quant_strategies"]["enabled"] == ["signed_tsmom_trend"]
    assert manifest["counts"]["quant_strategy_runs_succeeded"] == 1
    json.dumps(strategy_runs)


def test_quant_strategy_runner_writes_sma_cross_long_short_artifacts(tmp_path: Path) -> None:
    config_path = _write_sma_cross_long_short_strategy_config(tmp_path, lookback=5)
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
            _record(open_time="2026-06-02T00:00:00Z", close=102, volume=11),
            _record(open_time="2026-06-03T00:00:00Z", close=99, volume=12),
            _record(open_time="2026-06-04T00:00:00Z", close=100, volume=13),
            _record(open_time="2026-06-05T00:00:00Z", close=103, volume=14),
        ]
    )

    result = _run_pipeline_with_strategies(config, config_path)

    strategy_runs = _strategy_runs(result)
    manifest = _manifest(result)
    strategy_run = strategy_runs["runs"][0]

    assert result.succeeded is True
    assert strategy_run["strategy_name"] == "sma_cross_long_short"
    assert strategy_run["strategy_family"] == "moving_average"
    assert strategy_run["output_position_policy"] == "research_signed_target_exposure"
    assert strategy_run["params"] == {
        "short_window": 1,
        "long_window": 2,
        "neutral_band_pct": 0.5,
    }
    assert strategy_run["signals"]["latest_position_state"] == "long"
    assert strategy_run["signals"]["short_entry_count"] == 1
    assert strategy_run["backtest_diagnostic"]["status"] == "succeeded"
    assert strategy_run["backtest_diagnostic"]["assumptions"]["direction"] == "long_short"
    assert manifest["quant_strategies"]["enabled"] == ["sma_cross_long_short"]
    assert manifest["counts"]["quant_strategy_runs_succeeded"] == 1
    json.dumps(strategy_runs)


def test_quant_strategy_runner_writes_bollinger_rsi_long_short_artifacts(tmp_path: Path) -> None:
    config_path = _write_bollinger_rsi_long_short_strategy_config(tmp_path, lookback=3)
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
            _record(open_time="2026-06-02T00:00:00Z", close=102, volume=11),
            _record(open_time="2026-06-03T00:00:00Z", close=98, volume=12),
        ]
    )

    result = _run_pipeline_with_strategies(config, config_path)

    strategy_runs = _strategy_runs(result)
    manifest = _manifest(result)
    strategy_run = strategy_runs["runs"][0]

    assert result.succeeded is True
    assert strategy_run["strategy_name"] == "bollinger_rsi_long_short"
    assert strategy_run["strategy_family"] == "mean_reversion"
    assert strategy_run["output_position_policy"] == "research_signed_target_exposure"
    assert strategy_run["params"]["bollinger_window"] == 2
    assert strategy_run["signals"]["latest_position_state"] == "long"
    assert strategy_run["signals"]["latest_oversold"] is True
    assert strategy_run["backtest_diagnostic"]["status"] == "succeeded"
    assert strategy_run["backtest_diagnostic"]["assumptions"]["direction"] == "long_short"
    assert manifest["quant_strategies"]["enabled"] == ["bollinger_rsi_long_short"]
    assert manifest["counts"]["quant_strategy_runs_succeeded"] == 1
    json.dumps(strategy_runs)


def test_quant_strategy_runner_records_insufficient_data_without_fabrication(tmp_path: Path) -> None:
    config_path = _write_strategy_config(tmp_path, lookback=2)
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records([_record(open_time="2026-06-05T00:00:00Z", close=109, volume=14)])

    result = _run_pipeline_with_strategies(config, config_path)

    strategy_run = _strategy_runs(result)["runs"][0]
    market_signal = _market_signals(result)["signals"][0]
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
    assert market_signal["direction"] == "unknown"
    assert market_signal["insufficient_data"] is True
    assert market_signal["key_values"]["backtest_diagnostic_status"] == "skipped"
    assert manifest["counts"]["quant_strategy_runs_insufficient_data"] == 1
    assert manifest["counts"]["market_signals_insufficient_data"] == 1
    assert manifest["quant_strategies"]["insufficient_data"][0]["row_count"] == 1


def test_quant_strategy_runner_blocks_degraded_ohlcv_view_without_fabrication(
    tmp_path: Path,
) -> None:
    config_path = _write_strategy_config(tmp_path, lookback=4)
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
            _record(open_time="2026-06-03T00:00:00Z", close=104, volume=12),
            _record(open_time="2026-06-04T00:00:00Z", close=106, volume=13),
            _record(open_time="2026-06-05T00:00:00Z", close=109, volume=14),
        ]
    )

    result = _run_pipeline_with_strategies(config, config_path)

    strategy_run = _strategy_runs(result)["runs"][0]
    manifest = _manifest(result)

    assert result.succeeded is True
    assert strategy_run["status"] == "insufficient_data"
    assert strategy_run["data_quality"]["row_count"] == 4
    assert strategy_run["warnings"][0]["code"] == "degraded_ohlcv_quality"
    assert strategy_run["indicators"] == {}
    assert manifest["counts"]["quant_strategy_runs_succeeded"] == 0
    assert manifest["counts"]["quant_strategy_runs_insufficient_data"] == 1


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

    result = _run_pipeline_with_strategies(config, config_path, until_stage="build_materials")

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
        "metric_scope": "latest_state_and_canonical_next_bar_backtest_summary",
        "selection_policy": "diagnostic_only_no_best_parameter_selection",
        "strategy_backtest_enabled": True,
        "execution_model_id": "close_to_close_next_bar_v1",
        "signal_timing": "signal_at_bar_close",
        "position_timing": "next_bar",
        "lookahead_policy": "no_same_bar_execution",
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
    assert diagnostic["signal_state_stability"]["status"] == "sensitive"
    assert diagnostic["signal_state_stability"]["reason_codes"] == [
        "direction_sensitivity",
        "latest_regime_sensitivity",
        "invalid_combinations_present",
    ]
    assert diagnostic["performance_stability"]["status"] == "partially_stable"
    assert diagnostic["performance_stability"]["reason_codes"] == ["invalid_combinations_present"]
    assert diagnostic["performance_stability"]["metric_ranges"]["backtest_total_return_pct"]["range"] > 0
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
    assert any(item["code"] == "parameter_performance_partial_evidence" for item in diagnostic["warnings"])
    assert "do not choose trading parameters" in diagnostic["notes"][0]

    assert strategy_signal["key_values"]["parameter_diagnostic_status"] == "succeeded"
    assert strategy_signal["key_values"]["parameter_tested_combinations"] == 3
    assert strategy_signal["key_values"]["parameter_valid_combinations"] == 2
    assert strategy_signal["key_values"]["parameter_invalid_combinations"] == 1
    assert strategy_signal["key_values"]["parameter_stability"] == "sensitive"
    assert strategy_signal["key_values"]["parameter_signal_state_stability"] == "sensitive"
    assert strategy_signal["key_values"]["parameter_performance_stability"] == "partially_stable"
    assert strategy_signal["key_values"]["parameter_performance_stability_reason_codes"] == [
        "invalid_combinations_present"
    ]
    assert any("multiple assessment directions" in item for item in strategy_signal["uncertainty"])
    assert market_signal["key_values"]["parameter_stability"] == "sensitive"
    assert market_signal["key_values"]["parameter_performance_stability"] == "partially_stable"
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
    assert manifest["counts"]["quant_strategy_runs"] == 3
    assert manifest["counts"]["quant_strategy_runs_succeeded"] == 1
    assert manifest["counts"]["quant_strategy_runs_failed"] == 1
    assert manifest["counts"]["quant_strategy_runs_insufficient_data"] == 1
    assert manifest["counts"]["quant_strategy_runs_disabled"] == 0
    assert manifest["counts"]["quant_strategies_enabled"] == 3
    assert manifest["counts"]["quant_strategies_disabled"] == 1
    assert manifest["counts"]["market_signals"] == 3
    assert manifest["counts"]["market_signals_insufficient_data"] == 1
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


def test_quant_strategy_runner_uses_only_targeted_strategy_profiles(tmp_path: Path) -> None:
    config_path = _write_targeted_matrix_strategy_config(tmp_path)
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(
                source="binance",
                symbol="BTCUSDT",
                timeframe="1d",
                open_time="2026-06-01T00:00:00Z",
                close=100,
                volume=10,
            ),
            _record(
                source="binance",
                symbol="BTCUSDT",
                timeframe="1d",
                open_time="2026-06-02T00:00:00Z",
                close=102,
                volume=11,
            ),
            _record(
                source="binance",
                symbol="BTCUSDT",
                timeframe="1d",
                open_time="2026-06-03T00:00:00Z",
                close=104,
                volume=12,
            ),
            _record(
                source="binance",
                symbol="BTCUSDT",
                timeframe="4h",
                open_time="2026-06-01T00:00:00Z",
                close=100,
                volume=10,
            ),
            _record(
                source="binance",
                symbol="BTCUSDT",
                timeframe="4h",
                open_time="2026-06-01T04:00:00Z",
                close=102,
                volume=11,
            ),
            _record(
                source="binance",
                symbol="BTCUSDT",
                timeframe="4h",
                open_time="2026-06-01T08:00:00Z",
                close=101,
                volume=12,
            ),
        ]
    )

    result = _run_pipeline_with_strategies(config, config_path)

    runs = _strategy_runs(result)["runs"]
    manifest = _manifest(result)
    identities = sorted((item["strategy_name"], item["symbol"], item["timeframe"]) for item in runs)

    assert result.succeeded is True
    assert identities == [
        ("signed_tsmom_trend", "BTCUSDT", "4h"),
        ("tsmom_vol_scaled", "BTCUSDT", "1d"),
    ]
    assert all(item["parameter_profile"]["source"] == "targeted_params" for item in runs)
    assert {item["symbol"] for item in runs} == {"BTCUSDT"}
    assert manifest["counts"]["quant_strategy_runs"] == 2
    assert manifest["counts"]["quant_strategies_enabled"] == 3
    assert manifest["quant_strategies"]["selection_policy"] == {
        "source": "targeted_params",
        "unmatched_target_combinations_embedded": False,
    }


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


def test_quant_strategy_runner_writes_sma_cross_trend_artifacts(tmp_path: Path) -> None:
    config_path = _write_sma_cross_strategy_config(tmp_path, lookback=6)
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
    assert strategy_run["strategy_name"] == "sma_cross_trend"
    assert strategy_run["params"] == {
        "short_window": 2,
        "long_window": 3,
    }
    assert strategy_run["indicators"]["calculation_backend"] == "vectorbt.IndicatorFactory"
    assert strategy_run["indicators"]["latest_close"] == 110.0
    assert strategy_run["indicators"]["short_sma"] == 107.0
    assert strategy_run["indicators"]["long_sma"] == 105.666667
    assert strategy_run["indicators"]["trend_spread_pct"] == 1.212121
    assert strategy_run["signals"]["latest_regime"] == "sma_uptrend_active"
    assert strategy_run["signals"]["entry_count"] == 1
    assert strategy_run["signals"]["exit_count"] == 0
    assert strategy_run["signals"]["latest_entry"] is False
    assert strategy_run["signals"]["latest_signal_active"] is True
    assert strategy_run["assessment"]["direction"] == "bullish"
    assert strategy_run["assessment"]["strength"] == "medium"
    assert strategy_run["backtest_diagnostic"]["status"] == "succeeded"
    assert strategy_run["error"] is None

    assert strategy_signal["strategy_name"] == "sma_cross_trend"
    assert strategy_signal["direction"] == "bullish"
    assert strategy_signal["key_values"]["short_sma"] == 107.0
    assert strategy_signal["key_values"]["long_sma"] == 105.666667
    assert strategy_signal["key_values"]["trend_spread_pct"] == 1.212121
    assert strategy_signal["key_values"]["latest_regime"] == "sma_uptrend_active"
    assert strategy_signal["key_values"]["entry_count"] == 1
    assert strategy_signal["key_values"]["backtest_diagnostic_status"] == "succeeded"
    assert market_signal["strategy_name"] == "sma_cross_trend"
    assert manifest["counts"]["quant_strategy_runs_succeeded"] == 1
    assert manifest["quant_strategies"]["enabled"] == ["sma_cross_trend"]


def test_quant_strategy_runner_records_sma_cross_insufficient_data(tmp_path: Path) -> None:
    config_path = _write_sma_cross_strategy_config(tmp_path, lookback=2)
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


def test_strategy_signal_records_align_with_tsmom_run_transitions() -> None:
    definition = get_strategy_definition("tsmom_vol_scaled")
    assert definition is not None
    rows = [
        _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
        _record(open_time="2026-06-02T00:00:00Z", close=101, volume=11),
        _record(open_time="2026-06-03T00:00:00Z", close=99, volume=12),
        _record(open_time="2026-06-04T00:00:00Z", close=102, volume=13),
    ]
    strategy = {
        "name": "tsmom_vol_scaled",
        "params": {
            "return_window": 1,
            "volatility_window": 1,
            "target_volatility": 0.2,
        },
        "backtest": {"enabled": False},
    }
    view = _view(rows)

    signal_records = definition.signal_records(strategy, view, rows)
    strategy_run = definition.run(
        strategy,
        view,
        rows,
        engine=_engine(),
        created_at="2026-06-05T00:00:00Z",
    )

    assert signal_records["status"] == "succeeded"
    assert signal_records["position_policy"] == "research_long_flat_target_exposure"
    assert signal_records["entry_count"] == strategy_run["signals"]["entry_count"] == 2
    assert signal_records["exit_count"] == strategy_run["signals"]["exit_count"] == 1
    assert signal_records["latest_record"]["signal"]["active"] is strategy_run["signals"][
        "latest_signal_active"
    ]
    assert [item["signal"]["active"] for item in signal_records["records"]] == [
        False,
        True,
        False,
        True,
    ]
    assert [item["entry"] for item in signal_records["records"]] == [False, True, False, True]
    assert [item["exit"] for item in signal_records["records"]] == [False, False, True, False]
    assert [item["position"]["target_exposure"] for item in signal_records["records"]] == [
        0.0,
        1.0,
        0.0,
        1.0,
    ]
    assert signal_records["records"][1]["indicator_context"]["return_window_pct"] == 1.0
    json.dumps(signal_records)


def test_signed_tsmom_trend_signal_records_cover_long_short_flat_transitions() -> None:
    definition = get_strategy_definition("signed_tsmom_trend")
    assert definition is not None
    rows = [
        _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
        _record(open_time="2026-06-02T00:00:00Z", close=102, volume=11),
        _record(open_time="2026-06-03T00:00:00Z", close=101, volume=12),
        _record(open_time="2026-06-04T00:00:00Z", close=101.2, volume=13),
        _record(open_time="2026-06-05T00:00:00Z", close=103.224, volume=14),
    ]
    strategy = {
        "name": "signed_tsmom_trend",
        "params": {
            "return_window": 1,
            "deadband_pct": 0.5,
        },
        "backtest": {"enabled": False},
    }

    signal_records = definition.signal_records(strategy, _view(rows), rows)

    assert signal_records["status"] == "succeeded"
    assert signal_records["signal_record_version"] == 2
    assert signal_records["position_policy"] == "research_signed_target_exposure"
    assert [item["position"]["position_state"] for item in signal_records["records"]] == [
        "flat",
        "long",
        "short",
        "flat",
        "long",
    ]
    assert [item["position"]["target_exposure"] for item in signal_records["records"]] == [
        0.0,
        1.0,
        -1.0,
        0.0,
        1.0,
    ]
    assert [item["long_entry"] for item in signal_records["records"]] == [
        False,
        True,
        False,
        False,
        True,
    ]
    assert [item["short_entry"] for item in signal_records["records"]] == [
        False,
        False,
        True,
        False,
        False,
    ]
    assert signal_records["records"][2]["long_exit"] is True
    assert signal_records["records"][3]["short_exit"] is True
    assert signal_records["latest_record"]["indicator_context"]["return_window_pct"] == 2.0
    json.dumps(signal_records)


def test_signed_tsmom_trend_run_records_signed_policy_and_backtest_metrics() -> None:
    definition = get_strategy_definition("signed_tsmom_trend")
    assert definition is not None
    rows = [
        _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
        _record(open_time="2026-06-02T00:00:00Z", close=102, volume=11),
        _record(open_time="2026-06-03T00:00:00Z", close=101, volume=12),
        _record(open_time="2026-06-04T00:00:00Z", close=101.2, volume=13),
        _record(open_time="2026-06-05T00:00:00Z", close=103.224, volume=14),
    ]
    strategy = {
        "name": "signed_tsmom_trend",
        "params": {
            "return_window": 1,
            "deadband_pct": 0.5,
        },
        "backtest": {
            "enabled": True,
            "initial_cash": 10000,
            "fees_bps": 10,
            "slippage_bps": 5,
        },
    }

    strategy_run = definition.run(
        strategy,
        _view(rows),
        rows,
        engine=_engine(),
        created_at="2026-06-05T00:00:00Z",
    )

    assert strategy_run["status"] == "succeeded"
    assert strategy_run["strategy_family"] == "trend"
    assert strategy_run["output_position_policy"] == "research_signed_target_exposure"
    assert strategy_run["signals"]["latest_position_state"] == "long"
    assert strategy_run["signals"]["long_entry_count"] == 2
    assert strategy_run["signals"]["side_flip_count"] == 1
    assert strategy_run["assessment"]["direction"] == "bullish"
    assert strategy_run["backtest_diagnostic"]["status"] == "succeeded"
    assert strategy_run["backtest_diagnostic"]["assumptions"]["direction"] == "long_short"
    assert strategy_run["backtest_diagnostic"]["metrics"]["long_trade_count"] == 1
    assert strategy_run["backtest_diagnostic"]["metrics"]["short_trade_count"] == 1
    json.dumps(strategy_run)


def test_signed_tsmom_trend_run_records_bearish_and_neutral_states() -> None:
    definition = get_strategy_definition("signed_tsmom_trend")
    assert definition is not None
    bearish_rows = [
        _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
        _record(open_time="2026-06-02T00:00:00Z", close=98, volume=11),
    ]
    neutral_rows = [
        _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
        _record(open_time="2026-06-02T00:00:00Z", close=100.2, volume=11),
    ]
    strategy = {
        "name": "signed_tsmom_trend",
        "params": {
            "return_window": 1,
            "deadband_pct": 0.5,
        },
    }

    bearish_run = definition.run(
        strategy,
        _view(bearish_rows),
        bearish_rows,
        engine=_engine(),
        created_at="2026-06-05T00:00:00Z",
    )
    neutral_run = definition.run(
        strategy,
        _view(neutral_rows),
        neutral_rows,
        engine=_engine(),
        created_at="2026-06-05T00:00:00Z",
    )

    assert bearish_run["signals"]["latest_position_state"] == "short"
    assert bearish_run["assessment"]["direction"] == "bearish"
    assert neutral_run["signals"]["latest_position_state"] == "flat"
    assert neutral_run["assessment"]["direction"] == "neutral"
    json.dumps(bearish_run)
    json.dumps(neutral_run)


def test_signed_tsmom_trend_records_insufficient_data_and_param_validation() -> None:
    definition = get_strategy_definition("signed_tsmom_trend")
    assert definition is not None
    rows = [_record(open_time="2026-06-01T00:00:00Z", close=100, volume=10)]
    strategy = {
        "name": "signed_tsmom_trend",
        "params": {
            "return_window": 2,
            "deadband_pct": 0.5,
        },
    }

    signal_records = definition.signal_records(strategy, _view(rows), rows)

    assert signal_records["status"] == "insufficient_data"
    assert signal_records["position_policy"] == "research_signed_target_exposure"
    assert signal_records["warnings"][0]["code"] == "insufficient_ohlcv_rows"
    with pytest.raises(ValueError, match="return_window must be a positive integer"):
        definition.signal_records(
            {
                "name": "signed_tsmom_trend",
                "params": {"return_window": 0, "deadband_pct": 0.5},
            },
            _view(rows),
            rows,
        )
    with pytest.raises(ValueError, match="deadband_pct must be a number between 0.0 and 100.0"):
        definition.signal_records(
            {
                "name": "signed_tsmom_trend",
                "params": {"return_window": 1, "deadband_pct": -0.1},
            },
            _view(rows),
            rows,
        )
    json.dumps(signal_records)


def test_signed_tsmom_trend_optional_volatility_filter_records_pass_and_suppression() -> None:
    definition = get_strategy_definition("signed_tsmom_trend")
    assert definition is not None
    passed_rows = [
        _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
        _record(open_time="2026-06-02T00:00:00Z", close=101, volume=11),
        _record(open_time="2026-06-03T00:00:00Z", close=102, volume=12),
        _record(open_time="2026-06-04T00:00:00Z", close=103, volume=13),
    ]
    suppressed_rows = [
        _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
        _record(open_time="2026-06-02T00:00:00Z", close=101, volume=11),
        _record(open_time="2026-06-03T00:00:00Z", close=102, volume=12),
        _record(open_time="2026-06-04T00:00:00Z", close=120, volume=13),
    ]
    strategy = {
        "name": "signed_tsmom_trend",
        "params": {
            "return_window": 1,
            "deadband_pct": 0.1,
            "volatility_filter_enabled": True,
            "volatility_filter_window": 2,
            "max_realized_volatility_pct": 20.0,
        },
        "backtest": {"enabled": False},
    }

    passed_run = definition.run(
        strategy,
        _view(passed_rows),
        passed_rows,
        engine=_engine(),
        created_at="2026-06-05T00:00:00Z",
    )
    suppressed_run = definition.run(
        strategy,
        _view(suppressed_rows),
        suppressed_rows,
        engine=_engine(),
        created_at="2026-06-05T00:00:00Z",
    )

    assert passed_run["signals"]["latest_position_state"] == "long"
    assert passed_run["signals"]["volatility_filter"]["status"] == "passed"
    assert passed_run["signals"]["filter_suppression_reason"] is None
    assert suppressed_run["signals"]["latest_position_state"] == "flat"
    assert suppressed_run["signals"]["volatility_filter"]["status"] == "suppressed"
    assert suppressed_run["signals"]["filter_suppression_reason"] == "realized_volatility_above_max"
    assert suppressed_run["warnings"][0]["code"] == "realized_volatility_filter_suppressed_signal"
    assert suppressed_run["indicators"]["volatility_filter_realized_volatility_pct"] > 20.0
    json.dumps(passed_run)
    json.dumps(suppressed_run)


def test_signed_tsmom_trend_optional_volatility_filter_insufficient_and_invalid_params() -> None:
    definition = get_strategy_definition("signed_tsmom_trend")
    assert definition is not None
    rows = [
        _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
        _record(open_time="2026-06-02T00:00:00Z", close=101, volume=11),
        _record(open_time="2026-06-03T00:00:00Z", close=102, volume=12),
    ]

    signal_records = definition.signal_records(
        {
            "name": "signed_tsmom_trend",
            "params": {
                "return_window": 1,
                "deadband_pct": 0.1,
                "volatility_filter_enabled": True,
                "volatility_filter_window": 4,
                "max_realized_volatility_pct": 20.0,
            },
        },
        _view(rows),
        rows,
    )

    assert signal_records["status"] == "insufficient_data"
    assert signal_records["warnings"][0]["code"] == "insufficient_ohlcv_rows"
    with pytest.raises(ValueError, match="volatility_filter_enabled must be a boolean"):
        definition.signal_records(
            {
                "name": "signed_tsmom_trend",
                "params": {
                    "return_window": 1,
                    "deadband_pct": 0.1,
                    "volatility_filter_enabled": "yes",
                },
            },
            _view(rows),
            rows,
        )
    with pytest.raises(ValueError, match="max_realized_volatility_pct must be a positive number"):
        definition.signal_records(
            {
                "name": "signed_tsmom_trend",
                "params": {
                    "return_window": 1,
                    "deadband_pct": 0.1,
                    "volatility_filter_enabled": True,
                    "max_realized_volatility_pct": 0.0,
                },
            },
            _view(rows),
            rows,
        )
    json.dumps(signal_records)


def test_signed_tsmom_trend_optional_funding_rate_filter_suppresses_exposure() -> None:
    definition = get_strategy_definition("signed_tsmom_trend")
    assert definition is not None
    rows = [
        _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
        _record(open_time="2026-06-02T00:00:00Z", close=102, volume=11),
        _record(open_time="2026-06-03T00:00:00Z", close=104, volume=12),
    ]
    strategy = {
        "name": "signed_tsmom_trend",
        "params": {
            "return_window": 1,
            "deadband_pct": 0.1,
            "funding_rate_filter_enabled": True,
            "max_abs_funding_rate": 0.001,
        },
        "derivatives_features": {
            "funding_rate": {
                "status": "available",
                "records": [
                    {
                        "feature_time": "2026-06-02T00:00:00Z",
                        "as_of": "2026-06-02T00:00:00Z",
                        "first_seen_at": "2026-06-02T00:00:00Z",
                        "source": "binance_usdm",
                        "symbol": "BTCUSDT",
                        "period": "8h",
                        "data_class": "funding_rate",
                        "metric": "funding_rate",
                        "value": 0.002,
                        "unit": "ratio",
                        "quality": {"status": "available", "warnings": [], "errors": []},
                        "source_artifacts": [],
                    }
                ],
            }
        },
        "backtest": {"enabled": False},
    }

    strategy_run = definition.run(
        strategy,
        _view(rows),
        rows,
        engine=_engine(),
        created_at="2026-06-03T00:00:00Z",
    )
    signal_records = definition.signal_records(strategy, _view(rows), rows)

    assert strategy_run["status"] == "succeeded"
    assert strategy_run["signals"]["latest_position_state"] == "flat"
    assert strategy_run["signals"]["funding_rate_filter"]["status"] == "suppressed"
    assert strategy_run["signals"]["filter_suppression_reason"] == "funding_rate_abs_above_max"
    assert strategy_run["indicators"]["funding_rate_filter_value"] == 0.002
    assert strategy_run["warnings"][0]["code"] == "funding_rate_filter_suppressed_signal"
    assert (
        signal_records["latest_record"]["indicator_context"]["funding_rate_filter"]["suppression_reason"]
        == "funding_rate_abs_above_max"
    )
    json.dumps(strategy_run)
    json.dumps(signal_records)


def test_signed_tsmom_trend_optional_funding_rate_filter_validates_params() -> None:
    definition = get_strategy_definition("signed_tsmom_trend")
    assert definition is not None
    rows = [
        _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
        _record(open_time="2026-06-02T00:00:00Z", close=102, volume=11),
    ]

    with pytest.raises(ValueError, match="funding_rate_filter_enabled must be a boolean"):
        definition.signal_records(
            {
                "name": "signed_tsmom_trend",
                "params": {
                    "return_window": 1,
                    "deadband_pct": 0.1,
                    "funding_rate_filter_enabled": "yes",
                },
            },
            _view(rows),
            rows,
        )
    with pytest.raises(ValueError, match="max_abs_funding_rate must be a positive number"):
        definition.signal_records(
            {
                "name": "signed_tsmom_trend",
                "params": {
                    "return_window": 1,
                    "deadband_pct": 0.1,
                    "funding_rate_filter_enabled": True,
                    "max_abs_funding_rate": 0.0,
                },
            },
            _view(rows),
            rows,
        )


def test_signed_tsmom_trend_optional_market_anomaly_filter_suppresses_exposure() -> None:
    definition = get_strategy_definition("signed_tsmom_trend")
    assert definition is not None
    rows = [
        _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
        _record(open_time="2026-06-02T00:00:00Z", close=102, volume=11),
        _record(open_time="2026-06-03T00:00:00Z", close=104, volume=12),
    ]
    strategy = {
        "name": "signed_tsmom_trend",
        "params": {
            "return_window": 1,
            "deadband_pct": 0.1,
            "market_anomaly_filter_enabled": True,
            "market_anomaly_filter_lookback_hours": 24.0,
            "market_anomaly_filter_min_count": 1,
        },
        "event_features": {
            "market_anomaly": {
                "status": "available",
                "records": [
                    {
                        "event_id": "anomaly:BTCUSDT:2026-06-02T12:00:00Z",
                        "data_type": "market_anomaly",
                        "event_time": "2026-06-02T12:00:00Z",
                        "published_at": "2026-06-02T12:00:00Z",
                        "collected_at": "2026-06-02T12:01:00Z",
                        "first_seen_at": "2026-06-02T12:01:00Z",
                        "source": "halpha_monitor_rules",
                        "category": "volume_spike",
                        "categories": ["market_anomaly", "volume_spike"],
                        "class": "volume_spike",
                        "severity": "high",
                        "symbol": "BTCUSDT",
                        "region": "",
                        "title": "BTCUSDT volume spike",
                        "summary": "BTCUSDT volume spike detected.",
                        "keywords_text": "BTCUSDT volume spike",
                        "quality": {"status": "available", "warnings": [], "errors": []},
                        "source_artifacts": [],
                    }
                ],
            }
        },
        "backtest": {"enabled": False},
    }

    strategy_run = definition.run(
        strategy,
        _view(rows),
        rows,
        engine=_engine(),
        created_at="2026-06-03T00:00:00Z",
    )
    signal_records = definition.signal_records(strategy, _view(rows), rows)

    assert strategy_run["status"] == "succeeded"
    assert strategy_run["signals"]["latest_position_state"] == "flat"
    assert strategy_run["signals"]["market_anomaly_filter"]["event_count"] == 1
    assert strategy_run["signals"]["filter_suppression_reason"] == "event_count_at_or_above_min"
    assert strategy_run["indicators"]["market_anomaly_filter_event_count"] == 1
    assert strategy_run["warnings"][0]["code"] == "market_anomaly_filter_suppressed_signal"
    assert (
        signal_records["latest_record"]["indicator_context"]["market_anomaly_filter"]["suppression_reason"]
        == "event_count_at_or_above_min"
    )
    json.dumps(strategy_run)
    json.dumps(signal_records)


def test_signed_tsmom_trend_optional_market_anomaly_filter_validates_params() -> None:
    definition = get_strategy_definition("signed_tsmom_trend")
    assert definition is not None
    rows = [
        _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
        _record(open_time="2026-06-02T00:00:00Z", close=102, volume=11),
    ]

    with pytest.raises(ValueError, match="market_anomaly_filter_enabled must be a boolean"):
        definition.signal_records(
            {
                "name": "signed_tsmom_trend",
                "params": {
                    "return_window": 1,
                    "deadband_pct": 0.1,
                    "market_anomaly_filter_enabled": "yes",
                },
            },
            _view(rows),
            rows,
        )
    with pytest.raises(ValueError, match="market_anomaly_filter_lookback_hours must be a positive number"):
        definition.signal_records(
            {
                "name": "signed_tsmom_trend",
                "params": {
                    "return_window": 1,
                    "deadband_pct": 0.1,
                    "market_anomaly_filter_enabled": True,
                    "market_anomaly_filter_lookback_hours": 0.0,
                },
            },
            _view(rows),
            rows,
        )
    with pytest.raises(ValueError, match="market_anomaly_filter_min_count must be a positive integer"):
        definition.signal_records(
            {
                "name": "signed_tsmom_trend",
                "params": {
                    "return_window": 1,
                    "deadband_pct": 0.1,
                    "market_anomaly_filter_enabled": True,
                    "market_anomaly_filter_min_count": 0,
                },
            },
            _view(rows),
            rows,
        )


def test_sma_cross_long_short_signal_records_cover_long_short_flat_transitions() -> None:
    definition = get_strategy_definition("sma_cross_long_short")
    assert definition is not None
    rows = [
        _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
        _record(open_time="2026-06-02T00:00:00Z", close=102, volume=11),
        _record(open_time="2026-06-03T00:00:00Z", close=99, volume=12),
        _record(open_time="2026-06-04T00:00:00Z", close=100, volume=13),
        _record(open_time="2026-06-05T00:00:00Z", close=103, volume=14),
    ]
    strategy = {
        "name": "sma_cross_long_short",
        "params": {
            "short_window": 1,
            "long_window": 2,
            "neutral_band_pct": 0.5,
        },
        "backtest": {"enabled": False},
    }

    signal_records = definition.signal_records(strategy, _view(rows), rows)

    assert signal_records["status"] == "succeeded"
    assert signal_records["signal_record_version"] == 2
    assert signal_records["position_policy"] == "research_signed_target_exposure"
    assert [item["position"]["position_state"] for item in signal_records["records"]] == [
        "flat",
        "long",
        "short",
        "flat",
        "long",
    ]
    assert [item["position"]["target_exposure"] for item in signal_records["records"]] == [
        0.0,
        1.0,
        -1.0,
        0.0,
        1.0,
    ]
    assert signal_records["records"][2]["short_entry"] is True
    assert signal_records["records"][3]["short_exit"] is True
    assert signal_records["latest_record"]["indicator_context"]["short_sma"] == 103.0
    assert signal_records["latest_record"]["indicator_context"]["long_sma"] == 101.5
    assert signal_records["latest_record"]["indicator_context"]["trend_spread_pct"] == pytest.approx(
        1.456311,
        abs=0.000001,
    )
    json.dumps(signal_records)


def test_sma_cross_long_short_run_records_signed_policy_and_backtest_metrics() -> None:
    definition = get_strategy_definition("sma_cross_long_short")
    assert definition is not None
    rows = [
        _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
        _record(open_time="2026-06-02T00:00:00Z", close=102, volume=11),
        _record(open_time="2026-06-03T00:00:00Z", close=99, volume=12),
        _record(open_time="2026-06-04T00:00:00Z", close=100, volume=13),
        _record(open_time="2026-06-05T00:00:00Z", close=103, volume=14),
    ]
    strategy = {
        "name": "sma_cross_long_short",
        "params": {
            "short_window": 1,
            "long_window": 2,
            "neutral_band_pct": 0.5,
        },
        "backtest": {
            "enabled": True,
            "initial_cash": 10000,
            "fees_bps": 10,
            "slippage_bps": 5,
        },
    }

    strategy_run = definition.run(
        strategy,
        _view(rows),
        rows,
        engine=_engine(),
        created_at="2026-06-05T00:00:00Z",
    )

    assert strategy_run["status"] == "succeeded"
    assert strategy_run["strategy_family"] == "moving_average"
    assert strategy_run["output_position_policy"] == "research_signed_target_exposure"
    assert strategy_run["signals"]["latest_position_state"] == "long"
    assert strategy_run["signals"]["long_entry_count"] == 2
    assert strategy_run["signals"]["short_entry_count"] == 1
    assert strategy_run["signals"]["side_flip_count"] == 1
    assert strategy_run["indicators"]["neutral_band_pct"] == 0.5
    assert strategy_run["assessment"]["direction"] == "bullish"
    assert strategy_run["backtest_diagnostic"]["status"] == "succeeded"
    assert strategy_run["backtest_diagnostic"]["assumptions"]["direction"] == "long_short"
    assert strategy_run["backtest_diagnostic"]["metrics"]["long_trade_count"] == 1
    assert strategy_run["backtest_diagnostic"]["metrics"]["short_trade_count"] == 1
    json.dumps(strategy_run)


def test_sma_cross_long_short_run_records_bearish_and_neutral_states() -> None:
    definition = get_strategy_definition("sma_cross_long_short")
    assert definition is not None
    bearish_rows = [
        _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
        _record(open_time="2026-06-02T00:00:00Z", close=99, volume=11),
        _record(open_time="2026-06-03T00:00:00Z", close=98, volume=12),
    ]
    neutral_rows = [
        _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
        _record(open_time="2026-06-02T00:00:00Z", close=100.1, volume=11),
        _record(open_time="2026-06-03T00:00:00Z", close=100.2, volume=12),
    ]
    strategy = {
        "name": "sma_cross_long_short",
        "params": {
            "short_window": 1,
            "long_window": 2,
            "neutral_band_pct": 0.5,
        },
    }

    bearish_run = definition.run(
        strategy,
        _view(bearish_rows),
        bearish_rows,
        engine=_engine(),
        created_at="2026-06-05T00:00:00Z",
    )
    neutral_run = definition.run(
        strategy,
        _view(neutral_rows),
        neutral_rows,
        engine=_engine(),
        created_at="2026-06-05T00:00:00Z",
    )

    assert bearish_run["signals"]["latest_position_state"] == "short"
    assert bearish_run["assessment"]["direction"] == "bearish"
    assert neutral_run["signals"]["latest_position_state"] == "flat"
    assert neutral_run["assessment"]["direction"] == "neutral"
    json.dumps(bearish_run)
    json.dumps(neutral_run)


def test_sma_cross_long_short_records_insufficient_data_and_param_validation() -> None:
    definition = get_strategy_definition("sma_cross_long_short")
    assert definition is not None
    rows = [_record(open_time="2026-06-01T00:00:00Z", close=100, volume=10)]
    strategy = {
        "name": "sma_cross_long_short",
        "params": {
            "short_window": 1,
            "long_window": 2,
            "neutral_band_pct": 0.5,
        },
    }

    signal_records = definition.signal_records(strategy, _view(rows), rows)

    assert signal_records["status"] == "insufficient_data"
    assert signal_records["position_policy"] == "research_signed_target_exposure"
    assert signal_records["warnings"][0]["code"] == "insufficient_ohlcv_rows"
    with pytest.raises(ValueError, match="short_window must be a positive integer"):
        definition.signal_records(
            {
                "name": "sma_cross_long_short",
                "params": {"short_window": 0, "long_window": 2, "neutral_band_pct": 0.5},
            },
            _view(rows),
            rows,
        )
    with pytest.raises(ValueError, match="short_window must be lower than long_window"):
        definition.signal_records(
            {
                "name": "sma_cross_long_short",
                "params": {"short_window": 2, "long_window": 2, "neutral_band_pct": 0.5},
            },
            _view(rows),
            rows,
        )
    with pytest.raises(ValueError, match="neutral_band_pct must be a number between 0.0 and 100.0"):
        definition.signal_records(
            {
                "name": "sma_cross_long_short",
                "params": {"short_window": 1, "long_window": 2, "neutral_band_pct": -0.1},
            },
            _view(rows),
            rows,
        )
    json.dumps(signal_records)


def test_bollinger_rsi_long_short_signal_records_cover_long_short_flat_and_suppression() -> None:
    definition = get_strategy_definition("bollinger_rsi_long_short")
    assert definition is not None
    strategy = _bollinger_rsi_long_short_strategy()
    long_rows = [
        _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
        _record(open_time="2026-06-02T00:00:00Z", close=102, volume=11),
        _record(open_time="2026-06-03T00:00:00Z", close=98, volume=12),
    ]
    short_rows = [
        _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
        _record(open_time="2026-06-02T00:00:00Z", close=98, volume=11),
        _record(open_time="2026-06-03T00:00:00Z", close=102, volume=12),
    ]
    flat_rows = [
        _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
        _record(open_time="2026-06-02T00:00:00Z", close=100, volume=11),
        _record(open_time="2026-06-03T00:00:00Z", close=100, volume=12),
    ]
    suppressed_rows = [
        _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
        _record(open_time="2026-06-02T00:00:00Z", close=102, volume=11),
        _record(open_time="2026-06-03T00:00:00Z", close=80, volume=12),
    ]
    suppressed_strategy = _bollinger_rsi_long_short_strategy(trend_filter_pct=10)

    long_records = definition.signal_records(strategy, _view(long_rows), long_rows)
    short_records = definition.signal_records(strategy, _view(short_rows), short_rows)
    flat_records = definition.signal_records(strategy, _view(flat_rows), flat_rows)
    suppressed_records = definition.signal_records(suppressed_strategy, _view(suppressed_rows), suppressed_rows)

    assert long_records["latest_record"]["position"]["position_state"] == "long"
    assert long_records["latest_record"]["position"]["target_exposure"] == 1.0
    assert long_records["latest_record"]["indicator_context"]["latest_oversold"] is True
    assert short_records["latest_record"]["position"]["position_state"] == "short"
    assert short_records["latest_record"]["position"]["target_exposure"] == -1.0
    assert short_records["latest_record"]["indicator_context"]["latest_overbought"] is True
    assert flat_records["latest_record"]["position"]["position_state"] == "flat"
    assert flat_records["latest_record"]["indicator_context"]["latest_oversold"] is False
    assert flat_records["latest_record"]["indicator_context"]["latest_overbought"] is False
    assert suppressed_records["latest_record"]["position"]["position_state"] == "flat"
    assert suppressed_records["latest_record"]["indicator_context"]["latest_oversold"] is True
    assert suppressed_records["latest_record"]["indicator_context"]["trend_filter_active"] is True
    assert suppressed_records["latest_record"]["indicator_context"]["suppression_reason"] == "oversold_strong_downtrend"
    json.dumps(long_records)
    json.dumps(short_records)
    json.dumps(flat_records)
    json.dumps(suppressed_records)


def test_bollinger_rsi_long_short_run_records_short_and_suppressed_states() -> None:
    definition = get_strategy_definition("bollinger_rsi_long_short")
    assert definition is not None
    short_rows = [
        _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
        _record(open_time="2026-06-02T00:00:00Z", close=98, volume=11),
        _record(open_time="2026-06-03T00:00:00Z", close=102, volume=12),
    ]
    suppressed_rows = [
        _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
        _record(open_time="2026-06-02T00:00:00Z", close=102, volume=11),
        _record(open_time="2026-06-03T00:00:00Z", close=80, volume=12),
    ]

    short_run = definition.run(
        _bollinger_rsi_long_short_strategy(),
        _view(short_rows),
        short_rows,
        engine=_engine(),
        created_at="2026-06-05T00:00:00Z",
    )
    suppressed_run = definition.run(
        _bollinger_rsi_long_short_strategy(trend_filter_pct=10),
        _view(suppressed_rows),
        suppressed_rows,
        engine=_engine(),
        created_at="2026-06-05T00:00:00Z",
    )

    assert short_run["strategy_family"] == "mean_reversion"
    assert short_run["output_position_policy"] == "research_signed_target_exposure"
    assert short_run["signals"]["latest_position_state"] == "short"
    assert short_run["signals"]["short_entry_count"] == 1
    assert short_run["assessment"]["direction"] == "bearish"
    assert short_run["backtest_diagnostic"]["status"] == "succeeded"
    assert short_run["backtest_diagnostic"]["metrics"]["short_trade_count"] == 0
    assert suppressed_run["signals"]["latest_position_state"] == "flat"
    assert suppressed_run["signals"]["suppression_reason"] == "oversold_strong_downtrend"
    assert suppressed_run["assessment"]["direction"] == "mixed"
    assert suppressed_run["warnings"][0]["code"] == "strong_downtrend_reversion_filter"
    json.dumps(short_run)
    json.dumps(suppressed_run)


def test_bollinger_rsi_long_short_records_insufficient_data_and_param_validation() -> None:
    definition = get_strategy_definition("bollinger_rsi_long_short")
    assert definition is not None
    rows = [_record(open_time="2026-06-01T00:00:00Z", close=100, volume=10)]

    signal_records = definition.signal_records(_bollinger_rsi_long_short_strategy(), _view(rows), rows)

    assert signal_records["status"] == "insufficient_data"
    assert signal_records["position_policy"] == "research_signed_target_exposure"
    assert signal_records["warnings"][0]["code"] == "insufficient_ohlcv_rows"
    with pytest.raises(ValueError, match="bollinger_window must be a positive integer"):
        definition.signal_records(
            _bollinger_rsi_long_short_strategy(bollinger_window=0),
            _view(rows),
            rows,
        )
    with pytest.raises(ValueError, match="rsi_oversold must be lower than rsi_overbought"):
        definition.signal_records(
            _bollinger_rsi_long_short_strategy(rsi_oversold=80, rsi_overbought=70),
            _view(rows),
            rows,
        )
    with pytest.raises(ValueError, match="trend_filter_pct must be a positive number"):
        definition.signal_records(
            _bollinger_rsi_long_short_strategy(trend_filter_pct=0),
            _view(rows),
            rows,
        )
    json.dumps(signal_records)


def test_strategy_signal_records_align_with_sma_cross_transitions() -> None:
    definition = get_strategy_definition("sma_cross_trend")
    assert definition is not None
    rows = [
        _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
        _record(open_time="2026-06-02T00:00:00Z", close=102, volume=11),
        _record(open_time="2026-06-03T00:00:00Z", close=101, volume=12),
        _record(open_time="2026-06-04T00:00:00Z", close=103, volume=13),
    ]
    strategy = {
        "name": "sma_cross_trend",
        "params": {
            "short_window": 1,
            "long_window": 2,
        },
        "backtest": {"enabled": False},
    }
    view = _view(rows)

    signal_records = definition.signal_records(strategy, view, rows)
    strategy_run = definition.run(
        strategy,
        view,
        rows,
        engine=_engine(),
        created_at="2026-06-05T00:00:00Z",
    )

    assert signal_records["status"] == "succeeded"
    assert signal_records["entry_count"] == strategy_run["signals"]["entry_count"] == 2
    assert signal_records["exit_count"] == strategy_run["signals"]["exit_count"] == 1
    assert signal_records["latest_record"]["signal"]["active"] is strategy_run["signals"][
        "latest_signal_active"
    ]
    assert [item["signal"]["active"] for item in signal_records["records"]] == [
        False,
        True,
        False,
        True,
    ]
    assert [item["entry"] for item in signal_records["records"]] == [False, True, False, True]
    assert [item["exit"] for item in signal_records["records"]] == [False, False, True, False]
    assert signal_records["records"][1]["indicator_context"]["short_sma"] == 102.0
    assert signal_records["records"][1]["indicator_context"]["long_sma"] == 101.0
    assert signal_records["latest_record"]["indicator_context"]["trend_spread_pct"] == pytest.approx(
        0.970874,
        abs=0.000001,
    )
    json.dumps(signal_records)


def test_strategy_signal_records_cover_no_signal_state() -> None:
    definition = get_strategy_definition("bollinger_rsi_reversion")
    assert definition is not None
    rows = [
        _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
        _record(open_time="2026-06-02T00:00:00Z", close=101, volume=11),
        _record(open_time="2026-06-03T00:00:00Z", close=100, volume=12),
        _record(open_time="2026-06-04T00:00:00Z", close=101, volume=13),
        _record(open_time="2026-06-05T00:00:00Z", close=100, volume=14),
        _record(open_time="2026-06-06T00:00:00Z", close=101, volume=15),
    ]
    strategy = {
        "name": "bollinger_rsi_reversion",
        "params": {
            "bollinger_window": 3,
            "band_std": 1.0,
            "rsi_window": 3,
            "rsi_oversold": 35,
            "rsi_overbought": 65,
            "trend_window": 3,
            "trend_filter_pct": 50,
        },
    }

    signal_records = definition.signal_records(strategy, _view(rows), rows)

    assert signal_records["status"] == "succeeded"
    assert signal_records["active_count"] == 0
    assert signal_records["entry_count"] == 0
    assert signal_records["exit_count"] == 0
    assert all(item["signal"]["active"] is False for item in signal_records["records"])
    assert signal_records["latest_record"]["indicator_context"]["strong_trend_direction"] == "none"
    assert "bollinger_middle" in signal_records["latest_record"]["indicator_context"]
    assert "rsi" in signal_records["latest_record"]["indicator_context"]
    json.dumps(signal_records)


def test_strategy_signal_records_cover_insufficient_data() -> None:
    definition = get_strategy_definition("breakout_atr_trend")
    assert definition is not None
    rows = [
        _record(open_time="2026-06-05T00:00:00Z", close=104, volume=14),
        _record(open_time="2026-06-06T00:00:00Z", close=110, volume=20),
    ]
    strategy = {
        "name": "breakout_atr_trend",
        "params": {
            "breakout_window": 3,
            "exit_window": 2,
            "atr_window": 3,
        },
    }

    signal_records = definition.signal_records(strategy, _view(rows), rows)

    assert signal_records["status"] == "insufficient_data"
    assert signal_records["records"] == []
    assert signal_records["latest_record"] is None
    assert signal_records["entry_count"] == 0
    assert signal_records["exit_count"] == 0
    assert signal_records["active_count"] == 0
    assert signal_records["warnings"][0]["code"] == "insufficient_ohlcv_rows"
    json.dumps(signal_records)


def _run_pipeline_with_strategies(
    config: dict[str, Any],
    config_path: Path,
    *,
    until_stage: str = "run_strategy_research",
):
    return run_pipeline(
        config,
        config_path=config_path,
        until_stage=until_stage,
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


def _write_signed_tsmom_strategy_config(
    tmp_path: Path,
    *,
    lookback: int,
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
    - name: signed_tsmom_trend
      enabled: true
      params:
        return_window: 1
        deadband_pct: 0.5
      backtest:
        enabled: true
        initial_cash: 10000
        fees_bps: 10
        slippage_bps: 5
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


def _write_sma_cross_long_short_strategy_config(
    tmp_path: Path,
    *,
    lookback: int,
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
    - name: sma_cross_long_short
      enabled: true
      params:
        short_window: 1
        long_window: 2
        neutral_band_pct: 0.5
      backtest:
        enabled: true
        initial_cash: 10000
        fees_bps: 10
        slippage_bps: 5
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


def _write_bollinger_rsi_long_short_strategy_config(
    tmp_path: Path,
    *,
    lookback: int,
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
    - name: bollinger_rsi_long_short
      enabled: true
      params:
        bollinger_window: 2
        band_std: 0.5
        rsi_window: 1
        rsi_oversold: 35
        rsi_overbought: 65
        trend_window: 2
        trend_filter_pct: 50
      backtest:
        enabled: true
        initial_cash: 10000
        fees_bps: 10
        slippage_bps: 5
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


def _write_targeted_matrix_strategy_config(tmp_path: Path) -> Path:
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
    - ETHUSDT
  ohlcv:
    storage_dir: data/market/ohlcv
    timeframes:
      - 1d
      - 4h
    lookback:
      1d: 3
      4h: 3
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
      targeted_params:
        - source: binance
          symbol: BTCUSDT
          timeframe: 1d
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
    - name: signed_tsmom_trend
      enabled: true
      params:
        return_window: 2
        deadband_pct: 1.0
      targeted_params:
        - source: binance
          symbol: BTCUSDT
          timeframe: 4h
          params:
            return_window: 1
            deadband_pct: 0.0
      backtest:
        enabled: true
        initial_cash: 10000
        fees_bps: 10
        slippage_bps: 5
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


def _write_sma_cross_strategy_config(
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
    - name: sma_cross_trend
      enabled: true
      params:
        short_window: 2
        long_window: 3
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
    return _market_signals(result)


def _market_signals(result) -> dict[str, Any]:
    return json.loads((result.run.analysis_dir / "market_signals.json").read_text(encoding="utf-8"))


def _manifest(result) -> dict[str, Any]:
    return json.loads(result.run.manifest_path.read_text(encoding="utf-8"))


def _stage(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    for stage in manifest["stages"]:
        if stage["name"] == name:
            return stage
        for task in stage.get("tasks", []):
            if task["name"] == name:
                return task
    raise AssertionError(f"stage or task {name} not found")


def _noop_stage(config, run) -> list[str]:
    return []


def _engine() -> dict[str, Any]:
    return {
        "name": "vectorbt",
        "version": "test",
        "objects_exposed": False,
    }


def _bollinger_rsi_long_short_strategy(**params: Any) -> dict[str, Any]:
    strategy_params = {
        "bollinger_window": 2,
        "band_std": 0.5,
        "rsi_window": 1,
        "rsi_oversold": 35,
        "rsi_overbought": 65,
        "trend_window": 2,
        "trend_filter_pct": 50,
    }
    strategy_params.update(params)
    return {
        "name": "bollinger_rsi_long_short",
        "params": strategy_params,
        "backtest": {
            "enabled": True,
            "initial_cash": 10000,
            "fees_bps": 10,
            "slippage_bps": 5,
        },
    }


def _view(rows: list[dict[str, object]]) -> dict[str, object]:
    first = rows[0]["open_time"]
    latest = rows[-1]["open_time"]
    return {
        "view_id": f"ohlcv_view:binance:BTCUSDT:1d:{latest}",
        "source": "binance",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "requested_lookback": len(rows),
        "input_window_start": first,
        "input_window_end": latest,
        "latest_candle_time": latest,
    }


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
