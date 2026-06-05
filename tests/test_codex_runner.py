from __future__ import annotations

import json
import subprocess
from pathlib import Path

from halpha.config import load_config
from halpha.pipeline import run_pipeline


REPORT_STDOUT = "# 每日市场简报\n\n## 风险提示\n本内容仅供个人研究，不构成投资建议。\n"


def test_codex_runner_writes_report_from_stdout(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    calls: list[dict] = []

    def fake_run(command, input, text, encoding, errors, capture_output, timeout, cwd):
        calls.append(
            {
                "command": command,
                "input": input,
                "text": text,
                "encoding": encoding,
                "errors": errors,
                "capture_output": capture_output,
                "timeout": timeout,
                "cwd": cwd,
            }
        )
        return subprocess.CompletedProcess(command, 0, stdout=REPORT_STDOUT, stderr="")

    monkeypatch.setattr("halpha.codex.runner.subprocess.run", fake_run)

    result = run_pipeline(config, config_path=config_path)

    assert result.succeeded is True
    assert result.exit_code == 0
    assert result.failed_stage is None
    assert calls[0]["command"] == ["fake-codex", "exec", "-"]
    assert calls[0]["text"] is True
    assert calls[0]["encoding"] == "utf-8"
    assert calls[0]["errors"] == "replace"
    assert calls[0]["capture_output"] is True
    assert calls[0]["timeout"] == 9
    assert calls[0]["cwd"] == result.run.run_dir
    assert "Generate a Simplified Chinese Markdown market intelligence report" in calls[0]["input"]
    assert "Use Chinese section headings only." in calls[0]["input"]
    assert "- 核心摘要" in calls[0]["input"]
    assert "Do not invent prices, events, links, sources, or certainty." in calls[0]["input"]

    report = result.run.report_dir / "report.md"
    assert report.read_text(encoding="utf-8") == REPORT_STDOUT
    assert REPORT_STDOUT.startswith("# ")
    assert "风险提示" in REPORT_STDOUT

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "succeeded"
    assert manifest["artifacts"]["report"] == "report/report.md"
    assert manifest["codex"]["status"] == "succeeded"
    assert manifest["codex"]["exit_code"] == 0
    assert "stderr_summary" not in manifest["codex"]
    assert manifest["stages"][5]["name"] == "run_codex_report"
    assert manifest["stages"][5]["status"] == "succeeded"
    assert manifest["stages"][5]["artifacts"] == ["report/report.md"]
    assert manifest["errors"] == []


def test_codex_runner_resolves_configured_command_before_subprocess(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    commands: list[list[str]] = []

    def fake_which(command):
        assert command == "fake-codex"
        return "fake-codex.cmd"

    def fake_run(command, input, text, encoding, errors, capture_output, timeout, cwd):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=REPORT_STDOUT, stderr="")

    monkeypatch.setattr("halpha.codex.runner.shutil.which", fake_which)
    monkeypatch.setattr("halpha.codex.runner.subprocess.run", fake_run)

    result = run_pipeline(config, config_path=config_path)

    assert result.succeeded is True
    assert commands == [["fake-codex.cmd", "exec", "-"]]


def test_codex_runner_records_failure_exit_code_and_stderr_summary(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def fake_run(command, input, text, encoding, errors, capture_output, timeout, cwd):
        return subprocess.CompletedProcess(
            command,
            17,
            stdout="partial report",
            stderr="fatal Codex error\ntoken=secret-token\n",
        )

    monkeypatch.setattr("halpha.codex.runner.subprocess.run", fake_run)

    result = run_pipeline(config, config_path=config_path)

    assert result.succeeded is False
    assert result.exit_code == 17
    assert result.failed_stage == "run_codex_report"
    assert result.reason == "Codex command failed with exit code 17."
    assert "fatal Codex error" not in result.reason
    assert not (result.run.report_dir / "report.md").exists()

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    failed_stage = manifest["stages"][5]
    assert manifest["codex"]["status"] == "failed"
    assert manifest["codex"]["exit_code"] == 17
    assert manifest["codex"]["stderr_summary"] == "fatal Codex error\ntoken=[REDACTED]"
    assert failed_stage["error"] == {
        "stage": "run_codex_report",
        "message": "Codex command failed with exit code 17.",
        "exit_code": 17,
        "stderr_summary": "fatal Codex error\ntoken=[REDACTED]",
    }
    assert manifest["errors"] == [failed_stage["error"]]


def test_codex_runner_rejects_report_without_risk_notice(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def fake_run(command, input, text, encoding, errors, capture_output, timeout, cwd):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="# Market Brief\n\nNo risk section.\n",
            stderr="",
        )

    monkeypatch.setattr("halpha.codex.runner.subprocess.run", fake_run)

    result = run_pipeline(config, config_path=config_path)

    assert result.succeeded is False
    assert result.exit_code == 1
    assert result.failed_stage == "run_codex_report"
    assert result.reason == "Codex stdout did not include a risk notice; report/report.md was not written."
    assert not (result.run.report_dir / "report.md").exists()

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    failed_stage = manifest["stages"][5]
    assert manifest["codex"]["status"] == "failed"
    assert manifest["codex"]["exit_code"] == 0
    assert failed_stage["error"] == {
        "stage": "run_codex_report",
        "message": "Codex stdout did not include a risk notice; report/report.md was not written.",
        "exit_code": 0,
    }


def test_codex_runner_records_timeout_without_cli_exit_code(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def fake_run(command, input, text, encoding, errors, capture_output, timeout, cwd):
        raise subprocess.TimeoutExpired(command, timeout, output="partial", stderr="sk-timeoutsecret")

    monkeypatch.setattr("halpha.codex.runner.subprocess.run", fake_run)

    result = run_pipeline(config, config_path=config_path)

    assert result.succeeded is False
    assert result.exit_code == 124
    assert result.failed_stage == "run_codex_report"
    assert result.reason == "Codex command timed out after 9 seconds."
    assert not (result.run.report_dir / "report.md").exists()

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    failed_stage = manifest["stages"][5]
    assert manifest["codex"]["status"] == "failed"
    assert manifest["codex"]["exit_code"] is None
    assert manifest["codex"]["stderr_summary"] == "sk-[REDACTED]"
    assert failed_stage["error"] == {
        "stage": "run_codex_report",
        "message": "Codex command timed out after 9 seconds.",
        "stderr_summary": "sk-[REDACTED]",
    }
    assert "exit_code" not in failed_stage["error"]


def test_codex_runner_fails_when_prompt_artifact_is_missing(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={"build_codex_context": _skip_codex_context},
    )

    assert result.succeeded is False
    assert result.exit_code == 3
    assert result.failed_stage == "run_codex_report"
    assert result.reason == "codex_context/prompt.md was not found; build_codex_context must run first."
    assert not (result.run.report_dir / "report.md").exists()


def test_codex_runner_skips_when_codex_is_disabled(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, codex_enabled=False)
    config = load_config(config_path)

    result = run_pipeline(config, config_path=config_path)

    assert result.succeeded is True
    assert result.failed_stage is None
    assert not (result.run.report_dir / "report.md").exists()

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["codex"] == {
        "enabled": False,
        "command": None,
        "status": "disabled",
        "exit_code": None,
    }
    assert manifest["stages"][5]["name"] == "run_codex_report"
    assert manifest["stages"][5]["status"] == "succeeded"
    assert manifest["stages"][5]["artifacts"] == []


def _write_config(tmp_path: Path, *, codex_enabled: bool = True) -> Path:
    config_path = tmp_path / "config.yaml"
    codex_block = (
        """
codex:
  enabled: true
  command: fake-codex
  args:
    - exec
    - "-"
  timeout_seconds: 9
"""
        if codex_enabled
        else """
codex:
  enabled: false
"""
    )
    config_path.write_text(
        f"""
run:
  output_dir: runs
  timezone: Asia/Shanghai
market:
  enabled: false
text:
  enabled: false
report:
  title: Daily Market Brief
  language: zh-CN
{codex_block.rstrip()}
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _skip_codex_context(config, run) -> list[str]:
    return []
