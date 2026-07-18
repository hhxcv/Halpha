"""Build authoritative commission facts from Binance's read-only trade query."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from halpha.domain_values import canonical_decimal
from halpha.venue_integration.facts import build_venue_fact
from halpha.venue_integration.models import (
    ExecutionAction,
    VenueFact,
    VenueFactKind,
    VenueFactSourceClass,
)


class BinanceCommissionEvidenceError(ValueError):
    """A venue trade cannot safely complete a persisted fill's fee evidence."""


def missing_commission_trade_ids(facts: Iterable[VenueFact]) -> tuple[str, ...]:
    """Return stable fill trade IDs which have no actual commission fact."""

    materialized = tuple(facts)
    commission_ids = {
        fact.source_object_id
        for fact in materialized
        if fact.kind is VenueFactKind.COMMISSION
    }
    return tuple(
        dict.fromkeys(
            fact.source_object_id
            for fact in materialized
            if fact.kind is VenueFactKind.FILL
            and fact.source_object_id not in commission_ids
        )
    )


def commission_facts_from_user_trades(
    *,
    action: ExecutionAction,
    facts: Iterable[VenueFact],
    user_trades: Iterable[Any],
    expected_symbol: str,
    observed_at: datetime,
) -> tuple[VenueFact, ...]:
    """Map matching ``GET /fapi/v1/userTrades`` rows to missing commission facts.

    Unrelated account trades are ignored. A row claiming one of this action's fill
    trade IDs must agree on symbol, venue order, price, and quantity before it can
    become authoritative evidence.
    """

    if observed_at.utcoffset() is None:
        raise BinanceCommissionEvidenceError("COMMISSION_QUERY_TIMEZONE_REQUIRED")
    materialized = tuple(facts)
    fill_by_trade_id = {
        fact.source_object_id: fact
        for fact in materialized
        if fact.kind is VenueFactKind.FILL
    }
    missing_ids = set(missing_commission_trade_ids(materialized))
    if not missing_ids:
        return ()
    venue_order_refs = set(action.venue_order_refs)
    results: list[VenueFact] = []
    seen: set[str] = set()
    for trade in user_trades:
        trade_id = _required_identifier(getattr(trade, "id", None), "TRADE_ID")
        if trade_id not in missing_ids:
            continue
        if trade_id in seen:
            raise BinanceCommissionEvidenceError("COMMISSION_QUERY_DUPLICATE_TRADE")
        seen.add(trade_id)
        fill = fill_by_trade_id[trade_id]
        order_id = _required_identifier(
            getattr(trade, "orderId", None),
            "ORDER_ID",
        )
        if order_id not in venue_order_refs:
            raise BinanceCommissionEvidenceError("COMMISSION_QUERY_ORDER_MISMATCH")
        if str(getattr(trade, "symbol", "")) != expected_symbol:
            raise BinanceCommissionEvidenceError("COMMISSION_QUERY_SYMBOL_MISMATCH")
        price = _canonical_nonnegative(getattr(trade, "price", None), "PRICE")
        quantity = _canonical_nonnegative(getattr(trade, "qty", None), "QUANTITY")
        if Decimal(quantity) <= 0:
            raise BinanceCommissionEvidenceError("COMMISSION_QUERY_QUANTITY_INVALID")
        if price != _canonical_nonnegative(fill.payload.get("last_price"), "FILL_PRICE"):
            raise BinanceCommissionEvidenceError("COMMISSION_QUERY_PRICE_MISMATCH")
        if quantity != _canonical_nonnegative(
            fill.payload.get("last_quantity"),
            "FILL_QUANTITY",
        ):
            raise BinanceCommissionEvidenceError("COMMISSION_QUERY_QUANTITY_MISMATCH")
        amount = _canonical_nonnegative(
            getattr(trade, "commission", None),
            "COMMISSION",
        )
        currency = str(getattr(trade, "commissionAsset", ""))
        if not currency:
            raise BinanceCommissionEvidenceError("COMMISSION_QUERY_ASSET_MISSING")
        source_time = _source_time(getattr(trade, "time", None))
        results.append(
            build_venue_fact(
                venue_fact_id=str(uuid4()),
                environment_id=action.environment_id,
                venue_ref="BINANCE",
                account_ref=action.account_ref,
                instrument_ref=str(action.action_terms["instrument_ref"]),
                kind=VenueFactKind.COMMISSION,
                source_class=VenueFactSourceClass.VENUE_QUERY,
                source_object_id=trade_id,
                source_sequence=f"{order_id}:{trade_id}:COMMISSION",
                source_time=source_time,
                received_at=observed_at,
                cutoff=observed_at,
                payload={
                    "event_type": "BinanceUserTradeQuery",
                    "trade_id": trade_id,
                    "venue_order_ref": order_id,
                    "amount": amount,
                    "currency": currency,
                    "price": price,
                    "last_quantity": quantity,
                    "query_path": "/fapi/v1/userTrades",
                    "read_only": True,
                },
                action=action,
            )
        )
    return tuple(results)


def _required_identifier(value: Any, field: str) -> str:
    if value is None or str(value) == "":
        raise BinanceCommissionEvidenceError(f"COMMISSION_QUERY_{field}_MISSING")
    return str(value)


def _canonical_nonnegative(value: Any, field: str) -> str:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise BinanceCommissionEvidenceError(
            f"COMMISSION_QUERY_{field}_INVALID"
        ) from None
    if not parsed.is_finite() or parsed < 0:
        raise BinanceCommissionEvidenceError(
            f"COMMISSION_QUERY_{field}_INVALID"
        )
    return canonical_decimal(parsed)


def _source_time(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        milliseconds = int(value)
    except (TypeError, ValueError):
        raise BinanceCommissionEvidenceError(
            "COMMISSION_QUERY_SOURCE_TIME_INVALID"
        ) from None
    return datetime.fromtimestamp(milliseconds / 1000, tz=UTC)
