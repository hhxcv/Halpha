from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
from typing import Any, Callable, Mapping

from halpha.runtime.process_creation import hidden_subprocess_kwargs


COMMAND_JOB_CANCEL_GRACE_SECONDS = 2.0
COMMAND_JOB_FORCE_GRACE_SECONDS = 2.0
COMMAND_JOB_POLL_SECONDS = 0.05
_POSIX_EXITED_STATES = {"Z", "X", "x"}
_REAL_POPEN = subprocess.Popen


class CommandJobProcessError(Exception):
    pass


@dataclass
class CommandJobProcess:
    process: Any
    controller: "_ProcessTreeController"
    cancel_requested: threading.Event
    termination: dict[str, Any]

    @property
    def pid(self) -> int | None:
        pid = getattr(self.process, "pid", None)
        return int(pid) if isinstance(pid, int) else None

    @property
    def returncode(self) -> int | None:
        value = getattr(self.process, "returncode", None)
        return int(value) if isinstance(value, int) else None

    @property
    def identity(self) -> dict[str, Any]:
        return self.controller.identity

    def request_cancel(self) -> dict[str, Any]:
        self.cancel_requested.set()
        update = self.controller.request_graceful_termination(reason="caller_request")
        self.termination.update(update)
        return dict(self.termination)

    def communicate(self) -> tuple[str, str]:
        try:
            return self._communicate_with_polling()
        except TypeError:
            stdout, stderr = self.process.communicate()
            self._mark_exit_confirmed_if_cancelled()
            self._cleanup_after_root_exit()
            return stdout, stderr

    def _communicate_with_polling(self) -> tuple[str, str]:
        while True:
            try:
                stdout, stderr = self.process.communicate(timeout=COMMAND_JOB_POLL_SECONDS)
                self._mark_exit_confirmed_if_cancelled()
                self._cleanup_after_root_exit()
                return stdout, stderr
            except subprocess.TimeoutExpired:
                if self.cancel_requested.is_set():
                    self._finish_cancelled_tree()
                    stdout, stderr = self.process.communicate()
                    self._mark_exit_confirmed_if_cancelled()
                    self._cleanup_after_root_exit()
                    return stdout, stderr

    def _finish_cancelled_tree(self) -> None:
        if not self.termination.get("graceful_requested"):
            self.termination.update(self.controller.request_graceful_termination(reason="caller_request"))
        if self.controller.wait_tree_exit(COMMAND_JOB_CANCEL_GRACE_SECONDS):
            self.termination.update(
                {
                    "status": "terminated",
                    "confirmed_exit": True,
                    "forced": False,
                    "finished_at": _utc_now(),
                }
            )
            return
        self.termination.update(self.controller.force_termination(reason="cancel_timeout"))
        confirmed = self.controller.wait_tree_exit(COMMAND_JOB_FORCE_GRACE_SECONDS)
        self.termination.update(
            {
                "status": "terminated" if confirmed else "termination_unconfirmed",
                "confirmed_exit": confirmed,
                "forced": True,
                "finished_at": _utc_now(),
            }
        )

    def _cleanup_after_root_exit(self) -> None:
        if self.controller.cleanup_after_root_exit():
            self.termination.update(
                {
                    "cleanup_after_root_exit": True,
                    "cleanup_finished_at": _utc_now(),
                    "confirmed_exit": self.controller.wait_tree_exit(COMMAND_JOB_FORCE_GRACE_SECONDS),
                }
            )

    def _mark_exit_confirmed_if_cancelled(self) -> None:
        if not self.cancel_requested.is_set() or self.termination.get("confirmed_exit") is True:
            return
        if self.controller.tree_alive():
            return
        self.termination.update(
            {
                "status": "terminated",
                "confirmed_exit": True,
                "forced": bool(self.termination.get("force_requested")),
                "finished_at": _utc_now(),
            }
        )


