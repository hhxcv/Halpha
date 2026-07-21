"""One product TradingNode composition shared by Demo and Live profiles."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from nautilus_trader.adapters.binance import (
    BINANCE,
    BinanceAccountType,
    BinanceDataClientConfig,
    BinanceExecClientConfig,
    BinanceInstrumentProviderConfig,
    BinanceLiveDataClientFactory,
    BinanceLiveExecClientFactory,
)
from nautilus_trader.adapters.binance.common.enums import BinanceEnvironment
from nautilus_trader.common import Environment
from nautilus_trader.common.config import LoggingConfig
from nautilus_trader.live.config import (
    ControllerConfig,
    LiveDataEngineConfig,
    LiveExecEngineConfig,
    RoutingConfig,
    TradingNodeConfig,
)
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.identifiers import ClientOrderId, InstrumentId, TraderId
from nautilus_trader.trading.config import ImportableControllerConfig
from nautilus_trader.trading.controller import Controller
from pydantic import SecretStr

from halpha.capital.models import AuthorityClass, EnvironmentKind
from halpha.configuration import ExecutorSettingsView
from halpha.domain_values import canonical_decimal
from halpha.planning.bar_evaluation import (
    EntrySizingSnapshot,
    NautilusBarEntryEvaluator,
)
from halpha.planning.adapter import (
    ActivationAdapterLifecycle,
    ActivationAdapterSpec,
    HalphaStrategyAdapter,
)
from halpha.planning.models import PlanLifecycle, RunState
from halpha.planning.registry import OneShotParameters
from halpha.planning.repository import PostgreSQLPlanningRepository
from halpha.planning.strategies.one_shot import (
    ActivationStrategyState,
    InstrumentQuantityRules,
    OneShotDonchianAtrLogic,
    StrategyProposal,
)
from halpha.product_build import (
    EXECUTOR_STARTING_APPLICATION_NAME,
    executor_ready_application_name,
)
from halpha.venue_integration.gateway import PersistedActionGate
from halpha.venue_integration.nautilus_client import NautilusVenueExecutionClient
from halpha.venue_integration.repository import PostgreSQLExecutionActionRepository

from .coordinator import HalphaCoordinator
from .forward_observation import ForwardObservationSpec
from .product_entry import (
    LiveEntryFactTracker,
    ProductPreSubmitFactProvider,
    ProductPreSubmitRejected,
    ProductProposalBoundary,
    build_live_entry_sizing_snapshot,
)
from .responsibilities import ProductResponsibilityBoundary


_PROFILE_SPEC = {
    "BINANCE_DEMO": (
        BinanceEnvironment.DEMO,
        ("BTCUSDT-PERP.BINANCE", "ETHUSDT-PERP.BINANCE"),
    ),
    "BINANCE_LIVE_READ_ONLY": (
        BinanceEnvironment.LIVE,
        ("BTCUSDT-PERP.BINANCE",),
    ),
    "BINANCE_LIVE_WRITE": (
        BinanceEnvironment.LIVE,
        ("BTCUSDT-PERP.BINANCE",),
    ),
}


class ExecutorRuntimeError(RuntimeError):
    """Sanitized fail-closed product runtime failure."""


def _activation_entry_deadline(activation: object) -> datetime:
    rule_state = getattr(activation, "rule_state", {})
    deadlines = rule_state.get("deadlines", {}) if isinstance(rule_state, dict) else {}
    value = deadlines.get("entry_valid_until") if isinstance(deadlines, dict) else None
    if not isinstance(value, str):
        raise ExecutorRuntimeError("ENTRY_DEADLINE_MISSING")
    try:
        deadline = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ExecutorRuntimeError("ENTRY_DEADLINE_INVALID") from None
    if deadline.tzinfo is None:
        raise ExecutorRuntimeError("ENTRY_DEADLINE_INVALID")
    return deadline.astimezone(UTC)


class HalphaRuntimeController(Controller):
    """The unique product Controller used for activation adapter lifecycle."""

    def __init__(self, trader: Any, config: ControllerConfig | None = None) -> None:
        super().__init__(trader=trader, config=config)


def _connect_product_database(
    connector: Callable[..., Any],
    *,
    database_name: str,
    password: str,
    application_name: str | None = None,
) -> Any:
    """Keep reads outside explicit units from opening a hidden outer transaction."""

    values: dict[str, Any] = {
        "host": "127.0.0.1",
        "port": 5432,
        "dbname": database_name,
        "user": f"{database_name}_executor",
        "password": password,
        "connect_timeout": 2,
        "autocommit": True,
    }
    if application_name is not None:
        values["application_name"] = application_name
    return connector(
        **values,
    )


def _cached_leaves_quantity(cache: Any, client_order_id: str) -> str | None:
    """Read the framework-owned order projection without inventing a terminal state."""

    try:
        order = cache.order(ClientOrderId(client_order_id))
    except (TypeError, ValueError):
        return None
    if order is None:
        return None
    leaves_quantity = getattr(order, "leaves_qty", None)
    return str(leaves_quantity) if leaves_quantity is not None else None


def build_binance_client_configs(
    profile: str,
    *,
    api_key: SecretStr | None,
    api_secret: SecretStr | None,
    proxy_url: str | None = None,
) -> tuple[
    BinanceInstrumentProviderConfig,
    BinanceDataClientConfig,
    BinanceExecClientConfig | None,
]:
    """Build the sole environment-qualified Binance client topology."""

    try:
        venue_environment, raw_ids = _PROFILE_SPEC[profile]
    except KeyError:
        raise ExecutorRuntimeError("EXECUTION_PROFILE_MISMATCH") from None
    instrument_ids = frozenset(InstrumentId.from_str(value) for value in raw_ids)
    read_only = profile == "BINANCE_LIVE_READ_ONLY"
    if read_only:
        if api_key is not None or api_secret is not None:
            raise ExecutorRuntimeError("READ_ONLY_BINANCE_CREDENTIAL_FORBIDDEN")
    elif api_key is None or api_secret is None:
        raise ExecutorRuntimeError("BINANCE_CREDENTIAL_REQUIRED")
    provider = BinanceInstrumentProviderConfig(
        load_all=False,
        load_ids=instrument_ids,
        query_commission_rates=not read_only,
    )
    key = api_key.get_secret_value() if api_key is not None else None
    secret = api_secret.get_secret_value() if api_secret is not None else None
    routing = RoutingConfig(default=True, venues=frozenset({BINANCE}))
    data = BinanceDataClientConfig(
        api_key=key,
        api_secret=secret,
        account_type=BinanceAccountType.USDT_FUTURES,
        environment=venue_environment,
        instrument_provider=provider,
        routing=routing,
        proxy_url=proxy_url,
    )
    execution = None
    if not read_only:
        execution = BinanceExecClientConfig(
            api_key=key,
            api_secret=secret,
            account_type=BinanceAccountType.USDT_FUTURES,
            environment=venue_environment,
            instrument_provider=provider,
            routing=routing,
            proxy_url=proxy_url,
            use_reduce_only=True,
            use_position_ids=True,
            use_trade_lite=False,
            treat_expired_as_canceled=False,
            recv_window_ms=5000,
            max_retries=None,
            futures_leverages=None,
            futures_margin_types=None,
        )
    return provider, data, execution


def build_product_node_config(
    profile: str,
    *,
    api_key: SecretStr | None,
    api_secret: SecretStr | None,
    log_directory: Path,
    proxy_url: str | None = None,
) -> tuple[
    TradingNodeConfig,
    BinanceInstrumentProviderConfig,
    BinanceDataClientConfig,
    BinanceExecClientConfig | None,
]:
    provider, data, execution = build_binance_client_configs(
        profile,
        api_key=api_key,
        api_secret=api_secret,
        proxy_url=proxy_url,
    )
    instrument_ids = list(provider.load_ids or ())
    read_only = profile == "BINANCE_LIVE_READ_ONLY"
    exec_engine = (
        LiveExecEngineConfig(
            reconciliation=False,
            reconciliation_instrument_ids=None,
            inflight_check_interval_ms=0,
            open_check_interval_secs=None,
            position_check_interval_secs=None,
            generate_missing_orders=False,
            filter_unclaimed_external_orders=True,
            filter_position_reports=True,
        )
        if read_only
        else LiveExecEngineConfig(
            reconciliation=True,
            reconciliation_lookback_mins=None,
            reconciliation_instrument_ids=instrument_ids,
            reconciliation_startup_delay_secs=10.0,
            inflight_check_interval_ms=2_000,
            inflight_check_threshold_ms=5000,
            inflight_check_retries=5,
            open_check_interval_secs=10.0,
            open_check_open_only=True,
            open_check_lookback_mins=60,
            open_check_threshold_ms=5000,
            open_check_missing_retries=5,
            position_check_interval_secs=60.0,
            position_check_lookback_mins=60,
            position_check_retries=3,
            generate_missing_orders=True,
            filter_unclaimed_external_orders=False,
            filter_position_reports=False,
        )
    )
    config = TradingNodeConfig(
        environment=Environment.LIVE,
        trader_id=TraderId("HALPHA-OWNER-001"),
        cache=None,
        message_bus=None,
        emulator=None,
        streaming=None,
        catalogs=[],
        load_state=False,
        save_state=False,
        timeout_connection=30.0,
        timeout_disconnection=15.0,
        logging=LoggingConfig(
            log_level="INFO",
            log_level_file="INFO",
            log_directory=str(log_directory),
            log_file_name=f"halpha-{profile.lower().replace('_', '-')}",
            log_file_format="JSON",
            log_file_max_size=104857600,
            log_file_max_backup_count=5,
            log_colors=False,
            print_config=False,
            clear_log_file=False,
        ),
        data_engine=LiveDataEngineConfig(
            time_bars_interval_type="left-open",
            time_bars_timestamp_on_close=True,
            time_bars_skip_first_non_full_bar=True,
            time_bars_build_with_no_updates=False,
            validate_data_sequence=True,
        ),
        exec_engine=exec_engine,
        data_clients={BINANCE: data},
        exec_clients={} if execution is None else {BINANCE: execution},
        controller=ImportableControllerConfig(
            controller_path="halpha.executor.runtime:HalphaRuntimeController",
            config_path="nautilus_trader.live.config:ControllerConfig",
            config={},
        ),
    )
    return config, provider, data, execution


class ProductExecutorRuntime:
    """Own the one DB connection, TradingNode, controller, gate and coordinator."""

    def __init__(
        self,
        *,
        settings: ExecutorSettingsView,
        database_password: SecretStr | None,
        api_key: SecretStr | None,
        api_secret: SecretStr | None,
        log_directory: Path,
        proxy_url: str | None = None,
        forward_observation_spec: ForwardObservationSpec | None = None,
        observation_proposal_sink: Callable[[StrategyProposal], None] | None = None,
        observation_bar_sink: Callable[[object], None] | None = None,
        observation_quote_sink: Callable[[object], None] | None = None,
        observation_mark_price_sink: Callable[[object], None] | None = None,
        connector: Callable[..., Any] = psycopg.connect,
        node_factory: Callable[..., TradingNode] = TradingNode,
        loop: asyncio.AbstractEventLoop | None = None,
        runtime_real_write_gate: str = "CLOSED",
        live_write_activation_id: str | None = None,
        live_write_submission_guard: Callable[[str], None] | None = None,
        runtime_event_sink: Callable[[str, dict[str, object]], None] | None = None,
    ) -> None:
        self._settings = settings
        self._database_password = database_password
        self._api_key = api_key
        self._api_secret = api_secret
        self._log_directory = log_directory
        self._proxy_url = proxy_url
        self._forward_observation_spec = forward_observation_spec
        self._observation_proposal_sink = observation_proposal_sink
        self._observation_bar_sink = observation_bar_sink
        self._observation_quote_sink = observation_quote_sink
        self._observation_mark_price_sink = observation_mark_price_sink
        self._connector = connector
        self._node_factory = node_factory
        self._loop = loop or asyncio.new_event_loop()
        self._owns_loop = loop is None
        self._runtime_real_write_gate = runtime_real_write_gate
        self._live_write_activation_id = live_write_activation_id
        self._live_write_submission_guard = live_write_submission_guard
        self._runtime_event_sink = runtime_event_sink
        self._connection: Any | None = None
        self._node: TradingNode | None = None
        self._lifecycle: ActivationAdapterLifecycle | None = None
        self._coordinator: HalphaCoordinator | None = None
        self._capability: object | None = None
        self._proposal_processors: dict[str, ProductProposalBoundary] = {}
        self._responsibility_processors: dict[str, ProductResponsibilityBoundary] = {}
        self._recovery_complete = False
        self._recovered_action_count = 0

    def _record_runtime_event(self, event: str, **fields: object) -> None:
        sink = getattr(self, "_runtime_event_sink", None)
        if sink is not None:
            sink(event, fields)

    @property
    def node(self) -> TradingNode:
        if self._node is None:
            raise ExecutorRuntimeError("PRODUCT_RUNTIME_NOT_BUILT")
        return self._node

    @property
    def coordinator(self) -> HalphaCoordinator:
        if self._coordinator is None:
            raise ExecutorRuntimeError("PRODUCT_RUNTIME_NOT_BUILT")
        return self._coordinator

    def submit_strategy_proposal(self, proposal: StrategyProposal) -> str:
        """Enter the production EXE boundary used by the adapter proposal sink."""

        processor = self._proposal_processors.get(proposal.activation_id)
        if processor is None:
            raise ExecutorRuntimeError("PRODUCT_PROPOSAL_PROCESSOR_NOT_READY")
        return processor.submit(proposal)

    @property
    def recovery_complete(self) -> bool:
        return self._recovery_complete

    @property
    def recovered_action_count(self) -> int:
        return self._recovered_action_count

    @property
    def strategy_history_warmup_complete(self) -> bool:
        lifecycle = self._lifecycle
        if lifecycle is None:
            return False
        return all(
            lifecycle.adapter_for_activation(activation_id).live_history_ready
            for activation_id in lifecycle.activation_ids
        )

    async def _wait_for_strategy_history_warmup(
        self,
        *,
        timeout_seconds: float = 60.0,
    ) -> None:
        deadline = self._loop.time() + timeout_seconds
        while not self.strategy_history_warmup_complete:
            if self._loop.time() >= deadline:
                raise ExecutorRuntimeError("LIVE_HISTORY_WARMUP_TIMEOUT")
            await asyncio.sleep(0.05)

    def build(self) -> None:
        if self._node is not None:
            raise ExecutorRuntimeError("PRODUCT_RUNTIME_ALREADY_BUILT")
        release = self._settings.release
        read_only = release.profile == "BINANCE_LIVE_READ_ONLY"
        if release.profile == "BINANCE_LIVE_WRITE" and (
            self._runtime_real_write_gate != "OPEN"
            or self._live_write_activation_id is None
            or self._live_write_submission_guard is None
        ):
            raise ExecutorRuntimeError("RUNTIME_REAL_WRITE_GATE_CLOSED")
        database_password = self._database_password
        if read_only:
            if database_password is not None:
                raise ExecutorRuntimeError("READ_ONLY_DATABASE_CREDENTIAL_FORBIDDEN")
            if self._api_key is not None or self._api_secret is not None:
                raise ExecutorRuntimeError("READ_ONLY_BINANCE_CREDENTIAL_FORBIDDEN")
            if self._forward_observation_spec is None:
                raise ExecutorRuntimeError("READ_ONLY_OBSERVATION_SPEC_REQUIRED")
            if self._forward_observation_spec.profile != release.profile:
                raise ExecutorRuntimeError("READ_ONLY_OBSERVATION_PROFILE_MISMATCH")
        elif database_password is None:
            raise ExecutorRuntimeError("PRODUCT_DATABASE_CREDENTIAL_REQUIRED")
        try:
            config, provider, data, execution = build_product_node_config(
                release.profile,
                api_key=self._api_key,
                api_secret=self._api_secret,
                log_directory=self._log_directory,
                proxy_url=self._proxy_url,
            )
            if data.instrument_provider is not provider:
                raise ExecutorRuntimeError("BINANCE_PROVIDER_IDENTITY_MISMATCH")
            if read_only and execution is not None:
                raise ExecutorRuntimeError("READ_ONLY_EXECUTION_CLIENT_FORBIDDEN")
            if not read_only and (
                execution is None or execution.instrument_provider is not provider
            ):
                raise ExecutorRuntimeError("BINANCE_PROVIDER_IDENTITY_MISMATCH")
            connection = None
            if not read_only:
                if database_password is None:
                    raise ExecutorRuntimeError("PRODUCT_DATABASE_CREDENTIAL_REQUIRED")
                connection = _connect_product_database(
                    self._connector,
                    database_name=release.database_name,
                    password=database_password.get_secret_value(),
                    application_name=EXECUTOR_STARTING_APPLICATION_NAME,
                )
                self._connection = connection
            node = self._node_factory(config=config, loop=self._loop)
            node.add_data_client_factory(BINANCE, BinanceLiveDataClientFactory)
            if execution is not None:
                node.add_exec_client_factory(BINANCE, BinanceLiveExecClientFactory)
            node.build()
            controllers = [
                actor
                for actor in node.trader.actors()
                if isinstance(actor, HalphaRuntimeController)
            ]
            if len(controllers) != 1:
                raise ExecutorRuntimeError("CONTROLLER_COUNT_MISMATCH")
            lifecycle = ActivationAdapterLifecycle(controllers[0])
            self._node = node
            self._lifecycle = lifecycle
            if read_only:
                return
            if connection is None:
                raise ExecutorRuntimeError("PRODUCT_DATABASE_CREDENTIAL_REQUIRED")
            capability = object()
            self._capability = capability
            action_repository = PostgreSQLExecutionActionRepository(
                connection,
                release.environment_id,
            )
            client = NautilusVenueExecutionClient(
                lifecycle.adapter_for_activation,
                capability,
            )
            gate = PersistedActionGate(
                action_repository,
                client,
                environment_id=release.environment_id,
                execution_profile_ref=release.profile,
                account_ref=release.account_id,
            )
            environment_kind = "DEMO" if release.profile == "BINANCE_DEMO" else "LIVE"
            coordinator = HalphaCoordinator(
                connection,
                gate,
                environment_id=release.environment_id,
                environment_kind=environment_kind,
                authority_class=release.authority_class,
                execution_profile_ref=release.profile,
                account_ref=release.account_id,
                runtime_real_write_gate=self._runtime_real_write_gate,
                live_write_activation_id=self._live_write_activation_id,
                live_write_submission_guard=self._live_write_submission_guard,
            )
            self._coordinator = coordinator
        except ExecutorRuntimeError:
            self.close()
            raise
        except Exception as exc:
            self.close()
            raise ExecutorRuntimeError(
                f"PRODUCT_RUNTIME_BUILD_FAILED type={type(exc).__name__}"
            ) from None

    def publish_ready_product_build(self, product_build_id: str) -> None:
        """Publish framework readiness through the Executor's existing DB session."""

        if self._settings.release.profile == "BINANCE_LIVE_READ_ONLY":
            return
        if self._connection is None:
            raise ExecutorRuntimeError("PRODUCT_DATABASE_CONNECTION_MISSING")
        try:
            self._connection.execute(
                "SELECT set_config('application_name', %s, false)",
                (executor_ready_application_name(product_build_id),),
            )
        except Exception:
            raise ExecutorRuntimeError("EXECUTOR_READINESS_PUBLISH_FAILED") from None

    @staticmethod
    def _decimal_text(value: object | None) -> str | None:
        if value is None:
            return None
        if hasattr(value, "as_decimal"):
            value = value.as_decimal()
        try:
            return canonical_decimal(value)
        except Exception:
            return None

    def _read_only_sizing_snapshot(self, _bar: object) -> EntrySizingSnapshot | None:
        spec = self._forward_observation_spec
        if spec is None:
            raise ExecutorRuntimeError("READ_ONLY_OBSERVATION_SPEC_REQUIRED")
        instrument_id = InstrumentId.from_str(f"{spec.instrument_ref}.BINANCE")
        instrument = self.node.cache.instrument(instrument_id)
        quote = self.node.cache.quote_tick(instrument_id)
        mark = self.node.cache.mark_price(instrument_id)
        if instrument is None or quote is None or mark is None:
            return None
        direction = spec.parameters.direction.value
        reference_price = quote.ask_price if direction == "LONG" else quote.bid_price
        values = {
            "step_size": self._decimal_text(instrument.size_increment),
            "price_tick_size": self._decimal_text(instrument.price_increment),
            "min_quantity": self._decimal_text(instrument.min_quantity),
            "max_market_quantity": self._decimal_text(instrument.max_quantity),
            "min_notional": self._decimal_text(instrument.min_notional),
            "taker_fee_rate": self._decimal_text(instrument.taker_fee),
        }
        if any(value is None for value in values.values()):
            return None
        return EntrySizingSnapshot(
            reference_price=str(reference_price),
            reference_source=f"LIVE_TOP_OF_BOOK_{'ASK' if direction == 'LONG' else 'BID'}",
            max_allowed_loss=spec.max_allowed_loss,
            max_notional=spec.max_notional,
            max_margin=spec.max_margin,
            effective_leverage=spec.effective_leverage,
            taker_fee_rate=str(values["taker_fee_rate"]),
            rules=InstrumentQuantityRules(
                step_size=str(values["step_size"]),
                price_tick_size=str(values["price_tick_size"]),
                min_quantity=str(values["min_quantity"]),
                max_market_quantity=str(values["max_market_quantity"]),
                min_notional=str(values["min_notional"]),
            ),
        )

    def _start_read_only_adapter(self) -> None:
        if self._lifecycle is None or self._forward_observation_spec is None:
            raise ExecutorRuntimeError("PRODUCT_RUNTIME_NOT_BUILT")
        spec = self._forward_observation_spec
        proposal_sink = self._observation_proposal_sink or (lambda _proposal: None)
        evaluator = NautilusBarEntryEvaluator(
            activation_id=spec.activation_id,
            instrument_ref=spec.instrument_ref,
            parameters=spec.parameters,
            decision_not_before=spec.starts_at,
            valid_until=spec.entry_valid_until,
            sizing_provider=self._read_only_sizing_snapshot,
            requires_live_warmup=True,
        )
        self._lifecycle.start(
            ActivationAdapterSpec(
                activation_id=spec.activation_id,
                factory=lambda: HalphaStrategyAdapter(
                    activation_id=spec.activation_id,
                    logic=OneShotDonchianAtrLogic(spec.parameters),
                    state_provider=lambda: ActivationStrategyState(),
                    proposal_sink=proposal_sink,
                    instrument_ref=spec.instrument_ref,
                    persisted_action_capability=None,
                    execution_event_sink=None,
                    bar_evaluator=evaluator,
                    bar_event_sink=self._observation_bar_sink,
                    quote_event_sink=self._observation_quote_sink,
                    mark_price_event_sink=self._observation_mark_price_sink,
                    live_history_warmup=True,
                ),
            )
        )

    def _restore_paused_adapters(self, capability: object) -> None:
        if self._connection is None or self._lifecycle is None:
            raise ExecutorRuntimeError("PRODUCT_RUNTIME_NOT_BUILT")
        planning = PostgreSQLPlanningRepository(
            self._connection,
            self._settings.release.environment_id,
        )
        activations = planning.list_open_activations()
        if self._settings.release.profile == "BINANCE_DEMO":
            observed_at = datetime.now(UTC)
            for activation in activations:
                rule_state = getattr(activation, "rule_state", {})
                deadlines = (
                    rule_state.get("deadlines", {})
                    if isinstance(rule_state, dict)
                    else {}
                )
                deadline_value = (
                    deadlines.get("entry_valid_until")
                    if isinstance(deadlines, dict)
                    else None
                )
                if (
                    activation.lifecycle is not PlanLifecycle.RUNNING
                    or activation.entry_opportunity_consumed
                    or not isinstance(deadline_value, str)
                ):
                    continue
                try:
                    deadline = datetime.fromisoformat(
                        deadline_value.replace("Z", "+00:00")
                    )
                except ValueError:
                    raise ExecutorRuntimeError("ENTRY_DEADLINE_INVALID") from None
                if observed_at >= deadline:
                    self.coordinator.expire_empty_entry_window(
                        activation_id=activation.activation_id,
                        observed_at=observed_at,
                    )
            activations = planning.list_open_activations()
        if self._settings.release.profile == "BINANCE_LIVE_WRITE":
            authorized_activation_id = self._live_write_activation_id
            if (
                authorized_activation_id is None
                or len(activations) != 1
                or activations[0].activation_id != authorized_activation_id
            ):
                raise ExecutorRuntimeError("LIVE_WRITE_ACTIVATION_SET_MISMATCH")
        open_activation_ids = {activation.activation_id for activation in activations}
        removed_stale_adapter = False
        for activation_id in set(self._lifecycle.activation_ids) - open_activation_ids:
            self._lifecycle.stop_and_remove(activation_id)
            removed_stale_adapter = True
            proposal_processor = self._proposal_processors.pop(activation_id, None)
            if proposal_processor is not None:
                proposal_processor.close()
            responsibility_processor = self._responsibility_processors.pop(
                activation_id,
                None,
            )
            if responsibility_processor is not None:
                responsibility_processor.close()
        if removed_stale_adapter:
            # Nautilus requires no active subscription for the same underlying
            # market while aggregated history is requested. Give the controller
            # one sync cycle to finish the old adapter's unsubscriptions before
            # starting the replacement activation and its warmup request.
            return
        for activation in activations:
            if activation.activation_id in self._lifecycle.activation_ids:
                continue
            version = planning.get_version(activation.plan_version_ref)
            parameters = OneShotParameters.model_validate(
                version.strategy_basis.normalized_parameters
            )
            if (
                parameters.demo_immediate_entry
                and self._settings.release.profile != "BINANCE_DEMO"
            ):
                raise ExecutorRuntimeError("DEMO_IMMEDIATE_ENTRY_REQUIRES_DEMO")
            entry_valid_until = _activation_entry_deadline(activation)
            tracker = LiveEntryFactTracker()
            api_key = self._api_key
            api_secret = self._api_secret
            if api_key is None or api_secret is None:
                raise ExecutorRuntimeError("BINANCE_CREDENTIAL_REQUIRED")
            fact_provider = ProductPreSubmitFactProvider(
                node=self.node,
                profile=self._settings.release.profile,
                api_key=api_key,
                api_secret=api_secret,
                proxy_url=self._proxy_url,
            )
            environment_kind = (
                EnvironmentKind.DEMO
                if self._settings.release.profile == "BINANCE_DEMO"
                else EnvironmentKind.LIVE
            )
            processor = ProductProposalBoundary(
                loop=self._loop,
                coordinator=self.coordinator,
                fact_provider=fact_provider,
                environment_id=self._settings.release.environment_id,
                environment_kind=environment_kind,
                authority_class=AuthorityClass(self._settings.release.authority_class),
                account_ref=self._settings.release.account_id,
            )
            self._proposal_processors[activation.activation_id] = processor
            responsibility = ProductResponsibilityBoundary(
                loop=self._loop,
                coordinator=self.coordinator,
                fact_provider=fact_provider.risk_reduction_facts,
                entry_order_absence_provider=(
                    fact_provider.entry_order_is_definitely_absent
                ),
                environment_id=self._settings.release.environment_id,
            )
            self._responsibility_processors[activation.activation_id] = responsibility

            def state_provider(
                activation_id: str = activation.activation_id,
            ) -> ActivationStrategyState:
                current = planning.get_activation(activation_id)
                entry_responsibility_open = (
                    self.coordinator.has_open_entry_responsibility(activation_id)
                )
                new_risk_allowed = self.coordinator.new_risk_allowed(activation_id)
                return ActivationStrategyState(
                    entry_opportunity_consumed=(
                        current.entry_opportunity_consumed
                        or entry_responsibility_open
                    ),
                    lifecycle=current.lifecycle.value,
                    run_state=current.run_state.value,
                    new_risk_allowed=(
                        current.lifecycle is PlanLifecycle.RUNNING
                        and current.run_state is RunState.ACTIVE
                        and new_risk_allowed
                    ),
                )

            def proposal_sink(
                proposal: StrategyProposal,
            ) -> None:
                self._record_runtime_event(
                    "strategy_proposal_observed",
                    activation_id=proposal.activation_id,
                    source_identity=proposal.source_identity,
                )
                self.submit_strategy_proposal(proposal)

            def sizing_provider(
                _bar: object,
                *,
                activation_id: str = activation.activation_id,
                instrument_ref: str = activation.instrument_ref,
                direction=activation.direction,
                used_tracker: LiveEntryFactTracker = tracker,
            ) -> EntrySizingSnapshot | None:
                self._record_runtime_event(
                    "entry_sizing_requested",
                    activation_id=activation_id,
                )
                instrument_id = f"{instrument_ref}.BINANCE"
                nautilus_instrument_id = InstrumentId.from_str(instrument_id)
                instrument = self.node.cache.instrument(nautilus_instrument_id)
                account = self.node.cache.account_for_venue(
                    nautilus_instrument_id.venue
                )
                if instrument is None:
                    self._record_runtime_event(
                        "entry_sizing_unavailable",
                        activation_id=activation_id,
                        reason_code="INSTRUMENT_CACHE_MISSING",
                    )
                    return None
                if account is None:
                    self._record_runtime_event(
                        "entry_sizing_unavailable",
                        activation_id=activation_id,
                        reason_code="ACCOUNT_CACHE_MISSING",
                    )
                    return None
                try:
                    boundary = self.coordinator.get_entry_sizing_boundary(activation_id)
                    snapshot = build_live_entry_sizing_snapshot(
                        instrument_id=instrument_id,
                        direction=direction,
                        cutoff_ns=self.node.kernel.clock.timestamp_ns(),
                        tracker=used_tracker,
                        instrument=instrument,
                        account=account,
                        boundary=boundary,
                    )
                    self._record_runtime_event(
                        "entry_sizing_ready",
                        activation_id=activation_id,
                    )
                    return snapshot
                except ProductPreSubmitRejected as exc:
                    self._record_runtime_event(
                        "entry_sizing_unavailable",
                        activation_id=activation_id,
                        reason_code=exc.reason_code,
                    )
                    return None

            evaluator = NautilusBarEntryEvaluator(
                activation_id=activation.activation_id,
                instrument_ref=activation.instrument_ref,
                parameters=parameters,
                decision_not_before=version.valid_from,
                valid_until=entry_valid_until,
                sizing_provider=sizing_provider,
                requires_live_warmup=True,
            )

            normalizer = self.coordinator.build_nautilus_event_normalizer(
                leaves_quantity_for_client_order_id=lambda client_order_id: (
                    _cached_leaves_quantity(self.node.cache, client_order_id)
                ),
            )

            def event_sink(
                event: object,
                used_normalizer=normalizer,
                used_responsibility: ProductResponsibilityBoundary = responsibility,
                activation_id: str = activation.activation_id,
            ) -> None:
                client_order_id = getattr(event, "client_order_id", None)
                self._record_runtime_event(
                    "execution_event_observed",
                    activation_id=activation_id,
                    event_type=type(event).__name__,
                    client_order_id=(
                        str(client_order_id) if client_order_id is not None else None
                    ),
                )
                normalized = self.coordinator.handle_nautilus_order_event(
                    used_normalizer,
                    event,
                    observed_at=datetime.now(UTC),
                )
                used_responsibility.submit_event(normalized)

            def bar_event_sink(
                bar: object,
                *,
                activation_id: str = activation.activation_id,
            ) -> None:
                self._record_runtime_event(
                    "strategy_bar_observed",
                    activation_id=activation_id,
                    bar_type=str(getattr(bar, "bar_type", "UNKNOWN")),
                    ts_event=int(getattr(bar, "ts_event", 0)),
                )

            def bar_failure_sink(
                bar: object,
                exception: Exception,
                *,
                activation_id: str = activation.activation_id,
            ) -> None:
                self._record_runtime_event(
                    "strategy_bar_failed",
                    activation_id=activation_id,
                    bar_type=str(getattr(bar, "bar_type", "UNKNOWN")),
                    exception_type=type(exception).__name__,
                    reason_code=str(exception),
                )

            def history_warmup_failure_sink(
                stage: str,
                item: object | None,
                exception: Exception,
                *,
                activation_id: str = activation.activation_id,
            ) -> None:
                self._record_runtime_event(
                    "strategy_history_warmup_failed",
                    activation_id=activation_id,
                    stage=stage,
                    item_type=type(item).__name__ if item is not None else "NONE",
                    bar_type=str(getattr(item, "bar_type", "UNKNOWN")),
                    exception_type=type(exception).__name__,
                    reason_code=str(exception),
                )

            def adapter_factory(
                activation_id: str = activation.activation_id,
                instrument_ref: str = activation.instrument_ref,
                logic: OneShotDonchianAtrLogic = OneShotDonchianAtrLogic(parameters),
                used_state_provider=state_provider,
                used_proposal_sink=proposal_sink,
                used_event_sink=event_sink,
                used_evaluator: NautilusBarEntryEvaluator = evaluator,
                used_tracker: LiveEntryFactTracker = tracker,
            ) -> HalphaStrategyAdapter:
                return HalphaStrategyAdapter(
                    activation_id=activation_id,
                    logic=logic,
                    state_provider=used_state_provider,
                    proposal_sink=used_proposal_sink,
                    instrument_ref=instrument_ref,
                    persisted_action_capability=capability,
                    execution_event_sink=used_event_sink,
                    bar_evaluator=used_evaluator,
                    bar_event_sink=bar_event_sink,
                    bar_failure_sink=bar_failure_sink,
                    history_warmup_failure_sink=history_warmup_failure_sink,
                    quote_event_sink=used_tracker.record_quote,
                    mark_price_event_sink=used_tracker.record_mark,
                    live_history_warmup=True,
                )

            self._lifecycle.start(
                ActivationAdapterSpec(
                    activation_id=activation.activation_id,
                    factory=adapter_factory,
                )
            )
            self._record_runtime_event(
                "strategy_adapter_started",
                activation_id=activation.activation_id,
                entry_valid_until=entry_valid_until.isoformat(),
            )

    async def _wait_for_stop_and_sync_activations(
        self,
        stop_wait: Callable[[], object],
        capability: object,
        *,
        interval_seconds: float = 1.0,
    ) -> None:
        """Discover UI-created Demo activations without restarting the Executor."""

        if self._settings.release.profile != "BINANCE_DEMO":
            await self._loop.run_in_executor(None, stop_wait)
            return
        lifecycle = self._lifecycle
        if lifecycle is None:
            raise ExecutorRuntimeError("PRODUCT_RUNTIME_NOT_BUILT")

        stop_future = self._loop.run_in_executor(None, stop_wait)
        while not stop_future.done():
            await asyncio.sleep(interval_seconds)
            if stop_future.done():
                break
            previous_ids = set(lifecycle.activation_ids)
            self._restore_paused_adapters(capability)
            for activation_id, processor in tuple(
                self._responsibility_processors.items()
            ):
                try:
                    await processor.sync(activation_id)
                except Exception as exc:
                    self._record_runtime_event(
                        "responsibility_sync_failed",
                        activation_id=activation_id,
                        reason=type(exc).__name__,
                        reason_code=str(exc),
                    )
            current_ids = set(lifecycle.activation_ids)
            if current_ids - previous_ids:
                await self._wait_for_strategy_history_warmup()
        await stop_future

    async def _startup_and_stop(
        self,
        stop_wait: Callable[[], object],
        on_ready: Callable[[dict[str, object]], None] | None,
    ) -> None:
        for _ in range(3000):
            if self.node.is_running() and self.node.trader.is_running:
                break
            await asyncio.sleep(0.01)
        else:
            try:
                await self.node.stop_async()
            finally:
                raise ExecutorRuntimeError("TRADING_NODE_START_TIMEOUT")
        read_only = self._settings.release.profile == "BINANCE_LIVE_READ_ONLY"
        if read_only:
            self._start_read_only_adapter()
            await self._wait_for_strategy_history_warmup()
            if on_ready is not None:
                on_ready(
                    {
                        "product_runtime_started": True,
                        "profile": "BINANCE_LIVE_READ_ONLY",
                        "strategy_adapter_started": True,
                        "data_client_loaded": True,
                        "binance_credentials_loaded": False,
                        "instrument_commission_query_enabled": False,
                        "execution_client_loaded": False,
                        "database_connection_loaded": False,
                        "execution_action_repository_loaded": False,
                        "persisted_action_capability_loaded": False,
                        "startup_execution_reconciliation": "NOT_APPLICABLE",
                        "runtime_real_write_gate": self._runtime_real_write_gate,
                    }
                )
            await self._loop.run_in_executor(None, stop_wait)
            if self._lifecycle is not None:
                self._lifecycle.stop_all()
            await self.node.stop_async()
            return
        if self._capability is None:
            raise ExecutorRuntimeError("PRODUCT_RUNTIME_NOT_BUILT")
        self._restore_paused_adapters(self._capability)
        await asyncio.sleep(10.0)
        recovered = self.coordinator.recover_unresolved_actions(
            observed_at=datetime.now(UTC)
        )
        self._recovered_action_count = len(recovered)
        self._recovery_complete = True
        for activation_id, processor in self._responsibility_processors.items():
            processor.resume(activation_id)
        for processor in self._responsibility_processors.values():
            await processor.wait_idle()
        await self._wait_for_strategy_history_warmup()
        if on_ready is not None:
            on_ready(
                {
                    "product_runtime_started": True,
                    "database_continuity_guard_completed": True,
                    "startup_reconciliation_completed": True,
                    "recovered_unresolved_actions": len(recovered),
                    "runtime_real_write_gate": self._runtime_real_write_gate,
                }
            )
        await self._wait_for_stop_and_sync_activations(
            stop_wait,
            self._capability,
        )
        if self._lifecycle is not None:
            self._lifecycle.stop_all()
        await self.node.stop_async()

    def run_until_stop(
        self,
        stop_wait: Callable[[], object],
        *,
        on_ready: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        if self._node is None:
            raise ExecutorRuntimeError("PRODUCT_RUNTIME_NOT_BUILT")
        asyncio.set_event_loop(self._loop)
        task = self._loop.create_task(self._startup_and_stop(stop_wait, on_ready))
        try:
            self._node.run(raise_exception=True)
            task.result()
        finally:
            if not task.done():
                task.cancel()

    def close(self) -> None:
        for processor in self._proposal_processors.values():
            processor.close()
        self._proposal_processors.clear()
        for processor in self._responsibility_processors.values():
            processor.close()
        self._responsibility_processors.clear()
        if self._lifecycle is not None:
            try:
                self._lifecycle.stop_all()
            except Exception:
                pass
        if self._node is not None:
            try:
                if self._node.is_running():
                    self._node.stop()
                self._node.dispose()
            except Exception:
                pass
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:
                pass
        if self._owns_loop and not self._loop.is_closed():
            self._loop.close()
        self._lifecycle = None
        self._coordinator = None
        self._capability = None
        self._node = None
        self._connection = None
