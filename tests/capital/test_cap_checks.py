from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from halpha.capital.checks import (
    check_action,
    compute_activation_loss,
    effective_leverage,
    update_activation_capital_state,
)
from halpha.capital.models import (
    ActivationCapitalBoundary,
    ActionCheckInput,
    AuthorityClass,
    EnvironmentKind,
    RiskClass,
    StopCategory,
    StopStateVersion,
)


NOW = datetime(2026, 7, 17, 8, tzinfo=UTC)


def _boundary(**updates: object) -> ActivationCapitalBoundary:
    values: dict[str, object] = {
        "activation_id": "activation-1",
        "environment_id": "demo-1",
        "environment_kind": EnvironmentKind.DEMO,
        "authority_class": AuthorityClass.DEMO_VALIDATION,
        "account_ref": "account-1",
        "instrument_ref": "BTCUSDT-PERP",
        "valid_from": NOW - timedelta(minutes=1),
        "valid_until": NOW + timedelta(days=1),
        "allowed_actions": frozenset({"ENTRY_MARKET", "REDUCE_OR_CLOSE_MARKET"}),
        "max_margin": "200",
        "max_notional": "1000",
        "max_allowed_loss": "100",
        "activation_loss": "0",
        "lifecycle": "RUNNING",
        "responsibility_owner": "HALPHA",
    }
    values.update(updates)
    return ActivationCapitalBoundary(**values)


def _action(**updates: object) -> ActionCheckInput:
    values: dict[str, object] = {
        "environment_id": "demo-1",
        "environment_kind": EnvironmentKind.DEMO,
        "authority_class": AuthorityClass.DEMO_VALIDATION,
        "activation_id": "activation-1",
        "account_ref": "account-1",
        "instrument_ref": "BTCUSDT-PERP",
        "action_profile": "ENTRY_MARKET",
        "control_category": StopCategory.NEW_RISK,
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


def _stop(
    *categories: StopCategory,
    activation_id: str | None = "activation-1",
) -> StopStateVersion:
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


def test_actual_account_mode_is_never_upscaled() -> None:
    assert effective_leverage("CROSSED", "20") == Decimal("5")
    assert effective_leverage("ISOLATED", "3") == Decimal("3")
    with pytest.raises(ValueError, match="MARGIN_MODE_UNKNOWN"):
        effective_leverage("UNKNOWN", "5")


def test_plan_amount_is_the_only_notional_boundary() -> None:
    decision = check_action(_action(), boundary=_boundary())
    assert decision.accepted is True
    assert decision.effective_leverage == "5"
    assert decision.action_notional == "500"

    aggregate_reject = check_action(
        _action(activation_current_notional="600"),
        boundary=_boundary(),
    )
    assert aggregate_reject.reason_code == "NOTIONAL_LIMIT_EXCEEDED"


def test_split_retry_and_partial_fill_cannot_bypass_plan_amount() -> None:
    decision = check_action(
        _action(economic_action_prior_notional="700"),
        boundary=_boundary(),
    )
    assert decision.accepted is False
    assert decision.reason_code == "ACTION_LIMIT_EXCEEDED"
    assert decision.economic_action_notional == "1200"


def test_natural_overrun_only_blocks_increase_and_reduction_cannot_reverse() -> None:
    increasing = check_action(
        _action(activation_current_notional="1100"),
        boundary=_boundary(),
    )
    reducing_action = _action(
        action_profile="REDUCE_OR_CLOSE_MARKET",
        control_category=StopCategory.RISK_REDUCTION_OR_ORDER_MANAGEMENT,
        risk_class=RiskClass.RISK_REDUCING,
        activation_current_notional="1100",
        current_abs_position="1",
        post_action_abs_position="0.5",
    )
    reducing = check_action(reducing_action, boundary=_boundary())
    reverse = check_action(
        reducing_action.model_copy(update={"would_reverse_position": True}),
        boundary=_boundary(),
    )
    assert increasing.reason_code == "NOTIONAL_LIMIT_EXCEEDED"
    assert reducing.accepted is True
    assert reverse.reason_code == "RISK_REDUCTION_UNPROVEN"


def test_stop_categories_union_and_all_exchange_changes_precedence() -> None:
    protection = check_action(
        _action(control_category=StopCategory.PROTECTION),
        boundary=_boundary(),
        stop_states=(_stop(StopCategory.NEW_RISK),),
    )
    all_changes = check_action(
        _action(),
        boundary=_boundary(),
        stop_states=(
            _stop(StopCategory.NEW_RISK),
            _stop(StopCategory.ALL_EXCHANGE_CHANGES, activation_id=None),
        ),
    )
    assert protection.accepted is True
    assert all_changes.reason_code == "ALL_EXCHANGE_CHANGES_STOPPED"
    assert all_changes.stopped_categories == (
        StopCategory.ALL_EXCHANGE_CHANGES,
        StopCategory.NEW_RISK,
    )


@pytest.mark.parametrize(
    ("category", "risk_class", "profile"),
    (
        (StopCategory.NEW_RISK, RiskClass.RISK_INCREASING, "ENTRY_MARKET"),
        (StopCategory.PROTECTION, RiskClass.RISK_REDUCING, "REDUCE_OR_CLOSE_MARKET"),
        (
            StopCategory.RISK_REDUCTION_OR_ORDER_MANAGEMENT,
            RiskClass.RISK_REDUCING,
            "REDUCE_OR_CLOSE_MARKET",
        ),
    ),
)
def test_each_stop_category_rejects_only_its_mapped_action(
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
        boundary=_boundary(),
        stop_states=(_stop(category),),
    )
    assert stopped.accepted is False
    assert stopped.reason_code == "ACTION_CATEGORY_STOPPED"
    assert stopped.stopped_categories == (category,)


def test_activation_loss_is_isolated_and_latched_in_activation_state() -> None:
    loss = compute_activation_loss(
        realized_pnl="-40",
        unrealized_pnl="-50",
        funding="2",
        commission="12",
    )
    assert loss == Decimal("100")
    latched = update_activation_capital_state(
        {"activation_loss": "0", "max_loss_reached": False},
        activation_id="activation-1",
        max_allowed_loss="100",
        activation_loss=loss,
        fact_cutoff=NOW,
        funding_query_cutoff=NOW - timedelta(minutes=1),
        fact_digest="d" * 64,
    )
    assert latched["max_loss_reached"] is True
    assert latched["loss_latch_digest"]
    assert latched["loss_fact_cutoff"] == NOW.isoformat()

    replay = update_activation_capital_state(
        latched,
        activation_id="activation-1",
        max_allowed_loss="100",
        activation_loss=Decimal("90"),
        fact_cutoff=NOW + timedelta(minutes=1),
        funding_query_cutoff=NOW,
        fact_digest="e" * 64,
    )
    assert replay["max_loss_reached"] is True
    assert replay["activation_loss"] == "90"
    assert replay["loss_latch_digest"] == latched["loss_latch_digest"]
    with pytest.raises(ValueError, match="LOSS_FACT_CUTOFF_REGRESSION"):
        update_activation_capital_state(
            replay,
            activation_id="activation-1",
            max_allowed_loss="100",
            activation_loss=Decimal("100"),
            fact_cutoff=NOW,
            funding_query_cutoff=NOW - timedelta(minutes=1),
            fact_digest="f" * 64,
        )
