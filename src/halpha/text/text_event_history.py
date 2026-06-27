from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pyarrow as pa
import pyarrow.parquet as pq

from halpha.runtime.pipeline_contracts import RunContext
from halpha.storage import display_path, resolve_runtime_path, runtime_root, write_json


TEXT_EVENT_HISTORY_SCHEMA_VERSION = 2
TEXT_EVENT_HISTORY_STATE_ARTIFACT = "data/research/metadata/text_event_history_state.json"
TEXT_EVENT_HISTORY_STORAGE_ARTIFACT = "data/research/text_events"
TEXT_EVENT_RECORDS_ARTIFACT = "analysis/text_event_records.json"

TEXT_EVENT_HISTORY_SCHEMA = pa.schema(
    [
        pa.field("stable_event_key", pa.string()),
        pa.field("raw_item_id", pa.string()),
        pa.field("source", pa.string()),
        pa.field("source_type", pa.string()),
        pa.field("url", pa.string()),
        pa.field("canonical_url", pa.string()),
        pa.field("title", pa.string()),
        pa.field("published_at", pa.string()),
        pa.field("collected_at", pa.string()),
        pa.field("normalized_text", pa.string()),
        pa.field("content_hash", pa.string()),
        pa.field("origin_run_ids", pa.list_(pa.string())),
        pa.field("first_seen_run_id", pa.string()),
        pa.field("last_seen_run_id", pa.string()),
        pa.field("first_seen_at", pa.string()),
        pa.field("last_seen_at", pa.string()),
        pa.field("duplicate_group_key", pa.string()),
        pa.field("same_event_group_id", pa.string()),
        pa.field("same_event_group_method", pa.string()),
        pa.field("same_event_group_score_bucket", pa.string()),
        pa.field("status", pa.string()),
        pa.field("warnings", pa.list_(pa.string())),
        pa.field("source_artifacts", pa.list_(pa.string())),
    ]
)

SAME_EVENT_MAX_WINDOW_HOURS = 48.0
SAME_EVENT_TITLE_HIGH_MIN = 0.72
SAME_EVENT_TEXT_HIGH_MIN = 0.68
SAME_EVENT_TITLE_MEDIUM_MIN = 0.52
SAME_EVENT_TEXT_MEDIUM_MIN = 0.52
SAME_EVENT_CANDIDATE_MIN = 0.35
SAME_EVENT_CANDIDATE_LIMIT = 25
SAME_EVENT_DIRECTIONAL_CONFLICTS = (
    ({"inflow", "inflows"}, {"outflow", "outflows"}),
    ({"rise", "rises", "rose", "rising", "gain", "gains", "rally", "rallies"}, {"fall", "falls", "fell", "falling", "drop", "drops", "loss", "losses"}),
    ({"increase", "increases", "increased", "expansion", "expanded"}, {"decrease", "decreases", "decreased", "contraction", "contracted"}),
    ({"approve", "approves", "approved", "approval"}, {"reject", "rejects", "rejected", "rejection"}),
)


@dataclass(frozen=True)
class _TextEventHistoryOrigin:
    run_id: str
    config_path: Path
    records_artifact_ref: str
    state_source_artifact_ref: str
    source_artifact_base: Path | None


def write_text_event_history(
    config: dict[str, Any],
    run: RunContext,
    records: list[dict[str, Any]],
    *,
    now: datetime | str | None = None,
) -> list[str]:
    if not config.get("text", {}).get("enabled"):
        _record_manifest_summary(run, _skipped_state(run.config_path, reason="text.enabled is false.", now=now))
        return []

    origin = _TextEventHistoryOrigin(
        run_id=run.run_id,
        config_path=run.config_path,
        records_artifact_ref=display_path(run.analysis_dir / "text_event_records.json", base=runtime_root(run.config_path)),
        state_source_artifact_ref=TEXT_EVENT_RECORDS_ARTIFACT,
        source_artifact_base=run.run_dir,
    )
    state = _write_text_event_history_state(records, origin=origin, now=now)
    _record_manifest_summary(run, state)
    return [TEXT_EVENT_HISTORY_STATE_ARTIFACT]


