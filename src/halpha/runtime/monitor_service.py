from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from halpha.config import load_config
from halpha.dashboard.settings import dashboard_config_ref, sanitize_dashboard_message
from halpha.monitor.monitoring import (
    Sleeper,
    load_monitor_config,
)
from halpha.runtime.process_creation import hidden_subprocess_kwargs
from halpha.monitor.state_store import MonitorStateRepository
from halpha.runtime.service_lifecycle import ServiceLifecycleRepository, ServiceLifecycleResult
from halpha.storage import artifact_base, display_path


MONITOR_SERVICE_ROLE = "monitor"
MONITOR_SERVICE_NAME = "halpha_monitor"
CORE_SERVICE_ROLE = "core"
CORE_SERVICE_NAME = "halpha_core"
MONITOR_CONTROL_POLL_SECONDS = 0.25
MONITOR_START_WAIT_SECONDS = 10.0
MONITOR_STOP_WAIT_SECONDS = 5.0
CORE_HEALTH_TIMEOUT_SECONDS = 0.75
CORE_START_TIMEOUT_SECONDS = 15.0


class MonitorServiceError(Exception):
    def __init__(self, message: str, *, exit_code: int = 2) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class MonitorCoreClientError(Exception):
    pass


@dataclass(frozen=True)
class MonitorStartupConfig:
    config: dict[str, Any]
    config_path: Path


class LocalCoreServiceClient:
    def __init__(self, *, config_path: Path, repository: ServiceLifecycleRepository | None = None) -> None:
        self.config_path = Path(config_path)
        self.repository = repository or ServiceLifecycleRepository(runtime_root=artifact_base(self.config_path))

    def ensure_running(self) -> dict[str, Any]:
        lifecycle = self.repository.inspect(CORE_SERVICE_ROLE)
        if lifecycle.status == "running" and self._health_available(lifecycle):
            return _core_lifecycle_summary("running", lifecycle)
        if lifecycle.status in {"not_found", "stale", "stopped", "failed", "crashed"}:
            self._start_core_service()
            lifecycle = self.repository.inspect(CORE_SERVICE_ROLE)
            if lifecycle.status == "running" and self._health_available(lifecycle):
                return _core_lifecycle_summary("started", lifecycle)
        if lifecycle.status == "running":
            raise MonitorCoreClientError("core service lifecycle is running, but the health endpoint is unavailable.")
        raise MonitorCoreClientError(f"core service is not ready: {lifecycle.status}.")

    def _start_core_service(self) -> None:
        command = [sys.executable, "-m", "halpha", "dashboard", "start", "--config", str(self.config_path)]
        try:
            completed = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=Path.cwd(),
                timeout=CORE_START_TIMEOUT_SECONDS,
                check=False,
                **hidden_subprocess_kwargs(new_process_group=True),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise MonitorCoreClientError("core service could not be started by monitor supervision.") from exc
        if completed.returncode != 0:
            raise MonitorCoreClientError("core service start command failed.")

    def _health_available(self, lifecycle: ServiceLifecycleResult) -> bool:
        health_url = _core_health_url(lifecycle)
        if health_url is None:
            return False
        try:
            payload = _request_json("GET", health_url, None, timeout=CORE_HEALTH_TIMEOUT_SECONDS)
        except MonitorCoreClientError:
            return False
        return payload.get("service") == CORE_SERVICE_NAME and payload.get("status") in {"ok", "unconfigured"}


def load_monitor_startup_config(config_arg: str) -> MonitorStartupConfig:
    config_path = Path(config_arg)
    return MonitorStartupConfig(config=load_config(config_path), config_path=config_path)


