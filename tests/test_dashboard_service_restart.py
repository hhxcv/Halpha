from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import sys
from typing import Any

import pytest

import halpha.dashboard.app as dashboard_app
from halpha.config import load_config
from halpha.dashboard import DashboardError
from halpha.storage import write_json


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_run_dashboard_service_records_and_clears_service_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    state_path = tmp_path / ".halpha" / "dashboard" / "service_state.json"
    fake_uvicorn = _FakeUvicorn(
        on_run=lambda _app, **_kwargs: _assert_running_state(
            state_path,
            host="127.0.0.1",
            port=8765,
        )
    )

    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)
    monkeypatch.setattr(dashboard_app, "_dashboard_endpoint_can_bind", lambda _host, _port: True)

    dashboard_app.run_dashboard_service(config, config_path=config_path, host="127.0.0.1", port=8765)

    assert fake_uvicorn.calls == [{"host": "127.0.0.1", "port": 8765}]
    assert not state_path.exists()
    assert not (tmp_path / "runs" / "dashboard").exists()


def test_run_dashboard_service_restarts_matching_existing_dashboard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    state_path = tmp_path / ".halpha" / "dashboard" / "service_state.json"
    write_json(
        state_path,
        {
            "artifact_type": "dashboard_service_state",
            "schema_version": 1,
            "service": "halpha_dashboard",
            "status": "running",
            "pid": 4321,
            "host": "127.0.0.1",
            "port": 8765,
        },
    )
    bind_results = iter([False, True])
    terminated: list[int] = []
    fake_uvicorn = _FakeUvicorn()

    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)
    monkeypatch.setattr(dashboard_app, "_dashboard_endpoint_can_bind", lambda _host, _port: next(bind_results, True))
    monkeypatch.setattr(
        dashboard_app,
        "_read_dashboard_endpoint_health",
        lambda _host, _port: {"service": "halpha_dashboard", "status": "ok"},
    )
    monkeypatch.setattr(dashboard_app, "_dashboard_process_is_alive", lambda pid: pid == 4321)
    monkeypatch.setattr(dashboard_app, "_terminate_dashboard_process", lambda pid: terminated.append(pid))

    dashboard_app.run_dashboard_service(config, config_path=config_path, host="127.0.0.1", port=8765)

    assert terminated == [4321]
    assert fake_uvicorn.calls == [{"host": "127.0.0.1", "port": 8765}]
    assert not state_path.exists()
    assert not (tmp_path / "runs" / "dashboard").exists()


def test_run_dashboard_service_rejects_non_halpha_occupied_port(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    fake_uvicorn = _FakeUvicorn()

    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)
    monkeypatch.setattr(dashboard_app, "_dashboard_endpoint_can_bind", lambda _host, _port: False)
    monkeypatch.setattr(dashboard_app, "_read_dashboard_endpoint_health", lambda _host, _port: {"service": "other"})
    monkeypatch.setattr(
        dashboard_app,
        "_terminate_dashboard_process",
        lambda _pid: (_ for _ in ()).throw(AssertionError("non-Halpha service must not be stopped")),
    )

    with pytest.raises(DashboardError) as exc:
        dashboard_app.run_dashboard_service(config, config_path=config_path, host="127.0.0.1", port=8765)

    assert "already in use by a non-Halpha or unresponsive local service" in str(exc.value)
    assert fake_uvicorn.calls == []
    assert not (tmp_path / ".halpha" / "dashboard" / "service_state.json").exists()
    assert not (tmp_path / "runs" / "dashboard").exists()


def test_dashboard_process_is_alive_treats_missing_tasklist_stdout_as_not_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(dashboard_app.sys, "platform", "win32")
    monkeypatch.setattr(
        dashboard_app.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=None),
    )

    assert dashboard_app._dashboard_process_is_alive(4321) is False


def _assert_running_state(state_path: Path, *, host: str, port: int) -> None:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["artifact_type"] == "dashboard_service_state"
    assert state["service"] == "halpha_dashboard"
    assert state["status"] == "running"
    assert state["pid"] > 0
    assert state["host"] == host
    assert state["port"] == port
    assert state["config"] == {"loaded": True, "ref": "<external-config>"}


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
run:
  output_dir: runs
market:
  enabled: false
text:
  enabled: false
  sources: []
report:
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return path


class _FakeUvicorn:
    def __init__(self, on_run=None) -> None:  # noqa: ANN001
        self.calls: list[dict[str, Any]] = []
        self._on_run = on_run

    def run(self, _app: Any, *, host: str, port: int) -> None:
        self.calls.append({"host": host, "port": port})
        if self._on_run is not None:
            self._on_run(_app, host=host, port=port)
