from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import time
from typing import Any

from halpha.config import load_config
from halpha.dashboard.core_scheduler import CoreScheduler
from halpha.dashboard.schedule import DashboardScheduleManager
from halpha.runtime.command_job_execution import CommandJobExecutionResult
from halpha.runtime.command_jobs import CommandJobManager


def test_core_scheduler_dispatches_due_daily_report_as_core(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    current = {"value": datetime(2026, 6, 20, 0, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr("halpha.dashboard.schedule._utc_now_datetime", lambda: current["value"])
    config_path = _write_config(tmp_path, monitor_enabled=False)
    config = load_config(config_path)
    stdout = "Halpha run succeeded.\nrun_id: run-core\nmanifest: runs/run-core/run_manifest.json\n"

    def fake_execute_command_job(*args: Any, **kwargs: Any) -> CommandJobExecutionResult:
        return CommandJobExecutionResult(exit_code=0, stdout=stdout)

    monkeypatch.setattr("halpha.runtime.command_jobs.execute_command_job", fake_execute_command_job)
    job_manager = CommandJobManager(config, config_path=config_path, execution_mode="internal")
    schedule_manager = DashboardScheduleManager(config, config_path=config_path, job_manager=job_manager)
    schedule_manager.enable_daily_report_schedule(
        {"time_of_day": "00:01", "timezone": "UTC", "job_intent": "run_no_codex"}
    )
    current["value"] = datetime(2026, 6, 20, 0, 2, tzinfo=timezone.utc)
    scheduler = CoreScheduler(config, config_path=config_path, job_manager=job_manager, schedule_manager=schedule_manager)

    tick = scheduler.run_once()

    dispatch = tick["schedule_dispatch"]
    assert tick["status"] == "available"
    assert dispatch["status"] == "available"
    job_id = dispatch["job"]["job_id"]
    completed = _wait_for_terminal(job_manager, job_id)
    assert completed["status"] == "succeeded"
    assert completed["intent"] == "run_no_codex"
    assert completed["requested_by"] == "Core"
    assert completed["requester"] == {
        "dispatch_kind": "automatic",
        "schedule_id": "daily_report",
        "source": "daily_report_schedule",
    }
    schedule = schedule_manager.read_daily_report_schedule()
    assert schedule["runtime_boundary"]["automatic_dispatch"] == "core_scheduler"
    assert schedule["linked_job_ids"] == [job_id]


def test_core_scheduler_skips_monitor_cycle_when_monitor_disabled(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, monitor_enabled=False)
    config = load_config(config_path)
    jobs = _RecordingJobManager()
    scheduler = CoreScheduler(config, config_path=config_path, job_manager=jobs, schedule_manager=_SkippingScheduleManager())

    tick = scheduler.run_once()

    assert tick["monitor_cycle_job"]["status"] == "skipped"
    assert tick["monitor_cycle_job"]["reason"] == "monitor.enabled is false."
    assert jobs.created_requests == []


def test_core_scheduler_creates_monitor_cycle_when_enabled(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, monitor_enabled=True)
    config = load_config(config_path)
    jobs = _RecordingJobManager()
    scheduler = CoreScheduler(config, config_path=config_path, job_manager=jobs, schedule_manager=_SkippingScheduleManager())

    tick = scheduler.run_once()

    assert tick["monitor_cycle_job"]["status"] == "available"
    assert jobs.created_requests == [
        {
            "intent": "monitor_once",
            "params": {},
            "requested_by": "Core",
            "requester": {
                "source": "core_scheduler",
                "tick_id": tick["tick_id"],
            },
        }
    ]


def test_core_scheduler_skips_duplicate_transient_monitor_cycle(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, monitor_enabled=True)
    config = load_config(config_path)
    jobs = _RecordingJobManager(
        jobs=[
            {
                "job_id": "job-running",
                "kind": "monitor_cycle",
                "intent": "monitor_once",
                "status": "running",
            }
        ]
    )
    scheduler = CoreScheduler(config, config_path=config_path, job_manager=jobs, schedule_manager=_SkippingScheduleManager())

    tick = scheduler.run_once()

    assert tick["monitor_cycle_job"]["status"] == "skipped"
    assert tick["monitor_cycle_job"]["job"]["job_id"] == "job-running"
    assert jobs.created_requests == []


def test_core_scheduler_skips_recent_terminal_monitor_cycle(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, monitor_enabled=True)
    config = load_config(config_path)
    recent = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat().replace("+00:00", "Z")
    jobs = _RecordingJobManager(
        jobs=[
            {
                "job_id": "job-succeeded",
                "kind": "monitor_cycle",
                "intent": "monitor_once",
                "status": "succeeded",
                "created_at": recent,
            }
        ]
    )
    scheduler = CoreScheduler(config, config_path=config_path, job_manager=jobs, schedule_manager=_SkippingScheduleManager())

    tick = scheduler.run_once()

    assert tick["monitor_cycle_job"]["status"] == "skipped"
    assert tick["monitor_cycle_job"]["reason"] == "monitor cycle interval has not elapsed."
    assert tick["monitor_cycle_job"]["job"]["job_id"] == "job-succeeded"
    assert jobs.created_requests == []


class _SkippingScheduleManager:
    def dispatch_due_daily_report(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "artifact_type": "dashboard_daily_report_dispatch",
            "status": "skipped",
            "schedule": {"enabled": False, "next_run_at": None},
            "job": None,
            "warnings": ["daily report schedule is disabled."],
            "errors": [],
        }

    def next_due_seconds(self) -> float:
        return 300.0


class _RecordingJobManager:
    def __init__(self, *, jobs: list[dict[str, Any]] | None = None) -> None:
        self.jobs = list(jobs or [])
        self.created_requests: list[dict[str, Any]] = []

    def list_jobs(self, *, limit: int = 100) -> dict[str, Any]:
        return {"jobs": self.jobs[:limit]}

    def create_job(self, request: dict[str, Any]) -> dict[str, Any]:
        self.created_requests.append(request)
        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        job = {
            "schema_version": 1,
            "artifact_type": "command_job",
            "job_id": f"job-{len(self.created_requests)}",
            "kind": "monitor_cycle",
            "intent": request.get("intent"),
            "requested_by": request.get("requested_by"),
            "requester": request.get("requester"),
            "status": "queued",
            "created_at": created_at,
            "warnings": [],
            "errors": [],
        }
        self.jobs.insert(0, job)
        return job


def _write_config(tmp_path: Path, *, monitor_enabled: bool) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
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
  enabled: {str(monitor_enabled).lower()}
  interval_seconds: 300
  max_cycles: 1
  failure_backoff_max_seconds: 3600
  cooldown_seconds: 3600
  output_dir: runs/monitor
  target_stage: build_materials
  no_codex: true
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _wait_for_terminal(manager: CommandJobManager, job_id: str) -> dict[str, Any]:
    for _ in range(50):
        job = manager.get_job(job_id)
        if job and job["status"] in {"succeeded", "failed", "cancelled", "unsupported", "blocked"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"job did not finish: {job_id}")
