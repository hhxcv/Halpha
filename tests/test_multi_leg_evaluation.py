from __future__ import annotations

import json
from typing import Any

from halpha.quant.multi_leg_evaluation import evaluate_multi_leg_backtest


def test_multi_leg_backtest_evaluates_pair_long_short_no_lookahead() -> None:
    btc_rows = [
        _row("2026-06-01T00:00:00Z", 100),
        _row("2026-06-02T00:00:00Z", 110),
        _row("2026-06-03T00:00:00Z", 121),
    ]
    eth_rows = [
        _row("2026-06-01T00:00:00Z", 100),
        _row("2026-06-02T00:00:00Z", 90),
        _row("2026-06-03T00:00:00Z", 81),
    ]

    result = evaluate_multi_leg_backtest(
        strategy=_strategy(),
        legs=[
            _leg("long_leg", "BTCUSDT", btc_rows),
            _leg("short_leg", "ETHUSDT", eth_rows),
        ],
        signal_records=_signals(
            ["2026-06-01T00:00:00Z", "2026-06-02T00:00:00Z", "2026-06-03T00:00:00Z"],
            {"long_leg": 0.5, "short_leg": -0.5},
        ),
        cost_assumptions={"fees_bps": 0, "slippage_bps": 0},
    )

    assert result["status"] == "succeeded"
    assert result["execution_model"]["execution_model_id"] == "close_to_close_next_bar_multi_leg_v1"
    assert result["alignment"]["status"] == "aligned"
    assert result["strategy_metrics"]["gross_return_pct"] == 21.0
    assert result["strategy_metrics"]["net_return_pct"] == 21.0
    assert result["strategy_metrics"]["average_gross_exposure"] == 1.0
    assert result["strategy_metrics"]["average_net_exposure"] == 0.0
    assert [point["period_gross_return_pct"] for point in result["equity_curve"]] == [None, 10.0, 10.0]
    assert result["equity_curve"][1]["legs"][0]["gross_contribution_pct"] == 5.0
    assert result["equity_curve"][1]["legs"][1]["gross_contribution_pct"] == 5.0
    summaries = {item["leg_id"]: item for item in result["leg_summaries"]}
    assert summaries["long_leg"]["gross_contribution_pct"] == 10.0
    assert summaries["short_leg"]["gross_contribution_pct"] == 10.0
    json.dumps(result)


def test_multi_leg_backtest_reports_missing_leg_alignment() -> None:
    result = evaluate_multi_leg_backtest(
        strategy=_strategy(),
        legs=[
            _leg(
                "long_leg",
                "BTCUSDT",
                [_row("2026-06-01T00:00:00Z", 100), _row("2026-06-02T00:00:00Z", 110)],
            ),
            _leg(
                "short_leg",
                "ETHUSDT",
                [_row("2026-06-01T00:00:00Z", 100), _row("2026-06-03T00:00:00Z", 90)],
            ),
        ],
        signal_records=_signals(
            ["2026-06-01T00:00:00Z", "2026-06-02T00:00:00Z", "2026-06-03T00:00:00Z"],
            {"long_leg": 0.5, "short_leg": -0.5},
        ),
    )

    assert result["status"] == "insufficient_data"
    assert result["alignment"]["status"] == "degraded"
    assert result["alignment"]["row_count"] == 1
    assert result["warnings"][0]["code"] == "insufficient_aligned_rows"
    json.dumps(result)


def test_multi_leg_backtest_rejects_mismatched_timeframes_without_resampling() -> None:
    rows = [_row("2026-06-01T00:00:00Z", 100), _row("2026-06-02T00:00:00Z", 101)]

    result = evaluate_multi_leg_backtest(
        strategy=_strategy(),
        legs=[
            _leg("long_leg", "BTCUSDT", rows, timeframe="1d"),
            _leg("short_leg", "ETHUSDT", rows, timeframe="1h"),
        ],
        signal_records=_signals(
            ["2026-06-01T00:00:00Z", "2026-06-02T00:00:00Z"],
            {"long_leg": 0.5, "short_leg": -0.5},
        ),
    )

    assert result["status"] == "insufficient_data"
    assert "mismatched_leg_timeframes" in {item["code"] for item in result["warnings"]}
    assert result["equity_curve"] == []
    json.dumps(result)


def test_multi_leg_backtest_records_flat_exposure() -> None:
    rows = [
        _row("2026-06-01T00:00:00Z", 100),
        _row("2026-06-02T00:00:00Z", 110),
        _row("2026-06-03T00:00:00Z", 90),
    ]

    result = evaluate_multi_leg_backtest(
        strategy=_strategy(),
        legs=[
            _leg("long_leg", "BTCUSDT", rows),
            _leg("short_leg", "ETHUSDT", rows),
        ],
        signal_records=_signals(
            ["2026-06-01T00:00:00Z", "2026-06-02T00:00:00Z", "2026-06-03T00:00:00Z"],
            {"long_leg": 0.0, "short_leg": 0.0},
        ),
    )

    assert result["status"] == "succeeded"
    assert result["strategy_metrics"]["net_return_pct"] == 0.0
    assert result["strategy_metrics"]["average_gross_exposure"] == 0.0
    assert result["strategy_metrics"]["turnover"] == 0.0
    assert "no_multi_leg_exposure" in {item["code"] for item in result["warnings"]}
    json.dumps(result)


def _strategy() -> dict[str, Any]:
    return {
        "name": "pair_test",
        "params": {"lookback": 2},
    }


def _leg(leg_id: str, symbol: str, rows: list[dict[str, Any]], *, timeframe: str = "1d") -> dict[str, Any]:
    return {
        "leg_id": leg_id,
        "market_identity": {
            "source": "unit",
            "symbol": symbol,
            "timeframe": timeframe,
        },
        "price_basis": "close",
        "ohlcv_rows": rows,
    }


def _signals(times: list[str], exposures: dict[str, float]) -> dict[str, Any]:
    return {
        "status": "succeeded",
        "record_type": "multi_leg_signal",
        "records": [
            {
                "record_type": "multi_leg_signal",
                "signal_time": time,
                "legs": [
                    {
                        "leg_id": leg_id,
                        "target_exposure": exposure,
                        "price_basis": "close",
                    }
                    for leg_id, exposure in sorted(exposures.items())
                ],
            }
            for time in times
        ],
    }


def _row(open_time: str, close: float) -> dict[str, Any]:
    return {
        "open_time": open_time,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 1.0,
    }
