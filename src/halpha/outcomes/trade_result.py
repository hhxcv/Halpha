"""Calculate a small user-facing result from attributed fill and fee facts."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from halpha.domain_values import canonical_decimal


_EXTERNAL_CLOSURE = "EXTERNAL_ACCOUNT_CLOSURE"
_REDUCING_ACTIONS = frozenset(
    {"PROTECTION", "TAKE_PROFIT", "EXIT", _EXTERNAL_CLOSURE}
)


@dataclass
class _AttributedFill:
    action_kind: str
    price: Decimal
    quantity: Decimal
    order_side: str | None
    liquidity_side: str | None
    source_time: datetime | None


def summarize_trade_result(
    *,
    direction: str,
    action_kinds: Mapping[str, str],
    facts: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return P&L inputs only when every attributed fill has an actual fee fact."""

    fills: dict[str, _AttributedFill] = {}
    fill_conflicts: set[str] = set()
    metadata_conflicts: dict[str, set[str]] = {}
    commissions: dict[str, tuple[Decimal, str]] = {}
    commission_conflicts: set[str] = set()
    valid = direction in {"LONG", "SHORT"}
    for fact in facts:
        kind = str(fact.get("kind", ""))
        payload = fact.get("payload")
        if not isinstance(payload, Mapping):
            if kind in {"FILL", "COMMISSION"}:
                valid = False
            continue
        trade_id = str(payload.get("trade_id", ""))
        if kind == "FILL":
            action_ref = fact.get("action_ref")
            action_kind = action_kinds.get(str(action_ref), "")
            if action_ref is None and fact.get("result_role") == _EXTERNAL_CLOSURE:
                action_kind = _EXTERNAL_CLOSURE
            try:
                price = _positive_decimal(payload.get("last_price"))
                quantity = _positive_decimal(payload.get("last_quantity"))
            except ValueError:
                valid = False
                continue
            fill = _AttributedFill(
                action_kind=action_kind,
                price=price,
                quantity=quantity,
                order_side=_optional_text(payload.get("order_side")),
                liquidity_side=_optional_text(payload.get("liquidity_side")),
                source_time=_source_datetime(fact.get("source_time")),
            )
            if not trade_id or action_kind not in {"ENTRY", *_REDUCING_ACTIONS}:
                valid = False
            elif trade_id in fills:
                existing = fills[trade_id]
                if (
                    existing.action_kind,
                    existing.price,
                    existing.quantity,
                ) != (fill.action_kind, fill.price, fill.quantity):
                    valid = False
                    fill_conflicts.add(trade_id)
                else:
                    conflicts = metadata_conflicts.setdefault(trade_id, set())
                    _merge_optional_fill_value(
                        existing,
                        fill,
                        field="order_side",
                        conflicts=conflicts,
                    )
                    _merge_optional_fill_value(
                        existing,
                        fill,
                        field="liquidity_side",
                        conflicts=conflicts,
                    )
                    _merge_optional_fill_value(
                        existing,
                        fill,
                        field="source_time",
                        conflicts=conflicts,
                    )
            else:
                fills[trade_id] = fill
        elif kind == "COMMISSION":
            try:
                amount = _non_negative_decimal(payload.get("amount"))
            except ValueError:
                valid = False
                continue
            currency = str(payload.get("currency", ""))
            commission = (amount, currency)
            if not trade_id or currency != "USDT":
                valid = False
            elif trade_id in commissions and commissions[trade_id] != commission:
                valid = False
                commission_conflicts.add(trade_id)
            else:
                commissions[trade_id] = commission

    position_quantity = Decimal("0")
    fill_cash_flow = Decimal("0")
    entry_quantity = Decimal("0")
    entry_notional = Decimal("0")
    exit_quantity = Decimal("0")
    exit_notional = Decimal("0")
    for fill in fills.values():
        increasing = fill.action_kind == "ENTRY"
        price = fill.price
        quantity = fill.quantity
        signed_quantity = quantity if increasing == (direction == "LONG") else -quantity
        position_quantity += signed_quantity
        fill_cash_flow -= signed_quantity * price
        if increasing:
            entry_quantity += quantity
            entry_notional += quantity * price
        else:
            exit_quantity += quantity
            exit_notional += quantity * price

    commission_total = sum(
        (amount for amount, _currency in commissions.values()),
        Decimal("0"),
    )
    commission_complete = (
        bool(fills)
        and set(fills) == set(commissions)
        and not set(fills).intersection(commission_conflicts)
    )
    calculation_complete = valid and commission_complete
    closed = bool(fills) and position_quantity == 0
    gross_pnl = fill_cash_flow if closed and calculation_complete else None
    net_pnl = (
        gross_pnl - commission_total if gross_pnl is not None else None
    )
    fill_details = [
        _fill_detail(
            trade_id,
            fill,
            commission=commissions.get(trade_id),
            core_conflict=trade_id in fill_conflicts,
            metadata_conflicts=metadata_conflicts.get(trade_id, set()),
            commission_conflict=trade_id in commission_conflicts,
        )
        for trade_id, fill in fills.items()
    ]
    reliable_fill_times = [
        _reliable_fill_time(
            trade_id,
            fill,
            fill_conflicts=fill_conflicts,
            metadata_conflicts=metadata_conflicts,
        )
        for trade_id, fill in fills.items()
    ]
    fill_times_complete = bool(fills) and all(
        value is not None for value in reliable_fill_times
    )
    first_fill_time = (
        min(value for value in reliable_fill_times if value is not None)
        if fill_times_complete
        else None
    )
    last_fill_time = (
        max(value for value in reliable_fill_times if value is not None)
        if fill_times_complete
        else None
    )
    holding_duration = _holding_duration(
        fills,
        reliable_fill_times,
        closed=closed,
        fill_times_complete=fill_times_complete,
    )
    external_closure_count = sum(
        fill.action_kind == _EXTERNAL_CLOSURE for fill in fills.values()
    )
    return {
        "fill_count": len(fills),
        "fills": fill_details,
        "position_quantity": canonical_decimal(position_quantity),
        "average_entry_price": (
            canonical_decimal(entry_notional / entry_quantity)
            if entry_quantity > 0
            else None
        ),
        "average_exit_price": (
            canonical_decimal(exit_notional / exit_quantity)
            if exit_quantity > 0
            else None
        ),
        "entry_notional": canonical_decimal(entry_notional),
        "fill_cash_flow": canonical_decimal(fill_cash_flow),
        "commission": canonical_decimal(commission_total),
        "commission_complete": commission_complete,
        "calculation_complete": calculation_complete,
        "closed": closed,
        "gross_pnl": canonical_decimal(gross_pnl) if gross_pnl is not None else None,
        "net_pnl": canonical_decimal(net_pnl) if net_pnl is not None else None,
        "currency": "USDT",
        "funding_included": False,
        "fill_times_complete": fill_times_complete,
        "first_fill_time": _isoformat(first_fill_time),
        "last_fill_time": _isoformat(last_fill_time),
        "holding_duration_seconds": (
            canonical_decimal(holding_duration)
            if holding_duration is not None
            else None
        ),
        "result_scope": (
            "ACCOUNT_FACTS_WITH_EXTERNAL_CLOSURE"
            if external_closure_count
            else "HALPHA_ATTRIBUTED_ACTIONS"
        ),
        "external_closure_fill_count": external_closure_count,
        "strategy_attribution_complete": external_closure_count == 0,
    }


