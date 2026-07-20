from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


BASE_PATH = Path(__file__).resolve().parent.parent / "core-perp-volscaled-tsmom" / "study.py"
SPEC = importlib.util.spec_from_file_location("core_tsmom_base", BASE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load retained core TSMOM study")
base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)

EXPECTED_BASE_SHA256 = "aca8bcce736a7452d29e2ef01c76d32f4c7de92e1a4d541f9d0711bc6f0437fa"
ASSET_RISK_BUDGET = 0.03
MAX_ASSET_WEIGHT = 0.10
MAX_GROSS = 0.30
base.ASSET_RISK_BUDGET = ASSET_RISK_BUDGET
base.MAX_ASSET_WEIGHT = MAX_ASSET_WEIGHT
base.MAX_GROSS = MAX_GROSS
base.__file__ = __file__


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_base() -> None:
    if sha256_path(BASE_PATH) != EXPECTED_BASE_SHA256:
        raise RuntimeError("retained base study identity changed")


def command_fetch(args: argparse.Namespace) -> None:
    ensure_base(); base.command_fetch(args)


def command_analyze(args: argparse.Namespace) -> None:
    ensure_base(); base.command_analyze(args)


def gate_passed(result: dict[str, object], phase: str) -> bool:
    primary = result["strategy"][str(base.PRIMARY_LOOKBACK)]; main = primary["base"]; benchmark = result["continuous_half_long_benchmark"]["base"]
    diagnostics = [result["strategy"][str(window)]["base"]["total_return"] for window in base.LOOKBACKS]
    expected = {"2021", "2022"} if phase == "development" else {"2023", "2024"}
    return result["data_quality"]["status"] == "PASS" and main["total_return"] > 0 and primary["stress"]["total_return"] > 0 and set(main["by_year"]) == expected and all(item["return"] > 0 for item in main["by_year"].values()) and main["max_drawdown"] > (-0.20 if phase == "development" else -0.18) and main["max_drawdown"] >= benchmark["max_drawdown"] - 0.02 and main["worst_daily_intrabar_adverse_on_then_nav"] > -0.15 and sum(value > 0 for value in diagnostics) >= 2 and main["turnover"] <= 30


def command_qualify(args: argparse.Namespace, phase: str) -> None:
    ensure_base(); result = base.read_json(Path(args.input)); passed = gate_passed(result, phase)
    output = {
        "generated_at": base.utc_now(), "phase": phase, "input_content_digest": result["content_digest"],
        "qualification_status": f"PASSED_{phase.upper()}_GATE" if passed else f"FAILED_{phase.upper()}_GATE_STOP",
        "holdout_authorized": passed,
        "fixed_rule": "BTC_ETH_BNB_MONTHLY_180D_TSMOM_60D_VOLSCALED_MAX_0P3X",
    }
    output["content_digest"] = base.canonical_digest({key: value for key, value in output.items() if key != "generated_at"})
    base.write_json(Path(args.output), output); print(json.dumps({"status": output["qualification_status"]}))


def command_combine(args: argparse.Namespace) -> None:
    ensure_base()
    development = base.read_json(Path(args.development)); evaluation = base.read_json(Path(args.evaluation)); confirmation = base.read_json(Path(args.confirmation)); gate = base.read_json(Path(args.evaluation_gate))
    primary = confirmation["strategy"][str(base.PRIMARY_LOOKBACK)]; main = primary["base"]; benchmark = confirmation["continuous_half_long_benchmark"]["base"]
    diagnostics = [confirmation["strategy"][str(window)]["base"]["total_return"] for window in base.LOOKBACKS]
    combined = (1.0 + evaluation["strategy"][str(base.PRIMARY_LOOKBACK)]["base"]["total_return"]) * (1.0 + main["total_return"]) - 1.0
    support = gate["holdout_authorized"] and confirmation["data_quality"]["status"] == "PASS" and main["total_return"] > 0 and primary["stress"]["total_return"] > 0 and set(main["by_year"]) == {"2025", "2026"} and all(item["return"] > 0 for item in main["by_year"].values()) and main["max_drawdown"] > -0.18 and main["max_drawdown"] >= benchmark["max_drawdown"] - 0.02 and main["worst_daily_intrabar_adverse_on_then_nav"] > -0.15 and sum(value >= 0 for value in diagnostics) >= 2 and combined > 0
    conclusion = "SUPPORTS_WITHIN_SCOPE" if support else ("DOES_NOT_SUPPORT" if main["total_return"] < 0 or combined < 0 else "INSUFFICIENT_EVIDENCE")
    output = {
        "generated_at": base.utc_now(), "conclusion": conclusion,
        "scope": "BTC/ETH/BNB monthly 180d TSMOM, 60d volatility scaling, 3% risk budget per asset, max 0.3x gross, through 2026-06-29",
        "development": development["strategy"][str(base.PRIMARY_LOOKBACK)]["base"],
        "evaluation": evaluation["strategy"][str(base.PRIMARY_LOOKBACK)]["base"],
        "confirmation": main, "confirmation_stress": primary["stress"],
        "confirmation_robustness_returns": {str(window): diagnostics[index] for index, window in enumerate(base.LOOKBACKS)},
        "confirmation_continuous_long_benchmark": benchmark,
        "evaluation_confirmation_compounded_return": combined, "support_gate": support,
        "formal_product_strategy_comparison": "FIXED_BACKGROUND_ONLY_NO_IDENTICAL_ACTIVATION_REPLAY", "product_effects": "NONE",
    }
    output["content_digest"] = base.canonical_digest({key: value for key, value in output.items() if key != "generated_at"})
    base.write_json(Path(args.output), output); print(json.dumps({"conclusion": conclusion, "confirmation": main["total_return"]}))


def build_parser():
    parser = argparse.ArgumentParser(description="Conservative core-perpetual volatility-scaled TSMOM follow-up"); sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch"); fetch.add_argument("--cache-dir", required=True); fetch.add_argument("--start-month", required=True); fetch.add_argument("--end-month", required=True); fetch.add_argument("--manifest", required=True); fetch.set_defaults(func=command_fetch)
    analyze = sub.add_parser("analyze"); analyze.add_argument("--cache-dir", required=True); analyze.add_argument("--manifest", required=True); analyze.add_argument("--phase", choices=tuple(base.PHASES), required=True); analyze.add_argument("--authorization"); analyze.add_argument("--output", required=True); analyze.set_defaults(func=command_analyze)
    for name, phase in (("qualify-development", "development"), ("qualify-evaluation", "evaluation")):
        qualify = sub.add_parser(name); qualify.add_argument("--input", required=True); qualify.add_argument("--output", required=True); qualify.set_defaults(func=lambda args, fixed_phase=phase: command_qualify(args, fixed_phase))
    combine = sub.add_parser("combine"); combine.add_argument("--development", required=True); combine.add_argument("--evaluation", required=True); combine.add_argument("--evaluation-gate", required=True); combine.add_argument("--confirmation", required=True); combine.add_argument("--output", required=True); combine.set_defaults(func=command_combine)
    return parser


def main():
    args = build_parser().parse_args(); args.func(args)


if __name__ == "__main__":
    main()
