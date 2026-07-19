"""The physical product-record inventory."""

from __future__ import annotations


RECORD_FAMILY_OWNERS = {
    "trade_plan_draft": "TRADEPLAN",
    "trade_plan_version": "TRADEPLAN",
    "plan_activation": "TRADEPLAN",
    "plan_event": "TRADEPLAN",
    "venue_fact": "DAT",
    "stop_state_version": "CAP",
    "execution_action": "EXE",
    "review": "OUT",
    "command": "UX",
    "receipt": "UX",
}

PRODUCT_RECORD_FAMILIES = tuple(RECORD_FAMILY_OWNERS)
