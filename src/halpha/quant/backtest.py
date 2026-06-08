from __future__ import annotations

from typing import Any

import pandas as pd

from .strategy_records import backtest_assumptions, backtest_diagnostic
from .vectorbt_engine import load_vectorbt


VECTORBT_PORTFOLIO_BACKEND = "vectorbt.Portfolio.from_signals"
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
    entries, exits = _portfolio_signals(signal_series, mode=str(assumptions["mode"]))
    vbt = load_vectorbt()
    portfolio = vbt.Portfolio.from_signals(
        close,
        entries=entries,
        exits=exits,
        direction="longonly",
        init_cash=float(assumptions["initial_cash"]),
        fees=float(assumptions["fees_bps"]) / 10000,
        slippage=float(assumptions["slippage_bps"]) / 10000,
    )
    metrics = {
        "calculation_backend": VECTORBT_PORTFOLIO_BACKEND,
        "total_return_pct": _round(_scalar(portfolio.total_return()) * 100),
        "max_drawdown_pct": _round(_max_drawdown_pct(portfolio.value())),
        "trade_count": int(_scalar(portfolio.trades.count())),
        "exposure_pct": _round(_exposure_pct(portfolio.asset_value())),
        "final_equity": _round(_scalar(portfolio.final_value())),
    }
    return backtest_diagnostic(
        strategy,
        view,
        rows,
        status="succeeded",
        metrics=metrics,
        warnings=[
            BACKTEST_RESEARCH_WARNING,
            "Diagnostic uses configured close-to-close assumptions and is not future performance evidence.",
        ],
    )


def _portfolio_signals(signal_series: pd.Series, *, mode: str) -> tuple[pd.Series, pd.Series]:
    active = signal_series.fillna(False).astype(bool)
    previous = active.shift(1, fill_value=False)
    entries = active & ~previous
    if mode == "long_only":
        exits = pd.Series(False, index=active.index)
    else:
        exits = ~active & previous
    return entries, exits


def _scalar(value: Any) -> float:
    if isinstance(value, pd.Series):
        value = value.iloc[0] if not value.empty else 0.0
    elif isinstance(value, pd.DataFrame):
        value = value.iloc[0, 0] if not value.empty else 0.0
    elif hasattr(value, "item"):
        value = value.item()
    return float(value)


def _max_drawdown_pct(value: Any) -> float:
    series = _series(value)
    if series.empty:
        return 0.0
    peaks = series.cummax()
    drawdowns = (series / peaks) - 1
    return float(drawdowns.min()) * 100


def _exposure_pct(asset_value: Any) -> float:
    series = _series(asset_value)
    if series.empty:
        return 0.0
    return float((series > 0).mean()) * 100


def _series(value: Any) -> pd.Series:
    if isinstance(value, pd.DataFrame):
        if value.empty:
            return pd.Series(dtype=float)
        return value.iloc[:, 0].astype(float)
    if isinstance(value, pd.Series):
        return value.astype(float)
    return pd.Series([float(value)])


def _round(value: float) -> float:
    return round(float(value), 6)
