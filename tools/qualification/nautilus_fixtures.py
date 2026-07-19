from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from datetime import timezone
from uuid import uuid4

from nautilus_trader.indicators import AverageTrueRange
from nautilus_trader.indicators import DonchianChannel
from nautilus_trader.indicators import MovingAverageType
from nautilus_trader.live.config import ControllerConfig
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.enums import TimeInForce
from nautilus_trader.model.enums import TriggerType
from nautilus_trader.model.identifiers import ClientOrderId
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.trading.controller import Controller
from nautilus_trader.trading.strategy import Strategy

from tools.qualification.strategy_logic_fixture import OneShotQualificationLogic


class QualificationController(Controller):
    """Minimal public Controller used only by the DIRECT lifecycle fixture."""

    def __init__(self, trader, config: ControllerConfig | None = None) -> None:
        super().__init__(trader=trader, config=config)


class QualificationStrategy(Strategy):
    """No-I/O strategy used to exercise public Controller lifecycle calls."""

    def __init__(self, config: StrategyConfig | None = None) -> None:
        super().__init__(config=config)


class LiveProposalQualificationStrategy(Strategy):
    """No-I/O live harness adapter for the shared proposal-only fixture."""

    def __init__(self, config: StrategyConfig | None = None) -> None:
        super().__init__(config=config)
        self.logic = OneShotQualificationLogic(
            activation_id="DIRECT-LIVE-HARNESS-ACTIVATION-001",
            instrument_id="BTCUSDT-PERP.BINANCE",
        )
        self.proposals: list[dict[str, str]] = []

    def on_start(self) -> None:
        proposal = self.logic.evaluate_entry(
            trigger_id="LIVE_HARNESS_START",
            reference_price="100001.0",
            reference_source="LIVE_HARNESS_REFERENCE_PROXY",
        )
        if proposal is not None:
            self.proposals.append(proposal.canonical())


