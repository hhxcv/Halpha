from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from halpha.collectors.text import collect_text_events_raw
from halpha.data.collection_coverage import (
    COVERAGE_STATE_ARTIFACT,
    read_collection_coverage_state,
    write_collection_coverage_state,
)
from halpha.data.collection_planner import plan_collection_from_coverage
from halpha.data.raw_artifacts import RawArtifactError, validate_text_events_raw_artifact
from halpha.data.research_data_catalog import CATALOG_ARTIFACT, write_research_data_catalog_snapshot
from halpha.runtime.public_http import market_proxy_url_from_config
from halpha.text.text_event_history import (
    TEXT_EVENT_HISTORY_STATE_ARTIFACT,
    write_text_event_history_records,
)
from halpha.text.text_event_records import normalize_text_event_records


TEXT_EVENT_COLLECTION_SCHEMA_VERSION = 1
TEXT_EVENT_COLLECTION_RECORDS_REF = TEXT_EVENT_HISTORY_STATE_ARTIFACT


class TextEventCollectionError(Exception):
    def __init__(self, message: str, *, exit_code: int = 3) -> None:
        super().__init__(message)
        self.exit_code = exit_code


TextRawCollector = Callable[[dict[str, Any], str | None], dict[str, Any]]


def collect_text_event_data(
    config: dict[str, Any],
    *,
    config_path: Path,
    source: str,
    requested_start: str,
    requested_end: str,
    dry_run: bool = True,
    raw_collector: TextRawCollector | None = None,
    now: datetime | str | None = None,
    supports_historical: bool = True,
    max_exact_windows: int = 3,
    merge_gap_threshold_seconds: int = 0,
    min_fetch_window_seconds: int = 0,
) -> dict[str, Any]:
    start = _format_utc(requested_start)
    end = _format_utc(requested_end)
    if _parse_utc(end) <= _parse_utc(start):
        raise TextEventCollectionError("requested_end must be greater than requested_start.", exit_code=2)

    text = _text_config(config)
    selected_sources = _selected_sources(text, source)
    source_key, identity = _coverage_identity(source, selected_sources)
    coverage_state = read_collection_coverage_state(config_path)
    plan = plan_collection_from_coverage(
        coverage_state,
        data_type="text_event",
        source=source_key,
        identity=identity,
        requested_start=start,
        requested_end=end,
        supports_historical=supports_historical,
        now=now,
        max_exact_windows=max_exact_windows,
        merge_gap_threshold_seconds=merge_gap_threshold_seconds,
        min_fetch_window_seconds=min_fetch_window_seconds,
    )
    result = _base_result(
        mode="dry_run" if dry_run else "apply",
        source=source_key,
        identity=identity,
        requested_start=start,
        requested_end=end,
        plan=plan,
    )
    if dry_run:
        return result

    existing_coverage = _existing_coverage_records(coverage_state)
    if plan["strategy"] == "no_work":
        result["artifacts"].update(_write_catalog_snapshot(config, config_path=config_path, manifest={}, now=now))
        return result
    if plan["strategy"] == "blocked":
        coverage_updates = _blocked_coverage_records(
            source=source_key,
            identity=identity,
            requested_start=start,
            requested_end=end,
            plan=plan,
            now=now,
        )
        state = _write_coverage_and_catalog(
            config,
            config_path=config_path,
            existing_coverage=existing_coverage,
            coverage_updates=coverage_updates,
            result=result,
            manifest={},
            now=now,
        )
        result["status"] = "blocked"
        result["coverage_updates"] = coverage_updates
        result["counts"]["coverage_state_records"] = state["counts"]["records"]
        result["errors"].extend(plan.get("errors") or [])
        return result

    manifest: dict[str, Any] = {"artifacts": {}, "counts": {}}
    planned_windows = [window for window in plan.get("planned_fetch_windows", []) if isinstance(window, dict)]
    all_records: list[dict[str, Any]] = []
    coverage_updates: list[dict[str, Any]] = []
    collector = raw_collector or _default_raw_collector(config)
    text_for_source = {**text, "sources": selected_sources}

    for window in planned_windows:
        item = _collect_window(
            text_for_source,
            source=source_key,
            identity=identity,
            window=window,
            collector=collector,
            now=now,
        )
        result["fetches"].append(item)
        coverage_updates.append(_coverage_record_from_item(item, now=now))
        all_records.extend(item["records"])
        result["counts"]["raw_items"] += item["raw_item_count"]
        result["counts"]["raw_errors"] += item["raw_error_count"]
        result["counts"]["window_records"] += item["record_count"]
        result["counts"]["stored_records"] += item["record_count"]
        result["warnings"].extend(item["warnings"])
        result["errors"].extend(item["errors"])

    history_artifacts = write_text_event_history_records(
        config,
        config_path=config_path,
        run_id=f"text_event_data_collect:{_format_utc(now)}",
        records=all_records,
        records_artifact_ref=TEXT_EVENT_COLLECTION_RECORDS_REF,
        source_artifact_base=None,
        manifest=manifest,
        now=now,
    )
    for artifact in history_artifacts:
        result["artifacts"]["text_event_history_state"] = artifact

    state = _write_coverage_and_catalog(
        config,
        config_path=config_path,
        existing_coverage=existing_coverage,
        coverage_updates=coverage_updates,
        result=result,
        manifest=manifest,
        now=now,
    )
    result["coverage_updates"] = coverage_updates
    result["counts"]["coverage_state_records"] = state["counts"]["records"]
    _finalize_status(result)
    return result


