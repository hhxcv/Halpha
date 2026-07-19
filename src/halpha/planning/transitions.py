"""Pure TRADEPLAN identities, idempotency, and lifecycle transitions."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from enum import StrEnum
from typing import Iterable

from halpha.capital.models import StopCategory
from halpha.domain_values import canonical_decimal, content_digest, decimal_from_string
from halpha.planning.models import (
    PlanActivation,
    PlanEvent,
    PlanLifecycle,
    ProposedAction,
    ProposedActionKind,
    ProtectionState,
    RunState,
)
from halpha.planning.registry import ONE_SHOT_STRATEGY_ID
from halpha.planning.strategies.one_shot import (
    EntryRiskContext,
    RiskDirection,
    StrategyProposal,
)


class ControlIntent(StrEnum):
    STOP_NEW_RISK = "STOP_NEW_RISK"
    RESUME_ACTIVATION = "RESUME_ACTIVATION"
    EXIT_STRATEGY = "EXIT_STRATEGY"
    USER_TAKEOVER = "USER_TAKEOVER"


class EventConflict(ValueError):
    pass


def bar_source_identity(
    *, activation_id: str, rule_id: str, bar_type: str, ts_event_ns: int
) -> str:
    return f"{activation_id}:BAR:{rule_id}:{bar_type}:{ts_event_ns}"


def deadline_source_identity(
    *, activation_id: str, rule_id: str, deadline: datetime
) -> str:
    return f"{activation_id}:DEADLINE:{rule_id}:{deadline.isoformat()}"


def venue_source_identity(
    *,
    activation_id: str,
    rule_id: str,
    source_class: str,
    source_object_id: str,
    source_sequence_or_version: str,
) -> str:
    return (
        f"{activation_id}:VENUE:{rule_id}:{source_class}:"
        f"{source_object_id}:{source_sequence_or_version}"
    )


def user_source_identity(command_id: str) -> str:
    return f"COMMAND:{command_id}"


def proposed_action_from_strategy_proposal(
    activation: PlanActivation,
    proposal: StrategyProposal,
) -> ProposedAction:
    """Normalize the one-shot strategy proposal without granting execution authority."""

    proposal_basis = proposal.model_dump(
        mode="python",
        exclude={"proposal_digest"},
        exclude_none=True,
    )
    if content_digest(proposal_basis) != proposal.proposal_digest:
        raise EventConflict("FACT_CONFLICT")
    if (
        proposal.strategy_id != ONE_SHOT_STRATEGY_ID
        or proposal.strategy_id != activation.strategy_id
        or proposal.activation_id != activation.activation_id
        or proposal.direction is not activation.direction
    ):
        raise ValueError("PLAN_BOUNDARY_MISMATCH")
    if proposal.instrument_id != f"{activation.instrument_ref}.BINANCE":
        raise ValueError("ATTRIBUTION_AMBIGUOUS")
    if (
        proposal.action_profile != "ENTRY_MARKET"
        or proposal.risk_direction is not RiskDirection.INCREASE
    ):
        raise ValueError("STRATEGY_PROPOSAL_UNSUPPORTED")
    return ProposedAction(
        environment_id=activation.environment_id,
        action_kind=ProposedActionKind.ENTRY,
        action_profile=proposal.action_profile,
        instrument_ref=activation.instrument_ref,
        direction=proposal.direction,
        quantity=proposal.quantity,
        close_position=False,
        order_type="MARKET",
        price=None,
        trigger_price=None,
        valid_until=proposal.valid_until,
        reduce_only=False,
        source_responsibility="HALPHA_MONITORED",
        causation_ref=proposal.proposal_digest,
        execution_context={
            "reference_price": proposal.reference_price,
            "reference_source": proposal.reference_source,
            "entry_risk_context": (
                proposal.entry_risk_context.model_dump(mode="json")
                if proposal.entry_risk_context is not None
                else None
            ),
        },
    )


def resolve_existing_event(
    existing: PlanEvent | None,
    *,
    source_identity: str,
    input_digest: str,
) -> PlanEvent | None:
    if existing is None:
        return None
    if existing.source_identity != source_identity:
        raise EventConflict("PLAN_EVENT_IDENTITY_MISMATCH")
    if existing.input_digest != input_digest:
        raise EventConflict("FACT_CONFLICT")
    return existing


def build_plan_event(
    *,
    plan_event_id: str,
    activation: PlanActivation,
    rule_id: str,
    source_identity: str,
    source_cutoff: datetime,
    input_digest: str,
    reason_code: str,
    proposed_action: ProposedAction | None,
    no_action_reason: str | None,
    condition_judgement: object | None,
    capital_decision: dict[str, object],
    created_at: datetime,
) -> PlanEvent:
    capital_digest = content_digest(capital_decision)
    fields = {
        "plan_event_id": plan_event_id,
        "environment_id": activation.environment_id,
        "activation_id": activation.activation_id,
        "rule_id": rule_id,
        "source_identity": source_identity,
        "source_cutoff": source_cutoff,
        "input_digest": input_digest,
        "reason_code": reason_code,
        "condition_judgement": condition_judgement,
        "proposed_action": proposed_action,
        "no_action_reason": no_action_reason,
        "capital_decision": capital_decision,
        "capital_decision_digest": capital_digest,
        "created_at": created_at,
    }
    return PlanEvent(**fields, content_digest=content_digest(fields))


def mark_writer_continuity_lost(
    activation: PlanActivation,
    *,
    observed_at: datetime,
) -> PlanActivation:
    if activation.lifecycle in {PlanLifecycle.COMPLETED, PlanLifecycle.USER_TAKEOVER}:
        return activation
    if activation.run_state is RunState.PAUSED:
        return activation
    return activation.model_copy(
        update={
            "run_state": RunState.PAUSED,
            "pause_reason": "WRITER_CONTINUITY_LOST",
            "paused_at": observed_at,
            "reconciliation_digest": None,
            "current_resume_command_ref": None,
            "state_version": activation.state_version + 1,
            "updated_at": observed_at,
        }
    )


def callback_allowed(activation: PlanActivation) -> bool:
    return (
        activation.run_state is RunState.ACTIVE
        and activation.lifecycle not in {PlanLifecycle.COMPLETED, PlanLifecycle.USER_TAKEOVER}
    )


def resume_activation(
    activation: PlanActivation,
    *,
    command_id: str,
    reconciliation_digest: str,
    observed_at: datetime,
    active_stop_categories: Iterable[StopCategory],
    plan_current: bool,
    facts_known: bool,
) -> PlanActivation:
    if activation.run_state is RunState.ACTIVE:
        return activation
    if activation.lifecycle in {
        PlanLifecycle.EXITING,
        PlanLifecycle.USER_TAKEOVER,
        PlanLifecycle.COMPLETED,
        PlanLifecycle.UNKNOWN,
    }:
        raise ValueError("RESUME_BLOCKED_BY_LIFECYCLE")
    stops = frozenset(active_stop_categories)
    if StopCategory.ALL_EXCHANGE_CHANGES in stops:
        raise ValueError("ALL_EXCHANGE_CHANGES_STOPPED")
    if not plan_current:
        raise ValueError("PLAN_EXPIRED")
    if not facts_known:
        raise ValueError("FACT_UNKNOWN")
    return activation.model_copy(
        update={
            "run_state": RunState.ACTIVE,
            "pause_reason": None,
            "paused_at": None,
            "reconciliation_digest": reconciliation_digest,
            "current_resume_command_ref": command_id,
            "state_version": activation.state_version + 1,
            "updated_at": observed_at,
        }
    )


def enter_exit(activation: PlanActivation, *, observed_at: datetime) -> PlanActivation:
    if activation.lifecycle is PlanLifecycle.USER_TAKEOVER:
        raise ValueError("TAKEOVER_ACTIVE")
    if activation.lifecycle is PlanLifecycle.COMPLETED:
        raise ValueError("CLOSURE_ALREADY_COMPLETED")
    if activation.lifecycle is PlanLifecycle.EXITING:
        return activation
    return activation.model_copy(
        update={
            "lifecycle": PlanLifecycle.EXITING,
            "entry_opportunity_consumed": True,
            "state_version": activation.state_version + 1,
            "updated_at": observed_at,
        }
    )


def enter_user_takeover(
    activation: PlanActivation,
    *,
    takeover_scope: dict[str, object],
    observed_at: datetime,
) -> PlanActivation:
    if activation.lifecycle is PlanLifecycle.COMPLETED:
        raise ValueError("CLOSURE_ALREADY_COMPLETED")
    if activation.lifecycle is PlanLifecycle.USER_TAKEOVER:
        return activation
    return activation.model_copy(
        update={
            "lifecycle": PlanLifecycle.USER_TAKEOVER,
            "responsibility_owner": "USER",
            "entry_opportunity_consumed": True,
            "takeover_scope": takeover_scope,
            "state_version": activation.state_version + 1,
            "updated_at": observed_at,
        }
    )


def consume_entry_opportunity(
    activation: PlanActivation,
    *,
    observed_at: datetime,
) -> PlanActivation:
    if activation.entry_opportunity_consumed:
        return activation
    return activation.model_copy(
        update={
            "entry_opportunity_consumed": True,
            "state_version": activation.state_version + 1,
            "updated_at": observed_at,
        }
    )


def update_protection_projection(
    activation: PlanActivation,
    *,
    protection_state: ProtectionState,
    pending_action_digest: str | None,
    observed_at: datetime,
) -> PlanActivation:
    allowed = {
        ProtectionState.NONE: {ProtectionState.UNKNOWN, ProtectionState.GAP},
        ProtectionState.UNKNOWN: {
            ProtectionState.WORKING,
            ProtectionState.GAP,
            ProtectionState.CLOSED,
        },
        ProtectionState.GAP: {ProtectionState.WORKING, ProtectionState.CLOSED},
        ProtectionState.WORKING: {
            ProtectionState.UNKNOWN,
            ProtectionState.GAP,
            ProtectionState.CLOSED,
        },
        ProtectionState.CLOSED: set(),
    }
    if protection_state is activation.protection_state:
        return activation
    if protection_state not in allowed[activation.protection_state]:
        raise ValueError("PROTECTION_STATE_INVALID")
    return activation.model_copy(
        update={
            "protection_state": protection_state,
            "pending_action_digest": pending_action_digest,
            "state_version": activation.state_version + 1,
            "updated_at": observed_at,
        }
    )


def record_first_fill(
    activation: PlanActivation,
    *,
    entry_action_ref: str,
    fill_fact_ref: str,
    fill_price: str,
    fill_time: datetime,
    entry_risk_context: dict[str, object],
    observed_at: datetime,
) -> PlanActivation:
    """Freeze the first-fill R values once inside PlanActivation.rule_state."""

    context = EntryRiskContext.model_validate(entry_risk_context)
    price = decimal_from_string(fill_price, code="FILL_VALUE_INVALID", positive=True)
    stop_distance = Decimal(context.trigger_atr) * Decimal(
        context.initial_stop_atr_multiple
    )
    frozen = {
        "entry_action_ref": entry_action_ref,
        "first_fill_fact_ref": fill_fact_ref,
        "first_fill_price": canonical_decimal(price),
        "first_fill_time": fill_time.isoformat(),
        "trigger_atr": context.trigger_atr,
        "R": canonical_decimal(stop_distance),
        "time_exit_due_at": (
            fill_time + timedelta(minutes=15 * context.max_hold_bars_15m)
        ).isoformat(),
        "entry_risk_context": context.model_dump(mode="json"),
    }
    rule_state = dict(activation.rule_state)
    existing = rule_state.get("first_fill")
    if existing is not None:
        if not isinstance(existing, dict) or content_digest(existing) != content_digest(frozen):
            # Later partial fills legitimately have different fact/price/time. They
            # must reuse the already frozen first-fill context, not overwrite it.
            if (
                not isinstance(existing, dict)
                or existing.get("entry_action_ref") != entry_action_ref
                or existing.get("entry_risk_context")
                != context.model_dump(mode="json")
            ):
                raise EventConflict("FACT_CONFLICT")
        return activation
    rule_state["first_fill"] = frozen
    return activation.model_copy(
        update={
            "has_entry_fill": True,
            "entry_opportunity_consumed": True,
            "rule_state": rule_state,
            "state_version": activation.state_version + 1,
            "updated_at": observed_at,
        }
    )


def proposed_protection_from_fill(
    activation: PlanActivation,
    *,
    entry_action_ref: str,
    fill_fact_ref: str,
    fill_source_identity: str,
    fill_quantity: str,
) -> ProposedAction:
    """Form one explicit-quantity protection responsibility for one confirmed fill."""

    frozen = _first_fill_context(activation, entry_action_ref)
    context = EntryRiskContext.model_validate(frozen["entry_risk_context"])
    quantity = decimal_from_string(
        fill_quantity,
        code="FILL_VALUE_INVALID",
        positive=True,
    )
    first_price = Decimal(str(frozen["first_fill_price"]))
    risk_distance = Decimal(str(frozen["R"]))
    tick = Decimal(context.price_tick_size)
    raw_stop = (
        first_price - risk_distance
        if activation.direction.value == "LONG"
        else first_price + risk_distance
    )
    stop = _quantize_price(
        raw_stop,
        tick,
        round_up=activation.direction.value == "SHORT",
    )
    if stop <= 0:
        raise ValueError("PROTECTION_GAP")
    causation = content_digest(
        {
            "entry_action_ref": entry_action_ref,
            "fill_fact_ref": fill_fact_ref,
            "fill_source_identity": fill_source_identity,
            "fill_quantity": quantity,
            "first_fill_digest": content_digest(frozen),
            "responsibility": "PROTECTION",
        }
    )
    return ProposedAction(
        environment_id=activation.environment_id,
        action_kind=ProposedActionKind.PROTECTION,
        action_profile="PROTECTIVE_STOP_REDUCE_ONLY",
        instrument_ref=activation.instrument_ref,
        direction=activation.direction,
        quantity=canonical_decimal(quantity),
        close_position=False,
        order_type="STOP_MARKET",
        trigger_price=canonical_decimal(stop),
        valid_until=None,
        reduce_only=True,
        source_responsibility="NONE",
        causation_ref=causation,
        execution_context={
            "entry_action_ref": entry_action_ref,
            "fill_fact_ref": fill_fact_ref,
            "fill_source_identity": fill_source_identity,
            "first_fill": frozen,
        },
    )


def proposed_take_profits_from_fill(
    activation: PlanActivation,
    *,
    entry_action_ref: str,
    protection_action_ref: str,
    fill_fact_ref: str,
    fill_source_identity: str,
    fill_quantity: str,
) -> tuple[ProposedAction, ProposedAction]:
    """Form the two fixed reduce-only TP responsibilities after protection works."""

    frozen = _first_fill_context(activation, entry_action_ref)
    context = EntryRiskContext.model_validate(frozen["entry_risk_context"])
    quantity = decimal_from_string(fill_quantity, code="FILL_VALUE_INVALID", positive=True)
    step = Decimal(context.quantity_step)
    tp1_quantity = _floor_to_step(
        quantity * Decimal(context.take_profit_1_fraction),
        step,
    )
    tp2_quantity = _floor_to_step(quantity - tp1_quantity, step)
    if tp1_quantity <= 0 or tp2_quantity <= 0 or tp1_quantity + tp2_quantity != quantity:
        raise ValueError("TAKE_PROFIT_SPLIT_INVALID")
    first_price = Decimal(str(frozen["first_fill_price"]))
    risk_distance = Decimal(str(frozen["R"]))
    tick = Decimal(context.price_tick_size)
    direction_sign = Decimal("1") if activation.direction.value == "LONG" else Decimal("-1")
    prices = (
        first_price + direction_sign * risk_distance * Decimal(context.take_profit_1_r),
        first_price + direction_sign * risk_distance * Decimal(context.take_profit_2_r),
    )
    triggers = tuple(
        _quantize_price(
            price,
            tick,
            round_up=activation.direction.value == "SHORT",
        )
        for price in prices
    )
    if any(price <= 0 for price in triggers):
        raise ValueError("TAKE_PROFIT_SPLIT_INVALID")
    results = []
    for profile, tp_quantity, trigger in zip(
        ("TAKE_PROFIT_1", "TAKE_PROFIT_2"),
        (tp1_quantity, tp2_quantity),
        triggers,
        strict=True,
    ):
        causation = content_digest(
            {
                "entry_action_ref": entry_action_ref,
                "protection_action_ref": protection_action_ref,
                "fill_fact_ref": fill_fact_ref,
                "fill_source_identity": fill_source_identity,
                "profile": profile,
                "quantity": tp_quantity,
                "trigger": trigger,
            }
        )
        results.append(
            ProposedAction(
                environment_id=activation.environment_id,
                action_kind=ProposedActionKind.TAKE_PROFIT,
                action_profile=profile,
                instrument_ref=activation.instrument_ref,
                direction=activation.direction,
                quantity=canonical_decimal(tp_quantity),
                close_position=False,
                order_type="MARKET_IF_TOUCHED",
                trigger_price=canonical_decimal(trigger),
                valid_until=datetime.fromisoformat(str(frozen["time_exit_due_at"])),
                reduce_only=True,
                source_responsibility="NONE",
                causation_ref=causation,
                execution_context={
                    "entry_action_ref": entry_action_ref,
                    "protection_action_ref": protection_action_ref,
                    "fill_fact_ref": fill_fact_ref,
                    "fill_source_identity": fill_source_identity,
                    "first_fill": frozen,
                },
            )
        )
    return results[0], results[1]


def proposed_cancel_for_action(
    activation: PlanActivation,
    *,
    target_client_order_id: str,
    target_endpoint: str,
    causation_ref: str,
) -> ProposedAction:
    """Form one stable cancel responsibility for an already persisted identity."""

    if len(target_client_order_id) != 32 or any(
        character not in "0123456789abcdef" for character in target_client_order_id
    ):
        raise ValueError("CANCEL_TARGET_INVALID")
    if target_endpoint not in {"ORDINARY", "ALGO"}:
        raise ValueError("CANCEL_TARGET_INVALID")
    return ProposedAction(
        environment_id=activation.environment_id,
        action_kind=ProposedActionKind.CANCEL,
        action_profile="CANCEL_ORDER",
        instrument_ref=activation.instrument_ref,
        direction=activation.direction,
        quantity=None,
        close_position=False,
        order_type="CANCEL",
        reduce_only=False,
        source_responsibility="NONE",
        causation_ref=causation_ref,
        cancel_target={
            "client_order_id": target_client_order_id,
            "endpoint": target_endpoint,
        },
    )


def proposed_reduce_or_close_position(
    activation: PlanActivation,
    *,
    position_quantity: str,
    causation_ref: str,
    position_fact_ref: str,
) -> ProposedAction:
    """Form the explicit-quantity reduce-only market exit responsibility."""

    quantity = decimal_from_string(
        position_quantity,
        code="POSITION_UNKNOWN",
        positive=True,
    )
    return ProposedAction(
        environment_id=activation.environment_id,
        action_kind=ProposedActionKind.EXIT,
        action_profile="REDUCE_OR_CLOSE_MARKET",
        instrument_ref=activation.instrument_ref,
        direction=activation.direction,
        quantity=canonical_decimal(quantity),
        close_position=False,
        order_type="MARKET",
        reduce_only=True,
        source_responsibility="NONE",
        causation_ref=causation_ref,
        execution_context={"position_fact_ref": position_fact_ref},
    )


def _first_fill_context(
    activation: PlanActivation,
    entry_action_ref: str,
) -> dict[str, object]:
    frozen = activation.rule_state.get("first_fill")
    if not isinstance(frozen, dict) or frozen.get("entry_action_ref") != entry_action_ref:
        raise ValueError("PROTECTION_UNKNOWN")
    return frozen


def _floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def _quantize_price(value: Decimal, tick: Decimal, *, round_up: bool) -> Decimal:
    return (value / tick).to_integral_value(
        rounding=ROUND_UP if round_up else ROUND_DOWN
    ) * tick


def complete_activation(
    activation: PlanActivation,
    *,
    closure_digest: str,
    result_ref: str,
    observed_at: datetime,
) -> PlanActivation:
    if not closure_digest:
        raise ValueError("CLOSURE_UNPROVEN")
    return activation.model_copy(
        update={
            "lifecycle": PlanLifecycle.COMPLETED,
            "run_state": RunState.ACTIVE,
            "pause_reason": None,
            "paused_at": None,
            "entry_opportunity_consumed": True,
            "closure_digest": closure_digest,
            "result_ref": result_ref,
            "state_version": activation.state_version + 1,
            "updated_at": observed_at,
        }
    )
