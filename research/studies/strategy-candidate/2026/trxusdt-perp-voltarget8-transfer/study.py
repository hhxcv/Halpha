"""Sequential fixed transfer of the supported TRX 8% volatility-target strategy."""

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
TRANSFER_PATH = STUDY_DIR.parent / "trx-paxg-usdm-venue-transfer" / "study.py"
SPOT_RESULTS_PATH = (
    STUDY_DIR.parent.parent.parent
    / "legacy"
    / "2026"
    / "trxusdt-voltarget-8pct-long"
    / "results.json"
)
PERIODS = {
    "development": ("2021-01-01T00:00:00Z", "2023-01-01T00:00:00Z"),
    "evaluation": ("2023-01-01T00:00:00Z", "2025-01-01T00:00:00Z"),
    "confirmation": ("2025-01-01T00:00:00Z", "2026-07-01T00:00:00Z"),
}
TARGET_VOLS = (0.06, 0.08, 0.10)
PRIMARY_TARGET_VOL = 0.08
VOL_LOOKBACK_DAYS = 60
MAXIMUM_GROSS = 0.50
ANNUAL_CAPITAL_HURDLE = 0.04
SCENARIOS = {
    "favorable": {"fee": 0.0004, "slippage": 0.0006},
    "base": {"fee": 0.0004, "slippage": 0.0026},
    "stress": {"fee": 0.0004, "slippage": 0.0056},
}


def _load_transfer() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "halpha_trx_voltarget_base", TRANSFER_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("TRANSFER_STUDY_IMPORT_UNAVAILABLE")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


