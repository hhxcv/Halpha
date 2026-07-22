from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import vectorbt as vbt


HERE = Path(__file__).resolve().parent
ENGINE_PATH = HERE.parent / "perp-low-volatility-monthly-one-shot-long" / "study.py"
ENGINE_SPEC = importlib.util.spec_from_file_location("halpha_monthly_research_engine", ENGINE_PATH)
if ENGINE_SPEC is None or ENGINE_SPEC.loader is None:
    raise RuntimeError(f"cannot load the locked monthly research engine: {ENGINE_PATH}")
engine = importlib.util.module_from_spec(ENGINE_SPEC)
ENGINE_SPEC.loader.exec_module(engine)
engine_summarize = engine.summarize

CACHE_ROOT = Path(os.environ.get(
    "HALPHA_HIGH_VOLATILITY_SHORT_CACHE",
    "D:/projects/Codex/CodexHome/research-data/halpha/"
    "category-momentum-gated-one-shot-long/2026-07-22-v1",
))

STAGES = {
    "development": {
        "fetch_start": "2023-08-19T00:00:00Z",
        "start": "2024-01-01T00:00:00Z",
        "end_exclusive": "2025-01-01T00:00:00Z",
    },
    "evaluation": {
        "fetch_start": "2024-08-19T00:00:00Z",
        "start": "2025-01-01T00:00:00Z",
        "end_exclusive": "2026-01-01T00:00:00Z",
    },
    "confirmation": {
        "fetch_start": "2025-08-19T00:00:00Z",
        "start": "2026-01-01T00:00:00Z",
        "end_exclusive": "2026-07-01T00:00:00Z",
    },
}

CONFIG = {
    "strategy_id": "RESEARCH_PERP_VOL90_TOP3_MONTHLY_ONE_SHOT_SHORT_0P25X_V1",
    "direction": "SHORT_ONLY",
    "formation_days": 90,
    "top_targets": 3,
    "notional_fraction": 0.25,
    "target_min_median_quote_volume_30d": 10_000_000.0,
    "min_rankable_targets": 20,
    "annual_capital_hurdle": 0.04,
    "max_missing_funding_mark_fraction": 0.005,
    "max_excluded_trade_fraction": 0.05,
    "costs": {
        "favorable": {"fee_per_side": 0.0006, "slippage_per_side": 0.0, "funding_stress": False},
        "base": {"fee_per_side": 0.0006, "slippage_per_side": 0.0010, "funding_stress": False},
        "stress": {"fee_per_side": 0.0006, "slippage_per_side": 0.0020, "funding_stress": True},
    },
    "short_funding_stress": {
        "positive_benefit_multiplier": 0.5,
        "negative_cost_multiplier": 1.5,
    },
    "diagnostics": {
        "vol60": {"kind": "high_volatility", "formation_days": 60, "top_targets": 3},
        "vol120": {"kind": "high_volatility", "formation_days": 120, "top_targets": 3},
        "top5": {"kind": "high_volatility", "formation_days": 90, "top_targets": 5},
        "lowvol90": {"kind": "low_volatility", "formation_days": 90, "top_targets": 3},
        "loser90": {"kind": "loser_momentum", "formation_days": 90, "top_targets": 3},
        "scheduled_short": {"kind": "scheduled_short", "formation_days": 90, "top_targets": 3},
    },
}

# Rebind the validated engine to this question's immutable inputs and output directory.
engine.HERE = HERE
engine.CACHE_ROOT = CACHE_ROOT
engine.STAGES = STAGES
engine.CONFIG = CONFIG


def bound_file_hashes() -> dict[str, str]:
    return {
        "study_py_sha256": engine.sha256_file(Path(__file__)),
        "engine_py_sha256": engine.sha256_file(ENGINE_PATH),
        "preregistration_sha256": engine.sha256_file(HERE / "preregistration.md"),
        "sources_sha256": engine.sha256_file(HERE / "sources.md"),
    }


