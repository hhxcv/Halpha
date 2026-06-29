from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import threading
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from halpha.config import load_config
from halpha.dashboard import create_dashboard_app
from halpha.runtime.command_job_execution import CommandJobExecutionResult
from halpha.runtime.command_jobs import CommandJobManager
from halpha.runtime.command_job_store import CommandJobRepository
from halpha.dashboard.schedule import DashboardScheduleManager
from halpha.runtime.state_store import runtime_state_path


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
    assert payload["source_artifacts"] == [".halpha/state.sqlite"]
    assert payload["codex_authorization"]["valid"] is False
    assert payload["runtime_boundary"]["runs_only_while_dashboard_active"] is False
    assert payload["runtime_boundary"]["automatic_dispatch"] == "monitor_service"
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
    assert runtime_state_path(config_path=config_path).is_file()
    assert not (tmp_path / ".halpha" / "dashboard" / "schedules" / "daily_report_schedule.json").exists()
    assert not (tmp_path / "runs" / "dashboard").exists()

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

    assert not (tmp_path / ".halpha" / "dashboard" / "schedules" / "daily_report_schedule.json").exists()
    assert not (tmp_path / "runs" / "dashboard").exists()


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
    assert not (tmp_path / ".halpha" / "dashboard" / "schedules" / "daily_report_schedule.json").exists()
    assert not (tmp_path / "runs" / "dashboard").exists()


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
    captured_calls: list[dict[str, Any]] = []
    stdout = "\n".join(
        [
            "Halpha run succeeded.",
            "run_id: run-1",
            "report: runs/run-1/report/report.md",
            "manifest: runs/run-1/run_manifest.json",
        ]
    )

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("dashboard schedule jobs must use internal execution")

    def fake_execute_command_job(*args, **kwargs):  # noqa: ANN002, ANN003
        captured_calls.append(kwargs)
        return CommandJobExecutionResult(exit_code=0, stdout=stdout)

    monkeypatch.setattr("halpha.runtime.command_jobs.subprocess.Popen", fail_popen)
    monkeypatch.setattr("halpha.runtime.command_jobs.execute_command_job", fake_execute_command_job)
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
    assert completed["requested_by"] == "Core"
    assert completed["requester"] == {
        "dispatch_kind": "manual",
        "schedule_id": "daily_report",
        "source": "daily_report_schedule",
    }
    assert completed["command"] == ["internal", "run_no_codex"]
    assert captured_calls
    assert captured_calls[0]["run_trigger"]["source"] == "Core"
    assert captured_calls[0]["run_trigger"]["intent"] == "run_no_codex"
    assert captured_calls[0]["run_trigger"]["job_id"] == job_id
    assert captured_calls[0]["run_trigger"]["schedule_id"] == "daily_report"
    assert captured_calls[0]["run_trigger"]["dispatch_kind"] == "manual"
    assert schedule_response.json()["last_job_id"] == job_id
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

    monkeypatch.setattr("halpha.runtime.command_jobs.subprocess.Popen", fail_popen)
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
    captured_calls: list[dict[str, Any]] = []
    stdout = "\n".join(
        [
            "Halpha run succeeded.",
            "run_id: run-1",
            "report: runs/run-1/report/report.md",
            "manifest: runs/run-1/run_manifest.json",
        ]
    )

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("dashboard schedule jobs must use internal execution")

    def fake_execute_command_job(*args, **kwargs):  # noqa: ANN002, ANN003
        captured_calls.append(kwargs)
        return CommandJobExecutionResult(exit_code=0, stdout=stdout)

    monkeypatch.setattr("halpha.runtime.command_jobs.subprocess.Popen", fail_popen)
    monkeypatch.setattr("halpha.runtime.command_jobs.execute_command_job", fake_execute_command_job)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    client.post(
        "/api/schedule/daily-report/enable",
        json={"time_of_day": "08:30", "timezone": "UTC", "job_intent": "run", "confirm_codex": True},
    )
    trigger_response = client.post("/api/schedule/daily-report/trigger", json={"confirm_codex": True})
    trigger_payload = trigger_response.json()
    job_id = trigger_payload["job"]["job_id"]
    completed = _wait_for_api_terminal(client, job_id)

    assert trigger_response.status_code == 200
    assert trigger_payload["status"] == "available"
    assert trigger_payload["schedule"]["settings"]["job_intent"] == "run"
    assert trigger_payload["schedule"]["codex_authorization"]["valid"] is True
    assert trigger_payload["schedule"]["report_generation"]["generates_report"] is True
    assert completed["status"] == "succeeded"
    assert completed["intent"] == "run"
    assert completed["requested_by"] == "Core"
    assert completed["requester"] == {
        "dispatch_kind": "manual",
        "schedule_id": "daily_report",
        "source": "daily_report_schedule",
    }
    assert completed["command"] == ["internal", "run"]
    assert captured_calls[0]["run_trigger"]["source"] == "Core"
    assert captured_calls[0]["run_trigger"]["intent"] == "run"
    assert captured_calls[0]["run_trigger"]["job_id"] == job_id


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

    monkeypatch.setattr("halpha.runtime.command_jobs.subprocess.Popen", fake_popen)
    job_manager = CommandJobManager(config, config_path=config_path)
    schedule_manager = DashboardScheduleManager(config, config_path=config_path, job_manager=job_manager)
    enabled = schedule_manager.enable_daily_report_schedule(
        {"time_of_day": "00:01", "timezone": "UTC", "job_intent": "run_no_codex"}
    )
    current["value"] = datetime(2026, 6, 20, 0, 2, tzinfo=timezone.utc)

    result = schedule_manager.dispatch_due_daily_report()
    completed = _wait_for_manager_terminal(job_manager, str(result["job"]["job_id"]))

    assert enabled["settings"]["job_intent"] == "run_no_codex"
    assert enabled["report_generation"]["generates_report"] is False
    assert result["status"] == "available"
    assert result["job"]["intent"] == "run_no_codex"
    assert completed["requested_by"] == "Monitor"
    assert completed["requester"] == {
        "dispatch_kind": "automatic",
        "schedule_id": "daily_report",
        "source": "daily_report_schedule",
    }
    assert completed["status"] == "succeeded"
    assert result["errors"] == []
    assert commands == [[commands[0][0], "-m", "halpha", "run", "--config", str(config_path.resolve()), "--no-codex"]]


