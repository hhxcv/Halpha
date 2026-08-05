"""Bind external-position disposition plans to immutable account snapshots.

Revision ID: 20260802_0011
Revises: 20260731_0010
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "20260802_0011"
down_revision = "20260731_0010"
branch_labels = None
depends_on = None


def _digest(name: str) -> sa.Column[str]:
    return sa.Column(name, sa.String(64))


def _alignment_shape(column: str) -> str:
    return (
        f"{column} IS NULL OR COALESCE("
        f"{column}->>'schema_version' = 'HALPHA_POSITION_ALIGNMENT_V1' "
        f"AND {column}->>'operation' IN ('REDUCE', 'CLOSE') "
        f"AND {column} ? 'snapshot_ref' "
        f"AND {column} ? 'fact_cutoff' "
        f"AND {column} ? 'baseline_quantity' "
        f"AND {column} ? 'requested_reduction_quantity' "
        f"AND {column} ? 'target_quantity_after', FALSE)"
    )


def upgrade() -> None:
    op.add_column(
        "trade_plan_version",
        sa.Column("position_alignment", JSONB),
        schema="halpha",
    )
    op.add_column(
        "trade_plan_version",
        _digest("position_alignment_digest"),
        schema="halpha",
    )
    op.add_column(
        "plan_activation",
        sa.Column("position_alignment", JSONB),
        schema="halpha",
    )
    op.add_column(
        "plan_activation",
        _digest("position_alignment_digest"),
        schema="halpha",
    )

    op.drop_constraint(
        "ck_trade_plan_version_direct_schedule",
        "trade_plan_version",
        schema="halpha",
        type_="check",
    )
    op.drop_constraint(
        "ck_trade_plan_version_direct_schedule_strict",
        "trade_plan_version",
        schema="halpha",
        type_="check",
    )
    op.create_check_constraint(
        "ck_trade_plan_version_direct_schedule",
        "trade_plan_version",
        "(fixed_decision_basis->>'kind' = 'DIRECT_EXECUTION') = "
        "((order_schedule_spec IS NOT NULL) <> (position_alignment IS NOT NULL))",
        schema="halpha",
    )
    op.create_check_constraint(
        "ck_trade_plan_version_direct_schedule_strict",
        "trade_plan_version",
        "COALESCE((fixed_decision_basis->>'kind' = 'DIRECT_EXECUTION') = "
        "((order_schedule_spec IS NOT NULL) <> (position_alignment IS NOT NULL)), FALSE)",
        schema="halpha",
    )
    op.create_check_constraint(
        "ck_trade_plan_version_alignment_pair",
        "trade_plan_version",
        "(position_alignment IS NULL) = (position_alignment_digest IS NULL)",
        schema="halpha",
    )
    op.create_check_constraint(
        "ck_trade_plan_version_alignment_digest",
        "trade_plan_version",
        "position_alignment_digest IS NULL OR "
        "position_alignment_digest ~ '^[0-9a-f]{64}$'",
        schema="halpha",
    )
    op.create_check_constraint(
        "ck_trade_plan_version_alignment_shape",
        "trade_plan_version",
        _alignment_shape("position_alignment"),
        schema="halpha",
    )

    op.drop_constraint(
        "ck_plan_activation_direct_schedule",
        "plan_activation",
        schema="halpha",
        type_="check",
    )
    op.drop_constraint(
        "ck_plan_activation_direct_schedule_strict",
        "plan_activation",
        schema="halpha",
        type_="check",
    )
    op.create_check_constraint(
        "ck_plan_activation_direct_schedule",
        "plan_activation",
        "(decision_basis_ref = 'DIRECT_EXECUTION@1') = "
        "((order_schedule_snapshot IS NOT NULL) <> (position_alignment IS NOT NULL))",
        schema="halpha",
    )
    op.create_check_constraint(
        "ck_plan_activation_direct_schedule_strict",
        "plan_activation",
        "COALESCE((decision_basis_ref = 'DIRECT_EXECUTION@1') = "
        "((order_schedule_snapshot IS NOT NULL) <> (position_alignment IS NOT NULL)), FALSE)",
        schema="halpha",
    )
    op.create_check_constraint(
        "ck_plan_activation_alignment_pair",
        "plan_activation",
        "(position_alignment IS NULL) = (position_alignment_digest IS NULL)",
        schema="halpha",
    )
    op.create_check_constraint(
        "ck_plan_activation_alignment_digest",
        "plan_activation",
        "position_alignment_digest IS NULL OR "
        "position_alignment_digest ~ '^[0-9a-f]{64}$'",
        schema="halpha",
    )
    op.create_check_constraint(
        "ck_plan_activation_alignment_shape",
        "plan_activation",
        _alignment_shape("position_alignment"),
        schema="halpha",
    )


def downgrade() -> None:
    for name in (
        "ck_plan_activation_alignment_shape",
        "ck_plan_activation_alignment_digest",
        "ck_plan_activation_alignment_pair",
        "ck_plan_activation_direct_schedule_strict",
        "ck_plan_activation_direct_schedule",
    ):
        op.drop_constraint(
            name,
            "plan_activation",
            schema="halpha",
            type_="check",
        )
    op.create_check_constraint(
        "ck_plan_activation_direct_schedule",
        "plan_activation",
        "(decision_basis_ref = 'DIRECT_EXECUTION@1') = "
        "(order_schedule_snapshot IS NOT NULL)",
        schema="halpha",
    )
    op.create_check_constraint(
        "ck_plan_activation_direct_schedule_strict",
        "plan_activation",
        "COALESCE(((decision_basis_ref = 'DIRECT_EXECUTION@1') = "
        "(order_schedule_snapshot IS NOT NULL)), FALSE)",
        schema="halpha",
    )
    op.drop_column("plan_activation", "position_alignment_digest", schema="halpha")
    op.drop_column("plan_activation", "position_alignment", schema="halpha")

    for name in (
        "ck_trade_plan_version_alignment_shape",
        "ck_trade_plan_version_alignment_digest",
        "ck_trade_plan_version_alignment_pair",
        "ck_trade_plan_version_direct_schedule_strict",
        "ck_trade_plan_version_direct_schedule",
    ):
        op.drop_constraint(
            name,
            "trade_plan_version",
            schema="halpha",
            type_="check",
        )
    op.create_check_constraint(
        "ck_trade_plan_version_direct_schedule",
        "trade_plan_version",
        "(fixed_decision_basis->>'kind' = 'DIRECT_EXECUTION') = "
        "(order_schedule_spec IS NOT NULL)",
        schema="halpha",
    )
    op.create_check_constraint(
        "ck_trade_plan_version_direct_schedule_strict",
        "trade_plan_version",
        "COALESCE(((fixed_decision_basis->>'kind' = 'DIRECT_EXECUTION') = "
        "(order_schedule_spec IS NOT NULL)), FALSE)",
        schema="halpha",
    )
    op.drop_column(
        "trade_plan_version",
        "position_alignment_digest",
        schema="halpha",
    )
    op.drop_column("trade_plan_version", "position_alignment", schema="halpha")
