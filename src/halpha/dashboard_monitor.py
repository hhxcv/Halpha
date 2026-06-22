from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from .monitoring import (
    ALERT_ARCHIVE_FILENAME,
    ALERT_ARCHIVE_STATE_FILENAME,
    ALERT_COOLDOWN_STATE_FILENAME,
    MONITOR_HEALTH_STATE_FILENAME,
    load_monitor_config,
)


MAX_CYCLE_SUMMARIES = 20
MAX_ALERT_SAMPLE_RECORDS = 20
MAX_SOURCE_ARTIFACTS = 40
EXTERNAL_ARTIFACT_REF = "<external-artifact>"
ALERT_COUNT_KEYS = (
    "records",
    "emitted",
    "suppressed_duplicate",
    "suppressed_cooldown",
    "suppressed_no_alert",
    "skipped",
)
FAILED_MONITOR_STATUSES = {"failed", "error"}


def dashboard_monitor_summary(config: dict[str, Any], *, config_path: Path) -> dict[str, Any]:
    base = _config_base(config_path)
    settings = load_monitor_config(config)
    output_dir = _monitor_output_dir(config, base=base)
    health = _health_summary(output_dir, base=base)
    cycles = _cycle_list(output_dir, base=base, limit=MAX_CYCLE_SUMMARIES)
    alerts = _alert_summary(output_dir, base=base)
    cooldown = _cooldown_summary(output_dir, base=base)
    components = [health, cycles, alerts, cooldown]
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_monitor",
        "status": _overall_status([str(component.get("status") or "unknown") for component in components]),
        "monitor_output_dir": _safe_ref(output_dir, base=base),
        "settings": {
            "interval_seconds": settings.interval_seconds,
            "max_cycles": settings.max_cycles,
            "cooldown_seconds": settings.cooldown_seconds,
            "output_dir": _safe_ref(output_dir, base=base),
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
    base = _config_base(config_path)
    output_dir = _monitor_output_dir(config, base=base)
    return _cycle_list(output_dir, base=base, limit=MAX_CYCLE_SUMMARIES)


def dashboard_monitor_alerts(config: dict[str, Any], *, config_path: Path) -> dict[str, Any]:
    base = _config_base(config_path)
    output_dir = _monitor_output_dir(config, base=base)
    alerts = _alert_summary(output_dir, base=base)
    cooldown = _cooldown_summary(output_dir, base=base)
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


def _health_summary(output_dir: Path, *, base: Path) -> dict[str, Any]:
    path = output_dir / MONITOR_HEALTH_STATE_FILENAME
    artifact = _safe_ref(path, base=base)
    data, status, message = _read_json_object(path)
    if message:
        return _component(
            "monitor_health",
            status,
            source_artifacts=[artifact],
            warnings=[message] if status == "missing" else [],
            errors=[message] if status == "failed" else [],
        )
    fields = {
        "artifact": artifact,
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
    }
    status, warnings, errors = _monitor_health_status(fields)
    return _component(
        "monitor_health",
        status,
        fields=fields,
        source_artifacts=[artifact],
        warnings=warnings,
        errors=errors,
    )


def _cycle_list(output_dir: Path, *, base: Path, limit: int) -> dict[str, Any]:
    cycle_root = output_dir / "cycles"
    if not cycle_root.exists():
        return {
            "schema_version": 1,
            "artifact_type": "dashboard_monitor_cycles",
            "status": "missing",
            "cycles": [],
            "cycle_count": 0,
            "source_artifacts": [_safe_ref(cycle_root, base=base)],
            "warnings": ["monitor cycle directory was not found."],
            "errors": [],
        }
    paths = sorted(cycle_root.glob("*/monitor_cycle_manifest.json"))
    if not paths:
        return {
            "schema_version": 1,
            "artifact_type": "dashboard_monitor_cycles",
            "status": "missing",
            "cycles": [],
            "cycle_count": 0,
            "source_artifacts": [_safe_ref(cycle_root, base=base)],
            "warnings": ["monitor cycle manifests were not found."],
            "errors": [],
        }
    cycles = [_cycle_summary(path, base=base) for path in paths]
    cycles = sorted(cycles, key=lambda item: str(item.get("finished_at") or item.get("started_at") or ""), reverse=True)
    visible = cycles[:limit]
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_monitor_cycles",
        "status": _overall_status([str(cycle.get("status") or "unknown") for cycle in visible]),
        "cycles": visible,
        "cycle_count": len(cycles),
        "omitted_count": max(0, len(cycles) - len(visible)),
        "source_artifacts": _unique_artifacts(cycle.get("cycle_manifest") for cycle in visible),
        "warnings": _combined_messages(visible, key="warnings"),
        "errors": _combined_messages(visible, key="errors"),
    }


