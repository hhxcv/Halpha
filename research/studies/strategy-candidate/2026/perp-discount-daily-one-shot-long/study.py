from __future__ import annotations

import argparse
import importlib.util
import io
import json
import math
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


HERE = Path(__file__).resolve().parent
ENGINE_PATH = HERE.parent / "perp-low-volatility-monthly-one-shot-long" / "study.py"
SPEC = importlib.util.spec_from_file_location("halpha_daily_basis_engine", ENGINE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load research engine: {ENGINE_PATH}")
engine = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(engine)
engine_summarize = engine.summarize
engine_bootstrap = engine.circular_block_bootstrap

CACHE_ROOT = Path(os.environ.get(
    "HALPHA_PERP_DISCOUNT_CACHE",
    "D:/projects/Codex/CodexHome/research-data/halpha/"
    "category-momentum-gated-one-shot-long/2026-07-22-v1",
))
STAGES = {
    "development": {
        "fetch_start": "2021-11-17T00:00:00Z",
        "start": "2022-01-01T00:00:00Z",
        "end_exclusive": "2024-01-01T00:00:00Z",
    },
    "evaluation": {
        "fetch_start": "2023-11-17T00:00:00Z",
        "start": "2024-01-01T00:00:00Z",
        "end_exclusive": "2025-01-01T00:00:00Z",
    },
    "confirmation": {
        "fetch_start": "2024-11-17T00:00:00Z",
        "start": "2025-01-01T00:00:00Z",
        "end_exclusive": "2026-07-01T00:00:00Z",
    },
}
TARGETS = list(engine.TARGET_SYMBOLS)
CONFIG = {
    "strategy_id": "RESEARCH_PERP_PREMIUM1_BOTTOM3_DAILY_ONE_SHOT_LONG_0P25X_V1",
    "direction": "LONG_ONLY",
    "top_targets": 3,
    "notional_fraction": 0.25,
    "target_min_median_quote_volume_30d": 10_000_000.0,
    "min_rankable_targets": 20,
    "annual_capital_hurdle": 0.04,
    "max_missing_funding_mark_fraction": 0.005,
    "max_excluded_trade_fraction": 0.05,
    "bootstrap_block_days": 14,
    "costs": {
        "favorable": {"fee_per_side": 0.0006, "slippage_per_side": 0.0, "funding_stress": False},
        "base": {"fee_per_side": 0.0006, "slippage_per_side": 0.0010, "funding_stress": False},
        "stress": {"fee_per_side": 0.0006, "slippage_per_side": 0.0020, "funding_stress": True},
    },
    "long_funding_stress": {"positive_cost_multiplier": 1.5, "negative_benefit_multiplier": 0.5},
    "diagnostics": {
        "premium3": {"kind": "premium_discount", "lookback_days": 3, "top_targets": 3},
        "premium5": {"kind": "premium_discount", "lookback_days": 5, "top_targets": 3},
        "bottom5": {"kind": "premium_discount", "lookback_days": 1, "top_targets": 5},
        "funding1": {"kind": "funding_discount", "lookback_days": 1, "top_targets": 3},
        "momentum5": {"kind": "momentum", "lookback_days": 5, "top_targets": 3},
        "scheduled_long": {"kind": "scheduled_long", "lookback_days": 1, "top_targets": 3},
    },
}

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


def ensure_checkpoint() -> dict[str, Any]:
    checkpoint = engine.read_json(HERE / "checkpoint.json")
    if (
        checkpoint.get("config") != CONFIG
        or checkpoint.get("universe", {}).get("categories") != engine.CATEGORY_MEMBERS
        or checkpoint.get("universe", {}).get("target_symbols") != TARGETS
        or checkpoint.get("environment") != engine.environment_identity()
    ):
        raise RuntimeError("checkpoint differs from fixed method, universe, or environment")
    current = bound_file_hashes()
    authorized = checkpoint.get("files")
    for amendment_path in sorted(HERE.glob("checkpoint_amendment_*.json")):
        amendment = engine.read_json(amendment_path)
        digest = amendment.pop("content_digest", None)
        if digest != engine.canonical_digest(amendment):
            raise RuntimeError(f"checkpoint amendment digest mismatch: {amendment_path.name}")
        if (
            amendment.get("checkpoint_digest") != checkpoint.get("content_digest")
            or amendment.get("previous_files") != authorized
            or amendment.get("classification") not in {
                "ALLOWED_DATA_COMPLETENESS_FIX", "ALLOWED_DETERMINISTIC_PERFORMANCE_FIX"
            }
            or amendment.get("economic_method_changed") is not False
        ):
            raise RuntimeError(f"invalid checkpoint amendment chain: {amendment_path.name}")
        authorized = amendment.get("current_files")
    if authorized != current:
        raise RuntimeError("checkpoint-bound files changed without a matching amendment chain")
    engine.validate_universe_snapshot()
    return checkpoint


def command_checkpoint(_args: argparse.Namespace) -> None:
    engine.validate_universe_snapshot()
    path = HERE / "checkpoint.json"
    if path.exists():
        existing = ensure_checkpoint()
        print(json.dumps({
            "checkpoint": str(path), "digest": existing["content_digest"], "reused": True,
            "amendments": len(list(HERE.glob("checkpoint_amendment_*.json"))),
        }))
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
            "Does a negative prior-day Binance premium-index rank predict enough next-day absolute return among "
            "liquid current USD-M perpetual targets to support a 0.25x LONG one-shot plan after actual funding, "
            "retail costs, a capital hurdle, simple baselines, robustness neighborhoods, and sequential time gates?"
        ),
        "evidence_boundary": (
            "Price bytes and unrelated 2022-2024 strategy outcomes are exposed, so development and evaluation are "
            "not described as blind market samples. The official premium feature, selected trades, and results have "
            "not been computed. Only 2025-2026H1 is the relatively clean final time holdout, opened only after both "
            "earlier gates pass. The fixed target list is a current-survivor universe."
        ),
        "universe": {
            "path": str(engine.UNIVERSE_PATH),
            "sha256": engine.UNIVERSE_SHA256,
            "snapshot_time_utc": "2026-07-21T06:42:30Z",
            "categories": engine.CATEGORY_MEMBERS,
            "symbol_count": len(engine.SYMBOLS),
            "target_symbols": TARGETS,
            "target_symbol_count": len(TARGETS),
        },
        "stages": STAGES,
        "config": CONFIG,
        "stage_open_rule": "development -> evaluation -> confirmation; later download requires prior PASS",
        "allowed_fixes": (
            "retrieval, parsing, identity, completeness, deterministic statistics, or implementation defects only; "
            "no signal, direction, universe, cost, gate, stage, baseline, threshold, or parameter changes"
        ),
        "forbidden_after_checkpoint": [
            "selecting premium bars, lookback, rank, direction, target, day, or stage from outcomes",
            "removing the negative-premium condition",
            "lowering costs, hurdle, or statistical and robustness gates",
            "opening a later stage after failure",
            "calling a single-leg directional position cash-and-carry arbitrage",
        ],
        "files": bound_file_hashes(),
        "environment": engine.environment_identity(),
        "cache_root": str(CACHE_ROOT),
    }
    payload["content_digest"] = engine.canonical_digest(payload)
    engine.write_json(path, payload)
    print(json.dumps({"checkpoint": str(path), "digest": payload["content_digest"], "reused": False}))


