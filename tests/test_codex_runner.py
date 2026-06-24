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
    gate_heading = "## \u7b56\u7565\u6709\u6548\u6027\u95e8\u69db\u8868"
    synthesis_heading = "## \u7efc\u5408\u5224\u65ad"
    assert table_heading in report
    assert gate_heading in report
    assert report.index(table_heading) < report.index(synthesis_heading)
    assert report.index(gate_heading) < report.index(synthesis_heading)
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
    assert (
        "| \u7b56\u7565 | \u72b6\u6001 | \u57fa\u51c6\u8986\u76d6 | \u51c0\u6536\u76ca | "
        "\u76f8\u5bf9\u57fa\u51c6 | \u6210\u672c\u62d6\u7d2f | \u6837\u672c | "
        "Walk-forward | \u8fc7\u62df\u5408\u98ce\u9669 | \u5173\u952e\u539f\u56e0 |"
    ) in report
    assert (
        "| tsmom_vol_scaled | \u6709\u6548 | 4/4 (100%) | 6.5%; positive 75% | "
        "20%; positive 100% | 0.4% | rows 500-720 | stable; windows 12; positive 66.6667% | "
        "low | parameter_stability_unavailable |"
    ) in report


def test_codex_runner_injects_derivatives_market_section_after_codex_stdout(
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
        stage_handlers={"build_codex_context": _write_prompt_and_derivatives_material},
    )

    assert result.succeeded is True
    report = (result.run.report_dir / "report.md").read_text(encoding="utf-8")
    derivatives_heading = "## \u884d\u751f\u54c1\u4e0e\u5e02\u573a\u7ed3\u6784\u8bc1\u636e"
    synthesis_heading = "## \u7efc\u5408\u5224\u65ad"
    assert derivatives_heading in report
    assert report.index(derivatives_heading) < report.index(synthesis_heading)
    assert "analysis/derivatives_market_material.md" in report
    assert "\u8d44\u91d1\u8d39\u7387\u538b\u529b" in report
    assert "extreme_positive_funding" in report
    assert "\u5f3a\u5e73\u6765\u6e90\u53ef\u7528\u6027" in report
    assert "unavailable/unavailable" in report
    assert "degraded/stale" in report
    assert "succeeded/neutral" in report
    assert "no-impact" in report
    assert "\u4e0d\u4ee3\u8868\u4f4e\u98ce\u9669" in report
    assert "\u4ea4\u6613\u6307\u4ee4" in report
    assert "\u4ed3\u4f4d\u5efa\u8bae" in report
    assert "\u4ef7\u683c\u9884\u6d4b" in report


def test_codex_runner_injects_onchain_flow_section_after_codex_stdout(
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
        stage_handlers={"build_codex_context": _write_prompt_and_onchain_flow_material},
    )

    assert result.succeeded is True
    report = (result.run.report_dir / "report.md").read_text(encoding="utf-8")
    onchain_heading = "## \u94fe\u4e0a\u6d41\u4e0e\u6765\u6e90\u53ef\u7528\u6027\u8bc1\u636e"
    synthesis_heading = "## \u7efc\u5408\u5224\u65ad"
    assert onchain_heading in report
    assert report.index(onchain_heading) < report.index(synthesis_heading)
    assert "analysis/onchain_flow_material.md" in report
    assert "\u7a33\u5b9a\u5e01\u6d41\u52a8\u6027" in report
    assert "sharp_stablecoin_supply_contraction" in report
    assert "\u7f51\u7edc\u62e5\u5835" in report
    assert "elevated_network_congestion" in report
    assert "unavailable/source_unavailable" in report
    assert "\u5730\u5740\u6807\u7b7e" in report
    assert "\u4e0d\u4ee3\u8868\u4f4e\u98ce\u9669" in report
    assert "\u4ea4\u6613\u6307\u4ee4" in report
    assert "\u4ef7\u683c\u9884\u6d4b" in report


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
        "diagnostic": {
            "exception_type": "PipelineError",
            "traceback_embedded": False,
            "context": {"pipeline_exit_code": 17},
        },
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
    assert result.reason == "Codex stdout did not include a Markdown risk section heading; report/report.md was not written."
    assert not (result.run.report_dir / "report.md").exists()

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    failed_stage = _stage(manifest, "run_codex_report")
    assert manifest["codex"]["status"] == "failed"
    assert manifest["codex"]["exit_code"] == 0
    assert failed_stage["error"] == {
        "stage": "run_codex_report",
        "message": "Codex stdout did not include a Markdown risk section heading; report/report.md was not written.",
        "exit_code": 0,
        "diagnostic": {
            "exception_type": "PipelineError",
            "traceback_embedded": False,
            "context": {"pipeline_exit_code": 1},
        },
    }


