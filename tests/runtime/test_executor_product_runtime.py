from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from nautilus_trader.adapters.binance.common.enums import BinanceEnvironment
from nautilus_trader.model.identifiers import Venue
from pydantic import SecretStr

import halpha.executor.runtime as runtime_module
from halpha.domain_values import content_digest
from halpha.executor.forward_observation import ForwardObservationSpec
from halpha.executor.runtime import (
    ExecutorRuntimeError,
    ProductExecutorRuntime,
    _activation_entry_deadline,
    _cached_leaves_quantity,
    _connect_product_database,
    build_product_node_config,
)
from halpha.product_build import EXECUTOR_STARTING_APPLICATION_NAME
from halpha.planning.adapter import HalphaStrategyAdapter
from halpha.planning.bar_evaluation import NautilusBarEntryEvaluator
from halpha.planning.models import PlanLifecycle
from halpha.planning.registry import DIRECT_EXECUTION_REF, Direction, OneShotParameters
from halpha.planning.strategies.one_shot import OneShotDonchianAtrLogic


ROOT = Path(__file__).resolve().parents[2]


def test_runtime_submission_barrier_is_scoped_to_the_affected_activation() -> None:
    submitted: list[str] = []
    runtime = object.__new__(ProductExecutorRuntime)
    runtime._coordinator = SimpleNamespace(
        startup_recovery_allows_submission=lambda activation_id: (
            activation_id == "activation-clear"
        )
    )
    runtime._proposal_processors = {
        "activation-clear": SimpleNamespace(
            submit=lambda proposal: submitted.append(proposal.activation_id) or "accepted"
        )
    }

    with pytest.raises(ExecutorRuntimeError, match="STARTUP_RECOVERY_PENDING"):
        runtime.submit_strategy_proposal(
            SimpleNamespace(activation_id="activation-pending")
        )

    assert runtime.submit_strategy_proposal(
        SimpleNamespace(activation_id="activation-clear")
    ) == "accepted"
    assert submitted == ["activation-clear"]


def test_runtime_does_not_mark_recovery_complete_until_resolution_is_absorbed() -> None:
    action = SimpleNamespace(
        execution_action_id="startup-open",
        activation_id="activation-pending",
    )
    coordinator = SimpleNamespace(
        complete=False,
        sink=None,
    )
    coordinator.recover_unresolved_actions = lambda **values: (
        setattr(coordinator, "sink", values["resolution_sink"]) or (action,)
    )
    coordinator.startup_recovery_complete = lambda: coordinator.complete
    coordinator.startup_recovery_pending_action_ids = lambda: (
        () if coordinator.complete else (action.execution_action_id,)
    )
    coordinator.startup_recovery_allows_submission = (
        lambda _activation_id: coordinator.complete
    )
    responsibility_resumes: list[str] = []
    direct_resumes: list[str] = []
    events: list[tuple[str, dict[str, object]]] = []
    runtime = object.__new__(ProductExecutorRuntime)
    runtime._coordinator = coordinator
    runtime._recovered_action_count = 0
    runtime._recovery_complete = False
    runtime._responsibility_processors = {
        action.activation_id: SimpleNamespace(
            resume=responsibility_resumes.append
        )
    }
    runtime._direct_schedule_processors = {
        action.activation_id: SimpleNamespace(resume=direct_resumes.append)
    }
    runtime._runtime_event_sink = lambda event, fields: events.append((event, fields))

    recovered = runtime._begin_startup_recovery(
        observed_at=datetime(2026, 7, 23, 7, 0, tzinfo=UTC)
    )

    assert recovered == (action,)
    assert runtime.recovery_complete is False
    assert responsibility_resumes == []
    assert direct_resumes == []

    # The callback is invoked only after the coordinator has absorbed a fact.
    coordinator.complete = True
    runtime._apply_startup_recovery_resolution(
        action.activation_id,
        action.execution_action_id,
    )

    assert runtime.recovery_complete is True
    assert responsibility_resumes == [action.activation_id]
    assert direct_resumes == [action.activation_id]
    assert events[-1][0] == "startup_recovery_identity_resolved"


