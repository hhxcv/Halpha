from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from halpha.config import load_config
from halpha.dashboard import create_dashboard_app
from halpha.data.collection_coverage import write_collection_coverage_state
from halpha.market.ohlcv_store import OHLCVParquetStore
from halpha.pipeline import RunContext
from halpha.text.text_event_history import write_text_event_history


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_dashboard_data_viewer_summary_and_timeline_show_coverage_states(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    write_collection_coverage_state(
        config_path,
        [
            {
                "data_type": "ohlcv",
                "source": "binance",
                "identity": {"symbol": "BTCUSDT", "timeframe": "1d"},
                "range_start": "2026-06-01T00:00:00Z",
                "range_end": "2026-06-02T00:00:00Z",
                "status": "collected",
                "record_count": 1,
            },
            {
                "data_type": "ohlcv",
                "source": "binance",
                "identity": {"symbol": "BTCUSDT", "timeframe": "1d"},
                "range_start": "2026-06-02T00:00:00Z",
                "range_end": "2026-06-03T00:00:00Z",
                "status": "failed",
                "errors": [{"message": "source timeout"}],
            },
            {
                "data_type": "text_event",
                "source": "coindesk",
                "identity": {"source_name": "coindesk"},
                "range_start": "2026-06-01T00:00:00Z",
                "range_end": "2026-06-02T00:00:00Z",
                "status": "no_data",
            },
        ],
        now="2026-06-04T00:00:00Z",
    )
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    summary_response = client.get("/api/data/viewer/summary")
    timeline_response = client.post(
        "/api/data/viewer/timeline",
        json={
            "data_type": "ohlcv",
            "source": "binance",
            "symbol": "BTCUSDT",
            "timeframe": "1d",
            "start": "2026-06-01T00:00:00Z",
            "end": "2026-06-04T00:00:00Z",
        },
    )

    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["artifact_type"] == "dashboard_data_viewer_summary"
    stores = {store["data_type"]: store for store in summary["stores"]}
    assert stores["ohlcv"]["coverage"]["status_counts"] == {"collected": 1, "failed": 1}
    assert stores["ohlcv"]["query_capability"]["implemented"] is True
    assert stores["ohlcv"]["export_capability"]["formats"] == ["csv", "parquet"]
    assert stores["ohlcv"]["collection_capability"]["apply_job"] is True
    assert stores["macro_calendar"]["collection_capability"]["apply_job"] is False

    assert timeline_response.status_code == 200
    timeline = timeline_response.json()
    assert timeline["artifact_type"] == "dashboard_data_coverage_timeline"
    statuses = [interval["status"] for interval in timeline["intervals"]]
    assert statuses == ["collected", "failed", "unknown"]
    assert timeline["coverage"]["failed_ranges"] == [
        {"range_start": "2026-06-02T00:00:00Z", "range_end": "2026-06-03T00:00:00Z"}
    ]
    assert timeline["coverage"]["unknown_ranges"] == [
        {"range_start": "2026-06-03T00:00:00Z", "range_end": "2026-06-04T00:00:00Z"}
    ]
    assert str(tmp_path) not in summary_response.text
    assert str(tmp_path) not in timeline_response.text


def test_dashboard_data_viewer_preview_uses_query_boundaries(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    store = OHLCVParquetStore(tmp_path / "data" / "market" / "ohlcv")
    store.write_records(
        [
            _ohlcv_record(open_time="2026-06-01T00:00:00Z", close=101),
            _ohlcv_record(open_time="2026-06-02T00:00:00Z", close=102),
            _ohlcv_record(open_time="2026-06-03T00:00:00Z", close=103),
        ]
    )
    run = _run_context(tmp_path, config_path, "run-1")
    write_text_event_history(
        {"text": {"enabled": True}},
        run,
        [
            _text_event(
                "btc-1",
                published_at="2026-06-01T00:30:00Z",
                collected_at="2026-06-01T00:31:00Z",
            ),
            _text_event(
                "late-1",
                published_at="2026-06-01T01:30:00Z",
                collected_at="2026-06-03T00:00:00Z",
            ),
        ],
        now="2026-06-03T00:00:00Z",
    )
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    ohlcv = client.post(
        "/api/data/viewer/preview",
        json={
            "data_type": "ohlcv",
            "source": "binance",
            "symbol": "BTCUSDT",
            "timeframe": "1d",
            "start": "2026-06-01T00:00:00Z",
            "end": "2026-06-04T00:00:00Z",
            "as_of": "2026-06-03T12:00:00Z",
        },
    ).json()
    text = client.post(
        "/api/data/viewer/preview",
        json={
            "data_type": "text_event",
            "source": "coindesk",
            "start": "2026-06-01T00:00:00Z",
            "end": "2026-06-02T00:00:00Z",
            "as_of": "2026-06-01T02:00:00Z",
        },
    ).json()

    assert [record["open_time"] for record in ohlcv["records"]] == [
        "2026-06-01T00:00:00Z",
        "2026-06-02T00:00:00Z",
    ]
    assert ohlcv["query"]["matched_record_count"] == 2
    assert ohlcv["omitted"]["record_limit"] == 100
    assert [record["raw_item_id"] for record in text["records"]] == ["text:coindesk:btc-1"]
    assert text["query"]["filter_diagnostics"]["as_of_excluded_record_count"] == 1


def test_dashboard_data_viewer_export_calls_shared_service_and_rejects_unsafe_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    calls: list[dict[str, Any]] = []

    def fake_export(config: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {
            "schema_version": 1,
            "artifact_type": "data_export_result",
            "status": "ok",
            "data_type": kwargs["data_type"],
            "format": kwargs["output_format"],
            "output_path": "data/exports/events.json",
            "metadata_path": None,
            "record_count": 1,
            "matched_record_count": 1,
            "truncated": False,
            "query_parameters": {
                "start": kwargs["start"],
                "end": kwargs["end"],
                "as_of": kwargs["as_of"],
            },
            "coverage_diagnostics": {"status": "not_available", "record_count": 0},
            "warnings": [],
            "errors": [],
            "source_artifacts": ["data/research/metadata/collection_coverage_state.json"],
        }

    monkeypatch.setattr("halpha.dashboard.data_viewer.export_data", fake_export)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    response = client.post(
        "/api/data/viewer/export",
        json={
            "data_type": "text_event",
            "source": "coindesk",
            "start": "2026-06-01T00:00:00Z",
            "end": "2026-06-02T00:00:00Z",
            "as_of": "2026-06-01T12:00:00Z",
            "format": "json",
            "output_path": "data/exports/events.json",
        },
    )
    blocked = client.post(
        "/api/data/viewer/export",
        json={
            "data_type": "text_event",
            "source": "coindesk",
            "start": "2026-06-01T00:00:00Z",
            "end": "2026-06-02T00:00:00Z",
            "format": "json",
            "output_path": "../outside/events.json",
        },
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["artifact_type"] == "dashboard_data_export"
    assert payload["export"]["output_path"] == "data/exports/events.json"
    assert calls[0]["as_of"] == "2026-06-01T12:00:00Z"
    assert calls[0]["output_path"] == tmp_path / "data" / "exports" / "events.json"
    assert blocked.json()["status"] == "unsupported"
    assert "output_path must be a relative path" in blocked.json()["errors"][0]
    assert len(calls) == 1
    assert str(tmp_path) not in response.text
    assert str(tmp_path) not in blocked.text


def test_dashboard_data_viewer_collection_plan_and_job_use_planner_and_allowlist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    commands: list[list[str]] = []
    stdout = "\n".join(
        [
            "Halpha data collection apply succeeded.",
            "collection_coverage: data/research/metadata/collection_coverage_state.json",
            "research_data_catalog: data/research/metadata/research_data_catalog.json",
        ]
    )

    def fake_popen(command: list[str], *args: Any, **kwargs: Any) -> _FakeProcess:
        commands.append(command)
        return _FakeProcess(stdout=stdout, stderr="", returncode=0)

    monkeypatch.setattr("halpha.runtime.command_jobs.subprocess.Popen", fake_popen)
    client = TestClient(create_dashboard_app(config, config_path=config_path))
    request = {
        "data_type": "ohlcv",
        "source": "binance",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "start": "2026-06-01T00:00:00Z",
        "end": "2026-06-03T00:00:00Z",
        "max_exact_windows": 2,
    }

    plan = client.post("/api/data/viewer/collect/plan", json=request).json()
    job_payload = client.post("/api/data/viewer/collect/jobs", json=request).json()
    completed = _wait_for_api_terminal(client, job_payload["job"]["job_id"])

    assert plan["artifact_type"] == "dashboard_data_collection_plan"
    assert plan["plan"]["strategy"] == "gap_only"
    assert plan["plan"]["planned_fetch_windows"] == [
        {
            "range_start": "2026-06-01T00:00:00Z",
            "range_end": "2026-06-03T00:00:00Z",
            "reason": "missing_coverage",
        }
    ]
    assert job_payload["artifact_type"] == "dashboard_data_collection_job"
    assert completed["status"] == "succeeded"
    assert completed["intent"] == "data_collect"
    assert completed["requested_by"] == "Dashboard"
    assert completed["command"] == [
        "python",
        "-m",
        "halpha",
        "data",
        "collect",
        "--config",
        "<external-config>",
        "--apply",
        "--data-type",
        "ohlcv",
        "--source",
        "binance",
        "--symbol",
        "BTCUSDT",
        "--timeframe",
        "1d",
        "--start",
        "2026-06-01T00:00:00Z",
        "--end",
        "2026-06-03T00:00:00Z",
        "--max-exact-windows",
        "2",
    ]
    assert completed["result_refs"]["collection_coverage"] == "data/research/metadata/collection_coverage_state.json"
    assert completed["result_refs"]["research_data_catalog"] == "data/research/metadata/research_data_catalog.json"
    assert commands


def test_dashboard_data_viewer_rejects_unsupported_requests_before_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    def fail_popen(*args: Any, **kwargs: Any) -> _FakeProcess:
        raise AssertionError("unsupported data viewer request must not start a process")

    monkeypatch.setattr("halpha.runtime.command_jobs.subprocess.Popen", fail_popen)
    client = TestClient(create_dashboard_app(config, config_path=config_path))

    preview = client.post(
        "/api/data/viewer/preview",
        json={"data_type": "outcome", "start": "2026-06-01T00:00:00Z", "end": "2026-06-02T00:00:00Z"},
    ).json()
    job = client.post(
        "/api/data/viewer/collect/jobs",
        json={
            "data_type": "macro_calendar",
            "source": "federal_reserve_fomc",
            "start": "2026-06-01T00:00:00Z",
            "end": "2026-06-02T00:00:00Z",
        },
    ).json()

    assert preview["status"] == "unsupported"
    assert "data_type must be one of" in preview["errors"][0]
    assert job["status"] == "unsupported"
    assert "currently support ohlcv and text_event" in job["errors"][0]


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
  enabled: true
  sources:
    - name: coindesk
      type: rss
      url: https://example.com/rss.xml
report:
  title: Daily Market Brief
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _run_context(tmp_path: Path, config_path: Path, run_id: str) -> RunContext:
    run_dir = tmp_path / "runs" / run_id
    raw_dir = run_dir / "raw"
    analysis_dir = run_dir / "analysis"
    codex_context_dir = run_dir / "codex_context"
    report_dir = run_dir / "report"
    for directory in (raw_dir, analysis_dir, codex_context_dir, report_dir):
        directory.mkdir(parents=True, exist_ok=True)
    return RunContext(
        run_id=run_id,
        run_dir=run_dir,
        raw_dir=raw_dir,
        analysis_dir=analysis_dir,
        codex_context_dir=codex_context_dir,
        report_dir=report_dir,
        manifest_path=run_dir / "run_manifest.json",
        config_path=config_path,
        manifest={"artifacts": {}, "counts": {}, "errors": []},
    )


def _ohlcv_record(*, open_time: str, close: float) -> dict[str, Any]:
    return {
        "source": "binance",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "open_time": open_time,
        "open": close - 1,
        "high": close + 1,
        "low": close - 2,
        "close": close,
        "volume": 10,
        "fetched_at": "2026-06-05T00:00:00Z",
    }


def _text_event(raw_id: str, *, published_at: str, collected_at: str) -> dict[str, Any]:
    return {
        "event_id": f"text_event:coindesk:{raw_id}",
        "raw_item_id": f"text:coindesk:{raw_id}",
        "input_type": "rss_item",
        "source": {"name": "coindesk", "url": "https://example.com/coindesk/rss"},
        "title": f"Bitcoin market update {raw_id}",
        "content_text": f"Bitcoin market update content {raw_id}.",
        "link": f"https://example.com/coindesk/{raw_id}",
        "canonical_url": f"https://example.com/coindesk/{raw_id}",
        "published_at": published_at,
        "collected_at": collected_at,
        "language": "en",
        "normalized_title": f"bitcoin market update {raw_id}",
        "normalized_text": f"bitcoin market update content {raw_id}.",
        "warnings": [],
        "source_artifacts": ["raw/text_events.json"],
    }


class _FakeProcess:
    def __init__(self, *, stdout: str, stderr: str, returncode: int) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.pid = 4242

    def communicate(self) -> tuple[str, str]:
        return self.stdout, self.stderr

    def terminate(self) -> None:
        self.returncode = -15


def _wait_for_api_terminal(client: TestClient, job_id: str) -> dict[str, Any]:
    for _ in range(100):
        response = client.get(f"/api/jobs/{job_id}")
        payload = response.json()
        if payload["status"] in {"succeeded", "failed", "cancelled", "unsupported", "blocked"}:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"job did not finish: {job_id}")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
