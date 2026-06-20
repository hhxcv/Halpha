from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from halpha.cli import main
from halpha.pipeline import RunContext
from halpha.run_index import write_run_index
from halpha.storage import write_json


def test_validate_uses_latest_run_without_running_pipeline(
    tmp_path: Path,
    capsys,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    run = _write_run(tmp_path, config_path)
    _write_analysis_artifact(run, "risk_assessment", {"private_note": "private-host.local:9000"})
    run.manifest["artifacts"]["risk_assessment"] = "analysis/risk_assessment.json"
    write_json(run.manifest_path, run.manifest)
    write_run_index(run, now="2026-06-20T00:05:00Z")

    def fail_pipeline(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("validate must not run the product pipeline")

    monkeypatch.setattr("halpha.cli.run_pipeline", fail_pipeline)
    monkeypatch.setattr("halpha.cli.run_pipeline_stage", fail_pipeline)

    exit_code = main(["validate", "--config", str(config_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Halpha product validation succeeded." in output
    assert "status: ok" in output
    assert "selection: latest_run_index" in output
    assert "run_id: run-1" in output
    assert "run_dir: runs/run-1" in output
    assert "checks: total=" in output
    assert "failed_checks: none" in output
    assert "pipeline: not_run" in output
    assert "codex: not_run" in output
    assert "artifact_written: false" in output
    assert "private-host.local" not in output
    assert not (run.analysis_dir / "product_contract_validation.json").exists()


def test_validate_uses_explicit_run_dir_without_run_index(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path)
    run = _write_run(tmp_path, config_path)
    _write_analysis_artifact(run, "risk_assessment", {})
    run.manifest["artifacts"]["risk_assessment"] = "analysis/risk_assessment.json"
    write_json(run.manifest_path, run.manifest)

    exit_code = main(
        [
            "validate",
            "--config",
            str(config_path),
            "--run-dir",
            "runs/run-1",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "selection: explicit_run" in output
    assert "run_id: run-1" in output
    assert "run_dir: runs/run-1" in output


def test_validate_missing_run_index_is_bounded_failure(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path)

    exit_code = main(["validate", "--config", str(config_path)])

    output = capsys.readouterr().out
    assert exit_code == 3
    assert "Halpha product validation failed." in output
    assert "status: missing" in output
    assert "selection: latest_run_index" in output
    assert "source_artifact: data/research/index.sqlite" in output
    assert "local run index was not found" in output
    assert "pipeline: not_run" in output
    assert str(tmp_path) not in output


def test_validate_rejects_latest_run_index_outside_project_root(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path)
    run = _write_run(tmp_path, config_path)
    write_json(run.manifest_path, run.manifest)
    write_run_index(run, now="2026-06-20T00:05:00Z")
    outside_dir = tmp_path.parent / "outside-validation-run"
    write_json(
        outside_dir / "run_manifest.json",
        {
            "schema_version": 1,
            "run_id": run.run_id,
            "status": "succeeded",
            "private_note": "outside validation manifest was read",
        },
    )
    with sqlite3.connect(tmp_path / "data" / "research" / "index.sqlite") as connection:
        connection.execute("UPDATE runs SET run_dir = ? WHERE run_id = ?", (str(outside_dir), run.run_id))
        connection.commit()

    exit_code = main(["validate", "--config", str(config_path)])

    output = capsys.readouterr().out
    assert exit_code == 3
    assert "selection: latest_run_index" in output
    assert "reason: local run index points outside the configured project root." in output
    assert "outside validation manifest was read" not in output
    assert str(outside_dir) not in output


def test_validate_failed_contract_outputs_bounded_diagnostics(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path)
    run = _write_run(tmp_path, config_path)
    run.manifest["artifacts"]["risk_assessment"] = "analysis/risk_assessment.json"
    write_json(run.manifest_path, run.manifest)
    write_run_index(run, now="2026-06-20T00:05:00Z")

    exit_code = main(["validate", "--config", str(config_path)])

    output = capsys.readouterr().out
    assert exit_code == 3
    assert "Halpha product validation failed." in output
    assert "status: failed" in output
    assert "failed_checks: artifact_ref:analysis/risk_assessment.json" in output
    assert "source_artifacts: run_manifest.json, analysis/risk_assessment.json" in output
    assert "next_steps: Rerun the producer stage" in output
    assert "artifact_written: false" in output


def test_validate_privacy_boundary_excludes_config_and_raw_values(tmp_path: Path, capsys) -> None:
    config_path = _write_config(tmp_path, proxy="http://local-proxy.internal:7890")
    run = _write_run(tmp_path, config_path)
    _write_analysis_artifact(
        run,
        "risk_assessment",
        {
            "status": "ok",
            "raw_secret": "account-identifier-12345",
        },
    )
    run.manifest["artifacts"]["risk_assessment"] = "analysis/risk_assessment.json"
    write_json(run.manifest_path, run.manifest)
    write_run_index(run, now="2026-06-20T00:05:00Z")

    exit_code = main(["validate", "--config", str(config_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "local-proxy.internal" not in output
    assert "account-identifier-12345" not in output
    assert str(tmp_path) not in output


def _write_config(tmp_path: Path, *, proxy: str | None = None) -> Path:
    path = tmp_path / "config.yaml"
    proxy_text = f"\n  proxy: {proxy}" if proxy else ""
    path.write_text(
        f"""
run:
  output_dir: runs
market:
  enabled: false{proxy_text}
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
        "stage_order": ["collect_market_data", "run_codex_report", "validate_product_contracts"],
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
                "finished_at": "2026-06-20T00:01:01Z",
                "artifacts": [],
            },
        ],
        "artifacts": {},
        "counts": {},
        "codex": {"enabled": False, "status": "skipped"},
        "errors": [],
        "warnings": [],
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


def _write_analysis_artifact(run: RunContext, name: str, overrides: dict[str, object]) -> None:
    payload = {
        "schema_version": 1,
        "artifact_type": name,
        "status": "ok",
        "records": [],
        "warnings": [],
        "errors": [],
    }
    payload.update(overrides)
    write_json(run.analysis_dir / f"{name}.json", payload)
