from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from halpha.capital.checks import (
    allocate_plan,
    check_action,
    compute_activation_loss,
    effective_leverage,
    latch_max_loss,
)
from halpha.capital.models import (
    AccountCapitalLimitVersion,
    ActionCheckInput,
    AllocationRequest,
    AllocationStatus,
    AuthorityClass,
    EnvironmentKind,
    MachineAuthorizationVersion,
    PlanAllocation,
    RiskClass,
    StopCategory,
    StopStateVersion,
)


NOW = datetime(2026, 7, 17, 8, tzinfo=UTC)


def _account(**updates: object) -> AccountCapitalLimitVersion:
    values: dict[str, object] = {
        "capital_limit_version_id": "limit-1",
        "environment_id": "demo-1",
        "environment_kind": EnvironmentKind.DEMO,
        "authority_class": AuthorityClass.DEMO_VALIDATION,
        "account_ref": "account-1",
        "quote_asset": "USDT",
        "version": 1,
        "effective_at": NOW,
        "max_margin": "1000",
        "max_notional": "5000",
        "max_allowed_loss": "500",
        "max_action_notional": "1000",
        "scope": {"instruments": ["BTCUSDT-PERP"]},
        "content_digest": "a" * 64,
    }
    values.update(updates)
    return AccountCapitalLimitVersion(**values)


def _authorization(**updates: object) -> MachineAuthorizationVersion:
    values: dict[str, object] = {
        "authorization_version_id": "authorization-1",
        "environment_id": "demo-1",
        "environment_kind": EnvironmentKind.DEMO,
        "authority_class": AuthorityClass.DEMO_VALIDATION,
        "activation_id": "activation-1",
        "plan_version_ref": "plan-version-1",
        "account_ref": "account-1",
        "instrument_ref": "BTCUSDT-PERP",
        "direction": "LONG",
        "version": 1,
        "valid_from": NOW - timedelta(minutes=1),
        "valid_until": NOW + timedelta(days=1),
        "allowed_actions": frozenset({"ENTRY_MARKET", "REDUCE_OR_CLOSE_MARKET"}),
        "terms": {},
        "content_digest": "b" * 64,
    }
    values.update(updates)
    return MachineAuthorizationVersion(**values)


def _allocation(**updates: object) -> PlanAllocation:
    values: dict[str, object] = {
        "allocation_id": "allocation-1",
        "activation_id": "activation-1",
        "capital_limit_version_ref": "limit-1",
        "environment_id": "demo-1",
        "environment_kind": EnvironmentKind.DEMO,
        "authority_class": AuthorityClass.DEMO_VALIDATION,
        "quote_asset": "USDT",
        "max_margin": "200",
        "max_notional": "1000",
        "max_allowed_loss": "100",
    }
    values.update(updates)
    return PlanAllocation(**values)


def _action(**updates: object) -> ActionCheckInput:
    values: dict[str, object] = {
        "environment_id": "demo-1",
        "environment_kind": EnvironmentKind.DEMO,
        "authority_class": AuthorityClass.DEMO_VALIDATION,
        "activation_id": "activation-1",
        "account_ref": "account-1",
        "instrument_ref": "BTCUSDT-PERP",
        "action_profile": "ENTRY_MARKET",
        "control_category": StopCategory.NEW_FUNDING,
        "risk_class": RiskClass.RISK_INCREASING,
        "checked_at": NOW,
        "quantized_quantity": "0.1",
        "conservative_price": "5000",
        "account_dynamic_available_margin": "500",
        "actual_margin_mode": "CROSSED",
        "actual_leverage": "20",
        "post_action_abs_position": "0.1",
        "current_abs_position": "0",
    }
    values.update(updates)
    return ActionCheckInput(**values)


def _stop(*categories: StopCategory, activation_id: str | None = "activation-1") -> StopStateVersion:
    return StopStateVersion(
        stop_state_version_id="stop-" + "-".join(item.value for item in categories),
        environment_id="demo-1",
        environment_kind=EnvironmentKind.DEMO,
        authority_class=AuthorityClass.DEMO_VALIDATION,
        account_ref="account-1",
        activation_id=activation_id,
        version=1,
        stopped_categories=frozenset(categories),
        reason="test",
        source="USER",
        started_at=NOW,
        release_rules={"user_releasable": True},
        content_digest="c" * 64,
    )


def test_actual_account_mode_is_not_a_p0_blocker_and_never_upscaled() -> None:
    assert effective_leverage("CROSSED", "20") == Decimal("5")
    assert effective_leverage("ISOLATED", "3") == Decimal("3")
    with pytest.raises(ValueError, match="MARGIN_MODE_UNKNOWN"):
        effective_leverage("UNKNOWN", "5")


def test_three_allocation_axes_are_mutually_exclusive() -> None:
    request = AllocationRequest(
        allocation_id="allocation-2",
        activation_id="activation-2",
        capital_limit_version_ref="limit-1",
        environment_id="demo-1",
        environment_kind=EnvironmentKind.DEMO,
        authority_class=AuthorityClass.DEMO_VALIDATION,
        quote_asset="USDT",
        max_margin="900",
        max_notional="4000",
        max_allowed_loss="400",
    )
    allocation = allocate_plan(_account(), (), request)
    assert allocation.status is AllocationStatus.HELD
    with pytest.raises(ValueError, match="ACCOUNT_LIMIT_EXCEEDED"):
        allocate_plan(_account(), (_allocation(max_margin="200"),), request)


