from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from halpha.config import load_config
from halpha.pipeline import run_pipeline
from halpha.quant_signals import evaluate_market_strategy_signals
from halpha.storage import write_json


def test_quant_signals_build_from_strategy_run_artifact(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "sync_ohlcv": _noop_stage,
            "build_market_data_views": _noop_stage,
            "evaluate_quant_strategies": _write_strategy_runs_stage,
            "evaluate_market_strategy_signals": lambda config, run: evaluate_market_strategy_signals(
                config,
                run,
                now="2026-06-05T00:00:00Z",
            ),
            "build_market_signals": _noop_stage,
            "build_market_signal_material": _noop_stage,
            "build_market_regime_assessment": _noop_stage,
            "build_risk_assessment": _noop_stage,
            "build_decision_recommendations": _noop_stage,
            "build_watch_triggers": _noop_stage,
            "build_decision_intelligence_delta": _noop_stage,
            "build_analysis_materials": _noop_stage,
            "build_research_context": _noop_stage,
            "build_codex_context": _noop_stage,
            "run_codex_report": _noop_stage,
        },
    )

    artifact = _strategy_signals(result)
    signal = artifact["signals"][0]
    manifest = _manifest(result)

    assert result.succeeded is True
    assert artifact["artifact_type"] == "market_strategy_signals"
    assert artifact["source_artifacts"] == [
        "analysis/quant_strategy_runs.json",
        "raw/market_data_views.json",
    ]
    assert signal["strategy_signal_id"] == (
        "strategy_signal:tsmom_vol_scaled:binance:BTCUSDT:1d:2026-06-03T00:00:00Z"
    )
    assert signal["strategy_name"] == "tsmom_vol_scaled"
    assert signal["direction"] == "bullish"
    assert signal["strength"] == "medium"
    assert signal["confidence"] == "medium"
    assert signal["key_values"] == {
        "latest_close": 106.0,
        "return_window_pct": 6.0,
        "latest_return_pct": 2.912621,
        "realized_volatility_pct": 31.4,
        "target_volatility_pct": 20.0,
        "volatility_scaled_exposure": 0.64,
        "row_count": 3,
        "latest_regime": "risk_limited_momentum",
        "entry_count": 1,
        "exit_count": 0,
        "latest_signal_active": True,
        "backtest_diagnostic_status": "succeeded",
        "backtest_total_return_pct": 3.2,
        "backtest_max_drawdown_pct": -1.1,
        "backtest_trade_count": 1,
        "backtest_exposure_pct": 66.666667,
        "backtest_final_equity": 10320.0,
    }
    assert signal["evidence"] == ["return_window_pct is 6.0% over the configured return window."]
    assert signal["uncertainty"] == [
        "Strategy uses OHLCV close prices only and excludes text events.",
        "Realized volatility is elevated relative to the target volatility assumption.",
        "Historical backtest diagnostic is research material, not a forecast.",
    ]
    assert signal["insufficient_data"] is False
    assert signal["source_artifacts"] == [
        "analysis/quant_strategy_runs.json",
        "raw/market_data_views.json",
    ]
    assert manifest["artifacts"]["market_strategy_signals"] == "analysis/market_strategy_signals.json"
    assert manifest["counts"]["market_strategy_signals"] == 1
    assert manifest["counts"]["market_strategy_signals_insufficient_data"] == 0


def test_quant_signals_skip_when_quant_is_not_enabled(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, quant_enabled=False)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "sync_ohlcv": _noop_stage,
            "build_market_data_views": _noop_stage,
            "evaluate_quant_strategies": _noop_stage,
            "build_market_signals": _noop_stage,
            "build_market_signal_material": _noop_stage,
            "build_analysis_materials": _noop_stage,
            "build_research_context": _noop_stage,
            "build_codex_context": _noop_stage,
            "run_codex_report": _noop_stage,
        },
    )

    manifest = _manifest(result)
    assert result.succeeded is True
    assert not (result.run.analysis_dir / "market_strategy_signals.json").exists()
    assert "market_strategy_signals" not in manifest["artifacts"]
    assert manifest["counts"]["market_strategy_signals"] == 0
    assert _stage(manifest, "evaluate_market_strategy_signals")["artifacts"] == []


