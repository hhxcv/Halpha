"""The only PostgreSQL writers for EXE actions and append-only DAT facts."""

from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from halpha.venue_integration.models import ExecutionAction, VenueFact


class VenueIntegrationConflict(RuntimeError):
    pass


class PostgreSQLExecutionActionRepository:
    """EXE-private mutable repository shared by Demo and Live instances."""

    def __init__(self, connection: Connection[Any], environment_id: str) -> None:
        self._connection = connection
        self._environment_id = environment_id

    def insert(self, action: ExecutionAction) -> None:
        self._require_environment(action.environment_id)
        self._connection.execute(
            """
            INSERT INTO halpha.execution_action (
                execution_action_id, environment_id, environment_kind,
                authority_class, execution_profile_ref, account_ref,
                activation_id, plan_event_ref, source_identity, action_kind,
                action_class, action_terms, action_terms_digest,
                capital_decision_digest, client_order_id, cancel_target, state,
                state_version, state_digest, request_digest, call_started_at,
                call_completed_at, venue_order_refs, venue_fact_refs,
                unknown_reason, next_query_at, not_submitted_reason, protection_digest,
                closure_evidence_digest, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s
            )
            """,
            _action_values(action),
        )

    def get(self, execution_action_id: str, *, for_update: bool = False) -> ExecutionAction:
        suffix = " FOR UPDATE" if for_update else ""
        row = self._connection.execute(
            _ACTION_SELECT
            + " WHERE environment_id = %s AND execution_action_id = %s"
            + suffix,
            (self._environment_id, execution_action_id),
        ).fetchone()
        if row is None:
            raise VenueIntegrationConflict("EXECUTION_ACTION_NOT_FOUND")
        return _action_from_row(row)

    def find_by_source(
        self,
        *,
        activation_id: str,
        plan_event_ref: str,
        source_identity: str,
        action_kind: str,
    ) -> ExecutionAction | None:
        row = self._connection.execute(
            _ACTION_SELECT
            + """
              WHERE environment_id = %s AND activation_id = %s
                AND plan_event_ref = %s AND source_identity = %s
                AND action_kind = %s
            """,
            (
                self._environment_id,
                activation_id,
                plan_event_ref,
                source_identity,
                action_kind,
            ),
        ).fetchone()
        return None if row is None else _action_from_row(row)

    def find_order_action_by_client_id(
        self,
        client_order_id: str,
    ) -> ExecutionAction | None:
        row = self._connection.execute(
            _ACTION_SELECT
            + " WHERE environment_id = %s AND client_order_id = %s",
            (self._environment_id, client_order_id),
        ).fetchone()
        return None if row is None else _action_from_row(row)

    def find_open_cancel_for_target(
        self,
        client_order_id: str,
    ) -> ExecutionAction | None:
        row = self._connection.execute(
            _ACTION_SELECT
            + """
              WHERE environment_id = %s AND action_kind = 'CANCEL'
                AND cancel_target ->> 'client_order_id' = %s
                AND state IN ('SUBMITTING', 'UNKNOWN', 'OPEN')
              ORDER BY created_at DESC, execution_action_id DESC
              LIMIT 1
            """,
            (self._environment_id, client_order_id),
        ).fetchone()
        return None if row is None else _action_from_row(row)

    def list_for_activation(self, activation_id: str) -> tuple[ExecutionAction, ...]:
        rows = self._connection.execute(
            _ACTION_SELECT
            + " WHERE environment_id = %s AND activation_id = %s ORDER BY created_at, execution_action_id",
            (self._environment_id, activation_id),
        ).fetchall()
        return tuple(_action_from_row(row) for row in rows)

    def has_open_entry_responsibility(self, activation_id: str) -> bool:
        """Return whether an entry may still have changed venue or exposure."""

        row = self._connection.execute(
            """
            SELECT 1
            FROM halpha.execution_action
            WHERE environment_id = %s AND activation_id = %s
              AND action_kind = 'ENTRY'
              AND state NOT IN ('NOT_SUBMITTED', 'CLOSED', 'HANDED_OVER')
            LIMIT 1
            """,
            (self._environment_id, activation_id),
        ).fetchone()
        return row is not None

    def list_by_states(
        self,
        states: tuple[str, ...],
        *,
        for_update: bool = False,
    ) -> tuple[ExecutionAction, ...]:
        if not states:
            return ()
        suffix = " FOR UPDATE" if for_update else ""
        placeholders = ", ".join("%s" for _ in states)
        rows = self._connection.execute(
            _ACTION_SELECT
            + f"""
              WHERE environment_id = %s AND state IN ({placeholders})
              ORDER BY created_at, execution_action_id
            """
            + suffix,
            (self._environment_id, *states),
        ).fetchall()
        return tuple(_action_from_row(row) for row in rows)

    def lock_next_ready(self) -> ExecutionAction | None:
        row = self._connection.execute(
            _ACTION_SELECT
            + """
              WHERE environment_id = %s AND state = 'READY'
              ORDER BY created_at, execution_action_id
              FOR UPDATE SKIP LOCKED
              LIMIT 1
            """,
            (self._environment_id,),
        ).fetchone()
        return None if row is None else _action_from_row(row)

    def update(self, action: ExecutionAction, *, expected_version: int) -> None:
        self._require_environment(action.environment_id)
        cursor = self._connection.execute(
            """
            UPDATE halpha.execution_action
            SET capital_decision_digest = %s, state = %s, state_version = %s,
                state_digest = %s, request_digest = %s, call_started_at = %s,
                call_completed_at = %s, venue_order_refs = %s,
                venue_fact_refs = %s, unknown_reason = %s, next_query_at = %s,
                not_submitted_reason = %s,
                protection_digest = %s, closure_evidence_digest = %s,
                updated_at = %s
            WHERE environment_id = %s AND execution_action_id = %s
              AND state_version = %s
            """,
            (
                action.capital_decision_digest,
                action.state.value,
                action.state_version,
                action.state_digest,
                action.request_digest,
                action.call_started_at,
                action.call_completed_at,
                Jsonb(list(action.venue_order_refs)),
                Jsonb(list(action.venue_fact_refs)),
                action.unknown_reason,
                action.next_query_at,
                action.not_submitted_reason,
                action.protection_digest,
                action.closure_evidence_digest,
                action.updated_at,
                self._environment_id,
                action.execution_action_id,
                expected_version,
            ),
        )
        if cursor.rowcount != 1:
            raise VenueIntegrationConflict("EXECUTION_ACTION_VERSION_CONFLICT")

    def _require_environment(self, environment_id: str) -> None:
        if environment_id != self._environment_id:
            raise VenueIntegrationConflict("AUTHORIZATION_MISMATCH")


