from __future__ import annotations

import json
from datetime import UTC, datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from halpha.pipeline import PipelineError, RunContext


STAGE_NAME = "build_event_intelligence_material"
TEXT_EVENT_RECORDS_ARTIFACT = "analysis/text_event_records.json"
TEXT_EVENT_CLASSIFICATION_ARTIFACT = "analysis/text_event_classification_evidence.json"
TEXT_EVENT_TOPICS_ARTIFACT = "analysis/text_event_topics.json"
TEXT_EVENT_SIGNALS_ARTIFACT = "analysis/text_event_signals.json"
EVENT_MARKET_CONFLUENCE_ARTIFACT = "analysis/event_market_confluence.json"
EVENT_INTELLIGENCE_MATERIAL_ARTIFACT = "analysis/event_intelligence_material.md"
MAX_SECTION_RECORDS = 30
MAX_EVIDENCE_ITEMS = 5
MAX_TEXT_LENGTH = 240


def build_event_intelligence_material(config: dict[str, Any], run: RunContext) -> list[str]:
    text = config.get("text", {})
    if not text.get("enabled"):
        _record_manifest_summary(run, records=0, warnings=[], errors=[], status="skipped")
        return []

    signals_artifact = _read_optional_artifact(
        run.analysis_dir / "text_event_signals.json",
        TEXT_EVENT_SIGNALS_ARTIFACT,
        records_key="signals",
    )
    if signals_artifact is None:
        _record_manifest_summary(run, records=0, warnings=[], errors=[], status="skipped")
        return []

    records_artifact = _read_required_artifact(
        run.analysis_dir / "text_event_records.json",
        TEXT_EVENT_RECORDS_ARTIFACT,
        records_key="records",
        previous_stage="build_text_event_records",
    )
    classification_artifact = _read_required_artifact(
        run.analysis_dir / "text_event_classification_evidence.json",
        TEXT_EVENT_CLASSIFICATION_ARTIFACT,
        records_key="records",
        previous_stage="build_text_event_classification_evidence",
    )
    topics_artifact = _read_required_artifact(
        run.analysis_dir / "text_event_topics.json",
        TEXT_EVENT_TOPICS_ARTIFACT,
        records_key="topics",
        previous_stage="build_text_event_topics",
    )
    confluence_artifact = _read_optional_artifact(
        run.analysis_dir / "event_market_confluence.json",
        EVENT_MARKET_CONFLUENCE_ARTIFACT,
        records_key="records",
    )

    warnings = _material_warnings(signals_artifact, confluence_artifact)
    errors: list[dict[str, Any]] = []
    material = render_event_intelligence_material(
        run,
        records_artifact=records_artifact,
        classification_artifact=classification_artifact,
        topics_artifact=topics_artifact,
        signals_artifact=signals_artifact,
        confluence_artifact=confluence_artifact,
        warnings=warnings,
    )
    output_path = run.analysis_dir / "event_intelligence_material.md"
    output_path.write_text(material, encoding="utf-8")

    signals = _records(signals_artifact, "signals")
    run.manifest["artifacts"]["event_intelligence_material"] = EVENT_INTELLIGENCE_MATERIAL_ARTIFACT
    _record_manifest_summary(run, records=len(signals), warnings=warnings, errors=errors, status="succeeded")
    return [EVENT_INTELLIGENCE_MATERIAL_ARTIFACT]


