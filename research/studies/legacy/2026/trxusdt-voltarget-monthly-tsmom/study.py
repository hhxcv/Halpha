from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path


PARENT_PATH = Path(__file__).resolve().parent.parent / "trxusdt-spot-monthly-tsmom" / "study.py"
SPEC = importlib.util.spec_from_file_location("trx_tsmom_parent", PARENT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load retained TRX trend study")
parent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(parent)
base = parent.base

SYMBOL = "TRXUSDT"
TREND_LOOKBACK = 180
VOL_LOOKBACK = 60
TARGET_VOLS = (0.12, 0.15, 0.18)
PRIMARY_TARGET_VOL = 0.15
MAXIMUM_GROSS = 0.50
FIXED_RULE = "TRXUSDT_POSITIVE_180D_VOL60_TARGET15PCT_MONTHLY_MAX0P5X"


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_digest(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def vol_target(frames, decision_ms: int, target_vol: float, require_positive_trend: bool) -> dict[str, float]:
    frame = frames[SYMBOL]
    trend_start = decision_ms - TREND_LOOKBACK * base.DAY_MS
    vol_start = decision_ms - VOL_LOOKBACK * base.DAY_MS
    if decision_ms not in frame.index or trend_start not in frame.index or vol_start not in frame.index:
        return {SYMBOL: 0.0}
    if require_positive_trend and float(frame.at[decision_ms, "close"]) <= float(frame.at[trend_start, "close"]):
        return {SYMBOL: 0.0}
    closes = frame.loc[(frame.index >= vol_start) & (frame.index <= decision_ms), "close"].astype(float)
    if len(closes) != VOL_LOOKBACK + 1:
        return {SYMBOL: 0.0}
    realized = float(closes.map(math.log).diff().dropna().std(ddof=1) * math.sqrt(365.0))
    weight = min(MAXIMUM_GROSS, target_vol / realized) if realized > 0 else 0.0
    return {SYMBOL: weight}


def run(frames, phase: str, target_vol: float, cost: float, seed: int, require_positive_trend: bool) -> dict:
    start_ms, end_ms = (base.to_ms(value) for value in base.PHASES[phase])
    original = base.target_weights
    base.target_weights = lambda fixed_frames, decision_ms, lookback: vol_target(fixed_frames, decision_ms, target_vol, require_positive_trend)
    try:
        return base.simulate_strategy(frames, start_ms, end_ms, TREND_LOOKBACK, cost, seed)
    finally:
        base.target_weights = original


def phase_result(frames, phase: str) -> dict:
    start_ms, end_ms = (base.to_ms(value) for value in base.PHASES[phase])
    strategy = {
        f"{target_vol:.2f}": {
            name: run(frames, phase, target_vol, cost, 20260720 + vi * 10 + ci, True)
            for ci, (name, cost) in enumerate(parent.parent.COSTS.items())
        }
        for vi, target_vol in enumerate(TARGET_VOLS)
    }
    scaled_passive = {
        name: run(frames, phase, PRIMARY_TARGET_VOL, cost, 20261720 + ci, False)
        for ci, (name, cost) in enumerate(parent.parent.COSTS.items())
    }
    return {
        "phase": phase,
        "period": {"start": base.PHASES[phase][0], "end_exclusive": base.PHASES[phase][1]},
        "data_quality": base.data_quality(frames, start_ms, end_ms),
        "strategy": strategy,
        "vol_scaled_passive": scaled_passive,
    }


def command_fetch(args: argparse.Namespace) -> None:
    parent.command_fetch(args)


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
        "parent_study_code_sha256": sha256_path(PARENT_PATH),
        "rules": {
            "symbol": SYMBOL,
            "trend_lookback_days": TREND_LOOKBACK,
            "volatility_lookback_days": VOL_LOOKBACK,
            "annual_target_volatilities": list(TARGET_VOLS),
            "primary_target_volatility": PRIMARY_TARGET_VOL,
            "maximum_gross": MAXIMUM_GROSS,
            "rebalance": "first UTC daily open monthly using information through prior UTC close",
            "costs_per_unit_turnover": parent.parent.COSTS,
            "capital_hurdle_annual": parent.parent.CAPITAL_HURDLE_ANNUAL,
        },
    })
    output["content_digest"] = canonical_digest({key: value for key, value in output.items() if key != "generated_at"})
    base.write_json(Path(args.output), output)
    main = output["strategy"][f"{PRIMARY_TARGET_VOL:.2f}"]["base"]
    print(json.dumps({"phase": args.phase, "base_total": main["total_return"], "max_drawdown": main["max_drawdown"]}))


def components(result: dict) -> tuple[dict, dict, dict]:
    fixed = result["strategy"][f"{PRIMARY_TARGET_VOL:.2f}"]
    return fixed, fixed["base"], result["vol_scaled_passive"]["base"]


def hurdle(total_return: float, days: int) -> float:
    return parent.parent.hurdle_adjusted(total_return, days)


def write_gate(path: Path, payload: dict) -> None:
    payload["content_digest"] = canonical_digest({key: value for key, value in payload.items() if key != "generated_at"})
    base.write_json(path, payload)


