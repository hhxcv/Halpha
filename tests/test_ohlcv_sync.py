from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from halpha.config import load_config
from halpha.market.ohlcv_source import OHLCVSourceError
from halpha.market.ohlcv_store import OHLCVParquetStore
from halpha.market.ohlcv_sync import sync_ohlcv_history
from halpha.pipeline import run_pipeline


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_sync_ohlcv_history_skips_when_ohlcv_is_not_configured(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, include_ohlcv=False)
    config = load_config(config_path)

    result = _run_pipeline_with_sync(config, config_path, _FailIfCalledSource())

    manifest = _manifest(result)
    assert result.succeeded is True
    assert manifest["ohlcv_sync"]["status"] == "skipped"
    assert manifest["ohlcv_sync"]["totals"] == {
        "items": 0,
        "fetched_count": 0,
        "stored_count": 0,
        "skipped_count": 0,
        "error_count": 0,
    }
    assert "ohlcv_sync_state" not in manifest["artifacts"]
    assert manifest["artifacts"]["research_data_catalog"] == (
        "data/research/metadata/research_data_catalog.json"
    )
    assert manifest["research_data_catalog"]["status"] == "skipped"
    assert manifest["counts"]["research_data_catalog_stores"] == 0
    assert _stage(manifest, "sync_ohlcv")["artifacts"] == [
        "data/research/metadata/research_data_catalog.json"
    ]


def test_sync_ohlcv_history_initial_backfill_stores_latest_lookback(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, lookback=2)
    config = load_config(config_path)
    source = _FakeSource(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=101),
            _record(open_time="2026-06-02T00:00:00Z", close=102),
            _record(open_time="2026-06-03T00:00:00Z", close=103),
        ]
    )

    result = _run_pipeline_with_sync(config, config_path, source)

    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    stored = store.read_records(source="binance", symbol="BTCUSDT", timeframe="1d")
    manifest = _manifest(result)
    item = manifest["ohlcv_sync"]["items"][0]

    assert result.succeeded is True
    assert source.calls == [
        {
            "symbol": "BTCUSDT",
            "timeframe": "1d",
            "since": None,
            "limit": 3,
            "now": "2026-06-05T00:00:00Z",
        }
    ]
    assert [record["open_time"] for record in stored] == [
        "2026-06-02T00:00:00Z",
        "2026-06-03T00:00:00Z",
    ]
    assert item["mode"] == "initial_backfill"
    assert item["fetched_count"] == 3
    assert item["stored_count"] == 2
    assert item["skipped_count"] == 1
    assert item["stored_range"] == {
        "earliest_open_time": "2026-06-02T00:00:00Z",
        "latest_open_time": "2026-06-03T00:00:00Z",
        "row_count": 2,
    }
    assert item["latest_closed_candle"] == "2026-06-03T00:00:00Z"
    assert manifest["artifacts"]["ohlcv_schema"] == "data/market/metadata/ohlcv_schema.json"
    assert manifest["artifacts"]["ohlcv_sync_state"] == "data/market/metadata/ohlcv_sync_state.json"
    assert manifest["artifacts"]["research_data_catalog"] == (
        "data/research/metadata/research_data_catalog.json"
    )
    assert manifest["research_data_catalog"]["status"] == "ok"
    assert manifest["counts"]["research_data_catalog_stores"] == 1
    assert (tmp_path / "data" / "market" / "metadata" / "ohlcv_sync_state.json").is_file()
    assert (tmp_path / "data" / "research" / "metadata" / "research_data_catalog.json").is_file()


def test_sync_ohlcv_history_incremental_fetches_from_next_missing_candle(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, lookback=2)
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records([_record(open_time="2026-06-01T00:00:00Z", close=101)])
    source = _FakeSource(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=101),
            _record(open_time="2026-06-02T00:00:00Z", close=102),
            _record(open_time="2026-06-03T00:00:00Z", close=103),
        ]
    )

    result = _run_pipeline_with_sync(config, config_path, source)

    stored = store.read_records(source="binance", symbol="BTCUSDT", timeframe="1d")
    manifest = _manifest(result)
    item = manifest["ohlcv_sync"]["items"][0]

    assert result.succeeded is True
    assert source.calls == [
        {
            "symbol": "BTCUSDT",
            "timeframe": "1d",
            "since": "2026-06-02T00:00:00Z",
            "limit": 3,
            "now": "2026-06-05T00:00:00Z",
        }
    ]
    assert [record["open_time"] for record in stored] == [
        "2026-06-01T00:00:00Z",
        "2026-06-02T00:00:00Z",
        "2026-06-03T00:00:00Z",
    ]
    assert item["mode"] == "incremental"
    assert item["existing_count"] == 1
    assert item["requested_since_open_time"] == "2026-06-02T00:00:00Z"
    assert item["fetched_count"] == 3
    assert item["stored_count"] == 2
    assert item["skipped_count"] == 1
    assert item["stored_range"]["row_count"] == 3