def test_quant_signals_fail_when_strategy_runs_are_missing(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "sync_ohlcv": _noop_stage,
            "build_market_data_views": _noop_stage,
            "evaluate_quant_strategies": _noop_stage,
            "build_market_signals": _noop_stage,
            "build_market_signal_material": _noop_stage,
            "build_analysis_materials": _noop_stage,
            "build_research_context": _noop_stage,
            "build_codex_context": _noop_stage,
            "run_codex_report": _noop_stage,
        },
    )

    manifest = _manifest(result)
    assert result.succeeded is False
    assert result.failed_stage == "evaluate_market_strategy_signals"
    assert result.reason == (
        "analysis/quant_strategy_runs.json was not found; evaluate_quant_strategies must run first."
    )
    assert _stage(manifest, "evaluate_market_strategy_signals")["status"] == "failed"


def _write_config(tmp_path: Path, *, quant_enabled: bool = True) -> Path:
    quant_block = (
        """
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
""".strip()
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
      1d: 3
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


def _write_strategy_runs_stage(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "quant_strategy_runs.json",
        {
            "schema_version": 1,
            "artifact_type": "quant_strategy_runs",
            "created_at": "2026-06-05T00:00:00Z",
            "engine": {
                "name": "vectorbt",
                "version": "1.0.0",
                "objects_exposed": False,
            },
            "source_artifacts": ["raw/market_data_views.json"],
            "runs": [_strategy_run()],
        },
    )
    run.manifest["artifacts"]["quant_strategy_runs"] = "analysis/quant_strategy_runs.json"
    run.manifest["counts"]["quant_strategy_runs"] = 1
    return ["analysis/quant_strategy_runs.json"]


def _strategy_run() -> dict[str, Any]:
    return {
        "strategy_run_id": "quant_strategy_run:tsmom_vol_scaled:binance:BTCUSDT:1d:2026-06-03T00:00:00Z",
        "status": "succeeded",
        "strategy_name": "tsmom_vol_scaled",
        "strategy_version": 1,
        "engine": {"name": "vectorbt", "version": "1.0.0"},
        "source": "binance",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "input_view_id": "ohlcv_view:binance:BTCUSDT:1d:2026-06-03T00:00:00Z",
        "input_window_start": "2026-06-01T00:00:00Z",
        "input_window_end": "2026-06-03T00:00:00Z",
        "latest_candle_time": "2026-06-03T00:00:00Z",
        "params": {
            "return_window": 2,
            "volatility_window": 2,
            "target_volatility": 0.2,
        },
        "data_quality": {
            "row_count": 3,
            "requested_lookback": 3,
            "minimum_required_rows": 3,
            "sufficient_data": True,
            "missing_row_policy": "do_not_fabricate",
            "warnings": [],
        },
        "indicators": {
            "latest_close": 106.0,
            "return_window_pct": 6.0,
            "latest_return_pct": 2.912621,
            "realized_volatility_pct": 31.4,
            "target_volatility_pct": 20.0,
            "volatility_scaled_exposure": 0.64,
            "row_count": 3,
        },
        "signals": {
            "latest_regime": "risk_limited_momentum",
            "entry_count": 1,
            "exit_count": 0,
            "latest_signal_active": True,
        },
        "backtest_diagnostic": {
            "enabled": True,
            "status": "succeeded",
            "metrics": {
                "calculation_backend": "vectorbt.Portfolio.from_signals",
                "total_return_pct": 3.2,
                "max_drawdown_pct": -1.1,
                "trade_count": 1,
                "exposure_pct": 66.666667,
                "final_equity": 10320.0,
            },
            "warnings": ["Historical backtest diagnostic is research material, not a forecast."],
        },
        "parameter_diagnostic": {
            "enabled": False,
            "status": "disabled",
        },
        "assessment": {
            "direction": "bullish",
            "strength": "medium",
            "confidence": "medium",
            "summary": "Positive time-series momentum is present.",
            "evidence": ["return_window_pct is 6.0% over the configured return window."],
            "uncertainty": ["Strategy uses OHLCV close prices only and excludes text events."],
        },
        "warnings": [
            {
                "severity": "warning",
                "code": "high_realized_volatility",
                "message": "Realized volatility is elevated relative to the target volatility assumption.",
                "source": "strategy",
            }
        ],
        "error": None,
        "source_artifacts": ["raw/market_data_views.json"],
        "created_at": "2026-06-05T00:00:00Z",
    }


def _strategy_signals(result) -> dict[str, Any]:
    return json.loads((result.run.analysis_dir / "market_strategy_signals.json").read_text(encoding="utf-8"))


def _manifest(result) -> dict[str, Any]:
    return json.loads(result.run.manifest_path.read_text(encoding="utf-8"))


def _stage(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    return next(stage for stage in manifest["stages"] if stage["name"] == name)


def _noop_stage(config, run) -> list[str]:
    return []
