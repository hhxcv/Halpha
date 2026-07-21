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

SYMBOLS = ("TRXUSDT", "PAXGUSDT")
TRX, PAXG = SYMBOLS
WEIGHT = 0.25
MAXIMUM_GROSS = 0.50
COSTS = {"favorable": 0.0010, "base": 0.0030, "stress": 0.0060}
ANNUAL_CAPITAL_HURDLE = 0.04
FIXED_RULE = "TRX_PAXG_MONTHLY_25PCT_EACH_MAX0P5X"
base.SYMBOLS = SYMBOLS


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_digest(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def target_balanced(frames, decision_ms: int, lookback: int) -> dict[str, float]:
    return {TRX: WEIGHT, PAXG: WEIGHT}


def target_trx(frames, decision_ms: int, lookback: int) -> dict[str, float]:
    return {TRX: MAXIMUM_GROSS, PAXG: 0.0}


def target_paxg(frames, decision_ms: int, lookback: int) -> dict[str, float]:
    return {TRX: 0.0, PAXG: MAXIMUM_GROSS}


def run(frames, phase: str, cost: float, seed: int, target) -> dict:
    start_ms, end_ms = (base.to_ms(value) for value in base.PHASES[phase])
    original = base.target_weights
    base.target_weights = target
    try:
        return base.simulate_strategy(frames, start_ms, end_ms, 1, cost, seed)
    finally:
        base.target_weights = original


def hurdle(total_return: float, days: int) -> float:
    return (1.0 + total_return) / ((1.0 + ANNUAL_CAPITAL_HURDLE) ** (days / 365.0)) - 1.0


def phase_result(frames, phase: str) -> dict:
    start_ms, end_ms = (base.to_ms(value) for value in base.PHASES[phase])
    return {
        "phase": phase,
        "period": {"start": base.PHASES[phase][0], "end_exclusive": base.PHASES[phase][1]},
        "data_quality": base.data_quality(frames, start_ms, end_ms),
        "balanced": {name: run(frames, phase, cost, 20260720 + ci, target_balanced) for ci, (name, cost) in enumerate(COSTS.items())},
        "trx_half_long": {name: run(frames, phase, cost, 20261720 + ci, target_trx) for ci, (name, cost) in enumerate(COSTS.items())},
        "paxg_half_long": {name: run(frames, phase, cost, 20262720 + ci, target_paxg) for ci, (name, cost) in enumerate(COSTS.items())},
    }


def command_fetch(args: argparse.Namespace) -> None:
    base.command_fetch(args)


def command_analyze(args: argparse.Namespace) -> None:
    if args.phase != "development":
        if not args.authorization or not base.read_json(Path(args.authorization)).get("holdout_authorized"):
            raise RuntimeError("holdout is not authorized")
    manifest_path = Path(args.manifest); manifest = base.read_json(manifest_path); frames = base.load_inputs(Path(args.cache_dir).resolve(), manifest); output = phase_result(frames, args.phase)
    output.update({"schema_version": 1, "generated_at": base.utc_now(), "manifest_content_identity": manifest["content_identity"], "manifest_sha256": sha256_path(manifest_path), "study_code_sha256": sha256_path(Path(__file__)), "base_study_code_sha256": sha256_path(BASE_PATH), "rules": {"symbols": list(SYMBOLS), "target_weights": {TRX: WEIGHT, PAXG: WEIGHT}, "maximum_gross": MAXIMUM_GROSS, "rebalance": "first UTC daily open monthly", "costs_per_unit_turnover": COSTS, "annual_capital_hurdle": ANNUAL_CAPITAL_HURDLE}})
    output["content_digest"] = canonical_digest({key: value for key, value in output.items() if key != "generated_at"}); base.write_json(Path(args.output), output)
    print(json.dumps({"phase": args.phase, "base_total": output["balanced"]["base"]["total_return"], "max_drawdown": output["balanced"]["base"]["max_drawdown"]}))


def write_gate(path: Path, payload: dict) -> None:
    payload["content_digest"] = canonical_digest({key: value for key, value in payload.items() if key != "generated_at"}); base.write_json(path, payload)


def command_qualify_development(args: argparse.Namespace) -> None:
    result = base.read_json(Path(args.development)); main = result["balanced"]["base"]; stress = result["balanced"]["stress"]; stress_hurdle = hurdle(stress["total_return"], stress["days"])
    passed = result["data_quality"]["status"] == "PASS" and stress_hurdle > 0 and main["max_drawdown"] > -0.25 and main["max_drawdown"] > result["trx_half_long"]["base"]["max_drawdown"] and sum(item["return"] > 0 for item in main["by_year"].values()) >= 1 and main["turnover"] <= 4
    payload = {"generated_at": base.utc_now(), "development_content_digest": result["content_digest"], "qualification_status": "PASSED_DEVELOPMENT_GATE" if passed else "FAILED_DEVELOPMENT_GATE_STOP", "holdout_authorized": passed, "fixed_rule": FIXED_RULE, "stress_return_after_4pct_annual_hurdle": stress_hurdle}; write_gate(Path(args.output), payload); print(json.dumps({"status": payload["qualification_status"]}))


def command_qualify_evaluation(args: argparse.Namespace) -> None:
    result = base.read_json(Path(args.evaluation)); main = result["balanced"]["base"]; stress = result["balanced"]["stress"]; stress_hurdle = hurdle(stress["total_return"], stress["days"])
    passed = result["data_quality"]["status"] == "PASS" and stress_hurdle > 0 and sum(item["return"] > 0 for item in main["by_year"].values()) == len(main["by_year"]) and main["max_drawdown"] > -0.20 and main["max_drawdown"] > result["trx_half_long"]["base"]["max_drawdown"] and main["turnover"] <= 4
    payload = {"generated_at": base.utc_now(), "evaluation_content_digest": result["content_digest"], "qualification_status": "PASSED_EVALUATION_GATE" if passed else "FAILED_EVALUATION_GATE_STOP", "holdout_authorized": passed, "fixed_rule": FIXED_RULE, "stress_return_after_4pct_annual_hurdle": stress_hurdle}; write_gate(Path(args.output), payload); print(json.dumps({"status": payload["qualification_status"]}))


def command_combine(args: argparse.Namespace) -> None:
    development = base.read_json(Path(args.development)); evaluation = base.read_json(Path(args.evaluation)); gate = base.read_json(Path(args.evaluation_gate)); confirmation = base.read_json(Path(args.confirmation)); main = confirmation["balanced"]["base"]; stress = confirmation["balanced"]["stress"]; stress_hurdle = hurdle(stress["total_return"], stress["days"]); evaluation_return = evaluation["balanced"]["base"]["total_return"]; combined = (1 + evaluation_return) * (1 + main["total_return"]) - 1
    support = confirmation["data_quality"]["status"] == "PASS" and stress_hurdle > 0 and sum(item["return"] > 0 for item in main["by_year"].values()) == len(main["by_year"]) and main["max_drawdown"] > -0.15 and main["max_drawdown"] > confirmation["trx_half_long"]["base"]["max_drawdown"] and combined > 0
    conclusion = "SUPPORTS_WITHIN_SCOPE" if gate["holdout_authorized"] and support else ("DOES_NOT_SUPPORT" if main["total_return"] < 0 or combined < 0 else "INSUFFICIENT_EVIDENCE")
    payload = {"generated_at": base.utc_now(), "conclusion": conclusion, "scope": "Binance spot monthly 25% TRXUSDT plus 25% PAXGUSDT, maximum 0.5 gross", "development_balanced": development["balanced"]["base"], "evaluation_balanced": evaluation["balanced"]["base"], "confirmation_balanced": main, "confirmation_stress": stress, "confirmation_trx_half_long": confirmation["trx_half_long"]["base"], "confirmation_paxg_half_long": confirmation["paxg_half_long"]["base"], "confirmation_stress_return_after_4pct_annual_hurdle": stress_hurdle, "evaluation_confirmation_compounded_return": combined, "confirmation_support_gate": support, "formal_product_strategy_comparison": "FIXED_BACKGROUND_ONLY_DIFFERENT_MULTI_ASSET_SPOT_CONTRACT", "product_effects": "NONE"}
    payload["content_digest"] = canonical_digest({key: value for key, value in payload.items() if key != "generated_at"}); base.write_json(Path(args.output), payload); print(json.dumps({"conclusion": conclusion, "combined": combined}))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="TRX/PAXG balanced spot allocation"); sub = parser.add_subparsers(dest="command", required=True)
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
