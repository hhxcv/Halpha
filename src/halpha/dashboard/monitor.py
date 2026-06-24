from __future__ import annotations

from pathlib import Path
from typing import Any

from halpha.dashboard.common import (
    dashboard_overall_status as _overall_status,
    dashboard_safe_ref as _safe_ref,
)
from halpha.monitor.monitoring import load_monitor_config
from halpha.monitor.state_store import MONITOR_STATE_STORE_ARTIFACT, MonitorStateRepository
from halpha.storage import artifact_base as _artifact_base


MAX_CYCLE_SUMMARIES = 20
MAX_ALERT_SAMPLE_RECORDS = 20
MAX_SOURCE_ARTIFACTS = 40
ALERT_COUNT_KEYS = (
    "records",
    "emitted",
    "suppressed_duplicate",
    "suppressed_cooldown",
    "suppressed_no_alert",
    "skipped",
)


def dashboard_monitor_summary(config: dict[str, Any], *, config_path: Path) -> dict[str, Any]:
    base = _artifact_base(config_path)
    settings = load_monitor_config(config)
    output_dir = _monitor_output_dir(config, base=base)
    output_ref = _safe_ref(output_dir, base=base)
    repository = MonitorStateRepository(config_path=config_path)
    health = _health_summary(repository, output_ref=output_ref, base=base)
    cycles = repository.list_cycles(monitor_output_dir=output_ref, base=base, limit=MAX_CYCLE_SUMMARIES)
    alerts = repository.alert_summary(monitor_output_dir=output_ref, limit=MAX_ALERT_SAMPLE_RECORDS)
    cooldown = repository.cooldown_summary(monitor_output_dir=output_ref)
    components = [health, cycles, alerts, cooldown]
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_monitor",
        "status": _monitor_overall_status([str(component.get("status") or "unknown") for component in components]),
        "monitor_output_dir": output_ref,
        "settings": {
            "interval_seconds": settings.interval_seconds,
            "max_cycles": settings.max_cycles,
            "failure_backoff_max_seconds": settings.failure_backoff_max_seconds,
            "cooldown_seconds": settings.cooldown_seconds,
            "output_dir": output_ref,
            "target_stage": settings.target_stage,
            "no_codex": settings.no_codex,
        },
        "health": health,
        "latest_cycle": cycles["cycles"][0] if cycles["cycles"] else None,
        "cycles": cycles,
        "alert_archive": alerts,
        "cooldown": cooldown,
        "source_artifacts": _unique_artifacts(
            artifact
            for component in components
            for artifact in _string_list(component.get("source_artifacts"))
        ),
        "omitted": {
            "full_alert_archive_embedded": False,
            "full_cooldown_records_embedded": False,
            "private_personalized_evidence_embedded": False,
            "alert_sample_record_limit": MAX_ALERT_SAMPLE_RECORDS,
        },
        "warnings": _combined_messages(components, key="warnings"),
        "errors": _combined_messages(components, key="errors"),
    }


def dashboard_monitor_cycles(config: dict[str, Any], *, config_path: Path) -> dict[str, Any]:
    base = _artifact_base(config_path)
    output_dir = _monitor_output_dir(config, base=base)
    return MonitorStateRepository(config_path=config_path).list_cycles(
        monitor_output_dir=_safe_ref(output_dir, base=base),
        base=base,
        limit=MAX_CYCLE_SUMMARIES,
    )


def dashboard_monitor_alerts(config: dict[str, Any], *, config_path: Path) -> dict[str, Any]:
    base = _artifact_base(config_path)
    output_dir = _monitor_output_dir(config, base=base)
    output_ref = _safe_ref(output_dir, base=base)
    repository = MonitorStateRepository(config_path=config_path)
    alerts = repository.alert_summary(monitor_output_dir=output_ref, limit=MAX_ALERT_SAMPLE_RECORDS)
    cooldown = repository.cooldown_summary(monitor_output_dir=output_ref)
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_monitor_alerts",
        "status": _overall_status([str(alerts.get("status") or "unknown"), str(cooldown.get("status") or "unknown")]),
        "alert_archive": alerts,
        "cooldown": cooldown,
        "source_artifacts": _unique_artifacts(
            [*_string_list(alerts.get("source_artifacts")), *_string_list(cooldown.get("source_artifacts"))]
        ),
        "omitted": {
            "full_alert_archive_embedded": False,
            "full_cooldown_records_embedded": False,
            "private_personalized_evidence_embedded": False,
            "alert_sample_record_limit": MAX_ALERT_SAMPLE_RECORDS,
        },
        "warnings": _combined_messages([alerts, cooldown], key="warnings"),
        "errors": _combined_messages([alerts, cooldown], key="errors"),
    }


