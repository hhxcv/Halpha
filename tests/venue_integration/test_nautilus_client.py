from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from nautilus_trader.execution.messages import QueryOrder
from nautilus_trader.model.enums import OrderSide, TimeInForce, TriggerType
from nautilus_trader.model.identifiers import InstrumentId, StrategyId, TraderId

from halpha.planning.adapter import HalphaStrategyAdapter
from halpha.planning.models import ProposedActionKind
from halpha.venue_integration.gateway import (
    VenueDefinitelyNotSubmitted,
    VenueSubmissionUncertain,
)
from halpha.venue_integration.nautilus_client import NautilusVenueExecutionClient
from tests.venue_integration.test_execution_action import NOW, _action, _proposed


class _Adapter:
    activation_id = "10000000-0000-0000-0000-000000000002"

    def __init__(self, capability: object) -> None:
        self.capability = capability
        self.submissions: list[dict[str, object]] = []
        self.cancellations: list[str] = []
        self.queries: list[tuple[str, str]] = []

    def _submit_persisted_order(self, capability: object, **terms: object) -> None:
        assert capability is self.capability
        self.submissions.append(terms)

    def _cancel_persisted_order(self, capability: object, client_order_id: str) -> None:
        assert capability is self.capability
        self.cancellations.append(client_order_id)

    def _query_persisted_order(
        self,
        capability: object,
        client_order_id: str,
        *,
        instrument_ref: str,
    ) -> None:
        assert capability is self.capability
        self.queries.append((client_order_id, instrument_ref))


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
        "expire_at": None,
    }
    policy.update(updates)
    return policy


def test_nautilus_client_uses_one_async_adapter_path_without_synthesizing_ack() -> None:
    capability = object()
    adapter = _Adapter(capability)
    client = NautilusVenueExecutionClient(lambda activation_id: adapter, capability)
    action = _action_with_policy(
        {
            "order_type": "MARKET",
            "time_in_force": None,
            "post_only": False,
            "price_match": None,
            "expire_at": None,
        },
        limit=False,
    )
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
            "time_in_force": None,
            "post_only": False,
            "price_match": None,
            "expire_at": None,
        }
    ]
    assert adapter.activation_id == action.activation_id


def test_nautilus_client_does_not_call_adapter_after_action_expiry() -> None:
    capability = object()
    adapter = _Adapter(capability)
    client = NautilusVenueExecutionClient(
        lambda activation_id: adapter,
        capability,
        current_time_provider=lambda: NOW + timedelta(seconds=2),
    )
    proposed = _proposed().model_copy(
        update={"valid_until": NOW + timedelta(seconds=1)}
    )

    with pytest.raises(
        VenueDefinitelyNotSubmitted,
        match="ACTION_VALIDITY_EXPIRED_BEFORE_VENUE_CALL",
    ):
        client.submit_order(_action(proposed))

    assert adapter.submissions == []


def test_nautilus_client_preserves_fixed_hedge_side_on_the_adapter_write() -> None:
    capability = object()
    adapter = _Adapter(capability)
    client = NautilusVenueExecutionClient(lambda activation_id: adapter, capability)
    proposed = _proposed(
        kind=ProposedActionKind.EXIT,
        profile="REDUCE_OR_CLOSE_MARKET",
        order_type="MARKET",
        reduce_only=True,
    ).model_copy(
        update={
            "execution_context": {
                "exit_responsibility_role": "PRIMARY_EXIT",
                "position_side": "LONG",
                "venue_policy": {
                    "order_type": "MARKET",
                    "time_in_force": None,
                    "post_only": False,
                    "price_match": None,
                    "expire_at": None,
                },
            }
        }
    )

    with pytest.raises(VenueSubmissionUncertain, match="NAUTILUS_ASYNC_RESULT_PENDING"):
        client.submit_order(_action(proposed))

    assert adapter.submissions[0]["position_side"] == "LONG"
    assert adapter.submissions[0]["reduce_only"] is True


def test_nautilus_client_rejects_an_action_without_a_fixed_venue_policy() -> None:
    capability = object()
    adapter = _Adapter(capability)
    client = NautilusVenueExecutionClient(lambda activation_id: adapter, capability)

    with pytest.raises(ValueError, match="VENUE_ORDER_POLICY_REQUIRED"):
        client.submit_order(_action())

    assert adapter.submissions == []


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
    receipt = client.query_order(cancel)
    assert adapter.cancellations == ["f" * 32]
    assert adapter.queries == [(("f" * 32), "BTCUSDT-PERP")]
    assert receipt.status == "QUERY_DISPATCHED"
    assert receipt.source_object_id == "f" * 32
    assert receipt.payload == {
        "client_order_id": "f" * 32,
        "instrument_ref": "BTCUSDT-PERP",
    }


