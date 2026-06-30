from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from halpha.config import ConfigError, load_config
from halpha.live.triggers import LiveTriggerEvaluator


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_live_trigger_config_validation_accepts_allowlisted_fields(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        """
live:
  enabled: true
  reports:
    triggers:
      major_market_move:
        enabled: true
        cooldown_seconds: 300
        job_intent: run_no_codex
        window_seconds: 3600
        price_change_pct: 5.5
        volume_change_pct: 120
""",
    )

    config = load_config(config_path)

    trigger = config["live"]["reports"]["triggers"]["major_market_move"]
    assert trigger["price_change_pct"] == 5.5


def test_live_trigger_config_validation_rejects_unknown_trigger_fields(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        """
live:
  enabled: true
  reports:
    triggers:
      data_quality_degraded:
        enabled: true
        cooldown_seconds: 300
        unknown_field: nope
""",
    )

    with pytest.raises(ConfigError, match="unsupported live.reports.triggers.data_quality_degraded field"):
        load_config(config_path)


def test_live_trigger_config_validation_rejects_invalid_job_intent(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        """
live:
  enabled: true
  reports:
    triggers:
      data_quality_degraded:
        enabled: true
        cooldown_seconds: 300
        job_intent: unsupported
""",
    )

    with pytest.raises(ConfigError, match="job_intent must be one of"):
        load_config(config_path)


def test_disabled_live_trigger_records_skipped_disabled(tmp_path: Path) -> None:
    now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    config_path = _write_config(tmp_path, "live:\n  enabled: true\n")
    config = load_config(config_path)

    result = LiveTriggerEvaluator(config, config_path=config_path, job_manager=_RecordingJobManager(), now=now).evaluate()

    decisions = {item["trigger_id"]: item for item in result["decisions"]}
    assert decisions["critical_news"]["status"] == "skipped_disabled"
    assert decisions["critical_news"]["reason_codes"] == ["trigger_disabled"]


def test_critical_news_without_priority_fields_records_insufficient_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    config_path = _write_config(
        tmp_path,
        """
live:
  enabled: true
  reports:
    triggers:
      critical_news:
        enabled: true
        cooldown_seconds: 300
        min_priority: high
""",
    )
    config = load_config(config_path)
    monkeypatch.setattr(
        "halpha.live.triggers.query_event_like_records",
        lambda *args, **kwargs: _event_query_result(
            data_type="text_event",
            records=[{"title": "news without priority", "published_at": "2026-06-30T11:59:00Z"}],
            history_row_count=1,
        ),
    )

    result = LiveTriggerEvaluator(config, config_path=config_path, job_manager=_RecordingJobManager(), now=now).evaluate()
    decision = _decision(result, "critical_news")

    assert decision["status"] == "skipped_insufficient_evidence"
    assert decision["reason_codes"] == ["text_event_priority_fields_missing"]


def test_critical_news_below_priority_records_no_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    config_path = _write_config(
        tmp_path,
        """
live:
  enabled: true
  reports:
    triggers:
      critical_news:
        enabled: true
        cooldown_seconds: 300
        min_priority: high
""",
    )
    config = load_config(config_path)
    monkeypatch.setattr(
        "halpha.live.triggers.query_event_like_records",
        lambda *args, **kwargs: _event_query_result(
            data_type="text_event",
            records=[{"title": "minor update", "priority": "medium", "published_at": "2026-06-30T11:59:00Z"}],
            history_row_count=1,
        ),
    )

    result = LiveTriggerEvaluator(config, config_path=config_path, job_manager=_RecordingJobManager(), now=now).evaluate()
    decision = _decision(result, "critical_news")

    assert decision["status"] == "skipped_no_match"
    assert decision["reason_codes"] == ["critical_news_below_min_priority"]


def test_market_breakout_creates_run_no_codex_report_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    config_path = _write_config(
        tmp_path,
        """
live:
  enabled: true
  reports:
    triggers:
      market_breakout:
        enabled: true
        cooldown_seconds: 300
        job_intent: run_no_codex
""",
    )
    config = load_config(config_path)
    jobs = _RecordingJobManager()
    monkeypatch.setattr(
        "halpha.live.triggers.query_event_like_records",
        lambda *args, **kwargs: _event_query_result(
            data_type="market_anomaly",
            records=[
                {
                    "history_key": "anomaly-1",
                    "data_class": "market_breakout",
                    "symbol": "BTCUSDT",
                    "observed_at": "2026-06-30T11:59:00Z",
                }
            ],
            history_row_count=1,
        ),
    )

    result = LiveTriggerEvaluator(config, config_path=config_path, job_manager=jobs, now=now).evaluate(tick_id="tick-1")
    decision = _decision(result, "market_breakout")

    assert decision["status"] == "triggered"
    assert decision["linked_report_job_id"] == "job-1"
    assert decision["cooldown_until"] == "2026-06-30T12:05:00Z"
    assert jobs.created_requests == [
        {
            "intent": "run_no_codex",
            "params": {},
            "requested_by": "Core",
            "requester": {
                "source": "live_trigger",
                "tick_id": "tick-1",
                "trigger_id": "market_breakout",
                "trigger_revision": 1,
                "decision_id": decision["decision_id"],
            },
        }
    ]


