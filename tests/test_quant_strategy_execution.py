from __future__ import annotations

from typing import Any

import pandas as pd

from halpha.quant.strategy_execution import (
    input_is_insufficient,
    insufficient_strategy_run,
    strategy_transition_counts,
)


def test_strategy_execution_transition_counts() -> None:
    counts = strategy_transition_counts(pd.Series([False, True, True, False, True]))

    assert counts == {
        "entry_count": 2,
        "exit_count": 1,
        "latest_signal": True,
        "previous_signal": False,
    }


def test_strategy_execution_insufficient_run_shape() -> None:
    rows = [_row("2026-06-01T00:00:00Z")]
    view = {
        "source": "binance",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "view_id": "ohlcv_view:binance:BTCUSDT:1d:2026-06-01T00:00:00Z",
        "window_start": "2026-06-01T00:00:00Z",
        "window_end": "2026-06-01T00:00:00Z",
    }
    strategy = {"name": "tsmom_vol_scaled", "version": 1, "backtest": {"enabled": True}}

    assert input_is_insufficient(view, rows, minimum_rows=2) is True

    record = insufficient_strategy_run(
        strategy,
        view,
        rows,
        strategy_name="tsmom_vol_scaled",
        params={"return_window": 2},
        engine={"name": "vectorbt"},
        created_at="2026-06-02T00:00:00Z",
        minimum_rows=2,
        uncertainty="Insufficient data prevents strategy assessment.",
    )

    assert record["status"] == "insufficient_data"
    assert record["data_quality"]["row_count"] == 1
    assert record["data_quality"]["minimum_required_rows"] == 2
    assert record["indicators"] == {}
    assert record["signals"] == {}
    assert record["assessment"]["direction"] == "unknown"
    assert record["warnings"][0]["code"] == "insufficient_ohlcv_rows"
    assert record["backtest_diagnostic"]["status"] == "skipped"


def _row(open_time: str) -> dict[str, Any]:
    return {
        "open_time": open_time,
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.0,
        "volume": 10.0,
    }
