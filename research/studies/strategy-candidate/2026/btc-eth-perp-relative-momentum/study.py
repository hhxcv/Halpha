"""Sequential two-leg BTC/ETH perpetual relative-momentum study."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
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
BASE_PATH = STUDY_DIR.parent / "btcusdt-daily-donchian-ensemble" / "study.py"
RETURN_PATHS = (
    STUDY_DIR.parent / "btcusdt-daily-donchian-ensemble" / "development_daily_returns.csv",
    STUDY_DIR.parent / "btcusdt-daily-donchian-carry-conditioned" / "development_daily_returns.csv",
    STUDY_DIR.parent / "btcusdt-spot-daily-donchian" / "development_daily_returns.csv",
    STUDY_DIR.parent / "ethusdt-daily-donchian-short-carry-transfer" / "development_daily_returns.csv",
    STUDY_DIR.parent / "btcusdt-8h-donchian-execution-transfer" / "development_daily_returns.csv",
)
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
LOOKBACK_DAYS = 90
LEG_WEIGHT = 0.25
REBALANCE_THRESHOLD = 0.20
RELATED_TRIAL_COUNT = 13


def _load_base() -> ModuleType:
    spec = importlib.util.spec_from_file_location("halpha_relative_momentum_base", BASE_PATH)
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


def _utc_ms(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def _load_pair(args: argparse.Namespace) -> tuple[Any, Any]:
    btc = BASE._load_market_data(
        Path(args.btc_cache_root).resolve(), Path(args.btc_manifest).resolve()
    )
    eth = BASE._load_market_data(
        Path(args.eth_cache_root).resolve(), Path(args.eth_manifest).resolve()
    )
    if not np.array_equal(btc.open_time, eth.open_time):
        raise ValueError("BTC_ETH_TIMELINES_NOT_IDENTICAL")
    return btc, eth


def _monthly_relative_weights(btc: Any, eth: Any) -> tuple[np.ndarray, np.ndarray]:
    btc_weight = np.zeros(len(btc.close), dtype=np.float64)
    eth_weight = np.zeros(len(eth.close), dtype=np.float64)
    direction = 0.0
    dates = pd.to_datetime(btc.open_time, unit="ms", utc=True)
    for index, date in enumerate(dates):
        if date.day == 1 and index > LOOKBACK_DAYS:
            current_ratio = float(eth.close[index - 1] / btc.close[index - 1])
            prior_ratio = float(
                eth.close[index - 1 - LOOKBACK_DAYS]
                / btc.close[index - 1 - LOOKBACK_DAYS]
            )
            direction = 1.0 if current_ratio > prior_ratio else -1.0
        if direction > 0:
            btc_weight[index] = -LEG_WEIGHT
            eth_weight[index] = LEG_WEIGHT
        elif direction < 0:
            btc_weight[index] = LEG_WEIGHT
            eth_weight[index] = -LEG_WEIGHT
    return btc_weight, eth_weight


def _static_weights(length: int, direction: int) -> tuple[np.ndarray, np.ndarray]:
    return (
        np.full(length, -LEG_WEIGHT * direction, dtype=np.float64),
        np.full(length, LEG_WEIGHT * direction, dtype=np.float64),
    )


def _long_both_weights(length: int) -> tuple[np.ndarray, np.ndarray]:
    return (
        np.full(length, LEG_WEIGHT, dtype=np.float64),
        np.full(length, LEG_WEIGHT, dtype=np.float64),
    )


def _should_trade(target: float, current: float) -> bool:
    if target == 0.0 and current == 0.0:
        return False
    if target == 0.0 or current == 0.0 or math.copysign(1.0, target) != math.copysign(1.0, current):
        return True
    denominator = max(abs(target), abs(current))
    return abs(target - current) > REBALANCE_THRESHOLD * denominator


def _targets_after_cost(
    equity: float,
    current: tuple[float, float],
    target_weights: tuple[float, float],
    trade_flags: tuple[bool, bool],
    cost_rate: float,
) -> tuple[tuple[float, float], float]:
    post_equity = equity
    desired = current
    for _ in range(8):
        desired = tuple(
            target * post_equity if trade else now
            for target, trade, now in zip(target_weights, trade_flags, current, strict=True)
        )
        cost = sum(abs(after - before) for after, before in zip(desired, current, strict=True)) * cost_rate
        post_equity = equity - cost
    return (float(desired[0]), float(desired[1])), equity - post_equity


def _statistics(
    dates: pd.DatetimeIndex,
    returns: np.ndarray,
    *,
    turnover: float,
    trade_events: int,
    active_days: int,
    maximum_gross: float,
    maximum_absolute_net: float,
    price_pnl: dict[str, float],
    funding_pnl: dict[str, float],
    fee_cost: float,
    slippage_cost: float,
) -> dict[str, Any]:
    series = pd.Series(returns, index=dates)
    equity = (1.0 + series).cumprod()
    total = float(equity.iloc[-1] - 1.0)
    years = len(series) / 365.25
    cagr = float(equity.iloc[-1] ** (1.0 / years) - 1.0)
    volatility = float(series.std(ddof=1) * math.sqrt(365.0))
    sharpe = float(series.mean() / series.std(ddof=1) * math.sqrt(365.0))
    path = np.concatenate(([1.0], equity.to_numpy(dtype=np.float64)))
    drawdown = path / np.maximum.accumulate(path) - 1.0
    max_drawdown = float(drawdown.min())
    annual = {
        str(int(year)): float((1.0 + values).prod() - 1.0)
        for year, values in series.groupby(series.index.year)
    }
    monthly = (1.0 + series).groupby([series.index.year, series.index.month]).prod() - 1.0
    return {
        "days": int(len(series)),
        "total_return": total,
        "cagr": cagr,
        "annualized_volatility": volatility,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "calmar": cagr / abs(max_drawdown) if max_drawdown < 0 else None,
        "daily_skew": float(series.skew()),
        "daily_excess_kurtosis": float(series.kurt()),
        "positive_day_fraction": float((series > 0).mean()),
        "positive_month_fraction": float((monthly > 0).mean()),
        "annual_returns": annual,
        "turnover": float(turnover),
        "trade_events": int(trade_events),
        "active_days": int(active_days),
        "maximum_gross_weight": float(maximum_gross),
        "maximum_absolute_net_weight": float(maximum_absolute_net),
        "price_pnl_on_initial_equity": price_pnl,
        "funding_pnl_on_initial_equity": funding_pnl,
        "fee_cost_on_initial_equity": float(fee_cost),
        "slippage_cost_on_initial_equity": float(slippage_cost),
        "terminal_liquidation": True,
    }


def _simulate(
    btc: Any,
    eth: Any,
    weights: tuple[np.ndarray, np.ndarray],
    *,
    start_ms: int,
    end_ms: int,
    fee_rate: float,
    slippage_rate: float,
) -> tuple[dict[str, Any], np.ndarray, pd.DatetimeIndex]:
    start = int(np.searchsorted(btc.open_time, start_ms, side="left"))
    end = int(np.searchsorted(btc.open_time, end_ms, side="left"))
    if start <= LOOKBACK_DAYS or end <= start:
        raise ValueError("PERIOD_OUTSIDE_DATA")
    equity = 1.0
    quantities = [0.0, 0.0]
    prior_close = [float(btc.close[start - 1]), float(eth.close[start - 1])]
    returns: list[float] = []
    dates: list[pd.Timestamp] = []
    turnover = trade_events = active_days = 0
    maximum_gross = maximum_absolute_net = 0.0
    price_pnl = {"BTCUSDT": 0.0, "ETHUSDT": 0.0}
    funding_pnl = {"BTCUSDT": 0.0, "ETHUSDT": 0.0}
    fee_cost = slippage_cost = 0.0
    total_cost = fee_rate + slippage_rate
    markets = (btc, eth)
    symbols = ("BTCUSDT", "ETHUSDT")
    for index in range(start, end):
        initial = equity
        opens = [float(market.open[index]) for market in markets]
        closes = [float(market.close[index]) for market in markets]
        for leg, (market, symbol) in enumerate(zip(markets, symbols, strict=True)):
            gap = quantities[leg] * (opens[leg] - prior_close[leg])
            funding = -quantities[leg] * float(market.funding_boundary_value[index])
            equity += gap + funding
            price_pnl[symbol] += gap
            funding_pnl[symbol] += funding
        current = tuple(quantities[leg] * opens[leg] for leg in range(2))
        current_weights = tuple(value / equity for value in current)
        target_weights = (float(weights[0][index]), float(weights[1][index]))
        trade_flags = tuple(
            _should_trade(target, now)
            for target, now in zip(target_weights, current_weights, strict=True)
        )
        if any(trade_flags):
            desired, cost = _targets_after_cost(
                equity, current, target_weights, trade_flags, total_cost
            )
            turnover += sum(
                abs(after - before)
                for after, before in zip(desired, current, strict=True)
            ) / equity
            trade_events += sum(trade_flags)
            if total_cost > 0:
                fee_cost += cost * fee_rate / total_cost
                slippage_cost += cost * slippage_rate / total_cost
            equity -= cost
            quantities = [desired[leg] / opens[leg] for leg in range(2)]
        for leg, (market, symbol) in enumerate(zip(markets, symbols, strict=True)):
            price = quantities[leg] * (closes[leg] - opens[leg])
            funding = -quantities[leg] * float(market.funding_intraday_value[index])
            equity += price + funding
            price_pnl[symbol] += price
            funding_pnl[symbol] += funding
        if equity <= 0:
            raise ValueError("NON_POSITIVE_EQUITY")
        notionals = [quantities[leg] * closes[leg] / equity for leg in range(2)]
        maximum_gross = max(maximum_gross, sum(abs(value) for value in notionals))
        maximum_absolute_net = max(maximum_absolute_net, abs(sum(notionals)))
        if any(quantity != 0 for quantity in quantities):
            active_days += 1
        returns.append(equity / initial - 1.0)
        dates.append(pd.Timestamp(int(btc.open_time[index]), unit="ms", tz="UTC"))
        prior_close = closes
    terminal_notional = sum(abs(quantities[leg] * prior_close[leg]) for leg in range(2))
    terminal_cost = terminal_notional * total_cost
    before = equity
    equity -= terminal_cost
    turnover += terminal_notional / before
    trade_events += sum(quantity != 0 for quantity in quantities)
    if total_cost > 0:
        fee_cost += terminal_cost * fee_rate / total_cost
        slippage_cost += terminal_cost * slippage_rate / total_cost
    returns[-1] = (1.0 + returns[-1]) * (equity / before) - 1.0
    date_index = pd.DatetimeIndex(dates)
    return (
        _statistics(
            date_index,
            np.asarray(returns, dtype=np.float64),
            turnover=turnover,
            trade_events=trade_events,
            active_days=active_days,
            maximum_gross=maximum_gross,
            maximum_absolute_net=maximum_absolute_net,
            price_pnl=price_pnl,
            funding_pnl=funding_pnl,
            fee_cost=fee_cost,
            slippage_cost=slippage_cost,
        ),
        np.asarray(returns, dtype=np.float64),
        date_index,
    )


def _authorization(phase: str, path: str | None) -> None:
    if phase == "development":
        return
    if not path:
        raise ValueError("AUTHORIZATION_REQUIRED")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    key = "evaluation_authorized" if phase == "evaluation" else "confirmation_authorized"
    if not payload.get(key):
        raise ValueError(f"{phase.upper()}_NOT_AUTHORIZED")


def _development_dsr(
    returns: np.ndarray, dates: pd.DatetimeIndex
) -> tuple[float, dict[str, str]]:
    frames = [pd.read_csv(path, index_col="date", parse_dates=True) for path in RETURN_PATHS]
    frames.append(pd.DataFrame({"BTC_ETH_RELATIVE_MOMENTUM_90D": returns}, index=dates))
    matrix = pd.concat(frames, axis=1, join="inner")
    if len(matrix) != len(dates) or matrix.shape[1] != RELATED_TRIAL_COUNT:
        raise ValueError(f"RELATED_TRIAL_MATRIX_INVALID:{matrix.shape}")
    dsr = matrix.vbt.returns.deflated_sharpe_ratio(nb_trials=RELATED_TRIAL_COUNT)
    return float(dsr["BTC_ETH_RELATIVE_MOMENTUM_90D"]), {
        path.parent.name: _sha256(path) for path in RETURN_PATHS
    }


def analyze(args: argparse.Namespace) -> None:
    _authorization(args.phase, args.authorization)
    btc, eth = _load_pair(args)
    start_ms, end_ms = map(_utc_ms, PERIODS[args.phase])
    candidate_weights = _monthly_relative_weights(btc, eth)
    benchmark_weights = {
        "static_long_eth_short_btc": _static_weights(len(btc.close), 1),
        "static_long_btc_short_eth": _static_weights(len(btc.close), -1),
        "long_both_common_beta": _long_both_weights(len(btc.close)),
    }
    candidate: dict[str, Any] = {}
    base_returns: np.ndarray | None = None
    base_dates: pd.DatetimeIndex | None = None
    benchmarks: dict[str, dict[str, Any]] = {name: {} for name in benchmark_weights}
    for scenario, costs in SCENARIOS.items():
        metrics, returns, dates = _simulate(
            btc,
            eth,
            candidate_weights,
            start_ms=start_ms,
            end_ms=end_ms,
            fee_rate=costs["fee"],
            slippage_rate=costs["slippage"],
        )
        candidate[scenario] = metrics
        if scenario == "base":
            base_returns, base_dates = returns, dates
        for name, weights in benchmark_weights.items():
            benchmark, _, _ = _simulate(
                btc,
                eth,
                weights,
                start_ms=start_ms,
                end_ms=end_ms,
                fee_rate=costs["fee"],
                slippage_rate=costs["slippage"],
            )
            benchmarks[name][scenario] = benchmark
    if base_returns is None or base_dates is None:
        raise AssertionError("BASE_RETURNS_MISSING")
    dsr = trial_inputs = None
    if args.phase == "development":
        dsr, trial_inputs = _development_dsr(base_returns, base_dates)
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
            "btc_data_identity": btc.manifest_identity,
            "eth_data_identity": eth.manifest_identity,
            "related_trial_inputs": trial_inputs,
        },
        "data_quality": {"BTCUSDT": btc.quality, "ETHUSDT": eth.quality},
        "rules": {
            "lookback_days": LOOKBACK_DAYS,
            "signal": "90-day ETH/BTC ratio direction fixed at each month open using prior closes",
            "leg_weight": LEG_WEIGHT,
            "target_gross": 2 * LEG_WEIGHT,
            "target_net": 0.0,
            "rebalance_threshold": REBALANCE_THRESHOLD,
        },
        "costs_per_unit_turnover": SCENARIOS,
        "candidate": {
            "candidate_id": "BTC_ETH_RELATIVE_MOMENTUM_90D",
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
            "candidate_id": "BTC_ETH_RELATIVE_MOMENTUM_90D",
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
    pd.DataFrame(
        {"BTC_ETH_RELATIVE_MOMENTUM_90D": base_returns}, index=base_dates
    ).to_csv(output / f"{args.phase}_daily_returns.csv", index_label="date")
    print(json.dumps({"phase": args.phase, "candidate": "BTC_ETH_RELATIVE_MOMENTUM_90D"}))


def _best_static(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    items = [
        payload["benchmarks"]["static_long_eth_short_btc"]["base"],
        payload["benchmarks"]["static_long_btc_short_eth"]["base"],
    ]
    return max(items, key=lambda item: item["sharpe"]), max(
        items, key=lambda item: item["calmar"]
    )


def select_development(args: argparse.Namespace) -> None:
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    candidate = payload["candidate"]
    base = candidate["scenarios"]["base"]
    stress = candidate["scenarios"]["stress"]
    best_sharpe, best_calmar = _best_static(payload)
    annual = base["annual_returns"]
    checks = {
        "base_total_positive": base["total_return"] > 0,
        "stress_total_positive": stress["total_return"] > 0,
        "stress_cagr_above_4pct": stress["cagr"] > 0.04,
        "base_sharpe_at_least_0p75": base["sharpe"] >= 0.75,
        "thirteen_trial_dsr_at_least_0p80": candidate["deflated_sharpe_probability"] >= 0.80,
        "drawdown_above_minus_15pct": base["max_drawdown"] > -0.15,
        "two_of_three_years_positive": sum(annual[str(year)] > 0 for year in (2021, 2022, 2023)) >= 2,
        "worst_year_at_least_minus_5pct": min(annual[str(year)] for year in (2021, 2022, 2023)) >= -0.05,
        "active_days_at_least_1000": base["active_days"] >= 1000,
        "turnover_at_most_25": base["turnover"] <= 25,
        "sharpe_exceeds_both_static_directions": base["sharpe"] > best_sharpe["sharpe"],
        "calmar_exceeds_both_static_directions": base["calmar"] > best_calmar["calmar"],
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
    best_sharpe, best_calmar = _best_static(payload)
    annual = base["annual_returns"]
    checks = {
        "base_total_positive": base["total_return"] > 0,
        "stress_total_positive": stress["total_return"] > 0,
        "stress_cagr_above_4pct": stress["cagr"] > 0.04,
        "both_years_positive": annual["2024"] > 0 and annual["2025"] > 0,
        "base_sharpe_at_least_0p75": base["sharpe"] >= 0.75,
        "drawdown_above_minus_15pct": base["max_drawdown"] > -0.15,
        "active_days_at_least_650": base["active_days"] >= 650,
        "turnover_at_most_20": base["turnover"] <= 20,
        "sharpe_exceeds_both_static_directions": base["sharpe"] > best_sharpe["sharpe"],
        "calmar_exceeds_both_static_directions": base["calmar"] > best_calmar["calmar"],
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
    evaluation = json.loads(Path(args.evaluation).read_text(encoding="utf-8"))
    confirmation = json.loads(Path(args.confirmation).read_text(encoding="utf-8"))
    previous = evaluation["candidate"]["scenarios"]
    current = confirmation["candidate"]["scenarios"]
    combined: dict[str, float] = {}
    for scenario in ("base", "stress"):
        growth = (1 + previous[scenario]["total_return"]) * (1 + current[scenario]["total_return"])
        days = previous[scenario]["days"] + current[scenario]["days"]
        combined[scenario] = growth ** (365.25 / days) - 1.0
    base, stress = current["base"], current["stress"]
    checks = {
        "base_total_nonnegative": base["total_return"] >= 0,
        "stress_total_nonnegative": stress["total_return"] >= 0,
        "drawdown_above_minus_8pct": base["max_drawdown"] > -0.08,
        "active_days_at_least_150": base["active_days"] >= 150,
        "combined_base_cagr_above_4pct": combined["base"] > 0.04,
        "combined_stress_cagr_above_4pct": combined["stress"] > 0.04,
    }
    failed = [name for name, passed in checks.items() if not passed]
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "phase": "confirmation_gate",
        "evaluation_sha256": _sha256(Path(args.evaluation)),
        "confirmation_sha256": _sha256(Path(args.confirmation)),
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
    analyze_parser.add_argument("--btc-cache-root", required=True)
    analyze_parser.add_argument("--btc-manifest", required=True)
    analyze_parser.add_argument("--eth-cache-root", required=True)
    analyze_parser.add_argument("--eth-manifest", required=True)
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
