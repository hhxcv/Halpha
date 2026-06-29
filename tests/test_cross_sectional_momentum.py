from __future__ import annotations

import json
from typing import Any

import pytest

from halpha.quant.strategies import cross_sectional_momentum


def test_cross_sectional_momentum_ranks_three_instruments_long_short() -> None:
    result = cross_sectional_momentum.evaluate_universe_backtest(
        _strategy(),
        [
            _leg("BTCUSDT", [100, 100, 110, 121]),
            _leg("ETHUSDT", [100, 100, 100, 100]),
            _leg("XRPUSDT", [100, 100, 90, 81]),
        ],
        cost_assumptions={"fees_bps": 0, "slippage_bps": 0},
    )

    signals = result["signal_records"]
    latest = signals["latest_record"]

    assert result["status"] == "succeeded"
    assert result["strategy_family"] == "cross_sectional"
    assert result["exposure_assumptions"]["gross_exposure_cap"] == 1.0
    assert signals["status"] == "succeeded"
    assert signals["active_count"] == 2
    assert latest["gross_exposure"] == 1.0
    assert latest["net_exposure"] == 0.0
    assert latest["rank_inputs"][0]["symbol"] == "BTCUSDT"
    assert latest["rank_inputs"][-1]["symbol"] == "XRPUSDT"
    exposures = {
        leg["instrument_identity"]["symbol"]: leg["target_exposure"]
        for leg in latest["legs"]
    }
    assert exposures == {
        "BTCUSDT": 0.5,
        "ETHUSDT": 0.0,
        "XRPUSDT": -0.5,
    }
    assert result["multi_leg_evaluation"]["status"] == "succeeded"
    assert result["multi_leg_evaluation"]["strategy_metrics"]["gross_return_pct"] == 10.0
    json.dumps(result)


def test_cross_sectional_momentum_records_flat_when_universe_is_too_small() -> None:
    result = cross_sectional_momentum.evaluate_universe_backtest(
        _strategy(),
        [
            _leg("BTCUSDT", [100, 100, 110, 121]),
            _leg("ETHUSDT", [100, 100, 100, 100]),
        ],
    )

    signals = result["signal_records"]

    assert result["status"] == "insufficient_data"
    assert signals["status"] == "insufficient_data"
    assert signals["record_count"] == 4
    assert signals["active_count"] == 0
    assert all(record["gross_exposure"] == 0.0 for record in signals["records"])
    assert "insufficient_universe_instruments" in {item["code"] for item in signals["warnings"]}
    json.dumps(result)


def test_cross_sectional_momentum_reports_degraded_alignment_for_missing_data() -> None:
    result = cross_sectional_momentum.evaluate_universe_backtest(
        _strategy(),
        [
            _leg("BTCUSDT", [100, 100, 110, 121]),
            _leg("ETHUSDT", [100, 100, 100, 100], skip_index=1),
            _leg("XRPUSDT", [100, 100, 90, 81]),
        ],
    )

    signals = result["signal_records"]

    assert result["status"] == "succeeded"
    assert signals["alignment"]["status"] == "degraded"
    assert "universe_alignment_degraded" in {item["code"] for item in signals["warnings"]}
    assert "multi_leg_alignment_degraded" in {item["code"] for item in result["multi_leg_evaluation"]["warnings"]}
    json.dumps(result)


def test_cross_sectional_momentum_resolves_ties_with_stable_identity_ordering() -> None:
    result = cross_sectional_momentum.evaluate_universe_backtest(
        _strategy(),
        [
            _leg("ETHUSDT", [100, 100, 100, 100]),
            _leg("BTCUSDT", [100, 100, 100, 100]),
            _leg("ADAUSDT", [100, 100, 100, 100]),
        ],
    )

    latest = result["signal_records"]["latest_record"]
    ranks = [item["symbol"] for item in latest["rank_inputs"]]
    exposures = {
        leg["instrument_identity"]["symbol"]: leg["target_exposure"]
        for leg in latest["legs"]
    }

    assert result["status"] == "succeeded"
    assert ranks == ["ADAUSDT", "BTCUSDT", "ETHUSDT"]
    assert exposures["ADAUSDT"] == 0.5
    assert exposures["BTCUSDT"] == 0.0
    assert exposures["ETHUSDT"] == -0.5
    assert "cross_sectional_ties_resolved_deterministically" in {
        item["code"] for item in result["signal_records"]["warnings"]
    }
    json.dumps(result)


def test_cross_sectional_momentum_reports_insufficient_aligned_rows() -> None:
    result = cross_sectional_momentum.evaluate_universe_backtest(
        _strategy(),
        [
            _leg("BTCUSDT", [100, 100]),
            _leg("ETHUSDT", [100, 100]),
            _leg("XRPUSDT", [100, 100]),
        ],
    )

    assert result["status"] == "insufficient_data"
    assert result["signal_records"]["record_count"] == 2
    assert all(record["gross_exposure"] == 0.0 for record in result["signal_records"]["records"])
    assert "insufficient_aligned_universe_rows" in {
        item["code"] for item in result["signal_records"]["warnings"]
    }
    json.dumps(result)


def test_cross_sectional_momentum_missing_alignment_returns_insufficient_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cross_sectional_momentum, "_universe_warnings", lambda params, legs, aligned: [])

    signals = cross_sectional_momentum.universe_signal_records(
        _strategy(),
        [_leg("BTCUSDT", [100, 101, 102])],
    )

    assert signals["status"] == "insufficient_data"
    assert signals["record_count"] == 0
    assert signals["alignment"]["status"] == "not_aligned"
    assert "insufficient_aligned_universe_rows" in {item["code"] for item in signals["warnings"]}
    json.dumps(signals)


def _strategy() -> dict[str, Any]:
    return {
        "name": "cross_sectional_momentum",
        "params": {
            "lookback_window": 2,
            "long_count": 1,
            "short_count": 1,
            "min_instrument_count": 3,
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
            "source": "binance_usdm",
            "symbol": symbol,
            "timeframe": "1d",
        },
        "price_basis": "close",
        "ohlcv_rows": rows,
    }