def run_monitor_service(
    config: dict[str, Any],
    *,
    config_path: Path,
    restart_from_instance_id: str | None = None,
    max_cycles: int | None = None,
    sleeper: Sleeper = time.sleep,
    core_client: LocalCoreServiceClient | None = None,
) -> None:
    repository = _monitor_lifecycle_repository(config_path)
    state_repository = MonitorStateRepository(config_path=config_path)
    service_config = _monitor_service_runtime_config(config)
    settings = load_monitor_config(service_config)
    output_ref = _monitor_output_ref(settings.output_dir, config_path=config_path)
    config_digest = _monitor_service_config_digest(config, config_path=config_path)
    config_ref = dashboard_config_ref(config_path)
    if restart_from_instance_id:
        result, ownership = repository.attempt_restart_ownership(
            MONITOR_SERVICE_ROLE,
            previous_instance_id=restart_from_instance_id,
            config_ref=config_ref,
            config_digest=config_digest,
            endpoint=_monitor_endpoint_metadata(),
        )
    else:
        result, ownership = repository.attempt_start_ownership(
            MONITOR_SERVICE_ROLE,
            config_ref=config_ref,
            config_digest=config_digest,
            endpoint=_monitor_endpoint_metadata(),
        )
    if ownership is None or result.instance_id is None:
        raise MonitorServiceError(_monitor_lifecycle_start_message(result))

    instance_id = result.instance_id
    terminal_status = "stopped"
    terminal_error: str | None = None
    completed_cycles = 0
    consecutive_failures = 0
    latest_cycle_id: str | None = None
    latest_run_id: str | None = None
    latest_run_manifest: str | None = None
    latest_last_error: dict[str, Any] = {}
    client = core_client or LocalCoreServiceClient(config_path=config_path)
    try:
        repository.register_started(MONITOR_SERVICE_ROLE, instance_id=instance_id, endpoint=_monitor_endpoint_metadata())
        _save_service_health(
            state_repository,
            monitor_output_dir=output_ref,
            instance_id=instance_id,
            status="running",
        )
        while True:
            if _stop_requested(repository, instance_id):
                break
            repository.update_heartbeat(MONITOR_SERVICE_ROLE, instance_id=instance_id)
            _save_service_health(
                state_repository,
                monitor_output_dir=output_ref,
                instance_id=instance_id,
                status="checking_core",
                current_cycle_id=None,
                latest_cycle_id=latest_cycle_id,
                latest_run_id=latest_run_id,
                latest_run_manifest=latest_run_manifest,
                consecutive_failures=consecutive_failures,
            )
            completed_cycles += 1
            wait_seconds = settings.interval_seconds
            next_retry_at = None
            last_error: dict[str, Any] = {}
            try:
                core_status = client.ensure_running()
                consecutive_failures = 0
                latest_last_error = {}
                status = "waiting"
                warnings = _monitor_supervision_warnings(core_status=core_status)
                errors: list[str] = []
            except Exception as exc:
                consecutive_failures += 1
                wait_seconds = _monitor_backoff_seconds(settings.interval_seconds, settings.failure_backoff_max_seconds, consecutive_failures)
                next_retry_at = _future_timestamp(wait_seconds)
                last_error = _last_error(str(exc) or "monitor supervision failed")
                latest_last_error = last_error
                status = "retry_waiting"
                warnings = []
                errors = [last_error["message"]] if last_error else []
            _save_service_health(
                state_repository,
                monitor_output_dir=output_ref,
                instance_id=instance_id,
                status=status,
                current_cycle_id=None,
                latest_cycle_id=latest_cycle_id,
                latest_run_id=latest_run_id,
                latest_run_manifest=latest_run_manifest,
                consecutive_failures=consecutive_failures,
                next_retry_at=next_retry_at,
                last_error=last_error,
                warnings=warnings,
                errors=errors,
                warning_count=len(warnings),
                error_count=len(errors),
            )
            if max_cycles is not None and completed_cycles >= max_cycles:
                break
            if _wait_for_stop_or_timeout(repository, instance_id, wait_seconds, sleeper=sleeper):
                break
    except Exception as exc:
        terminal_status = "failed"
        terminal_error = str(exc)
        _save_service_health(
            state_repository,
            monitor_output_dir=output_ref,
            instance_id=instance_id,
            status="failed",
            current_cycle_id=None,
            latest_cycle_id=latest_cycle_id,
            latest_run_id=latest_run_id,
            latest_run_manifest=latest_run_manifest,
            consecutive_failures=consecutive_failures,
            last_error=_last_error(terminal_error),
            errors=[_last_error(terminal_error)["message"]],
            error_count=1,
        )
        raise
    finally:
        try:
            _save_service_health(
                state_repository,
                monitor_output_dir=output_ref,
                instance_id=instance_id,
                status=terminal_status,
                current_cycle_id=None,
                latest_cycle_id=latest_cycle_id,
                latest_run_id=latest_run_id,
                latest_run_manifest=latest_run_manifest,
                consecutive_failures=consecutive_failures,
                last_error=_last_error(terminal_error) if terminal_error else latest_last_error,
                errors=[_last_error(terminal_error)["message"]]
                if terminal_error
                else ([latest_last_error["message"]] if latest_last_error else []),
                error_count=1 if terminal_error or latest_last_error else 0,
            )
        finally:
            try:
                repository.record_terminal_exit(
                    MONITOR_SERVICE_ROLE,
                    instance_id=instance_id,
                    status=terminal_status,
                    exit_code=0 if terminal_status == "stopped" else 1,
                    error=terminal_error,
                )
            finally:
                ownership.release()


