from __future__ import annotations

from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from halpha.dashboard.settings import sanitize_dashboard_message
from halpha.runtime.monitor_service import (
    MONITOR_SERVICE_NAME,
    MonitorServiceError,
    _monitor_service_config_digest,
    monitor_service_status,
    restart_monitor_service,
    start_monitor_service,
    stop_monitor_service,
)


CORE_SERVICE_NAME = "halpha_core"
DASHBOARD_SERVICE_ROLES = ("core", "monitor")
CONTROLLED_SERVICE_ROLES = ("monitor",)
SERVICE_ACTIONS = ("start", "stop", "restart", "status")
ACTIVE_LIFECYCLE_STATUSES = {"starting", "running", "stop_requested", "unresponsive"}


def dashboard_services_summary(
    config: dict[str, Any] | None,
    *,
    config_path: Path | None,
    dashboard_lifecycle: dict[str, Any] | None,
) -> dict[str, Any]:
    services = {
        "core": _core_service_from_lifecycle(dashboard_lifecycle),
        "monitor": _unconfigured_service("monitor", MONITOR_SERVICE_NAME),
    }
    warnings: list[str] = []
    errors: list[str] = []
    if config_path is not None:
        monitor_digest = _expected_digest(
            config,
            config_path=config_path,
            digest_fn=_monitor_service_config_digest,
        )
        monitor_result = _safe_status(
            "monitor",
            config_path=config_path,
            status_fn=monitor_service_status,
        )
        services["monitor"] = _runtime_service_from_result(
            "monitor",
            MONITOR_SERVICE_NAME,
            monitor_result,
            config_path=config_path,
            expected_config_digest=monitor_digest,
        )
        errors.extend(services["monitor"].get("errors") or [])

    return {
        "schema_version": 1,
        "artifact_type": "dashboard_services",
        "status": "failed" if errors else ("unconfigured" if config_path is None else "available"),
        "services": services,
        "warnings": warnings,
        "errors": errors,
    }


def dashboard_service_action(
    config: dict[str, Any],
    *,
    config_path: Path,
    role: str,
    action: str,
) -> dict[str, Any]:
    role_id = role.strip().lower()
    action_id = action.strip().lower()
    if role_id not in CONTROLLED_SERVICE_ROLES:
        return _blocked_action(role_id, action_id, "core is managed by the local dashboard process; dashboard controls only start, stop, or restart monitor.")
    if action_id not in SERVICE_ACTIONS:
        return _blocked_action(role_id, action_id, f"unsupported service action: {action_id}.")

    expected_digest = _action_expected_digest(config, config_path=config_path, role=role_id)
    try:
        result = _run_service_action(config_path, role=role_id, action=action_id)
    except MonitorServiceError as exc:
        message = _safe_message(str(exc), config_path=config_path)
        status = "conflict" if "different service configuration" in message else "failed"
        service = _latest_service_after_error(
            config_path=config_path,
            role=role_id,
            expected_config_digest=expected_digest,
            error_message=message,
        )
        return {
            "schema_version": 1,
            "artifact_type": "dashboard_service_action",
            "status": status,
            "role": role_id,
            "action": action_id,
            "service": service,
            "warnings": [],
            "errors": [message],
        }

    service = _runtime_service_from_result(
        role_id,
        MONITOR_SERVICE_NAME,
        result,
        config_path=config_path,
        expected_config_digest=expected_digest,
    )
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_service_action",
        "status": service["status"],
        "role": role_id,
        "action": action_id,
        "service": service,
        "warnings": service["warnings"],
        "errors": service["errors"],
    }


def _run_service_action(config_path: Path, *, role: str, action: str) -> dict[str, Any]:
    config_arg = str(config_path)
    if role == "monitor":
        actions = {
            "start": start_monitor_service,
            "stop": stop_monitor_service,
            "restart": restart_monitor_service,
            "status": monitor_service_status,
        }
        return actions[action](config_arg)
    raise MonitorServiceError(f"unsupported service role: {role}.")


