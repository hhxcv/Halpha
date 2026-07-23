"""Fail-closed live proposal orchestration for the single product execution path."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import json
from typing import Any, Protocol
from uuid import NAMESPACE_URL, uuid4, uuid5

from nautilus_trader.adapters.binance import (
    BinanceAccountType,
    get_cached_binance_http_client,
)
from nautilus_trader.adapters.binance.common.enums import (
    BinanceEnvironment,
    BinanceKeyType,
)
from nautilus_trader.adapters.binance.http.error import BinanceClientError
from nautilus_trader.adapters.binance.futures.http.account import (
    BinanceFuturesAccountHttpAPI,
)
from nautilus_trader.adapters.binance.futures.http.market import (
    BinanceFuturesMarketHttpAPI,
)
from nautilus_trader.adapters.binance.futures.http.wallet import (
    BinanceFuturesWalletHttpAPI,
)
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.core.nautilus_pyo3 import HttpMethod
from pydantic import SecretStr

from halpha.capital.checks import effective_leverage
from halpha.capital.models import (
    ActivationCapitalBoundary,
    ActionCheckInput,
    AuthorityClass,
    EnvironmentKind,
    RiskClass,
    StopCategory,
)
from halpha.domain_values import canonical_decimal, content_digest, decimal_from_string
from halpha.planning.bar_evaluation import EntrySizingSnapshot
from halpha.planning.models import PlanActivation, ProposedAction
from halpha.planning.order_policies import ConditionFacts
from halpha.planning.order_schedule import InstrumentOrderRules
from halpha.planning.order_schedule_actions import MaterializedOrderLeg
from halpha.planning.registry import Direction
from halpha.planning.strategies.one_shot import (
    InstrumentQuantityRules,
    StrategyProposal,
)
from halpha.venue_integration.facts import build_venue_fact
from halpha.venue_integration.binance_rules import (
    BinanceInstrumentRulesError,
    binance_exchange_symbol_rules,
    parse_binance_symbol_filters,
)
from halpha.venue_integration.models import (
    ExecutionAction,
    ExecutionActionKind,
    ExecutionActionState,
    VenueFactKind,
    VenueFactSourceClass,
)
from halpha.venue_integration.nautilus_account import (
    BinanceAccountContractError,
    query_single_asset_mode,
)

from .responsibilities import ProductRiskReductionFacts


MAX_STREAM_FACT_AGE_NS = 3_000_000_000
MAX_PRELIMINARY_STREAM_FACT_AGE_NS = 15_000_000_000
MAX_QUERY_WINDOW_SECONDS = Decimal("5")
MAX_SOURCE_BAR_AGE_SECONDS = Decimal("65")
ENTRY_ORDER_ABSENCE_DELAY_SECONDS = Decimal("60")
MARK_PRICE_PATH = "/fapi/v1/premiumIndex"


class ProductPreSubmitRejected(RuntimeError):
    """A stable, non-secret reason why one proposal cannot cross the write boundary."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class ProductCoordinatorPort(Protocol):
    def consume_strategy_proposal(self, **kwargs: Any) -> Any: ...

    def process_execution_action(self, execution_action_id: str, **kwargs: Any) -> Any: ...

    def record_strategy_proposal_rejection(self, **kwargs: Any) -> Any: ...

    def reject_execution_action_before_submission(
        self,
        execution_action_id: str,
        **kwargs: Any,
    ) -> Any: ...


@dataclass(frozen=True, slots=True)
class ProductAccountFacts:
    checked_at: datetime
    conservative_price: str
    available_margin: str
    actual_margin_mode: str
    actual_leverage: str
    activation_current_notional: str
    account_current_notional: str
    activation_current_margin: str
    current_abs_position: str
    post_action_abs_position: str

    def action_check(
        self,
        proposal: StrategyProposal,
        *,
        environment_id: str,
        environment_kind: EnvironmentKind,
        authority_class: AuthorityClass,
        account_ref: str,
    ) -> ActionCheckInput:
        return self.entry_action_check(
            activation_id=proposal.activation_id,
            instrument_ref=_instrument_ref(proposal.instrument_id),
            action_profile=proposal.action_profile,
            quantity=proposal.quantity,
            environment_id=environment_id,
            environment_kind=environment_kind,
            authority_class=authority_class,
            account_ref=account_ref,
        )

    def direct_action_check(
        self,
        proposed: ProposedAction,
        *,
        activation_id: str,
        economic_action_prior_notional: str,
        environment_id: str,
        environment_kind: EnvironmentKind,
        authority_class: AuthorityClass,
        account_ref: str,
    ) -> ActionCheckInput:
        if proposed.quantity is None:
            raise ProductPreSubmitRejected("DIRECT_ENTRY_QUANTITY_REQUIRED")
        return self.entry_action_check(
            activation_id=activation_id,
            instrument_ref=proposed.instrument_ref,
            action_profile=proposed.action_profile,
            quantity=proposed.quantity,
            economic_action_prior_notional=economic_action_prior_notional,
            environment_id=environment_id,
            environment_kind=environment_kind,
            authority_class=authority_class,
            account_ref=account_ref,
        )

    def cancel_action_check(
        self,
        activation: PlanActivation,
    ) -> ActionCheckInput:
        """Build a risk-neutral check for one direct-entry cancellation."""

        return ActionCheckInput(
            environment_id=activation.environment_id,
            environment_kind=activation.environment_kind,
            authority_class=activation.authority_class,
            activation_id=activation.activation_id,
            account_ref=activation.account_ref,
            instrument_ref=activation.instrument_ref,
            action_profile="CANCEL_ORDER",
            control_category=StopCategory.RISK_REDUCTION_OR_ORDER_MANAGEMENT,
            risk_class=RiskClass.RISK_NEUTRAL,
            checked_at=self.checked_at,
            quantized_quantity="0",
            conservative_price=self.conservative_price,
            activation_current_notional=self.activation_current_notional,
            account_current_notional=self.account_current_notional,
            activation_current_margin=self.activation_current_margin,
            account_dynamic_available_margin=self.available_margin,
            actual_margin_mode=self.actual_margin_mode,
            actual_leverage=self.actual_leverage,
            post_action_abs_position=self.current_abs_position,
            current_abs_position=self.current_abs_position,
            would_reverse_position=False,
            facts_fresh=True,
            attribution_unambiguous=True,
        )

    def entry_action_check(
        self,
        *,
        activation_id: str,
        instrument_ref: str,
        action_profile: str,
        quantity: str,
        economic_action_prior_notional: str = "0",
        environment_id: str,
        environment_kind: EnvironmentKind,
        authority_class: AuthorityClass,
        account_ref: str,
    ) -> ActionCheckInput:
        return ActionCheckInput(
            environment_id=environment_id,
            environment_kind=environment_kind,
            authority_class=authority_class,
            activation_id=activation_id,
            account_ref=account_ref,
            instrument_ref=instrument_ref,
            action_profile=action_profile,
            control_category=StopCategory.NEW_RISK,
            risk_class=RiskClass.RISK_INCREASING,
            checked_at=self.checked_at,
            quantized_quantity=quantity,
            conservative_price=self.conservative_price,
            economic_action_prior_notional=economic_action_prior_notional,
            activation_current_notional=self.activation_current_notional,
            account_current_notional=self.account_current_notional,
            activation_current_margin=self.activation_current_margin,
            account_dynamic_available_margin=self.available_margin,
            actual_margin_mode=self.actual_margin_mode,
            actual_leverage=self.actual_leverage,
            post_action_abs_position=self.post_action_abs_position,
            current_abs_position=self.current_abs_position,
            would_reverse_position=False,
            facts_fresh=True,
            attribution_unambiguous=True,
        )


