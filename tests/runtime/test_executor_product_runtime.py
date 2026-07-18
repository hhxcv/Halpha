from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from nautilus_trader.adapters.binance.common.enums import BinanceEnvironment
from pydantic import SecretStr

import halpha.executor.runtime as runtime_module
from halpha.domain_values import content_digest
from halpha.executor.forward_observation import ForwardObservationSpec
from halpha.executor.runtime import (
    ExecutorRuntimeError,
    ProductExecutorRuntime,
    _cached_leaves_quantity,
    _connect_product_database,
    build_product_node_config,
)
from halpha.planning.adapter import HalphaStrategyAdapter
from halpha.planning.bar_evaluation import NautilusBarEntryEvaluator
from halpha.planning.registry import OneShotParameters
from halpha.planning.strategies.one_shot import OneShotDonchianAtrLogic


def _config(profile: str):
    return build_product_node_config(
        profile,
        api_key=(
            None
            if profile == "BINANCE_LIVE_READ_ONLY"
            else SecretStr("qualification-key")
        ),
        api_secret=(
            None
            if profile == "BINANCE_LIVE_READ_ONLY"
            else SecretStr("qualification-secret")
        ),
        log_directory=Path("logs"),
    )


def test_demo_product_node_uses_the_accepted_single_topology() -> None:
    node, provider, data, execution = _config("BINANCE_DEMO")

    assert execution is not None
    assert data.instrument_provider is provider
    assert execution.instrument_provider is provider
    assert data.environment is BinanceEnvironment.DEMO
    assert execution.environment is BinanceEnvironment.DEMO
    assert {str(item) for item in provider.load_ids or ()} == {
        "BTCUSDT-PERP.BINANCE",
        "ETHUSDT-PERP.BINANCE",
    }
    assert provider.load_all is False
    assert provider.query_commission_rates is True
    assert execution.max_retries is None
    assert execution.use_reduce_only is True
    assert execution.use_position_ids is True
    assert execution.futures_leverages is None
    assert execution.futures_margin_types is None
    assert node.cache is None
    assert node.message_bus is None
    assert node.emulator is None
    assert node.load_state is False
    assert node.save_state is False
    assert node.exec_engine.reconciliation is True
    assert node.exec_engine.reconciliation_startup_delay_secs == 10.0
    assert node.exec_engine.inflight_check_interval_ms == 0
    assert node.exec_engine.open_check_open_only is True
    assert node.exec_engine.generate_missing_orders is True
    assert node.controller is not None
    assert node.controller.controller_path == (
        "halpha.executor.runtime:HalphaRuntimeController"
    )


def test_demo_and_live_write_change_only_environment_qualified_inputs() -> None:
    demo_node, _demo_provider, _demo_data, _demo_execution = _config("BINANCE_DEMO")
    live_node, live_provider, live_data, live_execution = _config("BINANCE_LIVE_WRITE")

    assert live_execution is not None
    assert live_data.environment is BinanceEnvironment.LIVE
    assert live_execution.environment is BinanceEnvironment.LIVE
    assert {str(item) for item in live_provider.load_ids or ()} == {
        "BTCUSDT-PERP.BINANCE"
    }
    assert type(demo_node) is type(live_node)
    assert type(demo_node.exec_engine) is type(live_node.exec_engine)
    assert demo_node.controller == live_node.controller
    demo_engine = demo_node.exec_engine.dict()
    live_engine = live_node.exec_engine.dict()
    demo_engine.pop("reconciliation_instrument_ids")
    live_engine.pop("reconciliation_instrument_ids")
    assert demo_engine == live_engine


def test_live_read_only_uses_data_client_and_same_controller_without_execution() -> (
    None
):
    node, provider, data, execution = _config("BINANCE_LIVE_READ_ONLY")

    assert data.instrument_provider is provider
    assert data.environment is BinanceEnvironment.LIVE
    assert data.api_key is None
    assert data.api_secret is None
    assert provider.query_commission_rates is False
    assert execution is None
    assert node.exec_clients == {}
    assert node.exec_engine.reconciliation is False
    assert node.exec_engine.generate_missing_orders is False
    assert node.exec_engine.inflight_check_interval_ms == 0
    assert node.exec_engine.open_check_interval_secs is None
    assert node.exec_engine.position_check_interval_secs is None
    assert node.controller is not None
    assert node.controller.controller_path == (
        "halpha.executor.runtime:HalphaRuntimeController"
    )
    assert {str(item) for item in provider.load_ids or ()} == {"BTCUSDT-PERP.BINANCE"}


