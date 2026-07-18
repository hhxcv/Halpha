"""The one shared exact-Decimal CAP check used at proposal and write boundaries."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Iterable

from halpha.capital.models import (
    AccountCapitalLimitVersion,
    ActionCheckInput,
    AllocationRequest,
    AllocationStatus,
    CapDecision,
    MachineAuthorizationVersion,
    PlanAllocation,
    RiskClass,
    StopCategory,
    StopStateVersion,
)
from halpha.domain_values import canonical_decimal, content_digest, decimal_from_string


LEVERAGE_CAP = Decimal("5")


def effective_leverage(actual_margin_mode: str, actual_leverage: str) -> Decimal:
    """Apply the accepted isolated-equivalent 5x cap without mutating the account."""

    if actual_margin_mode not in {"ISOLATED", "CROSSED"}:
        raise ValueError("MARGIN_MODE_UNKNOWN")
    leverage = decimal_from_string(
        actual_leverage,
        code="LEVERAGE_INVALID",
        positive=True,
    )
    return min(leverage, LEVERAGE_CAP)


def allocate_plan(
    account: AccountCapitalLimitVersion,
    existing: Iterable[PlanAllocation],
    request: AllocationRequest,
) -> PlanAllocation:
    if (
        account.environment_id != request.environment_id
        or account.authority_class is not request.authority_class
        or account.account_ref == ""
        or account.capital_limit_version_id != request.capital_limit_version_ref
        or account.quote_asset != request.quote_asset
    ):
        raise ValueError("ALLOCATION_CONFLICT")
    counted = [item for item in existing if item.status is not AllocationStatus.RELEASED]
    for item in counted:
        if (
            item.environment_id != request.environment_id
            or item.authority_class is not request.authority_class
            or item.quote_asset != request.quote_asset
        ):
            raise ValueError("ALLOCATION_CONFLICT")
    axes = (
        ("max_margin", account.max_margin),
        ("max_notional", account.max_notional),
        ("max_allowed_loss", account.max_allowed_loss),
    )
    for field, limit in axes:
        total = sum((Decimal(getattr(item, field)) for item in counted), Decimal("0"))
        total += Decimal(getattr(request, field))
        if total > Decimal(limit):
            raise ValueError("ACCOUNT_LIMIT_EXCEEDED")
    return PlanAllocation(
        **request.model_dump(mode="python"),
        status=AllocationStatus.HELD,
    )


def _applicable_stops(
    action: ActionCheckInput,
    states: Iterable[StopStateVersion],
) -> frozenset[StopCategory]:
    categories: set[StopCategory] = set()
    for state in states:
        if (
            state.environment_id != action.environment_id
            or state.authority_class is not action.authority_class
            or state.account_ref != action.account_ref
        ):
            continue
        if state.activation_id is not None and state.activation_id != action.activation_id:
            continue
        categories.update(state.stopped_categories)
    return frozenset(categories)


def _decision(
    *,
    action: ActionCheckInput,
    accepted: bool,
    reason_code: str,
    leverage: Decimal | None,
    action_notional: Decimal,
    economic_action_notional: Decimal,
    activation_notional_after: Decimal,
    account_notional_after: Decimal,
    activation_margin_after: Decimal,
    stopped: frozenset[StopCategory],
) -> CapDecision:
    input_payload = action.model_dump(mode="python")
    input_digest = content_digest(input_payload)
    fields = {
        "accepted": accepted,
        "reason_code": reason_code,
        "risk_class": action.risk_class,
        "effective_leverage": canonical_decimal(leverage) if leverage is not None else None,
        "action_notional": canonical_decimal(action_notional),
        "economic_action_notional": canonical_decimal(economic_action_notional),
        "activation_notional_after": canonical_decimal(activation_notional_after),
        "account_notional_after": canonical_decimal(account_notional_after),
        "activation_margin_after": canonical_decimal(activation_margin_after),
        "stopped_categories": tuple(sorted(stopped, key=lambda item: item.value)),
        "input_digest": input_digest,
    }
    return CapDecision(**fields, decision_digest=content_digest(fields))


def check_action(
    action: ActionCheckInput,
    *,
    account: AccountCapitalLimitVersion,
    authorization: MachineAuthorizationVersion,
    allocation: PlanAllocation,
    stop_states: Iterable[StopStateVersion] = (),
) -> CapDecision:
    """Check an already venue-quantized action; never performs a venue write."""

    quantity = Decimal(action.quantized_quantity)
    price = Decimal(action.conservative_price)
    action_notional = quantity * price
    economic_notional = Decimal(action.economic_action_prior_notional) + action_notional
    activation_after = Decimal(action.activation_current_notional) + action_notional
    account_after = Decimal(action.account_current_notional) + action_notional
    stopped = _applicable_stops(action, stop_states)
    leverage: Decimal | None = None
    margin_after = Decimal(action.activation_current_margin)

    def reject(code: str) -> CapDecision:
        return _decision(
            action=action,
            accepted=False,
            reason_code=code,
            leverage=leverage,
            action_notional=action_notional,
            economic_action_notional=economic_notional,
            activation_notional_after=activation_after,
            account_notional_after=account_after,
            activation_margin_after=margin_after,
            stopped=stopped,
        )

    authority_values = (account, authorization, allocation)
    if any(
        item.environment_id != action.environment_id
        or item.authority_class is not action.authority_class
        for item in authority_values
    ):
        return reject("AUTHORIZATION_MISMATCH")
    if (
        authorization.activation_id != action.activation_id
        or allocation.activation_id != action.activation_id
        or authorization.account_ref != action.account_ref
        or authorization.instrument_ref != action.instrument_ref
        or account.account_ref != action.account_ref
    ):
        return reject("AUTHORIZATION_MISMATCH")
    if not (authorization.valid_from <= action.checked_at < authorization.valid_until):
        return reject("AUTHORIZATION_EXPIRED")
    if action.action_profile not in authorization.allowed_actions:
        return reject("AUTHORIZATION_MISMATCH")
    if not action.facts_fresh:
        return reject("VALUATION_UNKNOWN")
    if not action.attribution_unambiguous:
        return reject("ATTRIBUTION_UNKNOWN")
    if allocation.status is AllocationStatus.TAKEOVER_HELD:
        return reject("TAKEOVER_ACTIVE")
    if allocation.status is AllocationStatus.RELEASED:
        return reject("ALLOCATION_CONFLICT")
    if StopCategory.ALL_WRITES in stopped:
        return reject("ALL_WRITES_STOPPED")
    if action.control_category in stopped:
        return reject("ACTION_CATEGORY_STOPPED")
    if action.risk_class is RiskClass.AMBIGUOUS:
        return reject("ATTRIBUTION_UNKNOWN")
    if action.risk_class is RiskClass.RISK_INCREASING and allocation.status is not AllocationStatus.HELD:
        return reject("NEW_RISK_STOPPED")
    if action.risk_class is RiskClass.RISK_INCREASING and allocation.max_loss_reached:
        return reject("MAX_LOSS_REACHED")
    if action.risk_class is RiskClass.RISK_REDUCING:
        if action.would_reverse_position or Decimal(action.post_action_abs_position) > Decimal(
            action.current_abs_position
        ):
            return reject("RISK_REDUCTION_UNPROVEN")
        return _decision(
            action=action,
            accepted=True,
            reason_code="ACCEPTED_RISK_REDUCING",
            leverage=None,
            action_notional=action_notional,
            economic_action_notional=economic_notional,
            activation_notional_after=activation_after,
            account_notional_after=account_after,
            activation_margin_after=margin_after,
            stopped=stopped,
        )
    if action.risk_class is RiskClass.RISK_NEUTRAL:
        return _decision(
            action=action,
            accepted=True,
            reason_code="ACCEPTED_RISK_NEUTRAL",
            leverage=None,
            action_notional=action_notional,
            economic_action_notional=economic_notional,
            activation_notional_after=activation_after,
            account_notional_after=account_after,
            activation_margin_after=margin_after,
            stopped=stopped,
        )

    try:
        leverage = effective_leverage(action.actual_margin_mode, action.actual_leverage)
    except ValueError:
        return reject("VALUATION_UNKNOWN")
    margin_after += action_notional / leverage
    if economic_notional > Decimal(account.max_action_notional):
        return reject("ACTION_LIMIT_EXCEEDED")
    if activation_after > Decimal(allocation.max_notional):
        return reject("NOTIONAL_LIMIT_EXCEEDED")
    if account_after > Decimal(account.max_notional):
        return reject("ACCOUNT_LIMIT_EXCEEDED")
    if margin_after > Decimal(allocation.max_margin):
        return reject("MARGIN_LIMIT_EXCEEDED")
    if action_notional / leverage > Decimal(action.account_dynamic_available_margin):
        return reject("MARGIN_LIMIT_EXCEEDED")
    if Decimal(allocation.activation_loss) >= Decimal(allocation.max_allowed_loss):
        return reject("MAX_LOSS_REACHED")
    return _decision(
        action=action,
        accepted=True,
        reason_code="ACCEPTED_RISK_INCREASING",
        leverage=leverage,
        action_notional=action_notional,
        economic_action_notional=economic_notional,
        activation_notional_after=activation_after,
        account_notional_after=account_after,
        activation_margin_after=margin_after,
        stopped=stopped,
    )


def compute_activation_loss(
    *,
    realized_pnl: str,
    unrealized_pnl: str,
    funding: str,
    commission: str,
) -> Decimal:
    realized = decimal_from_string(realized_pnl, code="VALUATION_UNKNOWN")
    unrealized = decimal_from_string(unrealized_pnl, code="VALUATION_UNKNOWN")
    funding_value = decimal_from_string(funding, code="VALUATION_UNKNOWN")
    commission_value = decimal_from_string(
        commission,
        code="VALUATION_UNKNOWN",
        non_negative=True,
    )
    net = realized + unrealized + funding_value - commission_value
    return max(-net, Decimal("0"))


def latch_max_loss(
    allocation: PlanAllocation,
    *,
    activation_loss: Decimal,
    fact_cutoff: datetime,
    funding_query_cutoff: datetime,
    fact_digest: str,
) -> PlanAllocation:
    if activation_loss < 0:
        raise ValueError("VALUATION_UNKNOWN")
    if funding_query_cutoff > fact_cutoff:
        raise ValueError("FUNDING_CUTOFF_AFTER_LOSS_FACT")
    if allocation.loss_fact_cutoff is not None and fact_cutoff < allocation.loss_fact_cutoff:
        raise ValueError("LOSS_FACT_CUTOFF_REGRESSION")
    normalized_loss = canonical_decimal(activation_loss)
    evidence_unchanged = (
        allocation.activation_loss == normalized_loss
        and allocation.loss_fact_cutoff == fact_cutoff
        and allocation.funding_query_cutoff == funding_query_cutoff
    )
    if allocation.max_loss_reached:
        if evidence_unchanged:
            return allocation
        return allocation.model_copy(
            update={
                "activation_loss": normalized_loss,
                "loss_fact_cutoff": fact_cutoff,
                "funding_query_cutoff": funding_query_cutoff,
                "state_version": allocation.state_version + 1,
            }
        )
    if activation_loss < Decimal(allocation.max_allowed_loss):
        if evidence_unchanged:
            return allocation
        return allocation.model_copy(
            update={
                "activation_loss": normalized_loss,
                "loss_fact_cutoff": fact_cutoff,
                "funding_query_cutoff": funding_query_cutoff,
                "state_version": allocation.state_version + 1,
            }
        )
    latch_digest = content_digest(
        {
            "activation_id": allocation.activation_id,
            "activation_loss": activation_loss,
            "max_allowed_loss": allocation.max_allowed_loss,
            "fact_cutoff": fact_cutoff,
            "funding_query_cutoff": funding_query_cutoff,
            "fact_digest": fact_digest,
        }
    )
    return allocation.model_copy(
        update={
            "activation_loss": normalized_loss,
            "loss_fact_cutoff": fact_cutoff,
            "funding_query_cutoff": funding_query_cutoff,
            "max_loss_reached": True,
            "loss_latch_digest": latch_digest,
            "status": AllocationStatus.EXIT_ONLY,
            "state_version": allocation.state_version + 1,
        }
    )
