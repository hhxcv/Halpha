"""Fail-closed live proposal orchestration for the single product execution path."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import json
from time import monotonic
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
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.core.nautilus_pyo3 import HttpMethod
from pydantic import SecretStr

from halpha.binance_contracts import FUTURES_POSITION_RISK_PATH
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
from halpha.position_attribution import AccountInstrumentAttribution
from halpha.planning.bar_evaluation import BarEvaluationError, EntrySizingSnapshot
from halpha.planning.models import PlanActivation, ProposedAction
from halpha.planning.order_policies import ConditionFactProvenance, ConditionFacts
from halpha.planning.order_schedule import InstrumentOrderRules, VenueOrderType
from halpha.planning.order_schedule_actions import MaterializedOrderLeg
from halpha.planning.registry import Direction
from halpha.public_instrument_rules import (
    binance_public_instrument_rules_identity,
)
from halpha.planning.strategies.one_shot import (
    InstrumentQuantityRules,
    StrategyProposal,
)
from halpha.venue_integration.facts import build_venue_fact, venue_trade_fact_id
from halpha.venue_integration.binance_rate_limits import (
    binance_retry_after_seconds,
)
from halpha.venue_integration.binance_rules import (
    BinanceInstrumentRulesError,
    binance_exchange_symbol_rules,
    parse_binance_symbol_filters,
)
from halpha.venue_integration.models import (
    BINANCE_USDM_VENUE_REF,
    ExecutionAction,
    ExecutionActionKind,
    ExecutionActionState,
    VenueFact,
    VenueFactKind,
    VenueFactSourceClass,
)
from halpha.venue_integration.nautilus_account import (
    BinanceAccountContractError,
    query_single_asset_mode,
)
from halpha.venue_integration.binance_funding import (
    FundingIncomeRecord,
    query_funding_income,
)

from .responsibilities import ProductRiskReductionFacts


MAX_STREAM_FACT_AGE_NS = 3_000_000_000
MAX_CONDITION_MARK_AGE_NS = 10_000_000_000
MAX_PRELIMINARY_STREAM_FACT_AGE_NS = 15_000_000_000
MAX_QUERY_WINDOW_SECONDS = Decimal("5")
RISK_REDUCTION_ACCOUNT_MODE_CACHE_SECONDS = 30.0
MAX_SOURCE_BAR_AGE_SECONDS = Decimal("65")
FIFTEEN_MINUTE_BAR_NS = 15 * 60 * 1_000_000_000
MARK_PRICE_PATH = "/fapi/v1/premiumIndex"


class ProductPreSubmitRejected(RuntimeError):
    """A stable, non-secret reason why one proposal cannot cross the write boundary."""

    def __init__(
        self,
        reason_code: str,
        *,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.retry_after_seconds = retry_after_seconds


def _venue_query_failure_reason(prefix: str, exc: BaseException) -> str:
    """Expose only stable numeric venue diagnostics, never secrets or messages."""

    reason = f"{prefix}_{type(exc).__name__.upper()}"
    status = getattr(exc, "status", None)
    try:
        status_code = int(status)
    except (TypeError, ValueError):
        status_code = None
    if status_code is not None:
        reason = f"{reason}_HTTP_{status_code}"
    message = getattr(exc, "message", None)
    venue_code = message.get("code") if isinstance(message, dict) else None
    try:
        numeric_venue_code = int(venue_code)
    except (TypeError, ValueError):
        numeric_venue_code = None
    if numeric_venue_code is not None:
        reason = f"{reason}_CODE_{numeric_venue_code}"
    return reason


def _venue_query_rejection(
    prefix: str,
    exc: BaseException,
) -> ProductPreSubmitRejected:
    return ProductPreSubmitRejected(
        _venue_query_failure_reason(prefix, exc),
        retry_after_seconds=binance_retry_after_seconds(exc),
    )


class ProductCoordinatorPort(Protocol):
    def consume_strategy_proposal(self, **kwargs: Any) -> Any: ...

    def process_execution_action(
        self, execution_action_id: str, **kwargs: Any
    ) -> Any: ...

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
class _StreamValue:
    instrument_id: str
    value: Decimal
    ts_event: int
    ts_init: int


@dataclass(frozen=True, slots=True)
class _QuoteValue:
    instrument_id: str
    bid: Decimal
    ask: Decimal
    ts_event: int
    ts_init: int


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
        max(mark, book_price) if direction is Direction.LONG else min(mark, book_price)
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


def _require_risk_reduction_account_mode(
    hedge_mode: object,
    *,
    single_asset_mode: bool,
    position_side: str,
) -> None:
    """Allow a hedge account only for an exact side-bound disposition."""

    dual_side = bool(getattr(hedge_mode, "dualSidePosition", True))
    if position_side not in {"BOTH", "LONG", "SHORT"}:
        raise ProductPreSubmitRejected("ACCOUNT_POSITION_MODE_UNSUPPORTED")
    if dual_side != (position_side != "BOTH"):
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

    def __init__(self, instrument_ref: str | None = None) -> None:
        self._quotes: dict[str, _QuoteValue] = {}
        self._marks: dict[str, _StreamValue] = {}
        self._closed_bar_15m: _StreamValue | None = None
        self._target_bar_type: BarType | None = None
        self._warmup_complete = False
        if instrument_ref is not None:
            self.configure_closed_bar_15m(instrument_ref)

    def configure_closed_bar_15m(self, instrument_ref: str) -> None:
        target = BarType.from_str(
            f"{instrument_ref}.BINANCE-15-MINUTE-LAST-EXTERNAL"
        )
        if self._target_bar_type is not None and str(self._target_bar_type) != str(
            target
        ):
            raise ValueError("CLOSED_BAR_TRACKER_INSTRUMENT_CONFLICT")
        self._target_bar_type = target

    @property
    def subscribed_bar_types(self) -> tuple[BarType, ...]:
        return (self.target_bar_type,)

    @property
    def target_bar_type(self) -> BarType:
        if self._target_bar_type is None:
            raise BarEvaluationError("CLOSED_BAR_TRACKER_NOT_CONFIGURED")
        return self._target_bar_type

    @property
    def target_history_count(self) -> int:
        return 1

    @property
    def warmup_complete(self) -> bool:
        return self._warmup_complete

    def try_warm_from_cached_bars(
        self,
        *,
        target_bars: Iterable[Bar],
    ) -> bool:
        if self._warmup_complete:
            return True
        latest = max(
            (
                bar
                for bar in target_bars
                if str(bar.bar_type) == str(self.target_bar_type)
            ),
            key=lambda bar: bar.ts_event,
            default=None,
        )
        if latest is None:
            return False
        self.accept_historical(latest)
        self.complete_live_warmup()
        return True

    def accept_historical(self, bar: Bar) -> None:
        if self._warmup_complete:
            raise BarEvaluationError("HISTORICAL_BAR_OUTSIDE_WARMUP")
        self._record_closed_bar_15m(bar)

    def complete_live_warmup(self) -> None:
        if self._warmup_complete:
            return
        if self._closed_bar_15m is None:
            raise BarEvaluationError("CLOSED_BAR_WARMUP_INCOMPLETE")
        self._warmup_complete = True

    def accept(self, bar: Bar) -> None:
        if not self._warmup_complete:
            raise BarEvaluationError("LIVE_WARMUP_NOT_COMPLETE")
        self._record_closed_bar_15m(bar)

    def _record_closed_bar_15m(self, bar: Bar) -> None:
        if str(bar.bar_type) != str(self.target_bar_type):
            return
        try:
            close = Decimal(str(bar.close))
            ts_event = int(bar.ts_event)
            ts_init = int(bar.ts_init)
        except (AttributeError, InvalidOperation, TypeError, ValueError):
            raise BarEvaluationError("CLOSED_BAR_INVALID") from None
        if close <= 0 or ts_event <= 0 or ts_init < ts_event:
            raise BarEvaluationError("CLOSED_BAR_INVALID")
        current = self._closed_bar_15m
        if current is not None:
            if ts_event < current.ts_event:
                return
            if ts_event == current.ts_event:
                if close != current.value:
                    raise BarEvaluationError("CLOSED_BAR_IDENTITY_CONFLICT")
                return
        self._closed_bar_15m = _StreamValue(
            instrument_id=str(self.target_bar_type.instrument_id),
            value=close,
            ts_event=ts_event,
            ts_init=ts_init,
        )

    def record_quote(self, tick: object) -> None:
        try:
            instrument_id = str(getattr(tick, "instrument_id"))
            bid = Decimal(str(getattr(tick, "bid_price")))
            ask = Decimal(str(getattr(tick, "ask_price")))
            ts_event = int(getattr(tick, "ts_event"))
            ts_init = int(getattr(tick, "ts_init", ts_event))
        except (AttributeError, InvalidOperation, TypeError, ValueError):
            return
        if (
            bid <= 0
            or ask <= 0
            or bid > ask
            or ts_event <= 0
            or ts_init < ts_event
        ):
            return
        current = self._quotes.get(instrument_id)
        if current is not None and ts_event < current.ts_event:
            return
        self._quotes[instrument_id] = _QuoteValue(
            instrument_id=instrument_id,
            bid=bid,
            ask=ask,
            ts_event=ts_event,
            ts_init=ts_init,
        )

    def record_mark(self, update: object) -> None:
        try:
            instrument_id = str(getattr(update, "instrument_id"))
            value = Decimal(str(getattr(update, "value")))
            ts_event = int(getattr(update, "ts_event"))
            ts_init = int(getattr(update, "ts_init", ts_event))
        except (AttributeError, InvalidOperation, TypeError, ValueError):
            return
        if value <= 0 or ts_event <= 0 or ts_init < ts_event:
            return
        current = self._marks.get(instrument_id)
        if current is not None and ts_event < current.ts_event:
            return
        self._marks[instrument_id] = _StreamValue(
            instrument_id=instrument_id,
            value=value,
            ts_event=ts_event,
            ts_init=ts_init,
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

    def direct_condition_facts(
        self,
        instrument_id: str,
        *,
        cutoff_ns: int,
        observed_at: datetime,
        activated_at: datetime,
        price_move_bps_by_window: dict[int, str],
        market_source: str,
    ) -> ConditionFacts:
        """Build condition-only facts from the adapter's same-environment stream."""

        if observed_at.utcoffset() is None or activated_at.utcoffset() is None:
            raise ValueError("DIRECT_SCHEDULE_TIMEZONE_REQUIRED")
        quote = self._quotes.get(instrument_id)
        mark = self._marks.get(instrument_id)
        fresh_quote = (
            quote
            if quote is not None
            and 0 <= cutoff_ns - quote.ts_event <= MAX_STREAM_FACT_AGE_NS
            and quote.ts_event <= quote.ts_init <= cutoff_ns
            else None
        )
        fresh_mark = (
            mark
            if mark is not None
            and 0 <= cutoff_ns - mark.ts_event <= MAX_CONDITION_MARK_AGE_NS
            and mark.ts_event <= mark.ts_init <= cutoff_ns
            else None
        )
        expected_closed_bar_at_ns = (
            cutoff_ns // FIFTEEN_MINUTE_BAR_NS
        ) * FIFTEEN_MINUTE_BAR_NS
        closed_bar_15m = self._closed_bar_15m
        fresh_closed_bar_15m = (
            closed_bar_15m
            if self._warmup_complete
            and closed_bar_15m is not None
            and closed_bar_15m.ts_event == expected_closed_bar_at_ns
            and closed_bar_15m.ts_event <= closed_bar_15m.ts_init <= cutoff_ns
            else None
        )
        return ConditionFacts(
            basis_ready=True,
            mark_price=(
                canonical_decimal(fresh_mark.value) if fresh_mark is not None else None
            ),
            closed_bar_15m_close=(
                canonical_decimal(fresh_closed_bar_15m.value)
                if fresh_closed_bar_15m is not None
                else None
            ),
            closed_bar_15m_at=(
                datetime.fromtimestamp(
                    fresh_closed_bar_15m.ts_event / 1_000_000_000,
                    tz=UTC,
                )
                if fresh_closed_bar_15m is not None
                else None
            ),
            bid_price=(
                canonical_decimal(fresh_quote.bid) if fresh_quote is not None else None
            ),
            ask_price=(
                canonical_decimal(fresh_quote.ask) if fresh_quote is not None else None
            ),
            price_move_bps_by_window=price_move_bps_by_window,
            elapsed_seconds=max(
                0,
                int(
                    (
                        observed_at.astimezone(UTC) - activated_at.astimezone(UTC)
                    ).total_seconds()
                ),
            ),
            provenance=ConditionFactProvenance(
                source=market_source,
                source_cutoff=observed_at.astimezone(UTC),
                evaluated_at=observed_at.astimezone(UTC),
                quote_source_time=(
                    datetime.fromtimestamp(
                        fresh_quote.ts_event / 1_000_000_000,
                        tz=UTC,
                    )
                    if fresh_quote is not None
                    else None
                ),
                quote_received_at=(
                    datetime.fromtimestamp(
                        fresh_quote.ts_init / 1_000_000_000,
                        tz=UTC,
                    )
                    if fresh_quote is not None
                    else None
                ),
                mark_source_time=(
                    datetime.fromtimestamp(
                        fresh_mark.ts_event / 1_000_000_000,
                        tz=UTC,
                    )
                    if fresh_mark is not None
                    else None
                ),
                mark_received_at=(
                    datetime.fromtimestamp(
                        fresh_mark.ts_init / 1_000_000_000,
                        tz=UTC,
                    )
                    if fresh_mark is not None
                    else None
                ),
            ),
        )


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


