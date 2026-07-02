from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from typing import Any

import pytest

from halpha.config import load_config
from halpha.live.contracts import LIVE_DATA_TYPES
from halpha.live.scheduler import LiveScheduler
from halpha.live.state_store import LiveCollectionStateRepository, LiveTriggerStateRepository
from halpha.live.stream_state import LiveStreamStateRepository
from halpha.runtime.mutation_lease import LEASE_BLOCKED_MESSAGE


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_live_scheduler_skips_when_live_is_not_enabled(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, live_block="")
    config = load_config(config_path)
    jobs = _RecordingLiveJobManager()

    tick = LiveScheduler(config, config_path=config_path, job_manager=jobs).tick(tick_id="tick-1")

    assert tick["status"] == "skipped"
    assert tick["enabled"] is False
    assert {state["data_type"] for state in tick["collections"]} == set(LIVE_DATA_TYPES)
    assert jobs.created_requests == []


def test_live_scheduler_creates_due_ohlcv_collection_job(tmp_path: Path) -> None:
    now = datetime(2026, 6, 30, 12, 0, 30, tzinfo=timezone.utc)
    config_path = _write_config(
        tmp_path,
        live_block="""
live:
  enabled: true
  tick_seconds: 15
  collections:
    ohlcv:
      enabled: true
      cadence_seconds: 300
      lookback_seconds: 3600
""",
    )
    config = load_config(config_path)
    jobs = _RecordingLiveJobManager()

    tick = LiveScheduler(config, config_path=config_path, job_manager=jobs, now=now).tick(tick_id="tick-1")

    assert tick["status"] == "available"
    assert len(jobs.created_requests) == 1
    request = jobs.created_requests[0]
    assert request["intent"] == "data_collect"
    assert request["requested_by"] == "Core"
    assert request["requester"] == {
        "source": "live_scheduler",
        "tick_id": "tick-1",
        "data_type": "ohlcv",
        "target_key": "ohlcv:binance_usdm:BTCUSDT:1m",
    }
    assert request["params"] == {
        "data_type": "ohlcv",
        "source": "binance_usdm",
        "symbol": "BTCUSDT",
        "timeframe": "1m",
        "start": "2026-06-30T11:00:00Z",
        "end": "2026-06-30T12:00:00Z",
    }


def test_live_scheduler_skips_rest_ohlcv_when_websocket_stream_is_fresh(tmp_path: Path) -> None:
    now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    config_path = _write_config(
        tmp_path,
        live_block="""
live:
  enabled: true
  collections:
    ohlcv:
      enabled: true
      cadence_seconds: 300
      lookback_seconds: 3600
  streams:
    ohlcv:
      enabled: true
      stale_after_seconds: 180
""",
    )
    config = load_config(config_path)
    stream_repository = LiveStreamStateRepository(config_path)
    stream_repository.upsert_state(
        {
            "target_key": "ohlcv:binance_usdm:BTCUSDT:1m",
            "data_type": "ohlcv",
            "target": {"data_type": "ohlcv", "source": "binance_usdm", "symbol": "BTCUSDT", "timeframe": "1m"},
            "enabled": True,
            "status": "available",
            "stream_name": "btcusdt@kline_1m",
            "endpoint": "binance_usdm_market_stream",
            "connected_at": "2026-06-30T11:55:00Z",
            "last_event_at": "2026-06-30T11:59:50Z",
            "last_closed_candle_at": "2026-06-30T11:59:00Z",
            "backfill_required": False,
            "updated_at": "2026-06-30T11:59:50Z",
        }
    )
    jobs = _RecordingLiveJobManager()

    tick = LiveScheduler(
        config,
        config_path=config_path,
        job_manager=jobs,
        stream_state_repository=stream_repository,
        now=now,
    ).tick(tick_id="tick-1")

    assert tick["status"] == "available"
    assert jobs.created_requests == []
    state = _collection_state(tick, "ohlcv:binance_usdm:BTCUSDT:1m")
    assert state["transport"] == "websocket"
    assert state["stream"]["status"] == "available"
    assert state["next_attempt_at"] == "2026-06-30T12:03:00Z"


