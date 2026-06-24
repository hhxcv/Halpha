from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from halpha.config import load_config
from halpha.market.ohlcv_store import OHLCVParquetStore
from halpha.pipeline import run_pipeline


def test_strategy_benchmark_suite_expands_configured_history_with_stable_order(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        symbols=["ETHUSDT", "BTCUSDT"],
        timeframes=["1h", "1d"],
    )
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(
                symbol="BTCUSDT",
                timeframe="1d",
                open_time="2026-06-01T00:00:00Z",
                close=100,
            ),
            _record(
                symbol="BTCUSDT",
                timeframe="1d",
                open_time="2026-06-02T00:00:00Z",
                close=101,
            ),
            _record(
                symbol="BTCUSDT",
                timeframe="1d",
                open_time="2026-06-03T00:00:00Z",
                close=102,
            ),
            _record(
                symbol="ETHUSDT",
                timeframe="1h",
                open_time="2026-06-05T00:00:00Z",
                close=50,
            ),
            _record(
                symbol="ETHUSDT",
                timeframe="1h",
                open_time="2026-06-05T01:00:00Z",
                close=51,
            ),
        ]
    )

    result = _run_until_benchmark_suite(config, config_path)

    artifact = _benchmark_suite(result)
    manifest = _manifest(result)
    records = artifact["benchmarks"]
    btc_1d = records[0]
    btc_1h = records[1]

    assert result.succeeded is True
    assert artifact["artifact_type"] == "strategy_benchmark_suite"
    assert artifact["selection_policy"] == {
        "source": "configured_symbols_timeframes_and_windows",
        "raw_ohlcv_history_embedded": False,
        "supported_window_selections": ["configured_lookback", "date_window", "latest_lookback"],
    }
    assert artifact["coverage"] == {
        "configured_symbols": ["BTCUSDT", "ETHUSDT"],
        "configured_timeframes": ["1d", "1h"],
        "configured_windows": ["configured_lookback"],
        "benchmark_records": 4,
        "succeeded": 2,
        "insufficient_data": 2,
        "failed": 0,
        "missing_history": 2,
        "total_window_rows": 4,
    }
    assert [record["benchmark_id"] for record in records] == [
        (
            "strategy_benchmark:binance:BTCUSDT:1d:configured_lookback:"
            "2026-06-02T00:00:00Z:2026-06-03T00:00:00Z"
        ),
        "strategy_benchmark:binance:BTCUSDT:1h:configured_lookback:missing:missing",
        "strategy_benchmark:binance:ETHUSDT:1d:configured_lookback:missing:missing",
        (
            "strategy_benchmark:binance:ETHUSDT:1h:configured_lookback:"
            "2026-06-05T00:00:00Z:2026-06-05T01:00:00Z"
        ),
    ]
    assert btc_1d == {
        "benchmark_id": records[0]["benchmark_id"],
        "status": "succeeded",
        "source": "binance",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "window_identity": "configured_lookback",
        "window_selection": "configured_lookback",
        "requested_lookback": 2,
        "minimum_rows": 2,
        "input_window_start": "2026-06-02T00:00:00Z",
        "input_window_end": "2026-06-03T00:00:00Z",
        "latest_candle_time": "2026-06-03T00:00:00Z",
        "row_count": 2,
        "history_row_count": 3,
        "storage_ref": "data/market/ohlcv/source=binance/symbol=BTCUSDT/timeframe=1d",
        "included_columns": ["open_time", "open", "high", "low", "close", "volume"],
        "source_artifacts": ["data/market/metadata/ohlcv_sync_state.json"],
        "warnings": [],
        "errors": [],
    }
    assert btc_1h["status"] == "insufficient_data"
    assert btc_1h["row_count"] == 0
    assert btc_1h["history_row_count"] == 0
    assert [item["code"] for item in btc_1h["warnings"]] == [
        "missing_local_history",
        "insufficient_benchmark_history",
    ]
    assert "records" not in btc_1d
    assert manifest["artifacts"]["strategy_benchmark_suite"] == "analysis/strategy_benchmark_suite.json"
    assert manifest["counts"]["strategy_benchmark_records"] == 4
    assert manifest["counts"]["strategy_benchmark_succeeded"] == 2
    assert manifest["counts"]["strategy_benchmark_insufficient_data"] == 2
    assert manifest["counts"]["strategy_benchmark_failed"] == 0
    assert manifest["strategy_benchmark_suite"]["missing_history"] == 2
    assert _stage(manifest, "build_strategy_benchmark_suite")["artifacts"] == [
        "analysis/strategy_benchmark_suite.json"
    ]


