from __future__ import annotations

from typing import Any

from halpha.strategy.strategy_effectiveness_gates import build_strategy_effectiveness_gates


def test_strategy_effectiveness_gate_marks_effective_only_with_broad_evidence() -> None:
    artifact = _artifact(
        [
            _candidate(
                "broad_evidence",
                [
                    _evaluation(net=4.0, excess=2.0, trades=4),
                    _evaluation(net=3.0, excess=1.0, trades=4),
                ],
            )
        ]
    )

    gates = build_strategy_effectiveness_gates(artifact, {})
    record = gates["records"][0]

    assert gates["coverage"] == {
        "strategy_candidates": 1,
        "effective": 1,
        "watchlisted": 0,
        "rejected": 0,
        "insufficient_evidence": 0,
    }
    assert record["status"] == "effective"
    assert record["gate_inputs"]["walk_forward_stability"]["result_stability"] == "stable"
    assert record["gate_inputs"]["overfitting_risk"]["status"] == "low"
    assert "benchmark_coverage_met" in {item["code"] for item in record["reasons"]}


def test_strategy_effectiveness_gate_rejects_single_window_profit_alone() -> None:
    artifact = _artifact(
        [
            _candidate(
                "single_window_profit",
                [_evaluation(net=25.0, excess=20.0, trades=5, walk_forward=False)],
            )
        ]
    )

    gates = build_strategy_effectiveness_gates(artifact, {})
    record = gates["records"][0]
    reason_codes = {item["code"] for item in record["reasons"]}

    assert record["status"] == "insufficient_evidence"
    assert "insufficient_benchmark_coverage" in reason_codes
    assert "insufficient_walk_forward_evidence" in reason_codes
    assert gates["policy"]["single_window_profit_alone_can_be_effective"] is False


def test_strategy_effectiveness_gate_blocks_or_downgrades_risk_conditions() -> None:
    artifact = _artifact(
        [
            _candidate(
                "high_cost",
                [
                    _evaluation(net=4.0, excess=2.0, cost=2.5, trades=4),
                    _evaluation(net=3.0, excess=1.0, cost=2.0, trades=4),
                ],
            ),
            _candidate(
                "unstable_walk_forward",
                [
                    _evaluation(net=4.0, excess=2.0, trades=4, walk_forward_stability="unstable"),
                    _evaluation(net=3.0, excess=1.0, trades=4),
                ],
            ),
            _candidate(
                "low_trade_count",
                [
                    _evaluation(net=4.0, excess=2.0, trades=0),
                    _evaluation(net=3.0, excess=1.0, trades=0),
                ],
            ),
            _candidate(
                "short_sample",
                [
                    _evaluation(net=4.0, excess=2.0, trades=4, rows=20),
                    _evaluation(net=3.0, excess=1.0, trades=4, rows=20),
                ],
            ),
            _candidate(
                "elevated_overfitting",
                [
                    _evaluation(net=4.0, excess=2.0, trades=4),
                    _evaluation(net=3.0, excess=1.0, trades=4),
                ],
                overfitting_risk={"status": "elevated", "warnings": [], "evidence": []},
            ),
        ]
    )

    gates = build_strategy_effectiveness_gates(artifact, {})
    by_name = {record["strategy_name"]: record for record in gates["records"]}

    assert by_name["high_cost"]["status"] == "watchlisted"
    assert _reason_codes(by_name["high_cost"]) >= {"excessive_cost_drag", "elevated_overfitting_risk"}
    assert by_name["unstable_walk_forward"]["status"] == "watchlisted"
    assert _reason_codes(by_name["unstable_walk_forward"]) >= {
        "unstable_walk_forward",
        "elevated_overfitting_risk",
    }
    assert by_name["low_trade_count"]["status"] == "insufficient_evidence"
    assert "low_trade_count" in _reason_codes(by_name["low_trade_count"])
    assert by_name["short_sample"]["status"] == "insufficient_evidence"
    assert "insufficient_sample_quality" in _reason_codes(by_name["short_sample"])
    assert by_name["elevated_overfitting"]["status"] == "watchlisted"
    assert "elevated_overfitting_risk" in _reason_codes(by_name["elevated_overfitting"])