def command_checkpoint(_args: argparse.Namespace) -> None:
    engine.validate_universe_snapshot()
    checkpoint_path = HERE / "checkpoint.json"
    if checkpoint_path.exists():
        existing = engine.read_json(checkpoint_path)
        if (
            existing.get("config") != CONFIG
            or existing.get("universe", {}).get("categories") != engine.CATEGORY_MEMBERS
            or existing.get("universe", {}).get("target_symbols") != engine.TARGET_SYMBOLS
            or existing.get("files") != bound_file_hashes()
            or existing.get("environment") != engine.environment_identity()
        ):
            raise RuntimeError("existing checkpoint does not match current method or environment")
        print(json.dumps({"checkpoint": str(checkpoint_path), "digest": existing["content_digest"], "reused": True}))
        return
    payload = {
        "created_at_utc": engine.iso_now(),
        "baseline_commit": "0bdfeffa616260cebd2d2188ddc8deb9e85c77f4",
        "formal_strategy": {
            "id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT",
            "version": "1.0.1",
            "instrument": "BTCUSDT-PERP",
        },
        "research_kind": "STRATEGY_CANDIDATE",
        "question": (
            "Does a high trailing 90-day realized-volatility rank predict enough negative next-month absolute "
            "return among liquid current Binance perpetual targets to support a monthly SHORT one-shot plan "
            "after retail costs, actual funding, capital hurdle, simple baselines, and sequential time evidence?"
        ),
        "evidence_boundary": (
            "A 2022-2023 HIGHVOL90-LONG diagnostic from the prior question is exposed and is discovery evidence "
            "only. No 2022-2023 outcome can enter this gate. The fixed rule begins on previously unopened 2024 "
            "development data, followed only after PASS by 2025 evaluation and 2026-H1 confirmation. The fixed "
            "target list is a current-survivor rather than point-in-time market universe."
        ),
        "universe": {
            "path": str(engine.UNIVERSE_PATH),
            "sha256": engine.UNIVERSE_SHA256,
            "snapshot_time_utc": "2026-07-21T06:42:30Z",
            "categories": engine.CATEGORY_MEMBERS,
            "symbol_count": len(engine.SYMBOLS),
            "target_symbols": engine.TARGET_SYMBOLS,
            "target_symbol_count": len(engine.TARGET_SYMBOLS),
        },
        "stages": STAGES,
        "config": CONFIG,
        "stage_open_rule": (
            "development -> evaluation -> confirmation; next-stage download forbidden unless prior gate PASS"
        ),
        "allowed_fixes": (
            "retrieval, parsing, identity, completeness, deterministic statistics, or implementation defects only; "
            "no signal, direction, universe, cost, gate, period, baseline, or parameter changes after checkpoint"
        ),
        "forbidden_after_checkpoint": [
            "using the exposed 2022-2023 diagnostic as confirmatory evidence",
            "selecting a favorable target, direction, volatility lookback, month, or rank cutoff",
            "lowering costs or capital hurdle",
            "opening a later stage after gate failure",
            "treating the current target list or classifications as historical point-in-time facts",
        ],
        "files": bound_file_hashes(),
        "environment": engine.environment_identity(),
        "cache_root": str(CACHE_ROOT),
    }
    payload["content_digest"] = engine.canonical_digest(payload)
    engine.write_json(checkpoint_path, payload)
    print(json.dumps({"checkpoint": str(checkpoint_path), "digest": payload["content_digest"], "reused": False}))


def command_fetch(args: argparse.Namespace) -> None:
    checkpoint = engine.ensure_checkpoint()
    engine.stage_authorized(args.stage)
    spec = STAGES[args.stage]
    kline_start = pd.Timestamp(spec["fetch_start"])
    kline_end = engine.stage_kline_end(args.stage)
    archives = engine.fetch_target_archives(args.stage)
    manifest: dict[str, Any] = {
        "accessed_at_utc": engine.iso_now(),
        "stage": args.stage,
        "checkpoint_digest": checkpoint["content_digest"],
        "source": "Binance public USD-M REST and Binance Data Collection archives; no credentials",
        "periods": {
            "kline_start": str(kline_start),
            "kline_end_exclusive": str(kline_end),
            "funding_start": spec["start"],
            "funding_end_exclusive": spec["end_exclusive"],
        },
        "symbols": {},
    }
    for number, symbol in enumerate(engine.SYMBOLS, start=1):
        root = CACHE_ROOT / args.stage / symbol / "raw_highvol_short"
        manifest["symbols"][symbol] = {
            "category": engine.SYMBOL_TO_CATEGORY[symbol],
            "kline_pages": engine.fetch_pages(
                "/fapi/v1/klines",
                {"symbol": symbol, "interval": "1d"},
                "openTime",
                1500,
                kline_start,
                kline_end,
                root / "klines",
            ),
            "funding_archives": archives[symbol]["fundingRate"] if symbol in archives else [],
            "mark_price_archives": archives[symbol]["markPriceKlines"] if symbol in archives else [],
            "mark_price_gap_archives": archives[symbol]["markPriceKlines1m"] if symbol in archives else [],
        }
        if number % 10 == 0 or number == len(engine.SYMBOLS):
            print(json.dumps({"stage": args.stage, "fetched": number, "total": len(engine.SYMBOLS)}))
    manifest["content_digest"] = engine.canonical_digest(manifest)
    engine.write_json(HERE / f"source_manifest_{args.stage}.json", manifest)
    print(json.dumps({
        "manifest": str(HERE / f"source_manifest_{args.stage}.json"),
        "digest": manifest["content_digest"],
    }))


