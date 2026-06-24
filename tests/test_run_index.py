from __future__ import annotations

from contextlib import closing
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from halpha.config import load_config
from halpha.runtime.command_job_store import apply_command_job_migrations
from halpha.pipeline import PipelineError, run_pipeline, run_pipeline_stage
from halpha.pipeline_stages import OPERATION_ORDER
from halpha.product.product_validation_inspection import inspect_product_validation
from halpha.runtime.pipeline_contracts import RunContext
from halpha.runtime.state_store import open_runtime_state_connection
from halpha.data.run_index import (
    LATEST_REPORT_RUN_KEY,
    LATEST_RUN_KEY,
    LATEST_SUCCESSFUL_RUN_KEY,
    apply_run_index_migrations,
    inspect_indexed_manifest,
    run_index_latest_refs,
    run_index_path,
    select_latest_available_report_run,
    select_latest_run_record,
    select_previous_successful_run_record,
    write_run_index,
)


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_run_index_records_successful_run_metadata(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="refresh_data",
        stage_handlers=_noop_handlers({"collect_market_data": _market_stage}),
    )

    assert result.succeeded is True
    index_path = run_index_path(config_path)
    manifest = _manifest(result.run.manifest_path)
    assert index_path.is_file()
    assert not (tmp_path / "data" / "research" / "index.sqlite").exists()
    assert "run_index" not in manifest
    assert "research_data_catalog" not in manifest
    assert "outcome_history" not in manifest
    assert not (tmp_path / "data" / "research" / "metadata" / "research_data_catalog.json").exists()
    assert not (tmp_path / "data" / "research" / "metadata" / "outcome_history_state.json").exists()

    with closing(sqlite3.connect(index_path)) as connection:
        run_row = connection.execute(
            """
            SELECT run_id, run_dir, config_path, status, codex_status, manifest_path
            FROM runs
            WHERE run_id = ?
            """,
            (result.run.run_id,),
        ).fetchone()
        latest = dict(connection.execute("SELECT key, run_id FROM run_latest").fetchall())
        task_count = connection.execute(
            "SELECT COUNT(*) FROM run_tasks WHERE run_id = ?",
            (result.run.run_id,),
        ).fetchone()[0]
        artifacts = connection.execute(
            "SELECT artifact_key, path, kind FROM run_artifacts WHERE run_id = ? ORDER BY artifact_key",
            (result.run.run_id,),
        ).fetchall()

    assert run_row == (
        result.run.run_id,
        f"runs/{result.run.run_id}",
        "config.yaml",
        "succeeded",
        "not_run",
        f"runs/{result.run.run_id}/run_manifest.json",
    )
    assert latest["latest_run"] == result.run.run_id
    assert latest["latest_successful_run"] == result.run.run_id
    assert task_count == len(manifest["task_order"])
    assert ("market", "raw/market.json", "raw") in artifacts
    assert not any(artifact[0] == "run_index" for artifact in artifacts)


def test_run_index_records_failed_runs(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        stage_handlers={"collect_market_data": _failed_stage},
    )

    assert result.succeeded is False
    with closing(sqlite3.connect(run_index_path(config_path))) as connection:
        row = connection.execute(
            "SELECT status, failed_stage, error_count FROM runs WHERE run_id = ?",
            (result.run.run_id,),
        ).fetchone()
        task_row = connection.execute(
            "SELECT status, error_count FROM run_tasks WHERE run_id = ? AND task_name = ?",
            (result.run.run_id, "collect_market_data"),
        ).fetchone()
        latest = dict(connection.execute("SELECT key, run_id FROM run_latest").fetchall())

    assert row == ("failed", "collect_market_data", 1)
    assert task_row == ("failed", 1)
    assert latest["latest_run"] == result.run.run_id
    assert "latest_successful_run" not in latest