def require_direct_activation_profile_consistency(
    activation: PlanActivation | object,
    *,
    profile: str,
) -> EnvironmentKind:
    """Reject a persisted direct snapshot that belongs to another environment."""

    environment, expected_source = binance_public_instrument_rules_identity(profile)
    expected_kind = (
        EnvironmentKind.DEMO
        if environment is BinanceEnvironment.DEMO
        else EnvironmentKind.LIVE
    )
    if getattr(activation, "environment_kind", None) is not expected_kind:
        raise ProductPreSubmitRejected("ACTIVATION_ENVIRONMENT_PROFILE_MISMATCH")
    snapshot = getattr(activation, "order_schedule_snapshot", None)
    instrument_rules = getattr(snapshot, "instrument_rules", None)
    if getattr(instrument_rules, "source", None) != expected_source:
        raise ProductPreSubmitRejected("INSTRUMENT_RULES_SOURCE_ENVIRONMENT_MISMATCH")
    return expected_kind


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
        attribution_provider: (
            Callable[[str], AccountInstrumentAttribution] | None
        ) = None,
        monotonic_clock: Callable[[], float] = monotonic,
    ) -> None:
        self._node = node
        self._profile = profile
        self._api_key = api_key
        self._api_secret = api_secret
        self._proxy_url = proxy_url
        self._attribution_provider = attribution_provider
        self._monotonic_clock = monotonic_clock
        self._rate_limit_not_before: float | None = None
        self._client: object | None = None
        self._risk_reduction_mode_cache: tuple[float, object, bool] | None = None
        self._risk_reduction_mode_lock = asyncio.Lock()
        (
            self._binance_environment,
            self._expected_instrument_rules_source,
        ) = binance_public_instrument_rules_identity(profile)

    def _require_rate_limit_ready(self) -> None:
        if self._rate_limit_not_before is None:
            return
        now = self._monotonic_clock()
        if now >= self._rate_limit_not_before:
            self._rate_limit_not_before = None
            return
        raise ProductPreSubmitRejected(
            "BINANCE_RATE_LIMIT_BACKOFF",
            retry_after_seconds=self._rate_limit_not_before - now,
        )

    def _record_rate_limit(self, rejection: ProductPreSubmitRejected) -> None:
        if rejection.retry_after_seconds is None:
            return
        now = self._monotonic_clock()
        self._rate_limit_not_before = max(
            self._rate_limit_not_before or now,
            now + rejection.retry_after_seconds,
        )

    def _binance_client(self) -> object:
        if self._client is None:
            self._client = get_cached_binance_http_client(
                clock=self._node.kernel.clock,
                account_type=BinanceAccountType.USDT_FUTURES,
                api_key=self._api_key.get_secret_value(),
                api_secret=self._api_secret.get_secret_value(),
                key_type=BinanceKeyType.HMAC,
                base_url=None,
                environment=self._binance_environment,
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

    def _account_attribution(
        self,
        activation_id: str,
    ) -> AccountInstrumentAttribution | None:
        if self._attribution_provider is None:
            return None
        try:
            return self._attribution_provider(activation_id)
        except ValueError as exc:
            raise ProductPreSubmitRejected(str(exc)) from None

    async def _risk_reduction_account_modes(
        self,
        *,
        client: object,
        account_api: BinanceFuturesAccountHttpAPI,
    ) -> tuple[object, bool]:
        """Reuse bounded account-mode facts only for reduction checks.

        Binance rejects a position-mode change while an open position/order
        exists.  Multi-asset mode does not change side or reduce-only semantics.
        Every risk-increasing pre-submit check still queries both modes directly.
        """

        now = self._monotonic_clock()
        cached = self._risk_reduction_mode_cache
        if cached is not None and now - cached[0] <= (
            RISK_REDUCTION_ACCOUNT_MODE_CACHE_SECONDS
        ):
            return cached[1], cached[2]
        async with self._risk_reduction_mode_lock:
            now = self._monotonic_clock()
            cached = self._risk_reduction_mode_cache
            if cached is not None and now - cached[0] <= (
                RISK_REDUCTION_ACCOUNT_MODE_CACHE_SECONDS
            ):
                return cached[1], cached[2]
            hedge_mode, single_asset_mode = await asyncio.gather(
                account_api.query_futures_hedge_mode(recv_window="5000"),
                query_single_asset_mode(
                    client,
                    self._node.kernel.clock,
                    recv_window="5000",
                ),
            )
            self._risk_reduction_mode_cache = (
                self._monotonic_clock(),
                hedge_mode,
                single_asset_mode,
            )
            return hedge_mode, single_asset_mode

    async def __call__(self, proposal: StrategyProposal) -> ProductAccountFacts:
        self._require_rate_limit_ready()
        try:
            return await self._load_facts(proposal)
        except ProductPreSubmitRejected as exc:
            self._record_rate_limit(exc)
            raise

    async def direct_pre_submit_facts(
        self,
        activation: PlanActivation,
        leg: MaterializedOrderLeg,
        *,
        owned_order_client_ids: frozenset[str],
        owned_algo_client_ids: frozenset[str],
        expected_signed_position: str,
        outstanding_entry_quantity: str,
        outstanding_entry_notional: str,
    ) -> ProductAccountFacts:
        """Refresh facts for one fixed direct leg without strategy assumptions."""

        self._require_rate_limit_ready()
        attribution = self._account_attribution(activation.activation_id)
        try:
            require_direct_activation_profile_consistency(
                activation,
                profile=self._profile,
            )
            return await self._load_direct_pre_submit_facts(
                activation,
                leg,
                attribution=attribution,
                owned_order_client_ids=owned_order_client_ids,
                owned_algo_client_ids=owned_algo_client_ids,
                expected_signed_position=expected_signed_position,
                outstanding_entry_quantity=outstanding_entry_quantity,
                outstanding_entry_notional=outstanding_entry_notional,
            )
        except ProductPreSubmitRejected as exc:
            self._record_rate_limit(exc)
            raise

    async def risk_reduction_facts(
        self,
        activation: PlanActivation,
    ) -> ProductRiskReductionFacts:
        """Refresh the smaller fact set required by reduce-only responsibilities."""

        self._require_rate_limit_ready()
        try:
            return await self._load_risk_reduction_facts(activation)
        except ProductPreSubmitRejected as exc:
            self._record_rate_limit(exc)
            raise

    async def called_action_recovery_facts(
        self,
        action: ExecutionAction,
    ) -> tuple[VenueFact, ...]:
        """Recover one Halpha-called order through Binance's read-only APIs.

        Binance conditional orders have two identities after triggering: the
        original algo identity and the ordinary order which actually fills.
        Nautilus can query the original identity, but that query does not expose
        the generated order's trades.  Resolve that documented identity chain
        here so a missed user-stream fill cannot strand a plan's virtual
        position or time exit.
        """

        self._require_rate_limit_ready()
        try:
            return await self._load_called_action_recovery_facts(action)
        except ProductPreSubmitRejected as exc:
            self._record_rate_limit(exc)
            raise
        except Exception as exc:
            rejection = _venue_query_rejection("ACTION_FACT_QUERY_FAILED", exc)
            self._record_rate_limit(rejection)
            raise rejection from None

    async def funding_income(
        self,
        activation: PlanActivation,
        *,
        end_time: datetime,
    ) -> tuple[FundingIncomeRecord, ...]:
        """Read account funding with the same authenticated Nautilus client."""

        self._require_rate_limit_ready()
        try:
            return await asyncio.wait_for(
                query_funding_income(
                    self._binance_client(),
                    self._node.kernel.clock,
                    symbol=_binance_symbol(
                        f"{activation.instrument_ref}.BINANCE"
                    ),
                    start_time=activation.created_at,
                    end_time=end_time,
                ),
                timeout=10,
            )
        except Exception as exc:
            rejection = _venue_query_rejection("FUNDING_FACT_INVALID", exc)
            self._record_rate_limit(rejection)
            raise rejection from None

    async def _load_risk_reduction_facts(
        self,
        activation: PlanActivation,
    ) -> ProductRiskReductionFacts:
        attribution = self._account_attribution(activation.activation_id)
        client = self._binance_client()
        account_api = self._account_api(client)
        market_api = self._market_api(client)
        symbol = _binance_symbol(f"{activation.instrument_ref}.BINANCE")
        started_at = datetime.now(UTC)
        try:
            (
                account_info,
                symbol_configs,
                account_modes,
                positions,
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
                    self._risk_reduction_account_modes(
                        client=client,
                        account_api=account_api,
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
        except ProductPreSubmitRejected:
            raise
        except BinanceAccountContractError as exc:
            raise ProductPreSubmitRejected(str(exc)) from None
        except Exception as exc:
            raise _venue_query_rejection("ACCOUNT_FACT_QUERY_FAILED", exc) from None
        checked_at = datetime.now(UTC)
        if (
            Decimal(str((checked_at - started_at).total_seconds()))
            > MAX_QUERY_WINDOW_SECONDS
        ):
            raise ProductPreSubmitRejected("ACCOUNT_FACT_QUERY_STALE")
        attribution_cutoff = datetime.now(UTC)
        if attribution != self._account_attribution(activation.activation_id):
            # User-stream fills and terminal order events are persisted while
            # the signed REST reads above are in flight.  Never compare the
            # resulting venue snapshot with an older virtual-position
            # attribution: the pair describes two different account moments.
            # The responsibility boundary treats this as a transient read and
            # retries from a fresh snapshot without authorizing a venue write.
            raise ProductPreSubmitRejected("ACCOUNT_FACT_SUPERSEDED")
        hedge_mode, single_asset_mode = account_modes
        alignment = getattr(activation, "position_alignment", None)
        position_side = alignment.position_side if alignment is not None else "BOTH"
        _require_risk_reduction_account_mode(
            hedge_mode,
            single_asset_mode=single_asset_mode,
            position_side=position_side,
        )
        margin_mode, leverage, current_effective = _account_margin_state(
            account_info,
            symbol_configs,
            symbol,
        )
        bid, ask = _top_of_book(book_tickers, symbol)
        mark = _fresh_mark(mark_snapshot, checked_at)
        conservative_price = max(mark, bid, ask)
        signed_position = _symbol_position_for_side(
            symbol=symbol,
            positions=positions,
            position_side=position_side,
        )
        activation_signed_position = (
            Decimal(attribution.activation_signed_position)
            if attribution is not None
            else signed_position
        )
        if alignment is not None:
            if attribution is None:
                raise ProductPreSubmitRejected("POSITION_ATTRIBUTION_UNKNOWN")
            direction_sign = (
                Decimal(1)
                if activation.direction is Direction.LONG
                else Decimal(-1)
            )
            remaining_reduction = direction_sign * activation_signed_position
            requested_reduction = Decimal(
                alignment.requested_reduction_quantity
            )
            baseline = Decimal(alignment.baseline_quantity)
            reduction_filled = requested_reduction - remaining_reduction
            if (
                remaining_reduction < 0
                or reduction_filled < 0
                or reduction_filled > requested_reduction
            ):
                raise ProductPreSubmitRejected("POSITION_ALIGNMENT_DRIFT")
            expected_account_position = direction_sign * (
                baseline - reduction_filled
            )
        else:
            expected_account_position = (
                Decimal(attribution.account_signed_position)
                if attribution is not None
                else signed_position
            )
        if signed_position != expected_account_position:
            raise ProductPreSubmitRejected(
                "POSITION_ALIGNMENT_DRIFT"
                if alignment is not None
                else "POSITION_ATTRIBUTION_UNKNOWN"
            )
        if (
            activation.direction is Direction.LONG
            and activation_signed_position < 0
        ) or (
            activation.direction is Direction.SHORT
            and activation_signed_position > 0
        ):
            raise ProductPreSubmitRejected("POSITION_DIRECTION_CONFLICT")
        current_abs = abs(activation_signed_position)
        activation_notional = current_abs * conservative_price
        account_notional = sum(
            (_position_notional(item) for item in positions),
            Decimal("0"),
        )
        try:
            account_open_position_symbols = sorted(
                {
                    str(getattr(item, "symbol"))
                    for item in positions
                    if Decimal(str(getattr(item, "positionAmt"))) != 0
                }
            )
        except (AttributeError, InvalidOperation, TypeError, ValueError):
            raise ProductPreSubmitRejected(
                "POSITION_FACT_INVALID"
            ) from None
        open_order_client_ids = _client_order_ids(open_orders)
        open_algo_client_ids = _client_algo_order_ids(open_algo_orders)
        if attribution is not None and (
            not set(open_order_client_ids).issubset(
                attribution.account_ordinary_client_ids
            )
            or not set(open_algo_client_ids).issubset(
                attribution.account_algo_client_ids
            )
        ):
            raise ProductPreSubmitRejected("OPEN_ORDER_ATTRIBUTION_UNKNOWN")
        activation_open_order_client_ids = (
            tuple(
                item
                for item in open_order_client_ids
                if item in attribution.activation_ordinary_client_ids
            )
            if attribution is not None
            else open_order_client_ids
        )
        activation_open_algo_client_ids = (
            tuple(
                item
                for item in open_algo_client_ids
                if item in attribution.activation_algo_client_ids
            )
            if attribution is not None
            else open_algo_client_ids
        )
        position_fact = build_venue_fact(
            venue_fact_id=str(uuid4()),
            environment_id=activation.environment_id,
            venue_ref=BINANCE_USDM_VENUE_REF,
            account_ref=activation.account_ref,
            instrument_ref=activation.instrument_ref,
            kind=VenueFactKind.POSITION_STATE,
            source_class=VenueFactSourceClass.VENUE_QUERY,
            source_object_id=f"{symbol}:{position_side}:POSITION_RISK",
            source_sequence=str(int(checked_at.timestamp() * 1_000_000)),
            source_time=None,
            received_at=checked_at,
            cutoff=checked_at,
            payload={
                "query_path": FUTURES_POSITION_RISK_PATH,
                "read_only": True,
                "activation_id": activation.activation_id,
                "symbol": symbol,
                "position_side": position_side,
                "account_position_mode": (
                    "HEDGE" if position_side != "BOTH" else "ONE_WAY"
                ),
                "position_quantity": canonical_decimal(signed_position),
                "position_abs_quantity": canonical_decimal(abs(signed_position)),
                "activation_position_quantity": canonical_decimal(
                    activation_signed_position
                ),
                "activation_position_abs_quantity": canonical_decimal(current_abs),
                "attributed_account_position_quantity": canonical_decimal(
                    expected_account_position
                ),
                "activation_fill_fact_refs": (
                    list(attribution.activation_fill_fact_refs)
                    if attribution is not None
                    else []
                ),
                "account_fill_fact_refs": (
                    list(attribution.account_fill_fact_refs)
                    if attribution is not None
                    else []
                ),
                "mark_price": canonical_decimal(mark),
                "margin_mode": margin_mode,
                "leverage": leverage,
                "account_current_notional": canonical_decimal(account_notional),
                "account_open_position_symbols": (
                    account_open_position_symbols
                ),
                "instrument_open_order_client_ids": sorted(open_order_client_ids),
                "instrument_open_algo_client_ids": sorted(open_algo_client_ids),
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
            current_reference_price=canonical_decimal(mark),
            position_fact=position_fact,
            open_order_client_ids=activation_open_order_client_ids,
            open_algo_client_ids=activation_open_algo_client_ids,
            attribution_cutoff=attribution_cutoff,
        )

    async def _load_called_action_recovery_facts(
        self,
        action: ExecutionAction,
    ) -> tuple[VenueFact, ...]:
        client_order_id = action.client_order_id
        instrument_ref = action.action_terms.get("instrument_ref")
        if (
            not isinstance(client_order_id, str)
            or not client_order_id
            or not isinstance(instrument_ref, str)
            or not instrument_ref
            or action.action_kind is ExecutionActionKind.CANCEL
        ):
            raise ProductPreSubmitRejected("ACTION_IDENTITY_INVALID")
        client = self._binance_client()
        account_api = self._account_api(client)
        symbol = _binance_symbol(f"{instrument_ref}.BINANCE")
        observed_at = datetime.now(UTC)
        if action.action_kind in {
            ExecutionActionKind.PROTECTION,
            ExecutionActionKind.TAKE_PROFIT,
        }:
            algo_order = await asyncio.wait_for(
                account_api.query_algo_order(
                    client_algo_id=client_order_id,
                    recv_window="5000",
                ),
                timeout=float(MAX_QUERY_WINDOW_SECONDS),
            )
            actual_order_id = getattr(algo_order, "actualOrderId", None)
            if actual_order_id in {None, ""}:
                return (
                    _called_algo_order_state_fact(
                        action=action,
                        algo_order=algo_order,
                        observed_at=observed_at,
                    ),
                )
            try:
                venue_order_id = int(str(actual_order_id))
            except (TypeError, ValueError):
                raise ProductPreSubmitRejected(
                    "ACTION_ACTUAL_ORDER_ID_INVALID"
                ) from None
            order = await asyncio.wait_for(
                account_api.query_order(
                    symbol=symbol,
                    order_id=venue_order_id,
                    recv_window="5000",
                ),
                timeout=float(MAX_QUERY_WINDOW_SECONDS),
            )
        else:
            order = await asyncio.wait_for(
                account_api.query_order(
                    symbol=symbol,
                    orig_client_order_id=client_order_id,
                    recv_window="5000",
                ),
                timeout=float(MAX_QUERY_WINDOW_SECONDS),
            )
        order_id = getattr(order, "orderId", None)
        if order_id is None:
            raise ProductPreSubmitRejected("ACTION_ORDER_ID_MISSING")
        executed_quantity = _optional_decimal(
            getattr(order, "executedQty", None),
            code="ACTION_EXECUTED_QUANTITY_INVALID",
        )
        trades: object = ()
        if executed_quantity > 0:
            trades = await asyncio.wait_for(
                account_api.query_user_trades(
                    symbol=symbol,
                    order_id=int(order_id),
                    recv_window="5000",
                ),
                timeout=float(MAX_QUERY_WINDOW_SECONDS),
            )
        return _called_order_query_facts(
            action=action,
            order=order,
            trades=trades,
            observed_at=datetime.now(UTC),
        )

    async def _load_direct_pre_submit_facts(
        self,
        activation: PlanActivation,
        leg: MaterializedOrderLeg,
        *,
        attribution: AccountInstrumentAttribution | None,
        owned_order_client_ids: frozenset[str],
        owned_algo_client_ids: frozenset[str],
        expected_signed_position: str,
        outstanding_entry_quantity: str,
        outstanding_entry_notional: str,
    ) -> ProductAccountFacts:
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
            raise _venue_query_rejection("ACCOUNT_FACT_QUERY_FAILED", exc) from None
        checked_at = datetime.now(UTC)
        if (
            Decimal(str((checked_at - started_at).total_seconds()))
            > MAX_QUERY_WINDOW_SECONDS
        ):
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
                source=self._expected_instrument_rules_source,
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
        account_owned_order_ids = (
            attribution.account_ordinary_client_ids
            if attribution is not None
            else owned_order_client_ids
        )
        account_owned_algo_ids = (
            attribution.account_algo_client_ids
            if attribution is not None
            else owned_algo_client_ids
        )
        if (
            attribution is not None
            and (
                owned_order_client_ids
                != attribution.activation_ordinary_client_ids
                or owned_algo_client_ids
                != attribution.activation_algo_client_ids
                or Decimal(expected_signed_position)
                != Decimal(attribution.activation_signed_position)
            )
        ):
            raise ProductPreSubmitRejected("POSITION_ATTRIBUTION_UNKNOWN")
        if not ordinary_ids.issubset(account_owned_order_ids) or not algo_ids.issubset(
            account_owned_algo_ids
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
        expected_account_position = (
            Decimal(attribution.account_signed_position)
            if attribution is not None
            else expected_position
        )
        if signed_position != expected_account_position:
            raise ProductPreSubmitRejected("POSITION_ATTRIBUTION_UNKNOWN")
        if (activation.direction is Direction.LONG and expected_position < 0) or (
            activation.direction is Direction.SHORT and expected_position > 0
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
        valuation_price = max(
            mark,
            bid,
            ask,
            Decimal(leg.leg.sizing_price),
        )
        venue_policy = snapshot.schedule_spec.venue_policy
        if (
            venue_policy.order_type is VenueOrderType.LIMIT
            and venue_policy.price_match is None
        ):
            if leg.proposed_action.price is None:
                raise ProductPreSubmitRejected("ORDER_SCHEDULE_ACTION_CONFLICT")
            action_price = Decimal(leg.proposed_action.price)
        else:
            # Market and priceMatch orders have no fixed maximum venue price.
            action_price = valuation_price
        current_abs = abs(expected_position)
        activation_quantity = current_abs + outstanding
        activation_notional = current_abs * valuation_price + outstanding_notional
        account_notional = (
            sum(
                (_position_notional(item) for item in positions),
                Decimal(0),
            )
            + (
                Decimal(attribution.account_outstanding_entry_notional)
                if attribution is not None
                else outstanding_notional
            )
        )
        account_facts = ProductAccountFacts(
            checked_at=checked_at,
            conservative_price=canonical_decimal(action_price),
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
        return account_facts

    async def _load_facts(self, proposal: StrategyProposal) -> ProductAccountFacts:
        context = proposal.entry_risk_context
        if context is None:
            raise ProductPreSubmitRejected("ENTRY_RISK_CONTEXT_UNKNOWN")
        attribution = self._account_attribution(proposal.activation_id)
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
        except ProductPreSubmitRejected:
            raise
        except BinanceAccountContractError as exc:
            raise ProductPreSubmitRejected(str(exc)) from None
        except Exception as exc:
            raise _venue_query_rejection("ACCOUNT_FACT_QUERY_FAILED", exc) from None
        checked_at = datetime.now(UTC)
        if (
            Decimal(str((checked_at - started_at).total_seconds()))
            > MAX_QUERY_WINDOW_SECONDS
        ):
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
        if (proposal.direction is Direction.LONG and reference > boundary) or (
            proposal.direction is Direction.SHORT and reference < boundary
        ):
            raise ProductPreSubmitRejected("ENTRY_EXTENSION_LIMIT_EXCEEDED")

        if attribution is None:
            current_abs = _require_flat_entry_scope(
                symbol=symbol,
                positions=positions,
                open_orders=open_orders,
                open_algo_orders=open_algo_orders,
            )
        else:
            signed_position = _symbol_position(symbol=symbol, positions=positions)
            if signed_position != Decimal(attribution.account_signed_position):
                raise ProductPreSubmitRejected("POSITION_ATTRIBUTION_UNKNOWN")
            if Decimal(attribution.activation_signed_position) != 0:
                raise ProductPreSubmitRejected("ENTRY_POSITION_NOT_FLAT")
            ordinary_ids = frozenset(_client_order_ids(open_orders))
            algo_ids = frozenset(_client_algo_order_ids(open_algo_orders))
            if not ordinary_ids.issubset(
                attribution.account_ordinary_client_ids
            ) or not algo_ids.issubset(attribution.account_algo_client_ids):
                raise ProductPreSubmitRejected("ENTRY_OPEN_ORDER_CONFLICT")
            current_abs = Decimal(0)
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
        raise _venue_query_rejection("MARK_PRICE_QUERY_FAILED", exc) from None


COMPLETED_PROPOSAL_KEY_LIMIT = 4096


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
        failure_sink: Callable[[BaseException], None] | None = None,
    ) -> None:
        self._loop = loop
        self._coordinator = coordinator
        self._fact_provider = fact_provider
        self._environment_id = environment_id
        self._environment_kind = environment_kind
        self._authority_class = authority_class
        self._account_ref = account_ref
        self._failure_sink = failure_sink
        self._tasks: dict[str, _PendingProposal] = {}
        self._completed: OrderedDict[str, tuple[str, str]] = OrderedDict()

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
        completed = self._completed.get(proposal.source_identity)
        if completed is not None:
            proposal_digest, completed_action_id = completed
            if proposal_digest != proposal.proposal_digest:
                raise ProductPreSubmitRejected("SOURCE_IDENTITY_CONFLICT")
            self._completed.move_to_end(proposal.source_identity)
            return completed_action_id
        task = self._loop.create_task(self._process(proposal))
        self._tasks[proposal.source_identity] = _PendingProposal(
            proposal_digest=proposal.proposal_digest,
            execution_action_id=execution_action_id,
            task=task,
        )
        task.add_done_callback(
            lambda completed_task, source_identity=proposal.source_identity: (
                self._report_task_failure(source_identity, completed_task)
            )
        )
        return execution_action_id

    def _report_task_failure(
        self,
        source_identity: str,
        completed: asyncio.Task[None],
    ) -> None:
        pending = self._tasks.get(source_identity)
        owns_pending_slot = pending is not None and pending.task is completed
        if owns_pending_slot:
            self._tasks.pop(source_identity, None)
        if completed.cancelled():
            return
        exception = completed.exception()
        if exception is None:
            if not owns_pending_slot or pending is None:
                return
            self._completed[source_identity] = (
                pending.proposal_digest,
                pending.execution_action_id,
            )
            self._completed.move_to_end(source_identity)
            while len(self._completed) > COMPLETED_PROPOSAL_KEY_LIMIT:
                self._completed.popitem(last=False)
        else:
            if self._failure_sink is not None:
                try:
                    self._failure_sink(exception)
                except Exception as sink_exception:
                    self._loop.call_exception_handler(
                        {
                            "message": "HALPHA_PRODUCT_PROPOSAL_FAILURE_SINK_FAILED",
                            "exception_type": type(sink_exception).__name__,
                        }
                    )
            else:
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
        self._completed.clear()


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


def _position_side_text(value: object) -> str:
    raw = getattr(value, "value", value)
    text = str(raw).upper().rsplit(".", 1)[-1]
    if text not in {"BOTH", "LONG", "SHORT"}:
        raise ProductPreSubmitRejected("POSITION_FACT_INVALID")
    return text


def _symbol_position_for_side(
    *,
    symbol: str,
    positions: object,
    position_side: str,
) -> Decimal:
    try:
        matches = [
            item
            for item in positions
            if str(getattr(item, "symbol")) == symbol
            and _position_side_text(getattr(item, "positionSide", "BOTH"))
            == position_side
        ]
        if not matches:
            # /fapi/v3/positionRisk can omit a symbol/side once it is flat.
            # This call site always supplies the complete account response, so
            # absence is an authoritative zero rather than an unknown fact.
            return Decimal("0")
        if len(matches) != 1:
            raise ProductPreSubmitRejected("POSITION_FACT_INVALID")
        return Decimal(str(getattr(matches[0], "positionAmt")))
    except ProductPreSubmitRejected:
        raise
    except (AttributeError, InvalidOperation, TypeError, ValueError):
        raise ProductPreSubmitRejected("POSITION_FACT_INVALID") from None


def _symbol_abs_position(*, symbol: str, positions: object) -> Decimal:
    return abs(_symbol_position(symbol=symbol, positions=positions))


def _called_algo_order_state_fact(
    *,
    action: ExecutionAction,
    algo_order: object,
    observed_at: datetime,
) -> VenueFact:
    status = _binance_query_status(getattr(algo_order, "algoStatus", None))
    if status == "FILLED":
        # A filled algo order must expose the generated ordinary identity so
        # its exact trades can be attributed.  A terminal status alone is not
        # enough to change the virtual position.
        raise ProductPreSubmitRejected("ACTION_ACTUAL_ORDER_ID_MISSING")
    venue_order_ref = str(getattr(algo_order, "algoId"))
    source_time = _millisecond_datetime(
        getattr(algo_order, "updateTime", None),
        code="ACTION_ORDER_TIME_INVALID",
    )
    payload: dict[str, Any] = {
        "event_type": "BinanceAlgoOrderQuery",
        "status": status,
        "client_order_id": action.client_order_id,
        "venue_order_ref": venue_order_ref,
        "venue_order_quantity": str(getattr(algo_order, "quantity", "")),
        "reconciliation": True,
    }
    if status in {"CANCELLED", "REJECTED", "EXPIRED"}:
        payload["cumulative_filled_quantity"] = "0"
    return build_venue_fact(
        venue_fact_id=str(
            uuid5(
                NAMESPACE_URL,
                (
                    f"urn:halpha:{action.environment_id}:called-algo-query:"
                    f"{action.execution_action_id}:{venue_order_ref}:"
                    f"{source_time.isoformat()}:{status}"
                ),
            )
        ),
        environment_id=action.environment_id,
        venue_ref=BINANCE_USDM_VENUE_REF,
        account_ref=action.account_ref,
        instrument_ref=str(action.action_terms["instrument_ref"]),
        kind=VenueFactKind.ORDER_STATE,
        source_class=VenueFactSourceClass.VENUE_QUERY,
        source_object_id=str(action.client_order_id),
        source_sequence=f"{venue_order_ref}:{source_time.isoformat()}:{status}",
        source_time=source_time,
        received_at=observed_at,
        cutoff=observed_at,
        payload=payload,
        action=action,
    )


def _called_order_query_facts(
    *,
    action: ExecutionAction,
    order: object,
    trades: object,
    observed_at: datetime,
) -> tuple[VenueFact, ...]:
    status = _binance_query_status(getattr(order, "status", None))
    venue_order_ref = str(getattr(order, "orderId"))
    source_time = _millisecond_datetime(
        getattr(order, "updateTime", None),
        code="ACTION_ORDER_TIME_INVALID",
    )
    executed_quantity = _optional_decimal(
        getattr(order, "executedQty", None),
        code="ACTION_EXECUTED_QUANTITY_INVALID",
    )
    order_payload: dict[str, Any] = {
        "event_type": "BinanceOrderQuery",
        "status": status,
        "client_order_id": action.client_order_id,
        "venue_order_ref": venue_order_ref,
        "venue_order_quantity": str(getattr(order, "origQty", "")),
        "cumulative_filled_quantity": canonical_decimal(executed_quantity),
        "reconciliation": True,
    }
    facts: list[VenueFact] = [
        build_venue_fact(
            venue_fact_id=str(
                uuid5(
                    NAMESPACE_URL,
                    (
                        f"urn:halpha:{action.environment_id}:called-order-query:"
                        f"{action.execution_action_id}:{venue_order_ref}:"
                        f"{source_time.isoformat()}:{status}:"
                        f"{canonical_decimal(executed_quantity)}"
                    ),
                )
            ),
            environment_id=action.environment_id,
            venue_ref=BINANCE_USDM_VENUE_REF,
            account_ref=action.account_ref,
            instrument_ref=str(action.action_terms["instrument_ref"]),
            kind=VenueFactKind.ORDER_STATE,
            source_class=VenueFactSourceClass.VENUE_QUERY,
            source_object_id=str(action.client_order_id),
            source_sequence=(
                f"{venue_order_ref}:{source_time.isoformat()}:{status}:"
                f"{canonical_decimal(executed_quantity)}"
            ),
            source_time=source_time,
            received_at=observed_at,
            cutoff=observed_at,
            payload=order_payload,
            action=action,
        )
    ]
    try:
        queried_trades = tuple(trades)
    except TypeError:
        raise ProductPreSubmitRejected("ACTION_TRADE_FACT_INVALID") from None
    total_trade_quantity = Decimal("0")
    for trade in queried_trades:
        trade_id_raw = getattr(trade, "id", None)
        if trade_id_raw is None:
            trade_id_raw = getattr(trade, "tradeId", None)
        if trade_id_raw is None:
            raise ProductPreSubmitRejected("ACTION_TRADE_ID_MISSING")
        trade_id = str(trade_id_raw)
        quantity = _required_positive_decimal(
            getattr(trade, "qty", None),
            code="ACTION_TRADE_QUANTITY_INVALID",
        )
        price = _required_positive_decimal(
            getattr(trade, "price", None),
            code="ACTION_TRADE_PRICE_INVALID",
        )
        trade_time = _millisecond_datetime(
            getattr(trade, "time", None),
            code="ACTION_TRADE_TIME_INVALID",
        )
        side = _binance_enum_text(
            getattr(trade, "side", None) or getattr(order, "side", None)
        )
        if side not in {"BUY", "SELL"}:
            raise ProductPreSubmitRejected("ACTION_TRADE_SIDE_INVALID")
        total_trade_quantity += quantity
        fill = build_venue_fact(
            venue_fact_id=str(uuid4()),
            environment_id=action.environment_id,
            venue_ref=BINANCE_USDM_VENUE_REF,
            account_ref=action.account_ref,
            instrument_ref=str(action.action_terms["instrument_ref"]),
            kind=VenueFactKind.FILL,
            source_class=VenueFactSourceClass.VENUE_QUERY,
            source_object_id=trade_id,
            source_sequence=f"{venue_order_ref}:{trade_id}",
            source_time=trade_time,
            received_at=observed_at,
            cutoff=observed_at,
            payload={
                "event_type": "BinanceUserTradeQuery",
                "trade_id": trade_id,
                "client_order_id": action.client_order_id,
                "venue_order_ref": venue_order_ref,
                "last_price": canonical_decimal(price),
                "last_quantity": canonical_decimal(quantity),
                "order_side": side,
                "liquidity_side": (
                    "MAKER" if getattr(trade, "maker", None) is True else "TAKER"
                ),
                "reconciliation": True,
            },
            action=action,
        )
        facts.append(
            fill.model_copy(update={"venue_fact_id": venue_trade_fact_id(fill)})
        )
        commission = _optional_decimal(
            getattr(trade, "commission", None),
            code="ACTION_TRADE_COMMISSION_INVALID",
        )
        currency = str(getattr(trade, "commissionAsset", "")).upper()
        if not currency:
            raise ProductPreSubmitRejected("ACTION_TRADE_COMMISSION_ASSET_MISSING")
        commission_fact = build_venue_fact(
            venue_fact_id=str(uuid4()),
            environment_id=action.environment_id,
            venue_ref=BINANCE_USDM_VENUE_REF,
            account_ref=action.account_ref,
            instrument_ref=str(action.action_terms["instrument_ref"]),
            kind=VenueFactKind.COMMISSION,
            source_class=VenueFactSourceClass.VENUE_QUERY,
            source_object_id=trade_id,
            source_sequence=f"{venue_order_ref}:{trade_id}:COMMISSION",
            source_time=trade_time,
            received_at=observed_at,
            cutoff=observed_at,
            payload={
                "event_type": "BinanceUserTradeQuery",
                "trade_id": trade_id,
                "client_order_id": action.client_order_id,
                "amount": f"{canonical_decimal(commission)} {currency}",
                "currency": currency,
                "reconciliation": True,
            },
            action=action,
        )
        facts.append(
            commission_fact.model_copy(
                update={"venue_fact_id": venue_trade_fact_id(commission_fact)}
            )
        )
    if total_trade_quantity != executed_quantity:
        raise ProductPreSubmitRejected("ACTION_TRADE_QUANTITY_MISMATCH")
    return tuple(facts)


def _binance_query_status(value: object) -> str:
    status = _binance_enum_text(value)
    if status in {
        "NEW",
        "PARTIALLY_FILLED",
        "PENDING_CANCEL",
        "TRIGGERING",
        "TRIGGERED",
    }:
        return "WORKING"
    if status in {"FILLED", "FINISHED"}:
        return "FILLED"
    if status == "CANCELED":
        return "CANCELLED"
    if status in {"REJECTED", "EXPIRED"}:
        return status
    if status == "EXPIRED_IN_MATCH":
        return "EXPIRED"
    raise ProductPreSubmitRejected("ACTION_ORDER_STATUS_INVALID")


def _binance_enum_text(value: object) -> str:
    return str(getattr(value, "value", value)).upper()


def _millisecond_datetime(value: object, *, code: str) -> datetime:
    try:
        timestamp_ms = int(str(value))
    except (TypeError, ValueError):
        raise ProductPreSubmitRejected(code) from None
    if timestamp_ms <= 0:
        raise ProductPreSubmitRejected(code)
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)


def _optional_decimal(value: object, *, code: str) -> Decimal:
    if value in {None, ""}:
        return Decimal("0")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ProductPreSubmitRejected(code) from None
    if not result.is_finite() or result < 0:
        raise ProductPreSubmitRejected(code)
    return result


def _required_positive_decimal(value: object, *, code: str) -> Decimal:
    result = _optional_decimal(value, code=code)
    if result <= 0:
        raise ProductPreSubmitRejected(code)
    return result


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
