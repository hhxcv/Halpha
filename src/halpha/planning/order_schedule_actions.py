"""Pure materialization of one immutable order schedule into entry intentions."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict

from halpha.domain_values import canonical_decimal, content_digest
from halpha.planning.models import PlanActivation, ProposedAction, ProposedActionKind
from halpha.planning.order_schedule import (
    CompiledOrderLeg,
    OrderSchedulePreview,
    ScheduleSubmissionOrder,
    VenueOrderType,
    validate_order_schedule_snapshot,
)
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


def _ordered_legs(snapshot: OrderSchedulePreview) -> tuple[CompiledOrderLeg, ...]:
    if (
        snapshot.schedule_spec.submission_order
        is ScheduleSubmissionOrder.HIGH_TO_LOW
    ):
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
                "ENTRY_MARKET"
                if order_type is VenueOrderType.MARKET
                else "ENTRY_LIMIT"
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
