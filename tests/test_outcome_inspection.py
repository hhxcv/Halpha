from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any

import pytest

from halpha.cli import main
from halpha.pipeline import RunContext
from halpha.run_index import write_run_index
from halpha.storage import write_json


def test_outcomes_inspect_reports_missing_optional_stores_without_private_values(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_config(tmp_path, proxy_url="http://private-host.local:18080")

    exit_code = main(["outcomes", "inspect", "--config", str(config_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Halpha outcome inspection succeeded." in output
    assert "status: ok" in output
    assert "selected_run: skipped" in output
    assert "outcome_targets: skipped" in output
    assert "outcome_evaluations: skipped" in output
    assert "outcome_tracking_material: skipped" in output
    assert "outcome_history: skipped" in output
    assert "private-host" not in output
    assert "18080" not in output
    assert str(tmp_path) not in output


def test_outcomes_inspect_reports_latest_healthy_outcome_state(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path)
    run = _write_run_with_outcomes(tmp_path, config_path, run_id="run-1", outcome_status="ok")
    write_run_index(run, now="2026-06-05T00:10:00Z")
    _write_outcome_history_state(tmp_path, status="ok", records=2)

    exit_code = main(["outcomes", "inspect", "--config", str(config_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Halpha outcome inspection succeeded." in output
    assert "status: ok" in output
    assert "selected_run: ok" in output
    assert "run_id=run-1" in output
    assert "run_dir=runs/run-1" in output
    assert "outcome_targets: ok" in output
    assert "targets=2" in output
    assert "outcome_evaluations: ok" in output
    assert "evaluations=2" in output
    assert "evaluated=2" in output
    assert "outcome_tracking_material: ok" in output
    assert "selected_evaluations=2" in output
    assert "outcome_history: ok" in output
    assert "records=2" in output
    assert "history=data/research/outcomes/outcome_history.json" in output
    assert "stable_outcome_key" not in output
    assert "raw_record" not in output
    assert str(tmp_path) not in output


def test_outcomes_inspect_ignores_latest_run_index_outside_project_root(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_config(tmp_path)
    run = _write_run_with_outcomes(tmp_path, config_path, run_id="run-1", outcome_status="ok")
    write_run_index(run, now="2026-06-05T00:10:00Z")
    outside_dir = tmp_path.parent / "outside-outcome-inspect-run"
    write_json(
        outside_dir / "run_manifest.json",
        {
            "schema_version": 1,
            "run_id": run.run_id,
            "status": "succeeded",
            "private_note": "outside outcome inspect manifest was read",
        },
    )
    with sqlite3.connect(tmp_path / "data" / "research" / "index.sqlite") as connection:
        connection.execute("UPDATE runs SET run_dir = ? WHERE run_id = ?", (str(outside_dir), run.run_id))
        connection.commit()

    exit_code = main(["outcomes", "inspect", "--config", str(config_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "selected_run: skipped" in output
    assert "outcome_targets: skipped" in output
    assert "outside outcome inspect manifest was read" not in output
    assert str(outside_dir) not in output


def test_outcomes_inspect_reports_specific_degraded_run_state(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path)
    _write_run_with_outcomes(tmp_path, config_path, run_id="run-degraded", outcome_status="degraded")
    _write_outcome_history_state(tmp_path, status="warning", records=3, conflicts=1, warning_count=1)

    exit_code = main(
        [
            "outcomes",
            "inspect",
            "--config",
            str(config_path),
            "--run-dir",
            "runs/run-degraded",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "status: degraded" in output
    assert "selected_run: ok" in output
    assert "run_id=run-degraded" in output
    assert "outcome_evaluations: degraded" in output
    assert "failed=1" in output
    assert "errors=1" in output
    assert "outcome_history: warning" in output
    assert "conflicting_duplicates=1" in output
    assert "warnings=1" in output
    assert str(tmp_path) not in output


def test_outcomes_inspect_returns_error_for_missing_requested_run_dir(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path)

    exit_code = main(
        [
            "outcomes",
            "inspect",
            "--config",
            str(config_path),
            "--run-dir",
            "runs/missing",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 3
    assert "Halpha outcome inspection failed." in output
    assert "stage: outcomes_inspect" in output
    assert "requested run directory was not found" in output
    assert str(tmp_path) not in output


def test_outcomes_inspect_returns_error_for_invalid_outcome_artifact(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path)
    run = _write_run_with_outcomes(tmp_path, config_path, run_id="run-invalid", outcome_status="ok")
    (run.analysis_dir / "outcome_evaluations.json").write_text("{not json", encoding="utf-8")

    exit_code = main(
        [
            "outcomes",
            "inspect",
            "--config",
            str(config_path),
            "--run-dir",
            "runs/run-invalid",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 3
    assert "Halpha outcome inspection failed." in output
    assert "analysis/outcome_evaluations.json could not be inspected" in output
    assert "outcome_evaluations.json is not valid JSON" in output


def test_outcomes_inspect_help_mentions_run_dir(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["outcomes", "inspect", "--help"])

    output = capsys.readouterr().out
    assert exc.value.code == 0
    assert "Inspect outcome targets, evaluations, material, and history state." in output
    assert "--config" in output
    assert "--run-dir" in output


def _write_config(tmp_path: Path, *, proxy_url: str | None = None) -> Path:
    proxy_block = (
        f"""
  proxy:
    enabled: true
    url: {proxy_url}
"""
        if proxy_url
        else """
  proxy:
    enabled: false
"""
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
run:
  output_dir: runs
  timezone: Asia/Shanghai
market:
  enabled: true
  source: binance
{proxy_block.rstrip()}
  symbols:
    - BTCUSDT
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
    return config_path


def _write_run_with_outcomes(
    tmp_path: Path,
    config_path: Path,
    *,
    run_id: str,
    outcome_status: str,
) -> RunContext:
    run_dir = tmp_path / "runs" / run_id
    raw_dir = run_dir / "raw"
    analysis_dir = run_dir / "analysis"
    codex_context_dir = run_dir / "codex_context"
    report_dir = run_dir / "report"
    for directory in (raw_dir, analysis_dir, codex_context_dir, report_dir):
        directory.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "status": "succeeded",
        "started_at": "2026-06-05T00:00:00Z",
        "finished_at": "2026-06-05T00:10:00Z",
        "artifacts": {
            "outcome_targets": "analysis/outcome_targets.json",
            "outcome_evaluations": "analysis/outcome_evaluations.json",
            "outcome_tracking_material": "analysis/outcome_tracking_material.md",
        },
        "counts": {},
        "stages": [{"name": "evaluate_outcomes", "status": "succeeded"}],
        "codex": {"status": "skipped"},
        "outcome_tracking_material": {
            "status": "ok" if outcome_status == "ok" else "warning",
            "artifact": "analysis/outcome_tracking_material.md",
            "selected_evaluation_count": 2,
            "omitted_evaluation_count": 0,
        },
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
    write_json(run.manifest_path, manifest)
    write_json(
        analysis_dir / "outcome_targets.json",
        {
            "schema_version": 1,
            "artifact_type": "outcome_targets",
            "run_id": run_id,
            "status": "ok",
            "targets": [{"target_id": "target-1"}, {"target_id": "target-2"}],
            "skipped_records": [],
            "counts": {
                "targets": 2,
                "skipped_records": 0,
                "duplicate_records": 0,
                "missing_source_fields": 0,
            },
            "warnings": [],
            "errors": [],
        },
    )
    write_json(analysis_dir / "outcome_evaluations.json", _outcome_evaluations(run_id, status=outcome_status))
    (analysis_dir / "outcome_tracking_material.md").write_text(
        "# outcome_tracking_material\n\nbounded outcome summary\n",
        encoding="utf-8",
    )
    return run


def _outcome_evaluations(run_id: str, *, status: str) -> dict[str, Any]:
    warnings = ["Recorded one failed outcome target."] if status == "degraded" else []
    errors = [{"type": "OutcomeEvaluationError", "message": "sample validation failure"}] if status == "degraded" else []
    return {
        "schema_version": 1,
        "artifact_type": "outcome_evaluations",
        "run_id": run_id,
        "created_at": "2026-06-05T00:10:00Z",
        "status": status,
        "evaluations": [{"outcome_id": "outcome-1"}, {"outcome_id": "outcome-2"}],
        "counts": {
            "evaluations": 2,
            "evaluated": 1 if status == "degraded" else 2,
            "pending": 0,
            "insufficient_data": 0,
            "skipped": 0,
            "stale": 0,
            "failed": 1 if status == "degraded" else 0,
        },
        "warnings": warnings,
        "errors": errors,
    }


def _write_outcome_history_state(
    tmp_path: Path,
    *,
    status: str,
    records: int,
    conflicts: int = 0,
    warning_count: int = 0,
) -> None:
    write_json(
        tmp_path / "data" / "research" / "metadata" / "outcome_history_state.json",
        {
            "schema_version": 1,
            "artifact_type": "outcome_history_state",
            "status": status,
            "updated_at": "2026-06-05T00:10:00Z",
            "totals": {
                "records": records,
                "incoming_records": 2,
                "inserted_records": 2,
                "updated_records": 0,
                "duplicate_records": 0,
                "conflicting_duplicates": conflicts,
                "warning_count": warning_count,
                "error_count": 0,
            },
            "sources": [{"source_run_id": "source-run", "record_count": records}],
            "warnings": ["conflicting duplicate outcome history record"] if warning_count else [],
            "errors": [],
        },
    )