def test_live_scheduler_runs_rest_backfill_when_websocket_stream_requires_it(tmp_path: Path) -> None:
    now = datetime(2026, 6, 30, 12, 0, 30, tzinfo=timezone.utc)
    config_path = _write_config(
        tmp_path,
        live_block="""
live:
  enabled: true
  collections:
    ohlcv:
      enabled: true
      cadence_seconds: 300
      lookback_seconds: 3600
  streams:
    ohlcv:
      enabled: true
      stale_after_seconds: 180
""",
    )
    config = load_config(config_path)
    stream_repository = LiveStreamStateRepository(config_path)
    stream_repository.upsert_state(
        {
            "target_key": "ohlcv:binance_usdm:BTCUSDT:1m",
            "data_type": "ohlcv",
            "target": {"data_type": "ohlcv", "source": "binance_usdm", "symbol": "BTCUSDT", "timeframe": "1m"},
            "enabled": True,
            "status": "reconnecting",
            "stream_name": "btcusdt@kline_1m",
            "backfill_required": True,
            "backfill_since": "2026-06-30T11:57:00Z",
            "updated_at": "2026-06-30T11:59:00Z",
        }
    )
    jobs = _RecordingLiveJobManager()

    LiveScheduler(
        config,
        config_path=config_path,
        job_manager=jobs,
        stream_state_repository=stream_repository,
        now=now,
    ).tick(tick_id="tick-1")

    assert len(jobs.created_requests) == 1
    assert jobs.created_requests[0]["params"] == {
        "data_type": "ohlcv",
        "source": "binance_usdm",
        "symbol": "BTCUSDT",
        "timeframe": "1m",
        "start": "2026-06-30T11:57:00Z",
        "end": "2026-06-30T12:00:00Z",
    }


def test_live_scheduler_monthly_backfill_falls_back_to_aligned_previous_month(tmp_path: Path) -> None:
    now = datetime(2026, 7, 2, 12, 0, 30, tzinfo=timezone.utc)
    config_path = _write_config(
        tmp_path,
        live_block="""
live:
  enabled: true
  collections:
    ohlcv:
      enabled: true
      cadence_seconds: 300
      lookback_seconds: 3600
  streams:
    ohlcv:
      enabled: true
      stale_after_seconds: 180
""",
    )
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "    timeframes:\n      - 1m\n    lookback:\n      1m: 30",
            "    timeframes:\n      - 1M\n    lookback:\n      1M: 30",
        ),
        encoding="utf-8",
    )
    config = load_config(config_path)
    stream_repository = LiveStreamStateRepository(config_path)
    stream_repository.upsert_state(
        {
            "target_key": "ohlcv:binance_usdm:BTCUSDT:1M",
            "data_type": "ohlcv",
            "target": {"data_type": "ohlcv", "source": "binance_usdm", "symbol": "BTCUSDT", "timeframe": "1M"},
            "enabled": True,
            "status": "reconnecting",
            "stream_name": "btcusdt@kline_1M",
            "backfill_required": True,
            "backfill_since": "2026-07-02T11:59:00Z",
            "updated_at": "2026-07-02T11:59:00Z",
        }
    )
    jobs = _RecordingLiveJobManager()

    LiveScheduler(
        config,
        config_path=config_path,
        job_manager=jobs,
        stream_state_repository=stream_repository,
        now=now,
    ).tick(tick_id="tick-1")

    assert len(jobs.created_requests) == 1
    assert jobs.created_requests[0]["params"] == {
        "data_type": "ohlcv",
        "source": "binance_usdm",
        "symbol": "BTCUSDT",
        "timeframe": "1M",
        "start": "2026-06-01T00:00:00Z",
        "end": "2026-07-01T00:00:00Z",
    }


