from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from halpha.config import load_config
from halpha.pipeline import run_pipeline
from halpha.storage import write_json


ACTION_TAXONOMY = [
    "STRONG_DO",
    "DO",
    "TRY_SMALL",
    "WATCH",
    "AVOID",
    "EXIT_OR_REDUCE",
    "HEDGE_OR_PROTECT",
    "NO_ACTION",
]
ACTIONABLE_LEVELS = {"STRONG_DO", "DO", "TRY_SMALL", "AVOID", "EXIT_OR_REDUCE", "HEDGE_OR_PROTECT"}


def test_decision_recommendations_apply_taxonomy_and_policy_gates(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_decision_recommendations",
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "sync_ohlcv": _noop_stage,
            "build_market_data_views": _noop_stage,
            "evaluate_quant_strategies": _noop_stage,
            "evaluate_strategy_evaluation": _noop_stage,
            "evaluate_market_strategy_signals": _noop_stage,
            "build_market_signals": _write_market_signals,
            "build_market_signal_material": _noop_stage,
            "build_market_regime_assessment": _write_market_regime_assessment,
            "build_risk_assessment": _write_risk_assessment,
        },
    )

    assert result.succeeded is True
    artifact = _decision_recommendations(result)
    manifest = _manifest(result)
    records = {record["symbol"]: record for record in artifact["records"]}

    assert artifact["artifact_type"] == "decision_recommendations"
    assert artifact["schema_version"] == 1
    assert artifact["run_id"] == result.run.run_id
    assert artifact["created_at"] == "2026-06-05T00:00:00Z"
    assert artifact["action_taxonomy"] == ACTION_TAXONOMY
    assert artifact["source_artifacts"] == [
        "analysis/risk_assessment.json",
        "analysis/market_regime_assessment.json",
        "analysis/market_signals.json",
        "analysis/market_strategy_signals.json",
        "analysis/quant_strategy_runs.json",
        "raw/market_data_views.json",
    ]
    assert artifact["errors"] == []
    assert set(records) == {"ADAUSDT", "BTCUSDT", "DOGEUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"}

    eth = records["ETHUSDT"]
    assert eth["action_level"] == "DO"
    assert eth["status"] == "actionable"
    assert eth["decision_bias"] == "constructive"
    assert eth["recommended_actions"]
    assert eth["do_not_do"]
    assert eth["invalidation_conditions"]
    assert eth["evidence"]
    assert eth["conflicts"] == []

    ada = records["ADAUSDT"]
    assert ada["action_level"] == "TRY_SMALL"
    assert ada["status"] == "actionable"
    assert ada["decision_bias"] == "tentative_constructive"
    assert any("risk_level=medium" in item for item in ada["risk_conditions"])
    assert any("cap_action_level=TRY_SMALL" in item for item in ada["risk_conditions"])

    btc = records["BTCUSDT"]
    assert btc["action_level"] == "WATCH"
    assert btc["status"] == "watch"
    assert btc["decision_bias"] == "wait_for_conflict_resolution"
    assert btc["conflicts"]
    assert btc["recommended_actions"]
    assert any("conflict" in item.lower() for item in btc["warnings"])
    assert any("risk_level=high" in item for item in btc["risk_conditions"])

    sol = records["SOLUSDT"]
    assert sol["action_level"] == "NO_ACTION"
    assert sol["status"] == "insufficient_data"
    assert sol["decision_bias"] == "insufficient_evidence"
    assert sol["recommended_actions"] == []
    assert sol["invalidation_conditions"] == []
    assert any("insufficient" in item.lower() for item in sol["warnings"])

    xrp = records["XRPUSDT"]
    assert xrp["action_level"] == "NO_ACTION"
    assert xrp["status"] == "risk_blocked"
    assert xrp["decision_bias"] == "risk_blocked"
    assert any("risk_level=extreme" in item for item in xrp["risk_conditions"])
    assert any("Do not upgrade" in item for item in xrp["do_not_do"])

    doge = records["DOGEUSDT"]
    assert doge["action_level"] == "AVOID"
    assert doge["status"] == "actionable"
    assert doge["decision_bias"] == "defensive_avoid"
    assert doge["invalidation_conditions"]

    for record in artifact["records"]:
        if record["action_level"] in ACTIONABLE_LEVELS:
            assert record["evidence"]
            assert record["invalidation_conditions"]

    assert manifest["artifacts"]["decision_recommendations"] == "analysis/decision_recommendations.json"
    assert manifest["counts"]["decision_recommendation_records"] == 6
    assert manifest["counts"]["decision_recommendation_actionable_records"] == 3
    assert manifest["counts"]["decision_recommendation_non_actionable_records"] == 3
    assert manifest["counts"]["decision_recommendation_risk_blocked_records"] == 2
    assert _stage(manifest, "build_decision_recommendations")["artifacts"] == [
        "analysis/decision_recommendations.json"
    ]
    assert _stage(manifest, "build_analysis_materials")["status"] == "not_run"


