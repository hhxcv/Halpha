from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import statistics
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path


BASE_PATH = Path(__file__).resolve().parent.parent / "binance-positive-funding-cash-carry" / "study.py"
SPEC = importlib.util.spec_from_file_location("single_carry_base", BASE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load retained single-carry study")
base = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(base)

UNIVERSES = {
    "core": ("DOGEUSDT", "XRPUSDT", "ADAUSDT"),
    "confirmation": ("LTCUSDT", "LINKUSDT"),
}
PHASES = {
    "development": {"universe": "core", "start": "2021-01-01T00:00:00Z", "end": "2024-01-01T00:00:00Z"},
    "evaluation": {"universe": "core", "start": "2024-01-01T00:00:00Z", "end": "2026-01-01T00:00:00Z"},
    "confirmation": {"universe": "confirmation", "start": "2021-01-01T00:00:00Z", "end": "2026-01-01T00:00:00Z"},
}
THRESHOLD = 0.0003
PERSISTENCE = 2
SPOT_KLINE_URL = "https://data-api.binance.vision/api/v3/klines"
FUTURES_KLINE_URL = "https://fapi.binance.com/fapi/v1/klines"


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_backfill(cache: Path, symbol: str, market: str, start_ms: int, end_ms: int, label: str, archives):
    archive_times = set()
    for item in archives:
        if item["market"] == market:
            archive_times.update(timestamp for timestamp, _ in base.iter_opens(cache / item["cache_relative_path"]))
    url = SPOT_KLINE_URL if market == "spot" else FUTURES_KLINE_URL
    limit = 1000 if market == "spot" else 1500
    api_rows = {}
    cursor = start_ms
    pages = 0
    while cursor < end_ms:
        query = urllib.parse.urlencode({"symbol": symbol, "interval": base.INTERVAL, "startTime": cursor, "endTime": end_ms - 1, "limit": limit})
        page = json.loads(base.request_bytes(f"{url}?{query}").decode("utf-8"))
        pages += 1
        if not page:
            break
        for row in page:
            timestamp = int(row[0])
            if start_ms <= timestamp < end_ms:
                api_rows[timestamp] = {"openTime": timestamp, "open": str(row[1])}
        next_cursor = int(page[-1][0]) + base.INTERVAL_MS
        if next_cursor <= cursor:
            raise RuntimeError("Kline backfill pagination did not advance")
        cursor = next_cursor
        if len(page) < limit:
            break
    missing = sorted(set(range(start_ms, end_ms, base.INTERVAL_MS)) - archive_times)
    unresolved = sorted(set(missing) - set(api_rows))
    if unresolved:
        raise RuntimeError(f"unresolved {symbol} {market} 8h Kline gaps: {unresolved}")
    relative = Path(symbol) / market / f"kline-backfill-{label}.json"
    target = cache / relative
    base.write_json(target, [api_rows[timestamp] for timestamp in missing])
    return {
        "market": market,
        "url": url,
        "request_security": "NONE_PUBLIC_MARKET_DATA",
        "policy": "fill_only_timestamps_absent_from_checksum-verified_monthly_archives",
        "pages": pages,
        "records": len(missing),
        "open_times_ms": missing,
        "sha256": base.sha256_path(target),
        "bytes": target.stat().st_size,
        "cache_relative_path": relative.as_posix(),
    }


def command_fetch(args: argparse.Namespace) -> None:
    cache = Path(args.cache_dir).resolve()
    symbols = UNIVERSES[args.universe]
    start_ms, end_ms = base.month_bounds(args.start_month, args.end_month)
    archives, funding, backfills = {}, {}, {}
    for symbol in symbols:
        items = []
        for month in base.month_iter(args.start_month, args.end_month):
            items.append(base.fetch_archive(cache, symbol, "spot", month))
            items.append(base.fetch_archive(cache, symbol, "futures", month))
        archives[symbol] = items
        funding[symbol] = base.fetch_funding(cache, symbol, start_ms, end_ms, f"{args.start_month}_{args.end_month}")
        backfills[symbol] = {
            market: fetch_backfill(cache, symbol, market, start_ms, end_ms, f"{args.start_month}_{args.end_month}", items)
            for market in ("spot", "futures")
        }
    manifest = {
        "schema_version": 1,
        "generated_at": base.utc_now(),
        "venue": "BINANCE",
        "universe": args.universe,
        "symbols": list(symbols),
        "interval": base.INTERVAL,
        "timezone": "UTC",
        "spot_timestamp_rule": "Normalize values above 1e14 from microseconds to milliseconds",
        "cache_root": str(cache),
        "requested_start_month": args.start_month,
        "requested_end_month": args.end_month,
        "archives": archives,
        "funding_snapshots": funding,
        "kline_backfills": backfills,
    }
    manifest["content_identity"] = base.canonical_digest({"symbols": symbols, "archives": archives, "funding": funding, "backfills": backfills})
    base.write_json(Path(args.manifest), manifest)
    print(json.dumps({"symbols": len(symbols), "archives": sum(len(items) for items in archives.values()), "funding": sum(item["records"] for item in funding.values()), "backfills": sum(item[market]["records"] for item in backfills.values() for market in ("spot", "futures"))}))


def load_inputs(cache: Path, manifest: dict[str, object]):
    output = {}
    for symbol in manifest["symbols"]:
        markets = {"spot": {}, "futures": {}}
        for item in manifest["archives"][symbol]:
            path = cache / item["cache_relative_path"]
            if base.sha256_path(path) != item["sha256"]:
                raise RuntimeError(f"archive identity mismatch: {path}")
            markets[item["market"]].update(base.iter_opens(path))
        for market, item in manifest.get("kline_backfills", {}).get(symbol, {}).items():
            path = cache / item["cache_relative_path"]
            if base.sha256_path(path) != item["sha256"]:
                raise RuntimeError(f"backfill identity mismatch: {path}")
            markets[market].update((int(row["openTime"]), float(row["open"])) for row in base.read_json(path))
        funding_item = manifest["funding_snapshots"][symbol]
        funding_path = cache / funding_item["cache_relative_path"]
        if base.sha256_path(funding_path) != funding_item["sha256"]:
            raise RuntimeError("funding identity mismatch")
        rows = base.read_json(funding_path)
        events = {(int(row["fundingTime"]) // base.INTERVAL_MS) * base.INTERVAL_MS: float(row["fundingRate"]) for row in rows}
        output[symbol] = {"spot": markets["spot"], "futures": markets["futures"], "funding": events}
    return output


def build_rows(data, symbols, start_ms: int, end_ms: int, transition_cost: float):
    usable = {}
    per_symbol = {}
    for symbol in symbols:
        item = data[symbol]
        timestamps = {time for time in item["funding"] if start_ms <= time <= end_ms}
        aligned = timestamps & set(item["spot"]) & set(item["futures"])
        usable[symbol] = aligned
        per_symbol[symbol] = {"funding_events": len(timestamps), "aligned_events": len(aligned), "missing_event_prices": len(timestamps - aligned)}
    common = sorted(set.intersection(*(usable[symbol] for symbol in symbols)))
    rows = []
    active_symbol = None
    entry_spot = entry_future = 0.0
    episode = 0
    episode_returns = {}
    episode_symbols = {}
    previous_rates = {symbol: None for symbol in symbols}
    selection_counts = {symbol: 0 for symbol in symbols}
    forced_exit_time = None
    for timestamp, next_timestamp in zip(common, common[1:]):
        current_rates = {symbol: data[symbol]["funding"][timestamp] for symbol in symbols}
        next_rates = {symbol: data[symbol]["funding"][next_timestamp] for symbol in symbols}
        entered = False
        if active_symbol is None:
            qualified = [symbol for symbol in symbols if previous_rates[symbol] is not None and previous_rates[symbol] >= THRESHOLD and current_rates[symbol] >= THRESHOLD]
            if qualified:
                active_symbol = sorted(qualified, key=lambda symbol: (-current_rates[symbol], symbol))[0]
                entered = True
                episode += 1
                selection_counts[active_symbol] += 1
                entry_spot = data[active_symbol]["spot"][timestamp]
                entry_future = data[active_symbol]["futures"][timestamp]
                episode_returns[episode] = 0.0
                episode_symbols[episode] = active_symbol
        if active_symbol is None:
            rows.append({"time": next_timestamp, "year": datetime.fromtimestamp(next_timestamp / 1000, tz=timezone.utc).year, "active": False, "episode": None, "symbol": None, "basis": 0.0, "funding": 0.0, "cost": 0.0, "capital_return": 0.0})
        else:
            symbol = active_symbol
            basis_pnl = ((data[symbol]["spot"][next_timestamp] - data[symbol]["spot"][timestamp]) / entry_spot - (data[symbol]["futures"][next_timestamp] - data[symbol]["futures"][timestamp]) / entry_future)
            funding_pnl = next_rates[symbol] * data[symbol]["futures"][next_timestamp] / entry_future
            exit_now = next_rates[symbol] <= 0 or next_timestamp >= end_ms
            raw_cost = transition_cost * (int(entered) + int(exit_now))
            value = (basis_pnl + funding_pnl - raw_cost) / 2.0
            episode_returns[episode] += value
            rows.append({"time": next_timestamp, "year": datetime.fromtimestamp(next_timestamp / 1000, tz=timezone.utc).year, "active": True, "episode": episode, "symbol": symbol, "basis": basis_pnl / 2.0, "funding": funding_pnl / 2.0, "cost": -raw_cost / 2.0, "capital_return": value})
            if exit_now:
                active_symbol = None
        previous_rates = current_rates
    if active_symbol is not None:
        for row in reversed(rows):
            if row["active"] and row["episode"] == episode:
                exit_cost = transition_cost / 2.0
                row["cost"] -= exit_cost
                row["capital_return"] -= exit_cost
                episode_returns[episode] -= exit_cost
                forced_exit_time = row["time"]
                break
    metadata = {
        "per_symbol_alignment": per_symbol,
        "common_events_inclusive": len(common),
        "episodes": len(episode_returns),
        "episode_returns": [episode_returns[key] for key in sorted(episode_returns)],
        "episode_symbols": [episode_symbols[key] for key in sorted(episode_symbols)],
        "selection_counts": selection_counts,
        "forced_exit_at_last_event": base.iso_ms(forced_exit_time) if forced_exit_time else None,
    }
    return rows, metadata


def summarize(rows, metadata, seed: int):
    result = base.summarize(rows, metadata, seed)
    episodes = metadata["episode_returns"]
    result.update({
        "episode_median": statistics.median(episodes) if episodes else None,
        "selection_counts": metadata["selection_counts"],
        "episode_symbols": metadata["episode_symbols"],
    })
    return result


def command_analyze(args: argparse.Namespace) -> None:
    phase = PHASES[args.phase]
    if args.phase != "development" and (not args.authorization or not base.read_json(Path(args.authorization)).get("holdout_authorized")):
        raise RuntimeError("holdout is not authorized")
    manifest = base.read_json(Path(args.manifest))
    if manifest["universe"] != phase["universe"]:
        raise RuntimeError("manifest universe mismatch")
    data = load_inputs(Path(args.cache_dir).resolve(), manifest)
    scenarios, alignment = {}, None
    for offset, (name, cost) in enumerate(base.COSTS_COMBINED_TRANSITION.items()):
        rows, metadata = build_rows(data, tuple(manifest["symbols"]), base.parse_ms(phase["start"]), base.parse_ms(phase["end"]), cost)
        scenarios[name] = summarize(rows, metadata, 20260720 + offset)
        alignment = {key: value for key, value in metadata.items() if key not in {"episode_returns", "episode_symbols"}}
    output = {
        "schema_version": 1, "generated_at": base.utc_now(), "phase": args.phase,
        "universe": phase["universe"], "symbols": list(manifest["symbols"]),
        "period": {"start": phase["start"], "end_exclusive": phase["end"]},
        "manifest_content_identity": manifest["content_identity"], "study_code_sha256": sha256_path(Path(__file__)),
        "base_study_code_sha256": sha256_path(BASE_PATH),
        "rules": {"threshold_bps": 3.0, "persistence_events": PERSISTENCE, "max_simultaneous_assets": 1, "costs": base.COSTS_COMBINED_TRANSITION},
        "data_alignment": alignment, "favorable": scenarios["favorable"], "base": scenarios["base"], "stress": scenarios["stress"],
    }
    output["content_digest"] = base.canonical_digest({key: value for key, value in output.items() if key != "generated_at"})
    base.write_json(Path(args.output), output)
    print(json.dumps({"phase": args.phase, "base_return": output["base"]["return_noncompounded"], "episodes": output["base"]["episodes"]}))


def aligned(result) -> bool:
    return all(item["missing_event_prices"] == 0 for item in result["data_alignment"]["per_symbol_alignment"].values())


def command_qualify_development(args: argparse.Namespace) -> None:
    result = base.read_json(Path(args.development)); main = result["base"]
    passed = aligned(result) and main["return_noncompounded"] > 0 and result["stress"]["return_noncompounded"] > 0 and main["episodes"] >= 10 and main["active_intervals"] >= 100 and main["episode_median"] > 0 and main["positive_episode_fraction"] >= 0.5 and main["max_drawdown_noncompounded"] > -0.10
    output = {"generated_at": base.utc_now(), "development_content_digest": result["content_digest"], "qualification_status": "PASSED_DEVELOPMENT_GATE" if passed else "FAILED_DEVELOPMENT_GATE_STOP", "holdout_authorized": passed, "fixed_rule": "MULTI_ASSET_TWO_EVENT_3BP_CARRY"}
    output["content_digest"] = base.canonical_digest({key: value for key, value in output.items() if key != "generated_at"}); base.write_json(Path(args.output), output); print(json.dumps({"status": output["qualification_status"]}))


def command_qualify_evaluation(args: argparse.Namespace) -> None:
    result = base.read_json(Path(args.evaluation)); main = result["base"]
    passed = aligned(result) and main["return_noncompounded"] > 0 and result["stress"]["return_noncompounded"] > 0 and main["episodes"] >= 3 and main["active_intervals"] >= 30 and main["episode_median"] >= 0 and main["max_drawdown_noncompounded"] > -0.10
    output = {"generated_at": base.utc_now(), "evaluation_content_digest": result["content_digest"], "qualification_status": "PASSED_EVALUATION_GATE" if passed else "FAILED_EVALUATION_GATE_STOP", "holdout_authorized": passed, "fixed_rule": "MULTI_ASSET_TWO_EVENT_3BP_CARRY"}
    output["content_digest"] = base.canonical_digest({key: value for key, value in output.items() if key != "generated_at"}); base.write_json(Path(args.output), output); print(json.dumps({"status": output["qualification_status"]}))


def command_combine(args: argparse.Namespace) -> None:
    development = base.read_json(Path(args.development)); evaluation = base.read_json(Path(args.evaluation)); gate = base.read_json(Path(args.evaluation_gate)); confirmation = base.read_json(Path(args.confirmation)); main = confirmation["base"]
    both_symbols = all(count > 0 for count in main["selection_counts"].values())
    support = aligned(confirmation) and main["return_noncompounded"] > 0 and confirmation["stress"]["return_noncompounded"] > 0 and main["episodes"] >= 10 and main["active_intervals"] >= 100 and both_symbols and main["episode_median"] >= 0 and main["max_drawdown_noncompounded"] > -0.10
    evaluation_return = evaluation["base"]["return_noncompounded"]
    conclusion = "SUPPORTS_WITHIN_SCOPE" if gate["holdout_authorized"] and support else ("DOES_NOT_SUPPORT" if evaluation_return < 0 or main["return_noncompounded"] < 0 else "INSUFFICIENT_EVIDENCE")
    output = {"generated_at": base.utc_now(), "conclusion": conclusion, "scope": "same-venue one-asset-at-a-time two-event persistent positive funding cash-and-carry", "development": development["base"], "evaluation": evaluation["base"], "confirmation": main, "confirmation_support_gate": support, "formal_product_strategy_comparison": "NOT_RUN_ECONOMICALLY_INCOMPARABLE_SINGLE_LEG_TREND_STRATEGY", "product_effects": "NONE"}
    output["content_digest"] = base.canonical_digest({key: value for key, value in output.items() if key != "generated_at"}); base.write_json(Path(args.output), output); print(json.dumps({"conclusion": conclusion}))


def build_parser():
    parser = argparse.ArgumentParser(description="Multi-asset persistent funding cash-and-carry study"); sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch"); fetch.add_argument("--cache-dir", required=True); fetch.add_argument("--universe", choices=tuple(UNIVERSES), required=True); fetch.add_argument("--start-month", required=True); fetch.add_argument("--end-month", required=True); fetch.add_argument("--manifest", required=True); fetch.set_defaults(func=command_fetch)
    analyze = sub.add_parser("analyze"); analyze.add_argument("--cache-dir", required=True); analyze.add_argument("--manifest", required=True); analyze.add_argument("--phase", choices=tuple(PHASES), required=True); analyze.add_argument("--authorization"); analyze.add_argument("--output", required=True); analyze.set_defaults(func=command_analyze)
    dev = sub.add_parser("qualify-development"); dev.add_argument("--development", required=True); dev.add_argument("--output", required=True); dev.set_defaults(func=command_qualify_development)
    eva = sub.add_parser("qualify-evaluation"); eva.add_argument("--evaluation", required=True); eva.add_argument("--output", required=True); eva.set_defaults(func=command_qualify_evaluation)
    combine = sub.add_parser("combine"); combine.add_argument("--development", required=True); combine.add_argument("--evaluation", required=True); combine.add_argument("--evaluation-gate", required=True); combine.add_argument("--confirmation", required=True); combine.add_argument("--output", required=True); combine.set_defaults(func=command_combine)
    return parser


def main():
    args = build_parser().parse_args(); args.func(args)


if __name__ == "__main__":
    main()
