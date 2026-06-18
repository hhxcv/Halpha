from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from halpha.cli import main
from halpha.config import load_config
from halpha.pipeline import PipelineError, STAGE_ORDER, run_pipeline, run_pipeline_stage


def test_pipeline_records_failed_stage_without_fake_artifacts(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={"collect_market_data": _failed_market_stage},
    )

    assert result.succeeded is False
    assert result.exit_code == 3
    assert result.failed_stage == "collect_market_data"
    assert result.run.raw_dir.is_dir()
    assert result.run.analysis_dir.is_dir()
    assert result.run.codex_context_dir.is_dir()
    assert result.run.report_dir.is_dir()
    assert not (result.run.raw_dir / "market.json").exists()
    assert not (result.run.analysis_dir / "market_material.md").exists()
    assert not (result.run.report_dir / "report.md").exists()

    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "failed"
    assert manifest["stage_order"] == list(STAGE_ORDER)
    assert manifest["codex"] == {
        "enabled": True,
        "command": "codex",
        "status": "not_started",
        "exit_code": None,
    }
    assert manifest["stages"][0]["name"] == "collect_market_data"
    assert manifest["stages"][0]["status"] == "failed"
    assert manifest["stages"][0]["started_at"].endswith("Z")
    assert manifest["stages"][0]["finished_at"].endswith("Z")
    assert manifest["stages"][0]["artifacts"] == []
    assert manifest["stages"][0]["error"] == {
        "stage": "collect_market_data",
        "message": "stage collect_market_data is not implemented",
    }
    assert manifest["errors"] == [
        {
            "stage": "collect_market_data",
            "message": "stage collect_market_data is not implemented",
        }
    ]
    _assert_manifest_timeline(manifest)


def test_pipeline_records_successful_stage_lifecycle_before_later_failure(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def collect_market_data(config, run) -> list[str]:
        artifact = run.raw_dir / "market.json"
        artifact.write_text("{}", encoding="utf-8")
        return ["raw/market.json"]

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": collect_market_data,
            "collect_text_events": _failed_text_stage,
        },
    )

    assert result.succeeded is False
    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["stages"][0]["name"] == "collect_market_data"
    assert manifest["stages"][0]["status"] == "succeeded"
    assert manifest["stages"][0]["started_at"].endswith("Z")
    assert manifest["stages"][0]["finished_at"].endswith("Z")
    assert manifest["stages"][0]["artifacts"] == ["raw/market.json"]
    assert "error" not in manifest["stages"][0]
    assert manifest["stages"][1]["name"] == "collect_derivatives_market_data"
    assert manifest["stages"][1]["status"] == "succeeded"
    assert manifest["stages"][1]["artifacts"] == []
    assert manifest["stages"][2]["name"] == "sync_derivatives_market_history"
    assert manifest["stages"][2]["status"] == "succeeded"
    assert manifest["stages"][2]["artifacts"] == []
    assert manifest["stages"][3]["name"] == "build_derivatives_market_views"
    assert manifest["stages"][3]["status"] == "succeeded"
    assert manifest["stages"][3]["artifacts"] == []
    assert manifest["stages"][4]["name"] == "build_derivatives_market_context"
    assert manifest["stages"][4]["status"] == "succeeded"
    assert manifest["stages"][4]["artifacts"] == []
    assert manifest["stages"][5]["name"] == "collect_macro_calendar_data"
    assert manifest["stages"][5]["status"] == "succeeded"
    assert manifest["stages"][5]["artifacts"] == []
    assert manifest["stages"][6]["name"] == "collect_text_events"
    assert manifest["stages"][6]["status"] == "failed"
    assert manifest["stages"][6]["started_at"].endswith("Z")
    assert manifest["stages"][6]["finished_at"].endswith("Z")
    assert manifest["stages"][6]["artifacts"] == []
    assert manifest["stages"][6]["error"] == {
        "stage": "collect_text_events",
        "message": "stage collect_text_events is not implemented",
    }
    assert manifest["errors"] == [manifest["stages"][6]["error"]]
    assert not (result.run.raw_dir / "text_events.json").exists()
    assert not (result.run.report_dir / "report.md").exists()
    _assert_manifest_timeline(manifest)


def test_pipeline_records_finished_at_after_stage_handler_returns(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    current = [datetime(2026, 6, 5, 0, 0, tzinfo=timezone.utc)]

    def fake_clock(now):
        return lambda: current[0]

    def collect_market_data(config, run) -> list[str]:
        current[0] = current[0] + timedelta(minutes=5)
        return []

    monkeypatch.setattr("halpha.pipeline._clock", fake_clock)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="collect_market_data",
        stage_handlers={"collect_market_data": collect_market_data},
    )

    assert result.succeeded is True
    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["stages"][0]["started_at"] == "2026-06-05T00:00:00Z"
    assert manifest["stages"][0]["finished_at"] == "2026-06-05T00:05:00Z"
    assert manifest["finished_at"] == "2026-06-05T00:05:00Z"


