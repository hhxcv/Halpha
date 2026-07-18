from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from halpha.capital.models import AuthorityClass, EnvironmentKind, RiskClass
from halpha.executor.coordinator import (
    HalphaCoordinator,
    _protection_projection_state,
    _submission_block_reason,
)
from halpha.planning.models import (
    PlanLifecycle,
    ProtectionState,
    RunState,
)
from halpha.venue_integration.models import (
    ExecutionActionKind,
    ExecutionActionState,
)


def _action(kind: ExecutionActionKind, state: ExecutionActionState):
    return SimpleNamespace(action_kind=kind, state=state)


def test_working_protection_projects_working() -> None:
    assert (
        _protection_projection_state(
            _action(
                ExecutionActionKind.PROTECTION,
                ExecutionActionState.WORKING,
            )
        )
        is ProtectionState.WORKING
    )


def test_terminal_unfilled_protection_projects_gap() -> None:
    for state in (
        ExecutionActionState.CANCELLED,
        ExecutionActionState.REJECTED,
        ExecutionActionState.EXPIRED,
    ):
        assert (
            _protection_projection_state(
                _action(ExecutionActionKind.PROTECTION, state)
            )
            is ProtectionState.GAP
        )


def test_non_protection_or_non_projectable_state_has_no_projection() -> None:
    assert (
        _protection_projection_state(
            _action(ExecutionActionKind.ENTRY, ExecutionActionState.WORKING)
        )
        is None
    )
    assert (
        _protection_projection_state(
            _action(
                ExecutionActionKind.PROTECTION,
                ExecutionActionState.SUBMITTED_UNKNOWN,
            )
        )
        is None
    )


def test_paused_activation_blocks_only_risk_increasing_submission() -> None:
    paused = SimpleNamespace(
        lifecycle=PlanLifecycle.RUNNING,
        run_state=RunState.PAUSED,
    )
    increasing = SimpleNamespace(action_class=RiskClass.RISK_INCREASING)
    neutral = SimpleNamespace(action_class=RiskClass.RISK_NEUTRAL)
    reducing = SimpleNamespace(action_class=RiskClass.RISK_REDUCING)

    assert _submission_block_reason(increasing, paused) == "NEW_RISK_STOPPED"
    assert _submission_block_reason(neutral, paused) is None
    assert _submission_block_reason(reducing, paused) is None


def test_user_takeover_or_completion_blocks_every_submission_class() -> None:
    action = SimpleNamespace(action_class=RiskClass.RISK_REDUCING)
    for lifecycle in (PlanLifecycle.USER_TAKEOVER, PlanLifecycle.COMPLETED):
        activation = SimpleNamespace(
            lifecycle=lifecycle,
            run_state=RunState.PAUSED,
        )
        assert _submission_block_reason(action, activation) == "USER_TAKEOVER_ACTIVE"


def test_live_submission_guard_rechecks_the_exact_activation() -> None:
    observed: list[str] = []
    coordinator = object.__new__(HalphaCoordinator)
    coordinator._environment_kind = "LIVE"
    coordinator._live_write_submission_guard = observed.append

    coordinator._require_current_live_write_gate("activation-live-001")

    assert observed == ["activation-live-001"]


def test_live_submission_guard_fails_closed_without_leaking_internal_error() -> None:
    coordinator = object.__new__(HalphaCoordinator)
    coordinator._environment_kind = "LIVE"

    def fail(_activation_id: str) -> None:
        raise ValueError("sensitive-detail")

    coordinator._live_write_submission_guard = fail

    with pytest.raises(RuntimeError, match="^RUNTIME_REAL_WRITE_GATE_CLOSED$"):
        coordinator._require_current_live_write_gate("activation-live-001")


def test_demo_submission_path_does_not_add_a_second_gate() -> None:
    coordinator = object.__new__(HalphaCoordinator)
    coordinator._environment_kind = "DEMO"
    coordinator._live_write_submission_guard = lambda _activation_id: pytest.fail(
        "Demo must not invoke the LIVE deployment gate"
    )

    coordinator._require_current_live_write_gate("activation-demo-001")


