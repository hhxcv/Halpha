from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from halpha.cli import main
from halpha.config import load_config
from halpha.dashboard import create_dashboard_app, dashboard_health
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
    payload = response.json()
    assert payload["artifact_type"] == "dashboard_health"
    assert payload["service"] == "halpha_dashboard"
    assert payload["status"] == "ok"
    assert payload["local_only"] is True
    assert payload["host"] == "127.0.0.1"
    assert payload["port"] == 8765
    assert payload["config"] == {"loaded": True, "ref": "config.example.yaml"}
    assert payload["features"]["overview_api"] == "not_implemented"


def test_dashboard_health_omits_external_absolute_config_path(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    payload = dashboard_health(config, config_path=config_path)

    assert payload["config"] == {"loaded": True, "ref": "<external-config>"}
    assert str(tmp_path) not in str(payload)


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


def _write_run(tmp_path: Path, config_path: Path) -> RunContext:
    run_dir = tmp_path / "runs" / "run-1"
    raw_dir = run_dir / "raw"
    analysis_dir = run_dir / "analysis"
    codex_context_dir = run_dir / "codex_context"
    report_dir = run_dir / "report"
    for path in (raw_dir, analysis_dir, codex_context_dir, report_dir):
        path.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "run_id": "run-1",
        "status": "succeeded",
        "started_at": "2026-06-20T00:00:00Z",
        "finished_at": "2026-06-20T00:05:00Z",
        "config_path": "config.yaml",
        "stage_order": ["collect_market_data", "run_codex_report"],
        "stages": [
            {
                "name": "collect_market_data",
                "status": "succeeded",
                "started_at": "2026-06-20T00:00:00Z",
                "finished_at": "2026-06-20T00:01:00Z",
                "artifacts": [],
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
        run_id="run-1",
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