def test_strategy_effectiveness_gate_can_require_parameter_stability() -> None:
    artifact = _artifact(
        [
            _candidate(
                "needs_parameter_stability",
                [
                    _evaluation(net=4.0, excess=2.0, trades=4),
                    _evaluation(net=3.0, excess=1.0, trades=4),
                ],
            )
        ]
    )

    gates = build_strategy_effectiveness_gates(
        artifact,
        {"quant": {"effectiveness_gates": {"require_parameter_stability": True}}},
    )
    record = gates["records"][0]

    assert record["status"] == "insufficient_evidence"
    assert "parameter_stability_not_stable" in _reason_codes(record)


def test_strategy_effectiveness_gate_uses_performance_stability_contract() -> None:
    artifact = _artifact(
        [
            _candidate(
                "performance_sensitive",
                [
                    _evaluation(net=4.0, excess=2.0, trades=4),
                    _evaluation(net=3.0, excess=1.0, trades=4),
                ],
                parameter_stability=_parameter_stability(performance_status="sensitive"),
            )
        ]
    )

    gates = build_strategy_effectiveness_gates(
        artifact,
        {"quant": {"effectiveness_gates": {"require_parameter_stability": True}}},
    )
    record = gates["records"][0]

    assert record["status"] == "watchlisted"
    assert record["gate_inputs"]["parameter_stability"]["status"] == "fragile"
    assert record["gate_inputs"]["parameter_stability"]["performance_status"] == "sensitive"
    assert "parameter_stability_not_stable" in _reason_codes(record)


def test_strategy_effectiveness_gate_can_accept_unstable_walk_forward_when_not_required() -> None:
    artifact = _artifact(
        [
            _candidate(
                "unstable_allowed",
                [
                    _evaluation(net=4.0, excess=2.0, trades=4, walk_forward_stability="unstable"),
                    _evaluation(net=3.0, excess=1.0, trades=4, walk_forward_stability="unstable"),
                ],
            )
        ]
    )

    gates = build_strategy_effectiveness_gates(
        artifact,
        {
            "quant": {
                "effectiveness_gates": {
                    "require_walk_forward_stable": False,
                    "min_walk_forward_positive_net_return_window_pct": 0.0,
                }
            }
        },
    )
    record = gates["records"][0]

    assert record["status"] == "effective"
    assert record["gate_inputs"]["walk_forward_stability"]["result_stability"] == "unstable"
    assert record["gate_inputs"]["overfitting_risk"]["status"] == "low"
    assert "unstable_walk_forward" not in _reason_codes(record)


def test_strategy_effectiveness_gate_accepts_clean_signed_futures_evidence() -> None:
    artifact = _artifact(
        [
            _candidate(
                "clean_signed_futures",
                [
                    _evaluation(
                        net=4.0,
                        excess=2.0,
                        trades=4,
                        single_window_extra=_signed_futures_window(short_contribution=1.0),
                    ),
                    _evaluation(
                        net=3.0,
                        excess=1.0,
                        trades=4,
                        single_window_extra=_signed_futures_window(short_contribution=0.5),
                    ),
                ],
            )
        ]
    )

    gates = build_strategy_effectiveness_gates(artifact, {})
    record = gates["records"][0]

    assert record["status"] == "effective"
    assert record["gate_inputs"]["position_model"]["signed_single_leg"] is True
    assert record["gate_inputs"]["futures_risk"]["records_with_futures_diagnostics"] == 2
    assert record["gate_inputs"]["futures_risk"]["funding_status_counts"] == {"available": 2}
    assert "missing_funding_evidence" not in _reason_codes(record)


def test_strategy_effectiveness_gate_watchlists_futures_risk_conditions() -> None:
    artifact = _artifact(
        [
            _candidate(
                "crowded_signed_futures",
                [
                    _evaluation(
                        net=4.0,
                        excess=2.0,
                        trades=4,
                        single_window_extra=_signed_futures_window(
                            short_contribution=-1.0,
                            funding_status="unavailable",
                            funding_drag=2.0,
                            turnover=14.0,
                        ),
                    ),
                    _evaluation(
                        net=3.0,
                        excess=1.0,
                        trades=4,
                        single_window_extra=_signed_futures_window(
                            short_contribution=-0.5,
                            funding_status="unavailable",
                            funding_drag=1.5,
                            turnover=12.0,
                        ),
                    ),
                ],
            )
        ]
    )

    gates = build_strategy_effectiveness_gates(artifact, {})
    record = gates["records"][0]

    assert record["status"] == "watchlisted"
    assert _reason_codes(record) >= {
        "missing_funding_evidence",
        "excessive_funding_drag",
        "high_advanced_turnover",
        "weak_short_side_contribution",
    }


