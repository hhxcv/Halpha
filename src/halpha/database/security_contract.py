"""Small, explicit PostgreSQL safety contract shared by runtime and qualification."""

from __future__ import annotations

from hashlib import sha256
from typing import Any

from halpha.database.record_families import PRODUCT_RECORD_FAMILIES


ENVIRONMENT_ROLE_KINDS = {
    "demo": ("app", "executor", "migration", "backup"),
    "live_copy": ("app", "app_reader", "executor", "migration", "backup"),
    "live_personal": ("app", "app_reader", "executor", "migration", "backup"),
}
ROLE_VAULT_NAMES = {
    "app": "App",
    "app_reader": "AppReader",
    "executor": "Executor",
    "migration": "Migration",
    "backup": "Backup",
}

TABLE_OWNER_PRIVILEGES = frozenset(
    {
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
        "TRUNCATE",
        "REFERENCES",
        "TRIGGER",
        "MAINTAIN",
    }
)
APP_WRITE_PRIVILEGES = {
    "trade_plan_draft": frozenset({"INSERT", "UPDATE", "DELETE"}),
    "trade_plan_version": frozenset({"INSERT"}),
    "plan_activation": frozenset({"INSERT", "UPDATE"}),
    "stop_state_version": frozenset({"INSERT"}),
    "review": frozenset({"INSERT"}),
    "stage_review": frozenset({"INSERT"}),
    "command": frozenset({"INSERT"}),
    "receipt": frozenset({"INSERT", "UPDATE"}),
}
EXECUTOR_WRITE_PRIVILEGES = {
    "plan_activation": frozenset({"UPDATE"}),
    "plan_event": frozenset({"INSERT"}),
    "stop_state_version": frozenset({"INSERT"}),
    "execution_action": frozenset({"INSERT", "UPDATE"}),
    "venue_fact": frozenset({"INSERT"}),
    "review": frozenset({"INSERT"}),
    "receipt": frozenset({"UPDATE"}),
}

LIVE_ACTIVATION_SAFETY_INDEX = "ix_plan_activation_live_open_account_scope"
LIVE_ACTIVATION_SAFETY_INDEX_COLUMNS = ("environment_id", "account_ref")
LIVE_ACTIVATION_SAFETY_INDEX_PREDICATE = (
    "environment_kind::text = 'LIVE'::text "
    "AND lifecycle::text <> 'COMPLETED'::text"
)

AUTHORITY_PAIR_EXPRESSION = (
    "environment_kind::text = 'DEMO'::text "
    "AND authority_class::text = 'DEMO_VALIDATION'::text "
    "OR environment_kind::text = 'LIVE'::text "
    "AND authority_class::text = 'LIVE_REAL_CAPITAL'::text"
)
AUTHORITY_CONSTRAINT_TABLES = {
    "ck_execution_action_authority_pair": "execution_action",
    "ck_plan_activation_authority_pair": "plan_activation",
    "ck_stop_state_authority_pair": "stop_state_version",
}
DATABASE_ENVIRONMENT_CONSTRAINT_TABLES = {
    "ck_execution_action_database_environment": "execution_action",
    "ck_plan_activation_database_environment": "plan_activation",
    "ck_stop_state_version_database_environment": "stop_state_version",
}

CRITICAL_TRIGGER_FUNCTIONS = {
    "trg_execution_action_identity_immutable": {
        "table": "execution_action",
        "function": "guard_execution_action_identity_immutable",
        "body_sha256": "bd3dee1627bb0ff8b7e6db108001f36c036feea7554b74f76341418622b4a3a7",
    },
    "trg_plan_activation_identity_immutable": {
        "table": "plan_activation",
        "function": "guard_plan_activation_identity_immutable",
        "body_sha256": "b506274ad246754102e5979c420ed6cf63f8b4768ac57fb85d3f4aaa97c5a907",
    },
    "trg_review_append_only": {
        "table": "review",
        "function": "guard_review_append_only",
        "body_sha256": "72e2f2f06c80f34a6fa065afcbd7a12a2d796ab34ff6a98848e48868d1d5920c",
    },
    "trg_stage_review_append_only": {
        "table": "stage_review",
        "function": "guard_stage_review_append_only",
        "body_sha256": "b410535e0ff7b0946af5572c4d701efb60e6edb8d058de8d89cfdc8477a05799",
    },
    "trg_venue_fact_append_only": {
        "table": "venue_fact",
        "function": "guard_venue_fact_append_only",
        "body_sha256": "597eb9f3bc5185a2a386df89fc221536434129f0b97b95fe4bd8e0fc0ab2ea16",
    },
}


def role_name(environment: str, kind: str) -> str:
    if kind not in ENVIRONMENT_ROLE_KINDS.get(environment, ()):
        raise ValueError(
            f"DATABASE_ROLE_UNSUPPORTED environment={environment} kind={kind}"
        )
    return f"halpha_{environment}_{kind}"


