"""Exact virtual positions derived from activation-owned actions and venue facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from types import SimpleNamespace
from typing import Any, Callable, Iterable, Mapping, Sequence

from halpha.domain_values import canonical_decimal
from halpha.planning.models import PlanActivation
from halpha.planning.registry import Direction
from halpha.venue_integration.facts import collapse_synthetic_reconciliation_fills
from halpha.venue_integration.models import (
    ExecutionAction,
    ExecutionActionKind,
    ExecutionActionState,
    VenueFact,
    VenueFactKind,
)


_REDUCING_KINDS = frozenset(
    {
        ExecutionActionKind.PROTECTION,
        ExecutionActionKind.TAKE_PROFIT,
        ExecutionActionKind.RISK_REDUCTION,
        ExecutionActionKind.EXIT,
    }
)
_OPEN_ACTION_STATES = frozenset(
    {
        ExecutionActionState.READY,
        ExecutionActionState.SUBMITTING,
        ExecutionActionState.UNKNOWN,
        ExecutionActionState.OPEN,
    }
)


@dataclass(frozen=True, slots=True)
class ActivationPositionAttribution:
    activation_id: str
    signed_position: str
    outstanding_entry_quantity: str
    outstanding_entry_notional: str
    ordinary_client_ids: frozenset[str]
    algo_client_ids: frozenset[str]
    fill_fact_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AccountInstrumentAttribution:
    environment_id: str
    account_ref: str
    instrument_ref: str
    activation_id: str
    activation_signed_position: str
    account_signed_position: str
    account_outstanding_entry_notional: str
    activation_ordinary_client_ids: frozenset[str]
    activation_algo_client_ids: frozenset[str]
    account_ordinary_client_ids: frozenset[str]
    account_algo_client_ids: frozenset[str]
    activation_fill_fact_refs: tuple[str, ...]
    account_fill_fact_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FundingAllocation:
    activation_id: str
    signed_position: str
    income: str


def activation_position_attribution(
    activation: PlanActivation,
    actions: Iterable[ExecutionAction],
    facts_for_action: Callable[[str], Iterable[VenueFact]],
    *,
    as_of: datetime | None = None,
) -> ActivationPositionAttribution:
    """Derive one activation's virtual position without using account net position."""

    sign = Decimal(1) if activation.direction is Direction.LONG else Decimal(-1)
    alignment = getattr(activation, "position_alignment", None)
    position = (
        sign * Decimal(alignment.requested_reduction_quantity)
        if alignment is not None
        else Decimal(0)
    )
    outstanding_quantity = Decimal(0)
    outstanding_notional = Decimal(0)
    ordinary: set[str] = set()
    algo: set[str] = set()
    fill_refs: list[str] = []
    seen_fill_refs: set[str] = set()
    for action in actions:
        if as_of is not None and action.created_at > as_of:
            continue
        if (
            action.activation_id != activation.activation_id
            or action.account_ref != activation.account_ref
        ):
            raise ValueError("ACTIVATION_ACTION_ATTRIBUTION_CONFLICT")
        if action.client_order_id is not None:
            if action.action_kind in {
                ExecutionActionKind.PROTECTION,
                ExecutionActionKind.TAKE_PROFIT,
            }:
                algo.add(action.client_order_id)
            elif action.action_kind is not ExecutionActionKind.CANCEL:
                ordinary.add(action.client_order_id)
        filled = Decimal(0)
        for fact in collapse_synthetic_reconciliation_fills(
            facts_for_action(action.execution_action_id)
        ):
            if fact.kind is not VenueFactKind.FILL:
                continue
            if as_of is not None:
                if fact.source_time is None:
                    raise ValueError("ACTIVATION_FILL_TIME_UNKNOWN")
                if fact.source_time > as_of:
                    continue
            if (
                fact.action_ref != action.execution_action_id
                or fact.activation_ref != activation.activation_id
                or fact.venue_fact_id in seen_fill_refs
            ):
                raise ValueError("ACTIVATION_FILL_ATTRIBUTION_CONFLICT")
            try:
                quantity = Decimal(str(fact.payload["last_quantity"]))
            except (InvalidOperation, KeyError, TypeError, ValueError):
                raise ValueError("ACTIVATION_FILL_QUANTITY_INVALID") from None
            if not quantity.is_finite() or quantity <= 0:
                raise ValueError("ACTIVATION_FILL_QUANTITY_INVALID")
            seen_fill_refs.add(fact.venue_fact_id)
            fill_refs.append(fact.venue_fact_id)
            filled += quantity
        if action.action_kind is ExecutionActionKind.ENTRY:
            position += sign * filled
            if action.state in _OPEN_ACTION_STATES:
                try:
                    requested = Decimal(str(action.action_terms["quantity"]))
                    remaining = max(Decimal(0), requested - filled)
                    context = action.action_terms.get("execution_context", {})
                    schedule = (
                        context.get("order_schedule", {})
                        if isinstance(context, dict)
                        else {}
                    )
                    price = action.action_terms.get("price") or schedule.get(
                        "sizing_price"
                    )
                    if price is None:
                        raise ValueError
                    price_value = Decimal(str(price))
                except (InvalidOperation, KeyError, TypeError, ValueError):
                    raise ValueError("ACTIVATION_OPEN_ENTRY_INVALID") from None
                if requested <= 0 or price_value <= 0:
                    raise ValueError("ACTIVATION_OPEN_ENTRY_INVALID")
                outstanding_quantity += remaining
                outstanding_notional += remaining * price_value
        elif action.action_kind in _REDUCING_KINDS:
            position -= sign * filled
    if sign * position < 0:
        raise ValueError("ACTIVATION_POSITION_OVER_REDUCED")
    return ActivationPositionAttribution(
        activation_id=activation.activation_id,
        signed_position=canonical_decimal(position),
        outstanding_entry_quantity=canonical_decimal(outstanding_quantity),
        outstanding_entry_notional=canonical_decimal(outstanding_notional),
        ordinary_client_ids=frozenset(ordinary),
        algo_client_ids=frozenset(algo),
        fill_fact_refs=tuple(fill_refs),
    )


