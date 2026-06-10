from __future__ import annotations

import math
from typing import Any

import pandas as pd

from ..market_data_views import MARKET_DATA_VIEWS_ARTIFACT
from .strategy_records import STRATEGY_VERSION, warning


SIGNAL_RECORD_VERSION = 1
POSITION_POLICY = "research_long_flat_target_exposure"


def strategy_signal_records(
    strategy: dict[str, Any],
    view: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    params: dict[str, Any],
    frame: pd.DataFrame,
    close: pd.Series,
    signal_series: pd.Series,
    indicator_contexts: list[dict[str, Any]],
) -> dict[str, Any]:
    active = signal_series.fillna(False).astype(bool)
    previous = active.shift(1, fill_value=False)
    entries = active & ~previous
    exits = ~active & previous
    records = []
    for position, (_, item) in enumerate(frame.iterrows()):
        is_active = bool(active.iloc[position])
        records.append(
            {
                "open_time": _string_or_none(item.get("open_time")),
                "close": _number_or_none(close.iloc[position]),
                "signal": {"active": is_active},
                "position": {
                    "target_exposure": 1.0 if is_active else 0.0,
                    "unit": "fractional_long_exposure",
                },
                "entry": bool(entries.iloc[position]),
                "exit": bool(exits.iloc[position]),
                "indicator_context": _serializable_mapping(indicator_contexts[position]),
            }
        )
    return _base_record(
        strategy,
        view,
        rows,
        status="succeeded",
        params=params,
        records=records,
        warnings=[],
    )


def insufficient_strategy_signal_records(
    strategy: dict[str, Any],
    view: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    params: dict[str, Any],
    minimum_rows: int,
) -> dict[str, Any]:
    item = warning(
        "insufficient_ohlcv_rows",
        (
            f"{view.get('source')} {view.get('symbol')} {view.get('timeframe')} has "
            f"{len(rows)} OHLCV rows; {strategy.get('name')} requires at least {minimum_rows} rows."
        ),
        source="data_quality",
    )
    return _base_record(
        strategy,
        view,
        rows,
        status="insufficient_data",
        params=params,
        records=[],
        warnings=[item],
    )


def _base_record(
    strategy: dict[str, Any],
    view: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    status: str,
    params: dict[str, Any],
    records: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> dict[str, Any]:
    name = str(strategy["name"])
    latest = view.get("latest_candle_time") or "missing"
    return {
        "strategy_signal_id": f"strategy_signal_records:{name}:{view.get('source')}:{view.get('symbol')}:{view.get('timeframe')}:{latest}",
        "status": status,
        "strategy_name": name,
        "strategy_version": STRATEGY_VERSION,
        "signal_record_version": SIGNAL_RECORD_VERSION,
        "source": view.get("source"),
        "symbol": view.get("symbol"),
        "timeframe": view.get("timeframe"),
        "input_view_id": view.get("view_id"),
        "input_window_start": view.get("input_window_start"),
        "input_window_end": view.get("input_window_end"),
        "latest_candle_time": view.get("latest_candle_time"),
        "params": params,
        "position_policy": POSITION_POLICY,
        "price_column": "close",
        "row_count": len(rows),
        "records": records,
        "latest_record": records[-1] if records else None,
        "entry_count": sum(1 for item in records if item["entry"]),
        "exit_count": sum(1 for item in records if item["exit"]),
        "active_count": sum(1 for item in records if item["signal"]["active"]),
        "warnings": warnings,
        "source_artifacts": [MARKET_DATA_VIEWS_ARTIFACT],
    }


def _serializable_mapping(values: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _serializable_value(value) for key, value in values.items()}


def _serializable_value(value: Any) -> Any:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return _number_or_none(value)
    if hasattr(value, "item"):
        return _serializable_value(value.item())
    if isinstance(value, list):
        return [_serializable_value(item) for item in value]
    if isinstance(value, dict):
        return _serializable_mapping(value)
    return str(value)


def _number_or_none(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return round(number, 6)


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
