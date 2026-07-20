from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import math
import random
import statistics
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


INTERVAL = "8h"
INTERVAL_MS = 8 * 60 * 60 * 1000
ARCHIVE_ROOT = "https://data.binance.vision/data"
FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
THRESHOLDS_BPS = (1.0, 3.0, 5.0)
COSTS_COMBINED_TRANSITION = {"favorable": 0.0016, "base": 0.0024, "stress": 0.0040}
PHASES = {
    "development": {"symbol": "BTCUSDT", "start": "2021-01-01T00:00:00Z", "end": "2024-01-01T00:00:00Z"},
    "evaluation": {"symbol": "BTCUSDT", "start": "2024-01-01T00:00:00Z", "end": "2026-01-01T00:00:00Z"},
    "confirmation": {"symbol": "BNBUSDT", "start": "2021-01-01T00:00:00Z", "end": "2026-01-01T00:00:00Z"},
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_ms(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def iso_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_timestamp(value: int) -> int:
    return value // 1000 if value > 100_000_000_000_000 else value


def next_month(value: datetime) -> datetime:
    return value.replace(year=value.year + (value.month == 12), month=1 if value.month == 12 else value.month + 1)


def month_iter(start: str, end: str) -> Iterator[str]:
    current = datetime.strptime(start, "%Y-%m")
    final = datetime.strptime(end, "%Y-%m")
    while current <= final:
        yield current.strftime("%Y-%m")
        current = next_month(current)


def month_bounds(start: str, end: str) -> tuple[int, int]:
    first = datetime.strptime(start, "%Y-%m").replace(tzinfo=timezone.utc)
    final = next_month(datetime.strptime(end, "%Y-%m")).replace(tzinfo=timezone.utc)
    return int(first.timestamp() * 1000), int(final.timestamp() * 1000)


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


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def request_bytes(url: str, attempts: int = 4) -> bytes:
    error = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Halpha-public-research/1.0"})
            with urllib.request.urlopen(request, timeout=45) as response:
                return response.read()
        except Exception as exc:
            error = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"request failed: {url}") from error


def archive_spec(symbol: str, market: str, month: str) -> tuple[str, Path]:
    filename = f"{symbol}-{INTERVAL}-{month}.zip"
    if market == "spot":
        relative_url = f"spot/monthly/klines/{symbol}/{INTERVAL}/{filename}"
    else:
        relative_url = f"futures/um/monthly/klines/{symbol}/{INTERVAL}/{filename}"
    return f"{ARCHIVE_ROOT}/{relative_url}", Path(market) / filename


def fetch_archive(cache: Path, symbol: str, market: str, month: str) -> dict[str, object]:
    url, relative = archive_spec(symbol, market, month)
    expected = request_bytes(url + ".CHECKSUM").decode("utf-8").split()[0].lower()
    target = cache / symbol / relative
    if not target.exists() or sha256_path(target) != expected:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(request_bytes(url))
    actual = sha256_path(target)
    if actual != expected:
        raise RuntimeError(f"checksum mismatch: {symbol} {market} {month}")
    return {
        "market": market,
        "month": month,
        "url": url,
        "checksum_url": url + ".CHECKSUM",
        "sha256": actual,
        "bytes": target.stat().st_size,
        "cache_relative_path": (Path(symbol) / relative).as_posix(),
    }


def fetch_funding(cache: Path, symbol: str, start_ms: int, end_ms: int, label: str) -> dict[str, object]:
    rows = []
    cursor = start_ms
    pages = 0
    while cursor < end_ms:
        query = urllib.parse.urlencode(
            {"symbol": symbol, "startTime": cursor, "endTime": end_ms - 1, "limit": 1000}
        )
        page = json.loads(request_bytes(f"{FUNDING_URL}?{query}").decode("utf-8"))
        pages += 1
        if not page:
            break
        rows.extend(
            {"fundingTime": int(row["fundingTime"]), "fundingRate": str(row["fundingRate"])}
            for row in page
            if start_ms <= int(row["fundingTime"]) < end_ms
        )
        next_cursor = int(page[-1]["fundingTime"]) + 1
        if next_cursor <= cursor:
            raise RuntimeError("funding pagination did not advance")
        cursor = next_cursor
        if len(page) < 1000:
            break
    unique = {row["fundingTime"]: row for row in rows}
    ordered = [unique[key] for key in sorted(unique)]
    relative = Path(symbol) / f"funding-{label}.json"
    target = cache / relative
    write_json(target, ordered)
    return {
        "url": FUNDING_URL,
        "request_security": "NONE_PUBLIC_MARKET_DATA",
        "records": len(ordered),
        "pages": pages,
        "requested_start_ms": start_ms,
        "requested_end_exclusive_ms": end_ms,
        "sha256": sha256_path(target),
        "bytes": target.stat().st_size,
        "cache_relative_path": relative.as_posix(),
    }


def command_fetch(args: argparse.Namespace) -> None:
    cache = Path(args.cache_dir).resolve()
    start_ms, end_ms = month_bounds(args.start_month, args.end_month)
    archives = []
    for month in month_iter(args.start_month, args.end_month):
        archives.append(fetch_archive(cache, args.symbol, "spot", month))
        archives.append(fetch_archive(cache, args.symbol, "futures", month))
    funding = fetch_funding(cache, args.symbol, start_ms, end_ms, f"{args.start_month}_{args.end_month}")
    manifest = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "venue": "BINANCE",
        "symbol": args.symbol,
        "spot_contract": f"{args.symbol} spot",
        "perpetual_contract": f"{args.symbol} USD-M linear perpetual",
        "interval": INTERVAL,
        "timezone": "UTC",
        "spot_timestamp_rule": "Normalize values above 1e14 from microseconds to milliseconds",
        "cache_root": str(cache),
        "requested_start_month": args.start_month,
        "requested_end_month": args.end_month,
        "archives": archives,
        "funding_snapshot": funding,
    }
    manifest["content_identity"] = canonical_digest(
        {"archives": archives, "funding_snapshot": funding, "symbol": args.symbol, "interval": INTERVAL}
    )
    write_json(Path(args.manifest), manifest)
    print(json.dumps({"symbol": args.symbol, "archives": len(archives), "funding": funding["records"]}))


