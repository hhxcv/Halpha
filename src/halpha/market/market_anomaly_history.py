from __future__ import annotations

import json
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from halpha.collectors.market_anomalies import MARKET_ANOMALIES_ARTIFACT
from halpha.data.collection_coverage import (
    COVERAGE_STATE_ARTIFACT,
    read_collection_coverage_state,
    write_collection_coverage_state,
)
from halpha.runtime.pipeline_contracts import PipelineError, RunContext
from halpha.storage import display_path, resolve_runtime_path, runtime_root, write_json


STAGE_NAME = "sync_market_anomaly_history"
MARKET_ANOMALY_HISTORY_SCHEMA_VERSION = 1
MARKET_ANOMALY_HISTORY_STORAGE_ARTIFACT = "data/market/anomalies"
MARKET_ANOMALY_HISTORY_SCHEMA_ARTIFACT = "data/market/metadata/market_anomaly_schema.json"
MARKET_ANOMALY_HISTORY_STATE_ARTIFACT = "data/market/metadata/market_anomaly_state.json"


def sync_market_anomaly_history(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    anomalies = _anomalies_config(config)
    if not anomalies.get("enabled"):
        _record_manifest_summary(run, _skipped_state(run, reason="market.anomalies.enabled is false.", now=now))
        return []

    raw_path = run.raw_dir / "market_anomalies.json"
    if not raw_path.exists():
        _record_manifest_summary(run, _skipped_state(run, reason=f"{MARKET_ANOMALIES_ARTIFACT} was not found.", now=now))
        return []

    raw = _read_raw_artifact(raw_path)
    storage_root = market_anomaly_storage_path(run.config_path)
    schema_path = market_anomaly_schema_path(run.config_path)
    state_path = market_anomaly_state_path(run.config_path)

    incoming_records, incoming_warnings = _history_records(raw, run, now=now)
    existing_records = _read_history_records(storage_root)
    merged_records, merge_summary = _merge_history(existing_records, incoming_records)
    raw_warnings = _raw_warning_messages(raw)
    warnings = _unique_sorted([*incoming_warnings, *raw_warnings, *merge_summary["warnings"]])
    errors = _raw_error_messages(raw)

    _rewrite_history(storage_root, merged_records)
    _write_schema(schema_path, run)
    coverage_state = _write_coverage_state(
        run,
        raw=raw,
        incoming_records=incoming_records,
        errors=errors,
        warnings=warnings,
        now=now,
    )
    base = runtime_root(run.config_path)
    state = {
        "schema_version": MARKET_ANOMALY_HISTORY_SCHEMA_VERSION,
        "artifact_type": "market_anomaly_state",
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
            "dedupe_groups": _dedupe_group_count(merged_records),
            "warning_count": len(warnings),
            "error_count": len(errors),
        },
        "groups": _group_summaries(merged_records, base),
        "ranges": _ranges(merged_records),
        "coverage_state_path": COVERAGE_STATE_ARTIFACT,
        "coverage_records": coverage_state["counts"]["records"],
        "warnings": warnings,
        "errors": errors,
        "source_artifacts": [MARKET_ANOMALIES_ARTIFACT, COVERAGE_STATE_ARTIFACT],
    }
    write_json(state_path, state)
    _record_manifest_summary(run, state)
    return [MARKET_ANOMALY_HISTORY_SCHEMA_ARTIFACT, MARKET_ANOMALY_HISTORY_STATE_ARTIFACT]


def market_anomaly_storage_path(config_path: Path) -> Path:
    return resolve_runtime_path(MARKET_ANOMALY_HISTORY_STORAGE_ARTIFACT, config_path=config_path)


def market_anomaly_schema_path(config_path: Path) -> Path:
    return resolve_runtime_path(MARKET_ANOMALY_HISTORY_SCHEMA_ARTIFACT, config_path=config_path)


def market_anomaly_state_path(config_path: Path) -> Path:
    return resolve_runtime_path(MARKET_ANOMALY_HISTORY_STATE_ARTIFACT, config_path=config_path)


def market_anomaly_group_path(
    config_path: Path,
    *,
    source_kind: str,
    data_class: str,
    symbol: str,
    timeframe: str,
) -> Path:
    return _group_path_from_storage_root(
        market_anomaly_storage_path(config_path),
        source_kind=source_kind,
        data_class=data_class,
        symbol=symbol,
        timeframe=timeframe,
    )


