"""Harden decision-basis JSON and activation/version consistency.

Revision ID: 20260723_0012
Revises: 20260723_0011
Create Date: 2026-07-23
"""

from __future__ import annotations

from alembic import op


revision = "20260723_0012"
down_revision = "20260723_0011"
branch_labels = None
depends_on = None

SCHEMA = "halpha"


def upgrade() -> None:
    op.create_check_constraint(
        "ck_trade_plan_version_decision_basis_strict",
        "trade_plan_version",
        "COALESCE("
        "(fixed_decision_basis ? 'kind') "
        "AND (fixed_decision_basis ? 'decision_basis_ref') "
        "AND fixed_decision_basis->>'kind' IN "
        "('STRATEGY_SIGNAL', 'DIRECT_EXECUTION') "
        "AND fixed_decision_basis->>'decision_basis_ref' = decision_basis_ref "
        "AND ((fixed_decision_basis->>'kind' = 'DIRECT_EXECUTION') "
        "= (decision_basis_ref = 'DIRECT_EXECUTION@1')), "
        "FALSE)",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_trade_plan_version_direct_schedule_strict",
        "trade_plan_version",
        "COALESCE(((fixed_decision_basis->>'kind' = 'DIRECT_EXECUTION') "
        "= (order_schedule_spec IS NOT NULL)), FALSE)",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_plan_activation_direct_schedule_strict",
        "plan_activation",
        "COALESCE(((decision_basis_ref = 'DIRECT_EXECUTION@1') "
        "= (order_schedule_snapshot IS NOT NULL)), FALSE)",
        schema=SCHEMA,
    )
    op.create_unique_constraint(
        "uq_trade_plan_version_basis_identity",
        "trade_plan_version",
        ("environment_id", "plan_version_id", "decision_basis_ref"),
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_plan_activation_version_basis",
        "plan_activation",
        "trade_plan_version",
        ("environment_id", "plan_version_ref", "decision_basis_ref"),
        ("environment_id", "plan_version_id", "decision_basis_ref"),
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_plan_activation_version_basis",
        "plan_activation",
        schema=SCHEMA,
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_trade_plan_version_basis_identity",
        "trade_plan_version",
        schema=SCHEMA,
        type_="unique",
    )
    op.drop_constraint(
        "ck_plan_activation_direct_schedule_strict",
        "plan_activation",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_constraint(
        "ck_trade_plan_version_direct_schedule_strict",
        "trade_plan_version",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_constraint(
        "ck_trade_plan_version_decision_basis_strict",
        "trade_plan_version",
        schema=SCHEMA,
        type_="check",
    )
