"""Normalize an explicitly selected external account closure for one review.

The facts remain unclaimed account facts.  The impact scope links the economic
episode to a review without rewriting the external order as a Halpha action.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from halpha.venue_integration.facts import build_venue_fact
from halpha.venue_integration.models import (
    VenueFact,
    VenueFactKind,
    VenueFactSourceClass,
)


EXTERNAL_ACCOUNT_CLOSURE = "EXTERNAL_ACCOUNT_CLOSURE"


class AccountReconciliationError(ValueError):
    """A selected venue order cannot safely close the requested account episode."""


def build_external_account_closure_facts(
    *,
    environment_id: str,
    account_ref: str,
    instrument_ref: str,
    activation_id: str,
    direction: str,
    open_quantity: str,
    average_entry_price: str,
    attributed_trade_ids: frozenset[str],
    order: Mapping[str, Any],
    trades: Sequence[Mapping[str, Any]],
    observed_at: datetime,
) -> tuple[VenueFact, ...]:
    """Build exact external order/fill/fee facts after conservative validation."""

    if observed_at.utcoffset() is None:
        raise AccountReconciliationError("RECONCILIATION_TIMEZONE_REQUIRED")
    if direction not in {"LONG", "SHORT"}:
        raise AccountReconciliationError("RECONCILIATION_DIRECTION_INVALID")
    expected_quantity = _positive_decimal(open_quantity)
    entry_price = _positive_decimal(average_entry_price)
    symbol = _symbol_for_instrument(instrument_ref)
    order_id = _required_text(order.get("order_id"), "ORDER_ID_MISSING")
    client_order_id = _required_text(
        order.get("client_order_id"), "CLIENT_ORDER_ID_MISSING"
    )
    if str(order.get("symbol", "")) != symbol:
        raise AccountReconciliationError("EXTERNAL_ORDER_INSTRUMENT_MISMATCH")
    if str(order.get("status", "")).upper() != "FILLED":
        raise AccountReconciliationError("EXTERNAL_ORDER_NOT_FILLED")
    if order.get("reduce_only") is not True:
        raise AccountReconciliationError("EXTERNAL_ORDER_NOT_REDUCE_ONLY")
    expected_side = "SELL" if direction == "LONG" else "BUY"
    if str(order.get("side", "")).upper() != expected_side:
        raise AccountReconciliationError("EXTERNAL_ORDER_DIRECTION_MISMATCH")
    if _positive_decimal(order.get("executed_quantity")) != expected_quantity:
        raise AccountReconciliationError("EXTERNAL_ORDER_QUANTITY_MISMATCH")
    if not trades:
        raise AccountReconciliationError("EXTERNAL_ORDER_TRADES_MISSING")

    normalized: list[dict[str, Any]] = []
    total_quantity = Decimal("0")
    realized_pnl = Decimal("0")
    theoretical_pnl = Decimal("0")
    for item in trades:
        trade_id = _required_text(item.get("trade_id"), "TRADE_ID_MISSING")
        if trade_id in attributed_trade_ids:
            raise AccountReconciliationError("EXTERNAL_TRADE_ALREADY_ATTRIBUTED")
        if str(item.get("order_id", "")) != order_id:
            raise AccountReconciliationError("EXTERNAL_TRADE_ORDER_MISMATCH")
        if str(item.get("symbol", "")) != symbol:
            raise AccountReconciliationError("EXTERNAL_TRADE_INSTRUMENT_MISMATCH")
        if str(item.get("side", "")).upper() != expected_side:
            raise AccountReconciliationError("EXTERNAL_TRADE_DIRECTION_MISMATCH")
        price = _positive_decimal(item.get("price"))
        quantity = _positive_decimal(item.get("quantity"))
        fee = _non_negative_decimal(item.get("commission"))
        if str(item.get("commission_asset", "")) != "USDT":
            raise AccountReconciliationError("EXTERNAL_COMMISSION_CURRENCY_UNSUPPORTED")
        source_time = _millisecond_time(item.get("time_ms"))
        venue_realized = _decimal(item.get("realized_pnl"))
        calculated = (
            (price - entry_price) * quantity
            if direction == "LONG"
            else (entry_price - price) * quantity
        )
        total_quantity += quantity
        realized_pnl += venue_realized
        theoretical_pnl += calculated
        normalized.append(
            {
                "trade_id": trade_id,
                "price": price,
                "quantity": quantity,
                "commission": fee,
                "source_time": source_time,
                "realized_pnl": venue_realized,
                "liquidity_side": "MAKER" if item.get("maker") is True else "TAKER",
            }
        )
    if total_quantity != expected_quantity:
        raise AccountReconciliationError("EXTERNAL_TRADES_QUANTITY_MISMATCH")
    if realized_pnl != theoretical_pnl:
        raise AccountReconciliationError("EXTERNAL_REALIZED_PNL_MISMATCH")

    impact_scope = {
        "account_episode_activation_id": activation_id,
        "classification": EXTERNAL_ACCOUNT_CLOSURE,
        "association_basis": "EXPLICIT_OPERATOR_ORDER_SELECTION",
        "strategy_attribution": "NOT_ATTRIBUTED",
    }
    affected_refs = (activation_id,)
    source_class = VenueFactSourceClass.VENUE_QUERY
    order_time = _millisecond_time(order.get("update_time_ms"))
    facts: list[VenueFact] = [
        build_venue_fact(
            venue_fact_id=_fact_id(
                environment_id, activation_id, "ORDER_STATE", client_order_id, order_id
            ),
            environment_id=environment_id,
            venue_ref="BINANCE_USDM",
            account_ref=account_ref,
            instrument_ref=instrument_ref,
            kind=VenueFactKind.ORDER_STATE,
            source_class=source_class,
            source_object_id=client_order_id,
            source_sequence=order_id,
            source_time=order_time,
            received_at=observed_at,
            cutoff=observed_at,
            payload={
                "status": "FILLED",
                "client_order_id": client_order_id,
                "venue_order_ref": order_id,
                "order_side": expected_side,
                "order_type": str(order.get("order_type", "")),
                "executed_quantity": str(expected_quantity),
                "average_price": str(order.get("average_price", "")),
                "reduce_only": True,
                "external_account_closure": True,
            },
            impact_scope=impact_scope,
            affected_reference_refs=affected_refs,
        )
    ]
    for item in normalized:
        trade_id = str(item["trade_id"])
        source_time = item["source_time"]
        fill_sequence = f"{order_id}:{trade_id}"
        facts.append(
            build_venue_fact(
                venue_fact_id=_fact_id(
                    environment_id, activation_id, "FILL", trade_id, fill_sequence
                ),
                environment_id=environment_id,
                venue_ref="BINANCE_USDM",
                account_ref=account_ref,
                instrument_ref=instrument_ref,
                kind=VenueFactKind.FILL,
                source_class=source_class,
                source_object_id=trade_id,
                source_sequence=fill_sequence,
                source_time=source_time,
                received_at=observed_at,
                cutoff=observed_at,
                payload={
                    "trade_id": trade_id,
                    "last_price": str(item["price"]),
                    "last_quantity": str(item["quantity"]),
                    "order_side": expected_side,
                    "liquidity_side": item["liquidity_side"],
                    "client_order_id": client_order_id,
                    "venue_order_ref": order_id,
                    "realized_pnl": str(item["realized_pnl"]),
                    "external_account_closure": True,
                },
                impact_scope=impact_scope,
                affected_reference_refs=affected_refs,
            )
        )
        commission_sequence = f"{fill_sequence}:COMMISSION"
        facts.append(
            build_venue_fact(
                venue_fact_id=_fact_id(
                    environment_id,
                    activation_id,
                    "COMMISSION",
                    trade_id,
                    commission_sequence,
                ),
                environment_id=environment_id,
                venue_ref="BINANCE_USDM",
                account_ref=account_ref,
                instrument_ref=instrument_ref,
                kind=VenueFactKind.COMMISSION,
                source_class=source_class,
                source_object_id=trade_id,
                source_sequence=commission_sequence,
                source_time=source_time,
                received_at=observed_at,
                cutoff=observed_at,
                payload={
                    "trade_id": trade_id,
                    "amount": f"{item['commission']} USDT",
                    "currency": "USDT",
                    "client_order_id": client_order_id,
                    "external_account_closure": True,
                },
                impact_scope=impact_scope,
                affected_reference_refs=affected_refs,
            )
        )
    return tuple(facts)


def account_result_role(impact_scope: object) -> str | None:
    if not isinstance(impact_scope, Mapping):
        return None
    if (
        impact_scope.get("classification") == EXTERNAL_ACCOUNT_CLOSURE
        and impact_scope.get("strategy_attribution") == "NOT_ATTRIBUTED"
        and impact_scope.get("association_basis")
        == "EXPLICIT_OPERATOR_ORDER_SELECTION"
    ):
        return EXTERNAL_ACCOUNT_CLOSURE
    return None


def _fact_id(
    environment_id: str,
    activation_id: str,
    kind: str,
    source_object_id: str,
    source_sequence: str,
) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            ":".join(
                (
                    "urn:halpha",
                    environment_id,
                    "account-reconciliation",
                    activation_id,
                    kind,
                    source_object_id,
                    source_sequence,
                )
            ),
        )
    )


def _symbol_for_instrument(instrument_ref: str) -> str:
    suffix = "-PERP"
    if not instrument_ref.endswith(suffix):
        raise AccountReconciliationError("RECONCILIATION_INSTRUMENT_UNSUPPORTED")
    return instrument_ref[: -len(suffix)]


def _millisecond_time(value: Any) -> datetime:
    try:
        milliseconds = int(value)
    except (TypeError, ValueError):
        raise AccountReconciliationError("EXTERNAL_SOURCE_TIME_INVALID") from None
    if milliseconds <= 0:
        raise AccountReconciliationError("EXTERNAL_SOURCE_TIME_INVALID")
    return datetime.fromtimestamp(milliseconds / 1000, tz=UTC)


def _required_text(value: Any, code: str) -> str:
    rendered = str(value).strip() if value is not None else ""
    if not rendered:
        raise AccountReconciliationError(code)
    return rendered


def _positive_decimal(value: Any) -> Decimal:
    parsed = _decimal(value)
    if parsed <= 0:
        raise AccountReconciliationError("RECONCILIATION_NUMBER_INVALID")
    return parsed


def _non_negative_decimal(value: Any) -> Decimal:
    parsed = _decimal(value)
    if parsed < 0:
        raise AccountReconciliationError("RECONCILIATION_NUMBER_INVALID")
    return parsed


def _decimal(value: Any) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise AccountReconciliationError("RECONCILIATION_NUMBER_INVALID") from None
    if not parsed.is_finite():
        raise AccountReconciliationError("RECONCILIATION_NUMBER_INVALID")
    return parsed