def archive_storage_stage(stage: str) -> str:
    # Month-qualified filenames let 2022-2024 coexist and reuse earlier checksum-verified downloads.
    return "development" if stage in {"development", "evaluation"} else "confirmation"


def fetch_archives(stage: str) -> dict[str, dict[str, list[dict[str, Any]]]]:
    storage = archive_storage_stage(stage)
    tasks = [
        (storage, symbol, month, kind)
        for symbol in TARGETS
        for month in engine.month_labels(stage)
        for kind in ["fundingRate", "markPriceKlines"]
    ]
    results: list[dict[str, Any]] = []
    with engine.concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(engine.fetch_archive, task) for task in tasks]
        for number, future in enumerate(futures, 1):
            results.append(future.result())
            if number % 200 == 0 or number == len(futures):
                print(json.dumps({"stage": stage, "archive_files": number, "total": len(futures)}))
    output = {symbol: {"fundingRate": [], "markPriceKlines": [], "markPriceKlines1m": []} for symbol in TARGETS}
    for task, result in zip(tasks, results, strict=True):
        _storage, symbol, _month, kind = task
        output[symbol][kind].append(result)
    gaps = [
        (storage, symbol, month, "markPriceKlines1m")
        for symbol in TARGETS
        for month in engine.missing_mark_months(output[symbol]["fundingRate"], output[symbol]["markPriceKlines"])
    ]
    if gaps:
        with engine.concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(engine.fetch_archive, task) for task in gaps]
            for task, future in zip(gaps, futures, strict=True):
                _storage, symbol, _month, kind = task
                output[symbol][kind].append(future.result())
    return output


