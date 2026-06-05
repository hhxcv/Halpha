from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from halpha.cli import main
from halpha.config import load_config
from halpha.pipeline import PipelineError, STAGE_ORDER, run_pipeline


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
    assert manifest["stages"][1]["name"] == "collect_text_events"
    assert manifest["stages"][1]["status"] == "failed"
    assert manifest["stages"][1]["started_at"].endswith("Z")
    assert manifest["stages"][1]["finished_at"].endswith("Z")
    assert manifest["stages"][1]["artifacts"] == []
    assert manifest["stages"][1]["error"] == {
        "stage": "collect_text_events",
        "message": "stage collect_text_events is not implemented",
    }
    assert manifest["errors"] == [manifest["stages"][1]["error"]]
    assert not (result.run.raw_dir / "text_events.json").exists()
    assert not (result.run.report_dir / "report.md").exists()
    _assert_manifest_timeline(manifest)


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


def test_cli_run_reports_manifest_and_nonzero_exit(tmp_path: Path, capsys, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.setattr("halpha.collectors.market.urlopen", _fake_urlopen)
    monkeypatch.setattr("halpha.collectors.text.urlopen", _fake_rss_urlopen)

    exit_code = main(["run", "--config", str(config_path)])

    captured = capsys.readouterr()
    assert exit_code == 3
    assert "Halpha run failed." in captured.out
    assert "stage: build_research_context" in captured.out
    assert "reason: stage build_research_context is not implemented" in captured.out
    assert "manifest:" in captured.out


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
