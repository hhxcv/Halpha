"""The accepted P0 physical product-record inventory."""

from __future__ import annotations


RECORD_FAMILY_OWNERS = {
    "trade_plan_draft": "TRADEPLAN",
    "trade_plan_version": "TRADEPLAN",
    "plan_activation": "TRADEPLAN",
    "plan_event": "TRADEPLAN",
    "venue_fact": "DAT",
    "account_capital_limit_version": "CAP",
    "machine_authorization_version": "CAP",
    "plan_allocation": "CAP",
    "stop_state_version": "CAP",
    "execution_action": "EXE",
    "review": "OUT",
    "improvement_handoff": "OUT",
    "task": "UX",
    "command": "UX",
    "receipt": "UX",
    "notification": "UX",
}

PRODUCT_RECORD_FAMILIES = tuple(RECORD_FAMILY_OWNERS)

if len(PRODUCT_RECORD_FAMILIES) != 16:
    raise RuntimeError("P0_PRODUCT_RECORD_FAMILY_COUNT_MUST_BE_16")
