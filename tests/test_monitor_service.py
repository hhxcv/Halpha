from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from halpha.config import load_config
from halpha.monitor.state_store import MonitorStateRepository
from halpha.runtime.monitor_service import (
    MonitorServiceError,
    _monitor_service_config_digest,
    monitor_service_status,
    restart_monitor_service,
    run_monitor_service,
    start_monitor_service,
    stop_monitor_service,
)
from halpha.runtime.service_lifecycle import ServiceLifecycleRepository


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_monitor_start_returns_existing_shared_instance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
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
        monkeypatch.setattr("halpha.runtime.monitor_service._launch_monitor_service_process", _fail_launch)

        start = start_monitor_service(str(config_path))
    finally:
        ownership.release()

    assert start["status"] == "existing"
    assert start["instance_id"] == result.instance_id


def test_monitor_start_conflicting_config_does_not_launch_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
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

        with pytest.raises(MonitorServiceError, match="different service configuration"):
            start_monitor_service(str(config_path))
    finally:
        ownership.release()


def test_monitor_status_and_stop_do_not_require_loadable_config(tmp_path: Path) -> None:
    config_path = tmp_path / "broken.yaml"
    config_path.write_text("run: [", encoding="utf-8")

    status = monitor_service_status(str(config_path))
    stopped = stop_monitor_service(str(config_path))

    assert status["status"] == "not_found"
    assert stopped["status"] == "not_found"


def test_monitor_restart_launches_with_previous_terminal_instance_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    repository = ServiceLifecycleRepository(runtime_root=tmp_path)
    result, ownership = repository.attempt_start_ownership(
        "monitor",
        config_ref="<external-config>",
        config_digest="digest-a",
        endpoint={"service": "halpha_monitor"},
    )
    assert ownership is not None
    instance_id = result.instance_id or ""
    try:
        repository.register_started("monitor", instance_id=instance_id)
        repository.record_terminal_exit("monitor", instance_id=instance_id, status="stopped", exit_code=0)
    finally:
        ownership.release()
    launched: dict[str, Any] = {}

    def fake_launch(config_arg: str, *, restart_from_instance_id: str | None) -> _FakeProcess:
        launched["config_arg"] = config_arg
        launched["restart_from_instance_id"] = restart_from_instance_id
        return _FakeProcess()

    def fake_wait(process: _FakeProcess, *, repository, config_digest, timeout_seconds):  # noqa: ANN001
        return {"status": "started", "instance_id": "monitor-next", "pid": None, "warnings": [], "errors": []}

    monkeypatch.setattr("halpha.runtime.monitor_service._launch_monitor_service_process", fake_launch)
    monkeypatch.setattr("halpha.runtime.monitor_service._wait_for_monitor_service_start", fake_wait)

    restarted = restart_monitor_service(str(config_path))

    assert restarted["status"] == "started"
    assert launched == {
        "config_arg": str(config_path),
        "restart_from_instance_id": instance_id,
    }


def test_monitor_service_triggers_core_schedule_and_monitor_jobs(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, no_codex=False, text_enabled=True)
    config = load_config(config_path)
    core_client = _FakeCoreClient()
    sleeps: list[float] = []

    run_monitor_service(
        config,
        config_path=config_path,
        max_cycles=2,
        sleeper=lambda seconds: sleeps.append(seconds),
        core_client=core_client,
    )

    health_state = _health_state(config_path)

    assert core_client.ensure_calls == 2
    assert core_client.dispatch_calls == 2
    assert core_client.monitor_job_calls == [
        {"instance_id": health_state["service"]["service_instance_id"], "cycle_sequence": 1},
        {"instance_id": health_state["service"]["service_instance_id"], "cycle_sequence": 2},
    ]
    assert health_state["cycle_count"] == 0
    assert health_state["latest_cycle_status"] == "missing"
    assert health_state["service"]["status"] == "stopped"
    assert sum(sleeps) == pytest.approx(1.0)
    assert not (tmp_path / "monitor" / "monitor_health_state.json").exists()


