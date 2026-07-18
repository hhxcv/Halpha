"""Nautilus bar-to-entry evaluation boundary shared by live and backtest paths."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime

from nautilus_trader.indicators import AverageTrueRange, DonchianChannel, MovingAverageType
from nautilus_trader.model.data import Bar, BarType
from pydantic import BaseModel, ConfigDict

from halpha.domain_values import content_digest
from halpha.planning.indicators import IndicatorBar
from halpha.planning.registry import OneShotParameters
from halpha.planning.strategies.one_shot import (
    EntryEvaluationInput,
    InstrumentQuantityRules,
    NativeIndicatorSnapshot,
)


class BarEvaluationError(RuntimeError):
    """Fail-closed error for conflicting or out-of-order strategy inputs."""


class EntrySizingSnapshot(BaseModel):
    """Environment-qualified facts needed by the shared pure sizing boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reference_price: str
    reference_source: str
    max_allowed_loss: str
    max_notional: str
    max_margin: str
    effective_leverage: str
    taker_fee_rate: str
    rules: InstrumentQuantityRules


EntrySizingProvider = Callable[[Bar], EntrySizingSnapshot | None]


def _datetime_from_ns(timestamp_ns: int) -> datetime:
    seconds, nanoseconds = divmod(timestamp_ns, 1_000_000_000)
    return datetime.fromtimestamp(seconds, tz=UTC).replace(
        microsecond=nanoseconds // 1_000,
    )


