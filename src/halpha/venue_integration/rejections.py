"""Classify venue rejections that are expected parts of an execution policy."""

from __future__ import annotations

from enum import StrEnum
from typing import Iterable

from halpha.venue_integration.facts import (
    terminal_fills_complete,
    terminal_order_status,
)
from halpha.venue_integration.models import (
    ExecutionAction,
    ExecutionActionKind,
    VenueFact,
    VenueFactKind,
)


class VenueRejectionDisposition(StrEnum):
    RETRYABLE_POST_ONLY = "RETRYABLE_POST_ONLY"
    RETRYABLE_PRICE_MATCH = "RETRYABLE_PRICE_MATCH"
    TAKE_PROFIT_TRIGGER_ALREADY_CROSSED = "TAKE_PROFIT_TRIGGER_ALREADY_CROSSED"


def venue_rejection_disposition(
    action: ExecutionAction,
    facts: Iterable[VenueFact],
) -> VenueRejectionDisposition | None:
    """Return a bounded policy disposition; unknown rejection reasons stay errors."""

    materialized = tuple(facts)
    if (
        terminal_order_status(materialized) != "REJECTED"
        or not terminal_fills_complete(action, materialized)
        or any(fact.kind is VenueFactKind.FILL for fact in materialized)
    ):
        return None
    context = action.action_terms.get("execution_context")
    policy = context.get("venue_policy") if isinstance(context, dict) else None
    if not isinstance(policy, dict):
        return None
    reasons = " ".join(
        str(fact.payload.get("reason", "")).casefold()
        for fact in materialized
        if fact.kind is VenueFactKind.ORDER_STATE
        and str(fact.payload.get("status", "")).upper() == "REJECTED"
    )
    if action.action_kind is ExecutionActionKind.TAKE_PROFIT and (
        "-2021" in reasons or "order would immediately trigger" in reasons
    ):
        return VenueRejectionDisposition.TAKE_PROFIT_TRIGGER_ALREADY_CROSSED
    if action.action_kind is not ExecutionActionKind.ENTRY:
        return None
    if policy.get("post_only") is True and (
        "-5022" in reasons
        or "could not be executed as maker" in reasons
        or "post only order will be rejected" in reasons
        or "post-only order will be rejected" in reasons
    ):
        return VenueRejectionDisposition.RETRYABLE_POST_ONLY
    if (
        isinstance(policy.get("price_match"), str)
        and (
            "-5037" in reasons
            or "invalid price match" in reasons
        )
    ):
        return VenueRejectionDisposition.RETRYABLE_PRICE_MATCH
    return None
