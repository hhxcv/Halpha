from __future__ import annotations

import pytest

from halpha.planning.models import ProposedActionKind
from halpha.venue_integration.gateway import VenueSubmissionUncertain
from halpha.venue_integration.nautilus_client import NautilusVenueExecutionClient
from tests.venue_integration.test_execution_action import _action, _proposed


class _Adapter:
    activation_id = "10000000-0000-0000-0000-000000000002"

    def __init__(self, capability: object) -> None:
        self.capability = capability
        self.submissions: list[dict[str, object]] = []
        self.cancellations: list[str] = []
        self.queries: list[str] = []

    def _submit_persisted_order(self, capability: object, **terms: object) -> None:
        assert capability is self.capability
        self.submissions.append(terms)

    def _cancel_persisted_order(self, capability: object, client_order_id: str) -> None:
        assert capability is self.capability
        self.cancellations.append(client_order_id)

    def _query_persisted_order(self, capability: object, client_order_id: str) -> None:
        assert capability is self.capability
        self.queries.append(client_order_id)


def test_nautilus_client_uses_one_async_adapter_path_without_synthesizing_ack() -> None:
    capability = object()
    adapter = _Adapter(capability)
    client = NautilusVenueExecutionClient(lambda activation_id: adapter, capability)
    action = _action()
    with pytest.raises(VenueSubmissionUncertain, match="NAUTILUS_ASYNC_RESULT_PENDING"):
        client.submit_order(action)
    assert adapter.submissions == [
        {
            "profile": "ENTRY_MARKET",
            "instrument_ref": "BTCUSDT-PERP",
            "direction": "LONG",
            "quantity": "0.001",
            "price": None,
            "trigger_price": None,
            "reduce_only": False,
            "client_order_id": "0123456789abcdef0123456789abcdef",
        }
    ]
    assert adapter.activation_id == action.activation_id


def test_cancel_and_query_reuse_original_uuid32() -> None:
    capability = object()
    adapter = _Adapter(capability)
    client = NautilusVenueExecutionClient(lambda activation_id: adapter, capability)
    cancel = _action(
        _proposed(
            kind=ProposedActionKind.CANCEL,
            profile="CANCEL_ORDER",
            order_type="CANCEL",
            quantity=None,
            cancel_target={
                "client_order_id": "f" * 32,
                "endpoint": "ALGO",
            },
        )
    )
    with pytest.raises(VenueSubmissionUncertain):
        client.cancel_order(cancel)
    with pytest.raises(VenueSubmissionUncertain):
        client.query_order(cancel)
    assert adapter.cancellations == ["f" * 32]
    assert adapter.queries == ["f" * 32]
