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


NAME = "tsmom_vol_scaled"
DEFAULT_PARAMS = {
    "return_window": 20,
    "volatility_window": 20,
    "target_volatility": 0.2,
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
    baseline_close = state["baseline_close"]
    return_window_pct = state["return_window_pct"]
    latest_return_pct = state["latest_return_pct"]
    realized_volatility = state["realized_volatility"]
    realized_volatility_pct = state["realized_volatility_pct"]
    exposure = state["exposure"]
    target_volatility = state["target_volatility"]
    entry_count = _transition_count(signal_series, from_value=False, to_value=True)
    exit_count = _transition_count(signal_series, from_value=True, to_value=False)
    latest_signal = bool(signal_series.iloc[-1])
    previous_signal = bool(signal_series.iloc[-2])
    latest_entry = latest_signal and not previous_signal
    latest_exit = previous_signal and not latest_signal
    direction = _direction(return_window_pct)
    strength = _strength(abs(return_window_pct))
    warnings = _strategy_warnings(realized_volatility, target_volatility)
    confidence = _confidence(len(rows), minimum_rows=minimum_rows, warnings=warnings)
    latest_regime = _latest_regime(
        return_window_pct=return_window_pct,
        exposure=exposure,
        target_volatility=target_volatility,
        realized_volatility=realized_volatility,
    )

    indicators = {
        "calculation_backend": VECTORBT_BACKEND,
        "latest_close": _round(latest_close),
        "baseline_close": _round(baseline_close),
        "return_window_pct": _round(return_window_pct),
        "latest_return_pct": _round(latest_return_pct),
        "realized_volatility_pct": _round(realized_volatility_pct),
        "target_volatility_pct": _round(target_volatility * 100),
        "volatility_scaled_exposure": _round(exposure),
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
            "summary": _assessment_summary(direction, latest_regime, warnings),
            "evidence": [
                f"return_window_pct is {_round(return_window_pct)}% over the configured return window.",
                f"realized_volatility_pct is {_round(realized_volatility_pct)}% against target_volatility_pct {_round(target_volatility * 100)}%.",
                f"volatility_scaled_exposure is {_round(exposure)}.",
            ],
            "uncertainty": [
                "Strategy uses OHLCV close prices only and excludes text events.",
                "Volatility scaling is a bounded research assumption, not position sizing advice.",
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
            "uncertainty": ["Insufficient data prevents strategy assessment."],
        },
        warnings=[item],
        error=None,
    )


def _params(raw: Any) -> dict[str, Any]:
    params = dict(DEFAULT_PARAMS)
    if isinstance(raw, dict):
        params.update(raw)
    return_window = _positive_int(params["return_window"], "return_window")
    volatility_window = _positive_int(params["volatility_window"], "volatility_window")
    target_volatility = _positive_number(params["target_volatility"], "target_volatility")
    return {
        "return_window": return_window,
        "volatility_window": volatility_window,
        "target_volatility": target_volatility,
    }


def _minimum_rows(params: dict[str, Any]) -> int:
    return max(params["return_window"], params["volatility_window"]) + 1


def _signal_state(
    strategy: dict[str, Any],
    view: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    params: dict[str, Any],
) -> dict[str, Any]:
    frame = _frame(rows)
    close = frame["close"]
    returns = close.pct_change()
    return_window = int(params["return_window"])
    volatility_window = int(params["volatility_window"])
    target_volatility = float(params["target_volatility"])
    momentum_return = _vectorbt_momentum_return(close, return_window)
    latest_close = float(close.iloc[-1])
    baseline_close = float(close.iloc[-return_window - 1])
    return_window_pct = float(momentum_return.iloc[-1]) * 100
    latest_return_pct = _pct_change(float(close.iloc[-1]), float(close.iloc[-2]))
    realized_volatility = _annualized_volatility(
        returns.tail(volatility_window),
        timeframe=str(view.get("timeframe")),
    )
    signal_series = momentum_return > 0
    indicator_contexts = _signal_indicator_contexts(
        close,
        returns,
        momentum_return,
        view,
        volatility_window=volatility_window,
        target_volatility=target_volatility,
    )
    return {
        "frame": frame,
        "close": close,
        "signal_series": signal_series,
        "latest_close": latest_close,
        "baseline_close": baseline_close,
        "return_window_pct": return_window_pct,
        "latest_return_pct": latest_return_pct,
        "realized_volatility": realized_volatility,
        "realized_volatility_pct": realized_volatility * 100,
        "exposure": _volatility_scaled_exposure(target_volatility, realized_volatility),
        "target_volatility": target_volatility,
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
    returns: pd.Series,
    momentum_return: pd.Series,
    view: dict[str, Any],
    *,
    volatility_window: int,
    target_volatility: float,
) -> list[dict[str, Any]]:
    contexts = []
    timeframe = str(view.get("timeframe"))
    for position in range(len(close)):
        window_returns = returns.iloc[max(0, position - volatility_window + 1) : position + 1]
        realized_volatility = _annualized_volatility(window_returns, timeframe=timeframe)
        contexts.append(
            {
                "calculation_backend": VECTORBT_BACKEND,
                "return_window_pct": float(momentum_return.iloc[position]) * 100,
                "realized_volatility_pct": realized_volatility * 100,
                "target_volatility_pct": target_volatility * 100,
                "volatility_scaled_exposure": _volatility_scaled_exposure(
                    target_volatility,
                    realized_volatility,
                ),
            }
        )
    return contexts


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


def _frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows).sort_values("open_time")
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = frame[column].astype(float)
    return frame


