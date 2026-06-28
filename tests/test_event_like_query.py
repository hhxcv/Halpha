from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from halpha.data.collection_coverage import write_collection_coverage_state
from halpha.data.event_like_query import (
    query_derivatives_market_records,
    query_event_like_records,
    query_macro_calendar_records,
    query_market_anomaly_records,
    query_onchain_flow_records,
    query_text_event_records,
)
from halpha.pipeline import RunContext
from halpha.storage import write_json
from halpha.text.text_event_history import write_text_event_history


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_text_event_query_enforces_as_of_and_preserves_group_metadata(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    run = _run_context(tmp_path, config_path, "run-1")
    write_text_event_history(
        {"text": {"enabled": True}},
        run,
        [
            _text_event(
                "btc-1",
                source_name="coindesk",
                title="Bitcoin ETF inflows accelerate",
                text="Bitcoin ETF inflows accelerated after issuers reported strong demand.",
                link="https://example.com/coindesk/btc-etf-inflows",
                published_at="2026-06-01T00:30:00Z",
                collected_at="2026-06-01T00:31:00Z",
            ),
            _text_event(
                "btc-2",
                source_name="the-block",
                title="BTC ETF inflows accelerate as demand rises",
                text="BTC ETF inflows accelerated after issuers reported strong demand.",
                link="https://example.com/the-block/btc-etf-demand",
                published_at="2026-06-01T01:00:00Z",
                collected_at="2026-06-01T01:01:00Z",
            ),
            _text_event(
                "late-1",
                source_name="coindesk",
                title="Bitcoin miner update",
                text="Bitcoin miners reported operational changes.",
                link="https://example.com/coindesk/miners",
                published_at="2026-06-01T01:30:00Z",
                collected_at="2026-06-03T00:00:00Z",
            ),
        ],
        now="2026-06-03T00:00:00Z",
    )

    result = query_text_event_records(
        config_path,
        start="2026-06-01T00:00:00Z",
        end="2026-06-02T00:00:00Z",
        as_of="2026-06-01T02:00:00Z",
    )

    assert result["data_type"] == "text_event"
    assert result["time_fields"]["range_field"] == "published_at"
    assert result["record_count"] == 2
    assert result["filter_diagnostics"]["as_of_excluded_record_count"] == 1
    assert [record["source"] for record in result["records"]] == ["coindesk", "the-block"]
    assert {record["same_event_group_method"] for record in result["records"]} == {"near_duplicate_rule"}
    assert {record["same_event_group_id"] for record in result["records"]} != {None}
    assert all(record["first_seen_at"] <= result["as_of"] for record in result["records"])
    assert "data/research/text_events" not in result["source_artifacts"]


def test_macro_calendar_query_filters_scheduled_events_known_by_as_of(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_history_records(
        tmp_path / "data" / "macro" / "calendar" / "source=federal_reserve_fomc"
        / "data_class=central_bank_event" / "region=US" / "records.json",
        [
            _macro_record("2026-06-10T00:00:00Z", first_seen_at="2026-05-30T00:00:00Z"),
            _macro_record("2026-06-11T00:00:00Z", first_seen_at="2026-05-30T00:00:00Z"),
            _macro_record("2026-06-12T00:00:00Z", first_seen_at="2026-06-02T00:00:00Z"),
        ],
    )

    result = query_macro_calendar_records(
        config_path,
        source="federal_reserve_fomc",
        identity={"data_class": "central_bank_event", "region": "US"},
        start="2026-06-10T00:00:00Z",
        end="2026-06-13T00:00:00Z",
        as_of="2026-06-01T00:00:00Z",
    )

    assert result["time_fields"]["range_field"] == "scheduled_at"
    assert result["record_count"] == 2
    assert result["filter_diagnostics"]["as_of_excluded_record_count"] == 1
    assert [record["scheduled_at"] for record in result["records"]] == [
        "2026-06-10T00:00:00Z",
        "2026-06-11T00:00:00Z",
    ]
    assert result["records"][0]["source_artifacts"] == ["runs/run-1/raw/macro_calendar.json"]


def test_onchain_query_applies_observation_as_of_limit_and_sort_order(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_history_records(
        tmp_path / "data" / "onchain" / "flow" / "source=defillama_stablecoins"
        / "data_class=stablecoin_supply" / "asset=ALL_STABLECOINS" / "chain=all" / "records.json",
        [
            _onchain_record("2026-06-01T00:00:00Z", value=1000.0),
            _onchain_record("2026-06-02T00:00:00Z", value=1100.0),
            _onchain_record("2026-06-03T00:00:00Z", value=1200.0),
        ],
    )

    result = query_onchain_flow_records(
        config_path,
        source="defillama_stablecoins",
        identity={"data_class": "stablecoin_supply", "asset": "ALL_STABLECOINS", "chain": "all"},
        start="2026-06-01T00:00:00Z",
        end="2026-06-04T00:00:00Z",
        as_of="2026-06-02T12:00:00Z",
        limit=1,
        sort_order="desc",
    )

    assert result["truncated"] is True
    assert result["matched_record_count"] == 2
    assert result["record_count"] == 1
    assert result["records"][0]["as_of"] == "2026-06-02T00:00:00Z"
    assert "query_result_truncated" in {warning["code"] for warning in result["warnings"]}


def test_derivatives_query_filters_observation_range_deterministically(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_history_records(
        tmp_path / "data" / "market" / "derivatives" / "source=binance_usdm"
        / "data_class=funding_rate" / "symbol=BTCUSDT" / "period=8h" / "records.json",
        [
            _derivatives_record("2026-06-17T16:00:00Z", funding_rate=0.0001),
            _derivatives_record("2026-06-18T00:00:00Z", funding_rate=0.0002),
            _derivatives_record("2026-06-19T00:00:00Z", funding_rate=0.0003),
        ],
    )

    result = query_derivatives_market_records(
        config_path,
        source="binance_usdm",
        identity={"data_class": "funding_rate", "symbol": "BTCUSDT", "period": "8h"},
        start="2026-06-17T00:00:00Z",
        end="2026-06-19T00:00:00Z",
        as_of="2026-06-18T00:00:00Z",
    )

    assert result["record_count"] == 2
    assert [record["as_of"] for record in result["records"]] == [
        "2026-06-17T16:00:00Z",
        "2026-06-18T00:00:00Z",
    ]
    assert result["range"] == {
        "time_field": "as_of",
        "start": "2026-06-17T16:00:00Z",
        "end": "2026-06-18T00:00:00Z",
    }


def test_market_anomaly_query_uses_observed_time_and_seen_as_of(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    _write_history_records(
        tmp_path / "data" / "market" / "anomalies" / "source_kind=halpha_rule"
        / "data_class=price_move" / "symbol=BTCUSDT" / "timeframe=1d" / "records.json",
        [
            _market_anomaly_record("2026-06-17T00:00:00Z", first_seen_at="2026-06-17T01:00:00Z"),
            _market_anomaly_record("2026-06-18T00:00:00Z", first_seen_at="2026-06-20T00:00:00Z"),
        ],
    )

    result = query_market_anomaly_records(
        config_path,
        identity={"data_class": "price_move", "symbol": "BTCUSDT", "timeframe": "1d"},
        start="2026-06-17T00:00:00Z",
        end="2026-06-19T00:00:00Z",
        as_of="2026-06-18T12:00:00Z",
    )

    assert result["time_fields"]["range_field"] == "observed_at"
    assert result["record_count"] == 1
    assert result["filter_diagnostics"]["as_of_excluded_record_count"] == 1
    assert result["records"][0]["observed_at"] == "2026-06-17T00:00:00Z"


def test_event_like_query_distinguishes_no_data_not_collected_and_unknown_coverage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    write_collection_coverage_state(
        config_path,
        [
            {
                "data_type": "text_event",
                "source": "coindesk",
                "identity": {"source_name": "coindesk"},
                "range_start": "2026-06-01T00:00:00Z",
                "range_end": "2026-06-02T00:00:00Z",
                "status": "no_data",
            },
            {
                "data_type": "onchain_flow",
                "source": "defillama_stablecoins",
                "identity": {"data_class": "stablecoin_supply", "asset": "ALL_STABLECOINS", "chain": "all"},
                "range_start": "2026-06-01T00:00:00Z",
                "range_end": "2026-06-02T00:00:00Z",
                "status": "not_collected",
            },
        ],
        now="2026-06-03T00:00:00Z",
    )

    no_data = query_text_event_records(
        config_path,
        source="coindesk",
        start="2026-06-01T00:00:00Z",
        end="2026-06-02T00:00:00Z",
    )
    not_collected = query_onchain_flow_records(
        config_path,
        source="defillama_stablecoins",
        identity={"data_class": "stablecoin_supply", "asset": "ALL_STABLECOINS", "chain": "all"},
        start="2026-06-01T00:00:00Z",
        end="2026-06-02T00:00:00Z",
    )
    missing_root = tmp_path / "missing"
    missing_root.mkdir()
    monkeypatch.chdir(missing_root)
    missing_config_path = missing_root / "config.yaml"
    missing_config_path.write_text("run:\n  output_dir: runs\n", encoding="utf-8")
    unknown = query_event_like_records(
        missing_config_path,
        data_type="derivatives_market",
        start="2026-06-01T00:00:00Z",
        end="2026-06-02T00:00:00Z",
    )

    assert no_data["status"] == "ok"
    assert no_data["empty_result_diagnostics"]["status"] == "no_data"
    assert no_data["coverage_diagnostics"]["status_counts"] == {"no_data": 1}
    assert not_collected["status"] == "warning"
    assert not_collected["empty_result_diagnostics"]["status"] == "incomplete_coverage"
    assert not_collected["coverage_diagnostics"]["not_collected_ranges"] == [
        {"range_start": "2026-06-01T00:00:00Z", "range_end": "2026-06-02T00:00:00Z"}
    ]
    assert "incomplete_collection_coverage" in {warning["code"] for warning in not_collected["warnings"]}
    assert unknown["coverage_diagnostics"]["status"] == "not_available"
    assert unknown["empty_result_diagnostics"]["status"] == "unknown_coverage"
    assert "unknown_collection_coverage" in {warning["code"] for warning in unknown["warnings"]}


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text("run:\n  output_dir: runs\n", encoding="utf-8")
    return path


def _run_context(tmp_path: Path, config_path: Path, run_id: str) -> RunContext:
    run_dir = tmp_path / "runs" / run_id
    raw_dir = run_dir / "raw"
    analysis_dir = run_dir / "analysis"
    codex_context_dir = run_dir / "codex_context"
    report_dir = run_dir / "report"
    for directory in (raw_dir, analysis_dir, codex_context_dir, report_dir):
        directory.mkdir(parents=True, exist_ok=True)
    return RunContext(
        run_id=run_id,
        run_dir=run_dir,
        raw_dir=raw_dir,
        analysis_dir=analysis_dir,
        codex_context_dir=codex_context_dir,
        report_dir=report_dir,
        manifest_path=run_dir / "run_manifest.json",
        config_path=config_path,
        manifest={"artifacts": {}, "counts": {}, "errors": []},
    )


def _write_history_records(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, records)


def _text_event(
    raw_id: str,
    *,
    source_name: str,
    title: str,
    text: str,
    link: str,
    published_at: str,
    collected_at: str,
) -> dict[str, Any]:
    return {
        "event_id": f"text_event:{source_name}:{raw_id}",
        "raw_item_id": f"text:{source_name}:{raw_id}",
        "input_type": "rss_item",
        "source": {"name": source_name, "url": f"https://example.com/{source_name}/rss"},
        "title": title,
        "content_text": text,
        "link": link,
        "canonical_url": link,
        "published_at": published_at,
        "collected_at": collected_at,
        "language": "en",
        "normalized_title": title.lower(),
        "normalized_text": text.lower(),
        "warnings": ["source warning"] if raw_id == "btc-1" else [],
        "source_artifacts": ["raw/text_events.json"],
    }


def _macro_record(scheduled_at: str, *, first_seen_at: str) -> dict[str, Any]:
    return {
        "history_key": f"federal_reserve_fomc|central_bank_event|US|FOMC decision|{scheduled_at}",
        "item_id": f"macro:{scheduled_at}",
        "data_class": "central_bank_event",
        "source": "federal_reserve_fomc",
        "event_name": "FOMC decision",
        "event_type": "rate_decision",
        "region": "US",
        "affected_assets": ["BTCUSDT"],
        "scheduled_at": scheduled_at,
        "source_timezone": "UTC",
        "importance": "high",
        "source_published_at": "2026-05-29T00:00:00Z",
        "endpoint": "https://example.com/calendar",
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


def _onchain_record(as_of: str, *, value: float) -> dict[str, Any]:
    return {
        "history_key": f"defillama_stablecoins|stablecoin_supply|ALL_STABLECOINS|all|{as_of}",
        "item_id": f"onchain:{as_of}",
        "data_class": "stablecoin_supply",
        "source": "defillama_stablecoins",
        "asset": "ALL_STABLECOINS",
        "chain": "all",
        "as_of": as_of,
        "endpoint": "https://example.com/stablecoins",
        "metrics": {"total_circulating_usd": value},
        "units": {"total_circulating_usd": "usd"},
        "raw_fields": {},
        "payload_signature": as_of,
        "origin_run_ids": ["run-1"],
        "first_seen_run_id": "run-1",
        "last_seen_run_id": "run-1",
        "first_seen_at": "2026-06-04T00:00:00Z",
        "last_seen_at": "2026-06-04T00:00:00Z",
        "status": "active",
        "warnings": [],
        "errors": [],
        "source_artifacts": ["runs/run-1/raw/onchain_flow.json"],
    }


def _derivatives_record(as_of: str, *, funding_rate: float) -> dict[str, Any]:
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
        "first_seen_at": "2026-06-19T00:00:00Z",
        "last_seen_at": "2026-06-19T00:00:00Z",
        "status": "active",
        "warnings": [],
        "errors": [],
        "source_artifacts": ["runs/run-1/raw/derivatives_market.json"],
    }


def _market_anomaly_record(observed_at: str, *, first_seen_at: str) -> dict[str, Any]:
    return {
        "history_key": f"price_move|BTCUSDT|1d|{observed_at}|close_return_pct|up",
        "anomaly_id": f"halpha:{observed_at}",
        "dedupe_key": f"price_move|BTCUSDT|1d|{observed_at}|close_return_pct|up",
        "source_kind": "halpha_rule",
        "source": "halpha_monitor_rules",
        "source_kinds": ["halpha_rule"],
        "sources": ["halpha_monitor_rules"],
        "source_records": [],
        "data_class": "price_move",
        "symbol": "BTCUSDT",
        "market_type": "spot",
        "timeframe": "1d",
        "observed_at": observed_at,
        "published_at": observed_at,
        "collected_at": first_seen_at,
        "first_seen_at": first_seen_at,
        "last_seen_at": first_seen_at,
        "severity": "medium",
        "direction": "up",
        "metric": "close_return_pct",
        "value": 10.0,
        "threshold": 5.0,
        "unit": "percent",
        "window_start": "2026-06-16T00:00:00Z",
        "window_end": observed_at,
        "title": "BTCUSDT 1d close return 10.00%",
        "summary": "BTCUSDT 1d close changed 10.00% from the previous candle.",
        "metrics": {"close_return_pct": 10.0},
        "units": {"close_return_pct": "percent"},
        "raw_fields": {},
        "payload_signature": "test",
        "origin_run_ids": ["run-1"],
        "first_seen_run_id": "run-1",
        "last_seen_run_id": "run-1",
        "status": "active",
        "warnings": [],
        "errors": [],
        "source_artifacts": ["runs/run-1/raw/market_anomalies.json"],
    }
