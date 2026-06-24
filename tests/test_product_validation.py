from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from halpha.data.research_data_catalog import prepare_research_data_catalog_publication
from halpha.outcome.outcome_history import prepare_outcome_history_publication
from halpha.pipeline import RunContext
from halpha.product.product_validation import build_product_contract_validation
from halpha.runtime.pipeline_contracts import PipelineError
import halpha.shared_publication as shared_publication
from halpha.storage import write_json


@pytest.fixture(autouse=True)
def _isolate_artifact_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


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
    run.manifest["stages"][0]["tasks"][0]["status"] = "failed"
    run.manifest["stages"][0]["tasks"][0]["error"] = {
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


def test_product_validation_does_not_publish_staged_shared_state_when_validation_fails(
    tmp_path: Path,
) -> None:
    run = _run(tmp_path, codex_status="skipped")
    _prepare_shared_publication(run)
    run.manifest["artifacts"]["risk_assessment"] = "analysis/risk_assessment.json"

    with pytest.raises(PipelineError, match="blocks shared publication"):
        build_product_contract_validation({}, run)

    assert _validation_artifact(run)["status"] == "failed"
    assert not _history_path(tmp_path).exists()
    assert not _state_path(tmp_path).exists()
    assert not _catalog_path(tmp_path).exists()
    assert "outcome_history_state" not in run.manifest["artifacts"]
    assert "research_data_catalog" not in run.manifest["artifacts"]
    assert run.manifest["shared_state_publication"]["status"] == "not_published"
    assert "artifacts" not in run.manifest["shared_state_publication"]
    assert not _staging_dir(run).exists()


def test_product_validation_publishes_staged_shared_state_after_validation_passes(tmp_path: Path) -> None:
    run = _run(tmp_path, codex_status="skipped")
    _write_analysis_artifact(run, "risk_assessment", {"status": "ok"})
    run.manifest["artifacts"]["risk_assessment"] = "analysis/risk_assessment.json"
    _prepare_shared_publication(run)

    artifacts = build_product_contract_validation({}, run)

    assert artifacts == [
        "analysis/product_contract_validation.json",
        "data/research/outcomes/outcome_history.json",
        "data/research/metadata/outcome_history_state.json",
        "data/research/metadata/research_data_catalog.json",
    ]
    assert _history_path(tmp_path).is_file()
    assert _state_path(tmp_path).is_file()
    assert _catalog_path(tmp_path).is_file()
    assert _read_json(_history_path(tmp_path))["records"][0]["target_id"] == "target-1"
    assert _read_json(_state_path(tmp_path))["totals"]["records"] == 1
    assert _read_json(_catalog_path(tmp_path))["stores"][0]["name"] == "outcome_history"
    assert run.manifest["shared_state_publication"]["status"] == "published"
    assert run.manifest["artifacts"]["outcome_history_state"] == (
        "data/research/metadata/outcome_history_state.json"
    )
    assert run.manifest["artifacts"]["research_data_catalog"] == (
        "data/research/metadata/research_data_catalog.json"
    )
    assert not _staging_dir(run).exists()


@pytest.mark.parametrize("status", ["skipped", "unknown", None])
def test_product_validation_blocks_non_publishable_validation_statuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status: str | None,
) -> None:
    run = _run(tmp_path, codex_status="skipped")
    _prepare_shared_publication(run)

    def fake_validate_product_contracts(*args: Any, **kwargs: Any) -> dict[str, Any]:
        artifact = _validation_payload(status="ok")
        if status is None:
            artifact.pop("status")
        else:
            artifact["status"] = status
        return artifact

    monkeypatch.setattr(
        "halpha.product.product_validation.validate_product_contracts",
        fake_validate_product_contracts,
    )

    with pytest.raises(PipelineError, match="blocks shared publication"):
        build_product_contract_validation({}, run)

    assert not _history_path(tmp_path).exists()
    assert not _state_path(tmp_path).exists()
    assert not _catalog_path(tmp_path).exists()
    assert "outcome_history_state" not in run.manifest["artifacts"]
    assert "research_data_catalog" not in run.manifest["artifacts"]
    assert run.manifest["shared_state_publication"]["status"] == "not_published"
    assert not _staging_dir(run).exists()


def test_product_validation_blocks_malformed_validation_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _run(tmp_path, codex_status="skipped")
    _prepare_shared_publication(run)
    monkeypatch.setattr(
        "halpha.product.product_validation.validate_product_contracts",
        lambda *args, **kwargs: [],
    )

    with pytest.raises(PipelineError, match="did not return a JSON object"):
        build_product_contract_validation({}, run)

    assert not (run.analysis_dir / "product_contract_validation.json").exists()
    assert not _history_path(tmp_path).exists()
    assert run.manifest["shared_state_publication"]["status"] == "not_published"
    assert not _staging_dir(run).exists()


