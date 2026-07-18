"""Qualified Nautilus Strategy write client shared by Demo and Live profiles."""

from __future__ import annotations

from collections.abc import Callable

from halpha.planning.adapter import HalphaStrategyAdapter
from halpha.venue_integration.gateway import (
    VenueCallReceipt,
    VenueSubmissionUncertain,
)
from halpha.venue_integration.models import ExecutionAction


class NautilusVenueExecutionClient:
    """Map persisted actions to the one adapter-private Strategy write hop."""

    def __init__(
        self,
        adapter_for_activation: Callable[[str], HalphaStrategyAdapter],
        persisted_action_capability: object,
    ) -> None:
        self._adapter_for_activation = adapter_for_activation
        self._capability = persisted_action_capability

    def submit_order(self, action: ExecutionAction) -> VenueCallReceipt:
        terms = action.action_terms
        if action.client_order_id is None or terms.get("quantity") is None:
            raise ValueError("ACTION_PROFILE_MISMATCH")
        adapter = self._adapter(action)
        adapter._submit_persisted_order(
            self._capability,
            profile=str(terms["action_profile"]),
            instrument_ref=str(terms["instrument_ref"]),
            direction=str(terms["direction"]),
            quantity=str(terms["quantity"]),
            price=str(terms["price"]) if terms.get("price") is not None else None,
            trigger_price=(
                str(terms["trigger_price"])
                if terms.get("trigger_price") is not None
                else None
            ),
            reduce_only=bool(terms["reduce_only"]),
            client_order_id=action.client_order_id,
        )
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
        self._adapter(action)._query_persisted_order(self._capability, client_order_id)
        raise VenueSubmissionUncertain("NAUTILUS_ASYNC_RESULT_PENDING")

    def _adapter(self, action: ExecutionAction) -> HalphaStrategyAdapter:
        adapter = self._adapter_for_activation(action.activation_id)
        if adapter.activation_id != action.activation_id:
            raise RuntimeError("AUTHORIZATION_MISMATCH")
        return adapter