def test_live_read_model_filters_recoverable_stream_backfill_errors(tmp_path: Path) -> None:
    now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    config_path = _write_config(
        tmp_path,
        live_block="""
live:
  enabled: true
  collections:
    ohlcv:
      enabled: true
      cadence_seconds: 300
      lookback_seconds: 3600
  streams:
    ohlcv:
      enabled: true
      stale_after_seconds: 180
""",
    )
    config = load_config(config_path)
    stream_repository = LiveStreamStateRepository(config_path)
    stream_repository.upsert_state(
        {
            "target_key": "ohlcv:binance_usdm:BTCUSDT:1m",
            "data_type": "ohlcv",
            "target": {"data_type": "ohlcv", "source": "binance_usdm", "symbol": "BTCUSDT", "timeframe": "1m"},
            "enabled": True,
            "status": "streaming",
            "stream_name": "btcusdt@kline_1m",
            "last_event_at": "2026-06-30T11:59:50Z",
            "backfill_required": True,
            "backfill_since": "2026-06-30T11:57:00Z",
            "updated_at": "2026-06-30T11:59:50Z",
        }
    )
    jobs = _RecordingLiveJobManager(
        jobs=[
            _live_job(
                "collect-1",
                status="failed",
                target_key="ohlcv:binance_usdm:BTCUSDT:1m",
                data_type="ohlcv",
                created_at="2026-06-30T11:59:55Z",
                errors=[
                    "requested_start must align to the 1m UTC timeframe boundary.",
                    "job process identity was lost after the owning runtime restarted; the recorded PID was not treated as proof of the original job.",
                ],
            )
        ]
    )

    payload = LiveScheduler(
        config,
        config_path=config_path,
        job_manager=jobs,
        stream_state_repository=stream_repository,
        now=now,
    ).read_model()
    state = _collection_state(payload, "ohlcv:binance_usdm:BTCUSDT:1m")

    assert payload["status"] == "available"
    assert payload["errors"] == []
    assert state["errors"] == []
    assert state["stream"]["backfill_required"] is True
    assert "REST backfill will run" in state["warnings"][0]


def test_live_scheduler_suppresses_duplicate_transient_collection_target(tmp_path: Path) -> None:
    now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    config_path = _write_config(
        tmp_path,
        live_block="""
live:
  enabled: true
  collections:
    text_event:
      enabled: true
      cadence_seconds: 300
      lookback_seconds: 3600
""",
    )
    config = load_config(config_path)
    jobs = _RecordingLiveJobManager(
        jobs=[
            _live_job(
                "job-running",
                status="running",
                target_key="text_event:all",
                data_type="text_event",
                created_at="2026-06-30T11:59:00Z",
            )
        ]
    )

    tick = LiveScheduler(config, config_path=config_path, job_manager=jobs, now=now).tick(tick_id="tick-1")

    assert tick["status"] == "available"
    assert jobs.created_requests == []
    state = _collection_state(tick, "text_event:all")
    assert state["target_key"] == "text_event:all"
    assert state["latest_job_id"] == "job-running"
    assert state["latest_job_status"] == "running"


def test_live_scheduler_defers_collection_while_mutating_job_is_running(tmp_path: Path) -> None:
    now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    config_path = _write_config(
        tmp_path,
        live_block="""
live:
  enabled: true
  tick_seconds: 15
  collections:
    text_event:
      enabled: true
      cadence_seconds: 300
      lookback_seconds: 3600
""",
    )
    config = load_config(config_path)
    jobs = _RecordingLiveJobManager(
        jobs=[
            _command_job(
                "monitor-running",
                intent="monitor_once",
                kind="monitor_cycle",
                status="running",
                created_at="2026-06-30T11:59:50Z",
            )
        ]
    )

    tick = LiveScheduler(config, config_path=config_path, job_manager=jobs, now=now).tick(tick_id="tick-1")

    assert tick["status"] == "available"
    assert tick["errors"] == []
    assert jobs.created_requests == []
    state = _collection_state(tick, "text_event:all")
    assert state["latest_job_id"] is None
    assert state["latest_job_status"] is None
    assert state["next_attempt_at"] == "2026-06-30T12:01:00Z"
    assert state["consecutive_failures"] == 0


