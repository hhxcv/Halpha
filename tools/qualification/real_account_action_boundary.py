"""Shared projection of the current real-account trading safety facts."""

from __future__ import annotations

from typing import Any, Mapping


EXPECTED_DISABLED_REAL_ACCOUNT_TRADING: dict[str, Any] = {
    "exchange_change_requests_allowed": False,
    "credentials_loaded": False,
    "current_activation_id": None,
    "execution_actions_created": False,
    "exchange_changes_observed": False,
}


def assess_disabled_real_account_trading(
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    raw_facts = plan.get("real_account_trading")
    facts = raw_facts if isinstance(raw_facts, Mapping) else {}
    boundary = {
        field: facts.get(field, "MISSING")
        for field in EXPECTED_DISABLED_REAL_ACCOUNT_TRADING
    }
    boundary["status"] = (
        "QUALIFIED"
        if boundary == EXPECTED_DISABLED_REAL_ACCOUNT_TRADING
        else "REJECTED"
    )
    return boundary