def adjusted_short_funding_rate(rate: float) -> float:
    if rate > 0:
        return rate * float(CONFIG["short_funding_stress"]["positive_benefit_multiplier"])
    return rate * float(CONFIG["short_funding_stress"]["negative_cost_multiplier"])


def signal_at(
    kind: str,
    target: str,
    decision: pd.Timestamp,
    feature: pd.DataFrame,
    median_volume: pd.DataFrame,
    top_targets: int,
) -> tuple[bool, dict[str, Any]]:
    target_feature = feature.at[decision, target] if target in feature.columns else np.nan
    target_volume = median_volume.at[decision, target]
    common = {
        "feature_value": None if pd.isna(target_feature) else float(target_feature),
        "target_median_quote_volume_30d": None if pd.isna(target_volume) else float(target_volume),
        "feature_rank": None,
        "rankable_targets": 0,
    }
    if pd.isna(target_volume) or float(target_volume) < float(CONFIG["target_min_median_quote_volume_30d"]):
        return False, common
    eligible: list[tuple[float, str]] = []
    for symbol in engine.TARGET_SYMBOLS:
        med = median_volume.at[decision, symbol]
        value = feature.at[decision, symbol] if symbol in feature.columns else np.nan
        if pd.notna(med) and float(med) >= float(CONFIG["target_min_median_quote_volume_30d"]):
            if kind == "scheduled_short":
                eligible.append((0.0, symbol))
            elif pd.notna(value):
                eligible.append((float(value), symbol))
    common["rankable_targets"] = len(eligible)
    if len(eligible) < int(CONFIG["min_rankable_targets"]):
        return False, common
    if kind == "scheduled_short":
        return True, common
    ascending = kind in {"low_volatility", "loser_momentum"}
    ordered = sorted(eligible, key=lambda row: (row[0], row[1]) if ascending else (-row[0], row[1]))
    ranking = [symbol for _value, symbol in ordered]
    if target not in ranking:
        return False, common
    rank = ranking.index(target) + 1
    common["feature_rank"] = rank
    return rank <= top_targets, common