def _safe_status(
    role: str,
    *,
    config_path: Path,
    status_fn: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    try:
        return status_fn(str(config_path))
    except Exception as exc:  # pragma: no cover - defensive API boundary
        return {
            "status": "failed",
            "service": MONITOR_SERVICE_NAME,
            "instance_id": None,
            "pid": None,
            "lifecycle": {"role": role, "status": "failed", "instance_id": None, "last_error": {}},
            "warnings": [],
            "errors": [_safe_message(str(exc), config_path=config_path)],
        }


def _runtime_service_from_result(
    role: str,
    service_name: str,
    result: dict[str, Any],
    *,
    config_path: Path,
    expected_config_digest: str | None,
) -> dict[str, Any]:
    lifecycle = result.get("lifecycle") if isinstance(result.get("lifecycle"), dict) else {}
    status = str(result.get("status") or lifecycle.get("status") or "unknown")
    lifecycle_status = str(lifecycle.get("status") or status)
    heartbeat_at = _string_or_none(lifecycle.get("heartbeat_at"))
    started_at = _string_or_none(lifecycle.get("started_at"))
    updated_at = _string_or_none(lifecycle.get("updated_at"))
    stop_requested_at = _string_or_none(lifecycle.get("stop_requested_at"))
    terminal_at = _string_or_none(lifecycle.get("terminal_at"))
    observed_digest = lifecycle.get("config_digest") if isinstance(lifecycle.get("config_digest"), str) else None
    conflict = (
        lifecycle_status in ACTIVE_LIFECYCLE_STATUSES
        and expected_config_digest is not None
        and observed_digest is not None
        and observed_digest != expected_config_digest
    )
    errors = [_safe_message(str(item), config_path=config_path) for item in result.get("errors", []) if item]
    warnings = [_safe_message(str(item), config_path=config_path) for item in result.get("warnings", []) if item]
    return {
        "role": role,
        "service": service_name,
        "status": status,
        "lifecycle_status": lifecycle_status,
        "process_health": _process_health(lifecycle_status),
        "instance_id": result.get("instance_id") or lifecycle.get("instance_id"),
        "pid": result.get("pid") if isinstance(result.get("pid"), int) else lifecycle.get("pid"),
        "config_ref": lifecycle.get("config_ref"),
        "config_conflict": conflict,
        "heartbeat_at": heartbeat_at,
        "heartbeat_age_seconds": _heartbeat_age_seconds(heartbeat_at),
        "heartbeat_freshness": _heartbeat_freshness(lifecycle_status, heartbeat_at),
        "started_at": started_at,
        "updated_at": updated_at,
        "stop_requested_at": stop_requested_at,
        "terminal_at": terminal_at,
        "last_error": _safe_last_error(lifecycle.get("last_error"), config_path=config_path),
        "actionable": _actionable_summary(lifecycle_status, conflict),
        "warnings": warnings,
        "errors": errors,
    }


def _core_service_from_lifecycle(lifecycle: dict[str, Any] | None) -> dict[str, Any]:
    payload = lifecycle if isinstance(lifecycle, dict) else {}
    status = str(payload.get("status") or "unmanaged")
    heartbeat_at = _string_or_none(payload.get("heartbeat_at"))
    return {
        "role": "core",
        "service": CORE_SERVICE_NAME,
        "status": status,
        "lifecycle_status": status,
        "process_health": _process_health(status),
        "instance_id": payload.get("instance_id") if isinstance(payload.get("instance_id"), str) else None,
        "pid": payload.get("pid") if isinstance(payload.get("pid"), int) else None,
        "config_ref": payload.get("config_ref") if isinstance(payload.get("config_ref"), str) else None,
        "config_conflict": False,
        "heartbeat_at": heartbeat_at,
        "heartbeat_age_seconds": _heartbeat_age_seconds(heartbeat_at),
        "heartbeat_freshness": _heartbeat_freshness(status, heartbeat_at),
        "started_at": _string_or_none(payload.get("started_at")),
        "updated_at": _string_or_none(payload.get("updated_at")),
        "stop_requested_at": _string_or_none(payload.get("stop_requested_at")),
        "terminal_at": _string_or_none(payload.get("terminal_at")),
        "last_error": {},
        "actionable": "core service is managed by the current process." if status == "unmanaged" else "",
        "warnings": [],
        "errors": [],
    }


def _unconfigured_service(role: str, service_name: str) -> dict[str, Any]:
    return {
        "role": role,
        "service": service_name,
        "status": "unconfigured",
        "lifecycle_status": "unconfigured",
        "process_health": "unconfigured",
        "instance_id": None,
        "pid": None,
        "config_ref": None,
        "config_conflict": False,
        "heartbeat_at": None,
        "heartbeat_age_seconds": None,
        "heartbeat_freshness": "missing",
        "started_at": None,
        "updated_at": None,
        "stop_requested_at": None,
        "terminal_at": None,
        "last_error": {},
        "actionable": "load a dashboard config before controlling this service.",
        "warnings": [],
        "errors": [],
    }


def _latest_service_after_error(
    *,
    config_path: Path,
    role: str,
    expected_config_digest: str | None,
    error_message: str,
) -> dict[str, Any]:
    with suppress(Exception):
        return _runtime_service_from_result(
            role,
            MONITOR_SERVICE_NAME,
            monitor_service_status(str(config_path)),
            config_path=config_path,
            expected_config_digest=expected_config_digest,
        )
    service = _unconfigured_service(role, MONITOR_SERVICE_NAME)
    service["status"] = "failed"
    service["lifecycle_status"] = "failed"
    service["process_health"] = "failed"
    service["errors"] = [error_message]
    return service


def _blocked_action(role: str, action: str, reason: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "dashboard_service_action",
        "status": "blocked",
        "role": role,
        "action": action,
        "service": None,
        "warnings": [reason],
        "errors": [],
    }


def _expected_digest(
    config: dict[str, Any] | None,
    *,
    config_path: Path,
    digest_fn: Callable[[dict[str, Any], Any], str],
) -> str | None:
    if not isinstance(config, dict):
        return None
    with suppress(Exception):
        return digest_fn(config, config_path=config_path)
    return None


def _action_expected_digest(config: dict[str, Any], *, config_path: Path, role: str) -> str | None:
    if role == "monitor":
        return _expected_digest(config, config_path=config_path, digest_fn=_monitor_service_config_digest)
    return None


def _safe_last_error(value: Any, *, config_path: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    for key, item in value.items():
        if key == "message" and isinstance(item, str):
            result[key] = _safe_message(item, config_path=config_path)
        elif isinstance(item, (str, int, float, bool)) or item is None:
            result[key] = item
    return result


def _safe_message(message: str, *, config_path: Path) -> str:
    return sanitize_dashboard_message(message, config_path=config_path)[:500]


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _heartbeat_age_seconds(value: str | None) -> int | None:
    timestamp = _parse_timestamp(value)
    if timestamp is None:
        return None
    age = datetime.now(timezone.utc) - timestamp
    return max(0, int(age.total_seconds()))


def _heartbeat_freshness(status: str, value: str | None) -> str:
    if status in {"unconfigured", "not_found", "stopped", "failed", "crashed", "stale"}:
        return "not_running"
    age = _heartbeat_age_seconds(value)
    if age is None:
        return "missing"
    return "fresh" if age <= 60 else "stale"


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _process_health(status: str) -> str:
    if status in {"started", "existing"}:
        return "running"
    if status in {"running", "starting", "stop_requested", "unresponsive", "stale"}:
        return status
    if status in {"stopped", "failed", "crashed", "not_found", "unconfigured", "unmanaged"}:
        return status
    return "unknown"


def _actionable_summary(status: str, config_conflict: bool) -> str:
    if config_conflict:
        return "running instance uses a different active config; stop it or switch config before starting another instance."
    if status in {"not_found", "stale"}:
        return "service is not running; start it when needed."
    if status in {"stopped", "failed", "crashed"}:
        return "service is terminal; use restart after confirming the instance id."
    if status == "stop_requested":
        return "service is stopping; wait for terminal status before starting again."
    if status == "unresponsive":
        return "heartbeat is stale while the lock is held; inspect or stop before starting another service."
    return ""
