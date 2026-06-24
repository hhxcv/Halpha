from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from halpha.config import load_config
from halpha.market.ohlcv_store import OHLCVParquetStore
from halpha.pipeline import run_pipeline
from halpha.pipeline_stages import OPERATION_ORDER
from halpha.storage import write_json


def test_outcome_evaluations_use_no_lookahead_window_and_directional_alignment(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv").write_records(
        [
            _ohlcv("2026-06-05T00:00:00Z", open_=99, high=101, low=98, close=100),
            _ohlcv("2026-06-06T00:00:00Z", open_=100, high=108, low=99, close=106),
            _ohlcv("2026-06-07T00:00:00Z", open_=106, high=120, low=105, close=118),
        ]
    )

    result = _run_with_targets(
        config,
        config_path,
        [_target("market_signal", direction="bullish", threshold_pct=5.0)],
    )

    artifact = _outcome_evaluations(result)
    manifest = _manifest(result)
    evaluation = artifact["evaluations"][0]

    assert result.succeeded is True
    assert artifact["artifact_type"] == "outcome_evaluations"
    assert artifact["status"] == "ok"
    assert evaluation["evaluation_status"] == "evaluated"
    assert evaluation["outcome_state"] == "aligned"
    assert evaluation["observation_window"] == {
        "source_as_of": "2026-06-05T00:00:00Z",
        "start": "2026-06-06T00:00:00Z",
        "end": "2026-06-06T00:00:00Z",
        "horizon_end": "2026-06-06T00:00:00Z",
        "sample_rows": 1,
        "no_lookahead": True,
        "excluded_at_or_before_source_as_of": True,
    }
    assert evaluation["metrics"]["anchor_open_time"] == "2026-06-05T00:00:00Z"
    assert evaluation["metrics"]["return_pct"] == 6.0
    assert evaluation["metrics"]["max_favorable_excursion_pct"] == 8.0
    assert evaluation["metrics"]["max_adverse_excursion_pct"] == -1.0
    assert evaluation["metrics"]["threshold_hit"] is True
    assert manifest["artifacts"]["outcome_evaluations"] == "analysis/outcome_evaluations.json"
    assert manifest["counts"]["outcome_evaluations"] == 1
    assert manifest["counts"]["outcome_evaluations_evaluated"] == 1
    assert _stage(manifest, "evaluate_outcomes")["artifacts"] == ["analysis/outcome_evaluations.json"]


def test_outcome_evaluations_keep_pending_targets_visible(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv").write_records(
        [_ohlcv("2026-06-05T00:00:00Z", close=100), _ohlcv("2026-06-06T00:00:00Z", close=106)]
    )

    result = _run_with_targets(
        config,
        config_path,
        [
            _target(
                "market_signal",
                direction="bullish",
                matures_at="2026-06-08T00:00:00Z",
                horizon_end="2026-06-08T00:00:00Z",
                maturity_status="pending",
            )
        ],
        now=datetime(2026, 6, 6, 0, 0, tzinfo=UTC),
    )

    evaluation = _outcome_evaluations(result)["evaluations"][0]
    manifest = _manifest(result)

    assert evaluation["evaluation_status"] == "pending"
    assert evaluation["outcome_state"] == "unresolved"
    assert evaluation["metrics"] == {}
    assert evaluation["observation_window"]["sample_rows"] == 0
    assert manifest["counts"]["outcome_evaluations_pending"] == 1


def test_outcome_evaluations_record_insufficient_data_without_fabricated_metrics(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv").write_records(
        [_ohlcv("2026-06-05T00:00:00Z", close=100)]
    )

    result = _run_with_targets(
        config,
        config_path,
        [_target("market_signal", direction="bullish")],
    )

    artifact = _outcome_evaluations(result)
    evaluation = artifact["evaluations"][0]
    manifest = _manifest(result)

    assert artifact["status"] == "warning"
    assert evaluation["evaluation_status"] == "insufficient_data"
    assert evaluation["outcome_state"] == "insufficient_data"
    assert evaluation["metrics"] == {}
    assert "No OHLCV rows were available strictly after target source_as_of" in evaluation["warnings"][0]
    assert manifest["counts"]["outcome_evaluations_insufficient_data"] == 1


