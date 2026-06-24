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
    assert market_signals["source_artifacts"] == [
        "analysis/quant_strategy_runs.json",
        "raw/market_data_views.json",
    ]
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
        "key_values": {
            "latest_close": 106.0,
            "row_count": 3,
            "requested_lookback": 3,
            "minimum_required_rows": 3,
            "backtest_diagnostic_status": "disabled",
        },
        "evidence": ["return_window_pct is 6.0% over the configured return window."],
        "uncertainty": ["Strategy uses OHLCV close prices only and excludes text events."],
        "insufficient_data": False,
        "source_artifacts": [
            "analysis/quant_strategy_runs.json",
            "raw/market_data_views.json",
        ],
        "created_at": "2026-06-05T00:00:00Z",
    }
    assert "strategy_signal_id" not in signal
    assert "artifact_type: analysis_market_signal_material" in material
    assert "raw_ohlcv_history_embedded: false" in material
    assert "backtest_diagnostics_are_historical_research_material: true" in material
    assert "backtest_diagnostics_are_forecasts: false" in material
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


def test_market_signal_material_includes_quant_overview_matrix_conflicts_and_guidance(
    tmp_path: Path,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = _run_pipeline_with_representative_strategy_runs(config, config_path)

    material = (result.run.analysis_dir / "market_signal_material.md").read_text(encoding="utf-8")
    manifest = _manifest(result)

    assert result.succeeded is True
    assert "## quant_overview" in material
    assert "normalized_market_signal_artifact: analysis/market_signals.json" in material
    assert "quant_strategy_runs_artifact: analysis/quant_strategy_runs.json" in material
    assert "strategy_run_status_counts:" in material
    assert "succeeded: 4" in material
    assert "insufficient_data: 1" in material
    assert "## strategy_matrix" in material
    assert "strategy_name: tsmom_vol_scaled" in material
    assert "strategy_name: bollinger_rsi_reversion" in material
    assert "strategy_name: breakout_atr_trend" in material
    assert "## confluence_and_conflict" in material
    assert "confluence_group_count: 1" in material
    assert "conflict_group_count: 1" in material
    assert "group: binance:BTCUSDT:1d" in material
    assert "group: binance:ETHUSDT:1d" in material
    assert "## risk_and_uncertainty" in material
    assert "low_confidence_signals:" in material
    assert "insufficient_data_signals:" in material
    assert "## report_guidance" in material
    assert "high_confidence_signals:" in material
    assert "conflicting_signals:" in material
    assert "insufficient_data_signals:" in material
    assert "analysis/quant_strategy_runs.json" in material
    assert "analysis/market_signals.json" in material
    assert "raw_ohlcv_history_embedded: false" in material
    assert "open_time:" not in material
    assert "records:" not in material
    assert manifest["counts"]["market_signal_material_records"] == 5
    _assert_no_trading_language(material)


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
    assert signal["key_values"] == {
        "row_count": 1,
        "requested_lookback": 3,
        "minimum_required_rows": 3,
        "backtest_diagnostic_status": "disabled",
    }
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
            "evaluate_quant_strategies": _noop_stage,
            "evaluate_strategy_evaluation": _noop_stage,
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
        "analysis/quant_strategy_runs.json was not found; "
        "evaluate_quant_strategies must run first."
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
            "evaluate_quant_strategies": (
                lambda config, run: _write_quant_strategy_runs(
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


def _run_pipeline_with_representative_strategy_runs(config: dict[str, Any], config_path: Path):
    return run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "sync_ohlcv": _noop_stage,
            "build_market_data_views": _write_market_data_views,
            "evaluate_quant_strategies": _write_representative_quant_strategy_runs,
            "evaluate_strategy_evaluation": _noop_stage,
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


def _write_representative_quant_strategy_runs(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "quant_strategy_runs.json",
        {
            "schema_version": 1,
            "artifact_type": "quant_strategy_runs",
            "created_at": "2026-06-05T00:00:00Z",
            "engine": {"name": "vectorbt", "version": "0.28.0", "objects_exposed": False},
            "source_artifacts": ["raw/market_data_views.json"],
            "runs": [
                _strategy_run("tsmom_vol_scaled", "BTCUSDT", "succeeded", "bullish", "high"),
                _strategy_run("bollinger_rsi_reversion", "BTCUSDT", "succeeded", "bearish", "low"),
                _strategy_run("tsmom_vol_scaled", "ETHUSDT", "succeeded", "bullish", "high"),
                _strategy_run("breakout_atr_trend", "ETHUSDT", "succeeded", "bullish", "medium"),
                _strategy_run("breakout_atr_trend", "SOLUSDT", "insufficient_data", "unknown", "low"),
            ],
        },
    )
    run.manifest["artifacts"]["quant_strategy_runs"] = "analysis/quant_strategy_runs.json"
    run.manifest["counts"]["quant_strategy_runs"] = 5
    run.manifest["counts"]["quant_strategy_runs_succeeded"] = 4
    run.manifest["counts"]["quant_strategy_runs_insufficient_data"] = 1
    return ["analysis/quant_strategy_runs.json"]


def _write_quant_strategy_runs(config, run, *, insufficient: bool) -> list[str]:
    strategy_run = {
        "strategy_run_id": "quant_strategy_run:tsmom_vol_scaled:binance:BTCUSDT:1d:2026-06-03T00:00:00Z",
        "status": "insufficient_data" if insufficient else "succeeded",
        "strategy_name": "tsmom_vol_scaled",
        "source": "binance",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "input_view_id": "ohlcv_view:binance:BTCUSDT:1d:2026-06-03T00:00:00Z",
        "input_window_start": "2026-06-01T00:00:00Z",
        "input_window_end": "2026-06-03T00:00:00Z",
        "latest_candle_time": "2026-06-03T00:00:00Z",
        "data_quality": {
            "row_count": 1 if insufficient else 3,
            "requested_lookback": 3,
            "minimum_required_rows": 3,
            "sufficient_data": not insufficient,
            "missing_row_policy": "do_not_fabricate",
            "warnings": [],
        },
        "indicators": {} if insufficient else {"latest_close": 106.0, "row_count": 3},
        "signals": {},
        "backtest_diagnostic": {"enabled": False, "status": "disabled"},
        "parameter_diagnostic": {"enabled": False, "status": "disabled"},
        "assessment": {
            "direction": "unknown" if insufficient else "bullish",
            "strength": "unknown" if insufficient else "medium",
            "confidence": "low" if insufficient else "medium",
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
        },
        "warnings": [],
        "error": None,
        "source_artifacts": ["raw/market_data_views.json"],
        "created_at": "2026-06-05T00:00:00Z",
    }
    write_json(
        run.analysis_dir / "quant_strategy_runs.json",
        {
            "schema_version": 1,
            "artifact_type": "quant_strategy_runs",
            "created_at": "2026-06-05T00:00:00Z",
            "engine": {"name": "vectorbt", "version": "0.28.0", "objects_exposed": False},
            "source_artifacts": ["raw/market_data_views.json"],
            "runs": [strategy_run],
        },
    )
    run.manifest["artifacts"]["quant_strategy_runs"] = "analysis/quant_strategy_runs.json"
    run.manifest["counts"]["quant_strategy_runs"] = 1
    run.manifest["counts"]["quant_strategy_runs_succeeded"] = 0 if insufficient else 1
    run.manifest["counts"]["quant_strategy_runs_insufficient_data"] = int(insufficient)
    return ["analysis/quant_strategy_runs.json"]


def _strategy_run(
    strategy_name: str,
    symbol: str,
    status: str,
    direction: str,
    confidence: str,
) -> dict[str, Any]:
    return {
        "strategy_run_id": f"quant_strategy_run:{strategy_name}:binance:{symbol}:1d:2026-06-03T00:00:00Z",
        "status": status,
        "strategy_name": strategy_name,
        "source": "binance",
        "symbol": symbol,
        "timeframe": "1d",
        "input_view_id": f"ohlcv_view:binance:{symbol}:1d:2026-06-03T00:00:00Z",
        "input_window_start": "2026-06-01T00:00:00Z",
        "input_window_end": "2026-06-03T00:00:00Z",
        "latest_candle_time": "2026-06-03T00:00:00Z",
        "assessment": {
            "direction": direction,
            "strength": "medium" if direction != "unknown" else "unknown",
            "confidence": confidence,
            "evidence": [f"{strategy_name} evidence summary for {symbol}."],
            "uncertainty": [f"{strategy_name} uncertainty summary for {symbol}."],
        },
        "warnings": [],
        "source_artifacts": ["raw/market_data_views.json"],
        "created_at": "2026-06-05T00:00:00Z",
    }


def _market_signals(result) -> dict[str, Any]:
    return json.loads((result.run.analysis_dir / "market_signals.json").read_text(encoding="utf-8"))


def _manifest(result) -> dict[str, Any]:
    return json.loads(result.run.manifest_path.read_text(encoding="utf-8"))


def _stage(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    return next(
        task
        for stage in manifest["stages"]
        for task in stage.get("tasks", [])
        if task["name"] == name
    )


def _noop_stage(config, run) -> list[str]:
    return []


def _assert_no_trading_language(*artifacts: Any) -> None:
    text = json.dumps(artifacts, ensure_ascii=False).lower()
    forbidden = [
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
