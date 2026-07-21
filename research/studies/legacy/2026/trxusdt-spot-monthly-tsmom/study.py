from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


PARENT_PATH = Path(__file__).resolve().parent.parent / "paxgusdt-spot-monthly-tsmom" / "study.py"
SPEC = importlib.util.spec_from_file_location("spot_tsmom_parent", PARENT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load retained spot time-series momentum study")
parent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(parent)
base = parent.base

SYMBOL = "TRXUSDT"
parent.SYMBOL = SYMBOL
parent.SYMBOLS = (SYMBOL,)
parent.base.SYMBOLS = (SYMBOL,)
parent.__file__ = str(Path(__file__).resolve())
FIXED_RULE = "TRXUSDT_POSITIVE_180D_MONTHLY_0P5X"


def canonical_digest(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def command_fetch(args: argparse.Namespace) -> None:
    parent.command_fetch(args)


def command_analyze(args: argparse.Namespace) -> None:
    parent.command_analyze(args)


def components(result: dict) -> tuple[dict, dict, dict]:
    fixed = result["strategy"][str(parent.PRIMARY)]
    return fixed, fixed["base"], result["passive_half_long"]["base"]


def write_gate(path: Path, payload: dict) -> None:
    payload["content_digest"] = canonical_digest({key: value for key, value in payload.items() if key != "generated_at"})
    parent.base.write_json(path, payload)


def command_qualify_development(args: argparse.Namespace) -> None:
    result = parent.base.read_json(Path(args.development))
    fixed, main, passive = components(result)
    stress_after_hurdle = parent.hurdle_adjusted(fixed["stress"]["total_return"], fixed["stress"]["days"])
    passed = (
        result["data_quality"]["status"] == "PASS"
        and stress_after_hurdle > 0
        and main["max_drawdown"] > -0.25
        and main["max_drawdown"] > passive["max_drawdown"]
        and result["strategy"]["90"]["base"]["total_return"] > 0
        and result["strategy"]["270"]["base"]["total_return"] > 0
        and main["turnover"] <= 8
    )
    payload = {
        "generated_at": parent.base.utc_now(),
        "development_content_digest": result["content_digest"],
        "qualification_status": "PASSED_DEVELOPMENT_GATE" if passed else "FAILED_DEVELOPMENT_GATE_STOP",
        "holdout_authorized": passed,
        "fixed_rule": FIXED_RULE,
        "stress_return_after_4pct_annual_hurdle": stress_after_hurdle,
    }
    write_gate(Path(args.output), payload)
    print(json.dumps({"status": payload["qualification_status"]}))


def command_qualify_evaluation(args: argparse.Namespace) -> None:
    result = parent.base.read_json(Path(args.evaluation))
    fixed, main, passive = components(result)
    stress_after_hurdle = parent.hurdle_adjusted(fixed["stress"]["total_return"], fixed["stress"]["days"])
    positive_years = sum(item["return"] > 0 for item in main["by_year"].values())
    passed = (
        result["data_quality"]["status"] == "PASS"
        and stress_after_hurdle > 0
        and positive_years == len(main["by_year"])
        and main["max_drawdown"] > -0.18
        and main["max_drawdown"] > passive["max_drawdown"]
        and result["strategy"]["90"]["base"]["total_return"] > 0
        and result["strategy"]["270"]["base"]["total_return"] > 0
    )
    payload = {
        "generated_at": parent.base.utc_now(),
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
    development = parent.base.read_json(Path(args.development))
    evaluation = parent.base.read_json(Path(args.evaluation))
    evaluation_gate = parent.base.read_json(Path(args.evaluation_gate))
    confirmation = parent.base.read_json(Path(args.confirmation))
    fixed, main, passive = components(confirmation)
    stress_after_hurdle = parent.hurdle_adjusted(fixed["stress"]["total_return"], fixed["stress"]["days"])
    positive_years = sum(item["return"] > 0 for item in main["by_year"].values())
    evaluation_return = evaluation["strategy"][str(parent.PRIMARY)]["base"]["total_return"]
    combined = (1.0 + evaluation_return) * (1.0 + main["total_return"]) - 1.0
    support = (
        confirmation["data_quality"]["status"] == "PASS"
        and stress_after_hurdle > 0
        and positive_years == len(main["by_year"])
        and main["max_drawdown"] > -0.15
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
        "generated_at": parent.base.utc_now(),
        "conclusion": conclusion,
        "scope": "TRXUSDT Binance spot monthly positive 180d return long/cash at 0.5 maximum gross",
        "development": development["strategy"][str(parent.PRIMARY)]["base"],
        "evaluation": evaluation["strategy"][str(parent.PRIMARY)]["base"],
        "confirmation": main,
        "confirmation_passive_half_long": passive,
        "confirmation_stress_return_after_4pct_annual_hurdle": stress_after_hurdle,
        "evaluation_confirmation_compounded_return": combined,
        "confirmation_support_gate": support,
        "formal_product_strategy_comparison": "FIXED_BACKGROUND_ONLY_DIFFERENT_ASSET_AND_SPOT_CONTRACT",
        "product_effects": "NONE",
    }
    payload["content_digest"] = canonical_digest({key: value for key, value in payload.items() if key != "generated_at"})
    parent.base.write_json(Path(args.output), payload)
    print(json.dumps({"conclusion": conclusion, "combined": combined}))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TRXUSDT monthly spot time-series momentum")
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
    analyze.add_argument("--phase", choices=tuple(parent.base.PHASES), required=True)
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
