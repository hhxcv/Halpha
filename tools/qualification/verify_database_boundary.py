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

from halpha.database.record_families import PRODUCT_RECORD_FAMILIES
from halpha.runtime_identity import require_repository_runtime
from halpha.winvault import require_win_vault_backend


ENVIRONMENTS = {
    "demo": {"database": "halpha_demo", "profile": "BINANCE_DEMO", "kind": "DEMO"},
    "live": {"database": "halpha_live", "profile": "BINANCE_LIVE", "kind": "LIVE"},
}
HEAD = "20260723_0012"


def _reference(profile: str, role: str) -> tuple[str, str]:
    return (f"Halpha/PostgreSQL/{profile}/{role.title()}", "scram_password")


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


def _inspect_environment(environment: str) -> dict[str, Any]:
    settings = ENVIRONMENTS[environment]
    with _connect(environment, "migration") as migration:
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
        authority_constraints = [
            str(row[0])
            for row in migration.execute(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE connamespace = 'halpha'::regnamespace "
                "AND conname LIKE '%authority_pair%' ORDER BY conname"
            ).fetchall()
        ]
        public_create = bool(
            migration.execute(
                "SELECT has_schema_privilege('public', 'public', 'CREATE')"
            ).fetchone()[0]
        )

    with _connect(environment, "app") as app:
        app_privileges = {
            "command_insert": _privilege(app, "command", "INSERT"),
            "execution_action_insert": _privilege(app, "execution_action", "INSERT"),
            "venue_fact_insert": _privilege(app, "venue_fact", "INSERT"),
        }
    with _connect(environment, "executor") as executor:
        executor_privileges = {
            "command_insert": _privilege(executor, "command", "INSERT"),
            "execution_action_insert": _privilege(executor, "execution_action", "INSERT"),
            "venue_fact_insert": _privilege(executor, "venue_fact", "INSERT"),
            "trade_plan_version_insert": _privilege(
                executor, "trade_plan_version", "INSERT"
            ),
        }
    with _connect(environment, "backup") as backup:
        backup_privileges = {
            "all_product_tables_select": all(
                _privilege(backup, table, "SELECT") for table in PRODUCT_RECORD_FAMILIES
            ),
            "any_product_table_insert": any(
                _privilege(backup, table, "INSERT") for table in PRODUCT_RECORD_FAMILIES
            ),
        }

    return {
        "database": settings["database"],
        "revision": revision,
        "product_tables": tables,
        "authority_constraints_present": bool(authority_constraints),
        "public_schema_create": public_create,
        "app": app_privileges,
        "executor": executor_privileges,
        "backup": backup_privileges,
    }


def _cross_database_connect_rejected() -> bool:
    try:
        with _connect("demo", "app", database="halpha_live"):
            return False
    except psycopg.OperationalError as exc:
        if "permission denied for database" in str(exc):
            return True
        raise


def _qualified(evidence: dict[str, Any]) -> bool:
    expected_tables = sorted(PRODUCT_RECORD_FAMILIES)
    expected_app = {
        "command_insert": True,
        "execution_action_insert": False,
        "venue_fact_insert": False,
    }
    expected_executor = {
        "command_insert": False,
        "execution_action_insert": True,
        "venue_fact_insert": True,
        "trade_plan_version_insert": False,
    }
    expected_backup = {
        "all_product_tables_select": True,
        "any_product_table_insert": False,
    }
    for result in evidence["environments"].values():
        if (
            result["revision"] != HEAD
            or result["product_tables"] != expected_tables
            or not result["authority_constraints_present"]
            or result["public_schema_create"]
            or result["app"] != expected_app
            or result["executor"] != expected_executor
            or result["backup"] != expected_backup
        ):
            return False
    return bool(evidence["cross_database_demo_app_to_live_rejected"])


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
            for environment in ("demo", "live")
        },
        "cross_database_demo_app_to_live_rejected": _cross_database_connect_rejected(),
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
