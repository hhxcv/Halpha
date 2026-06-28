from __future__ import annotations

import math
from typing import Any

import pandas as pd

from halpha.market.market_data_views import MARKET_DATA_VIEWS_ARTIFACT
from .strategy_records import STRATEGY_VERSION, warning


SIGNAL_RECORD_VERSION = 1
POSITION_POLICY = "research_long_flat_target_exposure"
SIGNED_SIGNAL_RECORD_VERSION = 2
SIGNED_POSITION_POLICY = "research_signed_target_exposure"
SIGNED_POSITION_UNIT = "fractional_signed_exposure"


class SignalRecordError(ValueError):
    """Raised when strategy signal record inputs cannot produce valid records."""


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


def signed_strategy_signal_records(
    strategy: dict[str, Any],
    view: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    params: dict[str, Any],
    frame: pd.DataFrame,
    close: pd.Series,
    target_exposure_series: pd.Series,
    indicator_contexts: list[dict[str, Any]],
) -> dict[str, Any]:
    _require_matching_lengths(
        rows=rows,
        frame=frame,
        close=close,
        target_exposure_series=target_exposure_series,
        indicator_contexts=indicator_contexts,
    )
    exposures = [
        validate_single_leg_target_exposure(value, path=f"target_exposure[{position}]")
        for position, value in enumerate(target_exposure_series)
    ]
    records = []
    previous_state = "flat"
    for position, (_, item) in enumerate(frame.iterrows()):
        exposure = exposures[position]
        position_state = _signed_position_state(exposure)
        transition = _signed_transition(previous_state, position_state)
        records.append(
            {
                "schema_version": SIGNED_SIGNAL_RECORD_VERSION,
                "open_time": _string_or_none(item.get("open_time")),
                "signal_time": _string_or_none(item.get("open_time")),
                "close": _number_or_none(close.iloc[position]),
                "signal": {
                    "active": position_state != "flat",
                    "position_state": position_state,
                },
                "position": {
                    "target_exposure": exposure,
                    "unit": SIGNED_POSITION_UNIT,
                    "position_state": position_state,
                },
                "transition": transition,
                "entry": transition["entry"],
                "exit": transition["exit"],
                "long_entry": transition["long_entry"],
                "long_exit": transition["long_exit"],
                "short_entry": transition["short_entry"],
                "short_exit": transition["short_exit"],
                "indicator_context": _serializable_mapping(indicator_contexts[position]),
            }
        )
        previous_state = position_state
    return _base_record(
        strategy,
        view,
        rows,
        status="succeeded",
        params=params,
        records=records,
        warnings=[],
        signal_record_version=SIGNED_SIGNAL_RECORD_VERSION,
        position_policy=SIGNED_POSITION_POLICY,
    )


def insufficient_signed_strategy_signal_records(
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
        signal_record_version=SIGNED_SIGNAL_RECORD_VERSION,
        position_policy=SIGNED_POSITION_POLICY,
    )


def validate_single_leg_target_exposure(value: Any, *, path: str = "target_exposure") -> float:
    if isinstance(value, bool):
        raise SignalRecordError(f"{path} must be a finite number.")
    if hasattr(value, "item"):
        value = value.item()
        if isinstance(value, bool):
            raise SignalRecordError(f"{path} must be a finite number.")
    if not isinstance(value, (int, float)):
        raise SignalRecordError(f"{path} must be a finite number.")
    number = float(value)
    if not math.isfinite(number):
        raise SignalRecordError(f"{path} must be a finite number.")
    if number < -1.0 or number > 1.0:
        raise SignalRecordError(f"{path} must be between -1.0 and 1.0.")
    return round(number, 6)


def _base_record(
    strategy: dict[str, Any],
    view: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    status: str,
    params: dict[str, Any],
    records: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    signal_record_version: int = SIGNAL_RECORD_VERSION,
    position_policy: str = POSITION_POLICY,
) -> dict[str, Any]:
    name = str(strategy["name"])
    latest = view.get("latest_candle_time") or "missing"
    return {
        "strategy_signal_id": f"strategy_signal_records:{name}:{view.get('source')}:{view.get('symbol')}:{view.get('timeframe')}:{latest}",
        "status": status,
        "strategy_name": name,
        "strategy_version": STRATEGY_VERSION,
        "signal_record_version": signal_record_version,
        "source": view.get("source"),
        "symbol": view.get("symbol"),
        "timeframe": view.get("timeframe"),
        "input_view_id": view.get("view_id"),
        "input_window_start": view.get("input_window_start"),
        "input_window_end": view.get("input_window_end"),
        "latest_candle_time": view.get("latest_candle_time"),
        "params": params,
        "position_policy": position_policy,
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


def _require_matching_lengths(
    *,
    rows: list[dict[str, Any]],
    frame: pd.DataFrame,
    close: pd.Series,
    target_exposure_series: pd.Series,
    indicator_contexts: list[dict[str, Any]],
) -> None:
    expected = len(rows)
    if (
        len(frame) != expected
        or len(close) != expected
        or len(target_exposure_series) != expected
        or len(indicator_contexts) != expected
    ):
        raise SignalRecordError(
            "frame, close, target_exposure_series, rows, and indicator_contexts must have matching lengths."
        )


def _signed_position_state(target_exposure: float) -> str:
    if target_exposure > 0:
        return "long"
    if target_exposure < 0:
        return "short"
    return "flat"


def _signed_transition(previous_state: str, position_state: str) -> dict[str, bool]:
    long_entry = position_state == "long" and previous_state != "long"
    long_exit = previous_state == "long" and position_state != "long"
    short_entry = position_state == "short" and previous_state != "short"
    short_exit = previous_state == "short" and position_state != "short"
    return {
        "entry": long_entry or short_entry,
        "exit": long_exit or short_exit,
        "long_entry": long_entry,
        "long_exit": long_exit,
        "short_entry": short_entry,
        "short_exit": short_exit,
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
