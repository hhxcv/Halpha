"""Read-only PostgreSQL projections used by the local owner workbench."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import psycopg
from pydantic import SecretStr


class ProjectionUnavailable(RuntimeError):
    """Sanitized database-unavailable result for the interaction layer."""


class WorkbenchProjection(Protocol):
    def overview(self) -> dict[str, Any]: ...

    def availability(self) -> dict[str, Any]: ...

    def operations(self) -> dict[str, Any]: ...


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
                           a.protection_state, a.latest_venue_cutoff, a.updated_at,
                           v.max_margin, v.max_notional, v.max_allowed_loss,
                           v.terms, a.rule_state
                    FROM halpha.plan_activation AS a
                    JOIN halpha.trade_plan_version AS v
                      ON v.environment_id = a.environment_id
                     AND v.plan_version_id = a.plan_version_ref
                    WHERE a.environment_id = %s AND a.lifecycle <> 'COMPLETED'
                    ORDER BY a.updated_at DESC, a.activation_id
                    """,
                    (self.environment_id,),
                ).fetchall()
                activation_ids = [str(row[0]) for row in activation_rows]
                receipt_rows = []
                if activation_ids:
                    receipt_rows = cursor.execute(
                        """
                        SELECT c.target_ref, c.intent, c.submitted_at, r.receipt_id,
                               r.state, r.reason_code, r.updated_at
                        FROM halpha.command AS c
                        JOIN halpha.receipt AS r
                          ON r.environment_id = c.environment_id
                         AND r.command_id = c.command_id
                        WHERE c.target_kind = 'PLAN_ACTIVATION'
                          AND c.environment_id = %s
                          AND c.target_ref = ANY(%s)
                        ORDER BY r.updated_at DESC, r.receipt_id
                        LIMIT 50
                        """,
                        (self.environment_id, activation_ids),
                    ).fetchall()
                activations: list[dict[str, Any]] = []
                for row in activation_rows:
                    activation_id = str(row[0])
                    account_ref = str(row[1])
                    stop_rows = cursor.execute(
                        """
                        SELECT stopped_categories, reason, source, started_at
                        FROM (
                            SELECT DISTINCT ON (
                                CASE WHEN activation_id IS NULL
                                     THEN 'ACCOUNT'
                                     ELSE activation_id::text END
                            ) activation_id, stopped_categories, reason, source,
                              started_at, version
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
                    action_rows = cursor.execute(
                        """
                        SELECT action_kind, state, client_order_id, venue_order_refs,
                               unknown_reason, updated_at
                        FROM halpha.execution_action
                        WHERE environment_id = %s AND activation_id = %s
                        ORDER BY updated_at DESC, execution_action_id
                        LIMIT 20
                        """,
                        (self.environment_id, row[0]),
                    ).fetchall()
                    venue_rows = cursor.execute(
                        """
                        SELECT kind, source_object_id, cutoff, source_class
                        FROM halpha.venue_fact
                        WHERE environment_id = %s AND activation_ref = %s
                          AND kind IN ('POSITION_STATE', 'ORDER_STATE')
                        ORDER BY cutoff DESC, venue_fact_id
                        LIMIT 20
                        """,
                        (self.environment_id, row[0]),
                    ).fetchall()
                    stopped_categories = {
                        str(category)
                        for stop_row in stop_rows
                        for category in stop_row[0]
                    }
                    if "ALL_EXCHANGE_CHANGES" in stopped_categories:
                        stopped_categories.update(
                            {
                                "NEW_RISK",
                                "PROTECTION",
                                "RISK_REDUCTION_OR_ORDER_MANAGEMENT",
                            }
                        )
                    terms = dict(row[14])
                    rule_state = dict(row[15])
                    capital = rule_state.get("capital", {})
                    if not isinstance(capital, dict):
                        capital = {}
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
                            "max_margin": str(row[11]),
                            "max_notional": str(row[12]),
                            "max_allowed_loss": str(row[13]),
                            "activation_loss": str(capital.get("activation_loss", "0")),
                            "max_loss_reached": bool(capital.get("max_loss_reached")),
                            "plan_valid_until": str(terms.get("valid_until", "UNKNOWN")),
                            "quote_asset": "USDT",
                            "stopped_categories": sorted(stopped_categories),
                            "stop_evidence": [
                                {
                                    "reason": str(stop_row[1]),
                                    "source": str(stop_row[2]),
                                    "started_at": stop_row[3].isoformat(),
                                }
                                for stop_row in stop_rows
                            ],
                            "receipts": [
                                {
                                    "intent": str(receipt[1]),
                                    "submitted_at": receipt[2].isoformat(),
                                    "receipt_id": str(receipt[3]),
                                    "state": str(receipt[4]),
                                    "reason_code": (
                                        str(receipt[5]) if receipt[5] is not None else None
                                    ),
                                    "updated_at": receipt[6].isoformat(),
                                }
                                for receipt in receipt_rows
                                if str(receipt[0]) == activation_id
                            ],
                            "execution_actions": [
                                {
                                    "action_kind": str(action[0]),
                                    "state": str(action[1]),
                                    "client_order_id": (
                                        str(action[2]) if action[2] is not None else None
                                    ),
                                    "venue_order_refs": action[3],
                                    "unknown_reason": (
                                        str(action[4]) if action[4] is not None else None
                                    ),
                                    "updated_at": action[5].isoformat(),
                                }
                                for action in action_rows
                            ],
                            "venue_facts": [
                                {
                                    "kind": str(fact[0]),
                                    "source_object_id": (
                                        str(fact[1]) if fact[1] is not None else None
                                    ),
                                    "cutoff": fact[2].isoformat(),
                                    "source_class": str(fact[3]),
                                }
                                for fact in venue_rows
                            ],
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
