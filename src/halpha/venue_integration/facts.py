"""Pure DAT fact construction and same-environment attribution checks."""

from __future__ import annotations

from datetime import datetime
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
        "impact_scope": None,
        "affected_reference_refs": None,
    }
    fields["content_digest"] = venue_fact_content_digest(fields)
    return VenueFact(**fields)
