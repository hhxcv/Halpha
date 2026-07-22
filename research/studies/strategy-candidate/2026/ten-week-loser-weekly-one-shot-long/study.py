from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import vectorbt as vbt


HERE = Path(__file__).resolve().parent
RESEARCH_ROOT = HERE.parents[3]
UNIVERSE_PATH = RESEARCH_ROOT / "market-universe" / "universe.csv"
UNIVERSE_SHA256 = "1f24adfb64b7a52a170b730ee7517916b2da8ab45785779dee6be991762186cc"
DATA_ENGINE = HERE.parent / "perp-low-volatility-monthly-one-shot-long" / "study.py"
DEV_SOURCE = HERE.parent / "category-momentum-gated-one-shot-long"
EVAL_SOURCE = HERE.parent / "high-volatility-monthly-one-shot-short"
CONF_SOURCE = HERE.parent / "perp-premium-momentum-daily-one-shot-long"
EXTERNAL_PDF = Path(
    "D:/projects/Codex/CodexHome/research-data/halpha/_sources/"
    "cryptocurrency-momentum-reversal-dobrynskaya-hse.pdf"
)

SYMBOLS = [
    "1000XECUSDT", "AAVEUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "CRVUSDT",
    "DASHUSDT", "ENSUSDT", "ETCUSDT", "HBARUSDT", "KAVAUSDT", "LINKUSDT",
    "LTCUSDT", "NEARUSDT", "RUNEUSDT", "SNXUSDT", "SOLUSDT", "TRXUSDT",
    "UNIUSDT", "VETUSDT", "XLMUSDT", "XMRUSDT", "XRPUSDT", "ZECUSDT", "ZILUSDT",
]
CATEGORY_MEMBERS: dict[str, list[str]] = {
    "DeFi": ["AAVEUSDT", "CRVUSDT", "KAVAUSDT", "RUNEUSDT", "SNXUSDT", "UNIUSDT"],
    "Infrastructure": ["ENSUSDT", "LINKUSDT"],
    "Layer-1": ["AVAXUSDT", "BNBUSDT", "HBARUSDT", "NEARUSDT", "SOLUSDT", "TRXUSDT", "VETUSDT"],
    "Layer-2": ["XLMUSDT"],
    "Payment": ["1000XECUSDT", "BCHUSDT", "LTCUSDT", "XRPUSDT"],
    "PoW": ["DASHUSDT", "ETCUSDT", "XMRUSDT", "ZECUSDT", "ZILUSDT"],
}
SYMBOL_TO_CATEGORY = {
    symbol: category for category, members in CATEGORY_MEMBERS.items() for symbol in members
}
STAGES = {
    "development": ("2022-02-14T00:00:00Z", "2024-01-01T00:00:00Z"),
    "evaluation": ("2024-01-01T00:00:00Z", "2024-12-30T00:00:00Z"),
    "confirmation": ("2025-01-06T00:00:00Z", "2025-12-29T00:00:00Z"),
}
SOURCE_SPECS = {
    "development": {
        "directory": DEV_SOURCE,
        "manifest_stage": "development",
        "manifest": DEV_SOURCE / "source_manifest_development.json",
        "data_quality": DEV_SOURCE / "data_quality_development.json",
        "checkpoint": DEV_SOURCE / "checkpoint.json",
    },
    "evaluation": {
        "directory": EVAL_SOURCE,
        "manifest_stage": "development",
        "manifest": EVAL_SOURCE / "source_manifest_development.json",
        "data_quality": EVAL_SOURCE / "data_quality_development.json",
        "checkpoint": EVAL_SOURCE / "checkpoint.json",
    },
    "confirmation": {
        "directory": CONF_SOURCE,
        "manifest_stage": "evaluation",
        "manifest": CONF_SOURCE / "source_manifest_evaluation.json",
        "data_quality": CONF_SOURCE / "data_quality_evaluation.json",
        "checkpoint": CONF_SOURCE / "checkpoint.json",
    },
}
CONFIG = {
    "strategy_id": "RESEARCH_MOM70_BOTTOM30_WEEKLY_ONE_SHOT_LONG_0P25X_V1",
    "direction": "LONG_ONLY",
    "hold_days": 7,
    "notional_fraction": 0.25,
    "bottom_fraction": 0.30,
    "bottom_neighbor_fraction": 0.20,
    "minimum_rankable_symbols": 20,
    "minimum_median_quote_volume_30d": 10_000_000.0,
    "annual_capital_hurdle": 0.04,
    "cooldown_full_days": 1,
    "costs": {
        "favorable": {"fee_per_side": 0.0006, "slippage_per_side": 0.0, "funding_stress": False},
        "base": {"fee_per_side": 0.0006, "slippage_per_side": 0.0010, "funding_stress": False},
        "stress": {"fee_per_side": 0.0006, "slippage_per_side": 0.0020, "funding_stress": True},
    },
    "long_funding_stress": {"positive_cost_multiplier": 1.5, "negative_benefit_multiplier": 0.5},
    "bootstrap": {"block_weeks": 4, "repetitions": 5000, "seed": 20260722},
    "main": {"lookback_days": 70, "selection": "bottom_ceil_30pct"},
    "diagnostics": [
        "mom56", "mom84", "bottom20", "mom7", "winner70", "scheduled_long", "market_long"
    ],
}
STAGE_MINIMUMS = {
    "development": {"entry_dates": 90, "trades": 300},
    "evaluation": {"entry_dates": 48, "trades": 150},
    "confirmation": {"entry_dates": 47, "trades": 145},
}
FROZEN_FILES = ["README.md", "preregistration.md", "sources.md", "study.py"]
EPHEMERAL_KEYS = {"created_at_utc", "validated_at_utc", "analyzed_at_utc", "checked_at_utc"}


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: stable_value(item)
            for key, item in sorted(value.items())
            if key not in EPHEMERAL_KEYS and key != "content_digest"
        }
    if isinstance(value, list):
        return [stable_value(item) for item in value]
    return value


