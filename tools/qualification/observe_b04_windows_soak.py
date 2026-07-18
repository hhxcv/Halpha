"""Observe one uninterrupted 72-hour App/Executor Windows qualification run."""

from __future__ import annotations

import argparse
import ctypes
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Sequence
from urllib.request import urlopen

import win32com.client

from halpha.configuration import load_settings, settings_digest
from halpha.runtime_identity import require_repository_runtime
from halpha.windows_runtime import current_process_sid


TASK_FOLDER = r"\Halpha"
TASK_STATE_RUNNING = 4
DEFAULT_OUTPUT = Path("build/qualification/b04-windows-72h-soak.json")


class WindowsSoakObservationError(RuntimeError):
    """Sanitized qualification observation failure."""


def unbiased_interrupt_time_100ns() -> int:
    """Return Windows awake time, excluding sleep and hibernation."""

    value = ctypes.c_ulonglong()
    success = ctypes.windll.kernel32.QueryUnbiasedInterruptTime(ctypes.byref(value))
    if not success:
        raise WindowsSoakObservationError("UNBIASED_INTERRUPT_TIME_UNAVAILABLE")
    return int(value.value)


def continuity_clock(
    *,
    started_at: datetime,
    observed_at: datetime,
    started_unbiased_100ns: int,
    observed_unbiased_100ns: int,
) -> dict[str, float | bool]:
    if observed_unbiased_100ns < started_unbiased_100ns:
        raise WindowsSoakObservationError("UNBIASED_INTERRUPT_TIME_REGRESSION")
    wall_seconds = (observed_at - started_at).total_seconds()
    awake_seconds = (observed_unbiased_100ns - started_unbiased_100ns) / 10_000_000
    if wall_seconds < 0:
        raise WindowsSoakObservationError("SOAK_WALL_CLOCK_REGRESSION")
    sleep_or_hibernate_seconds = max(0.0, wall_seconds - awake_seconds)
    return {
        "wall_elapsed_hours": wall_seconds / 3600,
        "awake_elapsed_hours": awake_seconds / 3600,
        "sleep_or_hibernate_seconds": sleep_or_hibernate_seconds,
        "no_sleep_or_hibernate_over_60_seconds": (
            sleep_or_hibernate_seconds <= 60.0
        ),
        "minimum_72_awake_hours_observed": awake_seconds >= 72 * 3600,
    }


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


def _processes_by_module() -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = {"app": [], "executor": []}
    wmi = win32com.client.GetObject("winmgmts:")
    query = (
        "SELECT ProcessId,ParentProcessId,CommandLine,ExecutablePath "
        "FROM Win32_Process WHERE Name='python.exe'"
    )
    for process in wmi.ExecQuery(query):
        command = str(process.CommandLine or "")
        if "-m halpha.app" in command:
            role = "app"
        elif "-m halpha.executor" in command:
            role = "executor"
        else:
            continue
        owner = process.ExecMethod_("GetOwner")
        if int(owner.Properties_("ReturnValue").Value) != 0:
            raise WindowsSoakObservationError(
                f"PROCESS_OWNER_LOOKUP_FAILED role={role}"
            )
        result[role].append(
            {
                "pid": int(process.ProcessId),
                "parent_pid": int(process.ParentProcessId),
                "owner": (
                    f"{owner.Properties_('Domain').Value}\\"
                    f"{owner.Properties_('User').Value}"
                ),
                "executable": str(process.ExecutablePath or ""),
            }
        )
    for processes in result.values():
        processes.sort(key=lambda item: int(item["pid"]))
    return result


def normalize_task_time_local(value: datetime | str) -> str:
    """Attach the host offset to a Task Scheduler local wall-clock value.

    Task Scheduler exposes ``LastRunTime`` as a local COM ``DATE``.  Pywin32
    can attach timezone metadata that does not describe that wall clock (for
    example ``+00:00`` on a UTC+08 host).  Converting that aware value would
    shift the actual scheduler time, so discard the COM metadata first and
    then let Python attach the Windows host's date-specific local offset.
    """

    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    return parsed.replace(tzinfo=None).astimezone().isoformat(timespec="seconds")