def test_run_index_records_derived_stage_rerun_without_duplicate_rows(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    initial = run_pipeline(
        config,
        config_path=config_path,
        until_stage="refresh_data",
        stage_handlers=_noop_handlers(
            {
                "collect_market_data": _market_stage,
                "collect_text_events": _text_stage,
            }
        ),
    )

    result = run_pipeline_stage(
        config,
        config_path=config_path,
        run_dir=initial.run.run_dir,
        stage="build_source_evidence",
        stage_handlers=_noop_handlers(),
    )

    assert result.succeeded is True
    assert result.run.run_id != initial.run.run_id
    manifest = _manifest(result.run.manifest_path)
    with closing(sqlite3.connect(run_index_path(config_path))) as connection:
        run_count = connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        stage_count = connection.execute(
            "SELECT COUNT(*) FROM run_stages WHERE run_id = ?",
            (result.run.run_id,),
        ).fetchone()[0]
        task_count = connection.execute(
            "SELECT COUNT(*) FROM run_tasks WHERE run_id = ?",
            (result.run.run_id,),
        ).fetchone()[0]
        text_artifact = connection.execute(
            """
            SELECT kind FROM run_artifacts
            WHERE run_id = ? AND artifact_key = ? AND path = ?
            """,
            (result.run.run_id, "text_events", "raw/text_events.json"),
        ).fetchone()

    assert run_count == 2
    assert stage_count == len(manifest["stages"])
    assert task_count == sum(len(stage["tasks"]) for stage in manifest["stages"])
    assert text_artifact == ("raw",)

    write_run_index(result.run, now="2026-06-05T00:00:00Z")
    with closing(sqlite3.connect(run_index_path(config_path))) as connection:
        assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 2
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM run_stages WHERE run_id = ?",
                (result.run.run_id,),
            ).fetchone()[0]
            == len(manifest["stages"])
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM run_tasks WHERE run_id = ?",
                (result.run.run_id,),
            ).fetchone()[0]
            == sum(len(stage["tasks"]) for stage in manifest["stages"])
        )


