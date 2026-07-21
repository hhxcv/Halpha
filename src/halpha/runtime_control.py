"""One Windows lifecycle view for Halpha tasks, processes, and listeners."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import subprocess
import time
from typing import Any, Callable, Iterable

import pywintypes
import win32api
import win32com.client
import win32con
import win32event
import winerror

from halpha.configuration import HalphaSettings
from halpha.external_services import (
    ExternalServiceRegistration,
    read_external_service_registrations,
)
from halpha.windows_runtime import WindowsRuntimeError, signal_stop_event


TASK_FOLDER = r"\Halpha"
TASK_NAMES = {
    "app": "App",
    "executor": "Executor",
    "backup": "Backup",
}
TASK_STATE_NAMES = {
    0: "UNKNOWN",
    1: "DISABLED",
    2: "QUEUED",
    3: "READY",
    4: "RUNNING",
}
class RuntimeControlError(RuntimeError):
    """A sanitized lifecycle discovery or control failure."""


@dataclass(frozen=True)
class ProcessSnapshot:
    pid: int
    parent_pid: int
    name: str
    executable: str | None
    command_line: str | None
    worktree: str


@dataclass(frozen=True)
class ListenerSnapshot:
    local_address: str
    local_port: int
    pid: int

    @property
    def endpoint(self) -> str:
        return f"{self.local_address}:{self.local_port}"


@dataclass(frozen=True)
class TaskSnapshot:
    service: str
    task_name: str
    state: str
    enabled: bool
    engine_pids: tuple[int, ...]
    present: bool = True


@dataclass(frozen=True)
class ServiceSnapshot:
    service: str
    kind: str
    manager: str
    recognized_as: str | None
    enabled: bool | None
    state: str
    health: str
    root_pid: int | None
    process_ids: tuple[int, ...]
    listeners: tuple[str, ...]
    worktree: str | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeInventory:
    status: str
    repository_root: str
    worktrees: tuple[str, ...]
    services: tuple[ServiceSnapshot, ...]
    unmanaged_service_ids: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "repository_root": self.repository_root,
            "worktrees": list(self.worktrees),
            "services": [service.to_dict() for service in self.services],
            "unmanaged_service_ids": list(self.unmanaged_service_ids),
            "warnings": list(self.warnings),
        }


def _path_key(value: str | Path) -> str:
    return os.path.normcase(str(value)).replace("/", "\\").rstrip("\\")


def discover_worktrees(repository_root: Path) -> tuple[Path, ...]:
    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(repository_root),
                "worktree",
                "list",
                "--porcelain",
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise RuntimeControlError(
            f"GIT_WORKTREE_DISCOVERY_FAILED type={type(exc).__name__}"
        ) from None
    roots = []
    for line in completed.stdout.splitlines():
        if line.startswith("worktree "):
            roots.append(Path(line.removeprefix("worktree ")).resolve())
    current = repository_root.resolve()
    if current not in roots:
        roots.append(current)
    return tuple(sorted(set(roots), key=lambda path: _path_key(path)))


def _matching_worktree(
    executable: str | None,
    command_line: str | None,
    worktrees: Iterable[Path],
) -> Path | None:
    haystack = _path_key(f"{executable or ''}\0{command_line or ''}")
    matches = []
    for worktree in worktrees:
        key = _path_key(worktree)
        if f"{key}\\" in haystack or haystack.endswith(key):
            matches.append(worktree)
    return max(matches, key=lambda path: len(_path_key(path)), default=None)


def read_project_processes(
    worktrees: tuple[Path, ...],
) -> dict[int, ProcessSnapshot]:
    try:
        service = win32com.client.GetObject(r"winmgmts:root\cimv2")
        rows = service.ExecQuery(
            "SELECT ProcessId,ParentProcessId,Name,ExecutablePath,CommandLine "
            "FROM Win32_Process"
        )
    except Exception as exc:
        raise RuntimeControlError(
            f"WINDOWS_PROCESS_DISCOVERY_FAILED type={type(exc).__name__}"
        ) from None
    processes: dict[int, ProcessSnapshot] = {}
    for row in rows:
        executable = str(row.ExecutablePath) if row.ExecutablePath else None
        command_line = str(row.CommandLine) if row.CommandLine else None
        worktree = _matching_worktree(executable, command_line, worktrees)
        if worktree is None:
            continue
        pid = int(row.ProcessId)
        processes[pid] = ProcessSnapshot(
            pid=pid,
            parent_pid=int(row.ParentProcessId),
            name=str(row.Name),
            executable=executable,
            command_line=command_line,
            worktree=str(worktree),
        )
    return processes


def read_tcp_listeners() -> tuple[ListenerSnapshot, ...]:
    try:
        service = win32com.client.GetObject(
            r"winmgmts:{impersonationLevel=impersonate}!\\.\root\StandardCimv2"
        )
        rows = service.ExecQuery(
            "SELECT LocalAddress,LocalPort,OwningProcess,State "
            "FROM MSFT_NetTCPConnection WHERE State=2"
        )
    except Exception as exc:
        raise RuntimeControlError(
            f"WINDOWS_LISTENER_DISCOVERY_FAILED type={type(exc).__name__}"
        ) from None
    return tuple(
        sorted(
            (
                ListenerSnapshot(
                    local_address=str(row.LocalAddress),
                    local_port=int(row.LocalPort),
                    pid=int(row.OwningProcess),
                )
                for row in rows
            ),
            key=lambda item: (item.local_port, item.local_address, item.pid),
        )
    )


def _scheduled_task_service() -> Any:
    try:
        service = win32com.client.Dispatch("Schedule.Service")
        service.Connect()
        return service
    except Exception as exc:
        raise RuntimeControlError(
            f"WINDOWS_TASK_SCHEDULER_UNAVAILABLE type={type(exc).__name__}"
        ) from None


def read_scheduled_tasks(task_service: Any) -> tuple[TaskSnapshot, ...]:
    try:
        folder = task_service.GetFolder(TASK_FOLDER)
    except pywintypes.com_error:
        return tuple(
            TaskSnapshot(
                service=service,
                task_name=task_name,
                state="MISSING",
                enabled=False,
                engine_pids=(),
                present=False,
            )
            for service, task_name in TASK_NAMES.items()
        )
    snapshots = []
    for service, task_name in TASK_NAMES.items():
        try:
            task = folder.GetTask(task_name)
        except pywintypes.com_error:
            snapshots.append(
                TaskSnapshot(
                    service=service,
                    task_name=task_name,
                    state="MISSING",
                    enabled=False,
                    engine_pids=(),
                    present=False,
                )
            )
            continue
        state = int(task.State)
        engine_pids = tuple(
            sorted(
                int(instance.EnginePID)
                for instance in task.GetInstances(1)
                if int(instance.EnginePID) > 0
            )
        )
        snapshots.append(
            TaskSnapshot(
                service=service,
                task_name=task_name,
                state=TASK_STATE_NAMES.get(state, f"UNKNOWN_{state}"),
                enabled=bool(task.Enabled),
                engine_pids=engine_pids,
            )
        )
    return tuple(snapshots)


def _descendants(root_pid: int, processes: dict[int, ProcessSnapshot]) -> tuple[int, ...]:
    selected = {root_pid}
    changed = True
    while changed:
        changed = False
        for process in processes.values():
            if process.parent_pid in selected and process.pid not in selected:
                selected.add(process.pid)
                changed = True
    return tuple(sorted(selected))


def _root_pid(pid: int, processes: dict[int, ProcessSnapshot]) -> int:
    current = pid
    visited = set()
    while current not in visited:
        visited.add(current)
        process = processes.get(current)
        if process is None or process.parent_pid not in processes:
            return current
        parent = processes[process.parent_pid]
        if _path_key(parent.command_line or "") != _path_key(process.command_line or ""):
            return current
        current = parent.pid
    return pid


def _listeners_for(
    process_ids: Iterable[int],
    listeners: tuple[ListenerSnapshot, ...],
) -> tuple[str, ...]:
    selected = set(process_ids)
    return tuple(
        sorted({listener.endpoint for listener in listeners if listener.pid in selected})
    )


def _recognized_service(processes: Iterable[ProcessSnapshot]) -> str | None:
    commands = tuple(
        (process.command_line or "").replace("\\", "/").casefold()
        for process in processes
    )
    for service, signatures in (
        ("app", (" -m halpha.app ", "/halpha-app.exe")),
        ("executor", (" -m halpha.executor ", "/halpha-executor.exe")),
    ):
        if any(
            signature in f" {command} "
            for command in commands
            for signature in signatures
        ):
            return service
    return None


def build_inventory(
    *,
    repository_root: Path,
    worktrees: tuple[Path, ...],
    processes: dict[int, ProcessSnapshot],
    listeners: tuple[ListenerSnapshot, ...],
    tasks: tuple[TaskSnapshot, ...],
    external_registrations: tuple[ExternalServiceRegistration, ...] = (),
    registration_warnings: tuple[str, ...] = (),
) -> RuntimeInventory:
    services: list[ServiceSnapshot] = []
    assigned_pids: set[int] = set()
    warnings: list[str] = list(registration_warnings)
    for task in tasks:
        process_ids = tuple(
            sorted(
                {
                    pid
                    for engine_pid in task.engine_pids
                    for pid in _descendants(engine_pid, processes)
                }
            )
        )
        assigned_pids.update(process_ids)
        health = "OK"
        if not task.present:
            health = "TASK_MISSING"
            warnings.append(f"TASK_MISSING:{task.service}")
        elif task.state == "RUNNING" and not task.engine_pids:
            health = "TASK_PROCESS_UNKNOWN"
            warnings.append(f"TASK_PROCESS_UNKNOWN:{task.service}")
        elif task.state == "RUNNING" and not process_ids:
            health = "TASK_PROCESS_OUTSIDE_WORKTREE"
            warnings.append(f"TASK_PROCESS_OUTSIDE_WORKTREE:{task.service}")
        root_pid = task.engine_pids[0] if task.engine_pids else None
        root = processes.get(root_pid) if root_pid is not None else None
        task_listeners = _listeners_for(process_ids, listeners)
        if (
            task.service == "app"
            and task.state == "RUNNING"
            and not task_listeners
            and health == "OK"
        ):
            health = "EXPECTED_LISTENER_MISSING"
            warnings.append("EXPECTED_LISTENER_MISSING:app")
        services.append(
            ServiceSnapshot(
                service=task.service,
                kind="JOB" if task.service == "backup" else "PRODUCT_SERVICE",
                manager="WINDOWS_TASK",
                recognized_as=task.service,
                enabled=task.enabled,
                state=task.state,
                health=health,
                root_pid=root_pid,
                process_ids=process_ids,
                listeners=task_listeners,
                worktree=root.worktree if root is not None else None,
            )
        )

    listeners_by_endpoint: dict[str, list[ListenerSnapshot]] = {}
    for listener in listeners:
        listeners_by_endpoint.setdefault(listener.endpoint, []).append(listener)
    for registration in external_registrations:
        owned_endpoints = tuple(
            endpoint
            for endpoint in registration.listeners
            if any(
                listener.pid == registration.pid
                for listener in listeners_by_endpoint.get(endpoint, ())
            )
        )
        verified = len(owned_endpoints) == len(registration.listeners)
        endpoint_in_use = any(
            listeners_by_endpoint.get(endpoint) for endpoint in registration.listeners
        )
        health = "OK"
        state = "RUNNING"
        process_ids: tuple[int, ...] = (registration.pid,)
        if not verified:
            health = "REGISTRATION_MISMATCH" if endpoint_in_use else "REGISTRATION_STALE"
            state = "UNVERIFIED"
            process_ids = ()
            warnings.append(f"{health}:external:{registration.service_id}")
        elif registration.pid in processes:
            process_ids = _descendants(registration.pid, processes)
            assigned_pids.update(process_ids)
        root = processes.get(registration.pid)
        services.append(
            ServiceSnapshot(
                service=f"external:{registration.service_id}",
                kind="EXTERNAL_SERVICE",
                manager="EXTERNAL_REGISTRATION",
                recognized_as=None,
                enabled=None,
                state=state,
                health=health,
                root_pid=registration.pid,
                process_ids=process_ids,
                listeners=owned_endpoints,
                worktree=root.worktree if root is not None else None,
            )
        )

    candidate_pids = {
        listener.pid
        for listener in listeners
        if listener.pid in processes and listener.pid not in assigned_pids
    }
    candidate_pids.update(
        process.pid
        for process in processes.values()
        if process.pid not in assigned_pids
        and _recognized_service((process,)) is not None
    )
    candidate_roots = {_root_pid(pid, processes) for pid in candidate_pids}
    for root_pid in sorted(candidate_roots):
        process_ids = _descendants(root_pid, processes)
        assigned_pids.update(process_ids)
        group = tuple(processes[pid] for pid in process_ids if pid in processes)
        recognized_as = _recognized_service(group)
        root = processes.get(root_pid)
        process_listeners = _listeners_for(process_ids, listeners)
        services.append(
            ServiceSnapshot(
                service=f"unmanaged:{root_pid}",
                kind=(
                    "UNMANAGED_PROJECT_SERVICE"
                    if recognized_as is not None
                    else "UNMANAGED_LISTENER"
                ),
                manager="DISCOVERED_ONLY",
                recognized_as=recognized_as,
                enabled=None,
                state="RUNNING",
                health="UNREGISTERED",
                root_pid=root_pid,
                process_ids=process_ids,
                listeners=process_listeners,
                worktree=root.worktree if root is not None else None,
            )
        )
    unmanaged_services = tuple(
        service for service in services if service.manager == "DISCOVERED_ONLY"
    )
    unmanaged = tuple(dict.fromkeys(service.service for service in unmanaged_services))
    if unmanaged_services:
        warnings.append("UNMANAGED_PROJECT_PROCESS_FOUND")
    return RuntimeInventory(
        status="CONTROLLED" if not warnings else "ATTENTION_REQUIRED",
        repository_root=str(repository_root.resolve()),
        worktrees=tuple(str(path) for path in worktrees),
        services=tuple(
            sorted(
                services,
                key=lambda service: (
                    {"app": 0, "executor": 1, "backup": 2}.get(service.service, 3),
                    service.service,
                    service.root_pid or 0,
                ),
            )
        ),
        unmanaged_service_ids=unmanaged,
        warnings=tuple(sorted(warnings)),
    )


class RuntimeController:
    def __init__(
        self,
        repository_root: Path,
        settings: HalphaSettings,
        *,
        task_service_factory: Callable[[], Any] = _scheduled_task_service,
    ) -> None:
        self._root = repository_root.resolve()
        self._settings = settings
        self._task_service_factory = task_service_factory

    def inventory(self) -> RuntimeInventory:
        try:
            worktrees = discover_worktrees(self._root)
            processes = read_project_processes(worktrees)
            listeners = read_tcp_listeners()
            tasks = read_scheduled_tasks(self._task_service_factory())
            registrations, registration_warnings = (
                read_external_service_registrations()
            )
            return build_inventory(
                repository_root=self._root,
                worktrees=worktrees,
                processes=processes,
                listeners=listeners,
                tasks=tasks,
                external_registrations=registrations,
                registration_warnings=registration_warnings,
            )
        except RuntimeControlError:
            raise
        except Exception as exc:
            raise RuntimeControlError(
                f"RUNTIME_INVENTORY_FAILED type={type(exc).__name__}"
            ) from None

    def start(
        self,
        target: str,
        *,
        timeout_seconds: float = 15.0,
    ) -> dict[str, object]:
        if target == "product":
            results = {
                service: self._start_task(service, timeout_seconds=timeout_seconds)
                for service in ("app", "executor")
            }
            return {"status": "STARTED", "target": target, "results": results}
        if target in TASK_NAMES:
            return self._start_task(target, timeout_seconds=timeout_seconds)
        raise RuntimeControlError(f"SERVICE_TARGET_UNSUPPORTED target={target}")

    def stop(
        self,
        target: str,
        *,
        force: bool = False,
        timeout_seconds: float = 30.0,
    ) -> dict[str, object]:
        if target == "product":
            targets = ("app", "executor")
        elif target == "all":
            inventory = self.inventory()
            extras = tuple(
                service.service
                for service in inventory.services
                if service.manager == "DISCOVERED_ONLY"
            )
            targets = ("app", "executor", "backup", *extras)
        else:
            targets = (target,)
        results: dict[str, object] = {}
        failures = False
        seen = set()
        for service in targets:
            if service in seen:
                continue
            seen.add(service)
            try:
                if service in TASK_NAMES:
                    result = self._stop_task(
                        service,
                        force=force,
                        timeout_seconds=timeout_seconds,
                    )
                elif service.startswith("unmanaged:"):
                    result = self._stop_discovered(service, timeout_seconds=timeout_seconds)
                else:
                    raise RuntimeControlError(
                        f"SERVICE_TARGET_UNSUPPORTED target={service}"
                    )
                results[service] = result
            except (RuntimeControlError, WindowsRuntimeError) as exc:
                failures = True
                results[service] = {"status": "REJECTED", "reason": str(exc)}
        return {
            "status": "PARTIAL" if failures else "STOPPED",
            "target": target,
            "results": results,
        }

    def _task(self, service: str) -> Any:
        try:
            folder = self._task_service_factory().GetFolder(TASK_FOLDER)
            return folder.GetTask(TASK_NAMES[service])
        except Exception as exc:
            raise RuntimeControlError(
                f"WINDOWS_TASK_LOOKUP_FAILED service={service} type={type(exc).__name__}"
            ) from None

    def _start_task(self, service: str, *, timeout_seconds: float) -> dict[str, object]:
        task = self._task(service)
        unmanaged = [
            instance
            for instance in self.inventory().services
            if instance.manager == "DISCOVERED_ONLY"
            and instance.recognized_as == service
        ]
        if unmanaged:
            raise RuntimeControlError(
                f"UNMANAGED_SERVICE_INSTANCE_FOUND service={service} "
                f"instances={len(unmanaged)}"
            )
        if int(task.State) == 4:
            task.Enabled = True
            if service == "app":
                self._wait_for_managed_listener(
                    service,
                    port=self._settings.app.port,
                    timeout_seconds=timeout_seconds,
                )
            return {"status": "ALREADY_RUNNING", "service": service}
        if service == "app":
            occupied = [
                listener
                for listener in read_tcp_listeners()
                if listener.local_port == self._settings.app.port
            ]
            if occupied:
                raise RuntimeControlError(
                    f"SERVICE_PORT_ALREADY_IN_USE service=app port={self._settings.app.port}"
                )
        task.Enabled = True
        task.Run("")
        if service == "backup":
            return {"status": "START_REQUESTED", "service": service}
        self._wait_for_task(task, running=True, timeout_seconds=timeout_seconds)
        if service == "app":
            self._wait_for_managed_listener(
                service,
                port=self._settings.app.port,
                timeout_seconds=timeout_seconds,
            )
        return {"status": "STARTED", "service": service}

    def _stop_task(
        self,
        service: str,
        *,
        force: bool,
        timeout_seconds: float,
    ) -> dict[str, object]:
        task = self._task(service)
        task.Enabled = False
        if int(task.State) != 4:
            return {"status": "ALREADY_STOPPED", "service": service, "enabled": False}
        if service == "backup":
            task.Stop(0)
        else:
            windows = self._settings.windows
            name, task_sid = (
                (windows.app_stop_event, windows.app_task_sid)
                if service == "app"
                else (windows.executor_stop_event, windows.executor_task_sid)
            )
            signal_stop_event(
                name=name,
                task_sid=task_sid,
                maintenance_sid=windows.maintenance_sid,
            )
        try:
            self._wait_for_task(task, running=False, timeout_seconds=timeout_seconds)
        except RuntimeControlError:
            if not force:
                raise
            task.Stop(0)
            self._wait_for_task(task, running=False, timeout_seconds=timeout_seconds)
        return {"status": "STOPPED", "service": service, "enabled": False}

    @staticmethod
    def _wait_for_task(task: Any, *, running: bool, timeout_seconds: float) -> None:
        expected = 4 if running else 3
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            state = int(task.State)
            if (running and state == expected) or (not running and state != 4):
                return
            time.sleep(0.1)
        raise RuntimeControlError(
            f"WINDOWS_TASK_STATE_TIMEOUT task={task.Name} expected="
            f"{'RUNNING' if running else 'STOPPED'} actual={int(task.State)}"
        )

    def _wait_for_managed_listener(
        self,
        service: str,
        *,
        port: int,
        timeout_seconds: float,
    ) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            managed = next(
                (
                    instance
                    for instance in self.inventory().services
                    if instance.service == service
                    and instance.manager == "WINDOWS_TASK"
                ),
                None,
            )
            if managed is not None and any(
                endpoint.endswith(f":{port}") for endpoint in managed.listeners
            ):
                return
            time.sleep(0.1)
        raise RuntimeControlError(
            f"SERVICE_LISTENER_TIMEOUT service={service} port={port}"
        )

    def _stop_discovered(
        self,
        service_id: str,
        *,
        timeout_seconds: float,
    ) -> dict[str, object]:
        inventory = self.inventory()
        matches = [service for service in inventory.services if service.service == service_id]
        if not matches:
            return {"status": "ALREADY_STOPPED", "service": service_id}
        for service in matches:
            if service.manager == "WINDOWS_TASK":
                raise RuntimeControlError("DISCOVERED_STOP_TARGET_IS_SCHEDULED_TASK")
            self._terminate_process_tree(
                service.process_ids,
                timeout_seconds=timeout_seconds,
            )
        return {
            "status": "STOPPED",
            "service": service_id,
            "instances": len(matches),
        }

    def _terminate_process_tree(
        self,
        process_ids: tuple[int, ...],
        *,
        timeout_seconds: float,
    ) -> None:
        if os.getpid() in process_ids:
            raise RuntimeControlError("CONTROL_PROCESS_TERMINATION_FORBIDDEN")
        worktrees = discover_worktrees(self._root)
        processes = read_project_processes(worktrees)

        def depth(pid: int) -> int:
            value = 0
            current = processes.get(pid)
            while current is not None and current.parent_pid in processes:
                value += 1
                current = processes.get(current.parent_pid)
            return value

        for pid in sorted(set(process_ids), key=depth, reverse=True):
            if pid not in processes:
                continue
            self._terminate_pid(pid, timeout_seconds=timeout_seconds)

    @staticmethod
    def _terminate_pid(pid: int, *, timeout_seconds: float) -> None:
        try:
            handle = win32api.OpenProcess(
                win32con.PROCESS_TERMINATE | win32con.SYNCHRONIZE,
                False,
                pid,
            )
        except pywintypes.error as exc:
            if exc.winerror == winerror.ERROR_INVALID_PARAMETER:
                return
            raise RuntimeControlError(
                f"PROCESS_OPEN_FAILED pid={pid} code={exc.winerror}"
            ) from None
        try:
            win32api.TerminateProcess(handle, 1)
            result = win32event.WaitForSingleObject(handle, int(timeout_seconds * 1000))
            if result == win32con.WAIT_TIMEOUT:
                raise RuntimeControlError(f"PROCESS_STOP_TIMEOUT pid={pid}")
        finally:
            handle.Close()
