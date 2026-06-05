from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from urllib.error import URLError

from halpha.config import load_config
from halpha.pipeline import run_pipeline


def test_pipeline_collects_rss_text_events_and_writes_raw_artifact(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    requested_urls: list[str] = []

    def fake_urlopen(request, timeout):
        requested_urls.append(request.full_url)
        return _FakeResponse(
            b"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <item>
      <title>Bitcoin market event</title>
      <link>https://example.com/bitcoin-event</link>
      <guid>event-1</guid>
      <pubDate>Fri, 05 Jun 2026 00:30:00 GMT</pubDate>
      <description><![CDATA[<p>Source-provided <b>event</b> text.</p>]]></description>
    </item>
    <item>
      <title>Second event should be clipped</title>
      <link>https://example.com/second-event</link>
      <guid>event-2</guid>
      <pubDate>Fri, 05 Jun 2026 00:31:00 GMT</pubDate>
      <description>Second source text.</description>
    </item>
  </channel>
</rss>
"""
        )

    monkeypatch.setattr("halpha.collectors.text.urlopen", fake_urlopen)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={"collect_market_data": _collect_market_data},
    )

    assert result.succeeded is False
    assert result.failed_stage == "build_analysis_materials"
    assert requested_urls == ["https://www.coindesk.com/arc/outboundfeeds/rss/"]

    raw = json.loads((result.run.raw_dir / "text_events.json").read_text(encoding="utf-8"))
    raw_text = json.dumps(raw, ensure_ascii=False).lower()
    assert "manually written" not in raw_text
    assert "manually curated" not in raw_text
    assert raw["schema_version"] == 1
    assert raw["artifact_type"] == "text_events_raw"
    assert raw["collector"] == "text"
    assert raw["collection_method"] == "rss"
    assert raw["sources"] == [
        {
            "name": "coindesk",
            "type": "rss",
            "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        }
    ]
    assert raw["errors"] == []
    assert raw["items"] == [
        {
            "id": f"text:coindesk:{sha256(b'event-1').hexdigest()[:16]}",
            "type": "rss_item",
            "title": "Bitcoin market event",
            "published_at": "2026-06-05T00:30:00Z",
            "source": {
                "name": "coindesk",
                "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
            },
            "link": "https://example.com/bitcoin-event",
            "content_text": "Source-provided event text.",
            "language": None,
        }
    ]

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifacts"]["raw_text_events"] == "raw/text_events.json"
    assert manifest["counts"]["text_event_items"] == 1
    assert manifest["stages"][1]["name"] == "collect_text_events"
    assert manifest["stages"][1]["status"] == "succeeded"
    assert manifest["stages"][1]["artifacts"] == ["raw/text_events.json"]


def test_text_collection_all_feed_failure_writes_error_artifact_without_fake_records(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_config(tmp_path, second_source=True)
    config = load_config(config_path)

    def failing_urlopen(request, timeout):
        raise URLError("network unreachable")

    monkeypatch.setattr("halpha.collectors.text.urlopen", failing_urlopen)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={"collect_market_data": _collect_market_data},
    )

    assert result.succeeded is False
    assert result.failed_stage == "collect_text_events"
    assert result.exit_code == 3
    assert "network unreachable" in result.reason

    raw = json.loads((result.run.raw_dir / "text_events.json").read_text(encoding="utf-8"))
    assert raw["items"] == []
    assert raw["errors"] == [
        {
            "source": "coindesk",
            "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
            "message": "RSS request failed: network unreachable",
        },
        {
            "source": "cointelegraph",
            "url": "https://cointelegraph.com/rss",
            "message": "RSS request failed: network unreachable",
        },
    ]

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifacts"]["raw_text_events"] == "raw/text_events.json"
    assert manifest["counts"]["text_event_items"] == 0
    assert manifest["stages"][1]["status"] == "failed"
    assert manifest["stages"][1]["artifacts"] == ["raw/text_events.json"]
    assert manifest["stages"][1]["error"] == manifest["errors"][0]
    assert "coindesk: RSS request failed: network unreachable" in manifest["errors"][0]["message"]
    assert "cointelegraph: RSS request failed: network unreachable" in manifest["errors"][0]["message"]
    assert not (result.run.analysis_dir / "text_material.md").exists()
    assert not (result.run.report_dir / "report.md").exists()


def _write_config(tmp_path: Path, *, second_source: bool = False) -> Path:
    source_block = """
    - name: coindesk
      type: rss
      url: https://www.coindesk.com/arc/outboundfeeds/rss/
"""
    if second_source:
        source_block += """    - name: cointelegraph
      type: rss
      url: https://cointelegraph.com/rss
"""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
run:
  output_dir: runs
  timezone: Asia/Shanghai
market:
  enabled: true
  source: binance
  symbols:
    - BTCUSDT
text:
  enabled: true
  max_items: 1
  sources:
{source_block.rstrip()}
report:
  title: Daily Market Brief
  language: zh-CN
codex:
  enabled: true
  command: codex
  args:
    - exec
    - --sandbox
    - read-only
    - "-"
  timeout_seconds: 300
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _collect_market_data(config, run) -> list[str]:
    return []


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self.payload
