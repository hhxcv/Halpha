from __future__ import annotations

import json
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from halpha.collectors.derivatives_market import DERIVATIVES_MARKET_ARTIFACT
from halpha.runtime.pipeline_contracts import PipelineError, RunContext
from halpha.storage import display_path, resolve_runtime_path, runtime_root, write_json


STAGE_NAME = "sync_derivatives_market_history"
DERIVATIVES_HISTORY_SCHEMA_VERSION = 1
DERIVATIVES_HISTORY_STORAGE_ARTIFACT = "data/market/derivatives"
DERIVATIVES_HISTORY_SCHEMA_ARTIFACT = "data/market/metadata/derivatives_market_schema.json"
DERIVATIVES_HISTORY_STATE_ARTIFACT = "data/market/metadata/derivatives_market_state.json"


def sync_derivatives_market_history(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    derivatives = _derivatives_config(config)
    if not derivatives.get("enabled"):
        _record_manifest_summary(run, _skipped_state(run, reason="market.derivatives.enabled is false.", now=now))
        return []

    raw_path = run.raw_dir / "derivatives_market.json"
    if not raw_path.exists():
        _record_manifest_summary(run, _skipped_state(run, reason=f"{DERIVATIVES_MARKET_ARTIFACT} was not found.", now=now))
        return []

    raw = _read_raw_artifact(raw_path)
    storage_root = derivatives_market_storage_path(run.config_path)
    schema_path = derivatives_market_schema_path(run.config_path)
    state_path = derivatives_market_state_path(run.config_path)

    incoming_records, incoming_warnings = _history_records(raw, run, now=now)
    existing_records = _read_history_records(storage_root)
    merged_records, merge_summary = _merge_history(existing_records, incoming_records)
    raw_warnings = _raw_warning_messages(raw)
    warnings = _unique_sorted([*incoming_warnings, *raw_warnings, *merge_summary["warnings"]])
    errors = _raw_error_messages(raw)

    _rewrite_history(storage_root, merged_records)
    _write_schema(schema_path, run)
    base = runtime_root(run.config_path)
    state = {
        "schema_version": DERIVATIVES_HISTORY_SCHEMA_VERSION,
        "artifact_type": "derivatives_market_state",
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
        "warnings": warnings,
        "errors": errors,
        "source_artifacts": [DERIVATIVES_MARKET_ARTIFACT],
    }
    write_json(state_path, state)
    _record_manifest_summary(run, state)
    return [DERIVATIVES_HISTORY_SCHEMA_ARTIFACT, DERIVATIVES_HISTORY_STATE_ARTIFACT]


def derivatives_market_storage_path(config_path: Path) -> Path:
    return resolve_runtime_path(DERIVATIVES_HISTORY_STORAGE_ARTIFACT, config_path=config_path)


def derivatives_market_schema_path(config_path: Path) -> Path:
    return resolve_runtime_path(DERIVATIVES_HISTORY_SCHEMA_ARTIFACT, config_path=config_path)


def derivatives_market_state_path(config_path: Path) -> Path:
    return resolve_runtime_path(DERIVATIVES_HISTORY_STATE_ARTIFACT, config_path=config_path)


def derivatives_market_group_path(
    config_path: Path,
    *,
    source: str,
    data_class: str,
    symbol: str,
    period: str,
) -> Path:
    return _group_path_from_storage_root(
        derivatives_market_storage_path(config_path),
        source=source,
        data_class=data_class,
        symbol=symbol,
        period=period,
    )


def read_derivatives_history_records(config_path: Path) -> list[dict[str, Any]]:
    return _read_history_records(derivatives_market_storage_path(config_path))


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
            warnings.append("raw derivatives item is not a JSON object.")
            continue
        try:
            record = _history_record(item, run, observed_at=observed_at)
        except PipelineError as exc:
            warnings.append(str(exc))
            continue
        records.append(record)
    return sorted(records, key=lambda record: record["history_key"]), _unique_sorted(warnings)


def _history_record(item: dict[str, Any], run: RunContext, *, observed_at: str) -> dict[str, Any]:
    source = _required_text(item, "source")
    data_class = _required_text(item, "data_class")
    market_type = _required_text(item, "market_type")
    symbol = _required_text(item, "symbol")
    period = _required_text(item, "period")
    as_of = _required_text(item, "as_of")
    endpoint = _required_text(item, "endpoint")
    item_id = _required_text(item, "item_id")
    metrics = _mapping(item.get("metrics"))
    units = _mapping(item.get("units"))
    raw_fields = _mapping(item.get("raw_fields"))
    warnings = _string_list(item.get("warnings"))
    errors = _string_list(item.get("errors"))

    return {
        "history_key": _history_key(
            source=source,
            market_type=market_type,
            data_class=data_class,
            symbol=symbol,
            period=period,
            as_of=as_of,
        ),
        "item_id": item_id,
        "data_class": data_class,
        "source": source,
        "market_type": market_type,
        "symbol": symbol,
        "period": period,
        "as_of": as_of,
        "endpoint": endpoint,
        "metrics": metrics,
        "units": units,
        "raw_fields": raw_fields,
        "payload_signature": _payload_signature(metrics=metrics, units=units, raw_fields=raw_fields),
        "origin_run_ids": [run.run_id],
        "first_seen_run_id": run.run_id,
        "last_seen_run_id": run.run_id,
        "first_seen_at": observed_at,
        "last_seen_at": observed_at,
        "status": "warning" if warnings or errors else "active",
        "warnings": warnings,
        "errors": errors,
        "source_artifacts": [display_path(run.raw_dir / "derivatives_market.json", base=runtime_root(run.config_path))],
    }


def _merge_history(
    existing_records: list[dict[str, Any]],
    incoming_records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_key = {record["history_key"]: record for record in existing_records}
    inserted = 0
    updated = 0
    duplicate = 0
    conflicts = 0
    warnings = []

    for incoming in incoming_records:
        existing = by_key.get(incoming["history_key"])
        if existing is None:
            by_key[incoming["history_key"]] = incoming
            inserted += 1
            continue

        duplicate += 1
        updated += 1
        if existing.get("payload_signature") != incoming.get("payload_signature"):
            conflicts += 1
            warning = f"conflicting duplicate derivatives record: {incoming['history_key']}"
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
        existing["errors"] = _unique_sorted([*existing.get("errors", []), *incoming.get("errors", [])])
        if (existing["warnings"] or existing["errors"]) and existing.get("status") == "active":
            existing["status"] = "warning"

    return (
        sorted(by_key.values(), key=lambda record: _record_sort_key(record)),
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
        key = (record["source"], record["data_class"], record["symbol"], record["period"])
        by_group.setdefault(key, []).append(record)

    for (source, data_class, symbol, period), group_records in sorted(by_group.items()):
        group_dir = _group_path_from_storage_root(
            storage_root,
            source=source,
            data_class=data_class,
            symbol=symbol,
            period=period,
        )
        group_dir.mkdir(parents=True, exist_ok=True)
        write_json(group_dir / "records.json", sorted(group_records, key=lambda record: record["as_of"]))


def _write_schema(schema_path: Path, run: RunContext) -> None:
    schema = {
        "schema_version": DERIVATIVES_HISTORY_SCHEMA_VERSION,
        "artifact_type": "derivatives_market_schema",
        "updated_at": _format_utc(None),
        "storage_path": display_path(
            derivatives_market_storage_path(run.config_path),
            base=runtime_root(run.config_path),
        ),
        "identity": ["source", "market_type", "data_class", "symbol", "period", "as_of"],
        "grouping": ["source", "data_class", "symbol", "period"],
        "record_fields": [
            "history_key",
            "item_id",
            "data_class",
            "source",
            "market_type",
            "symbol",
            "period",
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
        key = (record["source"], record["data_class"], record["symbol"], record["period"])
        groups.setdefault(key, []).append(record)

    summaries = []
    for (source, data_class, symbol, period), group_records in sorted(groups.items()):
        group_records = sorted(group_records, key=lambda record: record["as_of"])
        storage_ref = display_path(
            derivatives_market_group_path(
                config_base / "config.yaml",
                source=source,
                data_class=data_class,
                symbol=symbol,
                period=period,
            ),
            base=config_base,
        )
        summaries.append(
            {
                "source": source,
                "data_class": data_class,
                "symbol": symbol,
                "period": period,
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
                "symbol": group["symbol"],
                "period": group["period"],
                "first_as_of": group["first_as_of"],
                "last_as_of": group["last_as_of"],
                "record_count": group["record_count"],
            }
        )
    return ranges


def _record_manifest_summary(run: RunContext, state: dict[str, Any]) -> None:
    totals = state["totals"]
    if state["status"] != "skipped":
        run.manifest["artifacts"]["derivatives_market_schema"] = DERIVATIVES_HISTORY_SCHEMA_ARTIFACT
        run.manifest["artifacts"]["derivatives_market_state"] = DERIVATIVES_HISTORY_STATE_ARTIFACT
    run.manifest["derivatives_market_history"] = {
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
    counts["derivatives_market_history_records"] = totals["records"]
    counts["derivatives_market_history_incoming_records"] = totals["incoming_records"]
    counts["derivatives_market_history_duplicate_records"] = totals["duplicate_records"]
    counts["derivatives_market_history_conflicting_duplicates"] = totals["conflicting_duplicates"]
    counts["derivatives_market_history_warnings"] = totals["warning_count"]
    counts["derivatives_market_history_errors"] = totals["error_count"]


def _skipped_state(run: RunContext, *, reason: str, now: datetime | str | None) -> dict[str, Any]:
    storage_path = derivatives_market_storage_path(run.config_path)
    state_path = derivatives_market_state_path(run.config_path)
    return {
        "schema_version": DERIVATIVES_HISTORY_SCHEMA_VERSION,
        "artifact_type": "derivatives_market_state",
        "updated_at": _format_utc(now),
        "status": "skipped",
        "storage_path": display_path(storage_path, base=runtime_root(run.config_path)),
        "schema_path": display_path(
            derivatives_market_schema_path(run.config_path),
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
        "warnings": [reason],
        "errors": [],
        "source_artifacts": [],
    }


def _read_raw_artifact(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        raise PipelineError(
            f"{DERIVATIVES_MARKET_ARTIFACT} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    if not isinstance(raw, dict):
        raise PipelineError(f"{DERIVATIVES_MARKET_ARTIFACT} must be a JSON object.", stage=STAGE_NAME, exit_code=3)
    return raw


def _raw_warning_messages(raw: dict[str, Any]) -> list[str]:
    warnings = _string_list(raw.get("warnings"))
    for item in _list(raw.get("availability")):
        if isinstance(item, dict) and item.get("status") in {"unavailable", "failed", "partial"}:
            reason = item.get("reason") or item.get("status")
            warnings.append(
                "derivatives source availability "
                f"{item.get('data_class') or 'unknown'} {item.get('symbol') or ''} "
                f"{item.get('period') or ''}: {reason}".strip()
            )
    return _unique_sorted(warnings)


def _raw_error_messages(raw: dict[str, Any]) -> list[str]:
    messages = []
    for error in _list(raw.get("errors")):
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                messages.append(message.strip())
    return _unique_sorted(messages)


def _status(*, record_count: int, warnings: list[str], errors: list[str]) -> str:
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
    market_type: str,
    data_class: str,
    symbol: str,
    period: str,
    as_of: str,
) -> str:
    return f"{source}|{market_type}|{data_class}|{symbol}|{period}|{as_of}"


def _payload_signature(*, metrics: dict[str, Any], units: dict[str, Any], raw_fields: dict[str, Any]) -> str:
    return json.dumps(
        {"metrics": metrics, "units": units, "raw_fields": raw_fields},
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
    normalized["errors"] = _string_list(record.get("errors"))
    normalized["source_artifacts"] = _string_list(record.get("source_artifacts"))
    normalized["status"] = str(record.get("status") or "active")
    normalized["payload_signature"] = str(
        record.get("payload_signature")
        or _payload_signature(
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
        str(record.get("symbol") or ""),
        str(record.get("period") or ""),
        str(record.get("as_of") or ""),
        str(record.get("history_key") or ""),
    )


def _derivatives_config(config: dict[str, Any]) -> dict[str, Any]:
    market = config.get("market")
    if not isinstance(market, dict):
        return {}
    derivatives = market.get("derivatives")
    return derivatives if isinstance(derivatives, dict) else {}


def _required_text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PipelineError(f"derivatives record missing {key}.", stage=STAGE_NAME, exit_code=3)
    return value.strip()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value or [] if isinstance(item, str) and item.strip()]


def _unique_sorted(values: list[str]) -> list[str]:
    return sorted(set(values))


def _latest_timestamp(left: Any, right: Any) -> str:
    left_text = str(left or "")
    right_text = str(right or "")
    return max(left_text, right_text)


def _partition_value(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in value)


def _group_path_from_storage_root(
    storage_root: Path,
    *,
    source: str,
    data_class: str,
    symbol: str,
    period: str,
) -> Path:
    return (
        storage_root
        / f"source={_partition_value(source)}"
        / f"data_class={_partition_value(data_class)}"
        / f"symbol={_partition_value(symbol)}"
        / f"period={_partition_value(period)}"
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