def command_fetch(args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    engine.stage_authorized(args.stage)
    spec = STAGES[args.stage]
    start = pd.Timestamp(spec["fetch_start"])
    price_end = pd.Timestamp(spec["end_exclusive"]) + pd.Timedelta(days=1)
    signal_end = pd.Timestamp(spec["end_exclusive"])
    archives = fetch_archives(args.stage)
    manifest: dict[str, Any] = {
        "accessed_at_utc": engine.iso_now(),
        "stage": args.stage,
        "checkpoint_digest": checkpoint["content_digest"],
        "source": "Binance public USD-M REST and official monthly archives; no credentials",
        "periods": {
            "input_start": str(start),
            "price_end_exclusive": str(price_end),
            "premium_end_exclusive": str(signal_end),
            "funding_start": spec["start"],
            "funding_end_exclusive": spec["end_exclusive"],
        },
        "symbols": {},
    }
    for number, symbol in enumerate(TARGETS, 1):
        root = CACHE_ROOT / "perp-discount-daily" / args.stage / symbol
        manifest["symbols"][symbol] = {
            "category": engine.SYMBOL_TO_CATEGORY[symbol],
            "kline_pages": engine.fetch_pages(
                "/fapi/v1/klines", {"symbol": symbol, "interval": "1d"}, "openTime", 1500,
                start, price_end, root / "klines",
            ),
            "premium_pages": engine.fetch_pages(
                "/fapi/v1/premiumIndexKlines", {"symbol": symbol, "interval": "8h"}, "openTime", 1500,
                start, signal_end, root / "premium8h",
            ),
            "funding_archives": archives[symbol]["fundingRate"],
            "mark_price_archives": archives[symbol]["markPriceKlines"],
            "mark_price_gap_archives": archives[symbol]["markPriceKlines1m"],
        }
        if number % 5 == 0 or number == len(TARGETS):
            print(json.dumps({"stage": args.stage, "fetched": number, "total": len(TARGETS)}))
    manifest["content_digest"] = engine.canonical_digest(manifest)
    engine.write_json(HERE / f"source_manifest_{args.stage}.json", manifest)
    print(json.dumps({"manifest": str(HERE / f"source_manifest_{args.stage}.json"), "digest": manifest["content_digest"]}))


def load_premium(stage: str, symbol: str) -> pd.Series:
    item = engine.read_json(HERE / f"source_manifest_{stage}.json")["symbols"][symbol]
    rows = engine.load_rows(item["premium_pages"])
    frame = pd.DataFrame(rows, columns=[
        "open_time", "open", "high", "low", "close", "ignore1", "close_time", "ignore2",
        "ignore3", "ignore4", "ignore5", "ignore6",
    ])
    frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    frame["close"] = pd.to_numeric(frame["close"], errors="raise")
    frame = frame.drop_duplicates("open_time", keep="last").sort_values("open_time").set_index("open_time")
    return frame["close"].rename(symbol)


def load_all(stage: str) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame], dict[str, pd.Series]]:
    bars: dict[str, pd.DataFrame] = {}
    funding: dict[str, pd.DataFrame] = {}
    premium: dict[str, pd.Series] = {}
    for symbol in TARGETS:
        bars[symbol], funding[symbol] = engine.load_symbol(stage, symbol)
        premium[symbol] = load_premium(stage, symbol)
    return bars, funding, premium