def test_validator_exception_leaves_existing_shared_files_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _run(tmp_path, codex_status="skipped")
    previous = _write_existing_shared_state(tmp_path)
    _prepare_shared_publication(run)

    def raise_validation_error(*args: Any, **kwargs: Any) -> dict[str, Any]:
        _ = args, kwargs
        raise RuntimeError("validator unavailable")

    monkeypatch.setattr(
        "halpha.product.product_validation.validate_product_contracts",
        raise_validation_error,
    )

    with pytest.raises(RuntimeError, match="validator unavailable"):
        build_product_contract_validation({}, run)

    assert _read_json(_history_path(tmp_path)) == previous["history"]
    assert _read_json(_state_path(tmp_path)) == previous["state"]
    assert _read_json(_catalog_path(tmp_path)) == previous["catalog"]
    assert "outcome_history_state" not in run.manifest["artifacts"]
    assert "research_data_catalog" not in run.manifest["artifacts"]
    assert run.manifest["shared_state_publication"]["status"] == "not_published"
    assert not _staging_dir(run).exists()


@pytest.mark.parametrize("failed_name", ["outcome_history_state.json", "research_data_catalog.json"])
def test_shared_state_publication_rolls_back_written_files_when_replacement_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failed_name: str,
) -> None:
    run = _run(tmp_path, codex_status="skipped")
    _write_analysis_artifact(run, "risk_assessment", {"status": "ok"})
    run.manifest["artifacts"]["risk_assessment"] = "analysis/risk_assessment.json"
    previous = _write_existing_shared_state(tmp_path)
    _prepare_shared_publication(run)
    original_write_json = shared_publication.write_json

    def fail_on_target(path: Path, payload: dict[str, Any]) -> None:
        if Path(path).name == failed_name:
            raise OSError("shared replacement denied")
        original_write_json(path, payload)

    monkeypatch.setattr(shared_publication, "write_json", fail_on_target)

    with pytest.raises(PipelineError, match="rolled back"):
        build_product_contract_validation({}, run)

    assert _read_json(_history_path(tmp_path)) == previous["history"]
    assert _read_json(_state_path(tmp_path)) == previous["state"]
    assert _read_json(_catalog_path(tmp_path)) == previous["catalog"]
    assert "outcome_history_state" not in run.manifest["artifacts"]
    assert "research_data_catalog" not in run.manifest["artifacts"]
    assert run.manifest["shared_state_publication"]["status"] == "rolled_back"
    assert not _staging_dir(run).exists()


def test_shared_state_publication_reports_rollback_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _run(tmp_path, codex_status="skipped")
    _write_analysis_artifact(run, "risk_assessment", {"status": "ok"})
    run.manifest["artifacts"]["risk_assessment"] = "analysis/risk_assessment.json"
    _write_existing_shared_state(tmp_path)
    _prepare_shared_publication(run)
    original_write_json = shared_publication.write_json

    def fail_on_state(path: Path, payload: dict[str, Any]) -> None:
        if Path(path).name == "outcome_history_state.json":
            raise OSError("state replacement denied")
        original_write_json(path, payload)

    def fail_restore(path: Path, payload: bytes) -> None:
        _ = path, payload
        raise OSError("restore denied")

    monkeypatch.setattr(shared_publication, "write_json", fail_on_state)
    monkeypatch.setattr(shared_publication, "_atomic_write_bytes", fail_restore)

    with pytest.raises(PipelineError, match="rollback was incomplete"):
        build_product_contract_validation({}, run)

    publication = run.manifest["shared_state_publication"]
    assert publication["status"] == "rollback_failed"
    assert publication["rollback_errors"]
    assert not _staging_dir(run).exists()


