from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import platform
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import scipy
import vectorbt as vbt


HERE = Path(__file__).resolve().parent
Q20_DIR = HERE.parent / "price-path-continuity-weekly-winner-long"
Q20_STUDY = Q20_DIR / "study.py"
CTREND_DIR = HERE.parent / "ctrend-weekly-top-quintile-one-shot-long"
CTREND_STUDY = CTREND_DIR / "study.py"


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


q20 = load_module(Q20_STUDY, "halpha_nearness52_q20_adapter")
ctrend = load_module(CTREND_STUDY, "halpha_nearness52_ctrend_adapter")
SYMBOLS = list(q20.SYMBOLS)
CATEGORY_MEMBERS = dict(q20.CATEGORY_MEMBERS)
SYMBOL_TO_CATEGORY = dict(q20.SYMBOL_TO_CATEGORY)
UNIVERSE_PATH = q20.UNIVERSE_PATH
UNIVERSE_SHA256 = q20.UNIVERSE_SHA256
STAGES = {
    "development": ("2024-01-01T00:00:00Z", "2024-12-30T00:00:00Z"),
    "evaluation": ("2025-01-06T00:00:00Z", "2025-12-29T00:00:00Z"),
}
CONFIG = {
    "strategy_id": "RESEARCH_NEARNESS52_TOP_DECILE_WEEKLY_LONG_0P25X_V1",
    "direction": "LONG_ONLY",
    "formation_weeks": 52,
    "hold_days": 7,
    "gap_full_days": 1,
    "top_fraction": 0.10,
    "top5_count": 5,
    "notional_fraction": 0.25,
    "minimum_rankable_symbols": 20,
    "minimum_median_quote_volume_30d": 10_000_000.0,
    "cooldown_full_days": 1,
    "annual_capital_hurdle": 0.04,
    "max_excluded_trade_fraction": 0.02,
    "costs": {
        "favorable": {"fee_per_side": 0.0006, "slippage_per_side": 0.0, "funding_stress": False},
        "base": {"fee_per_side": 0.0006, "slippage_per_side": 0.0010, "funding_stress": False},
        "stress": {"fee_per_side": 0.0006, "slippage_per_side": 0.0020, "funding_stress": True},
    },
    "long_funding_stress": {"positive_cost_multiplier": 1.5, "negative_benefit_multiplier": 0.5},
    "bootstrap": {"block_weeks": 4, "repetitions": 5000, "seed": 20260722},
    "diagnostics": [
        "nearness26", "nearness100", "top5", "mom52", "scheduled_long", "market_long",
    ],
}
FROZEN_FILES = ["README.md", "preregistration.md", "sources.md", "study.py"]

# Reuse only framework-independent cost, return, bootstrap and public-data adapters.
q20.CONFIG = CONFIG
q20.STAGES = STAGES


def iso_now() -> str:
    return q20.iso_now()


def sha256_file(path: Path) -> str:
    return q20.sha256_file(path)


def canonical_digest(value: Any) -> str:
    return q20.canonical_digest(value)


def read_json(path: Path) -> Any:
    return q20.read_json(path)


def write_json(path: Path, value: dict[str, Any], *, digest: bool = False) -> None:
    q20.write_json(path, value, digest=digest)


def validate_universe() -> None:
    q20.validate_universe()


