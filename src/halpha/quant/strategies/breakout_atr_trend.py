from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

import pandas as pd

from ..backtest import bounded_backtest_diagnostic
from ..strategy_records import (
    backtest_diagnostic,
    data_quality,
    parameter_diagnostic,
    strategy_run_record,
    warning,
)
from ..vectorbt_engine import load_vectorbt


NAME = "breakout_atr_trend"
DEFAULT_PARAMS = {
    "breakout_window": 20,
    "exit_window": 10,
    "atr_window": 14,
}
VECTORBT_BACKEND = "vectorbt.IndicatorFactory"


def run(
    strategy: dict[str, Any],
    view: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    engine: dict[str, str],
    created_at: str,
) -> dict[str, Any]:
    params = _params(strategy.get("params"))
    minimum_rows = max(params["breakout_window"], params["exit_window"], params["atr_window"]) + 1
    if _input_is_insufficient(view, rows, minimum_rows=minimum_rows):
        return _insufficient_run(
            strategy,
            view,
            rows,
            params=params,
            engine=engine,
            created_at=created_at,
            minimum_rows=minimum_rows,
        )

    frame = _frame(rows)
    high = frame["high"]
    low = frame["low"]
    close = frame["close"]
    latest_close = float(close.iloc[-1])
    breakout_high, breakout_low, exit_low, atr = _vectorbt_breakout_atr(
        high,
        low,
        close,
        params,
    )
    latest_breakout_high = float(breakout_high.iloc[-1])
    latest_breakout_low = float(breakout_low.iloc[-1])
    latest_exit_low = float(exit_low.iloc[-1])
    latest_atr = float(atr.iloc[-1])
    atr_pct = _pct(latest_atr, latest_close)
    range_width_pct = _pct(latest_breakout_high - latest_breakout_low, latest_close)
    breakout_distance_atr = _breakout_distance_atr(latest_close, latest_breakout_high, latest_atr)
    signal_series = _active_breakout_state(close, breakout_high, exit_low)
    entry_count = _transition_count(signal_series, from_value=False, to_value=True)
    exit_count = _transition_count(signal_series, from_value=True, to_value=False)
    latest_signal = bool(signal_series.iloc[-1])
    previous_signal = bool(signal_series.iloc[-2])
    latest_entry = latest_signal and not previous_signal
    latest_exit = previous_signal and not latest_signal
    latest_regime = _latest_regime(
        latest_signal=latest_signal,
        latest_entry=latest_entry,
        latest_exit=latest_exit,
        latest_close=latest_close,
        breakout_high=latest_breakout_high,
        exit_low=latest_exit_low,
        breakout_distance_atr=breakout_distance_atr,
    )
    warnings = _strategy_warnings(atr_pct)
    direction = "bullish" if latest_signal else "neutral"
    strength = _strength(latest_signal=latest_signal, breakout_distance_atr=breakout_distance_atr)
    confidence = _confidence(len(rows), minimum_rows=minimum_rows, warnings=warnings)

    indicators = {
        "calculation_backend": VECTORBT_BACKEND,
        "latest_close": _round(latest_close),
        "breakout_window_high": _round(latest_breakout_high),
        "breakout_window_low": _round(latest_breakout_low),
        "exit_window_low": _round(latest_exit_low),
        "atr": _round(latest_atr),
        "atr_pct": _round(atr_pct),
        "range_width_pct": _round(range_width_pct),
        "breakout_distance_atr": _round(breakout_distance_atr),
        "row_count": len(rows),
    }
    signals = {
        "calculation_backend": VECTORBT_BACKEND,
        "latest_regime": latest_regime,
        "entry_count": entry_count,
        "exit_count": exit_count,
        "latest_entry": latest_entry,
        "latest_exit": latest_exit,
        "latest_signal_active": latest_signal,
    }
    return strategy_run_record(
        strategy=strategy,
        view=view,
        engine=engine,
        created_at=created_at,
        status="succeeded",
        params=params,
        data_quality=data_quality(view, rows, minimum_rows=minimum_rows, sufficient=True),
        indicators=indicators,
        signals=signals,
        backtest_diagnostic=bounded_backtest_diagnostic(
            strategy,
            view,
            rows,
            close=close,
            signal_series=signal_series,
        ),
        parameter_diagnostic=parameter_diagnostic(),
        assessment={
            "direction": direction,
            "strength": strength,
            "confidence": confidence,
            "summary": _assessment_summary(direction, latest_regime),
            "evidence": [
                f"latest_close is {_round(latest_close)} versus breakout_window_high {_round(latest_breakout_high)}.",
                f"atr_pct is {_round(atr_pct)}% over the configured ATR window.",
                f"breakout_distance_atr is {_round(breakout_distance_atr)}.",
            ],
            "uncertainty": [
                "Strategy uses OHLCV ranges only and excludes text events.",
                "ATR is historical volatility context, not a live stop or position sizing instruction.",
                "Breakouts can fail after moving beyond the recent range.",
            ],
        },
        warnings=warnings,
        error=None,
    )


