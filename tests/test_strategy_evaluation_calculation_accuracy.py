from __future__ import annotations

import json
from typing import Any

import pandas as pd
import pytest
import vectorbt as vbt

from halpha.quant.strategy_evaluation import (
    evaluate_single_window_backtest,
    evaluate_walk_forward_backtest,
)


def test_single_window_uses_previous_bar_signal_without_same_bar_lookahead() -> None:
    result = evaluate_single_window_backtest(
        strategy=_strategy("delayed_long_flat"),
        market_identity=_market_identity(timeframe="1d"),
        ohlcv_rows=[
            _row("2026-06-01T00:00:00Z", 100.0),
            _row("2026-06-02T00:00:00Z", 110.0),
            _row("2026-06-03T00:00:00Z", 121.0),
            _row("2026-06-04T00:00:00Z", 60.5),
        ],
        signal_records=_signal_records(
            [
                ("2026-06-01T00:00:00Z", 0.0),
                ("2026-06-02T00:00:00Z", 1.0),
                ("2026-06-03T00:00:00Z", 0.0),
                ("2026-06-04T00:00:00Z", 0.0),
            ]
        ),
        cost_assumptions={"fees_bps": 0.0, "slippage_bps": 0.0},
    )

    assert result["status"] == "succeeded"
    assert result["execution_model"]["lookahead_policy"] == "no_same_bar_execution"
    assert [point["position"] for point in result["equity_curve"]] == [0.0, 0.0, 1.0, 0.0]
    assert [point["period_net_return_pct"] for point in result["equity_curve"]] == [
        None,
        0.0,
        10.0,
        0.0,
    ]
    assert result["strategy_metrics"]["net_return_pct"] == pytest.approx(10.0)
    assert result["baseline_metrics"]["buy_and_hold"]["net_return_pct"] == pytest.approx(-39.5)
    assert result["relative_metrics"]["excess_return_vs_buy_and_hold_pct"] == pytest.approx(49.5)
    assert result["trade_summary"]["trade_count"] == 1
    assert result["trade_summary"]["completed_trade_count"] == 1
    assert result["trade_summary"]["hit_rate_pct"] == pytest.approx(100.0)
    json.dumps(result)


def test_single_window_costs_compound_with_returns_and_drawdown_uses_net_equity() -> None:
    result = evaluate_single_window_backtest(
        strategy=_strategy("costed_long_flat"),
        market_identity=_market_identity(timeframe="1d"),
        ohlcv_rows=[
            _row("2026-06-01T00:00:00Z", 100.0),
            _row("2026-06-02T00:00:00Z", 110.0),
            _row("2026-06-03T00:00:00Z", 99.0),
            _row("2026-06-04T00:00:00Z", 99.0),
        ],
        signal_records=_signal_records(
            [
                ("2026-06-01T00:00:00Z", 1.0),
                ("2026-06-02T00:00:00Z", 1.0),
                ("2026-06-03T00:00:00Z", 0.0),
                ("2026-06-04T00:00:00Z", 0.0),
            ]
        ),
        cost_assumptions={"fees_bps": 10.0, "slippage_bps": 5.0},
    )

    entry_cost = 0.0015
    exit_cost = 0.0015
    expected_net_equity = (1.0 + 0.10 - entry_cost) * (1.0 - 0.10) * (1.0 - exit_cost)
    expected_gross_equity = (1.0 + 0.10) * (1.0 - 0.10)
    expected_drawdown = (expected_net_equity / (1.0 + 0.10 - entry_cost)) - 1.0

    assert result["status"] == "succeeded"
    assert result["strategy_metrics"]["final_equity"] == pytest.approx(expected_net_equity)
    assert result["strategy_metrics"]["gross_return_pct"] == pytest.approx((expected_gross_equity - 1.0) * 100)
    assert result["strategy_metrics"]["net_return_pct"] == pytest.approx((expected_net_equity - 1.0) * 100)
    assert result["strategy_metrics"]["total_cost_pct"] == pytest.approx((entry_cost + exit_cost) * 100)
    assert result["strategy_metrics"]["cost_drag_pct"] == pytest.approx(
        result["strategy_metrics"]["gross_return_pct"] - result["strategy_metrics"]["net_return_pct"]
    )
    assert result["strategy_metrics"]["max_drawdown_pct"] == pytest.approx(expected_drawdown * 100)
    assert result["drawdown_summary"]["max_drawdown_start"] == "2026-06-02T00:00:00Z"
    assert result["drawdown_summary"]["max_drawdown_end"] == "2026-06-04T00:00:00Z"
    assert result["trade_summary"]["turnover"] == pytest.approx(2.0)
    json.dumps(result)


