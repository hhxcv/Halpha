"""Authorize runtime schema checks and transactional receipt completion.

Revision ID: 20260731_0010
Revises: 20260729_0009
"""

from __future__ import annotations

import re

from alembic import op
import sqlalchemy as sa


revision = "20260731_0010"
down_revision = "20260729_0009"
branch_labels = None
depends_on = None

QUALIFICATION_DATABASE_PATTERN = re.compile(
    r"^halpha_workbench_fixture_[1-9][0-9]*$"
)


def _role_prefix() -> tuple[str, bool]:
    database_name = op.get_bind().execute(
        sa.text("SELECT current_database()")
    ).scalar_one()
    if database_name == "halpha_demo":
        return "halpha_demo", False
    if database_name in {
        "halpha_live",
        "halpha_live_copy",
        "halpha_live_personal",
    }:
        return str(database_name), True
    if QUALIFICATION_DATABASE_PATTERN.fullmatch(str(database_name)):
        return "halpha_demo", False
    raise RuntimeError(f"UNSUPPORTED_HALPHA_DATABASE name={database_name}")


def upgrade() -> None:
    role_prefix, is_live = _role_prefix()
    runtime_roles = [
        f"{role_prefix}_app",
        f"{role_prefix}_executor",
    ]
    if is_live:
        runtime_roles.append(f"{role_prefix}_app_reader")
    for role in runtime_roles:
        op.execute(sa.text(f'GRANT USAGE ON SCHEMA halpha_meta TO "{role}"'))
        op.execute(
            sa.text(
                "GRANT SELECT ON TABLE halpha_meta.alembic_version "
                f'TO "{role}"'
            )
        )
    op.execute(
        sa.text(
            "GRANT UPDATE ON TABLE halpha.receipt "
            f'TO "{role_prefix}_executor"'
        )
    )


def downgrade() -> None:
    raise RuntimeError("DATABASE_DOWNGRADE_FORBIDDEN")