def failed_params(strategy: dict[str, Any]) -> dict[str, Any]:
    params = dict(DEFAULT_PARAMS)
    raw = strategy.get("params")
    if isinstance(raw, dict):
        params.update(raw)
    return params


def _insufficient_run(
    strategy: dict[str, Any],
    view: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    params: dict[str, Any],
    engine: dict[str, str],
    created_at: str,
    minimum_rows: int,
) -> dict[str, Any]:
    item = warning(
        "insufficient_ohlcv_rows",
        (
            f"{view.get('source')} {view.get('symbol')} {view.get('timeframe')} has "
            f"{len(rows)} OHLCV rows; {NAME} requires at least {minimum_rows} rows."
        ),
        source="data_quality",
    )
    return strategy_run_record(
        strategy=strategy,
        view=view,
        engine=engine,
        created_at=created_at,
        status="insufficient_data",
        params=params,
        data_quality=data_quality(view, rows, minimum_rows=minimum_rows, sufficient=False, warnings=[item]),
        indicators={},
        signals={},
        backtest_diagnostic=backtest_diagnostic(strategy, view, rows, status="skipped"),
        parameter_diagnostic=parameter_diagnostic(),
        assessment={
            "direction": "unknown",
            "strength": "unknown",
            "confidence": "low",
            "summary": "Strategy result is unavailable because input data is insufficient.",
            "evidence": [f"input view has {len(rows)} OHLCV rows."],
            "uncertainty": ["Insufficient data prevents breakout ATR trend assessment."],
        },
        warnings=[item],
        error=None,
    )


def _params(raw: Any) -> dict[str, Any]:
    params = dict(DEFAULT_PARAMS)
    if isinstance(raw, dict):
        params.update(raw)
    return {
        "breakout_window": _positive_int(params["breakout_window"], "breakout_window"),
        "exit_window": _positive_int(params["exit_window"], "exit_window"),
        "atr_window": _positive_int(params["atr_window"], "atr_window"),
    }


def _positive_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer.")
    return value


def _frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows).sort_values("open_time")
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = frame[column].astype(float)
    return frame


def _input_is_insufficient(view: dict[str, Any], rows: list[dict[str, Any]], *, minimum_rows: int) -> bool:
    return bool(view.get("insufficient_data")) or len(rows) < minimum_rows


def _vectorbt_breakout_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    params: dict[str, int],
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    indicator = _breakout_atr_indicator()
    result = indicator.run(
        high,
        low,
        close,
        breakout_window=params["breakout_window"],
        exit_window=params["exit_window"],
        atr_window=params["atr_window"],
    )
    return (
        _series_output(result.breakout_high, index=close.index),
        _series_output(result.breakout_low, index=close.index),
        _series_output(result.exit_low, index=close.index),
        _series_output(result.atr, index=close.index),
    )


@lru_cache(maxsize=1)
def _breakout_atr_indicator() -> Any:
    vbt = load_vectorbt()
    return vbt.IndicatorFactory(
        input_names=["high", "low", "close"],
        param_names=["breakout_window", "exit_window", "atr_window"],
        output_names=["breakout_high", "breakout_low", "exit_low", "atr"],
    ).from_apply_func(_breakout_atr_apply)


