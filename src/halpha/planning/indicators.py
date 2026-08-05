"""NautilusTrader-native indicator boundary for the one-shot strategy."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from nautilus_trader.indicators import AverageTrueRange, DonchianChannel, MovingAverageType
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.objects import Price, Quantity

from halpha.domain_values import content_digest
from halpha.planning.strategies.one_shot import NativeIndicatorSnapshot


class IndicatorBar(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    open: str
    high: str
    low: str
    close: str
    volume: str
    ts_event_ns: int


def native_donchian_atr_snapshot(
    *,
    instrument_id: str,
    lookback: int,
    bars: tuple[IndicatorBar, ...],
) -> NativeIndicatorSnapshot:
    """Calculate the fixed indicators using only public Nautilus classes."""

    required_bar_count = max(lookback, 15)
    if len(bars) != required_bar_count:
        raise ValueError("INDICATOR_WINDOW_INCOMPLETE")
    timestamps = [bar.ts_event_ns for bar in bars]
    if timestamps != sorted(timestamps) or len(set(timestamps)) != len(timestamps):
        raise ValueError("INDICATOR_WINDOW_ORDER_INVALID")
    bar_type = BarType.from_str(f"{instrument_id}-15-MINUTE-LAST-EXTERNAL")
    donchian = DonchianChannel(lookback)
    atr = AverageTrueRange(
        period=14,
        ma_type=MovingAverageType.WILDER,
        use_previous=True,
        value_floor=0.0,
    )
    for item in bars:
        bar = Bar(
            bar_type=bar_type,
            open=Price.from_str(item.open),
            high=Price.from_str(item.high),
            low=Price.from_str(item.low),
            close=Price.from_str(item.close),
            volume=Quantity.from_str(item.volume),
            ts_event=item.ts_event_ns,
            ts_init=item.ts_event_ns,
        )
        donchian.handle_bar(bar)
        atr.handle_bar(bar)
    return NativeIndicatorSnapshot(
        upper=format(donchian.upper, ".12g"),
        lower=format(donchian.lower, ".12g"),
        atr=format(atr.value, ".12g"),
        initialized=bool(donchian.initialized and atr.initialized),
        source_digest=content_digest([bar.model_dump(mode="json") for bar in bars]),
        source_cutoff_ns=bars[-1].ts_event_ns,
    )
