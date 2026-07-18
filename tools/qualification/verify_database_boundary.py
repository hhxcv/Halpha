"""Verify the target-host PostgreSQL schema and least-privilege role boundary."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from typing import Any
from uuid import uuid4

import keyring
import psycopg
from psycopg import errors
from pydantic import SecretStr

from halpha.app.notifications import PostgreSQLNotificationRepository
from halpha.database.record_families import PRODUCT_RECORD_FAMILIES
from halpha.runtime_identity import require_repository_runtime
from halpha.winvault import require_win_vault_backend


ENVIRONMENTS = {
    "demo": {"database": "halpha_demo", "profile": "BINANCE_DEMO", "kind": "DEMO"},
    "live": {"database": "halpha_live", "profile": "BINANCE_LIVE", "kind": "LIVE"},
}
ROLE_KINDS = ("app", "executor", "migration", "backup")
HEAD = "20260717_0003"


def _migration_cycle(database: str) -> dict[str, Any]:
    results: dict[str, int] = {}
    for operation, target in (("downgrade", "base"), ("upgrade", "head")):
        process = subprocess.run(
            (
                sys.executable,
                "-m",
                "halpha.database.migrate",
                database,
                operation,
                target,
            ),
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        results[operation] = int(process.returncode)
    return {
        "downgrade_target": "base",
        "downgrade_returncode": results["downgrade"],
        "upgrade_target": "head",
        "upgrade_returncode": results["upgrade"],
    }


def _reference(profile: str, kind: str) -> tuple[str, str]:
    return (f"Halpha/PostgreSQL/{profile}/{kind.title()}", "scram_password")


def _connect(environment: str, kind: str, *, database: str | None = None) -> psycopg.Connection:
    settings = ENVIRONMENTS[environment]
    secret = keyring.get_password(*_reference(settings["profile"], kind))
    if not secret:
        raise RuntimeError(f"DATABASE_ROLE_REFERENCE_MISSING environment={environment} role={kind}")
    try:
        return psycopg.connect(
            host="127.0.0.1",
            port=5432,
            dbname=database or settings["database"],
            user=f"halpha_{environment}_{kind}",
            password=secret,
        )
    finally:
        secret = None


def _actual_write_rejected(connection: psycopg.Connection, table: str) -> bool:
    try:
        with connection.transaction():
            connection.execute(f"INSERT INTO halpha.{table} DEFAULT VALUES")
    except errors.InsufficientPrivilege:
        return True
    return False


def _notification_outbox_lifecycle(environment: str) -> dict[str, Any]:
    settings = ENVIRONMENTS[environment]
    environment_id = f"qualification-{environment}-notification"
    notification_id = uuid4()
    now = datetime.now(UTC)
    secret = keyring.get_password(*_reference(settings["profile"], "app"))
    if not secret:
        raise RuntimeError(
            f"DATABASE_ROLE_REFERENCE_MISSING environment={environment} role=app"
        )
    repository = PostgreSQLNotificationRepository(
        database_name=settings["database"],
        environment_id=environment_id,
        password=SecretStr(secret),
    )
    secret = None
    with _connect(environment, "app") as app:
        app.execute(
            """
            INSERT INTO halpha.notification (
                notification_id, environment_id, source_identity,
                source_business_time, recipient_route_ref, state,
                state_version, attempt_count, claim_version, next_attempt_at,
                content_digest, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, 'owner-primary-email', 'PENDING',
                      1, 0, 1, NULL, %s, %s, %s)
            """,
            (
                notification_id,
                environment_id,
                f"qualification:{notification_id}:v1",
                now,
                "1" * 64,
                now,
                now,
            ),
        )
    try:
        first = repository.claim_due(now=now)
        if first is None:
            raise RuntimeError("NOTIFICATION_QUALIFICATION_INITIAL_CLAIM_MISSING")
        repository.record_failure(
            first,
            failed_at=now,
            retry_after_seconds=60,
            abandon=False,
        )
        retry_blocked_until_due = repository.claim_due(now=now) is None
        second = repository.claim_due(now=now + timedelta(seconds=61))
        if second is None:
            raise RuntimeError("NOTIFICATION_QUALIFICATION_RETRY_CLAIM_MISSING")
        repository.mark_delivered(
            second,
            delivered_at=now + timedelta(seconds=61),
        )
        with _connect(environment, "app") as app:
            final = app.execute(
                """
                SELECT state, state_version, attempt_count, claim_version,
                       next_attempt_at IS NULL
                FROM halpha.notification
                WHERE environment_id = %s AND notification_id = %s
                """,
                (environment_id, notification_id),
            ).fetchone()
        if final is None:
            raise RuntimeError("NOTIFICATION_QUALIFICATION_FINAL_ROW_MISSING")
        return {
            "initial_claim_version": first.claim_version,
            "retry_blocked_until_due": retry_blocked_until_due,
            "retry_attempt_count": second.attempt_count,
            "retry_claim_version": second.claim_version,
            "final_state": str(final[0]),
            "final_state_version": int(final[1]),
            "final_attempt_count": int(final[2]),
            "final_claim_version": int(final[3]),
            "final_next_attempt_cleared": bool(final[4]),
        }
    finally:
        with _connect(environment, "app") as app:
            app.execute(
                "DELETE FROM halpha.notification "
                "WHERE environment_id = %s AND notification_id = %s",
                (environment_id, notification_id),
            )


def _capital_limit_check_rejected(
    connection: psycopg.Connection,
    *,
    environment_kind: str,
    authority_class: str,
) -> bool:
    try:
        with connection.transaction():
            connection.execute(
                "INSERT INTO halpha.account_capital_limit_version "
                "(capital_limit_version_id, environment_id, environment_kind, authority_class, "
                "account_ref, quote_asset, version, effective_at, max_margin, max_notional, "
                "max_allowed_loss, max_action_notional, scope, content_digest) "
                "VALUES (%s, %s, %s, %s, 'qualification-only', 'USDT', 1, now(), 1, 1, 1, 1, "
                "'{}'::jsonb, %s)",
                (
                    uuid4(),
                    f"qualification-{environment_kind.lower()}",
                    environment_kind,
                    authority_class,
                    "0" * 64,
                ),
            )
    except errors.CheckViolation:
        return True
    return False


def _inspect_environment(environment: str) -> dict[str, Any]:
    settings = ENVIRONMENTS[environment]
    with _connect(environment, "migration") as migration:
        tables = [
            row[0]
            for row in migration.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'halpha' AND table_type = 'BASE TABLE' ORDER BY table_name"
            ).fetchall()
        ]
        revision = migration.execute(
            "SELECT version_num FROM halpha_meta.alembic_version"
        ).fetchone()[0]
        environment_constraints = {
            row[0]: row[1]
            for row in migration.execute(
                "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE connamespace = 'halpha'::regnamespace "
                "AND conname LIKE 'ck_%_database_environment' ORDER BY conname"
            ).fetchall()
        }
        public_create = migration.execute(
            "SELECT has_schema_privilege('public', 'public', 'CREATE')"
        ).fetchone()[0]
        opposite_kind = "LIVE" if settings["kind"] == "DEMO" else "DEMO"
        opposite_authority = (
            "LIVE_REAL_CAPITAL" if opposite_kind == "LIVE" else "DEMO_VALIDATION"
        )
        database_environment_write_rejected = _capital_limit_check_rejected(
            migration,
            environment_kind=opposite_kind,
            authority_class=opposite_authority,
        )
        authority_pair_write_rejected = _capital_limit_check_rejected(
            migration,
            environment_kind=settings["kind"],
            authority_class=(
                "LIVE_REAL_CAPITAL"
                if settings["kind"] == "DEMO"
                else "DEMO_VALIDATION"
            ),
        )

    with _connect(environment, "app") as app:
        app_privileges = {
            "command_insert": app.execute(
                "SELECT has_table_privilege(current_user, 'halpha.command', 'INSERT')"
            ).fetchone()[0],
            "execution_action_insert": app.execute(
                "SELECT has_table_privilege(current_user, 'halpha.execution_action', 'INSERT')"
            ).fetchone()[0],
            "venue_fact_insert": app.execute(
                "SELECT has_table_privilege(current_user, 'halpha.venue_fact', 'INSERT')"
            ).fetchone()[0],
            "execution_action_actual_write_rejected": _actual_write_rejected(
                app, "execution_action"
            ),
            "notification_outbox": _notification_outbox_lifecycle(environment),
        }

    with _connect(environment, "executor") as executor:
        executor_privileges = {
            "execution_action_insert": executor.execute(
                "SELECT has_table_privilege(current_user, 'halpha.execution_action', 'INSERT')"
            ).fetchone()[0],
            "venue_fact_insert": executor.execute(
                "SELECT has_table_privilege(current_user, 'halpha.venue_fact', 'INSERT')"
            ).fetchone()[0],
            "command_insert": executor.execute(
                "SELECT has_table_privilege(current_user, 'halpha.command', 'INSERT')"
            ).fetchone()[0],
            "trade_plan_version_insert": executor.execute(
                "SELECT has_table_privilege(current_user, 'halpha.trade_plan_version', 'INSERT')"
            ).fetchone()[0],
            "command_actual_write_rejected": _actual_write_rejected(executor, "command"),
        }

    with _connect(environment, "backup") as backup:
        backup_privileges = {
            "all_product_tables_select": all(
                backup.execute(
                    "SELECT has_table_privilege(current_user, %s, 'SELECT')",
                    (f"halpha.{table}",),
                ).fetchone()[0]
                for table in PRODUCT_RECORD_FAMILIES
            ),
            "any_product_table_insert": any(
                backup.execute(
                    "SELECT has_table_privilege(current_user, %s, 'INSERT')",
                    (f"halpha.{table}",),
                ).fetchone()[0]
                for table in PRODUCT_RECORD_FAMILIES
            ),
            "task_actual_write_rejected": _actual_write_rejected(backup, "task"),
            "migration_metadata_select": backup.execute(
                "SELECT has_table_privilege(current_user, 'halpha_meta.alembic_version', 'SELECT')"
            ).fetchone()[0],
        }

    expected_constraint_fragment = f"= '{settings['kind']}'::text"
    return {
        "database": settings["database"],
        "revision": revision,
        "product_tables": tables,
        "product_table_count": len(tables),
        "environment_constraint_count": len(environment_constraints),
        "environment_constraints_match": all(
            expected_constraint_fragment in definition
            for definition in environment_constraints.values()
        ),
        "database_environment_write_rejected": database_environment_write_rejected,
        "authority_pair_write_rejected": authority_pair_write_rejected,
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
    if any(
        cycle != {
            "downgrade_target": "base",
            "downgrade_returncode": 0,
            "upgrade_target": "head",
            "upgrade_returncode": 0,
        }
        for cycle in evidence["migration_cycles"].values()
    ):
        return False
    expected_tables = sorted(PRODUCT_RECORD_FAMILIES)
    for environment in ("demo", "live"):
        result = evidence["environments"][environment]
        if result["revision"] != HEAD or result["product_tables"] != expected_tables:
            return False
        if result["product_table_count"] != 16 or result["environment_constraint_count"] != 6:
            return False
        if (
            not result["environment_constraints_match"]
            or not result["database_environment_write_rejected"]
            or not result["authority_pair_write_rejected"]
            or result["public_schema_create"]
        ):
            return False
        notification_outbox = result["app"]["notification_outbox"]
        app_boundary = {
            key: value
            for key, value in result["app"].items()
            if key != "notification_outbox"
        }
        if app_boundary != {
            "command_insert": True,
            "execution_action_insert": False,
            "venue_fact_insert": False,
            "execution_action_actual_write_rejected": True,
        }:
            return False
        if notification_outbox != {
            "initial_claim_version": 2,
            "retry_blocked_until_due": True,
            "retry_attempt_count": 1,
            "retry_claim_version": 3,
            "final_state": "DELIVERED",
            "final_state_version": 3,
            "final_attempt_count": 1,
            "final_claim_version": 3,
            "final_next_attempt_cleared": True,
        }:
            return False
        if result["executor"] != {
            "execution_action_insert": True,
            "venue_fact_insert": True,
            "command_insert": False,
            "trade_plan_version_insert": False,
            "command_actual_write_rejected": True,
        }:
            return False
        if result["backup"] != {
            "all_product_tables_select": True,
            "any_product_table_insert": False,
            "task_actual_write_rejected": True,
            "migration_metadata_select": True,
        }:
            return False
    return bool(evidence["cross_database_demo_app_to_live_rejected"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    runtime = require_repository_runtime()
    require_win_vault_backend(keyring.get_keyring())

    evidence: dict[str, Any] = {
        "schema_version": 1,
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "runtime": {
            "python_version": runtime.python_version,
            "executable": runtime.executable,
        },
        "postgresql": {
            "host": "127.0.0.1",
            "port": 5432,
            "secret_transport": "IN_MEMORY_KEYRING_TO_DRIVER",
        },
        "migration_cycles": {
            environment: _migration_cycle(settings["database"])
            for environment, settings in ENVIRONMENTS.items()
        },
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
        temporary = args.output.with_suffix(f"{args.output.suffix}.tmp")
        temporary.write_text(rendered, encoding="utf-8")
        temporary.replace(args.output)
    print(rendered, end="")
    return 0 if evidence["status"] == "QUALIFIED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
