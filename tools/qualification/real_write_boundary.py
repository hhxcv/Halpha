"""Shared fail-closed projection for qualification evidence summaries."""

from __future__ import annotations

from typing import Any, Mapping


EXPECTED_CLOSED_REAL_WRITE_BOUNDARY: dict[str, Any] = {
    "recorded_real_write_state": "CLOSED",
    "live_safety_real_write_state": "CLOSED",
    "current_activation_id": None,
    "recorded_live_credentials_loaded": False,
    "live_safety_credentials_loaded": False,
    "live_execution_actions_created": False,
    "venue_live_writes_observed": False,
}


def assess_closed_real_write_boundary(
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    current_facts = plan.get("current_facts")
    facts = current_facts if isinstance(current_facts, Mapping) else {}
    current_runtime = facts.get("runtime")
    runtime = current_runtime if isinstance(current_runtime, Mapping) else {}
    current_live_safety = plan.get("live_safety")
    live_safety = (
        current_live_safety if isinstance(current_live_safety, Mapping) else {}
    )
    boundary = {
        "recorded_real_write_state": runtime.get("real_write_state", "MISSING"),
        "live_safety_real_write_state": live_safety.get(
            "real_write_state", "MISSING"
        ),
        "current_activation_id": live_safety.get(
            "current_activation_id", "MISSING"
        ),
        "recorded_live_credentials_loaded": runtime.get(
            "live_credentials_loaded", "MISSING"
        ),
        "live_safety_credentials_loaded": live_safety.get(
            "live_credentials_loaded", "MISSING"
        ),
        "live_execution_actions_created": runtime.get(
            "live_execution_actions_created", "MISSING"
        ),
        "venue_live_writes_observed": runtime.get(
            "venue_live_writes_observed", "MISSING"
        ),
    }
    boundary["status"] = (
        "QUALIFIED"
        if boundary == EXPECTED_CLOSED_REAL_WRITE_BOUNDARY
        else "REJECTED"
    )
    return boundary
