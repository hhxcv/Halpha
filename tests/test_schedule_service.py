from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from halpha.config import load_config
from halpha.runtime.schedule_service import (
    ScheduleServiceError,
    _schedule_service_config_digest,
    restart_schedule_service,
    schedule_service_status,
    start_schedule_service,
    stop_schedule_service,
)
from halpha.runtime.service_lifecycle import ServiceLifecycleRepository


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_schedule_start_returns_existing_shared_instance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    repository = ServiceLifecycleRepository(runtime_root=tmp_path)
    result, ownership = repository.attempt_start_ownership(
        "schedule",
        config_ref="<external-config>",
        config_digest=_schedule_service_config_digest(config, config_path=config_path),
        endpoint={"service": "halpha_schedule"},
    )
    assert ownership is not None
    try:
        repository.register_started("schedule", instance_id=result.instance_id or "")
        monkeypatch.setattr("halpha.runtime.schedule_service._launch_schedule_service_process", _fail_launch)

        start = start_schedule_service(str(config_path))
    finally:
        ownership.release()

    assert start["status"] == "existing"
    assert start["instance_id"] == result.instance_id


def test_schedule_start_conflicting_config_does_not_launch_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    repository = ServiceLifecycleRepository(runtime_root=tmp_path)
    result, ownership = repository.attempt_start_ownership(
        "schedule",
        config_ref="<external-config>",
        config_digest="other-digest",
        endpoint={"service": "halpha_schedule"},
    )
    assert ownership is not None
    try:
        repository.register_started("schedule", instance_id=result.instance_id or "")
        monkeypatch.setattr("halpha.runtime.schedule_service._launch_schedule_service_process", _fail_launch)

        with pytest.raises(ScheduleServiceError, match="different service configuration"):
            start_schedule_service(str(config_path))
    finally:
        ownership.release()


def test_schedule_stop_requests_running_instance(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    repository = ServiceLifecycleRepository(runtime_root=tmp_path)
    result, ownership = repository.attempt_start_ownership(
        "schedule",
        config_ref="<external-config>",
        config_digest="digest-a",
        endpoint={"service": "halpha_schedule"},
    )
    assert ownership is not None
    try:
        repository.register_started("schedule", instance_id=result.instance_id or "")

        stopped = stop_schedule_service(str(config_path))
        status = schedule_service_status(str(config_path))
    finally:
        ownership.release()

    assert stopped["status"] == "stop_requested"
    assert stopped["instance_id"] == result.instance_id
    assert status["status"] == "stop_requested"


def test_schedule_status_and_stop_do_not_require_loadable_config(tmp_path: Path) -> None:
    config_path = tmp_path / "broken.yaml"
    config_path.write_text("run: [", encoding="utf-8")

    status = schedule_service_status(str(config_path))
    stopped = stop_schedule_service(str(config_path))

    assert status["status"] == "not_found"
    assert stopped["status"] == "not_found"


def test_schedule_restart_launches_with_previous_terminal_instance_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    repository = ServiceLifecycleRepository(runtime_root=tmp_path)
    result, ownership = repository.attempt_start_ownership(
        "schedule",
        config_ref="<external-config>",
        config_digest="digest-a",
        endpoint={"service": "halpha_schedule"},
    )
    assert ownership is not None
    instance_id = result.instance_id or ""
    try:
        repository.register_started("schedule", instance_id=instance_id)
        repository.record_terminal_exit("schedule", instance_id=instance_id, status="stopped", exit_code=0)
    finally:
        ownership.release()
    launched: dict[str, Any] = {}

    def fake_launch(config_arg: str, *, restart_from_instance_id: str | None) -> _FakeProcess:
        launched["config_arg"] = config_arg
        launched["restart_from_instance_id"] = restart_from_instance_id
        return _FakeProcess()

    def fake_wait(process: _FakeProcess, *, repository, config_digest, timeout_seconds):  # noqa: ANN001
        return {"status": "started", "instance_id": "schedule-next", "pid": None, "warnings": [], "errors": []}

    monkeypatch.setattr("halpha.runtime.schedule_service._launch_schedule_service_process", fake_launch)
    monkeypatch.setattr("halpha.runtime.schedule_service._wait_for_schedule_service_start", fake_wait)

    restarted = restart_schedule_service(str(config_path))

    assert restarted["status"] == "started"
    assert launched == {
        "config_arg": str(config_path),
        "restart_from_instance_id": instance_id,
    }


class _FakeProcess:
    def poll(self) -> int | None:
        return None


def _fail_launch(*args: Any, **kwargs: Any) -> Any:
    raise AssertionError("schedule service start must not launch a process")


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
run:
  output_dir: runs
  timezone: UTC
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