@dataclass(frozen=True, slots=True)
class DirectScheduleFacts:
    account: ProductAccountFacts
    conditions: ConditionFacts


@dataclass(frozen=True, slots=True)
class _StreamValue:
    instrument_id: str
    value: Decimal
    ts_event: int


@dataclass(frozen=True, slots=True)
class _QuoteValue:
    instrument_id: str
    bid: Decimal
    ask: Decimal
    ts_event: int


MAX_ENTRY_SPREAD_BPS = Decimal("10")


def _conservative_entry_price(
    direction: Direction,
    *,
    mark: Decimal,
    bid: Decimal,
    ask: Decimal,
) -> str:
    book_price = ask if direction is Direction.LONG else bid
    value = (
        max(mark, book_price)
        if direction is Direction.LONG
        else min(mark, book_price)
    )
    return canonical_decimal(value)


def _account_margin_state(
    account_info: object,
    symbol_configs: object,
    symbol: str,
) -> tuple[str, str, Decimal]:
    if not bool(getattr(account_info, "canTrade", False)):
        raise ProductPreSubmitRejected("ACCOUNT_TRADING_DISABLED")
    symbol_config = next(
        (item for item in symbol_configs if item.symbol == symbol),
        None,
    )
    if symbol_config is None:
        raise ProductPreSubmitRejected("SYMBOL_CONFIGURATION_UNKNOWN")
    margin_mode = str(symbol_config.marginType).upper()
    leverage = canonical_decimal(Decimal(str(symbol_config.leverage)))
    try:
        current_effective = effective_leverage(margin_mode, leverage)
    except ValueError:
        raise ProductPreSubmitRejected("ACCOUNT_LEVERAGE_UNKNOWN") from None
    return margin_mode, leverage, current_effective


def _require_supported_account_mode(
    hedge_mode: object,
    *,
    single_asset_mode: bool,
) -> None:
    """Require the one-way/single-asset contract used by Halpha order profiles."""

    if bool(getattr(hedge_mode, "dualSidePosition", True)):
        raise ProductPreSubmitRejected("ACCOUNT_POSITION_MODE_UNSUPPORTED")
    if not single_asset_mode:
        raise ProductPreSubmitRejected("ACCOUNT_MULTI_ASSET_MODE_UNSUPPORTED")


def _top_of_book(book_tickers: object, symbol: str) -> tuple[Decimal, Decimal]:
    book = next(
        (item for item in book_tickers if item.symbol == symbol),
        None,
    )
    if book is None:
        raise ProductPreSubmitRejected("TOP_OF_BOOK_UNKNOWN")
    bid = Decimal(str(book.bidPrice))
    ask = Decimal(str(book.askPrice))
    if bid <= 0 or ask <= 0 or bid > ask:
        raise ProductPreSubmitRejected("TOP_OF_BOOK_INVALID")
    return bid, ask


def _fresh_mark(
    mark_snapshot: tuple[Decimal, datetime],
    checked_at: datetime,
) -> Decimal:
    mark, mark_time = mark_snapshot
    mark_age = Decimal(str((checked_at - mark_time).total_seconds()))
    if mark_age < Decimal("-2") or mark_age > MAX_QUERY_WINDOW_SECONDS:
        raise ProductPreSubmitRejected("MARK_PRICE_STALE")
    return mark


