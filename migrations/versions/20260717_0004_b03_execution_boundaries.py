"""Enforce B03 EXE identity and append-only DAT boundaries.

Revision ID: 20260717_0004
Revises: 20260717_0003
Create Date: 2026-07-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260717_0004"
down_revision = "20260717_0003"
branch_labels = None
depends_on = None

SCHEMA = "halpha"


def _executor_role() -> str:
    database_name = op.get_bind().execute(sa.text("SELECT current_database()"), {}).scalar_one()
    if database_name not in {"halpha_demo", "halpha_live"}:
        raise RuntimeError("UNSUPPORTED_DATABASE_TARGET")
    return f"{database_name}_executor"


def upgrade() -> None:
    op.create_check_constraint(
        "ck_execution_action_order_identity",
        "execution_action",
        "(action_kind = 'CANCEL' AND client_order_id IS NULL AND cancel_target IS NOT NULL) OR "
        "(action_kind <> 'CANCEL' AND client_order_id ~ '^[0-9a-f]{32}$' AND cancel_target IS NULL)",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_execution_action_unknown_evidence",
        "execution_action",
        "(state = 'SUBMITTED_UNKNOWN' AND unknown_reason IS NOT NULL AND next_query_at IS NOT NULL) OR "
        "(state <> 'SUBMITTED_UNKNOWN' AND unknown_reason IS NULL AND next_query_at IS NULL)",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_execution_action_closure_evidence",
        "execution_action",
        "state <> 'RECONCILED' OR closure_evidence_digest IS NOT NULL",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_execution_action_time_order",
        "execution_action",
        "updated_at >= created_at AND "
        "(call_completed_at IS NULL OR (call_started_at IS NOT NULL AND call_completed_at >= call_started_at))",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_venue_fact_source_identity",
        "venue_fact",
        "source_object_id IS NOT NULL AND source_sequence IS NOT NULL",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_venue_fact_time_order",
        "venue_fact",
        "cutoff <= received_at",
        schema=SCHEMA,
    )

    op.execute(
        """
        CREATE FUNCTION halpha.guard_execution_action_identity_immutable()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          IF ROW(
            NEW.execution_action_id, NEW.environment_id, NEW.environment_kind,
            NEW.authority_class, NEW.execution_profile_ref, NEW.account_ref,
            NEW.activation_id, NEW.plan_event_ref, NEW.source_identity,
            NEW.action_kind, NEW.action_class, NEW.action_terms,
            NEW.action_terms_digest, NEW.client_order_id, NEW.cancel_target,
            NEW.created_at
          ) IS DISTINCT FROM ROW(
            OLD.execution_action_id, OLD.environment_id, OLD.environment_kind,
            OLD.authority_class, OLD.execution_profile_ref, OLD.account_ref,
            OLD.activation_id, OLD.plan_event_ref, OLD.source_identity,
            OLD.action_kind, OLD.action_class, OLD.action_terms,
            OLD.action_terms_digest, OLD.client_order_id, OLD.cancel_target,
            OLD.created_at
          ) THEN
            RAISE EXCEPTION 'EXECUTION_ACTION_IDENTITY_IMMUTABLE' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_execution_action_identity_immutable
        BEFORE UPDATE ON halpha.execution_action
        FOR EACH ROW EXECUTE FUNCTION halpha.guard_execution_action_identity_immutable()
        """
    )
    op.execute(
        """
        CREATE FUNCTION halpha.guard_venue_fact_append_only()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'VENUE_FACT_APPEND_ONLY' USING ERRCODE = '23514';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_venue_fact_append_only
        BEFORE UPDATE OR DELETE ON halpha.venue_fact
        FOR EACH ROW EXECUTE FUNCTION halpha.guard_venue_fact_append_only()
        """
    )
    executor = _executor_role()
    op.execute(
        sa.text(f'REVOKE UPDATE, DELETE ON TABLE halpha.venue_fact FROM "{executor}"')
    )


def downgrade() -> None:
    executor = _executor_role()
    op.execute(
        sa.text(f'GRANT UPDATE, DELETE ON TABLE halpha.venue_fact TO "{executor}"')
    )
    op.execute("DROP TRIGGER trg_venue_fact_append_only ON halpha.venue_fact")
    op.execute("DROP FUNCTION halpha.guard_venue_fact_append_only()")
    op.execute("DROP TRIGGER trg_execution_action_identity_immutable ON halpha.execution_action")
    op.execute("DROP FUNCTION halpha.guard_execution_action_identity_immutable()")
    op.drop_constraint(
        "ck_venue_fact_time_order", "venue_fact", schema=SCHEMA, type_="check"
    )
    op.drop_constraint(
        "ck_venue_fact_source_identity", "venue_fact", schema=SCHEMA, type_="check"
    )
    op.drop_constraint(
        "ck_execution_action_time_order",
        "execution_action",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_constraint(
        "ck_execution_action_closure_evidence",
        "execution_action",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_constraint(
        "ck_execution_action_unknown_evidence",
        "execution_action",
        schema=SCHEMA,
        type_="check",
    )
    op.drop_constraint(
        "ck_execution_action_order_identity",
        "execution_action",
        schema=SCHEMA,
        type_="check",
    )
