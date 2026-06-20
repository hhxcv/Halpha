from __future__ import annotations

import json
from pathlib import Path

from halpha.pipeline import RunContext
from halpha.product_validation import build_product_contract_validation
from halpha.storage import write_json


def test_product_contract_validation_accepts_no_codex_without_report(tmp_path: Path) -> None:
    run = _run(tmp_path, codex_status="skipped")
    _write_analysis_artifact(run, "risk_assessment", {"status": "ok"})
    run.manifest["artifacts"]["risk_assessment"] = "analysis/risk_assessment.json"
    write_json(
        tmp_path / "data" / "research" / "metadata" / "research_data_catalog.json",
        {"schema_version": 1, "artifact_type": "research_data_catalog", "status": "ok"},
    )
    run.manifest["artifacts"]["research_data_catalog"] = "data/research/metadata/research_data_catalog.json"

    artifacts = build_product_contract_validation({}, run)

    artifact = _validation_artifact(run)
    assert artifacts == ["analysis/product_contract_validation.json"]
    assert artifact["artifact_type"] == "product_contract_validation"
    assert artifact["status"] == "ok"
    assert _check(artifact, "codex_report:skipped_report")["status"] == "ok"
    assert _check(artifact, "artifact_json:data/research/metadata/research_data_catalog.json")["status"] == "ok"
    assert run.manifest["artifacts"]["product_contract_validation"] == "analysis/product_contract_validation.json"
    assert run.manifest["counts"]["product_contract_validation_failed"] == 0


def test_product_contract_validation_accepts_completed_codex_report(tmp_path: Path) -> None:
    run = _run(tmp_path, codex_status="succeeded")
    run.manifest["artifacts"]["report"] = "report/report.md"
    run.report_dir.mkdir(parents=True, exist_ok=True)
    (run.report_dir / "report.md").write_text("# report\n\n## 风险提示\n", encoding="utf-8")

    build_product_contract_validation({}, run)

    artifact = _validation_artifact(run)
    assert artifact["status"] == "ok"
    assert _check(artifact, "codex_report:completed_report")["status"] == "ok"


def test_product_contract_validation_catches_missing_recorded_artifact(tmp_path: Path) -> None:
    run = _run(tmp_path, codex_status="skipped")
    run.manifest["artifacts"]["risk_assessment"] = "analysis/risk_assessment.json"

    build_product_contract_validation({}, run)

    artifact = _validation_artifact(run)
    assert artifact["status"] == "failed"
    check = _check(artifact, "artifact_ref:analysis/risk_assessment.json")
    assert check["status"] == "failed"
    assert "was not found" in check["message"]
    assert run.manifest["product_contract_validation"]["failed"] == 1


def test_product_contract_validation_catches_invalid_artifact_type(tmp_path: Path) -> None:
    run = _run(tmp_path, codex_status="skipped")
    _write_analysis_artifact(run, "risk_assessment", {"artifact_type": "wrong_type", "status": "ok"})
    run.manifest["artifacts"]["risk_assessment"] = "analysis/risk_assessment.json"

    build_product_contract_validation({}, run)

    artifact = _validation_artifact(run)
    assert artifact["status"] == "failed"
    check = _check(artifact, "artifact_type:analysis/risk_assessment.json")
    assert check["status"] == "failed"
    assert check["expected"] == "risk_assessment"
    assert check["observed"] == "wrong_type"


def test_product_contract_validation_catches_failed_stage(tmp_path: Path) -> None:
    run = _run(tmp_path, codex_status="not_started")
    run.manifest["stages"][0]["status"] = "failed"
    run.manifest["stages"][0]["error"] = {
        "stage": "collect_market_data",
        "message": "source failed",
    }

    build_product_contract_validation({}, run)

    artifact = _validation_artifact(run)
    assert artifact["status"] == "failed"
    check = _check(artifact, "manifest:stage_health")
    assert check["status"] == "failed"
    assert "collect_market_data" in check["message"]


def test_product_contract_validation_catches_codex_success_without_report(tmp_path: Path) -> None:
    run = _run(tmp_path, codex_status="succeeded")

    build_product_contract_validation({}, run)

    artifact = _validation_artifact(run)
    assert artifact["status"] == "failed"
    check = _check(artifact, "codex_report:completed_report")
    assert check["status"] == "failed"
    assert "report/report.md" in check["message"]


def _run(tmp_path: Path, *, codex_status: str) -> RunContext:
    run_dir = tmp_path / "runs" / "run-1"
    raw_dir = run_dir / "raw"
    analysis_dir = run_dir / "analysis"
    codex_context_dir = run_dir / "codex_context"
    report_dir = run_dir / "report"
    for directory in (raw_dir, analysis_dir, codex_context_dir, report_dir):
        directory.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "run_id": "run-1",
        "status": "running",
        "stage_order": ["collect_market_data", "run_codex_report", "validate_product_contracts"],
        "stages": [
            {
                "name": "collect_market_data",
                "status": "succeeded",
                "started_at": "2026-06-20T00:00:00Z",
                "finished_at": "2026-06-20T00:00:01Z",
                "artifacts": [],
            },
            {
                "name": "validate_product_contracts",
                "status": "running",
                "started_at": "2026-06-20T00:00:02Z",
                "finished_at": None,
                "artifacts": [],
            },
        ],
        "artifacts": {},
        "counts": {},
        "codex": {"enabled": True, "command": "codex", "status": codex_status, "exit_code": None},
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
        config_path=tmp_path / "config.yaml",
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


def _validation_artifact(run: RunContext) -> dict[str, object]:
    return json.loads((run.analysis_dir / "product_contract_validation.json").read_text(encoding="utf-8"))


def _check(artifact: dict[str, object], check_id: str) -> dict[str, object]:
    checks = artifact["checks"]
    assert isinstance(checks, list)
    for check in checks:
        if isinstance(check, dict) and check.get("check_id") == check_id:
            return check
    raise AssertionError(f"missing check {check_id}")
