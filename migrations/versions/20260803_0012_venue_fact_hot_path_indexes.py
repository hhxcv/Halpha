"""Index append-only venue facts for long-running account and action reads.

Revision ID: 20260803_0012
Revises: 20260802_0011
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260803_0012"
down_revision = "20260802_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_venue_fact_action_timeline",
        "venue_fact",
        (
            "environment_id",
            "action_ref",
            "cutoff",
            "received_at",
            "venue_fact_id",
        ),
        unique=False,
        schema="halpha",
        postgresql_where=sa.text("action_ref IS NOT NULL"),
    )
    op.create_index(
        "ix_venue_fact_account_state_latest",
        "venue_fact",
        (
            "environment_id",
            "account_ref",
            "cutoff",
            "received_at",
            "venue_fact_id",
        ),
        unique=False,
        schema="halpha",
        postgresql_where=sa.text(
            "kind = 'ACCOUNT_STATE' "
            "AND source_class = 'VENUE_QUERY' "
            "AND account_ref IS NOT NULL"
        ),
    )
    op.create_index(
        "ix_venue_fact_trade_identity_timeline",
        "venue_fact",
        (
            "environment_id",
            "kind",
            "source_object_id",
            "account_ref",
            "instrument_ref",
            "received_at",
            "venue_fact_id",
        ),
        unique=False,
        schema="halpha",
        postgresql_where=sa.text("kind IN ('FILL', 'COMMISSION')"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_venue_fact_trade_identity_timeline",
        table_name="venue_fact",
        schema="halpha",
    )
    op.drop_index(
        "ix_venue_fact_account_state_latest",
        table_name="venue_fact",
        schema="halpha",
    )
    op.drop_index(
        "ix_venue_fact_action_timeline",
        table_name="venue_fact",
        schema="halpha",
    )
