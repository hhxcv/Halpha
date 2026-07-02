from __future__ import annotations

import json
from pathlib import Path

import pytest

from halpha.config import load_config
from halpha.pipeline import run_pipeline
from halpha.storage import write_json


pytestmark = pytest.mark.usefixtures("isolate_artifact_cwd")


def test_text_event_signals_accepts_source_backed_category_signal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("halpha.text.text_entity_evidence._load_ner_model", _skipped_ner_model)
    monkeypatch.setattr("halpha.text.text_event_classification._load_classifier_model", _accepted_classifier_model)
    monkeypatch.setattr("halpha.text.text_event_classification._load_sentiment_model", _accepted_sentiment_model)
    monkeypatch.setattr("halpha.text.text_event_topics._load_embedding_model", _skipped_embedding_model)
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_source_evidence",
        stage_handlers={"collect_text_events": _write_bitcoin_etf_raw},
    )

    assert result.succeeded is True
    artifact = json.loads((result.run.analysis_dir / "text_event_signals.json").read_text(encoding="utf-8"))
    signal = artifact["signals"][0]

    assert artifact["artifact_type"] == "text_event_signals"
    assert artifact["source_artifacts"] == [
        "analysis/text_event_records.json",
        "analysis/text_event_topics.json",
        "analysis/text_event_classification_evidence.json",
    ]
    assert artifact["coverage"]["signals"] == 1
    assert artifact["coverage"]["accepted_signals"] == 1
    assert signal["status"] == "accepted"
    assert signal["symbol"] == "BTCUSDT"
    assert signal["relevance_scope"] == "symbol"
    assert signal["primary_category"] == "etf_flows"
    assert signal["event_bias"] == "supportive"
    assert signal["risk_impact"] == "neutral"
    assert signal["opportunity_impact"] == "opportunity_up"
    assert signal["strength"] == "medium"
    assert signal["confidence"] == "high"
    assert signal["source_event_ids"]
    assert {item["type"] for item in signal["evidence"]} == {
        "category_gate",
        "financial_tone",
        "source_event",
        "topic_group",
    }
    assert any(item["type"] == "category_gate" and item["accepted_by_gate"] for item in signal["evidence"])
    assert any(
        item["type"] == "financial_tone" and item["not_trading_signal"] is True
        for item in signal["evidence"]
    )
    assert "event signal is research context, not a trading signal or price forecast" in signal["uncertainty"]

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifacts"]["text_event_signals"] == "analysis/text_event_signals.json"
    assert manifest["counts"]["text_event_signals"] == 1
    assert manifest["counts"]["text_event_signals_accepted"] == 1


def test_text_event_signals_preserves_low_confidence_events_without_accepting_them(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("halpha.text.text_entity_evidence._load_ner_model", _skipped_ner_model)
    monkeypatch.setattr("halpha.text.text_event_classification._load_classifier_model", _weak_classifier_model)
    monkeypatch.setattr("halpha.text.text_event_classification._load_sentiment_model", _weak_sentiment_model)
    monkeypatch.setattr("halpha.text.text_event_topics._load_embedding_model", _skipped_embedding_model)
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_source_evidence",
        stage_handlers={"collect_text_events": _write_bitcoin_etf_raw},
    )

    assert result.succeeded is True
    artifact = json.loads((result.run.analysis_dir / "text_event_signals.json").read_text(encoding="utf-8"))
    signal = artifact["signals"][0]

    assert artifact["coverage"]["accepted_signals"] == 0
    assert artifact["coverage"]["low_confidence_signals"] == 1
    assert signal["status"] == "low_confidence"
    assert signal["primary_category"] == "unknown"
    assert signal["event_bias"] == "unknown"
    assert signal["risk_impact"] == "unknown"
    assert signal["opportunity_impact"] == "unknown"
    assert signal["strength"] == "unknown"
    assert "signal_status_low_confidence" in signal["warnings"]
    assert "category evidence is low confidence" in signal["uncertainty"]
    assert any(item["type"] == "category_gate" and item["accepted_by_gate"] is False for item in signal["evidence"])