class LiveEntryFactTracker:
    """Keep only the latest same-event quote and mark facts for pre-submit freshness."""

    def __init__(self) -> None:
        self._quotes: dict[str, _QuoteValue] = {}
        self._marks: dict[str, _StreamValue] = {}

    def record_quote(self, tick: object) -> None:
        try:
            instrument_id = str(getattr(tick, "instrument_id"))
            bid = Decimal(str(getattr(tick, "bid_price")))
            ask = Decimal(str(getattr(tick, "ask_price")))
            ts_event = int(getattr(tick, "ts_event"))
        except (AttributeError, InvalidOperation, TypeError, ValueError):
            return
        if bid <= 0 or ask <= 0 or bid > ask:
            return
        self._quotes[instrument_id] = _QuoteValue(
            instrument_id=instrument_id,
            bid=bid,
            ask=ask,
            ts_event=ts_event,
        )

    def record_mark(self, update: object) -> None:
        try:
            instrument_id = str(getattr(update, "instrument_id"))
            value = Decimal(str(getattr(update, "value")))
            ts_event = int(getattr(update, "ts_event"))
        except (AttributeError, InvalidOperation, TypeError, ValueError):
            return
        if value <= 0:
            return
        self._marks[instrument_id] = _StreamValue(
            instrument_id=instrument_id,
            value=value,
            ts_event=ts_event,
        )

    def conservative_reference(
        self,
        instrument_id: str,
        direction: Direction,
        *,
        cutoff_ns: int,
        max_age_ns: int = MAX_STREAM_FACT_AGE_NS,
    ) -> str:
        quote = self._quotes.get(instrument_id)
        mark = self._marks.get(instrument_id)
        if quote is None or mark is None:
            raise ProductPreSubmitRejected("STREAM_FACTS_UNKNOWN")
        for timestamp in (quote.ts_event, mark.ts_event):
            age = cutoff_ns - timestamp
            if age < 0 or age > max_age_ns:
                raise ProductPreSubmitRejected("STREAM_FACTS_STALE")
        midpoint = (quote.bid + quote.ask) / Decimal("2")
        spread_bps = (quote.ask - quote.bid) / midpoint * Decimal("10000")
        if spread_bps > MAX_ENTRY_SPREAD_BPS:
            raise ProductPreSubmitRejected("ENTRY_SPREAD_TOO_WIDE")
        return _conservative_entry_price(
            direction,
            mark=mark.value,
            bid=quote.bid,
            ask=quote.ask,
        )

    def fresh_mark(
        self,
        instrument_id: str,
        *,
        cutoff_ns: int,
    ) -> Decimal:
        mark = self._marks.get(instrument_id)
        if mark is None:
            raise ProductPreSubmitRejected("STREAM_FACTS_UNKNOWN")
        age = cutoff_ns - mark.ts_event
        if age < 0 or age > MAX_STREAM_FACT_AGE_NS:
            raise ProductPreSubmitRejected("STREAM_FACTS_STALE")
        return mark.value


def instrument_rules_payload(instrument: object) -> dict[str, str]:
    try:
        info = getattr(instrument, "info")
        if not isinstance(info, dict):
            raise TypeError("instrument info is not a mapping")
        raw_filters = info.get("filters")
        if not isinstance(raw_filters, list):
            raise TypeError("instrument filters are not a list")
        return parse_binance_symbol_filters(raw_filters).market_sizing_payload()
    except (
        AttributeError,
        BinanceInstrumentRulesError,
        InvalidOperation,
        KeyError,
        TypeError,
        ValueError,
    ):
        raise ProductPreSubmitRejected("INSTRUMENT_RULES_UNKNOWN") from None


def build_live_entry_sizing_snapshot(
    *,
    instrument_id: str,
    direction: Direction,
    cutoff_ns: int,
    tracker: LiveEntryFactTracker,
    instrument: object,
    account: object,
    boundary: ActivationCapitalBoundary,
) -> EntrySizingSnapshot:
    try:
        leverage_value = getattr(account, "leverage")(
            InstrumentId.from_str(instrument_id)
        )
        if leverage_value is None:
            raise ProductPreSubmitRejected("ACCOUNT_LEVERAGE_UNKNOWN")
        leverage = min(Decimal(str(leverage_value)), Decimal("5"))
        if leverage <= 0:
            raise ProductPreSubmitRejected("ACCOUNT_LEVERAGE_UNKNOWN")
        rules = instrument_rules_payload(instrument)
        return EntrySizingSnapshot(
            reference_price=tracker.conservative_reference(
                instrument_id,
                direction,
                cutoff_ns=cutoff_ns,
                max_age_ns=MAX_PRELIMINARY_STREAM_FACT_AGE_NS,
            ),
            reference_source=(
                "BINANCE_MARK_AND_TOP_OF_BOOK_ASK"
                if direction is Direction.LONG
                else "BINANCE_MARK_AND_TOP_OF_BOOK_BID"
            ),
            max_allowed_loss=boundary.max_allowed_loss,
            max_notional=boundary.max_notional,
            max_margin=boundary.max_margin,
            effective_leverage=canonical_decimal(leverage),
            taker_fee_rate=canonical_decimal(
                Decimal(str(getattr(instrument, "taker_fee")))
            ),
            rules=InstrumentQuantityRules(**rules),
        )
    except ProductPreSubmitRejected:
        raise
    except (AttributeError, InvalidOperation, TypeError, ValueError):
        raise ProductPreSubmitRejected("ENTRY_SIZING_FACTS_UNKNOWN") from None