def test_activation_entry_deadline_uses_persisted_activation_window() -> None:
    activation = SimpleNamespace(
        rule_state={
            "deadlines": {"entry_valid_until": "2026-07-19T22:15:00+00:00"}
        }
    )

    assert _activation_entry_deadline(activation) == datetime(
        2026, 7, 19, 22, 15, tzinfo=UTC
    )


def test_activation_entry_deadline_rejects_missing_state() -> None:
    with pytest.raises(ExecutorRuntimeError, match="ENTRY_DEADLINE_MISSING"):
        _activation_entry_deadline(SimpleNamespace(rule_state={}))


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
    assert node.exec_engine.inflight_check_interval_ms == 2_000
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
    source_sha256 = {"src/halpha/example.py": "3" * 64}
    return ForwardObservationSpec(
        observation_id="read-only-check-20260718",
        activation_id="read-only-check-btcusdt",
        strategy_evidence_ref="build/evidence/reports/strategy-evidence.json",
        strategy_evidence_digest="1" * 64,
        configuration_digest="2" * 64,
        source_sha256=source_sha256,
        source_sha256_digest=content_digest(source_sha256),
        parameters=parameters,
        parameter_digest=content_digest(parameters.model_dump(mode="json")),
        starts_at=starts_at,
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
            application_name=EXECUTOR_STARTING_APPLICATION_NAME,
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
        "application_name": EXECUTOR_STARTING_APPLICATION_NAME,
    }


def test_product_runtime_publishes_ready_build_on_existing_connection() -> None:
    calls: list[tuple[str, tuple[str, ...]]] = []
    runtime = object.__new__(ProductExecutorRuntime)
    runtime._settings = SimpleNamespace(
        release=SimpleNamespace(profile="BINANCE_DEMO")
    )
    runtime._connection = SimpleNamespace(
        execute=lambda statement, parameters: calls.append((statement, parameters))
    )

    runtime.publish_ready_product_build("b" * 64)

    assert calls == [
        (
            "SELECT set_config('application_name', %s, false)",
            ("halpha-executor:ready:" + "b" * 40,),
        )
    ]


def test_live_write_product_runtime_fails_closed_without_an_open_runtime_gate() -> None:
    settings = SimpleNamespace(
        release=SimpleNamespace(profile="BINANCE_LIVE_WRITE")
    )
    runtime = ProductExecutorRuntime(
        settings=settings,
        database_password=SecretStr("qualification-password"),
        api_key=SecretStr("qualification-key"),
        api_secret=SecretStr("qualification-secret"),
        log_directory=Path("logs"),
    )
    try:
        with pytest.raises(
            ExecutorRuntimeError,
            match="RUNTIME_REAL_WRITE_GATE_CLOSED",
        ):
            runtime.build()
    finally:
        runtime.close()


def test_live_write_runtime_requires_a_current_submission_guard_even_when_open() -> None:
    settings = SimpleNamespace(
        release=SimpleNamespace(profile="BINANCE_LIVE_WRITE")
    )
    runtime = ProductExecutorRuntime(
        settings=settings,
        database_password=SecretStr("qualification-password"),
        api_key=SecretStr("qualification-key"),
        api_secret=SecretStr("qualification-secret"),
        log_directory=Path("logs"),
        runtime_real_write_gate="OPEN",
        live_write_activation_id="activation-live-001",
    )
    try:
        with pytest.raises(
            ExecutorRuntimeError,
            match="RUNTIME_REAL_WRITE_GATE_CLOSED",
        ):
            runtime.build()
    finally:
        runtime.close()


def test_executor_entry_checks_live_gate_before_resolving_binance_secrets() -> None:
    source = (ROOT / "src" / "halpha" / "executor" / "__main__.py").read_text(
        encoding="utf-8"
    )
    runtime_entry = source.index("live_write =")
    secret_resolution = source.index("api_key = resolver.resolve(key_reference)")
    precheck = source.index("require_live_write_gate_precheck(", runtime_entry)
    open_check = source.index("require_live_write_gate_open(", precheck)
    assert runtime_entry < precheck < open_check < secret_resolution
    assert "current_product_build_id=product_build_id" in source[
        precheck:secret_resolution
    ]