def account_instrument_attribution(
    target: PlanActivation,
    activations: Iterable[PlanActivation],
    actions_for_activation: Callable[[str], Iterable[ExecutionAction]],
    facts_for_action: Callable[[str], Iterable[VenueFact]],
    *,
    as_of: datetime | None = None,
) -> AccountInstrumentAttribution:
    """Aggregate same-direction virtual positions and preserve target ownership."""

    matching = tuple(
        activation
        for activation in activations
        if activation.environment_id == target.environment_id
        and activation.account_ref == target.account_ref
        and activation.instrument_ref == target.instrument_ref
    )
    if not any(item.activation_id == target.activation_id for item in matching):
        matching = (*matching, target)
    results = tuple(
        activation_position_attribution(
            activation,
            actions_for_activation(activation.activation_id),
            facts_for_action,
            as_of=as_of,
        )
        for activation in matching
    )
    active_directions = {
        activation.direction
        for activation, result in zip(matching, results, strict=True)
        if Decimal(result.signed_position) != 0
        or Decimal(result.outstanding_entry_quantity) != 0
    }
    if len(active_directions) > 1:
        raise ValueError("ACCOUNT_INSTRUMENT_DIRECTION_CONFLICT")
    target_result = next(
        item for item in results if item.activation_id == target.activation_id
    )
    return AccountInstrumentAttribution(
        environment_id=target.environment_id,
        account_ref=target.account_ref,
        instrument_ref=target.instrument_ref,
        activation_id=target.activation_id,
        activation_signed_position=target_result.signed_position,
        account_signed_position=canonical_decimal(
            sum((Decimal(item.signed_position) for item in results), Decimal(0))
        ),
        account_outstanding_entry_notional=canonical_decimal(
            sum(
                (
                    Decimal(item.outstanding_entry_notional)
                    for item in results
                ),
                Decimal(0),
            )
        ),
        activation_ordinary_client_ids=target_result.ordinary_client_ids,
        activation_algo_client_ids=target_result.algo_client_ids,
        account_ordinary_client_ids=frozenset().union(
            *(item.ordinary_client_ids for item in results)
        ),
        account_algo_client_ids=frozenset().union(
            *(item.algo_client_ids for item in results)
        ),
        activation_fill_fact_refs=target_result.fill_fact_refs,
        account_fill_fact_refs=tuple(
            fact_ref
            for item in results
            for fact_ref in item.fill_fact_refs
        ),
    )


