from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import time

import pytest
from fastapi.testclient import TestClient

from halpha.config import load_config
from halpha.dashboard import create_dashboard_app
from halpha.dashboard.jobs import DashboardJobManager
from halpha.dashboard.schedule import DashboardScheduleManager


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_dashboard_daily_report_schedule_reports_missing_state(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/schedule/daily-report")

    assert response.status_code == 200
    payload = response.json()
    assert payload["artifact_type"] == "dashboard_daily_report_schedule"
    assert payload["status"] == "missing"
    assert payload["enabled"] is False
    assert payload["persisted"] is False
    assert payload["settings"]["job_intent"] == "run"
    assert payload["report_generation"]["generates_report"] is True
    assert payload["report_generation"]["requires_codex_confirmation"] is True
    assert payload["next_run_at"] is None
    assert payload["source_artifacts"] == ["runs/dashboard/schedules/daily_report_schedule.json"]
    assert payload["runtime_boundary"]["hidden_service"] is False
    assert payload["runtime_boundary"]["hosted_scheduler"] is False
    assert str(tmp_path) not in response.text


def test_dashboard_daily_report_schedule_defaults_to_east_8_without_run_timezone(tmp_path: Path) -> None:
    config_path = _write_config_without_run_timezone(tmp_path)
    config = load_config(config_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/schedule/daily-report")

    assert response.status_code == 200
    assert response.json()["settings"]["timezone"] == "Asia/Shanghai"


def test_dashboard_daily_report_schedule_enable_disable_and_persistence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "halpha.dashboard.schedule._utc_now_datetime",
        lambda: datetime(2026, 6, 20, 1, 0, tzinfo=timezone.utc),
    )
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    enable_response = client.post(
        "/api/schedule/daily-report/enable",
        json={"time_of_day": "08:30", "timezone": "UTC", "job_intent": "run_no_codex"},
    )
    read_response = TestClient(create_dashboard_app(config, config_path=config_path)).get("/api/schedule/daily-report")
    disable_response = client.post("/api/schedule/daily-report/disable")

    assert enable_response.status_code == 200
    enabled = enable_response.json()
    assert enabled["status"] == "available"
    assert enabled["enabled"] is True
    assert enabled["persisted"] is True
    assert enabled["settings"]["time_of_day"] == "08:30"
    assert enabled["settings"]["timezone"] == "UTC"
    assert enabled["settings"]["job_intent"] == "run_no_codex"
    assert enabled["report_generation"]["generates_report"] is False
    assert enabled["report_generation"]["requires_codex_confirmation"] is False
    assert enabled["next_run_at"] == "2026-06-20T08:30:00Z"
    assert (tmp_path / "runs" / "dashboard" / "schedules" / "daily_report_schedule.json").is_file()

    persisted = read_response.json()
    assert persisted["enabled"] is True
    assert persisted["next_run_at"] == "2026-06-20T08:30:00Z"

    disabled = disable_response.json()
    assert disabled["enabled"] is False
    assert disabled["next_run_at"] is None
    assert disabled["settings"]["time_of_day"] == "08:30"


def test_dashboard_daily_report_schedule_rejects_invalid_input_before_persistence(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))
    cases = [
        ({"time_of_day": "25:00"}, "time_of_day must use HH:MM 24-hour format."),
        ({"timezone": "Invalid/Zone"}, "timezone is not available: Invalid/Zone."),
        ({"enabled": "yes"}, "enabled must be a boolean."),
        ({"surprise": True}, "unsupported daily report schedule field(s): surprise."),
    ]

    for request, error in cases:
        response = client.post("/api/schedule/daily-report", json=request)
        payload = response.json()
        assert response.status_code == 200
        assert payload["status"] == "blocked"
        assert payload["errors"] == [error]

    assert not (tmp_path / "runs" / "dashboard" / "schedules" / "daily_report_schedule.json").exists()


