"""Sequential, funding-aware daily Donchian ensemble study.

The script reads immutable public Binance archives from an explicit cache. It does
not import Halpha product code, use a product database, or call a trading endpoint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import vectorbt as vbt


PERIODS = {
    "development": ("2021-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
    "evaluation": ("2024-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
    "confirmation": ("2026-01-01T00:00:00Z", "2026-07-01T00:00:00Z"),
}
SCENARIOS = {
    "favorable": {"fee": 0.0004, "slippage": 0.0002},
    "base": {"fee": 0.0004, "slippage": 0.0010},
    "stress": {"fee": 0.0004, "slippage": 0.0015},
}
TARGET_VOL = 0.10
MAX_WEIGHT = 0.50
PAPER_TARGET_VOL = 0.25
PAPER_MAX_WEIGHT = 2.0
REBALANCE_THRESHOLD = 0.20
VOL_WINDOW = 90
CSV_COLUMNS = (
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trade_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "ignore",
)


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    direction: str
    lookbacks: tuple[int, ...]


CANDIDATES = (
    Candidate("LONG_FULL_9", "LONG_ONLY", (5, 10, 20, 30, 60, 90, 150, 250, 360)),
    Candidate("LONG_FAST_4", "LONG_ONLY", (5, 10, 20, 30)),
    Candidate("LONG_BALANCED_4", "LONG_ONLY", (20, 30, 60, 90)),
    Candidate("LONG_SLOW_5", "LONG_ONLY", (60, 90, 150, 250, 360)),
    Candidate(
        "LONG_SHORT_FULL_9", "LONG_SHORT", (5, 10, 20, 30, 60, 90, 150, 250, 360)
    ),
    Candidate("LONG_SHORT_BALANCED_4", "LONG_SHORT", (20, 30, 60, 90)),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _utc_ms(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def _finite(value: float) -> float | None:
    return float(value) if math.isfinite(float(value)) else None


@dataclass(frozen=True)
class MarketData:
    open_time: np.ndarray
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    funding_boundary_value: np.ndarray
    funding_intraday_value: np.ndarray
    manifest_identity: str
    quality: dict[str, Any]


def _load_market_data(cache_root: Path, manifest_path: Path) -> MarketData:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    frames: list[pd.DataFrame] = []
    verified: list[dict[str, Any]] = []
    for item in manifest["archives"]:
        archive = cache_root / item["cache_relative_path"]
        actual_sha = _sha256(archive)
        if actual_sha != item["sha256"]:
            raise ValueError(f"ARCHIVE_SHA256_MISMATCH:{archive.name}")
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            if len(names) != 1:
                raise ValueError(f"ARCHIVE_MEMBER_COUNT_INVALID:{archive.name}")
            with bundle.open(names[0]) as source:
                first_line = source.readline().strip().lower()
                source.seek(0)
                skiprows = 1 if first_line.startswith(b"open_time") else 0
                frame = pd.read_csv(
                    source,
                    header=None,
                    skiprows=skiprows,
                    names=CSV_COLUMNS,
                    usecols=range(12),
                )
        frames.append(frame)
        verified.append(
            {"month": item["month"], "sha256": actual_sha, "bytes": archive.stat().st_size}
        )

    bars = pd.concat(frames, ignore_index=True)
    for column in ("open_time", "open", "high", "low", "close"):
        bars[column] = pd.to_numeric(bars[column], errors="raise")
    bars = bars.sort_values("open_time", kind="stable")
    duplicate_count = int(bars.duplicated("open_time", keep=False).sum())
    if duplicate_count:
        raise ValueError("DUPLICATE_DAILY_BAR")
    bars = bars.reset_index(drop=True)
    open_time = bars["open_time"].to_numpy(dtype=np.int64)
    if len(open_time) < 2 or np.any(np.diff(open_time) != 86_400_000):
        raise ValueError("DAILY_TIMELINE_NOT_CONTINUOUS")
    open_price = bars["open"].to_numpy(dtype=np.float64)
    high = bars["high"].to_numpy(dtype=np.float64)
    low = bars["low"].to_numpy(dtype=np.float64)
    close = bars["close"].to_numpy(dtype=np.float64)
    if (
        np.any(~np.isfinite(open_price))
        or np.any(~np.isfinite(high))
        or np.any(~np.isfinite(low))
        or np.any(~np.isfinite(close))
        or np.any(open_price <= 0)
        or np.any(low <= 0)
        or np.any(high < np.maximum(open_price, close))
        or np.any(low > np.minimum(open_price, close))
    ):
        raise ValueError("DAILY_OHLC_INVALID")

    mark_frames: list[pd.DataFrame] = []
    mark_verified: list[dict[str, Any]] = []
    for item in manifest["mark_price_archives"]:
        archive = cache_root / item["cache_relative_path"]
        actual_sha = _sha256(archive)
        if actual_sha != item["sha256"]:
            raise ValueError(f"MARK_ARCHIVE_SHA256_MISMATCH:{archive.name}")
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            if len(names) != 1:
                raise ValueError(f"MARK_ARCHIVE_MEMBER_COUNT_INVALID:{archive.name}")
            with bundle.open(names[0]) as source:
                first_line = source.readline().strip().lower()
                source.seek(0)
                skiprows = 1 if first_line.startswith(b"open_time") else 0
                frame = pd.read_csv(
                    source,
                    header=None,
                    skiprows=skiprows,
                    names=CSV_COLUMNS,
                    usecols=range(12),
                )
        mark_frames.append(frame.loc[:, ["open_time", "close", "close_time"]])
        mark_verified.append(
            {"month": item["month"], "sha256": actual_sha, "bytes": archive.stat().st_size}
        )
    mark_bars = pd.concat(mark_frames, ignore_index=True)
    for column in ("open_time", "close", "close_time"):
        mark_bars[column] = pd.to_numeric(mark_bars[column], errors="raise")
    mark_bars = mark_bars.sort_values("open_time", kind="stable")
    if mark_bars.duplicated("open_time", keep=False).any():
        raise ValueError("DUPLICATE_MARK_PRICE_BAR")
    mark_open_time = mark_bars["open_time"].to_numpy(dtype=np.int64)
    if len(mark_open_time) < 2:
        raise ValueError("MARK_PRICE_HISTORY_EMPTY")
    mark_timeline_gap_count = int(np.count_nonzero(np.diff(mark_open_time) != 28_800_000))
    mark_settlement = mark_bars["close_time"].to_numpy(dtype=np.int64) + 1
    mark_close = mark_bars["close"].to_numpy(dtype=np.float64)
    mark_by_settlement = {
        int(timestamp): float(price) for timestamp, price in zip(mark_settlement, mark_close, strict=True)
    }

    funding_info = manifest["funding_snapshot"]
    funding_path = cache_root / funding_info["cache_relative_path"]
    funding_sha = _sha256(funding_path)
    if funding_sha != funding_info["sha256"]:
        raise ValueError("FUNDING_SHA256_MISMATCH")
    funding_records = json.loads(funding_path.read_text(encoding="utf-8"))
    boundary = np.zeros(len(bars), dtype=np.float64)
    intraday = np.zeros(len(bars), dtype=np.float64)
    used_events = 0
    source_empty_marks = 0
    backfilled_marks = 0
    daily_open_fallbacks = 0
    first_open = int(open_time[0])
    last_boundary = int(open_time[-1]) + 86_400_000
    for record in funding_records:
        event_ms = int(record["fundingTime"])
        if event_ms < first_open or event_ms >= last_boundary:
            continue
        index = int(np.searchsorted(open_time, event_ms, side="right") - 1)
        if index < 0 or index >= len(open_time):
            continue
        rate = float(record["fundingRate"])
        mark_text = str(record.get("markPrice", "")).strip()
        if mark_text:
            mark = float(mark_text)
        else:
            source_empty_marks += 1
            nearest_settlement = int(round(event_ms / 28_800_000) * 28_800_000)
            mark = mark_by_settlement.get(nearest_settlement, math.nan)
            if math.isfinite(mark):
                backfilled_marks += 1
            else:
                mark = float(open_price[index])
                daily_open_fallbacks += 1
        value = mark * rate
        if event_ms - int(open_time[index]) <= 60_000:
            boundary[index] += value
        else:
            intraday[index] += value
        used_events += 1

    quality = {
        "bars": int(len(bars)),
        "first_open_time": datetime.fromtimestamp(open_time[0] / 1000, tz=UTC).isoformat(),
        "last_open_time": datetime.fromtimestamp(open_time[-1] / 1000, tz=UTC).isoformat(),
        "continuous_daily": True,
        "valid_ohlc": True,
        "duplicate_bars": duplicate_count,
        "archives_verified": len(verified),
        "archive_bytes": int(sum(item["bytes"] for item in verified)),
        "mark_price_archives_verified": len(mark_verified),
        "mark_price_archive_bytes": int(sum(item["bytes"] for item in mark_verified)),
        "mark_price_timeline_gap_count": mark_timeline_gap_count,
        "funding_records_used": used_events,
        "funding_source_records_without_mark_price": source_empty_marks,
        "funding_marks_backfilled_from_official_8h_klines": backfilled_marks,
        "funding_marks_using_daily_open_fallback": daily_open_fallbacks,
    }
    identity = _json_digest(
        {
            "manifest_sha256": _sha256(manifest_path),
            "archives": verified,
            "mark_price_archives": mark_verified,
            "funding_sha256": funding_sha,
        }
    )
    return MarketData(
        open_time=open_time,
        open=open_price,
        high=high,
        low=low,
        close=close,
        funding_boundary_value=boundary,
        funding_intraday_value=intraday,
        manifest_identity=identity,
        quality=quality,
    )


def _component_state(close: np.ndarray, lookback: int, direction: str) -> np.ndarray:
    series = pd.Series(close)
    upper = series.rolling(lookback, min_periods=lookback).max().to_numpy(dtype=np.float64)
    lower = series.rolling(lookback, min_periods=lookback).min().to_numpy(dtype=np.float64)
    midpoint = (upper + lower) / 2.0
    state = np.zeros(len(close), dtype=np.float64)
    position = 0
    trailing = math.nan
    for index in range(len(close)):
        if not math.isfinite(upper[index]):
            continue
        price = float(close[index])
        if position > 0:
            trailing = max(trailing, float(midpoint[index]))
            if price <= trailing:
                position = 0
                trailing = math.nan
        elif position < 0:
            trailing = min(trailing, float(midpoint[index]))
            if price >= trailing:
                position = 0
                trailing = math.nan
        else:
            long_breakout = price >= float(upper[index])
            short_breakout = price <= float(lower[index])
            if long_breakout and not short_breakout:
                position = 1
                trailing = float(midpoint[index])
            elif direction == "LONG_SHORT" and short_breakout and not long_breakout:
                position = -1
                trailing = float(midpoint[index])
        state[index] = float(position)
    return state


def _volatility_scale(close: np.ndarray, target_vol: float, cap: float) -> np.ndarray:
    returns = pd.Series(close).pct_change()
    annualized = returns.rolling(VOL_WINDOW, min_periods=VOL_WINDOW).std(ddof=1) * math.sqrt(365.0)
    sigma = annualized.to_numpy(dtype=np.float64)
    scale = np.zeros(len(close), dtype=np.float64)
    valid = np.isfinite(sigma) & (sigma > 0)
    scale[valid] = np.minimum(target_vol / sigma[valid], cap)
    return scale


def _desired_weight(
    close: np.ndarray,
    candidate: Candidate,
    component_cache: dict[tuple[int, str], np.ndarray],
    *,
    target_vol: float,
    cap: float,
) -> tuple[np.ndarray, dict[int, np.ndarray]]:
    components: dict[int, np.ndarray] = {}
    for lookback in candidate.lookbacks:
        key = (lookback, candidate.direction)
        if key not in component_cache:
            component_cache[key] = _component_state(close, lookback, candidate.direction)
        components[lookback] = component_cache[key]
    combined = np.mean(np.column_stack(list(components.values())), axis=1)
    scale = _volatility_scale(close, target_vol, cap)
    return combined * scale, components


@dataclass(frozen=True)
class Simulation:
    dates: pd.DatetimeIndex
    returns: np.ndarray
    metrics: dict[str, Any]


def _should_trade(target: float, current: float) -> bool:
    if target == 0.0 and current == 0.0:
        return False
    if target == 0.0 or current == 0.0 or math.copysign(1.0, target) != math.copysign(1.0, current):
        return True
    denominator = max(abs(target), abs(current))
    return abs(target - current) > REBALANCE_THRESHOLD * denominator


def _target_after_cost(
    equity: float,
    current_notional: float,
    target_weight: float,
    cost_rate: float,
) -> tuple[float, float]:
    post_equity = equity
    desired_notional = target_weight * post_equity
    for _ in range(6):
        cost = abs(desired_notional - current_notional) * cost_rate
        post_equity = equity - cost
        desired_notional = target_weight * post_equity
    return desired_notional, equity - post_equity


def _statistics(
    dates: pd.DatetimeIndex,
    daily_returns: np.ndarray,
    *,
    turnover: float,
    trade_events: int,
    active_days: int,
    price_pnl: float,
    funding_pnl: float,
    fee_cost: float,
    slippage_cost: float,
    terminal_liquidation: bool,
) -> dict[str, Any]:
    if len(daily_returns) == 0 or np.any(~np.isfinite(daily_returns)):
        raise ValueError("INVALID_DAILY_RETURNS")
    equity = np.cumprod(1.0 + daily_returns)
    total_return = float(equity[-1] - 1.0)
    years = len(daily_returns) / 365.25
    cagr = (float(equity[-1]) ** (1.0 / years) - 1.0) if equity[-1] > 0 and years > 0 else math.nan
    volatility = float(np.std(daily_returns, ddof=1) * math.sqrt(365.0)) if len(daily_returns) > 1 else math.nan
    sharpe = (
        float(np.mean(daily_returns) / np.std(daily_returns, ddof=1) * math.sqrt(365.0))
        if len(daily_returns) > 1 and np.std(daily_returns, ddof=1) > 0
        else math.nan
    )
    peaks = np.maximum.accumulate(np.concatenate(([1.0], equity)))
    drawdowns = np.concatenate(([1.0], equity)) / peaks - 1.0
    max_drawdown = float(np.min(drawdowns))
    calmar = cagr / abs(max_drawdown) if max_drawdown < 0 and math.isfinite(cagr) else math.nan
    return_series = pd.Series(daily_returns, index=dates)
    annual = {
        str(int(year)): float((1.0 + values).prod() - 1.0)
        for year, values in return_series.groupby(return_series.index.year)
    }
    monthly = (1.0 + return_series).groupby(
        [return_series.index.year, return_series.index.month]
    ).prod() - 1.0
    return {
        "days": int(len(daily_returns)),
        "total_return": total_return,
        "cagr": _finite(cagr),
        "annualized_volatility": _finite(volatility),
        "sharpe": _finite(sharpe),
        "max_drawdown": max_drawdown,
        "calmar": _finite(calmar),
        "daily_skew": _finite(float(return_series.skew())),
        "daily_excess_kurtosis": _finite(float(return_series.kurt())),
        "positive_day_fraction": float((daily_returns > 0).mean()),
        "positive_month_fraction": float((monthly > 0).mean()) if len(monthly) else None,
        "annual_returns": annual,
        "turnover": float(turnover),
        "trade_events": int(trade_events),
        "active_days": int(active_days),
        "price_pnl_on_initial_equity": float(price_pnl),
        "funding_pnl_on_initial_equity": float(funding_pnl),
        "fee_cost_on_initial_equity": float(fee_cost),
        "slippage_cost_on_initial_equity": float(slippage_cost),
        "terminal_liquidation": terminal_liquidation,
    }


def _simulate(
    data: MarketData,
    desired_weight: np.ndarray,
    *,
    start_ms: int,
    end_ms: int,
    fee_rate: float,
    slippage_rate: float,
) -> Simulation:
    start_index = int(np.searchsorted(data.open_time, start_ms, side="left"))
    end_index = int(np.searchsorted(data.open_time, end_ms, side="left"))
    if start_index <= 0 or end_index <= start_index or end_index > len(data.open_time):
        raise ValueError("PERIOD_OUTSIDE_DATA")
    equity = 1.0
    quantity = 0.0
    prior_close = float(data.close[start_index - 1])
    daily_returns: list[float] = []
    dates: list[pd.Timestamp] = []
    turnover = 0.0
    trade_events = 0
    active_days = 0
    price_pnl_total = 0.0
    funding_pnl_total = 0.0
    fee_cost_total = 0.0
    slippage_cost_total = 0.0
    total_cost_rate = fee_rate + slippage_rate

    for index in range(start_index, end_index):
        day_start_equity = equity
        open_price = float(data.open[index])
        close_price = float(data.close[index])

        gap_pnl = quantity * (open_price - prior_close)
        boundary_funding = -quantity * float(data.funding_boundary_value[index])
        equity += gap_pnl + boundary_funding
        price_pnl_total += gap_pnl
        funding_pnl_total += boundary_funding
        if equity <= 0:
            raise ValueError("NON_POSITIVE_EQUITY_BEFORE_REBALANCE")

        current_notional = quantity * open_price
        current_weight = current_notional / equity
        target_weight = float(desired_weight[index - 1])
        if _should_trade(target_weight, current_weight):
            desired_notional, cost = _target_after_cost(
                equity, current_notional, target_weight, total_cost_rate
            )
            delta_notional = desired_notional - current_notional
            turnover += abs(delta_notional) / equity
            trade_events += 1
            if total_cost_rate > 0:
                fee_cost = cost * fee_rate / total_cost_rate
                slippage_cost = cost * slippage_rate / total_cost_rate
            else:
                fee_cost = 0.0
                slippage_cost = 0.0
            fee_cost_total += fee_cost
            slippage_cost_total += slippage_cost
            equity -= cost
            quantity = desired_notional / open_price

        intraday_price_pnl = quantity * (close_price - open_price)
        intraday_funding = -quantity * float(data.funding_intraday_value[index])
        equity += intraday_price_pnl + intraday_funding
        price_pnl_total += intraday_price_pnl
        funding_pnl_total += intraday_funding
        if quantity != 0.0:
            active_days += 1
        if equity <= 0:
            raise ValueError("NON_POSITIVE_EQUITY_AT_CLOSE")
        daily_returns.append(equity / day_start_equity - 1.0)
        dates.append(pd.Timestamp(int(data.open_time[index]), unit="ms", tz="UTC"))
        prior_close = close_price

    terminal_liquidation = quantity != 0.0
    if terminal_liquidation:
        terminal_notional = abs(quantity * prior_close)
        terminal_cost = terminal_notional * total_cost_rate
        if terminal_cost >= equity:
            raise ValueError("TERMINAL_COST_EXCEEDS_EQUITY")
        if total_cost_rate > 0:
            fee_cost_total += terminal_cost * fee_rate / total_cost_rate
            slippage_cost_total += terminal_cost * slippage_rate / total_cost_rate
        turnover += terminal_notional / equity
        trade_events += 1
        before = equity
        equity -= terminal_cost
        daily_returns[-1] = (1.0 + daily_returns[-1]) * (equity / before) - 1.0

    date_index = pd.DatetimeIndex(dates)
    returns_array = np.asarray(daily_returns, dtype=np.float64)
    metrics = _statistics(
        date_index,
        returns_array,
        turnover=turnover,
        trade_events=trade_events,
        active_days=active_days,
        price_pnl=price_pnl_total,
        funding_pnl=funding_pnl_total,
        fee_cost=fee_cost_total,
        slippage_cost=slippage_cost_total,
        terminal_liquidation=terminal_liquidation,
    )
    return Simulation(date_index, returns_array, metrics)


def _authorized_candidates(phase: str, authorization: str | None) -> tuple[Candidate, ...]:
    by_id = {candidate.candidate_id: candidate for candidate in CANDIDATES}
    if phase == "development":
        return CANDIDATES
    if not authorization:
        raise ValueError("AUTHORIZATION_REQUIRED")
    payload = json.loads(Path(authorization).read_text(encoding="utf-8"))
    if phase == "evaluation":
        if not payload.get("evaluation_authorized"):
            raise ValueError("EVALUATION_NOT_AUTHORIZED")
        ids = [item["candidate_id"] for item in payload["selected_candidates"]]
    else:
        if not payload.get("confirmation_authorized"):
            raise ValueError("CONFIRMATION_NOT_AUTHORIZED")
        item = payload.get("confirmation_candidate")
        ids = [item["candidate_id"]] if item else []
    if not ids or any(candidate_id not in by_id for candidate_id in ids):
        raise ValueError("AUTHORIZED_CANDIDATE_INVALID")
    return tuple(by_id[candidate_id] for candidate_id in ids)


def _continuous_long_weight(close: np.ndarray) -> np.ndarray:
    return _volatility_scale(close, TARGET_VOL, MAX_WEIGHT)


def analyze(args: argparse.Namespace) -> None:
    phase = args.phase
    candidates = _authorized_candidates(phase, args.authorization)
    start_ms, end_ms = map(_utc_ms, PERIODS[phase])
    cache_root = Path(args.cache_root).resolve()
    manifest_path = Path(args.manifest).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    data = _load_market_data(cache_root, manifest_path)
    component_cache: dict[tuple[int, str], np.ndarray] = {}

    benchmark_weight = _continuous_long_weight(data.close)
    benchmark: dict[str, Any] = {}
    for scenario, costs in SCENARIOS.items():
        benchmark[scenario] = _simulate(
            data,
            benchmark_weight,
            start_ms=start_ms,
            end_ms=end_ms,
            fee_rate=costs["fee"],
            slippage_rate=costs["slippage"],
        ).metrics

    result_candidates: list[dict[str, Any]] = []
    base_returns: dict[str, np.ndarray] = {}
    daily_index: pd.DatetimeIndex | None = None
    for candidate in candidates:
        desired, components = _desired_weight(
            data.close,
            candidate,
            component_cache,
            target_vol=TARGET_VOL,
            cap=MAX_WEIGHT,
        )
        scenarios: dict[str, Any] = {}
        for scenario, costs in SCENARIOS.items():
            simulation = _simulate(
                data,
                desired,
                start_ms=start_ms,
                end_ms=end_ms,
                fee_rate=costs["fee"],
                slippage_rate=costs["slippage"],
            )
            scenarios[scenario] = simulation.metrics
            if scenario == "base":
                base_returns[candidate.candidate_id] = simulation.returns
                daily_index = simulation.dates

        component_results: dict[str, Any] = {}
        positive_components = 0
        base_costs = SCENARIOS["base"]
        component_scale = _volatility_scale(data.close, TARGET_VOL, MAX_WEIGHT)
        for lookback, state in components.items():
            component_simulation = _simulate(
                data,
                state * component_scale,
                start_ms=start_ms,
                end_ms=end_ms,
                fee_rate=base_costs["fee"],
                slippage_rate=base_costs["slippage"],
            )
            component_results[str(lookback)] = component_simulation.metrics
            if component_simulation.metrics["total_return"] > 0:
                positive_components += 1
        result_candidates.append(
            {
                "candidate_id": candidate.candidate_id,
                "direction": candidate.direction,
                "lookbacks_days": list(candidate.lookbacks),
                "scenarios": scenarios,
                "component_diagnostics_base": component_results,
                "positive_component_count_base": positive_components,
            }
        )

    if daily_index is None:
        raise ValueError("NO_CANDIDATE_RETURNS")
    returns_frame = pd.DataFrame(base_returns, index=daily_index)
    dsr = returns_frame.vbt.returns.deflated_sharpe_ratio(nb_trials=len(CANDIDATES))
    for candidate in result_candidates:
        candidate["deflated_sharpe_probability"] = float(dsr[candidate["candidate_id"]])

    paper_diagnostic = None
    if any(candidate.candidate_id == "LONG_FULL_9" for candidate in candidates):
        paper_candidate = next(item for item in CANDIDATES if item.candidate_id == "LONG_FULL_9")
        paper_weight, _ = _desired_weight(
            data.close,
            paper_candidate,
            component_cache,
            target_vol=PAPER_TARGET_VOL,
            cap=PAPER_MAX_WEIGHT,
        )
        paper_diagnostic = _simulate(
            data,
            paper_weight,
            start_ms=start_ms,
            end_ms=end_ms,
            fee_rate=SCENARIOS["base"]["fee"],
            slippage_rate=SCENARIOS["base"]["slippage"],
        ).metrics

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "framework_versions": {
            "vectorbt": vbt.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
        "phase": phase,
        "period": list(PERIODS[phase]),
        "data_identity": data.manifest_identity,
        "data_quality": data.quality,
        "costs_per_unit_turnover": SCENARIOS,
        "candidate_scale": {"target_volatility": TARGET_VOL, "max_absolute_weight": MAX_WEIGHT},
        "rebalance_threshold": REBALANCE_THRESHOLD,
        "candidates": result_candidates,
        "benchmark_continuous_vol_target_long": benchmark,
        "paper_scale_full_9_base_diagnostic": paper_diagnostic,
        "candidate_distribution_digest": _json_digest(result_candidates),
    }
    json_path = output_dir / f"{phase}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    rows: list[dict[str, Any]] = []
    for candidate in result_candidates:
        for scenario, metrics in candidate["scenarios"].items():
            row = {
                "candidate_id": candidate["candidate_id"],
                "direction": candidate["direction"],
                "lookbacks_days": "/".join(map(str, candidate["lookbacks_days"])),
                "scenario": scenario,
                "deflated_sharpe_probability": candidate["deflated_sharpe_probability"],
                "positive_component_count_base": candidate["positive_component_count_base"],
            }
            for key, value in metrics.items():
                if key == "annual_returns":
                    for year, annual_return in value.items():
                        row[f"return_{year}"] = annual_return
                elif not isinstance(value, (dict, list)):
                    row[key] = value
            rows.append(row)
    pd.DataFrame(rows).to_csv(output_dir / f"{phase}.csv", index=False)
    returns_frame.to_csv(output_dir / f"{phase}_daily_returns.csv", index_label="date")
    print(
        json.dumps(
            {
                "phase": phase,
                "candidates": len(result_candidates),
                "output": str(json_path),
                "data_identity": data.manifest_identity,
            },
            ensure_ascii=False,
        )
    )


def _passes_development(candidate: dict[str, Any], benchmark: dict[str, Any]) -> tuple[bool, list[str]]:
    base = candidate["scenarios"]["base"]
    stress = candidate["scenarios"]["stress"]
    annual = base["annual_returns"]
    checks = {
        "base_total_positive": base["total_return"] > 0,
        "stress_total_positive": stress["total_return"] > 0,
        "base_sharpe_above_0p30": base["sharpe"] is not None and base["sharpe"] > 0.30,
        "base_drawdown_above_minus_20pct": base["max_drawdown"] > -0.20,
        "two_of_three_years_positive": sum(annual.get(year, -1.0) > 0 for year in ("2021", "2022", "2023")) >= 2,
        "sharpe_exceeds_benchmark": base["sharpe"] is not None and base["sharpe"] > benchmark["sharpe"],
        "calmar_exceeds_benchmark": base["calmar"] is not None and base["calmar"] > benchmark["calmar"],
        "two_positive_components": candidate["positive_component_count_base"] >= 2,
        "dsr_at_least_0p80": candidate["deflated_sharpe_probability"] >= 0.80,
    }
    return all(checks.values()), [name for name, passed in checks.items() if not passed]


def select_development(args: argparse.Namespace) -> None:
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if payload.get("phase") != "development":
        raise ValueError("NOT_DEVELOPMENT_RESULT")
    benchmark = payload["benchmark_continuous_vol_target_long"]["base"]
    assessed: list[dict[str, Any]] = []
    passers: list[dict[str, Any]] = []
    for candidate in payload["candidates"]:
        passed, failed = _passes_development(candidate, benchmark)
        record = {
            "candidate_id": candidate["candidate_id"],
            "passed": passed,
            "failed_checks": failed,
            "worst_annual_base_return": min(candidate["scenarios"]["base"]["annual_returns"].values()),
            "stress_sharpe": candidate["scenarios"]["stress"]["sharpe"],
            "base_sharpe": candidate["scenarios"]["base"]["sharpe"],
            "lookback_count": len(candidate["lookbacks_days"]),
        }
        assessed.append(record)
        if passed:
            passers.append(record)
    passers.sort(
        key=lambda item: (
            -item["worst_annual_base_return"],
            -item["stress_sharpe"],
            -item["base_sharpe"],
            item["lookback_count"],
            item["candidate_id"],
        )
    )
    selected = passers[:2]
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "phase": "development_selection",
        "source_sha256": _sha256(Path(args.input)),
        "assessed_candidates": assessed,
        "selected_candidates": selected,
        "evaluation_authorized": bool(selected),
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


def _passes_evaluation(candidate: dict[str, Any], benchmark: dict[str, Any]) -> tuple[bool, list[str]]:
    base = candidate["scenarios"]["base"]
    stress = candidate["scenarios"]["stress"]
    annual = base["annual_returns"]
    checks = {
        "base_total_positive": base["total_return"] > 0,
        "stress_total_positive": stress["total_return"] > 0,
        "base_drawdown_above_minus_18pct": base["max_drawdown"] > -0.18,
        "2024_not_below_minus_8pct": annual.get("2024", -1.0) >= -0.08,
        "2025_not_below_minus_8pct": annual.get("2025", -1.0) >= -0.08,
        "one_year_positive": max(annual.get("2024", -1.0), annual.get("2025", -1.0)) > 0,
        "sharpe_exceeds_benchmark": base["sharpe"] is not None and base["sharpe"] > benchmark["sharpe"],
        "calmar_exceeds_benchmark": base["calmar"] is not None and base["calmar"] > benchmark["calmar"],
    }
    return all(checks.values()), [name for name, passed in checks.items() if not passed]


def qualify_evaluation(args: argparse.Namespace) -> None:
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    selection = json.loads(Path(args.selection).read_text(encoding="utf-8"))
    if payload.get("phase") != "evaluation" or not selection.get("evaluation_authorized"):
        raise ValueError("EVALUATION_INPUT_INVALID")
    order = [item["candidate_id"] for item in selection["selected_candidates"]]
    by_id = {item["candidate_id"]: item for item in payload["candidates"]}
    benchmark = payload["benchmark_continuous_vol_target_long"]["base"]
    assessed: list[dict[str, Any]] = []
    confirmation_candidate: dict[str, Any] | None = None
    for candidate_id in order:
        candidate = by_id[candidate_id]
        passed, failed = _passes_evaluation(candidate, benchmark)
        record = {"candidate_id": candidate_id, "passed": passed, "failed_checks": failed}
        assessed.append(record)
        if passed and confirmation_candidate is None:
            confirmation_candidate = record
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "phase": "evaluation_gate",
        "source_sha256": _sha256(Path(args.input)),
        "selection_sha256": _sha256(Path(args.selection)),
        "assessed_candidates": assessed,
        "confirmation_candidate": confirmation_candidate,
        "confirmation_authorized": confirmation_candidate is not None,
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


def qualify_confirmation(args: argparse.Namespace) -> None:
    confirmation = json.loads(Path(args.input).read_text(encoding="utf-8"))
    evaluation = json.loads(Path(args.evaluation).read_text(encoding="utf-8"))
    authorization = json.loads(Path(args.authorization).read_text(encoding="utf-8"))
    if confirmation.get("phase") != "confirmation" or evaluation.get("phase") != "evaluation":
        raise ValueError("CONFIRMATION_INPUT_INVALID")
    candidate_id = authorization["confirmation_candidate"]["candidate_id"]
    confirmation_candidate = next(item for item in confirmation["candidates"] if item["candidate_id"] == candidate_id)
    evaluation_candidate = next(item for item in evaluation["candidates"] if item["candidate_id"] == candidate_id)
    base = confirmation_candidate["scenarios"]["base"]
    stress = confirmation_candidate["scenarios"]["stress"]
    combined = {}
    for scenario in ("base", "stress"):
        evaluation_return = evaluation_candidate["scenarios"][scenario]["total_return"]
        confirmation_return = confirmation_candidate["scenarios"][scenario]["total_return"]
        combined[scenario] = (1.0 + evaluation_return) * (1.0 + confirmation_return) - 1.0
    checks = {
        "base_non_negative": base["total_return"] >= 0,
        "stress_non_negative": stress["total_return"] >= 0,
        "base_drawdown_above_minus_12pct": base["max_drawdown"] > -0.12,
        "combined_evaluation_confirmation_base_positive": combined["base"] > 0,
        "combined_evaluation_confirmation_stress_positive": combined["stress"] > 0,
        "data_quality_pass": bool(confirmation["data_quality"]["continuous_daily"] and confirmation["data_quality"]["valid_ohlc"]),
    }
    passed = all(checks.values())
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "phase": "confirmation_gate",
        "candidate_id": candidate_id,
        "checks": checks,
        "combined_evaluation_confirmation_returns": combined,
        "passed": passed,
        "conclusion": "SUPPORTS_WITHIN_SCOPE" if passed else "DOES_NOT_SUPPORT",
        "source_sha256": _sha256(Path(args.input)),
    }
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_parser = subparsers.add_parser("analyze")
    analyze_parser.add_argument("--phase", choices=tuple(PERIODS), required=True)
    analyze_parser.add_argument("--cache-root", required=True)
    analyze_parser.add_argument("--manifest", required=True)
    analyze_parser.add_argument("--output-dir", required=True)
    analyze_parser.add_argument("--authorization")
    analyze_parser.set_defaults(func=analyze)

    select_parser = subparsers.add_parser("select-development")
    select_parser.add_argument("--input", required=True)
    select_parser.add_argument("--output", required=True)
    select_parser.set_defaults(func=select_development)

    evaluation_parser = subparsers.add_parser("qualify-evaluation")
    evaluation_parser.add_argument("--input", required=True)
    evaluation_parser.add_argument("--selection", required=True)
    evaluation_parser.add_argument("--output", required=True)
    evaluation_parser.set_defaults(func=qualify_evaluation)

    confirmation_parser = subparsers.add_parser("qualify-confirmation")
    confirmation_parser.add_argument("--input", required=True)
    confirmation_parser.add_argument("--evaluation", required=True)
    confirmation_parser.add_argument("--authorization", required=True)
    confirmation_parser.add_argument("--output", required=True)
    confirmation_parser.set_defaults(func=qualify_confirmation)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
