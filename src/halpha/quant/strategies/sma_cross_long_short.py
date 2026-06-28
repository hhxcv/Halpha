from __future__ import annotations

import math
from typing import Any

import pandas as pd

from ..signal_records import insufficient_signed_strategy_signal_records, signed_strategy_signal_records
from ..signed_strategy_support import signed_backtest_diagnostic, signed_transition_counts
from ..strategy_execution import input_is_insufficient, insufficient_strategy_run
from ..strategy_records import data_quality, parameter_diagnostic, strategy_run_record
from ..strategy_specs import require_strategy_spec


NAME = "sma_cross_long_short"
SPEC = require_strategy_spec(NAME)
DEFAULT_PARAMS = dict(SPEC.default_params)
CALCULATION_BACKEND = "pandas.rolling_mean"


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
    if input_is_insufficient(view, rows, minimum_rows=minimum_rows):
        return insufficient_strategy_run(
            strategy,
            view,
            rows,
            strategy_name=NAME,
            params=params,
            engine=engine,
            created_at=created_at,
            minimum_rows=minimum_rows,
            uncertainty="Insufficient data prevents signed SMA crossover assessment.",
        )

    state = _signal_state(strategy, view, rows, params=params)
    latest_record = state["signal_records"]["latest_record"]
    latest_exposure = float(latest_record["position"]["target_exposure"])
    latest_position_state = str(latest_record["position"]["position_state"])
    transition_counts = signed_transition_counts(state["signal_records"]["records"])
    warnings = _strategy_warnings(params)

    return strategy_run_record(
        strategy=strategy,
        view=view,
        engine=engine,
        created_at=created_at,
        status="succeeded",
        params=params,
        data_quality=data_quality(view, rows, minimum_rows=minimum_rows, sufficient=True, warnings=warnings),
        indicators={
            "calculation_backend": CALCULATION_BACKEND,
            "latest_close": _round(state["latest_close"]),
            "short_sma": _round(state["latest_short_sma"]),
            "long_sma": _round(state["latest_long_sma"]),
            "trend_spread_pct": _round(state["trend_spread_pct"]),
            "neutral_band_pct": _round(params["neutral_band_pct"]),
            "row_count": len(rows),
        },
        signals={
            "calculation_backend": CALCULATION_BACKEND,
            "latest_regime": _latest_regime(
                latest_position_state=latest_position_state,
                trend_spread_pct=state["trend_spread_pct"],
                neutral_band_pct=params["neutral_band_pct"],
            ),
            "latest_position_state": latest_position_state,
            "latest_target_exposure": _round(latest_exposure),
            **transition_counts,
        },
        backtest_diagnostic=signed_backtest_diagnostic(
            strategy,
            view,
            rows,
            signal_records=state["signal_records"],
        ),
        parameter_diagnostic=parameter_diagnostic(),
        assessment={
            "direction": _direction(latest_position_state),
            "strength": _strength(state["trend_spread_pct"], neutral_band_pct=params["neutral_band_pct"]),
            "confidence": _confidence(len(rows), minimum_rows=minimum_rows, warnings=warnings),
            "summary": _assessment_summary(
                latest_position_state,
                state["trend_spread_pct"],
                params["neutral_band_pct"],
            ),
            "evidence": [
                f"short_sma is {_round(state['latest_short_sma'])} versus long_sma {_round(state['latest_long_sma'])}.",
                f"trend_spread_pct is {_round(state['trend_spread_pct'])}%.",
                f"neutral_band_pct is {_round(params['neutral_band_pct'])}%.",
            ],
            "uncertainty": [
                "Strategy uses OHLCV close prices only and excludes text events.",
                "Signed exposure is research exposure, not borrowing, margin, or account state.",
                "Moving-average crossovers can lag during fast regime changes.",
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
    if input_is_insufficient(view, rows, minimum_rows=minimum_rows):
        return insufficient_signed_strategy_signal_records(
            strategy,
            view,
            rows,
            params=params,
            minimum_rows=minimum_rows,
        )
    return _signal_state(strategy, view, rows, params=params)["signal_records"]


def _params(raw: Any) -> dict[str, Any]:
    params = dict(DEFAULT_PARAMS)
    if isinstance(raw, dict):
        params.update(raw)
    short_window = _positive_int(params["short_window"], "short_window")
    long_window = _positive_int(params["long_window"], "long_window")
    if short_window >= long_window:
        raise ValueError("short_window must be lower than long_window.")
    neutral_band_pct = _bounded_number(params["neutral_band_pct"], "neutral_band_pct", minimum=0.0, maximum=100.0)
    return {
        "short_window": short_window,
        "long_window": long_window,
        "neutral_band_pct": neutral_band_pct,
    }


def _minimum_rows(params: dict[str, Any]) -> int:
    return int(params["long_window"]) + 1


def _signal_state(
    strategy: dict[str, Any],
    view: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    params: dict[str, Any],
) -> dict[str, Any]:
    frame = _frame(rows)
    close = frame["close"]
    short_sma = close.rolling(int(params["short_window"])).mean()
    long_sma = close.rolling(int(params["long_window"])).mean()
    trend_spread_pct = _trend_spread_pct(short_sma, long_sma, close)
    target_exposure_series = _target_exposure_series(
        trend_spread_pct,
        neutral_band_pct=float(params["neutral_band_pct"]),
    )
    indicator_contexts = _signal_indicator_contexts(
        short_sma,
        long_sma,
        trend_spread_pct,
        target_exposure_series,
        neutral_band_pct=float(params["neutral_band_pct"]),
    )
    return {
        "frame": frame,
        "close": close,
        "latest_close": float(close.iloc[-1]),
        "latest_short_sma": float(short_sma.iloc[-1]),
        "latest_long_sma": float(long_sma.iloc[-1]),
        "trend_spread_pct": float(trend_spread_pct.iloc[-1]),
        "target_exposure_series": target_exposure_series,
        "signal_records": signed_strategy_signal_records(
            strategy,
            view,
            rows,
            params=params,
            frame=frame,
            close=close,
            target_exposure_series=target_exposure_series,
            indicator_contexts=indicator_contexts,
        ),
    }


def _trend_spread_pct(short_sma: pd.Series, long_sma: pd.Series, close: pd.Series) -> pd.Series:
    spreads = []
    for short_value, long_value, close_value in zip(short_sma, long_sma, close, strict=True):
        if _has_nan(short_value, long_value) or float(close_value) == 0:
            spreads.append(math.nan)
        else:
            spreads.append(((float(short_value) - float(long_value)) / float(close_value)) * 100)
    return pd.Series(spreads, index=close.index, dtype=float)


def _target_exposure_series(trend_spread_pct: pd.Series, *, neutral_band_pct: float) -> pd.Series:
    values = []
    for value in trend_spread_pct:
        if not isinstance(value, (int, float)) or math.isnan(float(value)):
            values.append(0.0)
        elif float(value) > neutral_band_pct:
            values.append(1.0)
        elif float(value) < -neutral_band_pct:
            values.append(-1.0)
        else:
            values.append(0.0)
    return pd.Series(values, index=trend_spread_pct.index, dtype=float)


def _signal_indicator_contexts(
    short_sma: pd.Series,
    long_sma: pd.Series,
    trend_spread_pct: pd.Series,
    target_exposure_series: pd.Series,
    *,
    neutral_band_pct: float,
) -> list[dict[str, Any]]:
    contexts = []
    for short_value, long_value, spread_value, exposure in zip(
        short_sma,
        long_sma,
        trend_spread_pct,
        target_exposure_series,
        strict=True,
    ):
        exposure_value = float(exposure)
        contexts.append(
            {
                "calculation_backend": CALCULATION_BACKEND,
                "short_sma": _number_or_none(short_value),
                "long_sma": _number_or_none(long_value),
                "trend_spread_pct": _number_or_none(spread_value),
                "neutral_band_pct": neutral_band_pct,
                "target_exposure": exposure_value,
                "position_state": _position_state(exposure_value),
            }
        )
    return contexts


def _strategy_warnings(params: dict[str, Any]) -> list[dict[str, Any]]:
    if int(params["long_window"]) <= int(params["short_window"]) * 1.25:
        from ..strategy_records import warning

        return [
            warning(
                "narrow_sma_separation",
                "Short and long SMA windows are close; signed crossovers may be more sensitive to noise.",
                source="strategy",
            )
        ]
    return []


def _direction(position_state: str) -> str:
    if position_state == "long":
        return "bullish"
    if position_state == "short":
        return "bearish"
    return "neutral"


def _strength(trend_spread_pct: float, *, neutral_band_pct: float) -> str:
    excess = abs(trend_spread_pct) - neutral_band_pct
    if excess >= 5:
        return "high"
    if excess >= 1:
        return "medium"
    return "low"


def _confidence(row_count: int, *, minimum_rows: int, warnings: list[dict[str, Any]]) -> str:
    if warnings:
        return "medium"
    if row_count >= max(minimum_rows * 2, 120):
        return "high"
    return "medium"


def _latest_regime(*, latest_position_state: str, trend_spread_pct: float, neutral_band_pct: float) -> str:
    if latest_position_state == "long":
        return "signed_sma_bull_cross"
    if latest_position_state == "short":
        return "signed_sma_bear_cross"
    if abs(trend_spread_pct) <= neutral_band_pct:
        return "signed_sma_neutral_band"
    return "signed_sma_flat"


def _assessment_summary(position_state: str, trend_spread_pct: float, neutral_band_pct: float) -> str:
    if position_state == "long":
        return "Signed SMA crossover maps to long research exposure."
    if position_state == "short":
        return "Signed SMA crossover maps to short research exposure."
    return (
        "Signed SMA crossover is inside the configured neutral band; "
        f"trend_spread_pct is {_round(trend_spread_pct)}% and neutral_band_pct is {_round(neutral_band_pct)}%."
    )


def _position_state(exposure: float) -> str:
    if exposure > 0:
        return "long"
    if exposure < 0:
        return "short"
    return "flat"


def _frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows).sort_values("open_time")
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = frame[column].astype(float)
    return frame


def _positive_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive integer.")
    return value


def _bounded_number(value: Any, name: str, *, minimum: float, maximum: float) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or float(value) < minimum
        or float(value) > maximum
    ):
        raise ValueError(f"{name} must be a number between {minimum} and {maximum}.")
    return float(value)


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(float(value)):
        return None
    return _round(float(value))


def _has_nan(*values: Any) -> bool:
    return any(math.isnan(float(value)) for value in values)


def _round(value: float) -> float:
    return round(float(value), 6)
