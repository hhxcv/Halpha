from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from types import SimpleNamespace

import pytest
from nautilus_trader.adapters.binance.http.error import BinanceClientError
from pydantic import SecretStr

from halpha.capital.models import AuthorityClass, EnvironmentKind
from halpha.domain_values import content_digest
import halpha.executor.product_entry as product_entry_module
from halpha.executor.product_entry import (
    DirectScheduleFacts,
    LiveEntryFactTracker,
    ProductAccountFacts,
    ProductPreSubmitRejected,
    ProductPreSubmitFactProvider,
    ProductProposalBoundary,
    _conservative_entry_price,
    _query_current_mark_price,
    _require_supported_account_mode,
    _require_flat_entry_scope,
    instrument_rules_payload,
)
from halpha.planning.models import PlanActivation
from halpha.planning.order_policies import InitialStopSpec, ProtectionPolicy
from halpha.planning.order_schedule import (
    AmountDistribution,
    InstrumentOrderRules,
    OrderScheduleSpec,
    SinglePrice,
    compile_order_schedule,
)
from halpha.planning.order_schedule_actions import (
    MaterializedOrderLeg,
    materialize_direct_schedule,
)
from halpha.planning.registry import DIRECT_EXECUTION_REF, Direction
from halpha.planning.strategies.one_shot import (
    EntryRiskContext,
    RiskDirection,
    StrategyProposal,
)
from halpha.venue_integration.models import (
    ExecutionActionKind,
    ExecutionActionState,
)
from halpha.venue_integration.nautilus_account import query_single_asset_mode


NOW = datetime(2026, 7, 18, 6, 0, tzinfo=UTC)
DIRECT_CHECKED_AT = NOW + timedelta(minutes=1)


def _proposal() -> StrategyProposal:
    rules = {
        "step_size": "0.001",
        "price_tick_size": "0.1",
        "min_quantity": "0.001",
        "max_market_quantity": "100",
        "min_notional": "5",
    }
    fields = {
        "strategy_id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT",
        "activation_id": "activation-product-entry",
        "rule_id": "ENTRY_BREAKOUT",
        "source_identity": "activation-product-entry:BAR:1:2",
        "source_cutoff": NOW,
        "input_digest": "1" * 64,
        "instrument_id": "BTCUSDT-PERP.BINANCE",
        "direction": Direction.LONG,
        "action_profile": "ENTRY_MARKET",
        "risk_direction": RiskDirection.INCREASE,
        "quantity": "0.002",
        "reference_price": "50000",
        "reference_source": "BINANCE_MARK_AND_TOP_OF_BOOK_ASK",
        "reason_code": "ENTRY_BREAKOUT_CONFIRMED",
        "valid_until": NOW + timedelta(minutes=1),
        "entry_risk_context": EntryRiskContext(
            trigger_atr="500",
            initial_stop_atr_multiple="1.5",
            take_profit_1_r="1.5",
            take_profit_1_fraction="0.5",
            take_profit_2_r="3",
            max_hold_bars_15m=96,
            indicator_source_digest="2" * 64,
            indicator_source_cutoff_ns=int(NOW.timestamp() * 1_000_000_000),
            quantity_step="0.001",
            price_tick_size="0.1",
            entry_extension_boundary="50500",
            sizing_taker_fee_rate="0.0006",
            sizing_effective_leverage="5",
            instrument_rules_digest=content_digest(rules),
        ),
    }
    return StrategyProposal(
        **fields,
        proposal_digest=content_digest(fields),
    )


def _proposal_with_input_digest(input_digest: str) -> StrategyProposal:
    fields = _proposal().model_dump(mode="python")
    fields.pop("proposal_digest")
    fields["input_digest"] = input_digest
    return StrategyProposal(
        **fields,
        proposal_digest=content_digest(fields),
    )


def _facts() -> ProductAccountFacts:
    return ProductAccountFacts(
        checked_at=datetime.now(UTC),
        conservative_price="50010",
        available_margin="1000",
        actual_margin_mode="CROSSED",
        actual_leverage="20",
        activation_current_notional="0",
        account_current_notional="0",
        activation_current_margin="0",
        current_abs_position="0",
        post_action_abs_position="0.002",
    )


