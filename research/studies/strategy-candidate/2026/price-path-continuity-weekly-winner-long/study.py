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
from scipy.stats import rankdata
import vectorbt as vbt


HERE = Path(__file__).resolve().parent
Q18_DIR = HERE.parent / "high-volatility-ten-week-loser-weekly-one-shot-long"
Q18_STUDY = Q18_DIR / "study.py"
PPC_PDF = Path(
    "D:/projects/Codex/CodexHome/research-data/halpha/_sources/price-path-continuity-kim-2026-v2.pdf"
)


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


q18 = load_module(Q18_STUDY, "halpha_ppc_q18_adapter")
SYMBOLS = list(q18.SYMBOLS)
CATEGORY_MEMBERS = dict(q18.CATEGORY_MEMBERS)
SYMBOL_TO_CATEGORY = dict(q18.SYMBOL_TO_CATEGORY)
UNIVERSE_PATH = q18.UNIVERSE_PATH
UNIVERSE_SHA256 = q18.UNIVERSE_SHA256
STAGES = {
    "development": ("2024-01-01T00:00:00Z", "2024-12-30T00:00:00Z"),
    "evaluation": ("2025-01-06T00:00:00Z", "2025-12-29T00:00:00Z"),
}
CONFIG = {
    "strategy_id": "RESEARCH_PPC14_TOP_TERCILE_MOM14_TOP_TERCILE_WEEKLY_LONG_0P25X_V1",
    "direction": "LONG_ONLY",
    "formation_days": 14,
    "hold_days": 7,
    "gap_full_days": 1,
    "top_fraction": 1.0 / 3.0,
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
        "mom14", "ppc14", "formation7", "formation21", "inverse_max_share",
        "directional_smoothness", "scheduled_long", "market_long",
    ],
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
        (Q18_STUDY, "reused frozen public-data stitching and source adapter"),
        (Q18_DIR / "checkpoint.json", "frozen target, category, stage and adapter identity"),
        (q18.PARENT_STUDY, "reused funding/cost/statistics reference"),
        (q18.DATA_ENGINE, "official Binance public archive loader/fetcher"),
        (UNIVERSE_PATH, "frozen current target universe"),
        (q18.DEV_SOURCE / "source_manifest_development.json", "2024 public input manifest"),
        (q18.DEV_SOURCE / "data_quality_development.json", "2024 parent data quality"),
        (q18.EVAL_SOURCE / "source_manifest_evaluation.json", "2025 public input manifest"),
        (q18.EVAL_SOURCE / "data_quality_evaluation.json", "2025 parent data quality"),
        (PPC_PDF, "Kim 2026 PPC primary working paper; not a market input"),
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
            "Does a fixed configured liquid Binance USD-M target qualify a weekly 0.25x LONG only when its "
            "lagged 14-day return and rank-weighted price-path continuity are both in the cross-sectional top "
            "tercile, after a full-day gap, retail costs, funding, hurdle, simple baselines, robustness, breadth "
            "and sequential 2024-2025 evidence?"
        ),
        "known_exposure": (
            "Kim 2026 selected and tested PPC on a broad 2020-April-2026 crypto sample, and Halpha has viewed "
            "the underlying 2024-2025 market paths in other questions. Exact target-plan outputs remain unviewed, "
            "so sequencing prevents adaptation but cannot create post-publication market evidence."
        ),
        "support_limit": (
            "Even if both historical stages pass, the current conclusion is capped at INSUFFICIENT_EVIDENCE. "
            "At least 26 eligible frozen-rule weeks spanning two market states must accrue after this checkpoint "
            "and pass unchanged gates before a separate question can consider product handoff."
        ),
        "family_stop_rule": (
            "On failure, close this fixed PPC-conditioned long conversion; do not search nearby terciles, "
            "lookbacks, gaps, holds, symbols, categories, costs, states or directions without genuinely new "
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
        "allowed_after_checkpoint": (
            "Only deterministic stage artifacts and documented implementation-only amendments that preserve "
            "the economic rule; no market endpoint requiring credentials and no product/runtime change."
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
    if checkpoint.get("configuration") != CONFIG or checkpoint.get("stages") != {
        key: list(value) for key, value in STAGES.items()
    }:
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


def prior_stage(stage: str) -> str | None:
    return "development" if stage == "evaluation" else None


def stage_authorized(stage: str) -> None:
    prior = prior_stage(stage)
    if prior is None:
        return
    path = HERE / f"{prior}_gate.json"
    if not path.exists() or read_json(path).get("status") != "PASS":
        raise RuntimeError(f"{stage} sealed until {prior} PASS")


def load_stage(stage: str) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame], dict[str, Any]]:
    if stage not in STAGES:
        raise ValueError(stage)
    return q18.load_stage(stage)