def test_cooldown_suppresses_repeated_live_trigger_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    start = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    config_path = _write_config(
        tmp_path,
        """
live:
  enabled: true
  reports:
    triggers:
      market_breakout:
        enabled: true
        cooldown_seconds: 300
""",
    )
    config = load_config(config_path)
    jobs = _RecordingJobManager()
    monkeypatch.setattr(
        "halpha.live.triggers.query_event_like_records",
        lambda *args, **kwargs: _event_query_result(
            data_type="market_anomaly",
            records=[{"data_class": "market_breakout", "observed_at": "2026-06-30T11:59:00Z"}],
            history_row_count=1,
        ),
    )

    first = LiveTriggerEvaluator(config, config_path=config_path, job_manager=jobs, now=start).evaluate()
    second = LiveTriggerEvaluator(
        config,
        config_path=config_path,
        job_manager=jobs,
        now=start + timedelta(seconds=60),
    ).evaluate()

    assert _decision(first, "market_breakout")["status"] == "triggered"
    assert _decision(second, "market_breakout")["status"] == "suppressed_cooldown"
    assert _decision(second, "market_breakout")["reason_codes"][-1] == "cooldown_active"
    assert len(jobs.created_requests) == 1


def test_active_trigger_report_job_suppresses_duplicate_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    config_path = _write_config(
        tmp_path,
        """
live:
  enabled: true
  reports:
    triggers:
      market_breakout:
        enabled: true
        cooldown_seconds: 300
""",
    )
    config = load_config(config_path)
    jobs = _RecordingJobManager(jobs=[_trigger_job("existing", status="running", trigger_id="market_breakout")])
    monkeypatch.setattr(
        "halpha.live.triggers.query_event_like_records",
        lambda *args, **kwargs: _event_query_result(
            data_type="market_anomaly",
            records=[{"data_class": "market_breakout", "observed_at": "2026-06-30T11:59:00Z"}],
            history_row_count=1,
        ),
    )

    result = LiveTriggerEvaluator(config, config_path=config_path, job_manager=jobs, now=now).evaluate()
    decision = _decision(result, "market_breakout")

    assert decision["status"] == "suppressed_cooldown"
    assert decision["linked_report_job_id"] == "existing"
    assert "equivalent_active_report_job" in decision["reason_codes"]
    assert jobs.created_requests == []


def test_codex_capable_run_trigger_requires_persisted_authorization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    config_path = _write_config(
        tmp_path,
        """
live:
  enabled: true
  reports:
    triggers:
      market_breakout:
        enabled: true
        cooldown_seconds: 300
        job_intent: run
""",
    )
    config = load_config(config_path)
    jobs = _RecordingJobManager()
    monkeypatch.setattr(
        "halpha.live.triggers.query_event_like_records",
        lambda *args, **kwargs: _event_query_result(
            data_type="market_anomaly",
            records=[{"data_class": "market_breakout", "observed_at": "2026-06-30T11:59:00Z"}],
            history_row_count=1,
        ),
    )

    result = LiveTriggerEvaluator(config, config_path=config_path, job_manager=jobs, now=now).evaluate()
    decision = _decision(result, "market_breakout")

    assert decision["status"] == "blocked_authorization"
    assert decision["linked_report_job_id"] is None
    assert jobs.created_requests == []


def test_report_job_creation_failure_records_failed_decision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    config_path = _write_config(
        tmp_path,
        """
live:
  enabled: true
  reports:
    triggers:
      market_breakout:
        enabled: true
        cooldown_seconds: 300
""",
    )
    config = load_config(config_path)
    jobs = _RecordingJobManager(create_status="failed")
    monkeypatch.setattr(
        "halpha.live.triggers.query_event_like_records",
        lambda *args, **kwargs: _event_query_result(
            data_type="market_anomaly",
            records=[{"data_class": "market_breakout", "observed_at": "2026-06-30T11:59:00Z"}],
            history_row_count=1,
        ),
    )

    result = LiveTriggerEvaluator(config, config_path=config_path, job_manager=jobs, now=now).evaluate()
    decision = _decision(result, "market_breakout")

    assert decision["status"] == "failed"
    assert decision["linked_report_job_status"] == "failed"


