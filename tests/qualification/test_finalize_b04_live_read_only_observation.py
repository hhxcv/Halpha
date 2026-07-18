from __future__ import annotations

from tools.qualification.finalize_b04_live_read_only_observation import (
    non_smtp_checks_complete,
)


def test_non_smtp_completion_keeps_actual_delivery_independent() -> None:
    evidence = {
        "checks": {
            "read_only_runtime_ready": True,
            "minimum_seven_day_duration_elapsed": True,
            "market_data_gap_recovered": True,
            "actual_test_email_qualified": False,
        },
        "errors": [],
    }
    assert non_smtp_checks_complete(evidence)
    evidence["checks"]["market_data_gap_recovered"] = False
    assert not non_smtp_checks_complete(evidence)


def test_non_smtp_completion_rejects_integrity_errors() -> None:
    evidence = {
        "checks": {
            "read_only_runtime_ready": True,
            "actual_test_email_qualified": True,
        },
        "errors": ["EVENT_DIGEST_MISMATCH"],
    }
    assert not non_smtp_checks_complete(evidence)
