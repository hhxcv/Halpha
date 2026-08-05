"""Allow user handover to retain evidence from a called action.

Revision ID: 20260729_0009
Revises: 20260728_0008
"""

from __future__ import annotations

from alembic import op


revision = "20260729_0009"
down_revision = "20260728_0008"
branch_labels = None
depends_on = None


_CALL_EVIDENCE_CHECK = (
    "(state IN ('SUBMITTING','UNKNOWN','OPEN','CLOSED') "
    "AND request_digest IS NOT NULL AND call_started_at IS NOT NULL) OR "
    "(state IN ('NOT_SUBMITTED','HANDED_OVER') "
    "AND ((request_digest IS NULL AND call_started_at IS NULL) "
    "OR (request_digest IS NOT NULL AND call_started_at IS NOT NULL))) OR "
    "(state = 'READY' "
    "AND request_digest IS NULL AND call_started_at IS NULL)"
)


def upgrade() -> None:
    op.drop_constraint(
        "ck_execution_action_call_evidence",
        "execution_action",
        schema="halpha",
        type_="check",
    )
    op.create_check_constraint(
        "ck_execution_action_call_evidence",
        "execution_action",
        _CALL_EVIDENCE_CHECK,
        schema="halpha",
    )


def downgrade() -> None:
    raise RuntimeError("DATABASE_DOWNGRADE_FORBIDDEN")