def render_event_intelligence_material(
    run: RunContext,
    *,
    records_artifact: dict[str, Any],
    classification_artifact: dict[str, Any],
    topics_artifact: dict[str, Any],
    signals_artifact: dict[str, Any],
    confluence_artifact: dict[str, Any] | None,
    warnings: list[str],
) -> str:
    events = _records(records_artifact, "records")
    classifications = _records(classification_artifact, "records")
    topics = _records(topics_artifact, "topics")
    signals = _records(signals_artifact, "signals")
    confluence = _records(confluence_artifact, "records")
    event_index = {str(event.get("event_id")): event for event in events if event.get("event_id")}
    classification_index = {
        str(record.get("event_id")): record for record in classifications if record.get("event_id")
    }
    topic_index = {str(topic.get("topic_id")): topic for topic in topics if topic.get("topic_id")}
    confluence_index = _confluence_by_signal(confluence)
    source_artifacts = _source_artifacts(confluence_artifact is not None)

    lines = [
        "---",
        "artifact_type: analysis_event_intelligence_material",
        "schema_version: 1",
        "audience: ai",
        "source_artifacts:",
        *_yaml_list(source_artifacts),
        "---",
        "",
        "# event_intelligence_material",
        "",
        "## event_source_policy",
        "",
        "```yaml",
        _yaml_block(_event_source_policy()).rstrip(),
        "```",
        "",
        "## event_model_policy",
        "",
        "```yaml",
        _yaml_block(_event_model_policy(records_artifact, classification_artifact, topics_artifact, signals_artifact)).rstrip(),
        "```",
        "",
        "## event_overview",
        "",
        "```yaml",
        _yaml_block(
            _event_overview(
                run,
                events=events,
                topics=topics,
                signals=signals,
                confluence=confluence,
                confluence_generated=confluence_artifact is not None,
                warnings=warnings,
            )
        ).rstrip(),
        "```",
        "",
        "## topic_summary",
        "",
        "```yaml",
        _yaml_block(_topic_summary(topics)).rstrip(),
        "```",
        "",
        "## event_signal_summary",
        "",
        "```yaml",
        _yaml_block(_event_signal_summary(signals)).rstrip(),
        "```",
        "",
        "## event_market_confluence",
        "",
        "```yaml",
        _yaml_block(_confluence_summary(confluence, confluence_generated=confluence_artifact is not None)).rstrip(),
        "```",
        "",
        "## risk_and_uncertainty",
        "",
        "```yaml",
        _yaml_block(_risk_and_uncertainty(signals, confluence, warnings=warnings)).rstrip(),
        "```",
        "",
        "## report_usage_rules",
        "",
        "```yaml",
        _yaml_block(_report_usage_rules()).rstrip(),
        "```",
        "",
        "## records",
        "",
    ]
    record_blocks = _material_records(
        signals,
        event_index=event_index,
        classification_index=classification_index,
        topic_index=topic_index,
        confluence_index=confluence_index,
    )
    if not record_blocks:
        lines.extend(["```yaml", _yaml_block({"records": []}).rstrip(), "```", ""])
    else:
        for record in record_blocks:
            lines.extend(
                [
                    f"### record: {record['event_signal_id']}",
                    "",
                    "```yaml",
                    _yaml_block(record).rstrip(),
                    "```",
                    "",
                ]
            )

    return "\n".join(lines).rstrip() + "\n"