class PostgreSQLVenueFactRepository:
    """DAT's append-only repository; facts are never updated or deleted."""

    def __init__(self, connection: Connection[Any], environment_id: str) -> None:
        self._connection = connection
        self._environment_id = environment_id

    def insert(self, fact: VenueFact) -> None:
        if fact.environment_id != self._environment_id:
            raise VenueIntegrationConflict("AUTHORIZATION_MISMATCH")
        self._connection.execute(
            """
            INSERT INTO halpha.venue_fact (
                venue_fact_id, environment_id, venue_ref, account_ref,
                instrument_ref, kind, source_class, source_object_id,
                source_sequence, source_time, received_at, cutoff,
                schema_version, content_digest, payload, activation_ref,
                action_ref, attribution_digest, attribution_class,
                handover_command_ref, supersedes_ref, correction_reason,
                correction_evidence_refs, correction_effective_time,
                impact_scope, affected_reference_refs
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s
            ) ON CONFLICT (
                environment_id, kind, source_class, source_object_id,
                source_sequence, content_digest
            ) DO NOTHING
            """,
            (
                fact.venue_fact_id,
                fact.environment_id,
                fact.venue_ref,
                fact.account_ref,
                fact.instrument_ref,
                fact.kind.value,
                fact.source_class.value,
                fact.source_object_id,
                fact.source_sequence,
                fact.source_time,
                fact.received_at,
                fact.cutoff,
                fact.schema_version,
                fact.content_digest,
                Jsonb(fact.payload),
                fact.activation_ref,
                fact.action_ref,
                fact.attribution_digest,
                fact.attribution_class.value if fact.attribution_class else None,
                fact.handover_command_ref,
                fact.supersedes_ref,
                fact.correction_reason,
                Jsonb(list(fact.correction_evidence_refs))
                if fact.correction_evidence_refs is not None
                else None,
                fact.correction_effective_time,
                Jsonb(fact.impact_scope) if fact.impact_scope is not None else None,
                Jsonb(list(fact.affected_reference_refs))
                if fact.affected_reference_refs is not None
                else None,
            ),
        )

    def find_by_source(self, fact: VenueFact) -> VenueFact | None:
        row = self._connection.execute(
            _FACT_SELECT
            + """
              WHERE environment_id = %s AND kind = %s AND source_class = %s
                AND source_object_id = %s AND source_sequence = %s
              ORDER BY received_at, venue_fact_id
              LIMIT 1
            """,
            (
                self._environment_id,
                fact.kind.value,
                fact.source_class.value,
                fact.source_object_id,
                fact.source_sequence,
            ),
        ).fetchone()
        return None if row is None else _fact_from_row(row)

    def get(self, venue_fact_id: str) -> VenueFact:
        row = self._connection.execute(
            _FACT_SELECT + " WHERE environment_id = %s AND venue_fact_id = %s",
            (self._environment_id, venue_fact_id),
        ).fetchone()
        if row is None:
            raise VenueIntegrationConflict("VENUE_FACT_NOT_FOUND")
        return _fact_from_row(row)

    def list_for_action(self, execution_action_id: str) -> tuple[VenueFact, ...]:
        rows = self._connection.execute(
            _FACT_SELECT
            + " WHERE environment_id = %s AND action_ref = %s ORDER BY cutoff, received_at, venue_fact_id",
            (self._environment_id, execution_action_id),
        ).fetchall()
        return tuple(_fact_from_row(row) for row in rows)


