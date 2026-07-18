"""Qualify Notification abandonment and visible Task semantics on PostgreSQL."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any
from uuid import uuid4

import keyring
from pydantic import SecretStr


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from halpha.app.notifications import PostgreSQLNotificationRepository
from halpha.app.planning_api import PostgreSQLPlanningApi
from halpha.winvault import require_win_vault_backend
from tools.qualification.verify_b02_database_boundary import _connect


DEFAULT_OUTPUT = ROOT / "build/qualification/b04-notification-boundary.json"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _app_password() -> SecretStr:
    require_win_vault_backend(keyring.get_keyring())
    value = keyring.get_password(
        "Halpha/PostgreSQL/BINANCE_DEMO/App",
        "scram_password",
    )
    if not value:
        raise RuntimeError("DEMO_APP_DATABASE_REFERENCE_MISSING")
    try:
        return SecretStr(value)
    finally:
        value = None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    now = datetime.now(UTC)
    environment_id = f"qualification-b04-notification-{uuid4()}"
    account_ref = f"qualification-account-{uuid4()}"
    notification_id = uuid4()
    source_identity = f"qualification:{notification_id}:v1"
    source_digest = sha256(source_identity.encode("utf-8")).hexdigest()
    checks: dict[str, bool] = {}
    observations: dict[str, Any] = {}
    errors: list[str] = []
    password = _app_password()
    repository = PostgreSQLNotificationRepository(
        database_name="halpha_demo",
        environment_id=environment_id,
        password=password,
    )
    planning_api = PostgreSQLPlanningApi(
        database_name="halpha_demo",
        password=password,
        environment_id=environment_id,
        environment_kind="DEMO",
        authority_class="DEMO_VALIDATION",
        account_ref=account_ref,
        build_digest=None,
    )

    try:
        with _connect() as connection, connection.transaction():
            connection.execute(
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
                    source_identity,
                    now,
                    source_digest,
                    now,
                    now,
                ),
            )

        claim = repository.claim_due(now=now)
        if claim is None:
            raise RuntimeError("B04_NOTIFICATION_INITIAL_CLAIM_MISSING")
        repository.record_failure(
            claim,
            failed_at=now,
            retry_after_seconds=None,
            abandon=True,
        )

        tasks_before = planning_api.list_tasks()
        if len(tasks_before) != 1:
            raise RuntimeError("B04_NOTIFICATION_VISIBLE_TASK_COUNT_INVALID")
        task_before = tasks_before[0]
        expected_responsibility_key = (
            f"notification:{source_identity}:delivery-abandoned"
        )
        with _connect() as connection:
            notification = connection.execute(
                """
                SELECT state, state_version, attempt_count, task_ref
                FROM halpha.notification
                WHERE environment_id = %s AND notification_id = %s
                """,
                (environment_id, notification_id),
            ).fetchone()
            task_count = connection.execute(
                "SELECT count(*) FROM halpha.task WHERE environment_id = %s",
                (environment_id,),
            ).fetchone()[0]

        checks["abandoned_notification_forms_one_visible_task"] = (
            notification is not None
            and str(notification[0]) == "ABANDONED"
            and int(notification[1]) == 2
            and int(notification[2]) == 1
            and str(notification[3]) == task_before["task_id"]
            and int(task_count) == 1
            and task_before["responsibility_key"] == expected_responsibility_key
            and task_before["priority"] == "HIGH"
            and task_before["state"] == "OPEN"
            and task_before["source_kind"] == "NOTIFICATION"
            and task_before["source_ref"] == str(notification_id)
            and task_before["source_version"] == 2
            and task_before["source_digest"] == source_digest
        )

        checks["abandoned_notification_is_not_claimed_again"] = (
            repository.claim_due(now=now + timedelta(days=1)) is None
        )

        acknowledgement = planning_api.acknowledge_task(
            task_before["task_id"],
            expected_version=1,
            observed_at=now + timedelta(seconds=1),
        )
        tasks_after = planning_api.list_tasks()
        task_after = tasks_after[0]
        checks["acknowledgement_does_not_close_source_responsibility"] = (
            len(tasks_after) == 1
            and acknowledgement["state"] == "ACKNOWLEDGED"
            and acknowledgement["state_version"] == 2
            and acknowledgement["source_responsibility_changed"] is False
            and task_after["responsibility_key"]
            == task_before["responsibility_key"]
            and task_after["source_ref"] == task_before["source_ref"]
            and task_after["source_version"] == task_before["source_version"]
            and task_after["source_digest"] == task_before["source_digest"]
            and task_after["state"] == "ACKNOWLEDGED"
            and task_after["state_version"] == 2
            and task_after["content_digest"]
            == acknowledgement["content_digest"]
        )

        stale_rejected = False
        try:
            planning_api.acknowledge_task(
                task_before["task_id"],
                expected_version=1,
                observed_at=now + timedelta(seconds=2),
            )
        except ValueError as exc:
            stale_rejected = str(exc) == "VERSION_CONFLICT"
        checks["stale_acknowledgement_is_rejected_without_task_duplication"] = (
            stale_rejected and len(planning_api.list_tasks()) == 1
        )
        observations.update(
            {
                "notification_state": str(notification[0]),
                "task_state_after_acknowledgement": task_after["state"],
                "task_count": len(tasks_after),
                "record_family_delta": 0,
                "persistent_worker_delta": 0,
                "venue_write_performed": False,
            }
        )
    except Exception as exc:
        errors.append(
            f"B04_NOTIFICATION_BOUNDARY_FAILED:{type(exc).__name__}:{exc}"
        )
    finally:
        try:
            with _connect() as connection, connection.transaction():
                connection.execute(
                    "DELETE FROM halpha.notification WHERE environment_id = %s",
                    (environment_id,),
                )
                connection.execute(
                    "DELETE FROM halpha.task WHERE environment_id = %s",
                    (environment_id,),
                )
            with _connect() as connection:
                remaining = connection.execute(
                    """
                    SELECT
                      (SELECT count(*) FROM halpha.notification WHERE environment_id = %s),
                      (SELECT count(*) FROM halpha.task WHERE environment_id = %s)
                    """,
                    (environment_id, environment_id),
                ).fetchone()
            checks["qualification_records_cleaned"] = remaining == (0, 0)
        except Exception as exc:
            checks["qualification_records_cleaned"] = False
            errors.append(
                f"B04_NOTIFICATION_CLEANUP_FAILED:{type(exc).__name__}"
            )

    evidence: dict[str, Any] = {
        "stage": "B04_NOTIFICATION_BOUNDARY",
        "observed_at": datetime.now(UTC).isoformat(),
        "environment_kind": "DEMO",
        "authority_class": "DEMO_VALIDATION",
        "checks": checks,
        "observations": observations,
        "errors": errors,
        "venue_write_performed": False,
    }
    evidence["status"] = (
        "QUALIFIED" if checks and all(checks.values()) and not errors else "REJECTED"
    )
    evidence["evidence_digest"] = sha256(_canonical(evidence)).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if evidence["status"] == "QUALIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
