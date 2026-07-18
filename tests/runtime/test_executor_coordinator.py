from __future__ import annotations

from types import SimpleNamespace

from halpha.capital.models import RiskClass
from halpha.executor.coordinator import (
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
