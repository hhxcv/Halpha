from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from halpha.config import load_config
from halpha.ohlcv_store import OHLCVParquetStore
from halpha.pipeline import run_pipeline
from halpha.quant_signals import evaluate_market_strategy_signals


def test_quant_signals_write_initial_strategy_artifact(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, signals=["trend", "momentum"], lookback=3)
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
            _record(open_time="2026-06-02T00:00:00Z", close=103, volume=11),
            _record(open_time="2026-06-03T00:00:00Z", close=106, volume=12),
        ]
    )

    result = _run_pipeline_with_signals(config, config_path)

    artifact = _strategy_signals(result)
    manifest = _manifest(result)
    signals = artifact["signals"]
    trend = _signal(signals, "trend")
    momentum = _signal(signals, "momentum")

    assert result.succeeded is True
    assert artifact["artifact_type"] == "market_strategy_signals"
    assert artifact["source_artifacts"] == ["raw/market_data_views.json"]
    assert [signal["strategy_name"] for signal in signals] == ["trend", "momentum"]
    assert trend["strategy_signal_id"] == (
        "strategy_signal:trend:binance:BTCUSDT:1d:2026-06-03T00:00:00Z"
    )
    assert trend["source"] == "binance"
    assert trend["symbol"] == "BTCUSDT"
    assert trend["timeframe"] == "1d"
    assert trend["input_window_start"] == "2026-06-01T00:00:00Z"
    assert trend["input_window_end"] == "2026-06-03T00:00:00Z"
    assert trend["latest_candle_time"] == "2026-06-03T00:00:00Z"
    assert trend["direction"] == "bullish"
    assert trend["strength"] == "medium"
    assert trend["confidence"] == "medium"
    assert trend["insufficient_data"] is False
    assert trend["key_values"]["latest_close"] == 106.0
    assert trend["key_values"]["moving_average_short"] == 104.5
    assert trend["key_values"]["moving_average_long"] == 103.0
    assert trend["evidence"]
    assert trend["uncertainty"]
    assert momentum["direction"] == "bullish"
    assert momentum["key_values"]["window_return_pct"] == 6.0
    assert manifest["artifacts"]["market_strategy_signals"] == (
        "analysis/market_strategy_signals.json"
    )
    assert manifest["counts"]["market_strategy_signals"] == 2
    assert manifest["counts"]["market_strategy_signals_insufficient_data"] == 0
    assert _stage(manifest, "evaluate_market_strategy_signals")["artifacts"] == [
        "analysis/market_strategy_signals.json"
    ]
    _assert_no_trading_language(artifact)


def test_quant_signals_emit_all_configured_initial_signal_types(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        signals=["trend", "momentum", "volatility", "volume_anomaly"],
        lookback=4,
    )
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
            _record(open_time="2026-06-02T00:00:00Z", close=101, volume=10),
            _record(open_time="2026-06-03T00:00:00Z", close=103, volume=10),
            _record(open_time="2026-06-04T00:00:00Z", close=106, volume=30),
        ]
    )

    result = _run_pipeline_with_signals(config, config_path)

    artifact = _strategy_signals(result)
    assert [signal["strategy_name"] for signal in artifact["signals"]] == [
        "trend",
        "momentum",
        "volatility",
        "volume_anomaly",
    ]
    assert _signal(artifact["signals"], "volatility")["direction"] == "unknown"
    assert _signal(artifact["signals"], "volume_anomaly")["key_values"]["volume_ratio"] == 3.0
    _assert_no_trading_language(artifact)