def source_entries() -> list[dict[str, Any]]:
    paths: list[tuple[Path, str]] = [
        (Q20_STUDY, "reused 2024-2025 public daily/funding adapter and cost/statistics primitives"),
        (Q20_DIR / "checkpoint.json", "frozen Q20 adapter identity"),
        (Q20_DIR / "amendment-001.json", "Q20 implementation amendment chain"),
        (Q20_DIR / "amendment-002.json", "Q20 implementation amendment chain"),
        (Q20_DIR / "source_reuse_manifest.json", "Q20 public-source identity chain"),
        (Q20_DIR / "data_quality_development.json", "Q20 2024 source quality evidence"),
        (CTREND_STUDY, "reused pre-2024 public daily warm-up adapter"),
        (CTREND_DIR / "checkpoint.json", "frozen CTREND adapter identity"),
        (CTREND_DIR / "amendment-001.json", "CTREND implementation amendment chain"),
        (CTREND_DIR / "source_reuse_manifest.json", "CTREND public-source identity chain"),
        (CTREND_DIR / "source_supplement_manifest.json", "pre-2024 public daily file identities"),
        (CTREND_DIR / "data_quality_development.json", "pre-2024 source quality evidence"),
        (UNIVERSE_PATH, "frozen current target universe"),
    ]
    output: list[dict[str, Any]] = []
    for path, role in paths:
        if not path.exists():
            raise RuntimeError(f"missing source identity: {path}")
        output.append({
            "path": str(path), "bytes": path.stat().st_size,
            "sha256": sha256_file(path), "role": role,
        })
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
        "formal_strategy": {
            "strategy_id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT",
            "version": "1.0.1", "instrument": "BTCUSDT-PERP",
        },
        "research_kind": "STRATEGY_CANDIDATE",
        "question": (
            "Does 52-week-high nearness identify a fixed configured liquid Binance USD-M target whose weekly "
            "0.25x LONG plan clears retail costs, funding, a 4% full-plan-capital hurdle, plain 52-week momentum, "
            "market beta, robustness, breadth, risk and sequential 2024-2025 evidence?"
        ),
        "known_exposure": (
            "Jia et al. 2026 selected and tested the broad-market spot effect on a sample overlapping both stages; "
            "Halpha has also viewed these historical market paths in earlier questions. Sequencing prevents local "
            "adaptation but cannot make this post-publication or independent forward evidence."
        ),
        "support_limit": (
            "Even if both historical stages pass, the conclusion is capped at INSUFFICIENT_EVIDENCE. At least 26 "
            "eligible unchanged-rule weeks spanning two market states must accrue after this checkpoint in a "
            "separate question before product qualification can be considered."
        ),
        "family_stop_rule": (
            "On failure, close this fixed nearness52 long conversion; do not search nearby windows, top counts, "
            "holds, gaps, symbols, categories, costs, states or directions without new forward evidence or an "
            "independent economic mechanism."
        ),
        "configuration": CONFIG,
        "stages": {key: list(value) for key, value in STAGES.items()},
        "symbols": SYMBOLS, "categories": CATEGORY_MEMBERS,
        "selection_scope": {"selectable_primary_configurations": 1, "computed_columns": 7},
        "stage_open_rule": "development -> evaluation; evaluation sealed until development PASS",
        "frozen_file_sha256": {name: sha256_file(HERE / name) for name in FROZEN_FILES},
        "source_reuse_digest": read_json(HERE / "source_reuse_manifest.json")["content_digest"],
        "environment": {
            "python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
            "scipy": scipy.__version__, "vectorbt": vbt.__version__,
        },
        "allowed_after_checkpoint": (
            "Only deterministic stage artifacts and documented implementation-only amendments preserving the "
            "economic rule; no credentialed market endpoint and no product/runtime change."
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
    expected_stages = {key: list(value) for key, value in STAGES.items()}
    if checkpoint.get("configuration") != CONFIG or checkpoint.get("stages") != expected_stages:
        raise RuntimeError("checkpoint differs from code")
    validate_universe()
    for name, expected in checkpoint["frozen_file_sha256"].items():
        actual = sha256_file(HERE / name)
        if actual == expected:
            continue
        chain = expected
        amendments = [] if name != "study.py" else sorted(HERE.glob("amendment-*.json"))
        for amendment_path in amendments:
            amendment = read_json(amendment_path)
            if not (
                canonical_digest(amendment) == amendment.get("content_digest")
                and amendment.get("checkpoint_digest") == checkpoint["content_digest"]
                and amendment.get("original_study_sha256") == chain
                and amendment.get("economic_rule_changed") is False
            ):
                raise RuntimeError(f"invalid amendment: {amendment_path.name}")
            chain = amendment["amended_study_sha256"]
        if chain != actual:
            raise RuntimeError(f"frozen file changed: {name}")
    reuse = read_json(HERE / "source_reuse_manifest.json")
    if canonical_digest(reuse) != reuse.get("content_digest") or reuse["content_digest"] != checkpoint["source_reuse_digest"]:
        raise RuntimeError("source reuse identity mismatch")
    for item in reuse["entries"]:
        source = Path(item["path"])
        if not source.exists() or source.stat().st_size != int(item["bytes"]) or sha256_file(source) != item["sha256"]:
            raise RuntimeError(f"source changed: {source}")
    return checkpoint


def stage_authorized(stage: str) -> None:
    if stage == "evaluation":
        gate = HERE / "development_gate.json"
        if not gate.exists() or read_json(gate).get("status") != "PASS":
            raise RuntimeError("evaluation sealed until development PASS")


def stage_entries(stage: str) -> pd.DatetimeIndex:
    start, end = map(pd.Timestamp, STAGES[stage])
    return pd.date_range(start, end, freq="W-MON", inclusive="left")


def combine_bars(*collections: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    output: dict[str, pd.DataFrame] = {}
    for symbol in SYMBOLS:
        combined = pd.concat([collection[symbol] for collection in collections], axis=0).sort_index()
        output[symbol] = combined[~combined.index.duplicated(keep="last")]
    return output


def load_stage(stage: str) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame], dict[str, Any]]:
    if stage not in STAGES:
        raise ValueError(stage)
    early_bars, _ = ctrend.load_all()
    development_bars, development_funding, development_meta = q20.load_stage("development")
    if stage == "development":
        return combine_bars(early_bars, development_bars), development_funding, development_meta
    evaluation_bars, evaluation_funding, evaluation_meta = q20.load_stage("evaluation")
    return combine_bars(early_bars, development_bars, evaluation_bars), evaluation_funding, evaluation_meta


