from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from halpha.config import load_config
from halpha.dashboard import create_dashboard_app
from halpha.dashboard.live_history import dashboard_live_history, filter_live_history_events
from halpha.live.state_store import LiveCollectionStateRepository, LiveTriggerStateRepository
from halpha.runtime.command_job_store import CommandJobRepository


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_dashboard_live_history_builds_ordered_bounded_review_payload() -> None:
    payload = dashboard_live_history(
        live_payload=_live_payload(),
        jobs_payload={"jobs": [_collection_job(), _trigger_job(), _scheduled_job()]},
        schedule_payload=_schedule_payload(),
        cycles_payload={"status": "available", "cycles": [_cycle()]},
        alerts_payload=_alerts_payload(),
    )

    assert payload["artifact_type"] == "dashboard_live_history"
    assert payload["summary"]["timeline_events"] >= 8
    timestamps = [event["timestamp"] for event in payload["timeline"] if event["timestamp"]]
    assert timestamps == sorted(timestamps, reverse=True)
    event_kinds = {event["event_kind"] for event in payload["timeline"]}
    assert {
        "source_state",
        "collection_job",
        "trigger_decision",
        "trigger_report_job",
        "scheduled_report_dispatch",
        "scheduled_report_job",
        "monitor_cycle",
        "alert_archive_record",
    }.issubset(event_kinds)
    trigger_row = payload["triggered_reports"][0]
    assert trigger_row["trigger_id"] == "market_breakout"
    assert trigger_row["threshold_params"] == {"window_seconds": 3600}
    assert "record_count: 1" in trigger_row["evidence_summary"]
    assert trigger_row["linked_job_id"] == "trigger-job-1"
    assert trigger_row["linked_run_id"] == "run-trigger"
    assert trigger_row["linked_report_ref"] == "runs/run-trigger/report/report.md"
    assert payload["alert_archive"]["counts"]["suppressed_duplicate"] == 1
    assert payload["alert_archive"]["records"][0]["suppression_reasons"] == ["duplicate"]
    assert payload["omitted"]["full_raw_stores_embedded"] is False
    assert payload["omitted"]["full_command_logs_embedded"] is False


def test_dashboard_live_history_filters_and_marks_missing_refs() -> None:
    payload = dashboard_live_history(
        live_payload=_live_payload(decision_report_ref=None),
        jobs_payload={"jobs": [_trigger_job(result_refs={})]},
        schedule_payload={"status": "missing", "dispatches": []},
        cycles_payload={"status": "missing", "cycles": []},
        alerts_payload={"status": "missing", "alert_archive": {"fields": {"counts": {}, "sample_records": []}}},
    )

    filtered = filter_live_history_events(
        payload["timeline"],
        {
            "trigger_id": "market_breakout",
            "event_kind": "trigger_report_job",
            "attention_only": True,
        },
    )

    assert len(filtered) == 1
    assert filtered[0]["status"] == "degraded"
    assert filtered[0]["artifact_state"] == "missing"
    assert "linked report artifact ref is missing." in filtered[0]["warnings"]
    assert filter_live_history_events(payload["timeline"], {"report_linked_only": True})


