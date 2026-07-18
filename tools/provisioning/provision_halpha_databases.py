"""Provision isolated DEMO/LIVE databases and SCRAM roles through WinVault."""

from __future__ import annotations

import secrets
import string

import keyring
import psycopg
from psycopg import sql

from halpha.runtime_identity import require_repository_runtime
from halpha.winvault import require_win_vault_backend


SUPERUSER_REFERENCE = ("Halpha/PostgreSQL/Instance", "postgres_superuser")
ENVIRONMENTS = {
    "demo": {
        "database": "halpha_demo",
        "vault_profile": "BINANCE_DEMO",
    },
    "live": {
        "database": "halpha_live",
        "vault_profile": "BINANCE_LIVE",
    },
}
ROLE_KINDS = ("app", "executor", "migration", "backup")


def _role_name(environment: str, kind: str) -> str:
    return f"halpha_{environment}_{kind}"


def _vault_reference(profile: str, kind: str) -> tuple[str, str]:
    return (f"Halpha/PostgreSQL/{profile}/{kind.title()}", "scram_password")


def _ensure_secret(service: str, account: str) -> str:
    existing = keyring.get_password(service, account)
    if existing:
        return existing
    alphabet = string.ascii_letters + string.digits + "-_!@#%"
    value = "H!" + "".join(secrets.choice(alphabet) for _ in range(38)) + "9z"
    keyring.set_password(service, account, value)
    return value


def main() -> int:
    require_repository_runtime()
    require_win_vault_backend(keyring.get_keyring())
    superuser_secret = keyring.get_password(*SUPERUSER_REFERENCE)
    if not superuser_secret:
        raise RuntimeError("POSTGRESQL_SUPERUSER_REFERENCE_MISSING")

    role_secrets: dict[str, str] = {}
    for environment, settings in ENVIRONMENTS.items():
        for kind in ROLE_KINDS:
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
                identifier = sql.Identifier(role)
                password = sql.Literal(role_secret)
                if role not in existing_roles:
                    cursor.execute(
                        sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD {}").format(
                            identifier,
                            password,
                        )
                    )
                else:
                    cursor.execute(
                        sql.SQL("ALTER ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD {}").format(
                            identifier,
                            password,
                        )
                    )

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
                cursor.execute(sql.SQL("REVOKE CONNECT ON DATABASE {} FROM PUBLIC").format(sql.Identifier(database)))
                for kind in ROLE_KINDS:
                    cursor.execute(
                        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                            sql.Identifier(database),
                            sql.Identifier(_role_name(environment, kind)),
                        )
                    )

    superuser_secret = None
    role_secrets.clear()
    print(
        '{"status":"PROVISIONED","databases":["halpha_demo","halpha_live"],'
        '"roles_per_database":["app","executor","migration","backup"],'
        '"secret_storage":"WINVAULT_REFERENCE_ONLY"}'
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
