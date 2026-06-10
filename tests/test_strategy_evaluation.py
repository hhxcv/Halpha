from __future__ import annotations

import json
import math
from datetime import date, timedelta
from typing import Any

from halpha.quant.strategy_evaluation import evaluate_single_window_backtest, evaluate_walk_forward_backtest


def test_single_window_backtest_golden_entry_exit_path_is_hand_verifiable() -> None:
    rows = [
        _record("2026-06-01T00:00:00Z", 100),
        _record("2026-06-02T00:00:00Z", 110),
        _record("2026-06-03T00:00:00Z", 99),
        _record("2026-06-04T00:00:00Z", 108.9),
        _record("2026-06-05T00:00:00Z", 108.9),
    ]

    result = evaluate_single_window_backtest(
        strategy=_strategy(),
        market_identity=_market_identity(),
        ohlcv_rows=rows,
        signal_records=_signal_records(rows, [0, 1, 1, 0, 1]),
        cost_assumptions={"fees_bps": 10, "slippage_bps": 5},
    )

    # Hand check:
    # close returns: +10%, -10%, +10%, 0%
    # next-bar positions from prior signals: 0, 1, 1, 0
    # turnovers: 0, 1, 0, 1
    # cost rate: (10 + 5) / 10000 = 0.0015 per one-way turnover
    # gross returns: 0%, -10%, +10%, 0%
    # net returns: 0%, -10.15%, +10%, -0.15%
    # gross equity: 1.0 * 1.0 * 0.9 * 1.1 * 1.0 = 0.99
    # net equity: 1.0 * 1.0 * 0.8985 * 1.1 * 0.9985 = 0.986867475
    assert result["status"] == "succeeded"
    assert result["execution_model"]["lookahead_policy"] == "no_same_bar_execution"
    assert result["cost_assumptions"] == {
        "fees_bps": 10.0,
        "slippage_bps": 5.0,
        "total_one_way_bps": 15.0,
    }
    assert _curve_values(result, "position") == [0.0, 0.0, 1.0, 1.0, 0.0]
    assert _curve_values(result, "turnover") == [0.0, 0.0, 1.0, 0.0, 1.0]
    assert _curve_values(result, "period_gross_return_pct") == [None, 0.0, -10.0, 10.0, 0.0]
    assert _curve_values(result, "period_net_return_pct") == [None, 0.0, -10.15, 10.0, -0.15]
    assert _curve_values(result, "cost_pct") == [0.0, 0.0, 0.15, 0.0, 0.15]
    assert _curve_values(result, "gross_equity") == [1.0, 1.0, 0.9, 0.99, 0.99]
    assert _curve_values(result, "net_equity") == [1.0, 1.0, 0.8985, 0.98835, 0.986867]
    assert result["strategy_metrics"]["gross_return_pct"] == -1.0
    assert result["strategy_metrics"]["net_return_pct"] == -1.313252
    assert result["strategy_metrics"]["total_cost_pct"] == 0.3
    assert result["strategy_metrics"]["cost_drag_pct"] == 0.313252
    assert result["strategy_metrics"]["max_drawdown_pct"] == -10.15
    assert result["strategy_metrics"]["final_equity"] == 0.986867
    assert result["drawdown_summary"] == {
        "max_drawdown_pct": -10.15,
        "max_drawdown_start": "2026-06-02T00:00:00Z",
        "max_drawdown_end": "2026-06-03T00:00:00Z",
    }
    assert result["trade_summary"] == {
        "trade_count": 1,
        "completed_trade_count": 1,
        "open_trade_count": 0,
        "hit_rate_pct": 0.0,
        "turnover": 2.0,
        "exposure_pct": 50.0,
        "average_holding_bars": 2.0,
    }
    assert result["baseline_metrics"]["buy_and_hold"]["net_return_pct"] == 8.7515
    assert result["baseline_metrics"]["buy_and_hold"]["max_drawdown_pct"] == -10.0
    assert result["baseline_metrics"]["buy_and_hold"]["final_equity"] == 1.087515
    assert result["baseline_metrics"]["cash"] == {
        "net_return_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "volatility_pct": 0.0,
        "final_equity": 1.0,
    }
    assert result["relative_metrics"] == {
        "excess_return_vs_buy_and_hold_pct": -10.064752,
        "drawdown_delta_vs_buy_and_hold_pct": -0.15,
    }
    assert math.isclose(result["strategy_metrics"]["volatility_pct"], 136.109526, abs_tol=0.0001)
    assert math.isclose(result["strategy_metrics"]["sharpe"], -0.201125, abs_tol=0.0001)
    assert math.isclose(result["strategy_metrics"]["sortino"], -0.286575, abs_tol=0.0001)
    json.dumps(result)


