"""Create the accepted P0 sixteen-record-family schema.

Revision ID: 20260717_0001
Revises: None
Create Date: 2026-07-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260717_0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = "halpha"
PRODUCT_TABLES = (
    "trade_plan_draft",
    "trade_plan_version",
    "plan_activation",
    "plan_event",
    "venue_fact",
    "account_capital_limit_version",
    "machine_authorization_version",
    "plan_allocation",
    "stop_state_version",
    "execution_action",
    "review",
    "improvement_handoff",
    "task",
    "command",
    "receipt",
    "notification",
)
DROP_ORDER = (
    "notification",
    "receipt",
    "command",
    "task",
    "improvement_handoff",
    "review",
    "venue_fact",
    "execution_action",
    "stop_state_version",
    "plan_event",
    "plan_allocation",
    "plan_activation",
    "machine_authorization_version",
    "account_capital_limit_version",
    "trade_plan_version",
    "trade_plan_draft",
)

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())
MONEY = sa.Numeric(38, 18)
UTC_TS = sa.DateTime(timezone=True)
AUTHORITY_PAIR = (
    "(environment_kind = 'DEMO' AND authority_class = 'DEMO_VALIDATION') OR "
    "(environment_kind = 'LIVE' AND authority_class = 'LIVE_REAL_CAPITAL')"
)


def _digest(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.CHAR(64), nullable=nullable)


def _digest_check(column: str, constraint: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(
        f"{column} ~ '^[0-9a-f]{{64}}$'",
        name=constraint,
    )


def _environment() -> sa.Column:
    return sa.Column("environment_id", sa.String(96), nullable=False)


def _role_prefix() -> tuple[str, str]:
    database = op.get_bind().execute(sa.text("SELECT current_database()"))
    database_name = database.scalar_one()
    if database_name == "halpha_demo":
        return "halpha_demo", "DEMO"
    if database_name == "halpha_live":
        return "halpha_live", "LIVE"
    raise RuntimeError(f"UNSUPPORTED_HALPHA_DATABASE name={database_name}")


def upgrade() -> None:
    role_prefix, database_environment_kind = _role_prefix()
    op.execute(sa.text("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
    op.execute(sa.text("CREATE SCHEMA IF NOT EXISTS halpha AUTHORIZATION CURRENT_USER"))

    op.create_table(
        "trade_plan_draft",
        sa.Column("plan_id", UUID, primary_key=True),
        _environment(),
        sa.Column("draft_version", sa.BigInteger(), nullable=False),
        _digest("content_digest"),
        sa.Column("content", JSONB, nullable=False),
        sa.Column("updated_at", UTC_TS, nullable=False),
        sa.CheckConstraint("draft_version > 0", name="ck_trade_plan_draft_version"),
        _digest_check("content_digest", "ck_trade_plan_draft_digest"),
        sa.UniqueConstraint("environment_id", "plan_id", name="uq_trade_plan_draft_environment"),
        schema=SCHEMA,
    )
    op.create_table(
        "trade_plan_version",
        sa.Column("plan_version_id", UUID, primary_key=True),
        _environment(),
        sa.Column("plan_id", UUID, nullable=False),
        sa.Column("fixed_at", UTC_TS, nullable=False),
        sa.Column("strategy_definition_ref", sa.String(160), nullable=False),
        _digest("build_digest"),
        sa.Column("parameter_schema_version", sa.String(64), nullable=False),
        sa.Column("parameters", JSONB, nullable=False),
        _digest("parameter_digest"),
        sa.Column("account_ref", sa.String(160), nullable=False),
        sa.Column("venue_ref", sa.String(96), nullable=False),
        sa.Column("instrument_ref", sa.String(96), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("max_margin", MONEY, nullable=False),
        sa.Column("max_notional", MONEY, nullable=False),
        sa.Column("max_allowed_loss", MONEY, nullable=False),
        sa.Column("terms", JSONB, nullable=False),
        _digest("content_digest"),
        sa.ForeignKeyConstraint(
            ("environment_id", "plan_id"),
            ("halpha.trade_plan_draft.environment_id", "halpha.trade_plan_draft.plan_id"),
            name="fk_trade_plan_version_draft",
        ),
        sa.CheckConstraint("direction IN ('LONG', 'SHORT')", name="ck_trade_plan_version_direction"),
        sa.CheckConstraint(
            "max_margin >= 0 AND max_notional >= 0 AND max_allowed_loss >= 0",
            name="ck_trade_plan_version_limits",
        ),
        _digest_check("build_digest", "ck_trade_plan_version_build_digest"),
        _digest_check("parameter_digest", "ck_trade_plan_version_parameter_digest"),
        _digest_check("content_digest", "ck_trade_plan_version_content_digest"),
        sa.UniqueConstraint(
            "environment_id", "plan_version_id", name="uq_trade_plan_version_environment"
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "account_capital_limit_version",
        sa.Column("capital_limit_version_id", UUID, primary_key=True),
        _environment(),
        sa.Column("environment_kind", sa.String(8), nullable=False),
        sa.Column("authority_class", sa.String(32), nullable=False),
        sa.Column("account_ref", sa.String(160), nullable=False),
        sa.Column("quote_asset", sa.String(24), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("effective_at", UTC_TS, nullable=False),
        sa.Column("max_margin", MONEY, nullable=False),
        sa.Column("max_notional", MONEY, nullable=False),
        sa.Column("max_allowed_loss", MONEY, nullable=False),
        sa.Column("max_action_notional", MONEY, nullable=False),
        sa.Column("scope", JSONB, nullable=False),
        _digest("content_digest"),
        sa.CheckConstraint(AUTHORITY_PAIR, name="ck_capital_limit_authority_pair"),
        sa.CheckConstraint(
            "max_margin >= 0 AND max_notional >= 0 AND max_allowed_loss >= 0 AND max_action_notional >= 0",
            name="ck_capital_limit_values",
        ),
        sa.CheckConstraint("version > 0", name="ck_capital_limit_version"),
        _digest_check("content_digest", "ck_capital_limit_digest"),
        sa.UniqueConstraint(
            "environment_id",
            "authority_class",
            "capital_limit_version_id",
            name="uq_capital_limit_environment_authority",
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "machine_authorization_version",
        sa.Column("authorization_version_id", UUID, primary_key=True),
        _environment(),
        sa.Column("environment_kind", sa.String(8), nullable=False),
        sa.Column("authority_class", sa.String(32), nullable=False),
        sa.Column("activation_id", UUID, nullable=False),
        sa.Column("plan_version_ref", UUID, nullable=False),
        sa.Column("account_ref", sa.String(160), nullable=False),
        sa.Column("instrument_ref", sa.String(96), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("valid_from", UTC_TS, nullable=False),
        sa.Column("valid_until", UTC_TS, nullable=False),
        sa.Column("allowed_actions", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("terms", JSONB, nullable=False),
        _digest("content_digest"),
        sa.ForeignKeyConstraint(
            ("environment_id", "plan_version_ref"),
            ("halpha.trade_plan_version.environment_id", "halpha.trade_plan_version.plan_version_id"),
            name="fk_machine_authorization_plan_version",
        ),
        sa.CheckConstraint(AUTHORITY_PAIR, name="ck_machine_authorization_authority_pair"),
        sa.CheckConstraint("direction IN ('LONG', 'SHORT')", name="ck_machine_authorization_direction"),
        sa.CheckConstraint("version > 0", name="ck_machine_authorization_version"),
        sa.CheckConstraint("valid_until > valid_from", name="ck_machine_authorization_window"),
        _digest_check("content_digest", "ck_machine_authorization_digest"),
        sa.UniqueConstraint(
            "environment_id",
            "authority_class",
            "authorization_version_id",
            name="uq_machine_authorization_environment_authority",
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "plan_activation",
        sa.Column("activation_id", UUID, primary_key=True),
        _environment(),
        sa.Column("environment_kind", sa.String(8), nullable=False),
        sa.Column("authority_class", sa.String(32), nullable=False),
        sa.Column("plan_version_ref", UUID, nullable=False),
        sa.Column("authorization_version_ref", UUID, nullable=False),
        sa.Column("allocation_ref", UUID, nullable=False),
        sa.Column("account_ref", sa.String(160), nullable=False),
        sa.Column("instrument_ref", sa.String(96), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("strategy_id", sa.String(160), nullable=False),
        sa.Column("target_exposure", MONEY, nullable=False),
        sa.Column("lifecycle", sa.String(24), nullable=False),
        sa.Column("run_state", sa.String(16), nullable=False),
        sa.Column("pause_reason", sa.String(64)),
        sa.Column("has_entry_fill", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("responsibility_owner", sa.String(32), nullable=False),
        sa.Column("state_version", sa.BigInteger(), nullable=False),
        sa.Column("rule_state", JSONB, nullable=False),
        _digest("pending_action_digest", nullable=True),
        sa.Column("protection_state", sa.String(16), nullable=False),
        sa.Column("takeover_scope", JSONB),
        sa.Column("latest_venue_cutoff", UTC_TS),
        _digest("closure_digest", nullable=True),
        sa.Column("result_ref", sa.String(160)),
        sa.Column("created_at", UTC_TS, nullable=False),
        sa.Column("updated_at", UTC_TS, nullable=False),
        sa.ForeignKeyConstraint(
            ("environment_id", "plan_version_ref"),
            ("halpha.trade_plan_version.environment_id", "halpha.trade_plan_version.plan_version_id"),
            name="fk_plan_activation_plan_version",
        ),
        sa.ForeignKeyConstraint(
            ("environment_id", "authority_class", "authorization_version_ref"),
            (
                "halpha.machine_authorization_version.environment_id",
                "halpha.machine_authorization_version.authority_class",
                "halpha.machine_authorization_version.authorization_version_id",
            ),
            name="fk_plan_activation_authorization",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.CheckConstraint(AUTHORITY_PAIR, name="ck_plan_activation_authority_pair"),
        sa.CheckConstraint("direction IN ('LONG', 'SHORT')", name="ck_plan_activation_direction"),
        sa.CheckConstraint("target_exposure >= 0", name="ck_plan_activation_target_exposure"),
        sa.CheckConstraint(
            "lifecycle IN ('RUNNING','EXITING','USER_TAKEOVER','COMPLETED','UNKNOWN')",
            name="ck_plan_activation_lifecycle",
        ),
        sa.CheckConstraint("run_state IN ('ACTIVE','PAUSED')", name="ck_plan_activation_run_state"),
        sa.CheckConstraint(
            "(run_state = 'PAUSED' AND pause_reason IS NOT NULL) OR (run_state = 'ACTIVE' AND pause_reason IS NULL)",
            name="ck_plan_activation_pause_reason",
        ),
        sa.CheckConstraint(
            "protection_state IN ('NONE','WORKING','UNKNOWN','GAP','CLOSED')",
            name="ck_plan_activation_protection_state",
        ),
        sa.CheckConstraint("state_version > 0", name="ck_plan_activation_state_version"),
        _digest_check("pending_action_digest", "ck_plan_activation_pending_digest"),
        _digest_check("closure_digest", "ck_plan_activation_closure_digest"),
        sa.UniqueConstraint(
            "environment_id", "activation_id", name="uq_plan_activation_environment"
        ),
        sa.UniqueConstraint(
            "environment_id",
            "authority_class",
            "activation_id",
            name="uq_plan_activation_environment_authority",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "uq_plan_activation_open_scope",
        "plan_activation",
        ("environment_id", "account_ref", "instrument_ref"),
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("lifecycle <> 'COMPLETED'"),
    )
    op.create_table(
        "plan_event",
        sa.Column("plan_event_id", UUID, primary_key=True),
        _environment(),
        sa.Column("activation_id", UUID, nullable=False),
        sa.Column("rule_id", sa.String(160), nullable=False),
        sa.Column("source_identity", sa.String(384), nullable=False),
        sa.Column("source_cutoff", UTC_TS, nullable=False),
        _digest("input_digest"),
        sa.Column("reason_code", sa.String(96), nullable=False),
        sa.Column("condition_judgement", JSONB),
        sa.Column("proposed_action", JSONB),
        sa.Column("no_action_reason", sa.String(160)),
        sa.Column("capital_decision", JSONB, nullable=False),
        _digest("capital_decision_digest"),
        sa.Column("created_at", UTC_TS, nullable=False),
        _digest("content_digest"),
        sa.ForeignKeyConstraint(
            ("environment_id", "activation_id"),
            ("halpha.plan_activation.environment_id", "halpha.plan_activation.activation_id"),
            name="fk_plan_event_activation",
        ),
        sa.CheckConstraint(
            "(proposed_action IS NOT NULL) <> (no_action_reason IS NOT NULL)",
            name="ck_plan_event_action_or_no_action",
        ),
        _digest_check("input_digest", "ck_plan_event_input_digest"),
        _digest_check("capital_decision_digest", "ck_plan_event_capital_digest"),
        _digest_check("content_digest", "ck_plan_event_content_digest"),
        sa.UniqueConstraint(
            "environment_id", "plan_event_id", name="uq_plan_event_environment"
        ),
        sa.UniqueConstraint(
            "environment_id",
            "activation_id",
            "source_identity",
            name="uq_plan_event_source_identity",
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "plan_allocation",
        sa.Column("allocation_id", UUID, primary_key=True),
        _environment(),
        sa.Column("environment_kind", sa.String(8), nullable=False),
        sa.Column("authority_class", sa.String(32), nullable=False),
        sa.Column("activation_id", UUID, nullable=False),
        sa.Column("capital_limit_version_ref", UUID, nullable=False),
        sa.Column("quote_asset", sa.String(24), nullable=False),
        sa.Column("max_margin", MONEY, nullable=False),
        sa.Column("max_notional", MONEY, nullable=False),
        sa.Column("max_allowed_loss", MONEY, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("state_version", sa.BigInteger(), nullable=False),
        sa.Column("exposure_summary", JSONB, nullable=False),
        _digest("reservation_digest"),
        sa.Column("loss_fact_cutoff", UTC_TS),
        sa.Column("funding_query_cutoff", UTC_TS),
        sa.Column("max_loss_reached", sa.Boolean(), nullable=False, server_default=sa.false()),
        _digest("loss_latch_digest", nullable=True),
        _digest("closure_digest", nullable=True),
        sa.Column("released_at", UTC_TS),
        sa.ForeignKeyConstraint(
            ("environment_id", "authority_class", "capital_limit_version_ref"),
            (
                "halpha.account_capital_limit_version.environment_id",
                "halpha.account_capital_limit_version.authority_class",
                "halpha.account_capital_limit_version.capital_limit_version_id",
            ),
            name="fk_plan_allocation_capital_limit",
        ),
        sa.ForeignKeyConstraint(
            ("environment_id", "authority_class", "activation_id"),
            (
                "halpha.plan_activation.environment_id",
                "halpha.plan_activation.authority_class",
                "halpha.plan_activation.activation_id",
            ),
            name="fk_plan_allocation_activation",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.CheckConstraint(AUTHORITY_PAIR, name="ck_plan_allocation_authority_pair"),
        sa.CheckConstraint(
            "max_margin >= 0 AND max_notional >= 0 AND max_allowed_loss >= 0",
            name="ck_plan_allocation_values",
        ),
        sa.CheckConstraint(
            "status IN ('HELD','EXIT_ONLY','TAKEOVER_HELD','RELEASED')",
            name="ck_plan_allocation_status",
        ),
        sa.CheckConstraint("state_version > 0", name="ck_plan_allocation_state_version"),
        sa.CheckConstraint(
            "(max_loss_reached AND loss_latch_digest IS NOT NULL) OR NOT max_loss_reached",
            name="ck_plan_allocation_loss_latch",
        ),
        sa.CheckConstraint(
            "(status = 'RELEASED' AND released_at IS NOT NULL AND closure_digest IS NOT NULL) OR status <> 'RELEASED'",
            name="ck_plan_allocation_release",
        ),
        _digest_check("reservation_digest", "ck_plan_allocation_reservation_digest"),
        _digest_check("loss_latch_digest", "ck_plan_allocation_loss_digest"),
        _digest_check("closure_digest", "ck_plan_allocation_closure_digest"),
        sa.UniqueConstraint(
            "environment_id", "activation_id", name="uq_plan_allocation_activation"
        ),
        sa.UniqueConstraint(
            "environment_id",
            "authority_class",
            "allocation_id",
            name="uq_plan_allocation_environment_authority",
        ),
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_plan_activation_allocation",
        "plan_activation",
        "plan_allocation",
        ("environment_id", "authority_class", "allocation_ref"),
        ("environment_id", "authority_class", "allocation_id"),
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_foreign_key(
        "fk_machine_authorization_activation",
        "machine_authorization_version",
        "plan_activation",
        ("environment_id", "authority_class", "activation_id"),
        ("environment_id", "authority_class", "activation_id"),
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_table(
        "stop_state_version",
        sa.Column("stop_state_version_id", UUID, primary_key=True),
        _environment(),
        sa.Column("environment_kind", sa.String(8), nullable=False),
        sa.Column("authority_class", sa.String(32), nullable=False),
        sa.Column("account_ref", sa.String(160), nullable=False),
        sa.Column("activation_id", UUID),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("stopped_categories", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("reason", sa.String(160), nullable=False),
        sa.Column("source", sa.String(48), nullable=False),
        sa.Column("started_at", UTC_TS, nullable=False),
        sa.Column("authorization_version_ref", UUID),
        _digest("loss_latch_digest", nullable=True),
        sa.Column("release_rules", JSONB, nullable=False),
        _digest("content_digest"),
        sa.ForeignKeyConstraint(
            ("environment_id", "activation_id"),
            ("halpha.plan_activation.environment_id", "halpha.plan_activation.activation_id"),
            name="fk_stop_state_activation",
        ),
        sa.CheckConstraint(AUTHORITY_PAIR, name="ck_stop_state_authority_pair"),
        sa.CheckConstraint("version > 0", name="ck_stop_state_version"),
        sa.CheckConstraint(
            "cardinality(stopped_categories) > 0 AND stopped_categories <@ ARRAY['NEW_FUNDING','PROTECTION','RISK_REDUCTION_OR_ORDER_MANAGEMENT','ALL_WRITES']::text[]",
            name="ck_stop_state_categories",
        ),
        _digest_check("loss_latch_digest", "ck_stop_state_loss_digest"),
        _digest_check("content_digest", "ck_stop_state_content_digest"),
        sa.UniqueConstraint(
            "environment_id",
            "authority_class",
            "stop_state_version_id",
            name="uq_stop_state_environment_authority",
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "execution_action",
        sa.Column("execution_action_id", UUID, primary_key=True),
        _environment(),
        sa.Column("environment_kind", sa.String(8), nullable=False),
        sa.Column("authority_class", sa.String(32), nullable=False),
        sa.Column("execution_profile_ref", sa.String(64), nullable=False),
        sa.Column("account_ref", sa.String(160), nullable=False),
        sa.Column("activation_id", UUID, nullable=False),
        sa.Column("plan_event_ref", UUID, nullable=False),
        sa.Column("source_identity", sa.String(384), nullable=False),
        sa.Column("action_kind", sa.String(32), nullable=False),
        sa.Column("action_class", sa.String(24), nullable=False),
        sa.Column("action_terms", JSONB, nullable=False),
        _digest("action_terms_digest"),
        _digest("capital_decision_digest"),
        sa.Column("client_order_id", sa.CHAR(32)),
        sa.Column("cancel_target", JSONB),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("state_version", sa.BigInteger(), nullable=False),
        _digest("state_digest"),
        _digest("request_digest", nullable=True),
        sa.Column("call_started_at", UTC_TS),
        sa.Column("call_completed_at", UTC_TS),
        sa.Column("venue_order_refs", JSONB, nullable=False),
        sa.Column("venue_fact_refs", JSONB, nullable=False),
        sa.Column("unknown_reason", sa.String(160)),
        sa.Column("next_query_at", UTC_TS),
        _digest("protection_digest", nullable=True),
        _digest("closure_evidence_digest", nullable=True),
        sa.Column("created_at", UTC_TS, nullable=False),
        sa.Column("updated_at", UTC_TS, nullable=False),
        sa.ForeignKeyConstraint(
            ("environment_id", "activation_id"),
            ("halpha.plan_activation.environment_id", "halpha.plan_activation.activation_id"),
            name="fk_execution_action_activation",
        ),
        sa.ForeignKeyConstraint(
            ("environment_id", "plan_event_ref"),
            ("halpha.plan_event.environment_id", "halpha.plan_event.plan_event_id"),
            name="fk_execution_action_plan_event",
        ),
        sa.CheckConstraint(AUTHORITY_PAIR, name="ck_execution_action_authority_pair"),
        sa.CheckConstraint(
            "(environment_kind = 'DEMO' AND execution_profile_ref = 'BINANCE_DEMO') OR "
            "(environment_kind = 'LIVE' AND execution_profile_ref = 'BINANCE_LIVE_WRITE')",
            name="ck_execution_action_profile_pair",
        ),
        sa.CheckConstraint(
            "action_kind IN ('ENTRY','CANCEL','PROTECTION','TAKE_PROFIT','RISK_REDUCTION','EXIT')",
            name="ck_execution_action_kind",
        ),
        sa.CheckConstraint(
            "action_class IN ('RISK_INCREASING','RISK_NEUTRAL','RISK_REDUCING','AMBIGUOUS')",
            name="ck_execution_action_class",
        ),
        sa.CheckConstraint(
            "state IN ('READY','NOT_SUBMITTED','SUBMITTING','SUBMITTED_UNKNOWN','ACKNOWLEDGED','WORKING','PARTIALLY_FILLED','FILLED','CANCELLED','REJECTED','EXPIRED','RECONCILED','HANDED_OVER')",
            name="ck_execution_action_state",
        ),
        sa.CheckConstraint(
            "client_order_id IS NULL OR client_order_id ~ '^[0-9a-f]{32}$'",
            name="ck_execution_action_client_order_id",
        ),
        sa.CheckConstraint("state_version > 0", name="ck_execution_action_state_version"),
        sa.CheckConstraint(
            "(state IN ('SUBMITTING','SUBMITTED_UNKNOWN','ACKNOWLEDGED','WORKING','PARTIALLY_FILLED','FILLED','CANCELLED','REJECTED','EXPIRED','RECONCILED') AND request_digest IS NOT NULL AND call_started_at IS NOT NULL) OR "
            "state IN ('READY','NOT_SUBMITTED','HANDED_OVER')",
            name="ck_execution_action_call_evidence",
        ),
        _digest_check("action_terms_digest", "ck_execution_action_terms_digest"),
        _digest_check("capital_decision_digest", "ck_execution_action_capital_digest"),
        _digest_check("state_digest", "ck_execution_action_state_digest"),
        _digest_check("request_digest", "ck_execution_action_request_digest"),
        _digest_check("protection_digest", "ck_execution_action_protection_digest"),
        _digest_check("closure_evidence_digest", "ck_execution_action_closure_digest"),
        sa.UniqueConstraint(
            "environment_id", "execution_action_id", name="uq_execution_action_environment"
        ),
        sa.UniqueConstraint(
            "environment_id",
            "activation_id",
            "plan_event_ref",
            "source_identity",
            "action_kind",
            name="uq_execution_action_source",
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "venue_fact",
        sa.Column("venue_fact_id", UUID, primary_key=True),
        _environment(),
        sa.Column("venue_ref", sa.String(96), nullable=False),
        sa.Column("account_ref", sa.String(160)),
        sa.Column("instrument_ref", sa.String(96)),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("source_class", sa.String(32), nullable=False),
        sa.Column("source_object_id", sa.String(256)),
        sa.Column("source_sequence", sa.String(160)),
        sa.Column("source_time", UTC_TS),
        sa.Column("received_at", UTC_TS, nullable=False),
        sa.Column("cutoff", UTC_TS, nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        _digest("content_digest"),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("activation_ref", UUID),
        sa.Column("action_ref", UUID),
        _digest("attribution_digest", nullable=True),
        sa.Column("attribution_class", sa.String(32)),
        sa.Column("handover_command_ref", UUID),
        sa.Column("supersedes_ref", UUID),
        sa.Column("correction_reason", sa.String(160)),
        sa.Column("correction_evidence_refs", JSONB),
        sa.Column("correction_effective_time", UTC_TS),
        sa.Column("impact_scope", JSONB),
        sa.Column("affected_reference_refs", JSONB),
        sa.ForeignKeyConstraint(
            ("environment_id", "activation_ref"),
            ("halpha.plan_activation.environment_id", "halpha.plan_activation.activation_id"),
            name="fk_venue_fact_activation",
        ),
        sa.ForeignKeyConstraint(
            ("environment_id", "action_ref"),
            ("halpha.execution_action.environment_id", "halpha.execution_action.execution_action_id"),
            name="fk_venue_fact_execution_action",
        ),
        sa.ForeignKeyConstraint(
            ("environment_id", "supersedes_ref"),
            ("halpha.venue_fact.environment_id", "halpha.venue_fact.venue_fact_id"),
            name="fk_venue_fact_supersedes",
        ),
        sa.CheckConstraint(
            "kind IN ('CLOSED_BAR','MARK_PRICE','TOP_OF_BOOK','INSTRUMENT_RULES','ACCOUNT_STATE','ORDER_STATE','FILL','COMMISSION','FUNDING','POSITION_STATE')",
            name="ck_venue_fact_kind",
        ),
        sa.CheckConstraint(
            "source_class IN ('VENUE_QUERY','VENUE_STREAM','FRAMEWORK_DERIVED','EXTERNAL_UNCLAIMED')",
            name="ck_venue_fact_source_class",
        ),
        sa.CheckConstraint("schema_version > 0", name="ck_venue_fact_schema_version"),
        sa.CheckConstraint(
            "(attribution_class IS NULL AND activation_ref IS NULL AND action_ref IS NULL AND attribution_digest IS NULL) OR "
            "(attribution_class = 'HALPHA_EXECUTION' AND activation_ref IS NOT NULL AND action_ref IS NOT NULL AND attribution_digest IS NOT NULL AND handover_command_ref IS NULL) OR "
            "(attribution_class = 'USER_TAKEOVER' AND activation_ref IS NOT NULL AND action_ref IS NULL AND attribution_digest IS NOT NULL AND handover_command_ref IS NOT NULL)",
            name="ck_venue_fact_attribution",
        ),
        sa.CheckConstraint(
            "(supersedes_ref IS NULL AND correction_reason IS NULL AND correction_effective_time IS NULL) OR "
            "(supersedes_ref IS NOT NULL AND correction_reason IS NOT NULL AND correction_effective_time IS NOT NULL)",
            name="ck_venue_fact_correction",
        ),
        _digest_check("content_digest", "ck_venue_fact_content_digest"),
        _digest_check("attribution_digest", "ck_venue_fact_attribution_digest"),
        sa.UniqueConstraint(
            "environment_id", "venue_fact_id", name="uq_venue_fact_environment"
        ),
        sa.UniqueConstraint(
            "environment_id",
            "kind",
            "source_class",
            "source_object_id",
            "source_sequence",
            "content_digest",
            name="uq_venue_fact_source_content",
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "review",
        sa.Column("review_id", UUID, nullable=False),
        sa.Column("review_version", sa.BigInteger(), nullable=False),
        _environment(),
        sa.Column("activation_id", UUID, nullable=False),
        sa.Column("previous_version", sa.BigInteger()),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("primary_result", sa.String(24), nullable=False),
        sa.Column("fact_cutoff", UTC_TS, nullable=False),
        sa.Column("input_refs", JSONB, nullable=False),
        _digest("input_digest"),
        sa.Column("account_result", JSONB, nullable=False),
        sa.Column("open_responsibilities", JSONB, nullable=False),
        sa.Column("evaluations", JSONB, nullable=False),
        sa.Column("evidence_purpose", sa.String(48), nullable=False),
        _digest("content_digest"),
        sa.Column("created_at", UTC_TS, nullable=False),
        sa.PrimaryKeyConstraint("review_id", "review_version", name="pk_review"),
        sa.ForeignKeyConstraint(
            ("environment_id", "activation_id"),
            ("halpha.plan_activation.environment_id", "halpha.plan_activation.activation_id"),
            name="fk_review_activation",
        ),
        sa.CheckConstraint("review_version > 0", name="ck_review_version"),
        sa.CheckConstraint("status IN ('DRAFT','COMPLETE','SUPERSEDED')", name="ck_review_status"),
        sa.CheckConstraint(
            "primary_result IN ('NO_ACTION','COMPLETED','PARTIAL','RESULT_UNKNOWN','HANDED_OVER')",
            name="ck_review_primary_result",
        ),
        sa.CheckConstraint(
            "evidence_purpose IN ('SYSTEM_MECHANISM_EVIDENCE','LIVE_ACTIVATION_REVIEW')",
            name="ck_review_evidence_purpose",
        ),
        _digest_check("input_digest", "ck_review_input_digest"),
        _digest_check("content_digest", "ck_review_content_digest"),
        sa.UniqueConstraint("environment_id", "review_id", "review_version", name="uq_review_environment"),
        sa.UniqueConstraint("environment_id", "activation_id", "input_digest", name="uq_review_activation_input"),
        schema=SCHEMA,
    )
    op.create_table(
        "improvement_handoff",
        sa.Column("improvement_handoff_id", UUID, primary_key=True),
        _environment(),
        sa.Column("review_id", UUID, nullable=False),
        sa.Column("review_version", sa.BigInteger(), nullable=False),
        sa.Column("handoff_version", sa.BigInteger(), nullable=False),
        sa.Column("target_owner", sa.String(32), nullable=False),
        sa.Column("observable_problem", sa.Text(), nullable=False),
        sa.Column("evidence_refs", JSONB, nullable=False),
        sa.Column("impact_scope", JSONB, nullable=False),
        sa.Column("expected_change", sa.Text(), nullable=False),
        _digest("problem_digest"),
        _digest("content_digest"),
        sa.Column("created_at", UTC_TS, nullable=False),
        sa.ForeignKeyConstraint(
            ("environment_id", "review_id", "review_version"),
            ("halpha.review.environment_id", "halpha.review.review_id", "halpha.review.review_version"),
            name="fk_improvement_handoff_review",
        ),
        sa.CheckConstraint("handoff_version > 0", name="ck_improvement_handoff_version"),
        _digest_check("problem_digest", "ck_improvement_handoff_problem_digest"),
        _digest_check("content_digest", "ck_improvement_handoff_content_digest"),
        sa.UniqueConstraint(
            "environment_id",
            "review_id",
            "review_version",
            "target_owner",
            "problem_digest",
            name="uq_improvement_handoff_identity",
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "task",
        sa.Column("task_id", UUID, primary_key=True),
        _environment(),
        sa.Column("owner_scope", sa.String(96), nullable=False),
        sa.Column("responsibility_key", sa.String(384), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False),
        sa.Column("due_at", UTC_TS),
        sa.Column("source_kind", sa.String(64), nullable=False),
        sa.Column("source_ref", sa.String(160), nullable=False),
        sa.Column("source_version", sa.BigInteger(), nullable=False),
        _digest("source_digest"),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("state_version", sa.BigInteger(), nullable=False),
        sa.Column("resolution_ref", sa.String(160)),
        _digest("content_digest"),
        sa.Column("created_at", UTC_TS, nullable=False),
        sa.Column("updated_at", UTC_TS, nullable=False),
        sa.CheckConstraint("priority IN ('CRITICAL','HIGH','NORMAL','LOW')", name="ck_task_priority"),
        sa.CheckConstraint("state IN ('OPEN','ACKNOWLEDGED','RESOLVED')", name="ck_task_state"),
        sa.CheckConstraint("state_version > 0", name="ck_task_state_version"),
        _digest_check("source_digest", "ck_task_source_digest"),
        _digest_check("content_digest", "ck_task_content_digest"),
        sa.UniqueConstraint("environment_id", "task_id", name="uq_task_environment"),
        sa.UniqueConstraint("environment_id", "responsibility_key", name="uq_task_responsibility"),
        schema=SCHEMA,
    )
    op.create_table(
        "command",
        sa.Column("command_id", UUID, primary_key=True),
        _environment(),
        sa.Column("owner_scope", sa.String(96), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("target_kind", sa.String(64), nullable=False),
        sa.Column("target_ref", sa.String(160), nullable=False),
        sa.Column("expected_version", sa.BigInteger(), nullable=False),
        sa.Column("intent", sa.String(96), nullable=False),
        sa.Column("scope", JSONB, nullable=False),
        sa.Column("parameters", JSONB, nullable=False),
        sa.Column("submitted_at", UTC_TS, nullable=False),
        _digest("content_digest"),
        _digest_check("content_digest", "ck_command_content_digest"),
        sa.UniqueConstraint("environment_id", "command_id", name="uq_command_environment"),
        sa.UniqueConstraint("environment_id", "owner_scope", "idempotency_key", name="uq_command_idempotency"),
        schema=SCHEMA,
    )
    op.create_table(
        "receipt",
        sa.Column("receipt_id", UUID, primary_key=True),
        _environment(),
        sa.Column("command_id", UUID, nullable=False),
        sa.Column("processing_owner", sa.String(32), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("state_version", sa.BigInteger(), nullable=False),
        sa.Column("reason_code", sa.String(96)),
        sa.Column("result", JSONB),
        sa.Column("pending_responsibility_refs", JSONB, nullable=False),
        _digest("content_digest"),
        sa.Column("created_at", UTC_TS, nullable=False),
        sa.Column("updated_at", UTC_TS, nullable=False),
        sa.ForeignKeyConstraint(
            ("environment_id", "command_id"),
            ("halpha.command.environment_id", "halpha.command.command_id"),
            name="fk_receipt_command",
        ),
        sa.CheckConstraint(
            "state IN ('RECEIVED','PROCESSING','EFFECTIVE','REJECTED','UNKNOWN')",
            name="ck_receipt_state",
        ),
        sa.CheckConstraint("state_version > 0", name="ck_receipt_state_version"),
        _digest_check("content_digest", "ck_receipt_content_digest"),
        sa.UniqueConstraint("environment_id", "receipt_id", name="uq_receipt_environment"),
        sa.UniqueConstraint("environment_id", "command_id", name="uq_receipt_command"),
        schema=SCHEMA,
    )
    op.create_table(
        "notification",
        sa.Column("notification_id", UUID, primary_key=True),
        _environment(),
        sa.Column("source_identity", sa.String(384), nullable=False),
        sa.Column("task_ref", UUID),
        sa.Column("source_business_time", UTC_TS, nullable=False),
        sa.Column("recipient_route_ref", sa.String(160), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("state_version", sa.BigInteger(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("claim_version", sa.BigInteger(), nullable=False),
        sa.Column("next_attempt_at", UTC_TS),
        _digest("content_digest"),
        sa.Column("created_at", UTC_TS, nullable=False),
        sa.Column("updated_at", UTC_TS, nullable=False),
        sa.ForeignKeyConstraint(
            ("environment_id", "task_ref"),
            ("halpha.task.environment_id", "halpha.task.task_id"),
            name="fk_notification_task",
        ),
        sa.CheckConstraint("state IN ('PENDING','DELIVERED','ABANDONED')", name="ck_notification_state"),
        sa.CheckConstraint("state_version > 0 AND claim_version > 0", name="ck_notification_versions"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_notification_attempt_count"),
        _digest_check("content_digest", "ck_notification_content_digest"),
        sa.UniqueConstraint("environment_id", "notification_id", name="uq_notification_environment"),
        sa.UniqueConstraint("environment_id", "source_identity", name="uq_notification_source_identity"),
        schema=SCHEMA,
    )

    authority_tables = (
        "account_capital_limit_version",
        "machine_authorization_version",
        "plan_activation",
        "plan_allocation",
        "stop_state_version",
        "execution_action",
    )
    for table in authority_tables:
        op.create_check_constraint(
            f"ck_{table}_database_environment",
            table,
            f"environment_kind = '{database_environment_kind}'",
            schema=SCHEMA,
        )

    roles = {
        "app": f"{role_prefix}_app",
        "executor": f"{role_prefix}_executor",
        "backup": f"{role_prefix}_backup",
    }
    op.execute(sa.text("REVOKE ALL ON ALL TABLES IN SCHEMA halpha FROM PUBLIC"))
    for role in roles.values():
        op.execute(sa.text(f'GRANT USAGE ON SCHEMA halpha TO "{role}"'))
        op.execute(sa.text(f'GRANT SELECT ON ALL TABLES IN SCHEMA halpha TO "{role}"'))
    op.execute(sa.text(f'GRANT USAGE ON SCHEMA halpha_meta TO "{roles["backup"]}"'))
    op.execute(
        sa.text(
            f'GRANT SELECT ON TABLE halpha_meta.alembic_version TO "{roles["backup"]}"'
        )
    )

    app_write = (
        "trade_plan_draft",
        "trade_plan_version",
        "plan_activation",
        "plan_event",
        "account_capital_limit_version",
        "machine_authorization_version",
        "plan_allocation",
        "stop_state_version",
        "review",
        "improvement_handoff",
        "task",
        "command",
        "receipt",
        "notification",
    )
    executor_write = (
        "plan_activation",
        "plan_event",
        "venue_fact",
        "plan_allocation",
        "stop_state_version",
        "execution_action",
        "review",
        "improvement_handoff",
        "task",
        "receipt",
        "notification",
    )
    for table in app_write:
        op.execute(
            sa.text(
                f'GRANT INSERT, UPDATE, DELETE ON TABLE halpha.{table} TO "{roles["app"]}"'
            )
        )
    for table in executor_write:
        op.execute(
            sa.text(
                f'GRANT INSERT, UPDATE, DELETE ON TABLE halpha.{table} TO "{roles["executor"]}"'
            )
        )


def downgrade() -> None:
    op.drop_constraint(
        "fk_plan_activation_allocation",
        "plan_activation",
        schema=SCHEMA,
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_machine_authorization_activation",
        "machine_authorization_version",
        schema=SCHEMA,
        type_="foreignkey",
    )
    for table in DROP_ORDER:
        op.drop_table(table, schema=SCHEMA)
    op.execute(sa.text("DROP SCHEMA IF EXISTS halpha"))
