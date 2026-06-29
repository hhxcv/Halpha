from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

import pytest

from halpha.data.collection_coverage import write_collection_coverage_state
from halpha.quant.event_features import (
    build_market_anomaly_feature_input,
    event_count_filter_contexts,
    event_window_contexts,
)
from halpha.quant.multi_leg_evaluation import evaluate_multi_leg_backtest
from halpha.quant.strategy_evaluation import evaluate_single_window_backtest
from halpha.storage import write_json


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_quant_golden_signed_long_short_costs_and_no_lookahead_timing() -> None:
    rows = [
        _ohlcv_row("2026-06-01T00:00:00Z", 100),
        _ohlcv_row("2026-06-02T00:00:00Z", 110),
        _ohlcv_row("2026-06-03T00:00:00Z", 99),
        _ohlcv_row("2026-06-04T00:00:00Z", 108.9),
    ]

    result = evaluate_single_window_backtest(
        strategy=_strategy(),
        market_identity=_market_identity(),
        ohlcv_rows=rows,
        signal_records=_signed_signals(rows, [1, -1, -1, 0]),
        cost_assumptions={"fees_bps": 10, "slippage_bps": 5},
    )

    assert result["status"] == "succeeded"
    assert result["execution_model"]["execution_model_id"] == "close_to_close_next_bar_signed_v1"
    assert result["execution_model"]["position_timing"] == "next_bar"
    assert result["execution_model"]["lookahead_policy"] == "no_same_bar_execution"

    # Hand check:
    # close returns: +10%, -10%, +10%
    # next-bar positions from prior signals: +1, -1, -1
    # one-way cost rate: 15 bps; turnovers: 1, 2, 0
    # net period returns: 9.85%, 9.70%, -10.00%
    assert _curve(result, "position") == [0.0, 1.0, -1.0, -1.0]
    assert _curve(result, "turnover") == [0.0, 1.0, 2.0, 0.0]
    assert _curve(result, "period_gross_return_pct") == [None, 10.0, 10.0, -10.0]
    assert _curve(result, "period_net_return_pct") == [None, 9.85, 9.7, -10.0]
    assert _curve(result, "cost_pct") == [0.0, 0.15, 0.3, 0.0]
    assert _curve(result, "net_equity") == [1.0, 1.0985, 1.205054, 1.084549]
    assert result["strategy_metrics"]["total_cost_pct"] == 0.45
    assert result["strategy_metrics"]["cost_drag_pct"] == 0.445095
    assert result["strategy_metrics"]["net_return_pct"] == 8.454905
    assert result["trade_summary"]["long_to_short_count"] == 1
    assert result["trade_summary"]["side_flip_count"] == 1
    json.dumps(result)


def test_quant_golden_funding_costs_have_opposite_long_short_effects() -> None:
    rows = [
        _ohlcv_row("2026-06-01T00:00:00Z", 100),
        _ohlcv_row("2026-06-02T00:00:00Z", 100),
        _ohlcv_row("2026-06-03T00:00:00Z", 100),
    ]
    funding = _funding_costs(rows, [0.01, -0.005])

    long_result = evaluate_single_window_backtest(
        strategy=_strategy(),
        market_identity=_contract_market_identity(),
        ohlcv_rows=rows,
        signal_records=_signed_signals(rows, [1, 1, 1]),
        funding_costs=funding,
    )
    short_result = evaluate_single_window_backtest(
        strategy=_strategy(),
        market_identity=_contract_market_identity(),
        ohlcv_rows=rows,
        signal_records=_signed_signals(rows, [-1, -1, -1]),
        funding_costs=funding,
    )

    assert long_result["status"] == "succeeded"
    assert short_result["status"] == "succeeded"
    assert _curve(long_result, "funding_return_pct") == [0.0, -1.0, 0.5]
    assert _curve(short_result, "funding_return_pct") == [0.0, 1.0, -0.5]
    assert long_result["strategy_metrics"]["funding_drag_pct"] == 0.5
    assert short_result["strategy_metrics"]["funding_drag_pct"] == -0.5
    assert long_result["strategy_metrics"]["net_return_pct"] == -0.505
    assert short_result["strategy_metrics"]["net_return_pct"] == 0.495
    assert long_result["funding_costs"]["matched_record_count"] == 2
    json.dumps(long_result)
    json.dumps(short_result)


