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
DAY_MS = 24 * 60 * 60 * 1000
LOOKBACKS = (60, 90, 180)
MAX_ABS_WEIGHT = 0.25
ENSEMBLE_COMPONENT_WEIGHT = MAX_ABS_WEIGHT / len(LOOKBACKS)
COSTS = {"favorable": 0.0008, "base": 0.0016, "stress": 0.0028}
PHASES = {
    "development": ("2021-07-01T00:00:00Z", "2023-01-01T00:00:00Z"),
    "evaluation": ("2023-01-01T00:00:00Z", "2025-01-01T00:00:00Z"),
    "confirmation": ("2025-01-01T00:00:00Z", "2025-09-01T00:00:00Z"),
}
EXPECTED_SOURCE_MANIFEST_SHA256 = "0bbdd5c539701e48cc8625954b68b9b0b8728df653523168ffbed093839b1ef1"
EXPECTED_CONTENT_IDENTITY = "f434978bd47792c0e74ab94dc5f0f8ad9a7a4a82618833a56602ee7802d5abd5"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def to_ms(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def iso_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


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
                    values = {
                        "open": float(row[1]),
                        "high": float(row[2]),
                        "low": float(row[3]),
                        "close": float(row[4]),
                    }
                except ValueError:
                    continue
                yield timestamp, values


def load_inputs(cache: Path, manifest_path: Path):
    if sha256_path(manifest_path) != EXPECTED_SOURCE_MANIFEST_SHA256:
        raise RuntimeError("source manifest file identity changed")
    manifest = read_json(manifest_path)
    if manifest.get("content_identity") != EXPECTED_CONTENT_IDENTITY:
        raise RuntimeError("source manifest content identity changed")
    if manifest.get("symbol") != "BTCUSDT" or manifest.get("interval") != "8h":
        raise RuntimeError("study requires BTCUSDT 8h source manifest")
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
    raw_funding = read_json(funding_path)
    funding = {}
    for row in raw_funding:
        raw_timestamp = int(row["fundingTime"])
        boundary = ((raw_timestamp + INTERVAL_MS // 2) // INTERVAL_MS) * INTERVAL_MS
        if abs(raw_timestamp - boundary) > 1000:
            raise RuntimeError(f"funding timestamp is not within 1 second of an 8h boundary: {raw_timestamp}")
        if boundary in funding:
            raise RuntimeError(f"multiple funding events normalize to the same 8h boundary: {boundary}")
        funding[boundary] = float(row["fundingRate"])
    if len(funding) != len(raw_funding):
        raise RuntimeError("duplicate funding timestamps")
    return markets["spot"], markets["futures"], funding, manifest


def block_bootstrap_mean(values: list[float], seed: int, block: int = 9, reps: int = 4000):
    if not values:
        return [None, None]
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


def month_key(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).strftime("%Y-%m")


def direction(spot: dict[int, dict[str, float]], decision_ms: int, lookback: int) -> float:
    earlier_ms = decision_ms - lookback * DAY_MS
    if decision_ms not in spot or earlier_ms not in spot:
        raise RuntimeError(f"missing signal price at {iso_ms(decision_ms)} or {iso_ms(earlier_ms)}")
    current = spot[decision_ms]["close"]
    earlier = spot[earlier_ms]["close"]
    return 1.0 if current > earlier else (-1.0 if current < earlier else 0.0)


def target_weight(spot: dict[int, dict[str, float]], timestamp: int, variant: str) -> tuple[float, dict[str, float]]:
    if variant == "continuous_long":
        return MAX_ABS_WEIGHT, {"benchmark": 1.0}
    decision_ms = timestamp - INTERVAL_MS
    if variant == "ensemble":
        signals = {str(window): direction(spot, decision_ms, window) for window in LOOKBACKS}
        return sum(signals.values()) * ENSEMBLE_COMPONENT_WEIGHT, signals
    window = int(variant)
    signal = direction(spot, decision_ms, window)
    return signal * MAX_ABS_WEIGHT, {variant: signal}


def data_quality(
    spot: dict[int, dict[str, float]],
    futures: dict[int, dict[str, float]],
    funding: dict[int, float],
    start_ms: int,
    end_ms: int,
) -> dict[str, object]:
    phase_grid = list(range(start_ms, end_ms + INTERVAL_MS, INTERVAL_MS))
    required_spot_start = start_ms - INTERVAL_MS - max(LOOKBACKS) * DAY_MS
    signal_grid = list(range(required_spot_start, end_ms + INTERVAL_MS, INTERVAL_MS))
    missing_spot = [value for value in signal_grid if value not in spot]
    missing_futures = [value for value in phase_grid if value not in futures]
    settlement_grid = list(range(start_ms + INTERVAL_MS, end_ms + INTERVAL_MS, INTERVAL_MS))
    missing_funding = [value for value in settlement_grid if value not in funding]
    unexpected_funding = [
        value for value in funding
        if start_ms < value <= end_ms and value not in set(settlement_grid)
    ]
    invalid_ohlc = 0
    for market, values in (("spot", spot), ("futures", futures)):
        grid = signal_grid if market == "spot" else phase_grid
        for timestamp in grid:
            row = values.get(timestamp)
            if row is None:
                continue
            if (
                min(row.values()) <= 0
                or row["high"] < max(row["open"], row["close"])
                or row["low"] > min(row["open"], row["close"])
                or row["high"] < row["low"]
            ):
                invalid_ohlc += 1
    status = "PASS" if not (missing_spot or missing_futures or missing_funding or unexpected_funding or invalid_ohlc) else "FAIL"
    return {
        "status": status,
        "phase_intervals": len(settlement_grid),
        "required_spot_rows": len(signal_grid),
        "missing_spot_rows": len(missing_spot),
        "missing_futures_rows": len(missing_futures),
        "missing_funding_settlements": len(missing_funding),
        "unexpected_non_8h_funding_events": len(unexpected_funding),
        "funding_events_used": len(settlement_grid) - len(missing_funding),
        "invalid_ohlc_rows": invalid_ohlc,
        "funding_interval_boundary": "actual event timestamps normalized only when within 1 second of the nearest 8h boundary; no aggregation",
    }


def summarize(
    returns: list[float],
    timestamps: list[int],
    turnover: float,
    price_pnl: float,
    funding_pnl: float,
    cost_pnl: float,
    worst_intrabar_adverse: float,
    rebalance_records: list[dict[str, object]],
    seed: int,
) -> dict[str, object]:
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    by_year_returns: dict[str, list[float]] = {}
    for timestamp, value in zip(timestamps, returns):
        equity *= 1.0 + value
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity / peak - 1.0)
        by_year_returns.setdefault(str(datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).year), []).append(value)
    total = equity - 1.0
    std = statistics.stdev(returns) if len(returns) > 1 else 0.0
    years = len(returns) / (365.0 * 3.0)
    by_year = {
        year: {"intervals": len(values), "return": math.prod(1.0 + value for value in values) - 1.0}
        for year, values in sorted(by_year_returns.items())
    }
    sign_counts = {
        name: sum(1 for row in rebalance_records if row["target_weight"] > 0)
        for name in ("positive_rebalances",)
    }
    sign_counts.update({
        "negative_rebalances": sum(1 for row in rebalance_records if row["target_weight"] < 0),
        "zero_rebalances": sum(1 for row in rebalance_records if row["target_weight"] == 0),
    })
    return {
        "intervals": len(returns),
        "total_return": total,
        "annualized_return": (1.0 + total) ** (1.0 / years) - 1.0 if years > 0 and total > -1.0 else None,
        "annualized_volatility": std * math.sqrt(365.0 * 3.0),
        "sharpe_zero_rf": statistics.fmean(returns) / std * math.sqrt(365.0 * 3.0) if std else None,
        "max_drawdown": max_drawdown,
        "turnover": turnover,
        "price_pnl_on_initial_capital": price_pnl,
        "funding_pnl_on_initial_capital": funding_pnl,
        "cost_pnl_on_initial_capital": cost_pnl,
        "worst_8h_intrabar_adverse_on_then_nav": worst_intrabar_adverse,
        "interval_mean_block_bootstrap_95pct": block_bootstrap_mean(returns, seed),
        "by_year": by_year,
        "rebalance_count": len(rebalance_records),
        "position_sign_counts": sign_counts,
        "rebalance_records_digest": canonical_digest(rebalance_records),
        "returns_digest": canonical_digest(list(zip(timestamps, returns))),
    }


def simulate(
    spot: dict[int, dict[str, float]],
    futures: dict[int, dict[str, float]],
    funding: dict[int, float],
    start_ms: int,
    end_ms: int,
    variant: str,
    cost_rate: float,
    seed: int,
) -> dict[str, object]:
    timestamps = list(range(start_ms, end_ms, INTERVAL_MS))
    nav = 1.0
    quantity = 0.0
    total_turnover = 0.0
    price_pnl_total = 0.0
    funding_pnl_total = 0.0
    cost_pnl_total = 0.0
    worst_intrabar_adverse = 0.0
    returns: list[float] = []
    return_timestamps: list[int] = []
    rebalance_records: list[dict[str, object]] = []
    last_month = None
    for timestamp in timestamps:
        next_timestamp = timestamp + INTERVAL_MS
        nav_before = nav
        current_month = month_key(timestamp)
        if current_month != last_month:
            target, signals = target_weight(spot, timestamp, variant)
            current_weight = quantity * futures[timestamp]["open"] / nav
            turnover = abs(target - current_weight)
            cost_amount = nav * turnover * cost_rate
            nav -= cost_amount
            cost_pnl_total -= cost_amount
            total_turnover += turnover
            quantity = nav * target / futures[timestamp]["open"]
            rebalance_records.append({
                "timestamp": timestamp,
                "target_weight": target,
                "signals": signals,
                "turnover": turnover,
            })
            last_month = current_month
        row = futures[timestamp]
        if quantity >= 0:
            adverse_price = row["low"]
        else:
            adverse_price = row["high"]
        intrabar_adverse = quantity * (adverse_price - row["open"]) / nav
        worst_intrabar_adverse = min(worst_intrabar_adverse, intrabar_adverse)
        price_pnl = quantity * (futures[next_timestamp]["open"] - row["open"])
        funding_pnl = -quantity * futures[next_timestamp]["open"] * funding[next_timestamp]
        nav += price_pnl + funding_pnl
        price_pnl_total += price_pnl
        funding_pnl_total += funding_pnl
        if nav <= 0:
            raise RuntimeError("portfolio equity depleted")
        returns.append(nav / nav_before - 1.0)
        return_timestamps.append(next_timestamp)
    final_weight = quantity * futures[end_ms]["open"] / nav
    exit_turnover = abs(final_weight)
    exit_cost = nav * exit_turnover * cost_rate
    nav_after_exit = nav - exit_cost
    total_turnover += exit_turnover
    cost_pnl_total -= exit_cost
    returns[-1] = (1.0 + returns[-1]) * (nav_after_exit / nav) - 1.0
    return summarize(
        returns,
        return_timestamps,
        total_turnover,
        price_pnl_total,
        funding_pnl_total,
        cost_pnl_total,
        worst_intrabar_adverse,
        rebalance_records,
        seed,
    )


def phase_result(spot, futures, funding, phase: str) -> dict[str, object]:
    start_ms, end_ms = (to_ms(value) for value in PHASES[phase])
    quality = data_quality(spot, futures, funding, start_ms, end_ms)
    variants = ("ensemble", "60", "90", "180", "continuous_long")
    results = {
        variant: {
            name: simulate(spot, futures, funding, start_ms, end_ms, variant, cost, 20260720 + vi * 10 + ci)
            for ci, (name, cost) in enumerate(COSTS.items())
        }
        for vi, variant in enumerate(variants)
    }
    return {
        "phase": phase,
        "period": {"start": PHASES[phase][0], "end_exclusive": PHASES[phase][1]},
        "data_quality": quality,
        "strategy": {key: results[key] for key in ("ensemble", "60", "90", "180")},
        "continuous_quarter_long_benchmark": results["continuous_long"],
        "cash_benchmark_return": 0.0,
    }


def command_analyze(args: argparse.Namespace) -> None:
    if args.phase != "development":
        if not args.authorization or not read_json(Path(args.authorization)).get("holdout_authorized"):
            raise RuntimeError("holdout is not authorized")
    spot, futures, funding, manifest = load_inputs(Path(args.cache_dir).resolve(), Path(args.source_manifest))
    output = phase_result(spot, futures, funding, args.phase)
    output.update({
        "schema_version": 1,
        "generated_at": utc_now(),
        "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
        "manifest_content_identity": manifest["content_identity"],
        "study_code_sha256": sha256_path(Path(__file__)),
        "rules": {
            "instrument": "BTCUSDT USD-M linear perpetual",
            "signal_source": "BTCUSDT spot previous completed 8h close",
            "lookbacks_days": list(LOOKBACKS),
            "ensemble_component_weight": ENSEMBLE_COMPONENT_WEIGHT,
            "max_absolute_notional_weight": MAX_ABS_WEIGHT,
            "rebalance": "first 8h boundary of each UTC month",
            "funding": "actual event rate normalized within 1 second to its 8h boundary; positive rate debits longs and credits shorts",
            "turnover_costs": COSTS,
        },
    })
    output["content_digest"] = canonical_digest({key: value for key, value in output.items() if key != "generated_at"})
    write_json(Path(args.output), output)
    main = output["strategy"]["ensemble"]["base"]
    print(json.dumps({"phase": args.phase, "base_total": main["total_return"], "max_drawdown": main["max_drawdown"]}))


def development_passed(result: dict[str, object]) -> bool:
    ensemble = result["strategy"]["ensemble"]
    base = ensemble["base"]
    benchmark = result["continuous_quarter_long_benchmark"]["base"]
    diagnostics = [result["strategy"][str(window)]["base"]["total_return"] for window in LOOKBACKS]
    return (
        result["data_quality"]["status"] == "PASS"
        and base["total_return"] > 0
        and ensemble["stress"]["total_return"] > 0
        and base["max_drawdown"] > -0.20
        and base["max_drawdown"] >= benchmark["max_drawdown"] - 0.02
        and base["worst_8h_intrabar_adverse_on_then_nav"] > -0.10
        and sum(value > 0 for value in diagnostics) >= 2
        and base["turnover"] <= 12
    )


def evaluation_passed(result: dict[str, object]) -> bool:
    ensemble = result["strategy"]["ensemble"]
    base = ensemble["base"]
    benchmark = result["continuous_quarter_long_benchmark"]["base"]
    diagnostics = [result["strategy"][str(window)]["base"]["total_return"] for window in LOOKBACKS]
    return (
        result["data_quality"]["status"] == "PASS"
        and base["total_return"] > 0
        and ensemble["stress"]["total_return"] > 0
        and all(item["return"] > 0 for item in base["by_year"].values())
        and base["max_drawdown"] > -0.18
        and base["max_drawdown"] >= benchmark["max_drawdown"] - 0.02
        and base["worst_8h_intrabar_adverse_on_then_nav"] > -0.10
        and sum(value > 0 for value in diagnostics) >= 2
    )


def command_qualify(args: argparse.Namespace, phase: str) -> None:
    result = read_json(Path(args.input))
    passed = development_passed(result) if phase == "development" else evaluation_passed(result)
    output = {
        "generated_at": utc_now(),
        "phase": phase,
        "input_content_digest": result["content_digest"],
        "qualification_status": f"PASSED_{phase.upper()}_GATE" if passed else f"FAILED_{phase.upper()}_GATE_STOP",
        "holdout_authorized": passed,
        "fixed_rule": "BTCUSDT_PERP_MONTHLY_60_90_180_DIRECTION_ENSEMBLE_MAX_0P25X",
    }
    output["content_digest"] = canonical_digest({key: value for key, value in output.items() if key != "generated_at"})
    write_json(Path(args.output), output)
    print(json.dumps({"status": output["qualification_status"]}))


def command_combine(args: argparse.Namespace) -> None:
    development = read_json(Path(args.development))
    evaluation = read_json(Path(args.evaluation))
    confirmation = read_json(Path(args.confirmation))
    evaluation_gate = read_json(Path(args.evaluation_gate))
    confirm = confirmation["strategy"]["ensemble"]
    base = confirm["base"]
    benchmark = confirmation["continuous_quarter_long_benchmark"]["base"]
    diagnostics = [confirmation["strategy"][str(window)]["base"]["total_return"] for window in LOOKBACKS]
    combined = (1.0 + evaluation["strategy"]["ensemble"]["base"]["total_return"]) * (1.0 + base["total_return"]) - 1.0
    support_gate = (
        evaluation_gate["holdout_authorized"]
        and confirmation["data_quality"]["status"] == "PASS"
        and base["total_return"] > 0
        and confirm["stress"]["total_return"] > 0
        and base["max_drawdown"] > -0.15
        and base["max_drawdown"] >= benchmark["max_drawdown"] - 0.02
        and base["worst_8h_intrabar_adverse_on_then_nav"] > -0.10
        and sum(value >= 0 for value in diagnostics) >= 2
        and combined > 0
    )
    if support_gate:
        conclusion = "SUPPORTS_WITHIN_SCOPE"
    elif base["total_return"] < 0 or combined < 0:
        conclusion = "DOES_NOT_SUPPORT"
    else:
        conclusion = "INSUFFICIENT_EVIDENCE"
    output = {
        "generated_at": utc_now(),
        "conclusion": conclusion,
        "scope": "BTCUSDT monthly symmetric 60/90/180 direction ensemble on USD-M perpetual, max 0.25x, exact 8h funding, through 2025-08",
        "development": development["strategy"]["ensemble"]["base"],
        "evaluation": evaluation["strategy"]["ensemble"]["base"],
        "confirmation": base,
        "confirmation_stress": confirm["stress"],
        "confirmation_single_window_base_returns": {str(window): diagnostics[index] for index, window in enumerate(LOOKBACKS)},
        "confirmation_quarter_long_benchmark": benchmark,
        "evaluation_confirmation_compounded_return": combined,
        "confirmation_support_gate": support_gate,
        "formal_product_strategy_comparison": "FIXED_BACKGROUND_ONLY_NO_COMPARABLE_ACTIVATION_REPLAY",
        "product_effects": "NONE",
    }
    output["content_digest"] = canonical_digest({key: value for key, value in output.items() if key != "generated_at"})
    write_json(Path(args.output), output)
    print(json.dumps({"conclusion": conclusion, "combined": combined}))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BTCUSDT low-gross multi-horizon perpetual direction study")
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
