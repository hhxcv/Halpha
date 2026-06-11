from __future__ import annotations

import json
from pathlib import Path

from halpha.config import load_config
from halpha.pipeline import run_pipeline
from halpha.storage import write_json


def test_pipeline_generates_ai_readable_text_material(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_text_events": _write_complete_text_raw,
            "run_codex_report": _skip_codex_report,
        },
    )

    assert result.succeeded is True
    assert result.failed_stage is None

    material = (result.run.analysis_dir / "text_material.md").read_text(encoding="utf-8")
    assert "artifact_type: analysis_text_material" in material
    assert "audience: ai" in material
    assert "source_artifacts:\n  - raw/text_events.json" in material
    assert "```yaml" in material
    assert "record_type: text_event" in material
    assert "id: text:coindesk:event-1" in material
    assert "input_type: rss_item" in material
    assert "title: Bitcoin market event" in material
    assert "published_at: '2026-06-05T00:30:00Z'" in material
    assert "name: coindesk" in material
    assert "url: https://www.coindesk.com/arc/outboundfeeds/rss/" in material
    assert "link: https://example.com/bitcoin-event" in material
    assert "content_text: Source-provided event text." in material
    assert "derived_summary: null" in material
    assert '- coindesk published item "Bitcoin market event" at 2026-06-05T00:30:00Z.' in material
    assert "derived_observations: []" in material
    assert "assumptions: []" in material
    assert "uncertainties: []" in material

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifacts"]["text_material"] == "analysis/text_material.md"
    assert manifest["counts"]["text_material_records"] == 1
    stage = _stage(manifest, "build_analysis_materials")
    assert stage["status"] == "succeeded"
    assert stage["artifacts"] == [
        "analysis/data_quality_material.md",
        "analysis/text_material.md",
    ]


def test_text_material_marks_missing_optional_source_values_explicitly(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_text_events": _write_minimum_text_raw,
            "run_codex_report": _skip_codex_report,
        },
    )

    assert result.succeeded is True
    assert result.failed_stage is None

    material = (result.run.analysis_dir / "text_material.md").read_text(encoding="utf-8")
    assert "url: null" in material
    assert "link: null" in material
    assert "published_at: null" in material
    assert "derived_summary: null" in material
    assert "source.url is missing from raw/text_events.json." in material
    assert "link is missing from raw/text_events.json." in material
    assert "published_at is missing from raw/text_events.json." in material
    assert 'coindesk published item "Bitcoin market event" without a source-provided published_at' in material
    assert "timestamp." in material


def test_text_material_uses_artifact_source_url_when_item_url_is_missing(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_text_events": _write_text_raw_with_artifact_source_url,
            "run_codex_report": _skip_codex_report,
        },
    )

    assert result.succeeded is True
    assert result.failed_stage is None

    material = (result.run.analysis_dir / "text_material.md").read_text(encoding="utf-8")
    assert "url: https://www.coindesk.com/arc/outboundfeeds/rss/" in material
    assert "source.url is missing from raw/text_events.json." not in material


def test_text_material_skips_when_text_disabled(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, text_enabled=False)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={"run_codex_report": _skip_codex_report},
    )

    assert result.succeeded is True
    assert result.failed_stage is None
    assert not (result.run.raw_dir / "text_events.json").exists()
    assert not (result.run.analysis_dir / "text_material.md").exists()

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["counts"]["text_event_items"] == 0
    assert manifest["counts"]["text_material_records"] == 0
    text_stage = _stage(manifest, "collect_text_events")
    analysis_stage = _stage(manifest, "build_analysis_materials")
    assert text_stage["status"] == "succeeded"
    assert text_stage["artifacts"] == []
    assert analysis_stage["status"] == "succeeded"
    assert analysis_stage["artifacts"] == ["analysis/data_quality_material.md"]


