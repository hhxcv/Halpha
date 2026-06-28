from __future__ import annotations

import json
import math
from typing import Any

import pandas as pd
import pytest

from halpha.quant.signal_records import (
    SignalRecordError,
    insufficient_signed_strategy_signal_records,
    signed_strategy_signal_records,
    strategy_signal_records,
    validate_single_leg_target_exposure,
)


def test_long_flat_signal_records_keep_v1_shape() -> None:
    rows = _rows([100, 101, 102])
    frame = pd.DataFrame(rows)

    result = strategy_signal_records(
        _strategy(),
        _view(rows),
        rows,
        params={"window": 2},
        frame=frame,
        close=frame["close"],
        signal_series=pd.Series([False, True, False]),
        indicator_contexts=[{"value": index} for index in range(3)],
    )

    assert result["signal_record_version"] == 1
    assert result["position_policy"] == "research_long_flat_target_exposure"
    assert [item["signal"] for item in result["records"]] == [
        {"active": False},
        {"active": True},
        {"active": False},
    ]
    assert [item["position"] for item in result["records"]] == [
        {"target_exposure": 0.0, "unit": "fractional_long_exposure"},
        {"target_exposure": 1.0, "unit": "fractional_long_exposure"},
        {"target_exposure": 0.0, "unit": "fractional_long_exposure"},
    ]
    assert [item["entry"] for item in result["records"]] == [False, True, False]
    assert [item["exit"] for item in result["records"]] == [False, False, True]
    assert "position_state" not in result["records"][1]["position"]
    json.dumps(result)


def test_signed_signal_records_cover_long_transitions() -> None:
    result = _signed_records([0.0, 1.0, 0.75, 0.0])

    assert result["signal_record_version"] == 2
    assert result["position_policy"] == "research_signed_target_exposure"
    assert [item["position"]["position_state"] for item in result["records"]] == [
        "flat",
        "long",
        "long",
        "flat",
    ]
    assert [item["position"]["target_exposure"] for item in result["records"]] == [
        0.0,
        1.0,
        0.75,
        0.0,
    ]
    assert [item["long_entry"] for item in result["records"]] == [False, True, False, False]
    assert [item["long_exit"] for item in result["records"]] == [False, False, False, True]
    assert [item["entry"] for item in result["records"]] == [False, True, False, False]
    assert [item["exit"] for item in result["records"]] == [False, False, False, True]
    assert result["entry_count"] == 1
    assert result["exit_count"] == 1
    assert result["active_count"] == 2
    json.dumps(result)


def test_signed_signal_records_cover_short_transitions() -> None:
    result = _signed_records([0.0, -1.0, -0.5, 0.0])

    assert [item["signal"]["position_state"] for item in result["records"]] == [
        "flat",
        "short",
        "short",
        "flat",
    ]
    assert [item["short_entry"] for item in result["records"]] == [False, True, False, False]
    assert [item["short_exit"] for item in result["records"]] == [False, False, False, True]
    assert [item["entry"] for item in result["records"]] == [False, True, False, False]
    assert [item["exit"] for item in result["records"]] == [False, False, False, True]
    assert result["active_count"] == 2
    json.dumps(result)


def test_signed_signal_records_cover_direct_long_to_short() -> None:
    result = _signed_records([1.0, -1.0])
    second = result["records"][1]

    assert second["position"]["position_state"] == "short"
    assert second["entry"] is True
    assert second["exit"] is True
    assert second["long_exit"] is True
    assert second["short_entry"] is True
    assert second["long_entry"] is False
    assert second["short_exit"] is False


def test_signed_signal_records_cover_flat_state() -> None:
    result = _signed_records([0.0, 0.0, 0.0])

    assert result["entry_count"] == 0
    assert result["exit_count"] == 0
    assert result["active_count"] == 0
    assert all(item["position"]["position_state"] == "flat" for item in result["records"])
    assert result["latest_record"]["signal"]["active"] is False


@pytest.mark.parametrize("value", [1.1, -1.1, math.inf, -math.inf, math.nan, True, "1"])
def test_signed_target_exposure_validation_rejects_invalid_values(value: Any) -> None:
    with pytest.raises(SignalRecordError):
        validate_single_leg_target_exposure(value)


def test_signed_signal_records_reject_invalid_series_values() -> None:
    with pytest.raises(SignalRecordError, match=r"target_exposure\[1\] must be between -1.0 and 1.0"):
        _signed_records([0.0, 1.2])


def test_signed_signal_records_reject_mismatched_lengths() -> None:
    rows = _rows([100, 101])
    frame = pd.DataFrame(rows)

    with pytest.raises(SignalRecordError, match="must have matching lengths"):
        signed_strategy_signal_records(
            _strategy(),
            _view(rows),
            rows,
            params={},
            frame=frame,
            close=frame["close"],
            target_exposure_series=pd.Series([0.0]),
            indicator_contexts=[{} for _ in rows],
        )


def test_insufficient_signed_signal_records_use_signed_contract() -> None:
    rows = _rows([100, 101])

    result = insufficient_signed_strategy_signal_records(
        _strategy(),
        _view(rows),
        rows,
        params={"window": 3},
        minimum_rows=3,
    )

    assert result["status"] == "insufficient_data"
    assert result["signal_record_version"] == 2
    assert result["position_policy"] == "research_signed_target_exposure"
    assert result["records"] == []
    assert result["entry_count"] == 0
    assert result["exit_count"] == 0
    assert result["active_count"] == 0
    assert result["warnings"][0]["code"] == "insufficient_ohlcv_rows"
    json.dumps(result)


def _signed_records(exposures: list[float]) -> dict[str, Any]:
    rows = _rows([100 + index for index in range(len(exposures))])
    frame = pd.DataFrame(rows)
    return signed_strategy_signal_records(
        _strategy(),
        _view(rows),
        rows,
        params={"mode": "signed"},
        frame=frame,
        close=frame["close"],
        target_exposure_series=pd.Series(exposures),
        indicator_contexts=[{"index": index} for index in range(len(rows))],
    )


def _strategy() -> dict[str, Any]:
    return {"name": "signed_test"}


def _view(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "source": "synthetic",
        "symbol": "TESTUSDT",
        "timeframe": "1d",
        "view_id": "ohlcv_view:synthetic:TESTUSDT:1d",
        "input_window_start": rows[0]["open_time"] if rows else None,
        "input_window_end": rows[-1]["open_time"] if rows else None,
        "latest_candle_time": rows[-1]["open_time"] if rows else None,
    }


def _rows(closes: list[float]) -> list[dict[str, Any]]:
    return [
        {
            "open_time": f"2026-06-{index + 1:02d}T00:00:00Z",
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1.0,
        }
        for index, close in enumerate(closes)
    ]