class ProductPreSubmitFactProvider:
    """Refresh Binance rules/account facts after a proposal on the shared client."""

    def __init__(
        self,
        *,
        node: object,
        profile: str,
        api_key: SecretStr,
        api_secret: SecretStr,
        proxy_url: str | None,
    ) -> None:
        self._node = node
        self._profile = profile
        self._api_key = api_key
        self._api_secret = api_secret
        self._proxy_url = proxy_url
        self._client: object | None = None

    def _binance_client(self) -> object:
        if self._client is None:
            environment = (
                BinanceEnvironment.DEMO
                if self._profile == "BINANCE_DEMO"
                else BinanceEnvironment.LIVE
            )
            self._client = get_cached_binance_http_client(
                clock=self._node.kernel.clock,
                account_type=BinanceAccountType.USDT_FUTURES,
                api_key=self._api_key.get_secret_value(),
                api_secret=self._api_secret.get_secret_value(),
                key_type=BinanceKeyType.HMAC,
                base_url=None,
                environment=environment,
                is_us=False,
                proxy_url=self._proxy_url,
            )
        return self._client

    def _account_api(self, client: object) -> BinanceFuturesAccountHttpAPI:
        return BinanceFuturesAccountHttpAPI(
            client,
            self._node.kernel.clock,
            BinanceAccountType.USDT_FUTURES,
        )

    @staticmethod
    def _market_api(client: object) -> BinanceFuturesMarketHttpAPI:
        return BinanceFuturesMarketHttpAPI(
            client,
            BinanceAccountType.USDT_FUTURES,
        )

    def _wallet_api(self, client: object) -> BinanceFuturesWalletHttpAPI:
        return BinanceFuturesWalletHttpAPI(
            client,
            self._node.kernel.clock,
            BinanceAccountType.USDT_FUTURES,
        )

    async def __call__(self, proposal: StrategyProposal) -> ProductAccountFacts:
        try:
            return await self._load_facts(proposal)
        except ProductPreSubmitRejected:
            raise
        except Exception as exc:
            raise ProductPreSubmitRejected(
                f"ACCOUNT_FACT_INVALID_{type(exc).__name__.upper()}"
            ) from None

    async def direct_entry_facts(
        self,
        activation: PlanActivation,
        leg: MaterializedOrderLeg,
        *,
        owned_order_client_ids: frozenset[str],
        owned_algo_client_ids: frozenset[str],
        expected_signed_position: str,
        outstanding_entry_quantity: str,
        outstanding_entry_notional: str,
        price_move_bps_by_window: dict[int, str] | None = None,
    ) -> DirectScheduleFacts:
        """Refresh facts for one fixed direct leg without strategy assumptions."""

        try:
            return await self._load_direct_entry_facts(
                activation,
                leg,
                owned_order_client_ids=owned_order_client_ids,
                owned_algo_client_ids=owned_algo_client_ids,
                expected_signed_position=expected_signed_position,
                outstanding_entry_quantity=outstanding_entry_quantity,
                outstanding_entry_notional=outstanding_entry_notional,
                price_move_bps_by_window=price_move_bps_by_window or {},
            )
        except ProductPreSubmitRejected:
            raise
        except Exception as exc:
            raise ProductPreSubmitRejected(
                f"ACCOUNT_FACT_INVALID_{type(exc).__name__.upper()}"
            ) from None

    async def risk_reduction_facts(
        self,
        activation: PlanActivation,
    ) -> ProductRiskReductionFacts:
        """Refresh the smaller fact set required by reduce-only responsibilities."""

        try:
            return await self._load_risk_reduction_facts(activation)
        except ProductPreSubmitRejected:
            raise
        except Exception as exc:
            raise ProductPreSubmitRejected(
                f"ACCOUNT_FACT_INVALID_{type(exc).__name__.upper()}"
            ) from None

    async def entry_order_is_definitely_absent(
        self,
        action: ExecutionAction,
    ) -> bool:
        """Confirm an old unknown entry is absent by its original Binance UUID."""

        observed_at = datetime.now(UTC)
        if (
            action.action_kind is not ExecutionActionKind.ENTRY
            or action.state is not ExecutionActionState.UNKNOWN
            or action.client_order_id is None
            or action.call_started_at is None
            or Decimal(str((observed_at - action.call_started_at).total_seconds()))
            < ENTRY_ORDER_ABSENCE_DELAY_SECONDS
        ):
            return False
        client = self._binance_client()
        account_api = self._account_api(client)
        symbol = _binance_symbol(f"{action.action_terms['instrument_ref']}.BINANCE")
        try:
            await asyncio.wait_for(
                account_api.query_order(
                    symbol=symbol,
                    orig_client_order_id=action.client_order_id,
                    recv_window="5000",
                ),
                timeout=float(MAX_QUERY_WINDOW_SECONDS),
            )
        except BinanceClientError as exc:
            message = getattr(exc, "message", None)
            if isinstance(message, dict) and message.get("code") == -2013:
                return True
            raise ProductPreSubmitRejected("ENTRY_ORDER_QUERY_REJECTED") from None
        except Exception as exc:
            raise ProductPreSubmitRejected(
                f"ENTRY_ORDER_QUERY_FAILED_{type(exc).__name__.upper()}"
            ) from None
        return False

    async def _load_risk_reduction_facts(
        self,
        activation: PlanActivation,
    ) -> ProductRiskReductionFacts:
        client = self._binance_client()
        account_api = self._account_api(client)
        market_api = self._market_api(client)
        symbol = _binance_symbol(f"{activation.instrument_ref}.BINANCE")
        started_at = datetime.now(UTC)
        try:
            (
                account_info,
                symbol_configs,
                hedge_mode,
                single_asset_mode,
                positions,
                book_tickers,
                mark_snapshot,
                open_orders,
                open_algo_orders,
            ) = (
                await asyncio.wait_for(
                    asyncio.gather(
                        account_api.query_futures_account_info(recv_window="5000"),
                        account_api.query_futures_symbol_config(
                            symbol=symbol,
                            recv_window="5000",
                        ),
                        account_api.query_futures_hedge_mode(recv_window="5000"),
                        query_single_asset_mode(
                            client,
                            self._node.kernel.clock,
                            recv_window="5000",
                        ),
                        account_api.query_futures_position_risk(recv_window="5000"),
                        market_api.query_ticker_book(symbol=symbol),
                        _query_current_mark_price(client, symbol),
                        account_api.query_open_orders(
                            symbol=symbol,
                            recv_window="5000",
                        ),
                        account_api.query_open_algo_orders(
                            symbol=symbol,
                            recv_window="5000",
                        ),
                    ),
                    timeout=float(MAX_QUERY_WINDOW_SECONDS),
                )
            )
        except ProductPreSubmitRejected:
            raise
        except BinanceAccountContractError as exc:
            raise ProductPreSubmitRejected(str(exc)) from None
        except Exception as exc:
            raise ProductPreSubmitRejected(
                f"ACCOUNT_FACT_QUERY_FAILED_{type(exc).__name__.upper()}"
            ) from None
        checked_at = datetime.now(UTC)
        if Decimal(str((checked_at - started_at).total_seconds())) > MAX_QUERY_WINDOW_SECONDS:
            raise ProductPreSubmitRejected("ACCOUNT_FACT_QUERY_STALE")
        _require_supported_account_mode(
            hedge_mode,
            single_asset_mode=single_asset_mode,
        )
        margin_mode, leverage, current_effective = _account_margin_state(
            account_info,
            symbol_configs,
            symbol,
        )
        bid, ask = _top_of_book(book_tickers, symbol)
        mark = _fresh_mark(mark_snapshot, checked_at)
        conservative_price = max(mark, bid, ask)
        signed_position = _symbol_position(symbol=symbol, positions=positions)
        if (
            activation.direction is Direction.LONG
            and signed_position < 0
        ) or (
            activation.direction is Direction.SHORT
            and signed_position > 0
        ):
            raise ProductPreSubmitRejected("POSITION_DIRECTION_CONFLICT")
        current_abs = abs(signed_position)
        activation_notional = current_abs * conservative_price
        account_notional = sum(
            (_position_notional(item) for item in positions),
            Decimal("0"),
        )
        position_fact = build_venue_fact(
            venue_fact_id=str(uuid4()),
            environment_id=activation.environment_id,
            venue_ref="BINANCE",
            account_ref=activation.account_ref,
            instrument_ref=activation.instrument_ref,
            kind=VenueFactKind.POSITION_STATE,
            source_class=VenueFactSourceClass.VENUE_QUERY,
            source_object_id=f"{symbol}:POSITION_RISK",
            source_sequence=str(int(checked_at.timestamp() * 1_000_000)),
            source_time=None,
            received_at=checked_at,
            cutoff=checked_at,
            payload={
                "query_path": "/fapi/v2/positionRisk",
                "read_only": True,
                "symbol": symbol,
                "position_quantity": canonical_decimal(signed_position),
                "position_abs_quantity": canonical_decimal(current_abs),
                "mark_price": canonical_decimal(mark),
            },
        )
        return ProductRiskReductionFacts(
            checked_at=checked_at,
            conservative_price=canonical_decimal(conservative_price),
            available_margin=canonical_decimal(_available_margin(account_info)),
            actual_margin_mode=margin_mode,
            actual_leverage=leverage,
            activation_current_notional=canonical_decimal(activation_notional),
            account_current_notional=canonical_decimal(account_notional),
            activation_current_margin=canonical_decimal(
                activation_notional / current_effective
            ),
            current_abs_position=canonical_decimal(current_abs),
            position_fact=position_fact,
            open_order_client_ids=_client_order_ids(open_orders),
            open_algo_client_ids=_client_algo_order_ids(open_algo_orders),
        )

    async def _load_direct_entry_facts(
        self,
        activation: PlanActivation,
        leg: MaterializedOrderLeg,
        *,
        owned_order_client_ids: frozenset[str],
        owned_algo_client_ids: frozenset[str],
        expected_signed_position: str,
        outstanding_entry_quantity: str,
        outstanding_entry_notional: str,
        price_move_bps_by_window: dict[int, str],
    ) -> DirectScheduleFacts:
        snapshot = activation.order_schedule_snapshot
        if snapshot is None or snapshot.schedule_spec.protection_policy is None:
            raise ProductPreSubmitRejected("ORDER_SCHEDULE_SNAPSHOT_REQUIRED")
        schedule_context = leg.proposed_action.execution_context.get("order_schedule")
        if (
            not isinstance(schedule_context, dict)
            or schedule_context.get("schedule_digest") != snapshot.schedule_digest
        ):
            raise ProductPreSubmitRejected("ORDER_SCHEDULE_ACTION_CONFLICT")
        client = self._binance_client()
        account_api = self._account_api(client)
        market_api = self._market_api(client)
        symbol = _binance_symbol(f"{activation.instrument_ref}.BINANCE")
        started_at = datetime.now(UTC)
        try:
            (
                account_info,
                symbol_configs,
                hedge_mode,
                single_asset_mode,
                positions,
                exchange_info,
                book_tickers,
                mark_snapshot,
                open_orders,
                open_algo_orders,
            ) = await asyncio.wait_for(
                asyncio.gather(
                    account_api.query_futures_account_info(recv_window="5000"),
                    account_api.query_futures_symbol_config(
                        symbol=symbol,
                        recv_window="5000",
                    ),
                    account_api.query_futures_hedge_mode(recv_window="5000"),
                    query_single_asset_mode(
                        client,
                        self._node.kernel.clock,
                        recv_window="5000",
                    ),
                    account_api.query_futures_position_risk(recv_window="5000"),
                    market_api.query_futures_exchange_info(),
                    market_api.query_ticker_book(symbol=symbol),
                    _query_current_mark_price(client, symbol),
                    account_api.query_open_orders(
                        symbol=symbol,
                        recv_window="5000",
                    ),
                    account_api.query_open_algo_orders(
                        symbol=symbol,
                        recv_window="5000",
                    ),
                ),
                timeout=float(MAX_QUERY_WINDOW_SECONDS),
            )
        except ProductPreSubmitRejected:
            raise
        except BinanceAccountContractError as exc:
            raise ProductPreSubmitRejected(str(exc)) from None
        except Exception as exc:
            raise ProductPreSubmitRejected(
                f"ACCOUNT_FACT_QUERY_FAILED_{type(exc).__name__.upper()}"
            ) from None
        checked_at = datetime.now(UTC)
        if Decimal(str((checked_at - started_at).total_seconds())) > MAX_QUERY_WINDOW_SECONDS:
            raise ProductPreSubmitRejected("ACCOUNT_FACT_QUERY_STALE")
        valid_until = leg.proposed_action.valid_until
        if valid_until is not None and checked_at >= valid_until:
            raise ProductPreSubmitRejected("DIRECT_ENTRY_EXPIRED")
        _require_supported_account_mode(
            hedge_mode,
            single_asset_mode=single_asset_mode,
        )
        margin_mode, leverage, current_effective = _account_margin_state(
            account_info,
            symbol_configs,
            symbol,
        )
        try:
            current_rule_set = binance_exchange_symbol_rules(exchange_info, symbol)
            source_time_ms = getattr(exchange_info, "serverTime")
            if not isinstance(source_time_ms, int) or source_time_ms <= 0:
                raise ValueError("source time missing")
            current_rules = InstrumentOrderRules(
                **current_rule_set.order_schedule_payload(),
                source=snapshot.instrument_rules.source,
                source_cutoff=datetime.fromtimestamp(
                    source_time_ms / 1000,
                    tz=UTC,
                ).isoformat(),
            )
        except (
            AttributeError,
            BinanceInstrumentRulesError,
            TypeError,
            ValueError,
        ):
            raise ProductPreSubmitRejected("INSTRUMENT_RULES_UNKNOWN") from None
        if current_rules.digest != snapshot.instrument_rules_digest:
            raise ProductPreSubmitRejected("INSTRUMENT_RULES_DRIFT")

        ordinary_ids = frozenset(_client_order_ids(open_orders))
        algo_ids = frozenset(_client_algo_order_ids(open_algo_orders))
        if not ordinary_ids.issubset(owned_order_client_ids) or not algo_ids.issubset(
            owned_algo_client_ids
        ):
            raise ProductPreSubmitRejected("ENTRY_OPEN_ORDER_CONFLICT")
        signed_position = _symbol_position(symbol=symbol, positions=positions)
        expected_position = Decimal(
            canonical_decimal(
                decimal_from_string(
                    expected_signed_position,
                    code="POSITION_FACT_INVALID",
                )
            )
        )
        if signed_position != expected_position:
            raise ProductPreSubmitRejected("POSITION_ATTRIBUTION_UNKNOWN")
        if (
            activation.direction is Direction.LONG
            and signed_position < 0
        ) or (
            activation.direction is Direction.SHORT
            and signed_position > 0
        ):
            raise ProductPreSubmitRejected("POSITION_DIRECTION_CONFLICT")
        outstanding = decimal_from_string(
            outstanding_entry_quantity,
            code="OPEN_ORDER_FACT_INVALID",
            non_negative=True,
        )
        outstanding_notional = decimal_from_string(
            outstanding_entry_notional,
            code="OPEN_ORDER_FACT_INVALID",
            non_negative=True,
        )
        bid, ask = _top_of_book(book_tickers, symbol)
        mark = _fresh_mark(mark_snapshot, checked_at)
        conservative_price = max(
            mark,
            bid,
            ask,
            Decimal(leg.leg.sizing_price),
        )
        current_abs = abs(signed_position)
        activation_quantity = current_abs + outstanding
        activation_notional = current_abs * conservative_price + outstanding_notional
        account_notional = sum(
            (_position_notional(item) for item in positions),
            Decimal(0),
        ) + outstanding_notional
        account_facts = ProductAccountFacts(
            checked_at=checked_at,
            conservative_price=canonical_decimal(conservative_price),
            available_margin=canonical_decimal(_available_margin(account_info)),
            actual_margin_mode=margin_mode,
            actual_leverage=leverage,
            activation_current_notional=canonical_decimal(activation_notional),
            account_current_notional=canonical_decimal(account_notional),
            activation_current_margin=canonical_decimal(
                activation_notional / current_effective
            ),
            current_abs_position=canonical_decimal(current_abs),
            post_action_abs_position=canonical_decimal(
                activation_quantity + Decimal(leg.leg.quantity)
            ),
        )
        return DirectScheduleFacts(
            account=account_facts,
            conditions=ConditionFacts(
                basis_ready=True,
                mark_price=canonical_decimal(mark),
                bid_price=canonical_decimal(bid),
                ask_price=canonical_decimal(ask),
                price_move_bps_by_window=price_move_bps_by_window,
                elapsed_seconds=max(
                    0,
                    int((checked_at - activation.created_at).total_seconds()),
                ),
            ),
        )

    async def _load_facts(self, proposal: StrategyProposal) -> ProductAccountFacts:
        context = proposal.entry_risk_context
        if context is None:
            raise ProductPreSubmitRejected("ENTRY_RISK_CONTEXT_UNKNOWN")
        client = self._binance_client()
        account_api = self._account_api(client)
        market_api = self._market_api(client)
        wallet_api = self._wallet_api(client)
        symbol = _binance_symbol(proposal.instrument_id)
        started_at = datetime.now(UTC)
        try:
            (
                account_info,
                symbol_configs,
                hedge_mode,
                single_asset_mode,
                positions,
                exchange_info,
                commission,
                book_tickers,
                mark_snapshot,
                open_orders,
                open_algo_orders,
            ) = (
                await asyncio.wait_for(
                    asyncio.gather(
                        account_api.query_futures_account_info(recv_window="5000"),
                        account_api.query_futures_symbol_config(
                            symbol=symbol,
                            recv_window="5000",
                        ),
                        account_api.query_futures_hedge_mode(recv_window="5000"),
                        query_single_asset_mode(
                            client,
                            self._node.kernel.clock,
                            recv_window="5000",
                        ),
                        account_api.query_futures_position_risk(recv_window="5000"),
                        market_api.query_futures_exchange_info(),
                        wallet_api.query_futures_commission_rate(
                            symbol=symbol,
                            recv_window="5000",
                        ),
                        market_api.query_ticker_book(symbol=symbol),
                        _query_current_mark_price(client, symbol),
                        account_api.query_open_orders(
                            symbol=symbol,
                            recv_window="5000",
                        ),
                        account_api.query_open_algo_orders(
                            symbol=symbol,
                            recv_window="5000",
                        ),
                    ),
                    timeout=float(MAX_QUERY_WINDOW_SECONDS),
                )
            )
        except ProductPreSubmitRejected:
            raise
        except BinanceAccountContractError as exc:
            raise ProductPreSubmitRejected(str(exc)) from None
        except Exception as exc:
            raise ProductPreSubmitRejected(
                f"ACCOUNT_FACT_QUERY_FAILED_{type(exc).__name__.upper()}"
            ) from None
        checked_at = datetime.now(UTC)
        if Decimal(str((checked_at - started_at).total_seconds())) > MAX_QUERY_WINDOW_SECONDS:
            raise ProductPreSubmitRejected("ACCOUNT_FACT_QUERY_STALE")
        source_age = Decimal(str((checked_at - proposal.source_cutoff).total_seconds()))
        if source_age < 0 or source_age > MAX_SOURCE_BAR_AGE_SECONDS:
            raise ProductPreSubmitRejected("SOURCE_BAR_STALE")
        if checked_at >= proposal.valid_until:
            raise ProductPreSubmitRejected("PROPOSAL_EXPIRED")
        _require_supported_account_mode(
            hedge_mode,
            single_asset_mode=single_asset_mode,
        )
        margin_mode, leverage, current_effective = _account_margin_state(
            account_info,
            symbol_configs,
            symbol,
        )
        if current_effective != Decimal(context.sizing_effective_leverage):
            raise ProductPreSubmitRejected("EFFECTIVE_LEVERAGE_DRIFT")

        taker_fee = canonical_decimal(Decimal(str(commission.takerCommissionRate)))
        if Decimal(taker_fee) > Decimal(context.sizing_taker_fee_rate):
            raise ProductPreSubmitRejected("TAKER_FEE_EXCEEDS_SIZING_SNAPSHOT")
        rules_digest = _exchange_rules_digest(exchange_info, symbol)
        if rules_digest != context.instrument_rules_digest:
            raise ProductPreSubmitRejected("INSTRUMENT_RULES_DRIFT")

        bid, ask = _top_of_book(book_tickers, symbol)
        mark = _fresh_mark(mark_snapshot, checked_at)
        conservative_price = _conservative_entry_price(
            proposal.direction,
            mark=mark,
            bid=bid,
            ask=ask,
        )
        boundary = Decimal(context.entry_extension_boundary)
        reference = Decimal(conservative_price)
        if (
            proposal.direction is Direction.LONG
            and reference > boundary
        ) or (
            proposal.direction is Direction.SHORT
            and reference < boundary
        ):
            raise ProductPreSubmitRejected("ENTRY_EXTENSION_LIMIT_EXCEEDED")

        current_abs = _require_flat_entry_scope(
            symbol=symbol,
            positions=positions,
            open_orders=open_orders,
            open_algo_orders=open_algo_orders,
        )
        account_notional = sum(
            (_position_notional(item) for item in positions),
            Decimal("0"),
        )
        activation_notional = current_abs * reference
        available_margin = _available_margin(account_info)
        return ProductAccountFacts(
            checked_at=checked_at,
            conservative_price=conservative_price,
            available_margin=canonical_decimal(available_margin),
            actual_margin_mode=margin_mode,
            actual_leverage=leverage,
            activation_current_notional=canonical_decimal(activation_notional),
            account_current_notional=canonical_decimal(account_notional),
            activation_current_margin=canonical_decimal(
                activation_notional / current_effective
            ),
            current_abs_position=canonical_decimal(current_abs),
            post_action_abs_position=canonical_decimal(
                current_abs + Decimal(proposal.quantity)
            ),
        )


