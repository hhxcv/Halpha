from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from halpha.runtime.pipeline_contracts import RunContext
from halpha.storage import display_path, resolve_runtime_path, runtime_root, write_json


TEXT_EVENT_HISTORY_SCHEMA_VERSION = 1
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
        pa.field("status", pa.string()),
        pa.field("warnings", pa.list_(pa.string())),
        pa.field("source_artifacts", pa.list_(pa.string())),
    ]
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
    warnings = _unique_sorted([*incoming_warnings, *merge_summary["warnings"]])
    status = _status(record_count=len(merged_records), warnings=warnings)

    _rewrite_history(storage_root, merged_records)
    base = runtime_root(origin.config_path)
    state = {
        "schema_version": TEXT_EVENT_HISTORY_SCHEMA_VERSION,
        "artifact_type": "text_event_history_state",
        "updated_at": _format_utc(now),
        "status": status,
        "storage_path": display_path(storage_root, base=base),
        "state_path": display_path(state_path, base=base),
        "totals": {
            "records": len(merged_records),
            "incoming_records": len(incoming_records),
            "inserted_records": merge_summary["inserted_records"],
            "updated_records": merge_summary["updated_records"],
            "duplicate_records": merge_summary["duplicate_records"],
            "conflicting_duplicates": merge_summary["conflicting_duplicates"],
            "warning_count": len(warnings),
            "error_count": 0,
        },
        "sources": _source_summaries(merged_records),
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
            "warning_count": 1,
            "error_count": 0,
        },
        "sources": [],
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
        "warnings": totals["warning_count"],
        "errors": totals["error_count"],
    }
    counts = manifest.setdefault("counts", {})
    counts["text_event_history_records"] = totals["records"]
    counts["text_event_history_incoming_records"] = totals["incoming_records"]
    counts["text_event_history_duplicate_records"] = totals["duplicate_records"]
    counts["text_event_history_conflicting_duplicates"] = totals["conflicting_duplicates"]
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
