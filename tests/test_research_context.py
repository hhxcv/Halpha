from __future__ import annotations

import json
from pathlib import Path

from halpha.config import load_config
from halpha.pipeline import run_pipeline
from halpha.storage import write_json


def test_pipeline_generates_research_context_with_embedded_materials(tmp_path: Path) -> None:
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

    context = (result.run.analysis_dir / "research_context.md").read_text(encoding="utf-8")
    assert "artifact_type: research_context" in context
    assert "audience: codex_cli" in context
    assert "language_target: zh-CN" in context
    assert "raw_market: raw/market.json" in context
    assert "raw_text_events: raw/text_events.json" in context
    assert "market_material: analysis/market_material.md" in context
    assert "text_material: analysis/text_material.md" in context
    assert "## source_policy" in context
    assert "allowed_sources_only: true" in context
    assert "fabricate_missing_sources: false" in context
    assert "financial_advice: false" in context
    assert "## generation_constraints" in context
    assert "do_not_invent_prices_events_links_sources: true" in context
    assert "required_sections:" in context
    assert "- 核心摘要" in context
    assert "- market_overview" not in context
    assert '<embed path="analysis/market_material.md">' in context
    assert "artifact_type: analysis_market_material" in context
    assert '<embed path="analysis/text_material.md">' in context
    assert "artifact_type: analysis_text_material" in context
    assert "content_text: Source-provided event text." in context

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifacts"]["research_context"] == "analysis/research_context.md"
    assert manifest["stages"][3]["name"] == "build_research_context"
    assert manifest["stages"][3]["status"] == "succeeded"
    assert manifest["stages"][3]["artifacts"] == ["analysis/research_context.md"]
    assert manifest["stages"][4]["name"] == "build_codex_context"
    assert manifest["stages"][4]["status"] == "succeeded"
    assert manifest["stages"][5]["name"] == "run_codex_report"
    assert manifest["stages"][5]["status"] == "succeeded"


def test_research_context_marks_disabled_text_material_as_not_generated(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, text_enabled=False)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _write_market_raw,
            "run_codex_report": _skip_codex_report,
        },
    )

    assert result.succeeded is True
    assert result.failed_stage is None
    assert not (result.run.analysis_dir / "text_material.md").exists()

    context = (result.run.analysis_dir / "research_context.md").read_text(encoding="utf-8")
    assert "market_material: analysis/market_material.md" in context
    assert "text_material: null" in context
    assert "artifact: analysis/text_material.md" in context
    assert "status: not_generated" in context


def test_research_context_fails_when_enabled_material_is_missing(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _write_market_raw,
            "collect_text_events": _write_text_raw,
            "build_analysis_materials": _skip_analysis_materials,
        },
    )

    assert result.succeeded is False
    assert result.failed_stage == "build_research_context"
    assert result.reason == "analysis/market_material.md was not found; build_analysis_materials must run first."
    assert not (result.run.analysis_dir / "research_context.md").exists()

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["stages"][3]["name"] == "build_research_context"
    assert manifest["stages"][3]["status"] == "failed"
    assert manifest["errors"] == [
        {
            "stage": "build_research_context",
            "message": "analysis/market_material.md was not found; build_analysis_materials must run first.",
        }
    ]


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
  timezone: Asia/Shanghai
market:
  enabled: true
  source: binance
  symbols:
    - BTCUSDT
{text_block.rstrip()}
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


def _skip_analysis_materials(config, run) -> list[str]:
    return []


def _skip_codex_report(config, run) -> list[str]:
    return []
