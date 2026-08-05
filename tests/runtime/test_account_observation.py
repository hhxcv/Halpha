from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from nautilus_trader.adapters.binance.common.enums import BinanceEnvironment
from pydantic import SecretStr

import halpha.executor.account_observation as account_observation_module
from halpha.executor.account_observation import (
    AccountObservationError,
    ProductAccountObserver,
    build_account_snapshot_fact,
)
from halpha.venue_integration.models import (
    VenueFactKind,
    VenueFactSourceClass,
)


POSITION = {
    "symbol": "SOLUSDT",
    "positionAmt": "-2.5",
    "entryPrice": "152.25",
    "breakEvenPrice": "152.31",
    "markPrice": "154.00",
    "unRealizedProfit": "-4.375",
    "liquidationPrice": "271.8",
    "leverage": "3",
    "marginType": "cross",
    "notional": "-385",
    "isolatedMargin": "0",
    "positionSide": "BOTH",
    "updateTime": 1785661200000,
}

SYMBOL_CONFIG = {
    "symbol": "SOLUSDT",
    "marginType": "CROSSED",
    "leverage": 3,
}

ORDINARY_ORDER = {
    "symbol": "SOLUSDT",
    "orderId": 1234,
    "clientOrderId": "external-order",
    "price": "150.5",
    "origQty": "1.25",
    "executedQty": "0",
    "status": "NEW",
    "timeInForce": "GTC",
    "type": "LIMIT",
    "side": "BUY",
    "stopPrice": "0",
    "time": 1785661200000,
    "updateTime": 1785661201000,
    "reduceOnly": False,
    "positionSide": "SHORT",
    "closePosition": False,
}

ALGO_ORDER = {
    "algoId": 5678,
    "clientAlgoId": "external-algo",
    "algoType": "CONDITIONAL",
    "orderType": "STOP_MARKET",
    "symbol": "SOLUSDT",
    "side": "BUY",
    "positionSide": "SHORT",
    "timeInForce": "GTC",
    "quantity": "2.5",
    "algoStatus": "NEW",
    "triggerPrice": "160",
    "price": "0",
    "closePosition": False,
    "reduceOnly": True,
    "createTime": 1785661202000,
    "updateTime": 1785661203000,
}


def test_complete_account_snapshot_keeps_external_origin_unattributed() -> None:
    started_at = datetime(2026, 8, 2, 4, 0, tzinfo=UTC)
    checked_at = datetime(2026, 8, 2, 4, 0, 1, tzinfo=UTC)

    fact = build_account_snapshot_fact(
        environment_id="binance-live-copy-primary",
        account_ref="binance-usdm-copy-lead-primary",
        positions=[
            POSITION,
            {**POSITION, "symbol": "BTCUSDT", "positionAmt": "0"},
        ],
        symbol_configs=[SYMBOL_CONFIG],
        open_orders=[ORDINARY_ORDER],
        open_algo_orders=[ALGO_ORDER],
        started_at=started_at,
        checked_at=checked_at,
    )

    assert fact.kind is VenueFactKind.ACCOUNT_STATE
    assert fact.source_class is VenueFactSourceClass.VENUE_QUERY
    assert fact.activation_ref is None
    assert fact.action_ref is None
    assert fact.attribution_class is None
    assert fact.payload["snapshot_complete"] is True
    assert fact.payload["query_paths"][0] == "/fapi/v3/positionRisk"
    assert fact.payload["management_authority"] == "NONE"
    assert fact.payload["open_position_count"] == 1
    assert fact.payload["ordinary_open_order_count"] == 1
    assert fact.payload["algo_open_order_count"] == 1
    assert fact.payload["ordinary_open_orders"] == [
        {
            "kind": "ORDINARY",
            "instrument_ref": "SOLUSDT-PERP",
            "symbol": "SOLUSDT",
            "order_id": "1234",
            "client_order_id": "external-order",
            "side": "BUY",
            "position_side": "SHORT",
            "order_type": "LIMIT",
            "status": "NEW",
            "time_in_force": "GTC",
            "price": "150.5",
            "trigger_price": "0",
            "quantity": "1.25",
            "executed_quantity": "0",
            "reduce_only": False,
            "close_position": False,
            "source_create_time_ms": 1785661200000,
            "source_update_time_ms": 1785661201000,
        }
    ]
    assert fact.payload["algo_open_orders"] == [
        {
            "kind": "ALGO",
            "instrument_ref": "SOLUSDT-PERP",
            "symbol": "SOLUSDT",
            "order_id": "5678",
            "client_order_id": "external-algo",
            "side": "BUY",
            "position_side": "SHORT",
            "order_type": "STOP_MARKET",
            "status": "NEW",
            "time_in_force": "GTC",
            "price": "0",
            "trigger_price": "160",
            "quantity": "2.5",
            "executed_quantity": None,
            "reduce_only": True,
            "close_position": False,
            "source_create_time_ms": 1785661202000,
            "source_update_time_ms": 1785661203000,
        }
    ]
    assert fact.payload["positions"] == [
        {
            "instrument_ref": "SOLUSDT-PERP",
            "symbol": "SOLUSDT",
            "direction": "SHORT",
            "position_side": "BOTH",
            "quantity": "-2.5",
            "absolute_quantity": "2.5",
            "entry_price": "152.25",
            "break_even_price": "152.31",
            "mark_price": "154",
            "unrealized_pnl": "-4.375",
            "liquidation_price": "271.8",
            "leverage": 3,
            "margin_mode": "CROSS",
            "notional": "-385",
            "isolated_margin": "0",
            "source_update_time_ms": 1785661200000,
        }
    ]


