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


NAME = "bollinger_rsi_reversion"
DEFAULT_PARAMS = {
    "bollinger_window": 20,
    "band_std": 2.0,
    "rsi_window": 14,
    "rsi_oversold": 30.0,
    "rsi_overbought": 70.0,
    "trend_window": 50,
    "trend_filter_pct": 8.0,
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
    minimum_rows = max(
        params["bollinger_window"],
        params["rsi_window"] + 1,
        params["trend_window"] + 1,
    )
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
    close = frame["close"]
    middle, upper, lower, rsi, trend_return = _vectorbt_bollinger_rsi(close, params)
    latest_close = float(close.iloc[-1])
    latest_middle = float(middle.iloc[-1])
    latest_upper = float(upper.iloc[-1])
    latest_lower = float(lower.iloc[-1])
    latest_rsi = float(rsi.iloc[-1])
    latest_trend_window_pct = float(trend_return.iloc[-1])
    band_width_pct = _pct(latest_upper - latest_lower, latest_close)
    percent_b = _percent_b(latest_close, latest_lower, latest_upper)
    latest_oversold = latest_close <= latest_lower and latest_rsi <= params["rsi_oversold"]
    latest_overbought = latest_close >= latest_upper and latest_rsi >= params["rsi_overbought"]
    strong_downtrend = latest_trend_window_pct <= -params["trend_filter_pct"]
    strong_uptrend = latest_trend_window_pct >= params["trend_filter_pct"]
    trend_filter_active = (latest_oversold and strong_downtrend) or (latest_overbought and strong_uptrend)
    signal_series = _active_reversion_state(
        close,
        middle,
        upper,
        lower,
        rsi,
        trend_return,
        params,
    )
    entry_count = _transition_count(signal_series, from_value=False, to_value=True)
    exit_count = _transition_count(signal_series, from_value=True, to_value=False)
    latest_signal = bool(signal_series.iloc[-1])
    previous_signal = bool(signal_series.iloc[-2])
    latest_entry = latest_signal and not previous_signal
    latest_exit = previous_signal and not latest_signal
    warnings = _strategy_warnings(
        latest_oversold=latest_oversold,
        latest_overbought=latest_overbought,
        strong_downtrend=strong_downtrend,
        strong_uptrend=strong_uptrend,
    )
    latest_regime = _latest_regime(
        latest_oversold=latest_oversold,
        latest_overbought=latest_overbought,
        latest_signal=latest_signal,
        strong_downtrend=strong_downtrend,
        strong_uptrend=strong_uptrend,
    )
    direction = _direction(
        latest_oversold=latest_oversold,
        latest_overbought=latest_overbought,
        strong_downtrend=strong_downtrend,
        strong_uptrend=strong_uptrend,
    )
    strength = _strength(
        latest_oversold=latest_oversold,
        latest_overbought=latest_overbought,
        percent_b=percent_b,
        rsi=latest_rsi,
    )
    confidence = _confidence(len(rows), minimum_rows=minimum_rows, warnings=warnings)

    indicators = {
        "calculation_backend": VECTORBT_BACKEND,
        "latest_close": _round(latest_close),
        "bollinger_middle": _round(latest_middle),
        "bollinger_upper": _round(latest_upper),
        "bollinger_lower": _round(latest_lower),
        "bollinger_band_width_pct": _round(band_width_pct),
        "bollinger_percent_b": _round(percent_b),
        "rsi": _round(latest_rsi),
        "rsi_oversold_threshold": _round(params["rsi_oversold"]),
        "rsi_overbought_threshold": _round(params["rsi_overbought"]),
        "trend_window_pct": _round(latest_trend_window_pct),
        "trend_filter_pct": _round(params["trend_filter_pct"]),
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
        "latest_oversold": latest_oversold,
        "latest_overbought": latest_overbought,
        "trend_filter_active": trend_filter_active,
        "strong_trend_direction": _strong_trend_direction(strong_downtrend, strong_uptrend),
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
            "summary": _assessment_summary(direction, latest_regime, warnings),
            "evidence": [
                (
                    f"latest_close is {_round(latest_close)} versus Bollinger lower "
                    f"{_round(latest_lower)}, middle {_round(latest_middle)}, and upper {_round(latest_upper)}."
                ),
                (
                    f"rsi is {_round(latest_rsi)} against oversold threshold "
                    f"{_round(params['rsi_oversold'])} and overbought threshold "
                    f"{_round(params['rsi_overbought'])}."
                ),
                (
                    f"trend_window_pct is {_round(latest_trend_window_pct)}% against trend_filter_pct "
                    f"{_round(params['trend_filter_pct'])}%."
                ),
            ],
            "uncertainty": [
                "Strategy uses OHLCV close prices only and excludes text events.",
                "Mean-reversion conditions can persist or fail when a strong trend continues.",
                "Backtest diagnostics are bounded historical research material, not return forecasts.",
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
            "uncertainty": ["Insufficient data prevents Bollinger RSI reversion assessment."],
        },
        warnings=[item],
        error=None,
    )


def _params(raw: Any) -> dict[str, Any]:
    params = dict(DEFAULT_PARAMS)
    if isinstance(raw, dict):
        params.update(raw)
    bollinger_window = _positive_int(params["bollinger_window"], "bollinger_window")
    band_std = _positive_number(params["band_std"], "band_std")
    rsi_window = _positive_int(params["rsi_window"], "rsi_window")
    rsi_oversold = _rsi_threshold(params["rsi_oversold"], "rsi_oversold")
    rsi_overbought = _rsi_threshold(params["rsi_overbought"], "rsi_overbought")
    if rsi_oversold >= rsi_overbought:
        raise ValueError("rsi_oversold must be lower than rsi_overbought.")
    trend_window = _positive_int(params["trend_window"], "trend_window")
    trend_filter_pct = _positive_number(params["trend_filter_pct"], "trend_filter_pct")
    return {
        "bollinger_window": bollinger_window,
        "band_std": band_std,
        "rsi_window": rsi_window,
        "rsi_oversold": rsi_oversold,
        "rsi_overbought": rsi_overbought,
        "trend_window": trend_window,
        "trend_filter_pct": trend_filter_pct,
    }


def _positive_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer.")
    return value


def _positive_number(value: Any, name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or float(value) <= 0
    ):
        raise ValueError(f"{name} must be a positive number.")
    return float(value)


def _rsi_threshold(value: Any, name: str) -> float:
    number = _positive_number(value, name)
    if number >= 100:
        raise ValueError(f"{name} must be lower than 100.")
    return number


def _frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows).sort_values("open_time")
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = frame[column].astype(float)
    return frame


