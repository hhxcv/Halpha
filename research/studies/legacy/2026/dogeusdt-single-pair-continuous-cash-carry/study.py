from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


PARENT_PATH = Path(__file__).resolve().parent.parent / "xrpusdt-single-pair-continuous-cash-carry" / "study.py"
SPEC = importlib.util.spec_from_file_location("single_pair_parent", PARENT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load retained single-pair carry study")
parent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(parent)
base = parent.base

SYMBOL = "DOGEUSDT"
parent.SYMBOL = SYMBOL
parent.loader.UNIVERSES["xrp"] = (SYMBOL,)
# Make delegated analysis bind its reported code identity to this locked wrapper.
parent.__file__ = str(Path(__file__).resolve())


def canonical_digest(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def command_fetch(args: argparse.Namespace) -> None:
    parent.command_fetch(args)


def command_analyze(args: argparse.Namespace) -> None:
    parent.command_analyze(args)


def command_conclude(args: argparse.Namespace) -> None:
    result = base.read_json(Path(args.confirmation))
    main = result["scenarios"]["base"]
    stress = result["scenarios"]["stress"]
    support = (
        result["data_quality"]["status"] == "PASS"
        and stress["total_return_on_fully_funded_capital"] > 0
        and stress["return_after_four_pct_annual_capital_hurdle"] > 0
        and set(main["by_year"]) == {"2025", "2026"}
        and all(item["return_noncompounded"] > 0 for item in main["by_year"].values())
        and main["max_drawdown"] > -0.05
        and main["funding_pnl_on_initial_capital"] > abs(main["basis_pnl_on_initial_capital"])
        and main["interval_mean_block_bootstrap_95pct"][0] > 0
    )
    conclusion = (
        "SUPPORTS_WITHIN_SCOPE"
        if support
        else ("DOES_NOT_SUPPORT" if stress["total_return_on_fully_funded_capital"] < 0 else "INSUFFICIENT_EVIDENCE")
    )
    payload = {
        "generated_at": base.utc_now(),
        "conclusion": conclusion,
        "scope": "single DOGEUSDT same-venue continuous fully-funded equal-quantity spot-long/perpetual-short cash-and-carry, 2025-09 through 2026-06",
        "inherited_exposed_evidence": {
            "source_candidate": "DOGE_XRP_ADA_EQUAL_CAPITAL_CONTINUOUS_CASH_CARRY_BASKET",
            "2021_2022_doge_base_return": 6.763318705029634,
            "2023_doge_base_return": 0.053936554634059504,
            "2024_to_2025_aug_doge_base_return": 0.18424283516858397,
            "selection_status": "EXPOSED_CONTEXT_NOT_COUNTED_AS_FRESH_CONFIRMATION"
        },
        "fresh_confirmation_base": main,
        "fresh_confirmation_stress": stress,
        "fresh_confirmation_support_gate": support,
        "formal_product_strategy_comparison": "FIXED_BACKGROUND_ONLY_ECONOMICALLY_INCOMPARABLE",
        "product_effects": "NONE",
    }
    payload["content_digest"] = canonical_digest({key: value for key, value in payload.items() if key != "generated_at"})
    parent.write_json(Path(args.output), payload)
    print(json.dumps({"conclusion": conclusion, "support": support}))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Single-pair DOGE continuous cash-and-carry follow-up")
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
    analyze.add_argument("--output", required=True)
    analyze.set_defaults(func=command_analyze)
    conclude = sub.add_parser("conclude")
    conclude.add_argument("--confirmation", required=True)
    conclude.add_argument("--output", required=True)
    conclude.set_defaults(func=command_conclude)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
