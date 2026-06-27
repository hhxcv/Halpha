from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from halpha.cli import main
from halpha.market.ohlcv_store import OHLCVParquetStore
from halpha.pipeline import RunContext
from halpha.text.text_event_history import write_text_event_history


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_data_export_help_mentions_bounded_exports(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["data", "export", "--help"])

    output = capsys.readouterr().out
    assert exc.value.code == 0
    assert "Export bounded local research data without bypassing query filters." in output
    assert "--as-of" in output
    assert "--identity" in output
    assert "--output" in output


def test_data_export_ohlcv_csv_cli_writes_bounded_export(tmp_path: Path, capsys) -> None:
    config_path = _write_market_config(tmp_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _ohlcv_record(open_time="2026-06-01T00:00:00Z", close=101),
            _ohlcv_record(open_time="2026-06-02T00:00:00Z", close=102),
            _ohlcv_record(open_time="2026-06-03T00:00:00Z", close=103),
        ]
    )

    exit_code = main(
        [
            "data",
            "export",
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
            "2026-06-04T00:00:00Z",
            "--as-of",
            "2026-06-03T12:00:00Z",
            "--format",
            "csv",
            "--output",
            str(tmp_path / "exports" / "ohlcv.csv"),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Halpha data export succeeded." in output
    assert "record_count: 2" in output
    assert "metadata: exports/ohlcv.csv.metadata.json" in output
    assert (tmp_path / "exports" / "ohlcv.csv").exists()
    metadata = _read_json(tmp_path / "exports" / "ohlcv.csv.metadata.json")
    assert metadata["query_parameters"]["as_of"] == "2026-06-03T12:00:00Z"
    assert metadata["record_count"] == 2


def test_data_export_text_event_json_cli_writes_embedded_metadata(tmp_path: Path, capsys) -> None:
    config_path = _write_text_config(tmp_path)
    run = _run_context(tmp_path, config_path, "run-1")
    write_text_event_history(
        {"text": {"enabled": True}},
        run,
        [
            _text_event(
                "btc-1",
                published_at="2026-06-01T00:30:00Z",
                collected_at="2026-06-01T00:31:00Z",
            )
        ],
        now="2026-06-02T00:00:00Z",
    )

    exit_code = main(
        [
            "data",
            "export",
            "--config",
            str(config_path),
            "--data-type",
            "text_event",
            "--source",
            "coindesk",
            "--start",
            "2026-06-01T00:00:00Z",
            "--end",
            "2026-06-02T00:00:00Z",
            "--format",
            "json",
            "--output",
            str(tmp_path / "exports" / "events.json"),
        ]
    )

    output = capsys.readouterr().out
    payload = _read_json(tmp_path / "exports" / "events.json")
    assert exit_code == 0
    assert "metadata: embedded" in output
    assert payload["metadata"]["data_type"] == "text_event"
    assert payload["metadata"]["record_count"] == 1
    assert payload["records"][0]["raw_item_id"] == "text:coindesk:btc-1"


def test_data_export_cli_uses_shared_service_boundary(
    tmp_path: Path,
    capsys,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_text_config(tmp_path)
    calls: list[dict[str, Any]] = []

    def fake_export(config: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {
            "schema_version": 1,
            "artifact_type": "data_export_result",
            "status": "ok",
            "data_type": kwargs["data_type"],
            "format": kwargs["output_format"],
            "output_path": "exports/events.csv",
            "metadata_path": "exports/events.csv.metadata.json",
            "record_count": 1,
            "matched_record_count": 1,
            "truncated": False,
            "query_parameters": {
                "start": kwargs["start"],
                "end": kwargs["end"],
                "as_of": kwargs["as_of"],
            },
            "coverage_diagnostics": {"status": "not_available", "record_count": 0},
            "warnings": [],
            "errors": [],
            "source_artifacts": ["data/research/metadata/collection_coverage_state.json"],
        }

    monkeypatch.setattr("halpha.cli.export_data", fake_export)

    exit_code = main(
        [
            "data",
            "export",
            "--config",
            str(config_path),
            "--data-type",
            "macro_calendar",
            "--source",
            "federal_reserve_fomc",
            "--identity",
            "data_class=central_bank_event",
            "--identity",
            "region=US",
            "--start",
            "2026-06-01T00:00:00Z",
            "--end",
            "2026-06-30T00:00:00Z",
            "--as-of",
            "2026-06-15T00:00:00Z",
            "--format",
            "csv",
            "--output",
            str(tmp_path / "exports" / "events.csv"),
            "--limit",
            "10",
            "--sort-order",
            "desc",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert calls[0]["data_type"] == "macro_calendar"
    assert calls[0]["source"] == "federal_reserve_fomc"
    assert calls[0]["identity"] == {"data_class": "central_bank_event", "region": "US"}
    assert calls[0]["as_of"] == "2026-06-15T00:00:00Z"
    assert calls[0]["limit"] == 10
    assert calls[0]["sort_order"] == "desc"
    assert "Halpha data export succeeded." in output


def test_data_export_cli_rejects_invalid_identity(tmp_path: Path, capsys) -> None:
    config_path = _write_text_config(tmp_path)

    exit_code = main(
        [
            "data",
            "export",
            "--config",
            str(config_path),
            "--data-type",
            "text_event",
            "--identity",
            "bad-identity",
            "--start",
            "2026-06-01T00:00:00Z",
            "--end",
            "2026-06-02T00:00:00Z",
            "--format",
            "json",
            "--output",
            str(tmp_path / "exports" / "events.json"),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "--identity must use KEY=VALUE." in output


def _write_market_config(tmp_path: Path) -> Path:
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


def _run_context(tmp_path: Path, config_path: Path, run_id: str) -> RunContext:
    run_dir = tmp_path / "runs" / run_id
    raw_dir = run_dir / "raw"
    analysis_dir = run_dir / "analysis"
    codex_context_dir = run_dir / "codex_context"
    report_dir = run_dir / "report"
    for directory in (raw_dir, analysis_dir, codex_context_dir, report_dir):
        directory.mkdir(parents=True, exist_ok=True)
    return RunContext(
        run_id=run_id,
        run_dir=run_dir,
        raw_dir=raw_dir,
        analysis_dir=analysis_dir,
        codex_context_dir=codex_context_dir,
        report_dir=report_dir,
        manifest_path=run_dir / "run_manifest.json",
        config_path=config_path,
        manifest={"artifacts": {}, "counts": {}, "errors": []},
    )


def _ohlcv_record(*, open_time: str, close: float) -> dict[str, Any]:
    return {
        "source": "binance",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "open_time": open_time,
        "open": close - 1,
        "high": close + 1,
        "low": close - 2,
        "close": close,
        "volume": 10,
        "fetched_at": "2026-06-05T00:00:00Z",
    }


def _text_event(raw_id: str, *, published_at: str, collected_at: str) -> dict[str, Any]:
    return {
        "event_id": f"text_event:coindesk:{raw_id}",
        "raw_item_id": f"text:coindesk:{raw_id}",
        "input_type": "rss_item",
        "source": {"name": "coindesk", "url": "https://example.com/coindesk/rss"},
        "title": f"Bitcoin market update {raw_id}",
        "content_text": f"Bitcoin market update content {raw_id}.",
        "link": f"https://example.com/coindesk/{raw_id}",
        "canonical_url": f"https://example.com/coindesk/{raw_id}",
        "published_at": published_at,
        "collected_at": collected_at,
        "language": "en",
        "normalized_title": f"bitcoin market update {raw_id}",
        "normalized_text": f"bitcoin market update content {raw_id}.",
        "warnings": [],
        "source_artifacts": ["raw/text_events.json"],
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