def test_query_dispatch_marker_is_bounded_to_the_framework_query_window() -> None:
    capability = object()
    adapter = _Adapter(capability)
    observed_monotonic = [10.0]
    client = NautilusVenueExecutionClient(
        lambda activation_id: adapter,
        capability,
        monotonic_time_provider=lambda: observed_monotonic[0],
    )
    action = _action()

    client.query_order(action)

    assert client.query_was_recently_dispatched(action.client_order_id) is True
    observed_monotonic[0] = 40.001
    assert client.query_was_recently_dispatched(action.client_order_id) is False


def test_query_marker_precedes_dispatch_and_is_removed_when_dispatch_fails() -> None:
    capability = object()
    marker_visible_during_dispatch: list[bool] = []
    client: NautilusVenueExecutionClient

    class ReentrantAdapter(_Adapter):
        def _query_persisted_order(
            self,
            capability: object,
            client_order_id: str,
            *,
            instrument_ref: str,
        ) -> None:
            marker_visible_during_dispatch.append(
                client.query_was_recently_dispatched(client_order_id)
            )
            super()._query_persisted_order(
                capability,
                client_order_id,
                instrument_ref=instrument_ref,
            )
            raise RuntimeError("LOCAL_QUERY_DISPATCH_FAILED")

    adapter = ReentrantAdapter(capability)
    client = NautilusVenueExecutionClient(lambda activation_id: adapter, capability)
    action = _action()

    with pytest.raises(RuntimeError, match="LOCAL_QUERY_DISPATCH_FAILED"):
        client.query_order(action)

    assert marker_visible_during_dispatch == [True]
    assert client.query_was_recently_dispatched(action.client_order_id) is False


def test_query_dispatch_markers_prune_stale_identities() -> None:
    capability = object()
    adapter = _Adapter(capability)
    observed_monotonic = [10.0]
    client = NautilusVenueExecutionClient(
        lambda activation_id: adapter,
        capability,
        monotonic_time_provider=lambda: observed_monotonic[0],
    )
    first = _action()
    second = first.model_copy(update={"client_order_id": "e" * 32})

    client.query_order(first)
    observed_monotonic[0] = 311.0
    client.query_order(second)

    assert set(client._query_dispatched_at) == {"e" * 32}


