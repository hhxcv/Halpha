from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from halpha.config import load_config
from halpha.dashboard import create_dashboard_app
from halpha.monitor.state_store import MonitorArchivePersistence, MonitorStateRepository
from halpha.storage import write_json


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_dashboard_monitor_api_summarizes_complete_state_without_dumping_alerts(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    _write_complete_monitor_state(config_path, tmp_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    summary_response = client.get("/api/monitor")
    cycles_response = client.get("/api/monitor/cycles")
    alerts_response = client.get("/api/monitor/alerts")

    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["artifact_type"] == "dashboard_monitor"
    assert summary["status"] == "available"
    assert summary["settings"]["interval_seconds"] == 300
    assert summary["settings"]["max_cycles"] == 1
    assert summary["settings"]["failure_backoff_max_seconds"] == 3600
    assert summary["settings"]["cooldown_seconds"] == 1800
    assert summary["settings"]["output_dir"] == "runs/monitor"
    assert summary["health"]["fields"]["cycle_count"] == 1
    assert summary["health"]["fields"]["service"]["status"] == "missing"
    assert summary["health"]["fields"]["source_states"][0]["source_key"] == "text"
    assert summary["health"]["fields"]["source_states"][0]["status"] == "changed"
    assert summary["latest_cycle"]["cycle_id"] == "cycle-1"
    assert summary["alert_archive"]["fields"]["counts"]["records"] == 25
    assert summary["cooldown"]["fields"]["record_count"] == 2
    assert summary["omitted"]["full_alert_archive_embedded"] is False
    assert summary["omitted"]["private_personalized_evidence_embedded"] is False

    cycles = cycles_response.json()
    assert cycles["status"] == "available"
    assert cycles["cycle_count"] == 1
    assert cycles["cycles"][0]["alert_archive"]["counts"]["emitted"] == 20

    alerts = alerts_response.json()
    assert alerts["status"] == "available"
    sample = alerts["alert_archive"]["fields"]["sample_records"]
    assert len(sample) == 20
    assert alerts["alert_archive"]["fields"]["updated_at"] == "2026-06-20T00:24:00Z"
    assert alerts["alert_archive"]["fields"]["last_cycle_id"] == "cycle-1"
    assert alerts["alert_archive"]["fields"]["sample_order"] == "newest_first"
    assert alerts["alert_archive"]["fields"]["sample_truncated"] is True
    assert sample[0]["record_id"] == "record-24"
    assert sample[-1]["record_id"] == "record-5"
    assert sample[0]["sample_order"] == 1
    assert sample[0]["personalized_context_present"] is True
    assert sample[0]["source_artifact_count"] == 1
    assert "private_constraint" not in alerts_response.text
    assert "private evidence" not in alerts_response.text
    assert str(tmp_path) not in summary_response.text
    assert str(tmp_path) not in alerts_response.text


def test_dashboard_monitor_api_reports_missing_state(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/monitor")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "missing"
    assert payload["health"]["status"] == "missing"
    assert payload["cycles"]["status"] == "missing"
    assert payload["alert_archive"]["status"] == "missing"
    assert payload["cooldown"]["status"] == "missing"
    assert "monitor state store was not found." in payload["warnings"]


def test_dashboard_monitor_api_reports_partial_state(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    _write_monitor_cycle_state(config_path, tmp_path, records=[], cooldown_records={})
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/monitor")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "partial"
    assert payload["health"]["status"] == "available"
    assert payload["cycles"]["status"] == "available"
    assert payload["alert_archive"]["status"] == "missing"
    assert payload["cooldown"]["status"] == "missing"


def test_dashboard_monitor_api_promotes_failed_health_state(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    _write_monitor_cycle_state(
        config_path,
        tmp_path,
        cycle_id="cycle-failed",
        run_id="run-failed",
        status="failed",
        errors=["market source unavailable"],
        records=[],
        cooldown_records={},
    )
    MonitorStateRepository(config_path=config_path).save_loop(
        {
            "loop_id": "loop-1",
            "status": "failed",
            "max_cycles": 3,
            "completed_cycles": 2,
            "stop_reason": "cycle_failed",
            "started_at": "2026-06-20T00:00:00Z",
            "finished_at": "2026-06-20T00:20:00Z",
            "latest_cycle_id": "cycle-failed",
        },
        monitor_output_dir="runs/monitor",
        updated_at="2026-06-20T00:20:00Z",
    )
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/monitor")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["health"]["status"] == "failed"
    assert payload["health"]["fields"]["latest_cycle_status"] == "failed"
    assert payload["health"]["fields"]["warning_count"] == 0
    assert payload["health"]["fields"]["error_count"] == 1
    assert "market source unavailable" in payload["errors"]


def test_dashboard_monitor_api_reports_missing_cycle_evidence(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    _write_monitor_cycle_state(
        config_path,
        tmp_path,
        cycle_id="cycle-missing",
        run_id="run-missing",
        create_evidence=False,
        records=[],
        cooldown_records={},
    )
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/monitor")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "partial"
    assert payload["health"]["status"] == "partial"
    assert payload["cycles"]["status"] == "partial"
    assert any("monitor cycle manifest was not found" in warning for warning in payload["warnings"])
    assert any("linked run manifest was not found" in warning for warning in payload["warnings"])


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
run:
  output_dir: runs
market:
  enabled: false
text:
  enabled: false
  sources: []
monitor:
  output_dir: runs/monitor
  cooldown_seconds: 1800
report:
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return path


def _write_complete_monitor_state(config_path: Path, tmp_path: Path) -> None:
    counts = {
        "records": 25,
        "emitted": 20,
        "suppressed_duplicate": 2,
        "suppressed_cooldown": 1,
        "suppressed_no_alert": 1,
        "skipped": 1,
    }
    _write_monitor_cycle_state(
        config_path,
        tmp_path,
        records=[_alert_record(index) for index in range(25)],
        cooldown_records={
            "alert:BTCUSDT": {
                "alert_key": "alert:BTCUSDT",
                "cooldown_until": "2026-06-20T00:46:00Z",
                "last_record_id": "record-1",
            },
            "alert:ETHUSDT": {
                "alert_key": "alert:ETHUSDT",
                "cooldown_until": "2026-06-20T00:47:00Z",
                "last_record_id": "record-2",
            },
        },
        counts=counts,
    )


def _write_monitor_cycle_state(
    config_path: Path,
    tmp_path: Path,
    *,
    cycle_id: str = "cycle-1",
    run_id: str = "run-1",
    status: str = "succeeded",
    records: list[dict[str, object]],
    cooldown_records: dict[str, dict[str, object]],
    counts: dict[str, int] | None = None,
    errors: list[str] | None = None,
    create_evidence: bool = True,
) -> None:
    if create_evidence:
        write_json(tmp_path / "runs" / run_id / "run_manifest.json", {"run_id": run_id, "status": status})
        write_json(
            tmp_path / "runs" / "monitor" / "cycles" / cycle_id / "monitor_cycle_manifest.json",
            {"artifact_type": "monitor_cycle_manifest", "cycle_id": cycle_id, "status": status},
        )
    summary = {
        "status": "succeeded" if records else "skipped",
        "state_store": ".halpha/state.sqlite",
        "archive": ".halpha/state.sqlite",
        "cooldown_state": ".halpha/state.sqlite",
        "archive_state": ".halpha/state.sqlite",
        "counts": counts
        or {
            "records": len(records),
            "emitted": sum(1 for record in records if record.get("status") == "emitted"),
            "suppressed_duplicate": sum(1 for record in records if record.get("status") == "suppressed_duplicate"),
            "suppressed_cooldown": sum(1 for record in records if record.get("status") == "suppressed_cooldown"),
            "suppressed_no_alert": sum(1 for record in records if record.get("status") == "suppressed_no_alert"),
            "skipped": sum(1 for record in records if record.get("status") == "skipped"),
        },
        "warnings": [],
        "errors": [],
    }
    cycle = {
        "cycle_id": cycle_id,
        "monitor_output_dir": "runs/monitor",
        "cycle_manifest": f"runs/monitor/cycles/{cycle_id}/monitor_cycle_manifest.json",
        "cycle_mode": "loop",
        "loop_id": "loop-1",
        "cycle_sequence": 1,
        "trigger_source": "cli",
        "status": status,
        "started_at": "2026-06-20T00:10:00Z",
        "finished_at": "2026-06-20T00:15:00Z",
        "config_ref": "config.yaml",
        "target_stage": "build_personalized_risk_material",
        "no_codex": True,
        "exit_code": 0 if status == "succeeded" else 3,
        "run_id": run_id,
        "run_dir": f"runs/{run_id}",
        "run_manifest": f"runs/{run_id}/run_manifest.json",
        "product_run": {"status": status, "run_id": run_id},
        "source_artifacts": {"alert_decisions": "analysis/alert_decisions.json"},
        "alert_archive": summary,
        "warnings": [],
        "errors": errors or [],
    }
    MonitorStateRepository(config_path=config_path).persist_cycle_with_archive_builder(
        cycle,
        build_archive=lambda _cooldown: MonitorArchivePersistence(
            summary=summary,
            records=records,
            cooldown_records=cooldown_records,
        ),
        updated_at="2026-06-20T00:16:00Z",
    )
    MonitorStateRepository(config_path=config_path).save_source_states(
        [
            {
                "source_key": "text",
                "enabled": True,
                "cadence_seconds": 300,
                "status": "changed",
                "last_attempt_at": "2026-06-20T00:10:00Z",
                "last_success_at": "2026-06-20T00:10:00Z",
                "next_attempt_at": "2026-06-20T00:15:00Z",
                "consecutive_failures": 0,
                "backoff_seconds": 0,
                "latest_published_data_revision": "text-revision",
                "changed_scope": {"sources": ["feed"]},
                "latest_run_id": run_id,
                "latest_run_manifest": f"runs/{run_id}/run_manifest.json",
            }
        ],
        monitor_output_dir="runs/monitor",
        updated_at="2026-06-20T00:16:00Z",
    )


def _alert_record(index: int) -> dict[str, object]:
    return {
        "schema_version": 1,
        "artifact_type": "monitor_alert_archive_record",
        "record_id": f"record-{index}",
        "cycle_id": "cycle-1",
        "created_at": f"2026-06-20T00:{index:02d}:00Z",
        "status": "emitted" if index < 20 else "suppressed_duplicate",
        "alert_key": f"alert-{index}",
        "decision_id": f"decision-{index}",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "priority": "p1",
        "attention_decision": "watch",
        "requires_user_attention": True,
        "suppression_reasons": [],
        "cooldown_until": "2026-06-20T00:46:00Z",
        "source_artifacts": ["runs/run-1/analysis/alert_decisions.json"],
        "personalized_context": {
            "present": True,
            "constraint_id": "personalized:BTCUSDT:1d:watch",
            "state": "watch",
            "action": "downgrade",
        },
        "source_run": {"run_id": "run-1", "run_manifest": "runs/run-1/run_manifest.json"},
    }
