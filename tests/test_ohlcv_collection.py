from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from halpha.config import load_config
from halpha.data.collection_coverage import read_collection_coverage_state, write_collection_coverage_state
from halpha.market.ohlcv_collection import collect_ohlcv_data
from halpha.market.ohlcv_source import OHLCVSourceError
from halpha.market.ohlcv_store import OHLCVParquetStore


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_ohlcv_collection_dry_run_plans_without_network_or_writes(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = collect_ohlcv_data(
        config,
        config_path=config_path,
        source="binance",
        symbol="BTCUSDT",
        timeframe="1d",
        requested_start="2026-06-01T00:00:00Z",
        requested_end="2026-06-03T00:00:00Z",
        dry_run=True,
        source_factory=lambda source, proxy_url: _FailIfCalledSource(),
        now="2026-06-05T00:00:00Z",
    )

    assert result["mode"] == "dry_run"
    assert result["status"] == "ok"
    assert result["plan"]["strategy"] == "gap_only"
    assert result["counts"]["planned_fetch_windows"] == 1
    assert result["fetches"] == []
    assert result["artifacts"] == {}
    assert not (tmp_path / "data").exists()


def test_ohlcv_collection_apply_writes_store_coverage_and_catalog(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    source = _FakeSource(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=101),
            _record(open_time="2026-06-02T00:00:00Z", close=102),
        ]
    )

    result = _collect(config, config_path, source)

    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    stored = store.read_records(source="binance", symbol="BTCUSDT", timeframe="1d")
    coverage = read_collection_coverage_state(config_path)
    catalog = json.loads((tmp_path / "data" / "research" / "metadata" / "research_data_catalog.json").read_text())

    assert result["status"] == "ok"
    assert result["counts"]["fetched_records"] == 2
    assert result["counts"]["window_records"] == 2
    assert result["counts"]["stored_records"] == 2
    assert source.calls == [
        {
            "symbol": "BTCUSDT",
            "timeframe": "1d",
            "since": "2026-06-01T00:00:00Z",
            "limit": 3,
            "now": "2026-06-05T00:00:00Z",
        }
    ]
    assert [record["open_time"] for record in stored] == [
        "2026-06-01T00:00:00Z",
        "2026-06-02T00:00:00Z",
    ]
    assert coverage["records"][0]["status"] == "collected"
    assert coverage["records"][0]["range_start"] == "2026-06-01T00:00:00Z"
    assert coverage["records"][0]["range_end"] == "2026-06-03T00:00:00Z"
    assert catalog["stores"][0]["name"] == "ohlcv_history"
    assert catalog["stores"][0]["coverage_state"]["status_counts"] == {"collected": 1}


def test_ohlcv_collection_repeated_dry_run_skips_completed_interval(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    _collect(
        config,
        config_path,
        _FakeSource(
            [
                _record(open_time="2026-06-01T00:00:00Z", close=101),
                _record(open_time="2026-06-02T00:00:00Z", close=102),
            ]
        ),
    )

    result = collect_ohlcv_data(
        config,
        config_path=config_path,
        source="binance",
        symbol="BTCUSDT",
        timeframe="1d",
        requested_start="2026-06-01T00:00:00Z",
        requested_end="2026-06-03T00:00:00Z",
        dry_run=True,
        source_factory=lambda source, proxy_url: _FailIfCalledSource(),
        now="2026-06-05T00:00:00Z",
    )

    assert result["plan"]["strategy"] == "no_work"
    assert result["counts"]["skipped_ranges"] == 1
    assert result["counts"]["planned_fetch_windows"] == 0


def test_ohlcv_collection_backfills_middle_gap_without_discarding_surrounding_data(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _record(open_time="2026-06-01T00:00:00Z", close=101),
            _record(open_time="2026-06-03T00:00:00Z", close=103),
        ]
    )
    write_collection_coverage_state(
        config_path,
        [
            _coverage_record("2026-06-01T00:00:00Z", "2026-06-02T00:00:00Z", status="collected"),
            _coverage_record("2026-06-03T00:00:00Z", "2026-06-04T00:00:00Z", status="collected"),
        ],
        now="2026-06-05T00:00:00Z",
    )

    result = collect_ohlcv_data(
        config,
        config_path=config_path,
        source="binance",
        symbol="BTCUSDT",
        timeframe="1d",
        requested_start="2026-06-01T00:00:00Z",
        requested_end="2026-06-04T00:00:00Z",
        dry_run=False,
        source_factory=lambda source, proxy_url: _FakeSource([_record(open_time="2026-06-02T00:00:00Z", close=102)]),
        now="2026-06-05T00:00:00Z",
    )

    stored = store.read_records(source="binance", symbol="BTCUSDT", timeframe="1d")
    assert result["status"] == "ok"
    assert result["plan"]["gap_ranges"] == [
        {
            "range_start": "2026-06-02T00:00:00Z",
            "range_end": "2026-06-03T00:00:00Z",
            "status": "unknown",
        }
    ]
    assert [(record["open_time"], record["close"]) for record in stored] == [
        ("2026-06-01T00:00:00Z", 101.0),
        ("2026-06-02T00:00:00Z", 102.0),
        ("2026-06-03T00:00:00Z", 103.0),
    ]


