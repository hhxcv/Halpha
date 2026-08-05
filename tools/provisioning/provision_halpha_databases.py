"""Provision three isolated trading-context databases and SCRAM roles."""

from __future__ import annotations

import argparse
import secrets
import string
from collections.abc import Sequence

import keyring
import psycopg
from psycopg import sql

from halpha.database.security_contract import (
    ENVIRONMENT_ROLE_KINDS as ROLE_KINDS_BY_ENVIRONMENT,
    ROLE_VAULT_NAMES,
    database_access_roles,
    managed_role_names,
    role_name,
)
from halpha.runtime_identity import require_repository_runtime
from halpha.winvault import require_win_vault_backend


SUPERUSER_REFERENCE = ("Halpha/PostgreSQL/Instance", "postgres_superuser")
ENVIRONMENTS = {
    "demo": {
        "database": "halpha_demo",
        "vault_profile": "BINANCE_DEMO",
    },
    "live_copy": {
        "database": "halpha_live_copy",
        "vault_profile": "BINANCE_LIVE_COPY",
    },
    "live_personal": {
        "database": "halpha_live_personal",
        "vault_profile": "BINANCE_LIVE_PERSONAL",
    },
}
ROLE_SECURITY_ATTRIBUTES = (
    "LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT "
    "NOREPLICATION NOBYPASSRLS"
)


def _role_name(environment: str, kind: str) -> str:
    return role_name(environment, kind)


def _vault_reference(profile: str, kind: str) -> tuple[str, str]:
    return (
        f"Halpha/PostgreSQL/{profile}/{ROLE_VAULT_NAMES[kind]}",
        "scram_password",
    )


def _managed_role_names() -> tuple[str, ...]:
    return managed_role_names()


def _database_access_roles(
    environment: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    return database_access_roles(environment)


def _converge_database_acl(
    cursor: psycopg.Cursor[object],
    *,
    database: str,
    owner: str,
    granted_roles: Sequence[str],
) -> None:
    rows = cursor.execute(
        """
        SELECT DISTINCT COALESCE(role.rolname, 'PUBLIC')
        FROM pg_catalog.pg_database AS database_row
        CROSS JOIN LATERAL aclexplode(
            COALESCE(
                database_row.datacl,
                acldefault('d', database_row.datdba)
            )
        ) AS acl
        LEFT JOIN pg_catalog.pg_roles AS role ON role.oid = acl.grantee
        WHERE database_row.datname = %s
        """,
        (database,),
    ).fetchall()
    existing_grantees = {str(row[0]) for row in rows}
    revoke_targets = (
        existing_grantees
        | set(_managed_role_names())
        | {"PUBLIC"}
    ) - {owner}
    for grantee in sorted(revoke_targets):
        target = sql.SQL("PUBLIC") if grantee == "PUBLIC" else sql.Identifier(grantee)
        cursor.execute(
            sql.SQL("REVOKE ALL PRIVILEGES ON DATABASE {} FROM {}").format(
                sql.Identifier(database),
                target,
            )
        )
    for role in granted_roles:
        cursor.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(database),
                sql.Identifier(role),
            )
        )


def _converge_role(
    cursor: psycopg.Cursor[object],
    *,
    role: str,
    role_secret: str,
    exists: bool,
) -> None:
    identifier = sql.Identifier(role)
    password = sql.Literal(role_secret)
    if not exists:
        cursor.execute(
            sql.SQL(f"CREATE ROLE {{}} {ROLE_SECURITY_ATTRIBUTES} PASSWORD {{}}").format(
                identifier,
                password,
            )
        )
    else:
        cursor.execute(
            sql.SQL(f"ALTER ROLE {{}} WITH {ROLE_SECURITY_ATTRIBUTES} PASSWORD {{}}").format(
                identifier,
                password,
            )
        )
    cursor.execute(sql.SQL("ALTER ROLE {} RESET ALL").format(identifier))