def test_quantized_action_and_aggregate_limits_share_one_check() -> None:
    decision = check_action(
        _action(), account=_account(), authorization=_authorization(), allocation=_allocation()
    )
    assert decision.accepted is True
    assert decision.effective_leverage == "5"
    assert decision.action_notional == "500"
    aggregate_reject = check_action(
        _action(activation_current_notional="600"),
        account=_account(),
        authorization=_authorization(),
        allocation=_allocation(),
    )
    assert aggregate_reject.reason_code == "NOTIONAL_LIMIT_EXCEEDED"


def test_split_retry_and_partial_fill_cannot_bypass_action_limit() -> None:
    decision = check_action(
        _action(economic_action_prior_notional="700"),
        account=_account(),
        authorization=_authorization(),
        allocation=_allocation(),
    )
    assert decision.accepted is False
    assert decision.reason_code == "ACTION_LIMIT_EXCEEDED"
    assert decision.economic_action_notional == "1200"


def test_natural_overrun_only_blocks_increase_and_reduction_cannot_reverse() -> None:
    increasing = check_action(
        _action(activation_current_notional="1100"),
        account=_account(),
        authorization=_authorization(),
        allocation=_allocation(),
    )
    reducing_action = _action(
        action_profile="REDUCE_OR_CLOSE_MARKET",
        control_category=StopCategory.RISK_REDUCTION_OR_ORDER_MANAGEMENT,
        risk_class=RiskClass.RISK_REDUCING,
        activation_current_notional="1100",
        current_abs_position="1",
        post_action_abs_position="0.5",
    )
    reducing = check_action(
        reducing_action,
        account=_account(),
        authorization=_authorization(),
        allocation=_allocation(current_notional="1100"),
    )
    reverse = check_action(
        reducing_action.model_copy(update={"would_reverse_position": True}),
        account=_account(),
        authorization=_authorization(),
        allocation=_allocation(current_notional="1100"),
    )
    assert increasing.reason_code == "NOTIONAL_LIMIT_EXCEEDED"
    assert reducing.accepted is True
    assert reverse.reason_code == "RISK_REDUCTION_UNPROVEN"


def test_stop_categories_union_and_all_writes_precedence() -> None:
    protection = check_action(
        _action(control_category=StopCategory.PROTECTION),
        account=_account(),
        authorization=_authorization(),
        allocation=_allocation(),
        stop_states=(_stop(StopCategory.NEW_FUNDING),),
    )
    all_writes = check_action(
        _action(),
        account=_account(),
        authorization=_authorization(),
        allocation=_allocation(),
        stop_states=(
            _stop(StopCategory.NEW_FUNDING),
            _stop(StopCategory.ALL_WRITES, activation_id=None),
        ),
    )
    assert protection.accepted is True
    assert all_writes.reason_code == "ALL_WRITES_STOPPED"
    assert all_writes.stopped_categories == (
        StopCategory.ALL_WRITES,
        StopCategory.NEW_FUNDING,
    )


@pytest.mark.parametrize(
    ("category", "risk_class", "profile"),
    (
        (StopCategory.NEW_FUNDING, RiskClass.RISK_INCREASING, "ENTRY_MARKET"),
        (StopCategory.PROTECTION, RiskClass.RISK_REDUCING, "REDUCE_OR_CLOSE_MARKET"),
        (
            StopCategory.RISK_REDUCTION_OR_ORDER_MANAGEMENT,
            RiskClass.RISK_REDUCING,
            "REDUCE_OR_CLOSE_MARKET",
        ),
    ),
)
def test_each_action_stop_category_rejects_only_its_mapped_action(
    category: StopCategory,
    risk_class: RiskClass,
    profile: str,
) -> None:
    action = _action(
        action_profile=profile,
        control_category=category,
        risk_class=risk_class,
        current_abs_position="1",
        post_action_abs_position="0.5",
    )
    stopped = check_action(
        action,
        account=_account(),
        authorization=_authorization(),
        allocation=_allocation(),
        stop_states=(_stop(category),),
    )
    assert stopped.accepted is False
    assert stopped.reason_code == "ACTION_CATEGORY_STOPPED"
    assert stopped.stopped_categories == (category,)


def test_activation_loss_is_isolated_and_latched() -> None:
    loss = compute_activation_loss(
        realized_pnl="-40",
        unrealized_pnl="-50",
        funding="2",
        commission="12",
    )
    assert loss == Decimal("100")
    latched = latch_max_loss(
        _allocation(),
        activation_loss=loss,
        fact_cutoff=NOW,
        funding_query_cutoff=NOW - timedelta(minutes=1),
        fact_digest="d" * 64,
    )
    assert latched.max_loss_reached is True
    assert latched.status is AllocationStatus.EXIT_ONLY
    assert latched.loss_latch_digest is not None
    assert latched.loss_fact_cutoff == NOW
    assert latched.funding_query_cutoff == NOW - timedelta(minutes=1)
    assert latched.state_version == 2
    replay = latch_max_loss(
        latched,
        activation_loss=Decimal("90"),
        fact_cutoff=NOW + timedelta(minutes=1),
        funding_query_cutoff=NOW,
        fact_digest="e" * 64,
    )
    assert replay.max_loss_reached is True
    assert replay.status is AllocationStatus.EXIT_ONLY
    assert replay.activation_loss == "90"
    assert replay.loss_latch_digest == latched.loss_latch_digest
    assert replay.state_version == 3
    with pytest.raises(ValueError, match="LOSS_FACT_CUTOFF_REGRESSION"):
        latch_max_loss(
            replay,
            activation_loss=Decimal("100"),
            fact_cutoff=NOW,
            funding_query_cutoff=NOW - timedelta(minutes=1),
            fact_digest="f" * 64,
        )