def _forward_spec() -> ForwardObservationSpec:
    starts_at = datetime(2026, 7, 18, tzinfo=UTC)
    parameters = OneShotParameters(
        direction="LONG",
        channel_lookback_15m=96,
        confirmation_bars_1m=3,
        initial_stop_atr_multiple="1",
        max_entry_extension_atr="0.1",
        take_profit_1_r="1",
        take_profit_1_fraction="0.75",
        take_profit_2_r="2",
        max_hold_bars_15m=96,
        entry_valid_minutes=1440,
    )
    return ForwardObservationSpec(
        observation_id="b04-live-read-only-20260718",
        activation_id="b04-live-read-only-btcusdt",
        strategy_evidence_digest="1" * 64,
        configuration_digest="2" * 64,
        parameters=parameters,
        parameter_digest=content_digest(parameters.model_dump(mode="json")),
        starts_at=starts_at,
        minimum_end_at=starts_at + timedelta(days=7),
        maximum_end_at=starts_at + timedelta(days=14),
        max_allowed_loss="50",
        max_notional="500",
        max_margin="100",
        effective_leverage="5",
    )


def test_live_read_only_sizing_snapshot_canonicalizes_instrument_values() -> None:
    class Cache:
        @staticmethod
        def instrument(_instrument_id):
            return SimpleNamespace(
                size_increment=Decimal("0.001000"),
                price_increment=Decimal("0.10"),
                min_quantity=Decimal("0.001"),
                max_quantity=Decimal("100.000"),
                min_notional=Decimal("5.000"),
                taker_fee=Decimal("0.0004000"),
            )

        @staticmethod
        def quote_tick(_instrument_id):
            return SimpleNamespace(
                ask_price=Decimal("60000.100"),
                bid_price=Decimal("59999.900"),
            )

        @staticmethod
        def mark_price(_instrument_id):
            return Decimal("60000")

    runtime = object.__new__(ProductExecutorRuntime)
    runtime._forward_observation_spec = _forward_spec()
    runtime._node = SimpleNamespace(cache=Cache())

    snapshot = runtime._read_only_sizing_snapshot(object())

    assert snapshot is not None
    assert snapshot.reference_price == "60000.100"
    assert snapshot.taker_fee_rate == "0.0004"
    assert snapshot.rules.step_size == "0.001"
    assert snapshot.rules.price_tick_size == "0.1"
    assert snapshot.rules.min_quantity == "0.001"
    assert snapshot.rules.max_market_quantity == "100"
    assert snapshot.rules.min_notional == "5"


def test_live_read_only_runtime_build_never_loads_database_or_exec_factory(
    monkeypatch,
) -> None:
    calls: dict[str, int] = {"connector": 0, "data_factory": 0, "exec_factory": 0}
    created: list[object] = []

    class FakeController:
        def create_strategy(self, strategy, start=True):
            assert start is True
            created.append(strategy)

        def stop_strategy(self, _strategy):
            return None

        def remove_strategy(self, _strategy):
            return None

    controller = FakeController()

    class FakeTrader:
        def actors(self):
            return [controller]

    class FakeNode:
        def __init__(self, *, config, loop):
            self.config = config
            self.loop = loop
            self.trader = FakeTrader()

        def add_data_client_factory(self, _venue, _factory):
            calls["data_factory"] += 1

        def add_exec_client_factory(self, _venue, _factory):
            calls["exec_factory"] += 1

        def build(self):
            return None

        def is_running(self):
            return False

        def dispose(self):
            return None

    def connector(**_kwargs):
        calls["connector"] += 1
        raise AssertionError(
            "read-only runtime must not connect to the product database"
        )

    monkeypatch.setattr(runtime_module, "HalphaRuntimeController", FakeController)
    settings = SimpleNamespace(
        release=SimpleNamespace(
            profile="BINANCE_LIVE_READ_ONLY",
            database_name="halpha_live",
            environment_id="live-read-only",
            authority_class="NO_TRADING_AUTHORITY",
            account_id="binance-live",
        )
    )
    runtime = ProductExecutorRuntime(
        settings=settings,
        database_password=None,
        api_key=None,
        api_secret=None,
        log_directory=Path("logs"),
        forward_observation_spec=_forward_spec(),
        connector=connector,
        node_factory=FakeNode,
    )
    try:
        runtime.build()
        assert runtime.node.config.exec_clients == {}
        assert calls == {"connector": 0, "data_factory": 1, "exec_factory": 0}
        with pytest.raises(ExecutorRuntimeError, match="PRODUCT_RUNTIME_NOT_BUILT"):
            runtime.coordinator
        runtime._start_read_only_adapter()
        assert len(created) == 1
        adapter = created[0]
        assert isinstance(adapter, HalphaStrategyAdapter)
        assert isinstance(adapter._logic, OneShotDonchianAtrLogic)
        assert isinstance(adapter._bar_evaluator, NautilusBarEntryEvaluator)
        assert adapter._persisted_action_capability is None
        assert adapter._execution_event_sink is None
    finally:
        runtime.close()


