from __future__ import annotations

import json
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from halpha.collectors.onchain_flow import ONCHAIN_FLOW_ARTIFACT
from halpha.runtime.pipeline_contracts import PipelineError, RunContext
from halpha.storage import display_path, resolve_runtime_path, runtime_root, write_json


STAGE_NAME = "sync_onchain_flow_history"
ONCHAIN_FLOW_HISTORY_SCHEMA_VERSION = 1
ONCHAIN_FLOW_HISTORY_STORAGE_ARTIFACT = "data/onchain/flow"
ONCHAIN_FLOW_HISTORY_SCHEMA_ARTIFACT = "data/onchain/metadata/onchain_flow_schema.json"
ONCHAIN_FLOW_HISTORY_STATE_ARTIFACT = "data/onchain/metadata/onchain_flow_state.json"


def sync_onchain_flow_history(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    onchain_flow = _onchain_flow_config(config)
    if not onchain_flow.get("enabled"):
        _record_manifest_summary(run, _skipped_state(run, reason="onchain_flow.enabled is false.", now=now))
        return []

    raw_path = run.raw_dir / "onchain_flow.json"
    if not raw_path.exists():
        _record_manifest_summary(run, _skipped_state(run, reason=f"{ONCHAIN_FLOW_ARTIFACT} was not found.", now=now))
        return []

    raw = _read_raw_artifact(raw_path)
    storage_root = onchain_flow_storage_path(run.config_path)
    schema_path = onchain_flow_schema_path(run.config_path)
    state_path = onchain_flow_state_path(run.config_path)

    incoming_records, incoming_warnings = _history_records(raw, run, now=now)
    existing_records = _read_history_records(storage_root)
    merged_records, merge_summary = _merge_history(existing_records, incoming_records)
    warnings = _unique_sorted([*incoming_warnings, *_raw_warning_messages(raw), *merge_summary["warnings"]])
    errors = _raw_errors(raw)

    _rewrite_history(storage_root, merged_records)
    _write_schema(schema_path, run)
    base = runtime_root(run.config_path)
    state = {
        "schema_version": ONCHAIN_FLOW_HISTORY_SCHEMA_VERSION,
        "artifact_type": "onchain_flow_state",
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
        "source_artifacts": [ONCHAIN_FLOW_ARTIFACT],
    }
    write_json(state_path, state)
    _record_manifest_summary(run, state)
    return [ONCHAIN_FLOW_HISTORY_SCHEMA_ARTIFACT, ONCHAIN_FLOW_HISTORY_STATE_ARTIFACT]


def onchain_flow_storage_path(config_path: Path) -> Path:
    return resolve_runtime_path(ONCHAIN_FLOW_HISTORY_STORAGE_ARTIFACT, config_path=config_path)


def onchain_flow_schema_path(config_path: Path) -> Path:
    return resolve_runtime_path(ONCHAIN_FLOW_HISTORY_SCHEMA_ARTIFACT, config_path=config_path)


def onchain_flow_state_path(config_path: Path) -> Path:
    return resolve_runtime_path(ONCHAIN_FLOW_HISTORY_STATE_ARTIFACT, config_path=config_path)


def onchain_flow_group_path(
    config_path: Path,
    *,
    source: str,
    data_class: str,
    asset: str,
    chain: str,
) -> Path:
    return _group_path_from_storage_root(
        onchain_flow_storage_path(config_path),
        source=source,
        data_class=data_class,
        asset=asset,
        chain=chain,
    )


def read_onchain_flow_history_records(config_path: Path) -> list[dict[str, Any]]:
    return _read_history_records(onchain_flow_storage_path(config_path))


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
            warnings.append("raw on-chain flow item is not a JSON object.")
            continue
        try:
            records.append(_history_record(item, run, observed_at=observed_at))
        except PipelineError as exc:
            warnings.append(str(exc))
    return sorted(records, key=lambda record: record["history_key"]), _unique_sorted(warnings)


def _history_record(item: dict[str, Any], run: RunContext, *, observed_at: str) -> dict[str, Any]:
    source = _required_text(item, "source")
    data_class = _required_text(item, "data_class")
    asset = _required_text(item, "asset")
    chain = _required_text(item, "chain")
    as_of = _required_text(item, "as_of")
    endpoint = _required_text(item, "endpoint")
    item_id = _required_text(item, "item_id")
    metrics = _mapping(item.get("metrics"))
    units = _mapping(item.get("units"))
    raw_fields = _mapping(item.get("raw_fields"))
    warnings = _string_list(item.get("warnings"))
    errors = _error_list(item.get("errors"))

    signature = _payload_signature(endpoint=endpoint, metrics=metrics, units=units, raw_fields=raw_fields)
    return {
        "history_key": _history_key(
            source=source,
            data_class=data_class,
            asset=asset,
            chain=chain,
            as_of=as_of,
        ),
        "item_id": item_id,
        "data_class": data_class,
        "source": source,
        "asset": asset,
        "chain": chain,
        "as_of": as_of,
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
        "source_artifacts": [display_path(run.raw_dir / "onchain_flow.json", base=runtime_root(run.config_path))],
    }


def _merge_history(
    existing_records: list[dict[str, Any]],
    incoming_records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    _clear_stale_merge_warnings(existing_records)
    by_key = {record["history_key"]: record for record in existing_records}
    inserted = 0
    updated = 0
    duplicate = 0
    conflicts = 0
    warnings: list[str] = []

    for incoming in incoming_records:
        existing = by_key.get(incoming["history_key"])
        if existing is None:
            by_key[incoming["history_key"]] = incoming
            inserted += 1
            continue

        duplicate += 1
        updated += 1
        conflict_warnings = _merge_onchain_record(existing, incoming)
        if conflict_warnings:
            conflicts += 1
            warnings.extend(conflict_warnings)

    return (
        sorted(by_key.values(), key=_record_sort_key),
        {
            "inserted_records": inserted,
            "updated_records": updated,
            "duplicate_records": duplicate,
            "conflicting_duplicates": conflicts,
            "warnings": _unique_sorted(warnings),
        },
    )


def _merge_onchain_record(existing: dict[str, Any], incoming: dict[str, Any]) -> list[str]:
    history_key = incoming["history_key"]
    conflict_warning = f"conflicting duplicate on-chain flow record: {history_key}"
    metric_conflicts = _merge_mapping_without_overwrite(existing, incoming, "metrics")
    unit_conflicts = _merge_mapping_without_overwrite(existing, incoming, "units", case_insensitive_text=True)
    _merge_raw_fields(existing, incoming)

    if _incoming_has_more_specific_endpoint(existing, incoming):
        existing["endpoint"] = incoming["endpoint"]
    existing["payload_signature"] = _payload_signature(
        endpoint=existing["endpoint"],
        metrics=_mapping(existing.get("metrics")),
        units=_mapping(existing.get("units")),
        raw_fields=_mapping(existing.get("raw_fields")),
    )
    existing["origin_run_ids"] = _unique_sorted(
        [*existing.get("origin_run_ids", []), *incoming.get("origin_run_ids", [])]
    )
    existing["last_seen_run_id"] = incoming["last_seen_run_id"]
    existing["last_seen_at"] = _latest_timestamp(existing.get("last_seen_at"), incoming.get("last_seen_at"))
    existing["source_artifacts"] = _unique_sorted(
        [*existing.get("source_artifacts", []), *incoming.get("source_artifacts", [])]
    )
    existing_warnings = _without_warning(_string_list(existing.get("warnings")), conflict_warning)
    incoming_warnings = _without_warning(_string_list(incoming.get("warnings")), conflict_warning)
    conflicts = [*metric_conflicts, *unit_conflicts]
    if conflicts:
        existing_warnings.append(conflict_warning)
        existing_warnings.extend(conflicts)
    existing["warnings"] = _unique_sorted([*existing_warnings, *incoming_warnings])
    existing["errors"] = _error_list([*existing.get("errors", []), *incoming.get("errors", [])])
    existing["status"] = "warning" if existing["warnings"] or existing["errors"] else "active"
    return [conflict_warning] if conflicts else []


def _merge_mapping_without_overwrite(
    existing: dict[str, Any],
    incoming: dict[str, Any],
    field: str,
    *,
    case_insensitive_text: bool = False,
) -> list[str]:
    existing_value = _mapping(existing.get(field))
    incoming_value = _mapping(incoming.get(field))
    conflicts = []
    for key, value in sorted(incoming_value.items()):
        if key not in existing_value:
            existing_value[key] = value
        elif _same_merge_value(existing_value[key], value, case_insensitive_text=case_insensitive_text):
            existing_value[key] = value
        else:
            conflicts.append(f"conflicting on-chain flow {field}.{key} for {incoming['history_key']}.")
    existing[field] = existing_value
    return conflicts


def _same_merge_value(left: Any, right: Any, *, case_insensitive_text: bool) -> bool:
    if left == right:
        return True
    if case_insensitive_text and isinstance(left, str) and isinstance(right, str):
        return left.strip().lower() == right.strip().lower()
    return False


def _merge_raw_fields(existing: dict[str, Any], incoming: dict[str, Any]) -> None:
    existing["raw_fields"] = _merge_raw_mapping(
        _mapping(existing.get("raw_fields")),
        _mapping(incoming.get("raw_fields")),
    )


def _merge_raw_mapping(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key, value in sorted(incoming.items()):
        if key not in merged:
            merged[key] = value
        elif isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _merge_raw_mapping(merged[key], value)
    return merged


def _incoming_has_more_specific_endpoint(existing: dict[str, Any], incoming: dict[str, Any]) -> bool:
    incoming_metrics = _mapping(incoming.get("metrics"))
    existing_metrics = _mapping(existing.get("metrics"))
    return len(incoming_metrics) >= len(existing_metrics) and incoming.get("endpoint") != existing.get("endpoint")


def _latest_timestamp(left: Any, right: Any) -> str:
    left_value = str(left) if left else ""
    right_value = str(right) if right else ""
    return max(left_value, right_value)


def _without_warning(warnings: list[str], warning: str) -> list[str]:
    return [item for item in warnings if item != warning]


def _clear_stale_merge_warnings(records: list[dict[str, Any]]) -> None:
    for record in records:
        warnings = [warning for warning in _string_list(record.get("warnings")) if not _is_merge_warning(warning)]
        record["warnings"] = warnings
        if not warnings and not _error_list(record.get("errors")):
            record["status"] = "active"


def _is_merge_warning(warning: str) -> bool:
    return warning.startswith("conflicting duplicate on-chain flow record:") or warning.startswith(
        "conflicting on-chain flow "
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
    by_group: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for record in records:
        key = (record["source"], record["data_class"], record["asset"], record["chain"])
        by_group.setdefault(key, []).append(record)

    for (source, data_class, asset, chain), group_records in sorted(by_group.items()):
        group_dir = _group_path_from_storage_root(
            storage_root,
            source=source,
            data_class=data_class,
            asset=asset,
            chain=chain,
        )
        group_dir.mkdir(parents=True, exist_ok=True)
        write_json(group_dir / "records.json", sorted(group_records, key=lambda record: record["as_of"]))


def _write_schema(schema_path: Path, run: RunContext) -> None:
    schema = {
        "schema_version": ONCHAIN_FLOW_HISTORY_SCHEMA_VERSION,
        "artifact_type": "onchain_flow_schema",
        "updated_at": _format_utc(None),
        "storage_path": display_path(onchain_flow_storage_path(run.config_path), base=runtime_root(run.config_path)),
        "identity": ["source", "data_class", "asset", "chain", "as_of"],
        "grouping": ["source", "data_class", "asset", "chain"],
        "record_fields": [
            "history_key",
            "item_id",
            "data_class",
            "source",
            "asset",
            "chain",
            "as_of",
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
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for record in records:
        key = (record["source"], record["data_class"], record["asset"], record["chain"])
        groups.setdefault(key, []).append(record)

    summaries = []
    for (source, data_class, asset, chain), group_records in sorted(groups.items()):
        group_records = sorted(group_records, key=lambda record: record["as_of"])
        storage_ref = display_path(
            onchain_flow_group_path(
                config_base / "config.yaml",
                source=source,
                data_class=data_class,
                asset=asset,
                chain=chain,
            ),
            base=config_base,
        )
        summaries.append(
            {
                "source": source,
                "data_class": data_class,
                "asset": asset,
                "chain": chain,
                "record_count": len(group_records),
                "first_as_of": group_records[0]["as_of"],
                "last_as_of": group_records[-1]["as_of"],
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
                "asset": group["asset"],
                "chain": group["chain"],
                "first_as_of": group["first_as_of"],
                "last_as_of": group["last_as_of"],
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
        run.manifest["artifacts"]["onchain_flow_schema"] = ONCHAIN_FLOW_HISTORY_SCHEMA_ARTIFACT
        run.manifest["artifacts"]["onchain_flow_state"] = ONCHAIN_FLOW_HISTORY_STATE_ARTIFACT
    run.manifest["onchain_flow_history"] = {
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
    counts["onchain_flow_history_records"] = totals["records"]
    counts["onchain_flow_history_incoming_records"] = totals["incoming_records"]
    counts["onchain_flow_history_duplicate_records"] = totals["duplicate_records"]
    counts["onchain_flow_history_conflicting_duplicates"] = totals["conflicting_duplicates"]
    counts["onchain_flow_history_warnings"] = totals["warning_count"]
    counts["onchain_flow_history_errors"] = totals["error_count"]


def _skipped_state(run: RunContext, *, reason: str, now: datetime | str | None) -> dict[str, Any]:
    storage_path = onchain_flow_storage_path(run.config_path)
    state_path = onchain_flow_state_path(run.config_path)
    return {
        "schema_version": ONCHAIN_FLOW_HISTORY_SCHEMA_VERSION,
        "artifact_type": "onchain_flow_state",
        "updated_at": _format_utc(now),
        "status": "skipped",
        "storage_path": display_path(storage_path, base=runtime_root(run.config_path)),
        "schema_path": display_path(onchain_flow_schema_path(run.config_path), base=runtime_root(run.config_path)),
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
            f"{ONCHAIN_FLOW_ARTIFACT} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    if not isinstance(raw, dict):
        raise PipelineError(f"{ONCHAIN_FLOW_ARTIFACT} must be a JSON object.", stage=STAGE_NAME, exit_code=3)
    return raw


def _raw_warning_messages(raw: dict[str, Any]) -> list[str]:
    warnings = _string_list(raw.get("warnings"))
    warning_statuses = {"failed", "partial", "stale", "unavailable", "insufficient_data"}
    for item in _list(raw.get("availability")):
        if isinstance(item, dict) and item.get("status") in warning_statuses:
            reason = item.get("reason") or item.get("status")
            warnings.append(
                "on-chain flow source availability "
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
    asset: str,
    chain: str,
    as_of: str,
) -> str:
    return f"{source}|{data_class}|{asset}|{chain}|{as_of}"


def _payload_signature(
    *,
    endpoint: str,
    metrics: dict[str, Any],
    units: dict[str, Any],
    raw_fields: dict[str, Any],
) -> str:
    return json.dumps(
        {
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
    normalized["origin_run_ids"] = _string_list(record.get("origin_run_ids"))
    normalized["warnings"] = _string_list(record.get("warnings"))
    normalized["errors"] = _error_list(record.get("errors"))
    normalized["source_artifacts"] = _string_list(record.get("source_artifacts"))
    normalized["status"] = str(record.get("status") or "active")
    normalized["payload_signature"] = str(
        record.get("payload_signature")
        or _payload_signature(
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
        str(record.get("asset") or ""),
        str(record.get("chain") or ""),
        str(record.get("as_of") or ""),
        str(record.get("history_key") or ""),
    )


def _onchain_flow_config(config: dict[str, Any]) -> dict[str, Any]:
    onchain_flow = config.get("onchain_flow")
    return onchain_flow if isinstance(onchain_flow, dict) else {}


def _required_text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PipelineError(f"on-chain flow record missing {key}.", stage=STAGE_NAME, exit_code=3)
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
    asset: str,
    chain: str,
) -> Path:
    return (
        storage_root
        / f"source={_partition_value(source)}"
        / f"data_class={_partition_value(data_class)}"
        / f"asset={_partition_value(asset)}"
        / f"chain={_partition_value(chain)}"
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
