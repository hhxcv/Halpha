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
