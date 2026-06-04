from __future__ import annotations

import json
from pathlib import Path

from halpha.cli import main
from halpha.config import load_config
from halpha.pipeline import STAGE_ORDER, run_pipeline


def test_pipeline_scaffold_creates_failed_manifest_without_fake_artifacts(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(config, config_path=config_path)

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
    assert manifest["stages"][0]["name"] == "collect_market_data"
    assert manifest["stages"][0]["status"] == "failed"
    assert manifest["errors"] == [
        {
            "stage": "collect_market_data",
            "message": "stage collect_market_data is not implemented",
        }
    ]


def test_cli_run_reports_manifest_and_nonzero_exit(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path)

    exit_code = main(["run", "--config", str(config_path)])

    captured = capsys.readouterr()
    assert exit_code == 3
    assert "Halpha run failed." in captured.out
    assert "stage: collect_market_data" in captured.out
    assert "reason: stage collect_market_data is not implemented" in captured.out
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
