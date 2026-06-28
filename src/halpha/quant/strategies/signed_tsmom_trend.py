from __future__ import annotations

import math
from typing import Any

import pandas as pd

from ..signal_records import insufficient_signed_strategy_signal_records, signed_strategy_signal_records
from ..strategy_evaluation import evaluate_single_window_backtest
from ..strategy_execution import input_is_insufficient, insufficient_strategy_run
from ..strategy_records import (
    DEFAULT_BACKTEST_INITIAL_CASH,
    SIGNED_EXECUTION_MODEL,
    data_quality,
    parameter_diagnostic,
    strategy_run_record,
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
    transition_counts = _signed_transition_counts(state["signal_records"]["records"])
    warnings = []

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
            **transition_counts,
        },
        backtest_diagnostic=_signed_backtest_diagnostic(
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
    return {
        "return_window": return_window,
        "deadband_pct": deadband_pct,
    }


def _minimum_rows(params: dict[str, Any]) -> int:
    return int(params["return_window"]) + 1


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
    target_exposure_series = _target_exposure_series(momentum_return, deadband_pct=deadband_pct)
    indicator_contexts = _signal_indicator_contexts(
        momentum_return,
        target_exposure_series,
        deadband_pct=deadband_pct,
    )
    return {
        "frame": frame,
        "close": close,
        "latest_close": float(close.iloc[-1]),
        "baseline_close": float(close.iloc[-return_window - 1]),
        "return_window_pct": float(momentum_return.iloc[-1]) * 100,
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
) -> list[dict[str, Any]]:
    contexts = []
    for momentum_value, exposure in zip(momentum_return, target_exposure_series, strict=True):
        return_window_pct = _number_or_none(float(momentum_value) * 100)
        contexts.append(
            {
                "calculation_backend": CALCULATION_BACKEND,
                "return_window_pct": return_window_pct,
                "deadband_pct": deadband_pct,
                "target_exposure": float(exposure),
                "position_state": _position_state(float(exposure)),
            }
        )
    return contexts


def _signed_backtest_diagnostic(
    strategy: dict[str, Any],
    view: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    signal_records: dict[str, Any],
) -> dict[str, Any]:
    backtest = strategy.get("backtest") if isinstance(strategy.get("backtest"), dict) else {}
    if backtest.get("enabled") is not True:
        return {
            "enabled": False,
            "status": "disabled",
        }
    assumptions = _signed_backtest_assumptions(backtest)
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
        execution_model=SIGNED_EXECUTION_MODEL,
    )
    if evaluation.get("status") != "succeeded":
        return {
            "enabled": True,
            "status": str(evaluation.get("status") or "failed"),
            "assumptions": assumptions,
            "window": _window(view, rows),
            "metrics": {},
            "warnings": [
                "Signed backtest diagnostic uses the Halpha signed next-bar close-to-close evaluator.",
                *_warning_messages(evaluation.get("warnings")),
                *_error_messages(evaluation.get("errors")),
            ],
        }
    return {
        "enabled": True,
        "status": "succeeded",
        "assumptions": assumptions,
        "window": _window(view, rows),
        "metrics": _bounded_backtest_metrics(evaluation, initial_cash=assumptions["initial_cash"]),
        "warnings": [
            "Signed backtest diagnostic is historical research material, not a forecast.",
            "Signed exposure is not account leverage, margin, borrowing, or execution advice.",
        ],
    }


def _signed_backtest_assumptions(backtest: dict[str, Any]) -> dict[str, Any]:
    return {
        "initial_cash": _positive_number_or_default(
            backtest.get("initial_cash"),
            DEFAULT_BACKTEST_INITIAL_CASH,
        ),
        "fees_bps": _non_negative_number_or_default(backtest.get("fees_bps"), 0.0),
        "slippage_bps": _non_negative_number_or_default(backtest.get("slippage_bps"), 0.0),
        "mode": "signed_long_short",
        "direction": "long_short",
        **SIGNED_EXECUTION_MODEL,
    }


def _bounded_backtest_metrics(evaluation: dict[str, Any], *, initial_cash: float) -> dict[str, Any]:
    strategy_metrics = evaluation.get("strategy_metrics") if isinstance(evaluation.get("strategy_metrics"), dict) else {}
    trade_summary = evaluation.get("trade_summary") if isinstance(evaluation.get("trade_summary"), dict) else {}
    final_multiplier = float(strategy_metrics.get("final_equity") or 0.0)
    return {
        "calculation_backend": "halpha.strategy_evaluation.evaluate_single_window_backtest",
        "execution_model_id": SIGNED_EXECUTION_MODEL["execution_model_id"],
        "return_metric_basis": "net_after_costs",
        "gross_return_pct": strategy_metrics.get("gross_return_pct"),
        "net_return_pct": strategy_metrics.get("net_return_pct"),
        "total_cost_pct": strategy_metrics.get("total_cost_pct"),
        "cost_drag_pct": strategy_metrics.get("cost_drag_pct"),
        "max_drawdown_pct": strategy_metrics.get("max_drawdown_pct"),
        "trade_count": trade_summary.get("trade_count"),
        "long_trade_count": trade_summary.get("long_trade_count"),
        "short_trade_count": trade_summary.get("short_trade_count"),
        "side_flip_count": trade_summary.get("side_flip_count"),
        "turnover": trade_summary.get("turnover"),
        "long_exposure_pct": trade_summary.get("long_exposure_pct"),
        "short_exposure_pct": trade_summary.get("short_exposure_pct"),
        "average_abs_exposure_pct": trade_summary.get("average_abs_exposure_pct"),
        "final_equity": _round(initial_cash * final_multiplier),
        "final_equity_multiplier": strategy_metrics.get("final_equity"),
    }


def _window(view: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "start": view.get("input_window_start"),
        "end": view.get("input_window_end"),
        "rows": len(rows),
    }


def _signed_transition_counts(records: list[dict[str, Any]]) -> dict[str, Any]:
    long_entry_count = sum(1 for item in records if item.get("long_entry") is True)
    long_exit_count = sum(1 for item in records if item.get("long_exit") is True)
    short_entry_count = sum(1 for item in records if item.get("short_entry") is True)
    short_exit_count = sum(1 for item in records if item.get("short_exit") is True)
    side_flip_count = 0
    previous = "flat"
    for item in records:
        position = item.get("position") if isinstance(item.get("position"), dict) else {}
        state = str(position.get("position_state") or "flat")
        if {previous, state} == {"long", "short"}:
            side_flip_count += 1
        previous = state
    return {
        "entry_count": long_entry_count + short_entry_count,
        "exit_count": long_exit_count + short_exit_count,
        "long_entry_count": long_entry_count,
        "long_exit_count": long_exit_count,
        "short_entry_count": short_entry_count,
        "short_exit_count": short_exit_count,
        "side_flip_count": side_flip_count,
        "active_count": sum(1 for item in records if item.get("signal", {}).get("active") is True),
    }


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


def _positive_number_or_default(value: Any, default: float) -> float:
    number = _finite_number_or_none(value)
    if number is None or number <= 0:
        return default
    return number


def _non_negative_number_or_default(value: Any, default: float) -> float:
    number = _finite_number_or_none(value)
    if number is None or number < 0:
        return default
    return number


def _finite_number_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(float(value)):
        return None
    return float(value)


def _number_or_none(value: Any) -> float | None:
    number = _finite_number_or_none(value)
    return _round(number) if number is not None else None


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