def start_monitor_service(
    config_arg: str,
    *,
    restart_from_instance_id: str | None = None,
) -> dict[str, Any]:
    startup = load_monitor_startup_config(config_arg)
    repository = _monitor_lifecycle_repository(startup.config_path)
    config_digest = _monitor_service_config_digest(startup.config, config_path=startup.config_path)
    start_mutex = repository.acquire_start_mutex(MONITOR_SERVICE_ROLE)
    if start_mutex is None:
        return _wait_for_duplicate_monitor_start(
            repository,
            config_digest=config_digest,
            restart_from_instance_id=restart_from_instance_id,
            timeout_seconds=MONITOR_START_WAIT_SECONDS,
        )

    try:
        lifecycle = repository.inspect(MONITOR_SERVICE_ROLE)
        blocking = _monitor_start_blocking_result(
            lifecycle,
            config_digest=config_digest,
            restart_from_instance_id=restart_from_instance_id,
        )
        if blocking is not None:
            if blocking["status"] == "existing":
                return blocking
            if blocking["status"] == "starting":
                return _wait_for_existing_monitor_service(
                    repository,
                    config_digest=config_digest,
                    timeout_seconds=MONITOR_START_WAIT_SECONDS,
                )
            raise MonitorServiceError(str(blocking["reason"]))

        process = _launch_monitor_service_process(
            config_arg,
            restart_from_instance_id=restart_from_instance_id,
        )
        return _wait_for_monitor_service_start(
            process,
            repository=repository,
            config_digest=config_digest,
            timeout_seconds=MONITOR_START_WAIT_SECONDS,
        )
    finally:
        start_mutex.release()


def monitor_service_status(config_arg: str) -> dict[str, Any]:
    repository = _monitor_lifecycle_repository(Path(config_arg))
    lifecycle = repository.inspect(MONITOR_SERVICE_ROLE)
    return _monitor_service_result(lifecycle.status, lifecycle=lifecycle)


def stop_monitor_service(config_arg: str) -> dict[str, Any]:
    repository = _monitor_lifecycle_repository(Path(config_arg))
    lifecycle = repository.inspect(MONITOR_SERVICE_ROLE)
    if lifecycle.instance_id is None or lifecycle.status in {"not_found", "stale", "stopped", "failed", "crashed"}:
        return _monitor_service_result(lifecycle.status, lifecycle=lifecycle)
    requested = repository.request_graceful_stop(MONITOR_SERVICE_ROLE, instance_id=lifecycle.instance_id)
    stopped = _wait_for_monitor_service_stop(
        repository,
        previous_instance_id=lifecycle.instance_id,
        timeout_seconds=MONITOR_STOP_WAIT_SECONDS,
    )
    if stopped is not None:
        return stopped
    return {
        "status": "stop_requested",
        "instance_id": lifecycle.instance_id,
        "pid": _monitor_lifecycle_pid(lifecycle),
        "service": MONITOR_SERVICE_NAME,
        "lifecycle": _monitor_lifecycle_payload(requested),
        "warnings": ["monitor stop was requested, but the service has not exited yet."],
        "errors": [],
    }


def restart_monitor_service(config_arg: str) -> dict[str, Any]:
    startup = load_monitor_startup_config(config_arg)
    repository = _monitor_lifecycle_repository(startup.config_path)
    lifecycle = repository.inspect(MONITOR_SERVICE_ROLE)
    restart_from_instance_id = lifecycle.instance_id
    if lifecycle.status in {"running", "starting", "stop_requested", "unresponsive"} and lifecycle.instance_id:
        stopped = stop_monitor_service(config_arg)
        if stopped.get("status") not in {"stopped", "failed", "crashed", "stale", "not_found"}:
            return stopped
    if not restart_from_instance_id:
        return start_monitor_service(config_arg)
    return start_monitor_service(config_arg, restart_from_instance_id=restart_from_instance_id)


