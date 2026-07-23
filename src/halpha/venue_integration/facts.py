"""Pure DAT fact construction and same-environment attribution checks."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from halpha.domain_values import content_digest
from halpha.venue_integration.models import (
    ExecutionAction,
    VenueFact,
    VenueFactAttributionClass,
    VenueFactKind,
    VenueFactSourceClass,
    venue_fact_content_digest,
)


TERMINAL_ORDER_STATUSES = frozenset(
    {"FILLED", "CANCELLED", "REJECTED", "EXPIRED"}
)


def latest_execution_status(facts: Iterable[VenueFact]) -> str | None:
    """Project technical order status from authoritative Nautilus facts.

    The durable execution action deliberately does not copy Nautilus' order
    lifecycle. Consumers that need the current technical status derive it from
    the original order and fill observations.
    """

    observations: list[tuple[tuple[datetime, datetime, datetime, str], str]] = []
    for fact in facts:
        status: str | None = None
        if fact.kind is VenueFactKind.ORDER_STATE:
            value = str(fact.payload.get("status", "")).upper()
            status = {
                "ACCEPTED": "WORKING",
                "ACKNOWLEDGED": "WORKING",
                "NEW": "WORKING",
                "CANCELED": "CANCELLED",
            }.get(value, value)
        elif fact.kind is VenueFactKind.FILL:
            try:
                leaves = Decimal(str(fact.payload.get("leaves_quantity")))
            except (InvalidOperation, TypeError, ValueError):
                status = "PARTIALLY_FILLED"
            else:
                status = "FILLED" if leaves == 0 else "PARTIALLY_FILLED"
        if status:
            observations.append(
                (
                    (
                        fact.source_time or fact.cutoff,
                        fact.cutoff,
                        fact.received_at,
                        fact.venue_fact_id,
                    ),
                    status,
                )
            )
    if not observations:
        return None
    terminal_observations = tuple(
        observation
        for observation in observations
        if observation[1] in TERMINAL_ORDER_STATUSES
    )
    if terminal_observations:
        # Nautilus can emit a late OrderUpdated callback after OrderFilled.
        # Retain the raw callback as a fact, but never let a non-terminal
        # callback reopen a venue order whose terminal result is already
        # authoritative. Competing terminal facts still resolve by event order.
        return max(terminal_observations)[1]
    return max(observations)[1]


def order_is_working(facts: Iterable[VenueFact]) -> bool:
    return latest_execution_status(facts) in {"WORKING", "PARTIALLY_FILLED"}


def terminal_order_status(facts: Iterable[VenueFact]) -> str | None:
    status = latest_execution_status(facts)
    return status if status in TERMINAL_ORDER_STATUSES else None


def terminal_fills_complete(
    action: ExecutionAction,
    facts: Iterable[VenueFact],
) -> bool:
    """Prove that every fill preceding a terminal order result is persisted.

    A terminal status alone is not a cumulative execution report.  In
    particular, CANCELLED and EXPIRED can race a final fill callback.  The
    terminal observation must therefore carry the venue-derived cumulative
    filled quantity, and the locally persisted fill facts must add up to it.
    A final fill with zero leaves is the equivalent cumulative proof for the
    Nautilus path which does not emit a separate FILLED order-state callback.
    """

    materialized = tuple(facts)
    terminal_fact = _latest_terminal_fact(materialized)
    if terminal_fact is None:
        return False
    status = terminal_order_status((terminal_fact,))
    try:
        requested = Decimal(str(action.action_terms["quantity"]))
    except (InvalidOperation, KeyError, TypeError, ValueError):
        return False
    if requested < 0:
        return False

    cumulative_raw = terminal_fact.payload.get("cumulative_filled_quantity")
    if cumulative_raw is None:
        try:
            terminal_leaves = Decimal(
                str(terminal_fact.payload.get("leaves_quantity"))
            )
        except (InvalidOperation, TypeError, ValueError):
            terminal_leaves = None
        if (
            terminal_fact.kind is VenueFactKind.FILL
            and status == "FILLED"
            and terminal_leaves == 0
        ):
            cumulative = requested
        else:
            return False
    else:
        try:
            cumulative = Decimal(str(cumulative_raw))
        except (InvalidOperation, TypeError, ValueError):
            return False
    if cumulative < 0 or cumulative > requested:
        return False
    if status == "FILLED" and cumulative != requested:
        return False
    if status == "REJECTED" and cumulative != 0:
        return False

    persisted = Decimal(0)
    for fact in materialized:
        if fact.kind is not VenueFactKind.FILL:
            continue
        raw_quantity = fact.payload.get("last_quantity")
        try:
            quantity = Decimal(str(raw_quantity))
        except (InvalidOperation, TypeError, ValueError):
            return False
        if quantity <= 0:
            return False
        persisted += quantity
    return persisted == cumulative


def _latest_terminal_fact(facts: tuple[VenueFact, ...]) -> VenueFact | None:
    terminal_facts = tuple(
        fact for fact in facts if terminal_order_status((fact,)) is not None
    )
    if not terminal_facts:
        return None
    return max(
        terminal_facts,
        key=lambda fact: (
            fact.source_time or fact.cutoff,
            fact.cutoff,
            fact.received_at,
            fact.venue_fact_id,
        ),
    )


def build_venue_fact(
    *,
    venue_fact_id: str,
    environment_id: str,
    venue_ref: str,
    account_ref: str | None,
    instrument_ref: str | None,
    kind: VenueFactKind,
    source_class: VenueFactSourceClass,
    source_object_id: str,
    source_sequence: str,
    source_time: datetime | None,
    received_at: datetime,
    cutoff: datetime,
    payload: dict[str, Any],
    action: ExecutionAction | None = None,
    impact_scope: dict[str, Any] | None = None,
    affected_reference_refs: tuple[str, ...] | None = None,
) -> VenueFact:
    """Normalize one authoritative observation without inventing venue identity."""

    if action is not None:
        if (
            action.environment_id != environment_id
            or action.account_ref != account_ref
            or action.action_terms.get("instrument_ref") != instrument_ref
        ):
            raise ValueError("VENUE_FACT_ATTRIBUTION_INVALID")
        activation_ref = action.activation_id
        action_ref = action.execution_action_id
        attribution_class = VenueFactAttributionClass.HALPHA_EXECUTION
        attribution_digest = content_digest(
            {
                "environment_id": environment_id,
                "activation_ref": activation_ref,
                "action_ref": action_ref,
                "client_order_id": action.client_order_id,
                "cancel_target": action.cancel_target,
                "action_terms_digest": action.action_terms_digest,
                "source_object_id": source_object_id,
                "source_sequence": source_sequence,
            }
        )
    else:
        activation_ref = None
        action_ref = None
        attribution_class = None
        attribution_digest = None
    fields: dict[str, Any] = {
        "venue_fact_id": venue_fact_id,
        "environment_id": environment_id,
        "venue_ref": venue_ref,
        "account_ref": account_ref,
        "instrument_ref": instrument_ref,
        "kind": kind,
        "source_class": source_class,
        "source_object_id": source_object_id,
        "source_sequence": source_sequence,
        "source_time": source_time,
        "received_at": received_at,
        "cutoff": cutoff,
        "schema_version": 1,
        "payload": payload,
        "activation_ref": activation_ref,
        "action_ref": action_ref,
        "attribution_digest": attribution_digest,
        "attribution_class": attribution_class,
        "handover_command_ref": None,
        "supersedes_ref": None,
        "correction_reason": None,
        "correction_evidence_refs": None,
        "correction_effective_time": None,
        "impact_scope": impact_scope,
        "affected_reference_refs": affected_reference_refs,
    }
    fields["content_digest"] = venue_fact_content_digest(fields)
    return VenueFact(**fields)
