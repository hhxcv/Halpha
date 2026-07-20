from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


BASE_PATH = Path(__file__).resolve().parent.parent / "mature-alt-spot-top2-momentum" / "study.py"
SPEC = importlib.util.spec_from_file_location("spot_base", BASE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load retained public spot-data study")
base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)

SYMBOL = "PAXGUSDT"
SYMBOLS = (SYMBOL,)
LOOKBACKS = (90, 180, 270)
PRIMARY = 180
MAXIMUM_GROSS = 0.50
COSTS = {"favorable": 0.0010, "base": 0.0030, "stress": 0.0060}
CAPITAL_HURDLE_ANNUAL = 0.04
FIXED_RULE = "PAXGUSDT_POSITIVE_180D_MONTHLY_0P5X"
base.SYMBOLS = SYMBOLS
base.LOOKBACKS = LOOKBACKS
base.PRIMARY_LOOKBACK = PRIMARY


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def positive_trend_target(frames, decision_ms: int, lookback: int) -> dict[str, float]:
    earlier_ms = decision_ms - lookback * base.DAY_MS
    frame = frames[SYMBOL]
    if decision_ms not in frame.index or earlier_ms not in frame.index:
        return {SYMBOL: 0.0}
    positive = float(frame.at[decision_ms, "close"]) > float(frame.at[earlier_ms, "close"])
    return {SYMBOL: MAXIMUM_GROSS if positive else 0.0}


def passive_half_target(frames, decision_ms: int, lookback: int) -> dict[str, float]:
    return {SYMBOL: MAXIMUM_GROSS}


def run_with_target(frames, start_ms: int, end_ms: int, lookback: int, cost: float, seed: int, target):
    original = base.target_weights
    base.target_weights = target
    try:
        return base.simulate_strategy(frames, start_ms, end_ms, lookback, cost, seed)
    finally:
        base.target_weights = original


def phase_result(frames, phase: str) -> dict:
    start_ms, end_ms = (base.to_ms(value) for value in base.PHASES[phase])
    strategy = {
        str(lookback): {
            name: run_with_target(frames, start_ms, end_ms, lookback, cost, 20260720 + li * 10 + ci, positive_trend_target)
            for ci, (name, cost) in enumerate(COSTS.items())
        }
        for li, lookback in enumerate(LOOKBACKS)
    }
    benchmark = {
        name: run_with_target(frames, start_ms, end_ms, PRIMARY, cost, 20261720 + ci, passive_half_target)
        for ci, (name, cost) in enumerate(COSTS.items())
    }
    return {
        "phase": phase,
        "period": {"start": base.PHASES[phase][0], "end_exclusive": base.PHASES[phase][1]},
        "data_quality": base.data_quality(frames, start_ms, end_ms),
        "strategy": strategy,
        "passive_half_long": benchmark,
    }


def hurdle_adjusted(total_return: float, days: int) -> float:
    return (1.0 + total_return) / ((1.0 + CAPITAL_HURDLE_ANNUAL) ** (days / 365.0)) - 1.0


def command_fetch(args: argparse.Namespace) -> None:
    base.command_fetch(args)


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
        "rules": {
            "symbol": SYMBOL,
            "lookbacks": list(LOOKBACKS),
            "primary_lookback": PRIMARY,
            "signal": "own lookback return strictly positive",
            "maximum_gross": MAXIMUM_GROSS,
            "rebalance": "first UTC daily open monthly using information through prior UTC close",
            "costs_per_unit_turnover": COSTS,
            "capital_hurdle_annual": CAPITAL_HURDLE_ANNUAL,
        },
    })
    output["content_digest"] = base.canonical_digest(
        {key: value for key, value in output.items() if key != "generated_at"}
    )
    base.write_json(Path(args.output), output)
    main = output["strategy"][str(PRIMARY)]["base"]
    print(json.dumps({"phase": args.phase, "base_total": main["total_return"], "max_drawdown": main["max_drawdown"]}))


def components(result: dict) -> tuple[dict, dict, dict]:
    fixed = result["strategy"][str(PRIMARY)]
    return fixed, fixed["base"], result["passive_half_long"]["base"]


def write_gate(path: Path, payload: dict) -> None:
    payload["content_digest"] = base.canonical_digest(
        {key: value for key, value in payload.items() if key != "generated_at"}
    )
    base.write_json(path, payload)


