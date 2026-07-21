from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from halpha.capital.models import AuthorityClass, EnvironmentKind
from halpha.planning.control_service import ActivationControlService
from halpha.planning.models import PlanActivation, PlanLifecycle, ProtectionState
from halpha.planning.transitions import ControlIntent
from halpha.user_workbench.commands import (
    ReceiptState,
    advance_receipt,
    build_command,
    initial_receipt,
)


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
        "strategy_id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT",
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


def test_activation_with_a_pending_action_stays_open_for_real_closure() -> None:
    service = object.__new__(ActivationControlService)
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


def test_completed_activation_finalizes_processing_exit_receipt() -> None:
    activation = _activation(
        lifecycle=PlanLifecycle.COMPLETED,
        closure_digest="c" * 64,
        result_ref="review-1",
    )
    command = build_command(
        command_id="command-1",
        environment_id=activation.environment_id,
        owner_scope="owner-1",
        idempotency_key="exit-1",
        activation_id=activation.activation_id,
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
    processing = advance_receipt(
        received,
        state=ReceiptState.PROCESSING,
        reason_code="EXIT_RESPONSIBILITY_ACCEPTED",
        result={"activation_id": activation.activation_id},
        pending_responsibility_refs=("EXIT_CLOSURE_DIGEST",),
        observed_at=NOW,
    )
    updates = []
    service = object.__new__(ActivationControlService)
    service._planning = SimpleNamespace(
        get_activation=lambda *_args, **_kwargs: activation
    )
    service._commands = SimpleNamespace(
        list_processing_for_target=lambda *_args, **_kwargs: (
            (command, processing),
        ),
        update_receipt=lambda receipt, **_kwargs: updates.append(receipt),
    )

    finalized = service.finalize_completed_activation(
        activation.activation_id,
        observed_at=NOW,
    )

    assert finalized == tuple(updates)
    assert finalized[0].state is ReceiptState.EFFECTIVE
    assert finalized[0].pending_responsibility_refs == ()
    assert finalized[0].result == {
        "activation_id": activation.activation_id,
        "activation_state_version": activation.state_version,
        "result_ref": "review-1",
    }
