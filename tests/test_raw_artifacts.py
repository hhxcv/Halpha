from __future__ import annotations

import json
from pathlib import Path

import pytest

from halpha.config import load_config
from halpha.pipeline import run_pipeline
from halpha.raw_artifacts import (
    RawArtifactError,
    validate_market_raw_artifact,
    validate_text_events_raw_artifact,
)


def test_market_raw_validation_failure_records_manifest_error(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def invalid_raw_market(market):
        return {
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
        }

    monkeypatch.setattr("halpha.collectors.market._collect_raw_market", invalid_raw_market)

    result = run_pipeline(config, config_path=config_path)

    assert result.succeeded is False
    assert result.failed_stage == "collect_market_data"
    assert result.reason == "raw/market.json is invalid: items[0].id is required."
    assert not (result.run.raw_dir / "market.json").exists()

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["errors"] == [
        {
            "stage": "collect_market_data",
            "message": "raw/market.json is invalid: items[0].id is required.",
        }
    ]


def test_text_raw_validation_failure_records_manifest_error(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def invalid_raw_text(text, *, proxy_url=None):
        return {
            "schema_version": 1,
            "artifact_type": "text_events_raw",
            "items": [
                {
                    "id": "text:coindesk:1",
                    "title": "Market event",
                    "published_at": "2026-06-05T00:30:00Z",
                    "source": {"name": "coindesk", "url": "https://example.com/rss"},
                }
            ],
            "errors": [],
        }

    monkeypatch.setattr("halpha.collectors.text._collect_raw_text_events", invalid_raw_text)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={"collect_market_data": _collect_market_data},
    )

    assert result.succeeded is False
    assert result.failed_stage == "collect_text_events"
    assert result.reason == "raw/text_events.json is invalid: items[0].content_text is required."
    assert not (result.run.raw_dir / "text_events.json").exists()

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["errors"] == [
        {
            "stage": "collect_text_events",
            "message": "raw/text_events.json is invalid: items[0].content_text is required.",
        }
    ]


def test_raw_validation_rejects_non_object_artifact() -> None:
    with pytest.raises(RawArtifactError, match="raw/market.json is invalid: artifact must be a JSON object"):
        validate_market_raw_artifact([], "raw/market.json")


def test_raw_validation_rejects_missing_items_list() -> None:
    with pytest.raises(RawArtifactError, match="raw/text_events.json is invalid: items must be a list"):
        validate_text_events_raw_artifact({"items": {}}, "raw/text_events.json")


def test_text_raw_validation_allows_explicit_null_optional_source_values() -> None:
    validate_text_events_raw_artifact(
        {
            "items": [
                {
                    "id": "text:source:item",
                    "title": "Market event",
                    "published_at": None,
                    "source": {"name": "source", "url": None},
                    "content_text": "Source-provided text.",
                }
            ]
        },
        "raw/text_events.json",
    )


def test_text_raw_validation_rejects_blank_optional_published_at() -> None:
    with pytest.raises(RawArtifactError, match="items\\[0\\]\\.published_at must be a string or null"):
        validate_text_events_raw_artifact(
            {
                "items": [
                    {
                        "id": "text:source:item",
                        "title": "Market event",
                        "published_at": "",
                        "source": {"name": "source", "url": None},
                        "content_text": "Source-provided text.",
                    }
                ]
            },
            "raw/text_events.json",
        )


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


def _collect_market_data(config, run) -> list[str]:
    return []
