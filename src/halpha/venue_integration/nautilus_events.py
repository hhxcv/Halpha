"""Normalize qualified Nautilus order callbacks into DAT facts."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from halpha.venue_integration.facts import build_venue_fact
from halpha.venue_integration.models import (
    ExecutionAction,
    VenueFact,
    VenueFactKind,
    VenueFactSourceClass,
)


@dataclass(frozen=True, slots=True)
class NormalizedNautilusEvent:
    action: ExecutionAction | None
    facts: tuple[VenueFact, ...]
    client_order_id: str | None = None
    definitely_not_submitted: bool = False
    result_unknown: bool = False
    unknown_reason: str | None = None


class NautilusExecutionEventNormalizer:
    """Map callbacks only; Nautilus remains the technical order state owner."""

    def __init__(
        self,
        action_for_client_order_id: Callable[[str], ExecutionAction | None],
        *,
        environment_id: str,
        venue_ref: str = "BINANCE",
        leaves_quantity_for_client_order_id: Callable[[str], str | None] | None = None,
        cancel_action_for_target: Callable[[str], ExecutionAction | None] | None = None,
        fact_id_factory: Callable[[], str] = lambda: str(uuid4()),
    ) -> None:
        self._action_for_client_order_id = action_for_client_order_id
        self._environment_id = environment_id
        self._venue_ref = venue_ref
        self._leaves_quantity = leaves_quantity_for_client_order_id
        self._cancel_action_for_target = cancel_action_for_target
        self._fact_id_factory = fact_id_factory

    def normalize(
        self,
        event: object,
        *,
        received_at: datetime,
    ) -> NormalizedNautilusEvent:
        event_type = type(event).__name__
        client_order_id = _identifier(getattr(event, "client_order_id", None))
        action = (
            self._action_for_client_order_id(client_order_id)
            if client_order_id is not None
            else None
        )
        if action is not None and action.environment_id != self._environment_id:
            raise ValueError("VENUE_FACT_ATTRIBUTION_INVALID")
        if event_type == "OrderSubmitted":
            return NormalizedNautilusEvent(
                action=action,
                facts=(),
                client_order_id=client_order_id,
            )
        if event_type == "OrderDenied":
            return NormalizedNautilusEvent(
                action=action,
                facts=(),
                client_order_id=client_order_id,
                definitely_not_submitted=action is not None,
            )
        if event_type == "OrderCancelRejected":
            cancel_action = (
                self._cancel_action_for_target(client_order_id)
                if self._cancel_action_for_target is not None
                and client_order_id is not None
                else None
            )
            return NormalizedNautilusEvent(
                action=cancel_action,
                facts=(),
                client_order_id=client_order_id,
                result_unknown=cancel_action is not None,
                unknown_reason=(
                    "VENUE_CANCEL_RESULT_UNKNOWN" if cancel_action is not None else None
                ),
            )

        if event_type == "OrderRejected" and _submission_result_is_unknown(event):
            return NormalizedNautilusEvent(
                action=action,
                facts=(),
                client_order_id=client_order_id,
                result_unknown=action is not None,
                unknown_reason=(
                    "VENUE_SUBMISSION_RESULT_UNKNOWN" if action is not None else None
                ),
            )

        status = {
            # Nautilus emits OrderAccepted for Binance order/algo status NEW.
            # This is the authoritative venue event that the order is active;
            # waiting for a later OrderUpdated leaves resting protection UNKNOWN.
            "OrderAccepted": "WORKING",
            "OrderUpdated": "WORKING",
            "OrderRejected": "REJECTED",
            "OrderCanceled": "CANCELLED",
            "OrderExpired": "EXPIRED",
        }.get(event_type)
        if status is not None:
            return NormalizedNautilusEvent(
                action=action,
                facts=(
                    self._order_state_fact(
                        event,
                        action=action,
                        client_order_id=client_order_id,
                        status=status,
                        received_at=received_at,
                    ),
                ),
                client_order_id=client_order_id,
            )
        if event_type == "OrderFilled":
            return NormalizedNautilusEvent(
                action=action,
                facts=self._fill_facts(
                    event,
                    action=action,
                    client_order_id=client_order_id,
                    received_at=received_at,
                ),
                client_order_id=client_order_id,
            )
        return NormalizedNautilusEvent(
            action=action,
            facts=(),
            client_order_id=client_order_id,
        )

    def _order_state_fact(
        self,
        event: object,
        *,
        action: ExecutionAction | None,
        client_order_id: str | None,
        status: str,
        received_at: datetime,
    ) -> VenueFact:
        source_time = _source_time(event)
        source_sequence = _identifier(getattr(event, "id", None)) or str(
            getattr(event, "ts_event", 0)
        )
        source_object_id = client_order_id or _identifier(
            getattr(event, "venue_order_id", None)
        )
        if source_object_id is None:
            raise ValueError("VENUE_FACT_SOURCE_IDENTITY_REQUIRED")
        return build_venue_fact(
            venue_fact_id=self._fact_id_factory(),
            environment_id=self._environment_id,
            venue_ref=self._venue_ref,
            account_ref=(
                action.account_ref
                if action is not None
                else _identifier(getattr(event, "account_id", None))
            ),
            instrument_ref=(
                str(action.action_terms["instrument_ref"])
                if action is not None
                else _instrument_ref(event)
            ),
            kind=VenueFactKind.ORDER_STATE,
            source_class=_source_class(event, action),
            source_object_id=source_object_id,
            source_sequence=source_sequence,
            source_time=source_time,
            received_at=received_at,
            cutoff=received_at,
            payload={
                "event_type": type(event).__name__,
                "status": status,
                "client_order_id": client_order_id,
                "venue_order_ref": _identifier(getattr(event, "venue_order_id", None)),
                "reconciliation": bool(getattr(event, "reconciliation", False)),
                "reason": str(getattr(event, "reason", "")) or None,
            },
            action=action,
        )

    def _fill_facts(
        self,
        event: object,
        *,
        action: ExecutionAction | None,
        client_order_id: str | None,
        received_at: datetime,
    ) -> tuple[VenueFact, ...]:
        trade_id = _identifier(getattr(event, "trade_id", None))
        if trade_id is None:
            raise ValueError("VENUE_FACT_SOURCE_IDENTITY_REQUIRED")
        event_id = _identifier(getattr(event, "id", None)) or str(
            getattr(event, "ts_event", 0)
        )
        source_time = _source_time(event)
        leaves_quantity = (
            self._leaves_quantity(client_order_id)
            if self._leaves_quantity is not None and client_order_id is not None
            else None
        )
        common = {
            "environment_id": self._environment_id,
            "venue_ref": self._venue_ref,
            "account_ref": (
                action.account_ref
                if action is not None
                else _identifier(getattr(event, "account_id", None))
            ),
            "instrument_ref": (
                str(action.action_terms["instrument_ref"])
                if action is not None
                else _instrument_ref(event)
            ),
            "source_class": _source_class(event, action),
            "source_time": source_time,
            "received_at": received_at,
            "cutoff": received_at,
            "action": action,
        }
        fill = build_venue_fact(
            venue_fact_id=self._fact_id_factory(),
            kind=VenueFactKind.FILL,
            source_object_id=trade_id,
            source_sequence=event_id,
            payload={
                "event_type": type(event).__name__,
                "trade_id": trade_id,
                "client_order_id": client_order_id,
                "venue_order_ref": _identifier(getattr(event, "venue_order_id", None)),
                "last_price": str(getattr(event, "last_px")),
                "last_quantity": str(getattr(event, "last_qty")),
                "leaves_quantity": leaves_quantity,
                "order_side": str(getattr(event, "order_side", "")),
                "liquidity_side": str(getattr(event, "liquidity_side", "")),
                "reconciliation": bool(getattr(event, "reconciliation", False)),
            },
            **common,
        )
        facts = [fill]
        commission = getattr(event, "commission", None)
        if commission is not None:
            facts.append(
                build_venue_fact(
                    venue_fact_id=self._fact_id_factory(),
                    kind=VenueFactKind.COMMISSION,
                    source_object_id=trade_id,
                    source_sequence=f"{event_id}:COMMISSION",
                    payload={
                        "event_type": type(event).__name__,
                        "trade_id": trade_id,
                        "client_order_id": client_order_id,
                        "amount": str(commission),
                        "currency": _identifier(getattr(event, "currency", None)),
                    },
                    **common,
                )
            )
        return tuple(facts)


def _identifier(value: Any) -> str | None:
    if value is None:
        return None
    raw = getattr(value, "value", value)
    rendered = str(raw)
    return rendered if rendered else None


def _instrument_ref(event: object) -> str | None:
    value = _identifier(getattr(event, "instrument_id", None))
    if value is None:
        return None
    return value.removesuffix(".BINANCE")


def _source_time(event: object) -> datetime | None:
    value = getattr(event, "ts_event", None)
    if value is None:
        return None
    return datetime.fromtimestamp(int(value) / 1_000_000_000, tz=UTC)


def _source_class(
    event: object,
    action: ExecutionAction | None,
) -> VenueFactSourceClass:
    if action is None:
        return VenueFactSourceClass.EXTERNAL_UNCLAIMED
    if bool(getattr(event, "reconciliation", False)):
        return VenueFactSourceClass.VENUE_QUERY
    return VenueFactSourceClass.VENUE_STREAM


_SUBMISSION_UNKNOWN_HTTP_STATUS = re.compile(
    r"(?:\bhttp(?:error)?(?:/\d(?:\.\d)?)?\s+|<title>\s*|"
    r"\bstatus(?:\s+code)?\s*[:=]?\s*)(?:408|5\d\d)\b",
)


def _submission_result_is_unknown(event: object) -> bool:
    """Recognize post-submit responses that cannot prove a terminal venue result."""

    reason = str(getattr(event, "reason", "")).strip().casefold()
    if not reason:
        return False
    # LiveExecutionEngine resolves an order which stayed in-flight after all
    # status queries as a reconciliation OrderRejected(reason="UNKNOWN"). This
    # is a technical cache resolution, not proof that Binance rejected or never
    # accepted the original client order identity.
    if bool(getattr(event, "reconciliation", False)) and reason == "unknown":
        return True
    if _SUBMISSION_UNKNOWN_HTTP_STATUS.search(reason):
        return True
    return any(
        marker in reason
        for marker in (
            "-1007",
            "execution status unknown",
            "send status unknown",
            "timeout waiting for response from backend server",
            "unknown error, please check your request or try again later",
            "request occur unknown error",
            "bad gateway",
            "gateway timeout",
            "service unavailable",
            "internal server error",
            "request timeout",
            "connection reset",
            "connection aborted",
            "connection closed",
            "remote end closed connection",
            "unexpected eof",
            "timed out",
        )
    )