def test_quant_signals_record_risk_and_activity_values(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        signals=["volatility", "volume_anomaly"],
        lookback=4,
    )
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(
                open_time="2026-06-01T00:00:00Z",
                close=100,
                high=101,
                low=99,
                volume=10,
            ),
            _record(
                open_time="2026-06-02T00:00:00Z",
                close=100,
                high=102,
                low=98,
                volume=10,
            ),
            _record(
                open_time="2026-06-03T00:00:00Z",
                close=100,
                high=103,
                low=97,
                volume=10,
            ),
            _record(
                open_time="2026-06-04T00:00:00Z",
                close=100,
                high=104,
                low=96,
                volume=30,
            ),
        ]
    )

    result = _run_pipeline_with_signals(config, config_path)

    artifact = _strategy_signals(result)
    signals = artifact["signals"]
    volatility = _signal(signals, "volatility")
    volume_anomaly = _signal(signals, "volume_anomaly")
    assert [signal["strategy_name"] for signal in signals] == ["volatility", "volume_anomaly"]
    assert volatility["source"] == "binance"
    assert volatility["symbol"] == "BTCUSDT"
    assert volatility["timeframe"] == "1d"
    assert volatility["input_window_start"] == "2026-06-01T00:00:00Z"
    assert volatility["input_window_end"] == "2026-06-04T00:00:00Z"
    assert volatility["latest_candle_time"] == "2026-06-04T00:00:00Z"
    assert volatility["key_values"]["return_std_pct"] == 0.0
    assert volatility["key_values"]["latest_range_pct"] == 8.0
    assert volatility["key_values"]["average_range_pct"] == 5.0
    assert volatility["key_values"]["max_range_pct"] == 8.0
    assert "latest_range_pct" in "\n".join(volatility["evidence"])
    assert volatility["confidence"] == "medium"
    assert volatility["uncertainty"]
    assert volume_anomaly["key_values"]["volume_ratio"] == 3.0
    assert volume_anomaly["key_values"]["volume_change_pct"] == 200.0
    assert "volume_change_pct" in "\n".join(volume_anomaly["evidence"])
    assert volume_anomaly["direction"] == "unknown"
    assert volume_anomaly["strength"] == "high"
    assert volume_anomaly["uncertainty"]
    _assert_no_trading_language(artifact)


def test_quant_signals_record_unsupported_configured_signal_without_fabrication(
    tmp_path: Path,
) -> None:
    config_path = _write_config(tmp_path, signals=["trend"], lookback=2)
    config = load_config(config_path)
    config["quant"]["signals"] = ["future_signal"]
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
            _record(open_time="2026-06-02T00:00:00Z", close=101, volume=11),
        ]
    )

    result = _run_pipeline_with_signals(config, config_path)

    artifact = _strategy_signals(result)
    signal = artifact["signals"][0]
    manifest = _manifest(result)
    assert signal["strategy_name"] == "future_signal"
    assert signal["direction"] == "unknown"
    assert signal["strength"] == "unknown"
    assert signal["confidence"] == "low"
    assert signal["insufficient_data"] is True
    assert signal["key_values"] == {"requested_lookback": 2, "row_count": 2}
    assert signal["evidence"] == [
        "input view has 2 OHLCV rows for requested_lookback 2."
    ]
    assert signal["uncertainty"] == [
        "future_signal is configured but not implemented in the initial evaluator set."
    ]
    assert manifest["counts"]["market_strategy_signals"] == 1
    assert manifest["counts"]["market_strategy_signals_insufficient_data"] == 1
    _assert_no_trading_language(artifact)


def test_quant_signals_record_insufficient_data_signal(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, signals=["trend", "momentum"], lookback=3)
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records([_record(open_time="2026-06-01T00:00:00Z", close=100, volume=10)])

    result = _run_pipeline_with_signals(config, config_path)

    artifact = _strategy_signals(result)
    manifest = _manifest(result)
    for signal in artifact["signals"]:
        assert signal["direction"] == "unknown"
        assert signal["strength"] == "unknown"
        assert signal["confidence"] == "low"
        assert signal["insufficient_data"] is True
        assert signal["key_values"] == {"requested_lookback": 3, "row_count": 1}
        assert signal["evidence"] == [
            "input view has 1 OHLCV rows for requested_lookback 3."
        ]
        assert signal["uncertainty"]
    assert manifest["counts"]["market_strategy_signals"] == 2
    assert manifest["counts"]["market_strategy_signals_insufficient_data"] == 2


