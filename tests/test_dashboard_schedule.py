from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import time

from fastapi.testclient import TestClient

from halpha.config import load_config
from halpha.dashboard import create_dashboard_app


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
    assert payload["next_run_at"] is None
    assert payload["source_artifacts"] == ["runs/dashboard/schedules/daily_report_schedule.json"]
    assert payload["runtime_boundary"]["hidden_service"] is False
    assert payload["runtime_boundary"]["hosted_scheduler"] is False
    assert str(tmp_path) not in response.text


def test_dashboard_daily_report_schedule_enable_disable_and_persistence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "halpha.dashboard_schedule._utc_now_datetime",
        lambda: datetime(2026, 6, 20, 1, 0, tzinfo=timezone.utc),
    )
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    enable_response = client.post(
        "/api/schedule/daily-report/enable",
        json={"time_of_day": "08:30", "timezone": "UTC"},
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


def test_dashboard_daily_report_schedule_manual_trigger_creates_visible_job(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "halpha.dashboard_schedule._utc_now_datetime",
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

    monkeypatch.setattr("halpha.dashboard_jobs.subprocess.Popen", fake_popen)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    client.post("/api/schedule/daily-report/enable", json={"time_of_day": "08:30", "timezone": "UTC"})
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

    monkeypatch.setattr("halpha.dashboard_jobs.subprocess.Popen", fail_popen)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.post("/api/schedule/daily-report/trigger", json={"job_intent": "run"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked"
    assert payload["job"] is None
    assert payload["errors"] == ["confirm_codex must be true to trigger a Codex-capable daily report job."]


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
