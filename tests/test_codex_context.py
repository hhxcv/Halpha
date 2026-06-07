from __future__ import annotations

import json
from pathlib import Path

from halpha.config import load_config
from halpha.pipeline import run_pipeline
from halpha.storage import write_json


def test_pipeline_generates_codex_context_and_prompt_artifacts(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _write_market_raw,
            "collect_text_events": _write_text_raw,
            "run_codex_report": _skip_codex_report,
        },
    )

    assert result.succeeded is True
    assert result.failed_stage is None

    context = (result.run.codex_context_dir / "context.md").read_text(encoding="utf-8")
    assert "# codex_context" in context
    assert "raw_market: raw/market.json" in context
    assert "raw_text_events: raw/text_events.json" in context
    assert "market_material: analysis/market_material.md" in context
    assert "text_material: analysis/text_material.md" in context
    assert "research_context: analysis/research_context.md" in context
    assert "codex_context: codex_context/context.md" in context
    assert "codex_prompt: codex_context/prompt.md" in context
    assert '<embed path="analysis/research_context.md">' in context
    assert "artifact_type: research_context" in context
    assert "content_text: Source-provided event text." in context

    prompt = (result.run.codex_context_dir / "prompt.md").read_text(encoding="utf-8")
    assert "Generate a Simplified Chinese Markdown market intelligence report" in prompt
    assert "Use Chinese section headings only." in prompt
    assert "Do not invent prices, events, links, sources, or certainty." in prompt
    assert "Preserve source awareness." in prompt
    assert "Distinguish facts, assumptions, uncertainties, and judgment." in prompt
    assert "Use cautious language for market interpretation." in prompt
    assert "Include a risk notice." in prompt
    assert "not financial advice" in prompt
    assert "Do not modify repository files" in prompt
    assert "<context>" in prompt
    assert "# codex_context" in prompt
    assert "artifact_type: research_context" in prompt
    assert "- 核心摘要" in prompt
    assert "- Market Overview" not in prompt

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifacts"]["codex_context"] == "codex_context/context.md"
    assert manifest["artifacts"]["codex_prompt"] == "codex_context/prompt.md"
    codex_context_stage = _stage(manifest, "build_codex_context")
    report_stage = _stage(manifest, "run_codex_report")
    assert codex_context_stage["status"] == "succeeded"
    assert codex_context_stage["artifacts"] == [
        "codex_context/context.md",
        "codex_context/prompt.md",
    ]
    assert report_stage["status"] == "succeeded"


def test_codex_context_fails_when_research_context_is_missing(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _write_market_raw,
            "collect_text_events": _write_text_raw,
            "build_research_context": _skip_research_context,
        },
    )

    assert result.succeeded is False
    assert result.failed_stage == "build_codex_context"
    assert result.reason == "analysis/research_context.md was not found; build_research_context must run first."
    assert not (result.run.codex_context_dir / "context.md").exists()
    assert not (result.run.codex_context_dir / "prompt.md").exists()

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert _stage(manifest, "build_codex_context")["status"] == "failed"
    assert manifest["errors"] == [
        {
            "stage": "build_codex_context",
            "message": "analysis/research_context.md was not found; build_research_context must run first.",
        }
    ]


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
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
    - name: coindesk
      type: rss
      url: https://www.coindesk.com/arc/outboundfeeds/rss/
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


def _write_market_raw(config, run) -> list[str]:
    write_json(
        run.raw_dir / "market.json",
        {
            "schema_version": 1,
            "artifact_type": "market_raw",
            "collector": "market",
            "collection_method": "public_http",
            "source": {
                "name": "binance",
                "url": "https://data-api.binance.vision",
            },
            "collected_at": "2026-06-05T00:30:00Z",
            "items": [
                {
                    "id": "market:binance:BTCUSDT:2026-06-05T00:30:00Z",
                    "symbol": "BTCUSDT",
                    "as_of": "2026-06-05T00:30:00Z",
                    "metrics": {
                        "price": "68000.00",
                        "change_24h_pct": "1.25",
                        "volume_24h": "123.45",
                        "quote_volume_24h": "8394600.00",
                    },
                    "source": {
                        "name": "binance",
                        "url": "https://data-api.binance.vision",
                    },
                }
            ],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["raw_market"] = "raw/market.json"
    run.manifest["counts"]["market_items"] = 1
    return ["raw/market.json"]


def _write_text_raw(config, run) -> list[str]:
    write_json(
        run.raw_dir / "text_events.json",
        {
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
            "items": [
                {
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
                    "language": None,
                }
            ],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["raw_text_events"] = "raw/text_events.json"
    run.manifest["counts"]["text_event_items"] = 1
    return ["raw/text_events.json"]


def _skip_research_context(config, run) -> list[str]:
    return []


def _skip_codex_report(config, run) -> list[str]:
    return []


def _stage(manifest: dict, name: str) -> dict:
    return next(stage for stage in manifest["stages"] if stage["name"] == name)
