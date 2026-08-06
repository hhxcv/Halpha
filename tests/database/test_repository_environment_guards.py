from __future__ import annotations

from types import SimpleNamespace
from typing import Callable

import pytest

from halpha.capital.repository import CapitalConflict, PostgreSQLCapitalRepository
from halpha.planning.repository import PlanningConflict, PostgreSQLPlanningRepository
from halpha.user_workbench.repository import (
    CommandConflict,
    PostgreSQLCommandRepository,
)


DEMO_ENVIRONMENT = "binance-demo-primary"
LIVE_ENVIRONMENT = "binance-live-copy-primary"


class _NoExecuteConnection:
    def __init__(self) -> None:
        self.execute_calls = 0

    def execute(self, *_args: object, **_kwargs: object) -> None:
        self.execute_calls += 1
        raise AssertionError("database execute must not be reached")


class _EmptyRecordingConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object | None]] = []

    def execute(self, statement: str, params: object | None = None):
        self.calls.append((statement, params))
        return self

    def fetchone(self):
        return None

    def fetchall(self):
        return []


def test_account_stop_reads_share_one_transaction_advisory_lock() -> None:
    connection = _EmptyRecordingConnection()
    repository = PostgreSQLCapitalRepository(  # type: ignore[arg-type]
        connection,
        DEMO_ENVIRONMENT,
    )

    assert (
        repository.lock_current_account_stop_state(account_ref="owner-primary")
        is None
    )
    assert repository.lock_current_stop_states(
        account_ref="owner-primary",
        activation_id="activation-1",
    ) == ()

    lock_calls = [
        (statement, params)
        for statement, params in connection.calls
        if "pg_advisory_xact_lock" in statement
    ]
    assert len(lock_calls) == 2
    assert lock_calls[0][1] == (
        f"{DEMO_ENVIRONMENT}:owner-primary",
    )
    assert lock_calls[1][1] == lock_calls[0][1]
    assert all(
        "FOR UPDATE" not in statement
        for statement, _params in connection.calls
        if "stop_state_version" in statement
    )


@pytest.mark.parametrize(
    "operation",
    (
        lambda repository, value: repository.save_draft(
            value,
            expected_version=None,
        ),
        lambda repository, value: repository.insert_version(value),
        lambda repository, value: repository.insert_activation(value),
        lambda repository, value: repository.update_activation(
            value,
            expected_version=0,
        ),
        lambda repository, value: repository.insert_event(value),
    ),
    ids=(
        "save-draft",
        "insert-version",
        "insert-activation",
        "update-activation",
        "insert-event",
    ),
)
def test_planning_writes_reject_cross_environment_before_execute(
    operation: Callable[[PostgreSQLPlanningRepository, object], object],
) -> None:
    connection = _NoExecuteConnection()
    repository = PostgreSQLPlanningRepository(connection, DEMO_ENVIRONMENT)  # type: ignore[arg-type]
    foreign_value = SimpleNamespace(environment_id=LIVE_ENVIRONMENT)

    with pytest.raises(PlanningConflict, match="PLAN_ENVIRONMENT_MISMATCH"):
        operation(repository, foreign_value)

    assert connection.execute_calls == 0


def test_capital_write_rejects_cross_environment_before_execute() -> None:
    connection = _NoExecuteConnection()
    repository = PostgreSQLCapitalRepository(connection, DEMO_ENVIRONMENT)  # type: ignore[arg-type]
    foreign_state = SimpleNamespace(environment_id=LIVE_ENVIRONMENT)

    with pytest.raises(
        CapitalConflict,
        match="STOP_STATE_ENVIRONMENT_MISMATCH",
    ):
        repository.insert_stop_state(foreign_state)  # type: ignore[arg-type]

    assert connection.execute_calls == 0


@pytest.mark.parametrize(
    ("command_environment", "receipt_environment"),
    (
        (LIVE_ENVIRONMENT, DEMO_ENVIRONMENT),
        (DEMO_ENVIRONMENT, LIVE_ENVIRONMENT),
    ),
)
def test_command_insert_rejects_either_cross_environment_record_before_execute(
    command_environment: str,
    receipt_environment: str,
) -> None:
    connection = _NoExecuteConnection()
    repository = PostgreSQLCommandRepository(connection, DEMO_ENVIRONMENT)  # type: ignore[arg-type]
    command = SimpleNamespace(environment_id=command_environment)
    receipt = SimpleNamespace(environment_id=receipt_environment)

    with pytest.raises(CommandConflict, match="COMMAND_ENVIRONMENT_MISMATCH"):
        repository.insert(command, receipt)  # type: ignore[arg-type]

    assert connection.execute_calls == 0


def test_receipt_update_rejects_cross_environment_before_execute() -> None:
    connection = _NoExecuteConnection()
    repository = PostgreSQLCommandRepository(connection, DEMO_ENVIRONMENT)  # type: ignore[arg-type]
    foreign_receipt = SimpleNamespace(environment_id=LIVE_ENVIRONMENT)

    with pytest.raises(CommandConflict, match="COMMAND_ENVIRONMENT_MISMATCH"):
        repository.update_receipt(  # type: ignore[arg-type]
            foreign_receipt,
            expected_version=0,
        )

    assert connection.execute_calls == 0
