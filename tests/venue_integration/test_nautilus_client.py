from __future__ import annotations

from datetime import UTC, datetime

import pytest
from nautilus_trader.model.enums import TimeInForce, TriggerType

from halpha.planning.adapter import HalphaStrategyAdapter
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


def _action_with_policy(policy: dict[str, object], *, limit: bool = True):
    proposed = _proposed(
        profile="ENTRY_LIMIT" if limit else "ENTRY_MARKET",
        order_type="LIMIT" if limit else "MARKET",
        price="50000" if limit else None,
    ).model_copy(update={"execution_context": {"venue_policy": policy}})
    return _action(proposed)


def _limit_policy(**updates: object) -> dict[str, object]:
    policy: dict[str, object] = {
        "order_type": "LIMIT",
        "time_in_force": "GTC",
        "post_only": False,
        "price_match": None,
        "display_quantity": None,
        "expire_at": None,
    }
    policy.update(updates)
    return policy


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


@pytest.mark.parametrize(
    ("policy", "limit", "expected"),
    (
        (
            _limit_policy(post_only=True),
            True,
            {
                "time_in_force": "GTC",
                "post_only": True,
                "price_match": None,
                "expire_at": None,
            },
        ),
        (
            _limit_policy(price_match="QUEUE_5"),
            True,
            {
                "time_in_force": "GTC",
                "post_only": False,
                "price_match": "QUEUE_5",
                "expire_at": None,
            },
        ),
        (
            _limit_policy(
                time_in_force="GTD",
                expire_at="2026-07-23T12:30:00+00:00",
            ),
            True,
            {
                "time_in_force": "GTD",
                "post_only": False,
                "price_match": None,
                "expire_at": datetime(2026, 7, 23, 12, 30, tzinfo=UTC),
            },
        ),
        (
            {
                "order_type": "MARKET",
                "time_in_force": None,
                "post_only": False,
                "price_match": None,
                "display_quantity": None,
                "expire_at": None,
            },
            False,
            {
                "time_in_force": None,
                "post_only": False,
                "price_match": None,
                "expire_at": None,
            },
        ),
    ),
)
def test_fixed_venue_policy_is_mapped_without_inference(
    policy: dict[str, object],
    limit: bool,
    expected: dict[str, object],
) -> None:
    capability = object()
    adapter = _Adapter(capability)
    client = NautilusVenueExecutionClient(lambda activation_id: adapter, capability)

    with pytest.raises(VenueSubmissionUncertain, match="NAUTILUS_ASYNC_RESULT_PENDING"):
        client.submit_order(_action_with_policy(policy, limit=limit))

    assert {key: adapter.submissions[0][key] for key in expected} == expected


@pytest.mark.parametrize(
    ("policy", "limit", "reason"),
    (
        (
            {
                "order_type": "LIMIT",
                "time_in_force": "GTC",
                "post_only": False,
                "price_match": None,
            },
            True,
            "VENUE_ORDER_POLICY_INVALID",
        ),
        (
            _limit_policy(unqualified=True),
            True,
            "VENUE_ORDER_POLICY_INVALID",
        ),
        (
            _limit_policy(time_in_force="gtc"),
            True,
            "VENUE_ORDER_POLICY_INVALID",
        ),
        (
            _limit_policy(post_only="true"),
            True,
            "VENUE_ORDER_POLICY_INVALID",
        ),
        (
            _limit_policy(post_only=True, time_in_force="IOC"),
            True,
            "VENUE_ORDER_POLICY_CONFLICT",
        ),
        (
            _limit_policy(post_only=True, price_match="QUEUE"),
            True,
            "VENUE_ORDER_POLICY_CONFLICT",
        ),
        (
            _limit_policy(time_in_force="GTD"),
            True,
            "VENUE_ORDER_POLICY_CONFLICT",
        ),
        (
            _limit_policy(expire_at="2026-07-23T12:30:00+00:00"),
            True,
            "VENUE_ORDER_POLICY_CONFLICT",
        ),
        (
            _limit_policy(
                time_in_force="GTD",
                expire_at="2026-07-23T12:30:00",
            ),
            True,
            "VENUE_ORDER_POLICY_INVALID",
        ),
        (
            _limit_policy(price_match="QUEUE_25"),
            True,
            "VENUE_ORDER_POLICY_INVALID",
        ),
        (
            _limit_policy(display_quantity="0.001"),
            True,
            "DISPLAY_QUANTITY_NOT_DEMO_VERIFIED",
        ),
        (
            {
                "order_type": "MARKET",
                "time_in_force": "IOC",
                "post_only": False,
                "price_match": None,
                "display_quantity": None,
                "expire_at": None,
            },
            False,
            "VENUE_ORDER_POLICY_CONFLICT",
        ),
        (
            _limit_policy(order_type="MARKET"),
            True,
            "ACTION_PROFILE_MISMATCH",
        ),
    ),
)
def test_fixed_venue_policy_conflicts_fail_before_the_adapter_write_hop(
    policy: dict[str, object],
    limit: bool,
    reason: str,
) -> None:
    capability = object()
    adapter = _Adapter(capability)
    client = NautilusVenueExecutionClient(lambda activation_id: adapter, capability)

    with pytest.raises(ValueError, match=reason):
        client.submit_order(_action_with_policy(policy, limit=limit))

    assert adapter.submissions == []