def build_trades(
    stage: str,
    bars: dict[str, pd.DataFrame],
    funding: dict[str, pd.DataFrame],
    kind: str,
    formation_days: int,
    top_targets: int = 3,
) -> tuple[pd.DataFrame, int]:
    opens, closes, quote_volume = engine.make_matrices(bars, stage)
    log_returns = np.log(closes / closes.shift(1))
    if kind in {"low_volatility", "high_volatility"}:
        feature = log_returns.rolling(formation_days, min_periods=formation_days).std(ddof=1) * math.sqrt(365.0)
    elif kind == "loser_momentum":
        feature = closes / closes.shift(formation_days) - 1.0
    elif kind == "scheduled_short":
        feature = pd.DataFrame(np.nan, index=closes.index, columns=closes.columns)
    else:
        raise ValueError(f"unsupported signal kind: {kind}")
    median_volume = quote_volume.rolling(30, min_periods=30).median()
    start = pd.Timestamp(STAGES[stage]["start"])
    end = pd.Timestamp(STAGES[stage]["end_exclusive"])
    entries = pd.date_range(start, end, freq="MS", inclusive="left")
    decisions = entries - pd.Timedelta(days=1)
    rows: list[dict[str, Any]] = []
    excluded_missing_funding = 0
    for symbol in engine.TARGET_SYMBOLS:
        next_entry_after = start
        for decision in decisions:
            entry = decision + pd.Timedelta(days=1)
            exit_time = entry + pd.offsets.MonthBegin(1)
            hold_days = int((exit_time - entry).days)
            if entry < next_entry_after:
                continue
            entry_price = opens.at[entry, symbol] if entry in opens.index else np.nan
            exit_price = opens.at[exit_time, symbol] if exit_time in opens.index else np.nan
            if pd.isna(entry_price) or pd.isna(exit_price) or float(entry_price) <= 0 or float(exit_price) <= 0:
                continue
            active, diagnostics = signal_at(kind, symbol, decision, feature, median_volume, top_targets)
            if not active:
                continue
            entry_price = float(entry_price)
            exit_price = float(exit_price)
            quantity = float(CONFIG["notional_fraction"]) / entry_price
            rates = funding[symbol][(funding[symbol].index > entry) & (funding[symbol].index < exit_time)]
            if rates["markPrice"].isna().any():
                excluded_missing_funding += 1
                next_entry_after = exit_time + pd.Timedelta(days=1)
                continue
            actual_funding = float((quantity * rates["markPrice"] * rates["fundingRate"]).sum())
            stressed_rates = rates["fundingRate"].map(adjusted_short_funding_rate)
            stress_funding = float((quantity * rates["markPrice"] * stressed_rates).sum())
            rows.append({
                "trade_id": f"{stage}-{kind}-{symbol}-{entry.strftime('%Y%m%d')}-{formation_days}-{top_targets}",
                "stage": stage,
                "kind": kind,
                "symbol": symbol,
                "category": engine.SYMBOL_TO_CATEGORY[symbol],
                "decision_time": decision,
                "entry_time": entry,
                "exit_time": exit_time,
                "formation_days": formation_days,
                "hold_days": hold_days,
                "top_targets": top_targets,
                **diagnostics,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "quantity_per_unit_plan_capital": quantity,
                "funding_events": int(len(rates)),
                "actual_funding_return": actual_funding,
                "stress_funding_return": stress_funding,
                "gross_price_return": float(CONFIG["notional_fraction"]) * (1.0 - exit_price / entry_price),
            })
            next_entry_after = exit_time + pd.Timedelta(days=1)
    return pd.DataFrame(rows), excluded_missing_funding


def vectorbt_short_returns(trades: pd.DataFrame, fee: float, slippage: float) -> np.ndarray:
    if trades.empty:
        return np.array([], dtype=float)
    columns = trades["trade_id"].tolist()
    prices = pd.DataFrame(
        [trades["entry_price"].to_numpy(float), trades["exit_price"].to_numpy(float)],
        index=pd.Index([0, 1], name="step"),
        columns=columns,
    )
    quantity = trades["quantity_per_unit_plan_capital"].to_numpy(float)
    sizes = pd.DataFrame([-quantity, quantity], index=prices.index, columns=columns)
    portfolio = vbt.Portfolio.from_orders(
        prices,
        size=sizes,
        size_type="amount",
        direction="both",
        fees=fee,
        slippage=slippage,
        init_cash=1.0,
        freq="1D",
    )
    return portfolio.total_return().reindex(columns).to_numpy(float)


def manual_short_return(row: pd.Series, fee: float, slippage: float) -> float:
    quantity = float(row["quantity_per_unit_plan_capital"])
    entry_execution = float(row["entry_price"]) * (1.0 - slippage)
    exit_execution = float(row["exit_price"]) * (1.0 + slippage)
    return (
        quantity * (entry_execution - exit_execution)
        - quantity * entry_execution * fee
        - quantity * exit_execution * fee
    )


def attach_returns(trades: pd.DataFrame) -> pd.DataFrame:
    output = trades.copy()
    if output.empty:
        return output
    for scenario, assumptions in CONFIG["costs"].items():
        fee = float(assumptions["fee_per_side"])
        slippage = float(assumptions["slippage_per_side"])
        vectorbt_return = vectorbt_short_returns(output, fee, slippage)
        manual = output.apply(manual_short_return, axis=1, fee=fee, slippage=slippage).to_numpy(float)
        funding_column = "stress_funding_return" if assumptions["funding_stress"] else "actual_funding_return"
        output[f"{scenario}_price_cost_return"] = vectorbt_return
        output[f"{scenario}_reconciliation_error"] = vectorbt_return - manual
        output[f"{scenario}_net_return"] = vectorbt_return + output[funding_column].to_numpy(float)
        hurdle = (
            (1.0 + float(CONFIG["annual_capital_hurdle"]))
            ** (output["hold_days"].to_numpy(float) / 365.0)
            - 1.0
        )
        output[f"{scenario}_after_hurdle_return"] = (
            (1.0 + output[f"{scenario}_net_return"].to_numpy(float)) / (1.0 + hurdle) - 1.0
        )
    return output


