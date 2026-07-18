"""UX's private PostgreSQL writer for Command and Receipt."""

from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from halpha.planning.transitions import ControlIntent
from halpha.user_workbench.commands import Command, Receipt, ReceiptState


class CommandConflict(RuntimeError):
    pass


class PostgreSQLCommandRepository:
    def __init__(self, connection: Connection[Any], environment_id: str) -> None:
        self._connection = connection
        self._environment_id = environment_id

    def find_by_idempotency(
        self, owner_scope: str, idempotency_key: str, *, for_update: bool = False
    ) -> tuple[Command, Receipt] | None:
        suffix = " FOR UPDATE OF c, r" if for_update else ""
        row = self._connection.execute(
            """
            SELECT c.command_id, c.environment_id, c.owner_scope, c.idempotency_key,
                   c.target_kind, c.target_ref, c.expected_version, c.intent,
                   c.scope, c.parameters, c.submitted_at, c.content_digest,
                   r.receipt_id, r.processing_owner, r.state, r.state_version,
                   r.reason_code, r.result, r.pending_responsibility_refs,
                   r.content_digest, r.created_at, r.updated_at
            FROM halpha.command c
            JOIN halpha.receipt r
              ON r.environment_id = c.environment_id AND r.command_id = c.command_id
            WHERE c.environment_id = %s AND c.owner_scope = %s AND c.idempotency_key = %s
            """ + suffix,
            (self._environment_id, owner_scope, idempotency_key),
        ).fetchone()
        if row is None:
            return None
        command = Command(
            command_id=str(row[0]),
            environment_id=str(row[1]),
            owner_scope=str(row[2]),
            idempotency_key=str(row[3]),
            target_kind=str(row[4]),
            target_ref=str(row[5]),
            expected_version=int(row[6]),
            intent=ControlIntent(str(row[7])),
            scope=dict(row[8]),
            parameters=dict(row[9]),
            submitted_at=row[10],
            content_digest=str(row[11]),
        )
        receipt = Receipt(
            receipt_id=str(row[12]),
            environment_id=command.environment_id,
            command_id=command.command_id,
            processing_owner=str(row[13]),
            state=ReceiptState(str(row[14])),
            state_version=int(row[15]),
            reason_code=str(row[16]) if row[16] is not None else None,
            result=dict(row[17]) if row[17] is not None else None,
            pending_responsibility_refs=tuple(row[18]),
            content_digest=str(row[19]),
            created_at=row[20],
            updated_at=row[21],
        )
        return command, receipt

    def insert(self, command: Command, receipt: Receipt) -> None:
        self._connection.execute(
            """
            INSERT INTO halpha.command (
                command_id, environment_id, owner_scope, idempotency_key,
                target_kind, target_ref, expected_version, intent, scope,
                parameters, submitted_at, content_digest
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                command.command_id,
                command.environment_id,
                command.owner_scope,
                command.idempotency_key,
                command.target_kind,
                command.target_ref,
                command.expected_version,
                command.intent.value,
                Jsonb(command.scope),
                Jsonb(command.parameters),
                command.submitted_at,
                command.content_digest,
            ),
        )
        self._connection.execute(
            """
            INSERT INTO halpha.receipt (
                receipt_id, environment_id, command_id, processing_owner,
                state, state_version, reason_code, result,
                pending_responsibility_refs, content_digest, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                receipt.receipt_id,
                receipt.environment_id,
                receipt.command_id,
                receipt.processing_owner,
                receipt.state.value,
                receipt.state_version,
                receipt.reason_code,
                Jsonb(receipt.result) if receipt.result is not None else None,
                Jsonb(list(receipt.pending_responsibility_refs)),
                receipt.content_digest,
                receipt.created_at,
                receipt.updated_at,
            ),
        )

    def update_receipt(self, receipt: Receipt, *, expected_version: int) -> None:
        cursor = self._connection.execute(
            """
            UPDATE halpha.receipt
            SET state = %s, state_version = %s, reason_code = %s, result = %s,
                pending_responsibility_refs = %s, content_digest = %s, updated_at = %s
            WHERE environment_id = %s AND receipt_id = %s AND state_version = %s
            """,
            (
                receipt.state.value,
                receipt.state_version,
                receipt.reason_code,
                Jsonb(receipt.result) if receipt.result is not None else None,
                Jsonb(list(receipt.pending_responsibility_refs)),
                receipt.content_digest,
                receipt.updated_at,
                receipt.environment_id,
                receipt.receipt_id,
                expected_version,
            ),
        )
        if cursor.rowcount != 1:
            raise CommandConflict("VERSION_CONFLICT")
