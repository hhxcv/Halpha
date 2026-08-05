from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from halpha.planning.models import PlanLifecycle
from halpha.planning.service import PlanningApplicationService
from halpha.planning.transitions import ControlIntent
from halpha.user_workbench.commands import (
    ReceiptState,
    advance_receipt,
    build_command,
    initial_receipt,
)


NOW = datetime(2026, 7, 31, tzinfo=UTC)


def _processing_exit():
    command = build_command(
        command_id="command-1",
        environment_id="demo-main",
        owner_scope="owner-1",
        idempotency_key="exit-1",
        activation_id="activation-1",
        expected_version=1,
        intent=ControlIntent.EXIT_STRATEGY,
        scope={},
        parameters={},
        submitted_at=NOW,
    )
    received = initial_receipt(
        command,
        receipt_id="receipt-1",
        processing_owner="TRADEPLAN",
    )
    return command, advance_receipt(
        received,
        state=ReceiptState.PROCESSING,
        reason_code="EXIT_RESPONSIBILITY_ACCEPTED",
        result={"activation_id": "activation-1"},
        pending_responsibility_refs=("EXIT_CLOSURE_DIGEST",),
        observed_at=NOW,
    )


def test_completed_activation_finalizes_receipt_in_owning_service(monkeypatch) -> None:
    command, receipt = _processing_exit()
    updates = []

    class Commands:
        def __init__(self, _connection, _environment_id):
            pass

        @staticmethod
        def list_processing_for_target(_target, **_kwargs):
            return ((command, receipt),)

        @staticmethod
        def update_receipt(updated, **_kwargs):
            updates.append(updated)

    monkeypatch.setattr(
        "halpha.planning.service.PostgreSQLCommandRepository",
        Commands,
    )
    service = object.__new__(PlanningApplicationService)
    service._connection = object()
    service._environment_id = "demo-main"
    activation = SimpleNamespace(
        lifecycle=PlanLifecycle.COMPLETED,
        activation_id="activation-1",
        state_version=7,
        result_ref="review-1",
    )

    finalized = service._finalize_completed_receipts(activation, observed_at=NOW)

    assert finalized == tuple(updates)
    assert finalized[0].state is ReceiptState.EFFECTIVE
    assert finalized[0].reason_code == "EXIT_COMPLETED"
    assert finalized[0].pending_responsibility_refs == ()
    assert finalized[0].result == {
        "activation_id": "activation-1",
        "activation_state_version": 7,
        "result_ref": "review-1",
    }


def test_startup_recovery_only_finalizes_completed_targets(monkeypatch) -> None:
    recovered: list[str] = []
    locked: list[tuple[str, str]] = []

    class Commands:
        def __init__(self, _connection, _environment_id):
            pass

        @staticmethod
        def list_processing_target_refs():
            return ("completed", "running")

    monkeypatch.setattr(
        "halpha.planning.service.PostgreSQLCommandRepository",
        Commands,
    )
    monkeypatch.setattr(
        "halpha.planning.service.acquire_activation_control_lock",
        lambda _connection, *, environment_id, activation_id: locked.append(
            (environment_id, activation_id)
        ),
    )
    service = object.__new__(PlanningApplicationService)
    service._connection = object()
    service._environment_id = "demo-main"
    service._planning = SimpleNamespace(
        get_activation=lambda activation_id, **_kwargs: SimpleNamespace(
            activation_id=activation_id,
            lifecycle=(
                PlanLifecycle.COMPLETED
                if activation_id == "completed"
                else PlanLifecycle.RUNNING
            ),
        )
    )
    service._finalize_completed_receipts = lambda activation, **_kwargs: (
        (recovered.append(activation.activation_id) or ())
        if activation.lifecycle is PlanLifecycle.COMPLETED
        else ()
    )

    assert service.recover_completed_command_receipts(observed_at=NOW) == ()
    assert recovered == ["completed"]
    assert locked == [
        ("demo-main", "completed"),
        ("demo-main", "running"),
    ]


def test_execution_completion_takes_control_lock_before_plan_row(monkeypatch) -> None:
    events: list[str] = []
    activation = SimpleNamespace(state_version=4)
    completed = SimpleNamespace(state_version=5)

    monkeypatch.setattr(
        "halpha.planning.service.acquire_activation_control_lock",
        lambda *_args, **_kwargs: events.append("control-lock"),
    )
    monkeypatch.setattr(
        "halpha.planning.service.complete_activation",
        lambda *_args, **_kwargs: completed,
    )
    service = object.__new__(PlanningApplicationService)
    service._connection = object()
    service._environment_id = "demo-main"
    service._planning = SimpleNamespace(
        get_activation=lambda *_args, **_kwargs: (
            events.append("plan-lock") or activation
        ),
        update_activation=lambda *_args, **_kwargs: events.append("plan-update"),
    )
    service._finalize_completed_receipts = lambda *_args, **_kwargs: (
        events.append("receipt-lock") or ()
    )

    result = service.complete_with_execution_closure(
        activation_id="activation-1",
        closure_digest="closure-1",
        result_ref="review-1",
        observed_at=NOW,
    )

    assert result is completed
    assert events == [
        "control-lock",
        "plan-lock",
        "plan-update",
        "receipt-lock",
    ]