def _cycle_summary(path: Path, *, base: Path) -> dict[str, Any]:
    artifact = _safe_ref(path, base=base)
    data, status, message = _read_json_object(path)
    if message:
        return {
            "cycle_id": path.parent.name,
            "status": status,
            "cycle_manifest": artifact,
            "warnings": [message] if status == "missing" else [],
            "errors": [message] if status == "failed" else [],
        }
    archive = _dict(data.get("alert_archive"))
    product_run = _dict(data.get("product_run"))
    return {
        "cycle_id": data.get("cycle_id") or path.parent.name,
        "status": str(data.get("status") or "unknown"),
        "started_at": data.get("started_at"),
        "finished_at": data.get("finished_at"),
        "cycle_mode": data.get("cycle_mode"),
        "cycle_sequence": data.get("cycle_sequence"),
        "target_stage": data.get("target_stage"),
        "no_codex": data.get("no_codex"),
        "exit_code": data.get("exit_code"),
        "run_id": data.get("run_id"),
        "run_dir": data.get("run_dir"),
        "run_manifest": data.get("run_manifest"),
        "product_run": _bounded_mapping(product_run),
        "alert_archive": {
            "status": archive.get("status"),
            "archive": archive.get("archive"),
            "cooldown_state": archive.get("cooldown_state"),
            "counts": _alert_counts(archive.get("counts")),
        },
        "warning_count": len(_list(data.get("warnings"))) + len(_list(archive.get("warnings"))),
        "error_count": len(_list(data.get("errors"))) + len(_list(archive.get("errors"))),
        "source_artifacts": _unique_artifacts(data.get("source_artifacts")),
        "cycle_manifest": artifact,
        "warnings": _string_list(data.get("warnings")) + _string_list(archive.get("warnings")),
        "errors": _string_list(data.get("errors")) + _string_list(archive.get("errors")),
    }


def _alert_summary(output_dir: Path, *, base: Path) -> dict[str, Any]:
    state_path = output_dir / ALERT_ARCHIVE_STATE_FILENAME
    archive_path = output_dir / ALERT_ARCHIVE_FILENAME
    state_ref = _safe_ref(state_path, base=base)
    archive_ref = _safe_ref(archive_path, base=base)
    state, state_status, state_message = _read_json_object(state_path)
    sample = _alert_archive_sample(archive_path, base=base, limit=MAX_ALERT_SAMPLE_RECORDS)
    warnings = list(sample["warnings"])
    errors = list(sample["errors"])
    if state_message:
        if state_status == "missing":
            warnings.append(state_message)
        else:
            errors.append(state_message)
    state_counts = _alert_counts(_dict(state.get("counts")))
    fields = {
        "archive": archive_ref,
        "archive_state": state_ref,
        "artifact_type": state.get("artifact_type"),
        "updated_at": state.get("updated_at"),
        "last_cycle_id": state.get("last_cycle_id"),
        "archive_status": state.get("status") or state_status,
        "counts": state_counts,
        "sample_records": sample["records"],
        "sample_truncated": sample["truncated"],
        "sample_record_limit": MAX_ALERT_SAMPLE_RECORDS,
    }
    status = _overall_status([state_status, str(sample["status"])])
    return _component(
        "alert_archive",
        status,
        fields=fields,
        source_artifacts=[state_ref, archive_ref],
        warnings=warnings + _string_list(state.get("warnings")),
        errors=errors + _string_list(state.get("errors")),
    )


def _alert_archive_sample(path: Path, *, base: Path, limit: int) -> dict[str, Any]:
    if not path.exists():
        return {
            "status": "missing",
            "records": [],
            "truncated": False,
            "warnings": [f"{ALERT_ARCHIVE_FILENAME} was not found."],
            "errors": [],
        }
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for index, line in enumerate(handle):
                if index >= limit:
                    return {
                        "status": "available",
                        "records": records,
                        "truncated": True,
                        "warnings": warnings,
                        "errors": [],
                    }
                text = line.strip()
                if not text:
                    continue
                try:
                    loaded = json.loads(text)
                except JSONDecodeError:
                    warnings.append(f"{ALERT_ARCHIVE_FILENAME} line {index + 1} is not valid JSON.")
                    continue
                if isinstance(loaded, dict):
                    records.append(_alert_record_summary(loaded, base=base))
    except OSError as exc:
        return {
            "status": "failed",
            "records": records,
            "truncated": False,
            "warnings": warnings,
            "errors": [f"{ALERT_ARCHIVE_FILENAME} could not be read: {exc}"],
        }
    return {
        "status": "available",
        "records": records,
        "truncated": False,
        "warnings": warnings,
        "errors": [],
    }