def _read_optional_artifact(path: Path, artifact_name: str, *, records_key: str) -> dict[str, Any] | None:
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except JSONDecodeError as exc:
        raise PipelineError(
            f"{artifact_name} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    return _validate_artifact(artifact, artifact_name, records_key=records_key)


def _read_required_artifact(
    path: Path,
    artifact_name: str,
    *,
    records_key: str,
    previous_stage: str,
) -> dict[str, Any]:
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{artifact_name} was not found; {previous_stage} must run first.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    except JSONDecodeError as exc:
        raise PipelineError(
            f"{artifact_name} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    return _validate_artifact(artifact, artifact_name, records_key=records_key)


def _validate_artifact(artifact: Any, artifact_name: str, *, records_key: str) -> dict[str, Any]:
    if not isinstance(artifact, dict):
        raise PipelineError(f"{artifact_name} must be a JSON object.", stage=STAGE_NAME, exit_code=3)
    if not isinstance(artifact.get(records_key), list):
        raise PipelineError(f"{artifact_name} is invalid: {records_key} must be a list.", stage=STAGE_NAME, exit_code=3)
    return artifact


def _source_artifacts(include_confluence: bool) -> list[str]:
    artifacts = [
        TEXT_EVENT_RECORDS_ARTIFACT,
        TEXT_EVENT_CLASSIFICATION_ARTIFACT,
        TEXT_EVENT_TOPICS_ARTIFACT,
        TEXT_EVENT_SIGNALS_ARTIFACT,
    ]
    if include_confluence:
        artifacts.append(EVENT_MARKET_CONFLUENCE_ARTIFACT)
    return artifacts


def _event_source_policy() -> dict[str, Any]:
    return {
        "source_aware": True,
        "preserve_source_names": True,
        "preserve_links_when_available": True,
        "full_raw_feeds_embedded": False,
        "long_article_bodies_embedded": False,
        "fabricate_missing_sources": False,
        "fabricate_missing_events": False,
    }


def _event_model_policy(*artifacts: dict[str, Any]) -> dict[str, Any]:
    return {
        "pretrained_model_outputs_are_evidence_only": True,
        "halpha_deterministic_gates_are_final_authority": True,
        "model_states": _model_states(*artifacts),
        "accepted_outputs_may_still_have_uncertainty": True,
        "unknown_low_confidence_skipped_or_degraded_states_must_stay_conservative": True,
        "financial_tone_is_event_text_evidence_only": True,
        "event_signals_are_trading_signals": False,
    }


def _event_overview(
    run: RunContext,
    *,
    events: list[dict[str, Any]],
    topics: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    confluence: list[dict[str, Any]],
    confluence_generated: bool,
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "created_at": _utc_timestamp(),
        "event_records": len(events),
        "topics": len(topics),
        "event_signals": len(signals),
        "accepted_event_signals": _signal_status_count(signals, "accepted"),
        "low_confidence_event_signals": _signal_status_count(signals, "low_confidence"),
        "unknown_event_signals": _signal_status_count(signals, "unknown"),
        "event_market_confluence_generated": confluence_generated,
        "event_market_confluence_records": len(confluence),
        "confluence_records": _relationship_count(confluence, "confluence"),
        "conflict_records": _relationship_count(confluence, "conflict"),
        "insufficient_event_evidence_records": _relationship_count(confluence, "insufficient_event_evidence"),
        "warnings": warnings,
    }


def _topic_summary(topics: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "records": [
            {
                "topic_id": topic.get("topic_id"),
                "status": topic.get("status"),
                "topic_label": _bounded_text(topic.get("topic_label")),
                "symbols": _string_list(topic.get("symbols")),
                "event_count": topic.get("event_count"),
                "source_count": topic.get("source_count"),
                "first_seen_at": topic.get("first_seen_at"),
                "latest_seen_at": topic.get("latest_seen_at"),
                "merge_decisions": _topic_merge_summary(topic.get("merge_decisions")),
                "event_ids": _string_list(topic.get("event_ids"))[:MAX_EVIDENCE_ITEMS],
                "warnings": _string_list(topic.get("warnings")),
            }
            for topic in topics[:MAX_SECTION_RECORDS]
        ],
        "omitted_records": max(0, len(topics) - MAX_SECTION_RECORDS),
    }


def _event_signal_summary(signals: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "coverage": {
            "signals": len(signals),
            "accepted": _signal_status_count(signals, "accepted"),
            "low_confidence": _signal_status_count(signals, "low_confidence"),
            "unknown": _signal_status_count(signals, "unknown"),
        },
        "records": [_signal_summary(signal) for signal in signals[:MAX_SECTION_RECORDS]],
        "omitted_records": max(0, len(signals) - MAX_SECTION_RECORDS),
    }


def _confluence_summary(confluence: list[dict[str, Any]], *, confluence_generated: bool) -> dict[str, Any]:
    if not confluence_generated:
        return {
            "status": "not_generated",
            "reason": "event_market_confluence artifact was not available in this run",
            "records": [],
        }
    return {
        "status": "generated",
        "coverage": {
            "records": len(confluence),
            "confluence": _relationship_count(confluence, "confluence"),
            "conflict": _relationship_count(confluence, "conflict"),
            "independent": _relationship_count(confluence, "independent"),
            "insufficient_event_evidence": _relationship_count(confluence, "insufficient_event_evidence"),
        },
        "records": [_confluence_record(record) for record in confluence[:MAX_SECTION_RECORDS]],
        "omitted_records": max(0, len(confluence) - MAX_SECTION_RECORDS),
    }


def _risk_and_uncertainty(
    signals: list[dict[str, Any]],
    confluence: list[dict[str, Any]],
    *,
    warnings: list[str],
) -> dict[str, Any]:
    uncertainty = [
        "Event intelligence is research context, not a trading signal or price forecast.",
        "Event-market confluence is explanatory and must not upgrade action levels by itself.",
    ]
    for signal in signals:
        uncertainty.extend(_string_list(signal.get("uncertainty")))
    for record in confluence:
        uncertainty.extend(_string_list(record.get("uncertainty")))
    return {
        "uncertainty": _unique(uncertainty)[:MAX_SECTION_RECORDS],
        "warnings": _unique(warnings),
    }


def _report_usage_rules() -> dict[str, Any]:
    return {
        "codex_may_explain_event_evidence": True,
        "codex_may_explain_topic_grouping": True,
        "codex_may_explain_event_quant_confluence_or_conflict": True,
        "codex_may_generate_event_categories": False,
        "codex_may_generate_event_impacts": False,
        "codex_may_generate_event_market_relationships": False,
        "codex_may_generate_action_levels": False,
        "codex_may_generate_price_forecasts": False,
        "codex_may_generate_trading_advice": False,
        "codex_may_upgrade_low_confidence_event_evidence": False,
        "event_signals_are_trading_signals": False,
        "financial_advice": False,
    }


def _material_records(
    signals: list[dict[str, Any]],
    *,
    event_index: dict[str, dict[str, Any]],
    classification_index: dict[str, dict[str, Any]],
    topic_index: dict[str, dict[str, Any]],
    confluence_index: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    records = []
    for signal in signals[:MAX_SECTION_RECORDS]:
        signal_id = str(signal.get("event_signal_id") or "")
        source_event_ids = _string_list(signal.get("source_event_ids"))
        records.append(
            {
                "record_type": "event_intelligence_record",
                "event_signal_id": signal_id,
                "signal": _signal_summary(signal),
                "topic": _topic_record(topic_index.get(str(signal.get("topic_id") or ""))),
                "source_events": [
                    _source_event_record(event_index[event_id])
                    for event_id in source_event_ids[:MAX_EVIDENCE_ITEMS]
                    if event_id in event_index
                ],
                "classification_evidence": [
                    _classification_record(classification_index[event_id])
                    for event_id in source_event_ids[:MAX_EVIDENCE_ITEMS]
                    if event_id in classification_index
                ],
                "confluence_links": [
                    _confluence_record(record) for record in confluence_index.get(signal_id, [])[:MAX_EVIDENCE_ITEMS]
                ],
                "report_boundaries": _report_usage_rules(),
            }
        )
    return records


def _signal_summary(signal: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_signal_id": signal.get("event_signal_id"),
        "status": signal.get("status"),
        "symbol": signal.get("symbol"),
        "relevance_scope": signal.get("relevance_scope"),
        "topic_id": signal.get("topic_id"),
        "primary_category": signal.get("primary_category"),
        "event_bias": signal.get("event_bias"),
        "risk_impact": signal.get("risk_impact"),
        "opportunity_impact": signal.get("opportunity_impact"),
        "strength": signal.get("strength"),
        "confidence": signal.get("confidence"),
        "recency": signal.get("recency"),
        "source_event_ids": _string_list(signal.get("source_event_ids")),
        "evidence": _bounded_evidence(signal.get("evidence")),
        "uncertainty": _string_list(signal.get("uncertainty")),
        "warnings": _string_list(signal.get("warnings")),
    }


def _topic_record(topic: dict[str, Any] | None) -> dict[str, Any] | None:
    if topic is None:
        return None
    return {
        "topic_id": topic.get("topic_id"),
        "topic_label": _bounded_text(topic.get("topic_label")),
        "symbols": _string_list(topic.get("symbols")),
        "event_count": topic.get("event_count"),
        "source_count": topic.get("source_count"),
        "first_seen_at": topic.get("first_seen_at"),
        "latest_seen_at": topic.get("latest_seen_at"),
        "merge_decisions": _topic_merge_summary(topic.get("merge_decisions")),
        "warnings": _string_list(topic.get("warnings")),
    }


def _source_event_record(event: dict[str, Any]) -> dict[str, Any]:
    source = event.get("source") if isinstance(event.get("source"), dict) else {}
    return {
        "event_id": event.get("event_id"),
        "raw_item_id": event.get("raw_item_id"),
        "title": _bounded_text(event.get("title")),
        "source_name": source.get("name"),
        "source_url": source.get("url"),
        "link": event.get("link"),
        "canonical_url": event.get("canonical_url"),
        "published_at": event.get("published_at"),
        "collected_at": event.get("collected_at"),
        "warnings": _string_list(event.get("warnings")),
    }


def _classification_record(record: dict[str, Any]) -> dict[str, Any]:
    category = record.get("category_evidence") if isinstance(record.get("category_evidence"), dict) else {}
    tone = record.get("financial_tone_evidence") if isinstance(record.get("financial_tone_evidence"), dict) else {}
    return {
        "event_id": record.get("event_id"),
        "accepted_symbols": _string_list(record.get("accepted_symbols")),
        "category_evidence": {
            "state": category.get("state"),
            "primary_category": category.get("primary_category"),
            "confidence": category.get("confidence"),
            "threshold_checks": category.get("threshold_checks"),
            "top_candidates": _top_candidates(category.get("candidates")),
            "warnings": _string_list(category.get("warnings")),
        },
        "financial_tone_evidence": {
            "state": tone.get("state"),
            "tone": tone.get("tone"),
            "model_score": tone.get("model_score"),
            "scope": tone.get("scope"),
            "not_trading_signal": tone.get("not_trading_signal"),
            "warnings": _string_list(tone.get("warnings")),
        },
        "warnings": _string_list(record.get("warnings")),
    }


def _confluence_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "confluence_id": record.get("confluence_id"),
        "status": record.get("status"),
        "symbol": record.get("symbol"),
        "timeframe": record.get("timeframe"),
        "relationship": record.get("relationship"),
        "event_bias_summary": record.get("event_bias_summary"),
        "quant_direction_summary": record.get("quant_direction_summary"),
        "decision_action_level": record.get("decision_action_level"),
        "risk_effect": record.get("risk_effect"),
        "interpretation": record.get("interpretation"),
        "watch_implications": _string_list(record.get("watch_implications")),
        "linked_event_signal_ids": _string_list(record.get("linked_event_signal_ids")),
        "linked_decision_record_ids": _string_list(record.get("linked_decision_record_ids")),
        "uncertainty": _string_list(record.get("uncertainty")),
        "warnings": _string_list(record.get("warnings")),
    }


def _material_warnings(signals_artifact: dict[str, Any], confluence_artifact: dict[str, Any] | None) -> list[str]:
    warnings = _string_list(signals_artifact.get("warnings"))
    signals = _records(signals_artifact, "signals")
    if not any(signal.get("status") == "accepted" for signal in signals):
        warnings.append("no_accepted_event_signals_available")
    if confluence_artifact is None:
        warnings.append("event_market_confluence_not_generated")
    else:
        warnings.extend(_string_list(confluence_artifact.get("warnings")))
    return _unique(warnings)


def _model_states(*artifacts: dict[str, Any]) -> list[dict[str, Any]]:
    states = []
    seen = set()
    for artifact in artifacts:
        for state in artifact.get("model_states") or []:
            if not isinstance(state, dict):
                continue
            key = (
                state.get("role"),
                state.get("provider"),
                state.get("name"),
                state.get("revision"),
                state.get("status"),
            )
            if key in seen:
                continue
            seen.add(key)
            states.append(
                {
                    "role": state.get("role"),
                    "provider": state.get("provider"),
                    "name": state.get("name"),
                    "revision": state.get("revision"),
                    "status": state.get("status"),
                    "task": state.get("task"),
                    "warnings": _string_list(state.get("warnings")),
                    "errors": _string_list(state.get("errors")),
                }
            )
    return states


def _topic_merge_summary(value: Any) -> dict[str, Any]:
    decisions = [decision for decision in value or [] if isinstance(decision, dict)]
    return {
        "duplicate": _relationship_count(decisions, "duplicate"),
        "same_topic": _relationship_count(decisions, "same_topic"),
        "records": [
            {
                "left_event_id": decision.get("left_event_id"),
                "right_event_id": decision.get("right_event_id"),
                "relationship": decision.get("relationship"),
                "similarity": decision.get("similarity"),
                "reasons": _string_list(decision.get("reasons")),
                "methods": _string_list(decision.get("methods")),
            }
            for decision in decisions[:MAX_EVIDENCE_ITEMS]
        ],
    }


def _top_candidates(value: Any) -> list[dict[str, Any]]:
    candidates = [candidate for candidate in value or [] if isinstance(candidate, dict)]
    return [
        {
            "category": candidate.get("category"),
            "model_score": candidate.get("model_score"),
            "rank": candidate.get("rank"),
            "top_margin": candidate.get("top_margin"),
            "accepted_by_gate": candidate.get("accepted_by_gate"),
            "confidence": candidate.get("confidence"),
            "rule_evidence": _string_list(candidate.get("rule_evidence")),
            "warnings": _string_list(candidate.get("warnings")),
        }
        for candidate in candidates[:3]
    ]


def _bounded_evidence(value: Any) -> list[dict[str, Any]]:
    records = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        bounded = {}
        for key, entry in item.items():
            if isinstance(entry, str):
                bounded[key] = _bounded_text(entry)
            elif isinstance(entry, list):
                bounded[key] = [
                    _bounded_text(list_item) if isinstance(list_item, str) else list_item
                    for list_item in entry[:MAX_EVIDENCE_ITEMS]
                ]
            else:
                bounded[key] = entry
        records.append(bounded)
        if len(records) >= MAX_EVIDENCE_ITEMS:
            break
    return records


def _confluence_by_signal(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        for signal_id in _string_list(record.get("linked_event_signal_ids")):
            index.setdefault(signal_id, []).append(record)
    return index


def _records(artifact: dict[str, Any] | None, key: str) -> list[dict[str, Any]]:
    if artifact is None:
        return []
    return [record for record in artifact.get(key) or [] if isinstance(record, dict)]


def _signal_status_count(signals: list[dict[str, Any]], status: str) -> int:
    return sum(1 for signal in signals if signal.get("status") == status)


def _relationship_count(records: list[dict[str, Any]], relationship: str) -> int:
    return sum(1 for record in records if record.get("relationship") == relationship)


def _record_manifest_summary(
    run: RunContext,
    *,
    records: int,
    warnings: list[str],
    errors: list[dict[str, Any]],
    status: str,
) -> None:
    run.manifest["counts"]["event_intelligence_material_records"] = records
    run.manifest["event_intelligence_material"] = {
        "status": status,
        "artifacts": [EVENT_INTELLIGENCE_MATERIAL_ARTIFACT] if status == "succeeded" else [],
        "records": records,
        "warnings": len(warnings),
        "errors": len(errors),
    }


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def _unique(values: list[str]) -> list[str]:
    unique = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return unique


def _bounded_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    if len(cleaned) <= MAX_TEXT_LENGTH:
        return cleaned
    return f"{cleaned[: MAX_TEXT_LENGTH - 3]}..."


def _yaml_list(values: list[str]) -> list[str]:
    if not values:
        return ["  []"]
    return [f"  - {value}" for value in values]


def _yaml_block(data: dict[str, Any]) -> str:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise PipelineError(
            "PyYAML is required to write YAML event intelligence material.",
            stage=STAGE_NAME,
            exit_code=1,
        ) from exc

    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def _utc_timestamp(value: datetime | None = None) -> str:
    timestamp = value or datetime.now(UTC)
    timestamp = timestamp.astimezone(UTC).replace(microsecond=0)
    return timestamp.isoformat().replace("+00:00", "Z")
