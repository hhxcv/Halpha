from __future__ import annotations

import math
from typing import Any

import pandas as pd


REALIZED_VOLATILITY_FILTER_ID = "realized_volatility_max_pct_v1"
REGIME_FILTER_VERSION = 1


def realized_volatility_filter_contexts(
    close: pd.Series,
    *,
    timeframe: str,
    window: int,
    max_realized_volatility_pct: float,
) -> list[dict[str, Any]]:
    if not isinstance(window, int) or isinstance(window, bool) or window <= 0:
        raise ValueError("window must be a positive integer.")
    if (
        not isinstance(max_realized_volatility_pct, (int, float))
        or isinstance(max_realized_volatility_pct, bool)
        or not math.isfinite(float(max_realized_volatility_pct))
        or float(max_realized_volatility_pct) <= 0
    ):
        raise ValueError("max_realized_volatility_pct must be a positive number.")

    returns = close.astype(float).pct_change()
    contexts = []
    for position in range(len(close)):
        window_returns = returns.iloc[max(0, position - window + 1) : position + 1].dropna()
        if len(window_returns) < window:
            contexts.append(
                _context(
                    status="insufficient_data",
                    realized_volatility_pct=None,
                    max_realized_volatility_pct=float(max_realized_volatility_pct),
                    window=window,
                    timeframe=timeframe,
                    suppressed=True,
                    suppression_reason="insufficient_filter_data",
                )
            )
            continue
        realized_volatility_pct = _annualized_volatility_pct(window_returns, timeframe=timeframe)
        suppressed = realized_volatility_pct > float(max_realized_volatility_pct)
        contexts.append(
            _context(
                status="suppressed" if suppressed else "passed",
                realized_volatility_pct=realized_volatility_pct,
                max_realized_volatility_pct=float(max_realized_volatility_pct),
                window=window,
                timeframe=timeframe,
                suppressed=suppressed,
                suppression_reason="realized_volatility_above_max" if suppressed else None,
            )
        )
    return contexts


def _context(
    *,
    status: str,
    realized_volatility_pct: float | None,
    max_realized_volatility_pct: float,
    window: int,
    timeframe: str,
    suppressed: bool,
    suppression_reason: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": REGIME_FILTER_VERSION,
        "filter_id": REALIZED_VOLATILITY_FILTER_ID,
        "input_type": "ohlcv_close_return",
        "status": status,
        "suppressed": suppressed,
        "suppression_reason": suppression_reason,
        "realized_volatility_pct": _number_or_none(realized_volatility_pct),
        "max_realized_volatility_pct": _round(max_realized_volatility_pct),
        "window": window,
        "timeframe": timeframe,
        "lookahead_policy": "closed_bar_no_lookahead",
    }


def _annualized_volatility_pct(returns: pd.Series, *, timeframe: str) -> float:
    clean = returns.dropna()
    if clean.empty:
        return 0.0
    return _round(float(clean.std(ddof=0)) * math.sqrt(_periods_per_year(timeframe)) * 100)


def _periods_per_year(timeframe: str) -> int:
    if timeframe == "1h":
        return 365 * 24
    return 365


def _number_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(float(value)):
        return None
    return _round(float(value))


def _round(value: float) -> float:
    return round(float(value), 6)