def read_market_anomaly_history_records(config_path: Path) -> list[dict[str, Any]]:
    return _read_history_records(market_anomaly_storage_path(config_path))


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
            warnings.append("raw market anomaly item is not a JSON object.")
            continue
        try:
            record = _history_record(item, run, seen_at=observed_at)
        except PipelineError as exc:
            warnings.append(str(exc))
            continue
        records.append(record)
    return sorted(records, key=lambda record: record["history_key"]), _unique_sorted(warnings)


def _history_record(item: dict[str, Any], run: RunContext, *, seen_at: str) -> dict[str, Any]:
    source_kind = _required_text(item, "source_kind")
    source = _required_text(item, "source")
    data_class = _required_text(item, "data_class")
    symbol = _required_text(item, "symbol")
    timeframe = _required_text(item, "timeframe")
    observed_at = _required_text(item, "observed_at")
    metric = _required_text(item, "metric")
    direction = _required_text(item, "direction")
    anomaly_id = _required_text(item, "anomaly_id")
    dedupe_key = _optional_text(item.get("dedupe_key")) or _history_key(
        data_class=data_class,
        symbol=symbol,
        timeframe=timeframe,
        observed_at=observed_at,
        metric=metric,
        direction=direction,
    )
    metrics = _mapping(item.get("metrics"))
    units = _mapping(item.get("units"))
    raw_fields = _mapping(item.get("raw_fields"))
    warnings = _string_list(item.get("warnings"))
    errors = _string_list(item.get("errors"))
    source_artifacts = _string_list(item.get("source_artifacts"))
    if not source_artifacts:
        source_artifacts = [display_path(run.raw_dir / "market_anomalies.json", base=runtime_root(run.config_path))]

    history_key = _history_key(
        data_class=data_class,
        symbol=symbol,
        timeframe=timeframe,
        observed_at=observed_at,
        metric=metric,
        direction=direction,
    )
    return {
        "history_key": history_key,
        "anomaly_id": anomaly_id,
        "dedupe_key": dedupe_key,
        "source_kind": source_kind,
        "source": source,
        "source_kinds": [source_kind],
        "sources": [source],
        "source_records": [
            {
                "source_kind": source_kind,
                "source": source,
                "anomaly_id": anomaly_id,
                "first_seen_at": _optional_text(item.get("first_seen_at")) or seen_at,
            }
        ],
        "data_class": data_class,
        "symbol": symbol,
        "market_type": _optional_text(item.get("market_type")) or "unknown",
        "timeframe": timeframe,
        "observed_at": observed_at,
        "published_at": _optional_text(item.get("published_at")),
        "collected_at": _optional_text(item.get("collected_at")) or seen_at,
        "first_seen_at": _optional_text(item.get("first_seen_at")) or seen_at,
        "last_seen_at": _optional_text(item.get("last_seen_at")) or seen_at,
        "severity": _optional_text(item.get("severity")) or "medium",
        "direction": direction,
        "metric": metric,
        "value": item.get("value"),
        "threshold": item.get("threshold"),
        "unit": _optional_text(item.get("unit")),
        "window_start": _optional_text(item.get("window_start")),
        "window_end": _optional_text(item.get("window_end")),
        "title": _optional_text(item.get("title")) or f"{symbol} {data_class}",
        "summary": _optional_text(item.get("summary")),
        "metrics": metrics,
        "units": units,
        "raw_fields": raw_fields,
        "payload_signature": _payload_signature(
            metric=metric,
            value=item.get("value"),
            threshold=item.get("threshold"),
            unit=item.get("unit"),
            severity=item.get("severity"),
            metrics=metrics,
            units=units,
        ),
        "origin_run_ids": [run.run_id],
        "first_seen_run_id": run.run_id,
        "last_seen_run_id": run.run_id,
        "status": "warning" if warnings or errors else "active",
        "warnings": warnings,
        "errors": errors,
        "source_artifacts": source_artifacts,
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
            warning = f"conflicting duplicate market anomaly record: {incoming['history_key']}"
            warnings.append(warning)
            existing["warnings"] = _unique_sorted([*_string_list(existing.get("warnings")), warning])
            existing["status"] = "warning"
        existing["source_kinds"] = _unique_sorted([*_string_list(existing.get("source_kinds")), *incoming["source_kinds"]])
        existing["sources"] = _unique_sorted([*_string_list(existing.get("sources")), *incoming["sources"]])
        existing["source_records"] = _merge_source_records(
            _list(existing.get("source_records")),
            _list(incoming.get("source_records")),
        )
        existing["origin_run_ids"] = _unique_sorted(
            [*_string_list(existing.get("origin_run_ids")), *incoming.get("origin_run_ids", [])]
        )
        existing["last_seen_run_id"] = incoming["last_seen_run_id"]
        existing["last_seen_at"] = _latest_timestamp(existing.get("last_seen_at"), incoming.get("last_seen_at"))
        existing["source_artifacts"] = _unique_sorted(
            [*_string_list(existing.get("source_artifacts")), *incoming.get("source_artifacts", [])]
        )
        existing["warnings"] = _unique_sorted([*_string_list(existing.get("warnings")), *incoming.get("warnings", [])])
        existing["errors"] = _unique_sorted([*_string_list(existing.get("errors")), *incoming.get("errors", [])])
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
        key = (
            str(record.get("source_kind") or "mixed"),
            record["data_class"],
            record["symbol"],
            record["timeframe"],
        )
        by_group.setdefault(key, []).append(record)

    for (source_kind, data_class, symbol, timeframe), group_records in sorted(by_group.items()):
        group_dir = _group_path_from_storage_root(
            storage_root,
            source_kind=source_kind,
            data_class=data_class,
            symbol=symbol,
            timeframe=timeframe,
        )
        group_dir.mkdir(parents=True, exist_ok=True)
        write_json(group_dir / "records.json", sorted(group_records, key=lambda record: record["observed_at"]))


def _write_schema(schema_path: Path, run: RunContext) -> None:
    schema = {
        "schema_version": MARKET_ANOMALY_HISTORY_SCHEMA_VERSION,
        "artifact_type": "market_anomaly_schema",
        "updated_at": _format_utc(None),
        "storage_path": display_path(
            market_anomaly_storage_path(run.config_path),
            base=runtime_root(run.config_path),
        ),
        "identity": ["data_class", "symbol", "timeframe", "observed_at", "metric", "direction"],
        "dedupe_identity": ["dedupe_key", "source_kind", "source", "anomaly_id"],
        "grouping": ["source_kind", "data_class", "symbol", "timeframe"],
        "record_fields": [
            "history_key",
            "anomaly_id",
            "dedupe_key",
            "source_kind",
            "source",
            "source_kinds",
            "sources",
            "source_records",
            "data_class",
            "symbol",
            "market_type",
            "timeframe",
            "observed_at",
            "published_at",
            "collected_at",
            "first_seen_at",
            "last_seen_at",
            "severity",
            "direction",
            "metric",
            "value",
            "threshold",
            "unit",
            "window_start",
            "window_end",
            "title",
            "summary",
            "metrics",
            "units",
            "raw_fields",
            "origin_run_ids",
            "first_seen_run_id",
            "last_seen_run_id",
            "status",
            "warnings",
            "errors",
            "source_artifacts",
        ],
    }
    write_json(schema_path, schema)


def _write_coverage_state(
    run: RunContext,
    *,
    raw: dict[str, Any],
    incoming_records: list[dict[str, Any]],
    errors: list[str],
    warnings: list[str],
    now: datetime | str | None,
) -> dict[str, Any]:
    existing_records = [
        record
        for record in read_collection_coverage_state(run.config_path).get("records", [])
        if isinstance(record, dict)
    ]
    requested_start = _optional_text(raw.get("requested_start")) or _range_start(incoming_records) or _format_utc(now)
    requested_end = _optional_text(raw.get("requested_end")) or _range_end(incoming_records) or requested_start
    status = "partial" if errors and incoming_records else "failed" if errors else "collected" if incoming_records else "no_data"
    coverage_record = {
        "data_type": "market_anomaly",
        "source": "configured",
        "identity": {},
        "range_start": requested_start,
        "range_end": requested_end,
        "status": status,
        "record_count": len(incoming_records),
        "attempt_count": 1,
        "latest_attempt_at": _format_utc(now),
        "latest_success_at": _format_utc(now) if not errors else None,
        "updated_at": _format_utc(now),
        "coverage_method": "market_anomaly_history_sync",
        "source_artifacts": [MARKET_ANOMALIES_ARTIFACT],
        "warnings": warnings,
        "errors": [{"message": message} for message in errors],
    }
    return write_collection_coverage_state(
        run.config_path,
        [*existing_records, coverage_record],
        now=now,
        source_artifacts=[COVERAGE_STATE_ARTIFACT, MARKET_ANOMALIES_ARTIFACT],
    )


def _group_summaries(records: list[dict[str, Any]], config_base: Path) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for record in records:
        key = (record["source_kind"], record["data_class"], record["symbol"], record["timeframe"])
        groups.setdefault(key, []).append(record)

    summaries = []
    for (source_kind, data_class, symbol, timeframe), group_records in sorted(groups.items()):
        group_records = sorted(group_records, key=lambda record: record["observed_at"])
        storage_ref = display_path(
            _group_path_from_storage_root(
                market_anomaly_storage_path(config_base / "config.yaml"),
                source_kind=source_kind,
                data_class=data_class,
                symbol=symbol,
                timeframe=timeframe,
            ),
            base=config_base,
        )
        summaries.append(
            {
                "source_kind": source_kind,
                "data_class": data_class,
                "symbol": symbol,
                "timeframe": timeframe,
                "record_count": len(group_records),
                "first_observed_at": group_records[0]["observed_at"],
                "last_observed_at": group_records[-1]["observed_at"],
                "storage_ref": storage_ref,
            }
        )
    return summaries


def _ranges(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranges = []
    for group in _group_summaries(records, Path(".")):
        ranges.append(
            {
                "source_kind": group["source_kind"],
                "data_class": group["data_class"],
                "symbol": group["symbol"],
                "timeframe": group["timeframe"],
                "first_observed_at": group["first_observed_at"],
                "last_observed_at": group["last_observed_at"],
                "record_count": group["record_count"],
            }
        )
    return ranges


def _record_manifest_summary(run: RunContext, state: dict[str, Any]) -> None:
    totals = state["totals"]
    if state["status"] != "skipped":
        run.manifest["artifacts"]["market_anomaly_schema"] = MARKET_ANOMALY_HISTORY_SCHEMA_ARTIFACT
        run.manifest["artifacts"]["market_anomaly_state"] = MARKET_ANOMALY_HISTORY_STATE_ARTIFACT
    run.manifest["market_anomaly_history"] = {
        "status": state["status"],
        "storage_path": state["storage_path"],
        "state_path": state["state_path"],
        "records": totals["records"],
        "incoming_records": totals["incoming_records"],
        "duplicate_records": totals["duplicate_records"],
        "conflicting_duplicates": totals["conflicting_duplicates"],
        "dedupe_groups": totals["dedupe_groups"],
        "warnings": totals["warning_count"],
        "errors": totals["error_count"],
    }
    counts = run.manifest.setdefault("counts", {})
    counts["market_anomaly_history_records"] = totals["records"]
    counts["market_anomaly_history_incoming_records"] = totals["incoming_records"]
    counts["market_anomaly_history_duplicate_records"] = totals["duplicate_records"]
    counts["market_anomaly_history_conflicting_duplicates"] = totals["conflicting_duplicates"]
    counts["market_anomaly_history_dedupe_groups"] = totals["dedupe_groups"]
    counts["market_anomaly_history_warnings"] = totals["warning_count"]
    counts["market_anomaly_history_errors"] = totals["error_count"]


def _skipped_state(run: RunContext, *, reason: str, now: datetime | str | None) -> dict[str, Any]:
    storage_path = market_anomaly_storage_path(run.config_path)
    state_path = market_anomaly_state_path(run.config_path)
    return {
        "schema_version": MARKET_ANOMALY_HISTORY_SCHEMA_VERSION,
        "artifact_type": "market_anomaly_state",
        "updated_at": _format_utc(now),
        "status": "skipped",
        "storage_path": display_path(storage_path, base=runtime_root(run.config_path)),
        "schema_path": display_path(
            market_anomaly_schema_path(run.config_path),
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
            "dedupe_groups": 0,
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
            f"{MARKET_ANOMALIES_ARTIFACT} is not valid JSON: {exc.msg}.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc
    if not isinstance(raw, dict):
        raise PipelineError(f"{MARKET_ANOMALIES_ARTIFACT} must be a JSON object.", stage=STAGE_NAME, exit_code=3)
    return raw


def _raw_warning_messages(raw: dict[str, Any]) -> list[str]:
    warnings = _string_list(raw.get("warnings"))
    for item in _list(raw.get("availability")):
        if isinstance(item, dict) and item.get("status") in {"unavailable", "failed", "partial"}:
            reason = item.get("reason") or item.get("status")
            warnings.append(
                "market anomaly source availability "
                f"{item.get('source_kind') or 'unknown'} {item.get('source') or ''}: {reason}".strip()
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
    if errors or warnings:
        return "warning"
    if record_count == 0:
        return "skipped"
    return "ok"


def _history_key(
    *,
    data_class: str,
    symbol: str,
    timeframe: str,
    observed_at: str,
    metric: str,
    direction: str,
) -> str:
    return f"{data_class}|{symbol}|{timeframe}|{observed_at}|{metric}|{direction}"


def _payload_signature(
    *,
    metric: str,
    value: Any,
    threshold: Any,
    unit: Any,
    severity: Any,
    metrics: dict[str, Any],
    units: dict[str, Any],
) -> str:
    return json.dumps(
        {
            "metric": metric,
            "value": value,
            "threshold": threshold,
            "unit": unit,
            "severity": severity,
            "metrics": metrics,
            "units": units,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _normalize_existing(record: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    normalized["source_kinds"] = _string_list(record.get("source_kinds"))
    normalized["sources"] = _string_list(record.get("sources"))
    normalized["source_records"] = _list(record.get("source_records"))
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
            metric=str(record.get("metric") or ""),
            value=record.get("value"),
            threshold=record.get("threshold"),
            unit=record.get("unit"),
            severity=record.get("severity"),
            metrics=normalized["metrics"],
            units=normalized["units"],
        )
    )
    return normalized


def _record_sort_key(record: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
    return (
        str(record.get("data_class") or ""),
        str(record.get("symbol") or ""),
        str(record.get("timeframe") or ""),
        str(record.get("observed_at") or ""),
        str(record.get("metric") or ""),
        str(record.get("history_key") or ""),
    )


def _anomalies_config(config: dict[str, Any]) -> dict[str, Any]:
    market = config.get("market")
    if not isinstance(market, dict):
        return {}
    anomalies = market.get("anomalies")
    return anomalies if isinstance(anomalies, dict) else {}


def _required_text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PipelineError(f"market anomaly record missing {key}.", stage=STAGE_NAME, exit_code=3)
    return value.strip()


def _optional_text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


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


def _merge_source_records(left: list[Any], right: list[Any]) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in [*left, *right]:
        if not isinstance(item, dict):
            continue
        key = (
            str(item.get("source_kind") or ""),
            str(item.get("source") or ""),
            str(item.get("anomaly_id") or ""),
        )
        if key == ("", "", ""):
            continue
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = dict(item)
            continue
        existing["first_seen_at"] = min(
            str(existing.get("first_seen_at") or ""),
            str(item.get("first_seen_at") or ""),
        )
    return [by_key[key] for key in sorted(by_key)]


def _dedupe_group_count(records: list[dict[str, Any]]) -> int:
    return len({str(record.get("dedupe_key") or record.get("history_key") or "") for record in records})


def _range_start(records: list[dict[str, Any]]) -> str | None:
    values = [str(record.get("observed_at") or "") for record in records if record.get("observed_at")]
    return min(values) if values else None


def _range_end(records: list[dict[str, Any]]) -> str | None:
    values = [str(record.get("observed_at") or "") for record in records if record.get("observed_at")]
    return max(values) if values else None


def _partition_value(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in value)


def _group_path_from_storage_root(
    storage_root: Path,
    *,
    source_kind: str,
    data_class: str,
    symbol: str,
    timeframe: str,
) -> Path:
    return (
        storage_root
        / f"source_kind={_partition_value(source_kind)}"
        / f"data_class={_partition_value(data_class)}"
        / f"symbol={_partition_value(symbol)}"
        / f"timeframe={_partition_value(timeframe)}"
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
