"""Cross-process serialization between owner control and venue mutations."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


_SESSION_LOCK_SQL = "SELECT pg_advisory_lock(hashtextextended(%s, 0))"
_SESSION_UNLOCK_SQL = "SELECT pg_advisory_unlock(hashtextextended(%s, 0))"
_TRANSACTION_LOCK_SQL = "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))"


def activation_dispatch_lock_identity(
    environment_id: str,
    activation_id: str,
) -> str:
    if not environment_id or not activation_id:
        raise ValueError("ACTIVATION_DISPATCH_LOCK_IDENTITY_INVALID")
    return f"HALPHA:ACTIVATION_DISPATCH:{environment_id}:{activation_id}"


def acquire_activation_control_lock(
    connection: Any,
    *,
    environment_id: str,
    activation_id: str,
) -> None:
    """Hold until the caller's current transaction commits or rolls back."""

    connection.execute(
        _TRANSACTION_LOCK_SQL,
        (activation_dispatch_lock_identity(environment_id, activation_id),),
    )


@contextmanager
def serialize_activation_dispatch(
    connection: Any,
    *,
    environment_id: str,
    activation_id: str,
) -> Iterator[None]:
    """Serialize the final venue mutation with persisted owner controls.

    The Executor connection is autocommit, so the session advisory lock spans
    its local prepare transaction, the one external mutation call and result
    persistence.  A control transaction uses the matching transaction lock.
    """

    identity = activation_dispatch_lock_identity(environment_id, activation_id)
    connection.execute(_SESSION_LOCK_SQL, (identity,))
    try:
        yield
    finally:
        row = connection.execute(_SESSION_UNLOCK_SQL, (identity,)).fetchone()
        if row is None or row[0] is not True:
            raise RuntimeError("ACTIVATION_DISPATCH_LOCK_RELEASE_FAILED")
