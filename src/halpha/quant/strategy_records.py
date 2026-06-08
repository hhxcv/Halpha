from __future__ import annotations

import math
from typing import Any

from ..market_data_views import MARKET_DATA_VIEWS_ARTIFACT


STRATEGY_VERSION = 1
DEFAULT_BACKTEST_INITIAL_CASH = 10000.0
SUPPORTED_BACKTEST_MODES = {"long_flat", "long_only"}


def strategy_run_record(
    *,
    strategy: dict[str, Any],
    view: dict[str, Any],
    engine: dict[str, str],
    created_at: str,
    status: str,
    params: dict[str, Any],
    data_quality: dict[str, Any],
    indicators: dict[str, Any],
    signals: dict[str, Any],
    backtest_diagnostic: dict[str, Any],
    parameter_diagnostic: dict[str, Any],
    assessment: dict[str, Any],
    warnings: list[dict[str, Any]],
    error: dict[str, Any] | None,
) -> dict[str, Any]:
    name = str(strategy["name"])
    latest = view.get("latest_candle_time") or "missing"
    return {
        "strategy_run_id": f"quant_strategy_run:{name}:{view.get('source')}:{view.get('symbol')}:{view.get('timeframe')}:{latest}",
        "status": status,
        "strategy_name": name,
        "strategy_version": STRATEGY_VERSION,
        "engine": engine,
        "source": view.get("source"),
        "symbol": view.get("symbol"),
        "timeframe": view.get("timeframe"),
        "input_view_id": view.get("view_id"),
        "input_window_start": view.get("input_window_start"),
        "input_window_end": view.get("input_window_end"),
        "latest_candle_time": view.get("latest_candle_time"),
        "params": params,
        "data_quality": data_quality,
        "indicators": indicators,
        "signals": signals,
        "backtest_diagnostic": backtest_diagnostic,
        "parameter_diagnostic": parameter_diagnostic,
        "assessment": assessment,
        "warnings": warnings,
        "error": error,
        "source_artifacts": [MARKET_DATA_VIEWS_ARTIFACT],
        "created_at": created_at,
    }


def failed_strategy_run(
    strategy: dict[str, Any],
    view: dict[str, Any],
    *,
    engine: dict[str, str],
    created_at: str,
    params: dict[str, Any],
    error_type: str,
    message: str,
    stage: str,
) -> dict[str, Any]:
    return strategy_run_record(
        strategy=strategy,
        view=view,
        engine=engine,
        created_at=created_at,
        status="failed",
        params=params,
        data_quality=data_quality(view, [], minimum_rows=0, sufficient=False),
        indicators={},
        signals={},
        backtest_diagnostic=backtest_diagnostic(strategy, view, [], status="skipped"),
        parameter_diagnostic=parameter_diagnostic(),
        assessment={
            "direction": "unknown",
            "strength": "unknown",
            "confidence": "low",
            "summary": "Strategy run failed before assessment.",
            "evidence": [],
            "uncertainty": ["No strategy conclusion is available because execution failed."],
        },
        warnings=[],
        error={
            "error_type": error_type,
            "message": message,
            "stage": stage,
        },
    )


def data_quality(
    view: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    minimum_rows: int,
    sufficient: bool,
    warnings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "row_count": len(rows),
        "requested_lookback": view.get("requested_lookback"),
        "minimum_required_rows": minimum_rows,
        "sufficient_data": sufficient,
        "missing_row_policy": "do_not_fabricate",
        "warnings": warnings or [],
    }


def backtest_diagnostic(
    strategy: dict[str, Any],
    view: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    status: str,
    metrics: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    backtest = strategy.get("backtest") if isinstance(strategy.get("backtest"), dict) else {}
    enabled = bool(backtest.get("enabled", False))
    if not enabled:
        return {
            "enabled": False,
            "status": "disabled",
        }
    return {
        "enabled": True,
        "status": status,
        "assumptions": backtest_assumptions(strategy),
        "window": {
            "start": view.get("input_window_start"),
            "end": view.get("input_window_end"),
            "rows": len(rows),
        },
        "metrics": metrics or {},
        "warnings": warnings
        or [
            "Backtest diagnostic skipped before portfolio-style metric calculation.",
            "Historical backtest diagnostic is research material, not a forecast.",
        ],
    }


def backtest_assumptions(strategy: dict[str, Any]) -> dict[str, Any]:
    backtest = strategy.get("backtest") if isinstance(strategy.get("backtest"), dict) else {}
    mode = backtest.get("mode", "long_flat")
    if mode not in SUPPORTED_BACKTEST_MODES:
        mode = "long_flat"
    return {
        "initial_cash": _positive_number_or_default(
            backtest.get("initial_cash"),
            DEFAULT_BACKTEST_INITIAL_CASH,
        ),
        "fees_bps": _non_negative_number_or_default(backtest.get("fees_bps"), 0.0),
        "slippage_bps": _non_negative_number_or_default(backtest.get("slippage_bps"), 0.0),
        "mode": mode,
        "direction": "long_only",
        "price_source": "close",
        "execution_timing": "research_close_to_close",
    }


def parameter_diagnostic() -> dict[str, Any]:
    return {
        "enabled": False,
        "status": "disabled",
    }


def warning(code: str, message: str, *, source: str) -> dict[str, Any]:
    return {
        "severity": "warning",
        "code": code,
        "message": message,
        "source": source,
    }


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
