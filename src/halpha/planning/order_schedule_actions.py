"""Pure materialization of one immutable order schedule into entry intentions."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict

from halpha.domain_values import canonical_decimal, content_digest
from halpha.planning.models import PlanActivation, ProposedAction, ProposedActionKind
from halpha.planning.order_schedule import (
    CompiledOrderLeg,
    EntryProgramKind,
    OrderSchedulePreview,
    ScheduleSubmissionOrder,
    VenueOrderType,
    validate_order_schedule_snapshot,
)
from halpha.planning.order_policies import RepriceEntryRule
from halpha.planning.registry import DIRECT_EXECUTION_REF


class ScheduleActionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MaterializedOrderLeg(ScheduleActionModel):
    submission_index: int
    leg: CompiledOrderLeg
    source_identity: str
    input_digest: str
    plan_event_id: str
    execution_action_id: str
    client_order_id: str
    economic_action_prior_notional: str
    proposed_action: ProposedAction


def _stable_uuid(
    environment_id: str,
    activation_id: str,
    schedule_digest: str,
    leg_index: int,
    kind: str,
) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            (
                f"urn:halpha:{environment_id}:{kind}:{activation_id}:"
                f"{schedule_digest}:{leg_index}"
            ),
        )
    )


def _stable_attempt_uuid(
    environment_id: str,
    activation_id: str,
    schedule_digest: str,
    leg_index: int,
    attempt_index: int,
    kind: str,
) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            (
                f"urn:halpha:{environment_id}:{kind}:{activation_id}:"
                f"{schedule_digest}:{leg_index}:attempt:{attempt_index}"
            ),
        )
    )


def _ordered_legs(snapshot: OrderSchedulePreview) -> tuple[CompiledOrderLeg, ...]:
    if (
        snapshot.schedule_spec.resolved_entry_program.kind
        is EntryProgramKind.TIME_SLICED
    ):
        return snapshot.legs
    if snapshot.schedule_spec.submission_order is ScheduleSubmissionOrder.HIGH_TO_LOW:
        return tuple(reversed(snapshot.legs))
    return snapshot.legs


def materialize_direct_schedule(
    activation: PlanActivation,
    *,
    entry_valid_until: datetime,
) -> tuple[MaterializedOrderLeg, ...]:
    """Build stable direct-entry intentions without database or venue access."""

    if activation.decision_basis_ref != DIRECT_EXECUTION_REF:
        raise ValueError("DIRECT_EXECUTION_BASIS_REQUIRED")
    snapshot = activation.order_schedule_snapshot
    if snapshot is None:
        raise ValueError("ORDER_SCHEDULE_SNAPSHOT_REQUIRED")
    validate_order_schedule_snapshot(snapshot)
    if (
        snapshot.schedule_ref != activation.plan_version_ref
        or snapshot.instrument_ref != activation.instrument_ref
        or snapshot.direction is not activation.direction
        or entry_valid_until.utcoffset() is None
        or entry_valid_until <= activation.created_at
    ):
        raise ValueError("ORDER_SCHEDULE_SNAPSHOT_MISMATCH")
    spec = snapshot.schedule_spec
    if spec.protection_policy is None:
        raise ValueError("DIRECT_EXECUTION_PROTECTION_REQUIRED")
    venue_policy = spec.venue_policy.model_dump(mode="json")
    ordered = _ordered_legs(snapshot)
    prior_notional = Decimal(0)
    results: list[MaterializedOrderLeg] = []
    for submission_index, leg in enumerate(ordered):
        source_identity = (
            f"{activation.activation_id}:ORDER_SCHEDULE:"
            f"{snapshot.schedule_digest}:LEG:{leg.leg_index}"
        )
        schedule_context = {
            "schedule_ref": snapshot.schedule_ref,
            "schedule_digest": snapshot.schedule_digest,
            "leg_index": leg.leg_index,
            "leg_count": leg.leg_count,
            "release_after_seconds": leg.release_after_seconds,
            "submission_index": submission_index,
            "submission_mode": spec.submission_mode.value,
            "submission_order": spec.submission_order.value,
            "instrument_rules_digest": snapshot.instrument_rules_digest,
            "price_tick_size": snapshot.instrument_rules.price_tick_size,
            "quantity_step": (
                snapshot.instrument_rules.market_quantity_step
                if spec.venue_policy.order_type is VenueOrderType.MARKET
                else snapshot.instrument_rules.limit_quantity_step
            ),
            "sizing_price": leg.sizing_price,
        }
        causation_ref = content_digest(
            {
                "activation_id": activation.activation_id,
                "source_identity": source_identity,
                "schedule": schedule_context,
                "leg": leg.model_dump(mode="json"),
            }
        )
        valid_until = entry_valid_until
        if (
            spec.venue_policy.expire_at is not None
            and spec.venue_policy.expire_at < valid_until
        ):
            valid_until = spec.venue_policy.expire_at
        order_type = spec.venue_policy.order_type
        proposed = ProposedAction(
            environment_id=activation.environment_id,
            action_kind=ProposedActionKind.ENTRY,
            action_profile=(
                "ENTRY_MARKET" if order_type is VenueOrderType.MARKET else "ENTRY_LIMIT"
            ),
            instrument_ref=activation.instrument_ref,
            direction=activation.direction,
            quantity=leg.quantity,
            close_position=False,
            order_type=order_type.value,
            # priceMatch still needs a local Nautilus LimitOrder price. The
            # venue policy tells the Binance adapter to omit it on the wire.
            price=(
                None
                if order_type is VenueOrderType.MARKET
                else leg.price or leg.sizing_price
            ),
            trigger_price=None,
            valid_until=valid_until,
            reduce_only=False,
            source_responsibility="HALPHA_MONITORED",
            causation_ref=causation_ref,
            execution_context={
                "order_schedule": schedule_context,
                "venue_policy": venue_policy,
                "protection_policy": spec.protection_policy.model_dump(mode="json"),
                "dynamic_rules": [
                    rule.model_dump(mode="json") for rule in spec.dynamic_rules
                ],
            },
        )
        input_digest = content_digest(
            {
                "schedule_digest": snapshot.schedule_digest,
                "source_identity": source_identity,
                "leg": leg.model_dump(mode="json"),
                "entry_valid_until": entry_valid_until,
            }
        )
        plan_event_id = _stable_uuid(
            activation.environment_id,
            activation.activation_id,
            snapshot.schedule_digest,
            leg.leg_index,
            "plan-event-order-schedule",
        )
        execution_action_id = _stable_uuid(
            activation.environment_id,
            activation.activation_id,
            snapshot.schedule_digest,
            leg.leg_index,
            "execution-action-order-schedule",
        )
        client_order_id = uuid5(
            NAMESPACE_URL,
            (
                f"urn:halpha:{activation.environment_id}:client-order-order-schedule:"
                f"{activation.activation_id}:{snapshot.schedule_digest}:{leg.leg_index}"
            ),
        ).hex
        results.append(
            MaterializedOrderLeg(
                submission_index=submission_index,
                leg=leg,
                source_identity=source_identity,
                input_digest=input_digest,
                plan_event_id=plan_event_id,
                execution_action_id=execution_action_id,
                client_order_id=client_order_id,
                economic_action_prior_notional=canonical_decimal(prior_notional),
                proposed_action=proposed,
            )
        )
        prior_notional += Decimal(leg.effective_notional)
    return tuple(results)


def materialize_direct_schedule_retry(
    activation: PlanActivation,
    base: MaterializedOrderLeg,
    *,
    attempt_index: int,
    retry_reason: Literal[
        "POST_ONLY_WOULD_TAKE_RACE",
        "PRICE_MATCH_TEMPORARILY_UNAVAILABLE",
    ] = "POST_ONLY_WOULD_TAKE_RACE",
    replacement_price: str | None = None,
    reprice_index: int = 0,
) -> MaterializedOrderLeg:
    """Derive one stable retry identity without mutating the frozen order terms."""

    return materialize_direct_schedule_attempt(
        activation,
        base,
        attempt_index=attempt_index,
        retry_reason=retry_reason,
        replacement_price=replacement_price,
        reprice_index=reprice_index,
    )


def materialize_direct_schedule_reprice(
    activation: PlanActivation,
    base: MaterializedOrderLeg,
    *,
    attempt_index: int,
    replacement_price: str,
    reprice_index: int,
) -> MaterializedOrderLeg:
    """Derive one stable cancel-confirm-replace entry attempt."""

    return materialize_direct_schedule_attempt(
        activation,
        base,
        attempt_index=attempt_index,
        retry_reason="ENTRY_REPRICE",
        replacement_price=replacement_price,
        reprice_index=reprice_index,
    )


def materialize_direct_schedule_attempt(
    activation: PlanActivation,
    base: MaterializedOrderLeg,
    *,
    attempt_index: int,
    retry_reason: Literal[
        "POST_ONLY_WOULD_TAKE_RACE",
        "PRICE_MATCH_TEMPORARILY_UNAVAILABLE",
        "ENTRY_REPRICE",
    ],
    replacement_price: str | None = None,
    reprice_index: int = 0,
) -> MaterializedOrderLeg:
    """Derive one stable retry or bounded replacement from the frozen first leg."""

    if attempt_index < 1 or activation.order_schedule_snapshot is None:
        raise ValueError("ORDER_SCHEDULE_RETRY_INVALID")
    snapshot = activation.order_schedule_snapshot
    authoritative = {
        item.leg.leg_index: item
        for item in materialize_direct_schedule(
            activation,
            entry_valid_until=base.proposed_action.valid_until,
        )
    }
    expected_base = authoritative.get(base.leg.leg_index)
    if expected_base != base:
        raise ValueError("ORDER_SCHEDULE_RETRY_BASE_MISMATCH")
    reprice_rule = next(
        (
            rule
            for rule in snapshot.schedule_spec.dynamic_rules
            if isinstance(rule, RepriceEntryRule)
        ),
        None,
    )
    if retry_reason == "ENTRY_REPRICE" and (
        reprice_rule is None or replacement_price is None or reprice_index < 1
    ):
        raise ValueError("ORDER_SCHEDULE_REPRICE_INVALID")
    if replacement_price is None:
        if reprice_index != 0:
            raise ValueError("ORDER_SCHEDULE_REPRICE_INVALID")
        normalized_replacement_price = None
    else:
        if reprice_rule is None or reprice_index < 1:
            raise ValueError("ORDER_SCHEDULE_REPRICE_INVALID")
        if reprice_index > reprice_rule.max_adjustments:
            raise ValueError("ORDER_SCHEDULE_REPRICE_LIMIT_EXCEEDED")
        try:
            replacement = Decimal(replacement_price)
            original = Decimal(str(base.proposed_action.price))
            tick = Decimal(snapshot.instrument_rules.price_tick_size)
            min_price = Decimal(snapshot.instrument_rules.min_price)
            max_price = Decimal(snapshot.instrument_rules.max_price)
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("ORDER_SCHEDULE_REPRICE_INVALID") from None
        if (
            replacement <= 0
            or original <= 0
            or tick <= 0
            or replacement < min_price
            or replacement > max_price
            or replacement % tick != 0
            or (
                abs(replacement - original)
                * Decimal(10_000)
                / original
                > Decimal(reprice_rule.maximum_total_move_bps)
            )
        ):
            raise ValueError("ORDER_SCHEDULE_REPRICE_INVALID")
        normalized_replacement_price = canonical_decimal(replacement)
    source_identity = f"{base.source_identity}:ATTEMPT:{attempt_index}"
    execution_context = dict(base.proposed_action.execution_context)
    schedule_context = dict(execution_context.get("order_schedule", {}))
    schedule_context["attempt_index"] = attempt_index
    schedule_context["retry_reason"] = retry_reason
    if normalized_replacement_price is not None:
        schedule_context["replacement_price"] = normalized_replacement_price
        schedule_context["reprice_index"] = reprice_index
    execution_context["order_schedule"] = schedule_context
    causation_ref = content_digest(
        {
            "activation_id": activation.activation_id,
            "base_causation_ref": base.proposed_action.causation_ref,
            "attempt_index": attempt_index,
            "retry_reason": retry_reason,
            "replacement_price": normalized_replacement_price,
            "reprice_index": reprice_index,
        }
    )
    proposed_action = base.proposed_action.model_copy(
        update={
            "causation_ref": causation_ref,
            "execution_context": execution_context,
            "price": normalized_replacement_price or base.proposed_action.price,
        }
    )
    input_digest = content_digest(
        {
            "base_input_digest": base.input_digest,
            "attempt_index": attempt_index,
            "retry_reason": retry_reason,
            "replacement_price": normalized_replacement_price,
            "reprice_index": reprice_index,
        }
    )
    return base.model_copy(
        update={
            "source_identity": source_identity,
            "input_digest": input_digest,
            "plan_event_id": _stable_attempt_uuid(
                activation.environment_id,
                activation.activation_id,
                snapshot.schedule_digest,
                base.leg.leg_index,
                attempt_index,
                "plan-event-order-schedule-retry",
            ),
            "execution_action_id": _stable_attempt_uuid(
                activation.environment_id,
                activation.activation_id,
                snapshot.schedule_digest,
                base.leg.leg_index,
                attempt_index,
                "execution-action-order-schedule-retry",
            ),
            "client_order_id": uuid5(
                NAMESPACE_URL,
                (
                    f"urn:halpha:{activation.environment_id}:"
                    "client-order-order-schedule-retry:"
                    f"{activation.activation_id}:{snapshot.schedule_digest}:"
                    f"{base.leg.leg_index}:{attempt_index}"
                ),
            ).hex,
            "proposed_action": proposed_action,
        }
    )
