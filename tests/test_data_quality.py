from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from halpha.config import load_config
from halpha.data_quality import build_data_quality_summary
from halpha.pipeline import RunContext, run_pipeline
from halpha.storage import write_json


def test_data_quality_summary_records_clean_current_run_state(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, include_ohlcv=False)
    config = load_config(config_path)
    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="build_data_quality_summary",
        stage_handlers={
            "collect_market_data": _write_market_raw,
            "collect_text_events": _write_text_raw,
            "sync_ohlcv": _noop_stage,
            "build_market_data_views": _noop_stage,
        },
    )

    assert result.succeeded is True
    summary = _summary(result.run.analysis_dir)
    manifest = _manifest(result.run.manifest_path)

    assert summary["artifact_type"] == "data_quality_summary"
    assert summary["status"] == "ok"
    assert summary["counts"]["checks"] == 8
    assert summary["counts"]["failed"] == 0
    assert summary["counts"]["degraded"] == 0
    assert manifest["artifacts"]["data_quality_summary"] == "analysis/data_quality_summary.json"
    assert manifest["data_quality_summary"]["status"] == "ok"
    assert _check(summary, "raw_market")["status"] == "ok"
    assert _check(summary, "raw_text")["status"] == "ok"
    assert _check(summary, "ohlcv_store")["status"] == "skipped"
    assert _check(summary, "text_event_history")["status"] == "ok"
    run_index = _check(summary, "run_index")
    assert run_index["status"] == "skipped"
    assert "terminal artifact written after the data-quality stage" in run_index["summary"]
    assert run_index["details"]["stage_time_skip_is_expected"] is True
    assert run_index["details"]["report_as_final_missing"] is False