def _direct_rules() -> InstrumentOrderRules:
    return InstrumentOrderRules(
        source="BINANCE_DEMO_EXCHANGE_INFO",
        min_price="0.1",
        max_price="1000000",
        price_tick_size="0.1",
        limit_quantity_step="0.01",
        min_limit_quantity="0.01",
        max_limit_quantity="1000",
        market_quantity_step="0.1",
        min_market_quantity="0.1",
        max_market_quantity="100",
        min_notional="5",
        source_cutoff=NOW.isoformat(),
    )


def _direct_activation() -> PlanActivation:
    snapshot = compile_order_schedule(
        OrderScheduleSpec(
            price_distribution=SinglePrice(limit_price="100"),
            amount_distribution=AmountDistribution(base_notional="10"),
            protection_policy=ProtectionPolicy(
                initial_stop=InitialStopSpec(distance_bps="100")
            ),
        ),
        _direct_rules(),
        venue_ref="BINANCE_USDM",
        instrument_ref="BTCUSDT-PERP",
        direction=Direction.LONG,
        max_notional="100",
        schedule_ref="plan-version-direct-entry",
        reference_price="100",
    )
    assert snapshot.valid
    return PlanActivation(
        activation_id="activation-direct-entry",
        environment_id="demo-main",
        environment_kind=EnvironmentKind.DEMO,
        authority_class=AuthorityClass.DEMO_VALIDATION,
        plan_version_ref="plan-version-direct-entry",
        account_ref="demo-owner",
        instrument_ref="BTCUSDT-PERP",
        direction=Direction.LONG,
        decision_basis_ref=DIRECT_EXECUTION_REF,
        framework_strategy_id="HALPHA-INTERNAL-001",
        order_schedule_snapshot=snapshot,
        target_exposure="100",
        rule_state={
            "deadlines": {
                "entry_valid_until": (NOW + timedelta(hours=1)).isoformat()
            }
        },
        created_at=NOW,
        updated_at=NOW,
    )


def _direct_fact_case(
    monkeypatch: pytest.MonkeyPatch,
    *,
    valid_until: datetime | None = NOW + timedelta(hours=1),
    current_tick_size: str = "0.1",
    position_amount: str = "0.2",
    open_order_ids: tuple[str, ...] = ("owned-order",),
    open_algo_ids: tuple[str, ...] = ("owned-algo",),
) -> tuple[ProductPreSubmitFactProvider, PlanActivation, MaterializedOrderLeg]:
    activation = _direct_activation()
    leg = materialize_direct_schedule(
        activation,
        entry_valid_until=NOW + timedelta(hours=1),
    )[0]
    leg = leg.model_copy(
        update={
            "proposed_action": leg.proposed_action.model_copy(
                update={"valid_until": valid_until}
            )
        }
    )
    symbol = "BTCUSDT"
    positions = [
        SimpleNamespace(
            symbol=symbol,
            positionAmt=position_amount,
            notional=str(abs(Decimal(position_amount)) * Decimal("100")),
            markPrice="100",
        ),
        SimpleNamespace(
            symbol="ETHUSDT",
            positionAmt="2",
            notional="200",
            markPrice="100",
        ),
    ]
    exchange_info = SimpleNamespace(
        serverTime=int(DIRECT_CHECKED_AT.timestamp() * 1000),
        symbols=[
            SimpleNamespace(
                symbol=symbol,
                filters=[
                    {
                        "filterType": "PRICE_FILTER",
                        "minPrice": "0.1",
                        "maxPrice": "1000000",
                        "tickSize": current_tick_size,
                    },
                    {
                        "filterType": "LOT_SIZE",
                        "stepSize": "0.01",
                        "minQty": "0.01",
                        "maxQty": "1000",
                    },
                    {
                        "filterType": "MARKET_LOT_SIZE",
                        "stepSize": "0.1",
                        "minQty": "0.1",
                        "maxQty": "100",
                    },
                    {"filterType": "MIN_NOTIONAL", "notional": "5"},
                ],
            )
        ],
    )

    class AccountAPI:
        async def query_futures_account_info(self, **_kwargs):
            return SimpleNamespace(
                canTrade=True,
                availableBalance="1000",
                assets=[],
            )

        async def query_futures_symbol_config(self, **_kwargs):
            return [
                SimpleNamespace(
                    symbol=symbol,
                    marginType="CROSSED",
                    leverage="5",
                )
            ]

        async def query_futures_hedge_mode(self, **_kwargs):
            return SimpleNamespace(dualSidePosition=False)

        async def query_futures_position_risk(self, **_kwargs):
            return positions

        async def query_open_orders(self, **_kwargs):
            return [
                SimpleNamespace(clientOrderId=client_order_id)
                for client_order_id in open_order_ids
            ]

        async def query_open_algo_orders(self, **_kwargs):
            return [
                SimpleNamespace(clientAlgoId=client_algo_id)
                for client_algo_id in open_algo_ids
            ]

    class MarketAPI:
        async def query_futures_exchange_info(self):
            return exchange_info

        async def query_ticker_book(self, **_kwargs):
            return [
                SimpleNamespace(
                    symbol=symbol,
                    bidPrice="99",
                    askPrice="101",
                )
            ]

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return DIRECT_CHECKED_AT.replace(tzinfo=None)
            return DIRECT_CHECKED_AT.astimezone(tz)

    async def single_asset_mode(*_args, **_kwargs):
        return True

    async def current_mark_price(*_args, **_kwargs):
        return Decimal("100"), DIRECT_CHECKED_AT

    provider = ProductPreSubmitFactProvider(
        node=SimpleNamespace(kernel=SimpleNamespace(clock=object())),
        profile="BINANCE_DEMO",
        api_key=SecretStr("key"),
        api_secret=SecretStr("secret"),
        proxy_url=None,
    )
    client = object()
    monkeypatch.setattr(provider, "_binance_client", lambda: client)
    monkeypatch.setattr(provider, "_account_api", lambda _client: AccountAPI())
    monkeypatch.setattr(provider, "_market_api", lambda _client: MarketAPI())
    monkeypatch.setattr(product_entry_module, "datetime", FrozenDateTime)
    monkeypatch.setattr(
        product_entry_module,
        "query_single_asset_mode",
        single_asset_mode,
    )
    monkeypatch.setattr(
        product_entry_module,
        "_query_current_mark_price",
        current_mark_price,
    )
    return provider, activation, leg