def test_dashboard_daily_report_schedule_enable_requires_explicit_mode(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.post("/api/schedule/daily-report/enable", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked"
    assert payload["enabled"] is False
    assert payload["errors"] == ["job_intent must be selected before enabling the daily report schedule."]
    assert not (tmp_path / "runs" / "dashboard" / "schedules" / "daily_report_schedule.json").exists()


def test_dashboard_daily_report_schedule_manual_trigger_creates_visible_job(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "halpha.dashboard.schedule._utc_now_datetime",
        lambda: datetime(2026, 6, 20, 1, 0, tzinfo=timezone.utc),
    )
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    commands: list[list[str]] = []

    def fake_popen(command, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        commands.append(command)
        return _FakeProcess(
            stdout="\n".join(
                [
                    "Halpha run succeeded.",
                    "run_id: run-1",
                    "report: runs/run-1/report/report.md",
                    "manifest: runs/run-1/run_manifest.json",
                ]
            ),
            stderr="",
            returncode=0,
        )

    monkeypatch.setattr("halpha.dashboard.jobs.subprocess.Popen", fake_popen)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    client.post(
        "/api/schedule/daily-report/enable",
        json={"time_of_day": "08:30", "timezone": "UTC", "job_intent": "run_no_codex"},
    )
    trigger_response = client.post("/api/schedule/daily-report/trigger", json={})
    trigger_payload = trigger_response.json()
    job_id = trigger_payload["job"]["job_id"]
    completed = _wait_for_api_terminal(client, job_id)
    schedule_response = client.get("/api/schedule/daily-report")

    assert trigger_response.status_code == 200
    assert trigger_payload["artifact_type"] == "dashboard_daily_report_schedule_trigger"
    assert trigger_payload["status"] == "available"
    assert trigger_payload["schedule"]["last_run_at"] == "2026-06-20T01:00:00Z"
    assert trigger_payload["schedule"]["last_job_id"] == job_id
    assert trigger_payload["schedule"]["linked_job_ids"] == [job_id]
    assert trigger_payload["schedule"]["report_generation"]["generates_report"] is False
    assert completed["status"] == "succeeded"
    assert completed["intent"] == "run_no_codex"
    assert completed["command"] == ["python", "-m", "halpha", "run", "--config", "<external-config>", "--no-codex"]
    assert schedule_response.json()["last_job_id"] == job_id
    assert commands == [[commands[0][0], "-m", "halpha", "run", "--config", str(config_path), "--no-codex"]]
    assert str(tmp_path) not in trigger_response.text
    assert str(tmp_path) not in schedule_response.text


def test_dashboard_daily_report_schedule_codex_trigger_requires_confirmation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("Codex-capable scheduled trigger must require confirmation before process start")

    monkeypatch.setattr("halpha.dashboard.jobs.subprocess.Popen", fail_popen)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.post("/api/schedule/daily-report/trigger", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked"
    assert payload["job"] is None
    assert payload["errors"] == ["confirm_codex must be true to trigger a Codex-capable daily report job."]


def test_dashboard_daily_report_schedule_confirmed_codex_trigger_creates_report_job(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    commands: list[list[str]] = []

    def fake_popen(command, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        commands.append(command)
        return _FakeProcess(
            stdout="\n".join(
                [
                    "Halpha run succeeded.",
                    "run_id: run-1",
                    "report: runs/run-1/report/report.md",
                    "manifest: runs/run-1/run_manifest.json",
                ]
            ),
            stderr="",
            returncode=0,
        )

    monkeypatch.setattr("halpha.dashboard.jobs.subprocess.Popen", fake_popen)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    client.post(
        "/api/schedule/daily-report/enable",
        json={"time_of_day": "08:30", "timezone": "UTC", "job_intent": "run"},
    )
    trigger_response = client.post("/api/schedule/daily-report/trigger", json={"confirm_codex": True})
    trigger_payload = trigger_response.json()
    job_id = trigger_payload["job"]["job_id"]
    completed = _wait_for_api_terminal(client, job_id)

    assert trigger_response.status_code == 200
    assert trigger_payload["status"] == "available"
    assert trigger_payload["schedule"]["settings"]["job_intent"] == "run"
    assert trigger_payload["schedule"]["report_generation"]["generates_report"] is True
    assert completed["status"] == "succeeded"
    assert completed["intent"] == "run"
    assert completed["command"] == ["python", "-m", "halpha", "run", "--config", "<external-config>"]
    assert commands == [[commands[0][0], "-m", "halpha", "run", "--config", str(config_path)]]


def test_dashboard_daily_report_explicit_no_codex_enable_dispatches_due_job(
    tmp_path: Path,
    monkeypatch,
) -> None:
    current = {"value": datetime(2026, 6, 20, 0, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr("halpha.dashboard.schedule._utc_now_datetime", lambda: current["value"])
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    commands: list[list[str]] = []

    def fake_popen(command, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        commands.append(command)
        return _FakeProcess(stdout="Halpha run succeeded.\nrun_id: run-auto", stderr="", returncode=0)

    monkeypatch.setattr("halpha.dashboard.jobs.subprocess.Popen", fake_popen)
    job_manager = DashboardJobManager(config, config_path=config_path)
    schedule_manager = DashboardScheduleManager(config, config_path=config_path, job_manager=job_manager)
    enabled = schedule_manager.enable_daily_report_schedule(
        {"time_of_day": "00:01", "timezone": "UTC", "job_intent": "run_no_codex"}
    )
    current["value"] = datetime(2026, 6, 20, 0, 2, tzinfo=timezone.utc)

    result = schedule_manager.dispatch_due_daily_report()

    assert enabled["settings"]["job_intent"] == "run_no_codex"
    assert enabled["report_generation"]["generates_report"] is False
    assert result["status"] == "available"
    assert result["job"]["intent"] == "run_no_codex"
    assert result["errors"] == []
    assert commands == [[commands[0][0], "-m", "halpha", "run", "--config", str(config_path.resolve()), "--no-codex"]]


def test_dashboard_daily_report_dispatcher_creates_due_no_codex_job(
    tmp_path: Path,
    monkeypatch,
) -> None:
    current = {"value": datetime(2026, 6, 20, 0, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr("halpha.dashboard.schedule._utc_now_datetime", lambda: current["value"])
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    commands: list[list[str]] = []

    def fake_popen(command, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        commands.append(command)
        return _FakeProcess(stdout="Halpha run succeeded.\nrun_id: run-auto", stderr="", returncode=0)

    monkeypatch.setattr("halpha.dashboard.jobs.subprocess.Popen", fake_popen)
    job_manager = DashboardJobManager(config, config_path=config_path)
    schedule_manager = DashboardScheduleManager(config, config_path=config_path, job_manager=job_manager)
    schedule_manager.enable_daily_report_schedule(
        {"time_of_day": "00:01", "timezone": "UTC", "job_intent": "run_no_codex"}
    )
    current["value"] = datetime(2026, 6, 20, 0, 2, tzinfo=timezone.utc)

    try:
        schedule_manager.start_daily_report_dispatcher(interval_seconds=0.01)
        schedule = _wait_for_dispatched_schedule(schedule_manager)
    finally:
        schedule_manager.stop_daily_report_dispatcher()

    job_id = schedule["last_job_id"]
    completed = _wait_for_manager_terminal(job_manager, job_id)
    assert completed["status"] == "succeeded"
    assert completed["intent"] == "run_no_codex"
    assert schedule["last_run_at"] == "2026-06-20T00:02:00Z"
    assert schedule["linked_job_ids"] == [job_id]
    assert schedule["next_run_at"] == "2026-06-21T00:01:00Z"
    assert commands == [[commands[0][0], "-m", "halpha", "run", "--config", str(config_path.resolve()), "--no-codex"]]


def test_dashboard_daily_report_dispatch_skips_disabled_and_not_due(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    job_manager = DashboardJobManager(config, config_path=config_path)
    schedule_manager = DashboardScheduleManager(config, config_path=config_path, job_manager=job_manager)

    disabled = schedule_manager.dispatch_due_daily_report()
    schedule_manager.enable_daily_report_schedule(
        {"time_of_day": "23:59", "timezone": "UTC", "job_intent": "run_no_codex"}
    )
    not_due = schedule_manager.dispatch_due_daily_report()

    assert disabled["status"] == "skipped"
    assert disabled["job"] is None
    assert disabled["warnings"] == ["daily report schedule is disabled."]
    assert not_due["status"] == "skipped"
    assert not_due["job"] is None
    assert not_due["warnings"] == ["daily report schedule is not due."]


def test_dashboard_daily_report_dispatch_blocks_codex_capable_automatic_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    current = {"value": datetime(2026, 6, 20, 0, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr("halpha.dashboard.schedule._utc_now_datetime", lambda: current["value"])
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("automatic dispatch must not start Codex-capable run jobs")

    monkeypatch.setattr("halpha.dashboard.jobs.subprocess.Popen", fail_popen)
    job_manager = DashboardJobManager(config, config_path=config_path)
    schedule_manager = DashboardScheduleManager(config, config_path=config_path, job_manager=job_manager)
    schedule_manager.enable_daily_report_schedule({"time_of_day": "00:01", "timezone": "UTC", "job_intent": "run"})
    current["value"] = datetime(2026, 6, 20, 0, 2, tzinfo=timezone.utc)

    result = schedule_manager.dispatch_due_daily_report()
    persisted = schedule_manager.read_daily_report_schedule()

    assert result["status"] == "blocked"
    assert result["job"] is None
    assert result["errors"] == ["automatic Codex-capable daily report dispatch requires manual confirmation."]
    assert persisted["status"] == "blocked"
    assert persisted["errors"] == result["errors"]
    assert persisted["next_run_at"] == "2026-06-21T00:01:00Z"


class _FakeProcess:
    def __init__(self, *, stdout: str, stderr: str, returncode: int) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.pid = 4242

    def communicate(self) -> tuple[str, str]:
        return self.stdout, self.stderr

    def terminate(self) -> None:
        self.returncode = -15


def _wait_for_api_terminal(client: TestClient, job_id: str) -> dict:
    for _ in range(50):
        response = client.get(f"/api/jobs/{job_id}")
        payload = response.json()
        if payload["status"] in {"succeeded", "failed", "cancelled", "unsupported", "blocked"}:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"job did not finish: {job_id}")


def _wait_for_manager_terminal(manager: DashboardJobManager, job_id: str) -> dict:
    for _ in range(50):
        payload = manager.get_job(job_id)
        if payload and payload["status"] in {"succeeded", "failed", "cancelled", "unsupported", "blocked"}:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"job did not finish: {job_id}")


def _wait_for_dispatched_schedule(manager: DashboardScheduleManager) -> dict:
    for _ in range(100):
        schedule = manager.read_daily_report_schedule()
        if schedule.get("last_job_id"):
            return schedule
        time.sleep(0.02)
    raise AssertionError("daily report dispatcher did not create a job")


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


def _write_config_without_run_timezone(tmp_path: Path) -> Path:
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