def test_strategy_benchmark_suite_supports_explicit_date_window(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        benchmark_suite_yaml="""
  benchmark_suite:
    enabled: true
    windows:
      - name: june_02_to_03
        selection: date_window
        start: 2026-06-02T00:00:00Z
        end: 2026-06-03T00:00:00Z
        minimum_rows: 2
""",
    )
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=100),
            _record(open_time="2026-06-02T00:00:00Z", close=101),
            _record(open_time="2026-06-03T00:00:00Z", close=102),
        ]
    )

    result = _run_until_benchmark_suite(config, config_path)

    record = _benchmark_suite(result)["benchmarks"][0]
    assert result.succeeded is True
    assert record["status"] == "succeeded"
    assert record["window_identity"] == "june_02_to_03"
    assert record["window_selection"] == "date_window"
    assert record["requested_lookback"] is None
    assert record["minimum_rows"] == 2
    assert record["input_window_start"] == "2026-06-02T00:00:00Z"
    assert record["input_window_end"] == "2026-06-03T00:00:00Z"
    assert record["row_count"] == 2
    assert record["history_row_count"] == 3
    assert record["warnings"] == []


def test_strategy_benchmark_suite_skips_when_quant_is_disabled(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, quant_enabled=False)
    config = load_config(config_path)

    result = _run_until_benchmark_suite(config, config_path)

    manifest = _manifest(result)
    assert result.succeeded is True
    assert not (result.run.analysis_dir / "strategy_benchmark_suite.json").exists()
    assert "strategy_benchmark_suite" not in manifest["artifacts"]
    assert manifest["counts"]["strategy_benchmark_records"] == 0
    assert manifest["strategy_benchmark_suite"] == {
        "enabled": False,
        "records": 0,
        "warnings": [],
        "errors": [],
    }
    assert _stage(manifest, "build_strategy_benchmark_suite")["artifacts"] == []


def _run_until_benchmark_suite(config: dict[str, Any], config_path: Path):
    return run_pipeline(
        config,
        config_path=config_path,
        until_stage="run_strategy_research",
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "sync_ohlcv": _noop_stage,
            "build_market_data_views": _noop_stage,
            "evaluate_quant_strategies": _noop_stage,
            "evaluate_strategy_evaluation": _noop_stage,
            "build_strategy_experiment_material": _noop_stage,
            "evaluate_market_strategy_signals": _noop_stage,
            "build_market_signals": _noop_stage,
            "build_market_signal_material": _noop_stage,
        },
    )


def _write_config(
    tmp_path: Path,
    *,
    symbols: list[str] | None = None,
    timeframes: list[str] | None = None,
    benchmark_suite_yaml: str = "",
    quant_enabled: bool = True,
) -> Path:
    config_path = tmp_path / "config.yaml"
    symbol_yaml = "\n".join(f"    - {symbol}" for symbol in (symbols or ["BTCUSDT"]))
    timeframe_values = timeframes or ["1d"]
    timeframe_yaml = "\n".join(f"      - {timeframe}" for timeframe in timeframe_values)
    lookback_yaml = "\n".join(f"      {timeframe}: 2" for timeframe in timeframe_values)
    strategy_yaml = (
        f"""
  engine: vectorbt
  strategies:
    - name: tsmom_vol_scaled
      enabled: true
      params:
        return_window: 2
        volatility_window: 2
        target_volatility: 0.2
{benchmark_suite_yaml.rstrip()}
"""
        if quant_enabled
        else ""
    )
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
{timeframe_yaml}
    lookback:
{lookback_yaml}
quant:
  enabled: {"true" if quant_enabled else "false"}
{strategy_yaml.rstrip()}
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


def _benchmark_suite(result) -> dict[str, Any]:
    return json.loads((result.run.analysis_dir / "strategy_benchmark_suite.json").read_text(encoding="utf-8"))


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
        "high": close + 1,
        "low": close - 2,
        "close": close,
        "volume": 10,
        "fetched_at": "2026-06-05T00:00:00Z",
    }
