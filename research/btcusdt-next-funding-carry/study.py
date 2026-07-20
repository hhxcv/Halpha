#!/usr/bin/env python3
"""Reproducible BTCUSDT next-settlement funding-carry study.

This script deliberately uses only Python's standard library and public Binance
market-data endpoints.  It does not import Halpha product code, configuration,
credentials, databases, or runtime components.
"""

from __future__ import annotations

import argparse
import calendar
import csv
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import hashlib
import io
import json
import math
from pathlib import Path
import random
import statistics
import time
from typing import Iterable, Iterator
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import zipfile


SYMBOL = "BTCUSDT"
VENUE = "BINANCE_USDM"
INTERVAL_MS = 60_000
BASE_URL = "https://data.binance.vision/data/futures/um/monthly/klines"
FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
USER_AGENT = "halpha-independent-research/1.0"

BASELINE_COMMIT = "de6b3052f28fe547730e89e58186d4ab397884b1"
BASELINE_STRATEGY_ID = "ONE_SHOT_DONCHIAN_ATR_BREAKOUT"
BASELINE_STRATEGY_VERSION = "1.0.0"

THRESHOLDS = (0.0, 0.0001, 0.0003, 0.0005)
SELECTABLE_THRESHOLDS = (0.0001, 0.0003, 0.0005)
COST_SCENARIOS = {
    "favorable_12bps_round_trip": {"fee_per_side": 0.0004, "slippage_per_side": 0.0002},
    "base_32bps_round_trip": {"fee_per_side": 0.0006, "slippage_per_side": 0.0010},
    "stress_52bps_round_trip": {"fee_per_side": 0.0006, "slippage_per_side": 0.0020},
}
BASE_COST_NAME = "base_32bps_round_trip"