def test_outcome_evaluations_record_strategy_gate_context_and_costs(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv").write_records(
        [
            _ohlcv("2026-06-05T00:00:00Z", close=100),
            _ohlcv("2026-06-06T00:00:00Z", high=107, low=99, close=104),
        ]
    )

    result = _run_with_targets(
        config,
        config_path,
        [
            _target(
                "strategy_gate",
                direction="bullish",
                expected_extra={
                    "gate_status": "effective",
                    "strategy_name": "tsmom_vol_scaled",
                    "cost_context": {"fees_bps": 10, "slippage_bps": 5},
                },
            ),
            _target("unsupported_kind", record_id="unsupported:one"),
        ],
    )

    artifact = _outcome_evaluations(result)
    by_kind = {evaluation["target_kind"]: evaluation for evaluation in artifact["evaluations"]}

    assert artifact["counts"]["evaluated"] == 1
    assert artifact["counts"]["skipped"] == 1
    assert by_kind["strategy_gate"]["evaluation_status"] == "evaluated"
    assert by_kind["strategy_gate"]["outcome_state"] == "aligned"
    assert by_kind["strategy_gate"]["metrics"]["cost_context"] == {"fees_bps": 10, "slippage_bps": 5}
    assert by_kind["unsupported_kind"]["evaluation_status"] == "skipped"
    assert by_kind["unsupported_kind"]["outcome_state"] == "skipped"