def test_runtime_strategy_proposal_boundary_requires_the_activation_processor() -> None:
    proposal = SimpleNamespace(activation_id="activation-product-boundary")
    processor = SimpleNamespace(submit=lambda accepted: f"action:{accepted.activation_id}")
    runtime = object.__new__(ProductExecutorRuntime)
    runtime._proposal_processors = {proposal.activation_id: processor}

    assert runtime.submit_strategy_proposal(proposal) == (
        "action:activation-product-boundary"
    )

    runtime._proposal_processors = {}
    with pytest.raises(
        ExecutorRuntimeError,
        match="PRODUCT_PROPOSAL_PROCESSOR_NOT_READY",
    ):
        runtime.submit_strategy_proposal(proposal)


def test_runtime_stops_the_node_when_startup_times_out(monkeypatch) -> None:
    stopped = False

    class FakeNode:
        trader = SimpleNamespace(is_running=False)

        @staticmethod
        def is_running() -> bool:
            return False

        async def stop_async(self) -> None:
            nonlocal stopped
            stopped = True

    async def no_wait(_seconds: float) -> None:
        return None

    runtime = object.__new__(ProductExecutorRuntime)
    runtime._node = FakeNode()
    monkeypatch.setattr("halpha.executor.runtime.asyncio.sleep", no_wait)

    with pytest.raises(ExecutorRuntimeError, match="TRADING_NODE_START_TIMEOUT"):
        asyncio.run(runtime._startup_and_stop(lambda: None, None))

    assert stopped is True


def test_product_runtime_waits_for_every_strategy_history_warmup() -> None:
    adapters = {
        "activation-a": SimpleNamespace(live_history_ready=True),
        "activation-b": SimpleNamespace(live_history_ready=False),
    }

    class FakeLifecycle:
        @property
        def activation_ids(self):
            return tuple(adapters)

        @staticmethod
        def adapter_for_activation(activation_id):
            return adapters[activation_id]

    runtime = object.__new__(ProductExecutorRuntime)
    runtime._lifecycle = FakeLifecycle()

    async def exercise() -> None:
        runtime._loop = asyncio.get_running_loop()
        assert runtime.strategy_history_warmup_complete is False
        waiter = asyncio.create_task(
            runtime._wait_for_strategy_history_warmup(timeout_seconds=0.5)
        )
        await asyncio.sleep(0)
        adapters["activation-b"].live_history_ready = True
        await waiter
        assert runtime.strategy_history_warmup_complete is True

    asyncio.run(exercise())


def test_demo_runtime_discovers_ui_created_activation_without_restart() -> None:
    stop = threading.Event()
    activation_ids: list[str] = []
    sync_calls = 0
    warmup_calls = 0

    class FakeLifecycle:
        @property
        def activation_ids(self):
            return tuple(activation_ids)

    runtime = object.__new__(ProductExecutorRuntime)
    runtime._settings = SimpleNamespace(
        release=SimpleNamespace(profile="BINANCE_DEMO")
    )
    runtime._lifecycle = FakeLifecycle()
    runtime._responsibility_processors = {}

    def sync(_capability: object) -> None:
        nonlocal sync_calls
        sync_calls += 1
        activation_ids.append("activation-created-from-ui")
        stop.set()

    async def wait_for_warmup(*, timeout_seconds: float = 60.0) -> None:
        del timeout_seconds
        nonlocal warmup_calls
        warmup_calls += 1

    async def exercise() -> None:
        runtime._loop = asyncio.get_running_loop()
        runtime._restore_paused_adapters = sync
        runtime._wait_for_strategy_history_warmup = wait_for_warmup
        await runtime._wait_for_stop_and_sync_activations(
            stop.wait,
            object(),
            interval_seconds=0.001,
        )

    asyncio.run(exercise())

    assert sync_calls == 1
    assert activation_ids == ["activation-created-from-ui"]
    assert warmup_calls == 1