def _monitor_lifecycle_repository(config_path: Path) -> ServiceLifecycleRepository:
    return ServiceLifecycleRepository(runtime_root=artifact_base(config_path))


def _core_lifecycle_summary(status: str, lifecycle: ServiceLifecycleResult) -> dict[str, Any]:
    state = lifecycle.state if isinstance(lifecycle.state, dict) else {}
    return {
        "status": status,
        "lifecycle_status": lifecycle.status,
        "instance_id": lifecycle.instance_id,
        "heartbeat_at": state.get("heartbeat_at"),
        "endpoint": state.get("endpoint") if isinstance(state.get("endpoint"), dict) else {},
    }


def _core_health_url(lifecycle: ServiceLifecycleResult) -> str | None:
    state = lifecycle.state if isinstance(lifecycle.state, dict) else {}
    endpoint = state.get("endpoint") if isinstance(state.get("endpoint"), dict) else {}
    value = endpoint.get("health_url")
    return value if isinstance(value, str) and value.startswith("http://") else None


def _request_json(method: str, url: str, payload: dict[str, Any] | None, *, timeout: float) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        url,
        data=data,
        method=method,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read(65_536)
    except (HTTPError, OSError, TimeoutError, URLError, ValueError) as exc:
        raise MonitorCoreClientError("core service API request failed.") from exc
    try:
        loaded = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise MonitorCoreClientError("core service API returned invalid JSON.") from exc
    if not isinstance(loaded, dict):
        raise MonitorCoreClientError("core service API returned an invalid payload.")
    return loaded