def summarize(trades: pd.DataFrame) -> dict[str, Any]:
    result = engine_summarize(trades)
    if trades.empty:
        return result
    target_stats = result["by_target_base_after_hurdle"]
    eligible_targets = [value for value in target_stats.values() if value["trades"] >= 2]
    result["positive_target_fraction"] = (
        float(np.mean([value["mean"] > 0 for value in eligible_targets])) if eligible_targets else 0.0
    )
    drawdowns = [value["max_drawdown"] for value in eligible_targets]
    result["target_max_drawdown_median"] = float(np.median(drawdowns)) if drawdowns else -1.0
    result["target_max_drawdown_worst"] = float(np.min(drawdowns)) if drawdowns else -1.0
    return result


def command_analyze(args: argparse.Namespace) -> None:
    engine.ensure_checkpoint()
    engine.stage_authorized(args.stage)
    quality_path = HERE / f"data_quality_{args.stage}.json"
    if not quality_path.exists() or engine.read_json(quality_path)["status"] != "PASS":
        raise RuntimeError("stage data quality is not PASS")
    bars, funding = engine.load_all(args.stage)
    main_raw, main_excluded = build_trades(
        args.stage,
        bars,
        funding,
        "high_volatility",
        int(CONFIG["formation_days"]),
        int(CONFIG["top_targets"]),
    )
    main = attach_returns(main_raw)
    main.to_csv(HERE / f"{args.stage}_trades.csv", index=False, date_format="%Y-%m-%dT%H:%M:%SZ")
    main_summary = summarize(main)
    main_summary["excluded_trades_due_missing_funding_mark"] = main_excluded
    main_summary["excluded_trade_fraction"] = (
        float(main_excluded / (len(main) + main_excluded)) if len(main) + main_excluded else 0.0
    )
    diagnostic_results: dict[str, Any] = {}
    diagnostic_hashes: dict[str, str] = {}
    for name, spec in CONFIG["diagnostics"].items():
        raw, excluded = build_trades(
            args.stage,
            bars,
            funding,
            str(spec["kind"]),
            int(spec["formation_days"]),
            int(spec.get("top_targets", CONFIG["top_targets"])),
        )
        trades = attach_returns(raw)
        path = HERE / f"{args.stage}_{name}_trades.csv"
        trades.to_csv(path, index=False, date_format="%Y-%m-%dT%H:%M:%SZ")
        diagnostic_results[name] = summarize(trades)
        diagnostic_results[name]["excluded_trades_due_missing_funding_mark"] = excluded
        diagnostic_results[name]["excluded_trade_fraction"] = (
            float(excluded / (len(trades) + excluded)) if len(trades) + excluded else 0.0
        )
        diagnostic_hashes[name] = engine.sha256_file(path)
    payload = {
        "generated_at_utc": engine.iso_now(),
        "stage": args.stage,
        "period": {"start": STAGES[args.stage]["start"], "end_exclusive": STAGES[args.stage]["end_exclusive"]},
        "main": main_summary,
        "diagnostics": diagnostic_results,
        "search_disclosure": {
            "selectable_primary_configurations": 1,
            "parameter_neighborhoods_not_selectable": 3,
            "simple_baselines_not_selectable": 3,
        },
        "trade_csv_sha256": engine.sha256_file(HERE / f"{args.stage}_trades.csv"),
        "diagnostic_csv_sha256": diagnostic_hashes,
        "data_quality_digest": engine.read_json(quality_path)["content_digest"],
    }
    payload["content_digest"] = engine.canonical_digest(payload)
    engine.write_json(HERE / f"{args.stage}.json", payload)
    print(json.dumps({
        "stage": args.stage,
        "trades": payload["main"]["trades"],
        "base_after_hurdle": payload["main"]["scenarios"].get("base", {}).get("cohort_mean_after_hurdle"),
        "stress_after_hurdle": payload["main"]["scenarios"].get("stress", {}).get("cohort_mean_after_hurdle"),
    }))