def _run_direct_facts(
    provider: ProductPreSubmitFactProvider,
    activation: PlanActivation,
    leg: MaterializedOrderLeg,
    *,
    owned_order_client_ids: frozenset[str] = frozenset({"owned-order"}),
    owned_algo_client_ids: frozenset[str] = frozenset({"owned-algo"}),
    expected_signed_position: str = "0.2",
) -> DirectScheduleFacts:
    return asyncio.run(
        provider.direct_entry_facts(
            activation,
            leg,
            owned_order_client_ids=owned_order_client_ids,
            owned_algo_client_ids=owned_algo_client_ids,
            expected_signed_position=expected_signed_position,
            outstanding_entry_quantity="0.3",
            outstanding_entry_notional="30",
            price_move_bps_by_window={5: "-12.5"},
        )
    )


def test_direct_entry_facts_accepts_no_expiry_and_returns_complete_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, activation, leg = _direct_fact_case(
        monkeypatch,
        valid_until=None,
    )

    facts = _run_direct_facts(provider, activation, leg)

    assert facts.account.checked_at == DIRECT_CHECKED_AT
    assert facts.account.conservative_price == "101"
    assert facts.account.activation_current_notional == "50.2"
    assert facts.account.account_current_notional == "250"
    assert facts.account.activation_current_margin == "10.04"
    assert facts.account.current_abs_position == "0.2"
    assert facts.account.post_action_abs_position == "0.6"
    assert facts.conditions.basis_ready is True
    assert facts.conditions.mark_price == "100"
    assert facts.conditions.bid_price == "99"
    assert facts.conditions.ask_price == "101"
    assert facts.conditions.price_move_bps_by_window == {5: "-12.5"}
    assert facts.conditions.elapsed_seconds == 60

    action_check = facts.account.direct_action_check(
        leg.proposed_action,
        activation_id=activation.activation_id,
        economic_action_prior_notional="7",
        environment_id=activation.environment_id,
        environment_kind=activation.environment_kind,
        authority_class=activation.authority_class,
        account_ref=activation.account_ref,
    )
    assert action_check.quantized_quantity == "0.1"
    assert action_check.economic_action_prior_notional == "7"
    assert action_check.activation_current_notional == "50.2"
    assert action_check.account_current_notional == "250"