def test_strategy_effectiveness_gate_blocks_misaligned_multi_leg_evidence() -> None:
    artifact = _artifact(
        [
            _candidate(
                "misaligned_pair",
                [
                    _evaluation(net=4.0, excess=2.0, trades=4),
                    _evaluation(net=3.0, excess=1.0, trades=4),
                ],
                multi_leg_evaluation=_multi_leg_evaluation(status="insufficient_data", alignment_status="not_aligned"),
            )
        ]
    )

    gates = build_strategy_effectiveness_gates(artifact, {})
    record = gates["records"][0]

    assert record["status"] == "insufficient_evidence"
    assert record["gate_inputs"]["position_model"]["multi_leg"] is True
    assert record["gate_inputs"]["multi_leg_quality"]["alignment_status_counts"] == {"not_aligned": 1}
    assert "misaligned_multi_leg_evidence" in _reason_codes(record)


def test_strategy_effectiveness_gate_downgrades_optimization_robustness() -> None:
    artifact = _artifact(
        [
            _candidate(
                "overfit_optimized",
                [
                    _evaluation(net=4.0, excess=2.0, trades=4),
                    _evaluation(net=3.0, excess=1.0, trades=4),
                ],
                optimization_robustness={"status": "overfit_risk", "warnings": [], "errors": [], "summary": {}},
            )
        ]
    )

    gates = build_strategy_effectiveness_gates(artifact, {})
    record = gates["records"][0]

    assert record["status"] == "watchlisted"
    assert record["gate_inputs"]["optimization_robustness"]["status"] == "overfit_risk"
    assert "optimization_robustness_not_robust" in _reason_codes(record)


def test_strategy_effectiveness_gate_blocks_event_feature_insufficient_evidence() -> None:
    artifact = _artifact(
        [
            _candidate(
                "event_gap",
                [
                    _evaluation(net=4.0, excess=2.0, trades=4),
                    _evaluation(net=3.0, excess=1.0, trades=4),
                ],
                feature_availability={"status": "insufficient_data", "data_type": "market_anomaly"},
            )
        ]
    )

    gates = build_strategy_effectiveness_gates(artifact, {})
    record = gates["records"][0]

    assert record["status"] == "insufficient_evidence"
    assert record["gate_inputs"]["feature_availability"]["status_counts"] == {"insufficient_data": 1}
    assert "event_feature_insufficient_evidence" in _reason_codes(record)


def test_strategy_effectiveness_gate_rejects_advanced_strategy_when_performance_fails() -> None:
    artifact = _artifact(
        [
            _candidate(
                "bad_signed_futures",
                [
                    _evaluation(
                        net=-2.0,
                        excess=-3.0,
                        trades=4,
                        single_window_extra=_signed_futures_window(short_contribution=0.5),
                    ),
                    _evaluation(
                        net=-1.0,
                        excess=-2.0,
                        trades=4,
                        single_window_extra=_signed_futures_window(short_contribution=0.2),
                    ),
                ],
            )
        ]
    )

    gates = build_strategy_effectiveness_gates(artifact, {})
    record = gates["records"][0]

    assert record["status"] == "rejected"
    assert record["gate_inputs"]["position_model"]["signed_single_leg"] is True
    assert {"weak_net_performance", "weak_baseline_comparison"} <= _reason_codes(record)


def _artifact(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "strategy_experiment",
        "created_at": "2026-06-06T00:00:00Z",
        "source_artifacts": ["strategy_benchmark_suite.json"],
        "candidates": candidates,
    }


