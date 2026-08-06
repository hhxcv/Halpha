"""Persist immutable stage reviews over an explicit review range.

Revision ID: 20260728_0008
Revises: 20260727_0007
"""

from __future__ import annotations

import re

from alembic import op
from sqlalchemy.dialects import postgresql
import sqlalchemy as sa


revision = "20260728_0008"
down_revision = "20260727_0007"
branch_labels = None
depends_on = None


UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())
UTC_TS = sa.DateTime(timezone=True)
QUALIFICATION_DATABASE_PATTERN = re.compile(
    r"^halpha_workbench_fixture_[1-9][0-9]*$"
)


def _role_prefix() -> tuple[str, bool]:
    database_name = str(
        op.get_bind().execute(sa.text("SELECT current_database()")).scalar_one()
    )
    if database_name == "halpha_demo":
        return "halpha_demo", False
    if database_name in {
        "halpha_live_copy",
        "halpha_live_personal",
    }:
        return database_name, True
    if QUALIFICATION_DATABASE_PATTERN.fullmatch(database_name):
        return "halpha_demo", False
    raise RuntimeError(f"UNSUPPORTED_HALPHA_DATABASE: {database_name}")


def upgrade() -> None:
    role_prefix, is_live = _role_prefix()
    op.create_table(
        "stage_review",
        sa.Column("stage_review_id", UUID, primary_key=True),
        sa.Column("environment_id", sa.String(96), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("request_digest", sa.CHAR(64), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("range_start", UTC_TS, nullable=False),
        sa.Column("range_end", UTC_TS, nullable=False),
        sa.Column("source_review_refs", JSONB, nullable=False),
        sa.Column("metrics_snapshot", JSONB, nullable=False),
        sa.Column("problem_analysis", sa.Text(), nullable=False),
        sa.Column("improvement_plan", sa.Text(), nullable=False),
        sa.Column("creator_kind", sa.String(16), nullable=False),
        sa.Column("content_digest", sa.CHAR(64), nullable=False),
        sa.Column("created_at", UTC_TS, nullable=False),
        sa.CheckConstraint(
            "range_start <= range_end",
            name="ck_stage_review_range",
        ),
        sa.CheckConstraint(
            "creator_kind IN ('HUMAN','AI')",
            name="ck_stage_review_creator",
        ),
        sa.CheckConstraint(
            "request_digest ~ '^[0-9a-f]{64}$'",
            name="ck_stage_review_request_digest",
        ),
        sa.CheckConstraint(
            "content_digest ~ '^[0-9a-f]{64}$'",
            name="ck_stage_review_content_digest",
        ),
        sa.UniqueConstraint(
            "environment_id",
            "stage_review_id",
            name="uq_stage_review_environment",
        ),
        sa.UniqueConstraint(
            "environment_id",
            "idempotency_key",
            name="uq_stage_review_idempotency",
        ),
        schema="halpha",
    )
    op.execute(
        """
        CREATE FUNCTION halpha.guard_stage_review_append_only()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'STAGE_REVIEW_APPEND_ONLY' USING ERRCODE = '23514';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_stage_review_append_only
        BEFORE UPDATE OR DELETE ON halpha.stage_review
        FOR EACH ROW
        EXECUTE FUNCTION halpha.guard_stage_review_append_only()
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION halpha.guard_stage_review_append_only() FROM PUBLIC"
    )
    read_roles = [
        f"{role_prefix}_app",
        f"{role_prefix}_backup",
        *([f"{role_prefix}_app_reader"] if is_live else []),
    ]
    for role in read_roles:
        op.execute(
            sa.text(
                f'GRANT SELECT ON TABLE halpha.stage_review TO "{role}"'
            )
        )
    op.execute(
        sa.text(
            f'GRANT INSERT ON TABLE halpha.stage_review TO "{role_prefix}_app"'
        )
    )


def downgrade() -> None:
    raise RuntimeError("DATABASE_DOWNGRADE_FORBIDDEN")
