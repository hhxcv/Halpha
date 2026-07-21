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


BASE_PATH = Path(__file__).resolve().parent.parent / "multi-asset-persistent-funding-carry" / "study.py"
SPEC = importlib.util.spec_from_file_location("persistent_carry_source", BASE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load retained public-data loader")
base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)

SYMBOLS = ("DOGEUSDT", "XRPUSDT", "ADAUSDT")
INTERVAL_MS = 8 * 60 * 60 * 1000
INTERVALS_PER_YEAR = 365.0 * 3.0
ANNUAL_CAPITAL_HURDLE = 0.04
ROUND_TRIP_COSTS = {"favorable": 0.0016, "base": 0.0024, "stress": 0.0040}
PHASES = {
    "development": ("2021-01-01T00:00:00Z", "2023-01-01T00:00:00Z"),
    "evaluation": ("2023-01-01T00:00:00Z", "2023-12-31T16:00:00Z"),
    "confirmation": ("2024-01-01T00:00:00Z", "2025-09-01T00:00:00Z"),
}
EXPECTED_DEVELOPMENT_MANIFEST_SHA256 = "19525c87fe169cdd99e5a4f7830fd6a2dc07ad2a72d37e0236d8ac4b3d5538cd"
EXPECTED_DEVELOPMENT_CONTENT_IDENTITY = "1587d2f2505177db808e915a5a83dd1b4d35991e6f9588cf4dd95adcdb438609"
EXPECTED_LOADER_SHA256 = "41408a2b75718132153c0c5338273a4898146ae9f1a28d267eeb4f0c2b1ab2e7"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def to_ms(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_digest(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def block_bootstrap_mean(values: list[float], seed: int, block: int = 9, reps: int = 4000):
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


def validate_manifest(manifest_path: Path, phase: str) -> dict[str, object]:
    if sha256_path(BASE_PATH) != EXPECTED_LOADER_SHA256:
        raise RuntimeError("retained loader identity changed")
    manifest = read_json(manifest_path)
    if tuple(manifest.get("symbols", ())) != SYMBOLS or manifest.get("universe") != "core" or manifest.get("interval") != "8h":
        raise RuntimeError("manifest universe mismatch")
    if phase in {"development", "evaluation"}:
        if sha256_path(manifest_path) != EXPECTED_DEVELOPMENT_MANIFEST_SHA256 or manifest.get("content_identity") != EXPECTED_DEVELOPMENT_CONTENT_IDENTITY:
            raise RuntimeError("development manifest identity changed")
    else:
        if manifest.get("requested_start_month") != "2024-01" or manifest.get("requested_end_month") != "2025-09":
            raise RuntimeError("confirmation manifest period mismatch")
    return manifest


def data_quality(data, start_ms: int, end_ms: int) -> dict[str, object]:
    price_grid = list(range(start_ms, end_ms + INTERVAL_MS, INTERVAL_MS))
    settlement_grid = list(range(start_ms + INTERVAL_MS, end_ms + INTERVAL_MS, INTERVAL_MS))
    details = {}
    passed = True
    for symbol in SYMBOLS:
        missing_spot = sum(timestamp not in data[symbol]["spot"] for timestamp in price_grid)
        missing_futures = sum(timestamp not in data[symbol]["futures"] for timestamp in price_grid)
        missing_funding = sum(timestamp not in data[symbol]["funding"] for timestamp in settlement_grid)
        status = "PASS" if missing_spot == missing_futures == missing_funding == 0 else "FAIL"
        passed = passed and status == "PASS"
        details[symbol] = {
            "status": status,
            "intervals": len(settlement_grid),
            "missing_spot_rows": missing_spot,
            "missing_futures_rows": missing_futures,
            "missing_funding_settlements": missing_funding,
        }
    return {"status": "PASS" if passed else "FAIL", "symbols": details}


def asset_interval_pnl(item, start_ms: int, end_ms: int):
    capital = item["spot"][start_ms] + item["futures"][start_ms]
    basis, funding = [], []
    for timestamp in range(start_ms, end_ms, INTERVAL_MS):
        next_timestamp = timestamp + INTERVAL_MS
        basis.append((
            item["spot"][next_timestamp] - item["spot"][timestamp]
            - item["futures"][next_timestamp] + item["futures"][timestamp]
        ) / capital)
        funding.append(item["futures"][next_timestamp] * item["funding"][next_timestamp] / capital)
    return basis, funding


def simulate(data, start_ms: int, end_ms: int, round_trip_cost: float, seed: int) -> dict[str, object]:
    components = {symbol: asset_interval_pnl(data[symbol], start_ms, end_ms) for symbol in SYMBOLS}
    timestamps = list(range(start_ms, end_ms, INTERVAL_MS))
    values, basis_values, funding_values = [], [], []
    per_asset = {}
    for symbol in SYMBOLS:
        asset_raw = [left + right for left, right in zip(*components[symbol])]
        per_asset[symbol] = sum(asset_raw) - round_trip_cost
    for index, timestamp in enumerate(timestamps):
        basis_value = statistics.fmean(components[symbol][0][index] for symbol in SYMBOLS)
        funding_value = statistics.fmean(components[symbol][1][index] for symbol in SYMBOLS)
        value = basis_value + funding_value
        if index == 0:
            value -= round_trip_cost / 2.0
        if index == len(timestamps) - 1:
            value -= round_trip_cost / 2.0
        basis_values.append(basis_value)
        funding_values.append(funding_value)
        values.append(value)
    equity, peak, max_drawdown = 1.0, 1.0, 0.0
    yearly: dict[str, list[float]] = {}
    for timestamp, value in zip(timestamps, values):
        equity += value
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity / peak - 1.0)
        yearly.setdefault(str(datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).year), []).append(value)
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
        "per_asset_total_return": per_asset,
        "positive_asset_count": sum(value > 0 for value in per_asset.values()),
        "by_year": {year: {"intervals": len(items), "return_noncompounded": sum(items)} for year, items in sorted(yearly.items())},
        "interval_mean_block_bootstrap_95pct": block_bootstrap_mean(values, seed),
        "pnl_digest": canonical_digest(list(zip(timestamps, values))),
    }