_ACTION_SELECT = """
SELECT execution_action_id, environment_id, environment_kind, authority_class,
       execution_profile_ref, account_ref, activation_id, plan_event_ref,
       source_identity, action_kind, action_class, action_terms,
       action_terms_digest, capital_decision_digest, client_order_id,
       cancel_target, state, state_version, state_digest, request_digest,
       call_started_at, call_completed_at, venue_order_refs, venue_fact_refs,
       unknown_reason, next_query_at, not_submitted_reason, protection_digest,
       closure_evidence_digest, created_at, updated_at
FROM halpha.execution_action
"""


def _action_values(action: ExecutionAction) -> tuple[Any, ...]:
    return (
        action.execution_action_id,
        action.environment_id,
        action.environment_kind.value,
        action.authority_class.value,
        action.execution_profile_ref.value,
        action.account_ref,
        action.activation_id,
        action.plan_event_ref,
        action.source_identity,
        action.action_kind.value,
        action.action_class.value,
        Jsonb(action.action_terms),
        action.action_terms_digest,
        action.capital_decision_digest,
        action.client_order_id,
        Jsonb(action.cancel_target) if action.cancel_target is not None else None,
        action.state.value,
        action.state_version,
        action.state_digest,
        action.request_digest,
        action.call_started_at,
        action.call_completed_at,
        Jsonb(list(action.venue_order_refs)),
        Jsonb(list(action.venue_fact_refs)),
        action.unknown_reason,
        action.next_query_at,
        action.not_submitted_reason,
        action.protection_digest,
        action.closure_evidence_digest,
        action.created_at,
        action.updated_at,
    )


def _action_from_row(row: tuple[Any, ...]) -> ExecutionAction:
    return ExecutionAction(
        execution_action_id=str(row[0]),
        environment_id=str(row[1]),
        environment_kind=str(row[2]),
        authority_class=str(row[3]),
        execution_profile_ref=str(row[4]),
        account_ref=str(row[5]),
        activation_id=str(row[6]),
        plan_event_ref=str(row[7]),
        source_identity=str(row[8]),
        action_kind=str(row[9]),
        action_class=str(row[10]),
        action_terms=dict(row[11]),
        action_terms_digest=str(row[12]),
        capital_decision_digest=str(row[13]),
        client_order_id=str(row[14]) if row[14] is not None else None,
        cancel_target=dict(row[15]) if row[15] is not None else None,
        state=str(row[16]),
        state_version=int(row[17]),
        state_digest=str(row[18]),
        request_digest=str(row[19]) if row[19] is not None else None,
        call_started_at=row[20],
        call_completed_at=row[21],
        venue_order_refs=tuple(str(item) for item in row[22]),
        venue_fact_refs=tuple(str(item) for item in row[23]),
        unknown_reason=str(row[24]) if row[24] is not None else None,
        next_query_at=row[25],
        not_submitted_reason=str(row[26]) if row[26] is not None else None,
        protection_digest=str(row[27]) if row[27] is not None else None,
        closure_evidence_digest=str(row[28]) if row[28] is not None else None,
        created_at=row[29],
        updated_at=row[30],
    )


_FACT_SELECT = """
SELECT venue_fact_id, environment_id, venue_ref, account_ref, instrument_ref,
       kind, source_class, source_object_id, source_sequence, source_time,
       received_at, cutoff, schema_version, content_digest, payload,
       activation_ref, action_ref, attribution_digest, attribution_class,
       handover_command_ref, supersedes_ref, correction_reason,
       correction_evidence_refs, correction_effective_time, impact_scope,
       affected_reference_refs
FROM halpha.venue_fact
"""


def _fact_from_row(row: tuple[Any, ...]) -> VenueFact:
    return VenueFact(
        venue_fact_id=str(row[0]),
        environment_id=str(row[1]),
        venue_ref=str(row[2]),
        account_ref=str(row[3]) if row[3] is not None else None,
        instrument_ref=str(row[4]) if row[4] is not None else None,
        kind=str(row[5]),
        source_class=str(row[6]),
        source_object_id=str(row[7]) if row[7] is not None else None,
        source_sequence=str(row[8]) if row[8] is not None else None,
        source_time=row[9],
        received_at=row[10],
        cutoff=row[11],
        schema_version=int(row[12]),
        content_digest=str(row[13]),
        payload=dict(row[14]),
        activation_ref=str(row[15]) if row[15] is not None else None,
        action_ref=str(row[16]) if row[16] is not None else None,
        attribution_digest=str(row[17]) if row[17] is not None else None,
        attribution_class=str(row[18]) if row[18] is not None else None,
        handover_command_ref=str(row[19]) if row[19] is not None else None,
        supersedes_ref=str(row[20]) if row[20] is not None else None,
        correction_reason=str(row[21]) if row[21] is not None else None,
        correction_evidence_refs=(
            tuple(str(item) for item in row[22]) if row[22] is not None else None
        ),
        correction_effective_time=row[23],
        impact_scope=dict(row[24]) if row[24] is not None else None,
        affected_reference_refs=(
            tuple(str(item) for item in row[25]) if row[25] is not None else None
        ),
    )