def test_single_window_backtest_matches_independent_reference_path() -> None:
    rows = [
        _record("2026-06-01T00:00:00Z", 100),
        _record("2026-06-02T00:00:00Z", 104),
        _record("2026-06-03T00:00:00Z", 98.8),
        _record("2026-06-04T00:00:00Z", 103.74),
        _record("2026-06-05T00:00:00Z", 101.6652),
        _record("2026-06-06T00:00:00Z", 106.74846),
    ]
    targets = [0.0, 1.0, 0.5, 0.5, 0.0, 1.0]
    costs = {"fees_bps": 7.5, "slippage_bps": 2.5}

    result = evaluate_single_window_backtest(
        strategy=_strategy(),
        market_identity=_market_identity(),
        ohlcv_rows=rows,
        signal_records=_signal_records(rows, targets),
        cost_assumptions=costs,
    )
    reference = _independent_single_window_reference(rows, targets, costs)

    # This validation path is intentionally test-only: product artifacts remain Halpha-owned.
    # Tolerance is bounded to Halpha's six-decimal artifact rounding; semantic execution rules
    # mirrored here are close-to-close returns, next-bar positions, and one-way turnover costs.
    assert result["status"] == "succeeded"
    _assert_nested_close(result["strategy_metrics"], reference["strategy_metrics"])
    _assert_nested_close(result["baseline_metrics"], reference["baseline_metrics"])
    _assert_nested_close(result["relative_metrics"], reference["relative_metrics"])
    _assert_nested_close(result["trade_summary"], reference["trade_summary"])
    _assert_nested_close(result["drawdown_summary"], reference["drawdown_summary"])
    _assert_nested_close(result["equity_curve"], reference["equity_curve"])
    _assert_nested_close(result["drawdown_curve"], reference["drawdown_curve"])
    json.dumps(result)


def test_single_window_backtest_no_position_records_flat_equity() -> None:
    rows = [
        _record("2026-06-01T00:00:00Z", 100),
        _record("2026-06-02T00:00:00Z", 110),
        _record("2026-06-03T00:00:00Z", 105),
        _record("2026-06-04T00:00:00Z", 120),
    ]

    result = evaluate_single_window_backtest(
        strategy=_strategy(),
        market_identity=_market_identity(),
        ohlcv_rows=rows,
        signal_records=_signal_records(rows, [0, 0, 0, 0]),
        cost_assumptions={"fees_bps": 10, "slippage_bps": 5},
    )

    assert result["status"] == "succeeded"
    assert result["execution_model"]["execution_timing"] == "research_close_to_close"
    assert result["execution_model"]["position_timing"] == "next_bar"
    assert result["execution_model"]["lookahead_policy"] == "no_same_bar_execution"
    assert result["strategy_metrics"]["gross_return_pct"] == 0.0
    assert result["strategy_metrics"]["net_return_pct"] == 0.0
    assert result["strategy_metrics"]["total_cost_pct"] == 0.0
    assert result["strategy_metrics"]["cost_drag_pct"] == 0.0
    assert result["strategy_metrics"]["max_drawdown_pct"] == 0.0
    assert result["baseline_metrics"]["buy_and_hold"]["net_return_pct"] > 0.0
    assert result["baseline_metrics"]["cash"]["net_return_pct"] == 0.0
    assert result["relative_metrics"]["excess_return_vs_buy_and_hold_pct"] < 0.0
    assert result["trade_summary"]["trade_count"] == 0
    assert result["trade_summary"]["exposure_pct"] == 0.0
    assert result["equity_curve"][-1]["net_equity"] == 1.0
    warning_codes = {item["code"] for item in result["warnings"]}
    assert result["warnings"][0]["code"] == "historical_research_only"
    assert "insufficient_sample_length" in warning_codes
    assert "no_strategy_exposure" in warning_codes
    assert "low_trade_count" in warning_codes
    json.dumps(result)


