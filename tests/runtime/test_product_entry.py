from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from types import SimpleNamespace

import pytest
from pydantic import SecretStr
from nautilus_trader.model.data import Bar
from nautilus_trader.model.objects import Price, Quantity

from halpha.capital.models import AuthorityClass, EnvironmentKind
from halpha.domain_values import content_digest
import halpha.executor.product_entry as product_entry_module
from halpha.position_attribution import AccountInstrumentAttribution
from halpha.executor.product_entry import (
    LiveEntryFactTracker,
    ProductAccountFacts,
    ProductPreSubmitRejected,
    ProductPreSubmitFactProvider,
    ProductProposalBoundary,
    _account_margin_state,
    _conservative_entry_price,
    _query_current_mark_price,
    _require_supported_account_mode,
    _require_flat_entry_scope,
    instrument_rules_payload,
    _venue_query_failure_reason,
)
from halpha.planning.models import PlanActivation, PlanLifecycle, PositionAlignmentSpec
from halpha.planning.order_policies import InitialStopSpec, ProtectionPolicy
from halpha.planning.order_schedule import (
    AmountDistribution,
    BinancePriceMatch,
    InstrumentOrderRules,
    OrderScheduleSpec,
    SinglePrice,
    VenueOrderPolicy,
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
    VenueFactKind,
    VenueFactSourceClass,
)
from halpha.venue_integration.nautilus_account import query_single_asset_mode


NOW = datetime(2026, 7, 18, 6, 0, tzinfo=UTC)
DIRECT_CHECKED_AT = NOW + timedelta(minutes=1)


def test_venue_query_failure_reason_exposes_only_numeric_diagnostics() -> None:
    error = RuntimeError("secret-bearing venue message")
    error.status = 401  # type: ignore[attr-defined]
    error.message = {  # type: ignore[attr-defined]
        "code": -2015,
        "msg": "Invalid API-key, IP, or permissions",
    }

    reason = _venue_query_failure_reason("ACCOUNT_FACT_QUERY_FAILED", error)

    assert reason == "ACCOUNT_FACT_QUERY_FAILED_RUNTIMEERROR_HTTP_401_CODE_-2015"
    assert "secret" not in reason.lower()
    assert "invalid" not in reason.lower()


def test_pre_submit_provider_shares_binance_retry_after_across_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_monotonic = [10.0]
    provider = ProductPreSubmitFactProvider(
        node=SimpleNamespace(),
        profile="BINANCE_DEMO",
        api_key=SecretStr("qualification-key"),
        api_secret=SecretStr("qualification-secret"),
        proxy_url=None,
        monotonic_clock=lambda: observed_monotonic[0],
    )
    calls = [0]

    async def rate_limited(_activation):
        calls[0] += 1
        raise ProductPreSubmitRejected(
            "ACCOUNT_FACT_QUERY_FAILED_BINANCECLIENTERROR_HTTP_429",
            retry_after_seconds=90.0,
        )

    monkeypatch.setattr(provider, "_load_risk_reduction_facts", rate_limited)

    with pytest.raises(ProductPreSubmitRejected, match="HTTP_429"):
        asyncio.run(provider.risk_reduction_facts(SimpleNamespace()))
    observed_monotonic[0] = 50.0
    with pytest.raises(
        ProductPreSubmitRejected,
        match="BINANCE_RATE_LIMIT_BACKOFF",
    ) as captured:
        asyncio.run(provider.risk_reduction_facts(SimpleNamespace()))

    assert captured.value.retry_after_seconds == 50.0
    assert calls == [1]


def test_pre_submit_provider_does_not_hide_internal_failure_as_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = ProductPreSubmitFactProvider(
        node=SimpleNamespace(),
        profile="BINANCE_DEMO",
        api_key=SecretStr("qualification-key"),
        api_secret=SecretStr("qualification-secret"),
        proxy_url=None,
    )

    async def broken_loader(_activation):
        raise RuntimeError("private implementation failure")

    monkeypatch.setattr(provider, "_load_risk_reduction_facts", broken_loader)

    with pytest.raises(RuntimeError, match="private implementation failure"):
        asyncio.run(provider.risk_reduction_facts(SimpleNamespace()))


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


def _proposal_with_source_identity(source_identity: str) -> StrategyProposal:
    fields = _proposal().model_dump(mode="python")
    fields.pop("proposal_digest")
    fields["source_identity"] = source_identity
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