def test_decision_recommendations_do_not_fabricate_actions_when_upstream_is_empty(
    tmp_path: Path,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_decision_recommendations",
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "sync_ohlcv": _noop_stage,
            "build_market_data_views": _noop_stage,
            "evaluate_quant_strategies": _noop_stage,
            "evaluate_strategy_evaluation": _noop_stage,
            "evaluate_market_strategy_signals": _noop_stage,
            "build_market_signals": _write_empty_market_signals,
            "build_market_signal_material": _noop_stage,
            "build_market_regime_assessment": _write_empty_market_regime_assessment,
            "build_risk_assessment": _write_empty_risk_assessment,
        },
    )

    assert result.succeeded is True
    artifact = _decision_recommendations(result)
    manifest = _manifest(result)

    assert artifact["records"] == []
    assert artifact["warnings"] == [
        "No market, regime, or risk records were available for decision recommendations."
    ]
    assert artifact["errors"] == []
    assert manifest["counts"]["decision_recommendation_records"] == 0
    assert manifest["counts"]["decision_recommendation_actionable_records"] == 0
    assert manifest["counts"]["decision_recommendation_non_actionable_records"] == 0
    assert manifest["counts"]["decision_recommendation_risk_blocked_records"] == 0


def test_decision_recommendations_skip_when_quant_is_not_enabled(tmp_path: Path) -> None:
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
            "evaluate_strategy_evaluation": _noop_stage,
            "evaluate_market_strategy_signals": _noop_stage,
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
    assert not (result.run.analysis_dir / "decision_recommendations.json").exists()
    assert "decision_recommendations" not in manifest["artifacts"]
    assert manifest["counts"]["decision_recommendation_records"] == 0
    assert manifest["counts"]["decision_recommendation_actionable_records"] == 0
    assert manifest["counts"]["decision_recommendation_non_actionable_records"] == 0
    assert manifest["counts"]["decision_recommendation_risk_blocked_records"] == 0
    assert _stage(manifest, "build_decision_recommendations")["artifacts"] == []


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


def _write_market_signals(config, run) -> list[str]:
    signals = [
        _signal("ADAUSDT", "bullish", "medium", "risk_limited_momentum"),
        _signal("BTCUSDT", "bullish", "high", "risk_on_momentum"),
        _signal("BTCUSDT", "bearish", "low", "overbought_reversion_watch"),
        _signal("DOGEUSDT", "bearish", "high", "downtrend"),
        _signal("ETHUSDT", "bullish", "high", "risk_on_momentum"),
        _signal("ETHUSDT", "bullish", "high", "confirmed_breakout"),
        _signal("SOLUSDT", "unknown", "low", "unknown", insufficient=True),
        _signal("XRPUSDT", "bullish", "medium", "confirmed_breakout"),
    ]
    write_json(
        run.analysis_dir / "market_signals.json",
        {
            "schema_version": 1,
            "artifact_type": "market_signals",
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": [
                "analysis/market_strategy_signals.json",
                "analysis/quant_strategy_runs.json",
                "raw/market_data_views.json",
            ],
            "signals": signals,
        },
    )
    run.manifest["artifacts"]["market_signals"] = "analysis/market_signals.json"
    run.manifest["counts"]["market_signals"] = len(signals)
    return ["analysis/market_signals.json"]


