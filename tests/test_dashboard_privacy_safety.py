from __future__ import annotations

from pathlib import Path
import time

import pytest
from fastapi.testclient import TestClient

from halpha.config import load_config
from halpha.dashboard import create_dashboard_app
from halpha.runtime.command_job_execution import CommandJobExecutionResult
from halpha.runtime.command_jobs import MAX_JOB_LOG_CHARS
from halpha.runtime.state_store import runtime_state_path
from halpha.storage import write_json


PRIVATE_PROXY = "http://private-proxy.example:7890"
PRIVATE_USER_STATE = "user_state.local.yaml"
PRIVATE_NOTE = "do not expose this private note"
PRIVATE_TOKEN = "secret-token-123"


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_dashboard_artifact_preview_redacts_private_json_and_text_values(tmp_path: Path) -> None:
    config_path = _write_private_config(tmp_path)
    config = load_config(config_path)
    machine_path = str(tmp_path / "private" / "notes.txt")
    json_artifact = tmp_path / "runs" / "run-1" / "analysis" / "private_preview.json"
    yaml_artifact = tmp_path / "runs" / "run-1" / "raw" / "private_preview.yaml"
    write_json(
        json_artifact,
        {
            "public": "visible",
            "proxy_url": PRIVATE_PROXY,
            "token": PRIVATE_TOKEN,
            "nested": {
                "private_note": PRIVATE_NOTE,
                "machine_path": machine_path,
                "report": "runs/run-1/report/report.md",
            },
        },
    )
    yaml_artifact.parent.mkdir(parents=True, exist_ok=True)
    yaml_artifact.write_text(
        "\n".join(
            [
                "public: visible",
                f"proxy_url: {PRIVATE_PROXY}",
                f"private_note: {PRIVATE_NOTE}",
                f"token: {PRIVATE_TOKEN}",
                f"machine_path: {machine_path}",
            ]
        ),
        encoding="utf-8",
    )
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    json_response = client.get("/api/artifacts/preview", params={"path": "runs/run-1/analysis/private_preview.json"})
    yaml_response = client.get("/api/artifacts/preview", params={"path": "runs/run-1/raw/private_preview.yaml"})

    assert json_response.status_code == 200
    json_payload = json_response.json()
    assert json_payload["status"] == "available"
    assert json_payload["preview"]["public"] == "visible"
    assert json_payload["preview"]["proxy_url"] == "<redacted>"
    assert json_payload["preview"]["token"] == "<redacted>"
    assert json_payload["preview"]["nested"]["private_note"] == "<redacted>"
    assert json_payload["preview"]["nested"]["machine_path"] == "<redacted>"
    assert json_payload["preview"]["nested"]["report"] == "runs/run-1/report/report.md"

    assert yaml_response.status_code == 200
    assert "public: visible" in yaml_response.text
    for private_value in [PRIVATE_PROXY, PRIVATE_USER_STATE, PRIVATE_NOTE, PRIVATE_TOKEN, machine_path, str(tmp_path)]:
        assert private_value not in json_response.text
        assert private_value not in yaml_response.text


def test_dashboard_artifact_preview_rejects_user_state_and_traversal_paths(tmp_path: Path) -> None:
    config_path = _write_private_config(tmp_path)
    (tmp_path / PRIVATE_USER_STATE).write_text(f"private_note: {PRIVATE_NOTE}", encoding="utf-8")
    config = load_config(config_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))
    cases = ["user_state.local.yaml", "runs/../user_state.local.yaml", "../user_state.local.yaml"]

    for path in cases:
        response = client.get("/api/artifacts/preview", params={"path": path})
        payload = response.json()
        assert response.status_code == 200
        assert payload["status"] == "rejected"
        assert PRIVATE_NOTE not in response.text
        assert str(tmp_path) not in response.text


