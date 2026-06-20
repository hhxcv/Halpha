from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from halpha.pipeline import RunContext
from halpha.storage import write_json
from halpha.strategy_lifecycle_material import build_strategy_lifecycle_material


def test_strategy_lifecycle_material_bounds_records_and_omissions(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    write_json(run.analysis_dir / "strategy_lifecycle_state.json", _lifecycle_state(record_count=10))

    artifacts = build_strategy_lifecycle_material({}, run)

    material = (run.analysis_dir / "strategy_lifecycle_material.md").read_text(encoding="utf-8")
    assert artifacts == ["analysis/strategy_lifecycle_material.md"]
    assert "artifact_type: analysis_strategy_lifecycle_material" in material
    assert "record_type: strategy_lifecycle_overview" in material
    assert "record_type: selected_strategy_lifecycle_records" in material
    assert "selected_record_count: 8" in material
    assert "omitted_record_count: 2" in material
    assert "lifecycle_status: degraded" in material
    assert "lifecycle_status: retired" in material
    assert "codex_may_explain_lifecycle_status: true" in material
    assert "codex_may_generate_lifecycle_states: false" in material
    assert "codex_may_create_policy_records: false" in material
    assert "codex_may_promote_or_retire_strategies: false" in material
    assert "full_strategy_lifecycle_json_embedded: false" in material
    assert "full_local_lifecycle_policy_input_embedded: false" in material
    assert "PRIVATE POLICY NOTE" not in material
    assert run.manifest["artifacts"]["strategy_lifecycle_material"] == (
        "analysis/strategy_lifecycle_material.md"
    )
    assert run.manifest["counts"]["strategy_lifecycle_material_records"] == 8
    assert run.manifest["counts"]["strategy_lifecycle_material_omitted_records"] == 2
    assert run.manifest["strategy_lifecycle_material"]["status"] == "warning"


def test_strategy_lifecycle_material_skips_when_state_missing(tmp_path: Path) -> None:
    run = _run_context(tmp_path)

    artifacts = build_strategy_lifecycle_material({}, run)

    assert artifacts == []
    assert not (run.analysis_dir / "strategy_lifecycle_material.md").exists()
    assert run.manifest["strategy_lifecycle_material"]["status"] == "not_generated"
    assert run.manifest["counts"]["strategy_lifecycle_material_records"] == 0
    assert "strategy_lifecycle_material" not in run.manifest["artifacts"]


def test_strategy_lifecycle_material_rejects_invalid_state_artifact(tmp_path: Path) -> None:
    run = _run_context(tmp_path)
    write_json(
        run.analysis_dir / "strategy_lifecycle_state.json",
        {"artifact_type": "wrong", "records": []},
    )

    with pytest.raises(Exception) as exc_info:
        build_strategy_lifecycle_material({}, run)

    assert "must have artifact_type strategy_lifecycle_state" in str(exc_info.value)


def _lifecycle_state(*, record_count: int) -> dict[str, Any]:
    statuses = [
        "degraded",
        "retired",
        "watchlisted",
        "rejected",
        "failed",
        "insufficient_evidence",
        "effective",
        "active_candidate",
        "effective",
        "active_candidate",
    ]
    records = [
        _record(index=index, status=statuses[index])
        for index in range(record_count)
    ]
    return {
        "schema_version": 1,
        "artifact_type": "strategy_lifecycle_state",
        "run_id": "run-1",
        "created_at": "2026-06-06T00:00:00Z",
        "status": "warning",
        "records": records,
        "coverage": [
            {
                "source_layer": "gate",
                "source_artifact": "analysis/strategy_effectiveness_gates.json",
                "status": "used",
                "records": record_count,
            },
            {
                "source_layer": "policy",
                "source_artifact": "config:quant.lifecycle_policy.records",
                "status": "used",
                "records": 1,
            },
        ],
        "counts": {
            "records": record_count,
            "by_lifecycle_status": _count_by(records, "lifecycle_status"),
            "policy_records": 1,
            "warnings": 1,
            "errors": 0,
        },
        "warnings": ["Lifecycle state contains review-required records."],
        "errors": [],
        "source_artifacts": ["analysis/strategy_effectiveness_gates.json"],
    }


def _record(*, index: int, status: str) -> dict[str, Any]:
    return {
        "lifecycle_record_id": f"strategy_lifecycle:strategy_{index}:BTCUSDT:1d",
        "strategy_name": f"strategy_{index}",
        "scope": {"symbol": "BTCUSDT", "timeframe": "1d"},
        "strategy_contract_version": "1",
        "parameter_version": f"sha256:{index:016d}",
        "parameter_digest": f"sha256:{index:016d}",
        "lifecycle_status": status,
        "health_state": {
            "state": "degraded" if status == "degraded" else "retired" if status == "retired" else "watch",
            "confidence": "high" if status == "retired" else "medium",
            "reasons": [f"strategy_gate_status={status}."],
        },
        "degradation": {
            "state": "degraded" if status == "degraded" else "none",
            "reasons": ["Prior outcome feedback was not aligned."] if status == "degraded" else [],
            "source_record_refs": [f"outcome:{index}"],
        },
        "regime_weakness": {"state": "unknown", "regimes": [], "reasons": []},
        "promotion": {"state": "not_requested", "policy_refs": []},
        "retirement": {
            "state": "explicitly_retired" if status == "retired" else "not_retired",
            "policy_refs": ["lifecycle_policy:strategy_1:retire:abc"] if status == "retired" else [],
        },
        "evidence": [f"strategy_gate_status={status}."],
        "uncertainty": ["Lifecycle state is deterministic research material."],
        "warnings": [],
        "errors": [],
        "source_artifacts": ["analysis/strategy_effectiveness_gates.json"],
        "source_record_refs": [f"gate:{index}"],
    }


def _count_by(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(record.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _run_context(tmp_path: Path) -> RunContext:
    run_dir = tmp_path / "runs" / "run-1"
    raw_dir = run_dir / "raw"
    analysis_dir = run_dir / "analysis"
    codex_context_dir = run_dir / "codex_context"
    report_dir = run_dir / "report"
    for directory in (raw_dir, analysis_dir, codex_context_dir, report_dir):
        directory.mkdir(parents=True)
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
