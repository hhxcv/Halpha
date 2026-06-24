from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from halpha.config import load_config
from halpha.pipeline import run_pipeline
from halpha.storage import write_json


FIXTURES_DIR = Path(__file__).parent / "fixtures"
GOLDEN_RAW_PATH = FIXTURES_DIR / "text_event_golden_corpus.json"
GOLDEN_EXPECTATIONS_PATH = FIXTURES_DIR / "text_event_golden_expectations.json"


def test_golden_corpus_accepts_traceable_high_confidence_event_outputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("halpha.text.text_entity_evidence._load_ner_model", _unavailable_ner_model)
    monkeypatch.setattr("halpha.text.text_event_classification._load_classifier_model", _golden_classifier_model)
    monkeypatch.setattr("halpha.text.text_event_classification._load_sentiment_model", _golden_sentiment_model)
    monkeypatch.setattr("halpha.text.text_event_topics._load_embedding_model", _golden_embedding_model)
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_source_evidence",
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_text_events": _write_golden_raw,
        },
    )

    assert result.succeeded is True
    expectations = _expectations()
    records = _artifact(result, "text_event_records.json")["records"]
    entities = _artifact(result, "text_entity_evidence.json")
    classifications = _artifact(result, "text_event_classification_evidence.json")
    topics = _artifact(result, "text_event_topics.json")
    signals = _artifact(result, "text_event_signals.json")
    raw_to_event_id = {record["raw_item_id"]: record["event_id"] for record in records}

    _assert_asset_relevance(entities, expectations["accepted_asset_relevance"])
    _assert_accepted_categories(classifications, expectations["accepted_categories"])
    _assert_unknown_categories(classifications, expectations["unknown_categories"])
    _assert_high_confidence_traceability(classifications, entities)
    _assert_same_topic_groups(topics, raw_to_event_id, expectations["same_topic_groups"])
    _assert_false_merge_safety(topics, raw_to_event_id, expectations)
    _assert_signal_traceability(signals, classifications)


def test_golden_corpus_keeps_model_unavailable_classification_unknown(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr("halpha.text.text_entity_evidence._load_ner_model", _unavailable_ner_model)
    monkeypatch.setattr("halpha.text.text_event_classification._load_classifier_model", _unavailable_classifier_model)
    monkeypatch.setattr("halpha.text.text_event_classification._load_sentiment_model", _unavailable_sentiment_model)
    monkeypatch.setattr("halpha.text.text_event_topics._load_embedding_model", _unavailable_embedding_model)
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_source_evidence",
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_text_events": _write_golden_raw,
        },
    )

    assert result.succeeded is True
    classifications = _artifact(result, "text_event_classification_evidence.json")
    signals = _artifact(result, "text_event_signals.json")

    assert [state["status"] for state in classifications["model_states"]] == ["unavailable", "unavailable"]
    for record in classifications["records"]:
        category = record["category_evidence"]
        tone = record["financial_tone_evidence"]
        assert category["state"] == "unknown"
        assert category["primary_category"] == "unknown"
        assert category["candidates"] == []
        assert tone["state"] == "unknown"
        assert tone["tone"] == "unknown"
        assert "classifier_model_unavailable" in record["warnings"]
        assert "sentiment_model_unavailable" in record["warnings"]
    assert {signal["status"] for signal in signals["signals"]} == {"unknown"}
    assert all(signal["primary_category"] == "unknown" for signal in signals["signals"])


def _assert_asset_relevance(artifact: dict[str, Any], expected: dict[str, str]) -> None:
    records = {record["raw_item_id"]: record for record in artifact["records"]}
    for raw_item_id, symbol in expected.items():
        record = records[raw_item_id]
        accepted = [
            relevance for relevance in record["asset_relevance"] if relevance["state"] == "accepted"
        ]
        assert symbol in [relevance["symbol"] for relevance in accepted]
        relevance = next(relevance for relevance in accepted if relevance["symbol"] == symbol)
        assert relevance["confidence"] == "high"
        assert relevance["matched_rules"]
        assert any(rule.startswith("asset_alias:") for rule in relevance["matched_rules"])
        assert f"configured_symbol:{symbol}" in relevance["matched_rules"]
        assert record["source_artifacts"] == ["analysis/text_event_records.json"]


