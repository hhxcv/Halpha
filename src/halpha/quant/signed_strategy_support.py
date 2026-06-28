from __future__ import annotations

import math
from typing import Any

from .strategy_evaluation import evaluate_single_window_backtest
from .strategy_records import DEFAULT_BACKTEST_INITIAL_CASH, SIGNED_EXECUTION_MODEL


def signed_transition_counts(records: list[dict[str, Any]]) -> dict[str, Any]:
    long_entry_count = sum(1 for item in records if item.get("long_entry") is True)
    long_exit_count = sum(1 for item in records if item.get("long_exit") is True)
    short_entry_count = sum(1 for item in records if item.get("short_entry") is True)
    short_exit_count = sum(1 for item in records if item.get("short_exit") is True)
    side_flip_count = 0
    previous = "flat"
    for item in records:
        position = item.get("position") if isinstance(item.get("position"), dict) else {}
        state = str(position.get("position_state") or "flat")
        if {previous, state} == {"long", "short"}:
            side_flip_count += 1
        previous = state
    return {
        "entry_count": long_entry_count + short_entry_count,
        "exit_count": long_exit_count + short_exit_count,
        "long_entry_count": long_entry_count,
        "long_exit_count": long_exit_count,
        "short_entry_count": short_entry_count,
        "short_exit_count": short_exit_count,
        "side_flip_count": side_flip_count,
        "active_count": sum(1 for item in records if item.get("signal", {}).get("active") is True),
    }


def signed_backtest_diagnostic(
    strategy: dict[str, Any],
    view: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    signal_records: dict[str, Any],
) -> dict[str, Any]:
    backtest = strategy.get("backtest") if isinstance(strategy.get("backtest"), dict) else {}
    if backtest.get("enabled") is not True:
        return {
            "enabled": False,
            "status": "disabled",
        }
    assumptions = _signed_backtest_assumptions(backtest)
    evaluation = evaluate_single_window_backtest(
        strategy=strategy,
        market_identity={
            "source": view.get("source"),
            "symbol": view.get("symbol"),
            "timeframe": view.get("timeframe"),
        },
        ohlcv_rows=rows,
        signal_records=signal_records,
        cost_assumptions={
            "fees_bps": assumptions["fees_bps"],
            "slippage_bps": assumptions["slippage_bps"],
        },
        execution_model=SIGNED_EXECUTION_MODEL,
    )
    if evaluation.get("status") != "succeeded":
        return {
            "enabled": True,
            "status": str(evaluation.get("status") or "failed"),
            "assumptions": assumptions,
            "window": _window(view, rows),
            "metrics": {},
            "warnings": [
                "Signed backtest diagnostic uses the Halpha signed next-bar close-to-close evaluator.",
                *_warning_messages(evaluation.get("warnings")),
                *_error_messages(evaluation.get("errors")),
            ],
        }
    return {
        "enabled": True,
        "status": "succeeded",
        "assumptions": assumptions,
        "window": _window(view, rows),
        "metrics": _bounded_backtest_metrics(evaluation, initial_cash=assumptions["initial_cash"]),
        "warnings": [
            "Signed backtest diagnostic is historical research material, not a forecast.",
            "Signed exposure is not account leverage, margin, borrowing, or execution advice.",
        ],
    }


def _signed_backtest_assumptions(backtest: dict[str, Any]) -> dict[str, Any]:
    return {
        "initial_cash": _positive_number_or_default(
            backtest.get("initial_cash"),
            DEFAULT_BACKTEST_INITIAL_CASH,
        ),
        "fees_bps": _non_negative_number_or_default(backtest.get("fees_bps"), 0.0),
        "slippage_bps": _non_negative_number_or_default(backtest.get("slippage_bps"), 0.0),
        "mode": "signed_long_short",
        "direction": "long_short",
        **SIGNED_EXECUTION_MODEL,
    }


def _bounded_backtest_metrics(evaluation: dict[str, Any], *, initial_cash: float) -> dict[str, Any]:
    strategy_metrics = evaluation.get("strategy_metrics") if isinstance(evaluation.get("strategy_metrics"), dict) else {}
    trade_summary = evaluation.get("trade_summary") if isinstance(evaluation.get("trade_summary"), dict) else {}
    final_multiplier = float(strategy_metrics.get("final_equity") or 0.0)
    return {
        "calculation_backend": "halpha.strategy_evaluation.evaluate_single_window_backtest",
        "execution_model_id": SIGNED_EXECUTION_MODEL["execution_model_id"],
        "return_metric_basis": "net_after_costs",
        "gross_return_pct": strategy_metrics.get("gross_return_pct"),
        "net_return_pct": strategy_metrics.get("net_return_pct"),
        "total_cost_pct": strategy_metrics.get("total_cost_pct"),
        "cost_drag_pct": strategy_metrics.get("cost_drag_pct"),
        "max_drawdown_pct": strategy_metrics.get("max_drawdown_pct"),
        "trade_count": trade_summary.get("trade_count"),
        "long_trade_count": trade_summary.get("long_trade_count"),
        "short_trade_count": trade_summary.get("short_trade_count"),
        "side_flip_count": trade_summary.get("side_flip_count"),
        "turnover": trade_summary.get("turnover"),
        "long_exposure_pct": trade_summary.get("long_exposure_pct"),
        "short_exposure_pct": trade_summary.get("short_exposure_pct"),
        "average_abs_exposure_pct": trade_summary.get("average_abs_exposure_pct"),
        "final_equity": _round(initial_cash * final_multiplier),
        "final_equity_multiplier": strategy_metrics.get("final_equity"),
    }


def _window(view: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "start": view.get("input_window_start"),
        "end": view.get("input_window_end"),
        "rows": len(rows),
    }


def _positive_number_or_default(value: Any, default: float) -> float:
    number = _finite_number_or_none(value)
    if number is None or number <= 0:
        return default
    return number


def _non_negative_number_or_default(value: Any, default: float) -> float:
    number = _finite_number_or_none(value)
    if number is None or number < 0:
        return default
    return number


def _finite_number_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def _warning_messages(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        str(item.get("message"))
        for item in value
        if isinstance(item, dict) and isinstance(item.get("message"), str)
    ]


def _error_messages(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        str(item.get("message"))
        for item in value
        if isinstance(item, dict) and isinstance(item.get("message"), str)
    ]


def _round(value: float) -> float:
    return round(float(value), 6)