def _normalize_checkpoint_task_times(
    checkpoints: list[dict[str, object]],
) -> None:
    """Repair prior in-progress checkpoint labels without changing wall time."""

    for checkpoint in checkpoints:
        task_state = checkpoint.get("task_state")
        if not isinstance(task_state, dict):
            continue
        for state in task_state.values():
            if not isinstance(state, dict):
                continue
            value = state.get("last_run_time_local")
            if not isinstance(value, str):
                continue
            try:
                state["last_run_time_local"] = normalize_task_time_local(value)
            except ValueError:
                continue


def _task_state() -> dict[str, dict[str, object]]:
    service = win32com.client.Dispatch("Schedule.Service")
    service.Connect()
    folder = service.GetFolder(TASK_FOLDER)
    result: dict[str, dict[str, object]] = {}
    for role, name in (("app", "App"), ("executor", "Executor")):
        task = folder.GetTask(name)
        result[role] = {
            "state": int(task.State),
            "last_task_result": int(task.LastTaskResult),
            "last_run_time_local": normalize_task_time_local(task.LastRunTime),
        }
    return result


def _latest_runtime_ready(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    latest: dict[str, object] | None = None
    with path.open("rb") as stream:
        for raw_line in stream:
            if not raw_line.endswith(b"\n"):
                break
            try:
                value = json.loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict) and value.get("event") == "runtime_ready":
                latest = value
    return latest


def _http_status(port: int) -> int:
    with urlopen(f"http://127.0.0.1:{port}/operations", timeout=5) as response:
        return int(response.status)