def test_pipeline_records_finished_at_after_stage_handler_failure(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    current = [datetime(2026, 6, 5, 0, 0, tzinfo=timezone.utc)]

    def fake_clock(now):
        return lambda: current[0]

    def collect_market_data(config, run) -> None:
        current[0] = current[0] + timedelta(minutes=3)
        raise PipelineError("stage collect_market_data failed", stage="collect_market_data", exit_code=3)

    monkeypatch.setattr("halpha.pipeline._clock", fake_clock)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={"collect_market_data": collect_market_data},
    )

    assert result.succeeded is False
    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["stages"][0]["started_at"] == "2026-06-05T00:00:00Z"
    assert manifest["stages"][0]["finished_at"] == "2026-06-05T00:03:00Z"
    assert manifest["finished_at"] == "2026-06-05T00:03:00Z"
    _assert_manifest_timeline(manifest)


def test_single_stage_records_finished_at_after_handler_returns(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    initial = run_pipeline(
        config,
        config_path=config_path,
        until_stage="collect_market_data",
        stage_handlers={"collect_market_data": lambda config, run: []},
        now=datetime(2026, 6, 5, 0, 0, tzinfo=timezone.utc),
    )
    current = [datetime(2026, 6, 5, 1, 0, tzinfo=timezone.utc)]

    def fake_clock(now):
        return lambda: current[0]

    def collect_text_events(config, run) -> list[str]:
        current[0] = current[0] + timedelta(minutes=7)
        return []

    monkeypatch.setattr("halpha.pipeline._clock", fake_clock)

    result = run_pipeline_stage(
        config,
        config_path=config_path,
        run_dir=initial.run.run_dir,
        stage="collect_text_events",
        stage_handlers={"collect_text_events": collect_text_events},
    )

    assert result.succeeded is True
    manifest = json.loads(result.run.manifest_path.read_text(encoding="utf-8"))
    single_stage = manifest["stages"][-1]
    assert single_stage["name"] == "collect_text_events"
    assert single_stage["mode"] == "single_stage"
    assert single_stage["started_at"] == "2026-06-05T01:00:00Z"
    assert single_stage["finished_at"] == "2026-06-05T01:07:00Z"
    assert manifest["finished_at"] == "2026-06-05T01:07:00Z"


def test_pipeline_uses_utc_run_id_and_does_not_overwrite_existing_run_dir(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    now = datetime(2026, 6, 5, 8, 30, tzinfo=timezone(timedelta(hours=8)))

    stage_handlers = {"collect_market_data": _failed_market_stage}
    first = run_pipeline(config, config_path=config_path, stage_handlers=stage_handlers, now=now)
    second = run_pipeline(config, config_path=config_path, stage_handlers=stage_handlers, now=now)

    assert first.run.run_id == "20260605T003000Z"
    assert second.run.run_id == "20260605T003000Z-01"
    assert first.run.run_dir != second.run.run_dir
    assert first.run.manifest_path.exists()
    assert second.run.manifest_path.exists()
    manifest = json.loads(first.run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["started_at"] == "2026-06-05T00:30:00Z"
    assert manifest["stages"][0]["started_at"] == "2026-06-05T00:30:00Z"
    assert manifest["stages"][0]["finished_at"] == "2026-06-05T00:30:00Z"
    assert manifest["finished_at"] == "2026-06-05T00:30:00Z"
    _assert_manifest_timeline(manifest)


def test_cli_run_reports_report_manifest_and_zero_exit(tmp_path: Path, capsys, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.setattr("halpha.collectors.market.urlopen", _fake_urlopen)
    monkeypatch.setattr("halpha.collectors.text.urlopen", _fake_rss_urlopen)
    monkeypatch.setattr("halpha.codex.runner.subprocess.run", _fake_codex_run)

    exit_code = main(["run", "--config", str(config_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Halpha run succeeded." in captured.out
    assert "report:" in captured.out
    assert "manifest:" in captured.out

    report_paths = sorted(tmp_path.glob("runs/*/report/report.md"))
    assert len(report_paths) == 1
    assert "## 风险提示" in report_paths[0].read_text(encoding="utf-8")


def test_cli_run_returns_codex_failure_exit_code(tmp_path: Path, capsys, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.setattr("halpha.collectors.market.urlopen", _fake_urlopen)
    monkeypatch.setattr("halpha.collectors.text.urlopen", _fake_rss_urlopen)
    monkeypatch.setattr("halpha.codex.runner.subprocess.run", _fake_codex_failure_run)

    exit_code = main(["run", "--config", str(config_path)])

    captured = capsys.readouterr()
    assert exit_code == 17
    assert "Halpha run failed." in captured.out
    assert "stage: run_codex_report" in captured.out
    assert "reason: Codex command failed with exit code 17." in captured.out
    assert "manifest:" in captured.out
    assert not list(tmp_path.glob("runs/*/report/report.md"))


def test_cli_run_no_codex_skips_report_without_fake_report(tmp_path: Path, capsys, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.setattr("halpha.collectors.market.urlopen", _fake_urlopen)
    monkeypatch.setattr("halpha.collectors.text.urlopen", _fake_rss_urlopen)

    def fail_if_codex_runs(*args, **kwargs):
        raise AssertionError("Codex should not run in --no-codex mode.")

    monkeypatch.setattr("halpha.codex.runner.subprocess.run", fail_if_codex_runs)

    exit_code = main(["run", "--config", str(config_path), "--no-codex"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Halpha run succeeded." in captured.out
    assert "codex: skipped" in captured.out
    assert "report:" not in captured.out

    run_dir = _single_run_dir(tmp_path)
    manifest = _manifest(run_dir)
    assert manifest["status"] == "succeeded"
    assert manifest["validation"] == {
        "mode": "run",
        "skip_codex": True,
        "until_stage": None,
    }
    assert manifest["codex"]["status"] == "skipped"
    assert manifest["codex"]["exit_code"] is None
    assert manifest["codex"]["skip_reason"] == "--no-codex requested"
    assert manifest["stages"][-1]["name"] == "run_codex_report"
    assert manifest["stages"][-1]["status"] == "skipped"
    assert manifest["stages"][-1]["artifacts"] == []
    assert (run_dir / "codex_context" / "prompt.md").is_file()
    assert not (run_dir / "report" / "report.md").exists()
    assert "report" not in manifest["artifacts"]


def test_cli_run_until_marks_later_stages_not_run(tmp_path: Path, capsys, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.setattr("halpha.collectors.market.urlopen", _fake_urlopen)
    monkeypatch.setattr("halpha.collectors.text.urlopen", _fake_rss_urlopen)

    def fail_if_codex_runs(*args, **kwargs):
        raise AssertionError("Codex should not run after --until build_research_context.")

    monkeypatch.setattr("halpha.codex.runner.subprocess.run", fail_if_codex_runs)

    exit_code = main(["run", "--config", str(config_path), "--until", "build_research_context"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Halpha run succeeded." in captured.out
    assert "report:" not in captured.out

    run_dir = _single_run_dir(tmp_path)
    manifest = _manifest(run_dir)
    assert manifest["validation"] == {
        "mode": "run",
        "skip_codex": False,
        "until_stage": "build_research_context",
    }
    assert _stage(manifest, "build_research_context")["status"] == "succeeded"
    codex_context = _stage(manifest, "build_codex_context")
    codex_report = _stage(manifest, "run_codex_report")
    assert codex_context["status"] == "not_run"
    assert codex_context["reason"] == "--until build_research_context requested"
    assert codex_report["status"] == "not_run"
    assert codex_report["reason"] == "--until build_research_context requested"
    assert manifest["codex"]["status"] == "not_run"
    assert manifest["codex"]["skip_reason"] == "--until build_research_context requested"
    assert (run_dir / "analysis" / "research_context.md").is_file()
    assert not (run_dir / "codex_context" / "prompt.md").exists()
    assert not (run_dir / "report" / "report.md").exists()


def test_cli_stage_runs_single_stage_against_existing_run_dir(tmp_path: Path, capsys, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.setattr("halpha.collectors.market.urlopen", _fake_urlopen)
    monkeypatch.setattr("halpha.collectors.text.urlopen", _fake_rss_urlopen)

    assert main(["run", "--config", str(config_path), "--until", "build_analysis_materials"]) == 0
    run_dir = _single_run_dir(tmp_path)
    assert not (run_dir / "analysis" / "research_context.md").exists()

    exit_code = main(
        [
            "stage",
            "build_research_context",
            "--config",
            str(config_path),
            "--run-dir",
            str(run_dir),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Halpha stage succeeded." in captured.out
    assert "stage: build_research_context" in captured.out
    assert (run_dir / "analysis" / "research_context.md").is_file()

    manifest = _manifest(run_dir)
    assert manifest["artifacts"]["research_context"] == "analysis/research_context.md"
    assert manifest["single_stage_validation"]["stage"] == "build_research_context"
    single_stage = manifest["stages"][-1]
    assert single_stage["name"] == "build_research_context"
    assert single_stage["mode"] == "single_stage"
    assert single_stage["status"] == "succeeded"
    assert single_stage["artifacts"] == ["analysis/research_context.md"]


def test_cli_validation_stage_names_are_actionable_and_do_not_create_runs(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_config(tmp_path)

    run_exit = main(["run", "--config", str(config_path), "--until", "missing_stage"])
    run_output = capsys.readouterr().out
    assert run_exit == 2
    assert "Halpha run failed." in run_output
    assert "stage: cli" in run_output
    assert "--until must be one of:" in run_output
    assert not (tmp_path / "runs").exists()

    run_dir = tmp_path / "existing-run"
    run_dir.mkdir()
    stage_exit = main(
        [
            "stage",
            "missing_stage",
            "--config",
            str(config_path),
            "--run-dir",
            str(run_dir),
        ]
    )
    stage_output = capsys.readouterr().out
    assert stage_exit == 2
    assert "Halpha stage failed." in stage_output
    assert "stage: cli" in stage_output
    assert "stage must be one of:" in stage_output
    assert not (run_dir / "run_manifest.json").exists()


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  output_dir: runs
  timezone: Asia/Shanghai
market:
  enabled: true
  source: binance
  symbols:
    - BTCUSDT
text:
  enabled: true
  max_items: 1
  sources:
    - name: coindesk
      type: rss
      url: https://www.coindesk.com/arc/outboundfeeds/rss/
report:
  title: Daily Market Brief
  language: zh-CN
codex:
  enabled: true
  command: codex
  args:
    - exec
    - --sandbox
    - read-only
    - "-"
  timeout_seconds: 300
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _single_run_dir(tmp_path: Path) -> Path:
    run_dirs = sorted((tmp_path / "runs").iterdir())
    assert len(run_dirs) == 1
    return run_dirs[0]


def _manifest(run_dir: Path) -> dict:
    return json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))


def _stage(manifest: dict, name: str) -> dict:
    return next(stage for stage in manifest["stages"] if stage["name"] == name)


def _assert_manifest_timeline(manifest: dict) -> None:
    stages = manifest["stages"]
    assert manifest["started_at"] <= stages[0]["started_at"]
    for stage in stages:
        assert stage["started_at"] <= stage["finished_at"]
    assert stages[-1]["finished_at"] <= manifest["finished_at"]


def _failed_market_stage(config, run) -> None:
    raise PipelineError(
        "stage collect_market_data is not implemented",
        stage="collect_market_data",
        exit_code=3,
    )


def _failed_text_stage(config, run) -> None:
    raise PipelineError(
        "stage collect_text_events is not implemented",
        stage="collect_text_events",
        exit_code=3,
    )


def _fake_urlopen(request, timeout):
    return _FakeResponse(
        {
            "symbol": "BTCUSDT",
            "lastPrice": "68000.00",
            "priceChangePercent": "1.25",
            "volume": "123.45",
            "quoteVolume": "8394600.00",
            "closeTime": 1780619400000,
        }
    )


def _fake_rss_urlopen(request, timeout):
    return _FakeBytesResponse(
        b"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <item>
      <title>Market event</title>
      <link>https://example.com/market-event</link>
      <guid>event-1</guid>
      <pubDate>Fri, 05 Jun 2026 00:30:00 GMT</pubDate>
      <description>Source-provided event text.</description>
    </item>
  </channel>
</rss>
"""
    )


def _fake_codex_run(command, input, text, encoding, errors, capture_output, timeout, cwd):
    assert command[1:] == ["exec", "--sandbox", "read-only", "-"]
    assert "Generate a Simplified Chinese Markdown market intelligence report" in input
    assert "Use Chinese section headings only." in input
    assert text is True
    assert encoding == "utf-8"
    assert errors == "replace"
    assert capture_output is True
    assert timeout == 300
    assert cwd.name
    return subprocess.CompletedProcess(
        command,
        0,
        stdout="# 每日市场简报\n\n## 风险提示\n公开来源较少，后续事件可能改变当前观察。\n",
        stderr="",
    )


def _fake_codex_failure_run(command, input, text, encoding, errors, capture_output, timeout, cwd):
    return subprocess.CompletedProcess(
        command,
        17,
        stdout="partial report",
        stderr="Codex failed",
    )


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class _FakeBytesResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self.payload
