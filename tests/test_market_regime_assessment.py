from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from halpha.config import load_config
from halpha.pipeline import run_pipeline
from halpha.storage import write_json


def test_market_regime_assessment_classifies_groups_and_records_evidence(tmp_path: Path) -> None:
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
            "evaluate_quant_strategies": _write_quant_strategy_runs,
            "evaluate_strategy_evaluation": _noop_stage,
            "evaluate_market_strategy_signals": _write_strategy_signals,
            "build_analysis_materials": _noop_stage,
            "build_research_context": _noop_stage,
            "build_codex_context": _noop_stage,
            "run_codex_report": _noop_stage,
        },
    )

    assert result.succeeded is True
    artifact = _market_regime_assessment(result)
    manifest = _manifest(result)

    assert artifact["artifact_type"] == "market_regime_assessment"
    assert artifact["schema_version"] == 1
    assert artifact["run_id"] == result.run.run_id
    assert artifact["created_at"] == "2026-06-05T00:00:00Z"
    assert artifact["source_artifacts"] == [
        "analysis/market_signals.json",
        "analysis/market_strategy_signals.json",
        "analysis/quant_strategy_runs.json",
        "raw/market_data_views.json",
    ]
    assert artifact["errors"] == []
    assert len(artifact["records"]) == 3

    btc = artifact["records"][0]
    eth = artifact["records"][1]
    sol = artifact["records"][2]
    assert btc["record_id"] == "market_regime:binance:BTCUSDT:1d:2026-06-03T00:00:00Z"
    assert btc["regime"] == "mixed"
    assert btc["confidence"] == "low"
    assert btc["status"] == "succeeded"
    assert btc["conflicts"]
    assert "direction_counts: bearish=1, bullish=1." in btc["evidence"]
    assert any("tsmom_vol_scaled" in item for item in btc["evidence"])
    assert btc["source_artifacts"] == [
        "analysis/market_signals.json",
        "analysis/market_strategy_signals.json",
        "analysis/quant_strategy_runs.json",
        "raw/market_data_views.json",
    ]

    assert eth["record_id"] == "market_regime:binance:ETHUSDT:1d:2026-06-03T00:00:00Z"
    assert eth["regime"] == "trend_up"
    assert eth["confidence"] == "high"
    assert eth["status"] == "succeeded"
    assert eth["conflicts"] == []
    assert "direction_counts: bullish=2." in eth["evidence"]
    assert any("risk_on_momentum" in item for item in eth["evidence"])

    assert sol["record_id"] == "market_regime:binance:SOLUSDT:1d:2026-06-03T00:00:00Z"
    assert sol["regime"] == "unknown"
    assert sol["confidence"] == "low"
    assert sol["status"] == "insufficient_data"
    assert sol["warnings"] == [
        "One or more upstream market signals have insufficient or weak evidence.",
        "No usable upstream market signal evidence was available.",
    ]
    assert "No usable market signal records were available." in sol["evidence"]
    assert artifact["warnings"] == sol["warnings"]
    assert manifest["artifacts"]["market_regime_assessment"] == "analysis/market_regime_assessment.json"
    assert manifest["counts"]["market_regime_records"] == 3
    assert manifest["counts"]["market_regime_unknown_records"] == 1
    assert _stage(manifest, "build_market_regime_assessment")["artifacts"] == [
        "analysis/market_regime_assessment.json"
    ]


def test_market_regime_assessment_writes_warning_without_fake_records_when_signals_are_empty(
    tmp_path: Path,
) -> None:
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
            "evaluate_quant_strategies": _write_quant_strategy_runs,
            "evaluate_strategy_evaluation": _noop_stage,
            "evaluate_market_strategy_signals": _noop_stage,
            "build_market_signals": _write_empty_market_signals,
            "build_market_signal_material": _noop_stage,
            "build_analysis_materials": _noop_stage,
            "build_research_context": _noop_stage,
            "build_codex_context": _noop_stage,
            "run_codex_report": _noop_stage,
        },
    )

    assert result.succeeded is True
    artifact = _market_regime_assessment(result)
    manifest = _manifest(result)
    assert artifact["records"] == []
    assert artifact["warnings"] == ["No market signal records were available for regime assessment."]
    assert artifact["errors"] == []
    assert manifest["counts"]["market_regime_records"] == 0
    assert manifest["counts"]["market_regime_unknown_records"] == 0


def test_market_regime_assessment_skips_when_quant_is_not_enabled(tmp_path: Path) -> None:
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
    assert not (result.run.analysis_dir / "market_regime_assessment.json").exists()
    assert "market_regime_assessment" not in manifest["artifacts"]
    assert manifest["counts"]["market_regime_records"] == 0
    assert manifest["counts"]["market_regime_unknown_records"] == 0
    assert _stage(manifest, "build_market_regime_assessment")["artifacts"] == []


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
            "views": [],
        },
    )
    run.manifest["artifacts"]["market_data_views"] = "raw/market_data_views.json"
    run.manifest["counts"]["market_data_views"] = 0
    run.manifest["counts"]["market_data_views_insufficient_data"] = 0
    return ["raw/market_data_views.json"]


