from __future__ import annotations

import json
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from halpha.data.raw_artifacts import (
    RawArtifactError,
    validate_derivatives_market_raw_artifact,
    validate_macro_calendar_raw_artifact,
    validate_market_raw_artifact,
    validate_onchain_flow_raw_artifact,
    validate_text_events_raw_artifact,
)
from halpha.runtime.pipeline_contracts import RunContext


def raw_data_quality_checks(config: dict[str, Any], run: RunContext, *, now: str) -> list[dict[str, Any]]:
    return [
        _raw_market_check(config, run, now=now),
        _raw_derivatives_check(config, run, now=now),
        _raw_macro_calendar_check(config, run, now=now),
        _raw_onchain_flow_check(config, run, now=now),
        _raw_text_check(config, run, now=now),
    ]


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
            "unavailable_records": _availability_status_count(_list(raw.get("availability")), "unavailable"),
            "partial_records": _availability_status_count(_list(raw.get("availability")), "partial"),
            "failed_records": _availability_status_count(_list(raw.get("availability")), "failed"),
            "stale_records": _availability_status_count(_list(raw.get("availability")), "stale"),
            "degraded_records": _availability_status_count(_list(raw.get("availability")), "degraded"),
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


def _derivatives_timestamps(raw: dict[str, Any]) -> list[tuple[str, str]]:
    values = []
    if isinstance(raw.get("collected_at"), str):
        values.append(("raw/derivatives_market.json collected_at", raw["collected_at"]))
    for item in raw.get("items", []):
        if isinstance(item, dict) and isinstance(item.get("as_of"), str):
            values.append(("raw/derivatives_market.json as_of", item["as_of"]))
    return values


def _macro_calendar_timestamps(raw: dict[str, Any]) -> list[tuple[str, str]]:
    values = []
    if isinstance(raw.get("collected_at"), str):
        values.append(("raw/macro_calendar.json collected_at", raw["collected_at"]))
    for item in raw.get("items", []):
        if isinstance(item, dict) and isinstance(item.get("source_published_at"), str):
            values.append(("raw/macro_calendar.json source_published_at", item["source_published_at"]))
    return values


def _onchain_flow_timestamps(raw: dict[str, Any]) -> list[tuple[str, str]]:
    values = []
    if isinstance(raw.get("collected_at"), str):
        values.append(("raw/onchain_flow.json collected_at", raw["collected_at"]))
    for item in raw.get("items", []):
        if isinstance(item, dict) and isinstance(item.get("as_of"), str):
            values.append(("raw/onchain_flow.json as_of", item["as_of"]))
    return values


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


def _availability_status_count(records: list[Any], status: str) -> int:
    return sum(1 for item in records if isinstance(item, dict) and item.get("status") == status)


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


def _parse_utc(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _unique_sorted(values: list[str]) -> list[str]:
    return sorted(set(values))


__all__ = ["raw_data_quality_checks"]