PERIODS = {
    "development": ("2021-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
    "evaluation": ("2024-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
    "confirmation": ("2026-01-01T00:00:00Z", "2026-07-01T00:00:00Z"),
}


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def to_ms(value: datetime) -> int:
    return int(value.timestamp() * 1000)


def iso_from_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat().replace("+00:00", "Z")


def month_iter(start_month: str, end_month: str) -> Iterator[str]:
    year, month = (int(part) for part in start_month.split("-"))
    end_year, end_value = (int(part) for part in end_month.split("-"))
    while (year, month) <= (end_year, end_value):
        yield f"{year:04d}-{month:02d}"
        month += 1
        if month == 13:
            year += 1
            month = 1


def month_for_ms(value: int) -> str:
    item = datetime.fromtimestamp(value / 1000, tz=UTC)
    return f"{item.year:04d}-{item.month:02d}"


def month_bounds(month: str) -> tuple[int, int]:
    year, value = (int(part) for part in month.split("-"))
    start = datetime(year, value, 1, tzinfo=UTC)
    days = calendar.monthrange(year, value)[1]
    return to_ms(start), to_ms(start + timedelta(days=days))


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def request_bytes(url: str, *, attempts: int = 4) -> bytes:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=45) as response:
                return response.read()
        except (HTTPError, OSError) as error:
            last_error = error
            if attempt + 1 == attempts:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(str(last_error))


def archive_url(month: str) -> str:
    name = f"{SYMBOL}-1m-{month}.zip"
    return f"{BASE_URL}/{SYMBOL}/1m/{name}"


def fetch_archive(cache_dir: Path, month: str) -> dict[str, object]:
    url = archive_url(month)
    name = url.rsplit("/", 1)[-1]
    destination = cache_dir / "klines-1m" / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    checksum_text = request_bytes(url + ".CHECKSUM").decode("utf-8").strip()
    expected = checksum_text.split()[0].lower()
    if len(expected) != 64:
        raise ValueError(f"Invalid checksum for {url}: {checksum_text!r}")
    if not destination.exists() or sha256_path(destination) != expected:
        temporary = destination.with_suffix(".zip.part")
        temporary.write_bytes(request_bytes(url))
        actual = sha256_path(temporary)
        if actual != expected:
            temporary.unlink(missing_ok=True)
            raise ValueError(f"Checksum mismatch for {url}: {actual} != {expected}")
        temporary.replace(destination)
    actual = sha256_path(destination)
    return {
        "month": month,
        "url": url,
        "checksum_url": url + ".CHECKSUM",
        "sha256": actual,
        "bytes": destination.stat().st_size,
        "cache_relative_path": f"klines-1m/{name}",
    }


def fetch_funding(cache_dir: Path, start_ms: int, end_ms: int) -> dict[str, object]:
    destination = cache_dir / "funding-rate-history.json"
    existing: dict[int, dict[str, object]] = {}
    if destination.exists():
        for row in json.loads(destination.read_text(encoding="utf-8")):
            existing[int(row["fundingTime"])] = row

    cursor = start_ms
    pages = 0
    while cursor < end_ms:
        query = urlencode(
            {
                "symbol": SYMBOL,
                "startTime": cursor,
                "endTime": end_ms - 1,
                "limit": 1000,
            }
        )
        rows = json.loads(request_bytes(f"{FUNDING_URL}?{query}").decode("utf-8"))
        pages += 1
        if not rows:
            break
        for row in rows:
            if row.get("symbol") != SYMBOL:
                raise ValueError(f"Unexpected funding symbol: {row.get('symbol')}")
            timestamp = int(row["fundingTime"])
            normalized = {
                "symbol": SYMBOL,
                "fundingTime": timestamp,
                "fundingRate": str(row["fundingRate"]),
                "markPrice": str(row.get("markPrice", "")),
            }
            previous = existing.get(timestamp)
            if previous is not None and previous != normalized:
                raise ValueError(f"Conflicting funding record at {timestamp}")
            existing[timestamp] = normalized
        next_cursor = int(rows[-1]["fundingTime"]) + 1
        if next_cursor <= cursor:
            raise ValueError("Funding pagination did not advance")
        cursor = next_cursor
        if len(rows) < 1000:
            break
        time.sleep(0.15)

    ordered = [existing[key] for key in sorted(existing)]
    write_json(destination, ordered)
    return {
        "url": FUNDING_URL,
        "request_security": "NONE_PUBLIC_MARKET_DATA",
        "requested_start_ms": start_ms,
        "requested_end_exclusive_ms": end_ms,
        "pages_this_run": pages,
        "records_in_snapshot": len(ordered),
        "first_funding_time": ordered[0]["fundingTime"] if ordered else None,
        "last_funding_time": ordered[-1]["fundingTime"] if ordered else None,
        "sha256": sha256_path(destination),
        "bytes": destination.stat().st_size,
        "cache_relative_path": destination.name,
    }


def command_fetch(args: argparse.Namespace) -> None:
    cache_dir = Path(args.cache_dir).resolve()
    manifest_path = Path(args.manifest).resolve()
    previous: dict[str, object] = {}
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
    archive_map = {
        item["month"]: item
        for item in previous.get("archives", [])
        if isinstance(item, dict) and "month" in item
    }
    for month in month_iter(args.start_month, args.end_month):
        item = fetch_archive(cache_dir, month)
        archive_map[month] = item
        print(f"verified {month} {item['bytes']} bytes", flush=True)
    start_ms = month_bounds(args.start_month)[0]
    end_ms = month_bounds(args.end_month)[1]
    funding = fetch_funding(cache_dir, start_ms, end_ms)
    manifest = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "venue": VENUE,
        "instrument": "BTCUSDT-PERP",
        "exchange_symbol": SYMBOL,
        "contract": "USDⓈ-M linear perpetual settled in USDT",
        "timezone": "UTC",
        "bar_semantics": "Binance /fapi/v1/klines 1m OHLCV; open time is the stable bar identity",
        "cache_root": str(cache_dir),
        "archives": [archive_map[key] for key in sorted(archive_map)],
        "funding_snapshot": funding,
        "retrieval_rule": {
            "archive": f"{BASE_URL}/{SYMBOL}/1m/{SYMBOL}-1m-YYYY-MM.zip",
            "archive_integrity": "Verify the adjacent official .CHECKSUM SHA-256 before use",
            "funding": f"GET {FUNDING_URL} with symbol={SYMBOL}, inclusive startTime/endTime, limit=1000, ascending pagination",
        },
    }
    write_json(manifest_path, manifest)
    print(json.dumps({"manifest": str(manifest_path), "cache": str(cache_dir), "archives": len(archive_map)}))


@dataclass(frozen=True)
class Bar:
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


def archive_path(cache_dir: Path, month: str) -> Path:
    return cache_dir / "klines-1m" / f"{SYMBOL}-1m-{month}.zip"


def iter_archive_bars(path: Path) -> Iterator[Bar]:
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        if len(names) != 1:
            raise ValueError(f"Expected one CSV in {path}, found {names}")
        with archive.open(names[0]) as raw:
            with io.TextIOWrapper(raw, encoding="utf-8", newline="") as text:
                for row in csv.reader(text):
                    if not row or not row[0].lstrip("-").isdigit():
                        continue
                    timestamp = int(row[0])
                    if timestamp >= 100_000_000_000_000:
                        raise ValueError(f"Unexpected non-millisecond futures timestamp {timestamp}")
                    yield Bar(
                        open_time=timestamp,
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=float(row[5]),
                    )


