from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import pytest

from halpha.text.text_event_collection import collect_text_event_data


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_text_event_collect_dry_run_plans_without_writes(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)

    result = collect_text_event_data(
        _config(),
        config_path=config_path,
        source="coindesk",
        requested_start="2026-06-01T00:00:00Z",
        requested_end="2026-06-02T00:00:00Z",
        dry_run=True,
        raw_collector=_collector(_raw([_item()])),
        now="2026-06-05T00:00:00Z",
    )

    assert result["status"] == "ok"
    assert result["mode"] == "dry_run"
    assert result["data_type"] == "text_event"
    assert result["plan"]["strategy"] == "gap_only"
    assert result["counts"]["planned_fetch_windows"] == 1
    assert not (tmp_path / "data").exists()


def test_text_event_collect_apply_updates_history_coverage_and_catalog(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)

    result = collect_text_event_data(
        _config(),
        config_path=config_path,
        source="coindesk",
        requested_start="2026-06-01T00:00:00Z",
        requested_end="2026-06-02T00:00:00Z",
        dry_run=False,
        raw_collector=_collector(_raw([_item()])),
        now="2026-06-05T00:00:00Z",
    )

    state = _history_state(tmp_path)
    coverage = _coverage_state(tmp_path)
    catalog = _catalog(tmp_path)
    records = _history_records(tmp_path)

    assert result["status"] == "ok"
    assert result["counts"]["stored_records"] == 1
    assert result["artifacts"]["text_event_history_state"] == "data/research/metadata/text_event_history_state.json"
    assert state["totals"]["records"] == 1
    assert state["totals"]["incoming_records"] == 1
    assert records[0]["source"] == "coindesk"
    assert records[0]["published_at"] == "2026-06-01T12:00:00Z"
    assert coverage["counts"]["statuses"] == {"collected": 1}
    assert coverage["records"][0]["data_type"] == "text_event"
    assert coverage["records"][0]["identity"] == {"source_name": "coindesk"}
    assert catalog["stores"][0]["name"] == "text_event_history"
    assert catalog["stores"][0]["coverage_state"]["status_counts"] == {"collected": 1}


def test_text_event_collect_records_empty_success_as_no_data(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)

    result = collect_text_event_data(
        _config(),
        config_path=config_path,
        source="coindesk",
        requested_start="2026-06-01T00:00:00Z",
        requested_end="2026-06-02T00:00:00Z",
        dry_run=False,
        raw_collector=_collector(_raw([])),
        now="2026-06-05T00:00:00Z",
    )

    coverage = _coverage_state(tmp_path)

    assert result["status"] == "ok"
    assert result["counts"]["stored_records"] == 0
    assert coverage["counts"]["statuses"] == {"no_data": 1}
    assert coverage["records"][0]["latest_success_at"] == "2026-06-05T00:00:00Z"
    assert _history_state(tmp_path)["status"] == "skipped"


def test_text_event_collect_records_partial_source_failures(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, sources=["coindesk", "cointelegraph"])
    raw = _raw(
        [_item(source="coindesk")],
        sources=["coindesk", "cointelegraph"],
        errors=[{"source": "cointelegraph", "message": "timeout"}],
    )

    result = collect_text_event_data(
        _config(sources=["coindesk", "cointelegraph"]),
        config_path=config_path,
        source="all",
        requested_start="2026-06-01T00:00:00Z",
        requested_end="2026-06-02T00:00:00Z",
        dry_run=False,
        raw_collector=_collector(raw),
        now="2026-06-05T00:00:00Z",
    )

    coverage = _coverage_state(tmp_path)

    assert result["status"] == "warning"
    assert result["counts"]["stored_records"] == 1
    assert result["counts"]["raw_errors"] == 1
    assert coverage["records"][0]["status"] == "partial"
    assert coverage["records"][0]["identity"] == {"source_group": "all"}
    assert coverage["records"][0]["errors"] == [{"source": "cointelegraph", "message": "timeout"}]


def test_text_event_collect_blocks_unsupported_historical_apply(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)

    result = collect_text_event_data(
        _config(),
        config_path=config_path,
        source="coindesk",
        requested_start="2026-06-01T00:00:00Z",
        requested_end="2026-06-02T00:00:00Z",
        dry_run=False,
        raw_collector=_collector(_raw([_item()])),
        supports_historical=False,
        now="2026-06-05T00:00:00Z",
    )

    coverage = _coverage_state(tmp_path)

    assert result["status"] == "blocked"
    assert result["plan"]["strategy"] == "blocked"
    assert result["fetches"] == []
    assert coverage["records"][0]["status"] == "not_collected"
    assert coverage["records"][0]["errors"][0]["message"] == (
        "source does not support historical collection for the requested range."
    )


