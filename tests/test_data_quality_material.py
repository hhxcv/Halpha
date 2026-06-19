from __future__ import annotations

from pathlib import Path

import pytest

from halpha.analysis.data_quality_material import build_data_quality_material
from halpha.pipeline import PipelineError, RunContext
from halpha.storage import write_json


def test_data_quality_material_summarizes_quality_without_embedding_full_stores(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    write_json(
        run.analysis_dir / "data_quality_summary.json",
        {
            "schema_version": 1,
            "artifact_type": "data_quality_summary",
            "run_id": "run-1",
            "created_at": "2026-06-05T00:00:00Z",
            "status": "warning",
            "counts": {
                "checks": 4,
                "ok": 2,
                "warning": 2,
                "degraded": 0,
                "skipped": 0,
                "failed": 0,
                "warnings": 2,
                "errors": 0,
            },
            "checks": [
                {
                    "name": "raw_market",
                    "status": "ok",
                    "scope": "raw",
                    "summary": "1 market item(s), 0 collection error(s).",
                    "warning_count": 0,
                    "error_count": 0,
                    "source_artifacts": ["raw/market.json"],
                    "details": {"items": 1, "warnings": [], "errors": []},
                },
                {
                    "name": "run_index",
                    "status": "warning",
                    "scope": "shared_data",
                    "summary": "run index status: ok.",
                    "warning_count": 1,
                    "error_count": 0,
                    "source_artifacts": ["data/research/index.sqlite"],
                    "details": {
                        "runs": 1,
                        "run_stages": 31,
                        "run_artifacts": 18,
                        "run_latest": 2,
                        "warnings": ["index was rebuilt from current manifest."],
                        "errors": [],
                    },
                },
                {
                    "name": "derivatives_market_views",
                    "status": "warning",
                    "scope": "raw",
                    "summary": "3 derivatives market view(s).",
                    "warning_count": 1,
                    "error_count": 0,
                    "source_artifacts": ["raw/derivatives_market_views.json"],
                    "details": {
                        "views": 3,
                        "insufficient_views": 1,
                        "missing_history_views": 1,
                        "skipped_views": 1,
                        "warnings": ["one derivatives view has insufficient history."],
                        "errors": [],
                    },
                },
                {
                    "name": "personalized_risk_constraints",
                    "status": "ok",
                    "scope": "analysis",
                    "summary": "1 personalized risk constraint record(s), 1 source coverage record(s).",
                    "warning_count": 0,
                    "error_count": 0,
                    "source_artifacts": ["analysis/personalized_risk_constraints.json"],
                    "details": {
                        "records": 1,
                        "state_counts": {"watchlist_relevant": 1},
                        "action_counts": {"annotate": 1},
                        "warnings": [],
                        "errors": [],
                    },
                },
            ],
            "warnings": [
                "index was rebuilt from current manifest.",
                "one derivatives view has insufficient history.",
            ],
            "errors": [],
            "source_artifacts": [
                "analysis/data_quality_summary.json",
                "raw/market.json",
                "raw/derivatives_market_views.json",
                "data/research/index.sqlite",
                "data/market/metadata/derivatives_market_state.json",
                "data/research/metadata/research_data_catalog.json",
            ],
        },
    )
    run.manifest["artifacts"]["research_data_catalog"] = (
        "data/research/metadata/research_data_catalog.json"
    )

    assert build_data_quality_material({}, run) == ["analysis/data_quality_material.md"]

    material = (run.analysis_dir / "data_quality_material.md").read_text(encoding="utf-8")
    assert "artifact_type: analysis_data_quality_material" in material
    assert "status: warning" in material
    assert "quality_status_is_halpha_generated: true" in material
    assert "codex_may_explain_data_quality_status: true" in material
    assert "codex_may_generate_quality_checks: false" in material
    assert "codex_may_generate_validation_results: false" in material
    assert "codex_may_inspect_omitted_tables: false" in material
    assert "full_reusable_history_embedded: false" in material
    assert "full_catalog_embedded: false" in material
    assert "full_run_index_embedded: false" in material
    assert "run_index_lifecycle:" in material
    assert "report_stage_time_skip_as_final_missing: false" in material
    assert "data/research/index.sqlite" in material
    assert "data/market/metadata/derivatives_market_state.json" in material
    assert "derivatives_market_views" in material
    assert "insufficient_views: 1" in material
    assert "personalized_risk_constraints" in material
    assert "state_counts:" in material
    assert "watchlist_relevant: 1" in material
    assert "action_counts:" in material
    assert "annotate: 1" in material
    assert "data/research/metadata/research_data_catalog.json" in material
    assert "funding_rate:" not in material
    assert "CREATE TABLE" not in material
    assert "stable_event_key:" not in material
    assert "content_text:" not in material

    assert run.manifest["artifacts"]["data_quality_material"] == "analysis/data_quality_material.md"
    assert run.manifest["counts"]["data_quality_material_checks"] == 4


def test_data_quality_material_requires_summary_first(tmp_path: Path) -> None:
    run = _run_context(tmp_path)

    with pytest.raises(PipelineError) as error:
        build_data_quality_material({}, run)

    assert str(error.value) == (
        "analysis/data_quality_summary.json was not found; build_data_quality_summary must run first."
    )


def _run_context(tmp_path: Path) -> RunContext:
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
        manifest_path=run_dir / "run_manifest.json",
        config_path=tmp_path / "config.yaml",
        manifest={"artifacts": {}, "counts": {}, "errors": []},
    )