def test_command_job_api_redacts_private_values_from_response_and_logs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_private_config(tmp_path)
    config = load_config(config_path)
    machine_path = str(tmp_path / "private" / "job.txt")
    stdout = "\n".join([PRIVATE_PROXY, PRIVATE_USER_STATE, machine_path, f"manifest: {PRIVATE_USER_STATE}", "ok"])
    stdout += "x" * (MAX_JOB_LOG_CHARS + 1)
    stderr = f"{PRIVATE_PROXY}\n{PRIVATE_USER_STATE}\n{machine_path}"

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("dashboard command jobs must use internal execution")

    def fake_execute_command_job(*args, **kwargs):  # noqa: ANN002, ANN003
        return CommandJobExecutionResult(exit_code=0, stdout=stdout, stderr=stderr)

    monkeypatch.setattr("halpha.runtime.command_jobs.subprocess.Popen", fail_popen)
    monkeypatch.setattr("halpha.runtime.command_jobs.execute_command_job", fake_execute_command_job)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    create_response = client.post("/api/jobs", json={"intent": "validate", "params": {}})
    job_id = create_response.json()["job_id"]
    completed = _wait_for_api_terminal(client, job_id)
    detail_response = client.get(f"/api/jobs/{job_id}")
    stdout_log = (tmp_path / completed["logs"]["stdout_ref"]).read_text(encoding="utf-8")
    stderr_log = (tmp_path / completed["logs"]["stderr_ref"]).read_text(encoding="utf-8")
    state_bytes = runtime_state_path(config_path=config_path).read_bytes()
    assert not (tmp_path / "runs" / "dashboard").exists()
    assert not (tmp_path / ".halpha" / "dashboard" / "jobs" / job_id / "job.json").exists()

    assert completed["status"] == "succeeded"
    assert completed["logs"]["stdout_truncated"] is True
    assert completed["result_refs"]["manifest"] == "<redacted-artifact>"
    assert "<redacted-artifact>" not in completed["source_artifacts"]
    for private_value in [PRIVATE_PROXY, PRIVATE_USER_STATE, machine_path, str(config_path), str(tmp_path)]:
        assert private_value not in create_response.text
        assert private_value not in detail_response.text
        assert private_value not in stdout_log
        assert private_value not in stderr_log
        assert private_value.encode() not in state_bytes


def test_dashboard_command_safety_rejects_unsupported_args_and_codex_without_confirmation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_private_config(tmp_path)
    config = load_config(config_path)

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("blocked command job must not start a process")

    monkeypatch.setattr("halpha.runtime.command_jobs.subprocess.Popen", fail_popen)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    unsupported = client.post("/api/jobs", json={"intent": "shell", "params": {"command": "echo no"}}).json()
    unsupported_arg = client.post("/api/jobs", json={"intent": "validate", "params": {"command": "echo no"}}).json()
    codex_without_confirmation = client.post("/api/jobs", json={"intent": "run", "params": {}}).json()
    schedule_codex_without_confirmation = client.post(
        "/api/schedule/daily-report/trigger",
        json={"job_intent": "run"},
    ).json()

    assert unsupported["status"] == "unsupported"
    assert unsupported["pid"] is None
    assert unsupported_arg["status"] == "blocked"
    assert "unsupported validate job parameter(s): command" in unsupported_arg["errors"][0]
    assert codex_without_confirmation["status"] == "blocked"
    assert "confirm_codex must be true" in codex_without_confirmation["errors"][0]
    assert schedule_codex_without_confirmation["status"] == "blocked"
    assert schedule_codex_without_confirmation["job"] is None
    assert "confirm_codex must be true" in schedule_codex_without_confirmation["errors"][0]


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


def _write_private_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        f"""
run:
  output_dir: runs
market:
  enabled: false
  proxy:
    enabled: true
    url: {PRIVATE_PROXY}
text:
  enabled: false
  sources: []
user_state:
  enabled: false
  path: {PRIVATE_USER_STATE}
report:
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return path
