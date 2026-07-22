from __future__ import annotations

import argparse
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
from scipy.stats import skew
import vectorbt as vbt


HERE = Path(__file__).resolve().parent
Q21_DIR = HERE.parent / "fifty-two-week-high-nearness-weekly-long"
Q21_STUDY = Q21_DIR / "study.py"
CATEGORY_DIR = HERE.parent / "category-momentum-gated-one-shot-long"
CATEGORY_STUDY = CATEGORY_DIR / "study.py"


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


q21 = load_module(Q21_STUDY, "halpha_ptv_q21_adapter")
category = load_module(CATEGORY_STUDY, "halpha_ptv_category_adapter")
SYMBOLS = list(q21.SYMBOLS)
CATEGORY_MEMBERS = dict(q21.CATEGORY_MEMBERS)
SYMBOL_TO_CATEGORY = dict(q21.SYMBOL_TO_CATEGORY)
UNIVERSE_PATH = q21.UNIVERSE_PATH
UNIVERSE_SHA256 = q21.UNIVERSE_SHA256
STAGES = {
    "development": ("2022-01-03T00:00:00Z", "2024-01-01T00:00:00Z"),
    "evaluation": ("2024-01-01T00:00:00Z", "2024-12-30T00:00:00Z"),
}
CONFIG = {
    "strategy_id": "RESEARCH_PTV52_BOTTOM_DECILE_WEEKLY_LONG_0P25X_V1",
    "direction": "LONG_ONLY",
    "formation_weeks": 52,
    "hold_days": 7,
    "gap_full_days": 1,
    "top_fraction": 0.10,
    "notional_fraction": 0.25,
    "minimum_rankable_symbols": 20,
    "minimum_median_quote_volume_30d": 10_000_000.0,
    "cooldown_full_days": 1,
    "annual_capital_hurdle": 0.04,
    "max_excluded_trade_fraction": 0.02,
    "prospect_parameters": {"alpha": 0.88, "beta": 0.88, "lambda": 2.25, "gamma": 0.61, "delta": 0.69},
    "costs": {
        "favorable": {"fee_per_side": 0.0006, "slippage_per_side": 0.0, "funding_stress": False},
        "base": {"fee_per_side": 0.0006, "slippage_per_side": 0.0010, "funding_stress": False},
        "stress": {"fee_per_side": 0.0006, "slippage_per_side": 0.0020, "funding_stress": True},
    },
    "long_funding_stress": {"positive_cost_multiplier": 1.5, "negative_benefit_multiplier": 0.5},
    "bootstrap": {"block_weeks": 4, "repetitions": 5000, "seed": 20260722},
    "diagnostics": [
        "ptv26", "ptv78", "ptv52_zero", "low_mom52", "low_skew52", "high_vol52",
        "scheduled_long", "market_long",
    ],
}
FROZEN_FILES = ["README.md", "preregistration.md", "sources.md", "study.py"]

q21.CONFIG = CONFIG
q21.STAGES = STAGES
q21.q20.CONFIG = CONFIG
q21.q20.STAGES = STAGES


def iso_now() -> str:
    return q21.iso_now()


def sha256_file(path: Path) -> str:
    return q21.sha256_file(path)


def canonical_digest(value: Any) -> str:
    return q21.canonical_digest(value)


def read_json(path: Path) -> Any:
    return q21.read_json(path)


def write_json(path: Path, value: dict[str, Any], *, digest: bool = False) -> None:
    q21.write_json(path, value, digest=digest)


def validate_universe() -> None:
    q21.validate_universe()