TRANSFER = _load_transfer()
BASE = TRANSFER.BASE


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_ms(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def _load_market(args: argparse.Namespace) -> tuple[Any, dict[str, Any]]:
    root = Path(args.cache_root).resolve()
    manifest = Path(args.manifest).resolve()
    contract = TRANSFER._verify_contract_snapshot(root, manifest, "TRXUSDT")
    return BASE._load_market_data(root, manifest), contract


def _monthly_weights(market: Any, target_vol: float) -> np.ndarray:
    weights = np.zeros(len(market.close), dtype=np.float64)
    current = 0.0
    dates = pd.to_datetime(market.open_time, unit="ms", utc=True)
    for index, date in enumerate(dates):
        if date.day == 1:
            if index < VOL_LOOKBACK_DAYS + 1:
                current = 0.0
            else:
                closes = market.close[index - VOL_LOOKBACK_DAYS - 1 : index]
                returns = np.diff(np.log(closes))
                realized = float(np.std(returns, ddof=1) * math.sqrt(365.0))
                current = (
                    min(MAXIMUM_GROSS, target_vol / realized)
                    if realized > 0 and math.isfinite(realized)
                    else 0.0
                )
        weights[index] = current
    return weights


def _target_after_cost(
    equity: float, current_notional: float, target_weight: float, cost_rate: float
) -> tuple[float, float]:
    post_equity = equity
    desired = current_notional
    for _ in range(8):
        desired = target_weight * post_equity
        cost = abs(desired - current_notional) * cost_rate
        post_equity = equity - cost
    return float(desired), float(equity - post_equity)


def _simulate(
    market: Any,
    weights: np.ndarray,
    *,
    start_ms: int,
    end_ms: int,
    fee_rate: float,
    slippage_rate: float,
    include_funding: bool,
) -> tuple[dict[str, Any], np.ndarray, pd.DatetimeIndex]:
    start = int(np.searchsorted(market.open_time, start_ms, side="left"))
    end = int(np.searchsorted(market.open_time, end_ms, side="left"))
    if start < VOL_LOOKBACK_DAYS + 1 or end <= start:
        raise ValueError("PERIOD_OUTSIDE_DATA")
    equity = 1.0
    quantity = 0.0
    prior_close = float(market.close[start - 1])
    returns: list[float] = []
    dates: list[pd.Timestamp] = []
    turnover = trade_events = active_days = 0
    maximum_gross = maximum_absolute_net = 0.0
    price_pnl = {"TRXUSDT": 0.0}
    funding_pnl = {"TRXUSDT": 0.0}
    fee_cost = slippage_cost = 0.0
    total_cost = fee_rate + slippage_rate
    selected_monthly_weights: list[float] = []
    for index in range(start, end):
        initial = equity
        date = pd.Timestamp(int(market.open_time[index]), unit="ms", tz="UTC")
        open_price = float(market.open[index])
        close_price = float(market.close[index])
        gap = quantity * (open_price - prior_close)
        boundary_funding = (
            -quantity * float(market.funding_boundary_value[index])
            if include_funding
            else 0.0
        )
        equity += gap + boundary_funding
        price_pnl["TRXUSDT"] += gap
        funding_pnl["TRXUSDT"] += boundary_funding
        if date.day == 1:
            current_notional = quantity * open_price
            target_weight = float(weights[index])
            desired, cost = _target_after_cost(
                equity, current_notional, target_weight, total_cost
            )
            change = abs(desired - current_notional)
            turnover += change / equity
            trade_events += int(change > 1e-12)
            if total_cost > 0:
                fee_cost += cost * fee_rate / total_cost
                slippage_cost += cost * slippage_rate / total_cost
            equity -= cost
            quantity = desired / open_price
            selected_monthly_weights.append(target_weight)
        price = quantity * (close_price - open_price)
        intraday_funding = (
            -quantity * float(market.funding_intraday_value[index])
            if include_funding
            else 0.0
        )
        equity += price + intraday_funding
        price_pnl["TRXUSDT"] += price
        funding_pnl["TRXUSDT"] += intraday_funding
        if equity <= 0:
            raise ValueError("NON_POSITIVE_EQUITY")
        notional_weight = quantity * close_price / equity
        maximum_gross = max(maximum_gross, abs(notional_weight))
        maximum_absolute_net = max(maximum_absolute_net, abs(notional_weight))
        active_days += int(quantity != 0.0)
        returns.append(equity / initial - 1.0)
        dates.append(date)
        prior_close = close_price
    terminal_notional = abs(quantity * prior_close)
    terminal_cost = terminal_notional * total_cost
    before = equity
    equity -= terminal_cost
    turnover += terminal_notional / before
    trade_events += int(quantity != 0.0)
    if total_cost > 0:
        fee_cost += terminal_cost * fee_rate / total_cost
        slippage_cost += terminal_cost * slippage_rate / total_cost
    returns[-1] = (1.0 + returns[-1]) * (equity / before) - 1.0
    date_index = pd.DatetimeIndex(dates)
    metrics = TRANSFER.PAIR._statistics(
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
    )
    metrics["monthly_target_weight_min"] = float(min(selected_monthly_weights))
    metrics["monthly_target_weight_median"] = float(np.median(selected_monthly_weights))
    metrics["monthly_target_weight_max"] = float(max(selected_monthly_weights))
    return metrics, np.asarray(returns, dtype=np.float64), date_index


def _authorization(phase: str, path: str | None) -> None:
    if phase == "development":
        return
    if not path:
        raise ValueError("AUTHORIZATION_REQUIRED")
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    key = (
        "evaluation_authorized" if phase == "evaluation" else "confirmation_authorized"
    )
    if not payload.get(key):
        raise ValueError(f"{phase.upper()}_NOT_AUTHORIZED")


def analyze(args: argparse.Namespace) -> None:
    _authorization(args.phase, args.authorization)
    market, contract = _load_market(args)
    start_ms, end_ms = map(_utc_ms, PERIODS[args.phase])
    weights = {target: _monthly_weights(market, target) for target in TARGET_VOLS}
    candidates: dict[str, dict[str, Any]] = {}
    benchmarks: dict[str, dict[str, Any]] = {
        "price_only_primary": {},
        "unscaled_half_long": {},
    }
    base_returns: np.ndarray | None = None
    base_dates: pd.DatetimeIndex | None = None
    for target, target_weights in weights.items():
        key = f"{target:.2f}"
        candidates[key] = {}
        for scenario, costs in SCENARIOS.items():
            metrics, returns, dates = _simulate(
                market,
                target_weights,
                start_ms=start_ms,
                end_ms=end_ms,
                fee_rate=costs["fee"],
                slippage_rate=costs["slippage"],
                include_funding=True,
            )
            candidates[key][scenario] = metrics
            if target == PRIMARY_TARGET_VOL and scenario == "base":
                base_returns, base_dates = returns, dates
    for scenario, costs in SCENARIOS.items():
        benchmarks["price_only_primary"][scenario], _, _ = _simulate(
            market,
            weights[PRIMARY_TARGET_VOL],
            start_ms=start_ms,
            end_ms=end_ms,
            fee_rate=costs["fee"],
            slippage_rate=costs["slippage"],
            include_funding=False,
        )
        benchmarks["unscaled_half_long"][scenario], _, _ = _simulate(
            market,
            np.full(len(market.close), MAXIMUM_GROSS, dtype=np.float64),
            start_ms=start_ms,
            end_ms=end_ms,
            fee_rate=costs["fee"],
            slippage_rate=costs["slippage"],
            include_funding=True,
        )
    if base_returns is None or base_dates is None:
        raise AssertionError("BASE_RETURNS_MISSING")
    spot_results = json.loads(SPOT_RESULTS_PATH.read_text(encoding="utf-8"))
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
            "transfer_base_sha256": _sha256(TRANSFER_PATH),
            "spot_results_sha256": _sha256(SPOT_RESULTS_PATH),
            "spot_conclusion": spot_results["conclusion"],
            "data_identity": market.manifest_identity,
        },
        "contract_snapshot": contract,
        "data_quality": market.quality,
        "rules": {
            "instrument": "TRXUSDT USD-M perpetual",
            "volatility_lookback_days": VOL_LOOKBACK_DAYS,
            "target_volatilities": list(TARGET_VOLS),
            "primary_target_volatility": PRIMARY_TARGET_VOL,
            "maximum_gross": MAXIMUM_GROSS,
            "direction": "always long",
            "rebalance": "first UTC daily open monthly using prior completed close",
            "annual_capital_hurdle": ANNUAL_CAPITAL_HURDLE,
        },
        "costs_per_unit_turnover": SCENARIOS,
        "candidates": candidates,
        "benchmarks": benchmarks,
        "product_effects": "NONE",
    }
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / f"{args.phase}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    rows: list[dict[str, Any]] = []
    for target, scenarios in candidates.items():
        for scenario, metrics in scenarios.items():
            row: dict[str, Any] = {"target_vol": target, "scenario": scenario}
            for key, value in metrics.items():
                if key == "annual_returns":
                    for year, annual_return in value.items():
                        row[f"return_{year}"] = annual_return
                elif not isinstance(value, (dict, list)):
                    row[key] = value
            rows.append(row)
    pd.DataFrame(rows).to_csv(output / f"{args.phase}.csv", index=False)
    pd.DataFrame({"TRXUSDT_PERP_VOL60_TARGET8": base_returns}, index=base_dates).to_csv(
        output / f"{args.phase}_daily_returns.csv", index_label="date"
    )
    print(
        json.dumps(
            {
                "phase": args.phase,
                "candidate": candidates["0.08"]["base"],
            }
        )
    )