def test_dashboard_live_history_endpoint_reads_runtime_state(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    LiveCollectionStateRepository(config_path).upsert_state(
        {
            "target_key": "text_event:all",
            "data_type": "text_event",
            "target": {"source": "all"},
            "enabled": True,
            "cadence_seconds": 300,
            "lookback_seconds": 3600,
            "lookahead_seconds": None,
            "last_attempt_at": "2026-06-30T11:58:00Z",
            "last_success_at": "2026-06-30T11:59:00Z",
            "next_attempt_at": "2026-06-30T12:04:00Z",
            "latest_job_id": "collect-job-1",
            "latest_job_status": "succeeded",
            "latest_terminal_job_id": "collect-job-1",
            "latest_terminal_status": "succeeded",
            "consecutive_failures": 0,
            "source_refs": ["data/research/raw/text_events.json"],
            "warnings": [],
            "errors": [],
            "updated_at": "2026-06-30T12:00:00Z",
        }
    )
    LiveTriggerStateRepository(config_path).upsert_decision(
        {
            "decision_id": "decision-api",
            "trigger_id": "market_breakout",
            "status": "triggered",
            "evaluated_at": "2026-06-30T12:00:00Z",
            "source_data_types": ["market_anomaly"],
            "source_refs": ["data/research/market_anomalies"],
            "reason_codes": ["market_breakout_matched"],
            "threshold_params": {"window_seconds": 3600},
            "matched_evidence": {"record_count": 1, "records": [{"symbol": "BTCUSDT"}]},
            "cooldown_until": "2026-06-30T12:05:00Z",
            "linked_collection_job_ids": ["collect-job-1"],
            "linked_report_job_id": "trigger-job-api",
            "linked_report_job_status": "succeeded",
            "linked_run_id": "run-api",
            "linked_report_ref": "runs/run-api/report/report.md",
            "warnings": [],
            "errors": [],
            "updated_at": "2026-06-30T12:01:00Z",
        }
    )
    CommandJobRepository(config_path=config_path).save_job(
        _stored_job(
            "trigger-job-api",
            requester={"source": "live_trigger", "trigger_id": "market_breakout", "decision_id": "decision-api"},
            result_refs={"run_id": "run-api", "report": "runs/run-api/report/report.md"},
        ),
        event_type="seed",
    )
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/live/history")

    assert response.status_code == 200
    payload = response.json()
    assert payload["artifact_type"] == "dashboard_live_history"
    assert any(event["event_kind"] == "trigger_decision" for event in payload["timeline"])
    assert payload["triggered_reports"][0]["linked_report_ref"] == "runs/run-api/report/report.md"
    assert "decision-api" in response.text
    assert str(tmp_path) not in response.text


def _live_payload(*, decision_report_ref: str | None = "runs/run-trigger/report/report.md") -> dict[str, Any]:
    return {
        "status": "available",
        "scheduler": {"enabled": True},
        "collections": [
            {
                "target_key": "text_event:all",
                "data_type": "text_event",
                "target": {"source": "all"},
                "enabled": True,
                "latest_job_id": "collect-job-1",
                "latest_job_status": "succeeded",
                "latest_terminal_job_id": "collect-job-1",
                "latest_terminal_status": "succeeded",
                "last_attempt_at": "2026-06-30T11:58:00Z",
                "last_success_at": "2026-06-30T11:59:00Z",
                "updated_at": "2026-06-30T12:00:00Z",
                "source_refs": ["data/research/raw/text_events.json"],
                "warnings": [],
                "errors": [],
            }
        ],
        "triggers": {
            "status": "available",
            "config": {"enabled": True, "triggers": [{"trigger_id": "market_breakout", "enabled": True}]},
            "recent_decisions": [
                {
                    "decision_id": "decision-1",
                    "trigger_id": "market_breakout",
                    "status": "triggered",
                    "evaluated_at": "2026-06-30T12:00:00Z",
                    "source_data_types": ["market_anomaly"],
                    "source_refs": ["data/research/market_anomalies"],
                    "reason_codes": ["market_breakout_matched"],
                    "threshold_params": {"window_seconds": 3600},
                    "matched_evidence": {"record_count": 1, "records": [{"symbol": "BTCUSDT"}]},
                    "cooldown_until": "2026-06-30T12:05:00Z",
                    "linked_collection_job_ids": ["collect-job-1"],
                    "linked_report_job_id": "trigger-job-1",
                    "linked_report_job_status": "succeeded",
                    "linked_run_id": "run-trigger" if decision_report_ref else None,
                    "linked_report_ref": decision_report_ref,
                    "warnings": [],
                    "errors": [],
                    "updated_at": "2026-06-30T12:01:00Z",
                }
            ],
            "warnings": [],
            "errors": [],
        },
        "warnings": [],
        "errors": [],
    }


def _collection_job() -> dict[str, Any]:
    return _stored_job(
        "collect-job-1",
        kind="data_collection",
        intent="data_collect",
        requester={"source": "live_scheduler", "target_key": "text_event:all", "data_type": "text_event"},
        result_refs={"collection_coverage": "data/research/metadata/collection_coverage_state.json"},
        created_at="2026-06-30T11:58:00Z",
    )


def _trigger_job(result_refs: dict[str, Any] | None = None) -> dict[str, Any]:
    return _stored_job(
        "trigger-job-1",
        requester={"source": "live_trigger", "trigger_id": "market_breakout", "decision_id": "decision-1"},
        result_refs=result_refs if result_refs is not None else {"run_id": "run-trigger", "report": "runs/run-trigger/report/report.md"},
        created_at="2026-06-30T12:01:00Z",
    )


def _scheduled_job() -> dict[str, Any]:
    return _stored_job(
        "daily-job-1",
        requester={"source": "daily_report_schedule", "dispatch_kind": "automatic", "schedule_id": "daily_report"},
        result_refs={"run_id": "run-daily", "report": "runs/run-daily/report/report.md"},
        created_at="2026-06-30T08:01:00Z",
    )


def _stored_job(
    job_id: str,
    *,
    requester: dict[str, Any],
    kind: str = "product_run",
    intent: str = "run_no_codex",
    result_refs: dict[str, Any] | None = None,
    created_at: str = "2026-06-30T12:00:00Z",
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "command_job",
        "job_id": job_id,
        "kind": kind,
        "intent": intent,
        "requested_by": "Core",
        "requester": requester,
        "config_ref": "config.yaml",
        "params": {},
        "status": "succeeded",
        "created_at": created_at,
        "updated_at": created_at,
        "started_at": created_at,
        "finished_at": created_at,
        "pid": None,
        "exit_code": 0,
        "cancellable": False,
        "command": [],
        "job_dir": ".halpha/command_jobs/job-1",
        "logs": {"stdout_chars": 0, "stderr_chars": 0, "stdout_truncated": False, "stderr_truncated": False, "max_chars": 0},
        "result_refs": result_refs or {},
        "source_artifacts": [],
        "warnings": [],
        "errors": [],
    }


def _schedule_payload() -> dict[str, Any]:
    return {
        "status": "available",
        "enabled": True,
        "dispatches": [
            {
                "scheduled_for": "2026-06-30T08:00:00Z",
                "dispatch_kind": "automatic",
                "status": "succeeded",
                "claimed_at": "2026-06-30T08:00:10Z",
                "completed_at": "2026-06-30T08:10:00Z",
                "job_id": "daily-job-1",
                "run_ref": "run-daily",
                "report_ref": "runs/run-daily/report/report.md",
                "terminal_status": "succeeded",
                "warnings": [],
                "errors": [],
            }
        ],
        "warnings": [],
        "errors": [],
    }


def _cycle() -> dict[str, Any]:
    return {
        "cycle_id": "cycle-1",
        "status": "succeeded",
        "started_at": "2026-06-30T07:55:00Z",
        "finished_at": "2026-06-30T07:56:00Z",
        "run_id": "run-cycle",
        "run_manifest": "runs/run-cycle/run_manifest.json",
        "cycle_manifest": "runs/monitor/cycles/cycle-1/monitor_cycle_manifest.json",
        "warnings": [],
        "errors": [],
    }


def _alerts_payload() -> dict[str, Any]:
    return {
        "status": "available",
        "alert_archive": {
            "fields": {
                "counts": {"records": 2, "emitted": 1, "suppressed_duplicate": 1, "suppressed_cooldown": 0, "skipped": 0},
                "sample_records": [
                    {
                        "record_id": "alert-record-2",
                        "created_at": "2026-06-30T12:02:00Z",
                        "status": "suppressed_duplicate",
                        "alert_key": "alert:BTCUSDT",
                        "decision_id": "decision-1",
                        "symbol": "BTCUSDT",
                        "timeframe": "1m",
                        "priority": "p1",
                        "attention_decision": "watch",
                        "suppression_reasons": ["duplicate"],
                        "source_artifacts": ["runs/run-trigger/analysis/alert_decisions.json"],
                        "source_run": {"run_id": "run-trigger", "run_manifest": "runs/run-trigger/run_manifest.json"},
                    },
                    {
                        "record_id": "alert-record-1",
                        "created_at": "2026-06-30T12:01:30Z",
                        "status": "emitted",
                        "alert_key": "alert:ETHUSDT",
                        "symbol": "ETHUSDT",
                        "timeframe": "1m",
                        "priority": "p2",
                        "suppression_reasons": [],
                        "source_artifacts": [],
                    },
                ],
            }
        },
        "warnings": [],
        "errors": [],
    }


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
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
live:
  enabled: true
  collections:
    text_event:
      enabled: true
      cadence_seconds: 300
      lookback_seconds: 3600
  reports:
    triggers:
      market_breakout:
        enabled: true
        cooldown_seconds: 300
""".strip(),
        encoding="utf-8",
    )
    return config_path
