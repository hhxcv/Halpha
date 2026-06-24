from __future__ import annotations

from typing import Any

from .strategy_records import (
    backtest_diagnostic,
    data_quality,
    parameter_diagnostic,
    strategy_run_record,
    warning,
)


def input_is_insufficient(view: dict[str, Any], rows: list[dict[str, Any]], *, minimum_rows: int) -> bool:
    return bool(view.get("insufficient_data")) or len(rows) < minimum_rows


def strategy_transition_counts(signal_series: Any) -> dict[str, Any]:
    clean = signal_series.fillna(False).astype(bool)
    previous = clean.shift(1, fill_value=False)
    return {
        "entry_count": int(((~previous) & clean).sum()),
        "exit_count": int((previous & (~clean)).sum()),
        "latest_signal": bool(signal_series.iloc[-1]),
        "previous_signal": bool(signal_series.iloc[-2]),
    }


def insufficient_strategy_run(
    strategy: dict[str, Any],
    view: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    strategy_name: str,
    params: dict[str, Any],
    engine: dict[str, str],
    created_at: str,
    minimum_rows: int,
    uncertainty: str,
) -> dict[str, Any]:
    if len(rows) < minimum_rows:
        item = warning(
            "insufficient_ohlcv_rows",
            (
                f"{view.get('source')} {view.get('symbol')} {view.get('timeframe')} has "
                f"{len(rows)} OHLCV rows; {strategy_name} requires at least {minimum_rows} rows."
            ),
            source="data_quality",
        )
    else:
        item = warning(
            "degraded_ohlcv_quality",
            _view_quality_message(view),
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
            "uncertainty": [uncertainty],
        },
        warnings=[item],
        error=None,
    )


def _view_quality_message(view: dict[str, Any]) -> str:
    warnings = view.get("warnings")
    if isinstance(warnings, list):
        for item in warnings:
            if isinstance(item, str) and item:
                return item
    return (
        f"{view.get('source')} {view.get('symbol')} {view.get('timeframe')} "
        "OHLCV input view has degraded continuity or freshness."
    )
