from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


PARENT_PATH = Path(__file__).resolve().parent.parent / "mature-liquid-spot-low-vol-trend-filter" / "study.py"
SPEC = importlib.util.spec_from_file_location("trend_filter_parent", PARENT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load retained trend-filter study")
parent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(parent)
base = parent.base

# This is the only rule change from the exposed parent study. It is fixed before
# any evaluation or confirmation data are acquired.
MAXIMUM_GROSS = 0.30
WEIGHT_PER_ELIGIBLE_ASSET = 0.10
parent.parent.GROSS = MAXIMUM_GROSS
parent.parent.WEIGHT = WEIGHT_PER_ELIGIBLE_ASSET
FIXED_RULE = "BOTTOM3_REALIZED_VOL_POSITIVE_TREND_90D_0P3X"


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command_fetch(args: argparse.Namespace) -> None:
    parent.command_fetch(args)


def command_analyze(args: argparse.Namespace) -> None:
    if args.phase != "development":
        if not args.authorization or not base.read_json(Path(args.authorization)).get("holdout_authorized"):
            raise RuntimeError("holdout is not authorized")
    manifest = base.read_json(Path(args.manifest))
    frames = base.load_inputs(Path(args.cache_dir).resolve(), manifest)
    output = parent.phase_result(frames, args.phase)
    output.update({
        "schema_version": 1,
        "generated_at": base.utc_now(),
        "manifest_content_identity": manifest["content_identity"],
        "study_code_sha256": sha256_path(Path(__file__)),
        "parent_study_code_sha256": sha256_path(PARENT_PATH),
        "rules": {
            "symbols": list(parent.parent.SYMBOLS),
            "lookbacks": list(parent.parent.LOOKBACKS),
            "primary_lookback": parent.parent.PRIMARY,
            "selection": "bottom 3 realized volatility then retain only assets with positive own-window return",
            "weight_per_eligible_asset": WEIGHT_PER_ELIGIBLE_ASSET,
            "maximum_gross": MAXIMUM_GROSS,
            "rebalance": "first UTC daily open monthly using information through prior UTC close",
            "costs_per_unit_turnover": base.COSTS,
        },
    })
    output["content_digest"] = base.canonical_digest(
        {key: value for key, value in output.items() if key != "generated_at"}
    )
    base.write_json(Path(args.output), output)
    main = output["strategy"][str(parent.parent.PRIMARY)]["base"]
    print(json.dumps({"phase": args.phase, "base_total": main["total_return"], "max_drawdown": main["max_drawdown"]}))


def components(result: dict) -> tuple[dict, dict, dict, dict]:
    fixed = result["strategy"][str(parent.parent.PRIMARY)]
    return fixed, fixed["base"], result["unfiltered_low_vol"]["base"], result["monthly_rebalanced_half_long"]["base"]


def write_gate(path: Path, payload: dict) -> None:
    payload["content_digest"] = base.canonical_digest(
        {key: value for key, value in payload.items() if key != "generated_at"}
    )
    base.write_json(path, payload)


def command_qualify_development(args: argparse.Namespace) -> None:
    result = base.read_json(Path(args.development))
    fixed, main, unfiltered, simpler = components(result)
    drawdown_improvement = main["max_drawdown"] - unfiltered["max_drawdown"]
    passed = (
        result["data_quality"]["status"] == "PASS"
        and main["total_return"] > 0
        and fixed["stress"]["total_return"] > 0
        and main["max_drawdown"] > -0.22
        and drawdown_improvement >= 0.02
        and main["max_drawdown"] > simpler["max_drawdown"]
        and result["strategy"]["60"]["base"]["total_return"] > 0
        and result["strategy"]["180"]["base"]["total_return"] > 0
        and main["turnover"] <= 18
    )
    payload = {
        "generated_at": base.utc_now(),
        "development_content_digest": result["content_digest"],
        "qualification_status": "PASSED_DEVELOPMENT_GATE" if passed else "FAILED_DEVELOPMENT_GATE_STOP",
        "holdout_authorized": passed,
        "fixed_rule": FIXED_RULE,
        "drawdown_improvement_vs_unfiltered": drawdown_improvement,
    }
    write_gate(Path(args.output), payload)
    print(json.dumps({"status": payload["qualification_status"]}))


def command_qualify_evaluation(args: argparse.Namespace) -> None:
    result = base.read_json(Path(args.evaluation))
    fixed, main, unfiltered, simpler = components(result)
    positive_years = sum(item["return"] > 0 for item in main["by_year"].values())
    passed = (
        result["data_quality"]["status"] == "PASS"
        and main["total_return"] > 0
        and fixed["stress"]["total_return"] > 0
        and positive_years == len(main["by_year"])
        and main["max_drawdown"] > -0.18
        and main["max_drawdown"] > unfiltered["max_drawdown"]
        and main["max_drawdown"] > simpler["max_drawdown"]
        and result["strategy"]["60"]["base"]["total_return"] > 0
        and result["strategy"]["180"]["base"]["total_return"] > 0
    )
    payload = {
        "generated_at": base.utc_now(),
        "evaluation_content_digest": result["content_digest"],
        "qualification_status": "PASSED_EVALUATION_GATE" if passed else "FAILED_EVALUATION_GATE_STOP",
        "holdout_authorized": passed,
        "fixed_rule": FIXED_RULE,
        "positive_years": positive_years,
    }
    write_gate(Path(args.output), payload)
    print(json.dumps({"status": payload["qualification_status"]}))


def command_combine(args: argparse.Namespace) -> None:
    development = base.read_json(Path(args.development))
    evaluation = base.read_json(Path(args.evaluation))
    evaluation_gate = base.read_json(Path(args.evaluation_gate))
    confirmation = base.read_json(Path(args.confirmation))
    fixed, main, unfiltered, simpler = components(confirmation)
    evaluation_return = evaluation["strategy"][str(parent.parent.PRIMARY)]["base"]["total_return"]
    combined = (1.0 + evaluation_return) * (1.0 + main["total_return"]) - 1.0
    positive_years = sum(item["return"] > 0 for item in main["by_year"].values())
    support = (
        confirmation["data_quality"]["status"] == "PASS"
        and main["total_return"] > 0
        and fixed["stress"]["total_return"] > 0
        and positive_years >= 1
        and main["max_drawdown"] > -0.15
        and main["max_drawdown"] > unfiltered["max_drawdown"]
        and main["max_drawdown"] > simpler["max_drawdown"]
        and confirmation["strategy"]["60"]["base"]["total_return"] >= 0
        and confirmation["strategy"]["180"]["base"]["total_return"] >= 0
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
        "scope": "fixed 13-symbol Binance spot universe; monthly bottom-3 90d realized volatility; own-positive-trend filter; 0.1 each and 0.3 maximum gross",
        "development": development["strategy"][str(parent.parent.PRIMARY)]["base"],
        "evaluation": evaluation["strategy"][str(parent.parent.PRIMARY)]["base"],
        "confirmation": main,
        "confirmation_unfiltered_low_vol": unfiltered,
        "confirmation_monthly_rebalanced_0p3x_equal_weight": simpler,
        "evaluation_confirmation_compounded_return": combined,
        "confirmation_positive_years": positive_years,
        "confirmation_support_gate": support,
        "formal_product_strategy_comparison": "NOT_RUN_NO_COMPARABLE_MULTI_ASSET_SPOT_ACTIVATION_REPLAY",
        "product_effects": "NONE",
    }
    payload["content_digest"] = base.canonical_digest(
        {key: value for key, value in payload.items() if key != "generated_at"}
    )
    base.write_json(Path(args.output), payload)
    print(json.dumps({"conclusion": conclusion, "combined": combined}))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Conservative mature-liquid spot low-volatility trend-filter study")
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
