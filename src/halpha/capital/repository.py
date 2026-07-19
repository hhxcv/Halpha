"""Persistence for the small set of stop facts consumed by CAP checks."""

from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from halpha.capital.models import StopStateVersion


class CapitalConflict(RuntimeError):
    """A requested current capital fact is missing or conflicting."""


class PostgreSQLCapitalRepository:
    def __init__(self, connection: Connection[Any], environment_id: str) -> None:
        self._connection = connection
        self._environment_id = environment_id

    def lock_current_stop_states(
        self,
        *,
        account_ref: str,
        activation_id: str,
    ) -> tuple[StopStateVersion, ...]:
        rows = self._connection.execute(
            """
            SELECT stop_state_version_id, environment_id, environment_kind,
                   authority_class, account_ref, activation_id, version,
                   stopped_categories, reason, source, started_at,
                   loss_latch_digest, release_rules, content_digest
            FROM halpha.stop_state_version
            WHERE environment_id = %s AND account_ref = %s
              AND (activation_id IS NULL OR activation_id = %s)
            ORDER BY activation_id NULLS FIRST, version DESC
            FOR UPDATE
            """,
            (self._environment_id, account_ref, activation_id),
        ).fetchall()
        latest: dict[str, StopStateVersion] = {}
        for row in rows:
            state = StopStateVersion(
                stop_state_version_id=str(row[0]),
                environment_id=str(row[1]),
                environment_kind=str(row[2]),
                authority_class=str(row[3]),
                account_ref=str(row[4]),
                activation_id=str(row[5]) if row[5] is not None else None,
                version=int(row[6]),
                stopped_categories=frozenset(row[7]),
                reason=str(row[8]),
                source=str(row[9]),
                started_at=row[10],
                loss_latch_digest=str(row[11]) if row[11] is not None else None,
                release_rules=dict(row[12]),
                content_digest=str(row[13]),
            )
            scope_key = state.activation_id or "ACCOUNT"
            latest.setdefault(scope_key, state)
        return tuple(latest[key] for key in sorted(latest))

    def insert_stop_state(self, state: StopStateVersion) -> None:
        self._connection.execute(
            """
            INSERT INTO halpha.stop_state_version (
                stop_state_version_id, environment_id, environment_kind,
                authority_class, account_ref, activation_id, version,
                stopped_categories, reason, source, started_at,
                loss_latch_digest, release_rules, content_digest
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                state.stop_state_version_id,
                state.environment_id,
                state.environment_kind.value,
                state.authority_class.value,
                state.account_ref,
                state.activation_id,
                state.version,
                sorted(item.value for item in state.stopped_categories),
                state.reason,
                state.source,
                state.started_at,
                state.loss_latch_digest,
                Jsonb(state.release_rules),
                state.content_digest,
            ),
        )
