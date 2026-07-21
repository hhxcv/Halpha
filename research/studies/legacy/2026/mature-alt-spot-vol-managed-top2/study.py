from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd


BASE_PATH = Path(__file__).resolve().parent.parent / "mature-alt-spot-top2-momentum" / "study.py"
SPEC = importlib.util.spec_from_file_location("mature_alt_base", BASE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load retained base study")
base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)

PRIMARY_KEY = "mom90_vol56_target20"
VARIANTS = {
    PRIMARY_KEY: (90, 56, 0.20),
    "mom60_vol56_target20": (60, 56, 0.20),
    "mom120_vol56_target20": (120, 56, 0.20),
    "mom90_vol28_target20": (90, 28, 0.20),
    "mom90_vol84_target20": (90, 84, 0.20),
    "mom90_vol56_target15": (90, 56, 0.15),
    "mom90_vol56_target25": (90, 56, 0.25),
}
ROBUSTNESS_KEYS = tuple(key for key in VARIANTS if key != PRIMARY_KEY)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def risk_managed_target(
    frames: dict[str, pd.DataFrame], decision_ms: int, momentum_days: int, volatility_days: int, target: float
) -> dict[str, float]:
    unit_weights = base.target_weights(frames, decision_ms, momentum_days)
    winners = [symbol for symbol, weight in unit_weights.items() if weight > 0]
    if not winners:
        return unit_weights
    start_ms = decision_ms - volatility_days * base.DAY_MS
    dates = list(range(start_ms, decision_ms + base.DAY_MS, base.DAY_MS))
    if any(any(day not in frames[symbol].index for day in dates) for symbol in winners):
        return {symbol: 0.0 for symbol in base.SYMBOLS}
    returns = []
    for index in range(1, len(dates)):
        daily = np.mean([
            float(frames[symbol].at[dates[index], "close"] / frames[symbol].at[dates[index - 1], "close"] - 1.0)
            for symbol in winners
        ])
        returns.append(daily)
    realized = float(np.std(returns, ddof=1) * np.sqrt(365.0))
    exposure = min(1.0, target / realized) if realized > 0 else 0.0
    return {symbol: weight * exposure for symbol, weight in unit_weights.items()}


def simulate(
    frames: dict[str, pd.DataFrame],
    start_ms: int,
    end_ms: int,
    momentum_days: int,
    volatility_days: int,
    target: float,
    cost: float,
    seed: int,
) -> dict[str, object]:
    dates = frames[base.SYMBOLS[0]].index[
        (frames[base.SYMBOLS[0]].index >= start_ms) & (frames[base.SYMBOLS[0]].index < end_ms)
    ]
    cash = 1.0
    quantities = {symbol: 0.0 for symbol in base.SYMBOLS}
    prior_close_nav = 1.0
    returns = []
    invested_flags = []
    exposures = []
    total_turnover = 0.0
    selection_counts = {symbol: 0 for symbol in base.SYMBOLS}
    last_month = None
    for day_ms in dates:
        nav_open = cash + sum(quantities[symbol] * float(frames[symbol].at[day_ms, "open"]) for symbol in base.SYMBOLS)
        month = pd.Timestamp(day_ms, unit="ms", tz="UTC").strftime("%Y-%m")
        if month != last_month:
            target_weights = risk_managed_target(
                frames, int(day_ms - base.DAY_MS), momentum_days, volatility_days, target
            )
            current = {
                symbol: quantities[symbol] * float(frames[symbol].at[day_ms, "open"]) / nav_open
                for symbol in base.SYMBOLS
            }
            turnover = sum(abs(target_weights[symbol] - current[symbol]) for symbol in base.SYMBOLS)
            total_turnover += turnover
            after_cost = nav_open * (1.0 - turnover * cost)
            cash = after_cost * (1.0 - sum(target_weights.values()))
            for symbol in base.SYMBOLS:
                quantities[symbol] = after_cost * target_weights[symbol] / float(frames[symbol].at[day_ms, "open"])
                if target_weights[symbol] > 0:
                    selection_counts[symbol] += 1
            last_month = month
        nav_close = cash + sum(quantities[symbol] * float(frames[symbol].at[day_ms, "close"]) for symbol in base.SYMBOLS)
        risky_value = sum(quantities[symbol] * float(frames[symbol].at[day_ms, "close"]) for symbol in base.SYMBOLS)
        exposure = risky_value / nav_close
        returns.append(nav_close / prior_close_nav - 1.0)
        invested_flags.append(1.0 if exposure > 0 else 0.0)
        exposures.append(exposure)
        prior_close_nav = nav_close
    final_exposure = exposures[-1]
    total_turnover += final_exposure
    after_exit = prior_close_nav * (1.0 - final_exposure * cost)
    returns[-1] = (1.0 + returns[-1]) * (after_exit / prior_close_nav) - 1.0
    series = pd.Series(returns, index=dates, dtype="float64")
    invested = pd.Series(invested_flags, index=dates, dtype="float64")
    result = base.performance(series, total_turnover, invested, seed)
    result.update({
        "mean_risky_exposure": float(np.mean(exposures)),
        "max_risky_exposure": float(np.max(exposures)),
        "selection_counts": selection_counts,
    })
    return result


