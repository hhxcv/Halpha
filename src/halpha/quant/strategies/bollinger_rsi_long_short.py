from __future__ import annotations

import math
from typing import Any

import pandas as pd

from ..signal_records import insufficient_signed_strategy_signal_records, signed_strategy_signal_records
from ..signed_strategy_support import signed_backtest_diagnostic, signed_transition_counts
from ..strategy_execution import input_is_insufficient, insufficient_strategy_run
from ..strategy_records import data_quality, parameter_diagnostic, strategy_run_record, warning
from ..strategy_specs import require_strategy_spec


NAME = "bollinger_rsi_long_short"
SPEC = require_strategy_spec(NAME)
DEFAULT_PARAMS = dict(SPEC.default_params)
CALCULATION_BACKEND = "pandas.rolling_bollinger_rsi"


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
            uncertainty="Insufficient data prevents signed Bollinger RSI reversion assessment.",
        )

    state = _signal_state(strategy, view, rows, params=params)
    latest_record = state["signal_records"]["latest_record"]
    latest_exposure = float(latest_record["position"]["target_exposure"])
    latest_position_state = str(latest_record["position"]["position_state"])
    transition_counts = signed_transition_counts(state["signal_records"]["records"])
    warnings = _strategy_warnings(state)

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
            "bollinger_middle": _round(state["latest_middle"]),
            "bollinger_upper": _round(state["latest_upper"]),
            "bollinger_lower": _round(state["latest_lower"]),
            "bollinger_band_width_pct": _round(state["band_width_pct"]),
            "bollinger_percent_b": _round(state["percent_b"]),
            "rsi": _round(state["latest_rsi"]),
            "rsi_oversold_threshold": _round(params["rsi_oversold"]),
            "rsi_overbought_threshold": _round(params["rsi_overbought"]),
            "trend_window_pct": _round(state["latest_trend_window_pct"]),
            "trend_filter_pct": _round(params["trend_filter_pct"]),
            "row_count": len(rows),
        },
        signals={
            "calculation_backend": CALCULATION_BACKEND,
            "latest_regime": _latest_regime(
                latest_position_state=latest_position_state,
                latest_oversold=state["latest_oversold"],
                latest_overbought=state["latest_overbought"],
                suppression_reason=state["suppression_reason"],
            ),
            "latest_position_state": latest_position_state,
            "latest_target_exposure": _round(latest_exposure),
            "latest_oversold": state["latest_oversold"],
            "latest_overbought": state["latest_overbought"],
            "trend_filter_active": state["trend_filter_active"],
            "strong_trend_direction": state["strong_trend_direction"],
            "suppression_reason": state["suppression_reason"],
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
            "direction": _direction(latest_position_state, suppression_reason=state["suppression_reason"]),
            "strength": _strength(
                latest_position_state=latest_position_state,
                percent_b=state["percent_b"],
                rsi=state["latest_rsi"],
            ),
            "confidence": _confidence(len(rows), minimum_rows=minimum_rows, warnings=warnings),
            "summary": _assessment_summary(
                latest_position_state,
                suppression_reason=state["suppression_reason"],
            ),
            "evidence": [
                (
                    f"latest_close is {_round(state['latest_close'])} versus Bollinger lower "
                    f"{_round(state['latest_lower'])}, middle {_round(state['latest_middle'])}, "
                    f"and upper {_round(state['latest_upper'])}."
                ),
                (
                    f"rsi is {_round(state['latest_rsi'])} against oversold threshold "
                    f"{_round(params['rsi_oversold'])} and overbought threshold "
                    f"{_round(params['rsi_overbought'])}."
                ),
                (
                    f"trend_window_pct is {_round(state['latest_trend_window_pct'])}% against "
                    f"trend_filter_pct {_round(params['trend_filter_pct'])}%."
                ),
            ],
            "uncertainty": [
                "Strategy uses OHLCV close prices only and excludes text events.",
                "Signed exposure is research exposure, not borrowing, margin, or account state.",
                "Mean-reversion conditions can persist or fail when a strong trend continues.",
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


def _minimum_rows(params: dict[str, Any]) -> int:
    return max(
        int(params["bollinger_window"]),
        int(params["rsi_window"]) + 1,
        int(params["trend_window"]) + 1,
    )


def _signal_state(
    strategy: dict[str, Any],
    view: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    params: dict[str, Any],
) -> dict[str, Any]:
    frame = _frame(rows)
    close = frame["close"]
    middle, upper, lower = _bollinger(close, params)
    rsi = _rsi(close, int(params["rsi_window"]))
    trend_return = close.pct_change(int(params["trend_window"])) * 100
    target_exposure_series, state_contexts = _target_exposure_series(
        close,
        middle,
        upper,
        lower,
        rsi,
        trend_return,
        params,
    )
    indicator_contexts = _signal_indicator_contexts(
        middle,
        upper,
        lower,
        rsi,
        trend_return,
        target_exposure_series,
        state_contexts,
    )
    latest = state_contexts[-1]
    latest_close = float(close.iloc[-1])
    latest_lower = float(lower.iloc[-1])
    latest_upper = float(upper.iloc[-1])
    return {
        "frame": frame,
        "close": close,
        "latest_close": latest_close,
        "latest_middle": float(middle.iloc[-1]),
        "latest_upper": latest_upper,
        "latest_lower": latest_lower,
        "latest_rsi": float(rsi.iloc[-1]),
        "latest_trend_window_pct": float(trend_return.iloc[-1]),
        "band_width_pct": _pct(latest_upper - latest_lower, latest_close),
        "percent_b": _percent_b(latest_close, latest_lower, latest_upper),
        "latest_oversold": bool(latest["latest_oversold"]),
        "latest_overbought": bool(latest["latest_overbought"]),
        "trend_filter_active": bool(latest["trend_filter_active"]),
        "strong_trend_direction": str(latest["strong_trend_direction"]),
        "suppression_reason": latest["suppression_reason"],
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


def _bollinger(close: pd.Series, params: dict[str, Any]) -> tuple[pd.Series, pd.Series, pd.Series]:
    middle = close.rolling(int(params["bollinger_window"])).mean()
    rolling_std = close.rolling(int(params["bollinger_window"])).std(ddof=0)
    upper = middle + (rolling_std * float(params["band_std"]))
    lower = middle - (rolling_std * float(params["band_std"]))
    return middle, upper, lower


def _rsi(close: pd.Series, window: int) -> pd.Series:
    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    average_gain = gains.rolling(window).mean()
    average_loss = losses.rolling(window).mean()
    rs = average_gain.divide(average_loss.where(average_loss != 0))
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.mask((average_loss == 0) & (average_gain > 0), 100.0)
    rsi = rsi.mask((average_gain == 0) & (average_loss > 0), 0.0)
    rsi = rsi.mask((average_gain == 0) & (average_loss == 0), 50.0)
    return rsi


def _target_exposure_series(
    close: pd.Series,
    middle: pd.Series,
    upper: pd.Series,
    lower: pd.Series,
    rsi: pd.Series,
    trend_return: pd.Series,
    params: dict[str, Any],
) -> tuple[pd.Series, list[dict[str, Any]]]:
    exposures = []
    contexts = []
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
            exposures.append(0.0)
            contexts.append(_state_context(False, False, False, "none", None))
            continue
        oversold = float(latest_close) <= float(low) and float(latest_rsi) <= params["rsi_oversold"]
        overbought = float(latest_close) >= float(high) and float(latest_rsi) >= params["rsi_overbought"]
        strong_downtrend = float(trend_pct) <= -params["trend_filter_pct"]
        strong_uptrend = float(trend_pct) >= params["trend_filter_pct"]
        suppression_reason = _suppression_reason(
            oversold=oversold,
            overbought=overbought,
            strong_downtrend=strong_downtrend,
            strong_uptrend=strong_uptrend,
        )
        if oversold and suppression_reason is None:
            exposure = 1.0
        elif overbought and suppression_reason is None:
            exposure = -1.0
        else:
            exposure = 0.0
        exposures.append(exposure)
        contexts.append(
            _state_context(
                oversold,
                overbought,
                suppression_reason is not None,
                _strong_trend_direction(strong_downtrend, strong_uptrend),
                suppression_reason,
            )
        )
    return pd.Series(exposures, index=close.index, dtype=float), contexts


def _signal_indicator_contexts(
    middle: pd.Series,
    upper: pd.Series,
    lower: pd.Series,
    rsi: pd.Series,
    trend_return: pd.Series,
    target_exposure_series: pd.Series,
    state_contexts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    contexts = []
    for mid, high, low, latest_rsi, trend_pct, exposure, state_context in zip(
        middle,
        upper,
        lower,
        rsi,
        trend_return,
        target_exposure_series,
        state_contexts,
        strict=True,
    ):
        exposure_value = float(exposure)
        contexts.append(
            {
                "calculation_backend": CALCULATION_BACKEND,
                "bollinger_middle": _number_or_none(mid),
                "bollinger_upper": _number_or_none(high),
                "bollinger_lower": _number_or_none(low),
                "rsi": _number_or_none(latest_rsi),
                "trend_window_pct": _number_or_none(trend_pct),
                "target_exposure": exposure_value,
                "position_state": _position_state(exposure_value),
                **state_context,
            }
        )
    return contexts


def _state_context(
    oversold: bool,
    overbought: bool,
    trend_filter_active: bool,
    strong_trend_direction: str,
    suppression_reason: str | None,
) -> dict[str, Any]:
    return {
        "latest_oversold": oversold,
        "latest_overbought": overbought,
        "trend_filter_active": trend_filter_active,
        "strong_trend_direction": strong_trend_direction,
        "suppression_reason": suppression_reason,
    }


def _strategy_warnings(state: dict[str, Any]) -> list[dict[str, Any]]:
    if state["suppression_reason"] == "oversold_strong_downtrend":
        return [
            warning(
                "strong_downtrend_reversion_filter",
                "Oversold long reversion setup is suppressed inside a strong downtrend.",
                source="strategy",
            )
        ]
    if state["suppression_reason"] == "overbought_strong_uptrend":
        return [
            warning(
                "strong_uptrend_reversion_filter",
                "Overbought short reversion setup is suppressed inside a strong uptrend.",
                source="strategy",
            )
        ]
    return []


def _suppression_reason(
    *,
    oversold: bool,
    overbought: bool,
    strong_downtrend: bool,
    strong_uptrend: bool,
) -> str | None:
    if oversold and strong_downtrend:
        return "oversold_strong_downtrend"
    if overbought and strong_uptrend:
        return "overbought_strong_uptrend"
    return None


def _direction(position_state: str, *, suppression_reason: str | None) -> str:
    if suppression_reason:
        return "mixed"
    if position_state == "long":
        return "bullish"
    if position_state == "short":
        return "bearish"
    return "neutral"


def _strength(*, latest_position_state: str, percent_b: float, rsi: float) -> str:
    if latest_position_state == "long":
        if percent_b <= -0.25 or rsi <= 20:
            return "high"
        return "medium"
    if latest_position_state == "short":
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
    latest_position_state: str,
    latest_oversold: bool,
    latest_overbought: bool,
    suppression_reason: str | None,
) -> str:
    if suppression_reason:
        return suppression_reason
    if latest_position_state == "long":
        return "signed_oversold_reversion_long"
    if latest_position_state == "short":
        return "signed_overbought_reversion_short"
    if latest_oversold:
        return "oversold_reversion_flat"
    if latest_overbought:
        return "overbought_reversion_flat"
    return "neutral_range"


def _assessment_summary(position_state: str, *, suppression_reason: str | None) -> str:
    if suppression_reason == "oversold_strong_downtrend":
        return "Oversold long reversion setup is suppressed by the configured strong-downtrend filter."
    if suppression_reason == "overbought_strong_uptrend":
        return "Overbought short reversion setup is suppressed by the configured strong-uptrend filter."
    if position_state == "long":
        return "Signed Bollinger RSI reversion maps oversold context to long research exposure."
    if position_state == "short":
        return "Signed Bollinger RSI reversion maps overbought context to short research exposure."
    return "No active signed Bollinger RSI reversion setup is present."


def _position_state(exposure: float) -> str:
    if exposure > 0:
        return "long"
    if exposure < 0:
        return "short"
    return "flat"


def _strong_trend_direction(strong_downtrend: bool, strong_uptrend: bool) -> str:
    if strong_downtrend:
        return "down"
    if strong_uptrend:
        return "up"
    return "none"


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


def _rsi_threshold(value: Any, name: str) -> float:
    number = _positive_number(value, name)
    if number >= 100:
        raise ValueError(f"{name} must be lower than 100.")
    return number


def _pct(value: float, base: float) -> float:
    if base == 0:
        return 0.0
    return (value / base) * 100


def _percent_b(latest_close: float, lower: float, upper: float) -> float:
    width = upper - lower
    if width <= 0 or math.isnan(width):
        return 0.5
    return (latest_close - lower) / width


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
