from __future__ import annotations

import json
import os
from pathlib import Path
import threading
import time

import pytest
from fastapi.testclient import TestClient

from halpha.config import load_config
from halpha.dashboard import create_dashboard_app
from halpha.dashboard.job_commands import DashboardJobCommandBuilder, DashboardJobError
from halpha.dashboard.job_store import DashboardJobRepository, DashboardJobStoreError
from halpha.dashboard.jobs import DashboardJobManager, MAX_JOB_LOG_CHARS
from halpha.runtime.state_store import runtime_state_path


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_dashboard_job_command_builder_builds_command_preview(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    builder = DashboardJobCommandBuilder(config, config_path=config_path, base=tmp_path)

    command = builder.build("validate", {})

    assert command.spec.intent == "validate"
    assert command.preview == ["python", "-m", "halpha", "validate", "--config", "<external-config>"]
    assert command.command[1:] == ["-m", "halpha", "validate", "--config", str(config_path.resolve())]


def test_dashboard_job_command_builder_rejects_unsupported_intent(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    builder = DashboardJobCommandBuilder(config, config_path=config_path, base=tmp_path)

    try:
        builder.build("shell", {"command": "echo no"})
    except DashboardJobError as exc:
        assert exc.status == "unsupported"
        assert str(exc) == "unsupported dashboard job intent: shell"
    else:
        raise AssertionError("unsupported intent must be rejected by command builder")


def test_dashboard_job_api_rejects_unsupported_intent_before_process(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("unsupported intent must not start a process")

    monkeypatch.setattr("halpha.dashboard.jobs.subprocess.Popen", fail_popen)
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
    assert runtime_state_path(config_path=config_path).is_file()
    assert not (tmp_path / ".halpha" / "dashboard" / "jobs" / payload["job_id"] / "job.json").exists()
    assert not (tmp_path / "runs" / "dashboard").exists()
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
    monkeypatch.setattr("halpha.dashboard.jobs.subprocess.Popen", lambda *args, **kwargs: fake_process)
    manager = DashboardJobManager(config, config_path=config_path)

    job = manager.create_job({"intent": "validate", "params": {}})
    completed = _wait_for_terminal(manager, job["job_id"])

    assert completed["status"] == "succeeded"
    assert completed["exit_code"] == 0
    assert completed["pid"] == fake_process.pid
    assert completed["logs"]["stdout_truncated"] is True
    assert completed["logs"]["stderr_truncated"] is False
    assert completed["command"] == ["python", "-m", "halpha", "validate", "--config", "<external-config>"]
    assert completed["job_dir"].startswith(".halpha/dashboard/job_logs/")
    stdout_log = (tmp_path / completed["logs"]["stdout_ref"]).read_text(encoding="utf-8")
    stderr_log = (tmp_path / completed["logs"]["stderr_ref"]).read_text(encoding="utf-8")
    state_bytes = runtime_state_path(config_path=config_path).read_bytes()
    assert len(stdout_log) == MAX_JOB_LOG_CHARS
    assert secret not in stdout_log
    assert str(config_path) not in stdout_log
    assert secret not in stderr_log
    assert secret.encode() not in state_bytes
    assert str(config_path).encode() not in state_bytes
    assert not (tmp_path / ".halpha" / "dashboard" / "jobs" / completed["job_id"] / "job.json").exists()


def test_dashboard_job_logging_includes_context_without_private_values(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_private_config(tmp_path)
    config = load_config(config_path)
    secret = "http://private-proxy.example:7890"
    fake_process = _FakeProcess(stdout=f"stdout {secret}", stderr="", returncode=0)
    monkeypatch.setattr("halpha.dashboard.jobs.subprocess.Popen", lambda *args, **kwargs: fake_process)
    manager = DashboardJobManager(config, config_path=config_path)

    job = manager.create_job({"intent": "validate", "params": {}})
    completed = _wait_for_terminal(manager, job["job_id"])

    log_text = _wait_for_log_event(tmp_path / "logs" / "halpha.log", completed["job_id"], "dashboard.job.finished")
    events = [json.loads(line) for line in log_text.splitlines() if line.strip()]
    assert completed["job_id"] in log_text
    assert "dashboard.job.start" in {event.get("event") for event in events}
    assert "dashboard.job.finished" in {event.get("event") for event in events}
    assert secret not in log_text
    assert str(config_path) not in log_text
    assert str(tmp_path) not in log_text


def test_dashboard_job_start_failure_records_bounded_diagnostic(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_private_config(tmp_path)
    config = load_config(config_path)
    secret = "http://private-proxy.example:7890"

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise OSError(f"cannot start with {secret} at {config_path}")

    monkeypatch.setattr("halpha.dashboard.jobs.subprocess.Popen", fail_popen)
    manager = DashboardJobManager(config, config_path=config_path)

    job = manager.create_job({"intent": "validate", "params": {}})
    completed = _wait_for_terminal(manager, job["job_id"])
    state_bytes = runtime_state_path(config_path=config_path).read_bytes()

    assert completed["status"] == "failed"
    assert completed["diagnostic"] == {
        "exception_type": "OSError",
        "traceback_embedded": False,
        "context": {"phase": "process_start"},
    }
    assert "<redacted>" in completed["errors"][0]
    assert secret.encode() not in state_bytes
    assert str(config_path).encode() not in state_bytes
    assert str(tmp_path).encode() not in state_bytes


def test_dashboard_job_manager_preserves_relative_config_ref(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = Path("config.yaml")
    _write_config(tmp_path)
    config = load_config(config_path)
    monkeypatch.setattr(
        "halpha.dashboard.jobs.subprocess.Popen",
        lambda *args, **kwargs: _FakeProcess(stdout="config.yaml", stderr="", returncode=0),
    )
    manager = DashboardJobManager(config, config_path=config_path)

    job = manager.create_job({"intent": "validate", "params": {}})
    completed = _wait_for_terminal(manager, job["job_id"])

    assert completed["command"] == ["python", "-m", "halpha", "validate", "--config", "config.yaml"]
    stdout_log = (tmp_path / completed["logs"]["stdout_ref"]).read_text(encoding="utf-8")
    assert "config.yaml" in stdout_log


def test_dashboard_job_manager_passes_valid_subdirectory_config_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    config_path = Path("configs/local.yaml")
    _write_config(config_dir, name="local.yaml")
    config = load_config(config_path)
    commands: list[list[str]] = []
    cwd_values: list[Path] = []

    def fake_popen(command, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        commands.append(command)
        cwd_values.append(Path(kwargs["cwd"]))
        return _FakeProcess(stdout=str((tmp_path / config_path).resolve()), stderr="", returncode=0)

    monkeypatch.setattr("halpha.dashboard.jobs.subprocess.Popen", fake_popen)
    manager = DashboardJobManager(config, config_path=config_path)

    job = manager.create_job({"intent": "validate", "params": {}})
    completed = _wait_for_terminal(manager, job["job_id"])

    assert completed["command"] == ["python", "-m", "halpha", "validate", "--config", "configs/local.yaml"]
    assert cwd_values == [tmp_path.resolve()]
    assert Path(commands[0][-1]).is_file()
    assert Path(commands[0][-1]).resolve() == (tmp_path / config_path).resolve()
    stdout_log = (tmp_path / completed["logs"]["stdout_ref"]).read_text(encoding="utf-8")
    assert str((tmp_path / config_path).resolve()) not in stdout_log
    assert completed["job_dir"].startswith(".halpha/dashboard/job_logs/")
    assert not (config_dir / "runs").exists()


def test_dashboard_job_manager_accepts_readonly_command_intents(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    (tmp_path / "runs" / "run-1").mkdir(parents=True)
    commands: list[list[str]] = []

    def fake_popen(command, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        commands.append(command)
        return _FakeProcess(stdout="ok", stderr="", returncode=0)

    monkeypatch.setattr("halpha.dashboard.jobs.subprocess.Popen", fake_popen)
    manager = DashboardJobManager(config, config_path=config_path)
    cases = [
        ("validate", {}, ["python", "-m", "halpha", "validate", "--config", "<external-config>"]),
        (
            "data_inspect",
            {"run_dir": "runs/run-1"},
            [
                "python",
                "-m",
                "halpha",
                "data",
                "inspect",
                "--config",
                "<external-config>",
                "--run-dir",
                "runs/run-1",
            ],
        ),
        (
            "outcomes_inspect",
            {"run_dir": "runs/run-1"},
            [
                "python",
                "-m",
                "halpha",
                "outcomes",
                "inspect",
                "--config",
                "<external-config>",
                "--run-dir",
                "runs/run-1",
            ],
        ),
        (
            "workbench_build",
            {"run_dir": "runs/run-1"},
            [
                "python",
                "-m",
                "halpha",
                "workbench",
                "build",
                "--config",
                "<external-config>",
                "--run-dir",
                "runs/run-1",
            ],
        ),
        (
            "workbench_inspect",
            {},
            ["python", "-m", "halpha", "workbench", "inspect", "--config", "<external-config>"],
        ),
        (
            "monitor_inspect",
            {},
            ["python", "-m", "halpha", "monitor", "inspect", "--config", "<external-config>"],
        ),
    ]

    for intent, params, preview in cases:
        job = manager.create_job({"intent": intent, "params": params})
        completed = _wait_for_terminal(manager, job["job_id"])
        assert completed["status"] == "succeeded"
        assert completed["intent"] == intent
        assert completed["command"] == preview

    assert len(commands) == len(cases)
    assert all(command[:3] == [commands[0][0], "-m", "halpha"] for command in commands)


def test_dashboard_job_manager_accepts_monitor_command_intents(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    commands: list[list[str]] = []
    outputs = [
        "Halpha monitor dry run succeeded.\ncycle_execution: not_run",
        "Halpha monitor cycle succeeded.\nmonitor_manifest: runs/monitor/cycles/cycle-1/monitor_cycle_manifest.json",
        "Halpha monitor loop succeeded.\nhealth_state: runs/monitor/monitor_health_state.json",
    ]

    def fake_popen(command, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        index = len(commands)
        commands.append(command)
        return _FakeProcess(stdout=outputs[index], stderr="", returncode=0)

    monkeypatch.setattr("halpha.dashboard.jobs.subprocess.Popen", fake_popen)
    manager = DashboardJobManager(config, config_path=config_path)
    cases = [
        (
            "monitor_dry_run",
            {},
            ["python", "-m", "halpha", "monitor", "run", "--config", "<external-config>", "--dry-run"],
            {},
        ),
        (
            "monitor_once",
            {},
            ["python", "-m", "halpha", "monitor", "run", "--config", "<external-config>", "--once"],
            {"monitor_manifest": "runs/monitor/cycles/cycle-1/monitor_cycle_manifest.json"},
        ),
        (
            "monitor_loop",
            {"max_cycles": 2, "interval_seconds": 1},
            [
                "python",
                "-m",
                "halpha",
                "monitor",
                "run",
                "--config",
                "<external-config>",
                "--max-cycles",
                "2",
                "--interval-seconds",
                "1",
            ],
            {"health_state": "runs/monitor/monitor_health_state.json"},
        ),
    ]

    for intent, params, preview, expected_refs in cases:
        job = manager.create_job({"intent": intent, "params": params})
        completed = _wait_for_terminal(manager, job["job_id"])
        assert completed["status"] == "succeeded"
        assert completed["intent"] == intent
        assert completed["command"] == preview
        for key, value in expected_refs.items():
            assert completed["result_refs"][key] == value
            assert value in completed["source_artifacts"]

    assert len(commands) == len(cases)
    assert all(command[:3] == [commands[0][0], "-m", "halpha"] for command in commands)


def test_dashboard_job_manager_accepts_product_run_command_intents(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    (tmp_path / "runs" / "run-1").mkdir(parents=True)
    commands: list[list[str]] = []
    stdout = "\n".join(
        [
            "Halpha run succeeded.",
            "run_id: run-1",
            "report: runs/run-1/report/report.md",
            "manifest: runs/run-1/run_manifest.json",
        ]
    )

    def fake_popen(command, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        commands.append(command)
        return _FakeProcess(stdout=stdout, stderr="", returncode=0)

    monkeypatch.setattr("halpha.dashboard.jobs.subprocess.Popen", fake_popen)
    manager = DashboardJobManager(config, config_path=config_path)
    cases = [
        ("run", {"confirm_codex": True}, ["python", "-m", "halpha", "run", "--config", "<external-config>"]),
        (
            "run_no_codex",
            {},
            ["python", "-m", "halpha", "run", "--config", "<external-config>", "--no-codex"],
        ),
        (
            "run_until",
            {"stage_name": "build_materials"},
            [
                "python",
                "-m",
                "halpha",
                "run",
                "--config",
                "<external-config>",
                "--until",
                "build_materials",
            ],
        ),
        (
            "run_until",
            {"stage_name": "generate_report", "confirm_codex": True},
            [
                "python",
                "-m",
                "halpha",
                "run",
                "--config",
                "<external-config>",
                "--until",
                "generate_report",
            ],
        ),
        (
            "stage_rerun",
            {"stage_name": "build_source_evidence", "run_dir": "runs/run-1"},
            [
                "python",
                "-m",
                "halpha",
                "stage",
                "build_source_evidence",
                "--config",
                "<external-config>",
                "--run-dir",
                "runs/run-1",
            ],
        ),
    ]

    for intent, params, preview in cases:
        job = manager.create_job({"intent": intent, "params": params})
        completed = _wait_for_terminal(manager, job["job_id"])
        assert completed["status"] == "succeeded"
        assert completed["intent"] == intent
        assert completed["command"] == preview
        assert completed["result_refs"] == {
            "run_id": "run-1",
            "report": "runs/run-1/report/report.md",
            "run_manifest": "runs/run-1/run_manifest.json",
        }
        assert "runs/run-1/run_manifest.json" in completed["source_artifacts"]
        assert "runs/run-1/report/report.md" in completed["source_artifacts"]

    assert len(commands) == len(cases)
    assert all(command[:3] == [commands[0][0], "-m", "halpha"] for command in commands)


def test_dashboard_job_manager_accepts_strategy_and_text_command_intents(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_strategy_text_config(tmp_path)
    config = load_config(config_path)
    input_path = tmp_path / "runs" / "run-1" / "raw" / "text_events.json"
    input_path.parent.mkdir(parents=True)
    input_path.write_text("{}", encoding="utf-8")
    commands: list[list[str]] = []
    outputs = [
        "\n".join(
            [
                "Halpha backtest succeeded.",
                "strategy_backtest: runs/manual-backtests/run-1/strategy_backtest.json",
                "manifest: runs/manual-backtests/run-1/manifest.json",
            ]
        ),
        "\n".join(
            [
                "Halpha experiment succeeded.",
                "strategy_experiment: runs/manual-experiments/run-1/strategy_experiment.json",
                "strategy_benchmark_suite: runs/manual-experiments/run-1/strategy_benchmark_suite.json",
                "strategy_effectiveness_gates: runs/manual-experiments/run-1/strategy_effectiveness_gates.json",
                "manifest: runs/manual-experiments/run-1/manifest.json",
            ]
        ),
        "manifest: data/models/prep/model_prepare_manifest.json",
        "\n".join(
            [
                "Halpha text intelligence succeeded.",
                "output_dir: runs/text-intel/run-1",
                "text_event_records: analysis/text_event_records.json",
                "text_event_classification_evidence: analysis/text_event_classification_evidence.json",
                "text_event_topics: analysis/text_event_topics.json",
                "text_event_signals: analysis/text_event_signals.json",
                "event_intelligence_material: analysis/event_intelligence_material.md",
                "manifest: runs/text-intel/run-1/manifest.json",
            ]
        ),
    ]

    def fake_popen(command, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        index = len(commands)
        commands.append(command)
        return _FakeProcess(stdout=outputs[index], stderr="", returncode=0)

    monkeypatch.setattr("halpha.dashboard.jobs.subprocess.Popen", fake_popen)
    manager = DashboardJobManager(config, config_path=config_path)
    cases = [
        (
            "backtest",
            {
                "strategy_name": "tsmom_vol_scaled",
                "symbol": "BTCUSDT",
                "timeframe": "1d",
                "output_dir": "runs/manual-backtests",
            },
            [
                "python",
                "-m",
                "halpha",
                "backtest",
                "--config",
                "<external-config>",
                "--strategy",
                "tsmom_vol_scaled",
                "--symbol",
                "BTCUSDT",
                "--timeframe",
                "1d",
                "--output-dir",
                "runs/manual-backtests",
            ],
            {
                "strategy_backtest": "runs/manual-backtests/run-1/strategy_backtest.json",
                "manifest": "runs/manual-backtests/run-1/manifest.json",
            },
        ),
        (
            "experiment",
            {"strategy_names": ["tsmom_vol_scaled", "sma_cross_trend"], "output_dir": "runs/manual-experiments"},
            [
                "python",
                "-m",
                "halpha",
                "experiment",
                "--config",
                "<external-config>",
                "--strategy",
                "tsmom_vol_scaled",
                "--strategy",
                "sma_cross_trend",
                "--output-dir",
                "runs/manual-experiments",
            ],
            {
                "strategy_experiment": "runs/manual-experiments/run-1/strategy_experiment.json",
                "strategy_benchmark_suite": "runs/manual-experiments/run-1/strategy_benchmark_suite.json",
                "strategy_effectiveness_gates": "runs/manual-experiments/run-1/strategy_effectiveness_gates.json",
                "manifest": "runs/manual-experiments/run-1/manifest.json",
            },
        ),
        (
            "text_models_prepare",
            {"output_dir": "data/models/prep"},
            [
                "python",
                "-m",
                "halpha",
                "text-models",
                "prepare",
                "--config",
                "<external-config>",
                "--output-dir",
                "data/models/prep",
            ],
            {"manifest": "data/models/prep/model_prepare_manifest.json"},
        ),
        (
            "text_intel",
            {"input_path": "runs/run-1/raw/text_events.json", "output_dir": "runs/text-intel"},
            [
                "python",
                "-m",
                "halpha",
                "text-intel",
                "--config",
                "<external-config>",
                "--input",
                "runs/run-1/raw/text_events.json",
                "--output-dir",
                "runs/text-intel",
            ],
            {
                "output_dir": "runs/text-intel/run-1",
                "text_event_records": "runs/text-intel/run-1/analysis/text_event_records.json",
                "text_event_classification_evidence": (
                    "runs/text-intel/run-1/analysis/text_event_classification_evidence.json"
                ),
                "text_event_topics": "runs/text-intel/run-1/analysis/text_event_topics.json",
                "text_event_signals": "runs/text-intel/run-1/analysis/text_event_signals.json",
                "event_intelligence_material": "runs/text-intel/run-1/analysis/event_intelligence_material.md",
                "manifest": "runs/text-intel/run-1/manifest.json",
            },
        ),
    ]

    for intent, params, preview, expected_refs in cases:
        job = manager.create_job({"intent": intent, "params": params})
        completed = _wait_for_terminal(manager, job["job_id"])
        assert completed["status"] == "succeeded"
        assert completed["intent"] == intent
        assert completed["command"] == preview
        for key, value in expected_refs.items():
            assert completed["result_refs"][key] == value
        for key, value in expected_refs.items():
            if key != "output_dir":
                assert value in completed["source_artifacts"]

    assert len(commands) == len(cases)
    assert all(command[:3] == [commands[0][0], "-m", "halpha"] for command in commands)


def test_dashboard_job_manager_rejects_unsafe_run_dir_before_process(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("unsafe run_dir must not start a process")

    monkeypatch.setattr("halpha.dashboard.jobs.subprocess.Popen", fail_popen)
    manager = DashboardJobManager(config, config_path=config_path)

    job = manager.create_job({"intent": "data_inspect", "params": {"run_dir": "../outside"}})

    assert job["status"] == "blocked"
    assert "run_dir must stay within" in job["errors"][0]


def test_dashboard_job_manager_rejects_stage_rerun_unsafe_run_dir_before_process(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("unsafe run_dir must not start a process")

    monkeypatch.setattr("halpha.dashboard.jobs.subprocess.Popen", fail_popen)
    manager = DashboardJobManager(config, config_path=config_path)

    job = manager.create_job(
        {
            "intent": "stage_rerun",
            "params": {"stage_name": "build_source_evidence", "run_dir": "../outside"},
        }
    )

    assert job["status"] == "blocked"
    assert "run_dir must stay within" in job["errors"][0]


def test_dashboard_job_manager_rejects_invalid_stage_name_before_process(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("invalid stage_name must not start a process")

    monkeypatch.setattr("halpha.dashboard.jobs.subprocess.Popen", fail_popen)
    manager = DashboardJobManager(config, config_path=config_path)

    job = manager.create_job({"intent": "run_until", "params": {"stage_name": "not_a_stage"}})

    assert job["status"] == "blocked"
    assert "stage_name must be one of:" in job["errors"][0]


def test_dashboard_job_manager_rejects_unconfigured_strategy_values_before_process(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_strategy_text_config(tmp_path)
    config = load_config(config_path)

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("invalid configured values must not start a process")

    monkeypatch.setattr("halpha.dashboard.jobs.subprocess.Popen", fail_popen)
    manager = DashboardJobManager(config, config_path=config_path)
    cases = [
        (
            {"intent": "backtest", "params": {"strategy_name": "missing", "symbol": "BTCUSDT", "timeframe": "1d"}},
            "strategy_name is not configured or enabled",
        ),
        (
            {"intent": "backtest", "params": {"strategy_name": "tsmom_vol_scaled", "symbol": "DOGEUSDT", "timeframe": "1d"}},
            "symbol is not configured",
        ),
        (
            {"intent": "backtest", "params": {"strategy_name": "tsmom_vol_scaled", "symbol": "BTCUSDT", "timeframe": "5m"}},
            "timeframe is not configured",
        ),
        (
            {"intent": "experiment", "params": {"strategy_names": ["breakout_atr_trend"]}},
            "strategy_names is not configured or enabled",
        ),
        (
            {"intent": "experiment", "params": {"strategy_names": "tsmom_vol_scaled"}},
            "strategy_names must be a non-empty list",
        ),
    ]

    for request, error in cases:
        job = manager.create_job(request)
        assert job["status"] == "blocked"
        assert error in job["errors"][0]


def test_dashboard_job_manager_rejects_unsafe_strategy_text_paths_before_process(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_strategy_text_config(tmp_path)
    config = load_config(config_path)

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("unsafe paths must not start a process")

    monkeypatch.setattr("halpha.dashboard.jobs.subprocess.Popen", fail_popen)
    manager = DashboardJobManager(config, config_path=config_path)
    cases = [
        (
            {
                "intent": "backtest",
                "params": {
                    "strategy_name": "tsmom_vol_scaled",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "output_dir": "../outside",
                },
            },
            "output_dir must stay within",
        ),
        (
            {"intent": "text_models_prepare", "params": {"output_dir": "../outside"}},
            "output_dir must stay within",
        ),
        (
            {"intent": "text_intel", "params": {"input_path": "../outside/text_events.json"}},
            "input_path must stay within",
        ),
        (
            {"intent": "text_intel", "params": {"input_path": "runs/missing/text_events.json"}},
            "input_path must reference an existing file",
        ),
    ]

    for request, error in cases:
        job = manager.create_job(request)
        assert job["status"] == "blocked"
        assert error in job["errors"][0]


def test_dashboard_job_manager_rejects_invalid_monitor_loop_params_before_process(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("invalid monitor loop params must not start a process")

    monkeypatch.setattr("halpha.dashboard.jobs.subprocess.Popen", fail_popen)
    manager = DashboardJobManager(config, config_path=config_path)
    cases = [
        ({"intent": "monitor_loop", "params": {}}, "max_cycles must be a positive integer"),
        ({"intent": "monitor_loop", "params": {"max_cycles": 0}}, "max_cycles must be a positive integer"),
        (
            {"intent": "monitor_loop", "params": {"max_cycles": 1, "interval_seconds": "1"}},
            "interval_seconds must be a positive integer",
        ),
    ]

    for request, error in cases:
        job = manager.create_job(request)
        assert job["status"] == "blocked"
        assert error in job["errors"][0]


def test_dashboard_job_manager_requires_codex_confirmation_before_process(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    (tmp_path / "runs" / "run-1").mkdir(parents=True)

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("Codex-capable jobs must not start without confirmation")

    monkeypatch.setattr("halpha.dashboard.jobs.subprocess.Popen", fail_popen)
    manager = DashboardJobManager(config, config_path=config_path)
    cases = [
        {"intent": "run", "params": {}},
        {"intent": "run_until", "params": {"stage_name": "generate_report"}},
        {"intent": "stage_rerun", "params": {"stage_name": "generate_report", "run_dir": "runs/run-1"}},
    ]

    for request in cases:
        job = manager.create_job(request)
        assert job["status"] == "blocked"
        assert "confirm_codex must be true" in job["errors"][0]


def test_dashboard_job_manager_rejects_unsupported_intent_params_before_process(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("unsupported params must not start a process")

    monkeypatch.setattr("halpha.dashboard.jobs.subprocess.Popen", fail_popen)
    manager = DashboardJobManager(config, config_path=config_path)

    job = manager.create_job({"intent": "monitor_inspect", "params": {"run_dir": "runs/run-1"}})

    assert job["status"] == "blocked"
    assert "unsupported monitor_inspect job parameter(s): run_dir" in job["errors"][0]


def test_dashboard_job_api_starts_product_run_intent(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    stdout = "\n".join(
        [
            "Halpha run succeeded.",
            "run_id: run-api",
            "manifest: runs/run-api/run_manifest.json",
        ]
    )
    monkeypatch.setattr(
        "halpha.dashboard.jobs.subprocess.Popen",
        lambda *args, **kwargs: _FakeProcess(stdout=stdout, stderr="", returncode=0),
    )
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    create_response = client.post("/api/jobs", json={"intent": "run_no_codex", "params": {}})
    payload = create_response.json()
    completed = _wait_for_api_terminal(client, payload["job_id"])

    assert create_response.status_code == 200
    assert completed["status"] == "succeeded"
    assert completed["intent"] == "run_no_codex"
    assert completed["result_refs"]["run_manifest"] == "runs/run-api/run_manifest.json"
    assert str(tmp_path) not in create_response.text


def test_dashboard_job_api_starts_strategy_command_intent(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_strategy_text_config(tmp_path)
    config = load_config(config_path)
    stdout = "\n".join(
        [
            "Halpha backtest succeeded.",
            "strategy_backtest: runs/backtests/run-api/strategy_backtest.json",
            "manifest: runs/backtests/run-api/manifest.json",
        ]
    )
    monkeypatch.setattr(
        "halpha.dashboard.jobs.subprocess.Popen",
        lambda *args, **kwargs: _FakeProcess(stdout=stdout, stderr="", returncode=0),
    )
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    create_response = client.post(
        "/api/jobs",
        json={
            "intent": "backtest",
            "params": {
                "strategy_name": "tsmom_vol_scaled",
                "symbol": "BTCUSDT",
                "timeframe": "1d",
            },
        },
    )
    payload = create_response.json()
    completed = _wait_for_api_terminal(client, payload["job_id"])

    assert create_response.status_code == 200
    assert completed["status"] == "succeeded"
    assert completed["intent"] == "backtest"
    assert completed["result_refs"]["strategy_backtest"] == "runs/backtests/run-api/strategy_backtest.json"
    assert completed["result_refs"]["manifest"] == "runs/backtests/run-api/manifest.json"
    assert str(tmp_path) not in create_response.text


def test_dashboard_job_manager_normalizes_result_refs_without_external_path_leakage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    inside_manifest = tmp_path / "runs" / "run-api" / "run_manifest.json"
    outside_manifest = tmp_path.parent / "outside" / "run_manifest.json"
    stdout = "\n".join(
        [
            f"manifest: {inside_manifest}",
            f"report: {outside_manifest}",
        ]
    )
    monkeypatch.setattr(
        "halpha.dashboard.jobs.subprocess.Popen",
        lambda *args, **kwargs: _FakeProcess(stdout=stdout, stderr="", returncode=0),
    )
    manager = DashboardJobManager(config, config_path=config_path)

    job = manager.create_job({"intent": "run_no_codex", "params": {}})
    completed = _wait_for_terminal(manager, job["job_id"])

    assert completed["status"] == "succeeded"
    assert completed["result_refs"]["run_manifest"] == "runs/run-api/run_manifest.json"
    assert completed["result_refs"]["report"] == "<external-artifact>"
    assert "runs/run-api/run_manifest.json" in completed["source_artifacts"]
    assert "<external-artifact>" not in completed["source_artifacts"]
    assert str(tmp_path) not in str(completed)
    assert str(outside_manifest) not in str(completed)


def test_dashboard_job_manager_marks_relative_artifacts_external_when_output_dir_is_external(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_strategy_text_config(tmp_path)
    config = load_config(config_path)
    input_path = tmp_path / "runs" / "run-1" / "raw" / "text_events.json"
    input_path.parent.mkdir(parents=True)
    input_path.write_text("{}", encoding="utf-8")
    outside_dir = tmp_path.parent / "outside-text-intel"
    stdout = "\n".join(
        [
            f"output_dir: {outside_dir}",
            "text_event_records: analysis/text_event_records.json",
            f"manifest: {outside_dir / 'manifest.json'}",
        ]
    )
    monkeypatch.setattr(
        "halpha.dashboard.jobs.subprocess.Popen",
        lambda *args, **kwargs: _FakeProcess(stdout=stdout, stderr="", returncode=0),
    )
    manager = DashboardJobManager(config, config_path=config_path)

    job = manager.create_job(
        {
            "intent": "text_intel",
            "params": {
                "input_path": "runs/run-1/raw/text_events.json",
                "output_dir": "runs/text-intel",
            },
        }
    )
    completed = _wait_for_terminal(manager, job["job_id"])

    assert completed["status"] == "succeeded"
    assert completed["result_refs"]["output_dir"] == "<external-artifact>"
    assert completed["result_refs"]["text_event_records"] == "<external-artifact>"
    assert completed["result_refs"]["manifest"] == "<external-artifact>"
    assert "<external-artifact>" not in completed["source_artifacts"]
    assert str(outside_dir) not in str(completed)


def test_dashboard_job_manager_cancels_running_job(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    fake_process = _BlockingProcess()
    monkeypatch.setattr("halpha.dashboard.jobs.subprocess.Popen", lambda *args, **kwargs: fake_process)
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


def test_dashboard_job_manager_marks_stale_running_job_failed_on_restart(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    job_id = "20260622T000000Z_deadbeef"
    _seed_state_job(config_path, job_id=job_id, status="running", pid=99999999)
    manager = DashboardJobManager(config, config_path=config_path)

    detail = manager.get_job(job_id)
    listed = manager.list_jobs()["jobs"][0]

    assert detail is not None
    assert detail["status"] == "failed"
    assert "recorded PID was not treated as proof" in detail["errors"][0]
    assert listed["status"] == "failed"
    assert not (tmp_path / ".halpha" / "dashboard" / "jobs" / "index.json").exists()


def test_dashboard_job_manager_rejects_unattached_live_pid_as_process_identity(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    job_id = "20260622T000001Z_deadbeef"
    _seed_state_job(config_path, job_id=job_id, status="running", pid=os.getpid())
    manager = DashboardJobManager(config, config_path=config_path)

    detail = manager.get_job(job_id)

    assert detail is not None
    assert detail["status"] == "failed"
    assert detail["pid"] == os.getpid()
    assert "recorded PID was not treated as proof" in detail["errors"][0]


def test_dashboard_job_repository_rejects_terminal_transition_transactionally(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    job_id = "20260622T000002Z_deadbeef"
    _seed_state_job(config_path, job_id=job_id, status="succeeded")
    repository = DashboardJobRepository(config_path=config_path)
    job = repository.get_job(job_id)
    assert job is not None
    job["status"] = "running"
    job["updated_at"] = "2026-06-22T00:05:00Z"

    with pytest.raises(DashboardJobStoreError, match="terminal status succeeded"):
        repository.save_job(job, event_type="invalid")

    persisted = repository.get_job(job_id)
    events = repository.job_events(job_id)
    assert persisted is not None
    assert persisted["status"] == "succeeded"
    assert [event["event_type"] for event in events] == ["seed"]


def test_dashboard_job_api_lists_and_reads_jobs(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    monkeypatch.setattr(
        "halpha.dashboard.jobs.subprocess.Popen",
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


def test_dashboard_job_api_rejects_path_shaped_job_ids(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    outside = tmp_path / ".halpha" / "dashboard" / "outside_jobs"
    outside.mkdir(parents=True)
    (outside / "job.json").write_text(
        json.dumps({"schema_version": 1, "artifact_type": "dashboard_job", "job_id": "outside", "status": "leaked"}),
        encoding="utf-8",
    )
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    detail_response = client.get("/api/jobs/..%5Coutside_jobs")
    cancel_response = client.post("/api/jobs/..%5Coutside_jobs/cancel")

    assert detail_response.status_code == 200
    assert cancel_response.status_code == 200
    assert detail_response.json()["status"] == "missing"
    assert cancel_response.json()["status"] == "missing"
    assert "leaked" not in detail_response.text
    assert "leaked" not in cancel_response.text


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


def _wait_for_log_event(path: Path, job_id: str, event_name: str) -> str:
    for _ in range(50):
        if path.exists():
            text = path.read_text(encoding="utf-8")
            events = [json.loads(line) for line in text.splitlines() if line.strip()]
            if any(event.get("job_id") == job_id and event.get("event") == event_name for event in events):
                return text
        time.sleep(0.05)
    raise AssertionError(f"log event was not written: {event_name}")


def _seed_state_job(config_path: Path, *, job_id: str, status: str, pid: int | None = None) -> None:
    repository = DashboardJobRepository(config_path=config_path)
    repository.save_job(
        {
            "schema_version": 1,
            "artifact_type": "dashboard_job",
            "job_id": job_id,
            "intent": "monitor_loop",
            "kind": "monitor_loop",
            "requested_by": "Dashboard",
            "params": {},
            "config_ref": "config.yaml",
            "status": status,
            "created_at": "2026-06-22T00:00:00Z",
            "updated_at": "2026-06-22T00:00:00Z",
            "started_at": "2026-06-22T00:00:00Z",
            "finished_at": None,
            "pid": pid,
            "exit_code": None,
            "cancellable": True,
            "command": ["python", "-m", "halpha", "monitor", "run"],
            "job_dir": f".halpha/dashboard/job_logs/{job_id}",
            "logs": {
                "stdout_ref": f".halpha/dashboard/job_logs/{job_id}/stdout.log",
                "stderr_ref": f".halpha/dashboard/job_logs/{job_id}/stderr.log",
                "stdout_chars": 0,
                "stderr_chars": 0,
                "stdout_truncated": False,
                "stderr_truncated": False,
                "max_chars": MAX_JOB_LOG_CHARS,
            },
            "result_refs": {},
            "source_artifacts": [],
            "warnings": [],
            "errors": [],
        },
        event_type="seed",
    )


def _write_config(tmp_path: Path, *, name: str = "config.yaml") -> Path:
    path = tmp_path / name
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


def _write_strategy_text_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
run:
  output_dir: runs
market:
  enabled: true
  source: binance
  symbols:
    - BTCUSDT
    - ETHUSDT
  ohlcv:
    storage_dir: data/market/ohlcv
    timeframes:
      - 1d
      - 1h
    lookback:
      1d: 30
      1h: 48
quant:
  enabled: true
  strategies:
    - name: tsmom_vol_scaled
      enabled: true
    - name: sma_cross_trend
      enabled: true
    - name: breakout_atr_trend
      enabled: false
text:
  enabled: true
  intelligence:
    enabled: true
    model_cache_dir: data/models/text
    allow_model_download: false
    models:
      embedding:
        provider: sentence_transformers
        name: sentence-transformers/all-MiniLM-L6-v2
        revision: pinned
      classifier:
        provider: transformers_zero_shot
        name: facebook/bart-large-mnli
        revision: pinned
      sentiment:
        provider: transformers_text_classification
        name: ProsusAI/finbert
        revision: pinned
      ner:
        provider: gliner
        name: urchade/gliner_medium-v2.1
        revision: pinned
    thresholds:
      duplicate_similarity: 0.92
      same_topic_similarity: 0.82
      classifier_accept_score: 0.65
      classifier_top_margin: 0.10
      entity_accept_score: 0.50
      max_topic_window_hours: 48
  sources:
    - name: fixture
      type: rss
      url: https://example.com/feed.xml
report:
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return path