def _candidate(
    name: str,
    evaluations: list[dict[str, Any]],
    *,
    overfitting_risk: dict[str, Any] | None = None,
    parameter_stability: dict[str, Any] | None = None,
    optimization_robustness: dict[str, Any] | None = None,
    feature_availability: dict[str, Any] | None = None,
    multi_leg_evaluation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = {
        "strategy_name": name,
        "params": {},
        "status": "succeeded",
        "summary": {},
        "evaluations": evaluations,
        "warnings": [],
        "errors": [],
    }
    if overfitting_risk is not None:
        record["overfitting_risk"] = overfitting_risk
    if parameter_stability is not None:
        record["parameter_stability"] = parameter_stability
    if optimization_robustness is not None:
        record["optimization_robustness"] = optimization_robustness
    if feature_availability is not None:
        record["feature_availability"] = feature_availability
    if multi_leg_evaluation is not None:
        record["multi_leg_evaluation"] = multi_leg_evaluation
    return record


def _evaluation(
    *,
    net: float,
    excess: float,
    trades: int,
    rows: int = 120,
    cost: float = 0.2,
    drawdown: float = 8.0,
    walk_forward: bool = True,
    walk_forward_stability: str = "stable",
    single_window_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = {
        "status": "succeeded",
        "benchmark_status": "succeeded",
        "metrics": {
            "strategy": {
                "net_return_pct": net,
                "cost_drag_pct": cost,
                "max_drawdown_pct": -abs(drawdown),
            },
            "relative": {
                "excess_return_vs_buy_and_hold_pct": excess,
            },
            "trade": {
                "trade_count": trades,
            },
        },
        "single_window": {
            "sample": {
                "rows": rows,
            },
        },
        "warnings": [],
        "errors": [],
    }
    if single_window_extra is not None:
        record["single_window"].update(single_window_extra)
    if walk_forward:
        record["walk_forward"] = {
            "status": "succeeded",
            "summary": {
                "succeeded_windows": 3,
                "mean_net_return_pct": net / 3,
                "positive_net_return_window_pct": 66.666667,
                "result_stability": walk_forward_stability,
            },
            "warnings": [],
            "errors": [],
        }
    return record


def _signed_futures_window(
    *,
    short_contribution: float,
    funding_status: str = "available",
    funding_drag: float = 0.2,
    turnover: float = 2.0,
) -> dict[str, Any]:
    return {
        "execution_model": {"execution_model_id": "close_to_close_next_bar_signed_v1"},
        "trade_summary": {
            "long_trade_count": 2,
            "short_trade_count": 2,
            "side_flip_count": 1,
        },
        "futures_diagnostics": {
            "status": "succeeded",
            "contribution": {
                "long_gross_contribution_pct": 2.0,
                "short_gross_contribution_pct": short_contribution,
            },
            "exposure": {
                "short_time_pct": 40.0,
                "average_gross_exposure_pct": 80.0,
            },
            "turnover": {
                "total_turnover": turnover,
                "average_turnover": turnover / 10,
            },
            "funding": {
                "status": funding_status,
                "funding_drag_pct": funding_drag,
            },
            "warnings": [],
            "risk_warnings": [],
        },
    }


def _multi_leg_evaluation(*, status: str, alignment_status: str) -> dict[str, Any]:
    return {
        "record_type": "multi_leg_backtest",
        "status": status,
        "alignment": {
            "status": alignment_status,
            "omitted_rows": [{"leg_id": "ETHUSDT", "omitted_rows": 8}],
        },
        "strategy_metrics": {
            "turnover": 2.0,
            "average_gross_exposure": 1.0,
            "average_net_exposure": 0.0,
        },
        "warnings": [],
        "errors": [],
    }


def _parameter_stability(*, performance_status: str) -> dict[str, Any]:
    return {
        "enabled": True,
        "status": "stable",
        "signal_state_status": "stable",
        "performance_status": performance_status,
        "signal_state_stability": {
            "status": "stable",
            "reason_codes": ["direction_and_regime_agree"],
        },
        "performance_stability": {
            "status": performance_status,
            "reason_codes": ["metric_range_exceeds_threshold"],
            "metric_ranges": {
                "backtest_total_return_pct": {
                    "min": -4.0,
                    "max": 12.0,
                    "range": 16.0,
                    "threshold": 10.0,
                }
            },
        },
        "tested_combinations": 2,
        "valid_combinations": 2,
        "warnings": [],
    }


def _reason_codes(record: dict[str, Any]) -> set[str]:
    return {str(item["code"]) for item in record["reasons"]}