def _input_is_insufficient(view: dict[str, Any], rows: list[dict[str, Any]], *, minimum_rows: int) -> bool:
    return bool(view.get("insufficient_data")) or len(rows) < minimum_rows


def _vectorbt_momentum_return(close: pd.Series, window: int) -> pd.Series:
    indicator = _tsmom_indicator()
    result = indicator.run(close, window=window)
    return result.momentum_return


@lru_cache(maxsize=1)
def _tsmom_indicator() -> Any:
    vbt = load_vectorbt()
    return vbt.IndicatorFactory(
        input_names=["close"],
        param_names=["window"],
        output_names=["momentum_return"],
    ).from_apply_func(_momentum_return_apply)


def _momentum_return_apply(close: Any, window: int) -> Any:
    return pd.DataFrame(close).pct_change(int(window)).to_numpy()


def _annualized_volatility(returns: pd.Series, *, timeframe: str) -> float:
    clean = returns.dropna()
    if clean.empty:
        return 0.0
    periods = 365 * 24 if timeframe == "1h" else 365
    return float(clean.std(ddof=0)) * math.sqrt(periods)


def _volatility_scaled_exposure(target_volatility: float, realized_volatility: float) -> float:
    if realized_volatility <= 0:
        return 1.0
    return max(0.0, min(1.0, target_volatility / realized_volatility))


def _transition_count(series: pd.Series, *, from_value: bool, to_value: bool) -> int:
    clean = series.fillna(False).astype(bool)
    previous = clean.shift(1, fill_value=False)
    return int(((previous == from_value) & (clean == to_value)).sum())


def _strategy_warnings(realized_volatility: float, target_volatility: float) -> list[dict[str, Any]]:
    if target_volatility > 0 and realized_volatility > target_volatility * 1.5:
        return [
            warning(
                "high_realized_volatility",
                "Realized volatility is elevated relative to the target volatility assumption.",
                source="strategy",
            )
        ]
    return []


def _direction(return_window_pct: float) -> str:
    if return_window_pct > 0:
        return "bullish"
    if return_window_pct < 0:
        return "bearish"
    return "neutral"


def _strength(value: float) -> str:
    if value >= 10:
        return "high"
    if value >= 3:
        return "medium"
    return "low"


def _confidence(row_count: int, *, minimum_rows: int, warnings: list[dict[str, Any]]) -> str:
    if warnings:
        return "medium"
    if row_count >= max(minimum_rows * 2, 60):
        return "high"
    return "medium"


def _latest_regime(
    *,
    return_window_pct: float,
    exposure: float,
    target_volatility: float,
    realized_volatility: float,
) -> str:
    if return_window_pct < 0:
        return "risk_off_negative_momentum"
    if return_window_pct == 0:
        return "neutral"
    if target_volatility > 0 and realized_volatility > target_volatility * 1.5:
        return "risk_limited_momentum"
    if exposure < 0.5:
        return "risk_limited_momentum"
    return "risk_on_momentum"


def _assessment_summary(direction: str, latest_regime: str, warnings: list[dict[str, Any]]) -> str:
    if direction == "bullish" and warnings:
        return "Positive time-series momentum is present, but volatility keeps confidence bounded."
    if direction == "bullish":
        return f"Positive time-series momentum is present with latest regime {latest_regime}."
    if direction == "bearish":
        return f"Negative time-series momentum is present with latest regime {latest_regime}."
    return "Time-series momentum is neutral over the configured return window."


def _pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return ((current - previous) / previous) * 100


def _round(value: float) -> float:
    return round(float(value), 6)
