from __future__ import annotations

from datetime import UTC, datetime
from types import MethodType, SimpleNamespace

from nautilus_trader.core.uuid import UUID4
from nautilus_trader.model.events import OrderRejected
from nautilus_trader.model.identifiers import (
    AccountId,
    ClientOrderId,
    InstrumentId,
    StrategyId,
    TraderId,
)

from tools.qualification.run_b04_historical_backtest import (
    HistoricalEpisodeGateway,
)
import tools.qualification.run_b04_historical_backtest as historical_backtest


def _rejected_event(client_order_id: str) -> OrderRejected:
    observed_at = datetime(2024, 7, 15, 19, 28, tzinfo=UTC)
    observed_ns = int(observed_at.timestamp() * 1_000_000_000)
    return OrderRejected(
        trader_id=TraderId("BACKTESTER-001"),
        strategy_id=StrategyId("HALPHA-001"),
        instrument_id=InstrumentId.from_str("BTCUSDT-PERP.BINANCE"),
        client_order_id=ClientOrderId(client_order_id),
        account_id=AccountId("BINANCE-001"),
        reason="fixture rejection",
        event_id=UUID4(),
        ts_event=observed_ns,
        ts_init=observed_ns,
    )


def _gateway(profile: str, *, protection_accepted: bool) -> HistoricalEpisodeGateway:
    gateway = object.__new__(HistoricalEpisodeGateway)
    gateway.rejections = []
    gateway.unhandled_rejections = []
    gateway.protection_gap_at = None
    gateway.protection_gap_exit_submitted_at = None
    gateway.protection_order_id = "PROTECTION-001"
    gateway.accepted_order_ids = (
        {gateway.protection_order_id} if protection_accepted else set()
    )
    gateway.order_profiles = {"REJECTED-001": profile}

    def submit_gap_exit(
        self: HistoricalEpisodeGateway,
        observed_at: datetime,
    ) -> None:
        self.protection_gap_exit_submitted_at = observed_at

    gateway._submit_protection_gap_exit = MethodType(submit_gap_exit, gateway)
    return gateway


def test_take_profit_rejection_is_visible_but_handled_when_protection_is_accepted() -> None:
    gateway = _gateway("TAKE_PROFIT_1", protection_accepted=True)

    gateway.event_sink(_rejected_event("REJECTED-001"))

    assert len(gateway.rejections) == 1
    assert gateway.unhandled_rejections == []
    assert gateway.protection_gap_at is None
    assert gateway.protection_gap_exit_submitted_at is None


def test_protection_rejection_submits_gap_exit_at_the_observed_event_time() -> None:
    gateway = _gateway("PROTECTIVE_STOP_REDUCE_ONLY", protection_accepted=False)

    gateway.event_sink(_rejected_event("REJECTED-001"))

    assert len(gateway.rejections) == 1
    assert gateway.unhandled_rejections == []
    assert gateway.protection_gap_at == datetime(2024, 7, 15, 19, 28, tzinfo=UTC)
    assert gateway.protection_gap_exit_submitted_at == gateway.protection_gap_at


def test_other_rejection_remains_unhandled() -> None:
    gateway = _gateway("ENTRY_LIMIT", protection_accepted=False)

    gateway.event_sink(_rejected_event("REJECTED-001"))

    assert gateway.unhandled_rejections == gateway.rejections


def test_synchronous_protection_gap_exit_stops_take_profit_creation(
    monkeypatch,
) -> None:
    observed_at = datetime(2024, 7, 15, 19, 28, tzinfo=UTC)
    observed_ns = int(observed_at.timestamp() * 1_000_000_000)
    gateway = object.__new__(HistoricalEpisodeGateway)
    gateway.proposal = SimpleNamespace(
        entry_risk_context=SimpleNamespace(model_dump=lambda **_: {})
    )
    gateway.activation = object()
    gateway.entry_order_id = "ENTRY-001"
    gateway.protection_gap_exit_submitted_at = None
    take_profit_calls: list[object] = []

    monkeypatch.setattr(
        historical_backtest,
        "record_first_fill",
        lambda activation, **_: activation,
    )
    monkeypatch.setattr(
        historical_backtest,
        "proposed_protection_from_fill",
        lambda *_, **__: SimpleNamespace(
            action_profile="PROTECTIVE_STOP_REDUCE_ONLY",
            quantity="0.010",
            trigger_price="63432.30",
        ),
    )
    monkeypatch.setattr(
        historical_backtest,
        "proposed_take_profits_from_fill",
        lambda *args, **kwargs: take_profit_calls.append((args, kwargs)),
    )

    def submit_exit(
        self: HistoricalEpisodeGateway,
        **_: object,
    ) -> str:
        self.protection_gap_exit_submitted_at = observed_at
        return "PROTECTION-001"

    gateway._submit_exit_action = MethodType(submit_exit, gateway)

    gateway._submit_initial_protection_and_targets(
        SimpleNamespace(
            ts_event=observed_ns,
            trade_id="TRADE-001",
            last_px="63431.60",
            last_qty="0.010",
        )
    )

    assert gateway.protection_order_id == "PROTECTION-001"
    assert take_profit_calls == []
