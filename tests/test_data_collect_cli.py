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

    monkeypatch.setattr("halpha.cli.collect_research_data", fake_collect)

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
    assert calls[0]["apply"] is True
    assert calls[0]["source"] == "binance"
    assert calls[0]["symbol"] == "BTCUSDT"
    assert calls[0]["timeframe"] == "1d"
    assert "Halpha data collection apply succeeded." in output
    assert "coverage_records_written: 1" in output
    assert "collection_coverage: data/research/metadata/collection_coverage_state.json" in output


def test_data_collect_text_event_apply_uses_shared_service_boundary(
    tmp_path: Path,
    capsys,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_text_config(tmp_path)
    calls: list[dict[str, Any]] = []

    def fake_collect(config: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {
            "schema_version": 1,
            "artifact_type": "text_event_collection_result",
            "mode": "apply",
            "status": "warning",
            "data_type": "text_event",
            "source": kwargs["source"],
            "symbol": None,
            "timeframe": None,
            "identity": {"source_name": kwargs["source"]},
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
                "raw_items": 1,
                "raw_errors": 1,
                "window_records": 1,
                "stored_records": 1,
                "coverage_records_written": 1,
                "coverage_state_records": 1,
            },
            "artifacts": {"collection_coverage": "data/research/metadata/collection_coverage_state.json"},
            "warnings": ["partial source failure"],
            "errors": [],
        }

    monkeypatch.setattr("halpha.cli.collect_research_data", fake_collect)

    exit_code = main(
        [
            "data",
            "collect",
            "--config",
            str(config_path),
            "--data-type",
            "text_event",
            "--source",
            "coindesk",
            "--start",
            "2026-06-01T00:00:00Z",
            "--end",
            "2026-06-03T00:00:00Z",
            "--apply",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert calls[0]["apply"] is True
    assert calls[0]["source"] == "coindesk"
    assert "Halpha data collection apply succeeded." in output
    assert "data_type: text_event" in output
    assert "identity: {'source_name': 'coindesk'}" in output
    assert "raw_items: 1" in output
    assert "raw_errors: 1" in output


def test_data_collect_ohlcv_requires_symbol_and_timeframe(tmp_path: Path, capsys) -> None:
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
            "--start",
            "2026-06-01T00:00:00Z",
            "--end",
            "2026-06-03T00:00:00Z",
            "--dry-run",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "data collect --data-type ohlcv requires --source, --symbol and --timeframe." in output


def test_data_collect_macro_calendar_apply_uses_configured_pipeline_without_source(
    tmp_path: Path,
    capsys,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_macro_config(tmp_path)
    calls: list[dict[str, Any]] = []

    def fake_collect(config: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {
            "schema_version": 1,
            "artifact_type": "research_data_collection_result",
            "mode": "apply",
            "status": "succeeded",
            "data_type": "macro_calendar",
            "source": "configured",
            "symbol": None,
            "timeframe": None,
            "requested_start": kwargs["requested_start"],
            "requested_end": kwargs["requested_end"],
            "plan": {"strategy": "configured_scope", "planned_fetch_windows": []},
            "counts": {"raw_items": 2},
            "artifacts": {"manifest": "runs/run-1/run_manifest.json"},
            "warnings": [],
            "errors": [],
        }

    monkeypatch.setattr("halpha.cli.collect_research_data", fake_collect)

    exit_code = main(
        [
            "data",
            "collect",
            "--config",
            str(config_path),
            "--data-type",
            "macro_calendar",
            "--start",
            "2026-06-01T00:00:00Z",
            "--end",
            "2026-06-03T00:00:00Z",
            "--apply",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Halpha data collection apply succeeded." in output
    assert "data_type: macro_calendar" in output
    assert "source: configured" in output
    assert calls[0]["data_type"] == "macro_calendar"
    assert calls[0]["source"] is None
    assert calls[0]["symbol"] is None
    assert calls[0]["timeframe"] is None
    assert calls[0]["apply"] is True


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


def _write_text_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  output_dir: runs
  timezone: Asia/Shanghai
market:
  enabled: false
text:
  enabled: true
  sources:
    - name: coindesk
      type: rss
      url: https://example.com/rss.xml
report:
  title: Daily Market Brief
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _write_macro_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  output_dir: runs
  timezone: Asia/Shanghai
market:
  enabled: false
macro_calendar:
  enabled: true
  source: federal_reserve_fomc
  data_classes:
    - central_bank_event
  regions:
    - US
  lookback_days: 7
  lookahead_days: 45
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
