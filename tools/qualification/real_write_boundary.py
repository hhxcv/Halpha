"""Shared fail-closed projection for construction evidence summaries."""

from __future__ import annotations

from typing import Any, Mapping


EXPECTED_CLOSED_REAL_WRITE_BOUNDARY = {
    "live_write_build_capability": "NOT_QUALIFIED",
    "b05_real_capital_eligibility": "BLOCKED",
    "runtime_real_write_gate": "CLOSED",
}


def assess_closed_real_write_boundary(
    current_state: Mapping[str, Any],
) -> dict[str, str]:
    boundary = {
        field: str(current_state.get(field, "MISSING"))
        for field in EXPECTED_CLOSED_REAL_WRITE_BOUNDARY
    }
    boundary["status"] = (
        "QUALIFIED"
        if boundary == EXPECTED_CLOSED_REAL_WRITE_BOUNDARY
        else "REJECTED"
    )
    return boundary