def _assert_accepted_categories(artifact: dict[str, Any], expected: dict[str, str]) -> None:
    records = {record["raw_item_id"]: record for record in artifact["records"]}
    for raw_item_id, category_name in expected.items():
        record = records[raw_item_id]
        category = record["category_evidence"]
        candidate = category["candidates"][0]
        assert category["state"] == "accepted"
        assert category["primary_category"] == category_name
        assert category["threshold_checks"] == {
            "classifier_accept_score_met": True,
            "classifier_top_margin_met": True,
            "rule_or_entity_evidence_met": True,
        }
        assert candidate["category"] == category_name
        assert candidate["accepted_by_gate"] is True
        assert candidate["model"]["name"] == "facebook/bart-large-mnli"
        assert candidate["rule_evidence"] or record["accepted_symbols"]


def _assert_unknown_categories(artifact: dict[str, Any], raw_item_ids: list[str]) -> None:
    records = {record["raw_item_id"]: record for record in artifact["records"]}
    for raw_item_id in raw_item_ids:
        record = records[raw_item_id]
        category = record["category_evidence"]
        assert category["state"] == "low_confidence"
        assert category["primary_category"] == "unknown"
        assert "category_rule_or_entity_evidence_missing" in category["warnings"]


def _assert_high_confidence_traceability(
    classification_artifact: dict[str, Any],
    entity_artifact: dict[str, Any],
) -> None:
    entity_records = {record["event_id"]: record for record in entity_artifact["records"]}
    for record in classification_artifact["records"]:
        category = record["category_evidence"]
        if category["state"] != "accepted":
            continue
        entity_record = entity_records[record["event_id"]]
        candidate = category["candidates"][0]
        assert candidate["model"]["provider"] == "transformers_zero_shot"
        assert candidate["model_score"] >= 0.65
        assert candidate["top_margin"] >= 0.1
        assert candidate["rule_evidence"] or record["accepted_symbols"]
        assert record["source_artifacts"] == [
            "analysis/text_event_records.json",
            "analysis/text_entity_evidence.json",
        ]
        if record["accepted_symbols"]:
            assert entity_record["asset_relevance"]


def _assert_same_topic_groups(
    topics_artifact: dict[str, Any],
    raw_to_event_id: dict[str, str],
    expected_groups: list[list[str]],
) -> None:
    topic_event_sets = [set(topic["event_ids"]) for topic in topics_artifact["topics"]]
    for raw_group in expected_groups:
        expected_event_ids = {raw_to_event_id[raw_id] for raw_id in raw_group}
        assert any(expected_event_ids <= event_ids for event_ids in topic_event_sets)


def _assert_false_merge_safety(
    topics_artifact: dict[str, Any],
    raw_to_event_id: dict[str, str],
    expectations: dict[str, Any],
) -> None:
    btc_group = {raw_to_event_id[raw_id] for raw_id in expectations["same_topic_groups"][0]}
    must_not_merge = {raw_to_event_id[raw_id] for raw_id in expectations["must_not_merge_with_btc_etf_group"]}
    for topic in topics_artifact["topics"]:
        topic_ids = set(topic["event_ids"])
        assert not (btc_group & topic_ids and must_not_merge & topic_ids)

    pair_decisions = topics_artifact["pair_decisions"]
    left = raw_to_event_id["text:golden:btc-etf-a"]
    right = raw_to_event_id["text:golden:unrelated-art"]
    decision = _pair_decision(pair_decisions, left, right)
    assert decision["relationship"] in {"related_context", "distinct"}
    assert decision["relationship"] not in {"duplicate", "same_topic"}


def _assert_signal_traceability(signals_artifact: dict[str, Any], classification_artifact: dict[str, Any]) -> None:
    classification_index = {record["event_id"]: record for record in classification_artifact["records"]}
    for signal in signals_artifact["signals"]:
        if signal["status"] != "accepted":
            continue
        assert signal["source_event_ids"]
        assert signal["source_artifacts"] == [
            "analysis/text_event_records.json",
            "analysis/text_event_topics.json",
            "analysis/text_event_classification_evidence.json",
        ]
        assert any(evidence["type"] == "category_gate" for evidence in signal["evidence"])
        for event_id in signal["source_event_ids"]:
            if event_id in classification_index:
                assert classification_index[event_id]["category_evidence"]["state"] == "accepted"