def command_analyze(args: argparse.Namespace) -> None:
    if args.phase != "development" and (not args.authorization or not read_json(Path(args.authorization)).get("holdout_authorized")):
        raise RuntimeError("holdout is not authorized")
    manifest = validate_manifest(Path(args.manifest), args.phase)
    data = base.load_inputs(Path(args.cache_dir).resolve(), manifest)
    start_ms, end_ms = (to_ms(value) for value in PHASES[args.phase])
    output = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "phase": args.phase,
        "period": {"start": PHASES[args.phase][0], "end_exclusive": PHASES[args.phase][1]},
        "symbols": list(SYMBOLS),
        "data_quality": data_quality(data, start_ms, end_ms),
        "scenarios": {name: simulate(data, start_ms, end_ms, cost, 20260720 + index) for index, (name, cost) in enumerate(ROUND_TRIP_COSTS.items())},
        "rules": {
            "allocation": "equal one-third capital to each independent equal-quantity spot-long/perpetual-short pair",
            "rebalance": "none inside phase",
            "round_trip_costs": ROUND_TRIP_COSTS,
            "annual_capital_hurdle": ANNUAL_CAPITAL_HURDLE,
        },
        "manifest_sha256": sha256_path(Path(args.manifest)),
        "manifest_content_identity": manifest["content_identity"],
        "study_code_sha256": sha256_path(Path(__file__)),
        "loader_sha256": sha256_path(BASE_PATH),
    }
    output["content_digest"] = canonical_digest({key: value for key, value in output.items() if key != "generated_at"})
    write_json(Path(args.output), output)
    main = output["scenarios"]["base"]
    print(json.dumps({"phase": args.phase, "base": main["total_return_on_fully_funded_capital"], "after_hurdle": main["return_after_four_pct_annual_capital_hurdle"]}))


def gate_passed(result: dict[str, object], phase: str) -> bool:
    base_result = result["scenarios"]["base"]
    stress = result["scenarios"]["stress"]
    expected_years = {"2021", "2022"} if phase == "development" else {"2023"}
    return (
        result["data_quality"]["status"] == "PASS"
        and stress["total_return_on_fully_funded_capital"] > 0
        and stress["return_after_four_pct_annual_capital_hurdle"] > 0
        and set(base_result["by_year"]) == expected_years
        and all(item["return_noncompounded"] > 0 for item in base_result["by_year"].values())
        and base_result["positive_asset_count"] >= (3 if phase == "development" else 2)
        and base_result["max_drawdown"] > -0.10
        and base_result["funding_pnl_on_initial_capital"] > abs(base_result["basis_pnl_on_initial_capital"])
    )


