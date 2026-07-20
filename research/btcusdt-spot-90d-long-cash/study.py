from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


PARENT_PATH = Path(__file__).resolve().parent.parent / "btc-eth-spot-dual-momentum" / "study.py"
SPEC = importlib.util.spec_from_file_location("dual_parent", PARENT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load retained dual-momentum study")
parent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(parent)
base = parent.base


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def constant_btc_half(frames, decision_ms: int, lookback: int):
    return {"BTCUSDT": parent.GROSS, "ETHUSDT": 0.0}


def phase_result(frames, phase: str):
    start_ms, end_ms = (base.to_ms(value) for value in base.PHASES[phase])
    strategy = {str(lookback): {name: parent.run_with_target(frames, start_ms, end_ms, lookback, cost, 20260720 + li * 10 + ci, parent.btc_only_target) for ci, (name, cost) in enumerate(base.COSTS.items())} for li, lookback in enumerate(parent.LOOKBACKS)}
    benchmark = {name: parent.run_with_target(frames, start_ms, end_ms, parent.PRIMARY, cost, 20261720 + ci, constant_btc_half) for ci, (name, cost) in enumerate(base.COSTS.items())}
    return {"phase": phase, "period": {"start": base.PHASES[phase][0], "end_exclusive": base.PHASES[phase][1]}, "data_quality": base.data_quality(frames, start_ms, end_ms), "strategy": strategy, "monthly_rebalanced_btc_half_long": benchmark}


def command_fetch(args):
    parent.command_fetch(args)


def command_analyze(args):
    if args.phase != "development" and (not args.authorization or not base.read_json(Path(args.authorization)).get("holdout_authorized")):
        raise RuntimeError("holdout is not authorized")
    manifest = base.read_json(Path(args.manifest)); frames = base.load_inputs(Path(args.cache_dir).resolve(), manifest); output = phase_result(frames, args.phase)
    output.update({"schema_version": 1, "generated_at": base.utc_now(), "manifest_content_identity": manifest["content_identity"], "study_code_sha256": sha256_path(Path(__file__)), "parent_study_code_sha256": sha256_path(PARENT_PATH), "rules": {"instrument": "BTCUSDT Binance Spot", "lookbacks": list(parent.LOOKBACKS), "primary_lookback": parent.PRIMARY, "maximum_gross": parent.GROSS, "costs": base.COSTS}})
    output["content_digest"] = base.canonical_digest({key: value for key, value in output.items() if key != "generated_at"}); base.write_json(Path(args.output), output); main = output["strategy"][str(parent.PRIMARY)]["base"]; print(json.dumps({"phase": args.phase, "base_total": main["total_return"], "max_drawdown": main["max_drawdown"]}))


def components(result):
    fixed = result["strategy"][str(parent.PRIMARY)]; return fixed, fixed["base"], result["monthly_rebalanced_btc_half_long"]["base"]


def command_qualify_development(args):
    result = base.read_json(Path(args.development)); fixed, main, benchmark = components(result)
    passed = result["data_quality"]["status"] == "PASS" and main["total_return"] > 0 and fixed["stress"]["total_return"] > 0 and main["max_drawdown"] > -0.30 and main["max_drawdown"] > benchmark["max_drawdown"] and result["strategy"]["60"]["base"]["total_return"] > 0 and result["strategy"]["180"]["base"]["total_return"] > 0 and main["turnover"] <= 20
    output = {"generated_at": base.utc_now(), "development_content_digest": result["content_digest"], "qualification_status": "PASSED_DEVELOPMENT_GATE" if passed else "FAILED_DEVELOPMENT_GATE_STOP", "holdout_authorized": passed, "fixed_rule": "BTCUSDT_SPOT_POSITIVE_90D_0P5X"}; output["content_digest"] = base.canonical_digest({key: value for key, value in output.items() if key != "generated_at"}); base.write_json(Path(args.output), output); print(json.dumps({"status": output["qualification_status"]}))


def command_qualify_evaluation(args):
    result = base.read_json(Path(args.evaluation)); fixed, main, benchmark = components(result)
    passed = result["data_quality"]["status"] == "PASS" and main["total_return"] > 0 and fixed["stress"]["total_return"] > 0 and main["max_drawdown"] > -0.25 and main["max_drawdown"] > benchmark["max_drawdown"] and result["strategy"]["60"]["base"]["total_return"] > 0 and result["strategy"]["180"]["base"]["total_return"] > 0
    output = {"generated_at": base.utc_now(), "evaluation_content_digest": result["content_digest"], "qualification_status": "PASSED_EVALUATION_GATE" if passed else "FAILED_EVALUATION_GATE_STOP", "holdout_authorized": passed, "fixed_rule": "BTCUSDT_SPOT_POSITIVE_90D_0P5X"}; output["content_digest"] = base.canonical_digest({key: value for key, value in output.items() if key != "generated_at"}); base.write_json(Path(args.output), output); print(json.dumps({"status": output["qualification_status"]}))


def command_combine(args):
    development = base.read_json(Path(args.development)); evaluation = base.read_json(Path(args.evaluation)); gate = base.read_json(Path(args.evaluation_gate)); confirmation = base.read_json(Path(args.confirmation)); fixed, main, benchmark = components(confirmation)
    evaluation_return = evaluation["strategy"][str(parent.PRIMARY)]["base"]["total_return"]; combined = (1 + evaluation_return) * (1 + main["total_return"]) - 1
    support = confirmation["data_quality"]["status"] == "PASS" and main["total_return"] >= 0 and fixed["stress"]["total_return"] >= 0 and main["max_drawdown"] > -0.20 and main["max_drawdown"] > benchmark["max_drawdown"] and confirmation["strategy"]["60"]["base"]["total_return"] >= 0 and confirmation["strategy"]["180"]["base"]["total_return"] >= 0 and combined > 0
    conclusion = "SUPPORTS_WITHIN_SCOPE" if gate["holdout_authorized"] and support else ("DOES_NOT_SUPPORT" if main["total_return"] < 0 or combined < 0 else "INSUFFICIENT_EVIDENCE")
    output = {"generated_at": base.utc_now(), "conclusion": conclusion, "scope": "BTCUSDT Binance spot monthly positive 90-day momentum at maximum 0.5x", "development": development["strategy"][str(parent.PRIMARY)]["base"], "evaluation": evaluation["strategy"][str(parent.PRIMARY)]["base"], "confirmation": main, "confirmation_btc_half_long": benchmark, "evaluation_confirmation_compounded_return": combined, "confirmation_support_gate": support, "formal_product_strategy_comparison": "FIXED_BACKGROUND_NOT_REPLAYED_SAME_ASSET_BUT_SPOT_MONTHLY_RULE", "product_effects": "NONE"}; output["content_digest"] = base.canonical_digest({key: value for key, value in output.items() if key != "generated_at"}); base.write_json(Path(args.output), output); print(json.dumps({"conclusion": conclusion, "combined": combined}))


def build_parser():
    parser = argparse.ArgumentParser(description="BTCUSDT spot 90-day positive-momentum study"); sub = parser.add_subparsers(dest="command", required=True)
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