def test_signed_exposure_applies_long_short_pnl_funding_and_futures_diagnostics() -> None:
    result = evaluate_single_window_backtest(
        strategy=_strategy("signed_long_short"),
        market_identity=_market_identity(source="binance_usdm", timeframe="1d"),
        ohlcv_rows=[
            _row("2026-06-01T00:00:00Z", 100.0),
            _row("2026-06-02T00:00:00Z", 110.0),
            _row("2026-06-03T00:00:00Z", 99.0),
            _row("2026-06-04T00:00:00Z", 108.9),
        ],
        signal_records=_signal_records(
            [
                ("2026-06-01T00:00:00Z", 1.0),
                ("2026-06-02T00:00:00Z", -1.0),
                ("2026-06-03T00:00:00Z", 0.0),
                ("2026-06-04T00:00:00Z", 0.0),
            ],
            signed=True,
        ),
        cost_assumptions={"fees_bps": 0.0, "slippage_bps": 0.0},
        funding_costs={
            "status": "available",
            "period_count": 3,
            "matched_record_count": 2,
            "missing_period_count": 1,
            "periods": [
                {
                    "period_end": "2026-06-02T00:00:00Z",
                    "funding_rate": 0.001,
                    "matched_record_count": 1,
                },
                {
                    "period_end": "2026-06-03T00:00:00Z",
                    "funding_rate": 0.002,
                    "matched_record_count": 1,
                },
            ],
        },
    )

    expected_net_equity = (1.0 + 0.10 - 0.001) * (1.0 + 0.10 + 0.002)

    assert result["status"] == "succeeded"
    assert result["execution_model"]["execution_model_id"] == "close_to_close_next_bar_signed_v1"
    assert result["strategy_metrics"]["gross_return_pct"] == pytest.approx(21.0)
    assert result["strategy_metrics"]["net_return_pct"] == pytest.approx((expected_net_equity - 1.0) * 100)
    assert result["strategy_metrics"]["funding_drag_pct"] == pytest.approx(-0.1)
    assert [point["funding_return_pct"] for point in result["equity_curve"]] == [
        0.0,
        -0.1,
        0.2,
        0.0,
    ]
    assert result["trade_summary"]["trade_count"] == 2
    assert result["trade_summary"]["long_trade_count"] == 1
    assert result["trade_summary"]["short_trade_count"] == 1
    assert result["trade_summary"]["side_flip_count"] == 1
    assert result["trade_summary"]["completed_trade_count"] == 2
    diagnostics = result["futures_diagnostics"]
    assert diagnostics["contribution"]["long_gross_contribution_pct"] == pytest.approx(10.0)
    assert diagnostics["contribution"]["short_gross_contribution_pct"] == pytest.approx(10.0)
    assert diagnostics["exposure"]["long_time_pct"] == pytest.approx(100 / 3)
    assert diagnostics["exposure"]["short_time_pct"] == pytest.approx(100 / 3)
    assert diagnostics["funding"]["funding_drag_pct"] == pytest.approx(-0.1)
    json.dumps(result)


def test_walk_forward_uses_chronological_non_overlapping_windows() -> None:
    rows = [
        _row("2026-06-01T00:00:00Z", 100.0),
        _row("2026-06-02T00:00:00Z", 110.0),
        _row("2026-06-03T00:00:00Z", 121.0),
        _row("2026-06-04T00:00:00Z", 133.1),
        _row("2026-06-05T00:00:00Z", 146.41),
        _row("2026-06-06T00:00:00Z", 161.051),
    ]
    result = evaluate_walk_forward_backtest(
        strategy=_strategy("walk_forward_long"),
        market_identity=_market_identity(timeframe="1d"),
        ohlcv_rows=rows,
        signal_records=_signal_records([(row["open_time"], 1.0) for row in rows]),
        cost_assumptions={"fees_bps": 0.0, "slippage_bps": 0.0},
        window_policy={
            "calibration_rows": 2,
            "window_rows": 2,
            "min_window_rows": 2,
            "min_windows": 2,
        },
    )

    assert result["status"] == "succeeded"
    assert result["summary"]["window_count"] == 2
    assert result["summary"]["succeeded_windows"] == 2
    assert result["summary"]["mean_net_return_pct"] == pytest.approx(10.0)
    assert result["summary"]["positive_net_return_window_pct"] == pytest.approx(100.0)
    assert [
        window["evaluation_window"]
        for window in result["windows"]
    ] == [
        {
            "start": "2026-06-03T00:00:00Z",
            "end": "2026-06-04T00:00:00Z",
            "rows": 2,
        },
        {
            "start": "2026-06-05T00:00:00Z",
            "end": "2026-06-06T00:00:00Z",
            "rows": 2,
        },
    ]
    assert all(window["strategy_metrics"]["net_return_pct"] == pytest.approx(10.0) for window in result["windows"])
    json.dumps(result)


