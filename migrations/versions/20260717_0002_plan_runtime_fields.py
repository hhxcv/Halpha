"""Add embedded plan runtime values.

Revision ID: 20260717_0002
Revises: 20260717_0001
Create Date: 2026-07-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260717_0002"
down_revision = "20260717_0001"
branch_labels = None
depends_on = None

SCHEMA = "halpha"
UTC_TS = sa.DateTime(timezone=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column(
        "trade_plan_version",
        sa.Column("fixed_strategy_basis", JSONB, nullable=True),
        schema=SCHEMA,
    )
    op.execute(
        "UPDATE halpha.trade_plan_version "
        "SET fixed_strategy_basis = jsonb_build_object("
        "'strategy_definition_ref', strategy_definition_ref, "
        "'build_digest', build_digest, "
        "'parameter_schema_version', parameter_schema_version, "
        "'parameters', parameters, "
        "'parameter_digest', parameter_digest) "
        "WHERE fixed_strategy_basis IS NULL"
    )
    op.alter_column(
        "trade_plan_version",
        "fixed_strategy_basis",
        nullable=False,
        schema=SCHEMA,
    )

    op.add_column(
        "plan_activation",
        sa.Column("framework_strategy_id", sa.String(160)),
        schema=SCHEMA,
    )
    op.execute(
        "UPDATE halpha.plan_activation SET framework_strategy_id = strategy_id "
        "WHERE framework_strategy_id IS NULL"
    )
    op.alter_column(
        "plan_activation",
        "framework_strategy_id",
        nullable=False,
        schema=SCHEMA,
    )
    op.add_column(
        "plan_activation",
        sa.Column("paused_at", UTC_TS),
        schema=SCHEMA,
    )
    op.add_column(
        "plan_activation",
        sa.Column("reconciliation_digest", sa.CHAR(64)),
        schema=SCHEMA,
    )
    op.add_column(
        "plan_activation",
        sa.Column("current_resume_command_ref", UUID),
        schema=SCHEMA,
    )
    op.add_column(
        "plan_activation",
        sa.Column(
            "entry_opportunity_consumed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        schema=SCHEMA,
    )
    op.drop_constraint(
        "ck_plan_activation_pause_reason",
        "plan_activation",
        schema=SCHEMA,
        type_="check",
    )
    op.create_check_constraint(
        "ck_plan_activation_pause_state",
        "plan_activation",
        "(run_state = 'PAUSED' AND pause_reason = 'WRITER_CONTINUITY_LOST' AND paused_at IS NOT NULL) "
        "OR (run_state = 'ACTIVE' AND pause_reason IS NULL AND paused_at IS NULL)",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_plan_activation_reconciliation_digest",
        "plan_activation",
        "reconciliation_digest IS NULL OR reconciliation_digest ~ '^[0-9a-f]{64}$'",
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_plan_activation_resume_command",
        "plan_activation",
        "command",
        ("environment_id", "current_resume_command_ref"),
        ("environment_id", "command_id"),
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_plan_activation_resume_command",
        "plan_activation",
        schema=SCHEMA,
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_plan_activation_reconciliation_digest",
        "plan_activation",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_constraint(
        "ck_plan_activation_pause_state",
        "plan_activation",
        schema=SCHEMA,
        type_="check",
    )
    op.create_check_constraint(
        "ck_plan_activation_pause_reason",
        "plan_activation",
        "(run_state = 'PAUSED' AND pause_reason IS NOT NULL) "
        "OR (run_state = 'ACTIVE' AND pause_reason IS NULL)",
        schema=SCHEMA,
    )
    op.drop_column("plan_activation", "entry_opportunity_consumed", schema=SCHEMA)
    op.drop_column("plan_activation", "current_resume_command_ref", schema=SCHEMA)
    op.drop_column("plan_activation", "reconciliation_digest", schema=SCHEMA)
    op.drop_column("plan_activation", "paused_at", schema=SCHEMA)
    op.drop_column("plan_activation", "framework_strategy_id", schema=SCHEMA)
    op.drop_column("trade_plan_version", "fixed_strategy_basis", schema=SCHEMA)