def test_text_event_signals_accepts_rule_fallback_when_classifier_model_is_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("halpha.text.text_entity_evidence._load_ner_model", _skipped_ner_model)
    monkeypatch.setattr("halpha.text.text_event_classification._load_classifier_model", _unavailable_classifier_model)
    monkeypatch.setattr("halpha.text.text_event_classification._load_sentiment_model", _unavailable_sentiment_model)
    monkeypatch.setattr("halpha.text.text_event_topics._load_embedding_model", _skipped_embedding_model)
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_source_evidence",
        stage_handlers={"collect_text_events": _write_bitcoin_etf_raw},
    )

    assert result.succeeded is True
    artifact = json.loads((result.run.analysis_dir / "text_event_signals.json").read_text(encoding="utf-8"))
    signal = artifact["signals"][0]

    assert artifact["coverage"]["accepted_signals"] == 1
    assert artifact["coverage"]["unknown_signals"] == 0
    assert signal["status"] == "accepted"
    assert signal["symbol"] == "BTCUSDT"
    assert signal["primary_category"] == "etf_flows"
    assert signal["confidence"] == "low"
    assert signal["strength"] == "low"
    assert signal["event_bias"] == "supportive"
    assert "rule_based_category_fallback" in signal["warnings"]
    assert "sentiment_model_unavailable" in signal["warnings"]
    assert "signal_status_unknown" not in signal["warnings"]


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  output_dir: runs
market:
  enabled: false
  source: binance
  symbols:
    - BTCUSDT
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


def _write_bitcoin_etf_raw(config, run) -> list[str]:
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
                    "id": "text:coindesk:bitcoin-etf",
                    "type": "rss_item",
                    "title": "Bitcoin ETF inflows accelerate",
                    "published_at": "2026-06-05T00:30:00Z",
                    "source": {
                        "name": "coindesk",
                        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
                    },
                    "link": "https://example.com/bitcoin-etf",
                    "content_text": "Bitcoin ETF inflows rose as institutional demand improved.",
                    "language": "en",
                }
            ],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["raw_text_events"] = "raw/text_events.json"
    run.manifest["counts"]["text_event_items"] = 1
    return ["raw/text_events.json"]


def _accepted_classifier_model(config):
    state, _model = _unavailable_classifier_model(config)
    return ({**state, "status": "succeeded", "warnings": [], "errors": []}, _FakeClassifier([0.86, 0.64, 0.12]))


def _weak_classifier_model(config):
    state, _model = _unavailable_classifier_model(config)
    return ({**state, "status": "succeeded", "warnings": [], "errors": []}, _FakeClassifier([0.68, 0.64, 0.12]))


def _accepted_sentiment_model(config):
    state, _model = _unavailable_sentiment_model(config)
    return ({**state, "status": "succeeded", "warnings": [], "errors": []}, _FakeSentiment("positive", 0.91))


def _weak_sentiment_model(config):
    state, _model = _unavailable_sentiment_model(config)
    return ({**state, "status": "succeeded", "warnings": [], "errors": []}, _FakeSentiment("positive", 0.52))


def _unavailable_classifier_model(config):
    return (
        {
            "role": "classifier",
            "provider": "transformers_zero_shot",
            "name": "facebook/bart-large-mnli",
            "revision": "pinned",
            "status": "unavailable",
            "task": "event_category_zero_shot",
            "thresholds": {
                "classifier_accept_score": 0.65,
                "classifier_top_margin": 0.10,
            },
            "warnings": ["optional transformers runtime is not installed"],
            "errors": [],
        },
        None,
    )


def _unavailable_sentiment_model(config):
    return (
        {
            "role": "sentiment",
            "provider": "transformers_text_classification",
            "name": "ProsusAI/finbert",
            "revision": "pinned",
            "status": "unavailable",
            "task": "financial_tone_classification",
            "thresholds": {"financial_tone_accept_score": 0.55},
            "warnings": ["optional transformers runtime is not installed"],
            "errors": [],
        },
        None,
    )


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


class _FakeClassifier:
    def __init__(self, scores: list[float]) -> None:
        self.scores = scores

    def __call__(self, text, candidate_labels):
        return {
            "sequence": text,
            "labels": ["etf_flows", "institutional_adoption", "other"],
            "scores": self.scores,
        }


class _FakeSentiment:
    def __init__(self, label: str, score: float) -> None:
        self.label = label
        self.score = score

    def __call__(self, text):
        return [{"label": self.label, "score": self.score}]
