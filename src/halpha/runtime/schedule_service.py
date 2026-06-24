from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from halpha.config import load_config
from halpha.dashboard.schedule import DashboardScheduleManager
from halpha.dashboard.settings import dashboard_config_ref, sanitize_dashboard_message
from halpha.runtime.command_jobs import CommandJobManager
from halpha.runtime.service_lifecycle import ServiceLifecycleRepository, ServiceLifecycleResult
from halpha.storage import artifact_base


SCHEDULE_SERVICE_ROLE = "schedule"
SCHEDULE_SERVICE_NAME = "halpha_schedule"
SCHEDULE_CONTROL_POLL_SECONDS = 0.25
SCHEDULE_MAX_WAIT_SECONDS = 30.0
SCHEDULE_START_WAIT_SECONDS = 10.0
SCHEDULE_STOP_WAIT_SECONDS = 5.0


class ScheduleServiceError(Exception):
    def __init__(self, message: str, *, exit_code: int = 2) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass(frozen=True)
class ScheduleStartupConfig:
    config: dict[str, Any]
    config_path: Path


def load_schedule_startup_config(config_arg: str) -> ScheduleStartupConfig:
    config_path = Path(config_arg)
    return ScheduleStartupConfig(config=load_config(config_path), config_path=config_path)


def run_schedule_service(
    config: dict[str, Any],
    *,
    config_path: Path,
    restart_from_instance_id: str | None = None,
    max_cycles: int | None = None,
) -> None:
    repository = _schedule_lifecycle_repository(config_path)
    config_digest = _schedule_service_config_digest(config, config_path=config_path)
    config_ref = dashboard_config_ref(config_path)
    if restart_from_instance_id:
        result, ownership = repository.attempt_restart_ownership(
            SCHEDULE_SERVICE_ROLE,
            previous_instance_id=restart_from_instance_id,
            config_ref=config_ref,
            config_digest=config_digest,
            endpoint=_schedule_endpoint_metadata(),
        )
    else:
        result, ownership = repository.attempt_start_ownership(
            SCHEDULE_SERVICE_ROLE,
            config_ref=config_ref,
            config_digest=config_digest,
            endpoint=_schedule_endpoint_metadata(),
        )
    if ownership is None or result.instance_id is None:
        raise ScheduleServiceError(_schedule_lifecycle_start_message(result))

    job_manager = CommandJobManager(
        config,
        config_path=config_path,
        requested_by="Schedule",
        requester={
            "source": "schedule_service",
            "service_instance_id": result.instance_id,
        },
    )
    schedule_manager = DashboardScheduleManager(config, config_path=config_path, job_manager=job_manager)
    terminal_status = "stopped"
    terminal_error: str | None = None
    completed_cycles = 0
    try:
        repository.register_started(
            SCHEDULE_SERVICE_ROLE,
            instance_id=result.instance_id,
            endpoint=_schedule_endpoint_metadata(),
        )
        while True:
            if _stop_requested(repository, result.instance_id):
                break
            with suppress(Exception):
                repository.update_heartbeat(SCHEDULE_SERVICE_ROLE, instance_id=result.instance_id)
            with suppress(Exception):
                schedule_manager.dispatch_due_daily_report()
            completed_cycles += 1
            if max_cycles is not None and completed_cycles >= max_cycles:
                break
            wait_seconds = min(SCHEDULE_MAX_WAIT_SECONDS, max(SCHEDULE_CONTROL_POLL_SECONDS, schedule_manager.next_due_seconds()))
            if _wait_for_stop_or_timeout(repository, result.instance_id, wait_seconds):
                break
    except BaseException as exc:
        terminal_status = "failed"
        terminal_error = str(exc)
        raise
    finally:
        with suppress(Exception):
            repository.record_terminal_exit(
                SCHEDULE_SERVICE_ROLE,
                instance_id=result.instance_id,
                status=terminal_status,
                exit_code=0 if terminal_status == "stopped" else 1,
                error=terminal_error,
            )
        ownership.release()


def start_schedule_service(
    config_arg: str,
    *,
    restart_from_instance_id: str | None = None,
) -> dict[str, Any]:
    startup = load_schedule_startup_config(config_arg)
    repository = _schedule_lifecycle_repository(startup.config_path)
    config_digest = _schedule_service_config_digest(startup.config, config_path=startup.config_path)
    lifecycle = repository.inspect(SCHEDULE_SERVICE_ROLE)
    blocking = _schedule_start_blocking_result(
        lifecycle,
        config_digest=config_digest,
        restart_from_instance_id=restart_from_instance_id,
    )
    if blocking is not None:
        if blocking["status"] == "existing":
            return blocking
        if blocking["status"] == "starting":
            return _wait_for_existing_schedule_service(
                repository,
                config_digest=config_digest,
                timeout_seconds=SCHEDULE_START_WAIT_SECONDS,
            )
        raise ScheduleServiceError(str(blocking["reason"]))

    process = _launch_schedule_service_process(
        config_arg,
        restart_from_instance_id=restart_from_instance_id,
    )
    return _wait_for_schedule_service_start(
        process,
        repository=repository,
        config_digest=config_digest,
        timeout_seconds=SCHEDULE_START_WAIT_SECONDS,
    )


