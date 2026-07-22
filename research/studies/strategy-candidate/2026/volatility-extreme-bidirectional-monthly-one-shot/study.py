from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import platform
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import vectorbt as vbt


HERE = Path(__file__).resolve().parent
Q18_STUDY = HERE.parent / "high-volatility-ten-week-loser-weekly-one-shot-long" / "study.py"
MONTHLY_ENGINE = HERE.parent / "perp-low-volatility-monthly-one-shot-long" / "study.py"
LOWVOL_RESULT = HERE.parent / "perp-low-volatility-monthly-one-shot-long" / "results.json"
HIGHVOL_RESULT = HERE.parent / "high-volatility-monthly-one-shot-short" / "results.json"
EXTERNAL_PDFS = [
    Path("D:/projects/Codex/CodexHome/research-data/halpha/_sources/low-volatility-strategies-liquid-cryptocurrencies-kaya-mostowf.pdf"),
    Path("D:/projects/Codex/CodexHome/research-data/halpha/_sources/seasonality-cross-section-crypto-long-et-al-2020.pdf"),
]
CACHE_ROOT = Path(os.environ.get(
    "HALPHA_VOLATILITY_EXTREME_BIDIRECTIONAL_CACHE",
    "D:/projects/Codex/CodexHome/research-data/halpha/volatility-extreme-bidirectional/2026-07-22-v1",
))


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


q18 = load_module(Q18_STUDY, "halpha_vol_extreme_q18")
SYMBOLS = list(q18.SYMBOLS)
CATEGORY_MEMBERS = dict(q18.CATEGORY_MEMBERS)
SYMBOL_TO_CATEGORY = dict(q18.SYMBOL_TO_CATEGORY)
UNIVERSE_PATH = q18.UNIVERSE_PATH
UNIVERSE_SHA256 = q18.UNIVERSE_SHA256

