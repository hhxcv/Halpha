from __future__ import annotations

import json
from datetime import UTC, datetime
from json import JSONDecodeError
from typing import Any

from halpha.pipeline import PipelineError, RunContext
from halpha.storage import write_json


STAGE_NAME = "build_text_event_classification_evidence"
TEXT_EVENT_RECORDS_ARTIFACT = "analysis/text_event_records.json"
TEXT_ENTITY_EVIDENCE_ARTIFACT = "analysis/text_entity_evidence.json"
TEXT_EVENT_CLASSIFICATION_ARTIFACT = "analysis/text_event_classification_evidence.json"
TEXT_EVENT_CLASSIFICATION_ARTIFACT_TYPE = "text_event_classification_evidence"
EVENT_TAXONOMY = [
    "etf_flows",
    "regulation_compliance",
    "macro_policy",
    "monetary_policy",
    "stablecoin_liquidity",
    "exchange_market_structure",
    "security_exploit",
    "institutional_adoption",
    "derivatives_leverage",
    "onchain_network",
    "legal_enforcement",
    "other",
]
FINANCIAL_TONES = {"positive", "negative", "neutral"}
FINANCIAL_TONE_ACCEPT_SCORE = 0.55
CATEGORY_RULE_TERMS = {
    "etf_flows": ("bitcoin etf", "btc etf", "spot etf", "etf inflow", "etf outflow", "etf flow"),
    "regulation_compliance": ("regulation", "regulatory", "compliance", "regulator", "aml", "kyc"),
    "macro_policy": ("macro", "fiscal", "treasury", "gdp", "cpi", "inflation"),
    "monetary_policy": ("federal reserve", "interest rate", "rate cut", "rate hike", "monetary policy"),
    "stablecoin_liquidity": ("stablecoin", "usdt", "usdc", "tether", "circle"),
    "exchange_market_structure": ("exchange", "order book", "listing", "delisting", "market maker"),
    "security_exploit": ("hack", "exploit", "vulnerability", "stolen", "bridge attack"),
    "institutional_adoption": ("institutional", "blackrock", "fidelity", "adoption", "treasury company"),
    "derivatives_leverage": ("futures", "options", "leverage", "liquidation", "open interest"),
    "onchain_network": ("onchain", "validator", "staking", "gas fee", "hash rate", "network activity"),
    "legal_enforcement": ("lawsuit", "court", "indictment", "enforcement", "settlement"),
}


def build_text_event_classification_evidence(config: dict[str, Any], run: RunContext) -> list[str]:
    text = config.get("text", {})
    if not text.get("enabled"):
        _record_manifest_summary(
            run,
            records=[],
            warnings=[],
            errors=[],
            status="skipped",
            model_states=[],
        )
        return []

    event_artifact = _read_artifact(
        run.analysis_dir / "text_event_records.json",
        TEXT_EVENT_RECORDS_ARTIFACT,
        required_records_key="records",
        previous_stage="build_text_event_records",
    )
    entity_artifact = _read_artifact(
        run.analysis_dir / "text_entity_evidence.json",
        TEXT_ENTITY_EVIDENCE_ARTIFACT,
        required_records_key="records",
        previous_stage="build_text_entity_evidence",
    )
    event_records = list(event_artifact["records"])
    entity_index = _entity_index(entity_artifact["records"])
    classifier_state, classifier = _load_classifier_model(config)
    sentiment_state, sentiment = _load_sentiment_model(config)
    records = [
        _classification_record(
            event,
            entity_index=entity_index,
            classifier=classifier,
            classifier_state=classifier_state,
            sentiment=sentiment,
            sentiment_state=sentiment_state,
            config=config,
        )
        for event in event_records
    ]
    warnings = _artifact_warnings(records, [classifier_state, sentiment_state])
    errors: list[dict[str, Any]] = []
    artifact = {
        "schema_version": 1,
        "artifact_type": TEXT_EVENT_CLASSIFICATION_ARTIFACT_TYPE,
        "run_id": run.run_id,
        "created_at": _utc_timestamp(),
        "source_artifacts": [TEXT_EVENT_RECORDS_ARTIFACT, TEXT_ENTITY_EVIDENCE_ARTIFACT],
        "model_states": [classifier_state, sentiment_state],
        "coverage": _coverage(records),
        "records": records,
        "warnings": warnings,
        "errors": errors,
    }

    write_json(run.analysis_dir / "text_event_classification_evidence.json", artifact)
    run.manifest["artifacts"]["text_event_classification_evidence"] = TEXT_EVENT_CLASSIFICATION_ARTIFACT
    _record_manifest_summary(
        run,
        records=records,
        warnings=warnings,
        errors=errors,
        status="succeeded",
        model_states=[classifier_state, sentiment_state],
    )
    return [TEXT_EVENT_CLASSIFICATION_ARTIFACT]


