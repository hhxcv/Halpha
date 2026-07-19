"""Remove the superseded capital authorization and allocation model.

Revision ID: 20260720_0007
Revises: 20260718_0006
Create Date: 2026-07-20
"""

from __future__ import annotations

from alembic import op


revision = "20260720_0007"
down_revision = "20260718_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE halpha.stop_state_version "
        "SET stopped_categories = array_replace("
        "array_replace(stopped_categories, 'NEW_FUNDING', 'NEW_RISK'), "
        "'ALL_WRITES', 'ALL_EXCHANGE_CHANGES')"
    )
    op.execute(
        "ALTER TABLE halpha.stop_state_version "
        "DROP CONSTRAINT IF EXISTS ck_stop_state_categories"
    )
    op.execute(
        "ALTER TABLE halpha.stop_state_version ADD CONSTRAINT ck_stop_state_categories "
        "CHECK (stopped_categories <@ ARRAY['NEW_RISK','PROTECTION',"
        "'RISK_REDUCTION_OR_ORDER_MANAGEMENT','ALL_EXCHANGE_CHANGES']::text[])"
    )
    op.execute(
        "ALTER TABLE halpha.stop_state_version "
        "DROP COLUMN IF EXISTS authorization_version_ref CASCADE"
    )
    op.execute(
        "ALTER TABLE halpha.plan_activation "
        "DROP COLUMN IF EXISTS authorization_version_ref CASCADE, "
        "DROP COLUMN IF EXISTS allocation_ref CASCADE"
    )
    op.execute("DROP TABLE IF EXISTS halpha.plan_allocation CASCADE")
    op.execute("DROP TABLE IF EXISTS halpha.machine_authorization_version CASCADE")
    op.execute("DROP TABLE IF EXISTS halpha.account_capital_limit_version CASCADE")


def downgrade() -> None:
    raise RuntimeError("CAPITAL_MODEL_SIMPLIFICATION_IS_IRREVERSIBLE")
