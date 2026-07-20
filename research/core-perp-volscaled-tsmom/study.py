from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import random
import statistics
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


SOURCE_PATH = Path(__file__).resolve().parent.parent / "avax-dot-near-perp-monthly-tsmom" / "study.py"
SPEC = importlib.util.spec_from_file_location("daily_perp_source", SOURCE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load retained daily public-data source")
source = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(source)

SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT")
source.SYMBOLS = SYMBOLS
DAY_MS = 86_400_000
HOUR_MS = 3_600_000
LOOKBACKS = (120, 180, 240)
PRIMARY_LOOKBACK = 180
VOL_LOOKBACK = 60
ASSET_RISK_BUDGET = 0.05
MAX_ASSET_WEIGHT = 1.0 / 6.0
MAX_GROSS = 0.5
COSTS = {"favorable": 0.0006, "base": 0.0016, "stress": 0.0030}
PHASES = {
    "development": ("2021-01-01T00:00:00Z", "2023-01-01T00:00:00Z"),
    "evaluation": ("2023-01-01T00:00:00Z", "2025-01-01T00:00:00Z"),
    "confirmation": ("2025-01-01T00:00:00Z", "2026-06-30T00:00:00Z"),
}
EXPECTED_SOURCE_SHA256 = "1204afe0284daab4c9763b93a56f4ba0fe637d9408c554cf57e4d36af2f6450f"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def to_ms(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_digest(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def command_fetch(args: argparse.Namespace) -> None:
    if sha256_path(SOURCE_PATH) != EXPECTED_SOURCE_SHA256:
        raise RuntimeError("retained fetch source identity changed")
    source.command_fetch(args)


def load_funding_by_interval(cache: Path, manifest: dict[str, object]):
    rates, counts = {}, {}
    for symbol in SYMBOLS:
        item = manifest["funding_snapshots"][symbol]
        path = cache / item["cache_relative_path"]
        if sha256_path(path) != item["sha256"]:
            raise RuntimeError(f"funding identity mismatch: {symbol}")
        day_rates: dict[int, float] = {}
        day_counts: dict[int, int] = {}
        for row in read_json(path):
            raw = int(row["fundingTime"])
            boundary = ((raw + HOUR_MS // 2) // HOUR_MS) * HOUR_MS
            if abs(raw - boundary) > 1000:
                raise RuntimeError(f"funding timestamp outside 1-second hourly tolerance: {raw}")
            interval_start = ((boundary - 1) // DAY_MS) * DAY_MS
            day_rates[interval_start] = day_rates.get(interval_start, 0.0) + float(row["fundingRate"])
            day_counts[interval_start] = day_counts.get(interval_start, 0) + 1
        rates[symbol] = day_rates
        counts[symbol] = day_counts
    return rates, counts


def load_inputs(cache: Path, manifest_path: Path):
    if sha256_path(SOURCE_PATH) != EXPECTED_SOURCE_SHA256:
        raise RuntimeError("retained source identity changed")
    manifest = read_json(manifest_path)
    if tuple(manifest.get("symbols", ())) != SYMBOLS or manifest.get("interval") != "1d":
        raise RuntimeError("manifest universe mismatch")
    frames, _, _ = source.load_inputs(cache, manifest)
    funding, counts = load_funding_by_interval(cache, manifest)
    return frames, funding, counts, manifest


def data_quality(frames, counts, start_ms: int, end_ms: int) -> dict[str, object]:
    required_start = start_ms - (max(LOOKBACKS) + VOL_LOOKBACK + 2) * DAY_MS
    price_grid = list(range(required_start, end_ms + DAY_MS, DAY_MS))
    phase_grid = list(range(start_ms, end_ms, DAY_MS))
    details = {}
    passed = True
    for symbol in SYMBOLS:
        missing_prices = sum(timestamp not in frames[symbol].index for timestamp in price_grid)
        missing_funding_days = sum(counts[symbol].get(timestamp, 0) == 0 for timestamp in phase_grid)
        selected = frames[symbol][frames[symbol].index.isin(price_grid)]
        invalid = int(((selected[["open", "high", "low", "close"]] <= 0).any(axis=1) | (selected["high"] < selected[["open", "close"]].max(axis=1)) | (selected["low"] > selected[["open", "close"]].min(axis=1))).sum())
        status = "PASS" if missing_prices == missing_funding_days == invalid == 0 else "FAIL"
        passed = passed and status == "PASS"
        details[symbol] = {
            "status": status, "missing_price_days": missing_prices, "missing_funding_days": missing_funding_days,
            "funding_events": sum(counts[symbol].get(timestamp, 0) for timestamp in phase_grid), "invalid_ohlc": invalid,
        }
    return {"status": "PASS" if passed else "FAIL", "symbols": details}


def signal_weights(frames, decision_ms: int, lookback: int) -> dict[str, float]:
    weights = {}
    for symbol in SYMBOLS:
        frame = frames[symbol]
        earlier = decision_ms - lookback * DAY_MS
        if decision_ms not in frame.index or earlier not in frame.index:
            raise RuntimeError("missing momentum boundary")
        momentum = float(frame.at[decision_ms, "close"] / frame.at[earlier, "close"] - 1.0)
        returns = []
        for offset in range(VOL_LOOKBACK):
            right = decision_ms - offset * DAY_MS
            left = right - DAY_MS
            returns.append(float(frame.at[right, "close"] / frame.at[left, "close"] - 1.0))
        vol = statistics.stdev(returns) * math.sqrt(365.0)
        size = min(MAX_ASSET_WEIGHT, ASSET_RISK_BUDGET / vol) if vol > 0 else 0.0
        weights[symbol] = size if momentum > 0 else (-size if momentum < 0 else 0.0)
    gross = sum(abs(value) for value in weights.values())
    if gross > MAX_GROSS + 1e-12:
        raise RuntimeError("gross limit exceeded")
    return weights


def block_bootstrap_mean(values: list[float], seed: int, block: int = 30, reps: int = 4000):
    rng = random.Random(seed); count = len(values); means = []
    for _ in range(reps):
        sample = []
        while len(sample) < count:
            start = rng.randrange(count)
            sample.extend(values[(start + offset) % count] for offset in range(block))
        means.append(statistics.fmean(sample[:count]))
    means.sort(); return [means[int(reps * 0.025)], means[int(reps * 0.975) - 1]]


def summarize(returns, dates, turnover, adverse, price_pnl, funding_pnl, cost_pnl, rebalances, seed):
    equity, peak, max_drawdown = 1.0, 1.0, 0.0
    by_year: dict[str, list[float]] = {}
    for timestamp, value in zip(dates, returns):
        equity *= 1.0 + value; peak = max(peak, equity); max_drawdown = min(max_drawdown, equity / peak - 1.0)
        by_year.setdefault(str(datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).year), []).append(value)
    total = equity - 1.0; std = statistics.stdev(returns)
    return {
        "days": len(returns), "total_return": total,
        "annualized_return": (1.0 + total) ** (365.0 / len(returns)) - 1.0 if total > -1 else None,
        "annualized_volatility": std * math.sqrt(365.0),
        "sharpe_zero_rf": statistics.fmean(returns) / std * math.sqrt(365.0) if std else None,
        "max_drawdown": max_drawdown, "turnover": turnover,
        "worst_daily_intrabar_adverse_on_then_nav": adverse,
        "price_pnl_on_initial_capital": price_pnl, "funding_pnl_on_initial_capital": funding_pnl, "cost_pnl_on_initial_capital": cost_pnl,
        "daily_mean_block_bootstrap_95pct": block_bootstrap_mean(returns, seed),
        "by_year": {year: {"days": len(items), "return": math.prod(1.0 + value for value in items) - 1.0} for year, items in sorted(by_year.items())},
        "rebalance_count": len(rebalances), "average_gross_at_rebalance": statistics.fmean(row["gross"] for row in rebalances),
        "rebalance_digest": canonical_digest(rebalances), "returns_digest": canonical_digest(list(zip(dates, returns))),
    }


def simulate(frames, funding, start_ms: int, end_ms: int, lookback: int, cost: float, seed: int, continuous_long: bool = False):
    dates = list(range(start_ms, end_ms, DAY_MS))
    nav = 1.0; quantities = {symbol: 0.0 for symbol in SYMBOLS}; last_month = None
    returns = []; total_turnover = 0.0; adverse = 0.0; price_total = funding_total = cost_total = 0.0; rebalances = []
    for day_ms in dates:
        next_ms = day_ms + DAY_MS; nav_before = nav
        month = datetime.fromtimestamp(day_ms / 1000, tz=timezone.utc).strftime("%Y-%m")
        if month != last_month:
            if continuous_long:
                target = {symbol: MAX_ASSET_WEIGHT for symbol in SYMBOLS}
            else:
                target = signal_weights(frames, day_ms - DAY_MS, lookback)
            current = {symbol: quantities[symbol] * float(frames[symbol].at[day_ms, "open"]) / nav for symbol in SYMBOLS}
            turnover = sum(abs(target[symbol] - current[symbol]) for symbol in SYMBOLS)
            cost_amount = nav * turnover * cost; nav -= cost_amount; cost_total -= cost_amount; total_turnover += turnover
            for symbol in SYMBOLS:
                quantities[symbol] = nav * target[symbol] / float(frames[symbol].at[day_ms, "open"])
            rebalances.append({"day_ms": day_ms, "weights": target, "gross": sum(abs(value) for value in target.values()), "turnover": turnover})
            last_month = month
        interval_price = interval_funding = 0.0; worst = 0.0
        for symbol in SYMBOLS:
            row = frames[symbol].loc[day_ms]; qty = quantities[symbol]
            interval_price += qty * (float(frames[symbol].at[next_ms, "open"]) - float(row["open"]))
            interval_funding -= qty * float(frames[symbol].at[next_ms, "open"]) * funding[symbol].get(day_ms, 0.0)
            adverse_price = float(row["low"] if qty >= 0 else row["high"])
            worst += qty * (adverse_price - float(row["open"]))
        adverse = min(adverse, worst / nav)
        nav += interval_price + interval_funding; price_total += interval_price; funding_total += interval_funding
        if nav <= 0:
            raise RuntimeError("portfolio equity depleted")
        returns.append(nav / nav_before - 1.0)
    final_weights = {symbol: quantities[symbol] * float(frames[symbol].at[end_ms, "open"]) / nav for symbol in SYMBOLS}
    exit_turnover = sum(abs(value) for value in final_weights.values()); exit_cost = nav * exit_turnover * cost
    total_turnover += exit_turnover; cost_total -= exit_cost; returns[-1] = (1.0 + returns[-1]) * ((nav - exit_cost) / nav) - 1.0
    return summarize(returns, dates, total_turnover, adverse, price_total, funding_total, cost_total, rebalances, seed)


def command_analyze(args: argparse.Namespace) -> None:
    if args.phase != "development" and (not args.authorization or not read_json(Path(args.authorization)).get("holdout_authorized")):
        raise RuntimeError("holdout is not authorized")
    frames, funding, counts, manifest = load_inputs(Path(args.cache_dir).resolve(), Path(args.manifest))
    start_ms, end_ms = (to_ms(value) for value in PHASES[args.phase])
    strategies = {str(lookback): {name: simulate(frames, funding, start_ms, end_ms, lookback, cost, 20260720 + li * 10 + ci) for ci, (name, cost) in enumerate(COSTS.items())} for li, lookback in enumerate(LOOKBACKS)}
    benchmark = {name: simulate(frames, funding, start_ms, end_ms, PRIMARY_LOOKBACK, cost, 20261720 + ci, continuous_long=True) for ci, (name, cost) in enumerate(COSTS.items())}
    output = {
        "schema_version": 1, "generated_at": utc_now(), "phase": args.phase,
        "period": {"start": PHASES[args.phase][0], "end_exclusive": PHASES[args.phase][1]}, "symbols": list(SYMBOLS),
        "data_quality": data_quality(frames, counts, start_ms, end_ms), "strategy": strategies, "continuous_half_long_benchmark": benchmark,
        "rules": {"primary_lookback_days": PRIMARY_LOOKBACK, "robustness_lookbacks_days": [120, 240], "volatility_lookback_days": VOL_LOOKBACK, "asset_annual_risk_budget": ASSET_RISK_BUDGET, "max_asset_weight": MAX_ASSET_WEIGHT, "max_gross": MAX_GROSS, "costs": COSTS, "funding_assignment": "actual events in (daily open, next daily open]"},
        "manifest_sha256": sha256_path(Path(args.manifest)), "manifest_content_identity": manifest["content_identity"], "study_code_sha256": sha256_path(Path(__file__)), "source_code_sha256": sha256_path(SOURCE_PATH),
    }
    output["content_digest"] = canonical_digest({key: value for key, value in output.items() if key != "generated_at"}); write_json(Path(args.output), output)
    main = output["strategy"][str(PRIMARY_LOOKBACK)]["base"]; print(json.dumps({"phase": args.phase, "base": main["total_return"], "max_drawdown": main["max_drawdown"]}))


def gate_passed(result, phase: str):
    primary = result["strategy"][str(PRIMARY_LOOKBACK)]; main = primary["base"]; benchmark = result["continuous_half_long_benchmark"]["base"]
    diagnostics = [result["strategy"][str(window)]["base"]["total_return"] for window in LOOKBACKS]
    expected = {"2021", "2022"} if phase == "development" else {"2023", "2024"}
    return result["data_quality"]["status"] == "PASS" and main["total_return"] > 0 and primary["stress"]["total_return"] > 0 and set(main["by_year"]) == expected and all(item["return"] > 0 for item in main["by_year"].values()) and main["max_drawdown"] > (-0.20 if phase == "development" else -0.18) and main["max_drawdown"] >= benchmark["max_drawdown"] - 0.02 and main["worst_daily_intraday_adverse_on_then_nav"] > -0.15 and sum(value > 0 for value in diagnostics) >= 2 and main["turnover"] <= 30


def command_qualify(args, phase: str):
    result = read_json(Path(args.input)); passed = gate_passed(result, phase)
    output = {"generated_at": utc_now(), "phase": phase, "input_content_digest": result["content_digest"], "qualification_status": f"PASSED_{phase.upper()}_GATE" if passed else f"FAILED_{phase.upper()}_GATE_STOP", "holdout_authorized": passed, "fixed_rule": "BTC_ETH_BNB_MONTHLY_180D_TSMOM_60D_VOLSCALED_MAX_0P5X"}
    output["content_digest"] = canonical_digest({key: value for key, value in output.items() if key != "generated_at"}); write_json(Path(args.output), output); print(json.dumps({"status": output["qualification_status"]}))


def command_combine(args):
    development = read_json(Path(args.development)); evaluation = read_json(Path(args.evaluation)); confirmation = read_json(Path(args.confirmation)); gate = read_json(Path(args.evaluation_gate))
    primary = confirmation["strategy"][str(PRIMARY_LOOKBACK)]; main = primary["base"]; benchmark = confirmation["continuous_half_long_benchmark"]["base"]
    diagnostics = [confirmation["strategy"][str(window)]["base"]["total_return"] for window in LOOKBACKS]
    combined = (1.0 + evaluation["strategy"][str(PRIMARY_LOOKBACK)]["base"]["total_return"]) * (1.0 + main["total_return"]) - 1.0
    support = gate["holdout_authorized"] and confirmation["data_quality"]["status"] == "PASS" and main["total_return"] > 0 and primary["stress"]["total_return"] > 0 and set(main["by_year"]) == {"2025", "2026"} and all(item["return"] > 0 for item in main["by_year"].values()) and main["max_drawdown"] > -0.18 and main["max_drawdown"] >= benchmark["max_drawdown"] - 0.02 and main["worst_daily_intraday_adverse_on_then_nav"] > -0.15 and sum(value >= 0 for value in diagnostics) >= 2 and combined > 0
    conclusion = "SUPPORTS_WITHIN_SCOPE" if support else ("DOES_NOT_SUPPORT" if main["total_return"] < 0 or combined < 0 else "INSUFFICIENT_EVIDENCE")
    output = {"generated_at": utc_now(), "conclusion": conclusion, "scope": "BTC/ETH/BNB monthly 180d time-series momentum with 60d volatility scaling, actual funding and max 0.5x gross through 2026-06-29", "development": development["strategy"][str(PRIMARY_LOOKBACK)]["base"], "evaluation": evaluation["strategy"][str(PRIMARY_LOOKBACK)]["base"], "confirmation": main, "confirmation_stress": primary["stress"], "confirmation_robustness_returns": {str(window): diagnostics[index] for index, window in enumerate(LOOKBACKS)}, "confirmation_half_long_benchmark": benchmark, "evaluation_confirmation_compounded_return": combined, "support_gate": support, "formal_product_strategy_comparison": "FIXED_BACKGROUND_ONLY_NO_IDENTICAL_ACTIVATION_REPLAY", "product_effects": "NONE"}
    output["content_digest"] = canonical_digest({key: value for key, value in output.items() if key != "generated_at"}); write_json(Path(args.output), output); print(json.dumps({"conclusion": conclusion, "confirmation": main["total_return"]}))


def build_parser():
    parser = argparse.ArgumentParser(description="Core-perpetual volatility-scaled TSMOM study"); sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch"); fetch.add_argument("--cache-dir", required=True); fetch.add_argument("--start-month", required=True); fetch.add_argument("--end-month", required=True); fetch.add_argument("--manifest", required=True); fetch.set_defaults(func=command_fetch)
    analyze = sub.add_parser("analyze"); analyze.add_argument("--cache-dir", required=True); analyze.add_argument("--manifest", required=True); analyze.add_argument("--phase", choices=tuple(PHASES), required=True); analyze.add_argument("--authorization"); analyze.add_argument("--output", required=True); analyze.set_defaults(func=command_analyze)
    for name, phase in (("qualify-development", "development"), ("qualify-evaluation", "evaluation")):
        qualify = sub.add_parser(name); qualify.add_argument("--input", required=True); qualify.add_argument("--output", required=True); qualify.set_defaults(func=lambda args, fixed_phase=phase: command_qualify(args, fixed_phase))
    combine = sub.add_parser("combine"); combine.add_argument("--development", required=True); combine.add_argument("--evaluation", required=True); combine.add_argument("--evaluation-gate", required=True); combine.add_argument("--confirmation", required=True); combine.add_argument("--output", required=True); combine.set_defaults(func=command_combine)
    return parser


def main():
    args = build_parser().parse_args(); args.func(args)


if __name__ == "__main__":
    main()