class _Cache:
    def instrument(self, instrument_id: object) -> object:
        return object()


class _OrderFactory:
    def __init__(self) -> None:
        self.market_terms: list[dict[str, object]] = []
        self.limit_terms: list[dict[str, object]] = []
        self.stop_market_terms: list[dict[str, object]] = []

    def market(self, **terms: object) -> object:
        self.market_terms.append(terms)
        return object()

    def limit(self, **terms: object) -> object:
        self.limit_terms.append(terms)
        return object()

    def stop_market(self, **terms: object) -> object:
        self.stop_market_terms.append(terms)
        return object()


class _AdapterWriteHarness:
    def __init__(self) -> None:
        self.capability = object()
        self._persisted_action_capability = self.capability
        self._persisted_orders: dict[str, object] = {}
        self.cache = _Cache()
        self.order_factory = _OrderFactory()
        self.submitted: list[tuple[object, dict[str, object]]] = []

    def _require_persisted_action_capability(self, capability: object) -> None:
        if capability is not self.capability:
            raise RuntimeError("AUTHORIZATION_MISMATCH")

    def submit_order(self, order: object, **kwargs: object) -> None:
        self.submitted.append((order, kwargs))


def _submit_limit_to_harness(
    harness: _AdapterWriteHarness,
    *,
    client_order_id: str,
    time_in_force: str,
    post_only: bool = False,
    price_match: str | None = None,
    expire_at: datetime | None = None,
) -> object:
    return HalphaStrategyAdapter._submit_persisted_order(
        harness,
        harness.capability,
        profile="ENTRY_LIMIT",
        instrument_ref="BTCUSDT-PERP",
        direction="LONG",
        quantity="0.001",
        price="50000",
        trigger_price=None,
        reduce_only=False,
        client_order_id=client_order_id,
        time_in_force=time_in_force,
        post_only=post_only,
        price_match=price_match,
        expire_at=expire_at,
    )


@pytest.mark.parametrize(
    ("value", "expected", "expire_at"),
    (
        ("GTC", TimeInForce.GTC, None),
        ("IOC", TimeInForce.IOC, None),
        ("FOK", TimeInForce.FOK, None),
        (
            "GTD",
            TimeInForce.GTD,
            datetime(2026, 7, 23, 12, 30, tzinfo=UTC),
        ),
    ),
)
def test_adapter_maps_limit_time_in_force_and_native_expiry(
    value: str,
    expected: TimeInForce,
    expire_at: datetime | None,
) -> None:
    harness = _AdapterWriteHarness()

    _submit_limit_to_harness(
        harness,
        client_order_id=f"{len(value):032x}",
        time_in_force=value,
        expire_at=expire_at,
    )

    assert harness.order_factory.limit_terms[0]["time_in_force"] is expected
    assert harness.order_factory.limit_terms[0]["expire_time"] == expire_at
    assert harness.submitted[0][1] == {}


def test_adapter_maps_post_only_and_price_match_to_distinct_nautilus_channels() -> None:
    post_only = _AdapterWriteHarness()
    _submit_limit_to_harness(
        post_only,
        client_order_id="1" * 32,
        time_in_force="GTC",
        post_only=True,
    )
    assert post_only.order_factory.limit_terms[0]["post_only"] is True
    assert post_only.submitted[0][1] == {}

    price_match = _AdapterWriteHarness()
    order = _submit_limit_to_harness(
        price_match,
        client_order_id="2" * 32,
        time_in_force="GTC",
        price_match="OPPONENT_10",
    )
    # Nautilus requires a local LimitOrder price, while its Binance adapter
    # suppresses that placeholder on the wire when price_match is supplied.
    assert str(price_match.order_factory.limit_terms[0]["price"]) == "50000"
    assert price_match.submitted == [
        (order, {"params": {"price_match": "OPPONENT_10"}})
    ]


def test_adapter_maps_fixed_direct_protection_to_mark_price_trigger() -> None:
    harness = _AdapterWriteHarness()

    HalphaStrategyAdapter._submit_persisted_order(
        harness,
        harness.capability,
        profile="PROTECTIVE_STOP_REDUCE_ONLY",
        instrument_ref="BTCUSDT-PERP",
        direction="LONG",
        quantity="0.01",
        price=None,
        trigger_price="99000",
        reduce_only=True,
        client_order_id="3" * 32,
        trigger_source="MARK_PRICE",
    )

    assert (
        harness.order_factory.stop_market_terms[0]["trigger_type"]
        is TriggerType.MARK_PRICE
    )
