from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path


PARENT_PATH = Path(__file__).resolve().parent.parent / "multi-asset-persistent-funding-carry" / "study.py"
SPEC = importlib.util.spec_from_file_location("persistent_carry_parent", PARENT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load retained persistent-carry study")
parent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(parent)
base = parent.base

ENTRY_PERSISTENCE = 2
EXIT_PERSISTENCE = 2


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_rows(data, symbols, start_ms: int, end_ms: int, transition_cost: float):
    usable, per_symbol = {}, {}
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
    episode = nonpositive_streak = 0
    episode_returns, episode_symbols = {}, {}
    previous_rates = {symbol: None for symbol in symbols}
    selection_counts = {symbol: 0 for symbol in symbols}
    forced_exit_time = None
    for timestamp, next_timestamp in zip(common, common[1:]):
        current_rates = {symbol: data[symbol]["funding"][timestamp] for symbol in symbols}
        next_rates = {symbol: data[symbol]["funding"][next_timestamp] for symbol in symbols}
        entered = False
        if active_symbol is None:
            qualified = [symbol for symbol in symbols if previous_rates[symbol] is not None and previous_rates[symbol] > 0 and current_rates[symbol] > 0]
            if qualified:
                active_symbol = sorted(qualified, key=lambda symbol: (-current_rates[symbol], symbol))[0]
                entered = True; episode += 1; nonpositive_streak = 0; selection_counts[active_symbol] += 1
                entry_spot = data[active_symbol]["spot"][timestamp]; entry_future = data[active_symbol]["futures"][timestamp]
                episode_returns[episode] = 0.0; episode_symbols[episode] = active_symbol
        if active_symbol is None:
            rows.append({"time": next_timestamp, "year": datetime.fromtimestamp(next_timestamp / 1000, tz=timezone.utc).year, "active": False, "episode": None, "symbol": None, "basis": 0.0, "funding": 0.0, "cost": 0.0, "capital_return": 0.0})
        else:
            symbol = active_symbol
            basis_pnl = ((data[symbol]["spot"][next_timestamp] - data[symbol]["spot"][timestamp]) / entry_spot - (data[symbol]["futures"][next_timestamp] - data[symbol]["futures"][timestamp]) / entry_future)
            funding_pnl = next_rates[symbol] * data[symbol]["futures"][next_timestamp] / entry_future
            nonpositive_streak = nonpositive_streak + 1 if next_rates[symbol] <= 0 else 0
            exit_now = nonpositive_streak >= EXIT_PERSISTENCE or next_timestamp >= end_ms
            raw_cost = transition_cost * (int(entered) + int(exit_now))
            value = (basis_pnl + funding_pnl - raw_cost) / 2.0
            episode_returns[episode] += value
            rows.append({"time": next_timestamp, "year": datetime.fromtimestamp(next_timestamp / 1000, tz=timezone.utc).year, "active": True, "episode": episode, "symbol": symbol, "basis": basis_pnl / 2.0, "funding": funding_pnl / 2.0, "cost": -raw_cost / 2.0, "capital_return": value})
            if exit_now:
                active_symbol = None; nonpositive_streak = 0
        previous_rates = current_rates
    if active_symbol is not None:
        for row in reversed(rows):
            if row["active"] and row["episode"] == episode:
                exit_cost = transition_cost / 2.0; row["cost"] -= exit_cost; row["capital_return"] -= exit_cost; episode_returns[episode] -= exit_cost; forced_exit_time = row["time"]; break
    metadata = {"per_symbol_alignment": per_symbol, "common_events_inclusive": len(common), "episodes": len(episode_returns), "episode_returns": [episode_returns[key] for key in sorted(episode_returns)], "episode_symbols": [episode_symbols[key] for key in sorted(episode_symbols)], "selection_counts": selection_counts, "forced_exit_at_last_event": base.iso_ms(forced_exit_time) if forced_exit_time else None}
    return rows, metadata


def summarize(rows, metadata, seed: int):
    result = base.summarize(rows, metadata, seed); episodes = metadata["episode_returns"]
    result.update({"episode_median": statistics.median(episodes) if episodes else None, "selection_counts": metadata["selection_counts"], "episode_symbols": metadata["episode_symbols"]})
    return result


def command_fetch(args):
    parent.command_fetch(args)


def command_analyze(args):
    phase = parent.PHASES[args.phase]
    if args.phase != "development" and (not args.authorization or not base.read_json(Path(args.authorization)).get("holdout_authorized")):
        raise RuntimeError("holdout is not authorized")
    manifest = base.read_json(Path(args.manifest))
    if manifest["universe"] != phase["universe"]:
        raise RuntimeError("manifest universe mismatch")
    data = parent.load_inputs(Path(args.cache_dir).resolve(), manifest); scenarios, alignment = {}, None
    for offset, (name, cost) in enumerate(base.COSTS_COMBINED_TRANSITION.items()):
        rows, metadata = build_rows(data, tuple(manifest["symbols"]), base.parse_ms(phase["start"]), base.parse_ms(phase["end"]), cost)
        scenarios[name] = summarize(rows, metadata, 20260720 + offset); alignment = {key: value for key, value in metadata.items() if key not in {"episode_returns", "episode_symbols"}}
    output = {"schema_version": 1, "generated_at": base.utc_now(), "phase": args.phase, "universe": phase["universe"], "symbols": list(manifest["symbols"]), "period": {"start": phase["start"], "end_exclusive": phase["end"]}, "manifest_content_identity": manifest["content_identity"], "study_code_sha256": sha256_path(Path(__file__)), "parent_study_code_sha256": sha256_path(PARENT_PATH), "rules": {"entry": "two consecutive settled funding rates >0", "exit": "after two consecutive settled funding rates <=0, counting both", "max_simultaneous_assets": 1, "costs": base.COSTS_COMBINED_TRANSITION}, "data_alignment": alignment, "favorable": scenarios["favorable"], "base": scenarios["base"], "stress": scenarios["stress"]}
    output["content_digest"] = base.canonical_digest({key: value for key, value in output.items() if key != "generated_at"}); base.write_json(Path(args.output), output); print(json.dumps({"phase": args.phase, "base_return": output["base"]["return_noncompounded"], "episodes": output["base"]["episodes"]}))


def aligned(result):
    return all(item["missing_event_prices"] == 0 for item in result["data_alignment"]["per_symbol_alignment"].values())


def command_qualify_development(args):
    result = base.read_json(Path(args.development)); main = result["base"]
    passed = aligned(result) and main["return_noncompounded"] > 0 and result["stress"]["return_noncompounded"] > 0 and main["episodes"] >= 10 and main["active_intervals"] >= 100 and main["episode_median"] > 0 and main["positive_episode_fraction"] >= 0.5 and main["max_drawdown_noncompounded"] > -0.10
    output = {"generated_at": base.utc_now(), "development_content_digest": result["content_digest"], "qualification_status": "PASSED_DEVELOPMENT_GATE" if passed else "FAILED_DEVELOPMENT_GATE_STOP", "holdout_authorized": passed, "fixed_rule": "MULTI_ASSET_TWO_POSITIVE_IN_TWO_NONPOSITIVE_OUT_CARRY"}; output["content_digest"] = base.canonical_digest({key: value for key, value in output.items() if key != "generated_at"}); base.write_json(Path(args.output), output); print(json.dumps({"status": output["qualification_status"]}))


def command_qualify_evaluation(args):
    result = base.read_json(Path(args.evaluation)); main = result["base"]
    passed = aligned(result) and main["return_noncompounded"] > 0 and result["stress"]["return_noncompounded"] > 0 and main["episodes"] >= 5 and main["active_intervals"] >= 50 and main["episode_median"] >= 0 and main["positive_episode_fraction"] >= 0.5 and main["max_drawdown_noncompounded"] > -0.10
    output = {"generated_at": base.utc_now(), "evaluation_content_digest": result["content_digest"], "qualification_status": "PASSED_EVALUATION_GATE" if passed else "FAILED_EVALUATION_GATE_STOP", "holdout_authorized": passed, "fixed_rule": "MULTI_ASSET_TWO_POSITIVE_IN_TWO_NONPOSITIVE_OUT_CARRY"}; output["content_digest"] = base.canonical_digest({key: value for key, value in output.items() if key != "generated_at"}); base.write_json(Path(args.output), output); print(json.dumps({"status": output["qualification_status"]}))


def command_combine(args):
    development = base.read_json(Path(args.development)); evaluation = base.read_json(Path(args.evaluation)); gate = base.read_json(Path(args.evaluation_gate)); confirmation = base.read_json(Path(args.confirmation)); main = confirmation["base"]
    both_symbols = all(count > 0 for count in main["selection_counts"].values())
    support = aligned(confirmation) and main["return_noncompounded"] > 0 and confirmation["stress"]["return_noncompounded"] > 0 and main["episodes"] >= 10 and main["active_intervals"] >= 100 and both_symbols and main["episode_median"] >= 0 and main["positive_episode_fraction"] >= 0.5 and main["max_drawdown_noncompounded"] > -0.10
    evaluation_return = evaluation["base"]["return_noncompounded"]
    conclusion = "SUPPORTS_WITHIN_SCOPE" if gate["holdout_authorized"] and support else ("DOES_NOT_SUPPORT" if evaluation_return < 0 or main["return_noncompounded"] < 0 else "INSUFFICIENT_EVIDENCE")
    output = {"generated_at": base.utc_now(), "conclusion": conclusion, "scope": "same-venue one-asset-at-a-time funding-sign hysteresis cash-and-carry", "development": development["base"], "evaluation": evaluation["base"], "confirmation": main, "confirmation_support_gate": support, "formal_product_strategy_comparison": "NOT_RUN_ECONOMICALLY_INCOMPARABLE_SINGLE_LEG_TREND_STRATEGY", "product_effects": "NONE"}; output["content_digest"] = base.canonical_digest({key: value for key, value in output.items() if key != "generated_at"}); base.write_json(Path(args.output), output); print(json.dumps({"conclusion": conclusion}))


def build_parser():
    parser = argparse.ArgumentParser(description="Multi-asset funding-sign hysteresis carry study"); sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch"); fetch.add_argument("--cache-dir", required=True); fetch.add_argument("--universe", choices=tuple(parent.UNIVERSES), required=True); fetch.add_argument("--start-month", required=True); fetch.add_argument("--end-month", required=True); fetch.add_argument("--manifest", required=True); fetch.set_defaults(func=command_fetch)
    analyze = sub.add_parser("analyze"); analyze.add_argument("--cache-dir", required=True); analyze.add_argument("--manifest", required=True); analyze.add_argument("--phase", choices=tuple(parent.PHASES), required=True); analyze.add_argument("--authorization"); analyze.add_argument("--output", required=True); analyze.set_defaults(func=command_analyze)
    dev = sub.add_parser("qualify-development"); dev.add_argument("--development", required=True); dev.add_argument("--output", required=True); dev.set_defaults(func=command_qualify_development)
    eva = sub.add_parser("qualify-evaluation"); eva.add_argument("--evaluation", required=True); eva.add_argument("--output", required=True); eva.set_defaults(func=command_qualify_evaluation)
    combine = sub.add_parser("combine"); combine.add_argument("--development", required=True); combine.add_argument("--evaluation", required=True); combine.add_argument("--evaluation-gate", required=True); combine.add_argument("--confirmation", required=True); combine.add_argument("--output", required=True); combine.set_defaults(func=command_combine)
    return parser


def main():
    args = build_parser().parse_args(); args.func(args)


if __name__ == "__main__":
    main()
