from __future__ import annotations

import json
from dataclasses import dataclass

from nautilus_trader.common.component import TestClock
from nautilus_trader.data.aggregation import TimeBarAggregator
from nautilus_trader.indicators import AverageTrueRange
from nautilus_trader.indicators import DonchianChannel
from nautilus_trader.indicators import MovingAverageType
from nautilus_trader.model.data import Bar
from nautilus_trader.model.data import BarType
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity
from nautilus_trader.test_kit.providers import TestInstrumentProvider


MINUTE_NS = 60_000_000_000
START_NS = 1_767_225_600_000_000_000  # 2026-01-01T00:00:00Z
LOOKBACKS = (20, 96)
ATR_PERIOD = 14


@dataclass(frozen=True)
class WindowResult:
    usable: bool
    reason: str
    identical_duplicates: int


def _bar_types(instrument_id: str) -> tuple[BarType, BarType]:
    source = BarType.from_str(f"{instrument_id}-1-MINUTE-LAST-EXTERNAL")
    target = BarType.from_str(
        f"{instrument_id}-15-MINUTE-LAST-INTERNAL@1-MINUTE-EXTERNAL",
    )
    return source, target


def _make_bar(bar_type: BarType, index: int, interval_minutes: int = 1) -> Bar:
    base = 100_000 + index
    timestamp = START_NS + (index + 1) * interval_minutes * MINUTE_NS
    return Bar(
        bar_type=bar_type,
        open=Price.from_str(f"{base:.2f}"),
        high=Price.from_str(f"{base + 5:.2f}"),
        low=Price.from_str(f"{base - 5:.2f}"),
        close=Price.from_str(f"{base + 2:.2f}"),
        volume=Quantity.from_str("1.0000"),
        ts_event=timestamp,
        ts_init=timestamp,
    )


def _fingerprint(bar: Bar) -> tuple[str, str, str, str, str]:
    return (
        str(bar.open),
        str(bar.high),
        str(bar.low),
        str(bar.close),
        str(bar.volume),
    )


def _classify_source_window(bars: list[Bar], target_close_ns: int) -> WindowResult:
    by_timestamp: dict[int, tuple[str, str, str, str, str]] = {}
    identical_duplicates = 0
    for bar in bars:
        fingerprint = _fingerprint(bar)
        previous = by_timestamp.get(bar.ts_event)
        if previous is None:
            by_timestamp[bar.ts_event] = fingerprint
        elif previous == fingerprint:
            identical_duplicates += 1
        else:
            return WindowResult(False, "CONFLICTING_DUPLICATE", identical_duplicates)

    expected = [target_close_ns - offset * MINUTE_NS for offset in range(14, -1, -1)]
    if sorted(by_timestamp) != expected:
        return WindowResult(False, "GAP_OR_OUT_OF_WINDOW", identical_duplicates)
    return WindowResult(True, "CONTINUOUS_COMPLETE", identical_duplicates)


def _aggregate_source_bars(
    source_bars: list[Bar],
    target: BarType,
) -> list[Bar]:
    instrument = TestInstrumentProvider.btcusdt_perp_binance()
    output: list[Bar] = []
    aggregator = TimeBarAggregator(
        instrument=instrument,
        bar_type=target,
        handler=output.append,
        clock=TestClock(),
        interval_type="left-open",
        timestamp_on_close=True,
        skip_first_non_full_bar=True,
        build_with_no_updates=False,
    )
    aggregator.set_historical_mode(True, output.append)
    for bar in source_bars:
        aggregator.handle_bar(bar)
    aggregator.stop_timer()
    return output


def _indicator_evidence(target: BarType, lookback: int) -> dict[str, object]:
    bars = [_make_bar(target, index, interval_minutes=15) for index in range(lookback)]
    donchian = DonchianChannel(lookback)
    atr = AverageTrueRange(
        period=ATR_PERIOD,
        ma_type=MovingAverageType.WILDER,
        use_previous=True,
        value_floor=0.0,
    )
    for bar in bars:
        donchian.handle_bar(bar)
        atr.handle_bar(bar)
    return {
        "input_bars": len(bars),
        "donchian": {
            "class": f"{type(donchian).__module__}.{type(donchian).__qualname__}",
            "initialized": donchian.initialized,
            "upper": format(donchian.upper, ".12g"),
            "middle": format(donchian.middle, ".12g"),
            "lower": format(donchian.lower, ".12g"),
        },
        "atr": {
            "class": f"{type(atr).__module__}.{type(atr).__qualname__}",
            "initialized": atr.initialized,
            "period": atr.period,
            "ma_type": "WILDER",
            "use_previous": True,
            "value": format(atr.value, ".12g"),
        },
    }


