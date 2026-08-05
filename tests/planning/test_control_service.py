from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from halpha.capital.models import AuthorityClass, EnvironmentKind
from halpha.planning.control_service import ActivationControlService
from halpha.planning.models import PlanActivation, PlanLifecycle, ProtectionState
from halpha.planning.transitions import ControlIntent
from halpha.user_workbench.commands import (
    build_command,
    initial_receipt,
)
from halpha.user_workbench.repository import CommandConflict


NOW = datetime(2026, 7, 20, 4, tzinfo=UTC)


def _activation(**updates: object) -> PlanActivation:
    values: dict[str, object] = {
        "activation_id": "activation-empty-demo",
        "environment_id": "binance-demo-primary",
        "environment_kind": EnvironmentKind.DEMO,
        "authority_class": AuthorityClass.DEMO_VALIDATION,
        "plan_version_ref": "plan-version-empty-demo",
        "account_ref": "demo-owner",
        "instrument_ref": "BTCUSDT-PERP",
        "direction": "SHORT",
        "decision_basis_ref": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT@1.0.1",
        "framework_strategy_id": "HALPHA-EMPTY-DEMO",
        "target_exposure": "500",
        "rule_state": {},
        "protection_state": ProtectionState.NONE,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(updates)
    return PlanActivation(**values)


def test_empty_activation_can_close_without_inventing_venue_facts() -> None:
    service = object.__new__(ActivationControlService)
    checked_activation_ids: list[str] = []
    service._execution_actions = SimpleNamespace(
        has_open_entry_responsibility=lambda activation_id: (
            checked_activation_ids.append(activation_id) or False
        ),
        has_unclosed_called_responsibility=lambda _activation_id: False,
    )

    completed = service._complete_if_no_venue_responsibility(
        _activation(lifecycle=PlanLifecycle.EXITING),
        reason="EXIT_WITHOUT_VENUE_RESPONSIBILITY",
        command_ref="command-exit-empty",
        observed_at=NOW,
    )

    assert completed.lifecycle is PlanLifecycle.COMPLETED
    assert completed.closure_digest is not None
    assert completed.entry_opportunity_consumed is True
    assert completed.result_ref is not None
    assert checked_activation_ids == ["activation-empty-demo"]


def test_activation_with_open_entry_responsibility_stays_open_for_cancel() -> None:
    service = object.__new__(ActivationControlService)
    checked_activation_ids: list[str] = []
    service._execution_actions = SimpleNamespace(
        has_open_entry_responsibility=lambda activation_id: (
            checked_activation_ids.append(activation_id) or True
        ),
        has_unclosed_called_responsibility=lambda _activation_id: False,
    )
    exiting = _activation(lifecycle=PlanLifecycle.EXITING)

    result = service._complete_if_no_venue_responsibility(
        exiting,
        reason="EXIT_WITHOUT_VENUE_RESPONSIBILITY",
        command_ref="command-exit-with-open-entry",
        observed_at=NOW,
    )

    assert result is exiting
    assert result.lifecycle is PlanLifecycle.EXITING
    assert checked_activation_ids == ["activation-empty-demo"]


def test_activation_with_a_pending_action_stays_open_for_real_closure() -> None:
    service = object.__new__(ActivationControlService)
    service._execution_actions = SimpleNamespace(
        has_open_entry_responsibility=lambda _activation_id: False,
        has_unclosed_called_responsibility=lambda _activation_id: False,
    )
    exiting = _activation(
        lifecycle=PlanLifecycle.EXITING,
        pending_action_digest="a" * 64,
    )

    result = service._complete_if_no_venue_responsibility(
        exiting,
        reason="EXIT_WITHOUT_VENUE_RESPONSIBILITY",
        command_ref="command-exit-with-action",
        observed_at=NOW,
    )

    assert result is exiting
    assert result.lifecycle is PlanLifecycle.EXITING


def test_activation_with_unknown_cancel_stays_open_for_original_identity_query() -> None:
    service = object.__new__(ActivationControlService)
    service._execution_actions = SimpleNamespace(
        has_open_entry_responsibility=lambda _activation_id: False,
        has_unclosed_called_responsibility=lambda _activation_id: True,
    )
    takeover = _activation(
        lifecycle=PlanLifecycle.USER_TAKEOVER,
        takeover_scope={"execution_responsibility": "USER"},
    )

    result = service._complete_if_no_venue_responsibility(
        takeover,
        reason="USER_TAKEOVER_WITHOUT_VENUE_RESPONSIBILITY",
        command_ref="command-takeover-with-unknown-cancel",
        observed_at=NOW,
    )

    assert result is takeover
    assert result.lifecycle is PlanLifecycle.USER_TAKEOVER


def test_control_submission_serializes_with_final_venue_dispatch(monkeypatch) -> None:
    activation = _activation()
    command = build_command(
        command_id="command-lock-1",
        environment_id=activation.environment_id,
        owner_scope="owner-1",
        idempotency_key="stop-lock-1",
        activation_id=activation.activation_id,
        expected_version=activation.state_version,
        intent=ControlIntent.STOP_NEW_RISK,
        scope={},
        parameters={},
        submitted_at=NOW,
    )
    receipt = initial_receipt(
        command,
        receipt_id="receipt-lock-1",
        processing_owner="TRADEPLAN",
    )
    lock_calls: list[tuple[object, str, str]] = []
    connection = object()
    monkeypatch.setattr(
        "halpha.planning.control_service.acquire_activation_control_lock",
        lambda used_connection, *, environment_id, activation_id: lock_calls.append(
            (used_connection, environment_id, activation_id)
        ),
    )
    service = object.__new__(ActivationControlService)
    service._connection = connection
    service._environment_id = activation.environment_id
    service._commands = SimpleNamespace(
        find_by_idempotency=lambda *_args, **_kwargs: (command, receipt)
    )

    result = service.submit(
        command,
        receipt_id=receipt.receipt_id,
        stop_state_version_id="stop-lock-1",
    )

    assert result is receipt
    assert lock_calls == [
        (connection, activation.environment_id, activation.activation_id)
    ]


def test_control_replay_ignores_server_generated_arrival_time(monkeypatch) -> None:
    activation = _activation()
    original = build_command(
        command_id="command-replay-1",
        environment_id=activation.environment_id,
        owner_scope="owner-1",
        idempotency_key="replay-1",
        activation_id=activation.activation_id,
        expected_version=activation.state_version,
        intent=ControlIntent.STOP_NEW_RISK,
        scope={"activation_id": activation.activation_id, "cutoff": NOW.isoformat()},
        parameters={},
        submitted_at=NOW,
    )
    replayed = build_command(
        command_id=original.command_id,
        environment_id=activation.environment_id,
        owner_scope="owner-1",
        idempotency_key=original.idempotency_key,
        activation_id=activation.activation_id,
        expected_version=activation.state_version,
        intent=ControlIntent.STOP_NEW_RISK,
        scope={
            "activation_id": activation.activation_id,
            "cutoff": (NOW + timedelta(seconds=5)).isoformat(),
        },
        parameters={},
        submitted_at=NOW + timedelta(seconds=5),
    )
    receipt = initial_receipt(
        original,
        receipt_id="receipt-replay-1",
        processing_owner="TRADEPLAN",
    )
    monkeypatch.setattr(
        "halpha.planning.control_service.acquire_activation_control_lock",
        lambda *_args, **_kwargs: None,
    )
    service = object.__new__(ActivationControlService)
    service._connection = object()
    service._environment_id = activation.environment_id
    service._commands = SimpleNamespace(
        find_by_idempotency=lambda *_args, **_kwargs: (original, receipt)
    )

    assert service.submit(
        replayed,
        receipt_id=receipt.receipt_id,
        stop_state_version_id="stop-replay-1",
    ) is receipt


def test_control_replay_still_rejects_changed_client_terms(monkeypatch) -> None:
    activation = _activation()
    original = build_command(
        command_id="command-conflict-1",
        environment_id=activation.environment_id,
        owner_scope="owner-1",
        idempotency_key="conflict-1",
        activation_id=activation.activation_id,
        expected_version=activation.state_version,
        intent=ControlIntent.STOP_NEW_RISK,
        scope={"activation_id": activation.activation_id, "cutoff": NOW.isoformat()},
        parameters={},
        submitted_at=NOW,
    )
    conflicting = build_command(
        command_id=original.command_id,
        environment_id=activation.environment_id,
        owner_scope="owner-1",
        idempotency_key=original.idempotency_key,
        activation_id=activation.activation_id,
        expected_version=activation.state_version + 1,
        intent=ControlIntent.STOP_NEW_RISK,
        scope={
            "activation_id": activation.activation_id,
            "cutoff": (NOW + timedelta(seconds=5)).isoformat(),
        },
        parameters={},
        submitted_at=NOW + timedelta(seconds=5),
    )
    receipt = initial_receipt(
        original,
        receipt_id="receipt-conflict-1",
        processing_owner="TRADEPLAN",
    )
    monkeypatch.setattr(
        "halpha.planning.control_service.acquire_activation_control_lock",
        lambda *_args, **_kwargs: None,
    )
    service = object.__new__(ActivationControlService)
    service._connection = object()
    service._environment_id = activation.environment_id
    service._commands = SimpleNamespace(
        find_by_idempotency=lambda *_args, **_kwargs: (original, receipt)
    )

    with pytest.raises(CommandConflict, match="COMMAND_CONTENT_CONFLICT"):
        service.submit(
            conflicting,
            receipt_id=receipt.receipt_id,
            stop_state_version_id="stop-conflict-1",
        )