def test_direct_entry_facts_rejects_an_expired_leg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, activation, leg = _direct_fact_case(
        monkeypatch,
        valid_until=DIRECT_CHECKED_AT,
    )

    with pytest.raises(ProductPreSubmitRejected) as exc_info:
        _run_direct_facts(provider, activation, leg)

    assert exc_info.value.reason_code == "DIRECT_ENTRY_EXPIRED"


def test_direct_entry_facts_rejects_instrument_rule_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, activation, leg = _direct_fact_case(
        monkeypatch,
        current_tick_size="0.2",
    )

    with pytest.raises(ProductPreSubmitRejected) as exc_info:
        _run_direct_facts(provider, activation, leg)

    assert exc_info.value.reason_code == "INSTRUMENT_RULES_DRIFT"


@pytest.mark.parametrize(
    ("open_order_ids", "open_algo_ids", "owned_order_ids", "owned_algo_ids"),
    [
        (("foreign-order",), (), frozenset({"owned-order"}), frozenset()),
        ((), ("foreign-algo",), frozenset(), frozenset({"owned-algo"})),
    ],
)
def test_direct_entry_facts_rejects_unowned_open_ids(
    monkeypatch: pytest.MonkeyPatch,
    open_order_ids: tuple[str, ...],
    open_algo_ids: tuple[str, ...],
    owned_order_ids: frozenset[str],
    owned_algo_ids: frozenset[str],
) -> None:
    provider, activation, leg = _direct_fact_case(
        monkeypatch,
        open_order_ids=open_order_ids,
        open_algo_ids=open_algo_ids,
    )

    with pytest.raises(ProductPreSubmitRejected) as exc_info:
        _run_direct_facts(
            provider,
            activation,
            leg,
            owned_order_client_ids=owned_order_ids,
            owned_algo_client_ids=owned_algo_ids,
        )

    assert exc_info.value.reason_code == "ENTRY_OPEN_ORDER_CONFLICT"


