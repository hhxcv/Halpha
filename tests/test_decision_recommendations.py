from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from halpha.config import load_config
from halpha.pipeline import run_pipeline
from halpha.pipeline_stages import OPERATION_ORDER
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


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_decision_recommendations_apply_taxonomy_and_policy_gates(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="synthesize_intelligence",
        stage_handlers=_decision_handlers({
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "sync_ohlcv": _noop_stage,
            "build_market_data_views": _noop_stage,
            "evaluate_quant_strategies": _noop_stage,
            "evaluate_strategy_evaluation": _noop_stage,
            "build_market_signals": _write_market_signals,
            "build_market_signal_material": _noop_stage,
            "build_market_regime_assessment": _write_market_regime_assessment,
            "build_risk_assessment": _write_risk_assessment,
        }),
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


def test_decision_recommendations_downgrade_do_with_derivatives_stress(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = _run_decision_with_derivatives(config, config_path, _write_stressed_derivatives_context)

    assert result.succeeded is True
    artifact = _decision_recommendations(result)
    eth = next(record for record in artifact["records"] if record["symbol"] == "ETHUSDT")
    manifest = _manifest(result)

    assert eth["action_level"] == "WATCH"
    assert eth["decision_bias"] == "wait_for_confirmation"
    assert eth["downgrade_reasons"] == ["high_severity_derivatives_context"]
    assert eth["linked_derivatives_context_ids"] == [
        "derivatives_context:funding_pressure:binance_usdm:ETHUSDT:8h:2026-06-05T00:00:00Z"
    ]
    assert any("derivatives_context_risk" in item for item in eth["risk_conditions"])
    assert any("derivatives_context_blocking" in item for item in eth["risk_conditions"])
    assert any("derivatives_context funding_pressure" in item for item in eth["evidence"])
    assert any("Derivatives context downgraded" in item for item in eth["warnings"])
    assert "analysis/derivatives_market_context.json" in eth["source_artifacts"]
    assert manifest["counts"]["decision_recommendation_derivatives_context_records"] == 1
    assert manifest["counts"]["decision_recommendation_derivatives_linked_records"] == 1


def test_decision_recommendations_do_not_upgrade_with_stale_derivatives_context(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = _run_decision_with_derivatives(config, config_path, _write_stale_derivatives_context)

    assert result.succeeded is True
    artifact = _decision_recommendations(result)
    eth = next(record for record in artifact["records"] if record["symbol"] == "ETHUSDT")

    assert eth["action_level"] == "DO"
    assert eth["downgrade_reasons"] == []
    assert eth["linked_derivatives_context_ids"]
    assert any("derivatives_context_uncertainty" in item for item in eth["risk_conditions"])


def test_decision_recommendations_downgrade_do_with_macro_calendar_catalyst(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = _run_decision_with_macro_calendar(config, config_path, _write_eth_upcoming_macro_calendar_context)

    assert result.succeeded is True
    artifact = _decision_recommendations(result)
    manifest = _manifest(result)
    eth = next(record for record in artifact["records"] if record["symbol"] == "ETHUSDT")

    assert eth["action_level"] == "TRY_SMALL"
    assert eth["decision_bias"] == "tentative_constructive"
    assert eth["downgrade_reasons"] == ["macro_calendar_catalyst_caution"]
    assert eth["linked_macro_calendar_context_ids"] == [
        "macro_calendar_context:scheduled_catalyst:federal_reserve_fomc:US:Federal Reserve policy decision:2026-06-06T18:00:00Z"
    ]
    assert any("macro_calendar_context_risk" in item for item in eth["risk_conditions"])
    assert any("macro_calendar_context scheduled_catalyst" in item for item in eth["evidence"])
    assert any("Macro calendar context downgraded" in item for item in eth["warnings"])
    assert any("post-event confirmation" in item for item in eth["invalidation_conditions"])
    assert "analysis/macro_calendar_context.json" in eth["source_artifacts"]
    assert manifest["counts"]["decision_recommendation_macro_calendar_context_records"] == 1
    assert manifest["counts"]["decision_recommendation_macro_calendar_linked_records"] == 1


def test_decision_recommendations_preserve_conflict_gate_with_macro_calendar_context(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = _run_decision_with_macro_calendar(config, config_path, _write_btc_upcoming_macro_calendar_context)

    assert result.succeeded is True
    artifact = _decision_recommendations(result)
    btc = next(record for record in artifact["records"] if record["symbol"] == "BTCUSDT")

    assert btc["action_level"] == "WATCH"
    assert btc["decision_bias"] == "wait_for_conflict_resolution"
    assert btc["downgrade_reasons"] == []
    assert btc["conflicts"]
    assert btc["linked_macro_calendar_context_ids"]
    assert any("macro_calendar_context_risk" in item for item in btc["risk_conditions"])
    assert any("risk_level=high" in item for item in btc["risk_conditions"])


def test_decision_recommendations_downgrade_do_with_unavailable_onchain_flow_context(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = _run_decision_with_onchain_flow(config, config_path, _write_unavailable_onchain_flow_context)

    assert result.succeeded is True
    artifact = _decision_recommendations(result)
    manifest = _manifest(result)
    eth = next(record for record in artifact["records"] if record["symbol"] == "ETHUSDT")

    assert eth["action_level"] == "WATCH"
    assert eth["decision_bias"] == "wait_for_confirmation"
    assert eth["downgrade_reasons"] == ["onchain_flow_source_uncertainty"]
    assert eth["linked_onchain_flow_context_ids"] == [
        "onchain_flow_context:exchange_flow_source_availability:public_exchange_flow_aggregate:ALL_CONFIGURED_ASSETS:all:2026-06-05T00:00:00Z"
    ]
    assert any("onchain_flow_context_risk" in item for item in eth["risk_conditions"])
    assert any("onchain_flow_context_uncertainty" in item for item in eth["risk_conditions"])
    assert any("onchain_flow_context exchange_flow_source_availability" in item for item in eth["evidence"])
    assert any("On-chain flow context downgraded" in item for item in eth["warnings"])
    assert "analysis/onchain_flow_context.json" in eth["source_artifacts"]
    assert manifest["counts"]["decision_recommendation_onchain_flow_context_records"] == 1
    assert manifest["counts"]["decision_recommendation_onchain_flow_linked_records"] > 0


def test_decision_recommendations_treat_stale_onchain_flow_as_uncertainty(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = _run_decision_with_onchain_flow(config, config_path, _write_stale_onchain_flow_context)

    assert result.succeeded is True
    artifact = _decision_recommendations(result)
    eth = next(record for record in artifact["records"] if record["symbol"] == "ETHUSDT")

    assert eth["action_level"] == "WATCH"
    assert eth["downgrade_reasons"] == ["onchain_flow_source_uncertainty"]
    assert any("missing or degraded on-chain flow evidence" in item for item in eth["evidence"])
    assert any("onchain_flow_context_uncertainty" in item for item in eth["risk_conditions"])


def test_decision_recommendations_do_not_fabricate_actions_when_upstream_is_empty(
    tmp_path: Path,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="synthesize_intelligence",
        stage_handlers=_decision_handlers({
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "sync_ohlcv": _noop_stage,
            "build_market_data_views": _noop_stage,
            "evaluate_quant_strategies": _noop_stage,
            "evaluate_strategy_evaluation": _noop_stage,
            "build_market_signals": _write_empty_market_signals,
            "build_market_signal_material": _noop_stage,
            "build_market_regime_assessment": _write_empty_market_regime_assessment,
            "build_risk_assessment": _write_empty_risk_assessment,
        }),
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
        stage_handlers=_decision_handlers({
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "sync_ohlcv": _noop_stage,
            "build_market_data_views": _noop_stage,
            "evaluate_quant_strategies": _noop_stage,
            "evaluate_strategy_evaluation": _noop_stage,
            "build_market_signals": _noop_stage,
            "build_market_signal_material": _noop_stage,
            "build_analysis_materials": _noop_stage,
            "build_research_context": _noop_stage,
            "build_codex_context": _noop_stage,
            "run_codex_report": _noop_stage,
        }),
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


def _run_decision_with_derivatives(config: dict[str, Any], config_path: Path, derivatives_stage):
    return run_pipeline(
        config,
        config_path=config_path,
        until_stage="synthesize_intelligence",
        stage_handlers=_decision_handlers({
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "sync_ohlcv": _noop_stage,
            "build_market_data_views": _noop_stage,
            "build_derivatives_market_context": derivatives_stage,
            "evaluate_quant_strategies": _noop_stage,
            "evaluate_strategy_evaluation": _noop_stage,
            "build_market_signals": _write_market_signals,
            "build_market_signal_material": _noop_stage,
            "build_market_regime_assessment": _write_market_regime_assessment,
            "build_risk_assessment": _write_risk_assessment,
        }),
    )


def _run_decision_with_macro_calendar(config: dict[str, Any], config_path: Path, macro_stage):
    return run_pipeline(
        config,
        config_path=config_path,
        until_stage="synthesize_intelligence",
        stage_handlers=_decision_handlers({
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "sync_ohlcv": _noop_stage,
            "build_market_data_views": _noop_stage,
            "build_macro_calendar_context": macro_stage,
            "evaluate_quant_strategies": _noop_stage,
            "evaluate_strategy_evaluation": _noop_stage,
            "build_market_signals": _write_market_signals,
            "build_market_signal_material": _noop_stage,
            "build_market_regime_assessment": _write_market_regime_assessment,
            "build_risk_assessment": _write_risk_assessment,
        }),
    )


def _run_decision_with_onchain_flow(config: dict[str, Any], config_path: Path, onchain_stage):
    return run_pipeline(
        config,
        config_path=config_path,
        until_stage="synthesize_intelligence",
        stage_handlers=_decision_handlers({
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "collect_onchain_flow_data": _noop_stage,
            "sync_ohlcv": _noop_stage,
            "sync_onchain_flow_history": _noop_stage,
            "build_market_data_views": _noop_stage,
            "build_onchain_flow_views": _noop_stage,
            "build_onchain_flow_context": onchain_stage,
            "evaluate_quant_strategies": _noop_stage,
            "evaluate_strategy_evaluation": _noop_stage,
            "build_market_signals": _write_market_signals,
            "build_market_signal_material": _noop_stage,
            "build_market_regime_assessment": _write_market_regime_assessment,
            "build_risk_assessment": _write_risk_assessment,
        }),
    )


def _decision_handlers(overrides: dict[str, Any]) -> dict[str, Any]:
    handlers = {
        operation: _noop_stage
        for operation in OPERATION_ORDER
        if operation != "build_decision_recommendations"
    }
    handlers.update(overrides)
    return handlers


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
            "source_artifacts": [],
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


def _write_stressed_derivatives_context(config, run) -> list[str]:
    _write_derivatives_context(
        run,
        [
            _derivatives_context_record(
                symbol="ETHUSDT",
                context_type="funding_pressure",
                data_class="funding_rate",
                state="extreme_positive_funding",
                severity="high",
                status="succeeded",
            )
        ],
    )
    return ["analysis/derivatives_market_context.json"]


def _write_stale_derivatives_context(config, run) -> list[str]:
    _write_derivatives_context(
        run,
        [
            _derivatives_context_record(
                symbol="ETHUSDT",
                context_type="liquidation_availability",
                data_class="liquidation_summary",
                state="stale",
                severity="unknown",
                status="stale",
            )
        ],
    )
    return ["analysis/derivatives_market_context.json"]


def _write_eth_upcoming_macro_calendar_context(config, run) -> list[str]:
    _write_macro_calendar_context(run, [_macro_calendar_context_record("ETHUSDT")])
    return ["analysis/macro_calendar_context.json"]


def _write_btc_upcoming_macro_calendar_context(config, run) -> list[str]:
    _write_macro_calendar_context(run, [_macro_calendar_context_record("BTCUSDT")])
    return ["analysis/macro_calendar_context.json"]


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


def _write_stale_onchain_flow_context(config, run) -> list[str]:
    _write_onchain_flow_context(
        run,
        [
            _onchain_flow_context_record(
                context_type="stablecoin_liquidity",
                data_class="stablecoin_supply",
                source="defillama_stablecoins",
                asset="ALL_STABLECOINS",
                chain="all",
                state="stale",
                severity="medium",
                status="stale",
            )
        ],
    )
    return ["analysis/onchain_flow_context.json"]


def _write_macro_calendar_context(run, records: list[dict[str, Any]]) -> None:
    write_json(
        run.analysis_dir / "macro_calendar_context.json",
        {
            "schema_version": 1,
            "artifact_type": "macro_calendar_context",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "status": "warning",
            "records": records,
            "counts": {"records": len(records)},
            "warnings": [],
            "errors": [],
            "source_artifacts": ["raw/macro_calendar_views.json"],
        },
    )
    run.manifest["artifacts"]["macro_calendar_context"] = "analysis/macro_calendar_context.json"


def _macro_calendar_context_record(symbol: str) -> dict[str, Any]:
    scheduled_at = "2026-06-06T18:00:00Z"
    return {
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
        "affected_assets": [symbol],
        "importance": "high",
        "evidence": ["Federal Reserve policy decision calendar evidence."],
        "uncertainty": ["Federal Reserve policy decision source uncertainty."],
        "warnings": [],
        "errors": [],
        "source_artifacts": ["analysis/macro_calendar_context.json", "raw/macro_calendar_views.json"],
    }


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


def _write_derivatives_context(run, records: list[dict[str, Any]]) -> None:
    write_json(
        run.analysis_dir / "derivatives_market_context.json",
        {
            "schema_version": 1,
            "artifact_type": "derivatives_market_context",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "status": "warning",
            "records": records,
            "counts": {"records": len(records)},
            "warnings": [],
            "errors": [],
            "source_artifacts": ["raw/derivatives_market_views.json"],
        },
    )
    run.manifest["artifacts"]["derivatives_market_context"] = "analysis/derivatives_market_context.json"


def _derivatives_context_record(
    *,
    symbol: str,
    context_type: str,
    data_class: str,
    state: str,
    severity: str,
    status: str,
) -> dict[str, Any]:
    period = "source_availability" if context_type == "liquidation_availability" else "8h"
    return {
        "context_id": f"derivatives_context:{context_type}:binance_usdm:{symbol}:{period}:2026-06-05T00:00:00Z",
        "context_type": context_type,
        "data_class": data_class,
        "source": "binance_usdm",
        "market_type": "usd_m_futures",
        "symbol": symbol,
        "period": period,
        "as_of": "2026-06-05T00:00:00Z",
        "status": status,
        "state": state,
        "severity": severity,
        "confidence": "medium",
        "metrics": {},
        "thresholds": {},
        "evidence": [],
        "uncertainty": [],
        "warnings": [],
        "errors": [],
        "source_artifacts": ["analysis/derivatives_market_context.json", "raw/derivatives_market_views.json"],
    }


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
            "analysis/quant_strategy_runs.json",
            "raw/market_data_views.json",
        ],
    }


def _decision_recommendations(result) -> dict[str, Any]:
    return json.loads((result.run.analysis_dir / "decision_recommendations.json").read_text(encoding="utf-8"))


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
