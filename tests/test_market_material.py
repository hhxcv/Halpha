from __future__ import annotations

import json
from pathlib import Path

from halpha.config import load_config
from halpha.pipeline import run_pipeline
from halpha.storage import write_json


def test_pipeline_generates_ai_readable_market_material(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _write_complete_market_raw,
            "collect_text_events": _skip_text_collection,
            "run_codex_report": _skip_codex_report,
        },
    )

    assert result.succeeded is True
    assert result.failed_stage is None

    material = (result.run.analysis_dir / "market_material.md").read_text(encoding="utf-8")
    assert "artifact_type: analysis_market_material" in material
    assert "audience: ai" in material
    assert "source_artifacts:\n  - raw/market.json" in material
    assert "```yaml" in material
    assert "record_type: market_observation" in material
    assert "id: market:binance:BTCUSDT:2026-06-05T00:30:00Z" in material
    assert "symbol: BTCUSDT" in material
    assert "as_of: '2026-06-05T00:30:00Z'" in material
    assert "price: '68000.00'" in material
    assert "change_24h_pct: '1.25'" in material
    assert "name: binance" in material
    assert "url: https://data-api.binance.vision" in material
    assert "- binance reports BTCUSDT price as 68000.00 at 2026-06-05T00:30:00Z." in material
    assert "derived_observations: []" in material
    assert "assumptions: []" in material
    assert "uncertainties: []" in material

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifacts"]["market_material"] == "analysis/market_material.md"
    assert manifest["counts"]["market_material_records"] == 1
    stage = _stage(manifest, "build_analysis_materials")
    assert stage["status"] == "succeeded"
    assert stage["artifacts"] == [
        "analysis/data_quality_material.md",
        "analysis/market_material.md",
    ]


def test_market_material_marks_missing_values_explicitly(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _write_minimum_market_raw,
            "collect_text_events": _skip_text_collection,
            "run_codex_report": _skip_codex_report,
        },
    )

    assert result.succeeded is True
    assert result.failed_stage is None

    material = (result.run.analysis_dir / "market_material.md").read_text(encoding="utf-8")
    assert "price: null" in material
    assert "change_24h_pct: null" in material
    assert "volume_24h: null" in material
    assert "quote_volume_24h: null" in material
    assert "url: null" in material
    assert "metrics.price is missing from raw/market.json." in material
    assert "source.url is missing from raw/market.json." in material


def test_market_material_uses_artifact_source_url_when_item_url_is_missing(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _write_market_raw_with_artifact_source_url,
            "collect_text_events": _skip_text_collection,
            "run_codex_report": _skip_codex_report,
        },
    )

    assert result.succeeded is True
    assert result.failed_stage is None

    material = (result.run.analysis_dir / "market_material.md").read_text(encoding="utf-8")
    assert "url: https://data-api.binance.vision" in material
    assert "source.url is missing from raw/market.json." not in material


def test_market_material_skips_when_market_disabled(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, market_enabled=False)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_text_events": _skip_text_collection,
            "run_codex_report": _skip_codex_report,
        },
    )

    assert result.succeeded is True
    assert result.failed_stage is None
    assert not (result.run.raw_dir / "market.json").exists()
    assert not (result.run.analysis_dir / "market_material.md").exists()

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["counts"]["market_items"] == 0
    assert manifest["counts"]["market_material_records"] == 0
    market_stage = _stage(manifest, "collect_market_data")
    analysis_stage = _stage(manifest, "build_analysis_materials")
    assert market_stage["status"] == "succeeded"
    assert market_stage["artifacts"] == []
    assert analysis_stage["status"] == "succeeded"
    assert analysis_stage["artifacts"] == ["analysis/data_quality_material.md"]


def test_market_material_rejects_invalid_raw_market_artifact(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _write_invalid_market_raw,
            "collect_text_events": _skip_text_collection,
        },
    )

    assert result.succeeded is False
    assert result.failed_stage == "build_analysis_materials"
    assert result.reason == "raw/market.json is invalid: items[0].id is required."
    assert not (result.run.analysis_dir / "market_material.md").exists()

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["errors"] == [
        {
            "stage": "build_analysis_materials",
            "message": "raw/market.json is invalid: items[0].id is required.",
        }
    ]


def _write_config(
    tmp_path: Path,
    *,
    market_enabled: bool = True,
    text_enabled: bool = False,
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


def _write_complete_market_raw(config, run) -> list[str]:
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
    return ["raw/market.json"]


def _write_minimum_market_raw(config, run) -> list[str]:
    write_json(
        run.raw_dir / "market.json",
        {
            "schema_version": 1,
            "artifact_type": "market_raw",
            "collector": "market",
            "collection_method": "public_http",
            "source": {
                "name": "binance",
                "url": None,
            },
            "collected_at": "2026-06-05T00:30:00Z",
            "items": [
                {
                    "id": "market:binance:BTCUSDT:2026-06-05T00:30:00Z",
                    "symbol": "BTCUSDT",
                    "as_of": "2026-06-05T00:30:00Z",
                    "source": {
                        "name": "binance",
                        "url": None,
                    },
                }
            ],
            "errors": [],
        },
    )
    return ["raw/market.json"]


def _write_market_raw_with_artifact_source_url(config, run) -> list[str]:
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
                    "source": {
                        "name": "binance",
                    },
                }
            ],
            "errors": [],
        },
    )
    return ["raw/market.json"]


def _write_invalid_market_raw(config, run) -> list[str]:
    write_json(
        run.raw_dir / "market.json",
        {
            "schema_version": 1,
            "artifact_type": "market_raw",
            "items": [
                {
                    "symbol": "BTCUSDT",
                    "as_of": "2026-06-05T00:30:00Z",
                    "source": {"name": "binance"},
                }
            ],
            "errors": [],
        },
    )
    return ["raw/market.json"]


def _skip_text_collection(config, run) -> list[str]:
    return []


def _skip_codex_report(config, run) -> list[str]:
    return []


def _stage(manifest: dict, name: str) -> dict:
    return next(stage for stage in manifest["stages"] if stage["name"] == name)
