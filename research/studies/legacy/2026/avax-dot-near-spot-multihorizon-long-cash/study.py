from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


BASE_PATH = Path(__file__).resolve().parent.parent / "avax-dot-near-spot-long-cash" / "study.py"
SPEC = importlib.util.spec_from_file_location("single_window", BASE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load retained single-window study")
single = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(single)
base = single.base
WINDOWS = (60, 90, 120)
VOTE_WEIGHT = 1.0 / 18.0


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensemble_target(frames, decision_ms: int, ignored: int):
    weights = {}
    for symbol in single.SYMBOLS:
        positive = 0
        for window in WINDOWS:
            earlier = decision_ms - window * base.DAY_MS
            if decision_ms in frames[symbol].index and earlier in frames[symbol].index:
                positive += frames[symbol].at[decision_ms, "close"] / frames[symbol].at[earlier, "close"] - 1.0 > 0
        weights[symbol] = positive * VOTE_WEIGHT
    return weights


def phase_result(frames, phase: str):
    start_ms, end_ms = (base.to_ms(value) for value in base.PHASES[phase])
    ensemble = {
        name: single.run_with_target(frames, start_ms, end_ms, 90, cost, 20260720 + ci, ensemble_target)
        for ci, (name, cost) in enumerate(base.COSTS.items())
    }
    benchmark = {
        name: single.run_with_target(frames, start_ms, end_ms, 90, cost, 20261720 + ci, single.constant_half_long)
        for ci, (name, cost) in enumerate(base.COSTS.items())
    }
    diagnostics = {
        str(window): single.run_with_target(frames, start_ms, end_ms, window, base.COSTS["base"], 20262720 + i, single.long_cash_target)
        for i, window in enumerate(WINDOWS)
    }
    return {"phase": phase, "period": {"start": base.PHASES[phase][0], "end_exclusive": base.PHASES[phase][1]}, "data_quality": base.data_quality(frames, start_ms, end_ms), "ensemble": ensemble, "monthly_rebalanced_half_long": benchmark, "single_window_diagnostics_base": diagnostics}


def command_fetch(args):
    single.command_fetch(args)


def command_analyze(args):
    if args.phase != "development" and (not args.authorization or not base.read_json(Path(args.authorization)).get("holdout_authorized")):
        raise RuntimeError("holdout is not authorized")
    manifest = base.read_json(Path(args.manifest)); frames = base.load_inputs(Path(args.cache_dir).resolve(), manifest); output = phase_result(frames, args.phase)
    output.update({"schema_version": 1, "generated_at": base.utc_now(), "manifest_content_identity": manifest["content_identity"], "study_code_sha256": sha256_path(Path(__file__)), "single_window_study_code_sha256": sha256_path(BASE_PATH), "rules": {"windows": list(WINDOWS), "weight_per_positive_vote": VOTE_WEIGHT, "costs": base.COSTS}})
    output["content_digest"] = base.canonical_digest({key: value for key, value in output.items() if key != "generated_at"}); base.write_json(Path(args.output), output)
    main = output["ensemble"]["base"]; print(json.dumps({"phase": args.phase, "base_total": main["total_return"], "max_drawdown": main["max_drawdown"]}))


def command_qualify_development(args):
    result = base.read_json(Path(args.development)); main = result["ensemble"]["base"]; benchmark = result["monthly_rebalanced_half_long"]["base"]
    passed = result["data_quality"]["status"] == "PASS" and main["total_return"] > 0 and result["ensemble"]["stress"]["total_return"] > 0 and main["max_drawdown"] > -0.40 and main["max_drawdown"] >= benchmark["max_drawdown"] + 0.15 and main["turnover"] <= 20
    output = {"generated_at": base.utc_now(), "development_content_digest": result["content_digest"], "qualification_status": "PASSED_DEVELOPMENT_GATE" if passed else "FAILED_DEVELOPMENT_GATE_STOP", "holdout_authorized": passed, "fixed_rule": "AVAX_DOT_NEAR_SPOT_60_90_120_EQUAL_VOTE_LONG_CASH"}
    output["content_digest"] = base.canonical_digest({key: value for key, value in output.items() if key != "generated_at"}); base.write_json(Path(args.output), output); print(json.dumps({"status": output["qualification_status"]}))


def command_qualify_evaluation(args):
    result = base.read_json(Path(args.evaluation)); main = result["ensemble"]["base"]; benchmark = result["monthly_rebalanced_half_long"]["base"]
    positive_years = sum(item["return"] > 0 for item in main["by_year"].values())
    passed = result["data_quality"]["status"] == "PASS" and main["total_return"] > 0 and result["ensemble"]["stress"]["total_return"] > 0 and positive_years >= 1 and main["max_drawdown"] > -0.40 and main["max_drawdown"] > benchmark["max_drawdown"]
    output = {"generated_at": base.utc_now(), "evaluation_content_digest": result["content_digest"], "qualification_status": "PASSED_EVALUATION_GATE" if passed else "FAILED_EVALUATION_GATE_STOP", "holdout_authorized": passed, "fixed_rule": "AVAX_DOT_NEAR_SPOT_60_90_120_EQUAL_VOTE_LONG_CASH"}
    output["content_digest"] = base.canonical_digest({key: value for key, value in output.items() if key != "generated_at"}); base.write_json(Path(args.output), output); print(json.dumps({"status": output["qualification_status"]}))


def command_combine(args):
    development = base.read_json(Path(args.development)); evaluation = base.read_json(Path(args.evaluation)); gate = base.read_json(Path(args.evaluation_gate)); confirmation = base.read_json(Path(args.confirmation)); main = confirmation["ensemble"]["base"]; benchmark = confirmation["monthly_rebalanced_half_long"]["base"]
    evaluation_return = evaluation["ensemble"]["base"]["total_return"]; combined = (1 + evaluation_return) * (1 + main["total_return"]) - 1
    support = confirmation["data_quality"]["status"] == "PASS" and main["total_return"] >= -0.10 and confirmation["ensemble"]["stress"]["total_return"] >= -0.10 and main["max_drawdown"] > -0.25 and main["max_drawdown"] > benchmark["max_drawdown"] and combined > 0
    conclusion = "SUPPORTS_WITHIN_SCOPE" if gate["holdout_authorized"] and support else ("DOES_NOT_SUPPORT" if main["total_return"] < -0.10 or combined < 0 else "INSUFFICIENT_EVIDENCE")
    output = {"generated_at": base.utc_now(), "conclusion": conclusion, "scope": "AVAX/DOT/NEAR spot monthly equal-vote 60/90/120-day positive-momentum ensemble, maximum 0.5x", "development": development["ensemble"]["base"], "evaluation": evaluation["ensemble"]["base"], "confirmation": main, "confirmation_half_long": benchmark, "evaluation_confirmation_compounded_return": combined, "confirmation_support_gate": support, "formal_product_strategy_comparison": "NOT_RUN_NO_COMPARABLE_INSTRUMENT_OR_ACTIVATION_REPLAY", "product_effects": "NONE"}
    output["content_digest"] = base.canonical_digest({key: value for key, value in output.items() if key != "generated_at"}); base.write_json(Path(args.output), output); print(json.dumps({"conclusion": conclusion, "combined": combined}))


def build_parser():
    parser = argparse.ArgumentParser(description="AVAX/DOT/NEAR multi-horizon spot long/cash ensemble"); sub = parser.add_subparsers(dest="command", required=True)
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