def test_text_material_rejects_invalid_raw_text_artifact(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_text_events": _write_invalid_text_raw,
            "build_text_event_records": _skip_text_event_records,
            "build_text_entity_evidence": _skip_text_entity_evidence,
            "build_text_event_classification_evidence": _skip_text_event_classification_evidence,
            "build_text_event_topics": _skip_text_event_topics,
            "build_text_event_signals": _skip_text_event_signals,
        },
    )

    assert result.succeeded is False
    assert result.failed_stage == "build_analysis_materials"
    assert result.reason == "raw/text_events.json is invalid: items[0].content_text is required."
    assert not (result.run.analysis_dir / "text_material.md").exists()

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["errors"] == [
        {
            "stage": "build_analysis_materials",
            "message": "raw/text_events.json is invalid: items[0].content_text is required.",
        }
    ]


def test_analysis_stage_records_market_artifact_before_text_material_failure(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, market_enabled=True)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _write_market_raw,
            "collect_text_events": _write_invalid_text_raw,
            "build_text_event_records": _skip_text_event_records,
            "build_text_entity_evidence": _skip_text_entity_evidence,
            "build_text_event_classification_evidence": _skip_text_event_classification_evidence,
            "build_text_event_topics": _skip_text_event_topics,
            "build_text_event_signals": _skip_text_event_signals,
        },
    )

    assert result.succeeded is False
    assert result.failed_stage == "build_analysis_materials"
    assert (result.run.analysis_dir / "market_material.md").exists()
    assert not (result.run.analysis_dir / "text_material.md").exists()

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifacts"]["market_material"] == "analysis/market_material.md"
    stage = _stage(manifest, "build_analysis_materials")
    assert stage["status"] == "failed"
    assert stage["artifacts"] == [
        "analysis/data_quality_material.md",
        "analysis/market_material.md",
    ]


def _write_config(
    tmp_path: Path,
    *,
    market_enabled: bool = False,
    text_enabled: bool = True,
) -> Path:
    config_path = tmp_path / "config.yaml"
    market_block = (
        """
market:
  enabled: true
  source: binance
  symbols:
    - BTCUSDT
"""
        if market_enabled
        else """
market:
  enabled: false
"""
    )
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
{market_block.rstrip()}
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


def _write_complete_text_raw(config, run) -> list[str]:
    write_json(run.raw_dir / "text_events.json", _text_raw(_complete_item()))
    return ["raw/text_events.json"]


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
    return ["raw/market.json"]


def _write_minimum_text_raw(config, run) -> list[str]:
    write_json(run.raw_dir / "text_events.json", _text_raw(_minimum_item(), source_url=None))
    return ["raw/text_events.json"]


def _write_text_raw_with_artifact_source_url(config, run) -> list[str]:
    item = _minimum_item()
    item["source"] = {"name": "coindesk"}
    write_json(run.raw_dir / "text_events.json", _text_raw(item))
    return ["raw/text_events.json"]


def _write_invalid_text_raw(config, run) -> list[str]:
    item = _complete_item()
    del item["content_text"]
    write_json(run.raw_dir / "text_events.json", _text_raw(item))
    return ["raw/text_events.json"]


def _skip_codex_report(config, run) -> list[str]:
    return []


def _skip_text_event_records(config, run) -> list[str]:
    return []


def _skip_text_entity_evidence(config, run) -> list[str]:
    return []


def _skip_text_event_classification_evidence(config, run) -> list[str]:
    return []


def _skip_text_event_topics(config, run) -> list[str]:
    return []


def _skip_text_event_signals(config, run) -> list[str]:
    return []


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
        "link": "https://example.com/bitcoin-event",
        "content_text": "Source-provided event text.",
        "language": None,
    }


def _minimum_item() -> dict:
    return {
        "id": "text:coindesk:event-1",
        "type": "rss_item",
        "title": "Bitcoin market event",
        "published_at": None,
        "source": {
            "name": "coindesk",
            "url": None,
        },
        "link": None,
        "content_text": "Source-provided event text.",
    }
