"""Make the current stop set versionable down to an empty released set.

Revision ID: 20260717_0003
Revises: 20260717_0002
Create Date: 2026-07-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260717_0003"
down_revision = "20260717_0002"
branch_labels = None
depends_on = None

SCHEMA = "halpha"


def upgrade() -> None:
    op.drop_constraint(
        "ck_stop_state_categories",
        "stop_state_version",
        schema=SCHEMA,
        type_="check",
    )
    op.create_check_constraint(
        "ck_stop_state_categories",
        "stop_state_version",
        "stopped_categories <@ ARRAY['NEW_FUNDING','PROTECTION',"
        "'RISK_REDUCTION_OR_ORDER_MANAGEMENT','ALL_WRITES']::text[]",
        schema=SCHEMA,
    )
    op.create_index(
        "uq_stop_state_account_scope_version",
        "stop_state_version",
        ("environment_id", "account_ref", "version"),
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("activation_id IS NULL"),
    )
    op.create_index(
        "uq_stop_state_activation_scope_version",
        "stop_state_version",
        ("environment_id", "account_ref", "activation_id", "version"),
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("activation_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM halpha.stop_state_version WHERE cardinality(stopped_categories) = 0"
    )
    op.drop_index(
        "uq_stop_state_activation_scope_version",
        table_name="stop_state_version",
        schema=SCHEMA,
    )
    op.drop_index(
        "uq_stop_state_account_scope_version",
        table_name="stop_state_version",
        schema=SCHEMA,
    )
    op.drop_constraint(
        "ck_stop_state_categories",
        "stop_state_version",
        schema=SCHEMA,
        type_="check",
    )
    op.create_check_constraint(
        "ck_stop_state_categories",
        "stop_state_version",
        "cardinality(stopped_categories) > 0 AND "
        "stopped_categories <@ ARRAY['NEW_FUNDING','PROTECTION',"
        "'RISK_REDUCTION_OR_ORDER_MANAGEMENT','ALL_WRITES']::text[]",
        schema=SCHEMA,
    )
