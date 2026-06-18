from __future__ import annotations

import json
import math
from pathlib import Path

from halpha.config import load_config
from halpha.pipeline import run_pipeline
from halpha.storage import write_json


def test_text_event_topics_groups_exact_duplicate_url_and_title(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("halpha.text_event_topics._load_embedding_model", _skipped_embedding_model)
    monkeypatch.setattr("halpha.text_entity_evidence._load_ner_model", _skipped_ner_model)
    config_path = _write_config(tmp_path, symbols=["BTCUSDT"])
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_text_event_topics",
        stage_handlers={"collect_text_events": _write_duplicate_text_raw},
    )

    assert result.succeeded is True
    artifact = json.loads((result.run.analysis_dir / "text_event_topics.json").read_text(encoding="utf-8"))
    topic = artifact["topics"][0]
    decision = topic["merge_decisions"][0]

    assert artifact["artifact_type"] == "text_event_topics"
    assert artifact["source_artifacts"] == [
        "analysis/text_event_records.json",
        "analysis/text_entity_evidence.json",
    ]
    assert artifact["model_states"][0]["status"] == "skipped"
    assert artifact["coverage"]["events"] == 2
    assert artifact["coverage"]["topics"] == 1
    assert artifact["coverage"]["duplicate_decisions"] == 1
    assert topic["event_count"] == 2
    assert topic["source_count"] == 2
    assert topic["symbols"] == ["BTCUSDT"]
    assert decision["relationship"] == "duplicate"
    assert "canonical_url_match" in decision["reasons"]
    assert "normalized_title_match" in decision["reasons"]
    assert decision["methods"] == ["canonical_url_rule", "normalized_title_rule", "lexical_similarity_rule"]

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifacts"]["text_event_topics"] == "analysis/text_event_topics.json"
    assert manifest["counts"]["text_event_topics"] == 1
    assert manifest["counts"]["text_event_topic_duplicate_decisions"] == 1
    assert _stage(manifest, "build_text_event_topics")["artifacts"] == [
        "analysis/text_event_topics.json"
    ]


def test_text_event_topics_records_embedding_same_topic_without_erasing_traceability(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("halpha.text_event_topics._load_embedding_model", _available_embedding_model)
    monkeypatch.setattr("halpha.text_entity_evidence._load_ner_model", _skipped_ner_model)
    config_path = _write_config(tmp_path, symbols=["BTCUSDT", "ETHUSDT"])
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_text_event_topics",
        stage_handlers={"collect_text_events": _write_embedding_text_raw},
    )

    assert result.succeeded is True
    artifact = json.loads((result.run.analysis_dir / "text_event_topics.json").read_text(encoding="utf-8"))
    records = json.loads((result.run.analysis_dir / "text_event_records.json").read_text(encoding="utf-8"))
    btc_decision = _decision(artifact, records, "btc-1", "btc-2")
    cross_asset_decision = _decision(artifact, records, "btc-1", "eth-1")
    btc_topic = next(topic for topic in artifact["topics"] if topic["symbols"] == ["BTCUSDT"])

    assert artifact["model_states"][0]["status"] == "succeeded"
    assert artifact["coverage"]["same_topic_decisions"] == 1
    assert artifact["coverage"]["distinct_decisions"] == 2
    assert btc_decision["relationship"] == "same_topic"
    assert btc_decision["similarity"] == 0.85
    assert btc_decision["similarity_evidence"]["embedding"] == 0.85
    assert "pretrained_embedding_model" in btc_decision["methods"]
    assert "embedding_same_topic_similarity_met" in btc_decision["reasons"]
    assert "asset_overlap_met" in btc_decision["reasons"]
    assert "time_window_met" in btc_decision["reasons"]
    assert btc_topic["event_count"] == 2
    assert sorted(btc_topic["event_ids"]) == sorted(
        [btc_decision["left_event_id"], btc_decision["right_event_id"]]
    )
    assert btc_topic["merge_decisions"][0]["relationship"] == "same_topic"
    assert cross_asset_decision["relationship"] == "distinct"


def test_text_event_topics_does_not_merge_on_embedding_similarity_alone(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("halpha.text_event_topics._load_embedding_model", _high_similarity_embedding_model)
    monkeypatch.setattr("halpha.text_entity_evidence._load_ner_model", _skipped_ner_model)
    config_path = _write_config(tmp_path, symbols=["BTCUSDT"])
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_text_event_topics",
        stage_handlers={"collect_text_events": _write_no_asset_text_raw},
    )

    assert result.succeeded is True
    artifact = json.loads((result.run.analysis_dir / "text_event_topics.json").read_text(encoding="utf-8"))
    decision = artifact["pair_decisions"][0]

    assert decision["similarity"] == 0.95
    assert decision["relationship"] == "related_context"
    assert artifact["coverage"]["topics"] == 2
    assert all(topic["event_count"] == 1 for topic in artifact["topics"])


