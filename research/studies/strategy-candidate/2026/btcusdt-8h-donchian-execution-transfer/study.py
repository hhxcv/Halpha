"""Sequential BTCUSDT 8h execution-frequency transfer of a fixed Donchian rule."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pandas as pd
import vectorbt as vbt


STUDY_DIR = Path(__file__).resolve().parent
BASE_PATH = STUDY_DIR.parent / "btcusdt-daily-donchian-ensemble" / "study.py"
DONCHIAN_RETURNS = STUDY_DIR.parent / "btcusdt-daily-donchian-ensemble" / "development_daily_returns.csv"
CARRY_RETURNS = STUDY_DIR.parent / "btcusdt-daily-donchian-carry-conditioned" / "development_daily_returns.csv"
SPOT_RETURNS = STUDY_DIR.parent / "btcusdt-spot-daily-donchian" / "development_daily_returns.csv"
ETH_RETURNS = STUDY_DIR.parent / "ethusdt-daily-donchian-short-carry-transfer" / "development_daily_returns.csv"
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
BAR_MS = 8 * 60 * 60 * 1000
BARS_PER_DAY = 3
BARS_PER_YEAR = 365.0 * BARS_PER_DAY
LOOKBACK_DAYS = (20, 30, 60, 90)
LOOKBACK_BARS = tuple(value * BARS_PER_DAY for value in LOOKBACK_DAYS)
VOL_WINDOW_BARS = 90 * BARS_PER_DAY
TARGET_VOL = 0.10
MAX_WEIGHT = 0.50
REBALANCE_THRESHOLD = 0.20
RELATED_TRIAL_COUNT = 12


def _load_base() -> ModuleType:
    spec = importlib.util.spec_from_file_location("halpha_btc_8h_study_base", BASE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("BASE_STUDY_IMPORT_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BASE = _load_base()


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


def _normalize_timestamp(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="raise").astype("int64")
    return numeric.where(numeric < 100_000_000_000_000, numeric // 1000)


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


def _archive_frame(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as bundle:
        names = bundle.namelist()
        if len(names) != 1:
            raise ValueError(f"ARCHIVE_MEMBER_COUNT_INVALID:{path.name}")
        with bundle.open(names[0]) as source:
            first = source.readline().strip().lower()
            source.seek(0)
            return pd.read_csv(
                source,
                header=None,
                skiprows=1 if first.startswith(b"open_time") else 0,
                names=BASE.CSV_COLUMNS,
                usecols=range(12),
            )


def _load_market_data(cache_root: Path, manifest_path: Path) -> MarketData:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("interval") != "8h":
        raise ValueError("MANIFEST_INTERVAL_NOT_8H")
    frames: list[pd.DataFrame] = []
    verified: list[dict[str, Any]] = []
    for item in manifest["archives"]:
        archive = cache_root / item["cache_relative_path"]
        actual = _sha256(archive)
        if actual != item["sha256"]:
            raise ValueError(f"ARCHIVE_SHA256_MISMATCH:{archive.name}")
        frames.append(_archive_frame(archive))
        verified.append(
            {"month": item["month"], "sha256": actual, "bytes": archive.stat().st_size}
        )
    bars = pd.concat(frames, ignore_index=True)
    bars["open_time"] = _normalize_timestamp(bars["open_time"])
    for column in ("open", "high", "low", "close"):
        bars[column] = pd.to_numeric(bars[column], errors="raise")
    bars = bars.sort_values("open_time", kind="stable").reset_index(drop=True)
    duplicate_count = int(bars.duplicated("open_time", keep=False).sum())
    if duplicate_count:
        raise ValueError("DUPLICATE_8H_BAR")
    open_time = bars["open_time"].to_numpy(dtype=np.int64)
    if len(open_time) < 2 or np.any(np.diff(open_time) != BAR_MS):
        raise ValueError("TIMELINE_NOT_CONTINUOUS_8H")
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
        raise ValueError("OHLC_INVALID_8H")

    mark_frames: list[pd.DataFrame] = []
    mark_verified: list[dict[str, Any]] = []
    for item in manifest["mark_price_archives"]:
        archive = cache_root / item["cache_relative_path"]
        actual = _sha256(archive)
        if actual != item["sha256"]:
            raise ValueError(f"MARK_ARCHIVE_SHA256_MISMATCH:{archive.name}")
        mark_frames.append(_archive_frame(archive).loc[:, ["open_time", "close_time", "close"]])
        mark_verified.append(
            {"month": item["month"], "sha256": actual, "bytes": archive.stat().st_size}
        )
    mark_bars = pd.concat(mark_frames, ignore_index=True)
    mark_bars["open_time"] = _normalize_timestamp(mark_bars["open_time"])
    mark_bars["close_time"] = _normalize_timestamp(mark_bars["close_time"])
    mark_bars["close"] = pd.to_numeric(mark_bars["close"], errors="raise")
    mark_bars = mark_bars.sort_values("open_time", kind="stable").reset_index(drop=True)
    if mark_bars.duplicated("open_time", keep=False).any():
        raise ValueError("DUPLICATE_MARK_BAR")
    mark_open = mark_bars["open_time"].to_numpy(dtype=np.int64)
    gap_count = int(np.count_nonzero(np.diff(mark_open) != BAR_MS))
    mark_by_settlement = {
        int(timestamp) + 1: float(price)
        for timestamp, price in zip(
            mark_bars["close_time"].to_numpy(dtype=np.int64),
            mark_bars["close"].to_numpy(dtype=np.float64),
            strict=True,
        )
    }

    funding_info = manifest["funding_snapshot"]
    funding_path = cache_root / funding_info["cache_relative_path"]
    funding_sha = _sha256(funding_path)
    if funding_sha != funding_info["sha256"]:
        raise ValueError("FUNDING_SHA256_MISMATCH")
    funding_records = json.loads(funding_path.read_text(encoding="utf-8"))
    boundary = np.zeros(len(bars), dtype=np.float64)
    intraday = np.zeros(len(bars), dtype=np.float64)
    used = source_empty = backfilled = fallback = 0
    first_open = int(open_time[0])
    end_boundary = int(open_time[-1]) + BAR_MS
    for record in funding_records:
        event_ms = int(record["fundingTime"])
        if not first_open <= event_ms < end_boundary:
            continue
        index = int(np.searchsorted(open_time, event_ms, side="right") - 1)
        rate = float(record["fundingRate"])
        mark_text = str(record.get("markPrice", "")).strip()
        if mark_text:
            mark = float(mark_text)
        else:
            source_empty += 1
            settlement = int(round(event_ms / BAR_MS) * BAR_MS)
            mark = mark_by_settlement.get(settlement, math.nan)
            if math.isfinite(mark):
                backfilled += 1
            else:
                mark = float(open_price[index])
                fallback += 1
        value = mark * rate
        if event_ms - int(open_time[index]) <= 60_000:
            boundary[index] += value
        else:
            intraday[index] += value
        used += 1
    quality = {
        "bars": int(len(bars)),
        "first_open_time": datetime.fromtimestamp(open_time[0] / 1000, tz=UTC).isoformat(),
        "last_open_time": datetime.fromtimestamp(open_time[-1] / 1000, tz=UTC).isoformat(),
        "continuous_8h": True,
        "valid_ohlc": True,
        "duplicate_bars": duplicate_count,
        "archives_verified": len(verified),
        "archive_bytes": int(sum(item["bytes"] for item in verified)),
        "mark_price_archives_verified": len(mark_verified),
        "mark_price_archive_bytes": int(sum(item["bytes"] for item in mark_verified)),
        "mark_price_timeline_gap_count": gap_count,
        "funding_records_used": used,
        "funding_source_records_without_mark_price": source_empty,
        "funding_marks_backfilled_from_official_8h_klines": backfilled,
        "funding_marks_using_bar_open_fallback": fallback,
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
        open_time, open_price, high, low, close, boundary, intraday, identity, quality
    )


def _to_daily(data: MarketData) -> MarketData:
    frame = pd.DataFrame(
        {
            "open_time": data.open_time,
            "open": data.open,
            "high": data.high,
            "low": data.low,
            "close": data.close,
            "boundary": data.funding_boundary_value,
            "intraday": data.funding_intraday_value,
        }
    )
    frame["date"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True).dt.normalize()
    rows: list[dict[str, float | int]] = []
    for _, group in frame.groupby("date", sort=True):
        if len(group) != BARS_PER_DAY:
            raise ValueError("INCOMPLETE_UTC_DAY")
        rows.append(
            {
                "open_time": int(group.iloc[0]["open_time"]),
                "open": float(group.iloc[0]["open"]),
                "high": float(group["high"].max()),
                "low": float(group["low"].min()),
                "close": float(group.iloc[-1]["close"]),
                "boundary": float(group.iloc[0]["boundary"]),
                "intraday": float(group.iloc[0]["intraday"] + group.iloc[1:][["boundary", "intraday"]].to_numpy().sum()),
            }
        )
    daily = pd.DataFrame(rows)
    return MarketData(
        daily["open_time"].to_numpy(dtype=np.int64),
        daily["open"].to_numpy(dtype=np.float64),
        daily["high"].to_numpy(dtype=np.float64),
        daily["low"].to_numpy(dtype=np.float64),
        daily["close"].to_numpy(dtype=np.float64),
        daily["boundary"].to_numpy(dtype=np.float64),
        daily["intraday"].to_numpy(dtype=np.float64),
        data.manifest_identity,
        {**data.quality, "derived_daily_bars": int(len(daily))},
    )


def _volatility_scale(
    close: np.ndarray, *, window: int, periods_per_year: float
) -> np.ndarray:
    returns = pd.Series(close).pct_change()
    sigma = (
        returns.rolling(window, min_periods=window).std(ddof=1)
        * math.sqrt(periods_per_year)
    ).to_numpy(dtype=np.float64)
    scale = np.zeros(len(close), dtype=np.float64)
    valid = np.isfinite(sigma) & (sigma > 0)
    scale[valid] = np.minimum(TARGET_VOL / sigma[valid], MAX_WEIGHT)
    return scale


def _trend_weight(
    close: np.ndarray, *, lookbacks: tuple[int, ...], window: int, periods_per_year: float
) -> np.ndarray:
    components = [BASE._component_state(close, value, "LONG_ONLY") for value in lookbacks]
    signal = np.mean(np.column_stack(components), axis=1)
    return signal * _volatility_scale(
        close, window=window, periods_per_year=periods_per_year
    )


def _should_trade(target: float, current: float) -> bool:
    if target == 0.0 and current == 0.0:
        return False
    if target == 0.0 or current == 0.0:
        return True
    denominator = max(abs(target), abs(current))
    return abs(target - current) > REBALANCE_THRESHOLD * denominator


def _target_after_cost(
    equity: float, current_notional: float, target_weight: float, cost_rate: float
) -> tuple[float, float]:
    post_equity = equity
    desired = target_weight * post_equity
    for _ in range(6):
        cost = abs(desired - current_notional) * cost_rate
        post_equity = equity - cost
        desired = target_weight * post_equity
    return desired, equity - post_equity


def _statistics(
    dates: pd.DatetimeIndex,
    interval_returns: np.ndarray,
    *,
    turnover: float,
    trade_events: int,
    active_intervals: int,
    active_days: int,
    price_pnl: float,
    funding_pnl: float,
    fee_cost: float,
    slippage_cost: float,
    terminal_liquidation: bool,
) -> tuple[dict[str, Any], pd.Series]:
    series = pd.Series(interval_returns, index=dates)
    daily = (1.0 + series).groupby(series.index.normalize()).prod() - 1.0
    equity = (1.0 + daily).cumprod()
    total = float(equity.iloc[-1] - 1.0)
    years = len(daily) / 365.25
    cagr = float(equity.iloc[-1] ** (1.0 / years) - 1.0)
    volatility = float(daily.std(ddof=1) * math.sqrt(365.0))
    sharpe = float(daily.mean() / daily.std(ddof=1) * math.sqrt(365.0))
    path = np.concatenate(([1.0], equity.to_numpy(dtype=np.float64)))
    drawdown = path / np.maximum.accumulate(path) - 1.0
    max_drawdown = float(drawdown.min())
    annual = {
        str(int(year)): float((1.0 + values).prod() - 1.0)
        for year, values in daily.groupby(daily.index.year)
    }
    monthly = (1.0 + daily).groupby([daily.index.year, daily.index.month]).prod() - 1.0
    metrics = {
        "days": int(len(daily)),
        "total_return": total,
        "cagr": cagr,
        "annualized_volatility": volatility,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "calmar": cagr / abs(max_drawdown) if max_drawdown < 0 else None,
        "daily_skew": float(daily.skew()),
        "daily_excess_kurtosis": float(daily.kurt()),
        "positive_day_fraction": float((daily > 0).mean()),
        "positive_month_fraction": float((monthly > 0).mean()),
        "annual_returns": annual,
        "turnover": float(turnover),
        "trade_events": int(trade_events),
        "active_intervals": int(active_intervals),
        "active_days": int(active_days),
        "price_pnl_on_initial_equity": float(price_pnl),
        "funding_pnl_on_initial_equity": float(funding_pnl),
        "fee_cost_on_initial_equity": float(fee_cost),
        "slippage_cost_on_initial_equity": float(slippage_cost),
        "terminal_liquidation": terminal_liquidation,
    }
    return metrics, daily


def _simulate(
    data: MarketData,
    desired_weight: np.ndarray,
    *,
    start_ms: int,
    end_ms: int,
    fee_rate: float,
    slippage_rate: float,
) -> tuple[dict[str, Any], pd.Series]:
    start = int(np.searchsorted(data.open_time, start_ms, side="left"))
    end = int(np.searchsorted(data.open_time, end_ms, side="left"))
    if start <= 0 or end <= start:
        raise ValueError("PERIOD_OUTSIDE_DATA")
    equity = 1.0
    quantity = 0.0
    prior_close = float(data.close[start - 1])
    returns: list[float] = []
    dates: list[pd.Timestamp] = []
    turnover = trade_events = active_intervals = 0
    active_dates: set[str] = set()
    price_pnl = funding_pnl = fee_cost = slippage_cost = 0.0
    total_cost = fee_rate + slippage_rate
    for index in range(start, end):
        initial = equity
        open_price = float(data.open[index])
        close_price = float(data.close[index])
        gap = quantity * (open_price - prior_close)
        boundary = -quantity * float(data.funding_boundary_value[index])
        equity += gap + boundary
        price_pnl += gap
        funding_pnl += boundary
        current_notional = quantity * open_price
        current_weight = current_notional / equity
        target = float(desired_weight[index - 1])
        if _should_trade(target, current_weight):
            desired, cost = _target_after_cost(equity, current_notional, target, total_cost)
            turnover += abs(desired - current_notional) / equity
            trade_events += 1
            if total_cost > 0:
                fee_cost += cost * fee_rate / total_cost
                slippage_cost += cost * slippage_rate / total_cost
            equity -= cost
            quantity = desired / open_price
        intraday_price = quantity * (close_price - open_price)
        intraday_funding = -quantity * float(data.funding_intraday_value[index])
        equity += intraday_price + intraday_funding
        price_pnl += intraday_price
        funding_pnl += intraday_funding
        if equity <= 0:
            raise ValueError("NON_POSITIVE_EQUITY")
        timestamp = pd.Timestamp(int(data.open_time[index]), unit="ms", tz="UTC")
        if quantity != 0:
            active_intervals += 1
            active_dates.add(timestamp.strftime("%Y-%m-%d"))
        returns.append(equity / initial - 1.0)
        dates.append(timestamp)
        prior_close = close_price
    terminal = quantity != 0.0
    if terminal:
        terminal_notional = abs(quantity * prior_close)
        cost = terminal_notional * total_cost
        before = equity
        equity -= cost
        if total_cost > 0:
            fee_cost += cost * fee_rate / total_cost
            slippage_cost += cost * slippage_rate / total_cost
        turnover += terminal_notional / before
        trade_events += 1
        returns[-1] = (1.0 + returns[-1]) * (equity / before) - 1.0
    return _statistics(
        pd.DatetimeIndex(dates),
        np.asarray(returns, dtype=np.float64),
        turnover=turnover,
        trade_events=trade_events,
        active_intervals=active_intervals,
        active_days=len(active_dates),
        price_pnl=price_pnl,
        funding_pnl=funding_pnl,
        fee_cost=fee_cost,
        slippage_cost=slippage_cost,
        terminal_liquidation=terminal,
    )


def _authorization(phase: str, path: str | None) -> None:
    if phase == "development":
        return
    if path is None:
        raise ValueError("AUTHORIZATION_REQUIRED")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    key = "evaluation_authorized" if phase == "evaluation" else "confirmation_authorized"
    if not payload.get(key):
        raise ValueError(f"{phase.upper()}_NOT_AUTHORIZED")


def _development_dsr(daily: pd.Series) -> tuple[float, dict[str, str]]:
    paths = [DONCHIAN_RETURNS, CARRY_RETURNS, SPOT_RETURNS, ETH_RETURNS]
    frames = [pd.read_csv(path, index_col="date", parse_dates=True) for path in paths]
    frames.append(pd.DataFrame({"BTC_8H_LONG_BALANCED_4": daily}))
    matrix = pd.concat(frames, axis=1, join="inner")
    if len(matrix) != len(daily) or matrix.shape[1] != RELATED_TRIAL_COUNT:
        raise ValueError(f"RELATED_TRIAL_MATRIX_INVALID:{matrix.shape}")
    dsr = matrix.vbt.returns.deflated_sharpe_ratio(nb_trials=RELATED_TRIAL_COUNT)
    return float(dsr["BTC_8H_LONG_BALANCED_4"]), {
        path.name + "@" + path.parent.name: _sha256(path) for path in paths
    }


def analyze(args: argparse.Namespace) -> None:
    _authorization(args.phase, args.authorization)
    start_ms, end_ms = map(_utc_ms, PERIODS[args.phase])
    data = _load_market_data(Path(args.cache_root).resolve(), Path(args.manifest).resolve())
    daily_data = _to_daily(data)
    candidate_weight = _trend_weight(
        data.close,
        lookbacks=LOOKBACK_BARS,
        window=VOL_WINDOW_BARS,
        periods_per_year=BARS_PER_YEAR,
    )
    daily_weight = _trend_weight(
        daily_data.close,
        lookbacks=LOOKBACK_DAYS,
        window=90,
        periods_per_year=365.0,
    )
    continuous_weight = _volatility_scale(
        data.close, window=VOL_WINDOW_BARS, periods_per_year=BARS_PER_YEAR
    )
    candidate: dict[str, Any] = {}
    daily_returns: pd.Series | None = None
    benchmarks: dict[str, dict[str, Any]] = {
        "daily_execution_same_rule": {},
        "continuous_8h_vol_target_long": {},
    }
    for scenario, costs in SCENARIOS.items():
        metrics, returns = _simulate(
            data,
            candidate_weight,
            start_ms=start_ms,
            end_ms=end_ms,
            fee_rate=costs["fee"],
            slippage_rate=costs["slippage"],
        )
        candidate[scenario] = metrics
        if scenario == "base":
            daily_returns = returns
        daily_metrics, _ = _simulate(
            daily_data,
            daily_weight,
            start_ms=start_ms,
            end_ms=end_ms,
            fee_rate=costs["fee"],
            slippage_rate=costs["slippage"],
        )
        continuous_metrics, _ = _simulate(
            data,
            continuous_weight,
            start_ms=start_ms,
            end_ms=end_ms,
            fee_rate=costs["fee"],
            slippage_rate=costs["slippage"],
        )
        benchmarks["daily_execution_same_rule"][scenario] = daily_metrics
        benchmarks["continuous_8h_vol_target_long"][scenario] = continuous_metrics
    if daily_returns is None:
        raise AssertionError("BASE_RETURNS_MISSING")
    dsr = trial_inputs = None
    if args.phase == "development":
        dsr, trial_inputs = _development_dsr(daily_returns)
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "phase": args.phase,
        "period": list(PERIODS[args.phase]),
        "framework_versions": {
            "vectorbt": vbt.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
        "method_identity": {
            "study_sha256": _sha256(Path(__file__).resolve()),
            "base_study_sha256": _sha256(BASE_PATH),
            "data_identity": data.manifest_identity,
            "related_trial_inputs": trial_inputs,
        },
        "data_quality": data.quality,
        "rules": {
            "instrument": "BTCUSDT USD-M perpetual",
            "interval": "8h",
            "lookback_days": list(LOOKBACK_DAYS),
            "lookback_bars": list(LOOKBACK_BARS),
            "direction": "LONG_ONLY",
            "target_volatility": TARGET_VOL,
            "maximum_absolute_weight": MAX_WEIGHT,
            "volatility_window_bars": VOL_WINDOW_BARS,
            "rebalance_threshold": REBALANCE_THRESHOLD,
            "action_time": "next 8h bar open",
        },
        "costs_per_unit_turnover": SCENARIOS,
        "candidate": {
            "candidate_id": "BTC_8H_LONG_BALANCED_4",
            "scenarios": candidate,
            "deflated_sharpe_probability": dsr,
            "related_trial_count": RELATED_TRIAL_COUNT,
        },
        "benchmarks": benchmarks,
        "product_effects": "NONE",
    }
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / f"{args.phase}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    rows: list[dict[str, Any]] = []
    for scenario, metrics in candidate.items():
        row: dict[str, Any] = {
            "candidate_id": "BTC_8H_LONG_BALANCED_4",
            "scenario": scenario,
            "deflated_sharpe_probability": dsr,
        }
        for key, value in metrics.items():
            if key == "annual_returns":
                for year, annual_return in value.items():
                    row[f"return_{year}"] = annual_return
            elif not isinstance(value, (dict, list)):
                row[key] = value
        rows.append(row)
    pd.DataFrame(rows).to_csv(output / f"{args.phase}.csv", index=False)
    daily_returns.rename("BTC_8H_LONG_BALANCED_4").to_csv(
        output / f"{args.phase}_daily_returns.csv", index_label="date"
    )
    print(json.dumps({"phase": args.phase, "candidate": "BTC_8H_LONG_BALANCED_4"}))


def select_development(args: argparse.Namespace) -> None:
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    candidate = payload["candidate"]
    base = candidate["scenarios"]["base"]
    stress = candidate["scenarios"]["stress"]
    benchmark = payload["benchmarks"]["daily_execution_same_rule"]["base"]
    annual = base["annual_returns"]
    checks = {
        "base_total_positive": base["total_return"] > 0,
        "stress_total_positive": stress["total_return"] > 0,
        "stress_cagr_above_4pct": stress["cagr"] > 0.04,
        "base_sharpe_at_least_0p75": base["sharpe"] >= 0.75,
        "twelve_trial_dsr_at_least_0p80": candidate["deflated_sharpe_probability"] >= 0.80,
        "drawdown_above_minus_12pct": base["max_drawdown"] > -0.12,
        "two_of_three_years_positive": sum(annual[str(year)] > 0 for year in (2021, 2022, 2023)) >= 2,
        "worst_year_at_least_minus_3pct": min(annual[str(year)] for year in (2021, 2022, 2023)) >= -0.03,
        "active_days_at_least_365": base["active_days"] >= 365,
        "turnover_at_most_50": base["turnover"] <= 50,
        "sharpe_exceeds_daily_execution": base["sharpe"] > benchmark["sharpe"],
        "calmar_exceeds_daily_execution": base["calmar"] > benchmark["calmar"],
    }
    failed = [name for name, passed in checks.items() if not passed]
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "phase": "development_selection",
        "source_sha256": _sha256(Path(args.input)),
        "candidate_id": candidate["candidate_id"],
        "checks": checks,
        "failed_checks": failed,
        "evaluation_authorized": not failed,
    }
    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))


def qualify_evaluation(args: argparse.Namespace) -> None:
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    candidate = payload["candidate"]["scenarios"]
    base, stress = candidate["base"], candidate["stress"]
    benchmark = payload["benchmarks"]["daily_execution_same_rule"]["base"]
    annual = base["annual_returns"]
    checks = {
        "base_total_positive": base["total_return"] > 0,
        "stress_total_positive": stress["total_return"] > 0,
        "stress_cagr_above_4pct": stress["cagr"] > 0.04,
        "both_years_positive": annual["2024"] > 0 and annual["2025"] > 0,
        "base_sharpe_at_least_0p75": base["sharpe"] >= 0.75,
        "drawdown_above_minus_12pct": base["max_drawdown"] > -0.12,
        "active_days_at_least_240": base["active_days"] >= 240,
        "turnover_at_most_40": base["turnover"] <= 40,
        "sharpe_exceeds_daily_execution": base["sharpe"] > benchmark["sharpe"],
        "calmar_exceeds_daily_execution": base["calmar"] > benchmark["calmar"],
    }
    failed = [name for name, passed in checks.items() if not passed]
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "phase": "evaluation_gate",
        "source_sha256": _sha256(Path(args.input)),
        "checks": checks,
        "failed_checks": failed,
        "confirmation_authorized": not failed,
    }
    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))


def qualify_confirmation(args: argparse.Namespace) -> None:
    confirmation = json.loads(Path(args.confirmation).read_text(encoding="utf-8"))
    evaluation = json.loads(Path(args.evaluation).read_text(encoding="utf-8"))
    current = confirmation["candidate"]["scenarios"]
    previous = evaluation["candidate"]["scenarios"]
    combined: dict[str, float] = {}
    for scenario in ("base", "stress"):
        total = (1.0 + previous[scenario]["total_return"]) * (1.0 + current[scenario]["total_return"])
        days = previous[scenario]["days"] + current[scenario]["days"]
        combined[scenario] = total ** (365.25 / days) - 1.0
    base, stress = current["base"], current["stress"]
    checks = {
        "base_total_nonnegative": base["total_return"] >= 0,
        "stress_total_nonnegative": stress["total_return"] >= 0,
        "drawdown_above_minus_8pct": base["max_drawdown"] > -0.08,
        "active_days_at_least_30": base["active_days"] >= 30,
        "combined_base_cagr_above_4pct": combined["base"] > 0.04,
        "combined_stress_cagr_above_4pct": combined["stress"] > 0.04,
    }
    failed = [name for name, passed in checks.items() if not passed]
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "phase": "confirmation_gate",
        "confirmation_sha256": _sha256(Path(args.confirmation)),
        "evaluation_sha256": _sha256(Path(args.evaluation)),
        "combined_cagr": combined,
        "checks": checks,
        "failed_checks": failed,
        "research_supports_demo_candidate": not failed,
    }
    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(required=True)
    analyze_parser = commands.add_parser("analyze")
    analyze_parser.add_argument("--phase", choices=tuple(PERIODS), required=True)
    analyze_parser.add_argument("--authorization")
    analyze_parser.add_argument("--cache-root", required=True)
    analyze_parser.add_argument("--manifest", required=True)
    analyze_parser.add_argument("--output-dir", required=True)
    analyze_parser.set_defaults(func=analyze)
    select_parser = commands.add_parser("select-development")
    select_parser.add_argument("--input", required=True)
    select_parser.add_argument("--output", required=True)
    select_parser.set_defaults(func=select_development)
    evaluation_parser = commands.add_parser("qualify-evaluation")
    evaluation_parser.add_argument("--input", required=True)
    evaluation_parser.add_argument("--output", required=True)
    evaluation_parser.set_defaults(func=qualify_evaluation)
    confirmation_parser = commands.add_parser("qualify-confirmation")
    confirmation_parser.add_argument("--evaluation", required=True)
    confirmation_parser.add_argument("--confirmation", required=True)
    confirmation_parser.add_argument("--output", required=True)
    confirmation_parser.set_defaults(func=qualify_confirmation)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