def canonical_digest(value: Any) -> str:
    raw = json.dumps(
        stable_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def write_json(path: Path, value: dict[str, Any], *, digest: bool = False) -> None:
    payload = dict(value)
    if digest:
        payload["content_digest"] = canonical_digest(payload)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load research module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate_universe() -> None:
    if not UNIVERSE_PATH.exists() or sha256_file(UNIVERSE_PATH) != UNIVERSE_SHA256:
        raise RuntimeError("frozen market-universe snapshot is missing or changed")
    frame = pd.read_csv(UNIVERSE_PATH, dtype=str, keep_default_na=False)
    subset = frame[frame["symbol"].isin(SYMBOLS)]
    if set(subset["symbol"]) != set(SYMBOLS):
        raise RuntimeError("frozen market-universe does not contain all targets")
    actual = dict(zip(subset["symbol"], subset["classification_subtypes"], strict=True))
    if actual != SYMBOL_TO_CATEGORY:
        raise RuntimeError("target categories differ from the frozen universe")


def source_entries() -> list[dict[str, Any]]:
    paths: list[tuple[Path, str]] = [
        (DATA_ENGINE, "immutable public-cache loader"),
        (UNIVERSE_PATH, "frozen current universe and classification snapshot"),
    ]
    for stage, spec in SOURCE_SPECS.items():
        paths.extend([
            (spec["manifest"], f"{stage} public input manifest"),
            (spec["data_quality"], f"{stage} parent data quality"),
            (spec["checkpoint"], f"{stage} parent time and method identity"),
        ])
    entries: list[dict[str, Any]] = []
    for path, role in paths:
        if not path.exists():
            raise RuntimeError(f"missing reused source identity: {path}")
        entries.append({
            "path": str(path), "bytes": path.stat().st_size,
            "sha256": sha256_file(path), "role": role,
        })
    if not EXTERNAL_PDF.exists():
        raise RuntimeError(f"missing public paper cache: {EXTERNAL_PDF}")
    entries.append({
        "path": str(EXTERNAL_PDF), "bytes": EXTERNAL_PDF.stat().st_size,
        "sha256": sha256_file(EXTERNAL_PDF),
        "url": (
            "https://conference.hse.ru/files/download_file_ex?"
            "hash=FAE0AB2DC7A67656E89A0B1CB27D8C7D&id=3B5EE9A5-0B18-458A-9458-B4ED0F6C6664"
        ),
        "role": "public prior-art method/result identity; never a market input",
    })
    return entries


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
            "Does a paper-guided ten-week bottom-30% loser rank qualify a fixed-target 0.25x LONG / "
            "7d weekly one-shot plan after retail costs, actual funding, full-capital hurdle, simple "
            "long/market baselines, robustness, breadth, risk and sequential 2024/2025 evidence?"
        ),
        "known_exposure": (
            "Underlying 2022-2025 market paths and external papers were previously visible, but this exact "
            "MOM70 bottom-30% one-shot output was not inspected. External literature overlaps the time sample, "
            "so stages are internal exact-rule holdouts, not post-publication market evidence."
        ),
        "selection_scope": {"selectable_primary_configurations": 1, "computed_columns": 8},
        "configuration": CONFIG,
        "stages": STAGES,
        "stage_minimums": STAGE_MINIMUMS,
        "symbols": SYMBOLS,
        "categories": CATEGORY_MEMBERS,
        "universe": {"path": str(UNIVERSE_PATH), "sha256": UNIVERSE_SHA256},
        "stage_open_rule": "development -> evaluation -> confirmation; next stage requires prior PASS",
        "frozen_file_sha256": {name: sha256_file(HERE / name) for name in FROZEN_FILES},
        "source_reuse_digest": read_json(HERE / "source_reuse_manifest.json")["content_digest"],
        "environment": {
            "python": platform.python_version(), "numpy": np.__version__,
            "pandas": pd.__version__, "vectorbt": vbt.__version__,
        },
        "allowed_after_checkpoint": (
            "Append attempts and create deterministic data/result artifacts. Implementation-only fixes require "
            "a numbered amendment chain; no signal, universe, period, cost, hurdle, gate or baseline change."
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
        raise RuntimeError("checkpoint economic configuration differs from code")
    validate_universe()
    for name, expected in checkpoint["frozen_file_sha256"].items():
        actual = sha256_file(HERE / name)
        if actual == expected:
            continue
        chain = expected
        amendments = [] if name != "study.py" else sorted(HERE.glob("amendment-*.json"))
        for amendment_path in amendments:
            amendment = read_json(amendment_path)
            valid = (
                canonical_digest(amendment) == amendment.get("content_digest")
                and amendment.get("checkpoint_digest") == checkpoint["content_digest"]
                and amendment.get("original_study_sha256") == chain
                and amendment.get("economic_rule_changed") is False
            )
            if not valid:
                raise RuntimeError(f"invalid amendment chain: {amendment_path.name}")
            chain = amendment["amended_study_sha256"]
        if chain != actual:
            raise RuntimeError(f"frozen method file changed: {name}")
    reuse = read_json(HERE / "source_reuse_manifest.json")
    if (
        canonical_digest(reuse) != reuse.get("content_digest")
        or reuse["content_digest"] != checkpoint["source_reuse_digest"]
    ):
        raise RuntimeError("source reuse manifest mismatch")
    for item in reuse["entries"]:
        source = Path(item["path"])
        if (
            not source.exists() or source.stat().st_size != int(item["bytes"])
            or sha256_file(source) != item["sha256"]
        ):
            raise RuntimeError(f"reused source changed: {source}")
    return checkpoint


def prior_stage(stage: str) -> str | None:
    return {"evaluation": "development", "confirmation": "evaluation"}.get(stage)


def stage_authorized(stage: str) -> None:
    prior = prior_stage(stage)
    if prior is None:
        return
    gate = HERE / f"{prior}_gate.json"
    if not gate.exists() or read_json(gate).get("status") != "PASS":
        raise RuntimeError(f"{stage} is sealed until {prior} gate PASS")


def load_source(source_stage: str) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    spec = SOURCE_SPECS[source_stage]
    engine = load_module(DATA_ENGINE, f"halpha_mom70_loader_{source_stage}")
    engine.HERE = spec["directory"]
    bars: dict[str, pd.DataFrame] = {}
    funding: dict[str, pd.DataFrame] = {}
    for symbol in SYMBOLS:
        bars[symbol], funding[symbol] = engine.load_symbol(spec["manifest_stage"], symbol)
    return bars, funding


def load_stage(stage: str) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame], dict[str, Any]]:
    bars, funding = load_source(stage)
    metadata: dict[str, Any] = {"overlap_rows": 0, "overlap_mismatch_rows": 0}
    if stage != "confirmation":
        return bars, funding, metadata
    warm_bars, _ = load_source("evaluation")
    combined: dict[str, pd.DataFrame] = {}
    overlap_rows = overlap_mismatch_rows = 0
    columns = ["open", "high", "low", "close", "volume", "quote_volume"]
    for symbol in SYMBOLS:
        common = warm_bars[symbol].index.intersection(bars[symbol].index)
        overlap_rows += len(common)
        if len(common):
            left = warm_bars[symbol].loc[common, columns].to_numpy(float)
            right = bars[symbol].loc[common, columns].to_numpy(float)
            overlap_mismatch_rows += int((~np.isclose(left, right, rtol=1e-12, atol=0.0)).any(axis=1).sum())
        frame = pd.concat([warm_bars[symbol], bars[symbol]]).sort_index()
        combined[symbol] = frame[~frame.index.duplicated(keep="last")]
    metadata = {"overlap_rows": overlap_rows, "overlap_mismatch_rows": overlap_mismatch_rows}
    return combined, funding, metadata