def test_hedge_mode_keeps_long_and_short_account_sides_distinct() -> None:
    fact = build_account_snapshot_fact(
        environment_id="binance-live-copy-primary",
        account_ref="binance-usdm-copy-lead-primary",
        positions=[
            {
                **POSITION,
                "positionAmt": "2.5",
                "positionSide": "LONG",
                "unRealizedProfit": "3.25",
                "notional": "385",
            },
            {**POSITION, "positionSide": "SHORT"},
        ],
        symbol_configs=[SYMBOL_CONFIG],
        open_orders=[],
        open_algo_orders=[],
        started_at=datetime(2026, 8, 2, 4, 0, tzinfo=UTC),
        checked_at=datetime(2026, 8, 2, 4, 0, 1, tzinfo=UTC),
    )

    assert fact.payload["open_position_count"] == 2
    assert [
        (position["position_side"], position["direction"], position["quantity"])
        for position in fact.payload["positions"]
    ] == [
        ("LONG", "LONG", "2.5"),
        ("SHORT", "SHORT", "-2.5"),
    ]


@pytest.mark.parametrize(
    "change",
    (
        {"positionAmt": "not-a-number"},
        {"markPrice": "0"},
        {"positionSide": "LONG"},
    ),
)
def test_invalid_nonzero_position_rejects_the_whole_snapshot(
    change: dict[str, object],
) -> None:
    with pytest.raises(AccountObservationError):
        build_account_snapshot_fact(
            environment_id="binance-live-copy-primary",
            account_ref="binance-usdm-copy-lead-primary",
            positions=[{**POSITION, **change}],
            symbol_configs=[SYMBOL_CONFIG],
            open_orders=[],
            open_algo_orders=[],
            started_at=datetime(2026, 8, 2, 4, 0, tzinfo=UTC),
            checked_at=datetime(2026, 8, 2, 4, 0, 1, tzinfo=UTC),
        )


def test_missing_or_invalid_symbol_configuration_rejects_the_snapshot() -> None:
    with pytest.raises(AccountObservationError):
        build_account_snapshot_fact(
            environment_id="binance-live-copy-primary",
            account_ref="binance-usdm-copy-lead-primary",
            positions=[POSITION],
            symbol_configs=[{**SYMBOL_CONFIG, "marginType": "unknown"}],
            open_orders=[],
            open_algo_orders=[],
            started_at=datetime(2026, 8, 2, 4, 0, tzinfo=UTC),
            checked_at=datetime(2026, 8, 2, 4, 0, 1, tzinfo=UTC),
        )


def test_observer_queries_only_read_surfaces_and_persists_one_complete_fact() -> None:
    calls: list[str] = []

    class AccountApi:
        async def query_futures_position_risk(self, **kwargs: object):
            calls.append(f"positions:{kwargs['recv_window']}")
            return [POSITION]

        async def query_open_orders(self, **kwargs: object):
            calls.append(f"orders:{kwargs['recv_window']}")
            return []

        async def query_open_algo_orders(self, **kwargs: object):
            calls.append(f"algo:{kwargs['recv_window']}")
            return []

        async def query_futures_symbol_config(self, **kwargs: object):
            calls.append(f"config:{kwargs['recv_window']}")
            return [SYMBOL_CONFIG]

    class Repository:
        facts: list[object] = []

        def insert(self, fact: object) -> bool:
            self.facts.append(fact)
            return True

    repository = Repository()
    observer = ProductAccountObserver(
        profile="BINANCE_LIVE_READ_ONLY",
        environment_id="binance-live-copy-primary",
        account_ref="binance-usdm-copy-lead-primary",
        api_key=SecretStr("read-key"),
        api_secret=SecretStr("read-secret"),
        proxy_url="http://127.0.0.1:7897",
        repository=repository,
        account_api=AccountApi(),
    )

    fact = asyncio.run(observer.observe())

    assert sorted(calls) == [
        "algo:5000",
        "config:5000",
        "orders:5000",
        "positions:5000",
    ]
    assert repository.facts == [fact]
    assert fact.payload["positions"][0]["instrument_ref"] == "SOLUSDT-PERP"