def test_live_runtime_periodically_advances_time_based_responsibilities() -> None:
    stop = threading.Event()
    responsibility_calls: list[str] = []
    direct_calls: list[str] = []

    class Responsibility:
        @staticmethod
        async def sync(activation_id: str) -> None:
            responsibility_calls.append(activation_id)
            stop.set()

    class Direct:
        @staticmethod
        def resume(activation_id: str) -> None:
            direct_calls.append(activation_id)

    runtime = object.__new__(ProductExecutorRuntime)
    runtime._settings = SimpleNamespace(
        release=SimpleNamespace(profile="BINANCE_LIVE_READ_ONLY")
    )
    runtime._lifecycle = SimpleNamespace(activation_ids=("activation-live",))
    runtime._responsibility_processors = {"activation-live": Responsibility()}
    runtime._direct_schedule_processors = {"activation-live": Direct()}
    runtime._runtime_event_sink = lambda *_args: None
    runtime._restore_paused_adapters = lambda _capability: (_ for _ in ()).throw(
        AssertionError("Live must not discover new activations")
    )

    async def exercise() -> None:
        runtime._loop = asyncio.get_running_loop()
        await runtime._wait_for_stop_and_sync_activations(
            stop.wait,
            object(),
            interval_seconds=0.001,
        )

    asyncio.run(exercise())

    assert responsibility_calls == ["activation-live"]
    assert direct_calls == ["activation-live"]


def test_demo_runtime_keeps_running_when_responsibility_sync_fails() -> None:
    stop = threading.Event()
    events: list[tuple[str, dict[str, object]]] = []

    class FailingProcessor:
        @staticmethod
        async def sync(activation_id: str) -> None:
            assert activation_id == "activation-demo"
            stop.set()
            raise RuntimeError("private diagnostic detail")

    runtime = object.__new__(ProductExecutorRuntime)
    runtime._settings = SimpleNamespace(
        release=SimpleNamespace(profile="BINANCE_DEMO")
    )
    runtime._lifecycle = SimpleNamespace(activation_ids=("activation-demo",))
    runtime._responsibility_processors = {
        "activation-demo": FailingProcessor()
    }
    runtime._runtime_event_sink = lambda event, fields: events.append((event, fields))
    runtime._restore_paused_adapters = lambda _capability: None
    runtime._wait_for_strategy_history_warmup = lambda: None

    async def exercise() -> None:
        runtime._loop = asyncio.get_running_loop()
        await runtime._wait_for_stop_and_sync_activations(
            stop.wait,
            object(),
            interval_seconds=0.001,
        )

    asyncio.run(exercise())

    assert events == [
        (
            "responsibility_sync_failed",
            {
                "activation_id": "activation-demo",
                "reason": "RuntimeError",
                "reason_code": "private diagnostic detail",
            },
        )
    ]


def test_demo_runtime_closes_an_expired_empty_activation_before_wiring(
    monkeypatch,
) -> None:
    state = {"closed": False}
    activation = SimpleNamespace(
        activation_id="activation-demo-expired",
        lifecycle=PlanLifecycle.RUNNING,
        entry_opportunity_consumed=False,
        rule_state={
            "deadlines": {"entry_valid_until": "2026-07-19T00:00:00+00:00"}
        },
    )

    class FakePlanning:
        def __init__(self, *_args, **_kwargs):
            pass

        @staticmethod
        def list_open_activations():
            return () if state["closed"] else (activation,)

    class FakeCoordinator:
        @staticmethod
        def expire_empty_entry_window(**values):
            assert values["activation_id"] == activation.activation_id
            state["closed"] = True

    monkeypatch.setattr(
        runtime_module,
        "PostgreSQLPlanningRepository",
        FakePlanning,
    )
    runtime = object.__new__(ProductExecutorRuntime)
    runtime._connection = object()
    runtime._lifecycle = SimpleNamespace(activation_ids=())
    runtime._settings = SimpleNamespace(
        release=SimpleNamespace(
            profile="BINANCE_DEMO",
            environment_id="demo-main",
        )
    )
    runtime._coordinator = FakeCoordinator()
    runtime._proposal_processors = {}
    runtime._responsibility_processors = {}

    runtime._restore_paused_adapters(object())

    assert state["closed"] is True