def test_live_read_only_runtime_rejects_database_credential() -> None:
    settings = SimpleNamespace(
        release=SimpleNamespace(profile="BINANCE_LIVE_READ_ONLY")
    )
    runtime = ProductExecutorRuntime(
        settings=settings,
        database_password=SecretStr("forbidden"),
        api_key=None,
        api_secret=None,
        log_directory=Path("logs"),
        forward_observation_spec=_forward_spec(),
    )
    try:
        with pytest.raises(
            ExecutorRuntimeError,
            match="READ_ONLY_DATABASE_CREDENTIAL_FORBIDDEN",
        ):
            runtime.build()
    finally:
        runtime.close()


def test_live_read_only_runtime_rejects_binance_credentials() -> None:
    settings = SimpleNamespace(
        release=SimpleNamespace(profile="BINANCE_LIVE_READ_ONLY")
    )
    runtime = ProductExecutorRuntime(
        settings=settings,
        database_password=None,
        api_key=SecretStr("forbidden"),
        api_secret=SecretStr("forbidden"),
        log_directory=Path("logs"),
        forward_observation_spec=_forward_spec(),
    )
    try:
        with pytest.raises(
            ExecutorRuntimeError,
            match="READ_ONLY_BINANCE_CREDENTIAL_FORBIDDEN",
        ):
            runtime.build()
    finally:
        runtime.close()


def test_runtime_source_does_not_depend_on_qualification_fixtures() -> None:
    source = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "halpha"
        / "executor"
        / "runtime.py"
    ).read_text(encoding="utf-8")
    assert "tools.qualification" not in source
    assert "BINANCE_API_KEY" not in source
    assert "BINANCE_API_SECRET" not in source


def test_cached_leaves_quantity_uses_the_framework_order_projection() -> None:
    requested: list[str] = []

    class Cache:
        def order(self, client_order_id):
            requested.append(str(client_order_id))
            return SimpleNamespace(leaves_qty="0.000")

    assert (
        _cached_leaves_quantity(
            Cache(),
            "0123456789abcdef0123456789abcdef",
        )
        == "0.000"
    )
    assert requested == ["0123456789abcdef0123456789abcdef"]


def test_cached_leaves_quantity_preserves_unknown_when_order_is_absent() -> None:
    cache = SimpleNamespace(order=lambda _client_order_id: None)

    assert (
        _cached_leaves_quantity(
            cache,
            "0123456789abcdef0123456789abcdef",
        )
        is None
    )


def test_product_database_connection_uses_explicit_transactions_on_autocommit() -> None:
    captured: dict[str, object] = {}
    connection = object()

    def connector(**kwargs):
        captured.update(kwargs)
        return connection

    assert (
        _connect_product_database(
            connector,
            database_name="halpha_demo",
            password="qualification-password",
        )
        is connection
    )
    assert captured == {
        "host": "127.0.0.1",
        "port": 5432,
        "dbname": "halpha_demo",
        "user": "halpha_demo_executor",
        "password": "qualification-password",
        "connect_timeout": 2,
        "autocommit": True,
    }