def _write_quant_strategy_runs(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "quant_strategy_runs.json",
        {
            "schema_version": 1,
            "artifact_type": "quant_strategy_runs",
            "created_at": "2026-06-05T00:00:00Z",
            "engine": {"name": "vectorbt", "version": "1.0.0", "objects_exposed": False},
            "source_artifacts": ["raw/market_data_views.json"],
            "runs": [],
        },
    )
    run.manifest["artifacts"]["quant_strategy_runs"] = "analysis/quant_strategy_runs.json"
    run.manifest["counts"]["quant_strategy_runs"] = 0
    return ["analysis/quant_strategy_runs.json"]


def _write_strategy_signals(config, run) -> list[str]:
    signals = [
        _strategy_signal("tsmom_vol_scaled", "BTCUSDT", "bullish", "high", "risk_on_momentum"),
        _strategy_signal(
            "bollinger_rsi_reversion",
            "BTCUSDT",
            "bearish",
            "low",
            "overbought_reversion_watch",
        ),
        _strategy_signal("tsmom_vol_scaled", "ETHUSDT", "bullish", "high", "risk_on_momentum"),
        _strategy_signal("breakout_atr_trend", "ETHUSDT", "bullish", "high", "confirmed_breakout"),
        _strategy_signal(
            "breakout_atr_trend",
            "SOLUSDT",
            "unknown",
            "low",
            None,
            insufficient=True,
        ),
    ]
    write_json(
        run.analysis_dir / "market_strategy_signals.json",
        {
            "schema_version": 1,
            "artifact_type": "market_strategy_signals",
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": [
                "analysis/quant_strategy_runs.json",
                "raw/market_data_views.json",
            ],
            "signals": signals,
        },
    )
    run.manifest["artifacts"]["market_strategy_signals"] = "analysis/market_strategy_signals.json"
    run.manifest["counts"]["market_strategy_signals"] = len(signals)
    run.manifest["counts"]["market_strategy_signals_insufficient_data"] = 1
    return ["analysis/market_strategy_signals.json"]


def _write_empty_market_signals(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "market_signals.json",
        {
            "schema_version": 1,
            "artifact_type": "market_signals",
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": [
                "analysis/market_strategy_signals.json",
                "analysis/quant_strategy_runs.json",
            ],
            "signals": [],
        },
    )
    run.manifest["artifacts"]["market_signals"] = "analysis/market_signals.json"
    run.manifest["counts"]["market_signals"] = 0
    run.manifest["counts"]["market_signals_insufficient_data"] = 0
    return ["analysis/market_signals.json"]


def _strategy_signal(
    strategy_name: str,
    symbol: str,
    direction: str,
    confidence: str,
    latest_regime: str | None,
    *,
    insufficient: bool = False,
) -> dict[str, Any]:
    key_values = {"row_count": 3}
    if latest_regime:
        key_values["latest_regime"] = latest_regime
    if strategy_name == "tsmom_vol_scaled":
        key_values["return_window_pct"] = 6.0
        key_values["realized_volatility_pct"] = 18.0
        key_values["target_volatility_pct"] = 20.0
    if strategy_name == "breakout_atr_trend":
        key_values["atr_pct"] = 2.0
    if insufficient:
        key_values = {"requested_lookback": 3, "row_count": 1}
    return {
        "strategy_signal_id": (
            f"strategy_signal:{strategy_name}:binance:{symbol}:1d:2026-06-03T00:00:00Z"
        ),
        "strategy_name": strategy_name,
        "source": "binance",
        "symbol": symbol,
        "timeframe": "1d",
        "input_view_id": f"ohlcv_view:binance:{symbol}:1d:2026-06-03T00:00:00Z",
        "input_window_start": "2026-06-01T00:00:00Z",
        "input_window_end": "2026-06-03T00:00:00Z",
        "latest_candle_time": "2026-06-03T00:00:00Z",
        "direction": direction,
        "strength": "medium" if direction != "unknown" else "unknown",
        "confidence": confidence,
        "key_values": key_values,
        "evidence": (
            ["input view has 1 OHLCV rows for requested_lookback 3."]
            if insufficient
            else [f"{strategy_name} evidence summary for {symbol}."]
        ),
        "uncertainty": (
            ["binance SOLUSDT 1d has insufficient OHLCV rows."]
            if insufficient
            else [f"{strategy_name} uncertainty summary for {symbol}."]
        ),
        "insufficient_data": insufficient,
        "source_artifacts": [
            "analysis/quant_strategy_runs.json",
            "raw/market_data_views.json",
        ],
        "created_at": "2026-06-05T00:00:00Z",
    }


def _market_regime_assessment(result) -> dict[str, Any]:
    return json.loads((result.run.analysis_dir / "market_regime_assessment.json").read_text(encoding="utf-8"))


def _manifest(result) -> dict[str, Any]:
    return json.loads(result.run.manifest_path.read_text(encoding="utf-8"))


def _stage(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    return next(stage for stage in manifest["stages"] if stage["name"] == name)


def _noop_stage(config, run) -> list[str]:
    return []