def test_codex_runner_rejects_report_that_only_mentions_risk_without_heading(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def fake_run(command, input, text, encoding, errors, capture_output, timeout, cwd):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="# 每日市场简报\n\n正文提到了风险，但没有风险提示章节标题。\n",
            stderr="",
        )

    monkeypatch.setattr("halpha.codex.runner.subprocess.run", fake_run)

    result = run_pipeline(config, config_path=config_path)

    assert result.succeeded is False
    assert result.exit_code == 1
    assert result.failed_stage == "run_codex_report"
    assert result.reason == "Codex stdout did not include a Markdown risk section heading; report/report.md was not written."
    assert not (result.run.report_dir / "report.md").exists()


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
        "diagnostic": {
            "exception_type": "PipelineError",
            "traceback_embedded": False,
            "context": {"pipeline_exit_code": 124},
        },
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
    write_json(
        run.analysis_dir / "strategy_effectiveness_gates.json",
        {
            "schema_version": 1,
            "artifact_type": "strategy_effectiveness_gates",
            "created_at": "2026-06-05T00:00:00Z",
            "source_artifacts": ["analysis/strategy_experiment.json"],
            "coverage": {
                "strategy_candidates": 1,
                "effective": 1,
                "watchlisted": 0,
                "rejected": 0,
                "insufficient_evidence": 0,
            },
            "records": [
                {
                    "gate_id": "strategy_effectiveness_gate:tsmom_vol_scaled",
                    "strategy_name": "tsmom_vol_scaled",
                    "status": "effective",
                    "params": {"return_window": 120},
                    "gate_inputs": {
                        "benchmark_coverage": {
                            "benchmark_records": 4,
                            "succeeded": 4,
                            "success_rate_pct": 100.0,
                        },
                        "net_performance": {
                            "mean_net_return_pct": 6.5,
                            "positive_net_return_benchmark_pct": 75.0,
                        },
                        "baseline_comparison": {
                            "mean_excess_return_vs_buy_and_hold_pct": 20.0,
                            "positive_excess_return_benchmark_pct": 100.0,
                        },
                        "cost_drag": {"max_cost_drag_pct": 0.4},
                        "sample_quality": {"min_sample_rows": 500, "max_sample_rows": 720},
                        "walk_forward_stability": {
                            "result_stability": "stable",
                            "succeeded_windows": 12,
                            "min_positive_net_return_window_pct": 66.666667,
                        },
                        "overfitting_risk": {"status": "low"},
                    },
                    "reasons": [
                        {
                            "code": "parameter_stability_unavailable",
                            "severity": "info",
                            "value": "unavailable",
                            "threshold": "stable",
                            "message": "Parameter-stability evidence is unavailable.",
                        }
                    ],
                    "warnings": [],
                    "errors": [],
                    "source_artifacts": ["analysis/strategy_experiment.json"],
                }
            ],
            "warnings": [],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["codex_prompt"] = "codex_context/prompt.md"
    run.manifest["artifacts"]["quant_strategy_runs"] = "analysis/quant_strategy_runs.json"
    run.manifest["artifacts"]["strategy_effectiveness_gates"] = (
        "analysis/strategy_effectiveness_gates.json"
    )
    return ["codex_context/prompt.md"]


def _write_prompt_and_derivatives_material(config, run) -> list[str]:
    run.codex_context_dir.joinpath("prompt.md").write_text("prompt", encoding="utf-8")
    write_json(
        run.analysis_dir / "derivatives_market_context.json",
        {
            "schema_version": 1,
            "artifact_type": "derivatives_market_context",
            "run_id": run.run_id,
            "created_at": "2026-06-18T01:00:00Z",
            "status": "warning",
            "records": [
                {
                    "context_id": (
                        "derivatives_context:funding_pressure:binance_usdm:"
                        "BTCUSDT:8h:2026-06-18T00:00:00Z"
                    ),
                    "context_type": "funding_pressure",
                    "data_class": "funding_rate",
                    "source": "binance_usdm",
                    "market_type": "usd_m_futures",
                    "symbol": "BTCUSDT",
                    "period": "8h",
                    "as_of": "2026-06-18T00:00:00Z",
                    "status": "succeeded",
                    "state": "extreme_positive_funding",
                    "severity": "high",
                    "confidence": "medium",
                    "metrics": {"latest_funding_rate": 0.0007},
                    "thresholds": {"extreme_positive_funding_rate": 0.0005},
                    "evidence": [],
                    "uncertainty": [],
                    "warnings": [],
                    "errors": [],
                    "source_artifacts": [
                        "analysis/derivatives_market_context.json",
                        "raw/derivatives_market_views.json",
                    ],
                },
                {
                    "context_id": (
                        "derivatives_context:liquidation_availability:binance_usdm:"
                        "BTCUSDT:summary:2026-06-18T00:00:00Z"
                    ),
                    "context_type": "liquidation_availability",
                    "data_class": "liquidation_summary",
                    "source": "binance_usdm",
                    "market_type": "usd_m_futures",
                    "symbol": "BTCUSDT",
                    "period": "summary",
                    "as_of": "2026-06-18T00:00:00Z",
                    "status": "unavailable",
                    "state": "unavailable",
                    "severity": "unknown",
                    "confidence": "low",
                    "metrics": {},
                    "thresholds": {},
                    "evidence": [],
                    "uncertainty": ["periodic public liquidation summary is unavailable."],
                    "warnings": ["liquidation source is unavailable."],
                    "errors": [],
                    "source_artifacts": [
                        "analysis/derivatives_market_context.json",
                        "raw/derivatives_market.json",
                    ],
                },
                {
                    "context_id": (
                        "derivatives_context:premium_basis_state:binance_usdm:"
                        "BTCUSDT:snapshot:2026-06-18T00:00:00Z"
                    ),
                    "context_type": "premium_basis_state",
                    "data_class": "premium_index",
                    "source": "binance_usdm",
                    "market_type": "usd_m_futures",
                    "symbol": "BTCUSDT",
                    "period": "snapshot",
                    "as_of": "2026-06-18T00:00:00Z",
                    "status": "degraded",
                    "state": "stale",
                    "severity": "medium",
                    "confidence": "low",
                    "metrics": {"latest_premium_rate": 0.001},
                    "thresholds": {"stretched_abs_premium_rate": 0.001},
                    "evidence": [],
                    "uncertainty": ["latest derivatives observation is stale."],
                    "warnings": ["premium source is stale."],
                    "errors": [],
                    "source_artifacts": [
                        "analysis/derivatives_market_context.json",
                        "raw/derivatives_market_views.json",
                    ],
                },
                {
                    "context_id": (
                        "derivatives_context:liquidity_depth_state:binance_usdm:"
                        "BTCUSDT:snapshot:2026-06-18T00:00:00Z"
                    ),
                    "context_type": "liquidity_depth_state",
                    "data_class": "spread_depth",
                    "source": "binance_usdm",
                    "market_type": "usd_m_futures",
                    "symbol": "BTCUSDT",
                    "period": "snapshot",
                    "as_of": "2026-06-18T00:00:00Z",
                    "status": "succeeded",
                    "state": "neutral",
                    "severity": "low",
                    "confidence": "medium",
                    "metrics": {"latest_spread_bps": 2.0},
                    "thresholds": {"wide_spread_bps": 10.0},
                    "evidence": [],
                    "uncertainty": [],
                    "warnings": [],
                    "errors": [],
                    "source_artifacts": [
                        "analysis/derivatives_market_context.json",
                        "raw/derivatives_market_views.json",
                    ],
                },
            ],
            "counts": {"records": 4},
            "warnings": ["liquidation source is unavailable."],
            "errors": [],
            "source_artifacts": [
                "raw/derivatives_market_views.json",
                "raw/derivatives_market.json",
            ],
        },
    )
    run.analysis_dir.joinpath("derivatives_market_material.md").write_text(
        "\n".join(
            [
                "---",
                "artifact_type: analysis_derivatives_market_material",
                "schema_version: 1",
                "audience: ai",
                "source_artifacts:",
                "  - analysis/derivatives_market_context.json",
                "---",
                "",
                "# derivatives_market_material",
                "",
                "codex_may_generate_derivatives_states: false",
                "full_derivatives_context_json_embedded: false",
                "",
            ]
        ),
        encoding="utf-8",
    )
    run.manifest["artifacts"]["codex_prompt"] = "codex_context/prompt.md"
    run.manifest["artifacts"]["derivatives_market_context"] = (
        "analysis/derivatives_market_context.json"
    )
    run.manifest["artifacts"]["derivatives_market_material"] = (
        "analysis/derivatives_market_material.md"
    )
    return ["codex_context/prompt.md"]


def _write_prompt_and_onchain_flow_material(config, run) -> list[str]:
    run.codex_context_dir.joinpath("prompt.md").write_text("prompt", encoding="utf-8")
    write_json(
        run.analysis_dir / "onchain_flow_context.json",
        {
            "schema_version": 1,
            "artifact_type": "onchain_flow_context",
            "run_id": run.run_id,
            "created_at": "2026-06-18T01:00:00Z",
            "status": "warning",
            "records": [
                {
                    "context_id": (
                        "onchain_flow_context:stablecoin_liquidity:defillama_stablecoins:"
                        "ALL_STABLECOINS:all:2026-06-18T00:00:00Z"
                    ),
                    "context_type": "stablecoin_liquidity",
                    "data_class": "stablecoin_supply",
                    "source": "defillama_stablecoins",
                    "asset": "ALL_STABLECOINS",
                    "chain": "all",
                    "as_of": "2026-06-18T00:00:00Z",
                    "status": "succeeded",
                    "state": "sharp_stablecoin_supply_contraction",
                    "severity": "high",
                    "confidence": "medium",
                    "source_availability": "succeeded",
                    "metrics": {"stablecoin_supply_change_pct": -0.1},
                    "thresholds": {"sharp_supply_contraction_change_pct": -0.05},
                    "evidence": [],
                    "uncertainty": ["stablecoin supply is liquidity context, not a price forecast."],
                    "warnings": [],
                    "errors": [],
                    "source_artifacts": [
                        "analysis/onchain_flow_context.json",
                        "raw/onchain_flow_views.json",
                    ],
                },
                {
                    "context_id": (
                        "onchain_flow_context:network_congestion:blockchain_com_charts:"
                        "BTC:bitcoin:2026-06-18T00:00:00Z"
                    ),
                    "context_type": "network_congestion",
                    "data_class": "network_congestion",
                    "source": "blockchain_com_charts",
                    "asset": "BTC",
                    "chain": "bitcoin",
                    "as_of": "2026-06-18T00:00:00Z",
                    "status": "succeeded",
                    "state": "elevated_network_congestion",
                    "severity": "medium",
                    "confidence": "medium",
                    "source_availability": "succeeded",
                    "metrics": {"latest_mempool_size_bytes": 120000000.0},
                    "thresholds": {"elevated_mempool_size_bytes": 20000000.0},
                    "evidence": [],
                    "uncertainty": ["network congestion is settlement-friction context."],
                    "warnings": [],
                    "errors": [],
                    "source_artifacts": [
                        "analysis/onchain_flow_context.json",
                        "raw/onchain_flow_views.json",
                    ],
                },
                {
                    "context_id": (
                        "onchain_flow_context:exchange_flow_source_availability:"
                        "public_exchange_flow_aggregate:ALL_CONFIGURED_ASSETS:"
                        "all:2026-06-18T00:00:00Z"
                    ),
                    "context_type": "exchange_flow_source_availability",
                    "data_class": "exchange_flow_availability",
                    "source": "public_exchange_flow_aggregate",
                    "asset": "ALL_CONFIGURED_ASSETS",
                    "chain": "all",
                    "as_of": "2026-06-18T00:00:00Z",
                    "status": "unavailable",
                    "state": "source_unavailable",
                    "severity": "medium",
                    "confidence": "low",
                    "source_availability": "unavailable",
                    "metrics": {},
                    "thresholds": {},
                    "evidence": [],
                    "uncertainty": ["unavailable exchange-flow source prevents deterministic context."],
                    "warnings": ["exchange-flow source is unavailable."],
                    "errors": [],
                    "source_artifacts": [
                        "analysis/onchain_flow_context.json",
                        "raw/onchain_flow.json",
                    ],
                },
            ],
            "counts": {"records": 3},
            "warnings": ["exchange-flow source is unavailable."],
            "errors": [],
            "source_artifacts": ["raw/onchain_flow_views.json", "raw/onchain_flow.json"],
        },
    )
    run.analysis_dir.joinpath("onchain_flow_material.md").write_text(
        "\n".join(
            [
                "---",
                "artifact_type: analysis_onchain_flow_material",
                "schema_version: 1",
                "audience: ai",
                "source_artifacts:",
                "  - analysis/onchain_flow_context.json",
                "---",
                "",
                "# onchain_flow_material",
                "",
                "codex_may_generate_onchain_records: false",
                "codex_may_generate_flow_states: false",
                "codex_may_generate_address_labels: false",
                "full_onchain_flow_context_json_embedded: false",
                "",
            ]
        ),
        encoding="utf-8",
    )
    run.manifest["artifacts"]["codex_prompt"] = "codex_context/prompt.md"
    run.manifest["artifacts"]["onchain_flow_context"] = "analysis/onchain_flow_context.json"
    run.manifest["artifacts"]["onchain_flow_material"] = "analysis/onchain_flow_material.md"
    return ["codex_context/prompt.md"]


def _stage(manifest: dict, name: str) -> dict:
    return next(
        task
        for stage in manifest["stages"]
        for task in stage.get("tasks", [])
        if task["name"] == name
    )
