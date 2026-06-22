from __future__ import annotations

import json
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from .data_quality_post_artifacts import (
    POST_DATA_QUALITY_CHECK_NAMES,
    post_data_quality_artifact_checks,
)
from .pipeline import RunContext
from .raw_artifacts import (
    RawArtifactError,
    validate_derivatives_market_raw_artifact,
    validate_macro_calendar_raw_artifact,
    validate_market_raw_artifact,
    validate_onchain_flow_raw_artifact,
    validate_text_events_raw_artifact,
)
from .storage import write_json


STAGE_NAME = "build_data_quality_summary"
DATA_QUALITY_SUMMARY_ARTIFACT = "analysis/data_quality_summary.json"
DATA_QUALITY_SCHEMA_VERSION = 1


def build_data_quality_summary(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    created_at = _format_utc(now)
    checks = _data_quality_checks(config, run, now=created_at, m13_expected=False)
    _write_data_quality_summary(run, created_at=created_at, checks=checks)
    return [DATA_QUALITY_SUMMARY_ARTIFACT]


def refresh_m13_data_quality_checks(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    """Refresh final-stage analysis artifact checks after downstream artifacts exist."""
    created_at = _format_utc(now)
    existing, error = _read_json(run.analysis_dir / "data_quality_summary.json")
    if error:
        checks = _data_quality_checks(config, run, now=created_at, m13_expected=True)
    else:
        checks = [
            check
            for check in _list(existing.get("checks"))
            if isinstance(check, dict) and check.get("name") not in POST_DATA_QUALITY_CHECK_NAMES
        ]
        checks.extend(post_data_quality_artifact_checks(run, expected=True))
    _write_data_quality_summary(run, created_at=created_at, checks=checks)
    return [DATA_QUALITY_SUMMARY_ARTIFACT]


def _data_quality_checks(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: str,
    m13_expected: bool,
) -> list[dict[str, Any]]:
    checks = [
        _raw_market_check(config, run, now=now),
        _raw_derivatives_check(config, run, now=now),
        _raw_macro_calendar_check(config, run, now=now),
        _raw_onchain_flow_check(config, run, now=now),
        _raw_text_check(config, run, now=now),
        _ohlcv_store_check(config, run),
        _derivatives_history_check(config, run),
        _derivatives_views_check(config, run, now=now),
        _macro_calendar_history_check(config, run),
        _macro_calendar_views_check(config, run, now=now),
        _macro_calendar_context_check(config, run),
        _macro_calendar_material_check(config, run),
        _onchain_flow_history_check(config, run),
        _onchain_flow_views_check(config, run, now=now),
        _onchain_flow_context_check(config, run),
        _onchain_flow_material_check(config, run),
        _text_event_records_check(config, run, now=now),
        _text_event_history_check(run),
        _research_data_catalog_check(run),
        _run_index_check(run),
        _partial_collection_check(run),
        *post_data_quality_artifact_checks(run, expected=m13_expected),
    ]
    return checks


def _write_data_quality_summary(
    run: RunContext,
    *,
    created_at: str,
    checks: list[dict[str, Any]],
) -> None:
    warnings = _unique_sorted(
        [
            str(warning)
            for check in checks
            for warning in check["details"].get("warnings", [])
            if isinstance(warning, str)
        ]
    )
    errors = [
        {"check": check["name"], "message": str(error)}
        for check in checks
        for error in check["details"].get("errors", [])
        if isinstance(error, str)
    ]
    summary = {
        "schema_version": DATA_QUALITY_SCHEMA_VERSION,
        "artifact_type": "data_quality_summary",
        "run_id": run.run_id,
        "created_at": created_at,
        "status": _overall_status(checks),
        "checks": checks,
        "counts": {
            "checks": len(checks),
            "ok": _count_status(checks, "ok"),
            "warning": _count_status(checks, "warning"),
            "degraded": _count_status(checks, "degraded"),
            "skipped": _count_status(checks, "skipped"),
            "failed": _count_status(checks, "failed"),
            "warnings": len(warnings),
            "errors": len(errors),
        },
        "warnings": warnings,
        "errors": errors,
        "source_artifacts": _source_artifacts(checks),
    }
    write_json(run.analysis_dir / "data_quality_summary.json", summary)
    run.manifest["artifacts"]["data_quality_summary"] = DATA_QUALITY_SUMMARY_ARTIFACT
    run.manifest["data_quality_summary"] = {
        "status": summary["status"],
        "artifact": DATA_QUALITY_SUMMARY_ARTIFACT,
        "checks": summary["counts"]["checks"],
        "warnings": summary["counts"]["warnings"],
        "errors": summary["counts"]["errors"],
        "degraded": summary["counts"]["degraded"],
        "failed": summary["counts"]["failed"],
    }
    run.manifest["counts"]["data_quality_checks"] = summary["counts"]["checks"]
    run.manifest["counts"]["data_quality_warnings"] = summary["counts"]["warnings"]
    run.manifest["counts"]["data_quality_errors"] = summary["counts"]["errors"]
    run.manifest["counts"]["data_quality_degraded_checks"] = summary["counts"]["degraded"]
    run.manifest["counts"]["data_quality_failed_checks"] = summary["counts"]["failed"]


def _raw_market_check(config: dict[str, Any], run: RunContext, *, now: str) -> dict[str, Any]:
    market = config.get("market", {})
    if not market.get("enabled"):
        return _check("raw_market", "raw", "skipped", "market.enabled is false.", [])
    artifact = "raw/market.json"
    raw, error = _read_json(run.raw_dir / "market.json")
    if error:
        return _check("raw_market", "raw", "failed", error, [artifact], errors=[error])
    try:
        validate_market_raw_artifact(raw, artifact)
    except RawArtifactError as exc:
        return _check("raw_market", "raw", "failed", str(exc), [artifact], errors=[str(exc)])
    errors = _error_messages(raw.get("errors"))
    timestamp_warnings = _timestamp_warnings(_market_timestamps(raw), now=now)
    status = "degraded" if errors else "warning" if timestamp_warnings else "ok"
    return _check(
        "raw_market",
        "raw",
        status,
        f"{len(raw.get('items', []))} market item(s), {len(errors)} collection error(s).",
        [artifact],
        warnings=timestamp_warnings,
        errors=errors,
        details={"items": len(raw.get("items", []))},
    )


def _raw_text_check(config: dict[str, Any], run: RunContext, *, now: str) -> dict[str, Any]:
    text = config.get("text", {})
    if not text.get("enabled"):
        return _check("raw_text", "raw", "skipped", "text.enabled is false.", [])
    artifact = "raw/text_events.json"
    raw, error = _read_json(run.raw_dir / "text_events.json")
    if error:
        return _check("raw_text", "raw", "failed", error, [artifact], errors=[error])
    try:
        validate_text_events_raw_artifact(raw, artifact)
    except RawArtifactError as exc:
        return _check("raw_text", "raw", "failed", str(exc), [artifact], errors=[str(exc)])
    errors = _error_messages(raw.get("errors"))
    timestamp_warnings = _timestamp_warnings(_text_raw_timestamps(raw), now=now)
    status = "degraded" if errors else "warning" if timestamp_warnings else "ok"
    return _check(
        "raw_text",
        "raw",
        status,
        f"{len(raw.get('items', []))} text item(s), {len(errors)} collection error(s).",
        [artifact],
        warnings=timestamp_warnings,
        errors=errors,
        details={"items": len(raw.get("items", []))},
    )


def _raw_derivatives_check(config: dict[str, Any], run: RunContext, *, now: str) -> dict[str, Any]:
    derivatives = _derivatives_config(config)
    if not derivatives.get("enabled"):
        return _check("raw_derivatives_market", "raw", "skipped", "market.derivatives.enabled is false.", [])
    artifact = "raw/derivatives_market.json"
    raw, error = _read_json(run.raw_dir / "derivatives_market.json")
    if error:
        return _check("raw_derivatives_market", "raw", "failed", error, [artifact], errors=[error])
    try:
        validate_derivatives_market_raw_artifact(raw, artifact)
    except RawArtifactError as exc:
        return _check("raw_derivatives_market", "raw", "failed", str(exc), [artifact], errors=[str(exc)])

    errors = _error_messages(raw.get("errors"))
    timestamp_warnings = _timestamp_warnings(_derivatives_timestamps(raw), now=now)
    stale_warnings = _stale_timestamp_warnings(_derivatives_timestamps(raw), now=now, max_age_hours=48)
    value_warnings = _derivatives_missing_value_warnings(raw)
    availability_warnings = _derivatives_availability_warnings(raw)
    warnings = _unique_sorted([*timestamp_warnings, *stale_warnings, *value_warnings, *availability_warnings])
    status = "degraded" if errors else "warning" if warnings else "ok"
    return _check(
        "raw_derivatives_market",
        "raw",
        status,
        f"{len(raw.get('items', []))} derivatives item(s), {len(errors)} collection error(s).",
        [artifact],
        warnings=warnings,
        errors=errors,
        details={
            "items": len(raw.get("items", [])),
            "availability_records": len(_list(raw.get("availability"))),
            "unavailable_records": sum(
                1 for item in _list(raw.get("availability")) if isinstance(item, dict) and item.get("status") == "unavailable"
            ),
            "partial_records": sum(
                1 for item in _list(raw.get("availability")) if isinstance(item, dict) and item.get("status") == "partial"
            ),
            "failed_records": sum(
                1 for item in _list(raw.get("availability")) if isinstance(item, dict) and item.get("status") == "failed"
            ),
            "stale_records": sum(
                1 for item in _list(raw.get("availability")) if isinstance(item, dict) and item.get("status") == "stale"
            ),
            "degraded_records": sum(
                1 for item in _list(raw.get("availability")) if isinstance(item, dict) and item.get("status") == "degraded"
            ),
        },
    )


def _raw_macro_calendar_check(config: dict[str, Any], run: RunContext, *, now: str) -> dict[str, Any]:
    macro_calendar = _macro_calendar_config(config)
    if not macro_calendar.get("enabled"):
        return _check("raw_macro_calendar", "raw", "skipped", "macro_calendar.enabled is false.", [])
    artifact = "raw/macro_calendar.json"
    raw, error = _read_json(run.raw_dir / "macro_calendar.json")
    if error:
        return _check("raw_macro_calendar", "raw", "failed", error, [artifact], errors=[error])
    try:
        validate_macro_calendar_raw_artifact(raw, artifact)
    except RawArtifactError as exc:
        return _check("raw_macro_calendar", "raw", "failed", str(exc), [artifact], errors=[str(exc)])

    errors = _error_messages(raw.get("errors"))
    timestamps = _macro_calendar_timestamps(raw)
    timestamp_warnings = _timestamp_warnings(timestamps, now=now)
    stale_warnings = _stale_timestamp_warnings(timestamps, now=now, max_age_hours=48)
    availability_warnings = _macro_calendar_availability_warnings(raw)
    item_warnings = _macro_calendar_item_warnings(raw)
    warnings = _unique_sorted(
        [
            *_string_list(raw.get("warnings")),
            *timestamp_warnings,
            *stale_warnings,
            *availability_warnings,
            *item_warnings,
        ]
    )
    availability = _list(raw.get("availability"))
    status = "degraded" if errors else "warning" if warnings else "ok"
    return _check(
        "raw_macro_calendar",
        "raw",
        status,
        f"{len(raw.get('items', []))} macro calendar item(s), {len(errors)} collection error(s).",
        [artifact],
        warnings=warnings,
        errors=errors,
        details={
            "items": len(raw.get("items", [])),
            "availability_records": len(availability),
            "no_event_records": _availability_status_count(availability, "no_event"),
            "unavailable_records": _availability_status_count(availability, "unavailable"),
            "partial_records": _availability_status_count(availability, "partial"),
            "failed_records": _availability_status_count(availability, "failed"),
            "stale_records": _availability_status_count(availability, "stale"),
            "degraded_records": _availability_status_count(availability, "degraded"),
        },
    )


def _raw_onchain_flow_check(config: dict[str, Any], run: RunContext, *, now: str) -> dict[str, Any]:
    onchain_flow = _onchain_flow_config(config)
    if not onchain_flow.get("enabled"):
        return _check("raw_onchain_flow", "raw", "skipped", "onchain_flow.enabled is false.", [])
    artifact = "raw/onchain_flow.json"
    raw, error = _read_json(run.raw_dir / "onchain_flow.json")
    if error:
        return _check("raw_onchain_flow", "raw", "failed", error, [artifact], errors=[error])
    try:
        validate_onchain_flow_raw_artifact(raw, artifact)
    except RawArtifactError as exc:
        return _check("raw_onchain_flow", "raw", "failed", str(exc), [artifact], errors=[str(exc)])

    errors = _error_messages(raw.get("errors"))
    timestamps = _onchain_flow_timestamps(raw)
    timestamp_warnings = _timestamp_warnings(timestamps, now=now)
    stale_warnings = _stale_timestamp_warnings(timestamps, now=now, max_age_hours=72)
    value_warnings = _onchain_flow_missing_value_warnings(raw)
    availability_warnings = _onchain_flow_availability_warnings(raw)
    item_warnings = _onchain_flow_item_warnings(raw)
    warnings = _unique_sorted(
        [
            *_string_list(raw.get("warnings")),
            *timestamp_warnings,
            *stale_warnings,
            *value_warnings,
            *availability_warnings,
            *item_warnings,
        ]
    )
    availability = _list(raw.get("availability"))
    status = "degraded" if errors else "warning" if warnings else "ok"
    return _check(
        "raw_onchain_flow",
        "raw",
        status,
        f"{len(raw.get('items', []))} on-chain flow item(s), {len(errors)} collection error(s).",
        [artifact],
        warnings=warnings,
        errors=errors,
        details={
            "items": len(raw.get("items", [])),
            "availability_records": len(availability),
            "unavailable_records": _availability_status_count(availability, "unavailable"),
            "partial_records": _availability_status_count(availability, "partial"),
            "failed_records": _availability_status_count(availability, "failed"),
            "stale_records": _availability_status_count(availability, "stale"),
            "degraded_records": _availability_status_count(availability, "degraded"),
            "insufficient_data_records": _availability_status_count(availability, "insufficient_data"),
        },
    )


def _ohlcv_store_check(config: dict[str, Any], run: RunContext) -> dict[str, Any]:
    market = config.get("market", {})
    if not isinstance(market.get("ohlcv"), dict):
        return _check("ohlcv_store", "shared_data", "skipped", "market.ohlcv is not configured.", [])
    artifacts = [
        "data/market/metadata/ohlcv_schema.json",
        "data/market/metadata/ohlcv_sync_state.json",
        "raw/market_data_views.json",
    ]
    sync = run.manifest.get("ohlcv_sync") if isinstance(run.manifest.get("ohlcv_sync"), dict) else {}
    errors = _error_messages(sync.get("errors"))
    warnings = _string_list(sync.get("warnings"))
    insufficient_views = _int(run.manifest.get("counts", {}).get("market_data_views_insufficient_data"))
    if insufficient_views:
        warnings.append(f"{insufficient_views} market data view(s) have insufficient OHLCV history.")
    status = "failed" if errors else "warning" if warnings else "ok"
    return _check(
        "ohlcv_store",
        "shared_data",
        status,
        f"ohlcv_sync status: {sync.get('status') or 'unknown'}.",
        artifacts,
        warnings=warnings,
        errors=errors,
        details={"insufficient_views": insufficient_views},
    )


def _derivatives_history_check(config: dict[str, Any], run: RunContext) -> dict[str, Any]:
    derivatives = _derivatives_config(config)
    if not derivatives.get("enabled"):
        return _check("derivatives_market_history", "shared_data", "skipped", "market.derivatives.enabled is false.", [])
    artifact = "data/market/metadata/derivatives_market_state.json"
    summary = run.manifest.get("derivatives_market_history")
    if not isinstance(summary, dict):
        return _check("derivatives_market_history", "shared_data", "skipped", "derivatives market history was not produced.", [])
    state, error = _read_json(run.config_path.parent / artifact)
    if error:
        return _check("derivatives_market_history", "shared_data", "failed", error, [artifact], errors=[error])
    warnings = _string_list(state.get("warnings"))
    errors = _error_messages(state.get("errors"))
    totals_value = state.get("totals")
    totals = dict(totals_value) if isinstance(totals_value, dict) else {}
    status = _derivatives_history_status(str(state.get("status") or summary.get("status")), warnings, errors)
    return _check(
        "derivatives_market_history",
        "shared_data",
        status,
        f"derivatives market history status: {state.get('status') or 'unknown'}.",
        [artifact, "data/market/metadata/derivatives_market_schema.json"],
        warnings=warnings,
        errors=errors,
        details=totals,
    )


def _macro_calendar_history_check(config: dict[str, Any], run: RunContext) -> dict[str, Any]:
    macro_calendar = _macro_calendar_config(config)
    if not macro_calendar.get("enabled"):
        return _check("macro_calendar_history", "shared_data", "skipped", "macro_calendar.enabled is false.", [])
    artifact = "data/macro/metadata/macro_calendar_state.json"
    summary = run.manifest.get("macro_calendar_history")
    if not isinstance(summary, dict):
        return _check("macro_calendar_history", "shared_data", "skipped", "macro calendar history was not produced.", [])
    state, error = _read_json(run.config_path.parent / artifact)
    if error:
        return _check("macro_calendar_history", "shared_data", "failed", error, [artifact], errors=[error])
    warnings = _string_list(state.get("warnings"))
    errors = _error_messages(state.get("errors"))
    totals_value = state.get("totals")
    totals = dict(totals_value) if isinstance(totals_value, dict) else {}
    availability = _list(state.get("availability"))
    status = _status_from_summary(str(state.get("status") or summary.get("status")), warnings, errors)
    return _check(
        "macro_calendar_history",
        "shared_data",
        status,
        f"macro calendar history status: {state.get('status') or 'unknown'}.",
        [
            artifact,
            "data/macro/metadata/macro_calendar_schema.json",
        ],
        warnings=warnings,
        errors=errors,
        details={
            **totals,
            "groups": len(_list(state.get("groups"))),
            "availability_records": len(availability),
            "no_event_records": _availability_status_count(availability, "no_event"),
            "unavailable_records": _availability_status_count(availability, "unavailable"),
            "partial_records": _availability_status_count(availability, "partial"),
            "failed_records": _availability_status_count(availability, "failed"),
            "stale_records": _availability_status_count(availability, "stale"),
            "degraded_records": _availability_status_count(availability, "degraded"),
        },
    )


def _onchain_flow_history_check(config: dict[str, Any], run: RunContext) -> dict[str, Any]:
    onchain_flow = _onchain_flow_config(config)
    if not onchain_flow.get("enabled"):
        return _check("onchain_flow_history", "shared_data", "skipped", "onchain_flow.enabled is false.", [])
    artifact = "data/onchain/metadata/onchain_flow_state.json"
    summary = run.manifest.get("onchain_flow_history")
    if not isinstance(summary, dict):
        return _check("onchain_flow_history", "shared_data", "skipped", "on-chain flow history was not produced.", [])
    state, error = _read_json(run.config_path.parent / artifact)
    if error:
        return _check("onchain_flow_history", "shared_data", "failed", error, [artifact], errors=[error])
    warnings = _string_list(state.get("warnings"))
    errors = _error_messages(state.get("errors"))
    totals_value = state.get("totals")
    totals = dict(totals_value) if isinstance(totals_value, dict) else {}
    availability = _list(state.get("availability"))
    status = _status_from_summary(str(state.get("status") or summary.get("status")), warnings, errors)
    return _check(
        "onchain_flow_history",
        "shared_data",
        status,
        f"on-chain flow history status: {state.get('status') or 'unknown'}.",
        [
            artifact,
            "data/onchain/metadata/onchain_flow_schema.json",
        ],
        warnings=warnings,
        errors=errors,
        details={
            **totals,
            "groups": len(_list(state.get("groups"))),
            "availability_records": len(availability),
            "unavailable_records": _availability_status_count(availability, "unavailable"),
            "partial_records": _availability_status_count(availability, "partial"),
            "failed_records": _availability_status_count(availability, "failed"),
            "stale_records": _availability_status_count(availability, "stale"),
            "degraded_records": _availability_status_count(availability, "degraded"),
            "insufficient_data_records": _availability_status_count(availability, "insufficient_data"),
        },
    )


def _derivatives_views_check(config: dict[str, Any], run: RunContext, *, now: str) -> dict[str, Any]:
    derivatives = _derivatives_config(config)
    if not derivatives.get("enabled"):
        return _check("derivatives_market_views", "raw", "skipped", "market.derivatives.enabled is false.", [])
    artifact = "raw/derivatives_market_views.json"
    views_artifact, error = _read_json(run.raw_dir / "derivatives_market_views.json")
    if error:
        return _check("derivatives_market_views", "raw", "failed", error, [artifact], errors=[error])
    views = _list(views_artifact.get("views"))
    warnings = _unique_sorted(
        [
            *_string_list(views_artifact.get("warnings")),
            *_derivatives_view_warnings(views),
            *_timestamp_warnings(_derivatives_view_timestamps(views), now=now),
            *_stale_timestamp_warnings(_derivatives_view_timestamps(views), now=now, max_age_hours=48),
        ]
    )
    errors = _error_messages(views_artifact.get("errors"))
    status = "failed" if errors else "warning" if warnings else "ok"
    return _check(
        "derivatives_market_views",
        "raw",
        status,
        f"{len(views)} derivatives market view(s).",
        [artifact],
        warnings=warnings,
        errors=errors,
        details={
            "views": len(views),
            "insufficient_views": sum(
                1 for view in views if isinstance(view, dict) and view.get("insufficient_data")
            ),
            "missing_history_views": sum(
                1 for view in views if isinstance(view, dict) and view.get("status") == "missing_history"
            ),
            "skipped_views": sum(1 for view in views if isinstance(view, dict) and view.get("status") == "skipped"),
        },
    )


def _macro_calendar_views_check(config: dict[str, Any], run: RunContext, *, now: str) -> dict[str, Any]:
    macro_calendar = _macro_calendar_config(config)
    if not macro_calendar.get("enabled"):
        return _check("macro_calendar_views", "raw", "skipped", "macro_calendar.enabled is false.", [])
    artifact = "raw/macro_calendar_views.json"
    views_artifact, error = _read_json(run.raw_dir / "macro_calendar_views.json")
    if error:
        return _check("macro_calendar_views", "raw", "failed", error, [artifact], errors=[error])
    views = _list(views_artifact.get("views"))
    warnings = _unique_sorted(
        [
            *_string_list(views_artifact.get("warnings")),
            *_macro_calendar_view_warnings(views),
            *_timestamp_warnings(_macro_calendar_view_timestamps(views), now=now),
            *_stale_timestamp_warnings(_macro_calendar_view_timestamps(views), now=now, max_age_hours=48),
        ]
    )
    errors = _error_messages(views_artifact.get("errors"))
    status = "failed" if errors else "warning" if warnings else "ok"
    return _check(
        "macro_calendar_views",
        "raw",
        status,
        f"{len(views)} macro calendar view(s).",
        [artifact],
        warnings=warnings,
        errors=errors,
        details={
            "views": len(views),
            "events": sum(_int(view.get("event_count")) for view in views if isinstance(view, dict)),
            "records": sum(_int(view.get("included_record_count")) for view in views if isinstance(view, dict)),
            "no_event_views": sum(1 for view in views if isinstance(view, dict) and view.get("status") == "no_event"),
            "stale_views": sum(1 for view in views if isinstance(view, dict) and view.get("status") == "stale"),
            "unavailable_views": sum(
                1 for view in views if isinstance(view, dict) and view.get("status") == "unavailable"
            ),
            "skipped_views": sum(1 for view in views if isinstance(view, dict) and view.get("status") == "skipped"),
        },
    )


def _onchain_flow_views_check(config: dict[str, Any], run: RunContext, *, now: str) -> dict[str, Any]:
    onchain_flow = _onchain_flow_config(config)
    if not onchain_flow.get("enabled"):
        return _check("onchain_flow_views", "raw", "skipped", "onchain_flow.enabled is false.", [])
    artifact = "raw/onchain_flow_views.json"
    views_artifact, error = _read_json(run.raw_dir / "onchain_flow_views.json")
    if error:
        return _check("onchain_flow_views", "raw", "failed", error, [artifact], errors=[error])
    views = _list(views_artifact.get("views"))
    warnings = _unique_sorted(
        [
            *_string_list(views_artifact.get("warnings")),
            *_onchain_flow_view_warnings(views),
            *_timestamp_warnings(_onchain_flow_view_timestamps(views), now=now),
            *_stale_timestamp_warnings(_onchain_flow_view_timestamps(views), now=now, max_age_hours=72),
        ]
    )
    errors = _error_messages(views_artifact.get("errors"))
    status = "failed" if errors else "warning" if warnings else "ok"
    return _check(
        "onchain_flow_views",
        "raw",
        status,
        f"{len(views)} on-chain flow view(s).",
        [artifact],
        warnings=warnings,
        errors=errors,
        details={
            "views": len(views),
            "records": sum(_int(view.get("included_record_count")) for view in views if isinstance(view, dict)),
            "bounded_views": _status_count(views, "bounded"),
            "partial_views": _status_count(views, "partial"),
            "stale_views": _status_count(views, "stale"),
            "unavailable_views": _status_count(views, "unavailable"),
            "failed_views": _status_count(views, "failed"),
            "insufficient_data_views": _status_count(views, "insufficient_data"),
            "missing_history_views": _status_count(views, "missing_history"),
            "skipped_views": _status_count(views, "skipped"),
        },
    )


def _macro_calendar_context_check(config: dict[str, Any], run: RunContext) -> dict[str, Any]:
    macro_calendar = _macro_calendar_config(config)
    if not macro_calendar.get("enabled"):
        return _check("macro_calendar_context", "analysis", "skipped", "macro_calendar.enabled is false.", [])
    artifact = "analysis/macro_calendar_context.json"
    context, error = _read_json(run.analysis_dir / "macro_calendar_context.json")
    if error:
        return _check("macro_calendar_context", "analysis", "failed", error, [artifact], errors=[error])
    if context.get("artifact_type") != "macro_calendar_context" or not isinstance(context.get("records"), list):
        return _check(
            "macro_calendar_context",
            "analysis",
            "failed",
            "analysis/macro_calendar_context.json is invalid.",
            [artifact],
            errors=["macro calendar context artifact_type or records are invalid."],
        )
    records = _list(context.get("records"))
    warnings = _unique_sorted([*_string_list(context.get("warnings")), *_macro_calendar_context_warnings(records)])
    errors = _error_messages(context.get("errors"))
    status = _status_from_summary(str(context.get("status") or "unknown"), warnings, errors)
    counts = _dict(context.get("counts"))
    return _check(
        "macro_calendar_context",
        "analysis",
        status,
        f"{len(records)} macro calendar context record(s).",
        [artifact],
        warnings=warnings,
        errors=errors,
        details={
            "records": len(records),
            "scheduled_catalyst": _int(counts.get("scheduled_catalyst")),
            "recent_catalyst": _int(counts.get("recent_catalyst")),
            "no_event_window": _int(counts.get("no_event_window")),
            "source_availability": _int(counts.get("source_availability")),
            "succeeded": _status_count(records, "succeeded"),
            "partial": _status_count(records, "partial"),
            "stale": _status_count(records, "stale"),
            "no_event": _status_count(records, "no_event"),
            "unavailable": _status_count(records, "unavailable"),
            "failed": _status_count(records, "failed"),
            "degraded": _status_count(records, "degraded"),
        },
    )


def _onchain_flow_context_check(config: dict[str, Any], run: RunContext) -> dict[str, Any]:
    onchain_flow = _onchain_flow_config(config)
    if not onchain_flow.get("enabled"):
        return _check("onchain_flow_context", "analysis", "skipped", "onchain_flow.enabled is false.", [])
    artifact = "analysis/onchain_flow_context.json"
    context, error = _read_json(run.analysis_dir / "onchain_flow_context.json")
    if error:
        return _check("onchain_flow_context", "analysis", "failed", error, [artifact], errors=[error])
    if context.get("artifact_type") != "onchain_flow_context" or not isinstance(context.get("records"), list):
        return _check(
            "onchain_flow_context",
            "analysis",
            "failed",
            "analysis/onchain_flow_context.json is invalid.",
            [artifact],
            errors=["on-chain flow context artifact_type or records are invalid."],
        )
    records = _list(context.get("records"))
    warnings = _unique_sorted([*_string_list(context.get("warnings")), *_onchain_flow_context_warnings(records)])
    errors = _error_messages(context.get("errors"))
    status = _status_from_summary(str(context.get("status") or "unknown"), warnings, errors)
    counts = _dict(context.get("counts"))
    return _check(
        "onchain_flow_context",
        "analysis",
        status,
        f"{len(records)} on-chain flow context record(s).",
        [artifact],
        warnings=warnings,
        errors=errors,
        details={
            "records": len(records),
            "stablecoin_liquidity": _int(counts.get("stablecoin_liquidity")),
            "chain_activity": _int(counts.get("chain_activity")),
            "network_congestion": _int(counts.get("network_congestion")),
            "exchange_flow_source_availability": _int(counts.get("exchange_flow_source_availability")),
            "succeeded": _status_count(records, "succeeded"),
            "bounded": _status_count(records, "bounded"),
            "partial": _status_count(records, "partial"),
            "stale": _status_count(records, "stale"),
            "unavailable": _status_count(records, "unavailable"),
            "insufficient_data": _status_count(records, "insufficient_data"),
            "failed": _status_count(records, "failed"),
            "degraded": _status_count(records, "degraded"),
        },
    )


def _macro_calendar_material_check(config: dict[str, Any], run: RunContext) -> dict[str, Any]:
    macro_calendar = _macro_calendar_config(config)
    if not macro_calendar.get("enabled"):
        return _check("macro_calendar_material", "analysis", "skipped", "macro_calendar.enabled is false.", [])
    artifact = "analysis/macro_calendar_material.md"
    path = run.analysis_dir / "macro_calendar_material.md"
    if not path.exists():
        return _check("macro_calendar_material", "analysis", "failed", f"{artifact} was not found.", [artifact], errors=[f"{artifact} was not found."])
    material = path.read_text(encoding="utf-8")
    warnings = []
    errors = []
    required_boundaries = [
        "codex_may_generate_macro_events: false",
        "codex_may_generate_risk_levels: false",
        "full_raw_macro_calendar_artifacts_embedded: false",
        "full_reusable_macro_calendar_history_embedded: false",
        "full_macro_calendar_context_json_embedded: false",
    ]
    for boundary in required_boundaries:
        if boundary not in material:
            errors.append(f"macro calendar material missing boundary: {boundary}")
    summary = run.manifest.get("macro_calendar_material")
    summary_mapping = summary if isinstance(summary, dict) else {}
    status = "failed" if errors else "warning" if warnings else "ok"
    return _check(
        "macro_calendar_material",
        "analysis",
        status,
        "macro calendar material is present with Codex boundary metadata.",
        [artifact],
        warnings=warnings,
        errors=errors,
        details={
            "selected_records": _int(summary_mapping.get("selected_records")),
            "omitted_records": _int(summary_mapping.get("omitted_records")),
            "context_records": _int(summary_mapping.get("context_records")),
            "chars": len(material),
            "codex_boundaries_present": not errors,
        },
    )


def _onchain_flow_material_check(config: dict[str, Any], run: RunContext) -> dict[str, Any]:
    onchain_flow = _onchain_flow_config(config)
    if not onchain_flow.get("enabled"):
        return _check("onchain_flow_material", "analysis", "skipped", "onchain_flow.enabled is false.", [])
    artifact = "analysis/onchain_flow_material.md"
    path = run.analysis_dir / "onchain_flow_material.md"
    if not path.exists():
        return _check(
            "onchain_flow_material",
            "analysis",
            "failed",
            f"{artifact} was not found.",
            [artifact],
            errors=[f"{artifact} was not found."],
        )
    material = path.read_text(encoding="utf-8")
    warnings = []
    errors = []
    required_boundaries = [
        "codex_may_generate_onchain_records: false",
        "codex_may_generate_flow_states: false",
        "codex_may_generate_address_labels: false",
        "codex_may_generate_risk_levels: false",
        "full_raw_onchain_flow_artifacts_embedded: false",
        "full_reusable_onchain_flow_history_embedded: false",
        "full_onchain_flow_context_json_embedded: false",
    ]
    for boundary in required_boundaries:
        if boundary not in material:
            errors.append(f"on-chain flow material missing boundary: {boundary}")
    summary = run.manifest.get("onchain_flow_material")
    summary_mapping = summary if isinstance(summary, dict) else {}
    status = "failed" if errors else "warning" if warnings else "ok"
    return _check(
        "onchain_flow_material",
        "analysis",
        status,
        "on-chain flow material is present with Codex boundary metadata.",
        [artifact],
        warnings=warnings,
        errors=errors,
        details={
            "selected_records": _int(summary_mapping.get("selected_records")),
            "omitted_records": _int(summary_mapping.get("omitted_records")),
            "context_records": _int(summary_mapping.get("context_records")),
            "chars": len(material),
            "codex_boundaries_present": not errors,
        },
    )




def _text_event_records_check(config: dict[str, Any], run: RunContext, *, now: str) -> dict[str, Any]:
    if not config.get("text", {}).get("enabled"):
        return _check("text_event_records", "analysis", "skipped", "text.enabled is false.", [])
    artifact = "analysis/text_event_records.json"
    data, error = _read_json(run.analysis_dir / "text_event_records.json")
    if error:
        return _check("text_event_records", "analysis", "failed", error, [artifact], errors=[error])
    records = data.get("records") if isinstance(data, dict) else None
    if not isinstance(records, list):
        return _check(
            "text_event_records",
            "analysis",
            "failed",
            "analysis/text_event_records.json is invalid: records must be a list.",
            [artifact],
            errors=["records must be a list"],
        )
    duplicate_summary = _duplicate_summary(records)
    timestamp_warnings = _timestamp_warnings(_text_record_timestamps(records), now=now)
    record_warnings = [
        str(warning)
        for record in records
        if isinstance(record, dict)
        for warning in record.get("warnings", [])
        if isinstance(warning, str)
    ]
    warnings = _unique_sorted([*timestamp_warnings, *record_warnings, *duplicate_summary["warnings"]])
    status = "warning" if warnings else "ok"
    return _check(
        "text_event_records",
        "analysis",
        status,
        f"{len(records)} normalized text event record(s).",
        [artifact],
        warnings=warnings,
        details={
            "records": len(records),
            "duplicate_records": duplicate_summary["duplicates"],
            "conflicting_duplicates": duplicate_summary["conflicts"],
        },
    )


def _text_event_history_check(run: RunContext) -> dict[str, Any]:
    artifact = "data/research/metadata/text_event_history_state.json"
    summary = run.manifest.get("text_event_history")
    if not isinstance(summary, dict):
        return _check("text_event_history", "shared_data", "skipped", "text event history was not produced.", [])
    state, error = _read_json(run.config_path.parent / artifact)
    if error:
        return _check("text_event_history", "shared_data", "failed", error, [artifact], errors=[error])
    warnings = _string_list(state.get("warnings"))
    errors = _error_messages(state.get("errors"))
    status = _status_from_summary(str(state.get("status") or summary.get("status")), warnings, errors)
    return _check(
        "text_event_history",
        "shared_data",
        status,
        f"text event history status: {state.get('status') or 'unknown'}.",
        [artifact],
        warnings=warnings,
        errors=errors,
        details=dict(state.get("totals") or {}),
    )


def _research_data_catalog_check(run: RunContext) -> dict[str, Any]:
    artifact = "data/research/metadata/research_data_catalog.json"
    summary = run.manifest.get("research_data_catalog")
    if not isinstance(summary, dict):
        return _check("research_data_catalog", "shared_data", "skipped", "research data catalog was not produced.", [])
    catalog, error = _read_json(run.config_path.parent / artifact)
    if error:
        return _check("research_data_catalog", "shared_data", "failed", error, [artifact], errors=[error])
    warnings = _string_list(catalog.get("warnings"))
    errors = _error_messages(catalog.get("errors"))
    status = _status_from_summary(str(catalog.get("status") or summary.get("status")), warnings, errors)
    return _check(
        "research_data_catalog",
        "shared_data",
        status,
        f"research data catalog status: {catalog.get('status') or 'unknown'}.",
        [artifact],
        warnings=warnings,
        errors=errors,
        details=dict(catalog.get("counts") or {}),
    )


def _run_index_check(run: RunContext) -> dict[str, Any]:
    artifact = "data/research/index.sqlite"
    summary = run.manifest.get("run_index")
    if not isinstance(summary, dict):
        return _check(
            "run_index",
            "shared_data",
            "skipped",
            "run index is a terminal artifact written after the data-quality stage; this stage-time skip is expected and must not be reported as a final missing run index.",
            [artifact],
            details={
                "terminal_artifact": True,
                "written_after_data_quality_stage": True,
                "stage_time_skip_is_expected": True,
                "report_as_final_missing": False,
            },
        )
    errors = []
    if summary.get("status") == "failed":
        errors.append(str(summary.get("error") or "run index write failed"))
    status = "failed" if errors else "ok"
    return _check(
        "run_index",
        "shared_data",
        status,
        f"run index status: {summary.get('status') or 'unknown'}.",
        [artifact],
        errors=errors,
        details=dict(summary.get("tables") or {}),
    )


def _partial_collection_check(run: RunContext) -> dict[str, Any]:
    warnings = []
    errors = []
    for key in ("raw_market", "raw_derivatives_market", "raw_macro_calendar", "raw_onchain_flow", "raw_text_events"):
        path = run.manifest.get("artifacts", {}).get(key)
        if not isinstance(path, str):
            continue
        root = run.raw_dir if path.startswith("raw/") else run.run_dir
        data, error = _read_json(root / path.removeprefix("raw/"))
        if error:
            continue
        artifact_errors = _error_messages(data.get("errors")) if isinstance(data, dict) else []
        errors.extend(artifact_errors)
    status = "degraded" if errors else "ok"
    return _check(
        "partial_collection",
        "raw",
        status,
        f"{len(errors)} collection error(s) recorded across raw artifacts.",
        [],
        warnings=warnings,
        errors=errors,
    )


def _check(
    name: str,
    scope: str,
    status: str,
    summary: str,
    source_artifacts: list[str],
    *,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    warnings = _unique_sorted(warnings or [])
    errors = errors or []
    return {
        "name": name,
        "status": status,
        "scope": scope,
        "summary": summary,
        "warning_count": len(warnings),
        "error_count": len(errors),
        "source_artifacts": source_artifacts,
        "details": {
            **(details or {}),
            "warnings": warnings,
            "errors": errors,
        },
    }


def _read_json(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, f"{path.name} was not found."
    except JSONDecodeError as exc:
        return {}, f"{path.name} is not valid JSON: {exc.msg}."
    if not isinstance(loaded, dict):
        return {}, f"{path.name} must be a JSON object."
    return loaded, None


def _timestamp_warnings(timestamps: list[tuple[str, str]], *, now: str) -> list[str]:
    warnings = []
    now_value = _parse_utc(now)
    for field, value in timestamps:
        parsed = _parse_utc(value)
        if parsed is None:
            warnings.append(f"{field} is not a valid ISO 8601 UTC timestamp: {value}")
            continue
        if parsed > now_value:
            warnings.append(f"{field} is in the future: {value}")
    return warnings


def _market_timestamps(raw: dict[str, Any]) -> list[tuple[str, str]]:
    values = []
    for item in raw.get("items", []):
        if isinstance(item, dict) and isinstance(item.get("as_of"), str):
            values.append(("raw/market.json as_of", item["as_of"]))
    return values


def _text_raw_timestamps(raw: dict[str, Any]) -> list[tuple[str, str]]:
    values = []
    if isinstance(raw.get("collected_at"), str):
        values.append(("raw/text_events.json collected_at", raw["collected_at"]))
    for item in raw.get("items", []):
        if isinstance(item, dict) and isinstance(item.get("published_at"), str):
            values.append(("raw/text_events.json published_at", item["published_at"]))
    return values


def _text_record_timestamps(records: list[Any]) -> list[tuple[str, str]]:
    values = []
    for record in records:
        if not isinstance(record, dict):
            continue
        for field in ("published_at", "collected_at"):
            value = record.get(field)
            if isinstance(value, str):
                values.append((f"analysis/text_event_records.json {field}", value))
    return values


def _derivatives_timestamps(raw: dict[str, Any]) -> list[tuple[str, str]]:
    values = []
    if isinstance(raw.get("collected_at"), str):
        values.append(("raw/derivatives_market.json collected_at", raw["collected_at"]))
    for item in raw.get("items", []):
        if isinstance(item, dict) and isinstance(item.get("as_of"), str):
            values.append(("raw/derivatives_market.json as_of", item["as_of"]))
    return values


def _derivatives_view_timestamps(views: list[Any]) -> list[tuple[str, str]]:
    values = []
    for view in views:
        if not isinstance(view, dict):
            continue
        value = view.get("latest_observation_time")
        if isinstance(value, str):
            values.append(("raw/derivatives_market_views.json latest_observation_time", value))
    return values


def _macro_calendar_timestamps(raw: dict[str, Any]) -> list[tuple[str, str]]:
    values = []
    if isinstance(raw.get("collected_at"), str):
        values.append(("raw/macro_calendar.json collected_at", raw["collected_at"]))
    for item in raw.get("items", []):
        if isinstance(item, dict) and isinstance(item.get("source_published_at"), str):
            values.append(("raw/macro_calendar.json source_published_at", item["source_published_at"]))
    return values


def _macro_calendar_view_timestamps(views: list[Any]) -> list[tuple[str, str]]:
    values = []
    for view in views:
        if not isinstance(view, dict):
            continue
        value = view.get("latest_observation_time")
        if isinstance(value, str):
            values.append(("raw/macro_calendar_views.json latest_observation_time", value))
    return values


def _onchain_flow_timestamps(raw: dict[str, Any]) -> list[tuple[str, str]]:
    values = []
    if isinstance(raw.get("collected_at"), str):
        values.append(("raw/onchain_flow.json collected_at", raw["collected_at"]))
    for item in raw.get("items", []):
        if isinstance(item, dict) and isinstance(item.get("as_of"), str):
            values.append(("raw/onchain_flow.json as_of", item["as_of"]))
    return values


def _onchain_flow_view_timestamps(views: list[Any]) -> list[tuple[str, str]]:
    values = []
    for view in views:
        if not isinstance(view, dict):
            continue
        value = view.get("latest_observation_time")
        if isinstance(value, str):
            values.append(("raw/onchain_flow_views.json latest_observation_time", value))
    return values


def _stale_timestamp_warnings(timestamps: list[tuple[str, str]], *, now: str, max_age_hours: int) -> list[str]:
    warnings = []
    now_value = _parse_utc(now)
    if now_value is None:
        return warnings
    for field, value in timestamps:
        parsed = _parse_utc(value)
        if parsed is None or parsed > now_value:
            continue
        age_hours = (now_value - parsed).total_seconds() / 3600
        if age_hours > max_age_hours:
            warnings.append(f"{field} is stale: {value} is older than {max_age_hours} hours.")
    return warnings


def _derivatives_missing_value_warnings(raw: dict[str, Any]) -> list[str]:
    warnings = []
    for item in raw.get("items", []):
        if not isinstance(item, dict):
            continue
        metrics = item.get("metrics")
        if not isinstance(metrics, dict) or not metrics:
            warnings.append(f"derivatives item {item.get('item_id') or 'unknown'} has no metrics.")
            continue
        for key, value in metrics.items():
            if value is None:
                warnings.append(f"derivatives item {item.get('item_id') or 'unknown'} metric {key} is missing.")
    return warnings


def _derivatives_availability_warnings(raw: dict[str, Any]) -> list[str]:
    warnings = []
    for item in _list(raw.get("availability")):
        if not isinstance(item, dict):
            continue
        status = item.get("status")
        if status not in {"failed", "partial", "unavailable", "stale", "degraded"}:
            continue
        data_class = item.get("data_class") or "unknown"
        symbol = item.get("symbol") or "all_symbols"
        period = item.get("period") or "all_periods"
        reason = item.get("reason") or status
        warnings.append(f"derivatives availability {data_class} {symbol} {period}: {reason}.")
    return warnings


def _macro_calendar_availability_warnings(raw: dict[str, Any]) -> list[str]:
    warnings = []
    for item in _list(raw.get("availability")):
        if not isinstance(item, dict):
            continue
        status = item.get("status")
        if status not in {"failed", "partial", "unavailable", "stale", "degraded"}:
            continue
        source = item.get("source") or "unknown_source"
        data_class = item.get("data_class") or "unknown"
        region = item.get("region") or "all_regions"
        reason = item.get("reason") or status
        warnings.append(f"macro calendar availability {source} {data_class} {region}: {reason}.")
    return warnings


def _macro_calendar_item_warnings(raw: dict[str, Any]) -> list[str]:
    warnings = []
    for item in raw.get("items", []):
        if not isinstance(item, dict):
            continue
        warnings.extend(_string_list(item.get("warnings")))
    return warnings


def _onchain_flow_missing_value_warnings(raw: dict[str, Any]) -> list[str]:
    warnings = []
    for item in raw.get("items", []):
        if not isinstance(item, dict):
            continue
        metrics = item.get("metrics")
        if not isinstance(metrics, dict) or not metrics:
            warnings.append(f"on-chain flow item {item.get('item_id') or 'unknown'} has no metrics.")
            continue
        for key, value in metrics.items():
            if value is None:
                warnings.append(f"on-chain flow item {item.get('item_id') or 'unknown'} metric {key} is missing.")
    return warnings


def _onchain_flow_availability_warnings(raw: dict[str, Any]) -> list[str]:
    warnings = []
    for item in _list(raw.get("availability")):
        if not isinstance(item, dict):
            continue
        status = item.get("status")
        if status not in {"failed", "partial", "unavailable", "stale", "degraded", "insufficient_data"}:
            continue
        source = item.get("source") or "unknown_source"
        data_class = item.get("data_class") or "unknown"
        asset = item.get("asset") or "all_assets"
        chain = item.get("chain") or "all_chains"
        reason = item.get("reason") or status
        warnings.append(f"on-chain flow availability {source} {data_class} {asset} {chain}: {reason}.")
    return warnings


def _onchain_flow_item_warnings(raw: dict[str, Any]) -> list[str]:
    warnings = []
    for item in raw.get("items", []):
        if not isinstance(item, dict):
            continue
        warnings.extend(_string_list(item.get("warnings")))
    return warnings


def _derivatives_view_warnings(views: list[Any]) -> list[str]:
    warnings = []
    for view in views:
        if not isinstance(view, dict):
            continue
        warnings.extend(_string_list(view.get("warnings")))
    return warnings


def _macro_calendar_view_warnings(views: list[Any]) -> list[str]:
    warnings = []
    for view in views:
        if not isinstance(view, dict):
            continue
        warnings.extend(_string_list(view.get("warnings")))
    return warnings


def _macro_calendar_context_warnings(records: list[Any]) -> list[str]:
    warnings = []
    for record in records:
        if not isinstance(record, dict):
            continue
        warnings.extend(_string_list(record.get("warnings")))
    return warnings


def _onchain_flow_view_warnings(views: list[Any]) -> list[str]:
    warnings = []
    for view in views:
        if not isinstance(view, dict):
            continue
        warnings.extend(_string_list(view.get("warnings")))
    return warnings


def _onchain_flow_context_warnings(records: list[Any]) -> list[str]:
    warnings = []
    for record in records:
        if not isinstance(record, dict):
            continue
        warnings.extend(_string_list(record.get("warnings")))
    return warnings


def _availability_status_count(records: list[Any], status: str) -> int:
    return sum(1 for item in records if isinstance(item, dict) and item.get("status") == status)


def _status_count(records: list[Any], status: str) -> int:
    return sum(1 for item in records if isinstance(item, dict) and item.get("status") == status)


def _duplicate_summary(records: list[Any]) -> dict[str, Any]:
    seen: dict[str, str] = {}
    duplicates = 0
    conflicts = 0
    warnings = []
    for record in records:
        if not isinstance(record, dict):
            continue
        key = _duplicate_key(record)
        content = str(record.get("normalized_text") or "")
        existing = seen.get(key)
        if existing is None:
            seen[key] = content
            continue
        duplicates += 1
        if existing != content:
            conflicts += 1
            warnings.append(f"conflicting duplicate text event record: {key}")
    return {"duplicates": duplicates, "conflicts": conflicts, "warnings": warnings}


def _duplicate_key(record: dict[str, Any]) -> str:
    for field in ("canonical_url", "raw_item_id", "event_id"):
        value = record.get(field)
        if isinstance(value, str) and value:
            return value
    return str(record.get("normalized_text") or "")


def _status_from_summary(status: str, warnings: list[str], errors: list[str]) -> str:
    if errors or status == "failed":
        return "failed"
    if status in {"degraded", "warning", "skipped"}:
        return status
    if warnings:
        return "warning"
    return "ok"


def _derivatives_history_status(status: str, warnings: list[str], errors: list[str]) -> str:
    if status == "failed":
        return "failed"
    if status in {"degraded", "warning", "skipped"}:
        return status
    if errors or warnings:
        return "warning"
    return "ok"


def _overall_status(checks: list[dict[str, Any]]) -> str:
    statuses = {str(check["status"]) for check in checks}
    if "failed" in statuses:
        return "failed"
    if "degraded" in statuses:
        return "degraded"
    if "warning" in statuses:
        return "warning"
    if statuses == {"skipped"}:
        return "skipped"
    return "ok"


def _source_artifacts(checks: list[dict[str, Any]]) -> list[str]:
    values = []
    for check in checks:
        values.extend(check.get("source_artifacts") or [])
    return _unique_sorted([str(value) for value in values if isinstance(value, str) and value])


def _count_status(checks: list[dict[str, Any]], status: str) -> int:
    return sum(1 for check in checks if check["status"] == status)


def _error_messages(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    messages = []
    for value in values:
        if isinstance(value, dict):
            message = value.get("message")
            if isinstance(message, str) and message:
                messages.append(message)
        elif isinstance(value, str) and value:
            messages.append(value)
    return messages


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item]


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _derivatives_config(config: dict[str, Any]) -> dict[str, Any]:
    market = config.get("market")
    if not isinstance(market, dict):
        return {}
    derivatives = market.get("derivatives")
    return derivatives if isinstance(derivatives, dict) else {}


def _macro_calendar_config(config: dict[str, Any]) -> dict[str, Any]:
    macro_calendar = config.get("macro_calendar")
    return macro_calendar if isinstance(macro_calendar, dict) else {}


def _onchain_flow_config(config: dict[str, Any]) -> dict[str, Any]:
    onchain_flow = config.get("onchain_flow")
    return onchain_flow if isinstance(onchain_flow, dict) else {}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    return 0


def _parse_utc(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _format_utc(value: datetime | str | None) -> str:
    if value is None:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("created_at must include a UTC offset.")
        timestamp = value.astimezone(timezone.utc).replace(microsecond=0)
    elif isinstance(value, str):
        parsed = _parse_utc(value)
        if parsed is None:
            raise ValueError("created_at must be an ISO 8601 UTC string.")
        timestamp = parsed.replace(microsecond=0)
    else:
        raise ValueError("created_at must be a datetime or ISO 8601 UTC string.")
    return timestamp.isoformat().replace("+00:00", "Z")


def _unique_sorted(values: list[str]) -> list[str]:
    return sorted(set(values))