def _fill_detail(
    trade_id: str,
    fill: _AttributedFill,
    *,
    commission: tuple[Decimal, str] | None,
    core_conflict: bool,
    metadata_conflicts: set[str],
    commission_conflict: bool,
) -> dict[str, str | None]:
    price = None if core_conflict else fill.price
    quantity = None if core_conflict else fill.quantity
    fee = None if commission_conflict or commission is None else commission[0]
    return {
        "trade_id": trade_id,
        "action_kind": None if core_conflict else fill.action_kind,
        "price": canonical_decimal(price) if price is not None else None,
        "quantity": canonical_decimal(quantity) if quantity is not None else None,
        "notional": (
            canonical_decimal(price * quantity)
            if price is not None and quantity is not None
            else None
        ),
        "order_side": (
            None
            if core_conflict or "order_side" in metadata_conflicts
            else fill.order_side
        ),
        "liquidity_side": (
            None
            if core_conflict or "liquidity_side" in metadata_conflicts
            else fill.liquidity_side
        ),
        "fee": canonical_decimal(fee) if fee is not None else None,
        "fee_currency": (
            commission[1]
            if commission is not None and not commission_conflict
            else None
        ),
        "fill_time": _isoformat(
            None
            if core_conflict or "source_time" in metadata_conflicts
            else fill.source_time
        ),
    }


def _reliable_fill_time(
    trade_id: str,
    fill: _AttributedFill,
    *,
    fill_conflicts: set[str],
    metadata_conflicts: Mapping[str, set[str]],
) -> datetime | None:
    if trade_id in fill_conflicts or "source_time" in metadata_conflicts.get(
        trade_id, set()
    ):
        return None
    return fill.source_time


def _holding_duration(
    fills: Mapping[str, _AttributedFill],
    reliable_fill_times: list[datetime | None],
    *,
    closed: bool,
    fill_times_complete: bool,
) -> Decimal | None:
    if not closed or not fill_times_complete:
        return None
    entry_times = [
        fill_time
        for fill, fill_time in zip(fills.values(), reliable_fill_times, strict=True)
        if fill.action_kind == "ENTRY" and fill_time is not None
    ]
    reducing_times = [
        fill_time
        for fill, fill_time in zip(fills.values(), reliable_fill_times, strict=True)
        if fill.action_kind in _REDUCING_ACTIONS and fill_time is not None
    ]
    if not entry_times or not reducing_times:
        return None
    first_entry = min(entry_times)
    last_reduction = max(reducing_times)
    if last_reduction < first_entry:
        return None
    return Decimal(str((last_reduction - first_entry).total_seconds()))


def _merge_optional_fill_value(
    existing: _AttributedFill,
    incoming: _AttributedFill,
    *,
    field: str,
    conflicts: set[str],
) -> None:
    existing_value = getattr(existing, field)
    incoming_value = getattr(incoming, field)
    if existing_value is None:
        setattr(existing, field, incoming_value)
    elif incoming_value is not None and incoming_value != existing_value:
        conflicts.add(field)


def _source_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        token = value.strip()
        if token.endswith("Z"):
            token = f"{token[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(token)
        except ValueError:
            return None
    else:
        return None
    return parsed if parsed.utcoffset() is not None else None


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    return rendered or None


def _positive_decimal(value: Any) -> Decimal:
    parsed = _decimal(value)
    if parsed <= 0:
        raise ValueError("TRADE_RESULT_NUMBER_INVALID")
    return parsed


def _non_negative_decimal(value: Any) -> Decimal:
    parsed = _decimal(value)
    if parsed < 0:
        raise ValueError("TRADE_RESULT_NUMBER_INVALID")
    return parsed


def _decimal(value: Any) -> Decimal:
    token = str(value).strip().split(maxsplit=1)[0] if str(value).strip() else ""
    try:
        parsed = Decimal(token)
    except (InvalidOperation, ValueError):
        raise ValueError("TRADE_RESULT_NUMBER_INVALID") from None
    if not parsed.is_finite():
        raise ValueError("TRADE_RESULT_NUMBER_INVALID")
    return parsed