def test_live_scheduler_globally_throttles_recent_collection_dispatch(tmp_path: Path) -> None:
    now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    config_path = _write_config(
        tmp_path,
        live_block="""
live:
  enabled: true
  tick_seconds: 15
  collections:
    text_event:
      enabled: true
      cadence_seconds: 300
      lookback_seconds: 3600
    macro_calendar:
      enabled: true
      cadence_seconds: 3600
      lookback_seconds: 86400
      lookahead_seconds: 604800
""",
    )
    config = load_config(config_path)
    jobs = _RecordingLiveJobManager(
        jobs=[
            _live_job(
                "collect-recent",
                status="succeeded",
                target_key="text_event:all",
                data_type="text_event",
                created_at="2026-06-30T11:59:30Z",
            )
        ]
    )

    tick = LiveScheduler(config, config_path=config_path, job_manager=jobs, now=now).tick(tick_id="tick-1")

    assert tick["status"] == "available"
    assert jobs.created_requests == []
    assert _collection_state(tick, "text_event:all")["next_attempt_at"] == "2026-06-30T12:00:30Z"
    assert _collection_state(tick, "macro_calendar:configured")["next_attempt_at"] == "2026-06-30T12:01:30Z"


def test_live_scheduler_treats_mutation_lease_blocked_collection_as_deferred(tmp_path: Path) -> None:
    now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    config_path = _write_config(
        tmp_path,
        live_block="""
live:
  enabled: true
  collections:
    text_event:
      enabled: true
      cadence_seconds: 300
      lookback_seconds: 3600
""",
    )
    config = load_config(config_path)
    jobs = _RecordingLiveJobManager(create_status="blocked", create_errors=[LEASE_BLOCKED_MESSAGE])

    tick = LiveScheduler(config, config_path=config_path, job_manager=jobs, now=now).tick(tick_id="tick-1")

    assert tick["status"] == "available"
    assert tick["errors"] == []
    assert len(jobs.created_requests) == 1
    state = _collection_state(tick, "text_event:all")
    assert state["latest_job_status"] == "blocked"
    assert state["latest_terminal_status"] == "deferred"
    assert state["consecutive_failures"] == 0
    assert state["errors"] == []


def test_live_scheduler_uses_macro_calendar_lookahead_window(tmp_path: Path) -> None:
    now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    config_path = _write_config(
        tmp_path,
        live_block="""
live:
  enabled: true
  collections:
    macro_calendar:
      enabled: true
      cadence_seconds: 3600
      lookback_seconds: 86400
      lookahead_seconds: 604800
""",
    )
    config = load_config(config_path)
    jobs = _RecordingLiveJobManager()

    LiveScheduler(config, config_path=config_path, job_manager=jobs, now=now).tick(tick_id="tick-1")

    request = jobs.created_requests[0]
    assert request["requester"]["target_key"] == "macro_calendar:configured"
    assert request["params"] == {
        "data_type": "macro_calendar",
        "start": "2026-06-29T12:00:00Z",
        "end": "2026-07-07T12:00:00Z",
    }


def test_live_scheduler_respects_next_attempt_cadence(tmp_path: Path) -> None:
    start = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    config_path = _write_config(
        tmp_path,
        live_block="""
live:
  enabled: true
  collections:
    text_event:
      enabled: true
      cadence_seconds: 300
      lookback_seconds: 3600
""",
    )
    config = load_config(config_path)
    repository = LiveCollectionStateRepository(config_path)
    jobs = _RecordingLiveJobManager(create_status="succeeded")

    first = LiveScheduler(
        config,
        config_path=config_path,
        job_manager=jobs,
        state_repository=repository,
        now=start,
    ).tick(tick_id="tick-1")
    second = LiveScheduler(
        config,
        config_path=config_path,
        job_manager=jobs,
        state_repository=repository,
        now=start + timedelta(seconds=60),
    ).tick(tick_id="tick-2")

    assert len(jobs.created_requests) == 1
    assert _collection_state(first, "text_event:all")["next_attempt_at"] == "2026-06-30T12:05:00Z"
    assert _collection_state(second, "text_event:all")["next_attempt_at"] == "2026-06-30T12:05:00Z"