def command_qualify_development(args: argparse.Namespace) -> None:
    result = base.read_json(Path(args.development))
    fixed, main, passive = components(result)
    stress_hurdle = hurdle(fixed["stress"]["total_return"], fixed["stress"]["days"])
    passed = (
        result["data_quality"]["status"] == "PASS"
        and stress_hurdle > 0
        and main["max_drawdown"] > -0.20
        and main["max_drawdown"] > passive["max_drawdown"]
        and result["strategy"]["0.12"]["base"]["total_return"] > 0
        and result["strategy"]["0.18"]["base"]["total_return"] > 0
        and main["turnover"] <= 8
    )
    payload = {"generated_at": base.utc_now(), "development_content_digest": result["content_digest"], "qualification_status": "PASSED_DEVELOPMENT_GATE" if passed else "FAILED_DEVELOPMENT_GATE_STOP", "holdout_authorized": passed, "fixed_rule": FIXED_RULE, "stress_return_after_4pct_annual_hurdle": stress_hurdle}
    write_gate(Path(args.output), payload)
    print(json.dumps({"status": payload["qualification_status"]}))


def command_qualify_evaluation(args: argparse.Namespace) -> None:
    result = base.read_json(Path(args.evaluation))
    fixed, main, passive = components(result)
    stress_hurdle = hurdle(fixed["stress"]["total_return"], fixed["stress"]["days"])
    positive_years = sum(item["return"] > 0 for item in main["by_year"].values())
    passed = (
        result["data_quality"]["status"] == "PASS"
        and stress_hurdle > 0
        and positive_years == len(main["by_year"])
        and main["max_drawdown"] > -0.15
        and main["max_drawdown"] > passive["max_drawdown"]
        and result["strategy"]["0.12"]["base"]["total_return"] > 0
        and result["strategy"]["0.18"]["base"]["total_return"] > 0
    )
    payload = {"generated_at": base.utc_now(), "evaluation_content_digest": result["content_digest"], "qualification_status": "PASSED_EVALUATION_GATE" if passed else "FAILED_EVALUATION_GATE_STOP", "holdout_authorized": passed, "fixed_rule": FIXED_RULE, "positive_years": positive_years, "stress_return_after_4pct_annual_hurdle": stress_hurdle}
    write_gate(Path(args.output), payload)
    print(json.dumps({"status": payload["qualification_status"]}))


def command_combine(args: argparse.Namespace) -> None:
    development = base.read_json(Path(args.development)); evaluation = base.read_json(Path(args.evaluation)); gate = base.read_json(Path(args.evaluation_gate)); confirmation = base.read_json(Path(args.confirmation))
    fixed, main, passive = components(confirmation)
    stress_hurdle = hurdle(fixed["stress"]["total_return"], fixed["stress"]["days"])
    positive_years = sum(item["return"] > 0 for item in main["by_year"].values())
    evaluation_return = evaluation["strategy"][f"{PRIMARY_TARGET_VOL:.2f}"]["base"]["total_return"]
    combined = (1 + evaluation_return) * (1 + main["total_return"]) - 1
    support = confirmation["data_quality"]["status"] == "PASS" and stress_hurdle > 0 and positive_years == len(main["by_year"]) and main["max_drawdown"] > -0.12 and main["max_drawdown"] > passive["max_drawdown"] and confirmation["strategy"]["0.12"]["base"]["total_return"] >= 0 and confirmation["strategy"]["0.18"]["base"]["total_return"] >= 0 and combined > 0
    conclusion = "SUPPORTS_WITHIN_SCOPE" if gate["holdout_authorized"] and support else ("DOES_NOT_SUPPORT" if main["total_return"] < 0 or combined < 0 else "INSUFFICIENT_EVIDENCE")
    payload = {"generated_at": base.utc_now(), "conclusion": conclusion, "scope": "TRXUSDT spot monthly positive-180d trend with 60d realized-volatility scaling to 15% annual target, max 0.5x", "development": development["strategy"]["0.15"]["base"], "evaluation": evaluation["strategy"]["0.15"]["base"], "confirmation": main, "confirmation_vol_scaled_passive": passive, "confirmation_stress_return_after_4pct_annual_hurdle": stress_hurdle, "evaluation_confirmation_compounded_return": combined, "confirmation_support_gate": support, "formal_product_strategy_comparison": "FIXED_BACKGROUND_ONLY_DIFFERENT_ASSET_AND_SPOT_CONTRACT", "product_effects": "NONE"}
    payload["content_digest"] = canonical_digest({key: value for key, value in payload.items() if key != "generated_at"})
    base.write_json(Path(args.output), payload)
    print(json.dumps({"conclusion": conclusion, "combined": combined}))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TRX spot volatility-targeted monthly time-series momentum"); sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch"); fetch.add_argument("--cache-dir", required=True); fetch.add_argument("--start-month", required=True); fetch.add_argument("--end-month", required=True); fetch.add_argument("--manifest", required=True); fetch.set_defaults(func=command_fetch)
    analyze = sub.add_parser("analyze"); analyze.add_argument("--cache-dir", required=True); analyze.add_argument("--manifest", required=True); analyze.add_argument("--phase", choices=tuple(base.PHASES), required=True); analyze.add_argument("--authorization"); analyze.add_argument("--output", required=True); analyze.set_defaults(func=command_analyze)
    dev = sub.add_parser("qualify-development"); dev.add_argument("--development", required=True); dev.add_argument("--output", required=True); dev.set_defaults(func=command_qualify_development)
    eva = sub.add_parser("qualify-evaluation"); eva.add_argument("--evaluation", required=True); eva.add_argument("--output", required=True); eva.set_defaults(func=command_qualify_evaluation)
    combine = sub.add_parser("combine"); combine.add_argument("--development", required=True); combine.add_argument("--evaluation", required=True); combine.add_argument("--evaluation-gate", required=True); combine.add_argument("--confirmation", required=True); combine.add_argument("--output", required=True); combine.set_defaults(func=command_combine)
    return parser


def main() -> None:
    args = build_parser().parse_args(); args.func(args)


if __name__ == "__main__":
    main()