def gate_checks(stage: str, result: dict[str, Any]) -> dict[str, bool]:
    main = result["main"]
    base = main.get("scenarios", {}).get("base", {})
    stress = main.get("scenarios", {}).get("stress", {})
    minimum_trades, minimum_targets, minimum_entry_dates = {
        "development": (15, 6, 8),
        "evaluation": (15, 6, 8),
        "confirmation": (8, 4, 4),
    }[stage]
    expected_years = {"development": ["2024"], "evaluation": ["2025"], "confirmation": ["2026"]}[stage]
    minimum_positive_categories = 2 if stage == "confirmation" else 3
    neighbors = ["vol60", "vol120", "top5"]
    return {
        "data_quality_pass": engine.read_json(HERE / f"data_quality_{stage}.json")["status"] == "PASS",
        "excluded_trade_fraction_at_most_limit": main.get("excluded_trade_fraction", 1.0) <= float(CONFIG["max_excluded_trade_fraction"]),
        "vectorbt_reconciled": main.get("maximum_vectorbt_reconciliation_error", 1.0) <= 1e-10,
        "trades_at_least_minimum": main.get("trades", 0) >= minimum_trades,
        "targets_at_least_minimum": main.get("targets", 0) >= minimum_targets,
        "entry_dates_at_least_minimum": main.get("entry_dates", 0) >= minimum_entry_dates,
        "categories_at_least_minimum": main.get("categories", 0) >= minimum_positive_categories,
        "base_after_hurdle_positive": base.get("cohort_mean_after_hurdle", -1.0) > 0,
        "stress_after_hurdle_positive": stress.get("cohort_mean_after_hurdle", -1.0) > 0,
        "stress_bootstrap_lower_positive": (stress.get("cohort_bootstrap_95pct") or [-1.0])[0] > 0,
        "required_year_slices_positive": all(
            main.get("by_year_base_after_hurdle", {}).get(year, -1.0) > 0 for year in expected_years
        ),
        "positive_target_fraction_at_least_half": main.get("positive_target_fraction", 0.0) >= 0.5,
        "positive_categories_at_least_minimum": main.get("positive_category_count", 0) >= minimum_positive_categories,
        "beats_lowvol90": base.get("cohort_mean_after_hurdle", -1.0) > result["diagnostics"]["lowvol90"].get("scenarios", {}).get("base", {}).get("cohort_mean_after_hurdle", 1.0),
        "beats_loser90": base.get("cohort_mean_after_hurdle", -1.0) > result["diagnostics"]["loser90"].get("scenarios", {}).get("base", {}).get("cohort_mean_after_hurdle", 1.0),
        "beats_scheduled_short": base.get("cohort_mean_after_hurdle", -1.0) > result["diagnostics"]["scheduled_short"].get("scenarios", {}).get("base", {}).get("cohort_mean_after_hurdle", 1.0),
        "two_of_three_neighborhoods_stress_positive": sum(
            result["diagnostics"][name].get("scenarios", {}).get("stress", {}).get("cohort_mean_after_hurdle", -1.0) > 0
            for name in neighbors
        ) >= 2,
        "largest_positive_target_share_at_most_40pct": main.get("largest_positive_target_pnl_share", 1.0) <= 0.40,
        "median_target_drawdown_above_minus_15pct": main.get("target_max_drawdown_median", -1.0) > -0.15,
        "worst_target_drawdown_above_minus_30pct": main.get("target_max_drawdown_worst", -1.0) > -0.30,
    }


def conclusion_for_failed_gate(result: dict[str, Any]) -> str:
    main = result["main"]
    scenarios = main.get("scenarios", {})
    minimum_trades, minimum_targets = {
        "development": (15, 6),
        "evaluation": (15, 6),
        "confirmation": (8, 4),
    }[result["stage"]]
    sample_ok = main.get("trades", 0) >= minimum_trades and main.get("targets", 0) >= minimum_targets
    economic_positive = all(
        scenarios.get(name, {}).get("cohort_mean_after_hurdle", -1.0) > 0 for name in ["base", "stress"]
    )
    return "INSUFFICIENT_EVIDENCE" if sample_ok and economic_positive else "DOES_NOT_SUPPORT"