def _health_summary(repository: MonitorStateRepository, *, output_ref: str, base: Path) -> dict[str, Any]:
    data = repository.health_state(monitor_output_dir=output_ref, base=base)
    fields = {
        "artifact": MONITOR_STATE_STORE_ARTIFACT,
        "artifact_type": data.get("artifact_type"),
        "updated_at": data.get("updated_at"),
        "cycle_count": _int(data.get("cycle_count")),
        "failed_cycle_count": _int(data.get("failed_cycle_count")),
        "latest_cycle_id": data.get("latest_cycle_id"),
        "latest_cycle_status": data.get("latest_cycle_status"),
        "latest_run_id": data.get("latest_run_id"),
        "latest_run_manifest": data.get("latest_run_manifest"),
        "latest_cycle_manifest": data.get("latest_cycle_manifest"),
        "alert_archive_status": data.get("alert_archive_status"),
        "alert_counts": _alert_counts(data.get("alert_counts")),
        "cooldown_records": _int(data.get("cooldown_records")),
        "warning_count": _int(data.get("warning_count")),
        "error_count": _int(data.get("error_count")),
        "latest_loop": _bounded_mapping(data.get("latest_loop")),
        "service": _bounded_mapping(data.get("service")),
    }
    return _component(
        "monitor_health",
        str(data.get("status") or "unknown"),
        fields=fields,
        source_artifacts=_string_list(data.get("source_artifacts")),
        warnings=_string_list(data.get("warnings")),
        errors=_string_list(data.get("errors")),
    )


def _component(
    name: str,
    status: str,
    *,
    fields: dict[str, Any] | None = None,
    source_artifacts: list[str] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "fields": fields or {},
        "source_artifacts": _unique_artifacts(source_artifacts or []),
        "warnings": warnings or [],
        "errors": errors or [],
    }


def _monitor_overall_status(statuses: list[str]) -> str:
    cleaned = [status for status in statuses if status and status != "unknown"]
    if not cleaned:
        return "unknown"
    if all(status == "missing" for status in cleaned):
        return "missing"
    if "failed" in cleaned:
        return "failed"
    if any(status in {"partial", "degraded", "stale"} for status in cleaned):
        return "partial"
    if "missing" in cleaned:
        return "partial" if any(status == "available" for status in cleaned) else "missing"
    if all(status == "available" for status in cleaned):
        return "available"
    return "partial"


def _monitor_output_dir(config: dict[str, Any], *, base: Path) -> Path:
    settings = load_monitor_config(config)
    output_dir = Path(settings.output_dir)
    return output_dir if output_dir.is_absolute() else base / output_dir


def _alert_counts(value: Any) -> dict[str, int]:
    data = _dict(value)
    return {key: _int(data.get(key)) for key in ALERT_COUNT_KEYS}


def _bounded_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    output: dict[str, Any] = {}
    for key in sorted(value)[:20]:
        item = value[key]
        if isinstance(item, (str, int, float, bool)) or item is None:
            output[str(key)] = item
        elif isinstance(item, dict):
            output[str(key)] = _bounded_mapping(item)
        elif isinstance(item, list):
            output[str(key)] = [
                entry if isinstance(entry, (str, int, float, bool)) or entry is None else str(entry)
                for entry in item[:20]
            ]
        else:
            output[str(key)] = str(item)
    return output


def _combined_messages(items: list[dict[str, Any]], *, key: str) -> list[str]:
    messages: list[str] = []
    for item in items:
        messages.extend(_string_list(item.get(key)))
    return messages[:40]


def _unique_artifacts(values: Any) -> list[str]:
    artifacts: list[str] = []
    if isinstance(values, str):
        values = [values]
    for value in values or []:
        if not isinstance(value, str) or not value or value in artifacts:
            continue
        artifacts.append(value)
        if len(artifacts) >= MAX_SOURCE_ARTIFACTS:
            break
    return artifacts


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
