from __future__ import annotations

from pathlib import Path
import threading
import time

from fastapi.testclient import TestClient

from halpha.config import load_config
from halpha.dashboard import create_dashboard_app
from halpha.dashboard_jobs import DashboardJobManager, MAX_JOB_LOG_CHARS


def test_dashboard_job_api_rejects_unsupported_intent_before_process(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("unsupported intent must not start a process")

    monkeypatch.setattr("halpha.dashboard_jobs.subprocess.Popen", fail_popen)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.post("/api/jobs", json={"intent": "shell", "params": {"command": "echo no"}})

    assert response.status_code == 200
    payload = response.json()
    assert payload["artifact_type"] == "dashboard_job"
    assert payload["status"] == "unsupported"
    assert payload["intent"] == "shell"
    assert payload["pid"] is None
    assert payload["exit_code"] is None
    assert "unsupported dashboard job intent" in payload["errors"][0]
    assert (tmp_path / "runs" / "dashboard" / "jobs" / payload["job_id"] / "job.json").is_file()
    assert str(tmp_path) not in response.text


def test_dashboard_job_manager_runs_allowlisted_job_with_bounded_redacted_logs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_private_config(tmp_path)
    config = load_config(config_path)
    secret = "http://private-proxy.example:7890"
    stdout = f"{secret}\n{config_path}\n" + ("x" * (MAX_JOB_LOG_CHARS + 12))
    fake_process = _FakeProcess(stdout=stdout, stderr=f"stderr {secret}", returncode=0)
    monkeypatch.setattr("halpha.dashboard_jobs.subprocess.Popen", lambda *args, **kwargs: fake_process)
    manager = DashboardJobManager(config, config_path=config_path)

    job = manager.create_job({"intent": "validate", "params": {}})
    completed = _wait_for_terminal(manager, job["job_id"])

    assert completed["status"] == "succeeded"
    assert completed["exit_code"] == 0
    assert completed["pid"] == fake_process.pid
    assert completed["logs"]["stdout_truncated"] is True
    assert completed["logs"]["stderr_truncated"] is False
    assert completed["command"] == ["python", "-m", "halpha", "validate", "--config", "<external-config>"]
    stdout_log = (tmp_path / completed["logs"]["stdout_ref"]).read_text(encoding="utf-8")
    stderr_log = (tmp_path / completed["logs"]["stderr_ref"]).read_text(encoding="utf-8")
    job_json = (tmp_path / "runs" / "dashboard" / "jobs" / completed["job_id"] / "job.json").read_text(
        encoding="utf-8"
    )
    assert len(stdout_log) == MAX_JOB_LOG_CHARS
    assert secret not in stdout_log
    assert str(config_path) not in stdout_log
    assert secret not in stderr_log
    assert str(config_path) not in job_json


def test_dashboard_job_manager_cancels_running_job(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    fake_process = _BlockingProcess()
    monkeypatch.setattr("halpha.dashboard_jobs.subprocess.Popen", lambda *args, **kwargs: fake_process)
    manager = DashboardJobManager(config, config_path=config_path)

    job = manager.create_job({"intent": "validate", "params": {}})
    _wait_for_status(manager, job["job_id"], "running")
    cancel_payload = manager.cancel_job(job["job_id"])
    completed = _wait_for_terminal(manager, job["job_id"])

    assert cancel_payload["status"] == "cancel_requested"
    assert fake_process.terminated is True
    assert completed["status"] == "cancelled"
    assert completed["exit_code"] == -15
    assert "cancelled" in completed["warnings"][0]


def test_dashboard_job_api_lists_and_reads_jobs(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    monkeypatch.setattr(
        "halpha.dashboard_jobs.subprocess.Popen",
        lambda *args, **kwargs: _FakeProcess(stdout="ok", stderr="", returncode=0),
    )
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    create_response = client.post("/api/jobs", json={"intent": "validate", "params": {}})
    job_id = create_response.json()["job_id"]
    _wait_for_api_terminal(client, job_id)
    list_response = client.get("/api/jobs")
    detail_response = client.get(f"/api/jobs/{job_id}")

    assert list_response.status_code == 200
    assert detail_response.status_code == 200
    assert list_response.json()["artifact_type"] == "dashboard_job_list"
    assert list_response.json()["jobs"][0]["job_id"] == job_id
    assert detail_response.json()["status"] == "succeeded"
    assert str(tmp_path) not in list_response.text
    assert str(tmp_path) not in detail_response.text


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


class _BlockingProcess:
    def __init__(self) -> None:
        self.pid = 4343
        self.returncode = None
        self.terminated = False
        self._done = threading.Event()

    def communicate(self) -> tuple[str, str]:
        self._done.wait(timeout=5)
        return "cancelled stdout", "cancelled stderr"

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15
        self._done.set()


def _wait_for_terminal(manager: DashboardJobManager, job_id: str) -> dict:
    for _ in range(50):
        job = manager.get_job(job_id)
        if job and job["status"] in {"succeeded", "failed", "cancelled", "unsupported", "blocked"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"job did not finish: {job_id}")


def _wait_for_status(manager: DashboardJobManager, job_id: str, status: str) -> dict:
    for _ in range(50):
        job = manager.get_job(job_id)
        if job and job["status"] == status:
            return job
        time.sleep(0.05)
    raise AssertionError(f"job did not reach {status}: {job_id}")


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


def _write_private_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
run:
  output_dir: runs
market:
  enabled: false
  proxy:
    enabled: true
    url: http://private-proxy.example:7890
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
