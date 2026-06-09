from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from halpha.config import load_config
from halpha.pipeline import run_pipeline
from halpha.storage import write_json


TRIGGER_TYPES = [
    "confirmation",
    "invalidation",
    "risk_escalation",
    "risk_relief",
    "wait_condition",
    "recheck_next_run",
]


def test_watch_triggers_generate_supported_types_and_link_decisions(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_watch_triggers",
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "sync_ohlcv": _noop_stage,
            "build_market_data_views": _noop_stage,
            "evaluate_quant_strategies": _noop_stage,
            "evaluate_market_strategy_signals": _noop_stage,
            "build_market_signals": _write_market_signals,
            "build_market_signal_material": _noop_stage,
            "build_market_regime_assessment": _write_market_regime_assessment,
            "build_risk_assessment": _write_risk_assessment,
            "build_decision_recommendations": _write_decision_recommendations,
        },
    )

    assert result.succeeded is True
    artifact = _watch_triggers(result)
    manifest = _manifest(result)
    records = artifact["records"]
    records_by_type = {record["type"] for record in records}

    assert artifact["artifact_type"] == "watch_triggers"
    assert artifact["schema_version"] == 1
    assert artifact["run_id"] == result.run.run_id
    assert artifact["created_at"] == "2026-06-05T00:00:00Z"
    assert artifact["trigger_types"] == TRIGGER_TYPES
    assert artifact["source_artifacts"] == [
        "analysis/decision_recommendations.json",
        "analysis/risk_assessment.json",
        "analysis/market_regime_assessment.json",
        "analysis/market_signals.json",
        "analysis/market_strategy_signals.json",
        "analysis/quant_strategy_runs.json",
        "raw/market_data_views.json",
    ]
    assert artifact["errors"] == []
    assert records_by_type == set(TRIGGER_TYPES)
    assert all(record["condition"] for record in records)
    assert all(record["priority"] in {"high", "medium", "low"} for record in records)
    assert all(record["expected_decision_impact"] for record in records)
    assert all(record["evidence"] for record in records)
    assert all(record["source_artifacts"] for record in records)
    assert all(record["linked_decision_record_id"].startswith("decision_recommendation:") for record in records)

    eth_triggers = [record for record in records if record["symbol"] == "ETHUSDT"]
    assert {record["type"] for record in eth_triggers} >= {
        "confirmation",
        "invalidation",
        "risk_escalation",
        "recheck_next_run",
    }
    assert any(record["linked_decision_record_id"].endswith(":ETHUSDT:1d:2026-06-03T00:00:00Z") for record in eth_triggers)

    btc_triggers = [record for record in records if record["symbol"] == "BTCUSDT"]
    assert {record["type"] for record in btc_triggers} >= {"confirmation", "risk_relief", "wait_condition"}
    assert any("conflict" in record["condition"].lower() for record in btc_triggers)

    xrp_triggers = [record for record in records if record["symbol"] == "XRPUSDT"]
    assert {record["type"] for record in xrp_triggers} >= {"risk_relief", "wait_condition", "recheck_next_run"}
    assert any("risk_level=extreme" in " ".join(record["evidence"]) for record in xrp_triggers)

    assert manifest["artifacts"]["watch_triggers"] == "analysis/watch_triggers.json"
    assert manifest["counts"]["watch_trigger_records"] == len(records)
    assert manifest["counts"]["watch_trigger_linked_records"] == len(records)
    for trigger_type in TRIGGER_TYPES:
        assert manifest["counts"][f"watch_trigger_{trigger_type}_records"] > 0
    assert _stage(manifest, "build_watch_triggers")["artifacts"] == ["analysis/watch_triggers.json"]
    assert _stage(manifest, "build_analysis_materials")["status"] == "not_run"