def _write_market_regime_assessment(config, run) -> list[str]:
    records = [
        _regime("ADAUSDT", "trend_up", "medium"),
        _regime(
            "BTCUSDT",
            "mixed",
            "low",
            conflicts=["Upstream signals include both bullish and bearish directions for this market window."],
        ),
        _regime("DOGEUSDT", "trend_down", "high"),
        _regime("ETHUSDT", "trend_up", "high"),
        _regime(
            "SOLUSDT",
            "unknown",
            "low",
            status="insufficient_data",
            warnings=["No usable upstream market signal evidence was available."],
        ),
        _regime("XRPUSDT", "trend_up", "medium"),
    ]
    write_json(
        run.analysis_dir / "market_regime_assessment.json",
        {
            "schema_version": 1,
            "artifact_type": "market_regime_assessment",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": [
                "analysis/market_signals.json",
                "analysis/market_strategy_signals.json",
                "analysis/quant_strategy_runs.json",
                "raw/market_data_views.json",
            ],
            "records": records,
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["market_regime_assessment"] = "analysis/market_regime_assessment.json"
    run.manifest["counts"]["market_regime_records"] = len(records)
    return ["analysis/market_regime_assessment.json"]


def _write_risk_assessment(config, run) -> list[str]:
    records = [
        _risk("ADAUSDT", "medium", cap_action_level="TRY_SMALL"),
        _risk(
            "BTCUSDT",
            "high",
            cap_action_level="WATCH",
            signal_conflict_risks=["Bullish and bearish market signals conflict for this market window."],
            blocking_risks=["Market regime assessment reports material signal conflict."],
        ),
        _risk("DOGEUSDT", "low"),
        _risk("ETHUSDT", "low"),
        _risk(
            "SOLUSDT",
            "unknown",
            status="insufficient_data",
            cap_action_level="WATCH",
            data_quality_risks=["SOLUSDT has insufficient upstream market signal data."],
            blocking_risks=["Insufficient upstream evidence blocks stronger action levels."],
            warnings=["No usable upstream risk evidence was available; risk level is unknown."],
        ),
        _risk(
            "XRPUSDT",
            "extreme",
            cap_action_level="NO_ACTION",
            rising_risks=["XRPUSDT ATR volatility is extremely elevated."],
            blocking_risks=["Extreme ATR volatility blocks stronger action levels."],
        ),
    ]
    write_json(
        run.analysis_dir / "risk_assessment.json",
        {
            "schema_version": 1,
            "artifact_type": "risk_assessment",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": [
                "analysis/market_regime_assessment.json",
                "analysis/market_signals.json",
                "analysis/market_strategy_signals.json",
                "analysis/quant_strategy_runs.json",
                "raw/market_data_views.json",
            ],
            "records": records,
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["risk_assessment"] = "analysis/risk_assessment.json"
    run.manifest["counts"]["risk_assessment_records"] = len(records)
    return ["analysis/risk_assessment.json"]


def _write_empty_market_signals(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "market_signals.json",
        {
            "schema_version": 1,
            "artifact_type": "market_signals",
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["analysis/market_strategy_signals.json"],
            "signals": [],
        },
    )
    run.manifest["artifacts"]["market_signals"] = "analysis/market_signals.json"
    run.manifest["counts"]["market_signals"] = 0
    return ["analysis/market_signals.json"]


def _write_empty_market_regime_assessment(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "market_regime_assessment.json",
        {
            "schema_version": 1,
            "artifact_type": "market_regime_assessment",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["analysis/market_signals.json"],
            "records": [],
            "warnings": ["No market signal records were available for regime assessment."],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["market_regime_assessment"] = "analysis/market_regime_assessment.json"
    return ["analysis/market_regime_assessment.json"]


def _write_empty_risk_assessment(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "risk_assessment.json",
        {
            "schema_version": 1,
            "artifact_type": "risk_assessment",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": [
                "analysis/market_regime_assessment.json",
                "analysis/market_signals.json",
            ],
            "records": [],
            "warnings": ["No market or regime records were available for risk assessment."],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["risk_assessment"] = "analysis/risk_assessment.json"
    return ["analysis/risk_assessment.json"]


def _signal(
    symbol: str,
    direction: str,
    confidence: str,
    latest_regime: str,
    *,
    insufficient: bool = False,
) -> dict[str, Any]:
    return {
        "strategy_name": "tsmom_vol_scaled",
        "source": "binance",
        "symbol": symbol,
        "timeframe": "1d",
        "latest_candle_time": "2026-06-03T00:00:00Z",
        "direction": direction,
        "strength": "medium" if direction != "unknown" else "unknown",
        "confidence": confidence,
        "key_values": {"latest_regime": latest_regime},
        "evidence": (
            ["input view has insufficient rows for requested lookback."]
            if insufficient
            else [f"{symbol} {direction} signal evidence."]
        ),
        "uncertainty": (
            [f"{symbol} has insufficient OHLCV rows."]
            if insufficient
            else [f"{symbol} uncertainty summary."]
        ),
        "insufficient_data": insufficient,
        "source_artifacts": [
            "analysis/quant_strategy_runs.json",
            "raw/market_data_views.json",
        ],
        "created_at": "2026-06-05T00:00:00Z",
    }


def _regime(
    symbol: str,
    regime: str,
    confidence: str,
    *,
    status: str = "succeeded",
    conflicts: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "record_id": f"market_regime:binance:{symbol}:1d:2026-06-03T00:00:00Z",
        "source": "binance",
        "symbol": symbol,
        "timeframe": "1d",
        "latest_candle_time": "2026-06-03T00:00:00Z",
        "regime": regime,
        "confidence": confidence,
        "status": status,
        "evidence": [f"market_regime={regime}; confidence={confidence}; status={status}."],
        "conflicts": conflicts or [],
        "uncertainty": [],
        "warnings": warnings or [],
        "source_artifacts": [
            "analysis/market_signals.json",
            "analysis/market_strategy_signals.json",
            "analysis/quant_strategy_runs.json",
            "raw/market_data_views.json",
        ],
    }


def _risk(
    symbol: str,
    risk_level: str,
    *,
    status: str = "succeeded",
    cap_action_level: str | None = None,
    rising_risks: list[str] | None = None,
    blocking_risks: list[str] | None = None,
    data_quality_risks: list[str] | None = None,
    signal_conflict_risks: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "record_id": f"risk_assessment:binance:{symbol}:1d:2026-06-03T00:00:00Z",
        "source": "binance",
        "symbol": symbol,
        "timeframe": "1d",
        "latest_candle_time": "2026-06-03T00:00:00Z",
        "risk_level": risk_level,
        "status": status,
        "rising_risks": rising_risks or [],
        "blocking_risks": blocking_risks or [],
        "data_quality_risks": data_quality_risks or [],
        "signal_conflict_risks": signal_conflict_risks or [],
        "gates": {
            "block_strong_action": cap_action_level is not None,
            "cap_action_level": cap_action_level,
            "requires_invalidation": cap_action_level is not None,
        },
        "evidence": [
            f"risk_level={risk_level}; status={status}.",
            f"{symbol} risk evidence.",
        ],
        "warnings": warnings or [],
        "errors": [],
        "source_artifacts": [
            "analysis/market_regime_assessment.json",
            "analysis/market_signals.json",
            "analysis/market_strategy_signals.json",
            "analysis/quant_strategy_runs.json",
            "raw/market_data_views.json",
        ],
    }


def _decision_recommendations(result) -> dict[str, Any]:
    return json.loads((result.run.analysis_dir / "decision_recommendations.json").read_text(encoding="utf-8"))


def _manifest(result) -> dict[str, Any]:
    return json.loads(result.run.manifest_path.read_text(encoding="utf-8"))


def _stage(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    return next(stage for stage in manifest["stages"] if stage["name"] == name)


def _noop_stage(config, run) -> list[str]:
    return []
