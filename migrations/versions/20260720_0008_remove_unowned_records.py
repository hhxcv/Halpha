"""Remove record families no longer owned by the product.

Revision ID: 20260720_0008
Revises: 20260720_0007
Create Date: 2026-07-20
"""

from __future__ import annotations

from alembic import op


revision = "20260720_0008"
down_revision = "20260720_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS halpha.improvement_handoff CASCADE")
    op.execute("DROP TABLE IF EXISTS halpha.notification CASCADE")
    op.execute("DROP TABLE IF EXISTS halpha.task CASCADE")


def downgrade() -> None:
    raise RuntimeError("UNOWNED_RECORD_REMOVAL_IS_IRREVERSIBLE")