STAGES = {
    "development": ("2024-01-01T00:00:00Z", "2025-01-01T00:00:00Z"),
    "evaluation": ("2025-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
    "confirmation": ("2026-01-01T00:00:00Z", "2026-07-01T00:00:00Z"),
}
FETCH_STAGE = {
    "confirmation": {
        "fetch_start": "2025-08-19T00:00:00Z",
        "start": STAGES["confirmation"][0],
        "end_exclusive": STAGES["confirmation"][1],
    }
}
CONFIG = {
    "strategy_id": "RESEARCH_VOL90_BOTTOM3_LONG_TOP3_SHORT_MONTHLY_ONE_SHOT_0P25X_V1",
    "formation_days": 90,
    "extreme_targets": 3,
    "notional_fraction": 0.25,
    "minimum_rankable_symbols": 20,
    "minimum_median_quote_volume_30d": 10_000_000.0,
    "annual_capital_hurdle": 0.04,
    "cooldown_full_days": 1,
    "max_excluded_trade_fraction": 0.05,
    "costs": {
        "favorable": {"fee_per_side": 0.0006, "slippage_per_side": 0.0, "funding_stress": False},
        "base": {"fee_per_side": 0.0006, "slippage_per_side": 0.0010, "funding_stress": False},
        "stress": {"fee_per_side": 0.0006, "slippage_per_side": 0.0020, "funding_stress": True},
    },
    "long_funding_stress": {"positive_cost_multiplier": 1.5, "negative_benefit_multiplier": 0.5},
    "short_funding_stress": {"positive_benefit_multiplier": 0.5, "negative_cost_multiplier": 1.5},
    "diagnostics": ["rv60", "rv120", "extreme5", "reverse", "momentum90", "scheduled_long", "scheduled_short"],
}
FROZEN_FILES = ["README.md", "preregistration.md", "sources.md", "study.py"]


def iso_now() -> str:
    return q18.iso_now()


def sha256_file(path: Path) -> str:
    return q18.sha256_file(path)


def canonical_digest(value: Any) -> str:
    return q18.canonical_digest(value)


def read_json(path: Path) -> Any:
    return q18.read_json(path)


def write_json(path: Path, value: dict[str, Any], *, digest: bool = False) -> None:
    q18.write_json(path, value, digest=digest)


def validate_universe() -> None:
    q18.validate_universe()


def source_entries() -> list[dict[str, Any]]:
    paths: list[tuple[Path, str]] = [
        (Q18_STUDY, "reused frozen public data adapter and source stitching"),
        (q18.PARENT_STUDY, "reused funding/cost/statistics reference"),
        (q18.DATA_ENGINE, "official Binance public archive loader/fetcher"),
        (UNIVERSE_PATH, "frozen current target universe"),
        (LOWVOL_RESULT, "known 2022-2023 low-volatility LONG selection evidence"),
        (HIGHVOL_RESULT, "known 2024 high-volatility SHORT selection evidence"),
        (q18.DEV_SOURCE / "source_manifest_development.json", "2024 public data manifest"),
        (q18.DEV_SOURCE / "data_quality_development.json", "2024 source quality"),
        (q18.EVAL_SOURCE / "source_manifest_evaluation.json", "2025 public data manifest"),
        (q18.EVAL_SOURCE / "data_quality_evaluation.json", "2025 source quality"),
        *[(path, "external primary paper") for path in EXTERNAL_PDFS],
    ]
    output: list[dict[str, Any]] = []
    for path, role in paths:
        if not path.exists():
            raise RuntimeError(f"missing source identity: {path}")
        output.append({"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path), "role": role})
    return output


def command_checkpoint(_args: argparse.Namespace) -> None:
    validate_universe()
    path = HERE / "checkpoint.json"
    if path.exists():
        checkpoint = ensure_checkpoint()
        print(json.dumps({"checkpoint": str(path), "digest": checkpoint["content_digest"], "reused": True}))
        return
    reuse = {"created_at_utc": iso_now(), "entries": source_entries()}
    write_json(HERE / "source_reuse_manifest.json", reuse, digest=True)
    payload = {
        "created_at_utc": iso_now(),
        "baseline_commit": "0bdfeffa616260cebd2d2188ddc8deb9e85c77f4",
        "formal_strategy": {"strategy_id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT", "version": "1.0.1", "instrument": "BTCUSDT-PERP"},
        "research_kind": "STRATEGY_CANDIDATE",
        "question": (
            "Does a configured current liquid Binance USD-M target qualify a monthly 0.25x one-shot rule that "
            "proposes LONG in the bottom three VOL90 ranks, SHORT in the top three, and otherwise NO_ACTION, "
            "after retail costs, actual funding, capital hurdle, direction decomposition, robustness, risk and sequential evidence?"
        ),
        "known_exposure": (
            "The 2022-2023 low-volatility LONG and 2024 high-volatility SHORT single-leg outputs are exposed. "
            "Development 2024 is selection replay only and cannot independently support the candidate. The exact "
            "bidirectional 2025 output was not computed before this checkpoint; confirmation remains sealed until evaluation PASS."
        ),
        "configuration": CONFIG,
        "stages": {key: list(value) for key, value in STAGES.items()},
        "fetch_stage": FETCH_STAGE,
        "symbols": SYMBOLS,
        "categories": CATEGORY_MEMBERS,
        "family_stop_rule": (
            "On failure, close the fixed VOL90 bottom3-LONG/top3-SHORT monthly family; do not search nearby lookbacks, "
            "cutoffs, directions, symbols or holds without genuinely new forward evidence or an independent mechanism."
        ),
        "stage_open_rule": "2024 selection replay -> 2025 evaluation -> authorized 2026H1 fetch/confirmation",
        "frozen_file_sha256": {name: sha256_file(HERE / name) for name in FROZEN_FILES},
        "source_reuse_digest": read_json(HERE / "source_reuse_manifest.json")["content_digest"],
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__, "vectorbt": vbt.__version__},
        "confirmation_cache_root": str(CACHE_ROOT),
        "allowed_after_checkpoint": (
            "Deterministic result artifacts and implementation-only fixes with explicit amendment; no economic rule change. "
            "Confirmation public data may be fetched only after evaluation PASS."
        ),
    }
    write_json(path, payload, digest=True)
    checkpoint = read_json(path)
    print(json.dumps({"checkpoint": str(path), "digest": checkpoint["content_digest"], "reused": False}))


def ensure_checkpoint() -> dict[str, Any]:
    path = HERE / "checkpoint.json"
    if not path.exists():
        raise RuntimeError("checkpoint missing")
    checkpoint = read_json(path)
    if canonical_digest(checkpoint) != checkpoint.get("content_digest"):
        raise RuntimeError("checkpoint digest mismatch")
    if checkpoint.get("configuration") != CONFIG or checkpoint.get("stages") != {key: list(value) for key, value in STAGES.items()}:
        raise RuntimeError("checkpoint differs from code")
    validate_universe()
    for name, expected in checkpoint["frozen_file_sha256"].items():
        actual = sha256_file(HERE / name)
        if actual == expected:
            continue
        chain = expected
        amendments = sorted(HERE.glob("amendment-*.json")) if name == "study.py" else []
        for amendment_path in amendments:
            amendment = read_json(amendment_path)
            if (
                canonical_digest(amendment) != amendment.get("content_digest")
                or amendment.get("checkpoint_digest") != checkpoint["content_digest"]
                or amendment.get("original_study_sha256") != chain
                or amendment.get("economic_rule_changed") is not False
            ):
                raise RuntimeError(f"invalid amendment: {amendment_path.name}")
            chain = amendment["amended_study_sha256"]
        if chain != actual:
            raise RuntimeError(f"frozen file changed: {name}")
    reuse = read_json(HERE / "source_reuse_manifest.json")
    if canonical_digest(reuse) != reuse.get("content_digest") or reuse["content_digest"] != checkpoint["source_reuse_digest"]:
        raise RuntimeError("source reuse digest mismatch")
    for item in reuse["entries"]:
        path = Path(item["path"])
        if not path.exists() or path.stat().st_size != int(item["bytes"]) or sha256_file(path) != item["sha256"]:
            raise RuntimeError(f"source identity changed: {path}")
    return checkpoint


def prior_stage(stage: str) -> str | None:
    return {"evaluation": "development", "confirmation": "evaluation"}.get(stage)


def stage_authorized(stage: str) -> None:
    prior = prior_stage(stage)
    if prior is None:
        return
    gate = HERE / f"{prior}_gate.json"
    if not gate.exists() or read_json(gate).get("status") != "PASS":
        raise RuntimeError(f"{stage} sealed until {prior} PASS")


def command_fetch(args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    if args.stage != "confirmation":
        raise RuntimeError("2024/2025 reuse frozen public manifests; only confirmation is fetchable")
    stage_authorized(args.stage)
    manifest_path = HERE / "source_manifest_confirmation.json"
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        if canonical_digest(manifest) != manifest.get("content_digest"):
            raise RuntimeError("confirmation manifest digest mismatch")
        print(json.dumps({"manifest": str(manifest_path), "digest": manifest["content_digest"], "reused": True}))
        return
    engine = load_module(MONTHLY_ENGINE, "halpha_vol_extreme_fetch")
    engine.CACHE_ROOT = CACHE_ROOT
    engine.HERE = HERE
    engine.SYMBOLS = SYMBOLS
    engine.TARGET_SYMBOLS = SYMBOLS
    engine.SYMBOL_TO_CATEGORY = SYMBOL_TO_CATEGORY
    engine.STAGES = FETCH_STAGE
    engine.CONFIG = CONFIG
    spec = FETCH_STAGE["confirmation"]
    kline_start = pd.Timestamp(spec["fetch_start"])
    kline_end = pd.Timestamp(spec["end_exclusive"]) + pd.Timedelta(days=1)
    archives = engine.fetch_target_archives("confirmation")
    manifest: dict[str, Any] = {
        "accessed_at_utc": iso_now(), "stage": "confirmation", "checkpoint_digest": checkpoint["content_digest"],
        "source": "Binance public USD-M REST and official archives; no credentials",
        "periods": {"kline_start": str(kline_start), "kline_end_exclusive": str(kline_end), "funding_start": spec["start"], "funding_end_exclusive": spec["end_exclusive"]},
        "symbols": {},
    }
    for number, symbol in enumerate(SYMBOLS, start=1):
        root = CACHE_ROOT / "confirmation" / symbol / "raw_vol_extreme_bidirectional"
        manifest["symbols"][symbol] = {
            "category": SYMBOL_TO_CATEGORY[symbol],
            "kline_pages": engine.fetch_pages("/fapi/v1/klines", {"symbol": symbol, "interval": "1d"}, "openTime", 1500, kline_start, kline_end, root / "klines"),
            "funding_archives": archives[symbol]["fundingRate"],
            "mark_price_archives": archives[symbol]["markPriceKlines"],
            "mark_price_gap_archives": archives[symbol]["markPriceKlines1m"],
        }
        if number % 10 == 0 or number == len(SYMBOLS):
            print(json.dumps({"stage": args.stage, "symbols": number, "total": len(SYMBOLS)}))
    write_json(manifest_path, manifest, digest=True)
    written = read_json(manifest_path)
    print(json.dumps({"manifest": str(manifest_path), "digest": written["content_digest"], "reused": False}))


def load_stage(stage: str) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame], dict[str, Any]]:
    if stage in {"development", "evaluation"}:
        return q18.load_stage(stage)
    manifest = HERE / "source_manifest_confirmation.json"
    if not manifest.exists():
        raise RuntimeError("confirmation manifest missing")
    item = read_json(manifest)
    if canonical_digest(item) != item.get("content_digest"):
        raise RuntimeError("confirmation manifest digest mismatch")
    engine = load_module(MONTHLY_ENGINE, "halpha_vol_extreme_load_confirmation")
    engine.HERE = HERE
    bars: dict[str, pd.DataFrame] = {}
    funding: dict[str, pd.DataFrame] = {}
    for symbol in SYMBOLS:
        bars[symbol], funding[symbol] = engine.load_symbol("confirmation", symbol)
    return bars, funding, {"overlap_rows": 0, "overlap_mismatch_rows": 0}


def stage_entries(stage: str) -> pd.DatetimeIndex:
    start, end = map(pd.Timestamp, STAGES[stage])
    return pd.date_range(start, end, freq="MS", inclusive="left")


def feature_frame(frame: pd.DataFrame) -> pd.DataFrame:
    calendar = pd.date_range(frame.index.min(), frame.index.max(), freq="1D")
    frame = frame.reindex(calendar)
    output = pd.DataFrame(index=calendar)
    log_return = np.log(frame["close"] / frame["close"].shift(1))
    for days in (60, 90, 120):
        output[f"rv{days}"] = log_return.rolling(days, min_periods=days).std(ddof=1) * math.sqrt(365.0)
    output["mom90"] = frame["close"] / frame["close"].shift(90) - 1.0
    output["median_quote_volume_30d"] = frame["quote_volume"].rolling(30, min_periods=30).median()
    required = frame[["open", "high", "low", "close", "quote_volume"]].notna().all(axis=1)
    output["complete_91d"] = required.rolling(91, min_periods=91).sum().eq(91)
    return output.replace([np.inf, -np.inf], np.nan)


def command_prepare(args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    stage_authorized(args.stage)
    bars, funding, metadata = load_stage(args.stage)
    entries = stage_entries(args.stage)
    required_start = entries[0] - pd.Timedelta(days=121)
    required_end = entries[-1] + pd.offsets.MonthBegin(1)
    per_symbol: dict[str, Any] = {}
    status = metadata.get("overlap_mismatch_rows", 0) == 0
    features = {symbol: feature_frame(frame) for symbol, frame in bars.items()}
    rankable_counts: dict[str, int] = {}
    for symbol in SYMBOLS:
        frame = bars[symbol].sort_index()
        subset = frame[(frame.index >= required_start) & (frame.index <= required_end)]
        invalid = int(((subset[["open", "high", "low", "close"]] <= 0).any(axis=1) | (subset["high"] < subset[["open", "close"]].max(axis=1)) | (subset["low"] > subset[["open", "close"]].min(axis=1)) | (subset[["volume", "quote_volume"]] < 0).any(axis=1)).sum())
        rates = funding[symbol][(funding[symbol].index > entries[0]) & (funding[symbol].index < required_end)]
        max_gap = float(rates.index.to_series().diff().dt.total_seconds().max() / 3600.0) if len(rates) > 1 else math.inf
        item_pass = invalid == 0 and len(rates) > 0 and max_gap <= 25.0
        status = status and item_pass
        per_symbol[symbol] = {"daily_rows": int(len(subset)), "invalid_rows": invalid, "funding_rows": int(len(rates)), "missing_mark_rows": int(rates["markPrice"].isna().sum()), "max_funding_gap_hours": None if not math.isfinite(max_gap) else max_gap, "status": "PASS" if item_pass else "FAIL"}
    for entry in entries:
        decision = entry - pd.Timedelta(days=1)
        exit_time = entry + pd.offsets.MonthBegin(1)
        count = 0
        for symbol in SYMBOLS:
            f = features[symbol]
            if (decision in f.index and bool(f.at[decision, "complete_91d"]) and pd.notna(f.at[decision, "rv90"]) and pd.notna(f.at[decision, "median_quote_volume_30d"]) and float(f.at[decision, "median_quote_volume_30d"]) >= float(CONFIG["minimum_median_quote_volume_30d"]) and entry in bars[symbol].index and exit_time in bars[symbol].index and pd.notna(bars[symbol].at[entry, "open"]) and pd.notna(bars[symbol].at[exit_time, "open"])):
                count += 1
        rankable_counts[entry.isoformat()] = count
    below = {date: count for date, count in rankable_counts.items() if count < int(CONFIG["minimum_rankable_symbols"])}
    payload = {
        "checked_at_utc": iso_now(), "stage": args.stage, "status": "PASS" if status else "FAIL",
        "checkpoint_digest": checkpoint["content_digest"], "required_daily_range_inclusive": [required_start.isoformat(), required_end.isoformat()],
        "source_overlap": metadata, "decision_input_availability": {"minimum_rankable": min(rankable_counts.values()), "maximum_rankable": max(rankable_counts.values()), "dates_below_minimum": below},
        "symbols": per_symbol,
        "rule": "Calendar gaps are not imputed. A target with incomplete VOL90/volume/entry/exit input is NO_ACTION; a decision with fewer than 20 rankable targets is an all-target NO_ACTION month rather than a source-quality failure. Missing funding marks exclude only the spanning opportunity.",
    }
    write_json(HERE / f"data_quality_{args.stage}.json", payload, digest=True)
    print(json.dumps({"stage": args.stage, "status": payload["status"], "min_rankable": min(rankable_counts.values())}))


def build_panel(bars: dict[str, pd.DataFrame], stage: str) -> pd.DataFrame:
    features = {symbol: feature_frame(frame) for symbol, frame in bars.items()}
    rows: list[dict[str, Any]] = []
    for entry in stage_entries(stage):
        decision = entry - pd.Timedelta(days=1)
        exit_time = entry + pd.offsets.MonthBegin(1)
        candidates: list[dict[str, Any]] = []
        for symbol in SYMBOLS:
            f = features[symbol]
            if decision not in f.index or entry not in bars[symbol].index or exit_time not in bars[symbol].index:
                continue
            values = f.loc[decision, ["rv60", "rv90", "rv120", "mom90", "median_quote_volume_30d", "complete_91d"]]
            if pd.isna(values[["rv90", "mom90", "median_quote_volume_30d"]]).any() or not bool(values["complete_91d"]) or float(values["median_quote_volume_30d"]) < float(CONFIG["minimum_median_quote_volume_30d"]):
                continue
            candidates.append({"entry_time": entry, "decision_time": decision, "exit_time": exit_time, "symbol": symbol, "entry_price": float(bars[symbol].at[entry, "open"]), "exit_price": float(bars[symbol].at[exit_time, "open"]), "rv60": float(values["rv60"]) if pd.notna(values["rv60"]) else np.nan, "rv90": float(values["rv90"]), "rv120": float(values["rv120"]) if pd.notna(values["rv120"]) else np.nan, "mom90": float(values["mom90"])})
        if len(candidates) < int(CONFIG["minimum_rankable_symbols"]):
            continue
        for item in candidates:
            item["eligible_count"] = len(candidates)
        rows.extend(candidates)
    if not rows:
        raise RuntimeError(f"empty panel: {stage}")
    return pd.DataFrame(rows).sort_values(["entry_time", "symbol"]).reset_index(drop=True)


def select_variant(panel: pd.DataFrame, variant: str) -> dict[pd.Timestamp, pd.DataFrame]:
    output: dict[pd.Timestamp, pd.DataFrame] = {}
    for entry, raw in panel.groupby("entry_time", sort=True):
        month = raw.copy()
        if variant in {"scheduled_long", "scheduled_short"}:
            selected = month.sort_values("symbol").copy()
            selected["direction"] = "LONG" if variant == "scheduled_long" else "SHORT"
            selected["score"] = selected["rv90"]
            selected["selection_rank"] = np.arange(1, len(selected) + 1)
            output[pd.Timestamp(entry)] = selected
            continue
        if variant == "momentum90":
            low = month.sort_values(["mom90", "symbol"]).head(int(CONFIG["extreme_targets"])).copy()
            high = month.sort_values(["mom90", "symbol"], ascending=[False, True]).head(int(CONFIG["extreme_targets"])).copy()
            low["direction"], high["direction"] = "SHORT", "LONG"
            low["score"], high["score"] = low["mom90"], high["mom90"]
        else:
            column = {"rv60": "rv60", "rv120": "rv120"}.get(variant, "rv90")
            valid = month[pd.notna(month[column])].copy()
            count = 5 if variant == "extreme5" else int(CONFIG["extreme_targets"])
            low = valid.sort_values([column, "symbol"]).head(count).copy()
            high = valid.sort_values([column, "symbol"], ascending=[False, True]).head(count).copy()
            if variant == "reverse":
                low["direction"], high["direction"] = "SHORT", "LONG"
            else:
                low["direction"], high["direction"] = "LONG", "SHORT"
            low["score"], high["score"] = low[column], high[column]
        low["selection_rank"] = np.arange(1, len(low) + 1)
        high["selection_rank"] = np.arange(1, len(high) + 1)
        output[pd.Timestamp(entry)] = pd.concat([low, high], ignore_index=True).sort_values(["direction", "selection_rank", "symbol"])
    return output


def stressed_funding_rate(rate: float, direction: str) -> float:
    if direction == "LONG":
        return rate * (float(CONFIG["long_funding_stress"]["positive_cost_multiplier"]) if rate > 0 else float(CONFIG["long_funding_stress"]["negative_benefit_multiplier"]))
    return rate * (float(CONFIG["short_funding_stress"]["positive_benefit_multiplier"]) if rate > 0 else float(CONFIG["short_funding_stress"]["negative_cost_multiplier"]))


def make_trades(selections: dict[pd.Timestamp, pd.DataFrame], funding: dict[str, pd.DataFrame], stage: str, variant: str) -> tuple[pd.DataFrame, dict[str, int]]:
    rows: list[dict[str, Any]] = []
    last_exit: dict[str, pd.Timestamp] = {}
    planned = excluded_marks = excluded_funding = cooldown_skips = 0
    for entry in sorted(selections):
        for _, item in selections[entry].iterrows():
            symbol = str(item["symbol"])
            planned += 1
            if symbol in last_exit and entry <= last_exit[symbol] + pd.Timedelta(days=int(CONFIG["cooldown_full_days"])):
                cooldown_skips += 1
                continue
            exit_time = pd.Timestamp(item["exit_time"])
            rates = funding[symbol][(funding[symbol].index > entry) & (funding[symbol].index < exit_time)]
            if rates.empty:
                excluded_funding += 1
                last_exit[symbol] = exit_time
                continue
            if rates["markPrice"].isna().any():
                excluded_marks += 1
                last_exit[symbol] = exit_time
                continue
            direction = str(item["direction"])
            sign = 1.0 if direction == "LONG" else -1.0
            entry_price, exit_price = float(item["entry_price"]), float(item["exit_price"])
            notional = float(CONFIG["notional_fraction"])
            quantity = notional / entry_price
            exposure = quantity * rates["markPrice"]
            actual_funding = -sign * float((exposure * rates["fundingRate"]).sum())
            stress_rates = rates["fundingRate"].map(lambda value: stressed_funding_rate(float(value), direction))
            stress_funding = -sign * float((exposure * stress_rates).sum())
            rows.append({
                "trade_id": f"{stage}-{variant}-{entry:%Y%m%d}-{symbol}-{direction}", "stage": stage, "strategy_variant": variant,
                "entry_time": entry, "decision_time": item["decision_time"], "exit_time": exit_time, "symbol": symbol,
                "category": SYMBOL_TO_CATEGORY[symbol], "direction": direction, "score": float(item["score"]),
                "selection_rank": int(item["selection_rank"]), "eligible_count": int(item["eligible_count"]),
                "entry_price": entry_price, "exit_price": exit_price, "hold_days": int((exit_time - entry).days),
                "notional_fraction": notional, "quantity_per_unit_plan_capital": quantity, "funding_events": int(len(rates)),
                "actual_funding_return": actual_funding, "stress_funding_return": stress_funding,
                "gross_price_return": sign * notional * (exit_price / entry_price - 1.0),
            })
            last_exit[symbol] = exit_time
    return pd.DataFrame(rows), {"planned": planned, "excluded_missing_marks": excluded_marks, "excluded_missing_funding": excluded_funding, "cooldown_skips": cooldown_skips}


def vectorbt_returns(trades: pd.DataFrame, fee: float, slippage: float) -> np.ndarray:
    columns = trades["trade_id"].tolist()
    prices = pd.DataFrame([trades["entry_price"].to_numpy(float), trades["exit_price"].to_numpy(float)], columns=columns)
    sign = np.where(trades["direction"].to_numpy(str) == "LONG", 1.0, -1.0)
    quantity = trades["quantity_per_unit_plan_capital"].to_numpy(float)
    sizes = pd.DataFrame([sign * quantity, -sign * quantity], columns=columns)
    portfolio = vbt.Portfolio.from_orders(prices, size=sizes, size_type="amount", direction="both", fees=fee, slippage=slippage, init_cash=1.0, freq="1D")
    return portfolio.total_return().reindex(columns).to_numpy(float)


def manual_return(row: pd.Series, fee: float, slippage: float) -> float:
    quantity = float(row["quantity_per_unit_plan_capital"])
    if row["direction"] == "LONG":
        entry_execution = float(row["entry_price"]) * (1.0 + slippage)
        exit_execution = float(row["exit_price"]) * (1.0 - slippage)
        gross = quantity * (exit_execution - entry_execution)
    else:
        entry_execution = float(row["entry_price"]) * (1.0 - slippage)
        exit_execution = float(row["exit_price"]) * (1.0 + slippage)
        gross = quantity * (entry_execution - exit_execution)
    return gross - quantity * entry_execution * fee - quantity * exit_execution * fee


def attach_returns(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        raise RuntimeError("strategy produced no trades")
    output = trades.copy()
    for scenario, assumptions in CONFIG["costs"].items():
        fee, slippage = float(assumptions["fee_per_side"]), float(assumptions["slippage_per_side"])
        vector = vectorbt_returns(output, fee, slippage)
        manual = output.apply(manual_return, axis=1, fee=fee, slippage=slippage).to_numpy(float)
        funding_column = "stress_funding_return" if assumptions["funding_stress"] else "actual_funding_return"
        output[f"{scenario}_price_cost_return"] = vector
        output[f"{scenario}_reconciliation_error"] = vector - manual
        output[f"{scenario}_net_return"] = vector + output[funding_column].to_numpy(float)
        hurdle = (1.0 + float(CONFIG["annual_capital_hurdle"])) ** (output["hold_days"].to_numpy(float) / 365.0) - 1.0
        output[f"{scenario}_after_hurdle_return"] = (1.0 + output[f"{scenario}_net_return"].to_numpy(float)) / (1.0 + hurdle) - 1.0
    return output


def summarize(trades: pd.DataFrame) -> dict[str, Any]:
    engine = load_module(MONTHLY_ENGINE, f"halpha_vol_extreme_summary_{abs(hash(tuple(trades['trade_id'].head(3))))}")
    engine.CONFIG = CONFIG
    result = engine.summarize(trades)
    all_target_drawdowns = [value["max_drawdown"] for value in result["by_target_base_after_hurdle"].values()]
    result["target_max_drawdown_median"] = float(np.median(all_target_drawdowns))
    result["target_max_drawdown_worst"] = float(np.min(all_target_drawdowns))
    result["drawdown_target_scope"] = "all traded targets, including targets with fewer than three trades"
    result["by_direction"] = {}
    for direction in ("LONG", "SHORT"):
        subset = trades[trades["direction"] == direction]
        if not subset.empty:
            leg = engine.summarize(subset)
            result["by_direction"][direction] = {"trades": leg["trades"], "entry_dates": leg["entry_dates"], "targets": leg["targets"], "scenarios": leg["scenarios"]}
    midpoint = trades["entry_time"].min() + (trades["entry_time"].max() - trades["entry_time"].min()) / 2
    result["by_half"] = {}
    for label, subset in (("H1", trades[trades["entry_time"] <= midpoint]), ("H2", trades[trades["entry_time"] > midpoint])):
        result["by_half"][label] = {"entry_dates": int(subset["entry_time"].nunique()), "base_cohort_mean_after_hurdle": float(subset.groupby("entry_time")["base_after_hurdle_return"].mean().mean()) if not subset.empty else math.nan}
    return result


def compare(main: pd.DataFrame, baseline: pd.DataFrame, column: str = "base_after_hurdle_return") -> dict[str, Any]:
    left = main.groupby("entry_time")[column].mean().sort_index()
    right = baseline.groupby("entry_time")[column].mean().sort_index().reindex(left.index, fill_value=0.0)
    diff = left - right
    engine = load_module(MONTHLY_ENGINE, f"halpha_vol_extreme_compare_{column}")
    return {"main_mean": float(left.mean()), "baseline_mean": float(right.mean()), "difference_mean": float(diff.mean()), "difference_bootstrap_95pct": engine.circular_block_bootstrap(diff.to_numpy(float)), "positive_month_fraction": float((diff > 0).mean())}


def command_self_test(_args: argparse.Namespace) -> None:
    sample = pd.DataFrame([
        {"trade_id": "long", "entry_price": 100.0, "exit_price": 110.0, "quantity_per_unit_plan_capital": 0.0025, "direction": "LONG"},
        {"trade_id": "short", "entry_price": 100.0, "exit_price": 90.0, "quantity_per_unit_plan_capital": 0.0025, "direction": "SHORT"},
    ])
    vector = vectorbt_returns(sample, 0.0006, 0.0010)
    manual = sample.apply(manual_return, axis=1, fee=0.0006, slippage=0.0010).to_numpy(float)
    if float(np.max(np.abs(vector - manual))) > 1e-12:
        raise RuntimeError("VectorBT/manual direction reconciliation failed")
    if stressed_funding_rate(0.001, "LONG") != 0.0015 or stressed_funding_rate(-0.001, "SHORT") != -0.0015:
        raise RuntimeError("funding stress direction failed")
    print(json.dumps({"status": "PASS", "maximum_reconciliation_error": float(np.max(np.abs(vector - manual))), "long_return": float(vector[0]), "short_return": float(vector[1])}))


def command_analyze(args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    stage_authorized(args.stage)
    dq = HERE / f"data_quality_{args.stage}.json"
    if not dq.exists() or read_json(dq).get("status") != "PASS":
        raise RuntimeError("data quality is not PASS")
    bars, funding, _ = load_stage(args.stage)
    panel = build_panel(bars, args.stage)
    variants = ["main", *CONFIG["diagnostics"]]
    selections = {name: select_variant(panel, name) for name in variants}
    trades: dict[str, pd.DataFrame] = {}
    counts: dict[str, dict[str, int]] = {}
    csv_hashes: dict[str, str] = {}
    for name in variants:
        raw, counts[name] = make_trades(selections[name], funding, args.stage, name)
        trades[name] = attach_returns(raw)
        path = HERE / f"{args.stage}_{name}_trades.csv"
        trades[name].to_csv(path, index=False, date_format="%Y-%m-%dT%H:%M:%S%z")
        csv_hashes[path.name] = sha256_file(path)
    summaries = {name: summarize(frame) for name, frame in trades.items()}
    for name in variants:
        excluded = counts[name]["excluded_missing_marks"] + counts[name]["excluded_missing_funding"]
        summaries[name]["excluded_trade_fraction"] = float(excluded / (len(trades[name]) + excluded)) if len(trades[name]) + excluded else 0.0
    comparisons = {
        "base_vs_reverse": compare(trades["main"], trades["reverse"]),
        "base_vs_momentum90": compare(trades["main"], trades["momentum90"]),
        "stress_vs_reverse": compare(trades["main"], trades["reverse"], "stress_after_hurdle_return"),
    }
    payload = {"analyzed_at_utc": iso_now(), "stage": args.stage, "checkpoint_digest": checkpoint["content_digest"], "data_quality_digest": read_json(dq)["content_digest"], "panel_rows": int(len(panel)), "panel_months": int(panel["entry_time"].nunique()), "opportunity_counts": counts, "summaries": summaries, "comparisons": comparisons, "trade_csv_sha256": csv_hashes}
    write_json(HERE / f"{args.stage}.json", payload, digest=True)
    evidence = read_json(HERE / f"{args.stage}.json")
    main = summaries["main"]
    print(json.dumps({"stage": args.stage, "trades": main["trades"], "base_after_hurdle": main["scenarios"]["base"]["cohort_mean_after_hurdle"], "stress_after_hurdle": main["scenarios"]["stress"]["cohort_mean_after_hurdle"], "long_stress": main["by_direction"]["LONG"]["scenarios"]["stress"]["cohort_mean_after_hurdle"], "short_stress": main["by_direction"]["SHORT"]["scenarios"]["stress"]["cohort_mean_after_hurdle"], "digest": evidence["content_digest"]}))


def combined_later_stats() -> dict[str, Any]:
    frames = [pd.read_csv(HERE / f"{stage}_main_trades.csv", parse_dates=["entry_time"]) for stage in ("evaluation", "confirmation")]
    combined = pd.concat(frames, ignore_index=True)
    cohort = combined.groupby("entry_time")["stress_after_hurdle_return"].mean().sort_index()
    engine = load_module(MONTHLY_ENGINE, "halpha_vol_extreme_combined")
    return {"months": int(len(cohort)), "stress_mean_after_hurdle": float(cohort.mean()), "stress_bootstrap_95pct": engine.circular_block_bootstrap(cohort.to_numpy(float))}


def common_values(evidence: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    main = evidence["summaries"]["main"]
    return main, main["by_direction"]["LONG"], main["by_direction"]["SHORT"]


def gate_checks(stage: str, evidence: dict[str, Any]) -> tuple[dict[str, bool], dict[str, Any]]:
    main, long_leg, short_leg = common_values(evidence)
    base, stress = main["scenarios"]["base"], main["scenarios"]["stress"]
    minimums = {"development": (30, 8, 10, 3), "evaluation": (30, 10, 10, 4), "confirmation": (15, 5, 8, 3)}[stage]
    checks = {
        "data_quality_pass": read_json(HERE / f"data_quality_{stage}.json")["status"] == "PASS",
        "vectorbt_reconciled": main.get("maximum_vectorbt_reconciliation_error", 1.0) <= 1e-10,
        "excluded_trade_fraction_at_most_limit": main.get("excluded_trade_fraction", 1.0) <= float(CONFIG["max_excluded_trade_fraction"]),
        "minimum_trades": main.get("trades", 0) >= minimums[0], "minimum_entry_months": main.get("entry_dates", 0) >= minimums[1],
        "minimum_targets": main.get("targets", 0) >= minimums[2], "minimum_categories": main.get("categories", 0) >= minimums[3],
        "base_after_hurdle_positive": base.get("cohort_mean_after_hurdle", -1.0) > 0,
        "stress_after_hurdle_positive": stress.get("cohort_mean_after_hurdle", -1.0) > 0,
        "long_base_positive": long_leg["scenarios"]["base"]["cohort_mean_after_hurdle"] > 0,
        "long_stress_positive": long_leg["scenarios"]["stress"]["cohort_mean_after_hurdle"] > 0,
        "short_base_positive": short_leg["scenarios"]["base"]["cohort_mean_after_hurdle"] > 0,
        "short_stress_positive": short_leg["scenarios"]["stress"]["cohort_mean_after_hurdle"] > 0,
    }
    diagnostics: dict[str, Any] = {}
    if stage != "development":
        neighbor_positive = sum(evidence["summaries"][name]["scenarios"]["stress"]["cohort_mean_after_hurdle"] > 0 for name in ("rv60", "rv120", "extreme5"))
        positive_targets = [value for value in main.get("by_target_base_after_hurdle", {}).values() if value["trades"] >= 2]
        positive_target_fraction = float(np.mean([value["mean"] > 0 for value in positive_targets])) if positive_targets else 0.0
        positive_categories = sum(value["trades"] >= 3 and value["mean"] > 0 for value in main.get("by_category_base_after_hurdle", {}).values())
        required_positive_categories = 3 if stage == "evaluation" else 2
        checks.update({
            "stress_bootstrap_lower_positive": stress["cohort_bootstrap_95pct"][0] > 0 if stage == "evaluation" else True,
            "both_half_years_base_positive": all(value["base_cohort_mean_after_hurdle"] > 0 for value in main["by_half"].values()) if stage == "evaluation" else True,
            "beats_reverse": evidence["comparisons"]["base_vs_reverse"]["difference_mean"] > 0,
            "beats_momentum90": evidence["comparisons"]["base_vs_momentum90"]["difference_mean"] > 0,
            "two_of_three_neighbors_stress_positive": neighbor_positive >= 2,
            "positive_target_fraction_at_least_half": positive_target_fraction >= 0.5,
            "minimum_positive_categories": positive_categories >= required_positive_categories,
            "positive_pnl_concentration_below_limit": main.get("largest_positive_target_pnl_share", 1.0) <= (0.35 if stage == "evaluation" else 0.40),
            "median_target_drawdown_above_minus_15pct": main.get("target_max_drawdown_median", -1.0) > -0.15,
            "worst_target_drawdown_above_minus_30pct": main.get("target_max_drawdown_worst", -1.0) > -0.30,
        })
        diagnostics.update({"neighbor_positive": neighbor_positive, "positive_target_fraction": positive_target_fraction, "positive_categories": positive_categories})
    if stage == "confirmation":
        combined = combined_later_stats()
        checks["combined_later_stress_positive"] = combined["stress_mean_after_hurdle"] > 0
        checks["combined_later_bootstrap_lower_positive"] = combined["stress_bootstrap_95pct"][0] > 0
        diagnostics["combined_later"] = combined
    return checks, diagnostics


def conclusion_for_failure(evidence: dict[str, Any]) -> str:
    main, long_leg, short_leg = common_values(evidence)
    sample_ok = main.get("trades", 0) >= (15 if evidence["stage"] == "confirmation" else 30)
    economic_positive = main["scenarios"]["base"]["cohort_mean_after_hurdle"] > 0 and main["scenarios"]["stress"]["cohort_mean_after_hurdle"] > 0 and long_leg["scenarios"]["stress"]["cohort_mean_after_hurdle"] > 0 and short_leg["scenarios"]["stress"]["cohort_mean_after_hurdle"] > 0
    return "INSUFFICIENT_EVIDENCE" if sample_ok and economic_positive else "DOES_NOT_SUPPORT"


def write_terminal(stage: str, evidence: dict[str, Any], gate: dict[str, Any]) -> None:
    conclusion = conclusion_for_failure(evidence)
    main = evidence["summaries"]["main"]
    result = {"created_at_utc": iso_now(), "conclusion": conclusion, "failed_stage": stage, "failed_checks": gate["failed_checks"], "handoff_generated": False, "later_stages": "NOT_OPENED_BY_SEQUENTIAL_GATE", "family_disposition": "CLOSED_UNTIL_NEW_FORWARD_EVIDENCE_OR_INDEPENDENT_MECHANISM", "summary": {"trades": main["trades"], "entry_dates": main["entry_dates"], "targets": main["targets"], "base_after_hurdle": main["scenarios"]["base"]["cohort_mean_after_hurdle"], "stress_after_hurdle": main["scenarios"]["stress"]["cohort_mean_after_hurdle"], "stress_bootstrap_95pct": main["scenarios"]["stress"]["cohort_bootstrap_95pct"], "long_stress": main["by_direction"]["LONG"]["scenarios"]["stress"]["cohort_mean_after_hurdle"], "short_stress": main["by_direction"]["SHORT"]["scenarios"]["stress"]["cohort_mean_after_hurdle"]}}
    write_json(HERE / "results.json", result, digest=True)
    (HERE / "result.md").write_text(f"# 结果：波动率极端双向月频 one-shot\n\n## 结论\n\n`{conclusion}`\n\n固定 VOL90 最低三名 LONG、最高三名 SHORT 规则在 `{stage}` 未通过预注册门。失败项：`{', '.join(gate['failed_checks'])}`。后续不打开，handoff 不生成；2024 正选择回放不能覆盖后续反证。\n\n- trades / months / targets：`{main['trades']} / {main['entry_dates']} / {main['targets']}`\n- base / stress 扣门槛 cohort 均值：`{main['scenarios']['base']['cohort_mean_after_hurdle']:.6%} / {main['scenarios']['stress']['cohort_mean_after_hurdle']:.6%}`\n- LONG / SHORT stress：`{main['by_direction']['LONG']['scenarios']['stress']['cohort_mean_after_hurdle']:.6%} / {main['by_direction']['SHORT']['scenarios']['stress']['cohort_mean_after_hurdle']:.6%}`\n", encoding="utf-8")


def write_success(evidence: dict[str, Any], gate: dict[str, Any]) -> None:
    stages = {stage: read_json(HERE / f"{stage}.json") for stage in STAGES}
    handoff = {
        "candidate_id": CONFIG["strategy_id"], "version": "1", "allowed_directions": ["LONG", "SHORT"],
        "instrument_scope": "one configured symbol from the frozen 25-symbol current USD-M target set",
        "notional_fraction_of_owner_approved_plan_amount": CONFIG["notional_fraction"],
        "inputs": ["completed UTC 1d OHLCV for the fixed cross-section", "30d quote-volume median", "instrument identity and current validity"],
        "warmup": "121 contiguous UTC daily bars; main VOL90 uses prior 90 completed log returns",
        "decision": "Before each UTC month-start open, require at least 20 valid targets. Rank annualized VOL90 ascending with symbol tie-break. Configured target rank 1-3 -> LONG; last three -> SHORT; otherwise NO_ACTION.",
        "entry": "next UTC calendar-month first daily open", "exit": "next month first UTC daily open; no intramonth price stop; one full UTC day cooldown before any new activation",
        "unknown_no_action": "missing, stale, discontinuous or invalid target/universe input; insufficient rankable targets; target not in either extreme",
        "costs": CONFIG["costs"],
        "unsupported_execution_facts": ["historical order-book depth", "queue and partial fills", "margin/liquidation/ADL", "intramonth squeeze", "owner activation delay", "point-in-time delisting universe"],
        "framework_neutral_trace": [
            {"case": "bottom_rank", "rankable": 24, "target_rank": 2, "proposal": "LONG_NEXT_MONTH_OPEN_0P25X"},
            {"case": "top_rank", "rankable": 24, "target_rank": 23, "proposal": "SHORT_NEXT_MONTH_OPEN_0P25X"},
            {"case": "middle_rank", "rankable": 24, "target_rank": 12, "proposal": "NO_ACTION"},
            {"case": "unknown_universe", "rankable": 19, "target_rank": None, "proposal": "NO_ACTION"},
        ],
        "research_result_digest": {stage: stages[stage]["content_digest"] for stage in STAGES},
        "limitations": "Research support is bounded to the fixed current-survivor universe, public bar/funding inputs and modeled costs. It does not authorize product changes, capital, activation or real trading.",
    }
    write_json(HERE / "handoff.json", handoff, digest=True)
    combined = gate["diagnostics"]["combined_later"]
    result = {"created_at_utc": iso_now(), "conclusion": "SUPPORTS_WITHIN_SCOPE", "stage_gates": {stage: read_json(HERE / f"{stage}_gate.json")["status"] for stage in STAGES}, "combined_evaluation_confirmation": combined, "handoff_generated": True, "handoff_sha256": sha256_file(HERE / "handoff.json"), "product_effects": "NONE"}
    write_json(HERE / "results.json", result, digest=True)
    (HERE / "result.md").write_text(f"# 结果：波动率极端双向月频 one-shot\n\n## 结论\n\n`SUPPORTS_WITHIN_SCOPE`\n\n固定规则通过全部顺序门及合并门，生成框架无关 `handoff.json`，仅供未来交易核心资格验证。evaluation+confirmation stress 扣门槛月均值 `{combined['stress_mean_after_hurdle']:.6%}`，95% 区间 `[{combined['stress_bootstrap_95pct'][0]:.6%}, {combined['stress_bootstrap_95pct'][1]:.6%}]`。这不是长期盈利保证，也不授权产品或真实交易动作。\n", encoding="utf-8")


def command_gate(args: argparse.Namespace) -> None:
    ensure_checkpoint()
    stage_authorized(args.stage)
    evidence = read_json(HERE / f"{args.stage}.json")
    checks, diagnostics = gate_checks(args.stage, evidence)
    gate = {"checked_at_utc": iso_now(), "stage": args.stage, "status": "PASS" if all(checks.values()) else "FAIL", "checks": checks, "failed_checks": [key for key, value in checks.items() if not value], "diagnostics": diagnostics, "evidence_digest": evidence["content_digest"]}
    write_json(HERE / f"{args.stage}_gate.json", gate, digest=True)
    written = read_json(HERE / f"{args.stage}_gate.json")
    if written["status"] == "FAIL":
        write_terminal(args.stage, evidence, written)
    elif args.stage == "confirmation":
        write_success(evidence, written)
    print(json.dumps({"stage": args.stage, "status": written["status"], "failed": written["failed_checks"], "diagnostics": diagnostics}))


def command_validate(_args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    json_checked = 0
    for path in sorted(HERE.glob("*.json")):
        if path.name == "validation.json":
            continue
        value = read_json(path)
        if "content_digest" in value:
            if canonical_digest(value) != value["content_digest"]:
                raise RuntimeError(f"JSON digest mismatch: {path.name}")
            json_checked += 1
    csv_checked = 0
    for stage in STAGES:
        evidence_path = HERE / f"{stage}.json"
        if not evidence_path.exists():
            continue
        evidence = read_json(evidence_path)
        for name, expected in evidence["trade_csv_sha256"].items():
            path = HERE / name
            if not path.exists() or sha256_file(path) != expected:
                raise RuntimeError(f"trade CSV mismatch: {name}")
            csv_checked += 1
    opened = [stage for stage in STAGES if (HERE / f"{stage}.json").exists()]
    result = read_json(HERE / "results.json") if (HERE / "results.json").exists() else None
    payload = {"validated_at_utc": iso_now(), "status": "PASS", "checkpoint_digest": checkpoint["content_digest"], "opened_stages": opened, "json_digest_files_checked": json_checked, "trade_csv_files_checked": csv_checked, "conclusion": None if result is None else result["conclusion"], "handoff_generated": (HERE / "handoff.json").exists()}
    write_json(HERE / "validation.json", payload, digest=True)
    print(json.dumps(payload))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VOL90 extreme bidirectional monthly one-shot study")
    subs = parser.add_subparsers(dest="command", required=True)
    subs.add_parser("checkpoint").set_defaults(func=command_checkpoint)
    subs.add_parser("self-test").set_defaults(func=command_self_test)
    for name, function in (("fetch", command_fetch), ("prepare", command_prepare), ("analyze", command_analyze), ("gate", command_gate)):
        item = subs.add_parser(name)
        item.add_argument("--stage", choices=tuple(STAGES), required=True)
        item.set_defaults(func=function)
    subs.add_parser("validate").set_defaults(func=command_validate)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