def test_live_scheduler_reconciles_terminal_failure_once(tmp_path: Path) -> None:
    start = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    config_path = _write_config(
        tmp_path,
        live_block="""
live:
  enabled: true
  collections:
    text_event:
      enabled: true
      cadence_seconds: 300
      lookback_seconds: 3600
""",
    )
    config = load_config(config_path)
    repository = LiveCollectionStateRepository(config_path)
    jobs = _RecordingLiveJobManager(create_status="failed")

    first = LiveScheduler(
        config,
        config_path=config_path,
        job_manager=jobs,
        state_repository=repository,
        now=start,
    ).tick(tick_id="tick-1")
    second = LiveScheduler(
        config,
        config_path=config_path,
        job_manager=jobs,
        state_repository=repository,
        now=start + timedelta(seconds=60),
    ).tick(tick_id="tick-2")

    assert _collection_state(first, "text_event:all")["consecutive_failures"] == 1
    assert _collection_state(second, "text_event:all")["consecutive_failures"] == 1


def test_live_read_model_reconciles_terminal_success_without_next_tick(tmp_path: Path) -> None:
    now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    config_path = _write_config(
        tmp_path,
        live_block="""
live:
  enabled: true
  collections:
    ohlcv:
      enabled: true
      cadence_seconds: 300
      lookback_seconds: 3600
""",
    )
    config = load_config(config_path)
    repository = LiveCollectionStateRepository(config_path)
    repository.upsert_state(
        {
            "target_key": "ohlcv:binance_usdm:BTCUSDT:1m",
            "data_type": "ohlcv",
            "target": {"data_type": "ohlcv", "source": "binance_usdm", "symbol": "BTCUSDT", "timeframe": "1m"},
            "enabled": True,
            "cadence_seconds": 300,
            "lookback_seconds": 3600,
            "lookahead_seconds": None,
            "last_attempt_at": "2026-06-30T11:59:00Z",
            "last_success_at": None,
            "next_attempt_at": "2026-06-30T12:04:00Z",
            "latest_job_id": "collect-1",
            "latest_job_status": "running",
            "latest_terminal_job_id": None,
            "latest_terminal_status": None,
            "consecutive_failures": 0,
            "source_refs": [],
            "warnings": [],
            "errors": [],
            "updated_at": "2026-06-30T11:59:00Z",
        }
    )
    jobs = _RecordingLiveJobManager(
        jobs=[
            _live_job(
                "collect-1",
                status="succeeded",
                target_key="ohlcv:binance_usdm:BTCUSDT:1m",
                data_type="ohlcv",
                created_at="2026-06-30T12:00:00Z",
            )
        ]
    )

    payload = LiveScheduler(
        config,
        config_path=config_path,
        job_manager=jobs,
        state_repository=repository,
        now=now,
    ).read_model()
    state = _collection_state(payload, "ohlcv:binance_usdm:BTCUSDT:1m")
    persisted = _collection_state({"collections": repository.list_states()}, "ohlcv:binance_usdm:BTCUSDT:1m")

    assert state["latest_job_status"] == "succeeded"
    assert state["latest_terminal_job_id"] == "collect-1"
    assert state["latest_terminal_status"] == "succeeded"
    assert state["last_success_at"] == "2026-06-30T12:00:00Z"
    assert state["source_refs"] == ["data/research/metadata/collection_coverage_state.json"]
    assert persisted["latest_terminal_job_id"] == "collect-1"


