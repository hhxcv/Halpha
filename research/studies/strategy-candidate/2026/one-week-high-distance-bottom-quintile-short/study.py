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


HERE = Path(__file__).resolve().parent
PARENT_DIR = HERE.parent / "risk-adjusted-two-week-momentum-one-shot-long"
PARENT_STUDY = PARENT_DIR / "study.py"
EXTERNAL_PDF = Path(
    "D:/projects/Codex/CodexHome/research-data/halpha/_sources/"
    "impact-size-volume-crypto-momentum-reversal-ffa-2023.pdf"
)
SYMBOLS = [
    "1000XECUSDT", "AAVEUSDT", "AVAXUSDT", "BCHUSDT", "BNBUSDT", "CRVUSDT",
    "DASHUSDT", "ENSUSDT", "ETCUSDT", "HBARUSDT", "KAVAUSDT", "LINKUSDT",
    "LTCUSDT", "NEARUSDT", "RUNEUSDT", "SNXUSDT", "SOLUSDT", "TRXUSDT",
    "UNIUSDT", "VETUSDT", "XLMUSDT", "XMRUSDT", "XRPUSDT", "ZECUSDT", "ZILUSDT",
]
STAGES = {
    "development": ("2023-01-02T00:00:00Z", "2024-01-01T00:00:00Z"),
    "evaluation": ("2024-01-01T00:00:00Z", "2025-01-01T00:00:00Z"),
    "confirmation": ("2025-01-01T00:00:00Z", "2026-07-01T00:00:00Z"),
}
CONFIG = {
    "strategy_id": "RESEARCH_HMOM7_BOTTOM_QUINTILE_WEEKLY_ONE_SHOT_SHORT_0P5X_V1",
    "direction": "SHORT_ONLY",
    "hold_days": 7,
    "notional_fraction": 0.5,
    "bottom_fraction": 0.2,
    "top_fraction": 0.2,
    "minimum_rankable_symbols": 20,
    "minimum_median_quote_volume_30d": 10_000_000.0,
    "annual_capital_hurdle": 0.04,
    "cooldown_full_days": 1,
    "costs": {
        "favorable": {"fee_per_side": 0.0006, "slippage_per_side": 0.0, "funding_stress": False},
        "base": {"fee_per_side": 0.0006, "slippage_per_side": 0.0010, "funding_stress": False},
        "stress": {"fee_per_side": 0.0006, "slippage_per_side": 0.0020, "funding_stress": True},
    },
    "short_funding_stress": {"positive_benefit_multiplier": 0.5, "negative_cost_multiplier": 1.5},
    "bootstrap": {"block_weeks": 4, "repetitions": 5000, "seed": 20260722},
    "main": {"lookback_days": 7, "score": "log_close_over_rolling_intraday_high"},
    "diagnostics": ["hmom14", "hmom28", "bottom3", "mom7", "scheduled_short", "market_short"],
}
FROZEN_FILES = ["README.md", "preregistration.md", "sources.md", "study.py"]
EPHEMERAL_KEYS = {"created_at_utc", "validated_at_utc"}


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
        stable_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def write_json(path: Path, value: dict[str, Any], *, digest: bool = False) -> None:
    payload = dict(value)
    if digest:
        payload["content_digest"] = canonical_digest(payload)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_parent() -> Any:
    spec = importlib.util.spec_from_file_location("halpha_hmom_parent", PARENT_STUDY)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load reused research adapter")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def source_entries() -> list[dict[str, Any]]:
    paths = [
        PARENT_STUDY,
        PARENT_DIR / "checkpoint.json",
        PARENT_DIR / "amendment-001.json",
        PARENT_DIR / "amendment-002.json",
        PARENT_DIR / "source_reuse_manifest.json",
        PARENT_DIR / "data_quality_development.json",
        PARENT_DIR / "validation.json",
    ]
    entries: list[dict[str, Any]] = []
    for path in paths:
        if not path.exists():
            raise RuntimeError(f"missing reused source identity: {path}")
        entries.append({"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    if not EXTERNAL_PDF.exists():
        raise RuntimeError(f"missing public paper cache: {EXTERNAL_PDF}")
    entries.append({
        "path": str(EXTERNAL_PDF),
        "bytes": EXTERNAL_PDF.stat().st_size,
        "sha256": sha256_file(EXTERNAL_PDF),
        "url": "https://wp.ffu.vse.cz/pdfs/wps/2023/01/03.pdf",
        "role": "public prior-art formula and result identity; not a market input",
    })
    return entries


def command_checkpoint(_args: argparse.Namespace) -> None:
    if (HERE / "checkpoint.json").exists():
        checkpoint = ensure_checkpoint()
        print(json.dumps({"checkpoint": str(HERE / "checkpoint.json"), "digest": checkpoint["content_digest"]}))
        return
    parent = load_parent()
    parent.ensure_checkpoint()
    reuse = {"created_at_utc": iso_now(), "entries": source_entries()}
    write_json(HERE / "source_reuse_manifest.json", reuse, digest=True)
    payload = {
        "created_at_utc": iso_now(),
        "baseline_commit": "0bdfeffa616260cebd2d2188ddc8deb9e85c77f4",
        "formal_strategy": {
            "strategy_id": "ONE_SHOT_DONCHIAN_ATR_BREAKOUT",
            "version": "1.0.1",
            "instrument": "BTCUSDT-PERP",
        },
        "research_kind": "STRATEGY_CANDIDATE",
        "question": (
            "Does paper-defined one-week high-distance bottom-quintile selection qualify a fixed-target "
            "weekly one-shot perpetual SHORT after retail costs, funding, ordinary-momentum/market "
            "baselines, robustness, breadth and sequential time evidence?"
        ),
        "development_period": list(STAGES["development"]),
        "known_exposure": (
            "The same 2023 market paths were viewed by other questions; HMOM7 bottom-quintile SHORT "
            "rankings and plan outcomes were not viewed before this checkpoint."
        ),
        "selection_scope": {"selectable_primary_configurations": 1, "computed_columns": 7},
        "configuration": CONFIG,
        "symbols": SYMBOLS,
        "frozen_file_sha256": {name: sha256_file(HERE / name) for name in FROZEN_FILES},
        "source_reuse_digest": read_json(HERE / "source_reuse_manifest.json")["content_digest"],
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
        "allowed_after_checkpoint": (
            "Append attempts and create data/result artifacts. Economic rules may not change; "
            "implementation-only fixes require a numbered amendment before rerun."
        ),
    }
    write_json(HERE / "checkpoint.json", payload, digest=True)
    checkpoint = read_json(HERE / "checkpoint.json")
    print(json.dumps({"checkpoint": str(HERE / "checkpoint.json"), "digest": checkpoint["content_digest"]}))


def ensure_checkpoint() -> dict[str, Any]:
    path = HERE / "checkpoint.json"
    if not path.exists():
        raise RuntimeError("checkpoint missing")
    checkpoint = read_json(path)
    if canonical_digest(checkpoint) != checkpoint.get("content_digest"):
        raise RuntimeError("checkpoint digest mismatch")
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
            raise RuntimeError(f"frozen file changed after checkpoint: {name}")
    reuse = read_json(HERE / "source_reuse_manifest.json")
    if canonical_digest(reuse) != reuse.get("content_digest") or reuse["content_digest"] != checkpoint["source_reuse_digest"]:
        raise RuntimeError("source reuse manifest mismatch")
    for item in reuse["entries"]:
        source = Path(item["path"])
        if not source.exists() or source.stat().st_size != int(item["bytes"]) or sha256_file(source) != item["sha256"]:
            raise RuntimeError(f"reused source changed: {source}")
    parent = load_parent()
    parent.ensure_checkpoint()
    return checkpoint


def configure_base() -> Any:
    parent = load_parent()
    parent.CONFIG = CONFIG
    parent.STAGES = STAGES
    base = parent.configure_base()
    base.CONFIG = CONFIG
    base.STAGES = STAGES
    return base


def hmom_frame(frame: pd.DataFrame) -> pd.DataFrame:
    output = pd.DataFrame(index=frame.index)
    for days in (7, 14, 28):
        rolling_high = frame["high"].rolling(days, min_periods=days).max()
        output[f"hmom{days}"] = np.log(frame["close"] / rolling_high)
    output["mom7"] = frame["close"] / frame["close"].shift(7) - 1.0
    output["median_quote_volume_30d"] = frame["quote_volume"].rolling(30, min_periods=30).median()
    return output.replace([np.inf, -np.inf], np.nan)


def build_panel(bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
    indicators = {symbol: hmom_frame(frame) for symbol, frame in bars.items()}
    rows: list[dict[str, Any]] = []
    start, end = map(pd.Timestamp, STAGES["development"])
    for entry in pd.date_range(start, end, freq="W-MON", inclusive="left"):
        decision = entry - pd.Timedelta(days=1)
        exit_time = entry + pd.Timedelta(days=7)
        candidates: list[dict[str, Any]] = []
        for symbol in SYMBOLS:
            indicator = indicators[symbol]
            if decision not in indicator.index or entry not in bars[symbol].index or exit_time not in bars[symbol].index:
                continue
            values = indicator.loc[
                decision, ["hmom7", "hmom14", "hmom28", "mom7", "median_quote_volume_30d"]
            ]
            if values.isna().any() or float(values["median_quote_volume_30d"]) < CONFIG["minimum_median_quote_volume_30d"]:
                continue
            candidates.append({
                "entry_time": entry,
                "decision_time": decision,
                "exit_time": exit_time,
                "symbol": symbol,
                "entry_price": float(bars[symbol].at[entry, "open"]),
                "exit_price": float(bars[symbol].at[exit_time, "open"]),
                "hmom7": float(values["hmom7"]),
                "hmom14": float(values["hmom14"]),
                "hmom28": float(values["hmom28"]),
                "mom7": float(values["mom7"]),
            })
        if len(candidates) < int(CONFIG["minimum_rankable_symbols"]):
            continue
        for item in candidates:
            item["eligible_count"] = len(candidates)
        rows.extend(candidates)
    if not rows:
        raise RuntimeError("HMOM weekly panel is empty")
    return pd.DataFrame(rows).sort_values(["entry_time", "symbol"]).reset_index(drop=True)


def score_set(panel: pd.DataFrame, column: str) -> dict[pd.Timestamp, pd.DataFrame]:
    output: dict[pd.Timestamp, pd.DataFrame] = {}
    for entry, week in panel.groupby("entry_time", sort=True):
        ranked = week.copy()
        ranked["score"] = ranked[column]
        output[pd.Timestamp(entry)] = ranked
    return output


def preselect_bottom(scores: dict[pd.Timestamp, pd.DataFrame], count: int) -> dict[pd.Timestamp, pd.DataFrame]:
    return {
        entry: week.sort_values(["score", "symbol"], ascending=[True, True]).head(count).copy()
        for entry, week in scores.items()
    }


def stressed_short_rate(rate: float) -> float:
    if rate > 0:
        return rate * float(CONFIG["short_funding_stress"]["positive_benefit_multiplier"])
    return rate * float(CONFIG["short_funding_stress"]["negative_cost_multiplier"])


def make_short_trades(
    scores: dict[pd.Timestamp, pd.DataFrame],
    funding: dict[str, pd.DataFrame],
    stage: str,
    name: str,
    *,
    mode: str = "bottom",
    cooldown: bool = True,
) -> tuple[pd.DataFrame, dict[str, int]]:
    rows: list[dict[str, Any]] = []
    last_exit: dict[str, pd.Timestamp] = {}
    planned = excluded_marks = cooldown_skips = 0
    for entry in sorted(scores):
        week = scores[entry].copy()
        if mode == "bottom":
            count = int(math.ceil(len(week) * float(CONFIG["bottom_fraction"])))
            week = week.sort_values(["score", "symbol"], ascending=[True, True]).head(count)
        elif mode == "all":
            week = week.sort_values("symbol")
        else:
            raise ValueError(mode)
        for rank, (_, item) in enumerate(week.iterrows(), start=1):
            symbol = str(item["symbol"])
            planned += 1
            if cooldown and symbol in last_exit and entry <= last_exit[symbol] + pd.Timedelta(days=int(CONFIG["cooldown_full_days"])):
                cooldown_skips += 1
                continue
            exit_time = pd.Timestamp(item["exit_time"])
            rates = funding[symbol][(funding[symbol].index > entry) & (funding[symbol].index <= exit_time)]
            if rates["markPrice"].isna().any():
                excluded_marks += 1
                last_exit[symbol] = exit_time
                continue
            entry_price = float(item["entry_price"])
            exit_price = float(item["exit_price"])
            fraction = float(CONFIG["notional_fraction"])
            quantity = fraction / entry_price
            actual_funding = float((quantity * rates["markPrice"] * rates["fundingRate"]).sum())
            stress_funding = float(
                (quantity * rates["markPrice"] * rates["fundingRate"].map(stressed_short_rate)).sum()
            )
            gross_short = fraction * (1.0 - exit_price / entry_price)
            rows.append({
                "trade_id": f"{stage}-{name}-{entry:%Y%m%d}-{symbol}",
                "strategy_variant": name,
                "entry_time": entry,
                "exit_time": exit_time,
                "decision_time": item["decision_time"],
                "symbol": symbol,
                "score": float(item.get("score", np.nan)),
                "selection_rank": rank,
                "eligible_count": int(item["eligible_count"]),
                "entry_price": entry_price,
                "exit_price": exit_price,
                "notional_fraction": fraction,
                "quantity_per_unit_plan_capital": quantity,
                "funding_events": int(len(rates)),
                "actual_funding_return": actual_funding,
                "stress_funding_return": stress_funding,
                "gross_short_return": gross_short,
                "gross_long_return": gross_short,
            })
            last_exit[symbol] = exit_time
    return pd.DataFrame(rows), {
        "planned": planned,
        "excluded_missing_marks": excluded_marks,
        "cooldown_skips": cooldown_skips,
    }


def vectorbt_short_returns(base: Any, trades: pd.DataFrame, fee: float, slippage: float) -> np.ndarray:
    columns = trades["trade_id"].tolist()
    prices = pd.DataFrame(
        [trades["entry_price"].to_numpy(float), trades["exit_price"].to_numpy(float)], columns=columns
    )
    quantity = trades["quantity_per_unit_plan_capital"].to_numpy(float)
    sizes = pd.DataFrame([-quantity, quantity], columns=columns)
    portfolio = base.vbt.Portfolio.from_orders(
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


def attach_short_returns(base: Any, trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        raise RuntimeError("strategy produced no trades")
    output = trades.copy()
    for scenario, assumptions in CONFIG["costs"].items():
        fee = float(assumptions["fee_per_side"])
        slippage = float(assumptions["slippage_per_side"])
        vector = vectorbt_short_returns(base, output, fee, slippage)
        manual = output.apply(manual_short_return, axis=1, fee=fee, slippage=slippage).to_numpy(float)
        output[f"{scenario}_price_cost_return"] = vector
        output[f"{scenario}_reconciliation_error"] = vector - manual
        funding_column = "stress_funding_return" if assumptions["funding_stress"] else "actual_funding_return"
        output[f"{scenario}_net_return"] = vector + output[funding_column].to_numpy(float)
    return output


def compare_with_cash(base: Any, main: pd.DataFrame, baseline: pd.DataFrame) -> dict[str, Any]:
    left = base.date_returns(main, "base_net_return")
    raw_right = base.date_returns(baseline, "base_net_return")
    right = raw_right.reindex(left.index, fill_value=0.0)
    difference = left - right
    return {
        "main_mean": float(left.mean()),
        "baseline_mean": float(right.mean()),
        "difference_mean": float(difference.mean()),
        "difference_bootstrap_95pct": base.block_bootstrap_mean_ci(difference.to_numpy(float)),
        "positive_date_fraction": float((difference > 0).mean()),
        "baseline_no_action_dates_filled_as_cash": int((~left.index.isin(raw_right.index)).sum()),
    }


def command_prepare(args: argparse.Namespace) -> None:
    ensure_checkpoint()
    if args.stage != "development":
        raise RuntimeError("later stages are sealed")
    base = configure_base()
    parent_dq = read_json(PARENT_DIR / "data_quality_development.json")
    bars, funding = base.load_all()
    required_start = pd.Timestamp("2022-12-01T00:00:00Z")
    required_end = pd.Timestamp("2024-01-01T00:00:00Z")
    expected = pd.date_range(required_start, required_end, freq="D")
    per_symbol: dict[str, Any] = {}
    status = parent_dq.get("status") == "PASS"
    for symbol in SYMBOLS:
        frame = bars[symbol].sort_index()
        subset = frame[(frame.index >= required_start) & (frame.index <= required_end)]
        missing_days = int(len(expected.difference(subset.index)))
        invalid_ohlc = int((
            (subset[["open", "high", "low", "close"]] <= 0).any(axis=1)
            | (subset["high"] < subset[["open", "close"]].max(axis=1))
            | (subset["low"] > subset[["open", "close"]].min(axis=1))
        ).sum())
        duplicate_days = int(subset.index.duplicated().sum())
        rates = funding[symbol]
        stage_rates = rates[
            (rates.index >= pd.Timestamp(STAGES["development"][0]))
            & (rates.index <= pd.Timestamp(STAGES["development"][1]) + pd.Timedelta(days=7))
        ]
        missing_marks = int(stage_rates["markPrice"].isna().sum())
        per_symbol[symbol] = {
            "daily_rows": int(len(subset)),
            "missing_days": missing_days,
            "duplicate_days": duplicate_days,
            "invalid_ohlc_rows": invalid_ohlc,
            "funding_rows": int(len(stage_rates)),
            "missing_mark_rows": missing_marks,
        }
        status = status and missing_days == 0 and duplicate_days == 0 and invalid_ohlc == 0 and len(stage_rates) > 0
    payload = {
        "created_at_utc": iso_now(),
        "stage": args.stage,
        "status": "PASS" if status else "FAIL",
        "checkpoint_digest": read_json(HERE / "checkpoint.json")["content_digest"],
        "reused_parent_data_quality_digest": parent_dq["content_digest"],
        "required_daily_range_inclusive": [required_start.isoformat(), required_end.isoformat()],
        "symbols": per_symbol,
        "rule": (
            "Missing funding marks remain trade exclusions under the preregistered 2% gate; "
            "OHLCV and marks are not imputed."
        ),
    }
    write_json(HERE / "data_quality_development.json", payload, digest=True)
    print(json.dumps({"stage": args.stage, "status": payload["status"], "symbols": len(per_symbol)}))


def command_self_test(_args: argparse.Namespace) -> None:
    index = pd.date_range("2026-01-01T00:00:00Z", periods=40, freq="D")
    close = pd.Series(np.linspace(100.0, 120.0, 40), index=index)
    high = close * 1.02
    frame = pd.DataFrame({"close": close, "high": high, "quote_volume": 20_000_000.0}, index=index)
    output = hmom_frame(frame)
    expected = math.log(float(close.iloc[-1] / high.iloc[-7:].max()))
    if not math.isclose(float(output["hmom7"].iloc[-1]), expected, rel_tol=0.0, abs_tol=1e-14):
        raise RuntimeError("HMOM7 formula mismatch")
    base = configure_base()
    sample = pd.DataFrame([{
        "trade_id": "test",
        "entry_price": 100.0,
        "exit_price": 90.0,
        "quantity_per_unit_plan_capital": 0.005,
    }])
    vector = float(vectorbt_short_returns(base, sample, 0.0006, 0.0010)[0])
    manual = float(manual_short_return(sample.iloc[0], 0.0006, 0.0010))
    if not math.isclose(vector, manual, rel_tol=0.0, abs_tol=1e-12):
        raise RuntimeError("short VectorBT/manual mismatch")
    print(json.dumps({"status": "PASS", "hmom7": expected, "short_reconciliation": vector - manual}))


def command_analyze(args: argparse.Namespace) -> None:
    ensure_checkpoint()
    if args.stage != "development":
        raise RuntimeError("later stages are sealed until the prior gate passes")
    dq = read_json(HERE / "data_quality_development.json")
    if dq.get("status") != "PASS":
        raise RuntimeError("data quality is not PASS")
    base = configure_base()
    bars, funding = base.load_all()
    panel = build_panel(bars)
    categories = base.category_map()
    main_scores = score_set(panel, "hmom7")
    score_sets = {
        "main": main_scores,
        "hmom14": score_set(panel, "hmom14"),
        "hmom28": score_set(panel, "hmom28"),
        "bottom3": preselect_bottom(main_scores, 3),
        "mom7": score_set(panel, "mom7"),
        "scheduled_short": score_set(panel, "hmom7"),
        "market_short": score_set(panel, "hmom7"),
    }
    trades: dict[str, pd.DataFrame] = {}
    opportunity_counts: dict[str, dict[str, int]] = {}
    for name in ("main", "hmom14", "hmom28", "mom7"):
        raw, opportunity_counts[name] = make_short_trades(
            score_sets[name], funding, args.stage, name, mode="bottom", cooldown=True
        )
        trades[name] = attach_short_returns(base, raw)
    raw, opportunity_counts["bottom3"] = make_short_trades(
        score_sets["bottom3"], funding, args.stage, "bottom3", mode="all", cooldown=True
    )
    trades["bottom3"] = attach_short_returns(base, raw)
    for name, cooldown in (("scheduled_short", True), ("market_short", False)):
        raw, opportunity_counts[name] = make_short_trades(
            score_sets[name], funding, args.stage, name, mode="all", cooldown=cooldown
        )
        trades[name] = attach_short_returns(base, raw)
    csv_hashes: dict[str, str] = {}
    for name, frame in trades.items():
        path = HERE / f"{args.stage}_{name}_trades.csv"
        frame.to_csv(path, index=False, date_format="%Y-%m-%dT%H:%M:%S%z")
        csv_hashes[path.name] = sha256_file(path)
    summaries = {name: base.summarize(frame, args.stage, categories) for name, frame in trades.items()}
    gross_main = base.date_returns(trades["main"], "gross_short_return")
    gross_market = base.date_returns(trades["market_short"], "gross_short_return").reindex(gross_main.index)
    gross_excess = gross_main - gross_market
    rank_correlations = [
        float(week["hmom7"].corr(week["mom7"], method="spearman"))
        for _, week in panel.groupby("entry_time")
    ]
    comparisons = {
        "base_vs_mom7": compare_with_cash(base, trades["main"], trades["mom7"]),
        "base_vs_scheduled_short": compare_with_cash(base, trades["main"], trades["scheduled_short"]),
        "gross_vs_equal_weight_market_short": {
            "main_mean": float(gross_main.mean()),
            "market_mean": float(gross_market.mean()),
            "difference_mean": float(gross_excess.mean()),
            "difference_bootstrap_95pct": base.block_bootstrap_mean_ci(gross_excess.to_numpy(float)),
        },
        "hmom7_vs_mom7_weekly_spearman": {
            "median": float(np.median(rank_correlations)),
            "minimum": float(np.min(rank_correlations)),
            "maximum": float(np.max(rank_correlations)),
            "weeks": len(rank_correlations),
        },
    }
    payload = {
        "created_at_utc": iso_now(),
        "stage": args.stage,
        "checkpoint_digest": read_json(HERE / "checkpoint.json")["content_digest"],
        "data_quality_digest": dq["content_digest"],
        "panel_rows": int(len(panel)),
        "panel_weeks": int(panel["entry_time"].nunique()),
        "opportunity_counts": opportunity_counts,
        "summaries": summaries,
        "comparisons": comparisons,
        "trade_csv_sha256": csv_hashes,
    }
    write_json(HERE / f"{args.stage}.json", payload, digest=True)
    evidence = read_json(HERE / f"{args.stage}.json")
    print(json.dumps({
        "stage": args.stage,
        "trades": summaries["main"]["trades"],
        "base_after_hurdle": summaries["main"]["scenarios"]["base"]["date_mean_after_hurdle"],
        "stress_after_hurdle": summaries["main"]["scenarios"]["stress"]["date_mean_after_hurdle"],
        "digest": evidence["content_digest"],
    }))


def command_gate(args: argparse.Namespace) -> None:
    ensure_checkpoint()
    if args.stage != "development":
        raise RuntimeError("only development gate is implemented")
    evidence = read_json(HERE / "development.json")
    main = evidence["summaries"]["main"]
    base_summary = main["scenarios"]["base"]
    stress_summary = main["scenarios"]["stress"]
    counts = evidence["opportunity_counts"]["main"]
    excluded_fraction = counts["excluded_missing_marks"] / max(1, counts["planned"])
    positive_targets = sum(item["base_mean_after_hurdle"] > 0 for item in main["by_symbol"].values())
    positive_categories = sum(item["base_mean_after_hurdle"] > 0 for item in main["by_category"].values())
    neighbor_positive = sum(
        evidence["summaries"][name]["scenarios"]["stress"]["date_mean_after_hurdle"] >= 0
        for name in ("hmom14", "hmom28", "bottom3")
    )
    checks = {
        "data_quality_pass": read_json(HERE / "data_quality_development.json")["status"] == "PASS",
        "minimum_150_trades": main["trades"] >= 150,
        "minimum_20_symbols": main["symbols"] >= 20,
        "minimum_45_entry_dates": main["entry_dates"] >= 45,
        "excluded_missing_marks_at_most_2pct": excluded_fraction <= 0.02,
        "base_after_hurdle_positive": base_summary["date_mean_after_hurdle"] > 0,
        "stress_after_hurdle_positive": stress_summary["date_mean_after_hurdle"] > 0,
        "stress_bootstrap_lower_positive": stress_summary["date_mean_after_hurdle_bootstrap_95pct"][0] > 0,
        "both_halves_base_positive": all(
            item["dates"] > 0 and item["mean_after_hurdle"] > 0 for item in main["by_half"].values()
        ),
        "date_portfolio_drawdown_above_minus_20pct": base_summary["date_portfolio_max_drawdown"] > -0.20,
        "worst_symbol_drawdown_above_minus_40pct": main["worst_symbol_base_max_drawdown"] > -0.40,
        "base_beats_mom7": evidence["comparisons"]["base_vs_mom7"]["difference_mean"] > 0,
        "base_beats_scheduled_short": evidence["comparisons"]["base_vs_scheduled_short"]["difference_mean"] > 0,
        "gross_excess_vs_market_short_positive": (
            evidence["comparisons"]["gross_vs_equal_weight_market_short"]["difference_mean"] > 0
        ),
        "gross_excess_bootstrap_lower_positive": (
            evidence["comparisons"]["gross_vs_equal_weight_market_short"]["difference_bootstrap_95pct"][0] > 0
        ),
        "at_least_two_of_three_neighbors_stress_nonnegative": neighbor_positive >= 2,
        "at_least_half_selected_targets_positive": positive_targets / max(1, main["symbols"]) >= 0.5,
        "at_least_four_categories_positive": positive_categories >= 4,
        "largest_positive_pnl_share_at_most_20pct": main["largest_positive_pnl_share"] <= 0.20,
        "vectorbt_manual_reconciliation": main["maximum_vectorbt_reconciliation_error"] <= 1e-10,
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    gate = {
        "created_at_utc": iso_now(),
        "stage": args.stage,
        "status": status,
        "checks": checks,
        "failed": [name for name, passed in checks.items() if not passed],
        "evidence_digest": evidence["content_digest"],
        "excluded_missing_mark_fraction": excluded_fraction,
    }
    write_json(HERE / "development_gate.json", gate, digest=True)
    if status == "FAIL":
        does_not_support = (
            base_summary["date_mean_after_hurdle"] <= 0
            or stress_summary["date_mean_after_hurdle"] <= 0
            or not checks["base_beats_mom7"]
        )
        conclusion = "DOES_NOT_SUPPORT" if does_not_support else "INSUFFICIENT_EVIDENCE"
        results = {
            "created_at_utc": iso_now(),
            "question": read_json(HERE / "checkpoint.json")["question"],
            "conclusion": conclusion,
            "development_gate": "FAIL",
            "development_digest": evidence["content_digest"],
            "gate_digest": read_json(HERE / "development_gate.json")["content_digest"],
            "later_stage_outputs": 0,
            "handoff_generated": False,
            "summary": {
                "trades": main["trades"],
                "entry_dates": main["entry_dates"],
                "symbols": main["symbols"],
                "base_mean_after_hurdle": base_summary["date_mean_after_hurdle"],
                "stress_mean_after_hurdle": stress_summary["date_mean_after_hurdle"],
                "stress_bootstrap_95pct": stress_summary["date_mean_after_hurdle_bootstrap_95pct"],
                "base_max_drawdown": base_summary["date_portfolio_max_drawdown"],
                "base_vs_mom7": evidence["comparisons"]["base_vs_mom7"],
                "base_vs_scheduled_short": evidence["comparisons"]["base_vs_scheduled_short"],
                "gross_excess_vs_market_short": evidence["comparisons"]["gross_vs_equal_weight_market_short"],
                "rank_correlation_with_mom7": evidence["comparisons"]["hmom7_vs_mom7_weekly_spearman"],
                "largest_positive_pnl_share": main["largest_positive_pnl_share"],
                "failed_checks": gate["failed"],
            },
        }
        write_json(HERE / "results.json", results, digest=True)
        result_text = f"""# 结果：HMOM7 底部五分位 SHORT 未通过开发门

## 结论

`{conclusion}`

固定的一周高点距离、底部五分位和 `0.5x SHORT / 7d` 转换在 2023 development 没有通过全部现实成本、统计、基准、稳健性、广度与风险门。它不进入 evaluation/confirmation，不生成交易核心 handoff，也不修改正式策略、产品代码、资金或真实账户。

## 关键数值

- 交易 / entry dates / 目标：`{main['trades']} / {main['entry_dates']} / {main['symbols']}`。
- base / stress 扣 4% 全计划资本周门槛均值：`{base_summary['date_mean_after_hurdle']:.6%} / {stress_summary['date_mean_after_hurdle']:.6%}`。
- stress 四周 block-bootstrap 95% 区间：`[{stress_summary['date_mean_after_hurdle_bootstrap_95pct'][0]:.6%}, {stress_summary['date_mean_after_hurdle_bootstrap_95pct'][1]:.6%}]`。
- base date-portfolio 最大回撤：`{base_summary['date_portfolio_max_drawdown']:.6%}`。
- 相对 MOM7 输家 SHORT 的 base 均值差：`{evidence['comparisons']['base_vs_mom7']['difference_mean']:.6%}`。
- gross 相对同周等权市场 SHORT 均值差：`{evidence['comparisons']['gross_vs_equal_weight_market_short']['difference_mean']:.6%}`。
- HMOM7 与 MOM7 周横截面 Spearman 中位数：`{evidence['comparisons']['hmom7_vs_mom7_weekly_spearman']['median']:.4f}`。
- 失败门：`{', '.join(gate['failed'])}`。

## 解释边界

本结果只判断当前幸存 25 个 Binance USD-M 永续、固定单目标、零售成本和 one-shot 转换；不推翻论文的 point-in-time 多币组合。论文 Q1 原始均值本就不显著，显著的是风险调整 alpha；本题必须同时通过绝对净收益和市场相对门，不能只挑其中之一。相同市场路径此前已被其他问题查看，且正回测也不会证明长期 Alpha。
"""
        (HERE / "result.md").write_text(result_text, encoding="utf-8")
    print(json.dumps({"status": status, "failed": gate["failed"]}))


def command_validate(_args: argparse.Namespace) -> None:
    checkpoint = ensure_checkpoint()
    required = [
        "source_reuse_manifest.json",
        "checkpoint.json",
        "data_quality_development.json",
        "development.json",
        "development_gate.json",
    ]
    gate = read_json(HERE / "development_gate.json")
    if gate["status"] == "FAIL":
        required.append("results.json")
    for name in required:
        payload = read_json(HERE / name)
        if canonical_digest(payload) != payload.get("content_digest"):
            raise RuntimeError(f"stable digest mismatch: {name}")
    evidence = read_json(HERE / "development.json")
    for name, expected in evidence["trade_csv_sha256"].items():
        if sha256_file(HERE / name) != expected:
            raise RuntimeError(f"trade CSV mismatch: {name}")
    later = list(HERE.glob("evaluation*")) + list(HERE.glob("confirmation*")) + list(HERE.glob("handoff*"))
    if gate["status"] == "FAIL" and later:
        raise RuntimeError("later-stage artifact exists after development failure")
    result = read_json(HERE / "results.json") if (HERE / "results.json").exists() else {}
    payload = {
        "validated_at_utc": iso_now(),
        "status": "PASS",
        "checkpoint_digest": checkpoint["content_digest"],
        "json_digest_files_checked": len(required),
        "trade_csv_files_checked": len(evidence["trade_csv_sha256"]),
        "conclusion": result.get("conclusion"),
        "later_stage_outputs": len(later),
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
