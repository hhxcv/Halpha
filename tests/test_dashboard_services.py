from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pytest
from fastapi.testclient import TestClient

from halpha.config import load_config
from halpha.dashboard import create_dashboard_app
from halpha.runtime.monitor_service import _monitor_service_config_digest
from halpha.runtime.service_lifecycle import ServiceLifecycleRepository


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_dashboard_services_endpoint_reports_exact_service_roles_without_config() -> None:
    client = TestClient(create_dashboard_app())

    payload = client.get("/api/services").json()

    assert payload["artifact_type"] == "dashboard_services"
    assert payload["status"] == "unconfigured"
    assert set(payload["services"]) == {"core", "monitor"}
    assert payload["services"]["core"]["role"] == "core"
    assert payload["services"]["core"]["status"] == "unmanaged"
    assert payload["services"]["monitor"]["status"] == "unconfigured"


@pytest.mark.parametrize(
    (
        "role",
        "digest_function",
        "launch_patch_target",
        "endpoint_service",
        "api_path",
    ),
    [
        pytest.param(
            "monitor",
            _monitor_service_config_digest,
            "halpha.runtime.monitor_service._launch_monitor_service_process",
            "halpha_monitor",
            "/api/services/monitor/start",
            id="monitor",
        ),
    ],
)
def test_dashboard_service_action_delegates_start_to_shared_lifecycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    role: str,
    digest_function: Callable[..., str],
    launch_patch_target: str,
    endpoint_service: str,
    api_path: str,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    repository = ServiceLifecycleRepository(runtime_root=tmp_path)
    result, ownership = repository.attempt_start_ownership(
        role,
        config_ref="<external-config>",
        config_digest=digest_function(config, config_path=config_path),
        endpoint={"service": endpoint_service},
    )
    assert ownership is not None
    try:
        repository.register_started(role, instance_id=result.instance_id or "")
        monkeypatch.setattr(launch_patch_target, _fail_launch)
        client = TestClient(create_dashboard_app(config, config_path=config_path))

        payload = client.post(api_path).json()
    finally:
        ownership.release()

    assert payload["artifact_type"] == "dashboard_service_action"
    assert payload["status"] == "existing"
    assert payload["role"] == role
    assert payload["action"] == "start"
    assert payload["service"]["instance_id"] == result.instance_id
    assert payload["service"]["config_conflict"] is False


def test_dashboard_service_action_surfaces_monitor_config_conflict_without_launch_or_private_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    repository = ServiceLifecycleRepository(runtime_root=tmp_path)
    result, ownership = repository.attempt_start_ownership(
        "monitor",
        config_ref="<external-config>",
        config_digest="other-digest",
        endpoint={"service": "halpha_monitor"},
    )
    assert ownership is not None
    try:
        repository.register_started("monitor", instance_id=result.instance_id or "")
        monkeypatch.setattr("halpha.runtime.monitor_service._launch_monitor_service_process", _fail_launch)
        client = TestClient(create_dashboard_app(config, config_path=config_path))

        payload = client.post("/api/services/monitor/start").json()
    finally:
        ownership.release()

    assert payload["status"] == "conflict"
    assert payload["service"]["instance_id"] == result.instance_id
    assert payload["service"]["config_conflict"] is True
    assert "different service configuration" in payload["errors"][0]
    assert str(tmp_path) not in str(payload)


def test_dashboard_schedule_can_be_enabled_without_schedule_service_role(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    enabled = client.post("/api/schedule/daily-report/enable", json={"job_intent": "run_no_codex"}).json()
    schedule = client.get("/api/schedule/daily-report").json()
    services = client.get("/api/services").json()

    assert enabled["enabled"] is True
    assert schedule["enabled"] is True
    assert "schedule" not in services["services"]


def test_dashboard_config_switch_does_not_stop_existing_monitor_service(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, name="config-a.yaml", monitor_interval=60)
    next_config_path = _write_config(tmp_path, name="config-b.yaml", monitor_interval=120)
    config = load_config(config_path)
    next_config = load_config(next_config_path)
    repository = ServiceLifecycleRepository(runtime_root=tmp_path)
    result, ownership = repository.attempt_start_ownership(
        "monitor",
        config_ref="<external-config>",
        config_digest=_monitor_service_config_digest(config, config_path=config_path),
        endpoint={"service": "halpha_monitor"},
    )
    assert ownership is not None
    try:
        repository.register_started("monitor", instance_id=result.instance_id or "")
        client = TestClient(create_dashboard_app(config, config_path=config_path))

        selected = client.post("/api/config/select", json={"config_path": str(next_config_path)}).json()
        services = client.get("/api/services").json()
        lifecycle = repository.inspect("monitor")
    finally:
        ownership.release()

    assert selected["status"] == "succeeded"
    assert lifecycle.status == "running"
    assert lifecycle.instance_id == result.instance_id
    assert services["services"]["monitor"]["instance_id"] == result.instance_id
    assert services["services"]["monitor"]["config_conflict"] is True
    assert _monitor_service_config_digest(next_config, config_path=next_config_path) != _monitor_service_config_digest(
        config,
        config_path=config_path,
    )


def test_dashboard_rejects_core_role_action_without_lifecycle_side_effect(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    payload = client.post("/api/services/core/stop").json()

    assert payload["status"] == "blocked"
    assert payload["role"] == "core"
    assert payload["service"] is None


def test_dashboard_live_endpoint_returns_disabled_read_model(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    payload = client.get("/api/live").json()

    assert payload["artifact_type"] == "dashboard_live"
    assert payload["status"] == "disabled"
    assert payload["scheduler"] == {"enabled": False, "tick_seconds": 30, "source": "core"}
    assert payload["active_jobs"] == []
    assert payload["recent_jobs"] == []


def _service_result(role: str, service: str, *, status: str, instance_id: str) -> dict[str, Any]:
    return {
        "status": status,
        "service": service,
        "instance_id": instance_id,
        "pid": None,
        "lifecycle": {
            "status": "running" if status in {"started", "existing"} else status,
            "role": role,
            "instance_id": instance_id,
            "config_ref": "<external-config>",
            "config_digest": None,
            "heartbeat_at": "2026-06-24T00:00:00Z",
            "last_error": {},
        },
        "warnings": [],
        "errors": [],
    }


def _fail_launch(*args: Any, **kwargs: Any) -> Any:
    raise AssertionError("dashboard controls must use the existing shared lifecycle instance")


def _write_config(
    tmp_path: Path,
    *,
    name: str = "config.yaml",
    monitor_interval: int = 60,
) -> Path:
    path = tmp_path / name
    path.write_text(
        f"""
run:
  output_dir: runs
  timezone: UTC
market:
  enabled: false
monitor:
  interval_seconds: {monitor_interval}
  output_dir: runs/monitor
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