def test_single_window_backtest_always_long_uses_next_bar_position() -> None:
    rows = [
        _record("2026-06-01T00:00:00Z", 100),
        _record("2026-06-02T00:00:00Z", 110),
        _record("2026-06-03T00:00:00Z", 121),
    ]

    result = evaluate_single_window_backtest(
        strategy=_strategy(),
        market_identity=_market_identity(),
        ohlcv_rows=rows,
        signal_records=_signal_records(rows, [1, 1, 1]),
    )

    assert result["status"] == "succeeded"
    assert result["strategy_metrics"]["gross_return_pct"] == 21.0
    assert result["strategy_metrics"]["net_return_pct"] == 21.0
    assert result["strategy_metrics"]["cost_drag_pct"] == 0.0
    assert result["strategy_metrics"]["final_equity"] == 1.21
    assert result["baseline_metrics"]["buy_and_hold"]["net_return_pct"] == 21.0
    assert result["baseline_metrics"]["cash"]["net_return_pct"] == 0.0
    assert result["relative_metrics"]["excess_return_vs_buy_and_hold_pct"] == 0.0
    assert result["relative_metrics"]["drawdown_delta_vs_buy_and_hold_pct"] == 0.0
    assert result["trade_summary"]["trade_count"] == 1
    assert result["trade_summary"]["open_trade_count"] == 1
    assert result["trade_summary"]["completed_trade_count"] == 0
    assert result["trade_summary"]["exposure_pct"] == 100.0
    assert result["trade_summary"]["average_holding_bars"] == 2
    assert result["equity_curve"][1]["position"] == 1.0
    assert result["equity_curve"][1]["period_net_return_pct"] == 10.0
    json.dumps(result)


def test_single_window_backtest_entry_exit_applies_costs_and_no_same_bar_execution() -> None:
    rows = [
        _record("2026-06-01T00:00:00Z", 100),
        _record("2026-06-02T00:00:00Z", 110),
        _record("2026-06-03T00:00:00Z", 121),
        _record("2026-06-04T00:00:00Z", 108.9),
        _record("2026-06-05T00:00:00Z", 108.9),
    ]

    result = evaluate_single_window_backtest(
        strategy=_strategy(),
        market_identity=_market_identity(),
        ohlcv_rows=rows,
        signal_records=_signal_records(rows, [0, 1, 1, 0, 0]),
        cost_assumptions={"fees_bps": 10, "slippage_bps": 5},
    )

    assert result["status"] == "succeeded"
    assert result["equity_curve"][1]["position"] == 0.0
    assert result["equity_curve"][1]["net_equity"] == 1.0
    assert result["equity_curve"][2]["position"] == 1.0
    assert result["equity_curve"][2]["cost_pct"] == 0.15
    assert result["equity_curve"][4]["position"] == 0.0
    assert result["equity_curve"][4]["cost_pct"] == 0.15
    assert result["strategy_metrics"]["total_cost_pct"] == 0.3
    assert result["strategy_metrics"]["cost_drag_pct"] > 0
    assert result["trade_summary"]["trade_count"] == 1
    assert result["trade_summary"]["completed_trade_count"] == 1
    assert result["trade_summary"]["open_trade_count"] == 0
    assert result["trade_summary"]["turnover"] == 2.0
    assert result["trade_summary"]["exposure_pct"] == 50.0
    assert result["trade_summary"]["hit_rate_pct"] == 0.0
    assert result["strategy_metrics"]["max_drawdown_pct"] < 0
    assert result["drawdown_summary"]["max_drawdown_pct"] == result["strategy_metrics"]["max_drawdown_pct"]
    json.dumps(result)


