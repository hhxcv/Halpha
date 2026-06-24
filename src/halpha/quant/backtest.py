from __future__ import annotations

from typing import Any

import pandas as pd

from .strategy_evaluation import evaluate_single_window_backtest
from .strategy_records import CANONICAL_EXECUTION_MODEL, backtest_assumptions, backtest_diagnostic


HALPHA_BACKTEST_BACKEND = "halpha.strategy_evaluation.evaluate_single_window_backtest"
BACKTEST_RESEARCH_WARNING = "Historical backtest diagnostic is research material, not a forecast."


def bounded_backtest_diagnostic(
    strategy: dict[str, Any],
    view: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    close: pd.Series,
    signal_series: pd.Series,
) -> dict[str, Any]:
    backtest = strategy.get("backtest") if isinstance(strategy.get("backtest"), dict) else {}
    if backtest.get("enabled") is not True:
        return backtest_diagnostic(strategy, view, rows, status="disabled")

    assumptions = backtest_assumptions(strategy)
    signal_records = _signal_records_from_series(
        rows,
        close=close,
        signal_series=signal_series,
        mode=str(assumptions["mode"]),
    )
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
        execution_model=CANONICAL_EXECUTION_MODEL,
    )
    if evaluation.get("status") != "succeeded":
        return backtest_diagnostic(
            strategy,
            view,
            rows,
            status=str(evaluation.get("status") or "failed"),
            warnings=[
                BACKTEST_RESEARCH_WARNING,
                "Diagnostic uses the canonical next-bar close-to-close evaluator.",
                *_warning_messages(evaluation.get("warnings")),
                *_error_messages(evaluation.get("errors")),
            ],
        )

    metrics = _bounded_metrics(evaluation, initial_cash=float(assumptions["initial_cash"]))
    return backtest_diagnostic(
        strategy,
        view,
        rows,
        status="succeeded",
        metrics=metrics,
        warnings=[
            BACKTEST_RESEARCH_WARNING,
            "Diagnostic uses the canonical next-bar close-to-close evaluator and is not future performance evidence.",
        ],
    )


def _signal_records_from_series(
    rows: list[dict[str, Any]],
    *,
    close: pd.Series,
    signal_series: pd.Series,
    mode: str,
) -> list[dict[str, Any]]:
    if len(close) != len(signal_series) or len(rows) != len(signal_series):
        raise ValueError("close, signal_series, and rows must have matching lengths.")
    sorted_rows = sorted(rows, key=lambda item: str(item.get("open_time") or ""))
    targets = _target_exposures(signal_series, mode=mode)
    return [
        {
            "open_time": row.get("open_time"),
            "close": row.get("close"),
            "signal": {"active": bool(targets.iloc[index])},
            "position": {
                "target_exposure": 1.0 if bool(targets.iloc[index]) else 0.0,
                "unit": "fractional_long_exposure",
            },
        }
        for index, row in enumerate(sorted_rows)
    ]


def _target_exposures(signal_series: pd.Series, *, mode: str) -> pd.Series:
    active = signal_series.fillna(False).astype(bool)
    if mode == "long_only":
        return active.astype(int).cummax().astype(bool)
    return active


def _bounded_metrics(evaluation: dict[str, Any], *, initial_cash: float) -> dict[str, Any]:
    strategy_metrics = evaluation.get("strategy_metrics") if isinstance(evaluation.get("strategy_metrics"), dict) else {}
    trade_summary = evaluation.get("trade_summary") if isinstance(evaluation.get("trade_summary"), dict) else {}
    model = evaluation.get("execution_model") if isinstance(evaluation.get("execution_model"), dict) else {}
    final_multiplier = float(strategy_metrics.get("final_equity") or 0.0)
    return {
        "calculation_backend": HALPHA_BACKTEST_BACKEND,
        "execution_model_id": model.get("execution_model_id"),
        "signal_timing": model.get("signal_timing"),
        "position_timing": model.get("position_timing"),
        "lookahead_policy": model.get("lookahead_policy"),
        "return_metric_basis": "net_after_costs",
        "total_return_pct": strategy_metrics.get("net_return_pct"),
        "gross_return_pct": strategy_metrics.get("gross_return_pct"),
        "net_return_pct": strategy_metrics.get("net_return_pct"),
        "total_cost_pct": strategy_metrics.get("total_cost_pct"),
        "cost_drag_pct": strategy_metrics.get("cost_drag_pct"),
        "max_drawdown_pct": strategy_metrics.get("max_drawdown_pct"),
        "trade_count": trade_summary.get("trade_count"),
        "turnover": trade_summary.get("turnover"),
        "exposure_pct": trade_summary.get("exposure_pct"),
        "final_equity": _round(initial_cash * final_multiplier),
        "final_equity_multiplier": strategy_metrics.get("final_equity"),
    }


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