class NautilusBarEntryEvaluator:
    """Build normalized entry inputs from the one source/target bar topology.

    The evaluator owns no order, venue, plan, CAP or persistence capability. It
    only maps Nautilus bars and an explicitly supplied environment fact snapshot
    into the immutable input consumed by ``OneShotDonchianAtrLogic``.
    """

    def __init__(
        self,
        *,
        activation_id: str,
        instrument_ref: str,
        parameters: OneShotParameters,
        decision_not_before: datetime,
        valid_until: datetime,
        sizing_provider: EntrySizingProvider,
    ) -> None:
        if decision_not_before.tzinfo is None or valid_until.tzinfo is None:
            raise ValueError("BAR_EVALUATION_TIMEZONE_REQUIRED")
        if valid_until <= decision_not_before:
            raise ValueError("BAR_EVALUATION_WINDOW_INVALID")
        self.activation_id = activation_id
        self.instrument_ref = instrument_ref
        self.parameters = parameters
        self.decision_not_before = decision_not_before.astimezone(UTC)
        self.valid_until = valid_until.astimezone(UTC)
        self.sizing_provider = sizing_provider
        self.source_bar_type = BarType.from_str(
            f"{instrument_ref}.BINANCE-1-MINUTE-LAST-EXTERNAL"
        )
        self.target_bar_type = BarType.from_str(
            f"{instrument_ref}.BINANCE-15-MINUTE-LAST-INTERNAL@1-MINUTE-EXTERNAL"
        )
        self._delivered_target_bar_type = self.target_bar_type.standard()
        self._indicator_bars: deque[IndicatorBar] = deque(
            maxlen=parameters.channel_lookback_15m
        )
        self._confirmation_bars: deque[Bar] = deque(
            maxlen=parameters.confirmation_bars_1m
        )
        self._donchian = DonchianChannel(parameters.channel_lookback_15m)
        self._atr = AverageTrueRange(
            period=14,
            ma_type=MovingAverageType.WILDER,
            use_previous=True,
            value_floor=0.0,
        )
        self._last_target_ts: int | None = None
        self._last_target_digest: str | None = None
        self._last_source_ts: int | None = None
        self._last_source_digest: str | None = None

    @property
    def subscribed_bar_types(self) -> tuple[BarType, BarType]:
        return self.source_bar_type, self.target_bar_type

    def accept(self, bar: Bar) -> EntryEvaluationInput | None:
        bar_type = str(bar.bar_type)
        if bar_type == str(self._delivered_target_bar_type):
            self._accept_target(bar)
            return None
        if bar_type == str(self.source_bar_type):
            return self._accept_source(bar)
        return None

    def _accept_target(self, bar: Bar) -> None:
        item = IndicatorBar(
            open=str(bar.open),
            high=str(bar.high),
            low=str(bar.low),
            close=str(bar.close),
            volume=str(bar.volume),
            ts_event_ns=bar.ts_event,
        )
        digest = content_digest(item.model_dump(mode="json"))
        if self._last_target_ts is not None:
            if bar.ts_event < self._last_target_ts:
                raise BarEvaluationError("TARGET_BAR_OUT_OF_ORDER")
            if bar.ts_event == self._last_target_ts:
                if digest != self._last_target_digest:
                    raise BarEvaluationError("TARGET_BAR_IDENTITY_CONFLICT")
                return
        self._donchian.handle_bar(bar)
        self._atr.handle_bar(bar)
        self._indicator_bars.append(item)
        self._confirmation_bars.clear()
        self._last_target_ts = bar.ts_event
        self._last_target_digest = digest

    def _accept_source(self, bar: Bar) -> EntryEvaluationInput | None:
        digest = content_digest(
            {
                "bar_type": str(bar.bar_type),
                "open": str(bar.open),
                "high": str(bar.high),
                "low": str(bar.low),
                "close": str(bar.close),
                "volume": str(bar.volume),
                "ts_event_ns": bar.ts_event,
            }
        )
        if self._last_source_ts is not None:
            if bar.ts_event < self._last_source_ts:
                raise BarEvaluationError("SOURCE_BAR_OUT_OF_ORDER")
            if bar.ts_event == self._last_source_ts:
                if digest != self._last_source_digest:
                    raise BarEvaluationError("SOURCE_BAR_IDENTITY_CONFLICT")
                return None
        self._last_source_ts = bar.ts_event
        self._last_source_digest = digest
        if self._last_target_ts is None or bar.ts_event <= self._last_target_ts:
            return None
        decision_at = _datetime_from_ns(bar.ts_event)
        if decision_at < self.decision_not_before or decision_at >= self.valid_until:
            return None
        self._confirmation_bars.append(bar)
        if len(self._confirmation_bars) != self.parameters.confirmation_bars_1m:
            return None
        if len(self._indicator_bars) != self.parameters.channel_lookback_15m:
            return None
        if not self._donchian.initialized or not self._atr.initialized:
            return None
        sizing = self.sizing_provider(bar)
        if sizing is None:
            return None
        indicators = NativeIndicatorSnapshot(
            upper=format(self._donchian.upper, ".12g"),
            lower=format(self._donchian.lower, ".12g"),
            atr=format(self._atr.value, ".12g"),
            initialized=True,
            source_digest=content_digest(
                [item.model_dump(mode="json") for item in self._indicator_bars]
            ),
            source_cutoff_ns=self._last_target_ts,
        )
        confirmation_closes = tuple(str(item.close) for item in self._confirmation_bars)
        input_payload = {
            "activation_id": self.activation_id,
            "instrument_id": f"{self.instrument_ref}.BINANCE",
            "target_cutoff_ns": self._last_target_ts,
            "source_cutoff_ns": bar.ts_event,
            "confirmation_closes": confirmation_closes,
            "indicators": indicators.model_dump(mode="json"),
            "sizing": sizing.model_dump(mode="json"),
        }
        return EntryEvaluationInput(
            activation_id=self.activation_id,
            instrument_id=f"{self.instrument_ref}.BINANCE",
            source_identity=(
                f"{self.activation_id}:BAR:{self._last_target_ts}:{bar.ts_event}"
            ),
            source_cutoff=decision_at,
            input_digest=content_digest(input_payload),
            decision_at=decision_at,
            valid_until=self.valid_until,
            confirmation_closes=confirmation_closes,
            indicators=indicators,
            reference_price=sizing.reference_price,
            reference_source=sizing.reference_source,
            max_allowed_loss=sizing.max_allowed_loss,
            max_notional=sizing.max_notional,
            max_margin=sizing.max_margin,
            effective_leverage=sizing.effective_leverage,
            taker_fee_rate=sizing.taker_fee_rate,
            rules=sizing.rules,
        )