def stage_entries(stage: str) -> pd.DatetimeIndex:
    start, end = map(pd.Timestamp, STAGES[stage])
    return pd.date_range(start, end, freq="W-MON", inclusive="left")


def rank_weighted_ppc(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    if len(values) == 0 or not np.isfinite(values).all():
        return math.nan
    past = float(np.prod(1.0 + values) - 1.0)
    absolute_sum = float(np.abs(values).sum())
    if past == 0.0 or absolute_sum == 0.0:
        return 0.0
    ranks = rankdata(np.abs(values), method="average")
    weights = len(values) + 1.0 - ranks
    return float(np.sign(past) * np.sum(np.sign(values) * weights) / np.sum(weights))


def inverse_max_share(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    total = float(np.abs(values).sum())
    return math.nan if total == 0.0 or not np.isfinite(total) else float(1.0 - np.abs(values).max() / total)


def directional_smoothness(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    if not np.isfinite(values).all() or np.any(values <= -1.0):
        return math.nan
    logs = np.log1p(values)
    absolute = np.abs(logs)
    distance = float(absolute.sum())
    raw_abs = np.abs(values)
    raw_sum = float(raw_abs.sum())
    if distance == 0.0 or raw_sum == 0.0:
        return 0.0
    efficiency = float(abs(logs.sum()) / distance)
    hhi = float(np.square(raw_abs).sum() / (raw_sum * raw_sum))
    n = len(values)
    smoothness = float(1.0 - (hhi - 1.0 / n) / (1.0 - 1.0 / n))
    return efficiency * smoothness


def feature_frame(frame: pd.DataFrame) -> pd.DataFrame:
    calendar = pd.date_range(frame.index.min(), frame.index.max(), freq="1D")
    frame = frame.reindex(calendar)
    output = pd.DataFrame(index=frame.index)
    daily_return = frame["close"].pct_change(fill_method=None)
    for days in (7, 14, 21):
        output[f"past{days}"] = frame["close"] / frame["close"].shift(days) - 1.0
        output[f"ppc{days}"] = daily_return.rolling(days, min_periods=days).apply(rank_weighted_ppc, raw=True)
    output["inverse_max_share14"] = daily_return.rolling(14, min_periods=14).apply(inverse_max_share, raw=True)
    output["directional_smoothness14"] = daily_return.rolling(14, min_periods=14).apply(
        directional_smoothness, raw=True
    )
    output["median_quote_volume_30d"] = frame["quote_volume"].rolling(30, min_periods=30).median()
    required = frame[["open", "high", "low", "close", "quote_volume"]].notna().all(axis=1)
    output["complete_45d"] = required.rolling(45, min_periods=45).sum().eq(45)
    return output.replace([np.inf, -np.inf], np.nan)


def command_prepare(args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    stage_authorized(args.stage)
    bars, funding, metadata = load_stage(args.stage)
    parent_path = (
        q18.DEV_SOURCE / "data_quality_development.json"
        if args.stage == "development" else q18.EVAL_SOURCE / "data_quality_evaluation.json"
    )
    parent_quality = read_json(parent_path)
    status = parent_quality.get("status") == "PASS" and metadata.get("overlap_mismatch_rows", 0) == 0
    entries = stage_entries(args.stage)
    first_cutoff = entries[0] - pd.Timedelta(days=2)
    required_start = first_cutoff - pd.Timedelta(days=44)
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
            if values is not None and bool(values["complete_45d"]) and pd.notna(values["past14"]) and pd.notna(values["ppc14"]):
                if float(values["median_quote_volume_30d"]) >= float(CONFIG["minimum_median_quote_volume_30d"]):
                    count += 1
        counts[entry.isoformat()] = count
    below = {key: value for key, value in counts.items() if value < int(CONFIG["minimum_rankable_symbols"])}
    manifest_path = (
        q18.DEV_SOURCE / "source_manifest_development.json"
        if args.stage == "development" else q18.EVAL_SOURCE / "source_manifest_evaluation.json"
    )
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
        "source_manifest_sha256": sha256_file(manifest_path),
        "rule": (
            "Calendar gaps are never imputed. PPC inputs end with the Saturday bar, the Sunday bar is a full-day "
            "gap, and Monday open is the first action. A target with incomplete 45d inputs or median 30d quote "
            "volume below 10m is NO_ACTION; a decision with fewer than 20 remaining targets is global NO_ACTION "
            "for that week and does not invalidate otherwise intact source data."
        ),
    }
    write_json(HERE / f"data_quality_{args.stage}.json", payload, digest=True)
    print(json.dumps({"stage": args.stage, "status": payload["status"], "minimum_rankable": min(counts.values())}))


def build_panel(bars: dict[str, pd.DataFrame], stage: str) -> pd.DataFrame:
    features = {symbol: feature_frame(frame) for symbol, frame in bars.items()}
    rows: list[dict[str, Any]] = []
    columns = [
        "past7", "ppc7", "past14", "ppc14", "past21", "ppc21",
        "inverse_max_share14", "directional_smoothness14", "median_quote_volume_30d", "complete_45d",
    ]
    for entry in stage_entries(stage):
        cutoff, exit_time = entry - pd.Timedelta(days=2), entry + pd.Timedelta(days=7)
        candidates: list[dict[str, Any]] = []
        for symbol in SYMBOLS:
            if cutoff not in features[symbol].index or entry not in bars[symbol].index or exit_time not in bars[symbol].index:
                continue
            values = features[symbol].loc[cutoff, columns]
            numeric = values.drop(labels=["complete_45d"])
            if (
                numeric.isna().any() or not bool(values["complete_45d"])
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
        if variant in {"main", "formation7", "formation21", "inverse_max_share", "directional_smoothness"}:
            days = 7 if variant == "formation7" else 21 if variant == "formation21" else 14
            past_column = f"past{days}"
            continuity_column = {
                "inverse_max_share": "inverse_max_share14",
                "directional_smoothness": "directional_smoothness14",
            }.get(variant, f"ppc{days}")
            past_rank = top_ranks(week, past_column)
            continuity_rank = top_ranks(week, continuity_column)
            selected = week[(past_rank <= count) & (continuity_rank <= count) & (week[past_column] > 0)].copy()
            selected["past_rank"] = past_rank.loc[selected.index]
            selected["continuity_rank"] = continuity_rank.loc[selected.index]
            selected["selection_past"] = selected[past_column]
            selected["selection_continuity"] = selected[continuity_column]
        elif variant == "mom14":
            rank = top_ranks(week, "past14")
            selected = week[(rank <= count) & (week["past14"] > 0)].copy()
            selected["past_rank"] = rank.loc[selected.index]
            selected["continuity_rank"] = np.nan
            selected["selection_past"] = selected["past14"]
            selected["selection_continuity"] = np.nan
        elif variant == "ppc14":
            rank = top_ranks(week, "ppc14")
            selected = week[rank <= count].copy()
            selected["past_rank"] = np.nan
            selected["continuity_rank"] = rank.loc[selected.index]
            selected["selection_past"] = selected["past14"]
            selected["selection_continuity"] = selected["ppc14"]
        elif variant in {"scheduled_long", "market_long"}:
            selected = week.copy()
            selected["past_rank"] = np.nan
            selected["continuity_rank"] = np.nan
            selected["selection_past"] = selected["past14"]
            selected["selection_continuity"] = selected["ppc14"]
        else:
            raise ValueError(variant)
        output[pd.Timestamp(entry)] = selected.sort_values("symbol")
    return output


def adjusted_long_funding_rate(rate: float) -> float:
    if rate > 0:
        return rate * float(CONFIG["long_funding_stress"]["positive_cost_multiplier"])
    return rate * float(CONFIG["long_funding_stress"]["negative_benefit_multiplier"])


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
                "past14": float(item["past14"]), "ppc14": float(item["ppc14"]),
                "selection_past": float(item["selection_past"]),
                "selection_continuity": float(item["selection_continuity"]) if pd.notna(item["selection_continuity"]) else np.nan,
                "past_rank": float(item["past_rank"]) if pd.notna(item["past_rank"]) else np.nan,
                "continuity_rank": float(item["continuity_rank"]) if pd.notna(item["continuity_rank"]) else np.nan,
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


def vectorbt_long_returns(trades: pd.DataFrame, fee: float, slippage: float) -> np.ndarray:
    columns = trades["trade_id"].tolist()
    prices = pd.DataFrame(
        [trades["entry_price"].to_numpy(float), trades["exit_price"].to_numpy(float)], columns=columns,
    )
    quantity = trades["quantity_per_unit_plan_capital"].to_numpy(float)
    sizes = pd.DataFrame([quantity, -quantity], columns=columns)
    portfolio = vbt.Portfolio.from_orders(
        prices, size=sizes, size_type="amount", direction="both", fees=fee,
        slippage=slippage, init_cash=1.0, freq="1D",
    )
    return portfolio.total_return().reindex(columns).to_numpy(float)


def manual_long_return(row: pd.Series, fee: float, slippage: float) -> float:
    quantity = float(row["quantity_per_unit_plan_capital"])
    entry_execution = float(row["entry_price"]) * (1.0 + slippage)
    exit_execution = float(row["exit_price"]) * (1.0 - slippage)
    return (
        quantity * (exit_execution - entry_execution)
        - quantity * entry_execution * fee - quantity * exit_execution * fee
    )


def attach_returns(trades: pd.DataFrame) -> pd.DataFrame:
    output = trades.copy()
    for scenario, assumptions in CONFIG["costs"].items():
        fee, slippage = float(assumptions["fee_per_side"]), float(assumptions["slippage_per_side"])
        vector = vectorbt_long_returns(output, fee, slippage)
        manual = output.apply(manual_long_return, axis=1, fee=fee, slippage=slippage).to_numpy(float)
        output[f"{scenario}_price_cost_return"] = vector
        output[f"{scenario}_reconciliation_error"] = vector - manual
        funding_column = "stress_funding_return" if assumptions["funding_stress"] else "actual_funding_return"
        output[f"{scenario}_net_return"] = vector + output[funding_column].to_numpy(float)
    return output


def date_returns(trades: pd.DataFrame, column: str) -> pd.Series:
    return trades.groupby("entry_time")[column].mean().sort_index()


def hurdle_per_week() -> float:
    return float(CONFIG["annual_capital_hurdle"]) * float(CONFIG["hold_days"]) / 365.0


def block_bootstrap_mean_ci(values: np.ndarray) -> list[float]:
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        raise RuntimeError("bootstrap input empty")
    block, reps = int(CONFIG["bootstrap"]["block_weeks"]), int(CONFIG["bootstrap"]["repetitions"])
    rng = np.random.default_rng(int(CONFIG["bootstrap"]["seed"]))
    means = np.empty(reps)
    for index in range(reps):
        chosen: list[int] = []
        while len(chosen) < len(values):
            start = int(rng.integers(0, len(values)))
            chosen.extend(((start + np.arange(block)) % len(values)).tolist())
        means[index] = float(values[np.asarray(chosen[:len(values)])].mean())
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))]


def max_drawdown(returns: pd.Series) -> float:
    equity = (1.0 + returns).cumprod()
    prior_peak = pd.concat([pd.Series([1.0]), equity.reset_index(drop=True)]).cummax().iloc[1:].to_numpy()
    return float(np.min(equity.to_numpy() / prior_peak - 1.0))


def summarize(trades: pd.DataFrame, stage: str) -> dict[str, Any]:
    start, end = map(pd.Timestamp, STAGES[stage])
    result: dict[str, Any] = {
        "trades": int(len(trades)), "entry_dates": int(trades["entry_time"].nunique()),
        "symbols": int(trades["symbol"].nunique()), "funding_events": int(trades["funding_events"].sum()),
        "maximum_vectorbt_reconciliation_error": float(max(
            trades[f"{name}_reconciliation_error"].abs().max() for name in CONFIG["costs"]
        )),
        "scenarios": {}, "by_half": {}, "by_symbol": {}, "by_category": {},
    }
    for scenario in CONFIG["costs"]:
        dates = date_returns(trades, f"{scenario}_net_return")
        adjusted = dates - hurdle_per_week()
        total = float(np.prod(1.0 + dates.to_numpy(float)) - 1.0)
        result["scenarios"][scenario] = {
            "date_mean": float(dates.mean()), "date_mean_after_hurdle": float(adjusted.mean()),
            "date_mean_after_hurdle_bootstrap_95pct": block_bootstrap_mean_ci(adjusted.to_numpy(float)),
            "compound_return": total,
            "annualized_return": float((1.0 + total) ** (365.0 / (end - start).days) - 1.0),
            "date_portfolio_max_drawdown": max_drawdown(dates),
        }
    base_adjusted = date_returns(trades, "base_net_return") - hurdle_per_week()
    midpoint = start + (end - start) / 2
    for label, mask in (("H1", base_adjusted.index < midpoint), ("H2", base_adjusted.index >= midpoint)):
        values = base_adjusted[mask]
        result["by_half"][label] = {"dates": int(len(values)), "mean_after_hurdle": float(values.mean())}
    target_drawdowns: dict[str, float] = {}
    target_positive: list[bool] = []
    for symbol, group in trades.groupby("symbol"):
        ordered = group.sort_values("entry_time")
        adjusted = ordered["base_net_return"] - hurdle_per_week()
        target_drawdowns[str(symbol)] = max_drawdown(ordered["base_net_return"])
        result["by_symbol"][str(symbol)] = {
            "trades": int(len(group)), "base_mean_after_hurdle": float(adjusted.mean()),
            "base_max_drawdown": target_drawdowns[str(symbol)],
        }
        if len(group) >= 2:
            target_positive.append(float(adjusted.mean()) > 0.0)
    result["positive_target_fraction_at_least_two_trades"] = float(np.mean(target_positive)) if target_positive else 0.0
    result["worst_symbol_base_max_drawdown"] = float(min(target_drawdowns.values()))
    pnl = trades.groupby("symbol")["base_net_return"].sum()
    positive = pnl.clip(lower=0.0)
    result["largest_positive_pnl_share"] = float(positive.max() / positive.sum()) if positive.sum() > 0 else 1.0
    for category, members in CATEGORY_MEMBERS.items():
        subset = trades[trades["symbol"].isin(members)]
        if not subset.empty:
            result["by_category"][category] = {
                "trades": int(len(subset)),
                "base_mean_after_hurdle": float((subset["base_net_return"] - hurdle_per_week()).mean()),
            }
    return result


def compare(
    main: pd.DataFrame, baseline: pd.DataFrame, column: str, *, baseline_no_action_as_cash: bool = False,
) -> dict[str, Any]:
    left = date_returns(main, column)
    raw_right = date_returns(baseline, column)
    right = raw_right.reindex(left.index)
    missing_dates = int(right.isna().sum())
    if baseline_no_action_as_cash:
        right = right.fillna(0.0)
    if right.isna().any():
        raise RuntimeError("baseline missing a main entry date")
    difference = left - right
    return {
        "main_mean": float(left.mean()), "baseline_mean": float(right.mean()),
        "difference_mean": float(difference.mean()),
        "difference_bootstrap_95pct": block_bootstrap_mean_ci(difference.to_numpy(float)),
        "positive_date_fraction": float((difference > 0).mean()),
        "baseline_no_action_dates_filled_as_cash": missing_dates if baseline_no_action_as_cash else 0,
    }


def command_self_test(_args: argparse.Namespace) -> None:
    continuous_up = np.full(14, 0.01)
    continuous_down = np.full(14, -0.01)
    jumpy = np.array([-0.002] * 13 + [0.08])
    if not math.isclose(rank_weighted_ppc(continuous_up), 1.0, abs_tol=1e-14):
        raise RuntimeError("continuous up PPC mismatch")
    if not math.isclose(rank_weighted_ppc(continuous_down), 1.0, abs_tol=1e-14):
        raise RuntimeError("continuous down orientation mismatch")
    if not rank_weighted_ppc(jumpy) < rank_weighted_ppc(continuous_up):
        raise RuntimeError("jumpy path should have lower PPC")
    sample = pd.DataFrame([{
        "trade_id": "test", "entry_price": 100.0, "exit_price": 110.0,
        "quantity_per_unit_plan_capital": 0.0025,
    }])
    vector = float(vectorbt_long_returns(sample, 0.0006, 0.0010)[0])
    manual = float(manual_long_return(sample.iloc[0], 0.0006, 0.0010))
    if not math.isclose(vector, manual, rel_tol=0.0, abs_tol=1e-12):
        raise RuntimeError("VectorBT/manual mismatch")
    if adjusted_long_funding_rate(0.001) != 0.0015 or adjusted_long_funding_rate(-0.001) != -0.0005:
        raise RuntimeError("funding stress direction mismatch")
    print(json.dumps({
        "status": "PASS", "continuous_up_ppc": rank_weighted_ppc(continuous_up),
        "continuous_down_ppc": rank_weighted_ppc(continuous_down), "jumpy_ppc": rank_weighted_ppc(jumpy),
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
        float(week["past14"].corr(week["ppc14"], method="spearman"))
        for _, week in panel.groupby("entry_time", sort=True)
    ]
    payload = {
        "analyzed_at_utc": iso_now(), "stage": args.stage,
        "checkpoint_digest": checkpoint["content_digest"],
        "data_quality_digest": read_json(dq_path)["content_digest"],
        "panel_rows": int(len(panel)), "panel_weeks": int(panel["entry_time"].nunique()),
        "opportunity_counts": opportunity_counts, "summaries": summaries,
        "comparisons": {
            "base_vs_mom14": compare(trades["main"], trades["mom14"], "base_net_return"),
            "stress_vs_mom14": compare(trades["main"], trades["mom14"], "stress_net_return"),
            "gross_vs_market_long": compare(trades["main"], trades["market_long"], "gross_long_return"),
            "base_vs_scheduled_long": compare(
                trades["main"], trades["scheduled_long"], "base_net_return", baseline_no_action_as_cash=True,
            ),
            "past14_vs_ppc14_weekly_spearman": {
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
        "base_vs_mom14": payload["comparisons"]["base_vs_mom14"]["difference_mean"],
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
        for name in ("formation7", "formation21", "inverse_max_share", "directional_smoothness")
    ]
    positive_categories = sum(
        item["base_mean_after_hurdle"] > 0 for item in main["by_category"].values()
    )
    mom = evidence["comparisons"]["base_vs_mom14"]
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
        "base_increment_vs_mom14_positive": mom["difference_mean"] > 0,
        "base_increment_vs_mom14_bootstrap_lower_positive": mom["difference_bootstrap_95pct"][0] > 0,
        "gross_excess_vs_market_positive": market["difference_mean"] > 0,
        "gross_excess_vs_market_bootstrap_lower_positive": market["difference_bootstrap_95pct"][0] > 0,
        "three_of_four_neighbors_stress_positive": sum(value > 0 for value in neighbors) >= 3,
        "four_positive_categories": positive_categories >= 4,
        "half_targets_positive": main["positive_target_fraction_at_least_two_trades"] >= 0.50,
        "largest_positive_pnl_share_at_most_25pct": main["largest_positive_pnl_share"] <= 0.25,
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
        and evidence["comparisons"]["base_vs_mom14"]["difference_mean"] > 0
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
                "Both exact-rule historical stages passed, but Kim 2026 selected PPC using a sample that includes "
                "both periods and Halpha had already exposed the underlying paths. This is not enough independent "
                "forward evidence for product qualification or a long-run profitability claim."
            ),
            "forward_requirement": (
                "Keep the rule frozen for at least 26 eligible weeks spanning two market states, then repeat the "
                "same costs, MOM14 and market baselines, robustness, breadth and risk gates in a separate question."
            ),
            "handoff": "NOT_GENERATED", "product_effects": "NONE",
        }
        write_json(HERE / "results.json", terminal, digest=True)
    print(json.dumps({"stage": args.stage, "status": status, "failed": gate["failed_checks"]}))


def command_validate(_args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    json_files = sorted(HERE.glob("*.json"))
    verified_json = 0
    for path in json_files:
        item = read_json(path)
        if "content_digest" in item:
            if canonical_digest(item) != item["content_digest"]:
                raise RuntimeError(f"JSON digest mismatch: {path.name}")
            verified_json += 1
    stages = []
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
    parser = argparse.ArgumentParser(description="PPC-conditioned weekly winner single-target LONG study")
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