def test_live_gate_closing_after_submitting_records_not_submitted_without_venue_call() -> None:
    activation_id = "activation-live-001"
    action_id = "execution-action-live-001"
    observed_at = datetime(2026, 7, 18, 13, 0, tzinfo=UTC)
    action_terms = {
        "instrument_ref": "BTCUSDT-PERP",
        "action_profile": "ENTRY_MARKET",
        "quantity": "0.001",
    }
    action = SimpleNamespace(
        execution_action_id=action_id,
        environment_id="live-main",
        environment_kind=EnvironmentKind.LIVE,
        authority_class=AuthorityClass.LIVE_REAL_CAPITAL,
        activation_id=activation_id,
        account_ref="live-owner",
        action_class=RiskClass.RISK_INCREASING,
        action_terms=action_terms,
    )
    prepared = SimpleNamespace(
        **vars(action),
        state=ExecutionActionState.SUBMITTING,
        state_digest="d" * 64,
    )
    action_check = SimpleNamespace(
        environment_id="live-main",
        environment_kind=EnvironmentKind.LIVE,
        authority_class=AuthorityClass.LIVE_REAL_CAPITAL,
        activation_id=activation_id,
        account_ref="live-owner",
        instrument_ref="BTCUSDT-PERP",
        action_profile="ENTRY_MARKET",
        risk_class=RiskClass.RISK_INCREASING,
        quantized_quantity="0.001",
    )
    gate_checks: list[str] = []

    def current_gate_guard(current_activation_id: str) -> None:
        gate_checks.append(current_activation_id)
        if len(gate_checks) == 2:
            raise RuntimeError("binding-revoked-after-submitting")

    recorded: list[tuple[str, str]] = []

    class ExecutionService:
        @staticmethod
        def prepare_submission(*args, **kwargs):
            assert args == (action_id,)
            assert kwargs["observed_at"] == observed_at
            return prepared

        @staticmethod
        def record_definitely_not_submitted(
            execution_action_id: str,
            *,
            reason_code: str,
            observed_at: datetime,
        ):
            assert observed_at == datetime(2026, 7, 18, 13, 0, tzinfo=UTC)
            recorded.append((execution_action_id, reason_code))
            values = {
                **vars(prepared),
                "state": ExecutionActionState.NOT_SUBMITTED,
                "not_submitted_reason": reason_code,
            }
            return SimpleNamespace(**values)

    coordinator = object.__new__(HalphaCoordinator)
    coordinator._environment_kind = "LIVE"
    coordinator._runtime_real_write_gate = "OPEN"
    coordinator._live_write_activation_id = activation_id
    coordinator._live_write_submission_guard = current_gate_guard
    coordinator._connection = SimpleNamespace(transaction=lambda: nullcontext())
    coordinator._action_repository = SimpleNamespace(
        get=lambda execution_action_id, **_kwargs: action
    )
    coordinator._planning = SimpleNamespace(
        get_activation=lambda current_activation_id, **_kwargs: SimpleNamespace(
            lifecycle=PlanLifecycle.RUNNING,
            run_state=RunState.ACTIVE,
        )
    )
    coordinator._capital = SimpleNamespace(
        check_current_action=lambda _check: SimpleNamespace(accepted=True)
    )
    coordinator._execution = ExecutionService()
    coordinator._gate = SimpleNamespace(
        authorize_committed_submission=lambda *_args, **_kwargs: pytest.fail(
            "a closed runtime gate must not authorize a venue call"
        ),
        execute_once=lambda *_args, **_kwargs: pytest.fail(
            "a closed runtime gate must not execute a venue call"
        ),
    )

    result = coordinator.process_execution_action(
        action_id,
        action_check=action_check,
        request_payload={"order_type": "MARKET", "quantity": "0.001"},
        observed_at=observed_at,
    )

    assert gate_checks == [activation_id, activation_id]
    assert recorded == [(action_id, "RUNTIME_REAL_WRITE_GATE_CLOSED")]
    assert result.venue_called is False
    assert result.reason_code == "RUNTIME_REAL_WRITE_GATE_CLOSED"
    assert result.execution_action.state is ExecutionActionState.NOT_SUBMITTED