def test_live_runtime_rejects_an_activation_outside_the_authorized_set(
    monkeypatch,
) -> None:
    activation = SimpleNamespace(
        activation_id="activation-live-unauthorized",
        lifecycle=PlanLifecycle.RUNNING,
        entry_opportunity_consumed=False,
        rule_state={
            "deadlines": {"entry_valid_until": "2026-07-19T00:00:00+00:00"}
        },
    )

    class FakePlanning:
        def __init__(self, *_args, **_kwargs):
            pass

        @staticmethod
        def list_open_activations():
            return (activation,)

    monkeypatch.setattr(
        runtime_module,
        "PostgreSQLPlanningRepository",
        FakePlanning,
    )
    runtime = object.__new__(ProductExecutorRuntime)
    runtime._connection = object()
    runtime._lifecycle = SimpleNamespace(activation_ids=())
    runtime._settings = SimpleNamespace(
        release=SimpleNamespace(
            profile="BINANCE_LIVE_WRITE",
            environment_id="live-main",
        )
    )
    runtime._live_write_activation_id = "activation-live-authorized"
    runtime._coordinator = SimpleNamespace(
        expire_empty_entry_window=lambda **_values: pytest.fail(
            "unauthorized activation must not reach lifecycle mutation"
        )
    )
    runtime._proposal_processors = {}
    runtime._responsibility_processors = {}

    with pytest.raises(
        ExecutorRuntimeError,
        match="LIVE_WRITE_ACTIVATION_SET_MISMATCH",
    ):
        runtime._restore_paused_adapters(object())


def test_runtime_keeps_user_takeover_identity_for_read_only_reconciliation(
    monkeypatch,
) -> None:
    activation = SimpleNamespace(
        activation_id="activation-takeover",
        lifecycle=PlanLifecycle.USER_TAKEOVER,
        entry_opportunity_consumed=True,
        rule_state={},
    )
    inventory_reads: list[str] = []
    takeover_calls: list[str] = []

    class FakePlanning:
        def __init__(self, *_args, **_kwargs):
            pass

        @staticmethod
        def list_runtime_responsibility_activations():
            inventory_reads.append("runtime")
            return (activation,)

        @staticmethod
        def list_open_activations():
            raise AssertionError("takeover must use the responsibility inventory")

    monkeypatch.setattr(
        runtime_module,
        "PostgreSQLPlanningRepository",
        FakePlanning,
    )
    runtime = object.__new__(ProductExecutorRuntime)
    runtime._connection = object()
    runtime._lifecycle = SimpleNamespace(
        activation_ids=(activation.activation_id,)
    )
    runtime._settings = SimpleNamespace(
        release=SimpleNamespace(
            profile="BINANCE_DEMO",
            environment_id="demo-main",
        )
    )
    runtime._coordinator = SimpleNamespace(
        apply_persisted_user_takeover=lambda **values: takeover_calls.append(
            values["activation_id"]
        )
    )
    runtime._proposal_processors = {}
    runtime._responsibility_processors = {}

    runtime._restore_paused_adapters(object())

    assert inventory_reads == ["runtime", "runtime"]
    assert takeover_calls == [activation.activation_id]


def test_product_activation_handoff_defers_warmup_until_old_adapter_is_removed(
    monkeypatch,
) -> None:
    new_activation = SimpleNamespace(
        activation_id="activation-new",
        lifecycle=PlanLifecycle.RUNNING,
        entry_opportunity_consumed=False,
        rule_state={
            "deadlines": {"entry_valid_until": "2099-07-20T12:30:00+00:00"}
        },
    )
    version_reads: list[str] = []

    class FakePlanning:
        def __init__(self, *_args, **_kwargs):
            pass

        @staticmethod
        def list_open_activations():
            return (new_activation,)

        @staticmethod
        def get_version(plan_version_ref):
            version_reads.append(plan_version_ref)
            raise AssertionError("new warmup must wait for the next sync cycle")

    class FakeLifecycle:
        activation_ids = ("activation-old",)

        def __init__(self):
            self.removed: list[str] = []

        def stop_and_remove(self, activation_id):
            self.removed.append(activation_id)

    monkeypatch.setattr(
        runtime_module,
        "PostgreSQLPlanningRepository",
        FakePlanning,
    )
    lifecycle = FakeLifecycle()
    runtime = object.__new__(ProductExecutorRuntime)
    runtime._connection = object()
    runtime._lifecycle = lifecycle
    runtime._settings = SimpleNamespace(
        release=SimpleNamespace(
            profile="BINANCE_DEMO",
            environment_id="demo-main",
        )
    )
    runtime._coordinator = SimpleNamespace()
    runtime._proposal_processors = {}
    runtime._responsibility_processors = {}

    runtime._restore_paused_adapters(object())

    assert lifecycle.removed == ["activation-old"]
    assert version_reads == []


