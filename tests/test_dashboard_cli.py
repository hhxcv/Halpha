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
    assert payload["features"]["overview_api"] == "available"
    assert payload["features"]["run_history_api"] == "available"
    assert payload["features"]["artifact_preview_api"] == "available"
    assert payload["features"]["data_store_api"] == "available"
    assert payload["features"]["frontend_ui"] == "available"
    assert payload["features"]["job_runner"] == "not_implemented"


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
    assert "halpha-dashboard-app" in response.text
    assert "Operational overview" in response.text
    assert 'data-overview-endpoint="/api/overview"' in response.text
    assert 'data-runs-endpoint="/api/runs"' in response.text
    assert 'data-stores-endpoint="/api/data/stores"' in response.text
    assert 'data-preview-endpoint="/api/artifacts/preview"' in response.text
    assert "Runs &amp; reports" in response.text
    assert "Report preview" in response.text
    assert "Store coverage" in response.text
    assert "Command center" in response.text
    assert "pending" in response.text
    assert str(tmp_path) not in response.text


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
    assert len(run_list["runs"]) == 1
    listed = run_list["runs"][0]
    assert listed["run_id"] == "run-1"
    assert listed["run_dir"] == "runs/run-1"
    assert listed["status"] == "succeeded"
    assert listed["codex_status"] == "skipped"
    assert listed["manifest"] == "runs/run-1/run_manifest.json"
    assert listed["report"] == "report/report.md"

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["artifact_type"] == "dashboard_run_detail"
    assert detail["status"] == "available"
    assert detail["run_id"] == "run-1"
    assert detail["fields"]["manifest_status"] == "succeeded"
    assert detail["fields"]["report"] == "report/report.md"
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
    stores = {store["name"]: store for store in payload["stores"]}
    assert stores["research_data_catalog"]["status"] == "skipped"
    assert stores["run_index"]["status"] == "skipped"
    assert stores["text_event_history"]["status"] == "skipped"
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
    assert run_index["fields"]["runs"] == 1
    assert run_index["preview_path"] is None

    ohlcv = stores["ohlcv_history"]
    assert ohlcv["status"] == "ok"
    assert ohlcv["fields"]["records"] == 3
    assert ohlcv["preview_path"] == "data/market/metadata/ohlcv_sync_state.json"

    derivatives = stores["derivatives_market_history"]
    assert derivatives["status"] == "ok"
    assert derivatives["fields"]["records"] == 4

    macro = stores["macro_calendar_history"]
    assert macro["fields"]["records"] == 5

    onchain = stores["onchain_flow_history"]
    assert onchain["fields"]["records"] == 6

    text = stores["text_event_history"]
    assert text["fields"]["records"] == 2

    outcome = stores["outcome_history"]
    assert outcome["fields"]["records"] == 2
    assert outcome["fields"]["history"] == "data/research/outcomes/outcome_history.json"
    assert outcome["preview_path"] == "data/research/metadata/outcome_history_state.json"
    assert "data/research/outcomes/outcome_history.json" not in payload["source_artifacts"]
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
            "warnings": [],
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
            "items": [{"source": "binance", "symbol": "BTCUSDT", "timeframe": "1d", "row_count": 3}],
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
            "source_artifacts": ["runs/run-1/analysis/outcome_evaluations.json"],
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