def command_inspect(args: argparse.Namespace) -> None:
    ensure_checkpoint()
    engine.stage_authorized(args.stage)
    bars, funding, premium = load_all(args.stage)
    spec = STAGES[args.stage]
    required_start = pd.Timestamp(spec["start"]) - pd.Timedelta(days=30)
    daily_expected = pd.date_range(required_start, pd.Timestamp(spec["end_exclusive"]) + pd.Timedelta(days=1), freq="1D", inclusive="left")
    premium_expected = pd.date_range(required_start, spec["end_exclusive"], freq="8h", inclusive="left")
    payload: dict[str, Any] = {"checked_at_utc": engine.iso_now(), "stage": args.stage, "status": "PASS", "symbols": {}}
    for symbol in TARGETS:
        bar = bars[symbol]
        rate = funding[symbol]
        prem = premium[symbol]
        missing_daily = daily_expected.difference(bar.index)
        missing_premium = premium_expected.difference(prem.index)
        invalid_ohlc = int(((bar[["open", "high", "low", "close"]] <= 0) | ~np.isfinite(bar[["open", "high", "low", "close"]])).sum().sum())
        invalid_range = int(((bar["high"] < bar[["open", "close"]].max(axis=1)) | (bar["low"] > bar[["open", "close"]].min(axis=1))).sum())
        invalid_volume = int(((bar["quote_volume"] < 0) | ~np.isfinite(bar["quote_volume"])).sum())
        missing_mark = int(rate["markPrice"].isna().sum())
        missing_mark_fraction = float(missing_mark / len(rate)) if len(rate) else 1.0
        max_gap = float(rate.index.to_series().diff().dt.total_seconds().max() / 3600.0) if len(rate) > 1 else math.inf
        ok = (
            len(missing_daily) == 0 and len(missing_premium) == 0 and invalid_ohlc == 0
            and invalid_range == 0 and invalid_volume == 0 and prem.notna().all()
            and np.isfinite(prem).all() and missing_mark_fraction <= float(CONFIG["max_missing_funding_mark_fraction"])
            and max_gap <= 8.1
        )
        if not ok:
            payload["status"] = "FAIL"
        payload["symbols"][symbol] = {
            "status": "PASS" if ok else "FAIL",
            "daily_rows": int(len(bar)), "missing_daily": int(len(missing_daily)),
            "premium_8h_rows": int(len(prem)), "missing_premium_8h": int(len(missing_premium)),
            "invalid_ohlc": invalid_ohlc, "invalid_range": invalid_range, "invalid_volume": invalid_volume,
            "funding_rows": int(len(rate)), "missing_funding_mark_price": missing_mark,
            "missing_funding_mark_fraction": missing_mark_fraction, "max_funding_gap_hours": max_gap,
        }
    manifest_path = HERE / f"source_manifest_{args.stage}.json"
    payload["manifest_sha256"] = engine.sha256_file(manifest_path)
    payload["content_digest"] = engine.canonical_digest(payload)
    engine.write_json(HERE / f"data_quality_{args.stage}.json", payload)
    print(json.dumps({"stage": args.stage, "status": payload["status"]}))


_INPUT_CACHE: dict[tuple[str, int, int, int], tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]] = {}


