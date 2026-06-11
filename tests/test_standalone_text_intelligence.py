from __future__ import annotations

import json
from pathlib import Path

from halpha.cli import main
from halpha.storage import write_json


def test_text_intel_processes_existing_raw_text_artifact(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path)
    input_path = tmp_path / "raw_text_events.json"
    output_dir = tmp_path / "text_intelligence"
    write_json(input_path, _raw_text_events(_complete_item()))

    exit_code = main(
        [
            "text-intel",
            "--config",
            str(config_path),
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    stdout = capsys.readouterr().out
    run_dir = _single_output_dir(output_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    records = json.loads((run_dir / "analysis" / "text_event_records.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert "Halpha text intelligence succeeded." in stdout
    assert "text_event_records: analysis/text_event_records.json" in stdout
    assert "text_event_classification_evidence: analysis/text_event_classification_evidence.json" in stdout
    assert "text_event_topics: analysis/text_event_topics.json" in stdout
    assert (run_dir / "raw" / "text_events.json").is_file()
    assert not (run_dir / "codex_context").exists()
    assert not (run_dir / "report").exists()
    assert records["records"][0]["raw_item_id"] == "text:coindesk:event-1"
    assert manifest["artifact_type"] == "text_intelligence_manifest"
    assert manifest["status"] == "succeeded"
    assert manifest["inputs"]["mode"] == "existing_raw_artifact"
    assert manifest["inputs"]["input"] == "raw_text_events.json"
    assert manifest["artifacts"] == {
        "manifest": "manifest.json",
        "raw_text_events": "raw/text_events.json",
        "text_event_classification_evidence": "analysis/text_event_classification_evidence.json",
        "text_entity_evidence": "analysis/text_entity_evidence.json",
        "text_event_records": "analysis/text_event_records.json",
        "text_event_topics": "analysis/text_event_topics.json",
    }
    assert manifest["counts"]["text_event_items"] == 1
    assert manifest["counts"]["text_event_records"] == 1
    assert manifest["counts"]["text_event_classification_records"] == 1
    assert manifest["counts"]["text_event_topics"] == 1
    assert manifest["counts"]["processors_succeeded"] == 5
    assert manifest["counts"]["processors_skipped"] == 3
    assert manifest["model_states"] == []
    assert _processor_statuses(manifest) == {
        "load_raw_text_events": "succeeded",
        "build_text_event_records": "succeeded",
        "build_text_entity_evidence": "succeeded",
        "build_text_event_classification_evidence": "succeeded",
        "build_text_event_topics": "succeeded",
        "build_text_event_signals": "skipped",
        "build_event_market_confluence": "skipped",
        "build_event_intelligence_material": "skipped",
    }


def test_text_intel_collects_configured_text_sources(tmp_path: Path, capsys, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    output_dir = tmp_path / "text_intelligence"
    requested_urls: list[str] = []

    def fake_urlopen(request, timeout):
        requested_urls.append(request.full_url)
        return _BytesResponse(_rss_payload())

    monkeypatch.setattr("halpha.collectors.text.urlopen", fake_urlopen)

    exit_code = main(["text-intel", "--config", str(config_path), "--output-dir", str(output_dir)])

    stdout = capsys.readouterr().out
    run_dir = _single_output_dir(output_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    raw = json.loads((run_dir / "raw" / "text_events.json").read_text(encoding="utf-8"))
    records = json.loads((run_dir / "analysis" / "text_event_records.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert requested_urls == ["https://example.com/feed.xml"]
    assert "Halpha text intelligence succeeded." in stdout
    assert manifest["inputs"]["mode"] == "configured_sources"
    assert manifest["counts"]["text_event_items"] == 1
    assert manifest["counts"]["text_event_records"] == 1
    assert manifest["counts"]["text_event_classification_records"] == 1
    assert manifest["counts"]["text_event_topics"] == 1
    assert raw["items"][0]["title"] == "Bitcoin market event"
    assert records["records"][0]["normalized_title"] == "bitcoin market event"
    assert _processor_statuses(manifest)["collect_text_events"] == "succeeded"
    assert _processor_statuses(manifest)["build_text_entity_evidence"] == "succeeded"
    assert _processor_statuses(manifest)["build_text_event_classification_evidence"] == "succeeded"
    assert _processor_statuses(manifest)["build_text_event_topics"] == "succeeded"


def test_text_intel_rejects_invalid_input_without_fake_downstream_artifacts(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_config(tmp_path)
    input_path = tmp_path / "raw_text_events.json"
    output_dir = tmp_path / "text_intelligence"
    item = _complete_item()
    del item["content_text"]
    write_json(input_path, _raw_text_events(item))

    exit_code = main(
        [
            "text-intel",
            "--config",
            str(config_path),
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    stdout = capsys.readouterr().out
    run_dir = _single_output_dir(output_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))

    assert exit_code == 3
    assert "Halpha text intelligence failed." in stdout
    assert manifest["status"] == "failed"
    assert manifest["errors"][0]["stage"] == "load_raw_text_events"
    assert manifest["counts"]["processors_succeeded"] == 0
    assert manifest["counts"]["processors_skipped"] == 3
    assert "text_event_records" not in manifest["artifacts"]
    assert not (run_dir / "analysis" / "text_event_records.json").exists()


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  output_dir: runs
market:
  enabled: false
text:
  enabled: true
  max_items: 1
  sources:
    - name: test-feed
      type: rss
      url: https://example.com/feed.xml
report:
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _raw_text_events(item: dict) -> dict:
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
                "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
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
        "link": "https://example.com/bitcoin-event",
        "content_text": "Source-provided event text.",
        "language": "en",
    }


def _single_output_dir(output_dir: Path) -> Path:
    run_dirs = sorted(output_dir.iterdir())
    assert len(run_dirs) == 1
    return run_dirs[0]


def _processor_statuses(manifest: dict) -> dict[str, str]:
    return {processor["name"]: processor["status"] for processor in manifest["processors"]}


def _rss_payload() -> bytes:
    return b"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <item>
      <title>Bitcoin market event</title>
      <link>https://example.com/bitcoin-event?utm_source=test</link>
      <pubDate>Fri, 05 Jun 2026 00:30:00 GMT</pubDate>
      <description>Source-provided event text.</description>
    </item>
  </channel>
</rss>
"""


class _BytesResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return self.payload
