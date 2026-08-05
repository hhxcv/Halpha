from __future__ import annotations

from contextlib import nullcontext

import pytest

from halpha.venue_integration.dispatch_lock import (
    acquire_activation_control_lock,
    activation_dispatch_lock_identity,
    serialize_activation_dispatch,
)


class _Result:
    def __init__(self, row: tuple[object, ...] | None = None) -> None:
        self._row = row

    def fetchone(self) -> tuple[object, ...] | None:
        return self._row


class _Connection:
    def __init__(self, *, unlock_result: bool = True) -> None:
        self.calls: list[tuple[str, tuple[str, ...]]] = []
        self.unlock_result = unlock_result

    def execute(self, statement: str, parameters: tuple[str, ...]) -> _Result:
        self.calls.append((statement, parameters))
        if "pg_advisory_unlock" in statement:
            return _Result((self.unlock_result,))
        return _Result((None,))

    @staticmethod
    def transaction():
        return nullcontext()


def test_control_and_dispatch_use_the_same_activation_lock_identity() -> None:
    connection = _Connection()
    identity = activation_dispatch_lock_identity("demo", "activation-1")

    acquire_activation_control_lock(
        connection,
        environment_id="demo",
        activation_id="activation-1",
    )
    with serialize_activation_dispatch(
        connection,
        environment_id="demo",
        activation_id="activation-1",
    ):
        pass

    assert [parameters for _, parameters in connection.calls] == [
        (identity,),
        (identity,),
        (identity,),
    ]
    assert "pg_advisory_xact_lock" in connection.calls[0][0]
    assert "pg_advisory_lock" in connection.calls[1][0]
    assert "pg_advisory_unlock" in connection.calls[2][0]


def test_dispatch_lock_is_released_when_venue_path_raises() -> None:
    connection = _Connection()

    with pytest.raises(RuntimeError, match="venue failed"):
        with serialize_activation_dispatch(
            connection,
            environment_id="demo",
            activation_id="activation-1",
        ):
            raise RuntimeError("venue failed")

    assert "pg_advisory_unlock" in connection.calls[-1][0]


def test_dispatch_fails_closed_when_session_lock_cannot_be_released() -> None:
    connection = _Connection(unlock_result=False)

    with pytest.raises(RuntimeError, match="ACTIVATION_DISPATCH_LOCK_RELEASE_FAILED"):
        with serialize_activation_dispatch(
            connection,
            environment_id="demo",
            activation_id="activation-1",
        ):
            pass


@pytest.mark.parametrize("environment_id,activation_id", (("", "a"), ("e", "")))
def test_dispatch_lock_rejects_empty_identity(
    environment_id: str,
    activation_id: str,
) -> None:
    with pytest.raises(ValueError, match="ACTIVATION_DISPATCH_LOCK_IDENTITY_INVALID"):
        activation_dispatch_lock_identity(environment_id, activation_id)