def test_quant_golden_multi_leg_alignment_and_previous_signal_timing() -> None:
    times = [
        "2026-06-01T00:00:00Z",
        "2026-06-02T00:00:00Z",
        "2026-06-03T00:00:00Z",
    ]
    btc_rows = [
        _ohlcv_row(times[0], 100),
        _ohlcv_row(times[1], 110),
        _ohlcv_row(times[2], 121),
        _ohlcv_row("2026-06-04T00:00:00Z", 130),
    ]
    eth_rows = [
        _ohlcv_row(times[0], 100),
        _ohlcv_row(times[1], 90),
        _ohlcv_row(times[2], 81),
    ]

    result = evaluate_multi_leg_backtest(
        strategy={"name": "pair_golden", "params": {}},
        legs=[
            _leg("btc", "BTCUSDT", btc_rows),
            _leg("eth", "ETHUSDT", eth_rows),
        ],
        signal_records=_multi_leg_signals(
            times,
            [
                {"btc": 0.0, "eth": 0.0},
                {"btc": 0.5, "eth": -0.5},
                {"btc": 0.5, "eth": -0.5},
            ],
        ),
        cost_assumptions={"fees_bps": 10, "slippage_bps": 0},
    )

    assert result["status"] == "succeeded"
    assert result["alignment"]["status"] == "degraded"
    assert result["alignment"]["row_count"] == 3
    assert result["alignment"]["omitted_rows"] == [
        {"leg_id": "btc", "input_rows": 4, "aligned_rows": 3, "omitted_rows": 1},
        {"leg_id": "eth", "input_rows": 3, "aligned_rows": 3, "omitted_rows": 0},
    ]
    assert [point["period_gross_return_pct"] for point in result["equity_curve"]] == [None, 0.0, 10.0]
    assert [point["period_net_return_pct"] for point in result["equity_curve"]] == [None, 0.0, 9.9]
    assert [point["turnover"] for point in result["equity_curve"]] == [0.0, 0.0, 1.0]
    assert result["strategy_metrics"]["net_return_pct"] == 9.9
    assert result["strategy_metrics"]["average_gross_exposure"] == 0.5
    assert "multi_leg_alignment_degraded" in {item["code"] for item in result["warnings"]}
    json.dumps(result)


def test_quant_golden_event_as_of_excludes_future_and_unknown_coverage_is_explicit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    _write_market_anomaly_records(
        tmp_path,
        [
            _market_anomaly_record(
                "BTCUSDT",
                "2026-06-01T01:00:00Z",
                first_seen_at="2026-06-01T01:05:00Z",
                title="BTCUSDT visible anomaly",
            ),
            _market_anomaly_record(
                "BTCUSDT",
                "2026-06-01T03:00:00Z",
                first_seen_at="2026-06-01T03:05:00Z",
                title="BTCUSDT future anomaly",
            ),
            _market_anomaly_record(
                "BTCUSDT",
                "2026-06-01T01:30:00Z",
                first_seen_at="2026-06-02T00:00:00Z",
                title="BTCUSDT late anomaly",
            ),
        ],
    )

    feature = build_market_anomaly_feature_input(
        config_path,
        identity={"symbol": "BTCUSDT"},
        start="2026-06-01T00:00:00Z",
        end="2026-06-02T00:00:00Z",
        as_of="2026-06-01T04:00:00Z",
    )
    contexts = event_window_contexts(
        ["2026-06-01T02:00:00Z"],
        feature,
        window_seconds=24 * 3600,
        direction="lookback",
    )

    assert feature["status"] == "partial"
    assert feature["matched_record_count"] == 2
    assert feature["record_count"] == 2
    assert "incomplete_collection_coverage" in {item["code"] for item in feature["warnings"]}
    assert contexts[0]["status"] == "available"
    assert contexts[0]["event_count"] == 1
    assert contexts[0]["records"][0]["title"] == "BTCUSDT visible anomaly"

    missing_root = tmp_path / "missing"
    missing_root.mkdir()
    monkeypatch.chdir(missing_root)
    missing_config_path = missing_root / "config.yaml"
    missing_config_path.write_text("run:\n  output_dir: runs\n", encoding="utf-8")
    unknown = build_market_anomaly_feature_input(
        missing_config_path,
        identity={"symbol": "ETHUSDT"},
        start="2026-06-01T00:00:00Z",
        end="2026-06-02T00:00:00Z",
        as_of="2026-06-02T00:00:00Z",
    )
    filters = event_count_filter_contexts(
        ["2026-06-01T12:00:00Z"],
        unknown,
        window_seconds=24 * 3600,
        min_event_count=1,
    )

    assert unknown["status"] == "unavailable"
    assert unknown["record_count"] == 0
    assert "unknown_collection_coverage" in {item["code"] for item in unknown["warnings"]}
    assert filters[0]["suppressed"] is True
    assert filters[0]["suppression_reason"] == "missing_event_feature"
    json.dumps(feature)
    json.dumps(unknown)


