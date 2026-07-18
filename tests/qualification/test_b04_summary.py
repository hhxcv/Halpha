from __future__ import annotations

from tools.qualification.summarize_b04_evidence import (
    REQUIRED_B04_MANIFEST_BINDINGS,
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


def test_windows_soak_contract_requires_schema_v2_unbiased_awake_time() -> None:
    started = 1_000
    duration = 72 * 3600 * 10_000_000
    evidence = {
        "schema_version": 2,
        "started_unbiased_100ns": started,
        "observed_unbiased_100ns": started + duration,
        "elapsed_hours": 72.0,
        "wall_elapsed_hours": 72.0,
        "sleep_or_hibernate_seconds": 0.0,
        "checks": {
            "minimum_72_hours_observed": True,
            "no_sleep_or_hibernate_over_60_seconds": True,
        },
    }

    assert windows_soak_contract_error(evidence) is None
    assert windows_soak_contract_error({**evidence, "schema_version": 1}) == (
        "WINDOWS_SOAK_SCHEMA_V2_REQUIRED"
    )
    assert windows_soak_contract_error(
        {
            **evidence,
            "wall_elapsed_hours": 73.0,
            "sleep_or_hibernate_seconds": 3600.0,
        }
    ) == "WINDOWS_SLEEP_OR_HIBERNATION_LIMIT_EXCEEDED"
