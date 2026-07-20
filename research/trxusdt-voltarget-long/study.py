from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


PARENT_PATH = Path(__file__).resolve().parent.parent / "trxusdt-voltarget-monthly-tsmom" / "study.py"
SPEC = importlib.util.spec_from_file_location("voltarget_parent", PARENT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load retained volatility-targeting study")
parent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(parent)
base = parent.base

TARGET_VOLS = (0.08, 0.10, 0.12)
PRIMARY_TARGET_VOL = 0.10
FIXED_RULE = "TRXUSDT_VOL60_TARGET10PCT_MONTHLY_LONG_MAX0P5X"


def canonical_digest(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(frames, phase: str, target_vol: float, cost: float, seed: int) -> dict:
    return parent.run(frames, phase, target_vol, cost, seed, False)


def unscaled_target(frames, decision_ms: int, lookback: int) -> dict[str, float]:
    return {parent.SYMBOL: parent.MAXIMUM_GROSS}


def run_unscaled(frames, phase: str, cost: float, seed: int) -> dict:
    start_ms, end_ms = (base.to_ms(value) for value in base.PHASES[phase])
    original = base.target_weights
    base.target_weights = unscaled_target
    try:
        return base.simulate_strategy(frames, start_ms, end_ms, parent.TREND_LOOKBACK, cost, seed)
    finally:
        base.target_weights = original


def phase_result(frames, phase: str) -> dict:
    start_ms, end_ms = (base.to_ms(value) for value in base.PHASES[phase])
    strategy = {
        f"{target:.2f}": {
            name: run(frames, phase, target, cost, 20260720 + vi * 10 + ci)
            for ci, (name, cost) in enumerate(parent.parent.parent.COSTS.items())
        }
        for vi, target in enumerate(TARGET_VOLS)
    }
    unscaled = {
        name: run_unscaled(frames, phase, cost, 20261720 + ci)
        for ci, (name, cost) in enumerate(parent.parent.parent.COSTS.items())
    }
    return {
        "phase": phase,
        "period": {"start": base.PHASES[phase][0], "end_exclusive": base.PHASES[phase][1]},
        "data_quality": base.data_quality(frames, start_ms, end_ms),
        "strategy": strategy,
        "unscaled_half_long": unscaled,
    }


def command_fetch(args: argparse.Namespace) -> None:
    parent.command_fetch(args)


def command_analyze(args: argparse.Namespace) -> None:
    if args.phase == "confirmation":
        if not args.authorization or not base.read_json(Path(args.authorization)).get("holdout_authorized"):
            raise RuntimeError("confirmation is not authorized")
    manifest = base.read_json(Path(args.manifest))
    frames = base.load_inputs(Path(args.cache_dir).resolve(), manifest)
    output = phase_result(frames, args.phase)
    output.update({
        "schema_version": 1,
        "generated_at": base.utc_now(),
        "manifest_content_identity": manifest["content_identity"],
        "study_code_sha256": sha256_path(Path(__file__)),
        "parent_study_code_sha256": sha256_path(PARENT_PATH),
        "rules": {
            "symbol": parent.SYMBOL,
            "volatility_lookback_days": parent.VOL_LOOKBACK,
            "annual_target_volatilities": list(TARGET_VOLS),
            "primary_target_volatility": PRIMARY_TARGET_VOL,
            "maximum_gross": parent.MAXIMUM_GROSS,
            "direction": "always long; exposure only changes through monthly volatility targeting",
            "costs_per_unit_turnover": parent.parent.parent.COSTS,
            "capital_hurdle_annual": parent.parent.parent.CAPITAL_HURDLE_ANNUAL,
        },
    })
    output["content_digest"] = canonical_digest({key: value for key, value in output.items() if key != "generated_at"})
    base.write_json(Path(args.output), output)
    main = output["strategy"]["0.10"]["base"]
    print(json.dumps({"phase": args.phase, "base_total": main["total_return"], "max_drawdown": main["max_drawdown"]}))


def hurdle(total_return: float, days: int) -> float:
    return parent.parent.parent.hurdle_adjusted(total_return, days)


def command_qualify_calibration(args: argparse.Namespace) -> None:
    development = base.read_json(Path(args.development)); evaluation = base.read_json(Path(args.evaluation))
    passed = True
    diagnostics = {}
    for result in (development, evaluation):
        phase = result["phase"]; fixed = result["strategy"]["0.10"]; main = fixed["base"]
        stress_hurdle = hurdle(fixed["stress"]["total_return"], fixed["stress"]["days"])
        phase_pass = result["data_quality"]["status"] == "PASS" and stress_hurdle > 0 and main["max_drawdown"] > -0.15 and main["max_drawdown"] > result["unscaled_half_long"]["base"]["max_drawdown"] and result["strategy"]["0.08"]["base"]["total_return"] > 0 and result["strategy"]["0.12"]["base"]["total_return"] > 0
        passed = passed and phase_pass
        diagnostics[phase] = {"passed": phase_pass, "stress_return_after_4pct_hurdle": stress_hurdle}
    payload = {"generated_at": base.utc_now(), "development_content_digest": development["content_digest"], "evaluation_content_digest": evaluation["content_digest"], "qualification_status": "PASSED_EXPOSED_CALIBRATION_GATE" if passed else "FAILED_EXPOSED_CALIBRATION_GATE_STOP", "holdout_authorized": passed, "fixed_rule": FIXED_RULE, "diagnostics": diagnostics}
    payload["content_digest"] = canonical_digest({key: value for key, value in payload.items() if key != "generated_at"})
    base.write_json(Path(args.output), payload); print(json.dumps({"status": payload["qualification_status"]}))


def command_conclude(args: argparse.Namespace) -> None:
    development = base.read_json(Path(args.development)); evaluation = base.read_json(Path(args.evaluation)); gate = base.read_json(Path(args.calibration_gate)); confirmation = base.read_json(Path(args.confirmation))
    fixed = confirmation["strategy"]["0.10"]; main = fixed["base"]
    stress_hurdle = hurdle(fixed["stress"]["total_return"], fixed["stress"]["days"])
    positive_years = sum(item["return"] > 0 for item in main["by_year"].values())
    support = confirmation["data_quality"]["status"] == "PASS" and stress_hurdle > 0 and positive_years == len(main["by_year"]) and main["max_drawdown"] > -0.10 and main["max_drawdown"] > confirmation["unscaled_half_long"]["base"]["max_drawdown"] and confirmation["strategy"]["0.08"]["base"]["total_return"] >= 0 and confirmation["strategy"]["0.12"]["base"]["total_return"] >= 0
    conclusion = "SUPPORTS_WITHIN_SCOPE" if gate["holdout_authorized"] and support else ("DOES_NOT_SUPPORT" if main["total_return"] < 0 else "INSUFFICIENT_EVIDENCE")
    payload = {"generated_at": base.utc_now(), "conclusion": conclusion, "scope": "TRXUSDT spot monthly always-long 60d realized-volatility targeting to 10% annual risk, max 0.5x", "development": development["strategy"]["0.10"]["base"], "evaluation": evaluation["strategy"]["0.10"]["base"], "confirmation": main, "confirmation_unscaled_half_long": confirmation["unscaled_half_long"]["base"], "confirmation_stress_return_after_4pct_annual_hurdle": stress_hurdle, "confirmation_support_gate": support, "evidence_status": "development_and_evaluation_exposed_calibration_fresh_confirmation_only", "formal_product_strategy_comparison": "FIXED_BACKGROUND_ONLY_DIFFERENT_ASSET_AND_SPOT_CONTRACT", "product_effects": "NONE"}
    payload["content_digest"] = canonical_digest({key: value for key, value in payload.items() if key != "generated_at"})
    base.write_json(Path(args.output), payload); print(json.dumps({"conclusion": conclusion, "support": support}))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TRX spot always-long volatility target"); sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch"); fetch.add_argument("--cache-dir", required=True); fetch.add_argument("--start-month", required=True); fetch.add_argument("--end-month", required=True); fetch.add_argument("--manifest", required=True); fetch.set_defaults(func=command_fetch)
    analyze = sub.add_parser("analyze"); analyze.add_argument("--cache-dir", required=True); analyze.add_argument("--manifest", required=True); analyze.add_argument("--phase", choices=tuple(base.PHASES), required=True); analyze.add_argument("--authorization"); analyze.add_argument("--output", required=True); analyze.set_defaults(func=command_analyze)
    gate = sub.add_parser("qualify-calibration"); gate.add_argument("--development", required=True); gate.add_argument("--evaluation", required=True); gate.add_argument("--output", required=True); gate.set_defaults(func=command_qualify_calibration)
    conclude = sub.add_parser("conclude"); conclude.add_argument("--development", required=True); conclude.add_argument("--evaluation", required=True); conclude.add_argument("--calibration-gate", required=True); conclude.add_argument("--confirmation", required=True); conclude.add_argument("--output", required=True); conclude.set_defaults(func=command_conclude)
    return parser


def main() -> None:
    args = build_parser().parse_args(); args.func(args)


if __name__ == "__main__":
    main()