def test_quant_golden_backtest_medium_fixture_runtime_guardrail() -> None:
    rows = [
        _ohlcv_row(_open_time(index), 100 + math.sin(index / 11) * 3 + index * 0.01)
        for index in range(2_000)
    ]
    targets = [1.0 if index % 5 in {0, 1} else -0.5 if index % 5 == 2 else 0.0 for index in range(len(rows))]

    start = perf_counter()
    result = evaluate_single_window_backtest(
        strategy=_strategy(),
        market_identity=_contract_market_identity(timeframe="1h"),
        ohlcv_rows=rows,
        signal_records=_signed_signals(rows, targets),
        cost_assumptions={"fees_bps": 5, "slippage_bps": 5},
        funding_costs=_funding_costs(rows, [0.0 for _index in range(len(rows) - 1)]),
    )
    elapsed = perf_counter() - start

    assert result["status"] == "succeeded"
    assert result["sample"]["rows"] == 2_000
    assert len(result["equity_curve"]) == 2_000
    assert len(result["drawdown_curve"]) == 2_000
    assert elapsed < 2.0
    json.dumps(result)


def _strategy() -> dict[str, Any]:
    return {"name": "golden_strategy", "params": {"window": 2}}


def _market_identity() -> dict[str, str]:
    return {"source": "unit", "symbol": "TEST", "timeframe": "1d"}


def _contract_market_identity(*, timeframe: str = "1d") -> dict[str, Any]:
    return {
        "source": "unit",
        "symbol": "TEST",
        "timeframe": timeframe,
        "instrument_identity": {
            "schema_version": 1,
            "source": "unit",
            "symbol": "TEST",
            "exchange_symbol": "TEST",
            "market_type": "swap",
            "contract_type": "linear_perpetual",
            "base_asset": "TEST",
            "quote_asset": "USDT",
            "settlement_asset": "USDT",
            "price_unit": "quote_asset_per_base_asset",
            "timeframe": timeframe,
            "identity_status": "normalized",
            "warnings": [],
        },
    }


def _ohlcv_row(open_time: str, close: float) -> dict[str, Any]:
    return {
        "open_time": open_time,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 1.0,
    }


def _signed_signals(rows: list[dict[str, Any]], targets: list[float]) -> dict[str, Any]:
    return {
        "status": "succeeded",
        "signal_record_version": 2,
        "position_policy": "research_signed_target_exposure",
        "records": [
            {
                "schema_version": 2,
                "open_time": row["open_time"],
                "signal_time": row["open_time"],
                "signal": {
                    "active": target != 0,
                    "position_state": _target_state(target),
                },
                "position": {
                    "target_exposure": target,
                    "unit": "fractional_signed_exposure",
                    "position_state": _target_state(target),
                },
            }
            for row, target in zip(rows, targets, strict=True)
        ],
    }


def _funding_costs(rows: list[dict[str, Any]], rates: list[float]) -> dict[str, Any]:
    periods = [
        {
            "period_start": rows[index - 1]["open_time"],
            "period_end": rows[index]["open_time"],
            "funding_rate": rate,
            "matched_record_count": 1,
            "funding_as_of": [rows[index]["open_time"]],
        }
        for index, rate in enumerate(rates, start=1)
    ]
    return {
        "schema_version": 1,
        "artifact_type": "strategy_funding_cost_input",
        "status": "available",
        "source": "unit",
        "symbol": "TEST",
        "data_class": "funding_rate",
        "period": "8h",
        "unit": "fraction_of_notional",
        "sign_convention": "positive_rate_paid_by_longs_received_by_shorts",
        "period_count": len(periods),
        "matched_record_count": len(periods),
        "missing_period_count": 0,
        "periods": periods,
        "warnings": [],
        "errors": [],
        "source_artifacts": [],
    }


