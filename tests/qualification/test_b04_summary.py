from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from halpha.source_identity import source_sha256_digest

from tools.qualification.summarize_b04_evidence import (
    REQUIRED_B04_MANIFEST_BINDINGS,
    REQUIRED_SOURCE_SHA256_ARTIFACTS,
    _json_artifact,
    classify_summary,
    windows_soak_contract_error,
)


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


def test_manifest_contract_has_all_three_external_gates_and_the_final_summary() -> None:
    assert {
        "b04_windows_72h_soak",
        "b04_actual_smtp_delivery",
        "b04_live_read_only_observation",
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


def test_windows_soak_contract_requires_schema_v3_source_and_unbiased_awake_time() -> None:
    started = 1_000
    duration = 72 * 3600 * 10_000_000
    source = {"src/halpha/example.py": "1" * 64}
    evidence = {
        "schema_version": 3,
        "started_unbiased_100ns": started,
        "observed_unbiased_100ns": started + duration,
        "elapsed_hours": 72.0,
        "wall_elapsed_hours": 72.0,
        "sleep_or_hibernate_seconds": 0.0,
        "source_sha256": source,
        "source_sha256_digest": source_sha256_digest(source),
        "current_source_sha256_digest": source_sha256_digest(source),
        "checks": {
            "app_runtime_source_identity_matches_current": True,
            "configuration_identity_unchanged": True,
            "continuous_process_identity_unchanged": True,
            "executor_runtime_source_identity_matches_current": True,
            "minimum_72_hours_observed": True,
            "no_sleep_or_hibernate_over_60_seconds": True,
            "source_identity_unchanged": True,
        },
    }

    assert windows_soak_contract_error(evidence) is None
    assert windows_soak_contract_error({**evidence, "schema_version": 1}) == (
        "WINDOWS_SOAK_SCHEMA_V3_REQUIRED"
    )
    assert windows_soak_contract_error(
        {**evidence, "current_source_sha256_digest": "2" * 64}
    ) == "WINDOWS_SOAK_CURRENT_SOURCE_DIGEST_MISMATCH"
    assert windows_soak_contract_error(
        {
            **evidence,
            "wall_elapsed_hours": 73.0,
            "sleep_or_hibernate_seconds": 3600.0,
        }
    ) == "WINDOWS_SLEEP_OR_HIBERNATION_LIMIT_EXCEEDED"


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
