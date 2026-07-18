"""Normalize Binance open-algorithm-order queries into authoritative DAT facts."""

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
    ExecutionActionKind,
    VenueFact,
    VenueFactKind,
    VenueFactSourceClass,
)


class BinanceAlgoOrderEvidenceError(ValueError):
    """An open-algo row cannot safely prove the persisted action is working."""


_VENUE_ORDER_TYPE_BY_PROFILE = {
    "PROTECTIVE_STOP_REDUCE_ONLY": "STOP_MARKET",
    "TAKE_PROFIT_1": "TAKE_PROFIT_MARKET",
    "TAKE_PROFIT_2": "TAKE_PROFIT_MARKET",
}


def working_fact_from_open_algo_orders(
    *,
    action: ExecutionAction,
    open_algo_orders: Iterable[Any],
    expected_symbol: str,
    observed_at: datetime,
) -> VenueFact | None:
    """Return one WORKING fact for the action's exact UUID32, if currently open."""

    if observed_at.utcoffset() is None:
        raise BinanceAlgoOrderEvidenceError("ALGO_QUERY_TIMEZONE_REQUIRED")
    if action.action_kind not in {
        ExecutionActionKind.PROTECTION,
        ExecutionActionKind.TAKE_PROFIT,
    }:
        raise BinanceAlgoOrderEvidenceError("ALGO_QUERY_ACTION_KIND_INVALID")
    matches = tuple(
        order
        for order in open_algo_orders
        if str(getattr(order, "clientAlgoId", "")) == action.client_order_id
    )
    if not matches:
        return None
    if len(matches) != 1:
        raise BinanceAlgoOrderEvidenceError("ALGO_QUERY_DUPLICATE_CLIENT_ID")
    order = matches[0]
    algo_id = _required_identifier(getattr(order, "algoId", None), "ALGO_ID")
    if str(getattr(order, "symbol", "")) != expected_symbol:
        raise BinanceAlgoOrderEvidenceError("ALGO_QUERY_SYMBOL_MISMATCH")
    status = str(getattr(order, "algoStatus", "")).upper()
    if status not in {"NEW", "WORKING"}:
        raise BinanceAlgoOrderEvidenceError("ALGO_QUERY_STATUS_INVALID")
    terms = action.action_terms
    profile = str(terms["action_profile"])
    expected_venue_order_type = _VENUE_ORDER_TYPE_BY_PROFILE.get(profile)
    if expected_venue_order_type is None:
        raise BinanceAlgoOrderEvidenceError("ALGO_QUERY_PROFILE_INVALID")
    if str(getattr(order, "orderType", "")) != expected_venue_order_type:
        raise BinanceAlgoOrderEvidenceError("ALGO_QUERY_ORDER_TYPE_MISMATCH")
    if bool(getattr(order, "reduceOnly", False)) is not bool(terms["reduce_only"]):
        raise BinanceAlgoOrderEvidenceError("ALGO_QUERY_REDUCE_ONLY_MISMATCH")
    if bool(getattr(order, "closePosition", False)) is not bool(
        terms["close_position"]
    ):
        raise BinanceAlgoOrderEvidenceError("ALGO_QUERY_CLOSE_POSITION_MISMATCH")
    quantity = _canonical_positive(getattr(order, "quantity", None), "QUANTITY")
    if quantity != _canonical_positive(terms.get("quantity"), "ACTION_QUANTITY"):
        raise BinanceAlgoOrderEvidenceError("ALGO_QUERY_QUANTITY_MISMATCH")
    trigger_price = _canonical_positive(
        getattr(order, "triggerPrice", None),
        "TRIGGER_PRICE",
    )
    if trigger_price != _canonical_positive(
        terms.get("trigger_price"),
        "ACTION_TRIGGER_PRICE",
    ):
        raise BinanceAlgoOrderEvidenceError("ALGO_QUERY_TRIGGER_PRICE_MISMATCH")
    update_time = getattr(order, "updateTime", None)
    create_time = getattr(order, "createTime", None)
    source_time = _source_time(update_time if update_time is not None else create_time)
    source_version = str(update_time if update_time is not None else create_time)
    return build_venue_fact(
        venue_fact_id=str(uuid4()),
        environment_id=action.environment_id,
        venue_ref="BINANCE",
        account_ref=action.account_ref,
        instrument_ref=str(terms["instrument_ref"]),
        kind=VenueFactKind.ORDER_STATE,
        source_class=VenueFactSourceClass.VENUE_QUERY,
        source_object_id=algo_id,
        source_sequence=f"{source_version}:{status}",
        source_time=source_time,
        received_at=observed_at,
        cutoff=observed_at,
        payload={
            "event_type": "BinanceOpenAlgoOrderQuery",
            "status": "WORKING",
            "venue_status": status,
            "client_order_id": action.client_order_id,
            "venue_order_ref": algo_id,
            "order_type": str(getattr(order, "orderType")),
            "action_order_type": str(terms["order_type"]),
            "action_profile": profile,
            "quantity": quantity,
            "trigger_price": trigger_price,
            "reduce_only": bool(getattr(order, "reduceOnly")),
            "close_position": bool(getattr(order, "closePosition")),
            "working_type": str(getattr(order, "workingType", "")) or None,
            "query_path": "/fapi/v1/openAlgoOrders",
            "read_only": True,
        },
        action=action,
    )


def _required_identifier(value: Any, field: str) -> str:
    if value is None or str(value) == "":
        raise BinanceAlgoOrderEvidenceError(f"ALGO_QUERY_{field}_MISSING")
    return str(value)


def _canonical_positive(value: Any, field: str) -> str:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise BinanceAlgoOrderEvidenceError(f"ALGO_QUERY_{field}_INVALID") from None
    if not parsed.is_finite() or parsed <= 0:
        raise BinanceAlgoOrderEvidenceError(f"ALGO_QUERY_{field}_INVALID")
    return canonical_decimal(parsed)


def _source_time(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        milliseconds = int(value)
    except (TypeError, ValueError):
        raise BinanceAlgoOrderEvidenceError("ALGO_QUERY_SOURCE_TIME_INVALID") from None
    return datetime.fromtimestamp(milliseconds / 1000, tz=UTC)