def test_single_window_backtest_warns_on_high_turnover_and_cost_drag() -> None:
    rows = [
        _record(f"2026-06-{day:02d}T00:00:00Z", 100)
        for day in range(1, 13)
    ]

    result = evaluate_single_window_backtest(
        strategy=_strategy(),
        market_identity=_market_identity(),
        ohlcv_rows=rows,
        signal_records=_signal_records(rows, [1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0]),
        cost_assumptions={"fees_bps": 100, "slippage_bps": 100},
    )

    warning_codes = {item["code"] for item in result["warnings"]}

    assert result["status"] == "succeeded"
    assert result["trade_summary"]["trade_count"] == 6
    assert result["trade_summary"]["turnover"] == 11.0
    assert result["strategy_metrics"]["gross_return_pct"] == 0.0
    assert result["strategy_metrics"]["net_return_pct"] < 0
    assert result["strategy_metrics"]["cost_drag_pct"] >= 1.0
    assert "high_turnover" in warning_codes
    assert "high_cost_drag" in warning_codes
    assert "insufficient_sample_length" in warning_codes
    assert "low_trade_count" not in warning_codes
    json.dumps(result)


def test_single_window_backtest_requires_signal_for_each_ohlcv_row() -> None:
    rows = [
        _record("2026-06-01T00:00:00Z", 100),
        _record("2026-06-02T00:00:00Z", 110),
    ]

    result = evaluate_single_window_backtest(
        strategy=_strategy(),
        market_identity=_market_identity(),
        ohlcv_rows=rows,
        signal_records=_signal_records(rows[:1], [1]),
    )

    assert result["status"] == "insufficient_data"
    assert result["warnings"][0]["code"] == "insufficient_signal_records"
    assert result["strategy_metrics"] == {}
    assert result["equity_curve"] == []
    json.dumps(result)


def test_single_window_backtest_requires_at_least_two_ohlcv_rows() -> None:
    rows = [_record("2026-06-01T00:00:00Z", 100)]

    result = evaluate_single_window_backtest(
        strategy=_strategy(),
        market_identity=_market_identity(),
        ohlcv_rows=rows,
        signal_records=_signal_records(rows, [1]),
    )

    assert result["status"] == "insufficient_data"
    assert [item["code"] for item in result["warnings"]] == [
        "insufficient_ohlcv_rows",
        "historical_research_only",
    ]
    assert result["strategy_metrics"] == {}
    assert result["baseline_metrics"] == {}
    assert result["equity_curve"] == []
    assert result["errors"] == []
    json.dumps(result)


def test_single_window_backtest_rejects_non_positive_close_without_fake_success() -> None:
    rows = [
        _record("2026-06-01T00:00:00Z", 100),
        _record("2026-06-02T00:00:00Z", 0),
    ]

    result = evaluate_single_window_backtest(
        strategy=_strategy(),
        market_identity=_market_identity(),
        ohlcv_rows=rows,
        signal_records=_signal_records(rows, [1, 1]),
    )

    assert result["status"] == "failed"
    assert result["strategy_metrics"] == {}
    assert result["equity_curve"] == []
    assert result["warnings"][0]["code"] == "historical_research_only"
    assert result["errors"] == [
        {
            "error_type": "ValueError",
            "message": "close must be a positive number for strategy evaluation.",
            "stage": "strategy_evaluation.single_window",
        }
    ]
    json.dumps(result)


def test_walk_forward_backtest_records_sequential_windows_and_instability_warnings() -> None:
    rows = _walk_forward_rows()

    result = evaluate_walk_forward_backtest(
        strategy=_strategy(),
        market_identity=_market_identity(),
        ohlcv_rows=rows,
        signal_records=_signal_records(rows, [1 for _row in rows]),
    )

    warning_codes = {item["code"] for item in result["warnings"]}

    assert result["status"] == "succeeded"
    assert result["method"]["params_optimized_per_window"] is False
    assert result["method"]["state_carryover_between_windows"] is False
    assert result["window_policy"] == {
        "calibration_rows": 60,
        "window_rows": 60,
        "min_window_rows": 20,
        "min_windows": 3,
    }
    assert result["summary"]["window_count"] == 3
    assert result["summary"]["succeeded_windows"] == 3
    assert result["summary"]["positive_net_return_window_pct"] > 0
    assert result["summary"]["positive_net_return_window_pct"] < 100
    assert result["summary"]["result_stability"] == "unstable"
    assert [item["window_index"] for item in result["windows"]] == [1, 2, 3]
    assert result["windows"][0]["calibration_window"]["rows"] == 60
    assert result["windows"][0]["evaluation_window"]["rows"] == 60
    assert result["windows"][0]["strategy_metrics"]["net_return_pct"] > 0
    assert result["windows"][1]["strategy_metrics"]["net_return_pct"] < 0
    assert "unstable_walk_forward_results" in warning_codes
    assert "regime_dependent_walk_forward_outcomes" in warning_codes
    json.dumps(result)


