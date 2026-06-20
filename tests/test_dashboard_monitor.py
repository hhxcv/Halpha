from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from halpha.config import load_config
from halpha.dashboard import create_dashboard_app
from halpha.storage import write_json


def test_dashboard_monitor_api_summarizes_complete_state_without_dumping_alerts(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    _write_complete_monitor_state(tmp_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    summary_response = client.get("/api/monitor")
    cycles_response = client.get("/api/monitor/cycles")
    alerts_response = client.get("/api/monitor/alerts")

    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["artifact_type"] == "dashboard_monitor"
    assert summary["status"] == "available"
    assert summary["health"]["fields"]["cycle_count"] == 1
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
    assert alerts["alert_archive"]["fields"]["sample_truncated"] is True
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
    assert "monitor_health_state.json was not found." in payload["warnings"]


def test_dashboard_monitor_api_reports_partial_state(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    monitor_dir = tmp_path / "runs" / "monitor"
    write_json(
        monitor_dir / "monitor_health_state.json",
        {
            "schema_version": 1,
            "artifact_type": "monitor_health_state",
            "cycle_count": 0,
            "failed_cycle_count": 0,
            "latest_cycle_id": "none",
            "latest_cycle_status": "missing",
            "alert_archive_status": "missing",
            "alert_counts": {},
            "cooldown_records": 0,
            "warning_count": 0,
            "error_count": 0,
        },
    )
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/monitor")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "partial"
    assert payload["health"]["status"] == "available"
    assert payload["cycles"]["status"] == "missing"
    assert payload["alert_archive"]["status"] == "missing"
    assert payload["cooldown"]["status"] == "missing"


def test_dashboard_monitor_api_reports_malformed_artifacts(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    monitor_dir = tmp_path / "runs" / "monitor"
    cycle_dir = monitor_dir / "cycles" / "cycle-bad"
    cycle_dir.mkdir(parents=True)
    (monitor_dir / "monitor_health_state.json").write_text("{", encoding="utf-8")
    (cycle_dir / "monitor_cycle_manifest.json").write_text("{", encoding="utf-8")
    (monitor_dir / "alert_archive_state.json").write_text("{", encoding="utf-8")
    (monitor_dir / "alert_cooldown_state.json").write_text("[]", encoding="utf-8")
    (monitor_dir / "alert_archive.jsonl").write_text("{bad json}\n", encoding="utf-8")
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/monitor")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["health"]["status"] == "failed"
    assert payload["cycles"]["status"] == "failed"
    assert payload["alert_archive"]["status"] == "partial"
    assert payload["cooldown"]["status"] == "failed"
    assert any("monitor_health_state.json is not valid JSON" in error for error in payload["errors"])
    assert any("alert_cooldown_state.json must be a JSON object" in error for error in payload["errors"])
    assert "alert_archive.jsonl line 1 is not valid JSON." in payload["warnings"]


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


def _write_complete_monitor_state(tmp_path: Path) -> None:
    monitor_dir = tmp_path / "runs" / "monitor"
    cycle_dir = monitor_dir / "cycles" / "cycle-1"
    cycle_dir.mkdir(parents=True)
    write_json(
        monitor_dir / "monitor_health_state.json",
        {
            "schema_version": 1,
            "artifact_type": "monitor_health_state",
            "updated_at": "2026-06-20T00:20:00Z",
            "cycle_count": 1,
            "failed_cycle_count": 0,
            "latest_cycle_id": "cycle-1",
            "latest_cycle_status": "succeeded",
            "latest_run_id": "run-1",
            "latest_run_manifest": "runs/run-1/run_manifest.json",
            "latest_cycle_manifest": "runs/monitor/cycles/cycle-1/monitor_cycle_manifest.json",
            "alert_archive_status": "succeeded",
            "alert_counts": {
                "records": 25,
                "emitted": 20,
                "suppressed_duplicate": 2,
                "suppressed_cooldown": 1,
                "suppressed_no_alert": 1,
                "skipped": 1,
            },
            "cooldown_records": 2,
            "warning_count": 1,
            "error_count": 0,
            "latest_loop": {"completed_cycles": 1, "stop_reason": "max_cycles_reached"},
        },
    )
    write_json(
        cycle_dir / "monitor_cycle_manifest.json",
        {
            "schema_version": 1,
            "artifact_type": "monitor_cycle_manifest",
            "cycle_id": "cycle-1",
            "cycle_mode": "loop",
            "cycle_sequence": 1,
            "status": "succeeded",
            "started_at": "2026-06-20T00:10:00Z",
            "finished_at": "2026-06-20T00:15:00Z",
            "target_stage": "build_personalized_risk_material",
            "no_codex": True,
            "exit_code": 0,
            "run_id": "run-1",
            "run_dir": "runs/run-1",
            "run_manifest": "runs/run-1/run_manifest.json",
            "product_run": {"status": "succeeded", "run_id": "run-1"},
            "alert_archive": {
                "status": "succeeded",
                "archive": "runs/monitor/alert_archive.jsonl",
                "cooldown_state": "runs/monitor/alert_cooldown_state.json",
                "counts": {
                    "records": 25,
                    "emitted": 20,
                    "suppressed_duplicate": 2,
                    "suppressed_cooldown": 1,
                    "suppressed_no_alert": 1,
                    "skipped": 1,
                },
                "warnings": [],
                "errors": [],
            },
            "source_artifacts": ["runs/run-1/analysis/alert_decisions.json"],
            "warnings": ["cycle warning"],
            "errors": [],
        },
    )
    write_json(
        monitor_dir / "alert_archive_state.json",
        {
            "schema_version": 1,
            "artifact_type": "monitor_alert_archive_state",
            "updated_at": "2026-06-20T00:16:00Z",
            "last_cycle_id": "cycle-1",
            "status": "succeeded",
            "archive": "runs/monitor/alert_archive.jsonl",
            "cooldown_state": "runs/monitor/alert_cooldown_state.json",
            "counts": {
                "records": 25,
                "emitted": 20,
                "suppressed_duplicate": 2,
                "suppressed_cooldown": 1,
                "suppressed_no_alert": 1,
                "skipped": 1,
            },
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        monitor_dir / "alert_cooldown_state.json",
        {
            "schema_version": 1,
            "artifact_type": "monitor_alert_cooldown_state",
            "updated_at": "2026-06-20T00:16:00Z",
            "cooldown_seconds": 1800,
            "record_count": 2,
            "records": {
                "alert:BTCUSDT": {"cooldown_until": "2026-06-20T00:46:00Z"},
                "alert:ETHUSDT": {"cooldown_until": "2026-06-20T00:47:00Z"},
            },
            "state_path": "runs/monitor/alert_cooldown_state.json",
        },
    )
    records = [_alert_record(index) for index in range(25)]
    (monitor_dir / "alert_archive.jsonl").write_text(
        "\n".join(json.dumps(record, sort_keys=True) for record in records) + "\n",
        encoding="utf-8",
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
            "constraint_id": "private_constraint",
            "evidence": "private evidence",
        },
        "source_run": {"run_id": "run-1", "run_manifest": "runs/run-1/run_manifest.json"},
    }
