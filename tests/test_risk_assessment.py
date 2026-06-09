from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from halpha.config import load_config
from halpha.pipeline import run_pipeline
from halpha.storage import write_json


def test_risk_assessment_classifies_taxonomy_and_gating_fields(tmp_path: Path) -> None:
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
            "evaluate_market_strategy_signals": _write_strategy_signals,
            "build_analysis_materials": _noop_stage,
            "build_research_context": _noop_stage,
            "build_codex_context": _noop_stage,
            "run_codex_report": _noop_stage,
        },
    )

    assert result.succeeded is True
    artifact = _risk_assessment(result)
    manifest = _manifest(result)
    records = {record["symbol"]: record for record in artifact["records"]}

    assert artifact["artifact_type"] == "risk_assessment"
    assert artifact["schema_version"] == 1
    assert artifact["run_id"] == result.run.run_id
    assert artifact["created_at"] == "2026-06-05T00:00:00Z"
    assert artifact["source_artifacts"] == [
        "analysis/market_regime_assessment.json",
        "analysis/market_signals.json",
        "analysis/market_strategy_signals.json",
        "analysis/quant_strategy_runs.json",
        "raw/market_data_views.json",
    ]
    assert artifact["errors"] == []
    assert set(records) == {"ADAUSDT", "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"}

    ada = records["ADAUSDT"]
    assert ada["risk_level"] == "medium"
    assert ada["gates"] == {
        "block_strong_action": True,
        "cap_action_level": "TRY_SMALL",
        "requires_invalidation": True,
    }
    assert ada["rising_risks"]
    assert ada["blocking_risks"] == []

    btc = records["BTCUSDT"]
    assert btc["risk_level"] == "high"
    assert btc["signal_conflict_risks"]
    assert btc["blocking_risks"]
    assert btc["gates"]["block_strong_action"] is True
    assert btc["gates"]["cap_action_level"] == "WATCH"

    eth = records["ETHUSDT"]
    assert eth["risk_level"] == "low"
    assert eth["rising_risks"] == []
    assert eth["blocking_risks"] == []
    assert eth["gates"] == {
        "block_strong_action": False,
        "cap_action_level": None,
        "requires_invalidation": False,
    }
    assert "No elevated risk factors were found" in eth["evidence"][-1]

    sol = records["SOLUSDT"]
    assert sol["risk_level"] == "unknown"
    assert sol["status"] == "insufficient_data"
    assert sol["data_quality_risks"]
    assert sol["warnings"] == [
        "No usable upstream risk evidence was available; risk level is unknown."
    ]
    assert sol["gates"]["block_strong_action"] is True
    assert sol["gates"]["cap_action_level"] == "WATCH"

    xrp = records["XRPUSDT"]
    assert xrp["risk_level"] == "extreme"
    assert xrp["rising_risks"]
    assert xrp["blocking_risks"]
    assert xrp["gates"] == {
        "block_strong_action": True,
        "cap_action_level": "NO_ACTION",
        "requires_invalidation": True,
    }
    assert any("atr_pct 9.0" in item for item in xrp["evidence"])

    assert manifest["artifacts"]["risk_assessment"] == "analysis/risk_assessment.json"
    assert manifest["counts"]["risk_assessment_records"] == 5
    assert manifest["counts"]["risk_assessment_unknown_records"] == 1
    assert manifest["counts"]["risk_assessment_high_or_extreme_records"] == 2
    assert manifest["counts"]["risk_assessment_blocking_records"] == 3
    assert _stage(manifest, "build_risk_assessment")["artifacts"] == [
        "analysis/risk_assessment.json"
    ]