def test_flat_exposure_never_changes_strategy_equity_even_when_market_moves() -> None:
    result = evaluate_single_window_backtest(
        strategy=_strategy("flat"),
        market_identity=_market_identity(timeframe="1d"),
        ohlcv_rows=[
            _row("2026-06-01T00:00:00Z", 100.0),
            _row("2026-06-02T00:00:00Z", 130.0),
            _row("2026-06-03T00:00:00Z", 65.0),
        ],
        signal_records=_signal_records(
            [
                ("2026-06-01T00:00:00Z", 0.0),
                ("2026-06-02T00:00:00Z", 0.0),
                ("2026-06-03T00:00:00Z", 0.0),
            ]
        ),
    )

    assert result["status"] == "succeeded"
    assert result["strategy_metrics"]["net_return_pct"] == 0.0
    assert result["strategy_metrics"]["gross_return_pct"] == 0.0
    assert result["strategy_metrics"]["max_drawdown_pct"] == 0.0
    assert result["trade_summary"]["trade_count"] == 0
    assert result["baseline_metrics"]["buy_and_hold"]["net_return_pct"] == pytest.approx(-35.0)
    json.dumps(result)


@pytest.mark.parametrize(
    "closes",
    [
        [100.0, 101.0, 102.01, 103.0301],
        [100.0, 80.0, 88.0, 79.2],
        [100.0, 150.0, 75.0, 112.5],
    ],
)
def test_zero_cost_full_long_matches_buy_and_hold_across_price_paths(closes: list[float]) -> None:
    rows = [_row(f"2026-06-{index + 1:02d}T00:00:00Z", close) for index, close in enumerate(closes)]
    result = evaluate_single_window_backtest(
        strategy=_strategy("full_long"),
        market_identity=_market_identity(timeframe="1d"),
        ohlcv_rows=rows,
        signal_records=_signal_records([(row["open_time"], 1.0) for row in rows]),
        cost_assumptions={"fees_bps": 0.0, "slippage_bps": 0.0},
    )

    expected_return_pct = ((closes[-1] / closes[0]) - 1.0) * 100

    assert result["status"] == "succeeded"
    assert result["strategy_metrics"]["net_return_pct"] == pytest.approx(expected_return_pct)
    assert result["strategy_metrics"]["gross_return_pct"] == pytest.approx(expected_return_pct)
    assert result["baseline_metrics"]["buy_and_hold"]["net_return_pct"] == pytest.approx(expected_return_pct)
    assert result["relative_metrics"]["excess_return_vs_buy_and_hold_pct"] == pytest.approx(0.0)
    assert result["strategy_metrics"]["final_equity"] == pytest.approx(closes[-1] / closes[0])
    json.dumps(result)


def test_zero_cost_full_long_matches_vectorbt_target_percent_portfolio() -> None:
    closes = [100.0, 110.0, 99.0, 120.0]
    targets = [1.0, 1.0, 1.0, 1.0]
    result = _evaluate_single_window(closes, targets)

    vectorbt_equity = _vectorbt_target_percent_equity(closes, targets, direction="longonly")
    halpha_equity = [point["net_equity"] for point in result["equity_curve"]]

    assert result["status"] == "succeeded"
    assert halpha_equity == pytest.approx(vectorbt_equity, abs=1e-6)
    assert result["strategy_metrics"]["net_return_pct"] == pytest.approx((vectorbt_equity[-1] - 1.0) * 100)


