from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


PARENT_PATH = Path(__file__).resolve().parent.parent / "xrpusdt-single-pair-continuous-cash-carry" / "study.py"
SPEC = importlib.util.spec_from_file_location("single_pair_primitives", PARENT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load retained single-pair carry primitives")
parent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(parent)
base = parent.base

SYMBOL = "SOLUSDT"
PHASES = {
    "development": ("2023-01-01T00:00:00Z", "2023-12-31T16:00:00Z", "2023-01", "2023-12"),
    "evaluation": ("2024-01-01T00:00:00Z", "2024-12-31T16:00:00Z", "2024-01", "2024-12"),
    "confirmation": ("2025-01-01T00:00:00Z", "2026-06-30T16:00:00Z", "2025-01", "2026-06"),
}
parent.SYMBOL = SYMBOL
parent.loader.UNIVERSES["xrp"] = (SYMBOL,)
FIXED_RULE = "SOLUSDT_CONTINUOUS_FULLY_FUNDED_EQUAL_QUANTITY_CASH_CARRY"


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_digest(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def command_fetch(args: argparse.Namespace) -> None:
    parent.command_fetch(args)


def command_analyze(args: argparse.Namespace) -> None:
    if args.phase != "development":
        if not args.authorization or not base.read_json(Path(args.authorization)).get("holdout_authorized"):
            raise RuntimeError("holdout is not authorized")
    start, end, start_month, end_month = PHASES[args.phase]
    manifest_path = Path(args.manifest)
    manifest = base.read_json(manifest_path)
    if manifest.get("symbols") != [SYMBOL] or manifest.get("requested_start_month") != start_month or manifest.get("requested_end_month") != end_month:
        raise RuntimeError("locked manifest scope mismatch")
    data = parent.loader.load_inputs(Path(args.cache_dir).resolve(), manifest)
    start_ms, end_ms = parent.parse_ms(start), parent.parse_ms(end)
    output = {
        "schema_version": 1,
        "generated_at": base.utc_now(),
        "phase": args.phase,
        "period": {"start": start, "end_inclusive": end},
        "symbol": SYMBOL,
        "data_quality": parent.data_quality(data[SYMBOL], start_ms, end_ms),
        "scenarios": {
            name: parent.simulate(data[SYMBOL], start_ms, end_ms, cost, 20260720 + offset)
            for offset, (name, cost) in enumerate(parent.ROUND_TRIP_COSTS.items())
        },
        "rules": {
            "position": "equal SOL quantity long spot and short USD-M perpetual continuously",
            "capital": "spot purchase plus equal futures guarantee margin; no leverage credit",
            "rebalance": "none inside phase; one modeled entry and one modeled exit",
            "round_trip_costs": parent.ROUND_TRIP_COSTS,
            "annual_capital_hurdle": parent.ANNUAL_CAPITAL_HURDLE,
        },
        "manifest_sha256": sha256_path(manifest_path),
        "manifest_content_identity": manifest["content_identity"],
        "study_code_sha256": sha256_path(Path(__file__)),
        "primitive_study_sha256": sha256_path(PARENT_PATH),
    }
    output["content_digest"] = canonical_digest({key: value for key, value in output.items() if key != "generated_at"})
    parent.write_json(Path(args.output), output)
    main = output["scenarios"]["base"]
    print(json.dumps({"phase": args.phase, "base": main["total_return_on_fully_funded_capital"], "after_hurdle": main["return_after_four_pct_annual_capital_hurdle"]}))


def gate_passed(result: dict, require_two_years: bool = False) -> bool:
    main = result["scenarios"]["base"]
    stress = result["scenarios"]["stress"]
    expected_years = {"2025", "2026"} if require_two_years else {result["period"]["start"][:4]}
    return (
        result["data_quality"]["status"] == "PASS"
        and stress["total_return_on_fully_funded_capital"] > 0
        and stress["return_after_four_pct_annual_capital_hurdle"] > 0
        and set(main["by_year"]) == expected_years
        and all(item["return_noncompounded"] > 0 for item in main["by_year"].values())
        and main["max_drawdown"] > -0.05
        and main["funding_pnl_on_initial_capital"] > abs(main["basis_pnl_on_initial_capital"])
        and main["interval_mean_block_bootstrap_95pct"][0] > 0
    )


def write_gate(path: Path, payload: dict) -> None:
    payload["content_digest"] = canonical_digest({key: value for key, value in payload.items() if key != "generated_at"})
    parent.write_json(path, payload)


def command_qualify(args: argparse.Namespace, phase: str) -> None:
    result = base.read_json(Path(args.input))
    passed = gate_passed(result)
    payload = {
        "generated_at": base.utc_now(),
        "phase": phase,
        "input_content_digest": result["content_digest"],
        "qualification_status": f"PASSED_{phase.upper()}_GATE" if passed else f"FAILED_{phase.upper()}_GATE_STOP",
        "holdout_authorized": passed,
        "fixed_rule": FIXED_RULE,
    }
    write_gate(Path(args.output), payload)
    print(json.dumps({"status": payload["qualification_status"]}))


def command_combine(args: argparse.Namespace) -> None:
    development = base.read_json(Path(args.development))
    evaluation = base.read_json(Path(args.evaluation))
    evaluation_gate = base.read_json(Path(args.evaluation_gate))
    confirmation = base.read_json(Path(args.confirmation))
    support = evaluation_gate["holdout_authorized"] and gate_passed(confirmation, require_two_years=True)
    totals = [item["scenarios"]["base"]["total_return_on_fully_funded_capital"] for item in (development, evaluation, confirmation)]
    combined = sum(totals)
    conclusion = (
        "SUPPORTS_WITHIN_SCOPE"
        if support and combined > 0
        else ("DOES_NOT_SUPPORT" if confirmation["scenarios"]["stress"]["total_return_on_fully_funded_capital"] < 0 or combined < 0 else "INSUFFICIENT_EVIDENCE")
    )
    payload = {
        "generated_at": base.utc_now(),
        "conclusion": conclusion,
        "scope": "single SOLUSDT same-venue continuous fully-funded equal-quantity spot-long/perpetual-short cash-and-carry, 2023 through 2026-06",
        "development_base": development["scenarios"]["base"],
        "evaluation_base": evaluation["scenarios"]["base"],
        "confirmation_base": confirmation["scenarios"]["base"],
        "confirmation_stress": confirmation["scenarios"]["stress"],
        "noncompounded_three_phase_return": combined,
        "confirmation_support_gate": support,
        "formal_product_strategy_comparison": "FIXED_BACKGROUND_ONLY_ECONOMICALLY_INCOMPARABLE",
        "product_effects": "NONE",
    }
    payload["content_digest"] = canonical_digest({key: value for key, value in payload.items() if key != "generated_at"})
    parent.write_json(Path(args.output), payload)
    print(json.dumps({"conclusion": conclusion, "combined": combined}))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SOLUSDT continuous cash-and-carry")
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
    analyze.add_argument("--phase", choices=tuple(PHASES), required=True)
    analyze.add_argument("--authorization")
    analyze.add_argument("--output", required=True)
    analyze.set_defaults(func=command_analyze)
    for name, phase in (("qualify-development", "development"), ("qualify-evaluation", "evaluation")):
        gate = sub.add_parser(name)
        gate.add_argument("--input", required=True)
        gate.add_argument("--output", required=True)
        gate.set_defaults(func=lambda args, fixed_phase=phase: command_qualify(args, fixed_phase))
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