def stage_entries(stage: str) -> pd.DatetimeIndex:
    start, end = map(pd.Timestamp, STAGES[stage])
    return pd.date_range(start, end, freq="W-MON", inclusive="left")


def command_prepare(args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    stage_authorized(args.stage)
    bars, funding, load_metadata = load_stage(args.stage)
    entries = stage_entries(args.stage)
    first_decision = entries[0] - pd.Timedelta(days=1)
    required_start = first_decision - pd.Timedelta(days=84)
    required_end = entries[-1] + pd.Timedelta(days=7)
    expected = pd.date_range(required_start, required_end, freq="1D")
    parent_quality = read_json(SOURCE_SPECS[args.stage]["data_quality"])
    status = parent_quality.get("status") == "PASS" and load_metadata["overlap_mismatch_rows"] == 0
    per_symbol: dict[str, Any] = {}
    for symbol in SYMBOLS:
        frame = bars[symbol].sort_index()
        subset = frame[(frame.index >= required_start) & (frame.index <= required_end)]
        missing_days = int(len(expected.difference(subset.index)))
        invalid_ohlc = int((
            (subset[["open", "high", "low", "close"]] <= 0).any(axis=1)
            | (subset["high"] < subset[["open", "close"]].max(axis=1))
            | (subset["low"] > subset[["open", "close"]].min(axis=1))
        ).sum())
        invalid_volume = int((subset[["volume", "quote_volume"]] < 0).any(axis=1).sum())
        rates = funding[symbol]
        relevant = rates[(rates.index > entries[0]) & (rates.index <= required_end)]
        missing_marks = int(relevant["markPrice"].isna().sum())
        if len(relevant) > 1:
            max_gap = float(relevant.index.to_series().diff().dt.total_seconds().max() / 3600.0)
        else:
            max_gap = math.inf
        # A missing public bar makes that target NO_ACTION while its 85-day completeness
        # window contains the gap. It does not invalidate other targets or the whole stage.
        item_pass = (
            invalid_ohlc == 0 and invalid_volume == 0 and len(relevant) > 0 and max_gap <= 24.0
        )
        status = status and item_pass
        per_symbol[symbol] = {
            "daily_rows": int(len(subset)), "missing_days": missing_days,
            "invalid_ohlc_rows": invalid_ohlc, "invalid_volume_rows": invalid_volume,
            "funding_rows": int(len(relevant)), "missing_mark_rows": missing_marks,
            "max_funding_gap_hours": None if not math.isfinite(max_gap) else max_gap,
            "status": "PASS" if item_pass else "FAIL",
        }
    input_indicators = {symbol: momentum_frame(frame) for symbol, frame in bars.items()}
    decision_rankable_counts: dict[str, int] = {}
    for entry in entries:
        decision = entry - pd.Timedelta(days=1)
        exit_time = entry + pd.Timedelta(days=7)
        rankable = 0
        for symbol in SYMBOLS:
            indicator = input_indicators[symbol]
            if (
                decision in indicator.index and bool(indicator.at[decision, "complete_85d"])
                and entry in bars[symbol].index and exit_time in bars[symbol].index
                and pd.notna(bars[symbol].at[entry, "open"])
                and pd.notna(bars[symbol].at[exit_time, "open"])
            ):
                rankable += 1
        decision_rankable_counts[entry.isoformat()] = rankable
    below_minimum = {
        entry: count for entry, count in decision_rankable_counts.items()
        if count < int(CONFIG["minimum_rankable_symbols"])
    }
    status = status and not below_minimum
    payload = {
        "checked_at_utc": iso_now(), "stage": args.stage,
        "status": "PASS" if status else "FAIL",
        "checkpoint_digest": checkpoint["content_digest"],
        "source_manifest_sha256": sha256_file(SOURCE_SPECS[args.stage]["manifest"]),
        "parent_data_quality_sha256": sha256_file(SOURCE_SPECS[args.stage]["data_quality"]),
        "required_daily_range_inclusive": [required_start.isoformat(), required_end.isoformat()],
        "source_overlap": load_metadata,
        "decision_input_availability": {
            "minimum_rankable": min(decision_rankable_counts.values()),
            "maximum_rankable": max(decision_rankable_counts.values()),
            "dates_below_minimum": below_minimum,
        },
        "symbols": per_symbol,
        "rule": (
            "OHLCV is calendar-reindexed and never imputed. A target with any gap in its rolling 85-day "
            "input window is NO_ACTION; the stage remains valid only when every decision still has at least "
            "20 rankable targets. Missing funding marks exclude the spanning opportunity under the frozen "
            "2% gate. Funding gaps over 24h fail source integrity."
        ),
    }
    write_json(HERE / f"data_quality_{args.stage}.json", payload, digest=True)
    print(json.dumps({"stage": args.stage, "status": payload["status"], "symbols": len(per_symbol)}))


def momentum_frame(frame: pd.DataFrame) -> pd.DataFrame:
    calendar = pd.date_range(frame.index.min(), frame.index.max(), freq="1D")
    frame = frame.reindex(calendar)
    output = pd.DataFrame(index=frame.index)
    for days in (7, 56, 70, 84):
        output[f"mom{days}"] = frame["close"] / frame["close"].shift(days) - 1.0
    output["median_quote_volume_30d"] = frame["quote_volume"].rolling(30, min_periods=30).median()
    required = frame[["open", "high", "low", "close", "quote_volume"]].notna().all(axis=1)
    output["complete_85d"] = required.rolling(85, min_periods=85).sum().eq(85)
    return output.replace([np.inf, -np.inf], np.nan)


def build_panel(bars: dict[str, pd.DataFrame], stage: str) -> pd.DataFrame:
    indicators = {symbol: momentum_frame(frame) for symbol, frame in bars.items()}
    rows: list[dict[str, Any]] = []
    for entry in stage_entries(stage):
        decision = entry - pd.Timedelta(days=1)
        exit_time = entry + pd.Timedelta(days=7)
        candidates: list[dict[str, Any]] = []
        for symbol in SYMBOLS:
            if (
                decision not in indicators[symbol].index
                or entry not in bars[symbol].index or exit_time not in bars[symbol].index
            ):
                continue
            values = indicators[symbol].loc[
                decision, ["mom7", "mom56", "mom70", "mom84", "median_quote_volume_30d", "complete_85d"]
            ]
            if values.isna().any() or not bool(values["complete_85d"]) or float(values["median_quote_volume_30d"]) < float(
                CONFIG["minimum_median_quote_volume_30d"]
            ):
                continue
            candidates.append({
                "entry_time": entry, "decision_time": decision, "exit_time": exit_time,
                "symbol": symbol, "entry_price": float(bars[symbol].at[entry, "open"]),
                "exit_price": float(bars[symbol].at[exit_time, "open"]),
                "mom7": float(values["mom7"]), "mom56": float(values["mom56"]),
                "mom70": float(values["mom70"]), "mom84": float(values["mom84"]),
                "median_quote_volume_30d": float(values["median_quote_volume_30d"]),
            })
        if len(candidates) < int(CONFIG["minimum_rankable_symbols"]):
            continue
        for item in candidates:
            item["eligible_count"] = len(candidates)
        rows.extend(candidates)
    if not rows:
        raise RuntimeError(f"weekly panel is empty: {stage}")
    return pd.DataFrame(rows).sort_values(["entry_time", "symbol"]).reset_index(drop=True)


def score_set(panel: pd.DataFrame, column: str) -> dict[pd.Timestamp, pd.DataFrame]:
    output: dict[pd.Timestamp, pd.DataFrame] = {}
    for entry, week in panel.groupby("entry_time", sort=True):
        ranked = week.copy()
        ranked["score"] = ranked[column]
        output[pd.Timestamp(entry)] = ranked
    return output


def adjusted_long_funding_rate(rate: float) -> float:
    if rate > 0:
        return rate * float(CONFIG["long_funding_stress"]["positive_cost_multiplier"])
    return rate * float(CONFIG["long_funding_stress"]["negative_benefit_multiplier"])


def make_long_trades(
    scores: dict[pd.Timestamp, pd.DataFrame], funding: dict[str, pd.DataFrame],
    stage: str, name: str, *, mode: str, fraction: float | None = None,
    cooldown: bool = True,
) -> tuple[pd.DataFrame, dict[str, int]]:
    rows: list[dict[str, Any]] = []
    last_exit: dict[str, pd.Timestamp] = {}
    planned = excluded_marks = excluded_funding = cooldown_skips = 0
    for entry in sorted(scores):
        week = scores[entry].copy()
        if mode == "bottom":
            count = int(math.ceil(len(week) * float(fraction or CONFIG["bottom_fraction"])))
            week = week.sort_values(["score", "symbol"], ascending=[True, True]).head(count)
        elif mode == "top":
            count = int(math.ceil(len(week) * float(fraction or CONFIG["bottom_fraction"])))
            week = week.sort_values(["score", "symbol"], ascending=[False, True]).head(count)
        elif mode == "all":
            week = week.sort_values("symbol")
        else:
            raise ValueError(mode)
        for rank, (_, item) in enumerate(week.iterrows(), start=1):
            symbol = str(item["symbol"])
            planned += 1
            if (
                cooldown and symbol in last_exit
                and entry <= last_exit[symbol] + pd.Timedelta(days=int(CONFIG["cooldown_full_days"]))
            ):
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
            entry_price = float(item["entry_price"])
            exit_price = float(item["exit_price"])
            notional = float(CONFIG["notional_fraction"])
            quantity = notional / entry_price
            actual_funding = -float((quantity * rates["markPrice"] * rates["fundingRate"]).sum())
            stress_funding = -float((
                quantity * rates["markPrice"] * rates["fundingRate"].map(adjusted_long_funding_rate)
            ).sum())
            gross = notional * (exit_price / entry_price - 1.0)
            rows.append({
                "trade_id": f"{stage}-{name}-{entry:%Y%m%d}-{symbol}",
                "strategy_variant": name, "entry_time": entry, "exit_time": exit_time,
                "decision_time": item["decision_time"], "symbol": symbol,
                "score": float(item.get("score", np.nan)), "selection_rank": rank,
                "eligible_count": int(item["eligible_count"]),
                "entry_price": entry_price, "exit_price": exit_price,
                "notional_fraction": notional, "quantity_per_unit_plan_capital": quantity,
                "funding_events": int(len(rates)), "actual_funding_return": actual_funding,
                "stress_funding_return": stress_funding, "gross_long_return": gross,
            })
            last_exit[symbol] = exit_time
    return pd.DataFrame(rows), {
        "planned": planned, "excluded_missing_marks": excluded_marks,
        "excluded_missing_funding": excluded_funding, "cooldown_skips": cooldown_skips,
    }


def vectorbt_long_returns(trades: pd.DataFrame, fee: float, slippage: float) -> np.ndarray:
    columns = trades["trade_id"].tolist()
    prices = pd.DataFrame(
        [trades["entry_price"].to_numpy(float), trades["exit_price"].to_numpy(float)],
        columns=columns,
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
    if trades.empty:
        raise RuntimeError("strategy produced no trades")
    output = trades.copy()
    for scenario, assumptions in CONFIG["costs"].items():
        fee = float(assumptions["fee_per_side"])
        slippage = float(assumptions["slippage_per_side"])
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
        raise RuntimeError("bootstrap input is empty")
    block = int(CONFIG["bootstrap"]["block_weeks"])
    reps = int(CONFIG["bootstrap"]["repetitions"])
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
        weekly = date_returns(trades, f"{scenario}_net_return")
        adjusted = weekly - hurdle_per_week()
        total = float(np.prod(1.0 + weekly.to_numpy(float)) - 1.0)
        result["scenarios"][scenario] = {
            "date_mean": float(weekly.mean()), "date_mean_after_hurdle": float(adjusted.mean()),
            "date_mean_after_hurdle_bootstrap_95pct": block_bootstrap_mean_ci(adjusted.to_numpy(float)),
            "compound_return": total,
            "annualized_return": float((1.0 + total) ** (365.0 / (end - start).days) - 1.0),
            "date_portfolio_max_drawdown": max_drawdown(weekly),
        }
    base_adjusted = date_returns(trades, "base_net_return") - hurdle_per_week()
    midpoint = start + (end - start) / 2
    for label, mask in (("H1", base_adjusted.index < midpoint), ("H2", base_adjusted.index >= midpoint)):
        values = base_adjusted[mask]
        result["by_half"][label] = {"dates": int(len(values)), "mean_after_hurdle": float(values.mean())}
    target_means: dict[str, float] = {}
    target_drawdowns: dict[str, float] = {}
    for symbol, group in trades.groupby("symbol"):
        series = group.sort_values("entry_time")["base_net_return"]
        target_means[str(symbol)] = float((series - hurdle_per_week()).mean())
        target_drawdowns[str(symbol)] = max_drawdown(series)
    result["by_symbol"] = {
        symbol: {
            "trades": int((trades["symbol"] == symbol).sum()),
            "base_mean_after_hurdle": target_means[symbol],
            "base_max_drawdown": target_drawdowns[symbol],
        }
        for symbol in sorted(target_means)
    }
    result["worst_symbol_base_max_drawdown"] = float(min(target_drawdowns.values()))
    pnl = trades.groupby("symbol")["base_net_return"].sum()
    positive = pnl.clip(lower=0.0)
    result["largest_positive_pnl_share"] = float(positive.max() / positive.sum()) if positive.sum() > 0 else 1.0
    for category in sorted(CATEGORY_MEMBERS):
        subset = trades[trades["symbol"].isin(CATEGORY_MEMBERS[category])]
        if not subset.empty:
            result["by_category"][category] = {
                "trades": int(len(subset)),
                "base_mean_after_hurdle": float((subset["base_net_return"] - hurdle_per_week()).mean()),
            }
    return result


def compare_with_cash(main: pd.DataFrame, baseline: pd.DataFrame, column: str = "base_net_return") -> dict[str, Any]:
    left = date_returns(main, column)
    raw_right = date_returns(baseline, column)
    right = raw_right.reindex(left.index, fill_value=0.0)
    difference = left - right
    return {
        "main_mean": float(left.mean()), "baseline_mean": float(right.mean()),
        "difference_mean": float(difference.mean()),
        "difference_bootstrap_95pct": block_bootstrap_mean_ci(difference.to_numpy(float)),
        "positive_date_fraction": float((difference > 0).mean()),
        "baseline_no_action_dates_filled_as_cash": int((~left.index.isin(raw_right.index)).sum()),
    }


def command_self_test(_args: argparse.Namespace) -> None:
    index = pd.date_range("2025-01-01T00:00:00Z", periods=100, freq="1D")
    close = pd.Series(np.linspace(100.0, 200.0, 100), index=index)
    frame = pd.DataFrame({
        "open": close, "high": close * 1.01, "low": close * 0.99,
        "close": close, "quote_volume": 20_000_000.0,
    }, index=index)
    output = momentum_frame(frame)
    expected = float(close.iloc[-1] / close.iloc[-71] - 1.0)
    if not math.isclose(float(output["mom70"].iloc[-1]), expected, rel_tol=0.0, abs_tol=1e-14):
        raise RuntimeError("MOM70 formula mismatch")
    sample = pd.DataFrame([{
        "trade_id": "test", "entry_price": 100.0, "exit_price": 110.0,
        "quantity_per_unit_plan_capital": 0.0025,
    }])
    vector = float(vectorbt_long_returns(sample, 0.0006, 0.0010)[0])
    manual = float(manual_long_return(sample.iloc[0], 0.0006, 0.0010))
    if not math.isclose(vector, manual, rel_tol=0.0, abs_tol=1e-12):
        raise RuntimeError("VectorBT/manual long reconciliation mismatch")
    if adjusted_long_funding_rate(0.001) != 0.0015 or adjusted_long_funding_rate(-0.001) != -0.0005:
        raise RuntimeError("LONG funding stress direction mismatch")
    print(json.dumps({
        "status": "PASS", "mom70": expected,
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
    main_scores = score_set(panel, "mom70")
    score_sets = {
        "main": main_scores, "mom56": score_set(panel, "mom56"),
        "mom84": score_set(panel, "mom84"), "bottom20": main_scores,
        "mom7": score_set(panel, "mom7"), "winner70": main_scores,
        "scheduled_long": main_scores, "market_long": main_scores,
    }
    specs = {
        "main": ("bottom", float(CONFIG["bottom_fraction"]), True),
        "mom56": ("bottom", float(CONFIG["bottom_fraction"]), True),
        "mom84": ("bottom", float(CONFIG["bottom_fraction"]), True),
        "bottom20": ("bottom", float(CONFIG["bottom_neighbor_fraction"]), True),
        "mom7": ("bottom", float(CONFIG["bottom_fraction"]), True),
        "winner70": ("top", float(CONFIG["bottom_fraction"]), True),
        "scheduled_long": ("all", None, True),
        "market_long": ("all", None, False),
    }
    trades: dict[str, pd.DataFrame] = {}
    opportunity_counts: dict[str, dict[str, int]] = {}
    for name, (mode, fraction, cooldown) in specs.items():
        raw, opportunity_counts[name] = make_long_trades(
            score_sets[name], funding, args.stage, name, mode=mode,
            fraction=fraction, cooldown=cooldown,
        )
        trades[name] = attach_returns(raw)
    csv_hashes: dict[str, str] = {}
    for name, frame in trades.items():
        path = HERE / f"{args.stage}_{name}_trades.csv"
        frame.to_csv(path, index=False, date_format="%Y-%m-%dT%H:%M:%S%z")
        csv_hashes[path.name] = sha256_file(path)
    summaries = {name: summarize(frame, args.stage) for name, frame in trades.items()}
    gross_main = date_returns(trades["main"], "gross_long_return")
    gross_market = date_returns(trades["market_long"], "gross_long_return").reindex(gross_main.index)
    if gross_market.isna().any():
        raise RuntimeError("market baseline missing a main entry date")
    gross_excess = gross_main - gross_market
    correlations = [
        float(week["mom70"].corr(week["mom7"], method="spearman"))
        for _, week in panel.groupby("entry_time")
    ]
    comparisons = {
        "base_vs_mom7": compare_with_cash(trades["main"], trades["mom7"]),
        "base_vs_winner70": compare_with_cash(trades["main"], trades["winner70"]),
        "base_vs_scheduled_long": compare_with_cash(trades["main"], trades["scheduled_long"]),
        "gross_vs_equal_weight_market_long": {
            "main_mean": float(gross_main.mean()), "market_mean": float(gross_market.mean()),
            "difference_mean": float(gross_excess.mean()),
            "difference_bootstrap_95pct": block_bootstrap_mean_ci(gross_excess.to_numpy(float)),
        },
        "mom70_vs_mom7_weekly_spearman": {
            "median": float(np.median(correlations)), "minimum": float(np.min(correlations)),
            "maximum": float(np.max(correlations)), "weeks": len(correlations),
        },
    }
    payload = {
        "analyzed_at_utc": iso_now(), "stage": args.stage,
        "checkpoint_digest": checkpoint["content_digest"],
        "data_quality_digest": read_json(dq_path)["content_digest"],
        "panel_rows": int(len(panel)), "panel_weeks": int(panel["entry_time"].nunique()),
        "opportunity_counts": opportunity_counts, "summaries": summaries,
        "comparisons": comparisons, "trade_csv_sha256": csv_hashes,
    }
    write_json(HERE / f"{args.stage}.json", payload, digest=True)
    evidence = read_json(HERE / f"{args.stage}.json")
    print(json.dumps({
        "stage": args.stage, "trades": summaries["main"]["trades"],
        "base_after_hurdle": summaries["main"]["scenarios"]["base"]["date_mean_after_hurdle"],
        "stress_after_hurdle": summaries["main"]["scenarios"]["stress"]["date_mean_after_hurdle"],
        "digest": evidence["content_digest"],
    }))


def common_checks(stage: str, evidence: dict[str, Any]) -> tuple[dict[str, bool], dict[str, Any]]:
    main = evidence["summaries"]["main"]
    base = main["scenarios"]["base"]
    stress = main["scenarios"]["stress"]
    counts = evidence["opportunity_counts"]["main"]
    exclusions = counts["excluded_missing_marks"] + counts["excluded_missing_funding"]
    excluded_fraction = exclusions / max(1, counts["planned"])
    positive_targets = sum(item["base_mean_after_hurdle"] > 0 for item in main["by_symbol"].values())
    positive_categories = sum(item["base_mean_after_hurdle"] > 0 for item in main["by_category"].values())
    neighbor_positive = sum(
        evidence["summaries"][name]["scenarios"]["stress"]["date_mean_after_hurdle"] >= 0
        for name in ("mom56", "mom84", "bottom20")
    )
    minimums = STAGE_MINIMUMS[stage]
    checks = {
        "data_quality_pass": read_json(HERE / f"data_quality_{stage}.json")["status"] == "PASS",
        "minimum_trades": main["trades"] >= minimums["trades"],
        "minimum_20_symbols": main["symbols"] >= 20,
        "minimum_entry_dates": main["entry_dates"] >= minimums["entry_dates"],
        "excluded_funding_or_marks_at_most_2pct": excluded_fraction <= 0.02,
        "base_after_hurdle_positive": base["date_mean_after_hurdle"] > 0,
        "stress_after_hurdle_positive": stress["date_mean_after_hurdle"] > 0,
        "both_halves_base_positive": all(
            item["dates"] > 0 and item["mean_after_hurdle"] > 0 for item in main["by_half"].values()
        ),
        "date_portfolio_drawdown_above_minus_15pct": base["date_portfolio_max_drawdown"] > -0.15,
        "worst_symbol_drawdown_above_minus_30pct": main["worst_symbol_base_max_drawdown"] > -0.30,
        "base_beats_mom7": evidence["comparisons"]["base_vs_mom7"]["difference_mean"] > 0,
        "base_beats_winner70": evidence["comparisons"]["base_vs_winner70"]["difference_mean"] > 0,
        "base_beats_scheduled_long": (
            evidence["comparisons"]["base_vs_scheduled_long"]["difference_mean"] > 0
        ),
        "gross_excess_vs_market_positive": (
            evidence["comparisons"]["gross_vs_equal_weight_market_long"]["difference_mean"] > 0
        ),
        "at_least_two_of_three_neighbors_stress_nonnegative": neighbor_positive >= 2,
        "at_least_half_selected_targets_positive": positive_targets / max(1, main["symbols"]) >= 0.5,
        "at_least_four_categories_positive": positive_categories >= 4,
        "largest_positive_pnl_share_at_most_20pct": main["largest_positive_pnl_share"] <= 0.20,
        "vectorbt_manual_reconciliation": main["maximum_vectorbt_reconciliation_error"] <= 1e-10,
    }
    diagnostics = {
        "excluded_fraction": excluded_fraction, "positive_targets": positive_targets,
        "positive_categories": positive_categories, "neighbor_positive": neighbor_positive,
    }
    return checks, diagnostics


def pooled_heldout() -> dict[str, Any]:
    main_parts: list[pd.DataFrame] = []
    market_parts: list[pd.DataFrame] = []
    for stage in ("evaluation", "confirmation"):
        main = pd.read_csv(HERE / f"{stage}_main_trades.csv", parse_dates=["entry_time"])
        market = pd.read_csv(HERE / f"{stage}_market_long_trades.csv", parse_dates=["entry_time"])
        main_parts.append(main)
        market_parts.append(market)
    all_main = pd.concat(main_parts, ignore_index=True)
    all_market = pd.concat(market_parts, ignore_index=True)
    stress_adjusted = date_returns(all_main, "stress_net_return") - hurdle_per_week()
    gross_main = date_returns(all_main, "gross_long_return")
    gross_market = date_returns(all_market, "gross_long_return").reindex(gross_main.index)
    if gross_market.isna().any():
        raise RuntimeError("pooled market baseline missing a main date")
    gross_excess = gross_main - gross_market
    return {
        "entry_dates": int(len(stress_adjusted)),
        "stress_mean_after_hurdle": float(stress_adjusted.mean()),
        "stress_mean_after_hurdle_bootstrap_95pct": block_bootstrap_mean_ci(stress_adjusted.to_numpy(float)),
        "gross_market_excess_mean": float(gross_excess.mean()),
        "gross_market_excess_bootstrap_95pct": block_bootstrap_mean_ci(gross_excess.to_numpy(float)),
    }


def write_failure_result(stage: str, evidence: dict[str, Any], gate: dict[str, Any]) -> None:
    main = evidence["summaries"]["main"]
    base = main["scenarios"]["base"]
    stress = main["scenarios"]["stress"]
    economic_negative = (
        base["date_mean_after_hurdle"] <= 0 or stress["date_mean_after_hurdle"] <= 0
        or evidence["comparisons"]["base_vs_winner70"]["difference_mean"] <= 0
        or evidence["comparisons"]["base_vs_scheduled_long"]["difference_mean"] <= 0
        or evidence["comparisons"]["gross_vs_equal_weight_market_long"]["difference_mean"] <= 0
    )
    conclusion = "DOES_NOT_SUPPORT" if economic_negative else "INSUFFICIENT_EVIDENCE"
    stages = {
        name: read_json(HERE / f"{name}_gate.json")["status"]
        for name in STAGES if (HERE / f"{name}_gate.json").exists()
    }
    payload = {
        "created_at_utc": iso_now(), "question": read_json(HERE / "checkpoint.json")["question"],
        "conclusion": conclusion, "failed_stage": stage, "stage_gates": stages,
        "failed_checks": gate["failed"], "handoff_generated": False,
        "summary": {
            "trades": main["trades"], "entry_dates": main["entry_dates"], "symbols": main["symbols"],
            "base_mean_after_hurdle": base["date_mean_after_hurdle"],
            "stress_mean_after_hurdle": stress["date_mean_after_hurdle"],
            "stress_bootstrap_95pct": stress["date_mean_after_hurdle_bootstrap_95pct"],
            "base_max_drawdown": base["date_portfolio_max_drawdown"],
            "base_vs_mom7": evidence["comparisons"]["base_vs_mom7"],
            "base_vs_winner70": evidence["comparisons"]["base_vs_winner70"],
            "base_vs_scheduled_long": evidence["comparisons"]["base_vs_scheduled_long"],
            "gross_excess_vs_market": evidence["comparisons"]["gross_vs_equal_weight_market_long"],
            "largest_positive_pnl_share": main["largest_positive_pnl_share"],
        },
    }
    write_json(HERE / "results.json", payload, digest=True)
    text = f"""# 结果：10 周输家 one-shot LONG

## 结论

`{conclusion}`

固定的 MOM70 底部 30%、`0.25x LONG / 7d` 转换在 `{stage}` 阶段未通过预注册门，因此不再打开后续阶段，不生成交易核心 handoff，也不修改正式策略、产品代码、资金或真实账户。

## 关键数值

- 交易 / entry dates / 目标：`{main['trades']} / {main['entry_dates']} / {main['symbols']}`
- base / stress 扣 4% 全计划资金门槛后的周日期均值：`{base['date_mean_after_hurdle']:.6%} / {stress['date_mean_after_hurdle']:.6%}`
- stress 4 周 block-bootstrap 95% 区间：`[{stress['date_mean_after_hurdle_bootstrap_95pct'][0]:.6%}, {stress['date_mean_after_hurdle_bootstrap_95pct'][1]:.6%}]`
- base 日期组合最大回撤：`{base['date_portfolio_max_drawdown']:.6%}`
- 相对一周输家 / 十周赢家 / 无筛选做多的 base 差：`{evidence['comparisons']['base_vs_mom7']['difference_mean']:.6%} / {evidence['comparisons']['base_vs_winner70']['difference_mean']:.6%} / {evidence['comparisons']['base_vs_scheduled_long']['difference_mean']:.6%}`
- gross 相对等权市场差：`{evidence['comparisons']['gross_vs_equal_weight_market_long']['difference_mean']:.6%}`
- 失败门：`{', '.join(gate['failed'])}`

## 解释边界

这只否定或限制当前 25 个幸存 USD-M 永续、固定单目标、零售成本和 one-shot 转换；不推翻论文的广泛现货、point-in-time、分散 long-short 组合。正回测也不会证明长期盈利，本次失败更不能靠挑选诊断窗口补救。
"""
    (HERE / "result.md").write_text(text, encoding="utf-8")


def write_success_result(evidence: dict[str, Any], gate: dict[str, Any]) -> None:
    pooled = gate["pooled_heldout"]
    checkpoint = read_json(HERE / "checkpoint.json")
    handoff = {
        "created_at_utc": iso_now(),
        "status": "RESEARCH_CANDIDATE_FOR_CORE_QUALIFICATION_ONLY",
        "authorization": "No product change, capital allocation, real-account action or long-term-profit guarantee",
        "identity": {"strategy_id": CONFIG["strategy_id"], "version": "1.0.0-research"},
        "baseline_commit": checkpoint["baseline_commit"], "direction": "LONG_ONLY",
        "instrument_contract": (
            "The owner fixes one symbol from the frozen target list. The strategy only returns ELIGIBLE or "
            "NO_ACTION for that symbol; it does not choose or rotate the owner's instrument."
        ),
        "timeframe_and_warmup": {
            "bar": "UTC 1d completed OHLCV", "minimum_calendar_days": 85,
            "cross_section_symbols": SYMBOLS, "decision": "after completed UTC Sunday bar",
            "action_time": "following UTC Monday open boundary",
        },
        "inputs": {
            "per_symbol": ["open", "close", "quote_volume"],
            "cross_section": "same timestamp completed data for every frozen target",
            "derived": ["MOM70", "median_quote_volume_30d", "eligible_count", "rank"],
            "universe_sha256": UNIVERSE_SHA256,
        },
        "signal": {
            "score": "close[Sunday] / close[Sunday-70 calendar days] - 1",
            "liquidity": "median quote_volume over 30 completed daily bars >= 10,000,000 USDT",
            "minimum_rankable": 20, "sort": "score ascending; symbol ascending tie-break",
            "eligible_set": "first ceil(0.30 * rankable_count)",
        },
        "action": {
            "on_eligible": "LONG", "amount": "0.25 * owner-approved plan amount",
            "entry": "first executable price after the following UTC Monday boundary",
            "exit": "time exit after 7 completed calendar days; no pyramiding",
        },
        "protection": {
            "notional_cap": "0.25x plan capital", "maximum_positions_per_plan": 1,
            "time_exit_days": 7, "cooldown": "one full UTC day after exit",
            "intraday_price_stop": None,
            "qualification_caveat": "Adding any price stop is an economic-rule change and requires requalification",
        },
        "unknown_or_no_action": [
            "owner target or direction differs from frozen contract", "universe identity mismatch",
            "any required completed bar is missing, stale, revised or timestamp-ambiguous",
            "fewer than 20 rankable targets", "owner target is not in the bottom 30%",
            "cooldown is active", "entry/exit execution boundary cannot be established",
        ],
        "research_cost_proxy": CONFIG["costs"],
        "deterministic_decision_trace_fields": [
            "strategy_id", "universe_sha256", "decision_time", "action_time", "owner_symbol",
            "eligible_symbols", "eligible_count", "owner_mom70", "owner_volume_median_30d",
            "owner_rank", "selection_count", "cooldown_state", "decision", "reason",
        ],
        "qualification_evidence": {
            "development_digest": read_json(HERE / "development.json")["content_digest"],
            "evaluation_digest": read_json(HERE / "evaluation.json")["content_digest"],
            "confirmation_digest": evidence["content_digest"],
            "confirmation_gate_digest": gate["content_digest"],
            "pooled_heldout": pooled,
        },
        "known_limits": [
            "current-survivor target list; no delisted/new-listing point-in-time universe",
            "daily-bar execution proxy; no L2 latency or realized fill model",
            "external papers overlap the test years; this is not post-publication market evidence",
            "no OI, liquidation, news, sentiment or on-chain mechanism identification",
            "backtest support cannot establish future or long-term profitability",
        ],
    }
    write_json(HERE / "handoff.json", handoff, digest=True)
    main = evidence["summaries"]["main"]
    stress = main["scenarios"]["stress"]
    results = {
        "created_at_utc": iso_now(), "question": checkpoint["question"],
        "conclusion": "SUPPORTS_WITHIN_SCOPE",
        "stage_gates": {stage: "PASS" for stage in STAGES},
        "pooled_heldout": pooled, "handoff_generated": True,
        "handoff_digest": read_json(HERE / "handoff.json")["content_digest"],
        "scope_warning": (
            "Candidate for core qualification, not proof of alpha, long-term profit, product readiness or real trading."
        ),
    }
    write_json(HERE / "results.json", results, digest=True)
    text = f"""# 结果：10 周输家 one-shot LONG

## 结论

`SUPPORTS_WITHIN_SCOPE`

主规则通过 development、2024 evaluation、2025 confirmation 和合并留出期门，已生成框架无关 `handoff.json`，仅供未来交易核心资格验证。它没有修改产品，不授权实盘，也不证明长期盈利。

## 关键留出证据

- confirmation stress 扣 hurdle 周日期均值：`{stress['date_mean_after_hurdle']:.6%}`
- 合并 2024–2025 stress 均值与 95% 区间：`{pooled['stress_mean_after_hurdle']:.6%}`，`[{pooled['stress_mean_after_hurdle_bootstrap_95pct'][0]:.6%}, {pooled['stress_mean_after_hurdle_bootstrap_95pct'][1]:.6%}]`
- 合并 gross 市场超额均值与 95% 区间：`{pooled['gross_market_excess_mean']:.6%}`，`[{pooled['gross_market_excess_bootstrap_95pct'][0]:.6%}, {pooled['gross_market_excess_bootstrap_95pct'][1]:.6%}]`

## 限制

固定 current-survivor 名单、日线开盘代理、外部论文与测试年份重叠、无退市全市场与盘口成交证据。核心资格验证还必须重放决策 trace、核对数据可得性，并在 demo/shadow 中检验真实执行偏差。
"""
    (HERE / "result.md").write_text(text, encoding="utf-8")


def command_gate(args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    stage_authorized(args.stage)
    evidence_path = HERE / f"{args.stage}.json"
    if not evidence_path.exists():
        raise RuntimeError(f"stage evidence missing: {args.stage}")
    evidence = read_json(evidence_path)
    checks, diagnostics = common_checks(args.stage, evidence)
    if args.stage == "development":
        checks["stress_bootstrap_lower_positive"] = (
            evidence["summaries"]["main"]["scenarios"]["stress"]
            ["date_mean_after_hurdle_bootstrap_95pct"][0] > 0
        )
        checks["gross_market_excess_bootstrap_lower_positive"] = (
            evidence["comparisons"]["gross_vs_equal_weight_market_long"]
            ["difference_bootstrap_95pct"][0] > 0
        )
    pooled: dict[str, Any] | None = None
    if args.stage == "confirmation":
        pooled = pooled_heldout()
        checks.update({
            "pooled_heldout_stress_positive": pooled["stress_mean_after_hurdle"] > 0,
            "pooled_heldout_stress_bootstrap_lower_positive": (
                pooled["stress_mean_after_hurdle_bootstrap_95pct"][0] > 0
            ),
            "pooled_heldout_gross_market_excess_positive": pooled["gross_market_excess_mean"] > 0,
            "pooled_heldout_gross_market_excess_bootstrap_lower_positive": (
                pooled["gross_market_excess_bootstrap_95pct"][0] > 0
            ),
            "evaluation_stress_positive": (
                read_json(HERE / "evaluation.json")["summaries"]["main"]
                ["scenarios"]["stress"]["date_mean_after_hurdle"] > 0
            ),
        })
    status = "PASS" if all(checks.values()) else "FAIL"
    gate = {
        "created_at_utc": iso_now(), "stage": args.stage, "status": status,
        "checkpoint_digest": checkpoint["content_digest"], "checks": checks,
        "failed": [name for name, passed in checks.items() if not passed],
        "diagnostics": diagnostics, "evidence_digest": evidence["content_digest"],
    }
    if pooled is not None:
        gate["pooled_heldout"] = pooled
    write_json(HERE / f"{args.stage}_gate.json", gate, digest=True)
    written_gate = read_json(HERE / f"{args.stage}_gate.json")
    if status == "FAIL":
        write_failure_result(args.stage, evidence, written_gate)
    elif args.stage == "confirmation":
        write_success_result(evidence, written_gate)
    print(json.dumps({"stage": args.stage, "status": status, "failed": written_gate["failed"]}))


def command_validate(_args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    required_json = ["source_reuse_manifest.json", "checkpoint.json"]
    opened: list[str] = []
    for stage in STAGES:
        gate_path = HERE / f"{stage}_gate.json"
        if not gate_path.exists():
            break
        opened.append(stage)
        required_json.extend([f"data_quality_{stage}.json", f"{stage}.json", f"{stage}_gate.json"])
    if not opened:
        raise RuntimeError("no completed stage to validate")
    last_gate = read_json(HERE / f"{opened[-1]}_gate.json")
    terminal = last_gate["status"] == "FAIL" or opened[-1] == "confirmation"
    if terminal:
        required_json.append("results.json")
    if (HERE / "handoff.json").exists():
        required_json.append("handoff.json")
    for name in required_json:
        payload = read_json(HERE / name)
        if canonical_digest(payload) != payload.get("content_digest"):
            raise RuntimeError(f"stable digest mismatch: {name}")
    csv_checked = 0
    for stage in opened:
        evidence = read_json(HERE / f"{stage}.json")
        for name, expected in evidence["trade_csv_sha256"].items():
            if sha256_file(HERE / name) != expected:
                raise RuntimeError(f"trade CSV mismatch: {name}")
            csv_checked += 1
    for index, stage in enumerate(opened):
        gate = read_json(HERE / f"{stage}_gate.json")
        later_stages = list(STAGES)[index + 1:]
        if gate["status"] == "FAIL":
            for later in later_stages:
                if list(HERE.glob(f"{later}*")):
                    raise RuntimeError(f"later artifact exists after {stage} failure")
            if (HERE / "handoff.json").exists():
                raise RuntimeError("handoff exists after a failed gate")
            break
    result = read_json(HERE / "results.json") if (HERE / "results.json").exists() else {}
    if result.get("conclusion") == "SUPPORTS_WITHIN_SCOPE" and not (HERE / "handoff.json").exists():
        raise RuntimeError("supported conclusion lacks handoff")
    payload = {
        "validated_at_utc": iso_now(), "status": "PASS",
        "checkpoint_digest": checkpoint["content_digest"], "opened_stages": opened,
        "json_digest_files_checked": len(required_json), "trade_csv_files_checked": csv_checked,
        "conclusion": result.get("conclusion"),
        "handoff_generated": (HERE / "handoff.json").exists(),
        "stable_digest_excludes_ephemeral_timestamps": True,
    }
    write_json(HERE / "validation.json", payload, digest=True)
    print(json.dumps(payload))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("checkpoint").set_defaults(func=command_checkpoint)
    sub.add_parser("self-test").set_defaults(func=command_self_test)
    for name, func in (("prepare", command_prepare), ("analyze", command_analyze), ("gate", command_gate)):
        item = sub.add_parser(name)
        item.add_argument("--stage", choices=STAGES, required=True)
        item.set_defaults(func=func)
    sub.add_parser("validate").set_defaults(func=command_validate)
    return parser


if __name__ == "__main__":
    arguments = build_parser().parse_args()
    arguments.func(arguments)
