from __future__ import annotations

import pandas as pd

from halpha.quant.backtest import bounded_backtest_diagnostic
from halpha.quant.strategy_evaluation import evaluate_single_window_backtest


def test_bounded_backtest_diagnostic_matches_canonical_next_bar_evaluator() -> None:
    rows = [
        _record("2026-06-01T00:00:00Z", 100),
        _record("2026-06-02T00:00:00Z", 110),
        _record("2026-06-03T00:00:00Z", 99),
        _record("2026-06-04T00:00:00Z", 108.9),
        _record("2026-06-05T00:00:00Z", 108.9),
    ]
    signals = [False, True, True, False, True]
    strategy = _strategy(fees_bps=10, slippage_bps=5)
    view = _view(rows)

    diagnostic = bounded_backtest_diagnostic(
        strategy,
        view,
        rows,
        close=_close_series(rows),
        signal_series=pd.Series(signals),
    )
    canonical = evaluate_single_window_backtest(
        strategy=strategy,
        market_identity=_market_identity(view),
        ohlcv_rows=rows,
        signal_records=_signal_records(rows, signals),
        cost_assumptions={"fees_bps": 10, "slippage_bps": 5},
    )

    assert diagnostic["status"] == "succeeded"
    assert canonical["status"] == "succeeded"
    assert diagnostic["assumptions"]["execution_model_id"] == "close_to_close_next_bar_v1"
    assert diagnostic["assumptions"]["position_timing"] == "next_bar"
    assert diagnostic["assumptions"]["lookahead_policy"] == "no_same_bar_execution"
    assert diagnostic["metrics"]["execution_model_id"] == canonical["execution_model"]["execution_model_id"]
    assert diagnostic["metrics"]["position_timing"] == canonical["execution_model"]["position_timing"]
    assert diagnostic["metrics"]["lookahead_policy"] == canonical["execution_model"]["lookahead_policy"]
    assert diagnostic["metrics"]["return_metric_basis"] == "net_after_costs"
    assert diagnostic["metrics"]["total_return_pct"] == canonical["strategy_metrics"]["net_return_pct"]
    assert diagnostic["metrics"]["net_return_pct"] == canonical["strategy_metrics"]["net_return_pct"]
    assert diagnostic["metrics"]["gross_return_pct"] == canonical["strategy_metrics"]["gross_return_pct"]
    assert diagnostic["metrics"]["total_cost_pct"] == canonical["strategy_metrics"]["total_cost_pct"]
    assert diagnostic["metrics"]["cost_drag_pct"] == canonical["strategy_metrics"]["cost_drag_pct"]
    assert diagnostic["metrics"]["max_drawdown_pct"] == canonical["strategy_metrics"]["max_drawdown_pct"]
    assert diagnostic["metrics"]["trade_count"] == canonical["trade_summary"]["trade_count"]
    assert diagnostic["metrics"]["turnover"] == canonical["trade_summary"]["turnover"]
    assert diagnostic["metrics"]["exposure_pct"] == canonical["trade_summary"]["exposure_pct"]
    assert diagnostic["metrics"]["final_equity_multiplier"] == canonical["strategy_metrics"]["final_equity"]
    assert diagnostic["metrics"]["final_equity"] == 9868.67


def test_bounded_backtest_diagnostic_cannot_capture_current_bar_return() -> None:
    rows = [
        _record("2026-06-01T00:00:00Z", 100),
        _record("2026-06-02T00:00:00Z", 200),
        _record("2026-06-03T00:00:00Z", 50),
    ]
    signals = [False, True, False]
    same_bar_return = _same_bar_return_pct(rows, signals)

    diagnostic = bounded_backtest_diagnostic(
        _strategy(),
        _view(rows),
        rows,
        close=_close_series(rows),
        signal_series=pd.Series(signals),
    )

    assert same_bar_return == 100.0
    assert diagnostic["metrics"]["position_timing"] == "next_bar"
    assert diagnostic["metrics"]["lookahead_policy"] == "no_same_bar_execution"
    assert diagnostic["metrics"]["total_return_pct"] == -75.0
    assert diagnostic["metrics"]["final_equity"] == 2500.0


def test_bounded_backtest_diagnostic_long_only_matches_canonical_mode() -> None:
    rows = [
        _record("2026-06-01T00:00:00Z", 100),
        _record("2026-06-02T00:00:00Z", 110),
        _record("2026-06-03T00:00:00Z", 99),
        _record("2026-06-04T00:00:00Z", 120),
    ]
    signals = [False, True, False, False]
    strategy = _strategy(mode="long_only")
    view = _view(rows)

    diagnostic = bounded_backtest_diagnostic(
        strategy,
        view,
        rows,
        close=_close_series(rows),
        signal_series=pd.Series(signals),
    )
    canonical = evaluate_single_window_backtest(
        strategy=strategy,
        market_identity=_market_identity(view),
        ohlcv_rows=rows,
        signal_records=_signal_records(rows, signals),
    )

    assert diagnostic["metrics"]["total_return_pct"] == canonical["strategy_metrics"]["net_return_pct"]
    assert diagnostic["metrics"]["trade_count"] == canonical["trade_summary"]["trade_count"]
    assert diagnostic["metrics"]["exposure_pct"] == canonical["trade_summary"]["exposure_pct"]
    assert diagnostic["metrics"]["final_equity"] == 10909.09


def _record(open_time: str, close: float) -> dict[str, float | int | str]:
    return {
        "open_time": open_time,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 1,
    }


def _strategy(
    *,
    fees_bps: float = 0.0,
    slippage_bps: float = 0.0,
    mode: str = "long_flat",
) -> dict[str, object]:
    return {
        "name": "synthetic_strategy",
        "params": {},
        "backtest": {
            "enabled": True,
            "initial_cash": 10000,
            "fees_bps": fees_bps,
            "slippage_bps": slippage_bps,
            "mode": mode,
        },
    }


def _view(rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        "source": "synthetic",
        "symbol": "TEST",
        "timeframe": "1d",
        "input_window_start": rows[0]["open_time"],
        "input_window_end": rows[-1]["open_time"],
        "latest_candle_time": rows[-1]["open_time"],
    }


def _market_identity(view: dict[str, object]) -> dict[str, object]:
    return {
        "source": view["source"],
        "symbol": view["symbol"],
        "timeframe": view["timeframe"],
    }


def _close_series(rows: list[dict[str, object]]) -> pd.Series:
    return pd.Series([row["close"] for row in rows])


def _signal_records(rows: list[dict[str, object]], signals: list[bool]) -> list[dict[str, object]]:
    return [
        {
            "open_time": row["open_time"],
            "signal": {"active": signals[index]},
            "position": {
                "target_exposure": 1.0 if signals[index] else 0.0,
                "unit": "fractional_long_exposure",
            },
        }
        for index, row in enumerate(rows)
    ]


def _same_bar_return_pct(rows: list[dict[str, object]], signals: list[bool]) -> float:
    equity = 1.0
    closes = [float(row["close"]) for row in rows]
    for index in range(1, len(rows)):
        close_return = (closes[index] / closes[index - 1]) - 1
        equity *= 1 + (1.0 if signals[index] else 0.0) * close_return
    return round((equity - 1) * 100, 6)
