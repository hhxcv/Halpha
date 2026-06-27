from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import pyarrow.parquet as pq

from halpha.pipeline import RunContext
from halpha.text.text_event_history import write_text_event_history


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_text_event_history_appends_records_and_updates_manifest(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    run = _run_context(tmp_path, config_path, "run-1")

    artifacts = write_text_event_history(_config(), run, [_event_record("event-1")], now="2026-06-05T00:00:00Z")

    state = _state(tmp_path)
    records = _history_records(tmp_path)
    record = records[0]

    assert artifacts == ["data/research/metadata/text_event_history_state.json"]
    assert state["schema_version"] == 2
    assert state["status"] == "ok"
    assert state["totals"]["records"] == 1
    assert record["raw_item_id"] == "text:coindesk:event-1"
    assert record["source"] == "coindesk"
    assert record["origin_run_ids"] == ["run-1"]
    assert record["source_artifacts"] == [
        "runs/run-1/analysis/text_event_records.json",
        "runs/run-1/raw/text_events.json",
    ]
    assert run.manifest["artifacts"]["text_event_history_state"] == (
        "data/research/metadata/text_event_history_state.json"
    )
    assert run.manifest["counts"]["text_event_history_records"] == 1


def test_text_event_history_deduplicates_repeated_events_with_run_traceability(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    first_run = _run_context(tmp_path, config_path, "run-1")
    second_run = _run_context(tmp_path, config_path, "run-2")

    write_text_event_history(_config(), first_run, [_event_record("event-1")], now="2026-06-05T00:00:00Z")
    write_text_event_history(_config(), second_run, [_event_record("event-1")], now="2026-06-06T00:00:00Z")

    state = _state(tmp_path)
    records = _history_records(tmp_path)

    assert state["totals"]["records"] == 1
    assert state["totals"]["duplicate_records"] == 1
    assert state["totals"]["updated_records"] == 1
    assert records[0]["origin_run_ids"] == ["run-1", "run-2"]
    assert records[0]["first_seen_run_id"] == "run-1"
    assert records[0]["last_seen_run_id"] == "run-2"


def test_text_event_history_warns_on_conflicting_duplicate_content(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    first_run = _run_context(tmp_path, config_path, "run-1")
    second_run = _run_context(tmp_path, config_path, "run-2")

    write_text_event_history(_config(), first_run, [_event_record("event-1", text="Bitcoin ETF inflows rise")])
    write_text_event_history(_config(), second_run, [_event_record("event-1", text="Different content")])

    state = _state(tmp_path)
    record = _history_records(tmp_path)[0]

    assert state["status"] == "warning"
    assert state["totals"]["conflicting_duplicates"] == 1
    assert "conflicting duplicate text event:" in state["warnings"][0]
    assert record["status"] == "warning"
    assert record["origin_run_ids"] == ["run-1", "run-2"]
    assert record["same_event_group_id"] is None
    assert state["totals"]["same_event_groups"] == 0


def test_text_event_history_groups_source_preserving_near_duplicates(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    first_run = _run_context(tmp_path, config_path, "run-1")
    second_run = _run_context(tmp_path, config_path, "run-2")
    first_records = [
        _event_record(
            "btc-1",
            source_name="coindesk",
            title="Bitcoin ETF inflows accelerate",
            text="Bitcoin ETF inflows accelerated after issuers reported strong demand.",
            link="https://example.com/coindesk/btc-etf-inflows",
            published_at="2026-06-05T00:30:00Z",
        ),
        _event_record(
            "btc-2",
            source_name="the-block",
            title="BTC ETF inflows accelerate as demand rises",
            text="BTC ETF inflows accelerated after issuers reported strong demand.",
            link="https://example.com/the-block/btc-etf-demand",
            published_at="2026-06-05T02:00:00Z",
            collected_at="2026-06-05T02:01:00Z",
        ),
    ]

    write_text_event_history(_config(), first_run, first_records, now="2026-06-05T03:00:00Z")
    first_group_id = _state(tmp_path)["same_event_groups"][0]["same_event_group_id"]
    write_text_event_history(_config(), second_run, list(reversed(first_records)), now="2026-06-06T00:00:00Z")

    state = _state(tmp_path)
    records = _history_records(tmp_path)
    group = state["same_event_groups"][0]

    assert state["totals"]["records"] == 2
    assert state["totals"]["duplicate_records"] == 2
    assert state["totals"]["same_event_groups"] == 1
    assert state["totals"]["same_event_grouped_records"] == 2
    assert state["totals"]["same_event_candidate_pairs"] == 0
    assert group["same_event_group_id"] == first_group_id
    assert group["method"] == "near_duplicate_rule"
    assert group["score_bucket"] == "high"
    assert group["source_count"] == 2
    assert group["sources"] == ["coindesk", "the-block"]
    assert group["first_seen_at"] == "2026-06-05T00:31:00Z"
    assert group["last_seen_at"] == "2026-06-05T02:01:00Z"
    assert group["record_ids"] == sorted(record["stable_event_key"] for record in records)
    assert group["decisions"][0]["relationship"] == "same_event"
    assert "source_diversity_met" in group["decisions"][0]["reasons"]
    assert "time_window_met" in group["decisions"][0]["reasons"]
    assert sorted(record["source"] for record in records) == ["coindesk", "the-block"]
    assert {record["canonical_url"] for record in records} == {
        "https://example.com/coindesk/btc-etf-inflows",
        "https://example.com/the-block/btc-etf-demand",
    }
    assert {record["same_event_group_id"] for record in records} == {group["same_event_group_id"]}
    assert {record["same_event_group_method"] for record in records} == {"near_duplicate_rule"}
    assert {record["same_event_group_score_bucket"] for record in records} == {"high"}
    assert all(record["origin_run_ids"] == ["run-1", "run-2"] for record in records)


def test_text_event_history_keeps_similar_events_separate_outside_time_window(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    run = _run_context(tmp_path, config_path, "run-1")

    write_text_event_history(
        _config(),
        run,
        [
            _event_record(
                "btc-1",
                source_name="coindesk",
                title="Bitcoin ETF inflows accelerate",
                text="Bitcoin ETF inflows accelerated after issuers reported strong demand.",
                link="https://example.com/coindesk/btc-etf-inflows",
                published_at="2026-06-05T00:30:00Z",
            ),
            _event_record(
                "btc-2",
                source_name="the-block",
                title="BTC ETF inflows accelerate as demand rises",
                text="BTC ETF inflows accelerated after issuers reported strong demand.",
                link="https://example.com/the-block/btc-etf-demand",
                published_at="2026-06-12T02:00:00Z",
                collected_at="2026-06-12T02:01:00Z",
            ),
        ],
        now="2026-06-12T03:00:00Z",
    )

    state = _state(tmp_path)
    records = _history_records(tmp_path)
    candidate = state["same_event_group_candidates"][0]

    assert state["totals"]["same_event_groups"] == 0
    assert state["totals"]["same_event_grouped_records"] == 0
    assert state["totals"]["same_event_candidate_pairs"] == 1
    assert candidate["relationship"] == "separate"
    assert candidate["score_bucket"] == "high"
    assert "outside_same_event_time_window" in candidate["reasons"]
    assert {record["same_event_group_id"] for record in records} == {None}


def test_text_event_history_keeps_directional_conflict_separate(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    run = _run_context(tmp_path, config_path, "run-1")

    write_text_event_history(
        _config(),
        run,
        [
            _event_record(
                "btc-1",
                source_name="coindesk",
                title="Bitcoin ETF inflows accelerate",
                text="Bitcoin ETF inflows accelerated after issuers reported strong demand.",
                link="https://example.com/coindesk/btc-etf-inflows",
                published_at="2026-06-05T00:30:00Z",
            ),
            _event_record(
                "btc-2",
                source_name="the-block",
                title="Bitcoin ETF outflows accelerate",
                text="Bitcoin ETF outflows accelerated after issuers reported weak demand.",
                link="https://example.com/the-block/btc-etf-outflows",
                published_at="2026-06-05T02:00:00Z",
                collected_at="2026-06-05T02:01:00Z",
            ),
        ],
        now="2026-06-05T03:00:00Z",
    )

    state = _state(tmp_path)
    candidate = state["same_event_group_candidates"][0]

    assert state["same_event_groups"] == []
    assert state["totals"]["same_event_grouped_records"] == 0
    assert candidate["relationship"] == "separate"
    assert candidate["score_bucket"] == "medium"
    assert "directional_term_conflict" in candidate["reasons"]


def test_text_event_history_records_malformed_timestamps_and_no_record_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    run = _run_context(tmp_path, config_path, "run-1")

    write_text_event_history(
        _config(),
        run,
        [_event_record("event-1", published_at="not-a-time", collected_at=None)],
        now="2026-06-05T00:00:00Z",
    )
    malformed_state = _state(tmp_path)
    malformed_record = _history_records(tmp_path)[0]

    assert malformed_state["status"] == "warning"
    assert "published_at is not a valid ISO 8601 timestamp" in malformed_state["warnings"][0]
    assert malformed_record["published_at"] is None
    assert malformed_record["first_seen_at"] == "2026-06-05T00:00:00Z"

    empty_run = _run_context(tmp_path / "empty", tmp_path / "empty" / "config.yaml", "run-empty")
    empty_run.config_path.write_text("run:\n  output_dir: runs\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path / "empty")
    write_text_event_history(_config(), empty_run, [], now="2026-06-05T00:00:00Z")
    assert _state(tmp_path / "empty")["status"] == "skipped"


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text("run:\n  output_dir: runs\n", encoding="utf-8")
    return path


def _config() -> dict[str, Any]:
    return {"text": {"enabled": True}}


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


def _event_record(
    raw_id: str,
    *,
    source_name: str = "coindesk",
    title: str = "Bitcoin market event",
    text: str = "Bitcoin ETF inflows rise",
    link: str = "https://example.com/bitcoin-etf",
    canonical_url: str | None = None,
    published_at: str | None = "2026-06-05T00:30:00Z",
    collected_at: str | None = "2026-06-05T00:31:00Z",
) -> dict[str, Any]:
    canonical_url = canonical_url or link
    return {
        "event_id": f"text_event:{source_name}:{raw_id}",
        "raw_item_id": f"text:{source_name}:{raw_id}",
        "input_type": "rss_item",
        "source": {"name": source_name, "url": f"https://example.com/{source_name}/rss"},
        "title": title,
        "content_text": text,
        "link": link,
        "canonical_url": canonical_url,
        "published_at": published_at,
        "collected_at": collected_at,
        "language": "en",
        "normalized_title": title.lower(),
        "normalized_text": text.lower(),
        "warnings": [],
        "source_artifacts": ["raw/text_events.json"],
    }


def _state(tmp_path: Path) -> dict[str, Any]:
    return json.loads(
        (tmp_path / "data" / "research" / "metadata" / "text_event_history_state.json").read_text(
            encoding="utf-8"
        )
    )


def _history_records(tmp_path: Path) -> list[dict[str, Any]]:
    records = []
    for parquet_file in sorted((tmp_path / "data" / "research" / "text_events").rglob("*.parquet")):
        records.extend(pq.ParquetFile(parquet_file).read().to_pylist())
    return sorted(records, key=lambda record: record["stable_event_key"])
