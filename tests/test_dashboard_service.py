from __future__ import annotations

from pathlib import Path
import sqlite3
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient
import pytest

from halpha.dashboard import DashboardError
from halpha.dashboard.app import restart_dashboard_service, run_dashboard_service, start_dashboard_service
from halpha.dashboard.state import read_dashboard_selected_config_state, write_dashboard_selected_config_state
from halpha.runtime.service_lifecycle import ServiceLifecycleRepository


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_dashboard_foreground_records_shared_lifecycle_without_legacy_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    health_payload: dict[str, Any] = {}

    class FakeServer:
        def __init__(self, config: Any) -> None:
            self.config = config
            self.should_exit = False

        def run(self) -> None:
            health_payload.update(TestClient(self.config.app).get("/api/health").json())
            return None

    monkeypatch.setattr("uvicorn.Config", lambda app, *, host, port: SimpleNamespace(app=app, host=host, port=port))
    monkeypatch.setattr("uvicorn.Server", FakeServer)

    run_dashboard_service(None, config_path=None, host="127.0.0.1", port=8765)

    lifecycle = ServiceLifecycleRepository(runtime_root=tmp_path).inspect("core")
    assert lifecycle.status == "stopped"
    assert lifecycle.instance_id is not None
    assert health_payload["lifecycle"]["status"] == "running"
    assert health_payload["lifecycle"]["instance_id"] == lifecycle.instance_id
    assert lifecycle.state is not None
    assert lifecycle.state["endpoint"] == {
        "health_url": "http://127.0.0.1:8765/api/health",
        "host": "127.0.0.1",
        "port": 8765,
    }
    assert not (tmp_path / ".halpha" / "dashboard" / "service_state.json").exists()


def test_dashboard_start_returns_existing_shared_instance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = ServiceLifecycleRepository(runtime_root=tmp_path)
    result, ownership = repository.attempt_start_ownership(
        "core",
        config_ref="dashboard-service-unconfigured",
        config_digest=_dashboard_digest("127.0.0.1", 8765),
        endpoint={"host": "127.0.0.1", "port": 8765, "health_url": "http://127.0.0.1:8765/api/health"},
    )
    assert ownership is not None
    try:
        repository.register_started("core", instance_id=result.instance_id or "")
        monkeypatch.setattr("halpha.dashboard.app._dashboard_endpoint_can_bind", lambda host, port: False)
        monkeypatch.setattr(
            "halpha.dashboard.app._read_dashboard_endpoint_health",
            lambda host, port: {"service": "halpha_core"},
        )
        monkeypatch.setattr("halpha.dashboard.app.subprocess.Popen", _fail_popen)

        start = start_dashboard_service(None, host="127.0.0.1", port=8765)
    finally:
        ownership.release()

    assert start["status"] == "existing"
    assert start["instance_id"] == result.instance_id


def test_dashboard_start_conflicting_endpoint_does_not_launch_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = ServiceLifecycleRepository(runtime_root=tmp_path)
    result, ownership = repository.attempt_start_ownership(
        "core",
        config_ref="dashboard-service-unconfigured",
        config_digest=_dashboard_digest("127.0.0.1", 8765),
        endpoint={"host": "127.0.0.1", "port": 8765, "health_url": "http://127.0.0.1:8765/api/health"},
    )
    assert ownership is not None
    try:
        repository.register_started("core", instance_id=result.instance_id or "")
        monkeypatch.setattr("halpha.dashboard.app._dashboard_endpoint_can_bind", lambda host, port: True)
        monkeypatch.setattr("halpha.dashboard.app.subprocess.Popen", _fail_popen)

        with pytest.raises(DashboardError, match="different endpoint"):
            start_dashboard_service(None, host="127.0.0.1", port=9001)
    finally:
        ownership.release()


def test_dashboard_start_rejects_non_halpha_occupied_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("halpha.dashboard.app._dashboard_endpoint_can_bind", lambda host, port: False)
    monkeypatch.setattr(
        "halpha.dashboard.app._read_dashboard_endpoint_health",
        lambda host, port: {"service": "other"},
    )
    monkeypatch.setattr("halpha.dashboard.app.subprocess.Popen", _fail_popen)

    with pytest.raises(DashboardError, match="non-Halpha or unresponsive local service"):
        start_dashboard_service(None, host="127.0.0.1", port=8765)


def test_dashboard_restart_stops_then_starts_with_previous_instance_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = ServiceLifecycleRepository(runtime_root=tmp_path)
    result, ownership = repository.attempt_start_ownership(
        "core",
        config_ref="dashboard-service-unconfigured",
        config_digest=_dashboard_digest("127.0.0.1", 8765),
        endpoint={"host": "127.0.0.1", "port": 8765, "health_url": "http://127.0.0.1:8765/api/health"},
    )
    assert ownership is not None
    calls: list[tuple[str, str | None]] = []

    def fake_stop(config_arg, *, host, port):  # noqa: ANN001
        calls.append(("stop", None))
        return {"status": "stopped", "instance_id": result.instance_id, "endpoint": {"host": host, "port": port}}

    def fake_start(config_arg, *, host, port, restart_from_instance_id=None):  # noqa: ANN001
        calls.append(("start", restart_from_instance_id))
        return {"status": "started", "instance_id": "dashboard-next", "endpoint": {"host": host, "port": port}}

    try:
        repository.register_started("core", instance_id=result.instance_id or "")
        monkeypatch.setattr("halpha.dashboard.app.stop_dashboard_service", fake_stop)
        monkeypatch.setattr("halpha.dashboard.app.start_dashboard_service", fake_start)

        restarted = restart_dashboard_service(None, host="127.0.0.1", port=8765)
    finally:
        ownership.release()

    assert restarted["status"] == "started"
    assert calls == [("stop", None), ("start", result.instance_id)]


def test_dashboard_selected_config_uses_runtime_state_store(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("run:\n  output_dir: runs\n", encoding="utf-8")

    written = write_dashboard_selected_config_state(config_path)
    state, error = read_dashboard_selected_config_state()

    assert error is None
    assert state == written
    assert state["config_path"] == str(config_path)
    assert not (tmp_path / ".halpha" / "dashboard" / "selected_config.json").exists()
    state_store = tmp_path / ".halpha" / "state.sqlite"
    assert state_store.is_file()
    with sqlite3.connect(state_store) as connection:
        versions = [row[0] for row in connection.execute("SELECT version FROM schema_migrations ORDER BY version")]
    assert versions == [1, 8]


def _dashboard_digest(host: str, port: int) -> str:
    from hashlib import sha256

    return sha256(f"core-service-v1|host={host}|port={int(port)}".encode("utf-8")).hexdigest()


def _fail_popen(*args: Any, **kwargs: Any) -> Any:
    raise AssertionError("dashboard start must not launch a process")
