"""Run the preregistered B04 development/holdout episode backtest."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import sys
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nautilus_trader.analysis import MaxDrawdown, ProfitFactor, ReportProvider, WinRate
from nautilus_trader.backtest.config import BacktestEngineConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.backtest.models import (
    LatencyModel,
    MakerTakerFeeModel,
    OneTickSlippageFillModel,
)
from nautilus_trader.common.config import LoggingConfig
from nautilus_trader.data.config import DataEngineConfig
from nautilus_trader.model.data import Bar
from nautilus_trader.model.enums import AccountType, OmsType, OrderSide, TriggerType
from nautilus_trader.model.events import OrderAccepted, OrderDenied, OrderFilled, OrderRejected
from nautilus_trader.model.identifiers import ClientOrderId
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from halpha.capital.checks import (
    check_action,
    compute_activation_loss,
    latch_max_loss,
)
from halpha.capital.models import (
    AccountCapitalLimitVersion,
    ActionCheckInput,
    AllocationStatus,
    AuthorityClass,
    EnvironmentKind,
    MachineAuthorizationVersion,
    PlanAllocation,
    RiskClass,
    StopCategory,
)
from halpha.domain_values import content_digest
from halpha.planning.adapter import HalphaStrategyAdapter, strategy_id_for_activation
from halpha.planning.bar_evaluation import EntrySizingSnapshot, NautilusBarEntryEvaluator
from halpha.planning.models import PlanActivation
from halpha.planning.registry import Direction, OneShotParameters
from halpha.planning.strategies.one_shot import (
    ActivationStrategyState,
    InstrumentQuantityRules,
    OneShotDonchianAtrLogic,
    StrategyProposal,
)
from halpha.planning.transitions import (
    consume_entry_opportunity,
    proposed_action_from_strategy_proposal,
    proposed_protection_from_fill,
    proposed_reduce_or_close_position,
    proposed_take_profits_from_fill,
    record_first_fill,
)
from tools.qualification.build_b04_historical_catalog import (
    BAR_TYPE,
    CATALOG_EVIDENCE_PATH,
    CATALOG_ROOT,
    PREREGISTRATION_PATH,
    _instrument,
    _load_verified,
)


EVIDENCE_PATH = ROOT / "build" / "qualification" / "b04-historical-backtest.json"
STARTING_EQUITY = Decimal("100000")
ONE_MINUTE = timedelta(minutes=1)
LATENCY_NANOS = {
    "base": 1_000_000,
    "insert": 2_000_000,
    "update": 3_000_000,
    "cancel": 4_000_000,
}
SOURCE_FILES = (
    "requirements/runtime.txt",
    "src/halpha/capital/checks.py",
    "src/halpha/capital/models.py",
    "src/halpha/domain_values.py",
    "src/halpha/planning/adapter.py",
    "src/halpha/planning/bar_evaluation.py",
    "src/halpha/planning/indicators.py",
    "src/halpha/planning/models.py",
    "src/halpha/planning/registry.py",
    "src/halpha/planning/strategies/one_shot.py",
    "src/halpha/planning/transitions.py",
    "tools/qualification/build_b04_historical_catalog.py",
    "tools/qualification/run_b04_historical_backtest.py",
)


class HistoricalBacktestError(RuntimeError):
    """Sanitized failure for the B04 historical backtest boundary."""


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _digest(value: object) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_sha256() -> dict[str, str]:
    return {relative: _file_digest(ROOT / relative) for relative in SOURCE_FILES}


def _source_binding_drift(
    expected: dict[str, str],
    actual: dict[str, str],
) -> list[dict[str, str | None]]:
    drift: list[dict[str, str | None]] = []
    for relative, expected_digest in sorted(expected.items()):
        actual_digest = actual.get(relative)
        if actual_digest != expected_digest:
            drift.append(
                {
                    "path": relative,
                    "reason": (
                        "SOURCE_FILE_NOT_IN_CURRENT_BINDING"
                        if actual_digest is None
                        else "SOURCE_SHA256_MISMATCH"
                    ),
                    "expected": expected_digest,
                    "actual": actual_digest,
                }
            )
    return drift


def _datetime_from_ns(timestamp_ns: int) -> datetime:
    seconds, nanoseconds = divmod(timestamp_ns, 1_000_000_000)
    return datetime.fromtimestamp(seconds, tz=UTC).replace(
        microsecond=nanoseconds // 1_000
    )


def _pnl_decimal(value: object) -> Decimal:
    text = str(value)
    return Decimal(text.split()[0])


def _finite_stat(value: object) -> float | None:
    if value is None:
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


class HistoricalEpisodeGateway:
    """Test-only post-proposal gateway; it is not a product runtime or writer."""

    def __init__(
        self,
        *,
        activation_id: str,
        period_name: str,
        parameters: OneShotParameters,
        decision_start: datetime,
        valid_until: datetime,
        period_end: datetime,
        instrument_rules: dict[str, Any],
    ) -> None:
        self.activation_id = activation_id
        self.period_name = period_name
        self.parameters = parameters
        self.decision_start = decision_start
        self.valid_until = valid_until
        self.period_end = period_end
        self.instrument_rules = instrument_rules
        self.activation = PlanActivation(
            activation_id=activation_id,
            environment_id=f"b04-historical-{period_name}",
            environment_kind=EnvironmentKind.DEMO,
            authority_class=AuthorityClass.DEMO_VALIDATION,
            plan_version_ref="b04-historical-plan-v1",
            authorization_version_ref=f"auth-{activation_id}",
            allocation_ref=f"allocation-{activation_id}",
            account_ref="b04-historical-evidence-account",
            instrument_ref="BTCUSDT-PERP",
            direction=parameters.direction,
            strategy_id="ONE_SHOT_DONCHIAN_ATR_BREAKOUT",
            framework_strategy_id=strategy_id_for_activation(activation_id),
            target_exposure="0",
            rule_state={},
            created_at=decision_start,
            updated_at=decision_start,
        )
        self.account = AccountCapitalLimitVersion(
            environment_id=self.activation.environment_id,
            environment_kind=EnvironmentKind.DEMO,
            authority_class=AuthorityClass.DEMO_VALIDATION,
            capital_limit_version_id="b04-historical-capital-v1",
            account_ref=self.activation.account_ref,
            quote_asset="USDT",
            version=1,
            effective_at=decision_start,
            max_margin="100",
            max_notional="500",
            max_allowed_loss="50",
            max_action_notional="500",
            scope={"purpose": "HISTORICAL_TECHNICAL_EVIDENCE"},
            content_digest=content_digest({"capital": "b04-historical-v1"}),
        )
        self.authorization = MachineAuthorizationVersion(
            environment_id=self.activation.environment_id,
            environment_kind=EnvironmentKind.DEMO,
            authority_class=AuthorityClass.DEMO_VALIDATION,
            authorization_version_id=self.activation.authorization_version_ref,
            activation_id=activation_id,
            plan_version_ref=self.activation.plan_version_ref,
            account_ref=self.activation.account_ref,
            instrument_ref=self.activation.instrument_ref,
            direction=parameters.direction.value,
            version=1,
            valid_from=decision_start,
            valid_until=period_end + ONE_MINUTE,
            allowed_actions=frozenset(
                {
                    "ENTRY_MARKET",
                    "PROTECTIVE_STOP_REDUCE_ONLY",
                    "TAKE_PROFIT_1",
                    "TAKE_PROFIT_2",
                    "REDUCE_OR_CLOSE_MARKET",
                }
            ),
            terms={"funding_model": "NOT_MODELED"},
            content_digest=content_digest({"authorization": activation_id}),
        )
        self.allocation = PlanAllocation(
            environment_id=self.activation.environment_id,
            environment_kind=EnvironmentKind.DEMO,
            authority_class=AuthorityClass.DEMO_VALIDATION,
            allocation_id=self.activation.allocation_ref,
            activation_id=activation_id,
            capital_limit_version_ref=self.account.capital_limit_version_id,
            quote_asset="USDT",
            max_margin="100",
            max_notional="500",
            max_allowed_loss="50",
            status=AllocationStatus.HELD,
        )
        self.adapter: HalphaStrategyAdapter | None = None
        self.engine: BacktestEngine | None = None
        self.entry_order_id: str | None = None
        self.exit_order_ids: set[str] = set()
        self.order_profiles: dict[str, str] = {}
        self.accepted_order_ids: set[str] = set()
        self.protection_order_id: str | None = None
        self.proposal: StrategyProposal | None = None
        self.cap_decisions: list[dict[str, Any]] = []
        self.entry_filled_quantity = Decimal("0")
        self.exit_filled_quantity = Decimal("0")
        self.target_bars_after_fill = 0
        self.time_exit_submitted = False
        self.max_loss_exit_submitted = False
        self.commission_total = Decimal("0")
        self.expired_without_entry = False
        self.closed = False
        self.closed_at: datetime | None = None
        self.first_fill_at: datetime | None = None
        self.rejections: list[str] = []
        self.unhandled_rejections: list[str] = []
        self.protection_gap_at: datetime | None = None
        self.protection_gap_exit_submitted_at: datetime | None = None
        self.direct_write_attempts = 0

    def bind(self, adapter: HalphaStrategyAdapter, engine: BacktestEngine) -> None:
        self.adapter = adapter
        self.engine = engine

    def strategy_state(self) -> ActivationStrategyState:
        return ActivationStrategyState(
            entry_opportunity_consumed=self.activation.entry_opportunity_consumed,
            lifecycle=self.activation.lifecycle.value,
            run_state=self.activation.run_state.value,
            new_risk_allowed=not self.activation.entry_opportunity_consumed,
        )

    def _cap_check(
        self,
        *,
        profile: str,
        risk_class: RiskClass,
        quantity: str,
        price: str,
        current_position: str,
        post_position: str,
        checked_at: datetime,
    ) -> None:
        category = (
            StopCategory.NEW_FUNDING
            if risk_class is RiskClass.RISK_INCREASING
            else StopCategory.PROTECTION
            if profile == "PROTECTIVE_STOP_REDUCE_ONLY"
            else StopCategory.RISK_REDUCTION_OR_ORDER_MANAGEMENT
        )
        decision = check_action(
            ActionCheckInput(
                environment_id=self.activation.environment_id,
                environment_kind=EnvironmentKind.DEMO,
                authority_class=AuthorityClass.DEMO_VALIDATION,
                activation_id=self.activation_id,
                account_ref=self.activation.account_ref,
                instrument_ref=self.activation.instrument_ref,
                action_profile=profile,
                control_category=category,
                risk_class=risk_class,
                checked_at=checked_at,
                quantized_quantity=quantity,
                conservative_price=price,
                account_dynamic_available_margin="100000",
                actual_margin_mode="ISOLATED",
                actual_leverage="5",
                current_abs_position=current_position,
                post_action_abs_position=post_position,
                would_reverse_position=False,
            ),
            account=self.account,
            authorization=self.authorization,
            allocation=self.allocation,
        )
        self.cap_decisions.append(decision.model_dump(mode="json"))
        if not decision.accepted:
            raise HistoricalBacktestError(f"CAP_REJECTED:{decision.reason_code}")

    def proposal_sink(self, proposal: StrategyProposal) -> None:
        if self.adapter is None:
            raise HistoricalBacktestError("EPISODE_ADAPTER_NOT_BOUND")
        if self.proposal is not None:
            raise HistoricalBacktestError("ONE_SHOT_PROPOSAL_REPEATED")
        proposed = proposed_action_from_strategy_proposal(self.activation, proposal)
        if proposed.quantity is None:
            raise HistoricalBacktestError("ENTRY_QUANTITY_MISSING")
        self._cap_check(
            profile=proposed.action_profile,
            risk_class=RiskClass.RISK_INCREASING,
            quantity=proposed.quantity,
            price=proposal.reference_price,
            current_position="0",
            post_position=proposed.quantity,
            checked_at=proposal.source_cutoff,
        )
        self.proposal = proposal
        self.activation = consume_entry_opportunity(
            self.activation,
            observed_at=proposal.source_cutoff,
        )
        side = OrderSide.BUY if proposal.direction is Direction.LONG else OrderSide.SELL
        order = self.adapter.order_factory.market(
            instrument_id=self.adapter._bar_evaluator.source_bar_type.instrument_id,
            order_side=side,
            quantity=Quantity.from_str(self._venue_quantity(proposed.quantity)),
        )
        self.entry_order_id = str(order.client_order_id)
        self.order_profiles[self.entry_order_id] = "ENTRY_MARKET"
        self.adapter.submit_order(order)

    def _submit_exit_action(
        self,
        *,
        profile: str,
        quantity: str,
        trigger_price: str | None,
        checked_at: datetime,
    ) -> str:
        if self.adapter is None:
            raise HistoricalBacktestError("EPISODE_ADAPTER_NOT_BOUND")
        remaining = max(self.entry_filled_quantity - self.exit_filled_quantity, Decimal("0"))
        self._cap_check(
            profile=profile,
            risk_class=RiskClass.RISK_REDUCING,
            quantity=quantity,
            price=trigger_price or (self.proposal.reference_price if self.proposal else "1"),
            current_position=str(remaining),
            post_position="0",
            checked_at=checked_at,
        )
        side = OrderSide.SELL if self.parameters.direction is Direction.LONG else OrderSide.BUY
        instrument_id = self.adapter._bar_evaluator.source_bar_type.instrument_id
        venue_quantity = self._venue_quantity(quantity)
        venue_trigger = self._venue_price(trigger_price) if trigger_price is not None else None
        if profile == "PROTECTIVE_STOP_REDUCE_ONLY":
            order = self.adapter.order_factory.stop_market(
                instrument_id=instrument_id,
                order_side=side,
                quantity=Quantity.from_str(venue_quantity),
                trigger_price=Price.from_str(venue_trigger),
                trigger_type=TriggerType.LAST_PRICE,
                reduce_only=True,
            )
        elif profile in {"TAKE_PROFIT_1", "TAKE_PROFIT_2"}:
            order = self.adapter.order_factory.market_if_touched(
                instrument_id=instrument_id,
                order_side=side,
                quantity=Quantity.from_str(venue_quantity),
                trigger_price=Price.from_str(venue_trigger),
                trigger_type=TriggerType.LAST_PRICE,
                reduce_only=True,
            )
        elif profile == "REDUCE_OR_CLOSE_MARKET":
            order = self.adapter.order_factory.market(
                instrument_id=instrument_id,
                order_side=side,
                quantity=Quantity.from_str(venue_quantity),
                reduce_only=True,
            )
        else:
            raise HistoricalBacktestError("HISTORICAL_EXIT_PROFILE_INVALID")
        identity = str(order.client_order_id)
        self.exit_order_ids.add(identity)
        self.order_profiles[identity] = profile
        self.adapter.submit_order(order)
        return identity

    def _venue_quantity(self, value: str) -> str:
        return format(
            Decimal(value),
            f".{int(self.instrument_rules['quantity_precision'])}f",
        )

    def _venue_price(self, value: str) -> str:
        return format(
            Decimal(value),
            f".{int(self.instrument_rules['price_precision'])}f",
        )

    def _submit_initial_protection_and_targets(self, event: OrderFilled) -> None:
        if self.proposal is None or self.proposal.entry_risk_context is None:
            raise HistoricalBacktestError("ENTRY_RISK_CONTEXT_MISSING")
        fill_time = _datetime_from_ns(event.ts_event)
        self.activation = record_first_fill(
            self.activation,
            entry_action_ref=self.entry_order_id,
            fill_fact_ref=f"BACKTEST_FILL:{event.trade_id}",
            fill_price=str(event.last_px),
            fill_time=fill_time,
            entry_risk_context=self.proposal.entry_risk_context.model_dump(mode="json"),
            observed_at=fill_time,
        )
        fill_quantity = str(event.last_qty)
        protection = proposed_protection_from_fill(
            self.activation,
            entry_action_ref=self.entry_order_id,
            fill_fact_ref=f"BACKTEST_FILL:{event.trade_id}",
            fill_source_identity=f"BACKTEST_FILL:{event.trade_id}",
            fill_quantity=fill_quantity,
        )
        self.protection_order_id = self._submit_exit_action(
            profile=protection.action_profile,
            quantity=protection.quantity,
            trigger_price=protection.trigger_price,
            checked_at=fill_time,
        )
        if self.protection_gap_exit_submitted_at is not None:
            return
        take_profits = proposed_take_profits_from_fill(
            self.activation,
            entry_action_ref=self.entry_order_id,
            protection_action_ref=self.protection_order_id,
            fill_fact_ref=f"BACKTEST_FILL:{event.trade_id}",
            fill_source_identity=f"BACKTEST_FILL:{event.trade_id}",
            fill_quantity=fill_quantity,
        )
        for action in take_profits:
            self._submit_exit_action(
                profile=action.action_profile,
                quantity=action.quantity,
                trigger_price=action.trigger_price,
                checked_at=fill_time,
            )

    def event_sink(self, event: object) -> None:
        if isinstance(event, OrderAccepted):
            self.accepted_order_ids.add(str(event.client_order_id))
            return
        if isinstance(event, (OrderDenied, OrderRejected)):
            identity = str(event.client_order_id)
            profile = self.order_profiles.get(identity, "UNKNOWN_PROFILE")
            rejection = (
                f"{profile}:"
                f"{type(event).__name__}:{getattr(event, 'reason', 'UNKNOWN_REASON')}"
            )
            self.rejections.append(rejection)
            observed_at = _datetime_from_ns(
                getattr(event, "ts_event", event.ts_init)
            )
            if profile == "PROTECTIVE_STOP_REDUCE_ONLY":
                self.protection_gap_at = observed_at
                self._submit_protection_gap_exit(observed_at)
            elif profile in {"TAKE_PROFIT_1", "TAKE_PROFIT_2"} and (
                self.protection_order_id in self.accepted_order_ids
                or self.protection_gap_exit_submitted_at is not None
            ):
                pass
            else:
                self.unhandled_rejections.append(rejection)
            return
        if not isinstance(event, OrderFilled):
            return
        self.commission_total += _pnl_decimal(event.commission)
        identity = str(event.client_order_id)
        event_time = _datetime_from_ns(event.ts_event)
        if identity == self.entry_order_id:
            self.entry_filled_quantity += Decimal(str(event.last_qty))
            if self.first_fill_at is None:
                self.first_fill_at = event_time
                self._submit_initial_protection_and_targets(event)
            return
        if identity in self.exit_order_ids:
            self.exit_filled_quantity += Decimal(str(event.last_qty))
            if self.exit_filled_quantity >= self.entry_filled_quantity:
                self.closed = True
                self.closed_at = event_time
                self._cancel_open_exit_orders()

    def _cancel_open_exit_orders(self) -> None:
        if self.adapter is None:
            return
        for identity in tuple(self.exit_order_ids):
            order = self.adapter.cache.order(ClientOrderId(identity))
            if order is not None and order.is_open:
                self.adapter.cancel_order(order)

    def _submit_time_exit(self, observed_at: datetime) -> None:
        if self.time_exit_submitted or self.adapter is None:
            return
        remaining = self.entry_filled_quantity - self.exit_filled_quantity
        if remaining <= 0:
            return
        self.time_exit_submitted = True
        self._cancel_open_exit_orders()
        proposed = proposed_reduce_or_close_position(
            self.activation,
            position_quantity=str(remaining),
            causation_ref=f"TIME_EXIT:{observed_at.isoformat()}",
            position_fact_ref=f"BACKTEST_POSITION:{observed_at.isoformat()}",
        )
        self._submit_exit_action(
            profile=proposed.action_profile,
            quantity=proposed.quantity,
            trigger_price=None,
            checked_at=observed_at,
        )

    def _submit_protection_gap_exit(self, observed_at: datetime) -> None:
        if self.protection_gap_exit_submitted_at is not None:
            return
        remaining = self.entry_filled_quantity - self.exit_filled_quantity
        if remaining <= 0:
            return
        self.protection_gap_exit_submitted_at = observed_at
        self._cancel_open_exit_orders()
        proposed = proposed_reduce_or_close_position(
            self.activation,
            position_quantity=str(remaining),
            causation_ref=f"PROTECTION_GAP_EXIT:{observed_at.isoformat()}",
            position_fact_ref=f"BACKTEST_POSITION:{observed_at.isoformat()}",
        )
        self._submit_exit_action(
            profile=proposed.action_profile,
            quantity=proposed.quantity,
            trigger_price=None,
            checked_at=observed_at,
        )

    def _check_max_loss(self, observed_at: datetime) -> None:
        if (
            self.engine is None
            or self.adapter is None
            or self.first_fill_at is None
            or self.closed
            or self.max_loss_exit_submitted
        ):
            return
        instrument_id = self.adapter._bar_evaluator.source_bar_type.instrument_id
        realized = self.engine.portfolio.realized_pnl(instrument_id)
        unrealized = self.engine.portfolio.unrealized_pnl(instrument_id)
        if realized is None or unrealized is None:
            return
        activation_loss = compute_activation_loss(
            realized_pnl=str(_pnl_decimal(realized)),
            unrealized_pnl=str(_pnl_decimal(unrealized)),
            funding="0",
            commission=str(self.commission_total),
        )
        self.allocation = latch_max_loss(
            self.allocation,
            activation_loss=activation_loss,
            fact_cutoff=observed_at,
            funding_query_cutoff=observed_at,
            fact_digest=content_digest(
                {
                    "source": "BACKTEST_PORTFOLIO_PROJECTION",
                    "realized": str(realized),
                    "unrealized": str(unrealized),
                    "commission": str(self.commission_total),
                    "cutoff": observed_at,
                }
            ),
        )
        if self.allocation.max_loss_reached:
            remaining = self.entry_filled_quantity - self.exit_filled_quantity
            if remaining > 0:
                self.max_loss_exit_submitted = True
                self._cancel_open_exit_orders()
                proposed = proposed_reduce_or_close_position(
                    self.activation,
                    position_quantity=str(remaining),
                    causation_ref=f"MAX_LOSS_EXIT:{observed_at.isoformat()}",
                    position_fact_ref=f"BACKTEST_POSITION:{observed_at.isoformat()}",
                )
                self._submit_exit_action(
                    profile=proposed.action_profile,
                    quantity=proposed.quantity,
                    trigger_price=None,
                    checked_at=observed_at,
                )

    def bar_sink(self, bar: object) -> None:
        if self.engine is None or self.adapter is None:
            return
        observed_at = _datetime_from_ns(bar.ts_event)
        if str(bar.bar_type) == str(self.adapter._bar_evaluator.source_bar_type):
            self._check_max_loss(observed_at)
        if (
            self.entry_order_id is None
            and str(bar.bar_type) == str(self.adapter._bar_evaluator.source_bar_type)
            and observed_at >= self.valid_until
        ):
            self.expired_without_entry = True
            return
        if (
            self.first_fill_at is not None
            and not self.closed
            and str(bar.bar_type)
            == str(self.adapter._bar_evaluator.target_bar_type.standard())
            and observed_at > self.first_fill_at
        ):
            self.target_bars_after_fill += 1
            if self.target_bars_after_fill >= self.parameters.max_hold_bars_15m:
                self._submit_time_exit(observed_at)


def _engine(instrument: object) -> BacktestEngine:
    engine = BacktestEngine(
        BacktestEngineConfig(
            data_engine=DataEngineConfig(
                time_bars_interval_type="left-open",
                time_bars_timestamp_on_close=True,
                time_bars_skip_first_non_full_bar=True,
                time_bars_build_with_no_updates=False,
                validate_data_sequence=True,
            ),
            logging=LoggingConfig(log_level="ERROR", bypass_logging=True),
            run_analysis=True,
        )
    )
    engine.add_venue(
        venue=instrument.id.venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        starting_balances=[Money.from_str(f"{STARTING_EQUITY} USDT")],
        base_currency=None,
        default_leverage=Decimal("5"),
        fill_model=OneTickSlippageFillModel(),
        fee_model=MakerTakerFeeModel(),
        latency_model=LatencyModel(
            base_latency_nanos=LATENCY_NANOS["base"],
            insert_latency_nanos=LATENCY_NANOS["insert"],
            update_latency_nanos=LATENCY_NANOS["update"],
            cancel_latency_nanos=LATENCY_NANOS["cancel"],
        ),
        use_reduce_only=True,
        bar_execution=True,
        bar_adaptive_high_low_ordering=True,
        liquidity_consumption=False,
    )
    engine.add_instrument(instrument)
    engine.portfolio.analyzer.register_statistic(ProfitFactor())
    engine.portfolio.analyzer.register_statistic(MaxDrawdown())
    engine.portfolio.analyzer.register_statistic(WinRate())
    return engine


def _run_episode(
    *,
    catalog: ParquetDataCatalog,
    instrument: object,
    parameters: OneShotParameters,
    rules: dict[str, Any],
    period_name: str,
    period_start: datetime,
    period_end: datetime,
    decision_start: datetime,
) -> tuple[dict[str, Any], datetime]:
    activation_id = str(
        uuid5(
            NAMESPACE_URL,
            f"urn:halpha:b04:historical:{period_name}:{decision_start.isoformat()}",
        )
    )
    valid_until = min(
        decision_start + timedelta(minutes=parameters.entry_valid_minutes),
        period_end,
    )
    warmup = timedelta(minutes=parameters.channel_lookback_15m * 15 + 15)
    query_start = max(period_start, decision_start - warmup)
    query_end = min(
        period_end,
        valid_until + timedelta(minutes=parameters.max_hold_bars_15m * 15 + 15),
    )
    bars = catalog.query(
        Bar,
        identifiers=[str(BAR_TYPE)],
        start=query_start,
        end=query_end,
    )
    if not bars:
        raise HistoricalBacktestError("EPISODE_DATA_EMPTY")
    gateway = HistoricalEpisodeGateway(
        activation_id=activation_id,
        period_name=period_name,
        parameters=parameters,
        decision_start=decision_start,
        valid_until=valid_until,
        period_end=period_end,
        instrument_rules=rules,
    )
    evaluator = NautilusBarEntryEvaluator(
        activation_id=activation_id,
        instrument_ref="BTCUSDT-PERP",
        parameters=parameters,
        decision_not_before=decision_start,
        valid_until=valid_until,
        sizing_provider=lambda bar: EntrySizingSnapshot(
            reference_price=str(bar.close),
            reference_source="BACKTEST_LAST_BAR_PROXY",
            max_allowed_loss="50",
            max_notional="500",
            max_margin="100",
            effective_leverage="5",
            taker_fee_rate="0.0006",
            rules=InstrumentQuantityRules(
                step_size=rules["market_step_size"],
                price_tick_size=rules["price_tick_size"],
                min_quantity=rules["market_min_quantity"],
                max_market_quantity=rules["market_max_quantity"],
                min_notional=rules["min_notional"],
            ),
        ),
    )
    adapter = HalphaStrategyAdapter(
        activation_id=activation_id,
        logic=OneShotDonchianAtrLogic(parameters),
        state_provider=gateway.strategy_state,
        proposal_sink=gateway.proposal_sink,
        bar_evaluator=evaluator,
        execution_event_sink=gateway.event_sink,
        bar_event_sink=gateway.bar_sink,
    )
    engine = _engine(instrument)
    gateway.bind(adapter, engine)
    engine.add_data(bars)
    engine.add_strategy(adapter)
    try:
        engine.run()
        positions = engine.cache.positions()
        closed_positions = engine.cache.positions_closed()
        reporter = ReportProvider()
        orders_report = reporter.generate_orders_report(engine.cache.orders())
        fills_report = reporter.generate_order_fills_report(engine.cache.orders())
        positions_report = reporter.generate_positions_report(positions)
        realized_pnl = (
            sum((_pnl_decimal(item.realized_pnl) for item in closed_positions), Decimal("0"))
            if closed_positions
            else None
        )
        terminal_at = gateway.closed_at or valid_until
        terminal = (
            "CLOSED"
            if gateway.closed
            else "EXPIRED_NO_ENTRY"
            if gateway.entry_order_id is None
            else "INCOMPLETE_OPEN_POSITION"
        )
        result = {
            "activation_id": activation_id,
            "decision_start": decision_start.isoformat().replace("+00:00", "Z"),
            "valid_until": valid_until.isoformat().replace("+00:00", "Z"),
            "terminal": terminal,
            "terminal_at": terminal_at.isoformat().replace("+00:00", "Z"),
            "proposal_count": 1 if gateway.proposal is not None else 0,
            "entry_fill_quantity": str(gateway.entry_filled_quantity),
            "exit_fill_quantity": str(gateway.exit_filled_quantity),
            "cap_check_count": len(gateway.cap_decisions),
            "cap_all_accepted": all(item["accepted"] for item in gateway.cap_decisions),
            "protection_submitted": gateway.protection_order_id is not None,
            "protection_accepted": (
                gateway.protection_order_id in gateway.accepted_order_ids
                if gateway.protection_order_id is not None
                else False
            ),
            "order_rejections": gateway.rejections,
            "unhandled_order_rejections": gateway.unhandled_rejections,
            "protection_gap_at": (
                gateway.protection_gap_at.isoformat().replace("+00:00", "Z")
                if gateway.protection_gap_at is not None
                else None
            ),
            "protection_gap_exit_submitted_at": (
                gateway.protection_gap_exit_submitted_at.isoformat().replace("+00:00", "Z")
                if gateway.protection_gap_exit_submitted_at is not None
                else None
            ),
            "protection_gap_exit_within_30_seconds": (
                gateway.protection_gap_at is not None
                and gateway.protection_gap_exit_submitted_at is not None
                and gateway.protection_gap_exit_submitted_at
                <= gateway.protection_gap_at + timedelta(seconds=30)
            ),
            "time_exit_submitted": gateway.time_exit_submitted,
            "max_loss_reached": gateway.allocation.max_loss_reached,
            "max_loss_exit_submitted": gateway.max_loss_exit_submitted,
            "report_provider": {
                "orders_rows": len(orders_report),
                "fills_rows": len(fills_report),
                "positions_rows": len(positions_report),
            },
            "realized_pnl_usdt": str(realized_pnl) if realized_pnl is not None else None,
            "net_r": (
                str(realized_pnl / Decimal("50")) if realized_pnl is not None else None
            ),
            "one_shot_no_reentry": gateway.proposal is None or gateway.entry_order_id is not None,
            "product_records_created": False,
        }
    finally:
        engine.dispose()
    next_start = terminal_at + ONE_MINUTE
    if next_start <= decision_start:
        raise HistoricalBacktestError("EPISODE_CURSOR_DID_NOT_ADVANCE")
    return result, next_start


def _period_summary(
    *,
    name: str,
    catalog: ParquetDataCatalog,
    instrument: object,
    parameters: OneShotParameters,
    rules: dict[str, Any],
    start: datetime,
    end: datetime,
    max_episodes: int | None,
) -> dict[str, Any]:
    warmup = timedelta(minutes=parameters.channel_lookback_15m * 15 + 15)
    cursor = start + warmup
    episodes: list[dict[str, Any]] = []
    while cursor < end and (max_episodes is None or len(episodes) < max_episodes):
        episode, cursor = _run_episode(
            catalog=catalog,
            instrument=instrument,
            parameters=parameters,
            rules=rules,
            period_name=name,
            period_start=start,
            period_end=end,
            decision_start=cursor,
        )
        episodes.append(episode)
        if len(episodes) % 100 == 0:
            print(
                json.dumps(
                    {
                        "period": name,
                        "episodes": len(episodes),
                        "cursor": cursor.isoformat(),
                    },
                    sort_keys=True,
                ),
                file=sys.stderr,
                flush=True,
            )
    pnls = [
        Decimal(item["realized_pnl_usdt"])
        for item in episodes
        if item["realized_pnl_usdt"] is not None
    ]
    raw_returns = {
        index: float(value / STARTING_EQUITY)
        for index, value in enumerate(pnls, start=1)
    }
    completed_interval = cursor >= end
    return {
        "period": name,
        "start": start.isoformat().replace("+00:00", "Z"),
        "end": end.isoformat().replace("+00:00", "Z"),
        "completed_interval": completed_interval,
        "cursor_at_end": cursor.isoformat().replace("+00:00", "Z"),
        "episode_count": len(episodes),
        "closed_episode_count": sum(item["terminal"] == "CLOSED" for item in episodes),
        "no_entry_episode_count": sum(
            item["terminal"] == "EXPIRED_NO_ENTRY" for item in episodes
        ),
        "incomplete_episode_count": sum(
            item["terminal"] == "INCOMPLETE_OPEN_POSITION" for item in episodes
        ),
        "profit_factor": _finite_stat(
            ProfitFactor().calculate_from_returns(raw_returns) if raw_returns else None
        ),
        "max_drawdown_return": _finite_stat(
            MaxDrawdown().calculate_from_returns(raw_returns) if raw_returns else None
        ),
        "win_rate": _finite_stat(
            WinRate().calculate_from_realized_pnls([float(value) for value in pnls])
            if pnls
            else None
        ),
        "average_net_r": (
            str(sum((value / Decimal("50") for value in pnls), Decimal("0")) / len(pnls))
            if pnls
            else None
        ),
        "total_realized_pnl_usdt": str(sum(pnls, Decimal("0"))),
        "episodes": episodes,
        "episode_digest": _digest(episodes),
    }


def main() -> int:
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    partial_limit_text = os.environ.get("HALPHA_B04_HISTORICAL_MAX_EPISODES")
    partial_limit = int(partial_limit_text) if partial_limit_text else None
    source_sha256_at_start: dict[str, str] | None = None
    try:
        source_sha256_at_start = _source_sha256()
        preregistration = _load_verified(PREREGISTRATION_PATH)
        catalog_evidence = _load_verified(CATALOG_EVIDENCE_PATH)
        if catalog_evidence["status"] != "QUALIFIED":
            raise HistoricalBacktestError("HISTORICAL_CATALOG_NOT_QUALIFIED")
        if (
            catalog_evidence["preregistration_digest"]
            != preregistration["evidence_digest"]
        ):
            raise HistoricalBacktestError("HISTORICAL_MANIFEST_BINDING_MISMATCH")
        preregistration_source_sha256 = preregistration.get("source_digests")
        if not isinstance(preregistration_source_sha256, dict) or not all(
            isinstance(relative, str) and isinstance(digest, str)
            for relative, digest in preregistration_source_sha256.items()
        ):
            raise HistoricalBacktestError("PREREGISTRATION_SOURCE_BINDING_INVALID")
        preregistration_source_drift = _source_binding_drift(
            preregistration_source_sha256,
            source_sha256_at_start,
        )
        parameters = OneShotParameters.model_validate(
            preregistration["strategy"]["parameters"]
        )
        instrument = _instrument(preregistration["instrument_rules"])
        catalog = ParquetDataCatalog(CATALOG_ROOT)
        development = _period_summary(
            name="development",
            catalog=catalog,
            instrument=instrument,
            parameters=parameters,
            rules=preregistration["instrument_rules"],
            start=datetime(2022, 1, 1, tzinfo=UTC),
            end=datetime(2025, 1, 1, tzinfo=UTC),
            max_episodes=partial_limit,
        )
        holdout = _period_summary(
            name="holdout",
            catalog=catalog,
            instrument=instrument,
            parameters=parameters,
            rules=preregistration["instrument_rules"],
            start=datetime(2025, 1, 1, tzinfo=UTC),
            end=datetime(2026, 7, 1, tzinfo=UTC),
            max_episodes=partial_limit,
        )
        completed = development["completed_interval"] and holdout["completed_interval"]
        all_episodes = [*development["episodes"], *holdout["episodes"]]
        closed_count = sum(item["terminal"] == "CLOSED" for item in all_episodes)
        technical_errors: list[str] = []
        if not completed:
            technical_errors.append("FULL_INTERVAL_NOT_COMPLETED")
        if closed_count < 30:
            technical_errors.append("TARGET_SAMPLE_BELOW_30")
        if any(item["terminal"] == "INCOMPLETE_OPEN_POSITION" for item in all_episodes):
            technical_errors.append("INCOMPLETE_OPEN_POSITION")
        if any(not item["one_shot_no_reentry"] for item in all_episodes):
            technical_errors.append("ONE_SHOT_INVARIANT_FAILED")
        traded = [item for item in all_episodes if item["proposal_count"] == 1]
        if any(not item["cap_all_accepted"] for item in traded):
            technical_errors.append("CAP_BRIDGE_REJECTED")
        if any(not item["protection_submitted"] for item in traded):
            technical_errors.append("PROTECTION_NOT_SUBMITTED")
        if any(
            not item["protection_accepted"]
            and not item["protection_gap_exit_within_30_seconds"]
            for item in traded
        ):
            technical_errors.append("PROTECTION_NOT_ACCEPTED_OR_GAP_EXIT_MISSED")
        if any(item["unhandled_order_rejections"] for item in traded):
            technical_errors.append("UNHANDLED_BACKTEST_ORDER_REJECTION")
        source_sha256_at_end = _source_sha256()
        source_stable_during_run = source_sha256_at_end == source_sha256_at_start
        if not source_stable_during_run:
            technical_errors.append("SOURCE_CHANGED_DURING_BACKTEST")
        holdout_interpretation = (
            "ORIGINAL_PREREGISTERED_SOURCE"
            if not preregistration_source_drift
            else "CURRENT_SOURCE_TECHNICAL_REVALIDATION_AFTER_HOLDOUT_EXPOSURE"
        )
        evidence: dict[str, Any] = {
            "schema_version": 1,
            "stage": "B04_HISTORICAL_DEVELOPMENT_HOLDOUT",
            "status": "QUALIFIED" if not technical_errors else "INSUFFICIENT",
            "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "preregistration_digest": preregistration["evidence_digest"],
            "catalog_evidence_digest": catalog_evidence["evidence_digest"],
            "source_sha256": source_sha256_at_start,
            "preregistration_source_binding": {
                "matches_current_source": not preregistration_source_drift,
                "drift": preregistration_source_drift,
                "holdout_interpretation": holdout_interpretation,
            },
            "adapter_class": "halpha.planning.adapter.HalphaStrategyAdapter",
            "pure_logic_class": "halpha.planning.strategies.one_shot.OneShotDonchianAtrLogic",
            "proposal_bridge": "proposed_action_from_strategy_proposal",
            "cap_bridge": "halpha.capital.checks.check_action",
            "engine": "nautilus_trader.backtest.engine.BacktestEngine",
            "reporter": "nautilus_trader.analysis.ReportProvider",
            "statistics": ["ProfitFactor", "MaxDrawdown", "WinRate"],
            "funding_model": "NOT_MODELED",
            "funding_data_injected": False,
            "episode_rule": "NEXT_EPISODE_ONLY_AFTER_PREVIOUS_CLOSED_OR_EXPIRED",
            "partial_diagnostic_limit": partial_limit,
            "development": development,
            "holdout": holdout,
            "performance_difference": {
                "development_average_net_r": development["average_net_r"],
                "holdout_average_net_r": holdout["average_net_r"],
                "development_profit_factor": development["profit_factor"],
                "holdout_profit_factor": holdout["profit_factor"],
                "independent_unexposed_holdout": not preregistration_source_drift,
                "holdout_interpretation": holdout_interpretation,
                "not_an_authorization_or_profit_guarantee": True,
            },
            "technical_safety": {
                "closed_episode_count": closed_count,
                "target_sample_at_least_30": closed_count >= 30,
                "full_intervals_completed": completed,
                "same_adapter_and_logic": True,
                "all_proposals_use_tradeplan_and_cap_bridge": True,
                "product_records_created": False,
                "parallel_strategy_or_execution_runtime_created": False,
                "historical_net_excludes_funding": True,
                "current_source_bound": True,
                "source_stable_during_run": source_stable_during_run,
            },
            "errors": technical_errors,
        }
    except Exception as exc:
        evidence = {
            "schema_version": 1,
            "stage": "B04_HISTORICAL_DEVELOPMENT_HOLDOUT",
            "status": "REJECTED",
            "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "funding_model": "NOT_MODELED",
            "funding_data_injected": False,
            "errors": [f"HISTORICAL_BACKTEST_FAILED:{type(exc).__name__}"],
        }
        if source_sha256_at_start is not None:
            evidence["source_sha256"] = source_sha256_at_start
    evidence["evidence_digest"] = _digest(evidence)
    EVIDENCE_PATH.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary = {
        "status": evidence["status"],
        "evidence_digest": evidence["evidence_digest"],
        "development_episodes": evidence.get("development", {}).get("episode_count"),
        "holdout_episodes": evidence.get("holdout", {}).get("episode_count"),
        "errors": evidence["errors"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if evidence["status"] == "QUALIFIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
