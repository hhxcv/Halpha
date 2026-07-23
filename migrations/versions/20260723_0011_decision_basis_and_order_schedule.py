"""Name decision basis explicitly and persist order-schedule JSON snapshots.

Revision ID: 20260723_0011
Revises: 20260721_0010
Create Date: 2026-07-23
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260723_0011"
down_revision = "20260721_0010"
branch_labels = None
depends_on = None

SCHEMA = "halpha"
JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.execute(
        "ALTER TABLE halpha.trade_plan_version "
        "RENAME COLUMN strategy_definition_ref TO decision_basis_ref"
    )
    op.execute(
        "ALTER TABLE halpha.trade_plan_version "
        "RENAME COLUMN fixed_strategy_basis TO fixed_decision_basis"
    )
    op.execute(
        "UPDATE halpha.trade_plan_version SET fixed_decision_basis = "
        "fixed_decision_basis || jsonb_build_object("
        "'kind', 'STRATEGY_SIGNAL', "
        "'decision_basis_ref', decision_basis_ref)"
    )
    op.execute(
        "ALTER TABLE halpha.plan_activation "
        "RENAME COLUMN strategy_id TO decision_basis_ref"
    )
    op.execute(
        "UPDATE halpha.plan_activation AS activation "
        "SET decision_basis_ref = version.decision_basis_ref "
        "FROM halpha.trade_plan_version AS version "
        "WHERE activation.environment_id = version.environment_id "
        "AND activation.plan_version_ref = version.plan_version_id"
    )

    op.add_column(
        "trade_plan_version",
        sa.Column("order_schedule_spec", JSONB),
        schema=SCHEMA,
    )
    op.add_column(
        "trade_plan_version",
        sa.Column("order_schedule_spec_digest", sa.CHAR(64)),
        schema=SCHEMA,
    )
    op.add_column(
        "plan_activation",
        sa.Column("order_schedule_snapshot", JSONB),
        schema=SCHEMA,
    )
    op.add_column(
        "plan_activation",
        sa.Column("order_schedule_snapshot_digest", sa.CHAR(64)),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_trade_plan_version_decision_basis_ref",
        "trade_plan_version",
        "length(decision_basis_ref) > 0",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_trade_plan_version_decision_basis_consistency",
        "trade_plan_version",
        "fixed_decision_basis->>'kind' IN ('STRATEGY_SIGNAL', 'DIRECT_EXECUTION') "
        "AND fixed_decision_basis->>'decision_basis_ref' = decision_basis_ref",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_trade_plan_version_direct_schedule",
        "trade_plan_version",
        "(fixed_decision_basis->>'kind' = 'DIRECT_EXECUTION') "
        "= (order_schedule_spec IS NOT NULL)",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_trade_plan_version_schedule_pair",
        "trade_plan_version",
        "(order_schedule_spec IS NULL) = (order_schedule_spec_digest IS NULL)",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_trade_plan_version_schedule_digest",
        "trade_plan_version",
        "order_schedule_spec_digest IS NULL OR "
        "order_schedule_spec_digest ~ '^[0-9a-f]{64}$'",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_plan_activation_decision_basis_ref",
        "plan_activation",
        "length(decision_basis_ref) > 0",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_plan_activation_direct_schedule",
        "plan_activation",
        "(decision_basis_ref = 'DIRECT_EXECUTION@1') "
        "= (order_schedule_snapshot IS NOT NULL)",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_plan_activation_schedule_pair",
        "plan_activation",
        "(order_schedule_snapshot IS NULL) = "
        "(order_schedule_snapshot_digest IS NULL)",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_plan_activation_schedule_digest",
        "plan_activation",
        "order_schedule_snapshot_digest IS NULL OR "
        "order_schedule_snapshot_digest ~ '^[0-9a-f]{64}$'",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM halpha.trade_plan_version WHERE "
        "fixed_decision_basis->>'kind' = 'DIRECT_EXECUTION' "
        "OR order_schedule_spec IS NOT NULL) "
        "OR EXISTS (SELECT 1 FROM halpha.plan_activation "
        "WHERE order_schedule_snapshot IS NOT NULL) "
        "OR EXISTS (SELECT 1 FROM halpha.trade_plan_draft "
        "WHERE content ? 'decision_basis' OR content ? 'order_schedule_spec') THEN "
        "RAISE EXCEPTION 'cannot downgrade decision basis or order schedule facts'; "
        "END IF; END $$"
    )
    op.drop_constraint(
        "ck_plan_activation_schedule_digest",
        "plan_activation",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_constraint(
        "ck_plan_activation_schedule_pair",
        "plan_activation",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_constraint(
        "ck_plan_activation_direct_schedule",
        "plan_activation",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_constraint(
        "ck_plan_activation_decision_basis_ref",
        "plan_activation",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_constraint(
        "ck_trade_plan_version_schedule_digest",
        "trade_plan_version",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_constraint(
        "ck_trade_plan_version_schedule_pair",
        "trade_plan_version",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_constraint(
        "ck_trade_plan_version_direct_schedule",
        "trade_plan_version",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_constraint(
        "ck_trade_plan_version_decision_basis_consistency",
        "trade_plan_version",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_constraint(
        "ck_trade_plan_version_decision_basis_ref",
        "trade_plan_version",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_column("plan_activation", "order_schedule_snapshot_digest", schema=SCHEMA)
    op.drop_column("plan_activation", "order_schedule_snapshot", schema=SCHEMA)
    op.drop_column("trade_plan_version", "order_schedule_spec_digest", schema=SCHEMA)
    op.drop_column("trade_plan_version", "order_schedule_spec", schema=SCHEMA)
    op.execute(
        "UPDATE halpha.plan_activation SET decision_basis_ref = "
        "split_part(decision_basis_ref, '@', 1)"
    )
    op.execute(
        "ALTER TABLE halpha.plan_activation "
        "RENAME COLUMN decision_basis_ref TO strategy_id"
    )
    op.execute(
        "UPDATE halpha.trade_plan_version SET fixed_decision_basis = "
        "fixed_decision_basis - 'kind' - 'decision_basis_ref'"
    )
    op.execute(
        "ALTER TABLE halpha.trade_plan_version "
        "RENAME COLUMN fixed_decision_basis TO fixed_strategy_basis"
    )
    op.execute(
        "ALTER TABLE halpha.trade_plan_version "
        "RENAME COLUMN decision_basis_ref TO strategy_definition_ref"
    )
