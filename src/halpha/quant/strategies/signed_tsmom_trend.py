from __future__ import annotations

import math
from typing import Any

import pandas as pd

from ..regime_filters import realized_volatility_filter_contexts
from ..signal_records import insufficient_signed_strategy_signal_records, signed_strategy_signal_records
from ..signed_strategy_support import signed_backtest_diagnostic, signed_transition_counts
from ..strategy_execution import input_is_insufficient, insufficient_strategy_run
from ..strategy_records import (
    data_quality,
    parameter_diagnostic,
    strategy_run_record,
    warning,
)
from ..strategy_specs import require_strategy_spec


NAME = "signed_tsmom_trend"
SPEC = require_strategy_spec(NAME)
DEFAULT_PARAMS = dict(SPEC.default_params)
CALCULATION_BACKEND = "pandas.pct_change"


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
            uncertainty="Insufficient data prevents signed time-series momentum assessment.",
        )

    state = _signal_state(strategy, view, rows, params=params)
    latest_record = state["signal_records"]["latest_record"]
    latest_exposure = float(latest_record["position"]["target_exposure"])
    latest_position_state = str(latest_record["position"]["position_state"])
    return_window_pct = float(state["return_window_pct"])
    transition_counts = signed_transition_counts(state["signal_records"]["records"])
    warnings = _strategy_warnings(state)

    return strategy_run_record(
        strategy=strategy,
        view=view,
        engine=engine,
        created_at=created_at,
        status="succeeded",
        params=params,
        data_quality=data_quality(view, rows, minimum_rows=minimum_rows, sufficient=True),
        indicators={
            "calculation_backend": CALCULATION_BACKEND,
            "latest_close": _round(state["latest_close"]),
            "baseline_close": _round(state["baseline_close"]),
            "return_window_pct": _round(return_window_pct),
            "deadband_pct": _round(params["deadband_pct"]),
            "row_count": len(rows),
            **_filter_indicator_values(state),
        },
        signals={
            "calculation_backend": CALCULATION_BACKEND,
            "latest_regime": _latest_regime(
                latest_position_state=latest_position_state,
                return_window_pct=return_window_pct,
                deadband_pct=params["deadband_pct"],
            ),
            "latest_position_state": latest_position_state,
            "latest_target_exposure": _round(latest_exposure),
            **_filter_signal_values(state),
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
            "strength": _strength(return_window_pct, deadband_pct=params["deadband_pct"]),
            "confidence": _confidence(len(rows), minimum_rows=minimum_rows),
            "summary": _assessment_summary(latest_position_state, return_window_pct, params["deadband_pct"]),
            "evidence": [
                f"return_window_pct is {_round(return_window_pct)}% over the configured return window.",
                f"deadband_pct is {_round(params['deadband_pct'])}%.",
                f"latest_target_exposure is {_round(latest_exposure)}.",
                *_filter_evidence(state),
            ],
            "uncertainty": [
                "Strategy uses OHLCV close prices only and excludes text events.",
                "Signed exposure is research exposure, not borrowing, margin, or account state.",
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
    return_window = _positive_int(params["return_window"], "return_window")
    deadband_pct = _bounded_number(params["deadband_pct"], "deadband_pct", minimum=0.0, maximum=100.0)
    parsed = {
        "return_window": return_window,
        "deadband_pct": deadband_pct,
    }
    filter_enabled = _bool(params.get("volatility_filter_enabled", False), "volatility_filter_enabled")
    if filter_enabled:
        parsed.update(
            {
                "volatility_filter_enabled": True,
                "volatility_filter_window": _positive_int(
                    params.get("volatility_filter_window", 20),
                    "volatility_filter_window",
                ),
                "max_realized_volatility_pct": _positive_number(
                    params.get("max_realized_volatility_pct", 100.0),
                    "max_realized_volatility_pct",
                ),
            }
        )
    return parsed


def _minimum_rows(params: dict[str, Any]) -> int:
    minimum_rows = int(params["return_window"]) + 1
    if params.get("volatility_filter_enabled") is True:
        minimum_rows = max(minimum_rows, int(params["volatility_filter_window"]) + 1)
    return minimum_rows


def _signal_state(
    strategy: dict[str, Any],
    view: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    params: dict[str, Any],
) -> dict[str, Any]:
    frame = _frame(rows)
    close = frame["close"]
    return_window = int(params["return_window"])
    deadband_pct = float(params["deadband_pct"])
    momentum_return = close.pct_change(return_window)
    base_target_exposure_series = _target_exposure_series(momentum_return, deadband_pct=deadband_pct)
    filter_contexts = _filter_contexts(close, view, params)
    target_exposure_series = _apply_filters(
        base_target_exposure_series,
        filter_contexts=filter_contexts,
    )
    indicator_contexts = _signal_indicator_contexts(
        momentum_return,
        target_exposure_series,
        deadband_pct=deadband_pct,
        filter_contexts=filter_contexts,
    )
    latest_filter = filter_contexts[-1] if filter_contexts else None
    return {
        "frame": frame,
        "close": close,
        "latest_close": float(close.iloc[-1]),
        "baseline_close": float(close.iloc[-return_window - 1]),
        "return_window_pct": float(momentum_return.iloc[-1]) * 100,
        "filter_enabled": bool(filter_contexts),
        "latest_filter": latest_filter,
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


def _target_exposure_series(momentum_return: pd.Series, *, deadband_pct: float) -> pd.Series:
    threshold = deadband_pct / 100
    values = []
    for value in momentum_return:
        if not isinstance(value, (int, float)) or math.isnan(float(value)):
            values.append(0.0)
        elif float(value) > threshold:
            values.append(1.0)
        elif float(value) < -threshold:
            values.append(-1.0)
        else:
            values.append(0.0)
    return pd.Series(values, index=momentum_return.index, dtype=float)


def _signal_indicator_contexts(
    momentum_return: pd.Series,
    target_exposure_series: pd.Series,
    *,
    deadband_pct: float,
    filter_contexts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    contexts = []
    for position, (momentum_value, exposure) in enumerate(zip(momentum_return, target_exposure_series, strict=True)):
        return_window_pct = _number_or_none(float(momentum_value) * 100)
        context = {
            "calculation_backend": CALCULATION_BACKEND,
            "return_window_pct": return_window_pct,
            "deadband_pct": deadband_pct,
            "target_exposure": float(exposure),
            "position_state": _position_state(float(exposure)),
        }
        if filter_contexts:
            context["volatility_filter"] = filter_contexts[position]
        contexts.append(context)
    return contexts


def _filter_contexts(
    close: pd.Series,
    view: dict[str, Any],
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    if params.get("volatility_filter_enabled") is not True:
        return []
    return realized_volatility_filter_contexts(
        close,
        timeframe=str(view.get("timeframe")),
        window=int(params["volatility_filter_window"]),
        max_realized_volatility_pct=float(params["max_realized_volatility_pct"]),
    )


def _apply_filters(
    target_exposure_series: pd.Series,
    *,
    filter_contexts: list[dict[str, Any]],
) -> pd.Series:
    if not filter_contexts:
        return target_exposure_series
    values = []
    for exposure, context in zip(target_exposure_series, filter_contexts, strict=True):
        if context.get("suppressed") is True:
            values.append(0.0)
        else:
            values.append(float(exposure))
    return pd.Series(values, index=target_exposure_series.index, dtype=float)


def _filter_indicator_values(state: dict[str, Any]) -> dict[str, Any]:
    latest_filter = state.get("latest_filter")
    if not isinstance(latest_filter, dict):
        return {}
    return {
        "volatility_filter_status": latest_filter.get("status"),
        "volatility_filter_realized_volatility_pct": latest_filter.get("realized_volatility_pct"),
        "volatility_filter_max_realized_volatility_pct": latest_filter.get("max_realized_volatility_pct"),
    }


def _filter_signal_values(state: dict[str, Any]) -> dict[str, Any]:
    latest_filter = state.get("latest_filter")
    if not isinstance(latest_filter, dict):
        return {}
    return {
        "volatility_filter": latest_filter,
        "filter_suppression_reason": latest_filter.get("suppression_reason"),
    }


def _filter_evidence(state: dict[str, Any]) -> list[str]:
    latest_filter = state.get("latest_filter")
    if not isinstance(latest_filter, dict):
        return []
    return [
        (
            "volatility_filter status is "
            f"{latest_filter.get('status')} with realized_volatility_pct "
            f"{latest_filter.get('realized_volatility_pct')} and max_realized_volatility_pct "
            f"{latest_filter.get('max_realized_volatility_pct')}."
        )
    ]


def _strategy_warnings(state: dict[str, Any]) -> list[dict[str, Any]]:
    latest_filter = state.get("latest_filter")
    if not isinstance(latest_filter, dict):
        return []
    if latest_filter.get("suppression_reason") == "realized_volatility_above_max":
        return [
            warning(
                "realized_volatility_filter_suppressed_signal",
                "Signed momentum exposure is suppressed because realized volatility is above the configured maximum.",
                source="strategy_filter",
            )
        ]
    return []


def _direction(position_state: str) -> str:
    if position_state == "long":
        return "bullish"
    if position_state == "short":
        return "bearish"
    return "neutral"


def _strength(return_window_pct: float, *, deadband_pct: float) -> str:
    excess = abs(return_window_pct) - deadband_pct
    if excess >= 10:
        return "high"
    if excess >= 3:
        return "medium"
    return "low"


def _confidence(row_count: int, *, minimum_rows: int) -> str:
    if row_count >= max(minimum_rows * 2, 60):
        return "high"
    return "medium"


def _latest_regime(*, latest_position_state: str, return_window_pct: float, deadband_pct: float) -> str:
    if latest_position_state == "long":
        return "signed_positive_momentum"
    if latest_position_state == "short":
        return "signed_negative_momentum"
    if abs(return_window_pct) <= deadband_pct:
        return "signed_momentum_deadband"
    return "signed_momentum_flat"


def _assessment_summary(position_state: str, return_window_pct: float, deadband_pct: float) -> str:
    if position_state == "long":
        return "Signed time-series momentum is positive and maps to long research exposure."
    if position_state == "short":
        return "Signed time-series momentum is negative and maps to short research exposure."
    return (
        "Signed time-series momentum is inside the configured deadband; "
        f"return_window_pct is {_round(return_window_pct)}% and deadband_pct is {_round(deadband_pct)}%."
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


def _positive_number(value: Any, name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(float(value))
        or float(value) <= 0
    ):
        raise ValueError(f"{name} must be a positive number.")
    return float(value)


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


def _bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean.")
    return value


def _finite_number_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(float(value)):
        return None
    return float(value)


def _number_or_none(value: Any) -> float | None:
    number = _finite_number_or_none(value)
    return _round(number) if number is not None else None


def _round(value: float) -> float:
    return round(float(value), 6)
