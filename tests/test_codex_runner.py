from __future__ import annotations

import json
import subprocess
from pathlib import Path

from halpha.config import load_config
from halpha.pipeline import run_pipeline
from halpha.storage import write_json


REPORT_STDOUT = "# 每日市场简报\n\n## 风险提示\n- 数据窗口较短，结论需要结合后续公开事件验证。\n"


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
    assert "The first line must be a single H1 title" in calls[0]["input"]
    assert "Do not create a separate title section." in calls[0]["input"]
    assert "Use Markdown tables for market data" in calls[0]["input"]
    assert "do not recreate the full strategy run table" in calls[0]["input"]
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
    stage = _stage(manifest, "run_codex_report")
    assert stage["status"] == "succeeded"
    assert stage["artifacts"] == ["report/report.md"]
    assert manifest["errors"] == []


def test_codex_runner_injects_quant_strategy_markdown_table_after_codex_stdout(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    report_stdout = "\n".join(
        [
            "# \u6bcf\u65e5\u5e02\u573a\u7b80\u62a5",
            "",
            "## \u5e02\u573a\u6982\u89c8",
            "",
            "Codex generated market overview.",
            "",
            "## \u7efc\u5408\u5224\u65ad",
            "",
            "Codex generated synthesis.",
            "",
            "## \u98ce\u9669\u63d0\u793a",
            "",
            "\u6570\u636e\u7a97\u53e3\u8f83\u77ed\uff0c\u9700\u8981\u7ee7\u7eed\u89c2\u5bdf\u516c\u5f00\u4e8b\u4ef6\u548c\u4ef7\u683c\u53d8\u5316\u3002",
            "",
        ]
    )

    def fake_run(command, input, text, encoding, errors, capture_output, timeout, cwd):
        return subprocess.CompletedProcess(command, 0, stdout=report_stdout, stderr="")

    monkeypatch.setattr("halpha.codex.runner.subprocess.run", fake_run)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={"build_codex_context": _write_prompt_and_quant_strategy_runs},
    )

    assert result.succeeded is True
    report = (result.run.report_dir / "report.md").read_text(encoding="utf-8")
    table_heading = "## \u91cf\u5316\u7b56\u7565\u8f93\u51fa\u8868"
    synthesis_heading = "## \u7efc\u5408\u5224\u65ad"
    assert table_heading in report
    assert report.index(table_heading) < report.index(synthesis_heading)
    assert (
        "| \u7b56\u7565 | \u6765\u6e90 | \u6807\u7684 | \u5468\u671f | "
        "\u8f93\u5165\u7a97\u53e3 | \u72b6\u6001 | \u65b9\u5411 | \u5f3a\u5ea6 | "
        "\u7f6e\u4fe1\u5ea6 | \u7ed3\u8bba |"
    ) in report
    assert (
        "| tsmom_vol_scaled | binance | BTCUSDT | 1d | "
        "2026-06-01T00:00:00Z to 2026-06-05T00:00:00Z | "
        "\u6210\u529f | bullish | medium | high | Positive time-series momentum is present. |"
    ) in report
    assert (
        "| breakout_atr_trend | binance | BTCUSDT | 1h | "
        "2026-06-05T00:00:00Z to 2026-06-05T04:00:00Z | "
        "\u6570\u636e\u4e0d\u8db3 | unknown | unknown | low | Strategy result is unavailable because input data is insufficient. |"
    ) in report


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
    failed_stage = _stage(manifest, "run_codex_report")
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


def test_codex_runner_rejects_report_without_risk_section(tmp_path: Path, monkeypatch) -> None:
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
    assert result.reason == "Codex stdout did not include a risk section; report/report.md was not written."
    assert not (result.run.report_dir / "report.md").exists()

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    failed_stage = _stage(manifest, "run_codex_report")
    assert manifest["codex"]["status"] == "failed"
    assert manifest["codex"]["exit_code"] == 0
    assert failed_stage["error"] == {
        "stage": "run_codex_report",
        "message": "Codex stdout did not include a risk section; report/report.md was not written.",
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
    failed_stage = _stage(manifest, "run_codex_report")
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
    stage = _stage(manifest, "run_codex_report")
    assert stage["status"] == "succeeded"
    assert stage["artifacts"] == []


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


def _write_prompt_and_quant_strategy_runs(config, run) -> list[str]:
    run.codex_context_dir.joinpath("prompt.md").write_text("prompt", encoding="utf-8")
    write_json(
        run.analysis_dir / "quant_strategy_runs.json",
        {
            "schema_version": 1,
            "artifact_type": "quant_strategy_runs",
            "created_at": "2026-06-05T00:00:00Z",
            "engine": {"name": "vectorbt", "version": "1.0.0", "objects_exposed": False},
            "source_artifacts": ["raw/market_data_views.json"],
            "runs": [
                {
                    "strategy_name": "tsmom_vol_scaled",
                    "status": "succeeded",
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "input_window_start": "2026-06-01T00:00:00Z",
                    "input_window_end": "2026-06-05T00:00:00Z",
                    "assessment": {
                        "direction": "bullish",
                        "strength": "medium",
                        "confidence": "high",
                        "summary": "Positive time-series momentum is present.",
                    },
                },
                {
                    "strategy_name": "breakout_atr_trend",
                    "status": "insufficient_data",
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1h",
                    "input_window_start": "2026-06-05T00:00:00Z",
                    "input_window_end": "2026-06-05T04:00:00Z",
                    "data_quality": {"row_count": 5, "minimum_required_rows": 11},
                    "assessment": {
                        "direction": "unknown",
                        "strength": "unknown",
                        "confidence": "low",
                        "summary": "Strategy result is unavailable because input data is insufficient.",
                    },
                },
            ],
        },
    )
    run.manifest["artifacts"]["codex_prompt"] = "codex_context/prompt.md"
    run.manifest["artifacts"]["quant_strategy_runs"] = "analysis/quant_strategy_runs.json"
    return ["codex_context/prompt.md"]


def _stage(manifest: dict, name: str) -> dict:
    return next(stage for stage in manifest["stages"] if stage["name"] == name)
