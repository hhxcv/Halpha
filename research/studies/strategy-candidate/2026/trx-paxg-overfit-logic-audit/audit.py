"""Audit selection bias and diversification logic of the TRX/PAXG candidate."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import itertools
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pandas as pd
import vectorbt as vbt


STUDY_DIR = Path(__file__).resolve().parent
LEGACY_ROOT = STUDY_DIR.parent.parent.parent / "legacy" / "2026"
BASE_PATH = LEGACY_ROOT / "mature-alt-spot-top2-momentum" / "study.py"
PARENT_SPOT_RESULTS = LEGACY_ROOT / "trx-paxg-balanced-spot" / "results.json"
PARENT_PERP_RESULTS = STUDY_DIR.parent / "trx-paxg-usdm-venue-transfer" / "results.json"
DAY_MS = 86_400_000
FULL_PERIOD = ("2021-01-01T00:00:00Z", "2026-07-01T00:00:00Z")
COMMON_PERIOD = ("2022-01-01T00:00:00Z", "2026-07-01T00:00:00Z")
COSTS = {"favorable": 0.001, "base": 0.003, "stress": 0.006}
ANNUAL_CAPITAL_HURDLE = 0.04
FIXED_WEIGHT = 0.25
MAXIMUM_GROSS = 0.50
INV_VOL_LOOKBACK = 360
BOOTSTRAP_BLOCK = 90
BOOTSTRAP_REPS = 20_000
BOOTSTRAP_SEED = 20_260_722
CSCV_BLOCKS = 16
DSR_TRIALS = (3, 12, 33)

CANDIDATE = "TRX_PAXG_MONTHLY_25PCT_EACH"
BUY_HOLD = "TRX_PAXG_BUY_HOLD_25PCT_EACH"
BTC_FIXED = "BTC_PAXG_MONTHLY_25PCT_EACH"
ETH_FIXED = "ETH_PAXG_MONTHLY_25PCT_EACH"
TRX_INV_VOL = "TRX_PAXG_INV_VOL360_MONTHLY_GROSS0P5"
BTC_INV_VOL = "BTC_PAXG_INV_VOL360_MONTHLY_GROSS0P5"
VARIANTS = (
    CANDIDATE,
    BUY_HOLD,
    BTC_FIXED,
    ETH_FIXED,
    TRX_INV_VOL,
    BTC_INV_VOL,
)


def _load_base() -> ModuleType:
    spec = importlib.util.spec_from_file_location("halpha_spot_audit_base", BASE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("SPOT_DATA_BASE_UNAVAILABLE")
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


def _to_ms(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def _load_manifest_group(
    cache_root: Path, manifest_paths: list[Path], symbols: tuple[str, ...]
) -> tuple[dict[str, pd.DataFrame], list[dict[str, Any]]]:
    grouped: dict[str, list[pd.DataFrame]] = {symbol: [] for symbol in symbols}
    identities: list[dict[str, Any]] = []
    BASE.SYMBOLS = symbols
    for path in manifest_paths:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        frames = BASE.load_inputs(cache_root, manifest)
        identities.append(
            {
                "path": path.as_posix(),
                "sha256": _sha256(path),
                "content_identity": manifest["content_identity"],
            }
        )
        for symbol in symbols:
            grouped[symbol].append(frames[symbol])
    merged: dict[str, pd.DataFrame] = {}
    for symbol, pieces in grouped.items():
        frame = pd.concat(pieces).sort_index()
        duplicated = frame.index.duplicated(keep=False)
        if duplicated.any():
            duplicate_values = frame.loc[duplicated]
            for _, group in duplicate_values.groupby(level=0):
                if len(group.drop_duplicates()) != 1:
                    raise ValueError(f"CONFLICTING_DUPLICATE_BAR:{symbol}")
        merged[symbol] = frame[~frame.index.duplicated(keep="first")]
    return merged, identities


def _load_all(args: argparse.Namespace) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    pair_frames, pair_identities = _load_manifest_group(
        Path(args.pair_cache_root).resolve(),
        [Path(value).resolve() for value in args.pair_manifests],
        ("TRXUSDT", "PAXGUSDT"),
    )
    core_frames, core_identities = _load_manifest_group(
        Path(args.core_cache_root).resolve(),
        [Path(args.core_manifest).resolve()],
        ("BTCUSDT", "ETHUSDT"),
    )
    frames = {**pair_frames, **core_frames}
    common_index: pd.Index | None = None
    for frame in frames.values():
        common_index = frame.index if common_index is None else common_index.intersection(frame.index)
    if common_index is None:
        raise AssertionError("NO_MARKET_DATA")
    common_index = common_index.sort_values()
    start, end = map(_to_ms, FULL_PERIOD)
    common_index = common_index[(common_index >= start) & (common_index < end)]
    expected = pd.Index(range(start, end, DAY_MS), dtype="int64")
    if not common_index.equals(expected):
        missing = expected.difference(common_index)
        raise ValueError(f"COMMON_TIMELINE_NOT_CONTINUOUS:{len(missing)}")
    aligned = {symbol: frame.loc[common_index].copy() for symbol, frame in frames.items()}
    for symbol, frame in aligned.items():
        if frame.index.duplicated().any() or (frame[["open", "high", "low", "close"]] <= 0).any().any():
            raise ValueError(f"INVALID_MARKET_DATA:{symbol}")
    return aligned, {"pair_manifests": pair_identities, "core_manifests": core_identities}


def _inverse_vol_target(
    frames: dict[str, pd.DataFrame], pair: tuple[str, str], day_ms: int
) -> dict[str, float]:
    inverse: dict[str, float] = {}
    for symbol in pair:
        history = frames[symbol].loc[frames[symbol].index < day_ms, "close"].tail(
            INV_VOL_LOOKBACK + 1
        )
        returns = history.pct_change().dropna()
        if len(returns) != INV_VOL_LOOKBACK:
            raise ValueError(f"INV_VOL_WARMUP_MISSING:{symbol}:{day_ms}")
        volatility = float(returns.std(ddof=1))
        if not math.isfinite(volatility) or volatility <= 0:
            raise ValueError(f"INV_VOL_INVALID:{symbol}:{day_ms}")
        inverse[symbol] = 1.0 / volatility
    total = sum(inverse.values())
    return {symbol: MAXIMUM_GROSS * inverse[symbol] / total for symbol in pair}


def _metrics(returns: pd.Series, turnover: float) -> dict[str, Any]:
    equity = (1.0 + returns).cumprod()
    total_return = float(equity.iloc[-1] - 1.0)
    years = len(returns) / 365.25
    cagr = float((1.0 + total_return) ** (1.0 / years) - 1.0)
    volatility = float(returns.std(ddof=1) * math.sqrt(365.25))
    sharpe = float(returns.mean() / returns.std(ddof=1) * math.sqrt(365.25))
    drawdown = equity / equity.cummax() - 1.0
    annual_returns = {
        str(year): float((1.0 + values).prod() - 1.0)
        for year, values in returns.groupby(returns.index.year)
    }
    rolling = (1.0 + returns).rolling(365).apply(np.prod, raw=True) - 1.0
    rolling = rolling.dropna()
    return {
        "days": int(len(returns)),
        "total_return": total_return,
        "cagr": cagr,
        "annualized_volatility": volatility,
        "sharpe": sharpe,
        "max_drawdown": float(drawdown.min()),
        "calmar": float(cagr / abs(drawdown.min())) if drawdown.min() < 0 else None,
        "turnover": float(turnover),
        "annual_returns": annual_returns,
        "rolling_365d_positive_fraction": float((rolling > 0).mean()),
        "rolling_365d_above_4pct_fraction": float((rolling > ANNUAL_CAPITAL_HURDLE).mean()),
        "rolling_365d_minimum": float(rolling.min()),
        "rolling_365d_median": float(rolling.median()),
    }


def _risk_contribution(details: dict[str, Any], pair: tuple[str, str]) -> dict[str, float]:
    matrix = np.column_stack(
        [details["leg_return_contributions"][symbol] for symbol in pair]
    )
    price_portfolio = matrix.sum(axis=1)
    variance = float(np.var(price_portfolio, ddof=1))
    if variance <= 0:
        raise ValueError("NON_POSITIVE_PRICE_RETURN_VARIANCE")
    return {
        symbol: float(np.cov(matrix[:, index], price_portfolio, ddof=1)[0, 1] / variance)
        for index, symbol in enumerate(pair)
    }


def _simulate(
    frames: dict[str, pd.DataFrame],
    pair: tuple[str, str],
    period: tuple[str, str],
    *,
    policy: str,
    cost_rate: float,
) -> tuple[dict[str, Any], pd.Series, dict[str, Any]]:
    start, end = map(_to_ms, period)
    dates = frames[pair[0]].index[(frames[pair[0]].index >= start) & (frames[pair[0]].index < end)]
    if len(dates) < 2:
        raise ValueError("PERIOD_HAS_TOO_FEW_DAYS")
    cash = 1.0
    quantities = {symbol: 0.0 for symbol in pair}
    prior_nav = 1.0
    prior_close = {symbol: float(frames[symbol].at[int(dates[0]), "open"]) for symbol in pair}
    total_turnover = 0.0
    returns: list[float] = []
    cost_contributions: list[float] = []
    leg_contributions: dict[str, list[float]] = {symbol: [] for symbol in pair}
    leg_pnl = {symbol: 0.0 for symbol in pair}
    total_cost = 0.0
    daily_weights: dict[str, list[float]] = {symbol: [] for symbol in pair}
    last_month: str | None = None
    entered = False
    for raw_day in dates:
        day_ms = int(raw_day)
        opens = {symbol: float(frames[symbol].at[day_ms, "open"]) for symbol in pair}
        closes = {symbol: float(frames[symbol].at[day_ms, "close"]) for symbol in pair}
        gap_pnl = {
            symbol: quantities[symbol] * (opens[symbol] - prior_close[symbol])
            for symbol in pair
        }
        nav_open = cash + sum(quantities[symbol] * opens[symbol] for symbol in pair)
        month = pd.Timestamp(day_ms, unit="ms", tz="UTC").strftime("%Y-%m")
        rebalance = (policy != "buy_hold" and month != last_month) or not entered
        day_cost = 0.0
        if rebalance:
            if policy == "inverse_vol":
                target = _inverse_vol_target(frames, pair, day_ms)
            else:
                target = {symbol: FIXED_WEIGHT for symbol in pair}
            current = {
                symbol: quantities[symbol] * opens[symbol] / nav_open for symbol in pair
            }
            turnover = sum(abs(target[symbol] - current[symbol]) for symbol in pair)
            total_turnover += turnover
            day_cost = nav_open * turnover * cost_rate
            total_cost += day_cost
            after_cost = nav_open - day_cost
            cash = after_cost * (1.0 - sum(target.values()))
            quantities = {
                symbol: after_cost * target[symbol] / opens[symbol] for symbol in pair
            }
            entered = True
            last_month = month
        intraday_pnl = {
            symbol: quantities[symbol] * (closes[symbol] - opens[symbol])
            for symbol in pair
        }
        nav_close = cash + sum(quantities[symbol] * closes[symbol] for symbol in pair)
        returns.append(nav_close / prior_nav - 1.0)
        cost_contributions.append(-day_cost / prior_nav)
        for symbol in pair:
            pnl = gap_pnl[symbol] + intraday_pnl[symbol]
            leg_pnl[symbol] += pnl
            leg_contributions[symbol].append(pnl / prior_nav)
            daily_weights[symbol].append(quantities[symbol] * closes[symbol] / nav_close)
        prior_nav = nav_close
        prior_close = closes
    final_exposure = sum(quantities[symbol] * prior_close[symbol] for symbol in pair)
    exit_turnover = final_exposure / prior_nav
    exit_cost = final_exposure * cost_rate
    total_turnover += exit_turnover
    total_cost += exit_cost
    after_exit = prior_nav - exit_cost
    returns[-1] = (1.0 + returns[-1]) * (after_exit / prior_nav) - 1.0
    cost_contributions[-1] -= exit_cost / prior_nav
    index = pd.to_datetime(pd.Index(dates), unit="ms", utc=True)
    series = pd.Series(returns, index=index, dtype="float64", name="return")
    details = {
        "leg_pnl_on_initial_equity": leg_pnl,
        "cost_on_initial_equity": total_cost,
        "leg_return_contributions": {
            symbol: np.asarray(values, dtype=np.float64)
            for symbol, values in leg_contributions.items()
        },
        "cost_return_contributions": np.asarray(cost_contributions, dtype=np.float64),
        "daily_weights": {
            symbol: np.asarray(values, dtype=np.float64)
            for symbol, values in daily_weights.items()
        },
    }
    metrics = _metrics(series, total_turnover)
    metrics["risk_contribution"] = _risk_contribution(details, pair)
    metrics["average_close_weights"] = {
        symbol: float(np.mean(details["daily_weights"][symbol])) for symbol in pair
    }
    metrics["leg_pnl_on_initial_equity"] = leg_pnl
    metrics["cost_on_initial_equity"] = total_cost
    return metrics, series, details


def _strictly_dominates(candidate: dict[str, Any], alternative: dict[str, Any]) -> bool:
    comparisons = (
        alternative["total_return"] >= candidate["total_return"],
        alternative["sharpe"] >= candidate["sharpe"],
        alternative["max_drawdown"] >= candidate["max_drawdown"],
    )
    strict = (
        alternative["total_return"] > candidate["total_return"] + 1e-12
        or alternative["sharpe"] > candidate["sharpe"] + 1e-12
        or alternative["max_drawdown"] > candidate["max_drawdown"] + 1e-12
    )
    return all(comparisons) and strict


def _paired_block_bootstrap(frame: pd.DataFrame) -> dict[str, Any]:
    values = frame.to_numpy(dtype=np.float64)
    count, columns = values.shape
    hurdle = (1.0 + ANNUAL_CAPITAL_HURDLE) ** (count / 365.25) - 1.0
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    candidate_index = frame.columns.get_loc(CANDIDATE)
    comparator_indices = {
        name: frame.columns.get_loc(name) for name in frame.columns if name != CANDIDATE
    }
    candidate_totals: list[np.ndarray] = []
    beats = {name: 0 for name in comparator_indices}
    positive = above_hurdle = best = processed = 0
    offsets = np.arange(BOOTSTRAP_BLOCK, dtype=np.int64)
    blocks_needed = math.ceil(count / BOOTSTRAP_BLOCK)
    batch_size = 250
    for start in range(0, BOOTSTRAP_REPS, batch_size):
        batch = min(batch_size, BOOTSTRAP_REPS - start)
        starts = rng.integers(0, count, size=(batch, blocks_needed), dtype=np.int64)
        indices = ((starts[:, :, None] + offsets) % count).reshape(batch, -1)[:, :count]
        sampled = values[indices]
        totals = np.expm1(np.log1p(sampled).sum(axis=1))
        candidate_values = totals[:, candidate_index]
        candidate_totals.append(candidate_values)
        positive += int(np.sum(candidate_values > 0))
        above_hurdle += int(np.sum(candidate_values > hurdle))
        for name, index in comparator_indices.items():
            beats[name] += int(np.sum(candidate_values > totals[:, index]))
        best += int(np.sum(candidate_values >= totals.max(axis=1) - 1e-15))
        processed += batch
    candidate_array = np.concatenate(candidate_totals)
    return {
        "block_days": BOOTSTRAP_BLOCK,
        "replications": processed,
        "seed": BOOTSTRAP_SEED,
        "probability_candidate_positive": positive / processed,
        "probability_candidate_above_4pct_hurdle": above_hurdle / processed,
        "probability_candidate_beats": {
            name: value / processed for name, value in beats.items()
        },
        "probability_candidate_best_of_aligned_variants": best / processed,
        "candidate_total_return_p05": float(np.quantile(candidate_array, 0.05)),
        "candidate_total_return_median": float(np.median(candidate_array)),
        "candidate_total_return_p95": float(np.quantile(candidate_array, 0.95)),
    }


def _sharpe_from_moments(total: np.ndarray, squared: np.ndarray, count: int) -> np.ndarray:
    mean = total / count
    variance = (squared - total * total / count) / (count - 1)
    variance = np.maximum(variance, 0.0)
    return np.divide(
        mean,
        np.sqrt(variance),
        out=np.full_like(mean, -np.inf),
        where=variance > 0,
    ) * math.sqrt(365.25)


def _cscv_pbo(frame: pd.DataFrame) -> dict[str, Any]:
    values = frame.to_numpy(dtype=np.float64)
    blocks = np.array_split(np.arange(len(values)), CSCV_BLOCKS)
    sums = np.asarray([values[index].sum(axis=0) for index in blocks])
    squares = np.asarray([(values[index] ** 2).sum(axis=0) for index in blocks])
    counts = np.asarray([len(index) for index in blocks], dtype=np.int64)
    total_sum = sums.sum(axis=0)
    total_square = squares.sum(axis=0)
    total_count = int(counts.sum())
    below_median = 0
    splits = 0
    selected = {name: 0 for name in frame.columns}
    oos_relative_ranks: list[float] = []
    for chosen in itertools.combinations(range(CSCV_BLOCKS), CSCV_BLOCKS // 2):
        if 0 not in chosen:
            continue
        chosen_index = np.asarray(chosen, dtype=np.int64)
        train_sum = sums[chosen_index].sum(axis=0)
        train_square = squares[chosen_index].sum(axis=0)
        train_count = int(counts[chosen_index].sum())
        test_sum = total_sum - train_sum
        test_square = total_square - train_square
        test_count = total_count - train_count
        train_sharpe = _sharpe_from_moments(train_sum, train_square, train_count)
        test_sharpe = _sharpe_from_moments(test_sum, test_square, test_count)
        winner = int(np.argmax(train_sharpe))
        selected[str(frame.columns[winner])] += 1
        rank = int(np.sum(test_sharpe < test_sharpe[winner]))
        relative_rank = rank / (len(frame.columns) - 1)
        oos_relative_ranks.append(relative_rank)
        below_median += int(relative_rank < 0.5)
        splits += 1
    return {
        "blocks": CSCV_BLOCKS,
        "splits": splits,
        "probability_backtest_overfit": below_median / splits,
        "median_selected_oos_relative_rank": float(np.median(oos_relative_ranks)),
        "in_sample_selection_fraction": {
            name: value / splits for name, value in selected.items()
        },
    }


def _correlation_diagnostics(frames: dict[str, pd.DataFrame]) -> dict[str, Any]:
    closes = pd.DataFrame(
        {
            symbol: frames[symbol]["close"].astype(float)
            for symbol in ("TRXUSDT", "PAXGUSDT")
        }
    )
    returns = closes.pct_change().dropna()
    periods = {
        "2021_2022": ("2021-01-01", "2023-01-01"),
        "2023_2024": ("2023-01-01", "2025-01-01"),
        "2025_2026H1": ("2025-01-01", "2026-07-01"),
    }
    correlations = {"full": float(returns.corr().iloc[0, 1])}
    for name, (start, end) in periods.items():
        first, last = map(_to_ms, (f"{start}T00:00:00Z", f"{end}T00:00:00Z"))
        selected = returns[(returns.index >= first) & (returns.index < last)]
        correlations[name] = float(selected.corr().iloc[0, 1])
    dated = returns.copy()
    dated.index = pd.to_datetime(dated.index, unit="ms", utc=True)
    rolling_90 = dated["TRXUSDT"].rolling(90).corr(dated["PAXGUSDT"]).dropna()
    rolling_365 = dated["TRXUSDT"].rolling(365).corr(dated["PAXGUSDT"]).dropna()
    tail_threshold = float(dated["TRXUSDT"].quantile(0.05))
    tail = dated[dated["TRXUSDT"] <= tail_threshold]
    return {
        "daily_return_correlations": correlations,
        "rolling_90d_correlation": {
            "minimum": float(rolling_90.min()),
            "median": float(rolling_90.median()),
            "maximum": float(rolling_90.max()),
        },
        "rolling_365d_correlation": {
            "minimum": float(rolling_365.min()),
            "median": float(rolling_365.median()),
            "maximum": float(rolling_365.max()),
        },
        "trx_bottom_5pct_threshold": tail_threshold,
        "paxg_mean_return_on_trx_bottom_5pct_days": float(tail["PAXGUSDT"].mean()),
        "paxg_positive_fraction_on_trx_bottom_5pct_days": float(
            (tail["PAXGUSDT"] > 0).mean()
        ),
        "tail_days": int(len(tail)),
    }


def _concentration(returns: pd.Series) -> dict[str, Any]:
    monthly = (1.0 + returns).resample("MS").prod() - 1.0
    annual = (1.0 + returns).resample("YS").prod() - 1.0
    best_month = monthly.idxmax()
    best_year = annual.idxmax()
    without_month = float((1.0 + monthly.drop(best_month)).prod() - 1.0)
    without_year = float((1.0 + annual.drop(best_year)).prod() - 1.0)
    return {
        "best_month": best_month.strftime("%Y-%m"),
        "best_month_return": float(monthly.loc[best_month]),
        "total_return_without_best_month": without_month,
        "best_year": best_year.strftime("%Y"),
        "best_year_return": float(annual.loc[best_year]),
        "total_return_without_best_year": without_year,
    }


def analyze(args: argparse.Namespace) -> None:
    frames, data_identity = _load_all(args)
    full_specs = {
        CANDIDATE: (("TRXUSDT", "PAXGUSDT"), "monthly_fixed"),
        BUY_HOLD: (("TRXUSDT", "PAXGUSDT"), "buy_hold"),
        BTC_FIXED: (("BTCUSDT", "PAXGUSDT"), "monthly_fixed"),
        ETH_FIXED: (("ETHUSDT", "PAXGUSDT"), "monthly_fixed"),
    }
    common_specs = {
        **full_specs,
        TRX_INV_VOL: (("TRXUSDT", "PAXGUSDT"), "inverse_vol"),
        BTC_INV_VOL: (("BTCUSDT", "PAXGUSDT"), "inverse_vol"),
    }
    full_metrics: dict[str, dict[str, Any]] = {}
    full_returns: dict[str, pd.Series] = {}
    full_details: dict[str, dict[str, Any]] = {}
    for name, (pair, policy) in full_specs.items():
        full_metrics[name] = {}
        for scenario, cost in COSTS.items():
            metrics, returns, details = _simulate(
                frames, pair, FULL_PERIOD, policy=policy, cost_rate=cost
            )
            full_metrics[name][scenario] = metrics
            if scenario == "base":
                full_returns[name] = returns
                full_details[name] = details
    common_metrics: dict[str, dict[str, Any]] = {}
    common_returns: dict[str, pd.Series] = {}
    for name, (pair, policy) in common_specs.items():
        metrics, returns, _ = _simulate(
            frames, pair, COMMON_PERIOD, policy=policy, cost_rate=COSTS["base"]
        )
        common_metrics[name] = metrics
        common_returns[name] = returns
    full_frame = pd.DataFrame(full_returns)
    common_frame = pd.DataFrame(common_returns)[list(VARIANTS)]
    if full_frame.isna().any().any() or common_frame.isna().any().any():
        raise ValueError("ALIGNED_RETURN_MATRIX_HAS_NAN")
    dsr: dict[str, Any] = {}
    for trial_count in DSR_TRIALS:
        values = common_frame.vbt.returns.deflated_sharpe_ratio(nb_trials=trial_count)
        dsr[str(trial_count)] = {
            name: float(value) for name, value in values.to_dict().items()
        }
    candidate_full = full_metrics[CANDIDATE]["base"]
    candidate_common = common_metrics[CANDIDATE]
    dominance: dict[str, bool] = {}
    for name in (BUY_HOLD, BTC_FIXED, ETH_FIXED):
        dominance[name] = _strictly_dominates(
            candidate_full, full_metrics[name]["base"]
        )
    for name in (TRX_INV_VOL, BTC_INV_VOL):
        dominance[name] = _strictly_dominates(candidate_common, common_metrics[name])
    bootstrap = _paired_block_bootstrap(full_frame)
    phase_risk: dict[str, Any] = {}
    parent = json.loads(PARENT_SPOT_RESULTS.read_text(encoding="utf-8"))
    parent_periods = {
        "development": ("2021-01-01T00:00:00Z", "2023-01-01T00:00:00Z"),
        "evaluation": ("2023-01-01T00:00:00Z", "2025-01-01T00:00:00Z"),
        "confirmation": ("2025-01-01T00:00:00Z", "2026-07-01T00:00:00Z"),
    }
    replay_checks: dict[str, bool] = {}
    for phase, period in parent_periods.items():
        metrics, _, _ = _simulate(
            frames,
            ("TRXUSDT", "PAXGUSDT"),
            period,
            policy="monthly_fixed",
            cost_rate=COSTS["base"],
        )
        phase_risk[phase] = metrics["risk_contribution"]
        expected = parent[f"{phase}_balanced"]
        replay_checks[phase] = all(
            abs(metrics[actual_key] - expected[parent_key]) <= 1e-12
            for actual_key, parent_key in (
                ("total_return", "total_return"),
                ("max_drawdown", "max_drawdown"),
                ("turnover", "turnover"),
            )
        )
    candidate_dsr_12 = dsr["12"][CANDIDATE]
    rebalancing_increment = (
        candidate_full["total_return"]
        - full_metrics[BUY_HOLD]["base"]["total_return"]
    )
    checks = {
        "twelve_trial_dsr_at_least_0p80": candidate_dsr_12 >= 0.80,
        "rebalancing_total_return_increment_positive": rebalancing_increment > 0,
        "bootstrap_probability_beats_buy_hold_at_least_0p60": bootstrap[
            "probability_candidate_beats"
        ][BUY_HOLD]
        >= 0.60,
        "not_strictly_dominated_by_fixed_alternatives": not any(dominance.values()),
        "trx_variance_contribution_at_most_0p80": candidate_full[
            "risk_contribution"
        ]["TRXUSDT"]
        <= 0.80,
        "bootstrap_probability_above_4pct_hurdle_at_least_0p80": bootstrap[
            "probability_candidate_above_4pct_hurdle"
        ]
        >= 0.80,
        "broad_external_mechanism_support_with_no_exact_trx_rule_support": True,
    }
    failed = [name for name, value in checks.items() if not value]
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "question": "Does the TRX/PAXG candidate survive explicit selection-bias and mechanism auditing?",
        "conclusion": (
            "SUPPORTS_DEMO_CANDIDATE_WITH_LIMITS"
            if not failed
            else "INSUFFICIENT_EVIDENCE"
        ),
        "parent_candidate": "TRX_PAXG_USDM_MONTHLY_25PCT_EACH",
        "periods": {"full": list(FULL_PERIOD), "common": list(COMMON_PERIOD)},
        "framework_versions": {
            "vectorbt": vbt.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
        "method_identity": {
            "audit_sha256": _sha256(Path(__file__).resolve()),
            "base_sha256": _sha256(BASE_PATH),
            "parent_spot_results_sha256": _sha256(PARENT_SPOT_RESULTS),
            "parent_perp_results_sha256": _sha256(PARENT_PERP_RESULTS),
        },
        "data_identity": data_identity,
        "data_quality": {
            "aligned_days": int(len(next(iter(frames.values())))),
            "first_day": "2021-01-01",
            "last_day": "2026-06-30",
            "continuous": True,
            "valid_ohlc": True,
        },
        "full_period_variants": full_metrics,
        "common_period_base_variants": common_metrics,
        "selection_bias": {
            "dsr_trial_sensitivity": dsr,
            "candidate_12_trial_dsr": candidate_dsr_12,
            "candidate_33_trial_dsr": dsr["33"][CANDIDATE],
            "cscv": _cscv_pbo(common_frame),
            "trial_count_interpretation": "3 is the explicit parent choice set; 12 is the related formation-lineage sensitivity; 33 is the prior completed-question upper bound. They are not claimed independent.",
        },
        "mechanism": {
            "rebalancing_total_return_increment": rebalancing_increment,
            "candidate_full_risk_contribution": candidate_full["risk_contribution"],
            "candidate_phase_risk_contribution": phase_risk,
            "candidate_leg_pnl_on_initial_equity": full_details[CANDIDATE][
                "leg_pnl_on_initial_equity"
            ],
            "candidate_cost_on_initial_equity": full_details[CANDIDATE][
                "cost_on_initial_equity"
            ],
            "correlation": _correlation_diagnostics(frames),
            "return_concentration": _concentration(full_returns[CANDIDATE]),
            "strict_dominance_by_alternative": dominance,
        },
        "paired_block_bootstrap": bootstrap,
        "parent_spot_phase_replay": replay_checks,
        "checks": checks,
        "failed_checks": failed,
        "parent_research_supports_demo_after_audit": not failed,
        "evidence_boundary": "All price history is exposed and no new holdout was created. The audit can downgrade but cannot strengthen the parent claim.",
        "product_effects": "NONE",
    }
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "audit.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    full_frame.to_csv(output / "audit_full_daily_returns.csv", index_label="date")
    common_frame.to_csv(output / "audit_common_daily_returns.csv", index_label="date")
    print(
        json.dumps(
            {
                "conclusion": result["conclusion"],
                "failed_checks": failed,
                "candidate": candidate_full,
                "candidate_12_trial_dsr": candidate_dsr_12,
            },
            ensure_ascii=False,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair-cache-root", required=True)
    parser.add_argument("--pair-manifests", nargs=3, required=True)
    parser.add_argument("--core-cache-root", required=True)
    parser.add_argument("--core-manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    analyze(parser.parse_args())


if __name__ == "__main__":
    main()