def command_conclude(_args: argparse.Namespace) -> None:
    gates = {stage: engine.read_json(HERE / f"{stage}_gate.json") for stage in STAGES}
    if not all(gate["status"] == "PASS" for gate in gates.values()):
        raise RuntimeError("cannot conclude support unless all sequential gates PASS")
    stages = {stage: engine.read_json(HERE / f"{stage}.json") for stage in STAGES}
    combined_later_mean = float(np.mean([
        stages[stage]["main"]["scenarios"]["base"]["cohort_mean_after_hurdle"]
        for stage in ["evaluation", "confirmation"]
    ]))
    if combined_later_mean <= 0:
        raise RuntimeError("evaluation and confirmation combined mean is not positive")
    handoff = {
        "candidate_id": CONFIG["strategy_id"],
        "version": "1",
        "allowed_direction": "SHORT",
        "notional_fraction_of_plan_capital": CONFIG["notional_fraction"],
        "inputs": ["daily OHLCV including quote volume for the fixed target universe", "UTC bar close/open timestamps"],
        "warmup_days": 120,
        "decision": (
            "Before each UTC month-start open, require at least 20 targets with 30d median quote volume >=10m "
            "and complete VOL90. Compute annualized sample standard deviation of the prior 90 complete daily log "
            "returns, rank descending with symbol as deterministic tie-break, and propose SHORT for ranks one to three."
        ),
        "entry": "next UTC calendar-month first daily open",
        "exit": "next calendar-month first UTC daily open; require one full UTC day before reactivation",
        "unknown_no_action": "missing, stale, discontinuous, invalid, insufficient targets, or incomplete ranking input",
        "costs": CONFIG["costs"],
        "unsupported_execution_facts": [
            "historical book depth",
            "queue and partial fills",
            "intraday margin/liquidation/ADL",
            "user reactivation latency",
        ],
        "framework_neutral_trace": [
            {"case": "rank_three", "target_volume_ok": True, "rankable_targets": 23, "vol90": 1.22, "feature_rank": 3, "proposal": "SHORT_ENTRY_NEXT_MONTH_OPEN"},
            {"case": "rank_four", "target_volume_ok": True, "rankable_targets": 23, "vol90": 1.21, "feature_rank": 4, "proposal": "NO_ACTION"},
            {"case": "insufficient_universe", "target_volume_ok": True, "rankable_targets": 19, "vol90": 1.22, "feature_rank": None, "proposal": "NO_ACTION"},
        ],
        "research_result_digest": {stage: stages[stage]["content_digest"] for stage in STAGES},
        "limitations": (
            "Current-survivor fixed target list, not a point-in-time full market; daily bars cannot model intraday "
            "short-squeeze or book liquidity; research result does not authorize product or trading use."
        ),
    }
    handoff["content_digest"] = engine.canonical_digest(handoff)
    engine.write_json(HERE / "handoff.json", handoff)
    result = {
        "generated_at_utc": engine.iso_now(),
        "conclusion": "SUPPORTS_WITHIN_SCOPE",
        "stage_gates": {stage: gate["status"] for stage, gate in gates.items()},
        "stages": {stage: value["main"] for stage, value in stages.items()},
        "evaluation_confirmation_mean": combined_later_mean,
        "handoff_sha256": engine.sha256_file(HERE / "handoff.json"),
        "product_effects": "NONE",
    }
    result["content_digest"] = engine.canonical_digest(result)
    engine.write_json(HERE / "results.json", result)
    print(json.dumps({"conclusion": result["conclusion"], "handoff": str(HERE / "handoff.json")}))


# Install question-specific behavior into the shared engine before delegating reusable commands.
engine.bound_file_hashes = bound_file_hashes
engine.command_checkpoint = command_checkpoint
engine.command_fetch = command_fetch
engine.adjusted_short_funding_rate = adjusted_short_funding_rate
engine.signal_at = signal_at
engine.build_trades = build_trades
engine.vectorbt_short_returns = vectorbt_short_returns
engine.manual_short_return = manual_short_return
engine.attach_returns = attach_returns
engine.summarize = summarize
engine.command_analyze = command_analyze
engine.gate_checks = gate_checks
engine.conclusion_for_failed_gate = conclusion_for_failed_gate
engine.command_conclude = command_conclude


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="High-volatility monthly one-shot SHORT study")
    subparsers = parser.add_subparsers(dest="command", required=True)
    checkpoint = subparsers.add_parser("checkpoint")
    checkpoint.set_defaults(func=command_checkpoint)
    for command, function in [
        ("fetch", command_fetch),
        ("inspect", engine.command_inspect),
        ("analyze", command_analyze),
        ("gate", engine.command_gate),
    ]:
        item = subparsers.add_parser(command)
        item.add_argument("--stage", choices=tuple(STAGES), required=True)
        item.set_defaults(func=function)
    conclude = subparsers.add_parser("conclude")
    conclude.set_defaults(func=command_conclude)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