def test_live_read_model_reconciles_terminal_failure_once(tmp_path: Path) -> None:
    now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    config_path = _write_config(
        tmp_path,
        live_block="""
live:
  enabled: true
  collections:
    text_event:
      enabled: true
      cadence_seconds: 300
      lookback_seconds: 3600
""",
    )
    config = load_config(config_path)
    repository = LiveCollectionStateRepository(config_path)
    repository.upsert_state(
        {
            "target_key": "text_event:all",
            "data_type": "text_event",
            "target": {"data_type": "text_event"},
            "enabled": True,
            "cadence_seconds": 300,
            "lookback_seconds": 3600,
            "lookahead_seconds": None,
            "last_attempt_at": "2026-06-30T11:59:00Z",
            "last_success_at": None,
            "next_attempt_at": "2026-06-30T12:04:00Z",
            "latest_job_id": "collect-2",
            "latest_job_status": "running",
            "latest_terminal_job_id": None,
            "latest_terminal_status": None,
            "consecutive_failures": 0,
            "source_refs": [],
            "warnings": [],
            "errors": [],
            "updated_at": "2026-06-30T11:59:00Z",
        }
    )
    jobs = _RecordingLiveJobManager(
        jobs=[
            _live_job(
                "collect-2",
                status="failed",
                target_key="text_event:all",
                data_type="text_event",
                created_at="2026-06-30T12:00:00Z",
                errors=["collection failed"],
            )
        ]
    )

    first = LiveScheduler(
        config,
        config_path=config_path,
        job_manager=jobs,
        state_repository=repository,
        now=now,
    ).read_model()
    second = LiveScheduler(
        config,
        config_path=config_path,
        job_manager=jobs,
        state_repository=repository,
        now=now + timedelta(seconds=10),
    ).read_model()

    first_state = _collection_state(first, "text_event:all")
    second_state = _collection_state(second, "text_event:all")
    assert first_state["latest_job_status"] == "failed"
    assert first_state["latest_terminal_status"] == "failed"
    assert first_state["consecutive_failures"] == 1
    assert first_state["errors"] == ["collection failed"]
    assert second_state["consecutive_failures"] == 1


def test_live_read_model_relabels_persisted_mutation_lease_block_as_deferred(tmp_path: Path) -> None:
    now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    config_path = _write_config(
        tmp_path,
        live_block="""
live:
  enabled: true
  collections:
    text_event:
      enabled: true
      cadence_seconds: 300
      lookback_seconds: 3600
""",
    )
    config = load_config(config_path)
    repository = LiveCollectionStateRepository(config_path)
    repository.upsert_state(
        {
            "target_key": "text_event:all",
            "data_type": "text_event",
            "target": {"data_type": "text_event"},
            "enabled": True,
            "cadence_seconds": 300,
            "lookback_seconds": 3600,
            "lookahead_seconds": None,
            "last_attempt_at": "2026-06-30T11:59:00Z",
            "last_success_at": "2026-06-30T11:55:00Z",
            "next_attempt_at": "2026-06-30T12:04:00Z",
            "latest_job_id": "collect-3",
            "latest_job_status": "blocked",
            "latest_terminal_job_id": "collect-3",
            "latest_terminal_status": "blocked",
            "consecutive_failures": 1,
            "source_refs": [],
            "warnings": [],
            "errors": [LEASE_BLOCKED_MESSAGE],
            "updated_at": "2026-06-30T11:59:00Z",
        }
    )
    jobs = _RecordingLiveJobManager(
        jobs=[
            _live_job(
                "collect-3",
                status="blocked",
                target_key="text_event:all",
                data_type="text_event",
                created_at="2026-06-30T12:00:00Z",
                errors=[LEASE_BLOCKED_MESSAGE],
            )
        ]
    )

    payload = LiveScheduler(
        config,
        config_path=config_path,
        job_manager=jobs,
        state_repository=repository,
        now=now,
    ).read_model()
    state = _collection_state(payload, "text_event:all")
    persisted = _collection_state({"collections": repository.list_states()}, "text_event:all")

    assert payload["status"] == "available"
    assert payload["errors"] == []
    assert state["latest_terminal_status"] == "deferred"
    assert state["consecutive_failures"] == 0
    assert state["errors"] == []
    assert persisted["latest_terminal_status"] == "deferred"


