"""Make each persisted order UUID32 unique inside an environment.

Revision ID: 20260717_0005
Revises: 20260717_0004
Create Date: 2026-07-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260717_0005"
down_revision = "20260717_0004"
branch_labels = None
depends_on = None

SCHEMA = "halpha"


def upgrade() -> None:
    op.create_index(
        "uq_execution_action_client_order_identity",
        "execution_action",
        ("environment_id", "client_order_id"),
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("client_order_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_execution_action_client_order_identity",
        table_name="execution_action",
        schema=SCHEMA,
    )
