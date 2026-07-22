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
PARENT_DIR = HERE.parent / "ten-week-loser-weekly-one-shot-long"
PARENT_STUDY = PARENT_DIR / "study.py"
DATA_ENGINE = HERE.parent / "perp-low-volatility-monthly-one-shot-long" / "study.py"
DEV_SOURCE = HERE.parent / "high-volatility-monthly-one-shot-short"
EVAL_SOURCE = HERE.parent / "perp-premium-momentum-daily-one-shot-long"
UNIVERSE_PATH = HERE.parents[3] / "market-universe" / "universe.csv"
UNIVERSE_SHA256 = "1f24adfb64b7a52a170b730ee7517916b2da8ab45785779dee6be991762186cc"
EXTERNAL_PDF = Path(
    "D:/projects/Codex/CodexHome/research-data/halpha/_sources/"
    "cryptocurrency-momentum-reversal-dobrynskaya-hse.pdf"
)
CACHE_ROOT = Path(
    "D:/projects/Codex/CodexHome/research-data/halpha/"
    "high-volatility-ten-week-loser/2026-07-22-v1"
)
SYMBOLS = [
    "1000XECUSDT", "AAVEUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "CRVUSDT",
    "DASHUSDT", "ENSUSDT", "ETCUSDT", "HBARUSDT", "KAVAUSDT", "LINKUSDT",
    "LTCUSDT", "NEARUSDT", "RUNEUSDT", "SNXUSDT", "SOLUSDT", "TRXUSDT",
    "UNIUSDT", "VETUSDT", "XLMUSDT", "XMRUSDT", "XRPUSDT", "ZECUSDT", "ZILUSDT",
]
CATEGORY_MEMBERS = {
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
    "development": ("2024-01-01T00:00:00Z", "2024-12-30T00:00:00Z"),
    "evaluation": ("2025-01-06T00:00:00Z", "2025-12-29T00:00:00Z"),
    "confirmation": ("2026-04-06T00:00:00Z", "2026-06-29T00:00:00Z"),
}
FETCH_STAGE = {
    "confirmation": {
        "fetch_start": "2026-01-01T00:00:00Z",
        "start": "2026-04-01T00:00:00Z",
        "end_exclusive": "2026-07-01T00:00:00Z",
    }
}
CONFIG = {
    "strategy_id": "RESEARCH_RV28_HIGH_HALF_MOM70_BOTTOM30_WEEKLY_LONG_0P25X_V1",
    "direction": "LONG_ONLY", "hold_days": 7, "notional_fraction": 0.25,
    "high_volatility_fraction": 0.50, "loser_fraction": 0.30,
    "minimum_rankable_symbols": 20,
    "minimum_median_quote_volume_30d": 10_000_000.0,
    "annual_capital_hurdle": 0.04, "cooldown_full_days": 1,
    "costs": {
        "favorable": {"fee_per_side": 0.0006, "slippage_per_side": 0.0, "funding_stress": False},
        "base": {"fee_per_side": 0.0006, "slippage_per_side": 0.0010, "funding_stress": False},
        "stress": {"fee_per_side": 0.0006, "slippage_per_side": 0.0020, "funding_stress": True},
    },
    "long_funding_stress": {"positive_cost_multiplier": 1.5, "negative_benefit_multiplier": 0.5},
    "bootstrap": {"block_weeks": 4, "repetitions": 5000, "seed": 20260722},
    "main": {"volatility_days": 28, "momentum_days": 70},
    "diagnostics": [
        "rv21", "rv42", "mom56", "lowvol_loser", "unconditional_loser",
        "highvol_winner", "highvol_scheduled", "market_long",
    ],
}
FROZEN_FILES = ["README.md", "preregistration.md", "sources.md", "study.py"]
EPHEMERAL_KEYS = {"created_at_utc", "checked_at_utc", "analyzed_at_utc", "validated_at_utc", "accessed_at_utc"}


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
            key: stable_value(item) for key, item in sorted(value.items())
            if key not in EPHEMERAL_KEYS and key != "content_digest"
        }
    if isinstance(value, list):
        return [stable_value(item) for item in value]
    return value