def _collect_window(
    text: dict[str, Any],
    *,
    source: str,
    identity: dict[str, str],
    window: dict[str, Any],
    collector: TextRawCollector,
    now: datetime | str | None,
) -> dict[str, Any]:
    start = _format_utc(str(window["range_start"]))
    end = _format_utc(str(window["range_end"]))
    errors: list[dict[str, Any]] = []
    warnings: list[str] = []
    records: list[dict[str, Any]] = []
    raw_item_count = 0

    try:
        raw = collector(text, _format_utc(now) if now is not None else None)
        validate_text_events_raw_artifact(raw, "text_event_data_collect")
        raw = _filter_raw_window(raw, start=start, end=end)
        raw_item_count = len(raw["items"])
        records, record_warnings = normalize_text_event_records(
            raw,
            source_artifact_ref=TEXT_EVENT_COLLECTION_RECORDS_REF,
        )
        warnings.extend(record_warnings)
        errors.extend(_error_items(raw.get("errors")))
    except (TextEventCollectionError, RawArtifactError, ValueError) as exc:
        errors.append({"message": str(exc)})

    status = _window_status(record_count=len(records), errors=errors)
    if status == "partial":
        warnings.append(f"text-event collection window {start}..{end} recorded partial source failures.")
    return {
        "status": status,
        "source": source,
        "identity": identity,
        "range_start": start,
        "range_end": end,
        "raw_item_count": raw_item_count,
        "raw_error_count": len(errors),
        "record_count": len(records),
        "records": records,
        "warnings": _unique_sorted(warnings),
        "errors": errors,
    }


def _filter_raw_window(raw: dict[str, Any], *, start: str, end: str) -> dict[str, Any]:
    start_dt = _parse_utc(start)
    end_dt = _parse_utc(end)
    raw_collected_at = _optional_utc(raw.get("collected_at"))
    items = []
    for item in raw.get("items", []):
        if not isinstance(item, dict):
            continue
        timestamp = _item_timestamp(item, raw_collected_at=raw_collected_at)
        if timestamp is None or start_dt <= timestamp < end_dt:
            items.append(item)
    return {**raw, "items": items}


def _item_timestamp(item: dict[str, Any], *, raw_collected_at: datetime | None) -> datetime | None:
    published_at = _optional_utc(item.get("published_at"))
    if published_at is not None:
        return published_at
    return raw_collected_at


