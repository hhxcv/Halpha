from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
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


def test_monitor_service_continues_after_failed_cycle_and_resets_backoff(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, no_codex=False)
    config = load_config(config_path)
    pipeline_calls: list[dict[str, Any]] = []
    sleeps: list[float] = []

    run_monitor_service(
        config,
        config_path=config_path,
        max_cycles=2,
        pipeline_runner=_pipeline_factory(tmp_path, statuses=["failed", "succeeded"], calls=pipeline_calls),
        sleeper=lambda seconds: sleeps.append(seconds),
    )

    health_state = _health_state(config_path)
    manifests = _cycle_manifests(tmp_path)

    assert len(manifests) == 2
    assert [manifest["status"] for manifest in manifests] == ["failed", "succeeded"]
    assert {manifest["cycle_mode"] for manifest in manifests} == {"service"}
    assert {manifest["trigger_source"] for manifest in manifests} == {"monitor_service"}
    assert all(call["skip_codex"] is True for call in pipeline_calls)
    assert health_state["cycle_count"] == 2
    assert health_state["failed_cycle_count"] == 1
    assert health_state["service"]["status"] == "stopped"
    assert health_state["service"]["consecutive_failures"] == 0
    assert health_state["service"]["next_retry_at"] is None
    assert health_state["service"]["last_error"] == {}
    assert sum(sleeps) == pytest.approx(1.0)
    assert not (tmp_path / "monitor" / "monitor_health_state.json").exists()


def test_monitor_service_backs_off_recoverable_failures_with_configured_cap(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, interval_seconds=2, failure_backoff_max_seconds=3)
    config = load_config(config_path)
    sleeps: list[float] = []

    run_monitor_service(
        config,
        config_path=config_path,
        max_cycles=3,
        pipeline_runner=_pipeline_factory(tmp_path, statuses=["failed", "failed", "failed"]),
        sleeper=lambda seconds: sleeps.append(seconds),
    )

    health_state = _health_state(config_path)

    assert health_state["failed_cycle_count"] == 3
    assert health_state["service"]["consecutive_failures"] == 3
    assert health_state["service"]["last_error"]["message"] == "simulated source failure"
    assert sum(sleeps) == pytest.approx(5.0)


def test_monitor_service_observes_graceful_stop_during_wait(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, interval_seconds=5)
    config = load_config(config_path)
    repository = ServiceLifecycleRepository(runtime_root=tmp_path)
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
        pipeline_runner=_pipeline_factory(tmp_path, statuses=["succeeded", "succeeded"]),
        sleeper=request_stop,
    )

    health_state = _health_state(config_path)

    assert health_state["cycle_count"] == 1
    assert health_state["service"]["status"] == "stopped"
    assert sleep_calls == 1


class _FakeProcess:
    def poll(self) -> int | None:
        return None


def _fail_launch(*args: Any, **kwargs: Any) -> Any:
    raise AssertionError("monitor service start must not launch a process")


def _write_config(
    tmp_path: Path,
    *,
    interval_seconds: int = 1,
    failure_backoff_max_seconds: int = 4,
    no_codex: bool = True,
) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        f"""
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


def _pipeline_factory(
    tmp_path: Path,
    *,
    statuses: list[str],
    calls: list[dict[str, Any]] | None = None,
):
    state = {"count": 0}

    def pipeline(config, *, config_path, until_stage, skip_codex):  # noqa: ANN001
        state["count"] += 1
        if calls is not None:
            calls.append({"until_stage": until_stage, "skip_codex": skip_codex, "monitor": dict(config.get("monitor", {}))})
        status = statuses[state["count"] - 1]
        run_id = f"run-{state['count']}"
        run_dir = tmp_path / "runs" / run_id
        analysis_dir = run_dir / "analysis"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        artifacts = {}
        if status == "succeeded":
            (analysis_dir / "alert_decisions.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "artifact_type": "alert_decisions",
                        "records": [_alert_record()],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            artifacts = {"alert_decisions": "analysis/alert_decisions.json"}
        return SimpleNamespace(
            succeeded=status == "succeeded",
            exit_code=0 if status == "succeeded" else 3,
            failed_stage=None if status == "succeeded" else "collect_market_data",
            reason=None if status == "succeeded" else "simulated source failure",
            run=SimpleNamespace(
                run_id=run_id,
                run_dir=run_dir,
                manifest_path=run_dir / "run_manifest.json",
                manifest={"status": status, "artifacts": artifacts, "stages": []},
            ),
        )

    return pipeline


def _alert_record() -> dict[str, Any]:
    return {
        "alert_decision_id": "alert_decision:BTCUSDT:1d:assessment-1",
        "status": "active",
        "priority": "P1",
        "scope": {
            "symbol": "BTCUSDT",
            "timeframe": "1d",
            "assessment_id": "assessment-1",
            "topic_ids": ["topic-1"],
            "event_signal_ids": ["signal-1"],
        },
        "attention_decision": "review_soon",
        "requires_user_attention": True,
        "source_artifacts": ["analysis/alert_decisions.json"],
    }


def _cycle_manifests(tmp_path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((tmp_path / "monitor" / "cycles").glob("*/monitor_cycle_manifest.json"))
    ]


def _health_state(config_path: Path) -> dict[str, Any]:
    return MonitorStateRepository(config_path=config_path).health_state(monitor_output_dir="monitor", base=config_path.parent)