def test_monitor_service_observes_graceful_stop_during_wait(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, interval_seconds=5, text_enabled=True)
    config = load_config(config_path)
    repository = ServiceLifecycleRepository(runtime_root=tmp_path)
    core_client = _FakeCoreClient()
    sleep_calls = 0

    def request_stop(seconds: float) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        lifecycle = repository.inspect("monitor")
        assert lifecycle.instance_id is not None
        repository.request_graceful_stop("monitor", instance_id=lifecycle.instance_id)

    run_monitor_service(
        config,
        config_path=config_path,
        sleeper=request_stop,
        core_client=core_client,
    )

    health_state = _health_state(config_path)

    assert core_client.ensure_calls == 1
    assert core_client.dispatch_calls == 1
    assert health_state["cycle_count"] == 0
    assert health_state["service"]["status"] == "stopped"
    assert sleep_calls == 1


def test_monitor_service_records_core_dispatch_failure(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, interval_seconds=1, text_enabled=True)
    config = load_config(config_path)
    core_client = _FakeCoreClient(fail_dispatch=True)
    sleeps: list[float] = []

    run_monitor_service(
        config,
        config_path=config_path,
        max_cycles=1,
        sleeper=lambda seconds: sleeps.append(seconds),
        core_client=core_client,
    )

    health_state = _health_state(config_path)

    assert core_client.ensure_calls == 1
    assert core_client.dispatch_calls == 1
    assert core_client.monitor_job_calls == []
    assert health_state["service"]["status"] == "stopped"
    assert health_state["service"]["last_error"]["message"] == "core dispatch failed"


class _FakeProcess:
    def poll(self) -> int | None:
        return None


def _fail_launch(*args: Any, **kwargs: Any) -> Any:
    raise AssertionError("monitor service start must not launch a process")


class _FakeCoreClient:
    def __init__(self, *, fail_dispatch: bool = False) -> None:
        self.fail_dispatch = fail_dispatch
        self.ensure_calls = 0
        self.dispatch_calls = 0
        self.monitor_job_calls: list[dict[str, Any]] = []

    def ensure_running(self) -> dict[str, Any]:
        self.ensure_calls += 1
        return {"status": "running", "instance_id": "core-1"}

    def dispatch_due_daily_report(self) -> dict[str, Any]:
        self.dispatch_calls += 1
        if self.fail_dispatch:
            raise RuntimeError("core dispatch failed")
        return {
            "status": "skipped",
            "schedule": {"enabled": False, "next_run_at": None},
            "job": None,
            "warnings": ["daily report schedule is disabled."],
            "errors": [],
        }

    def create_monitor_cycle_job(self, *, instance_id: str, cycle_sequence: int) -> dict[str, Any]:
        self.monitor_job_calls.append({"instance_id": instance_id, "cycle_sequence": cycle_sequence})
        return {"status": "queued", "job_id": f"job-{cycle_sequence}"}


def _write_config(
    tmp_path: Path,
    *,
    interval_seconds: int = 1,
    failure_backoff_max_seconds: int = 4,
    no_codex: bool = True,
    text_enabled: bool = False,
) -> Path:
    path = tmp_path / "config.yaml"
    text_sources = (
        """
  sources:
    - name: feed
      type: rss
      url: https://example.invalid/feed.xml
""".rstrip()
        if text_enabled
        else "  sources: []"
    )
    path.write_text(
        f"""
run:
  output_dir: runs
  timezone: UTC
market:
  enabled: false
text:
  enabled: {str(text_enabled).lower()}
{text_sources}
report:
  language: zh-CN
codex:
  enabled: false
monitor:
  output_dir: monitor
  interval_seconds: {interval_seconds}
  failure_backoff_max_seconds: {failure_backoff_max_seconds}
  cooldown_seconds: 3600
  target_stage: build_materials
  no_codex: {str(no_codex).lower()}
""".strip(),
        encoding="utf-8",
    )
    return path


def _health_state(config_path: Path) -> dict[str, Any]:
    return MonitorStateRepository(config_path=config_path).health_state(monitor_output_dir="monitor", base=config_path.parent)
