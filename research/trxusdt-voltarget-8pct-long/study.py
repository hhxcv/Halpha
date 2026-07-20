from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


PARENT_PATH = Path(__file__).resolve().parent.parent / "trxusdt-voltarget-long" / "study.py"
SPEC = importlib.util.spec_from_file_location("voltarget_long_parent", PARENT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load retained always-long volatility target study")
parent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(parent)
base = parent.base

TARGET_VOLS = (0.06, 0.08, 0.10)
PRIMARY = "0.08"
FIXED_RULE = "TRXUSDT_VOL60_TARGET8PCT_MONTHLY_LONG_MAX0P5X"
parent.TARGET_VOLS = TARGET_VOLS
parent.PRIMARY_TARGET_VOL = 0.08
parent.__file__ = str(Path(__file__).resolve())


def canonical_digest(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def command_fetch(args: argparse.Namespace) -> None:
    parent.command_fetch(args)


def command_analyze(args: argparse.Namespace) -> None:
    parent.command_analyze(args)


def hurdle(total_return: float, days: int) -> float:
    return parent.hurdle(total_return, days)


def command_qualify_calibration(args: argparse.Namespace) -> None:
    development = base.read_json(Path(args.development)); evaluation = base.read_json(Path(args.evaluation)); passed = True; diagnostics = {}
    for result in (development, evaluation):
        phase = result["phase"]; fixed = result["strategy"][PRIMARY]; main = fixed["base"]; stress_hurdle = hurdle(fixed["stress"]["total_return"], fixed["stress"]["days"])
        phase_pass = result["data_quality"]["status"] == "PASS" and stress_hurdle > 0 and main["max_drawdown"] > -0.14 and main["max_drawdown"] > result["unscaled_half_long"]["base"]["max_drawdown"] and result["strategy"]["0.06"]["base"]["total_return"] > 0 and result["strategy"]["0.10"]["base"]["total_return"] > 0
        passed = passed and phase_pass; diagnostics[phase] = {"passed": phase_pass, "stress_return_after_4pct_hurdle": stress_hurdle}
    payload = {"generated_at": base.utc_now(), "development_content_digest": development["content_digest"], "evaluation_content_digest": evaluation["content_digest"], "qualification_status": "PASSED_EXPOSED_CALIBRATION_GATE" if passed else "FAILED_EXPOSED_CALIBRATION_GATE_STOP", "holdout_authorized": passed, "fixed_rule": FIXED_RULE, "diagnostics": diagnostics}
    payload["content_digest"] = canonical_digest({key: value for key, value in payload.items() if key != "generated_at"}); base.write_json(Path(args.output), payload); print(json.dumps({"status": payload["qualification_status"]}))


def command_conclude(args: argparse.Namespace) -> None:
    development = base.read_json(Path(args.development)); evaluation = base.read_json(Path(args.evaluation)); gate = base.read_json(Path(args.calibration_gate)); confirmation = base.read_json(Path(args.confirmation))
    fixed = confirmation["strategy"][PRIMARY]; main = fixed["base"]; stress_hurdle = hurdle(fixed["stress"]["total_return"], fixed["stress"]["days"]); positive_years = sum(item["return"] > 0 for item in main["by_year"].values())
    support = confirmation["data_quality"]["status"] == "PASS" and stress_hurdle > 0 and positive_years == len(main["by_year"]) and main["max_drawdown"] > -0.10 and main["max_drawdown"] > confirmation["unscaled_half_long"]["base"]["max_drawdown"] and confirmation["strategy"]["0.06"]["base"]["total_return"] >= 0 and confirmation["strategy"]["0.10"]["base"]["total_return"] >= 0
    conclusion = "SUPPORTS_WITHIN_SCOPE" if gate["holdout_authorized"] and support else ("DOES_NOT_SUPPORT" if main["total_return"] < 0 else "INSUFFICIENT_EVIDENCE")
    payload = {"generated_at": base.utc_now(), "conclusion": conclusion, "scope": "TRXUSDT spot monthly always-long 60d realized-volatility targeting to 8% annual risk, max 0.5x", "development": development["strategy"][PRIMARY]["base"], "evaluation": evaluation["strategy"][PRIMARY]["base"], "confirmation": main, "confirmation_unscaled_half_long": confirmation["unscaled_half_long"]["base"], "confirmation_stress_return_after_4pct_annual_hurdle": stress_hurdle, "confirmation_support_gate": support, "evidence_status": "8pct_was_preregistered_diagnostic_in_parent_fresh_confirmation_only", "formal_product_strategy_comparison": "FIXED_BACKGROUND_ONLY_DIFFERENT_ASSET_AND_SPOT_CONTRACT", "product_effects": "NONE"}
    payload["content_digest"] = canonical_digest({key: value for key, value in payload.items() if key != "generated_at"}); base.write_json(Path(args.output), payload); print(json.dumps({"conclusion": conclusion, "support": support}))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TRX spot 8% always-long volatility target"); sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch"); fetch.add_argument("--cache-dir", required=True); fetch.add_argument("--start-month", required=True); fetch.add_argument("--end-month", required=True); fetch.add_argument("--manifest", required=True); fetch.set_defaults(func=command_fetch)
    analyze = sub.add_parser("analyze"); analyze.add_argument("--cache-dir", required=True); analyze.add_argument("--manifest", required=True); analyze.add_argument("--phase", choices=tuple(base.PHASES), required=True); analyze.add_argument("--authorization"); analyze.add_argument("--output", required=True); analyze.set_defaults(func=command_analyze)
    gate = sub.add_parser("qualify-calibration"); gate.add_argument("--development", required=True); gate.add_argument("--evaluation", required=True); gate.add_argument("--output", required=True); gate.set_defaults(func=command_qualify_calibration)
    conclude = sub.add_parser("conclude"); conclude.add_argument("--development", required=True); conclude.add_argument("--evaluation", required=True); conclude.add_argument("--calibration-gate", required=True); conclude.add_argument("--confirmation", required=True); conclude.add_argument("--output", required=True); conclude.set_defaults(func=command_conclude)
    return parser


def main() -> None:
    args = build_parser().parse_args(); args.func(args)


if __name__ == "__main__":
    main()
