from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import statistics
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


INTERVAL_MS = 8 * 60 * 60 * 1000
INTERVALS_PER_YEAR = 365.0 * 3.0
ANNUAL_CAPITAL_HURDLE = 0.04
ROUND_TRIP_COSTS_ON_CAPITAL = {"favorable": 0.0016, "base": 0.0024, "stress": 0.0040}
PHASES = {
    "development": ("2021-01-01T00:00:00Z", "2023-01-01T00:00:00Z"),
    "evaluation": ("2023-01-01T00:00:00Z", "2025-01-01T00:00:00Z"),
    "confirmation": ("2025-01-01T00:00:00Z", "2025-09-01T00:00:00Z"),
}
EXPECTED_SOURCE_MANIFEST_SHA256 = "0bbdd5c539701e48cc8625954b68b9b0b8728df653523168ffbed093839b1ef1"
EXPECTED_CONTENT_IDENTITY = "f434978bd47792c0e74ab94dc5f0f8ad9a7a4a82618833a56602ee7802d5abd5"


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


def normalize_timestamp(value: int) -> int:
    return value // 1000 if value > 100_000_000_000_000 else value


def iter_ohlc(path: Path) -> Iterator[tuple[int, dict[str, float]]]:
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(names) != 1:
            raise RuntimeError(f"expected one CSV in {path}")
        with archive.open(names[0]) as raw:
            for row in csv.reader(line.decode("utf-8") for line in raw):
                if not row:
                    continue
                try:
                    timestamp = normalize_timestamp(int(row[0]))
                    values = {"open": float(row[1]), "high": float(row[2]), "low": float(row[3]), "close": float(row[4])}
                except ValueError:
                    continue
                yield timestamp, values