def test_ohlcv_collection_empty_success_records_no_data(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = _collect(config, config_path, _FakeSource([]), end="2026-06-02T00:00:00Z")

    coverage = read_collection_coverage_state(config_path)
    assert result["status"] == "ok"
    assert result["fetches"][0]["status"] == "no_data"
    assert coverage["records"][0]["status"] == "no_data"
    assert coverage["records"][0]["record_count"] == 0


def test_ohlcv_collection_partial_success_records_partial_coverage(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = _collect(
        config,
        config_path,
        _FakeSource([_record(open_time="2026-06-01T00:00:00Z", close=101)]),
    )

    coverage = read_collection_coverage_state(config_path)
    assert result["status"] == "warning"
    assert result["fetches"][0]["status"] == "partial"
    assert coverage["records"][0]["status"] == "partial"
    assert coverage["records"][0]["warnings"]


def test_ohlcv_collection_failed_fetch_records_failed_coverage(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    source = _FailingSource(OHLCVSourceError("public OHLCV source request failed"))

    result = _collect(config, config_path, source)

    coverage = read_collection_coverage_state(config_path)
    assert result["status"] == "failed"
    assert result["fetches"][0]["status"] == "failed"
    assert coverage["records"][0]["status"] == "failed"
    assert coverage["records"][0]["errors"][0]["message"] == "public OHLCV source request failed"


def test_ohlcv_collection_source_initialization_failure_records_failed_coverage(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def fail_source_factory(source: str, proxy_url: str | None) -> _FakeSource:
        raise OHLCVSourceError("source initialization failed")

    result = collect_ohlcv_data(
        config,
        config_path=config_path,
        source="binance",
        symbol="BTCUSDT",
        timeframe="1d",
        requested_start="2026-06-01T00:00:00Z",
        requested_end="2026-06-03T00:00:00Z",
        dry_run=False,
        source_factory=fail_source_factory,
        now="2026-06-05T00:00:00Z",
    )

    coverage = read_collection_coverage_state(config_path)
    assert result["status"] == "failed"
    assert result["fetches"] == []
    assert result["errors"][0]["message"] == "source initialization failed"
    assert coverage["records"][0]["status"] == "failed"
    assert coverage["records"][0]["errors"][0]["message"] == "source initialization failed"


def test_ohlcv_collection_conflict_preserves_existing_history_and_records_failure(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records([_record(open_time="2026-06-01T00:00:00Z", close=101)])
    write_collection_coverage_state(
        config_path,
        [_coverage_record("2026-06-01T00:00:00Z", "2026-06-02T00:00:00Z", status="not_collected")],
        now="2026-06-05T00:00:00Z",
    )

    result = collect_ohlcv_data(
        config,
        config_path=config_path,
        source="binance",
        symbol="BTCUSDT",
        timeframe="1d",
        requested_start="2026-06-01T00:00:00Z",
        requested_end="2026-06-02T00:00:00Z",
        dry_run=False,
        source_factory=lambda source, proxy_url: _FakeSource([_record(open_time="2026-06-01T00:00:00Z", close=102)]),
        now="2026-06-05T00:00:00Z",
    )

    stored = store.read_records(source="binance", symbol="BTCUSDT", timeframe="1d")
    coverage = read_collection_coverage_state(config_path)
    assert result["status"] == "failed"
    assert [record["close"] for record in stored] == [101.0]
    assert coverage["records"][-1]["status"] == "failed"
    assert "conflicting values" in coverage["records"][-1]["errors"][0]["message"]


def test_ohlcv_collection_blocked_plan_records_failed_diagnostics_without_fetching(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = collect_ohlcv_data(
        config,
        config_path=config_path,
        source="binance",
        symbol="BTCUSDT",
        timeframe="1d",
        requested_start="2026-06-01T00:00:00Z",
        requested_end="2026-06-03T00:00:00Z",
        dry_run=False,
        source_factory=lambda source, proxy_url: _FailIfCalledSource(),
        supports_historical=False,
        now="2026-06-05T00:00:00Z",
    )

    coverage = read_collection_coverage_state(config_path)
    assert result["status"] == "blocked"
    assert result["plan"]["planned_fetch_windows"] == []
    assert coverage["records"][0]["status"] == "failed"
    assert "does not support historical collection" in coverage["records"][0]["errors"][0]["message"]


def _collect(
    config: dict[str, Any],
    config_path: Path,
    source: Any,
    *,
    end: str = "2026-06-03T00:00:00Z",
) -> dict[str, Any]:
    return collect_ohlcv_data(
        config,
        config_path=config_path,
        source="binance",
        symbol="BTCUSDT",
        timeframe="1d",
        requested_start="2026-06-01T00:00:00Z",
        requested_end=end,
        dry_run=False,
        source_factory=lambda source_name, proxy_url: source,
        now="2026-06-05T00:00:00Z",
    )


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


def _coverage_record(start: str, end: str, *, status: str) -> dict[str, object]:
    return {
        "data_type": "ohlcv",
        "source": "binance",
        "identity": {"symbol": "BTCUSDT", "timeframe": "1d"},
        "range_start": start,
        "range_end": end,
        "status": status,
        "record_count": 1 if status == "collected" else 0,
        "attempt_count": 1,
        "latest_attempt_at": end,
        "latest_success_at": end if status == "collected" else None,
        "updated_at": end,
        "coverage_method": "explicit",
        "source_artifacts": ["data/market/metadata/ohlcv_sync_state.json"],
        "warnings": [],
        "errors": [],
    }


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
        raise AssertionError("source should not be called")