def feature_frame(frame: pd.DataFrame) -> pd.DataFrame:
    calendar = pd.date_range(frame.index.min(), frame.index.max(), freq="1D")
    daily = frame.reindex(calendar)
    output = pd.DataFrame(index=daily.index)
    saturday_close = daily["close"].where(daily.index.dayofweek == 5)
    weekly = saturday_close.dropna()
    for weeks in (26, 52, 100):
        value = weekly / weekly.rolling(weeks, min_periods=weeks).max()
        output.loc[value.index, f"nearness{weeks}"] = value
    output.loc[weekly.index, "mom52"] = weekly / weekly.shift(52) - 1.0
    output["median_quote_volume_30d"] = daily["quote_volume"].rolling(30, min_periods=30).median()
    required = daily[["open", "high", "low", "close", "quote_volume"]].notna().all(axis=1)
    output["complete_701d"] = required.rolling(701, min_periods=701).sum().eq(701)
    return output.replace([np.inf, -np.inf], np.nan)


def command_prepare(args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    stage_authorized(args.stage)
    bars, funding, metadata = load_stage(args.stage)
    parent_path = Q20_DIR / f"data_quality_{args.stage}.json"
    if not parent_path.exists():
        raise RuntimeError(f"parent data quality missing: {parent_path.name}")
    parent_quality = read_json(parent_path)
    status = parent_quality.get("status") == "PASS" and metadata.get("overlap_mismatch_rows", 0) == 0
    entries = stage_entries(args.stage)
    first_cutoff = entries[0] - pd.Timedelta(days=2)
    required_start = first_cutoff - pd.Timedelta(days=700)
    required_end = entries[-1] + pd.Timedelta(days=7)
    expected = pd.date_range(required_start, required_end, freq="1D")
    features = {symbol: feature_frame(frame) for symbol, frame in bars.items()}
    per_symbol: dict[str, Any] = {}
    for symbol in SYMBOLS:
        subset = bars[symbol][(bars[symbol].index >= required_start) & (bars[symbol].index <= required_end)]
        invalid_ohlc = int((
            (subset[["open", "high", "low", "close"]] <= 0).any(axis=1)
            | (subset["high"] < subset[["open", "close"]].max(axis=1))
            | (subset["low"] > subset[["open", "close"]].min(axis=1))
        ).sum())
        invalid_volume = int((subset[["volume", "quote_volume"]] < 0).any(axis=1).sum())
        rates = funding[symbol][(funding[symbol].index > entries[0]) & (funding[symbol].index <= required_end)]
        max_gap = float(rates.index.to_series().diff().dt.total_seconds().max() / 3600.0) if len(rates) > 1 else math.inf
        item_pass = invalid_ohlc == 0 and invalid_volume == 0 and len(rates) > 0 and max_gap <= 24.0
        status = status and item_pass
        per_symbol[symbol] = {
            "daily_rows": int(len(subset)), "missing_days": int(len(expected.difference(subset.index))),
            "invalid_ohlc_rows": invalid_ohlc, "invalid_volume_rows": invalid_volume,
            "funding_rows": int(len(rates)), "missing_mark_rows": int(rates["markPrice"].isna().sum()),
            "max_funding_gap_hours": None if not math.isfinite(max_gap) else max_gap,
            "source_integrity": "PASS" if item_pass else "FAIL",
        }
    counts: dict[str, int] = {}
    for entry in entries:
        cutoff = entry - pd.Timedelta(days=2)
        count = 0
        for symbol in SYMBOLS:
            values = features[symbol].loc[cutoff] if cutoff in features[symbol].index else None
            if values is not None and bool(values["complete_701d"]) and pd.notna(values["nearness52"]):
                if float(values["median_quote_volume_30d"]) >= float(CONFIG["minimum_median_quote_volume_30d"]):
                    count += 1
        counts[entry.isoformat()] = count
    below = {key: value for key, value in counts.items() if value < int(CONFIG["minimum_rankable_symbols"])}
    source_manifest = Q20_DIR / f"source_manifest_{args.stage}.json"
    payload = {
        "checked_at_utc": iso_now(), "stage": args.stage, "status": "PASS" if status else "FAIL",
        "checkpoint_digest": checkpoint["content_digest"],
        "required_daily_range_inclusive": [required_start.isoformat(), required_end.isoformat()],
        "source_overlap": metadata,
        "decision_input_availability": {
            "minimum_rankable": min(counts.values()), "maximum_rankable": max(counts.values()),
            "global_no_action_dates_below_minimum": below,
        },
        "symbols": per_symbol, "parent_data_quality_sha256": sha256_file(parent_path),
        "source_manifest_sha256": sha256_file(source_manifest) if source_manifest.exists() else None,
        "rule": (
            "Calendar gaps are never imputed. All feature inputs end with the Saturday bar, Sunday is a full-day "
            "gap, and Monday open is the first action. A target without 701 contiguous daily bars, exact weekly "
            "features or 10m median quote volume is NO_ACTION; fewer than 20 targets makes the week global "
            "NO_ACTION without invalidating otherwise intact source data."
        ),
    }
    write_json(HERE / f"data_quality_{args.stage}.json", payload, digest=True)
    print(json.dumps({"stage": args.stage, "status": payload["status"], "minimum_rankable": min(counts.values())}))


def build_panel(bars: dict[str, pd.DataFrame], stage: str) -> pd.DataFrame:
    features = {symbol: feature_frame(frame) for symbol, frame in bars.items()}
    rows: list[dict[str, Any]] = []
    feature_columns = [
        "nearness26", "nearness52", "nearness100", "mom52",
        "median_quote_volume_30d", "complete_701d",
    ]
    for entry in stage_entries(stage):
        cutoff, exit_time = entry - pd.Timedelta(days=2), entry + pd.Timedelta(days=7)
        candidates: list[dict[str, Any]] = []
        for symbol in SYMBOLS:
            if cutoff not in features[symbol].index or entry not in bars[symbol].index or exit_time not in bars[symbol].index:
                continue
            values = features[symbol].loc[cutoff, feature_columns]
            numeric = values.drop(labels=["complete_701d"])
            if (
                numeric.isna().any() or not bool(values["complete_701d"])
                or float(values["median_quote_volume_30d"]) < float(CONFIG["minimum_median_quote_volume_30d"])
            ):
                continue
            candidates.append({
                "entry_time": entry, "signal_cutoff": cutoff, "exit_time": exit_time, "symbol": symbol,
                "entry_price": float(bars[symbol].at[entry, "open"]),
                "exit_price": float(bars[symbol].at[exit_time, "open"]),
                **{name: float(values[name]) for name in numeric.index},
            })
        if len(candidates) < int(CONFIG["minimum_rankable_symbols"]):
            continue
        for item in candidates:
            item["eligible_count"] = len(candidates)
        rows.extend(candidates)
    if not rows:
        raise RuntimeError(f"panel empty: {stage}")
    return pd.DataFrame(rows).sort_values(["entry_time", "symbol"]).reset_index(drop=True)


def top_ranks(frame: pd.DataFrame, column: str) -> pd.Series:
    ordered = frame.sort_values([column, "symbol"], ascending=[False, True])
    ranks = pd.Series(np.arange(1, len(ordered) + 1), index=ordered.index, dtype="int64")
    return ranks.reindex(frame.index)


def select_variant(panel: pd.DataFrame, variant: str) -> dict[pd.Timestamp, pd.DataFrame]:
    output: dict[pd.Timestamp, pd.DataFrame] = {}
    for entry, raw in panel.groupby("entry_time", sort=True):
        week = raw.copy()
        count = int(math.ceil(len(week) * float(CONFIG["top_fraction"])))
        if variant in {"main", "nearness26", "nearness100", "top5"}:
            column = "nearness52" if variant in {"main", "top5"} else variant
            rank = top_ranks(week, column)
            selected_count = min(int(CONFIG["top5_count"]), len(week)) if variant == "top5" else count
            selected = week[rank <= selected_count].copy()
            selected["selection_rank"] = rank.loc[selected.index]
            selected["selection_score"] = selected[column]
        elif variant == "mom52":
            rank = top_ranks(week, "mom52")
            selected = week[rank <= count].copy()
            selected["selection_rank"] = rank.loc[selected.index]
            selected["selection_score"] = selected["mom52"]
        elif variant in {"scheduled_long", "market_long"}:
            selected = week.copy()
            selected["selection_rank"] = np.nan
            selected["selection_score"] = selected["nearness52"]
        else:
            raise ValueError(variant)
        output[pd.Timestamp(entry)] = selected.sort_values("symbol")
    return output


def adjusted_long_funding_rate(rate: float) -> float:
    return q20.adjusted_long_funding_rate(rate)


def make_trades(
    selections: dict[pd.Timestamp, pd.DataFrame], funding: dict[str, pd.DataFrame], stage: str,
    variant: str, *, cooldown: bool = True,
) -> tuple[pd.DataFrame, dict[str, int]]:
    rows: list[dict[str, Any]] = []
    last_exit: dict[str, pd.Timestamp] = {}
    planned = excluded_marks = excluded_funding = cooldown_skips = 0
    for entry in sorted(selections):
        for _, item in selections[entry].iterrows():
            symbol = str(item["symbol"])
            planned += 1
            if cooldown and symbol in last_exit and entry <= last_exit[symbol] + pd.Timedelta(days=int(CONFIG["cooldown_full_days"])):
                cooldown_skips += 1
                continue
            exit_time = pd.Timestamp(item["exit_time"])
            rates = funding[symbol][(funding[symbol].index > entry) & (funding[symbol].index <= exit_time)]
            if rates.empty:
                excluded_funding += 1
                last_exit[symbol] = exit_time
                continue
            if rates["markPrice"].isna().any():
                excluded_marks += 1
                last_exit[symbol] = exit_time
                continue
            entry_price, exit_price = float(item["entry_price"]), float(item["exit_price"])
            notional = float(CONFIG["notional_fraction"])
            quantity = notional / entry_price
            actual_funding = -float((quantity * rates["markPrice"] * rates["fundingRate"]).sum())
            stress_funding = -float((
                quantity * rates["markPrice"] * rates["fundingRate"].map(adjusted_long_funding_rate)
            ).sum())
            rows.append({
                "trade_id": f"{stage}-{variant}-{entry:%Y%m%d}-{symbol}", "strategy_variant": variant,
                "entry_time": entry, "exit_time": exit_time, "signal_cutoff": item["signal_cutoff"],
                "symbol": symbol, "category": SYMBOL_TO_CATEGORY[symbol], "eligible_count": int(item["eligible_count"]),
                "nearness26": float(item["nearness26"]), "nearness52": float(item["nearness52"]),
                "nearness100": float(item["nearness100"]), "mom52": float(item["mom52"]),
                "selection_score": float(item["selection_score"]),
                "selection_rank": float(item["selection_rank"]) if pd.notna(item["selection_rank"]) else np.nan,
                "entry_price": entry_price, "exit_price": exit_price, "notional_fraction": notional,
                "quantity_per_unit_plan_capital": quantity, "funding_events": int(len(rates)),
                "actual_funding_return": actual_funding, "stress_funding_return": stress_funding,
                "gross_long_return": notional * (exit_price / entry_price - 1.0),
            })
            last_exit[symbol] = exit_time
    if not rows:
        raise RuntimeError(f"strategy produced no trades: {stage} {variant}")
    return pd.DataFrame(rows), {
        "planned": planned, "excluded_missing_marks": excluded_marks,
        "excluded_missing_funding": excluded_funding, "cooldown_skips": cooldown_skips,
    }


def attach_returns(trades: pd.DataFrame) -> pd.DataFrame:
    return q20.attach_returns(trades)


def summarize(trades: pd.DataFrame, stage: str) -> dict[str, Any]:
    return q20.summarize(trades, stage)


def compare(
    main: pd.DataFrame, baseline: pd.DataFrame, column: str, *, baseline_no_action_as_cash: bool = False,
) -> dict[str, Any]:
    return q20.compare(main, baseline, column, baseline_no_action_as_cash=baseline_no_action_as_cash)


def command_self_test(_args: argparse.Namespace) -> None:
    dates = pd.date_range("2020-01-04", periods=105, freq="W-SAT", tz="UTC")
    daily_dates = pd.date_range(dates.min() - pd.Timedelta(days=730), dates.max(), freq="1D", tz="UTC")
    close = pd.Series(np.linspace(50.0, 100.0, len(daily_dates)), index=daily_dates)
    sample_frame = pd.DataFrame({
        "open": close, "high": close, "low": close, "close": close,
        "volume": 1.0, "quote_volume": 20_000_000.0,
    })
    features = feature_frame(sample_frame)
    last = dates[-1]
    if not math.isclose(float(features.at[last, "nearness52"]), 1.0, abs_tol=1e-14):
        raise RuntimeError("52-week high nearness mismatch")
    synthetic = pd.DataFrame([{
        "trade_id": "test", "entry_price": 100.0, "exit_price": 110.0,
        "quantity_per_unit_plan_capital": 0.0025,
    }])
    vector = float(q20.vectorbt_long_returns(synthetic, 0.0006, 0.0010)[0])
    manual = float(q20.manual_long_return(synthetic.iloc[0], 0.0006, 0.0010))
    if not math.isclose(vector, manual, rel_tol=0.0, abs_tol=1e-12):
        raise RuntimeError("VectorBT/manual mismatch")
    if adjusted_long_funding_rate(0.001) != 0.0015 or adjusted_long_funding_rate(-0.001) != -0.0005:
        raise RuntimeError("funding stress direction mismatch")
    print(json.dumps({
        "status": "PASS", "nearness52_at_high": float(features.at[last, "nearness52"]),
        "vectorbt_manual_reconciliation": vector - manual, "funding_stress": "PASS",
    }))


def command_analyze(args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    stage_authorized(args.stage)
    dq_path = HERE / f"data_quality_{args.stage}.json"
    if not dq_path.exists() or read_json(dq_path).get("status") != "PASS":
        raise RuntimeError(f"data quality is not PASS: {args.stage}")
    bars, funding, _ = load_stage(args.stage)
    panel = build_panel(bars, args.stage)
    variants = ["main", *CONFIG["diagnostics"]]
    selections = {name: select_variant(panel, name) for name in variants}
    trades: dict[str, pd.DataFrame] = {}
    opportunity_counts: dict[str, dict[str, int]] = {}
    for name in variants:
        raw, opportunity_counts[name] = make_trades(
            selections[name], funding, args.stage, name, cooldown=name != "market_long",
        )
        trades[name] = attach_returns(raw)
    csv_hashes: dict[str, str] = {}
    for name, frame in trades.items():
        path = HERE / f"{args.stage}_{name}_trades.csv"
        frame.to_csv(path, index=False, date_format="%Y-%m-%dT%H:%M:%S%z")
        csv_hashes[path.name] = sha256_file(path)
    summaries = {name: summarize(frame, args.stage) for name, frame in trades.items()}
    correlations = [
        float(week["nearness52"].corr(week["mom52"], method="spearman"))
        for _, week in panel.groupby("entry_time", sort=True)
    ]
    payload = {
        "analyzed_at_utc": iso_now(), "stage": args.stage,
        "checkpoint_digest": checkpoint["content_digest"],
        "data_quality_digest": read_json(dq_path)["content_digest"],
        "panel_rows": int(len(panel)), "panel_weeks": int(panel["entry_time"].nunique()),
        "opportunity_counts": opportunity_counts, "summaries": summaries,
        "comparisons": {
            "base_vs_mom52": compare(
                trades["main"], trades["mom52"], "base_net_return", baseline_no_action_as_cash=True,
            ),
            "stress_vs_mom52": compare(
                trades["main"], trades["mom52"], "stress_net_return", baseline_no_action_as_cash=True,
            ),
            "gross_vs_market_long": compare(trades["main"], trades["market_long"], "gross_long_return"),
            "base_vs_scheduled_long": compare(
                trades["main"], trades["scheduled_long"], "base_net_return", baseline_no_action_as_cash=True,
            ),
            "nearness52_vs_mom52_weekly_spearman": {
                "median": float(np.nanmedian(correlations)), "minimum": float(np.nanmin(correlations)),
                "maximum": float(np.nanmax(correlations)), "weeks": len(correlations),
            },
        },
        "search_disclosure": {"selectable_primary_configurations": 1, "computed_columns": len(variants)},
        "trade_csv_sha256": csv_hashes,
    }
    write_json(HERE / f"{args.stage}.json", payload, digest=True)
    evidence = read_json(HERE / f"{args.stage}.json")
    print(json.dumps({
        "stage": args.stage, "trades": summaries["main"]["trades"],
        "base_after_hurdle": summaries["main"]["scenarios"]["base"]["date_mean_after_hurdle"],
        "stress_after_hurdle": summaries["main"]["scenarios"]["stress"]["date_mean_after_hurdle"],
        "base_vs_mom52": payload["comparisons"]["base_vs_mom52"]["difference_mean"],
        "digest": evidence["content_digest"],
    }))


def gate_checks(evidence: dict[str, Any]) -> tuple[dict[str, bool], dict[str, Any]]:
    main = evidence["summaries"]["main"]
    base, stress = main["scenarios"]["base"], main["scenarios"]["stress"]
    counts = evidence["opportunity_counts"]["main"]
    excluded = counts["excluded_missing_marks"] + counts["excluded_missing_funding"]
    excluded_fraction = float(excluded / counts["planned"]) if counts["planned"] else 1.0
    neighbors = [
        evidence["summaries"][name]["scenarios"]["stress"]["date_mean_after_hurdle"]
        for name in ("nearness26", "nearness100", "top5")
    ]
    positive_categories = sum(item["base_mean_after_hurdle"] > 0 for item in main["by_category"].values())
    mom = evidence["comparisons"]["base_vs_mom52"]
    market = evidence["comparisons"]["gross_vs_market_long"]
    checks = {
        "data_quality_pass": read_json(HERE / f"data_quality_{evidence['stage']}.json")["status"] == "PASS",
        "vectorbt_reconciled": main["maximum_vectorbt_reconciliation_error"] <= 1e-10,
        "excluded_trade_fraction_at_most_2pct": excluded_fraction <= float(CONFIG["max_excluded_trade_fraction"]),
        "trades_at_least_50": main["trades"] >= 50,
        "entry_dates_at_least_20": main["entry_dates"] >= 20,
        "symbols_at_least_15": main["symbols"] >= 15,
        "each_half_at_least_8_dates": all(item["dates"] >= 8 for item in main["by_half"].values()),
        "base_after_hurdle_positive": base["date_mean_after_hurdle"] > 0,
        "stress_after_hurdle_positive": stress["date_mean_after_hurdle"] > 0,
        "stress_bootstrap_lower_positive": stress["date_mean_after_hurdle_bootstrap_95pct"][0] > 0,
        "both_halves_base_after_hurdle_positive": all(item["mean_after_hurdle"] > 0 for item in main["by_half"].values()),
        "base_increment_vs_mom52_positive": mom["difference_mean"] > 0,
        "base_increment_vs_mom52_bootstrap_lower_positive": mom["difference_bootstrap_95pct"][0] > 0,
        "gross_excess_vs_market_positive": market["difference_mean"] > 0,
        "gross_excess_vs_market_bootstrap_lower_positive": market["difference_bootstrap_95pct"][0] > 0,
        "two_of_three_neighbors_stress_positive": sum(value > 0 for value in neighbors) >= 2,
        "four_positive_categories": positive_categories >= 4,
        "half_targets_positive": main["positive_target_fraction_at_least_two_trades"] >= 0.50,
        "largest_positive_pnl_share_at_most_25pct": main["largest_positive_pnl_share"] <= 0.25,
        "date_portfolio_drawdown_above_minus_20pct": base["date_portfolio_max_drawdown"] > -0.20,
        "worst_target_drawdown_above_minus_30pct": main["worst_symbol_base_max_drawdown"] > -0.30,
    }
    diagnostics = {
        "excluded_trade_fraction": excluded_fraction, "neighbor_stress_after_hurdle": neighbors,
        "positive_categories": positive_categories,
    }
    return checks, diagnostics


def conclusion_for_failure(evidence: dict[str, Any]) -> str:
    main = evidence["summaries"]["main"]
    economic = (
        main["scenarios"]["base"]["date_mean_after_hurdle"] > 0
        and main["scenarios"]["stress"]["date_mean_after_hurdle"] > 0
        and evidence["comparisons"]["base_vs_mom52"]["difference_mean"] > 0
        and evidence["comparisons"]["gross_vs_market_long"]["difference_mean"] > 0
    )
    return "INSUFFICIENT_EVIDENCE" if economic else "DOES_NOT_SUPPORT"


def command_gate(args: argparse.Namespace) -> None:
    ensure_checkpoint()
    stage_authorized(args.stage)
    evidence = read_json(HERE / f"{args.stage}.json")
    if canonical_digest(evidence) != evidence.get("content_digest"):
        raise RuntimeError("evidence digest mismatch")
    checks, diagnostics = gate_checks(evidence)
    status = "PASS" if all(checks.values()) else "FAIL"
    gate = {
        "generated_at_utc": iso_now(), "stage": args.stage, "status": status,
        "checks": checks, "failed_checks": [key for key, value in checks.items() if not value],
        "diagnostics": diagnostics, "evidence_digest": evidence["content_digest"],
    }
    write_json(HERE / f"{args.stage}_gate.json", gate, digest=True)
    gate = read_json(HERE / f"{args.stage}_gate.json")
    if status == "FAIL":
        terminal = {
            "generated_at_utc": iso_now(), "conclusion": conclusion_for_failure(evidence),
            "stopped_after": args.stage, "gate_status": status, "failed_checks": gate["failed_checks"],
            "main": evidence["summaries"]["main"], "comparisons": evidence["comparisons"],
            "diagnostics": {name: evidence["summaries"][name] for name in CONFIG["diagnostics"]},
            "later_stages": "NOT_OPENED_BY_SEQUENTIAL_GATE", "handoff": "NOT_GENERATED",
            "product_effects": "NONE",
        }
        write_json(HERE / "results.json", terminal, digest=True)
    elif args.stage == "evaluation":
        terminal = {
            "generated_at_utc": iso_now(), "conclusion": "INSUFFICIENT_EVIDENCE",
            "stage_gates": {"development": "PASS", "evaluation": "PASS"},
            "reason": (
                "Both historical stages passed, but Jia et al. 2026 selected the effect using overlapping paths "
                "and Halpha had already exposed them. This is not independent forward evidence for qualification "
                "or a long-run profitability claim."
            ),
            "forward_requirement": (
                "Keep the rule frozen for at least 26 eligible weeks spanning two market states, then repeat the "
                "same costs, MOM52 and market baselines, robustness, breadth and risk gates in a separate question."
            ),
            "handoff": "NOT_GENERATED", "product_effects": "NONE",
        }
        write_json(HERE / "results.json", terminal, digest=True)
    print(json.dumps({"stage": args.stage, "status": status, "failed": gate["failed_checks"]}))


def command_validate(_args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    verified_json = 0
    for path in sorted(HERE.glob("*.json")):
        item = read_json(path)
        if "content_digest" in item:
            if canonical_digest(item) != item["content_digest"]:
                raise RuntimeError(f"JSON digest mismatch: {path.name}")
            verified_json += 1
    stages: list[str] = []
    csv_files = 0
    for stage in STAGES:
        evidence_path = HERE / f"{stage}.json"
        if not evidence_path.exists():
            continue
        evidence = read_json(evidence_path)
        for name, expected in evidence["trade_csv_sha256"].items():
            path = HERE / name
            if not path.exists() or sha256_file(path) != expected:
                raise RuntimeError(f"trade CSV mismatch: {name}")
            csv_files += 1
        stages.append(stage)
    conclusion = read_json(HERE / "results.json")["conclusion"] if (HERE / "results.json").exists() else "OPEN"
    print(json.dumps({
        "status": "PASS", "checkpoint": checkpoint["content_digest"], "opened_stages": stages,
        "verified_json_digests": verified_json, "verified_trade_csvs": csv_files, "conclusion": conclusion,
    }))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="52-week-high-nearness weekly single-target LONG study")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("checkpoint").set_defaults(func=command_checkpoint)
    sub.add_parser("self-test").set_defaults(func=command_self_test)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--stage", choices=tuple(STAGES), required=True)
    prepare.set_defaults(func=command_prepare)
    analyze = sub.add_parser("analyze")
    analyze.add_argument("--stage", choices=tuple(STAGES), required=True)
    analyze.set_defaults(func=command_analyze)
    gate = sub.add_parser("gate")
    gate.add_argument("--stage", choices=tuple(STAGES), required=True)
    gate.set_defaults(func=command_gate)
    sub.add_parser("validate").set_defaults(func=command_validate)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