def test_direct_entry_facts_requires_the_expected_signed_position(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, activation, leg = _direct_fact_case(monkeypatch)

    with pytest.raises(ProductPreSubmitRejected) as exc_info:
        _run_direct_facts(
            provider,
            activation,
            leg,
            expected_signed_position="0.1",
        )

    assert exc_info.value.reason_code == "POSITION_ATTRIBUTION_UNKNOWN"


def test_product_market_rules_use_the_execution_profile_filters() -> None:
    instrument = SimpleNamespace(
        size_increment="0.0001",
        max_quantity="1000",
        info={
            "filters": [
                {
                    "filterType": "PRICE_FILTER",
                    "minPrice": "0.10",
                    "maxPrice": "1000000.00",
                    "tickSize": "0.10",
                },
                {
                    "filterType": "LOT_SIZE",
                    "stepSize": "0.0001",
                    "minQty": "0.0001",
                    "maxQty": "1000",
                },
                {
                    "filterType": "MARKET_LOT_SIZE",
                    "stepSize": "0.001",
                    "minQty": "0.001",
                    "maxQty": "100",
                },
                {
                    "filterType": "MIN_NOTIONAL",
                    "notional": "5.0",
                },
            ]
        },
    )

    assert instrument_rules_payload(instrument) == {
        "step_size": "0.001",
        "price_tick_size": "0.1",
        "min_quantity": "0.001",
        "max_market_quantity": "100",
        "min_notional": "5",
    }


def test_current_mark_query_requires_the_requested_symbol_and_positive_value() -> None:
    class Client:
        async def send_request(self, **kwargs):
            assert kwargs["url_path"] == "/fapi/v1/premiumIndex"
            assert kwargs["payload"] == {"symbol": "BTCUSDT"}
            return json.dumps(
                {
                    "symbol": "BTCUSDT",
                    "markPrice": "50000.10",
                    "time": 1_784_357_200_000,
                }
            ).encode()

    mark, observed_at = asyncio.run(
        _query_current_mark_price(Client(), "BTCUSDT")
    )

    assert mark == Decimal("50000.10")
    assert int(observed_at.timestamp() * 1000) == 1_784_357_200_000


def test_single_asset_mode_uses_the_shared_nautilus_signed_client() -> None:
    class Clock:
        def timestamp_ms(self) -> int:
            return 1_784_357_200_000

    class Client:
        async def sign_request(self, **kwargs):
            assert kwargs["url_path"] == "/fapi/v1/multiAssetsMargin"
            assert kwargs["payload"] == {
                "timestamp": "1784357200000",
                "recvWindow": "5000",
            }
            return b'{"multiAssetsMargin":false}'

    assert asyncio.run(query_single_asset_mode(Client(), Clock())) is True


@pytest.mark.parametrize(
    ("dual_side", "single_asset", "reason_code"),
    (
        (True, True, "ACCOUNT_POSITION_MODE_UNSUPPORTED"),
        (False, False, "ACCOUNT_MULTI_ASSET_MODE_UNSUPPORTED"),
    ),
)
def test_unsupported_account_modes_fail_closed(
    dual_side: bool,
    single_asset: bool,
    reason_code: str,
) -> None:
    with pytest.raises(ProductPreSubmitRejected, match=reason_code):
        _require_supported_account_mode(
            SimpleNamespace(dualSidePosition=dual_side),
            single_asset_mode=single_asset,
        )


def test_old_unknown_entry_is_closed_only_on_exact_binance_absence(
    monkeypatch,
) -> None:
    class AccountApi:
        def __init__(self, *_args):
            pass

        async def query_order(self, **values):
            assert values == {
                "symbol": "BTCUSDT",
                "orig_client_order_id": "a" * 32,
                "recv_window": "5000",
            }
            raise BinanceClientError(
                400,
                {"code": -2013, "msg": "Order does not exist."},
                {},
            )

    monkeypatch.setattr(
        product_entry_module,
        "get_cached_binance_http_client",
        lambda **_values: object(),
    )
    monkeypatch.setattr(
        product_entry_module,
        "BinanceFuturesAccountHttpAPI",
        AccountApi,
    )
    provider = ProductPreSubmitFactProvider(
        node=SimpleNamespace(kernel=SimpleNamespace(clock=object())),
        profile="BINANCE_DEMO",
        api_key=SecretStr("demo-key"),
        api_secret=SecretStr("demo-secret"),
        proxy_url=None,
    )
    action = SimpleNamespace(
        action_kind=ExecutionActionKind.ENTRY,
        state=ExecutionActionState.UNKNOWN,
        client_order_id="a" * 32,
        call_started_at=datetime.now(UTC) - timedelta(minutes=2),
        action_terms={"instrument_ref": "BTCUSDT-PERP"},
    )

    assert asyncio.run(provider.entry_order_is_definitely_absent(action)) is True


def test_recent_unknown_entry_is_not_declared_absent_without_query(monkeypatch) -> None:
    monkeypatch.setattr(
        product_entry_module,
        "get_cached_binance_http_client",
        lambda **_values: pytest.fail("recent unknown must not be queried as absent"),
    )
    provider = ProductPreSubmitFactProvider(
        node=SimpleNamespace(kernel=SimpleNamespace(clock=object())),
        profile="BINANCE_DEMO",
        api_key=SecretStr("demo-key"),
        api_secret=SecretStr("demo-secret"),
        proxy_url=None,
    )
    action = SimpleNamespace(
        action_kind=ExecutionActionKind.ENTRY,
        state=ExecutionActionState.UNKNOWN,
        client_order_id="a" * 32,
        call_started_at=datetime.now(UTC) - timedelta(seconds=5),
        action_terms={"instrument_ref": "BTCUSDT-PERP"},
    )

    assert asyncio.run(provider.entry_order_is_definitely_absent(action)) is False


@pytest.mark.parametrize(
    ("positions", "open_orders", "open_algo_orders", "reason_code"),
    (
        (
            [SimpleNamespace(symbol="BTCUSDT", positionAmt="0.001")],
            [],
            [],
            "ENTRY_POSITION_NOT_FLAT",
        ),
        ([], [SimpleNamespace(symbol="BTCUSDT")], [], "ENTRY_OPEN_ORDER_CONFLICT"),
        (
            [],
            [],
            [SimpleNamespace(symbol="BTCUSDT")],
            "ENTRY_OPEN_ALGO_ORDER_CONFLICT",
        ),
    ),
)
def test_first_entry_rejects_existing_instrument_responsibility(
    positions,
    open_orders,
    open_algo_orders,
    reason_code,
) -> None:
    with pytest.raises(ProductPreSubmitRejected, match=reason_code):
        _require_flat_entry_scope(
            symbol="BTCUSDT",
            positions=positions,
            open_orders=open_orders,
            open_algo_orders=open_algo_orders,
        )


def test_first_entry_accepts_zero_positions_without_open_orders() -> None:
    assert _require_flat_entry_scope(
        symbol="BTCUSDT",
        positions=[
            SimpleNamespace(symbol="BTCUSDT", positionAmt="0"),
            SimpleNamespace(symbol="ETHUSDT", positionAmt="1"),
        ],
        open_orders=[],
        open_algo_orders=[],
    ) == Decimal("0")


class FakeCoordinator:
    def __init__(self) -> None:
        self.rejections: list[dict[str, object]] = []
        self.consumed: list[dict[str, object]] = []
        self.processed: list[tuple[str, dict[str, object]]] = []
        self.rejected_actions: list[str] = []

    def record_strategy_proposal_rejection(self, **kwargs):
        self.rejections.append(kwargs)

    def consume_strategy_proposal(self, **kwargs):
        self.consumed.append(kwargs)
        return SimpleNamespace(
            execution_action=SimpleNamespace(state=ExecutionActionState.READY)
        )

    def process_execution_action(self, execution_action_id: str, **kwargs):
        self.processed.append((execution_action_id, kwargs))

    def reject_execution_action_before_submission(
        self,
        execution_action_id: str,
        **kwargs,
    ):
        self.rejected_actions.append((execution_action_id, kwargs["reason_code"]))


def test_stream_tracker_uses_one_fresh_quote_and_mark_snapshot() -> None:
    tracker = LiveEntryFactTracker()
    cutoff = int(NOW.timestamp() * 1_000_000_000)
    tracker.record_quote(
        SimpleNamespace(
            instrument_id="BTCUSDT-PERP.BINANCE",
            bid_price="49999",
            ask_price="50001",
            ts_event=cutoff - 1_000_000_000,
        )
    )
    tracker.record_mark(
        SimpleNamespace(
            instrument_id="BTCUSDT-PERP.BINANCE",
            value="50002",
            ts_event=cutoff - 2_000_000_000,
        )
    )

    assert tracker.conservative_reference(
        "BTCUSDT-PERP.BINANCE",
        Direction.LONG,
        cutoff_ns=cutoff,
    ) == "50002"

    try:
        tracker.conservative_reference(
            "BTCUSDT-PERP.BINANCE",
            Direction.LONG,
            cutoff_ns=cutoff + 4_000_000_000,
        )
    except ProductPreSubmitRejected as exc:
        assert exc.reason_code == "STREAM_FACTS_STALE"
    else:
        raise AssertionError("stale stream facts must fail closed")


def test_entry_extension_price_is_conservative_in_both_directions() -> None:
    assert _conservative_entry_price(
        Direction.LONG,
        mark=Decimal("50002"),
        bid=Decimal("49999"),
        ask=Decimal("50001"),
    ) == "50002"
    assert _conservative_entry_price(
        Direction.SHORT,
        mark=Decimal("49998"),
        bid=Decimal("49999"),
        ask=Decimal("50001"),
    ) == "49998"


def test_preliminary_sizing_allows_a_short_unchanged_quote_window() -> None:
    tracker = LiveEntryFactTracker()
    cutoff = int(NOW.timestamp() * 1_000_000_000)
    tracker.record_quote(
        SimpleNamespace(
            instrument_id="BTCUSDT-PERP.BINANCE",
            bid_price="49999",
            ask_price="50001",
            ts_event=cutoff - 10_000_000_000,
        )
    )
    tracker.record_mark(
        SimpleNamespace(
            instrument_id="BTCUSDT-PERP.BINANCE",
            value="50002",
            ts_event=cutoff - 1_000_000_000,
        )
    )

    assert tracker.conservative_reference(
        "BTCUSDT-PERP.BINANCE",
        Direction.LONG,
        cutoff_ns=cutoff,
        max_age_ns=15_000_000_000,
    ) == "50002"


def test_stream_tracker_rejects_spread_above_sizing_assumption() -> None:
    tracker = LiveEntryFactTracker()
    cutoff = int(NOW.timestamp() * 1_000_000_000)
    tracker.record_quote(
        SimpleNamespace(
            instrument_id="BTCUSDT-PERP.BINANCE",
            bid_price="49950",
            ask_price="50050.1",
            ts_event=cutoff - 1_000_000_000,
        )
    )
    tracker.record_mark(
        SimpleNamespace(
            instrument_id="BTCUSDT-PERP.BINANCE",
            value="50000",
            ts_event=cutoff - 1_000_000_000,
        )
    )

    with pytest.raises(
        ProductPreSubmitRejected,
        match="ENTRY_SPREAD_TOO_WIDE",
    ):
        tracker.conservative_reference(
            "BTCUSDT-PERP.BINANCE",
            Direction.LONG,
            cutoff_ns=cutoff,
        )


def test_product_proposal_processor_enters_cap_and_exe_once_with_stable_identity() -> None:
    async def scenario() -> FakeCoordinator:
        coordinator = FakeCoordinator()

        async def provider(_proposal):
            return _facts()

        processor = ProductProposalBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=provider,
            environment_id="demo-main",
            environment_kind=EnvironmentKind.DEMO,
            authority_class=AuthorityClass.DEMO_VALIDATION,
            account_ref="demo-owner",
        )
        processor.submit(_proposal())
        processor.submit(_proposal())
        await processor.wait_idle()
        processor.close()
        return coordinator

    coordinator = asyncio.run(scenario())
    assert coordinator.rejections == []
    assert len(coordinator.consumed) == 1
    assert len(coordinator.processed) == 1
    consumed = coordinator.consumed[0]
    action_id, processed = coordinator.processed[0]
    assert consumed["execution_action_id"] == action_id
    assert len(consumed["client_order_id"]) == 32
    assert processed["action_check"].environment_kind is EnvironmentKind.DEMO
    assert processed["request_payload"]["profile"] == "ENTRY_MARKET"


