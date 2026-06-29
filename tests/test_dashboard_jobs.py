from __future__ import annotations

from contextlib import closing

import json
import os
from pathlib import Path
import sqlite3
import sys
import threading
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from halpha.config import load_config
from halpha.dashboard import create_dashboard_app
from halpha.runtime.command_job_commands import (
    CommandJobBuilder,
    CommandJobCommand,
    CommandJobError,
    CommandSpec,
    command_config_ref,
)
from halpha.runtime.command_job_execution import CommandJobExecutionResult
from halpha.runtime.command_job_store import CommandJobRepository, CommandJobStoreError, apply_command_job_migrations
from halpha.runtime.command_jobs import CommandJobManager, MAX_JOB_LOG_CHARS
from halpha.runtime.mutation_lease import acquire_mutation_lease
from halpha.runtime.state_store import open_runtime_state_connection, runtime_state_path


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_command_job_command_builder_builds_command_preview(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    builder = CommandJobBuilder(config, config_path=config_path, base=tmp_path)

    command = builder.build("validate", {})

    assert command.spec.intent == "validate"
    assert command.preview == ["python", "-m", "halpha", "validate", "--config", "<external-config>"]
    assert command.command[1:] == ["-m", "halpha", "validate", "--config", str(config_path.resolve())]


def test_command_job_command_builder_rejects_unsupported_intent(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    builder = CommandJobBuilder(config, config_path=config_path, base=tmp_path)

    try:
        builder.build("shell", {"command": "echo no"})
    except CommandJobError as exc:
        assert exc.status == "unsupported"
        assert str(exc) == "unsupported command job intent: shell"
    else:
        raise AssertionError("unsupported intent must be rejected by command builder")


def test_command_job_api_rejects_unsupported_intent_before_process(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("unsupported intent must not start a process")

    monkeypatch.setattr("halpha.runtime.command_jobs.subprocess.Popen", fail_popen)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.post("/api/jobs", json={"intent": "shell", "params": {"command": "echo no"}})

    assert response.status_code == 200
    payload = response.json()
    assert payload["artifact_type"] == "command_job"
    assert payload["status"] == "unsupported"
    assert payload["intent"] == "shell"
    assert payload["pid"] is None
    assert payload["exit_code"] is None
    assert "unsupported command job intent" in payload["errors"][0]
    assert runtime_state_path(config_path=config_path).is_file()
    assert not (tmp_path / ".halpha" / "dashboard" / "jobs" / payload["job_id"] / "job.json").exists()
    assert not (tmp_path / "runs" / "dashboard").exists()
    assert str(tmp_path) not in response.text


def test_command_job_manager_blocks_mutating_job_without_starting_process_when_runtime_lease_is_busy(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    lease = acquire_mutation_lease(
        config_path=config_path,
        owner_kind="test",
        workflow="product_run",
        requested_by="CLI",
        owner_id="external-owner",
        owner_pid=os.getpid(),
    )

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("blocked command job must not start a process")

    monkeypatch.setattr("halpha.runtime.command_jobs.subprocess.Popen", fail_popen)
    manager = CommandJobManager(config, config_path=config_path, requested_by="Dashboard")

    try:
        job = manager.create_job({"intent": "run_no_codex", "params": {}})
        completed = _wait_for_terminal(manager, job["job_id"])
    finally:
        lease.release()

    assert completed["status"] == "blocked"
    assert completed["pid"] is None
    assert completed["exit_code"] is None
    assert completed["cancellable"] is False
    assert "another mutating Halpha workflow" in completed["errors"][0]
    assert completed["diagnostic"]["database_ref"] == ".halpha/state.sqlite"
    assert completed["diagnostic"]["private_values_embedded"] is False
    assert not (tmp_path / "runs").exists()
    assert str(tmp_path) not in str(completed)


def test_command_job_manager_runs_allowlisted_job_with_bounded_redacted_logs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_private_config(tmp_path)
    config = load_config(config_path)
    secret = "http://private-proxy.example:7890"
    stdout = f"{secret}\n{config_path}\n" + ("x" * (MAX_JOB_LOG_CHARS + 12))
    fake_process = _FakeProcess(stdout=stdout, stderr=f"stderr {secret}", returncode=0)
    monkeypatch.setattr("halpha.runtime.command_jobs.subprocess.Popen", lambda *args, **kwargs: fake_process)
    manager = CommandJobManager(config, config_path=config_path)

    job = manager.create_job({"intent": "validate", "params": {}})
    completed = _wait_for_terminal(manager, job["job_id"])

    assert completed["status"] == "succeeded"
    assert completed["exit_code"] == 0
    assert completed["pid"] == fake_process.pid
    assert completed["requested_by"] == "CLI"
    assert completed["requester"] == {}
    assert completed["logs"]["stdout_truncated"] is True
    assert completed["logs"]["stderr_truncated"] is False
    assert completed["command"] == ["python", "-m", "halpha", "validate", "--config", "<external-config>"]
    assert completed["job_dir"].startswith(".halpha/command_jobs/job_logs/")
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


def test_command_job_manager_records_explicit_requester_metadata(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    monkeypatch.setattr(
        "halpha.runtime.command_jobs.subprocess.Popen",
        lambda *args, **kwargs: _FakeProcess(stdout="ok", stderr="", returncode=0),
    )
    manager = CommandJobManager(
        config,
        config_path=config_path,
        requested_by="Monitor",
        requester={"source": "monitor_service", "service_instance_id": "monitor-1"},
    )

    job = manager.create_job(
        {
            "intent": "validate",
            "params": {},
            "requested_by": "CLI",
            "requester": {"source": "manual_cli"},
        }
    )
    completed = _wait_for_terminal(manager, job["job_id"])

    assert completed["status"] == "succeeded"
    assert completed["requested_by"] == "CLI"
    assert completed["requester"] == {"service_instance_id": "monitor-1", "source": "manual_cli"}


def test_command_job_logging_includes_context_without_private_values(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_private_config(tmp_path)
    config = load_config(config_path)
    secret = "http://private-proxy.example:7890"
    fake_process = _FakeProcess(stdout=f"stdout {secret}", stderr="", returncode=0)
    monkeypatch.setattr("halpha.runtime.command_jobs.subprocess.Popen", lambda *args, **kwargs: fake_process)
    manager = CommandJobManager(config, config_path=config_path)

    job = manager.create_job({"intent": "validate", "params": {}})
    completed = _wait_for_terminal(manager, job["job_id"])

    log_text = _wait_for_log_event(tmp_path / "logs" / "halpha.log", completed["job_id"], "command_job.finished")
    events = [json.loads(line) for line in log_text.splitlines() if line.strip()]
    assert completed["job_id"] in log_text
    assert "command_job.start" in {event.get("event") for event in events}
    assert "command_job.finished" in {event.get("event") for event in events}
    assert secret not in log_text
    assert str(config_path) not in log_text
    assert str(tmp_path) not in log_text


def test_command_job_start_failure_records_bounded_diagnostic(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_private_config(tmp_path)
    config = load_config(config_path)
    secret = "http://private-proxy.example:7890"

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise OSError(f"cannot start with {secret} at {config_path}")

    monkeypatch.setattr("halpha.runtime.command_jobs.subprocess.Popen", fail_popen)
    manager = CommandJobManager(config, config_path=config_path)

    job = manager.create_job({"intent": "validate", "params": {}})
    completed = _wait_for_terminal(manager, job["job_id"])
    state_bytes = runtime_state_path(config_path=config_path).read_bytes()
    stderr_text = (tmp_path / completed["logs"]["stderr_ref"]).read_text(encoding="utf-8")
    log_text = _wait_for_log_event(tmp_path / "logs" / "halpha.log", completed["job_id"], "command_job.start_failed")

    assert completed["status"] == "failed"
    assert completed["diagnostic"] == {
        "exception_type": "OSError",
        "traceback_embedded": False,
        "context": {"phase": "process_start"},
    }
    assert "<redacted>" in completed["errors"][0]
    assert "job process could not start" in stderr_text
    assert "<redacted>" in stderr_text
    assert "process_start" in log_text
    assert secret not in stderr_text
    assert str(config_path) not in stderr_text
    assert secret.encode() not in state_bytes
    assert str(config_path).encode() not in state_bytes
    assert str(tmp_path).encode() not in state_bytes


def test_internal_command_job_exception_records_diagnostic_log(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_private_config(tmp_path)
    config = load_config(config_path)
    secret = "http://private-proxy.example:7890"

    def fail_internal_job(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError(f"internal failed through {secret} at {config_path}")

    monkeypatch.setattr("halpha.runtime.command_jobs.execute_command_job", fail_internal_job)
    manager = CommandJobManager(config, config_path=config_path, execution_mode="internal")

    job = manager.create_job({"intent": "validate", "params": {}})
    completed = _wait_for_terminal(manager, job["job_id"])
    stderr_text = (tmp_path / completed["logs"]["stderr_ref"]).read_text(encoding="utf-8")
    log_text = _wait_for_log_event(tmp_path / "logs" / "halpha.log", completed["job_id"], "command_job.internal_failed")
    events = [json.loads(line) for line in log_text.splitlines() if line.strip()]
    failure = next(event for event in events if event.get("event") == "command_job.internal_failed")

    assert completed["status"] == "failed"
    assert completed["diagnostic"] == {
        "exception_type": "RuntimeError",
        "traceback_embedded": False,
        "context": {"phase": "internal_execution"},
    }
    assert "internal command job failed" in stderr_text
    assert "<redacted>" in stderr_text
    assert failure["phase"] == "internal_execution"
    assert failure["exception_type"] == "RuntimeError"
    assert secret not in log_text
    assert str(config_path) not in log_text


def test_command_job_manager_preserves_relative_config_ref(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = Path("config.yaml")
    _write_config(tmp_path)
    config = load_config(config_path)
    monkeypatch.setattr(
        "halpha.runtime.command_jobs.subprocess.Popen",
        lambda *args, **kwargs: _FakeProcess(stdout="config.yaml", stderr="", returncode=0),
    )
    manager = CommandJobManager(config, config_path=config_path)

    job = manager.create_job({"intent": "validate", "params": {}})
    completed = _wait_for_terminal(manager, job["job_id"])

    assert completed["command"] == ["python", "-m", "halpha", "validate", "--config", "config.yaml"]
    stdout_log = (tmp_path / completed["logs"]["stdout_ref"]).read_text(encoding="utf-8")
    assert "config.yaml" in stdout_log


def test_command_job_config_ref_rejects_traversal_like_relative_path() -> None:
    assert command_config_ref(Path("../private/config.yaml")) == "<external-config>"
    assert command_config_ref(Path("config.yaml")) == "config.yaml"


def test_command_job_manager_passes_valid_subdirectory_config_path(
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

    monkeypatch.setattr("halpha.runtime.command_jobs.subprocess.Popen", fake_popen)
    manager = CommandJobManager(config, config_path=config_path)

    job = manager.create_job({"intent": "validate", "params": {}})
    completed = _wait_for_terminal(manager, job["job_id"])

    assert completed["command"] == ["python", "-m", "halpha", "validate", "--config", "configs/local.yaml"]
    assert cwd_values == [tmp_path.resolve()]
    assert Path(commands[0][-1]).is_file()
    assert Path(commands[0][-1]).resolve() == (tmp_path / config_path).resolve()
    stdout_log = (tmp_path / completed["logs"]["stdout_ref"]).read_text(encoding="utf-8")
    assert str((tmp_path / config_path).resolve()) not in stdout_log
    assert completed["job_dir"].startswith(".halpha/command_jobs/job_logs/")
    assert not (config_dir / "runs").exists()


def test_command_job_manager_accepts_readonly_command_intents(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    (tmp_path / "runs" / "run-1").mkdir(parents=True)
    commands: list[list[str]] = []

    def fake_popen(command, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        commands.append(command)
        return _FakeProcess(stdout="ok", stderr="", returncode=0)

    monkeypatch.setattr("halpha.runtime.command_jobs.subprocess.Popen", fake_popen)
    manager = CommandJobManager(config, config_path=config_path)
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


def test_command_job_manager_accepts_monitor_command_intents(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    commands: list[list[str]] = []
    outputs = [
        "Halpha monitor dry run succeeded.\ncycle_execution: not_run",
        "Halpha monitor cycle succeeded.\nmonitor_manifest: runs/monitor/cycles/cycle-1/monitor_cycle_manifest.json",
    ]

    def fake_popen(command, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        index = len(commands)
        commands.append(command)
        return _FakeProcess(stdout=outputs[index], stderr="", returncode=0)

    monkeypatch.setattr("halpha.runtime.command_jobs.subprocess.Popen", fake_popen)
    manager = CommandJobManager(config, config_path=config_path)
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


def test_command_job_manager_accepts_product_run_command_intents(tmp_path: Path, monkeypatch) -> None:
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

    monkeypatch.setattr("halpha.runtime.command_jobs.subprocess.Popen", fake_popen)
    manager = CommandJobManager(config, config_path=config_path)
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


def test_command_job_manager_accepts_strategy_and_text_command_intents(
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
        "\n".join(
            [
                "Halpha optimization succeeded.",
                "strategy_optimization: runs/manual-optimizations/run-1/strategy_optimization.json",
                "strategy_benchmark_suite: runs/manual-optimizations/run-1/strategy_benchmark_suite.json",
                "manifest: runs/manual-optimizations/run-1/manifest.json",
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

    monkeypatch.setattr("halpha.runtime.command_jobs.subprocess.Popen", fake_popen)
    manager = CommandJobManager(config, config_path=config_path)
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
            "optimize",
            {
                "strategy_name": "tsmom_vol_scaled",
                "grid": {"return_window": [1, 2], "volatility_window": [1]},
                "max_combinations": 4,
                "walk_forward_train_rows": 3,
                "output_dir": "runs/manual-optimizations",
            },
            [
                "python",
                "-m",
                "halpha",
                "optimize",
                "--config",
                "<external-config>",
                "--strategy",
                "tsmom_vol_scaled",
                "--grid",
                "return_window=1,2",
                "--grid",
                "volatility_window=1",
                "--max-combinations",
                "4",
                "--walk-forward-train-rows",
                "3",
                "--output-dir",
                "runs/manual-optimizations",
            ],
            {
                "strategy_optimization": "runs/manual-optimizations/run-1/strategy_optimization.json",
                "strategy_benchmark_suite": "runs/manual-optimizations/run-1/strategy_benchmark_suite.json",
                "manifest": "runs/manual-optimizations/run-1/manifest.json",
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


def test_command_job_manager_rejects_unsafe_run_dir_before_process(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("unsafe run_dir must not start a process")

    monkeypatch.setattr("halpha.runtime.command_jobs.subprocess.Popen", fail_popen)
    manager = CommandJobManager(config, config_path=config_path)

    job = manager.create_job({"intent": "data_inspect", "params": {"run_dir": "../outside"}})

    assert job["status"] == "blocked"
    assert "run_dir must stay within" in job["errors"][0]


def test_command_job_manager_rejects_stage_rerun_unsafe_run_dir_before_process(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("unsafe run_dir must not start a process")

    monkeypatch.setattr("halpha.runtime.command_jobs.subprocess.Popen", fail_popen)
    manager = CommandJobManager(config, config_path=config_path)

    job = manager.create_job(
        {
            "intent": "stage_rerun",
            "params": {"stage_name": "build_source_evidence", "run_dir": "../outside"},
        }
    )

    assert job["status"] == "blocked"
    assert "run_dir must stay within" in job["errors"][0]


def test_command_job_manager_rejects_invalid_stage_name_before_process(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("invalid stage_name must not start a process")

    monkeypatch.setattr("halpha.runtime.command_jobs.subprocess.Popen", fail_popen)
    manager = CommandJobManager(config, config_path=config_path)

    job = manager.create_job({"intent": "run_until", "params": {"stage_name": "not_a_stage"}})

    assert job["status"] == "blocked"
    assert "stage_name must be one of:" in job["errors"][0]


def test_command_job_manager_rejects_unconfigured_strategy_values_before_process(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_strategy_text_config(tmp_path)
    config = load_config(config_path)

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("invalid configured values must not start a process")

    monkeypatch.setattr("halpha.runtime.command_jobs.subprocess.Popen", fail_popen)
    manager = CommandJobManager(config, config_path=config_path)
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
        (
            {"intent": "optimize", "params": {"strategy_name": "missing"}},
            "strategy_name is not configured or enabled",
        ),
        (
            {
                "intent": "optimize",
                "params": {
                    "strategy_name": "tsmom_vol_scaled",
                    "grid": {"return_window": [1]},
                    "grid_args": ["return_window=1"],
                },
            },
            "grid and grid_args cannot both be provided",
        ),
        (
            {"intent": "optimize", "params": {"strategy_name": "tsmom_vol_scaled", "max_combinations": 0}},
            "max_combinations must be a positive integer",
        ),
    ]

    for request, error in cases:
        job = manager.create_job(request)
        assert job["status"] == "blocked"
        assert error in job["errors"][0]


def test_command_job_manager_rejects_unsafe_strategy_text_paths_before_process(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_strategy_text_config(tmp_path)
    config = load_config(config_path)

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("unsafe paths must not start a process")

    monkeypatch.setattr("halpha.runtime.command_jobs.subprocess.Popen", fail_popen)
    manager = CommandJobManager(config, config_path=config_path)
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


def test_command_job_manager_rejects_monitor_loop_intent_before_process(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("invalid monitor loop params must not start a process")

    monkeypatch.setattr("halpha.runtime.command_jobs.subprocess.Popen", fail_popen)
    manager = CommandJobManager(config, config_path=config_path)
    job = manager.create_job({"intent": "monitor_loop", "params": {"max_cycles": 1, "interval_seconds": 1}})

    assert job["status"] == "unsupported"
    assert "unsupported command job intent: monitor_loop" in job["errors"][0]


def test_command_job_manager_requires_codex_confirmation_before_process(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    (tmp_path / "runs" / "run-1").mkdir(parents=True)

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("Codex-capable jobs must not start without confirmation")

    monkeypatch.setattr("halpha.runtime.command_jobs.subprocess.Popen", fail_popen)
    manager = CommandJobManager(config, config_path=config_path)
    cases = [
        {"intent": "run", "params": {}},
        {"intent": "run_until", "params": {"stage_name": "generate_report"}},
        {"intent": "stage_rerun", "params": {"stage_name": "generate_report", "run_dir": "runs/run-1"}},
    ]

    for request in cases:
        job = manager.create_job(request)
        assert job["status"] == "blocked"
        assert "confirm_codex must be true" in job["errors"][0]


def test_command_job_manager_rejects_unsupported_intent_params_before_process(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("unsupported params must not start a process")

    monkeypatch.setattr("halpha.runtime.command_jobs.subprocess.Popen", fail_popen)
    manager = CommandJobManager(config, config_path=config_path)

    job = manager.create_job({"intent": "monitor_inspect", "params": {"run_dir": "runs/run-1"}})

    assert job["status"] == "blocked"
    assert "unsupported monitor_inspect job parameter(s): run_dir" in job["errors"][0]


def test_command_job_api_starts_product_run_intent(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    stdout = "\n".join(
        [
            "Halpha run succeeded.",
            "run_id: run-api",
            "manifest: runs/run-api/run_manifest.json",
        ]
    )
    captured_calls: list[dict[str, Any]] = []

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("dashboard API jobs must use internal execution")

    def fake_execute_command_job(*args, **kwargs):  # noqa: ANN002, ANN003
        captured_calls.append(kwargs)
        return CommandJobExecutionResult(exit_code=0, stdout=stdout)

    monkeypatch.setattr(
        "halpha.runtime.command_jobs.subprocess.Popen",
        fail_popen,
    )
    monkeypatch.setattr(
        "halpha.runtime.command_jobs.execute_command_job",
        fake_execute_command_job,
    )
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    create_response = client.post("/api/jobs", json={"intent": "run_no_codex", "params": {}})
    payload = create_response.json()
    completed = _wait_for_api_terminal(client, payload["job_id"])

    assert create_response.status_code == 200
    assert completed["status"] == "succeeded"
    assert completed["intent"] == "run_no_codex"
    assert completed["requested_by"] == "Core"
    assert completed["requester"] == {"source": "core_api"}
    assert completed["command"] == ["internal", "run_no_codex"]
    assert completed["pid"] is None
    assert completed["result_refs"]["run_manifest"] == "runs/run-api/run_manifest.json"
    assert captured_calls[0]["spec"].intent == "run_no_codex"
    assert captured_calls[0]["run_trigger"]["source"] == "Core"
    assert captured_calls[0]["run_trigger"]["intent"] == "run_no_codex"
    assert captured_calls[0]["run_trigger"]["job_id"] == completed["job_id"]
    assert str(tmp_path) not in create_response.text


def test_command_job_api_starts_strategy_command_intent(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_strategy_text_config(tmp_path)
    config = load_config(config_path)
    stdout = "\n".join(
        [
            "Halpha backtest succeeded.",
            "strategy_backtest: runs/backtests/run-api/strategy_backtest.json",
            "manifest: runs/backtests/run-api/manifest.json",
        ]
    )
    captured_calls: list[dict[str, Any]] = []

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("dashboard API jobs must use internal execution")

    def fake_execute_command_job(*args, **kwargs):  # noqa: ANN002, ANN003
        captured_calls.append(kwargs)
        return CommandJobExecutionResult(exit_code=0, stdout=stdout)

    monkeypatch.setattr(
        "halpha.runtime.command_jobs.subprocess.Popen",
        fail_popen,
    )
    monkeypatch.setattr(
        "halpha.runtime.command_jobs.execute_command_job",
        fake_execute_command_job,
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
    assert completed["command"] == ["internal", "backtest"]
    assert completed["pid"] is None
    assert captured_calls[0]["params"]["strategy_name"] == "tsmom_vol_scaled"
    assert completed["result_refs"]["strategy_backtest"] == "runs/backtests/run-api/strategy_backtest.json"
    assert completed["result_refs"]["manifest"] == "runs/backtests/run-api/manifest.json"
    assert str(tmp_path) not in create_response.text


def test_strategy_action_api_starts_optimization_internal_job(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_strategy_text_config(tmp_path)
    config = load_config(config_path)
    stdout = "\n".join(
        [
            "Halpha optimization succeeded.",
            "strategy_optimization: runs/optimizations/run-api/strategy_optimization.json",
            "strategy_benchmark_suite: runs/optimizations/run-api/strategy_benchmark_suite.json",
            "manifest: runs/optimizations/run-api/manifest.json",
        ]
    )
    captured_calls: list[dict[str, Any]] = []

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("dashboard strategy action jobs must use internal execution")

    def fake_execute_command_job(*args, **kwargs):  # noqa: ANN002, ANN003
        captured_calls.append(kwargs)
        return CommandJobExecutionResult(exit_code=0, stdout=stdout)

    monkeypatch.setattr("halpha.runtime.command_jobs.subprocess.Popen", fail_popen)
    monkeypatch.setattr("halpha.runtime.command_jobs.execute_command_job", fake_execute_command_job)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    create_response = client.post(
        "/api/strategies/actions/optimize",
        json={
            "params": {
                "strategy_name": "tsmom_vol_scaled",
                "grid": {"return_window": [1, 2]},
                "max_combinations": 4,
            }
        },
    )
    payload = create_response.json()
    completed = _wait_for_api_terminal(client, payload["job"]["job_id"])

    assert create_response.status_code == 200
    assert payload["artifact_type"] == "dashboard_strategy_action_job"
    assert payload["action"] == "optimize"
    assert completed["status"] == "succeeded"
    assert completed["intent"] == "optimize"
    assert completed["command"] == ["internal", "optimize"]
    assert captured_calls[0]["spec"].intent == "optimize"
    assert captured_calls[0]["params"]["grid"] == {"return_window": [1, 2]}
    assert completed["result_refs"]["strategy_optimization"] == "runs/optimizations/run-api/strategy_optimization.json"
    assert completed["result_refs"]["strategy_benchmark_suite"] == "runs/optimizations/run-api/strategy_benchmark_suite.json"
    assert str(tmp_path) not in create_response.text


def test_strategy_action_api_rejects_unknown_action_before_job_creation(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_strategy_text_config(tmp_path)
    config = load_config(config_path)

    def fail_create_job(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("unsupported strategy action must not create a job")

    monkeypatch.setattr("halpha.runtime.command_jobs.CommandJobManager.create_job", fail_create_job)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.post("/api/strategies/actions/shell", json={"params": {}})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unsupported"
    assert payload["job"] is None
    assert "strategy action must be one of:" in payload["errors"][0]
    assert str(tmp_path) not in response.text


def test_command_job_manager_preserves_attached_internal_running_job(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    started = threading.Event()
    release = threading.Event()

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("internal command job must not start a process")

    def fake_execute_command_job(*args, **kwargs):  # noqa: ANN002, ANN003
        started.set()
        release.wait(timeout=2)
        return CommandJobExecutionResult(exit_code=0, stdout="ok")

    monkeypatch.setattr("halpha.runtime.command_jobs.subprocess.Popen", fail_popen)
    monkeypatch.setattr("halpha.runtime.command_jobs.execute_command_job", fake_execute_command_job)
    manager = CommandJobManager(config, config_path=config_path, execution_mode="internal")

    job = manager.create_job({"intent": "validate", "params": {}})
    assert started.wait(timeout=2)
    running = manager.get_job(job["job_id"])

    assert running["status"] == "running"
    assert running["runtime_attached"] is True
    assert running["process_alive"] is True
    release.set()
    completed = _wait_for_terminal(manager, job["job_id"])
    assert completed["status"] == "succeeded"


def test_command_job_manager_normalizes_result_refs_without_external_path_leakage(
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
            "health_state: /home/private/health_state.json",
        ]
    )
    monkeypatch.setattr(
        "halpha.runtime.command_jobs.subprocess.Popen",
        lambda *args, **kwargs: _FakeProcess(stdout=stdout, stderr="", returncode=0),
    )
    manager = CommandJobManager(config, config_path=config_path)

    job = manager.create_job({"intent": "run_no_codex", "params": {}})
    completed = _wait_for_terminal(manager, job["job_id"])

    assert completed["status"] == "succeeded"
    assert completed["result_refs"]["run_manifest"] == "runs/run-api/run_manifest.json"
    assert completed["result_refs"]["report"] == "<external-artifact>"
    assert completed["result_refs"]["health_state"] == "<external-artifact>"
    assert "runs/run-api/run_manifest.json" in completed["source_artifacts"]
    assert "<external-artifact>" not in completed["source_artifacts"]
    assert str(tmp_path) not in str(completed)
    assert str(outside_manifest) not in str(completed)
    assert "/home/private/health_state.json" not in str(completed)


def test_command_job_manager_marks_relative_artifacts_external_when_output_dir_is_external(
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
        "halpha.runtime.command_jobs.subprocess.Popen",
        lambda *args, **kwargs: _FakeProcess(stdout=stdout, stderr="", returncode=0),
    )
    manager = CommandJobManager(config, config_path=config_path)

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


def test_command_job_manager_cancels_running_job(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    fake_process = _BlockingProcess()
    monkeypatch.setattr("halpha.runtime.command_jobs.subprocess.Popen", lambda *args, **kwargs: fake_process)
    manager = CommandJobManager(config, config_path=config_path)

    job = manager.create_job({"intent": "validate", "params": {}})
    _wait_for_status(manager, job["job_id"], "running")
    cancel_payload = manager.cancel_job(job["job_id"])
    completed = _wait_for_terminal(manager, job["job_id"])

    assert cancel_payload["status"] == "cancel_requested"
    assert fake_process.terminated is True
    assert completed["status"] == "cancelled"
    assert completed["exit_code"] == -15
    assert "cancelled" in completed["warnings"][0]


@pytest.mark.skipif(os.name != "posix", reason="process-group tree cancellation is POSIX-specific")
def test_command_job_manager_cancels_complete_posix_process_tree(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    root_script = _write_process_tree_scripts(tmp_path, ignore_sigterm=False)
    tree_dir = tmp_path / "process-tree"
    _patch_job_command(monkeypatch, root_script=root_script, tree_dir=tree_dir)
    manager = CommandJobManager(config, config_path=config_path)

    job = manager.create_job({"intent": "validate", "params": {}})
    _wait_for_status(manager, job["job_id"], "running")
    child_pid = _wait_for_pid_file(tree_dir / "child.pid")
    grandchild_pid = _wait_for_pid_file(tree_dir / "grandchild.pid")
    cancel_payload = manager.cancel_job(job["job_id"])
    completed = _wait_for_terminal(manager, job["job_id"])

    assert cancel_payload["status"] == "cancel_requested"
    assert completed["status"] == "cancelled"
    assert completed["process_identity"]["strategy"] == "posix_process_group"
    assert completed["process_identity"]["verified"] is True
    assert completed["process_termination"]["confirmed_exit"] is True
    assert _wait_for_pid_exit(child_pid)
    assert _wait_for_pid_exit(grandchild_pid)


@pytest.mark.skipif(os.name != "posix", reason="process-group tree cancellation is POSIX-specific")
def test_command_job_manager_forces_posix_process_tree_after_grace_timeout(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    root_script = _write_process_tree_scripts(tmp_path, ignore_sigterm=True)
    tree_dir = tmp_path / "process-tree-force"
    monkeypatch.setattr("halpha.runtime.command_job_process.COMMAND_JOB_CANCEL_GRACE_SECONDS", 0.1)
    monkeypatch.setattr("halpha.runtime.command_job_process.COMMAND_JOB_FORCE_GRACE_SECONDS", 1.0)
    _patch_job_command(monkeypatch, root_script=root_script, tree_dir=tree_dir)
    manager = CommandJobManager(config, config_path=config_path)

    job = manager.create_job({"intent": "validate", "params": {}})
    _wait_for_status(manager, job["job_id"], "running")
    child_pid = _wait_for_pid_file(tree_dir / "child.pid")
    grandchild_pid = _wait_for_pid_file(tree_dir / "grandchild.pid")
    manager.cancel_job(job["job_id"])
    completed = _wait_for_terminal(manager, job["job_id"])

    assert completed["status"] == "cancelled"
    assert completed["process_termination"]["forced"] is True
    assert completed["process_termination"]["confirmed_exit"] is True
    assert _wait_for_pid_exit(child_pid)
    assert _wait_for_pid_exit(grandchild_pid)


def test_command_job_manager_keeps_cancelled_job_failed_when_tree_exit_unconfirmed(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    manager = CommandJobManager(config, config_path=config_path)
    job_id = "20260622T000003Z_deadbeef"
    _seed_state_job(config_path, job_id=job_id, status="cancel_requested", pid=12345)
    job = manager._repository.get_job(job_id)
    assert job is not None
    manager._cancel_requested.add(job_id)

    manager._finish_subprocess_job(
        job_id=job_id,
        job=job,
        spec=CommandSpec(
            intent="validate",
            kind="product_validation",
            cancellable=True,
            cli_parts=("validate",),
        ),
        job_process=_FinishedJobProcess(
            returncode=-9,
            termination={
                "schema_version": 1,
                "status": "termination_unconfirmed",
                "strategy": "posix_process_group",
                "confirmed_exit": False,
                "forced": True,
                "private_values_embedded": False,
            },
        ),
        stdout="",
        stderr="",
    )

    completed = manager.get_job(job_id)

    assert completed is not None
    assert completed["status"] == "failed"
    assert completed["exit_code"] == -9
    assert completed["process_termination"]["confirmed_exit"] is False
    assert "job cancellation could not confirm complete process-tree termination." in completed["errors"]


@pytest.mark.skipif(os.name != "posix", reason="process identity check is POSIX-specific")
def test_command_job_manager_preserves_unattached_live_owned_process_after_restart(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    root_script = _write_process_tree_scripts(tmp_path, ignore_sigterm=False)
    tree_dir = tmp_path / "process-tree-restart"
    _patch_job_command(monkeypatch, root_script=root_script, tree_dir=tree_dir)
    manager = CommandJobManager(config, config_path=config_path)

    job = manager.create_job({"intent": "validate", "params": {}})
    running = _wait_for_status(manager, job["job_id"], "running")
    restarted_manager = CommandJobManager(config, config_path=config_path)
    restarted_view = restarted_manager.get_job(job["job_id"])
    manager.cancel_job(job["job_id"])
    completed = _wait_for_terminal(manager, job["job_id"])

    assert running["process_identity"]["strategy"] == "posix_process_group"
    assert restarted_view is not None
    assert restarted_view["status"] == "running"
    assert restarted_view["runtime_attached"] is False
    assert restarted_view["process_alive"] is True
    assert completed["status"] == "cancelled"


def test_command_job_manager_marks_stale_running_job_failed_on_restart(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    job_id = "20260622T000000Z_deadbeef"
    _seed_state_job(config_path, job_id=job_id, status="running", pid=99999999)
    manager = CommandJobManager(config, config_path=config_path)

    detail = manager.get_job(job_id)
    listed = manager.list_jobs()["jobs"][0]

    assert detail is not None
    assert detail["status"] == "failed"
    assert "recorded PID was not treated as proof" in detail["errors"][0]
    assert listed["status"] == "failed"
    assert not (tmp_path / ".halpha" / "dashboard" / "jobs" / "index.json").exists()


def test_command_job_manager_rejects_unattached_live_pid_as_process_identity(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    job_id = "20260622T000001Z_deadbeef"
    _seed_state_job(config_path, job_id=job_id, status="running", pid=os.getpid())
    manager = CommandJobManager(config, config_path=config_path)

    detail = manager.get_job(job_id)

    assert detail is not None
    assert detail["status"] == "failed"
    assert detail["pid"] == os.getpid()
    assert "recorded PID was not treated as proof" in detail["errors"][0]


def test_command_job_repository_rejects_terminal_transition_transactionally(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    job_id = "20260622T000002Z_deadbeef"
    _seed_state_job(config_path, job_id=job_id, status="succeeded")
    repository = CommandJobRepository(config_path=config_path)
    job = repository.get_job(job_id)
    assert job is not None
    job["status"] = "running"
    job["updated_at"] = "2026-06-22T00:05:00Z"

    with pytest.raises(CommandJobStoreError, match="terminal status succeeded"):
        repository.save_job(job, event_type="invalid")

    persisted = repository.get_job(job_id)
    events = repository.job_events(job_id)
    assert persisted is not None
    assert persisted["status"] == "succeeded"
    assert [event["event_type"] for event in events] == ["seed"]


def test_command_job_repository_reads_missing_store_as_empty_without_creating_database(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    repository = CommandJobRepository(config_path=config_path)
    job_id = "20260622T000003Z_deadbeef"

    assert repository.get_job(job_id) is None
    assert repository.list_jobs(limit=10) == []
    assert repository.list_transient_jobs() == []
    assert repository.job_events(job_id) == []
    assert not runtime_state_path(config_path=config_path).exists()


def test_command_job_repository_reads_valid_empty_store_without_error(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    repository = CommandJobRepository(config_path=config_path)

    with closing(open_runtime_state_connection(config_path=config_path)) as connection:
        apply_command_job_migrations(connection, now="2026-06-22T00:00:00Z")

    assert repository.list_jobs(limit=10) == []
    assert repository.list_transient_jobs() == []


def test_command_job_repository_read_does_not_apply_migrations(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    state_path = runtime_state_path(config_path=config_path)
    state_path.parent.mkdir(parents=True)
    sqlite3.connect(state_path).close()
    repository = CommandJobRepository(config_path=config_path)

    with pytest.raises(CommandJobStoreError, match="could not be read") as exc_info:
        repository.list_jobs(limit=10)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic["status"] == "failed"
    assert diagnostic["operation"] == "list command jobs"
    assert diagnostic["database_ref"] == ".halpha/state.sqlite"
    with closing(sqlite3.connect(state_path)) as connection:
        tables = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    assert tables == []


def test_command_job_repository_surfaces_locked_read_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    _seed_state_job(config_path, job_id="20260622T000004Z_deadbeef", status="running")
    repository = CommandJobRepository(config_path=config_path)

    def fail_readonly_connection(**kwargs):  # noqa: ANN003
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(
        "halpha.runtime.command_job_store.open_runtime_state_readonly_connection",
        fail_readonly_connection,
    )

    with pytest.raises(CommandJobStoreError, match="could not be read") as exc_info:
        repository.list_transient_jobs()

    assert exc_info.value.diagnostic == {
        "status": "failed",
        "operation": "list transient command jobs",
        "error_type": "OperationalError",
        "message": "runtime state database is locked; retry after the current writer finishes.",
        "database_ref": ".halpha/state.sqlite",
        "private_values_embedded": False,
    }


def test_command_job_repository_surfaces_corrupt_database_without_private_paths(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    state_path = runtime_state_path(config_path=config_path)
    state_path.parent.mkdir(parents=True)
    state_path.write_text("not a sqlite database", encoding="utf-8")
    repository = CommandJobRepository(config_path=config_path)

    with pytest.raises(CommandJobStoreError, match="could not be read") as exc_info:
        repository.get_job("20260622T000005Z_deadbeef")

    diagnostic_text = repr(exc_info.value.diagnostic)
    assert exc_info.value.diagnostic["status"] == "failed"
    assert exc_info.value.diagnostic["operation"] == "read command job detail"
    assert exc_info.value.diagnostic["database_ref"] == ".halpha/state.sqlite"
    assert str(tmp_path) not in diagnostic_text


def test_command_job_api_lists_and_reads_jobs(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def fail_popen(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("dashboard API jobs must use internal execution")

    monkeypatch.setattr(
        "halpha.runtime.command_jobs.subprocess.Popen",
        fail_popen,
    )
    monkeypatch.setattr(
        "halpha.runtime.command_jobs.execute_command_job",
        lambda *args, **kwargs: CommandJobExecutionResult(exit_code=0, stdout="ok"),
    )
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    create_response = client.post("/api/jobs", json={"intent": "validate", "params": {}})
    job_id = create_response.json()["job_id"]
    _wait_for_api_terminal(client, job_id)
    list_response = client.get("/api/jobs")
    detail_response = client.get(f"/api/jobs/{job_id}")

    assert list_response.status_code == 200
    assert detail_response.status_code == 200
    assert list_response.json()["artifact_type"] == "command_job_list"
    assert list_response.json()["jobs"][0]["job_id"] == job_id
    assert detail_response.json()["status"] == "succeeded"
    assert str(tmp_path) not in list_response.text
    assert str(tmp_path) not in detail_response.text


def test_command_job_api_surfaces_state_store_read_failure_without_private_paths(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    state_path = runtime_state_path(config_path=config_path)
    state_path.parent.mkdir(parents=True)
    state_path.write_text("not a sqlite database", encoding="utf-8")
    client = TestClient(create_dashboard_app(config, config_path=config_path))
    job_id = "20260622T000006Z_deadbeef"

    list_response = client.get("/api/jobs")
    detail_response = client.get(f"/api/jobs/{job_id}")
    cancel_response = client.post(f"/api/jobs/{job_id}/cancel")

    assert list_response.status_code == 200
    assert detail_response.status_code == 200
    assert cancel_response.status_code == 200
    assert list_response.json()["status"] == "failed"
    assert list_response.json()["jobs"] == []
    assert detail_response.json()["status"] == "failed"
    assert detail_response.json()["store_read_failed"] is True
    assert cancel_response.json()["status"] == "failed"
    assert cancel_response.json()["store_read_failed"] is True
    assert "command job state store could not be read." in list_response.json()["errors"]
    assert "command job was not found" not in cancel_response.text
    assert str(tmp_path) not in list_response.text
    assert str(tmp_path) not in detail_response.text
    assert str(tmp_path) not in cancel_response.text


def test_command_job_manager_reports_transient_reconciliation_read_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def fail_transient_jobs(self):  # noqa: ANN001
        raise CommandJobStoreError(
            "command job state store could not be read.",
            diagnostic={
                "status": "failed",
                "operation": "list transient command jobs",
                "error_type": "OperationalError",
                "message": "runtime state database is locked; retry after the current writer finishes.",
                "database_ref": ".halpha/state.sqlite",
                "private_values_embedded": False,
            },
        )

    monkeypatch.setattr(CommandJobRepository, "list_transient_jobs", fail_transient_jobs)

    manager = CommandJobManager(config, config_path=config_path)
    payload = manager.list_jobs()

    assert payload["status"] == "degraded"
    assert "transient command-job reconciliation could not read runtime state." in payload["warnings"]
    assert "command job state store could not be read during startup reconciliation." in payload["errors"]
    assert payload["diagnostic"]["database_ref"] == ".halpha/state.sqlite"


def test_command_job_api_rejects_path_shaped_job_ids(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    outside = tmp_path / ".halpha" / "dashboard" / "outside_jobs"
    outside.mkdir(parents=True)
    (outside / "job.json").write_text(
        json.dumps({"schema_version": 1, "artifact_type": "command_job", "job_id": "outside", "status": "leaked"}),
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


class _FinishedJobProcess:
    def __init__(self, *, returncode: int, termination: dict[str, Any]) -> None:
        self.returncode = returncode
        self.termination = termination
        self.identity = {
            "schema_version": 1,
            "platform": "posix",
            "strategy": "posix_process_group",
            "pid": 12345,
            "pgid": 12345,
            "verified": True,
            "private_values_embedded": False,
        }


def _wait_for_terminal(manager: CommandJobManager, job_id: str) -> dict:
    for _ in range(100):
        job = manager.get_job(job_id)
        if job and job["status"] in {"succeeded", "failed", "cancelled", "unsupported", "blocked"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"job did not finish: {job_id}")


def _wait_for_status(manager: CommandJobManager, job_id: str, status: str) -> dict:
    for _ in range(100):
        job = manager.get_job(job_id)
        if job and job["status"] == status:
            return job
        time.sleep(0.05)
    raise AssertionError(f"job did not reach {status}: {job_id}")


def _wait_for_api_terminal(client: TestClient, job_id: str) -> dict:
    for _ in range(100):
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


def _patch_job_command(monkeypatch, *, root_script: Path, tree_dir: Path) -> None:
    spec = CommandSpec(
        intent="validate",
        kind="product_validation",
        cancellable=True,
        cli_parts=("validate",),
    )
    command = [sys.executable, str(root_script), str(tree_dir)]
    payload = CommandJobCommand(spec=spec, command=command, preview=["python", "process-tree-root.py"])
    monkeypatch.setattr(CommandJobBuilder, "build", lambda self, intent, params: payload)


def _write_process_tree_scripts(tmp_path: Path, *, ignore_sigterm: bool) -> Path:
    script_dir = tmp_path / "process_tree_scripts"
    script_dir.mkdir()
    signal_setup = "signal.signal(signal.SIGTERM, signal.SIG_IGN)" if ignore_sigterm else (
        "signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))"
    )
    (script_dir / "grandchild.py").write_text(
        f"""
from pathlib import Path
import os
import signal
import sys
import time

{signal_setup}
tree_dir = Path(sys.argv[1])
tree_dir.mkdir(parents=True, exist_ok=True)
(tree_dir / "grandchild.pid").write_text(str(os.getpid()), encoding="utf-8")
while True:
    time.sleep(1)
""".strip(),
        encoding="utf-8",
    )
    (script_dir / "child.py").write_text(
        f"""
from pathlib import Path
import os
import signal
import subprocess
import sys
import time

{signal_setup}
tree_dir = Path(sys.argv[1])
tree_dir.mkdir(parents=True, exist_ok=True)
(tree_dir / "child.pid").write_text(str(os.getpid()), encoding="utf-8")
subprocess.Popen([sys.executable, str(Path(__file__).with_name("grandchild.py")), str(tree_dir)])
while True:
    time.sleep(1)
""".strip(),
        encoding="utf-8",
    )
    root_script = script_dir / "root.py"
    root_script.write_text(
        f"""
from pathlib import Path
import os
import signal
import subprocess
import sys
import time

{signal_setup}
tree_dir = Path(sys.argv[1])
tree_dir.mkdir(parents=True, exist_ok=True)
(tree_dir / "root.pid").write_text(str(os.getpid()), encoding="utf-8")
subprocess.Popen([sys.executable, str(Path(__file__).with_name("child.py")), str(tree_dir)])
while True:
    time.sleep(1)
""".strip(),
        encoding="utf-8",
    )
    return root_script


def _wait_for_pid_file(path: Path) -> int:
    for _ in range(100):
        if path.exists():
            return int(path.read_text(encoding="utf-8"))
        time.sleep(0.05)
    raise AssertionError(f"pid file was not written: {path.name}")


def _wait_for_pid_exit(pid: int) -> bool:
    for _ in range(100):
        if not _pid_alive(pid):
            return True
        time.sleep(0.05)
    return False


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _seed_state_job(config_path: Path, *, job_id: str, status: str, pid: int | None = None) -> None:
    repository = CommandJobRepository(config_path=config_path)
    repository.save_job(
        {
            "schema_version": 1,
            "artifact_type": "command_job",
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
            "job_dir": f".halpha/command_jobs/job_logs/{job_id}",
            "logs": {
                "stdout_ref": f".halpha/command_jobs/job_logs/{job_id}/stdout.log",
                "stderr_ref": f".halpha/command_jobs/job_logs/{job_id}/stderr.log",
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