ProposalFactProvider = Callable[[StrategyProposal], Awaitable[ProductAccountFacts]]


async def _query_current_mark_price(
    client: object,
    symbol: str,
) -> tuple[Decimal, datetime]:
    try:
        raw = await client.send_request(
            http_method=HttpMethod.GET,
            url_path=MARK_PRICE_PATH,
            payload={"symbol": symbol},
            ratelimiter_keys=[
                f"binance:{MARK_PRICE_PATH}",
                "binance:global",
            ],
        )
        decoded = json.loads(raw)
        if not isinstance(decoded, dict) or decoded.get("symbol") != symbol:
            raise ValueError("mark response identity mismatch")
        mark = Decimal(str(decoded["markPrice"]))
        timestamp_ms = int(decoded["time"])
        if mark <= 0 or timestamp_ms <= 0:
            raise ValueError("mark response value invalid")
        return mark, datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
    except ProductPreSubmitRejected:
        raise
    except Exception as exc:
        raise ProductPreSubmitRejected(
            f"MARK_PRICE_QUERY_FAILED_{type(exc).__name__.upper()}"
        ) from None


class ProductProposalBoundary:
    """Schedule proposal checks on the node loop and enter EXE only after fresh facts."""

    def __init__(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        coordinator: ProductCoordinatorPort,
        fact_provider: ProposalFactProvider,
        environment_id: str,
        environment_kind: EnvironmentKind,
        authority_class: AuthorityClass,
        account_ref: str,
    ) -> None:
        self._loop = loop
        self._coordinator = coordinator
        self._fact_provider = fact_provider
        self._environment_id = environment_id
        self._environment_kind = environment_kind
        self._authority_class = authority_class
        self._account_ref = account_ref
        self._tasks: dict[str, _PendingProposal] = {}

    def submit(self, proposal: StrategyProposal) -> str:
        execution_action_id = _stable_id(
            "execution-action",
            self._environment_id,
            proposal,
        )
        existing = self._tasks.get(proposal.source_identity)
        if existing is not None:
            if existing.proposal_digest != proposal.proposal_digest:
                raise ProductPreSubmitRejected("SOURCE_IDENTITY_CONFLICT")
            if not existing.task.done():
                return existing.execution_action_id
            if not existing.task.cancelled() and existing.task.exception() is None:
                return existing.execution_action_id
        task = self._loop.create_task(self._process(proposal))
        self._tasks[proposal.source_identity] = _PendingProposal(
            proposal_digest=proposal.proposal_digest,
            execution_action_id=execution_action_id,
            task=task,
        )
        task.add_done_callback(self._report_task_failure)
        return execution_action_id

    def _report_task_failure(self, completed: asyncio.Task[None]) -> None:
        if completed.cancelled():
            return
        exception = completed.exception()
        if exception is not None:
            self._loop.call_exception_handler(
                {
                    "message": "HALPHA_PRODUCT_PROPOSAL_PROCESSOR_FAILED",
                    "exception": exception,
                    "task": completed,
                }
            )

    async def _process(self, proposal: StrategyProposal) -> None:
        plan_event_id = _stable_id("plan-event", self._environment_id, proposal)
        try:
            facts = await self._fact_provider(proposal)
        except ProductPreSubmitRejected as exc:
            self._coordinator.record_strategy_proposal_rejection(
                plan_event_id=plan_event_id,
                proposal=proposal,
                reason_code=exc.reason_code,
                observed_at=datetime.now(UTC),
            )
            return
        action_check = facts.action_check(
            proposal,
            environment_id=self._environment_id,
            environment_kind=self._environment_kind,
            authority_class=self._authority_class,
            account_ref=self._account_ref,
        )
        execution_action_id = _stable_id(
            "execution-action",
            self._environment_id,
            proposal,
        )
        coordinated = self._coordinator.consume_strategy_proposal(
            plan_event_id=plan_event_id,
            execution_action_id=execution_action_id,
            proposal=proposal,
            action_check=action_check,
            created_at=facts.checked_at,
            client_order_id=_stable_client_order_id(self._environment_id, proposal),
        )
        action = coordinated.execution_action
        if action is None or action.state is not ExecutionActionState.READY:
            return
        try:
            refreshed_facts = await self._fact_provider(proposal)
        except ProductPreSubmitRejected as exc:
            self._coordinator.reject_execution_action_before_submission(
                execution_action_id,
                reason_code=exc.reason_code,
                observed_at=datetime.now(UTC),
            )
            return
        action_check = refreshed_facts.action_check(
            proposal,
            environment_id=self._environment_id,
            environment_kind=self._environment_kind,
            authority_class=self._authority_class,
            account_ref=self._account_ref,
        )
        self._coordinator.process_execution_action(
            execution_action_id,
            action_check=action_check,
            request_payload={
                "profile": proposal.action_profile,
                "quantity": proposal.quantity,
                "pre_submit_cutoff": refreshed_facts.checked_at.isoformat(),
            },
            observed_at=datetime.now(UTC),
        )

    async def wait_idle(self) -> None:
        pending = tuple(
            item.task for item in self._tasks.values() if not item.task.done()
        )
        if pending:
            await asyncio.gather(*pending)

    def close(self) -> None:
        for item in self._tasks.values():
            if not item.task.done():
                item.task.cancel()
        self._tasks.clear()


