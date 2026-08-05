"""Qualified Nautilus Strategy write client shared by Demo and Live profiles."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from typing import Any

from halpha.planning.adapter import HalphaStrategyAdapter
from halpha.venue_integration.gateway import (
    VenueDefinitelyNotSubmitted,
    VenueCallReceipt,
    VenueSubmissionUncertain,
)
from halpha.venue_integration.models import ExecutionAction


_VENUE_POLICY_FIELDS = frozenset(
    {
        "order_type",
        "time_in_force",
        "post_only",
        "price_match",
        "expire_at",
    }
)
_LIMIT_TIME_IN_FORCE_VALUES = frozenset({"GTC", "GTD", "IOC", "FOK"})
_BINANCE_PRICE_MATCH_VALUES = frozenset(
    {
        "OPPONENT",
        "OPPONENT_5",
        "OPPONENT_10",
        "OPPONENT_20",
        "QUEUE",
        "QUEUE_5",
        "QUEUE_10",
        "QUEUE_20",
    }
)
_PLAIN_ORDER_PROFILE_TYPES = {
    "ENTRY_LIMIT": "LIMIT",
    "ENTRY_MARKET": "MARKET",
    "ENTRY_STOP_MARKET": "STOP_MARKET",
    "PROTECTIVE_STOP_REDUCE_ONLY": "STOP_MARKET",
    "TAKE_PROFIT_1": "MARKET_IF_TOUCHED",
    "TAKE_PROFIT_2": "MARKET_IF_TOUCHED",
    "REDUCE_OR_CLOSE_MARKET": "MARKET",
}
_MISSING = object()
_QUERY_DISPATCH_RETENTION_SECONDS = 300.0
_MAX_QUERY_DISPATCH_MARKERS = 4096


@dataclass(frozen=True, slots=True)
class _VenueOrderPolicy:
    time_in_force: str | None
    post_only: bool
    price_match: str | None
    expire_at: datetime | None


def _parse_expire_at(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("VENUE_ORDER_POLICY_INVALID")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("VENUE_ORDER_POLICY_INVALID") from None
    if parsed.utcoffset() is None:
        raise ValueError("VENUE_ORDER_POLICY_INVALID")
    return parsed


def _venue_order_policy(action: ExecutionAction) -> _VenueOrderPolicy:
    """Read a complete fixed venue policy without inferring missing terms."""

    terms = action.action_terms
    execution_context = terms.get("execution_context", {})
    if not isinstance(execution_context, dict):
        raise ValueError("VENUE_ORDER_POLICY_INVALID")
    raw_policy = execution_context.get("venue_policy", _MISSING)
    if raw_policy is _MISSING:
        raise ValueError("VENUE_ORDER_POLICY_REQUIRED")
    if (
        not isinstance(raw_policy, dict)
        or frozenset(raw_policy) != _VENUE_POLICY_FIELDS
    ):
        raise ValueError("VENUE_ORDER_POLICY_INVALID")

    profile = terms.get("action_profile")
    expected_order_type = _PLAIN_ORDER_PROFILE_TYPES.get(profile)
    order_type = raw_policy["order_type"]
    if (
        expected_order_type is None
        or order_type != expected_order_type
        or terms.get("order_type") != expected_order_type
    ):
        raise ValueError("ACTION_PROFILE_MISMATCH")

    time_in_force = raw_policy["time_in_force"]
    post_only = raw_policy["post_only"]
    price_match = raw_policy["price_match"]
    expire_at = _parse_expire_at(raw_policy["expire_at"])
    if type(post_only) is not bool:
        raise ValueError("VENUE_ORDER_POLICY_INVALID")

    if order_type in {"MARKET", "STOP_MARKET", "MARKET_IF_TOUCHED"}:
        if (
            time_in_force is not None
            or post_only
            or price_match is not None
            or expire_at is not None
        ):
            raise ValueError("VENUE_ORDER_POLICY_CONFLICT")
        return _VenueOrderPolicy(
            time_in_force=None,
            post_only=False,
            price_match=None,
            expire_at=None,
        )

    if (
        not isinstance(time_in_force, str)
        or time_in_force not in _LIMIT_TIME_IN_FORCE_VALUES
    ):
        raise ValueError("VENUE_ORDER_POLICY_INVALID")
    if price_match is not None and (
        not isinstance(price_match, str)
        or price_match not in _BINANCE_PRICE_MATCH_VALUES
    ):
        raise ValueError("VENUE_ORDER_POLICY_INVALID")
    if post_only and (time_in_force != "GTC" or price_match is not None):
        raise ValueError("VENUE_ORDER_POLICY_CONFLICT")
    if (time_in_force == "GTD") != (expire_at is not None):
        raise ValueError("VENUE_ORDER_POLICY_CONFLICT")
    return _VenueOrderPolicy(
        time_in_force=time_in_force,
        post_only=post_only,
        price_match=price_match,
        expire_at=expire_at,
    )


class NautilusVenueExecutionClient:
    """Map persisted actions to the one adapter-private Strategy write hop."""

    def __init__(
        self,
        adapter_for_activation: Callable[[str], HalphaStrategyAdapter],
        persisted_action_capability: object,
        *,
        current_time_provider: Callable[[], datetime] | None = None,
        monotonic_time_provider: Callable[[], float] = monotonic,
    ) -> None:
        self._adapter_for_activation = adapter_for_activation
        self._capability = persisted_action_capability
        self._current_time_provider = current_time_provider or (
            lambda: datetime.now(UTC)
        )
        self._monotonic_time_provider = monotonic_time_provider
        self._query_dispatched_at: dict[str, float] = {}

    def query_was_recently_dispatched(
        self,
        client_order_id: str,
        *,
        window_seconds: float = 30.0,
    ) -> bool:
        dispatched_at = self._query_dispatched_at.get(client_order_id)
        if dispatched_at is None:
            return False
        now = self._monotonic_time_provider()
        if now - dispatched_at > window_seconds or now < dispatched_at:
            self._query_dispatched_at.pop(client_order_id, None)
            return False
        return True

    def _record_query_dispatch(self, client_order_id: str) -> None:
        now = self._monotonic_time_provider()
        if self._query_dispatched_at:
            self._query_dispatched_at = {
                identity: dispatched_at
                for identity, dispatched_at in self._query_dispatched_at.items()
                if 0 <= now - dispatched_at <= _QUERY_DISPATCH_RETENTION_SECONDS
            }
        if len(self._query_dispatched_at) >= _MAX_QUERY_DISPATCH_MARKERS:
            oldest = min(
                self._query_dispatched_at,
                key=self._query_dispatched_at.__getitem__,
            )
            self._query_dispatched_at.pop(oldest, None)
        self._query_dispatched_at[client_order_id] = now

    def _require_action_still_valid(self, action: ExecutionAction) -> None:
        value = action.action_terms.get("valid_until")
        if value is None:
            return
        if not isinstance(value, str):
            raise ValueError("ACTION_VALID_UNTIL_INVALID")
        try:
            valid_until = datetime.fromisoformat(value)
        except ValueError:
            raise ValueError("ACTION_VALID_UNTIL_INVALID") from None
        current_time = self._current_time_provider()
        if valid_until.utcoffset() is None or current_time.utcoffset() is None:
            raise ValueError("ACTION_VALID_UNTIL_INVALID")
        if current_time.astimezone(UTC) >= valid_until.astimezone(UTC):
            # No adapter call has happened, so expiry is one of the rare cases
            # where the client can prove that the venue was not contacted.
            raise VenueDefinitelyNotSubmitted(
                "ACTION_VALIDITY_EXPIRED_BEFORE_VENUE_CALL"
            )

    def submit_order(self, action: ExecutionAction) -> VenueCallReceipt:
        self._require_action_still_valid(action)
        terms = action.action_terms
        if action.client_order_id is None or terms.get("quantity") is None:
            raise ValueError("ACTION_PROFILE_MISMATCH")
        reduce_only = terms.get("reduce_only")
        if type(reduce_only) is not bool:
            raise ValueError("ACTION_PROFILE_MISMATCH")
        venue_policy = _venue_order_policy(action)
        execution_context = terms.get("execution_context", {})
        if not isinstance(execution_context, dict):
            raise ValueError("ACTION_PROFILE_MISMATCH")
        trigger_source = execution_context.get("trigger_source")
        if trigger_source is not None and (
            not isinstance(trigger_source, str)
            or trigger_source not in {"LAST_PRICE", "MARK_PRICE"}
        ):
            raise ValueError("VENUE_TRIGGER_SOURCE_INVALID")
        position_side = terms.get("position_side")
        if str(terms["action_profile"]) == "REDUCE_OR_CLOSE_MARKET":
            if position_side not in {"BOTH", "LONG", "SHORT"}:
                raise ValueError("ACTION_POSITION_SIDE_INVALID")
        elif position_side is not None:
            raise ValueError("ACTION_POSITION_SIDE_INVALID")
        adapter = self._adapter(action)
        order_terms: dict[str, Any] = {
            "profile": str(terms["action_profile"]),
            "instrument_ref": str(terms["instrument_ref"]),
            "direction": str(terms["direction"]),
            "quantity": str(terms["quantity"]),
            "price": str(terms["price"]) if terms.get("price") is not None else None,
            "trigger_price": (
                str(terms["trigger_price"])
                if terms.get("trigger_price") is not None
                else None
            ),
            "reduce_only": reduce_only,
            "client_order_id": action.client_order_id,
        }
        if position_side is not None:
            order_terms["position_side"] = position_side
        if trigger_source is not None:
            order_terms["trigger_source"] = trigger_source
        order_terms.update(
            {
                "time_in_force": venue_policy.time_in_force,
                "post_only": venue_policy.post_only,
                "price_match": venue_policy.price_match,
                "expire_at": venue_policy.expire_at,
            }
        )
        adapter._submit_persisted_order(self._capability, **order_terms)
        # Strategy writes are asynchronous. The callback/query path supplies the
        # authoritative venue observation; a local return never fabricates ACK.
        raise VenueSubmissionUncertain("NAUTILUS_ASYNC_RESULT_PENDING")

    def cancel_order(self, action: ExecutionAction) -> VenueCallReceipt:
        target = action.cancel_target or {}
        client_order_id = target.get("client_order_id")
        if not isinstance(client_order_id, str):
            raise ValueError("CANCEL_TARGET_INVALID")
        self._adapter(action)._cancel_persisted_order(self._capability, client_order_id)
        raise VenueSubmissionUncertain("NAUTILUS_ASYNC_RESULT_PENDING")

    def query_order(self, action: ExecutionAction) -> VenueCallReceipt:
        client_order_id = action.client_order_id
        if action.cancel_target is not None:
            client_order_id = action.cancel_target.get("client_order_id")
        if not isinstance(client_order_id, str):
            raise ValueError("CLIENT_ORDER_ID_INVALID")
        instrument_ref = action.action_terms.get("instrument_ref")
        if not isinstance(instrument_ref, str):
            raise ValueError("ACTION_PROFILE_MISMATCH")
        self._record_query_dispatch(client_order_id)
        try:
            self._adapter(action)._query_persisted_order(
                self._capability,
                client_order_id,
                instrument_ref=instrument_ref,
            )
        except Exception:
            # The marker must exist before dispatch so a synchronous framework
            # callback cannot race it.  A local dispatch failure proves there
            # is no query response to classify, so remove the marker again.
            self._query_dispatched_at.pop(client_order_id, None)
            raise
        # This proves only that Nautilus accepted the local read command.
        # Authoritative order state still arrives exclusively through events.
        return VenueCallReceipt(
            source_object_id=client_order_id,
            source_sequence=action.execution_action_id,
            source_time=None,
            status="QUERY_DISPATCHED",
            payload={
                "client_order_id": client_order_id,
                "instrument_ref": instrument_ref,
            },
        )

    def _adapter(self, action: ExecutionAction) -> HalphaStrategyAdapter:
        adapter = self._adapter_for_activation(action.activation_id)
        if adapter.activation_id != action.activation_id:
            raise RuntimeError("AUTHORIZATION_MISMATCH")
        return adapter
