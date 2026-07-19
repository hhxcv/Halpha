from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import yaml

from tools.qualification.summarize_b04_evidence import (
    REQUIRED_B04_MANIFEST_BINDINGS,
    REQUIRED_SOURCE_SHA256_ARTIFACTS,
    _json_artifact,
    classify_summary,
    is_current_b04_package,
)
from tools.qualification.real_write_boundary import (
    EXPECTED_CLOSED_REAL_WRITE_BOUNDARY,
    assess_closed_real_write_boundary,
)


ROOT = Path(__file__).resolve().parents[2]


def test_current_plan_uses_the_shared_closed_real_write_boundary() -> None:
    plan = yaml.safe_load(
        (ROOT / "docs/L4/HALPHA-PLAN-001-current-construction-plan.yaml").read_text(
            encoding="utf-8"
        )
    )

    boundary = assess_closed_real_write_boundary(plan)

    assert boundary == {
        **EXPECTED_CLOSED_REAL_WRITE_BOUNDARY,
        "status": "QUALIFIED",
    }


def test_summary_requires_every_artifact_test_and_gate() -> None:
    qualified = {"a": {"status": "QUALIFIED"}, "b": {"status": "QUALIFIED"}}
    assert classify_summary(qualified, pytest_status="QUALIFIED", gates_qualified=True) == "QUALIFIED"
    assert classify_summary(qualified, pytest_status="MISSING", gates_qualified=True) == "IN_PROGRESS"
    assert (
        classify_summary(
            {**qualified, "b": {"status": "IN_PROGRESS"}},
            pytest_status="QUALIFIED",
            gates_qualified=True,
        )
        == "IN_PROGRESS"
    )
    assert (
        classify_summary(
            {**qualified, "b": {"status": "REJECTED"}},
            pytest_status="QUALIFIED",
            gates_qualified=True,
        )
        == "REJECTED"
    )
    assert classify_summary(qualified, pytest_status="QUALIFIED", gates_qualified=False) == "REJECTED"


def test_current_b04_package_uses_simple_recorded_states() -> None:
    assert is_current_b04_package("IN_PROGRESS") is True
    assert is_current_b04_package("COMPLETED") is True
    assert is_current_b04_package("NOT_STARTED") is False


def test_manifest_contract_keeps_direct_delivery_and_final_summary() -> None:
    assert {
        "b04_actual_smtp_delivery",
        "b04_summary",
    } <= REQUIRED_B04_MANIFEST_BINDINGS


def test_all_behavioral_b04_artifacts_require_current_source_binding() -> None:
    assert {
        "critical_invariant_trace",
        "empty_database_restore",
        "historical_backtest",
        "notification_boundary",
        "outcome_boundary",
        "product_demo_cycle",
        "windows_fault_drills",
    } <= REQUIRED_SOURCE_SHA256_ARTIFACTS


def test_qualified_artifact_rejects_bound_source_drift(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    source.write_text("before\n", encoding="utf-8")
    before_digest = sha256(source.read_bytes()).hexdigest()
    artifact = tmp_path / "artifact.json"
    artifact.write_text(
        json.dumps(
            {
                "status": "QUALIFIED",
                "source_sha256": {
                    "source.py": before_digest,
                },
            }
        ),
        encoding="utf-8",
    )

    assert _json_artifact(tmp_path, "artifact.json")["status"] == "QUALIFIED"

    source.write_text("after\n", encoding="utf-8")
    after_digest = sha256(source.read_bytes()).hexdigest()
    result = _json_artifact(tmp_path, "artifact.json")

    assert result["status"] == "REJECTED"
    assert result["error"] == "SOURCE_SHA256_DRIFT"
    assert result["source_sha256_status"] == "REJECTED"
    assert result["source_sha256_drift"] == [
        {
            "path": "source.py",
            "reason": "SOURCE_SHA256_MISMATCH",
            "expected": before_digest,
            "actual": after_digest,
        }
    ]


def test_legacy_qualified_artifact_without_source_map_is_not_reclassified(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_text(json.dumps({"status": "QUALIFIED"}), encoding="utf-8")

    result = _json_artifact(tmp_path, "artifact.json")

    assert result["status"] == "QUALIFIED"
    assert result["source_sha256_status"] == "NOT_DECLARED"
    assert result["source_sha256_drift"] == []


def test_required_source_binding_rejects_qualified_artifact_without_map(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_text(json.dumps({"status": "QUALIFIED"}), encoding="utf-8")

    result = _json_artifact(
        tmp_path,
        "artifact.json",
        require_source_sha256=True,
    )

    assert result["status"] == "REJECTED"
    assert result["error"] == "SOURCE_SHA256_REQUIRED"
    assert result["source_sha256_status"] == "NOT_DECLARED"