def _pair_decision(pair_decisions: list[dict[str, Any]], left: str, right: str) -> dict[str, Any]:
    for decision in pair_decisions:
        if {decision["left_event_id"], decision["right_event_id"]} == {left, right}:
            return decision
    raise AssertionError(f"pair decision not found for {left} and {right}")


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  output_dir: runs
market:
  enabled: true
  source: binance
  symbols:
    - BTCUSDT
    - ETHUSDT
text:
  enabled: true
  max_items: 10
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
    - name: golden-feed
      type: rss
      url: https://example.com/golden-feed.xml
report:
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _write_golden_raw(config, run) -> list[str]:
    write_json(run.raw_dir / "text_events.json", json.loads(GOLDEN_RAW_PATH.read_text(encoding="utf-8")))
    run.manifest["artifacts"]["raw_text_events"] = "raw/text_events.json"
    run.manifest["counts"]["text_event_items"] = len(json.loads(GOLDEN_RAW_PATH.read_text(encoding="utf-8"))["items"])
    return ["raw/text_events.json"]


def _noop_stage(config, run) -> list[str]:
    return []


def _artifact(result, filename: str) -> dict[str, Any]:
    return json.loads((result.run.analysis_dir / filename).read_text(encoding="utf-8"))


def _expectations() -> dict[str, Any]:
    return json.loads(GOLDEN_EXPECTATIONS_PATH.read_text(encoding="utf-8"))


def _golden_classifier_model(config):
    state, _model = _unavailable_classifier_model(config)
    return ({**state, "status": "succeeded", "warnings": [], "errors": []}, _GoldenClassifier())


def _golden_sentiment_model(config):
    state, _model = _unavailable_sentiment_model(config)
    return ({**state, "status": "succeeded", "warnings": [], "errors": []}, _GoldenSentiment())


def _golden_embedding_model(config):
    state, _model = _unavailable_embedding_model(config)
    return ({**state, "status": "succeeded", "warnings": [], "errors": []}, _GoldenEmbedding())


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


def _unavailable_embedding_model(config):
    return (
        {
            "role": "embedding",
            "provider": "sentence_transformers",
            "name": "sentence-transformers/all-MiniLM-L6-v2",
            "revision": "pinned",
            "status": "unavailable",
            "task": "sentence_similarity",
            "thresholds": {
                "duplicate_similarity": 0.92,
                "same_topic_similarity": 0.82,
                "max_topic_window_hours": 48,
                "lexical_same_topic_min": 0.35,
            },
            "warnings": ["optional sentence-transformers runtime is not installed"],
            "errors": [],
        },
        None,
    )


class _GoldenClassifier:
    def __call__(self, text, candidate_labels):
        category = _category_for_text(text)
        if category == "unrelated":
            return {
                "sequence": text,
                "labels": ["institutional_adoption", "other", "etf_flows"],
                "scores": [0.88, 0.60, 0.10],
            }
        return {
            "sequence": text,
            "labels": [category, "other", "institutional_adoption"],
            "scores": [0.90, 0.61, 0.20],
        }


class _GoldenSentiment:
    def __call__(self, text):
        return [{"label": "neutral", "score": 0.82}]


class _GoldenEmbedding:
    def encode(self, texts, normalize_embeddings=True):
        return [_embedding_vector(text) for text in texts]


def _category_for_text(text: str) -> str:
    lowered = text.lower()
    if "etf" in lowered:
        return "etf_flows"
    if "exploit" in lowered or "vulnerability" in lowered:
        return "security_exploit"
    if "stablecoin" in lowered or "usdc" in lowered:
        return "stablecoin_liquidity"
    if "regulation" in lowered or "compliance" in lowered:
        return "regulation_compliance"
    if "cpi" in lowered or "inflation" in lowered:
        return "macro_policy"
    return "unrelated"


def _embedding_vector(text: str) -> list[float]:
    lowered = text.lower()
    if "spot bitcoin etf flow" in lowered:
        return [0.86, math.sqrt(1 - 0.86**2)]
    return [1.0, 0.0]
