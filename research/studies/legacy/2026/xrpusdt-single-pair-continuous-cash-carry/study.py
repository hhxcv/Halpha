from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import random
import statistics
from datetime import datetime, timezone
from pathlib import Path


LOADER_PATH = Path(__file__).resolve().parent.parent / "multi-asset-persistent-funding-carry" / "study.py"
SPEC = importlib.util.spec_from_file_location("public_carry_loader", LOADER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load retained public spot/perpetual loader")
loader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(loader)
base = loader.base

SYMBOL = "XRPUSDT"
INTERVAL_MS = 8 * 60 * 60 * 1000
INTERVALS_PER_YEAR = 365.0 * 3.0
START = "2025-09-01T00:00:00Z"
END = "2026-06-30T16:00:00Z"
ROUND_TRIP_COSTS = {"favorable": 0.0016, "base": 0.0024, "stress": 0.0040}
ANNUAL_CAPITAL_HURDLE = 0.04
loader.UNIVERSES["xrp"] = (SYMBOL,)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_digest(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def block_bootstrap_mean(values: list[float], seed: int, block: int = 9, reps: int = 4000) -> list[float]:
    rng = random.Random(seed)
    count = len(values)
    means = []
    for _ in range(reps):
        sample = []
        while len(sample) < count:
            start = rng.randrange(count)
            sample.extend(values[(start + offset) % count] for offset in range(block))
        means.append(statistics.fmean(sample[:count]))
    means.sort()
    return [means[int(reps * 0.025)], means[int(reps * 0.975) - 1]]


def parse_ms(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def data_quality(item: dict, start_ms: int, end_ms: int) -> dict:
    price_grid = set(range(start_ms, end_ms + INTERVAL_MS, INTERVAL_MS))
    funding_grid = set(range(start_ms + INTERVAL_MS, end_ms + INTERVAL_MS, INTERVAL_MS))
    missing_spot = sorted(price_grid - set(item["spot"]))
    missing_futures = sorted(price_grid - set(item["futures"]))
    missing_funding = sorted(funding_grid - set(item["funding"]))
    passed = not missing_spot and not missing_futures and not missing_funding
    return {
        "status": "PASS" if passed else "FAIL",
        "intervals": len(funding_grid),
        "missing_spot_rows": len(missing_spot),
        "missing_futures_rows": len(missing_futures),
        "missing_funding_settlements": len(missing_funding),
    }


def simulate(item: dict, start_ms: int, end_ms: int, round_trip_cost: float, seed: int) -> dict:
    capital = item["spot"][start_ms] + item["futures"][start_ms]
    timestamps = list(range(start_ms, end_ms, INTERVAL_MS))
    values, basis_values, funding_values = [], [], []
    for index, timestamp in enumerate(timestamps):
        next_timestamp = timestamp + INTERVAL_MS
        basis = (
            item["spot"][next_timestamp] - item["spot"][timestamp]
            - item["futures"][next_timestamp] + item["futures"][timestamp]
        ) / capital
        funding = item["futures"][next_timestamp] * item["funding"][next_timestamp] / capital
        value = basis + funding
        if index == 0:
            value -= round_trip_cost / 2.0
        if index == len(timestamps) - 1:
            value -= round_trip_cost / 2.0
        basis_values.append(basis)
        funding_values.append(funding)
        values.append(value)
    equity, peak, max_drawdown = 1.0, 1.0, 0.0
    by_year: dict[str, list[float]] = {}
    for timestamp, value in zip(timestamps, values):
        equity += value
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity / peak - 1.0)
        year = str(datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).year)
        by_year.setdefault(year, []).append(value)
    total = sum(values)
    years = len(values) / INTERVALS_PER_YEAR
    std = statistics.stdev(values)
    hurdle = ANNUAL_CAPITAL_HURDLE * years
    return {
        "intervals": len(values),
        "total_return_on_fully_funded_capital": total,
        "annualized_compound_equivalent": (1.0 + total) ** (1.0 / years) - 1.0 if total > -1 else None,
        "annualized_volatility_of_8h_pnl": std * math.sqrt(INTERVALS_PER_YEAR),
        "sharpe_zero_rf": statistics.fmean(values) / std * math.sqrt(INTERVALS_PER_YEAR) if std else None,
        "max_drawdown": max_drawdown,
        "basis_pnl_on_initial_capital": sum(basis_values),
        "funding_pnl_on_initial_capital": sum(funding_values),
        "round_trip_cost_on_initial_capital": -round_trip_cost,
        "four_pct_annual_capital_hurdle": hurdle,
        "return_after_four_pct_annual_capital_hurdle": total - hurdle,
        "by_year": {year: {"intervals": len(items), "return_noncompounded": sum(items)} for year, items in sorted(by_year.items())},
        "interval_mean_block_bootstrap_95pct": block_bootstrap_mean(values, seed),
        "pnl_digest": canonical_digest(list(zip(timestamps, values))),
    }


def command_fetch(args: argparse.Namespace) -> None:
    delegated = argparse.Namespace(
        cache_dir=args.cache_dir,
        universe="xrp",
        start_month=args.start_month,
        end_month=args.end_month,
        manifest=args.manifest,
    )
    loader.command_fetch(delegated)


def command_analyze(args: argparse.Namespace) -> None:
    manifest_path = Path(args.manifest)
    manifest = base.read_json(manifest_path)
    if manifest.get("symbols") != [SYMBOL] or manifest.get("requested_start_month") != "2025-09" or manifest.get("requested_end_month") != "2026-06":
        raise RuntimeError("locked manifest scope mismatch")
    data = loader.load_inputs(Path(args.cache_dir).resolve(), manifest)
    start_ms, end_ms = parse_ms(START), parse_ms(END)
    output = {
        "schema_version": 1,
        "generated_at": base.utc_now(),
        "period": {"start": START, "end_inclusive": END},
        "symbol": SYMBOL,
        "data_quality": data_quality(data[SYMBOL], start_ms, end_ms),
        "scenarios": {
            name: simulate(data[SYMBOL], start_ms, end_ms, cost, 20260720 + offset)
            for offset, (name, cost) in enumerate(ROUND_TRIP_COSTS.items())
        },
        "rules": {
            "position": "equal XRP quantity long spot and short USD-M perpetual continuously",
            "capital": "spot purchase plus equal futures guarantee margin; no leverage credit",
            "rebalance": "none inside phase; one modeled entry and one modeled exit",
            "round_trip_costs": ROUND_TRIP_COSTS,
            "annual_capital_hurdle": ANNUAL_CAPITAL_HURDLE,
        },
        "manifest_sha256": sha256_path(manifest_path),
        "manifest_content_identity": manifest["content_identity"],
        "study_code_sha256": sha256_path(Path(__file__)),
        "loader_sha256": sha256_path(LOADER_PATH),
    }
    output["content_digest"] = canonical_digest({key: value for key, value in output.items() if key != "generated_at"})
    write_json(Path(args.output), output)
    main = output["scenarios"]["base"]
    print(json.dumps({"base": main["total_return_on_fully_funded_capital"], "after_hurdle": main["return_after_four_pct_annual_capital_hurdle"]}))


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
        "scope": "single XRPUSDT same-venue continuous fully-funded equal-quantity spot-long/perpetual-short cash-and-carry, 2025-09 through 2026-06",
        "inherited_exposed_evidence": {
            "source_candidate": "DOGE_XRP_ADA_EQUAL_CAPITAL_CONTINUOUS_CASH_CARRY_BASKET",
            "2021_2022_xrp_base_return": 0.9208230887137557,
            "2023_xrp_base_return": 0.06418328209206224,
            "2024_to_2025_aug_xrp_base_return": 0.14704667409031838,
            "selection_status": "EXPOSED_CONTEXT_NOT_COUNTED_AS_FRESH_CONFIRMATION"
        },
        "fresh_confirmation_base": main,
        "fresh_confirmation_stress": stress,
        "fresh_confirmation_support_gate": support,
        "formal_product_strategy_comparison": "FIXED_BACKGROUND_ONLY_ECONOMICALLY_INCOMPARABLE",
        "product_effects": "NONE",
    }
    payload["content_digest"] = canonical_digest({key: value for key, value in payload.items() if key != "generated_at"})
    write_json(Path(args.output), payload)
    print(json.dumps({"conclusion": conclusion, "support": support}))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Single-pair XRP continuous cash-and-carry follow-up")
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