@dataclass(frozen=True, slots=True)
class _PendingProposal:
    proposal_digest: str
    execution_action_id: str
    task: asyncio.Task[None]


def _stable_id(kind: str, environment_id: str, proposal: StrategyProposal) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            (
                f"urn:halpha:{environment_id}:{kind}:{proposal.activation_id}:"
                f"{proposal.source_identity}:{proposal.input_digest}"
            ),
        )
    )


def _stable_client_order_id(environment_id: str, proposal: StrategyProposal) -> str:
    return uuid5(
        NAMESPACE_URL,
        (
            f"urn:halpha:{environment_id}:client-order:{proposal.activation_id}:"
            f"{proposal.source_identity}:{proposal.input_digest}"
        ),
    ).hex


def _instrument_ref(instrument_id: str) -> str:
    suffix = ".BINANCE"
    if not instrument_id.endswith(suffix):
        raise ProductPreSubmitRejected("INSTRUMENT_SCOPE_MISMATCH")
    return instrument_id[: -len(suffix)]


def _binance_symbol(instrument_id: str) -> str:
    instrument_ref = _instrument_ref(instrument_id)
    suffix = "-PERP"
    if not instrument_ref.endswith(suffix):
        raise ProductPreSubmitRejected("INSTRUMENT_SCOPE_MISMATCH")
    return instrument_ref[: -len(suffix)]


