"""Qualify B04 Windows task, abnormal-restart, and PostgreSQL recovery drills."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import time
from typing import Any, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import win32api
import win32com.client
import win32con
import win32service
import win32serviceutil

from halpha.configuration import load_settings, settings_digest
from halpha.runtime_identity import require_repository_runtime
from halpha.windows_runtime import current_process_sid, signal_stop_event
from tools.qualification.source_binding import (
    SourceBindingError,
    capture_source_sha256,
)
from tools.qualification.verify_windows_runtime import _processes_by_module


TASK_FOLDER = r"\Halpha"
TASK_DISABLED = 1
TASK_READY = 3
TASK_RUNNING = 4
TASK_RESULT_RUNNING = 267009
DEFAULT_OUTPUT = Path("build/qualification/b04-windows-fault-drills.json")
SOURCE_PATTERNS = (
    "config/halpha.toml",
    "migrations/versions/*.py",
    "requirements/runtime.txt",
    "src/halpha/**/*.py",
    "tools/qualification/source_binding.py",
    "src/halpha/source_identity.py",
    "tools/qualification/verify_b04_windows_faults.py",
    "tools/qualification/verify_windows_runtime.py",
)


class WindowsFaultQualificationError(RuntimeError):
    """Sanitized operational qualification failure."""


def _canonical_digest(value: dict[str, Any]) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def _wait(predicate: Any, *, seconds: float, reason: str) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.25)
    raise WindowsFaultQualificationError(reason)


def _latest_ready(path: Path, *, after: datetime) -> dict[str, object] | None:
    if not path.is_file():
        return None
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict) or value.get("event") != "runtime_ready":
            continue
        raw = value.get("observed_at")
        if not isinstance(raw, str):
            continue
        observed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if observed >= after:
            return value
    return None


def _http(port: int) -> tuple[int, str]:
    try:
        with urlopen(f"http://127.0.0.1:{port}/operations", timeout=5) as response:
            return int(response.status), response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        return int(exc.code), ""
    except (OSError, URLError):
        return 0, ""


def _tasks() -> tuple[Any, dict[str, Any]]:
    service = win32com.client.Dispatch("Schedule.Service")
    service.Connect()
    folder = service.GetFolder(TASK_FOLDER)
    return folder, {"app": folder.GetTask("App"), "executor": folder.GetTask("Executor")}


def _task_enablement(tasks: dict[str, Any]) -> dict[str, bool]:
    return {role: bool(task.Enabled) for role, task in tasks.items()}


def _apply_task_enablement(
    tasks: dict[str, Any],
    enabled: dict[str, bool],
) -> None:
    for role, value in enabled.items():
        tasks[role].Enabled = value


def _signal_role(settings: Any, role: str) -> None:
    if role == "app":
        name = settings.windows.app_stop_event
        sid = settings.windows.app_task_sid
    else:
        name = settings.windows.executor_stop_event
        sid = settings.windows.executor_task_sid
    signal_stop_event(
        name=name,
        task_sid=sid,
        maintenance_sid=settings.windows.maintenance_sid,
    )


def _stop_running(settings: Any, tasks: dict[str, Any], roles: Sequence[str]) -> None:
    original_enablement = {
        role: bool(tasks[role].Enabled)
        for role in roles
    }
    try:
        # The production tasks have one-minute recovery triggers.  Disable them
        # before signaling so a successful controlled stop cannot race the next
        # trigger and look like a shutdown timeout.
        for role in roles:
            tasks[role].Enabled = False
        for role in roles:
            if int(tasks[role].State) == TASK_RUNNING:
                _signal_role(settings, role)
        for role in roles:
            _wait(
                lambda role=role: (
                    int(tasks[role].State) in (TASK_DISABLED, TASK_READY)
                    and not _processes_by_module()[role]
                ),
                seconds=45,
                reason=f"CONTROLLED_STOP_TIMEOUT role={role}",
            )
    finally:
        for role, enabled in original_enablement.items():
            tasks[role].Enabled = enabled


def _wait_product_ready(
    root: Path,
    settings: Any,
    tasks: dict[str, Any],
    *,
    after: datetime,
    roles: Sequence[str] = ("app", "executor"),
    seconds: float = 90,
    reason: str = "PRODUCT_RUNTIME_READY_TIMEOUT",
) -> dict[str, object]:
    log_path = root / settings.maintenance.log_root / "executor.jsonl"

    def ready() -> bool:
        if any(int(tasks[role].State) != TASK_RUNNING for role in roles):
            return False
        if "app" in roles and _http(settings.app.port)[0] != 200:
            return False
        if "executor" in roles:
            evidence = _latest_ready(log_path, after=after)
            if evidence is None or evidence.get("product_runtime_started") is not True:
                return False
        return True

    _wait(ready, seconds=seconds, reason=reason)
    evidence = _latest_ready(log_path, after=after)
    return evidence or {}


def _terminate_executor_child(processes: dict[str, list[dict[str, object]]]) -> int:
    items = processes["executor"]
    pids = {int(item["pid"]) for item in items}
    children = [item for item in items if int(item["parent_pid"]) in pids]
    if len(children) != 1:
        raise WindowsFaultQualificationError("EXECUTOR_CHILD_IDENTITY_AMBIGUOUS")
    pid = int(children[0]["pid"])
    handle = win32api.OpenProcess(win32con.PROCESS_TERMINATE, False, pid)
    try:
        win32api.TerminateProcess(handle, 70)
    finally:
        handle.Close()
    return pid


def _service_state(name: str) -> int:
    return int(win32serviceutil.QueryServiceStatus(name)[1])


def qualify(
    root: Path,
    config_path: Path,
    *,
    postgresql_service: str,
) -> dict[str, Any]:
    require_repository_runtime(root)
    settings = load_settings(config_path)
    if current_process_sid() != settings.windows.maintenance_sid:
        raise WindowsFaultQualificationError("MAINTENANCE_SID_MISMATCH")
    _folder, tasks = _tasks()
    observations: dict[str, Any] = {}

    _stop_running(settings, tasks, ("executor", "app"))
    initial_start = datetime.now(UTC)
    tasks["app"].Run("")
    tasks["executor"].Run("")
    initial_ready = _wait_product_ready(
        root,
        settings,
        tasks,
        after=initial_start,
        reason="INITIAL_PRODUCT_RUNTIME_READY_TIMEOUT",
    )
    initial_processes = _processes_by_module()
    observations["initial_ready"] = initial_ready

    tasks["app"].Run("")
    tasks["executor"].Run("")
    time.sleep(1)
    duplicate_processes = _processes_by_module()

    crash_at = datetime.now(UTC)
    killed_pid = _terminate_executor_child(duplicate_processes)
    _wait(
        lambda: _processes_by_module()["executor"] != duplicate_processes["executor"],
        seconds=20,
        reason="EXECUTOR_CRASH_PROCESS_SET_UNCHANGED",
    )
    abnormal_ready = _wait_product_ready(
        root,
        settings,
        tasks,
        after=crash_at,
        roles=("executor",),
        seconds=100,
        reason="EXECUTOR_WATCHDOG_RESTART_READY_TIMEOUT",
    )
    after_abnormal_processes = _processes_by_module()
    observations["abnormal_restart"] = {
        "terminated_child_pid": killed_pid,
        "runtime_ready": abnormal_ready,
        "processes": after_abnormal_processes["executor"],
    }

    _signal_role(settings, "executor")
    _wait(
        lambda: int(tasks["executor"].State) == TASK_READY,
        seconds=45,
        reason="EXECUTOR_PRE_DATABASE_STOP_TIMEOUT",
    )
    win32serviceutil.StopService(postgresql_service)
    _wait(
        lambda: _service_state(postgresql_service) == win32service.SERVICE_STOPPED,
        seconds=45,
        reason="POSTGRESQL_STOP_TIMEOUT",
    )
    db_down_status, _ = _http(settings.app.port)
    database_start_attempt_at = datetime.now(UTC)
    tasks["executor"].Run("")
    _wait(
        lambda: int(tasks["executor"].State) == TASK_READY
        and int(tasks["executor"].LastTaskResult) not in (0, TASK_RESULT_RUNNING),
        seconds=30,
        reason="EXECUTOR_DID_NOT_FAIL_CLOSED_WITH_DATABASE_DOWN",
    )
    database_down_result = int(tasks["executor"].LastTaskResult)

    win32serviceutil.StartService(postgresql_service)
    _wait(
        lambda: _service_state(postgresql_service) == win32service.SERVICE_RUNNING,
        seconds=45,
        reason="POSTGRESQL_START_TIMEOUT",
    )
    recovery_at = datetime.now(UTC)
    tasks["executor"].Run("")
    recovery_ready = _wait_product_ready(
        root,
        settings,
        tasks,
        after=recovery_at,
        roles=("executor",),
        seconds=90,
        reason="POSTGRESQL_RECOVERY_RUNTIME_READY_TIMEOUT",
    )
    recovered_http_status, _ = _http(settings.app.port)
    observations["database_fault"] = {
        "service": postgresql_service,
        "database_start_attempt_at": database_start_attempt_at.isoformat().replace(
            "+00:00", "Z"
        ),
        "app_status_while_database_down": db_down_status,
        "executor_task_result_while_database_down": database_down_result,
        "recovery_runtime_ready": recovery_ready,
        "app_status_after_database_recovery": recovered_http_status,
    }

    _stop_running(settings, tasks, ("executor", "app"))
    final_results = {
        role: int(task.LastTaskResult) for role, task in tasks.items()
    }
    checks = {
        "initial_product_runtime_ready": initial_ready.get("product_runtime_started") is True,
        "duplicate_task_start_created_no_process": initial_processes == duplicate_processes,
        "executor_abnormal_exit_restarted_with_new_processes": (
            after_abnormal_processes["executor"] != initial_processes["executor"]
            and abnormal_ready.get("product_runtime_started") is True
        ),
        "postgresql_recovered_running": _service_state(postgresql_service)
        == win32service.SERVICE_RUNNING,
        "app_authentication_entry_remained_available": db_down_status == 200,
        "executor_start_failed_closed_while_database_down": database_down_result not in (
            0,
            TASK_RESULT_RUNNING,
        ),
        "postgresql_restart_and_executor_reconciliation_succeeded": (
            recovery_ready.get("product_runtime_started") is True
            and recovery_ready.get("startup_reconciliation_completed") is True
            and recovered_http_status == 200
        ),
        "runtime_real_write_gate_remained_closed": all(
            item.get("runtime_real_write_gate") == "CLOSED"
            for item in (initial_ready, abnormal_ready, recovery_ready)
        ),
        "controlled_stop_completed": all(
            int(tasks[role].State) == TASK_READY for role in ("app", "executor")
        ),
        "controlled_stop_returned_success": final_results == {"app": 0, "executor": 0},
    }
    report: dict[str, Any] = {
        "schema_version": 1,
        "stage": "B04_WINDOWS_AND_DATABASE_FAULT_DRILLS",
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "configuration_digest": settings_digest(settings),
        "checks": checks,
        "observations": observations,
        "final_task_results": final_results,
        "status": "QUALIFIED" if all(checks.values()) else "REJECTED",
    }
    report["evidence_digest"] = _canonical_digest(report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--postgresql-service", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    root = args.repository_root.resolve()
    output = args.output.resolve()
    if not output.is_relative_to(root):
        raise WindowsFaultQualificationError("OUTPUT_OUTSIDE_REPOSITORY")
    source_sha256_at_start = capture_source_sha256(root, SOURCE_PATTERNS)
    settings = load_settings(args.config.resolve())
    _folder, task_scope = _tasks()
    original_task_enablement = _task_enablement(task_scope)
    try:
        _apply_task_enablement(
            task_scope,
            {role: True for role in original_task_enablement},
        )
        report = qualify(
            root,
            args.config.resolve(),
            postgresql_service=args.postgresql_service,
        )
    except Exception as exc:
        recovery_errors: list[str] = []
        try:
            if _service_state(args.postgresql_service) != win32service.SERVICE_RUNNING:
                win32serviceutil.StartService(args.postgresql_service)
                _wait(
                    lambda: _service_state(args.postgresql_service)
                    == win32service.SERVICE_RUNNING,
                    seconds=45,
                    reason="POSTGRESQL_RECOVERY_AFTER_DRILL_FAILURE_TIMEOUT",
                )
        except Exception as recovery_exc:
            recovery_errors.append(
                f"POSTGRESQL_RECOVERY_FAILED type={type(recovery_exc).__name__}"
            )
        try:
            settings = load_settings(args.config.resolve())
            _folder, tasks = _tasks()
            _stop_running(settings, tasks, ("executor", "app"))
        except Exception as recovery_exc:
            recovery_errors.append(
                f"TASK_RECOVERY_FAILED type={type(recovery_exc).__name__}"
            )
        if isinstance(exc, WindowsFaultQualificationError):
            reason = str(exc)
        else:
            reason = f"B04_WINDOWS_FAULT_DRILL_FAILED type={type(exc).__name__}"
        report = {
            "schema_version": 1,
            "stage": "B04_WINDOWS_AND_DATABASE_FAULT_DRILLS",
            "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "status": "REJECTED",
            "errors": [reason, *recovery_errors],
        }
        report["evidence_digest"] = _canonical_digest(report)
    task_scope_errors: list[str] = []
    try:
        _folder, task_scope = _tasks()
        _stop_running(settings, task_scope, ("executor", "app"))
    except Exception as scope_exc:
        task_scope_errors.append(
            f"TASK_SCOPE_STOP_FAILED type={type(scope_exc).__name__}"
        )
    try:
        _folder, task_scope = _tasks()
        _apply_task_enablement(task_scope, original_task_enablement)
    except Exception as scope_exc:
        task_scope_errors.append(
            f"TASK_SCOPE_RESTORE_FAILED type={type(scope_exc).__name__}"
        )
    try:
        _folder, task_scope = _tasks()
        restored_task_enablement = _task_enablement(task_scope)
    except Exception as scope_exc:
        restored_task_enablement = {}
        task_scope_errors.append(
            f"TASK_SCOPE_VERIFY_FAILED type={type(scope_exc).__name__}"
        )
    task_enablement_restored = restored_task_enablement == original_task_enablement
    report.setdefault("observations", {})["task_enablement_scope"] = {
        "before": original_task_enablement,
        "after": restored_task_enablement,
    }
    if task_scope_errors:
        report.setdefault("errors", []).extend(task_scope_errors)
        report["status"] = "REJECTED"
    report["source_sha256"] = source_sha256_at_start
    try:
        source_stable = (
            capture_source_sha256(root, SOURCE_PATTERNS) == source_sha256_at_start
        )
    except SourceBindingError as exc:
        source_stable = False
        report.setdefault("errors", []).append(
            f"WINDOWS_FAULT_SOURCE_BINDING_FAILED:{exc}"
        )
    checks = report.setdefault("checks", {})
    checks["scheduled_task_enablement_restored"] = task_enablement_restored
    checks["source_stable_during_qualification"] = source_stable
    if not source_stable or not task_enablement_restored or (
        report.get("status") == "QUALIFIED" and not all(checks.values())
    ):
        report["status"] = "REJECTED"
    report.pop("evidence_digest", None)
    report["evidence_digest"] = _canonical_digest(report)
    _write_report(output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "QUALIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