class MarketDataQualificationStrategy(Strategy):
    """DIRECT-only fixture for public historical and live Binance data APIs."""

    REQUEST_SAFE_SECOND = 30

    def __init__(self, config: StrategyConfig | None = None) -> None:
        super().__init__(config=config)
        self.instrument_ids = (
            InstrumentId.from_str("BTCUSDT-PERP.BINANCE"),
            InstrumentId.from_str("ETHUSDT-PERP.BINANCE"),
        )
        self.source_types = {
            instrument_id: BarType.from_str(
                f"{instrument_id}-1-MINUTE-LAST-EXTERNAL",
            )
            for instrument_id in self.instrument_ids
        }
        self.target_types = {
            instrument_id: BarType.from_str(
                f"{instrument_id}-15-MINUTE-LAST-INTERNAL@1-MINUTE-EXTERNAL",
            )
            for instrument_id in self.instrument_ids
        }
        self.donchian = {
            instrument_id: DonchianChannel(20)
            for instrument_id in self.instrument_ids
        }
        self.atr = {
            instrument_id: AverageTrueRange(
                period=14,
                ma_type=MovingAverageType.WILDER,
                use_previous=True,
                value_floor=0.0,
            )
            for instrument_id in self.instrument_ids
        }
        self.sequence: list[str] = []
        self.errors: list[str] = []
        self.request_ids: dict[InstrumentId, str] = {}
        self.completed_requests: set[InstrumentId] = set()
        self.historical_timestamps: dict[str, list[int]] = {}
        self.live_bar_timestamps: dict[str, list[int]] = {}
        self.mark_timestamps: dict[InstrumentId, list[int]] = {}
        self.quote_timestamps: dict[InstrumentId, list[int]] = {}
        self.warmup_start = None
        self.warmup_end = None
        self.request_deferred_seconds = 0

    def on_start(self) -> None:
        for instrument_id in self.instrument_ids:
            target = self.target_types[instrument_id]
            self.register_indicator_for_bars(target, self.donchian[instrument_id])
            self.register_indicator_for_bars(target, self.atr[instrument_id])
            self.sequence.append(f"REGISTER_INDICATORS:{instrument_id}")

        now_seconds = self.clock.timestamp_ns() // 1_000_000_000
        now = datetime.fromtimestamp(now_seconds, tz=timezone.utc)
        if now.second < self.REQUEST_SAFE_SECOND:
            request_at = now.replace(second=self.REQUEST_SAFE_SECOND, microsecond=0)
            self.request_deferred_seconds = self.REQUEST_SAFE_SECOND - now.second
            self.sequence.append("DEFER_HISTORY_TO_SAFE_SECOND")
            self.clock.set_time_alert(
                name="DIRECT_MARKET_HISTORY_SAFE_SECOND",
                alert_time=request_at,
                callback=self._begin_history_requests,
                allow_past=False,
            )
        else:
            self._begin_history_requests()

    def _begin_history_requests(self, _event=None) -> None:
        if self.request_ids:
            self.errors.append("HISTORY_REQUEST_STARTED_MORE_THAN_ONCE")
            return
        minute_floor_seconds = self.clock.timestamp_ns() // 60_000_000_000 * 60
        minute_floor = datetime.fromtimestamp(minute_floor_seconds, tz=timezone.utc)
        self.warmup_end = minute_floor
        fifteen_minute_floor = minute_floor.replace(
            minute=(minute_floor.minute // 15) * 15,
        )
        self.warmup_start = fifteen_minute_floor - timedelta(hours=72)

        for instrument_id in self.instrument_ids:
            target = self.target_types[instrument_id]
            request_id = self.request_aggregated_bars(
                [target],
                start=self.warmup_start,
                end=self.warmup_end,
                limit=1500,
                callback=lambda completed_id, used_id=instrument_id: self._on_history_complete(
                    used_id,
                    completed_id,
                ),
                include_external_data=True,
                update_subscriptions=True,
                update_catalog=False,
            )
            self.request_ids[instrument_id] = str(request_id)
            self.sequence.append(f"REQUEST_HISTORY:{instrument_id}")

    def on_historical_data(self, data) -> None:
        if isinstance(data, Bar):
            self.historical_timestamps.setdefault(str(data.bar_type), []).append(data.ts_event)

    def _on_history_complete(self, instrument_id: InstrumentId, request_id) -> None:
        try:
            self.sequence.append(f"CALLBACK_BEGIN:{instrument_id}")
            self.subscribe_bars(self.source_types[instrument_id])
            self.sequence.append(f"SUBSCRIBE_SOURCE:{instrument_id}")
            self.subscribe_bars(self.target_types[instrument_id])
            self.sequence.append(f"SUBSCRIBE_TARGET:{instrument_id}")
            self.subscribe_mark_prices(instrument_id)
            self.sequence.append(f"SUBSCRIBE_MARK:{instrument_id}")
            self.subscribe_quote_ticks(instrument_id)
            self.sequence.append(f"SUBSCRIBE_QUOTE:{instrument_id}")
            self.completed_requests.add(instrument_id)
            self.sequence.append(f"CALLBACK_END:{instrument_id}")
            if self.request_ids.get(instrument_id) != str(request_id):
                self.errors.append(f"REQUEST_CALLBACK_ID_MISMATCH:{instrument_id}")
        except Exception as exc:
            self.errors.append(f"CALLBACK_FAILED:{instrument_id}:{type(exc).__name__}")

    def on_bar(self, bar: Bar) -> None:
        self.live_bar_timestamps.setdefault(str(bar.bar_type), []).append(bar.ts_event)

    def on_mark_price(self, mark_price) -> None:
        self.mark_timestamps.setdefault(mark_price.instrument_id, []).append(mark_price.ts_event)

    def on_quote_tick(self, tick) -> None:
        self.quote_timestamps.setdefault(tick.instrument_id, []).append(tick.ts_event)

    def on_stop(self) -> None:
        for instrument_id in self.instrument_ids:
            self.unsubscribe_bars(self.target_types[instrument_id])
            self.unsubscribe_bars(self.source_types[instrument_id])
            self.unsubscribe_quote_ticks(instrument_id)

    @property
    def smoke_ready(self) -> bool:
        return bool(
            len(self.completed_requests) == len(self.instrument_ids)
            and all(
                self.live_bar_timestamps.get(str(self.source_types[instrument_id]))
                for instrument_id in self.instrument_ids
            )
            and all(self.mark_timestamps.get(instrument_id) for instrument_id in self.instrument_ids)
            and all(self.quote_timestamps.get(instrument_id) for instrument_id in self.instrument_ids)
        )

    @staticmethod
    def _is_continuous(timestamps: list[int], interval_ns: int, count: int) -> bool:
        unique = sorted(set(timestamps))
        if len(unique) < count:
            return False
        recent = unique[-count:]
        return all(
            later - earlier == interval_ns
            for earlier, later in zip(recent, recent[1:])
        )

    def qualification_evidence(self) -> tuple[dict[str, object], list[str]]:
        errors = list(self.errors)
        instruments: dict[str, dict[str, object]] = {}
        for instrument_id in self.instrument_ids:
            source = self.source_types[instrument_id]
            target = self.target_types[instrument_id]
            source_history = self.historical_timestamps.get(str(source), [])
            target_history = self.historical_timestamps.get(str(target.standard()), [])
            source_live = self.live_bar_timestamps.get(str(source), [])
            target_live = self.live_bar_timestamps.get(str(target.standard()), [])
            source_history_unique = sorted(set(source_history))
            target_history_unique = sorted(set(target_history))
            source_live_unique = sorted(set(source_live))
            source_continuous = self._is_continuous(source_history, 60_000_000_000, 15)
            target_continuous = self._is_continuous(target_history, 900_000_000_000, 20)
            boundary_delta_ns = (
                source_live_unique[0] - source_history_unique[-1]
                if source_history_unique and source_live_unique
                else None
            )
            if not source_continuous:
                errors.append(f"HISTORICAL_SOURCE_NOT_CONTINUOUS:{instrument_id}")
            if not target_continuous:
                errors.append(f"HISTORICAL_TARGET_NOT_CONTINUOUS:{instrument_id}")
            if not self.donchian[instrument_id].initialized:
                errors.append(f"DONCHIAN_NOT_INITIALIZED:{instrument_id}")
            if not self.atr[instrument_id].initialized:
                errors.append(f"ATR_NOT_INITIALIZED:{instrument_id}")
            if boundary_delta_ns not in {0, 60_000_000_000}:
                errors.append(f"HISTORY_LIVE_SOURCE_BOUNDARY_GAP:{instrument_id}")
            instruments[str(instrument_id)] = {
                "source_1m": str(source),
                "target_15m": str(target),
                "delivered_target_15m": str(target.standard()),
                "target_composite_source": str(target.composite()),
                "historical_source_count": len(source_history),
                "historical_target_count": len(target_history),
                "historical_source_recent_15_continuous": source_continuous,
                "historical_target_recent_20_continuous": target_continuous,
                "historical_source_duplicate_timestamps": len(source_history)
                - len(set(source_history)),
                "historical_target_duplicate_timestamps": len(target_history)
                - len(set(target_history)),
                "historical_source_first_ts_ns": (
                    source_history_unique[0] if source_history_unique else None
                ),
                "historical_source_last_ts_ns": (
                    source_history_unique[-1] if source_history_unique else None
                ),
                "historical_target_first_ts_ns": (
                    target_history_unique[0] if target_history_unique else None
                ),
                "historical_target_last_ts_ns": (
                    target_history_unique[-1] if target_history_unique else None
                ),
                "live_source_count": len(source_live),
                "live_source_first_ts_ns": source_live_unique[0] if source_live_unique else None,
                "history_live_source_boundary_delta_ns": boundary_delta_ns,
                "history_live_source_boundary": (
                    "IDENTICAL_REPLAY"
                    if boundary_delta_ns == 0
                    else "CONTIGUOUS_NEXT_BAR"
                    if boundary_delta_ns == 60_000_000_000
                    else "GAP_OR_UNKNOWN"
                ),
                "live_target_count": len(target_live),
                "mark_price_count": len(self.mark_timestamps.get(instrument_id, [])),
                "quote_tick_count": len(self.quote_timestamps.get(instrument_id, [])),
                "quote_bid_ask_same_event": bool(self.quote_timestamps.get(instrument_id)),
                "donchian_initialized": self.donchian[instrument_id].initialized,
                "atr_initialized": self.atr[instrument_id].initialized,
            }

        return (
            {
                "request": {
                    "warmup_start": (
                        self.warmup_start.isoformat() if self.warmup_start is not None else None
                    ),
                    "warmup_end": (
                        self.warmup_end.isoformat() if self.warmup_end is not None else None
                    ),
                    "duration_hours": 72,
                    "limit": 1500,
                    "include_external_data": True,
                    "update_subscriptions": True,
                    "update_catalog": False,
                    "custom_time_range_segmentation": False,
                    "safe_request_second": self.REQUEST_SAFE_SECOND,
                    "deferred_seconds": self.request_deferred_seconds,
                    "end_boundary_adjustment": (
                        "EXACT_MINUTE_FLOOR; COMPONENT_FILTERS_INCOMPLETE_CURRENT_BAR"
                    ),
                },
                "callback_sequence": list(self.sequence),
                "completed_request_count": len(self.completed_requests),
                "instruments": instruments,
            },
            errors,
        )


class BacktestQualificationStrategy(Strategy):
    """DIRECT-only adapter proving one-shot proposal, fill, fee, and close behavior."""

    def __init__(
        self,
        *,
        instrument_id: InstrumentId,
        bar_type: BarType,
        config: StrategyConfig | None = None,
    ) -> None:
        super().__init__(config=config)
        self.instrument_id = instrument_id
        self.bar_type = bar_type
        self.logic = OneShotQualificationLogic(
            activation_id="DIRECT-BACKTEST-ACTIVATION-001",
            instrument_id=str(instrument_id),
        )
        self.proposals: list[dict[str, str]] = []
        self.fills: list[dict[str, str]] = []
        self.entry_submitted = False
        self.exit_submitted = False
        self.closed_positions = 0

    def on_start(self) -> None:
        self.subscribe_bars(self.bar_type)

    def on_bar(self, bar: Bar) -> None:
        proposal = self.logic.evaluate_entry(
            trigger_id=f"BAR:{bar.ts_event}",
            reference_price=str(bar.close),
            reference_source="BACKTEST_LAST_BAR_PROXY",
        )
        if proposal is not None:
            self.proposals.append(proposal.canonical())
            self.entry_submitted = True
            entry = self.order_factory.market(
                instrument_id=self.instrument_id,
                order_side=OrderSide.BUY,
                quantity=Quantity.from_str("0.010"),
            )
            self.submit_order(entry)
            return

        if self.cache.positions_open() and not self.exit_submitted:
            self.exit_submitted = True
            exit_order = self.order_factory.market(
                instrument_id=self.instrument_id,
                order_side=OrderSide.SELL,
                quantity=Quantity.from_str("0.010"),
                reduce_only=True,
            )
            self.submit_order(exit_order)

    def on_order_filled(self, event) -> None:
        self.fills.append(
            {
                "order_side": str(event.order_side),
                "last_price": str(event.last_px),
                "last_quantity": str(event.last_qty),
                "commission": str(event.commission),
            },
        )

    def on_position_closed(self, _event) -> None:
        self.closed_positions += 1

    def on_stop(self) -> None:
        self.unsubscribe_bars(self.bar_type)


class DemoOrderCapabilityStrategy(Strategy):
    """DIRECT-only public-API probe for one ordinary and one algo order round trip."""

    CANCEL_DELAY_SECONDS = 2
    QUERY_DELAY_SECONDS = 0.5

    def __init__(self, config: StrategyConfig | None = None) -> None:
        super().__init__(config=config)
        self.instrument_id = InstrumentId.from_str("BTCUSDT-PERP.BINANCE")
        self.armed = False
        self.started = False
        self.done = False
        self.errors: list[str] = []
        self.sequence: list[str] = []
        self.orders: dict[str, object] = {}
        self.query_calls: set[str] = set()
        self.accepted: set[str] = set()
        self.canceled: set[str] = set()
        self._last_ask: Price | None = None

    def on_start(self) -> None:
        self.sequence.append("STRATEGY_STARTED_UNARMED")

    def arm(self) -> None:
        if self.armed:
            self.errors.append("ARMED_MORE_THAN_ONCE")
            return
        self.armed = True
        self.subscribe_quote_ticks(self.instrument_id)
        self.sequence.append("ARMED_AFTER_READ_ONLY_PREFLIGHT")

    def on_quote_tick(self, tick) -> None:
        self._last_ask = tick.ask_price
        if not self.armed or self.started:
            return
        self.started = True
        instrument = self.cache.instrument(self.instrument_id)
        if instrument is None:
            self.errors.append("INSTRUMENT_NOT_IN_CACHE")
            return
        limit_price = instrument.make_price(float(tick.bid_price) * 0.8)
        order = self.order_factory.limit(
            instrument_id=self.instrument_id,
            order_side=OrderSide.BUY,
            quantity=instrument.make_qty("0.002"),
            price=limit_price,
            time_in_force=TimeInForce.GTC,
            client_order_id=ClientOrderId(uuid4().hex),
        )
        self.orders["ENTRY_LIMIT"] = order
        self.sequence.append("SUBMIT_ENTRY_LIMIT")
        self.submit_order(order)

    def on_order_accepted(self, event) -> None:
        profile = self._profile_for_client_order_id(event.client_order_id)
        if profile is None:
            self.errors.append("ACCEPTED_UNKNOWN_ORDER")
            return
        self.accepted.add(profile)
        self.sequence.append(f"ACCEPTED:{profile}")
        self._schedule_query(profile)
        self._schedule_cancel(profile)

    def _schedule_query(self, profile: str) -> None:
        now = datetime.fromtimestamp(self.clock.timestamp_ns() / 1_000_000_000, tz=timezone.utc)
        self.clock.set_time_alert(
            name=f"DIRECT_QUERY_{profile}",
            alert_time=now + timedelta(seconds=self.QUERY_DELAY_SECONDS),
            callback=lambda _event, used_profile=profile: self._query_profile(used_profile),
            allow_past=False,
        )

    def _query_profile(self, profile: str) -> None:
        order = self.orders[profile]
        if order.is_open:
            self.query_order(order)
            self.query_calls.add(profile)
            self.sequence.append(f"PUBLIC_QUERY:{profile}")
        else:
            self.errors.append(f"ORDER_NOT_OPEN_AT_QUERY:{profile}")

    def _schedule_cancel(self, profile: str) -> None:
        now = datetime.fromtimestamp(self.clock.timestamp_ns() / 1_000_000_000, tz=timezone.utc)
        self.clock.set_time_alert(
            name=f"DIRECT_CANCEL_{profile}",
            alert_time=now + timedelta(seconds=self.CANCEL_DELAY_SECONDS),
            callback=lambda _event, used_profile=profile: self._cancel_profile(used_profile),
            allow_past=False,
        )

    def _cancel_profile(self, profile: str) -> None:
        order = self.orders[profile]
        if order.is_open:
            self.sequence.append(f"PUBLIC_CANCEL:{profile}")
            self.cancel_order(order)
        elif not order.is_closed:
            self.errors.append(f"ORDER_NOT_OPEN_AT_CANCEL:{profile}")

    def on_order_canceled(self, event) -> None:
        profile = self._profile_for_client_order_id(event.client_order_id)
        if profile is None:
            self.errors.append("CANCELED_UNKNOWN_ORDER")
            return
        self.canceled.add(profile)
        self.sequence.append(f"CANCELED:{profile}")
        if profile == "ENTRY_LIMIT":
            self._submit_entry_stop_market()
        elif profile == "ENTRY_STOP_MARKET":
            self.done = True
            self.sequence.append("ROUND_TRIPS_COMPLETED")

    def _submit_entry_stop_market(self) -> None:
        instrument = self.cache.instrument(self.instrument_id)
        if instrument is None or self._last_ask is None:
            self.errors.append("STOP_ORDER_REFERENCE_UNAVAILABLE")
            return
        trigger_price = instrument.make_price(float(self._last_ask) * 1.2)
        order = self.order_factory.stop_market(
            instrument_id=self.instrument_id,
            order_side=OrderSide.BUY,
            quantity=instrument.make_qty("0.002"),
            trigger_price=trigger_price,
            trigger_type=TriggerType.LAST_PRICE,
            reduce_only=False,
            client_order_id=ClientOrderId(uuid4().hex),
        )
        self.orders["ENTRY_STOP_MARKET"] = order
        self.sequence.append("SUBMIT_ENTRY_STOP_MARKET")
        self.submit_order(order)

    def on_order_denied(self, event) -> None:
        profile = self._profile_for_client_order_id(event.client_order_id) or "UNKNOWN"
        self.errors.append(f"ORDER_DENIED:{profile}")

    def on_order_rejected(self, event) -> None:
        profile = self._profile_for_client_order_id(event.client_order_id) or "UNKNOWN"
        self.errors.append(f"ORDER_REJECTED:{profile}")

    def on_order_cancel_rejected(self, event) -> None:
        profile = self._profile_for_client_order_id(event.client_order_id) or "UNKNOWN"
        self.errors.append(f"ORDER_CANCEL_REJECTED:{profile}")

    def request_cleanup(self) -> None:
        for profile, order in self.orders.items():
            if order.is_open and profile in self.accepted:
                self.sequence.append(f"CLEANUP_CANCEL:{profile}")
                self.cancel_order(order)

    def _profile_for_client_order_id(self, client_order_id: ClientOrderId) -> str | None:
        for profile, order in self.orders.items():
            if order.client_order_id == client_order_id:
                return profile
        return None

    def qualification_evidence(self) -> dict[str, object]:
        return {
            "sequence": list(self.sequence),
            "profiles": sorted(self.orders),
            "accepted_profiles": sorted(self.accepted),
            "public_query_profiles": sorted(self.query_calls),
            "canceled_profiles": sorted(self.canceled),
            "client_order_ids_are_uuid32": all(
                len(order.client_order_id.value) == 32
                and order.client_order_id.value.isascii()
                and order.client_order_id.value.islower()
                and all(character in "0123456789abcdef" for character in order.client_order_id.value)
                for order in self.orders.values()
            ),
            "actual_client_order_ids_persisted": False,
            "write_retry": "DISABLED_BY_EXEC_CLIENT_CONFIG",
            "done": self.done,
            "errors": list(self.errors),
        }

    def on_stop(self) -> None:
        if self.armed:
            self.unsubscribe_quote_ticks(self.instrument_id)


class DemoRestartSeedStrategy(Strategy):
    """DIRECT-only fixture which leaves exact far-away orders open across one restart."""

    def __init__(self, config: StrategyConfig | None = None) -> None:
        super().__init__(config=config)
        self.instrument_id = InstrumentId.from_str("BTCUSDT-PERP.BINANCE")
        self.armed = False
        self.started = False
        self.orders: dict[str, object] = {}
        self.accepted: set[str] = set()
        self.errors: list[str] = []

    def arm(self) -> None:
        if self.armed:
            self.errors.append("ARMED_MORE_THAN_ONCE")
            return
        self.armed = True
        self.subscribe_quote_ticks(self.instrument_id)

    def on_quote_tick(self, tick) -> None:
        if not self.armed or self.started:
            return
        self.started = True
        instrument = self.cache.instrument(self.instrument_id)
        if instrument is None:
            self.errors.append("INSTRUMENT_NOT_IN_CACHE")
            return

        orders = {
            "KNOWN_ORDINARY": self.order_factory.limit(
                instrument_id=self.instrument_id,
                order_side=OrderSide.BUY,
                quantity=instrument.make_qty("0.002"),
                price=instrument.make_price(float(tick.bid_price) * 0.8),
                time_in_force=TimeInForce.GTC,
                client_order_id=ClientOrderId(uuid4().hex),
            ),
            "UNKNOWN_SENTINEL": self.order_factory.limit(
                instrument_id=self.instrument_id,
                order_side=OrderSide.BUY,
                quantity=instrument.make_qty("0.002"),
                price=instrument.make_price(float(tick.bid_price) * 0.75),
                time_in_force=TimeInForce.GTC,
                client_order_id=ClientOrderId(uuid4().hex),
            ),
            "KNOWN_ALGO": self.order_factory.stop_market(
                instrument_id=self.instrument_id,
                order_side=OrderSide.BUY,
                quantity=instrument.make_qty("0.002"),
                trigger_price=instrument.make_price(float(tick.ask_price) * 1.2),
                trigger_type=TriggerType.LAST_PRICE,
                reduce_only=False,
                client_order_id=ClientOrderId(uuid4().hex),
            ),
        }
        self.orders.update(orders)
        for order in orders.values():
            self.submit_order(order)

    def on_order_accepted(self, event) -> None:
        profile = self._profile_for_client_order_id(event.client_order_id)
        if profile is None:
            self.errors.append("ACCEPTED_UNKNOWN_ORDER")
            return
        self.accepted.add(profile)

    def on_order_denied(self, event) -> None:
        profile = self._profile_for_client_order_id(event.client_order_id) or "UNKNOWN"
        self.errors.append(f"ORDER_DENIED:{profile}")

    def on_order_rejected(self, event) -> None:
        profile = self._profile_for_client_order_id(event.client_order_id) or "UNKNOWN"
        self.errors.append(f"ORDER_REJECTED:{profile}")

    def _profile_for_client_order_id(self, client_order_id: ClientOrderId) -> str | None:
        for profile, order in self.orders.items():
            if order.client_order_id == client_order_id:
                return profile
        return None

    def on_stop(self) -> None:
        if self.armed:
            self.unsubscribe_quote_ticks(self.instrument_id)


class DemoExternalOrderRecoveryStrategy(Strategy):
    """DIRECT-only fixture for canceling one reconciled external order via Strategy API."""

    def __init__(self, config: StrategyConfig | None = None) -> None:
        super().__init__(config=config)
        self.cancel_called = False
        self.cancel_call_count = 0
        self.query_call_count = 0

    def query_reconciled_order(self, order) -> None:
        self.query_call_count += 1
        self.query_order(order)

    def cancel_reconciled_order(self, order) -> None:
        self.cancel_called = True
        self.cancel_call_count += 1
        self.cancel_order(order)


class DemoReduceOnlyTopologyStrategy(Strategy):
    """DIRECT-only fixture for explicit-quantity reduce-only topology probes."""

    def __init__(self, config: StrategyConfig | None = None) -> None:
        super().__init__(config=config)
        self.instrument_id = InstrumentId.from_str("BTCUSDT-PERP.BINANCE")
        self.last_bid: Price | None = None
        self.last_ask: Price | None = None
        self.orders: dict[str, object] = {}
        self.submitted: list[str] = []
        self.accepted: set[str] = set()
        self.filled: set[str] = set()
        self.canceled: set[str] = set()
        self.expired: set[str] = set()
        self.public_query_calls: list[str] = []
        self.public_cancel_calls: list[str] = []
        self.fill_quantities: dict[str, list[str]] = {}
        self.errors: list[str] = []

    def on_start(self) -> None:
        self.subscribe_quote_ticks(self.instrument_id)

    def on_quote_tick(self, tick) -> None:
        self.last_bid = tick.bid_price
        self.last_ask = tick.ask_price

    def submit_entry_market(self, profile: str, quantity: str) -> None:
        instrument = self._instrument()
        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=OrderSide.BUY,
            quantity=instrument.make_qty(quantity),
            reduce_only=False,
            client_order_id=ClientOrderId(uuid4().hex),
        )
        self._submit_profile(profile, order)

    def submit_protective_stop(
        self,
        profile: str,
        quantity: str,
        trigger_price: float,
    ) -> None:
        instrument = self._instrument()
        order = self.order_factory.stop_market(
            instrument_id=self.instrument_id,
            order_side=OrderSide.SELL,
            quantity=instrument.make_qty(quantity),
            trigger_price=instrument.make_price(trigger_price),
            trigger_type=TriggerType.LAST_PRICE,
            reduce_only=True,
            client_order_id=ClientOrderId(uuid4().hex),
        )
        self._submit_profile(profile, order)

    def submit_take_profit(
        self,
        profile: str,
        quantity: str,
        trigger_price: float,
    ) -> None:
        instrument = self._instrument()
        order = self.order_factory.market_if_touched(
            instrument_id=self.instrument_id,
            order_side=OrderSide.SELL,
            quantity=instrument.make_qty(quantity),
            trigger_price=instrument.make_price(trigger_price),
            trigger_type=TriggerType.LAST_PRICE,
            reduce_only=True,
            client_order_id=ClientOrderId(uuid4().hex),
        )
        self._submit_profile(profile, order)

    def submit_reduce_only_market(
        self,
        profile: str,
        quantity: str,
        order_side: OrderSide = OrderSide.SELL,
    ) -> None:
        instrument = self._instrument()
        order = self.order_factory.market(
            instrument_id=self.instrument_id,
            order_side=order_side,
            quantity=instrument.make_qty(quantity),
            reduce_only=True,
            client_order_id=ClientOrderId(uuid4().hex),
        )
        self._submit_profile(profile, order)

    def query_profile(self, profile: str) -> None:
        order = self.orders[profile]
        self.public_query_calls.append(profile)
        self.query_order(order)

    def adopt_reconciled_order(self, profile: str, order) -> None:
        if profile in self.orders:
            raise RuntimeError(f"DUPLICATE_PROFILE:{profile}")
        self.orders[profile] = order

    def cancel_profile(self, profile: str) -> None:
        order = self.orders[profile]
        if order.is_open:
            self.public_cancel_calls.append(profile)
            self.cancel_order(order)

    def request_public_cleanup(self) -> None:
        for profile in list(self.submitted):
            self.cancel_profile(profile)

    def on_order_accepted(self, event) -> None:
        profile = self._profile_for_client_order_id(event.client_order_id)
        if profile is None:
            self.errors.append("ACCEPTED_UNKNOWN_ORDER")
            return
        self.accepted.add(profile)

    def on_order_filled(self, event) -> None:
        profile = self._profile_for_client_order_id(event.client_order_id)
        if profile is None:
            self.errors.append("FILLED_UNKNOWN_ORDER")
            return
        self.fill_quantities.setdefault(profile, []).append(str(event.last_qty))
        order = self.orders[profile]
        if order.is_closed:
            self.filled.add(profile)

    def on_order_canceled(self, event) -> None:
        profile = self._profile_for_client_order_id(event.client_order_id)
        if profile is None:
            self.errors.append("CANCELED_UNKNOWN_ORDER")
            return
        self.canceled.add(profile)

    def on_order_expired(self, event) -> None:
        profile = self._profile_for_client_order_id(event.client_order_id)
        if profile is None:
            self.errors.append("EXPIRED_UNKNOWN_ORDER")
            return
        self.expired.add(profile)

    def on_order_denied(self, event) -> None:
        profile = self._profile_for_client_order_id(event.client_order_id) or "UNKNOWN"
        self.errors.append(f"ORDER_DENIED:{profile}:{event.reason}")

    def on_order_rejected(self, event) -> None:
        profile = self._profile_for_client_order_id(event.client_order_id) or "UNKNOWN"
        self.errors.append(f"ORDER_REJECTED:{profile}:{event.reason}")

    def on_order_cancel_rejected(self, event) -> None:
        profile = self._profile_for_client_order_id(event.client_order_id) or "UNKNOWN"
        self.errors.append(f"ORDER_CANCEL_REJECTED:{profile}:{event.reason}")

    def on_stop(self) -> None:
        self.unsubscribe_quote_ticks(self.instrument_id)

    def _instrument(self):
        instrument = self.cache.instrument(self.instrument_id)
        if instrument is None:
            raise RuntimeError("INSTRUMENT_NOT_IN_CACHE")
        return instrument

    def _submit_profile(self, profile: str, order) -> None:
        if profile in self.orders:
            raise RuntimeError(f"DUPLICATE_PROFILE:{profile}")
        self.orders[profile] = order
        self.submitted.append(profile)
        self.submit_order(order)

    def _profile_for_client_order_id(self, client_order_id: ClientOrderId) -> str | None:
        for profile, order in self.orders.items():
            if order.client_order_id == client_order_id:
                return profile
        return None