def _exchange_rules_digest(exchange_info: object, symbol: str) -> str:
    try:
        payload = binance_exchange_symbol_rules(
            exchange_info,
            symbol,
        ).market_sizing_payload()
    except BinanceInstrumentRulesError:
        raise ProductPreSubmitRejected("INSTRUMENT_RULES_UNKNOWN") from None
    return content_digest(payload)


def _position_notional(position: object) -> Decimal:
    value = getattr(position, "notional", None)
    if value is not None:
        return abs(Decimal(str(value)))
    return abs(
        Decimal(str(getattr(position, "positionAmt")))
        * Decimal(str(getattr(position, "markPrice")))
    )


def _symbol_position(*, symbol: str, positions: object) -> Decimal:
    try:
        return sum(
            (
                Decimal(str(getattr(item, "positionAmt")))
                for item in positions
                if str(getattr(item, "symbol")) == symbol
            ),
            Decimal("0"),
        )
    except (AttributeError, InvalidOperation, TypeError, ValueError):
        raise ProductPreSubmitRejected("POSITION_FACT_INVALID") from None


def _symbol_abs_position(*, symbol: str, positions: object) -> Decimal:
    return abs(_symbol_position(symbol=symbol, positions=positions))


def _client_order_ids(orders: object) -> tuple[str, ...]:
    try:
        return tuple(
            str(getattr(order, "clientOrderId"))
            for order in orders
            if getattr(order, "clientOrderId", None) is not None
        )
    except TypeError:
        raise ProductPreSubmitRejected("OPEN_ORDER_FACT_INVALID") from None


