from __future__ import annotations

import json
from pathlib import Path

from halpha.config import load_config
from halpha.pipeline import run_pipeline
from halpha.storage import write_json


def test_text_entity_evidence_accepts_configured_asset_alias(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("halpha.text_entity_evidence._load_ner_model", _unavailable_ner_model)
    config_path = _write_config(tmp_path, symbols=["BTCUSDT", "ETHUSDT"])
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_text_entity_evidence",
        stage_handlers={"collect_text_events": _write_bitcoin_text_raw},
    )

    assert result.succeeded is True
    artifact = json.loads((result.run.analysis_dir / "text_entity_evidence.json").read_text(encoding="utf-8"))
    record = artifact["records"][0]
    relevance = record["asset_relevance"][0]
    entity = record["entity_evidence"][0]

    assert artifact["artifact_type"] == "text_entity_evidence"
    assert artifact["source_artifacts"] == ["analysis/text_event_records.json"]
    assert artifact["model_states"][0]["status"] == "unavailable"
    assert artifact["coverage"]["events_with_asset_relevance"] == 1
    assert artifact["coverage"]["accepted_asset_relevance"] == 1
    assert relevance["symbol"] == "BTCUSDT"
    assert relevance["asset"] == "BTC"
    assert relevance["state"] == "accepted"
    assert relevance["confidence"] == "high"
    assert "asset_alias:bitcoin" in relevance["matched_rules"]
    assert "configured_symbol:BTCUSDT" in relevance["matched_rules"]
    assert entity["method"] == "deterministic_asset_alias_rule"
    assert entity["accepted"] is True
    assert entity["asset_relevance"]["symbol"] == "BTCUSDT"

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifacts"]["text_entity_evidence"] == "analysis/text_entity_evidence.json"
    assert manifest["counts"]["text_asset_relevance_accepted"] == 1
    assert _stage(manifest, "build_text_entity_evidence")["artifacts"] == [
        "analysis/text_entity_evidence.json"
    ]


def test_text_entity_evidence_keeps_ambiguous_asset_references_unknown(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("halpha.text_entity_evidence._load_ner_model", _skipped_ner_model)
    config_path = _write_config(tmp_path, symbols=["BTCUSDT", "BTCUSDC"])
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_text_entity_evidence",
        stage_handlers={"collect_text_events": _write_btc_text_raw},
    )

    assert result.succeeded is True
    artifact = json.loads((result.run.analysis_dir / "text_entity_evidence.json").read_text(encoding="utf-8"))
    relevance = artifact["records"][0]["asset_relevance"][0]

    assert relevance["symbol"] is None
    assert relevance["asset"] == "BTC"
    assert relevance["state"] == "unknown"
    assert relevance["confidence"] == "low"
    assert relevance["candidate_symbols"] == ["BTCUSDC", "BTCUSDT"]
    assert relevance["matched_rules"] == ["ambiguous_asset_alias:btc"]
    assert artifact["coverage"]["unknown_asset_relevance"] == 1


def test_text_entity_evidence_uses_available_ner_model_as_traceable_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("halpha.text_entity_evidence._load_ner_model", _available_ner_model)
    config_path = _write_config(tmp_path, symbols=["BTCUSDT"])
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_text_entity_evidence",
        stage_handlers={"collect_text_events": _write_bitcoin_text_raw},
    )

    assert result.succeeded is True
    artifact = json.loads((result.run.analysis_dir / "text_entity_evidence.json").read_text(encoding="utf-8"))
    model_entities = [
        entity
        for entity in artifact["records"][0]["entity_evidence"]
        if entity["method"] == "pretrained_entity_model"
    ]

    assert artifact["model_states"][0]["status"] == "succeeded"
    assert model_entities == [
        {
            "event_id": artifact["records"][0]["event_id"],
            "text": "BlackRock",
            "label": "organization",
            "score": 0.92,
            "accepted": True,
            "method": "pretrained_entity_model",
            "model": {
                "provider": "gliner",
                "name": "urchade/gliner_medium-v2.1",
                "revision": "pinned",
            },
            "matched_rules": [],
            "asset_relevance": None,
            "warnings": [],
        }
    ]


def _write_config(tmp_path: Path, *, symbols: list[str]) -> Path:
    config_path = tmp_path / "config.yaml"
    symbol_lines = "\n".join(f"    - {symbol}" for symbol in symbols)
    config_path.write_text(
        f"""
run:
  output_dir: runs
market:
  enabled: true
  source: binance
  symbols:
{symbol_lines}
text:
  enabled: true
  max_items: 1
  intelligence:
    enabled: true
    model_cache_dir: data/models/text
    allow_model_download: false
    models:
      embedding:
        provider: sentence_transformers
        name: sentence-transformers/all-MiniLM-L6-v2
        revision: pinned
      classifier:
        provider: transformers_zero_shot
        name: facebook/bart-large-mnli
        revision: pinned
      sentiment:
        provider: transformers_text_classification
        name: ProsusAI/finbert
        revision: pinned
      ner:
        provider: gliner
        name: urchade/gliner_medium-v2.1
        revision: pinned
    thresholds:
      duplicate_similarity: 0.92
      same_topic_similarity: 0.82
      classifier_accept_score: 0.65
      classifier_top_margin: 0.10
      entity_accept_score: 0.50
      max_topic_window_hours: 48
  sources:
    - name: coindesk
      type: rss
      url: https://www.coindesk.com/arc/outboundfeeds/rss/
report:
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _write_bitcoin_text_raw(config, run) -> list[str]:
    write_json(run.raw_dir / "text_events.json", _raw_text_events(_item("Bitcoin ETF issuer BlackRock expands")))
    run.manifest["artifacts"]["raw_text_events"] = "raw/text_events.json"
    run.manifest["counts"]["text_event_items"] = 1
    return ["raw/text_events.json"]


def _write_btc_text_raw(config, run) -> list[str]:
    write_json(run.raw_dir / "text_events.json", _raw_text_events(_item("BTC market liquidity improves")))
    run.manifest["artifacts"]["raw_text_events"] = "raw/text_events.json"
    run.manifest["counts"]["text_event_items"] = 1
    return ["raw/text_events.json"]


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


def _item(title: str) -> dict:
    return {
        "id": f"text:coindesk:{title.lower().replace(' ', '-')}",
        "type": "rss_item",
        "title": title,
        "published_at": "2026-06-05T00:30:00Z",
        "source": {
            "name": "coindesk",
            "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        },
        "link": "https://example.com/bitcoin-event",
        "content_text": "Source-provided event text.",
        "language": "en",
    }


def _stage(manifest: dict, name: str) -> dict:
    return next(stage for stage in manifest["stages"] if stage["name"] == name)


def _unavailable_ner_model(config):
    return (
        {
            "role": "ner",
            "provider": "gliner",
            "name": "urchade/gliner_medium-v2.1",
            "revision": "pinned",
            "status": "unavailable",
            "task": "open_entity_extraction",
            "thresholds": {"entity_accept_score": 0.5},
            "warnings": ["optional gliner runtime is not installed"],
            "errors": [],
        },
        None,
    )


def _skipped_ner_model(config):
    state, _model = _unavailable_ner_model(config)
    return ({**state, "status": "skipped", "warnings": ["text_intelligence_disabled"]}, None)


def _available_ner_model(config):
    state, _model = _unavailable_ner_model(config)
    return ({**state, "status": "succeeded", "warnings": []}, _FakeNERModel())


class _FakeNERModel:
    def predict_entities(self, text, labels, threshold):
        return [{"text": "BlackRock", "label": "organization", "score": 0.92}]