def test_data_quality_degraded_trigger_links_collection_job(tmp_path: Path) -> None:
    now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    config_path = _write_config(
        tmp_path,
        """
live:
  enabled: true
  reports:
    triggers:
      data_quality_degraded:
        enabled: true
        cooldown_seconds: 300
        min_failed_targets: 1
""",
    )
    config = load_config(config_path)
    live_read_model = {
        "collections": [
            {
                "target_key": "text_event:all",
                "data_type": "text_event",
                "enabled": True,
                "latest_job_id": "collect-1",
                "latest_job_status": "failed",
                "latest_terminal_status": "failed",
                "errors": ["collection failed"],
            }
        ]
    }

    result = LiveTriggerEvaluator(
        config,
        config_path=config_path,
        job_manager=_RecordingJobManager(),
        now=now,
    ).evaluate(live_read_model=live_read_model)
    decision = _decision(result, "data_quality_degraded")

    assert decision["status"] == "triggered"
    assert decision["linked_collection_job_ids"] == ["collect-1"]
    assert decision["matched_evidence"]["failed_target_count"] == 1


def test_live_trigger_read_model_reconciles_linked_report_job_refs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    config_path = _write_config(
        tmp_path,
        """
live:
  enabled: true
  reports:
    triggers:
      market_breakout:
        enabled: true
        cooldown_seconds: 300
""",
    )
    config = load_config(config_path)
    jobs = _RecordingJobManager()
    monkeypatch.setattr(
        "halpha.live.triggers.query_event_like_records",
        lambda *args, **kwargs: _event_query_result(
            data_type="market_anomaly",
            records=[{"data_class": "market_breakout", "observed_at": "2026-06-30T11:59:00Z"}],
            history_row_count=1,
        ),
    )
    first = LiveTriggerEvaluator(config, config_path=config_path, job_manager=jobs, now=now).evaluate()
    job_id = _decision(first, "market_breakout")["linked_report_job_id"]
    jobs.replace_job(_trigger_job(job_id, status="succeeded", trigger_id="market_breakout"))

    read_model = LiveTriggerEvaluator(
        config,
        config_path=config_path,
        job_manager=jobs,
        now=now + timedelta(seconds=30),
    ).read_model()
    latest = read_model["latest_decisions"]["market_breakout"]

    assert latest["linked_report_job_status"] == "succeeded"
    assert latest["linked_run_id"] == "run-1"
    assert latest["linked_report_ref"] == "runs/run-1/report/report.md"
    assert read_model["cooldowns"][0]["trigger_id"] == "market_breakout"


class _RecordingJobManager:
    def __init__(self, *, jobs: list[dict[str, Any]] | None = None, create_status: str = "queued") -> None:
        self.jobs = list(jobs or [])
        self.created_requests: list[dict[str, Any]] = []
        self.create_status = create_status

    def create_job(self, request: dict[str, Any]) -> dict[str, Any]:
        self.created_requests.append(request)
        job = _trigger_job(
            f"job-{len(self.created_requests)}",
            status=self.create_status,
            trigger_id=str(request["requester"]["trigger_id"]),
            requester=request["requester"],
            intent=request["intent"],
        )
        if self.create_status == "failed":
            job["errors"] = ["report job failed"]
        self.jobs.insert(0, job)
        return job

    def list_jobs(self, *, limit: int = 100) -> dict[str, Any]:
        return {"jobs": self.jobs[:limit]}

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        for job in self.jobs:
            if job.get("job_id") == job_id:
                return job
        return None

    def replace_job(self, job: dict[str, Any]) -> None:
        self.jobs = [item for item in self.jobs if item.get("job_id") != job.get("job_id")]
        self.jobs.insert(0, job)


def _trigger_job(
    job_id: str,
    *,
    status: str,
    trigger_id: str,
    requester: dict[str, Any] | None = None,
    intent: str = "run_no_codex",
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "command_job",
        "job_id": job_id,
        "kind": "product_run",
        "intent": intent,
        "requested_by": "Core",
        "requester": requester
        or {
            "source": "live_trigger",
            "trigger_id": trigger_id,
            "trigger_revision": 1,
            "decision_id": "decision-1",
        },
        "params": {},
        "status": status,
        "created_at": "2026-06-30T12:00:00Z",
        "updated_at": "2026-06-30T12:00:30Z",
        "finished_at": "2026-06-30T12:00:30Z" if status in {"succeeded", "failed", "cancelled", "unsupported", "blocked"} else None,
        "result_refs": {"run_id": "run-1", "report": "runs/run-1/report/report.md"} if status == "succeeded" else {},
        "source_artifacts": [],
        "warnings": [],
        "errors": [],
    }


def _event_query_result(
    *,
    data_type: str,
    records: list[dict[str, Any]],
    history_row_count: int,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "event_like_query_result",
        "status": "ok",
        "data_type": data_type,
        "records": records,
        "history_row_count": history_row_count,
        "source_artifacts": [f"data/research/{data_type}"],
        "warnings": [],
        "errors": [],
    }


def _decision(payload: dict[str, Any], trigger_id: str) -> dict[str, Any]:
    for decision in payload["decisions"]:
        if decision["trigger_id"] == trigger_id:
            return decision
    raise AssertionError(f"missing decision for {trigger_id}")


def _write_config(tmp_path: Path, live_block: str) -> Path:
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