def fixed_exposure_explanation(
    frames: dict[str, pd.DataFrame], start_ms: int, end_ms: int, exposure: float, cost: float, seed: int
) -> dict[str, object]:
    original = base.target_weights

    def scaled(items, decision_ms, lookback):
        return {symbol: weight * exposure for symbol, weight in original(items, decision_ms, lookback).items()}

    base.target_weights = scaled
    try:
        return base.simulate_strategy(frames, start_ms, end_ms, 90, cost, seed)
    finally:
        base.target_weights = original


def phase_result(frames: dict[str, pd.DataFrame], phase: str) -> dict[str, object]:
    start_ms, end_ms = (base.to_ms(value) for value in base.PHASES[phase])
    quality = base.data_quality(frames, start_ms, end_ms)
    variants = {}
    for variant_offset, (key, (momentum_days, volatility_days, target)) in enumerate(VARIANTS.items()):
        variants[key] = {
            name: simulate(
                frames,
                start_ms,
                end_ms,
                momentum_days,
                volatility_days,
                target,
                cost,
                20260720 + variant_offset * 10 + cost_offset,
            )
            for cost_offset, (name, cost) in enumerate(base.COSTS.items())
        }
    benchmark = {
        name: base.simulate_benchmark(frames, start_ms, end_ms, cost, 20261720 + offset)
        for offset, (name, cost) in enumerate(base.COSTS.items())
    }
    unmanaged = {
        name: base.simulate_strategy(frames, start_ms, end_ms, 90, cost, 20262720 + offset)
        for offset, (name, cost) in enumerate(base.COSTS.items())
    }
    fixed20 = {
        name: fixed_exposure_explanation(frames, start_ms, end_ms, 0.20, cost, 20263720 + offset)
        for offset, (name, cost) in enumerate(base.COSTS.items())
    }
    return {
        "phase": phase,
        "period": {"start": base.PHASES[phase][0], "end_exclusive": base.PHASES[phase][1]},
        "data_quality": quality,
        "variants": variants,
        "equal_weight_buy_and_hold": benchmark,
        "unmanaged_90d": unmanaged,
        "fixed_20pct_exposure_90d": fixed20,
    }


def command_analyze(args: argparse.Namespace) -> None:
    if args.phase != "development":
        if not args.authorization or not base.read_json(Path(args.authorization)).get("holdout_authorized"):
            raise RuntimeError("holdout is not authorized")
    manifest = base.read_json(Path(args.manifest))
    frames = base.load_inputs(Path(args.cache_dir).resolve(), manifest)
    output = phase_result(frames, args.phase)
    output.update({
        "schema_version": 1,
        "generated_at": base.utc_now(),
        "manifest_content_identity": manifest["content_identity"],
        "study_code_sha256": sha256_path(Path(__file__)),
        "base_study_code_sha256": sha256_path(BASE_PATH),
        "rules": {"primary": PRIMARY_KEY, "variants": VARIANTS, "costs": base.COSTS},
    })
    output["content_digest"] = base.canonical_digest({k: v for k, v in output.items() if k != "generated_at"})
    base.write_json(Path(args.output), output)
    primary = output["variants"][PRIMARY_KEY]["base"]
    print(json.dumps({"phase": args.phase, "base_total": primary["total_return"], "max_drawdown": primary["max_drawdown"]}))


def robustness_nonnegative(result: dict[str, object], strict: bool) -> int:
    values = [result["variants"][key]["base"]["total_return"] for key in ROBUSTNESS_KEYS]
    return sum(value > 0 if strict else value >= 0 for value in values)


def command_qualify_development(args: argparse.Namespace) -> None:
    result = base.read_json(Path(args.development))
    primary = result["variants"][PRIMARY_KEY]
    managed = primary["base"]
    unmanaged = result["unmanaged_90d"]["base"]
    passed = (
        result["data_quality"]["status"] == "PASS"
        and managed["total_return"] > 0
        and primary["stress"]["total_return"] > 0
        and managed["max_drawdown"] > -0.35
        and managed["max_drawdown"] >= unmanaged["max_drawdown"] + 0.30
        and robustness_nonnegative(result, strict=True) >= 4
        and managed["turnover"] <= 30
    )
    output = {
        "generated_at": base.utc_now(),
        "development_content_digest": result["content_digest"],
        "qualification_status": "PASSED_DEVELOPMENT_GATE" if passed else "FAILED_DEVELOPMENT_GATE_STOP",
        "holdout_authorized": passed,
        "robustness_positive_count": robustness_nonnegative(result, strict=True),
        "fixed_rule": "MATURE_ALT_SPOT_VOL_MANAGED_TOP2_90D_56D_20PCT",
    }
    output["content_digest"] = base.canonical_digest({k: v for k, v in output.items() if k != "generated_at"})
    base.write_json(Path(args.output), output)
    print(json.dumps({"status": output["qualification_status"]}))


