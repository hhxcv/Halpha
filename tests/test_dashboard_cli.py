from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient

from halpha.cli import main
from halpha.config import load_config
from halpha.dashboard import create_dashboard_app, dashboard_display_timezone, dashboard_health
from halpha.pipeline import RunContext
from halpha.run_index import write_run_index
from halpha.storage import write_json


def test_dashboard_help_mentions_local_server(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["dashboard", "--help"])

    output = capsys.readouterr().out
    assert exc.value.code == 0
    assert "Run the local web dashboard." in output
    assert "--config" in output
    assert "--host" in output
    assert "--port" in output


def test_dashboard_health_endpoint_uses_bounded_config_ref() -> None:
    config_path = Path("config.example.yaml")
    config = load_config(config_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, max-age=0"
    payload = response.json()
    assert payload["artifact_type"] == "dashboard_health"
    assert payload["service"] == "halpha_dashboard"
    assert payload["status"] == "ok"
    assert payload["local_only"] is True
    assert payload["host"] == "127.0.0.1"
    assert payload["port"] == 8765
    assert payload["config"] == {"loaded": True, "ref": "config.example.yaml"}
    assert payload["features"]["overview_api"] == "available"
    assert payload["features"]["run_history_api"] == "available"
    assert payload["features"]["artifact_preview_api"] == "available"
    assert payload["features"]["data_store_api"] == "available"
    assert payload["features"]["data_deletion_api"] == "available"
    assert payload["features"]["config_profile_api"] == "available"
    assert payload["features"]["strategy_research_api"] == "available"
    assert payload["features"]["monitor_api"] == "available"
    assert payload["features"]["text_intelligence_api"] == "available"
    assert payload["features"]["schedule_api"] == "available"
    assert payload["features"]["frontend_ui"] == "available"
    assert payload["features"]["job_runner"] == "available"


def test_dashboard_health_omits_external_absolute_config_path(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    payload = dashboard_health(config, config_path=config_path)

    assert payload["config"] == {"loaded": True, "ref": "<external-config>"}
    assert str(tmp_path) not in str(payload)


def test_dashboard_root_serves_operational_overview_shell(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.headers["pragma"] == "no-cache"
    assert "halpha-dashboard-app" in response.text
    assert "System status, reports, monitor, and data health" in response.text
    assert "refreshCurrentView" in response.text
    assert 'data-overview-endpoint="/api/overview"' in response.text
    assert 'data-text-intelligence-endpoint="/api/text-intelligence"' in response.text
    assert 'data-runs-endpoint="/api/runs"' in response.text
    assert 'data-stores-endpoint="/api/data/stores"' in response.text
    assert 'data-delete-endpoint="/api/data/deletion"' in response.text
    assert 'data-strategies-endpoint="/api/strategies"' in response.text
    assert 'data-monitor-endpoint="/api/monitor"' in response.text
    assert 'data-jobs-endpoint="/api/jobs"' in response.text
    assert 'data-schedule-endpoint="/api/schedule/daily-report"' in response.text
    assert 'data-settings-endpoint="/api/config/profile"' in response.text
    assert 'data-preview-endpoint="/api/artifacts/preview"' in response.text
    assert 'data-display-timezone="Asia/Shanghai"' in response.text
    assert '<strong id="display-timezone">Asia/Shanghai</strong>' in response.text
    assert "formatTimestamp(value)" in response.text
    assert 'href="#overview" data-view-target="overview"' in response.text
    assert 'href="#reports" data-view-target="reports"' in response.text
    assert 'href="#strategies" data-view-target="strategies"' in response.text
    assert 'href="#monitor" data-view-target="monitor"' in response.text
    assert 'href="#intelligence" data-view-target="intelligence"' in response.text
    assert 'href="#settings" data-view-target="settings"' in response.text
    assert 'href="#artifacts"' not in response.text
    assert 'href="#commands"' not in response.text
    assert "Report operations" in response.text
    assert "All reports" in response.text
    assert "Report outline" in response.text
    assert "Markdown" not in response.text
    assert "Backtest candlestick chart" in response.text
    assert "Strategy parameters" in response.text
    assert "Monitor timeline" in response.text
    assert "Controls" in response.text
    assert "Intelligence" in response.text
    assert "Topic volume over time" in response.text
    assert "Settings" in response.text
    assert "Config file" in response.text
    assert "Storage maintenance" in response.text
    assert "DELETE RUN DATA" in response.text
    assert "empty-state" in response.text
    assert "No monitor cycles yet" in response.text
    assert "Dry run" in response.text
    assert "Run one cycle" in response.text
    assert "Run backtest" in response.text
    assert "Generate report" in response.text
    assert "Save changes" in response.text
    assert "Config save is staged" not in response.text
    assert str(tmp_path) not in response.text


def test_dashboard_root_uses_configured_display_timezone(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "market:\n",
            "dashboard:\n  display_timezone: UTC\n\nmarket:\n",
        ),
        encoding="utf-8",
    )
    config = load_config(config_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/")

    assert response.status_code == 200
    assert 'data-display-timezone="UTC"' in response.text
    assert '<strong id="display-timezone">UTC</strong>' in response.text


def test_dashboard_display_timezone_falls_back_to_run_timezone() -> None:
    assert dashboard_display_timezone({"run": {"timezone": "UTC"}}) == "UTC"


def test_dashboard_display_timezone_defaults_to_east_8() -> None:
    assert dashboard_display_timezone({"run": {}}) == "Asia/Shanghai"
    assert dashboard_display_timezone({"dashboard": {"display_timezone": "Invalid/Zone"}, "run": {}}) == "Asia/Shanghai"


def test_dashboard_config_profile_exposes_safe_editable_fields(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/config/profile")

    assert response.status_code == 200
    payload = response.json()
    assert payload["artifact_type"] == "dashboard_config_profile"
    assert payload["status"] == "available"
    assert payload["config"]["ref"] == "<external-config>"
    assert payload["config"]["requires_confirmation"] is True
    assert "confirmation_text" not in payload["config"]
    assert payload["sections"] == [
        "General",
        "Market data",
        "Strategy",
        "Reports",
        "Monitor",
        "Intelligence sources",
        "Storage",
        "Dashboard",
    ]
    fields = {field["path"]: field for field in payload["fields"]}
    assert fields["dashboard.display_timezone"]["value"] == "Asia/Shanghai"
    assert fields["market.enabled"]["control"] == "toggle"
    assert fields["market.symbols"]["control"] == "tags"
    assert fields["market.ohlcv.timeframes"]["options"] == ["1d", "1h"]
    assert "monitor.enabled" not in fields
    assert payload["omitted"]["raw_config_text_embedded"] is False
    assert str(tmp_path) not in response.text


def test_dashboard_config_backup_endpoint_creates_bounded_backup_ref(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.post("/api/config/profile/backup", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["artifact_type"] == "dashboard_config_backup"
    assert payload["status"] == "succeeded"
    assert payload["backup_ref"].startswith("runs/dashboard/config_backups/config-")
    assert (tmp_path / payload["backup_ref"]).exists()
    assert str(tmp_path) not in response.text


def test_dashboard_config_save_validates_and_updates_current_config(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.post(
        "/api/config/profile",
        json={
            "confirm": True,
            "changes": {
                "dashboard.display_timezone": "UTC",
                "monitor.interval_seconds": 600,
                "text.max_items": 12,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "succeeded"
    assert payload["changed_paths"] == [
        "dashboard.display_timezone",
        "monitor.interval_seconds",
        "text.max_items",
    ]
    assert payload["backup_ref"].startswith("runs/dashboard/config_backups/config-")
    saved = load_config(config_path)
    assert saved["dashboard"]["display_timezone"] == "UTC"
    assert saved["monitor"]["interval_seconds"] == 600
    assert saved["text"]["max_items"] == 12
    assert dashboard_display_timezone(config) == "UTC"
    assert str(tmp_path) not in response.text


def test_dashboard_config_save_rejects_unknown_path_and_wrong_confirmation(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    blocked = client.post(
        "/api/config/profile",
        json={"confirm": False, "changes": {"dashboard.display_timezone": "UTC"}},
    ).json()
    failed = client.post(
        "/api/config/profile",
        json={"confirm": True, "changes": {"local.secret": "value"}},
    ).json()

    assert blocked["status"] == "blocked"
    assert failed["status"] == "failed"
    assert "local.secret is not editable" in failed["errors"][0]
    assert "dashboard" not in load_config(config_path)
    assert str(tmp_path) not in str(blocked)
    assert str(tmp_path) not in str(failed)


def test_dashboard_overview_endpoint_reports_missing_local_state(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["artifact_type"] == "dashboard_overview"
    assert payload["status"] == "partial"
    assert payload["config"] == {"loaded": True, "ref": "<external-config>"}
    sections = payload["sections"]
    assert sections["latest_run"]["status"] == "missing"
    assert sections["product_validation"]["status"] == "skipped"
    assert sections["data_quality"]["status"] == "skipped"
    assert sections["monitor"]["status"] == "missing"
    assert sections["workbench"]["status"] == "missing"
    assert str(tmp_path) not in response.text


def test_dashboard_overview_endpoint_reads_artifact_backed_state(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    run = _write_run(tmp_path, config_path)
    _write_dashboard_source_artifacts(tmp_path, run)
    write_run_index(run, now="2026-06-20T00:05:00Z")
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "available"
    sections = payload["sections"]
    latest = sections["latest_run"]
    assert latest["status"] == "available"
    assert latest["fields"]["run_id"] == "run-1"
    assert latest["fields"]["run_dir"] == "runs/run-1"
    assert latest["fields"]["manifest"] == "runs/run-1/run_manifest.json"
    assert latest["fields"]["run_status"] == "succeeded"
    assert latest["fields"]["codex_status"] == "skipped"
    assert latest["fields"]["stage_counts"] == {"succeeded": 1, "skipped": 1}
    assert latest["fields"]["report"] == {"status": "available", "artifact": "report/report.md"}

    product = sections["product_validation"]
    assert product["status"] == "available"
    assert product["fields"]["artifact_status"] == "ok"
    assert product["fields"]["counts"]["checks"] == 1
    assert product["fields"]["check_counts"] == {"ok": 1}

    quality = sections["data_quality"]
    assert quality["status"] == "available"
    assert quality["fields"]["artifact_status"] == "ok"
    assert quality["fields"]["counts"]["checks"] == 2

    monitor = sections["monitor"]
    assert monitor["status"] == "available"
    assert monitor["fields"]["cycle_count"] == 2
    assert monitor["fields"]["alert_counts"]["emitted"] == 1

    workbench = sections["workbench"]
    assert workbench["status"] == "available"
    assert workbench["fields"]["generated_at"] == "2026-06-20T00:06:00Z"
    assert str(tmp_path) not in response.text


def test_dashboard_overview_marks_stale_workbench_summary(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    old_run = _write_run(
        tmp_path,
        config_path,
        run_id="run-1",
        started_at="2026-06-20T00:00:00Z",
        finished_at="2026-06-20T00:05:00Z",
    )
    _write_dashboard_source_artifacts(tmp_path, old_run)
    new_run = _write_run(
        tmp_path,
        config_path,
        run_id="run-2",
        started_at="2026-06-20T01:00:00Z",
        finished_at="2026-06-20T01:05:00Z",
    )
    write_run_index(old_run, now="2026-06-20T00:05:00Z")
    write_run_index(new_run, now="2026-06-20T01:05:00Z")
    write_json(
        tmp_path / "runs" / "workbench" / "latest" / "workbench_summary.json",
        {
            "artifact_type": "workbench_summary",
            "status": "available",
            "generated_at": "2026-06-20T00:06:00Z",
            "latest_run": {"fields": {"run_id": "run-1", "run_status": "succeeded"}},
            "monitor_state": {"fields": {"latest_cycle_id": "cycle-1"}},
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        tmp_path / "runs" / "monitor" / "monitor_health_state.json",
        {
            "artifact_type": "monitor_health_state",
            "cycle_count": 3,
            "failed_cycle_count": 0,
            "latest_cycle_id": "cycle-2",
            "latest_cycle_status": "succeeded",
            "latest_run_id": "run-2",
            "alert_archive_status": "ok",
            "alert_counts": {"records": 1, "emitted": 1},
            "cooldown_records": 0,
            "warning_count": 0,
            "error_count": 0,
        },
    )
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/overview")

    assert response.status_code == 200
    workbench = response.json()["sections"]["workbench"]
    assert workbench["status"] == "partial"
    assert workbench["fields"]["stale"] is True
    assert workbench["fields"]["stale_warning_count"] == 2
    assert workbench["source_artifacts"] == [
        "runs/workbench/latest/workbench_summary.json",
        "data/research/index.sqlite",
        "runs/monitor/monitor_health_state.json",
    ]
    assert workbench["warnings"] == [
        "workbench summary references run run-1, but latest run is run-2. Source: data/research/index.sqlite.",
        "workbench summary references monitor cycle cycle-1, but latest monitor cycle is cycle-2. "
        "Source: runs/monitor/monitor_health_state.json.",
    ]
    assert str(tmp_path) not in response.text


def test_dashboard_overview_endpoint_explains_product_validation_not_run(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    run = _write_run(tmp_path, config_path)
    reason = "Stopped after run_codex_report by --until."
    run.manifest["stage_order"].append("validate_product_contracts")
    run.manifest["stages"].append(
        {
            "name": "validate_product_contracts",
            "status": "not_run",
            "started_at": None,
            "finished_at": None,
            "artifacts": [],
            "reason": reason,
        }
    )
    run.manifest["artifacts"].pop("product_contract_validation")
    write_json(run.manifest_path, run.manifest)
    write_run_index(run, now="2026-06-20T00:05:00Z")
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/overview")

    assert response.status_code == 200
    product = response.json()["sections"]["product_validation"]
    assert product["status"] == "not_run"
    assert product["fields"] == {
        "artifact": "analysis/product_contract_validation.json",
        "artifact_key": "product_contract_validation",
        "stage": "validate_product_contracts",
        "stage_status": "not_run",
        "stage_reason": reason,
    }
    assert product["source_artifacts"] == ["run_manifest.json"]
    expected_warning = (
        "product_contract_validation artifact was not produced because "
        "validate_product_contracts stage is not_run."
    )
    assert product["warnings"] == [
        expected_warning,
        f"Stage reason: {reason}",
    ]
    assert product["errors"] == []
    assert str(tmp_path) not in response.text


def test_dashboard_removed_legacy_endpoints_return_not_found(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    for path in ("/api/workbench", "/api/decision-risk", "/api/event-alert", "/api/outcomes"):
        response = client.get(path)
        assert response.status_code == 404
        assert str(tmp_path) not in response.text


def test_dashboard_text_intelligence_endpoint_reports_missing_run_state(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/text-intelligence")

    assert response.status_code == 200
    payload = response.json()
    assert payload["artifact_type"] == "dashboard_text_intelligence"
    assert payload["status"] == "missing"
    assert payload["artifacts"] == []
    assert payload["commands"]["text_models_prepare"] == "available"
    assert payload["commands"]["text_intel"] == "available"
    assert "local run index was not found" in payload["warnings"][0]
    assert payload["omitted"]["full_raw_text_events_embedded"] is False
    assert payload["omitted"]["llm_generated_event_states"] is False
    assert str(tmp_path) not in response.text


def test_dashboard_text_intelligence_endpoint_summarizes_selected_run_artifacts(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    run = _write_run(tmp_path, config_path)
    run.manifest["artifacts"].update(
        {
            "raw_text_events": "raw/text_events.json",
            "text_event_records": "analysis/text_event_records.json",
            "text_entity_evidence": "analysis/text_entity_evidence.json",
            "text_event_classification_evidence": "analysis/text_event_classification_evidence.json",
            "text_event_topics": "analysis/text_event_topics.json",
            "text_event_signals": "analysis/text_event_signals.json",
            "event_intelligence_material": "analysis/event_intelligence_material.md",
        }
    )
    write_json(run.manifest_path, run.manifest)
    write_json(
        run.raw_dir / "text_events.json",
        {
            "artifact_type": "text_events_raw",
            "items": [{"title": "event one"}, {"title": "event two"}],
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        run.analysis_dir / "text_event_records.json",
        {
            "artifact_type": "text_event_records",
            "status": "ok",
            "records": [{"event_id": "event-1"}],
            "source_artifacts": ["raw/text_events.json"],
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        run.analysis_dir / "text_entity_evidence.json",
        {
            "artifact_type": "text_entity_evidence",
            "status": "ok",
            "records": [{"event_id": "event-1", "assets": ["BTC"]}],
            "source_artifacts": ["analysis/text_event_records.json"],
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        run.analysis_dir / "text_event_classification_evidence.json",
        {
            "artifact_type": "text_event_classification_evidence",
            "status": "warning",
            "records": [{"event_id": "event-1", "category": "policy"}],
            "source_artifacts": ["analysis/text_event_records.json"],
            "warnings": ["classification threshold review needed"],
            "errors": [],
        },
    )
    write_json(
        run.analysis_dir / "text_event_topics.json",
        {
            "artifact_type": "text_event_topics",
            "status": "ok",
            "topics": [{"topic_id": "topic-1"}],
            "source_artifacts": ["analysis/text_event_records.json"],
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        run.analysis_dir / "text_event_signals.json",
        {
            "artifact_type": "text_event_signals",
            "status": "ok",
            "signals": [{"signal_id": "signal-1"}],
            "counts": {"signals": 1},
            "source_artifacts": ["analysis/text_event_topics.json"],
            "warnings": [],
            "errors": [],
        },
    )
    (run.analysis_dir / "event_intelligence_material.md").write_text("# Event material\n", encoding="utf-8")
    write_run_index(run, now="2026-06-20T00:05:00Z")
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/text-intelligence", params={"run_id": "run-1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["artifact_type"] == "dashboard_text_intelligence"
    assert payload["selected_run"]["fields"]["run_id"] == "run-1"
    artifacts = {artifact["name"]: artifact for artifact in payload["artifacts"]}
    assert artifacts["raw_text_events"]["status"] == "available"
    assert artifacts["raw_text_events"]["fields"]["record_count"] == 2
    assert artifacts["text_event_classification_evidence"]["status"] == "warning"
    assert artifacts["text_event_classification_evidence"]["warnings"] == ["classification threshold review needed"]
    assert artifacts["text_event_topics"]["fields"]["record_count"] == 1
    assert artifacts["text_event_signals"]["fields"]["record_count"] == 1
    assert artifacts["event_intelligence_material"]["fields"]["preview_path"] == "runs/run-1/analysis/event_intelligence_material.md"
    assert "runs/run-1/raw/text_events.json" in payload["source_artifacts"]
    assert "runs/run-1/analysis/text_event_records.json" in payload["source_artifacts"]
    assert payload["commands"]["text_models_prepare"] == "available"
    assert payload["commands"]["text_intel"] == "available"
    assert payload["omitted"]["full_raw_text_events_embedded"] is False
    assert payload["omitted"]["full_text_intelligence_artifacts_embedded"] is False
    assert payload["omitted"]["llm_generated_event_states"] is False
    assert str(tmp_path) not in response.text


def test_dashboard_runs_endpoint_reports_missing_index(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/runs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["artifact_type"] == "dashboard_run_list"
    assert payload["status"] == "missing"
    assert payload["runs"] == []
    assert payload["warnings"] == ["local run index was not found."]
    assert str(tmp_path) not in response.text


def test_dashboard_runs_and_detail_endpoint_read_index_and_manifest(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    run = _write_run(tmp_path, config_path)
    _write_dashboard_source_artifacts(tmp_path, run)
    write_run_index(run, now="2026-06-20T00:05:00Z")
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    list_response = client.get("/api/runs")
    detail_response = client.get("/api/runs/run-1")

    assert list_response.status_code == 200
    run_list = list_response.json()
    assert run_list["artifact_type"] == "dashboard_run_list"
    assert run_list["status"] == "available"
    assert run_list["latest"] == {"latest_run_id": "run-1", "latest_successful_run_id": "run-1"}
    assert len(run_list["runs"]) == 1
    listed = run_list["runs"][0]
    assert listed["run_id"] == "run-1"
    assert listed["run_dir"] == "runs/run-1"
    assert listed["status"] == "succeeded"
    assert listed["codex_status"] == "skipped"
    assert listed["manifest"] == "runs/run-1/run_manifest.json"
    assert listed["integrity_state"] == {
        "status": "available",
        "run_dir": "runs/run-1",
        "manifest": "runs/run-1/run_manifest.json",
        "missing": [],
    }
    assert listed["latest_state"] == {"is_latest_run": True, "is_latest_successful_run": True}
    assert listed["report"] == "report/report.md"
    assert listed["report_state"] == {"status": "available", "artifact": "report/report.md"}

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["artifact_type"] == "dashboard_run_detail"
    assert detail["status"] == "available"
    assert detail["run_id"] == "run-1"
    assert detail["fields"]["manifest_status"] == "succeeded"
    assert detail["fields"]["report"] == "report/report.md"
    assert detail["fields"]["report_state"] == {"status": "available", "artifact": "report/report.md"}
    assert detail["fields"]["codex"]["status"] == "skipped"
    assert detail["stages"] == [
        {
            "index": 0,
            "name": "collect_market_data",
            "status": "succeeded",
            "started_at": "2026-06-20T00:00:00Z",
            "finished_at": "2026-06-20T00:01:00Z",
            "artifact_count": 1,
            "artifacts": [{"path": "raw/market.json", "kind": "raw"}],
            "artifact_omitted_count": 0,
            "warning_count": 0,
            "error_count": 0,
        },
        {
            "index": 1,
            "name": "run_codex_report",
            "status": "skipped",
            "started_at": "2026-06-20T00:01:00Z",
            "finished_at": "2026-06-20T00:02:00Z",
            "artifact_count": 0,
            "artifacts": [],
            "artifact_omitted_count": 0,
            "warning_count": 0,
            "error_count": 0,
        },
    ]
    assert {"key": "report", "path": "report/report.md", "kind": "report"} in detail["artifacts"]
    assert {"key": "data_quality_summary", "path": "analysis/data_quality_summary.json", "kind": "analysis"} in detail[
        "artifacts"
    ]
    assert str(tmp_path) not in detail_response.text


def test_dashboard_latest_state_distinguishes_latest_failed_from_successful(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    successful = _write_run(
        tmp_path,
        config_path,
        run_id="run-1",
        started_at="2026-06-20T00:00:00Z",
        finished_at="2026-06-20T00:05:00Z",
    )
    _write_dashboard_source_artifacts(tmp_path, successful)
    failed = _write_run(
        tmp_path,
        config_path,
        run_id="run-2",
        started_at="2026-06-20T01:00:00Z",
        finished_at="2026-06-20T01:05:00Z",
    )
    failed.manifest["status"] = "failed"
    failed.manifest["errors"] = [{"stage": "collect_market_data", "message": "source unavailable"}]
    failed.manifest["stages"][0]["status"] = "failed"
    write_json(failed.manifest_path, failed.manifest)
    write_run_index(successful, now="2026-06-20T00:05:00Z")
    write_run_index(failed, now="2026-06-20T01:05:00Z")
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    overview = client.get("/api/overview").json()
    runs = client.get("/api/runs").json()

    latest_fields = overview["sections"]["latest_run"]["fields"]
    assert latest_fields["run_id"] == "run-1"
    assert latest_fields["selection"] == {
        "key": "latest_successful_run",
        "label": "latest successful run",
        "latest_run_id": "run-2",
        "latest_successful_run_id": "run-1",
    }
    assert runs["latest"] == {"latest_run_id": "run-2", "latest_successful_run_id": "run-1"}
    assert [run["run_id"] for run in runs["runs"]] == ["run-2", "run-1"]
    assert runs["runs"][0]["latest_state"] == {"is_latest_run": True, "is_latest_successful_run": False}
    assert runs["runs"][1]["latest_state"] == {"is_latest_run": False, "is_latest_successful_run": True}
    assert str(tmp_path) not in str(overview)
    assert str(tmp_path) not in str(runs)


def test_dashboard_runs_endpoint_omits_missing_report_refs(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    run = _write_run(tmp_path, config_path)
    write_run_index(run, now="2026-06-20T00:05:00Z")
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/runs")
    detail_response = client.get("/api/runs/run-1")

    assert response.status_code == 200
    payload = response.json()
    listed = payload["runs"][0]
    assert listed["run_id"] == "run-1"
    assert listed["report"] is None
    assert listed["report_state"] == {
        "status": "missing",
        "artifact": "report/report.md",
        "warning": "recorded report artifact was not found.",
    }
    assert payload["report_diagnostics"] == [
        {"run_id": "run-1", "status": "missing", "artifact": "report/report.md"}
    ]
    assert payload["warnings"] == ["1 recorded report artifact(s) were missing and omitted from report lists."]
    detail = detail_response.json()
    assert detail["fields"]["report"] is None
    assert detail["fields"]["report_state"] == {
        "status": "missing",
        "artifact": "report/report.md",
        "warning": "recorded report artifact was not found.",
    }
    assert str(tmp_path) not in response.text
    assert str(tmp_path) not in detail_response.text


def test_dashboard_runs_endpoint_reports_dangling_index_manifest(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    run = _write_run(tmp_path, config_path)
    _write_dashboard_source_artifacts(tmp_path, run)
    write_run_index(run, now="2026-06-20T00:05:00Z")
    run.manifest_path.unlink()
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/runs")

    assert response.status_code == 200
    payload = response.json()
    listed = payload["runs"][0]
    assert payload["status"] == "partial"
    assert listed["integrity_state"] == {
        "status": "missing",
        "run_dir": "runs/run-1",
        "manifest": "runs/run-1/run_manifest.json",
        "missing": ["manifest"],
    }
    assert payload["index_diagnostics"] == [
        {
            "run_id": "run-1",
            "status": "missing",
            "missing": ["manifest"],
            "run_dir": "runs/run-1",
            "manifest": "runs/run-1/run_manifest.json",
        }
    ]
    assert payload["warnings"] == ["1 run index row(s) reference missing run artifacts."]
    assert str(tmp_path) not in response.text


def test_dashboard_run_detail_reports_empty_report_dir_as_not_generated(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    run = _write_run(tmp_path, config_path)
    run.manifest["artifacts"].pop("report")
    write_json(run.manifest_path, run.manifest)
    write_run_index(run, now="2026-06-20T00:05:00Z")
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    list_response = client.get("/api/runs")
    detail_response = client.get("/api/runs/run-1")

    assert (run.report_dir).is_dir()
    assert not (run.report_dir / "report.md").exists()
    listed = list_response.json()["runs"][0]
    assert listed["report"] is None
    assert listed["report_state"] == {"status": "skipped", "artifact": None}
    detail = detail_response.json()
    assert detail["fields"]["report"] is None
    assert detail["fields"]["report_state"] == {"status": "skipped", "artifact": None}
    assert str(tmp_path) not in detail_response.text


def test_dashboard_rejects_run_index_refs_outside_project_root(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    run = _write_run(tmp_path, config_path)
    outside_dir = tmp_path.parent / "outside-dashboard-run"
    outside_manifest = outside_dir / "run_manifest.json"
    write_json(
        outside_manifest,
        {
            "schema_version": 1,
            "run_id": "run-1",
            "status": "succeeded",
            "private_note": "outside manifest was read",
            "artifacts": {},
        },
    )
    write_run_index(run, now="2026-06-20T00:05:00Z")
    with sqlite3.connect(tmp_path / "data" / "research" / "index.sqlite") as connection:
        connection.execute(
            "UPDATE runs SET run_dir = ?, manifest_path = ? WHERE run_id = ?",
            (str(outside_dir), str(outside_manifest), "run-1"),
        )
        connection.commit()
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    list_response = client.get("/api/runs")
    detail_response = client.get("/api/runs/run-1")
    overview_response = client.get("/api/overview")
    strategies_response = client.get("/api/strategies")

    assert list_response.status_code == 200
    listed = list_response.json()["runs"][0]
    assert listed["run_dir"] == "<external-artifact>"
    assert listed["manifest"] == "<external-artifact>"

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["status"] == "failed"
    assert detail["source_artifacts"] == ["data/research/index.sqlite", "<external-artifact>"]
    assert detail["errors"] == ["external artifact reference was rejected."]

    assert overview_response.status_code == 200
    assert overview_response.json()["sections"]["latest_run"]["fields"]["manifest"] == "<external-artifact>"

    assert strategies_response.status_code == 200
    strategies = strategies_response.json()
    assert strategies["selected_run"]["manifest"] == "<external-artifact>"

    for response in (list_response, detail_response, overview_response, strategies_response):
        assert "outside manifest was read" not in response.text
        assert str(outside_dir) not in response.text
        assert str(outside_manifest) not in response.text


def test_dashboard_run_detail_reports_missing_run_id(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    run = _write_run(tmp_path, config_path)
    write_run_index(run, now="2026-06-20T00:05:00Z")
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/runs/missing-run")

    assert response.status_code == 200
    payload = response.json()
    assert payload["artifact_type"] == "dashboard_run_detail"
    assert payload["status"] == "missing"
    assert payload["run_id"] == "missing-run"
    assert payload["stages"] == []
    assert payload["artifacts"] == []
    assert payload["warnings"] == ["run id was not found in the local run index."]


def test_dashboard_artifact_preview_returns_bounded_json(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    artifact_path = tmp_path / "runs" / "run-1" / "analysis" / "sample.json"
    write_json(
        artifact_path,
        {
            "artifact_type": "sample",
            "status": "ok",
            "records": [{"index": index} for index in range(105)],
        },
    )
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/artifacts/preview", params={"path": "runs/run-1/analysis/sample.json"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["artifact_type"] == "dashboard_artifact_preview"
    assert payload["status"] == "available"
    assert payload["kind"] == "json"
    assert payload["path"] == "runs/run-1/analysis/sample.json"
    assert len(payload["preview"]["records"]) == 100
    assert payload["omitted"] == {"records.items": 5}
    assert str(tmp_path) not in response.text


def test_dashboard_artifact_preview_returns_bounded_jsonl(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    artifact_path = tmp_path / "runs" / "monitor" / "alert_archive.jsonl"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        "\n".join(f'{{"index": {index}}}' for index in range(105)) + "\n",
        encoding="utf-8",
    )
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/artifacts/preview", params={"path": "runs/monitor/alert_archive.jsonl"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "available"
    assert payload["kind"] == "jsonl"
    assert len(payload["preview"]) == 100
    assert payload["omitted"]["rows"] == 5


def test_dashboard_artifact_preview_truncates_markdown(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    artifact_path = tmp_path / "runs" / "run-1" / "report" / "report.md"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("# Report\n" + ("a" * 21_000), encoding="utf-8")
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/artifacts/preview", params={"path": "runs/run-1/report/report.md"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "available"
    assert payload["kind"] == "markdown"
    assert payload["truncated"] is True
    assert len(payload["preview"]) == 20_000


def test_dashboard_artifact_preview_rejects_unsafe_paths(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/artifacts/preview", params={"path": "../config.yaml"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "rejected"
    assert "traversal" in payload["warnings"][0]
    assert str(tmp_path) not in response.text


def test_dashboard_artifact_preview_rejects_unsupported_store_files(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    artifact_path = tmp_path / "data" / "research" / "index.sqlite"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("not a real sqlite file", encoding="utf-8")
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/artifacts/preview", params={"path": "data/research/index.sqlite"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unsupported"
    assert payload["preview"] is None
    assert "not expanded" in payload["warnings"][0]


def test_dashboard_data_stores_endpoint_reports_missing_metadata(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/data/stores")

    assert response.status_code == 200
    payload = response.json()
    assert payload["artifact_type"] == "dashboard_data_stores"
    assert payload["status"] == "partial"
    assert payload["state_scope"] == "shared_reusable_stores"
    assert payload["run_snapshot_scope"] == "not_included"
    stores = {store["name"]: store for store in payload["stores"]}
    assert stores["research_data_catalog"]["status"] == "skipped"
    assert stores["run_index"]["status"] == "skipped"
    assert stores["run_index"]["state_scope"] == "local_run_index"
    assert stores["run_index"]["source_label"] == "Local run index"
    assert stores["run_index"]["run_snapshot"] is False
    assert stores["text_event_history"]["status"] == "skipped"
    assert stores["text_event_history"]["state_scope"] == "shared_reusable_store"
    assert stores["text_event_history"]["source_label"] == "Shared reusable store"
    assert stores["text_event_history"]["run_snapshot"] is False
    assert stores["outcome_history"]["status"] == "skipped"
    assert stores["run_index"]["preview_path"] is None
    assert payload["omitted"]["full_raw_histories_embedded"] is False
    assert payload["omitted"]["sqlite_table_contents_embedded"] is False
    assert payload["omitted"]["parquet_table_contents_embedded"] is False
    assert str(tmp_path) not in response.text


def test_dashboard_data_stores_endpoint_reads_available_metadata(tmp_path: Path) -> None:
    config_path = _write_data_store_config(tmp_path)
    config = load_config(config_path)
    run = _write_run(tmp_path, config_path)
    write_run_index(run, now="2026-06-20T00:05:00Z")
    _write_dashboard_data_store_metadata(tmp_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/data/stores")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "available"
    stores = {store["name"]: store for store in payload["stores"]}

    catalog = stores["research_data_catalog"]
    assert catalog["status"] == "ok"
    assert catalog["fields"]["stores"] == 7
    assert catalog["preview_path"] == "data/research/metadata/research_data_catalog.json"

    run_index = stores["run_index"]
    assert run_index["status"] == "ok"
    assert run_index["state_scope"] == "local_run_index"
    assert run_index["source_label"] == "Local run index"
    assert run_index["fields"]["runs"] == 1
    assert run_index["drilldown"]["category"] == "system"
    assert run_index["drilldown"]["omitted"]["sqlite_table_contents_embedded"] is False
    assert run_index["preview_path"] is None

    ohlcv = stores["ohlcv_history"]
    assert ohlcv["status"] == "ok"
    assert ohlcv["state_scope"] == "shared_reusable_store"
    assert ohlcv["source_label"] == "Shared reusable store"
    assert ohlcv["fields"]["records"] == 3
    assert ohlcv["drilldown"]["category"] == "market"
    assert ohlcv["drilldown"]["dimensions"]["symbols"] == "BTCUSDT"
    assert ohlcv["drilldown"]["dimensions"]["timeframes"] == "1d"
    assert ohlcv["drilldown"]["groups"][0]["row_count"] == 3
    assert ohlcv["drilldown"]["groups"][0]["first_open_time"] == "2026-06-18T00:00:00Z"
    assert ohlcv["preview_path"] == "data/market/metadata/ohlcv_sync_state.json"

    derivatives = stores["derivatives_market_history"]
    assert derivatives["status"] == "ok"
    assert derivatives["fields"]["records"] == 4
    assert derivatives["drilldown"]["category"] == "derivatives"
    assert derivatives["drilldown"]["groups"][0]["source"] == "binance_usdm"

    macro = stores["macro_calendar_history"]
    assert macro["fields"]["records"] == 5
    assert macro["drilldown"]["category"] == "macro_calendar"
    assert macro["drilldown"]["dimensions"]["regions"] == "US"

    onchain = stores["onchain_flow_history"]
    assert onchain["fields"]["records"] == 6
    assert onchain["drilldown"]["category"] == "onchain"
    assert onchain["drilldown"]["dimensions"]["assets"] == "BTC"

    text = stores["text_event_history"]
    assert text["fields"]["records"] == 2
    assert text["drilldown"]["category"] == "text"
    assert text["drilldown"]["dimensions"]["sources"] == "coindesk"
    assert text["drilldown"]["warnings"] == ["text history is stale"]

    outcome = stores["outcome_history"]
    assert outcome["fields"]["records"] == 2
    assert outcome["fields"]["history"] == "data/research/outcomes/outcome_history.json"
    assert outcome["drilldown"]["category"] == "outcome"
    assert outcome["drilldown"]["dimensions"]["outcome_states"] == "confirmed"
    assert outcome["preview_path"] == "data/research/metadata/outcome_history_state.json"
    assert "data/research/outcomes/outcome_history.json" not in payload["source_artifacts"]
    assert str(tmp_path) not in response.text


def test_dashboard_data_deletion_plan_separates_run_and_shared_data(tmp_path: Path) -> None:
    config_path = _write_data_store_config(tmp_path)
    config = load_config(config_path)
    run = _write_run(tmp_path, config_path)
    _write_dashboard_source_artifacts(tmp_path, run)
    write_run_index(run, now="2026-06-20T00:05:00Z")
    _write_dashboard_data_store_metadata(tmp_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/data/deletion")

    assert response.status_code == 200
    payload = response.json()
    assert payload["artifact_type"] == "dashboard_data_deletion_plan"
    assert payload["confirmations"]["run_artifacts"] == "DELETE RUN DATA"
    assert payload["confirmations"]["shared_data"] == "DELETE SHARED DATA"
    assert payload["run_artifacts"]["items"][0]["run_id"] == "run-1"
    assert payload["run_artifacts"]["items"][0]["run_dir"] == "runs/run-1"
    assert payload["run_artifacts"]["items"][0]["deletable"] is True
    assert payload["cleanup_candidates"]["status"] == "empty"
    assert payload["cleanup_candidates"]["items"] == []
    shared = {item["name"]: item for item in payload["shared_data"]["items"]}
    assert shared["run_index"]["delete_refs"][0]["ref"] == "data/research/index.sqlite"
    assert shared["ohlcv_history"]["deletable"] is True
    assert payload["omitted"]["absolute_local_paths_embedded"] is False
    assert str(tmp_path) not in response.text


def test_dashboard_data_deletion_plan_surfaces_cleanup_candidates(tmp_path: Path) -> None:
    config_path = _write_data_store_config(tmp_path)
    config = load_config(config_path)
    run = _write_run(tmp_path, config_path)
    write_run_index(run, now="2026-06-20T00:05:00Z")
    _write_dashboard_data_store_metadata(tmp_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/data/deletion")

    assert response.status_code == 200
    payload = response.json()
    assert payload["cleanup_candidates"]["status"] == "available"
    assert payload["cleanup_candidates"]["counts"] == {
        "items": 1,
        "run_index_refs": 0,
        "missing_report_refs": 1,
        "nested_run_roots": 0,
    }
    assert payload["cleanup_candidates"]["items"] == [
        {
            "kind": "missing_report_ref",
            "run_id": "run-1",
            "reason": "recorded report artifact is missing and omitted from report lists.",
            "missing": ["report"],
            "refs": ["report/report.md"],
        }
    ]
    assert payload["run_artifacts"]["counts"]["cleanup_candidates"] == 1
    assert str(tmp_path) not in response.text


def test_dashboard_data_deletion_plan_surfaces_nested_run_root_candidates(tmp_path: Path) -> None:
    config_path = _write_data_store_config(tmp_path)
    config = load_config(config_path)
    run = _write_run(tmp_path, config_path)
    _write_dashboard_source_artifacts(tmp_path, run)
    write_run_index(run, now="2026-06-20T00:05:00Z")
    nested_run_dir = tmp_path / "runs" / "runs" / "nested-run"
    write_json(
        nested_run_dir / "run_manifest.json",
        {
            "schema_version": 1,
            "run_id": "nested-run",
            "status": "succeeded",
            "artifacts": {},
        },
    )
    _write_dashboard_data_store_metadata(tmp_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/data/deletion")

    assert response.status_code == 200
    payload = response.json()
    assert payload["cleanup_candidates"]["counts"] == {
        "items": 1,
        "run_index_refs": 0,
        "missing_report_refs": 0,
        "nested_run_roots": 1,
    }
    assert payload["cleanup_candidates"]["items"] == [
        {
            "kind": "nested_run_root",
            "run_id": None,
            "reason": "nested run root is outside indexed run history and requires explicit review before cleanup.",
            "missing": [],
            "refs": ["runs/runs", "runs/runs/nested-run/run_manifest.json"],
            "counts": {"run_manifests": 1, "sample_refs": 1},
            "indexed": False,
        }
    ]
    assert str(tmp_path) not in response.text


def test_dashboard_data_deletion_plan_blocks_external_shared_refs(tmp_path: Path) -> None:
    config_path = _write_data_store_config(tmp_path)
    config = load_config(config_path)
    config["market"]["ohlcv"]["storage_dir"] = str(tmp_path.parent / "external_ohlcv")
    run = _write_run(tmp_path, config_path)
    write_run_index(run, now="2026-06-20T00:05:00Z")
    _write_dashboard_data_store_metadata(tmp_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/data/deletion")

    assert response.status_code == 200
    payload = response.json()
    shared = {item["name"]: item for item in payload["shared_data"]["items"]}
    ohlcv = shared["ohlcv_history"]
    assert ohlcv["deletable"] is False
    assert any(ref["ref"] == "<external-artifact>" for ref in ohlcv["delete_refs"])
    assert str(tmp_path.parent) not in response.text


def test_dashboard_data_deletion_requires_confirmation(tmp_path: Path) -> None:
    config_path = _write_data_store_config(tmp_path)
    config = load_config(config_path)
    run = _write_run(tmp_path, config_path)
    write_run_index(run, now="2026-06-20T00:05:00Z")
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.post(
        "/api/data/deletion",
        json={"kind": "run_artifacts", "run_ids": ["run-1"], "confirm": "DELETE"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked"
    assert (tmp_path / "runs" / "run-1").exists()


def test_dashboard_delete_run_artifacts_supports_multi_select_and_refreshes_latest(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    run1 = _write_run(
        tmp_path,
        config_path,
        run_id="run-1",
        started_at="2026-06-20T00:00:00Z",
        finished_at="2026-06-20T00:05:00Z",
    )
    run2 = _write_run(
        tmp_path,
        config_path,
        run_id="run-2",
        started_at="2026-06-20T01:00:00Z",
        finished_at="2026-06-20T01:05:00Z",
    )
    run3 = _write_run(
        tmp_path,
        config_path,
        run_id="run-3",
        started_at="2026-06-20T02:00:00Z",
        finished_at="2026-06-20T02:05:00Z",
    )
    write_run_index(run1, now="2026-06-20T00:05:00Z")
    write_run_index(run2, now="2026-06-20T01:05:00Z")
    write_run_index(run3, now="2026-06-20T02:05:00Z")
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.post(
        "/api/data/deletion",
        json={"kind": "run_artifacts", "run_ids": ["run-2", "run-3"], "confirm": "DELETE RUN DATA"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "succeeded"
    assert {item["id"] for item in payload["deleted"]} == {"run-2", "run-3"}
    assert (tmp_path / "runs" / "run-1").exists()
    assert not (tmp_path / "runs" / "run-2").exists()
    assert not (tmp_path / "runs" / "run-3").exists()
    runs_payload = client.get("/api/runs").json()
    assert [run["run_id"] for run in runs_payload["runs"]] == ["run-1"]
    overview = client.get("/api/overview").json()
    assert overview["sections"]["latest_run"]["fields"]["run_id"] == "run-1"
    with sqlite3.connect(tmp_path / "data" / "research" / "index.sqlite") as connection:
        assert connection.execute("SELECT COUNT(*) FROM run_artifacts").fetchone()[0] == 3


def test_dashboard_delete_shared_data_only_removes_selected_shared_refs(tmp_path: Path) -> None:
    config_path = _write_data_store_config(tmp_path)
    config = load_config(config_path)
    run = _write_run(tmp_path, config_path)
    write_run_index(run, now="2026-06-20T00:05:00Z")
    _write_dashboard_data_store_metadata(tmp_path)
    write_json(tmp_path / "data" / "market" / "ohlcv" / "sample.json", {"rows": []})
    write_json(tmp_path / "data" / "research" / "text_events" / "sample.json", {"events": []})
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.post(
        "/api/data/deletion",
        json={
            "kind": "shared_data",
            "store_names": ["ohlcv_history", "text_event_history"],
            "confirm": "DELETE SHARED DATA",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "succeeded"
    deleted_refs = {item["ref"] for item in payload["deleted"]}
    assert "data/market/metadata/ohlcv_schema.json" in deleted_refs
    assert "data/market/metadata/ohlcv_sync_state.json" in deleted_refs
    assert "data/market/ohlcv" in deleted_refs
    assert "data/research/metadata/text_event_history_state.json" in deleted_refs
    assert "data/research/text_events" in deleted_refs
    assert (tmp_path / "runs" / "run-1").exists()
    assert (tmp_path / "data" / "research" / "index.sqlite").exists()
    assert not (tmp_path / "data" / "market" / "ohlcv").exists()
    assert not (tmp_path / "data" / "research" / "text_events").exists()
    assert str(tmp_path) not in response.text


def test_dashboard_strategies_endpoint_reports_missing_strategy_artifacts(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/strategies")

    assert response.status_code == 200
    payload = response.json()
    assert payload["artifact_type"] == "dashboard_strategy_research"
    assert payload["status"] == "missing"
    assert payload["notice"] == "Strategy output is historical research material, not trading advice."
    assert payload["selected_run"]["run_id"] is None
    assert payload["pipeline"]["status"] == "missing"
    assert payload["standalone"]["status"] == "missing"
    assert payload["omitted"]["full_equity_curves_embedded"] is False
    assert payload["omitted"]["full_strategy_records_embedded"] is False
    assert payload["omitted"]["full_strategy_lifecycle_json_embedded"] is False
    assert payload["omitted"]["vectorbt_objects_embedded"] is False
    assert payload["omitted"]["trading_instructions_embedded"] is False
    assert str(tmp_path) not in response.text


def test_dashboard_strategies_endpoint_summarizes_strategy_outputs(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    run = _write_run(tmp_path, config_path)
    _write_dashboard_strategy_artifacts(run)
    _write_standalone_strategy_outputs(tmp_path)
    write_run_index(run, now="2026-06-20T00:05:00Z")
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/strategies")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "failed"
    assert payload["selected_run"]["run_id"] == "run-1"
    assert payload["pipeline"]["status"] == "warning"
    assert payload["standalone"]["status"] == "failed"
    assert payload["commands"]["backtest"] == "available"
    assert payload["commands"]["experiment"] == "available"
    assert payload["commands"]["options"]["strategy_names"] == []
    assert payload["commands"]["options"]["symbols"] == []
    assert payload["commands"]["options"]["timeframes"] == []
    assert "runs/run-1/analysis/strategy_evaluation_summary.json" in payload["source_artifacts"]

    pipeline = {item["name"]: item for item in payload["pipeline"]["artifacts"]}
    assert pipeline["strategy_benchmark_suite"]["status"] == "available"
    assert pipeline["quant_strategy_runs"]["records"]["runs"][0]["strategy_name"] == "tsmom_vol_scaled"
    evaluation = pipeline["strategy_evaluation_summary"]["records"]["records"][0]
    assert evaluation["strategy_metrics"]["net_return_pct"] == 4.2
    assert evaluation["walk_forward"]["window_count"] == 1
    assert "equity_curve" not in str(pipeline["strategy_evaluation_summary"]["records"])
    assert pipeline["strategy_experiment"]["status"] == "warning"
    assert pipeline["strategy_effectiveness_gates"]["records"]["gates"][0]["status"] == "effective"
    lifecycle = pipeline["strategy_lifecycle_state"]["records"]["lifecycle"][0]
    assert lifecycle["lifecycle_status"] == "degraded"
    assert lifecycle["degradation_state"] == "degraded"

    backtest = payload["standalone"]["backtests"][0]
    assert backtest["status"] == "failed"
    assert backtest["fields"]["evaluation_status"] == "failed"
    assert backtest["fields"]["equity_curve_points"] == 2
    assert "equity_curve" not in str(backtest["fields"]["metrics"])
    assert backtest["visualization"]["chart_type"] == "candlestick_backtest"
    assert backtest["visualization"]["status"] == "available"
    assert len(backtest["visualization"]["bars"]) == 2
    assert backtest["visualization"]["bars"][0]["open"] == 99
    assert backtest["visualization"]["markers"][0]["kind"] == "entry"
    assert len(backtest["visualization"]["equity_curve"]) == 2
    assert backtest["visualization"]["limits"]["max_bars"] == 120

    experiment = payload["standalone"]["experiments"][0]
    assert experiment["status"] == "available"
    assert experiment["fields"]["counts"]["evaluations"] == 1
    assert experiment["records"]["gates"][0]["reason_codes"] == ["benchmark_coverage_met"]
    assert str(tmp_path) not in response.text


def test_dashboard_strategies_endpoint_reports_configured_command_options() -> None:
    config_path = Path("config.example.yaml")
    config = load_config(config_path)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.get("/api/strategies")

    assert response.status_code == 200
    payload = response.json()
    assert payload["commands"]["backtest"] == "available"
    assert payload["commands"]["experiment"] == "available"
    assert payload["commands"]["options"]["strategy_names"] == [
        "bollinger_rsi_reversion",
        "breakout_atr_trend",
        "sma_cross_trend",
        "tsmom_vol_scaled",
    ]
    assert payload["commands"]["options"]["symbols"] == ["BTCUSDT", "ETHUSDT"]
    assert payload["commands"]["options"]["timeframes"] == ["1d", "1h"]


def test_dashboard_command_loads_config_and_invokes_service(
    tmp_path: Path,
    capsys,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    calls: list[dict[str, object]] = []

    def fake_run_dashboard_service(config, *, config_path, host, port):  # noqa: ANN001
        calls.append(
            {
                "config": config,
                "config_path": config_path,
                "host": host,
                "port": port,
            }
        )

    monkeypatch.setattr("halpha.cli.run_dashboard_service", fake_run_dashboard_service)

    exit_code = main(
        [
            "dashboard",
            "--config",
            str(config_path),
            "--host",
            "localhost",
            "--port",
            "9001",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Halpha dashboard starting." in output
    assert "url: http://localhost:9001" in output
    assert "config: <external-config>" in output
    assert str(tmp_path) not in output
    assert len(calls) == 1
    assert calls[0]["config_path"] == config_path
    assert calls[0]["host"] == "localhost"
    assert calls[0]["port"] == 9001


def test_dashboard_rejects_non_local_host_before_service_start(
    tmp_path: Path,
    capsys,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)

    def fail_service(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("invalid dashboard host must not start the service")

    monkeypatch.setattr("halpha.cli.run_dashboard_service", fail_service)

    exit_code = main(["dashboard", "--config", str(config_path), "--host", "0.0.0.0"])

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "Halpha dashboard failed." in output
    assert "stage: dashboard" in output
    assert "dashboard host must be local-only" in output
    assert "Halpha dashboard starting." not in output
    assert str(tmp_path) not in output


def test_dashboard_config_error_omits_external_absolute_path(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "missing.yaml"

    exit_code = main(["dashboard", "--config", str(config_path)])

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "Halpha dashboard failed." in output
    assert "stage: config" in output
    assert "config file not found: <external-config>" in output
    assert str(tmp_path) not in output


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
report:
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return path


def _write_data_store_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
run:
  output_dir: runs
  timezone: Asia/Shanghai
market:
  enabled: true
  source: binance
  proxy:
    enabled: false
  symbols:
    - BTCUSDT
  ohlcv:
    storage_dir: data/market/ohlcv
    timeframes:
      - 1d
    lookback:
      1d: 10
  derivatives:
    enabled: true
    source: binance_usdm
    symbols:
      - BTCUSDT
    data_classes:
      - funding_rate
      - open_interest
    periods:
      - 5m
    lookback:
      5m: 2
macro_calendar:
  enabled: true
  source: federal_reserve_fomc
  data_classes:
    - central_bank_event
  regions:
    - US
  lookback_days: 7
  lookahead_days: 45
onchain_flow:
  enabled: true
  source: public_aggregate
  data_classes:
    - stablecoin_supply
    - exchange_flow_availability
  assets:
    - ALL_STABLECOINS
    - BTC
  chains:
    - all
    - bitcoin
  lookback_days: 7
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
    return path


def _write_run(
    tmp_path: Path,
    config_path: Path,
    *,
    run_id: str = "run-1",
    started_at: str = "2026-06-20T00:00:00Z",
    finished_at: str = "2026-06-20T00:05:00Z",
) -> RunContext:
    run_dir = tmp_path / "runs" / run_id
    raw_dir = run_dir / "raw"
    analysis_dir = run_dir / "analysis"
    codex_context_dir = run_dir / "codex_context"
    report_dir = run_dir / "report"
    for path in (raw_dir, analysis_dir, codex_context_dir, report_dir):
        path.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "status": "succeeded",
        "started_at": started_at,
        "finished_at": finished_at,
        "config_path": "config.yaml",
        "stage_order": ["collect_market_data", "run_codex_report"],
        "stages": [
            {
                "name": "collect_market_data",
                "status": "succeeded",
                "started_at": "2026-06-20T00:00:00Z",
                "finished_at": "2026-06-20T00:01:00Z",
                "artifacts": ["raw/market.json"],
            },
            {
                "name": "run_codex_report",
                "status": "skipped",
                "started_at": "2026-06-20T00:01:00Z",
                "finished_at": "2026-06-20T00:02:00Z",
                "artifacts": [],
            },
        ],
        "artifacts": {
            "report": "report/report.md",
            "product_contract_validation": "analysis/product_contract_validation.json",
            "data_quality_summary": "analysis/data_quality_summary.json",
        },
        "counts": {},
        "codex": {"enabled": False, "status": "skipped", "exit_code": None},
        "errors": [],
    }
    run = RunContext(
        run_id=run_id,
        run_dir=run_dir,
        raw_dir=raw_dir,
        analysis_dir=analysis_dir,
        codex_context_dir=codex_context_dir,
        report_dir=report_dir,
        manifest_path=run_dir / "run_manifest.json",
        config_path=config_path,
        manifest=manifest,
    )
    write_json(run.manifest_path, run.manifest)
    return run


def _write_dashboard_data_store_metadata(tmp_path: Path) -> None:
    write_json(
        tmp_path / "data" / "research" / "metadata" / "research_data_catalog.json",
        {
            "schema_version": 1,
            "artifact_type": "research_data_catalog",
            "generated_at": "2026-06-20T00:10:00Z",
            "status": "ok",
            "stores": [
                {"name": "ohlcv_history", "status": "ok"},
                {"name": "run_index", "status": "ok"},
                {"name": "text_event_history", "status": "ok"},
                {"name": "derivatives_market_history", "status": "ok"},
                {"name": "macro_calendar_history", "status": "ok"},
                {"name": "onchain_flow_history", "status": "ok"},
                {"name": "outcome_history", "status": "ok"},
            ],
            "counts": {"stores": 7, "records": 20, "warnings": 0, "errors": 0},
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        tmp_path / "data" / "research" / "metadata" / "text_event_history_state.json",
        {
            "schema_version": 1,
            "artifact_type": "text_event_history_state",
            "status": "ok",
            "updated_at": "2026-06-20T00:10:00Z",
            "totals": {"records": 2},
            "sources": [{"source": "coindesk"}],
            "warnings": ["text history is stale"],
            "errors": [],
        },
    )
    write_json(
        tmp_path / "data" / "market" / "metadata" / "ohlcv_schema.json",
        {"schema_version": 1, "unique_key": ["source", "symbol", "timeframe", "open_time"]},
    )
    write_json(
        tmp_path / "data" / "market" / "metadata" / "ohlcv_sync_state.json",
        {
            "schema_version": 1,
            "artifact_type": "ohlcv_sync_state",
            "status": "ok",
            "updated_at": "2026-06-20T00:10:00Z",
            "items": [
                {
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "row_count": 3,
                    "first_open_time": "2026-06-18T00:00:00Z",
                    "last_open_time": "2026-06-20T00:00:00Z",
                }
            ],
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        tmp_path / "data" / "market" / "metadata" / "derivatives_market_schema.json",
        {"schema_version": 1, "unique_key": ["source", "symbol", "metric", "timestamp"]},
    )
    write_json(
        tmp_path / "data" / "market" / "metadata" / "derivatives_market_state.json",
        {
            "schema_version": 1,
            "artifact_type": "derivatives_market_state",
            "status": "ok",
            "totals": {"records": 4},
            "groups": [{"source": "binance_usdm", "symbol": "BTCUSDT"}],
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        tmp_path / "runs" / "run-1" / "raw" / "derivatives_market_views.json",
        {
            "schema_version": 1,
            "artifact_type": "derivatives_market_views",
            "views": [{"status": "ok", "included_record_count": 2}],
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        tmp_path / "data" / "macro" / "metadata" / "macro_calendar_schema.json",
        {"schema_version": 1, "unique_key": ["source", "event_id"]},
    )
    write_json(
        tmp_path / "data" / "macro" / "metadata" / "macro_calendar_state.json",
        {
            "schema_version": 1,
            "artifact_type": "macro_calendar_state",
            "status": "ok",
            "totals": {"records": 5, "duplicate_records": 0, "conflicting_duplicates": 0},
            "groups": [{"source": "federal_reserve_fomc", "region": "US"}],
            "availability": [{"status": "ok"}],
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        tmp_path / "runs" / "run-1" / "raw" / "macro_calendar_views.json",
        {
            "schema_version": 1,
            "artifact_type": "macro_calendar_views",
            "views": [{"status": "ok", "included_record_count": 3}],
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        tmp_path / "data" / "onchain" / "metadata" / "onchain_flow_schema.json",
        {"schema_version": 1, "unique_key": ["source", "asset", "metric", "timestamp"]},
    )
    write_json(
        tmp_path / "data" / "onchain" / "metadata" / "onchain_flow_state.json",
        {
            "schema_version": 1,
            "artifact_type": "onchain_flow_state",
            "status": "ok",
            "totals": {"records": 6, "duplicate_records": 0, "conflicting_duplicates": 0},
            "groups": [{"source": "public_aggregate", "asset": "BTC"}],
            "availability": [{"status": "ok"}],
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        tmp_path / "runs" / "run-1" / "raw" / "onchain_flow_views.json",
        {
            "schema_version": 1,
            "artifact_type": "onchain_flow_views",
            "views": [{"status": "ok", "included_record_count": 4}],
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        tmp_path / "data" / "research" / "metadata" / "outcome_history_state.json",
        {
            "schema_version": 1,
            "artifact_type": "outcome_history_state",
            "status": "ok",
            "updated_at": "2026-06-20T00:10:00Z",
            "history_path": "data/research/outcomes/outcome_history.json",
            "storage_path": "data/research/outcomes",
            "totals": {
                "records": 2,
                "incoming_records": 2,
                "inserted_records": 2,
                "updated_records": 0,
                "duplicate_records": 0,
                "conflicting_duplicates": 0,
                "warning_count": 0,
                "error_count": 0,
            },
            "outcome_states": [{"value": "confirmed", "record_count": 2}],
            "source_artifacts": ["runs/run-1/analysis/outcome_evaluations.json"],
            "warnings": [],
            "errors": [],
        },
    )


def _write_dashboard_strategy_artifacts(run: RunContext) -> None:
    run.manifest["artifacts"].update(
        {
            "strategy_benchmark_suite": "analysis/strategy_benchmark_suite.json",
            "quant_strategy_runs": "analysis/quant_strategy_runs.json",
            "strategy_evaluation_summary": "analysis/strategy_evaluation_summary.json",
            "strategy_experiment": "analysis/strategy_experiment.json",
            "strategy_effectiveness_gates": "analysis/strategy_effectiveness_gates.json",
            "strategy_lifecycle_state": "analysis/strategy_lifecycle_state.json",
        }
    )
    write_json(run.manifest_path, run.manifest)
    write_json(
        run.analysis_dir / "strategy_benchmark_suite.json",
        {
            "artifact_type": "strategy_benchmark_suite",
            "status": "ok",
            "coverage": {
                "benchmark_records": 1,
                "succeeded": 1,
                "insufficient_data": 0,
                "failed": 0,
            },
            "benchmarks": [
                {
                    "benchmark_id": "benchmark:BTCUSDT:1d",
                    "status": "succeeded",
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "window_identity": "configured_lookback",
                    "input_window_start": "2026-06-01T00:00:00Z",
                    "input_window_end": "2026-06-05T00:00:00Z",
                    "row_count": 5,
                }
            ],
            "source_artifacts": ["raw/market_data_views.json"],
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        run.analysis_dir / "quant_strategy_runs.json",
        {
            "artifact_type": "quant_strategy_runs",
            "status": "ok",
            "runs": [
                {
                    "strategy_run_id": "run:tsmom_vol_scaled:BTCUSDT:1d",
                    "strategy_name": "tsmom_vol_scaled",
                    "strategy_version": 2,
                    "status": "succeeded",
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "summary": {"records": 5},
                    "warnings": [],
                    "errors": [],
                }
            ],
            "source_artifacts": ["raw/market_data_views.json"],
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        run.analysis_dir / "strategy_evaluation_summary.json",
        {
            "artifact_type": "strategy_evaluation_summary",
            "status": "ok",
            "records": [
                {
                    "evaluation_id": "evaluation:tsmom_vol_scaled:BTCUSDT:1d",
                    "strategy_name": "tsmom_vol_scaled",
                    "strategy_version": 2,
                    "status": "succeeded",
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "single_window": {
                        "strategy_metrics": {"net_return_pct": 4.2, "max_drawdown_pct": -1.0},
                        "baseline_metrics": {"buy_and_hold_return_pct": 2.0},
                        "relative_metrics": {"excess_return_vs_buy_and_hold_pct": 2.2},
                        "trade_summary": {"trade_count": 3},
                        "equity_curve": [
                            {"timestamp": "2026-06-01T00:00:00Z", "equity": 10000},
                            {"timestamp": "2026-06-02T00:00:00Z", "equity": 10010},
                        ],
                    },
                    "walk_forward": {
                        "enabled": True,
                        "status": "succeeded",
                        "summary": {"window_count": 1, "result_stability": "stable"},
                        "windows": [{"window_id": "wf-1"}],
                    },
                    "parameter_stability": {"enabled": False, "status": "disabled"},
                    "overfitting_risk": {"status": "low"},
                    "assessment": {"reliability": "medium", "cost_sensitivity": "low"},
                    "warnings": [],
                    "errors": [],
                }
            ],
            "source_artifacts": ["analysis/quant_strategy_runs.json"],
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        run.analysis_dir / "strategy_experiment.json",
        {
            "artifact_type": "strategy_experiment",
            "created_at": "2026-06-20T00:04:00Z",
            "coverage": {
                "strategy_candidates": 1,
                "evaluations": 1,
                "evaluations_succeeded": 1,
                "evaluations_failed": 0,
            },
            "candidates": [
                {
                    "strategy_name": "tsmom_vol_scaled",
                    "status": "succeeded",
                    "summary": {"benchmark_records": 1, "succeeded": 1},
                    "evaluations": [{"status": "succeeded"}],
                    "warnings": [],
                    "errors": [],
                }
            ],
            "source_artifacts": ["analysis/strategy_benchmark_suite.json"],
            "warnings": [{"code": "small_sample", "message": "sample is small."}],
            "errors": [],
        },
    )
    write_json(
        run.analysis_dir / "strategy_effectiveness_gates.json",
        {
            "artifact_type": "strategy_effectiveness_gates",
            "status": "ok",
            "coverage": {
                "strategy_candidates": 1,
                "effective": 1,
                "watchlisted": 0,
                "rejected": 0,
                "insufficient_evidence": 0,
            },
            "records": [
                {
                    "gate_id": "gate:tsmom_vol_scaled:BTCUSDT:1d",
                    "strategy_name": "tsmom_vol_scaled",
                    "status": "effective",
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "reasons": [{"code": "benchmark_coverage_met"}],
                    "warnings": [],
                    "errors": [],
                }
            ],
            "source_artifacts": ["analysis/strategy_experiment.json"],
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        run.analysis_dir / "strategy_lifecycle_state.json",
        {
            "artifact_type": "strategy_lifecycle_state",
            "status": "warning",
            "counts": {"records": 1, "degraded": 1},
            "records": [
                {
                    "lifecycle_record_id": "strategy_lifecycle:tsmom_vol_scaled:BTCUSDT:1d",
                    "scope": {
                        "strategy_name": "tsmom_vol_scaled",
                        "source": "binance",
                        "symbol": "BTCUSDT",
                        "timeframe": "1d",
                    },
                    "lifecycle_status": "degraded",
                    "degradation": {"state": "degraded"},
                    "health_state": {"state": "degraded"},
                    "retirement": {"state": "not_retired"},
                    "strategy_contract_version": "2",
                    "parameter_version": "1",
                    "warnings": [],
                    "errors": [],
                }
            ],
            "source_artifacts": ["analysis/strategy_effectiveness_gates.json"],
            "warnings": [{"code": "degraded_lifecycle", "message": "lifecycle degraded."}],
            "errors": [],
        },
    )


def _write_standalone_strategy_outputs(tmp_path: Path) -> None:
    backtest_dir = tmp_path / "runs" / "strategy_backtests" / "20260620T000000Z_tsmom_binance_BTCUSDT_1d"
    write_json(
        backtest_dir / "strategy_backtest.json",
        {
            "artifact_type": "strategy_backtest",
            "status": "failed",
            "strategy_metrics": {"net_return_pct": -2.5},
            "baseline_metrics": {"buy_and_hold_return_pct": 1.0},
            "relative_metrics": {"excess_return_vs_buy_and_hold_pct": -3.5},
            "trade_summary": {"trade_count": 1},
            "sample": {"rows": 5},
            "execution_model": {"lookahead_policy": "no_same_bar_execution"},
            "cost_assumptions": {"fees_bps": 10.0},
            "equity_curve": [
                {"timestamp": "2026-06-01T00:00:00Z", "equity": 10000},
                {"timestamp": "2026-06-02T00:00:00Z", "equity": 9900},
            ],
            "visualization": {
                "schema_version": 1,
                "chart_type": "candlestick_backtest",
                "status": "available",
                "strategy_name": "tsmom_vol_scaled",
                "source": "binance",
                "symbol": "BTCUSDT",
                "timeframe": "1d",
                "bars": [
                    {
                        "time": "2026-06-01T00:00:00Z",
                        "open": 99,
                        "high": 102,
                        "low": 98,
                        "close": 100,
                        "volume": 10,
                    },
                    {
                        "time": "2026-06-02T00:00:00Z",
                        "open": 100,
                        "high": 104,
                        "low": 99,
                        "close": 103,
                        "volume": 12,
                    },
                ],
                "markers": [
                    {
                        "time": "2026-06-02T00:00:00Z",
                        "kind": "entry",
                        "label": "Long",
                        "position": 1,
                        "price": 103,
                    }
                ],
                "equity_curve": [
                    {"time": "2026-06-01T00:00:00Z", "net_equity": 1, "position": 0, "turnover": 0},
                    {"time": "2026-06-02T00:00:00Z", "net_equity": 0.99, "position": 1, "turnover": 1},
                ],
                "limits": {"max_bars": 120, "max_markers": 80},
                "omitted": {"bars": 0, "markers": 0},
                "warnings": [],
            },
            "warnings": [],
            "errors": [{"message": "strategy evaluation status is failed"}],
        },
    )
    write_json(
        backtest_dir / "manifest.json",
        {
            "artifact_type": "standalone_strategy_backtest_manifest",
            "created_at": "2026-06-20T00:00:00Z",
            "status": "failed",
            "evaluation_status": "failed",
            "inputs": {
                "strategy_name": "tsmom_vol_scaled",
                "source": "binance",
                "symbol": "BTCUSDT",
                "timeframe": "1d",
            },
            "artifacts": {
                "strategy_backtest": "strategy_backtest.json",
                "manifest": "manifest.json",
            },
            "warnings": [],
            "errors": [{"message": "strategy evaluation status is failed"}],
        },
    )

    experiment_dir = tmp_path / "runs" / "strategy_experiments" / "20260620T000000Z_strategy_experiment"
    write_json(
        experiment_dir / "strategy_benchmark_suite.json",
        {
            "artifact_type": "strategy_benchmark_suite",
            "status": "ok",
            "coverage": {"benchmark_records": 1, "succeeded": 1},
            "benchmarks": [
                {
                    "benchmark_id": "benchmark:BTCUSDT:1d",
                    "status": "succeeded",
                    "source": "binance",
                    "symbol": "BTCUSDT",
                    "timeframe": "1d",
                    "row_count": 5,
                }
            ],
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        experiment_dir / "strategy_experiment.json",
        {
            "artifact_type": "strategy_experiment",
            "coverage": {
                "strategy_candidates": 1,
                "evaluations": 1,
                "evaluations_succeeded": 1,
            },
            "candidates": [
                {
                    "strategy_name": "tsmom_vol_scaled",
                    "status": "succeeded",
                    "summary": {"benchmark_records": 1, "succeeded": 1},
                    "evaluations": [{"status": "succeeded"}],
                    "warnings": [],
                    "errors": [],
                }
            ],
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        experiment_dir / "strategy_effectiveness_gates.json",
        {
            "artifact_type": "strategy_effectiveness_gates",
            "status": "ok",
            "coverage": {"strategy_candidates": 1, "effective": 1},
            "records": [
                {
                    "gate_id": "gate:tsmom_vol_scaled:BTCUSDT:1d",
                    "strategy_name": "tsmom_vol_scaled",
                    "status": "effective",
                    "reasons": [{"code": "benchmark_coverage_met"}],
                }
            ],
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        experiment_dir / "manifest.json",
        {
            "artifact_type": "strategy_experiment_manifest",
            "created_at": "2026-06-20T00:00:00Z",
            "status": "succeeded",
            "inputs": {"strategy_names": ["tsmom_vol_scaled"], "benchmark_records": 1},
            "counts": {
                "strategy_candidates": 1,
                "evaluations": 1,
                "strategy_gate_effective": 1,
            },
            "artifacts": {
                "strategy_experiment": "strategy_experiment.json",
                "strategy_benchmark_suite": "strategy_benchmark_suite.json",
                "strategy_effectiveness_gates": "strategy_effectiveness_gates.json",
                "manifest": "manifest.json",
            },
            "warnings": [],
            "errors": [],
        },
    )


def _write_dashboard_source_artifacts(tmp_path: Path, run: RunContext) -> None:
    (run.report_dir / "report.md").write_text("# Report\n", encoding="utf-8")
    write_json(
        run.analysis_dir / "product_contract_validation.json",
        {
            "artifact_type": "product_contract_validation",
            "status": "ok",
            "counts": {"checks": 1, "ok": 1, "failed": 0},
            "checks": [{"name": "manifest", "status": "ok"}],
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        run.analysis_dir / "data_quality_summary.json",
        {
            "artifact_type": "data_quality_summary",
            "status": "ok",
            "counts": {"checks": 2, "ok": 2, "failed": 0},
            "checks": [{"name": "market", "status": "ok"}, {"name": "text", "status": "ok"}],
            "warnings": [],
            "errors": [],
        },
    )
    write_json(
        tmp_path / "runs" / "monitor" / "monitor_health_state.json",
        {
            "artifact_type": "monitor_health_state",
            "cycle_count": 2,
            "failed_cycle_count": 0,
            "latest_cycle_id": "cycle-1",
            "latest_cycle_status": "succeeded",
            "latest_run_id": "run-1",
            "alert_archive_status": "ok",
            "alert_counts": {"records": 1, "emitted": 1},
            "cooldown_records": 0,
            "warning_count": 0,
            "error_count": 0,
        },
    )
    write_json(
        tmp_path / "runs" / "workbench" / "latest" / "workbench_summary.json",
        {
            "artifact_type": "workbench_summary",
            "status": "available",
            "generated_at": "2026-06-20T00:06:00Z",
            "latest_run": {"fields": {"run_id": "run-1", "run_status": "succeeded"}},
            "warnings": [],
            "errors": [],
        },
    )