def test_watch_triggers_do_not_fabricate_conditions_without_evidence(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_watch_triggers",
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "sync_ohlcv": _noop_stage,
            "build_market_data_views": _noop_stage,
            "evaluate_quant_strategies": _noop_stage,
            "evaluate_market_strategy_signals": _noop_stage,
            "build_market_signals": _write_empty_market_signals,
            "build_market_signal_material": _noop_stage,
            "build_market_regime_assessment": _write_empty_market_regime_assessment,
            "build_risk_assessment": _write_empty_risk_assessment,
            "build_decision_recommendations": _write_empty_decision_recommendations,
        },
    )

    assert result.succeeded is True
    artifact = _watch_triggers(result)
    manifest = _manifest(result)

    assert artifact["records"] == []
    assert artifact["warnings"] == [
        "No decision recommendation records were available for watch trigger generation."
    ]
    assert artifact["errors"] == []
    assert manifest["counts"]["watch_trigger_records"] == 0
    assert manifest["counts"]["watch_trigger_linked_records"] == 0


def test_watch_triggers_skip_when_quant_is_not_enabled(tmp_path: Path) -> None:
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
    assert not (result.run.analysis_dir / "watch_triggers.json").exists()
    assert "watch_triggers" not in manifest["artifacts"]
    assert manifest["counts"]["watch_trigger_records"] == 0
    assert manifest["counts"]["watch_trigger_linked_records"] == 0
    assert _stage(manifest, "build_watch_triggers")["artifacts"] == []


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
        _signal("BTCUSDT", "bullish", "high", "risk_on_momentum"),
        _signal("BTCUSDT", "bearish", "low", "overbought_reversion_watch"),
        _signal("ETHUSDT", "bullish", "high", "risk_on_momentum"),
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
    return ["analysis/market_signals.json"]