def load_inputs(cache: Path, manifest_path: Path):
    if sha256_path(manifest_path) != EXPECTED_SOURCE_MANIFEST_SHA256:
        raise RuntimeError("source manifest file identity changed")
    manifest = read_json(manifest_path)
    if manifest.get("content_identity") != EXPECTED_CONTENT_IDENTITY:
        raise RuntimeError("source manifest content identity changed")
    markets: dict[str, dict[int, dict[str, float]]] = {"spot": {}, "futures": {}}
    for item in manifest["archives"]:
        path = cache / item["cache_relative_path"]
        if sha256_path(path) != item["sha256"]:
            raise RuntimeError(f"archive identity mismatch: {path}")
        markets[item["market"]].update(iter_ohlc(path))
    funding_item = manifest["funding_snapshot"]
    funding_path = cache / funding_item["cache_relative_path"]
    if sha256_path(funding_path) != funding_item["sha256"]:
        raise RuntimeError("funding identity mismatch")
    funding = {}
    for row in read_json(funding_path):
        raw_timestamp = int(row["fundingTime"])
        boundary = ((raw_timestamp + INTERVAL_MS // 2) // INTERVAL_MS) * INTERVAL_MS
        if abs(raw_timestamp - boundary) > 1000:
            raise RuntimeError(f"funding timestamp outside 1-second boundary tolerance: {raw_timestamp}")
        if boundary in funding:
            raise RuntimeError(f"multiple funding events at normalized boundary: {boundary}")
        funding[boundary] = float(row["fundingRate"])
    return markets["spot"], markets["futures"], funding, manifest


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


def data_quality(spot, futures, funding, start_ms: int, end_ms: int) -> dict[str, object]:
    price_grid = list(range(start_ms, end_ms + INTERVAL_MS, INTERVAL_MS))
    settlement_grid = list(range(start_ms + INTERVAL_MS, end_ms + INTERVAL_MS, INTERVAL_MS))
    missing_spot = [timestamp for timestamp in price_grid if timestamp not in spot]
    missing_futures = [timestamp for timestamp in price_grid if timestamp not in futures]
    missing_funding = [timestamp for timestamp in settlement_grid if timestamp not in funding]
    unexpected_funding = [timestamp for timestamp in funding if start_ms < timestamp <= end_ms and timestamp not in set(settlement_grid)]
    invalid = 0
    for values in (spot, futures):
        for timestamp in price_grid:
            row = values.get(timestamp)
            if row is None:
                continue
            if min(row.values()) <= 0 or row["high"] < max(row["open"], row["close"]) or row["low"] > min(row["open"], row["close"]):
                invalid += 1
    passed = not (missing_spot or missing_futures or missing_funding or unexpected_funding or invalid)
    return {
        "status": "PASS" if passed else "FAIL",
        "intervals": len(settlement_grid),
        "missing_spot_rows": len(missing_spot),
        "missing_futures_rows": len(missing_futures),
        "missing_funding_settlements": len(missing_funding),
        "unexpected_non_8h_funding_events": len(unexpected_funding),
        "invalid_ohlc_rows": invalid,
    }


def simulate(spot, futures, funding, start_ms: int, end_ms: int, round_trip_cost: float, seed: int) -> dict[str, object]:
    quantity = 1.0
    initial_capital = quantity * (spot[start_ms]["open"] + futures[start_ms]["open"])
    interval_values: list[float] = []
    timestamps: list[int] = []
    basis_sum = 0.0
    funding_sum = 0.0
    worst_intrabar = 0.0
    grid = list(range(start_ms, end_ms, INTERVAL_MS))
    for index, timestamp in enumerate(grid):
        next_timestamp = timestamp + INTERVAL_MS
        basis_pnl = quantity * (
            spot[next_timestamp]["open"] - spot[timestamp]["open"]
            - futures[next_timestamp]["open"] + futures[timestamp]["open"]
        ) / initial_capital
        funding_pnl = quantity * futures[next_timestamp]["open"] * funding[next_timestamp] / initial_capital
        value = basis_pnl + funding_pnl
        if index == 0:
            value -= round_trip_cost / 2.0
        if index == len(grid) - 1:
            value -= round_trip_cost / 2.0
        interval_values.append(value)
        timestamps.append(timestamp)
        basis_sum += basis_pnl
        funding_sum += funding_pnl
        conservative_intrabar = quantity * (
            spot[timestamp]["low"] - spot[timestamp]["open"]
            - futures[timestamp]["high"] + futures[timestamp]["open"]
        ) / initial_capital
        worst_intrabar = min(worst_intrabar, conservative_intrabar)
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    yearly: dict[str, list[float]] = {}
    for timestamp, value in zip(timestamps, interval_values):
        equity += value
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity / peak - 1.0)
        year = str(datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).year)
        yearly.setdefault(year, []).append(value)
    total = sum(interval_values)
    years = len(interval_values) / INTERVALS_PER_YEAR
    hurdle = ANNUAL_CAPITAL_HURDLE * years
    spot_half = 0.5 * (spot[end_ms]["open"] / spot[start_ms]["open"] - 1.0) - round_trip_cost
    std = statistics.stdev(interval_values)
    return {
        "intervals": len(interval_values),
        "total_return_on_fully_funded_capital": total,
        "annualized_compound_equivalent": (1.0 + total) ** (1.0 / years) - 1.0 if total > -1 else None,
        "annualized_volatility_of_8h_pnl": std * math.sqrt(INTERVALS_PER_YEAR),
        "sharpe_zero_rf": statistics.fmean(interval_values) / std * math.sqrt(INTERVALS_PER_YEAR) if std else None,
        "max_drawdown": max_drawdown,
        "worst_conservative_same_bar_adverse": worst_intrabar,
        "basis_pnl_on_initial_capital": basis_sum,
        "funding_pnl_on_initial_capital": funding_sum,
        "round_trip_cost_on_initial_capital": -round_trip_cost,
        "four_pct_annual_capital_hurdle": hurdle,
        "return_after_four_pct_annual_capital_hurdle": total - hurdle,
        "half_capital_spot_long_benchmark_return": spot_half,
        "by_year": {year: {"intervals": len(values), "return_noncompounded": sum(values)} for year, values in sorted(yearly.items())},
        "interval_mean_block_bootstrap_95pct": block_bootstrap_mean(interval_values, seed),
        "pnl_digest": canonical_digest(list(zip(timestamps, interval_values))),
    }


def command_analyze(args: argparse.Namespace) -> None:
    if args.phase != "development" and (not args.authorization or not read_json(Path(args.authorization)).get("holdout_authorized")):
        raise RuntimeError("holdout is not authorized")
    spot, futures, funding, manifest = load_inputs(Path(args.cache_dir).resolve(), Path(args.source_manifest))
    start_ms, end_ms = (to_ms(value) for value in PHASES[args.phase])
    output = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "phase": args.phase,
        "period": {"start": PHASES[args.phase][0], "end_exclusive": PHASES[args.phase][1]},
        "data_quality": data_quality(spot, futures, funding, start_ms, end_ms),
        "scenarios": {
            name: simulate(spot, futures, funding, start_ms, end_ms, cost, 20260720 + index)
            for index, (name, cost) in enumerate(ROUND_TRIP_COSTS_ON_CAPITAL.items())
        },
        "rules": {
            "position": "one BTC spot long plus one BTC USD-M perpetual short; equal BTC quantity, no rebalance",
            "capital": "spot purchase plus fully funded short initial notional",
            "round_trip_costs_on_capital": ROUND_TRIP_COSTS_ON_CAPITAL,
            "annual_capital_hurdle": ANNUAL_CAPITAL_HURDLE,
            "funding": "actual event normalized within 1 second to 8h boundary; positive rate credits short",
        },
        "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
        "manifest_content_identity": manifest["content_identity"],
        "study_code_sha256": sha256_path(Path(__file__)),
    }
    output["content_digest"] = canonical_digest({key: value for key, value in output.items() if key != "generated_at"})
    write_json(Path(args.output), output)
    base = output["scenarios"]["base"]
    print(json.dumps({"phase": args.phase, "base": base["total_return_on_fully_funded_capital"], "after_hurdle": base["return_after_four_pct_annual_capital_hurdle"]}))