def _hurdle(metrics: dict[str, Any]) -> float:
    return (1.0 + metrics["total_return"]) / (
        (1.0 + ANNUAL_CAPITAL_HURDLE) ** (metrics["days"] / 365.25)
    ) - 1.0


def _funding_drag(metrics: dict[str, Any]) -> float | None:
    price = float(sum(metrics["price_pnl_on_initial_equity"].values()))
    funding = float(sum(metrics["funding_pnl_on_initial_equity"].values()))
    return max(0.0, -funding) / price if price > 0 else None


def select_development(args: argparse.Namespace) -> None:
    source = Path(args.input)
    payload = json.loads(source.read_text(encoding="utf-8"))
    primary = payload["candidates"]["0.08"]
    base, stress = primary["base"], primary["stress"]
    passive = payload["benchmarks"]["unscaled_half_long"]["base"]
    funding_drag = _funding_drag(base)
    checks = {
        "spot_support_inherited": payload["method_identity"]["spot_conclusion"]
        == "SUPPORTS_WITHIN_SCOPE",
        "base_total_positive": base["total_return"] > 0,
        "stress_total_positive": stress["total_return"] > 0,
        "stress_after_4pct_hurdle_positive": _hurdle(stress) > 0,
        "base_sharpe_at_least_0p45": base["sharpe"] >= 0.45,
        "drawdown_above_minus_12pct": base["max_drawdown"] > -0.12,
        "drawdown_shallower_than_unscaled": base["max_drawdown"]
        > passive["max_drawdown"],
        "six_and_ten_pct_neighbors_positive": all(
            payload["candidates"][key]["base"]["total_return"] > 0
            for key in ("0.06", "0.10")
        ),
        "active_days_at_least_700": base["active_days"] >= 700,
        "turnover_at_most_3": base["turnover"] <= 3.0,
        "funding_drag_at_most_half_price_pnl": funding_drag is not None
        and funding_drag <= 0.50,
    }
    failed = [name for name, passed in checks.items() if not passed]
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "phase": "development_selection",
        "source_sha256": _sha256(source),
        "checks": checks,
        "failed_checks": failed,
        "stress_return_after_4pct_annual_hurdle": _hurdle(stress),
        "funding_drag_fraction_of_price_pnl": funding_drag,
        "evaluation_authorized": not failed,
    }
    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))