def _read_artifact(
    path,
    artifact_name: str,
    *,
    required_records_key: str,
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

    if not isinstance(artifact, dict) or not isinstance(artifact.get(required_records_key), list):
        raise PipelineError(
            f"{artifact_name} is invalid: {required_records_key} must be a list.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    return artifact


def _classification_record(
    event: dict[str, Any],
    *,
    entity_index: dict[str, dict[str, Any]],
    classifier: Any | None,
    classifier_state: dict[str, Any],
    sentiment: Any | None,
    sentiment_state: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    event_id = str(event["event_id"])
    accepted_symbols = list(entity_index.get(event_id, {}).get("accepted_symbols") or [])
    category_evidence = _category_evidence(
        event,
        classifier=classifier,
        model_state=classifier_state,
        accepted_symbols=accepted_symbols,
        config=config,
    )
    tone_evidence = _financial_tone_evidence(event, sentiment=sentiment, model_state=sentiment_state)
    warnings = _record_warnings(category_evidence, tone_evidence)
    return {
        "event_id": event_id,
        "raw_item_id": event.get("raw_item_id"),
        "accepted_symbols": accepted_symbols,
        "category_evidence": category_evidence,
        "financial_tone_evidence": tone_evidence,
        "warnings": warnings,
        "source_artifacts": [TEXT_EVENT_RECORDS_ARTIFACT, TEXT_ENTITY_EVIDENCE_ARTIFACT],
    }


def _category_evidence(
    event: dict[str, Any],
    *,
    classifier: Any | None,
    model_state: dict[str, Any],
    accepted_symbols: list[str],
    config: dict[str, Any],
) -> dict[str, Any]:
    thresholds = _classifier_thresholds(config)
    rule_evidence = _category_rule_evidence(event)
    if classifier is None:
        return _unknown_category_evidence(
            state="unknown",
            model_state=model_state,
            thresholds=thresholds,
            rule_evidence=rule_evidence,
            warnings=[_model_unavailable_warning("classifier", model_state)],
        )

    try:
        output = classifier(_event_text(event), candidate_labels=EVENT_TAXONOMY)
    except Exception as exc:  # pragma: no cover - depends on optional runtime behavior.
        degraded_state = {
            **model_state,
            "status": "degraded",
            "warnings": [*model_state.get("warnings", []), "classifier failed during local inference"],
            "errors": [*model_state.get("errors", []), f"{exc.__class__.__name__}: {exc}"],
        }
        return _unknown_category_evidence(
            state="unknown",
            model_state=degraded_state,
            thresholds=thresholds,
            rule_evidence=rule_evidence,
            warnings=["classifier failed during local inference"],
        )

    candidates = _category_candidates(output, model_state=model_state, rule_evidence=rule_evidence)
    top_candidate = candidates[0] if candidates else None
    top_score = _score(top_candidate.get("model_score") if top_candidate else None)
    top_margin = _score(top_candidate.get("top_margin") if top_candidate else None)
    score_met = top_score >= thresholds["classifier_accept_score"]
    margin_met = top_margin >= thresholds["classifier_top_margin"]
    evidence_met = bool(top_candidate and (top_candidate["rule_evidence"] or accepted_symbols))
    accepted = bool(top_candidate and score_met and margin_met and evidence_met)
    warnings = _category_warnings(
        score_met=score_met,
        margin_met=margin_met,
        evidence_met=evidence_met,
        has_candidate=bool(top_candidate),
    )
    for candidate in candidates:
        candidate["accepted_by_gate"] = bool(candidate is top_candidate and accepted)
        candidate["warnings"] = [] if candidate["accepted_by_gate"] else list(warnings)
    state = "accepted" if accepted else "low_confidence"
    return {
        "state": state,
        "primary_category": str(top_candidate["category"]) if accepted and top_candidate else "unknown",
        "confidence": _category_confidence(top_score, top_margin, accepted=accepted),
        "threshold_checks": {
            "classifier_accept_score_met": score_met,
            "classifier_top_margin_met": margin_met,
            "rule_or_entity_evidence_met": evidence_met,
        },
        "candidates": candidates,
        "rule_evidence": rule_evidence,
        "model": _model_ref(model_state),
        "warnings": warnings,
    }


def _unknown_category_evidence(
    *,
    state: str,
    model_state: dict[str, Any],
    thresholds: dict[str, float],
    rule_evidence: dict[str, list[str]],
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "state": state,
        "primary_category": "unknown",
        "confidence": "low",
        "threshold_checks": {
            "classifier_accept_score_met": False,
            "classifier_top_margin_met": False,
            "rule_or_entity_evidence_met": bool(_flatten_rule_evidence(rule_evidence)),
        },
        "candidates": [],
        "rule_evidence": rule_evidence,
        "model": _model_ref(model_state),
        "thresholds": thresholds,
        "warnings": [warning for warning in warnings if warning],
    }


def _category_candidates(
    output: Any,
    *,
    model_state: dict[str, Any],
    rule_evidence: dict[str, list[str]],
) -> list[dict[str, Any]]:
    if not isinstance(output, dict):
        return []
    labels = output.get("labels") if isinstance(output.get("labels"), list) else []
    scores = output.get("scores") if isinstance(output.get("scores"), list) else []
    rows = [
        (str(label), _score(score))
        for label, score in zip(labels, scores)
        if str(label) in EVENT_TAXONOMY
    ]
    rows.sort(key=lambda item: (-item[1], item[0]))
    top_score = rows[0][1] if rows else 0.0
    second_score = rows[1][1] if len(rows) > 1 else 0.0
    top_margin = max(0.0, top_score - second_score)
    return [
        {
            "event_id": str(output.get("event_id") or ""),
            "category": label,
            "model_score": _round_score(score),
            "rank": index + 1,
            "top_margin": _round_score(top_margin if index == 0 else max(0.0, score - second_score)),
            "rule_evidence": list(rule_evidence.get(label) or []),
            "accepted_by_gate": False,
            "confidence": _candidate_confidence(score),
            "model": _model_ref(model_state),
            "warnings": [],
        }
        for index, (label, score) in enumerate(rows[:5])
    ]


def _financial_tone_evidence(
    event: dict[str, Any],
    *,
    sentiment: Any | None,
    model_state: dict[str, Any],
) -> dict[str, Any]:
    if sentiment is None:
        return _unknown_tone_evidence(
            state="unknown",
            model_state=model_state,
            warnings=[_model_unavailable_warning("sentiment", model_state)],
        )

    try:
        output = sentiment(_event_text(event))
    except Exception as exc:  # pragma: no cover - depends on optional runtime behavior.
        degraded_state = {
            **model_state,
            "status": "degraded",
            "warnings": [*model_state.get("warnings", []), "sentiment model failed during local inference"],
            "errors": [*model_state.get("errors", []), f"{exc.__class__.__name__}: {exc}"],
        }
        return _unknown_tone_evidence(
            state="unknown",
            model_state=degraded_state,
            warnings=["sentiment model failed during local inference"],
        )

    candidate = _tone_candidate(output, model_state=model_state)
    if candidate is None:
        return _unknown_tone_evidence(
            state="unknown",
            model_state=model_state,
            warnings=["sentiment model returned no usable financial tone label"],
        )
    accepted = candidate["model_score"] >= FINANCIAL_TONE_ACCEPT_SCORE and candidate["tone"] in FINANCIAL_TONES
    warnings = [] if accepted else ["financial_tone_score_below_threshold"]
    return {
        "state": "accepted" if accepted else "low_confidence",
        "tone": candidate["tone"] if accepted else "unknown",
        "raw_label": candidate["raw_label"],
        "model_score": candidate["model_score"],
        "confidence": _tone_confidence(candidate["model_score"], accepted=accepted),
        "threshold_checks": {
            "financial_tone_accept_score_met": accepted,
        },
        "model": _model_ref(model_state),
        "scope": "event_text_tone_only",
        "not_trading_signal": True,
        "warnings": warnings,
    }


def _unknown_tone_evidence(
    *,
    state: str,
    model_state: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "state": state,
        "tone": "unknown",
        "raw_label": None,
        "model_score": 0.0,
        "confidence": "low",
        "threshold_checks": {
            "financial_tone_accept_score_met": False,
        },
        "model": _model_ref(model_state),
        "scope": "event_text_tone_only",
        "not_trading_signal": True,
        "warnings": [warning for warning in warnings if warning],
    }


def _tone_candidate(output: Any, *, model_state: dict[str, Any]) -> dict[str, Any] | None:
    rows = output
    if isinstance(rows, list) and rows and isinstance(rows[0], list):
        rows = rows[0]
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        return None
    candidates = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_label = str(row.get("label") or "").strip()
        tone = _normalize_tone(raw_label)
        candidates.append(
            {
                "tone": tone,
                "raw_label": raw_label,
                "model_score": _round_score(_score(row.get("score"))),
                "model": _model_ref(model_state),
            }
        )
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (-item["model_score"], item["tone"]))[0]


def _load_classifier_model(config: dict[str, Any]) -> tuple[dict[str, Any], Any | None]:
    return _load_transformers_pipeline(
        config,
        role="classifier",
        task="zero-shot-classification",
        warning_role="classifier",
    )


def _load_sentiment_model(config: dict[str, Any]) -> tuple[dict[str, Any], Any | None]:
    return _load_transformers_pipeline(
        config,
        role="sentiment",
        task="text-classification",
        warning_role="sentiment",
    )


def _load_transformers_pipeline(
    config: dict[str, Any],
    *,
    role: str,
    task: str,
    warning_role: str,
) -> tuple[dict[str, Any], Any | None]:
    model_config = _model_config(config, role)
    thresholds = _model_thresholds(config, role)
    state = _model_state(model_config, role=role, task=task, status="skipped", warnings=[], errors=[], thresholds=thresholds)
    intelligence = _text_intelligence_config(config)
    if not intelligence.get("enabled"):
        return {**state, "warnings": ["text_intelligence_disabled"]}, None
    if not model_config:
        return {**state, "warnings": [f"{warning_role}_model_not_configured"]}, None

    try:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline
    except ModuleNotFoundError:
        return _model_state(
            model_config,
            role=role,
            task=task,
            status="unavailable",
            warnings=["optional transformers runtime is not installed"],
            errors=[],
            thresholds=thresholds,
        ), None

    try:
        model = AutoModelForSequenceClassification.from_pretrained(
            model_config["name"],
            revision=model_config["revision"],
            local_files_only=True,
        )
        tokenizer = AutoTokenizer.from_pretrained(
            model_config["name"],
            revision=model_config["revision"],
            local_files_only=True,
        )
        model_pipeline = pipeline(task, model=model, tokenizer=tokenizer)
    except Exception as exc:  # pragma: no cover - depends on optional runtime/model cache.
        return _model_state(
            model_config,
            role=role,
            task=task,
            status="unavailable",
            warnings=[f"configured {warning_role} model is unavailable in the local model cache"],
            errors=[f"{exc.__class__.__name__}: {exc}"],
            thresholds=thresholds,
        ), None

    return _model_state(
        model_config,
        role=role,
        task=task,
        status="succeeded",
        warnings=[],
        errors=[],
        thresholds=thresholds,
    ), model_pipeline


def _entity_index(entity_records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for record in entity_records:
        if not isinstance(record, dict):
            continue
        event_id = str(record.get("event_id") or "")
        accepted_symbols = sorted(
            {
                str(relevance.get("symbol")).upper()
                for relevance in record.get("asset_relevance") or []
                if isinstance(relevance, dict)
                and relevance.get("state") == "accepted"
                and isinstance(relevance.get("symbol"), str)
                and relevance.get("symbol")
            }
        )
        index[event_id] = {"accepted_symbols": accepted_symbols}
    return index


def _category_rule_evidence(event: dict[str, Any]) -> dict[str, list[str]]:
    text = _event_text(event).lower()
    evidence = {}
    for category, terms in CATEGORY_RULE_TERMS.items():
        matches = [f"matched term: {term}" for term in terms if term in text]
        if matches:
            evidence[category] = matches
    return evidence


def _category_warnings(
    *,
    score_met: bool,
    margin_met: bool,
    evidence_met: bool,
    has_candidate: bool,
) -> list[str]:
    warnings = []
    if not has_candidate:
        warnings.append("classifier_returned_no_supported_category")
        return warnings
    if not score_met:
        warnings.append("classifier_score_below_threshold")
    if not margin_met:
        warnings.append("classifier_top_margin_below_threshold")
    if not evidence_met:
        warnings.append("category_rule_or_entity_evidence_missing")
    return warnings


def _record_warnings(category_evidence: dict[str, Any], tone_evidence: dict[str, Any]) -> list[str]:
    warnings = []
    for item in (category_evidence, tone_evidence):
        for warning in item.get("warnings") or []:
            if warning not in warnings:
                warnings.append(str(warning))
    return warnings


def _artifact_warnings(records: list[dict[str, Any]], model_states: list[dict[str, Any]]) -> list[str]:
    warnings = []
    for state in model_states:
        for warning in state.get("warnings") or []:
            if warning not in warnings:
                warnings.append(str(warning))
    for record in records:
        for warning in record.get("warnings") or []:
            if warning not in warnings:
                warnings.append(str(warning))
    return warnings


def _coverage(records: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "events": len(records),
        "records": len(records),
        "category_candidate_evidence": sum(len(record["category_evidence"]["candidates"]) for record in records),
        "accepted_category_records": sum(
            1 for record in records if record["category_evidence"]["state"] == "accepted"
        ),
        "low_confidence_category_records": sum(
            1 for record in records if record["category_evidence"]["state"] == "low_confidence"
        ),
        "unknown_category_records": sum(
            1 for record in records if record["category_evidence"]["primary_category"] == "unknown"
        ),
        "financial_tone_evidence": sum(
            1 for record in records if record["financial_tone_evidence"]["state"] != "unknown"
        ),
        "accepted_financial_tone_records": sum(
            1 for record in records if record["financial_tone_evidence"]["state"] == "accepted"
        ),
        "low_confidence_financial_tone_records": sum(
            1 for record in records if record["financial_tone_evidence"]["state"] == "low_confidence"
        ),
    }


def _record_manifest_summary(
    run: RunContext,
    *,
    records: list[dict[str, Any]],
    warnings: list[str],
    errors: list[dict[str, Any]],
    status: str,
    model_states: list[dict[str, Any]],
) -> None:
    coverage = _coverage(records)
    run.manifest["counts"]["text_event_classification_records"] = len(records)
    run.manifest["counts"]["text_event_category_candidate_evidence"] = coverage["category_candidate_evidence"]
    run.manifest["counts"]["text_event_category_accepted"] = coverage["accepted_category_records"]
    run.manifest["counts"]["text_event_category_low_confidence"] = coverage["low_confidence_category_records"]
    run.manifest["counts"]["text_event_category_unknown"] = coverage["unknown_category_records"]
    run.manifest["counts"]["text_event_financial_tone_evidence"] = coverage["financial_tone_evidence"]
    run.manifest["counts"]["text_event_financial_tone_accepted"] = coverage["accepted_financial_tone_records"]
    run.manifest["counts"]["text_event_financial_tone_low_confidence"] = coverage[
        "low_confidence_financial_tone_records"
    ]
    run.manifest["text_event_classification_evidence"] = {
        "status": status,
        "artifacts": [TEXT_EVENT_CLASSIFICATION_ARTIFACT] if status == "succeeded" else [],
        "records": len(records),
        "category_candidates": coverage["category_candidate_evidence"],
        "accepted_categories": coverage["accepted_category_records"],
        "financial_tone_evidence": coverage["financial_tone_evidence"],
        "model_states": [state["status"] for state in model_states],
        "warnings": len(warnings),
        "errors": len(errors),
    }


def _model_state(
    model_config: dict[str, Any],
    *,
    role: str,
    task: str,
    status: str,
    warnings: list[str],
    errors: list[str],
    thresholds: dict[str, Any],
) -> dict[str, Any]:
    return {
        "role": role,
        "provider": str(model_config.get("provider") or _default_provider(role)),
        "name": str(model_config.get("name") or ""),
        "revision": str(model_config.get("revision") or ""),
        "status": status,
        "task": _model_task(role, task),
        "thresholds": thresholds,
        "warnings": warnings,
        "errors": errors,
    }


def _model_thresholds(config: dict[str, Any], role: str) -> dict[str, Any]:
    if role == "classifier":
        thresholds = _classifier_thresholds(config)
        return {
            "classifier_accept_score": thresholds["classifier_accept_score"],
            "classifier_top_margin": thresholds["classifier_top_margin"],
        }
    if role == "sentiment":
        return {"financial_tone_accept_score": FINANCIAL_TONE_ACCEPT_SCORE}
    return {}


def _classifier_thresholds(config: dict[str, Any]) -> dict[str, float]:
    intelligence = _text_intelligence_config(config)
    thresholds = intelligence.get("thresholds") if isinstance(intelligence.get("thresholds"), dict) else {}
    return {
        "classifier_accept_score": _score(thresholds.get("classifier_accept_score"), default=0.65),
        "classifier_top_margin": _score(thresholds.get("classifier_top_margin"), default=0.10),
    }


def _model_config(config: dict[str, Any], role: str) -> dict[str, Any]:
    intelligence = _text_intelligence_config(config)
    models = intelligence.get("models") if isinstance(intelligence.get("models"), dict) else {}
    model = models.get(role) if isinstance(models.get(role), dict) else {}
    return model


def _text_intelligence_config(config: dict[str, Any]) -> dict[str, Any]:
    text = config.get("text") if isinstance(config.get("text"), dict) else {}
    intelligence = text.get("intelligence") if isinstance(text.get("intelligence"), dict) else {}
    return intelligence


def _model_ref(model_state: dict[str, Any]) -> dict[str, str | None]:
    if not model_state.get("name"):
        return None
    return {
        "provider": str(model_state["provider"]),
        "name": str(model_state["name"]),
        "revision": str(model_state["revision"]),
    }


def _model_task(role: str, task: str) -> str:
    if role == "classifier":
        return "event_category_zero_shot"
    if role == "sentiment":
        return "financial_tone_classification"
    return task


def _default_provider(role: str) -> str:
    if role == "classifier":
        return "transformers_zero_shot"
    if role == "sentiment":
        return "transformers_text_classification"
    return "transformers"


def _model_unavailable_warning(role: str, model_state: dict[str, Any]) -> str:
    status = str(model_state.get("status") or "skipped")
    if status == "succeeded":
        return ""
    return f"{role}_model_{status}"


def _event_text(event: dict[str, Any]) -> str:
    values = [
        event.get("title"),
        event.get("content_text"),
        event.get("normalized_text"),
    ]
    text = " ".join(str(value) for value in values if isinstance(value, str) and value.strip()).strip()
    return text or str(event.get("event_id") or "")


def _flatten_rule_evidence(rule_evidence: dict[str, list[str]]) -> list[str]:
    return [item for values in rule_evidence.values() for item in values]


def _category_confidence(score: float, top_margin: float, *, accepted: bool) -> str:
    if not accepted:
        return "low"
    if score >= 0.80 and top_margin >= 0.20:
        return "high"
    return "medium"


def _candidate_confidence(score: float) -> str:
    if score >= 0.80:
        return "high"
    if score >= 0.65:
        return "medium"
    return "low"


def _tone_confidence(score: float, *, accepted: bool) -> str:
    if not accepted:
        return "low"
    if score >= 0.80:
        return "high"
    return "medium"


def _normalize_tone(label: str) -> str:
    normalized = label.strip().lower()
    if "positive" in normalized:
        return "positive"
    if "negative" in normalized:
        return "negative"
    if "neutral" in normalized:
        return "neutral"
    return "unknown"


def _score(value: Any, *, default: float = 0.0) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return default


def _round_score(value: float | None) -> float:
    if value is None:
        return 0.0
    return round(float(value), 6)


def _utc_timestamp(value: datetime | None = None) -> str:
    timestamp = value or datetime.now(UTC)
    timestamp = timestamp.astimezone(UTC).replace(microsecond=0)
    return timestamp.isoformat().replace("+00:00", "Z")
