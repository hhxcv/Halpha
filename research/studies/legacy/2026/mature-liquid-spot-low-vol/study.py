from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path


BASE_PATH = Path(__file__).resolve().parent.parent / "mature-alt-spot-top2-momentum" / "study.py"
SPEC = importlib.util.spec_from_file_location("spot_base", BASE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load retained spot study")
base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)

SYMBOLS = (
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "LTCUSDT", "LINKUSDT",
    "DOGEUSDT", "BCHUSDT", "TRXUSDT", "XLMUSDT", "ETCUSDT", "ATOMUSDT",
)
LOOKBACKS = (60, 90, 180)
PRIMARY = 90
HOLDINGS = 3
GROSS = 0.5
WEIGHT = GROSS / HOLDINGS
base.SYMBOLS = SYMBOLS
base.LOOKBACKS = LOOKBACKS
base.PRIMARY_LOOKBACK = PRIMARY


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def low_vol_target(frames, decision_ms: int, lookback: int):
    earlier = decision_ms - lookback * base.DAY_MS
    volatility = {}
    for symbol in SYMBOLS:
        frame = frames[symbol]
        closes = frame.loc[(frame.index >= earlier) & (frame.index <= decision_ms), "close"]
        if len(closes) != lookback + 1:
            return {item: 0.0 for item in SYMBOLS}
        log_returns = closes.astype(float).map(math.log).diff().dropna()
        volatility[symbol] = float(log_returns.std(ddof=1))
    selected = sorted(volatility, key=lambda item: (volatility[item], item))[:HOLDINGS]
    return {symbol: WEIGHT if symbol in selected else 0.0 for symbol in SYMBOLS}


def constant_half_long(frames, decision_ms: int, lookback: int):
    return {symbol: GROSS / len(SYMBOLS) for symbol in SYMBOLS}


def run_with_target(frames, start_ms: int, end_ms: int, lookback: int, cost: float, seed: int, target_function):
    original = base.target_weights
    base.target_weights = target_function
    try:
        return base.simulate_strategy(frames, start_ms, end_ms, lookback, cost, seed)
    finally:
        base.target_weights = original


def phase_result(frames, phase: str):
    start_ms, end_ms = (base.to_ms(value) for value in base.PHASES[phase])
    strategy = {
        str(lookback): {
            name: run_with_target(frames, start_ms, end_ms, lookback, cost, 20260720 + li * 10 + ci, low_vol_target)
            for ci, (name, cost) in enumerate(base.COSTS.items())
        }
        for li, lookback in enumerate(LOOKBACKS)
    }
    benchmark = {
        name: run_with_target(frames, start_ms, end_ms, PRIMARY, cost, 20261720 + ci, constant_half_long)
        for ci, (name, cost) in enumerate(base.COSTS.items())
    }
    return {
        "phase": phase,
        "period": {"start": base.PHASES[phase][0], "end_exclusive": base.PHASES[phase][1]},
        "data_quality": base.data_quality(frames, start_ms, end_ms),
        "strategy": strategy,
        "monthly_rebalanced_half_long": benchmark,
    }


def command_fetch(args):
    base.command_fetch(args)


def command_analyze(args):
    if args.phase != "development" and (not args.authorization or not base.read_json(Path(args.authorization)).get("holdout_authorized")):
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
        "rules": {"symbols": list(SYMBOLS), "lookbacks": list(LOOKBACKS), "holdings": HOLDINGS, "maximum_gross": GROSS, "costs": base.COSTS},
    })
    output["content_digest"] = base.canonical_digest({key: value for key, value in output.items() if key != "generated_at"})
    base.write_json(Path(args.output), output)
    main = output["strategy"][str(PRIMARY)]["base"]
    print(json.dumps({"phase": args.phase, "base_total": main["total_return"], "max_drawdown": main["max_drawdown"]}))


def support_components(result):
    fixed = result["strategy"][str(PRIMARY)]
    main = fixed["base"]
    benchmark = result["monthly_rebalanced_half_long"]["base"]
    return fixed, main, benchmark


def command_qualify_development(args):
    result = base.read_json(Path(args.development)); fixed, main, benchmark = support_components(result)
    passed = result["data_quality"]["status"] == "PASS" and main["total_return"] > 0 and fixed["stress"]["total_return"] > 0 and main["max_drawdown"] > -0.35 and main["max_drawdown"] > benchmark["max_drawdown"] and result["strategy"]["60"]["base"]["total_return"] > 0 and result["strategy"]["180"]["base"]["total_return"] > 0 and main["turnover"] <= 30
    output = {"generated_at": base.utc_now(), "development_content_digest": result["content_digest"], "qualification_status": "PASSED_DEVELOPMENT_GATE" if passed else "FAILED_DEVELOPMENT_GATE_STOP", "holdout_authorized": passed, "fixed_rule": "MATURE_LIQUID_SPOT_BOTTOM3_REALIZED_VOL_90D_0P5X"}
    output["content_digest"] = base.canonical_digest({key: value for key, value in output.items() if key != "generated_at"}); base.write_json(Path(args.output), output); print(json.dumps({"status": output["qualification_status"]}))


