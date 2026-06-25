from __future__ import annotations

import json
from pathlib import Path

import pytest

from halpha.config import load_config
from halpha.pipeline import run_pipeline
from halpha.storage import write_json


pytestmark = pytest.mark.usefixtures("isolate_artifact_cwd")


def test_event_intelligence_material_bounds_report_facing_event_evidence(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_materials",
        stage_handlers=_material_handlers({
            "collect_text_events": _noop_stage,
            "build_text_event_records": _write_event_records,
            "build_text_entity_evidence": _noop_stage,
            "build_text_event_classification_evidence": _write_classification,
            "build_text_event_topics": _write_topics,
            "build_text_event_signals": _write_signals,
            "build_event_market_confluence": _write_confluence,
        }),
    )

    assert result.succeeded is True
    material = (result.run.analysis_dir / "event_intelligence_material.md").read_text(encoding="utf-8")
    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))

    assert "artifact_type: analysis_event_intelligence_material" in material
    assert "analysis/text_event_records.json" in material
    assert "analysis/text_event_classification_evidence.json" in material
    assert "analysis/text_event_topics.json" in material
    assert "analysis/text_event_signals.json" in material
    assert "analysis/event_market_confluence.json" in material
    assert "## event_source_policy" in material
    assert "## event_model_policy" in material
    assert "## event_overview" in material
    assert "## topic_summary" in material
    assert "## event_signal_summary" in material
    assert "## event_market_confluence" in material
    assert "## risk_and_uncertainty" in material
    assert "## report_usage_rules" in material
    assert "## records" in material
    assert "codex_may_generate_event_categories: false" in material
    assert "codex_may_generate_event_impacts: false" in material
    assert "codex_may_generate_event_market_relationships: false" in material
    assert "codex_may_generate_action_levels: false" in material
    assert "codex_may_generate_price_forecasts: false" in material
    assert "event_signals_are_trading_signals: false" in material
    assert "financial_tone_is_event_text_evidence_only: true" in material
    assert "event_signal_id: text_event_signal:btcusdt:etf_flows:abc123" in material
    assert "primary_category: etf_flows" in material
    assert "relationship: confluence" in material
    assert "canonical_url: https://example.com/bitcoin-etf" in material
    assert "This full raw body should not be embedded" not in material
    assert manifest["artifacts"]["event_intelligence_material"] == "analysis/event_intelligence_material.md"
    assert manifest["counts"]["event_intelligence_material_records"] == 1
    assert manifest["event_intelligence_material"]["status"] == "succeeded"


def test_event_intelligence_material_retains_accepted_and_compresses_unknown_signals(
    tmp_path: Path,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_materials",
        stage_handlers=_material_handlers({
            "collect_text_events": _noop_stage,
            "build_text_event_records": _write_event_records,
            "build_text_entity_evidence": _noop_stage,
            "build_text_event_classification_evidence": _write_classification,
            "build_text_event_topics": _write_topics,
            "build_text_event_signals": _write_many_signals,
            "build_event_market_confluence": _write_confluence,
        }),
    )

    assert result.succeeded is True
    material = (result.run.analysis_dir / "event_intelligence_material.md").read_text(encoding="utf-8")
    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))

    assert "## material_budget" in material
    assert "policy: retain_accepted_event_signals_then_sample_low_priority_records" in material
    assert "selected_records: 9" in material
    assert "omitted_records: 4" in material
    assert "low_priority_signal_budget_exceeded" in material
    assert "event_signal_id: text_event_signal:accepted-retained" in material
    assert "event_signal_id: text_event_signal:unknown-00" in material
    assert "event_signal_id: text_event_signal:unknown-11" not in material
    assert manifest["event_intelligence_material"]["material_selection"]["selected_records"] == 9
    assert manifest["event_intelligence_material"]["material_selection"]["omitted_records"] == 4
    assert manifest["event_intelligence_material"]["material_selection"]["omitted_by_status"] == {
        "unknown": 4
    }


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  output_dir: runs
market:
  enabled: false
text:
  enabled: true
  max_items: 1
  sources:
    - name: coindesk
      type: rss
      url: https://example.com/feed.xml
report:
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _material_handlers(overrides: dict[str, object]) -> dict[str, object]:
    handlers = {
        "build_alert_decision_material": _noop_stage,
        "build_decision_intelligence_material": _noop_stage,
        "build_data_quality_summary": _noop_stage,
        "build_personalized_risk_material": _noop_stage,
        "build_analysis_materials": _noop_stage,
    }
    handlers.update(overrides)
    return handlers


