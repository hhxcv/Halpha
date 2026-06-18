from __future__ import annotations

import json
from pathlib import Path

from halpha.config import load_config
from halpha.pipeline import run_pipeline
from halpha.storage import write_json


def test_text_event_classification_accepts_high_confidence_category_and_tone(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("halpha.text_entity_evidence._load_ner_model", _skipped_ner_model)
    monkeypatch.setattr("halpha.text_event_classification._load_classifier_model", _available_classifier_model)
    monkeypatch.setattr("halpha.text_event_classification._load_sentiment_model", _available_sentiment_model)
    config_path = _write_config(tmp_path, symbols=["BTCUSDT"])
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_text_event_classification_evidence",
        stage_handlers={"collect_text_events": _write_bitcoin_etf_raw},
    )

    assert result.succeeded is True
    artifact = json.loads(
        (result.run.analysis_dir / "text_event_classification_evidence.json").read_text(encoding="utf-8")
    )
    record = artifact["records"][0]
    category = record["category_evidence"]
    tone = record["financial_tone_evidence"]

    assert artifact["artifact_type"] == "text_event_classification_evidence"
    assert artifact["source_artifacts"] == [
        "analysis/text_event_records.json",
        "analysis/text_entity_evidence.json",
    ]
    assert [state["status"] for state in artifact["model_states"]] == ["succeeded", "succeeded"]
    assert record["accepted_symbols"] == ["BTCUSDT"]
    assert category["state"] == "accepted"
    assert category["primary_category"] == "etf_flows"
    assert category["confidence"] == "high"
    assert category["threshold_checks"] == {
        "classifier_accept_score_met": True,
        "classifier_top_margin_met": True,
        "rule_or_entity_evidence_met": True,
    }
    assert category["candidates"][0]["category"] == "etf_flows"
    assert category["candidates"][0]["model_score"] == 0.86
    assert category["candidates"][0]["top_margin"] == 0.22
    assert category["candidates"][0]["accepted_by_gate"] is True
    assert "matched term: bitcoin etf" in category["candidates"][0]["rule_evidence"]
    assert tone["state"] == "accepted"
    assert tone["tone"] == "positive"
    assert tone["model_score"] == 0.91
    assert tone["not_trading_signal"] is True
    assert tone["scope"] == "event_text_tone_only"
    assert artifact["coverage"]["accepted_category_records"] == 1
    assert artifact["coverage"]["accepted_financial_tone_records"] == 1

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["artifacts"]["text_event_classification_evidence"] == (
        "analysis/text_event_classification_evidence.json"
    )
    assert manifest["counts"]["text_event_category_accepted"] == 1
    assert manifest["counts"]["text_event_financial_tone_accepted"] == 1


def test_text_event_classification_downgrades_weak_model_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("halpha.text_entity_evidence._load_ner_model", _skipped_ner_model)
    monkeypatch.setattr("halpha.text_event_classification._load_classifier_model", _weak_classifier_model)
    monkeypatch.setattr("halpha.text_event_classification._load_sentiment_model", _weak_sentiment_model)
    config_path = _write_config(tmp_path, symbols=["BTCUSDT"])
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_text_event_classification_evidence",
        stage_handlers={"collect_text_events": _write_bitcoin_etf_raw},
    )

    assert result.succeeded is True
    artifact = json.loads(
        (result.run.analysis_dir / "text_event_classification_evidence.json").read_text(encoding="utf-8")
    )
    record = artifact["records"][0]
    category = record["category_evidence"]
    tone = record["financial_tone_evidence"]

    assert category["state"] == "low_confidence"
    assert category["primary_category"] == "unknown"
    assert category["candidates"][0]["accepted_by_gate"] is False
    assert category["threshold_checks"]["classifier_accept_score_met"] is True
    assert category["threshold_checks"]["classifier_top_margin_met"] is False
    assert "classifier_top_margin_below_threshold" in category["warnings"]
    assert tone["state"] == "low_confidence"
    assert tone["tone"] == "unknown"
    assert tone["not_trading_signal"] is True
    assert "financial_tone_score_below_threshold" in tone["warnings"]
    assert artifact["coverage"]["low_confidence_category_records"] == 1
    assert artifact["coverage"]["low_confidence_financial_tone_records"] == 1


def test_text_event_classification_marks_missing_models_unknown(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("halpha.text_entity_evidence._load_ner_model", _skipped_ner_model)
    monkeypatch.setattr("halpha.text_event_classification._load_classifier_model", _unavailable_classifier_model)
    monkeypatch.setattr("halpha.text_event_classification._load_sentiment_model", _unavailable_sentiment_model)
    config_path = _write_config(tmp_path, symbols=["BTCUSDT"])
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_text_event_classification_evidence",
        stage_handlers={"collect_text_events": _write_bitcoin_etf_raw},
    )

    assert result.succeeded is True
    artifact = json.loads(
        (result.run.analysis_dir / "text_event_classification_evidence.json").read_text(encoding="utf-8")
    )
    record = artifact["records"][0]

    assert [state["status"] for state in artifact["model_states"]] == ["unavailable", "unavailable"]
    assert record["category_evidence"]["state"] == "unknown"
    assert record["category_evidence"]["primary_category"] == "unknown"
    assert record["category_evidence"]["candidates"] == []
    assert record["financial_tone_evidence"]["state"] == "unknown"
    assert record["financial_tone_evidence"]["tone"] == "unknown"
    assert "classifier_model_unavailable" in record["warnings"]
    assert "sentiment_model_unavailable" in record["warnings"]
    assert artifact["coverage"]["unknown_category_records"] == 1
    assert artifact["coverage"]["financial_tone_evidence"] == 0


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
        _raw_text_events(
            _item(
                "Bitcoin ETF inflows accelerate",
                "Bitcoin ETF inflows rose as institutional demand improved.",
            )
        ),
    )
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


def _item(title: str, content_text: str) -> dict:
    return {
        "id": "text:coindesk:bitcoin-etf",
        "type": "rss_item",
        "title": title,
        "published_at": "2026-06-05T00:30:00Z",
        "source": {
            "name": "coindesk",
            "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        },
        "link": "https://example.com/bitcoin-etf",
        "content_text": content_text,
        "language": "en",
    }


def _available_classifier_model(config):
    state, _model = _unavailable_classifier_model(config)
    return ({**state, "status": "succeeded", "warnings": [], "errors": []}, _FakeClassifier([0.86, 0.64, 0.12]))


def _weak_classifier_model(config):
    state, _model = _unavailable_classifier_model(config)
    return ({**state, "status": "succeeded", "warnings": [], "errors": []}, _FakeClassifier([0.68, 0.64, 0.12]))


def _available_sentiment_model(config):
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
