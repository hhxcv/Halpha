from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from halpha.cli import main


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_data_collect_help_mentions_ohlcv_and_apply(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["data", "collect", "--help"])

    output = capsys.readouterr().out
    assert exc.value.code == 0
    assert "Collect or backfill local research data without running a report." in output
    assert "--data-type" in output
    assert "--apply" in output
    assert "--dry-run" in output


def test_data_collect_dry_run_prints_plan_without_writes(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path)

    exit_code = main(
        [
            "data",
            "collect",
            "--config",
            str(config_path),
            "--data-type",
            "ohlcv",
            "--source",
            "binance",
            "--symbol",
            "BTCUSDT",
            "--timeframe",
            "1d",
            "--start",
            "2026-06-01T00:00:00Z",
            "--end",
            "2026-06-03T00:00:00Z",
            "--dry-run",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Halpha data collection dry run succeeded." in output
    assert "mode: dry_run" in output
    assert "data_type: ohlcv" in output
    assert "strategy: gap_only" in output
    assert "planned_fetch_windows: 1" in output
    assert "fetch_window: 2026-06-01T00:00:00Z..2026-06-03T00:00:00Z reason=missing_coverage" in output
    assert not (tmp_path / "data").exists()


def test_data_collect_apply_uses_shared_service_boundary(
    tmp_path: Path,
    capsys,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    calls: list[dict[str, Any]] = []

    def fake_collect(config: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {
            "schema_version": 1,
            "artifact_type": "ohlcv_collection_result",
            "mode": "apply",
            "status": "ok",
            "data_type": "ohlcv",
            "source": kwargs["source"],
            "symbol": kwargs["symbol"],
            "timeframe": kwargs["timeframe"],
            "requested_start": kwargs["requested_start"],
            "requested_end": kwargs["requested_end"],
            "plan": {"strategy": "gap_only", "planned_fetch_windows": []},
            "fetches": [],
            "coverage_updates": [],
            "counts": {
                "skipped_ranges": 0,
                "gap_ranges": 1,
                "retry_ranges": 0,
                "planned_fetch_windows": 1,
                "fetched_records": 2,
                "window_records": 2,
                "stored_records": 2,
                "coverage_records_written": 1,
                "coverage_state_records": 1,
            },
            "artifacts": {"collection_coverage": "data/research/metadata/collection_coverage_state.json"},
            "warnings": [],
            "errors": [],
        }

    monkeypatch.setattr("halpha.cli.collect_ohlcv_data", fake_collect)

    exit_code = main(
        [
            "data",
            "collect",
            "--config",
            str(config_path),
            "--data-type",
            "ohlcv",
            "--source",
            "binance",
            "--symbol",
            "BTCUSDT",
            "--timeframe",
            "1d",
            "--start",
            "2026-06-01T00:00:00Z",
            "--end",
            "2026-06-03T00:00:00Z",
            "--apply",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert calls[0]["dry_run"] is False
    assert calls[0]["source"] == "binance"
    assert calls[0]["symbol"] == "BTCUSDT"
    assert calls[0]["timeframe"] == "1d"
    assert "Halpha data collection apply succeeded." in output
    assert "coverage_records_written: 1" in output
    assert "collection_coverage: data/research/metadata/collection_coverage_state.json" in output


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
  ohlcv:
    storage_dir: data/market/ohlcv
    timeframes:
      - 1d
    lookback:
      1d: 2
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
