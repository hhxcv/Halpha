"""Allow same-direction activations to share one venue net position.

Revision ID: 20260726_0001
Revises: 20260724_0001
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260726_0001"
down_revision = "20260724_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index(
        "uq_plan_activation_open_scope",
        table_name="plan_activation",
        schema="halpha",
    )
    op.drop_index(
        "uq_plan_activation_live_open_account_scope",
        table_name="plan_activation",
        schema="halpha",
    )
    op.create_index(
        "ix_plan_activation_open_scope",
        "plan_activation",
        ("environment_id", "account_ref", "instrument_ref"),
        unique=False,
        schema="halpha",
        postgresql_where=sa.text("lifecycle <> 'COMPLETED'"),
    )
    op.create_index(
        "ix_plan_activation_live_open_account_scope",
        "plan_activation",
        ("environment_id", "account_ref"),
        unique=False,
        schema="halpha",
        postgresql_where=sa.text(
            "environment_kind = 'LIVE' AND lifecycle <> 'COMPLETED'"
        ),
    )
    op.drop_constraint(
        "ck_venue_fact_attribution",
        "venue_fact",
        schema="halpha",
        type_="check",
    )
    op.create_check_constraint(
        "ck_venue_fact_attribution",
        "venue_fact",
        "(attribution_class IS NULL AND activation_ref IS NULL AND action_ref IS NULL AND attribution_digest IS NULL) OR "
        "(attribution_class = 'HALPHA_EXECUTION' AND activation_ref IS NOT NULL AND action_ref IS NOT NULL AND attribution_digest IS NOT NULL AND handover_command_ref IS NULL) OR "
        "(attribution_class = 'HALPHA_ACTIVATION_ALLOCATION' AND activation_ref IS NOT NULL AND action_ref IS NULL AND attribution_digest IS NOT NULL AND handover_command_ref IS NULL) OR "
        "(attribution_class = 'USER_TAKEOVER' AND activation_ref IS NOT NULL AND action_ref IS NULL AND attribution_digest IS NOT NULL AND handover_command_ref IS NOT NULL)",
        schema="halpha",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_venue_fact_attribution",
        "venue_fact",
        schema="halpha",
        type_="check",
    )
    op.create_check_constraint(
        "ck_venue_fact_attribution",
        "venue_fact",
        "(attribution_class IS NULL AND activation_ref IS NULL AND action_ref IS NULL AND attribution_digest IS NULL) OR "
        "(attribution_class = 'HALPHA_EXECUTION' AND activation_ref IS NOT NULL AND action_ref IS NOT NULL AND attribution_digest IS NOT NULL AND handover_command_ref IS NULL) OR "
        "(attribution_class = 'USER_TAKEOVER' AND activation_ref IS NOT NULL AND action_ref IS NULL AND attribution_digest IS NOT NULL AND handover_command_ref IS NOT NULL)",
        schema="halpha",
    )
    op.drop_index(
        "ix_plan_activation_live_open_account_scope",
        table_name="plan_activation",
        schema="halpha",
    )
    op.drop_index(
        "ix_plan_activation_open_scope",
        table_name="plan_activation",
        schema="halpha",
    )
    op.create_index(
        "uq_plan_activation_open_scope",
        "plan_activation",
        ("environment_id", "account_ref", "instrument_ref"),
        unique=True,
        schema="halpha",
        postgresql_where=sa.text("lifecycle <> 'COMPLETED'"),
    )
    op.create_index(
        "uq_plan_activation_live_open_account_scope",
        "plan_activation",
        ("environment_id", "account_ref"),
        unique=True,
        schema="halpha",
        postgresql_where=sa.text(
            "environment_kind = 'LIVE' AND lifecycle <> 'COMPLETED'"
        ),
    )