def test_walk_forward_backtest_records_insufficient_history_without_fake_success() -> None:
    rows = [_record(_open_time_for_index(index), 100 + index) for index in range(80)]

    result = evaluate_walk_forward_backtest(
        strategy=_strategy(),
        market_identity=_market_identity(),
        ohlcv_rows=rows,
        signal_records=_signal_records(rows, [1 for _row in rows]),
    )

    warning_codes = {item["code"] for item in result["warnings"]}

    assert result["status"] == "insufficient_data"
    assert result["summary"]["window_count"] == 1
    assert result["summary"]["succeeded_windows"] == 1
    assert result["windows"][0]["status"] == "succeeded"
    assert result["windows"][0]["evaluation_window"]["rows"] == 20
    assert "too_few_walk_forward_windows" in warning_codes
    assert "insufficient_walk_forward_history" in warning_codes
    assert "short_walk_forward_samples" in warning_codes
    json.dumps(result)


def _strategy() -> dict[str, Any]:
    return {
        "name": "unit_strategy",
        "params": {"window": 2},
    }


def _market_identity() -> dict[str, str]:
    return {
        "source": "unit",
        "symbol": "TEST",
        "timeframe": "1d",
    }


def _record(open_time: str, close: float) -> dict[str, Any]:
    return {
        "open_time": open_time,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 1.0,
    }


def _signal_records(rows: list[dict[str, Any]], targets: list[float]) -> dict[str, Any]:
    return {
        "status": "succeeded",
        "records": [
            {
                "open_time": row["open_time"],
                "signal": {"active": target > 0},
                "position": {
                    "target_exposure": target,
                    "unit": "fractional_long_exposure",
                },
                "entry": False,
                "exit": False,
                "indicator_context": {},
            }
            for row, target in zip(rows, targets, strict=True)
        ],
    }


def _curve_values(result: dict[str, Any], field: str) -> list[Any]:
    return [item[field] for item in result["equity_curve"]]