def observe(
    repository_root: Path,
    config_path: Path,
    output: Path,
    *,
    reset: bool = False,
) -> dict[str, Any]:
    require_repository_runtime(repository_root)
    root = repository_root.resolve()
    settings = load_settings(config_path)
    if current_process_sid() != settings.windows.maintenance_sid:
        raise WindowsSoakObservationError("MAINTENANCE_SID_MISMATCH")
    now = datetime.now(UTC)
    current_unbiased_100ns = unbiased_interrupt_time_100ns()
    processes = _processes_by_module()
    tasks = _task_state()
    runtime_ready = _latest_runtime_ready(root / settings.maintenance.log_root / "executor.jsonl")
    try:
        http_status = _http_status(settings.app.port)
    except OSError:
        http_status = 0

    expected_owners = {
        "app": f"{__import__('socket').gethostname()}\\HalphaApp".lower(),
        "executor": f"{__import__('socket').gethostname()}\\HalphaExecutor".lower(),
    }
    current_checks = {
        "app_task_running": tasks["app"]["state"] == TASK_STATE_RUNNING,
        "executor_task_running": tasks["executor"]["state"] == TASK_STATE_RUNNING,
        "app_process_identity_exact": len(processes["app"]) == 2
        and all(
            str(item["owner"]).lower() == expected_owners["app"]
            for item in processes["app"]
        ),
        "executor_process_identity_exact": len(processes["executor"]) == 2
        and all(
            str(item["owner"]).lower() == expected_owners["executor"]
            for item in processes["executor"]
        ),
        "operations_http_200": http_status == 200,
        "executor_product_runtime_ready": runtime_ready is not None
        and runtime_ready.get("product_runtime_started") is True
        and runtime_ready.get("startup_reconciliation_completed") is True
        and runtime_ready.get("database_continuity_guard_completed") is True,
        "runtime_proxy_value_not_observed": runtime_ready is not None
        and "proxy_url" not in runtime_ready
        and runtime_ready.get("proxy_supplied") is True,
        "runtime_real_write_gate_closed": runtime_ready is not None
        and runtime_ready.get("runtime_real_write_gate") == "CLOSED",
    }

    prior: dict[str, Any] | None = None
    if output.is_file() and not reset:
        loaded = json.loads(output.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            prior = loaded
    if prior is None:
        started_at = now
        started_unbiased_100ns = current_unbiased_100ns
        baseline_processes = processes
        checkpoints: list[dict[str, object]] = []
    else:
        started_at = datetime.fromisoformat(str(prior["started_at"]).replace("Z", "+00:00"))
        if "started_unbiased_100ns" not in prior:
            raise WindowsSoakObservationError("SOAK_EVIDENCE_UNBIASED_CLOCK_MISSING")
        started_unbiased_100ns = int(prior["started_unbiased_100ns"])
        baseline_processes = prior["baseline_processes"]
        checkpoints = list(prior.get("checkpoints", []))
        _normalize_checkpoint_task_times(checkpoints)

    identity_unchanged = processes == baseline_processes
    clock = continuity_clock(
        started_at=started_at,
        observed_at=now,
        started_unbiased_100ns=started_unbiased_100ns,
        observed_unbiased_100ns=current_unbiased_100ns,
    )
    checkpoint = {
        "observed_at": now.isoformat().replace("+00:00", "Z"),
        "unbiased_interrupt_time_100ns": current_unbiased_100ns,
        "awake_elapsed_hours": clock["awake_elapsed_hours"],
        "http_status": http_status,
        "task_state": tasks,
        "processes": processes,
        "current_checks": current_checks,
        "continuous_identity_unchanged": identity_unchanged,
    }
    checkpoints.append(checkpoint)
    checks = {
        **current_checks,
        "continuous_process_identity_unchanged": identity_unchanged,
        "no_sleep_or_hibernate_over_60_seconds": clock[
            "no_sleep_or_hibernate_over_60_seconds"
        ],
        "minimum_72_hours_observed": clock["minimum_72_awake_hours_observed"],
    }
    continuity_failed = (
        not identity_unchanged
        or not all(current_checks.values())
        or not checks["no_sleep_or_hibernate_over_60_seconds"]
    )
    status = (
        "REJECTED"
        if continuity_failed
        else ("QUALIFIED" if checks["minimum_72_hours_observed"] else "IN_PROGRESS")
    )
    report: dict[str, Any] = {
        "schema_version": 2,
        "stage": "B04_WINDOWS_72H_SOAK",
        "started_at": started_at.isoformat().replace("+00:00", "Z"),
        "started_unbiased_100ns": started_unbiased_100ns,
        "observed_at": now.isoformat().replace("+00:00", "Z"),
        "observed_unbiased_100ns": current_unbiased_100ns,
        "elapsed_hours": clock["awake_elapsed_hours"],
        "wall_elapsed_hours": clock["wall_elapsed_hours"],
        "sleep_or_hibernate_seconds": clock["sleep_or_hibernate_seconds"],
        "configuration_digest": settings_digest(settings),
        "source_sha256": {
            "tools/qualification/observe_b04_windows_soak.py": sha256(
                Path(__file__).read_bytes()
            ).hexdigest(),
            "src/halpha/windows_runtime.py": sha256(
                (root / "src/halpha/windows_runtime.py").read_bytes()
            ).hexdigest(),
        },
        "baseline_processes": baseline_processes,
        "checks": checks,
        "checkpoints": checkpoints[-1000:],
        "status": status,
        "limitations": [
            "This report proves the same Demo App/Executor process identities across at least 72 Windows awake hours and rejects sleep or hibernation over 60 seconds.",
            "Checkpoint endpoint checks do not prove per-second application or venue availability between observations.",
            "SMTP, LIVE_READ_ONLY, database interruption, abnormal restart, and controlled-stop drills have separate evidence.",
        ],
    }
    report["evidence_digest"] = _canonical_digest(report)
    _write_report(output, report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args(argv)
    root = args.repository_root.resolve()
    output = args.output.resolve()
    if not output.is_relative_to(root):
        raise WindowsSoakObservationError("OUTPUT_OUTSIDE_REPOSITORY")
    report = observe(root, args.config.resolve(), output, reset=args.reset)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] in {"IN_PROGRESS", "QUALIFIED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
