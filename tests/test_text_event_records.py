from __future__ import annotations

import json
from pathlib import Path

from halpha.config import load_config
from halpha.pipeline import run_pipeline
from halpha.storage import write_json


def test_pipeline_generates_normalized_text_event_records(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_text_event_records",
        stage_handlers={"collect_text_events": _write_complete_text_raw},
    )

    assert result.succeeded is True
    artifact = json.loads((result.run.analysis_dir / "text_event_records.json").read_text(encoding="utf-8"))
    record = artifact["records"][0]

    assert artifact["artifact_type"] == "text_event_records"
    assert artifact["source_artifacts"] == ["raw/text_events.json"]
    assert artifact["model_states"] == []
    assert artifact["coverage"] == {
        "raw_items": 1,
        "records": 1,
        "records_with_warnings": 0,
        "missing_canonical_url": 0,
        "missing_published_at": 0,
        "missing_language": 0,
    }
    assert record["event_id"].startswith("text_event:coindesk:")
    assert record["raw_item_id"] == "text:coindesk:event-1"
    assert record["input_type"] == "rss_item"
    assert record["source"] == {
        "name": "coindesk",
        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    }
    assert record["title"] == "Bitcoin market event"
    assert record["content_text"] == "Source-provided event text."
    assert record["link"] == "https://Example.com/article/?utm_source=newsletter&b=2&a=1#section"
    assert record["canonical_url"] == "https://example.com/article?a=1&b=2"
    assert record["published_at"] == "2026-06-05T00:30:00Z"
    assert record["collected_at"] == "2026-06-05T00:31:00Z"
    assert record["language"] == "en"
    assert record["normalized_title"] == "bitcoin market event"
    assert record["normalized_text"] == "bitcoin market event source provided event text"
    assert record["warnings"] == []
    assert record["source_artifacts"] == ["raw/text_events.json"]

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifacts"]["text_event_records"] == "analysis/text_event_records.json"
    assert manifest["counts"]["text_event_records"] == 1
    assert manifest["counts"]["text_event_records_with_warnings"] == 0
    assert manifest["counts"]["text_event_record_warnings"] == 0
    assert manifest["counts"]["text_event_record_errors"] == 0
    assert manifest["text_event_records"] == {
        "status": "succeeded",
        "records": 1,
        "warnings": 0,
        "errors": 0,
    }
    assert _stage(manifest, "build_text_event_records")["artifacts"] == [
        "analysis/text_event_records.json"
    ]


def test_text_event_records_preserve_missing_optional_fields_as_warnings(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_text_event_records",
        stage_handlers={"collect_text_events": _write_minimum_text_raw},
    )

    assert result.succeeded is True
    artifact = json.loads((result.run.analysis_dir / "text_event_records.json").read_text(encoding="utf-8"))
    record = artifact["records"][0]

    assert record["input_type"] is None
    assert record["source"] == {"name": "coindesk", "url": None}
    assert record["link"] is None
    assert record["canonical_url"] is None
    assert record["published_at"] is None
    assert record["collected_at"] is None
    assert record["language"] is None
    assert record["warnings"] == [
        "source.url is missing from raw/text_events.json.",
        "type is missing from raw/text_events.json.",
        "link is missing from raw/text_events.json.",
        "published_at is missing from raw/text_events.json.",
        "collected_at is missing from raw/text_events.json.",
        "language is missing from raw/text_events.json.",
    ]
    assert artifact["warnings"] == record["warnings"]
    assert artifact["coverage"]["records_with_warnings"] == 1
    assert artifact["coverage"]["missing_canonical_url"] == 1
    assert artifact["coverage"]["missing_published_at"] == 1
    assert artifact["coverage"]["missing_language"] == 1


def test_text_event_records_skip_when_text_disabled(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, text_enabled=False)
    config = load_config(config_path)

    result = run_pipeline(config, config_path=config_path, until_stage="build_text_event_records")

    assert result.succeeded is True
    assert not (result.run.analysis_dir / "text_event_records.json").exists()

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert "text_event_records" not in manifest["artifacts"]
    assert manifest["counts"]["text_event_records"] == 0
    assert manifest["text_event_records"]["status"] == "skipped"
    assert _stage(manifest, "build_text_event_records")["artifacts"] == []