def _write_event_records(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "text_event_records.json",
        {
            "schema_version": 1,
            "artifact_type": "text_event_records",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:30:00Z",
            "source_artifacts": ["raw/text_events.json"],
            "model_states": [],
            "coverage": {"records": 1},
            "records": [
                {
                    "event_id": "text_event:coindesk:abc123",
                    "raw_item_id": "text:coindesk:event-1",
                    "input_type": "rss_item",
                    "source": {
                        "name": "coindesk",
                        "url": "https://example.com/feed.xml",
                    },
                    "title": "Bitcoin ETF inflow rises",
                    "content_text": "This full raw body should not be embedded in event intelligence material.",
                    "link": "https://example.com/bitcoin-etf",
                    "canonical_url": "https://example.com/bitcoin-etf",
                    "published_at": "2026-06-05T00:30:00Z",
                    "collected_at": "2026-06-05T00:31:00Z",
                    "language": "en",
                    "normalized_title": "bitcoin etf inflow rises",
                    "normalized_text": "bitcoin etf inflow rises",
                    "warnings": [],
                    "source_artifacts": ["raw/text_events.json"],
                }
            ],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["text_event_records"] = "analysis/text_event_records.json"
    return ["analysis/text_event_records.json"]


def _write_classification(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "text_event_classification_evidence.json",
        {
            "schema_version": 1,
            "artifact_type": "text_event_classification_evidence",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:30:00Z",
            "source_artifacts": [
                "analysis/text_event_records.json",
                "analysis/text_entity_evidence.json",
            ],
            "model_states": [
                {
                    "role": "classifier",
                    "provider": "transformers_zero_shot",
                    "name": "facebook/bart-large-mnli",
                    "revision": "pinned",
                    "status": "succeeded",
                    "task": "event_category_zero_shot",
                    "warnings": [],
                    "errors": [],
                }
            ],
            "coverage": {"records": 1},
            "records": [
                {
                    "event_id": "text_event:coindesk:abc123",
                    "raw_item_id": "text:coindesk:event-1",
                    "accepted_symbols": ["BTCUSDT"],
                    "category_evidence": {
                        "state": "accepted",
                        "primary_category": "etf_flows",
                        "confidence": "medium",
                        "threshold_checks": {
                            "classifier_accept_score_met": True,
                            "classifier_top_margin_met": True,
                            "rule_or_entity_evidence_met": True,
                        },
                        "candidates": [
                            {
                                "category": "etf_flows",
                                "model_score": 0.81,
                                "rank": 1,
                                "top_margin": 0.2,
                                "accepted_by_gate": True,
                                "confidence": "medium",
                                "rule_evidence": ["matched term: etf"],
                                "warnings": [],
                            }
                        ],
                        "warnings": [],
                    },
                    "financial_tone_evidence": {
                        "state": "accepted",
                        "tone": "positive",
                        "model_score": 0.87,
                        "scope": "event_text_tone_only",
                        "not_trading_signal": True,
                        "warnings": [],
                    },
                    "warnings": [],
                    "source_artifacts": [
                        "analysis/text_event_records.json",
                        "analysis/text_entity_evidence.json",
                    ],
                }
            ],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["text_event_classification_evidence"] = (
        "analysis/text_event_classification_evidence.json"
    )
    return ["analysis/text_event_classification_evidence.json"]


def _write_topics(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "text_event_topics.json",
        {
            "schema_version": 1,
            "artifact_type": "text_event_topics",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:30:00Z",
            "source_artifacts": [
                "analysis/text_event_records.json",
                "analysis/text_entity_evidence.json",
            ],
            "model_states": [],
            "coverage": {"topics": 1},
            "topics": [
                {
                    "topic_id": "text_event_topic:btcusdt:abc123",
                    "status": "succeeded",
                    "topic_label": "Bitcoin ETF inflow rises",
                    "primary_category": "unknown",
                    "symbols": ["BTCUSDT"],
                    "event_ids": ["text_event:coindesk:abc123"],
                    "primary_event_id": "text_event:coindesk:abc123",
                    "source_count": 1,
                    "event_count": 1,
                    "first_seen_at": "2026-06-05T00:30:00Z",
                    "latest_seen_at": "2026-06-05T00:30:00Z",
                    "merge_decisions": [],
                    "warnings": [],
                    "source_artifacts": [
                        "analysis/text_event_records.json",
                        "analysis/text_entity_evidence.json",
                    ],
                }
            ],
            "pair_decisions": [],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["text_event_topics"] = "analysis/text_event_topics.json"
    return ["analysis/text_event_topics.json"]


def _write_signals(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "text_event_signals.json",
        {
            "schema_version": 1,
            "artifact_type": "text_event_signals",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:30:00Z",
            "source_artifacts": [
                "analysis/text_event_records.json",
                "analysis/text_event_topics.json",
                "analysis/text_event_classification_evidence.json",
            ],
            "model_states": [],
            "coverage": {"signals": 1, "accepted_signals": 1},
            "signals": [
                {
                    "event_signal_id": "text_event_signal:btcusdt:etf_flows:abc123",
                    "status": "accepted",
                    "symbol": "BTCUSDT",
                    "relevance_scope": "symbol",
                    "topic_id": "text_event_topic:btcusdt:abc123",
                    "primary_category": "etf_flows",
                    "event_bias": "supportive",
                    "risk_impact": "neutral",
                    "opportunity_impact": "opportunity_up",
                    "strength": "medium",
                    "confidence": "medium",
                    "recency": "fresh",
                    "evidence": [
                        {
                            "type": "category_gate",
                            "state": "accepted",
                            "primary_category": "etf_flows",
                            "accepted_by_gate": True,
                        }
                    ],
                    "uncertainty": [
                        "event signal is research context, not a trading signal or price forecast"
                    ],
                    "warnings": [],
                    "source_event_ids": ["text_event:coindesk:abc123"],
                    "source_artifacts": [
                        "analysis/text_event_records.json",
                        "analysis/text_event_topics.json",
                        "analysis/text_event_classification_evidence.json",
                    ],
                }
            ],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["text_event_signals"] = "analysis/text_event_signals.json"
    return ["analysis/text_event_signals.json"]


def _write_many_signals(config, run) -> list[str]:
    signals = [
        {
            "event_signal_id": "text_event_signal:accepted-retained",
            "status": "accepted",
            "symbol": "BTCUSDT",
            "relevance_scope": "symbol",
            "topic_id": "text_event_topic:btcusdt:abc123",
            "primary_category": "etf_flows",
            "event_bias": "supportive",
            "risk_impact": "neutral",
            "opportunity_impact": "opportunity_up",
            "strength": "medium",
            "confidence": "medium",
            "recency": "fresh",
            "evidence": [
                {
                    "type": "category_gate",
                    "state": "accepted",
                    "primary_category": "etf_flows",
                    "accepted_by_gate": True,
                }
            ],
            "uncertainty": [
                "event signal is research context, not a trading signal or price forecast"
            ],
            "warnings": [],
            "source_event_ids": ["text_event:coindesk:abc123"],
            "source_artifacts": [
                "analysis/text_event_records.json",
                "analysis/text_event_topics.json",
                "analysis/text_event_classification_evidence.json",
            ],
        }
    ]
    for index in range(12):
        signals.append(
            {
                "event_signal_id": f"text_event_signal:unknown-{index:02d}",
                "status": "unknown",
                "symbol": None,
                "relevance_scope": "market_wide",
                "topic_id": "text_event_topic:btcusdt:abc123",
                "primary_category": "unknown",
                "event_bias": "unknown",
                "risk_impact": "unknown",
                "opportunity_impact": "unknown",
                "strength": "unknown",
                "confidence": "low",
                "recency": "unknown",
                "evidence": [],
                "uncertainty": ["Unknown event signal remains conservative."],
                "warnings": ["signal_status_unknown"],
                "source_event_ids": [],
                "source_artifacts": [
                    "analysis/text_event_records.json",
                    "analysis/text_event_topics.json",
                    "analysis/text_event_classification_evidence.json",
                ],
            }
        )
    write_json(
        run.analysis_dir / "text_event_signals.json",
        {
            "schema_version": 1,
            "artifact_type": "text_event_signals",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:30:00Z",
            "source_artifacts": [
                "analysis/text_event_records.json",
                "analysis/text_event_topics.json",
                "analysis/text_event_classification_evidence.json",
            ],
            "model_states": [],
            "coverage": {"signals": len(signals), "accepted_signals": 1},
            "signals": signals,
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["text_event_signals"] = "analysis/text_event_signals.json"
    return ["analysis/text_event_signals.json"]


def _write_confluence(config, run) -> list[str]:
    write_json(
        run.analysis_dir / "event_market_confluence.json",
        {
            "schema_version": 1,
            "artifact_type": "event_market_confluence",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:30:00Z",
            "source_artifacts": ["analysis/text_event_signals.json"],
            "coverage": {"records": 1, "confluence_records": 1},
            "records": [
                {
                    "confluence_id": "event_market_confluence:BTCUSDT:1d",
                    "status": "succeeded",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "relationship": "confluence",
                    "event_bias_summary": "supportive",
                    "quant_direction_summary": "bullish",
                    "decision_action_level": "TRY_SMALL",
                    "risk_effect": "do_not_upgrade",
                    "interpretation": "Accepted event evidence is supportive and current quant evidence is aligned.",
                    "watch_implications": [
                        "Use event evidence only as context; do not upgrade action levels from events alone."
                    ],
                    "evidence": [],
                    "uncertainty": [
                        "Event confluence is explanatory and must not upgrade action levels by itself."
                    ],
                    "linked_event_signal_ids": ["text_event_signal:btcusdt:etf_flows:abc123"],
                    "linked_decision_record_ids": ["decision:BTCUSDT:1d"],
                    "warnings": [],
                    "source_artifacts": ["analysis/text_event_signals.json"],
                }
            ],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["event_market_confluence"] = "analysis/event_market_confluence.json"
    return ["analysis/event_market_confluence.json"]


def _noop_stage(config, run) -> list[str]:
    return []