def test_data_quality_summary_flags_schema_drift_future_timestamp_and_duplicates(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    run = _run_context(tmp_path, config_path)
    write_json(
        run.raw_dir / "market.json",
        {
            "items": [
                {
                    "id": "market:binance:BTCUSDT:future",
                    "symbol": "BTCUSDT",
                    "as_of": "2026-06-06T00:00:00Z",
                    "source": {"name": "binance"},
                }
            ],
            "errors": [],
        },
    )
    write_json(
        run.raw_dir / "text_events.json",
        {"items": [{"id": "broken", "title": "Broken", "source": {"name": "coindesk"}}], "errors": []},
    )
    write_json(
        run.analysis_dir / "text_event_records.json",
        {
            "records": [
                _event_record("one", canonical_url="https://example.com/a", text="one"),
                _event_record("two", canonical_url="https://example.com/a", text="two"),
            ]
        },
    )

    build_data_quality_summary(_config(), run, now="2026-06-05T00:00:00Z")

    summary = _summary(run.analysis_dir)
    assert summary["status"] == "failed"
    assert _check(summary, "raw_market")["status"] == "warning"
    assert "is in the future" in _check(summary, "raw_market")["details"]["warnings"][0]
    assert _check(summary, "raw_text")["status"] == "failed"
    assert "content_text is required" in _check(summary, "raw_text")["details"]["errors"][0]
    text_records = _check(summary, "text_event_records")
    assert text_records["status"] == "warning"
    assert text_records["details"]["duplicate_records"] == 1
    assert text_records["details"]["conflicting_duplicates"] == 1


def test_data_quality_summary_records_partial_collection_and_optional_skips(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, include_ohlcv=False)
    run = _run_context(tmp_path, config_path)
    write_json(
        run.raw_dir / "market.json",
        {
            "items": [
                {
                    "id": "market:binance:BTCUSDT:now",
                    "symbol": "BTCUSDT",
                    "as_of": "2026-06-05T00:00:00Z",
                    "source": {"name": "binance"},
                }
            ],
            "errors": [{"message": "one market source failed"}],
        },
    )
    run.manifest["artifacts"]["raw_market"] = "raw/market.json"

    build_data_quality_summary(_config(include_ohlcv=False, text_enabled=False), run, now="2026-06-05T00:00:00Z")

    summary = _summary(run.analysis_dir)
    assert summary["status"] == "degraded"
    assert _check(summary, "raw_text")["status"] == "skipped"
    assert _check(summary, "ohlcv_store")["status"] == "skipped"
    assert _check(summary, "partial_collection")["status"] == "degraded"


def _write_config(tmp_path: Path, *, include_ohlcv: bool = True) -> Path:
    ohlcv = ""
    if include_ohlcv:
        ohlcv = """
  ohlcv:
    storage_dir: data/market/ohlcv
    timeframes:
      - 1d
    lookback:
      1d: 2
"""
    path = tmp_path / "config.yaml"
    path.write_text(
        f"""
run:
  output_dir: runs
market:
  enabled: true
  source: binance
  symbols:
    - BTCUSDT
{ohlcv.rstrip()}
text:
  enabled: true
  max_items: 1
  sources:
    - name: coindesk
      type: rss
      url: https://example.com/rss.xml
report:
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return path


def _config(*, include_ohlcv: bool = True, text_enabled: bool = True) -> dict[str, Any]:
    market: dict[str, Any] = {
        "enabled": True,
        "source": "binance",
        "symbols": ["BTCUSDT"],
    }
    if include_ohlcv:
        market["ohlcv"] = {"storage_dir": "data/market/ohlcv", "timeframes": ["1d"], "lookback": {"1d": 2}}
    return {
        "market": market,
        "text": {"enabled": text_enabled},
    }


def _run_context(tmp_path: Path, config_path: Path) -> RunContext:
    run_dir = tmp_path / "runs" / "run-1"
    raw_dir = run_dir / "raw"
    analysis_dir = run_dir / "analysis"
    codex_context_dir = run_dir / "codex_context"
    report_dir = run_dir / "report"
    for directory in (raw_dir, analysis_dir, codex_context_dir, report_dir):
        directory.mkdir(parents=True, exist_ok=True)
    return RunContext(
        run_id="run-1",
        run_dir=run_dir,
        raw_dir=raw_dir,
        analysis_dir=analysis_dir,
        codex_context_dir=codex_context_dir,
        report_dir=report_dir,
        manifest_path=run_dir / "run_manifest.json",
        config_path=config_path,
        manifest={"artifacts": {}, "counts": {}, "errors": []},
    )


def _write_market_raw(config, run) -> list[str]:
    write_json(
        run.raw_dir / "market.json",
        {
            "items": [
                {
                    "id": "market:binance:BTCUSDT:now",
                    "symbol": "BTCUSDT",
                    "as_of": "2026-06-05T00:00:00Z",
                    "source": {"name": "binance"},
                }
            ],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["raw_market"] = "raw/market.json"
    return ["raw/market.json"]


def _write_text_raw(config, run) -> list[str]:
    write_json(
        run.raw_dir / "text_events.json",
        {
            "collected_at": "2026-06-05T00:00:00Z",
            "items": [
                {
                    "id": "text:coindesk:event-1",
                    "type": "rss_item",
                    "title": "Bitcoin market event",
                    "published_at": "2026-06-05T00:00:00Z",
                    "source": {"name": "coindesk", "url": "https://example.com/rss.xml"},
                    "link": "https://example.com/bitcoin",
                    "content_text": "Bitcoin event.",
                    "language": "en",
                }
            ],
            "errors": [],
        },
    )
    run.manifest["artifacts"]["raw_text_events"] = "raw/text_events.json"
    return ["raw/text_events.json"]


def _event_record(raw_id: str, *, canonical_url: str, text: str) -> dict[str, Any]:
    return {
        "event_id": f"text_event:coindesk:{raw_id}",
        "raw_item_id": f"text:coindesk:{raw_id}",
        "canonical_url": canonical_url,
        "published_at": "2026-06-05T00:00:00Z",
        "collected_at": "2026-06-05T00:00:00Z",
        "normalized_text": text,
        "warnings": [],
    }


def _noop_stage(config, run) -> list[str]:
    return []


def _summary(analysis_dir: Path) -> dict[str, Any]:
    return json.loads((analysis_dir / "data_quality_summary.json").read_text(encoding="utf-8"))


def _manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _check(summary: dict[str, Any], name: str) -> dict[str, Any]:
    return next(check for check in summary["checks"] if check["name"] == name)