def test_shared_state_publication_retry_is_idempotent(tmp_path: Path) -> None:
    run = _run(tmp_path, codex_status="skipped")
    _write_analysis_artifact(run, "risk_assessment", {"status": "ok"})
    run.manifest["artifacts"]["risk_assessment"] = "analysis/risk_assessment.json"
    _prepare_shared_publication(run)
    build_product_contract_validation({}, run)

    _prepare_shared_publication(run)
    build_product_contract_validation({}, run)

    history = _read_json(_history_path(tmp_path))
    state = _read_json(_state_path(tmp_path))
    assert len(history["records"]) == 1
    assert history["records"][0]["evaluation_run_ids"] == ["run-1"]
    assert state["totals"]["records"] == 1
    assert state["totals"]["duplicate_records"] == 0


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
        "stage_order": [
            "refresh_data",
            "build_source_evidence",
            "run_strategy_research",
            "synthesize_intelligence",
            "build_materials",
            "generate_report",
            "finalize_run",
        ],
        "stages": [
            {
                "name": "refresh_data",
                "status": "succeeded",
                "started_at": "2026-06-20T00:00:00Z",
                "finished_at": "2026-06-20T00:00:01Z",
                "artifacts": [],
                "tasks": [
                    {
                        "name": "collect_market_data",
                        "status": "succeeded",
                        "started_at": "2026-06-20T00:00:00Z",
                        "finished_at": "2026-06-20T00:00:01Z",
                        "artifacts": [],
                    }
                ],
            },
            {
                "name": "finalize_run",
                "status": "running",
                "started_at": "2026-06-20T00:00:02Z",
                "finished_at": None,
                "artifacts": [],
                "tasks": [
                    {
                        "name": "validate_product_contracts",
                        "status": "running",
                        "started_at": "2026-06-20T00:00:02Z",
                        "finished_at": None,
                        "artifacts": [],
                    }
                ],
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


def _prepare_shared_publication(run: RunContext) -> None:
    _write_outcome_evaluations(run, [_outcome_evaluation("target-1")])
    prepare_outcome_history_publication({}, run, now="2026-06-05T00:00:00Z")
    prepare_research_data_catalog_publication({}, run, now="2026-06-05T00:00:00Z")


def _write_outcome_evaluations(run: RunContext, evaluations: list[dict[str, Any]]) -> None:
    artifact = {
        "schema_version": 1,
        "artifact_type": "outcome_evaluations",
        "run_id": run.run_id,
        "created_at": "2026-06-05T00:00:00Z",
        "status": "ok",
        "evaluation_policy": {},
        "evaluations": evaluations,
        "counts": {"evaluations": len(evaluations)},
        "source_artifacts": ["analysis/outcome_targets.json"],
        "warnings": [],
        "errors": [],
    }
    write_json(run.analysis_dir / "outcome_evaluations.json", artifact)


def _outcome_evaluation(target_id: str) -> dict[str, Any]:
    return {
        "outcome_id": f"outcome:{target_id}:run-1",
        "target_id": target_id,
        "target_kind": "market_signal",
        "source_run_id": "source-run",
        "evaluation_run_id": "run-1",
        "evaluated_at": "2026-06-05T00:00:00Z",
        "evaluation_status": "evaluated",
        "outcome_state": "aligned",
        "observation_window": {
            "source_as_of": "2026-06-04T00:00:00Z",
            "start": "2026-06-05T00:00:00Z",
            "end": "2026-06-05T00:00:00Z",
            "horizon_end": "2026-06-05T00:00:00Z",
            "sample_rows": 1,
            "no_lookahead": True,
            "excluded_at_or_before_source_as_of": True,
        },
        "metrics": {"return_pct": 0.04},
        "evidence": ["Observation rows are strictly after target source_as_of."],
        "source_artifacts": ["analysis/outcome_targets.json"],
        "warnings": [],
        "errors": [],
    }


def _write_existing_shared_state(tmp_path: Path) -> dict[str, dict[str, Any]]:
    previous = {
        "history": {
            "schema_version": 1,
            "artifact_type": "outcome_history",
            "records": [{"stable_outcome_key": "old"}],
        },
        "state": {
            "schema_version": 1,
            "artifact_type": "outcome_history_state",
            "status": "ok",
            "totals": {"records": 1},
        },
        "catalog": {
            "schema_version": 1,
            "artifact_type": "research_data_catalog",
            "status": "ok",
            "stores": [{"name": "old"}],
            "counts": {"stores": 1, "records": 1, "warnings": 0, "errors": 0},
        },
    }
    write_json(_history_path(tmp_path), previous["history"])
    write_json(_state_path(tmp_path), previous["state"])
    write_json(_catalog_path(tmp_path), previous["catalog"])
    return previous


def _validation_payload(*, status: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "artifact_type": "product_contract_validation",
        "run_id": "run-1",
        "created_at": "2026-06-05T00:00:00Z",
        "status": status,
        "mode": "product_run",
        "counts": {
            "checks": 1,
            "ok": 1 if status == "ok" else 0,
            "warning": 0,
            "degraded": 0,
            "failed": 0,
            "skipped": 1 if status == "skipped" else 0,
            "errors": 0,
            "warnings": 0,
        },
        "checks": [],
        "source_artifacts": ["run_manifest.json"],
        "warnings": [],
        "errors": [],
    }


def _validation_artifact(run: RunContext) -> dict[str, object]:
    return json.loads((run.analysis_dir / "product_contract_validation.json").read_text(encoding="utf-8"))


def _check(artifact: dict[str, object], check_id: str) -> dict[str, object]:
    checks = artifact["checks"]
    assert isinstance(checks, list)
    for check in checks:
        if isinstance(check, dict) and check.get("check_id") == check_id:
            return check
    raise AssertionError(f"missing check {check_id}")


def _history_path(tmp_path: Path) -> Path:
    return tmp_path / "data" / "research" / "outcomes" / "outcome_history.json"


def _state_path(tmp_path: Path) -> Path:
    return tmp_path / "data" / "research" / "metadata" / "outcome_history_state.json"


def _catalog_path(tmp_path: Path) -> Path:
    return tmp_path / "data" / "research" / "metadata" / "research_data_catalog.json"


def _staging_dir(run: RunContext) -> Path:
    return run.run_dir / ".shared_state_publication"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
