from __future__ import annotations

import json
from pathlib import Path

from halpha.build_manifest import (
    DEFAULT_ARTIFACT_SPECS,
    SCHEMA_VERSION,
    ArtifactSpec,
    _artifact_bindings,
)


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_qualification_binding_requires_the_expected_json_status(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.json"
    spec = ArtifactSpec(
        "qualification",
        "evidence.json",
        expected_json_status="QUALIFIED",
    )

    _write_json(evidence, {"status": "IN_PROGRESS"})
    in_progress = _artifact_bindings(tmp_path, (spec,))[0]
    assert in_progress["status"] == "STATUS_MISMATCH"
    assert in_progress["qualification_status"] == "IN_PROGRESS"

    _write_json(evidence, {"status": "QUALIFIED"})
    qualified = _artifact_bindings(tmp_path, (spec,))[0]
    assert qualified["status"] == "BOUND"
    assert qualified["expected_json_status"] == "QUALIFIED"
    assert qualified["qualification_status"] == "QUALIFIED"


def test_invalid_or_missing_qualification_evidence_never_binds(tmp_path: Path) -> None:
    spec = ArtifactSpec(
        "qualification",
        "evidence.json",
        expected_json_status="QUALIFIED",
    )
    missing = _artifact_bindings(tmp_path, (spec,))[0]
    assert missing["status"] == "MISSING"
    assert missing["qualification_status"] is None

    evidence = tmp_path / "evidence.json"
    evidence.write_text("not-json", encoding="utf-8")
    invalid = _artifact_bindings(tmp_path, (spec,))[0]
    assert invalid["status"] == "STATUS_MISMATCH"
    assert invalid["qualification_status"] == "INVALID_JSON"


def test_schema_two_requires_the_direct_b02_to_b04_evidence_set() -> None:
    names = {spec.name for spec in DEFAULT_ARTIFACT_SPECS}
    assert SCHEMA_VERSION == 2
    assert {
        "b02_summary",
        "b03_summary",
        "b04_historical_backtest",
        "b04_product_demo_cycle",
        "b04_browser_workbench",
        "b04_implemented_complexity_budget",
        "b04_actual_smtp_delivery",
        "b04_summary",
        "nonsecret_live_write_config",
    } <= names
    assert len(names) == len(DEFAULT_ARTIFACT_SPECS)