def test_quant_signals_skip_when_quant_is_not_enabled(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, quant_enabled=False)
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=100, volume=10),
            _record(open_time="2026-06-02T00:00:00Z", close=101, volume=10),
        ]
    )

    result = _run_pipeline_with_signals(config, config_path)

    manifest = _manifest(result)
    assert result.succeeded is True
    assert not (result.run.analysis_dir / "market_strategy_signals.json").exists()
    assert "market_strategy_signals" not in manifest["artifacts"]
    assert manifest["counts"]["market_strategy_signals"] == 0
    assert _stage(manifest, "evaluate_market_strategy_signals")["artifacts"] == []


def test_quant_signals_fail_when_data_views_are_missing(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, signals=["trend"], lookback=2)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "sync_ohlcv": _noop_stage,
            "build_market_data_views": _noop_stage,
            "build_analysis_materials": _noop_stage,
            "build_research_context": _noop_stage,
            "build_codex_context": _noop_stage,
            "run_codex_report": _noop_stage,
        },
    )

    manifest = _manifest(result)
    assert result.succeeded is False
    assert result.failed_stage == "evaluate_market_strategy_signals"
    assert result.reason == "raw/market_data_views.json was not found; build_market_data_views must run first."
    assert _stage(manifest, "evaluate_market_strategy_signals")["status"] == "failed"


def _run_pipeline_with_signals(config: dict[str, Any], config_path: Path):
    return run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "sync_ohlcv": _noop_stage,
            "evaluate_market_strategy_signals": lambda config, run: evaluate_market_strategy_signals(
                config,
                run,
                now="2026-06-05T00:00:00Z",
            ),
            "build_analysis_materials": _noop_stage,
            "build_research_context": _noop_stage,
            "build_codex_context": _noop_stage,
            "run_codex_report": _noop_stage,
        },
    )


def _write_config(
    tmp_path: Path,
    *,
    signals: list[str] | None = None,
    lookback: int = 2,
    quant_enabled: bool = True,
) -> Path:
    signals = signals or ["trend"]
    quant_block = (
        "\n".join(["quant:", "  enabled: true", "  signals:", *[f"    - {signal}" for signal in signals]])
        if quant_enabled
        else "quant:\n  enabled: false"
    )
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
{quant_block}
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


def _strategy_signals(result) -> dict[str, Any]:
    return json.loads(
        (result.run.analysis_dir / "market_strategy_signals.json").read_text(encoding="utf-8")
    )


def _manifest(result) -> dict[str, Any]:
    return json.loads(result.run.manifest_path.read_text(encoding="utf-8"))


def _signal(signals: list[dict[str, Any]], strategy: str) -> dict[str, Any]:
    return next(signal for signal in signals if signal["strategy_name"] == strategy)


def _stage(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    return next(stage for stage in manifest["stages"] if stage["name"] == name)


def _noop_stage(config, run) -> list[str]:
    return []


def _assert_no_trading_language(artifact: dict[str, Any]) -> None:
    text = json.dumps(artifact, ensure_ascii=False).lower()
    forbidden = [
        "backtest",
        "buy",
        "calmar",
        "drawdown",
        "expected return",
        "sell",
        "order",
        "pnl",
        "portfolio",
        "position",
        "sharpe",
        "sortino",
        "entry",
        "exit",
        "investment recommendation",
        "win rate",
    ]
    assert not any(word in text for word in forbidden)


def _record(
    *,
    source: str = "binance",
    symbol: str = "BTCUSDT",
    timeframe: str = "1d",
    open_time: str,
    close: float,
    volume: float,
    high: float | None = None,
    low: float | None = None,
) -> dict[str, object]:
    return {
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "open_time": open_time,
        "open": close - 1,
        "high": close + 1 if high is None else high,
        "low": close - 2 if low is None else low,
        "close": close,
        "volume": volume,
        "fetched_at": "2026-06-05T00:00:00Z",
    }