def command_qualify(args: argparse.Namespace, phase: str) -> None:
    result = read_json(Path(args.input))
    passed = gate_passed(result, phase)
    output = {
        "generated_at": utc_now(), "phase": phase, "input_content_digest": result["content_digest"],
        "qualification_status": f"PASSED_{phase.upper()}_GATE" if passed else f"FAILED_{phase.upper()}_GATE_STOP",
        "holdout_authorized": passed,
        "fixed_rule": "DOGE_XRP_ADA_EQUAL_CAPITAL_CONTINUOUS_CASH_CARRY_BASKET",
    }
    output["content_digest"] = canonical_digest({key: value for key, value in output.items() if key != "generated_at"})
    write_json(Path(args.output), output)
    print(json.dumps({"status": output["qualification_status"]}))


def command_combine(args: argparse.Namespace) -> None:
    development = read_json(Path(args.development)); evaluation = read_json(Path(args.evaluation)); confirmation = read_json(Path(args.confirmation)); gate = read_json(Path(args.evaluation_gate))
    main = confirmation["scenarios"]["base"]; stress = confirmation["scenarios"]["stress"]
    combined = evaluation["scenarios"]["base"]["total_return_on_fully_funded_capital"] + main["total_return_on_fully_funded_capital"]
    support = (
        gate["holdout_authorized"] and confirmation["data_quality"]["status"] == "PASS"
        and stress["total_return_on_fully_funded_capital"] > 0
        and stress["return_after_four_pct_annual_capital_hurdle"] > 0
        and set(main["by_year"]) == {"2024", "2025"}
        and all(item["return_noncompounded"] > 0 for item in main["by_year"].values())
        and main["positive_asset_count"] >= 2
        and main["max_drawdown"] > -0.10
        and main["funding_pnl_on_initial_capital"] > abs(main["basis_pnl_on_initial_capital"])
        and combined > 0
    )
    if support:
        conclusion = "SUPPORTS_WITHIN_SCOPE"
    elif main["total_return_on_fully_funded_capital"] < 0 or combined < 0:
        conclusion = "DOES_NOT_SUPPORT"
    else:
        conclusion = "INSUFFICIENT_EVIDENCE"
    output = {
        "generated_at": utc_now(), "conclusion": conclusion,
        "scope": "equal-capital DOGE/XRP/ADA continuous fully-funded same-venue cash-and-carry basket through 2025-08",
        "development_base": development["scenarios"]["base"], "evaluation_base": evaluation["scenarios"]["base"],
        "confirmation_base": main, "confirmation_stress": stress,
        "evaluation_confirmation_noncompounded_return": combined, "support_gate": support,
        "formal_product_strategy_comparison": "FIXED_BACKGROUND_ONLY_NO_COMPARABLE_ACTIVATION_REPLAY", "product_effects": "NONE",
    }
    output["content_digest"] = canonical_digest({key: value for key, value in output.items() if key != "generated_at"})
    write_json(Path(args.output), output)
    print(json.dumps({"conclusion": conclusion, "confirmation": main["total_return_on_fully_funded_capital"]}))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mature-alt continuous cash-and-carry basket")
    sub = parser.add_subparsers(dest="command", required=True)
    analyze = sub.add_parser("analyze"); analyze.add_argument("--cache-dir", required=True); analyze.add_argument("--manifest", required=True); analyze.add_argument("--phase", choices=tuple(PHASES), required=True); analyze.add_argument("--authorization"); analyze.add_argument("--output", required=True); analyze.set_defaults(func=command_analyze)
    for name, phase in (("qualify-development", "development"), ("qualify-evaluation", "evaluation")):
        qualify = sub.add_parser(name); qualify.add_argument("--input", required=True); qualify.add_argument("--output", required=True); qualify.set_defaults(func=lambda args, fixed_phase=phase: command_qualify(args, fixed_phase))
    combine = sub.add_parser("combine"); combine.add_argument("--development", required=True); combine.add_argument("--evaluation", required=True); combine.add_argument("--evaluation-gate", required=True); combine.add_argument("--confirmation", required=True); combine.add_argument("--output", required=True); combine.set_defaults(func=command_combine)
    return parser


def main() -> None:
    args = build_parser().parse_args(); args.func(args)


if __name__ == "__main__":
    main()