def test_risk_assessment_writes_warning_without_fake_low_risk_when_upstream_is_empty(
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
            "evaluate_quant_strategies": _write_empty_quant_strategy_runs,
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
    artifact = _risk_assessment(result)
    manifest = _manifest(result)
    assert artifact["records"] == []
    assert artifact["warnings"] == ["No market or regime records were available for risk assessment."]
    assert artifact["errors"] == []
    assert manifest["counts"]["risk_assessment_records"] == 0
    assert manifest["counts"]["risk_assessment_unknown_records"] == 0
    assert manifest["counts"]["risk_assessment_high_or_extreme_records"] == 0
    assert manifest["counts"]["risk_assessment_blocking_records"] == 0


def test_risk_assessment_skips_when_quant_is_not_enabled(tmp_path: Path) -> None:
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
    assert not (result.run.analysis_dir / "risk_assessment.json").exists()
    assert "risk_assessment" not in manifest["artifacts"]
    assert manifest["counts"]["risk_assessment_records"] == 0
    assert manifest["counts"]["risk_assessment_unknown_records"] == 0
    assert manifest["counts"]["risk_assessment_high_or_extreme_records"] == 0
    assert manifest["counts"]["risk_assessment_blocking_records"] == 0
    assert _stage(manifest, "build_risk_assessment")["artifacts"] == []


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
    runs = [
        _strategy_run("tsmom_vol_scaled", "ADAUSDT"),
        _strategy_run("tsmom_vol_scaled", "BTCUSDT"),
        _strategy_run("bollinger_rsi_reversion", "BTCUSDT"),
        _strategy_run("tsmom_vol_scaled", "ETHUSDT"),
        _strategy_run("breakout_atr_trend", "ETHUSDT"),
        _strategy_run(
            "breakout_atr_trend",
            "SOLUSDT",
            status="insufficient_data",
            warning="input view has insufficient OHLCV rows.",
            row_count=1,
            minimum_required_rows=3,
        ),
        _strategy_run(
            "breakout_atr_trend",
            "XRPUSDT",
            warning="ATR is elevated relative to price, so breakout interpretation should stay risk-bounded.",
        ),
    ]
    write_json(
        run.analysis_dir / "quant_strategy_runs.json",
        {
            "schema_version": 1,
            "artifact_type": "quant_strategy_runs",
            "created_at": "2026-06-05T00:00:00Z",
            "engine": {"name": "vectorbt", "version": "1.0.0", "objects_exposed": False},
            "source_artifacts": ["raw/market_data_views.json"],
            "runs": runs,
        },
    )
    run.manifest["artifacts"]["quant_strategy_runs"] = "analysis/quant_strategy_runs.json"
    run.manifest["counts"]["quant_strategy_runs"] = len(runs)
    return ["analysis/quant_strategy_runs.json"]


def _write_empty_quant_strategy_runs(config, run) -> list[str]:
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
        _strategy_signal(
            "tsmom_vol_scaled",
            "ADAUSDT",
            "bullish",
            "medium",
            {
                "latest_regime": "risk_limited_momentum",
                "realized_volatility_pct": 24.0,
                "target_volatility_pct": 20.0,
            },
        ),
        _strategy_signal(
            "tsmom_vol_scaled",
            "BTCUSDT",
            "bullish",
            "high",
            {
                "latest_regime": "risk_on_momentum",
                "realized_volatility_pct": 18.0,
                "target_volatility_pct": 20.0,
            },
        ),
        _strategy_signal(
            "bollinger_rsi_reversion",
            "BTCUSDT",
            "bearish",
            "low",
            {"latest_regime": "overbought_reversion_watch", "rsi": 82.0},
        ),
        _strategy_signal("tsmom_vol_scaled", "ETHUSDT", "bullish", "high", {"latest_regime": "risk_on_momentum"}),
        _strategy_signal(
            "breakout_atr_trend",
            "ETHUSDT",
            "bullish",
            "high",
            {"latest_regime": "confirmed_breakout"},
        ),
        _strategy_signal(
            "breakout_atr_trend",
            "SOLUSDT",
            "unknown",
            "low",
            {"requested_lookback": 3, "row_count": 1},
            insufficient=True,
        ),
        _strategy_signal(
            "breakout_atr_trend",
            "XRPUSDT",
            "bullish",
            "medium",
            {"latest_regime": "confirmed_breakout", "atr_pct": 9.0},
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
    key_values: dict[str, Any],
    *,
    insufficient: bool = False,
) -> dict[str, Any]:
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


def _strategy_run(
    strategy_name: str,
    symbol: str,
    *,
    status: str = "succeeded",
    warning: str | None = None,
    row_count: int = 3,
    minimum_required_rows: int = 3,
) -> dict[str, Any]:
    return {
        "strategy_name": strategy_name,
        "source": "binance",
        "symbol": symbol,
        "timeframe": "1d",
        "input_view_id": f"ohlcv_view:binance:{symbol}:1d:2026-06-03T00:00:00Z",
        "latest_candle_time": "2026-06-03T00:00:00Z",
        "status": status,
        "data_quality": {
            "row_count": row_count,
            "minimum_required_rows": minimum_required_rows,
            "sufficient_data": status != "insufficient_data",
        },
        "warnings": (
            [{"code": "test_warning", "message": warning, "source": "strategy"}]
            if warning
            else []
        ),
        "source_artifacts": ["raw/market_data_views.json"],
        "created_at": "2026-06-05T00:00:00Z",
    }


def _risk_assessment(result) -> dict[str, Any]:
    return json.loads((result.run.analysis_dir / "risk_assessment.json").read_text(encoding="utf-8"))


def _manifest(result) -> dict[str, Any]:
    return json.loads(result.run.manifest_path.read_text(encoding="utf-8"))


def _stage(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    return next(stage for stage in manifest["stages"] if stage["name"] == name)


def _noop_stage(config, run) -> list[str]:
    return []