def _client_algo_order_ids(orders: object) -> tuple[str, ...]:
    try:
        return tuple(
            str(getattr(order, "clientAlgoId"))
            for order in orders
            if getattr(order, "clientAlgoId", None) is not None
        )
    except TypeError:
        raise ProductPreSubmitRejected("OPEN_ALGO_ORDER_FACT_INVALID") from None


def _require_flat_entry_scope(
    *,
    symbol: str,
    positions: object,
    open_orders: object,
    open_algo_orders: object,
) -> Decimal:
    """Reject a first entry when the instrument already has external responsibility."""

    try:
        current_abs = _symbol_abs_position(symbol=symbol, positions=positions)
    except (AttributeError, InvalidOperation, TypeError, ValueError):
        raise ProductPreSubmitRejected("ENTRY_POSITION_FACT_INVALID") from None
    if current_abs != 0:
        raise ProductPreSubmitRejected("ENTRY_POSITION_NOT_FLAT")
    try:
        if len(open_orders) != 0:
            raise ProductPreSubmitRejected("ENTRY_OPEN_ORDER_CONFLICT")
        if len(open_algo_orders) != 0:
            raise ProductPreSubmitRejected("ENTRY_OPEN_ALGO_ORDER_CONFLICT")
    except TypeError:
        raise ProductPreSubmitRejected("ENTRY_OPEN_ORDER_FACT_INVALID") from None
    return current_abs


def _available_margin(account_info: object) -> Decimal:
    direct = getattr(account_info, "availableBalance", None)
    if direct is not None:
        value = Decimal(str(direct))
        if value >= 0:
            return value
    for asset in account_info.assets:
        if asset.asset == "USDT":
            value = Decimal(str(asset.availableBalance))
            if value >= 0:
                return value
    raise ProductPreSubmitRejected("AVAILABLE_MARGIN_UNKNOWN")
