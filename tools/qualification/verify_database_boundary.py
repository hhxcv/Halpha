"""Read-only check of the current PostgreSQL schema and role boundary."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import keyring
import psycopg

from halpha.database.record_families import (
    CURRENT_PRODUCT_SCHEMA_REVISION,
    PRODUCT_RECORD_FAMILIES,
)
from halpha.database.security_contract import (
    APP_WRITE_PRIVILEGES,
    AUTHORITY_CONSTRAINT_TABLES,
    AUTHORITY_PAIR_EXPRESSION,
    CRITICAL_TRIGGER_FUNCTIONS,
    DATABASE_ENVIRONMENT_CONSTRAINT_TABLES,
    ENVIRONMENT_ROLE_KINDS as ROLE_KINDS_BY_ENVIRONMENT,
    EXECUTOR_WRITE_PRIVILEGES,
    LIVE_ACTIVATION_SAFETY_INDEX,
    ROLE_VAULT_NAMES,
    expected_database_acl,
    expected_function_acl,
    expected_schema_acl,
    expected_table_acl,
    live_activation_safety_index_qualified,
    managed_role_names,
    normalize_sql,
    normalized_sql_sha256,
)
from halpha.runtime_identity import require_repository_runtime
from halpha.winvault import require_win_vault_backend


ENVIRONMENTS = {
    "demo": {"database": "halpha_demo", "profile": "BINANCE_DEMO", "kind": "DEMO"},
    "live_copy": {
        "database": "halpha_live_copy",
        "profile": "BINANCE_LIVE_COPY",
        "kind": "LIVE",
    },
    "live_personal": {
        "database": "halpha_live_personal",
        "profile": "BINANCE_LIVE_PERSONAL",
        "kind": "LIVE",
    },
}
HEAD = CURRENT_PRODUCT_SCHEMA_REVISION
EXPECTED_ROLE_ATTRIBUTES = {
    "login": True,
    "superuser": False,
    "create_database": False,
    "create_role": False,
    "inherit": False,
    "replication": False,
    "bypass_rls": False,
    "config": [],
}
PLAN_ACTIVATION_IMMUTABLE_FIELDS = (
    "activation_id",
    "environment_id",
    "environment_kind",
    "authority_class",
    "plan_version_ref",
    "account_ref",
    "instrument_ref",
    "direction",
    "decision_basis_ref",
    "framework_strategy_id",
    "target_exposure",
    "order_schedule_snapshot",
    "order_schedule_snapshot_digest",
    "created_at",
)
WRITE_PRIVILEGES = ("INSERT", "UPDATE", "DELETE")
EXPECTED_APP_WRITES = {
    table: [
        privilege
        for privilege in WRITE_PRIVILEGES
        if privilege in privileges
    ]
    for table, privileges in APP_WRITE_PRIVILEGES.items()
}
EXPECTED_EXECUTOR_WRITES = {
    table: [
        privilege
        for privilege in WRITE_PRIVILEGES
        if privilege in privileges
    ]
    for table, privileges in EXECUTOR_WRITE_PRIVILEGES.items()
}


def _reference(profile: str, role: str) -> tuple[str, str]:
    return (
        f"Halpha/PostgreSQL/{profile}/{ROLE_VAULT_NAMES[role]}",
        "scram_password",
    )


def _managed_role_names() -> tuple[str, ...]:
    return managed_role_names()


def _connect(
    environment: str,
    role: str,
    *,
    database: str | None = None,
) -> psycopg.Connection[Any]:
    settings = ENVIRONMENTS[environment]
    secret = keyring.get_password(*_reference(settings["profile"], role))
    if not secret:
        raise RuntimeError(
            f"DATABASE_ROLE_REFERENCE_MISSING environment={environment} role={role}"
        )
    try:
        return psycopg.connect(
            host="127.0.0.1",
            port=5432,
            dbname=database or settings["database"],
            user=f"halpha_{environment}_{role}",
            password=secret,
        )
    finally:
        secret = ""


def _privilege(connection: psycopg.Connection[Any], table: str, privilege: str) -> bool:
    return bool(
        connection.execute(
            "SELECT has_table_privilege(current_user, %s, %s)",
            (f"halpha.{table}", privilege),
        ).fetchone()[0]
    )


def _write_matrix(connection: psycopg.Connection[Any]) -> dict[str, list[str]]:
    return {
        table: [
            privilege
            for privilege in WRITE_PRIVILEGES
            if _privilege(connection, table, privilege)
        ]
        for table in sorted(PRODUCT_RECORD_FAMILIES)
        if any(
            _privilege(connection, table, privilege)
            for privilege in WRITE_PRIVILEGES
        )
    }


def _canonical_rows(rows: set[tuple[Any, ...]]) -> list[list[Any]]:
    return [
        list(row)
        for row in sorted(
            rows,
            key=lambda row: json.dumps(
                row,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
    ]


def _row_set_digest(rows: set[tuple[Any, ...]]) -> str:
    canonical = json.dumps(
        _canonical_rows(rows),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def _exact_rows(
    actual: set[tuple[Any, ...]],
    expected: set[tuple[Any, ...]],
) -> dict[str, Any]:
    return {
        "exact": actual == expected,
        "actual_count": len(actual),
        "expected_count": len(expected),
        "actual_digest": _row_set_digest(actual),
        "expected_digest": _row_set_digest(expected),
        "missing": _canonical_rows(expected - actual),
        "unexpected": _canonical_rows(actual - expected),
    }


def _inspect_function_boundary(
    connection: psycopg.Connection[Any],
    environment: str,
) -> dict[str, Any]:
    migration_role = f"halpha_{environment}_migration"
    function_owners = {
        (str(row[0]), str(row[1]))
        for row in connection.execute(
            """
            SELECT procedure.proname || '('
                   || pg_get_function_identity_arguments(procedure.oid) || ')',
                   owner.rolname
            FROM pg_catalog.pg_proc AS procedure
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = procedure.pronamespace
            JOIN pg_catalog.pg_roles AS owner ON owner.oid = procedure.proowner
            WHERE namespace.nspname = 'halpha'
            """
        ).fetchall()
    }
    function_acl = {
        (str(row[0]), str(row[1]), str(row[2]), bool(row[3]))
        for row in connection.execute(
            """
            SELECT procedure.proname || '('
                   || pg_get_function_identity_arguments(procedure.oid) || ')',
                   COALESCE(grantee.rolname, 'PUBLIC'),
                   acl.privilege_type, acl.is_grantable
            FROM pg_catalog.pg_proc AS procedure
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = procedure.pronamespace
            CROSS JOIN LATERAL aclexplode(
                COALESCE(
                    procedure.proacl,
                    acldefault('f', procedure.proowner)
                )
            ) AS acl
            LEFT JOIN pg_catalog.pg_roles AS grantee
              ON grantee.oid = acl.grantee
            WHERE namespace.nspname = 'halpha'
            """
        ).fetchall()
    }
    expected_function_owners = {
        (f"{contract['function']}()", migration_role)
        for contract in CRITICAL_TRIGGER_FUNCTIONS.values()
    }
    return {
        "function_owners": _exact_rows(
            function_owners,
            expected_function_owners,
        ),
        "function_acl": _exact_rows(
            function_acl,
            expected_function_acl(environment),
        ),
    }


def _inspect_acl_boundary(
    connection: psycopg.Connection[Any],
    environment: str,
) -> dict[str, Any]:
    migration_role = f"halpha_{environment}_migration"
    database_row = connection.execute(
        """
        SELECT database_row.datname, owner.rolname,
               database_row.datcollate, database_row.datctype
        FROM pg_catalog.pg_database AS database_row
        JOIN pg_catalog.pg_roles AS owner ON owner.oid = database_row.datdba
        WHERE database_row.datname = current_database()
        """
    ).fetchone()
    database_acl = {
        (str(row[0]), str(row[1]), bool(row[2]))
        for row in connection.execute(
            """
            SELECT COALESCE(grantee.rolname, 'PUBLIC'),
                   acl.privilege_type, acl.is_grantable
            FROM pg_catalog.pg_database AS database_row
            CROSS JOIN LATERAL aclexplode(
                COALESCE(
                    database_row.datacl,
                    acldefault('d', database_row.datdba)
                )
            ) AS acl
            LEFT JOIN pg_catalog.pg_roles AS grantee
              ON grantee.oid = acl.grantee
            WHERE database_row.datname = current_database()
            """
        ).fetchall()
    }
    schema_owners = {
        (str(row[0]), str(row[1]))
        for row in connection.execute(
            """
            SELECT namespace.nspname, owner.rolname
            FROM pg_catalog.pg_namespace AS namespace
            JOIN pg_catalog.pg_roles AS owner ON owner.oid = namespace.nspowner
            WHERE namespace.nspname IN ('halpha', 'halpha_meta', 'public')
            """
        ).fetchall()
    }
    schema_acl = {
        (str(row[0]), str(row[1]), str(row[2]), bool(row[3]))
        for row in connection.execute(
            """
            SELECT namespace.nspname,
                   COALESCE(grantee.rolname, 'PUBLIC'),
                   acl.privilege_type, acl.is_grantable
            FROM pg_catalog.pg_namespace AS namespace
            CROSS JOIN LATERAL aclexplode(
                COALESCE(
                    namespace.nspacl,
                    acldefault('n', namespace.nspowner)
                )
            ) AS acl
            LEFT JOIN pg_catalog.pg_roles AS grantee
              ON grantee.oid = acl.grantee
            WHERE namespace.nspname IN ('halpha', 'halpha_meta', 'public')
            """
        ).fetchall()
    }
    table_owners = {
        (str(row[0]), str(row[1]), str(row[2]))
        for row in connection.execute(
            """
            SELECT namespace.nspname, relation.relname, owner.rolname
            FROM pg_catalog.pg_class AS relation
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            JOIN pg_catalog.pg_roles AS owner ON owner.oid = relation.relowner
            WHERE namespace.nspname IN ('halpha', 'halpha_meta')
              AND relation.relkind IN ('r', 'p')
            """
        ).fetchall()
    }
    table_acl = {
        (
            str(row[0]),
            str(row[1]),
            str(row[2]),
            str(row[3]),
            bool(row[4]),
        )
        for row in connection.execute(
            """
            SELECT namespace.nspname, relation.relname,
                   COALESCE(grantee.rolname, 'PUBLIC'),
                   acl.privilege_type, acl.is_grantable
            FROM pg_catalog.pg_class AS relation
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            CROSS JOIN LATERAL aclexplode(
                COALESCE(
                    relation.relacl,
                    acldefault('r', relation.relowner)
                )
            ) AS acl
            LEFT JOIN pg_catalog.pg_roles AS grantee
              ON grantee.oid = acl.grantee
            WHERE namespace.nspname IN ('halpha', 'halpha_meta')
              AND relation.relkind IN ('r', 'p')
            """
        ).fetchall()
    }
    column_acl = {
        (
            str(row[0]),
            str(row[1]),
            str(row[2]),
            str(row[3]),
            str(row[4]),
            bool(row[5]),
        )
        for row in connection.execute(
            """
            SELECT namespace.nspname, relation.relname, attribute.attname,
                   COALESCE(grantee.rolname, 'PUBLIC'),
                   acl.privilege_type, acl.is_grantable
            FROM pg_catalog.pg_attribute AS attribute
            JOIN pg_catalog.pg_class AS relation
              ON relation.oid = attribute.attrelid
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            CROSS JOIN LATERAL aclexplode(attribute.attacl) AS acl
            LEFT JOIN pg_catalog.pg_roles AS grantee
              ON grantee.oid = acl.grantee
            WHERE namespace.nspname IN ('halpha', 'halpha_meta')
              AND relation.relkind IN ('r', 'p')
              AND attribute.attnum > 0
              AND NOT attribute.attisdropped
              AND attribute.attacl IS NOT NULL
            """
        ).fetchall()
    }
    expected_table_owners = {
        ("halpha", table, migration_role)
        for table in PRODUCT_RECORD_FAMILIES
    } | {("halpha_meta", "alembic_version", migration_role)}
    expected_schema_owners = {
        ("halpha", migration_role),
        ("halpha_meta", migration_role),
        ("public", "pg_database_owner"),
    }
    return {
        "database": {
            "name": str(database_row[0]) if database_row else None,
            "owner": str(database_row[1]) if database_row else None,
            "collation": str(database_row[2]) if database_row else None,
            "ctype": str(database_row[3]) if database_row else None,
            "acl": _exact_rows(database_acl, expected_database_acl(environment)),
        },
        "schema_owners": _exact_rows(schema_owners, expected_schema_owners),
        "schema_acl": _exact_rows(schema_acl, expected_schema_acl(environment)),
        "table_owners": _exact_rows(table_owners, expected_table_owners),
        "table_acl": _exact_rows(table_acl, expected_table_acl(environment)),
        "column_acl": _exact_rows(column_acl, set()),
        **_inspect_function_boundary(connection, environment),
    }


def _acl_boundary_qualified(boundary: dict[str, Any], environment: str) -> bool:
    database = boundary.get("database", {})
    return (
        database.get("owner") == f"halpha_{environment}_migration"
        and database.get("collation") == "C"
        and database.get("ctype") == "C"
        and database.get("acl", {}).get("exact") is True
        and all(
            boundary.get(key, {}).get("exact") is True
            for key in (
                "schema_owners",
                "schema_acl",
                "table_owners",
                "table_acl",
                "column_acl",
                "function_owners",
                "function_acl",
            )
        )
    )


def _inspect_managed_role_boundary() -> dict[str, Any]:
    managed_roles = list(_managed_role_names())
    with _connect("demo", "migration") as connection:
        role_rows = connection.execute(
            """
            SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
                   rolinherit, rolreplication, rolbypassrls, rolconfig
            FROM pg_catalog.pg_roles
            WHERE rolname = ANY(%s)
            ORDER BY rolname
            """,
            (managed_roles,),
        ).fetchall()
        membership_rows = connection.execute(
            """
            SELECT granted.rolname, member.rolname
            FROM pg_catalog.pg_auth_members AS membership
            JOIN pg_catalog.pg_roles AS granted
              ON granted.oid = membership.roleid
            JOIN pg_catalog.pg_roles AS member
              ON member.oid = membership.member
            WHERE granted.rolname = ANY(%s)
               OR member.rolname = ANY(%s)
            ORDER BY granted.rolname, member.rolname
            """,
            (managed_roles, managed_roles),
        ).fetchall()
    return {
        "attributes": {
            str(row[0]): {
                "login": bool(row[1]),
                "superuser": bool(row[2]),
                "create_database": bool(row[3]),
                "create_role": bool(row[4]),
                "inherit": bool(row[5]),
                "replication": bool(row[6]),
                "bypass_rls": bool(row[7]),
                "config": list(row[8] or ()),
            }
            for row in role_rows
        },
        "memberships": [
            {"granted_role": str(row[0]), "member_role": str(row[1])}
            for row in membership_rows
        ],
    }


def _critical_contract_qualified(
    contract: dict[str, Any],
    environment: str,
) -> bool:
    index = contract.get("live_activation_safety_index")
    if not live_activation_safety_index_qualified(index):
        return False
    constraints = contract.get("constraints")
    if not isinstance(constraints, dict):
        return False
    expected_constraint_names = (
        set(AUTHORITY_CONSTRAINT_TABLES)
        | set(DATABASE_ENVIRONMENT_CONSTRAINT_TABLES)
    )
    if set(constraints) != expected_constraint_names:
        return False
    for name, table in AUTHORITY_CONSTRAINT_TABLES.items():
        item = constraints[name]
        if (
            item.get("table") != table
            or item.get("type") != "c"
            or item.get("validated") is not True
            or item.get("expression") != AUTHORITY_PAIR_EXPRESSION
        ):
            return False
    environment_expression = (
        f"environment_kind::text = '{ENVIRONMENTS[environment]['kind']}'::text"
    )
    for name, table in DATABASE_ENVIRONMENT_CONSTRAINT_TABLES.items():
        item = constraints[name]
        if (
            item.get("table") != table
            or item.get("type") != "c"
            or item.get("validated") is not True
            or item.get("expression") != environment_expression
        ):
            return False
    triggers = contract.get("triggers")
    if not isinstance(triggers, dict) or set(triggers) != set(CRITICAL_TRIGGER_FUNCTIONS):
        return False
    trigger_inventory = contract.get("trigger_inventory")
    expected_trigger_inventory = sorted(
        [expected["table"], name]
        for name, expected in CRITICAL_TRIGGER_FUNCTIONS.items()
    )
    if trigger_inventory != expected_trigger_inventory:
        return False
    migration_role = f"halpha_{environment}_migration"
    for name, expected in CRITICAL_TRIGGER_FUNCTIONS.items():
        item = triggers[name]
        if (
            item.get("table") != expected["table"]
            or item.get("enabled") != "O"
            or item.get("type_bits") != 27
            or item.get("function") != expected["function"]
            or item.get("body_sha256") != expected["body_sha256"]
            or item.get("language") != "plpgsql"
            or item.get("security_definer") is not False
            or item.get("volatility") != "v"
            or item.get("function_owner") != migration_role
        ):
            return False
    review_fk = contract.get("review_version_chain_fk")
    return review_fk == {
        "table": "review",
        "type": "f",
        "validated": True,
        "definition": (
            "FOREIGN KEY (environment_id, review_id, previous_version) "
            "REFERENCES halpha.review(environment_id, review_id, review_version)"
        ),
    }


def _inspect_environment(
    environment: str,
    *,
    database: str | None = None,
) -> dict[str, Any]:
    settings = ENVIRONMENTS[environment]
    with _connect(environment, "migration", database=database) as migration:
        tables = [
            str(row[0])
            for row in migration.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'halpha' AND table_type = 'BASE TABLE' "
                "ORDER BY table_name"
            ).fetchall()
        ]
        revision_row = migration.execute(
            "SELECT version_num FROM halpha_meta.alembic_version"
        ).fetchone()
        revision = str(revision_row[0]) if revision_row else "MISSING"
        live_activation_safety_index = migration.execute(
            """
            SELECT index.indisunique, index.indisvalid, index.indisready,
                   ARRAY(
                       SELECT attribute.attname
                       FROM unnest(index.indkey) WITH ORDINALITY
                            AS key_column(attnum, ordinal)
                       JOIN pg_catalog.pg_attribute AS attribute
                         ON attribute.attrelid = index.indrelid
                        AND attribute.attnum = key_column.attnum
                       ORDER BY key_column.ordinal
                   ),
                   pg_get_expr(index.indpred, index.indrelid, true)
            FROM pg_catalog.pg_index AS index
            WHERE index.indexrelid = to_regclass(%s)
            """,
            (f"halpha.{LIVE_ACTIVATION_SAFETY_INDEX}",),
        ).fetchone()
        constraint_names = [
            *AUTHORITY_CONSTRAINT_TABLES,
            *DATABASE_ENVIRONMENT_CONSTRAINT_TABLES,
        ]
        constraints = {
            str(row[0]): {
                "table": str(row[1]),
                "type": str(row[2]),
                "validated": bool(row[3]),
                "expression": normalize_sql(str(row[4])),
                "expression_sha256": normalized_sql_sha256(str(row[4])),
            }
            for row in migration.execute(
                """
                SELECT constraint_row.conname, relation.relname,
                       constraint_row.contype, constraint_row.convalidated,
                       pg_get_expr(
                           constraint_row.conbin,
                           constraint_row.conrelid,
                           true
                       )
                FROM pg_catalog.pg_constraint AS constraint_row
                JOIN pg_catalog.pg_class AS relation
                  ON relation.oid = constraint_row.conrelid
                WHERE constraint_row.connamespace = 'halpha'::regnamespace
                  AND constraint_row.conname = ANY(%s)
                ORDER BY constraint_row.conname
                """,
                (constraint_names,),
            ).fetchall()
        }
        trigger_rows = migration.execute(
            """
            SELECT trigger_row.tgname, relation.relname,
                   trigger_row.tgenabled, trigger_row.tgtype,
                   procedure.proname, procedure.prosrc,
                   language.lanname, procedure.prosecdef,
                   procedure.provolatile, owner.rolname
            FROM pg_catalog.pg_trigger AS trigger_row
            JOIN pg_catalog.pg_class AS relation
              ON relation.oid = trigger_row.tgrelid
            JOIN pg_catalog.pg_namespace AS namespace
              ON namespace.oid = relation.relnamespace
            JOIN pg_catalog.pg_proc AS procedure
              ON procedure.oid = trigger_row.tgfoid
            JOIN pg_catalog.pg_language AS language
              ON language.oid = procedure.prolang
            JOIN pg_catalog.pg_roles AS owner
              ON owner.oid = procedure.proowner
            WHERE namespace.nspname = 'halpha'
              AND relation.relname = ANY(%s)
              AND NOT trigger_row.tgisinternal
            ORDER BY relation.relname, trigger_row.tgname
            """,
            (list(PRODUCT_RECORD_FAMILIES),),
        ).fetchall()
        triggers = {
            str(row[0]): {
                "table": str(row[1]),
                "enabled": str(row[2]),
                "type_bits": int(row[3]),
                "function": str(row[4]),
                "body_sha256": normalized_sql_sha256(str(row[5])),
                "language": str(row[6]),
                "security_definer": bool(row[7]),
                "volatility": str(row[8]),
                "function_owner": str(row[9]),
            }
            for row in trigger_rows
        }
        review_fk_row = migration.execute(
            """
            SELECT relation.relname, constraint_row.contype,
                   constraint_row.convalidated,
                   pg_get_constraintdef(constraint_row.oid, true)
            FROM pg_catalog.pg_constraint AS constraint_row
            JOIN pg_catalog.pg_class AS relation
              ON relation.oid = constraint_row.conrelid
            WHERE constraint_row.connamespace = 'halpha'::regnamespace
              AND constraint_row.conname = 'fk_review_previous_version'
            """
        ).fetchone()
        review_fk = (
            {
                "table": str(review_fk_row[0]),
                "type": str(review_fk_row[1]),
                "validated": bool(review_fk_row[2]),
                "definition": normalize_sql(str(review_fk_row[3])),
            }
            if review_fk_row
            else None
        )
        critical_contract = {
            "live_activation_safety_index": (
                list(live_activation_safety_index)
                if live_activation_safety_index is not None
                else None
            ),
            "constraints": constraints,
            "triggers": triggers,
            "trigger_inventory": sorted(
                [str(row[1]), str(row[0])]
                for row in trigger_rows
            ),
            "review_version_chain_fk": review_fk,
        }
        critical_contract["qualified"] = _critical_contract_qualified(
            critical_contract,
            environment,
        )
        acl_boundary = _inspect_acl_boundary(migration, environment)

    with _connect(environment, "app", database=database) as app:
        app_privileges = {
            "command_insert": _privilege(app, "command", "INSERT"),
            "execution_action_insert": _privilege(app, "execution_action", "INSERT"),
            "venue_fact_insert": _privilege(app, "venue_fact", "INSERT"),
            "write_matrix": _write_matrix(app),
        }
    with _connect(environment, "executor", database=database) as executor:
        executor_privileges = {
            "command_insert": _privilege(executor, "command", "INSERT"),
            "execution_action_insert": _privilege(executor, "execution_action", "INSERT"),
            "venue_fact_insert": _privilege(executor, "venue_fact", "INSERT"),
            "trade_plan_version_insert": _privilege(
                executor, "trade_plan_version", "INSERT"
            ),
            "write_matrix": _write_matrix(executor),
        }
    with _connect(environment, "backup", database=database) as backup:
        backup_privileges = {
            "all_product_tables_select": all(
                _privilege(backup, table, "SELECT") for table in PRODUCT_RECORD_FAMILIES
            ),
            "any_product_table_insert": any(
                _privilege(backup, table, "INSERT") for table in PRODUCT_RECORD_FAMILIES
            ),
            "write_matrix": _write_matrix(backup),
        }
    app_reader_privileges = None
    if environment.startswith("live_"):
        with _connect(environment, "app_reader", database=database) as app_reader:
            app_reader_privileges = {
                "all_product_tables_select": all(
                    _privilege(app_reader, table, "SELECT")
                    for table in PRODUCT_RECORD_FAMILIES
                ),
                "database_temporary": bool(
                    app_reader.execute(
                        "SELECT has_database_privilege("
                        "current_user, current_database(), 'TEMPORARY')"
                    ).fetchone()[0]
                ),
                "write_matrix": _write_matrix(app_reader),
            }

    return {
        "database": database or settings["database"],
        "revision": revision,
        "product_tables": tables,
        "critical_contract": critical_contract,
        "acl_boundary": acl_boundary,
        "app": app_privileges,
        "executor": executor_privileges,
        "backup": backup_privileges,
        "app_reader": app_reader_privileges,
    }


def _managed_role_boundary_qualified(boundary: dict[str, Any]) -> bool:
    attributes = boundary.get("attributes")
    memberships = boundary.get("memberships")
    return (
        isinstance(attributes, dict)
        and set(attributes) == set(_managed_role_names())
        and all(
            role_attributes == EXPECTED_ROLE_ATTRIBUTES
            for role_attributes in attributes.values()
        )
        and memberships == []
    )


def _cross_database_connect_matrix() -> dict[str, bool]:
    results: dict[str, bool] = {}
    for source in ENVIRONMENTS:
        for target in ENVIRONMENTS:
            if source == target:
                continue
            target_database = str(ENVIRONMENTS[target]["database"])
            for role in ROLE_KINDS_BY_ENVIRONMENT[source]:
                key = f"{source}_{role}_to_{target}"
                try:
                    with _connect(source, role, database=target_database):
                        results[key] = False
                except psycopg.OperationalError as exc:
                    if "permission denied for database" not in str(exc):
                        raise
                    results[key] = True
    return results


def _environment_qualified(
    environment: str,
    result: dict[str, Any],
) -> bool:
    expected_tables = sorted(PRODUCT_RECORD_FAMILIES)
    expected_app = {
        "command_insert": True,
        "execution_action_insert": False,
        "venue_fact_insert": False,
        "write_matrix": EXPECTED_APP_WRITES,
    }
    expected_executor = {
        "command_insert": False,
        "execution_action_insert": True,
        "venue_fact_insert": True,
        "trade_plan_version_insert": False,
        "write_matrix": EXPECTED_EXECUTOR_WRITES,
    }
    expected_backup = {
        "all_product_tables_select": True,
        "any_product_table_insert": False,
        "write_matrix": {},
    }
    expected_app_reader = (
        {
            "all_product_tables_select": True,
            "database_temporary": False,
            "write_matrix": {},
        }
        if environment.startswith("live_")
        else None
    )
    return (
        result.get("revision") == HEAD
        and result.get("product_tables") == expected_tables
        and result.get("critical_contract", {}).get("qualified") is True
        and _critical_contract_qualified(
            result.get("critical_contract", {}),
            environment,
        )
        and _acl_boundary_qualified(
            result.get("acl_boundary", {}),
            environment,
        )
        and result.get("app") == expected_app
        and result.get("executor") == expected_executor
        and result.get("backup") == expected_backup
        and result.get("app_reader") == expected_app_reader
    )


def _qualified(evidence: dict[str, Any]) -> bool:
    environments = evidence.get("environments")
    if not isinstance(environments, dict) or set(environments) != set(ENVIRONMENTS):
        return False
    if not all(
        _environment_qualified(environment, environments[environment])
        for environment in ENVIRONMENTS
    ):
        return False
    expected_cross_database_checks = {
        f"{source}_{role}_to_{target}"
        for source in ENVIRONMENTS
        for target in ENVIRONMENTS
        if source != target
        for role in ROLE_KINDS_BY_ENVIRONMENT[source]
    }
    matrix = evidence.get("cross_database_connect_rejected", {})
    return (
        set(matrix) == expected_cross_database_checks
        and all(matrix.values())
        and _managed_role_boundary_qualified(
            evidence.get("managed_role_boundary", {})
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    runtime = require_repository_runtime()
    require_win_vault_backend(keyring.get_keyring())
    evidence: dict[str, Any] = {
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "runtime": {"python_version": runtime.python_version},
        "check_mode": "READ_ONLY",
        "environments": {
            environment: _inspect_environment(environment)
            for environment in ENVIRONMENTS
        },
        "managed_role_boundary": _inspect_managed_role_boundary(),
        "cross_database_connect_rejected": _cross_database_connect_matrix(),
    }
    evidence["status"] = "QUALIFIED" if _qualified(evidence) else "REJECTED"
    canonical = json.dumps(evidence, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    evidence["evidence_digest"] = sha256(canonical.encode("utf-8")).hexdigest()
    rendered = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if evidence["status"] == "QUALIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
