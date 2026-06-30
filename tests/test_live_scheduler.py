from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from halpha.config import load_config
from halpha.live.contracts import LIVE_DATA_TYPES
from halpha.live.scheduler import LiveScheduler
from halpha.live.state_store import LiveCollectionStateRepository


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
    now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
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


class _RecordingLiveJobManager:
    def __init__(self, *, jobs: list[dict[str, Any]] | None = None, create_status: str = "queued") -> None:
        self.jobs = list(jobs or [])
        self.created_requests: list[dict[str, Any]] = []
        self.create_status = create_status

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
            errors=["collection failed"] if self.create_status == "failed" else [],
        )
        self.jobs.insert(0, job)
        return job


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