def test_dashboard_daily_report_authorized_codex_dispatch_creates_report_job(
    tmp_path: Path,
    monkeypatch,
) -> None:
    current = {"value": datetime(2026, 6, 20, 0, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr("halpha.dashboard.schedule._utc_now_datetime", lambda: current["value"])
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    job_manager = _RecordingJobManager()
    schedule_manager = DashboardScheduleManager(config, config_path=config_path, job_manager=job_manager)  # type: ignore[arg-type]
    enabled = schedule_manager.enable_daily_report_schedule(
        {"time_of_day": "00:01", "timezone": "UTC", "job_intent": "run", "confirm_codex": True}
    )
    current["value"] = datetime(2026, 6, 20, 0, 2, tzinfo=timezone.utc)

    result = schedule_manager.dispatch_due_daily_report()
    schedule = schedule_manager.read_daily_report_schedule()

    assert enabled["codex_authorization"]["valid"] is True
    assert result["status"] == "available"
    assert result["job"]["intent"] == "run"
    assert job_manager.created_intents == ["run"]
    assert job_manager.created_requests[0]["params"] == {"confirm_codex": True}
    assert schedule["dispatches"][0]["status"] == "job_succeeded"
    assert schedule["dispatches"][0]["report_ref"] is None


def test_dashboard_daily_report_repeated_due_dispatch_claims_once(
    tmp_path: Path,
    monkeypatch,
) -> None:
    current = {"value": datetime(2026, 6, 20, 0, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr("halpha.dashboard.schedule._utc_now_datetime", lambda: current["value"])
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    job_manager = _RecordingJobManager()
    schedule_manager = DashboardScheduleManager(config, config_path=config_path, job_manager=job_manager)  # type: ignore[arg-type]
    schedule_manager.enable_daily_report_schedule(
        {"time_of_day": "00:01", "timezone": "UTC", "job_intent": "run_no_codex"}
    )
    current["value"] = datetime(2026, 6, 20, 0, 2, tzinfo=timezone.utc)

    first = schedule_manager.dispatch_due_daily_report()
    second = schedule_manager.dispatch_due_daily_report()
    schedule = schedule_manager.read_daily_report_schedule()

    assert first["status"] == "available"
    assert first["job"]["job_id"] == "job-1"
    assert second["status"] == "skipped"
    assert second["job"] is None
    assert job_manager.created_intents == ["run_no_codex"]
    assert [dispatch["scheduled_for"] for dispatch in schedule["dispatches"]] == ["2026-06-20T00:01:00Z"]
    assert not (tmp_path / ".halpha" / "dashboard" / "schedules" / "daily_report_schedule.json").exists()


def test_dashboard_daily_report_concurrent_due_dispatch_claims_one_job(
    tmp_path: Path,
    monkeypatch,
) -> None:
    current = {"value": datetime(2026, 6, 20, 0, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr("halpha.dashboard.schedule._utc_now_datetime", lambda: current["value"])
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    job_manager = _RecordingJobManager()
    first_manager = DashboardScheduleManager(config, config_path=config_path, job_manager=job_manager)  # type: ignore[arg-type]
    second_manager = DashboardScheduleManager(config, config_path=config_path, job_manager=job_manager)  # type: ignore[arg-type]
    first_manager.enable_daily_report_schedule(
        {"time_of_day": "00:01", "timezone": "UTC", "job_intent": "run_no_codex"}
    )
    current["value"] = datetime(2026, 6, 20, 0, 2, tzinfo=timezone.utc)
    barrier = threading.Barrier(2)
    results: list[dict] = []
    errors: list[BaseException] = []

    def dispatch(manager: DashboardScheduleManager) -> None:
        try:
            barrier.wait(timeout=2)
            results.append(manager.dispatch_due_daily_report())
        except BaseException as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=dispatch, args=(manager,)) for manager in (first_manager, second_manager)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    schedule = first_manager.read_daily_report_schedule()
    assert errors == []
    assert len(results) == 2
    assert sum(1 for result in results if result["job"] is not None) == 1
    assert job_manager.created_intents == ["run_no_codex"]
    assert [dispatch["scheduled_for"] for dispatch in schedule["dispatches"]] == ["2026-06-20T00:01:00Z"]


def test_dashboard_daily_report_catch_up_marks_older_due_occurrences_missed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    current = {"value": datetime(2026, 6, 20, 0, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr("halpha.dashboard.schedule._utc_now_datetime", lambda: current["value"])
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    job_manager = _RecordingJobManager()
    schedule_manager = DashboardScheduleManager(config, config_path=config_path, job_manager=job_manager)  # type: ignore[arg-type]
    schedule_manager.enable_daily_report_schedule(
        {"time_of_day": "00:01", "timezone": "UTC", "job_intent": "run_no_codex"}
    )
    current["value"] = datetime(2026, 6, 23, 0, 2, tzinfo=timezone.utc)

    result = schedule_manager.dispatch_due_daily_report()
    schedule = schedule_manager.read_daily_report_schedule()

    assert result["status"] == "available"
    assert job_manager.created_intents == ["run_no_codex"]
    assert [dispatch["scheduled_for"] for dispatch in schedule["dispatches"]] == [
        "2026-06-23T00:01:00Z",
        "2026-06-22T00:01:00Z",
        "2026-06-21T00:01:00Z",
        "2026-06-20T00:01:00Z",
    ]
    assert [dispatch["status"] for dispatch in schedule["dispatches"]] == [
        "job_succeeded",
        "missed",
        "missed",
        "missed",
    ]


def test_dashboard_daily_report_dispatch_records_job_creation_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    current = {"value": datetime(2026, 6, 20, 0, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr("halpha.dashboard.schedule._utc_now_datetime", lambda: current["value"])
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    job_manager = _FailingJobManager()
    schedule_manager = DashboardScheduleManager(config, config_path=config_path, job_manager=job_manager)  # type: ignore[arg-type]
    schedule_manager.enable_daily_report_schedule(
        {"time_of_day": "00:01", "timezone": "UTC", "job_intent": "run_no_codex"}
    )
    current["value"] = datetime(2026, 6, 20, 0, 2, tzinfo=timezone.utc)

    result = schedule_manager.dispatch_due_daily_report()
    schedule = schedule_manager.read_daily_report_schedule()

    assert result["status"] == "failed"
    assert result["job"] is None
    assert result["errors"] == ["daily report job could not be created."]
    assert schedule["dispatches"][0]["status"] == "job_failed"
    assert schedule["dispatches"][0]["errors"] == ["daily report job could not be created."]


def test_dashboard_daily_report_read_reconciles_completed_report_link(
    tmp_path: Path,
    monkeypatch,
) -> None:
    current = {"value": datetime(2026, 6, 20, 0, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr("halpha.dashboard.schedule._utc_now_datetime", lambda: current["value"])
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    job_manager = _RecordingJobManager(initial_status="running")
    schedule_manager = DashboardScheduleManager(config, config_path=config_path, job_manager=job_manager)  # type: ignore[arg-type]
    schedule_manager.enable_daily_report_schedule(
        {"time_of_day": "00:01", "timezone": "UTC", "job_intent": "run_no_codex"}
    )
    current["value"] = datetime(2026, 6, 20, 0, 2, tzinfo=timezone.utc)
    result = schedule_manager.dispatch_due_daily_report()
    job_manager.complete_job(str(result["job"]["job_id"]), report_ref="runs/run-1/report/report.md")

    schedule = schedule_manager.read_daily_report_schedule()

    assert schedule["linked_job_ids"] == ["job-1"]
    assert schedule["linked_report_refs"] == ["runs/run-1/report/report.md"]
    assert schedule["dispatches"][0]["terminal_status"] == "succeeded"
    assert schedule["dispatches"][0]["report_ref"] == "runs/run-1/report/report.md"


def test_core_schedule_dispatch_due_endpoint_creates_due_no_codex_job(
    tmp_path: Path,
    monkeypatch,
) -> None:
    current = {"value": datetime(2026, 6, 20, 0, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr("halpha.dashboard.schedule._utc_now_datetime", lambda: current["value"])
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    stdout = "Halpha run succeeded.\nrun_id: run-auto\nmanifest: runs/run-auto/run_manifest.json\n"

    def fake_execute_command_job(*args, **kwargs):  # noqa: ANN002, ANN003
        return CommandJobExecutionResult(exit_code=0, stdout=stdout)

    monkeypatch.setattr("halpha.runtime.command_jobs.execute_command_job", fake_execute_command_job)
    client = TestClient(create_dashboard_app(config, config_path=config_path))
    client.post(
        "/api/schedule/daily-report/enable",
        json={"time_of_day": "00:01", "timezone": "UTC", "job_intent": "run_no_codex"},
    )
    current["value"] = datetime(2026, 6, 20, 0, 2, tzinfo=timezone.utc)

    dispatch_response = client.post("/api/schedule/daily-report/dispatch-due")

    assert dispatch_response.status_code == 200
    assert dispatch_response.json()["status"] == "available"
    job_id = dispatch_response.json()["job"]["job_id"]
    completed = _wait_for_api_terminal(client, job_id)
    schedule = client.get("/api/schedule/daily-report").json()
    assert completed["status"] == "succeeded"
    assert completed["intent"] == "run_no_codex"
    assert completed["requested_by"] == "Monitor"
    assert schedule["last_run_at"] == "2026-06-20T00:02:00Z"
    assert schedule["linked_job_ids"] == [job_id]
    assert schedule["next_run_at"] == "2026-06-21T00:01:00Z"


def test_dashboard_daily_report_dispatch_skips_disabled_and_not_due(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    job_manager = CommandJobManager(config, config_path=config_path)
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


def test_dashboard_daily_report_dispatch_blocks_codex_when_authorization_is_invalidated(
    tmp_path: Path,
    monkeypatch,
) -> None:
    current = {"value": datetime(2026, 6, 20, 0, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr("halpha.dashboard.schedule._utc_now_datetime", lambda: current["value"])
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("automatic dispatch must not start Codex-capable run jobs")

    monkeypatch.setattr("halpha.runtime.command_jobs.subprocess.Popen", fail_popen)
    job_manager = CommandJobManager(config, config_path=config_path)
    schedule_manager = DashboardScheduleManager(config, config_path=config_path, job_manager=job_manager)
    enabled = schedule_manager.enable_daily_report_schedule(
        {"time_of_day": "00:01", "timezone": "UTC", "job_intent": "run", "confirm_codex": True}
    )
    changed_config = {**config, "codex": {"enabled": True}}
    changed_manager = DashboardScheduleManager(changed_config, config_path=config_path, job_manager=job_manager)
    current["value"] = datetime(2026, 6, 20, 0, 2, tzinfo=timezone.utc)

    result = changed_manager.dispatch_due_daily_report()
    persisted = changed_manager.read_daily_report_schedule()

    assert enabled["codex_authorization"]["valid"] is True
    assert persisted["codex_authorization"]["valid"] is False
    assert result["status"] == "blocked"
    assert result["job"] is None
    assert result["errors"] == ["unattended Codex-capable daily report dispatch requires valid persisted authorization."]
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


class _RecordingJobManager:
    def __init__(self, *, initial_status: str = "succeeded") -> None:
        self.initial_status = initial_status
        self.created_intents: list[str] = []
        self.created_requests: list[dict] = []
        self.jobs: dict[str, dict] = {}

    def create_job(self, request: dict) -> dict:
        self.created_intents.append(str(request.get("intent") or ""))
        self.created_requests.append(request)
        job_id = f"job-{len(self.created_intents)}"
        job = {
            "schema_version": 1,
            "artifact_type": "command_job",
            "job_id": job_id,
            "intent": request.get("intent"),
            "requested_by": request.get("requested_by"),
            "requester": request.get("requester"),
            "status": self.initial_status,
            "result_refs": {},
            "warnings": [],
            "errors": [],
        }
        if self.initial_status == "succeeded":
            job["result_refs"] = {"run_id": "run-1"}
        self.jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> dict | None:
        return self.jobs.get(job_id)

    def complete_job(self, job_id: str, *, report_ref: str) -> None:
        job = self.jobs[job_id]
        job["status"] = "succeeded"
        job["result_refs"] = {"run_id": "run-1", "report": report_ref}


class _FailingJobManager:
    def create_job(self, request: dict) -> dict:
        raise RuntimeError("job creation failed")

    def get_job(self, job_id: str) -> dict | None:
        return None


class _RepositoryJobReader:
    def __init__(self, config_path: Path) -> None:
        self._repository = CommandJobRepository(config_path=config_path)

    def get_job(self, job_id: str) -> dict | None:
        return self._repository.get_job(job_id)


def _wait_for_api_terminal(client: TestClient, job_id: str) -> dict:
    for _ in range(50):
        response = client.get(f"/api/jobs/{job_id}")
        payload = response.json()
        if payload["status"] in {"succeeded", "failed", "cancelled", "unsupported", "blocked"}:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"job did not finish: {job_id}")


def _wait_for_repository_terminal(repository: CommandJobRepository, job_id: str) -> dict:
    for _ in range(50):
        payload = repository.get_job(job_id)
        if payload and payload["status"] in {"succeeded", "failed", "cancelled", "unsupported", "blocked"}:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"job did not finish: {job_id}")


def _wait_for_schedule_terminal_dispatch(manager: DashboardScheduleManager) -> dict:
    for _ in range(50):
        schedule = manager.read_daily_report_schedule()
        dispatches = schedule.get("dispatches") if isinstance(schedule.get("dispatches"), list) else []
        if dispatches and dispatches[0].get("terminal_status"):
            return schedule
        time.sleep(0.05)
    raise AssertionError("daily report schedule dispatch did not reach a terminal job state")


def _wait_for_manager_terminal(manager: CommandJobManager, job_id: str) -> dict:
    for _ in range(50):
        payload = manager.get_job(job_id)
        if payload and payload["status"] in {"succeeded", "failed", "cancelled", "unsupported", "blocked"}:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"job did not finish: {job_id}")


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
