from __future__ import annotations

from typing import Any

from halpha.strategy_effectiveness_gates import build_strategy_effectiveness_gates


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


def _reason_codes(record: dict[str, Any]) -> set[str]:
    return {str(item["code"]) for item in record["reasons"]}
