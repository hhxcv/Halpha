"""The single live/backtest Halpha Strategy adapter and lifecycle wrapper."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import NAMESPACE_URL, uuid5

from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.trading.strategy import Strategy
from nautilus_trader.model.enums import OrderSide, TimeInForce, TriggerType
from nautilus_trader.model.data import Bar
from nautilus_trader.model.identifiers import ClientOrderId, InstrumentId
from nautilus_trader.model.objects import Price, Quantity

from halpha.planning.strategies.one_shot import (
    ActivationStrategyState,
    EntryEvaluationInput,
    OneShotDonchianAtrLogic,
    StrategyProposal,
)
from halpha.planning.bar_evaluation import NautilusBarEntryEvaluator


class ProposalSink(Protocol):
    def __call__(self, proposal: StrategyProposal) -> None: ...


class ExecutionEventSink(Protocol):
    def __call__(self, event: object) -> None: ...


class BarEventSink(Protocol):
    def __call__(self, bar: object) -> None: ...


class QuoteEventSink(Protocol):
    def __call__(self, tick: object) -> None: ...


class MarkPriceEventSink(Protocol):
    def __call__(self, mark_price: object) -> None: ...


class ControllerPort(Protocol):
    def create_strategy(self, strategy: Strategy, start: bool = True) -> None: ...

    def stop_strategy(self, strategy: Strategy) -> None: ...

    def remove_strategy(self, strategy: Strategy) -> None: ...


def strategy_id_for_activation(activation_id: str) -> str:
    stable = uuid5(NAMESPACE_URL, f"urn:halpha:activation:{activation_id}")
    return f"HALPHA-{stable.hex.upper()}"


def strategy_config_for_activation(activation_id: str) -> StrategyConfig:
    return StrategyConfig(
        strategy_id=strategy_id_for_activation(activation_id),
        order_id_tag="001",
        external_order_claims=None,
        manage_contingent_orders=False,
        manage_gtd_expiry=False,
        manage_stop=False,
    )


class HalphaStrategyAdapter(Strategy):
    """Final-style proposal adapter shared by live and BacktestEngine paths.

    The planning surface exposes no venue operation from this class. Execution may add only the private
    persisted-action gate allowed by ALP/EXE after its own qualification.
    """

    def __init__(
        self,
        *,
        activation_id: str,
        logic: OneShotDonchianAtrLogic,
        state_provider: Callable[[], ActivationStrategyState],
        proposal_sink: ProposalSink,
        instrument_ref: str | None = None,
        persisted_action_capability: object | None = None,
        execution_event_sink: ExecutionEventSink | None = None,
        bar_evaluator: NautilusBarEntryEvaluator | None = None,
        bar_event_sink: BarEventSink | None = None,
        quote_event_sink: QuoteEventSink | None = None,
        mark_price_event_sink: MarkPriceEventSink | None = None,
        live_history_warmup: bool = False,
        current_time_provider: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__(config=strategy_config_for_activation(activation_id))
        self._activation_id = activation_id
        self._logic = logic
        self._state_provider = state_provider
        self._proposal_sink = proposal_sink
        self._instrument_id = (
            InstrumentId.from_str(f"{instrument_ref}.BINANCE")
            if instrument_ref is not None
            else None
        )
        self._persisted_action_capability = persisted_action_capability
        self._execution_event_sink = execution_event_sink
        self._bar_evaluator = bar_evaluator
        self._bar_event_sink = bar_event_sink
        self._quote_event_sink = quote_event_sink
        self._mark_price_event_sink = mark_price_event_sink
        self._live_history_warmup = live_history_warmup
        self._current_time_provider = current_time_provider
        self._history_request_id: str | None = None
        self._live_bar_subscriptions_started = False
        self._stopping = False
        self._persisted_orders: dict[str, Any] = {}

    @property
    def activation_id(self) -> str:
        return self._activation_id

    @property
    def live_history_ready(self) -> bool:
        """Return whether the configured live history handoff is complete."""

        if not self._live_history_warmup:
            return True
        return bool(
            self._bar_evaluator is not None
            and self._bar_evaluator.warmup_complete
            and self._live_bar_subscriptions_started
        )

    def evaluate_normalized_entry(self, evaluation: EntryEvaluationInput) -> None:
        result = self._logic.evaluate_entry(evaluation, self._state_provider())
        if result.proposal is not None:
            self._proposal_sink(result.proposal)

    def on_start(self) -> None:
        if self._bar_evaluator is not None and not self._live_history_warmup:
            for bar_type in self._bar_evaluator.subscribed_bar_types:
                self.subscribe_bars(bar_type)
            self._live_bar_subscriptions_started = True
        if self._instrument_id is not None:
            self.subscribe_mark_prices(self._instrument_id)
            self.subscribe_quote_ticks(self._instrument_id)
        if self._bar_evaluator is not None and self._live_history_warmup:
            self._begin_live_history_warmup()

    def _begin_live_history_warmup(self) -> None:
        if self._bar_evaluator is None or self._history_request_id is not None:
            raise RuntimeError("LIVE_WARMUP_STATE_INVALID")
        current_time = (
            self._current_time_provider()
            if self._current_time_provider is not None
            else self.clock.utc_now()
        )
        if current_time.tzinfo is None:
            raise RuntimeError("LIVE_WARMUP_TIMEZONE_REQUIRED")
        minute_floor = current_time.astimezone(UTC).replace(second=0, microsecond=0)
        warmup_end = minute_floor - timedelta(milliseconds=1)
        fifteen_minute_floor = minute_floor.replace(
            minute=(minute_floor.minute // 15) * 15,
            second=0,
            microsecond=0,
        )
        warmup_start = fifteen_minute_floor - timedelta(hours=72)
        request_id = self.request_aggregated_bars(
            [
                self._bar_evaluator.target_bar_type,
            ],
            start=warmup_start,
            end=warmup_end,
            limit=1500,
            callback=self._on_live_history_complete,
            include_external_data=True,
            update_subscriptions=True,
            update_catalog=False,
        )
        self._history_request_id = str(request_id)

    def on_historical_data(self, data: object) -> None:
        if (
            self._live_history_warmup
            and self._bar_evaluator is not None
            and isinstance(data, Bar)
        ):
            self._bar_evaluator.accept_historical(data)

    def _on_live_history_complete(self, request_id: object) -> None:
        if self._stopping:
            return
        if self._history_request_id != str(request_id):
            raise RuntimeError("LIVE_WARMUP_REQUEST_ID_MISMATCH")
        if self._bar_evaluator is None:
            raise RuntimeError("LIVE_WARMUP_STATE_INVALID")
        self._bar_evaluator.complete_live_warmup()
        source, target = self._bar_evaluator.subscribed_bar_types
        self.subscribe_bars(source)
        self.subscribe_bars(target)
        self._live_bar_subscriptions_started = True

    def on_stop(self) -> None:
        self._stopping = True
        if self._bar_evaluator is not None and self._live_bar_subscriptions_started:
            for bar_type in reversed(self._bar_evaluator.subscribed_bar_types):
                self.unsubscribe_bars(bar_type)
        if self._instrument_id is not None:
            self.unsubscribe_quote_ticks(self._instrument_id)
            # The fixed Binance client has no mark-price unsubscribe coroutine.
            # The single node disconnect owns teardown of that stream.

    def on_bar(self, bar: object) -> None:
        if self._bar_event_sink is not None:
            self._bar_event_sink(bar)
        if self._bar_evaluator is None:
            return
        evaluation = self._bar_evaluator.accept(bar)
        if evaluation is not None:
            self.evaluate_normalized_entry(evaluation)

    def on_quote_tick(self, tick: object) -> None:
        if self._quote_event_sink is not None:
            self._quote_event_sink(tick)

    def on_mark_price(self, mark_price: object) -> None:
        if self._mark_price_event_sink is not None:
            self._mark_price_event_sink(mark_price)

    def _submit_persisted_order(
        self,
        capability: object,
        *,
        profile: str,
        instrument_ref: str,
        direction: str,
        quantity: str,
        price: str | None,
        trigger_price: str | None,
        reduce_only: bool,
        client_order_id: str,
    ) -> object:
        """EXE-only final write hop after a committed SUBMITTING action."""

        self._require_persisted_action_capability(capability)
        if client_order_id in self._persisted_orders:
            raise RuntimeError("DUPLICATE_IDENTITY_CONFLICT")
        instrument_id = InstrumentId.from_str(f"{instrument_ref}.BINANCE")
        if self.cache.instrument(instrument_id) is None:
            raise RuntimeError("INSTRUMENT_NOT_IN_CACHE")
        order_side = (
            OrderSide.BUY
            if (direction == "LONG") is not reduce_only
            else OrderSide.SELL
        )
        common = {
            "instrument_id": instrument_id,
            "order_side": order_side,
            "quantity": Quantity.from_str(quantity),
            "client_order_id": ClientOrderId(client_order_id),
        }
        if profile == "ENTRY_MARKET" or profile == "REDUCE_OR_CLOSE_MARKET":
            order = self.order_factory.market(**common, reduce_only=reduce_only)
        elif profile == "ENTRY_LIMIT":
            if price is None:
                raise ValueError("ACTION_PROFILE_MISMATCH")
            order = self.order_factory.limit(
                **common,
                price=Price.from_str(price),
                time_in_force=TimeInForce.GTC,
            )
        elif profile in {
            "ENTRY_STOP_MARKET",
            "PROTECTIVE_STOP_REDUCE_ONLY",
        }:
            if trigger_price is None:
                raise ValueError("ACTION_PROFILE_MISMATCH")
            order = self.order_factory.stop_market(
                **common,
                trigger_price=Price.from_str(trigger_price),
                trigger_type=TriggerType.LAST_PRICE,
                reduce_only=reduce_only,
            )
        elif profile in {"TAKE_PROFIT_1", "TAKE_PROFIT_2"}:
            if trigger_price is None:
                raise ValueError("ACTION_PROFILE_MISMATCH")
            order = self.order_factory.market_if_touched(
                **common,
                trigger_price=Price.from_str(trigger_price),
                trigger_type=TriggerType.LAST_PRICE,
                reduce_only=True,
            )
        else:
            raise ValueError("ACTION_PROFILE_UNQUALIFIED")
        self._persisted_orders[client_order_id] = order
        self.submit_order(order)
        return order

    def _query_persisted_order(self, capability: object, client_order_id: str) -> object:
        self._require_persisted_action_capability(capability)
        order = self._persisted_order(client_order_id)
        self.query_order(order)
        return order

    def _cancel_persisted_order(self, capability: object, client_order_id: str) -> object:
        self._require_persisted_action_capability(capability)
        order = self._persisted_order(client_order_id)
        if order.is_open:
            self.cancel_order(order)
        else:
            self.query_order(order)
        return order

    def _persisted_order(self, client_order_id: str) -> object:
        existing = self._persisted_orders.get(client_order_id)
        if existing is not None:
            return existing
        recovered = self.cache.order(ClientOrderId(client_order_id))
        if recovered is None:
            raise RuntimeError("POSITION_UNKNOWN")
        self._persisted_orders[client_order_id] = recovered
        return recovered

    def _require_persisted_action_capability(self, capability: object) -> None:
        if (
            self._persisted_action_capability is None
            or capability is not self._persisted_action_capability
        ):
            raise RuntimeError("AUTHORIZATION_MISMATCH")

    def _forward_execution_event(self, event: object) -> None:
        if self._execution_event_sink is not None:
            self._execution_event_sink(event)

    def on_order_submitted(self, event: object) -> None:
        self._forward_execution_event(event)

    def on_order_accepted(self, event: object) -> None:
        self._forward_execution_event(event)

    def on_order_rejected(self, event: object) -> None:
        self._forward_execution_event(event)

    def on_order_denied(self, event: object) -> None:
        self._forward_execution_event(event)

    def on_order_updated(self, event: object) -> None:
        self._forward_execution_event(event)

    def on_order_filled(self, event: object) -> None:
        self._forward_execution_event(event)

    def on_order_canceled(self, event: object) -> None:
        self._forward_execution_event(event)

    def on_order_expired(self, event: object) -> None:
        self._forward_execution_event(event)

    def on_order_cancel_rejected(self, event: object) -> None:
        self._forward_execution_event(event)


@dataclass(frozen=True)
class ActivationAdapterSpec:
    activation_id: str
    factory: Callable[[], HalphaStrategyAdapter]


class ActivationAdapterLifecycle:
    """One adapter per open non-takeover activation, owned by Controller."""

    def __init__(self, controller: ControllerPort) -> None:
        self._controller = controller
        self._adapters: dict[str, HalphaStrategyAdapter] = {}

    @property
    def activation_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))

    def adapter_for_activation(self, activation_id: str) -> HalphaStrategyAdapter:
        try:
            return self._adapters[activation_id]
        except KeyError:
            raise RuntimeError("ACTIVATION_ADAPTER_NOT_READY") from None

    def start(self, spec: ActivationAdapterSpec) -> HalphaStrategyAdapter:
        existing = self._adapters.get(spec.activation_id)
        if existing is not None:
            return existing
        adapter = spec.factory()
        if adapter.activation_id != spec.activation_id:
            raise ValueError("ADAPTER_ACTIVATION_MISMATCH")
        self._controller.create_strategy(adapter, start=True)
        self._adapters[spec.activation_id] = adapter
        return adapter

    def stop_and_remove(self, activation_id: str) -> None:
        adapter = self._adapters.pop(activation_id, None)
        if adapter is None:
            return
        self._controller.stop_strategy(adapter)
        self._controller.remove_strategy(adapter)

    def stop_all(self) -> None:
        for activation_id in tuple(self._adapters):
            self.stop_and_remove(activation_id)
