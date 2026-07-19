"""Store one product build identity on fixed plans.

Revision ID: 20260720_0009
Revises: 20260720_0008
Create Date: 2026-07-20
"""

from __future__ import annotations

from alembic import op


revision = "20260720_0009"
down_revision = "20260720_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE halpha.trade_plan_version "
        "RENAME COLUMN build_digest TO product_build_id"
    )
    op.execute(
        "ALTER TABLE halpha.trade_plan_version "
        "RENAME CONSTRAINT ck_trade_plan_version_build_digest "
        "TO ck_trade_plan_version_product_build_id"
    )
    op.execute(
        "UPDATE halpha.trade_plan_version "
        "SET fixed_strategy_basis = "
        "(fixed_strategy_basis - 'build_digest' - 'evidence_digest' - 'evidence_scope') "
        "|| jsonb_build_object('product_build_id', product_build_id)"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE halpha.trade_plan_version "
        "SET fixed_strategy_basis = "
        "(fixed_strategy_basis - 'product_build_id') "
        "|| jsonb_build_object("
        "'build_digest', product_build_id, "
        "'evidence_digest', product_build_id, "
        "'evidence_scope', '{}'::jsonb)"
    )
    op.execute(
        "ALTER TABLE halpha.trade_plan_version "
        "RENAME CONSTRAINT ck_trade_plan_version_product_build_id "
        "TO ck_trade_plan_version_build_digest"
    )
    op.execute(
        "ALTER TABLE halpha.trade_plan_version "
        "RENAME COLUMN product_build_id TO build_digest"
    )
