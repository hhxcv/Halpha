from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from halpha.config import load_config
from halpha.ohlcv_store import OHLCVParquetStore
from halpha.pipeline import run_pipeline


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
    assert strategy_run["indicators"]["latest_close"] == 109.0
    assert strategy_run["indicators"]["baseline_close"] == 104.0
    assert strategy_run["indicators"]["return_window_pct"] == 4.807692
    assert strategy_run["indicators"]["row_count"] == 5
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
    assert strategy_run["backtest_diagnostic"]["enabled"] is True
    assert strategy_run["backtest_diagnostic"]["status"] == "skipped"
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
    assert strategy_signal["key_values"]["backtest_diagnostic_status"] == "skipped"
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

    assert manifest["artifacts"]["quant_strategy_runs"] == "analysis/quant_strategy_runs.json"
    assert manifest["artifacts"]["market_strategy_signals"] == "analysis/market_strategy_signals.json"
    assert manifest["counts"]["quant_strategy_runs"] == 1
    assert manifest["counts"]["quant_strategy_runs_succeeded"] == 1
    assert manifest["counts"]["quant_strategy_runs_failed"] == 0
    assert manifest["counts"]["quant_strategy_runs_insufficient_data"] == 0
    assert manifest["counts"]["market_strategy_signals"] == 1
    assert manifest["quant_strategies"]["enabled"] == ["tsmom_vol_scaled"]
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


def _write_strategy_config(tmp_path: Path, *, lookback: int) -> Path:
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
        return_window: 2
        volatility_window: 2
        target_volatility: 0.2
      backtest:
        enabled: true
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
        "volume": volume,
        "fetched_at": "2026-06-05T00:00:00Z",
    }