def test_account_observer_reuses_the_same_read_path_in_live_write() -> None:
    class Repository:
        @staticmethod
        def insert(_fact: object) -> bool:
            return True

    account_api = object()
    observer = ProductAccountObserver(
        profile="BINANCE_LIVE_WRITE",
        environment_id="binance-live-copy-primary",
        account_ref="binance-usdm-copy-lead-primary",
        api_key=SecretStr("write-key"),
        api_secret=SecretStr("write-secret"),
        proxy_url=None,
        repository=Repository(),
        account_api=account_api,
    )

    assert observer._account_api is account_api


def test_account_observer_routes_demo_profile_to_demo_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    account_api = object()

    def http_client(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    def account_api_factory(*_args: object) -> object:
        return account_api

    monkeypatch.setattr(
        account_observation_module,
        "get_cached_binance_http_client",
        http_client,
    )
    monkeypatch.setattr(
        account_observation_module,
        "BinanceFuturesAccountHttpAPI",
        account_api_factory,
    )

    observer = ProductAccountObserver(
        profile="BINANCE_DEMO",
        environment_id="binance-demo-primary",
        account_ref="binance-usdm-demo-owner-primary",
        api_key=SecretStr("demo-key"),
        api_secret=SecretStr("demo-secret"),
        proxy_url="http://127.0.0.1:7897",
        repository=object(),  # type: ignore[arg-type]
    )

    assert captured["environment"] is BinanceEnvironment.DEMO
    assert observer._account_api is account_api


def test_observer_failure_is_sanitized_and_never_persists_a_partial_snapshot() -> None:
    secret = "secret-must-not-escape"

    class AccountApi:
        async def query_futures_position_risk(self, **_kwargs: object):
            raise OSError(secret)

        async def query_open_orders(self, **_kwargs: object):
            return []

        async def query_open_algo_orders(self, **_kwargs: object):
            return []

        async def query_futures_symbol_config(self, **_kwargs: object):
            return [SYMBOL_CONFIG]

    class Repository:
        def insert(self, _fact: object) -> bool:
            raise AssertionError("partial snapshot must not be persisted")

    observer = ProductAccountObserver(
        profile="BINANCE_LIVE_READ_ONLY",
        environment_id="binance-live-copy-primary",
        account_ref="binance-usdm-copy-lead-primary",
        api_key=SecretStr("read-key"),
        api_secret=SecretStr("read-secret"),
        proxy_url=None,
        repository=Repository(),
        account_api=AccountApi(),
    )

    with pytest.raises(AccountObservationError) as captured:
        asyncio.run(observer.observe())

    assert str(captured.value) == "ACCOUNT_SNAPSHOT_QUERY_FAILED_OSERROR"
    assert secret not in str(captured.value)
    assert captured.value.retryable is True


def test_observer_preserves_binance_retry_after_without_leaking_response() -> None:
    class RateLimitedError(RuntimeError):
        status = 429
        headers = {"Retry-After": "90"}

    class AccountApi:
        async def query_futures_position_risk(self, **_kwargs: object):
            raise RateLimitedError("private response")

        async def query_open_orders(self, **_kwargs: object):
            return []

        async def query_open_algo_orders(self, **_kwargs: object):
            return []

        async def query_futures_symbol_config(self, **_kwargs: object):
            return [SYMBOL_CONFIG]

    class Repository:
        def insert(self, _fact: object) -> bool:
            raise AssertionError("partial snapshot must not be persisted")

    observer = ProductAccountObserver(
        profile="BINANCE_LIVE_READ_ONLY",
        environment_id="binance-live-copy-primary",
        account_ref="binance-usdm-copy-lead-primary",
        api_key=SecretStr("read-key"),
        api_secret=SecretStr("read-secret"),
        proxy_url=None,
        repository=Repository(),
        account_api=AccountApi(),
    )

    with pytest.raises(AccountObservationError) as captured:
        asyncio.run(observer.observe())

    assert captured.value.retry_after_seconds == 90.0
    assert captured.value.retryable is True
    assert "private response" not in str(captured.value)