def test_live_read_model_omits_stale_ohlcv_targets_from_previous_platform(tmp_path: Path) -> None:
    now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    config_path = _write_config(
        tmp_path,
        live_block="""
live:
  enabled: true
  collections:
    ohlcv:
      enabled: true
      cadence_seconds: 300
      lookback_seconds: 3600
""",
    )
    config = load_config(config_path)
    repository = LiveCollectionStateRepository(config_path)
    repository.upsert_state(
        {
            "target_key": "ohlcv:okx_spot:BTCUSDT:1m",
            "data_type": "ohlcv",
            "target": {"data_type": "ohlcv", "source": "okx_spot", "symbol": "BTCUSDT", "timeframe": "1m"},
            "enabled": True,
            "cadence_seconds": 300,
            "lookback_seconds": 3600,
            "lookahead_seconds": None,
            "last_attempt_at": None,
            "last_success_at": None,
            "next_attempt_at": None,
            "latest_job_id": None,
            "latest_job_status": None,
            "latest_terminal_job_id": None,
            "latest_terminal_status": None,
            "consecutive_failures": 0,
            "source_refs": [],
            "warnings": [],
            "errors": [],
            "updated_at": "2026-06-30T11:00:00Z",
        }
    )

    payload = LiveScheduler(config, config_path=config_path, job_manager=_RecordingLiveJobManager(), state_repository=repository, now=now).read_model()

    target_keys = {state["target_key"] for state in payload["collections"]}
    assert "ohlcv:binance_usdm:BTCUSDT:1m" in target_keys
    assert "ohlcv:okx_spot:BTCUSDT:1m" not in target_keys
    assert repository.get_state("ohlcv:okx_spot:BTCUSDT:1m") is not None


def test_live_read_model_does_not_persist_stream_overlay_only_change(tmp_path: Path) -> None:
    now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    config_path = _write_config(
        tmp_path,
        live_block="""
live:
  enabled: true
  collections:
    ohlcv:
      enabled: true
      cadence_seconds: 300
      lookback_seconds: 3600
  streams:
    ohlcv:
      enabled: true
      stale_after_seconds: 180
""",
    )
    config = load_config(config_path)
    repository = LiveCollectionStateRepository(config_path)
    stream_repository = LiveStreamStateRepository(config_path)
    repository.upsert_state(
        {
            "target_key": "ohlcv:binance_usdm:BTCUSDT:1m",
            "data_type": "ohlcv",
            "target": {"data_type": "ohlcv", "source": "binance_usdm", "symbol": "BTCUSDT", "timeframe": "1m"},
            "enabled": True,
            "cadence_seconds": 300,
            "lookback_seconds": 3600,
            "lookahead_seconds": None,
            "last_attempt_at": None,
            "last_success_at": None,
            "next_attempt_at": None,
            "latest_job_id": None,
            "latest_job_status": None,
            "latest_terminal_job_id": None,
            "latest_terminal_status": None,
            "consecutive_failures": 0,
            "source_refs": [],
            "warnings": [],
            "errors": [],
            "updated_at": "2026-06-30T11:00:00Z",
        }
    )
    stream_repository.upsert_state(
        {
            "target_key": "ohlcv:binance_usdm:BTCUSDT:1m",
            "data_type": "ohlcv",
            "target": {"data_type": "ohlcv", "source": "binance_usdm", "symbol": "BTCUSDT", "timeframe": "1m"},
            "enabled": True,
            "status": "disabled",
            "stream_name": "btcusdt@kline_1m",
            "endpoint": "binance_usdm_market_stream",
            "updated_at": "2026-06-30T11:59:00Z",
        }
    )

    payload = LiveScheduler(
        config,
        config_path=config_path,
        job_manager=_RecordingLiveJobManager(),
        state_repository=repository,
        stream_state_repository=stream_repository,
        now=now,
    ).read_model()

    state = _collection_state(payload, "ohlcv:binance_usdm:BTCUSDT:1m")
    persisted = repository.get_state("ohlcv:binance_usdm:BTCUSDT:1m")
    assert state["transport"] == "websocket"
    assert state["stream"]["status"] == "disabled"
    assert persisted is not None
    assert persisted["updated_at"] == "2026-06-30T11:00:00Z"


