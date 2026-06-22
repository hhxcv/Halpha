from __future__ import annotations

import hashlib
import inspect
import json
import math
import re
from datetime import UTC, datetime
from json import JSONDecodeError
from typing import Any

from halpha.runtime.pipeline_contracts import PipelineError, RunContext
from halpha.storage import write_json


STAGE_NAME = "build_text_event_topics"
TEXT_EVENT_RECORDS_ARTIFACT = "analysis/text_event_records.json"
TEXT_ENTITY_EVIDENCE_ARTIFACT = "analysis/text_entity_evidence.json"
TEXT_EVENT_TOPICS_ARTIFACT = "analysis/text_event_topics.json"
TEXT_EVENT_TOPICS_ARTIFACT_TYPE = "text_event_topics"
EMBEDDING_TASK = "sentence_similarity"
LEXICAL_SAME_TOPIC_MIN = 0.35


def build_text_event_topics(config: dict[str, Any], run: RunContext) -> list[str]:
    text = config.get("text", {})
    if not text.get("enabled"):
        _record_manifest_summary(
            run,
            topics=[],
            pair_decisions=[],
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
    model_state, embeddings = _embedding_vectors(event_records, config)
    pair_decisions = _pair_decisions(
        event_records,
        entity_index=entity_index,
        embeddings=embeddings,
        model_state=model_state,
        config=config,
    )
    topics = _topic_records(event_records, entity_index=entity_index, pair_decisions=pair_decisions)
    warnings = _artifact_warnings(model_state)
    errors: list[dict[str, Any]] = []
    artifact = {
        "schema_version": 1,
        "artifact_type": TEXT_EVENT_TOPICS_ARTIFACT_TYPE,
        "run_id": run.run_id,
        "created_at": _utc_timestamp(),
        "source_artifacts": [TEXT_EVENT_RECORDS_ARTIFACT, TEXT_ENTITY_EVIDENCE_ARTIFACT],
        "model_states": [model_state],
        "coverage": _coverage(topics, pair_decisions, event_records),
        "topics": topics,
        "pair_decisions": pair_decisions,
        "warnings": warnings,
        "errors": errors,
    }

    write_json(run.analysis_dir / "text_event_topics.json", artifact)
    run.manifest["artifacts"]["text_event_topics"] = TEXT_EVENT_TOPICS_ARTIFACT
    _record_manifest_summary(
        run,
        topics=topics,
        pair_decisions=pair_decisions,
        warnings=warnings,
        errors=errors,
        status="succeeded",
        model_states=[model_state],
    )
    return [TEXT_EVENT_TOPICS_ARTIFACT]


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
        unknown_assets = sorted(
            {
                str(relevance.get("asset")).upper()
                for relevance in record.get("asset_relevance") or []
                if isinstance(relevance, dict)
                and relevance.get("state") == "unknown"
                and isinstance(relevance.get("asset"), str)
                and relevance.get("asset")
            }
        )
        index[event_id] = {
            "accepted_symbols": accepted_symbols,
            "unknown_assets": unknown_assets,
        }
    return index


def _pair_decisions(
    events: list[dict[str, Any]],
    *,
    entity_index: dict[str, dict[str, Any]],
    embeddings: dict[str, list[float]],
    model_state: dict[str, Any],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    thresholds = _topic_thresholds(config)
    decisions = []
    for left_index, left in enumerate(events):
        for right in events[left_index + 1 :]:
            decisions.append(
                _pair_decision(
                    left,
                    right,
                    entity_index=entity_index,
                    embeddings=embeddings,
                    model_state=model_state,
                    thresholds=thresholds,
                )
            )
    return decisions


def _pair_decision(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    entity_index: dict[str, dict[str, Any]],
    embeddings: dict[str, list[float]],
    model_state: dict[str, Any],
    thresholds: dict[str, float],
) -> dict[str, Any]:
    left_id = str(left["event_id"])
    right_id = str(right["event_id"])
    reasons: list[str] = []
    methods: list[str] = []
    left_symbols = set(entity_index.get(left_id, {}).get("accepted_symbols") or [])
    right_symbols = set(entity_index.get(right_id, {}).get("accepted_symbols") or [])
    shared_symbols = sorted(left_symbols & right_symbols)
    title_similarity = _jaccard(_tokens(str(left.get("normalized_title") or "")), _tokens(str(right.get("normalized_title") or "")))
    text_similarity = _jaccard(_tokens(str(left.get("normalized_text") or "")), _tokens(str(right.get("normalized_text") or "")))
    lexical_similarity = max(title_similarity, text_similarity)
    embedding_similarity = _embedding_similarity(left_id, right_id, embeddings)
    time_window = _time_window_evidence(left, right, max_hours=thresholds["max_topic_window_hours"])
    same_url = _same_canonical_url(left, right)
    same_title = _same_normalized_title(left, right)

    if same_url:
        reasons.append("canonical_url_match")
        methods.append("canonical_url_rule")
    if same_title:
        reasons.append("normalized_title_match")
        methods.append("normalized_title_rule")
    if shared_symbols:
        reasons.append("asset_overlap_met")
    if time_window["met"]:
        reasons.append("time_window_met")
    elif time_window["reason"]:
        reasons.append(time_window["reason"])
    if embedding_similarity is not None and embedding_similarity >= thresholds["duplicate_similarity"]:
        reasons.append("embedding_duplicate_similarity_met")
        methods.append("pretrained_embedding_model")
    elif embedding_similarity is not None and embedding_similarity >= thresholds["same_topic_similarity"]:
        reasons.append("embedding_same_topic_similarity_met")
        methods.append("pretrained_embedding_model")
    if lexical_similarity >= LEXICAL_SAME_TOPIC_MIN:
        reasons.append("lexical_similarity_met")
        methods.append("lexical_similarity_rule")

    relationship = _relationship(
        same_url=same_url,
        same_title=same_title,
        embedding_similarity=embedding_similarity,
        lexical_similarity=lexical_similarity,
        shared_symbols=shared_symbols,
        time_window_met=time_window["met"],
        thresholds=thresholds,
    )
    if relationship == "distinct":
        reasons = [reason for reason in reasons if reason in {"missing_time_window", "outside_topic_time_window"}]
        methods = []
    methods = _unique(methods)
    similarity = embedding_similarity if embedding_similarity is not None else lexical_similarity
    return {
        "left_event_id": left_id,
        "right_event_id": right_id,
        "relationship": relationship,
        "similarity": _round_score(similarity),
        "similarity_evidence": {
            "embedding": _round_score(embedding_similarity) if embedding_similarity is not None else None,
            "lexical_title": _round_score(title_similarity),
            "lexical_text": _round_score(text_similarity),
            "embedding_model_status": model_state["status"],
        },
        "shared_symbols": shared_symbols,
        "time_window_hours": time_window["hours"],
        "reasons": _unique(reasons),
        "methods": methods,
        "source_artifacts": [TEXT_EVENT_RECORDS_ARTIFACT, TEXT_ENTITY_EVIDENCE_ARTIFACT],
    }


def _relationship(
    *,
    same_url: bool,
    same_title: bool,
    embedding_similarity: float | None,
    lexical_similarity: float,
    shared_symbols: list[str],
    time_window_met: bool,
    thresholds: dict[str, float],
) -> str:
    if same_url or same_title:
        return "duplicate"
    has_overlap = bool(shared_symbols)
    if (
        embedding_similarity is not None
        and embedding_similarity >= thresholds["duplicate_similarity"]
        and has_overlap
        and time_window_met
    ):
        return "duplicate"
    if (
        embedding_similarity is not None
        and embedding_similarity >= thresholds["same_topic_similarity"]
        and has_overlap
        and time_window_met
    ):
        return "same_topic"
    if lexical_similarity >= LEXICAL_SAME_TOPIC_MIN and has_overlap and time_window_met:
        return "same_topic"
    if has_overlap and time_window_met:
        return "related_context"
    if embedding_similarity is not None and embedding_similarity >= thresholds["same_topic_similarity"]:
        return "related_context"
    return "distinct"


def _topic_records(
    events: list[dict[str, Any]],
    *,
    entity_index: dict[str, dict[str, Any]],
    pair_decisions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    parent = {str(event["event_id"]): str(event["event_id"]) for event in events}

    for decision in pair_decisions:
        if decision["relationship"] in {"duplicate", "same_topic"}:
            _union(parent, decision["left_event_id"], decision["right_event_id"])

    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        grouped.setdefault(_find(parent, str(event["event_id"])), []).append(event)

    decision_index = {
        frozenset({decision["left_event_id"], decision["right_event_id"]}): decision for decision in pair_decisions
    }
    topics = []
    for members in grouped.values():
        members = sorted(members, key=lambda event: str(event["event_id"]))
        event_ids = [str(event["event_id"]) for event in members]
        symbols = sorted(
            {
                symbol
                for event_id in event_ids
                for symbol in entity_index.get(event_id, {}).get("accepted_symbols", [])
            }
        )
        topic_decisions = _topic_decisions(event_ids, decision_index)
        source_names = sorted(
            {
                str((event.get("source") or {}).get("name") or "unknown_source")
                for event in members
                if isinstance(event.get("source"), dict)
            }
        )
        seen_values = _seen_values(members)
        topic_id = _topic_id(symbols=symbols, event_ids=event_ids)
        topics.append(
            {
                "topic_id": topic_id,
                "status": "succeeded",
                "topic_label": _topic_label(members),
                "primary_category": "unknown",
                "symbols": symbols,
                "event_ids": event_ids,
                "primary_event_id": _primary_event_id(members),
                "source_count": len(source_names),
                "event_count": len(members),
                "first_seen_at": seen_values["first_seen_at"],
                "latest_seen_at": seen_values["latest_seen_at"],
                "merge_decisions": topic_decisions,
                "warnings": [],
                "source_artifacts": [TEXT_EVENT_RECORDS_ARTIFACT, TEXT_ENTITY_EVIDENCE_ARTIFACT],
            }
        )

    return sorted(topics, key=lambda topic: (topic["first_seen_at"] or "", topic["topic_id"]))


def _topic_decisions(
    event_ids: list[str],
    decision_index: dict[frozenset[str], dict[str, Any]],
) -> list[dict[str, Any]]:
    decisions = []
    for left_index, left_id in enumerate(event_ids):
        for right_id in event_ids[left_index + 1 :]:
            decision = decision_index.get(frozenset({left_id, right_id}))
            if decision is None:
                continue
            if decision["relationship"] not in {"duplicate", "same_topic"}:
                continue
            decisions.append(
                {
                    "left_event_id": decision["left_event_id"],
                    "right_event_id": decision["right_event_id"],
                    "relationship": decision["relationship"],
                    "similarity": decision["similarity"],
                    "reasons": decision["reasons"],
                    "methods": decision["methods"],
                }
            )
    return decisions


def _embedding_vectors(
    events: list[dict[str, Any]],
    config: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, list[float]]]:
    state, model = _load_embedding_model(config)
    if model is None or not events:
        return state, {}

    texts = [_embedding_text(event) for event in events]
    try:
        vectors = _encode_embeddings(model, texts)
    except Exception as exc:  # pragma: no cover - depends on optional runtime behavior.
        return (
            {
                **state,
                "status": "degraded",
                "warnings": [*state.get("warnings", []), "embedding model failed during local inference"],
                "errors": [*state.get("errors", []), f"{exc.__class__.__name__}: {exc}"],
            },
            {},
        )

    if len(vectors) != len(events):
        return (
            {
                **state,
                "status": "degraded",
                "warnings": [*state.get("warnings", []), "embedding model returned an unexpected vector count"],
                "errors": [*state.get("errors", []), f"expected {len(events)} vectors, got {len(vectors)}"],
            },
            {},
        )
    return state, {str(event["event_id"]): vector for event, vector in zip(events, vectors, strict=True)}


def _load_embedding_model(config: dict[str, Any]) -> tuple[dict[str, Any], Any | None]:
    model_config = _embedding_model_config(config)
    thresholds = _topic_thresholds(config)
    state = _model_state(model_config, status="skipped", warnings=[], errors=[], thresholds=thresholds)
    intelligence = _text_intelligence_config(config)
    if not intelligence.get("enabled"):
        return {**state, "warnings": ["text_intelligence_disabled"]}, None
    if not model_config:
        return {**state, "warnings": ["embedding_model_not_configured"]}, None

    try:
        from sentence_transformers import SentenceTransformer
    except ModuleNotFoundError:
        return _model_state(
            model_config,
            status="unavailable",
            warnings=["optional sentence-transformers runtime is not installed"],
            errors=[],
            thresholds=thresholds,
        ), None

    signature = inspect.signature(SentenceTransformer)
    if "local_files_only" not in signature.parameters:
        return _model_state(
            model_config,
            status="unavailable",
            warnings=[
                "sentence-transformers local-only model loading is unavailable; skipped to avoid hidden downloads"
            ],
            errors=[],
            thresholds=thresholds,
        ), None

    kwargs: dict[str, Any] = {
        "model_name_or_path": model_config["name"],
        "revision": model_config["revision"],
        "local_files_only": True,
    }
    model_cache_dir = intelligence.get("model_cache_dir")
    if isinstance(model_cache_dir, str) and model_cache_dir.strip() and "cache_folder" in signature.parameters:
        kwargs["cache_folder"] = model_cache_dir.strip()

    try:
        model = SentenceTransformer(**kwargs)
    except Exception as exc:  # pragma: no cover - depends on optional runtime/model cache.
        return _model_state(
            model_config,
            status="unavailable",
            warnings=["configured embedding model is unavailable in the local model cache"],
            errors=[f"{exc.__class__.__name__}: {exc}"],
            thresholds=thresholds,
        ), None

    return _model_state(model_config, status="succeeded", warnings=[], errors=[], thresholds=thresholds), model


def _encode_embeddings(model: Any, texts: list[str]) -> list[list[float]]:
    try:
        raw_vectors = model.encode(texts, normalize_embeddings=True)
    except TypeError:
        raw_vectors = model.encode(texts)
    return [_vector(vector) for vector in raw_vectors]


def _model_state(
    model_config: dict[str, Any],
    *,
    status: str,
    warnings: list[str],
    errors: list[str],
    thresholds: dict[str, float],
) -> dict[str, Any]:
    return {
        "role": "embedding",
        "provider": str(model_config.get("provider") or "sentence_transformers"),
        "name": str(model_config.get("name") or ""),
        "revision": str(model_config.get("revision") or ""),
        "status": status,
        "task": EMBEDDING_TASK,
        "thresholds": {
            "duplicate_similarity": thresholds["duplicate_similarity"],
            "same_topic_similarity": thresholds["same_topic_similarity"],
            "max_topic_window_hours": thresholds["max_topic_window_hours"],
            "lexical_same_topic_min": LEXICAL_SAME_TOPIC_MIN,
        },
        "warnings": warnings,
        "errors": errors,
    }


def _topic_thresholds(config: dict[str, Any]) -> dict[str, float]:
    intelligence = _text_intelligence_config(config)
    thresholds = intelligence.get("thresholds") if isinstance(intelligence.get("thresholds"), dict) else {}
    return {
        "duplicate_similarity": _score(thresholds.get("duplicate_similarity"), default=0.92),
        "same_topic_similarity": _score(thresholds.get("same_topic_similarity"), default=0.82),
        "max_topic_window_hours": _score(thresholds.get("max_topic_window_hours"), default=48.0),
    }


def _embedding_model_config(config: dict[str, Any]) -> dict[str, Any]:
    intelligence = _text_intelligence_config(config)
    models = intelligence.get("models") if isinstance(intelligence.get("models"), dict) else {}
    model = models.get("embedding") if isinstance(models.get("embedding"), dict) else {}
    return model


def _text_intelligence_config(config: dict[str, Any]) -> dict[str, Any]:
    text = config.get("text") if isinstance(config.get("text"), dict) else {}
    intelligence = text.get("intelligence") if isinstance(text.get("intelligence"), dict) else {}
    return intelligence


def _coverage(
    topics: list[dict[str, Any]],
    pair_decisions: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> dict[str, int]:
    return {
        "events": len(events),
        "topics": len(topics),
        "multi_event_topics": sum(1 for topic in topics if topic["event_count"] > 1),
        "pair_decisions": len(pair_decisions),
        "duplicate_decisions": _relationship_count(pair_decisions, "duplicate"),
        "same_topic_decisions": _relationship_count(pair_decisions, "same_topic"),
        "related_context_decisions": _relationship_count(pair_decisions, "related_context"),
        "distinct_decisions": _relationship_count(pair_decisions, "distinct"),
        "embedding_similarity_decisions": sum(
            1 for decision in pair_decisions if decision["similarity_evidence"]["embedding"] is not None
        ),
        "rule_similarity_decisions": sum(
            1 for decision in pair_decisions if decision["similarity_evidence"]["lexical_text"] > 0
        ),
    }


def _relationship_count(pair_decisions: list[dict[str, Any]], relationship: str) -> int:
    return sum(1 for decision in pair_decisions if decision["relationship"] == relationship)


def _record_manifest_summary(
    run: RunContext,
    *,
    topics: list[dict[str, Any]],
    pair_decisions: list[dict[str, Any]],
    warnings: list[str],
    errors: list[dict[str, Any]],
    status: str,
    model_states: list[dict[str, Any]],
) -> None:
    coverage = _coverage(topics, pair_decisions, [])
    run.manifest["counts"]["text_event_topics"] = len(topics)
    run.manifest["counts"]["text_event_topic_pair_decisions"] = len(pair_decisions)
    run.manifest["counts"]["text_event_topic_duplicate_decisions"] = coverage["duplicate_decisions"]
    run.manifest["counts"]["text_event_topic_same_topic_decisions"] = coverage["same_topic_decisions"]
    run.manifest["counts"]["text_event_topic_related_context_decisions"] = coverage["related_context_decisions"]
    run.manifest["counts"]["text_event_topic_distinct_decisions"] = coverage["distinct_decisions"]
    run.manifest["text_event_topics"] = {
        "status": status,
        "artifacts": [TEXT_EVENT_TOPICS_ARTIFACT] if status == "succeeded" else [],
        "topics": len(topics),
        "pair_decisions": len(pair_decisions),
        "model_states": [state["status"] for state in model_states],
        "warnings": len(warnings),
        "errors": len(errors),
    }


def _artifact_warnings(model_state: dict[str, Any]) -> list[str]:
    warnings = []
    for warning in model_state.get("warnings") or []:
        warnings.append(str(warning))
    if model_state["status"] in {"skipped", "unavailable", "degraded"}:
        warning = "embedding model unavailable; deterministic grouping gates used available rule evidence only"
        if warning not in warnings:
            warnings.append(warning)
    return warnings


def _same_canonical_url(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_url = left.get("canonical_url")
    right_url = right.get("canonical_url")
    return isinstance(left_url, str) and isinstance(right_url, str) and left_url == right_url


def _same_normalized_title(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_title = left.get("normalized_title")
    right_title = right.get("normalized_title")
    return isinstance(left_title, str) and isinstance(right_title, str) and bool(left_title) and left_title == right_title


def _time_window_evidence(left: dict[str, Any], right: dict[str, Any], *, max_hours: float) -> dict[str, Any]:
    left_time = _event_time(left)
    right_time = _event_time(right)
    if left_time is None or right_time is None:
        return {"met": False, "hours": None, "reason": "missing_time_window"}
    hours = abs((left_time - right_time).total_seconds()) / 3600
    return {
        "met": hours <= max_hours,
        "hours": _round_score(hours),
        "reason": None if hours <= max_hours else "outside_topic_time_window",
    }


def _event_time(event: dict[str, Any]) -> datetime | None:
    for field in ("published_at", "collected_at"):
        value = event.get(field)
        if isinstance(value, str) and value.strip():
            parsed = _parse_utc(value)
            if parsed is not None:
                return parsed
    return None


def _parse_utc(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _embedding_similarity(left_id: str, right_id: str, embeddings: dict[str, list[float]]) -> float | None:
    left_vector = embeddings.get(left_id)
    right_vector = embeddings.get(right_id)
    if left_vector is None or right_vector is None:
        return None
    return _cosine(left_vector, right_vector)


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    numerator = sum(left_value * right_value for left_value, right_value in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return max(0.0, min(1.0, numerator / (left_norm * right_norm)))


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) > 2}


def _vector(value: Any) -> list[float]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    return [float(item) for item in value]


def _embedding_text(event: dict[str, Any]) -> str:
    values = [
        event.get("normalized_title"),
        event.get("normalized_text"),
        event.get("title"),
        event.get("content_text"),
    ]
    text = " ".join(str(value) for value in values if isinstance(value, str) and value.strip()).strip()
    return text or str(event.get("event_id") or "")


def _seen_values(events: list[dict[str, Any]]) -> dict[str, str | None]:
    values = sorted(
        parsed.isoformat().replace("+00:00", "Z")
        for event in events
        if (parsed := _event_time(event)) is not None
    )
    return {
        "first_seen_at": values[0] if values else None,
        "latest_seen_at": values[-1] if values else None,
    }


def _topic_label(events: list[dict[str, Any]]) -> str:
    primary = _primary_event(events)
    title = str(primary.get("title") or "").strip()
    return title[:120] if title else "Text event topic"


def _primary_event_id(events: list[dict[str, Any]]) -> str:
    return str(_primary_event(events)["event_id"])


def _primary_event(events: list[dict[str, Any]]) -> dict[str, Any]:
    return sorted(events, key=lambda event: (_event_time(event) or datetime.max.replace(tzinfo=UTC), str(event["event_id"])))[0]


def _topic_id(*, symbols: list[str], event_ids: list[str]) -> str:
    symbol_part = _slug(symbols[0]) if symbols else "market"
    digest = hashlib.sha256("|".join(sorted(event_ids)).encode("utf-8")).hexdigest()[:12]
    return f"text_event_topic:{symbol_part}:{digest}"


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "market"


def _find(parent: dict[str, str], value: str) -> str:
    root = parent[value]
    if root != value:
        parent[value] = _find(parent, root)
    return parent[value]


def _union(parent: dict[str, str], left: str, right: str) -> None:
    left_root = _find(parent, left)
    right_root = _find(parent, right)
    if left_root == right_root:
        return
    parent[max(left_root, right_root)] = min(left_root, right_root)


def _score(value: Any, *, default: float = 0.0) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return default


def _round_score(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)


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