def canonical_digest(value: Any) -> str:
    raw = json.dumps(
        stable_value(value), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def write_json(path: Path, value: dict[str, Any], *, digest: bool = False) -> None:
    payload = dict(value)
    if digest:
        payload["content_digest"] = canonical_digest(payload)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def configure_parent() -> Any:
    parent = load_module(PARENT_STUDY, "halpha_highvol_loser_parent")
    parent.CONFIG = CONFIG
    parent.STAGES = STAGES
    return parent


def validate_universe() -> None:
    if not UNIVERSE_PATH.exists() or sha256_file(UNIVERSE_PATH) != UNIVERSE_SHA256:
        raise RuntimeError("frozen universe is missing or changed")
    frame = pd.read_csv(UNIVERSE_PATH, dtype=str, keep_default_na=False)
    subset = frame[frame["symbol"].isin(SYMBOLS)]
    actual = dict(zip(subset["symbol"], subset["classification_subtypes"], strict=True))
    if actual != SYMBOL_TO_CATEGORY:
        raise RuntimeError("frozen target classification differs")


def source_entries() -> list[dict[str, Any]]:
    paths: list[tuple[Path, str]] = [
        (PARENT_STUDY, "reused cost/statistics and public-cache adapter"),
        (PARENT_DIR / "amendment-001.json", "parent implementation identity chain"),
        (PARENT_DIR / "checkpoint.json", "closed Q17 identity and exposure"),
        (PARENT_DIR / "sources.md", "prior-art and counterevidence identity"),
        (DATA_ENGINE, "official public archive loader/fetcher"),
        (UNIVERSE_PATH, "frozen current target universe"),
        (DEV_SOURCE / "source_manifest_development.json", "2024 public input manifest"),
        (DEV_SOURCE / "data_quality_development.json", "2024 parent data quality"),
        (DEV_SOURCE / "checkpoint.json", "2024 parent source identity"),
        (EVAL_SOURCE / "source_manifest_evaluation.json", "2025 public input manifest"),
        (EVAL_SOURCE / "data_quality_evaluation.json", "2025 parent data quality"),
        (EVAL_SOURCE / "checkpoint.json", "2025 parent source identity"),
        (EXTERNAL_PDF, "peer-reviewed reversal prior; not a market input"),
    ]
    entries: list[dict[str, Any]] = []
    for path, role in paths:
        if not path.exists():
            raise RuntimeError(f"missing source identity: {path}")
        entries.append({
            "path": str(path), "bytes": path.stat().st_size,
            "sha256": sha256_file(path), "role": role,
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
            "strategy_id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT", "version": "1.0.1",
            "instrument": "BTCUSDT-PERP",
        },
        "research_kind": "STRATEGY_CANDIDATE",
        "question": (
            "Does the externally-prioritized high-volatility concentration of medium-horizon crypto reversal "
            "qualify a fixed-target RV28-high-half/MOM70-bottom30 0.25x LONG 7d plan after retail costs, "
            "funding, hurdle, conditional/simple baselines, robustness, risk and sequential 2024-2026Q2 evidence?"
        ),
        "known_exposure": (
            "Q17 unconditional MOM70 2022-2023 is DOES_NOT_SUPPORT. High-vol conditioning was externally "
            "specified before Q17 outcome and has not been computed on 2024. External literature overlaps "
            "2024-2026Q1; only 2026Q2 is a short post-paper slice."
        ),
        "family_stop_rule": (
            "If this fixed high-volatility condition fails, do not search size, volatility cutoff, formation "
            "window, symbol or direction neighbors in the medium-horizon reversal family."
        ),
        "configuration": CONFIG, "stages": STAGES, "fetch_stage": FETCH_STAGE,
        "symbols": SYMBOLS, "categories": CATEGORY_MEMBERS,
        "selection_scope": {"selectable_primary_configurations": 1, "computed_columns": 9},
        "stage_open_rule": "development -> evaluation -> confirmation fetch/analyze",
        "frozen_file_sha256": {name: sha256_file(HERE / name) for name in FROZEN_FILES},
        "source_reuse_digest": read_json(HERE / "source_reuse_manifest.json")["content_digest"],
        "environment": {
            "python": platform.python_version(), "numpy": np.__version__,
            "pandas": pd.__version__, "vectorbt": vbt.__version__,
        },
        "confirmation_cache_root": str(CACHE_ROOT),
        "allowed_after_checkpoint": (
            "Create deterministic stage artifacts and, only after evaluation PASS, fetch the frozen public "
            "confirmation range. Implementation-only fixes require amendments; no economic-rule changes."
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
    if (
        canonical_digest(reuse) != reuse.get("content_digest")
        or reuse["content_digest"] != checkpoint["source_reuse_digest"]
    ):
        raise RuntimeError("source reuse identity mismatch")
    for item in reuse["entries"]:
        source = Path(item["path"])
        if (
            not source.exists() or source.stat().st_size != int(item["bytes"])
            or sha256_file(source) != item["sha256"]
        ):
            raise RuntimeError(f"source changed: {source}")
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
        raise RuntimeError("development/evaluation reuse frozen public manifests; only confirmation is fetchable")
    stage_authorized(args.stage)
    manifest_path = HERE / "source_manifest_confirmation.json"
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        if canonical_digest(manifest) != manifest.get("content_digest"):
            raise RuntimeError("existing confirmation manifest digest mismatch")
        print(json.dumps({"manifest": str(manifest_path), "digest": manifest["content_digest"], "reused": True}))
        return
    engine = load_module(DATA_ENGINE, "halpha_highvol_loser_fetch")
    engine.CACHE_ROOT = CACHE_ROOT
    engine.HERE = HERE
    engine.SYMBOLS = SYMBOLS
    engine.TARGET_SYMBOLS = SYMBOLS
    engine.SYMBOL_TO_CATEGORY = SYMBOL_TO_CATEGORY
    engine.STAGES = FETCH_STAGE
    spec = FETCH_STAGE["confirmation"]
    kline_start = pd.Timestamp(spec["fetch_start"])
    kline_end = pd.Timestamp(spec["end_exclusive"]) + pd.Timedelta(days=1)
    archives = engine.fetch_target_archives("confirmation")
    manifest: dict[str, Any] = {
        "accessed_at_utc": iso_now(), "stage": "confirmation",
        "checkpoint_digest": checkpoint["content_digest"],
        "source": "Binance public USD-M REST and official monthly archives; no credentials",
        "periods": {
            "kline_start": str(kline_start), "kline_end_exclusive": str(kline_end),
            "funding_start": spec["start"], "funding_end_exclusive": spec["end_exclusive"],
        },
        "symbols": {},
    }
    for number, symbol in enumerate(SYMBOLS, start=1):
        root = CACHE_ROOT / "confirmation" / symbol / "raw_highvol_loser"
        manifest["symbols"][symbol] = {
            "category": SYMBOL_TO_CATEGORY[symbol],
            "kline_pages": engine.fetch_pages(
                "/fapi/v1/klines", {"symbol": symbol, "interval": "1d"}, "openTime", 1500,
                kline_start, kline_end, root / "klines",
            ),
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
    parent = configure_parent()
    if stage == "development":
        bars, funding = parent.load_source("evaluation")
        return bars, funding, {"overlap_rows": 0, "overlap_mismatch_rows": 0}
    if stage == "evaluation":
        return parent.load_stage("confirmation")
    manifest = HERE / "source_manifest_confirmation.json"
    if not manifest.exists():
        raise RuntimeError("confirmation manifest missing; run authorized fetch first")
    item = read_json(manifest)
    if canonical_digest(item) != item.get("content_digest"):
        raise RuntimeError("confirmation manifest digest mismatch")
    engine = load_module(DATA_ENGINE, "halpha_highvol_loser_load_confirmation")
    engine.HERE = HERE
    bars: dict[str, pd.DataFrame] = {}
    funding: dict[str, pd.DataFrame] = {}
    for symbol in SYMBOLS:
        bars[symbol], funding[symbol] = engine.load_symbol("confirmation", symbol)
    return bars, funding, {"overlap_rows": 0, "overlap_mismatch_rows": 0}


def stage_entries(stage: str) -> pd.DatetimeIndex:
    start, end = map(pd.Timestamp, STAGES[stage])
    return pd.date_range(start, end, freq="W-MON", inclusive="left")


def feature_frame(frame: pd.DataFrame) -> pd.DataFrame:
    calendar = pd.date_range(frame.index.min(), frame.index.max(), freq="1D")
    frame = frame.reindex(calendar)
    output = pd.DataFrame(index=frame.index)
    log_return = np.log(frame["close"] / frame["close"].shift(1))
    for days in (21, 28, 42):
        output[f"rv{days}"] = log_return.rolling(days, min_periods=days).std(ddof=1) * math.sqrt(365.0)
    for days in (56, 70):
        output[f"mom{days}"] = frame["close"] / frame["close"].shift(days) - 1.0
    output["median_quote_volume_30d"] = frame["quote_volume"].rolling(30, min_periods=30).median()
    required = frame[["open", "high", "low", "close", "quote_volume"]].notna().all(axis=1)
    output["complete_85d"] = required.rolling(85, min_periods=85).sum().eq(85)
    return output.replace([np.inf, -np.inf], np.nan)


def command_prepare(args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    stage_authorized(args.stage)
    bars, funding, metadata = load_stage(args.stage)
    parent_quality = None
    if args.stage == "development":
        parent_quality = read_json(DEV_SOURCE / "data_quality_development.json")
    elif args.stage == "evaluation":
        parent_quality = read_json(EVAL_SOURCE / "data_quality_evaluation.json")
    status = (parent_quality is None or parent_quality.get("status") == "PASS")
    status = status and metadata["overlap_mismatch_rows"] == 0
    entries = stage_entries(args.stage)
    first_decision = entries[0] - pd.Timedelta(days=1)
    required_start = first_decision - pd.Timedelta(days=84)
    required_end = entries[-1] + pd.Timedelta(days=7)
    expected = pd.date_range(required_start, required_end, freq="1D")
    per_symbol: dict[str, Any] = {}
    for symbol in SYMBOLS:
        subset = bars[symbol][
            (bars[symbol].index >= required_start) & (bars[symbol].index <= required_end)
        ]
        missing_days = int(len(expected.difference(subset.index)))
        invalid_ohlc = int((
            (subset[["open", "high", "low", "close"]] <= 0).any(axis=1)
            | (subset["high"] < subset[["open", "close"]].max(axis=1))
            | (subset["low"] > subset[["open", "close"]].min(axis=1))
        ).sum())
        invalid_volume = int((subset[["volume", "quote_volume"]] < 0).any(axis=1).sum())
        rates = funding[symbol][
            (funding[symbol].index > entries[0]) & (funding[symbol].index <= required_end)
        ]
        max_gap = (
            float(rates.index.to_series().diff().dt.total_seconds().max() / 3600.0)
            if len(rates) > 1 else math.inf
        )
        missing_marks = int(rates["markPrice"].isna().sum())
        item_pass = invalid_ohlc == 0 and invalid_volume == 0 and len(rates) > 0 and max_gap <= 24.0
        status = status and item_pass
        per_symbol[symbol] = {
            "daily_rows": int(len(subset)), "missing_days": missing_days,
            "invalid_ohlc_rows": invalid_ohlc, "invalid_volume_rows": invalid_volume,
            "funding_rows": int(len(rates)), "missing_mark_rows": missing_marks,
            "max_funding_gap_hours": None if not math.isfinite(max_gap) else max_gap,
            "source_integrity": "PASS" if item_pass else "FAIL",
        }
    features = {symbol: feature_frame(frame) for symbol, frame in bars.items()}
    decision_counts: dict[str, int] = {}
    for entry in entries:
        decision, exit_time = entry - pd.Timedelta(days=1), entry + pd.Timedelta(days=7)
        count = 0
        for symbol in SYMBOLS:
            indicator = features[symbol]
            if (
                decision in indicator.index and bool(indicator.at[decision, "complete_85d"])
                and entry in bars[symbol].index and exit_time in bars[symbol].index
            ):
                count += 1
        decision_counts[entry.isoformat()] = count
    below = {
        key: value for key, value in decision_counts.items()
        if value < int(CONFIG["minimum_rankable_symbols"])
    }
    status = status and not below
    payload = {
        "checked_at_utc": iso_now(), "stage": args.stage,
        "status": "PASS" if status else "FAIL", "checkpoint_digest": checkpoint["content_digest"],
        "required_daily_range_inclusive": [required_start.isoformat(), required_end.isoformat()],
        "source_overlap": metadata,
        "decision_input_availability": {
            "minimum_complete": min(decision_counts.values()),
            "maximum_complete": max(decision_counts.values()), "dates_below_20": below,
        },
        "symbols": per_symbol,
        "source_manifest_sha256": (
            sha256_file(HERE / "source_manifest_confirmation.json")
            if args.stage == "confirmation" else
            sha256_file(DEV_SOURCE / "source_manifest_development.json")
            if args.stage == "development" else
            sha256_file(EVAL_SOURCE / "source_manifest_evaluation.json")
        ),
        "rule": (
            "Calendar gaps are never imputed; a target is NO_ACTION while its 85-day completeness window "
            "contains a gap. Every decision must retain at least 20 complete targets."
        ),
    }
    write_json(HERE / f"data_quality_{args.stage}.json", payload, digest=True)
    print(json.dumps({"stage": args.stage, "status": payload["status"], "symbols": len(SYMBOLS)}))


def build_panel(bars: dict[str, pd.DataFrame], stage: str) -> pd.DataFrame:
    features = {symbol: feature_frame(frame) for symbol, frame in bars.items()}
    rows: list[dict[str, Any]] = []
    for entry in stage_entries(stage):
        decision, exit_time = entry - pd.Timedelta(days=1), entry + pd.Timedelta(days=7)
        candidates: list[dict[str, Any]] = []
        for symbol in SYMBOLS:
            feature = features[symbol]
            if (
                decision not in feature.index or entry not in bars[symbol].index
                or exit_time not in bars[symbol].index
            ):
                continue
            values = feature.loc[
                decision, ["rv21", "rv28", "rv42", "mom56", "mom70", "median_quote_volume_30d", "complete_85d"]
            ]
            if (
                values.isna().any() or not bool(values["complete_85d"])
                or float(values["median_quote_volume_30d"]) < float(CONFIG["minimum_median_quote_volume_30d"])
            ):
                continue
            candidates.append({
                "entry_time": entry, "decision_time": decision, "exit_time": exit_time,
                "symbol": symbol, "entry_price": float(bars[symbol].at[entry, "open"]),
                "exit_price": float(bars[symbol].at[exit_time, "open"]),
                **{name: float(values[name]) for name in ("rv21", "rv28", "rv42", "mom56", "mom70")},
            })
        if len(candidates) < int(CONFIG["minimum_rankable_symbols"]):
            continue
        for item in candidates:
            item["eligible_count"] = len(candidates)
        rows.extend(candidates)
    if not rows:
        raise RuntimeError(f"panel empty: {stage}")
    return pd.DataFrame(rows).sort_values(["entry_time", "symbol"]).reset_index(drop=True)


def select_variant(panel: pd.DataFrame, variant: str) -> dict[pd.Timestamp, pd.DataFrame]:
    output: dict[pd.Timestamp, pd.DataFrame] = {}
    for entry, raw in panel.groupby("entry_time", sort=True):
        week = raw.copy()
        vol_column = {"rv21": "rv21", "rv42": "rv42"}.get(variant, "rv28")
        high_count = int(math.ceil(len(week) * float(CONFIG["high_volatility_fraction"])))
        low_count = len(week) - high_count
        high = week.sort_values([vol_column, "symbol"], ascending=[False, True]).head(high_count)
        low = week.sort_values([vol_column, "symbol"], ascending=[True, True]).head(low_count)
        momentum_column = "mom56" if variant == "mom56" else "mom70"
        if variant == "market_long":
            selected = week.sort_values("symbol")
            selected["score"] = selected["mom70"]
        elif variant == "unconditional_loser":
            count = int(math.ceil(len(week) * float(CONFIG["loser_fraction"])))
            selected = week.sort_values(["mom70", "symbol"]).head(count)
            selected["score"] = selected["mom70"]
        elif variant == "lowvol_loser":
            count = int(math.ceil(len(low) * float(CONFIG["loser_fraction"])))
            selected = low.sort_values(["mom70", "symbol"]).head(count)
            selected["score"] = selected["mom70"]
        elif variant == "highvol_scheduled":
            selected = high.sort_values("symbol")
            selected["score"] = selected["mom70"]
        elif variant == "highvol_winner":
            count = int(math.ceil(len(high) * float(CONFIG["loser_fraction"])))
            selected = high.sort_values(["mom70", "symbol"], ascending=[False, True]).head(count)
            selected["score"] = selected["mom70"]
        else:
            count = int(math.ceil(len(high) * float(CONFIG["loser_fraction"])))
            selected = high.sort_values([momentum_column, "symbol"]).head(count)
            selected["score"] = selected[momentum_column]
        selected = selected.copy()
        selected["intended_rank"] = np.arange(1, len(selected) + 1)
        output[pd.Timestamp(entry)] = selected
    return output


def attach_intended_rank(raw: pd.DataFrame, selections: dict[pd.Timestamp, pd.DataFrame]) -> pd.DataFrame:
    rank_map = {
        (pd.Timestamp(entry), str(row["symbol"])): int(row["intended_rank"])
        for entry, frame in selections.items() for _, row in frame.iterrows()
    }
    output = raw.copy()
    output["selection_rank"] = [
        rank_map[(pd.Timestamp(entry), str(symbol))]
        for entry, symbol in zip(output["entry_time"], output["symbol"], strict=True)
    ]
    return output


def command_self_test(_args: argparse.Namespace) -> None:
    index = pd.date_range("2025-01-01T00:00:00Z", periods=100, freq="1D")
    close = pd.Series(np.exp(np.linspace(0.0, 0.4, 100)), index=index)
    frame = pd.DataFrame({
        "open": close, "high": close * 1.01, "low": close * 0.99,
        "close": close, "quote_volume": 20_000_000.0,
    }, index=index)
    features = feature_frame(frame)
    expected_mom = float(close.iloc[-1] / close.iloc[-71] - 1.0)
    if not math.isclose(float(features["mom70"].iloc[-1]), expected_mom, abs_tol=1e-14):
        raise RuntimeError("MOM70 mismatch")
    returns = np.log(close / close.shift(1)).iloc[-28:]
    expected_rv = float(returns.std(ddof=1) * math.sqrt(365.0))
    if not math.isclose(float(features["rv28"].iloc[-1]), expected_rv, abs_tol=1e-14):
        raise RuntimeError("RV28 mismatch")
    parent = configure_parent()
    sample = pd.DataFrame([{
        "trade_id": "test", "entry_price": 100.0, "exit_price": 110.0,
        "quantity_per_unit_plan_capital": 0.0025,
    }])
    vector = float(parent.vectorbt_long_returns(sample, 0.0006, 0.0010)[0])
    manual = float(parent.manual_long_return(sample.iloc[0], 0.0006, 0.0010))
    if not math.isclose(vector, manual, abs_tol=1e-12):
        raise RuntimeError("VectorBT/manual mismatch")
    print(json.dumps({
        "status": "PASS", "mom70": expected_mom, "rv28": expected_rv,
        "vectorbt_manual_reconciliation": vector - manual,
    }))


def command_analyze(args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    stage_authorized(args.stage)
    dq = HERE / f"data_quality_{args.stage}.json"
    if not dq.exists() or read_json(dq).get("status") != "PASS":
        raise RuntimeError("data quality is not PASS")
    bars, funding, _ = load_stage(args.stage)
    panel = build_panel(bars, args.stage)
    parent = configure_parent()
    variants = ["main", *CONFIG["diagnostics"]]
    selections = {name: select_variant(panel, name) for name in variants}
    trades: dict[str, pd.DataFrame] = {}
    counts: dict[str, dict[str, int]] = {}
    for name in variants:
        cooldown = name != "market_long"
        raw, counts[name] = parent.make_long_trades(
            selections[name], funding, args.stage, name, mode="all", cooldown=cooldown,
        )
        raw = attach_intended_rank(raw, selections[name])
        trades[name] = parent.attach_returns(raw)
    csv_hashes: dict[str, str] = {}
    for name, frame in trades.items():
        path = HERE / f"{args.stage}_{name}_trades.csv"
        frame.to_csv(path, index=False, date_format="%Y-%m-%dT%H:%M:%S%z")
        csv_hashes[path.name] = sha256_file(path)
    summaries = {name: parent.summarize(frame, args.stage) for name, frame in trades.items()}
    comparisons = {
        "base_vs_unconditional_loser": parent.compare_with_cash(trades["main"], trades["unconditional_loser"]),
        "base_vs_lowvol_loser": parent.compare_with_cash(trades["main"], trades["lowvol_loser"]),
        "base_vs_highvol_winner": parent.compare_with_cash(trades["main"], trades["highvol_winner"]),
        "base_vs_highvol_scheduled": parent.compare_with_cash(trades["main"], trades["highvol_scheduled"]),
        "stress_vs_unconditional_loser": parent.compare_with_cash(
            trades["main"], trades["unconditional_loser"], column="stress_net_return"
        ),
    }
    gross_main = parent.date_returns(trades["main"], "gross_long_return")
    gross_market = parent.date_returns(trades["market_long"], "gross_long_return").reindex(gross_main.index)
    if gross_market.isna().any():
        raise RuntimeError("market baseline missing main date")
    gross_excess = gross_main - gross_market
    comparisons["gross_vs_equal_weight_market_long"] = {
        "main_mean": float(gross_main.mean()), "market_mean": float(gross_market.mean()),
        "difference_mean": float(gross_excess.mean()),
        "difference_bootstrap_95pct": parent.block_bootstrap_mean_ci(gross_excess.to_numpy(float)),
    }
    payload = {
        "analyzed_at_utc": iso_now(), "stage": args.stage,
        "checkpoint_digest": checkpoint["content_digest"],
        "data_quality_digest": read_json(dq)["content_digest"],
        "panel_rows": int(len(panel)), "panel_weeks": int(panel["entry_time"].nunique()),
        "opportunity_counts": counts, "summaries": summaries,
        "comparisons": comparisons, "trade_csv_sha256": csv_hashes,
    }
    write_json(HERE / f"{args.stage}.json", payload, digest=True)
    evidence = read_json(HERE / f"{args.stage}.json")
    print(json.dumps({
        "stage": args.stage, "trades": summaries["main"]["trades"],
        "base_after_hurdle": summaries["main"]["scenarios"]["base"]["date_mean_after_hurdle"],
        "stress_after_hurdle": summaries["main"]["scenarios"]["stress"]["date_mean_after_hurdle"],
        "vs_unconditional": comparisons["base_vs_unconditional_loser"]["difference_mean"],
        "digest": evidence["content_digest"],
    }))


def stage_thresholds(stage: str) -> dict[str, float | int]:
    if stage == "confirmation":
        return {"dates": 10, "trades": 20, "symbols": 8, "categories": 3, "mdd": -0.10, "concentration": 0.40}
    return {"dates": 48, "trades": 120, "symbols": 15, "categories": 4, "mdd": -0.15, "concentration": 0.25}


def common_checks(stage: str, evidence: dict[str, Any]) -> tuple[dict[str, bool], dict[str, Any]]:
    main = evidence["summaries"]["main"]
    base, stress = main["scenarios"]["base"], main["scenarios"]["stress"]
    counts = evidence["opportunity_counts"]["main"]
    exclusions = counts["excluded_missing_marks"] + counts["excluded_missing_funding"]
    excluded_fraction = exclusions / max(1, counts["planned"])
    positive_symbols = sum(item["base_mean_after_hurdle"] > 0 for item in main["by_symbol"].values())
    positive_categories = sum(item["base_mean_after_hurdle"] > 0 for item in main["by_category"].values())
    neighbor_positive = sum(
        evidence["summaries"][name]["scenarios"]["stress"]["date_mean_after_hurdle"] >= 0
        for name in ("rv21", "rv42", "mom56")
    )
    limits = stage_thresholds(stage)
    checks = {
        "data_quality_pass": read_json(HERE / f"data_quality_{stage}.json")["status"] == "PASS",
        "minimum_trades": main["trades"] >= limits["trades"],
        "minimum_entry_dates": main["entry_dates"] >= limits["dates"],
        "minimum_symbols": main["symbols"] >= limits["symbols"],
        "excluded_at_most_2pct": excluded_fraction <= 0.02,
        "base_after_hurdle_positive": base["date_mean_after_hurdle"] > 0,
        "stress_after_hurdle_positive": stress["date_mean_after_hurdle"] > 0,
        "date_drawdown_above_limit": base["date_portfolio_max_drawdown"] > limits["mdd"],
        "worst_symbol_drawdown_above_minus_30pct": main["worst_symbol_base_max_drawdown"] > -0.30,
        "base_beats_unconditional_loser": (
            evidence["comparisons"]["base_vs_unconditional_loser"]["difference_mean"] > 0
        ),
        "base_beats_highvol_scheduled": (
            evidence["comparisons"]["base_vs_highvol_scheduled"]["difference_mean"] > 0
        ),
        "gross_market_excess_positive": (
            evidence["comparisons"]["gross_vs_equal_weight_market_long"]["difference_mean"] > 0
        ),
        "at_least_two_of_three_neighbors_stress_nonnegative": neighbor_positive >= 2,
        "at_least_half_symbols_positive": positive_symbols / max(1, main["symbols"]) >= 0.5,
        "minimum_positive_categories": positive_categories >= limits["categories"],
        "positive_pnl_concentration_below_limit": (
            main["largest_positive_pnl_share"] <= limits["concentration"]
        ),
        "vectorbt_manual_reconciliation": main["maximum_vectorbt_reconciliation_error"] <= 1e-10,
    }
    if stage != "confirmation":
        checks.update({
            "both_halves_base_positive": all(
                item["dates"] > 0 and item["mean_after_hurdle"] > 0 for item in main["by_half"].values()
            ),
            "base_beats_lowvol_loser": evidence["comparisons"]["base_vs_lowvol_loser"]["difference_mean"] > 0,
            "base_beats_highvol_winner": evidence["comparisons"]["base_vs_highvol_winner"]["difference_mean"] > 0,
        })
    return checks, {
        "excluded_fraction": excluded_fraction, "positive_symbols": positive_symbols,
        "positive_categories": positive_categories, "neighbor_positive": neighbor_positive,
    }


def pooled_development_evaluation() -> dict[str, Any]:
    parent = configure_parent()
    main = pd.concat([
        pd.read_csv(HERE / f"{stage}_main_trades.csv", parse_dates=["entry_time"])
        for stage in ("development", "evaluation")
    ], ignore_index=True)
    unconditional = pd.concat([
        pd.read_csv(HERE / f"{stage}_unconditional_loser_trades.csv", parse_dates=["entry_time"])
        for stage in ("development", "evaluation")
    ], ignore_index=True)
    market = pd.concat([
        pd.read_csv(HERE / f"{stage}_market_long_trades.csv", parse_dates=["entry_time"])
        for stage in ("development", "evaluation")
    ], ignore_index=True)
    stress = parent.date_returns(main, "stress_net_return") - parent.hurdle_per_week()
    stress_unconditional = parent.date_returns(unconditional, "stress_net_return").reindex(stress.index, fill_value=0.0)
    stress_increment = parent.date_returns(main, "stress_net_return") - stress_unconditional
    gross_main = parent.date_returns(main, "gross_long_return")
    gross_market = parent.date_returns(market, "gross_long_return").reindex(gross_main.index)
    gross_excess = gross_main - gross_market
    return {
        "entry_dates": int(len(stress)),
        "stress_after_hurdle_mean": float(stress.mean()),
        "stress_after_hurdle_bootstrap_95pct": parent.block_bootstrap_mean_ci(stress.to_numpy(float)),
        "stress_increment_vs_unconditional_mean": float(stress_increment.mean()),
        "stress_increment_vs_unconditional_bootstrap_95pct": (
            parent.block_bootstrap_mean_ci(stress_increment.to_numpy(float))
        ),
        "gross_market_excess_mean": float(gross_excess.mean()),
        "gross_market_excess_bootstrap_95pct": parent.block_bootstrap_mean_ci(gross_excess.to_numpy(float)),
    }


def conclusion_for_failure(evidence: dict[str, Any]) -> str:
    main = evidence["summaries"]["main"]
    return "DOES_NOT_SUPPORT" if (
        main["scenarios"]["base"]["date_mean_after_hurdle"] <= 0
        or main["scenarios"]["stress"]["date_mean_after_hurdle"] <= 0
        or evidence["comparisons"]["base_vs_unconditional_loser"]["difference_mean"] <= 0
        or evidence["comparisons"]["base_vs_highvol_scheduled"]["difference_mean"] <= 0
        or evidence["comparisons"]["gross_vs_equal_weight_market_long"]["difference_mean"] <= 0
    ) else "INSUFFICIENT_EVIDENCE"


def write_failure(stage: str, evidence: dict[str, Any], gate: dict[str, Any]) -> None:
    conclusion = conclusion_for_failure(evidence)
    main = evidence["summaries"]["main"]
    base, stress = main["scenarios"]["base"], main["scenarios"]["stress"]
    result = {
        "created_at_utc": iso_now(), "conclusion": conclusion, "failed_stage": stage,
        "failed_checks": gate["failed"], "handoff_generated": False,
        "later_stages": "NOT_OPENED_BY_SEQUENTIAL_GATE",
        "family_disposition": "CLOSED_NO_FURTHER_MEDIUM_HORIZON_REVERSAL_CONDITION_SEARCH",
        "summary": {
            "trades": main["trades"], "entry_dates": main["entry_dates"], "symbols": main["symbols"],
            "base_after_hurdle": base["date_mean_after_hurdle"],
            "stress_after_hurdle": stress["date_mean_after_hurdle"],
            "stress_bootstrap_95pct": stress["date_mean_after_hurdle_bootstrap_95pct"],
            "base_max_drawdown": base["date_portfolio_max_drawdown"],
            "base_vs_unconditional": evidence["comparisons"]["base_vs_unconditional_loser"],
            "base_vs_lowvol": evidence["comparisons"]["base_vs_lowvol_loser"],
            "base_vs_highvol_scheduled": evidence["comparisons"]["base_vs_highvol_scheduled"],
            "base_vs_highvol_winner": evidence["comparisons"]["base_vs_highvol_winner"],
            "gross_vs_market": evidence["comparisons"]["gross_vs_equal_weight_market_long"],
            "largest_positive_pnl_share": main["largest_positive_pnl_share"],
        },
    }
    write_json(HERE / "results.json", result, digest=True)
    text = f"""# 结果：高波动中期输家 one-shot LONG

## 结论

`{conclusion}`

固定的 RV28 高半区、MOM70 底部 30%、`0.25x LONG / 7d` 在 `{stage}` 未通过预注册门。后期不打开、handoff 不生成；按 family stop rule，不再搜索中期反转的 size、波动 cutoff、窗口、币种或方向邻域。

## 关键证据

- 交易 / entry dates / 目标：`{main['trades']} / {main['entry_dates']} / {main['symbols']}`
- base / stress 扣全资金门槛周日期均值：`{base['date_mean_after_hurdle']:.6%} / {stress['date_mean_after_hurdle']:.6%}`
- stress 95% 区间：`[{stress['date_mean_after_hurdle_bootstrap_95pct'][0]:.6%}, {stress['date_mean_after_hurdle_bootstrap_95pct'][1]:.6%}]`
- base 相对无条件输家 / 低波输家 / 高波无筛选 / 高波赢家：`{evidence['comparisons']['base_vs_unconditional_loser']['difference_mean']:.6%} / {evidence['comparisons']['base_vs_lowvol_loser']['difference_mean']:.6%} / {evidence['comparisons']['base_vs_highvol_scheduled']['difference_mean']:.6%} / {evidence['comparisons']['base_vs_highvol_winner']['difference_mean']:.6%}`
- gross 市场超额：`{evidence['comparisons']['gross_vs_equal_weight_market_long']['difference_mean']:.6%}`
- base MDD：`{base['date_portfolio_max_drawdown']:.6%}`
- 失败门：`{', '.join(gate['failed'])}`

这只判断当前幸存永续、固定单目标和零售成本转换；不推翻论文的 spot long-short 多币组合，也不证明其他数据机制不存在。
"""
    (HERE / "result.md").write_text(text, encoding="utf-8")


def write_success(evidence: dict[str, Any], gate: dict[str, Any]) -> None:
    checkpoint = read_json(HERE / "checkpoint.json")
    handoff = {
        "created_at_utc": iso_now(), "status": "RESEARCH_CANDIDATE_FOR_CORE_QUALIFICATION_ONLY",
        "authorization": "No product change, capital allocation, live trading or profit guarantee",
        "identity": {"strategy_id": CONFIG["strategy_id"], "version": "1.0.0-research"},
        "baseline_commit": checkpoint["baseline_commit"], "direction": "LONG_ONLY",
        "instrument_contract": "Owner fixes one frozen target; strategy returns ELIGIBLE or NO_ACTION only",
        "timeframe": "completed UTC 1d bars; Sunday decision; following Monday action boundary",
        "warmup": "85 contiguous UTC daily OHLCV bars for all rankable targets",
        "signal": {
            "rv28": "sample std of 28 completed daily log returns * sqrt(365)",
            "high_volatility_group": "top ceil(50% of rankable targets), symbol ascending tie-break",
            "mom70": "close[t] / close[t-70 calendar days] - 1",
            "eligible": "bottom ceil(30% of high-volatility group), symbol ascending tie-break",
            "minimum_rankable": 20, "volume_floor": "30d median quote volume >= 10m USDT",
        },
        "action": {
            "entry": "first executable price after following UTC Monday boundary",
            "amount": "0.25 * owner-approved plan amount", "exit": "7 calendar days",
        },
        "protection": {
            "notional_cap": "0.25x", "single_position": True, "pyramiding": False,
            "cooldown": "one full UTC day after exit", "intraday_stop": None,
        },
        "unknown_no_action": [
            "universe mismatch", "missing/stale/incomplete 85d data", "fewer than 20 rankable",
            "target not selected", "direction not LONG", "cooldown active", "execution boundary unknown",
        ],
        "decision_trace_fields": [
            "strategy_id", "universe_sha256", "decision_time", "owner_symbol", "rankable_symbols",
            "rv28", "rv_rank", "high_group_count", "mom70", "mom_rank_within_high",
            "selection_count", "cooldown", "decision", "reason",
        ],
        "cost_proxy": CONFIG["costs"],
        "evidence": {
            "development": read_json(HERE / "development.json")["content_digest"],
            "evaluation": read_json(HERE / "evaluation.json")["content_digest"],
            "confirmation": evidence["content_digest"], "confirmation_gate": gate["content_digest"],
            "pooled_2024_2025": read_json(HERE / "evaluation_gate.json")["pooled"],
        },
        "limits": [
            "current-survivor fixed list", "daily execution proxy; no L2 fills", "short post-paper Q2 slice",
            "external literature overlaps 2024-2026Q1", "no point-in-time delisting/size universe",
            "backtest cannot establish future or long-term profitability",
        ],
    }
    write_json(HERE / "handoff.json", handoff, digest=True)
    result = {
        "created_at_utc": iso_now(), "conclusion": "SUPPORTS_WITHIN_SCOPE",
        "stage_gates": {stage: "PASS" for stage in STAGES}, "handoff_generated": True,
        "handoff_digest": read_json(HERE / "handoff.json")["content_digest"],
        "scope_warning": "Core qualification candidate only; not alpha proof or live-trading authorization",
    }
    write_json(HERE / "results.json", result, digest=True)
    (HERE / "result.md").write_text(
        "# 结果\n\n`SUPPORTS_WITHIN_SCOPE`\n\n三阶段与合并门通过；见 `results.json` 和 `handoff.json`。这不证明长期盈利，也不授权产品或实盘。\n",
        encoding="utf-8",
    )


def command_gate(args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    stage_authorized(args.stage)
    evidence = read_json(HERE / f"{args.stage}.json")
    checks, diagnostics = common_checks(args.stage, evidence)
    pooled = None
    if args.stage == "evaluation":
        pooled = pooled_development_evaluation()
        checks.update({
            "pooled_stress_after_hurdle_positive": pooled["stress_after_hurdle_mean"] > 0,
            "pooled_stress_after_hurdle_ci_lower_positive": pooled["stress_after_hurdle_bootstrap_95pct"][0] > 0,
            "pooled_stress_increment_vs_unconditional_positive": (
                pooled["stress_increment_vs_unconditional_mean"] > 0
            ),
            "pooled_stress_increment_vs_unconditional_ci_lower_positive": (
                pooled["stress_increment_vs_unconditional_bootstrap_95pct"][0] > 0
            ),
            "pooled_gross_market_excess_positive": pooled["gross_market_excess_mean"] > 0,
            "pooled_gross_market_excess_ci_lower_positive": (
                pooled["gross_market_excess_bootstrap_95pct"][0] > 0
            ),
        })
    status = "PASS" if all(checks.values()) else "FAIL"
    gate = {
        "created_at_utc": iso_now(), "stage": args.stage, "status": status,
        "checkpoint_digest": checkpoint["content_digest"], "evidence_digest": evidence["content_digest"],
        "checks": checks, "failed": [name for name, passed in checks.items() if not passed],
        "diagnostics": diagnostics,
    }
    if pooled is not None:
        gate["pooled"] = pooled
    write_json(HERE / f"{args.stage}_gate.json", gate, digest=True)
    written = read_json(HERE / f"{args.stage}_gate.json")
    if status == "FAIL":
        write_failure(args.stage, evidence, written)
    elif args.stage == "confirmation":
        write_success(evidence, written)
    print(json.dumps({"stage": args.stage, "status": status, "failed": written["failed"]}))


def command_validate(_args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    required = ["source_reuse_manifest.json", "checkpoint.json"]
    opened: list[str] = []
    for stage in STAGES:
        if not (HERE / f"{stage}_gate.json").exists():
            break
        opened.append(stage)
        required.extend([f"data_quality_{stage}.json", f"{stage}.json", f"{stage}_gate.json"])
    if not opened:
        raise RuntimeError("no completed stage")
    terminal = read_json(HERE / f"{opened[-1]}_gate.json")["status"] == "FAIL" or opened[-1] == "confirmation"
    if terminal:
        required.append("results.json")
    if (HERE / "handoff.json").exists():
        required.append("handoff.json")
    for name in required:
        payload = read_json(HERE / name)
        if canonical_digest(payload) != payload.get("content_digest"):
            raise RuntimeError(f"digest mismatch: {name}")
    csv_checked = 0
    for stage in opened:
        evidence = read_json(HERE / f"{stage}.json")
        for name, expected in evidence["trade_csv_sha256"].items():
            if sha256_file(HERE / name) != expected:
                raise RuntimeError(f"CSV mismatch: {name}")
            csv_checked += 1
    for index, stage in enumerate(opened):
        if read_json(HERE / f"{stage}_gate.json")["status"] == "FAIL":
            for later in list(STAGES)[index + 1:]:
                if list(HERE.glob(f"{later}*")):
                    raise RuntimeError(f"later artifact after {stage} failure")
            if (HERE / "handoff.json").exists():
                raise RuntimeError("handoff after failed gate")
            break
    result = read_json(HERE / "results.json") if (HERE / "results.json").exists() else {}
    payload = {
        "validated_at_utc": iso_now(), "status": "PASS",
        "checkpoint_digest": checkpoint["content_digest"], "opened_stages": opened,
        "json_digest_files_checked": len(required), "trade_csv_files_checked": csv_checked,
        "conclusion": result.get("conclusion"), "handoff_generated": (HERE / "handoff.json").exists(),
    }
    write_json(HERE / "validation.json", payload, digest=True)
    print(json.dumps(payload))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("checkpoint").set_defaults(func=command_checkpoint)
    sub.add_parser("self-test").set_defaults(func=command_self_test)
    fetch = sub.add_parser("fetch")
    fetch.add_argument("--stage", choices=STAGES, required=True)
    fetch.set_defaults(func=command_fetch)
    for name, func in (("prepare", command_prepare), ("analyze", command_analyze), ("gate", command_gate)):
        item = sub.add_parser(name)
        item.add_argument("--stage", choices=STAGES, required=True)
        item.set_defaults(func=func)
    sub.add_parser("validate").set_defaults(func=command_validate)
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    args.func(args)