def test_live_trigger_state_adds_recent_decision_order_index(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    repository = LiveTriggerStateRepository(config_path)

    repository.list_decisions(limit=1)

    with sqlite3.connect(repository.database_path) as connection:
        index_names = {
            str(row[1])
            for row in connection.execute("PRAGMA index_list('live_trigger_decisions')").fetchall()
        }
    assert "idx_live_trigger_decisions_recent" in index_names


class _RecordingLiveJobManager:
    def __init__(
        self,
        *,
        jobs: list[dict[str, Any]] | None = None,
        create_status: str = "queued",
        create_errors: list[str] | None = None,
    ) -> None:
        self.jobs = list(jobs or [])
        self.created_requests: list[dict[str, Any]] = []
        self.create_status = create_status
        self.create_errors = list(create_errors or [])

    def list_jobs(self, *, limit: int = 100) -> dict[str, Any]:
        return {"jobs": self.jobs[:limit]}

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        for job in self.jobs:
            if job["job_id"] == job_id:
                return job
        return None

    def create_job(self, request: dict[str, Any]) -> dict[str, Any]:
        self.created_requests.append(request)
        requester = request["requester"]
        created_at = "2026-06-30T12:00:00Z"
        job = _live_job(
            f"job-{len(self.created_requests)}",
            status=self.create_status,
            target_key=str(requester["target_key"]),
            data_type=str(requester["data_type"]),
            created_at=created_at,
            params=request["params"],
            errors=self.create_errors or (["collection failed"] if self.create_status == "failed" else []),
        )
        self.jobs.insert(0, job)
        return job


def _command_job(
    job_id: str,
    *,
    intent: str,
    kind: str,
    status: str,
    created_at: str,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "command_job",
        "job_id": job_id,
        "kind": kind,
        "intent": intent,
        "requested_by": "Core",
        "requester": {"source": "core_scheduler"},
        "params": {},
        "status": status,
        "created_at": created_at,
        "updated_at": created_at,
        "finished_at": created_at if status in {"succeeded", "failed", "cancelled", "unsupported", "blocked"} else None,
        "result_refs": {},
        "source_artifacts": [],
        "warnings": [],
        "errors": list(errors or []),
    }


def _live_job(
    job_id: str,
    *,
    status: str,
    target_key: str,
    data_type: str,
    created_at: str,
    params: dict[str, Any] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "command_job",
        "job_id": job_id,
        "kind": "data_collection",
        "intent": "data_collect",
        "requested_by": "Core",
        "requester": {
            "source": "live_scheduler",
            "target_key": target_key,
            "data_type": data_type,
        },
        "params": params or {"data_type": data_type, "source": "all", "start": created_at, "end": created_at},
        "status": status,
        "created_at": created_at,
        "updated_at": created_at,
        "finished_at": created_at if status in {"succeeded", "failed", "cancelled", "unsupported", "blocked"} else None,
        "result_refs": {"collection_coverage": "data/research/metadata/collection_coverage_state.json"}
        if status == "succeeded"
        else {},
        "source_artifacts": [],
        "warnings": [],
        "errors": list(errors or []),
    }


def _collection_state(payload: dict[str, Any], target_key: str) -> dict[str, Any]:
    for state in payload["collections"]:
        if state["target_key"] == target_key:
            return state
    raise AssertionError(f"missing collection state: {target_key}")


def _write_config(tmp_path: Path, *, live_block: str) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
run:
  output_dir: runs
  timezone: UTC
market:
  enabled: true
  source: binance_usdm
  symbols:
    - BTCUSDT
  ohlcv:
    storage_dir: data/market/ohlcv
    sources:
      - binance_usdm
    timeframes:
      - 1m
    lookback:
      1m: 30
text:
  enabled: false
  sources: []
report:
  language: zh-CN
codex:
  enabled: false
monitor:
  enabled: false
{live_block}
""".strip(),
        encoding="utf-8",
    )
    return config_path
