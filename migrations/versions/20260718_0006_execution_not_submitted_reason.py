"""Persist the stable reason for a definitely-not-submitted action.

Revision ID: 20260718_0006
Revises: 20260717_0005
Create Date: 2026-07-18
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
import json
from typing import Any
from uuid import UUID

from alembic import op
import sqlalchemy as sa


revision = "20260718_0006"
down_revision = "20260717_0005"
branch_labels = None
depends_on = None

SCHEMA = "halpha"
LEGACY_REASON = "LEGACY_DEFINITELY_NOT_SUBMITTED"


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        rendered = format(value, "f")
        if "." in rendered:
            rendered = rendered.rstrip("0").rstrip(".")
        return "0" if rendered in {"", "-0"} else rendered
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        _json_value(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def upgrade() -> None:
    op.add_column(
        "execution_action",
        sa.Column("not_submitted_reason", sa.String(160), nullable=True),
        schema=SCHEMA,
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT execution_action_id, environment_id, environment_kind,
                   authority_class, execution_profile_ref, account_ref,
                   activation_id, plan_event_ref, source_identity, action_kind,
                   action_class, action_terms, action_terms_digest,
                   capital_decision_digest, client_order_id, cancel_target,
                   state, state_version, state_digest, request_digest,
                   call_started_at, call_completed_at, venue_order_refs,
                   venue_fact_refs, unknown_reason, next_query_at,
                   protection_digest, closure_evidence_digest, created_at,
                   updated_at
            FROM halpha.execution_action
            WHERE state = 'NOT_SUBMITTED'
            """
        )
    ).mappings()
    for row in rows:
        values = dict(row)
        values.pop("state_digest")
        values["not_submitted_reason"] = LEGACY_REASON
        connection.execute(
            sa.text(
                """
                UPDATE halpha.execution_action
                SET not_submitted_reason = :reason, state_digest = :state_digest
                WHERE execution_action_id = :execution_action_id
                  AND environment_id = :environment_id
                """
            ),
            {
                "reason": LEGACY_REASON,
                "state_digest": _digest(values),
                "execution_action_id": row["execution_action_id"],
                "environment_id": row["environment_id"],
            },
        )
    op.create_check_constraint(
        "ck_execution_action_not_submitted_reason",
        "execution_action",
        "(state = 'NOT_SUBMITTED' AND not_submitted_reason IS NOT NULL) OR "
        "(state <> 'NOT_SUBMITTED' AND not_submitted_reason IS NULL)",
        schema=SCHEMA,
    )


def downgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT execution_action_id, environment_id, environment_kind,
                   authority_class, execution_profile_ref, account_ref,
                   activation_id, plan_event_ref, source_identity, action_kind,
                   action_class, action_terms, action_terms_digest,
                   capital_decision_digest, client_order_id, cancel_target,
                   state, state_version, state_digest, request_digest,
                   call_started_at, call_completed_at, venue_order_refs,
                   venue_fact_refs, unknown_reason, next_query_at,
                   not_submitted_reason, protection_digest,
                   closure_evidence_digest, created_at, updated_at
            FROM halpha.execution_action
            WHERE state = 'NOT_SUBMITTED'
            """
        )
    ).mappings()
    for row in rows:
        values = dict(row)
        values.pop("state_digest")
        values.pop("not_submitted_reason")
        connection.execute(
            sa.text(
                """
                UPDATE halpha.execution_action
                SET state_digest = :state_digest
                WHERE execution_action_id = :execution_action_id
                  AND environment_id = :environment_id
                """
            ),
            {
                "state_digest": _digest(values),
                "execution_action_id": row["execution_action_id"],
                "environment_id": row["environment_id"],
            },
        )
    op.drop_constraint(
        "ck_execution_action_not_submitted_reason",
        "execution_action",
        type_="check",
        schema=SCHEMA,
    )
    op.drop_column("execution_action", "not_submitted_reason", schema=SCHEMA)