def _write_market_regime_assessment(config, run) -> list[str]:
    records = [
        _regime(
            "BTCUSDT",
            "mixed",
            "low",
            conflicts=["Upstream signals include both bullish and bearish directions for this market window."],
        ),
        _regime("ETHUSDT", "trend_up", "high"),
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
    return ["analysis/market_regime_assessment.json"]


def _write_risk_assessment(config, run) -> list[str]:
    records = [
        _risk(
            "BTCUSDT",
            "high",
            cap_action_level="WATCH",
            signal_conflict_risks=["Bullish and bearish market signals conflict for this market window."],
            blocking_risks=["Market regime assessment reports material signal conflict."],
        ),
        _risk("ETHUSDT", "low"),
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
    return ["analysis/risk_assessment.json"]


def _write_decision_recommendations(config, run) -> list[str]:
    records = [
        _decision("BTCUSDT", "WATCH", "wait_for_conflict_resolution", "watch", risk_level="high"),
        _decision("ETHUSDT", "TRY_SMALL", "tentative_constructive", "actionable", risk_level="low"),
        _decision("XRPUSDT", "NO_ACTION", "risk_blocked", "risk_blocked", risk_level="extreme"),
    ]
    write_json(
        run.analysis_dir / "decision_recommendations.json",
        {
            "schema_version": 1,
            "artifact_type": "decision_recommendations",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "action_taxonomy": [
                "STRONG_DO",
                "DO",
                "TRY_SMALL",
                "WATCH",
                "AVOID",
                "EXIT_OR_REDUCE",
                "HEDGE_OR_PROTECT",
                "NO_ACTION",
            ],
            "source_artifacts": [
                "analysis/risk_assessment.json",
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
    run.manifest["artifacts"]["decision_recommendations"] = "analysis/decision_recommendations.json"
    return ["analysis/decision_recommendations.json"]


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


def _write_empty_decision_recommendations(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "decision_recommendations.json",
        {
            "schema_version": 1,
            "artifact_type": "decision_recommendations",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "action_taxonomy": [],
            "source_artifacts": [
                "analysis/risk_assessment.json",
                "analysis/market_regime_assessment.json",
                "analysis/market_signals.json",
            ],
            "records": [],
            "warnings": ["No decision recommendation records were available."],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["decision_recommendations"] = "analysis/decision_recommendations.json"
    return ["analysis/decision_recommendations.json"]


def _signal(symbol: str, direction: str, confidence: str, latest_regime: str) -> dict[str, Any]:
    return {
        "strategy_name": "tsmom_vol_scaled",
        "source": "binance",
        "symbol": symbol,
        "timeframe": "1d",
        "latest_candle_time": "2026-06-03T00:00:00Z",
        "direction": direction,
        "strength": "medium",
        "confidence": confidence,
        "key_values": {"latest_regime": latest_regime},
        "evidence": [f"{symbol} {direction} signal evidence."],
        "uncertainty": [f"{symbol} uncertainty summary."],
        "insufficient_data": False,
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
    conflicts: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "record_id": f"market_regime:binance:{symbol}:1d:2026-06-03T00:00:00Z",
        "source": "binance",
        "symbol": symbol,
        "timeframe": "1d",
        "latest_candle_time": "2026-06-03T00:00:00Z",
        "regime": regime,
        "confidence": confidence,
        "status": "succeeded",
        "evidence": [f"market_regime={regime}; confidence={confidence}; status=succeeded."],
        "conflicts": conflicts or [],
        "uncertainty": [],
        "warnings": [],
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
    cap_action_level: str | None = None,
    rising_risks: list[str] | None = None,
    blocking_risks: list[str] | None = None,
    signal_conflict_risks: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "record_id": f"risk_assessment:binance:{symbol}:1d:2026-06-03T00:00:00Z",
        "source": "binance",
        "symbol": symbol,
        "timeframe": "1d",
        "latest_candle_time": "2026-06-03T00:00:00Z",
        "risk_level": risk_level,
        "status": "succeeded",
        "rising_risks": rising_risks or [],
        "blocking_risks": blocking_risks or [],
        "data_quality_risks": [],
        "signal_conflict_risks": signal_conflict_risks or [],
        "gates": {
            "block_strong_action": cap_action_level is not None,
            "cap_action_level": cap_action_level,
            "requires_invalidation": cap_action_level is not None,
        },
        "evidence": [
            f"risk_level={risk_level}; status=succeeded.",
            f"{symbol} risk evidence.",
        ],
        "warnings": [],
        "errors": [],
        "source_artifacts": [
            "analysis/market_regime_assessment.json",
            "analysis/market_signals.json",
            "analysis/market_strategy_signals.json",
            "analysis/quant_strategy_runs.json",
            "raw/market_data_views.json",
        ],
    }


def _decision(
    symbol: str,
    action_level: str,
    decision_bias: str,
    status: str,
    *,
    risk_level: str,
) -> dict[str, Any]:
    invalidation_conditions = (
        [
            f"{symbol} risk_level rises to high or extreme.",
            f"{symbol} upstream market signals no longer support the current decision bias.",
        ]
        if action_level in {"DO", "TRY_SMALL", "AVOID"}
        else []
    )
    warnings = [f"risk_level={risk_level} caps stronger action levels."] if action_level in {"WATCH", "NO_ACTION"} else []
    return {
        "record_id": f"decision_recommendation:binance:{symbol}:1d:2026-06-03T00:00:00Z",
        "source": "binance",
        "symbol": symbol,
        "timeframe": "1d",
        "latest_candle_time": "2026-06-03T00:00:00Z",
        "action_level": action_level,
        "decision_bias": decision_bias,
        "confidence": "medium",
        "status": status,
        "recommended_actions": [f"Watch {symbol} for decision-relevant changes."],
        "do_not_do": ["Do not treat this record as an order."],
        "risk_conditions": [f"risk_level={risk_level}; status=succeeded."],
        "invalidation_conditions": invalidation_conditions,
        "evidence": [
            f"direction_counts: bullish=1.",
            f"risk_level={risk_level}; status=succeeded.",
            f"{symbol} decision evidence.",
        ],
        "conflicts": (
            ["Upstream signals include both bullish and bearish directions for this market window."]
            if symbol == "BTCUSDT"
            else []
        ),
        "warnings": warnings,
        "source_artifacts": [
            "analysis/risk_assessment.json",
            "analysis/market_regime_assessment.json",
            "analysis/market_signals.json",
            "analysis/market_strategy_signals.json",
            "analysis/quant_strategy_runs.json",
            "raw/market_data_views.json",
        ],
    }


def _watch_triggers(result) -> dict[str, Any]:
    return json.loads((result.run.analysis_dir / "watch_triggers.json").read_text(encoding="utf-8"))


def _manifest(result) -> dict[str, Any]:
    return json.loads(result.run.manifest_path.read_text(encoding="utf-8"))


def _stage(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    return next(stage for stage in manifest["stages"] if stage["name"] == name)


def _noop_stage(config, run) -> list[str]:
    return []