def _independent_single_window_reference(
    rows: list[dict[str, Any]],
    targets: list[float],
    costs: dict[str, float],
) -> dict[str, Any]:
    closes = [float(row["close"]) for row in rows]
    cost_rate = (float(costs["fees_bps"]) + float(costs["slippage_bps"])) / 10000
    gross_equity = 1.0
    net_equity = 1.0
    equity_curve = [
        {
            "open_time": rows[0]["open_time"],
            "gross_equity": 1.0,
            "net_equity": 1.0,
            "position": 0.0,
            "turnover": 0.0,
            "period_gross_return_pct": None,
            "period_net_return_pct": None,
            "cost_pct": 0.0,
        }
    ]
    period_net_returns: list[float] = []
    positions: list[float] = []
    turnovers: list[float] = []
    cost_returns: list[float] = []

    for index in range(1, len(rows)):
        close_return = closes[index] / closes[index - 1] - 1
        exposure = float(targets[index - 1])
        previous_exposure = float(targets[index - 2]) if index >= 2 else 0.0
        turnover = abs(exposure - previous_exposure)
        cost_return = turnover * cost_rate
        gross_return = exposure * close_return
        net_return = gross_return - cost_return

        gross_equity *= 1 + gross_return
        net_equity *= 1 + net_return
        period_net_returns.append(net_return)
        positions.append(exposure)
        turnovers.append(turnover)
        cost_returns.append(cost_return)
        equity_curve.append(
            {
                "open_time": rows[index]["open_time"],
                "gross_equity": _artifact_round(gross_equity),
                "net_equity": _artifact_round(net_equity),
                "position": _artifact_round(exposure),
                "turnover": _artifact_round(turnover),
                "period_gross_return_pct": _artifact_pct(gross_return),
                "period_net_return_pct": _artifact_pct(net_return),
                "cost_pct": _artifact_pct(cost_return),
            }
        )

    drawdown_curve, drawdown_summary = _independent_drawdowns(equity_curve)
    baseline = _independent_buy_and_hold(closes, cost_rate)
    strategy_metrics = {
        "gross_return_pct": _artifact_pct(gross_equity - 1),
        "net_return_pct": _artifact_pct(net_equity - 1),
        "total_cost_pct": _artifact_pct(sum(cost_returns)),
        "cost_drag_pct": _artifact_round(_artifact_pct(gross_equity - 1) - _artifact_pct(net_equity - 1)),
        "max_drawdown_pct": drawdown_summary["max_drawdown_pct"],
        "volatility_pct": _artifact_pct(_population_stddev(period_net_returns) * math.sqrt(365)),
        "sharpe": _independent_sharpe(period_net_returns),
        "sortino": _independent_sortino(period_net_returns),
        "final_equity": _artifact_round(net_equity),
    }
    return {
        "strategy_metrics": strategy_metrics,
        "baseline_metrics": {
            "buy_and_hold": baseline,
            "cash": {
                "net_return_pct": 0.0,
                "max_drawdown_pct": 0.0,
                "volatility_pct": 0.0,
                "final_equity": 1.0,
            },
        },
        "relative_metrics": {
            "excess_return_vs_buy_and_hold_pct": _artifact_round(
                strategy_metrics["net_return_pct"] - baseline["net_return_pct"]
            ),
            "drawdown_delta_vs_buy_and_hold_pct": _artifact_round(
                strategy_metrics["max_drawdown_pct"] - baseline["max_drawdown_pct"]
            ),
        },
        "trade_summary": _independent_trade_summary(positions, period_net_returns, turnovers),
        "drawdown_summary": drawdown_summary,
        "equity_curve": equity_curve,
        "drawdown_curve": drawdown_curve,
    }


def _independent_buy_and_hold(closes: list[float], cost_rate: float) -> dict[str, float]:
    equity = 1.0
    equity_values = [equity]
    period_returns = []
    for index in range(1, len(closes)):
        close_return = closes[index] / closes[index - 1] - 1
        cost_return = cost_rate if index == 1 else 0.0
        net_return = close_return - cost_return
        period_returns.append(net_return)
        equity *= 1 + net_return
        equity_values.append(equity)
    return {
        "net_return_pct": _artifact_pct(equity - 1),
        "max_drawdown_pct": _artifact_pct(_independent_max_drawdown(equity_values)),
        "volatility_pct": _artifact_pct(_population_stddev(period_returns) * math.sqrt(365)),
        "final_equity": _artifact_round(equity),
    }


def _independent_trade_summary(
    positions: list[float],
    period_net_returns: list[float],
    turnovers: list[float],
) -> dict[str, Any]:
    trade_count = 0
    completed_returns = []
    holding_bars = []
    open_multiplier: float | None = None
    current_holding_bars = 0
    previous_position = 0.0

    for position, period_return in zip(positions, period_net_returns, strict=True):
        if position > 0 and previous_position <= 0:
            trade_count += 1
            open_multiplier = 1.0
            current_holding_bars = 0
        if open_multiplier is not None:
            open_multiplier *= 1 + period_return
            if position > 0:
                current_holding_bars += 1
        if position <= 0 and previous_position > 0 and open_multiplier is not None:
            completed_returns.append(open_multiplier - 1)
            holding_bars.append(current_holding_bars)
            open_multiplier = None
            current_holding_bars = 0
        previous_position = position

    if open_multiplier is not None:
        holding_bars.append(current_holding_bars)

    hit_rate = None
    if completed_returns:
        hit_rate = sum(1 for value in completed_returns if value > 0) / len(completed_returns) * 100
    average_holding = sum(holding_bars) / len(holding_bars) if holding_bars else None
    return {
        "trade_count": trade_count,
        "completed_trade_count": len(completed_returns),
        "open_trade_count": 1 if open_multiplier is not None else 0,
        "hit_rate_pct": _artifact_round(hit_rate) if hit_rate is not None else None,
        "turnover": _artifact_round(sum(turnovers)),
        "exposure_pct": _artifact_round(
            sum(1 for position in positions if position > 0) / len(positions) * 100
        ),
        "average_holding_bars": _artifact_round(average_holding) if average_holding is not None else None,
    }