def managed_role_names() -> tuple[str, ...]:
    return tuple(
        role_name(environment, kind)
        for environment in ENVIRONMENT_ROLE_KINDS
        for kind in ENVIRONMENT_ROLE_KINDS[environment]
    )


def database_access_roles(
    environment: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if environment not in ENVIRONMENT_ROLE_KINDS:
        raise ValueError(f"DATABASE_ENVIRONMENT_UNSUPPORTED environment={environment}")
    granted = tuple(
        role_name(environment, kind)
        for kind in ENVIRONMENT_ROLE_KINDS[environment]
    )
    revoked = tuple(
        role_name(peer, kind)
        for peer in ENVIRONMENT_ROLE_KINDS
        if peer != environment
        for kind in ENVIRONMENT_ROLE_KINDS[peer]
    )
    return granted, revoked


def normalize_sql(value: str) -> str:
    return " ".join(value.split())


def normalized_sql_sha256(value: str) -> str:
    return sha256(normalize_sql(value).encode("utf-8")).hexdigest()


def live_activation_safety_index_qualified(row: Any) -> bool:
    if row is None or len(row) != 5:
        return False
    unique, valid, ready, columns, predicate = row
    return (
        unique is False
        and valid is True
        and ready is True
        and tuple(columns or ()) == LIVE_ACTIVATION_SAFETY_INDEX_COLUMNS
        and normalize_sql(str(predicate or ""))
        == LIVE_ACTIVATION_SAFETY_INDEX_PREDICATE
    )


def expected_database_acl(environment: str) -> set[tuple[str, str, bool]]:
    owner = role_name(environment, "migration")
    rows = {
        (owner, privilege, False)
        for privilege in ("CONNECT", "CREATE", "TEMPORARY")
    }
    rows.update(
        (role_name(environment, kind), "CONNECT", False)
        for kind in ENVIRONMENT_ROLE_KINDS[environment]
        if kind != "migration"
    )
    return rows


def expected_schema_acl(environment: str) -> set[tuple[str, str, str, bool]]:
    owner = role_name(environment, "migration")
    rows = {
        ("halpha", owner, "CREATE", False),
        ("halpha", owner, "USAGE", False),
        ("halpha_meta", owner, "CREATE", False),
        ("halpha_meta", owner, "USAGE", False),
        ("halpha_meta", role_name(environment, "backup"), "USAGE", False),
        ("public", "pg_database_owner", "CREATE", False),
        ("public", "pg_database_owner", "USAGE", False),
        ("public", "PUBLIC", "USAGE", False),
    }
    rows.update(
        ("halpha", role_name(environment, kind), "USAGE", False)
        for kind in ENVIRONMENT_ROLE_KINDS[environment]
        if kind != "migration"
    )
    rows.update(
        ("halpha_meta", role_name(environment, kind), "USAGE", False)
        for kind in ENVIRONMENT_ROLE_KINDS[environment]
        if kind in {"app", "app_reader", "executor"}
    )
    return rows


def expected_table_acl(
    environment: str,
) -> set[tuple[str, str, str, str, bool]]:
    owner = role_name(environment, "migration")
    rows: set[tuple[str, str, str, str, bool]] = set()
    for table in PRODUCT_RECORD_FAMILIES:
        rows.update(
            ("halpha", table, owner, privilege, False)
            for privilege in TABLE_OWNER_PRIVILEGES
        )
        rows.add(("halpha", table, role_name(environment, "app"), "SELECT", False))
        if table != "stage_review":
            rows.add(
                ("halpha", table, role_name(environment, "executor"), "SELECT", False)
            )
        rows.add(
            ("halpha", table, role_name(environment, "backup"), "SELECT", False)
        )
        if environment.startswith("live_"):
            rows.add(
                (
                    "halpha",
                    table,
                    role_name(environment, "app_reader"),
                    "SELECT",
                    False,
                )
            )
        rows.update(
            ("halpha", table, role_name(environment, "app"), privilege, False)
            for privilege in APP_WRITE_PRIVILEGES.get(table, ())
        )
        rows.update(
            ("halpha", table, role_name(environment, "executor"), privilege, False)
            for privilege in EXECUTOR_WRITE_PRIVILEGES.get(table, ())
        )
    rows.update(
        ("halpha_meta", "alembic_version", owner, privilege, False)
        for privilege in TABLE_OWNER_PRIVILEGES
    )
    rows.add(
        (
            "halpha_meta",
            "alembic_version",
            role_name(environment, "backup"),
            "SELECT",
            False,
        )
    )
    rows.update(
        (
            "halpha_meta",
            "alembic_version",
            role_name(environment, kind),
            "SELECT",
            False,
        )
        for kind in ENVIRONMENT_ROLE_KINDS[environment]
        if kind in {"app", "app_reader", "executor"}
    )
    return rows


def expected_function_acl(
    environment: str,
) -> set[tuple[str, str, str, bool]]:
    owner = role_name(environment, "migration")
    return {
        (f"{contract['function']}()", owner, "EXECUTE", False)
        for contract in CRITICAL_TRIGGER_FUNCTIONS.values()
    }