def test_product_proposal_processor_rejects_a_concurrent_source_conflict() -> None:
    async def scenario() -> FakeCoordinator:
        coordinator = FakeCoordinator()
        started = asyncio.Event()
        release = asyncio.Event()

        async def provider(_proposal):
            started.set()
            await release.wait()
            return _facts()

        processor = ProductProposalBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=provider,
            environment_id="demo-main",
            environment_kind=EnvironmentKind.DEMO,
            authority_class=AuthorityClass.DEMO_VALIDATION,
            account_ref="demo-owner",
        )
        processor.submit(_proposal())
        await started.wait()
        with pytest.raises(ProductPreSubmitRejected, match="SOURCE_IDENTITY_CONFLICT"):
            processor.submit(_proposal_with_input_digest("3" * 64))
        release.set()
        await processor.wait_idle()
        processor.close()
        return coordinator

    coordinator = asyncio.run(scenario())
    assert len(coordinator.consumed) == 1
    assert len(coordinator.processed) == 1


def test_product_proposal_processor_persists_fail_closed_fact_rejection() -> None:
    async def scenario() -> FakeCoordinator:
        coordinator = FakeCoordinator()

        async def provider(_proposal):
            raise ProductPreSubmitRejected("STREAM_FACTS_STALE")

        processor = ProductProposalBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=provider,
            environment_id="demo-main",
            environment_kind=EnvironmentKind.DEMO,
            authority_class=AuthorityClass.DEMO_VALIDATION,
            account_ref="demo-owner",
        )
        processor.submit(_proposal())
        await processor.wait_idle()
        processor.close()
        return coordinator

    coordinator = asyncio.run(scenario())
    assert coordinator.consumed == []
    assert coordinator.processed == []
    assert len(coordinator.rejections) == 1
    assert coordinator.rejections[0]["reason_code"] == "STREAM_FACTS_STALE"


def test_product_proposal_processor_rejects_ready_action_when_second_check_fails() -> None:
    async def scenario() -> FakeCoordinator:
        coordinator = FakeCoordinator()
        calls = 0

        async def provider(_proposal):
            nonlocal calls
            calls += 1
            if calls == 1:
                return _facts()
            raise ProductPreSubmitRejected("FRESH_FACTS_CHANGED")

        processor = ProductProposalBoundary(
            loop=asyncio.get_running_loop(),
            coordinator=coordinator,
            fact_provider=provider,
            environment_id="demo-main",
            environment_kind=EnvironmentKind.DEMO,
            authority_class=AuthorityClass.DEMO_VALIDATION,
            account_ref="demo-owner",
        )
        processor.submit(_proposal())
        await processor.wait_idle()
        processor.close()
        return coordinator

    coordinator = asyncio.run(scenario())
    assert len(coordinator.consumed) == 1
    assert coordinator.processed == []
    assert coordinator.rejected_actions == [
        (
            coordinator.consumed[0]["execution_action_id"],
            "FRESH_FACTS_CHANGED",
        )
    ]
