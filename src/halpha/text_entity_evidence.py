from __future__ import annotations

import inspect
import json
import re
from datetime import UTC, datetime
from json import JSONDecodeError
from typing import Any

from .pipeline import PipelineError, RunContext
from .storage import write_json


STAGE_NAME = "build_text_entity_evidence"
TEXT_EVENT_RECORDS_ARTIFACT = "analysis/text_event_records.json"
TEXT_ENTITY_EVIDENCE_ARTIFACT = "analysis/text_entity_evidence.json"
TEXT_ENTITY_EVIDENCE_ARTIFACT_TYPE = "text_entity_evidence"
NER_LABELS = [
    "asset",
    "organization",
    "regulator",
    "exchange",
    "fund",
    "protocol",
    "person",
    "location",
]
KNOWN_QUOTES = ("USDT", "USDC", "FDUSD", "BUSD", "USD", "BTC", "ETH")
BASE_ASSET_ALIASES = {
    "BTC": {"bitcoin", "btc", "xbt"},
    "ETH": {"ethereum", "ether", "eth"},
    "SOL": {"solana", "sol"},
    "BNB": {"bnb", "binance coin"},
    "XRP": {"xrp", "ripple"},
    "ADA": {"ada", "cardano"},
    "DOGE": {"doge", "dogecoin"},
}


def build_text_entity_evidence(config: dict[str, Any], run: RunContext) -> list[str]:
    text = config.get("text", {})
    if not text.get("enabled"):
        _record_manifest_summary(run, records=[], warnings=[], errors=[], status="skipped", model_states=[])
        return []

    event_records = _read_text_event_records(run)
    model_state, model_entities = _model_entity_evidence(event_records["records"], config)
    records = [
        _evidence_record(event, config=config, model_entities=model_entities.get(event["event_id"], []))
        for event in event_records["records"]
    ]
    warnings = _artifact_warnings(records, model_state)
    errors: list[dict[str, Any]] = []
    artifact = {
        "schema_version": 1,
        "artifact_type": TEXT_ENTITY_EVIDENCE_ARTIFACT_TYPE,
        "run_id": run.run_id,
        "created_at": _utc_timestamp(),
        "source_artifacts": [TEXT_EVENT_RECORDS_ARTIFACT],
        "model_states": [model_state],
        "coverage": _coverage(records),
        "records": records,
        "warnings": warnings,
        "errors": errors,
    }

    write_json(run.analysis_dir / "text_entity_evidence.json", artifact)
    run.manifest["artifacts"]["text_entity_evidence"] = TEXT_ENTITY_EVIDENCE_ARTIFACT
    _record_manifest_summary(run, records=records, warnings=warnings, errors=errors, status="succeeded", model_states=[model_state])
    return [TEXT_ENTITY_EVIDENCE_ARTIFACT]


