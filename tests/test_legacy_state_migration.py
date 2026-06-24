from __future__ import annotations

from contextlib import closing
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from halpha.cli import main
from halpha.config import load_config
from halpha.dashboard.schedule_store import DashboardScheduleRepository
from halpha.dashboard.state import read_dashboard_selected_config_state
from halpha.data.run_index import apply_run_index_migrations, run_index_path
from halpha.runtime.command_job_store import CommandJobRepository
from halpha.runtime.legacy_state_migration import (
    apply_legacy_state_migration,
    legacy_state_migration_dry_run,
    rebuild_run_index_from_manifests,
)
from halpha.runtime.service_lifecycle import ServiceLifecycleRepository
from halpha.runtime.state_store import open_runtime_state_connection, runtime_state_path, runtime_state_transaction


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_legacy_state_migration_dry_run_is_read_only_and_privacy_bounded(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = _write_config(tmp_path)
    _write_legacy_selected_config(tmp_path, "config.yaml")
    schedule_path = _write_legacy_schedule(tmp_path, time_of_day="08:15")
    _write_legacy_job(tmp_path, job_id="job-1", status="running")
    before_schedule = schedule_path.read_text(encoding="utf-8")

    result = legacy_state_migration_dry_run(load_config(config_path), config_path=config_path)
    exit_code = main(["data", "migrate-state", "--config", str(config_path), "--dry-run"])
    output = capsys.readouterr().out

    assert result["mode"] == "dry_run"
    assert result["runtime_state"] == ".halpha/state.sqlite"
    assert result["counts"]["discovered_files"] == 3
    assert result["counts"]["importable_records"] == 3
    assert all(candidate["deletable"] is False for candidate in result["cleanup_plan"]["candidates"])
    assert runtime_state_path(config_path=config_path).exists() is False
    assert schedule_path.read_text(encoding="utf-8") == before_schedule
    assert str(tmp_path) not in repr(result)
    assert exit_code == 0
    assert "Halpha legacy state migration dry run succeeded." in output
    assert "runtime_state: .halpha/state.sqlite" in output
    assert str(tmp_path) not in output


def test_apply_imports_legacy_state_and_repeat_is_idempotent(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    _write_run_manifest(tmp_path, run_id="run-1", status="succeeded")
    _write_legacy_run_index(tmp_path, rows=[{"run_id": "run-1", "status": "failed", "manifest_path": "runs/run-1/run_manifest.json"}])
    _write_legacy_job(tmp_path, job_id="job-1", status="running")
    _write_legacy_schedule(tmp_path, time_of_day="08:15")
    _write_legacy_selected_config(tmp_path, "config.yaml")

    first = apply_legacy_state_migration(config, config_path=config_path, now="2026-06-24T00:00:00Z")
    second = apply_legacy_state_migration(config, config_path=config_path, now="2026-06-24T00:01:00Z")

    job = CommandJobRepository(config_path=config_path).get_job("job-1")
    schedule = DashboardScheduleRepository(config_path=config_path).get_schedule()
    selected, selected_error = read_dashboard_selected_config_state(runtime_root=tmp_path)
    with closing(sqlite3.connect(run_index_path(config_path))) as connection:
        run_row = connection.execute("SELECT status, manifest_path FROM runs WHERE run_id = 'run-1'").fetchone()
        job_count = connection.execute("SELECT COUNT(*) FROM local_command_jobs WHERE job_id = 'job-1'").fetchone()[0]
        source_rows = connection.execute("SELECT source_ref, status FROM legacy_state_sources ORDER BY source_ref").fetchall()

    assert first["status"] == "succeeded"
    assert first["counts"]["imported_records"] == 4
    assert first["counts"]["backups_created"] >= 4
    assert second["counts"]["imported_records"] == 0
    assert second["counts"]["duplicate_records"] >= 4
    assert run_row == ("succeeded", "runs/run-1/run_manifest.json")
    assert job is not None
    assert job["status"] == "failed"
    assert "legacy non-terminal command job had no verified live process ownership." in job["errors"]
    assert job_count == 1
    assert schedule is not None
    assert schedule["settings"]["time_of_day"] == "08:15"
    assert selected_error is None
    assert selected["status"] == "selected"
    assert (".halpha/dashboard/selected_config.json", "imported") in source_rows
    assert (tmp_path / "data" / "research" / "index.sqlite").is_file()
    assert (tmp_path / ".halpha" / "dashboard" / "jobs" / "job-1" / "job.json").is_file()


def test_legacy_schedule_requires_explicit_replacement_after_conflict(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    DashboardScheduleRepository(config_path=config_path).save_schedule(
        _schedule_payload(time_of_day="07:30", updated_at="2026-06-24T00:00:00Z")
    )
    _write_legacy_schedule(tmp_path, time_of_day="08:45")

    blocked = apply_legacy_state_migration(config, config_path=config_path, now="2026-06-24T00:01:00Z")
    still_current = DashboardScheduleRepository(config_path=config_path).get_schedule()
    replaced = apply_legacy_state_migration(
        config,
        config_path=config_path,
        replace_schedule=True,
        now="2026-06-24T00:02:00Z",
    )
    replacement = DashboardScheduleRepository(config_path=config_path).get_schedule()

    assert blocked["status"] == "partial"
    assert blocked["counts"]["conflicts"] == 1
    assert still_current is not None
    assert still_current["settings"]["time_of_day"] == "07:30"
    assert replaced["status"] == "succeeded"
    assert replacement is not None
    assert replacement["settings"]["time_of_day"] == "08:45"


def test_migration_reports_invalid_and_diagnostic_sources_without_service_resurrection(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    _write_legacy_selected_config(tmp_path, "missing.local.yaml")
    _write_legacy_run_index(
        tmp_path,
        rows=[{"run_id": "dangling-run", "status": "succeeded", "manifest_path": "runs/missing/run_manifest.json"}],
    )
    _write_legacy_service_state(tmp_path, status="running")

    dry_run = legacy_state_migration_dry_run(config, config_path=config_path)
    applied = apply_legacy_state_migration(config, config_path=config_path, now="2026-06-24T00:00:00Z")
    service = ServiceLifecycleRepository(runtime_root=tmp_path).inspect("dashboard")

    selected_source = next(source for source in dry_run["sources"] if source["source_type"] == "legacy_dashboard_selected_config")
    run_index_source = next(source for source in dry_run["sources"] if source["source_type"] == "legacy_run_index")
    service_source = next(source for source in dry_run["sources"] if source["source_type"] == "legacy_dashboard_service_state")
    assert dry_run["counts"]["invalid_records"] == 1
    assert dry_run["counts"]["diagnostic_records"] == 2
    assert selected_source["status"] == "invalid"
    assert run_index_source["records"][0]["status"] == "diagnostic"
    assert service_source["records"][0]["legacy_status"] == "running"
    assert service_source["records"][0]["status"] == "diagnostic"
    assert applied["counts"]["imported_records"] == 0
    assert service.status == "not_found"
    assert str(tmp_path) not in repr(dry_run)
    assert (tmp_path / ".halpha" / "dashboard" / "service_state.json").is_file()


def test_monitor_archive_and_cooldown_imports_are_idempotent(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    _write_monitor_cycle(tmp_path, cycle_id="cycle-1")
    _write_alert_archive(tmp_path)
    _write_cooldown_state(tmp_path, cooldown_until="2026-06-24T01:00:00Z")

    first = apply_legacy_state_migration(config, config_path=config_path, now="2026-06-24T00:00:00Z")
    _write_cooldown_state(tmp_path, cooldown_until="2026-06-24T02:00:00Z")
    second = apply_legacy_state_migration(config, config_path=config_path, now="2026-06-24T00:01:00Z")

    with closing(sqlite3.connect(runtime_state_path(config_path=config_path))) as connection:
        alert_count = connection.execute("SELECT COUNT(*) FROM monitor_alert_records").fetchone()[0]
        cooldown_until = connection.execute(
            "SELECT cooldown_until FROM monitor_alert_cooldowns WHERE alert_key = 'BTCUSDT:1d'"
        ).fetchone()[0]

    cooldown_source = next(source for source in second["sources"] if source["source_type"] == "legacy_monitor_cooldowns")
    assert first["status"] == "succeeded"
    assert "1 malformed alert archive line(s) were skipped." in first["warnings"]
    assert not any(ref.endswith("monitor_cycle_manifest.json") for ref in first["backup"]["refs"])
    assert alert_count == 1
    assert cooldown_until == "2026-06-24T01:00:00Z"
    assert cooldown_source["apply_result"]["duplicate_records"] == 1


def test_rebuild_run_index_from_manifests_replaces_stale_rows(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    _write_run_manifest(tmp_path, run_id="run-1", status="succeeded")
    with closing(open_runtime_state_connection(config_path=config_path)) as connection:
        apply_run_index_migrations(connection, now="2026-06-24T00:00:00Z")
        with runtime_state_transaction(connection):
            connection.execute(
                """
                INSERT INTO runs (
                  run_id,
                  run_dir,
                  config_path,
                  status,
                  warning_count,
                  error_count,
                  manifest_path
                )
                VALUES ('stale-run', 'runs/stale-run', 'config.yaml', 'failed', 0, 0, 'runs/stale-run/run_manifest.json')
                """
            )

    result = rebuild_run_index_from_manifests(config, config_path=config_path, now="2026-06-24T00:01:00Z")
    exit_code = main(["data", "rebuild-index", "--config", str(config_path)])
    output = capsys.readouterr().out

    with closing(sqlite3.connect(run_index_path(config_path))) as connection:
        run_ids = [row[0] for row in connection.execute("SELECT run_id FROM runs ORDER BY run_id").fetchall()]

    assert result["status"] == "succeeded"
    assert result["counts"] == {"run_manifests": 1, "rebuilt_runs": 1, "diagnostics": 0}
    assert run_ids == ["run-1"]
    assert exit_code == 0
    assert "Halpha run index rebuild succeeded." in output
    assert "rebuilt_runs: 1" in output


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
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
monitor:
  output_dir: runs/monitor
""".strip(),
        encoding="utf-8",
    )
    return config_path


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return path


def _write_legacy_selected_config(tmp_path: Path, config_ref: str) -> Path:
    return _write_json(tmp_path / ".halpha" / "dashboard" / "selected_config.json", {"config_path": config_ref})


def _write_legacy_schedule(tmp_path: Path, *, time_of_day: str) -> Path:
    return _write_json(
        tmp_path / ".halpha" / "dashboard" / "schedules" / "daily_report_schedule.json",
        _schedule_payload(time_of_day=time_of_day, updated_at="2026-06-23T00:00:00Z"),
    )


def _schedule_payload(*, time_of_day: str, updated_at: str) -> dict[str, Any]:
    return {
        "schedule_id": "daily_report",
        "schedule_kind": "daily_report",
        "enabled": True,
        "status": "available",
        "settings": {"time_of_day": time_of_day, "timezone": "UTC", "job_intent": "run_no_codex"},
        "created_at": "2026-06-23T00:00:00Z",
        "updated_at": updated_at,
        "codex_authorization": {"authorized": False},
    }


def _write_legacy_job(tmp_path: Path, *, job_id: str, status: str) -> Path:
    return _write_json(
        tmp_path / ".halpha" / "dashboard" / "jobs" / job_id / "job.json",
        {
            "job_id": job_id,
            "kind": "command",
            "intent": "validate",
            "requested_by": "Dashboard",
            "config_ref": "config.yaml",
            "status": status,
            "created_at": "2026-06-23T00:00:00Z",
            "updated_at": "2026-06-23T00:01:00Z",
            "pid": 12345,
            "command": ["python", "-m", "halpha", "validate", "--config", "config.yaml"],
            "job_dir": f".halpha/dashboard/jobs/{job_id}",
            "logs": {"stdout_ref": f".halpha/dashboard/jobs/{job_id}/stdout.log"},
        },
    )


def _write_legacy_service_state(tmp_path: Path, *, status: str) -> Path:
    return _write_json(
        tmp_path / ".halpha" / "dashboard" / "service_state.json",
        {
            "status": status,
            "pid": 12345,
            "instance_id": "legacy-dashboard",
            "updated_at": "2026-06-23T00:00:00Z",
        },
    )


def _write_run_manifest(tmp_path: Path, *, run_id: str, status: str) -> Path:
    run_dir = tmp_path / "runs" / run_id
    return _write_json(
        run_dir / "run_manifest.json",
        {
            "schema_version": 1,
            "run_id": run_id,
            "status": status,
            "started_at": "2026-06-23T00:00:00Z",
            "finished_at": "2026-06-23T00:05:00Z",
            "codex": {"status": "not_run"},
            "stages": [
                {
                    "name": "refresh_data",
                    "status": status,
                    "started_at": "2026-06-23T00:00:00Z",
                    "finished_at": "2026-06-23T00:05:00Z",
                    "tasks": [{"name": "collect_market_data", "status": status, "artifacts": []}],
                }
            ],
            "artifacts": {"manifest": "run_manifest.json"},
            "warnings": [],
            "errors": [],
        },
    )


def _write_legacy_run_index(tmp_path: Path, *, rows: list[dict[str, Any]]) -> Path:
    path = tmp_path / "data" / "research" / "index.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(
            """
            CREATE TABLE runs (
              run_id TEXT,
              status TEXT,
              manifest_path TEXT,
              started_at TEXT,
              finished_at TEXT
            )
            """
        )
        for row in rows:
            connection.execute(
                "INSERT INTO runs (run_id, status, manifest_path, started_at, finished_at) VALUES (?, ?, ?, ?, ?)",
                (
                    row.get("run_id"),
                    row.get("status"),
                    row.get("manifest_path"),
                    row.get("started_at", "2026-06-22T00:00:00Z"),
                    row.get("finished_at", "2026-06-22T00:01:00Z"),
                ),
            )
        connection.commit()
    return path


def _write_monitor_cycle(tmp_path: Path, *, cycle_id: str) -> Path:
    return _write_json(
        tmp_path / "runs" / "monitor" / "cycles" / cycle_id / "monitor_cycle_manifest.json",
        {
            "cycle_id": cycle_id,
            "monitor_output_dir": "runs/monitor",
            "cycle_mode": "once",
            "trigger_source": "cli",
            "status": "succeeded",
            "started_at": "2026-06-24T00:00:00Z",
            "finished_at": "2026-06-24T00:01:00Z",
            "updated_at": "2026-06-24T00:01:00Z",
            "config_ref": "config.yaml",
            "target_stage": "build_materials",
            "no_codex": True,
            "alert_archive": {"status": "succeeded", "counts": {"records": 1, "emitted": 1}},
        },
    )


def _write_alert_archive(tmp_path: Path) -> Path:
    path = tmp_path / "runs" / "monitor" / "alert_archive.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "record_id": "alert-1",
        "cycle_id": "cycle-1",
        "created_at": "2026-06-24T00:01:00Z",
        "status": "emitted",
        "alert_key": "BTCUSDT:1d",
        "decision_id": "decision-1",
        "symbol": "BTCUSDT",
        "timeframe": "1d",
        "priority": "P1",
        "attention_decision": "watch",
        "requires_user_attention": True,
        "suppression_reasons": [],
        "source_artifacts": ["analysis/alert_decisions.json"],
    }
    path.write_text(
        "\n".join([json.dumps(record, sort_keys=True), json.dumps(record, sort_keys=True), "{not-json"]),
        encoding="utf-8",
    )
    return path


def _write_cooldown_state(tmp_path: Path, *, cooldown_until: str) -> Path:
    return _write_json(
        tmp_path / "runs" / "monitor" / "alert_cooldown_state.json",
        {
            "cooldown_records": {
                "BTCUSDT:1d": {
                    "cooldown_until": cooldown_until,
                    "last_emitted_at": "2026-06-24T00:01:00Z",
                    "last_record_id": "alert-1",
                    "decision_id": "decision-1",
                    "priority": "P1",
                    "attention_decision": "watch",
                    "source_artifacts": ["analysis/alert_decisions.json"],
                }
            }
        },
    )