def test_run_index_query_helpers_derive_distinct_latest_states(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    available_report = _write_indexed_run(
        tmp_path,
        config_path,
        run_id="run-report-available",
        started_at="2026-06-05T00:00:00Z",
        finished_at="2026-06-05T00:05:00Z",
        report_ref="report/report.md",
        write_report=True,
    )
    missing_report = _write_indexed_run(
        tmp_path,
        config_path,
        run_id="run-report-missing",
        started_at="2026-06-05T01:00:00Z",
        finished_at="2026-06-05T01:05:00Z",
        report_ref="report/report.md",
        write_report=False,
    )
    failed_latest = _write_indexed_run(
        tmp_path,
        config_path,
        run_id="run-failed",
        status="failed",
        started_at="2026-06-05T02:00:00Z",
        finished_at="2026-06-05T02:05:00Z",
    )

    with closing(sqlite3.connect(run_index_path(config_path))) as connection:
        latest = select_latest_run_record(connection, prefer_successful=False)
        latest_successful = select_latest_run_record(connection)
        latest_report = select_latest_available_report_run(connection, base=tmp_path)
        refs = run_index_latest_refs(connection)

    assert latest is not None
    assert latest.selection_key == LATEST_RUN_KEY
    assert latest.run.run_id == failed_latest.run_id
    assert latest_successful is not None
    assert latest_successful.selection_key == LATEST_SUCCESSFUL_RUN_KEY
    assert latest_successful.run.run_id == missing_report.run_id
    assert latest_report is not None
    assert latest_report.selection_key == LATEST_REPORT_RUN_KEY
    assert latest_report.run.run_id == available_report.run_id
    assert latest_report.artifacts == {"report": "report/report.md"}
    assert refs == {
        "latest_run_id": failed_latest.run_id,
        "latest_successful_run_id": missing_report.run_id,
    }


def test_run_index_previous_successful_query_filters_artifacts(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    previous = _write_indexed_run(
        tmp_path,
        config_path,
        run_id="run-previous",
        started_at="2026-06-05T00:00:00Z",
        finished_at="2026-06-05T00:05:00Z",
        extra_artifacts={
            "market_signals": "analysis/market_signals.json",
            "raw_market": "raw/market.json",
        },
    )
    current = _write_indexed_run(
        tmp_path,
        config_path,
        run_id="run-current",
        started_at="2026-06-06T00:00:00Z",
        finished_at="2026-06-06T00:05:00Z",
    )

    with closing(sqlite3.connect(run_index_path(config_path))) as connection:
        selected = select_previous_successful_run_record(
            connection,
            current_run_id=current.run_id,
            artifact_keys={"market_signals"},
        )

    assert selected is not None
    assert selected.run.run_id == previous.run_id
    assert selected.selection_key == "latest_previous_successful_run"
    assert selected.artifacts == {"market_signals": "analysis/market_signals.json"}


def test_run_index_manifest_consistency_inspection_is_read_only(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    run = _write_indexed_run(
        tmp_path,
        config_path,
        run_id="run-1",
        started_at="2026-06-05T00:00:00Z",
        finished_at="2026-06-05T00:05:00Z",
    )
    manifest = _manifest(run.manifest_path)
    manifest["status"] = "failed"
    run.manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    with closing(sqlite3.connect(run_index_path(config_path))) as connection:
        inspection = inspect_indexed_manifest(connection, run_id=run.run_id, base=tmp_path)
        indexed_status = connection.execute("SELECT status FROM runs WHERE run_id = ?", (run.run_id,)).fetchone()[0]

    assert inspection.status == "warning"
    assert inspection.warnings == ("indexed status differs from run_manifest.json.",)
    assert inspection.errors == ()
    assert indexed_status == "succeeded"


def test_run_index_releases_sqlite_file_after_write_and_read_access(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)

    result = run_pipeline(
        config,
        config_path=config_path,
        until_stage="refresh_data",
        stage_handlers=_noop_handlers({"collect_market_data": _market_stage}),
    )

    assert result.succeeded is True
    validation = inspect_product_validation(config, config_path=config_path)
    assert validation.status == "ok"
    index_path = run_index_path(config_path)
    moved_path = index_path.with_name("index-moved.sqlite")

    index_path.rename(moved_path)
    assert moved_path.is_file()
    moved_path.unlink()
    assert not moved_path.exists()


def test_run_index_task_migration_uses_distinct_runtime_version(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)

    with closing(open_runtime_state_connection(config_path=config_path)) as connection:
        apply_command_job_migrations(connection, now="2026-06-05T00:00:00Z")
        apply_run_index_migrations(connection, now="2026-06-05T00:01:00Z")
        versions = [
            row[0]
            for row in connection.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
        ]
        run_tasks = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'run_tasks'"
        ).fetchone()

    assert versions == [1, 2, 6, 9]
    assert run_tasks == ("run_tasks",)


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
run:
  output_dir: runs
  timezone: Asia/Shanghai
market:
  enabled: true
  source: binance
  symbols:
    - BTCUSDT
text:
  enabled: true
  max_items: 1
  sources:
    - name: coindesk
      type: rss
      url: https://www.coindesk.com/arc/outboundfeeds/rss/
report:
  title: Daily Market Brief
  language: zh-CN
codex:
  enabled: false
""".strip(),
        encoding="utf-8",
    )
    return path


def _manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _market_stage(config, run) -> list[str]:
    artifact = run.raw_dir / "market.json"
    artifact.write_text("{}", encoding="utf-8")
    run.manifest["artifacts"]["market"] = "raw/market.json"
    return ["raw/market.json"]


def _text_stage(config, run) -> list[str]:
    artifact = run.raw_dir / "text_events.json"
    artifact.write_text("{}", encoding="utf-8")
    run.manifest["artifacts"]["text_events"] = "raw/text_events.json"
    return ["raw/text_events.json"]


def _noop_handlers(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    handlers = {stage: _noop_stage for stage in OPERATION_ORDER}
    if overrides:
        handlers.update(overrides)
    return handlers


def _noop_stage(config, run) -> list[str]:
    return []


def _failed_stage(config, run) -> None:
    raise PipelineError("collection failed", stage="collect_market_data", exit_code=3)


def _write_indexed_run(
    tmp_path: Path,
    config_path: Path,
    *,
    run_id: str,
    status: str = "succeeded",
    started_at: str,
    finished_at: str,
    report_ref: str | None = None,
    write_report: bool = False,
    extra_artifacts: dict[str, str] | None = None,
) -> RunContext:
    run_dir = tmp_path / "runs" / run_id
    raw_dir = run_dir / "raw"
    analysis_dir = run_dir / "analysis"
    codex_context_dir = run_dir / "codex_context"
    report_dir = run_dir / "report"
    for directory in (raw_dir, analysis_dir, codex_context_dir, report_dir):
        directory.mkdir(parents=True, exist_ok=True)
    artifacts = dict(extra_artifacts or {})
    if report_ref:
        artifacts["report"] = report_ref
        if write_report:
            report_path = run_dir / report_ref
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text("# report\n", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": finished_at,
        "status": status,
        "stages": [],
        "artifacts": artifacts,
        "warnings": [],
        "errors": [{"stage": "collect_market_data", "message": "failed"}] if status == "failed" else [],
        "codex": {"status": "skipped"},
    }
    manifest_path = run_dir / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    run = RunContext(
        run_id=run_id,
        run_dir=run_dir,
        raw_dir=raw_dir,
        analysis_dir=analysis_dir,
        codex_context_dir=codex_context_dir,
        report_dir=report_dir,
        manifest_path=manifest_path,
        config_path=config_path,
        manifest=manifest,
    )
    write_run_index(run, now=finished_at)
    return run