def _target_state(target: float) -> str:
    if target > 0:
        return "long"
    if target < 0:
        return "short"
    return "flat"


def _leg(leg_id: str, symbol: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "leg_id": leg_id,
        "market_identity": {
            "source": "unit",
            "symbol": symbol,
            "timeframe": "1d",
        },
        "price_basis": "close",
        "ohlcv_rows": rows,
    }


def _multi_leg_signals(times: list[str], exposures_by_time: list[dict[str, float]]) -> dict[str, Any]:
    return {
        "status": "succeeded",
        "record_type": "multi_leg_signal",
        "records": [
            {
                "record_type": "multi_leg_signal",
                "signal_time": signal_time,
                "legs": [
                    {"leg_id": leg_id, "target_exposure": exposure, "price_basis": "close"}
                    for leg_id, exposure in sorted(exposures.items())
                ],
            }
            for signal_time, exposures in zip(times, exposures_by_time, strict=True)
        ],
    }


def _curve(result: dict[str, Any], field: str) -> list[Any]:
    return [item[field] for item in result["equity_curve"]]


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text("run:\n  output_dir: runs\n", encoding="utf-8")
    write_collection_coverage_state(
        path,
        [
            {
                "data_type": "market_anomaly",
                "source": "halpha_monitor_rules",
                "identity": {"symbol": "BTCUSDT"},
                "range_start": "2026-06-01T00:00:00Z",
                "range_end": "2026-06-01T02:00:00Z",
                "status": "collected",
                "record_count": 1,
            },
            {
                "data_type": "market_anomaly",
                "source": "halpha_monitor_rules",
                "identity": {"symbol": "BTCUSDT"},
                "range_start": "2026-06-01T02:00:00Z",
                "range_end": "2026-06-02T00:00:00Z",
                "status": "not_collected",
                "record_count": 0,
            },
        ],
        now="2026-06-02T00:00:00Z",
    )
    return path


def _write_market_anomaly_records(tmp_path: Path, records: list[dict[str, Any]]) -> None:
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for record in records:
        key = (
            str(record["source_kind"]),
            str(record["data_class"]),
            str(record["symbol"]),
            str(record["timeframe"]),
        )
        groups.setdefault(key, []).append(record)
    for (source_kind, data_class, symbol, timeframe), group_records in groups.items():
        path = (
            tmp_path
            / "data"
            / "market"
            / "anomalies"
            / f"source_kind={source_kind}"
            / f"data_class={data_class}"
            / f"symbol={symbol}"
            / f"timeframe={timeframe}"
            / "records.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, group_records)


def _market_anomaly_record(
    symbol: str,
    observed_at: str,
    *,
    first_seen_at: str,
    title: str,
) -> dict[str, Any]:
    return {
        "history_key": f"volume_spike|{symbol}|1m|{observed_at}|volume|up",
        "anomaly_id": f"anomaly:{symbol}:{observed_at}",
        "dedupe_key": f"{symbol}:volume_spike:{observed_at}",
        "source_kind": "halpha_monitor_rule",
        "source": "halpha_monitor_rules",
        "source_kinds": ["halpha_monitor_rule"],
        "sources": ["halpha_monitor_rules"],
        "source_records": [],
        "data_class": "volume_spike",
        "symbol": symbol,
        "market_type": "swap",
        "timeframe": "1m",
        "observed_at": observed_at,
        "published_at": observed_at,
        "collected_at": first_seen_at,
        "first_seen_at": first_seen_at,
        "last_seen_at": first_seen_at,
        "severity": "high",
        "direction": "up",
        "metric": "volume",
        "value": 2.0,
        "threshold": 1.5,
        "unit": "ratio",
        "window_start": None,
        "window_end": observed_at,
        "title": title,
        "summary": f"{title} detected.",
        "metrics": {"multiplier": 2.0},
        "units": {"multiplier": "ratio"},
        "raw_fields": {},
        "payload_signature": observed_at,
        "origin_run_ids": ["run-1"],
        "first_seen_run_id": "run-1",
        "last_seen_run_id": "run-1",
        "status": "active",
        "warnings": [],
        "errors": [],
        "source_artifacts": ["runs/run-1/raw/market_anomalies.json"],
    }


def _open_time(index: int) -> str:
    value = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=index)
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")
