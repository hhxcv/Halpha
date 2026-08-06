"""Normalize qualified Nautilus order callbacks into DAT facts."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from nautilus_trader.model.enums import (
    LiquiditySide,
    OrderSide,
    liquidity_side_to_str,
    order_side_to_str,
)

from halpha.domain_values import canonical_decimal
from halpha.venue_integration.binance_rate_limits import (
    MAX_BINANCE_RATE_LIMIT_BACKOFF_SECONDS,
)
from halpha.venue_integration.facts import (
    build_venue_fact,
    synthetic_reconciliation_trade_id,
    venue_trade_fact_id,
)
from halpha.venue_integration.models import (
    BINANCE_USDM_VENUE_REF,
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
    retry_after_seconds: float | None = None


class NautilusExecutionEventNormalizer:
    """Map callbacks only; Nautilus remains the technical order state owner."""

    def __init__(
        self,
        action_for_client_order_id: Callable[[str], ExecutionAction | None],
        *,
        environment_id: str,
        action_for_venue_order_ref: Callable[
            [str], ExecutionAction | None
        ] | None = None,
        venue_ref: str = BINANCE_USDM_VENUE_REF,
        leaves_quantity_for_client_order_id: Callable[[str], str | None] | None = None,
        filled_quantity_for_client_order_id: Callable[[str], str | None] | None = None,
        order_quantity_for_client_order_id: Callable[[str], str | None] | None = None,
        cancel_action_for_target: Callable[[str], ExecutionAction | None] | None = None,
        query_was_recently_dispatched: Callable[[str], bool] | None = None,
        fact_id_factory: Callable[[], str] = lambda: str(uuid4()),
    ) -> None:
        self._action_for_client_order_id = action_for_client_order_id
        self._action_for_venue_order_ref = action_for_venue_order_ref
        if venue_ref != BINANCE_USDM_VENUE_REF:
            raise ValueError("VENUE_REF_MISMATCH")
        self._environment_id = environment_id
        self._venue_ref = venue_ref
        self._leaves_quantity = leaves_quantity_for_client_order_id
        self._filled_quantity = filled_quantity_for_client_order_id
        self._order_quantity = order_quantity_for_client_order_id
        self._cancel_action_for_target = cancel_action_for_target
        self._query_was_recently_dispatched = query_was_recently_dispatched
        self._fact_id_factory = fact_id_factory

    def normalize(
        self,
        event: object,
        *,
        received_at: datetime,
    ) -> NormalizedNautilusEvent:
        event_type = type(event).__name__
        observed_client_order_id = _identifier(
            getattr(event, "client_order_id", None)
        )
        action = (
            self._action_for_client_order_id(observed_client_order_id)
            if observed_client_order_id is not None
            else None
        )
        if action is None and self._action_for_venue_order_ref is not None:
            venue_order_ref = _identifier(getattr(event, "venue_order_id", None))
            if venue_order_ref is not None:
                action = self._action_for_venue_order_ref(venue_order_ref)
        # Nautilus may synthesize a UUID client identity while reconciling an
        # already-known venue order after restart. The persisted Halpha identity
        # remains authoritative once the venue order reference proves ownership.
        client_order_id = (
            action.client_order_id
            if action is not None and action.client_order_id is not None
            else observed_client_order_id
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

        recent_query_failure = (
            event_type == "OrderRejected"
            and client_order_id is not None
            and self._query_was_recently_dispatched is not None
            and self._query_was_recently_dispatched(client_order_id)
            and _query_failure_is_non_authoritative(event)
        )
        if event_type == "OrderRejected" and (
            _submission_result_is_unknown(event) or recent_query_failure
        ):
            return NormalizedNautilusEvent(
                action=action,
                facts=(),
                client_order_id=client_order_id,
                result_unknown=action is not None,
                unknown_reason=(
                    "VENUE_SUBMISSION_RESULT_UNKNOWN" if action is not None else None
                ),
                retry_after_seconds=(
                    _query_failure_retry_after_seconds(event, received_at)
                    if recent_query_failure
                    else None
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
            if _synthetic_reconciliation_fill_event(event):
                # An order-status reconciliation can expose cumulative fill
                # quantity while Nautilus supplies a generated UUID instead of
                # Binance's trade id.  Persist the terminal order result, then
                # let the authenticated user-trade query recover exact fills
                # and commissions.  Treating this placeholder as a trade would
                # double count once the real numeric trade arrives.
                return NormalizedNautilusEvent(
                    action=action,
                    facts=(
                        self._order_state_fact(
                            event,
                            action=action,
                            client_order_id=client_order_id,
                            status="FILLED",
                            received_at=received_at,
                        ),
                    ),
                    client_order_id=client_order_id,
                )
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
        payload: dict[str, Any] = {
            "event_type": type(event).__name__,
            "status": status,
            "client_order_id": client_order_id,
            "venue_order_ref": _identifier(getattr(event, "venue_order_id", None)),
            "reconciliation": bool(getattr(event, "reconciliation", False)),
            "reason": str(getattr(event, "reason", "")) or None,
        }
        venue_order_quantity = getattr(event, "quantity", None)
        if (
            venue_order_quantity is None
            and self._order_quantity is not None
            and client_order_id is not None
        ):
            venue_order_quantity = self._order_quantity(client_order_id)
        if venue_order_quantity is not None:
            payload["venue_order_quantity"] = str(venue_order_quantity)
        cumulative = self._terminal_cumulative_filled_quantity(
            action=action,
            client_order_id=client_order_id,
            status=status,
        )
        if cumulative is not None:
            payload["cumulative_filled_quantity"] = cumulative
        elif status == "FILLED":
            cumulative = getattr(event, "last_qty", None)
            if cumulative is None and self._filled_quantity is not None:
                cumulative = self._filled_quantity(client_order_id)
            if cumulative is not None:
                payload["cumulative_filled_quantity"] = str(cumulative)
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
            payload=payload,
            action=action,
        )

    def _terminal_cumulative_filled_quantity(
        self,
        *,
        action: ExecutionAction | None,
        client_order_id: str | None,
        status: str,
    ) -> str | None:
        if action is None or status not in {"REJECTED", "CANCELLED", "EXPIRED"}:
            return None
        if status == "REJECTED":
            return "0"
        filled_raw = (
            self._filled_quantity(client_order_id)
            if self._filled_quantity is not None and client_order_id is not None
            else None
        )
        try:
            cumulative = Decimal(str(filled_raw))
        except (InvalidOperation, TypeError, ValueError):
            return None
        if cumulative < 0:
            return None
        return canonical_decimal(cumulative)

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
                "order_side": _order_side(getattr(event, "order_side", "")),
                "liquidity_side": _liquidity_side(
                    getattr(event, "liquidity_side", "")
                ),
                "reconciliation": bool(getattr(event, "reconciliation", False)),
            },
            **common,
        )
        fill = fill.model_copy(
            update={"venue_fact_id": venue_trade_fact_id(fill)}
        )
        facts = [fill]
        commission = getattr(event, "commission", None)
        if commission is not None:
            commission_fact = build_venue_fact(
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
            facts.append(
                commission_fact.model_copy(
                    update={
                        "venue_fact_id": venue_trade_fact_id(commission_fact)
                    }
                )
            )
        return tuple(facts)


def _order_side(value: object) -> str:
    return order_side_to_str(value) if isinstance(value, OrderSide) else str(value)


def _liquidity_side(value: object) -> str:
    return (
        liquidity_side_to_str(value)
        if isinstance(value, LiquiditySide)
        else str(value)
    )


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


def _synthetic_reconciliation_fill_event(event: object) -> bool:
    if not bool(getattr(event, "reconciliation", False)):
        return False
    trade_id = _identifier(getattr(event, "trade_id", None))
    if trade_id is None:
        return True
    return synthetic_reconciliation_trade_id(trade_id)


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
_BINANCE_SUBMISSION_UNKNOWN_CODE = re.compile(
    r"(?<!\d)-(?:1000|1006|1007)(?!\d)",
)
_BINANCE_QUERY_TECHNICAL_ERROR_CODE = re.compile(
    r"(?<!\d)-(?:1000|1001|1002|1003|1006|1007|1008|1021|1022)(?!\d)",
)
_QUERY_HTTP_ERROR_STATUS = re.compile(
    r"(?:\bhttp(?:error)?(?:/\d(?:\.\d)?)?\s+|<title>\s*|"
    r"\bstatus(?:\s+code)?\s*[:=]?\s*)(?:4\d\d|5\d\d)\b",
)


def _query_failure_is_non_authoritative(event: object) -> bool:
    """Recognize technical query failures which cannot decide order state."""

    reason = str(getattr(event, "reason", "")).strip().casefold()
    if not reason:
        return True
    if _BINANCE_QUERY_TECHNICAL_ERROR_CODE.search(reason):
        return True
    if _QUERY_HTTP_ERROR_STATUS.search(reason):
        return True
    return any(
        marker in reason
        for marker in (
            "connection reset",
            "connection aborted",
            "connection closed",
            "remote end closed connection",
            "unexpected eof",
            "timed out",
        )
    )


def _query_failure_retry_after_seconds(
    event: object,
    received_at: datetime,
) -> float | None:
    reason = str(getattr(event, "reason", "")).strip().casefold()
    banned_until = re.search(r"\bip banned until\s+(\d{13})\b", reason)
    if banned_until is not None:
        remaining = (
            int(banned_until.group(1)) / 1000
            - received_at.astimezone(UTC).timestamp()
        )
        return min(
            max(120.0, remaining),
            float(MAX_BINANCE_RATE_LIMIT_BACKOFF_SECONDS),
        )
    if re.search(r"\b(?:http\s+|status\s*[:=]?\s*)418\b", reason):
        return 120.0
    if (
        _BINANCE_QUERY_TECHNICAL_ERROR_CODE.search(reason)
        and any(code in reason for code in ("-1003", "-1008"))
    ) or re.search(r"\b(?:http\s+|status\s*[:=]?\s*)429\b", reason):
        return 60.0
    return None


def _submission_result_is_unknown(event: object) -> bool:
    """Recognize post-submit responses that cannot prove a terminal venue result."""

    reason = str(getattr(event, "reason", "")).strip().casefold()
    if not reason:
        # A rejection without a venue reason cannot prove that Binance did not
        # accept the stable client identity.  Preserve UNKNOWN and reconcile
        # that identity instead of fabricating a terminal business rejection.
        return True
    # LiveExecutionEngine resolves an order which stayed in-flight after all
    # status queries as a reconciliation OrderRejected(reason="UNKNOWN"). This
    # is a technical cache resolution, not proof that Binance rejected or never
    # accepted the original client order identity.
    if bool(getattr(event, "reconciliation", False)) and reason in {
        "unknown",
        "order_not_found_at_venue",
    }:
        # LiveExecutionEngine can synthesize this rejection after a targeted
        # status query returns no report. Binance uses the same no-report result
        # for -2013 and transient read failure, so it is not venue rejection
        # evidence and must not release an UNKNOWN identity.
        return True
    if _SUBMISSION_UNKNOWN_HTTP_STATUS.search(reason):
        return True
    if _BINANCE_SUBMISSION_UNKNOWN_CODE.search(reason):
        return True
    return any(
        marker in reason
        for marker in (
            "-2013",
            "execution status unknown",
            "send status unknown",
            "unknown error occured while processing the request",
            "unknown error occurred while processing the request",
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
