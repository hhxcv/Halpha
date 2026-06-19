from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from halpha.analysis.intelligence_fusion_material import build_intelligence_fusion_material
from halpha.pipeline import RunContext
from halpha.storage import write_json


def test_intelligence_fusion_material_writes_bounded_records_and_boundaries(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    _write_fusion_artifact(run, records=[_fusion_record(index) for index in range(12)])

    artifacts = build_intelligence_fusion_material({}, run)

    assert artifacts == ["analysis/intelligence_fusion_material.md"]
    material = (run.analysis_dir / "intelligence_fusion_material.md").read_text(encoding="utf-8")
    assert "artifact_type: analysis_intelligence_fusion_material" in material
    assert "audience: ai" in material
    assert "full_intelligence_fusion_json_embedded: false" in material
    assert "full_upstream_json_embedded: false" in material
    assert "codex_may_generate_fusion_states: false" in material
    assert "codex_may_generate_action_levels: false" in material
    assert "record_type: selected_intelligence_fusion_records" in material
    assert "selected_record_count: 8" in material
    assert "omitted_record_count: 4" in material
    assert "source_record_refs" not in material
    assert "full_pairwise_topic_decisions" not in material
    assert run.manifest["artifacts"]["intelligence_fusion_material"] == "analysis/intelligence_fusion_material.md"
    assert run.manifest["counts"]["intelligence_fusion_material_records"] == 8
    assert run.manifest["counts"]["intelligence_fusion_material_omitted_records"] == 4


def _run_context(tmp_path: Path) -> RunContext:
    run_dir = tmp_path / "run"
    raw_dir = run_dir / "raw"
    analysis_dir = run_dir / "analysis"
    codex_context_dir = run_dir / "codex_context"
    report_dir = run_dir / "report"
    for directory in (raw_dir, analysis_dir, codex_context_dir, report_dir):
        directory.mkdir(parents=True, exist_ok=True)
    return RunContext(
        run_id="test-run",
        run_dir=run_dir,
        raw_dir=raw_dir,
        analysis_dir=analysis_dir,
        codex_context_dir=codex_context_dir,
        report_dir=report_dir,
        manifest_path=run_dir / "run_manifest.json",
        config_path=tmp_path / "config.yaml",
        manifest={"artifacts": {}, "counts": {}, "stages": [], "codex": {}, "errors": []},
    )


def _write_fusion_artifact(run: RunContext, *, records: list[dict[str, Any]]) -> None:
    write_json(
        run.analysis_dir / "intelligence_fusion.json",
        {
            "schema_version": 1,
            "artifact_type": "intelligence_fusion",
            "run_id": run.run_id,
            "created_at": "2026-06-05T00:00:00Z",
            "status": "warning",
            "records": records,
            "coverage": [],
            "counts": {
                "records": len(records),
                "state_counts": {"risk_blocked": 1, "supportive": 11},
                "confluence_counts": {"aligned": 12},
                "conflict_counts": {"none": 12},
                "risk_override_counts": {"block": 1, "none": 11},
                "event_override_counts": {"none": 12},
                "outcome_feedback_counts": {"unknown": 12},
                "warnings": 1,
                "errors": 0,
            },
            "warnings": ["fusion source warning"],
            "errors": [],
            "source_artifacts": ["analysis/intelligence_fusion.json", "analysis/market_signals.json"],
        },
    )


def _fusion_record(index: int) -> dict[str, Any]:
    state = "risk_blocked" if index == 0 else "supportive"
    return {
        "fusion_record_id": f"fusion:btcusdt:{index}",
        "scope": {
            "symbol": "BTCUSDT",
            "timeframe": f"{index}h",
            "asset": None,
            "chain": None,
            "region": None,
        },
        "state": state,
        "direction": "unknown" if state == "risk_blocked" else "bullish",
        "confidence": "medium",
        "confluence": {
            "state": "aligned",
            "supporting_sources": 2,
            "independent_sources": 2,
            "source_layers": ["strategy", "factor"],
        },
        "conflict": {"state": "none", "conflicting_sources": 0, "source_layers": []},
        "risk_override": {
            "state": "block" if state == "risk_blocked" else "none",
            "risk_level": "extreme" if state == "risk_blocked" else "low",
            "reasons": ["risk block"] if state == "risk_blocked" else [],
        },
        "event_override": {"state": "none", "severity": "unknown", "reasons": []},
        "outcome_feedback": {"state": "unknown", "source_records": 0},
        "evidence": [f"fusion evidence {index}"],
        "uncertainty": [f"fusion uncertainty {index}"],
        "warnings": [],
        "errors": [],
        "source_artifacts": ["analysis/intelligence_fusion.json", "analysis/market_signals.json"],
        "source_record_refs": [
            {
                "source_layer": "strategy",
                "source_artifact": "analysis/market_signals.json",
                "source_record_id": f"signal:{index}",
            }
        ],
        "created_at": "2026-06-05T00:00:00Z",
    }