def write_text_event_history_records(
    config: dict[str, Any],
    *,
    config_path: Path,
    run_id: str,
    records: list[dict[str, Any]],
    records_artifact_ref: str,
    source_artifact_base: Path | None = None,
    manifest: dict[str, Any] | None = None,
    now: datetime | str | None = None,
) -> list[str]:
    if not config.get("text", {}).get("enabled"):
        state = _skipped_state(config_path, reason="text.enabled is false.", now=now)
    else:
        origin = _TextEventHistoryOrigin(
            run_id=run_id,
            config_path=config_path,
            records_artifact_ref=records_artifact_ref,
            state_source_artifact_ref=records_artifact_ref,
            source_artifact_base=source_artifact_base,
        )
        state = _write_text_event_history_state(records, origin=origin, now=now)
    if manifest is not None:
        _apply_manifest_summary(manifest, state)
    return [] if state["status"] == "skipped" and not records else [TEXT_EVENT_HISTORY_STATE_ARTIFACT]


def _write_text_event_history_state(
    records: list[dict[str, Any]],
    *,
    origin: _TextEventHistoryOrigin,
    now: datetime | str | None,
) -> dict[str, Any]:
    storage_root = text_event_history_storage_path(origin.config_path)
    state_path = text_event_history_state_path(origin.config_path)
    incoming_records, incoming_warnings = _history_records(records, origin, now=now)
    existing_records = _read_history_records(storage_root)
    merged_records, merge_summary = _merge_history(existing_records, incoming_records)
    annotated_records, group_summary = _annotate_same_event_groups(merged_records)
    warnings = _unique_sorted([*incoming_warnings, *merge_summary["warnings"], *group_summary["warnings"]])
    status = _status(record_count=len(annotated_records), warnings=warnings)

    _rewrite_history(storage_root, annotated_records)
    base = runtime_root(origin.config_path)
    state = {
        "schema_version": TEXT_EVENT_HISTORY_SCHEMA_VERSION,
        "artifact_type": "text_event_history_state",
        "updated_at": _format_utc(now),
        "status": status,
        "storage_path": display_path(storage_root, base=base),
        "state_path": display_path(state_path, base=base),
        "totals": {
            "records": len(annotated_records),
            "incoming_records": len(incoming_records),
            "inserted_records": merge_summary["inserted_records"],
            "updated_records": merge_summary["updated_records"],
            "duplicate_records": merge_summary["duplicate_records"],
            "conflicting_duplicates": merge_summary["conflicting_duplicates"],
            "same_event_groups": len(group_summary["groups"]),
            "same_event_grouped_records": sum(len(group["record_ids"]) for group in group_summary["groups"]),
            "same_event_candidate_pairs": len(group_summary["candidate_pairs"])
            + group_summary["candidate_pair_omitted_count"],
            "same_event_candidate_pair_omitted_count": group_summary["candidate_pair_omitted_count"],
            "warning_count": len(warnings),
            "error_count": 0,
        },
        "sources": _source_summaries(annotated_records),
        "same_event_groups": group_summary["groups"],
        "same_event_group_candidates": group_summary["candidate_pairs"],
        "warnings": warnings,
        "errors": [],
        "source_artifacts": [origin.state_source_artifact_ref],
    }
    write_json(state_path, state)
    return state


def text_event_history_storage_path(config_path: Path) -> Path:
    return resolve_runtime_path(TEXT_EVENT_HISTORY_STORAGE_ARTIFACT, config_path=config_path)


def text_event_history_state_path(config_path: Path) -> Path:
    return resolve_runtime_path(TEXT_EVENT_HISTORY_STATE_ARTIFACT, config_path=config_path)