def command_qualify_evaluation(args):
    result = base.read_json(Path(args.evaluation)); fixed, main, benchmark = support_components(result)
    passed = result["data_quality"]["status"] == "PASS" and main["total_return"] > 0 and fixed["stress"]["total_return"] > 0 and sum(item["return"] > 0 for item in main["by_year"].values()) >= 1 and main["max_drawdown"] > -0.35 and main["max_drawdown"] > benchmark["max_drawdown"] and result["strategy"]["60"]["base"]["total_return"] > 0 and result["strategy"]["180"]["base"]["total_return"] > 0
    output = {"generated_at": base.utc_now(), "evaluation_content_digest": result["content_digest"], "qualification_status": "PASSED_EVALUATION_GATE" if passed else "FAILED_EVALUATION_GATE_STOP", "holdout_authorized": passed, "fixed_rule": "MATURE_LIQUID_SPOT_BOTTOM3_REALIZED_VOL_90D_0P5X"}
    output["content_digest"] = base.canonical_digest({key: value for key, value in output.items() if key != "generated_at"}); base.write_json(Path(args.output), output); print(json.dumps({"status": output["qualification_status"]}))


def command_combine(args):
    development = base.read_json(Path(args.development)); evaluation = base.read_json(Path(args.evaluation)); gate = base.read_json(Path(args.evaluation_gate)); confirmation = base.read_json(Path(args.confirmation)); fixed, main, benchmark = support_components(confirmation)
    evaluation_return = evaluation["strategy"][str(PRIMARY)]["base"]["total_return"]
    combined = (1.0 + evaluation_return) * (1.0 + main["total_return"]) - 1.0
    support = confirmation["data_quality"]["status"] == "PASS" and main["total_return"] > 0 and fixed["stress"]["total_return"] > 0 and main["max_drawdown"] > -0.30 and main["max_drawdown"] > benchmark["max_drawdown"] and confirmation["strategy"]["60"]["base"]["total_return"] >= 0 and confirmation["strategy"]["180"]["base"]["total_return"] >= 0 and combined > 0
    conclusion = "SUPPORTS_WITHIN_SCOPE" if gate["holdout_authorized"] and support else ("DOES_NOT_SUPPORT" if main["total_return"] < 0 or combined < 0 else "INSUFFICIENT_EVIDENCE")
    output = {"generated_at": base.utc_now(), "conclusion": conclusion, "scope": "fixed 13-symbol Binance spot monthly bottom-3 realized-volatility portfolio at 0.5x", "development": development["strategy"][str(PRIMARY)]["base"], "evaluation": evaluation["strategy"][str(PRIMARY)]["base"], "confirmation": main, "confirmation_half_long": benchmark, "evaluation_confirmation_compounded_return": combined, "confirmation_support_gate": support, "formal_product_strategy_comparison": "NOT_RUN_NO_COMPARABLE_INSTRUMENT_OR_ACTIVATION_REPLAY", "product_effects": "NONE"}
    output["content_digest"] = base.canonical_digest({key: value for key, value in output.items() if key != "generated_at"}); base.write_json(Path(args.output), output); print(json.dumps({"conclusion": conclusion, "combined": combined}))


def build_parser():
    parser = argparse.ArgumentParser(description="Mature-liquid spot low-volatility study"); sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch"); fetch.add_argument("--cache-dir", required=True); fetch.add_argument("--start-month", required=True); fetch.add_argument("--end-month", required=True); fetch.add_argument("--manifest", required=True); fetch.set_defaults(func=command_fetch)
    analyze = sub.add_parser("analyze"); analyze.add_argument("--cache-dir", required=True); analyze.add_argument("--manifest", required=True); analyze.add_argument("--phase", choices=tuple(base.PHASES), required=True); analyze.add_argument("--authorization"); analyze.add_argument("--output", required=True); analyze.set_defaults(func=command_analyze)
    dev = sub.add_parser("qualify-development"); dev.add_argument("--development", required=True); dev.add_argument("--output", required=True); dev.set_defaults(func=command_qualify_development)
    eva = sub.add_parser("qualify-evaluation"); eva.add_argument("--evaluation", required=True); eva.add_argument("--output", required=True); eva.set_defaults(func=command_qualify_evaluation)
    combine = sub.add_parser("combine"); combine.add_argument("--development", required=True); combine.add_argument("--evaluation", required=True); combine.add_argument("--evaluation-gate", required=True); combine.add_argument("--confirmation", required=True); combine.add_argument("--output", required=True); combine.set_defaults(func=command_combine)
    return parser


def main():
    args = build_parser().parse_args(); args.func(args)


if __name__ == "__main__":
    main()