def launch_command_job_process(
    command: list[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None,
    popen_factory: Callable[..., Any] = subprocess.Popen,
) -> CommandJobProcess:
    cancel_requested = threading.Event()
    kwargs: dict[str, Any] = {
        "cwd": cwd,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "shell": False,
        "env": dict(env) if env is not None else None,
    }
    platform = _platform_name()
    if platform == "posix":
        kwargs["start_new_session"] = True
    elif platform == "windows":
        kwargs.update(hidden_subprocess_kwargs(new_process_group=True, platform="win32"))
    else:
        raise CommandJobProcessError("command job process trees are not supported on this platform.")

    process = popen_factory(command, **kwargs)
    if not isinstance(process, _REAL_POPEN):
        controller = _PopenOnlyController(process)
    elif platform == "posix":
        controller = _PosixProcessGroupController(process)
    else:
        controller = _WindowsTaskkillController(process)
    return CommandJobProcess(
        process=process,
        controller=controller,
        cancel_requested=cancel_requested,
        termination={
            "schema_version": 1,
            "status": "running",
            "strategy": controller.identity.get("strategy"),
            "confirmed_exit": False,
            "forced": False,
            "private_values_embedded": False,
        },
    )


def process_identity_alive(identity: Mapping[str, Any]) -> bool:
    strategy = str(identity.get("strategy") or "")
    if strategy == "posix_process_group" and _platform_name() == "posix":
        return _posix_identity_alive(identity)
    if strategy == "windows_taskkill_tree" and _platform_name() == "windows":
        return _windows_identity_alive(identity)
    return False


class _ProcessTreeController:
    identity: dict[str, Any]

    def request_graceful_termination(self, *, reason: str) -> dict[str, Any]:
        raise NotImplementedError

    def force_termination(self, *, reason: str) -> dict[str, Any]:
        raise NotImplementedError

    def wait_tree_exit(self, timeout_seconds: float) -> bool:
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while time.monotonic() <= deadline:
            if not self.tree_alive():
                return True
            time.sleep(COMMAND_JOB_POLL_SECONDS)
        return not self.tree_alive()

    def tree_alive(self) -> bool:
        raise NotImplementedError

    def cleanup_after_root_exit(self) -> bool:
        if not self.tree_alive():
            return False
        self.request_graceful_termination(reason="root_exit_cleanup")
        if self.wait_tree_exit(COMMAND_JOB_CANCEL_GRACE_SECONDS):
            return True
        self.force_termination(reason="root_exit_cleanup_timeout")
        return True


class _PopenOnlyController(_ProcessTreeController):
    def __init__(self, process: Any) -> None:
        self.process = process
        self.identity = {
            "schema_version": 1,
            "platform": _platform_name(),
            "strategy": "popen_only_unverified",
            "pid": getattr(process, "pid", None),
            "manager_pid": os.getpid(),
            "started_at": _utc_now(),
            "verified": False,
            "private_values_embedded": False,
        }

    def request_graceful_termination(self, *, reason: str) -> dict[str, Any]:
        with _suppress_os_error():
            self.process.terminate()
        return {
            "status": "graceful_requested",
            "graceful_requested": True,
            "reason": reason,
            "requested_at": _utc_now(),
        }

    def force_termination(self, *, reason: str) -> dict[str, Any]:
        kill = getattr(self.process, "kill", None)
        if callable(kill):
            with _suppress_os_error():
                kill()
        return {"force_requested": True, "force_reason": reason, "force_requested_at": _utc_now()}

    def tree_alive(self) -> bool:
        return getattr(self.process, "returncode", None) is None

    def cleanup_after_root_exit(self) -> bool:
        return False


class _PosixProcessGroupController(_ProcessTreeController):
    def __init__(self, process: subprocess.Popen[str]) -> None:
        self.process = process
        self.pid = int(process.pid)
        self.pgid = os.getpgid(self.pid)
        self.start_time = _posix_start_time_ticks(self.pid)
        self.identity = {
            "schema_version": 1,
            "platform": "posix",
            "strategy": "posix_process_group",
            "pid": self.pid,
            "pgid": self.pgid,
            "start_time_ticks": self.start_time,
            "manager_pid": os.getpid(),
            "started_at": _utc_now(),
            "verified": self.start_time is not None,
            "private_values_embedded": False,
        }

    def request_graceful_termination(self, *, reason: str) -> dict[str, Any]:
        with _suppress_os_error():
            os.killpg(self.pgid, signal.SIGTERM)
        return {
            "status": "graceful_requested",
            "graceful_requested": True,
            "reason": reason,
            "requested_at": _utc_now(),
        }

    def force_termination(self, *, reason: str) -> dict[str, Any]:
        with _suppress_os_error():
            os.killpg(self.pgid, signal.SIGKILL)
        return {"force_requested": True, "force_reason": reason, "force_requested_at": _utc_now()}

    def tree_alive(self) -> bool:
        return _posix_process_group_alive(self.pgid)


class _WindowsTaskkillController(_ProcessTreeController):
    def __init__(self, process: subprocess.Popen[str]) -> None:
        self.process = process
        self.pid = int(process.pid)
        self.creation_time = _windows_process_creation_time(self.pid)
        self.identity = {
            "schema_version": 1,
            "platform": "windows",
            "strategy": "windows_taskkill_tree",
            "pid": self.pid,
            "creation_time_100ns": self.creation_time,
            "manager_pid": os.getpid(),
            "started_at": _utc_now(),
            "verified": self.creation_time is not None,
            "private_values_embedded": False,
        }

    def request_graceful_termination(self, *, reason: str) -> dict[str, Any]:
        _run_taskkill(self.pid, force=False)
        return {
            "status": "graceful_requested",
            "graceful_requested": True,
            "reason": reason,
            "requested_at": _utc_now(),
        }

    def force_termination(self, *, reason: str) -> dict[str, Any]:
        _run_taskkill(self.pid, force=True)
        return {"force_requested": True, "force_reason": reason, "force_requested_at": _utc_now()}

    def tree_alive(self) -> bool:
        return _windows_identity_alive(self.identity)


def _posix_identity_alive(identity: Mapping[str, Any]) -> bool:
    pid = _positive_int(identity.get("pid"))
    pgid = _positive_int(identity.get("pgid"))
    if pid is None or pgid is None:
        return False
    expected_start = identity.get("start_time_ticks")
    if expected_start is not None and _posix_start_time_ticks(pid) != expected_start:
        return False
    return _posix_process_group_alive(pgid)


def _posix_process_group_alive(pgid: int, *, proc_root: Path | None = None) -> bool:
    proc_alive = _posix_process_group_alive_from_proc(pgid, proc_root=proc_root or Path("/proc"))
    if proc_alive is not None:
        return proc_alive
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _posix_process_group_alive_from_proc(pgid: int, *, proc_root: Path) -> bool | None:
    try:
        if not proc_root.is_dir():
            return None
        entries = list(proc_root.iterdir())
    except OSError:
        return None
    found_member = False
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            text = (entry / "stat").read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        except PermissionError:
            return None
        except OSError:
            continue
        fields = _parse_posix_stat_fields(text)
        if len(fields) < 3:
            continue
        try:
            process_group = int(fields[2])
        except ValueError:
            continue
        if process_group != pgid:
            continue
        found_member = True
        if fields[0] not in _POSIX_EXITED_STATES:
            return True
    return False if found_member else False


def _posix_stat_fields(pid: int, *, proc_root: Path | None = None) -> list[str] | None:
    stat_path = (proc_root or Path("/proc")) / str(pid) / "stat"
    try:
        text = stat_path.read_text(encoding="utf-8")
    except OSError:
        return None
    return _parse_posix_stat_fields(text)


def _parse_posix_stat_fields(text: str) -> list[str]:
    marker = text.rfind(") ")
    if marker < 0:
        return []
    return text[marker + 2 :].split()


def _posix_start_time_ticks(pid: int) -> int | None:
    fields = _posix_stat_fields(pid)
    if fields is None:
        return None
    if len(fields) < 20:
        return None
    try:
        return int(fields[19])
    except ValueError:
        return None


def _windows_identity_alive(identity: Mapping[str, Any]) -> bool:
    pid = _positive_int(identity.get("pid"))
    if pid is None:
        return False
    expected = identity.get("creation_time_100ns")
    current = _windows_process_creation_time(pid)
    if current is None:
        return False
    return expected is None or current == expected


def _windows_process_creation_time(pid: int) -> int | None:
    if _platform_name() != "windows":
        return None
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return None
    process_query_limited_information = 0x1000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    ]
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(process_query_limited_information, False, int(pid))
    if not handle:
        return None
    try:
        created = wintypes.FILETIME()
        exited = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        if not kernel32.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user)):
            return None
        return (int(created.dwHighDateTime) << 32) + int(created.dwLowDateTime)
    finally:
        kernel32.CloseHandle(handle)


def _run_taskkill(pid: int, *, force: bool) -> None:
    command = ["taskkill", "/PID", str(pid), "/T"]
    if force:
        command.append("/F")
    with _suppress_os_error():
        subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            **hidden_subprocess_kwargs(platform="win32"),
        )


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    return None


def _platform_name() -> str:
    if os.name == "posix":
        return "posix"
    if os.name == "nt":
        return "windows"
    return os.name


class _suppress_os_error:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, traceback) -> bool:
        return exc_type is not None and issubclass(exc_type, OSError)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