def _history_records(
    records: list[dict[str, Any]],
    origin: _TextEventHistoryOrigin,
    *,
    now: datetime | str | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    normalized = []
    warnings = []
    observed_at = _format_utc(now)
    for record in records:
        item, item_warnings = _history_record(record, origin, observed_at=observed_at)
        normalized.append(item)
        warnings.extend(item_warnings)
    return sorted(normalized, key=lambda item: item["stable_event_key"]), _unique_sorted(warnings)


def _history_record(
    record: dict[str, Any],
    origin: _TextEventHistoryOrigin,
    *,
    observed_at: str,
) -> tuple[dict[str, Any], list[str]]:
    source = record.get("source") if isinstance(record.get("source"), dict) else {}
    source_name = _clean_text(source.get("name"), fallback="unknown_source")
    raw_item_id = _clean_text(record.get("raw_item_id"), fallback="")
    canonical_url = _optional_text(record.get("canonical_url"))
    url = _optional_text(record.get("link"))
    normalized_text = _clean_text(record.get("normalized_text"), fallback="")
    content_hash = _hash_text(normalized_text)
    stable_event_key = _stable_event_key(
        source=source_name,
        canonical_url=canonical_url,
        raw_item_id=raw_item_id,
        content_hash=content_hash,
    )
    published_at, published_warning = _optional_utc(record.get("published_at"), "published_at", stable_event_key)
    collected_at, collected_warning = _optional_utc(record.get("collected_at"), "collected_at", stable_event_key)
    warnings = [warning for warning in (published_warning, collected_warning) if warning]
    warnings.extend(str(warning) for warning in record.get("warnings") or [] if isinstance(warning, str))
    first_seen_at = collected_at or published_at or observed_at

    return {
        "stable_event_key": stable_event_key,
        "raw_item_id": raw_item_id,
        "source": source_name,
        "source_type": _clean_text(record.get("input_type"), fallback="unknown"),
        "url": url,
        "canonical_url": canonical_url,
        "title": _clean_text(record.get("title"), fallback=""),
        "published_at": published_at,
        "collected_at": collected_at,
        "normalized_text": normalized_text,
        "content_hash": content_hash,
        "origin_run_ids": [origin.run_id],
        "first_seen_run_id": origin.run_id,
        "last_seen_run_id": origin.run_id,
        "first_seen_at": first_seen_at,
        "last_seen_at": first_seen_at,
        "duplicate_group_key": canonical_url or content_hash,
        "same_event_group_id": None,
        "same_event_group_method": None,
        "same_event_group_score_bucket": None,
        "status": "warning" if warnings else "active",
        "warnings": _unique_sorted(warnings),
        "source_artifacts": _source_artifacts(record, origin),
    }, warnings


def _merge_history(
    existing_records: list[dict[str, Any]],
    incoming_records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_key = {record["stable_event_key"]: record for record in existing_records}
    inserted = 0
    updated = 0
    duplicate = 0
    conflicts = 0
    warnings = []

    for incoming in incoming_records:
        existing = by_key.get(incoming["stable_event_key"])
        if existing is None:
            by_key[incoming["stable_event_key"]] = incoming
            inserted += 1
            continue

        duplicate += 1
        updated += 1
        if existing.get("content_hash") != incoming.get("content_hash"):
            conflicts += 1
            warning = f"conflicting duplicate text event: {incoming['stable_event_key']}"
            warnings.append(warning)
            existing["warnings"] = _unique_sorted([*existing.get("warnings", []), warning])
            existing["status"] = "warning"
        existing["origin_run_ids"] = _unique_sorted(
            [*existing.get("origin_run_ids", []), *incoming.get("origin_run_ids", [])]
        )
        existing["last_seen_run_id"] = incoming["last_seen_run_id"]
        existing["last_seen_at"] = _latest_timestamp(existing.get("last_seen_at"), incoming.get("last_seen_at"))
        existing["source_artifacts"] = _unique_sorted(
            [*existing.get("source_artifacts", []), *incoming.get("source_artifacts", [])]
        )
        existing["warnings"] = _unique_sorted([*existing.get("warnings", []), *incoming.get("warnings", [])])
        if existing["warnings"] and existing.get("status") == "active":
            existing["status"] = "warning"

    return (
        sorted(by_key.values(), key=lambda record: (record["source"], record["stable_event_key"])),
        {
            "inserted_records": inserted,
            "updated_records": updated,
            "duplicate_records": duplicate,
            "conflicting_duplicates": conflicts,
            "warnings": _unique_sorted(warnings),
        },
    )


def _annotate_same_event_groups(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    annotated = []
    for record in records:
        annotated.append(
            {
                **record,
                "same_event_group_id": None,
                "same_event_group_method": None,
                "same_event_group_score_bucket": None,
            }
        )

    decisions = _same_event_pair_decisions(annotated)
    parent = {str(record["stable_event_key"]): str(record["stable_event_key"]) for record in annotated}
    for decision in decisions:
        if decision["relationship"] == "same_event":
            _union(parent, decision["left_record_id"], decision["right_record_id"])

    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in annotated:
        grouped.setdefault(_find(parent, str(record["stable_event_key"])), []).append(record)

    decision_index = {
        frozenset({decision["left_record_id"], decision["right_record_id"]}): decision for decision in decisions
    }
    groups = []
    for members in grouped.values():
        if len(members) < 2:
            continue
        members = sorted(members, key=lambda record: str(record["stable_event_key"]))
        member_ids = [str(member["stable_event_key"]) for member in members]
        group_decisions = _group_decisions(member_ids, decision_index)
        group_id = _same_event_group_id(member_ids)
        method = _same_event_group_method(group_decisions)
        score_bucket = _same_event_group_score_bucket(group_decisions)
        for member in members:
            member["same_event_group_id"] = group_id
            member["same_event_group_method"] = method
            member["same_event_group_score_bucket"] = score_bucket
        groups.append(_same_event_group_record(group_id, members, group_decisions, method, score_bucket))

    candidate_pairs = [
        decision
        for decision in decisions
        if decision["relationship"] == "separate" and decision["score_bucket"] in {"low", "medium", "high"}
    ]
    candidate_pairs = sorted(candidate_pairs, key=lambda decision: (decision["left_record_id"], decision["right_record_id"]))
    omitted = max(0, len(candidate_pairs) - SAME_EVENT_CANDIDATE_LIMIT)
    return (
        sorted(annotated, key=lambda record: (record["source"], record["stable_event_key"])),
        {
            "groups": sorted(groups, key=lambda group: (group["first_seen_at"] or "", group["same_event_group_id"])),
            "candidate_pairs": candidate_pairs[:SAME_EVENT_CANDIDATE_LIMIT],
            "candidate_pair_omitted_count": omitted,
            "warnings": [],
        },
    )


def _same_event_pair_decisions(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decisions = []
    for left_index, left in enumerate(records):
        for right in records[left_index + 1 :]:
            decisions.append(_same_event_pair_decision(left, right))
    return decisions


def _same_event_pair_decision(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_id = str(left["stable_event_key"])
    right_id = str(right["stable_event_key"])
    reasons: list[str] = []
    methods: list[str] = []
    left_title_tokens = _tokens(str(left.get("title") or ""))
    right_title_tokens = _tokens(str(right.get("title") or ""))
    left_text_tokens = _tokens(str(left.get("normalized_text") or ""))
    right_text_tokens = _tokens(str(right.get("normalized_text") or ""))
    title_similarity = _jaccard(left_title_tokens, right_title_tokens)
    text_similarity = _jaccard(left_text_tokens, right_text_tokens)
    url_path_similarity = _jaccard(_url_tokens(left), _url_tokens(right))
    duplicate_key_match = _same_duplicate_group_key(left, right)
    time_window = _same_event_time_window(left, right)
    source_diverse = _source_diverse(left, right)
    directional_conflict = _has_directional_conflict(
        left_title_tokens | left_text_tokens,
        right_title_tokens | right_text_tokens,
    )

    if duplicate_key_match:
        reasons.append("duplicate_group_key_match")
        methods.append("duplicate_group_key_rule")
    if directional_conflict:
        reasons.append("directional_term_conflict")
    if source_diverse:
        reasons.append("source_diversity_met")
    else:
        reasons.append("source_diversity_not_met")
    if time_window["met"]:
        reasons.append("time_window_met")
    else:
        reasons.append(time_window["reason"])
    score_bucket = _same_event_score_bucket(
        duplicate_key_match=duplicate_key_match,
        title_similarity=title_similarity,
        text_similarity=text_similarity,
    )
    if title_similarity >= SAME_EVENT_TITLE_MEDIUM_MIN:
        reasons.append("title_similarity_met")
        methods.append("title_similarity_rule")
    if text_similarity >= SAME_EVENT_TEXT_MEDIUM_MIN:
        reasons.append("text_similarity_met")
        methods.append("text_similarity_rule")
    if url_path_similarity >= SAME_EVENT_CANDIDATE_MIN:
        reasons.append("url_path_similarity_observed")
        methods.append("url_path_similarity_rule")

    relationship = "separate"
    if duplicate_key_match:
        relationship = "same_event"
    elif source_diverse and time_window["met"] and score_bucket in {"high", "medium"} and not directional_conflict:
        relationship = "same_event"
    elif score_bucket == "none" and max(title_similarity, text_similarity, url_path_similarity) >= SAME_EVENT_CANDIDATE_MIN:
        score_bucket = "low"
        reasons.append("insufficient_same_event_similarity")

    return {
        "left_record_id": left_id,
        "right_record_id": right_id,
        "relationship": relationship,
        "status": "accepted" if relationship == "same_event" else "low_confidence_separate",
        "method": "exact_duplicate_key_rule" if duplicate_key_match else "near_duplicate_rule",
        "score_bucket": score_bucket,
        "similarity_evidence": {
            "title": _round_score(title_similarity),
            "text": _round_score(text_similarity),
            "url_path": _round_score(url_path_similarity),
        },
        "time_window_hours": time_window["hours"],
        "reasons": _unique_sorted(reasons),
        "methods": _unique_sorted(methods),
    }


def _same_event_group_record(
    group_id: str,
    members: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    method: str,
    score_bucket: str,
) -> dict[str, Any]:
    warnings = _unique_sorted(
        [warning for member in members for warning in member.get("warnings", []) if isinstance(warning, str)]
    )
    return {
        "same_event_group_id": group_id,
        "method": method,
        "score_bucket": score_bucket,
        "record_ids": [str(member["stable_event_key"]) for member in members],
        "source_count": len({str(member.get("source") or "unknown_source") for member in members}),
        "sources": sorted({str(member.get("source") or "unknown_source") for member in members}),
        "first_seen_at": _earliest_timestamp(member.get("first_seen_at") for member in members),
        "last_seen_at": _latest_timestamp_many(member.get("last_seen_at") for member in members),
        "published_start_at": _earliest_timestamp(member.get("published_at") for member in members),
        "published_end_at": _latest_timestamp_many(member.get("published_at") for member in members),
        "source_artifacts": _unique_sorted(
            [artifact for member in members for artifact in member.get("source_artifacts", []) if isinstance(artifact, str)]
        ),
        "decisions": decisions,
        "warnings": warnings,
        "conflicts": [warning for warning in warnings if "conflicting duplicate text event:" in warning],
    }


def _group_decisions(
    member_ids: list[str],
    decision_index: dict[frozenset[str], dict[str, Any]],
) -> list[dict[str, Any]]:
    decisions = []
    for left_index, left_id in enumerate(member_ids):
        for right_id in member_ids[left_index + 1 :]:
            decision = decision_index.get(frozenset({left_id, right_id}))
            if decision is None or decision["relationship"] != "same_event":
                continue
            decisions.append(decision)
    return sorted(decisions, key=lambda decision: (decision["left_record_id"], decision["right_record_id"]))


def _same_event_group_method(decisions: list[dict[str, Any]]) -> str:
    if any(decision["method"] == "exact_duplicate_key_rule" for decision in decisions):
        return "exact_duplicate_key_rule"
    return "near_duplicate_rule"


def _same_event_group_score_bucket(decisions: list[dict[str, Any]]) -> str:
    ordered = {"exact": 3, "high": 2, "medium": 1, "low": 0, "none": -1}
    best = "none"
    for decision in decisions:
        bucket = str(decision.get("score_bucket") or "none")
        if ordered.get(bucket, -1) > ordered.get(best, -1):
            best = bucket
    return best


def _same_event_group_id(member_ids: list[str]) -> str:
    digest = hashlib.sha256("|".join(sorted(member_ids)).encode("utf-8")).hexdigest()[:24]
    return f"text_event_same_event:{digest}"


def _same_event_score_bucket(
    *,
    duplicate_key_match: bool,
    title_similarity: float,
    text_similarity: float,
) -> str:
    if duplicate_key_match:
        return "exact"
    if title_similarity >= SAME_EVENT_TITLE_HIGH_MIN or text_similarity >= SAME_EVENT_TEXT_HIGH_MIN:
        return "high"
    if title_similarity >= SAME_EVENT_TITLE_MEDIUM_MIN and text_similarity >= SAME_EVENT_TEXT_MEDIUM_MIN:
        return "medium"
    return "none"


def _has_directional_conflict(left_tokens: set[str], right_tokens: set[str]) -> bool:
    for positive_tokens, negative_tokens in SAME_EVENT_DIRECTIONAL_CONFLICTS:
        if left_tokens & positive_tokens and right_tokens & negative_tokens:
            return True
        if left_tokens & negative_tokens and right_tokens & positive_tokens:
            return True
    return False


def _same_duplicate_group_key(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_key = _optional_text(left.get("duplicate_group_key"))
    right_key = _optional_text(right.get("duplicate_group_key"))
    return left_key is not None and right_key is not None and left_key == right_key


def _same_event_time_window(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_time = _event_time(left)
    right_time = _event_time(right)
    if left_time is None or right_time is None:
        return {"met": False, "hours": None, "reason": "missing_same_event_time_window"}
    hours = abs((left_time - right_time).total_seconds()) / 3600
    return {
        "met": hours <= SAME_EVENT_MAX_WINDOW_HOURS,
        "hours": _round_score(hours),
        "reason": "outside_same_event_time_window" if hours > SAME_EVENT_MAX_WINDOW_HOURS else None,
    }


def _event_time(record: dict[str, Any]) -> datetime | None:
    for field in ("published_at", "collected_at", "first_seen_at"):
        value = record.get(field)
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
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _source_diverse(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_source = _optional_text(left.get("source"))
    right_source = _optional_text(right.get("source"))
    return left_source is not None and right_source is not None and left_source != right_source


def _url_tokens(record: dict[str, Any]) -> set[str]:
    value = _optional_text(record.get("canonical_url")) or _optional_text(record.get("url")) or ""
    parsed = urlparse(value)
    return _tokens(f"{parsed.netloc} {parsed.path}")


def _tokens(value: str) -> set[str]:
    return {token for token in "".join(character.lower() if character.isalnum() else " " for character in value).split() if len(token) > 2}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _round_score(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)


def _earliest_timestamp(values: Any) -> str | None:
    parsed = sorted(timestamp for value in values if (timestamp := _timestamp_text(value)) is not None)
    return parsed[0] if parsed else None


def _latest_timestamp_many(values: Any) -> str | None:
    parsed = sorted(timestamp for value in values if (timestamp := _timestamp_text(value)) is not None)
    return parsed[-1] if parsed else None


def _timestamp_text(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    parsed = _parse_utc(value)
    if parsed is None:
        return None
    return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _read_history_records(storage_root: Path) -> list[dict[str, Any]]:
    if not storage_root.exists():
        return []
    records = []
    for parquet_file in sorted(storage_root.rglob("*.parquet")):
        table = pq.ParquetFile(parquet_file).read()
        records.extend(table.to_pylist())
    return [_normalize_existing(record) for record in records]


def _rewrite_history(storage_root: Path, records: list[dict[str, Any]]) -> None:
    if storage_root.exists():
        for parquet_file in sorted(storage_root.rglob("*.parquet")):
            parquet_file.unlink()
    by_partition: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for record in records:
        year, month = _partition_time(record)
        key = (_partition_value(record["source"]), year, month)
        by_partition.setdefault(key, []).append(record)

    for (source, year, month), partition_records in sorted(by_partition.items()):
        partition_dir = storage_root / f"source={source}" / f"year={year}" / f"month={month}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pylist(partition_records, schema=TEXT_EVENT_HISTORY_SCHEMA)
        pq.write_table(table, partition_dir / "part-000.parquet")


def _normalize_existing(record: dict[str, Any]) -> dict[str, Any]:
    normalized = {}
    for field in TEXT_EVENT_HISTORY_SCHEMA.names:
        value = record.get(field)
        if field in {"origin_run_ids", "warnings", "source_artifacts"}:
            normalized[field] = [str(item) for item in value or [] if isinstance(item, str)]
        else:
            normalized[field] = str(value) if value is not None else None
    normalized["status"] = normalized["status"] or "active"
    return normalized


def _skipped_state(config_path: Path, *, reason: str, now: datetime | str | None) -> dict[str, Any]:
    return {
        "schema_version": TEXT_EVENT_HISTORY_SCHEMA_VERSION,
        "artifact_type": "text_event_history_state",
        "updated_at": _format_utc(now),
        "status": "skipped",
        "storage_path": display_path(
            text_event_history_storage_path(config_path),
            base=runtime_root(config_path),
        ),
        "state_path": display_path(text_event_history_state_path(config_path), base=runtime_root(config_path)),
        "totals": {
            "records": 0,
            "incoming_records": 0,
            "inserted_records": 0,
            "updated_records": 0,
            "duplicate_records": 0,
            "conflicting_duplicates": 0,
            "same_event_groups": 0,
            "same_event_grouped_records": 0,
            "same_event_candidate_pairs": 0,
            "same_event_candidate_pair_omitted_count": 0,
            "warning_count": 1,
            "error_count": 0,
        },
        "sources": [],
        "same_event_groups": [],
        "same_event_group_candidates": [],
        "warnings": [reason],
        "errors": [],
        "source_artifacts": [],
    }


def _record_manifest_summary(run: RunContext, state: dict[str, Any]) -> None:
    _apply_manifest_summary(run.manifest, state)


def _apply_manifest_summary(manifest: dict[str, Any], state: dict[str, Any]) -> None:
    totals = state["totals"]
    if state["status"] != "skipped":
        manifest.setdefault("artifacts", {})["text_event_history_state"] = TEXT_EVENT_HISTORY_STATE_ARTIFACT
    manifest["text_event_history"] = {
        "status": state["status"],
        "storage_path": state["storage_path"],
        "state_path": state["state_path"],
        "records": totals["records"],
        "incoming_records": totals["incoming_records"],
        "duplicate_records": totals["duplicate_records"],
        "conflicting_duplicates": totals["conflicting_duplicates"],
        "same_event_groups": totals["same_event_groups"],
        "same_event_grouped_records": totals["same_event_grouped_records"],
        "warnings": totals["warning_count"],
        "errors": totals["error_count"],
    }
    counts = manifest.setdefault("counts", {})
    counts["text_event_history_records"] = totals["records"]
    counts["text_event_history_incoming_records"] = totals["incoming_records"]
    counts["text_event_history_duplicate_records"] = totals["duplicate_records"]
    counts["text_event_history_conflicting_duplicates"] = totals["conflicting_duplicates"]
    counts["text_event_history_same_event_groups"] = totals["same_event_groups"]
    counts["text_event_history_same_event_grouped_records"] = totals["same_event_grouped_records"]
    counts["text_event_history_warnings"] = totals["warning_count"]
    counts["text_event_history_errors"] = totals["error_count"]


def _source_summaries(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_source: dict[str, int] = {}
    for record in records:
        by_source[record["source"]] = by_source.get(record["source"], 0) + 1
    return [{"source": source, "record_count": count} for source, count in sorted(by_source.items())]


def _source_artifacts(record: dict[str, Any], origin: _TextEventHistoryOrigin) -> list[str]:
    artifacts = [origin.records_artifact_ref]
    for artifact in record.get("source_artifacts") or []:
        if not isinstance(artifact, str) or not artifact:
            continue
        if origin.source_artifact_base is None:
            artifacts.append(artifact)
        else:
            artifacts.append(display_path(origin.source_artifact_base / artifact, base=runtime_root(origin.config_path)))
    return _unique_sorted(artifacts)


def _stable_event_key(
    *,
    source: str,
    canonical_url: str | None,
    raw_item_id: str,
    content_hash: str,
) -> str:
    identity = canonical_url or raw_item_id or content_hash
    digest = hashlib.sha256(f"{source}|{identity}".encode("utf-8")).hexdigest()[:24]
    return f"text_event_history:{digest}"


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _optional_utc(value: Any, field: str, stable_event_key: str) -> tuple[str | None, str | None]:
    if not isinstance(value, str) or not value.strip():
        return None, None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None, f"{field} is not a valid ISO 8601 timestamp for {stable_event_key}."
    if parsed.tzinfo is None:
        return None, f"{field} must include a UTC offset for {stable_event_key}."
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"), None


def _latest_timestamp(left: Any, right: Any) -> str:
    left_text = _optional_text(left)
    right_text = _optional_text(right)
    if left_text is None:
        return right_text or ""
    if right_text is None:
        return left_text
    return max(left_text, right_text)


def _partition_time(record: dict[str, Any]) -> tuple[str, str]:
    for field in ("published_at", "collected_at", "first_seen_at"):
        value = record.get(field)
        if not isinstance(value, str) or not value:
            continue
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
        parsed = parsed.astimezone(timezone.utc)
        return f"{parsed.year:04d}", f"{parsed.month:02d}"
    return "unknown", "unknown"


def _partition_value(value: str) -> str:
    cleaned = "".join(character.lower() if character.isalnum() else "_" for character in value)
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    return cleaned or "unknown_source"


def _status(*, record_count: int, warnings: list[str]) -> str:
    if warnings:
        return "warning"
    if record_count == 0:
        return "skipped"
    return "ok"


def _clean_text(value: Any, *, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _optional_text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("updated_at must include a UTC offset.")
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str):
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("updated_at must be an ISO 8601 UTC string.") from exc
        if timestamp.tzinfo is None:
            raise ValueError("updated_at must include a UTC offset.")
        timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)
    else:
        raise ValueError("updated_at must be a datetime or ISO 8601 UTC string.")
    return timestamp.isoformat().replace("+00:00", "Z")


def _unique_sorted(values: list[str]) -> list[str]:
    return sorted(set(values))
