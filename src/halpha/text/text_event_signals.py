from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from json import JSONDecodeError
from typing import Any

from halpha.pipeline import PipelineError, RunContext
from halpha.storage import write_json


STAGE_NAME = "build_text_event_signals"
TEXT_EVENT_RECORDS_ARTIFACT = "analysis/text_event_records.json"
TEXT_EVENT_TOPICS_ARTIFACT = "analysis/text_event_topics.json"
TEXT_EVENT_CLASSIFICATION_ARTIFACT = "analysis/text_event_classification_evidence.json"
TEXT_EVENT_SIGNALS_ARTIFACT = "analysis/text_event_signals.json"
TEXT_EVENT_SIGNALS_ARTIFACT_TYPE = "text_event_signals"
SUPPORTIVE_CATEGORIES = {"etf_flows", "institutional_adoption", "stablecoin_liquidity"}
ADVERSE_CATEGORIES = {"security_exploit", "legal_enforcement"}
MIXED_RISK_CATEGORIES = {"regulation_compliance", "derivatives_leverage"}
OPPORTUNITY_UP_CATEGORIES = {"etf_flows", "institutional_adoption", "stablecoin_liquidity", "onchain_network"}


def build_text_event_signals(config: dict[str, Any], run: RunContext) -> list[str]:
    text = config.get("text", {})
    if not text.get("enabled"):
        _record_manifest_summary(run, signals=[], warnings=[], errors=[], status="skipped")
        return []

    events_artifact = _read_artifact(
        run.analysis_dir / "text_event_records.json",
        TEXT_EVENT_RECORDS_ARTIFACT,
        required_key="records",
        previous_stage="build_text_event_records",
    )
    topics_artifact = _read_artifact(
        run.analysis_dir / "text_event_topics.json",
        TEXT_EVENT_TOPICS_ARTIFACT,
        required_key="topics",
        previous_stage="build_text_event_topics",
    )
    classification_artifact = _read_artifact(
        run.analysis_dir / "text_event_classification_evidence.json",
        TEXT_EVENT_CLASSIFICATION_ARTIFACT,
        required_key="records",
        previous_stage="build_text_event_classification_evidence",
    )
    event_index = {str(event["event_id"]): event for event in events_artifact["records"]}
    classification_index = {
        str(record["event_id"]): record for record in classification_artifact["records"] if isinstance(record, dict)
    }
    signals = [
        _signal_record(topic, event_index=event_index, classification_index=classification_index)
        for topic in topics_artifact["topics"]
    ]
    warnings = _artifact_warnings(signals)
    errors: list[dict[str, Any]] = []
    artifact = {
        "schema_version": 1,
        "artifact_type": TEXT_EVENT_SIGNALS_ARTIFACT_TYPE,
        "run_id": run.run_id,
        "created_at": _utc_timestamp(),
        "source_artifacts": [
            TEXT_EVENT_RECORDS_ARTIFACT,
            TEXT_EVENT_TOPICS_ARTIFACT,
            TEXT_EVENT_CLASSIFICATION_ARTIFACT,
        ],
        "model_states": list(classification_artifact.get("model_states") or []),
        "coverage": _coverage(signals),
        "signals": signals,
        "warnings": warnings,
        "errors": errors,
    }

    write_json(run.analysis_dir / "text_event_signals.json", artifact)
    run.manifest["artifacts"]["text_event_signals"] = TEXT_EVENT_SIGNALS_ARTIFACT
    _record_manifest_summary(run, signals=signals, warnings=warnings, errors=errors, status="succeeded")
    return [TEXT_EVENT_SIGNALS_ARTIFACT]