def _revoke_managed_role_memberships(
    cursor: psycopg.Cursor[object],
    managed_roles: Sequence[str],
) -> None:
    role_names = list(managed_roles)
    memberships = cursor.execute(
        """
        SELECT granted.rolname, member.rolname
        FROM pg_catalog.pg_auth_members AS membership
        JOIN pg_catalog.pg_roles AS granted
          ON granted.oid = membership.roleid
        JOIN pg_catalog.pg_roles AS member
          ON member.oid = membership.member
        WHERE granted.rolname = ANY(%s)
           OR member.rolname = ANY(%s)
        """,
        (role_names, role_names),
    ).fetchall()
    for granted_role, member_role in sorted(
        {(str(row[0]), str(row[1])) for row in memberships}
    ):
        cursor.execute(
            sql.SQL("REVOKE {} FROM {}").format(
                sql.Identifier(granted_role),
                sql.Identifier(member_role),
            )
        )


def _ensure_secret(service: str, account: str) -> str:
    existing = keyring.get_password(service, account)
    if existing:
        return existing
    alphabet = string.ascii_letters + string.digits + "-_!@#%"
    value = "H!" + "".join(secrets.choice(alphabet) for _ in range(38)) + "9z"
    keyring.set_password(service, account, value)
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="provision-halpha-databases")
    parser.parse_args(argv)
    require_repository_runtime()
    require_win_vault_backend(keyring.get_keyring())
    superuser_secret = keyring.get_password(*SUPERUSER_REFERENCE)
    if not superuser_secret:
        raise RuntimeError("POSTGRESQL_SUPERUSER_REFERENCE_MISSING")

    role_secrets: dict[str, str] = {}
    for environment, settings in ENVIRONMENTS.items():
        for kind in ROLE_KINDS_BY_ENVIRONMENT[environment]:
            role = _role_name(environment, kind)
            role_secrets[role] = _ensure_secret(
                *_vault_reference(settings["vault_profile"], kind)
            )

    with psycopg.connect(
        host="127.0.0.1",
        port=5432,
        dbname="postgres",
        user="postgres",
        password=superuser_secret,
        autocommit=True,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT rolname FROM pg_roles")
            existing_roles = {row[0] for row in cursor.fetchall()}
            for role, role_secret in sorted(role_secrets.items()):
                _converge_role(
                    cursor,
                    role=role,
                    role_secret=role_secret,
                    exists=role in existing_roles,
                )
            _revoke_managed_role_memberships(cursor, _managed_role_names())

            cursor.execute("SELECT datname FROM pg_database")
            existing_databases = {row[0] for row in cursor.fetchall()}
            for environment, settings in ENVIRONMENTS.items():
                database = settings["database"]
                migration_role = _role_name(environment, "migration")
                if database not in existing_databases:
                    cursor.execute(
                        sql.SQL(
                            "CREATE DATABASE {} OWNER {} TEMPLATE template0 ENCODING 'UTF8' LC_COLLATE 'C' LC_CTYPE 'C'"
                        ).format(sql.Identifier(database), sql.Identifier(migration_role))
                    )
                cursor.execute(
                    sql.SQL("ALTER DATABASE {} OWNER TO {}").format(
                        sql.Identifier(database), sql.Identifier(migration_role)
                    )
                )
                granted_roles, _ = _database_access_roles(environment)
                _converge_database_acl(
                    cursor,
                    database=database,
                    owner=migration_role,
                    granted_roles=granted_roles,
                )

    superuser_secret = None
    role_secrets.clear()
    print(
        '{"status":"PROVISIONED","databases":['
        '"halpha_demo","halpha_live_copy","halpha_live_personal"],'
        '"roles":{"demo":["app","executor","migration","backup"],'
        '"live_copy":["app","app_reader","executor","migration","backup"],'
        '"live_personal":["app","app_reader","executor","migration","backup"]},'
        '"secret_storage":"WINVAULT_REFERENCE_ONLY"}'
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
