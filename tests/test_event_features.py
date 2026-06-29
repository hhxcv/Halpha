from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from halpha.data.collection_coverage import write_collection_coverage_state
from halpha.quant.event_features import (
    build_event_feature_input,
    build_market_anomaly_feature_input,
    event_count_filter_contexts,
    event_window_contexts,
)
from halpha.storage import write_json


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_market_anomaly_event_features_enforce_as_of_and_first_seen_boundaries(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_market_anomaly_records(
        tmp_path,
        [
            _market_anomaly_record(
                "BTCUSDT",
                "2026-06-01T01:00:00Z",
                first_seen_at="2026-06-01T01:05:00Z",
                title="BTCUSDT volume spike",
            ),
            _market_anomaly_record(
                "BTCUSDT",
                "2026-06-01T02:00:00Z",
                first_seen_at="2026-06-02T00:00:00Z",
                title="BTCUSDT late-seen volume spike",
            ),
        ],
    )

    result = build_market_anomaly_feature_input(
        config_path,
        identity={"symbol": "BTCUSDT"},
        start="2026-06-01T00:00:00Z",
        end="2026-06-02T00:00:00Z",
        as_of="2026-06-01T12:00:00Z",
    )

    assert result["status"] == "available"
    assert result["feature_source"] == "strategy_event_features"
    assert result["record_count"] == 1
    assert result["matched_record_count"] == 1
    assert result["records"][0]["record_type"] == "strategy_event_feature_record"
    assert result["records"][0]["event_time"] == "2026-06-01T01:00:00Z"
    assert result["records"][0]["first_seen_at"] == "2026-06-01T01:05:00Z"
    json.dumps(result)


def test_event_window_contexts_exclude_future_observed_events_from_lookback_features(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_market_anomaly_records(
        tmp_path,
        [
            _market_anomaly_record("BTCUSDT", "2026-06-01T01:00:00Z", title="BTCUSDT first anomaly"),
            _market_anomaly_record("BTCUSDT", "2026-06-01T03:00:00Z", title="BTCUSDT future anomaly"),
        ],
    )
    feature = build_market_anomaly_feature_input(
        config_path,
        identity={"symbol": "BTCUSDT"},
        start="2026-06-01T00:00:00Z",
        end="2026-06-02T00:00:00Z",
        as_of="2026-06-02T00:00:00Z",
    )

    contexts = event_window_contexts(
        ["2026-06-01T02:00:00Z"],
        feature,
        window_seconds=24 * 3600,
        direction="lookback",
    )

    assert contexts[0]["status"] == "available"
    assert contexts[0]["event_count"] == 1
    assert contexts[0]["records"][0]["title"] == "BTCUSDT first anomaly"


def test_macro_calendar_event_features_support_scheduled_events_ahead_of_bar(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_macro_calendar_records(
        tmp_path,
        [
            _macro_calendar_record(
                scheduled_at="2026-06-02T12:30:00Z",
                source_published_at="2026-06-01T06:00:00Z",
                first_seen_at="2026-06-01T06:05:00Z",
            )
        ],
    )
    feature = build_event_feature_input(
        config_path,
        data_type="macro_calendar",
        identity={"region": "US"},
        start="2026-06-01T00:00:00Z",
        end="2026-06-03T00:00:00Z",
        as_of="2026-06-01T12:00:00Z",
    )

    contexts = event_window_contexts(
        ["2026-06-01T12:00:00Z", "2026-06-01T00:00:00Z"],
        feature,
        window_seconds=48 * 3600,
        direction="lookahead",
    )

    assert feature["status"] == "available"
    assert feature["records"][0]["event_time"] == "2026-06-02T12:30:00Z"
    assert contexts[0]["event_count"] == 1
    assert contexts[0]["records"][0]["title"] == "US CPI"
    assert contexts[1]["event_count"] == 0


def test_event_feature_input_marks_missing_coverage_explicitly(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)

    result = build_market_anomaly_feature_input(
        config_path,
        identity={"symbol": "BTCUSDT"},
        start="2026-06-01T00:00:00Z",
        end="2026-06-02T00:00:00Z",
    )
    contexts = event_count_filter_contexts(
        ["2026-06-01T12:00:00Z"],
        result,
        window_seconds=24 * 3600,
        min_event_count=1,
    )

    assert result["status"] == "unavailable"
    assert "unknown_collection_coverage" in {item["code"] for item in result["warnings"]}
    assert "event_feature_unavailable" in {item["code"] for item in result["warnings"]}
    assert contexts[0]["suppressed"] is True
    assert contexts[0]["suppression_reason"] == "missing_event_feature"


def test_event_feature_input_marks_collected_no_data_as_empty(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    write_collection_coverage_state(
        config_path,
        [
            {
                "data_type": "market_anomaly",
                "source": "halpha_monitor_rules",
                "identity": {"symbol": "BTCUSDT"},
                "range_start": "2026-06-01T00:00:00Z",
                "range_end": "2026-06-02T00:00:00Z",
                "status": "no_data",
                "record_count": 0,
                "attempt_count": 1,
                "latest_attempt_at": "2026-06-02T00:00:00Z",
                "latest_success_at": "2026-06-02T00:00:00Z",
            }
        ],
    )

    result = build_market_anomaly_feature_input(
        config_path,
        identity={"symbol": "BTCUSDT"},
        start="2026-06-01T00:00:00Z",
        end="2026-06-02T00:00:00Z",
    )
    contexts = event_count_filter_contexts(
        ["2026-06-01T12:00:00Z"],
        result,
        window_seconds=24 * 3600,
        min_event_count=1,
    )

    assert result["status"] == "empty"
    assert result["record_count"] == 0
    assert result["warnings"] == []
    assert contexts[0]["status"] == "empty"
    assert contexts[0]["suppressed"] is False
    assert contexts[0]["suppression_reason"] is None


def test_event_feature_input_filters_categories_keywords_and_bounds_output(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_market_anomaly_records(
        tmp_path,
        [
            _market_anomaly_record("DOGEUSDT", "2026-06-01T01:00:00Z", title="DOGEUSDT volume spike"),
            _market_anomaly_record("DOGEUSDT", "2026-06-01T02:00:00Z", title="DOGEUSDT volume spike again"),
            _market_anomaly_record("BTCUSDT", "2026-06-01T03:00:00Z", title="BTCUSDT spread anomaly"),
        ],
    )

    result = build_market_anomaly_feature_input(
        config_path,
        start="2026-06-01T00:00:00Z",
        end="2026-06-02T00:00:00Z",
        as_of="2026-06-02T00:00:00Z",
        categories=["volume_spike"],
        keywords=["doge"],
        limit=2,
    )

    assert result["status"] == "partial"
    assert result["record_count"] == 2
    assert result["matched_record_count"] == 3
    assert result["filtered_out_record_count"] == 0
    assert all(record["symbol"] == "DOGEUSDT" for record in result["records"])
    assert "query_result_truncated" in {item["code"] for item in result["warnings"]}


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text("run:\n  output_dir: runs\n", encoding="utf-8")
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


def _write_macro_calendar_records(tmp_path: Path, records: list[dict[str, Any]]) -> None:
    path = (
        tmp_path
        / "data"
        / "macro"
        / "calendar"
        / "source=public_calendar"
        / "data_class=economic_release"
        / "region=US"
        / "records.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, records)


def _market_anomaly_record(
    symbol: str,
    observed_at: str,
    *,
    first_seen_at: str | None = None,
    title: str,
) -> dict[str, Any]:
    first_seen_at = first_seen_at or observed_at
    return {
        "history_key": f"volume_spike|{symbol}|1m|{observed_at}|volume|up",
        "anomaly_id": f"anomaly:{symbol}:{observed_at}",
        "dedupe_key": f"{symbol}:volume_spike:{observed_at}",
        "source_kind": "halpha_monitor_rule",
        "source": "halpha_monitor_rules",
        "source_kinds": ["halpha_monitor_rule"],
        "sources": ["halpha_monitor_rules"],
        "source_records": [
            {
                "source_kind": "halpha_monitor_rule",
                "source": "halpha_monitor_rules",
                "anomaly_id": f"anomaly:{symbol}:{observed_at}",
                "first_seen_at": first_seen_at,
            }
        ],
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


def _macro_calendar_record(
    *,
    scheduled_at: str,
    source_published_at: str,
    first_seen_at: str,
) -> dict[str, Any]:
    return {
        "history_key": f"public_calendar|economic_release|US|US CPI|{scheduled_at}",
        "item_id": f"macro:{scheduled_at}",
        "data_class": "economic_release",
        "source": "public_calendar",
        "event_name": "US CPI",
        "event_type": "inflation",
        "region": "US",
        "affected_assets": ["BTCUSDT"],
        "scheduled_at": scheduled_at,
        "source_timezone": "UTC",
        "importance": "high",
        "source_published_at": source_published_at,
        "endpoint": "public_calendar",
        "metrics": {},
        "units": {},
        "raw_fields": {},
        "payload_signature": scheduled_at,
        "origin_run_ids": ["run-1"],
        "first_seen_run_id": "run-1",
        "last_seen_run_id": "run-1",
        "first_seen_at": first_seen_at,
        "last_seen_at": first_seen_at,
        "status": "active",
        "warnings": [],
        "errors": [],
        "source_artifacts": ["runs/run-1/raw/macro_calendar.json"],
    }