def test_product_open_activation_wires_warmup_proposal_and_event_path(
    monkeypatch,
) -> None:
    activation = SimpleNamespace(
        activation_id="activation-product-wiring",
        plan_version_ref="plan-version-product-wiring",
        instrument_ref="BTCUSDT-PERP",
        direction=Direction.LONG,
        entry_opportunity_consumed=False,
        lifecycle=SimpleNamespace(value="RUNNING"),
        run_state=SimpleNamespace(value="ACTIVE"),
        rule_state={
            "deadlines": {"entry_valid_until": "2026-07-19T00:00:00+00:00"}
        },
    )
    version = SimpleNamespace(
        valid_from=datetime(2026, 7, 18, tzinfo=UTC),
        valid_until=datetime(2026, 7, 19, tzinfo=UTC),
        strategy_basis=SimpleNamespace(
            normalized_parameters=OneShotParameters(
                direction=Direction.LONG
            ).model_dump(mode="json")
        ),
    )

    class FakePlanning:
        def __init__(self, *_args, **_kwargs):
            pass

        @staticmethod
        def list_open_activations():
            return (activation,)

        @staticmethod
        def get_version(_plan_version_ref):
            return version

        @staticmethod
        def get_activation(_activation_id):
            return activation

    class FakeLifecycle:
        adapter = None

        @property
        def activation_ids(self):
            if self.adapter is None:
                return ()
            return (self.adapter.activation_id,)

        def start(self, spec):
            self.adapter = spec.factory()
            return self.adapter

        def stop_and_remove(self, _activation_id):
            self.adapter = None

    class FakeCoordinator:
        @staticmethod
        def build_nautilus_event_normalizer(**_kwargs):
            return object()

        @staticmethod
        def handle_nautilus_order_event(*_args, **_kwargs):
            return None

    monkeypatch.setattr(
        runtime_module,
        "PostgreSQLPlanningRepository",
        FakePlanning,
    )
    lifecycle = FakeLifecycle()
    loop = asyncio.new_event_loop()
    runtime = object.__new__(ProductExecutorRuntime)
    runtime._connection = object()
    runtime._lifecycle = lifecycle
    runtime._settings = SimpleNamespace(
        release=SimpleNamespace(
            profile="BINANCE_DEMO",
            environment_id="demo-main",
            authority_class="DEMO_VALIDATION",
            account_id="demo-owner",
        )
    )
    runtime._api_key = SecretStr("qualification-key")
    runtime._api_secret = SecretStr("qualification-secret")
    runtime._proxy_url = None
    runtime._loop = loop
    observed_venues: list[Venue] = []

    class FakeCache:
        @staticmethod
        def instrument(_instrument_id):
            return object()

        @staticmethod
        def account_for_venue(venue):
            observed_venues.append(venue)
            return None

    runtime._node = SimpleNamespace(
        cache=FakeCache(),
        kernel=SimpleNamespace(clock=SimpleNamespace(timestamp_ns=lambda: 0)),
    )
    runtime._coordinator = FakeCoordinator()
    runtime._proposal_processors = {}
    runtime._responsibility_processors = {}
    runtime_events: list[tuple[str, dict[str, object]]] = []
    runtime._runtime_event_sink = lambda event, fields: runtime_events.append(
        (event, fields)
    )
    try:
        runtime._restore_paused_adapters(object())
        adapter = lifecycle.adapter
        assert isinstance(adapter, HalphaStrategyAdapter)
        assert isinstance(adapter._bar_evaluator, NautilusBarEntryEvaluator)
        assert adapter._bar_evaluator.sizing_provider(object()) is None
        assert observed_venues == [Venue("BINANCE")]
        assert adapter._bar_evaluator.warmup_complete is False
        assert adapter._live_history_warmup is True
        assert adapter._quote_event_sink is not None
        assert adapter._mark_price_event_sink is not None
        assert adapter._bar_event_sink is not None
        assert adapter._bar_failure_sink is not None
        adapter._bar_event_sink(
            SimpleNamespace(bar_type="BTCUSDT-PERP-1-MINUTE-LAST-EXTERNAL", ts_event=1)
        )
        adapter._bar_failure_sink(
            SimpleNamespace(bar_type="BTCUSDT-PERP-1-MINUTE-LAST-EXTERNAL"),
            RuntimeError("evaluation-failed"),
        )
        assert [event for event, _fields in runtime_events] == [
            "strategy_adapter_started",
            "entry_sizing_requested",
            "entry_sizing_unavailable",
            "strategy_bar_observed",
            "strategy_bar_failed",
        ]
        assert tuple(runtime._proposal_processors) == (
            "activation-product-wiring",
        )
        assert tuple(runtime._responsibility_processors) == (
            "activation-product-wiring",
        )
    finally:
        for processor in runtime._proposal_processors.values():
            processor.close()
        for processor in runtime._responsibility_processors.values():
            processor.close()
        loop.close()