def iter_bars(cache_dir: Path, start_ms: int, end_ms: int) -> Iterator[Bar]:
    start_month = month_for_ms(start_ms)
    end_month = month_for_ms(max(start_ms, end_ms - 1))
    for month in month_iter(start_month, end_month):
        path = archive_path(cache_dir, month)
        if not path.exists():
            raise FileNotFoundError(f"Missing archive {path}")
        for bar in iter_archive_bars(path):
            if start_ms <= bar.open_time < end_ms:
                yield bar


def load_funding(cache_dir: Path) -> list[dict[str, object]]:
    path = cache_dir / "funding-rate-history.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    return sorted(rows, key=lambda row: int(row["fundingTime"]))


def command_inspect(args: argparse.Namespace) -> None:
    cache_dir = Path(args.cache_dir).resolve()
    start_ms = to_ms(parse_time(args.start))
    end_ms = to_ms(parse_time(args.end))
    first = None
    last = None
    previous = None
    rows = 0
    gaps: list[dict[str, object]] = []
    duplicates = 0
    out_of_order = 0
    invalid_ohlc = 0
    non_positive = 0
    for bar in iter_bars(cache_dir, start_ms, end_ms):
        rows += 1
        first = bar.open_time if first is None else first
        last = bar.open_time
        if previous is not None:
            delta = bar.open_time - previous
            if delta == 0:
                duplicates += 1
            elif delta < 0:
                out_of_order += 1
            elif delta != INTERVAL_MS:
                gaps.append({"after": iso_from_ms(previous), "before": iso_from_ms(bar.open_time), "delta_ms": delta})
        if min(bar.open, bar.high, bar.low, bar.close) <= 0:
            non_positive += 1
        if bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close) or bar.high < bar.low:
            invalid_ohlc += 1
        previous = bar.open_time

    funding = [
        row
        for row in load_funding(cache_dir)
        if start_ms <= int(row["fundingTime"]) < end_ms
    ]
    funding_times = [int(row["fundingTime"]) for row in funding]
    funding_duplicates = len(funding_times) - len(set(funding_times))
    interval_hours: dict[str, int] = defaultdict(int)
    for left, right in zip(funding_times, funding_times[1:]):
        hours = round((right - left) / 3_600_000, 6)
        interval_hours[str(hours)] += 1
    result = {
        "generated_at": utc_now(),
        "requested_start": args.start,
        "requested_end_exclusive": args.end,
        "instrument": "BTCUSDT-PERP",
        "venue": VENUE,
        "timezone": "UTC",
        "klines": {
            "rows": rows,
            "first_open_time": iso_from_ms(first) if first is not None else None,
            "last_open_time": iso_from_ms(last) if last is not None else None,
            "expected_rows_if_continuous": (end_ms - start_ms) // INTERVAL_MS,
            "duplicates": duplicates,
            "out_of_order": out_of_order,
            "gap_count": len(gaps),
            "gaps": gaps,
            "invalid_ohlc": invalid_ohlc,
            "non_positive_prices": non_positive,
        },
        "funding": {
            "records": len(funding),
            "first_time": iso_from_ms(funding_times[0]) if funding_times else None,
            "last_time": iso_from_ms(funding_times[-1]) if funding_times else None,
            "duplicates": funding_duplicates,
            "observed_interval_hours": dict(sorted(interval_hours.items())),
            "empty_mark_price_records": sum(not str(row.get("markPrice", "")) for row in funding),
        },
    }
    write_json(Path(args.output).resolve(), result)
    print(json.dumps(result["klines"], sort_keys=True))


def collect_prices(cache_dir: Path, start_ms: int, end_ms: int, times: set[int]) -> dict[int, float]:
    result: dict[int, float] = {}
    for bar in iter_bars(cache_dir, start_ms, end_ms):
        if bar.open_time in times:
            result[bar.open_time] = bar.open
    return result


@dataclass(frozen=True)
class FundingTrade:
    signal_time: int
    exit_time: int
    direction: int
    current_funding: float
    next_funding: float
    entry_mid: float
    settlement_mid: float
    exit_mid: float
    holding_hours: float


def funding_trade_return(trade: FundingTrade, fee: float, slippage: float) -> dict[str, float]:
    entry_fill = trade.entry_mid * (1 + trade.direction * slippage)
    exit_fill = trade.exit_mid * (1 - trade.direction * slippage)
    gross_price = trade.direction * (trade.exit_mid / trade.entry_mid - 1)
    price_after_slippage = trade.direction * (exit_fill / entry_fill - 1)
    funding = -trade.direction * trade.next_funding * (trade.settlement_mid / entry_fill)
    fees = fee * (1 + exit_fill / entry_fill)
    return {
        "gross_price": gross_price,
        "slippage_effect": price_after_slippage - gross_price,
        "funding": funding,
        "fees": -fees,
        "net": price_after_slippage + funding - fees,
    }


