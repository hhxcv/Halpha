from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

import pandas as pd

from ..strategy_records import (
    backtest_assumptions,
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
VECTORBT_PORTFOLIO_BACKEND = "vectorbt.Portfolio.from_signals"
BACKTEST_RESEARCH_WARNING = "Historical backtest diagnostic is research material, not a forecast."


def run(
    strategy: dict[str, Any],
    view: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    engine: dict[str, str],
    created_at: str,
) -> dict[str, Any]:
    params = _params(strategy.get("params"))
    minimum_rows = max(params["return_window"], params["volatility_window"]) + 1
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
    realized_volatility_pct = realized_volatility * 100
    exposure = _volatility_scaled_exposure(target_volatility, realized_volatility)
    signal_series = momentum_return > 0
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
        backtest_diagnostic=_backtest_diagnostic(
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


def _backtest_diagnostic(
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
