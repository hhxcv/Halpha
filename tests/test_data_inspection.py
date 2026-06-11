from __future__ import annotations

import json
from pathlib import Path

import pytest

from halpha.cli import main
from halpha.pipeline import RunContext
from halpha.run_index import write_run_index
from halpha.storage import write_json


def test_data_inspect_reports_missing_optional_stores_without_private_config_values(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_config(
        tmp_path,
        ohlcv_enabled=False,
        proxy_url="http://private-host.local:18080",
    )

    exit_code = main(["data", "inspect", "--config", str(config_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Halpha data inspection succeeded." in output
    assert "status: ok" in output
    assert "research_data_catalog: skipped" in output
    assert "run_index: skipped" in output
    assert "text_event_history: skipped" in output
    assert "ohlcv_history: skipped" in output
    assert "data_quality_summary: skipped" in output
    assert "private-host" not in output
    assert "18080" not in output
    assert str(tmp_path) not in output


def test_data_inspect_reports_local_stores_and_degraded_quality_summary(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_config(tmp_path, ohlcv_enabled=True)
    run = _write_run_with_quality(tmp_path, config_path, quality_status="degraded")
    _write_store_metadata(tmp_path, run)

    exit_code = main(["data", "inspect", "--config", str(config_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Halpha data inspection succeeded." in output
    assert "status: degraded" in output
    assert "research_data_catalog: ok" in output
    assert "stores=3" in output
    assert "store_statuses: ohlcv_history=ok, run_index=ok, text_event_history=ok" in output
    assert "run_index: ok" in output
    assert "latest_successful_run_id=run-1" in output
    assert "text_event_history: ok" in output
    assert "records=2" in output
    assert "ohlcv_history: ok" in output
    assert "items=1" in output
    assert "data_quality_summary: degraded" in output
    assert "run_id=run-1" in output
    assert "checks=8" in output
    assert "degraded=1" in output
    assert "runs/run-1/analysis/data_quality_summary.json" in output
    assert "CREATE TABLE" not in output
    assert "content_text" not in output
    assert "stable_event_key" not in output
    assert str(tmp_path) not in output


def test_data_inspect_uses_specific_run_dir_and_reports_missing_quality_as_skipped(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_config(tmp_path, ohlcv_enabled=False)
    run_dir = tmp_path / "runs" / "run-without-quality"
    run_dir.mkdir(parents=True)
    write_json(
        run_dir / "run_manifest.json",
        {
            "schema_version": 1,
            "run_id": "run-without-quality",
            "status": "succeeded",
            "artifacts": {},
            "counts": {},
            "stages": [],
            "errors": [],
        },
    )

    exit_code = main(
        [
            "data",
            "inspect",
            "--config",
            str(config_path),
            "--run-dir",
            "runs/run-without-quality",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "data_quality_summary: skipped" in output
    assert "run_id=run-without-quality" in output
    assert "run_status=succeeded" in output


def test_data_inspect_returns_error_for_missing_requested_run_dir(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path, ohlcv_enabled=False)

    exit_code = main(
        [
            "data",
            "inspect",
            "--config",
            str(config_path),
            "--run-dir",
            "runs/missing",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 3
    assert "Halpha data inspection failed." in output
    assert "stage: data_inspect" in output
    assert "requested run directory was not found" in output


def test_data_inspect_help_mentions_run_dir(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["data", "inspect", "--help"])

    output = capsys.readouterr().out
    assert exc.value.code == 0
    assert "Inspect local stores and data-quality state." in output
    assert "--config" in output
    assert "--run-dir" in output


def _write_config(
    tmp_path: Path,
    *,
    ohlcv_enabled: bool,
    proxy_url: str | None = None,
) -> Path:
    proxy_block = (
        f"""
  proxy:
    enabled: true
    url: {proxy_url}
"""
        if proxy_url
        else """
  proxy:
    enabled: false
"""
    )
    ohlcv_block = (
        """
  ohlcv:
    storage_dir: data/market/ohlcv
    timeframes:
      - 1d
    lookback:
      1d: 10
"""
        if ohlcv_enabled
        else ""
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
run:
  output_dir: runs
  timezone: Asia/Shanghai
market:
  enabled: true
  source: binance
{proxy_block.rstrip()}
  symbols:
    - BTCUSDT
{ohlcv_block.rstrip()}
text:
  enabled: false
report:
  title: Daily Market Brief
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _write_run_with_quality(tmp_path: Path, config_path: Path, *, quality_status: str) -> RunContext:
    run_dir = tmp_path / "runs" / "run-1"
    raw_dir = run_dir / "raw"
    analysis_dir = run_dir / "analysis"
    codex_context_dir = run_dir / "codex_context"
    report_dir = run_dir / "report"
    for directory in (raw_dir, analysis_dir, codex_context_dir, report_dir):
        directory.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "run_id": "run-1",
        "status": "succeeded",
        "started_at": "2026-06-05T00:00:00Z",
        "finished_at": "2026-06-05T00:10:00Z",
        "artifacts": {"data_quality_summary": "analysis/data_quality_summary.json"},
        "counts": {},
        "stages": [{"name": "build_data_quality_summary", "status": "succeeded"}],
        "codex": {"status": "skipped"},
        "errors": [],
    }
    run = RunContext(
        run_id="run-1",
        run_dir=run_dir,
        raw_dir=raw_dir,
        analysis_dir=analysis_dir,
        codex_context_dir=codex_context_dir,
        report_dir=report_dir,
        manifest_path=run_dir / "run_manifest.json",
        config_path=config_path,
        manifest=manifest,
    )
    write_json(run.manifest_path, manifest)
    write_json(
        analysis_dir / "data_quality_summary.json",
        {
            "schema_version": 1,
            "artifact_type": "data_quality_summary",
            "run_id": "run-1",
            "created_at": "2026-06-05T00:10:00Z",
            "status": quality_status,
            "counts": {
                "checks": 8,
                "ok": 7,
                "warning": 0,
                "degraded": 1,
                "skipped": 0,
                "failed": 0,
                "warnings": 1,
                "errors": 0,
            },
            "checks": [],
            "warnings": ["one configured source returned partial data."],
            "errors": [],
            "source_artifacts": ["raw/market.json"],
        },
    )
    summary = write_run_index(run, now="2026-06-05T00:10:00Z")
    run.manifest["run_index"] = summary
    return run


def _write_store_metadata(tmp_path: Path, run: RunContext) -> None:
    write_json(
        tmp_path / "data" / "research" / "metadata" / "research_data_catalog.json",
        {
            "schema_version": 1,
            "artifact_type": "research_data_catalog",
            "generated_at": "2026-06-05T00:10:00Z",
            "status": "ok",
            "stores": [
                {"name": "ohlcv_history", "status": "ok"},
                {"name": "run_index", "status": "ok"},
                {"name": "text_event_history", "status": "ok"},
            ],
            "counts": {"stores": 3, "records": 5, "warnings": 0, "errors": 0},
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        tmp_path / "data" / "research" / "metadata" / "text_event_history_state.json",
        {
            "schema_version": 1,
            "status": "ok",
            "updated_at": "2026-06-05T00:10:00Z",
            "totals": {"records": 2},
            "sources": [{"source": "coindesk"}],
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        tmp_path / "data" / "market" / "metadata" / "ohlcv_schema.json",
        {
            "schema_version": 1,
            "unique_key": ["source", "symbol", "timeframe", "open_time"],
        },
    )
    write_json(
        tmp_path / "data" / "market" / "metadata" / "ohlcv_sync_state.json",
        {
            "schema_version": 1,
            "status": "ok",
            "updated_at": "2026-06-05T00:10:00Z",
            "items": [{"source": "binance", "symbol": "BTCUSDT", "timeframe": "1d", "row_count": 3}],
            "warnings": [],
            "errors": [],
        },
    )
