from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from halpha.pipeline import RunContext
from halpha.text.text_event_history import write_text_event_history


def test_text_event_history_appends_records_and_updates_manifest(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    run = _run_context(tmp_path, config_path, "run-1")

    artifacts = write_text_event_history(_config(), run, [_event_record("event-1")], now="2026-06-05T00:00:00Z")

    state = _state(tmp_path)
    records = _history_records(tmp_path)
    record = records[0]

    assert artifacts == ["data/research/metadata/text_event_history_state.json"]
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


def test_text_event_history_records_malformed_timestamps_and_no_record_state(tmp_path: Path) -> None:
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
    text: str = "Bitcoin ETF inflows rise",
    published_at: str | None = "2026-06-05T00:30:00Z",
    collected_at: str | None = "2026-06-05T00:31:00Z",
) -> dict[str, Any]:
    return {
        "event_id": f"text_event:coindesk:{raw_id}",
        "raw_item_id": f"text:coindesk:{raw_id}",
        "input_type": "rss_item",
        "source": {"name": "coindesk", "url": "https://example.com/rss"},
        "title": "Bitcoin market event",
        "content_text": text,
        "link": "https://example.com/bitcoin-etf",
        "canonical_url": "https://example.com/bitcoin-etf",
        "published_at": published_at,
        "collected_at": collected_at,
        "language": "en",
        "normalized_title": "bitcoin market event",
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