def bootstrap_mean_interval(values: list[float], *, seed: int, reps: int = 2000, block: int = 8) -> list[float | None]:
    if len(values) < block * 2:
        return [None, None]
    rng = random.Random(seed)
    sample_means: list[float] = []
    length = len(values)
    for _ in range(reps):
        sample: list[float] = []
        while len(sample) < length:
            start = rng.randrange(length)
            sample.extend(values[(start + offset) % length] for offset in range(block))
        sample_means.append(statistics.fmean(sample[:length]))
    sample_means.sort()
    return [sample_means[int(0.025 * reps)], sample_means[int(0.975 * reps) - 1]]


def summarized_returns(rows: list[dict[str, float]], exit_times: list[int], holding_hours: list[float]) -> dict[str, object]:
    nets = [row["net"] for row in rows]
    if not nets:
        return {
            "trades": 0,
            "mean_net_return": None,
            "median_net_return": None,
            "compounded_net_return": None,
            "max_drawdown": None,
            "win_rate": None,
            "bootstrap_95pct_mean": [None, None],
            "yearly": {},
        }
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for value in nets:
        equity *= 1 + value
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity / peak - 1)
    yearly: dict[str, dict[str, object]] = {}
    grouped: dict[int, list[int]] = defaultdict(list)
    for index, timestamp in enumerate(exit_times):
        grouped[datetime.fromtimestamp(timestamp / 1000, tz=UTC).year].append(index)
    for year, indices in sorted(grouped.items()):
        values = [nets[index] for index in indices]
        year_equity = math.prod(1 + value for value in values)
        yearly[str(year)] = {
            "trades": len(values),
            "mean_net_return": statistics.fmean(values),
            "median_net_return": statistics.median(values),
            "compounded_net_return": year_equity - 1,
            "win_rate": sum(value > 0 for value in values) / len(values),
        }
    return {
        "trades": len(nets),
        "mean_net_return": statistics.fmean(nets),
        "median_net_return": statistics.median(nets),
        "standard_deviation": statistics.stdev(nets) if len(nets) > 1 else 0.0,
        "compounded_net_return": equity - 1,
        "max_drawdown": max_drawdown,
        "win_rate": sum(value > 0 for value in nets) / len(nets),
        "mean_holding_hours": statistics.fmean(holding_hours),
        "bootstrap_95pct_mean": bootstrap_mean_interval(nets, seed=20260720),
        "component_sums": {
            key: sum(row[key] for row in rows)
            for key in ("gross_price", "slippage_effect", "funding", "fees", "net")
        },
        "yearly": yearly,
    }