def command_qualify_evaluation(args: argparse.Namespace) -> None:
    result = base.read_json(Path(args.evaluation))
    primary = result["variants"][PRIMARY_KEY]
    managed = primary["base"]
    benchmark = result["equal_weight_buy_and_hold"]["base"]
    positive_years = sum(item["return"] > 0 for item in managed["by_year"].values())
    passed = (
        result["data_quality"]["status"] == "PASS"
        and managed["total_return"] > 0
        and primary["stress"]["total_return"] > 0
        and positive_years >= 1
        and managed["max_drawdown"] > -0.35
        and managed["max_drawdown"] > benchmark["max_drawdown"]
        and robustness_nonnegative(result, strict=False) >= 4
    )
    output = {
        "generated_at": base.utc_now(),
        "evaluation_content_digest": result["content_digest"],
        "qualification_status": "PASSED_EVALUATION_GATE" if passed else "FAILED_EVALUATION_GATE_STOP",
        "holdout_authorized": passed,
        "robustness_nonnegative_count": robustness_nonnegative(result, strict=False),
        "fixed_rule": "MATURE_ALT_SPOT_VOL_MANAGED_TOP2_90D_56D_20PCT",
    }
    output["content_digest"] = base.canonical_digest({k: v for k, v in output.items() if k != "generated_at"})
    base.write_json(Path(args.output), output)
    print(json.dumps({"status": output["qualification_status"]}))


def command_combine(args: argparse.Namespace) -> None:
    development = base.read_json(Path(args.development))
    evaluation = base.read_json(Path(args.evaluation))
    evaluation_gate = base.read_json(Path(args.evaluation_gate))
    confirmation = base.read_json(Path(args.confirmation))
    primary = confirmation["variants"][PRIMARY_KEY]
    managed = primary["base"]
    benchmark = confirmation["equal_weight_buy_and_hold"]["base"]
    confirmation_support = (
        confirmation["data_quality"]["status"] == "PASS"
        and managed["total_return"] >= 0
        and primary["stress"]["total_return"] >= 0
        and managed["max_drawdown"] > -0.35
        and managed["max_drawdown"] > benchmark["max_drawdown"]
        and robustness_nonnegative(confirmation, strict=False) >= 4
    )
    evaluation_total = evaluation["variants"][PRIMARY_KEY]["base"]["total_return"]
    if evaluation_gate["holdout_authorized"] and confirmation_support:
        conclusion = "SUPPORTS_WITHIN_SCOPE"
    elif evaluation_total < 0 or managed["total_return"] < 0:
        conclusion = "DOES_NOT_SUPPORT"
    else:
        conclusion = "INSUFFICIENT_EVIDENCE"
    output = {
        "generated_at": base.utc_now(),
        "conclusion": conclusion,
        "scope": "fixed five-symbol spot top-2 momentum scaled by prior 56-day volatility to 20% annual target",
        "development": development["variants"][PRIMARY_KEY]["base"],
        "evaluation": evaluation["variants"][PRIMARY_KEY]["base"],
        "confirmation": managed,
        "confirmation_equal_weight_buy_and_hold": benchmark,
        "confirmation_support_gate": confirmation_support,
        "confirmation_robustness_nonnegative_count": robustness_nonnegative(confirmation, strict=False),
        "formal_product_strategy_comparison": "NOT_RUN_NO_COMPARABLE_INSTRUMENT_OR_ACTIVATION_REPLAY",
        "product_effects": "NONE",
    }
    output["content_digest"] = base.canonical_digest({k: v for k, v in output.items() if k != "generated_at"})
    base.write_json(Path(args.output), output)
    print(json.dumps({"conclusion": conclusion}))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Volatility-managed mature-alt spot momentum study")
    sub = parser.add_subparsers(dest="command", required=True)
    analyze = sub.add_parser("analyze")
    analyze.add_argument("--cache-dir", required=True)
    analyze.add_argument("--manifest", required=True)
    analyze.add_argument("--phase", choices=tuple(base.PHASES), required=True)
    analyze.add_argument("--authorization")
    analyze.add_argument("--output", required=True)
    analyze.set_defaults(func=command_analyze)
    dev = sub.add_parser("qualify-development")
    dev.add_argument("--development", required=True)
    dev.add_argument("--output", required=True)
    dev.set_defaults(func=command_qualify_development)
    eva = sub.add_parser("qualify-evaluation")
    eva.add_argument("--evaluation", required=True)
    eva.add_argument("--output", required=True)
    eva.set_defaults(func=command_qualify_evaluation)
    combine = sub.add_parser("combine")
    combine.add_argument("--development", required=True)
    combine.add_argument("--evaluation", required=True)
    combine.add_argument("--evaluation-gate", required=True)
    combine.add_argument("--confirmation", required=True)
    combine.add_argument("--output", required=True)
    combine.set_defaults(func=command_combine)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