def _read_text_event_records(run: RunContext) -> dict[str, Any]:
    path = run.analysis_dir / "text_event_records.json"
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{TEXT_EVENT_RECORDS_ARTIFACT} was not found; build_text_event_records must run first.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    except JSONDecodeError as exc:
        raise PipelineError(
            f"{TEXT_EVENT_RECORDS_ARTIFACT} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc

    if not isinstance(artifact, dict) or not isinstance(artifact.get("records"), list):
        raise PipelineError(
            f"{TEXT_EVENT_RECORDS_ARTIFACT} is invalid: records must be a list.",
            stage=STAGE_NAME,
            exit_code=3,
        )
    return artifact


def _evidence_record(
    event: dict[str, Any],
    *,
    config: dict[str, Any],
    model_entities: list[dict[str, Any]],
) -> dict[str, Any]:
    rule_entities, asset_relevance = _rule_entity_and_asset_evidence(event, config)
    entity_evidence = [*rule_entities, *model_entities]
    warnings = _record_warnings(asset_relevance, entity_evidence)
    return {
        "event_id": event["event_id"],
        "raw_item_id": event.get("raw_item_id"),
        "entity_evidence": entity_evidence,
        "asset_relevance": asset_relevance,
        "warnings": warnings,
        "source_artifacts": [TEXT_EVENT_RECORDS_ARTIFACT],
    }


def _rule_entity_and_asset_evidence(
    event: dict[str, Any],
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    text = _event_text(event)
    alias_index = _asset_alias_index(config)
    entity_evidence = []
    asset_relevance = []
    seen_entity_keys = set()

    for alias in sorted(alias_index, key=lambda value: (-len(value), value)):
        matches = _alias_matches(text, alias)
        if not matches:
            continue

        candidates = alias_index[alias]
        matched_text = matches[0]
        if len(candidates) == 1:
            candidate = candidates[0]
            relevance = _accepted_asset_relevance(event, alias, matched_text, candidate)
        else:
            relevance = _ambiguous_asset_relevance(event, alias, matched_text, candidates)
        asset_relevance.append(relevance)

        entity_key = (matched_text.lower(), "asset")
        if entity_key in seen_entity_keys:
            continue
        seen_entity_keys.add(entity_key)
        entity_evidence.append(
            {
                "event_id": event["event_id"],
                "text": matched_text,
                "label": "asset",
                "score": 1.0,
                "accepted": relevance["state"] == "accepted",
                "method": "deterministic_asset_alias_rule",
                "model": None,
                "matched_rules": relevance["matched_rules"],
                "asset_relevance": {
                    "state": relevance["state"],
                    "symbol": relevance.get("symbol"),
                    "candidate_symbols": relevance.get("candidate_symbols", []),
                    "confidence": relevance["confidence"],
                },
                "warnings": list(relevance.get("warnings") or []),
            }
        )

    return entity_evidence, asset_relevance


def _accepted_asset_relevance(
    event: dict[str, Any],
    alias: str,
    matched_text: str,
    candidate: dict[str, str],
) -> dict[str, Any]:
    return {
        "event_id": event["event_id"],
        "symbol": candidate["symbol"],
        "asset": candidate["base_asset"],
        "state": "accepted",
        "confidence": "high",
        "score": 1.0,
        "matched_aliases": [alias],
        "matched_text": matched_text,
        "matched_rules": [f"asset_alias:{alias}", f"configured_symbol:{candidate['symbol']}"],
        "candidate_symbols": [candidate["symbol"]],
        "warnings": [],
    }


def _ambiguous_asset_relevance(
    event: dict[str, Any],
    alias: str,
    matched_text: str,
    candidates: list[dict[str, str]],
) -> dict[str, Any]:
    candidate_symbols = sorted(candidate["symbol"] for candidate in candidates)
    candidate_assets = sorted({candidate["base_asset"] for candidate in candidates})
    return {
        "event_id": event["event_id"],
        "symbol": None,
        "asset": candidate_assets[0] if len(candidate_assets) == 1 else alias.upper(),
        "state": "unknown",
        "confidence": "low",
        "score": 0.0,
        "matched_aliases": [alias],
        "matched_text": matched_text,
        "matched_rules": [f"ambiguous_asset_alias:{alias}"],
        "candidate_symbols": candidate_symbols,
        "warnings": [
            f"asset alias {alias} matched multiple configured symbols: {', '.join(candidate_symbols)}."
        ],
    }


def _model_entity_evidence(
    event_records: list[dict[str, Any]],
    config: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    state, model = _load_ner_model(config)
    if model is None:
        return state, {}

    threshold = _entity_threshold(config)
    evidence_by_event: dict[str, list[dict[str, Any]]] = {}
    errors = []
    for event in event_records:
        try:
            entities = model.predict_entities(_event_text(event), NER_LABELS, threshold=threshold)
        except Exception as exc:  # pragma: no cover - depends on optional runtime behavior.
            errors.append(f"{event['event_id']}: {exc.__class__.__name__}: {exc}")
            continue
        evidence_by_event[event["event_id"]] = [
            _model_entity_record(event, entity, threshold=threshold, model_state=state)
            for entity in entities
            if isinstance(entity, dict)
        ]

    if errors:
        state = {**state, "status": "degraded", "errors": errors}
    return state, evidence_by_event


def _load_ner_model(config: dict[str, Any]) -> tuple[dict[str, Any], Any | None]:
    model_config = _ner_model_config(config)
    threshold = _entity_threshold(config)
    state = _model_state(model_config, status="skipped", warnings=[], errors=[], threshold=threshold)
    intelligence = _text_intelligence_config(config)
    if not intelligence.get("enabled"):
        return {**state, "warnings": ["text_intelligence_disabled"]}, None
    if not model_config:
        return {**state, "warnings": ["ner_model_not_configured"]}, None

    try:
        from gliner import GLiNER
    except ModuleNotFoundError:
        return _model_state(
            model_config,
            status="unavailable",
            warnings=["optional gliner runtime is not installed"],
            errors=[],
            threshold=threshold,
        ), None

    signature = inspect.signature(GLiNER.from_pretrained)
    if "local_files_only" not in signature.parameters:
        return _model_state(
            model_config,
            status="unavailable",
            warnings=["gliner local-only model loading is unavailable; skipped to avoid hidden downloads"],
            errors=[],
            threshold=threshold,
        ), None

    try:
        model = GLiNER.from_pretrained(
            model_config["name"],
            revision=model_config["revision"],
            local_files_only=True,
        )
    except Exception as exc:  # pragma: no cover - depends on optional runtime/model cache.
        return _model_state(
            model_config,
            status="unavailable",
            warnings=["configured ner model is unavailable in the local model cache"],
            errors=[f"{exc.__class__.__name__}: {exc}"],
            threshold=threshold,
        ), None

    return _model_state(model_config, status="succeeded", warnings=[], errors=[], threshold=threshold), model


def _model_entity_record(
    event: dict[str, Any],
    entity: dict[str, Any],
    *,
    threshold: float,
    model_state: dict[str, Any],
) -> dict[str, Any]:
    score = _score(entity.get("score"))
    accepted = score >= threshold
    return {
        "event_id": event["event_id"],
        "text": str(entity.get("text") or "").strip(),
        "label": str(entity.get("label") or "unknown").lower(),
        "score": score,
        "accepted": accepted,
        "method": "pretrained_entity_model",
        "model": {
            "provider": model_state["provider"],
            "name": model_state["name"],
            "revision": model_state["revision"],
        },
        "matched_rules": [],
        "asset_relevance": None,
        "warnings": [] if accepted else ["model_entity_score_below_threshold"],
    }


def _asset_alias_index(config: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    market = config.get("market") if isinstance(config.get("market"), dict) else {}
    symbols = market.get("symbols") if isinstance(market.get("symbols"), list) else []
    index: dict[str, list[dict[str, str]]] = {}
    for symbol_value in symbols:
        if not isinstance(symbol_value, str) or not symbol_value.strip():
            continue
        symbol = symbol_value.strip().upper()
        base_asset = _base_asset(symbol)
        aliases = {symbol.lower(), base_asset.lower(), *BASE_ASSET_ALIASES.get(base_asset, set())}
        candidate = {
            "symbol": symbol,
            "base_asset": base_asset,
        }
        for alias in aliases:
            index.setdefault(alias, []).append(candidate)
    return index


def _base_asset(symbol: str) -> str:
    for quote in KNOWN_QUOTES:
        if symbol.endswith(quote) and len(symbol) > len(quote):
            return symbol[: -len(quote)]
    return symbol


def _alias_matches(text: str, alias: str) -> list[str]:
    pattern = re.compile(rf"(?<!\w){re.escape(alias)}(?!\w)", re.IGNORECASE)
    return [match.group(0) for match in pattern.finditer(text)]


def _event_text(event: dict[str, Any]) -> str:
    return " ".join(
        str(value)
        for value in (event.get("title"), event.get("content_text"), event.get("normalized_text"))
        if isinstance(value, str) and value.strip()
    )


def _record_warnings(asset_relevance: list[dict[str, Any]], entity_evidence: list[dict[str, Any]]) -> list[str]:
    warnings = []
    for item in [*asset_relevance, *entity_evidence]:
        for warning in item.get("warnings") or []:
            if warning not in warnings:
                warnings.append(str(warning))
    return warnings


def _artifact_warnings(records: list[dict[str, Any]], model_state: dict[str, Any]) -> list[str]:
    warnings = []
    for warning in model_state.get("warnings") or []:
        warnings.append(str(warning))
    for record in records:
        for warning in record.get("warnings") or []:
            if warning not in warnings:
                warnings.append(str(warning))
    return warnings


def _coverage(records: list[dict[str, Any]]) -> dict[str, int]:
    entity_count = sum(len(record["entity_evidence"]) for record in records)
    asset_count = sum(len(record["asset_relevance"]) for record in records)
    accepted_assets = sum(
        1
        for record in records
        for relevance in record["asset_relevance"]
        if relevance.get("state") == "accepted"
    )
    unknown_assets = sum(
        1
        for record in records
        for relevance in record["asset_relevance"]
        if relevance.get("state") == "unknown"
    )
    return {
        "events": len(records),
        "events_with_entity_evidence": sum(1 for record in records if record["entity_evidence"]),
        "events_with_asset_relevance": sum(1 for record in records if record["asset_relevance"]),
        "entity_evidence": entity_count,
        "asset_relevance_evidence": asset_count,
        "accepted_asset_relevance": accepted_assets,
        "unknown_asset_relevance": unknown_assets,
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
    run.manifest["counts"]["text_entity_records"] = len(records)
    run.manifest["counts"]["text_entity_evidence"] = coverage["entity_evidence"]
    run.manifest["counts"]["text_asset_relevance_evidence"] = coverage["asset_relevance_evidence"]
    run.manifest["counts"]["text_asset_relevance_accepted"] = coverage["accepted_asset_relevance"]
    run.manifest["counts"]["text_asset_relevance_unknown"] = coverage["unknown_asset_relevance"]
    run.manifest["text_entity_evidence"] = {
        "status": status,
        "artifacts": [TEXT_ENTITY_EVIDENCE_ARTIFACT] if status == "succeeded" else [],
        "records": len(records),
        "entity_evidence": coverage["entity_evidence"],
        "asset_relevance_evidence": coverage["asset_relevance_evidence"],
        "model_states": [state["status"] for state in model_states],
        "warnings": len(warnings),
        "errors": len(errors),
    }


def _text_intelligence_config(config: dict[str, Any]) -> dict[str, Any]:
    text = config.get("text") if isinstance(config.get("text"), dict) else {}
    intelligence = text.get("intelligence") if isinstance(text.get("intelligence"), dict) else {}
    return intelligence


def _ner_model_config(config: dict[str, Any]) -> dict[str, Any]:
    intelligence = _text_intelligence_config(config)
    models = intelligence.get("models") if isinstance(intelligence.get("models"), dict) else {}
    model = models.get("ner") if isinstance(models.get("ner"), dict) else {}
    return model


def _model_state(
    model_config: dict[str, Any],
    *,
    status: str,
    warnings: list[str],
    errors: list[str],
    threshold: float,
) -> dict[str, Any]:
    return {
        "role": "ner",
        "provider": str(model_config.get("provider") or "gliner"),
        "name": str(model_config.get("name") or ""),
        "revision": str(model_config.get("revision") or ""),
        "status": status,
        "task": "open_entity_extraction",
        "thresholds": {
            "entity_accept_score": threshold,
        },
        "warnings": warnings,
        "errors": errors,
    }


def _entity_threshold(config: dict[str, Any]) -> float:
    intelligence = _text_intelligence_config(config)
    thresholds = intelligence.get("thresholds") if isinstance(intelligence.get("thresholds"), dict) else {}
    return _score(thresholds.get("entity_accept_score"), default=0.5)


def _score(value: Any, *, default: float = 0.0) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return default


def _utc_timestamp(value: datetime | None = None) -> str:
    timestamp = value or datetime.now(UTC)
    timestamp = timestamp.astimezone(UTC).replace(microsecond=0)
    return timestamp.isoformat().replace("+00:00", "Z")
