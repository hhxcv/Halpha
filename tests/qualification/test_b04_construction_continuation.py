from __future__ import annotations

from pathlib import Path

import pytest

from tools.qualification.finalize_b04_construction_continuation import (
    ConstructionContinuationError,
    _canonical_digest,
    _verify_embedded_digest,
    read_junit_summary,
    select_platform_continuity_checkpoint,
)


def _report(*, recorded_hours: float = 8.25, observed_delta_hours: float = 8.25) -> dict:
    started = 100_000_000
    observed = started + int(observed_delta_hours * 3600 * 10_000_000)
    return {
        "started_unbiased_100ns": started,
        "checkpoints": [
            {
                "observed_at": "2026-07-19T01:15:00Z",
                "unbiased_interrupt_time_100ns": observed,
                "awake_elapsed_hours": recorded_hours,
                "source_identity_unchanged": False,
                "configuration_identity_unchanged": False,
                "continuous_identity_unchanged": False,
            }
        ],
    }


def test_platform_claim_uses_same_boot_awake_clock_not_old_build_identity() -> None:
    selected = select_platform_continuity_checkpoint(_report())

    assert selected["same_boot_unbiased_clock_monotonic"] is True
    assert selected["awake_elapsed_hours"] == pytest.approx(8.25)


def test_platform_claim_rejects_elapsed_value_not_supported_by_raw_clock() -> None:
    with pytest.raises(
        ConstructionContinuationError,
        match="PLATFORM_AWAKE_8H_CHECKPOINT_NOT_FOUND",
    ):
        select_platform_continuity_checkpoint(
            _report(recorded_hours=8.25, observed_delta_hours=7.5)
        )


def test_platform_claim_rejects_unmet_awake_duration() -> None:
    with pytest.raises(
        ConstructionContinuationError,
        match="PLATFORM_AWAKE_8H_CHECKPOINT_NOT_FOUND",
    ):
        select_platform_continuity_checkpoint(
            _report(recorded_hours=7.99, observed_delta_hours=7.99)
        )


def test_junit_summary_reads_leaf_suite_once(tmp_path: Path) -> None:
    junit = tmp_path / "pytest.xml"
    junit.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuites name="pytest tests">
  <testsuite name="pytest" tests="4" failures="0" errors="0" skipped="1" />
</testsuites>
""",
        encoding="utf-8",
    )

    assert read_junit_summary(junit) == {
        "tests": 4,
        "failures": 0,
        "errors": 0,
        "skipped": 1,
    }


def test_old_bare_digest_is_recomputed_then_normalized() -> None:
    report = {"schema_version": 3, "status": "REJECTED"}
    report["evidence_digest"] = _canonical_digest(report).removeprefix("sha256:")

    assert _verify_embedded_digest(report) == "sha256:" + report["evidence_digest"]