def account_instrument_attribution_from_rows(
    target: PlanActivation,
    activations: Iterable[PlanActivation],
    action_rows: Iterable[Sequence[Any]],
    fact_rows: Iterable[Sequence[Any]],
) -> AccountInstrumentAttribution:
    """Build the read projection from narrow SQL rows without EXE repositories.

    Action row shape:
    ``activation_id, execution_action_id, account_ref, action_kind,
    action_terms, client_order_id, state, created_at``.

    Fact row shape:
    ``venue_fact_id, action_ref, activation_ref, kind, payload, source_time``.
    """

    actions_by_activation: dict[str, list[SimpleNamespace]] = {}
    for row in action_rows:
        if len(row) != 8:
            raise ValueError("ATTRIBUTION_ACTION_ROW_INVALID")
        action = SimpleNamespace(
            activation_id=str(row[0]),
            execution_action_id=str(row[1]),
            account_ref=str(row[2]),
            action_kind=ExecutionActionKind(str(row[3])),
            action_terms=dict(row[4]),
            client_order_id=(
                str(row[5]) if row[5] is not None else None
            ),
            state=ExecutionActionState(str(row[6])),
            created_at=row[7],
        )
        actions_by_activation.setdefault(action.activation_id, []).append(
            action
        )
    facts_by_action: dict[str, list[SimpleNamespace]] = {}
    for row in fact_rows:
        if len(row) != 6:
            raise ValueError("ATTRIBUTION_FACT_ROW_INVALID")
        fact = SimpleNamespace(
            venue_fact_id=str(row[0]),
            action_ref=str(row[1]) if row[1] is not None else None,
            activation_ref=(
                str(row[2]) if row[2] is not None else None
            ),
            kind=VenueFactKind(str(row[3])),
            payload=dict(row[4]),
            source_time=row[5],
        )
        if fact.action_ref is not None:
            facts_by_action.setdefault(fact.action_ref, []).append(fact)
    return account_instrument_attribution(
        target,
        activations,
        lambda activation_id: tuple(
            actions_by_activation.get(activation_id, ())
        ),
        lambda action_id: tuple(facts_by_action.get(action_id, ())),
    )


def allocate_funding_income(
    income: str,
    signed_positions: Mapping[str, str],
) -> tuple[FundingAllocation, ...]:
    """Allocate one exact venue funding amount by absolute virtual position."""

    try:
        amount = Decimal(income)
        positions = {
            activation_id: Decimal(quantity)
            for activation_id, quantity in signed_positions.items()
            if Decimal(quantity) != 0
        }
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("FUNDING_ALLOCATION_INPUT_INVALID") from None
    if not amount.is_finite() or any(
        not value.is_finite() for value in positions.values()
    ):
        raise ValueError("FUNDING_ALLOCATION_INPUT_INVALID")
    if not positions:
        if amount == 0:
            return ()
        raise ValueError("FUNDING_ALLOCATION_POSITION_UNKNOWN")
    directions = {value > 0 for value in positions.values()}
    if len(directions) != 1:
        raise ValueError("FUNDING_ALLOCATION_DIRECTION_CONFLICT")
    total_position = sum((abs(value) for value in positions.values()), Decimal(0))
    unit = Decimal(1).scaleb(amount.as_tuple().exponent)
    total_units = int((abs(amount) / unit).to_integral_exact())
    bases: dict[str, int] = {}
    remainders: list[tuple[Decimal, str]] = []
    for activation_id, position in positions.items():
        raw_units = Decimal(total_units) * abs(position) / total_position
        base_units = int(raw_units.to_integral_value(rounding=ROUND_FLOOR))
        bases[activation_id] = base_units
        remainders.append((raw_units - Decimal(base_units), activation_id))
    residual_units = total_units - sum(bases.values())
    for _remainder, activation_id in sorted(
        remainders,
        key=lambda item: (-item[0], item[1]),
    )[:residual_units]:
        bases[activation_id] += 1
    sign = Decimal(-1) if amount < 0 else Decimal(1)
    allocations = tuple(
        FundingAllocation(
            activation_id=activation_id,
            signed_position=canonical_decimal(positions[activation_id]),
            income=canonical_decimal(sign * unit * bases[activation_id]),
        )
        for activation_id in sorted(positions)
    )
    if sum((Decimal(item.income) for item in allocations), Decimal(0)) != amount:
        raise ValueError("FUNDING_ALLOCATION_RECONCILIATION_FAILED")
    return allocations
