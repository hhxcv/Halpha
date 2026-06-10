from __future__ import annotations

import json
from typing import Any

from halpha.quant.strategy_evaluation import evaluate_single_window_backtest


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