def source_entries() -> list[dict[str, Any]]:
    q20_dir = Q21_DIR.parent / "price-path-continuity-weekly-winner-long"
    ctrend_dir = Q21_DIR.parent / "ctrend-weekly-top-quintile-one-shot-long"
    paths: list[tuple[Path, str]] = [
        (Q21_STUDY, "reused cost, funding, VectorBT and statistical primitives"),
        (Q21_DIR / "checkpoint.json", "frozen Q21 adapter identity"),
        (Q21_DIR / "amendment-001.json", "Q21 implementation amendment chain"),
        (CATEGORY_STUDY, "reused 2022-2023 official daily/funding loader"),
        (CATEGORY_DIR / "checkpoint.json", "frozen category adapter identity"),
        (CATEGORY_DIR / "source_manifest_development.json", "2022-2023 public source identities"),
        (CATEGORY_DIR / "data_quality_development.json", "2022-2023 source quality evidence"),
        (ctrend_dir / "study.py", "reused pre-2022 official daily warm-up loader"),
        (ctrend_dir / "checkpoint.json", "frozen warm-up adapter identity"),
        (ctrend_dir / "amendment-001.json", "warm-up adapter amendment chain"),
        (ctrend_dir / "source_supplement_manifest.json", "pre-2022 public daily identities"),
        (q20_dir / "study.py", "reused 2024 official daily/funding loader"),
        (q20_dir / "checkpoint.json", "frozen 2024 adapter identity"),
        (q20_dir / "amendment-001.json", "2024 adapter amendment chain"),
        (q20_dir / "amendment-002.json", "2024 adapter amendment chain"),
        (q20_dir / "data_quality_development.json", "2024 source quality evidence"),
        (UNIVERSE_PATH, "frozen current target universe"),
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
    write_json(HERE / "source_reuse_manifest.json", {"created_at_utc": iso_now(), "entries": source_entries()}, digest=True)
    payload = {
        "created_at_utc": iso_now(),
        "baseline_commit": "0bdfeffa616260cebd2d2188ddc8deb9e85c77f4",
        "formal_strategy": {"strategy_id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT", "version": "1.0.1", "instrument": "BTCUSDT-PERP"},
        "research_kind": "STRATEGY_CANDIDATE",
        "question": (
            "Does bottom-decile 52-week cumulative prospect-theory value identify a fixed liquid Binance USD-M "
            "target whose weekly 0.25x LONG plan clears retail costs, funding, a full-plan-capital hurdle, plain "
            "momentum/skewness/volatility explanations, market beta, robustness, breadth and sequential evidence?"
        ),
        "known_exposure": (
            "The source paper ends in 2020; development begins in 2022. Halpha has viewed the underlying paths in "
            "other questions but had not computed PTV rankings or PTV-conditioned returns before this checkpoint."
        ),
        "support_limit": (
            "Both historical stages passing is capped at INSUFFICIENT_EVIDENCE. At least 26 eligible unchanged-rule "
            "weeks spanning two market states after this checkpoint are required in a separate question before handoff."
        ),
        "family_stop_rule": (
            "On failure close this fixed PTV52 long conversion; do not search adjacent windows, thresholds, holds, "
            "symbols, categories, reference points, preference parameters, costs, states or directions without new "
            "forward evidence or an independent mechanism."
        ),
        "configuration": CONFIG,
        "stages": {key: list(value) for key, value in STAGES.items()},
        "symbols": SYMBOLS, "categories": CATEGORY_MEMBERS,
        "selection_scope": {"selectable_primary_configurations": 1, "computed_columns": 9},
        "stage_open_rule": "development -> evaluation; evaluation sealed until development PASS",
        "frozen_file_sha256": {name: sha256_file(HERE / name) for name in FROZEN_FILES},
        "source_reuse_digest": read_json(HERE / "source_reuse_manifest.json")["content_digest"],
        "environment": {
            "python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
            "scipy": scipy.__version__, "vectorbt": vbt.__version__,
        },
        "allowed_after_checkpoint": "Deterministic stage artifacts and implementation-only amendments preserving the economic rule.",
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
        for amendment_path in ([] if name != "study.py" else sorted(HERE.glob("amendment-*.json"))):
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
        path = HERE / "development_gate.json"
        if not path.exists() or read_json(path).get("status") != "PASS":
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
    early_bars, _ = q21.ctrend.load_all()
    category_bars_all, category_funding_all = category.load_all("development")
    category_bars = {symbol: category_bars_all[symbol] for symbol in SYMBOLS}
    category_funding = {symbol: category_funding_all[symbol] for symbol in SYMBOLS}
    if stage == "development":
        return combine_bars(early_bars, category_bars), category_funding, {"overlap_mismatch_rows": 0, "sources": ["ctrend", "category-development"]}
    bars_2024, funding_2024, metadata = q21.q20.load_stage("development")
    return combine_bars(early_bars, category_bars, bars_2024), funding_2024, metadata


def probability_weight(p: float, exponent: float) -> float:
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    numerator = p ** exponent
    return float(numerator / ((p ** exponent + (1.0 - p) ** exponent) ** (1.0 / exponent)))


def prospect_value(values: np.ndarray) -> float:
    values = np.sort(np.asarray(values, dtype=float))
    if len(values) == 0 or not np.isfinite(values).all():
        return math.nan
    params = CONFIG["prospect_parameters"]
    losses = values[values < 0.0]
    gains = values[values >= 0.0]
    total = len(values)
    result = 0.0
    for index, value in enumerate(losses, start=1):
        weight = probability_weight(index / total, params["delta"]) - probability_weight((index - 1) / total, params["delta"])
        result += weight * (-params["lambda"] * ((-value) ** params["beta"]))
    count = len(gains)
    for index, value in enumerate(gains):
        remaining = count - index
        weight = probability_weight(remaining / total, params["gamma"]) - probability_weight((remaining - 1) / total, params["gamma"])
        result += weight * (value ** params["alpha"])
    return float(result)


def build_panel(bars: dict[str, pd.DataFrame], stage: str) -> pd.DataFrame:
    daily: dict[str, pd.DataFrame] = {}
    weekly_close: dict[str, pd.Series] = {}
    for symbol, raw in bars.items():
        frame = raw.reindex(pd.date_range(raw.index.min(), raw.index.max(), freq="1D"))
        frame["median_quote_volume_30d"] = frame["quote_volume"].rolling(30, min_periods=30).median()
        required = frame[["open", "high", "low", "close", "quote_volume"]].notna().all(axis=1)
        frame["complete_547d"] = required.rolling(547, min_periods=547).sum().eq(547)
        daily[symbol] = frame
        weekly_close[symbol] = frame.loc[frame.index.dayofweek == 5, "close"]
    rows: list[dict[str, Any]] = []
    for entry in stage_entries(stage):
        cutoff, exit_time = entry - pd.Timedelta(days=2), entry + pd.Timedelta(days=7)
        candidate_returns: dict[str, np.ndarray] = {}
        candidate_meta: dict[str, dict[str, Any]] = {}
        for symbol in SYMBOLS:
            frame = daily[symbol]
            if cutoff not in frame.index or entry not in frame.index or exit_time not in frame.index:
                continue
            if not bool(frame.at[cutoff, "complete_547d"]):
                continue
            if float(frame.at[cutoff, "median_quote_volume_30d"]) < float(CONFIG["minimum_median_quote_volume_30d"]):
                continue
            closes = weekly_close[symbol].loc[:cutoff].tail(79)
            if len(closes) != 79 or closes.isna().any() or (closes <= 0).any():
                continue
            candidate_returns[symbol] = np.diff(np.log(closes.to_numpy(float)))
            candidate_meta[symbol] = {
                "entry_price": float(frame.at[entry, "open"]), "exit_price": float(frame.at[exit_time, "open"]),
            }
        if len(candidate_returns) < int(CONFIG["minimum_rankable_symbols"]):
            continue
        ordered_symbols = sorted(candidate_returns)
        matrix = np.column_stack([candidate_returns[symbol] for symbol in ordered_symbols])
        market = matrix.mean(axis=1)
        for column, symbol in enumerate(ordered_symbols):
            raw_returns = matrix[:, column]
            excess = raw_returns - market
            rows.append({
                "entry_time": entry, "signal_cutoff": cutoff, "exit_time": exit_time, "symbol": symbol,
                "eligible_count": len(ordered_symbols), **candidate_meta[symbol],
                "ptv26": prospect_value(excess[-26:]), "ptv52": prospect_value(excess[-52:]),
                "ptv78": prospect_value(excess[-78:]), "ptv52_zero": prospect_value(raw_returns[-52:]),
                "mom52": float(excess[-52:].sum()), "skew52": float(skew(excess[-52:], bias=False)),
                "vol52": float(np.std(excess[-52:], ddof=1)),
            })
    if not rows:
        raise RuntimeError(f"panel empty: {stage}")
    panel = pd.DataFrame(rows).replace([np.inf, -np.inf], np.nan).dropna()
    return panel.sort_values(["entry_time", "symbol"]).reset_index(drop=True)


def command_prepare(args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    stage_authorized(args.stage)
    bars, funding, metadata = load_stage(args.stage)
    parent_path = CATEGORY_DIR / "data_quality_development.json" if args.stage == "development" else Q21_DIR.parent / "price-path-continuity-weekly-winner-long" / "data_quality_development.json"
    parent = read_json(parent_path)
    status = parent.get("status") == "PASS" and metadata.get("overlap_mismatch_rows", 0) == 0
    entries = stage_entries(args.stage)
    required_start = entries[0] - pd.Timedelta(days=2 + 546)
    required_end = entries[-1] + pd.Timedelta(days=7)
    expected = pd.date_range(required_start, required_end, freq="1D")
    per_symbol: dict[str, Any] = {}
    for symbol in SYMBOLS:
        subset = bars[symbol][(bars[symbol].index >= required_start) & (bars[symbol].index <= required_end)]
        invalid_ohlc = int(((subset[["open", "high", "low", "close"]] <= 0).any(axis=1) | (subset["high"] < subset[["open", "close"]].max(axis=1)) | (subset["low"] > subset[["open", "close"]].min(axis=1))).sum())
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
    panel = build_panel(bars, args.stage)
    counts = panel.groupby("entry_time")["symbol"].nunique()
    all_entries = stage_entries(args.stage)
    missing_weeks = [entry.isoformat() for entry in all_entries if entry not in counts.index]
    payload = {
        "checked_at_utc": iso_now(), "stage": args.stage, "status": "PASS" if status else "FAIL",
        "checkpoint_digest": checkpoint["content_digest"], "source_overlap": metadata,
        "required_daily_range_inclusive": [required_start.isoformat(), required_end.isoformat()],
        "decision_input_availability": {
            "minimum_rankable_on_action_weeks": int(counts.min()), "maximum_rankable": int(counts.max()),
            "global_no_action_dates": missing_weeks,
        },
        "symbols": per_symbol, "parent_data_quality_sha256": sha256_file(parent_path),
        "rule": "No interpolation. Exact Saturday feature cutoff, full Sunday gap, Monday action; incomplete 547d or fewer than 20 targets is NO_ACTION.",
    }
    write_json(HERE / f"data_quality_{args.stage}.json", payload, digest=True)
    print(json.dumps({"stage": args.stage, "status": payload["status"], "panel_weeks": int(len(counts)), "minimum_rankable": int(counts.min())}))


def ranks(frame: pd.DataFrame, column: str, ascending: bool) -> pd.Series:
    ordered = frame.sort_values([column, "symbol"], ascending=[ascending, True])
    values = pd.Series(np.arange(1, len(ordered) + 1), index=ordered.index, dtype="int64")
    return values.reindex(frame.index)


def select_variant(panel: pd.DataFrame, variant: str) -> dict[pd.Timestamp, pd.DataFrame]:
    output: dict[pd.Timestamp, pd.DataFrame] = {}
    mapping = {
        "main": ("ptv52", True), "ptv26": ("ptv26", True), "ptv78": ("ptv78", True),
        "ptv52_zero": ("ptv52_zero", True), "low_mom52": ("mom52", True),
        "low_skew52": ("skew52", True), "high_vol52": ("vol52", False),
    }
    for entry, raw in panel.groupby("entry_time", sort=True):
        week = raw.copy()
        count = int(math.ceil(len(week) * float(CONFIG["top_fraction"])))
        if variant in mapping:
            column, ascending = mapping[variant]
            rank = ranks(week, column, ascending)
            selected = week[rank <= count].copy()
            selected["selection_rank"] = rank.loc[selected.index]
            selected["selection_score"] = selected[column]
        elif variant in {"scheduled_long", "market_long"}:
            selected = week.copy()
            selected["selection_rank"] = np.nan
            selected["selection_score"] = selected["ptv52"]
        else:
            raise ValueError(variant)
        output[pd.Timestamp(entry)] = selected.sort_values("symbol")
    return output


def make_trades(selections: dict[pd.Timestamp, pd.DataFrame], funding: dict[str, pd.DataFrame], stage: str, variant: str, *, cooldown: bool = True) -> tuple[pd.DataFrame, dict[str, int]]:
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
            stress_funding = -float((quantity * rates["markPrice"] * rates["fundingRate"].map(q21.adjusted_long_funding_rate)).sum())
            rows.append({
                "trade_id": f"{stage}-{variant}-{entry:%Y%m%d}-{symbol}", "strategy_variant": variant,
                "entry_time": entry, "exit_time": exit_time, "signal_cutoff": item["signal_cutoff"],
                "symbol": symbol, "category": SYMBOL_TO_CATEGORY[symbol], "eligible_count": int(item["eligible_count"]),
                "ptv26": float(item["ptv26"]), "ptv52": float(item["ptv52"]), "ptv78": float(item["ptv78"]),
                "ptv52_zero": float(item["ptv52_zero"]), "mom52": float(item["mom52"]),
                "skew52": float(item["skew52"]), "vol52": float(item["vol52"]),
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
    return pd.DataFrame(rows), {"planned": planned, "excluded_missing_marks": excluded_marks, "excluded_missing_funding": excluded_funding, "cooldown_skips": cooldown_skips}


def summarize(trades: pd.DataFrame, stage: str) -> dict[str, Any]:
    result = q21.summarize(trades, stage)
    result["by_year"] = {}
    dates = q21.q20.date_returns(trades, "base_net_return") - q21.q20.hurdle_per_week()
    for year, values in dates.groupby(dates.index.year):
        result["by_year"][str(year)] = {"dates": int(len(values)), "mean_after_hurdle": float(values.mean())}
    return result


def compare(main: pd.DataFrame, baseline: pd.DataFrame, column: str, *, cash: bool = False) -> dict[str, Any]:
    return q21.compare(main, baseline, column, baseline_no_action_as_cash=cash)


def compare_simple_envelope(main: pd.DataFrame, baselines: list[pd.DataFrame]) -> dict[str, Any]:
    left = q21.q20.date_returns(main, "base_net_return")
    candidates = [q21.q20.date_returns(frame, "base_net_return").reindex(left.index).fillna(0.0) for frame in baselines]
    envelope = pd.concat(candidates, axis=1).max(axis=1)
    difference = left - envelope
    return {
        "main_mean": float(left.mean()), "envelope_mean": float(envelope.mean()),
        "difference_mean": float(difference.mean()),
        "difference_bootstrap_95pct": q21.q20.block_bootstrap_mean_ci(difference.to_numpy(float)),
        "positive_date_fraction": float((difference > 0).mean()),
    }


def command_self_test(_args: argparse.Namespace) -> None:
    symmetric = np.array([-0.04, -0.02, -0.01, 0.01, 0.02, 0.04])
    shifted = symmetric + 0.01
    if not prospect_value(shifted) > prospect_value(symmetric):
        raise RuntimeError("PTV monotonicity mismatch")
    if not math.isclose(probability_weight(0.0, 0.61), 0.0) or not math.isclose(probability_weight(1.0, 0.61), 1.0):
        raise RuntimeError("probability weight boundary mismatch")
    sample = pd.DataFrame([{"trade_id": "test", "entry_price": 100.0, "exit_price": 110.0, "quantity_per_unit_plan_capital": 0.0025}])
    vector = float(q21.q20.vectorbt_long_returns(sample, 0.0006, 0.0010)[0])
    manual = float(q21.q20.manual_long_return(sample.iloc[0], 0.0006, 0.0010))
    if not math.isclose(vector, manual, rel_tol=0.0, abs_tol=1e-12):
        raise RuntimeError("VectorBT/manual mismatch")
    print(json.dumps({"status": "PASS", "ptv_symmetric": prospect_value(symmetric), "ptv_shifted": prospect_value(shifted), "vectorbt_manual_reconciliation": vector - manual}))


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
        raw, opportunity_counts[name] = make_trades(selections[name], funding, args.stage, name, cooldown=name != "market_long")
        trades[name] = q21.attach_returns(raw)
    csv_hashes: dict[str, str] = {}
    for name, frame in trades.items():
        path = HERE / f"{args.stage}_{name}_trades.csv"
        frame.to_csv(path, index=False, date_format="%Y-%m-%dT%H:%M:%S%z")
        csv_hashes[path.name] = sha256_file(path)
    summaries = {name: summarize(frame, args.stage) for name, frame in trades.items()}
    simple_names = ["low_mom52", "low_skew52", "high_vol52"]
    payload = {
        "analyzed_at_utc": iso_now(), "stage": args.stage, "checkpoint_digest": checkpoint["content_digest"],
        "data_quality_digest": read_json(dq_path)["content_digest"],
        "panel_rows": int(len(panel)), "panel_weeks": int(panel["entry_time"].nunique()),
        "opportunity_counts": opportunity_counts, "summaries": summaries,
        "comparisons": {
            **{f"base_vs_{name}": compare(trades["main"], trades[name], "base_net_return", cash=True) for name in simple_names},
            "base_vs_best_simple_envelope": compare_simple_envelope(trades["main"], [trades[name] for name in simple_names]),
            "gross_vs_market_long": compare(trades["main"], trades["market_long"], "gross_long_return"),
            "base_vs_scheduled_long": compare(trades["main"], trades["scheduled_long"], "base_net_return", cash=True),
            "weekly_feature_spearman": {
                column: float(panel.groupby("entry_time").apply(lambda frame, c=column: frame["ptv52"].corr(frame[c], method="spearman"), include_groups=False).median())
                for column in ("mom52", "skew52", "vol52")
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
        "simple_envelope_increment": payload["comparisons"]["base_vs_best_simple_envelope"]["difference_mean"],
        "digest": evidence["content_digest"],
    }))


def gate_checks(evidence: dict[str, Any]) -> tuple[dict[str, bool], dict[str, Any]]:
    main = evidence["summaries"]["main"]
    base, stress = main["scenarios"]["base"], main["scenarios"]["stress"]
    counts = evidence["opportunity_counts"]["main"]
    excluded = counts["excluded_missing_marks"] + counts["excluded_missing_funding"]
    excluded_fraction = float(excluded / counts["planned"]) if counts["planned"] else 1.0
    minimum = {"development": {"trades": 100, "dates": 40, "symbols": 18, "half": 15}, "evaluation": {"trades": 50, "dates": 20, "symbols": 15, "half": 8}}[evidence["stage"]]
    neighbors = [evidence["summaries"][name]["scenarios"]["stress"]["date_mean_after_hurdle"] for name in ("ptv26", "ptv78", "ptv52_zero")]
    positive_categories = sum(item["base_mean_after_hurdle"] > 0 for item in main["by_category"].values())
    simple = [evidence["comparisons"][f"base_vs_{name}"] for name in ("low_mom52", "low_skew52", "high_vol52")]
    envelope = evidence["comparisons"]["base_vs_best_simple_envelope"]
    market = evidence["comparisons"]["gross_vs_market_long"]
    checks = {
        "data_quality_pass": read_json(HERE / f"data_quality_{evidence['stage']}.json")["status"] == "PASS",
        "vectorbt_reconciled": main["maximum_vectorbt_reconciliation_error"] <= 1e-10,
        "excluded_trade_fraction_at_most_2pct": excluded_fraction <= float(CONFIG["max_excluded_trade_fraction"]),
        "minimum_trades": main["trades"] >= minimum["trades"], "minimum_entry_dates": main["entry_dates"] >= minimum["dates"],
        "minimum_symbols": main["symbols"] >= minimum["symbols"],
        "each_half_minimum_dates": all(item["dates"] >= minimum["half"] for item in main["by_half"].values()),
        "base_after_hurdle_positive": base["date_mean_after_hurdle"] > 0,
        "stress_after_hurdle_positive": stress["date_mean_after_hurdle"] > 0,
        "stress_bootstrap_lower_positive": stress["date_mean_after_hurdle_bootstrap_95pct"][0] > 0,
        "both_halves_positive": all(item["mean_after_hurdle"] > 0 for item in main["by_half"].values()),
        "all_years_positive": all(item["mean_after_hurdle"] > 0 for item in main["by_year"].values()),
        "beats_each_simple_mean": all(item["difference_mean"] > 0 for item in simple),
        "beats_simple_envelope_bootstrap_lower_positive": envelope["difference_mean"] > 0 and envelope["difference_bootstrap_95pct"][0] > 0,
        "gross_excess_vs_market_positive": market["difference_mean"] > 0,
        "gross_excess_vs_market_bootstrap_lower_positive": market["difference_bootstrap_95pct"][0] > 0,
        "two_of_three_neighbors_stress_positive": sum(value > 0 for value in neighbors) >= 2,
        "four_positive_categories": positive_categories >= 4,
        "half_targets_positive": main["positive_target_fraction_at_least_two_trades"] >= 0.50,
        "largest_positive_pnl_share_at_most_25pct": main["largest_positive_pnl_share"] <= 0.25,
        "date_drawdown_above_minus_20pct": base["date_portfolio_max_drawdown"] > -0.20,
        "worst_target_drawdown_above_minus_30pct": main["worst_symbol_base_max_drawdown"] > -0.30,
    }
    return checks, {"excluded_trade_fraction": excluded_fraction, "neighbor_stress_after_hurdle": neighbors, "positive_categories": positive_categories}


def conclusion_for_failure(evidence: dict[str, Any]) -> str:
    main = evidence["summaries"]["main"]
    economic = (
        main["scenarios"]["base"]["date_mean_after_hurdle"] > 0
        and main["scenarios"]["stress"]["date_mean_after_hurdle"] > 0
        and evidence["comparisons"]["base_vs_best_simple_envelope"]["difference_mean"] > 0
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
    gate = {"generated_at_utc": iso_now(), "stage": args.stage, "status": status, "checks": checks, "failed_checks": [key for key, value in checks.items() if not value], "diagnostics": diagnostics, "evidence_digest": evidence["content_digest"]}
    write_json(HERE / f"{args.stage}_gate.json", gate, digest=True)
    if status == "FAIL":
        write_json(HERE / "results.json", {
            "generated_at_utc": iso_now(), "conclusion": conclusion_for_failure(evidence), "stopped_after": args.stage,
            "gate_status": status, "failed_checks": gate["failed_checks"], "main": evidence["summaries"]["main"],
            "comparisons": evidence["comparisons"], "diagnostics": {name: evidence["summaries"][name] for name in CONFIG["diagnostics"]},
            "later_stages": "NOT_OPENED_BY_SEQUENTIAL_GATE", "handoff": "NOT_GENERATED", "product_effects": "NONE",
        }, digest=True)
    elif args.stage == "evaluation":
        write_json(HERE / "results.json", {
            "generated_at_utc": iso_now(), "conclusion": "INSUFFICIENT_EVIDENCE", "stage_gates": {"development": "PASS", "evaluation": "PASS"},
            "reason": "Historical stages passed but are not checkpoint-after forward evidence and do not prove long-run profitability.",
            "forward_requirement": "At least 26 eligible frozen-rule weeks spanning two market states, then repeat unchanged gates in a separate question.",
            "handoff": "NOT_GENERATED", "product_effects": "NONE",
        }, digest=True)
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
        path = HERE / f"{stage}.json"
        if not path.exists():
            continue
        evidence = read_json(path)
        for name, expected in evidence["trade_csv_sha256"].items():
            trade_path = HERE / name
            if not trade_path.exists() or sha256_file(trade_path) != expected:
                raise RuntimeError(f"trade CSV mismatch: {name}")
            csv_files += 1
        stages.append(stage)
    conclusion = read_json(HERE / "results.json")["conclusion"] if (HERE / "results.json").exists() else "OPEN"
    print(json.dumps({"status": "PASS", "checkpoint": checkpoint["content_digest"], "opened_stages": stages, "verified_json_digests": verified_json, "verified_trade_csvs": csv_files, "conclusion": conclusion}))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prospect-theory-value weekly single-target LONG study")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("checkpoint").set_defaults(func=command_checkpoint)
    sub.add_parser("self-test").set_defaults(func=command_self_test)
    prepare = sub.add_parser("prepare"); prepare.add_argument("--stage", choices=tuple(STAGES), required=True); prepare.set_defaults(func=command_prepare)
    analyze = sub.add_parser("analyze"); analyze.add_argument("--stage", choices=tuple(STAGES), required=True); analyze.set_defaults(func=command_analyze)
    gate = sub.add_parser("gate"); gate.add_argument("--stage", choices=tuple(STAGES), required=True); gate.set_defaults(func=command_gate)
    sub.add_parser("validate").set_defaults(func=command_validate)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