def build_funding_trades(cache_dir: Path, start_ms: int, end_ms: int) -> list[FundingTrade]:
    funding = [
        row
        for row in load_funding(cache_dir)
        if start_ms <= int(row["fundingTime"]) < end_ms
    ]
    pairs = []
    needed: set[int] = set()
    for current, following in zip(funding, funding[1:]):
        current_time = int(current["fundingTime"])
        next_time = int(following["fundingTime"])
        entry_time = (current_time // INTERVAL_MS) * INTERVAL_MS + INTERVAL_MS
        settlement_time = (next_time // INTERVAL_MS) * INTERVAL_MS
        exit_time = settlement_time + INTERVAL_MS
        if entry_time < start_ms or exit_time >= end_ms:
            continue
        pairs.append((current, following, entry_time, settlement_time, exit_time))
        needed.update((entry_time, settlement_time, exit_time))
    prices = collect_prices(cache_dir, start_ms, end_ms, needed)
    missing = sorted(needed - prices.keys())
    if missing:
        raise ValueError(f"Missing {len(missing)} candidate price bars, first={iso_from_ms(missing[0])}")
    result = []
    for current, following, entry_time, settlement_time, exit_time in pairs:
        rate = float(current["fundingRate"])
        if rate == 0:
            continue
        result.append(
            FundingTrade(
                signal_time=int(current["fundingTime"]),
                exit_time=exit_time,
                direction=-1 if rate > 0 else 1,
                current_funding=rate,
                next_funding=float(following["fundingRate"]),
                entry_mid=prices[entry_time],
                settlement_mid=prices[settlement_time],
                exit_mid=prices[exit_time],
                holding_hours=(exit_time - entry_time) / 3_600_000,
            )
        )
    return result


def funding_metrics(trades: list[FundingTrade], threshold: float) -> dict[str, object]:
    selected = [trade for trade in trades if abs(trade.current_funding) >= threshold]
    scenarios = {}
    for name, cost in COST_SCENARIOS.items():
        rows = [
            funding_trade_return(trade, cost["fee_per_side"], cost["slippage_per_side"])
            for trade in selected
        ]
        scenarios[name] = summarized_returns(
            rows,
            [trade.exit_time for trade in selected],
            [trade.holding_hours for trade in selected],
        )
    same_sign = sum(
        (trade.current_funding > 0) == (trade.next_funding > 0)
        for trade in selected
    )
    return {
        "threshold_absolute_funding_rate": threshold,
        "signal_rule": "At observed settlement choose SHORT if current funding > 0, LONG if current funding < 0",
        "entry_rule": "Enter at the open of the one-minute bar beginning one full minute after fundingTime",
        "exit_rule": "Exit at the open of the one-minute bar beginning one full minute after the next observed settlement",
        "eligible_trades": len(selected),
        "long_trades": sum(trade.direction == 1 for trade in selected),
        "short_trades": sum(trade.direction == -1 for trade in selected),
        "next_funding_same_sign_rate": same_sign / len(selected) if selected else None,
        "cost_scenarios": scenarios,
    }


@dataclass
class TargetBar:
    bucket: int
    open: float
    high: float
    low: float
    close: float


@dataclass
class BaselinePosition:
    direction: int
    entry_time: int
    entry_mid: float
    entry_fill: float
    quantity: float
    stop: float
    tp1: float
    tp2: float
    time_exit: int
    remaining: float = 1.0
    tp1_done: bool = False
    pnl: float = 0.0
    funding: float = 0.0
    fees: float = 0.0


@dataclass
class BaselineState:
    direction: int
    confirmations: deque[float] = field(default_factory=lambda: deque(maxlen=2))
    scheduled: tuple[int, float] | None = None
    position: BaselinePosition | None = None
    trades: list[dict[str, object]] = field(default_factory=list)


def exit_piece(position: BaselinePosition, fraction: float, mid: float, fee: float, slippage: float) -> None:
    exit_fill = mid * (1 - position.direction * slippage)
    quantity = position.quantity * fraction
    position.pnl += position.direction * quantity * (exit_fill - position.entry_fill)
    position.fees += fee * exit_fill * quantity
    position.remaining -= fraction


def close_baseline(state: BaselineState, timestamp: int, reason: str) -> None:
    position = state.position
    if position is None or position.remaining > 1e-9:
        return
    state.trades.append(
        {
            "entry_time": position.entry_time,
            "exit_time": timestamp,
            "direction": position.direction,
            "net": position.pnl + position.funding - position.fees,
            "gross_price": position.pnl,
            "funding": position.funding,
            "fees": -position.fees,
            "slippage_effect": 0.0,
            "holding_hours": (timestamp - position.entry_time) / 3_600_000,
            "exit_reason": reason,
        }
    )
    state.position = None


def simulate_formal_baseline_proxy(cache_dir: Path, start_ms: int, end_ms: int) -> dict[str, object]:
    fee = COST_SCENARIOS[BASE_COST_NAME]["fee_per_side"]
    slippage = COST_SCENARIOS[BASE_COST_NAME]["slippage_per_side"]
    warmup_start = max(to_ms(parse_time("2021-01-01T00:00:00Z")), start_ms - 7 * 86_400_000)
    funding_map = {
        (int(row["fundingTime"]) // INTERVAL_MS) * INTERVAL_MS: float(row["fundingRate"])
        for row in load_funding(cache_dir)
        if warmup_start <= int(row["fundingTime"]) < end_ms
    }
    states = {direction: BaselineState(direction=direction) for direction in (1, -1)}
    targets: deque[TargetBar] = deque(maxlen=20)
    current_target: TargetBar | None = None
    previous_target_close: float | None = None
    atr_value: float | None = None
    atr_count = 0
    alpha = 2.0 / 15.0
    channel: tuple[float, float] | None = None
    last_bar: Bar | None = None

    def finalize_target(target: TargetBar) -> None:
        nonlocal previous_target_close, atr_value, atr_count, channel
        true_range = target.high - target.low
        if previous_target_close is not None:
            true_range = max(
                true_range,
                abs(target.high - previous_target_close),
                abs(target.low - previous_target_close),
            )
        atr_value = true_range if atr_value is None else alpha * true_range + (1 - alpha) * atr_value
        atr_count += 1
        previous_target_close = target.close
        targets.append(target)
        channel = (max(item.high for item in targets), min(item.low for item in targets)) if len(targets) == 20 else None
        for state in states.values():
            state.confirmations.clear()

    for bar in iter_bars(cache_dir, warmup_start, end_ms):
        last_bar = bar
        bucket = bar.open_time // 900_000
        if current_target is None:
            current_target = TargetBar(bucket, bar.open, bar.high, bar.low, bar.close)
        elif current_target.bucket != bucket:
            finalize_target(current_target)
            current_target = TargetBar(bucket, bar.open, bar.high, bar.low, bar.close)
        else:
            current_target.high = max(current_target.high, bar.high)
            current_target.low = min(current_target.low, bar.low)
            current_target.close = bar.close

        if bar.open_time < start_ms:
            continue

        rate = funding_map.get(bar.open_time)
        if rate is not None:
            for state in states.values():
                position = state.position
                if position is not None:
                    position.funding += -position.direction * rate * bar.open * position.quantity * position.remaining

        for state in states.values():
            position = state.position
            if position is not None and bar.open_time >= position.time_exit:
                exit_piece(position, position.remaining, bar.open, fee, slippage)
                close_baseline(state, bar.open_time, "TIME_EXIT")

            if state.scheduled is not None and state.scheduled[0] == bar.open_time and state.position is None:
                _, atr = state.scheduled
                entry_fill = bar.open * (1 + state.direction * slippage)
                quantity = 1.0 / bar.open
                risk_distance = 1.5 * atr
                position = BaselinePosition(
                    direction=state.direction,
                    entry_time=bar.open_time,
                    entry_mid=bar.open,
                    entry_fill=entry_fill,
                    quantity=quantity,
                    stop=entry_fill - state.direction * risk_distance,
                    tp1=entry_fill + state.direction * risk_distance * 1.5,
                    tp2=entry_fill + state.direction * risk_distance * 3.0,
                    time_exit=bar.open_time + 96 * 900_000,
                    fees=fee * entry_fill * quantity,
                )
                state.position = position
                state.scheduled = None

            position = state.position
            if position is not None:
                stop_hit = bar.low <= position.stop if position.direction == 1 else bar.high >= position.stop
                tp1_hit = bar.high >= position.tp1 if position.direction == 1 else bar.low <= position.tp1
                tp2_hit = bar.high >= position.tp2 if position.direction == 1 else bar.low <= position.tp2
                if stop_hit:
                    exit_piece(position, position.remaining, position.stop, fee, slippage)
                    close_baseline(state, bar.open_time + INTERVAL_MS, "STOP_CONSERVATIVE_INTRABAR")
                else:
                    if not position.tp1_done and tp1_hit:
                        exit_piece(position, min(0.5, position.remaining), position.tp1, fee, slippage)
                        position.tp1_done = True
                    if tp2_hit and position.remaining > 1e-9:
                        exit_piece(position, position.remaining, position.tp2, fee, slippage)
                        close_baseline(state, bar.open_time + INTERVAL_MS, "TAKE_PROFIT_2")

        if channel is not None and atr_value is not None and atr_count >= 14:
            upper, lower = channel
            for state in states.values():
                if state.position is not None or state.scheduled is not None:
                    continue
                state.confirmations.append(bar.close)
                if len(state.confirmations) != 2:
                    continue
                extension = 0.5 * atr_value
                if state.direction == 1:
                    triggered = all(value > upper for value in state.confirmations) and state.confirmations[-1] <= upper + extension
                else:
                    triggered = all(value < lower for value in state.confirmations) and state.confirmations[-1] >= lower - extension
                entry_time = bar.open_time + INTERVAL_MS
                if triggered and entry_time < end_ms:
                    state.scheduled = (entry_time, atr_value)

    if last_bar is not None:
        for state in states.values():
            if state.position is not None:
                exit_piece(state.position, state.position.remaining, last_bar.close, fee, slippage)
                # Keep a boundary-forced exit inside the evaluated half-open
                # period so calendar attribution does not leak into the next
                # year merely because ``end_ms`` is exactly midnight.
                close_baseline(state, end_ms - 1, "PERIOD_END")

    result: dict[str, object] = {}
    for direction, state in states.items():
        rows = [
            {
                key: float(trade[key])
                for key in ("net", "gross_price", "funding", "fees", "slippage_effect")
            }
            for trade in state.trades
        ]
        result["LONG" if direction == 1 else "SHORT"] = summarized_returns(
            rows,
            [int(trade["exit_time"]) for trade in state.trades],
            [float(trade["holding_hours"]) for trade in state.trades],
        ) | {
            "exit_reason_counts": dict(
                sorted(
                    {
                        reason: sum(trade["exit_reason"] == reason for trade in state.trades)
                        for reason in {str(trade["exit_reason"]) for trade in state.trades}
                    }.items()
                )
            )
        }
    return {
        "identity": {
            "baseline_commit": BASELINE_COMMIT,
            "strategy_id": BASELINE_STRATEGY_ID,
            "strategy_version": BASELINE_STRATEGY_VERSION,
        },
        "proxy_limits": [
            "Repeated independent activations are simulated because L4 does not define a historical activation schedule.",
            "LONG and SHORT are replayed separately; no product plan chooses direction dynamically.",
            "ATR uses a documented EMA proxy (alpha=2/(14+1)); NautilusTrader 1.230.0 is not imported into the independent study.",
            "Entry occurs at the next 1m open after two closes confirm the 20x15m channel; same-minute stop/TP ambiguity is resolved stop-first.",
            "Order-book spread, queueing, partial fills, liquidation, margin and latency beyond the 10 bps slippage proxy are unmodeled.",
        ],
        "parameters": {
            "channel_lookback_15m": 20,
            "confirmation_bars_1m": 2,
            "initial_stop_atr_multiple": 1.5,
            "max_entry_extension_atr": 0.5,
            "take_profit_1_r": 1.5,
            "take_profit_1_fraction": 0.5,
            "take_profit_2_r": 3.0,
            "max_hold_bars_15m": 96,
            "cost_scenario": BASE_COST_NAME,
        },
        "directions": result,
    }


def command_analyze(args: argparse.Namespace) -> None:
    if args.phase not in PERIODS:
        raise ValueError(f"Unknown phase {args.phase}")
    start_text, end_text = PERIODS[args.phase]
    start_ms, end_ms = to_ms(parse_time(start_text)), to_ms(parse_time(end_text))
    cache_dir = Path(args.cache_dir).resolve()
    manifest_path = Path(args.manifest).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_trades = build_funding_trades(cache_dir, start_ms, end_ms)
    if args.phase == "development":
        thresholds = THRESHOLDS
    else:
        if not args.selection:
            raise ValueError("--selection is required outside development")
        selection = json.loads(Path(args.selection).read_text(encoding="utf-8"))
        thresholds = (float(selection["selected_threshold"]),)
    candidate = {format(value, ".8f"): funding_metrics(raw_trades, value) for value in thresholds}
    result = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "phase": args.phase,
        "period_start": start_text,
        "period_end_exclusive": end_text,
        "known_exposure": "All metrics in this phase become viewed evidence when this file is generated.",
        "question": "Does one-leg next-settlement funding carry on BTCUSDT-PERP survive observable timing and realistic costs?",
        "data_identity": {
            "source_manifest": str(manifest_path),
            "source_manifest_sha256": sha256_path(manifest_path),
            "funding_snapshot_sha256": manifest["funding_snapshot"]["sha256"],
            "venue": VENUE,
            "instrument": "BTCUSDT-PERP",
            "timezone": "UTC",
        },
        "candidate_family": candidate,
        "comparison_baselines": {
            "NO_TRADE": {"net_return": 0.0},
            "CURRENT_FORMAL_STRATEGY_REPLAY_PROXY": simulate_formal_baseline_proxy(cache_dir, start_ms, end_ms),
        },
    }
    write_json(Path(args.output).resolve(), result)
    print(json.dumps({"phase": args.phase, "thresholds": list(thresholds), "output": str(Path(args.output).resolve())}))


def command_select(args: argparse.Namespace) -> None:
    development = json.loads(Path(args.development).read_text(encoding="utf-8"))
    candidates = []
    for threshold in SELECTABLE_THRESHOLDS:
        key = format(threshold, ".8f")
        metrics = development["candidate_family"][key]["cost_scenarios"][BASE_COST_NAME]
        positive_years = sum(
            float(year["mean_net_return"]) > 0
            for year in metrics["yearly"].values()
        )
        ci_low = metrics["bootstrap_95pct_mean"][0]
        eligible = metrics["trades"] >= 60 and positive_years >= 2
        candidates.append(
            {
                "threshold": threshold,
                "trades": metrics["trades"],
                "mean_net_return": metrics["mean_net_return"],
                "bootstrap_95pct_mean_low": ci_low,
                "positive_calendar_years": positive_years,
                "passed_development_gate": eligible,
            }
        )
    passed = [item for item in candidates if item["passed_development_gate"]]
    pool = passed if passed else candidates
    selected = max(
        pool,
        key=lambda item: (
            item["bootstrap_95pct_mean_low"] if item["bootstrap_95pct_mean_low"] is not None else -math.inf,
            item["mean_net_return"],
        ),
    )
    result = {
        "generated_at": utc_now(),
        "development_file": str(Path(args.development).resolve()),
        "development_sha256": sha256_path(Path(args.development).resolve()),
        "selection_rule_predeclared_in_study_py": True,
        "gate": "At least 60 trades and positive base-cost mean in at least two development calendar years; rank passers by 8-trade circular-block bootstrap lower bound then mean.",
        "selection_status": "PASSED_DEVELOPMENT_GATE" if passed else "NO_VARIANT_PASSED_DEVELOPMENT_GATE_BEST_RETAINED_ONLY_FOR_FALSIFICATION",
        "selected_threshold": selected["threshold"],
        "candidate_rows": candidates,
    }
    write_json(Path(args.output).resolve(), result)
    print(json.dumps(result, sort_keys=True))


def command_combine(args: argparse.Namespace) -> None:
    development_path = Path(args.development).resolve()
    evaluation_path = Path(args.evaluation).resolve()
    confirmation_path = Path(args.confirmation).resolve()
    selection_path = Path(args.selection).resolve()
    development = json.loads(development_path.read_text(encoding="utf-8"))
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    confirmation = json.loads(confirmation_path.read_text(encoding="utf-8"))
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    threshold = float(selection["selected_threshold"])
    key = format(threshold, ".8f")

    def base(result: dict[str, object]) -> dict[str, object]:
        return result["candidate_family"][key]["cost_scenarios"][BASE_COST_NAME]

    dev, eva, conf = base(development), base(evaluation), base(confirmation)
    enough = int(eva["trades"]) >= 30 and int(conf["trades"]) >= 15
    evaluation_positive = float(eva["mean_net_return"]) > 0
    confirmation_positive = float(conf["mean_net_return"]) > 0
    ci_low = eva["bootstrap_95pct_mean"][0]
    all_eval_years_positive = all(float(row["mean_net_return"]) > 0 for row in eva["yearly"].values())
    supports = bool(
        enough
        and selection["selection_status"] == "PASSED_DEVELOPMENT_GATE"
        and evaluation_positive
        and confirmation_positive
        and ci_low is not None
        and float(ci_low) > 0
        and all_eval_years_positive
    )
    contradicted = bool(enough and (not evaluation_positive or not confirmation_positive))
    if supports:
        conclusion = "SUPPORTS_WITHIN_SCOPE"
    elif contradicted:
        conclusion = "DOES_NOT_SUPPORT"
    else:
        conclusion = "INSUFFICIENT_EVIDENCE"
    result = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "question": development["question"],
        "selected_threshold": threshold,
        "selection_status": selection["selection_status"],
        "conclusion": conclusion,
        "predeclared_decision_rule": {
            "support": "Development gate passes; evaluation has >=30 and confirmation >=15 trades; base-cost mean is positive in evaluation, every evaluation calendar year and confirmation; evaluation 8-trade block-bootstrap lower bound is >0.",
            "does_not_support": "With minimum sample counts, base-cost mean is non-positive in evaluation or confirmation.",
            "otherwise": "INSUFFICIENT_EVIDENCE",
        },
        "phase_metrics_base_cost": {
            "development": dev,
            "evaluation": eva,
            "confirmation": conf,
        },
        "artifact_hashes": {
            "development": sha256_path(development_path),
            "selection": sha256_path(selection_path),
            "evaluation": sha256_path(evaluation_path),
            "confirmation": sha256_path(confirmation_path),
        },
        "strongest_support": "Funding sign persistence and the most favorable-cost scenario are retained in phase files even if they do not rescue the base-cost result.",
        "strongest_counterevidence": "Base-cost out-of-sample and 2026H1 means, year splits, component sums and confidence intervals determine whether price risk and execution costs dominate funding receipts.",
        "cannot_infer": [
            "Future alpha or live profitability",
            "Spot-perpetual delta-neutral funding arbitrage performance",
            "Capacity, liquidation safety, order-book fills or account-specific fee rates",
            "Authorization to add a product strategy or change L4, capital or real-account state",
        ],
    }
    write_json(Path(args.output).resolve(), result)
    print(json.dumps({"conclusion": conclusion, "selected_threshold": threshold, "output": str(Path(args.output).resolve())}))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch = subparsers.add_parser("fetch")
    fetch.add_argument("--cache-dir", required=True)
    fetch.add_argument("--start-month", required=True)
    fetch.add_argument("--end-month", required=True)
    fetch.add_argument("--manifest", required=True)
    fetch.set_defaults(func=command_fetch)

    inspect = subparsers.add_parser("inspect")
    inspect.add_argument("--cache-dir", required=True)
    inspect.add_argument("--start", required=True)
    inspect.add_argument("--end", required=True)
    inspect.add_argument("--output", required=True)
    inspect.set_defaults(func=command_inspect)

    analyze = subparsers.add_parser("analyze")
    analyze.add_argument("--cache-dir", required=True)
    analyze.add_argument("--manifest", required=True)
    analyze.add_argument("--phase", choices=tuple(PERIODS), required=True)
    analyze.add_argument("--selection")
    analyze.add_argument("--output", required=True)
    analyze.set_defaults(func=command_analyze)

    select = subparsers.add_parser("select")
    select.add_argument("--development", required=True)
    select.add_argument("--output", required=True)
    select.set_defaults(func=command_select)

    combine = subparsers.add_parser("combine")
    combine.add_argument("--development", required=True)
    combine.add_argument("--selection", required=True)
    combine.add_argument("--evaluation", required=True)
    combine.add_argument("--confirmation", required=True)
    combine.add_argument("--output", required=True)
    combine.set_defaults(func=command_combine)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