def test_direct_activation_uses_execution_adapter_without_strategy_basis(
    monkeypatch,
) -> None:
    activation = SimpleNamespace(
        activation_id="activation-direct-wiring",
        plan_version_ref="plan-version-direct-wiring",
        decision_basis_ref=DIRECT_EXECUTION_REF,
        instrument_ref="BTCUSDT-PERP",
        direction=Direction.LONG,
        entry_opportunity_consumed=False,
        lifecycle=PlanLifecycle.RUNNING,
        run_state=SimpleNamespace(value="ACTIVE"),
        rule_state={
            "deadlines": {"entry_valid_until": "2099-07-19T00:00:00+00:00"}
        },
    )
    version_reads: list[str] = []

    class FakePlanning:
        def __init__(self, *_args, **_kwargs):
            pass

        @staticmethod
        def list_open_activations():
            return (activation,)

        @staticmethod
        def get_version(plan_version_ref):
            version_reads.append(plan_version_ref)
            raise AssertionError("direct execution must not read strategy basis")

    class FakeLifecycle:
        adapter = None

        @property
        def activation_ids(self):
            return () if self.adapter is None else (self.adapter.activation_id,)

        def start(self, spec):
            self.adapter = spec.factory()
            return self.adapter

    class FakeCoordinator:
        @staticmethod
        def build_nautilus_event_normalizer(**_kwargs):
            return object()

        @staticmethod
        def handle_nautilus_order_event(*_args, **_kwargs):
            return None

    monkeypatch.setattr(runtime_module, "PostgreSQLPlanningRepository", FakePlanning)
    lifecycle = FakeLifecycle()
    loop = asyncio.new_event_loop()
    runtime = object.__new__(ProductExecutorRuntime)
    runtime._connection = object()
    runtime._lifecycle = lifecycle
    runtime._settings = SimpleNamespace(
        release=SimpleNamespace(
            profile="BINANCE_DEMO",
            environment_id="demo-main",
            authority_class="DEMO_VALIDATION",
            account_id="demo-owner",
        )
    )
    runtime._api_key = SecretStr("qualification-key")
    runtime._api_secret = SecretStr("qualification-secret")
    runtime._proxy_url = None
    runtime._loop = loop
    runtime._node = SimpleNamespace(cache=SimpleNamespace())
    runtime._coordinator = FakeCoordinator()
    runtime._proposal_processors = {}
    runtime._direct_schedule_processors = {}
    runtime._responsibility_processors = {}
    runtime._recovery_complete = False
    runtime._runtime_event_sink = None
    try:
        runtime._restore_paused_adapters(object())

        adapter = lifecycle.adapter
        assert isinstance(adapter, HalphaStrategyAdapter)
        assert adapter._logic is None
        assert adapter._state_provider is None
        assert adapter._proposal_sink is None
        assert adapter._bar_evaluator is None
        assert adapter.live_history_ready is True
        assert version_reads == []
        assert tuple(runtime._proposal_processors) == ()
        assert tuple(runtime._direct_schedule_processors) == (
            "activation-direct-wiring",
        )
        assert tuple(runtime._responsibility_processors) == (
            "activation-direct-wiring",
        )
    finally:
        for processor in runtime._direct_schedule_processors.values():
            processor.close()
        for processor in runtime._responsibility_processors.values():
            processor.close()
        loop.close()
