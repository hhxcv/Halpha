from __future__ import annotations

import json
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from halpha.collectors.macro_calendar import MACRO_CALENDAR_ARTIFACT
from halpha.data.history_merge import merge_history_records
from halpha.runtime.pipeline_contracts import PipelineError, RunContext
from halpha.storage import display_path, resolve_runtime_path, runtime_root, write_json


STAGE_NAME = "sync_macro_calendar_history"
MACRO_CALENDAR_HISTORY_SCHEMA_VERSION = 1
MACRO_CALENDAR_HISTORY_STORAGE_ARTIFACT = "data/macro/calendar"
MACRO_CALENDAR_HISTORY_SCHEMA_ARTIFACT = "data/macro/metadata/macro_calendar_schema.json"
MACRO_CALENDAR_HISTORY_STATE_ARTIFACT = "data/macro/metadata/macro_calendar_state.json"


def sync_macro_calendar_history(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    macro_calendar = _macro_calendar_config(config)
    if not macro_calendar.get("enabled"):
        _record_manifest_summary(run, _skipped_state(run, reason="macro_calendar.enabled is false.", now=now))
        return []

    raw_path = run.raw_dir / "macro_calendar.json"
    if not raw_path.exists():
        _record_manifest_summary(run, _skipped_state(run, reason=f"{MACRO_CALENDAR_ARTIFACT} was not found.", now=now))
        return []

    raw = _read_raw_artifact(raw_path)
    storage_root = macro_calendar_history_storage_path(run.config_path)
    schema_path = macro_calendar_history_schema_path(run.config_path)
    state_path = macro_calendar_history_state_path(run.config_path)

    incoming_records, incoming_warnings = _history_records(raw, run, now=now)
    existing_records = _read_history_records(storage_root)
    merged_records, merge_summary = _merge_history(existing_records, incoming_records)
    warnings = _unique_sorted([*incoming_warnings, *_raw_warning_messages(raw), *merge_summary["warnings"]])
    errors = _raw_errors(raw)

    _rewrite_history(storage_root, merged_records)
    _write_schema(schema_path, run)
    base = runtime_root(run.config_path)
    state = {
        "schema_version": MACRO_CALENDAR_HISTORY_SCHEMA_VERSION,
        "artifact_type": "macro_calendar_state",
        "updated_at": _format_utc(now),
        "status": _status(record_count=len(merged_records), warnings=warnings, errors=errors),
        "storage_path": display_path(storage_root, base=base),
        "schema_path": display_path(schema_path, base=base),
        "state_path": display_path(state_path, base=base),
        "totals": {
            "records": len(merged_records),
            "incoming_records": len(incoming_records),
            "inserted_records": merge_summary["inserted_records"],
            "updated_records": merge_summary["updated_records"],
            "duplicate_records": merge_summary["duplicate_records"],
            "conflicting_duplicates": merge_summary["conflicting_duplicates"],
            "warning_count": len(warnings),
            "error_count": len(errors),
        },
        "groups": _group_summaries(merged_records, base),
        "ranges": _ranges(merged_records),
        "availability": _availability_summaries(raw),
        "warnings": warnings,
        "errors": errors,
        "source_artifacts": [MACRO_CALENDAR_ARTIFACT],
    }
    write_json(state_path, state)
    _record_manifest_summary(run, state)
    return [MACRO_CALENDAR_HISTORY_SCHEMA_ARTIFACT, MACRO_CALENDAR_HISTORY_STATE_ARTIFACT]


def macro_calendar_history_storage_path(config_path: Path) -> Path:
    return resolve_runtime_path(MACRO_CALENDAR_HISTORY_STORAGE_ARTIFACT, config_path=config_path)


def macro_calendar_history_schema_path(config_path: Path) -> Path:
    return resolve_runtime_path(MACRO_CALENDAR_HISTORY_SCHEMA_ARTIFACT, config_path=config_path)


def macro_calendar_history_state_path(config_path: Path) -> Path:
    return resolve_runtime_path(MACRO_CALENDAR_HISTORY_STATE_ARTIFACT, config_path=config_path)


def macro_calendar_group_path(
    config_path: Path,
    *,
    source: str,
    data_class: str,
    region: str,
) -> Path:
    return _group_path_from_storage_root(
        macro_calendar_history_storage_path(config_path),
        source=source,
        data_class=data_class,
        region=region,
    )


def read_macro_calendar_history_records(config_path: Path) -> list[dict[str, Any]]:
    return _read_history_records(macro_calendar_history_storage_path(config_path))


def _history_records(
    raw: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    observed_at = _format_utc(now)
    records = []
    warnings = []
    for item in _list(raw.get("items")):
        if not isinstance(item, dict):
            warnings.append("raw macro calendar item is not a JSON object.")
            continue
        try:
            records.append(_history_record(item, run, observed_at=observed_at))
        except PipelineError as exc:
            warnings.append(str(exc))
    return sorted(records, key=lambda record: record["history_key"]), _unique_sorted(warnings)


def _history_record(item: dict[str, Any], run: RunContext, *, observed_at: str) -> dict[str, Any]:
    source = _required_text(item, "source")
    data_class = _required_text(item, "data_class")
    region = _required_text(item, "region")
    event_name = _required_text(item, "event_name")
    event_type = _required_text(item, "event_type")
    scheduled_at = _required_text(item, "scheduled_at")
    item_id = _required_text(item, "item_id")
    endpoint = _required_text(item, "endpoint")
    metrics = _mapping(item.get("metrics"))
    units = _mapping(item.get("units"))
    raw_fields = _mapping(item.get("raw_fields"))
    warnings = _string_list(item.get("warnings"))
    errors = _error_list(item.get("errors"))
    affected_assets = _string_list(item.get("affected_assets"))

    signature = _payload_signature(
        event_name=event_name,
        event_type=event_type,
        source_timezone=str(item.get("source_timezone") or ""),
        importance=str(item.get("importance") or ""),
        source_published_at=item.get("source_published_at"),
        endpoint=endpoint,
        metrics=metrics,
        units=units,
        raw_fields=raw_fields,
    )
    return {
        "history_key": _history_key(
            source=source,
            data_class=data_class,
            region=region,
            event_name=event_name,
            scheduled_at=scheduled_at,
        ),
        "item_id": item_id,
        "data_class": data_class,
        "source": source,
        "event_name": event_name,
        "event_type": event_type,
        "region": region,
        "affected_assets": affected_assets,
        "scheduled_at": scheduled_at,
        "source_timezone": str(item.get("source_timezone") or ""),
        "importance": str(item.get("importance") or ""),
        "source_published_at": item.get("source_published_at"),
        "endpoint": endpoint,
        "metrics": metrics,
        "units": units,
        "raw_fields": raw_fields,
        "payload_signature": signature,
        "origin_run_ids": [run.run_id],
        "first_seen_run_id": run.run_id,
        "last_seen_run_id": run.run_id,
        "first_seen_at": observed_at,
        "last_seen_at": observed_at,
        "status": "warning" if warnings or errors else "active",
        "warnings": warnings,
        "errors": errors,
        "source_artifacts": [display_path(run.raw_dir / "macro_calendar.json", base=runtime_root(run.config_path))],
    }


def _merge_history(
    existing_records: list[dict[str, Any]],
    incoming_records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return merge_history_records(
        existing_records,
        incoming_records,
        conflict_label="macro calendar",
        sort_key=_record_sort_key,
        extra_string_list_fields=("affected_assets",),
        replace_conflicting_payload=True,
    )


def _read_history_records(storage_root: Path) -> list[dict[str, Any]]:
    if not storage_root.exists():
        return []
    records = []
    for records_file in sorted(storage_root.rglob("records.json")):
        try:
            loaded = json.loads(records_file.read_text(encoding="utf-8"))
        except JSONDecodeError:
            continue
        if isinstance(loaded, list):
            records.extend(record for record in loaded if isinstance(record, dict))
    return sorted((_normalize_existing(record) for record in records), key=lambda record: _record_sort_key(record))


def _rewrite_history(storage_root: Path, records: list[dict[str, Any]]) -> None:
    if storage_root.exists():
        for records_file in sorted(storage_root.rglob("records.json")):
            records_file.unlink()
    by_group: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for record in records:
        key = (record["source"], record["data_class"], record["region"])
        by_group.setdefault(key, []).append(record)

    for (source, data_class, region), group_records in sorted(by_group.items()):
        group_dir = _group_path_from_storage_root(
            storage_root,
            source=source,
            data_class=data_class,
            region=region,
        )
        group_dir.mkdir(parents=True, exist_ok=True)
        write_json(group_dir / "records.json", sorted(group_records, key=lambda record: record["scheduled_at"]))


def _write_schema(schema_path: Path, run: RunContext) -> None:
    schema = {
        "schema_version": MACRO_CALENDAR_HISTORY_SCHEMA_VERSION,
        "artifact_type": "macro_calendar_schema",
        "updated_at": _format_utc(None),
        "storage_path": display_path(
            macro_calendar_history_storage_path(run.config_path),
            base=runtime_root(run.config_path),
        ),
        "identity": ["source", "data_class", "region", "event_name", "scheduled_at"],
        "grouping": ["source", "data_class", "region"],
        "record_fields": [
            "history_key",
            "item_id",
            "data_class",
            "source",
            "event_name",
            "event_type",
            "region",
            "affected_assets",
            "scheduled_at",
            "source_timezone",
            "importance",
            "source_published_at",
            "endpoint",
            "metrics",
            "units",
            "raw_fields",
            "origin_run_ids",
            "first_seen_run_id",
            "last_seen_run_id",
            "first_seen_at",
            "last_seen_at",
            "status",
            "warnings",
            "errors",
            "source_artifacts",
        ],
    }
    write_json(schema_path, schema)


def _group_summaries(records: list[dict[str, Any]], config_base: Path) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for record in records:
        key = (record["source"], record["data_class"], record["region"])
        groups.setdefault(key, []).append(record)

    summaries = []
    for (source, data_class, region), group_records in sorted(groups.items()):
        group_records = sorted(group_records, key=lambda record: record["scheduled_at"])
        storage_ref = display_path(
            macro_calendar_group_path(
                config_base / "config.yaml",
                source=source,
                data_class=data_class,
                region=region,
            ),
            base=config_base,
        )
        summaries.append(
            {
                "source": source,
                "data_class": data_class,
                "region": region,
                "record_count": len(group_records),
                "first_scheduled_at": group_records[0]["scheduled_at"],
                "last_scheduled_at": group_records[-1]["scheduled_at"],
                "storage_ref": storage_ref,
            }
        )
    return summaries


def _ranges(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranges = []
    for group in _group_summaries(records, Path(".")):
        ranges.append(
            {
                "source": group["source"],
                "data_class": group["data_class"],
                "region": group["region"],
                "first_scheduled_at": group["first_scheduled_at"],
                "last_scheduled_at": group["last_scheduled_at"],
                "record_count": group["record_count"],
            }
        )
    return ranges


def _availability_summaries(raw: dict[str, Any]) -> list[dict[str, Any]]:
    summaries = []
    for item in _list(raw.get("availability")):
        if not isinstance(item, dict):
            continue
        summaries.append(
            {
                "source": item.get("source"),
                "data_class": item.get("data_class"),
                "status": item.get("status"),
                "record_count": item.get("record_count", 0),
                "parsed_record_count": item.get("parsed_record_count", 0),
                "error_count": item.get("error_count", 0),
                "reason": item.get("reason"),
            }
        )
    return sorted(summaries, key=lambda item: (str(item.get("source") or ""), str(item.get("data_class") or "")))


def _record_manifest_summary(run: RunContext, state: dict[str, Any]) -> None:
    totals = state["totals"]
    if state["status"] != "skipped":
        run.manifest["artifacts"]["macro_calendar_schema"] = MACRO_CALENDAR_HISTORY_SCHEMA_ARTIFACT
        run.manifest["artifacts"]["macro_calendar_state"] = MACRO_CALENDAR_HISTORY_STATE_ARTIFACT
    run.manifest["macro_calendar_history"] = {
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
    counts = run.manifest.setdefault("counts", {})
    counts["macro_calendar_history_records"] = totals["records"]
    counts["macro_calendar_history_incoming_records"] = totals["incoming_records"]
    counts["macro_calendar_history_duplicate_records"] = totals["duplicate_records"]
    counts["macro_calendar_history_conflicting_duplicates"] = totals["conflicting_duplicates"]
    counts["macro_calendar_history_warnings"] = totals["warning_count"]
    counts["macro_calendar_history_errors"] = totals["error_count"]


def _skipped_state(run: RunContext, *, reason: str, now: datetime | str | None) -> dict[str, Any]:
    storage_path = macro_calendar_history_storage_path(run.config_path)
    state_path = macro_calendar_history_state_path(run.config_path)
    return {
        "schema_version": MACRO_CALENDAR_HISTORY_SCHEMA_VERSION,
        "artifact_type": "macro_calendar_state",
        "updated_at": _format_utc(now),
        "status": "skipped",
        "storage_path": display_path(storage_path, base=runtime_root(run.config_path)),
        "schema_path": display_path(
            macro_calendar_history_schema_path(run.config_path),
            base=runtime_root(run.config_path),
        ),
        "state_path": display_path(state_path, base=runtime_root(run.config_path)),
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
        "groups": [],
        "ranges": [],
        "availability": [],
        "warnings": [reason],
        "errors": [],
        "source_artifacts": [],
    }


def _read_raw_artifact(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        raise PipelineError(
            f"{MACRO_CALENDAR_ARTIFACT} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    if not isinstance(raw, dict):
        raise PipelineError(f"{MACRO_CALENDAR_ARTIFACT} must be a JSON object.", stage=STAGE_NAME, exit_code=3)
    return raw


def _raw_warning_messages(raw: dict[str, Any]) -> list[str]:
    warnings = _string_list(raw.get("warnings"))
    for item in _list(raw.get("availability")):
        if isinstance(item, dict) and item.get("status") in {"unavailable", "failed", "partial", "stale"}:
            reason = item.get("reason") or item.get("status")
            warnings.append(
                "macro calendar source availability "
                f"{item.get('data_class') or 'unknown'}: {reason}".strip()
            )
    return _unique_sorted(warnings)


def _raw_errors(raw: dict[str, Any]) -> list[dict[str, Any]]:
    return _error_list(raw.get("errors"))


def _status(*, record_count: int, warnings: list[str], errors: list[dict[str, Any]]) -> str:
    if errors:
        return "warning"
    if warnings:
        return "warning"
    if record_count == 0:
        return "skipped"
    return "ok"


def _history_key(
    *,
    source: str,
    data_class: str,
    region: str,
    event_name: str,
    scheduled_at: str,
) -> str:
    return f"{source}|{data_class}|{region}|{event_name}|{scheduled_at}"


def _payload_signature(
    *,
    event_name: str,
    event_type: str,
    source_timezone: str,
    importance: str,
    source_published_at: Any,
    endpoint: str,
    metrics: dict[str, Any],
    units: dict[str, Any],
    raw_fields: dict[str, Any],
) -> str:
    return json.dumps(
        {
            "event_name": event_name,
            "event_type": event_type,
            "source_timezone": source_timezone,
            "importance": importance,
            "source_published_at": source_published_at,
            "endpoint": endpoint,
            "metrics": metrics,
            "units": units,
            "raw_fields": raw_fields,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _normalize_existing(record: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    normalized["metrics"] = _mapping(record.get("metrics"))
    normalized["units"] = _mapping(record.get("units"))
    normalized["raw_fields"] = _mapping(record.get("raw_fields"))
    normalized["affected_assets"] = _string_list(record.get("affected_assets"))
    normalized["origin_run_ids"] = _string_list(record.get("origin_run_ids"))
    normalized["warnings"] = _string_list(record.get("warnings"))
    normalized["errors"] = _error_list(record.get("errors"))
    normalized["source_artifacts"] = _string_list(record.get("source_artifacts"))
    normalized["status"] = str(record.get("status") or "active")
    normalized["payload_signature"] = str(
        record.get("payload_signature")
        or _payload_signature(
            event_name=str(record.get("event_name") or ""),
            event_type=str(record.get("event_type") or ""),
            source_timezone=str(record.get("source_timezone") or ""),
            importance=str(record.get("importance") or ""),
            source_published_at=record.get("source_published_at"),
            endpoint=str(record.get("endpoint") or ""),
            metrics=normalized["metrics"],
            units=normalized["units"],
            raw_fields=normalized["raw_fields"],
        )
    )
    return normalized


def _record_sort_key(record: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
    return (
        str(record.get("source") or ""),
        str(record.get("data_class") or ""),
        str(record.get("region") or ""),
        str(record.get("scheduled_at") or ""),
        str(record.get("event_name") or ""),
        str(record.get("history_key") or ""),
    )


def _macro_calendar_config(config: dict[str, Any]) -> dict[str, Any]:
    macro_calendar = config.get("macro_calendar")
    return macro_calendar if isinstance(macro_calendar, dict) else {}


def _required_text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PipelineError(f"macro calendar record missing {key}.", stage=STAGE_NAME, exit_code=3)
    return value.strip()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value or [] if isinstance(item, str) and item.strip()]


def _error_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _unique_sorted(values: list[str]) -> list[str]:
    return sorted(set(values))


def _partition_value(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in value)


def _group_path_from_storage_root(
    storage_root: Path,
    *,
    source: str,
    data_class: str,
    region: str,
) -> Path:
    return (
        storage_root
        / f"source={_partition_value(source)}"
        / f"data_class={_partition_value(data_class)}"
        / f"region={_partition_value(region)}"
    )


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise PipelineError("timestamp must include a UTC offset.", stage=STAGE_NAME, exit_code=3)
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str):
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise PipelineError("timestamp must be an ISO 8601 UTC string.", stage=STAGE_NAME, exit_code=3) from exc
        if timestamp.tzinfo is None:
            raise PipelineError("timestamp must include a UTC offset.", stage=STAGE_NAME, exit_code=3)
        timestamp = timestamp.astimezone(timezone.utc).replace(microsecond=0)
    else:
        raise PipelineError("timestamp must be a datetime or ISO 8601 UTC string.", stage=STAGE_NAME, exit_code=3)
    return timestamp.isoformat().replace("+00:00", "Z")