def make_inputs(
    stage: str,
    bars: dict[str, pd.DataFrame],
    funding: dict[str, pd.DataFrame],
    premium: dict[str, pd.Series],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    cache_key = (stage, id(bars), id(funding), id(premium))
    if cache_key in _INPUT_CACHE:
        return _INPUT_CACHE[cache_key]
    spec = STAGES[stage]
    daily_index = pd.date_range(spec["fetch_start"], pd.Timestamp(spec["end_exclusive"]), freq="1D", inclusive="both")
    opens = pd.DataFrame(index=daily_index, columns=TARGETS, dtype=float)
    closes = opens.copy()
    quote_volume = opens.copy()
    premium_daily = pd.DataFrame(index=daily_index, columns=TARGETS, dtype=float)
    funding_daily = pd.DataFrame(index=daily_index, columns=TARGETS, dtype=float)
    for symbol in TARGETS:
        opens[symbol] = bars[symbol]["open"].reindex(daily_index)
        closes[symbol] = bars[symbol]["close"].reindex(daily_index)
        quote_volume[symbol] = bars[symbol]["quote_volume"].reindex(daily_index)
        premium_daily[symbol] = premium[symbol].resample("1D").mean().reindex(daily_index)
        funding_daily[symbol] = funding[symbol]["fundingRate"].resample("1D").mean().reindex(daily_index)
    output = (opens, closes, quote_volume, premium_daily, funding_daily)
    _INPUT_CACHE[cache_key] = output
    return output


def signal_at(
    kind: str,
    target: str,
    decision: pd.Timestamp,
    feature: pd.DataFrame,
    median_volume: pd.DataFrame,
    top_targets: int,
) -> tuple[bool, dict[str, Any]]:
    value = feature.at[decision, target] if target in feature.columns else np.nan
    volume = median_volume.at[decision, target]
    common = {
        "feature_value": None if pd.isna(value) else float(value),
        "target_median_quote_volume_30d": None if pd.isna(volume) else float(volume),
        "feature_rank": None,
        "rankable_targets": 0,
    }
    if pd.isna(volume) or float(volume) < float(CONFIG["target_min_median_quote_volume_30d"]):
        return False, common
    eligible: list[tuple[float, str]] = []
    for symbol in TARGETS:
        med = median_volume.at[decision, symbol]
        item = feature.at[decision, symbol] if symbol in feature.columns else np.nan
        if pd.notna(med) and float(med) >= float(CONFIG["target_min_median_quote_volume_30d"]):
            if kind == "scheduled_long":
                eligible.append((0.0, symbol))
            elif pd.notna(item):
                eligible.append((float(item), symbol))
    common["rankable_targets"] = len(eligible)
    if len(eligible) < int(CONFIG["min_rankable_targets"]):
        return False, common
    if kind == "scheduled_long":
        return True, common
    ascending = kind in {"premium_discount", "funding_discount"}
    ordered = sorted(eligible, key=lambda row: (row[0], row[1]) if ascending else (-row[0], row[1]))
    ranking = [symbol for _value, symbol in ordered]
    if target not in ranking:
        return False, common
    rank = ranking.index(target) + 1
    common["feature_rank"] = rank
    if kind in {"premium_discount", "funding_discount"} and float(value) >= 0:
        return False, common
    return rank <= top_targets, common


def build_trades(
    stage: str,
    bars: dict[str, pd.DataFrame],
    funding: dict[str, pd.DataFrame],
    premium: dict[str, pd.Series],
    kind: str,
    lookback_days: int,
    top_targets: int,
) -> tuple[pd.DataFrame, int]:
    opens, closes, quote_volume, premium_daily, funding_daily = make_inputs(stage, bars, funding, premium)
    if kind == "premium_discount":
        feature = premium_daily.rolling(lookback_days, min_periods=lookback_days).mean()
    elif kind == "funding_discount":
        feature = funding_daily.rolling(lookback_days, min_periods=lookback_days).mean()
    elif kind == "momentum":
        feature = closes / closes.shift(lookback_days) - 1.0
    elif kind == "scheduled_long":
        feature = pd.DataFrame(np.nan, index=closes.index, columns=closes.columns)
    else:
        raise ValueError(kind)
    median_volume = quote_volume.rolling(30, min_periods=30).median()
    start = pd.Timestamp(STAGES[stage]["start"])
    end = pd.Timestamp(STAGES[stage]["end_exclusive"])
    decisions = pd.date_range(start - pd.Timedelta(days=1), end - pd.Timedelta(days=1), freq="1D")
    rows: list[dict[str, Any]] = []
    excluded = 0
    for symbol in TARGETS:
        next_entry_after = start
        for decision in decisions:
            entry = decision + pd.Timedelta(days=1)
            exit_time = entry + pd.Timedelta(days=1)
            if entry < next_entry_after:
                continue
            entry_price = opens.at[entry, symbol] if entry in opens.index else np.nan
            exit_price = opens.at[exit_time, symbol] if exit_time in opens.index else np.nan
            if pd.isna(entry_price) or pd.isna(exit_price) or float(entry_price) <= 0 or float(exit_price) <= 0:
                continue
            active, diagnostics = signal_at(kind, symbol, decision, feature, median_volume, top_targets)
            if not active:
                continue
            entry_price, exit_price = float(entry_price), float(exit_price)
            quantity = float(CONFIG["notional_fraction"]) / entry_price
            rates = funding[symbol][(funding[symbol].index > entry) & (funding[symbol].index < exit_time)]
            if rates["markPrice"].isna().any():
                excluded += 1
                next_entry_after = exit_time + pd.Timedelta(days=1)
                continue
            actual_funding = float((-quantity * rates["markPrice"] * rates["fundingRate"]).sum())
            stressed = rates["fundingRate"].map(engine.adjusted_long_funding_rate)
            stress_funding = float((-quantity * rates["markPrice"] * stressed).sum())
            rows.append({
                "trade_id": f"{stage}-{kind}-{symbol}-{entry.strftime('%Y%m%d')}-{lookback_days}-{top_targets}",
                "stage": stage, "kind": kind, "symbol": symbol,
                "category": engine.SYMBOL_TO_CATEGORY[symbol],
                "decision_time": decision, "entry_time": entry, "exit_time": exit_time,
                "lookback_days": lookback_days, "hold_days": 1, "top_targets": top_targets,
                **diagnostics,
                "entry_price": entry_price, "exit_price": exit_price,
                "quantity_per_unit_plan_capital": quantity, "funding_events": int(len(rates)),
                "actual_funding_return": actual_funding, "stress_funding_return": stress_funding,
                "gross_price_return": float(CONFIG["notional_fraction"]) * (exit_price / entry_price - 1.0),
            })
            next_entry_after = exit_time + pd.Timedelta(days=1)
    return pd.DataFrame(rows), excluded


def summarize(trades: pd.DataFrame) -> dict[str, Any]:
    # The reusable monthly summary calculates an unused 3-period bootstrap. Suppress that duplicate
    # calculation, then calculate the pre-registered 14-day bootstrap exactly once below.
    saved_bootstrap = engine.circular_block_bootstrap
    engine.circular_block_bootstrap = lambda _values, **_kwargs: [math.nan, math.nan]
    try:
        result = engine_summarize(trades)
    finally:
        engine.circular_block_bootstrap = saved_bootstrap
    if trades.empty:
        return result
    for scenario in CONFIG["costs"]:
        cohort = trades.groupby("entry_time")[f"{scenario}_after_hurdle_return"].mean().sort_index()
        result["scenarios"][scenario]["cohort_bootstrap_95pct"] = engine_bootstrap(
            cohort.to_numpy(float), block=int(CONFIG["bootstrap_block_days"]), reps=5000, seed=20260722,
        )
    targets = result["by_target_base_after_hurdle"]
    eligible = [value for value in targets.values() if value["trades"] >= 10]
    result["positive_target_fraction"] = float(np.mean([value["mean"] > 0 for value in eligible])) if eligible else 0.0
    drawdowns = [value["max_drawdown"] for value in eligible]
    result["target_max_drawdown_median"] = float(np.median(drawdowns)) if drawdowns else -1.0
    result["target_max_drawdown_worst"] = float(np.min(drawdowns)) if drawdowns else -1.0
    result["positive_category_count"] = int(sum(
        value["trades"] >= 10 and value["mean"] > 0
        for value in result["by_category_base_after_hurdle"].values()
    ))
    return result


def command_analyze(args: argparse.Namespace) -> None:
    ensure_checkpoint()
    engine.stage_authorized(args.stage)
    quality = HERE / f"data_quality_{args.stage}.json"
    if not quality.exists() or engine.read_json(quality)["status"] != "PASS":
        raise RuntimeError("stage data quality is not PASS")
    bars, funding, premium = load_all(args.stage)
    raw, excluded = build_trades(args.stage, bars, funding, premium, "premium_discount", 1, int(CONFIG["top_targets"]))
    main = engine.attach_returns(raw)
    main_path = HERE / f"{args.stage}_trades.csv"
    main.to_csv(main_path, index=False, date_format="%Y-%m-%dT%H:%M:%SZ")
    main_summary = summarize(main)
    main_summary["excluded_trades_due_missing_funding_mark"] = excluded
    main_summary["excluded_trade_fraction"] = float(excluded / (len(main) + excluded)) if len(main) + excluded else 0.0
    diagnostics: dict[str, Any] = {}
    hashes: dict[str, str] = {}
    for name, spec in CONFIG["diagnostics"].items():
        raw, skipped = build_trades(
            args.stage, bars, funding, premium, str(spec["kind"]), int(spec["lookback_days"]), int(spec["top_targets"]),
        )
        trades = engine.attach_returns(raw)
        path = HERE / f"{args.stage}_{name}_trades.csv"
        trades.to_csv(path, index=False, date_format="%Y-%m-%dT%H:%M:%SZ")
        diagnostics[name] = summarize(trades)
        diagnostics[name]["excluded_trades_due_missing_funding_mark"] = skipped
        diagnostics[name]["excluded_trade_fraction"] = float(skipped / (len(trades) + skipped)) if len(trades) + skipped else 0.0
        hashes[name] = engine.sha256_file(path)
    payload = {
        "generated_at_utc": engine.iso_now(), "stage": args.stage,
        "period": {"start": STAGES[args.stage]["start"], "end_exclusive": STAGES[args.stage]["end_exclusive"]},
        "main": main_summary, "diagnostics": diagnostics,
        "search_disclosure": {"selectable_primary_configurations": 1, "parameter_neighborhoods_not_selectable": 3, "simple_baselines_not_selectable": 3},
        "trade_csv_sha256": engine.sha256_file(main_path), "diagnostic_csv_sha256": hashes,
        "data_quality_digest": engine.read_json(quality)["content_digest"],
    }
    payload["content_digest"] = engine.canonical_digest(payload)
    engine.write_json(HERE / f"{args.stage}.json", payload)
    print(json.dumps({
        "stage": args.stage, "trades": main_summary["trades"],
        "base_after_hurdle": main_summary.get("scenarios", {}).get("base", {}).get("cohort_mean_after_hurdle"),
        "stress_after_hurdle": main_summary.get("scenarios", {}).get("stress", {}).get("cohort_mean_after_hurdle"),
    }))


def gate_checks(stage: str, result: dict[str, Any]) -> dict[str, bool]:
    main = result["main"]
    base = main.get("scenarios", {}).get("base", {})
    stress = main.get("scenarios", {}).get("stress", {})
    minimum_trades, minimum_targets, minimum_dates = {
        "development": (150, 12, 120), "evaluation": (75, 10, 60), "confirmation": (100, 10, 90),
    }[stage]
    years = {"development": ["2022", "2023"], "evaluation": ["2024"], "confirmation": ["2025", "2026"]}[stage]
    min_categories = 3 if stage == "confirmation" else 4
    neighbors = ["premium3", "premium5", "bottom5"]
    return {
        "data_quality_pass": engine.read_json(HERE / f"data_quality_{stage}.json")["status"] == "PASS",
        "excluded_trade_fraction_at_most_limit": main.get("excluded_trade_fraction", 1.0) <= float(CONFIG["max_excluded_trade_fraction"]),
        "vectorbt_reconciled": main.get("maximum_vectorbt_reconciliation_error", 1.0) <= 1e-10,
        "trades_at_least_minimum": main.get("trades", 0) >= minimum_trades,
        "targets_at_least_minimum": main.get("targets", 0) >= minimum_targets,
        "entry_dates_at_least_minimum": main.get("entry_dates", 0) >= minimum_dates,
        "categories_at_least_minimum": main.get("categories", 0) >= min_categories,
        "base_after_hurdle_positive": base.get("cohort_mean_after_hurdle", -1.0) > 0,
        "stress_after_hurdle_positive": stress.get("cohort_mean_after_hurdle", -1.0) > 0,
        "stress_bootstrap_lower_positive": (stress.get("cohort_bootstrap_95pct") or [-1.0])[0] > 0,
        "required_year_slices_positive": all(main.get("by_year_base_after_hurdle", {}).get(year, -1.0) > 0 for year in years),
        "positive_target_fraction_at_least_half": main.get("positive_target_fraction", 0.0) >= 0.5,
        "positive_categories_at_least_minimum": main.get("positive_category_count", 0) >= min_categories,
        "beats_funding1": base.get("cohort_mean_after_hurdle", -1.0) > result["diagnostics"]["funding1"].get("scenarios", {}).get("base", {}).get("cohort_mean_after_hurdle", 1.0),
        "beats_momentum5": base.get("cohort_mean_after_hurdle", -1.0) > result["diagnostics"]["momentum5"].get("scenarios", {}).get("base", {}).get("cohort_mean_after_hurdle", 1.0),
        "beats_scheduled_long": base.get("cohort_mean_after_hurdle", -1.0) > result["diagnostics"]["scheduled_long"].get("scenarios", {}).get("base", {}).get("cohort_mean_after_hurdle", 1.0),
        "two_of_three_neighborhoods_stress_positive": sum(
            result["diagnostics"][name].get("scenarios", {}).get("stress", {}).get("cohort_mean_after_hurdle", -1.0) > 0 for name in neighbors
        ) >= 2,
        "largest_positive_target_share_at_most_25pct": main.get("largest_positive_target_pnl_share", 1.0) <= 0.25,
        "median_target_drawdown_above_minus_10pct": main.get("target_max_drawdown_median", -1.0) > -0.10,
        "worst_target_drawdown_above_minus_25pct": main.get("target_max_drawdown_worst", -1.0) > -0.25,
    }


def conclusion_for_failed_gate(result: dict[str, Any]) -> str:
    minimum = {"development": (150, 12), "evaluation": (75, 10), "confirmation": (100, 10)}[result["stage"]]
    main = result["main"]
    sample_ok = main.get("trades", 0) >= minimum[0] and main.get("targets", 0) >= minimum[1]
    economic = all(main.get("scenarios", {}).get(name, {}).get("cohort_mean_after_hurdle", -1.0) > 0 for name in ["base", "stress"])
    return "INSUFFICIENT_EVIDENCE" if sample_ok and economic else "DOES_NOT_SUPPORT"


def command_conclude(_args: argparse.Namespace) -> None:
    gates = {stage: engine.read_json(HERE / f"{stage}_gate.json") for stage in STAGES}
    if not all(value["status"] == "PASS" for value in gates.values()):
        raise RuntimeError("cannot conclude support unless all sequential gates PASS")
    stages = {stage: engine.read_json(HERE / f"{stage}.json") for stage in STAGES}
    handoff = {
        "candidate_id": CONFIG["strategy_id"], "version": "1", "allowed_direction": "LONG",
        "notional_fraction_of_plan_capital": CONFIG["notional_fraction"],
        "inputs": ["daily USD-M OHLCV/quote volume", "8h official premium-index closes", "UTC timestamps"],
        "warmup_days": 45,
        "decision": (
            "Before each UTC daily open, require at least 20 liquid targets with complete prior-day inputs; average "
            "the three prior complete 8h premium-index closes, rank ascending with symbol tie-break, and propose "
            "LONG only when the fixed target has negative premium and rank one to three."
        ),
        "entry": "next UTC daily open", "exit": "following UTC daily open; one full UTC day before reactivation",
        "unknown_no_action": "missing, stale, discontinuous, invalid, nonnegative premium, insufficient targets, held, or cooling down",
        "costs": CONFIG["costs"],
        "unsupported_execution_facts": ["order-book depth", "queue/partial fills", "00:00 funding-order sequencing", "intraday margin/liquidation/ADL", "manual latency"],
        "framework_neutral_trace": [
            {"case": "negative_rank_three", "premium1": -0.0004, "feature_rank": 3, "rankable_targets": 23, "proposal": "LONG_ENTRY_NEXT_DAILY_OPEN"},
            {"case": "positive_rank_three", "premium1": 0.0001, "feature_rank": 3, "rankable_targets": 23, "proposal": "NO_ACTION"},
            {"case": "insufficient_universe", "premium1": -0.0004, "feature_rank": None, "rankable_targets": 19, "proposal": "NO_ACTION"},
        ],
        "research_result_digest": {stage: value["content_digest"] for stage, value in stages.items()},
        "limitations": "Current-survivor list; single-leg directional strategy is not arbitrage; daily/8h inputs cannot model intraday execution and margin path; no product or trading authorization.",
    }
    handoff["content_digest"] = engine.canonical_digest(handoff)
    engine.write_json(HERE / "handoff.json", handoff)
    result = {
        "generated_at_utc": engine.iso_now(), "conclusion": "SUPPORTS_WITHIN_SCOPE",
        "stage_gates": {stage: value["status"] for stage, value in gates.items()},
        "stages": {stage: value["main"] for stage, value in stages.items()},
        "handoff_sha256": engine.sha256_file(HERE / "handoff.json"), "product_effects": "NONE",
    }
    result["content_digest"] = engine.canonical_digest(result)
    engine.write_json(HERE / "results.json", result)
    print(json.dumps({"conclusion": result["conclusion"], "handoff": str(HERE / "handoff.json")}))


engine.bound_file_hashes = bound_file_hashes
engine.ensure_checkpoint = ensure_checkpoint
engine.command_checkpoint = command_checkpoint
engine.command_fetch = command_fetch
engine.command_inspect = command_inspect
engine.build_trades = build_trades
engine.summarize = summarize
engine.command_analyze = command_analyze
engine.gate_checks = gate_checks
engine.conclusion_for_failed_gate = conclusion_for_failed_gate
engine.command_conclude = command_conclude


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Daily perpetual-discount one-shot LONG study")
    subs = parser.add_subparsers(dest="command", required=True)
    item = subs.add_parser("checkpoint"); item.set_defaults(func=command_checkpoint)
    for name, function in [("fetch", command_fetch), ("inspect", command_inspect), ("analyze", command_analyze), ("gate", engine.command_gate)]:
        item = subs.add_parser(name); item.add_argument("--stage", choices=tuple(STAGES), required=True); item.set_defaults(func=function)
    item = subs.add_parser("conclude"); item.set_defaults(func=command_conclude)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