def iter_opens(path: Path) -> Iterator[tuple[int, float]]:
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
                    price = float(row[1])
                except ValueError:
                    continue
                yield timestamp, price


def load_inputs(cache: Path, manifest: dict[str, object]) -> tuple[dict[int, float], dict[int, float], list[tuple[int, float]]]:
    markets = {"spot": {}, "futures": {}}
    for item in manifest["archives"]:
        path = cache / item["cache_relative_path"]
        if sha256_path(path) != item["sha256"]:
            raise RuntimeError(f"archive identity mismatch: {path}")
        markets[item["market"]].update(iter_opens(path))
    funding_item = manifest["funding_snapshot"]
    funding_path = cache / funding_item["cache_relative_path"]
    if sha256_path(funding_path) != funding_item["sha256"]:
        raise RuntimeError("funding identity mismatch")
    funding_rows = read_json(funding_path)
    events = sorted(
        ((int(row["fundingTime"]) // INTERVAL_MS) * INTERVAL_MS, float(row["fundingRate"]))
        for row in funding_rows
    )
    unique_events = {timestamp: rate for timestamp, rate in events}
    return markets["spot"], markets["futures"], sorted(unique_events.items())


def block_bootstrap_mean(values: list[float], seed: int, block: int = 9, reps: int = 4000) -> list[float | None]:
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


def max_drawdown(values: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return worst


def build_rows(
    spot: dict[int, float],
    futures: dict[int, float],
    funding: list[tuple[int, float]],
    start_ms: int,
    end_ms: int,
    threshold_bps: float,
    transition_cost: float,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    threshold = threshold_bps / 10_000.0
    events = [(timestamp, rate) for timestamp, rate in funding if start_ms <= timestamp <= end_ms]
    aligned = [(timestamp, rate) for timestamp, rate in events if timestamp in spot and timestamp in futures]
    rows = []
    active = False
    entry_spot = 0.0
    entry_futures = 0.0
    episode = 0
    episode_returns: dict[int, float] = {}
    forced_exit_time = None
    for (timestamp, current_rate), (next_timestamp, next_rate) in zip(aligned, aligned[1:]):
        if timestamp < start_ms or next_timestamp > end_ms:
            continue
        entered = False
        if not active and current_rate + 1e-15 >= threshold:
            active = True
            entered = True
            episode += 1
            entry_spot = spot[timestamp]
            entry_futures = futures[timestamp]
            episode_returns[episode] = 0.0
        if not active:
            rows.append(
                {
                    "time": next_timestamp,
                    "year": datetime.fromtimestamp(next_timestamp / 1000, tz=timezone.utc).year,
                    "active": False,
                    "episode": None,
                    "basis": 0.0,
                    "funding": 0.0,
                    "cost": 0.0,
                    "capital_return": 0.0,
                }
            )
            continue
        basis = (
            (spot[next_timestamp] - spot[timestamp]) / entry_spot
            - (futures[next_timestamp] - futures[timestamp]) / entry_futures
        )
        funding_pnl = next_rate * futures[next_timestamp] / entry_futures
        exit_now = next_rate <= 0 or next_timestamp >= end_ms
        raw_cost = transition_cost * (int(entered) + int(exit_now))
        capital_return = (basis + funding_pnl - raw_cost) / 2.0
        episode_returns[episode] += capital_return
        rows.append(
            {
                "time": next_timestamp,
                "year": datetime.fromtimestamp(next_timestamp / 1000, tz=timezone.utc).year,
                "active": True,
                "episode": episode,
                "basis": basis / 2.0,
                "funding": funding_pnl / 2.0,
                "cost": -raw_cost / 2.0,
                "capital_return": capital_return,
            }
        )
        if exit_now:
            active = False
    if active:
        for row in reversed(rows):
            if row["active"] and row["episode"] == episode:
                exit_cost_on_capital = transition_cost / 2.0
                row["cost"] = float(row["cost"]) - exit_cost_on_capital
                row["capital_return"] = float(row["capital_return"]) - exit_cost_on_capital
                episode_returns[episode] -= exit_cost_on_capital
                forced_exit_time = row["time"]
                break
        active = False
    metadata = {
        "funding_events_inclusive": len(events),
        "aligned_events_inclusive": len(aligned),
        "missing_event_prices": len(events) - len(aligned),
        "event_gap_counts": {
            str(delta // 3_600_000): count
            for delta, count in sorted(
                {
                    current: sum(
                        1 for left, right in zip(aligned, aligned[1:]) if right[0] - left[0] == current
                    )
                    for current in {right[0] - left[0] for left, right in zip(aligned, aligned[1:])}
                }.items()
            )
        },
        "episodes": len(episode_returns),
        "episode_returns": [episode_returns[key] for key in sorted(episode_returns)],
        "forced_exit_at_last_available_event": iso_ms(forced_exit_time) if forced_exit_time else None,
    }
    return rows, metadata


def summarize(rows: list[dict[str, object]], metadata: dict[str, object], seed: int) -> dict[str, object]:
    values = [float(row["capital_return"]) for row in rows]
    active = [float(row["capital_return"]) for row in rows if row["active"]]
    years = {}
    for year in sorted({str(row["year"]) for row in rows}):
        yearly = [float(row["capital_return"]) for row in rows if str(row["year"]) == year]
        years[year] = {
            "intervals": len(yearly),
            "active_intervals": sum(row["active"] for row in rows if str(row["year"]) == year),
            "return_noncompounded": sum(yearly),
        }
    compounded = math.prod(1.0 + value for value in values) - 1.0
    return {
        "intervals": len(values),
        "active_intervals": len(active),
        "exposure_fraction": len(active) / len(values) if values else None,
        "episodes": metadata["episodes"],
        "episode_returns": metadata["episode_returns"],
        "positive_episode_fraction": (
            sum(value > 0 for value in metadata["episode_returns"]) / len(metadata["episode_returns"])
            if metadata["episode_returns"]
            else None
        ),
        "return_noncompounded": sum(values),
        "return_compounded_resized_sensitivity": compounded,
        "active_interval_mean": statistics.fmean(active) if active else None,
        "active_interval_bootstrap_95pct_mean": block_bootstrap_mean(active, seed=seed),
        "max_drawdown_noncompounded": max_drawdown(values),
        "basis_sum": sum(float(row["basis"]) for row in rows),
        "funding_sum": sum(float(row["funding"]) for row in rows),
        "cost_sum": sum(float(row["cost"]) for row in rows),
        "by_year": years,
        "rows_digest": canonical_digest(rows),
    }


def threshold_from_selection(path: str) -> float:
    value = read_json(Path(path)).get("selected_threshold_bps")
    if value is None:
        raise RuntimeError("development did not authorize holdout")
    return float(value)


def command_analyze(args: argparse.Namespace) -> None:
    phase = PHASES[args.phase]
    manifest = read_json(Path(args.manifest))
    if manifest["symbol"] != phase["symbol"]:
        raise RuntimeError(f"phase requires {phase['symbol']}, manifest has {manifest['symbol']}")
    if args.phase == "development":
        thresholds = THRESHOLDS_BPS
    else:
        if not args.selection:
            raise RuntimeError("holdout phases require --selection")
        thresholds = (threshold_from_selection(args.selection),)
    spot, futures, funding = load_inputs(Path(args.cache_dir).resolve(), manifest)
    start_ms, end_ms = parse_ms(phase["start"]), parse_ms(phase["end"])
    variants = {}
    for threshold in thresholds:
        scenarios = {}
        metadata_for_output = None
        for offset, (name, cost) in enumerate(COSTS_COMBINED_TRANSITION.items()):
            rows, metadata = build_rows(spot, futures, funding, start_ms, end_ms, threshold, cost)
            scenarios[name] = summarize(rows, metadata, seed=20260720 + int(threshold * 10) + offset)
            metadata_for_output = {k: v for k, v in metadata.items() if k != "episode_returns"}
        variants[f"{threshold:g}bps"] = {
            "threshold_bps": threshold,
            "data_alignment": metadata_for_output,
            "favorable": scenarios["favorable"],
            "base": scenarios["base"],
            "stress": scenarios["stress"],
        }
    output = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "phase": args.phase,
        "symbol": phase["symbol"],
        "period": {"start": phase["start"], "end_exclusive": phase["end"]},
        "manifest_content_identity": manifest["content_identity"],
        "study_code_sha256": sha256_path(Path(__file__)),
        "rules": {
            "entry_thresholds_bps": list(thresholds),
            "exit": "after a settled funding rate <= 0",
            "capital": "two fully funded units; all PnL divided by two",
            "combined_transition_costs": COSTS_COMBINED_TRANSITION,
        },
        "variants": variants,
    }
    output["content_digest"] = canonical_digest({k: v for k, v in output.items() if k != "generated_at"})
    write_json(Path(args.output), output)
    print(json.dumps({
        "phase": args.phase,
        "symbol": phase["symbol"],
        "base_returns": {key: value["base"]["return_noncompounded"] for key, value in variants.items()},
    }))


def command_select(args: argparse.Namespace) -> None:
    development = read_json(Path(args.development))
    candidates = []
    for key, variant in development["variants"].items():
        base = variant["base"]
        ci_low = base["active_interval_bootstrap_95pct_mean"][0]
        positive_years = sum(item["return_noncompounded"] > 0 for item in base["by_year"].values())
        passed = (
            base["active_intervals"] >= 300
            and base["return_noncompounded"] > 0
            and positive_years >= 2
            and ci_low is not None
            and ci_low > 0
        )
        candidates.append({
            "variant": key,
            "threshold_bps": variant["threshold_bps"],
            "active_intervals": base["active_intervals"],
            "return_noncompounded": base["return_noncompounded"],
            "positive_years": positive_years,
            "bootstrap_low": ci_low,
            "passed": passed,
        })
    passers = [item for item in candidates if item["passed"]]
    passers.sort(key=lambda item: (item["bootstrap_low"], item["return_noncompounded"]), reverse=True)
    selected = passers[0] if passers else None
    output = {
        "generated_at": utc_now(),
        "development_content_digest": development["content_digest"],
        "gate": "active intervals >= 300; positive noncompounded return; >=2 positive years; 9-interval block-bootstrap lower mean > 0",
        "candidates": candidates,
        "selection_status": "PASSED_DEVELOPMENT_GATE" if selected else "NO_VARIANT_PASSED_DEVELOPMENT_GATE_STOP",
        "selected_threshold_bps": selected["threshold_bps"] if selected else None,
        "holdout_authorized": bool(selected),
    }
    output["content_digest"] = canonical_digest({k: v for k, v in output.items() if k != "generated_at"})
    write_json(Path(args.output), output)
    print(json.dumps({"status": output["selection_status"], "selected": output["selected_threshold_bps"]}))


def command_combine(args: argparse.Namespace) -> None:
    development = read_json(Path(args.development))
    selection = read_json(Path(args.selection))
    evaluation = read_json(Path(args.evaluation))
    confirmation = read_json(Path(args.confirmation))
    threshold = float(selection["selected_threshold_bps"])
    key = f"{threshold:g}bps"
    dev = development["variants"][key]["base"]
    eva = evaluation["variants"][key]["base"]
    con = confirmation["variants"][key]["base"]
    eva_ci = eva["active_interval_bootstrap_95pct_mean"][0]
    con_ci = con["active_interval_bootstrap_95pct_mean"][0]
    evaluation_support = (
        eva["return_noncompounded"] > 0
        and set(eva["by_year"]) == {"2024", "2025"}
        and all(item["return_noncompounded"] > 0 for item in eva["by_year"].values())
        and eva_ci is not None
        and eva_ci > 0
    )
    confirmation_support = (
        con["active_intervals"] >= 600
        and con["return_noncompounded"] > 0
        and sum(item["return_noncompounded"] > 0 for item in con["by_year"].values()) >= 3
        and con_ci is not None
        and con_ci > 0
    )
    if evaluation_support and confirmation_support:
        conclusion = "SUPPORTS_WITHIN_SCOPE"
    elif eva["return_noncompounded"] < 0:
        conclusion = "DOES_NOT_SUPPORT"
    else:
        conclusion = "INSUFFICIENT_EVIDENCE"
    output = {
        "generated_at": utc_now(),
        "conclusion": conclusion,
        "scope": "Same-venue long spot/short USD-M perpetual after positive settled funding, fixed two-unit capital and modeled two-leg costs",
        "selected_threshold_bps": threshold,
        "development_btc": dev,
        "evaluation_btc": eva,
        "confirmation_bnb": con,
        "evaluation_support_gate": evaluation_support,
        "confirmation_support_gate": confirmation_support,
        "formal_product_strategy_comparison": "NOT_RUN_ECONOMICALLY_INCOMPARABLE_SINGLE_LEG_TREND_STRATEGY",
        "product_effects": "NONE",
    }
    output["content_digest"] = canonical_digest({k: v for k, v in output.items() if k != "generated_at"})
    write_json(Path(args.output), output)
    print(json.dumps({"conclusion": conclusion, "threshold_bps": threshold}))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Binance same-venue positive-funding cash-and-carry study")
    sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch")
    fetch.add_argument("--cache-dir", required=True)
    fetch.add_argument("--symbol", choices=("BTCUSDT", "BNBUSDT"), required=True)
    fetch.add_argument("--start-month", required=True)
    fetch.add_argument("--end-month", required=True)
    fetch.add_argument("--manifest", required=True)
    fetch.set_defaults(func=command_fetch)
    analyze = sub.add_parser("analyze")
    analyze.add_argument("--cache-dir", required=True)
    analyze.add_argument("--manifest", required=True)
    analyze.add_argument("--phase", choices=tuple(PHASES), required=True)
    analyze.add_argument("--selection")
    analyze.add_argument("--output", required=True)
    analyze.set_defaults(func=command_analyze)
    select = sub.add_parser("select")
    select.add_argument("--development", required=True)
    select.add_argument("--output", required=True)
    select.set_defaults(func=command_select)
    combine = sub.add_parser("combine")
    combine.add_argument("--development", required=True)
    combine.add_argument("--selection", required=True)
    combine.add_argument("--evaluation", required=True)
    combine.add_argument("--confirmation", required=True)
    combine.add_argument("--output", required=True)
    combine.set_defaults(func=command_combine)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
