from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from halpha.capital.checks import (
    check_action,
    effective_leverage,
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
        "actual_margin_mode": "ISOLATED",
        "actual_leverage": "5",
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


def test_new_risk_supports_crossed_and_isolated_margin_with_same_plan_boundary() -> None:
    crossed = check_action(
        _action(actual_margin_mode="CROSSED"),
        boundary=_boundary(),
    )
    higher_actual_leverage = check_action(
        _action(actual_leverage="20"),
        boundary=_boundary(),
    )
    reducing = check_action(
        _action(
            action_profile="REDUCE_OR_CLOSE_MARKET",
            control_category=StopCategory.RISK_REDUCTION_OR_ORDER_MANAGEMENT,
            risk_class=RiskClass.RISK_REDUCING,
            actual_margin_mode="CROSSED",
            actual_leverage="20",
            current_abs_position="1",
            post_action_abs_position="0.5",
        ),
        boundary=_boundary(),
    )

    assert crossed.reason_code == "ACCEPTED_RISK_INCREASING"
    assert crossed.effective_leverage == "5"
    assert higher_actual_leverage.reason_code == "ACCEPTED_RISK_INCREASING"
    assert higher_actual_leverage.effective_leverage == "5"
    assert reducing.reason_code == "ACCEPTED_RISK_REDUCING"


def test_account_external_activity_stop_blocks_entry_but_allows_proven_reduction() -> None:
    account_stop = _stop(StopCategory.NEW_RISK, activation_id=None).model_copy(
        update={"source": "SYSTEM_EXTERNAL_ACTIVITY"}
    )
    entry = check_action(
        _action(),
        boundary=_boundary(),
        stop_states=(account_stop,),
    )
    reducing = check_action(
        _action(
            action_profile="REDUCE_OR_CLOSE_MARKET",
            control_category=StopCategory.RISK_REDUCTION_OR_ORDER_MANAGEMENT,
            risk_class=RiskClass.RISK_REDUCING,
            quantized_quantity="0.5",
            current_abs_position="1",
            post_action_abs_position="0.5",
            attribution_unambiguous=True,
        ),
        boundary=_boundary(),
        stop_states=(account_stop,),
    )

    assert entry.reason_code == "ACTION_CATEGORY_STOPPED"
    assert reducing.reason_code == "ACCEPTED_RISK_REDUCING"


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


def test_owned_cancel_remains_allowed_after_exit_stops_new_risk() -> None:
    cancel = _action(
        action_profile="CANCEL_ORDER",
        control_category=StopCategory.RISK_REDUCTION_OR_ORDER_MANAGEMENT,
        risk_class=RiskClass.RISK_NEUTRAL,
        quantized_quantity="0",
        conservative_price="1",
        current_abs_position="0",
        post_action_abs_position="0",
    )

    decision = check_action(
        cancel,
        boundary=_boundary(lifecycle="EXITING"),
        stop_states=(_stop(StopCategory.NEW_RISK),),
    )

    assert decision.accepted is True
    assert decision.reason_code == "ACCEPTED_RISK_NEUTRAL"


def test_owned_cancel_does_not_wait_for_market_or_position_wide_facts() -> None:
    cancel = _action(
        action_profile="CANCEL_ORDER",
        control_category=StopCategory.RISK_REDUCTION_OR_ORDER_MANAGEMENT,
        risk_class=RiskClass.RISK_NEUTRAL,
        quantized_quantity="0",
        conservative_price="1",
        current_abs_position="0",
        post_action_abs_position="0",
        facts_fresh=False,
        attribution_unambiguous=False,
    )

    decision = check_action(cancel, boundary=_boundary())

    assert decision.accepted is True
    assert decision.reason_code == "ACCEPTED_RISK_NEUTRAL"


def test_expired_plan_blocks_new_risk_but_not_reduction_or_owned_cancel() -> None:
    expired = _boundary(
        valid_from=NOW - timedelta(days=1),
        valid_until=NOW - timedelta(seconds=1),
        lifecycle="EXITING",
    )
    reducing = _action(
        action_profile="REDUCE_OR_CLOSE_MARKET",
        control_category=StopCategory.RISK_REDUCTION_OR_ORDER_MANAGEMENT,
        risk_class=RiskClass.RISK_REDUCING,
        current_abs_position="1",
        post_action_abs_position="0.9",
    )
    cancel = _action(
        action_profile="CANCEL_ORDER",
        control_category=StopCategory.RISK_REDUCTION_OR_ORDER_MANAGEMENT,
        risk_class=RiskClass.RISK_NEUTRAL,
        quantized_quantity="0",
        conservative_price="1",
        current_abs_position="1",
        post_action_abs_position="1",
    )

    assert check_action(_action(), boundary=expired).reason_code == "PLAN_EXPIRED"
    assert check_action(reducing, boundary=expired).reason_code == (
        "ACCEPTED_RISK_REDUCING"
    )
    assert check_action(cancel, boundary=expired).reason_code == (
        "ACCEPTED_RISK_NEUTRAL"
    )


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


def test_action_check_does_not_claim_an_unimplemented_runtime_loss_latch() -> None:
    decision = check_action(
        _action(),
        boundary=_boundary(max_allowed_loss="1"),
        stop_states=(),
    )

    assert decision.accepted is True
    assert decision.reason_code == "ACCEPTED_RISK_INCREASING"
