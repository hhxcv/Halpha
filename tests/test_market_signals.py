from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from halpha.config import load_config
from halpha.pipeline import run_pipeline
from halpha.storage import write_json


def test_market_signals_normalize_strategy_outputs_and_write_material(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = _run_pipeline_with_strategy_outputs(config, config_path)

    market_signals = _market_signals(result)
    material = (result.run.analysis_dir / "market_signal_material.md").read_text(encoding="utf-8")
    manifest = _manifest(result)
    signal = market_signals["signals"][0]
    assert result.succeeded is True
    assert market_signals["artifact_type"] == "market_signals"
    assert market_signals["source_artifacts"] == ["analysis/market_strategy_signals.json"]
    assert signal == {
        "signal_id": "market_signal:tsmom_vol_scaled:binance:BTCUSDT:1d:2026-06-03T00:00:00Z",
        "strategy_name": "tsmom_vol_scaled",
        "source": "binance",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "input_window_start": "2026-06-01T00:00:00Z",
        "input_window_end": "2026-06-03T00:00:00Z",
        "latest_candle_time": "2026-06-03T00:00:00Z",
        "direction": "bullish",
        "strength": "medium",
        "confidence": "medium",
        "key_values": {"latest_close": 106.0, "row_count": 3},
        "evidence": ["return_window_pct is 6.0% over the configured return window."],
        "uncertainty": ["Strategy uses OHLCV close prices only and excludes text events."],
        "insufficient_data": False,
        "source_artifacts": [
            "analysis/market_strategy_signals.json",
            "raw/market_data_views.json",
        ],
        "created_at": "2026-06-05T00:00:00Z",
    }
    assert "strategy_signal_id" not in signal
    assert "artifact_type: analysis_market_signal_material" in material
    assert "raw_ohlcv_history_embedded: false" in material
    assert "record_type: market_signal" in material
    assert "signal_id: market_signal:tsmom_vol_scaled:binance:BTCUSDT:1d:2026-06-03T00:00:00Z" in material
    assert "input_window_start: '2026-06-01T00:00:00Z'" in material
    assert "latest_close: 106.0" in material
    assert "return_window_pct is 6.0% over the configured return window." in material
    assert "Strategy uses OHLCV close prices only and excludes text events." in material
    assert "raw/market_data_views.json" in material
    assert "open_time:" not in material
    assert "records:" not in material
    assert manifest["artifacts"]["market_signals"] == "analysis/market_signals.json"
    assert manifest["artifacts"]["market_signal_material"] == "analysis/market_signal_material.md"
    assert manifest["counts"]["market_signals"] == 1
    assert manifest["counts"]["market_signals_insufficient_data"] == 0
    assert manifest["counts"]["market_signal_material_records"] == 1
    assert _stage(manifest, "build_market_signals")["artifacts"] == [
        "analysis/market_signals.json"
    ]
    assert _stage(manifest, "build_market_signal_material")["artifacts"] == [
        "analysis/market_signal_material.md"
    ]
    _assert_no_trading_language(market_signals, material)


def test_market_signals_preserve_insufficient_signal_state(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = _run_pipeline_with_strategy_outputs(config, config_path, insufficient=True)

    market_signals = _market_signals(result)
    signal = market_signals["signals"][0]
    manifest = _manifest(result)
    assert signal["direction"] == "unknown"
    assert signal["strength"] == "unknown"
    assert signal["confidence"] == "low"
    assert signal["key_values"] == {"requested_lookback": 3, "row_count": 1}
    assert signal["evidence"] == ["input view has 1 OHLCV rows for requested_lookback 3."]
    assert signal["uncertainty"] == ["binance BTCUSDT 1d has insufficient OHLCV rows."]
    assert signal["insufficient_data"] is True
    assert manifest["counts"]["market_signals_insufficient_data"] == 1
    _assert_no_trading_language(market_signals)


def test_market_signal_artifacts_skip_when_quant_is_not_enabled(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, quant_enabled=False)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "build_analysis_materials": _noop_stage,
            "build_research_context": _noop_stage,
            "build_codex_context": _noop_stage,
            "run_codex_report": _noop_stage,
        },
    )

    manifest = _manifest(result)
    assert result.succeeded is True
    assert not (result.run.analysis_dir / "market_signals.json").exists()
    assert not (result.run.analysis_dir / "market_signal_material.md").exists()
    assert "market_signals" not in manifest["artifacts"]
    assert "market_signal_material" not in manifest["artifacts"]
    assert manifest["counts"]["market_signals"] == 0
    assert manifest["counts"]["market_signals_insufficient_data"] == 0
    assert manifest["counts"]["market_signal_material_records"] == 0
    assert _stage(manifest, "build_market_signals")["artifacts"] == []
    assert _stage(manifest, "build_market_signal_material")["artifacts"] == []


def test_market_signals_fail_when_strategy_outputs_are_missing(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "sync_ohlcv": _noop_stage,
            "build_market_data_views": _write_market_data_views,
            "evaluate_market_strategy_signals": _noop_stage,
            "build_analysis_materials": _noop_stage,
            "build_research_context": _noop_stage,
            "build_codex_context": _noop_stage,
            "run_codex_report": _noop_stage,
        },
    )

    manifest = _manifest(result)
    assert result.succeeded is False
    assert result.failed_stage == "build_market_signals"
    assert result.reason == (
        "analysis/market_strategy_signals.json was not found; "
        "evaluate_market_strategy_signals must run first."
    )
    assert not (result.run.analysis_dir / "market_signals.json").exists()
    assert _stage(manifest, "build_market_signals")["status"] == "failed"