def _monitor_supervision_warnings(*, core_status: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if core_status.get("status") == "started":
        warnings.append("core service was started by monitor supervision.")
    return warnings[:10]


def _monitor_service_config_digest(config: dict[str, Any], *, config_path: Path) -> str:
    material = {
        "service": MONITOR_SERVICE_NAME,
        "config": config if isinstance(config, dict) else {},
        "config_ref": dashboard_config_ref(config_path),
        "service_contract": "monitor_service_v1",
    }
    payload = json.dumps(material, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _monitor_endpoint_metadata() -> dict[str, Any]:
    return {"service": MONITOR_SERVICE_NAME}


def _monitor_lifecycle_start_message(result: ServiceLifecycleResult) -> str:
    if result.reason:
        return result.reason
    return f"monitor service could not start because lifecycle status is {result.status}."


def _monitor_start_blocking_result(
    lifecycle: ServiceLifecycleResult,
    *,
    config_digest: str,
    restart_from_instance_id: str | None,
) -> dict[str, Any] | None:
    if lifecycle.status in {"not_found", "stale"}:
        return None
    if lifecycle.status in {"stopped", "failed", "crashed"}:
        if restart_from_instance_id and lifecycle.instance_id == restart_from_instance_id:
            return None
        return {
            "status": lifecycle.status,
            "reason": "monitor service is in a terminal state; use monitor restart after confirming the instance id.",
            "lifecycle": _monitor_lifecycle_payload(lifecycle),
        }
    state = lifecycle.state if isinstance(lifecycle.state, dict) else {}
    if lifecycle.status == "unresponsive":
        return {
            "status": "unresponsive",
            "reason": "monitor service lock is held but heartbeat is stale; stop or inspect it before starting another service.",
            "lifecycle": _monitor_lifecycle_payload(lifecycle),
        }
    if lifecycle.status not in {"running", "starting", "stop_requested"}:
        return None
    if state.get("config_digest") != config_digest:
        return {
            "status": "conflict",
            "reason": "monitor service is already active for a different service configuration.",
            "lifecycle": _monitor_lifecycle_payload(lifecycle),
        }
    if lifecycle.status == "starting":
        return {
            "status": "starting",
            "reason": "monitor service is already starting.",
            "lifecycle": _monitor_lifecycle_payload(lifecycle),
        }
    if lifecycle.status == "stop_requested":
        return {
            "status": "stop_requested",
            "reason": "monitor service is stopping; wait for it to exit before starting another service.",
            "lifecycle": _monitor_lifecycle_payload(lifecycle),
        }
    return _monitor_service_result("existing", lifecycle=lifecycle)


def _launch_monitor_service_process(
    config_arg: str,
    *,
    restart_from_instance_id: str | None,
) -> subprocess.Popen[Any]:
    command = [sys.executable, "-m", "halpha", "monitor", "service", "--config", config_arg]
    if restart_from_instance_id:
        command.extend(["--restart-from-instance-id", restart_from_instance_id])
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "cwd": Path.cwd(),
    }
    if sys.platform == "win32":
        kwargs.update(hidden_subprocess_kwargs(new_process_group=True, detached=True))
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(command, **kwargs)


def _wait_for_monitor_service_start(
    process: subprocess.Popen[Any],
    *,
    repository: ServiceLifecycleRepository,
    config_digest: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        lifecycle = repository.inspect(MONITOR_SERVICE_ROLE)
        if lifecycle.status == "running" and _lifecycle_config_digest(lifecycle) == config_digest:
            return _monitor_service_result("started", lifecycle=lifecycle)
        if process.poll() is not None:
            raise MonitorServiceError("monitor service exited before it registered a running lifecycle state.")
        time.sleep(MONITOR_CONTROL_POLL_SECONDS)
    raise MonitorServiceError("monitor service did not become running before the startup timeout.")


def _wait_for_duplicate_monitor_start(
    repository: ServiceLifecycleRepository,
    *,
    config_digest: str,
    restart_from_instance_id: str | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        lifecycle = repository.inspect(MONITOR_SERVICE_ROLE)
        blocking = _monitor_start_blocking_result(
            lifecycle,
            config_digest=config_digest,
            restart_from_instance_id=restart_from_instance_id,
        )
        if blocking is not None:
            if blocking["status"] == "existing":
                return blocking
            if blocking["status"] == "starting":
                time.sleep(MONITOR_CONTROL_POLL_SECONDS)
                continue
            raise MonitorServiceError(str(blocking["reason"]))
        time.sleep(MONITOR_CONTROL_POLL_SECONDS)
    raise MonitorServiceError("monitor service start is already in progress; retry after it finishes or run monitor status.")


def _wait_for_existing_monitor_service(
    repository: ServiceLifecycleRepository,
    *,
    config_digest: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        lifecycle = repository.inspect(MONITOR_SERVICE_ROLE)
        if lifecycle.status == "running" and _lifecycle_config_digest(lifecycle) == config_digest:
            return _monitor_service_result("existing", lifecycle=lifecycle)
        time.sleep(MONITOR_CONTROL_POLL_SECONDS)
    raise MonitorServiceError("monitor service is starting, but it is not running yet.")


def _wait_for_monitor_service_stop(
    repository: ServiceLifecycleRepository,
    *,
    previous_instance_id: str,
    timeout_seconds: float,
) -> dict[str, Any] | None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        lifecycle = repository.inspect(MONITOR_SERVICE_ROLE)
        if lifecycle.instance_id == previous_instance_id and lifecycle.status in {"stopped", "failed", "crashed", "stale"}:
            return _monitor_service_result(lifecycle.status, lifecycle=lifecycle)
        time.sleep(MONITOR_CONTROL_POLL_SECONDS)
    return None


def _monitor_service_result(status: str, *, lifecycle: ServiceLifecycleResult) -> dict[str, Any]:
    return {
        "status": status,
        "service": MONITOR_SERVICE_NAME,
        "instance_id": lifecycle.instance_id,
        "pid": _monitor_lifecycle_pid(lifecycle),
        "lifecycle": _monitor_lifecycle_payload(lifecycle),
        "warnings": [],
        "errors": [],
    }


def _monitor_lifecycle_payload(lifecycle: ServiceLifecycleResult) -> dict[str, Any]:
    state = lifecycle.state if isinstance(lifecycle.state, dict) else {}
    return {
        "status": lifecycle.status,
        "role": lifecycle.role,
        "instance_id": lifecycle.instance_id,
        "owns_lock": lifecycle.owns_lock,
        "reason": lifecycle.reason,
        "pid": _monitor_lifecycle_pid(lifecycle),
        "config_ref": state.get("config_ref"),
        "config_digest": state.get("config_digest"),
        "started_at": state.get("started_at"),
        "updated_at": state.get("updated_at"),
        "heartbeat_at": state.get("heartbeat_at"),
        "stop_requested_at": state.get("stop_requested_at"),
        "terminal_at": state.get("terminal_at"),
        "last_error": state.get("last_error") if isinstance(state.get("last_error"), dict) else {},
    }


def _monitor_lifecycle_pid(lifecycle: ServiceLifecycleResult) -> int | None:
    state = lifecycle.state if isinstance(lifecycle.state, dict) else {}
    pid = state.get("pid")
    if isinstance(pid, bool):
        return None
    if isinstance(pid, int) and pid > 0:
        return pid
    return None


def _lifecycle_config_digest(lifecycle: ServiceLifecycleResult) -> str | None:
    state = lifecycle.state if isinstance(lifecycle.state, dict) else {}
    value = state.get("config_digest")
    return value if isinstance(value, str) else None


def _stop_requested(repository: ServiceLifecycleRepository, instance_id: str) -> bool:
    return repository.observe_stop_request(MONITOR_SERVICE_ROLE, instance_id=instance_id).requested


def _wait_for_stop_or_timeout(
    repository: ServiceLifecycleRepository,
    instance_id: str,
    seconds: float,
    *,
    sleeper: Sleeper,
) -> bool:
    remaining = max(0.0, seconds)
    while remaining > 0.0:
        if _stop_requested(repository, instance_id):
            return True
        repository.update_heartbeat(MONITOR_SERVICE_ROLE, instance_id=instance_id)
        sleep_seconds = min(MONITOR_CONTROL_POLL_SECONDS, remaining)
        sleeper(sleep_seconds)
        remaining -= sleep_seconds
    return _stop_requested(repository, instance_id)


def _save_service_health(
    repository: MonitorStateRepository,
    *,
    monitor_output_dir: str,
    instance_id: str,
    status: str,
    current_cycle_id: str | None = None,
    latest_cycle_id: str | None = None,
    latest_run_id: str | None = None,
    latest_run_manifest: str | None = None,
    consecutive_failures: int = 0,
    next_retry_at: str | None = None,
    last_error: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    warning_count: int = 0,
    error_count: int = 0,
) -> None:
    repository.save_service_health(
        {
            "service_instance_id": instance_id,
            "status": status,
            "current_cycle_id": current_cycle_id,
            "latest_cycle_id": latest_cycle_id,
            "latest_run_id": latest_run_id,
            "latest_run_manifest": latest_run_manifest,
            "consecutive_failures": consecutive_failures,
            "next_retry_at": next_retry_at,
            "last_error": last_error or {},
            "warning_count": warning_count,
            "error_count": error_count,
            "warnings": warnings or [],
            "errors": errors or [],
        },
        monitor_output_dir=monitor_output_dir,
        updated_at=_utc_timestamp(),
    )


def _monitor_service_runtime_config(config: dict[str, Any]) -> dict[str, Any]:
    service_config = deepcopy(config if isinstance(config, dict) else {})
    monitor = service_config.get("monitor")
    if not isinstance(monitor, dict):
        monitor = {}
        service_config["monitor"] = monitor
    monitor["no_codex"] = True
    return service_config


def _monitor_backoff_seconds(interval_seconds: int, max_seconds: int, consecutive_failures: int) -> float:
    exponent = max(0, consecutive_failures - 1)
    return float(min(max_seconds, interval_seconds * (2**exponent)))


def _monitor_output_ref(output_dir: Path, *, config_path: Path) -> str:
    base = artifact_base(config_path)
    resolved = output_dir if output_dir.is_absolute() else base / output_dir
    return display_path(resolved, base=base)


def _future_timestamp(seconds: float) -> str:
    return _utc_timestamp(datetime.now(timezone.utc) + timedelta(seconds=max(0.0, seconds)))


def _utc_timestamp(value: datetime | None = None) -> str:
    timestamp = value or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _last_error(message: str | None) -> dict[str, Any]:
    text = str(message or "").strip()
    if not text:
        return {}
    lowered = text.lower()
    private_markers = ("\\", "/", "://", "token", "secret", "cookie", "proxy", "password")
    if any(marker in lowered for marker in private_markers):
        return {
            "message": "monitor service error redacted; inspect local logs.",
            "private_values_embedded": False,
        }
    return {"message": text[:500], "private_values_embedded": False}


def monitor_service_error_message(message: str, *, config_path: Path) -> str:
    return sanitize_dashboard_message(message, config_path=config_path)
