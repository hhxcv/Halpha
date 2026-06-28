from __future__ import annotations

from pathlib import Path
from typing import Any

from halpha.quant.funding_costs import build_funding_cost_input, funding_cost_input_from_records
from halpha.storage import write_json


def test_funding_cost_input_aligns_records_to_ohlcv_periods() -> None:
    rows = [
        _row("2026-06-01T00:00:00Z"),
        _row("2026-06-02T00:00:00Z"),
        _row("2026-06-03T00:00:00Z"),
    ]

    result = funding_cost_input_from_records(
        rows,
        [
            _funding_record("2026-06-01T08:00:00Z", 0.001),
            _funding_record("2026-06-01T16:00:00Z", 0.002),
            _funding_record("2026-06-02T08:00:00Z", -0.001),
        ],
        source="binance_usdm",
        symbol="BTCUSDT",
        period="8h",
        as_of_boundary="2026-06-03T00:00:00Z",
    )

    assert result["status"] == "available"
    assert result["matched_record_count"] == 3
    assert result["missing_period_count"] == 0
    assert [item["funding_rate"] for item in result["periods"]] == [0.003, -0.001]
    assert result["periods"][0]["funding_as_of"] == [
        "2026-06-01T08:00:00Z",
        "2026-06-01T16:00:00Z",
    ]


def test_funding_cost_input_marks_partial_coverage() -> None:
    rows = [
        _row("2026-06-01T00:00:00Z"),
        _row("2026-06-02T00:00:00Z"),
        _row("2026-06-03T00:00:00Z"),
    ]

    result = funding_cost_input_from_records(
        rows,
        [_funding_record("2026-06-02T08:00:00Z", 0.001)],
        source="binance_usdm",
        symbol="BTCUSDT",
    )

    assert result["status"] == "partial"
    assert result["matched_record_count"] == 1
    assert result["missing_period_count"] == 1
    assert "funding_history_partial" in {warning["code"] for warning in result["warnings"]}


def test_build_funding_cost_input_uses_derivatives_query_as_of_boundary(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = _write_config(tmp_path)
    _write_history_records(
        tmp_path / "data" / "market" / "derivatives" / "source=binance_usdm"
        / "data_class=funding_rate" / "symbol=BTCUSDT" / "period=8h" / "records.json",
        [
            _funding_record("2026-06-01T08:00:00Z", 0.001),
            _funding_record("2026-06-02T08:00:00Z", 0.002),
        ],
    )
    rows = [
        _row("2026-06-01T00:00:00Z"),
        _row("2026-06-02T00:00:00Z"),
        _row("2026-06-03T00:00:00Z"),
    ]

    result = build_funding_cost_input(
        config_path,
        market_identity={
            "source": "binance_usdm",
            "symbol": "BTCUSDT",
        },
        ohlcv_rows=rows,
        as_of="2026-06-02T00:00:00Z",
    )

    assert result["status"] == "partial"
    assert result["matched_record_count"] == 1
    assert [item["funding_rate"] for item in result["periods"]] == [0.001, 0.0]
    assert result["periods"][1]["matched_record_count"] == 0


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text("run:\n  output_dir: runs\n", encoding="utf-8")
    return path


def _write_history_records(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, records)


def _row(open_time: str) -> dict[str, Any]:
    return {
        "open_time": open_time,
        "open": 100.0,
        "high": 100.0,
        "low": 100.0,
        "close": 100.0,
        "volume": 1.0,
    }


def _funding_record(as_of: str, funding_rate: float) -> dict[str, Any]:
    return {
        "history_key": f"binance_usdm|usd_m_futures|funding_rate|BTCUSDT|8h|{as_of}",
        "item_id": f"derivatives:{as_of}",
        "data_class": "funding_rate",
        "source": "binance_usdm",
        "market_type": "usd_m_futures",
        "symbol": "BTCUSDT",
        "period": "8h",
        "as_of": as_of,
        "endpoint": "https://example.com/funding",
        "metrics": {"funding_rate": funding_rate},
        "units": {"funding_rate": "ratio"},
        "raw_fields": {},
        "payload_signature": as_of,
        "origin_run_ids": ["run-1"],
        "first_seen_run_id": "run-1",
        "last_seen_run_id": "run-1",
        "first_seen_at": "2026-06-03T00:00:00Z",
        "last_seen_at": "2026-06-03T00:00:00Z",
        "status": "active",
        "warnings": [],
        "errors": [],
        "source_artifacts": ["runs/run-1/raw/derivatives_market.json"],
    }