def schedule_service_status(config_arg: str) -> dict[str, Any]:
    repository = _schedule_lifecycle_repository(Path(config_arg))
    lifecycle = repository.inspect(SCHEDULE_SERVICE_ROLE)
    return _schedule_service_result(lifecycle.status, lifecycle=lifecycle)


def stop_schedule_service(config_arg: str) -> dict[str, Any]:
    repository = _schedule_lifecycle_repository(Path(config_arg))
    lifecycle = repository.inspect(SCHEDULE_SERVICE_ROLE)
    if lifecycle.instance_id is None or lifecycle.status in {"not_found", "stale", "stopped", "failed", "crashed"}:
        return _schedule_service_result(lifecycle.status, lifecycle=lifecycle)
    requested = repository.request_graceful_stop(SCHEDULE_SERVICE_ROLE, instance_id=lifecycle.instance_id)
    stopped = _wait_for_schedule_service_stop(
        repository,
        previous_instance_id=lifecycle.instance_id,
        timeout_seconds=SCHEDULE_STOP_WAIT_SECONDS,
    )
    if stopped is not None:
        return stopped
    return {
        "status": "stop_requested",
        "instance_id": lifecycle.instance_id,
        "pid": _schedule_lifecycle_pid(lifecycle),
        "service": SCHEDULE_SERVICE_NAME,
        "lifecycle": _schedule_lifecycle_payload(requested),
        "warnings": ["schedule stop was requested, but the service has not exited yet."],
        "errors": [],
    }


def restart_schedule_service(config_arg: str) -> dict[str, Any]:
    startup = load_schedule_startup_config(config_arg)
    repository = _schedule_lifecycle_repository(startup.config_path)
    lifecycle = repository.inspect(SCHEDULE_SERVICE_ROLE)
    restart_from_instance_id = lifecycle.instance_id
    if lifecycle.status in {"running", "starting", "stop_requested", "unresponsive"} and lifecycle.instance_id:
        stopped = stop_schedule_service(config_arg)
        if stopped.get("status") not in {"stopped", "failed", "crashed", "stale", "not_found"}:
            return stopped
    if not restart_from_instance_id:
        return start_schedule_service(config_arg)
    return start_schedule_service(config_arg, restart_from_instance_id=restart_from_instance_id)


def _schedule_lifecycle_repository(config_path: Path) -> ServiceLifecycleRepository:
    return ServiceLifecycleRepository(runtime_root=artifact_base(config_path))


