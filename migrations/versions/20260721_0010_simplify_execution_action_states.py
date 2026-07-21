"""Keep responsibility state separate from Nautilus technical order state.

Revision ID: 20260721_0010
Revises: 20260720_0009
Create Date: 2026-07-21
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


revision = "20260721_0010"
down_revision = "20260720_0009"
branch_labels = None
depends_on = None

SCHEMA = "halpha"

_UPGRADE_STATE = {
    "SUBMITTED_UNKNOWN": "UNKNOWN",
    "ACKNOWLEDGED": "OPEN",
    "WORKING": "OPEN",
    "PARTIALLY_FILLED": "OPEN",
    "FILLED": "OPEN",
    "CANCELLED": "OPEN",
    "REJECTED": "OPEN",
    "EXPIRED": "OPEN",
    "RECONCILED": "CLOSED",
}
_DOWNGRADE_STATE = {
    "UNKNOWN": "SUBMITTED_UNKNOWN",
    "OPEN": "ACKNOWLEDGED",
    "CLOSED": "RECONCILED",
}

_SELECT_ACTIONS = """
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
"""


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


def _drop_state_constraints() -> None:
    for name in (
        "ck_execution_action_closure_evidence",
        "ck_execution_action_unknown_evidence",
        "ck_execution_action_call_evidence",
        "ck_execution_action_state",
    ):
        op.drop_constraint(name, "execution_action", schema=SCHEMA, type_="check")


def _rewrite_states(mapping: dict[str, str]) -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text(_SELECT_ACTIONS)).mappings()
    for row in rows:
        target = mapping.get(str(row["state"]))
        if target is None:
            continue
        values = dict(row)
        values.pop("state_digest")
        values["state"] = target
        values["state_version"] = int(values["state_version"]) + 1
        connection.execute(
            sa.text(
                """
                UPDATE halpha.execution_action
                SET state = :state, state_version = :state_version,
                    state_digest = :state_digest
                WHERE environment_id = :environment_id
                  AND execution_action_id = :execution_action_id
                """
            ),
            {
                "state": target,
                "state_version": values["state_version"],
                "state_digest": _digest(values),
                "environment_id": row["environment_id"],
                "execution_action_id": row["execution_action_id"],
            },
        )


def _create_current_constraints() -> None:
    op.create_check_constraint(
        "ck_execution_action_state",
        "execution_action",
        "state IN ('READY','NOT_SUBMITTED','SUBMITTING','UNKNOWN','OPEN','CLOSED','HANDED_OVER')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_execution_action_call_evidence",
        "execution_action",
        "(state IN ('SUBMITTING','UNKNOWN','OPEN','CLOSED') "
        "AND request_digest IS NOT NULL AND call_started_at IS NOT NULL) OR "
        "(state = 'NOT_SUBMITTED' AND ((request_digest IS NULL AND call_started_at IS NULL) "
        "OR (request_digest IS NOT NULL AND call_started_at IS NOT NULL))) OR "
        "(state IN ('READY','HANDED_OVER') "
        "AND request_digest IS NULL AND call_started_at IS NULL)",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_execution_action_unknown_evidence",
        "execution_action",
        "(state = 'UNKNOWN' AND unknown_reason IS NOT NULL AND next_query_at IS NOT NULL) OR "
        "(state <> 'UNKNOWN' AND unknown_reason IS NULL AND next_query_at IS NULL)",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_execution_action_closure_evidence",
        "execution_action",
        "state <> 'CLOSED' OR closure_evidence_digest IS NOT NULL",
        schema=SCHEMA,
    )


def _create_legacy_constraints() -> None:
    op.create_check_constraint(
        "ck_execution_action_state",
        "execution_action",
        "state IN ('READY','NOT_SUBMITTED','SUBMITTING','SUBMITTED_UNKNOWN',"
        "'ACKNOWLEDGED','WORKING','PARTIALLY_FILLED','FILLED','CANCELLED',"
        "'REJECTED','EXPIRED','RECONCILED','HANDED_OVER')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_execution_action_call_evidence",
        "execution_action",
        "(state IN ('SUBMITTING','SUBMITTED_UNKNOWN','ACKNOWLEDGED','WORKING',"
        "'PARTIALLY_FILLED','FILLED','CANCELLED','REJECTED','EXPIRED','RECONCILED') "
        "AND request_digest IS NOT NULL AND call_started_at IS NOT NULL) OR "
        "state IN ('READY','NOT_SUBMITTED','HANDED_OVER')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_execution_action_unknown_evidence",
        "execution_action",
        "(state = 'SUBMITTED_UNKNOWN' AND unknown_reason IS NOT NULL "
        "AND next_query_at IS NOT NULL) OR "
        "(state <> 'SUBMITTED_UNKNOWN' AND unknown_reason IS NULL "
        "AND next_query_at IS NULL)",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_execution_action_closure_evidence",
        "execution_action",
        "state <> 'RECONCILED' OR closure_evidence_digest IS NOT NULL",
        schema=SCHEMA,
    )


def upgrade() -> None:
    _drop_state_constraints()
    _rewrite_states(_UPGRADE_STATE)
    _create_current_constraints()


def downgrade() -> None:
    _drop_state_constraints()
    _rewrite_states(_DOWNGRADE_STATE)
    _create_legacy_constraints()