def _alert_record_summary(record: dict[str, Any], *, base: Path) -> dict[str, Any]:
    personalized = _dict(record.get("personalized_context"))
    source_run = _dict(record.get("source_run"))
    return {
        "record_id": record.get("record_id"),
        "cycle_id": record.get("cycle_id"),
        "created_at": record.get("created_at"),
        "status": record.get("status"),
        "decision_id": record.get("decision_id"),
        "symbol": record.get("symbol"),
        "timeframe": record.get("timeframe"),
        "priority": record.get("priority"),
        "attention_decision": record.get("attention_decision"),
        "requires_user_attention": record.get("requires_user_attention") is True,
        "suppression_reasons": _string_list(record.get("suppression_reasons")),
        "cooldown_until": record.get("cooldown_until"),
        "source_artifact_count": len(_string_list(record.get("source_artifacts"))),
        "personalized_context_present": personalized.get("present") is True,
        "source_run": {
            "run_id": source_run.get("run_id"),
            "run_manifest": _safe_artifact_ref(source_run.get("run_manifest"), base=base),
        },
    }


def _cooldown_summary(output_dir: Path, *, base: Path) -> dict[str, Any]:
    path = output_dir / ALERT_COOLDOWN_STATE_FILENAME
    artifact = _safe_ref(path, base=base)
    data, status, message = _read_json_object(path)
    if message:
        return _component(
            "cooldown",
            status,
            source_artifacts=[artifact],
            warnings=[message] if status == "missing" else [],
            errors=[message] if status == "failed" else [],
        )
    fields = {
        "artifact": artifact,
        "artifact_type": data.get("artifact_type"),
        "updated_at": data.get("updated_at"),
        "cooldown_seconds": _int(data.get("cooldown_seconds")),
        "record_count": _int(data.get("record_count")),
        "state_path": data.get("state_path"),
    }
    return _component("cooldown", "available", fields=fields, source_artifacts=[artifact])


def _monitor_health_status(fields: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    latest_cycle_status = str(fields.get("latest_cycle_status") or "").lower()
    latest_loop = _dict(fields.get("latest_loop"))
    latest_loop_status = str(latest_loop.get("status") or "").lower()
    warning_count = _int(fields.get("warning_count"))
    error_count = _int(fields.get("error_count"))
    failed_cycle_count = _int(fields.get("failed_cycle_count"))
    warnings: list[str] = []
    errors: list[str] = []
    if latest_cycle_status in FAILED_MONITOR_STATUSES:
        errors.append(f"latest monitor cycle status is {latest_cycle_status}.")
    if latest_loop_status in FAILED_MONITOR_STATUSES:
        errors.append(f"latest monitor loop status is {latest_loop_status}.")
    if error_count:
        errors.append(f"monitor health records {error_count} error(s).")
    if errors:
        return "failed", warnings, errors
    if warning_count:
        warnings.append(f"monitor health records {warning_count} warning(s).")
    if failed_cycle_count:
        warnings.append(f"monitor health records {failed_cycle_count} failed cycle(s).")
    if warnings:
        return "partial", warnings, errors
    return "available", warnings, errors


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


def _read_json_object(path: Path) -> tuple[dict[str, Any], str, str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, "missing", f"{path.name} was not found."
    except OSError as exc:
        return {}, "failed", f"{path.name} could not be read: {exc}."
    except JSONDecodeError as exc:
        return {}, "failed", f"{path.name} is not valid JSON: {exc.msg}."
    if not isinstance(data, dict):
        return {}, "failed", f"{path.name} must be a JSON object."
    return data, "available", None


def _monitor_output_dir(config: dict[str, Any], *, base: Path) -> Path:
    settings = load_monitor_config(config)
    output_dir = Path(settings.output_dir)
    return output_dir if output_dir.is_absolute() else base / output_dir


def _overall_status(statuses: list[str]) -> str:
    normalized = [_normalize_status(status) for status in statuses if status and status != "unknown"]
    if not normalized:
        return "unknown"
    if all(status == "missing" for status in normalized):
        return "missing"
    if any(status == "failed" for status in normalized):
        return "partial" if any(status == "available" for status in normalized) else "failed"
    if any(status == "missing" for status in normalized):
        return "partial" if any(status == "available" for status in normalized) else "missing"
    if all(status == "available" for status in normalized):
        return "available"
    return "partial"


def _normalize_status(status: str) -> str:
    lowered = status.lower()
    if lowered in {"ok", "succeeded", "success"}:
        return "available"
    return lowered


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


def _safe_artifact_ref(value: Any, *, base: Path) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    target = path if path.is_absolute() else base / path
    return _safe_ref(target, base=base)


def _safe_ref(path: Path, *, base: Path) -> str:
    target = path if path.is_absolute() else base / path
    try:
        return target.resolve().relative_to(base.resolve()).as_posix()
    except (OSError, ValueError):
        return EXTERNAL_ARTIFACT_REF


def _config_base(config_path: Path) -> Path:
    parent = config_path.parent
    if str(parent) in {"", "."}:
        return Path.cwd()
    return parent


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
