from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

import pandas as pd

from ..backtest import bounded_backtest_diagnostic
from ..signal_records import insufficient_strategy_signal_records, strategy_signal_records
from ..strategy_records import (
    backtest_diagnostic,
    data_quality,
    parameter_diagnostic,
    strategy_run_record,
    warning,
)
from ..vectorbt_engine import load_vectorbt


NAME = "sma_cross_trend"
DEFAULT_PARAMS = {
    "short_window": 20,
    "long_window": 50,
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
    minimum_rows = _minimum_rows(params)
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

    state = _signal_state(strategy, view, rows, params=params)
    close = state["close"]
    signal_series = state["signal_series"]
    latest_close = state["latest_close"]
    latest_short_sma = state["latest_short_sma"]
    latest_long_sma = state["latest_long_sma"]
    trend_spread_pct = state["trend_spread_pct"]
    entry_count = _transition_count(signal_series, from_value=False, to_value=True)
    exit_count = _transition_count(signal_series, from_value=True, to_value=False)
    latest_signal = bool(signal_series.iloc[-1])
    previous_signal = bool(signal_series.iloc[-2])
    latest_entry = latest_signal and not previous_signal
    latest_exit = previous_signal and not latest_signal
    warnings = _strategy_warnings(params)
    direction = "bullish" if latest_signal else "neutral"
    strength = _strength(latest_signal=latest_signal, trend_spread_pct=trend_spread_pct)
    confidence = _confidence(len(rows), minimum_rows=minimum_rows, warnings=warnings)
    latest_regime = _latest_regime(
        latest_signal=latest_signal,
        latest_entry=latest_entry,
        latest_exit=latest_exit,
        trend_spread_pct=trend_spread_pct,
    )

    indicators = {
        "calculation_backend": VECTORBT_BACKEND,
        "latest_close": _round(latest_close),
        "short_sma": _round(latest_short_sma),
        "long_sma": _round(latest_long_sma),
        "trend_spread_pct": _round(trend_spread_pct),
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
                f"short_sma is {_round(latest_short_sma)} versus long_sma {_round(latest_long_sma)}.",
                f"trend_spread_pct is {_round(trend_spread_pct)}%.",
            ],
            "uncertainty": [
                "Strategy uses OHLCV close prices only and excludes text events.",
                "Moving-average trend filters can lag around fast regime changes.",
                "Historical backtest diagnostics are research material, not forecasts.",
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


def signal_records(
    strategy: dict[str, Any],
    view: dict[str, Any],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    params = _params(strategy.get("params"))
    minimum_rows = _minimum_rows(params)
    if _input_is_insufficient(view, rows, minimum_rows=minimum_rows):
        return insufficient_strategy_signal_records(
            strategy,
            view,
            rows,
            params=params,
            minimum_rows=minimum_rows,
        )
    return _signal_state(strategy, view, rows, params=params)["signal_records"]


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
            "uncertainty": ["Insufficient data prevents SMA cross trend assessment."],
        },
        warnings=[item],
        error=None,
    )


def _params(raw: Any) -> dict[str, int]:
    params = dict(DEFAULT_PARAMS)
    if isinstance(raw, dict):
        params.update(raw)
    short_window = _positive_int(params["short_window"], "short_window")
    long_window = _positive_int(params["long_window"], "long_window")
    if short_window >= long_window:
        raise ValueError("short_window must be lower than long_window.")
    return {
        "short_window": short_window,
        "long_window": long_window,
    }


def _minimum_rows(params: dict[str, int]) -> int:
    return params["long_window"] + 1


def _signal_state(
    strategy: dict[str, Any],
    view: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    params: dict[str, int],
) -> dict[str, Any]:
    frame = _frame(rows)
    close = frame["close"]
    short_sma, long_sma = _vectorbt_sma_cross(close, params)
    signal_series = (short_sma > long_sma).fillna(False)
    latest_close = float(close.iloc[-1])
    latest_short_sma = float(short_sma.iloc[-1])
    latest_long_sma = float(long_sma.iloc[-1])
    trend_spread_pct = _pct(latest_short_sma - latest_long_sma, latest_close)
    indicator_contexts = _signal_indicator_contexts(close, short_sma, long_sma)
    return {
        "frame": frame,
        "close": close,
        "signal_series": signal_series,
        "latest_close": latest_close,
        "latest_short_sma": latest_short_sma,
        "latest_long_sma": latest_long_sma,
        "trend_spread_pct": trend_spread_pct,
        "signal_records": strategy_signal_records(
            strategy,
            view,
            rows,
            params=params,
            frame=frame,
            close=close,
            signal_series=signal_series,
            indicator_contexts=indicator_contexts,
        ),
    }


def _signal_indicator_contexts(
    close: pd.Series,
    short_sma: pd.Series,
    long_sma: pd.Series,
) -> list[dict[str, Any]]:
    contexts = []
    for latest_close, short_value, long_value in zip(close, short_sma, long_sma, strict=True):
        contexts.append(
            {
                "calculation_backend": VECTORBT_BACKEND,
                "short_sma": float(short_value) if not math.isnan(float(short_value)) else None,
                "long_sma": float(long_value) if not math.isnan(float(long_value)) else None,
                "trend_spread_pct": _pct(float(short_value) - float(long_value), float(latest_close))
                if not _has_nan(short_value, long_value)
                else None,
            }
        )
    return contexts


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


def _vectorbt_sma_cross(close: pd.Series, params: dict[str, int]) -> tuple[pd.Series, pd.Series]:
    indicator = _sma_cross_indicator()
    result = indicator.run(
        close,
        short_window=params["short_window"],
        long_window=params["long_window"],
    )
    return (
        _series_output(result.short_sma, index=close.index),
        _series_output(result.long_sma, index=close.index),
    )


@lru_cache(maxsize=1)
def _sma_cross_indicator() -> Any:
    vbt = load_vectorbt()
    return vbt.IndicatorFactory(
        input_names=["close"],
        param_names=["short_window", "long_window"],
        output_names=["short_sma", "long_sma"],
    ).from_apply_func(_sma_cross_apply)


def _sma_cross_apply(close: Any, short_window: int, long_window: int) -> tuple[Any, Any]:
    close_series = pd.DataFrame(close).iloc[:, 0].astype(float)
    short_sma = close_series.rolling(int(short_window)).mean()
    long_sma = close_series.rolling(int(long_window)).mean()
    return short_sma.to_numpy(), long_sma.to_numpy()


def _series_output(value: Any, *, index: pd.Index) -> pd.Series:
    if isinstance(value, pd.DataFrame):
        series = value.iloc[:, 0] if not value.empty else pd.Series(dtype=float)
    elif isinstance(value, pd.Series):
        series = value
    else:
        series = pd.Series(value)
    return pd.Series(series.to_numpy(dtype=float), index=index)


def _transition_count(series: pd.Series, *, from_value: bool, to_value: bool) -> int:
    clean = series.fillna(False).astype(bool)
    previous = clean.shift(1, fill_value=False)
    return int(((previous == from_value) & (clean == to_value)).sum())


def _strategy_warnings(params: dict[str, int]) -> list[dict[str, Any]]:
    if params["long_window"] <= params["short_window"] * 1.25:
        return [
            warning(
                "narrow_sma_separation",
                "Short and long SMA windows are close; crossovers may be more sensitive to noise.",
                source="strategy",
            )
        ]
    return []


def _strength(*, latest_signal: bool, trend_spread_pct: float) -> str:
    if not latest_signal:
        return "low"
    spread = abs(trend_spread_pct)
    if spread >= 5:
        return "high"
    if spread >= 1:
        return "medium"
    return "low"


def _confidence(row_count: int, *, minimum_rows: int, warnings: list[dict[str, Any]]) -> str:
    if warnings:
        return "medium"
    if row_count >= max(minimum_rows * 2, 120):
        return "high"
    return "medium"


def _latest_regime(
    *,
    latest_signal: bool,
    latest_entry: bool,
    latest_exit: bool,
    trend_spread_pct: float,
) -> str:
    if latest_entry:
        return "fresh_sma_bull_cross"
    if latest_exit:
        return "sma_bull_cross_lost"
    if latest_signal and trend_spread_pct >= 5:
        return "strong_sma_uptrend"
    if latest_signal:
        return "sma_uptrend_active"
    return "sma_downtrend_or_cash"


def _assessment_summary(direction: str, latest_regime: str) -> str:
    if direction == "bullish":
        return f"SMA cross trend filter is active with latest regime {latest_regime}."
    return f"SMA cross trend filter is inactive; latest regime is {latest_regime}."


def _pct(value: float, base: float) -> float:
    if base == 0:
        return 0.0
    return (value / base) * 100


def _has_nan(*values: Any) -> bool:
    return any(math.isnan(float(value)) for value in values)


def _round(value: float) -> float:
    return round(float(value), 6)