def test_text_event_records_fail_when_raw_text_events_are_missing(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_text_event_records",
        stage_handlers={"collect_text_events": _skip_text_collection},
    )

    assert result.succeeded is False
    assert result.failed_stage == "build_text_event_records"
    assert result.reason == "raw/text_events.json was not found; collect_text_events must run first."
    assert not (result.run.analysis_dir / "text_event_records.json").exists()


def test_text_event_records_reject_invalid_raw_text_artifact(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_text_event_records",
        stage_handlers={"collect_text_events": _write_invalid_text_raw},
    )

    assert result.succeeded is False
    assert result.failed_stage == "build_text_event_records"
    assert result.reason == "raw/text_events.json is invalid: items[0].content_text is required."
    assert not (result.run.analysis_dir / "text_event_records.json").exists()


def _write_config(tmp_path: Path, *, text_enabled: bool = True) -> Path:
    config_path = tmp_path / "config.yaml"
    text_block = (
        """
text:
  enabled: true
  max_items: 1
  sources:
    - name: coindesk
      type: rss
      url: https://www.coindesk.com/arc/outboundfeeds/rss/
"""
        if text_enabled
        else """
text:
  enabled: false
"""
    )
    config_path.write_text(
        f"""
run:
  output_dir: runs
market:
  enabled: false
{text_block.rstrip()}
report:
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _write_complete_text_raw(config, run) -> list[str]:
    write_json(run.raw_dir / "text_events.json", _text_raw(_complete_item()))
    run.manifest["artifacts"]["raw_text_events"] = "raw/text_events.json"
    run.manifest["counts"]["text_event_items"] = 1
    return ["raw/text_events.json"]


def _write_minimum_text_raw(config, run) -> list[str]:
    raw = _text_raw(_minimum_item(), source_url=None)
    del raw["collected_at"]
    write_json(run.raw_dir / "text_events.json", raw)
    run.manifest["artifacts"]["raw_text_events"] = "raw/text_events.json"
    run.manifest["counts"]["text_event_items"] = 1
    return ["raw/text_events.json"]


def _skip_text_collection(config, run) -> list[str]:
    return []


def _write_invalid_text_raw(config, run) -> list[str]:
    item = _complete_item()
    del item["content_text"]
    write_json(run.raw_dir / "text_events.json", _text_raw(item))
    run.manifest["artifacts"]["raw_text_events"] = "raw/text_events.json"
    run.manifest["counts"]["text_event_items"] = 1
    return ["raw/text_events.json"]


def _stage(manifest: dict, name: str) -> dict:
    return next(stage for stage in manifest["stages"] if stage["name"] == name)


def _text_raw(
    item: dict,
    *,
    source_url: str | None = "https://www.coindesk.com/arc/outboundfeeds/rss/",
) -> dict:
    return {
        "schema_version": 1,
        "artifact_type": "text_events_raw",
        "collector": "text",
        "collection_method": "rss",
        "collected_at": "2026-06-05T00:31:00Z",
        "sources": [
            {
                "name": "coindesk",
                "type": "rss",
                "url": source_url,
            }
        ],
        "items": [item],
        "errors": [],
    }


def _complete_item() -> dict:
    return {
        "id": "text:coindesk:event-1",
        "type": "rss_item",
        "title": "Bitcoin market event",
        "published_at": "2026-06-05T00:30:00Z",
        "source": {
            "name": "coindesk",
            "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        },
        "link": "https://Example.com/article/?utm_source=newsletter&b=2&a=1#section",
        "content_text": "Source-provided event text.",
        "language": "en",
    }


def _minimum_item() -> dict:
    return {
        "id": "text:coindesk:event-1",
        "title": "Bitcoin market event",
        "published_at": None,
        "source": {
            "name": "coindesk",
            "url": None,
        },
        "link": None,
        "content_text": "Source-provided event text.",
    }
