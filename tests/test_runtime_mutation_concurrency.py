from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

from halpha.cli import main
from halpha.runtime.mutation_lease import acquire_mutation_lease


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_direct_run_cli_exits_nonzero_without_run_dir_when_runtime_lease_is_busy(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    lease = acquire_mutation_lease(
        config_path=config_path,
        owner_kind="test",
        workflow="product_run",
        requested_by="CLI",
        owner_id="external-owner",
        owner_pid=os.getpid(),
    )

    try:
        result = subprocess.run(
            [sys.executable, "-m", "halpha", "run", "--config", str(config_path), "--no-codex"],
            cwd=tmp_path,
            env=_subprocess_env(),
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
    finally:
        lease.release()

    output = result.stdout + result.stderr
    assert result.returncode == 4
    assert "Halpha run failed." in result.stdout
    assert "stage: runtime_mutation_lease" in result.stdout
    assert "another mutating Halpha workflow" in result.stdout
    assert not (tmp_path / "runs").exists()
    assert str(tmp_path) not in output


def test_read_only_monitor_inspect_remains_available_while_runtime_lease_is_busy(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = _write_config(tmp_path)
    lease = acquire_mutation_lease(
        config_path=config_path,
        owner_kind="test",
        workflow="product_run",
        requested_by="CLI",
        owner_id="external-owner",
        owner_pid=os.getpid(),
    )

    try:
        exit_code = main(["monitor", "inspect", "--config", str(config_path)])
    finally:
        lease.release()

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Halpha monitor inspection succeeded." in output
    assert "runtime_mutation_lease" not in output


def test_monitor_run_cli_exits_nonzero_without_cycle_manifest_when_runtime_lease_is_busy(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = _write_config(
        tmp_path,
        monitor_block="""
monitor:
  enabled: true
  output_dir: monitor
  target_stage: refresh_data
  no_codex: true
""".strip(),
    )
    lease = acquire_mutation_lease(
        config_path=config_path,
        owner_kind="test",
        workflow="product_run",
        requested_by="CLI",
        owner_id="external-owner",
        owner_pid=os.getpid(),
    )

    try:
        exit_code = main(["monitor", "run", "--config", str(config_path), "--once"])
    finally:
        lease.release()

    output = capsys.readouterr().out
    assert exit_code == 4
    assert "Halpha monitor run failed." in output
    assert "stage: runtime_mutation_lease" in output
    assert "another mutating Halpha workflow" in output
    assert not (tmp_path / "monitor").exists()
    assert not (tmp_path / "runs").exists()
    assert str(tmp_path) not in output


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    src_path = str(Path(__file__).resolve().parents[1] / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src_path if not existing else f"{src_path}{os.pathsep}{existing}"
    return env


def _write_config(tmp_path: Path, monitor_block: str | None = None) -> Path:
    monitor_section = f"\n{monitor_block}" if monitor_block else ""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
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
  enabled: false{monitor_section}
""".strip(),
        encoding="utf-8",
    )
    return config_path
