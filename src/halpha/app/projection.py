"""Read-only PostgreSQL projections used by the local owner workbench."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import psycopg
from pydantic import SecretStr

from halpha.product_build import (
    EXECUTOR_READY_APPLICATION_NAME_PREFIX,
    EXECUTOR_STARTING_APPLICATION_NAME,
    executor_ready_application_name,
)


class ProjectionUnavailable(RuntimeError):
    """Sanitized database-unavailable result for the interaction layer."""


class WorkbenchProjection(Protocol):
    def overview(self) -> dict[str, Any]: ...

    def availability(self) -> dict[str, Any]: ...

    def operations(self) -> dict[str, Any]: ...

    def executor_status(self, product_build_id: str) -> dict[str, Any]: ...


def _executor_status_from_application_names(
    application_names: tuple[str, ...],
    *,
    product_build_id: str,
) -> tuple[str, bool | None]:
    expected = executor_ready_application_name(product_build_id)
    names = tuple(name for name in application_names if name)
    if names == (expected,):
        return "READY", True
    if len(names) > 1:
        return "AMBIGUOUS", None
    if names == (EXECUTOR_STARTING_APPLICATION_NAME,):
        return "STARTING", None
    if len(names) == 1 and names[0].startswith(
        EXECUTOR_READY_APPLICATION_NAME_PREFIX
    ):
        return "BUILD_MISMATCH", False
    if not names:
        return "UNAVAILABLE", None
    return "UNKNOWN", None


@dataclass(frozen=True, repr=False)
class PostgreSQLWorkbenchProjection:
    database_name: str
    password: SecretStr
    environment_id: str
    host: str = "127.0.0.1"
    port: int = 5432

    @property
    def role_name(self) -> str:
        return f"{self.database_name}_app"

    def _connect(self) -> psycopg.Connection[Any]:
        try:
            return psycopg.connect(
                host=self.host,
                port=self.port,
                dbname=self.database_name,
                user=self.role_name,
                password=self.password.get_secret_value(),
                connect_timeout=2,
                autocommit=True,
            )
        except Exception as exc:
            raise ProjectionUnavailable(
                f"DATABASE_UNAVAILABLE type={type(exc).__name__}"
            ) from None

    def overview(self) -> dict[str, Any]:
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        clock_timestamp() AT TIME ZONE 'UTC',
                        (SELECT count(*) FROM halpha.plan_activation
                         WHERE environment_id = %s AND lifecycle <> 'COMPLETED'),
                        current_database(),
                        current_user
                    """,
                    (self.environment_id,),
                )
                row = cursor.fetchone()
        except ProjectionUnavailable:
            raise
        except Exception as exc:
            raise ProjectionUnavailable(
                f"DATABASE_PROJECTION_FAILED type={type(exc).__name__}"
            ) from None
        if row is None:
            raise ProjectionUnavailable("DATABASE_PROJECTION_EMPTY")
        cutoff = row[0]
        if isinstance(cutoff, datetime):
            cutoff = cutoff.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")
        return {
            "database_available": True,
            "server_fact_cutoff": str(cutoff),
            "open_activation_count": int(row[1]),
            "database_name": str(row[2]),
            "database_role": str(row[3]),
        }

    def availability(self) -> dict[str, Any]:
        try:
            summary = self.overview()
        except ProjectionUnavailable:
            return {
                "database_available": False,
                "reason_code": "DATABASE_UNAVAILABLE",
                "server_fact_cutoff": None,
            }
        return {
            "database_available": True,
            "reason_code": None,
            "server_fact_cutoff": summary["server_fact_cutoff"],
        }

    def executor_status(self, product_build_id: str) -> dict[str, Any]:
        """Project the current Executor session without adding a heartbeat store."""

        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT clock_timestamp() AT TIME ZONE 'UTC', application_name
                    FROM pg_stat_activity
                    WHERE datname = current_database()
                      AND usename = %s
                      AND (
                        application_name = %s
                        OR application_name LIKE %s
                      )
                    ORDER BY pid
                    """,
                    (
                        f"{self.database_name}_executor",
                        EXECUTOR_STARTING_APPLICATION_NAME,
                        f"{EXECUTOR_READY_APPLICATION_NAME_PREFIX}%",
                    ),
                )
                rows = cursor.fetchall()
                checked_at = cursor.execute(
                    "SELECT clock_timestamp() AT TIME ZONE 'UTC'"
                ).fetchone()[0]
        except ProjectionUnavailable:
            raise
        except Exception as exc:
            raise ProjectionUnavailable(
                f"EXECUTOR_STATUS_FAILED type={type(exc).__name__}"
            ) from None
        status, consistent = _executor_status_from_application_names(
            tuple(str(row[1]) for row in rows),
            product_build_id=product_build_id,
        )
        if rows:
            checked_at = rows[-1][0]
        if isinstance(checked_at, datetime):
            checked_at = checked_at.replace(tzinfo=UTC).isoformat().replace(
                "+00:00", "Z"
            )
        return {
            "status": status,
            "checked_at": str(checked_at),
            "product_build_consistent": consistent,
        }

    def operations(self) -> dict[str, Any]:
        """Project the small authoritative fact set required by `/operations`."""

        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cutoff = cursor.execute(
                    "SELECT clock_timestamp() AT TIME ZONE 'UTC'"
                ).fetchone()[0]
                activation_rows = cursor.execute(
                    """
                    SELECT a.activation_id, a.account_ref, a.instrument_ref, a.direction,
                           a.lifecycle, a.run_state, a.pause_reason, a.state_version,
                           a.protection_state, a.latest_venue_cutoff, a.updated_at
                    FROM halpha.plan_activation AS a
                    WHERE a.environment_id = %s AND a.lifecycle <> 'COMPLETED'
                    ORDER BY a.updated_at DESC, a.activation_id
                    """,
                    (self.environment_id,),
                ).fetchall()
                activations: list[dict[str, Any]] = []
                for row in activation_rows:
                    activation_id = str(row[0])
                    account_ref = str(row[1])
                    stop_rows = cursor.execute(
                        """
                        SELECT stopped_categories
                        FROM (
                            SELECT DISTINCT ON (
                                CASE WHEN activation_id IS NULL
                                     THEN 'ACCOUNT'
                                     ELSE activation_id::text END
                            ) activation_id, stopped_categories, version
                            FROM halpha.stop_state_version
                            WHERE environment_id = %s
                              AND account_ref = %s
                              AND (activation_id IS NULL OR activation_id = %s)
                            ORDER BY CASE WHEN activation_id IS NULL
                                          THEN 'ACCOUNT'
                                          ELSE activation_id::text END,
                                     version DESC
                        ) AS current_stops
                        """,
                        (self.environment_id, account_ref, row[0]),
                    ).fetchall()
                    stopped_categories = {
                        str(category)
                        for stop_row in stop_rows
                        for category in stop_row[0]
                    }
                    activations.append(
                        {
                            "activation_id": activation_id,
                            "account_ref": account_ref,
                            "instrument_ref": str(row[2]),
                            "direction": str(row[3]),
                            "lifecycle": str(row[4]),
                            "run_state": str(row[5]),
                            "pause_reason": str(row[6]) if row[6] is not None else None,
                            "state_version": int(row[7]),
                            "protection_state": str(row[8]),
                            "latest_venue_cutoff": (
                                row[9].isoformat() if row[9] is not None else None
                            ),
                            "updated_at": row[10].isoformat(),
                            "stopped_categories": sorted(stopped_categories),
                        }
                    )
        except ProjectionUnavailable:
            raise
        except Exception as exc:
            raise ProjectionUnavailable(
                f"OPERATIONS_PROJECTION_FAILED type={type(exc).__name__}"
            ) from None
        if isinstance(cutoff, datetime):
            cutoff = cutoff.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")
        return {
            "database_available": True,
            "server_fact_cutoff": str(cutoff),
            "activations": activations,
        }