def _direct_rules(
    source: str = "BINANCE_DEMO_EXCHANGE_INFO",
) -> InstrumentOrderRules:
    return InstrumentOrderRules(
        source=source,
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


def _direct_activation(
    *,
    rules_source: str = "BINANCE_DEMO_EXCHANGE_INFO",
    environment_kind: EnvironmentKind = EnvironmentKind.DEMO,
    price_match: BinancePriceMatch | None = None,
) -> PlanActivation:
    snapshot = compile_order_schedule(
        OrderScheduleSpec(
            price_distribution=SinglePrice(
                limit_price=None if price_match is not None else "100"
            ),
            amount_distribution=AmountDistribution(base_notional="10"),
            venue_policy=VenueOrderPolicy(price_match=price_match),
            protection_policy=ProtectionPolicy(
                initial_stop=InitialStopSpec(distance_bps="100")
            ),
        ),
        _direct_rules(rules_source),
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
        environment_id=(
            "demo-main" if environment_kind is EnvironmentKind.DEMO else "live-main"
        ),
        environment_kind=environment_kind,
        authority_class=(
            AuthorityClass.DEMO_VALIDATION
            if environment_kind is EnvironmentKind.DEMO
            else AuthorityClass.LIVE_REAL_CAPITAL
        ),
        plan_version_ref="plan-version-direct-entry",
        account_ref=(
            "demo-owner" if environment_kind is EnvironmentKind.DEMO else "live-owner"
        ),
        instrument_ref="BTCUSDT-PERP",
        direction=Direction.LONG,
        decision_basis_ref=DIRECT_EXECUTION_REF,
        framework_strategy_id="HALPHA-INTERNAL-001",
        order_schedule_snapshot=snapshot,
        target_exposure="100",
        rule_state={
            "deadlines": {"entry_valid_until": (NOW + timedelta(hours=1)).isoformat()}
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
    price_match: BinancePriceMatch | None = None,
    hedge_mode: bool = False,
    position_side: str = "BOTH",
    opposite_position_amount: str | None = None,
) -> tuple[ProductPreSubmitFactProvider, PlanActivation, MaterializedOrderLeg]:
    activation = _direct_activation(price_match=price_match)
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
            positionSide=position_side,
            notional=str(abs(Decimal(position_amount)) * Decimal("100")),
            markPrice="100",
        ),
        SimpleNamespace(
            symbol="ETHUSDT",
            positionAmt="2",
            positionSide="BOTH",
            notional="200",
            markPrice="100",
        ),
    ]
    if opposite_position_amount is not None:
        opposite_side = "SHORT" if position_side == "LONG" else "LONG"
        positions.append(
            SimpleNamespace(
                symbol=symbol,
                positionAmt=opposite_position_amount,
                positionSide=opposite_side,
                notional=str(
                    abs(Decimal(opposite_position_amount)) * Decimal("100")
                ),
                markPrice="100",
            )
        )
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
                    marginType="ISOLATED",
                    leverage="5",
                    isAutoAddMargin=False,
                )
            ]

        async def query_futures_hedge_mode(self, **_kwargs):
            return SimpleNamespace(dualSidePosition=hedge_mode)

        async def query_futures_position_risk(self, **_kwargs):
            return positions

        async def query_open_orders(self, **kwargs):
            requested_symbol = kwargs.get("symbol")
            orders = [
                SimpleNamespace(
                    clientOrderId=client_order_id,
                    symbol=(
                        "ETHUSDT" if client_order_id.endswith("-eth") else symbol
                    ),
                )
                for client_order_id in open_order_ids
            ]
            return [
                item
                for item in orders
                if requested_symbol is None or item.symbol == requested_symbol
            ]

        async def query_open_algo_orders(self, **kwargs):
            requested_symbol = kwargs.get("symbol")
            orders = [
                SimpleNamespace(
                    clientAlgoId=client_algo_id,
                    symbol=(
                        "ETHUSDT" if client_algo_id.endswith("-eth") else symbol
                    ),
                )
                for client_algo_id in open_algo_ids
            ]
            return [
                item
                for item in orders
                if requested_symbol is None or item.symbol == requested_symbol
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


def _run_direct_pre_submit_facts(
    provider: ProductPreSubmitFactProvider,
    activation: PlanActivation,
    leg: MaterializedOrderLeg,
    *,
    owned_order_client_ids: frozenset[str] = frozenset({"owned-order"}),
    owned_algo_client_ids: frozenset[str] = frozenset({"owned-algo"}),
    expected_signed_position: str = "0.2",
) -> ProductAccountFacts:
    return asyncio.run(
        provider.direct_pre_submit_facts(
            activation,
            leg,
            owned_order_client_ids=owned_order_client_ids,
            owned_algo_client_ids=owned_algo_client_ids,
            expected_signed_position=expected_signed_position,
            outstanding_entry_quantity="0.3",
            outstanding_entry_notional="30",
        )
    )


def test_direct_pre_submit_facts_accept_no_expiry_and_return_complete_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, activation, leg = _direct_fact_case(
        monkeypatch,
        valid_until=None,
    )

    facts = _run_direct_pre_submit_facts(provider, activation, leg)

    assert facts.checked_at == DIRECT_CHECKED_AT
    assert facts.conservative_price == "100"
    assert facts.activation_current_notional == "50.2"
    assert facts.account_current_notional == "250"
    assert facts.activation_current_margin == "10.04"
    assert facts.current_abs_position == "0.2"
    assert facts.post_action_abs_position == "0.6"
    action_check = facts.direct_action_check(
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


def test_direct_pre_submit_facts_use_live_price_for_price_match_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, activation, leg = _direct_fact_case(
        monkeypatch,
        price_match=BinancePriceMatch.OPPONENT,
    )

    facts = _run_direct_pre_submit_facts(provider, activation, leg)

    assert facts.conservative_price == "101"
    assert facts.activation_current_notional == "50.2"


def test_direct_pre_submit_facts_accept_other_halpha_plan_orders_and_use_target_position(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, activation, leg = _direct_fact_case(
        monkeypatch,
        position_amount="0.3",
        open_order_ids=("owned-order", "other-plan-order"),
        open_algo_ids=("owned-algo", "other-plan-algo"),
    )
    attribution = AccountInstrumentAttribution(
        environment_id=activation.environment_id,
        account_ref=activation.account_ref,
        instrument_ref=activation.instrument_ref,
        activation_id=activation.activation_id,
        activation_signed_position="0.2",
        account_signed_position="0.3",
        account_outstanding_entry_notional="70",
        activation_ordinary_client_ids=frozenset({"owned-order"}),
        activation_algo_client_ids=frozenset({"owned-algo"}),
        account_ordinary_client_ids=frozenset(
            {"owned-order", "other-plan-order"}
        ),
        account_algo_client_ids=frozenset(
            {"owned-algo", "other-plan-algo"}
        ),
        activation_fill_fact_refs=("target-fill",),
        account_fill_fact_refs=("target-fill", "other-fill"),
    )
    provider._attribution_provider = lambda _activation_id: attribution

    facts = _run_direct_pre_submit_facts(provider, activation, leg)

    assert facts.current_abs_position == "0.2"
    assert facts.activation_current_notional == "50.2"
    assert facts.account_current_notional == "300"
    assert facts.post_action_abs_position == "0.6"


def test_risk_reduction_facts_return_only_target_plan_order_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, activation, _leg = _direct_fact_case(
        monkeypatch,
        position_amount="0.3",
        open_order_ids=("owned-order", "other-plan-order"),
        open_algo_ids=("owned-algo", "other-plan-algo"),
    )
    attribution = AccountInstrumentAttribution(
        environment_id=activation.environment_id,
        account_ref=activation.account_ref,
        instrument_ref=activation.instrument_ref,
        activation_id=activation.activation_id,
        activation_signed_position="0.2",
        account_signed_position="0.3",
        account_outstanding_entry_notional="0",
        activation_ordinary_client_ids=frozenset({"owned-order"}),
        activation_algo_client_ids=frozenset({"owned-algo"}),
        account_ordinary_client_ids=frozenset(
            {"owned-order", "other-plan-order"}
        ),
        account_algo_client_ids=frozenset(
            {"owned-algo", "other-plan-algo"}
        ),
        activation_fill_fact_refs=("target-fill",),
        account_fill_fact_refs=("target-fill", "other-fill"),
    )
    provider._attribution_provider = lambda _activation_id: attribution

    facts = asyncio.run(provider.risk_reduction_facts(activation))

    assert facts.current_abs_position == "0.2"
    assert facts.open_order_client_ids == ("owned-order",)
    assert facts.open_algo_client_ids == ("owned-algo",)
    assert facts.position_fact.payload["position_quantity"] == "0.3"
    assert facts.position_fact.payload["activation_id"] == activation.activation_id
    assert facts.position_fact.payload["activation_position_quantity"] == "0.2"
    assert (
        facts.position_fact.payload["attributed_account_position_quantity"]
        == "0.3"
    )


def test_risk_reduction_treats_missing_target_position_row_as_flat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, activation, _leg = _direct_fact_case(
        monkeypatch,
        open_order_ids=(),
        open_algo_ids=(),
    )
    account_api = provider._account_api(object())

    async def flat_account_positions(**_kwargs):
        # Binance /fapi/v3/positionRisk returns no target row after the final
        # reducer fill.  The account-wide response is still complete.
        return []

    account_api.query_futures_position_risk = flat_account_positions
    monkeypatch.setattr(provider, "_account_api", lambda _client: account_api)
    provider._attribution_provider = lambda _activation_id: (
        AccountInstrumentAttribution(
            environment_id=activation.environment_id,
            account_ref=activation.account_ref,
            instrument_ref=activation.instrument_ref,
            activation_id=activation.activation_id,
            activation_signed_position="0",
            account_signed_position="0",
            account_outstanding_entry_notional="0",
            activation_ordinary_client_ids=frozenset(),
            activation_algo_client_ids=frozenset(),
            account_ordinary_client_ids=frozenset(),
            account_algo_client_ids=frozenset(),
            activation_fill_fact_refs=("entry-fill", "exit-fill"),
            account_fill_fact_refs=("entry-fill", "exit-fill"),
        )
    )

    facts = asyncio.run(provider.risk_reduction_facts(activation))

    assert facts.current_abs_position == "0"
    assert facts.position_fact is not None
    assert facts.position_fact.payload["position_quantity"] == "0"
    assert facts.position_fact.payload["activation_position_quantity"] == "0"
    assert facts.position_fact.payload["account_open_position_symbols"] == []


def test_risk_reduction_discards_attribution_changed_during_signed_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, activation, _leg = _direct_fact_case(
        monkeypatch,
        position_amount="0",
        open_order_ids=(),
        open_algo_ids=(),
    )
    before_fill = AccountInstrumentAttribution(
        environment_id=activation.environment_id,
        account_ref=activation.account_ref,
        instrument_ref=activation.instrument_ref,
        activation_id=activation.activation_id,
        activation_signed_position="0.01",
        account_signed_position="0.01",
        account_outstanding_entry_notional="0",
        activation_ordinary_client_ids=frozenset({"exit-order"}),
        activation_algo_client_ids=frozenset(),
        account_ordinary_client_ids=frozenset({"exit-order"}),
        account_algo_client_ids=frozenset(),
        activation_fill_fact_refs=("entry-fill",),
        account_fill_fact_refs=("entry-fill",),
    )
    after_fill = replace(
        before_fill,
        activation_signed_position="0",
        account_signed_position="0",
        activation_fill_fact_refs=("entry-fill", "exit-fill"),
        account_fill_fact_refs=("entry-fill", "exit-fill"),
    )
    snapshots = iter((before_fill, after_fill))
    provider._attribution_provider = lambda _activation_id: next(snapshots)

    with pytest.raises(ProductPreSubmitRejected, match="ACCOUNT_FACT_SUPERSEDED"):
        asyncio.run(provider.risk_reduction_facts(activation))


def test_symbol_position_for_side_still_rejects_duplicate_target_rows() -> None:
    positions = [
        SimpleNamespace(
            symbol="BTCUSDT",
            positionSide="BOTH",
            positionAmt="0",
        ),
        SimpleNamespace(
            symbol="BTCUSDT",
            positionSide="BOTH",
            positionAmt="0",
        ),
    ]

    with pytest.raises(ProductPreSubmitRejected, match="POSITION_FACT_INVALID"):
        product_entry_module._symbol_position_for_side(
            symbol="BTCUSDT",
            positions=positions,
            position_side="BOTH",
        )


def _position_alignment_activation(
    activation: PlanActivation,
    *,
    position_side: str = "BOTH",
) -> PlanActivation:
    payload = activation.model_dump(mode="python")
    payload.update(
        {
            "order_schedule_snapshot": None,
            "position_alignment": PositionAlignmentSpec(
                operation="REDUCE",
                snapshot_ref="account-snapshot-1",
                fact_cutoff=NOW,
                account_ref=activation.account_ref,
                venue_ref="BINANCE_USDM",
                instrument_ref=activation.instrument_ref,
                direction=activation.direction,
                position_side=position_side,
                baseline_quantity="0.3",
                requested_reduction_quantity="0.2",
                target_quantity_after="0.1",
                baseline_entry_price="90",
                baseline_mark_price="100",
            ),
            "lifecycle": PlanLifecycle.EXITING,
            "entry_opportunity_consumed": True,
        }
    )
    return PlanActivation.model_validate(payload)


def test_position_alignment_risk_reduction_uses_external_baseline_without_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, direct_activation, _leg = _direct_fact_case(
        monkeypatch,
        position_amount="0.3",
        open_order_ids=(),
        open_algo_ids=(),
    )
    activation = _position_alignment_activation(direct_activation)
    attribution = AccountInstrumentAttribution(
        environment_id=activation.environment_id,
        account_ref=activation.account_ref,
        instrument_ref=activation.instrument_ref,
        activation_id=activation.activation_id,
        activation_signed_position="0.2",
        account_signed_position="0",
        account_outstanding_entry_notional="0",
        activation_ordinary_client_ids=frozenset(),
        activation_algo_client_ids=frozenset(),
        account_ordinary_client_ids=frozenset(),
        account_algo_client_ids=frozenset(),
        activation_fill_fact_refs=(),
        account_fill_fact_refs=(),
    )
    provider._attribution_provider = lambda _activation_id: attribution

    facts = asyncio.run(provider.risk_reduction_facts(activation))

    assert facts.current_abs_position == "0.2"
    assert facts.position_fact.payload["position_quantity"] == "0.3"
    assert facts.position_fact.payload["activation_position_quantity"] == "0.2"
    assert facts.position_fact.payload["attributed_account_position_quantity"] == "0.3"


def test_position_alignment_hedge_mode_reads_only_the_fixed_long_side(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, direct_activation, _leg = _direct_fact_case(
        monkeypatch,
        position_amount="0.3",
        open_order_ids=(),
        open_algo_ids=(),
        hedge_mode=True,
        position_side="LONG",
        opposite_position_amount="-0.4",
    )
    activation = _position_alignment_activation(
        direct_activation,
        position_side="LONG",
    )
    attribution = AccountInstrumentAttribution(
        environment_id=activation.environment_id,
        account_ref=activation.account_ref,
        instrument_ref=activation.instrument_ref,
        activation_id=activation.activation_id,
        activation_signed_position="0.2",
        account_signed_position="0",
        account_outstanding_entry_notional="0",
        activation_ordinary_client_ids=frozenset(),
        activation_algo_client_ids=frozenset(),
        account_ordinary_client_ids=frozenset(),
        account_algo_client_ids=frozenset(),
        activation_fill_fact_refs=(),
        account_fill_fact_refs=(),
    )
    provider._attribution_provider = lambda _activation_id: attribution

    facts = asyncio.run(provider.risk_reduction_facts(activation))

    assert facts.current_abs_position == "0.2"
    assert facts.position_fact is not None
    assert facts.position_fact.payload["position_side"] == "LONG"
    assert facts.position_fact.payload["account_position_mode"] == "HEDGE"
    assert facts.position_fact.payload["position_quantity"] == "0.3"
    assert facts.position_fact.payload["attributed_account_position_quantity"] == "0.3"


def test_position_alignment_rejects_account_drift_before_submission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, direct_activation, _leg = _direct_fact_case(
        monkeypatch,
        position_amount="0.31",
        open_order_ids=(),
        open_algo_ids=(),
    )
    activation = _position_alignment_activation(direct_activation)
    attribution = AccountInstrumentAttribution(
        environment_id=activation.environment_id,
        account_ref=activation.account_ref,
        instrument_ref=activation.instrument_ref,
        activation_id=activation.activation_id,
        activation_signed_position="0.2",
        account_signed_position="0",
        account_outstanding_entry_notional="0",
        activation_ordinary_client_ids=frozenset(),
        activation_algo_client_ids=frozenset(),
        account_ordinary_client_ids=frozenset(),
        account_algo_client_ids=frozenset(),
        activation_fill_fact_refs=(),
        account_fill_fact_refs=(),
    )
    provider._attribution_provider = lambda _activation_id: attribution

    with pytest.raises(ProductPreSubmitRejected, match="POSITION_ALIGNMENT_DRIFT"):
        asyncio.run(provider.risk_reduction_facts(activation))


def test_risk_reduction_uses_symbol_orders_and_full_account_positions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, activation, _leg = _direct_fact_case(
        monkeypatch,
        open_order_ids=("ordinary-btc", "ordinary-eth"),
        open_algo_ids=("algo-btc", "algo-eth"),
    )
    account_api = provider._account_api(object())
    ordinary_calls: list[dict[str, object]] = []
    algo_calls: list[dict[str, object]] = []
    query_open_orders = account_api.query_open_orders
    query_open_algo_orders = account_api.query_open_algo_orders

    async def recorded_open_orders(**kwargs):
        ordinary_calls.append(kwargs)
        return await query_open_orders(**kwargs)

    async def recorded_open_algo_orders(**kwargs):
        algo_calls.append(kwargs)
        return await query_open_algo_orders(**kwargs)

    account_api.query_open_orders = recorded_open_orders
    account_api.query_open_algo_orders = recorded_open_algo_orders
    monkeypatch.setattr(provider, "_account_api", lambda _client: account_api)

    facts = asyncio.run(provider.risk_reduction_facts(activation))

    assert ordinary_calls == [{"symbol": "BTCUSDT", "recv_window": "5000"}]
    assert algo_calls == [{"symbol": "BTCUSDT", "recv_window": "5000"}]
    assert facts.account_current_notional == "220"
    assert facts.open_order_client_ids == ("ordinary-btc",)
    assert facts.open_algo_client_ids == ("algo-btc",)
    assert facts.position_fact.payload["account_current_notional"] == "220"
    assert facts.position_fact.payload[
        "account_open_position_symbols"
    ] == ["BTCUSDT", "ETHUSDT"]
    assert facts.position_fact.payload[
        "instrument_open_order_client_ids"
    ] == ["ordinary-btc"]
    assert facts.position_fact.payload[
        "instrument_open_algo_client_ids"
    ] == ["algo-btc"]


def test_risk_reduction_reuses_bounded_account_mode_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, activation, _leg = _direct_fact_case(
        monkeypatch,
        open_order_ids=(),
        open_algo_ids=(),
    )
    account_api = provider._account_api(object())
    hedge_mode_queries = [0]
    original_query = account_api.query_futures_hedge_mode
    observed_monotonic = [10.0]

    async def recorded_hedge_mode(**kwargs):
        hedge_mode_queries[0] += 1
        return await original_query(**kwargs)

    account_api.query_futures_hedge_mode = recorded_hedge_mode
    monkeypatch.setattr(provider, "_account_api", lambda _client: account_api)
    provider._monotonic_clock = lambda: observed_monotonic[0]

    async def exercise_cache() -> None:
        await provider.risk_reduction_facts(activation)
        await provider.risk_reduction_facts(activation)
        observed_monotonic[0] = 41.0
        await provider.risk_reduction_facts(activation)

    asyncio.run(exercise_cache())

    assert hedge_mode_queries == [2]


def test_called_algo_action_recovery_follows_actual_order_and_trade_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, activation, _leg = _direct_fact_case(monkeypatch)
    client_order_id = "a" * 32
    calls: list[tuple[str, dict[str, object]]] = []

    class AccountAPI:
        async def query_algo_order(self, **kwargs):
            calls.append(("algo", kwargs))
            return SimpleNamespace(
                algoId=71,
                clientAlgoId=client_order_id,
                algoStatus="FINISHED",
                actualOrderId="81",
                quantity="0.001",
                updateTime=int(DIRECT_CHECKED_AT.timestamp() * 1000),
            )

        async def query_order(self, **kwargs):
            calls.append(("order", kwargs))
            return SimpleNamespace(
                orderId=81,
                status="FILLED",
                executedQty="0.001",
                origQty="0.001",
                updateTime=int(DIRECT_CHECKED_AT.timestamp() * 1000),
                side="SELL",
            )

        async def query_user_trades(self, **kwargs):
            calls.append(("trades", kwargs))
            return [
                SimpleNamespace(
                    id=91,
                    qty="0.001",
                    price="100",
                    time=int(DIRECT_CHECKED_AT.timestamp() * 1000),
                    side="SELL",
                    maker=False,
                    commission="0.04",
                    commissionAsset="USDT",
                )
            ]

    monkeypatch.setattr(provider, "_account_api", lambda _client: AccountAPI())
    action_terms = {
        "instrument_ref": activation.instrument_ref,
        "quantity": "0.001",
    }
    action = SimpleNamespace(
        execution_action_id="protection-action",
        environment_id=activation.environment_id,
        account_ref=activation.account_ref,
        activation_id=activation.activation_id,
        action_kind=ExecutionActionKind.PROTECTION,
        action_terms=action_terms,
        action_terms_digest=content_digest(action_terms),
        client_order_id=client_order_id,
        cancel_target=None,
    )

    facts = asyncio.run(provider.called_action_recovery_facts(action))

    assert [fact.kind for fact in facts] == [
        VenueFactKind.ORDER_STATE,
        VenueFactKind.FILL,
        VenueFactKind.COMMISSION,
    ]
    assert all(fact.action_ref == "protection-action" for fact in facts)
    assert all(
        fact.source_class is VenueFactSourceClass.VENUE_QUERY for fact in facts
    )
    assert facts[0].payload["status"] == "FILLED"
    assert facts[1].payload["trade_id"] == "91"
    assert facts[1].payload["client_order_id"] == client_order_id
    assert facts[1].payload["last_quantity"] == "0.001"
    assert calls == [
        (
            "algo",
            {"client_algo_id": client_order_id, "recv_window": "5000"},
        ),
        (
            "order",
            {"symbol": "BTCUSDT", "order_id": 81, "recv_window": "5000"},
        ),
        (
            "trades",
            {"symbol": "BTCUSDT", "order_id": 81, "recv_window": "5000"},
        ),
    ]


def test_direct_pre_submit_facts_reject_an_expired_leg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, activation, leg = _direct_fact_case(
        monkeypatch,
        valid_until=DIRECT_CHECKED_AT,
    )

    with pytest.raises(ProductPreSubmitRejected) as exc_info:
        _run_direct_pre_submit_facts(provider, activation, leg)

    assert exc_info.value.reason_code == "DIRECT_ENTRY_EXPIRED"


def test_direct_pre_submit_facts_reject_instrument_rule_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, activation, leg = _direct_fact_case(
        monkeypatch,
        current_tick_size="0.2",
    )

    with pytest.raises(ProductPreSubmitRejected) as exc_info:
        _run_direct_pre_submit_facts(provider, activation, leg)

    assert exc_info.value.reason_code == "INSTRUMENT_RULES_DRIFT"


@pytest.mark.parametrize(
    ("profile", "environment_kind", "rules_source"),
    [
        (
            "BINANCE_LIVE_WRITE",
            EnvironmentKind.LIVE,
            "BINANCE_DEMO_EXCHANGE_INFO",
        ),
        (
            "BINANCE_DEMO",
            EnvironmentKind.DEMO,
            "BINANCE_LIVE_EXCHANGE_INFO",
        ),
    ],
)
def test_direct_pre_submit_facts_reject_cross_environment_rules_before_query(
    monkeypatch: pytest.MonkeyPatch,
    profile: str,
    environment_kind: EnvironmentKind,
    rules_source: str,
) -> None:
    activation = _direct_activation(
        rules_source=rules_source,
        environment_kind=environment_kind,
    )
    leg = materialize_direct_schedule(
        activation,
        entry_valid_until=NOW + timedelta(hours=1),
    )[0]
    provider = ProductPreSubmitFactProvider(
        node=SimpleNamespace(kernel=SimpleNamespace(clock=object())),
        profile=profile,
        api_key=SecretStr("key"),
        api_secret=SecretStr("secret"),
        proxy_url=None,
    )
    query_calls = 0

    def forbidden_client():
        nonlocal query_calls
        query_calls += 1
        raise AssertionError("cross-environment snapshot must fail before query")

    monkeypatch.setattr(provider, "_binance_client", forbidden_client)

    with pytest.raises(ProductPreSubmitRejected) as exc_info:
        _run_direct_pre_submit_facts(
            provider,
            activation,
            leg,
            owned_order_client_ids=frozenset(),
            owned_algo_client_ids=frozenset(),
            expected_signed_position="0",
        )

    assert exc_info.value.reason_code == "INSTRUMENT_RULES_SOURCE_ENVIRONMENT_MISMATCH"
    assert query_calls == 0


@pytest.mark.parametrize(
    ("open_order_ids", "open_algo_ids", "owned_order_ids", "owned_algo_ids"),
    [
        (("foreign-order",), (), frozenset({"owned-order"}), frozenset()),
        ((), ("foreign-algo",), frozenset(), frozenset({"owned-algo"})),
    ],
)
def test_direct_pre_submit_facts_reject_unowned_open_ids(
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
        _run_direct_pre_submit_facts(
            provider,
            activation,
            leg,
            owned_order_client_ids=owned_order_ids,
            owned_algo_client_ids=owned_algo_ids,
        )

    assert exc_info.value.reason_code == "ENTRY_OPEN_ORDER_CONFLICT"


def test_direct_pre_submit_facts_require_the_expected_signed_position(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, activation, leg = _direct_fact_case(monkeypatch)

    with pytest.raises(ProductPreSubmitRejected) as exc_info:
        _run_direct_pre_submit_facts(
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

    mark, observed_at = asyncio.run(_query_current_mark_price(Client(), "BTCUSDT"))

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


@pytest.mark.parametrize(
    ("margin_type", "leverage", "auto_add_margin"),
    (
        ("CROSSED", "5", False),
        ("ISOLATED", "5", True),
    ),
)
def test_new_risk_supports_crossed_and_isolated_symbol_configuration(
    margin_type: str,
    leverage: str,
    auto_add_margin: bool,
) -> None:
    account = SimpleNamespace(canTrade=True)
    symbol_configs = (
        SimpleNamespace(
            symbol="BTCUSDT",
            marginType=margin_type,
            leverage=leverage,
            isAutoAddMargin=auto_add_margin,
        ),
    )

    margin_mode, actual_leverage, effective = _account_margin_state(
        account,
        symbol_configs,
        "BTCUSDT",
    )
    assert margin_mode == margin_type
    assert actual_leverage == leverage
    assert effective == min(Decimal(leverage), Decimal("5"))


def test_isolated_high_leverage_keeps_conservative_five_x_arithmetic() -> None:
    margin_mode, actual_leverage, effective = _account_margin_state(
        SimpleNamespace(canTrade=True),
        (
            SimpleNamespace(
                symbol="BTCUSDT",
                marginType="ISOLATED",
                leverage="20",
                isAutoAddMargin=False,
            ),
        ),
        "BTCUSDT",
    )

    assert margin_mode == "ISOLATED"
    assert actual_leverage == "20"
    assert effective == Decimal("5")


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

    assert (
        tracker.conservative_reference(
            "BTCUSDT-PERP.BINANCE",
            Direction.LONG,
            cutoff_ns=cutoff,
        )
        == "50002"
    )

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


def test_stream_tracker_does_not_regress_to_out_of_order_market_facts() -> None:
    tracker = LiveEntryFactTracker()
    cutoff = int(NOW.timestamp() * 1_000_000_000)
    tracker.record_quote(
        SimpleNamespace(
            instrument_id="BTCUSDT-PERP.BINANCE",
            bid_price="50099",
            ask_price="50101",
            ts_event=cutoff - 1_000_000_000,
            ts_init=cutoff - 500_000_000,
        )
    )
    tracker.record_mark(
        SimpleNamespace(
            instrument_id="BTCUSDT-PERP.BINANCE",
            value="50102",
            ts_event=cutoff - 1_000_000_000,
            ts_init=cutoff - 250_000_000,
        )
    )
    tracker.record_quote(
        SimpleNamespace(
            instrument_id="BTCUSDT-PERP.BINANCE",
            bid_price="100",
            ask_price="101",
            ts_event=cutoff - 2_000_000_000,
        )
    )
    tracker.record_mark(
        SimpleNamespace(
            instrument_id="BTCUSDT-PERP.BINANCE",
            value="100",
            ts_event=cutoff - 2_000_000_000,
        )
    )

    facts = tracker.direct_condition_facts(
        "BTCUSDT-PERP.BINANCE",
        cutoff_ns=cutoff,
        observed_at=NOW,
        activated_at=NOW - timedelta(seconds=60),
        price_move_bps_by_window={},
        market_source="BINANCE_DEMO_PUBLIC",
    )

    assert facts.bid_price == "50099"
    assert facts.ask_price == "50101"
    assert facts.mark_price == "50102"
    assert facts.provenance is not None
    assert facts.provenance.source == "BINANCE_DEMO_PUBLIC"
    assert facts.provenance.source_cutoff == NOW
    assert facts.provenance.quote_source_time == NOW - timedelta(seconds=1)
    assert facts.provenance.quote_received_at == NOW - timedelta(milliseconds=500)
    assert facts.provenance.mark_source_time == NOW - timedelta(seconds=1)
    assert facts.provenance.mark_received_at == NOW - timedelta(milliseconds=250)


def test_direct_condition_facts_allow_brief_mark_gap_but_not_stale_book() -> None:
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
            ts_event=cutoff - 1_000_000_000,
        )
    )

    fresh = tracker.direct_condition_facts(
        "BTCUSDT-PERP.BINANCE",
        cutoff_ns=cutoff,
        observed_at=NOW,
        activated_at=NOW - timedelta(seconds=60),
        price_move_bps_by_window={5: "12"},
        market_source="BINANCE_DEMO_PUBLIC",
    )
    brief_gap = tracker.direct_condition_facts(
        "BTCUSDT-PERP.BINANCE",
        cutoff_ns=cutoff + 4_000_000_000,
        observed_at=NOW + timedelta(seconds=4),
        activated_at=NOW - timedelta(seconds=60),
        price_move_bps_by_window={},
        market_source="BINANCE_DEMO_PUBLIC",
    )
    stale = tracker.direct_condition_facts(
        "BTCUSDT-PERP.BINANCE",
        cutoff_ns=cutoff + 11_000_000_000,
        observed_at=NOW + timedelta(seconds=11),
        activated_at=NOW - timedelta(seconds=60),
        price_move_bps_by_window={},
        market_source="BINANCE_DEMO_PUBLIC",
    )

    assert fresh.mark_price == "50002"
    assert fresh.bid_price == "49999"
    assert fresh.ask_price == "50001"
    assert fresh.price_move_bps_by_window == {5: "12"}
    assert fresh.elapsed_seconds == 60
    assert brief_gap.mark_price == "50002"
    assert brief_gap.bid_price is None
    assert brief_gap.ask_price is None
    assert brief_gap.elapsed_seconds == 64
    assert stale.mark_price is None
    assert stale.bid_price is None
    assert stale.ask_price is None
    assert stale.elapsed_seconds == 71


def test_closed_15m_bar_fact_warms_and_fails_closed_at_the_next_boundary() -> None:
    tracker = LiveEntryFactTracker("BTCUSDT-PERP")
    target = tracker.target_bar_type
    first_close_at = datetime(2026, 8, 1, 6, 0, tzinfo=UTC)

    def bar(close_at: datetime, close: str) -> Bar:
        timestamp = int(close_at.timestamp() * 1_000_000_000)
        return Bar(
            bar_type=target,
            open=Price.from_str(close),
            high=Price.from_str(close),
            low=Price.from_str(close),
            close=Price.from_str(close),
            volume=Quantity.from_str("1"),
            ts_event=timestamp,
            ts_init=timestamp + 1_000_000,
        )

    assert tracker.try_warm_from_cached_bars(
        target_bars=(bar(first_close_at, "62960.5"),),
    )
    observed_at = first_close_at + timedelta(minutes=7)
    cutoff_ns = int(observed_at.timestamp() * 1_000_000_000)
    fresh = tracker.direct_condition_facts(
        "BTCUSDT-PERP.BINANCE",
        cutoff_ns=cutoff_ns,
        observed_at=observed_at,
        activated_at=first_close_at - timedelta(minutes=1),
        price_move_bps_by_window={},
        market_source="BINANCE_DEMO_PUBLIC",
    )

    assert fresh.closed_bar_15m_close == "62960.5"
    assert fresh.closed_bar_15m_at == first_close_at

    next_close_at = first_close_at + timedelta(minutes=15)
    before_next_bar_arrives = tracker.direct_condition_facts(
        "BTCUSDT-PERP.BINANCE",
        cutoff_ns=int((next_close_at + timedelta(seconds=1)).timestamp() * 1e9),
        observed_at=next_close_at + timedelta(seconds=1),
        activated_at=first_close_at - timedelta(minutes=1),
        price_move_bps_by_window={},
        market_source="BINANCE_DEMO_PUBLIC",
    )
    assert before_next_bar_arrives.closed_bar_15m_close is None
    assert before_next_bar_arrives.closed_bar_15m_at is None

    tracker.accept(bar(next_close_at, "62940"))
    after_next_bar_arrives = tracker.direct_condition_facts(
        "BTCUSDT-PERP.BINANCE",
        cutoff_ns=int((next_close_at + timedelta(seconds=1)).timestamp() * 1e9),
        observed_at=next_close_at + timedelta(seconds=1),
        activated_at=first_close_at - timedelta(minutes=1),
        price_move_bps_by_window={},
        market_source="BINANCE_DEMO_PUBLIC",
    )
    assert after_next_bar_arrives.closed_bar_15m_close == "62940"
    assert after_next_bar_arrives.closed_bar_15m_at == next_close_at


def test_entry_extension_price_is_conservative_in_both_directions() -> None:
    assert (
        _conservative_entry_price(
            Direction.LONG,
            mark=Decimal("50002"),
            bid=Decimal("49999"),
            ask=Decimal("50001"),
        )
        == "50002"
    )
    assert (
        _conservative_entry_price(
            Direction.SHORT,
            mark=Decimal("49998"),
            bid=Decimal("49999"),
            ask=Decimal("50001"),
        )
        == "49998"
    )


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

    assert (
        tracker.conservative_reference(
            "BTCUSDT-PERP.BINANCE",
            Direction.LONG,
            cutoff_ns=cutoff,
            max_age_ns=15_000_000_000,
        )
        == "50002"
    )


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


def test_product_proposal_processor_enters_cap_and_exe_once_with_stable_identity() -> (
    None
):
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


def test_product_proposal_processor_keeps_only_bounded_completed_identities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> tuple[ProductProposalBoundary, FakeCoordinator]:
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
        for index in range(3):
            processor.submit(
                _proposal_with_source_identity(f"activation-product-entry:BAR:{index}")
            )
        await processor.wait_idle()
        await asyncio.sleep(0)
        return processor, coordinator

    monkeypatch.setattr(product_entry_module, "COMPLETED_PROPOSAL_KEY_LIMIT", 2)
    processor, coordinator = asyncio.run(scenario())

    assert processor._tasks == {}
    assert len(processor._completed) == 2
    assert len(coordinator.consumed) == 3
    processor.close()


def test_product_proposal_failure_uses_structured_sink_without_default_handler() -> (
    None
):
    async def scenario() -> tuple[list[str], list[dict[str, object]]]:
        failures: list[str] = []
        loop_contexts: list[dict[str, object]] = []
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(
            lambda _loop, context: loop_contexts.append(context)
        )

        async def provider(_proposal):
            raise RuntimeError("private diagnostic detail")

        processor = ProductProposalBoundary(
            loop=loop,
            coordinator=FakeCoordinator(),
            fact_provider=provider,
            environment_id="demo-main",
            environment_kind=EnvironmentKind.DEMO,
            authority_class=AuthorityClass.DEMO_VALIDATION,
            account_ref="demo-owner",
            failure_sink=lambda exception: failures.append(type(exception).__name__),
        )
        processor.submit(_proposal())
        with pytest.raises(RuntimeError, match="private diagnostic detail"):
            await processor.wait_idle()
        await asyncio.sleep(0)
        processor.close()
        return failures, loop_contexts

    failures, loop_contexts = asyncio.run(scenario())

    assert failures == ["RuntimeError"]
    assert loop_contexts == []


def test_product_proposal_failure_sink_error_is_sanitized() -> None:
    async def scenario() -> list[dict[str, object]]:
        loop_contexts: list[dict[str, object]] = []
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(
            lambda _loop, context: loop_contexts.append(context)
        )

        async def provider(_proposal):
            raise RuntimeError("private original diagnostic")

        def failed_sink(_exception: BaseException) -> None:
            raise RuntimeError("private sink diagnostic")

        processor = ProductProposalBoundary(
            loop=loop,
            coordinator=FakeCoordinator(),
            fact_provider=provider,
            environment_id="demo-main",
            environment_kind=EnvironmentKind.DEMO,
            authority_class=AuthorityClass.DEMO_VALIDATION,
            account_ref="demo-owner",
            failure_sink=failed_sink,
        )
        processor.submit(_proposal())
        with pytest.raises(RuntimeError, match="private original diagnostic"):
            await processor.wait_idle()
        await asyncio.sleep(0)
        processor.close()
        return loop_contexts

    loop_contexts = asyncio.run(scenario())

    assert len(loop_contexts) == 1
    assert (
        loop_contexts[0]["message"]
        == "HALPHA_PRODUCT_PROPOSAL_FAILURE_SINK_FAILED"
    )
    assert loop_contexts[0]["exception_type"] == "RuntimeError"
    assert "exception" not in loop_contexts[0]
    assert "task" not in loop_contexts[0]


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


def test_product_proposal_processor_rejects_ready_action_when_second_check_fails() -> (
    None
):
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