def _breakout_atr_apply(
    high: Any,
    low: Any,
    close: Any,
    breakout_window: int,
    exit_window: int,
    atr_window: int,
) -> tuple[Any, Any, Any, Any]:
    high_series = pd.DataFrame(high).iloc[:, 0].astype(float)
    low_series = pd.DataFrame(low).iloc[:, 0].astype(float)
    close_series = pd.DataFrame(close).iloc[:, 0].astype(float)
    frame = pd.DataFrame(
        {
            "high": high_series,
            "low": low_series,
            "close": close_series,
        }
    )
    breakout_high = frame["high"].shift(1).rolling(int(breakout_window)).max()
    breakout_low = frame["low"].shift(1).rolling(int(breakout_window)).min()
    exit_low = frame["low"].shift(1).rolling(int(exit_window)).min()
    previous_close = frame["close"].shift(1)
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = true_range.rolling(int(atr_window)).mean()
    return (
        breakout_high.to_numpy(),
        breakout_low.to_numpy(),
        exit_low.to_numpy(),
        atr.to_numpy(),
    )


def _series_output(value: Any, *, index: pd.Index) -> pd.Series:
    if isinstance(value, pd.DataFrame):
        series = value.iloc[:, 0] if not value.empty else pd.Series(dtype=float)
    elif isinstance(value, pd.Series):
        series = value
    else:
        series = pd.Series(value)
    return pd.Series(series.to_numpy(dtype=float), index=index)


def _active_breakout_state(close: pd.Series, breakout_high: pd.Series, exit_low: pd.Series) -> pd.Series:
    active = []
    current = False
    for latest_close, high_level, exit_level in zip(close, breakout_high, exit_low, strict=True):
        if not math.isnan(float(high_level)) and float(latest_close) > float(high_level):
            current = True
        elif not math.isnan(float(exit_level)) and float(latest_close) < float(exit_level):
            current = False
        active.append(current)
    return pd.Series(active, index=close.index)


def _transition_count(series: pd.Series, *, from_value: bool, to_value: bool) -> int:
    clean = series.fillna(False).astype(bool)
    previous = clean.shift(1, fill_value=False)
    return int(((previous == from_value) & (clean == to_value)).sum())


def _pct(value: float, base: float) -> float:
    if base == 0:
        return 0.0
    return (value / base) * 100


def _breakout_distance_atr(latest_close: float, breakout_high: float, atr: float) -> float:
    if atr <= 0 or math.isnan(atr):
        return 0.0
    return (latest_close - breakout_high) / atr


def _latest_regime(
    *,
    latest_signal: bool,
    latest_entry: bool,
    latest_exit: bool,
    latest_close: float,
    breakout_high: float,
    exit_low: float,
    breakout_distance_atr: float,
) -> str:
    if latest_entry and breakout_distance_atr >= 0.5:
        return "confirmed_breakout"
    if latest_entry:
        return "early_breakout"
    if latest_signal:
        return "trend_active_above_exit_floor"
    if latest_exit or latest_close < exit_low:
        return "range_breakdown_exit"
    if latest_close > breakout_high:
        return "early_breakout"
    return "range_bound"


def _strategy_warnings(atr_pct: float) -> list[dict[str, Any]]:
    if atr_pct >= 8:
        return [
            warning(
                "high_atr_volatility_context",
                "ATR is elevated relative to price, so breakout interpretation should stay risk-bounded.",
                source="strategy",
            )
        ]
    return []


def _strength(*, latest_signal: bool, breakout_distance_atr: float) -> str:
    if not latest_signal:
        return "low"
    if breakout_distance_atr >= 1:
        return "high"
    if breakout_distance_atr >= 0.5:
        return "medium"
    return "low"


def _confidence(row_count: int, *, minimum_rows: int, warnings: list[dict[str, Any]]) -> str:
    if warnings:
        return "medium"
    if row_count >= max(minimum_rows * 2, 60):
        return "high"
    return "medium"


def _assessment_summary(direction: str, latest_regime: str) -> str:
    if direction == "bullish":
        return f"Price is in a breakout ATR trend state with latest regime {latest_regime}."
    return f"No active upside breakout is present; latest regime is {latest_regime}."


def _round(value: float) -> float:
    return round(float(value), 6)