def test_outcome_evaluations_classify_follow_through_states(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    targets = [
        _target(
            "event_assessment",
            record_id="event:confirmed",
            expected_extra=_event_expected("supports_existing_view", "neutral"),
        ),
        _target(
            "event_assessment",
            record_id="event:unresolved",
            expected_extra=_event_expected("supports_existing_view", "neutral"),
        ),
        _target(
            "event_assessment",
            record_id="event:stale",
            expected_extra=_event_expected("supports_existing_view", "neutral"),
        ),
        _target(
            "alert_decision",
            record_id="alert:confirmed",
            expected_extra={
                "priority": "P1",
                "attention_decision": "escalate",
            },
        ),
        _target(
            "decision_recommendation",
            record_id="decision:contradicted",
            expected_extra={
                "action_level": "TRY_SMALL",
                "decision_bias": "tentative_constructive",
            },
        ),
        _target(
            "watch_trigger",
            record_id="watch:missing",
            expected_extra={
                "trigger_type": "confirmation",
                "condition": "Confirmation remains required.",
            },
        ),
    ]

    result = _run_with_targets(
        config,
        config_path,
        targets,
        stage_overrides={
            "build_event_intelligence_assessment": lambda config, run: _write_current_event_assessments(
                run,
                [
                    _event_record("event:confirmed", "supports_existing_view", "neutral"),
                    _event_record("event:unresolved", "insufficient_evidence", "unknown"),
                    _event_record("event:stale", "supports_existing_view", "neutral", stale=True),
                ],
            ),
            "build_decision_recommendations": lambda config, run: _write_current_decisions(
                run,
                [
                    {
                        "record_id": "decision:contradicted",
                        "symbol": "BTCUSDT",
                        "timeframe": "1d",
                        "action_level": "AVOID",
                        "decision_bias": "defensive_avoid",
                        "source_artifacts": ["analysis/risk_assessment.json"],
                        "uncertainty": ["Decision evidence changed."],
                    }
                ],
            ),
            "build_alert_decisions": lambda config, run: _write_current_alert_decisions(
                run,
                [
                    {
                        "alert_decision_id": "alert:confirmed",
                        "scope": {"symbol": "BTCUSDT", "timeframe": "1d"},
                        "priority": "P1",
                        "attention_decision": "escalate",
                        "linked_event_assessment_ids": ["event:confirmed"],
                        "source_artifacts": ["analysis/event_intelligence_assessment.json"],
                        "uncertainty": ["Alert remains relevant."],
                    }
                ],
            ),
        },
    )

    artifact = _outcome_evaluations(result)
    by_target = {evaluation["target_id"]: evaluation for evaluation in artifact["evaluations"]}
    confirmed = by_target["outcome_target:event_assessment:source-run:event:confirmed"]
    unresolved = by_target["outcome_target:event_assessment:source-run:event:unresolved"]
    stale = by_target["outcome_target:event_assessment:source-run:event:stale"]
    alert = by_target["outcome_target:alert_decision:source-run:alert:confirmed"]
    contradicted = by_target["outcome_target:decision_recommendation:source-run:decision:contradicted"]
    insufficient = by_target["outcome_target:watch_trigger:source-run:watch:missing"]

    assert confirmed["outcome_state"] == "confirmed"
    assert confirmed["metrics"]["confirming_evidence_count"] == 1
    assert alert["outcome_state"] == "confirmed"
    assert alert["metrics"]["matched_record_ids"] == ["alert:confirmed"]
    assert contradicted["outcome_state"] == "contradicted"
    assert contradicted["metrics"]["contradicting_evidence_count"] == 1
    assert unresolved["outcome_state"] == "unresolved"
    assert "follow_through_unresolved" in unresolved["warnings"]
    assert stale["evaluation_status"] == "stale"
    assert stale["outcome_state"] == "stale"
    assert "stale_event" in stale["warnings"]
    assert insufficient["evaluation_status"] == "insufficient_data"
    assert insufficient["outcome_state"] == "insufficient_data"
    assert insufficient["uncertainty"] == ["No matched follow-through record was available."]
    assert "analysis/event_intelligence_assessment.json" in confirmed["source_artifacts"]
    assert "analysis/text_event_signals.json" in confirmed["source_artifacts"]
    assert "analysis/alert_decisions.json" in alert["source_artifacts"]
    assert "analysis/decision_recommendations.json" in contradicted["source_artifacts"]
    assert "analysis/risk_assessment.json" in contradicted["source_artifacts"]
    assert artifact["counts"]["by_outcome_state"] == {
        "confirmed": 2,
        "contradicted": 1,
        "insufficient_data": 1,
        "stale": 1,
        "unresolved": 1,
    }


def _run_with_targets(
    config: dict[str, Any],
    config_path: Path,
    targets: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    stage_overrides: dict[str, Any] | None = None,
):
    overrides = {
        "build_outcome_targets": lambda config, run: _write_outcome_targets(run, targets),
    }
    if stage_overrides:
        overrides.update(stage_overrides)
    return run_pipeline(
        config,
        config_path=config_path,
        until_stage="synthesize_intelligence",
        stage_handlers=_handlers_for_until("evaluate_outcomes", overrides),
        now=now or datetime(2026, 6, 7, 0, 0, tzinfo=UTC),
    )


def _handlers_for_until(stage: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    handlers = {name: _noop_stage for name in OPERATION_ORDER if name != stage}
    if overrides:
        handlers.update(overrides)
    return handlers


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  output_dir: runs
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
quant:
  enabled: true
  engine: vectorbt
  strategies:
    - name: tsmom_vol_scaled
text:
  enabled: false
report:
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _target(
    target_kind: str,
    *,
    record_id: str | None = None,
    direction: str | None = None,
    threshold_pct: float | None = None,
    matures_at: str = "2026-06-06T00:00:00Z",
    horizon_end: str = "2026-06-06T00:00:00Z",
    maturity_status: str = "matured",
    expected_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target_id = f"outcome_target:{target_kind}:source-run:{record_id or 'one'}"
    expected = {"observation_type": "directional_market_move"}
    if direction is not None:
        expected["direction"] = direction
    if threshold_pct is not None:
        expected["threshold_pct"] = threshold_pct
    if expected_extra:
        expected.update(expected_extra)
    return {
        "target_id": target_id,
        "target_kind": target_kind,
        "source_run_id": "source-run",
        "source_artifact": "analysis/outcome_targets_source.json",
        "source_record_id": record_id or f"{target_kind}:record",
        "source_record_type": target_kind,
        "source_created_at": "2026-06-05T00:00:00Z",
        "source_as_of": "2026-06-05T00:00:00Z",
        "source": "binance",
        "asset": "BTCUSDT",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "horizon": {
            "horizon_id": f"{target_kind}:1d:next_candle",
            "horizon_kind": "next_candle",
            "duration": "1d",
            "start_at": "2026-06-05T00:00:00Z",
            "matures_at": matures_at,
            "expires_at": None,
            "observation_window_start": "2026-06-05T00:00:00Z",
            "observation_window_end": horizon_end,
        },
        "maturity_status": maturity_status,
        "expected_observation": expected,
        "evidence": ["target evidence"],
        "uncertainty": [],
        "warnings": [],
        "errors": [],
        "source_artifacts": ["analysis/outcome_targets_source.json"],
    }


def _write_outcome_targets(run, targets: list[dict[str, Any]]) -> list[str]:
    write_json(
        run.analysis_dir / "outcome_targets.json",
        {
            "schema_version": 1,
            "artifact_type": "outcome_targets",
            "run_id": run.run_id,
            "created_at": "2026-06-06T00:00:00Z",
            "status": "ok",
            "previous_run": {"status": "found", "run_id": "source-run"},
            "target_policy": {},
            "targets": targets,
            "skipped_records": [],
            "counts": {"targets": len(targets)},
            "source_artifacts": ["analysis/outcome_targets_source.json"],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["outcome_targets"] = "analysis/outcome_targets.json"
    return ["analysis/outcome_targets.json"]


def _event_expected(decision_impact: str, risk_effect: str) -> dict[str, Any]:
    return {
        "event_severity": "medium",
        "decision_impact": decision_impact,
        "risk_effect": risk_effect,
        "watch_relevance": "confirmation",
    }


def _event_record(
    record_id: str,
    decision_impact: str,
    risk_effect: str,
    *,
    stale: bool = False,
) -> dict[str, Any]:
    return {
        "assessment_id": record_id,
        "status": "degraded" if stale else "succeeded",
        "scope": {"symbol": "BTCUSDT", "timeframe": "1d"},
        "event_severity": "medium",
        "decision_impact": decision_impact,
        "risk_effect": risk_effect,
        "watch_relevance": "confirmation",
        "evidence": [{"type": "event_signal", "event_signal_id": record_id}],
        "downgrade_reasons": ["stale_event"] if stale else [],
        "uncertainty": ["Event follow-through uncertainty."],
        "source_artifacts": ["analysis/text_event_signals.json"],
        "warnings": ["stale_event"] if stale else [],
    }


def _write_current_event_assessments(run, records: list[dict[str, Any]]) -> list[str]:
    write_json(
        run.analysis_dir / "event_intelligence_assessment.json",
        {
            "schema_version": 1,
            "artifact_type": "event_intelligence_assessment",
            "run_id": run.run_id,
            "created_at": "2026-06-07T00:00:00Z",
            "source_artifacts": ["analysis/text_event_signals.json"],
            "records": records,
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["event_intelligence_assessment"] = "analysis/event_intelligence_assessment.json"
    return ["analysis/event_intelligence_assessment.json"]


def _write_current_decisions(run, records: list[dict[str, Any]]) -> list[str]:
    write_json(
        run.analysis_dir / "decision_recommendations.json",
        {
            "schema_version": 1,
            "artifact_type": "decision_recommendations",
            "run_id": run.run_id,
            "created_at": "2026-06-07T00:00:00Z",
            "source_artifacts": ["analysis/risk_assessment.json"],
            "records": records,
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["decision_recommendations"] = "analysis/decision_recommendations.json"
    return ["analysis/decision_recommendations.json"]


def _write_current_alert_decisions(run, records: list[dict[str, Any]]) -> list[str]:
    write_json(
        run.analysis_dir / "alert_decisions.json",
        {
            "schema_version": 1,
            "artifact_type": "alert_decisions",
            "run_id": run.run_id,
            "created_at": "2026-06-07T00:00:00Z",
            "source_artifacts": ["analysis/event_intelligence_assessment.json"],
            "records": records,
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["alert_decisions"] = "analysis/alert_decisions.json"
    return ["analysis/alert_decisions.json"]


def _ohlcv(
    open_time: str,
    *,
    source: str = "binance",
    symbol: str = "BTCUSDT",
    timeframe: str = "1d",
    open_: float | None = None,
    high: float | None = None,
    low: float | None = None,
    close: float,
) -> dict[str, Any]:
    return {
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "open_time": open_time,
        "open": open_ if open_ is not None else close,
        "high": high if high is not None else close,
        "low": low if low is not None else close,
        "close": close,
        "volume": 10,
        "fetched_at": "2026-06-07T00:00:00Z",
    }


def _outcome_evaluations(result) -> dict[str, Any]:
    return json.loads((result.run.analysis_dir / "outcome_evaluations.json").read_text(encoding="utf-8"))


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