def _input_is_insufficient(view: dict[str, Any], rows: list[dict[str, Any]], *, minimum_rows: int) -> bool:
    return bool(view.get("insufficient_data")) or len(rows) < minimum_rows


def _vectorbt_bollinger_rsi(
    close: pd.Series,
    params: dict[str, Any],
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    indicator = _bollinger_rsi_indicator()
    result = indicator.run(
        close,
        bollinger_window=params["bollinger_window"],
        band_std=params["band_std"],
        rsi_window=params["rsi_window"],
        trend_window=params["trend_window"],
    )
    return (
        _series_output(result.bollinger_middle, index=close.index),
        _series_output(result.bollinger_upper, index=close.index),
        _series_output(result.bollinger_lower, index=close.index),
        _series_output(result.rsi, index=close.index),
        _series_output(result.trend_return, index=close.index),
    )


@lru_cache(maxsize=1)
def _bollinger_rsi_indicator() -> Any:
    vbt = load_vectorbt()
    return vbt.IndicatorFactory(
        input_names=["close"],
        param_names=["bollinger_window", "band_std", "rsi_window", "trend_window"],
        output_names=[
            "bollinger_middle",
            "bollinger_upper",
            "bollinger_lower",
            "rsi",
            "trend_return",
        ],
    ).from_apply_func(_bollinger_rsi_apply)


def _bollinger_rsi_apply(
    close: Any,
    bollinger_window: int,
    band_std: float,
    rsi_window: int,
    trend_window: int,
) -> tuple[Any, Any, Any, Any, Any]:
    close_series = pd.DataFrame(close).iloc[:, 0].astype(float)
    middle = close_series.rolling(int(bollinger_window)).mean()
    rolling_std = close_series.rolling(int(bollinger_window)).std(ddof=0)
    upper = middle + (rolling_std * float(band_std))
    lower = middle - (rolling_std * float(band_std))
    delta = close_series.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    average_gain = gains.rolling(int(rsi_window)).mean()
    average_loss = losses.rolling(int(rsi_window)).mean()
    rs = average_gain.divide(average_loss.where(average_loss != 0))
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.mask((average_loss == 0) & (average_gain > 0), 100.0)
    rsi = rsi.mask((average_gain == 0) & (average_loss > 0), 0.0)
    rsi = rsi.mask((average_gain == 0) & (average_loss == 0), 50.0)
    trend_return = close_series.pct_change(int(trend_window)) * 100
    return (
        middle.to_numpy(),
        upper.to_numpy(),
        lower.to_numpy(),
        rsi.to_numpy(),
        trend_return.to_numpy(),
    )


def _series_output(value: Any, *, index: pd.Index) -> pd.Series:
    if isinstance(value, pd.DataFrame):
        series = value.iloc[:, 0] if not value.empty else pd.Series(dtype=float)
    elif isinstance(value, pd.Series):
        series = value
    else:
        series = pd.Series(value)
    return pd.Series(series.to_numpy(dtype=float), index=index)


def _active_reversion_state(
    close: pd.Series,
    middle: pd.Series,
    upper: pd.Series,
    lower: pd.Series,
    rsi: pd.Series,
    trend_return: pd.Series,
    params: dict[str, Any],
) -> pd.Series:
    active = []
    current = False
    for latest_close, mid, high, low, latest_rsi, trend_pct in zip(
        close,
        middle,
        upper,
        lower,
        rsi,
        trend_return,
        strict=True,
    ):
        if _has_nan(latest_close, mid, high, low, latest_rsi, trend_pct):
            active.append(current)
            continue
        oversold = float(latest_close) <= float(low) and float(latest_rsi) <= params["rsi_oversold"]
        overbought = float(latest_close) >= float(high) and float(latest_rsi) >= params["rsi_overbought"]
        strong_downtrend = float(trend_pct) <= -params["trend_filter_pct"]
        if current and (float(latest_close) >= float(mid) or overbought):
            current = False
        elif not current and oversold and not strong_downtrend:
            current = True
        active.append(current)
    return pd.Series(active, index=close.index)


def _transition_count(series: pd.Series, *, from_value: bool, to_value: bool) -> int:
    clean = series.fillna(False).astype(bool)
    previous = clean.shift(1, fill_value=False)
    return int(((previous == from_value) & (clean == to_value)).sum())


def _strategy_warnings(
    *,
    latest_oversold: bool,
    latest_overbought: bool,
    strong_downtrend: bool,
    strong_uptrend: bool,
) -> list[dict[str, Any]]:
    if latest_oversold and strong_downtrend:
        return [
            warning(
                "strong_downtrend_reversion_filter",
                "Oversold mean-reversion setup appears inside a strong downtrend; snapback evidence is less reliable.",
                source="strategy",
            )
        ]
    if latest_overbought and strong_uptrend:
        return [
            warning(
                "strong_uptrend_reversion_filter",
                "Overbought mean-reversion setup appears inside a strong uptrend; reversal evidence is less reliable.",
                source="strategy",
            )
        ]
    return []


def _direction(
    *,
    latest_oversold: bool,
    latest_overbought: bool,
    strong_downtrend: bool,
    strong_uptrend: bool,
) -> str:
    if (latest_oversold and strong_downtrend) or (latest_overbought and strong_uptrend):
        return "mixed"
    if latest_oversold:
        return "bullish"
    if latest_overbought:
        return "bearish"
    return "neutral"


def _strength(
    *,
    latest_oversold: bool,
    latest_overbought: bool,
    percent_b: float,
    rsi: float,
) -> str:
    if latest_oversold:
        if percent_b <= -0.25 or rsi <= 20:
            return "high"
        return "medium"
    if latest_overbought:
        if percent_b >= 1.25 or rsi >= 80:
            return "high"
        return "medium"
    return "low"


def _confidence(row_count: int, *, minimum_rows: int, warnings: list[dict[str, Any]]) -> str:
    if warnings:
        return "low"
    if row_count >= max(minimum_rows * 2, 80):
        return "high"
    return "medium"


def _latest_regime(
    *,
    latest_oversold: bool,
    latest_overbought: bool,
    latest_signal: bool,
    strong_downtrend: bool,
    strong_uptrend: bool,
) -> str:
    if latest_oversold and strong_downtrend:
        return "oversold_reversion_risk_strong_downtrend"
    if latest_overbought and strong_uptrend:
        return "overbought_reversion_risk_strong_uptrend"
    if latest_oversold:
        return "oversold_reversion_watch"
    if latest_overbought:
        return "overbought_reversion_watch"
    if latest_signal:
        return "reversion_long_active"
    return "neutral_range"


def _assessment_summary(direction: str, latest_regime: str, warnings: list[dict[str, Any]]) -> str:
    if warnings:
        return f"Bollinger RSI mean-reversion state is {latest_regime}, with trend-filter warnings."
    if direction == "bullish":
        return "Price is stretched below the lower Bollinger band with oversold RSI context."
    if direction == "bearish":
        return "Price is stretched above the upper Bollinger band with overbought RSI context."
    return f"No stretched Bollinger RSI mean-reversion condition is present; latest regime is {latest_regime}."


def _strong_trend_direction(strong_downtrend: bool, strong_uptrend: bool) -> str:
    if strong_downtrend:
        return "down"
    if strong_uptrend:
        return "up"
    return "none"


def _pct(value: float, base: float) -> float:
    if base == 0:
        return 0.0
    return (value / base) * 100


def _percent_b(latest_close: float, lower: float, upper: float) -> float:
    width = upper - lower
    if width <= 0 or math.isnan(width):
        return 0.5
    return (latest_close - lower) / width


def _has_nan(*values: Any) -> bool:
    return any(math.isnan(float(value)) for value in values)


def _round(value: float) -> float:
    return round(float(value), 6)