def gate_passed(result: dict[str, object], phase: str) -> bool:
    base = result["scenarios"]["base"]
    stress = result["scenarios"]["stress"]
    expected_years = {"2021", "2022"} if phase == "development" else {"2023", "2024"}
    return (
        result["data_quality"]["status"] == "PASS"
        and base["total_return_on_fully_funded_capital"] > 0
        and stress["total_return_on_fully_funded_capital"] > 0
        and stress["return_after_four_pct_annual_capital_hurdle"] > 0
        and set(base["by_year"]) == expected_years
        and all(item["return_noncompounded"] > 0 for item in base["by_year"].values())
        and base["max_drawdown"] > -0.08
        and base["funding_pnl_on_initial_capital"] > abs(base["basis_pnl_on_initial_capital"])
    )


def command_qualify(args: argparse.Namespace, phase: str) -> None:
    result = read_json(Path(args.input))
    passed = gate_passed(result, phase)
    output = {
        "generated_at": utc_now(),
        "phase": phase,
        "input_content_digest": result["content_digest"],
        "qualification_status": f"PASSED_{phase.upper()}_GATE" if passed else f"FAILED_{phase.upper()}_GATE_STOP",
        "holdout_authorized": passed,
        "fixed_rule": "BTCUSDT_CONTINUOUS_EQUAL_QUANTITY_SPOT_LONG_PERP_SHORT_FULLY_FUNDED",
    }
    output["content_digest"] = canonical_digest({key: value for key, value in output.items() if key != "generated_at"})
    write_json(Path(args.output), output)
    print(json.dumps({"status": output["qualification_status"]}))


def command_combine(args: argparse.Namespace) -> None:
    development = read_json(Path(args.development))
    evaluation = read_json(Path(args.evaluation))
    evaluation_gate = read_json(Path(args.evaluation_gate))
    confirmation = read_json(Path(args.confirmation))
    base = confirmation["scenarios"]["base"]
    stress = confirmation["scenarios"]["stress"]
    combined = evaluation["scenarios"]["base"]["total_return_on_fully_funded_capital"] + base["total_return_on_fully_funded_capital"]
    support = (
        evaluation_gate["holdout_authorized"]
        and confirmation["data_quality"]["status"] == "PASS"
        and base["total_return_on_fully_funded_capital"] > 0
        and stress["total_return_on_fully_funded_capital"] > 0
        and stress["return_after_four_pct_annual_capital_hurdle"] > 0
        and base["max_drawdown"] > -0.08
        and base["funding_pnl_on_initial_capital"] > abs(base["basis_pnl_on_initial_capital"])
        and combined > 0
    )
    if support:
        conclusion = "SUPPORTS_WITHIN_SCOPE"
    elif base["total_return_on_fully_funded_capital"] < 0 or combined < 0:
        conclusion = "DOES_NOT_SUPPORT"
    else:
        conclusion = "INSUFFICIENT_EVIDENCE"
    output = {
        "generated_at": utc_now(),
        "conclusion": conclusion,
        "scope": "continuous equal-BTC-quantity BTCUSDT spot long/perpetual short, fully funded, through 2025-08",
        "development_base": development["scenarios"]["base"],
        "evaluation_base": evaluation["scenarios"]["base"],
        "confirmation_base": base,
        "confirmation_stress": stress,
        "evaluation_confirmation_noncompounded_return": combined,
        "support_gate": support,
        "formal_product_strategy_comparison": "FIXED_BACKGROUND_ONLY_NO_COMPARABLE_ACTIVATION_REPLAY",
        "product_effects": "NONE",
    }
    output["content_digest"] = canonical_digest({key: value for key, value in output.items() if key != "generated_at"})
    write_json(Path(args.output), output)
    print(json.dumps({"conclusion": conclusion, "confirmation": base["total_return_on_fully_funded_capital"]}))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BTCUSDT continuous fully-funded cash-and-carry study")
    sub = parser.add_subparsers(dest="command", required=True)
    analyze = sub.add_parser("analyze")
    analyze.add_argument("--cache-dir", required=True)
    analyze.add_argument("--source-manifest", required=True)
    analyze.add_argument("--phase", choices=tuple(PHASES), required=True)
    analyze.add_argument("--authorization")
    analyze.add_argument("--output", required=True)
    analyze.set_defaults(func=command_analyze)
    for name, phase in (("qualify-development", "development"), ("qualify-evaluation", "evaluation")):
        qualify = sub.add_parser(name)
        qualify.add_argument("--input", required=True)
        qualify.add_argument("--output", required=True)
        qualify.set_defaults(func=lambda args, fixed_phase=phase: command_qualify(args, fixed_phase))
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