def _write_config(tmp_path: Path, *, symbols: list[str]) -> Path:
    config_path = tmp_path / "config.yaml"
    symbol_lines = "\n".join(f"    - {symbol}" for symbol in symbols)
    config_path.write_text(
        f"""
run:
  output_dir: runs
market:
  enabled: false
  source: binance
  symbols:
{symbol_lines}
text:
  enabled: true
  max_items: 3
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


def _write_duplicate_text_raw(config, run) -> list[str]:
    write_json(
        run.raw_dir / "text_events.json",
        _raw_text_events(
            [
                _item(
                    "dup-1",
                    "coindesk",
                    "Bitcoin ETF inflows rise",
                    "Bitcoin ETF inflows rose again.",
                    "https://example.com/bitcoin-etf?utm_source=a",
                    "2026-06-05T00:30:00Z",
                ),
                _item(
                    "dup-2",
                    "the-block",
                    "Bitcoin ETF inflows rise",
                    "Bitcoin ETF inflows rose again.",
                    "https://example.com/bitcoin-etf?utm_source=b",
                    "2026-06-05T01:30:00Z",
                ),
            ]
        ),
    )
    run.manifest["artifacts"]["raw_text_events"] = "raw/text_events.json"
    run.manifest["counts"]["text_event_items"] = 2
    return ["raw/text_events.json"]


def _write_embedding_text_raw(config, run) -> list[str]:
    write_json(
        run.raw_dir / "text_events.json",
        _raw_text_events(
            [
                _item(
                    "btc-1",
                    "coindesk",
                    "Bitcoin ETF inflows accelerate",
                    "Bitcoin ETF demand increased during the session.",
                    "https://example.com/btc-etf-1",
                    "2026-06-05T00:30:00Z",
                ),
                _item(
                    "btc-2",
                    "the-block",
                    "BTC ETF inflows expand",
                    "BTC ETF demand expanded during the session.",
                    "https://example.com/btc-etf-2",
                    "2026-06-05T02:30:00Z",
                ),
                _item(
                    "eth-1",
                    "coindesk",
                    "Ethereum staking queue changes",
                    "Ethereum staking validators adjusted queue exposure.",
                    "https://example.com/eth-staking",
                    "2026-06-05T03:30:00Z",
                ),
            ]
        ),
    )
    run.manifest["artifacts"]["raw_text_events"] = "raw/text_events.json"
    run.manifest["counts"]["text_event_items"] = 3
    return ["raw/text_events.json"]


def _write_no_asset_text_raw(config, run) -> list[str]:
    write_json(
        run.raw_dir / "text_events.json",
        _raw_text_events(
            [
                _item(
                    "macro-1",
                    "coindesk",
                    "Macro liquidity expectations improve",
                    "Traders discussed broader liquidity expectations.",
                    "https://example.com/macro-1",
                    "2026-06-05T00:30:00Z",
                ),
                _item(
                    "macro-2",
                    "the-block",
                    "Global liquidity expectations strengthen",
                    "Market participants discussed broader liquidity expectations.",
                    "https://example.com/macro-2",
                    "2026-06-05T01:30:00Z",
                ),
            ]
        ),
    )
    run.manifest["artifacts"]["raw_text_events"] = "raw/text_events.json"
    run.manifest["counts"]["text_event_items"] = 2
    return ["raw/text_events.json"]


def _raw_text_events(items: list[dict]) -> dict:
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
            },
            {
                "name": "the-block",
                "type": "rss",
                "url": "https://www.theblock.co/rss.xml",
            },
        ],
        "items": items,
        "errors": [],
    }


def _item(raw_id: str, source_name: str, title: str, content_text: str, link: str, published_at: str) -> dict:
    return {
        "id": f"text:{source_name}:{raw_id}",
        "type": "rss_item",
        "title": title,
        "published_at": published_at,
        "source": {
            "name": source_name,
            "url": f"https://example.com/{source_name}",
        },
        "link": link,
        "content_text": content_text,
        "language": "en",
    }


def _decision(artifact: dict, records_artifact: dict, left_raw_id: str, right_raw_id: str) -> dict:
    records = {
        record["raw_item_id"].rsplit(":", 1)[-1]: record["event_id"]
        for record in records_artifact["records"]
    }
    expected = {records[left_raw_id], records[right_raw_id]}
    for decision in artifact["pair_decisions"]:
        if {decision["left_event_id"], decision["right_event_id"]} == expected:
            return decision
    raise AssertionError(f"pair decision not found: {left_raw_id}, {right_raw_id}")


def _stage(manifest: dict, name: str) -> dict:
    return next(stage for stage in manifest["stages"] if stage["name"] == name)


def _skipped_embedding_model(config):
    return (
        {
            "role": "embedding",
            "provider": "sentence_transformers",
            "name": "sentence-transformers/all-MiniLM-L6-v2",
            "revision": "pinned",
            "status": "skipped",
            "task": "sentence_similarity",
            "thresholds": {
                "duplicate_similarity": 0.92,
                "same_topic_similarity": 0.82,
                "max_topic_window_hours": 48,
                "lexical_same_topic_min": 0.35,
            },
            "warnings": ["text_intelligence_disabled"],
            "errors": [],
        },
        None,
    )


def _available_embedding_model(config):
    state, _model = _skipped_embedding_model(config)
    return ({**state, "status": "succeeded", "warnings": []}, _FakeEmbeddingModel(0.85))


def _high_similarity_embedding_model(config):
    state, _model = _skipped_embedding_model(config)
    return ({**state, "status": "succeeded", "warnings": []}, _FakeEmbeddingModel(0.95))


def _skipped_ner_model(config):
    return (
        {
            "role": "ner",
            "provider": "gliner",
            "name": "urchade/gliner_medium-v2.1",
            "revision": "pinned",
            "status": "skipped",
            "task": "open_entity_extraction",
            "thresholds": {"entity_accept_score": 0.5},
            "warnings": ["text_intelligence_disabled"],
            "errors": [],
        },
        None,
    )


class _FakeEmbeddingModel:
    def __init__(self, pair_similarity: float) -> None:
        self.pair_similarity = pair_similarity

    def encode(self, texts, normalize_embeddings=True):
        y = math.sqrt(1 - self.pair_similarity**2)
        vectors = [
            [1.0, 0.0, 0.0],
            [self.pair_similarity, y, 0.0],
        ]
        if len(texts) > 2:
            vectors.append([0.0, 0.0, 1.0])
        return vectors[: len(texts)]