def _read_artifact(
    path,
    artifact_name: str,
    *,
    required_key: str,
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

    if not isinstance(artifact, dict) or not isinstance(artifact.get(required_key), list):
        raise PipelineError(
            f"{artifact_name} is invalid: {required_key} must be a list.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    return artifact


def _signal_record(
    topic: dict[str, Any],
    *,
    event_index: dict[str, dict[str, Any]],
    classification_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    event_ids = [str(event_id) for event_id in topic.get("event_ids") or []]
    classifications = [classification_index[event_id] for event_id in event_ids if event_id in classification_index]
    selected = _select_classification(classifications)
    category = _category(selected)
    category_state = str(category.get("state") or "unknown")
    primary_category = str(category.get("primary_category") or "unknown")
    confidence = _signal_confidence(category)
    topic_symbols = [str(symbol) for symbol in topic.get("symbols") or [] if str(symbol)]
    classification_symbols = _classification_symbols(selected)
    symbols = sorted({*topic_symbols, *classification_symbols})
    symbol = symbols[0] if symbols else None
    status = _signal_status(category_state)
    tone = selected.get("financial_tone_evidence") if isinstance(selected, dict) else {}
    event_bias = _event_bias(primary_category, tone if isinstance(tone, dict) else {}, status=status)
    risk_impact = _risk_impact(primary_category, status=status)
    opportunity_impact = _opportunity_impact(primary_category, status=status)
    strength = _strength(confidence, int(topic.get("event_count") or len(event_ids) or 0), status=status)
    source_events = [event_index[event_id] for event_id in event_ids if event_id in event_index]
    warnings = _signal_warnings(category, tone if isinstance(tone, dict) else {}, status=status)
    uncertainty = _uncertainty(category, tone if isinstance(tone, dict) else {}, status=status)
    evidence = _evidence(
        topic,
        selected,
        source_events=source_events,
        primary_category=primary_category,
        status=status,
    )
    return {
        "event_signal_id": _signal_id(symbol=symbol, category=primary_category, topic_id=str(topic.get("topic_id") or "")),
        "status": status,
        "symbol": symbol,
        "relevance_scope": "symbol" if symbol else "market_wide",
        "topic_id": topic.get("topic_id"),
        "primary_category": primary_category if status == "accepted" else "unknown",
        "event_bias": event_bias,
        "risk_impact": risk_impact,
        "opportunity_impact": opportunity_impact,
        "strength": strength,
        "confidence": confidence if status == "accepted" else ("low" if status == "low_confidence" else "unknown"),
        "recency": _recency(topic),
        "evidence": evidence,
        "uncertainty": uncertainty,
        "warnings": warnings,
        "source_event_ids": event_ids,
        "source_artifacts": [
            TEXT_EVENT_RECORDS_ARTIFACT,
            TEXT_EVENT_TOPICS_ARTIFACT,
            TEXT_EVENT_CLASSIFICATION_ARTIFACT,
        ],
    }


def _select_classification(classifications: list[dict[str, Any]]) -> dict[str, Any]:
    if not classifications:
        return {}

    def key(record: dict[str, Any]) -> tuple[int, float, str]:
        category = _category(record)
        state_rank = {"accepted": 2, "low_confidence": 1}.get(str(category.get("state") or "unknown"), 0)
        candidates = category.get("candidates") if isinstance(category.get("candidates"), list) else []
        score = _score(candidates[0].get("model_score")) if candidates and isinstance(candidates[0], dict) else 0.0
        return (state_rank, score, str(record.get("event_id") or ""))

    return sorted(classifications, key=key, reverse=True)[0]


def _category(record: dict[str, Any]) -> dict[str, Any]:
    category = record.get("category_evidence") if isinstance(record, dict) else {}
    return category if isinstance(category, dict) else {}


def _classification_symbols(record: dict[str, Any]) -> list[str]:
    if not isinstance(record, dict):
        return []
    return sorted({str(symbol) for symbol in record.get("accepted_symbols") or [] if str(symbol)})


def _signal_status(category_state: str) -> str:
    if category_state == "accepted":
        return "accepted"
    if category_state == "low_confidence":
        return "low_confidence"
    if category_state in {"skipped", "degraded", "failed"}:
        return category_state
    return "unknown"


def _event_bias(primary_category: str, tone: dict[str, Any], *, status: str) -> str:
    if status != "accepted":
        return "unknown"
    tone_value = str(tone.get("tone") or "unknown")
    if primary_category in SUPPORTIVE_CATEGORIES:
        return "mixed" if tone_value == "negative" else "supportive"
    if primary_category in ADVERSE_CATEGORIES:
        return "mixed" if tone_value == "positive" else "adverse"
    if primary_category in MIXED_RISK_CATEGORIES:
        return "mixed"
    return "neutral"


def _risk_impact(primary_category: str, *, status: str) -> str:
    if status != "accepted":
        return "unknown"
    if primary_category in ADVERSE_CATEGORIES or primary_category in MIXED_RISK_CATEGORIES:
        return "risk_up"
    return "neutral"


def _opportunity_impact(primary_category: str, *, status: str) -> str:
    if status != "accepted":
        return "unknown"
    if primary_category in OPPORTUNITY_UP_CATEGORIES:
        return "opportunity_up"
    if primary_category in ADVERSE_CATEGORIES:
        return "opportunity_down"
    return "neutral"


def _strength(confidence: str, event_count: int, *, status: str) -> str:
    if status != "accepted":
        return "unknown"
    if confidence == "high" and event_count >= 2:
        return "high"
    if confidence in {"high", "medium"}:
        return "medium"
    return "low"


def _signal_confidence(category: dict[str, Any]) -> str:
    confidence = str(category.get("confidence") or "unknown")
    return confidence if confidence in {"low", "medium", "high", "unknown"} else "unknown"


def _evidence(
    topic: dict[str, Any],
    classification: dict[str, Any],
    *,
    source_events: list[dict[str, Any]],
    primary_category: str,
    status: str,
) -> list[dict[str, Any]]:
    category = _category(classification)
    candidates = category.get("candidates") if isinstance(category.get("candidates"), list) else []
    top_candidate = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
    tone = classification.get("financial_tone_evidence") if isinstance(classification, dict) else {}
    evidence = [
        {
            "type": "topic_group",
            "topic_id": topic.get("topic_id"),
            "event_count": int(topic.get("event_count") or 0),
            "source_count": int(topic.get("source_count") or 0),
        },
        {
            "type": "category_gate",
            "state": str(category.get("state") or "unknown"),
            "primary_category": primary_category,
            "model_score": _score(top_candidate.get("model_score")) if top_candidate else 0.0,
            "top_margin": _score(top_candidate.get("top_margin")) if top_candidate else 0.0,
            "rule_evidence": list(top_candidate.get("rule_evidence") or []) if top_candidate else [],
            "accepted_by_gate": status == "accepted",
        },
    ]
    if isinstance(tone, dict):
        evidence.append(
            {
                "type": "financial_tone",
                "state": str(tone.get("state") or "unknown"),
                "tone": str(tone.get("tone") or "unknown"),
                "model_score": _score(tone.get("model_score")),
                "not_trading_signal": bool(tone.get("not_trading_signal")),
            }
        )
    for event in source_events[:5]:
        source = event.get("source") if isinstance(event.get("source"), dict) else {}
        evidence.append(
            {
                "type": "source_event",
                "event_id": event.get("event_id"),
                "source_name": source.get("name"),
                "canonical_url": event.get("canonical_url"),
                "published_at": event.get("published_at"),
            }
        )
    return evidence


def _uncertainty(category: dict[str, Any], tone: dict[str, Any], *, status: str) -> list[str]:
    uncertainty = []
    if status != "accepted":
        uncertainty.append("event evidence did not pass deterministic acceptance gates")
    if str(category.get("state") or "") == "low_confidence":
        uncertainty.append("category evidence is low confidence")
    if str(category.get("primary_category") or "unknown") == "unknown":
        uncertainty.append("primary event category is unknown")
    if tone and str(tone.get("state") or "") != "accepted":
        uncertainty.append("financial tone evidence is not accepted")
    uncertainty.append("event signal is research context, not a trading signal or price forecast")
    return _unique(uncertainty)


def _signal_warnings(category: dict[str, Any], tone: dict[str, Any], *, status: str) -> list[str]:
    warnings = []
    for item in (category, tone):
        for warning in item.get("warnings") or []:
            if warning not in warnings:
                warnings.append(str(warning))
    if status != "accepted":
        warnings.append(f"signal_status_{status}")
    return _unique(warnings)


def _recency(topic: dict[str, Any]) -> str:
    latest = _parse_utc(topic.get("latest_seen_at"))
    if latest is None:
        return "unknown"
    age_hours = (datetime.now(UTC) - latest).total_seconds() / 3600
    if age_hours <= 24:
        return "fresh"
    if age_hours <= 72:
        return "recent"
    return "stale"


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _coverage(signals: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "signals": len(signals),
        "accepted_signals": _status_count(signals, "accepted"),
        "low_confidence_signals": _status_count(signals, "low_confidence"),
        "unknown_signals": _status_count(signals, "unknown"),
        "skipped_signals": _status_count(signals, "skipped"),
        "degraded_signals": _status_count(signals, "degraded"),
        "rejected_signals": _status_count(signals, "rejected"),
        "failed_signals": _status_count(signals, "failed"),
        "symbol_scoped_signals": sum(1 for signal in signals if signal["relevance_scope"] == "symbol"),
        "market_wide_signals": sum(1 for signal in signals if signal["relevance_scope"] == "market_wide"),
    }


def _status_count(signals: list[dict[str, Any]], status: str) -> int:
    return sum(1 for signal in signals if signal["status"] == status)


def _record_manifest_summary(
    run: RunContext,
    *,
    signals: list[dict[str, Any]],
    warnings: list[str],
    errors: list[dict[str, Any]],
    status: str,
) -> None:
    coverage = _coverage(signals)
    run.manifest["counts"]["text_event_signals"] = coverage["signals"]
    run.manifest["counts"]["text_event_signals_accepted"] = coverage["accepted_signals"]
    run.manifest["counts"]["text_event_signals_low_confidence"] = coverage["low_confidence_signals"]
    run.manifest["counts"]["text_event_signals_unknown"] = coverage["unknown_signals"]
    run.manifest["counts"]["text_event_signals_symbol_scoped"] = coverage["symbol_scoped_signals"]
    run.manifest["counts"]["text_event_signals_market_wide"] = coverage["market_wide_signals"]
    run.manifest["text_event_signals"] = {
        "status": status,
        "artifacts": [TEXT_EVENT_SIGNALS_ARTIFACT] if status == "succeeded" else [],
        "signals": coverage["signals"],
        "accepted": coverage["accepted_signals"],
        "low_confidence": coverage["low_confidence_signals"],
        "unknown": coverage["unknown_signals"],
        "warnings": len(warnings),
        "errors": len(errors),
    }


def _artifact_warnings(signals: list[dict[str, Any]]) -> list[str]:
    warnings = []
    for signal in signals:
        for warning in signal.get("warnings") or []:
            if warning not in warnings:
                warnings.append(str(warning))
    return warnings


def _signal_id(*, symbol: str | None, category: str, topic_id: str) -> str:
    symbol_part = _slug(symbol or "market")
    category_part = _slug(category or "unknown")
    digest = hashlib.sha256(topic_id.encode("utf-8")).hexdigest()[:12]
    return f"text_event_signal:{symbol_part}:{category_part}:{digest}"


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "unknown"


def _score(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return 0.0


def _unique(values: list[str]) -> list[str]:
    unique = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return unique


def _utc_timestamp(value: datetime | None = None) -> str:
    timestamp = value or datetime.now(UTC)
    timestamp = timestamp.astimezone(UTC).replace(microsecond=0)
    return timestamp.isoformat().replace("+00:00", "Z")