def _independent_drawdowns(
    equity_curve: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    peak = 0.0
    peak_time = None
    max_drawdown = 0.0
    max_start = None
    max_end = None
    records = []
    for point in equity_curve:
        equity = float(point["net_equity"])
        if equity >= peak:
            peak = equity
            peak_time = point["open_time"]
        drawdown = 0.0 if peak <= 0 else equity / peak - 1
        if drawdown < max_drawdown:
            max_drawdown = drawdown
            max_start = peak_time
            max_end = point["open_time"]
        records.append(
            {
                "open_time": point["open_time"],
                "net_drawdown_pct": _artifact_pct(drawdown),
            }
        )
    return records, {
        "max_drawdown_pct": _artifact_pct(max_drawdown),
        "max_drawdown_start": max_start,
        "max_drawdown_end": max_end,
    }


def _independent_max_drawdown(equity_values: list[float]) -> float:
    peak = 0.0
    max_drawdown = 0.0
    for equity in equity_values:
        if equity >= peak:
            peak = equity
        drawdown = 0.0 if peak <= 0 else equity / peak - 1
        max_drawdown = min(max_drawdown, drawdown)
    return max_drawdown


def _independent_sharpe(period_returns: list[float]) -> float:
    volatility = _population_stddev(period_returns)
    if len(period_returns) < 2 or volatility == 0:
        return 0.0
    return _artifact_round((sum(period_returns) / len(period_returns) * 365) / (volatility * math.sqrt(365)))


def _independent_sortino(period_returns: list[float]) -> float:
    downside_returns = [value for value in period_returns if value < 0]
    downside_volatility = _population_stddev(downside_returns)
    if len(period_returns) < 2 or not downside_returns or downside_volatility == 0:
        return 0.0
    return _artifact_round(
        (sum(period_returns) / len(period_returns) * 365) / (downside_volatility * math.sqrt(365))
    )


def _population_stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    value_mean = sum(values) / len(values)
    return math.sqrt(sum((value - value_mean) ** 2 for value in values) / len(values))


def _assert_nested_close(actual: Any, expected: Any) -> None:
    if isinstance(expected, dict):
        assert isinstance(actual, dict)
        assert set(actual) == set(expected)
        for key, expected_value in expected.items():
            _assert_nested_close(actual[key], expected_value)
        return
    if isinstance(expected, list):
        assert isinstance(actual, list)
        assert len(actual) == len(expected)
        for actual_value, expected_value in zip(actual, expected, strict=True):
            _assert_nested_close(actual_value, expected_value)
        return
    if isinstance(expected, float):
        assert isinstance(actual, (int, float))
        assert math.isclose(float(actual), expected, abs_tol=0.000001)
        return
    assert actual == expected


def _artifact_pct(value: float) -> float:
    return _artifact_round(value * 100)


def _artifact_round(value: float) -> float:
    return round(float(value), 6)


def _walk_forward_rows() -> list[dict[str, Any]]:
    closes = (
        [100.0 for _index in range(60)]
        + [100.0 + index for index in range(60)]
        + [160.0 - index for index in range(60)]
        + [100.0 + index for index in range(60)]
    )
    return [
        _record(_open_time_for_index(index), close)
        for index, close in enumerate(closes)
    ]


def _open_time_for_index(index: int) -> str:
    value = date(2026, 1, 1) + timedelta(days=index)
    return f"{value.isoformat()}T00:00:00Z"