def test_zero_cost_long_flat_timing_matches_vectorbt_target_percent_portfolio() -> None:
    closes = [100.0, 110.0, 99.0, 120.0]
    targets = [0.0, 1.0, 1.0, 0.0]
    result = _evaluate_single_window(closes, targets)

    vectorbt_equity = _vectorbt_target_percent_equity(closes, targets, direction="longonly")
    halpha_equity = [point["net_equity"] for point in result["equity_curve"]]

    assert result["status"] == "succeeded"
    assert result["execution_model"]["lookahead_policy"] == "no_same_bar_execution"
    assert halpha_equity == pytest.approx(vectorbt_equity, abs=1e-6)
    assert result["strategy_metrics"]["net_return_pct"] == pytest.approx((vectorbt_equity[-1] - 1.0) * 100)


def test_zero_cost_signed_long_short_matches_vectorbt_both_direction_portfolio() -> None:
    closes = [100.0, 110.0, 99.0, 120.0, 108.0]
    targets = [0.0, 1.0, -1.0, -1.0, 0.0]
    result = _evaluate_single_window(closes, targets, signed=True)

    vectorbt_equity = _vectorbt_target_percent_equity(closes, targets, direction="both")
    halpha_equity = [point["net_equity"] for point in result["equity_curve"]]

    assert result["status"] == "succeeded"
    assert result["execution_model"]["execution_model_id"] == "close_to_close_next_bar_signed_v1"
    assert halpha_equity == pytest.approx(vectorbt_equity, abs=1e-6)
    assert result["strategy_metrics"]["net_return_pct"] == pytest.approx((vectorbt_equity[-1] - 1.0) * 100)


def _evaluate_single_window(
    closes: list[float],
    targets: list[float],
    *,
    signed: bool = False,
) -> dict[str, Any]:
    rows = [_row(f"2026-06-{index + 1:02d}T00:00:00Z", close) for index, close in enumerate(closes)]
    source = "binance_usdm" if signed else "binance"
    return evaluate_single_window_backtest(
        strategy=_strategy("vectorbt_cross_check"),
        market_identity=_market_identity(source=source, timeframe="1d"),
        ohlcv_rows=rows,
        signal_records=_signal_records(
            [(row["open_time"], target) for row, target in zip(rows, targets, strict=True)],
            signed=signed,
        ),
        cost_assumptions={"fees_bps": 0.0, "slippage_bps": 0.0},
    )


def _vectorbt_target_percent_equity(
    closes: list[float],
    targets: list[float],
    *,
    direction: str,
) -> list[float]:
    index = pd.date_range("2026-06-01", periods=len(closes), freq="D", tz="UTC")
    close = pd.Series(closes, index=index)
    target_percent = pd.Series(targets, index=index)
    portfolio = vbt.Portfolio.from_orders(
        close=close,
        size=target_percent,
        size_type="targetpercent",
        direction=direction,
        fees=0.0,
        fixed_fees=0.0,
        slippage=0.0,
        init_cash=1.0,
        cash_sharing=False,
        call_seq="auto",
    )
    return [float(value) for value in portfolio.value().to_numpy()]


def _strategy(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "backtest": {
            "enabled": True,
            "mode": "long_flat",
        },
    }


def _market_identity(
    *,
    source: str = "binance",
    symbol: str = "BTCUSDT",
    timeframe: str,
) -> dict[str, Any]:
    return {
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
    }


def _signal_records(items: list[tuple[str, float]], *, signed: bool = False) -> dict[str, Any]:
    return {
        "status": "succeeded",
        "signal_record_version": 2 if signed else 1,
        "position_policy": "research_signed_target_exposure" if signed else "research_long_flat_target_exposure",
        "records": [
            {
                "open_time": open_time,
                "signal": {
                    "active": exposure != 0,
                    "position_state": _position_state(exposure) if signed else None,
                },
                "position": {
                    "target_exposure": exposure,
                    "unit": "fractional_signed_exposure" if signed else "fractional_long_exposure",
                    "position_state": _position_state(exposure) if signed else None,
                },
            }
            for open_time, exposure in items
        ],
    }


def _position_state(exposure: float) -> str:
    if exposure > 0:
        return "long"
    if exposure < 0:
        return "short"
    return "flat"


def _row(open_time: str, close: float) -> dict[str, Any]:
    return {
        "open_time": open_time,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 1.0,
    }