def test_text_event_collect_preserves_duplicate_history_on_partial_retry(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    partial_raw = _raw([_item()], errors=[{"source": "coindesk", "message": "temporary failure"}])

    collect_text_event_data(
        _config(),
        config_path=config_path,
        source="coindesk",
        requested_start="2026-06-01T00:00:00Z",
        requested_end="2026-06-02T00:00:00Z",
        dry_run=False,
        raw_collector=_collector(partial_raw),
        now="2026-06-05T00:00:00Z",
    )
    result = collect_text_event_data(
        _config(),
        config_path=config_path,
        source="coindesk",
        requested_start="2026-06-01T00:00:00Z",
        requested_end="2026-06-02T00:00:00Z",
        dry_run=False,
        raw_collector=_collector(_raw([_item()])),
        now="2026-06-06T00:00:00Z",
    )

    state = _history_state(tmp_path)
    records = _history_records(tmp_path)

    assert result["plan"]["strategy"] == "gap_only"
    assert state["totals"]["records"] == 1
    assert state["totals"]["duplicate_records"] == 1
    assert records[0]["origin_run_ids"] == [
        "text_event_data_collect:2026-06-05T00:00:00Z",
        "text_event_data_collect:2026-06-06T00:00:00Z",
    ]


def _write_config(tmp_path: Path, *, sources: list[str] | None = None) -> Path:
    config_path = tmp_path / "config.yaml"
    source_yaml = "\n".join(
        f"    - name: {source}\n      type: rss\n      url: https://example.com/{source}.xml"
        for source in (sources or ["coindesk"])
    )
    config_path.write_text(
        f"""
run:
  output_dir: runs
text:
  enabled: true
  sources:
{source_yaml}
report:
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _config(*, sources: list[str] | None = None) -> dict[str, Any]:
    return {
        "text": {
            "enabled": True,
            "sources": [
                {
                    "name": source,
                    "type": "rss",
                    "url": f"https://example.com/{source}.xml",
                }
                for source in (sources or ["coindesk"])
            ],
        }
    }


def _collector(raw: dict[str, Any]):
    def _collect(text: dict[str, Any], now: str | None) -> dict[str, Any]:
        return raw

    return _collect


def _raw(
    items: list[dict[str, Any]],
    *,
    sources: list[str] | None = None,
    errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "text_events_raw",
        "collector": "text",
        "collection_method": "rss",
        "collected_at": "2026-06-01T12:10:00Z",
        "sources": [
            {"name": source, "type": "rss", "url": f"https://example.com/{source}.xml"}
            for source in (sources or ["coindesk"])
        ],
        "items": items,
        "errors": errors or [],
    }


def _item(*, source: str = "coindesk", published_at: str = "2026-06-01T12:00:00Z") -> dict[str, Any]:
    return {
        "id": "text:coindesk:event-1",
        "type": "rss_item",
        "title": "Bitcoin market event",
        "published_at": published_at,
        "source": {"name": source, "url": f"https://example.com/{source}.xml"},
        "link": "https://example.com/article?utm_source=newsletter&a=1",
        "content_text": "Bitcoin ETF inflows rise.",
        "language": "en",
    }


def _history_state(tmp_path: Path) -> dict[str, Any]:
    return json.loads(
        (tmp_path / "data" / "research" / "metadata" / "text_event_history_state.json").read_text(
            encoding="utf-8"
        )
    )


def _coverage_state(tmp_path: Path) -> dict[str, Any]:
    return json.loads(
        (tmp_path / "data" / "research" / "metadata" / "collection_coverage_state.json").read_text(
            encoding="utf-8"
        )
    )


def _catalog(tmp_path: Path) -> dict[str, Any]:
    return json.loads(
        (tmp_path / "data" / "research" / "metadata" / "research_data_catalog.json").read_text(
            encoding="utf-8"
        )
    )


def _history_records(tmp_path: Path) -> list[dict[str, Any]]:
    records = []
    for parquet_file in sorted((tmp_path / "data" / "research" / "text_events").rglob("*.parquet")):
        records.extend(pq.ParquetFile(parquet_file).read().to_pylist())
    return sorted(records, key=lambda record: record["stable_event_key"])