def _run_pipeline_with_strategy_outputs(
    config: dict[str, Any],
    config_path: Path,
    *,
    insufficient: bool = False,
):
    return run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "sync_ohlcv": _noop_stage,
            "build_market_data_views": _write_market_data_views,
            "evaluate_market_strategy_signals": (
                lambda config, run: _write_strategy_signals(
                    config,
                    run,
                    insufficient=insufficient,
                )
            ),
            "build_analysis_materials": _noop_stage,
            "build_research_context": _noop_stage,
            "build_codex_context": _noop_stage,
            "run_codex_report": _noop_stage,
        },
    )


def _write_config(tmp_path: Path, *, quant_enabled: bool = True) -> Path:
    ohlcv_block = (
        """
  ohlcv:
    storage_dir: data/market/ohlcv
    timeframes:
      - 1d
    lookback:
      1d: 3
"""
        if quant_enabled
        else ""
    )
    quant_block = (
        """
quant:
  enabled: true
  engine: vectorbt
  strategies:
    - name: tsmom_vol_scaled
"""
        if quant_enabled
        else """
quant:
  enabled: false
"""
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
{ohlcv_block.rstrip()}
{quant_block.rstrip()}
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


def _write_market_data_views(config, run) -> list[str]:
    write_json(
        run.raw_dir / "market_data_views.json",
        {
            "schema_version": 1,
            "artifact_type": "market_data_views",
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["data/market/metadata/ohlcv_sync_state.json"],
            "views": [
                {
                    "view_id": "ohlcv_view:binance:BTCUSDT:1d:2026-06-03T00:00:00Z",
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "requested_lookback": 3,
                    "input_window_start": "2026-06-01T00:00:00Z",
                    "input_window_end": "2026-06-03T00:00:00Z",
                    "latest_candle_time": "2026-06-03T00:00:00Z",
                    "row_count": 3,
                    "storage_ref": "data/market/ohlcv/source=binance/symbol=BTCUSDT/timeframe=1d",
                    "included_columns": ["open_time", "open", "high", "low", "close", "volume"],
                    "insufficient_data": False,
                    "warnings": [],
                }
            ],
        },
    )
    run.manifest["artifacts"]["market_data_views"] = "raw/market_data_views.json"
    run.manifest["counts"]["market_data_views"] = 1
    run.manifest["counts"]["market_data_views_insufficient_data"] = 0
    return ["raw/market_data_views.json"]


def _write_strategy_signals(config, run, *, insufficient: bool) -> list[str]:
    key_values = (
        {"requested_lookback": 3, "row_count": 1}
        if insufficient
        else {"latest_close": 106.0, "row_count": 3}
    )
    signal = {
        "strategy_signal_id": "strategy_signal:tsmom_vol_scaled:binance:BTCUSDT:1d:2026-06-03T00:00:00Z",
        "strategy_name": "tsmom_vol_scaled",
        "source": "binance",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "input_view_id": "ohlcv_view:binance:BTCUSDT:1d:2026-06-03T00:00:00Z",
        "input_window_start": "2026-06-01T00:00:00Z",
        "input_window_end": "2026-06-03T00:00:00Z",
        "latest_candle_time": "2026-06-03T00:00:00Z",
        "direction": "unknown" if insufficient else "bullish",
        "strength": "unknown" if insufficient else "medium",
        "confidence": "low" if insufficient else "medium",
        "key_values": key_values,
        "evidence": (
            ["input view has 1 OHLCV rows for requested_lookback 3."]
            if insufficient
            else ["return_window_pct is 6.0% over the configured return window."]
        ),
        "uncertainty": (
            ["binance BTCUSDT 1d has insufficient OHLCV rows."]
            if insufficient
            else ["Strategy uses OHLCV close prices only and excludes text events."]
        ),
        "insufficient_data": insufficient,
        "source_artifacts": ["raw/market_data_views.json"],
        "created_at": "2026-06-05T00:00:00Z",
    }
    write_json(
        run.analysis_dir / "market_strategy_signals.json",
        {
            "schema_version": 1,
            "artifact_type": "market_strategy_signals",
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["raw/market_data_views.json"],
            "signals": [signal],
        },
    )
    run.manifest["artifacts"]["market_strategy_signals"] = "analysis/market_strategy_signals.json"
    run.manifest["counts"]["market_strategy_signals"] = 1
    run.manifest["counts"]["market_strategy_signals_insufficient_data"] = int(insufficient)
    return ["analysis/market_strategy_signals.json"]


def _market_signals(result) -> dict[str, Any]:
    return json.loads((result.run.analysis_dir / "market_signals.json").read_text(encoding="utf-8"))


def _manifest(result) -> dict[str, Any]:
    return json.loads(result.run.manifest_path.read_text(encoding="utf-8"))


def _stage(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    return next(stage for stage in manifest["stages"] if stage["name"] == name)


def _noop_stage(config, run) -> list[str]:
    return []


def _assert_no_trading_language(*artifacts: Any) -> None:
    text = json.dumps(artifacts, ensure_ascii=False).lower()
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