def _base_result(
    *,
    mode: str,
    source: str,
    identity: dict[str, str],
    requested_start: str,
    requested_end: str,
    plan: dict[str, Any],
) -> dict[str, Any]:
    planned_windows = [window for window in plan.get("planned_fetch_windows", []) if isinstance(window, dict)]
    return {
        "schema_version": TEXT_EVENT_COLLECTION_SCHEMA_VERSION,
        "artifact_type": "text_event_collection_result",
        "mode": mode,
        "status": str(plan.get("status") or "ok"),
        "data_type": "text_event",
        "source": source,
        "symbol": None,
        "timeframe": None,
        "identity": identity,
        "requested_start": requested_start,
        "requested_end": requested_end,
        "plan": plan,
        "fetches": [],
        "coverage_updates": [],
        "counts": {
            "planned_fetch_windows": len(planned_windows),
            "skipped_ranges": len(plan.get("skipped_ranges") or []),
            "gap_ranges": len(plan.get("gap_ranges") or []),
            "retry_ranges": len(plan.get("retry_ranges") or []),
            "raw_items": 0,
            "raw_errors": 0,
            "window_records": 0,
            "stored_records": 0,
            "coverage_records_written": 0,
            "coverage_state_records": 0,
        },
        "artifacts": {},
        "warnings": list(plan.get("warnings") or []),
        "errors": list(plan.get("errors") or []),
    }


def _write_coverage_and_catalog(
    config: dict[str, Any],
    *,
    config_path: Path,
    existing_coverage: list[dict[str, Any]],
    coverage_updates: list[dict[str, Any]],
    result: dict[str, Any],
    manifest: dict[str, Any],
    now: datetime | str | None,
) -> dict[str, Any]:
    state = write_collection_coverage_state(
        config_path,
        [*existing_coverage, *coverage_updates],
        now=now,
        source_artifacts=[TEXT_EVENT_HISTORY_STATE_ARTIFACT],
    )
    result["counts"]["coverage_records_written"] = len(coverage_updates)
    result["artifacts"]["collection_coverage"] = COVERAGE_STATE_ARTIFACT
    result["artifacts"].update(_write_catalog_snapshot(config, config_path=config_path, manifest=manifest, now=now))
    return state


def _write_catalog_snapshot(
    config: dict[str, Any],
    *,
    config_path: Path,
    manifest: dict[str, Any],
    now: datetime | str | None,
) -> dict[str, str]:
    write_research_data_catalog_snapshot(config, config_path=config_path, manifest=manifest, now=now)
    return {"research_data_catalog": CATALOG_ARTIFACT}


def _coverage_record_from_item(item: dict[str, Any], *, now: datetime | str | None) -> dict[str, Any]:
    timestamp = _format_utc(now)
    status = str(item["status"])
    return {
        "data_type": "text_event",
        "source": item["source"],
        "identity": item["identity"],
        "range_start": item["range_start"],
        "range_end": item["range_end"],
        "status": status,
        "record_count": int(item.get("record_count") or 0),
        "attempt_count": 1,
        "latest_attempt_at": timestamp,
        "latest_success_at": timestamp if status in {"collected", "no_data", "partial"} else None,
        "updated_at": timestamp,
        "coverage_method": "text_event_data_collect",
        "source_artifacts": [TEXT_EVENT_HISTORY_STATE_ARTIFACT],
        "warnings": item["warnings"],
        "errors": item["errors"],
    }