@pytest.mark.parametrize(
    ("policy", "limit", "expected"),
    (
        (
            {
                "order_type": "LIMIT",
                "time_in_force": "GTC",
                "post_only": False,
                "price_match": None,
                "expire_at": None,
            },
            True,
            {
                "time_in_force": "GTC",
                "post_only": False,
                "price_match": None,
                "expire_at": None,
            },
        ),
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
            {
                "order_type": "MARKET",
                "time_in_force": "IOC",
                "post_only": False,
                "price_match": None,
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
        self._instrument_id = InstrumentId.from_str("BTCUSDT-PERP.BINANCE")
        self.cache = _Cache()
        self.order_factory = _OrderFactory()
        self.submitted: list[tuple[object, dict[str, object]]] = []

    def _require_persisted_action_capability(self, capability: object) -> None:
        if capability is not self.capability:
            raise RuntimeError("AUTHORIZATION_MISMATCH")

    def submit_order(self, order: object, **kwargs: object) -> None:
        self.submitted.append((order, kwargs))


class _QueryCache:
    def __init__(self, order: object | None = None) -> None:
        self.order_value = order

    def order(self, _client_order_id: object) -> object | None:
        return self.order_value


class _QueryClock:
    def timestamp_ns(self) -> int:
        return 123_456_789


class _QueryMessageBus:
    def __init__(self, *, endpoint_available: bool = True) -> None:
        self.endpoint_available = endpoint_available
        self.sent: list[tuple[str, object]] = []

    def endpoints(self) -> list[str]:
        return ["ExecEngine.execute"] if self.endpoint_available else []

    def send(self, endpoint: str, msg: object) -> None:
        self.sent.append((endpoint, msg))


def test_adapter_releases_terminal_order_only_after_event_is_persisted() -> None:
    observed: list[object] = []
    adapter = HalphaStrategyAdapter.__new__(HalphaStrategyAdapter)
    adapter._execution_event_sink = observed.append
    adapter._persisted_orders = {"terminal-order": object()}
    event = SimpleNamespace(client_order_id="terminal-order")

    adapter.on_order_canceled(event)

    assert observed == [event]
    assert adapter._persisted_orders == {}


def test_adapter_retains_order_when_terminal_event_persistence_fails() -> None:
    adapter = HalphaStrategyAdapter.__new__(HalphaStrategyAdapter)
    adapter._execution_event_sink = lambda _event: (_ for _ in ()).throw(
        RuntimeError("database unavailable")
    )
    order = object()
    adapter._persisted_orders = {"terminal-order": order}

    with pytest.raises(RuntimeError, match="database unavailable"):
        adapter.on_order_canceled(
            SimpleNamespace(client_order_id="terminal-order")
        )

    assert adapter._persisted_orders == {"terminal-order": order}


def test_adapter_keeps_partial_fill_and_releases_completed_fill() -> None:
    adapter = HalphaStrategyAdapter.__new__(HalphaStrategyAdapter)
    adapter._execution_event_sink = lambda _event: None
    event = SimpleNamespace(client_order_id="filled-order")
    adapter._persisted_orders = {
        "filled-order": SimpleNamespace(is_closed=False)
    }

    adapter.on_order_filled(event)
    assert "filled-order" in adapter._persisted_orders

    adapter._persisted_orders["filled-order"].is_closed = True
    adapter.on_order_filled(event)
    assert "filled-order" not in adapter._persisted_orders


class _AdapterQueryHarness:
    def __init__(
        self,
        *,
        cached_order: object | None = None,
        endpoint_available: bool = True,
    ) -> None:
        self.capability = object()
        self._persisted_action_capability = self.capability
        self._persisted_orders: dict[str, object] = {}
        self._instrument_id = InstrumentId.from_str("BTCUSDT-PERP.BINANCE")
        self.cache = _QueryCache(cached_order)
        self.trader_id = TraderId("TRADER-001")
        self.id = StrategyId("HALPHA-001")
        self.clock = _QueryClock()
        self.msgbus = _QueryMessageBus(endpoint_available=endpoint_available)
        self.queried: list[object] = []

    def _require_persisted_action_capability(self, capability: object) -> None:
        if capability is not self.capability:
            raise RuntimeError("AUTHORIZATION_MISMATCH")

    def query_order(self, order: object) -> None:
        self.queried.append(order)


def test_adapter_queries_original_identity_when_cache_order_is_missing() -> None:
    harness = _AdapterQueryHarness()

    command = HalphaStrategyAdapter._query_persisted_order(
        harness,
        harness.capability,
        "4" * 32,
        instrument_ref="BTCUSDT-PERP",
    )

    assert isinstance(command, QueryOrder)
    assert str(command.trader_id) == "TRADER-001"
    assert str(command.strategy_id) == "HALPHA-001"
    assert str(command.instrument_id) == "BTCUSDT-PERP.BINANCE"
    assert str(command.client_order_id) == "4" * 32
    assert command.venue_order_id is None
    assert harness.queried == []
    assert harness.msgbus.sent == [("ExecEngine.execute", command)]


def test_adapter_cache_miss_query_fails_if_execution_endpoint_is_missing() -> None:
    harness = _AdapterQueryHarness(endpoint_available=False)

    with pytest.raises(
        RuntimeError,
        match="EXECUTION_QUERY_ENDPOINT_UNAVAILABLE",
    ):
        HalphaStrategyAdapter._query_persisted_order(
            harness,
            harness.capability,
            "5" * 32,
            instrument_ref="BTCUSDT-PERP",
        )

    assert harness.msgbus.sent == []


def test_adapter_cache_hit_keeps_native_strategy_query_path() -> None:
    cached_order = type(
        "_CachedOrder",
        (),
        {"venue_order_id": "12345"},
    )()
    harness = _AdapterQueryHarness(cached_order=cached_order)

    returned = HalphaStrategyAdapter._query_persisted_order(
        harness,
        harness.capability,
        "6" * 32,
        instrument_ref="BTCUSDT-PERP",
    )

    assert returned is cached_order
    assert harness.queried == [cached_order]
    assert harness.msgbus.sent == []


def test_adapter_cache_hit_without_venue_order_id_queries_original_identity() -> None:
    cached_order = type(
        "_CachedOrder",
        (),
        {"venue_order_id": None},
    )()
    harness = _AdapterQueryHarness(cached_order=cached_order)

    command = HalphaStrategyAdapter._query_persisted_order(
        harness,
        harness.capability,
        "7" * 32,
        instrument_ref="BTCUSDT-PERP",
    )

    assert isinstance(command, QueryOrder)
    assert str(command.client_order_id) == "7" * 32
    assert command.venue_order_id is None
    assert harness.queried == []
    assert harness.msgbus.sent == [("ExecEngine.execute", command)]


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


def test_adapter_maps_short_reduce_market_to_buy_and_reduce_only() -> None:
    harness = _AdapterWriteHarness()

    HalphaStrategyAdapter._submit_persisted_order(
        harness,
        harness.capability,
        profile="REDUCE_OR_CLOSE_MARKET",
        instrument_ref="BTCUSDT-PERP",
        direction="SHORT",
        quantity="0.01",
        price=None,
        trigger_price=None,
        reduce_only=True,
        client_order_id="5" * 32,
        position_side="BOTH",
    )

    terms = harness.order_factory.market_terms[0]
    assert terms["order_side"] is OrderSide.BUY
    assert terms["reduce_only"] is True
    assert len(harness.submitted) == 1


def test_adapter_routes_hedge_reduce_through_nautilus_position_id() -> None:
    harness = _AdapterWriteHarness()

    HalphaStrategyAdapter._submit_persisted_order(
        harness,
        harness.capability,
        profile="REDUCE_OR_CLOSE_MARKET",
        instrument_ref="BTCUSDT-PERP",
        direction="LONG",
        quantity="0.01",
        price=None,
        trigger_price=None,
        reduce_only=True,
        client_order_id="6" * 32,
        position_side="LONG",
    )

    terms = harness.order_factory.market_terms[0]
    assert terms["order_side"] is OrderSide.SELL
    assert terms["reduce_only"] is True
    assert str(harness.submitted[0][1]["position_id"]).endswith("-LONG")


def test_adapter_rejects_cross_instrument_persisted_write() -> None:
    harness = _AdapterWriteHarness()

    with pytest.raises(RuntimeError, match="AUTHORIZATION_MISMATCH"):
        HalphaStrategyAdapter._submit_persisted_order(
            harness,
            harness.capability,
            profile="ENTRY_MARKET",
            instrument_ref="ETHUSDT-PERP",
            direction="LONG",
            quantity="0.01",
            price=None,
            trigger_price=None,
            reduce_only=False,
            client_order_id="4" * 32,
        )

    assert harness.submitted == []


@pytest.mark.parametrize(
    ("profile", "direction", "reduce_only", "reason"),
    (
        ("ENTRY_MARKET", "UNKNOWN", False, "ACTION_DIRECTION_INVALID"),
        ("ENTRY_MARKET", "LONG", "false", "ACTION_REDUCE_ONLY_INVALID"),
        (
            "ENTRY_MARKET",
            "LONG",
            True,
            "ACTION_REDUCE_ONLY_PROFILE_MISMATCH",
        ),
        (
            "REDUCE_OR_CLOSE_MARKET",
            "LONG",
            False,
            "ACTION_REDUCE_ONLY_PROFILE_MISMATCH",
        ),
        (
            "PROTECTIVE_STOP_REDUCE_ONLY",
            "LONG",
            False,
            "ACTION_REDUCE_ONLY_PROFILE_MISMATCH",
        ),
        (
            "TAKE_PROFIT_1",
            "LONG",
            False,
            "ACTION_REDUCE_ONLY_PROFILE_MISMATCH",
        ),
    ),
)
def test_adapter_rejects_direction_or_reduce_only_profile_mismatch(
    profile: str,
    direction: str,
    reduce_only: object,
    reason: str,
) -> None:
    harness = _AdapterWriteHarness()

    with pytest.raises(ValueError, match=reason):
        HalphaStrategyAdapter._submit_persisted_order(
            harness,
            harness.capability,
            profile=profile,
            instrument_ref="BTCUSDT-PERP",
            direction=direction,
            quantity="0.01",
            price=None,
            trigger_price="49000",
            reduce_only=reduce_only,
            client_order_id="8" * 32,
            position_side=(
                "BOTH" if profile == "REDUCE_OR_CLOSE_MARKET" else None
            ),
        )

    assert harness.submitted == []
