from __future__ import annotations

from contextlib import closing
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from halpha.cli import main
from halpha.config import load_config
from halpha.data.run_archive_cleanup import (
    REPORT_ARCHIVE_DELETE_CONFIRMATION,
    apply_run_archive_cleanup,
    plan_run_archive_cleanup,
)
from halpha.data.run_index import run_index_path, write_run_index
from halpha.runtime.pipeline_contracts import RunContext
from halpha.storage import write_json


def test_run_archive_cleanup_dry_run_classifies_candidates_without_deleting(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    disposable = _write_run(
        tmp_path,
        config_path=config_path,
        run_id="validation-run",
        run_kind="validation_run",
        disposal_class="validation_archive",
        trigger={"source": "CLI", "intent": "run_until"},
    )
    report = _write_run(
        tmp_path,
        config_path=config_path,
        run_id="report-run",
        run_kind="product_report",
        disposal_class="report_archive",
        trigger={"source": "CLI", "intent": "run"},
        report=True,
    )
    _write_run(tmp_path, config_path=config_path, run_id="legacy-run", include_classification=False)
    _write_run(
        tmp_path,
        config_path=config_path,
        run_id="failed-run",
        run_kind="validation_run",
        disposal_class="validation_archive",
        trigger={"source": "CLI", "intent": "run_until"},
        status="failed",
    )
    _write_bad_manifest(tmp_path, "bad-run")
    write_run_index(disposable, now="2026-06-24T00:00:00Z")
    write_run_index(report, now="2026-06-24T00:05:00Z")

    plan = plan_run_archive_cleanup(config, config_path=config_path)
    exit_code = main(["data", "cleanup-runs", "--config", str(config_path)])
    output = capsys.readouterr().out

    candidates = {item["run_id"]: item for item in plan["candidates"]}
    diagnostics = {item.get("run_id"): item for item in plan["diagnostics"] if item.get("run_id")}
    assert exit_code == 0
    assert plan["counts"]["safe_to_delete"] == 1
    assert plan["counts"]["report_bearing"] == 1
    assert plan["counts"]["review_required"] == 3
    assert plan["counts"]["approximate_deletable_size_bytes"] > 0
    assert candidates["validation-run"]["deletable"] is True
    assert candidates["validation-run"]["report"]["status"] == "absent"
    assert candidates["validation-run"]["latest_index_refs"] == ["latest_run_id", "latest_successful_run_id"]
    assert candidates["report-run"]["deletable"] is False
    assert candidates["report-run"]["report"]["status"] == "present"
    assert diagnostics["legacy-run"]["deletion_reason"] == "unknown or legacy classification requires review."
    assert diagnostics["failed-run"]["deletion_reason"] == "run status failed requires review."
    assert diagnostics["bad-run"]["reason"] == "run_manifest.json is not valid JSON."
    assert (tmp_path / "runs" / "validation-run").is_dir()
    assert "Halpha run archive cleanup dry run succeeded." in output
    assert "candidate: validation-run category=safe_to_delete" in output
    assert "candidate: report-run category=report_bearing" in output


def test_run_archive_cleanup_apply_deletes_selected_archive_and_rebuilds_index(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    disposable = _write_run(
        tmp_path,
        config_path=config_path,
        run_id="validation-run",
        run_kind="validation_run",
        disposal_class="validation_archive",
        trigger={"source": "CLI", "intent": "run_until"},
    )
    report = _write_run(
        tmp_path,
        config_path=config_path,
        run_id="report-run",
        run_kind="product_report",
        disposal_class="report_archive",
        trigger={"source": "CLI", "intent": "run"},
        report=True,
    )
    shared_data = tmp_path / "data" / "market" / "ohlcv" / "keep.txt"
    shared_data.parent.mkdir(parents=True)
    shared_data.write_text("keep", encoding="utf-8")
    write_run_index(disposable, now="2026-06-24T00:00:00Z")
    write_run_index(report, now="2026-06-24T00:05:00Z")

    result = apply_run_archive_cleanup(config, config_path=config_path, run_ids=["validation-run"])
    exit_code = main(
        [
            "data",
            "cleanup-runs",
            "--config",
            str(config_path),
            "--apply",
            "--run-id",
            "missing-run",
        ]
    )
    output = capsys.readouterr().out

    with closing(sqlite3.connect(run_index_path(config_path))) as connection:
        rows = connection.execute("SELECT run_id FROM runs ORDER BY run_id").fetchall()

    assert result["status"] == "succeeded"
    assert result["deleted"][0]["run_id"] == "validation-run"
    assert not (tmp_path / "runs" / "validation-run").exists()
    assert (tmp_path / "runs" / "report-run").is_dir()
    assert shared_data.read_text(encoding="utf-8") == "keep"
    assert run_index_path(config_path).exists()
    assert rows == [("report-run",)]
    assert exit_code == 1
    assert "blocked: missing-run" in output
    assert main(["data", "inspect", "--config", str(config_path)]) == 0
    assert main(["run", "--config", str(config_path), "--until", "refresh_data"]) == 0


def test_report_bearing_archive_requires_stronger_confirmation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    report = _write_run(
        tmp_path,
        config_path=config_path,
        run_id="report-run",
        run_kind="product_report",
        disposal_class="report_archive",
        trigger={"source": "CLI", "intent": "run"},
        report=True,
    )
    write_run_index(report, now="2026-06-24T00:00:00Z")

    blocked = apply_run_archive_cleanup(config, config_path=config_path, run_ids=["report-run"])
    deleted = apply_run_archive_cleanup(
        config,
        config_path=config_path,
        run_ids=["report-run"],
        include_report_archives=True,
        confirm_report_deletion=REPORT_ARCHIVE_DELETE_CONFIRMATION,
    )

    with closing(sqlite3.connect(run_index_path(config_path))) as connection:
        rows = connection.execute("SELECT run_id FROM runs ORDER BY run_id").fetchall()

    assert blocked["status"] == "blocked"
    assert "report-bearing archive requires" in blocked["blocked"][0]["reason"]
    assert deleted["status"] == "succeeded"
    assert not (tmp_path / "runs" / "report-run").exists()
    assert rows == []


def test_cleanup_surfaces_dangling_and_deleted_index_refs_as_diagnostics(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    config_path = _write_config(tmp_path)
    config = load_config(config_path)
    dangling = _write_run(
        tmp_path,
        config_path=config_path,
        run_id="dangling-report-run",
        run_kind="product_report",
        disposal_class="report_archive",
        trigger={"source": "CLI", "intent": "run"},
        report=True,
        create_report=False,
    )
    deleted = _write_run(
        tmp_path,
        config_path=config_path,
        run_id="deleted-run",
        run_kind="validation_run",
        disposal_class="validation_archive",
        trigger={"source": "CLI", "intent": "run_until"},
    )
    write_run_index(dangling, now="2026-06-24T00:00:00Z")
    write_run_index(deleted, now="2026-06-24T00:05:00Z")
    shutil.rmtree(tmp_path / "runs" / "deleted-run")

    plan = plan_run_archive_cleanup(config, config_path=config_path)

    diagnostics = {item.get("run_id"): item for item in plan["diagnostics"] if item.get("run_id")}
    assert diagnostics["dangling-report-run"]["deletion_reason"] == "report artifact refs are dangling and require review."
    assert diagnostics["deleted-run"]["missing"] == ["run_dir", "manifest"]
    assert not any(item["run_id"] == "dangling-report-run" for item in plan["candidates"])


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


def _write_run(
    tmp_path: Path,
    *,
    config_path: Path,
    run_id: str,
    run_kind: str = "unknown",
    disposal_class: str = "legacy_archive",
    trigger: dict[str, Any] | None = None,
    report: bool = False,
    create_report: bool = True,
    include_classification: bool = True,
    status: str = "succeeded",
) -> RunContext:
    run_dir = tmp_path / "runs" / run_id
    manifest_path = run_dir / "run_manifest.json"
    if report and create_report:
        report_path = run_dir / "report" / "report.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("# report\n", encoding="utf-8")
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "status": status,
        "started_at": "2026-06-24T00:00:00Z",
        "finished_at": "2026-06-24T00:01:00Z",
        "artifacts": {"manifest": "run_manifest.json"},
        "codex": {"status": "skipped"},
        "stages": [],
        "warnings": [],
        "errors": [],
    }
    if report:
        manifest["artifacts"]["report"] = "report/report.md"
    if include_classification:
        manifest.update(
            {
                "run_kind": run_kind,
                "trigger": trigger or {"source": "CLI", "intent": "run"},
                "disposal_class": disposal_class,
            }
        )
    write_json(manifest_path, manifest)
    return RunContext(
        run_id=run_id,
        run_dir=run_dir,
        raw_dir=run_dir / "raw",
        analysis_dir=run_dir / "analysis",
        codex_context_dir=run_dir / "codex_context",
        report_dir=run_dir / "report",
        manifest_path=manifest_path,
        config_path=config_path,
        manifest=manifest,
    )


def _write_bad_manifest(tmp_path: Path, run_id: str) -> Path:
    path = tmp_path / "runs" / run_id / "run_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{", encoding="utf-8")
    return path