def test_sync_ohlcv_history_failure_preserves_existing_history_and_records_error(
    tmp_path: Path,
) -> None:
    config_path = _write_config(tmp_path, lookback=2)
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records([_record(open_time="2026-06-01T00:00:00Z", close=101)])
    source = _FailingSource(OHLCVSourceError("public OHLCV source request failed"))

    result = _run_pipeline_with_sync(config, config_path, source)

    stored = store.read_records(source="binance", symbol="BTCUSDT", timeframe="1d")
    manifest = _manifest(result)
    item = manifest["ohlcv_sync"]["items"][0]

    assert result.succeeded is False
    assert result.failed_stage == "sync_ohlcv"
    assert [record["open_time"] for record in stored] == ["2026-06-01T00:00:00Z"]
    assert manifest["ohlcv_sync"]["status"] == "failed"
    assert manifest["ohlcv_sync"]["totals"]["error_count"] == 1
    assert item["status"] == "failed"
    assert item["stored_range"] == {
        "earliest_open_time": "2026-06-01T00:00:00Z",
        "latest_open_time": "2026-06-01T00:00:00Z",
        "row_count": 1,
    }
    assert item["errors"][0]["message"] == "public OHLCV source request failed"
    stage = _stage(manifest, "sync_ohlcv")
    assert stage["status"] == "failed"
    assert stage["artifacts"] == [
        "data/market/metadata/ohlcv_schema.json",
        "data/market/metadata/ohlcv_sync_state.json",
        "data/research/metadata/research_data_catalog.json",
    ]
    assert manifest["research_data_catalog"]["status"] == "failed"


def _run_pipeline_with_sync(config: dict[str, Any], config_path: Path, source) -> Any:
    return run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={
            "collect_market_data": _noop_stage,
            "collect_text_events": _noop_stage,
            "sync_ohlcv": lambda config, run: sync_ohlcv_history(
                config,
                run,
                source_factory=lambda source_name, proxy_url: source,
                now="2026-06-05T00:00:00Z",
            ),
            "build_analysis_materials": _noop_stage,
            "build_research_context": _noop_stage,
            "build_codex_context": _noop_stage,
            "run_codex_report": _noop_stage,
        },
    )


def _write_config(tmp_path: Path, *, include_ohlcv: bool = True, lookback: int = 2) -> Path:
    ohlcv = ""
    if include_ohlcv:
        ohlcv = f"""
  ohlcv:
    storage_dir: data/market/ohlcv
    timeframes:
      - 1d
    lookback:
      1d: {lookback}
"""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
run:
  output_dir: runs
  timezone: Asia/Shanghai
market:
  enabled: true
  source: binance
  symbols:
    - BTCUSDT
{ohlcv.rstrip()}
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


def _manifest(result) -> dict[str, Any]:
    return json.loads(result.run.manifest_path.read_text(encoding="utf-8"))


def _stage(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    for stage in manifest["stages"]:
        if stage["name"] == name:
            return stage
        for task in stage.get("tasks", []):
            if task["name"] == name:
                return task
    raise AssertionError(f"stage or task {name} not found")


def _noop_stage(config, run) -> list[str]:
    return []


def _record(
    *,
    source: str = "binance",
    symbol: str = "BTCUSDT",
    timeframe: str = "1d",
    open_time: str,
    close: float,
) -> dict[str, object]:
    return {
        "source": source,
        "symbol": symbol,
        "timeframe": timeframe,
        "open_time": open_time,
        "open": close - 1,
        "high": close + 1,
        "low": close - 2,
        "close": close,
        "volume": 10,
        "fetched_at": "2026-06-05T00:00:00Z",
    }


def _format_since(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return value


class _FakeSource:
    def __init__(self, records: list[dict[str, object]]) -> None:
        self.records = records
        self.calls: list[dict[str, object]] = []

    def fetch_records(
        self,
        *,
        symbol: str,
        timeframe: str,
        since: datetime | str | None = None,
        limit: int | None = None,
        now: datetime | str | None = None,
    ) -> list[dict[str, object]]:
        self.calls.append(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "since": _format_since(since),
                "limit": limit,
                "now": _format_since(now),
            }
        )
        return list(self.records)


class _FailingSource(_FakeSource):
    def __init__(self, error: Exception) -> None:
        super().__init__([])
        self.error = error

    def fetch_records(
        self,
        *,
        symbol: str,
        timeframe: str,
        since: datetime | str | None = None,
        limit: int | None = None,
        now: datetime | str | None = None,
    ) -> list[dict[str, object]]:
        self.calls.append(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "since": _format_since(since),
                "limit": limit,
                "now": _format_since(now),
            }
        )
        raise self.error


class _FailIfCalledSource(_FakeSource):
    def __init__(self) -> None:
        super().__init__([])

    def fetch_records(self, **kwargs) -> list[dict[str, object]]:
        raise AssertionError("source should not be called without market.ohlcv")
