from __future__ import annotations

import json
from typing import Any

from halpha.quant.strategies import pair_zscore_reversion


def test_pair_zscore_reversion_evaluates_long_spread_with_multi_leg_backtest() -> None:
    result = pair_zscore_reversion.evaluate_pair_backtest(
        _strategy(),
        [
            _leg("BTCUSDT", [100, 100, 100, 90, 99]),
            _leg("ETHUSDT", [100, 100, 100, 100, 100]),
        ],
        cost_assumptions={"fees_bps": 0, "slippage_bps": 0},
    )

    signals = result["signal_records"]
    evaluation = result["multi_leg_evaluation"]

    assert result["status"] == "succeeded"
    assert result["output_position_policy"] == "research_multi_leg_target_exposure"
    assert result["hedge_ratio_assumption"]["mode"] == "configured_fixed"
    assert result["hedge_ratio_assumption"]["cointegration_test"] == "not_performed"
    assert signals["status"] == "succeeded"
    assert signals["long_spread_count"] == 1
    assert signals["short_spread_count"] == 0
    long_record = signals["records"][3]
    assert long_record["pair_signal_state"] == "long_spread"
    assert long_record["legs"][0]["target_exposure"] == 0.5
    assert long_record["legs"][1]["target_exposure"] == -0.5
    assert long_record["indicator_context"]["spread_zscore"] < -1.0
    assert evaluation["status"] == "succeeded"
    assert evaluation["strategy_metrics"]["gross_return_pct"] == 5.0
    assert evaluation["leg_summaries"][0]["leg_id"] == "spread_leg_a"
    assert evaluation["leg_summaries"][1]["leg_id"] == "spread_leg_b"
    json.dumps(result)


def test_pair_zscore_reversion_evaluates_short_spread_with_multi_leg_backtest() -> None:
    result = pair_zscore_reversion.evaluate_pair_backtest(
        _strategy(),
        [
            _leg("BTCUSDT", [100, 100, 100, 110, 100]),
            _leg("ETHUSDT", [100, 100, 100, 100, 100]),
        ],
        cost_assumptions={"fees_bps": 0, "slippage_bps": 0},
    )

    signals = result["signal_records"]
    short_record = signals["records"][3]

    assert result["status"] == "succeeded"
    assert signals["short_spread_count"] == 1
    assert signals["long_spread_count"] == 0
    assert short_record["pair_signal_state"] == "short_spread"
    assert short_record["legs"][0]["target_exposure"] == -0.5
    assert short_record["legs"][1]["target_exposure"] == 0.5
    assert short_record["indicator_context"]["spread_zscore"] > 1.0
    assert result["multi_leg_evaluation"]["strategy_metrics"]["gross_return_pct"] == 4.545455
    json.dumps(result)


def test_pair_zscore_reversion_records_flat_no_signal_case() -> None:
    result = pair_zscore_reversion.evaluate_pair_backtest(
        _strategy(),
        [
            _leg("BTCUSDT", [100, 100.1, 100, 100.1, 100]),
            _leg("ETHUSDT", [100, 100, 100, 100, 100]),
        ],
        cost_assumptions={"fees_bps": 0, "slippage_bps": 0},
    )

    assert result["status"] == "succeeded"
    assert result["signal_records"]["long_spread_count"] == 0
    assert result["signal_records"]["short_spread_count"] == 0
    assert result["signal_records"]["flat_count"] == 5
    assert "no_pair_exposure" in {item["code"] for item in result["signal_records"]["warnings"]}
    assert "no_multi_leg_exposure" in {item["code"] for item in result["multi_leg_evaluation"]["warnings"]}
    json.dumps(result)


def test_pair_zscore_reversion_reports_missing_leg_alignment() -> None:
    result = pair_zscore_reversion.evaluate_pair_backtest(
        _strategy(),
        [
            _leg("BTCUSDT", [100, 100, 100, 90, 99]),
            _leg("ETHUSDT", [100, 100, 100, 100, 100], skip_index=3),
        ],
    )

    assert result["status"] == "succeeded"
    assert result["signal_records"]["alignment"]["status"] == "degraded"
    assert "pair_alignment_degraded" in {item["code"] for item in result["signal_records"]["warnings"]}
    assert "multi_leg_alignment_degraded" in {item["code"] for item in result["multi_leg_evaluation"]["warnings"]}
    json.dumps(result)


def test_pair_zscore_reversion_reports_insufficient_aligned_rows() -> None:
    result = pair_zscore_reversion.evaluate_pair_backtest(
        _strategy(),
        [
            _leg("BTCUSDT", [100, 100, 100]),
            _leg("ETHUSDT", [100, 100, 100]),
        ],
    )

    assert result["status"] == "insufficient_data"
    assert result["signal_records"]["status"] == "insufficient_data"
    assert result["signal_records"]["records"] == []
    assert "insufficient_aligned_pair_rows" in {item["code"] for item in result["signal_records"]["warnings"]}
    json.dumps(result)


def test_pair_zscore_reversion_rejects_missing_second_leg() -> None:
    result = pair_zscore_reversion.evaluate_pair_backtest(_strategy(), [_leg("BTCUSDT", [100, 100, 100, 90, 99])])

    assert result["status"] == "insufficient_data"
    assert "insufficient_pair_legs" in {item["code"] for item in result["signal_records"]["warnings"]}
    json.dumps(result)


def _strategy() -> dict[str, Any]:
    return {
        "name": "pair_zscore_reversion",
        "params": {
            "lookback_window": 3,
            "entry_zscore": 1.0,
            "exit_zscore": 0.25,
            "hedge_ratio": 1.0,
        },
        "backtest": {
            "enabled": True,
            "fees_bps": 0,
            "slippage_bps": 0,
        },
    }


def _leg(symbol: str, closes: list[float], *, skip_index: int | None = None) -> dict[str, Any]:
    rows = []
    for index, close in enumerate(closes):
        if index == skip_index:
            continue
        rows.append(
            {
                "open_time": f"2026-06-{index + 1:02d}T00:00:00Z",
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 1.0,
            }
        )
    return {
        "market_identity": {
            "source": "unit",
            "symbol": symbol,
            "timeframe": "1d",
        },
        "price_basis": "close",
        "ohlcv_rows": rows,
    }
