from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest

from halpha.cli import main
from halpha.pipeline import RunContext
from halpha.data.run_index import write_run_index
from halpha.storage import write_json


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_workbench_help_mentions_build_and_inspect(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["workbench", "--help"])

    output = capsys.readouterr().out
    assert exc.value.code == 0
    assert "Build or inspect local workbench delivery artifacts." in output
    assert "build" in output
    assert "inspect" in output


def test_workbench_build_writes_summary_without_running_pipeline(
    tmp_path: Path,
    capsys,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    run = _write_run(tmp_path, config_path)
    write_json(run.analysis_dir / "decision_recommendations.json", _artifact("decision_recommendations"))
    run.manifest["artifacts"]["decision_recommendations"] = "analysis/decision_recommendations.json"
    run.manifest["counts"]["decision_recommendation_records"] = 1
    write_json(run.manifest_path, run.manifest)
    run.manifest["run_index"] = write_run_index(run, now="2026-06-20T00:05:00Z")
    write_json(run.manifest_path, run.manifest)

    def fail_pipeline(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("workbench build must not run pipeline")

    monkeypatch.setattr("halpha.cli.run_pipeline", fail_pipeline)

    exit_code = main(["workbench", "build", "--config", str(config_path)])

    output = capsys.readouterr().out
    summary_path = tmp_path / "runs" / "workbench" / "latest" / "workbench_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert "Halpha workbench build succeeded." in output
    assert "summary:" in output
    assert "index_markdown: runs/workbench/latest/index.md" in output
    assert "index_html: runs/workbench/latest/index.html" in output
    assert "latest_run_id: run-1" in output
    assert "latest_run_source: latest_successful_run" in output
    assert "codex: not_run" in output
    assert summary["source_selection"]["mode"] == "latest_run_index"
    assert summary["source_selection"]["selection_key"] == "latest_successful_run"
    assert summary["source_selection"]["selection_label"] == "latest successful run"
    assert summary["source_selection"]["run_id"] == "run-1"
    assert summary["decision_state"]["fields"]["decision_records"] == 1
    assert (tmp_path / "runs" / "workbench" / "latest" / "index.md").is_file()
    assert (tmp_path / "runs" / "workbench" / "latest" / "index.html").is_file()


def test_workbench_build_rejects_latest_run_index_outside_project_root(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_config(tmp_path)
    run = _write_run(tmp_path, config_path)
    write_json(run.manifest_path, run.manifest)
    write_run_index(run, now="2026-06-20T00:05:00Z")
    outside_dir = tmp_path.parent / "outside-workbench-run"
    write_json(
        outside_dir / "run_manifest.json",
        {
            "schema_version": 1,
            "run_id": run.run_id,
            "status": "succeeded",
            "private_note": "outside workbench manifest was read",
        },
    )
    with sqlite3.connect(tmp_path / "data" / "research" / "index.sqlite") as connection:
        connection.execute("UPDATE runs SET run_dir = ? WHERE run_id = ?", (str(outside_dir), run.run_id))
        connection.commit()

    exit_code = main(["workbench", "build", "--config", str(config_path)])

    output = capsys.readouterr().out
    summary = json.loads(
        (tmp_path / "runs" / "workbench" / "latest" / "workbench_summary.json").read_text(encoding="utf-8")
    )
    assert exit_code == 0
    assert summary["source_selection"]["status"] == "failed"
    assert summary["source_selection"]["run_dir"] is None
    assert summary["source_selection"]["reason"] == "local run index points outside the configured project root."
    assert summary["latest_run"]["status"] == "missing"
    assert "latest_run_id:" not in output
    assert "outside workbench manifest was read" not in json.dumps(summary)
    assert str(outside_dir) not in json.dumps(summary)


def test_workbench_build_uses_explicit_run_dir(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path)
    run = _write_run(tmp_path, config_path)
    write_json(run.manifest_path, run.manifest)

    exit_code = main(
        [
            "workbench",
            "build",
            "--config",
            str(config_path),
            "--run-dir",
            "runs/run-1",
        ]
    )

    output = capsys.readouterr().out
    summary = json.loads(
        (tmp_path / "runs" / "workbench" / "latest" / "workbench_summary.json").read_text(encoding="utf-8")
    )
    assert exit_code == 0
    assert "Halpha workbench build succeeded." in output
    assert summary["source_selection"]["mode"] == "explicit_run"
    assert summary["latest_run"]["fields"]["run_id"] == "run-1"


def test_workbench_inspect_missing_summary_is_read_only(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path)
    summary_path = tmp_path / "runs" / "workbench" / "latest" / "workbench_summary.json"

    exit_code = main(["workbench", "inspect", "--config", str(config_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Halpha workbench inspection succeeded." in output
    assert "status: missing" in output
    assert "workbench_summary.json was not found" in output
    assert not summary_path.exists()


def test_workbench_inspect_prints_existing_summary(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path)
    summary_path = tmp_path / "runs" / "workbench" / "latest" / "workbench_summary.json"
    write_json(
        summary_path,
        {
            "schema_version": 1,
            "artifact_type": "workbench_summary",
            "status": "partial",
            "latest_run": {
                "status": "available",
                "fields": {
                    "run_id": "run-1",
                    "run_status": "succeeded",
                    "report": {"status": "missing", "artifact": "report/report.md"},
                },
            },
            "decision_state": {"status": "available", "fields": {"decision_records": 2, "watch_trigger_records": 3}},
            "alert_state": {"status": "missing", "fields": {"alert_decision_records": 0}},
            "monitor_state": {"status": "missing", "fields": {"cycle_count": 0}},
            "outcome_state": {"status": "missing", "fields": {"evaluation_records": 0}},
            "strategy_state": {"status": "available", "fields": {"strategy_gate_effective": 3}},
            "product_validation_state": {
                "status": "failed",
                "fields": {"checks": 5, "warning": 1, "degraded": 0, "failed": 1},
            },
            "data_quality_state": {"status": "available", "fields": {"warnings": 1}},
            "warnings": ["one source artifact was missing"],
            "errors": [],
        },
    )

    exit_code = main(["workbench", "inspect", "--config", str(config_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Halpha workbench inspection succeeded." in output
    assert "status: partial" in output
    assert "latest_run_id: run-1" in output
    assert "decision_records: 2" in output
    assert "strategy_gate_effective: 3" in output
    assert "strategy_lifecycle_state_status: missing" in output
    assert "strategy_lifecycle_degraded: 0" in output
    assert "product_validation_state: failed" in output
    assert "product_validation_checks: 5" in output
    assert "product_validation_failed: 1" in output
    assert "warning_count: 1" in output


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
        "artifacts": {},
        "counts": {},
        "stages": [],
        "codex": {"status": "skipped"},
        "errors": [],
    }
    return RunContext(
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


def _artifact(artifact_type: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "artifact_type": artifact_type,
        "status": "ok",
        "counts": {"records": 1},
        "warnings": [],
        "errors": [],
    }
