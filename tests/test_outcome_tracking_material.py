from __future__ import annotations

import json
from pathlib import Path

from halpha.analysis.outcome_tracking_material import build_outcome_tracking_material
from halpha.pipeline import RunContext


def test_outcome_tracking_material_summarizes_evidence_without_full_history(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    run = _run_context(tmp_path, config_path)
    _write_targets(run)
    _write_evaluations(run)
    _write_history_state(tmp_path)
    _write_full_history_with_sentinel(tmp_path)

    artifacts = build_outcome_tracking_material({}, run)

    material = (run.analysis_dir / "outcome_tracking_material.md").read_text(encoding="utf-8")
    manifest = run.manifest

    assert artifacts == ["analysis/outcome_tracking_material.md"]
    assert "artifact_type: analysis_outcome_tracking_material" in material
    assert "record_type: outcome_tracking_context" in material
    assert "codex_may_generate_outcome_labels: false" in material
    assert "codex_may_validate_missing_histories: false" in material
    assert "codex_may_infer_omitted_store_contents: false" in material
    assert "codex_may_score_prior_recommendations: false" in material
    assert "full_outcome_history_embedded: false" in material
    assert "outcome_history_records: 9" in material
    assert "outcome_history.json" in material
    assert "FULL_HISTORY_SHOULD_NOT_APPEAR" not in material
    assert "stable_outcome_key:" not in material
    assert "target-contradicted" in material
    assert "target-confirmed" in material
    assert manifest["artifacts"]["outcome_tracking_material"] == "analysis/outcome_tracking_material.md"
    assert manifest["counts"]["outcome_tracking_material_evaluations"] == 2
    assert manifest["outcome_tracking_material"]["selected_evaluation_count"] == 2


def test_outcome_tracking_material_skips_when_no_evidence_exists(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    run = _run_context(tmp_path, config_path)
    _write_json(
        run.analysis_dir / "outcome_targets.json",
        {
            "artifact_type": "outcome_targets",
            "targets": [],
            "skipped_records": [],
            "counts": {"targets": 0, "skipped_records": 0},
            "warnings": [],
            "errors": [],
        },
    )
    _write_json(
        run.analysis_dir / "outcome_evaluations.json",
        {
            "artifact_type": "outcome_evaluations",
            "evaluations": [],
            "counts": {"evaluations": 0},
            "warnings": [],
            "errors": [],
        },
    )

    artifacts = build_outcome_tracking_material({}, run)

    assert artifacts == []
    assert not (run.analysis_dir / "outcome_tracking_material.md").exists()
    assert run.manifest["outcome_tracking_material"]["status"] == "not_generated"
    assert run.manifest["counts"]["outcome_tracking_material_evaluations"] == 0


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text("run:\n  output_dir: runs\n", encoding="utf-8")
    return path


def _run_context(tmp_path: Path, config_path: Path) -> RunContext:
    run_dir = tmp_path / "runs" / "run-1"
    raw_dir = run_dir / "raw"
    analysis_dir = run_dir / "analysis"
    codex_context_dir = run_dir / "codex_context"
    report_dir = run_dir / "report"
    for directory in (raw_dir, analysis_dir, codex_context_dir, report_dir):
        directory.mkdir(parents=True, exist_ok=True)
    return RunContext(
        run_id="run-1",
        run_dir=run_dir,
        raw_dir=raw_dir,
        analysis_dir=analysis_dir,
        codex_context_dir=codex_context_dir,
        report_dir=report_dir,
        manifest={"artifacts": {}, "counts": {}, "errors": []},
        manifest_path=run_dir / "run_manifest.json",
        config_path=config_path,
    )


def _write_targets(run: RunContext) -> None:
    _write_json(
        run.analysis_dir / "outcome_targets.json",
        {
            "schema_version": 1,
            "artifact_type": "outcome_targets",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "status": "ok",
            "targets": [{"target_id": "target-contradicted"}, {"target_id": "target-confirmed"}],
            "skipped_records": [],
            "counts": {"targets": 2, "skipped_records": 0},
            "source_artifacts": ["data/research/index.sqlite"],
            "warnings": [],
            "errors": [],
        },
    )


def _write_evaluations(run: RunContext) -> None:
    _write_json(
        run.analysis_dir / "outcome_evaluations.json",
        {
            "schema_version": 1,
            "artifact_type": "outcome_evaluations",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "status": "warning",
            "evaluations": [
                _evaluation("target-confirmed", "event_assessment", "confirmed"),
                _evaluation("target-contradicted", "decision_recommendation", "contradicted"),
            ],
            "counts": {
                "evaluations": 2,
                "evaluated": 2,
                "pending": 0,
                "skipped": 0,
                "stale": 0,
                "insufficient_data": 0,
                "by_target_kind": {"event_assessment": 1, "decision_recommendation": 1},
                "by_evaluation_status": {"evaluated": 2},
                "by_outcome_state": {"confirmed": 1, "contradicted": 1},
            },
            "source_artifacts": ["analysis/outcome_targets.json"],
            "warnings": ["Recorded 1 contradicted outcome target."],
            "errors": [],
        },
    )


def _evaluation(target_id: str, target_kind: str, outcome_state: str) -> dict:
    return {
        "outcome_id": f"outcome:{target_id}:run-1",
        "target_id": target_id,
        "target_kind": target_kind,
        "source_run_id": "source-run",
        "evaluation_run_id": "run-1",
        "evaluated_at": "2026-06-05T00:00:00Z",
        "evaluation_status": "evaluated",
        "outcome_state": outcome_state,
        "observation_window": {
            "source_as_of": "2026-06-04T00:00:00Z",
            "start": "2026-06-05T00:00:00Z",
            "end": "2026-06-05T00:00:00Z",
            "horizon_end": "2026-06-05T00:00:00Z",
            "sample_rows": 1,
            "no_lookahead": True,
        },
        "metrics": {"confirming_evidence_count": 1, "contradicting_evidence_count": 1},
        "evidence": ["Later follow-through record supports the state."],
        "uncertainty": ["Limited follow-through window."],
        "warnings": [],
        "errors": [],
        "source_artifacts": ["analysis/outcome_targets.json"],
    }


def _write_history_state(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "data" / "research" / "metadata" / "outcome_history_state.json",
        {
            "schema_version": 1,
            "artifact_type": "outcome_history_state",
            "updated_at": "2026-06-05T00:00:00Z",
            "status": "ok",
            "storage_path": "data/research/outcomes",
            "history_path": "data/research/outcomes/outcome_history.json",
            "state_path": "data/research/metadata/outcome_history_state.json",
            "totals": {"records": 9, "warning_count": 0, "error_count": 0},
            "sources": [{"source_run_id": "source-run", "record_count": 9}],
            "target_kinds": [{"value": "event_assessment", "record_count": 4}],
            "outcome_states": [{"value": "confirmed", "record_count": 5}],
            "evaluation_statuses": [{"value": "evaluated", "record_count": 9}],
            "source_artifacts": ["runs/run-1/analysis/outcome_evaluations.json"],
            "warnings": [],
            "errors": [],
        },
    )


def _write_full_history_with_sentinel(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "data" / "research" / "outcomes" / "outcome_history.json",
        {
            "records": [
                {
                    "stable_outcome_key": "FULL_HISTORY_SHOULD_NOT_APPEAR",
                    "target_id": "FULL_HISTORY_SHOULD_NOT_APPEAR",
                }
            ]
        },
    )


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