def _blocked_coverage_records(
    *,
    source: str,
    identity: dict[str, str],
    requested_start: str,
    requested_end: str,
    plan: dict[str, Any],
    now: datetime | str | None,
) -> list[dict[str, Any]]:
    timestamp = _format_utc(now)
    return [
        {
            "data_type": "text_event",
            "source": source,
            "identity": identity,
            "range_start": requested_start,
            "range_end": requested_end,
            "status": "not_collected",
            "record_count": 0,
            "attempt_count": 1,
            "latest_attempt_at": timestamp,
            "latest_success_at": None,
            "updated_at": timestamp,
            "coverage_method": "text_event_data_collect",
            "source_artifacts": [COVERAGE_STATE_ARTIFACT],
            "warnings": list(plan.get("warnings") or []),
            "errors": [error for error in plan.get("errors", []) if isinstance(error, dict)],
        }
    ]


def _finalize_status(result: dict[str, Any]) -> None:
    if result["status"] == "blocked":
        return
    fetches = [fetch for fetch in result.get("fetches", []) if isinstance(fetch, dict)]
    failed = [fetch for fetch in fetches if fetch.get("status") == "failed"]
    partial = [fetch for fetch in fetches if fetch.get("status") == "partial"]
    stored_records = int(result.get("counts", {}).get("stored_records") or 0)
    if failed and stored_records == 0:
        result["status"] = "failed"
    elif failed or partial or result["warnings"] or result["errors"]:
        result["status"] = "warning"
    else:
        result["status"] = "ok"


def _window_status(*, record_count: int, errors: list[dict[str, Any]]) -> str:
    if errors and record_count > 0:
        return "partial"
    if errors:
        return "failed"
    if record_count == 0:
        return "no_data"
    return "collected"


def _default_raw_collector(config: dict[str, Any]) -> TextRawCollector:
    proxy_url = market_proxy_url_from_config(config, error_factory=TextEventCollectionError)

    def _collect(text: dict[str, Any], now: str | None) -> dict[str, Any]:
        return collect_text_events_raw(text, proxy_url=proxy_url)

    return _collect


def _text_config(config: dict[str, Any]) -> dict[str, Any]:
    text = config.get("text") if isinstance(config.get("text"), dict) else {}
    if text.get("enabled") is not True:
        raise TextEventCollectionError("text.enabled must be true for text-event collection.", exit_code=2)
    sources = text.get("sources")
    if not isinstance(sources, list) or not sources:
        raise TextEventCollectionError("text.sources must be configured for text-event collection.", exit_code=2)
    return text


def _selected_sources(text: dict[str, Any], source: str) -> list[dict[str, Any]]:
    source_name = str(source or "").strip()
    if not source_name:
        raise TextEventCollectionError("source must be a configured text source name or all.", exit_code=2)
    sources = [item for item in text.get("sources", []) if isinstance(item, dict)]
    if source_name == "all":
        return sources
    selected = [item for item in sources if str(item.get("name") or "") == source_name]
    if not selected:
        raise TextEventCollectionError(f"requested text source is not configured: {source_name}", exit_code=2)
    return selected


def _coverage_identity(source: str, selected_sources: list[dict[str, Any]]) -> tuple[str, dict[str, str]]:
    source_name = str(source).strip()
    if source_name == "all":
        return "all", {"source_group": "all"}
    return source_name, {"source_name": source_name}


def _existing_coverage_records(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [record for record in state.get("records", []) if isinstance(record, dict)]


def _error_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _unique_sorted(values: list[str]) -> list[str]:
    return sorted(set(values))


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise TextEventCollectionError("collection timestamps must include a UTC offset.", exit_code=2)
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str):
        timestamp = _parse_utc(value)
    else:
        raise TextEventCollectionError("collection timestamps must be datetimes or ISO 8601 strings.", exit_code=2)
    return timestamp.isoformat().replace("+00:00", "Z")


def _optional_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return _parse_utc(value)
    except TextEventCollectionError:
        return None


def _parse_utc(value: str) -> datetime:
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TextEventCollectionError(f"collection timestamp is not valid ISO 8601: {value}", exit_code=2) from exc
    if timestamp.tzinfo is None:
        raise TextEventCollectionError("collection timestamps must include a UTC offset.", exit_code=2)
    return timestamp.astimezone(timezone.utc).replace(microsecond=0)
