from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from halpha.quant.derivatives_features import (
    build_funding_rate_feature_input,
    funding_rate_filter_contexts,
)
from halpha.storage import write_json


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_funding_rate_feature_input_loads_visible_records_with_as_of_boundary(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_history_records(
        tmp_path,
        [
            _funding_record(
                "2026-06-01T00:00:00Z",
                0.0001,
                first_seen_at="2026-06-01T00:05:00Z",
            ),
            _funding_record(
                "2026-06-02T00:00:00Z",
                0.0002,
                first_seen_at="2026-06-02T00:05:00Z",
            ),
        ],
    )

    result = build_funding_rate_feature_input(
        config_path,
        market_identity={"source": "binance_usdm", "symbol": "BTCUSDT"},
        start="2026-06-01T00:00:00Z",
        end="2026-06-03T00:00:00Z",
        as_of="2026-06-01T12:00:00Z",
    )

    assert result["status"] == "available"
    assert result["artifact_type"] == "strategy_derivatives_feature_input"
    assert result["record_count"] == 1
    assert result["matched_record_count"] == 1
    assert result["records"][0]["value"] == 0.0001
    assert result["records"][0]["first_seen_at"] == "2026-06-01T00:05:00Z"
    json.dumps(result)


def test_funding_rate_feature_input_excludes_records_first_seen_after_as_of_boundary(
    tmp_path: Path,
) -> None:
    config_path = _write_config(tmp_path)
    _write_history_records(
        tmp_path,
        [
            _funding_record(
                "2026-06-01T00:00:00Z",
                0.0001,
                first_seen_at="2026-06-02T00:00:00Z",
            )
        ],
    )

    result = build_funding_rate_feature_input(
        config_path,
        market_identity={"source": "binance_usdm", "symbol": "BTCUSDT"},
        start="2026-06-01T00:00:00Z",
        end="2026-06-02T00:00:00Z",
        as_of="2026-06-01T12:00:00Z",
    )

    assert result["status"] == "unavailable"
    assert result["matched_record_count"] == 1
    assert result["skipped_record_count"] == 1
    assert "derivatives_feature_not_observable_as_of" in {item["code"] for item in result["warnings"]}
    assert "derivatives_feature_unavailable" in {item["code"] for item in result["warnings"]}


def test_funding_rate_feature_input_marks_missing_and_stale_records(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)

    missing = build_funding_rate_feature_input(
        config_path,
        market_identity={"source": "binance_usdm", "symbol": "ETHUSDT"},
        start="2026-06-01T00:00:00Z",
        end="2026-06-02T00:00:00Z",
    )

    _write_history_records(
        tmp_path,
        [
            _funding_record(
                "2026-06-01T00:00:00Z",
                0.0001,
                first_seen_at="2026-06-01T00:05:00Z",
            )
        ],
    )
    stale = build_funding_rate_feature_input(
        config_path,
        market_identity={"source": "binance_usdm", "symbol": "BTCUSDT"},
        start="2026-06-01T00:00:00Z",
        end="2026-06-03T00:00:00Z",
        max_staleness_seconds=3600,
    )

    assert missing["status"] == "unavailable"
    assert "derivatives_feature_unavailable" in {item["code"] for item in missing["warnings"]}
    assert stale["status"] == "stale"
    assert stale["record_count"] == 1
    assert "derivatives_feature_stale" in {item["code"] for item in stale["warnings"]}


def test_funding_rate_feature_input_marks_partial_and_degraded_source_records(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_history_records(
        tmp_path,
        [
            _funding_record(
                "2026-06-01T00:00:00Z",
                0.0001,
                first_seen_at="2026-06-01T00:05:00Z",
                warnings=["source field was incomplete"],
            ),
            _funding_record(
                "2026-06-01T08:00:00Z",
                "invalid",
                first_seen_at="2026-06-01T08:05:00Z",
            ),
        ],
    )

    result = build_funding_rate_feature_input(
        config_path,
        market_identity={"source": "binance_usdm", "symbol": "BTCUSDT"},
        start="2026-06-01T00:00:00Z",
        end="2026-06-02T00:00:00Z",
    )

    assert result["status"] == "partial"
    assert result["record_count"] == 1
    assert result["records"][0]["quality"]["status"] == "degraded"
    assert "invalid_derivatives_feature_metric" in {item["code"] for item in result["warnings"]}
    assert "derivatives_feature_partial" in {item["code"] for item in result["warnings"]}


def test_funding_rate_filter_contexts_use_latest_observable_feature_record() -> None:
    contexts = funding_rate_filter_contexts(
        [
            "2026-06-01T00:30:00Z",
            "2026-06-01T01:30:00Z",
            "2026-06-01T02:30:00Z",
        ],
        {
            "status": "available",
            "records": [
                _feature_record("2026-06-01T01:00:00Z", 0.0001),
                _feature_record("2026-06-01T02:00:00Z", 0.002),
            ],
        },
        max_abs_funding_rate=0.001,
    )

    assert contexts[0]["status"] == "unavailable"
    assert contexts[0]["suppression_reason"] == "missing_derivatives_feature"
    assert contexts[1]["status"] == "passed"
    assert contexts[1]["feature_value"] == 0.0001
    assert contexts[2]["status"] == "suppressed"
    assert contexts[2]["suppression_reason"] == "funding_rate_abs_above_max"


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text("run:\n  output_dir: runs\n", encoding="utf-8")
    return path


def _write_history_records(tmp_path: Path, records: list[dict[str, Any]]) -> None:
    path = (
        tmp_path
        / "data"
        / "market"
        / "derivatives"
        / "source=binance_usdm"
        / "data_class=funding_rate"
        / "symbol=BTCUSDT"
        / "period=8h"
        / "records.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, records)


def _funding_record(
    as_of: str,
    funding_rate: Any,
    *,
    first_seen_at: str,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "history_key": f"binance_usdm|usd_m_futures|funding_rate|BTCUSDT|8h|{as_of}",
        "item_id": f"derivatives:{as_of}",
        "data_class": "funding_rate",
        "source": "binance_usdm",
        "market_type": "usd_m_futures",
        "symbol": "BTCUSDT",
        "period": "8h",
        "as_of": as_of,
        "endpoint": "funding_rate_history",
        "metrics": {"funding_rate": funding_rate},
        "units": {"funding_rate": "ratio"},
        "raw_fields": {},
        "payload_signature": as_of,
        "origin_run_ids": ["run-1"],
        "first_seen_run_id": "run-1",
        "last_seen_run_id": "run-1",
        "first_seen_at": first_seen_at,
        "last_seen_at": first_seen_at,
        "status": "warning" if warnings else "active",
        "warnings": warnings or [],
        "errors": [],
        "source_artifacts": ["runs/run-1/raw/derivatives_market.json"],
    }


def _feature_record(feature_time: str, value: float) -> dict[str, Any]:
    return {
        "feature_time": feature_time,
        "as_of": feature_time,
        "first_seen_at": feature_time,
        "source": "binance_usdm",
        "symbol": "BTCUSDT",
        "period": "8h",
        "data_class": "funding_rate",
        "metric": "funding_rate",
        "value": value,
        "unit": "ratio",
        "quality": {"status": "available", "warnings": [], "errors": []},
        "source_artifacts": [],
    }