def _schedule_service_config_digest(config: dict[str, Any], *, config_path: Path) -> str:
    material = {
        "service": SCHEDULE_SERVICE_NAME,
        "config": config if isinstance(config, dict) else {},
        "config_ref": dashboard_config_ref(config_path),
        "service_contract": "schedule_service_v1",
    }
    payload = json.dumps(material, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(payload.encode("utf-8")).hexdigest()


def _schedule_endpoint_metadata() -> dict[str, Any]:
    return {"service": SCHEDULE_SERVICE_NAME}


def _schedule_lifecycle_start_message(result: ServiceLifecycleResult) -> str:
    if result.reason:
        return result.reason
    return f"schedule service could not start because lifecycle status is {result.status}."


def _schedule_start_blocking_result(
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
            "reason": "schedule service is in a terminal state; use schedule restart after confirming the instance id.",
            "lifecycle": _schedule_lifecycle_payload(lifecycle),
        }
    state = lifecycle.state if isinstance(lifecycle.state, dict) else {}
    if lifecycle.status == "unresponsive":
        return {
            "status": "unresponsive",
            "reason": "schedule service lock is held but heartbeat is stale; stop or inspect it before starting another service.",
            "lifecycle": _schedule_lifecycle_payload(lifecycle),
        }
    if lifecycle.status not in {"running", "starting", "stop_requested"}:
        return None
    if state.get("config_digest") != config_digest:
        return {
            "status": "conflict",
            "reason": "schedule service is already active for a different service configuration.",
            "lifecycle": _schedule_lifecycle_payload(lifecycle),
        }
    if lifecycle.status == "starting":
        return {
            "status": "starting",
            "reason": "schedule service is already starting.",
            "lifecycle": _schedule_lifecycle_payload(lifecycle),
        }
    if lifecycle.status == "stop_requested":
        return {
            "status": "stop_requested",
            "reason": "schedule service is stopping; wait for it to exit before starting another service.",
            "lifecycle": _schedule_lifecycle_payload(lifecycle),
        }
    return _schedule_service_result("existing", lifecycle=lifecycle)


def _launch_schedule_service_process(
    config_arg: str,
    *,
    restart_from_instance_id: str | None,
) -> subprocess.Popen[Any]:
    command = [sys.executable, "-m", "halpha", "schedule", "service", "--config", config_arg]
    if restart_from_instance_id:
        command.extend(["--restart-from-instance-id", restart_from_instance_id])
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "cwd": Path.cwd(),
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(command, **kwargs)


def _wait_for_schedule_service_start(
    process: subprocess.Popen[Any],
    *,
    repository: ServiceLifecycleRepository,
    config_digest: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        lifecycle = repository.inspect(SCHEDULE_SERVICE_ROLE)
        if lifecycle.status == "running" and _lifecycle_config_digest(lifecycle) == config_digest:
            return _schedule_service_result("started", lifecycle=lifecycle)
        if process.poll() is not None:
            raise ScheduleServiceError("schedule service exited before it registered a running lifecycle state.")
        time.sleep(SCHEDULE_CONTROL_POLL_SECONDS)
    raise ScheduleServiceError("schedule service did not become running before the startup timeout.")


def _wait_for_existing_schedule_service(
    repository: ServiceLifecycleRepository,
    *,
    config_digest: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        lifecycle = repository.inspect(SCHEDULE_SERVICE_ROLE)
        if lifecycle.status == "running" and _lifecycle_config_digest(lifecycle) == config_digest:
            return _schedule_service_result("existing", lifecycle=lifecycle)
        time.sleep(SCHEDULE_CONTROL_POLL_SECONDS)
    raise ScheduleServiceError("schedule service is starting, but it is not running yet.")


def _wait_for_schedule_service_stop(
    repository: ServiceLifecycleRepository,
    *,
    previous_instance_id: str,
    timeout_seconds: float,
) -> dict[str, Any] | None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        lifecycle = repository.inspect(SCHEDULE_SERVICE_ROLE)
        if lifecycle.instance_id == previous_instance_id and lifecycle.status in {"stopped", "failed", "crashed", "stale"}:
            return _schedule_service_result(lifecycle.status, lifecycle=lifecycle)
        time.sleep(SCHEDULE_CONTROL_POLL_SECONDS)
    return None


def _schedule_service_result(status: str, *, lifecycle: ServiceLifecycleResult) -> dict[str, Any]:
    return {
        "status": status,
        "service": SCHEDULE_SERVICE_NAME,
        "instance_id": lifecycle.instance_id,
        "pid": _schedule_lifecycle_pid(lifecycle),
        "lifecycle": _schedule_lifecycle_payload(lifecycle),
        "warnings": [],
        "errors": [],
    }


def _schedule_lifecycle_payload(lifecycle: ServiceLifecycleResult) -> dict[str, Any]:
    state = lifecycle.state if isinstance(lifecycle.state, dict) else {}
    return {
        "status": lifecycle.status,
        "role": lifecycle.role,
        "instance_id": lifecycle.instance_id,
        "owns_lock": lifecycle.owns_lock,
        "reason": lifecycle.reason,
        "pid": _schedule_lifecycle_pid(lifecycle),
        "config_ref": state.get("config_ref"),
        "config_digest": state.get("config_digest"),
        "started_at": state.get("started_at"),
        "updated_at": state.get("updated_at"),
        "heartbeat_at": state.get("heartbeat_at"),
        "stop_requested_at": state.get("stop_requested_at"),
        "terminal_at": state.get("terminal_at"),
        "last_error": state.get("last_error") if isinstance(state.get("last_error"), dict) else {},
    }


def _schedule_lifecycle_pid(lifecycle: ServiceLifecycleResult) -> int | None:
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
    with suppress(Exception):
        return repository.observe_stop_request(SCHEDULE_SERVICE_ROLE, instance_id=instance_id).requested
    return False


def _wait_for_stop_or_timeout(repository: ServiceLifecycleRepository, instance_id: str, seconds: float) -> bool:
    deadline = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < deadline:
        if _stop_requested(repository, instance_id):
            return True
        with suppress(Exception):
            repository.update_heartbeat(SCHEDULE_SERVICE_ROLE, instance_id=instance_id)
        time.sleep(min(SCHEDULE_CONTROL_POLL_SECONDS, max(0.0, deadline - time.monotonic())))
    return _stop_requested(repository, instance_id)


def schedule_service_error_message(message: str, *, config_path: Path) -> str:
    return sanitize_dashboard_message(message, config_path=config_path)