def qualify_evaluation(args: argparse.Namespace) -> None:
    source = Path(args.input)
    payload = json.loads(source.read_text(encoding="utf-8"))
    primary = payload["candidates"]["0.08"]
    base, stress = primary["base"], primary["stress"]
    passive = payload["benchmarks"]["unscaled_half_long"]["base"]
    checks = {
        "base_total_positive": base["total_return"] > 0,
        "stress_total_positive": stress["total_return"] > 0,
        "stress_after_4pct_hurdle_positive": _hurdle(stress) > 0,
        "both_years_positive": all(
            base["annual_returns"].get(year, -1.0) > 0 for year in ("2023", "2024")
        ),
        "base_sharpe_at_least_0p75": base["sharpe"] >= 0.75,
        "drawdown_above_minus_14pct": base["max_drawdown"] > -0.14,
        "drawdown_shallower_than_unscaled": base["max_drawdown"]
        > passive["max_drawdown"],
        "six_and_ten_pct_neighbors_positive": all(
            payload["candidates"][key]["base"]["total_return"] > 0
            for key in ("0.06", "0.10")
        ),
        "turnover_at_most_4": base["turnover"] <= 4.0,
    }
    failed = [name for name, passed in checks.items() if not passed]
    result = {
        "schema_version": 1,
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "phase": "evaluation_gate",
        "source_sha256": _sha256(source),
        "checks": checks,
        "failed_checks": failed,
        "stress_return_after_4pct_annual_hurdle": _hurdle(stress),
        "confirmation_authorized": not failed,
    }
    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))


def qualify_confirmation(args: argparse.Namespace) -> None:
    evaluation = json.loads(Path(args.evaluation).read_text(encoding="utf-8"))
    confirmation = json.loads(Path(args.confirmation).read_text(encoding="utf-8"))
    primary = confirmation["candidates"]["0.08"]
    base, stress = primary["base"], primary["stress"]
    passive = confirmation["benchmarks"]["unscaled_half_long"]["base"]
    combined: dict[str, float] = {}
    for scenario in ("base", "stress"):
        prior = evaluation["candidates"]["0.08"][scenario]
        current = confirmation["candidates"]["0.08"][scenario]
        growth = (1.0 + prior["total_return"]) * (1.0 + current["total_return"])
        days = prior["days"] + current["days"]
        combined[scenario] = growth ** (365.25 / days) - 1.0
    checks = {
        "base_total_positive": base["total_return"] > 0,
        "stress_total_positive": stress["total_return"] > 0,
        "stress_after_4pct_hurdle_positive": _hurdle(stress) > 0,
        "both_calendar_segments_positive": all(
            base["annual_returns"].get(year, -1.0) > 0 for year in ("2025", "2026")
        ),
        "base_sharpe_at_least_0p50": base["sharpe"] >= 0.50,
        "drawdown_above_minus_10pct": base["max_drawdown"] > -0.10,
        "drawdown_shallower_than_unscaled": base["max_drawdown"]
        > passive["max_drawdown"],
        "six_and_ten_pct_neighbors_nonnegative": all(
            confirmation["candidates"][key]["base"]["total_return"] >= 0
            for key in ("0.06", "0.10")
        ),
        "active_days_at_least_530": base["active_days"] >= 530,
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
        "combined_evaluation_confirmation_cagr": combined,
        "checks": checks,
        "failed_checks": failed,
        "research_supports_demo_candidate": not failed,
        "conclusion": "SUPPORTS_WITHIN_SCOPE" if not failed else "DOES_NOT_SUPPORT",
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
