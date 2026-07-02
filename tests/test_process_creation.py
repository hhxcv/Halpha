from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from halpha.dashboard.app import _launch_dashboard_service_process
from halpha.runtime import command_job_process
from halpha.runtime.monitor_service import LocalCoreServiceClient, _launch_monitor_service_process
from halpha.runtime.process_creation import hidden_subprocess_kwargs
import halpha.runtime.process_creation as process_creation


CREATE_NEW_PROCESS_GROUP = 0x00000200
DETACHED_PROCESS = 0x00000008
CREATE_NO_WINDOW = 0x08000000
STARTF_USESHOWWINDOW = 0x00000001
SW_HIDE = 0


class _FakeStartupInfo:
    def __init__(self) -> None:
        self.dwFlags = 0
        self.wShowWindow = -1


class _FakeProcess:
    pid = 12345
    returncode = None

    def poll(self) -> None:
        return None


@pytest.fixture
def windows_subprocess_constants(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(process_creation.subprocess, "CREATE_NEW_PROCESS_GROUP", CREATE_NEW_PROCESS_GROUP, raising=False)
    monkeypatch.setattr(process_creation.subprocess, "DETACHED_PROCESS", DETACHED_PROCESS, raising=False)
    monkeypatch.setattr(process_creation.subprocess, "CREATE_NO_WINDOW", CREATE_NO_WINDOW, raising=False)
    monkeypatch.setattr(process_creation.subprocess, "STARTF_USESHOWWINDOW", STARTF_USESHOWWINDOW, raising=False)
    monkeypatch.setattr(process_creation.subprocess, "SW_HIDE", SW_HIDE, raising=False)
    monkeypatch.setattr(process_creation.subprocess, "STARTUPINFO", _FakeStartupInfo, raising=False)


def test_hidden_subprocess_kwargs_hides_windows_console(windows_subprocess_constants: None) -> None:
    kwargs = hidden_subprocess_kwargs(new_process_group=True, detached=True)

    assert kwargs["creationflags"] & CREATE_NEW_PROCESS_GROUP
    assert kwargs["creationflags"] & DETACHED_PROCESS
    assert kwargs["creationflags"] & CREATE_NO_WINDOW
    assert kwargs["startupinfo"].dwFlags & STARTF_USESHOWWINDOW
    assert kwargs["startupinfo"].wShowWindow == SW_HIDE


def test_dashboard_service_launch_uses_windows_no_window_kwargs(
    windows_subprocess_constants: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_popen(command: list[str], **kwargs: Any) -> _FakeProcess:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return _FakeProcess()

    monkeypatch.setattr("halpha.dashboard.app.subprocess.Popen", fake_popen)

    _launch_dashboard_service_process(
        "config.yaml",
        host="127.0.0.1",
        port=8765,
        restart_from_instance_id="core-prev",
    )

    kwargs = captured["kwargs"]
    assert kwargs["creationflags"] & CREATE_NO_WINDOW
    assert kwargs["startupinfo"].wShowWindow == SW_HIDE
    assert "--restart-from-instance-id" in captured["command"]


def test_monitor_service_launch_uses_windows_no_window_kwargs(
    windows_subprocess_constants: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_popen(command: list[str], **kwargs: Any) -> _FakeProcess:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return _FakeProcess()

    monkeypatch.setattr("halpha.runtime.monitor_service.subprocess.Popen", fake_popen)

    _launch_monitor_service_process("config.yaml", restart_from_instance_id="monitor-prev")

    kwargs = captured["kwargs"]
    assert kwargs["creationflags"] & CREATE_NO_WINDOW
    assert kwargs["startupinfo"].wShowWindow == SW_HIDE
    assert "--restart-from-instance-id" in captured["command"]


def test_monitor_core_supervision_uses_windows_no_window_run_kwargs(
    windows_subprocess_constants: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("halpha.runtime.monitor_service.subprocess.run", fake_run)

    LocalCoreServiceClient(config_path=tmp_path / "config.yaml")._start_core_service()

    kwargs = captured["kwargs"]
    assert kwargs["creationflags"] & CREATE_NO_WINDOW
    assert kwargs["startupinfo"].wShowWindow == SW_HIDE
    assert captured["command"][:3] == [sys.executable, "-m", "halpha"]


def test_command_job_process_uses_windows_no_window_kwargs(
    windows_subprocess_constants: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_popen(command: list[str], **kwargs: Any) -> _FakeProcess:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return _FakeProcess()

    monkeypatch.setattr(command_job_process.os, "name", "nt")

    command_job_process.launch_command_job_process(
        [sys.executable, "-V"],
        cwd=tmp_path,
        env={},
        popen_factory=fake_popen,
    )

    kwargs = captured["kwargs"]
    assert kwargs["creationflags"] & CREATE_NEW_PROCESS_GROUP
    assert kwargs["creationflags"] & CREATE_NO_WINDOW
    assert kwargs["startupinfo"].wShowWindow == SW_HIDE


def test_windows_taskkill_uses_no_window_kwargs(
    windows_subprocess_constants: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("halpha.runtime.command_job_process.subprocess.run", fake_run)

    command_job_process._run_taskkill(12345, force=True)

    kwargs = captured["kwargs"]
    assert captured["command"] == ["taskkill", "/PID", "12345", "/T", "/F"]
    assert kwargs["creationflags"] & CREATE_NO_WINDOW
    assert kwargs["startupinfo"].wShowWindow == SW_HIDE