def main() -> int:
    errors: list[str] = []
    types: dict[str, dict[str, object]] = {}
    for instrument_id in ("BTCUSDT-PERP.BINANCE", "ETHUSDT-PERP.BINANCE"):
        source, target = _bar_types(instrument_id)
        types[instrument_id] = {
            "source_1m": str(source),
            "target_15m": str(target),
            "source_external": source.is_externally_aggregated(),
            "target_internal": target.is_internally_aggregated(),
            "target_composite": target.is_composite(),
            "target_composite_source": str(target.composite()),
        }
        if str(target.composite()) != str(source):
            errors.append(f"COMPOSITE_SOURCE_MISMATCH:{instrument_id}")

    source, target = _bar_types("BTCUSDT-PERP.BINANCE")
    full_bars = [_make_bar(source, index) for index in range(30)]
    target_close_ns = START_NS + 30 * MINUTE_NS
    second_window = full_bars[15:]
    full = _classify_source_window(second_window, target_close_ns)
    missing = _classify_source_window(
        [bar for index, bar in enumerate(second_window) if index != 7],
        target_close_ns,
    )
    identical = _classify_source_window(
        [*second_window, second_window[7]],
        target_close_ns,
    )
    conflicting_bar = Bar(
        bar_type=second_window[7].bar_type,
        open=second_window[7].open,
        high=second_window[7].high,
        low=second_window[7].low,
        close=second_window[7].open,
        volume=second_window[7].volume,
        ts_event=second_window[7].ts_event,
        ts_init=second_window[7].ts_init,
    )
    conflicting = _classify_source_window(
        [*second_window, conflicting_bar],
        target_close_ns,
    )
    aggregated = _aggregate_source_bars(full_bars, target)

    if not full.usable:
        errors.append("COMPLETE_WINDOW_REJECTED")
    if missing.usable:
        errors.append("GAPPED_WINDOW_ACCEPTED")
    if not identical.usable or identical.identical_duplicates != 1:
        errors.append("IDENTICAL_REPLAY_NOT_DEDUPLICATED")
    if conflicting.usable:
        errors.append("CONFLICTING_DUPLICATE_ACCEPTED")
    if len(aggregated) != 1 or aggregated[0].ts_event != target_close_ns:
        errors.append("NATIVE_15M_AGGREGATION_MISMATCH")

    indicators = {
        str(lookback): _indicator_evidence(target, lookback)
        for lookback in LOOKBACKS
    }
    for lookback, item in indicators.items():
        if not item["donchian"]["initialized"]:
            errors.append(f"DONCHIAN_NOT_INITIALIZED:{lookback}")
        if not item["atr"]["initialized"]:
            errors.append(f"ATR_NOT_INITIALIZED:{lookback}")

    evidence = {
        "status": "QUALIFIED" if not errors else "REJECTED",
        "errors": errors,
        "bar_types": types,
        "native_aggregation": {
            "source_bars": len(full_bars),
            "first_target_skipped_by_runtime_setting": True,
            "emitted_target_bars": len(aggregated),
            "emitted_target_close_ns": [bar.ts_event for bar in aggregated],
            "interval_type": "left-open",
            "timestamp_on_close": True,
            "skip_first_non_full_bar": True,
            "build_with_no_updates": False,
        },
        "continuity_gate_fixture": {
            "complete": full.__dict__,
            "missing_one": missing.__dict__,
            "identical_replay": identical.__dict__,
            "conflicting_duplicate": conflicting.__dict__,
            "note": "DIRECT qualification fixture only; not product runtime code",
        },
        "indicators": indicators,
    }
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