def command_qualify_development(args: argparse.Namespace) -> None:
    result = base.read_json(Path(args.development))
    fixed, main, passive = components(result)
    passed = (
        result["data_quality"]["status"] == "PASS"
        and main["total_return"] > 0
        and fixed["stress"]["total_return"] > 0
        and main["max_drawdown"] > -0.12
        and main["max_drawdown"] > passive["max_drawdown"]
        and result["strategy"]["90"]["base"]["total_return"] >= 0
        and result["strategy"]["270"]["base"]["total_return"] >= 0
        and main["turnover"] <= 6
    )
    payload = {
        "generated_at": base.utc_now(),
        "development_content_digest": result["content_digest"],
        "qualification_status": "PASSED_DEVELOPMENT_GATE" if passed else "FAILED_DEVELOPMENT_GATE_STOP",
        "holdout_authorized": passed,
        "fixed_rule": FIXED_RULE,
    }
    write_gate(Path(args.output), payload)
    print(json.dumps({"status": payload["qualification_status"]}))


def command_qualify_evaluation(args: argparse.Namespace) -> None:
    result = base.read_json(Path(args.evaluation))
    fixed, main, passive = components(result)
    positive_years = sum(item["return"] > 0 for item in main["by_year"].values())
    stress_after_hurdle = hurdle_adjusted(fixed["stress"]["total_return"], fixed["stress"]["days"])
    passed = (
        result["data_quality"]["status"] == "PASS"
        and main["total_return"] > 0
        and fixed["stress"]["total_return"] > 0
        and stress_after_hurdle > 0
        and positive_years == len(main["by_year"])
        and main["max_drawdown"] > -0.10
        and main["max_drawdown"] > passive["max_drawdown"]
        and result["strategy"]["90"]["base"]["total_return"] > 0
        and result["strategy"]["270"]["base"]["total_return"] > 0
    )
    payload = {
        "generated_at": base.utc_now(),
        "evaluation_content_digest": result["content_digest"],
        "qualification_status": "PASSED_EVALUATION_GATE" if passed else "FAILED_EVALUATION_GATE_STOP",
        "holdout_authorized": passed,
        "fixed_rule": FIXED_RULE,
        "positive_years": positive_years,
        "stress_return_after_4pct_annual_hurdle": stress_after_hurdle,
    }
    write_gate(Path(args.output), payload)
    print(json.dumps({"status": payload["qualification_status"]}))


def command_combine(args: argparse.Namespace) -> None:
    development = base.read_json(Path(args.development))
    evaluation = base.read_json(Path(args.evaluation))
    evaluation_gate = base.read_json(Path(args.evaluation_gate))
    confirmation = base.read_json(Path(args.confirmation))
    fixed, main, passive = components(confirmation)
    evaluation_return = evaluation["strategy"][str(PRIMARY)]["base"]["total_return"]
    combined = (1.0 + evaluation_return) * (1.0 + main["total_return"]) - 1.0
    positive_years = sum(item["return"] > 0 for item in main["by_year"].values())
    stress_after_hurdle = hurdle_adjusted(fixed["stress"]["total_return"], fixed["stress"]["days"])
    support = (
        confirmation["data_quality"]["status"] == "PASS"
        and main["total_return"] > 0
        and fixed["stress"]["total_return"] > 0
        and stress_after_hurdle > 0
        and positive_years == len(main["by_year"])
        and main["max_drawdown"] > -0.12
        and main["max_drawdown"] > passive["max_drawdown"]
        and confirmation["strategy"]["90"]["base"]["total_return"] >= 0
        and confirmation["strategy"]["270"]["base"]["total_return"] >= 0
        and combined > 0
    )
    conclusion = (
        "SUPPORTS_WITHIN_SCOPE"
        if evaluation_gate["holdout_authorized"] and support
        else ("DOES_NOT_SUPPORT" if main["total_return"] < 0 or combined < 0 else "INSUFFICIENT_EVIDENCE")
    )
    payload = {
        "generated_at": base.utc_now(),
        "conclusion": conclusion,
        "scope": "PAXGUSDT Binance spot; monthly positive 180d return long/cash; 0.5 maximum gross",
        "development": development["strategy"][str(PRIMARY)]["base"],
        "evaluation": evaluation["strategy"][str(PRIMARY)]["base"],
        "confirmation": main,
        "confirmation_passive_half_long": passive,
        "confirmation_stress_return_after_4pct_annual_hurdle": stress_after_hurdle,
        "evaluation_confirmation_compounded_return": combined,
        "confirmation_support_gate": support,
        "formal_product_strategy_comparison": "NOT_RUN_DIFFERENT_ASSET_AND_SPOT_CONTRACT",
        "product_effects": "NONE",
    }
    payload["content_digest"] = base.canonical_digest(
        {key: value for key, value in payload.items() if key != "generated_at"}
    )
    base.write_json(Path(args.output), payload)
    print(json.dumps({"conclusion": conclusion, "combined": combined}))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PAXGUSDT monthly spot time-series momentum")
    sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch")
    fetch.add_argument("--cache-dir", required=True)
    fetch.add_argument("--start-month", required=True)
    fetch.add_argument("--end-month", required=True)
    fetch.add_argument("--manifest", required=True)
    fetch.set_defaults(func=command_fetch)
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
