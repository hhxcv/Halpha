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
            "evaluate_strategy_evaluation": _noop_stage,
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


def test_watch_triggers_include_derivatives_risk_conditions(tmp_path: Path) -> None:
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
            "build_derivatives_market_context": _write_stressed_derivatives_context,
            "evaluate_quant_strategies": _noop_stage,
            "evaluate_strategy_evaluation": _noop_stage,
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
    eth_triggers = [record for record in artifact["records"] if record["symbol"] == "ETHUSDT"]
    derivatives_triggers = [
        record for record in eth_triggers if record["linked_derivatives_context_ids"]
    ]

    assert derivatives_triggers
    assert any(record["type"] == "risk_escalation" for record in derivatives_triggers)
    assert any(record["type"] == "risk_relief" for record in derivatives_triggers)
    assert any("derivatives context adds" in record["condition"] for record in derivatives_triggers)
    assert all("analysis/derivatives_market_context.json" in record["source_artifacts"] for record in derivatives_triggers)
    assert manifest["counts"]["watch_trigger_derivatives_context_records"] == 1
    assert manifest["counts"]["watch_trigger_derivatives_linked_records"] == len(derivatives_triggers)


def test_watch_triggers_include_macro_calendar_observation_conditions(tmp_path: Path) -> None:
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
            "build_macro_calendar_context": _write_upcoming_macro_calendar_context,
            "evaluate_quant_strategies": _noop_stage,
            "evaluate_strategy_evaluation": _noop_stage,
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
    eth_triggers = [record for record in artifact["records"] if record["symbol"] == "ETHUSDT"]
    macro_triggers = [record for record in eth_triggers if record["linked_macro_calendar_context_ids"]]

    assert macro_triggers
    assert any(record["type"] == "wait_condition" for record in macro_triggers)
    assert any(record["type"] == "confirmation" for record in macro_triggers)
    assert any("post-event" in record["condition"] for record in macro_triggers)
    assert any("do not infer realized impact" in record["condition"] for record in macro_triggers)
    assert all("analysis/macro_calendar_context.json" in record["source_artifacts"] for record in macro_triggers)
    assert manifest["counts"]["watch_trigger_macro_calendar_context_records"] == 1
    assert manifest["counts"]["watch_trigger_macro_calendar_linked_records"] == len(macro_triggers)


def test_watch_triggers_include_onchain_flow_risk_conditions(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_watch_triggers",
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "collect_onchain_flow_data": _noop_stage,
            "sync_ohlcv": _noop_stage,
            "sync_onchain_flow_history": _noop_stage,
            "build_market_data_views": _noop_stage,
            "build_onchain_flow_views": _noop_stage,
            "build_onchain_flow_context": _write_stressed_onchain_flow_context,
            "evaluate_quant_strategies": _noop_stage,
            "evaluate_strategy_evaluation": _noop_stage,
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
    eth_triggers = [record for record in artifact["records"] if record["symbol"] == "ETHUSDT"]
    onchain_triggers = [record for record in eth_triggers if record["linked_onchain_flow_context_ids"]]

    assert onchain_triggers
    assert any(record["type"] == "risk_escalation" for record in onchain_triggers)
    assert any(record["type"] == "risk_relief" for record in onchain_triggers)
    assert any("on-chain flow context adds" in record["condition"] for record in onchain_triggers)
    assert all("analysis/onchain_flow_context.json" in record["source_artifacts"] for record in onchain_triggers)
    assert manifest["counts"]["watch_trigger_onchain_flow_context_records"] == 1
    assert manifest["counts"]["watch_trigger_onchain_flow_linked_records"] == sum(
        1 for record in artifact["records"] if record["linked_onchain_flow_context_ids"]
    )


def test_watch_triggers_recheck_unavailable_onchain_flow_without_false_relief(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_watch_triggers",
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "collect_onchain_flow_data": _noop_stage,
            "sync_ohlcv": _noop_stage,
            "sync_onchain_flow_history": _noop_stage,
            "build_market_data_views": _noop_stage,
            "build_onchain_flow_views": _noop_stage,
            "build_onchain_flow_context": _write_unavailable_onchain_flow_context,
            "evaluate_quant_strategies": _noop_stage,
            "evaluate_strategy_evaluation": _noop_stage,
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
    eth_triggers = [record for record in artifact["records"] if record["symbol"] == "ETHUSDT"]
    onchain_triggers = [record for record in eth_triggers if record["linked_onchain_flow_context_ids"]]

    assert onchain_triggers
    assert any(record["type"] == "recheck_next_run" for record in onchain_triggers)
    assert any("do not treat stale, unavailable, partial, or missing flow evidence as neutral" in record["condition"] for record in onchain_triggers)
    assert not any("on-chain flow stress clears" in record["condition"] for record in onchain_triggers)


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
            "evaluate_strategy_evaluation": _noop_stage,
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


def _write_stressed_derivatives_context(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "derivatives_market_context.json",
        {
            "schema_version": 1,
            "artifact_type": "derivatives_market_context",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "status": "warning",
            "records": [
                {
                    "context_id": "derivatives_context:funding_pressure:binance_usdm:ETHUSDT:8h:2026-06-05T00:00:00Z",
                    "context_type": "funding_pressure",
                    "data_class": "funding_rate",
                    "source": "binance_usdm",
                    "market_type": "usd_m_futures",
                    "symbol": "ETHUSDT",
                    "period": "8h",
                    "as_of": "2026-06-05T00:00:00Z",
                    "status": "succeeded",
                    "state": "extreme_positive_funding",
                    "severity": "high",
                    "confidence": "medium",
                    "metrics": {},
                    "thresholds": {},
                    "evidence": [],
                    "uncertainty": [],
                    "warnings": [],
                    "errors": [],
                    "source_artifacts": [
                        "analysis/derivatives_market_context.json",
                        "raw/derivatives_market_views.json",
                    ],
                }
            ],
            "counts": {"records": 1},
            "warnings": [],
            "errors": [],
            "source_artifacts": ["raw/derivatives_market_views.json"],
        },
    )
    run.manifest["artifacts"]["derivatives_market_context"] = "analysis/derivatives_market_context.json"
    return ["analysis/derivatives_market_context.json"]


def _write_upcoming_macro_calendar_context(config, run) -> list[str]:
    scheduled_at = "2026-06-06T18:00:00Z"
    write_json(
        run.analysis_dir / "macro_calendar_context.json",
        {
            "schema_version": 1,
            "artifact_type": "macro_calendar_context",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "status": "warning",
            "records": [
                {
                    "context_id": (
                        "macro_calendar_context:scheduled_catalyst:federal_reserve_fomc:US:"
                        f"Federal Reserve policy decision:{scheduled_at}"
                    ),
                    "context_type": "scheduled_catalyst",
                    "data_class": "central_bank_event",
                    "source": "federal_reserve_fomc",
                    "event_name": "Federal Reserve policy decision",
                    "region": "US",
                    "scheduled_at": scheduled_at,
                    "as_of": "2026-06-05T00:00:00Z",
                    "status": "succeeded",
                    "state": "upcoming",
                    "severity": "medium",
                    "confidence": "medium",
                    "time_to_event_hours": 42.0,
                    "affected_assets": ["ETHUSDT"],
                    "importance": "high",
                    "evidence": ["Federal Reserve policy decision calendar evidence."],
                    "uncertainty": ["Federal Reserve policy decision source uncertainty."],
                    "warnings": [],
                    "errors": [],
                    "source_artifacts": [
                        "analysis/macro_calendar_context.json",
                        "raw/macro_calendar_views.json",
                    ],
                }
            ],
            "counts": {"records": 1},
            "warnings": [],
            "errors": [],
            "source_artifacts": ["raw/macro_calendar_views.json"],
        },
    )
    run.manifest["artifacts"]["macro_calendar_context"] = "analysis/macro_calendar_context.json"
    return ["analysis/macro_calendar_context.json"]


def _write_stressed_onchain_flow_context(config, run) -> list[str]:
    _write_onchain_flow_context(
        run,
        [
            _onchain_flow_context_record(
                context_type="stablecoin_liquidity",
                data_class="stablecoin_supply",
                source="defillama_stablecoins",
                asset="ALL_STABLECOINS",
                chain="all",
                state="sharp_stablecoin_supply_contraction",
                severity="high",
                status="succeeded",
            )
        ],
    )
    return ["analysis/onchain_flow_context.json"]


def _write_unavailable_onchain_flow_context(config, run) -> list[str]:
    _write_onchain_flow_context(
        run,
        [
            _onchain_flow_context_record(
                context_type="exchange_flow_source_availability",
                data_class="exchange_flow_availability",
                source="public_exchange_flow_aggregate",
                asset="ALL_CONFIGURED_ASSETS",
                chain="all",
                state="source_unavailable",
                severity="medium",
                status="unavailable",
            )
        ],
    )
    return ["analysis/onchain_flow_context.json"]


def _write_onchain_flow_context(run, records: list[dict[str, Any]]) -> None:
    write_json(
        run.analysis_dir / "onchain_flow_context.json",
        {
            "schema_version": 1,
            "artifact_type": "onchain_flow_context",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "status": "warning",
            "records": records,
            "counts": {"records": len(records)},
            "warnings": [],
            "errors": [],
            "source_artifacts": ["raw/onchain_flow_views.json"],
        },
    )
    run.manifest["artifacts"]["onchain_flow_context"] = "analysis/onchain_flow_context.json"


def _onchain_flow_context_record(
    *,
    context_type: str,
    data_class: str,
    source: str,
    asset: str,
    chain: str,
    state: str,
    severity: str,
    status: str,
) -> dict[str, Any]:
    as_of = "2026-06-05T00:00:00Z"
    return {
        "context_id": f"onchain_flow_context:{context_type}:{source}:{asset}:{chain}:{as_of}",
        "context_type": context_type,
        "data_class": data_class,
        "source": source,
        "asset": asset,
        "chain": chain,
        "as_of": as_of,
        "status": status,
        "state": state,
        "severity": severity,
        "confidence": "medium",
        "source_availability": status,
        "metrics": {},
        "thresholds": {},
        "evidence": [{"source_artifact": "raw/onchain_flow_views.json", "summary": f"{context_type} evidence."}],
        "uncertainty": [f"{context_type} uncertainty."],
        "warnings": [],
        "errors": [],
        "source_artifacts": ["analysis/onchain_flow_context.json", "raw/onchain_flow_views.json"],
    }


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
